"""Smart Balloon V13: Batch Testing on Chapter 112 Conjoined Balloon Samples.

Located and executed exclusively inside e:\\houmi\\research\\

Implements:
1. Dynamic ROI cropping around conjoined pairs from project.json.
2. 100% Automatic Pinch Apex Detection & Closed-Loop Bézier Reconstruction.
3. 4-Panel High-Definition Visualization for Chapter 112 samples.
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

RESEARCH_DIR = Path(r"e:\houmi\research")
CHAPTER_112_DIR = Path(r"E:\Chapter Download\Kuaikanmanhua\ดาว\112")
OUTPUT_DIR = RESEARCH_DIR / "v13_112_previews"
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
    """Find the 2 physical concave constriction points (waists) on the left and right outer boundaries."""
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


def heal_balloon1_contour_auto(
    combined_cnt: np.ndarray,
    left_waist: np.ndarray,
    right_waist: np.ndarray,
    text_bbox: tuple[int, int, int, int]
) -> np.ndarray:
    bx, by, bw, bh = text_bbox
    main_cnt = combined_cnt.reshape(-1, 2)
    
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


def heal_balloon2_contour_auto(
    combined_cnt: np.ndarray,
    left_waist: np.ndarray,
    right_waist: np.ndarray,
    text_bbox: tuple[int, int, int, int],
    tail_tip: tuple[int, int] | None
) -> np.ndarray:
    bx, by, bw, bh = text_bbox
    main_cnt = combined_cnt.reshape(-1, 2)
    
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


def separate_balloons_voronoi(combined_mask: np.ndarray, text_centers: list[tuple[int, int]]) -> tuple[list[np.ndarray], np.ndarray]:
    ch, cw = combined_mask.shape
    c1, c2 = text_centers[0], text_centers[1]
    
    y_grid, x_grid = np.ogrid[:ch, :cw]
    d1_sq = (x_grid - c1[0])**2 + (y_grid - c1[1])**2
    d2_sq = (x_grid - c2[0])**2 + (y_grid - c2[1])**2
    
    label_map = np.zeros((ch, cw), dtype=np.uint8)
    label_map[(combined_mask > 0) & (d1_sq <= d2_sq)] = 1
    label_map[(combined_mask > 0) & (d2_sq < d1_sq)] = 2
    
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    mask1 = cv2.morphologyEx((label_map == 1).astype(np.uint8) * 255, cv2.MORPH_CLOSE, kernel)
    mask2 = cv2.morphologyEx((label_map == 2).astype(np.uint8) * 255, cv2.MORPH_CLOSE, kernel)
    
    return [mask1, mask2], label_map


def process_conjoined_sample(page_img: np.ndarray, blk1: dict, blk2: dict, sample_name: str) -> np.ndarray | None:
    x1, y1, w1, h1 = int(blk1["x"]), int(blk1["y"]), int(blk1["width"]), int(blk1["height"])
    x2, y2, w2, h2 = int(blk2["x"]), int(blk2["y"]), int(blk2["width"]), int(blk2["height"])
    
    # Sort top to bottom
    if y1 > y2:
        x1, y1, w1, h1, x2, y2, w2, h2 = x2, y2, w2, h2, x1, y1, w1, h1
        blk1, blk2 = blk2, blk1
        
    pad = 120
    min_x = max(0, min(x1, x2) - pad)
    min_y = max(0, min(y1, y2) - pad)
    max_x = min(page_img.shape[1], max(x1 + w1, x2 + w2) + pad)
    max_y = min(page_img.shape[0], max(y1 + h1, y2 + h2) + pad)
    
    crop = page_img[min_y:max_y, min_x:max_x].copy()
    ch, cw = crop.shape[:2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    
    l1_x, l1_y = x1 - min_x, y1 - min_y
    l2_x, l2_y = x2 - min_x, y2 - min_y
    
    text_blocks = [
        {"bbox": (l1_x, l1_y, w1, h1), "text": blk1.get("text", "")},
        {"bbox": (l2_x, l2_y, w2, h2), "text": blk2.get("text", "")}
    ]
    
    # Extract white interior
    pure_white = (gray >= 195).astype(np.uint8) * 255
    pure_white = cv2.morphologyEx(pure_white, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
    pure_white = cv2.morphologyEx(pure_white, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    
    combined_mask = np.zeros((ch, cw), dtype=np.uint8)
    text_centers = []
    for blk in text_blocks:
        bx, by, bw, bh = blk["bbox"]
        cx = int(bx + bw / 2.0)
        cy = int(by + bh / 2.0)
        text_centers.append((cx, cy))
        seed = np.zeros((ch + 2, cw + 2), dtype=np.uint8)
        cv2.floodFill(pure_white.copy(), seed, (cx, cy), 255, flags=8 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY)
        combined_mask = cv2.bitwise_or(combined_mask, seed[1:-1, 1:-1] * 255)
        
    cnts, _ = cv2.findContours(combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        return None
    combined_cnt = max(cnts, key=cv2.contourArea)
    
    left_waist, right_waist = find_true_waist_concave_points(combined_cnt, text_centers[0], text_centers[1])
    tail_tip2 = detect_tail_tip(combined_cnt, text_centers[1])
    
    separated_masks, label_map = separate_balloons_voronoi(combined_mask, text_centers)
    
    poly1 = heal_balloon1_contour_auto(combined_cnt, left_waist, right_waist, text_blocks[0]["bbox"])
    poly2 = heal_balloon2_contour_auto(combined_cnt, left_waist, right_waist, text_blocks[1]["bbox"], tail_tip2)
    
    mask1 = np.zeros((ch, cw), dtype=np.uint8)
    cv2.fillPoly(mask1, [poly1], 255)
    mask2 = np.zeros((ch, cw), dtype=np.uint8)
    cv2.fillPoly(mask2, [poly2], 255)
    
    balloon_data = [
        {"id": 1, "text": text_blocks[0]["text"], "contour": poly1, "tail_tip": None, "mask": mask1},
        {"id": 2, "text": text_blocks[1]["text"], "contour": poly2, "tail_tip": tail_tip2, "mask": mask2},
    ]
    
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
    
    # 4 Panels
    p1 = crop.copy()
    for blk in text_blocks:
        bx, by, bw, bh = blk["bbox"]
        cv2.rectangle(p1, (bx, by), (bx + bw, by + bh), (0, 0, 255), 3)
    cv2.putText(p1, "1. INITIAL BBOXES", (15, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2)
    
    p2 = crop.copy()
    ov2 = p2.copy()
    ov2[label_map == 1] = [255, 190, 190]
    ov2[label_map == 2] = [190, 255, 190]
    cv2.addWeighted(ov2, 0.45, p2, 0.55, 0, p2)
    cv2.circle(p2, text_centers[0], 6, (255, 0, 0), -1)
    cv2.circle(p2, text_centers[1], 6, (0, 180, 0), -1)
    cv2.circle(p2, tuple(left_waist), 7, (0, 0, 255), -1)
    cv2.circle(p2, tuple(right_waist), 7, (0, 0, 255), -1)
    cv2.putText(p2, "2. SEPARATED + WAISTS", (15, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 150, 255), 2)
    
    p3 = crop.copy()
    ov3 = p3.copy()
    for b_item in balloon_data:
        cv2.fillPoly(ov3, [b_item["contour"]], (240, 240, 255))
    cv2.addWeighted(ov3, 0.35, p3, 0.65, 0, p3)
    for b_item in balloon_data:
        cv2.drawContours(p3, [b_item["contour"]], -1, (0, 255, 0), 3)
        if b_item["tail_tip"] is not None:
            cv2.circle(p3, b_item["tail_tip"], 7, (0, 0, 255), -1)
    cv2.putText(p3, "3. 2 DYNAMIC LOOPS", (15, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
    
    p4 = cleaned.copy()
    for b_item in balloon_data:
        cv2.drawContours(p4, [b_item["contour"]], -1, (0, 255, 0), 3)
        rx, ry, rw, rh = b_item["bbox"]
        cx, cy = b_item["center"]
        cv2.line(p4, (rx, cy), (rx + rw, cy), (255, 150, 0), 3)
        cv2.circle(p4, (cx, cy), 6, (255, 100, 0), -1)
    cv2.putText(p4, "4. CLEANED & CENTERS", (15, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
    
    out_img = np.hstack([p1, p2, p3, p4])
    out_file = OUTPUT_DIR / f"v13_112_{sample_name}.png"
    save_image(out_file, out_img)
    print(f"Processed {sample_name} -> {out_file}")
    return out_img


def main():
    print("=== TESTING SMART BALLOON V13 ON CHAPTER 112 ===")
    proj = json.load(open(CHAPTER_112_DIR / "project.json", encoding="utf-8"))
    
    # Test cases:
    # 1. Page 10 Pair #1 & #2
    # 2. Page 11 Pair #1 & #2
    # 3. Page 15 Pair #1 & #2
    # 4. Page 20 Pair #1 & #2
    
    test_specs = [
        {"page_num": 10, "b_indices": (0, 1), "name": "page10_pair1_2"},
        {"page_num": 11, "b_indices": (0, 1), "name": "page11_pair1_2"},
        {"page_num": 15, "b_indices": (0, 1), "name": "page15_pair1_2"},
        {"page_num": 20, "b_indices": (0, 1), "name": "page20_pair1_2"},
    ]
    
    for spec in test_specs:
        p_data = [p for p in proj["pages"] if p["page_number"] == spec["page_num"]][0]
        img_name = f"{spec['page_num']:02d}.jpg"
        page_img = load_image(CHAPTER_112_DIR / img_name)
        if page_img is None:
            print(f"Failed to load {img_name}")
            continue
            
        b1 = p_data["text_blocks"][spec["b_indices"][0]]
        b2 = p_data["text_blocks"][spec["b_indices"][1]]
        
        t0 = time.time()
        process_conjoined_sample(page_img, b1, b2, spec["name"])
        print(f"  Took {time.time() - t0:.2f}s")
        
    print("\nBatch testing on Chapter 112 completed successfully!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
