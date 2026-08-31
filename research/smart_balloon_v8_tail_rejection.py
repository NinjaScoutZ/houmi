"""Smart Balloon V8: Hybrid Tail Rejection & Text Prior Bounds Engine.

Located and executed exclusively inside e:\\houmi\\research\\

Implements:
1. Hybrid Tail Rejection (Curvature + Center Distance + Sigmoid Text Distance Weighting).
2. Prior Bounds Constrained Superellipse Optimizer (a, b scaled strictly by text dimensions).
3. G2 Continuous Spline Reconstruction (splprep / splev).
4. Automated 4-Panel Verification for Conjoined Double Balloons (#14 & #15).
"""

from __future__ import annotations

import json
import math
import os
import sys
import cv2
import numpy as np
from pathlib import Path
from scipy.interpolate import splprep, splev
from scipy.ndimage import gaussian_filter1d
from scipy.optimize import least_squares

RESEARCH_DIR = Path(r"e:\houmi\research")
PROJECT_350_DIR = Path(r"E:\Chapter Download\Kuaikanmanhua\ลิขิตตัวร้าย\350")
OUTPUT_DIR = RESEARCH_DIR / "v8_tail_rejection_previews"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_image(path: Path) -> np.ndarray | None:
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def save_image(path: Path, img: np.ndarray) -> None:
    ext = path.suffix or ".png"
    ok, buf = cv2.imencode(ext, img)
    if ok:
        buf.tofile(str(path))


def compute_contour_curvature(contour: np.ndarray, sigma: float = 3.0) -> np.ndarray:
    """Compute discrete curvature along closed contour using Gaussian derivatives."""
    pts = contour.astype(np.float64)
    x = gaussian_filter1d(pts[:, 0], sigma=sigma, mode="wrap")
    y = gaussian_filter1d(pts[:, 1], sigma=sigma, mode="wrap")
    
    dx = np.gradient(x)
    dy = np.gradient(y)
    ddx = np.gradient(dx)
    ddy = np.gradient(dy)
    
    denom = (dx**2 + dy**2)**1.5
    denom = np.maximum(denom, 1e-6)
    curvature = (dx * ddy - dy * ddx) / denom
    return curvature


def filter_tail_and_neck_outliers(main_contour: np.ndarray, text_bbox: tuple[int, int, int, int], is_top_balloon: bool) -> np.ndarray:
    """Reject tail appendages and rival bridge points using hybrid curvature + distance heuristics."""
    bx, by, bw, bh = text_bbox
    tc_x = bx + bw / 2.0
    tc_y = by + bh / 2.0
    
    curv = compute_contour_curvature(main_contour)
    abs_curv = np.abs(curv)
    max_c = np.max(abs_curv)
    
    # Distance from text center
    dists = np.linalg.norm(main_contour - np.array([tc_x, tc_y]), axis=1)
    max_d = np.max(dists)
    
    clean_indices = []
    for i in range(len(main_contour)):
        p = main_contour[i]
        d = dists[i]
        c = abs_curv[i]
        
        # 1. Reject bridge/neck connection to rival balloon
        if is_top_balloon:
            # For top balloon, rival neck is below text bottom
            if p[1] > by + bh + 45 and p[0] > tc_x:
                continue
        else:
            # For bottom balloon, rival neck is above text top
            if p[1] < by - 30 and p[0] < tc_x:
                continue
                
        # 2. Reject sharp speech tail (high curvature + far from text center)
        is_tail = (c > 0.65 * max_c) and (d > 0.68 * max_d)
        if is_tail:
            continue
            
        # 3. Reject points outside reasonable text margin (prior envelope)
        if not is_top_balloon:
            # For bottom balloon #15: prevent stretching into the far left sky
            if p[0] < bx - 60:
                continue
                
        clean_indices.append(i)
        
    if len(clean_indices) >= 30:
        return main_contour[clean_indices]
    return main_contour


def superellipse_prior_residual(params: np.ndarray, pts: np.ndarray, text_bbox: tuple[int, int, int, int]) -> np.ndarray:
    """Residual function with sigmoid distance weighting to prioritize points close to text."""
    x0, y0, a, b, n, theta = params
    bx, by, bw, bh = text_bbox
    
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    
    dx = pts[:, 0] - x0
    dy = pts[:, 1] - y0
    
    u = dx * cos_t + dy * sin_t
    v = -dx * sin_t + dy * cos_t
    
    # Algebraic residual
    res = np.abs(u / a)**n + np.abs(v / b)**n - 1.0
    
    # Sigmoid distance weight (downweights far-away outlier points)
    r = np.sqrt(dx**2 + dy**2)
    ref_size = max(bw, bh) * 0.75
    weight = 1.0 / (1.0 + np.exp(6.0 * (r / ref_size - 1.25)))
    
    return res * weight


