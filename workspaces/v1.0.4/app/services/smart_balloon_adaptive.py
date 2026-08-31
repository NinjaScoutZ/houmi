"""Smart Balloon V16 - Adaptive Background-Aware Enhancement.

New Features over V15's acquisition stage:
1. Adaptive White Threshold - Dynamic per-balloon background sampling
2. Gradient-Tolerant Flood Fill - Multi-seed adaptive tolerance
3. Weak Edge Reinforcement - Enhance faint balloon strokes before flood fill
4. Tail Preservation - Extended crop padding for protruding tails/spikes

Schema contract: returns the SAME field set as process_smart_balloon_v15
(smart_*, crop_mask, crop_offset, raw_contour_points, row_width_constraints,
metadata) so every downstream consumer works unchanged. When a rival box
indicates a genuinely conjoined balloon, V16 declines via
fallback="conjoined_deferred_to_v15" so the dispatcher's waist-slicing
path takes over.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

SMART_BALLOON_V16_VERSION = "v16_adaptive"


def estimate_local_background_stats(
    gray: np.ndarray,
    text_bbox_local: dict[str, float],
) -> dict[str, float]:
    """
    Sample background pixels around the text bbox to estimate local brightness.
    Returns adaptive white threshold and flood fill tolerance.
    """
    ch, cw = gray.shape[:2]
    bx = int(text_bbox_local["x"])
    by = int(text_bbox_local["y"])
    bw = int(text_bbox_local["width"])
    bh = int(text_bbox_local["height"])

    pad = max(20, min(int(bw * 0.3), 60))

    samples = []
    regions = [
        (max(0, bx - pad), max(0, by - pad), min(cw, bx), min(ch, by)),
        (max(0, bx + bw), max(0, by - pad), min(cw, bx + bw + pad), min(ch, by)),
        (max(0, bx - pad), max(0, by + bh), min(cw, bx), min(ch, by + bh + pad)),
        (max(0, bx + bw), max(0, by + bh), min(cw, bx + bw + pad), min(ch, by + bh + pad)),
    ]

    for x0, y0, x1, y1 in regions:
        if x1 > x0 and y1 > y0:
            roi = gray[y0:y1, x0:x1]
            if roi.size > 0:
                bright_mask = roi > 150
                if np.count_nonzero(bright_mask) > roi.size * 0.3:
                    samples.extend(roi[bright_mask].flatten().tolist())

    if not samples:
        border_w = max(5, cw // 20)
        border_strips = [
            gray[:border_w, :],
            gray[-border_w:, :],
            gray[:, :border_w],
            gray[:, -border_w:],
        ]
        for strip in border_strips:
            if strip.size > 0:
                samples.extend(strip.flatten().tolist())

    if not samples:
        return {
            "bg_mean": 245.0,
            "bg_std": 15.0,
            "white_thresh": 180,
            "lo_diff": 35,
            "up_diff": 35,
        }

    samples_arr = np.array(samples, dtype=np.float32)
    bg_mean = float(np.mean(samples_arr))
    bg_std = float(np.std(samples_arr))

    if bg_mean >= 230:
        white_thresh = max(160, int(bg_mean - 50))
        lo_diff = 40
        up_diff = 40
    elif bg_mean >= 200:
        white_thresh = max(170, int(bg_mean - 30))
        lo_diff = 25
        up_diff = 25
    elif bg_mean >= 170:
        white_thresh = max(150, int(bg_mean - 20))
        lo_diff = 20
        up_diff = 20
    else:
        white_thresh = 180
        lo_diff = 35
        up_diff = 35

    return {
        "bg_mean": bg_mean,
        "bg_std": bg_std,
        "white_thresh": white_thresh,
        "lo_diff": lo_diff,
        "up_diff": up_diff,
    }


def reinforce_weak_balloon_edges(
    gray: np.ndarray,
    text_bbox_local: dict[str, float],
    edge_strength_thresh: int = 60,
) -> np.ndarray:
    """
    Detect and reinforce weak balloon boundary strokes that Canny might miss.
    Returns enhanced edge barrier mask.
    """
    ch, cw = gray.shape[:2]

    dark_thresh = (gray < 110).astype(np.uint8) * 255

    canny_edges = cv2.Canny(gray, 40, 120)

    sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    gradient_mag = np.sqrt(sobelx**2 + sobely**2)
    weak_edges = (gradient_mag > edge_strength_thresh).astype(np.uint8) * 255

    combined_edges = cv2.bitwise_or(dark_thresh, canny_edges)
    combined_edges = cv2.bitwise_or(combined_edges, weak_edges)

    k_edge = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    combined_edges = cv2.dilate(combined_edges, k_edge)

    return combined_edges


def multi_seed_adaptive_flood_fill(
    gray: np.ndarray,
    text_bbox_local: dict[str, float],
    edge_barrier: np.ndarray,
    bg_stats: dict[str, float],
) -> np.ndarray:
    """
    Perform flood fill with multiple seed points and adaptive tolerance.
    Returns the best connected white component.
    """
    ch, cw = gray.shape[:2]
    bx = float(text_bbox_local["x"])
    by = float(text_bbox_local["y"])
    bw = float(text_bbox_local["width"])
    bh = float(text_bbox_local["height"])

    white_thresh = int(bg_stats["white_thresh"])
    lo_diff = int(bg_stats["lo_diff"])
    up_diff = int(bg_stats["up_diff"])

    seed_points = []
    for row_frac in [0.3, 0.5, 0.7]:
        for col_frac in [0.3, 0.5, 0.7]:
            sx = int(bx + bw * col_frac)
            sy = int(by + bh * row_frac)
            sx = max(0, min(cw - 1, sx))
            sy = max(0, min(ch - 1, sy))
            if edge_barrier[sy, sx] == 0 and gray[sy, sx] >= white_thresh:
                seed_points.append((sx, sy))

    if not seed_points:
        cx = int(bx + bw / 2.0)
        cy = int(by + bh / 2.0)
        cx = max(0, min(cw - 1, cx))
        cy = max(0, min(ch - 1, cy))
        seed_points = [(cx, cy)]

    best_mask = None
    best_score = -1.0

    for sx, sy in seed_points:
        flood_mask = np.zeros((ch + 2, cw + 2), dtype=np.uint8)
        flood_mask[1:-1, 1:-1] = (edge_barrier > 0).astype(np.uint8) * 1

        filled_img = gray.copy()
        cv2.floodFill(
            filled_img,
            flood_mask,
            (sx, sy),
            255,
            loDiff=lo_diff,
            upDiff=up_diff,
            flags=4 | cv2.FLOODFILL_FIXED_RANGE | (255 << 8),
        )

        candidate_mask = (flood_mask[1:-1, 1:-1] == 255).astype(np.uint8) * 255
        area = cv2.countNonZero(candidate_mask)

        tb_roi = candidate_mask[int(by):int(by + bh), int(bx):int(bx + bw)]
        coverage = cv2.countNonZero(tb_roi) / max(1.0, bw * bh)

        score = area * (1.0 + coverage)

        if score > best_score:
            best_score = score
            best_mask = candidate_mask

    if best_mask is None:
        best_mask = np.zeros((ch, cw), dtype=np.uint8)

    return best_mask


def _rival_requires_v15_splitting(
    rival_boxes: list[dict] | None,
    connected_white: np.ndarray,
    ch: int,
    cw: int,
    sx0: int,
    sy0: int,
    text_bbox_global: dict[str, float],
) -> bool:
    """
    Mirrors V15's conjoined-balloon pre-checks. Returns True when any rival
    shares this balloon's white component or overlaps enough that V15's
    waist-slicing path should own the block instead of V16.
    """
    if not rival_boxes:
        return False

    bx = float(text_bbox_global["x"]) - sx0
    by = float(text_bbox_global["y"]) - sy0
    bw = float(text_bbox_global["width"])
    bh = float(text_bbox_global["height"])

    own_cx = int(bx + bw / 2.0)
    own_cy = int(by + bh / 2.0)

    for r_box in rival_boxes:
        r_cx = int(r_box["x"] + r_box["width"] / 2.0) - sx0
        r_cy = int(r_box["y"] + r_box["height"] / 2.0) - sy0

        r_x0 = int(r_box["x"]) - sx0
        r_y0 = int(r_box["y"]) - sy0
        r_x1 = r_x0 + int(r_box["width"])
        r_y1 = r_y0 + int(r_box["height"])
        t_x0, t_y0 = int(bx), int(by)
        t_x1, t_y1 = int(bx + bw), int(by + bh)
        ix = max(0, min(t_x1, r_x1) - max(t_x0, r_x0))
        iy = max(0, min(t_y1, r_y1) - max(t_y0, r_y0))
        overlap_area = ix * iy
        rival_area = int(r_box["width"]) * int(r_box["height"])
        target_area = bw * bh
        overlap_ratio = overlap_area / max(1, min(rival_area, target_area))

        in_crop = 0 <= r_cx < cw and 0 <= r_cy < ch
        is_same_white_blob = bool(in_crop and connected_white[r_cy, r_cx] > 0)

        if not is_same_white_blob and overlap_ratio < 0.10:
            continue

        dist_det = float(np.hypot(own_cx - r_cx, own_cy - r_cy)) if in_crop else float("inf")
        min_sep_det = float(max(bw, bh) * 0.05)
        if dist_det < min_sep_det:
            continue

        if is_same_white_blob or overlap_ratio >= 0.10:
            return True

    return False


def process_smart_balloon_v16_adaptive(
    image: np.ndarray,
    text_bbox: dict,
    rival_boxes: list[dict] | None = None,
    inset_ratio: float = 0.10,
) -> dict[str, Any]:
    """
    Smart Balloon V16 with adaptive background-aware processing.

    Returns the full V15-compatible result schema on success.
    """
    from app.services.smart_balloon import (
        apply_contour_inset,
        classify_balloon_archetype,
        _compute_row_width_constraints,
    )

    t0 = time.perf_counter()
    img_h, img_w = image.shape[:2]
    bx, by = float(text_bbox["x"]), float(text_bbox["y"])
    bw, bh = float(text_bbox["width"]), float(text_bbox["height"])

    pad_x = max(180, int(bw * 0.40))
    pad_y = max(240, int(bh * 1.60))
    sx0 = max(0, int(bx - pad_x))
    sy0 = max(0, int(by - pad_y))
    sx1 = min(img_w, int(bx + bw + pad_x))
    sy1 = min(img_h, int(by + bh + pad_y))

    crop = image[sy0:sy1, sx0:sx1]
    if crop.size == 0:
        return {"success": False, "fallback": "empty_crop"}

    ch, cw = crop.shape[:2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    local_bx = bx - sx0
    local_by = by - sy0

    local_bbox = {
        "x": local_bx,
        "y": local_by,
        "width": bw,
        "height": bh,
    }

    bg_stats = estimate_local_background_stats(gray, local_bbox)

    edge_barrier = reinforce_weak_balloon_edges(gray, local_bbox)

    connected_white = multi_seed_adaptive_flood_fill(
        gray, local_bbox, edge_barrier, bg_stats
    )

    if cv2.countNonZero(connected_white) >= (bw * bh * 0.20):
        open_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        opened_white = cv2.morphologyEx(connected_white, cv2.MORPH_OPEN, open_k)
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(opened_white)
        if num_labels > 1:
            tb_x0 = max(0, int(local_bx))
            tb_y0 = max(0, int(local_by))
            tb_x1 = min(cw, int(local_bx + bw))
            tb_y1 = min(ch, int(local_by + bh))
            best_lbl = 0
            best_score = -1.0
            for lbl in range(1, num_labels):
                comp_mask = labels == lbl
                overlap = int(np.count_nonzero(comp_mask[tb_y0:tb_y1, tb_x0:tb_x1]))
                area = stats[lbl, cv2.CC_STAT_AREA]
                score = overlap * 3.0 + area * 0.1
                if score > best_score and overlap > 0:
                    best_score = score
                    best_lbl = lbl
            if best_lbl > 0:
                cleaned_comp = (labels == best_lbl).astype(np.uint8) * 255
                restored = cv2.dilate(
                    cleaned_comp, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
                )
                connected_white = cv2.bitwise_and(restored, connected_white)

    k_text_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (19, 19))
    closed_text = cv2.morphologyEx(connected_white, cv2.MORPH_CLOSE, k_text_close)
    cnts_fill, _ = cv2.findContours(
        closed_text, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if cnts_fill:
        solid_white = np.zeros_like(connected_white)
        cv2.drawContours(solid_white, cnts_fill, -1, 255, -1)
        connected_white = solid_white

    if _rival_requires_v15_splitting(
        rival_boxes, connected_white, ch, cw, sx0, sy0, text_bbox
    ):
        return {"success": False, "fallback": "conjoined_deferred_to_v15"}

    cnts, _ = cv2.findContours(
        connected_white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE
    )
    if not cnts:
        return {"success": False, "fallback": "no_contour"}

    main_cnt = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(main_cnt) < (bw * bh * 0.4):
        return {"success": False, "fallback": "contour_too_small"}

    check_mask = np.zeros((ch, cw), dtype=np.uint8)
    cv2.fillPoly(check_mask, [main_cnt], 255)
    tb_x0g = max(0, int(local_bx))
    tb_y0g = max(0, int(local_by))
    tb_x1g = min(cw, int(local_bx + bw))
    tb_y1g = min(ch, int(local_by + bh))
    bbox_cover = float(np.count_nonzero(check_mask[tb_y0g:tb_y1g, tb_x0g:tb_x1g])) / max(
        1, (tb_x1g - tb_x0g) * (tb_y1g - tb_y0g)
    )
    if bbox_cover < 0.35:
        return {"success": False, "fallback": "text_bbox_not_covered"}

    local_classify_bbox = {"x": local_bx, "y": local_by, "width": bw, "height": bh}
    archetype, cls_meta = classify_balloon_archetype(
        main_cnt, local_classify_bbox, crop_w=cw, crop_h=ch, raw_gray=gray
    )

    body_poly = main_cnt
    poly_mask = np.zeros((ch, cw), dtype=np.uint8)
    cv2.fillPoly(poly_mask, [main_cnt], 255)
    dist_map = cv2.distanceTransform(poly_mask, cv2.DIST_L2, 5)
    max_r = float(np.max(dist_map)) if np.max(dist_map) > 0 else 10.0

    if archetype != "SPIKY_FUZZY":
        # Distance-proportional morphological opening to cleanly sever speech tails from main oval body
        ksize = max(13, min(int(max_r * 0.45), int(min(bw, bh) * 0.40), 75))
        if ksize % 2 == 0:
            ksize += 1
        open_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
        body_mask = cv2.morphologyEx(poly_mask, cv2.MORPH_OPEN, open_k)
        body_cnts, _ = cv2.findContours(body_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if body_cnts:
            best_body = max(body_cnts, key=cv2.contourArea)
            if cv2.contourArea(best_body) >= (cv2.contourArea(main_cnt) * 0.25):
                body_poly = best_body

    safe_poly = apply_contour_inset(body_poly, inset_ratio=inset_ratio)

    peri_raw = cv2.arcLength(body_poly, True)
    poly_simple = cv2.approxPolyDP(body_poly, 0.002 * peri_raw, True) if peri_raw > 0 else body_poly

    peri_safe = cv2.arcLength(safe_poly, True)
    safe_poly_simple = cv2.approxPolyDP(safe_poly, 0.002 * peri_safe, True) if peri_safe > 0 else safe_poly

    abs_raw_cnt = poly_simple.reshape(-1, 2) + np.array([sx0, sy0])
    abs_safe_cnt = safe_poly_simple.reshape(-1, 2) + np.array([sx0, sy0])

    rx, ry, rw, rh = cv2.boundingRect(abs_raw_cnt)
    sx, sy, sw, sh = cv2.boundingRect(abs_safe_cnt)

    M = cv2.moments(body_poly)
    if M["m00"] > 0:
        abs_cx = float(sx0 + M["m10"] / M["m00"])
        abs_cy = float(sy0 + M["m01"] / M["m00"])
    else:
        abs_cx = float(sx + sw / 2.0)
        abs_cy = float(sy + sh / 2.0)

    crop_mask = np.zeros((ch, cw), dtype=np.uint8)
    cv2.fillPoly(crop_mask, [main_cnt], 255)

    elapsed_sec = time.perf_counter() - t0

    meta = dict(cls_meta)
    meta.update({
        "elapsed_sec": round(elapsed_sec, 4),
        "inset_ratio": inset_ratio,
        "confidence": round(min(0.99, max(0.80, float(cv2.contourArea(body_poly) / max(1.0, float(bw * bh))))), 2),
        "adaptive_bg": bg_stats,
        "engine": SMART_BALLOON_V16_VERSION,
    })

    return {
        "success": True,
        "method": f"smart_balloon_{SMART_BALLOON_V16_VERSION}",
        "version": SMART_BALLOON_V16_VERSION,
        "archetype": archetype,
        "smart_x": float(sx),
        "smart_y": float(sy),
        "smart_width": float(sw),
        "smart_height": float(sh),
        "raw_bbox": {"x": float(rx), "y": float(ry), "width": float(rw), "height": float(rh)},
        "safe_bbox": {"x": float(sx), "y": float(sy), "width": float(sw), "height": float(sh)},
        "center": {"x": abs_cx, "y": abs_cy},
        "crop_mask": crop_mask,
        "crop_offset": (int(sx0), int(sy0)),
        "mask_area": int(cv2.countNonZero(crop_mask)),
        "contour_points": abs_safe_cnt.tolist(),
        "raw_contour_points": abs_raw_cnt.tolist(),
        "row_width_constraints": _compute_row_width_constraints(safe_poly, sx, sy, sw, sh),
        "metadata": meta,
        "bg_stats": bg_stats,
    }
