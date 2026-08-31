"""Two-Zone Spatial Mask Classifier for comic text masking.

Analyzes text crops by separating the balloon interior (Zone A) from the
surrounding background context (Zone B), preventing external artwork colors
from falsifying the classification of black-and-white dialogue balloons.
"""

from __future__ import annotations

import cv2
import numpy as np

MASK_MODE_MONOCHROME_FLAT = "monochrome_flat"
MASK_MODE_COLOR_OR_COMPLEX = "color_or_complex"


def classify_text_mask_mode(
    image_bgr: np.ndarray,
) -> tuple[str, dict[str, float | bool]]:
    """Classify whether a crop should use monochrome flat or neural complex routing.

    Uses Two-Zone spatial analysis:
    1. Extracts Zone A (Balloon Interior) using luminance segmentation or central kernel.
    2. Computes Chroma (saturation) and Flatness (luminance variance) specifically on Zone A.
    3. Analyzes Boundary Enclosure to route dialogue balloons vs floating textured SFX.
    """
    if image_bgr is None or image_bgr.size == 0:
        return MASK_MODE_COLOR_OR_COMPLEX, {
            "chroma_p90": 0.0,
            "flat_ratio": 0.0,
            "interior_chroma": 0.0,
            "has_enclosure": False,
        }

    height, width = image_bgr.shape[:2]
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    chroma = np.sqrt((lab[:, :, 1] - 128.0) ** 2 + (lab[:, :, 2] - 128.0) ** 2)
    overall_chroma_p90 = float(np.percentile(chroma, 90)) if chroma.size > 0 else 0.0

    # 1. Segment Zone A (Balloon Interior)
    _, bright_mask = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
        bright_mask, connectivity=8
    )

    interior_mask = np.zeros((height, width), dtype=np.uint8)
    cx_crop, cy_crop = width / 2.0, height / 2.0
    has_enclosure = False

    if num_labels > 1:
        # Find the bright component closest to center with substantial area
        best_label = -1
        min_dist = float("inf")
        for l in range(1, num_labels):
            area = stats[l, cv2.CC_STAT_AREA]
            lx = stats[l, cv2.CC_STAT_LEFT]
            ly = stats[l, cv2.CC_STAT_TOP]
            lw = stats[l, cv2.CC_STAT_WIDTH]
            lh = stats[l, cv2.CC_STAT_HEIGHT]
            if area < (height * width * 0.05):
                continue
            touches_count = sum(
                [ly <= 0, (ly + lh) >= height, lx <= 0, (lx + lw) >= width]
            )
            if touches_count >= 3 and overall_chroma_p90 > 20.0:
                continue
            dist = np.sqrt((centroids[l][0] - cx_crop) ** 2 + (centroids[l][1] - cy_crop) ** 2)
            if dist < min_dist:
                min_dist = dist
                best_label = l

        if best_label > 0:
            interior_mask[labels == best_label] = 255
            has_enclosure = True

    # Fallback to central 60% kernel if no distinct bright component was segmented
    if not has_enclosure or np.count_nonzero(interior_mask) < (height * width * 0.10):
        y0, y1 = int(height * 0.20), int(height * 0.80)
        x0, x1 = int(width * 0.20), int(width * 0.80)
        interior_mask[y0:y1, x0:x1] = 255
        has_enclosure = False

    # Hull continuous interior
    cnts, _ = cv2.findContours(interior_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    hull_mask = np.zeros_like(interior_mask)
    for c in cnts:
        hull = cv2.convexHull(c)
        cv2.drawContours(hull_mask, [hull], -1, 255, -1)

    hull_indices = hull_mask > 0
    interior_chroma = chroma[hull_indices]
    interior_gray = gray[hull_indices]

    interior_chroma_p90 = (
        float(np.percentile(interior_chroma, 90))
        if interior_chroma.size > 0
        else overall_chroma_p90
    )
    median_interior_gray = (
        float(np.median(interior_gray))
        if interior_gray.size > 0
        else float(np.median(gray))
    )
    bright_interior = interior_gray[interior_gray > 160]
    balloon_bg_std = float(np.std(bright_interior)) if bright_interior.size > 0 else 999.0
    balloon_bg_ratio = float(np.mean(interior_gray > 160)) if interior_gray.size > 0 else 0.0
    flat_ratio = (
        float(np.mean(np.abs(interior_gray - median_interior_gray) <= 15.0))
        if interior_gray.size > 0
        else 0.0
    )

    # 3. Decision Matrix
    # Flat monochrome balloons: Low interior chroma, clean white background interior, and enclosure
    is_monochrome_flat = (
        interior_chroma_p90 <= 15.0
        and balloon_bg_ratio >= 0.60
        and balloon_bg_std < 20.0
        and (flat_ratio >= 0.45 or median_interior_gray >= 200)
        and (overall_chroma_p90 <= 20.0 or has_enclosure)
    )

    mode = MASK_MODE_MONOCHROME_FLAT if is_monochrome_flat else MASK_MODE_COLOR_OR_COMPLEX

    return mode, {
        "chroma_p90": round(overall_chroma_p90, 3),
        "interior_chroma": round(interior_chroma_p90, 3),
        "flat_ratio": round(flat_ratio, 4),
        "has_enclosure": has_enclosure,
        "median_interior_gray": round(median_interior_gray, 1),
    }