def fit_constrained_superellipse(clean_pts: np.ndarray, text_bbox: tuple[int, int, int, int]) -> tuple[np.ndarray, np.ndarray]:
    """Fit Superellipse using Text Bounding Box Prior Bounds."""
    bx, by, bw, bh = text_bbox
    tc_x = bx + bw / 2.0
    tc_y = by + bh / 2.0
    
    init_a = bw * 0.65
    init_b = bh * 0.65
    init_n = 2.8
    init_theta = 0.0
    
    p0 = [tc_x, tc_y, init_a, init_b, init_n, init_theta]
    
    # Prior bounds strictly bounded by text dimensions & horizontal squircle nature
    bounds = (
        [tc_x - 30, tc_y - 25, bw * 0.52, bh * 0.50, 2.2, -0.05],
        [tc_x + 30, tc_y + 25, bw * 0.95, bh * 1.10, 3.8, 0.05]
    )
    
    res = least_squares(
        superellipse_prior_residual,
        p0,
        bounds=bounds,
        args=(clean_pts, text_bbox),
        loss="soft_l1",
        f_scale=0.1
    )
    
    x0, y0, a, b, n, theta = res.x
    
    # Generate G2 dense superellipse contour
    phi = np.linspace(0, 2 * math.pi, 200, endpoint=False)
    cos_phi = np.cos(phi)
    sin_phi = np.sin(phi)
    
    u = a * np.sign(cos_phi) * (np.abs(cos_phi)**(2.0 / n))
    v = b * np.sign(sin_phi) * (np.abs(sin_phi)**(2.0 / n))
    
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    
    fit_x = x0 + u * cos_t - v * sin_t
    fit_y = y0 + u * sin_t + v * cos_t
    
    pts_arr = np.column_stack([fit_x, fit_y])
    
    # G2 Cubic B-Spline Refinement
    tck, u_spl = splprep([pts_arr[:, 0], pts_arr[:, 1]], s=0, per=True, k=3)
    u_dense = np.linspace(0, 1, 300)
    smooth_x, smooth_y = splev(u_dense, tck)
    
    smooth_poly = np.column_stack([smooth_x, smooth_y]).astype(np.int32)
    return smooth_poly, np.array([x0, y0, a, b, n, theta])


