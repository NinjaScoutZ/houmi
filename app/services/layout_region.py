import logging
import os
from pathlib import Path
from typing import Any, Mapping

import cv2
import numpy as np


logger = logging.getLogger("houmi-layout-region")
LAYOUT_REGION_VERSION = "1.0.0"
TRANSLATION_LAYOUT_POLICY_VERSION = 2


def _box_from(value: Any) -> tuple[float, float, float, float]:
    if isinstance(value, Mapping):
        return (
            float(value.get("x", 0.0)),
            float(value.get("y", 0.0)),
            float(value.get("width", 0.0)),
            float(value.get("height", 0.0)),
        )
    return (
        float(getattr(value, "x", 0.0)),
        float(getattr(value, "y", 0.0)),
        float(getattr(value, "width", 0.0)),
        float(getattr(value, "height", 0.0)),
    )


def _fallback_region(value: Any, reason: str = "not_analyzed", enable_smart: bool = True) -> dict[str, Any]:
    sx = getattr(value, "smart_x", None) if not isinstance(value, Mapping) else value.get("smart_x")
    sy = getattr(value, "smart_y", None) if not isinstance(value, Mapping) else value.get("smart_y")
    sw = getattr(value, "smart_width", None) if not isinstance(value, Mapping) else value.get("smart_width")
    sh = getattr(value, "smart_height", None) if not isinstance(value, Mapping) else value.get("smart_height")
    
    if enable_smart and sx is not None and sw is not None and float(sw) > 10.0 and float(sh) > 10.0:
        x, y, width, height = float(sx), float(sy), float(sw), float(sh)
        source_type = "smart_balloon"
    else:
        x, y, width, height = _box_from(value)
        source_type = "fallback_bbox"

    return {
        "x": x,
        "y": y,
        "width": max(1.0, width),
        "height": max(1.0, height),
        "shape": getattr(value, "balloon_type", None)
        or (value.get("balloon_type") if isinstance(value, Mapping) else None)
        or "bubble",
        "confidence": 0.9 if source_type == "smart_balloon" else 0.0,
        "source": source_type,
        "safe_margin": 0.0,
        "reason": reason,
        "version": LAYOUT_REGION_VERSION,
    }


def _detector_bbox_region(image: np.ndarray, value: Any, reason: str) -> dict[str, Any]:
    """Use a conservative inset of the detector box when a balloon edge is visible."""
    fallback = _fallback_region(value, reason)
    image_h, image_w = image.shape[:2]
    x, y, width, height = _box_from(value)
    x0 = max(0, int(np.floor(x)))
    y0 = max(0, int(np.floor(y)))
    x1 = min(image_w, int(np.ceil(x + width)))
    y1 = min(image_h, int(np.ceil(y + height)))
    crop = image[y0:y1, x0:x1]
    if crop.size == 0:
        return fallback
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    edges = cv2.Canny(gray, 60, 160)
    band = max(2, int(round(min(crop.shape[:2]) * 0.12)))
    outer = np.zeros_like(edges, dtype=bool)
    outer[:band, :] = True
    outer[-band:, :] = True
    outer[:, :band] = True
    outer[:, -band:] = True
    edge_density = float(np.count_nonzero(edges[outer])) / max(1, int(np.count_nonzero(outer)))
    if edge_density < 0.018:
        return fallback
    return {
        **fallback,
        "x": x,
        "y": y,
        "width": max(4.0, width),
        "height": max(4.0, height),
        "confidence": round(min(0.78, 0.48 + edge_density * 2.0), 4),
        "source": "detector_bbox",
        "safe_margin": 0.0,
        "reason": reason,
        "source_bbox": {"x": x, "y": y, "width": width, "height": height},
    }



def get_effective_layout_region(block: Any, settings: dict | None = None) -> dict[str, Any]:
    """Return a validated absolute page-space layout region or the source bbox fallback."""
    from app.config import get_enable_smart_balloon

    enable_smart = get_enable_smart_balloon(settings)
    if enable_smart:
        sx = getattr(block, "smart_x", None) if not isinstance(block, Mapping) else block.get("smart_x")
        sy = getattr(block, "smart_y", None) if not isinstance(block, Mapping) else block.get("smart_y")
        sw = getattr(block, "smart_width", None) if not isinstance(block, Mapping) else block.get("smart_width")
        sh = getattr(block, "smart_height", None) if not isinstance(block, Mapping) else block.get("smart_height")
        if sx is not None and sw is not None and float(sw) > 10.0 and float(sh) > 10.0:
            return {
                "x": float(sx),
                "y": float(sy),
                "width": float(sw),
                "height": float(sh),
                "confidence": 0.95,
                "source": "smart_balloon",
                "shape": getattr(block, "balloon_type", None) or "bubble",
                "version": LAYOUT_REGION_VERSION,
            }

    metadata = getattr(block, "extra_metadata", None) or {}
    candidate = metadata.get("layout_region") if isinstance(metadata, Mapping) else None
    if isinstance(candidate, Mapping):
        source = str(candidate.get("source", "metadata"))
        if enable_smart or source not in {"smart_balloon", "smart_balloon_v15"}:
            try:
                x = float(candidate["x"])
                y = float(candidate["y"])
                width = float(candidate["width"])
                height = float(candidate["height"])
                if width >= 4.0 and height >= 4.0 and all(
                    np.isfinite(number) for number in (x, y, width, height)
                ):
                    return {
                        **candidate,
                        "x": x,
                        "y": y,
                        "width": width,
                        "height": height,
                        "confidence": max(0.0, min(1.0, float(candidate.get("confidence", 0.0)))),
                        "source": source,
                        "shape": str(candidate.get("shape", getattr(block, "balloon_type", "bubble"))),
                    }
            except (KeyError, TypeError, ValueError):
                pass
    return _fallback_region(block, reason="missing_or_invalid_metadata", enable_smart=enable_smart)


