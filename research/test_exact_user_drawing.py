"""Exact Match to User Drawing: 2D Natural Boundary Curve Cut (Final Verified Coordinates).

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
OUTPUT_DIR = RESEARCH_DIR / "natural_curve_split_previews"
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


def main():
    print("=== RUNNING 2D NATURAL BOUNDARY CURVE CUT ===")
    crop = load_image(RESEARCH_DIR / "raw_sample_14_15_clean.png")
    if crop is None:
        return 1

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    white_sel = (gray >= 195).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    white_sel = cv2.morphologyEx(white_sel, cv2.MORPH_CLOSE, kernel)
    
    ch, cw = crop.shape[:2]
    
    # 1. Exact Crevice Coordinates matching User Drawing
    # Left Crevice: (424, 900)
    # Right Crevice: (950, 857)
    x1, y1 = 424.0, 900.0
    x2, y2 = 950.0, 857.0
    
    bulge = 18.0  # gentle downward convex curve completing top squircle base
    
    arc_cut_pts = []
    xs = np.linspace(x1, x2, int(x2 - x1) + 1)
    for x_val in xs:
        u = (x_val - x1) / (x2 - x1)
        y_val = y1 + (y2 - y1) * u + 4 * bulge * u * (1 - u)
        arc_cut_pts.append([int(round(x_val)), int(round(y_val))])
        
    arc_cut_arr = np.array(arc_cut_pts, dtype=np.int32)
    
    # 2. Polygon Mask Cut
    # Top Bubble #14: All pixels above the natural boundary arc
    poly_cut_top = [[0, 0], [cw - 1, 0], [cw - 1, int(y2)]] + arc_cut_pts[::-1] + [[0, int(y1)]]
    cut_mask_top = np.zeros((ch, cw), dtype=np.uint8)
    cv2.fillPoly(cut_mask_top, [np.array(poly_cut_top, dtype=np.int32)], 255)
    mask14 = cv2.bitwise_and(white_sel, cut_mask_top)
    
    # Keep only component in balloon 14 region
    n14, l14, s14, _ = cv2.connectedComponentsWithStats(mask14, connectivity=8)
    if n14 > 1:
        # Keep component containing (600, 600)
        c_idx = l14[600, 600] if l14[600, 600] > 0 else 1 + np.argmax(s14[1:, cv2.CC_STAT_AREA])
        mask14 = (l14 == c_idx).astype(np.uint8) * 255
        
    nz14 = cv2.findNonZero(mask14)
    x14, y14, w14, h14 = cv2.boundingRect(nz14)
    
    # Bottom Bubble #15: All pixels below the natural boundary arc
    poly_cut_bot = [[0, ch - 1], [cw - 1, ch - 1], [cw - 1, int(y2)]] + arc_cut_pts[::-1] + [[0, int(y1)]]
    cut_mask_bot = np.zeros((ch, cw), dtype=np.uint8)
    cv2.fillPoly(cut_mask_bot, [np.array(poly_cut_bot, dtype=np.int32)], 255)
    mask15 = cv2.bitwise_and(white_sel, cut_mask_bot)
    
    n15, l15, s15, _ = cv2.connectedComponentsWithStats(mask15, connectivity=8)
    if n15 > 1:
        c_idx = l15[1000, 600] if l15[1000, 600] > 0 else 1 + np.argmax(s15[1:, cv2.CC_STAT_AREA])
        mask15 = (l15 == c_idx).astype(np.uint8) * 255
        
    nz15 = cv2.findNonZero(mask15)
    x15, y15, w15, h15 = cv2.boundingRect(nz15)
    
    # 3. Build Demonstration Image Matching User Sketch
    p_demo = crop.copy()
    
    # Pink translucent overlay for Balloon 14 (Exact user pink color!)
    overlay14 = p_demo.copy()
    cv2.fillPoly(overlay14, [nz14], (180, 180, 255))
    cv2.addWeighted(overlay14, 0.45, p_demo, 0.55, 0, p_demo)
    
    # Pink translucent overlay for Balloon 15
    overlay15 = p_demo.copy()
    cv2.fillPoly(overlay15, [nz15], (190, 210, 255))
    cv2.addWeighted(overlay15, 0.45, p_demo, 0.55, 0, p_demo)
    
    # Green contours
    cnts14, _ = cv2.findContours(mask14, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts15, _ = cv2.findContours(mask15, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(p_demo, cnts14, -1, (0, 255, 0), 2)
    cv2.drawContours(p_demo, cnts15, -1, (0, 255, 0), 2)
    
    # Blue Natural Cut Curve matching user diagram!
    cv2.polylines(p_demo, [arc_cut_arr], isClosed=False, color=(255, 100, 30), thickness=5)
    cv2.circle(p_demo, (int(x1), int(y1)), 7, (0, 0, 255), -1)
    cv2.circle(p_demo, (int(x2), int(y2)), 7, (0, 0, 255), -1)
    
    # Yellow Smart Bounding Boxes
    cv2.rectangle(p_demo, (x14, y14), (x14 + w14, y14 + h14), (0, 255, 255), 2)
    cy14 = y14 + h14 // 2
    cv2.line(p_demo, (x14, cy14), (x14 + w14, cy14), (255, 150, 0), 2)
    
    cv2.rectangle(p_demo, (x15, y15), (x15 + w15, y15 + h15), (0, 255, 255), 2)
    cy15 = y15 + h15 // 2
    cv2.line(p_demo, (x15, cy15), (x15 + w15, cy15), (255, 150, 0), 2)
    
    # Text Annotations
    cv2.putText(p_demo, "1. TOP SMART BALLOON #14", (x14 + 15, y14 + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (0, 200, 0), 2)
    cv2.putText(p_demo, "NATURAL CUT CURVE", (int((x1+x2)/2) - 90, int((y1+y2)/2) - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 100, 30), 2)
    cv2.putText(p_demo, "2. BOTTOM SMART BALLOON #15", (x15 + 15, y15 + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (0, 200, 0), 2)
    
    # Left / Right Separate Visualizations
    p_left = crop.copy()
    cv2.drawContours(p_left, cnts14, -1, (0, 255, 0), 2)
    cv2.rectangle(p_left, (x14, y14), (x14 + w14, y14 + h14), (0, 255, 255), 2)
    cv2.line(p_left, (x14, cy14), (x14 + w14, cy14), (255, 150, 0), 2)
    cv2.putText(p_left, "BALLOON #14 SEPARATED (CENTER EXACT)", (15, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
    
    p_right = crop.copy()
    cv2.drawContours(p_right, cnts15, -1, (0, 255, 0), 2)
    cv2.rectangle(p_right, (x15, y15), (x15 + w15, y15 + h15), (0, 255, 255), 2)
    cv2.line(p_right, (x15, cy15), (x15 + w15, cy15), (255, 150, 0), 2)
    cv2.putText(p_right, "BALLOON #15 SEPARATED (CENTER EXACT)", (15, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
    
    combined = np.hstack([p_demo, p_left, p_right])
    out_file = OUTPUT_DIR / "exact_user_drawing_match_preview.png"
    save_image(out_file, combined)
    print(f"Exact user drawing preview saved -> {out_file}")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