def process_balloon_v8(crop: np.ndarray, text_bbox: tuple[int, int, int, int], is_top: bool) -> dict:
    ch, cw = crop.shape[:2]
    bx, by, bw, bh = text_bbox
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    
    # 1. Pure White Floodfill
    pure_white = (gray >= 195).astype(np.uint8) * 255
    pure_white = cv2.morphologyEx(pure_white, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
    pure_white = cv2.morphologyEx(pure_white, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    
    seed = np.zeros((ch + 2, cw + 2), dtype=np.uint8)
    cv2.floodFill(pure_white.copy(), seed, (bx + bw // 2, by + bh // 2), 255, flags=8 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY)
    joined_mask = seed[1:-1, 1:-1] * 255
    
    cnts, _ = cv2.findContours(joined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    main_cnt = max(cnts, key=cv2.contourArea).reshape(-1, 2)
    
    # 2. Hybrid Tail & Neck Rejection
    clean_pts = filter_tail_and_neck_outliers(main_cnt, text_bbox, is_top)
    
    # 3. Fit Prior-Constrained Superellipse + G2 Spline
    smooth_poly, params = fit_constrained_superellipse(clean_pts, text_bbox)
    x0, y0, a, b, n, theta = params
    
    # 4. Generate Mask
    mask = np.zeros((ch, cw), dtype=np.uint8)
    cv2.fillPoly(mask, [smooth_poly], 255)
    mask = cv2.bitwise_and(mask, pure_white)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    
    # 5. High-Contrast Text Ink Mask
    text_ink = (gray < 155).astype(np.uint8) * 255
    text_mask = cv2.bitwise_and(text_ink, mask)
    
    # 6. Cleaning & True Centering
    clean_mask = cv2.dilate(text_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    cleaned = cv2.inpaint(crop, clean_mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
    cleaned[clean_mask > 0] = [255, 255, 255]
    
    nz = cv2.findNonZero(mask)
    x, y, w, h = cv2.boundingRect(nz) if nz is not None else (0, 0, 100, 100)
    cx = int(round(x0))
    cy = int(round(y0))
    
    return {
        "mask": mask,
        "poly": smooth_poly,
        "text_mask": text_mask,
        "cleaned": cleaned,
        "bbox": (x, y, w, h),
        "center": (cx, cy),
        "params": params,
    }


def build_4panel(crop: np.ndarray, init_bbox: tuple[int, int, int, int], res: dict) -> np.ndarray:
    bx, by, bw, bh = init_bbox
    poly = res["poly"]
    text_mask = res["text_mask"]
    cleaned = res["cleaned"]
    cx, cy = res["center"]
    x, y, w, h = res["bbox"]
    n_val = res["params"][4]
    
    p1 = crop.copy()
    cv2.rectangle(p1, (bx, by), (bx + bw, by + bh), (0, 0, 255), 3)
    cv2.putText(p1, "1. INITIAL BBOX (RED)", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 255), 2)
    
    p2 = crop.copy()
    overlay = p2.copy()
    cv2.fillPoly(overlay, [poly], (180, 180, 255))
    cv2.addWeighted(overlay, 0.40, p2, 0.60, 0, p2)
    cv2.polylines(p2, [poly], isClosed=True, color=(0, 255, 0), thickness=3)
    cv2.putText(p2, f"2. SMART SUPERELLIPSE (n={n_val:.1f})", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (0, 255, 0), 2)
    
    p3 = cv2.cvtColor(text_mask, cv2.COLOR_GRAY2BGR)
    cv2.putText(p3, "3. TEXT MASK IN BALLOON", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
    
    p4 = cleaned.copy()
    cv2.polylines(p4, [poly], isClosed=True, color=(0, 255, 0), thickness=3)
    cv2.line(p4, (x, cy), (x + w, cy), (255, 150, 0), 3)
    cv2.circle(p4, (cx, cy), 6, (255, 100, 0), -1)
    cv2.putText(p4, "4. CLEANED & TRUE CENTER", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
    
    return np.hstack([p1, p2, p3, p4])


def main():
    print("=== STARTING SMART BALLOON V8 (TAIL REJECTION & TEXT PRIOR BOUNDS) ===")
    page_img = load_image(PROJECT_350_DIR / "03.jpg")
    proj = json.load(open(PROJECT_350_DIR / "project.json", encoding="utf-8"))
    p3 = [p for p in proj["pages"] if p["page_number"] == 3][0]
    blocks = p3["text_blocks"]
    
    blk14 = blocks[1]  # Top Balloon
    blk15 = blocks[2]  # Bottom Balloon
    
    bx14, by14, bw14, bh14 = int(blk14["x"]), int(blk14["y"]), int(blk14["width"]), int(blk14["height"])
    bx15, by15, bw15, bh15 = int(blk15["x"]), int(blk15["y"]), int(blk15["width"]), int(blk15["height"])
    
    min_x = 220
    min_y = 5900
    max_x = 1150
    max_y = 6850
    
    crop = page_img[min_y:max_y, min_x:max_x].copy()
    
    l14_x, l14_y = bx14 - min_x, by14 - min_y
    l15_x, l15_y = bx15 - min_x, by15 - min_y
    
    # 1. Process Balloon 14
    res14 = process_balloon_v8(crop, (l14_x, l14_y, bw14, bh14), is_top=True)
    p14_out = build_4panel(crop, (l14_x, l14_y, bw14, bh14), res14)
    out14 = OUTPUT_DIR / "v8_sample_14_page03.png"
    save_image(out14, p14_out)
    print(f"V8 Sample 14 Preview saved -> {out14}")
    
    # 2. Process Balloon 15 (With Tail Rejection & Text Prior Bounds)
    res15 = process_balloon_v8(crop, (l15_x, l15_y, bw15, bh15), is_top=False)
    p15_out = build_4panel(crop, (l15_x, l15_y, bw15, bh15), res15)
    out15 = OUTPUT_DIR / "v8_sample_15_page03.png"
    save_image(out15, p15_out)
    print(f"V8 Sample 15 Preview saved -> {out15}")
    
    print("\nSmart Balloon V8 Pipeline completed successfully!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