def analyze_layout_region(image: np.ndarray | None, block: Any) -> dict[str, Any]:
    """Extract layout region from pre-computed balloon mask if available."""
    metadata = dict(getattr(block, "extra_metadata", None) or {})
    mask_path = metadata.get("mask_path") or metadata.get("smart_balloon_mask")

    if not mask_path or not os.path.exists(str(mask_path)):
        block_id = getattr(block, "id", None)
        if block_id:
            possible_path = Path("masks") / f"mask_{block_id}.png"
            if possible_path.exists():
                mask_path = str(possible_path)

    if mask_path and os.path.exists(str(mask_path)):
        try:
            from app.utils.image_utils import cv2_imread_unicode
            mask = cv2_imread_unicode(mask_path, cv2.IMREAD_GRAYSCALE)
            if mask is not None and cv2.countNonZero(mask) > 0:
                nz = cv2.findNonZero(mask)
                x, y, w, h = cv2.boundingRect(nz)
                return {
                    "x": float(x),
                    "y": float(y),
                    "width": float(w),
                    "height": float(h),
                    "source": "precomputed_balloon_mask",
                    "confidence": 0.95,
                    "mask_path": str(mask_path),
                }
        except Exception as exc:
            logger.warning("Failed to load precomputed balloon mask: %s", exc)

    return _fallback_region(block, "text_bbox_passthrough")




def analyze_layout_region_file(image_path: str | Path, block: Any) -> dict[str, Any]:
    try:
        from app.utils.image_utils import cv2_imread_unicode
        image = cv2_imread_unicode(image_path)
    except Exception as exc:
        logger.warning("Failed to read image for layout region: %s", exc)
        image = None
    return analyze_layout_region(image, block)


def _apply_translation_box_policy(block: Any, detected_region: dict[str, Any]) -> dict[str, Any]:
    """Keep translated text inside the original detector box while retaining balloon context."""
    page = getattr(block, "page", None)
    project = getattr(page, "project", None)
    settings = getattr(project, "settings", None) or {}
    # OCR geometry is for recognition/masking; translated text should use the
    # detected balloon interior unless the user explicitly enables this legacy
    # compatibility option.
    if not bool(settings.get("lock_translation_to_detected_box", False)):
        return detected_region
    x, y, width, height = _box_from(block)
    metadata = dict(getattr(block, "extra_metadata", None) or {})
    metadata["balloon_context_region"] = detected_region
    locked = {
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "shape": detected_region.get("shape", getattr(block, "balloon_type", "bubble")),
        "confidence": detected_region.get("confidence", 0.0),
        "source": "locked_detector_box",
        "safe_margin": 0.0,
        "reason": "translation_box_locked",
        "version": LAYOUT_REGION_VERSION,
        "source_bbox": {"x": x, "y": y, "width": width, "height": height},
    }
    metadata["layout_region"] = locked
    block.extra_metadata = metadata
    return locked


def refresh_block_layout_region(block: Any) -> dict[str, Any]:
    page = getattr(block, "page", None)
    image_path = getattr(page, "source_image_path", None)
    region = analyze_layout_region_file(image_path, block) if image_path else _fallback_region(block, "page_unavailable")
    return _apply_translation_box_policy(block, region)


