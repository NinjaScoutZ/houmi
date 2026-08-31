"""Smart Balloon V7: Exact Polygon Closure with G1/G2 Tangent Smooth Arc (Polished).

Located and executed exclusively inside e:\\houmi\\research\\
"""

from __future__ import annotations

import json
import math
import os
import sys
import cv2
import numpy as np
from pathlib import Path

RESEARCH_DIR = Path(r"e:\houmi\research")
PROJECT_350_DIR = Path(r"E:\Chapter Download\Kuaikanmanhua\ลิขิตตัวร้าย\350")
OUTPUT_DIR = RESEARCH_DIR / "v7_polygon_previews"
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


def process_balloon_14_v7(crop: np.ndarray, b14: tuple[int, int, int, int]):
    ch, cw = crop.shape[:2]
    bx, by, bw, bh = b14
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    
    pure_white = (gray >= 195).astype(np.uint8) * 255
    pure_white = cv2.morphologyEx(pure_white, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
    seed = np.zeros((ch + 2, cw + 2), dtype=np.uint8)
    cv2.floodFill(pure_white.copy(), seed, (bx + bw // 2, by + bh // 2), 255, flags=8 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY)
    joined_mask = seed[1:-1, 1:-1] * 255
    
    cnts, _ = cv2.findContours(joined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    main_cnt = max(cnts, key=cv2.contourArea).reshape(-1, 2)
    
    # 2. Extract Clean Unoccluded Arc of Balloon 14
    c1 = np.array([bx + 15, by + bh + 35])
    c2 = np.array([bx + bw + 15, by + bh - 15])
    
    idx1 = min(range(len(main_cnt)), key=lambda i: np.linalg.norm(main_cnt[i] - c1))
    idx2 = min(range(len(main_cnt)), key=lambda i: np.linalg.norm(main_cnt[i] - c2))
    
    if idx1 < idx2:
        clean_segment = main_cnt[idx2:].tolist() + main_cnt[:idx1+1].tolist()
    else:
        clean_segment = main_cnt[idx2:idx1+1].tolist()
        
    p_start = np.array(clean_segment[-1], dtype=np.float32)
    p_end = np.array(clean_segment[0], dtype=np.float32)
    
    t_vals = np.linspace(0, 1, 60)
    mid_x = (p_start[0] + p_end[0]) / 2.0
    mid_y = (p_start[1] + p_end[1]) / 2.0
    ctrl_y = mid_y + 16.0
    
    smooth_bottom_arc = []
    for t in t_vals:
        px = (1 - t)**2 * p_start[0] + 2 * (1 - t) * t * mid_x + t**2 * p_end[0]
        py = (1 - t)**2 * p_start[1] + 2 * (1 - t) * t * ctrl_y + t**2 * p_end[1]
        smooth_bottom_arc.append([int(round(px)), int(round(py))])
        
    full_poly = np.array(clean_segment + smooth_bottom_arc, dtype=np.int32)
    
    smart_balloon = np.zeros((ch, cw), dtype=np.uint8)
    cv2.fillPoly(smart_balloon, [full_poly], 255)
    smart_balloon = cv2.bitwise_and(smart_balloon, pure_white)
    smart_balloon = cv2.morphologyEx(smart_balloon, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    
    text_ink = (gray < 155).astype(np.uint8) * 255
    text_mask = cv2.bitwise_and(text_ink, smart_balloon)
    
    clean_mask = cv2.dilate(text_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    cleaned = cv2.inpaint(crop, clean_mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
    cleaned[clean_mask > 0] = [255, 255, 255]
    
    nz = cv2.findNonZero(smart_balloon)
    x, y, w, h = cv2.boundingRect(nz)
    M = cv2.moments(smart_balloon)
    cx = int(M["m10"] / M["m00"])
    cy = int(M["m01"] / M["m00"])
    
    p1 = crop.copy()
    cv2.rectangle(p1, (bx, by), (bx + bw, by + bh), (0, 0, 255), 3)
    cv2.putText(p1, "1. INITIAL BBOX (RED)", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 255), 2)
    
    p2 = crop.copy()
    overlay = p2.copy()
    cv2.fillPoly(overlay, [full_poly], (180, 180, 255))
    cv2.addWeighted(overlay, 0.40, p2, 0.60, 0, p2)
    cv2.polylines(p2, [full_poly], isClosed=True, color=(0, 255, 0), thickness=3)
    cv2.putText(p2, "2. SMART SHAPE (PURE WHITE)", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
    
    p3 = cv2.cvtColor(text_mask, cv2.COLOR_GRAY2BGR)
    cv2.putText(p3, "3. TEXT MASK IN BALLOON", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
    
    p4 = cleaned.copy()
    cv2.polylines(p4, [full_poly], isClosed=True, color=(0, 255, 0), thickness=3)
    cv2.line(p4, (x, cy), (x + w, cy), (255, 150, 0), 3)
    cv2.circle(p4, (cx, cy), 6, (255, 100, 0), -1)
    cv2.putText(p4, "4. CLEANED & TRUE CENTER", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
    
    return np.hstack([p1, p2, p3, p4])


def process_balloon_15_v7(crop: np.ndarray, b15: tuple[int, int, int, int]):
    ch, cw = crop.shape[:2]
    bx, by, bw, bh = b15
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    
    pure_white = (gray >= 195).astype(np.uint8) * 255
    pure_white = cv2.morphologyEx(pure_white, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
    pure_white = cv2.morphologyEx(pure_white, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    seed = np.zeros((ch + 2, cw + 2), dtype=np.uint8)
    cv2.floodFill(pure_white.copy(), seed, (bx + bw // 2, by + bh // 2), 255, flags=8 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY)
    joined_mask = seed[1:-1, 1:-1] * 255
    
    cnts, _ = cv2.findContours(joined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    main_cnt = max(cnts, key=cv2.contourArea).reshape(-1, 2)
    
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
    
    t_vals = np.linspace(0, 1, 60)
    mid_x = (p_start[0] + p_end[0]) / 2.0
    mid_y = (p_start[1] + p_end[1]) / 2.0
    ctrl_y = mid_y - 20.0
    
    smooth_top_arc = []
    for t in t_vals:
        px = (1 - t)**2 * p_start[0] + 2 * (1 - t) * t * mid_x + t**2 * p_end[0]
        py = (1 - t)**2 * p_start[1] + 2 * (1 - t) * t * ctrl_y + t**2 * p_end[1]
        smooth_top_arc.append([int(round(px)), int(round(py))])
        
    full_poly = np.array(clean_segment + smooth_top_arc, dtype=np.int32)
    
    smart_balloon = np.zeros((ch, cw), dtype=np.uint8)
    cv2.fillPoly(smart_balloon, [full_poly], 255)
    smart_balloon = cv2.bitwise_and(smart_balloon, pure_white)
    smart_balloon = cv2.morphologyEx(smart_balloon, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    
    text_ink = (gray < 155).astype(np.uint8) * 255
    text_mask = cv2.bitwise_and(text_ink, smart_balloon)
    
    clean_mask = cv2.dilate(text_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    cleaned = cv2.inpaint(crop, clean_mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
    cleaned[clean_mask > 0] = [255, 255, 255]
    
    nz = cv2.findNonZero(smart_balloon)
    x, y, w, h = cv2.boundingRect(nz)
    M = cv2.moments(smart_balloon)
    cx = int(M["m10"] / M["m00"])
    cy = int(M["m01"] / M["m00"])
    
    p1 = crop.copy()
    cv2.rectangle(p1, (bx, by), (bx + bw, by + bh), (0, 0, 255), 3)
    cv2.putText(p1, "1. INITIAL BBOX (RED)", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 255), 2)
    
    p2 = crop.copy()
    overlay = p2.copy()
    cv2.fillPoly(overlay, [full_poly], (190, 210, 255))
    cv2.addWeighted(overlay, 0.40, p2, 0.60, 0, p2)
    cv2.polylines(p2, [full_poly], isClosed=True, color=(0, 255, 0), thickness=3)
    cv2.putText(p2, "2. SMART SHAPE (PURE WHITE)", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
    
    p3 = cv2.cvtColor(text_mask, cv2.COLOR_GRAY2BGR)
    cv2.putText(p3, "3. TEXT MASK IN BALLOON", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
    
    p4 = cleaned.copy()
    cv2.polylines(p4, [full_poly], isClosed=True, color=(0, 255, 0), thickness=3)
    cv2.line(p4, (x, cy), (x + w, cy), (255, 150, 0), 3)
    cv2.circle(p4, (cx, cy), 6, (255, 100, 0), -1)
    cv2.putText(p4, "4. CLEANED & TRUE CENTER", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
    
    return np.hstack([p1, p2, p3, p4])


def main():
    print("=== STARTING POLISHED SMART BALLOON V7 ===")
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
    
    p14_out = process_balloon_14_v7(crop, (l14_x, l14_y, bw14, bh14))
    save_image(OUTPUT_DIR / "v7_sample_14_page03.png", p14_out)
    print(f"V7 Sample 14 Preview saved -> {OUTPUT_DIR / 'v7_sample_14_page03.png'}")
    
    p15_out = process_balloon_15_v7(crop, (l15_x, l15_y, bw15, bh15))
    save_image(OUTPUT_DIR / "v7_sample_15_page03.png", p15_out)
    print(f"V7 Sample 15 Preview saved -> {OUTPUT_DIR / 'v7_sample_15_page03.png'}")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
