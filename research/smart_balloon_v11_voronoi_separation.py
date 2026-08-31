"""Smart Balloon V11: Voronoi Separation & 2 Independent Smooth Contours (Instantaneous Fix).

Located and executed exclusively inside e:\\houmi\\research\\
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
OUTPUT_DIR = RESEARCH_DIR / "v11_voronoi_previews"
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


def get_smooth_closed_contour(main_cnt: np.ndarray, tail_tip: tuple[int, int] | None = None) -> np.ndarray:
    pts = main_cnt.reshape(-1, 2).astype(np.float64)
    if len(pts) < 10:
        return main_cnt
        
    if len(pts) > 400:
        step = max(1, len(pts) // 300)
        pts = pts[::step]
        
    smooth_x = gaussian_filter1d(pts[:, 0], sigma=2.0, mode="wrap")
    smooth_y = gaussian_filter1d(pts[:, 1], sigma=2.0, mode="wrap")
    smoothed = np.column_stack([smooth_x, smooth_y])
    
    if tail_tip is not None:
        dists = np.linalg.norm(smoothed - np.array(tail_tip), axis=1)
        tip_idx = np.argmin(dists)
        smoothed[tip_idx] = [tail_tip[0], tail_tip[1]]
        
    return smoothed.astype(np.int32).reshape(-1, 1, 2)


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
    print("1. Loading image and project...")
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
    
    print("2. Extracting pure white mask...")
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
        
    print("3. Voronoi separation...")
    separated_masks, label_map = separate_balloons_voronoi(combined_mask, text_centers)
    
    balloon_data = []
    total_text_mask = np.zeros((ch, cw), dtype=np.uint8)
    
    for i, blk in enumerate(text_blocks):
        b_mask = separated_masks[i]
        cnts, _ = cv2.findContours(b_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        main_cnt = max(cnts, key=cv2.contourArea)
        
        tail_tip = detect_tail_tip(main_cnt, text_centers[i]) if i == 1 else None
        smooth_cnt = get_smooth_closed_contour(main_cnt, tail_tip)
        
        text_ink = (gray < 155).astype(np.uint8) * 255
        text_mask = cv2.bitwise_and(text_ink, b_mask)
        total_text_mask = cv2.bitwise_or(total_text_mask, text_mask)
        
        M = cv2.moments(b_mask)
        cx = int(M["m10"] / M["m00"]) if M["m00"] > 0 else text_centers[i][0]
        cy = int(M["m01"] / M["m00"]) if M["m00"] > 0 else text_centers[i][1]
        nz = cv2.findNonZero(b_mask)
        rx, ry, rw, rh = cv2.boundingRect(nz) if nz is not None else (0, 0, 100, 100)
        
        balloon_data.append({
            "id": i + 1,
            "text": blk.get("text", ""),
            "text_bbox": blk["bbox"],
            "contour": smooth_cnt,
            "tail_tip": tail_tip,
            "center": (cx, cy),
            "bbox": (rx, ry, rw, rh),
            "mask": b_mask,
        })
        
    print("4. Fast inpainting...")
    clean_mask = cv2.dilate(total_text_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    cleaned = crop.copy()
    cleaned[clean_mask > 0] = [255, 255, 255]
    
    print("5. Rendering 4 panels...")
    # Panel 1: INITIAL BBOXES (RED)
    p1 = crop.copy()
    for blk in text_blocks:
        bx, by, bw, bh = blk["bbox"]
        cv2.rectangle(p1, (bx, by), (bx + bw, by + bh), (0, 0, 255), 3)
    cv2.putText(p1, "1. INITIAL BBOXES (RED)", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (0, 0, 255), 2)
    
    # Panel 2: SEPARATED INSTANCES (BLUE / GREEN)
    p2 = crop.copy()
    ov2 = p2.copy()
    ov2[label_map == 1] = [255, 190, 190]
    ov2[label_map == 2] = [190, 255, 190]
    cv2.addWeighted(ov2, 0.45, p2, 0.55, 0, p2)
    cv2.circle(p2, text_centers[0], 6, (255, 0, 0), -1)
    cv2.circle(p2, text_centers[1], 6, (0, 180, 0), -1)
    cv2.putText(p2, "2. SEPARATED INSTANCES", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 150, 255), 2)
    
    # Panel 3: 2 INDEPENDENT SMOOTH CONTOURS (GREEN)
    p3 = crop.copy()
    ov3 = p3.copy()
    for b_item in balloon_data:
        cv2.fillPoly(ov3, [b_item["contour"]], (240, 240, 255))
    cv2.addWeighted(ov3, 0.35, p3, 0.65, 0, p3)
    for b_item in balloon_data:
        cv2.drawContours(p3, [b_item["contour"]], -1, (0, 255, 0), 3)
        if b_item["tail_tip"] is not None:
            cv2.circle(p3, b_item["tail_tip"], 7, (0, 0, 255), -1)
    cv2.putText(p3, "3. 2 INDEPENDENT CONTOURS", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
    
    # Panel 4: CLEANED & TRUE CENTERS
    p4 = cleaned.copy()
    for b_item in balloon_data:
        cv2.drawContours(p4, [b_item["contour"]], -1, (0, 255, 0), 3)
        rx, ry, rw, rh = b_item["bbox"]
        cx, cy = b_item["center"]
        cv2.line(p4, (rx, cy), (rx + rw, cy), (255, 150, 0), 3)
        cv2.circle(p4, (cx, cy), 6, (255, 100, 0), -1)
    cv2.putText(p4, "4. CLEANED & TRUE CENTERS", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
    
    out_img = np.hstack([p1, p2, p3, p4])
    out_file = OUTPUT_DIR / "v11_voronoi_conjoined_page03.png"
    save_image(out_file, out_img)
    elapsed = time.time() - t0
    print(f"DONE in {elapsed:.2f}s! Saved to -> {out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