def _resolve_shared_layout_regions(blocks: list[Any], regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prevent two independent balloon layers from claiming the same bright component."""
    unsafe: set[int] = set()
    for index, region in enumerate(regions):
        if str(region.get("source")) in {"manual", "locked_detector_box"}:
            continue
        rx0, ry0 = float(region["x"]), float(region["y"])
        rx1, ry1 = rx0 + float(region["width"]), ry0 + float(region["height"])
        area = max(1.0, float(region["width"]) * float(region["height"]))
        for other_index in range(index + 1, len(regions)):
            other = regions[other_index]
            if str(other.get("source")) in {"manual", "locked_detector_box"}:
                continue
            ox0, oy0 = float(other["x"]), float(other["y"])
            ox1, oy1 = ox0 + float(other["width"]), oy0 + float(other["height"])
            overlap = max(0.0, min(rx1, ox1) - max(rx0, ox0)) * max(0.0, min(ry1, oy1) - max(ry0, oy0))
            other_area = max(1.0, float(other["width"]) * float(other["height"]))
            if overlap / min(area, other_area) >= 0.55:
                unsafe.update((index, other_index))

    for index in unsafe:
        block = blocks[index]
        x, y, width, height = _box_from(block)
        inset_x = width * 0.045
        inset_y = height * 0.055
        replacement = {
            **regions[index],
            "x": x + inset_x,
            "y": y + inset_y,
            "width": max(4.0, width - inset_x * 2),
            "height": max(4.0, height - inset_y * 2),
            "source": "overlap_safe_bbox",
            "confidence": min(0.72, float(regions[index].get("confidence", 0.0))),
            "safe_margin": round(min(inset_x, inset_y), 2),
            "reason": "shared_balloon_component",
            "source_bbox": {"x": x, "y": y, "width": width, "height": height},
        }
        regions[index] = replacement
        metadata = dict(getattr(block, "extra_metadata", None) or {})
        metadata["layout_region"] = replacement
        block.extra_metadata = metadata
    return regions


def refresh_block_layout_regions(blocks: list[Any]) -> list[dict[str, Any]]:
    """Analyze many blocks while decoding each page image only once."""
    image_cache: dict[str, np.ndarray | None] = {}
    regions: list[dict[str, Any]] = []
    for block in blocks:
        metadata = dict(getattr(block, "extra_metadata", None) or {})
        existing = metadata.get("layout_region")
        if isinstance(existing, Mapping) and existing.get("source") == "manual":
            regions.append(_apply_translation_box_policy(block, dict(existing)))
            continue
        page = getattr(block, "page", None)
        image_path = str(getattr(page, "source_image_path", "") or "")
        if image_path not in image_cache:
            try:
                from app.utils.image_utils import cv2_imread_unicode
                image_cache[image_path] = cv2_imread_unicode(image_path) if image_path else None
            except Exception as exc:
                logger.warning("Failed to read page image for layout regions: %s", exc)
                image_cache[image_path] = None
        detected_region = analyze_layout_region(image_cache[image_path], block)
        regions.append(_apply_translation_box_policy(block, detected_region))
    return _resolve_shared_layout_regions(blocks, regions)


def migrate_project_translation_layout_policy(project: Any) -> int:
    """Migrate legacy OCR-box text layouts to the saved balloon interior once."""
    settings = dict(getattr(project, "settings", None) or {})
    try:
        current_version = int(settings.get("translation_layout_policy_version", 0) or 0)
    except (TypeError, ValueError):
        current_version = 0
    if current_version >= TRANSLATION_LAYOUT_POLICY_VERSION:
        return 0

    settings["lock_translation_to_detected_box"] = False
    settings["translation_layout_policy_version"] = TRANSLATION_LAYOUT_POLICY_VERSION
    project.settings = settings

    affected: list[Any] = []
    for page in list(getattr(project, "pages", None) or []):
        needs_detection: list[Any] = []
        for block in list(getattr(page, "text_blocks", None) or []):
            metadata = dict(getattr(block, "extra_metadata", None) or {})
            existing = metadata.get("layout_region")
            if not isinstance(existing, Mapping) or existing.get("source") != "locked_detector_box":
                continue
            context = metadata.get("balloon_context_region")
            if isinstance(context, Mapping):
                metadata["layout_region"] = dict(context)
                metadata.pop("balloon_context_region", None)
                block.extra_metadata = metadata
            else:
                needs_detection.append(block)
            affected.append(block)
        if needs_detection:
            refresh_block_layout_regions(needs_detection)

    if affected:
        from app.services.typesetting import compute_block_typesetting, persist_typesetting_spec

        for block in affected:
            metadata = dict(getattr(block, "extra_metadata", None) or {})
            try:
                spec = compute_block_typesetting(block, log_feedback=False)
                persist_typesetting_spec(block, spec)
            except Exception as exc:
                logger.warning("Failed to recompute migrated layout for block %s: %s", getattr(block, "id", "?"), exc)
                metadata.pop("typesetting_spec", None)
                block.extra_metadata = metadata
    return len(affected)


def sort_blocks_reading_order(blocks: list, direction: str = "rtl") -> list:
    """Sort text blocks in comic reading order (Right-to-Left for Manga or Left-to-Right).
    
    For Manga (RTL):
    - Primary sort: Top-to-bottom (y-coordinate) grouped in horizontal panel bands.
    - Secondary sort: Right-to-left (x + width / 2 descending).
    """
    if not blocks:
        return []

    def get_coords(b):
        if isinstance(b, dict):
            return float(b.get("x", 0)), float(b.get("y", 0)), float(b.get("width", 0)), float(b.get("height", 0))
        return float(getattr(b, "x", 0)), float(getattr(b, "y", 0)), float(getattr(b, "width", 0)), float(getattr(b, "height", 0))

    heights = [get_coords(b)[3] for b in blocks if get_coords(b)[3] > 0]
    avg_h = float(np.mean(heights)) if heights else 50.0
    band_height = max(30.0, avg_h * 0.8)

    def sort_key(b):
        x, y, w, h = get_coords(b)
        center_x = x + w / 2.0
        band = int(y // band_height)
        if direction.lower() == "rtl":
            return (band, -center_x)
        else:
            return (band, center_x)

    return sorted(blocks, key=sort_key)

