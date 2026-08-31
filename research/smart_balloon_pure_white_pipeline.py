"""Smart Balloon Pipeline: Pure White Extraction & Simple Curve Completion (No Yellow Box).

Located and executed exclusively inside e:\\houmi\\research\\

Workflow:
1. Panel 1: Original image with RED initial text bounding box from project.json.
2. Panel 2: Smart Balloon shape generated from Pure White (gray >= 210) seed floodfill + Simple Curve Completion from corner inflection points (Green contour + translucent fill, NO yellow box).
3. Panel 3: Text ink mask strictly inside the Smart Balloon.
4. Panel 4: Cleaned inpaint result + Blue True Center Line.
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
OUTPUT_DIR = RESEARCH_DIR / "pure_white_pipeline_previews"
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


def process_sample_14_15_pure_white(page_img: np.ndarray, blk14: dict, blk15: dict):
    bx14, by14, bw14, bh14 = int(blk14["x"]), int(blk14["y"]), int(blk14["width"]), int(blk14["height"])
    bx15, by15, bw15, bh15 = int(blk15["x"]), int(blk15["y"]), int(blk15["width"]), int(blk15["height"])
    
    # Context crop for the scene
    min_x = 0
    min_y = 5600
    max_x = page_img.shape[1]
    max_y = 6750
    
    crop = page_img[min_y:max_y, min_x:max_x].copy()
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    ch, cw = crop.shape[:2]
    
    l14_x, l14_y = bx14 - min_x, by14 - min_y
    l15_x, l15_y = bx15 - min_x, by15 - min_y
    
    # 1. Pure White Extraction:
    pure_white = (gray >= 200).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    pure_white = cv2.morphologyEx(pure_white, cv2.MORPH_CLOSE, kernel)
    
    # FloodFill from Balloon 14 text center
    seed_14 = np.zeros((ch + 2, cw + 2), dtype=np.uint8)
    cv2.floodFill(pure_white.copy(), seed_14, (l14_x + bw14 // 2, l14_y + bh14 // 2), 255, flags=8 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY)
    connected_14_15 = seed_14[1:-1, 1:-1] * 255
    
    # 2. Simple Curve Completion for Balloon 14 (Top Squircle)
    # Corner inflection points on Balloon 14 base
    c14_l = np.array([380.0, 830.0])
    c14_r = np.array([960.0, 835.0])
    t_vals = np.linspace(0, 1, 80)
    
    curve14 = []
    mid14_x = (c14_l[0] + c14_r[0]) / 2.0
    mid14_y = (c14_l[1] + c14_r[1]) / 2.0
    ctrl14_y = mid14_y + 15.0  # smooth natural downward arc
    for t in t_vals:
        px = (1 - t)**2 * c14_l[0] + 2 * (1 - t) * t * mid14_x + t**2 * c14_r[0]
        py = (1 - t)**2 * c14_l[1] + 2 * (1 - t) * t * ctrl14_y + t**2 * c14_r[1]
        curve14.append([int(round(px)), int(round(py))])
        
    poly_top_cut = [[0, 0], [cw - 1, 0], [cw - 1, int(c14_r[1])]] + curve14[::-1] + [[0, int(c14_l[1])]]
    mask_top = np.zeros((ch, cw), dtype=np.uint8)
    cv2.fillPoly(mask_top, [np.array(poly_top_cut, dtype=np.int32)], 255)
    
    smart_balloon_14 = cv2.bitwise_and(connected_14_15, mask_top)
    smart_balloon_14 = cv2.morphologyEx(smart_balloon_14, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    
    # 3. Simple Curve Completion for Balloon 15 (Bottom Oval)
    # The cut line separates Balloon 14 and Balloon 15
    poly_bot_cut = [[0, ch - 1], [cw - 1, ch - 1], [cw - 1, int(c14_r[1])]] + curve14[::-1] + [[0, int(c14_l[1])]]
    mask_bot = np.zeros((ch, cw), dtype=np.uint8)
    cv2.fillPoly(mask_bot, [np.array(poly_bot_cut, dtype=np.int32)], 255)
    
    smart_balloon_15 = cv2.bitwise_and(connected_14_15, mask_bot)
    smart_balloon_15 = cv2.morphologyEx(smart_balloon_15, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    
    # 4. Text Ink Masks
    text_ink = (gray < 150).astype(np.uint8) * 255
    text_mask_14 = cv2.bitwise_and(text_ink, smart_balloon_14)
    text_mask_15 = cv2.bitwise_and(text_ink, smart_balloon_15)
    
    # 5. Cleaned Inpaint Images
    clean_mask_14 = cv2.dilate(text_mask_14, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    cleaned_crop_14 = cv2.inpaint(crop, clean_mask_14, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
    
    clean_mask_15 = cv2.dilate(text_mask_15, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    cleaned_crop_15 = cv2.inpaint(crop, clean_mask_15, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
    
    # 6. Generate 4-Panel Sequential Previews (NO YELLOW BOXES!)
    # --- Sample 14 Preview ---
    # Panel 1: Original with RED Initial Box from project.json
    s14_p1 = crop.copy()
    cv2.rectangle(s14_p1, (l14_x, l14_y), (l14_x + bw14, l14_y + bh14), (0, 0, 255), 3)
    cv2.putText(s14_p1, "1. INITIAL BBOX (RED)", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 255), 2)
    
    # Panel 2: Smart Balloon Shape (Pure White + Simple Curve, Green Contour, NO YELLOW BOX)
    s14_p2 = crop.copy()
    overlay14 = s14_p2.copy()
    nz14 = cv2.findNonZero(smart_balloon_14)
    cv2.fillPoly(overlay14, [nz14], (180, 180, 255))
    cv2.addWeighted(overlay14, 0.40, s14_p2, 0.60, 0, s14_p2)
    cnts14, _ = cv2.findContours(smart_balloon_14, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(s14_p2, cnts14, -1, (0, 255, 0), 3)
    cv2.putText(s14_p2, "2. SMART SHAPE (PURE WHITE)", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
    
    # Panel 3: Text Mask in Balloon
    s14_p3 = cv2.cvtColor(text_mask_14, cv2.COLOR_GRAY2BGR)
    cv2.putText(s14_p3, "3. TEXT MASK IN BALLOON", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 0), 2)
    
    # Panel 4: Cleaned & True Center Line (NO YELLOW BOX)
    s14_p4 = cleaned_crop_14.copy()
    cv2.drawContours(s14_p4, cnts14, -1, (0, 255, 0), 3)
    M14 = cv2.moments(smart_balloon_14)
    c14_cx = int(M14["m10"] / M14["m00"])
    c14_cy = int(M14["m01"] / M14["m00"])
    x14, y14, w14, h14 = cv2.boundingRect(nz14)
    cv2.line(s14_p4, (x14, c14_cy), (x14 + w14, c14_cy), (255, 150, 0), 3)
    cv2.putText(s14_p4, "4. CLEANED & TRUE CENTER", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
    
    preview14 = np.hstack([s14_p1, s14_p2, s14_p3, s14_p4])
    save_image(OUTPUT_DIR / "pure_white_sample_14_page03.png", preview14)
    print(f"Sample 14 Pure White Preview saved -> {OUTPUT_DIR / 'pure_white_sample_14_page03.png'}")
    
    # --- Sample 15 Preview ---
    s15_p1 = crop.copy()
    cv2.rectangle(s15_p1, (l15_x, l15_y), (l15_x + bw15, l15_y + bh15), (0, 0, 255), 3)
    cv2.putText(s15_p1, "1. INITIAL BBOX (RED)", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 255), 2)
    
    s15_p2 = crop.copy()
    overlay15 = s15_p2.copy()
    nz15 = cv2.findNonZero(smart_balloon_15)
    cv2.fillPoly(overlay15, [nz15], (190, 210, 255))
    cv2.addWeighted(overlay15, 0.40, s15_p2, 0.60, 0, s15_p2)
    cnts15, _ = cv2.findContours(smart_balloon_15, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(s15_p2, cnts15, -1, (0, 255, 0), 3)
    cv2.putText(s15_p2, "2. SMART SHAPE (PURE WHITE)", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
    
    s15_p3 = cv2.cvtColor(text_mask_15, cv2.COLOR_GRAY2BGR)
    cv2.putText(s15_p3, "3. TEXT MASK IN BALLOON", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 0), 2)
    
    s15_p4 = cleaned_crop_15.copy()
    cv2.drawContours(s15_p4, cnts15, -1, (0, 255, 0), 3)
    M15 = cv2.moments(smart_balloon_15)
    c15_cx = int(M15["m10"] / M15["m00"])
    c15_cy = int(M15["m01"] / M15["m00"])
    x15, y15, w15, h15 = cv2.boundingRect(nz15)
    cv2.line(s15_p4, (x15, c15_cy), (x15 + w15, c15_cy), (255, 150, 0), 3)
    cv2.putText(s15_p4, "4. CLEANED & TRUE CENTER", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
    
    preview15 = np.hstack([s15_p1, s15_p2, s15_p3, s15_p4])
    save_image(OUTPUT_DIR / "pure_white_sample_15_page03.png", preview15)
    print(f"Sample 15 Pure White Preview saved -> {OUTPUT_DIR / 'pure_white_sample_15_page03.png'}")


def main():
    print("=== STARTING PURE WHITE PIPELINE EXECUTION (NO YELLOW BOX) ===")
    page_img = load_image(PROJECT_350_DIR / "03.jpg")
    proj = json.load(open(PROJECT_350_DIR / "project.json", encoding="utf-8"))
    p3 = [p for p in proj["pages"] if p["page_number"] == 3][0]
    blocks = p3["text_blocks"]
    
    process_sample_14_15_pure_white(page_img, blocks[1], blocks[2])
    print("\nPure White Pipeline execution completed cleanly!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
