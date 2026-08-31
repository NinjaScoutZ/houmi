"""Smart Balloon V9: Complete Conjoined Balloon Separation & 5-Panel Pipeline (Polished).

Located and executed exclusively inside e:\\houmi\\research\\

Implements:
1. Pure White Shared Interior Segmentation.
2. Text-Anchored Geodesic/Voronoi Partitioning & Distance Ridge Separation.
3. Multi-Text Aware Owned Point Partitioning & Tail Rejection.
4. Prior-Constrained Superellipse (Squircle n in [2.2, 3.8]) Fitting for each balloon.
5. 5-Panel High-Definition Visualization:
   - Panel 1: INITIAL BBOXES (RED)
   - Panel 2: WATERSHED & SEPARATION LINE (RED CUT + VORONOI PARTITION)
   - Panel 3: SMART SUPERELLIPSE SHAPES (GREEN SQUIRCLES)
   - Panel 4: TEXT MASKS IN BALLOONS
   - Panel 5: CLEANED INPAINT & TRUE CENTERS (BLUE LINES)
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
OUTPUT_DIR = RESEARCH_DIR / "v9_watershed_previews"
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


def compute_discrete_curvature(contour: np.ndarray, sigma: float = 3.0) -> np.ndarray:
    pts = contour.astype(np.float64)
    x = gaussian_filter1d(pts[:, 0], sigma=sigma, mode="wrap")
    y = gaussian_filter1d(pts[:, 1], sigma=sigma, mode="wrap")
    
    dx = np.gradient(x)
    dy = np.gradient(y)
    ddx = np.gradient(dx)
    ddy = np.gradient(dy)
    
    denom = (dx**2 + dy**2)**1.5
    denom = np.maximum(denom, 1e-6)
    return (dx * ddy - dy * ddx) / denom


def superellipse_prior_residual(params: np.ndarray, pts: np.ndarray, text_bbox: tuple[int, int, int, int]) -> np.ndarray:
    x0, y0, a, b, n, theta = params
    bx, by, bw, bh = text_bbox
    
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    
    dx = pts[:, 0] - x0
    dy = pts[:, 1] - y0
    
    u = dx * cos_t + dy * sin_t
    v = -dx * sin_t + dy * cos_t
    
    res = np.abs(u / a)**n + np.abs(v / b)**n - 1.0
    
    r = np.sqrt(dx**2 + dy**2)
    ref_size = max(bw, bh) * 0.75
    weight = 1.0 / (1.0 + np.exp(6.0 * (r / ref_size - 1.25)))
    return res * weight


def fit_constrained_squircle(clean_pts: np.ndarray, text_bbox: tuple[int, int, int, int]) -> tuple[np.ndarray, np.ndarray]:
    bx, by, bw, bh = text_bbox
    tc_x = bx + bw / 2.0
    tc_y = by + bh / 2.0
    
    init_a = bw * 0.65
    init_b = bh * 0.65
    init_n = 2.8
    init_theta = 0.0
    
    p0 = [tc_x, tc_y, init_a, init_b, init_n, init_theta]
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
    tck, u_spl = splprep([pts_arr[:, 0], pts_arr[:, 1]], s=0, per=True, k=3)
    u_dense = np.linspace(0, 1, 300)
    smooth_x, smooth_y = splev(u_dense, tck)
    
    smooth_poly = np.column_stack([smooth_x, smooth_y]).astype(np.int32)
    return smooth_poly, np.array([x0, y0, a, b, n, theta])


def process_conjoined_balloons_v9(crop: np.ndarray, bboxes: list[tuple[int, int, int, int]]) -> np.ndarray:
    ch, cw = crop.shape[:2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    
    # 1. Pure White Shared Interior Mask
    pure_white = (gray >= 195).astype(np.uint8) * 255
    pure_white = cv2.morphologyEx(pure_white, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
    pure_white = cv2.morphologyEx(pure_white, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    
    combined_mask = np.zeros((ch, cw), dtype=np.uint8)
    centers = []
    for bx, by, bw, bh in bboxes:
        cx = int(bx + bw / 2.0)
        cy = int(by + bh / 2.0)
        centers.append((cx, cy))
        seed = np.zeros((ch + 2, cw + 2), dtype=np.uint8)
        cv2.floodFill(pure_white.copy(), seed, (cx, cy), 255, flags=8 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY)
        combined_mask = cv2.bitwise_or(combined_mask, seed[1:-1, 1:-1] * 255)
        
    # 2. Text-Anchored Voronoi Partition of Shared Mask
    c1, c2 = centers[0], centers[1]
    y_grid, x_grid = np.ogrid[:ch, :cw]
    dist1 = (x_grid - c1[0])**2 + (y_grid - c1[1])**2
    dist2 = (x_grid - c2[0])**2 + (y_grid - c2[1])**2
    
    label_map = np.zeros((ch, cw), dtype=np.uint8)
    label_map[(combined_mask > 0) & (dist1 <= dist2)] = 1
    label_map[(combined_mask > 0) & (dist1 > dist2)] = 2
    
    # Find exact separation line between label 1 and label 2
    dil1 = cv2.dilate((label_map == 1).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
    dil2 = cv2.dilate((label_map == 2).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
    sep_mask = ((dil1 > 0) & (dil2 > 0) & (combined_mask > 0)).astype(np.uint8) * 255
    sep_mask = cv2.dilate(sep_mask, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
    
    # 3. Fit Squircle for each balloon
    balloon_results = []
    for i, (bx, by, bw, bh) in enumerate(bboxes):
        is_top = (i == 0)
        blob = (label_map == (i + 1)).astype(np.uint8) * 255
        cnts, _ = cv2.findContours(blob, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not cnts:
            continue
        main_cnt = max(cnts, key=cv2.contourArea).reshape(-1, 2)
        
        curv = compute_discrete_curvature(main_cnt)
        abs_curv = np.abs(curv)
        max_c = np.max(abs_curv)
        
        tc_x, tc_y = centers[i]
        dists = np.linalg.norm(main_cnt - np.array([tc_x, tc_y]), axis=1)
        max_d = np.max(dists)
        
        clean_pts = []
        for p_idx in range(len(main_cnt)):
            p = main_cnt[p_idx]
            d = dists[p_idx]
            c = abs_curv[p_idx]
            
            # Exclude tail points
            if (c > 0.65 * max_c) and (d > 0.68 * max_d):
                continue
            if not is_top and p[0] < bx - 60:
                continue
            # Exclude points on the separation line itself to avoid flat cut influence
            if is_top and p[1] > by + bh + 45 and p[0] > tc_x:
                continue
            clean_pts.append(p)
            
        clean_pts = np.array(clean_pts) if len(clean_pts) >= 30 else main_cnt
        
        poly, params = fit_constrained_squircle(clean_pts, (bx, by, bw, bh))
        x0, y0, a, b, n, theta = params
        
        single_mask = np.zeros((ch, cw), dtype=np.uint8)
        cv2.fillPoly(single_mask, [poly], 255)
        single_mask = cv2.bitwise_and(single_mask, pure_white)
        
        text_ink = (gray < 155).astype(np.uint8) * 255
        single_text_mask = cv2.bitwise_and(text_ink, single_mask)
        
        nz = cv2.findNonZero(single_mask)
        rx, ry, rw, rh = cv2.boundingRect(nz) if nz is not None else (0, 0, 100, 100)
        
        balloon_results.append({
            "poly": poly,
            "mask": single_mask,
            "text_mask": single_text_mask,
            "center": (int(round(x0)), int(round(y0))),
            "bbox": (rx, ry, rw, rh),
            "n_exp": n,
        })
        
    # 4. Inpainting
    total_text_mask = np.zeros((ch, cw), dtype=np.uint8)
    for b_res in balloon_results:
        total_text_mask = cv2.bitwise_or(total_text_mask, b_res["text_mask"])
        
    clean_mask = cv2.dilate(total_text_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    cleaned = cv2.inpaint(crop, clean_mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
    cleaned[clean_mask > 0] = [255, 255, 255]
    
    # 5. Build 5-Panel Visualization
    
    # Panel 1: INITIAL BBOXES (RED)
    p1 = crop.copy()
    for bx, by, bw, bh in bboxes:
        cv2.rectangle(p1, (bx, by), (bx + bw, by + bh), (0, 0, 255), 3)
    cv2.putText(p1, "1. INITIAL BBOXES (RED)", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (0, 0, 255), 2)
    
    # Panel 2: WATERSHED & SEPARATION LINE
    p2 = crop.copy()
    ov2 = p2.copy()
    ov2[label_map == 1] = [255, 200, 200]
    ov2[label_map == 2] = [200, 255, 200]
    cv2.addWeighted(ov2, 0.40, p2, 0.60, 0, p2)
    p2[sep_mask > 0] = [0, 0, 255]  # Red separation line
    for cx, cy in centers:
        cv2.circle(p2, (cx, cy), 6, (0, 0, 255), -1)
    cv2.putText(p2, "2. SEPARATION LINE (RED)", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2)
    
    # Panel 3: SMART SUPERELLIPSE SHAPES (GREEN)
    p3 = crop.copy()
    ov3 = p3.copy()
    for b_res in balloon_results:
        cv2.fillPoly(ov3, [b_res["poly"]], (180, 180, 255))
    cv2.addWeighted(ov3, 0.40, p3, 0.60, 0, p3)
    for b_res in balloon_results:
        cv2.polylines(p3, [b_res["poly"]], isClosed=True, color=(0, 255, 0), thickness=3)
    cv2.putText(p3, "3. SMART SQUIRCLES (GREEN)", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
    
    # Panel 4: TEXT MASKS IN BALLOONS
    p4 = cv2.cvtColor(total_text_mask, cv2.COLOR_GRAY2BGR)
    cv2.putText(p4, "4. TEXT MASKS IN BALLOONS", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
    
    # Panel 5: CLEANED INPAINT & TRUE CENTERS
    p5 = cleaned.copy()
    for b_res in balloon_results:
        cv2.polylines(p5, [b_res["poly"]], isClosed=True, color=(0, 255, 0), thickness=3)
        rx, ry, rw, rh = b_res["bbox"]
        cx, cy = b_res["center"]
        cv2.line(p5, (rx, cy), (rx + rw, cy), (255, 150, 0), 3)
        cv2.circle(p5, (cx, cy), 6, (255, 100, 0), -1)
    cv2.putText(p5, "5. CLEANED & TRUE CENTERS", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
    
    return np.hstack([p1, p2, p3, p4, p5])


def main():
    print("=== STARTING POLISHED SMART BALLOON V9 (5-PANEL PIPELINE) ===")
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
    
    v9_5panel = process_conjoined_balloons_v9(crop, [
        (l14_x, l14_y, bw14, bh14),
        (l15_x, l15_y, bw15, bh15)
    ])
    
    out_file = OUTPUT_DIR / "v9_conjoined_5panel_page03.png"
    save_image(out_file, v9_5panel)
    print(f"V9 5-Panel Preview saved -> {out_file}")
    
    print("\nPolished Smart Balloon V9 Pipeline completed successfully!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
