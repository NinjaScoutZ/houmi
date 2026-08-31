import re
import logging
import difflib
import math
from copy import deepcopy
from pathlib import Path
from sqlalchemy.orm import Session
from psd_tools import PSDImage
from app.models.all_models import Page, TextBlock
from app.services.typesetting import compute_block_typesetting

logger = logging.getLogger("houmi-psd-import")


def _number(value, default: float = 0.0) -> float:
    if hasattr(value, "value"):
        value = value.value
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _photoshop_text_geometry(layer, snapshot: dict) -> dict | None:
    """Read Photoshop paragraph-text geometry instead of its raster glyph bbox."""
    if snapshot.get("psd_geometry_version") != "2":
        return None
    try:
        engine = layer.engine_dict
        children = engine.get("Rendered", {}).get("Shapes", {}).get("Children", [])
        photoshop = children[0].get("Cookie", {}).get("Photoshop", {})
        bounds = photoshop.get("BoxBounds")
        transform = list(layer.transform)
    except (AttributeError, IndexError, KeyError, TypeError):
        return None

    if not bounds or len(bounds) != 4 or len(transform) != 6:
        return None

    left, top, right, bottom = (_number(value) for value in bounds)
    xx, xy, yx, yy, tx, ty = (_number(value) for value in transform)
    scale_x = math.hypot(xx, xy)
    scale_y = math.hypot(yx, yy)
    if right <= left or bottom <= top or scale_x <= 0 or scale_y <= 0:
        return None

    padding_raw = snapshot.get("padding") or {}
    padding_right = max(0.0, _number(padding_raw.get("right")))
    padding_bottom = max(0.0, _number(padding_raw.get("bottom")))

    # Exported BoxBounds keeps its right/bottom edges at the canonical inner
    # region. Adding the matching trailing padding reconstructs the outer
    # balloon, while transform carries document placement/rotation/scale.
    local_width = right + padding_right
    local_height = bottom + padding_bottom
    document_center_x = tx + xx * local_width / 2.0 + yx * local_height / 2.0
    document_center_y = ty + xy * local_width / 2.0 + yy * local_height / 2.0
    width = local_width * scale_x
    height = local_height * scale_y
    return {
        "x": document_center_x - width / 2.0,
        "y": document_center_y - height / 2.0,
        "width": width,
        "height": height,
        "rotation_deg": math.degrees(math.atan2(xy, xx)),
    }


def _abort_import(db: Session, message: str) -> None:
    db.rollback()
    raise ValueError(f"IMPORT_FAILED: {message}")


def remove_auto_breaks_with_snapshot(snapshot: dict, imported_text: str) -> str:
    """
    Cleans up imported text using the explicit auto-break offsets saved during export.
    This resolves repeated-character mapping issues deterministically.
    """
    original_text = snapshot.get("original_authored_text", "")
    exported_text = snapshot.get("exported_text", "")

    bp_list = snapshot.get("break_provenance")
    if bp_list:
        auto_break_offsets = [
            bp.get("char_offset")
            for bp in bp_list
            if isinstance(bp, dict) and bp.get("break_kind") == "automatic"
        ]
    else:
        auto_break_offsets = snapshot.get("auto_break_offsets", [])

    if not exported_text:
        return imported_text

    if imported_text == exported_text:
        return original_text

    matcher = difflib.SequenceMatcher(None, exported_text, imported_text)
    imported_flags = [0] * len(imported_text)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                exp_idx = i1 + offset
                imp_idx = j1 + offset
                if exp_idx in auto_break_offsets:
                    imported_flags[imp_idx] = 1

    cjk_thai = re.compile(
        r"[\u4e00-\u9fff\u3040-\u30ff\u31f0-\u31ff\u30a0-\u30ff\uff00-\uffef\u0e00-\u0e7f]"
    )
    result = []
    for k, char in enumerate(imported_text):
        if char == "\n" and k < len(imported_flags) and imported_flags[k] == 1:
            prev_char = ""
            next_char = ""
            for p in range(k - 1, -1, -1):
                if not imported_text[p].isspace():
                    prev_char = imported_text[p]
                    break
            for n in range(k + 1, len(imported_text)):
                if not imported_text[n].isspace():
                    next_char = imported_text[n]
                    break

            if prev_char and next_char:
                if cjk_thai.search(prev_char) and cjk_thai.search(next_char):
                    continue
                else:
                    result.append(" ")
            else:
                result.append(" ")
        else:
            result.append(char)

    return "".join(result)


