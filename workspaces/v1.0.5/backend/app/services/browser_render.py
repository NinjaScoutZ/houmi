"""Canonical WYSIWYG render ingestion.

Chromium/Fabric is the typesetting renderer used by the editor preview.  This
module deliberately does not lay text out again: it validates a transparent
PNG produced by that same canvas and alpha-composites it onto the full-quality
page background.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.config import PROJECTS_DIR
from app.models.all_models import Page
from app.services.project_paths import rendered_asset_path


MAX_BROWSER_RENDER_BYTES = 128 * 1024 * 1024
MAX_BROWSER_RENDER_PIXELS = 300_000_000
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
RENDER_ENGINE = "fabric-browser-v1"


class BrowserRenderError(ValueError):
    """Invalid or unsafe browser render payload."""


class StaleBrowserRenderError(BrowserRenderError):
    """The page changed after the browser received its render contract."""


def _json_value(value: Any) -> Any:
    """Return a deterministic JSON-compatible value for revision hashing."""
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


def _render_relevant_metadata(metadata: Any) -> Any:
    """Drop export bookkeeping that cannot change the rendered pixels."""
    if not isinstance(metadata, dict):
        return _json_value(metadata or {})
    return _json_value({
        key: value
        for key, value in metadata.items()
        if key not in {"psd_export_snapshot", "psd_export_history"}
    })


def page_render_revision(page: Page, background_kind: str = "clean") -> str:
    if background_kind not in {"clean", "source"}:
        raise BrowserRenderError("background_kind must be 'clean' or 'source'")

    if background_kind == "clean":
        background = Path(page.inpainted_image_path) if page.inpainted_image_path else Path(page.source_image_path)
    else:
        background = Path(page.source_image_path)

    try:
        stat = background.stat()
        background_fingerprint = {
            "path": str(background.resolve()),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }
    except OSError:
        background_fingerprint = {"path": str(background), "missing": True}

    blocks = []
    for block in sorted(page.text_blocks, key=lambda item: (item.block_index, item.id)):
        blocks.append({
            "id": block.id,
            "block_index": block.block_index,
            "x": block.x,
            "y": block.y,
            "width": block.width,
            "height": block.height,
            "rotation_deg": block.rotation_deg,
            "source_text": block.source_text,
            "translation": block.translation,
            "font_family": block.font_family,
            "font_size": block.font_size,
            "color_hex": block.color_hex,
            "bold": block.bold,
            "italic": block.italic,
            "text_direction": block.text_direction,
            "text_align": block.text_align,
            "balloon_type": block.balloon_type,
            "extra_metadata": _render_relevant_metadata(block.extra_metadata or {}),
        })

    payload = {
        "page_id": page.id,
        "width": page.width,
        "height": page.height,
        "background_kind": background_kind,
        "background": background_fingerprint,
        "blocks": blocks,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def render_metadata_path(page: Page) -> Path:
    # Keep implementation metadata out of the user's flat `rendered` folder;
    # that folder should contain only the numbered deliverable images.
    return PROJECTS_DIR / str(page.project_id) / str(page.id) / "rendered" / "browser_render.json"


def browser_overlay_path(page: Page) -> Path:
    """Canonical transparent Fabric text overlay used by editable PSD fallbacks."""
    return PROJECTS_DIR / str(page.project_id) / str(page.id) / "rendered" / "browser_overlay.png"


def browser_render_is_fresh(page: Page) -> bool:
    output = rendered_asset_path(page)
    metadata_path = render_metadata_path(page)
    if not output.exists() or not metadata_path.exists():
        return False
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        kind = str(metadata.get("background_kind", "clean"))
        return (
            metadata.get("engine") == RENDER_ENGINE
            and metadata.get("revision") == page_render_revision(page, kind)
            and metadata.get("width") == page.width
            and metadata.get("height") == page.height
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def save_browser_render(
    page_id: str,
    overlay_bytes: bytes,
    revision: str,
    background_kind: str,
    db: Session,
) -> Path:
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise LookupError("Page not found")
    if len(overlay_bytes) > MAX_BROWSER_RENDER_BYTES:
        raise BrowserRenderError("Render overlay exceeds the 128 MiB upload limit")
    if not overlay_bytes.startswith(PNG_SIGNATURE):
        raise BrowserRenderError("Render overlay must be a PNG image")

    expected_revision = page_render_revision(page, background_kind)
    if revision != expected_revision:
        raise StaleBrowserRenderError("Page changed while the preview render was being captured")

    try:
        with Image.open(BytesIO(overlay_bytes)) as candidate:
            if candidate.format != "PNG":
                raise BrowserRenderError("Render overlay must be a PNG image")
            if int(getattr(candidate, "n_frames", 1)) != 1:
                raise BrowserRenderError("Animated PNG overlays are not supported")
            if candidate.width * candidate.height > MAX_BROWSER_RENDER_PIXELS:
                raise BrowserRenderError("Render overlay dimensions exceed the safety limit")
            if candidate.size != (page.width, page.height):
                raise BrowserRenderError(
                    f"Render overlay must be exactly {page.width}x{page.height}px; "
                    f"received {candidate.width}x{candidate.height}px"
                )
            if candidate.mode != "RGBA":
                raise BrowserRenderError("Render overlay must contain an alpha channel")
            candidate.load()
            overlay = candidate.copy()
    except BrowserRenderError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise BrowserRenderError("Render overlay is not a valid PNG image") from exc

    if background_kind == "clean":
        if not page.inpainted_image_path or not Path(page.inpainted_image_path).exists():
            try:
                from app.services.inpainter import clean_page_text
                clean_path = clean_page_text(page.id, db)
                page.inpainted_image_path = str(clean_path)
                db.commit()
                db.refresh(page)
            except Exception as exc:
                raise BrowserRenderError(f"Clean page background is not available: {exc}")
        background_path = Path(page.inpainted_image_path)
    elif background_kind == "source":
        background_path = Path(page.source_image_path)
    else:
        raise BrowserRenderError("background_kind must be 'clean' or 'source'")

    if not background_path.exists():
        raise BrowserRenderError(f"Page background is missing: {background_path}")

    with Image.open(background_path) as source:
        if source.size != (page.width, page.height):
            page.width, page.height = source.size
            try:
                db.commit()
            except Exception:
                pass
        composite = Image.alpha_composite(source.convert("RGBA"), overlay)

    output_path = rendered_asset_path(page)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        # PNG optimization performs several expensive whole-page passes and is
        # especially painful for 15k-20k pixel webtoons. A moderate compression
        # level is lossless, pixel-identical, and dramatically faster.
        composite.save(temporary, format="PNG", compress_level=3)
        os.replace(temporary, output_path)
    finally:
        temporary.unlink(missing_ok=True)

    # Preserve the exact transparent canvas, not just the flattened preview.
    # PSD text layers use crops from this file as their pixel fallback when
    # Photoshop decides it must recompose the editable Type Engine data.
    overlay_path = browser_overlay_path(page)
    _atomic_write_bytes(overlay_path, overlay_bytes)

    metadata = {
        "engine": RENDER_ENGINE,
        "revision": expected_revision,
        "background_kind": background_kind,
        "width": page.width,
        "height": page.height,
        "overlay_file": overlay_path.name,
    }
    _atomic_write_json(render_metadata_path(page), metadata)

    page.rendered_image_path = str(output_path)
    page.status = "processed"
    db.commit()
    db.refresh(page)
    return output_path
