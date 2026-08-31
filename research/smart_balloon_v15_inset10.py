"""Smart Balloon V15: 10% Safe Boundary Inset for Typesetting & Placement.

Located and executed exclusively inside e:\\houmi\\research\\

Implements:
1. Pure Raw Mask Feature Preservation.
2. Centroid-Anchored 10% Safe Margin Inset:
   P_inset = Centroid + 0.90 * (P - Centroid)
3. Visual comparison of Outer Border vs. 10% Inset Safe Zone.
4. 4-Panel High-Definition Visualization with Inset Text Margins.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
import cv2
import numpy as np
from pathlib import Path
from scipy.ndimage import gaussian_filter1d
from typing import Literal

RESEARCH_DIR = Path(r"e:\houmi\research")
CHAPTER_112_DIR = Path(r"E:\Chapter Download\Kuaikanmanhua\ดาว\112")
PROJECT_350_DIR = Path(r"E:\Chapter Download\Kuaikanmanhua\ลิขิตตัวร้าย\350")
OUTPUT_DIR = RESEARCH_DIR / "v15_inset_previews"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

COLOR_MAP = {
    "SPIKY_FUZZY": (255, 100, 255),   # Purple / Violet
    "RECTANGULAR": (255, 150, 50),    # Cyan
    "ANGULAR": (80, 220, 100),        # Lime Green
    "SMOOTH_OVAL": (50, 180, 255)     # Orange
}


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


def compute_edge_roughness(contour: np.ndarray) -> float:
    pts = contour.reshape(-1, 2).astype(np.float32)
    if len(pts) < 15:
        return 0.0
    M = cv2.moments(contour)
    if M["m00"] <= 0:
        return 0.0
    cx, cy = M["m10"] / M["m00"], M["m01"] / M["m00"]
    distances = np.linalg.norm(pts - np.array([cx, cy], dtype=np.float32), axis=1)
    smooth_dist = gaussian_filter1d(distances, sigma=12.0, mode="wrap")
    return float(np.std(distances - smooth_dist))


def compute_rectangularity(contour: np.ndarray) -> tuple[float, float]:
    rect = cv2.minAreaRect(contour)
    box = cv2.boxPoints(rect)
    box_area = cv2.contourArea(box)
    contour_area = cv2.contourArea(contour)
    rect_ratio = (contour_area / box_area) if box_area > 0 else 0.0
    w, h = rect[1]
    aspect_ratio = max(w, h) / (min(w, h) + 1e-6)
    return float(rect_ratio), float(aspect_ratio)


def count_corners(contour: np.ndarray) -> int:
    perimeter = cv2.arcLength(contour, True)
    epsilon = 0.015 * perimeter
    approx = cv2.approxPolyDP(contour, epsilon, True)
    return len(approx)


def classify_instance_shape(contour: np.ndarray, text_bbox: tuple[int, int, int, int]) -> tuple[str, dict]:
    roughness = compute_edge_roughness(contour)
    rect_ratio, aspect_ratio = compute_rectangularity(contour)
    corner_count = count_corners(contour)
    
    meta = {
        "roughness": round(roughness, 2),
        "rect_ratio": round(rect_ratio, 2),
        "corner_count": corner_count,
        "aspect": round(aspect_ratio, 2)
    }
    
    if roughness > 1.8:
        return "SPIKY_FUZZY", meta
    elif rect_ratio > 0.82 and aspect_ratio > 1.6:
        return "RECTANGULAR", meta
    elif corner_count <= 10 and rect_ratio < 0.80:
        return "ANGULAR", meta
    else:
        return "SMOOTH_OVAL", meta


def detect_tail_tip(main_cnt: np.ndarray, text_center: tuple[int, int]) -> tuple[int, int] | None:
    tc_x, tc_y = text_center
    pts = main_cnt.reshape(-1, 2)
    if len(pts) < 10:
        return None
    dists = np.linalg.norm(pts - np.array([tc_x, tc_y]), axis=1)
    pts_f = pts.astype(np.float64)
    x = gaussian_filter1d(pts_f[:, 0], sigma=2.0, mode="wrap")
    y = gaussian_filter1d(pts_f[:, 1], sigma=2.0, mode="wrap")
    dx = np.gradient(x)
    dy = np.gradient(y)
    ddx = np.gradient(dx)
    ddy = np.gradient(dy)
    denom = np.maximum((dx**2 + dy**2)**1.5, 1e-6)
    curv = np.abs((dx * ddy - dy * ddx) / denom)
    
    max_d = np.max(dists)
    tail_candidates = [i for i in range(len(pts)) if dists[i] > 0.70 * max_d and curv[i] > np.percentile(curv, 80)]
    if tail_candidates:
        best_idx = max(tail_candidates, key=lambda i: dists[i])
        return int(pts[best_idx, 0]), int(pts[best_idx, 1])
    return None


def find_true_waist_concave_points(
    combined_cnt: np.ndarray, 
    c1: tuple[int, int], 
    c2: tuple[int, int]
) -> tuple[np.ndarray, np.ndarray]:
    pts = combined_cnt.reshape(-1, 2)
    y_mid = (c1[1] + c2[1]) / 2.0
    x_mid = (c1[0] + c2[0]) / 2.0
    y_span = max(60.0, abs(c1[1] - c2[1]) * 0.40)
    y_min, y_max = y_mid - y_span, y_mid + y_span
    
    left_pts = [p for p in pts if y_min <= p[1] <= y_max and p[0] < x_mid]
    right_pts = [p for p in pts if y_min <= p[1] <= y_max and p[0] >= x_mid]
    
    if left_pts:
        left_waist = max(left_pts, key=lambda p: p[0])
    else:
        left_waist = np.array([int(x_mid - 250), int(y_mid)])
        
    if right_pts:
        right_waist = min(right_pts, key=lambda p: p[0])
    else:
        right_waist = np.array([int(x_mid + 250), int(y_mid)])
        
    return left_waist, right_waist


def reconstruct_raw_balloon_top(
    raw_combined_cnt: np.ndarray,
    left_waist: np.ndarray,
    right_waist: np.ndarray,
    text_bbox: tuple[int, int, int, int]
) -> np.ndarray:
    bx, by, bw, bh = text_bbox
    main_cnt = raw_combined_cnt.reshape(-1, 2)
    idx1 = min(range(len(main_cnt)), key=lambda i: np.linalg.norm(main_cnt[i] - left_waist))
    idx2 = min(range(len(main_cnt)), key=lambda i: np.linalg.norm(main_cnt[i] - right_waist))
    
    if idx1 < idx2:
        seg_a = main_cnt[idx1:idx2+1]
        seg_b = np.vstack([main_cnt[idx2:], main_cnt[:idx1+1]])
    else:
        seg_a = main_cnt[idx2:idx1+1]
        seg_b = np.vstack([main_cnt[idx1:], main_cnt[:idx2+1]])
        
    top_seg = seg_a if seg_a[:, 1].mean() < seg_b[:, 1].mean() else seg_b
    p_start = top_seg[-1].astype(np.float32)
    p_end = top_seg[0].astype(np.float32)
    
    mid_x = (p_start[0] + p_end[0]) / 2.0
    ctrl_y = float(max(by + bh + 35, max(p_start[1], p_end[1]) + 15))
    
    t_vals = np.linspace(0, 1, 50)
    bottom_arc = []
    for t in t_vals:
        px = (1 - t)**2 * p_start[0] + 2 * (1 - t) * t * mid_x + t**2 * p_end[0]
        py = (1 - t)**2 * p_start[1] + 2 * (1 - t) * t * ctrl_y + t**2 * p_end[1]
        bottom_arc.append([int(round(px)), int(round(py))])
        
    full_poly = np.vstack([top_seg, np.array(bottom_arc)])
    return full_poly.reshape(-1, 1, 2)


def reconstruct_raw_balloon_bottom(
    raw_combined_cnt: np.ndarray,
    left_waist: np.ndarray,
    right_waist: np.ndarray,
    text_bbox: tuple[int, int, int, int],
    tail_tip: tuple[int, int] | None
) -> np.ndarray:
    bx, by, bw, bh = text_bbox
    main_cnt = raw_combined_cnt.reshape(-1, 2)
    idx1 = min(range(len(main_cnt)), key=lambda i: np.linalg.norm(main_cnt[i] - left_waist))
    idx2 = min(range(len(main_cnt)), key=lambda i: np.linalg.norm(main_cnt[i] - right_waist))
    
    if idx1 < idx2:
        seg_a = main_cnt[idx1:idx2+1]
        seg_b = np.vstack([main_cnt[idx2:], main_cnt[:idx1+1]])
    else:
        seg_a = main_cnt[idx2:idx1+1]
        seg_b = np.vstack([main_cnt[idx1:], main_cnt[:idx2+1]])
        
    bottom_seg = seg_a if seg_a[:, 1].mean() > seg_b[:, 1].mean() else seg_b
    p_start = bottom_seg[-1].astype(np.float32)
    p_end = bottom_seg[0].astype(np.float32)
    
    mid_x = (p_start[0] + p_end[0]) / 2.0
    ctrl_y = float(min(by - 15, min(p_start[1], p_end[1]) - 15))
    
    t_vals = np.linspace(0, 1, 50)
    top_arc = []
    for t in t_vals:
        px = (1 - t)**2 * p_start[0] + 2 * (1 - t) * t * mid_x + t**2 * p_end[0]
        py = (1 - t)**2 * p_start[1] + 2 * (1 - t) * t * ctrl_y + t**2 * p_end[1]
        top_arc.append([int(round(px)), int(round(py))])
        
    full_poly = np.vstack([bottom_seg, np.array(top_arc)])
    return full_poly.reshape(-1, 1, 2)


# =========================================================================
# 10% Inset / Safe Margin Transform
# =========================================================================
def apply_contour_inset_10pct(contour: np.ndarray, scale_factor: float = 0.90) -> np.ndarray:
    """Scales a closed contour inward by 10% towards its centroid (Safe Text Margin)."""
    pts = contour.reshape(-1, 2).astype(np.float32)
    M = cv2.moments(contour)
    if M["m00"] > 0:
        cx = M["m10"] / M["m00"]
        cy = M["m01"] / M["m00"]
    else:
        cx = np.mean(pts[:, 0])
        cy = np.mean(pts[:, 1])
        
    center = np.array([cx, cy], dtype=np.float32)
    # P_inset = Center + scale * (P - Center)
    inset_pts = center + scale_factor * (pts - center)
    return inset_pts.astype(np.int32).reshape(-1, 1, 2)


def process_sample_with_10pct_inset(
    page_img: np.ndarray,
    blk1: dict,
    blk2: dict,
    sample_name: str
) -> tuple[np.ndarray | None, dict]:
    t0 = time.time()
    
    bx1, by1, bw1, bh1 = int(blk1["x"]), int(blk1["y"]), int(blk1["width"]), int(blk1["height"])
    bx2, by2, bw2, bh2 = int(blk2["x"]), int(blk2["y"]), int(blk2["width"]), int(blk2["height"])
    
    if by1 > by2:
        bx1, by1, bw1, bh1, bx2, by2, bw2, bh2 = bx2, by2, bw2, bh2, bx1, by1, bw1, bh1
        blk1, blk2 = blk2, blk1
        
    pad = 120
    min_x = max(0, min(bx1, bx2) - pad)
    min_y = max(0, min(by1, by2) - pad)
    max_x = min(page_img.shape[1], max(bx1 + bw1, bx2 + bw2) + pad)
    max_y = min(page_img.shape[0], max(by1 + bh1, by2 + bh2) + pad)
    
    crop = page_img[min_y:max_y, min_x:max_x].copy()
    ch, cw = crop.shape[:2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    
    adjusted_blocks = [
        {"bbox": (bx1 - min_x, by1 - min_y, bw1, bh1), "text": blk1.get("text", "")},
        {"bbox": (bx2 - min_x, by2 - min_y, bw2, bh2), "text": blk2.get("text", "")}
    ]
    
    # 1. 100% Raw white interior extraction
    raw_white = (gray >= 180).astype(np.uint8) * 255
    
    combined_mask = np.zeros((ch, cw), dtype=np.uint8)
    text_centers = []
    for blk in adjusted_blocks:
        bx, by, bw, bh = blk["bbox"]
        cx = int(bx + bw / 2.0)
        cy = int(by + bh / 2.0)
        text_centers.append((cx, cy))
        seed = np.zeros((ch + 2, cw + 2), dtype=np.uint8)
        cv2.floodFill(raw_white.copy(), seed, (cx, cy), 255, flags=8 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY)
        combined_mask = cv2.bitwise_or(combined_mask, seed[1:-1, 1:-1] * 255)
        
    cnts, _ = cv2.findContours(combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        return None, {}
    raw_combined_cnt = max(cnts, key=cv2.contourArea)
    
    # 2. Pre-classify on raw un-blurred instance shapes
    y_grid, x_grid = np.ogrid[:ch, :cw]
    d1_sq = (x_grid - text_centers[0][0])**2 + (y_grid - text_centers[0][1])**2
    d2_sq = (x_grid - text_centers[1][0])**2 + (y_grid - text_centers[1][1])**2
    raw_lbl = np.zeros((ch, cw), dtype=np.uint8)
    raw_lbl[(combined_mask > 0) & (d1_sq <= d2_sq)] = 1
    raw_lbl[(combined_mask > 0) & (d2_sq < d1_sq)] = 2
    
    balloon_types = []
    for b_idx in (1, 2):
        inst_m = (raw_lbl == b_idx).astype(np.uint8) * 255
        i_cnts, _ = cv2.findContours(inst_m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        i_main = max(i_cnts, key=cv2.contourArea) if i_cnts else raw_combined_cnt
        b_type, meta = classify_instance_shape(i_main, adjusted_blocks[b_idx-1]["bbox"])
        balloon_types.append(b_type)
        
    type1, type2 = balloon_types[0], balloon_types[1]
    
    # 3. Dynamic Waist Constriction Detection
    left_waist, right_waist = find_true_waist_concave_points(raw_combined_cnt, text_centers[0], text_centers[1])
    tail_tip2 = detect_tail_tip(raw_combined_cnt, text_centers[1])
    
    # 4. Reconstruct Full Boundary
    poly1_full = reconstruct_raw_balloon_top(raw_combined_cnt, left_waist, right_waist, adjusted_blocks[0]["bbox"])
    poly2_full = reconstruct_raw_balloon_bottom(raw_combined_cnt, left_waist, right_waist, adjusted_blocks[1]["bbox"], tail_tip2)
    
    # 5. Apply 10% Inset / Safe Margin Transform
    poly1_inset = apply_contour_inset_10pct(poly1_full, scale_factor=0.90)
    poly2_inset = apply_contour_inset_10pct(poly2_full, scale_factor=0.90)
    
    mask1 = np.zeros((ch, cw), dtype=np.uint8)
    cv2.fillPoly(mask1, [poly1_full], 255)
    mask2 = np.zeros((ch, cw), dtype=np.uint8)
    cv2.fillPoly(mask2, [poly2_full], 255)
    
    balloon_data = [
        {"id": 1, "type": type1, "text": adjusted_blocks[0]["text"], "contour_full": poly1_full, "contour_inset": poly1_inset, "tail_tip": None, "mask": mask1},
        {"id": 2, "type": type2, "text": adjusted_blocks[1]["text"], "contour_full": poly2_full, "contour_inset": poly2_inset, "tail_tip": tail_tip2, "mask": mask2},
    ]
    
    # Inpaint text
    total_text_mask = np.zeros((ch, cw), dtype=np.uint8)
    text_ink = (gray < 155).astype(np.uint8) * 255
    for b_item in balloon_data:
        t_mask = cv2.bitwise_and(text_ink, b_item["mask"])
        total_text_mask = cv2.bitwise_or(total_text_mask, t_mask)
        M = cv2.moments(b_item["mask"])
        cx = int(M["m10"] / M["m00"]) if M["m00"] > 0 else text_centers[b_item["id"]-1][0]
        cy = int(M["m01"] / M["m00"]) if M["m00"] > 0 else text_centers[b_item["id"]-1][1]
        nz = cv2.findNonZero(b_item["mask"])
        rx, ry, rw, rh = cv2.boundingRect(nz) if nz is not None else (0, 0, 100, 100)
        b_item["center"] = (cx, cy)
        b_item["bbox"] = (rx, ry, rw, rh)
        
    clean_mask = cv2.dilate(total_text_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    cleaned = crop.copy()
    cleaned[clean_mask > 0] = [255, 255, 255]
    
    # 6. Render 4 Panels
    # Panel 1: Initial BBoxes
    p1 = crop.copy()
    for blk in adjusted_blocks:
        bx, by, bw, bh = blk["bbox"]
        cv2.rectangle(p1, (bx, by), (bx + bw, by + bh), (0, 0, 255), 3)
    cv2.putText(p1, "1. INITIAL BBOXES", (15, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2)
    
    # Panel 2: Outer vs 10% Inset Comparison
    p2 = crop.copy()
    for b_item in balloon_data:
        b_col = COLOR_MAP.get(b_item["type"], (0, 255, 0))
        # Outer border in thin white/gray
        cv2.drawContours(p2, [b_item["contour_full"]], -1, (180, 180, 180), 2)
        # 10% Inset Safe Margin in thick color
        cv2.drawContours(p2, [b_item["contour_inset"]], -1, b_col, 3)
    cv2.putText(p2, "2. FULL vs 10% INSET", (15, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 150, 255), 2)
    
    # Panel 3: 10% Inset Safe Zones Filled
    p3 = crop.copy()
    ov3 = p3.copy()
    for b_item in balloon_data:
        cv2.fillPoly(ov3, [b_item["contour_inset"]], (240, 240, 255))
    cv2.addWeighted(ov3, 0.40, p3, 0.60, 0, p3)
    for b_item in balloon_data:
        b_col = COLOR_MAP.get(b_item["type"], (0, 255, 0))
        cv2.drawContours(p3, [b_item["contour_inset"]], -1, b_col, 2)
        if b_item["tail_tip"] is not None:
            cv2.circle(p3, b_item["tail_tip"], 7, (0, 0, 255), -1)
    cv2.putText(p3, "3. 10% INSET SAFE ZONES", (15, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
    
    # Panel 4: Cleaned + 10% Inset + True Centers
    p4 = cleaned.copy()
    for b_item in balloon_data:
        b_col = COLOR_MAP.get(b_item["type"], (0, 255, 0))
        cv2.drawContours(p4, [b_item["contour_full"]], -1, (200, 200, 200), 1)
        cv2.drawContours(p4, [b_item["contour_inset"]], -1, b_col, 2)
        rx, ry, rw, rh = b_item["bbox"]
        cx, cy = b_item["center"]
        cv2.line(p4, (rx, cy), (rx + rw, cy), (255, 150, 0), 3)
        cv2.circle(p4, (cx, cy), 6, (255, 100, 0), -1)
    cv2.putText(p4, "4. INPAINT + 10% SAFE BOUNDS", (15, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
    
    out_img = np.hstack([p1, p2, p3, p4])
    out_file = OUTPUT_DIR / f"v15_inset10_{sample_name}.png"
    save_image(out_file, out_img)
    elapsed = time.time() - t0
    print(f"  Processed {sample_name} in {elapsed:.2f}s -> {out_file}\n")
    return out_img, {"type1": type1, "type2": type2, "time": elapsed}


def main():
    print("=== STARTING SMART BALLOON V15 (10% SAFE INSET PIPELINE) ===")
    proj_112 = json.load(open(CHAPTER_112_DIR / "project.json", encoding="utf-8"))
    
    # 1. Page 10 (SPIKY_FUZZY)
    p10_data = [p for p in proj_112["pages"] if p["page_number"] == 10][0]
    p10_img = load_image(CHAPTER_112_DIR / "10.jpg")
    process_sample_with_10pct_inset(p10_img, p10_data["text_blocks"][0], p10_data["text_blocks"][1], "page10_spiky")
    
    # 2. Page 20 (ANGULAR)
    p20_data = [p for p in proj_112["pages"] if p["page_number"] == 20][0]
    p20_img = load_image(CHAPTER_112_DIR / "20.jpg")
    process_sample_with_10pct_inset(p20_img, p20_data["text_blocks"][0], p20_data["text_blocks"][1], "page20_angular")
    
    # 3. Chapter 350 Page 3 (SMOOTH_OVAL)
    proj_350 = json.load(open(PROJECT_350_DIR / "project.json", encoding="utf-8"))
    p3_data = [p for p in proj_350["pages"] if p["page_number"] == 3][0]
    p3_img = load_image(PROJECT_350_DIR / "03.jpg")
    process_sample_with_10pct_inset(p3_img, p3_data["text_blocks"][1], p3_data["text_blocks"][2], "page03_smooth_oval")
    
    # 4. Page 11 (RECTANGULAR)
    p11_data = [p for p in proj_112["pages"] if p["page_number"] == 11][0]
    p11_img = load_image(CHAPTER_112_DIR / "11.jpg")
    process_sample_with_10pct_inset(p11_img, p11_data["text_blocks"][0], p11_data["text_blocks"][1], "page11_rectangular")
    
    print("\nSmart Balloon V15 Inset testing completed successfully!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