def remove_auto_breaks(old_text: str, exported_text: str, imported_text: str) -> str:
    """
    Legacy fallback: cleans up imported text by removing auto-wrapped breaks while preserving manual ones.
    """
    if not old_text:
        return imported_text
    if not exported_text:
        exported_text = old_text

    matcher = difflib.SequenceMatcher(None, old_text, exported_text)
    exported_flags = [0] * len(exported_text)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "insert":
            for j in range(j1, j2):
                if exported_text[j] == "\n":
                    exported_flags[j] = 1
        elif tag == "replace":
            for j in range(j1, j2):
                if exported_text[j] == "\n":
                    exported_flags[j] = 1

    matcher2 = difflib.SequenceMatcher(None, exported_text, imported_text)
    imported_flags = [0] * len(imported_text)

    for tag, i1, i2, j1, j2 in matcher2.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                imported_flags[j1 + offset] = exported_flags[i1 + offset]

    cjk_thai = re.compile(
        r"[\u4e00-\u9fff\u3040-\u30ff\u31f0-\u31ff\u30a0-\u30ff\uff00-\uffef\u0e00-\u0e7f]"
    )
    result = []
    for k, char in enumerate(imported_text):
        if char == "\n" and k < len(imported_flags) and imported_flags[k] == 1:
            prev_char = ""
            next_char = ""
            for p in range(k - 1, -1, -1):
                if not imported_text[p].isspace():
                    prev_char = imported_text[p]
                    break
            for n in range(k + 1, len(imported_text)):
                if not imported_text[n].isspace():
                    next_char = imported_text[n]
                    break

            if prev_char and next_char:
                if cjk_thai.search(prev_char) and cjk_thai.search(next_char):
                    continue
                else:
                    result.append(" ")
            else:
                result.append(" ")
        else:
            result.append(char)

    return "".join(result)


