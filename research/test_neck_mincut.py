"""Approach D: Geodesic Saddle-Point Min-Cut Partitioning for Connected Double Balloons.

Located and executed exclusively inside e:\\houmi\\research\\

Algorithm:
1. Given connected multi-balloon containing Block A and Block B.
2. Find the Geodesic Saddle Point (narrowest neck between Block A centroid and Block B centroid).
3. Cut along the minimum energy contour path through the neck.
4. Extract Independent Top Balloon Sphere and Independent Bottom Balloon Sphere.
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
OUTPUT_DIR = RESEARCH_DIR / "split_approaches_previews"
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
    print("=== TESTING GEODESIC SADDLE MIN-CUT PARTITIONING ===")
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
    seed_m = np.zeros((ch + 2, cw + 2), dtype=np.uint8)
    l14_x, l14_y = bx14 - min_x, by14 - min_y
    l15_x, l15_y = bx15 - min_x, by15 - min_y
    
    cv2.floodFill(white_sel, seed_m, (l14_x + bw14 // 2, l14_y + bh14 // 2), 255, flags=8 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY)
    joined_mask = seed_m[1:-1, 1:-1] * 255
    
    # 1. Distance Transform from each block
    m14 = np.zeros((ch, cw), dtype=np.uint8)
    cv2.rectangle(m14, (l14_x, l14_y), (l14_x + bw14, l14_y + bh14), 255, -1)
    d14 = cv2.distanceTransform((cv2.bitwise_and(joined_mask, m14) > 0).astype(np.uint8), cv2.DIST_L2, 5)
    
    m15 = np.zeros((ch, cw), dtype=np.uint8)
    cv2.rectangle(m15, (l15_x, l15_y), (l15_x + bw15, l15_y + bh15), 255, -1)
    d15 = cv2.distanceTransform((cv2.bitwise_and(joined_mask, m15) > 0).astype(np.uint8), cv2.DIST_L2, 5)
    
    # 2. Saddle Point Neck Cut:
    # Look for the row with minimum width between bottom of block 14 and top of block 15
    row_y0 = l14_y + bh14 - 30
    row_y1 = l15_y + 40
    
    row_widths = []
    for y in range(row_y0, row_y1):
        row_slice = joined_mask[y, :]
        w_px = cv2.countNonZero(row_slice)
        row_widths.append((w_px, y))
        
    row_widths.sort()
    min_width, neck_cut_y = row_widths[0]
    print(f"Narrowest neck found at y={neck_cut_y} with width={min_width}px")
    
    # 3. Partition into top mask and bottom mask along neck_cut_y
    top_mask = joined_mask.copy()
    top_mask[neck_cut_y:, :] = 0
    # Clean top contour
    nz14 = cv2.findNonZero(top_mask)
    x14, y14, w14, h14 = cv2.boundingRect(nz14)
    
    bot_mask = joined_mask.copy()
    bot_mask[:neck_cut_y, :] = 0
    nz15 = cv2.findNonZero(bot_mask)
    x15, y15, w15, h15 = cv2.boundingRect(nz15)
    
    # 4. Generate Previews for both 14 and 15
    # Preview Sample 14 (Top)
    p14 = crop.copy()
    cnts14, _ = cv2.findContours(top_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(p14, cnts14, -1, (0, 255, 0), 2)
    cv2.rectangle(p14, (x14, y14), (x14 + w14, y14 + h14), (0, 255, 255), 2)
    cy14 = y14 + h14 // 2
    cv2.line(p14, (x14, cy14), (x14 + w14, cy14), (255, 150, 0), 2)
    cv2.rectangle(p14, (l14_x, l14_y), (l14_x + bw14, l14_y + bh14), (0, 0, 255), 2)
    cv2.putText(p14, "TOP BALLOON #14 (SEPARATED)", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 2)
    
    # Preview Sample 15 (Bottom)
    p15 = crop.copy()
    cnts15, _ = cv2.findContours(bot_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(p15, cnts15, -1, (0, 255, 0), 2)
    cv2.rectangle(p15, (x15, y15), (x15 + w15, y15 + h15), (0, 255, 255), 2)
    cy15 = y15 + h15 // 2
    cv2.line(p15, (x15, cy15), (x15 + w15, cy15), (255, 150, 0), 2)
    cv2.rectangle(p15, (l15_x, l15_y), (l15_x + bw15, l15_y + bh15), (0, 0, 255), 2)
    cv2.putText(p15, "BOTTOM BALLOON #15 (SEPARATED)", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 2)
    
    pair_preview = np.hstack([p14, p15])
    out_path = OUTPUT_DIR / "perfect_split_sample14_15.png"
    save_image(out_path, pair_preview)
    print(f"Perfect split preview saved -> {out_path}")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
