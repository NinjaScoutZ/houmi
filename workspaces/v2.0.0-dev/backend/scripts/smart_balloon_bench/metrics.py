"""Geometry metrics for the Smart Balloon benchmark harness.

All metrics compare an engine's safe polygon against a binary ground-truth
interior mask (uint8, 255 = balloon interior). When no GT mask exists the
record still contributes timing/success/fallback statistics.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Sequence

import cv2
import numpy as np


def rasterize_polygon(points: Sequence[Sequence[float]], shape: tuple[int, int]) -> np.ndarray:
    mask = np.zeros((int(shape[0]), int(shape[1])), dtype=np.uint8)
    if len(points) < 3:
        return mask
    pts = np.asarray(points, dtype=np.int32).reshape(-1, 1, 2)
    cv2.fillPoly(mask, [pts], 255)
    return mask


def compute_pair_metrics(
    gt_mask: np.ndarray,
    safe_polygon: Sequence[Sequence[float]],
    margin_px: int = 8,
) -> dict[str, float]:
    """IoU / precision / utilization / containment of the safe polygon vs GT.

    containment = fraction of the safe polygon lying inside the GT interior
    eroded by `margin_px`, i.e. the layout-safety proxy for "glyph pixels stay
    inside the balloon with breathing room".
    """
    gt = (gt_mask > 0).astype(np.uint8) * 255
    safe = rasterize_polygon(safe_polygon, gt.shape)

    safe_area = int(np.count_nonzero(safe))
    gt_area = int(np.count_nonzero(gt))
    if safe_area == 0 or gt_area == 0:
        return {
            "mask_iou": 0.0,
            "precision": 0.0,
            "utilization": 0.0,
            "containment": 0.0,
        }

    inter = int(np.count_nonzero(cv2.bitwise_and(safe, gt)))
    union = int(np.count_nonzero(cv2.bitwise_or(safe, gt)))

    k = max(3, int(margin_px) * 2 + 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    gt_eroded = cv2.erode(gt, kernel)
    contained = int(np.count_nonzero(cv2.bitwise_and(safe, gt_eroded)))

    return {
        "mask_iou": round(inter / union, 4),
        "precision": round(inter / safe_area, 4),
        "utilization": round(inter / gt_area, 4),
        "containment": round(contained / safe_area, 4),
    }


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    arr = np.asarray(values, dtype=np.float64)
    return float(round(np.percentile(arr, q), 3))


def aggregate_rows(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate result rows into nested stats keyed by scope.

    Scopes: overall -> engine -> {all, balloon_type:<t>, archetype:<a>, split:<s>}
    """
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        engine = str(row.get("engine", "?"))
        groups[(engine,)].append(row)
        groups[(engine, f"balloon_type:{row.get('balloon_type', '?')}")].append(row)
        if row.get("success"):
            groups[(engine, f"archetype:{row.get('archetype', 'UNKNOWN')}")].append(row)
        groups[(engine, f"split:{row.get('split', '?')}")].append(row)

    out: dict[str, Any] = {}
    all_rows = list(rows)
    out["overall"] = _agg_one_group(all_rows)
    per_engine: dict[str, Any] = {}
    for key, grp in sorted(groups.items()):
        engine = key[0]
        sub = "all" if len(key) == 1 else key[1]
        entry = per_engine.setdefault(engine, {})
        entry[sub] = _agg_one_group(grp)
    out["engines"] = per_engine
    return out


def _agg_one_group(grp: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(grp)
    successes = [r for r in grp if r.get("success")]
    scored = [r for r in successes if r.get("has_gt")]
    ious = [r["metrics"]["mask_iou"] for r in scored]
    precs = [r["metrics"]["precision"] for r in scored]
    utils = [r["metrics"]["utilization"] for r in scored]
    contains = [r["metrics"]["containment"] for r in scored]
    times = [float(r.get("elapsed_ms", 0.0)) for r in grp]

    fallbacks: dict[str, int] = defaultdict(int)
    for r in grp:
        if not r.get("success"):
            fallbacks[str(r.get("fallback_reason", "unknown"))] += 1

    return {
        "n": n,
        "n_scored": len(scored),
        "success_rate": round(len(successes) / n, 4) if n else 0.0,
        "iou_mean": round(sum(ious) / len(ious), 4) if ious else None,
        "iou_median": round(float(np.median(ious)), 4) if ious else None,
        "precision_mean": round(sum(precs) / len(precs), 4) if precs else None,
        "utilization_mean": round(sum(utils) / len(utils), 4) if utils else None,
        "containment_mean": round(sum(contains) / len(contains), 4) if contains else None,
        "runtime_p50_ms": _percentile(times, 50),
        "runtime_p95_ms": _percentile(times, 95),
        "fallback_reasons": dict(fallbacks),
    }
