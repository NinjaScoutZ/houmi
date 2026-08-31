"""Simple Smooth Curve Continuation from Corner Inflection Points.

Located and executed exclusively inside e:\\houmi\\research\\

Principle:
When a balloon contour hits a corner/notch inflection point where a bridge begins,
we DO NOT follow the wavy bridge/neck.
Instead, we continue with a single, elegant Simple Convex Arc (G1 Continuous Curve)
directly completing the natural squircle base from the left corner to the right corner.
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
OUTPUT_DIR = RESEARCH_DIR / "simple_curve_previews"
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
    print("=== TESTING SIMPLE CONTINUOUS CURVE FROM CORNER INFLECTION ===")
    crop = load_image(RESEARCH_DIR / "raw_sample_14_15_clean.png")
    if crop is None:
        return 1

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    white_sel = (gray >= 195).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    white_sel = cv2.morphologyEx(white_sel, cv2.MORPH_CLOSE, kernel)
    
    ch, cw = crop.shape[:2]
    
    # 1. Corner inflection points where the natural shape of Balloon 1 meets the neck
    # Left corner of Balloon 1 bottom: (380, 830)
    # Right corner of Balloon 1 bottom: (960, 835)
    # This completely bypasses the downward dip of the neck!
    c_left = np.array([380.0, 830.0])
    c_right = np.array([960.0, 835.0])
    
    # 2. Single Simple Smooth Curve (Quadratic Bezier with G1 Tangency)
    # Flat/smooth bottom curve for Balloon 1 (Squircle base)
    t_vals = np.linspace(0, 1, 100)
    simple_bottom_curve = []
    
    mid_x = (c_left[0] + c_right[0]) / 2.0
    mid_y = (c_left[1] + c_right[1]) / 2.0
    # Tangent-matched control point (smooth downward arc of 15px depth)
    ctrl_x = mid_x
    ctrl_y = mid_y + 15.0
    
    for t in t_vals:
        px = (1 - t)**2 * c_left[0] + 2 * (1 - t) * t * ctrl_x + t**2 * c_right[0]
        py = (1 - t)**2 * c_left[1] + 2 * (1 - t) * t * ctrl_y + t**2 * c_right[1]
        simple_bottom_curve.append([int(round(px)), int(round(py))])
        
    simple_curve_arr = np.array(simple_bottom_curve, dtype=np.int32)
    
    # 3. Create Continuous Top Balloon #14 Mask
    # All pixels above the simple curve
    poly_top_cut = [[0, 0], [cw - 1, 0], [cw - 1, int(c_right[1])]] + simple_bottom_curve[::-1] + [[0, int(c_left[1])]]
    mask_top_cut = np.zeros((ch, cw), dtype=np.uint8)
    cv2.fillPoly(mask_top_cut, [np.array(poly_top_cut, dtype=np.int32)], 255)
    
    mask14 = cv2.bitwise_and(white_sel, mask_top_cut)
    n14, l14, s14, _ = cv2.connectedComponentsWithStats(mask14, connectivity=8)
    if n14 > 1:
        c_idx = l14[600, 600] if l14[600, 600] > 0 else 1 + np.argmax(s14[1:, cv2.CC_STAT_AREA])
        mask14 = (l14 == c_idx).astype(np.uint8) * 255
        
    # Morphological smooth of contour
    kernel_sm = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask14 = cv2.morphologyEx(mask14, cv2.MORPH_CLOSE, kernel_sm)
    
    nz14 = cv2.findNonZero(mask14)
    x14, y14, w14, h14 = cv2.boundingRect(nz14)
    
    # 4. Create Continuous Bottom Balloon #15 Mask
    # Top simple curve for Balloon 15 closing its oval naturally
    c15_left = np.array([350.0, 940.0])
    c15_right = np.array([880.0, 920.0])
    mid15_x = (c15_left[0] + c15_right[0]) / 2.0
    mid15_y = (c15_left[1] + c15_right[1]) / 2.0
    ctrl15_x = mid15_x
    ctrl15_y = mid15_y - 25.0  # gentle upward curve closing oval top
    
    simple_top15_curve = []
    for t in t_vals:
        px = (1 - t)**2 * c15_left[0] + 2 * (1 - t) * t * ctrl15_x + t**2 * c15_right[0]
        py = (1 - t)**2 * c15_left[1] + 2 * (1 - t) * t * ctrl15_y + t**2 * c15_right[1]
        simple_top15_curve.append([int(round(px)), int(round(py))])
        
    poly_bot_cut = [[0, ch - 1], [cw - 1, ch - 1], [cw - 1, int(c15_right[1])]] + simple_top15_curve[::-1] + [[0, int(c15_left[1])]]
    mask_bot_cut = np.zeros((ch, cw), dtype=np.uint8)
    cv2.fillPoly(mask_bot_cut, [np.array(poly_bot_cut, dtype=np.int32)], 255)
    
    mask15 = cv2.bitwise_and(white_sel, mask_bot_cut)
    n15, l15, s15, _ = cv2.connectedComponentsWithStats(mask15, connectivity=8)
    if n15 > 1:
        c_idx = l15[1000, 600] if l15[1000, 600] > 0 else 1 + np.argmax(s15[1:, cv2.CC_STAT_AREA])
        mask15 = (l15 == c_idx).astype(np.uint8) * 255
        
    mask15 = cv2.morphologyEx(mask15, cv2.MORPH_CLOSE, kernel_sm)
    nz15 = cv2.findNonZero(mask15)
    x15, y15, w15, h15 = cv2.boundingRect(nz15)
    
    # 5. Generate Clean Visual Previews
    # Preview 1: Simple Continuous Curve Overlay (Matching User Demand!)
    p_main = crop.copy()
    
    # Translucent pink fill for Balloon 14
    overlay14 = p_main.copy()
    cv2.fillPoly(overlay14, [nz14], (180, 180, 255))
    cv2.addWeighted(overlay14, 0.45, p_main, 0.55, 0, p_main)
    
    # Translucent pink fill for Balloon 15
    overlay15 = p_main.copy()
    cv2.fillPoly(overlay15, [nz15], (190, 210, 255))
    cv2.addWeighted(overlay15, 0.45, p_main, 0.55, 0, p_main)
    
    cnts14, _ = cv2.findContours(mask14, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts15, _ = cv2.findContours(mask15, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(p_main, cnts14, -1, (0, 255, 0), 2)
    cv2.drawContours(p_main, cnts15, -1, (0, 255, 0), 2)
    
    # Draw the Simple Continuous Curve in Blue (No Wavy Bridge!)
    cv2.polylines(p_main, [simple_curve_arr], isClosed=False, color=(255, 80, 30), thickness=4)
    cv2.circle(p_main, (int(c_left[0]), int(c_left[1])), 7, (0, 0, 255), -1)
    cv2.circle(p_main, (int(c_right[0]), int(c_right[1])), 7, (0, 0, 255), -1)
    
    # Smart Yellow Bboxes & True Center Lines
    cv2.rectangle(p_main, (x14, y14), (x14 + w14, y14 + h14), (0, 255, 255), 2)
    cy14 = y14 + h14 // 2
    cv2.line(p_main, (x14, cy14), (x14 + w14, cy14), (255, 150, 0), 2)
    
    cv2.rectangle(p_main, (x15, y15), (x15 + w15, y15 + h15), (0, 255, 255), 2)
    cy15 = y15 + h15 // 2
    cv2.line(p_main, (x15, cy15), (x15 + w15, cy15), (255, 150, 0), 2)
    
    cv2.putText(p_main, "1. SIMPLE CONTINUOUS SQUIRCLE", (x14 + 15, y14 + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (0, 200, 0), 2)
    cv2.putText(p_main, "SIMPLE CONTINUOUS CURVE (NO WAVY BRIDGE)", (int(mid_x) - 160, int(mid_y) - 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 80, 30), 2)
    cv2.putText(p_main, "2. SIMPLE CONTINUOUS OVAL", (x15 + 15, y15 + 40), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (0, 200, 0), 2)
    
    # Save Image
    out_file = OUTPUT_DIR / "simple_curve_continuation_preview.png"
    save_image(out_file, p_main)
    print(f"Simple continuous curve preview saved -> {out_file}")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
