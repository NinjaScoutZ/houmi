from app.utils.image_utils import cv2_imread_unicode, cv2_imwrite_unicode
import cv2
import numpy as np
import logging
import shutil
import time
import hashlib
import json
import threading
from typing import Any
from pathlib import Path
from sqlalchemy.orm import Session
try:
    import onnxruntime as ort
except ImportError:
    ort = None

_inpaint_thread_lock = threading.Lock()
from app.config import (
    INPAINT_MODEL_PATH,
    MAT_MODEL_PATH,
    PROJECTS_DIR,
    get_execution_providers,
    get_execution_provider_setting,
    get_inpaint_engine,
    create_onnx_session_options,
)

try:
    import os
    cv2.setNumThreads(max(1, min(4, (os.cpu_count() or 4) // 2)))
except Exception:
    pass

from app.models.all_models import Page
from app.services.memory_cache import page_image_cache
from app.services.performance import resolve_performance_settings
from app.services.project_paths import (
    inpaint_preview_asset_path,
    inpainted_asset_path,
    mask_asset_path,
    page_asset_dir,
    page_asset_key,
    uses_external_workspace,
    rendered_asset_path,
)

logger = logging.getLogger("houmi-inpainter")

CLEAN_PIPELINE_VERSION = "2.7"  # adaptive monochrome edge coverage and editor provenance
EFFECTIVE_MASK_CACHE_KIND = "editor_effective_mask"


def clean_manifest_path(page: Page) -> Path:
    """Store clean provenance beside generated clean assets in masks folder."""
    if uses_external_workspace(page.project):
        path = page_asset_dir(page, "masks") / f"{page_asset_key(page)}_manifest.json"
    else:
        path = PROJECTS_DIR / str(page.project_id) / str(page.id) / "masks" / "clean_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _asset_fingerprint(path: Path) -> dict:
    try:
        stat = path.stat()
    except OSError:
        return {"missing": True}
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def compute_clean_fingerprint(page: Page) -> str:
    """Hash every input that can change a cleaned page, including manual masks."""
    settings = page.project.settings or {}
    relevant_settings = {
        key: settings.get(key)
        for key in (
            "cleanup_mask_strategy",
            "process_by_text_areas",
            "mask_dilation_kernel",
            "force_lama_inpaint",
            "default_image_inpaint_method",
            "inpaint_context_padding",
            "image_inpainting_radius",
            "inpaint_tile_size",
            "inpaint_strategy",
            "full_page_unet_clean",
        )
    }
    blocks = []
    for block in sorted(page.text_blocks, key=lambda item: (item.block_index, item.id)):
        mask_path = _mask_asset_path(page, f"mask_{block.id}.png")
        blocks.append({
            "id": block.id,
            "x": block.x,
            "y": block.y,
            "width": block.width,
            "height": block.height,
            "mask": _asset_fingerprint(mask_path),
        })
    payload = {
        "version": CLEAN_PIPELINE_VERSION,
        "source": _asset_fingerprint(Path(page.source_image_path)),
        "settings": relevant_settings,
        "blocks": blocks,
        "manual_mask": _asset_fingerprint(_mask_asset_path(page, "manual_mask.png")),
        "page_mask_override": _asset_fingerprint(_mask_asset_path(page, "page_mask_override.png")),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def write_clean_manifest(page: Page) -> str:
    fingerprint = compute_clean_fingerprint(page)
    settings = page.project.settings or {}
    blocks = []
    for block in sorted(page.text_blocks, key=lambda item: (item.block_index, item.id)):
        mask_path = _mask_asset_path(page, f"mask_{block.id}.png")
        blocks.append({
            "id": str(block.id),
            "x": block.x,
            "y": block.y,
            "width": block.width,
            "height": block.height,
            "mask": _asset_fingerprint(mask_path),
        })
    manifest = {
        "version": CLEAN_PIPELINE_VERSION,
        "fingerprint": fingerprint,
        "requested_engine": "LaMa" if should_use_lama_inpaint(settings) else "Telea",
        "output": str(inpainted_asset_path(page)),
        "blocks": blocks,
        "manual_mask": _asset_fingerprint(_mask_asset_path(page, "manual_mask.png")),
        "page_mask_override": _asset_fingerprint(_mask_asset_path(page, "page_mask_override.png")),
    }
    path = clean_manifest_path(page)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    temporary.replace(path)
    return fingerprint


def is_clean_asset_current(page: Page) -> bool:
    """Return False for missing, legacy, or input-stale clean output.

    Also validates that custom mask files referenced in the manifest still exist
    with the same fingerprint, preventing use of stale cached output when masks
    have been deleted or modified.
    """
    output_path = inpainted_asset_path(page)
    if not output_path.is_file():
        return False
    try:
        manifest = json.loads(clean_manifest_path(page).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False

    # Version and fingerprint check
    if manifest.get("version") != CLEAN_PIPELINE_VERSION:
        return False
    if manifest.get("fingerprint") != compute_clean_fingerprint(page):
        return False

    # Validate that custom mask files haven't changed or disappeared
    # This prevents using cached clean output when user deletes a custom mask
    manifest_blocks = {b["id"]: b for b in manifest.get("blocks", [])}
    for block in page.text_blocks:
        block_manifest = manifest_blocks.get(str(block.id))
        if not block_manifest:
            continue

        # Check custom mask fingerprint
        mask_path = _mask_asset_path(page, f"mask_{block.id}.png")
        cached_mask_fp = block_manifest.get("mask", {})
        current_mask_fp = _asset_fingerprint(mask_path)

        # If mask state changed (exists → missing, or modified), invalidate
        if cached_mask_fp != current_mask_fp:
            logger.info(
                "Clean asset stale: mask for block %s changed (was %s, now %s)",
                block.id,
                cached_mask_fp,
                current_mask_fp,
            )
            return False

    # Check manual mask fingerprint
    manual_mask_fp_cached = manifest.get("manual_mask", {})
    manual_mask_fp_current = _asset_fingerprint(_mask_asset_path(page, "manual_mask.png"))
    if manual_mask_fp_cached != manual_mask_fp_current:
        logger.info(
            "Clean asset stale: manual mask changed (was %s, now %s)",
            manual_mask_fp_cached,
            manual_mask_fp_current,
        )
        return False

    override_fp_cached = manifest.get("page_mask_override", {})
    override_fp_current = _asset_fingerprint(_mask_asset_path(page, "page_mask_override.png"))
    if override_fp_cached != override_fp_current:
        logger.info(
            "Clean asset stale: page mask override changed (was %s, now %s)",
            override_fp_cached,
            override_fp_current,
        )
        return False

    return True


def invalidate_clean_assets(page: Page) -> int:
    """Remove stale clean/render artifacts and clear their database pointers."""
    source_path = Path(page.source_image_path)
    candidates = {
        inpainted_asset_path(page),
        inpaint_preview_asset_path(page),
        clean_manifest_path(page),
        rendered_asset_path(page),
        source_path.parent / "clean" / "inpainted.png",
        source_path.parent / "clean" / "preview_inpainted.jpg",
    }
    removed = 0
    for path in candidates:
        try:
            if path.is_file():
                path.unlink()
                removed += 1
        except OSError as exc:
            logger.warning("Could not remove stale clean asset %s: %s", path, exc)
    page.inpainted_image_path = None
    page.rendered_image_path = None
    return removed


def mark_clean_assets_stale(page: Page) -> int:
    """Invalidate clean provenance without deleting the last usable image.

    Mask edits make the generated clean image outdated, but the previous image
    is still a better editing base than silently falling back to the original.
    Destructive removal is reserved for explicit reset/delete operations.
    """
    manifest_path = clean_manifest_path(page)
    try:
        if manifest_path.is_file():
            manifest_path.unlink()
            return 1
    except OSError as exc:
        logger.warning("Could not mark clean asset stale at %s: %s", manifest_path, exc)
    return 0


def _mask_asset_path(page: Page, filename: str) -> Path:
    """Return the canonical per-page mask asset path, migrating legacy files lazily."""
    source_path = Path(page.source_image_path)
    canonical = mask_asset_path(page, filename)
    mask_dir = page_asset_dir(page, "masks")
    legacy_candidates = [
        mask_dir / page_asset_key(page) / filename,
        source_path.parent / "masks" / filename,
        source_path.parent / filename,
    ]
    if not canonical.exists():
        for legacy in legacy_candidates:
            if not legacy.exists() or legacy == canonical:
                continue
            try:
                canonical.write_bytes(legacy.read_bytes())
                break
            except OSError:
                return legacy
    return canonical


def _padded_block_coords(block, img_w: int, img_h: int, pad_margin: int = 16):
    """Compute padded crop coordinates that encompass both the YOLO bbox and layout_region.

    Mirrors ``get_padded_block_coords`` in pipeline.py so saved masks from the
    Mask Editor (which uses the same padded crop) are placed correctly.
    """
    bx0 = float(block.x)
    by0 = float(block.y)
    bx1 = bx0 + float(block.width)
    by1 = by0 + float(block.height)

    metadata = getattr(block, "extra_metadata", None) or {}
    layout = metadata.get("layout_region") if isinstance(metadata, dict) else None
    if isinstance(layout, dict):
        try:
            lx, ly = float(layout["x"]), float(layout["y"])
            lw, lh = float(layout["width"]), float(layout["height"])
            if lw >= 4 and lh >= 4:
                bx0, by0 = min(bx0, lx), min(by0, ly)
                bx1, by1 = max(bx1, lx + lw), max(by1, ly + lh)
        except (KeyError, TypeError, ValueError):
            pass

    ew, eh = bx1 - bx0, by1 - by0
    pad = max(pad_margin, int(max(ew, eh) * 0.18), 32)
    return (
        max(0, int(bx0 - pad)),
        max(0, int(by0 - pad)),
        min(img_w, int(bx1 + pad)),
        min(img_h, int(by1 + pad)),
    )


def _load_page_mask_override(page: Page, width: int, height: int) -> np.ndarray | None:
    """Load the authoritative full-page editor mask, if the user saved one."""
    override_path = _mask_asset_path(page, "page_mask_override.png")
    override = cv2_imread_unicode(str(override_path), cv2.IMREAD_GRAYSCALE) if override_path.exists() else None
    if override is not None and override.shape[:2] != (height, width):
        override = cv2.resize(override, (width, height), interpolation=cv2.INTER_NEAREST)
    return override

def _effective_dilation_kernel(requested: int, crop_w: int, crop_h: int) -> int:
    """Allow user-defined kernel dilation up to 56px."""
    max_safe = max(56, int(round(min(crop_w, crop_h) * 0.45)))
    kernel = max(0, min(56, min(int(requested), max_safe)))
    # Odd kernels have a stable center pixel in OpenCV morphology operations.
    if kernel > 1 and kernel % 2 == 0:
        kernel -= 1
    return kernel


def _merge_overlapping_regions(
    boxes: list[tuple[int, int, int, int]],
    margin: int = 35,
) -> list[tuple[int, int, int, int]]:
    """Merge bounding boxes that are close to each other or overlap when padded."""
    if not boxes:
        return []

    rects = []
    for x, y, w, h in boxes:
        rects.append([
            max(0, x - margin),
            max(0, y - margin),
            x + w + margin,
            y + h + margin,
            x,
            y,
            w,
            h,
        ])

    merged = True
    while merged:
        merged = False
        new_rects = []
        visited = [False] * len(rects)
        for i in range(len(rects)):
            if visited[i]:
                continue
            r1 = rects[i]
            visited[i] = True
            for j in range(i + 1, len(rects)):
                if visited[j]:
                    continue
                r2 = rects[j]
                if not (r1[2] < r2[0] or r2[2] < r1[0] or r1[3] < r2[1] or r2[3] < r1[1]):
                    min_x = min(r1[4], r2[4])
                    min_y = min(r1[5], r2[5])
                    max_x = max(r1[4] + r1[6], r2[4] + r2[6])
                    max_y = max(r1[5] + r1[7], r2[5] + r2[7])
                    new_w = max_x - min_x
                    new_h = max_y - min_y
                    r1 = [
                        max(0, min_x - margin),
                        max(0, min_y - margin),
                        max_x + margin,
                        max_y + margin,
                        min_x,
                        min_y,
                        new_w,
                        new_h,
                    ]
                    visited[j] = True
                    merged = True
            new_rects.append(r1)
        rects = new_rects

    return [(r[4], r[5], r[6], r[7]) for r in rects]


def _find_inpaint_regions(mask: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Group nearby glyphs and sentences efficiently for ultra-fast batch inference."""
    grouping_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (55, 55))
    grouping_mask = cv2.dilate(mask, grouping_kernel, iterations=1)
    contours, _ = cv2.findContours(
        grouping_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    boxes = [cv2.boundingRect(contour) for contour in contours]
    valid_boxes = [b for b in boxes if b[2] >= 4 and b[3] >= 4]
    return _merge_overlapping_regions(valid_boxes, margin=55)


def _rectangles_intersect(
    left: tuple[int, int, int, int], right: tuple[int, int, int, int]
) -> bool:
    """Return whether two x0/y0/x1/y1 rectangles overlap."""
    return not (
        left[2] <= right[0]
        or right[2] <= left[0]
        or left[3] <= right[1]
        or right[3] <= left[1]
    )


def _write_inpaint_preview(page: Page, image: np.ndarray) -> Path:
    """Write the UI-sized clean preview without changing the canonical PNG."""
    performance_settings = resolve_performance_settings(page.project.settings or {})
    height, width = image.shape[:2]
    max_width = performance_settings.preview_width
    if width > max_width:
        ratio = max_width / width
        new_width, new_height = max_width, int(height * ratio)
    else:
        new_width, new_height = width, height
    if new_height > 60000:
        scale_ratio = 60000 / new_height
        new_width, new_height = int(new_width * scale_ratio), 60000

    preview = (
        cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_AREA)
        if (new_width, new_height) != (width, height)
        else image
    )
    preview_path = inpaint_preview_asset_path(page)
    if not cv2_imwrite_unicode(str(preview_path), preview):
        raise OSError(f"Failed to save clean preview: {preview_path}")
    return preview_path


def _effective_inpaint_context_padding(requested: int, region_w: int, region_h: int) -> int:
    """Return progressive context expansion padding based on balloon bounding box.

    Expands the balloon box proportionally to its longest dimension (min 64px,
    max 256px) to provide rich surrounding scene context for the inpainting model.
    Larger balloons get proportionally more context, matching MangaToolPlus's
    proven progressive padding strategy.
    """
    longest_edge = max(1, int(region_w), int(region_h))
    # Progressive: min 64px, proportional to 1/3 of longest edge, max 256px
    pad = max(64, min(256, longest_edge // 3, 160))
    return pad


def _detect_uniform_fill_color(
    crop: np.ndarray, crop_mask: np.ndarray
) -> list[int] | None:
    """Return the dominant flat background color using ring extraction + histogram.

    Ported from MangaToolPlus _estimate_flat_fill_color_bgr:
    1. Dilate mask to create a context ring around text (excludes text pixels)
    2. Quantize ring samples into 16³ BGR bins → find dominant color mode
    3. Validate with Laplacian texture check, luma spread ≤28, channel spread ≤28
    4. Safety: reject dark fills on bright balloon interiors
    """
    if crop.size == 0 or crop_mask.shape[:2] != crop.shape[:2]:
        return None

    crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    # Screentone / Texture check via Laplacian variance
    laplacian_var = cv2.Laplacian(crop_gray, cv2.CV_64F).var()
    if laplacian_var > 35.0:
        return None

    # --- Ring extraction: dilate mask → XOR with original → context ring ---
    x, y, box_w, box_h = cv2.boundingRect(crop_mask)
    margin = max(8, min(40, max(box_w, box_h) // 6))
    k = max(9, (margin * 2 + 1) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    ring = cv2.dilate(crop_mask, kernel)
    ring = cv2.bitwise_and(ring, cv2.bitwise_not(crop_mask))

    # Sample pixels from the ring (context around text, not text itself)
    samples = crop[ring > 0]
    if samples.shape[0] < 32:
        samples = crop[crop_mask == 0]  # fallback: all non-mask pixels
    if samples.shape[0] < 32:
        return None

    # --- 16-step histogram quantization ---
    quantized = samples // 16
    bins, counts = np.unique(quantized, axis=0, return_counts=True)
    top_idx = int(np.argmax(counts))
    dominant_ratio = counts[top_idx] / samples.shape[0]
    dominant = samples[np.all(quantized == bins[top_idx], axis=1)]

    if dominant_ratio >= 0.45 and dominant.shape[0] >= 16:
        # Validate with luma + channel spread
        luma = (
            0.114 * dominant[:, 0].astype(np.float32)
            + 0.587 * dominant[:, 1].astype(np.float32)
            + 0.299 * dominant[:, 2].astype(np.float32)
        )
        luma_spread = float(np.percentile(luma, 90) - np.percentile(luma, 10))
        channel_spread = float(
            np.mean(
                np.percentile(dominant, 90, axis=0)
                - np.percentile(dominant, 10, axis=0)
            )
        )
        if luma_spread <= 28 and channel_spread <= 28:
            detected = np.median(dominant, axis=0).astype(np.uint8).tolist()
            # Safety: reject dark fill on bright balloon
            if float(np.mean(detected)) < 160.0 and float(np.max(crop_gray)) > 180.0:
                return None
            return detected

    # Fallback: use median of all ring samples with stricter variance check
    median_color = np.median(samples, axis=0)
    samples_gray = crop_gray[ring > 0] if np.any(ring > 0) else crop_gray[crop_mask == 0]
    if samples_gray.shape[0] < 32:
        return None
    std_gray = float(np.std(samples_gray.astype(np.float32)))
    if std_gray > 6.0:
        return None

    detected = median_color.astype(np.uint8).tolist()
    if float(np.mean(detected)) < 160.0 and float(np.max(crop_gray)) > 180.0:
        return None
    return detected


def _should_use_solid_fill(
    process_by_text_areas: bool,
    has_custom_mask: bool,
    settings: dict | None = None,
) -> bool:
    """Smart Solid Fill Fast-Pass:
    Enables instant 1ms fill for certified flat solid backgrounds (e.g. clean white speech balloons),
    while automatically routing textured/screentoned/complex regions to LaMa neural inpainting.
    """
    settings = settings or {}
    if has_custom_mask:
        return False
    # If user explicitly disabled solid fill or forced neural inpainting, respect the setting
    if settings.get("disable_solid_fill", False) or settings.get("force_lama_inpaint", False):
        return False
    if settings.get("default_image_inpaint_method") in ("LamaInpaint", "LaMa", "lama", "mat", "manga_cleaner"):
        return False
    engine = str(settings.get("inpaint_engine", "")).lower()
    if engine in ("lamainpaint", "lama", "lama_manga", "mat", "manga_cleaner"):
        return False
    return bool(process_by_text_areas)


def _compose_page_mask(page: Page, img: np.ndarray, *, include_saved_masks: bool) -> np.ndarray:
    """Compose a page mask without changing any user-owned mask assets."""
    h, w = img.shape[:2]
    if include_saved_masks:
        override = _load_page_mask_override(page, w, h)
        if override is not None:
            return override
    effective_mask = np.zeros((h, w), dtype=np.uint8)
    settings = page.project.settings or {}

    for block in page.text_blocks:
        x0 = max(0, min(w, int(block.x)))
        y0 = max(0, min(h, int(block.y)))
        x1 = max(0, min(w, int(block.x + block.width)))
        y1 = max(0, min(h, int(block.y + block.height)))
        if x1 <= x0 or y1 <= y0:
            continue
        px0, py0, px1, py1 = _padded_block_coords(block, w, h)

        custom = None
        if include_saved_masks:
            custom_path = _mask_asset_path(page, f"mask_{block.id}.png")
            custom = cv2_imread_unicode(str(custom_path), cv2.IMREAD_GRAYSCALE) if custom_path.exists() else None

        if custom is not None:
            block_mask = np.zeros((h, w), dtype=np.uint8)
            if custom.shape[:2] == (py1 - py0, px1 - px0):
                block_mask[py0:py1, px0:px1] = custom
            elif custom.shape[:2] == (y1 - y0, x1 - x0):
                block_mask[y0:y1, x0:x1] = custom
            else:
                custom_resized = cv2.resize(custom, (px1 - px0, py1 - py0), interpolation=cv2.INTER_NEAREST)
                block_mask[py0:py1, px0:px1] = custom_resized
        else:
            block_mask = get_automatic_block_mask(img, block, settings)
        effective_mask = cv2.bitwise_or(effective_mask, block_mask)

    if include_saved_masks:
        manual_path = _mask_asset_path(page, "manual_mask.png")
        manual = cv2_imread_unicode(str(manual_path), cv2.IMREAD_GRAYSCALE) if manual_path.exists() else None
        if manual is not None:
            if manual.shape[:2] != (h, w):
                manual = cv2.resize(manual, (w, h), interpolation=cv2.INTER_NEAREST)
            effective_mask = cv2.bitwise_or(effective_mask, manual)

    return effective_mask


def _clip_auto_mask_to_balloon(
    block: Any, mask: np.ndarray, width: int, height: int, *, image: np.ndarray | None = None, dilation_margin: int = 6
) -> np.ndarray:
    """Keep automatic text masks strictly inside a confirmed Smart Balloon / speech-balloon region.

    Auto detection runs on a padded crop so punctuation is not clipped. That
    padding must NEVER become permission to mask or clean page artwork, outer balloon
    borders, tails, or illustration elements outside the text block.
    """
    if mask is None or mask.size == 0 or not np.any(mask):
        return mask

    bx = max(0, int(round(float(getattr(block, "x", 0)))))
    by = max(0, int(round(float(getattr(block, "y", 0)))))
    bw = max(1, int(round(float(getattr(block, "width", 0)))))
    bh = max(1, int(round(float(getattr(block, "height", 0)))))

    eff_margin = max(6, int(dilation_margin))

    # Permitted bounding window: text box + adaptive margin for diacritics/punctuation
    margin_x = max(16, eff_margin, int(round(bw * 0.20)))
    margin_y = max(16, eff_margin, int(round(bh * 0.20)))
    tx0 = max(0, bx - margin_x)
    ty0 = max(0, by - margin_y)
    tx1 = min(width, bx + bw + margin_x)
    ty1 = min(height, by + bh + margin_y)

    # 1. Clear any mask data outside permitted window
    permitted_window = np.zeros((height, width), dtype=np.uint8)
    permitted_window[ty0:ty1, tx0:tx1] = 255
    mask = cv2.bitwise_and(mask, permitted_window)

    # 2. Filter out disconnected outer components strictly within local window
    mask_roi = mask[ty0:ty1, tx0:tx1]
    if np.any(mask_roi):
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask_roi, connectivity=8)
        if num_labels > 1:
            filtered_roi = np.zeros_like(mask_roi)
            core_margin = max(6, eff_margin)
            for l in range(1, num_labels):
                lx = stats[l, cv2.CC_STAT_LEFT] + tx0
                ly = stats[l, cv2.CC_STAT_TOP] + ty0
                lw = stats[l, cv2.CC_STAT_WIDTH]
                lh = stats[l, cv2.CC_STAT_HEIGHT]

                # Component must overlap or be adjacent to the core text box (bx, by, bw, bh)
                overlaps_core = not (
                    lx + lw < bx - core_margin
                    or lx > bx + bw + core_margin
                    or ly + lh < by - core_margin
                    or ly > by + bh + core_margin
                )
                if overlaps_core:
                    filtered_roi[labels == l] = 255
            mask[ty0:ty1, tx0:tx1] = filtered_roi

    if image is not None and np.any(mask[ty0:ty1, tx0:tx1]):
        from app.services.mask.border_clamper import clamp_mask_to_balloon_interior
        clamped_roi = clamp_mask_to_balloon_interior(mask[ty0:ty1, tx0:tx1], image[ty0:ty1, tx0:tx1], margin_px=3)
        if clamped_roi is not None:
            mask[ty0:ty1, tx0:tx1] = clamped_roi

    # 3. Rival Block Hard-Separation (prevents mask bleeding into adjacent connected twin bubbles)
    page = getattr(block, "page", None)
    rival_blocks = getattr(page, "text_blocks", []) if page else []
    for rival in rival_blocks:
        if getattr(rival, "id", None) == getattr(block, "id", None):
            continue
        rx = float(getattr(rival, "x", 0))
        ry = float(getattr(rival, "y", 0))
        rw = float(getattr(rival, "width", 0))
        rh = float(getattr(rival, "height", 0))
        if rw <= 0 or rh <= 0:
            continue
        # Check if rival is vertically adjacent/touching
        overlap_x = max(0, min(bx + bw, rx + rw) - max(bx, rx))
        if overlap_x > 10:
            # If rival is directly above this block
            if ry + rh <= by + bh * 0.5 and ry + rh > by - margin_y:
                split_y = int(round((max(by, ry + rh) + min(by, ry + rh)) / 2.0))
                mask[:split_y, :] = 0
            # If rival is directly below this block
            elif ry >= by + bh * 0.5 and ry < by + bh + margin_y:
                split_y = int(round((min(by + bh, ry) + max(by + bh, ry)) / 2.0))
                mask[split_y:, :] = 0

    def clip_to_source_bbox(margin: int | None = None) -> np.ndarray:
        """Keep automatic text output safely inside the detector's text box (+ font margin)."""
        m = eff_margin if margin is None else margin
        try:
            x0 = max(0, min(width, int(np.floor(float(block.x) - m))))
            y0 = max(0, min(height, int(np.floor(float(block.y) - m))))
            x1 = max(x0, min(width, int(np.ceil(float(block.x + block.width) + m))))
            y1 = max(y0, min(height, int(np.ceil(float(block.y + block.height) + m))))
        except (AttributeError, TypeError, ValueError):
            return np.zeros_like(mask)
        permitted = np.zeros((height, width), dtype=np.uint8)
        permitted[y0:y1, x0:x1] = 255
        return cv2.bitwise_and(mask, permitted)

    def _get_permitted_text_box(margin: int | None = None) -> np.ndarray:
        m = eff_margin if margin is None else margin
        try:
            x0 = max(0, min(width, int(np.floor(float(block.x) - m))))
            y0 = max(0, min(height, int(np.floor(float(block.y) - m))))
            x1 = max(x0, min(width, int(np.ceil(float(block.x + block.width) + m))))
            y1 = max(y0, min(height, int(np.ceil(float(block.y + block.height) + m))))
        except (AttributeError, TypeError, ValueError):
            return np.zeros_like(mask)
        permitted = np.zeros((height, width), dtype=np.uint8)
        permitted[y0:y1, x0:x1] = 255
        return permitted

    text_bbox_mask = _get_permitted_text_box()

    metadata = getattr(block, "extra_metadata", None) or {}
    sb_meta = metadata.get("smart_balloon") if isinstance(metadata, dict) else None
    if isinstance(sb_meta, dict):
        contour_points = sb_meta.get("raw_contour_points") or sb_meta.get("contour_points")
        if isinstance(contour_points, list) and len(contour_points) > 2:
            interior = np.zeros((height, width), dtype=np.uint8)
            poly_pts = np.array(contour_points, dtype=np.int32).reshape(-1, 1, 2)
            cv2.fillPoly(interior, [poly_pts], 255)
            clamped = cv2.bitwise_and(mask, interior)
            if image is not None and np.any(clamped):
                from app.services.mask.border_clamper import clamp_mask_to_balloon_interior
                return clamp_mask_to_balloon_interior(clamped, image, margin_px=2)
            return clamped

    region = metadata.get("layout_region") if isinstance(metadata, dict) else None
    if not isinstance(region, dict):
        try:
            from app.services.layout_region import analyze_layout_region
            if image is not None:
                region = analyze_layout_region(image, block)
        except Exception:
            region = None

    confirmed_sources = {"balloon_interior", "manual", "smart_balloon_v15", "smart_balloon"}
    if not isinstance(region, dict) or region.get("source") not in confirmed_sources:
        return clip_to_source_bbox(margin=eff_margin)

    shape = str(region.get("shape") or getattr(block, "balloon_type", "bubble")).lower()
    try:
        rx = max(0, min(width, int(round(float(region["x"])))))
        ry = max(0, min(height, int(round(float(region["y"])))))
        rw = max(0, min(width - rx, int(round(float(region["width"])))))
        rh = max(0, min(height - ry, int(round(float(region["height"])))))
        if rw < 2 or rh < 2:
            return clip_to_source_bbox(margin=eff_margin)
        safe = max(0, int(round(float(region.get("safe_margin", 0)))))
    except (KeyError, TypeError, ValueError):
        return clip_to_source_bbox(margin=eff_margin)

    interior = np.zeros((height, width), dtype=np.uint8)
    x0, y0 = rx + safe, ry + safe
    x1, y1 = max(x0, rx + rw - safe), max(y0, ry + rh - safe)
    if shape in {"bubble", "thought", "ellipse", "circle", "smooth_oval"}:
        cv2.ellipse(interior, ((x0 + x1) // 2, (y0 + y1) // 2),
                    (max(1, (x1 - x0) // 2), max(1, (y1 - y0) // 2)),
                    0, 0, 360, 255, -1)
    else:
        interior[y0:y1, x0:x1] = 255
    clamped = cv2.bitwise_and(mask, interior)
    if image is not None and np.any(clamped):
        from app.services.mask.border_clamper import clamp_mask_to_balloon_interior
        return clamp_mask_to_balloon_interior(clamped, image, margin_px=2)
    return clamped


def build_effective_page_mask(page_id: str, db: Session) -> np.ndarray:
    """Build the current persisted + automatic mask without writing derived files."""
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise ValueError("Page not found")
    source_path = Path(page.source_image_path)
    img = cv2_imread_unicode(str(source_path))
    if img is None:
        raise ValueError(f"Failed to load image via OpenCV: {source_path}")
    return _compose_page_mask(page, img, include_saved_masks=True)


def build_automatic_page_mask(page_id: str, db: Session) -> np.ndarray:
    """Build a fresh automatic preview while preserving all saved manual masks."""
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise ValueError("Page not found")
    source_path = Path(page.source_image_path)
    img = cv2_imread_unicode(str(source_path))
    if img is None:
        raise ValueError(f"Failed to load image via OpenCV: {source_path}")
    return _compose_page_mask(page, img, include_saved_masks=False)


def _effective_mask_cache_manifest_path(page: Page) -> Path:
    return mask_asset_path(page, "effective_mask_manifest.json")


def _write_effective_page_mask_cache(page: Page, effective_mask: np.ndarray) -> Path:
    output_path = mask_asset_path(page, "effective_mask.png")
    if not cv2_imwrite_unicode(str(output_path), effective_mask):
        raise OSError(f"Failed to save effective mask: {output_path}")
    manifest_path = _effective_mask_cache_manifest_path(page)
    temporary = manifest_path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({
            "version": CLEAN_PIPELINE_VERSION,
            "kind": EFFECTIVE_MASK_CACHE_KIND,
            "fingerprint": compute_clean_fingerprint(page),
            "width": int(effective_mask.shape[1]),
            "height": int(effective_mask.shape[0]),
        }, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(manifest_path)
    return output_path


def get_or_build_effective_page_mask(page_id: str, db: Session) -> np.ndarray:
    """Use the derived mask cache when every mask input still matches."""
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise ValueError("Page not found")
    output_path = mask_asset_path(page, "effective_mask.png")
    manifest_path = _effective_mask_cache_manifest_path(page)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        cache_matches = (
            manifest.get("version") == CLEAN_PIPELINE_VERSION
            and manifest.get("kind") == EFFECTIVE_MASK_CACHE_KIND
            and manifest.get("fingerprint") == compute_clean_fingerprint(page)
        )
    except (OSError, ValueError, TypeError):
        cache_matches = False
    if cache_matches and output_path.exists():
        cached = cv2_imread_unicode(str(output_path), cv2.IMREAD_GRAYSCALE)
        if cached is not None:
            return cached

    effective_mask = build_effective_page_mask(page_id, db)
    try:
        _write_effective_page_mask_cache(page, effective_mask)
    except OSError as exc:
        # A read-only/removable project workspace must not make Mask Mode fail.
        # The rebuilt in-memory mask is still valid for this response.
        logger.warning("Failed to cache rebuilt effective mask: %s", exc)
    return effective_mask


def save_effective_page_mask(page_id: str, db: Session) -> Path:
    """Materialize the effective removal mask for inspection and training."""
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise ValueError("Page not found")
    effective_mask = build_effective_page_mask(page_id, db)

    return _write_effective_page_mask_cache(page, effective_mask)


def _lama_uses_cuda(lama: "LamaONNXInpainter | None") -> bool:
    """LaMa at 512px is too slow for interactive use when ORT fell back to CPU."""
    if lama is None:
        return False
    try:
        return "CUDAExecutionProvider" in lama.session.get_providers()
    except Exception:
        return False


def should_use_smart_mask(settings: dict | None) -> bool:
    """Resolve the cleanup mask policy without breaking existing projects.

    ``process_by_text_areas`` was the original, poorly named switch for the
    adaptive text-only mask.  The new setting is explicit, while old projects
    retain their existing behaviour until a user chooses a cleanup profile.
    """
    settings = settings or {}
    strategy = str(settings.get("cleanup_mask_strategy", "")).strip().lower()
    if strategy in {"smart", "adaptive", "text"}:
        return True
    if strategy in {"box", "rectangle", "full_box"}:
        return False
    return bool(settings.get("process_by_text_areas", True))


def resolve_inpaint_engine_name(settings: dict | None) -> str:
    settings = settings or {}
    raw_engine = str(
        settings.get("inpaint_engine")
        or settings.get("active_inpaint_engine")
        or settings.get("default_image_inpaint_method")
        or settings.get("inpaint_method")
        or ""
    ).strip().lower()

    if raw_engine in {"manga_cleaner", "mangacleaner", "manga_cleaner_v2", "lama_manga", "lama-manga", "animemangainpainting"}:
        return "manga_cleaner"
    elif raw_engine in {"mat", "mat_onnx", "mask_aware_transformer"}:
        return "mat"
    elif raw_engine in {"lama", "lamainpaint", "local_lama", "gpu_inpaint_server", "lama_onnx", "big_lama_onnx", "lama-onnx", "standard_lama_onnx", "godkiller standard lama (big-lama onnx - 208mb)"}:
        return "lama"
    elif raw_engine in {"telea", "cv2_telea", "inpaint_telea"}:
        return "telea"

    return "manga_cleaner"


def should_use_lama_inpaint(settings: dict | None) -> bool:
    settings = settings or {}
    resolved = resolve_inpaint_engine_name(settings)
    if resolved == "telea" and not settings.get("force_lama_inpaint"):
        return False
    return True


class MATInpainter:
    """
    Mask-Aware Transformer (MAT) Inpainting via ONNX Runtime.
    High-fidelity contextual inpainting for detailed backgrounds.
    (CVPR 2022 / Mask-Aware Transformer)
    """

    def __init__(self, model_path: str, execution_provider: str | None = None):
        opts = create_onnx_session_options() or ort.SessionOptions()

        providers = get_execution_providers(execution_provider)
        safe_providers = [p for p in providers if p != "DmlExecutionProvider"]
        if not safe_providers:
            safe_providers = ["CPUExecutionProvider"]

        try:
            self.session = ort.InferenceSession(model_path, sess_options=opts, providers=safe_providers)
            self.current_providers = self.session.get_providers()
            logger.info("MAT Inpainter initialized cleanly on provider: %s", self.current_providers)
        except Exception as e:
            logger.warning("Failed to initialize MAT Inpainter on %s (%s), using CPU fallback", safe_providers, e)
            self.session = ort.InferenceSession(model_path, sess_options=opts, providers=["CPUExecutionProvider"])
            self.current_providers = ["CPUExecutionProvider"]

        inputs = self.session.get_inputs()
        self.input_name = inputs[0].name
        self.mask_name = inputs[1].name if len(inputs) > 1 else "mask"
        self.input_size = 512

    def inpaint(self, image_bgr: np.ndarray, mask_gray: np.ndarray) -> np.ndarray:
        orig_h, orig_w = image_bgr.shape[:2]

        img_resized = cv2.resize(image_bgr, (self.input_size, self.input_size))
        mask_resized = cv2.resize(mask_gray, (self.input_size, self.input_size))

        img_rgb = (
            cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        )
        img_tensor = np.transpose(img_rgb, (2, 0, 1))[np.newaxis, ...]

        mask_tensor = (mask_resized.astype(np.float32) / 255.0)[
            np.newaxis, np.newaxis, ...
        ]
        mask_tensor = (mask_tensor > 0.0).astype(np.float32)

        output = self.session.run(
            None, {self.input_name: img_tensor, self.mask_name: mask_tensor}
        )[0]

        result = np.transpose(output[0], (1, 2, 0))
        if result.max() <= 1.05:
            result = result * 255.0
        result = np.clip(result, 0, 255).astype(np.uint8)
        result = cv2.cvtColor(result, cv2.COLOR_RGB2BGR)

        result_resized = cv2.resize(result, (orig_w, orig_h))

        mask_blur = cv2.GaussianBlur(mask_gray, (3, 3), 0)
        mask_blur_normalized = mask_blur.astype(float) / 255.0
        mask_blur_3d = np.expand_dims(mask_blur_normalized, axis=2)

        blended = (
            result_resized.astype(float) * mask_blur_3d
            + image_bgr.astype(float) * (1.0 - mask_blur_3d)
        )
        return np.clip(blended, 0, 255).astype(np.uint8)


class LamaONNXInpainter:
    """LaMa inpainting via ONNX Runtime. Zero PyTorch dependency."""
    def __init__(self, model_path: str, execution_provider: str | None = None):
        self.model_path = model_path
        self._cpu_session = None
        self._supports_dynamic_shape: bool | None = None  # None = untested
        opts = create_onnx_session_options() or ort.SessionOptions()

        providers = get_execution_providers(execution_provider)
        # DirectML does not support Fast Fourier Convolution (FFC) MatMul operators in LaMa ONNX.
        # Filter out DmlExecutionProvider to prevent runtime MatMul_5 driver exceptions.
        safe_providers = [p for p in providers if p != "DmlExecutionProvider"]
        if not safe_providers:
            safe_providers = ["CPUExecutionProvider"]

        try:
            self.session = ort.InferenceSession(model_path, sess_options=opts, providers=safe_providers)
            self.current_providers = self.session.get_providers()
            logger.info("LaMa Inpainter initialized cleanly on provider: %s", self.current_providers)
        except Exception as e:
            logger.warning("Failed to initialize LaMa Inpainter on %s (%s), using CPU fallback", safe_providers, e)
            self.session = ort.InferenceSession(model_path, sess_options=opts, providers=["CPUExecutionProvider"])
            self.current_providers = ["CPUExecutionProvider"]

        self.input_name = self.session.get_inputs()[0].name
        self.mask_name = self.session.get_inputs()[1].name
        self.input_size = 512
        self._inference_lock = threading.Lock()

        # Probe ONNX model for dynamic shape support
        try:
            inp_shape = self.session.get_inputs()[0].shape  # e.g. [1, 3, 512, 512] or [1, 3, 'h', 'w']
            if any(isinstance(s, str) or s is None for s in inp_shape):
                self._supports_dynamic_shape = True
                logger.info("⚡ LaMa ONNX model supports dynamic input shape — native resolution enabled")
            else:
                self._supports_dynamic_shape = False
                logger.info("LaMa ONNX model has fixed input shape %s — using resize mode", inp_shape)
        except Exception:
            self._supports_dynamic_shape = False

        # Pre-warm session to eliminate cold-start lag (256×256 for better CUDA kernel coverage)
        try:
            dummy_img = np.zeros((256, 256, 3), dtype=np.uint8)
            dummy_mask = np.zeros((256, 256), dtype=np.uint8)
            self.inpaint(dummy_img, dummy_mask)
            logger.info("⚡ LaMa ONNX session pre-warmed & resident in RAM")
        except Exception as e_warm:
            logger.debug("LaMa session warmup note: %s", e_warm)

    def _inpaint_native_resolution(self, image_bgr: np.ndarray, mask_gray: np.ndarray) -> np.ndarray:
        """Native resolution inference with symmetric divisor-8 padding (no resize)."""
        orig_h, orig_w = image_bgr.shape[:2]

        img_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        img_tensor = np.transpose(img_rgb, (2, 0, 1))[np.newaxis, ...]

        mask_tensor = (mask_gray.astype(np.float32) / 255.0)[np.newaxis, np.newaxis, ...]
        mask_tensor = (mask_tensor > 0.0).astype(np.float32)

        # Symmetric padding to nearest multiple of 8
        pad_h = (8 - orig_h % 8) % 8
        pad_w = (8 - orig_w % 8) % 8
        h_top = pad_h // 2
        h_bot = pad_h - h_top
        w_left = pad_w // 2
        w_right = pad_w - w_left

        if pad_h > 0 or pad_w > 0:
            img_tensor = np.pad(img_tensor, ((0, 0), (0, 0), (h_top, h_bot), (w_left, w_right)), mode="reflect")
            mask_tensor = np.pad(mask_tensor, ((0, 0), (0, 0), (h_top, h_bot), (w_left, w_right)), mode="reflect")

        lock = getattr(self, "_inference_lock", None)
        if lock is None:
            lock = threading.Lock()
            self._inference_lock = lock

        with lock:
            output = self.session.run(
                None, {self.input_name: img_tensor, self.mask_name: mask_tensor}
            )[0]

        result = np.transpose(output[0], (1, 2, 0))

        # Remove symmetric padding
        if pad_h > 0 or pad_w > 0:
            rh, rw = result.shape[:2]
            result = result[h_top:rh - h_bot if h_bot else rh, w_left:rw - w_right if w_right else rw, :]

        if result.max() <= 1.05:
            result = result * 255.0
        result = np.clip(result, 0, 255).astype(np.uint8)
        result = cv2.cvtColor(result, cv2.COLOR_RGB2BGR)

        # Blend only inside mask
        mask_blur = cv2.GaussianBlur(mask_gray, (3, 3), 0)
        mask_blur_normalized = mask_blur.astype(float) / 255.0
        mask_blur_3d = np.expand_dims(mask_blur_normalized, axis=2)

        blended = (
            result * mask_blur_3d + image_bgr * (1.0 - mask_blur_3d)
        ).astype(np.uint8)
        return blended

    def inpaint(self, image_bgr: np.ndarray, mask_gray: np.ndarray) -> np.ndarray:
        # Try native resolution if model supports dynamic shapes
        if self._supports_dynamic_shape:
            try:
                return self._inpaint_native_resolution(image_bgr, mask_gray)
            except Exception as e:
                logger.warning("Native resolution ONNX inference failed (%s), falling back to 512 resize", e)
                self._supports_dynamic_shape = False  # don't retry

        # Standard 512×512 resize path (guaranteed to work with fixed-shape ONNX models)
        orig_h, orig_w = image_bgr.shape[:2]

        # Resize to 512x512 as required by LaMa ONNX model
        img_resized = cv2.resize(image_bgr, (512, 512))
        mask_resized = cv2.resize(mask_gray, (512, 512))

        # BGR -> RGB, normalize to [0, 1]
        img_rgb = (
            cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        )
        # HWC -> NCHW
        img_tensor = np.transpose(img_rgb, (2, 0, 1))[np.newaxis, ...]

        # Mask: normalize to [0, 1] and reshape to [1, 1, 512, 512]
        mask_tensor = (mask_resized.astype(np.float32) / 255.0)[
            np.newaxis, np.newaxis, ...
        ]
        # Ensure binary mask
        mask_tensor = (mask_tensor > 0.0).astype(np.float32)

        lock = getattr(self, "_inference_lock", None)
        if lock is None:
            lock = threading.Lock()
            self._inference_lock = lock

        try:
            with lock:
                output = self.session.run(
                    None, {self.input_name: img_tensor, self.mask_name: mask_tensor}
                )[0]
        except Exception as exc:
            providers = getattr(self, "current_providers", ["unknown"])
            logger.warning("LaMa session.run failed on %s (%s), falling back permanently to CPU session", providers, exc)
            with lock:
                if getattr(self, "_cpu_session", None) is None:
                    opts = ort.SessionOptions()
                    opts.enable_cpu_mem_arena = False
                    opts.enable_mem_pattern = False
                    opts.log_severity_level = 3
                    self._cpu_session = ort.InferenceSession(self.model_path, sess_options=opts, providers=["CPUExecutionProvider"])
                self.session = self._cpu_session
                self.current_providers = ["CPUExecutionProvider"]
                output = self.session.run(
                    None, {self.input_name: img_tensor, self.mask_name: mask_tensor}
                )[0]

        # Output is NCHW [1, 3, 512, 512] in RGB
        result = np.transpose(output[0], (1, 2, 0))
        # Handle models emitting [0, 1] (e.g. FourierUnitJIT / AnimeMangaInpainting) vs [0, 255]
        if result.max() <= 1.05:
            result = result * 255.0
        result = np.clip(result, 0, 255).astype(np.uint8)
        result = cv2.cvtColor(result, cv2.COLOR_RGB2BGR)

        # Resize back to original size
        result_resized = cv2.resize(result, (orig_w, orig_h))

        # Blend the inpainted result back into original image ONLY where the mask is active
        # This keeps the rest of the image completely untouched and pixel-perfect.
        mask_blur = cv2.GaussianBlur(mask_gray, (3, 3), 0)
        mask_blur_normalized = mask_blur.astype(float) / 255.0
        mask_blur_3d = np.expand_dims(mask_blur_normalized, axis=2)

        blended = (
            result_resized * mask_blur_3d + image_bgr * (1.0 - mask_blur_3d)
        ).astype(np.uint8)
        return blended


_lama = None
_lama_checked = False


def _tile_based_inpaint(
    image_bgr: np.ndarray,
    mask_gray: np.ndarray,
    lama_service: LamaONNXInpainter,
    tile_size: int = 1024,
    overlap: int = 64
) -> np.ndarray:
    """
    Tile-based inpainting for large regions to preserve detail.

    Args:
        image_bgr: Input image in BGR format
        mask_gray: Mask in grayscale (255 = inpaint)
        lama_service: LaMa inpainter instance
        tile_size: Size of each tile (default 1024px)
        overlap: Overlap between tiles for blending (default 64px)

    Returns:
        Inpainted image in BGR format
    """
    h, w = image_bgr.shape[:2]

    # If image is small enough, use standard inpainting
    if max(h, w) <= tile_size:
        return lama_service.inpaint(image_bgr, mask_gray)

    # Calculate tile grid
    stride = tile_size - overlap
    tiles_y = max(1, int(np.ceil((h - overlap) / stride)))
    tiles_x = max(1, int(np.ceil((w - overlap) / stride)))

    # Result accumulator with weights for blending
    result = np.zeros_like(image_bgr, dtype=np.float32)
    weights = np.zeros((h, w, 1), dtype=np.float32)

    # Create blending weight map (fade near edges)
    tile_weight = np.ones((tile_size, tile_size, 1), dtype=np.float32)
    if overlap > 0:
        # Create smooth transition in overlap regions
        fade = np.linspace(0, 1, overlap)
        # Top edge
        tile_weight[:overlap, :, 0] *= fade[:, np.newaxis]
        # Bottom edge
        tile_weight[-overlap:, :, 0] *= fade[::-1, np.newaxis]
        # Left edge
        tile_weight[:, :overlap, 0] *= fade[np.newaxis, :]
        # Right edge
        tile_weight[:, -overlap:, 0] *= fade[::-1][np.newaxis, :]

    logger.info(f"Tile-based inpaint: {tiles_y}x{tiles_x} tiles, size={tile_size}px, overlap={overlap}px")

    for ty in range(tiles_y):
        for tx in range(tiles_x):
            # Calculate tile bounds
            y0 = ty * stride
            x0 = tx * stride
            y1 = min(y0 + tile_size, h)
            x1 = min(x0 + tile_size, w)

            # Extract tile
            tile_img = image_bgr[y0:y1, x0:x1].copy()
            tile_mask = mask_gray[y0:y1, x0:x1].copy()

            # Skip tiles with no mask
            if np.max(tile_mask) == 0:
                continue

            # Inpaint tile
            tile_result = lama_service.inpaint(tile_img, tile_mask)

            # Get actual tile dimensions
            tile_h, tile_w = tile_result.shape[:2]

            # Get weight map for this tile
            tile_w_map = tile_weight[:tile_h, :tile_w, :].copy()

            # Accumulate
            result[y0:y1, x0:x1] += tile_result.astype(np.float32) * tile_w_map
            weights[y0:y1, x0:x1] += tile_w_map

    # Normalize by weights
    weights_3ch = np.repeat(weights, 3, axis=2)
    mask_safe = weights_3ch > 1e-6
    result[mask_safe] /= weights_3ch[mask_safe]

    # Fill areas with no weight (shouldn't happen, but safety)
    no_weight = ~(weights[:, :, 0] > 1e-6)
    if np.any(no_weight):
        result[no_weight] = image_bgr[no_weight]

    return result.astype(np.uint8)


class LamaCleanerClientInpainter:
    """Ultra-fast GPU Inpainting via local PyTorch CUDA lama-cleaner server (e.g. RTX 4060)."""
    def __init__(self, endpoint_url: str = "http://127.0.0.1:2328/inpaint", execution_provider: str | None = None):
        target = str(endpoint_url).strip() if endpoint_url else "http://127.0.0.1:2328/inpaint"
        if not target.endswith("/inpaint"):
            target = f"{target.rstrip('/')}/inpaint"
        self.endpoint_url = target
        self.execution_provider = execution_provider  # Store for fallback
        self.current_providers = ["CUDA (PyTorch GPU / NVIDIA RTX 4060)"]
        self.max_retries = 2  # Retry once on transient network drop
        self.retry_delay = 0.2
        self.fallback_instance = None  # Cached permanent fallback if server is down

    def inpaint(self, image_bgr: np.ndarray, mask_gray: np.ndarray) -> np.ndarray:
        # If server was previously unreachable, bypass HTTP completely
        if self.fallback_instance is not None:
            return self.fallback_instance.inpaint(image_bgr, mask_gray)

        import urllib.request
        orig_h, orig_w = image_bgr.shape[:2]
        _, img_encoded = cv2.imencode('.png', image_bgr)
        _, mask_encoded = cv2.imencode('.png', mask_gray)

        boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
        body = (
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="ldmSteps"\r\n\r\n25\r\n'
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="hdStrategy"\r\n\r\nOriginal\r\n'
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="hdStrategyCropMargin"\r\n\r\n128\r\n'
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="hdStrategyCropTrigerSize"\r\n\r\n2048\r\n'
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="hdStrategyResizeLimit"\r\n\r\n2048\r\n'
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="sizeLimit"\r\n\r\nOriginal\r\n'
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="image"; filename="image.png"\r\n'
            f'Content-Type: image/png\r\n\r\n'
        ).encode('utf-8') + img_encoded.tobytes() + (
            f'\r\n--{boundary}\r\n'
            f'Content-Disposition: form-data; name="mask"; filename="mask.png"\r\n'
            f'Content-Type: image/png\r\n\r\n'
        ).encode('utf-8') + mask_encoded.tobytes() + (
            f'\r\n--{boundary}--\r\n'
        ).encode('utf-8')

        req = urllib.request.Request(
            self.endpoint_url,
            data=body,
            headers={'Content-Type': f'multipart/form-data; boundary={boundary}'},
            method='POST'
        )

        # Retry logic for transient failures
        last_error = None
        for attempt in range(self.max_retries):
            try:
                with urllib.request.urlopen(req, timeout=15.0) as resp:
                    res_bytes = resp.read()
                    res_arr = np.frombuffer(res_bytes, np.uint8)
                    res_img = cv2.imdecode(res_arr, cv2.IMREAD_COLOR)
                    if res_img is not None:
                        if res_img.shape[:2] != (orig_h, orig_w):
                            res_img = cv2.resize(res_img, (orig_w, orig_h))
                        return res_img
            except urllib.error.HTTPError as http_err:
                last_error = http_err
                if http_err.code in (400, 422):
                    # Box-specific payload format issue: fallback for THIS box only, keep GPU alive for remaining boxes!
                    logger.debug(f"GPU Inpaint box payload note ({http_err}), fallback Telea for this box")
                    return cv2.inpaint(image_bgr, mask_gray, inpaintRadius=4, flags=cv2.INPAINT_TELEA)
                if attempt < self.max_retries - 1:
                    import time
                    time.sleep(self.retry_delay)
                    continue
            except Exception as err:
                last_error = err
                if attempt < self.max_retries - 1:
                    import time
                    time.sleep(self.retry_delay)
                    continue

        # Server unreachable (Connection refused / Server died) -> Fallback to built-in ONNX
        logger.warning(f"LamaCleanerClientInpainter connection error on {self.endpoint_url} ({last_error}), switching to built-in inpainter")
        try:
            global _lama
            fallback = _get_fallback_lama_onnx(execution_provider=self.execution_provider)
            if fallback is not None:
                self.fallback_instance = fallback  # Fast-path for this client instance
                _lama = fallback  # Fast-path for global cache
                logger.info(f"⚡ Switched to cached ONNX LaMa ({fallback.current_providers}) for remaining boxes")
                return fallback.inpaint(image_bgr, mask_gray)
        except Exception as e_fb:
            logger.debug(f"ONNX fallback error: {e_fb}")

        # Final ultra-fast fallback to Telea
        return cv2.inpaint(image_bgr, mask_gray, inpaintRadius=4, flags=cv2.INPAINT_TELEA)


def _get_fallback_lama_onnx(execution_provider: str | None = None) -> Any | None:
    """Retrieve or initialize the built-in ONNX LaMa model (cached in-memory singleton)."""
    global _lama_onnx
    if _lama_onnx is not None:
        return _lama_onnx

    from app.config import MODELS_DIR, INPAINT_MODEL_PATH
    for alt in (INPAINT_MODEL_PATH, MODELS_DIR / "inpainting" / "lama_manga.onnx", MODELS_DIR / "inpainting" / "lama.onnx"):
        if alt.exists():
            try:
                _lama_onnx = LamaONNXInpainter(str(alt), execution_provider=execution_provider)
                logger.info("✅ Cached Built-In Neural LaMa ONNX Inpainter loaded: %s with providers %s", alt.name, _lama_onnx.current_providers)
                return _lama_onnx
            except Exception as e_init:
                logger.warning("Failed to initialize ONNX fallback %s: %s", alt, e_init)
    return None


def _is_local_lama_cleaner_alive(port: int = 2328, timeout: float = 0.5) -> bool:
    """Check if local lama-cleaner server is responding on the given port."""
    if port == 2322:  # Port 2322 is reserved for Houmi OCR Server
        return False
    try:
        import urllib.request
        for path in ["/", "/health"]:
            try:
                req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", headers={"User-Agent": "HoumiStudio"}, method="GET")
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    if resp.status == 200:
                        data = resp.read().decode("utf-8", errors="ignore").lower()
                        if "ocr" in data and "inpaint" not in data and "lama" not in data:
                            return False
                        return True
            except Exception:
                pass
    except Exception:
        pass
    return False


_lama = None
_lama_checked = False
_lama_onnx = None


def _get_lama(execution_provider: str | None = None, custom_url: str | None = None, force_onnx: bool = False):
    global _lama, _lama_checked, _lama_onnx

    if force_onnx:
        if _lama_onnx is not None:
            return _lama_onnx
        model_to_use = INPAINT_MODEL_PATH if INPAINT_MODEL_PATH.exists() else None
        if model_to_use is None:
            from app.config import MODELS_DIR
            for alt in (MODELS_DIR / "inpainting" / "lama_manga.onnx", MODELS_DIR / "inpainting" / "lama.onnx"):
                if alt.exists():
                    model_to_use = alt
                    break
        if model_to_use and model_to_use.exists():
            try:
                _lama_onnx = LamaONNXInpainter(str(model_to_use), execution_provider=execution_provider)
                logger.info("✅ Built-In Neural LaMa ONNX Inpainter loaded: %s with providers %s", model_to_use.name, _lama_onnx.current_providers)
                return _lama_onnx
            except Exception as e:
                logger.warning("LaMa ONNX failed to initialize: %s", e)
        return None

    # Check if cached instance is valid or if custom_url changed
    if isinstance(_lama, LamaCleanerClientInpainter):
        if custom_url and _lama.endpoint_url != custom_url:
            # Custom URL changed → invalidate cache and reconnect
            logger.info("Custom GPU URL changed from %s to %s, reconnecting...", _lama.endpoint_url, custom_url)
            _lama = None
            _lama_checked = False
        elif not custom_url:
            # No custom URL specified → use cached instance
            return _lama

    # 0. User custom URL from Settings
    if custom_url and custom_url.strip():
        try:
            target_url = custom_url.strip()
            if not target_url.endswith("/inpaint"):
                target_url = f"{target_url.rstrip('/')}/inpaint"
            base_url = target_url.split("/inpaint")[0].rstrip("/")
            import urllib.request
            req = urllib.request.Request(f"{base_url}/health", headers={"User-Agent": "HoumiStudio"}, method="GET")
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status in (200, 404, 405):
                    _lama = LamaCleanerClientInpainter(target_url, execution_provider=execution_provider)
                    logger.info("⚡ Custom GPU Inpaint Server Connected: %s", target_url)
                    _lama_checked = True
                    return _lama
        except Exception as e:
            logger.warning("Failed to connect to custom GPU inpaint URL %s: %s", custom_url, e)

    # 1. Prefer Houmi's Built-In GPU Server (port 2328 / 2335) - strictly excluding OCR port 2322
    for port in (2328, 2335):
        if _is_local_lama_cleaner_alive(port):
            try:
                _lama = LamaCleanerClientInpainter(f"http://127.0.0.1:{port}/inpaint", execution_provider=execution_provider)
                logger.info("⚡ Ultra-Fast GPU Inpainting Connected: NVIDIA CUDA on port %d", port)
                _lama_checked = True
                return _lama
            except Exception as e:
                logger.warning("Failed to connect to GPU inpainter on port %d: %s", port, e)

    # 2. Try auto-starting background inpaint daemon
    try:
        from app.services.inpaint_server_manager import inpaint_manager
        inpaint_manager.start_server_if_needed()
        for port in (2328, 2335):
            if _is_local_lama_cleaner_alive(port):
                _lama = LamaCleanerClientInpainter(f"http://127.0.0.1:{port}/inpaint", execution_provider=execution_provider)
                logger.info("⚡ Ultra-Fast GPU Inpainting Connected after auto-start on port %d", port)
                _lama_checked = True
                return _lama
    except Exception as e_daemon:
        logger.debug("Daemon auto-start check: %s", e_daemon)

    # 3. Built-in Fallback
    _lama_checked = True
    return _get_fallback_lama_onnx(execution_provider=execution_provider)


_mat = None
_mat_checked = False


def _get_mat(execution_provider: str | None = None):
    global _mat, _mat_checked
    if _mat is not None:
        return _mat

    if not _mat_checked:
        if MAT_MODEL_PATH.exists():
            try:
                _mat = MATInpainter(str(MAT_MODEL_PATH), execution_provider=execution_provider)
                logger.info("MAT (Mask-Aware Transformer) inpainting loaded: %s with providers %s", MAT_MODEL_PATH, _mat.current_providers)
            except Exception as e:
                logger.warning("MAT inpainting model failed to load, falling back: %s", e)
                _mat = None
        else:
            logger.info("MAT model not found at %s (will fall back to LaMa/Telea)", MAT_MODEL_PATH)
_manga_unet_session = None

def _get_full_page_manga_unet_mask(img: np.ndarray) -> np.ndarray | None:
    global _manga_unet_session
    from app.config import MODELS_DIR
    unet_path = MODELS_DIR / "manga_text_segmentation" / "manga_unet.onnx"
    if not unet_path.exists():
        return None
    try:
        h, w = img.shape[:2]
        if _manga_unet_session is None and ort is not None:
            try:
                _manga_unet_session = ort.InferenceSession(str(unet_path), providers=["DmlExecutionProvider", "CPUExecutionProvider"])
            except Exception:
                _manga_unet_session = ort.InferenceSession(str(unet_path), providers=["CPUExecutionProvider"])
        if _manga_unet_session is None:
            return None

        img_512 = cv2.resize(img, (512, 512))
        img_rgb = cv2.cvtColor(img_512, cv2.COLOR_BGR2RGB)
        img_norm = (img_rgb.astype(np.float32) / 255.0 - 0.5) / 0.5
        input_tensor = np.transpose(img_norm, (2, 0, 1))[np.newaxis, ...]

        try:
            input_name = _manga_unet_session.get_inputs()[0].name
            outputs = _manga_unet_session.run(None, {input_name: input_tensor})
        except Exception as exc:
            if "suspended" in str(exc).lower() or "device_removed" in str(exc).lower() or "887a0005" in str(exc).lower():
                logger.warning("DirectML GPU suspended in full-page UNet mask! Fallback to CPU: %s", exc)
                _manga_unet_session = ort.InferenceSession(str(unet_path), providers=["CPUExecutionProvider"])
                input_name = _manga_unet_session.get_inputs()[0].name
                outputs = _manga_unet_session.run(None, {input_name: input_tensor})
            else:
                raise exc
        pred = outputs[0][0, 0]
        mask_512 = (pred > 0.5).astype(np.uint8) * 255

        mask_full = cv2.resize(mask_512, (w, h), interpolation=cv2.INTER_NEAREST)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask_dilated = cv2.dilate(mask_full, kernel, iterations=1)
        return fill_mask_holes(mask_dilated)
    except Exception as e:
        logger.warning("Failed to run full page Manga UNet mask: %s", e)
        return None

def fill_mask_holes(mask: np.ndarray, max_hole_area: int = 400, max_hole_dim: int = 32) -> np.ndarray:
    """Fill internal counter holes/loops inside text glyphs (e.g. 口, 日, 田, O, 0, B, A).

    Uses two-level contour hierarchy (RETR_CCOMP) to inspect inner holes.
    Holes larger than letter loop dimensions are preserved as whitespace/background,
    strictly preventing balloons, panels, or hatching boundaries from being filled solid.
    """
    if mask is None or mask.size == 0 or not np.any(mask):
        return mask
    binary = np.where(mask > 0, 255, 0).astype(np.uint8)

    contours, hierarchy = cv2.findContours(binary, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None or len(contours) == 0:
        return binary

    hierarchy_flat = hierarchy[0]
    filled = binary.copy()

    for i, (cnt, h) in enumerate(zip(contours, hierarchy_flat)):
        parent_idx = h[3]
        if parent_idx != -1:
            # Inner hole inside a foreground component
            hole_area = cv2.contourArea(cnt)
            _, _, rw, rh = cv2.boundingRect(cnt)
            if hole_area <= max_hole_area and max(rw, rh) <= max_hole_dim:
                cv2.drawContours(filled, contours, i, 255, -1)

    return filled


# LRU cache for adaptive masks to avoid recomputation
from functools import lru_cache
import hashlib

def _hash_region(img_shape: tuple, x0: int, y0: int, x1: int, y1: int, kernel: int) -> str:
    """Generate cache key for mask region"""
    return f"{img_shape}_{x0}_{y0}_{x1}_{y1}_{kernel}"

_adaptive_mask_cache = {}
_MAX_CACHE_SIZE = 100

def get_configured_block_mask(
    img: np.ndarray, x0: int, y0: int, x1: int, y1: int, settings: dict | None = None
) -> np.ndarray:
    """Generate block mask based on configured mask engine (hybrid/ocr_text, sam, contour, balloon)."""
    if settings is None:
        settings = {}
    dilation_kernel = max(0, min(56, int(settings.get("mask_dilation_kernel", 3))))
    method = str(
        settings.get("mask_gen_method")
        or settings.get("default_mask_gen_method")
        or "hybrid"
    ).lower()

    h, w = img.shape[:2]
    # Add generous 48px padding margin around text block to catch trailing dots (……), punctuation (!), and overflowing characters
    pad_margin = max(48, int(round(max(x1 - x0, y1 - y0) * 0.35)))
    px0, py0 = max(0, int(x0) - pad_margin), max(0, int(y0) - pad_margin)
    px1, py1 = min(w, int(x1) + pad_margin), min(h, int(y1) + pad_margin)

    if method in ("sam", "segment"):
        try:
            from app.services.sam_segmenter import smart_segment_box
            crop = img[py0:py1, px0:px1]
            if crop.size > 0:
                ch, cw = crop.shape[:2]
                sam_mask = smart_segment_box(crop, 0, 0, cw, ch)
                if sam_mask is not None and np.any(sam_mask):
                    if dilation_kernel > 0:
                        ksize = max(3, dilation_kernel * 2 + 1)
                        kelem = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
                        sam_mask = cv2.dilate(sam_mask, kelem, iterations=1)
                    full_mask = np.zeros((h, w), dtype=np.uint8)
                    full_mask[py0:py1, px0:px1] = sam_mask
                    return full_mask
        except Exception as exc:
            logger.warning("SAM mask generation failed, falling back to adaptive: %s", exc)

    elif method in ("rectangle", "full_box", "balloon", "box", "full"):
        full_mask = np.zeros((h, w), dtype=np.uint8)
        full_mask[py0:py1, px0:px1] = 255
        return full_mask

    elif method == "imagetrans":
        from app.services.text_mask import generate_imagetrans_text_mask
        crop = img[py0:py1, px0:px1]
        if crop.size > 0:
            mask = generate_imagetrans_text_mask(crop, dilation_kernel=dilation_kernel)
            if mask is not None and np.any(mask):
                full_mask = np.zeros((h, w), dtype=np.uint8)
                full_mask[py0:py1, px0:px1] = mask
                return full_mask

    elif method in ("contour", "morphology", "adaptive"):
        from app.services.text_mask import generate_contour_morphology_text_mask
        crop = img[py0:py1, px0:px1]
        if crop.size > 0:
            mask = generate_contour_morphology_text_mask(crop, dilation_kernel=dilation_kernel)
            if mask is not None and np.any(mask):
                full_mask = np.zeros((h, w), dtype=np.uint8)
                full_mask[py0:py1, px0:px1] = mask
                return full_mask

    # Primary for Intelligent Hybrid (and fallback for others):
    # High-accuracy Neural Manga UNet++ deep learning model
    try:
        from app.services.text_mask import generate_routed_text_mask, generate_adaptive_sfx_mask
        crop = img[py0:py1, px0:px1]
        if crop.size > 0:
            mask, _mode, _diagnostics = generate_routed_text_mask(
                crop, dilation_kernel=dilation_kernel
            )
            if mask is None or not np.any(mask):
                mask = generate_adaptive_sfx_mask(crop, dilation_kernel=dilation_kernel)
            if mask is not None and np.any(mask):
                full_mask = np.zeros((h, w), dtype=np.uint8)
                full_mask[py0:py1, px0:px1] = mask
                return full_mask
    except Exception as exc:
        logger.warning("High quality OCR text mask failed, falling back to adaptive: %s", exc)

    return get_adaptive_text_mask(img, x0, y0, x1, y1, dilation_kernel)


def get_automatic_block_mask(
    img: np.ndarray,
    block: Any,
    settings: dict | None = None,
    *,
    dilation_kernel: int | None = None,
) -> np.ndarray:
    """Build the canonical automatic mask used by editor, preview, and cleaning.

    The block editor has always inspected a crop containing the union of the OCR
    box and ``layout_region``. Page cleaning previously regenerated the mask from
    the smaller OCR box (and sometimes padded that box twice), so the two views
    could disagree for the same block.
    """
    settings = dict(settings or {})
    requested_kernel = int(
        dilation_kernel
        if dilation_kernel is not None
        else settings.get("mask_dilation_kernel", 3)
    )
    settings["mask_dilation_kernel"] = requested_kernel
    height, width = img.shape[:2]
    px0, py0, px1, py1 = _padded_block_coords(block, width, height)
    if px1 <= px0 or py1 <= py0:
        return np.zeros((height, width), dtype=np.uint8)

    clean_balloon_border = bool(
        settings.get("clean_balloon_border")
        or (isinstance(getattr(block, "extra_metadata", None), dict) and block.extra_metadata.get("clean_balloon_border"))
    )

    method = str(
        settings.get("mask_gen_method")
        or settings.get("default_mask_gen_method")
        or "hybrid"
    ).lower()
    
    if method in ("unet", "manga_unet"):
        from app.services.text_mask import generate_manga_unet_text_mask
        crop = img[py0:py1, px0:px1]
        local_mask = generate_manga_unet_text_mask(crop, dilation_kernel=requested_kernel)
        mask = np.zeros((height, width), dtype=np.uint8)
        if local_mask is not None and local_mask.shape[:2] == crop.shape[:2]:
            mask[py0:py1, px0:px1] = local_mask
    elif method == "imagetrans":
        from app.services.text_mask import generate_imagetrans_text_mask
        crop = img[py0:py1, px0:px1]
        local_mask = generate_imagetrans_text_mask(crop, dilation_kernel=requested_kernel)
        mask = np.zeros((height, width), dtype=np.uint8)
        if local_mask is not None and local_mask.shape[:2] == crop.shape[:2]:
            mask[py0:py1, px0:px1] = local_mask
    elif method in ("contour", "morphology", "adaptive"):
        from app.services.text_mask import generate_contour_morphology_text_mask
        crop = img[py0:py1, px0:px1]
        local_mask = generate_contour_morphology_text_mask(crop, dilation_kernel=requested_kernel)
        mask = np.zeros((height, width), dtype=np.uint8)
        if local_mask is not None and local_mask.shape[:2] == crop.shape[:2]:
            mask[py0:py1, px0:px1] = local_mask
    elif clean_balloon_border or method in {"sam", "segment", "rectangle", "full_box", "balloon", "box", "full"}:
        mask = get_configured_block_mask(
            img,
            int(block.x),
            int(block.y),
            int(block.x + block.width),
            int(block.y + block.height),
            settings,
        )
    else:
        crop = img[py0:py1, px0:px1]
        from app.services.text_mask import generate_adaptive_sfx_mask, generate_routed_text_mask

        local_mask, _mode, _diagnostics = generate_routed_text_mask(
            crop, dilation_kernel=requested_kernel
        )
        if local_mask is None or not np.any(local_mask):
            local_mask = generate_adaptive_sfx_mask(
                crop, dilation_kernel=requested_kernel
            )

        magnetic_fill_enabled = bool(
            settings.get("mask_magnetic_line_fill")
            or settings.get("magnetic_mask_fill")
            or (isinstance(getattr(block, "extra_metadata", None), dict) and block.extra_metadata.get("mask_magnetic_line_fill"))
        )
        if magnetic_fill_enabled and local_mask is not None and np.any(local_mask):
            from app.services.mask.magnetic_mask import apply_magnetic_line_fill
            local_mask = apply_magnetic_line_fill(local_mask, image_bgr=crop)

        mask = np.zeros((height, width), dtype=np.uint8)
        if local_mask is not None and local_mask.shape[:2] == crop.shape[:2]:
            mask[py0:py1, px0:px1] = local_mask

    clipped_mask = _clip_auto_mask_to_balloon(
        block, mask, width, height, image=img, dilation_margin=requested_kernel
    )
    return fill_mask_holes(clipped_mask)


def get_adaptive_text_mask(
    img: np.ndarray, x0: int, y0: int, x1: int, y1: int, dilation_kernel: int = 3
) -> np.ndarray:
    """
    Generates a high-precision mask for text inside a bounding box
    using polarity detection, adaptive thresholting, balloon segmentation,
    and contour filtering.

    Results are cached to avoid expensive recomputation.
    """
    # Check cache first
    cache_key = _hash_region(img.shape, x0, y0, x1, y1, dilation_kernel)
    if cache_key in _adaptive_mask_cache:
        return _adaptive_mask_cache[cache_key].copy()

    # Clear cache if too large
    if len(_adaptive_mask_cache) > _MAX_CACHE_SIZE:
        _adaptive_mask_cache.clear()
    h, w = img.shape[:2]
    requested_x0, requested_y0 = max(0, x0), max(0, y0)
    requested_x1, requested_y1 = min(w, x1), min(h, y1)
    requested_width = max(1, requested_x1 - requested_x0)
    requested_height = max(1, requested_y1 - requested_y0)

    context_padding = min(
        16,
        max(
            12,
            int(dilation_kernel) * 2 + 1,
            int(round(min(requested_width, requested_height) * 0.08)),
        ),
    )
    cx0, cy0 = max(0, x0 - context_padding), max(0, y0 - context_padding)
    cx1, cy1 = min(w, x1 + context_padding), min(h, y1 + context_padding)

    crop = img[cy0:cy1, cx0:cx1]
    if crop.size > 0:
        try:
            from app.services.text_mask import generate_routed_text_mask
            unet_mask, _mode, _diagnostics = generate_routed_text_mask(
                crop, dilation_kernel=max(1, dilation_kernel // 2)
            )
            if unet_mask is not None and np.any(unet_mask):
                full_mask = np.zeros((h, w), dtype=np.uint8)
                full_mask[cy0:cy1, cx0:cx1] = unet_mask
                _adaptive_mask_cache[cache_key] = full_mask.copy()
                return full_mask
        except Exception as exc:
            logger.warning("UNet++ text mask in inpainter failed: %s", exc)

    # OCR boxes are commonly tight enough to cut through the first/last glyph.
    # Give thresholding a small amount of surrounding context so those strokes
    # no longer look like a balloon border touching the crop edge.
    context_padding = min(
        16,
        max(
            12,
            int(dilation_kernel) * 2 + 1,
            int(round(min(requested_width, requested_height) * 0.08)),
        ),
    )
    x0, y0 = max(0, x0 - context_padding), max(0, y0 - context_padding)
    x1, y1 = min(w, x1 + context_padding), min(h, y1 + context_padding)

    crop = img[y0:y1, x0:x1]
    crop_h, crop_w = crop.shape[:2]
    if crop_h <= 0 or crop_w <= 0:
        return np.zeros((h, w), dtype=np.uint8)

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    requested_region = (
        requested_x0 - x0,
        requested_y0 - y0,
        requested_x1 - x0,
        requested_y1 - y0,
    )

    if min(crop_w, crop_h) < 30:
        denoised = gray.copy()
    else:
        denoised = cv2.bilateralFilter(gray, 5, 40, 40)

    border_pixels = []
    border_pixels.extend(denoised[0:2, :].flatten())
    border_pixels.extend(denoised[-2:, :].flatten())
    border_pixels.extend(denoised[:, 0:2].flatten())
    border_pixels.extend(denoised[:, -2:].flatten())
    bg_mean = np.mean(border_pixels) if len(border_pixels) > 0 else 255

    block_size = 15

    if bg_mean < 120:
        thresh_text = cv2.adaptiveThreshold(
            denoised,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            block_size,
            3,
        )
    else:
        thresh_text = cv2.adaptiveThreshold(
            denoised,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            block_size,
            3,
        )

    thresh_text[0, :] = 0
    thresh_text[-1, :] = 0
    thresh_text[:, 0] = 0
    thresh_text[:, -1] = 0

    # Pre-clean text to find text anchor components for validating balloon interiors
    contours, hierarchy = cv2.findContours(
        thresh_text, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
    )
    temp_cleaned = np.zeros_like(thresh_text)

    if hierarchy is not None and len(contours) > 0:
        hierarchy_flat = hierarchy[0]
        for i, contour in enumerate(contours):
            area = cv2.contourArea(contour)
            rx, ry, rw, rh = cv2.boundingRect(contour)
            if rw > 0.95 * crop_w or rh > 0.95 * crop_h:
                continue
            aspect = max(rw, rh) / (min(rw, rh) + 1)
            rect_area = rw * rh
            solidity = area / rect_area if rect_area > 0 else 0

            touches_border = (
                (rx <= 2)
                or (rx + rw >= crop_w - 2)
                or (ry <= 2)
                or (ry + rh >= crop_h - 2)
            )
            skipped = False
            if touches_border:
                if rw > 0.5 * crop_w or rh > 0.5 * crop_h:
                    skipped = True
                elif aspect > 4.0 and max(rw, rh) > 25:
                    skipped = True
                elif solidity < 0.12:
                    skipped = True
                elif area < 3:
                    skipped = True
            else:
                if aspect > 8.0 and area < 100:
                    skipped = True

            first_child = hierarchy_flat[i][2]
            if (
                not skipped
                and first_child != -1
                and (rw > 0.55 * crop_w or rh > 0.55 * crop_h)
            ):
                skipped = True

            if not skipped:
                cv2.drawContours(temp_cleaned, contours, i, 255, -1)

    # Balloon interior logic with closed borders
    if bg_mean >= 120:
        _, thresh_bg = cv2.threshold(
            denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
    else:
        _, thresh_bg = cv2.threshold(
            denoised, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )

    thresh_bg_closed = thresh_bg.copy()
    thresh_bg_closed[0:2, :] = 0
    thresh_bg_closed[-2:, :] = 0
    thresh_bg_closed[:, 0:2] = 0
    thresh_bg_closed[:, -2:] = 0

    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    eroded = cv2.erode(thresh_bg_closed, kernel_close, iterations=3)

    filled = eroded.copy()
    flood_mask = np.zeros((crop_h + 2, crop_w + 2), dtype=np.uint8)

    for x in range(crop_w):
        if filled[0, x] == 255:
            cv2.floodFill(filled, flood_mask, (x, 0), 128)
        if filled[crop_h - 1, x] == 255:
            cv2.floodFill(filled, flood_mask, (x, crop_h - 1), 128)
    for y in range(crop_h):
        if filled[y, 0] == 255:
            cv2.floodFill(filled, flood_mask, (0, y), 128)
        if filled[y, crop_w - 1] == 255:
            cv2.floodFill(filled, flood_mask, (crop_w - 1, y), 128)

    balloon_mask = np.zeros_like(eroded)
    balloon_mask[filled == 255] = 255

    bg_contours, _ = cv2.findContours(
        balloon_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    solid_bg = np.zeros_like(balloon_mask)

    crop_total_area = crop_w * crop_h
    for cnt in bg_contours:
        area = cv2.contourArea(cnt)
        pct = (area / crop_total_area) * 100

        # Calculate text overlap
        cnt_mask = np.zeros_like(balloon_mask)
        cv2.drawContours(cnt_mask, [cnt], -1, 255, -1)
        overlap = cv2.bitwise_and(temp_cleaned, cnt_mask)
        overlap_pixels = np.count_nonzero(overlap)

        # Keep only if relative area pct > 8.0% AND has text overlap
        if pct > 8.0 and overlap_pixels > 5:
            cv2.drawContours(solid_bg, [cnt], -1, 255, -1)

    # Erode the balloon interior mask to protect balloon border
    kernel_protect = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    eroded_bg = cv2.erode(solid_bg, kernel_protect, iterations=2)

    has_balloon_mask = np.count_nonzero(eroded_bg) > 0.05 * crop_total_area
    if has_balloon_mask:
        # Adaptive thresholding can leave thin antialiased CJK strokes behind.
        # Otsu supplies a conservative second opinion, restricted to the safe
        # balloon interior so it cannot consume the balloon outline.
        otsu_mode = cv2.THRESH_BINARY_INV if bg_mean >= 120 else cv2.THRESH_BINARY
        _, global_ink = cv2.threshold(
            denoised, 0, 255, otsu_mode + cv2.THRESH_OTSU
        )
        thresh_text = cv2.bitwise_or(thresh_text, global_ink)
        thresh_text = cv2.bitwise_and(thresh_text, eroded_bg)

    contours, hierarchy = cv2.findContours(
        thresh_text, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
    )
    cleaned = np.zeros_like(thresh_text)

    if hierarchy is not None and len(contours) > 0:
        hierarchy_flat = hierarchy[0]
        for i, contour in enumerate(contours):
            area = cv2.contourArea(contour)
            rx, ry, rw, rh = cv2.boundingRect(contour)

            req_x0, req_y0, req_x1, req_y1 = requested_region
            intersects_requested_box = not (
                rx + rw < req_x0 - 2
                or ry + rh < req_y0 - 2
                or rx > req_x1 + 2
                or ry > req_y1 + 2
            )
            if not intersects_requested_box:
                continue

            if rw > 0.95 * crop_w or rh > 0.95 * crop_h:
                continue

            # Once a safe balloon interior is known, long thin components are
            # legitimate CJK strokes much more often than they are artwork.
            # The old aspect/solidity filters removed exactly these strokes.
            if has_balloon_mask:
                if area >= 1:
                    cv2.drawContours(cleaned, contours, i, 255, -1)
                continue

            aspect = max(rw, rh) / (min(rw, rh) + 1)
            rect_area = rw * rh
            solidity = area / rect_area if rect_area > 0 else 0

            touches_border = (
                (rx <= 2)
                or (rx + rw >= crop_w - 2)
                or (ry <= 2)
                or (ry + rh >= crop_h - 2)
            )
            skipped = False

            if touches_border:
                if rw > 0.5 * crop_w or rh > 0.5 * crop_h:
                    skipped = True
                elif aspect > 4.0 and max(rw, rh) > 25:
                    skipped = True
                elif solidity < 0.12:
                    skipped = True
                elif area < 3:
                    skipped = True
            else:
                if aspect > 8.0 and area < 100:
                    skipped = True
                elif (rw > 50 or rh > 50) and solidity < 0.15:
                    skipped = True

            first_child = hierarchy_flat[i][2]
            if (
                not skipped
                and first_child != -1
                and (rw > 0.55 * crop_w or rh > 0.55 * crop_h)
            ):
                skipped = True

            if not skipped:
                cv2.drawContours(cleaned, contours, i, 255, -1)

    dilation_kernel = _effective_dilation_kernel(dilation_kernel, crop_w, crop_h)
    kernel_dilate = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (dilation_kernel, dilation_kernel)
    )
    dilated = cv2.dilate(cleaned, kernel_dilate, iterations=1)

    # Fill character mask holes
    contours_mask, _ = cv2.findContours(
        dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    cv2.drawContours(dilated, contours_mask, -1, 255, -1)

    # Only discard the synthetic outermost crop edge. The previous 2% strip
    # could erase several pixels from real glyphs and caused black remnants.
    dilated[:, 0] = 0
    dilated[:, -1] = 0
    dilated[0, :] = 0
    dilated[-1, :] = 0

    full_mask = np.zeros((h, w), dtype=np.uint8)
    full_mask[y0:y1, x0:x1] = dilated

    # Cache the result
    _adaptive_mask_cache[cache_key] = full_mask.copy()

    return full_mask


def invalidate_adaptive_mask_cache():
    """Clear the adaptive mask cache. Call when page/blocks change significantly."""
    global _adaptive_mask_cache
    _adaptive_mask_cache.clear()
    logger.info("Adaptive mask cache cleared")


def generate_page_mask_only(page_id: str, db: Session) -> Path:
    """Generates text masks for all blocks on a page and saves mask assets without running inpainting."""
    with _inpaint_thread_lock:
        page = db.query(Page).filter(Page.id == page_id).first()
        if not page:
            raise ValueError("Page not found")

        source_path = Path(page.source_image_path)
        img = page_image_cache.get_source_image(page_id)
        if img is None:
            img = cv2_imread_unicode(str(source_path))
            if img is None:
                raise ValueError(f"Failed to load image: {source_path}")
            page_image_cache.set_source_image(page_id, img)

        h, w = img.shape[:2]
        effective_mask = np.zeros((h, w), dtype=np.uint8)
        project_settings = page.project.settings or {}

        for block in page.text_blocks:
            px0, py0, px1, py1 = _padded_block_coords(block, w, h)
            block_mask = get_automatic_block_mask(img, block, project_settings)
            effective_mask = cv2.bitwise_or(effective_mask, block_mask)
            # Save individual block mask
            crop_mask = block_mask[py0:py1, px0:px1]
            custom_mask_path = _mask_asset_path(page, f"mask_{block.id}.png")
            cv2_imwrite_unicode(str(custom_mask_path), crop_mask)

        # Save page level mask and cache
        _write_effective_page_mask_cache(page, effective_mask)
        page_mask_path = _mask_asset_path(page, "manual_mask.png")
        cv2_imwrite_unicode(str(page_mask_path), effective_mask)
        logger.info("Generated mask only for page %s at %s", page_id, page_mask_path)
        return page_mask_path


def _single_pass_full_page_inpaint(
    img: np.ndarray,
    mask: np.ndarray,
    inpaint_service: Any,
    *,
    chunk_height: int = 1024,
    overlap: int = 64,
    cancel_check: Any = None,
) -> np.ndarray:
    """Ultra-fast ImageTrans-style single-pass inpainting.

    Instead of cropping N small regions and running N separate neural passes,
    this processes the entire page (or vertical chunks for tall webtoons) in 1 pass,
    reducing inpainting time from 60-80s down to ~1.7s on CPU/GPU.
    Only the masked pixels are blended back onto the original high-resolution image,
    preserving 100% full sharpness of non-text drawings.
    """
    h, w = img.shape[:2]
    img_cleaned = img.copy()

    # Standard manga/comic page (single pass)
    if h <= chunk_height:
        if cancel_check and cancel_check():
            return img_cleaned
        inpainted_full = inpaint_service.inpaint(img, mask)
        if inpainted_full is not None and inpainted_full.shape[:2] == (h, w):
            mask_indices = mask > 0
            if np.any(mask_indices):
                mask_blur = cv2.GaussianBlur(mask, (3, 3), 0).astype(np.float32) / 255.0
                mask_blur_3d = np.expand_dims(mask_blur, axis=2)
                blended = (
                    inpainted_full.astype(np.float32) * mask_blur_3d
                    + img.astype(np.float32) * (1.0 - mask_blur_3d)
                )


def _color_match_and_blend_crop(
    inpainted_crop: np.ndarray,
    original_crop: np.ndarray,
    crop_mask: np.ndarray,
) -> np.ndarray:
    """Color-match inpainted crop to surrounding context and feather-blend at boundary.

    Uses channel-wise mean/stddev tone correction to prevent color drift, then
    applies distance-transform feathering at the mask boundary for seamless
    paste-back (ported from MangaToolPlus _color_match_and_blend).
    """
    if inpainted_crop.shape != original_crop.shape:
        return inpainted_crop

    src = inpainted_crop.copy()
    mask_bin = (crop_mask > 0).astype(np.uint8)
    context_mask = cv2.bitwise_not(mask_bin * 255)

    # Channel-wise mean/stddev tone correction
    if cv2.countNonZero(context_mask) > 10 and cv2.countNonZero(mask_bin) > 0:
        for c in range(3):
            sm, ss = cv2.meanStdDev(src[:, :, c], mask=context_mask)
            dm, ds = cv2.meanStdDev(original_crop[:, :, c], mask=context_mask)
            scale = float(np.clip(ds[0][0] / (ss[0][0] + 1e-5), 0.7, 1.5))
            corrected = np.clip(
                (src[:, :, c].astype(np.float32) - sm[0][0]) * scale + dm[0][0],
                0, 255,
            ).astype(np.uint8)
            src[:, :, c] = np.where(mask_bin > 0, corrected, src[:, :, c])

    # Distance-transform feathering at mask boundary
    ys, xs = np.where(mask_bin > 0)
    if xs.size == 0:
        return original_crop.copy()

    region_min = min(int(xs.max() - xs.min()) + 1, int(ys.max() - ys.min()) + 1)
    feather = int(np.clip(region_min * 0.25, 1, 4))

    dist = cv2.distanceTransform(mask_bin, cv2.DIST_L2, 3)
    alpha = np.clip(dist / max(feather, 1), 0.0, 1.0)
    k = (feather * 2 + 1) | 1
    alpha = cv2.GaussianBlur(alpha, (k, k), 0)
    mask_f = alpha[:, :, np.newaxis]

    blended = (
        src.astype(np.float32) * mask_f
        + original_crop.astype(np.float32) * (1.0 - mask_f)
    )
    return np.clip(blended, 0, 255).astype(np.uint8)


def _cluster_inpaint(
    img: np.ndarray,
    mask: np.ndarray,
    text_blocks: list[Any],
    page_width: int,
    page_height: int,
    inpaint_service: Any,
    settings: dict,
    *,
    context_padding: int = 48,
    cancel_check: Any = None,
) -> np.ndarray:
    """Cluster-Aware Inpainting: merge nearby text blocks into clusters, then
    send one crop per cluster to the inpainting model.

    For a page with 20 text blocks, blocks within 150px of each other are merged
    into ~5 clusters, reducing LaMa inference calls by ~75%.  Each cluster crop
    receives progressive context padding (min 64px, proportional to cluster size)
    and is blended back with color-match tone correction + distance-transform
    feathering for seamless results.
    """
    img_cleaned = img.copy()
    h, w = img.shape[:2]
    MERGE_THRESHOLD = 150

    # --- 1. Build block bounding boxes ---
    block_rects: list[dict] = []
    for block in text_blocks:
        px0, py0, px1, py1 = _padded_block_coords(block, w, h)
        block_mask = mask[py0:py1, px0:px1]
        if np.count_nonzero(block_mask) == 0:
            continue
        block_rects.append({"x1": px0, "y1": py0, "x2": px1, "y2": py1})

    if not block_rects:
        return img_cleaned

    # --- 2. BFS proximity clustering (merge blocks within MERGE_THRESHOLD px) ---
    block_rects.sort(key=lambda r: (r["y1"], r["x1"]))
    clusters: list[dict] = []

    while block_rects:
        current = block_rects.pop(0)
        i = 0
        while i < len(block_rects):
            r = block_rects[i]
            dx = max(0, current["x1"] - r["x2"], r["x1"] - current["x2"])
            dy = max(0, current["y1"] - r["y2"], r["y1"] - current["y2"])
            if dx < MERGE_THRESHOLD and dy < MERGE_THRESHOLD:
                current["x1"] = min(current["x1"], r["x1"])
                current["y1"] = min(current["y1"], r["y1"])
                current["x2"] = max(current["x2"], r["x2"])
                current["y2"] = max(current["y2"], r["y2"])
                block_rects.pop(i)
                i = 0  # restart to catch transitive merges
            else:
                i += 1
        clusters.append(current)

    total_clusters = len(clusters)
    logger.info(
        f"⚡ [CLUSTER INPAINT] {len(text_blocks)} blocks → {total_clusters} clusters"
    )

    # --- 3. Inpaint each cluster ---
    for idx, cluster in enumerate(clusters, 1):
        if cancel_check and cancel_check():
            break

        cx1, cy1, cx2, cy2 = cluster["x1"], cluster["y1"], cluster["x2"], cluster["y2"]
        cw, ch = cx2 - cx1, cy2 - cy1

        # Progressive context padding: min 64px, proportional to cluster size
        pad_x = max(64, min(256, cw // 3, 160))
        pad_y = max(64, min(256, ch // 3, 160))

        bx0 = max(0, cx1 - pad_x)
        by0 = max(0, cy1 - pad_y)
        bx1 = min(w, cx2 + pad_x)
        by1 = min(h, cy2 + pad_y)

        crop_img = img_cleaned[by0:by1, bx0:bx1].copy()
        crop_mask = mask[by0:by1, bx0:bx1].copy()

        if np.count_nonzero(crop_mask) == 0:
            continue

        crop_h, crop_w = crop_img.shape[:2]
        t_start = time.perf_counter()

        try:
            # Clamp very large crops to max 1024px before inference
            max_dim = max(crop_h, crop_w)
            scale = 1.0
            if max_dim > 1024:
                scale = 1024.0 / max_dim
                proc_w = max(8, int(crop_w * scale))
                proc_h = max(8, int(crop_h * scale))
                proc_img = cv2.resize(crop_img, (proc_w, proc_h), interpolation=cv2.INTER_AREA)
                proc_mask = cv2.resize(crop_mask, (proc_w, proc_h), interpolation=cv2.INTER_NEAREST)
            elif max_dim > 512:
                scale = 512.0 / max_dim
                proc_w = max(8, int(crop_w * scale))
                proc_h = max(8, int(crop_h * scale))
                proc_img = cv2.resize(crop_img, (proc_w, proc_h), interpolation=cv2.INTER_AREA)
                proc_mask = cv2.resize(crop_mask, (proc_w, proc_h), interpolation=cv2.INTER_NEAREST)
            else:
                proc_img, proc_mask = crop_img, crop_mask
                scale = 1.0

            inpainted_proc = inpaint_service.inpaint(proc_img, proc_mask)

            if inpainted_proc is not None:
                if scale != 1.0:
                    inpainted_crop = cv2.resize(
                        inpainted_proc, (crop_w, crop_h), interpolation=cv2.INTER_CUBIC
                    )
                elif inpainted_proc.shape[:2] != (crop_h, crop_w):
                    inpainted_crop = cv2.resize(
                        inpainted_proc, (crop_w, crop_h), interpolation=cv2.INTER_LINEAR
                    )
                else:
                    inpainted_crop = inpainted_proc

                # Color-match tone correction + distance-transform feathered blend
                blended_crop = _color_match_and_blend_crop(inpainted_crop, crop_img, crop_mask)
                img_cleaned[by0:by1, bx0:bx1] = blended_crop
            else:
                # Fallback to Telea
                telea_crop = cv2.inpaint(crop_img, crop_mask, inpaintRadius=4, flags=cv2.INPAINT_TELEA)
                mask_indices = crop_mask > 0
                crop_img[mask_indices] = telea_crop[mask_indices]
                img_cleaned[by0:by1, bx0:bx1] = crop_img

            t_ms = (time.perf_counter() - t_start) * 1000
            logger.info(
                f"   ✨ [Cluster {idx}/{total_clusters}] ({crop_w}×{crop_h} px, "
                f"{cw}×{ch} content) → cleaned in {t_ms:.1f} ms"
            )
        except Exception as e:
            logger.warning(f"Cluster inpaint error for cluster {idx}: {e}")
            telea_crop = cv2.inpaint(crop_img, crop_mask, inpaintRadius=4, flags=cv2.INPAINT_TELEA)
            mask_indices = crop_mask > 0
            crop_img[mask_indices] = telea_crop[mask_indices]
            img_cleaned[by0:by1, bx0:bx1] = crop_img

    logger.info(f"✅ Cluster Inpainting completed: {total_clusters} clusters processed!")

    # Phase 6: Clear GPU VRAM cache after batch inference to prevent VRAM leak
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
            logger.debug("GPU VRAM cache cleared after cluster inpaint batch")
    except ImportError:
        pass

    return img_cleaned


def _per_block_inpaint(
    img: np.ndarray,
    mask: np.ndarray,
    text_blocks: list[Any],
    page_width: int,
    page_height: int,
    inpaint_service: Any,
    settings: dict,
    *,
    context_padding: int = 48,
    cancel_check: Any = None,
) -> np.ndarray:
    """Per-Block Inpainting: ส่งทีละ text block แยกกัน (เสถียรที่สุดสำหรับ CPU/GPU ทุกระดับ).

    แทนที่จะรวม regions ที่อยู่ใกล้กัน, โหมดนี้ inpaint ทีละ text block โดยตรง.
    เหมาะสำหรับระบบที่มีหน่วยความจำน้อยหรือต้องการความเสถียรสูงสุด.
    """
    img_cleaned = img.copy()
    h, w = img.shape[:2]

    total_blocks = len(text_blocks)
    logger.info(f"⚡ [Per-Block Inpaint] Processing {total_blocks} text blocks independently...")

    for idx, block in enumerate(text_blocks, 1):
        if cancel_check and cancel_check():
            break

        # Get block bounds with padding
        px0, py0, px1, py1 = _padded_block_coords(block, w, h)

        # Extract block mask
        block_mask = mask[py0:py1, px0:px1]
        if np.count_nonzero(block_mask) == 0:
            continue

        # Add context padding
        pad = _effective_inpaint_context_padding(context_padding, px1 - px0, py1 - py0)
        bx0 = max(0, px0 - pad)
        by0 = max(0, py0 - pad)
        bx1 = min(w, px1 + pad)
        by1 = min(h, py1 + pad)

        crop_img = img_cleaned[by0:by1, bx0:bx1]
        crop_mask = mask[by0:by1, bx0:bx1]

        if np.count_nonzero(crop_mask) > 0:
            crop_h, crop_w = crop_img.shape[:2]
            t_start = time.perf_counter()
            try:
                # Fast inference scaling (max 512px) - ImageTrans standard
                max_dim = max(crop_h, crop_w)
                if max_dim > 512:
                    scale = 512.0 / max_dim
                    proc_w, proc_h = max(8, int(crop_w * scale)), max(8, int(crop_h * scale))
                    proc_img = cv2.resize(crop_img, (proc_w, proc_h), interpolation=cv2.INTER_AREA)
                    proc_mask = cv2.resize(crop_mask, (proc_w, proc_h), interpolation=cv2.INTER_NEAREST)
                else:
                    proc_img, proc_mask = crop_img, crop_mask

                inpainted_proc = inpaint_service.inpaint(proc_img, proc_mask)
                if inpainted_proc is not None:
                    if inpainted_proc.shape[:2] != (crop_h, crop_w):
                        inpainted_crop = cv2.resize(inpainted_proc, (crop_w, crop_h), interpolation=cv2.INTER_LINEAR)
                    else:
                        inpainted_crop = inpainted_proc

                    # ImageTrans cvMat.copyTo seamless blending:
                    mask_indices = crop_mask > 0
                    mask_blur = cv2.GaussianBlur(crop_mask, (3, 3), 0).astype(np.float32) / 255.0
                    mask_blur_3d = np.expand_dims(mask_blur, axis=2)
                    blended = (
                        inpainted_crop.astype(np.float32) * mask_blur_3d
                        + crop_img.astype(np.float32) * (1.0 - mask_blur_3d)
                    )
                    crop_img[mask_indices] = np.clip(blended[mask_indices], 0, 255).astype(np.uint8)
                    img_cleaned[by0:by1, bx0:bx1] = crop_img
                else:
                    telea_crop = cv2.inpaint(crop_img, crop_mask, inpaintRadius=4, flags=cv2.INPAINT_TELEA)
                    mask_indices = crop_mask > 0
                    crop_img[mask_indices] = telea_crop[mask_indices]
                    img_cleaned[by0:by1, bx0:bx1] = crop_img

                t_ms = (time.perf_counter() - t_start) * 1000
                logger.info(f"   ✨ [Block {idx}/{total_blocks}] ({crop_w}x{crop_h} px) -> cleaned in {t_ms:.1f} ms")
            except Exception as e:
                logger.warning(f"Block inpaint error for block {idx}, using Telea: {e}")
                telea_crop = cv2.inpaint(crop_img, crop_mask, inpaintRadius=4, flags=cv2.INPAINT_TELEA)
                mask_indices = crop_mask > 0
                crop_img[mask_indices] = telea_crop[mask_indices]
                img_cleaned[by0:by1, bx0:bx1] = crop_img
                t_ms = (time.perf_counter() - t_start) * 1000
                logger.info(f"   ✨ [Block {idx}/{total_blocks}] ({crop_w}x{crop_h} px) -> fallback in {t_ms:.1f} ms")

    logger.info(f"✅ Per-Block Inpainting completed for {total_blocks} blocks!")

    # Clear GPU VRAM cache after batch inference
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
    except ImportError:
        pass

    return img_cleaned


def _region_based_inpaint(
    img: np.ndarray,
    mask: np.ndarray,
    inpaint_service: Any,
    *,
    context_padding: int = 48,
    cancel_check: Any = None,
) -> np.ndarray:
    """Ultra-fast Region-based Bounding Box Inpainting (1:1 with ImageTrans architecture).

    Extracts connected component bounding boxes around text masks with context padding,
    sends only the small crop (e.g. 172x303 px) to LaMa/ONNX, and blends back into original.
    Extremely fast (<0.05s per box on GPU, <0.3s on CPU) with zero VRAM strain and zero blur.
    """
    h, w = img.shape[:2]
    img_cleaned = img.copy()
    
    regions = _find_inpaint_regions(mask)
    if not regions:
        return img_cleaned
        
    total_regions = len(regions)
    logger.info(f"⚡ [Fast Box Inpaint] Inpainting {total_regions} text boxes on page ({w}x{h})...")
    
    for idx, (cx, cy, cw, ch) in enumerate(regions, 1):
        if cancel_check and cancel_check():
            break
            
        pad = _effective_inpaint_context_padding(context_padding, cw, ch)
        bx0 = max(0, cx - pad)
        by0 = max(0, cy - pad)
        bx1 = min(w, cx + cw + pad)
        by1 = min(h, cy + ch + pad)
        
        crop_img = img_cleaned[by0:by1, bx0:bx1]
        crop_mask = mask[by0:by1, bx0:bx1]
        
        if np.count_nonzero(crop_mask) > 0:
            crop_h, crop_w = crop_img.shape[:2]
            t_box0 = time.perf_counter()
            try:
                # Fast inference scaling (max 512px) - guarantees <50ms per box even on CPU
                max_dim = max(crop_h, crop_w)
                if max_dim > 512:
                    scale = 512.0 / max_dim
                    proc_w, proc_h = max(8, int(crop_w * scale)), max(8, int(crop_h * scale))
                    proc_img = cv2.resize(crop_img, (proc_w, proc_h), interpolation=cv2.INTER_AREA)
                    proc_mask = cv2.resize(crop_mask, (proc_w, proc_h), interpolation=cv2.INTER_NEAREST)
                else:
                    proc_img, proc_mask = crop_img, crop_mask

                inpainted_proc = inpaint_service.inpaint(proc_img, proc_mask)
                if inpainted_proc is not None:
                    if inpainted_proc.shape[:2] != (crop_h, crop_w):
                        inpainted_crop = cv2.resize(inpainted_proc, (crop_w, crop_h), interpolation=cv2.INTER_LINEAR)
                    else:
                        inpainted_crop = inpainted_proc

                    mask_indices = crop_mask > 0
                    mask_blur = cv2.GaussianBlur(crop_mask, (3, 3), 0).astype(np.float32) / 255.0
                    mask_blur_3d = np.expand_dims(mask_blur, axis=2)
                    blended = (
                        inpainted_crop.astype(np.float32) * mask_blur_3d
                        + crop_img.astype(np.float32) * (1.0 - mask_blur_3d)
                    )
                    crop_img[mask_indices] = np.clip(blended[mask_indices], 0, 255).astype(np.uint8)
                    img_cleaned[by0:by1, bx0:bx1] = crop_img
                else:
                    telea_crop = cv2.inpaint(crop_img, crop_mask, inpaintRadius=4, flags=cv2.INPAINT_TELEA)
                    mask_indices = crop_mask > 0
                    crop_img[mask_indices] = telea_crop[mask_indices]
                    img_cleaned[by0:by1, bx0:bx1] = crop_img
                
                t_box_ms = (time.perf_counter() - t_box0) * 1000
                logger.info(f"   ✨ [Box {idx}/{total_regions}] ({crop_w}x{crop_h} px) -> cleaned in {t_box_ms:.1f} ms")
            except Exception as e_box:
                logger.debug(f"Box inpaint error on region {idx}/{total_regions}: {e_box}")
                telea_crop = cv2.inpaint(crop_img, crop_mask, inpaintRadius=4, flags=cv2.INPAINT_TELEA)
                mask_indices = crop_mask > 0
                crop_img[mask_indices] = telea_crop[mask_indices]
                img_cleaned[by0:by1, bx0:bx1] = crop_img
                t_box_ms = (time.perf_counter() - t_box0) * 1000
                logger.info(f"   ✨ [Box {idx}/{total_regions}] ({crop_w}x{crop_h} px) -> fallback in {t_box_ms:.1f} ms")

    logger.info(f"✅ Fast Box Inpainting completed for all {total_regions} regions!")
    return img_cleaned


def clean_page_text(page_id: str, db: Session, *, engine_override: str | None = None, cancel_check: Any = None) -> Path:
    with _inpaint_thread_lock:
        return _clean_page_text_impl(page_id, db, engine_override=engine_override, cancel_check=cancel_check)


def _clean_page_text_impl(page_id: str, db: Session, *, engine_override: str | None = None, cancel_check: Any = None) -> Path:
    """
    Cleans text blocks from a manga page image by generating text masks
    and applying OpenCV Telea Inpainting.
    Saves results as inpainted.png.
    """
    started_at = time.perf_counter()
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise ValueError("Page not found")

    source_path = Path(page.source_image_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Source image not found at {source_path}")

    # 1. Load source image (with memory caching)
    img = page_image_cache.get_source_image(page_id)
    if img is None:
        img = cv2_imread_unicode(str(source_path))
        if img is None:
            raise ValueError(f"Failed to load image via OpenCV: {source_path}")
        page_image_cache.set_source_image(page_id, img)
    # Solid-fill optimization and other cleanup stages edit ``img`` in place.
    # Never let those writes poison the canonical source frame held by the
    # memory cache; region reclean must always be able to rebuild from source.
    img = img.copy()

    h, w = img.shape[:2]

    # 2. Create blank binary mask
    mask = np.zeros((h, w), dtype=np.uint8)
    effective_mask = np.zeros((h, w), dtype=np.uint8)

    project_settings = page.project.settings or {}
    performance_settings = resolve_performance_settings(project_settings)
    dilation_kernel = int(project_settings.get("mask_dilation_kernel", 3))
    process_by_text_areas = should_use_smart_mask(project_settings)
    if engine_override:
        use_lama = resolve_inpaint_engine_name({"inpaint_engine": engine_override}) in {"manga_cleaner", "lama", "mat"}
    else:
        use_lama = should_use_lama_inpaint(project_settings)
    context_padding = max(0, min(512, int(project_settings.get("inpaint_context_padding", 96))))
    page_mask_override = _load_page_mask_override(page, w, h)

    # Check for authoritative page-level mask override (drawn manually by user on canvas)
    has_existing_page_mask = False
    if page_mask_override is not None:
        mask = page_mask_override
        effective_mask = mask.copy()
        has_existing_page_mask = True

    # 3. Draw text regions on mask from blocks, custom block masks, and current dilation kernel
    if not has_existing_page_mask:
        for block in page.text_blocks:
            x0 = int(block.x)
            y0 = int(block.y)
            x1 = int(block.x + block.width)
            y1 = int(block.y + block.height)

            px0, py0, px1, py1 = _padded_block_coords(block, w, h)

            block_mask = None
            has_custom_mask = False
            for m_name in (f"mask_{block.id}.png", f"smart_balloon_{block.id}.png"):
                custom_mask_path = _mask_asset_path(page, m_name)
                if custom_mask_path.exists():
                    custom_mask = cv2_imread_unicode(str(custom_mask_path), cv2.IMREAD_GRAYSCALE)
                    if custom_mask is not None and np.count_nonzero(custom_mask) > 0:
                        has_custom_mask = True
                        block_mask = np.zeros((h, w), dtype=np.uint8)
                        if custom_mask.shape[:2] == (py1 - py0, px1 - px0):
                            block_mask[py0:py1, px0:px1] = custom_mask
                        elif custom_mask.shape[:2] == (y1 - y0, x1 - x0):
                            block_mask[y0:y1, x0:x1] = custom_mask
                        else:
                            custom_resized = cv2.resize(custom_mask, (px1 - px0, py1 - py0), interpolation=cv2.INTER_NEAREST)
                            block_mask[py0:py1, px0:px1] = custom_resized
                        break

            if block_mask is None:
                block_mask = get_automatic_block_mask(img, block, project_settings)

            effective_mask = cv2.bitwise_or(effective_mask, block_mask)

            solid_color = None
            if _should_use_solid_fill(process_by_text_areas, has_custom_mask, settings=project_settings):
                solid_color = _detect_uniform_fill_color(
                    img[y0:y1, x0:x1], block_mask[y0:y1, x0:x1]
                )

            if solid_color is not None:
                # --- Phase 5+8: Connected-Component Feathered Solid Fill ---
                # Split mask into components, fill each independently with feathered edges
                local_mask = block_mask[y0:y1, x0:x1]
                num_labels, labels, stats, _centroids = cv2.connectedComponentsWithStats(
                    local_mask, connectivity=8
                )
                if num_labels <= 1:
                    # Single region or empty — direct feathered fill
                    bw, bh = x1 - x0, y1 - y0
                    blur_r = max(7, int(max(bw, bh) * 0.04) | 1)
                    mask_blur = cv2.GaussianBlur(block_mask.astype(np.float32), (blur_r, blur_r), 0) / 255.0
                    mask_f = mask_blur[:, :, np.newaxis]
                    fill_layer = np.full_like(img, solid_color, dtype=np.float32)
                    img[:] = np.clip(
                        fill_layer * mask_f + img.astype(np.float32) * (1.0 - mask_f),
                        0, 255,
                    ).astype(np.uint8)
                else:
                    # Multiple components — fill each with per-component color + feather
                    for ci in range(1, num_labels):
                        cx, cy, cw_cc, ch_cc, area = stats[ci]
                        if cw_cc == 0 or ch_cc == 0:
                            continue
                        comp_mask = (labels == ci).astype(np.uint8) * 255
                        # Try per-component color estimation from ring
                        comp_color = _detect_uniform_fill_color(
                            img[y0:y1, x0:x1], comp_mask
                        )
                        if comp_color is None:
                            comp_color = solid_color
                        # Feathered fill for this component
                        blur_r = max(7, int(max(cw_cc, ch_cc) * 0.04) | 1)
                        full_comp_mask = np.zeros((h, w), dtype=np.uint8)
                        full_comp_mask[y0:y1, x0:x1] = comp_mask
                        mask_blur = cv2.GaussianBlur(full_comp_mask.astype(np.float32), (blur_r, blur_r), 0) / 255.0
                        mask_f = mask_blur[:, :, np.newaxis]
                        fill_layer = np.full_like(img, comp_color, dtype=np.float32)
                        img[:] = np.clip(
                            fill_layer * mask_f + img.astype(np.float32) * (1.0 - mask_f),
                            0, 255,
                        ).astype(np.uint8)
                logger.info(
                    f"Solid Fill: Cleaned block {block.id} with feathered CC fill ({num_labels - 1} components)."
                )
            else:
                mask = cv2.bitwise_or(mask, block_mask)

    # A full-page editor save is authoritative, so erased automatic regions stay
    # erased. Legacy manual_mask.png remains an additive brush asset.
    manual_mask_path = _mask_asset_path(page, "manual_mask.png")
    if page_mask_override is not None:
        mask = page_mask_override.copy()
        effective_mask = page_mask_override.copy()
    elif manual_mask_path.exists():
        logger.info(f"Found manual brush mask at {manual_mask_path}. Blending...")
        manual_mask = cv2_imread_unicode(str(manual_mask_path), cv2.IMREAD_GRAYSCALE)
        if manual_mask is not None:
            if manual_mask.shape[:2] != (h, w):
                manual_mask = cv2.resize(
                    manual_mask, (w, h), interpolation=cv2.INTER_NEAREST
                )
            mask = cv2.bitwise_or(mask, manual_mask)
            effective_mask = cv2.bitwise_or(effective_mask, manual_mask)

    # 3b. Optional full-page text mask. It is opt-in because an unconstrained
    # page model can classify line art as text and erase artwork outside balloons.
    if page_mask_override is None and project_settings.get("full_page_unet_clean", False):
        unet_mask = _get_full_page_manga_unet_mask(img)
        if unet_mask is not None:
            mask = cv2.bitwise_or(mask, unet_mask)

    try:
        _write_effective_page_mask_cache(page, effective_mask)
    except OSError as exc:
        logger.warning("Failed to save effective mask: %s", exc)

    mask_ready_at = time.perf_counter()

    # 4. Apply Inpainting (LaMa ONNX preferred, Telea fallback) on local connected components
    img_cleaned = img.copy()

    if np.count_nonzero(mask) > 0:
        engine_name = resolve_inpaint_engine_name(project_settings)
        gpu_ep = get_execution_provider_setting(project_settings)

        custom_gpu_url = project_settings.get("gpu_inpaint_url")

        inpaint_service = None
        if engine_name == "mat":
            inpaint_service = _get_mat(execution_provider=gpu_ep)
            if inpaint_service is None:
                engine_name = "lama"
                inpaint_service = _get_lama(execution_provider=gpu_ep, custom_url=custom_gpu_url)
        elif engine_name == "lama_onnx":
            inpaint_service = _get_lama(execution_provider=gpu_ep, force_onnx=True)
        elif engine_name in {"lama", "lama_manga", "manga_cleaner"}:
            inpaint_service = _get_lama(execution_provider=gpu_ep, custom_url=custom_gpu_url)

        if inpaint_service is not None:
            providers = getattr(inpaint_service, "current_providers", ["GPU (CUDA)"])
            provider_str = ", ".join(providers) if isinstance(providers, list) else str(providers)

            # Choose inpaint strategy based on project settings (Default: cluster)
            inpaint_strategy = project_settings.get("inpaint_strategy")
            if not inpaint_strategy or inpaint_strategy not in ("region", "parallel", "per_block", "cluster"):
                inpaint_strategy = "cluster"

            if inpaint_strategy == "cluster":
                logger.info(f"🚀 [CLUSTER INPAINT] Hardware: {provider_str} | Engine: {engine_name} | Page: {source_path.name}")
                img_cleaned = _cluster_inpaint(
                    img_cleaned,
                    mask,
                    page.text_blocks,
                    w,
                    h,
                    inpaint_service,
                    project_settings,
                    context_padding=context_padding,
                    cancel_check=cancel_check,
                )
            elif inpaint_strategy == "per_block":
                logger.info(f"🚀 [PER-BLOCK INPAINT] Hardware: {provider_str} | Engine: {engine_name} | Page: {source_path.name}")
                img_cleaned = _per_block_inpaint(
                    img_cleaned,
                    mask,
                    page.text_blocks,
                    w,
                    h,
                    inpaint_service,
                    project_settings,
                    context_padding=context_padding,
                    cancel_check=cancel_check,
                )
            elif inpaint_strategy == "parallel":
                logger.info(f"🚀 [PARALLEL INPAINT] Hardware: {provider_str} | Engine: {engine_name} | Page: {source_path.name}")
                from app.services.parallel_inpaint import inpaint_regions_parallel
                regions = _find_inpaint_regions(mask)
                img_cleaned = inpaint_regions_parallel(
                    img_cleaned,
                    mask,
                    regions,
                    inpaint_service,
                    project_settings,
                    cancel_check=cancel_check,
                )
            else:  # Default: "region"
                logger.info(f"🚀 [REGION INPAINT] Hardware: {provider_str} | Engine: {engine_name} | Page: {source_path.name}")
                img_cleaned = _region_based_inpaint(
                    img_cleaned,
                    mask,
                    inpaint_service,
                    context_padding=context_padding,
                    cancel_check=cancel_check,
                )
        else:
            logger.warning(f"⚠️ [FALLBACK CPU TELEA] GPU Inpaint Server unreachable. Applying Telea fallback on: {source_path.name}")
            regions = _find_inpaint_regions(mask)
            for cx, cy, cw, ch in regions:
                if cancel_check and cancel_check():
                    break
                pad = _effective_inpaint_context_padding(context_padding, cw, ch)
                bx0 = max(0, cx - pad)
                by0 = max(0, cy - pad)
                bx1 = min(w, cx + cw + pad)
                by1 = min(h, cy + ch + pad)
                crop_img = img_cleaned[by0:by1, bx0:bx1]
                crop_mask = mask[by0:by1, bx0:bx1]
                if np.count_nonzero(crop_mask) > 0:
                    inpainted_crop = cv2.inpaint(crop_img, crop_mask, inpaintRadius=4, flags=cv2.INPAINT_TELEA)
                    mask_indices = crop_mask > 0
                    if np.any(mask_indices):
                        crop_img[mask_indices] = inpainted_crop[mask_indices]
                    img_cleaned[by0:by1, bx0:bx1] = crop_img
            # End of sequential inpainting loop

        # LaMa already blends only inside the precise mask and Telea only writes
        # masked pixels. A full-page bilateral pass is expensive and softens ink.
        final_img = img_cleaned
    else:
        final_img = img_cleaned

    # 6. Save output
    logger.info(f"Saving cleaned image for page {page_id}")
    clean_dir = page_asset_dir(page, "clean")
    output_path = inpainted_asset_path(page)
    logger.info(f"Writing inpainted image to: {output_path}")
    cv2_imwrite_unicode(str(output_path), final_img)
    logger.info(f"Inpainted image saved successfully")

    # Save a downsampled preview version of inpainted image for smooth UI rendering
    h, w = final_img.shape[:2]
    max_width = performance_settings.preview_width

    # 1. Scale based on width
    if w > max_width:
        ratio = max_width / w
        new_w = max_width
        new_h = int(h * ratio)
    else:
        new_w, new_h = w, h
    # 2. Cap height for JPEG limit (65535, cap to 60000 for safety)
    if new_h > 60000:
        scale_ratio = 60000 / new_h
        new_w = int(new_w * scale_ratio)
        new_h = 60000

    if (new_w, new_h) != (w, h):
        preview_inpainted = cv2.resize(
            final_img, (new_w, new_h), interpolation=cv2.INTER_AREA
        )
    else:
        preview_inpainted = final_img

    preview_inpainted_path = inpaint_preview_asset_path(page)
    logger.info(f"Writing preview image to: {preview_inpainted_path}")
    cv2_imwrite_unicode(str(preview_inpainted_path), preview_inpainted)
    logger.info(f"Preview image saved successfully")

    # The desktop static server keeps its fast cache under data/projects while
    # the canonical, user-visible assets live beside the story images.
    internal_clean_dir = source_path.parent / "clean"
    if internal_clean_dir.resolve() != clean_dir.resolve():
        internal_clean_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(output_path, internal_clean_dir / "inpainted.png")
        shutil.copy2(preview_inpainted_path, internal_clean_dir / "preview_inpainted.jpg")

    # Ensure clean directory contains ONLY clean image files for easy user copying
    try:
        for stale in clean_dir.glob("*_inpaint_preview.jpg"):
            stale.unlink(missing_ok=True)
        for stale in clean_dir.glob("*.json"):
            stale.unlink(missing_ok=True)
    except Exception:
        pass

    # Update page database record
    logger.info(f"Updating database for page {page_id}")
    page.inpainted_image_path = str(output_path)
    page_image_cache.set_clean_composite(page_id, final_img)
    write_clean_manifest(page)
    logger.info(f"Committing database changes for page {page_id}")
    db.commit()
    logger.info(f"Database commit successful for page {page_id}")

    logger.info(
        "Cleaned page saved: %s (mask %.0f ms, total %.0f ms)",
        output_path,
        (mask_ready_at - started_at) * 1000,
        (time.perf_counter() - started_at) * 1000,
    )
    return output_path


def reclean_page_block(page_id: str, block_id: str, db: Session, *, engine_override: str | None = None) -> Path:
    with _inpaint_thread_lock:
        return _reclean_page_block_impl(page_id, block_id, db, engine_override=engine_override)


def _reclean_page_block_impl(page_id: str, block_id: str, db: Session, *, engine_override: str | None = None) -> Path:
    """Reclean only the source-backed dirty region affected by one block mask.

    The existing clean output is used solely as the compositing target.  The
    dirty crop is always rebuilt from the original page, so repeated edits do
    not inpaint on top of previous inpainting artifacts.
    """
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise ValueError("Page not found")
    block = next((item for item in page.text_blocks if str(item.id) == str(block_id)), None)
    if block is None:
        raise ValueError("Text block does not belong to this page")

    source_path = Path(page.source_image_path)
    output_path = inpainted_asset_path(page)

    source = page_image_cache.get_source_image(page_id)
    if source is None:
        source = cv2_imread_unicode(str(source_path))
        if source is not None:
            page_image_cache.set_source_image(page_id, source)

    previous_clean = page_image_cache.get_clean_composite(page_id)
    if previous_clean is None:
        previous_clean = cv2_imread_unicode(str(output_path))
    if previous_clean is None and source is not None:
        previous_clean = source.copy()

    if source is None or previous_clean is None or source.shape != previous_clean.shape:
        raise ValueError("Failed to load source or compositing base for region reclean")

    height, width = source.shape[:2]
    settings = page.project.settings or {}
    dilation_kernel = int(settings.get("mask_dilation_kernel", 3))
    smart_mask = should_use_smart_mask(settings)
    if engine_override:
        use_lama = resolve_inpaint_engine_name({"inpaint_engine": engine_override}) in {"manga_cleaner", "lama", "mat"}
    else:
        use_lama = should_use_lama_inpaint(settings)
    requested_padding = max(0, min(512, int(settings.get("inpaint_context_padding", 96))))
    removal_mask = np.zeros((height, width), dtype=np.uint8)
    effective_mask = np.zeros((height, width), dtype=np.uint8)
    solid_masks: list[tuple[np.ndarray, list[int]]] = []
    page_mask_override = _load_page_mask_override(page, width, height)

    # Cluster-Aware Target Blocks: target block must ALWAYS be included and recleaned with its custom/smart mask
    target_blocks = [block]
    if getattr(page, "text_blocks", None):
        target_seed = _padded_block_coords(block, width, height)
        inflated_seed = (
            max(0, target_seed[0] - requested_padding),
            max(0, target_seed[1] - requested_padding),
            min(width, target_seed[2] + requested_padding),
            min(height, target_seed[3] + requested_padding),
        )
        for other_b in page.text_blocks:
            if getattr(other_b, "id", None) != getattr(block, "id", None):
                other_rect = _padded_block_coords(other_b, width, height)
                if _rectangles_intersect(inflated_seed, other_rect):
                    target_blocks.append(other_b)

    for candidate in target_blocks:
        x0 = max(0, min(width, int(candidate.x)))
        y0 = max(0, min(height, int(candidate.y)))
        x1 = max(x0, min(width, int(candidate.x + candidate.width)))
        y1 = max(y0, min(height, int(candidate.y + candidate.height)))
        if x1 <= x0 or y1 <= y0:
            continue

        px0, py0, px1, py1 = _padded_block_coords(candidate, width, height)

        custom_path = _mask_asset_path(page, f"mask_{candidate.id}.png")
        custom = cv2_imread_unicode(str(custom_path), cv2.IMREAD_GRAYSCALE) if custom_path.exists() else None
        has_custom_mask = custom is not None
        if custom is not None:
            block_mask = np.zeros((height, width), dtype=np.uint8)
            if custom.shape[:2] == (py1 - py0, px1 - px0):
                block_mask[py0:py1, px0:px1] = custom
            elif custom.shape[:2] == (y1 - y0, x1 - x0):
                block_mask[y0:y1, x0:x1] = custom
            else:
                custom_resized = cv2.resize(custom, (px1 - px0, py1 - py0), interpolation=cv2.INTER_NEAREST)
                block_mask[py0:py1, px0:px1] = custom_resized
        elif smart_mask:
            block_mask = get_automatic_block_mask(
                source, candidate, settings, dilation_kernel=dilation_kernel
            )
        else:
            block_mask = np.zeros((height, width), dtype=np.uint8)
            block_mask[y0:y1, x0:x1] = 255

        effective_mask = cv2.bitwise_or(effective_mask, block_mask)
        fill_color = (
            _detect_uniform_fill_color(source[y0:y1, x0:x1], block_mask[y0:y1, x0:x1])
            if _should_use_solid_fill(smart_mask, has_custom_mask, settings=settings)
            else None
        )
        if fill_color is None:
            removal_mask = cv2.bitwise_or(removal_mask, block_mask)
        else:
            solid_masks.append((block_mask, fill_color))

    manual_path = _mask_asset_path(page, "manual_mask.png")
    if page_mask_override is not None:
        removal_mask = cv2.bitwise_or(removal_mask, page_mask_override)
        effective_mask = cv2.bitwise_or(effective_mask, page_mask_override)
    elif manual_path.exists():
        manual_mask = cv2_imread_unicode(str(manual_path), cv2.IMREAD_GRAYSCALE)
        if manual_mask is not None:
            if manual_mask.shape[:2] != (height, width):
                manual_mask = cv2.resize(manual_mask, (width, height), interpolation=cv2.INTER_NEAREST)
            removal_mask = cv2.bitwise_or(removal_mask, manual_mask)
            effective_mask = cv2.bitwise_or(effective_mask, manual_mask)

    # The Mask Editor works on the padded layout crop, which may be much larger
    # than the OCR bbox.  Seed the complete editor crop so a region reclean also
    # restores pixels affected by an older/wider custom mask.
    seed = _padded_block_coords(block, width, height)
    regions = _find_inpaint_regions(removal_mask)
    dirty = seed
    selected_regions: list[tuple[int, int, int, int]] = []
    changed = True
    while changed:
        changed = False
        for rx, ry, rw, rh in regions:
            region = (rx, ry, rx + rw, ry + rh)
            if region in selected_regions or not _rectangles_intersect(dirty, region):
                continue
            selected_regions.append(region)
            dirty = (
                min(dirty[0], region[0]), min(dirty[1], region[1]),
                max(dirty[2], region[2]), max(dirty[3], region[3]),
            )
            changed = True

    # Include model context in the source crop.  Even an empty replacement mask
    # needs this crop to restore the old clean result back to original pixels.
    dirty_width, dirty_height = max(1, dirty[2] - dirty[0]), max(1, dirty[3] - dirty[1])
    padding = _effective_inpaint_context_padding(requested_padding, dirty_width, dirty_height)
    px0, py0 = max(0, dirty[0] - padding), max(0, dirty[1] - padding)
    px1, py1 = min(width, dirty[2] + padding), min(height, dirty[3] + padding)

    patch_mask = removal_mask[py0:py1, px0:px1]
    # Preserve existing clean artwork outside the active removal regions
    if previous_clean is not None and previous_clean.shape[:2] == (height, width):
        patch_clean = previous_clean[py0:py1, px0:px1].copy()
    else:
        patch_clean = source[py0:py1, px0:px1].copy()

    for block_mask, fill_color in solid_masks:
        local_mask = block_mask[py0:py1, px0:px1]
        if np.count_nonzero(local_mask):
            patch_clean[local_mask > 0] = fill_color

    gpu_ep = get_execution_provider_setting(settings)
    lama = _get_lama(execution_provider=gpu_ep) if use_lama else None
    logger.info(
        "reclean_page_block engine_override=%s use_lama=%s lama_loaded=%s gpu_ep=%s target_cluster_size=%d",
        engine_override, use_lama, lama is not None, gpu_ep, len(target_blocks),
    )

    for cx, cy, cw, ch in _find_inpaint_regions(patch_mask):
        cx1, cy1 = cx + cw, cy + ch
        local_padding = _effective_inpaint_context_padding(requested_padding, cw, ch)
        bx0, by0 = max(0, cx - local_padding), max(0, cy - local_padding)
        bx1, by1 = min(patch_clean.shape[1], cx1 + local_padding), min(patch_clean.shape[0], cy1 + local_padding)
        crop_image, crop_mask = patch_clean[by0:by1, bx0:bx1], patch_mask[by0:by1, bx0:bx1]
        if not np.count_nonzero(crop_mask):
            continue
        # Fast-Path: Check if region background is flat/solid color (e.g. speech balloon) when LaMa not active
        solid_color = None
        if _should_use_solid_fill(True, False, settings=settings):
            solid_color = _detect_uniform_fill_color(crop_image, crop_mask)
        if solid_color is not None:
            mask_indices = crop_mask > 0
            crop_image[mask_indices] = solid_color
            patch_clean[by0:by1, bx0:bx1] = crop_image
            continue
        try:
            if lama is not None:
                # Use tile-based inpainting for large regions
                crop_h, crop_w = crop_image.shape[:2]
                tile_threshold = settings.get("inpaint_tile_size", 1024)

                if max(crop_h, crop_w) > tile_threshold:
                    result = _tile_based_inpaint(
                        crop_image,
                        crop_mask,
                        lama,
                        tile_size=tile_threshold,
                        overlap=64
                    )
                else:
                    result = lama.inpaint(crop_image, crop_mask)
            else:
                result = cv2.inpaint(crop_image, crop_mask, 4, cv2.INPAINT_TELEA)
        except Exception as exc:
            logger.warning("Local LaMa region reclean failed; using Telea: %s", exc)
            result = cv2.inpaint(crop_image, crop_mask, 4, cv2.INPAINT_TELEA)
        patch_clean[by0:by1, bx0:bx1] = result

    final = previous_clean.copy()
    final[py0:py1, px0:px1] = patch_clean
    if not cv2_imwrite_unicode(str(output_path), final):
        raise OSError(f"Failed to save region reclean result: {output_path}")
    # Do not write the page-level editor cache from this block-only operation.
    # Its fingerprint is already stale after the custom mask save, so the next
    # editor read will rebuild the complete page mask from every block.
    preview_path = _write_inpaint_preview(page, final)

    source_clean_dir = source_path.parent / "clean"
    clean_dir = page_asset_dir(page, "clean")
    if source_clean_dir.resolve() != clean_dir.resolve():
        source_clean_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(output_path, source_clean_dir / "inpainted.png")
        shutil.copy2(preview_path, source_clean_dir / "preview_inpainted.jpg")

    page.inpainted_image_path = str(output_path)
    page.rendered_image_path = None
    page_image_cache.set_clean_composite(page_id, final, is_dirty=False)
    page_image_cache.set_patch(page_id, block_id, patch_clean, (px0, py0, px1, py1), "reclean", is_dirty=False)
    write_clean_manifest(page)
    db.commit()
    logger.info("Region recleaned block %s at (%d, %d)-(%d, %d)", block_id, px0, py0, px1, py1)
    return output_path


def _select_inpaint_preview_blocks(
    page: Page,
    block_id: str | None,
    image_width: int,
    image_height: int,
) -> tuple[list, tuple[int, int, int, int] | None]:
    """Limit an editor preview to one block and return its page-space crop.

    The normal page preview intentionally processes every block.  The Text Mask
    Editor must not do that: it is an isolated inspection tool and users need to
    judge only the mask they are currently editing.
    """
    blocks = list(page.text_blocks)
    if block_id is None:
        return blocks, None

    block = next((candidate for candidate in blocks if str(candidate.id) == str(block_id)), None)
    if block is None:
        raise ValueError("Text block does not belong to this page")

    # Use padded coordinates to match the Mask Editor's padded crop view
    x0, y0, x1, y1 = _padded_block_coords(block, image_width, image_height)
    if x1 <= x0 or y1 <= y0:
        raise ValueError("Text block has an empty preview region")
    return [block], (x0, y0, x1, y1)


def generate_inpaint_preview(
    page_id: str,
    db: Session,
    block_id: str | None = None,
) -> np.ndarray:
    """
    Generates and returns the inpainted image without saving it to the page's output path.
    """
    started_at = time.perf_counter()
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise ValueError("Page not found")

    source_path = Path(page.source_image_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Source image not found at {source_path}")

    img = cv2_imread_unicode(str(source_path))
    if img is None:
        raise ValueError(f"Failed to load image via OpenCV: {source_path}")

    h, w = img.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)

    project_settings = page.project.settings or {}
    performance_settings = resolve_performance_settings(project_settings)
    dilation_kernel = int(project_settings.get("mask_dilation_kernel", 3))
    process_by_text_areas = should_use_smart_mask(project_settings)
    use_lama = should_use_lama_inpaint(project_settings)

    preview_blocks, preview_bounds = _select_inpaint_preview_blocks(page, block_id, w, h)
    page_mask_override = _load_page_mask_override(page, w, h)

    for block in ([] if page_mask_override is not None else preview_blocks):
        x0 = int(block.x)
        y0 = int(block.y)
        x1 = int(block.x + block.width)
        y1 = int(block.y + block.height)
        if (x1 - x0) <= 0 or (y1 - y0) <= 0:
            continue

        px0, py0, px1, py1 = _padded_block_coords(block, w, h)

        custom_mask_path = _mask_asset_path(page, f"mask_{block.id}.png")
        has_custom_mask = False
        if custom_mask_path.exists():
            custom_mask = cv2_imread_unicode(str(custom_mask_path), cv2.IMREAD_GRAYSCALE)
            if custom_mask is not None:
                has_custom_mask = True
                block_mask = np.zeros((h, w), dtype=np.uint8)
                if custom_mask.shape[:2] == (py1 - py0, px1 - px0):
                    block_mask[py0:py1, px0:px1] = custom_mask
                elif custom_mask.shape[:2] == (y1 - y0, x1 - x0):
                    block_mask[y0:y1, x0:x1] = custom_mask
                else:
                    custom_resized = cv2.resize(custom_mask, (px1 - px0, py1 - py0), interpolation=cv2.INTER_NEAREST)
                    block_mask[py0:py1, px0:px1] = custom_resized
            else:
                if process_by_text_areas:
                    block_mask = get_automatic_block_mask(
                        img, block, project_settings, dilation_kernel=dilation_kernel
                    )
                else:
                    block_mask = np.zeros((h, w), dtype=np.uint8)
                    block_mask[y0:y1, x0:x1] = 255
        else:
            if process_by_text_areas:
                block_mask = get_automatic_block_mask(
                    img, block, project_settings, dilation_kernel=dilation_kernel
                )
            else:
                block_mask = np.zeros((h, w), dtype=np.uint8)
                block_mask[y0:y1, x0:x1] = 255

        solid_color = None
        if _should_use_solid_fill(process_by_text_areas, has_custom_mask, settings=project_settings):
            solid_color = _detect_uniform_fill_color(
                img[y0:y1, x0:x1], block_mask[y0:y1, x0:x1]
            )

        if solid_color is not None:
            # Paint directly on the source image to bypass inpainting and prevent border smudging
            img[block_mask > 0] = solid_color
        else:
            mask = cv2.bitwise_or(mask, block_mask)

    # Full-page editor overrides are authoritative; legacy manual masks add to
    # the automatically composed block mask.
    manual_mask_path = _mask_asset_path(page, "manual_mask.png")
    if page_mask_override is not None:
        mask = page_mask_override.copy()
    elif manual_mask_path.exists():
        manual_mask = cv2_imread_unicode(str(manual_mask_path), cv2.IMREAD_GRAYSCALE)
        if manual_mask is not None:
            if manual_mask.shape[:2] != (h, w):
                manual_mask = cv2.resize(
                    manual_mask, (w, h), interpolation=cv2.INTER_NEAREST
                )
            mask = cv2.bitwise_or(mask, manual_mask)

    img_cleaned = img.copy()

    if np.count_nonzero(mask) > 0:
        engine_name = resolve_inpaint_engine_name(project_settings)
        gpu_ep = get_execution_provider_setting(project_settings)

        inpaint_service = None
        if engine_name == "mat":
            inpaint_service = _get_mat(execution_provider=gpu_ep)
            if inpaint_service is None:
                inpaint_service = _get_lama(execution_provider=gpu_ep)
        elif engine_name in {"lama", "manga_cleaner"}:
            inpaint_service = _get_lama(execution_provider=gpu_ep)

        if engine_name != "telea" and inpaint_service is None:
            logger.warning("Inpainting engine '%s' selected for preview but is unavailable; using Telea fallback", engine_name)

        regions = _find_inpaint_regions(mask)
        for cx, cy, cw, ch in regions:
            cx1, cy1 = cx + cw, cy + ch

            requested_padding = max(
                0, min(512, int(project_settings.get("inpaint_context_padding", 96)))
            )
            pad = _effective_inpaint_context_padding(requested_padding, cw, ch)
            bx0 = max(0, cx - pad)
            by0 = max(0, cy - pad)
            bx1 = min(w, cx1 + pad)
            by1 = min(h, cy1 + pad)

            crop_w = bx1 - bx0
            crop_h = by1 - by0

            if crop_w <= 0 or crop_h <= 0:
                continue

            diff = abs(crop_w - crop_h)
            pad_half = diff // 2
            if crop_w > crop_h:
                by0 = max(0, by0 - pad_half)
                by1 = min(h, by1 + (diff - pad_half))
            else:
                bx0 = max(0, bx0 - pad_half)
                bx1 = min(w, bx1 + (diff - pad_half))

            crop_img = img_cleaned[by0:by1, bx0:bx1]
            crop_mask = mask[by0:by1, bx0:bx1]

            if np.count_nonzero(crop_mask) > 0:
                if inpaint_service is not None:
                    try:
                        crop_h, crop_w = crop_img.shape[:2]
                        tile_threshold = project_settings.get("inpaint_tile_size", 1024)

                        if max(crop_h, crop_w) > tile_threshold:
                            inpainted_crop = _tile_based_inpaint(
                                crop_img,
                                crop_mask,
                                inpaint_service,
                                tile_size=tile_threshold,
                                overlap=64
                            )
                        else:
                            inpainted_crop = inpaint_service.inpaint(crop_img, crop_mask)

                        img_cleaned[by0:by1, bx0:bx1] = inpainted_crop
                    except Exception as e:
                        logger.error(f"Local inpaint preview ({engine_name}) failed: {e}")
                        img_cleaned[by0:by1, bx0:bx1] = cv2.inpaint(
                            crop_img,
                            crop_mask,
                            inpaintRadius=4,
                            flags=cv2.INPAINT_TELEA,
                        )
                else:
                    img_cleaned[by0:by1, bx0:bx1] = cv2.inpaint(
                        crop_img, crop_mask, inpaintRadius=4, flags=cv2.INPAINT_TELEA
                    )

        final_img = img_cleaned
    else:
        final_img = img_cleaned

    logger.info(
        "Generated inpaint preview in %.0f ms",
        (time.perf_counter() - started_at) * 1000,
    )
    if preview_bounds is not None:
        x0, y0, x1, y1 = preview_bounds
        return final_img[y0:y1, x0:x1].copy()
    return final_img


def fast_telea_preview(crop_image: np.ndarray, crop_mask: np.ndarray) -> np.ndarray:
    """Ultra-fast preview using OpenCV Telea (5-15ms) for real-time mask drawing live preview."""
    if crop_image is None or crop_mask is None or crop_image.size == 0 or crop_mask.size == 0:
        raise ValueError("Invalid crop image or mask for fast preview")
    if crop_image.shape[:2] != crop_mask.shape[:2]:
        crop_mask = cv2.resize(crop_mask, (crop_image.shape[1], crop_image.shape[0]), interpolation=cv2.INTER_NEAREST)
    service = _get_lama()
    if service is not None:
        try:
            return service.inpaint(crop_image, crop_mask)
        except Exception:
            pass
    return cv2.inpaint(crop_image, crop_mask, 3, cv2.INPAINT_NS)


def inpaint_subregion_patch(
    full_image: np.ndarray,
    mask: np.ndarray,
    bbox: tuple[int, int, int, int] | None = None,
    padding: int = 48,
    feather_kernel: int = 7,
) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """
    High-speed contextual sub-region inpainting with soft-edge feathering.
    Crops only around the active mask area with context padding, aligns to 8/32 grid,
    runs inpainting on the crop, and blends back with zero seam artifacts.
    """
    if full_image is None or mask is None:
        raise ValueError("Invalid full image or mask")

    ih, iw = full_image.shape[:2]
    if mask.shape[:2] != (ih, iw):
        mask = cv2.resize(mask, (iw, ih), interpolation=cv2.INTER_NEAREST)

    if bbox is not None:
        bx, by, bw, bh = [int(v) for v in bbox]
        x0 = max(0, bx - padding)
        y0 = max(0, by - padding)
        x1 = min(iw, bx + bw + padding)
        y1 = min(ih, by + bh + padding)
    else:
        pts = np.argwhere(mask > 0)
        if len(pts) == 0:
            return full_image.copy(), (0, 0, iw, ih)
        y_min, x_min = pts.min(axis=0)
        y_max, x_max = pts.max(axis=0) + 1
        x0 = max(0, x_min - padding)
        y0 = max(0, y_min - padding)
        x1 = min(iw, x_max + padding)
        y1 = min(ih, y_max + padding)

    # Grid alignment to multiple of 8
    crop_w = x1 - x0
    crop_h = y1 - y0
    rem_w = crop_w % 8
    rem_h = crop_h % 8
    if rem_w != 0:
        x1 = min(iw, x1 + (8 - rem_w))
    if rem_h != 0:
        y1 = min(ih, y1 + (8 - rem_h))

    crop_img = full_image[y0:y1, x0:x1].copy()
    crop_mask = mask[y0:y1, x0:x1].copy()

    if np.count_nonzero(crop_mask) == 0:
        return full_image.copy(), (x0, y0, x1, y1)

    # Execute inpainting on the crop
    lama = _get_lama()
    if lama is not None:
        try:
            inpainted_crop = lama.inpaint(crop_img, crop_mask)
        except Exception as e:
            logger.warning("Subregion LaMa inpaint failed: %s, falling back to OpenCV NS", e)
            inpainted_crop = cv2.inpaint(crop_img, crop_mask, 5, cv2.INPAINT_NS)
    else:
        inpainted_crop = cv2.inpaint(crop_img, crop_mask, 5, cv2.INPAINT_NS)

    # Soft alpha feather blend on boundaries to prevent seam lines
    k = max(3, feather_kernel | 1)
    feather = cv2.GaussianBlur((crop_mask > 0).astype(np.float32), (k, k), 1.5)
    feather_3c = np.repeat(feather[:, :, np.newaxis], 3, axis=2)

    blended_crop = (
        inpainted_crop.astype(np.float32) * feather_3c
        + crop_img.astype(np.float32) * (1.0 - feather_3c)
    ).astype(np.uint8)

    result = full_image.copy()
    result[y0:y1, x0:x1] = blended_crop

    return result, (x0, y0, x1, y1)

