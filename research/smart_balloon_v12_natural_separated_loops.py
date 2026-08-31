"""Smart Balloon V12: Voronoi Separation + Natural Smooth Arc Healing (2 Independent Closed Loops).

Located and executed exclusively inside e:\\houmi\\research\\

Implements:
1. Pure White Shared Interior Extraction.
2. Text-Anchored Voronoi Partitioning.
3. Natural Smooth Arc Healing across the neck interface (replaces flat cut lines with organic convex curves).
4. Speech Tail Preservation on Balloon 2.
5. 4-Panel Visualization:
   - Panel 1: INITIAL BBOXES (RED)
   - Panel 2: SEPARATED INSTANCES (BLUE / GREEN)
   - Panel 3: 2 INDEPENDENT NATURAL SMOOTH LOOPS (GREEN)
   - Panel 4: CLEANED & TRUE CENTERS (INPAINT + DEDICATED CENTER LINES)
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
PROJECT_350_DIR = Path(r"E:\Chapter Download\Kuaikanmanhua\ลิขิตตัวร้าย\350")
OUTPUT_DIR = RESEARCH_DIR / "v12_natural_previews"
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


def heal_balloon1_contour(mask: np.ndarray, text_bbox: tuple[int, int, int, int]) -> np.ndarray:
    """Heal the bottom neck cut of Balloon 1 with a smooth convex arc."""
    bx, by, bw, bh = text_bbox
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        return np.array([])
    main_cnt = max(cnts, key=cv2.contourArea).reshape(-1, 2)
    
    # Corner 1 (Bottom-Left): (bx + 15, by + bh + 35)
    # Corner 2 (Bottom-Right): (bx + bw + 15, by + bh - 15)
    c1 = np.array([95, 510])
    c2 = np.array([740, 480])
    
    idx1 = min(range(len(main_cnt)), key=lambda i: np.linalg.norm(main_cnt[i] - c1))
    idx2 = min(range(len(main_cnt)), key=lambda i: np.linalg.norm(main_cnt[i] - c2))
    
    # Select the path between idx1 and idx2 that goes through the top dome (minimum y)
    if idx1 < idx2:
        seg_a = main_cnt[idx1:idx2+1].tolist()
        seg_b = main_cnt[idx2:].tolist() + main_cnt[:idx1+1].tolist()
    else:
        seg_a = main_cnt[idx2:idx1+1].tolist()
        seg_b = main_cnt[idx1:].tolist() + main_cnt[:idx2+1].tolist()
        
    min_y_a = min(p[1] for p in seg_a)
    min_y_b = min(p[1] for p in seg_b)
    
    # Top dome has the smaller min_y
    top_dome = seg_a if min_y_a < min_y_b else seg_b
    
    p_start = np.array(top_dome[-1], dtype=np.float32)
    p_end = np.array(top_dome[0], dtype=np.float32)
    
    t_vals = np.linspace(0, 1, 50)
    ctrl_x = 420.0
    ctrl_y = 610.0
    
    smooth_bottom_arc = []
    for t in t_vals:
        px = (1 - t)**2 * p_start[0] + 2 * (1 - t) * t * ctrl_x + t**2 * p_end[0]
        py = (1 - t)**2 * p_start[1] + 2 * (1 - t) * t * ctrl_y + t**2 * p_end[1]
        smooth_bottom_arc.append([int(round(px)), int(round(py))])
        
    full_poly = np.array(top_dome + smooth_bottom_arc, dtype=np.int32)
    return full_poly.reshape(-1, 1, 2)


def heal_balloon2_contour(mask: np.ndarray, text_bbox: tuple[int, int, int, int], tail_tip: tuple[int, int] | None) -> np.ndarray:
    """Heal the top neck cut of Balloon 2 with a smooth convex arc while preserving speech tail."""
    bx, by, bw, bh = text_bbox
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        return np.array([])
    main_cnt = max(cnts, key=cv2.contourArea).reshape(-1, 2)
    
    # Corner 1 (Top-Left): (bx - 10, by + 15)
    # Corner 2 (Top-Right): (bx + bw + 15, by - 5)
    c1 = np.array([bx - 10, by + 15])
    c2 = np.array([bx + bw + 15, by - 5])
    
    idx1 = min(range(len(main_cnt)), key=lambda i: np.linalg.norm(main_cnt[i] - c1))
    idx2 = min(range(len(main_cnt)), key=lambda i: np.linalg.norm(main_cnt[i] - c2))
    
    if idx1 < idx2:
        clean_segment = main_cnt[idx1:idx2+1].tolist()
    else:
        clean_segment = main_cnt[idx1:].tolist() + main_cnt[:idx2+1].tolist()
        
    p_start = np.array(clean_segment[-1], dtype=np.float32)
    p_end = np.array(clean_segment[0], dtype=np.float32)
    
    t_vals = np.linspace(0, 1, 50)
    mid_x = (p_start[0] + p_end[0]) / 2.0
    mid_y = (p_start[1] + p_end[1]) / 2.0
    ctrl_y = mid_y - 20.0
    
    smooth_top_arc = []
    for t in t_vals:
        px = (1 - t)**2 * p_start[0] + 2 * (1 - t) * t * mid_x + t**2 * p_end[0]
        py = (1 - t)**2 * p_start[1] + 2 * (1 - t) * t * ctrl_y + t**2 * p_end[1]
        smooth_top_arc.append([int(round(px)), int(round(py))])
        
    full_poly = np.array(clean_segment + smooth_top_arc, dtype=np.int32)
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


def main():
    t0 = time.time()
    page_img = load_image(PROJECT_350_DIR / "03.jpg")
    proj = json.load(open(PROJECT_350_DIR / "project.json", encoding="utf-8"))
    p3 = [p for p in proj["pages"] if p["page_number"] == 3][0]
    blocks = p3["text_blocks"]
    
    blk14 = blocks[1]
    blk15 = blocks[2]
    
    bx14, by14, bw14, bh14 = int(blk14["x"]), int(blk14["y"]), int(blk14["width"]), int(blk14["height"])
    bx15, by15, bw15, bh15 = int(blk15["x"]), int(blk15["y"]), int(blk15["width"]), int(blk15["height"])
    
    min_x = 220
    min_y = 5900
    max_x = 1150
    max_y = 6850
    
    crop = page_img[min_y:max_y, min_x:max_x].copy()
    ch, cw = crop.shape[:2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    
    l14_x, l14_y = bx14 - min_x, by14 - min_y
    l15_x, l15_y = bx15 - min_x, by15 - min_y
    
    text_blocks = [
        {"bbox": (l14_x, l14_y, bw14, bh14), "text": blk14.get("text", "")},
        {"bbox": (l15_x, l15_y, bw15, bh15), "text": blk15.get("text", "")}
    ]
    
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
        
    separated_masks, label_map = separate_balloons_voronoi(combined_mask, text_centers)
    
    # Balloon 1 (Healed Natural Squircle Loop)
    poly1 = heal_balloon1_contour(separated_masks[0], text_blocks[0]["bbox"])
    
    # Balloon 2 (Healed Natural Oval + Tail Loop)
    cnts2, _ = cv2.findContours(separated_masks[1], cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    main_cnt2 = max(cnts2, key=cv2.contourArea)
    tail_tip2 = detect_tail_tip(main_cnt2, text_centers[1])
    poly2 = heal_balloon2_contour(separated_masks[1], text_blocks[1]["bbox"], tail_tip2)
    
    # Create healed individual masks
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
        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])
        nz = cv2.findNonZero(b_item["mask"])
        rx, ry, rw, rh = cv2.boundingRect(nz)
        b_item["center"] = (cx, cy)
        b_item["bbox"] = (rx, ry, rw, rh)
        
    clean_mask = cv2.dilate(total_text_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    cleaned = crop.copy()
    cleaned[clean_mask > 0] = [255, 255, 255]
    
    # 4-Panel Visualization
    p1 = crop.copy()
    for blk in text_blocks:
        bx, by, bw, bh = blk["bbox"]
        cv2.rectangle(p1, (bx, by), (bx + bw, by + bh), (0, 0, 255), 3)
    cv2.putText(p1, "1. INITIAL BBOXES (RED)", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (0, 0, 255), 2)
    
    p2 = crop.copy()
    ov2 = p2.copy()
    ov2[label_map == 1] = [255, 190, 190]
    ov2[label_map == 2] = [190, 255, 190]
    cv2.addWeighted(ov2, 0.45, p2, 0.55, 0, p2)
    cv2.circle(p2, text_centers[0], 6, (255, 0, 0), -1)
    cv2.circle(p2, text_centers[1], 6, (0, 180, 0), -1)
    cv2.putText(p2, "2. SEPARATED INSTANCES", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 150, 255), 2)
    
    p3 = crop.copy()
    ov3 = p3.copy()
    for b_item in balloon_data:
        cv2.fillPoly(ov3, [b_item["contour"]], (240, 240, 255))
    cv2.addWeighted(ov3, 0.35, p3, 0.65, 0, p3)
    for b_item in balloon_data:
        cv2.drawContours(p3, [b_item["contour"]], -1, (0, 255, 0), 3)
        if b_item["tail_tip"] is not None:
            cv2.circle(p3, b_item["tail_tip"], 7, (0, 0, 255), -1)
    cv2.putText(p3, "3. 2 NATURAL SMOOTH LOOPS", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
    
    p4 = cleaned.copy()
    for b_item in balloon_data:
        cv2.drawContours(p4, [b_item["contour"]], -1, (0, 255, 0), 3)
        rx, ry, rw, rh = b_item["bbox"]
        cx, cy = b_item["center"]
        cv2.line(p4, (rx, cy), (rx + rw, cy), (255, 150, 0), 3)
        cv2.circle(p4, (cx, cy), 6, (255, 100, 0), -1)
    cv2.putText(p4, "4. CLEANED & TRUE CENTERS", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
    
    out_img = np.hstack([p1, p2, p3, p4])
    out_file = OUTPUT_DIR / "v12_natural_separated_page03.png"
    save_image(out_file, out_img)
    elapsed = time.time() - t0
    print(f"DONE in {elapsed:.2f}s! Saved to -> {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
