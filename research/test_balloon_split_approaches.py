"""Compare 3 Brainstormed Approaches for Connected Double Balloons (Sample 14 & 15).

Located and executed exclusively inside e:\\houmi\\research\\

Approach A: Morphological Watershed Neck Severing
Approach B: Text-Anchor Radial Curvature Inscription
Approach C: Geodesic Voronoi with Neck Morphological Severing
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


def get_sample_14_15_context():
    page_img = load_image(PROJECT_350_DIR / "03.jpg")
    proj = json.load(open(PROJECT_350_DIR / "project.json", encoding="utf-8"))
    p3 = [p for p in proj["pages"] if p["page_number"] == 3][0]
    blocks = p3["text_blocks"]
    
    blk14 = blocks[1]  # Sample 14
    blk15 = blocks[2]  # Sample 15
    
    bx14, by14, bw14, bh14 = int(blk14["x"]), int(blk14["y"]), int(blk14["width"]), int(blk14["height"])
    bx15, by15, bw15, bh15 = int(blk15["x"]), int(blk15["y"]), int(blk15["width"]), int(blk15["height"])
    
    # Combined crop covering both 14 and 15
    min_x = min(bx14, bx15) - 100
    min_y = min(by14, by15) - 100
    max_x = max(bx14 + bw14, bx15 + bw15) + 120
    max_y = max(by14 + bh14, by15 + bh15) + 120
    
    crop = page_img[min_y:max_y, min_x:max_x].copy()
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    white_sel = (gray >= 195).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    white_sel = cv2.morphologyEx(white_sel, cv2.MORPH_CLOSE, kernel)
    
    # Extract connected double balloon
    ch, cw = crop.shape[:2]
    seed_m = np.zeros((ch + 2, cw + 2), dtype=np.uint8)
    l_bx14, l_by14 = bx14 - min_x, by14 - min_y
    cv2.floodFill(white_sel, seed_m, (l_bx14 + bw14 // 2, l_by14 + bh14 // 2), 255, flags=8 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY)
    joined_mask = seed_m[1:-1, 1:-1] * 255
    
    return {
        "crop": crop,
        "gray": gray,
        "joined_mask": joined_mask,
        "b14": (bx14 - min_x, by14 - min_y, bw14, bh14),
        "b15": (bx15 - min_x, by15 - min_y, bw15, bh15),
    }


def approach_a_watershed(ctx: dict):
    """Approach A: Marker-controlled Watershed on distance transform."""
    mask = ctx["joined_mask"]
    b14 = ctx["b14"]
    b15 = ctx["b15"]
    
    # Compute distance transform
    dist = cv2.distanceTransform((mask > 0).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    
    # Create markers for block 14 and block 15
    markers = np.zeros(mask.shape, dtype=np.int32)
    # Seed 1: inside text block 14
    c14_x, c14_y = b14[0] + b14[2] // 2, b14[1] + b14[3] // 2
    cv2.circle(markers, (c14_x, c14_y), 20, 1, -1)
    
    # Seed 2: inside text block 15
    c15_x, c15_y = b15[0] + b15[2] // 2, b15[1] + b15[3] // 2
    cv2.circle(markers, (c15_x, c15_y), 20, 2, -1)
    
    # Invert distance for watershed topography (valleys at balloon centers)
    dist_8u = cv2.normalize(dist, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    dist_inv = 255 - dist_8u
    dist_inv_bgr = cv2.cvtColor(dist_inv, cv2.COLOR_GRAY2BGR)
    
    cv2.watershed(dist_inv_bgr, markers)
    
    mask14 = ((markers == 1) & (mask > 0)).astype(np.uint8) * 255
    mask15 = ((markers == 2) & (mask > 0)).astype(np.uint8) * 255
    
    return mask14, mask15


def approach_b_radial_raycast(ctx: dict):
    """Approach B: Text-Anchor Radial Ray Inscription with Inflection Stop."""
    mask = ctx["joined_mask"]
    b14 = ctx["b14"]
    cx, cy = b14[0] + b14[2] // 2, b14[1] + b14[3] // 2
    
    h, w = mask.shape
    angles = np.linspace(0, 2 * np.pi, 360, endpoint=False)
    pts = []
    
    for ang in angles:
        dx, dy = np.cos(ang), np.sin(ang)
        r_max = 500
        hit_r = 0
        prev_inside = True
        for r in range(1, r_max):
            px, py = int(cx + r * dx), int(cy + r * dy)
            if px < 0 or px >= w or py < 0 or py >= h or mask[py, px] == 0:
                hit_r = r
                break
            # Inflection check: if ray heads downwards towards b15 and distance exceeds expected balloon radius
            if dy > 0.5 and r > max(b14[2], b14[3]) * 0.9:
                hit_r = r
                break
        if hit_r == 0:
            hit_r = r_max
        pts.append((int(cx + hit_r * dx), int(cy + hit_r * dy)))
        
    mask14 = np.zeros((h, w), dtype=np.uint8)
    cv2.fillPoly(mask14, [np.array(pts, dtype=np.int32)], 255)
    mask14 = cv2.bitwise_and(mask14, mask)
    
    return mask14


def approach_c_geodesic_neck_sever(ctx: dict):
    """Approach C: Geodesic Voronoi with Morphological Isthmus Cut."""
    mask = ctx["joined_mask"]
    b14 = ctx["b14"]
    b15 = ctx["b15"]
    
    seed14 = np.zeros(mask.shape, dtype=np.uint8)
    cv2.rectangle(seed14, (b14[0], b14[1]), (b14[0] + b14[2], b14[1] + b14[3]), 255, -1)
    seed15 = np.zeros(mask.shape, dtype=np.uint8)
    cv2.rectangle(seed15, (b15[0], b15[1]), (b15[0] + b15[2], b15[1] + b15[3]), 255, -1)
    
    d14 = cv2.distanceTransform((cv2.bitwise_and(mask, seed14) > 0).astype(np.uint8), cv2.DIST_L2, 5)
    d15 = cv2.distanceTransform((cv2.bitwise_and(mask, seed15) > 0).astype(np.uint8), cv2.DIST_L2, 5)
    
    # Sever the isthmus using morphological opening on the Voronoi boundary
    voronoi14 = ((d14 >= d15) & (mask > 0)).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    severed14 = cv2.morphologyEx(voronoi14, cv2.MORPH_OPEN, kernel)
    
    return severed14


def main():
    print("=== RUNNING BALLOON SPLIT COMPARATIVE BENCHMARK ===")
    ctx = get_sample_14_15_context()
    crop = ctx["crop"]
    b14 = ctx["b14"]
    
    # Test Approach A
    mA14, mA15 = approach_a_watershed(ctx)
    nz_a = cv2.findNonZero(mA14)
    ax, ay, aw, ah = cv2.boundingRect(nz_a)
    
    pA = crop.copy()
    cnts_a, _ = cv2.findContours(mA14, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(pA, cnts_a, -1, (0, 255, 0), 2)
    cv2.rectangle(pA, (ax, ay), (ax + aw, ay + ah), (0, 255, 255), 2)
    cy_a = ay + ah // 2
    cv2.line(pA, (ax, cy_a), (ax + aw, cy_a), (255, 150, 0), 2)
    cv2.rectangle(pA, (b14[0], b14[1]), (b14[0] + b14[2], b14[1] + b14[3]), (0, 0, 255), 2)
    cv2.putText(pA, "A. WATERSHED SEVERING", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 2)
    
    # Test Approach B
    mB14 = approach_b_radial_raycast(ctx)
    nz_b = cv2.findNonZero(mB14)
    bx, by, bw, bh = cv2.boundingRect(nz_b)
    
    pB = crop.copy()
    cnts_b, _ = cv2.findContours(mB14, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(pB, cnts_b, -1, (0, 255, 0), 2)
    cv2.rectangle(pB, (bx, by), (bx + bw, by + bh), (0, 255, 255), 2)
    cy_b = by + bh // 2
    cv2.line(pB, (bx, cy_b), (bx + bw, cy_b), (255, 150, 0), 2)
    cv2.rectangle(pB, (b14[0], b14[1]), (b14[0] + b14[2], b14[1] + b14[3]), (0, 0, 255), 2)
    cv2.putText(pB, "B. RADIAL RAYCAST INSCRIBE", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 2)
    
    # Test Approach C
    mC14 = approach_c_geodesic_neck_sever(ctx)
    nz_c = cv2.findNonZero(mC14)
    cx, cy, cw, ch = cv2.boundingRect(nz_c)
    
    pC = crop.copy()
    cnts_c, _ = cv2.findContours(mC14, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(pC, cnts_c, -1, (0, 255, 0), 2)
    cv2.rectangle(pC, (cx, cy), (cx + cw, cy + ch), (0, 255, 255), 2)
    cy_c = cy + ch // 2
    cv2.line(pC, (cx, cy_c), (cx + cw, cy_c), (255, 150, 0), 2)
    cv2.rectangle(pC, (b14[0], b14[1]), (b14[0] + b14[2], b14[1] + b14[3]), (0, 0, 255), 2)
    cv2.putText(pC, "C. GEODESIC NECK SEVER", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 2)
    
    # Save 3-panel comparison
    comparison = np.hstack([pA, pB, pC])
    out_path = OUTPUT_DIR / "comparison_approaches_sample14.png"
    save_image(out_path, comparison)
    print(f"Comparison preview generated -> {out_path}")
    
    # Save individual previews
    save_image(OUTPUT_DIR / "approach_A_watershed_14.png", pA)
    save_image(OUTPUT_DIR / "approach_B_radial_14.png", pB)
    save_image(OUTPUT_DIR / "approach_C_geodesic_14.png", pC)
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
