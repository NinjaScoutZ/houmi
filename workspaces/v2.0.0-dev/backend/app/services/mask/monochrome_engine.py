"""High-precision monochrome flat text mask engine.

Extracts text strokes in speech bubbles with sub-millisecond speed, strictly
protecting balloon border outlines and speech tails from being masked or erased.
"""

from __future__ import annotations

import cv2
import numpy as np


def generate_monochrome_flat_text_mask(
    image_bgr: np.ndarray,
    dilation_kernel: int = 3,
    remove_outer_contours: bool = True,
) -> np.ndarray:
    """Generate a clean binary mask (0/255) for text in speech balloons without touching borders or tails."""
    if image_bgr is None or image_bgr.size == 0:
        return np.zeros((1, 1), dtype=np.uint8)

    height, width = image_bgr.shape[:2]
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY) if image_bgr.ndim == 3 else image_bgr.copy()
    lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB).astype(np.float32) if image_bgr.ndim == 3 else None
    chroma = np.sqrt((lab[:, :, 1] - 128.0) ** 2 + (lab[:, :, 2] - 128.0) ** 2) if lab is not None else np.zeros_like(gray)
    background_gray = float(np.median(gray))

    # Case A: Dark background (gray < 128) -> Extract bright/glowing text
    if background_gray < 128:
        thresh_val = int(background_gray + 12)
        _, raw_light = cv2.threshold(gray, thresh_val, 255, cv2.THRESH_BINARY)
        
        raw_disconnected = raw_light.copy()
        raw_disconnected[0, :] = 0
        raw_disconnected[-1, :] = 0
        raw_disconnected[:, 0] = 0
        raw_disconnected[:, -1] = 0

        num_l, labels_l, stats_l, _ = cv2.connectedComponentsWithStats(
            raw_disconnected, connectivity=8
        )
        clean_light_mask = np.zeros((height, width), dtype=np.uint8)
        for l in range(1, num_l):
            area = stats_l[l, cv2.CC_STAT_AREA]
            lx = stats_l[l, cv2.CC_STAT_LEFT]
            ly = stats_l[l, cv2.CC_STAT_TOP]
            lw = stats_l[l, cv2.CC_STAT_WIDTH]
            lh = stats_l[l, cv2.CC_STAT_HEIGHT]

            if area < 6:
                continue

            touches_border = (
                lx <= 1 or ly <= 1 or (lx + lw) >= width - 1 or (ly + lh) >= height - 1
            )
            if touches_border and (lw > (width * 0.40) or lh > (height * 0.40) or area > (height * width * 0.20)):
                continue

            clean_light_mask[labels_l == l] = 255

        k_glow_size = max(9, int(dilation_kernel) * 2 + 3)
        kernel_glow = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_glow_size, k_glow_size))
        dilated_glow = cv2.dilate(clean_light_mask, kernel_glow, iterations=1)

        dilated_glow[0:3, :] = 0
        dilated_glow[-3:, :] = 0
        dilated_glow[:, 0:3] = 0
        dilated_glow[:, -3:] = 0
        return dilated_glow

    # Case B: Light background / Speech balloon (gray >= 128)
    # 1. Segment Bright Balloon Interior (Zone A)
    bright = (gray > 195).astype(np.uint8) * 255
    num_comp, labels_comp, stats_comp, centroids_comp = cv2.connectedComponentsWithStats(
        bright, connectivity=8
    )

    cx, cy = width / 2.0, height / 2.0
    best_label = -1
    min_dist = float("inf")
    for l in range(1, num_comp):
        area = stats_comp[l, cv2.CC_STAT_AREA]
        if area < int(height * width * 0.12):
            continue
        dist = (centroids_comp[l][0] - cx) ** 2 + (centroids_comp[l][1] - cy) ** 2
        if dist < min_dist:
            min_dist = dist
            best_label = l

    if best_label > 0:
        balloon_interior = (labels_comp == best_label).astype(np.uint8) * 255
        cnts_comp, _ = cv2.findContours(
            balloon_interior, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        interior_hull = np.zeros_like(gray)
        for c in cnts_comp:
            hull = cv2.convexHull(c)
            cv2.drawContours(interior_hull, [hull], -1, 255, -1)
        safe_interior = cv2.erode(interior_hull, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
        has_bright_balloon = True
    else:
        safe_interior = np.ones_like(gray) * 255
        has_bright_balloon = False

    # 2. Build Impenetrable Outer Border Barrier
    dark_elements = (gray < 70).astype(np.uint8) * 255
    num_d, labels_d, stats_d, _ = cv2.connectedComponentsWithStats(dark_elements)
    outer_barrier = np.zeros_like(gray)
    for d in range(1, num_d):
        lx, ly, lw, lh, area = stats_d[d]
        touches_border = (lx <= 2 or ly <= 2 or (lx + lw) >= width - 2 or (ly + lh) >= height - 2)
        if touches_border and (lw > width * 0.25 or lh > height * 0.25 or area > height * width * 0.03):
            outer_barrier[labels_d == d] = 255

    impenetrable_shield = cv2.dilate(outer_barrier, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))

    # 3. Extract Text ONLY INSIDE safe_interior
    local_bg = cv2.boxFilter(gray, -1, (31, 31))
    if has_bright_balloon:
        text_dark = (gray < 185) & (gray < (local_bg - 15)) & (safe_interior > 0)
    else:
        text_dark = (gray < 40) | ((gray < 185) & (gray < (local_bg - 18)) & (chroma < 22))

    raw_text = text_dark.astype(np.uint8) * 255

    # 4. Disconnect border collisions (1px crop border disconnect)
    raw_disconnected = raw_text.copy()
    raw_disconnected[0, :] = 0
    raw_disconnected[-1, :] = 0
    raw_disconnected[:, 0] = 0
    raw_disconnected[:, -1] = 0

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        raw_disconnected, connectivity=8
    )
    clean_mask = np.zeros((height, width), dtype=np.uint8)

    for l in range(1, num_labels):
        area = stats[l, cv2.CC_STAT_AREA]
        lx = stats[l, cv2.CC_STAT_LEFT]
        ly = stats[l, cv2.CC_STAT_TOP]
        lw = stats[l, cv2.CC_STAT_WIDTH]
        lh = stats[l, cv2.CC_STAT_HEIGHT]

        if area < 3:
            continue

        touches_border = (
            lx <= 1 or ly <= 1 or (lx + lw) >= width - 1 or (ly + lh) >= height - 1
        )
        if touches_border and (lw > (width * 0.40) or lh > (height * 0.40) or area > (height * width * 0.20)):
            continue

        clean_mask[labels == l] = 255

    # 5. Adaptive stroke dilation + horizontal bridging for dots '......'
    effective_dilation = max(1, int(dilation_kernel))
    k_size = effective_dilation * 2 + 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_size, k_size))
    dilated_mask = cv2.dilate(clean_mask, kernel, iterations=1)

    k_bridge = cv2.getStructuringElement(cv2.MORPH_RECT, (11, 3))
    dilated_mask = cv2.morphologyEx(dilated_mask, cv2.MORPH_CLOSE, k_bridge)

    if has_bright_balloon:
        final_mask = cv2.bitwise_and(dilated_mask, safe_interior)
        final_mask = cv2.bitwise_and(final_mask, cv2.bitwise_not(impenetrable_shield))
    else:
        final_mask = dilated_mask

    return final_mask

