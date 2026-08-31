"""Exact Symmetrical Ellipse Completion for Balloon 14 & 15.

Located and executed exclusively inside e:\\houmi\\research\\

Algorithm:
1. Extract the clean, unoccluded boundary points (top arc, left arc, right arc).
2. Fit an algebraic ellipse (Direct Least Squares Ellipse Fit).
3. Draw the reconstructed smooth closed balloon polygon.
4. Calculate exact Smart Bbox and True Balloon Center.
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
OUTPUT_DIR = RESEARCH_DIR / "shape_completion_previews"
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


def fit_clean_balloon_ellipse(mask: np.ndarray, text_bbox: tuple[int, int, int, int], is_top: bool) -> dict:
    """Fit a symmetrical ellipse using only clean boundary points."""
    bx, by, bw, bh = text_bbox
    cx, cy = bx + bw // 2, by + bh // 2
    h, w = mask.shape
    
    # Extract contour points of the mask
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return {}
    
    main_cnt = max(contours, key=cv2.contourArea).reshape(-1, 2)
    
    # Filter points:
    # If this is top balloon, keep points where y <= cy + bh * 0.4 (clean top and sides)
    # If this is bottom balloon, keep points where y >= cy - bh * 0.4 (clean bottom and sides)
    clean_pts = []
    for px, py in main_cnt:
        dist_from_text = math.hypot(px - cx, py - cy)
        # Keep points reasonably close to text block
        if dist_from_text < max(bw, bh) * 1.5:
            if is_top:
                # Top balloon clean points are above or level with text bottom
                if py <= by + bh + 20:
                    clean_pts.append([px, py])
            else:
                # Bottom balloon clean points are below or level with text top
                if py >= by - 20:
                    clean_pts.append([px, py])
                    
    clean_pts = np.array(clean_pts, dtype=np.int32)
    
    if len(clean_pts) < 10:
        clean_pts = main_cnt
        
    # Fit ellipse on clean points
    ellipse = cv2.fitEllipse(clean_pts)
    (ex, ey), (ew, eh), e_angle = ellipse
    
    # Generate smooth polygon from fitted ellipse
    ellipse_pts = cv2.ellipse2Poly((int(ex), int(ey)), (int(ew / 2), int(eh / 2)), int(e_angle), 0, 360, 2)
    
    # Extract tight bounding box of the ellipse
    rx, ry, rw, rh = cv2.boundingRect(ellipse_pts)
    
    return {
        "ellipse": ellipse,
        "ellipse_pts": ellipse_pts,
        "bbox": (rx, ry, rw, rh),
        "center": (int(ex), int(ey)),
    }


def main():
    print("=== TESTING EXACT SYMMETRICAL ELLIPSE COMPLETION ===")
    page_img = load_image(PROJECT_350_DIR / "03.jpg")
    proj = json.load(open(PROJECT_350_DIR / "project.json", encoding="utf-8"))
    p3 = [p for p in proj["pages"] if p["page_number"] == 3][0]
    blocks = p3["text_blocks"]
    
    blk14 = blocks[1]  # Sample 14 (Top)
    blk15 = blocks[2]  # Sample 15 (Bottom)
    
    bx14, by14, bw14, bh14 = int(blk14["x"]), int(blk14["y"]), int(blk14["width"]), int(blk14["height"])
    bx15, by15, bw15, bh15 = int(blk15["x"]), int(blk15["y"]), int(blk15["width"]), int(blk15["height"])
    
    min_x = min(bx14, bx15) - 100
    min_y = min(by14, by15) - 100
    max_x = max(bx14 + bw14, bx15 + bw15) + 120
    max_y = max(by14 + bh14, by15 + bh15) + 120
    
    crop = page_img[min_y:max_y, min_x:max_x].copy()
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    white_sel = (gray >= 195).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    white_sel = cv2.morphologyEx(white_sel, cv2.MORPH_CLOSE, kernel)
    
    ch, cw = crop.shape[:2]
    l14_x, l14_y = bx14 - min_x, by14 - min_y
    l15_x, l15_y = bx15 - min_x, by15 - min_y
    
    seed_m = np.zeros((ch + 2, cw + 2), dtype=np.uint8)
    cv2.floodFill(white_sel, seed_m, (l14_x + bw14 // 2, l14_y + bh14 // 2), 255, flags=8 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY)
    joined_mask = seed_m[1:-1, 1:-1] * 255
    
    res14 = fit_clean_balloon_ellipse(joined_mask, (l14_x, l14_y, bw14, bh14), is_top=True)
    res15 = fit_clean_balloon_ellipse(joined_mask, (l15_x, l15_y, bw15, bh15), is_top=False)
    
    # Visual Preview for Top Balloon 14
    p14 = crop.copy()
    cv2.polylines(p14, [res14["ellipse_pts"]], isClosed=True, color=(0, 255, 0), thickness=2)
    bx, by, bw, bh = res14["bbox"]
    cv2.rectangle(p14, (bx, by), (bx + bw, by + bh), (0, 255, 255), 2)
    cx, cy = res14["center"]
    cv2.line(p14, (bx, cy), (bx + bw, cy), (255, 150, 0), 2)
    cv2.rectangle(p14, (l14_x, l14_y), (l14_x + bw14, l14_y + bh14), (0, 0, 255), 2)
    cv2.putText(p14, "BALLOON #14 (SYMMETRIC ELLIPSE)", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 2)
    
    # Visual Preview for Bottom Balloon 15
    p15 = crop.copy()
    cv2.polylines(p15, [res15["ellipse_pts"]], isClosed=True, color=(0, 255, 0), thickness=2)
    bx15, by15, bw15, bh15 = res15["bbox"]
    cv2.rectangle(p15, (bx15, by15), (bx15 + bw15, by15 + bh15), (0, 255, 255), 2)
    cx15, cy15 = res15["center"]
    cv2.line(p15, (bx15, cy15), (bx15 + bw15, cy15), (255, 150, 0), 2)
    cv2.rectangle(p15, (l15_x, l15_y), (l15_x + bw15, l15_y + bh15), (0, 0, 255), 2)
    cv2.putText(p15, "BALLOON #15 (SYMMETRIC ELLIPSE)", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 2)
    
    combined = np.hstack([p14, p15])
    out_path = OUTPUT_DIR / "fitted_symmetric_ellipse_sample14_15.png"
    save_image(out_path, combined)
    print(f"Fitted Symmetrical Ellipse Preview saved -> {out_path}")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