def import_psd_to_page(page_id: str, psd_path: str, db: Session) -> dict:
    """
    Reads modified PSD file, extracts text content & positions from Photoshop text layers,
    matches them by Layer Name Unique ID, and updates SQLite DB.

    Implemented as a strict two-pass process to achieve atomicity:
    - Pass 1: Parse and validate all layers, export identity, snapshots, and check for duplicates.
    - Pass 2: Apply mutations and recompute typesetting specs, then save.
    """
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise ValueError("Page not found")

    psd_file = Path(psd_path)
    if not psd_file.exists():
        raise FileNotFoundError(f"PSD file not found at {psd_path}")

    logger.info(f"Opening PSD for reverse import: {psd_path}")
    psd = PSDImage.open(psd_path)

    block_map = {block.id: block for block in page.text_blocks}

    id_pattern = re.compile(
        r"(?:blk-)?([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})",
        re.IGNORECASE,
    )

    # Pass 1: Parse and Validate
    found_export_ids = set()
    layer_targets = []
    seen_block_ids = set()

    def scan_layers_validation(layer_group):
        for layer in layer_group:
            if layer.is_group():
                scan_layers_validation(layer)
                continue

            if layer.kind == "type":
                layer_name = layer.name or ""
                # Photoshop documents can contain unrelated text layers. Only
                # Houmi-managed layers participate in the import transaction.
                if not layer_name.startswith("TL "):
                    continue

                # Extract export_id first
                exp_match = re.search(
                    r"exp_v1:([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})",
                    layer_name,
                    re.IGNORECASE,
                )
                if not exp_match:
                    _abort_import(
                        db,
                        f"Managed text layer '{layer_name}' is missing a valid exp_v1 export identity",
                    )
                found_export_ids.add(exp_match.group(1).lower())

                # Strip export_id to avoid block_id extraction mismatch
                clean_name = re.sub(
                    r"exp_v1:[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
                    "",
                    layer_name,
                    flags=re.IGNORECASE,
                )

                match = id_pattern.search(clean_name)
                if not match:
                    _abort_import(
                        db,
                        f"Managed text layer '{layer_name}' is missing a valid block ID",
                    )

                full_match_id = match.group(0)
                captured_uuid = match.group(1)

                block = block_map.get(captured_uuid) or block_map.get(full_match_id)
                if not block:
                    _abort_import(
                        db,
                        f"Block ID in managed layer '{layer_name}' does not belong to page {page_id}",
                    )

                if block.id in seen_block_ids:
                    _abort_import(
                        db, f"Duplicate text layers found for block {block.id}"
                    )
                seen_block_ids.add(block.id)

                layer_targets.append((layer, block))

    scan_layers_validation(psd)

    # Enforce identity validation policy (fail closed)
    if not found_export_ids:
        _abort_import(
            db,
            "Missing persistent export identity (export_id) in PSD layers. The file was not exported by a compatible version.",
        )
    if len(found_export_ids) > 1:
        _abort_import(
            db,
            f"Multiple conflicting export IDs found in PSD layers: {found_export_ids}",
        )

    psd_export_id = list(found_export_ids)[0]

    # Resolve all snapshots before mutating any ORM entities
    updates_payload = []
    for layer, block in layer_targets:
        text_content = layer.text.replace("\r", "\n") if layer.text else ""

        snapshot = None
        if block.extra_metadata:
            history = block.extra_metadata.get("psd_export_history", {})
            snapshot = history.get(psd_export_id)

        if not snapshot:
            _abort_import(
                db,
                f"Export identity '{psd_export_id}' was evicted from history or does not belong to block {block.id}",
            )

        updates_payload.append((layer, block, snapshot, text_content))

    # Pass 2: Apply mutations and recompute specs
    from sqlalchemy.orm.attributes import flag_modified

    updates = []
    originals = {
        block.id: {
            "translation": block.translation,
            "x": block.x,
            "y": block.y,
            "width": block.width,
            "height": block.height,
            "rotation_deg": block.rotation_deg,
            "extra_metadata": deepcopy(block.extra_metadata),
        }
        for _, block, _, _ in updates_payload
    }

    try:
        for layer, block, snapshot, text_content in updates_payload:
            text_to_save = remove_auto_breaks_with_snapshot(snapshot, text_content)
            old_text = snapshot.get("original_authored_text", "")

            text_geometry = _photoshop_text_geometry(layer, snapshot)
            bbox = layer.bbox
            if text_geometry:
                left = text_geometry["x"]
                top = text_geometry["y"]
                width = text_geometry["width"]
                height = text_geometry["height"]
                rotation = text_geometry["rotation_deg"]
            elif bbox and len(bbox) >= 4:
                left = float(bbox[0])
                top = float(bbox[1])
                width = float(bbox[2] - bbox[0])
                height = float(bbox[3] - bbox[1])
                rotation = float(block.rotation_deg or 0.0)
            else:
                left = block.x
                top = block.y
                width = block.width
                height = block.height
                rotation = float(block.rotation_deg or 0.0)

            block.translation = text_to_save
            block.rotation_deg = rotation
            metadata = dict(block.extra_metadata or {})
            metadata["layout_region"] = {
                **dict(metadata.get("layout_region") or {}),
                "x": left,
                "y": top,
                "width": width,
                "height": height,
                "shape": block.balloon_type or "bubble",
                "confidence": 1.0,
                "source": "manual",
                "safe_margin": float((metadata.get("layout_region") or {}).get("safe_margin", 0.0)),
                "reason": "psd_imported",
                "version": "1.0.0",
            }
            block.extra_metadata = metadata

            spec = compute_block_typesetting(block)
            from app.services.typesetting import persist_typesetting_spec
            persist_typesetting_spec(block, spec, reset_suggestion=True)
            flag_modified(block, "extra_metadata")

            updates.append(
                {
                    "id": block.id,
                    "old_translation": old_text,
                    "new_translation": text_to_save,
                    "x": left,
                    "y": top,
                    "width": width,
                    "height": height,
                    "rotation_deg": rotation,
                    "typesetting_spec": block.extra_metadata.get("typesetting_spec"),
                }
            )

        if updates:
            db.commit()
    except Exception as exc:
        db.rollback()
        for _, block, _, _ in updates_payload:
            original = originals[block.id]
            block.translation = original["translation"]
            block.x = original["x"]
            block.y = original["y"]
            block.width = original["width"]
            block.height = original["height"]
            block.rotation_deg = original["rotation_deg"]
            block.extra_metadata = original["extra_metadata"]
        raise ValueError(
            f"IMPORT_FAILED: Could not apply PSD import atomically: {exc}"
        ) from exc

    if updates:
        from app.services.project_serializer import save_project_json

        save_project_json(page.project_id, db)
        logger.info(f"Reverse import complete. Updated {len(updates)} blocks.")

    return {"success": True, "updated_blocks": updates, "errors": []}
