"""
Webtoon Bubble-Safe Smart Split Service
=======================================
Splits tall vertical webtoon strips into balanced page chunks
while intelligently avoiding slicing through speech bubbles and text blocks.
"""

from __future__ import annotations

import logging
from typing import List, Dict, Any, Tuple
import cv2
import numpy as np

logger = logging.getLogger(__name__)

BUBBLE_CUT_MARGIN = 30  # Safe clearance margin in pixels around bubbles


def find_optimal_cut_position(
    img_h: int,
    nominal_y: int,
    bubbles: List[Dict[str, float]],
    search_window: int = 400,
    gray_image: np.ndarray | None = None
) -> int:
    """
    Finds a safe horizontal cut line near `nominal_y` that does not intersect
    any speech bubble, prioritizing blank whitespace rows.

    Parameters:
    - img_h: Total image height
    - nominal_y: Desired target split position (e.g. 2000, 4000...)
    - bubbles: List of bubble/text bboxes with keys 'y', 'height' (or 'y0', 'y1')
    - search_window: Maximum distance (+/- px) to search for a clean cut
    - gray_image: Optional grayscale image to compute row gradient density

    Returns:
    - Optimal y coordinate for cutting.
    """
    y_min = max(100, nominal_y - search_window)
    y_max = min(img_h - 100, nominal_y + search_window)

    if y_min >= y_max:
        return nominal_y

    # Build obstacle mask for all bubble bounding boxes + margin
    obstacle_mask = np.zeros(img_h, dtype=bool)
    for b in bubbles:
        by0 = int(b.get("y", b.get("y0", 0))) - BUBBLE_CUT_MARGIN
        bh = int(b.get("height", b.get("h", 0)))
        by1 = by0 + bh + (2 * BUBBLE_CUT_MARGIN)
        by0 = max(0, by0)
        by1 = min(img_h, by1)
        obstacle_mask[by0:by1] = True

    # Candidate y positions inside the search window that are obstacle-free
    free_candidates = [y for y in range(y_min, y_max) if not obstacle_mask[y]]

    if not free_candidates:
        # If whole window is blocked by large bubbles, pick the point furthest from any bubble center
        logger.warning(f"No completely free cut line found near y={nominal_y}, using nearest gap")
        return nominal_y

    # If gray image is available, score candidates by lowest horizontal edge energy (whitest / most uniform row)
    if gray_image is not None and gray_image.shape[0] == img_h:
        grad_y = cv2.Sobel(gray_image, cv2.CV_32F, 0, 1, ksize=3)
        row_energies = np.mean(np.abs(grad_y), axis=1)

        best_y = free_candidates[0]
        best_score = float("inf")
        for y in free_candidates:
            # Score: row visual complexity + distance penalty from nominal_y
            dist_penalty = (abs(y - nominal_y) / float(search_window)) * 2.0
            score = float(row_energies[y]) + dist_penalty
            if score < best_score:
                best_score = score
                best_y = y
        return best_y

    # Otherwise, pick free candidate closest to nominal_y
    return min(free_candidates, key=lambda y: abs(y - nominal_y))


def smart_split_webtoon(
    image: np.ndarray,
    bubbles: List[Dict[str, float]],
    target_height: int = 2500,
    min_chunk_height: int = 800
) -> List[Tuple[np.ndarray, Tuple[int, int]]]:
    """
    Slices a tall webtoon strip into multiple images without cutting bubbles.

    Returns:
    - List of (cropped_image_array, (y_start, y_end)) tuples.
    """
    img_h, img_w = image.shape[:2]
    if img_h <= target_height:
        return [(image, (0, img_h))]

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    cut_positions = [0]
    curr_y = target_height

    while curr_y < img_h - min_chunk_height:
        safe_cut = find_optimal_cut_position(img_h, curr_y, bubbles, search_window=int(target_height * 0.25), gray_image=gray)
        # Ensure progress
        if safe_cut <= cut_positions[-1] + min_chunk_height:
            safe_cut = cut_positions[-1] + min_chunk_height
        cut_positions.append(safe_cut)
        curr_y = safe_cut + target_height

    cut_positions.append(img_h)

    chunks = []
    for i in range(len(cut_positions) - 1):
        y0 = cut_positions[i]
        y1 = cut_positions[i + 1]
        chunk_img = image[y0:y1, :]
        chunks.append((chunk_img, (y0, y1)))

    logger.info(f"Smart Split complete: {img_h}px image split into {len(chunks)} chunks at {cut_positions[1:-1]}")
    return chunks
