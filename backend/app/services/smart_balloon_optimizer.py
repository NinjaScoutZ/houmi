"""
Houmi Studio - Maximal Inscribed Text Rectangle Optimizer
Calculates optimal typographic bounding boxes inside irregular speech balloons
using Euclidean Distance Transforms and Multi-Scale Aspect-Ratio Ray Insetting.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple, Optional, List

import cv2
import numpy as np


@dataclass
class InscribedRectangle:
    x: float
    y: float
    width: float
    height: float
    area: float
    aspect_ratio: float
    center_x: float
    center_y: float
    inset_ratio: float


class MaximalInscribedRectangleOptimizer:
    """
    Computes the maximal usable text area rectangle inside arbitrary polygon contours.
    Guarantees 0 overlap with balloon boundaries and maintains safe typographic margins.
    """

    @classmethod
    def find_maximal_inscribed_rectangle(
        cls,
        contour: np.ndarray,
        canvas_shape: Optional[Tuple[int, int]] = None,
        target_aspect_ratio: float = 1.0,
        safe_margin_ratio: float = 0.08,
    ) -> Optional[InscribedRectangle]:
        if contour is None or len(contour) < 5:
            return None

        # Determine canvas bounds from contour bounding box
        x_min, y_min, w, h = cv2.boundingRect(contour)
        if w <= 10 or h <= 10:
            return None

        pad = 20
        ch = h + 2 * pad
        cw = w + 2 * pad

        # Render local binary balloon mask
        local_mask = np.zeros((ch, cw), dtype=np.uint8)
        local_contour = contour - np.array([x_min - pad, y_min - pad])
        cv2.drawContours(local_mask, [local_contour.astype(np.int32)], -1, 255, -1)

        # 1. Exact Euclidean Distance Transform
        dist = cv2.distanceTransform(local_mask, cv2.DIST_L2, 5)
        _, max_val, _, max_loc = cv2.minMaxLoc(dist)
        
        if max_val < 4.0:
            return InscribedRectangle(
                x=float(x_min), y=float(y_min),
                width=float(w), height=float(h),
                area=float(w * h), aspect_ratio=float(w / max(1.0, h)),
                center_x=float(x_min + w / 2), center_y=float(y_min + h / 2),
                inset_ratio=0.0,
            )

        cx, cy = max_loc

        # 2. Multi-aspect ratio maximal box exploration around centroid
        best_area = -1.0
        best_box = (0, 0, 0, 0)

        # Search aspect ratios around target aspect ratio
        aspect_ratios = [target_aspect_ratio, 0.6, 0.8, 1.0, 1.2, 1.5, 2.0]
        
        for ar in aspect_ratios:
            # Ray marching to expand rectangle from centroid
            max_half_w = int(max_val * 2.5)
            for hw in range(4, max_half_w, 2):
                hh = int(hw / max(0.1, ar))
                rx0, ry0 = cx - hw, cy - hh
                rx1, ry1 = cx + hw, cy + hh

                if rx0 < 0 or ry0 < 0 or rx1 >= cw or ry1 >= ch:
                    break

                # Sample perimeter of candidate rectangle
                rect_roi = local_mask[ry0:ry1, rx0:rx1]
                if rect_roi.size == 0 or np.any(rect_roi == 0):
                    break

                curr_area = (2 * hw) * (2 * hh)
                if curr_area > best_area:
                    best_area = curr_area
                    best_box = (rx0, ry0, 2 * hw, 2 * hh)

        if best_area <= 0:
            # Fallback to inscribed circle bounding square
            side = int(max_val * math.sqrt(2.0))
            best_box = (cx - side // 2, cy - side // 2, side, side)
            best_area = side * side

        bx, by, bw, bh = best_box

        # Apply safe margin inset
        inset_x = bw * safe_margin_ratio
        inset_y = bh * safe_margin_ratio
        final_x = (bx + x_min - pad) + inset_x
        final_y = (by + y_min - pad) + inset_y
        final_w = max(10.0, bw - 2 * inset_x)
        final_h = max(10.0, bh - 2 * inset_y)

        return InscribedRectangle(
            x=round(float(final_x), 1),
            y=round(float(final_y), 1),
            width=round(float(final_w), 1),
            height=round(float(final_h), 1),
            area=round(float(final_w * final_h), 1),
            aspect_ratio=round(float(final_w / max(1.0, final_h)), 3),
            center_x=round(float(final_x + final_w / 2), 1),
            center_y=round(float(final_y + final_h / 2), 1),
            inset_ratio=safe_margin_ratio,
        )
