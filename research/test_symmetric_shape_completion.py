"""Symmetric Shape Reconstruction & Parametric Completion for Manga Balloons.

Located and executed exclusively inside e:\\houmi\\research\\

Principle:
A speech balloon is fundamentally a natural symmetrical convex shape (ellipse/superellipse).
When a neck/tail protrudes out (breaking symmetry), we reconstruct the natural boundary by:
1. Identifying clean, unoccluded contour arcs (where no neck exists).
2. Fitting a robust parametric ellipse / superellipse.
3. Mirroring radial distances from the clean opposite side to complete the occluded/protruding arc.
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


def reconstruct_symmetric_balloon(mask: np.ndarray, text_bbox: tuple[int, int, int, int]) -> dict:
    """Reconstruct natural symmetrical balloon shape from clean contour arcs."""
    bx, by, bw, bh = text_bbox
    cx, cy = bx + bw // 2, by + bh // 2
    h, w = mask.shape
    
    # 1. Cast 360 radial rays from text centroid
    angles = np.linspace(0, 2 * np.pi, 360, endpoint=False)
    radii = []
    
    for ang in angles:
        dx, dy = np.cos(ang), np.sin(ang)
        r_val = 0
        for r in range(1, 600):
            px, py = int(cx + r * dx), int(cy + r * dy)
            if px < 0 or px >= w or py < 0 or py >= h or mask[py, px] == 0:
                r_val = r
                break
        radii.append(r_val)
        
    radii = np.array(radii, dtype=np.float64)
    
    # 2. Detect protrusion anomalies:
    # A natural balloon radius smoothly varies. We compare with opposite side (r(theta + pi))
    # and mirrored horizontal side (r(pi - theta))
    reconstructed_radii = radii.copy()
    
    # Expected radius model from clean top-half (angles between 0 and pi)
    for i, ang in enumerate(angles):
        # Opposite index (180 deg away)
        opp_idx = (i + 180) % 360
        # Horizontal mirror index
        # ang mirrored across vertical axis = pi - ang
        mirror_ang = (np.pi - ang) % (2 * np.pi)
        mirror_idx = int(round(mirror_ang / (2 * np.pi) * 360)) % 360
        
        # Vertical mirror index (across horizontal axis)
        vert_mirror_ang = (-ang) % (2 * np.pi)
        vert_mirror_idx = int(round(vert_mirror_ang / (2 * np.pi) * 360)) % 360
        
        r_cur = radii[i]
        r_opp = radii[opp_idx]
        r_hmirror = radii[mirror_idx]
        r_vmirror = radii[vert_mirror_idx]
        
        # If radius in current direction is abnormally larger than mirrored opposite/vertical side
        # (e.g. protruding neck pointing downwards/rightwards), reconstruct from clean mirror!
        expected_r = min(r_cur, r_vmirror * 1.08, (r_opp + r_hmirror) / 2 * 1.15)
        
        if r_cur > expected_r * 1.20 and r_cur > max(bw, bh) * 0.75:
            reconstructed_radii[i] = expected_r
            
    # 3. Smooth the reconstructed radial curve (Gaussian filtering along perimeter)
    reconstructed_radii = cv2.GaussianBlur(reconstructed_radii.reshape(-1, 1), (31, 1), 5.0).flatten()
    
    # 4. Generate reconstructed polygon
    pts = []
    for i, ang in enumerate(angles):
        r = reconstructed_radii[i]
        px = int(cx + r * np.cos(ang))
        py = int(cy + r * np.sin(ang))
        pts.append((px, py))
        
    pts = np.array(pts, dtype=np.int32)
    
    # 5. Create clean shape mask
    recon_mask = np.zeros((h, w), dtype=np.uint8)
    cv2.fillPoly(recon_mask, [pts], 255)
    
    # 6. Extract regularized bounding box and true symmetrical center
    nz = cv2.findNonZero(recon_mask)
    rx, ry, rw, rh = cv2.boundingRect(nz)
    
    # Also fit an exact smooth ellipse on the reconstructed polygon
    ellipse = None
    if len(pts) >= 5:
        ellipse = cv2.fitEllipse(pts)
        
    return {
        "recon_mask": recon_mask,
        "recon_pts": pts,
        "recon_bbox": (rx, ry, rw, rh),
        "true_center": (rx + rw // 2, ry + rh // 2),
        "fitted_ellipse": ellipse,
    }


def main():
    print("=== TESTING SYMMETRIC SHAPE RECONSTRUCTION ===")
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
    
    # 1. Flood fill to get full joined white region
    seed_m = np.zeros((ch + 2, cw + 2), dtype=np.uint8)
    cv2.floodFill(white_sel, seed_m, (l14_x + bw14 // 2, l14_y + bh14 // 2), 255, flags=8 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY)
    joined_mask = seed_m[1:-1, 1:-1] * 255
    
    # 2. Reconstruct Symmetrical Shape for Block 14 (Top Balloon)
    res14 = reconstruct_symmetric_balloon(joined_mask, (l14_x, l14_y, bw14, bh14))
    
    # 3. Reconstruct Symmetrical Shape for Block 15 (Bottom Balloon)
    res15 = reconstruct_symmetric_balloon(joined_mask, (l15_x, l15_y, bw15, bh15))
    
    # 4. Generate Visual Previews
    # Top Balloon #14 Preview
    p14 = crop.copy()
    cv2.polylines(p14, [res14["recon_pts"]], isClosed=True, color=(0, 255, 0), thickness=2)
    rx, ry, rw, rh = res14["recon_bbox"]
    cv2.rectangle(p14, (rx, ry), (rx + rw, ry + rh), (0, 255, 255), 2)
    tc_x, tc_y = res14["true_center"]
    cv2.line(p14, (rx, tc_y), (rx + rw, tc_y), (255, 150, 0), 2)
    cv2.rectangle(p14, (l14_x, l14_y), (l14_x + bw14, l14_y + bh14), (0, 0, 255), 2)
    cv2.putText(p14, "TOP BALLOON #14 (SYMMETRIC SHAPE)", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 2)
    
    # Bottom Balloon #15 Preview
    p15 = crop.copy()
    cv2.polylines(p15, [res15["recon_pts"]], isClosed=True, color=(0, 255, 0), thickness=2)
    rx15, ry15, rw15, rh15 = res15["recon_bbox"]
    cv2.rectangle(p15, (rx15, ry15), (rx15 + rw15, ry15 + rh15), (0, 255, 255), 2)
    tc15_x, tc15_y = res15["true_center"]
    cv2.line(p15, (rx15, tc15_y), (rx15 + rw15, tc15_y), (255, 150, 0), 2)
    cv2.rectangle(p15, (l15_x, l15_y), (l15_x + bw15, l15_y + bh15), (0, 0, 255), 2)
    cv2.putText(p15, "BOTTOM BALLOON #15 (SYMMETRIC SHAPE)", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 2)
    
    # Combined Side-by-Side
    combined = np.hstack([p14, p15])
    out_path = OUTPUT_DIR / "symmetric_shape_completion_sample14_15.png"
    save_image(out_path, combined)
    print(f"Symmetric Shape Completion Preview saved -> {out_path}")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
