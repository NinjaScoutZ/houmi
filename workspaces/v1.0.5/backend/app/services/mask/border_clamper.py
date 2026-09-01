"""Distance-aware border and tail clamping for speech balloon text masks.

Prevents dilated text masks from eroding or leaking into balloon stroke borders and tails.
"""

from __future__ import annotations

import cv2
import numpy as np


def clamp_mask_to_balloon_interior(
    mask: np.ndarray,
    image_bgr: np.ndarray,
    margin_px: int = 2,
) -> np.ndarray:
    """Constrain text mask strictly to the inner region of the balloon,
    protecting balloon border lines and tails from being eroded or masked.
    
    Polarity-aware: On light balloons, protects dark border strokes.
    On dark/screaming balloons, avoids treating the dark background as a border.
    """
    if mask is None or image_bgr is None or not np.any(mask):
        return mask

    height, width = image_bgr.shape[:2]
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY) if image_bgr.ndim == 3 else image_bgr.copy()

    # 1. Sample perimeter rim polarity
    rim_h = min(3, max(1, height // 10))
    rim_w = min(3, max(1, width // 10))
    rim_pixels = np.concatenate([
        gray[:rim_h, :].flatten(),
        gray[-rim_h:, :].flatten(),
        gray[:, :rim_w].flatten(),
        gray[:, -rim_w:].flatten(),
    ])
    rim_median = float(np.median(rim_pixels)) if rim_pixels.size > 0 else 255.0
    bg_median = float(np.median(gray))

    # If background is dark (e.g. dark spiky scream balloon, night panel, or black bubble),
    # dark pixels are the background fill itself, NOT a bounding border stroke.
    is_dark_background = (rim_median < 130 and bg_median < 140)

    if is_dark_background:
        # On dark backgrounds, check for light/white enclosing borders if any
        _, light_binary = cv2.threshold(gray, 210, 255, cv2.THRESH_BINARY)
        candidate_binary = light_binary
    else:
        # On standard light balloons, detect dark strokes
        _, dark_binary = cv2.threshold(gray, 110, 255, cv2.THRESH_BINARY_INV)
        candidate_binary = dark_binary

    if np.count_nonzero(candidate_binary) == 0:
        return mask

    # Separate outer balloon border / frame strokes from interior text glyphs
    num_l, labels_l, stats_l, _ = cv2.connectedComponentsWithStats(candidate_binary, connectivity=8)
    border_binary = np.zeros_like(candidate_binary)
    total_pixels = height * width

    for l in range(1, num_l):
        area = stats_l[l, cv2.CC_STAT_AREA]
        lx = stats_l[l, cv2.CC_STAT_LEFT]
        ly = stats_l[l, cv2.CC_STAT_TOP]
        lw = stats_l[l, cv2.CC_STAT_WIDTH]
        lh = stats_l[l, cv2.CC_STAT_HEIGHT]

        touches_perimeter = (lx <= 2 or ly <= 2 or (lx + lw) >= width - 2 or (ly + lh) >= height - 2)
        is_large_stroke = (area > (total_pixels * 0.08) or lw >= (width * 0.50) or lh >= (height * 0.50))

        if touches_perimeter or is_large_stroke:
            # Measure maximum stroke thickness via local distance transform
            comp_mask = (labels_l == l).astype(np.uint8)
            comp_dist = cv2.distanceTransform(comp_mask, cv2.DIST_L2, 3)
            max_thickness = float(comp_dist.max()) * 2.0 if comp_dist.size > 0 else 0.0

            # Real balloon borders are line strokes (max thickness <= 24px).
            # Giant solid background fills have massive thickness (> 28px).
            if max_thickness <= 24.0 or (touches_perimeter and not is_dark_background):
                border_binary[labels_l == l] = 255

    # Seal small gaps in balloon stroke to form an impassable flood barrier
    k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    closed_border = cv2.morphologyEx(border_binary, cv2.MORPH_CLOSE, k_close)

    # Flood fill from perimeter edges to segment exterior artwork from balloon interior
    flood_mask = np.zeros((height + 2, width + 2), dtype=np.uint8)
    flood_mask[1:-1, 1:-1] = (closed_border > 0).astype(np.uint8)
    flooded_exterior = np.zeros((height, width), dtype=np.uint8)

    step_x = max(1, width // 10)
    step_y = max(1, height // 10)
    for x in range(0, width, step_x):
        if flood_mask[1, x + 1] == 0:
            cv2.floodFill(flooded_exterior, flood_mask, (x, 0), 255)
        if flood_mask[height, x + 1] == 0:
            cv2.floodFill(flooded_exterior, flood_mask, (x, height - 1), 255)
    for y in range(0, height, step_y):
        if flood_mask[y + 1, 1] == 0:
            cv2.floodFill(flooded_exterior, flood_mask, (0, y), 255)
        if flood_mask[y + 1, width] == 0:
            cv2.floodFill(flooded_exterior, flood_mask, (width - 1, y), 255)

    exterior_detected = (flood_mask[1:-1, 1:-1] == 255) | (flooded_exterior > 0)

    # Euclidean distance transform from detected balloon borders
    dist_map = cv2.distanceTransform((255 - border_binary), cv2.DIST_L2, 5)

    clamped_mask = mask.copy()
    
    # Only apply exterior wipe if exterior doesn't consume the entire frame (avoiding leaky flood-fills)
    exterior_count = np.count_nonzero(exterior_detected)
    if 0 < exterior_count < (total_pixels * 0.85):
        clamped_mask[exterior_detected] = 0
    
    # Protect border line stroke with distance margin
    clamped_mask[dist_map <= float(margin_px)] = 0

    # Safety Guard: If clamping accidentally wiped out > 70% of original text or zeroed it out completely,
    # fall back to protecting the text mask while only suppressing exact border pixels.
    orig_count = np.count_nonzero(mask)
    clamped_count = np.count_nonzero(clamped_mask)
    if orig_count > 0 and clamped_count < max(8, int(orig_count * 0.30)):
        safe_mask = mask.copy()
        if np.any(border_binary):
            safe_mask[border_binary > 0] = 0
        return safe_mask

    return clamped_mask

