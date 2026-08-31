import json
import subprocess
import tempfile
import os
import logging
import uuid
import datetime
import hashlib
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from app.config import PSD_CLI_PATH
from app.models.all_models import Page, TextBlock
from app.services.font_registry import font_registry
from app.services.browser_render import browser_overlay_path, browser_render_is_fresh
from app.services.project_paths import project_export_path, rendered_asset_path
from app.services.renderer import render_page_text
from app.services.typesetting import (
    compute_block_typesetting,
    validate_typesetting_spec,
    get_effective_typesetting_spec,
    persist_typesetting_spec,
)

logger = logging.getLogger("houmi-psd-export")


def export_page_to_psd(
    page_id: str,
    db: Session,
    force: bool = False,
    text_mode: str = "point",
    embed_overlay: bool = True,
) -> Path:
    """
    Exports a manga page to PSD format with editable text layers
    by spawning the Rust standalone manga-psd-cli tool.
    """
    text_mode = str(text_mode or "point").strip().lower()
    if text_mode not in {"paragraph", "point"}:
        raise ValueError("text_mode must be 'paragraph' or 'point'")

    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise ValueError("Page not found")

    # 1. Enforce export preflight policy
    blocked_blocks = []
    block_specs = {}

    for block in page.text_blocks:
        # Use translation if present; fallback to source_text so text layers are included in PSD even before translation
        text_val = (block.translation or block.source_text or "").strip()
        if not text_val:
            continue

        # Get or recompute valid spec (do not persist yet)
        spec = get_effective_typesetting_spec(block)
        is_stale = not validate_typesetting_spec(block, spec)
        if is_stale:
            spec = compute_block_typesetting(block)

        block_specs[block.id] = spec

        has_error = spec.overflow or any(w.severity == "error" for w in spec.warnings)
        # NEEDS_REVIEW with font issues also blocks quiet export
        if getattr(spec, "decision_status", None) == "NEEDS_REVIEW":
            codes = set(getattr(spec, "reason_codes", None) or [])
            if codes & {"FONT_FALLBACK", "FONT_UNAVAILABLE", "TEXT_OVERFLOW"}:
                has_error = True
        # Font availability preflight — never silent fallback into PSD
        style_name = str(spec.resolved_font_style or "regular").lower()
        use_bold = bool(getattr(spec, "bold", False)) or ("bold" in style_name)
        use_italic = bool(getattr(spec, "italic", False)) or ("italic" in style_name)
        pre_font = font_registry.resolve_font(
            spec.resolved_postscript_name or spec.resolved_font_family,
            bold=use_bold,
            italic=use_italic,
        )
        if getattr(pre_font, "is_fallback", False) and pre_font.family.lower() != str(spec.resolved_font_family or "").lower():
            has_error = True
        if has_error:
            blocked_blocks.append(block.id)

    if blocked_blocks and not force:
        raise ValueError(
            f"EXPORT_BLOCKED: The following blocks have overflow, font, or error warnings: {', '.join(blocked_blocks)}. "
            f"Pass force=True to export anyway."
        )

    # Generate page-level export_id
    export_id = str(uuid.uuid4())

    # 2. Gather text blocks data for CLI manifest
    text_blocks_data = []
    snapshots_to_write = {}

    for block in page.text_blocks:
        if block.id not in block_specs:
            continue
        spec = block_specs[block.id]

        # Semantic parity: color / align / direction / rotation come from Spec v2
        # — never re-derive layout from live block fields at export time.
        hex_color = (getattr(spec, "color_hex", None) or block.color_hex or "#000000").lstrip("#")
        r = int(hex_color[0:2], 16) if len(hex_color) >= 2 else 0
        g = int(hex_color[2:4], 16) if len(hex_color) >= 4 else 0
        b = int(hex_color[4:6], 16) if len(hex_color) >= 6 else 0

        style_name = str(spec.resolved_font_style or "regular").lower()
        use_bold = bool(getattr(spec, "bold", False)) or ("bold" in style_name)
        use_italic = bool(getattr(spec, "italic", False)) or ("italic" in style_name)
        resolved_font = font_registry.resolve_font(
            spec.resolved_postscript_name or spec.resolved_font_family,
            bold=use_bold,
            italic=use_italic,
        )
        if (
            spec.font_fingerprint
            and resolved_font.fingerprint != spec.font_fingerprint
        ):
            logger.warning(
                "Font fingerprint mismatch block %s spec=%s loaded=%s",
                block.id,
                spec.font_fingerprint,
                resolved_font.fingerprint,
            )

        resolved_font_family = resolved_font.postscript_name
        resolved_style = str(spec.resolved_font_style or resolved_font.style or "regular").lower()
        font_weight = getattr(resolved_font, "weight", 400)
        # Strictly prevent double bolding: only apply faux bold if the resolved font is not a native bold variant
        faux_bold = bool(use_bold and "bold" not in resolved_style and font_weight < 600)
        faux_italic = bool(use_italic and "italic" not in resolved_style and getattr(resolved_font, "css_style", "normal") != "italic")
        text_val = (block.translation or block.source_text or "").strip()
        non_empty_lines = [l for l in (spec.explicit_lines or []) if l.strip()]
        text_val_lines = "\n".join(non_empty_lines) if non_empty_lines else text_val
        align = getattr(spec, "text_align", None) or spec.horizontal_align or "center"
        direction = getattr(spec, "writing_direction", None) or block.text_direction or "horizontal"
        rotation = float(getattr(spec, "rotation_deg", None) if getattr(spec, "rotation_deg", None) is not None else (block.rotation_deg or 0.0))
        # Keep Photoshop's editable text area identical to the canonical renderer.
        # Padding is part of TypesettingSpec (and affects both fitting and glyph
        # placement); dropping it here makes the PSD reflow text against the full
        # balloon bounds and is the main source of the post-export size/position
        # drift users see before pressing Transform in Photoshop.
        padding = getattr(spec, "padding", None)
        if hasattr(padding, "model_dump"):
            padding = padding.model_dump()
        padding = padding or {}

        text_blocks_data.append(
            {
                "id": block.id,
                "x": spec.layout_region.x,
                "y": spec.layout_region.y,
                "width": spec.layout_region.width,
                "height": spec.layout_region.height,
                "rotation_deg": rotation,
                "translation": text_val_lines,
                "direction": direction,
                "style": {
                    "font_families": [resolved_font_family],
                    "font_size": spec.font_size,
                    "font_weight": font_weight,
                    "color": [r, g, b, 255],
                    "bold": faux_bold,
                    "italic": faux_italic,
                    "anti_alias": getattr(spec, "anti_alias", "sharp") or "sharp",
                    "align": align,
                    "vertical_align": getattr(spec, "vertical_align", "center") or "center",
                    "stroke_width": float(getattr(spec, "stroke_width", 0) or 0),
                    "stroke_color": getattr(spec, "stroke_color", "#ffffff"),
                    "glow_enabled": bool(
                        getattr(spec, "outline_glow_enabled", False)
                        or (getattr(spec, "outer_glow", None) and getattr(spec.outer_glow, "enabled", False))
                    ),
                    "glow_radius": float(
                        getattr(getattr(spec, "outer_glow", None), "size", getattr(spec, "outline_glow_radius", 0)) or 0
                    ),
                    "glow_color": getattr(getattr(spec, "outer_glow", None), "color", getattr(spec, "outline_glow_color", "#ffffff")),
                    "drop_shadow": (
                        spec.drop_shadow.model_dump()
                        if getattr(spec, "drop_shadow", None) is not None
                        else {"enabled": False}
                    ),
                    "inner_shadow": (
                        spec.inner_shadow.model_dump()
                        if getattr(spec, "inner_shadow", None) is not None
                        else {"enabled": False}
                    ),
                    "outer_glow": (
                        spec.outer_glow.model_dump()
                        if getattr(spec, "outer_glow", None) is not None
                        else {"enabled": False}
                    ),
                    "line_height": float(spec.line_height),
                    "tracking": float(getattr(spec, "tracking", 0) or 0),
                    "padding": {
                        "top": float(padding.get("top", 0) or 0),
                        "right": float(padding.get("right", 0) or 0),
                        "bottom": float(padding.get("bottom", 0) or 0),
                        "left": float(padding.get("left", 0) or 0),
                    },
                    "gradient": (
                        spec.gradient.model_dump()
                        if getattr(spec, "gradient", None) is not None
                        else {"enabled": False}
                    ),
                    "render_fingerprint": getattr(spec, "render_fingerprint", ""),
                    "schema_version": spec.schema_version,
                    # Paragraph text is the stable balloon master. Point mode
                    # is opt-in for users who want free positioning in Photoshop.
                    # Both values are sent explicitly because the Rust CLI
                    # otherwise defaults to point text for legacy manifests.
                    "text_type": text_mode,
                    "is_point_text": text_mode == "point",
                },
                "text_type": text_mode,
                "is_point_text": text_mode == "point",
            }
        )

    # Prepare input image paths
    source_img = Path(page.source_image_path)
    page_dir = source_img.parent

    from app.services.project_paths import inpainted_asset_path
    from app.services.inpainter import clean_page_text

    inpainted_img = inpainted_asset_path(page)
    if not inpainted_img.exists() and page.inpainted_image_path:
        inpainted_img = Path(page.inpainted_image_path)
    if not inpainted_img.exists():
        p_alt = page_dir / "inpainted.png"
        if p_alt.exists():
            inpainted_img = p_alt
    if not inpainted_img.exists():
        try:
            inpainted_img = Path(clean_page_text(page.id, db))
        except Exception as e:
            logger.warning("Auto clean_page_text failed for page %s: %s", page.id, e)

    # Prefer the canonical Fabric composite so the PSD preview matches Houmi's
    # editor. Pillow remains a headless fallback when no fresh browser capture
    # exists yet.
    rendered_img = rendered_asset_path(page)
    browser_render_fresh = browser_render_is_fresh(page)
    if not browser_render_fresh and source_img.exists():
        rendered_img = Path(render_page_text(page.id, db, persist=False))
    rendered_overlay = (
        browser_overlay_path(page) if (embed_overlay and browser_render_fresh) else None
    )

    # 3. Build JSON Manifest
    manifest_data = {
        "width": page.width,
        "height": page.height,
        "export_id": export_id,
        "source_image": str(source_img),
        "inpainted_image": str(inpainted_img) if inpainted_img.exists() else None,
        "rendered_image": str(rendered_img) if rendered_img.exists() else None,
        "rendered_overlay_image": (
            str(rendered_overlay) if rendered_overlay and rendered_overlay.exists() else None
        ),
        "text_blocks": text_blocks_data,
    }

    # Write temporary JSON manifest file
    temp_fd, temp_path_str = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, ensure_ascii=False, indent=2)

        # Output PSD path
        project = getattr(page, "project", None)
        if project is not None:
            from app.services.project_paths import project_workspace_dir
            psd_dir = project_workspace_dir(project) / "psd"
            psd_dir.mkdir(parents=True, exist_ok=True)
            psd_output_path = psd_dir / f"page_{page.page_number:03d}.psd"
        else:
            psd_output_path = page_dir / f"page_{page.page_number:03d}.psd"

        # Determine PSD Export Engine (JSX for native Photoshop Layer Effects vs Rust CLI)
        project_settings = getattr(project, "settings", {}) if project is not None else {}
        export_engine = str(project_settings.get("psd_export_engine", "rust")).lower()
        photoshop_custom_path = project_settings.get("photoshop_path")
        jsx_succeeded = False

        if export_engine in {"jsx", "photoshop"}:
            from app.services.jsx_export import export_psd_via_jsx, find_photoshop_executable
            ps_exe = find_photoshop_executable(photoshop_custom_path)
            if ps_exe:
                logger.info(f"Using JSX Export Engine with Photoshop at {ps_exe}")
                jsx_succeeded = export_psd_via_jsx(Path(temp_path_str), psd_output_path, ps_exe)
                if not jsx_succeeded:
                    logger.warning("JSX export failed, falling back to Rust CLI engine...")

        if not jsx_succeeded:
            # Resolve PSD CLI executable with fallback candidate paths
            import sys
            cli_candidates = [
                PSD_CLI_PATH,
                Path(sys.executable).parent / "bin" / "houmi-psd-cli.exe",
                Path(sys.executable).parent / "_internal" / "bin" / "houmi-psd-cli.exe",
                Path(sys.executable).parent / "houmi-psd-cli.exe",
                Path(sys.executable).parent / "_internal" / "houmi-psd-cli.exe",
                Path(sys.executable).parent / "bin" / "manga-psd-cli.exe",
                Path(sys.executable).parent / "_internal" / "bin" / "manga-psd-cli.exe",
                Path(sys.executable).parent / "manga-psd-cli.exe",
                Path(sys.executable).parent / "_internal" / "manga-psd-cli.exe",
            ]
            actual_cli_path = None
            for candidate in cli_candidates:
                if candidate and candidate.exists():
                    actual_cli_path = candidate
                    break

            if not actual_cli_path:
                raise FileNotFoundError(
                    f"manga-psd-cli binary not found at {PSD_CLI_PATH}. Build or install it first!"
                )

            logger.info(
                f"Invoking PSD CLI: {actual_cli_path} --manifest {temp_path_str} --output {psd_output_path}"
            )

            result = subprocess.run(
                [
                    str(actual_cli_path),
                    "--manifest",
                    temp_path_str,
                    "--output",
                    str(psd_output_path),
                ],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

            if result.returncode != 0:
                logger.error(f"PSD CLI error (exit {result.returncode}): {result.stderr}")
                raise RuntimeError(f"Rust PSD CLI failed: {result.stderr}")

        # 4. Compute PSD file hash and write snapshots/specs on CLI success
        logger.info(f"PSD CLI succeeded. Computing hash for {psd_output_path}...")
        sha256 = hashlib.sha256()
        with open(psd_output_path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                sha256.update(chunk)
        psd_hash = sha256.hexdigest()

        for block in page.text_blocks:
            if block.id not in block_specs:
                continue
            spec = block_specs[block.id]

            # Break coordinates are emitted by the layout engine. Never infer them
            # from the rendered text because repeated characters make that ambiguous.
            break_provenance = spec.metrics.get("break_provenance", [])
            auto_breaks = [
                item["char_offset"]
                for item in break_provenance
                if item.get("break_kind") == "automatic"
                and isinstance(item.get("char_offset"), int)
            ]
            authored_breaks = [
                item["char_offset"]
                for item in break_provenance
                if item.get("break_kind") == "authored"
                and isinstance(item.get("char_offset"), int)
            ]

            snapshot = {
                "export_id": export_id,
                "export_timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "original_authored_text": block.translation,
                "normalized_text": spec.normalized_text,
                "exported_text": "\n".join(spec.explicit_lines),
                "explicit_lines": spec.explicit_lines,
                "auto_break_offsets": auto_breaks,
                "authored_newline_offsets": authored_breaks,
                "source_signature": spec.source_signature,
                "schema_version": spec.schema_version,
                "layout_version": spec.layout_version,
                "export_version": "1.2.0",
                "text_mode": text_mode,
                "psd_geometry_version": "2",
                "resolved_font_family": spec.resolved_font_family,
                "resolved_font_style": spec.resolved_font_style,
                "font_fingerprint": spec.font_fingerprint,
                "psd_file_hash": psd_hash,
                "break_provenance": break_provenance,
                "padding": (
                    spec.padding.model_dump()
                    if hasattr(spec.padding, "model_dump")
                    else (spec.padding or {})
                ),
            }

            if not block.extra_metadata:
                block.extra_metadata = {}

            # Save the spec
            persist_typesetting_spec(block, spec)
            # Save the latest snapshot
            block.extra_metadata["psd_export_snapshot"] = snapshot

            # Append to history dict
            history = block.extra_metadata.get("psd_export_history", {})
            history[export_id] = snapshot
            if len(history) > 3:
                sorted_keys = sorted(
                    history.keys(), key=lambda k: history[k].get("export_timestamp", "")
                )
                while len(history) > 3:
                    history.pop(sorted_keys.pop(0))
            block.extra_metadata["psd_export_history"] = history

            flag_modified(block, "extra_metadata")

        if len(block_specs) > 0:
            db.commit()

        # Automatically shoot JSX script into Photoshop if Photoshop is active
        _shoot_photoshop_jsx_script(psd_output_path)

        logger.info(
            f"Successfully generated PSD file and committed snapshots: {psd_output_path}"
        )
        return psd_output_path

    finally:
        # Cleanup temp JSON manifest
        if os.path.exists(temp_path_str):
            try:
                os.remove(temp_path_str)
            except Exception:
                pass


def _shoot_photoshop_jsx_script(psd_path: Path):
    """
    Directly shoots/executes JSX script into Photoshop (via COM if Photoshop is running)
    to apply Adobe World-Ready Composer & text engine layout fixes automatically.
    """
    if "PYTEST_CURRENT_TEST" in os.environ or os.environ.get("SKIP_PHOTOSHOP_COM") == "1":
        return

    try:
        import win32com.client
        import pythoncom
        pythoncom.CoInitialize()
        ps = win32com.client.GetActiveObject("Photoshop.Application")
        doc = ps.Open(str(psd_path))

        jsx_code = """
        (function() {
            var doc = app.activeDocument;
            for (var i = 0; i < doc.layers.length; i++) {
                var layer = doc.layers[i];
                if (layer.kind === LayerKind.TEXT) {
                    try {
                        layer.textItem.autoLeading = true;
                        layer.textItem.useFractionalLineWidths = true;
                    } catch(e) {}
                    try {
                        var idsetd = charIDToTypeID("setd");
                        var desc1 = new ActionDescriptor();
                        var ref1 = new ActionReference();
                        ref1.putEnumerated(charIDToTypeID("TxLr"), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
                        desc1.putReference(charIDToTypeID("null"), ref1);
                        var descText = new ActionDescriptor();
                        descText.putInteger(stringIDToTypeID("composer"), 2);
                        desc1.putObject(charIDToTypeID("to  "), charIDToTypeID("TxLr"), descText);
                        executeAction(idsetd, desc1, DialogModes.NO);
                    } catch(e) {}
                }
            }
        })();
        """
        ps.DoJavaScript(jsx_code)
        doc.Save()
        doc.Close(2)
        logger.info(f"Direct Photoshop JSX script shot successfully into: {psd_path.name}")
    except Exception as e:
        logger.debug(f"Direct Photoshop JSX script trigger skipped: {e}")

