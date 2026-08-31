"""Interactive balloon segmentation for experimental typesetting layout."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import cv2
import numpy as np


class BalloonSegmenterUnavailable(RuntimeError):
    pass


def segment_balloon_layout(
    image: np.ndarray,
    selection: tuple[int, int, int, int],
    block: Any,
    *,
    segmenter: Callable[[np.ndarray, int, int, int, int], np.ndarray | None] | None = None,
) -> tuple[dict[str, Any], np.ndarray, tuple[int, int, int, int]]:
    """Segment one selected balloon and derive a conservative inner text box."""
    if image is None or image.size == 0:
        raise ValueError("Source image is unavailable")

    height, width = image.shape[:2]
    sx0, sy0, sx1, sy1 = selection
    sx0, sx1 = sorted((max(0, min(width - 1, int(sx0))), max(1, min(width, int(sx1)))))
    sy0, sy1 = sorted((max(0, min(height - 1, int(sy0))), max(1, min(height, int(sy1)))))
    if sx1 - sx0 < 8 or sy1 - sy0 < 8:
        raise ValueError("Balloon selection is too small")

    padding = max(24, int(round(max(sx1 - sx0, sy1 - sy0) * 0.20)))
    cx0, cy0 = max(0, sx0 - padding), max(0, sy0 - padding)
    cx1, cy1 = min(width, sx1 + padding), min(height, sy1 + padding)
    crop = image[cy0:cy1, cx0:cx1]

    if segmenter is None:
        from app.services.sam_segmenter import smart_segment_box

        segmenter = smart_segment_box
    mask = segmenter(crop, sx0 - cx0, sy0 - cy0, sx1 - cx0, sy1 - cy0)
    if mask is None:
        raise BalloonSegmenterUnavailable("SAM 2.1 model is not available")
    if mask.shape[:2] != crop.shape[:2]:
        mask = cv2.resize(mask, (crop.shape[1], crop.shape[0]), interpolation=cv2.INTER_NEAREST)
    binary = np.where(mask > 0, 255, 0).astype(np.uint8)

    count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    prompt = np.zeros_like(binary)
    prompt[sy0 - cy0:sy1 - cy0, sx0 - cx0:sx1 - cx0] = 255
    best_label = 0
    best_score = -1.0
    prompt_area = max(1, int(np.count_nonzero(prompt)))
    for label in range(1, count):
        component = labels == label
        area = int(stats[label, cv2.CC_STAT_AREA])
        overlap = int(np.count_nonzero(component & (prompt > 0)))
        if area < 32 or overlap == 0:
            continue
        score = (overlap / prompt_area) * 4.0 + min(2.0, area / prompt_area)
        if score > best_score:
            best_label, best_score = label, score
    if best_label == 0:
        raise ValueError("SAM did not find a balloon inside the selection")

    component = np.where(labels == best_label, 255, 0).astype(np.uint8)
    points = cv2.findNonZero(component)
    if points is None:
        raise ValueError("Segmented balloon is empty")
    bx, by, bw, bh = cv2.boundingRect(points)
    if bw * bh > crop.shape[0] * crop.shape[1] * 0.96:
        raise ValueError("Segmented region escaped the selected balloon")

    safe_margin = max(3, int(round(min(bw, bh) * 0.045)))
    distance = cv2.distanceTransform(component, cv2.DIST_L2, 5)
    safe = np.where(distance >= safe_margin, 255, 0).astype(np.uint8)
    safe_points = cv2.findNonZero(safe)
    if safe_points is None:
        raise ValueError("Balloon interior is too small for text")
    ix, iy, iw, ih = cv2.boundingRect(safe_points)

    selection_area = max(1, (sx1 - sx0) * (sy1 - sy0))
    overlap = np.count_nonzero((component > 0) & (prompt > 0)) / selection_area
    region = {
        "x": float(cx0 + ix),
        "y": float(cy0 + iy),
        "width": float(iw),
        "height": float(ih),
        "shape": str(getattr(block, "balloon_type", None) or "bubble"),
        "confidence": round(float(max(0.0, min(1.0, overlap))), 4),
        "source": "manual",
        "method": "sam2_balloon",
        "safe_margin": 0.0,
        "locked": True,
        "selection_box": {
            "x": float(sx0),
            "y": float(sy0),
            "width": float(sx1 - sx0),
            "height": float(sy1 - sy0),
        },
        "outer_box": {
            "x": float(cx0 + bx),
            "y": float(cy0 + by),
            "width": float(bw),
            "height": float(bh),
        },
    }
    return region, component, (cx0, cy0, cx1, cy1)
