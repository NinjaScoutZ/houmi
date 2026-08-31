"""Magnetic Line and Block Mask Engine.

Bridges horizontal gaps between words/glyphs on the same text line,
producing continuous solid rectangular bands across each line (preventing hollow gaps
in the middle of sentences in speech bubbles) while strictly respecting speech bubble borders.
"""

from __future__ import annotations

import cv2
import numpy as np
from app.services.mask.border_clamper import clamp_mask_to_balloon_interior


def apply_magnetic_line_fill(
    mask: np.ndarray,
    image_bgr: np.ndarray | None = None,
    balloon_barrier: np.ndarray | None = None,
    line_bridge_gap: int = 45,
) -> np.ndarray:
    """
    Connects/bridges horizontal gaps between words/glyphs on the same text line,
    filling each line solidly as a clean rectangular band without hollow holes in the middle,
    while strictly staying inside the balloon barrier.
    """
    if mask is None or np.count_nonzero(mask) == 0:
        return mask

    height, width = mask.shape[:2]

    # 1. Connect components on the same line horizontally using horizontal morphological closing
    k_w = max(15, min(width // 2, line_bridge_gap))
    k_h = 3  # small vertical height to prevent bridging between separate lines vertically
    kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (k_w, k_h))

    closed_lines = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel_h)

    # 2. Extract each line component and fill its individual horizontal bounding rectangle
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(closed_lines, connectivity=8)
    filled_mask = np.zeros((height, width), dtype=np.uint8)

    for l in range(1, num_labels):
        area = stats[l, cv2.CC_STAT_AREA]
        if area < 8:
            continue
        lx = stats[l, cv2.CC_STAT_LEFT]
        ly = stats[l, cv2.CC_STAT_TOP]
        lw = stats[l, cv2.CC_STAT_WIDTH]
        lh = stats[l, cv2.CC_STAT_HEIGHT]

        # Fill bounding rectangle of this text line
        filled_mask[ly:ly + lh, lx:lx + lw] = 255

    # 3. Constrain to balloon interior if balloon barrier or image is provided
    if balloon_barrier is not None and np.any(balloon_barrier):
        final_mask = cv2.bitwise_and(filled_mask, balloon_barrier)
    elif image_bgr is not None:
        final_mask = clamp_mask_to_balloon_interior(filled_mask, image_bgr, margin_px=2)
    else:
        final_mask = filled_mask

    # Preserve any fine details that were in the original mask
    return cv2.bitwise_or(final_mask, mask)
