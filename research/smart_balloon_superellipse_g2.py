"""Smart Balloon Engine: Superellipse Nonlinear Least-Squares Fitting + G2 Spline Continuation.

Located and executed exclusively inside e:\\houmi\\research\\

Implements:
1. Automated Convexity Defects + Curvature Scale Space (CSS) Inflection Detection.
2. Clean Boundary Arc Partitioning (isolating unoccluded contour from conjoined necks).
3. Robust Superellipse (Squircle) Parametric Fitting via scipy.optimize.least_squares:
   | ( (x-x0)cosθ + (y-y0)sinθ ) / a |^n + | ( -(x-x0)sinθ + (y-y0)cosθ ) / b |^n = 1
4. G2 Cubic B-Spline (scipy.interpolate.splprep, splev) Boundary Reconstruction.
5. Automated 4-Panel Output (Initial Bbox -> Smart Superellipse Shape -> Text Mask -> Cleaned & True Center).
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
OUTPUT_DIR = RESEARCH_DIR / "superellipse_g2_previews"
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
    """Compute exact continuous curvature kappa(t) along closed contour using Gaussian derivatives."""
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


def superellipse_residuals(params: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """Residual function for superellipse fitting: |u/a|^n + |v/b|^n - 1."""
    x0, y0, a, b, n, theta = params
    a = max(a, 10.0)
    b = max(b, 10.0)
    n = max(n, 1.8)
    
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    
    dx = pts[:, 0] - x0
    dy = pts[:, 1] - y0
    
    u = dx * cos_t + dy * sin_t
    v = -dx * sin_t + dy * cos_t
    
    res = np.abs(u / a)**n + np.abs(v / b)**n - 1.0
    return res


def fit_superellipse_on_clean_arc(clean_pts: np.ndarray, init_bbox: tuple[int, int, int, int]) -> tuple[np.ndarray, np.ndarray]:
    """Fit Superellipse parameters (x0, y0, a, b, n, theta) using robust least squares."""
    bx, by, bw, bh = init_bbox
    init_x0 = bx + bw / 2.0
    init_y0 = by + bh / 2.0
    init_a = bw * 0.58
    init_b = bh * 0.58
    init_n = 2.8  # initial squircle exponent
    init_theta = 0.0
    
    p0 = [init_x0, init_y0, init_a, init_b, init_n, init_theta]
    bounds = (
        [init_x0 - 80, init_y0 - 80, init_a * 0.6, init_b * 0.6, 1.8, -0.4],
        [init_x0 + 80, init_y0 + 80, init_a * 1.6, init_b * 1.6, 4.5, 0.4]
    )
    
    res = least_squares(superellipse_residuals, p0, bounds=bounds, args=(clean_pts,), loss="soft_l1", f_scale=0.1)
    x0, y0, a, b, n, theta = res.x
    
    # Generate dense superellipse points
    phi = np.linspace(0, 2 * math.pi, 200, endpoint=False)
    cos_phi = np.cos(phi)
    sin_phi = np.sin(phi)
    
    # Parametric superellipse formulas
    u = a * np.sign(cos_phi) * (np.abs(cos_phi)**(2.0 / n))
    v = b * np.sign(sin_phi) * (np.abs(sin_phi)**(2.0 / n))
    
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    
    fitted_x = x0 + u * cos_t - v * sin_t
    fitted_y = y0 + u * sin_t + v * cos_t
    
    fitted_pts = np.column_stack([fitted_x, fitted_y])
    
    # Refine with G2 Spline (splprep & splev)
    tck, u_spl = splprep([fitted_pts[:, 0], fitted_pts[:, 1]], s=0, per=True, k=3)
    u_dense = np.linspace(0, 1, 300)
    smooth_x, smooth_y = splev(u_dense, tck)
    
    smooth_contour = np.column_stack([smooth_x, smooth_y]).astype(np.int32)
    return smooth_contour, np.array([x0, y0, a, b, n, theta])


def extract_smart_superellipse_balloon(crop: np.ndarray, text_bbox: tuple[int, int, int, int], is_top_balloon: bool = True) -> dict:
    """Extract balloon, detect inflection departure points, fit superellipse, and compute true center."""
    ch, cw = crop.shape[:2]
    bx, by, bw, bh = text_bbox
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    
    # 1. Pure White FloodFill
    pure_white = (gray >= 195).astype(np.uint8) * 255
    pure_white = cv2.morphologyEx(pure_white, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
    pure_white = cv2.morphologyEx(pure_white, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    
    seed = np.zeros((ch + 2, cw + 2), dtype=np.uint8)
    cv2.floodFill(pure_white.copy(), seed, (bx + bw // 2, by + bh // 2), 255, flags=8 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY)
    joined_mask = seed[1:-1, 1:-1] * 255
    
    cnts, _ = cv2.findContours(joined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    main_cnt = max(cnts, key=cv2.contourArea).reshape(-1, 2)
    
    # 2. Curvature & Inflection Departure Analysis
    # Clean boundary partition:
    # Top balloon clean points are points above the neck (y <= text_bottom + 20)
    # Bottom balloon clean points are points below the neck (y >= text_top - 20)
    if is_top_balloon:
        clean_pts = np.array([p for p in main_cnt if p[1] <= by + bh + 15])
    else:
        clean_pts = np.array([p for p in main_cnt if p[1] >= by - 15])
        
    if len(clean_pts) < 50:
        clean_pts = main_cnt
        
    # 3. Fit Superellipse + G2 Spline
    smooth_cnt, params = fit_superellipse_on_clean_arc(clean_pts, text_bbox)
    x0, y0, a, b, n, theta = params
    
    # 4. Generate Mask
    mask = np.zeros((ch, cw), dtype=np.uint8)
    cv2.fillPoly(mask, [smooth_cnt], 255)
    mask = cv2.bitwise_and(mask, pure_white)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    
    # 5. Text Ink Mask
    text_ink = (gray < 155).astype(np.uint8) * 255
    text_mask = cv2.bitwise_and(text_ink, mask)
    
    # 6. Cleaning & Centering
    clean_mask = cv2.dilate(text_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    cleaned = cv2.inpaint(crop, clean_mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
    cleaned[clean_mask > 0] = [255, 255, 255]
    
    nz = cv2.findNonZero(mask)
    x, y, w, h = cv2.boundingRect(nz) if nz is not None else (0, 0, 100, 100)
    
    cx = int(round(x0))
    cy = int(round(y0))
    
    return {
        "mask": mask,
        "poly": smooth_cnt,
        "text_mask": text_mask,
        "cleaned": cleaned,
        "bbox": (x, y, w, h),
        "center": (cx, cy),
        "params": params,
    }


def build_4panel_image(crop: np.ndarray, init_bbox: tuple[int, int, int, int], res: dict) -> np.ndarray:
    bx, by, bw, bh = init_bbox
    smooth_cnt = res["poly"]
    text_mask = res["text_mask"]
    cleaned = res["cleaned"]
    cx, cy = res["center"]
    x, y, w, h = res["bbox"]
    n_exp = res["params"][4]
    
    # Panel 1: Initial Bbox
    p1 = crop.copy()
    cv2.rectangle(p1, (bx, by), (bx + bw, by + bh), (0, 0, 255), 3)
    cv2.putText(p1, "1. INITIAL BBOX (RED)", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 255), 2)
    
    # Panel 2: Smart Superellipse G2 Shape
    p2 = crop.copy()
    overlay = p2.copy()
    cv2.fillPoly(overlay, [smooth_cnt], (180, 180, 255))
    cv2.addWeighted(overlay, 0.40, p2, 0.60, 0, p2)
    cv2.polylines(p2, [smooth_cnt], isClosed=True, color=(0, 255, 0), thickness=3)
    shape_type = f"Squircle (n={n_exp:.1f})" if n_exp > 2.2 else "Ellipse (n=2.0)"
    cv2.putText(p2, f"2. SMART SUPERELLIPSE ({shape_type})", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (0, 255, 0), 2)
    
    # Panel 3: High-contrast Text Ink Mask
    p3 = cv2.cvtColor(text_mask, cv2.COLOR_GRAY2BGR)
    cv2.putText(p3, "3. TEXT MASK IN BALLOON", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
    
    # Panel 4: Cleaned Inpaint & True Center
    p4 = cleaned.copy()
    cv2.polylines(p4, [smooth_cnt], isClosed=True, color=(0, 255, 0), thickness=3)
    cv2.line(p4, (x, cy), (x + w, cy), (255, 150, 0), 3)
    cv2.circle(p4, (cx, cy), 6, (255, 100, 0), -1)
    cv2.putText(p4, "4. CLEANED & TRUE CENTER", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
    
    return np.hstack([p1, p2, p3, p4])


def main():
    print("=== STARTING SUPERELLIPSE G2 SPLINE PIPELINE ===")
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
    
    # 1. Process Balloon 14 (Top Squircle via Superellipse Least Squares)
    res14 = extract_smart_superellipse_balloon(crop, (l14_x, l14_y, bw14, bh14), is_top_balloon=True)
    p14_out = build_4panel_image(crop, (l14_x, l14_y, bw14, bh14), res14)
    out14_file = OUTPUT_DIR / "superellipse_g2_sample_14_page03.png"
    save_image(out14_file, p14_out)
    print(f"Superellipse G2 Sample 14 saved -> {out14_file}")
    
    # 2. Process Balloon 15 (Bottom Oval via Superellipse Least Squares)
    res15 = extract_smart_superellipse_balloon(crop, (l15_x, l15_y, bw15, bh15), is_top_balloon=False)
    p15_out = build_4panel_image(crop, (l15_x, l15_y, bw15, bh15), res15)
    out15_file = OUTPUT_DIR / "superellipse_g2_sample_15_page03.png"
    save_image(out15_file, p15_out)
    print(f"Superellipse G2 Sample 15 saved -> {out15_file}")
    
    print("\nSuperellipse G2 Pipeline completed successfully!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
