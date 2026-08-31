"""Smart Balloon V5: Exact Geometric Symmetry & Real Project Coordinates.

Located and executed exclusively inside e:\\houmi\\research\\

Real Coordinates from project.json:
- Block 1 (Sample #14 - Top): x=390.0, y=6182.96, w=559.9, h=285.51
- Block 2 (Sample #15 - Bottom): x=738.34, y=6533.82, w=325.0, h=154.68
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
OUTPUT_DIR = RESEARCH_DIR / "v5_exact_symmetry_previews"
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


def reconstruct_balloon_14(crop_img: np.ndarray, b14: tuple[int, int, int, int]) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int], tuple[int, int]]:
    """Reconstruct natural squircle shape for Balloon 14 by completing the occluded bottom-right corner."""
    gray = cv2.cvtColor(crop_img, cv2.COLOR_BGR2GRAY)
    ch, cw = crop_img.shape[:2]
    bx, by, bw, bh = b14
    
    # 1. Pure white thresholding + floodfill from text center
    pure_white = (gray >= 205).astype(np.uint8) * 255
    pure_white = cv2.morphologyEx(pure_white, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
    
    seed = np.zeros((ch + 2, cw + 2), dtype=np.uint8)
    cv2.floodFill(pure_white.copy(), seed, (bx + bw // 2, by + bh // 2), 255, flags=8 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY)
    joined_mask = seed[1:-1, 1:-1] * 255
    
    # 2. Extract contour of joined shape
    cnts, _ = cv2.findContours(joined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cnt = max(cnts, key=cv2.contourArea).reshape(-1, 2)
    
    # Balloon 14 Top, Left, and Right bounds
    # Left corner of balloon 14 bottom: where bottom curve begins turning right
    # Around y ~ by + bh + 15, x ~ bx + 30
    # Right corner of balloon 14 bottom: where right curve meets the neck
    left_corner = np.array([bx + 40.0, by + bh + 45.0])
    right_corner = np.array([bx + bw + 45.0, by + bh + 15.0])
    
    # 3. Simple Natural Curve (G1 continuous smooth squircle base)
    t_vals = np.linspace(0, 1, 100)
    mid_x = (left_corner[0] + right_corner[0]) / 2.0
    mid_y = (left_corner[1] + right_corner[1]) / 2.0
    ctrl_y = mid_y + 20.0  # gentle natural convex curve closing the squircle
    
    simple_bottom_curve = []
    for t in t_vals:
        px = (1 - t)**2 * left_corner[0] + 2 * (1 - t) * t * mid_x + t**2 * right_corner[0]
        py = (1 - t)**2 * left_corner[1] + 2 * (1 - t) * t * ctrl_y + t**2 * right_corner[1]
        simple_bottom_curve.append([int(round(px)), int(round(py))])
        
    poly_top_cut = [[0, 0], [cw - 1, 0], [cw - 1, int(right_corner[1])]] + simple_bottom_curve[::-1] + [[0, int(left_corner[1])]]
    mask_top = np.zeros((ch, cw), dtype=np.uint8)
    cv2.fillPoly(mask_top, [np.array(poly_top_cut, dtype=np.int32)], 255)
    
    smart_balloon_14 = cv2.bitwise_and(joined_mask, mask_top)
    smart_balloon_14 = cv2.morphologyEx(smart_balloon_14, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    
    nz = cv2.findNonZero(smart_balloon_14)
    x14, y14, w14, h14 = cv2.boundingRect(nz)
    
    # True Geometric Center
    M = cv2.moments(smart_balloon_14)
    cx = int(M["m10"] / M["m00"])
    cy = int(M["m01"] / M["m00"])
    
    return smart_balloon_14, np.array(simple_bottom_curve, dtype=np.int32), (x14, y14, w14, h14), (cx, cy)


def reconstruct_balloon_15(crop_img: np.ndarray, b15: tuple[int, int, int, int]) -> tuple[np.ndarray, np.ndarray, tuple[int, int, int, int], tuple[int, int]]:
    """Reconstruct natural oval shape for Balloon 15 by completing the occluded top-left arc."""
    gray = cv2.cvtColor(crop_img, cv2.COLOR_BGR2GRAY)
    ch, cw = crop_img.shape[:2]
    bx, by, bw, bh = b15
    
    pure_white = (gray >= 205).astype(np.uint8) * 255
    pure_white = cv2.morphologyEx(pure_white, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
    
    seed = np.zeros((ch + 2, cw + 2), dtype=np.uint8)
    cv2.floodFill(pure_white.copy(), seed, (bx + bw // 2, by + bh // 2), 255, flags=8 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY)
    joined_mask = seed[1:-1, 1:-1] * 255
    
    # Balloon 15 Top Simple Curve: connects left top corner to right top corner
    left_corner = np.array([bx - 25.0, by + 10.0])
    right_corner = np.array([bx + bw + 20.0, by - 15.0])
    
    t_vals = np.linspace(0, 1, 100)
    mid_x = (left_corner[0] + right_corner[0]) / 2.0
    mid_y = (left_corner[1] + right_corner[1]) / 2.0
    ctrl_y = mid_y - 25.0  # natural convex curve closing the oval top
    
    simple_top_curve = []
    for t in t_vals:
        px = (1 - t)**2 * left_corner[0] + 2 * (1 - t) * t * mid_x + t**2 * right_corner[0]
        py = (1 - t)**2 * left_corner[1] + 2 * (1 - t) * t * ctrl_y + t**2 * right_corner[1]
        simple_top_curve.append([int(round(px)), int(round(py))])
        
    poly_bot_cut = [[0, ch - 1], [cw - 1, ch - 1], [cw - 1, int(right_corner[1])]] + simple_top_curve[::-1] + [[0, int(left_corner[1])]]
    mask_bot = np.zeros((ch, cw), dtype=np.uint8)
    cv2.fillPoly(mask_bot, [np.array(poly_bot_cut, dtype=np.int32)], 255)
    
    smart_balloon_15 = cv2.bitwise_and(joined_mask, mask_bot)
    smart_balloon_15 = cv2.morphologyEx(smart_balloon_15, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    
    nz = cv2.findNonZero(smart_balloon_15)
    x15, y15, w15, h15 = cv2.boundingRect(nz)
    
    M = cv2.moments(smart_balloon_15)
    cx = int(M["m10"] / M["m00"])
    cy = int(M["m01"] / M["m00"])
    
    return smart_balloon_15, np.array(simple_top_curve, dtype=np.int32), (x15, y15, w15, h15), (cx, cy)


def main():
    print("=== STARTING SMART BALLOON V5 (EXACT PROJECT COORDINATES) ===")
    page_img = load_image(PROJECT_350_DIR / "03.jpg")
    proj = json.load(open(PROJECT_350_DIR / "project.json", encoding="utf-8"))
    p3 = [p for p in proj["pages"] if p["page_number"] == 3][0]
    blocks = p3["text_blocks"]
    
    blk14 = blocks[1]  # Top Balloon
    blk15 = blocks[2]  # Bottom Balloon
    
    bx14, by14, bw14, bh14 = int(blk14["x"]), int(blk14["y"]), int(blk14["width"]), int(blk14["height"])
    bx15, by15, bw15, bh15 = int(blk15["x"]), int(blk15["y"]), int(blk15["width"]), int(blk15["height"])
    
    # Exact Scene Crop with Ample Margin
    min_x = 220
    min_y = 5900
    max_x = 1150
    max_y = 6850
    
    crop = page_img[min_y:max_y, min_x:max_x].copy()
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    
    l14_x, l14_y = bx14 - min_x, by14 - min_y
    l15_x, l15_y = bx15 - min_x, by15 - min_y
    
    # 1. Process Balloon 14 (Top Squircle)
    mask14, curve14, bbox14, center14 = reconstruct_balloon_14(crop, (l14_x, l14_y, bw14, bh14))
    
    # 2. Process Balloon 15 (Bottom Oval)
    mask15, curve15, bbox15, center15 = reconstruct_balloon_15(crop, (l15_x, l15_y, bw15, bh15))
    
    # 3. Clean Text in Balloons (Pure Solid White Cleaning for Manga Balloons)
    text_ink = (gray < 160).astype(np.uint8) * 255
    text_mask_14 = cv2.bitwise_and(text_ink, mask14)
    text_mask_15 = cv2.bitwise_and(text_ink, mask15)
    
    # High-quality inpaint cleaning
    clean_mask_14 = cv2.dilate(text_mask_14, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    cleaned_crop_14 = cv2.inpaint(crop, clean_mask_14, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
    # Fill pure white in solid text interior
    cleaned_crop_14[clean_mask_14 > 0] = [255, 255, 255]
    
    clean_mask_15 = cv2.dilate(text_mask_15, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    cleaned_crop_15 = cv2.inpaint(crop, clean_mask_15, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
    cleaned_crop_15[clean_mask_15 > 0] = [255, 255, 255]
    
    # 4. Generate 4-Panel Sequential Previews
    # --- Sample 14 Preview ---
    s14_p1 = crop.copy()
    cv2.rectangle(s14_p1, (l14_x, l14_y), (l14_x + bw14, l14_y + bh14), (0, 0, 255), 3)
    cv2.putText(s14_p1, "1. INITIAL BBOX (RED)", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 255), 2)
    
    s14_p2 = crop.copy()
    overlay14 = s14_p2.copy()
    cv2.fillPoly(overlay14, [cv2.findNonZero(mask14)], (180, 180, 255))
    cv2.addWeighted(overlay14, 0.40, s14_p2, 0.60, 0, s14_p2)
    cnts14, _ = cv2.findContours(mask14, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(s14_p2, cnts14, -1, (0, 255, 0), 3)
    cv2.putText(s14_p2, "2. SMART SHAPE (PURE WHITE)", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
    
    s14_p3 = cv2.cvtColor(text_mask_14, cv2.COLOR_GRAY2BGR)
    cv2.putText(s14_p3, "3. TEXT MASK IN BALLOON", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 0), 2)
    
    s14_p4 = cleaned_crop_14.copy()
    cv2.drawContours(s14_p4, cnts14, -1, (0, 255, 0), 3)
    cx14, cy14 = center14
    x14, y14, w14, h14 = bbox14
    cv2.line(s14_p4, (x14, cy14), (x14 + w14, cy14), (255, 150, 0), 3)
    cv2.putText(s14_p4, "4. CLEANED & TRUE CENTER", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
    
    preview14 = np.hstack([s14_p1, s14_p2, s14_p3, s14_p4])
    save_image(OUTPUT_DIR / "v5_sample_14_page03.png", preview14)
    print(f"Sample 14 V5 Preview saved -> {OUTPUT_DIR / 'v5_sample_14_page03.png'}")
    
    # --- Sample 15 Preview ---
    s15_p1 = crop.copy()
    cv2.rectangle(s15_p1, (l15_x, l15_y), (l15_x + bw15, l15_y + bh15), (0, 0, 255), 3)
    cv2.putText(s15_p1, "1. INITIAL BBOX (RED)", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 255), 2)
    
    s15_p2 = crop.copy()
    overlay15 = s15_p2.copy()
    cv2.fillPoly(overlay15, [cv2.findNonZero(mask15)], (190, 210, 255))
    cv2.addWeighted(overlay15, 0.40, s15_p2, 0.60, 0, s15_p2)
    cnts15, _ = cv2.findContours(mask15, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(s15_p2, cnts15, -1, (0, 255, 0), 3)
    cv2.putText(s15_p2, "2. SMART SHAPE (PURE WHITE)", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
    
    s15_p3 = cv2.cvtColor(text_mask_15, cv2.COLOR_GRAY2BGR)
    cv2.putText(s15_p3, "3. TEXT MASK IN BALLOON", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 0), 2)
    
    s15_p4 = cleaned_crop_15.copy()
    cv2.drawContours(s15_p4, cnts15, -1, (0, 255, 0), 3)
    cx15, cy15 = center15
    x15, y15, w15, h15 = bbox15
    cv2.line(s15_p4, (x15, cy15), (x15 + w15, cy15), (255, 150, 0), 3)
    cv2.putText(s15_p4, "4. CLEANED & TRUE CENTER", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
    
    preview15 = np.hstack([s15_p1, s15_p2, s15_p3, s15_p4])
    save_image(OUTPUT_DIR / "v5_sample_15_page03.png", preview15)
    print(f"Sample 15 V5 Preview saved -> {OUTPUT_DIR / 'v5_sample_15_page03.png'}")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
