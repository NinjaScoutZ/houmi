"""Engine adapters that normalize Smart Balloon engine outputs into benchmark rows."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

import cv2
import numpy as np

from app.utils.image_utils import cv2_imread_unicode

from .manifest import BenchRecord
from .metrics import compute_pair_metrics

logger = logging.getLogger(__name__)

ENGINE_NAMES: tuple[str, ...] = ("bbox", "v15", "v16", "prod")


def _bbox_polygon(bbox: dict[str, float]) -> list[list[float]]:
    x, y = float(bbox["x"]), float(bbox["y"])
    w, h = float(bbox["width"]), float(bbox["height"])
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def _run_bbox(image: np.ndarray, record: BenchRecord, inset_ratio: float) -> dict[str, Any]:
    bbox = {
        "x": float(record.text_bbox["x"]),
        "y": float(record.text_bbox["y"]),
        "width": float(record.text_bbox["width"]),
        "height": float(record.text_bbox["height"]),
    }
    return {
        "success": True,
        "method": "baseline_text_bbox",
        "archetype": "UNKNOWN",
        "safe_polygon": _bbox_polygon(bbox),
        "raw_contour_points": None,
        "metadata": {"note": "detector text bbox passthrough"},
    }


def _run_v15(image: np.ndarray, record: BenchRecord, inset_ratio: float) -> dict[str, Any]:
    from app.services.smart_balloon import process_smart_balloon_v15

    res = process_smart_balloon_v15(
        image,
        dict(record.text_bbox),
        rival_boxes=record.rival_boxes or None,
        inset_ratio=inset_ratio,
        use_adaptive=False,
    )
    return _normalize_engine_result(res)


def _run_v16(image: np.ndarray, record: BenchRecord, inset_ratio: float) -> dict[str, Any]:
    from app.services.smart_balloon import process_smart_balloon_v15

    res = process_smart_balloon_v15(
        image,
        dict(record.text_bbox),
        rival_boxes=record.rival_boxes or None,
        inset_ratio=inset_ratio,
        use_adaptive=True,
    )
    normalized = _normalize_engine_result(res)
    if res.get("success") and res.get("version") == "v16_adaptive":
        normalized["method"] = "smart_balloon_v16_adaptive"
    return normalized


def _normalize_engine_result(res: dict[str, Any]) -> dict[str, Any]:
    safe_points = res.get("contour_points") or []
    if not safe_points and res.get("success"):
        bb = res.get("safe_bbox") or {}
        if bb:
            safe_points = _bbox_polygon(bb)
    return {
        "success": bool(res.get("success")),
        "method": str(res.get("method", res.get("version", "unknown"))),
        "archetype": str(res.get("archetype", "UNKNOWN")),
        "fallback_reason": None if res.get("success") else str(
            (res.get("metadata") or {}).get("fallback_reason")
            or res.get("fallback")
            or "engine_failed"
        ),
        "safe_polygon": [list(map(float, p)) for p in safe_points],
        "raw_contour_points": res.get("raw_contour_points"),
        "metadata": res.get("metadata") or {},
    }


def _run_prod(image: np.ndarray, record: BenchRecord, inset_ratio: float) -> dict[str, Any]:
    from app.services.detector import compute_smart_balloon_bounds

    res = compute_smart_balloon_bounds(
        image,
        {**dict(record.text_bbox), "balloon_type": record.balloon_type},
        rival_boxes=record.rival_boxes or None,
        inset_ratio=inset_ratio,
        settings={"smart_balloon_adaptive": False},
    )
    return _normalize_prod_result(res, record)


def _normalize_prod_result(res: dict[str, Any], record: BenchRecord) -> dict[str, Any]:
    method = str(res.get("method", "unknown"))
    legacy_success = bool(res.get("success"))
    has_payload = bool(res.get("contour_points")) or res.get("crop_mask") is not None
    success = legacy_success or has_payload
    if not success:
        return {
            "success": False,
            "method": method,
            "archetype": "UNKNOWN",
            "fallback_reason": method,
            "safe_polygon": [],
            "raw_contour_points": None,
            "metadata": {},
        }

    safe_points = res.get("contour_points")
    if not safe_points and res.get("crop_mask") is not None:
        crop_mask = res["crop_mask"]
        off_x, off_y = res.get("crop_offset", (0, 0))
        cnts, _ = cv2.findContours((crop_mask > 0).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if cnts:
            main = max(cnts, key=cv2.contourArea).reshape(-1, 2) + np.array([off_x, off_y])
            safe_points = main.tolist()
    if not safe_points:
        bb = res.get("safe_bbox") or {}
        if bb and bb.get("width"):
            safe_points = _bbox_polygon(bb)
        else:
            safe_points = _bbox_polygon(record.text_bbox)

    return {
        "success": True,
        "method": method,
        "archetype": str(res.get("archetype", "UNKNOWN")),
        "fallback_reason": None,
        "safe_polygon": [list(map(float, p)) for p in safe_points],
        "raw_contour_points": res.get("raw_contour_points"),
        "metadata": res.get("metadata") or {},
    }


_RUNNERS: dict[str, Callable[[np.ndarray, BenchRecord, float], dict[str, Any]]] = {
    "bbox": _run_bbox,
    "v15": _run_v15,
    "v16": _run_v16,
    "prod": _run_prod,
}


def load_gt_mask(gt_path: str | None, expected_shape: tuple[int, int]) -> np.ndarray | None:
    if not gt_path:
        return None
    mask = cv2_imread_unicode(str(gt_path), flags=cv2.IMREAD_GRAYSCALE)
    if mask is None:
        logger.warning("GT mask unreadable: %s", gt_path)
        return None
    if mask.shape[:2] != expected_shape[:2]:
        mask = cv2.resize(mask, (expected_shape[1], expected_shape[0]), interpolation=cv2.INTER_NEAREST)
    return (mask > 127).astype(np.uint8) * 255


def run_record(
    record: BenchRecord,
    engine: str,
    inset_ratio: float = 0.10,
    margin_px: int = 8,
) -> dict[str, Any]:
    """Execute one engine on one manifest record and produce a result row."""
    row: dict[str, Any] = {
        "record_id": record.record_id,
        "project_id": record.project_id,
        "page_id": record.page_id,
        "block_index": record.block_index,
        "engine": engine,
        "balloon_type": record.balloon_type,
        "split": record.split,
        "has_gt": False,
        "metrics": None,
    }

    image = cv2_imread_unicode(record.image_path)
    if image is None:
        row.update({
            "success": False,
            "method": "error",
            "archetype": "UNKNOWN",
            "fallback_reason": "image_unreadable",
            "elapsed_ms": 0.0,
        })
        return row

    runner = _RUNNERS[engine]
    t0 = time.perf_counter()
    try:
        result = runner(image, record, inset_ratio)
    except Exception as exc:
        logger.warning("engine %s crashed on %s: %s", engine, record.record_id, exc)
        result = {"success": False, "method": "exception", "archetype": "UNKNOWN", "fallback_reason": f"exception:{exc}"}
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)

    row.update({
        "success": bool(result["success"]),
        "method": result["method"],
        "archetype": result["archetype"],
        "fallback_reason": result.get("fallback_reason"),
        "elapsed_ms": elapsed_ms,
    })

    gt_mask = load_gt_mask(record.gt_mask_path, image.shape[:2])
    if record.gt_mask_path:
        row["_gt_mask_path"] = record.gt_mask_path
    if gt_mask is not None and result["success"] and len(result["safe_polygon"]) >= 3:
        row["has_gt"] = True
        row["metrics"] = compute_pair_metrics(gt_mask, result["safe_polygon"], margin_px=margin_px)

    row["preview_payload"] = {
        "image_shape": tuple(int(v) for v in image.shape[:2]),
        "text_bbox": dict(record.text_bbox),
        "safe_polygon": result["safe_polygon"] if result["success"] else [],
    }
    return row
