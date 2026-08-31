"""Natural Contour Arc Splitting for Connected Multi-Bubbles (Exact User Specification).

Located and executed exclusively inside e:\\houmi\\research\\

Algorithm:
1. Identify the 2 concave notch/crevice points where the top bubble meets the bottom bubble.
2. For Top Bubble (#14):
   Interpolate a natural convex arc between the two notches matching the curvature of the top bubble
   (closing the top squircle naturally without including the lower bubble).
3. For Bottom Bubble (#15):
   Interpolate a natural convex arc between the two notches matching the curvature of the bottom bubble
   (closing the bottom oval naturally).
4. Compute Smart Bbox and True Center for each separated bubble.
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


def find_concave_notches(contour: np.ndarray, c1: tuple[int, int], c2: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    """Find the 2 concave notch points on the contour where two bubbles merge."""
    cnt = contour.reshape(-1, 2)
    hull = cv2.convexHull(cnt, returnPoints=False)
    defects = cv2.convexityDefects(cnt, hull)
    
    if defects is None:
        # Fallback to closest contour points to the midpoint between c1 and c2
        mid_y = (c1[1] + c2[1]) // 2
        left_pts = [p for p in cnt if abs(p[1] - mid_y) < 60 and p[0] < min(c1[0], c2[0]) + 50]
        right_pts = [p for p in cnt if abs(p[1] - mid_y) < 60 and p[0] > max(c1[0], c2[0]) - 50]
        p1 = min(left_pts, key=lambda p: p[0]) if left_pts else cnt[0]
        p2 = max(right_pts, key=lambda p: p[0]) if right_pts else cnt[len(cnt)//2]
        return np.array(p1), np.array(p2)
    
    # Sort defects by depth (deepest inward notches)
    deep_defects = []
    for i in range(defects.shape[0]):
        item = defects[i].flatten()
        s, e, f, d = int(item[0]), int(item[1]), int(item[2]), float(item[3])
        far_pt = cnt[f]
        # Filter notches that lie between c1 and c2 vertically
        min_y, max_y = min(c1[1], c2[1]), max(c1[1], c2[1])
        if min_y - 20 <= far_pt[1] <= max_y + 20:
            deep_defects.append((d, far_pt))
            
    deep_defects.sort(key=lambda x: x[0], reverse=True)
    if len(deep_defects) >= 2:
        # Take the two deepest notches on opposite sides (left vs right)
        n1 = deep_defects[0][1]
        # Find second notch with maximum distance from n1
        n2 = max(deep_defects[1:], key=lambda x: np.linalg.norm(x[1] - n1))[1]
        return np.array(n1), np.array(n2)
    elif len(deep_defects) == 1:
        n1 = deep_defects[0][1]
        # Approximate second notch on opposite side
        n2 = np.array([c1[0] + (c1[0] - n1[0]), n1[1]])
        return np.array(n1), n2
        
    return cnt[0], cnt[len(cnt)//2]


def natural_bubble_split(crop_img: np.ndarray, joined_mask: np.ndarray, b14: tuple[int, int, int, int], b15: tuple[int, int, int, int]) -> tuple[dict, dict]:
    """Split connected double balloon into two natural closed bubble shapes."""
    c14 = (b14[0] + b14[2] // 2, b14[1] + b14[3] // 2)
    c15 = (b15[0] + b15[2] // 2, b15[1] + b15[3] // 2)
    
    contours, _ = cv2.findContours(joined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    main_cnt = max(contours, key=cv2.contourArea)
    
    # 1. Find the 2 notch points where the bubbles intersect
    n1, n2 = find_concave_notches(main_cnt, c14, c15)
    if n1[0] > n2[0]:
        n1, n2 = n2, n1  # n1 is left notch, n2 is right notch
        
    # 2. Natural convex arc for Top Bubble (#14)
    # The curve arches gently downwards from n1 to n2 following the squircle radius of #14
    dx = n2[0] - n1[0]
    dy = n2[1] - n1[1]
    mid_x = (n1[0] + n2[0]) / 2
    mid_y = (n1[1] + n2[1]) / 2
    
    # Sagitta/bulge for top balloon bottom curve
    bulge14 = 25.0  # slight downward convex curve
    
    # Generate smooth arc points between n1 and n2 for bubble 14
    t_vals = np.linspace(0, 1, 50)
    arc14_pts = []
    for t in t_vals:
        # Quadratic bezier curve
        # Control point below midpoint
        ctrl_x = mid_x
        ctrl_y = mid_y + bulge14
        px = (1 - t)**2 * n1[0] + 2 * (1 - t) * t * ctrl_x + t**2 * n2[0]
        py = (1 - t)**2 * n1[1] + 2 * (1 - t) * t * ctrl_y + t**2 * n2[1]
        arc14_pts.append([int(round(px)), int(round(py))])
        
    # Build Top Bubble #14 Polygon:
    # Contour points from n2 counter-clockwise around the top to n1, then arc14_pts back to n2
    cnt_pts = main_cnt.reshape(-1, 2).tolist()
    # Find indices of closest points to n1 and n2 on contour
    idx_n1 = min(range(len(cnt_pts)), key=lambda i: np.linalg.norm(np.array(cnt_pts[i]) - n1))
    idx_n2 = min(range(len(cnt_pts)), key=lambda i: np.linalg.norm(np.array(cnt_pts[i]) - n2))
    
    # Extract the top segment of the contour (from n1 to n2 going over the top)
    if idx_n1 < idx_n2:
        top_segment = cnt_pts[idx_n2:] + cnt_pts[:idx_n1+1]
    else:
        top_segment = cnt_pts[idx_n2:idx_n1+1]
        
    poly14 = top_segment + arc14_pts
    poly14 = np.array(poly14, dtype=np.int32)
    
    # Create Top Mask
    mask14 = np.zeros_like(joined_mask)
    cv2.fillPoly(mask14, [poly14], 255)
    # Intersect with white selection
    mask14 = cv2.bitwise_and(mask14, joined_mask)
    
    nz14 = cv2.findNonZero(mask14)
    x14, y14, w14, h14 = cv2.boundingRect(nz14) if nz14 is not None else (0, 0, 100, 100)
    
    # 3. Natural convex arc for Bottom Bubble (#15)
    bulge15 = -20.0  # slight upward convex curve closing bottom bubble
    arc15_pts = []
    for t in t_vals:
        ctrl_x = mid_x
        ctrl_y = mid_y + bulge15
        px = (1 - t)**2 * n1[0] + 2 * (1 - t) * t * ctrl_x + t**2 * n2[0]
        py = (1 - t)**2 * n1[1] + 2 * (1 - t) * t * ctrl_y + t**2 * n2[1]
        arc15_pts.append([int(round(px)), int(round(py))])
        
    # Extract bottom segment of contour
    if idx_n1 < idx_n2:
        bot_segment = cnt_pts[idx_n1:idx_n2+1]
    else:
        bot_segment = cnt_pts[idx_n1:] + cnt_pts[:idx_n2+1]
        
    poly15 = bot_segment + arc15_pts[::-1]
    poly15 = np.array(poly15, dtype=np.int32)
    
    mask15 = np.zeros_like(joined_mask)
    cv2.fillPoly(mask15, [poly15], 255)
    mask15 = cv2.bitwise_and(mask15, joined_mask)
    
    nz15 = cv2.findNonZero(mask15)
    x15, y15, w15, h15 = cv2.boundingRect(nz15) if nz15 is not None else (0, 0, 100, 100)
    
    res14 = {
        "mask": mask14,
        "poly": poly14,
        "bbox": (x14, y14, w14, h14),
        "center": (x14 + w14 // 2, y14 + h14 // 2),
        "cut_arc": np.array(arc14_pts, dtype=np.int32),
        "notches": (n1, n2),
    }
    
    res15 = {
        "mask": mask15,
        "poly": poly15,
        "bbox": (x15, y15, w15, h15),
        "center": (x15 + w15 // 2, y15 + h15 // 2),
        "cut_arc": np.array(arc15_pts, dtype=np.int32),
        "notches": (n1, n2),
    }
    
    return res14, res15


def main():
    print("=== RUNNING NATURAL CONTOUR ARC SPLIT (EXACT USER SPEC) ===")
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
    
    res14, res15 = natural_bubble_split(crop, joined_mask, (l14_x, l14_y, bw14, bh14), (l15_x, l15_y, bw15, bh15))
    
    # 1. Visual Preview for Top Balloon 14
    p14 = crop.copy()
    # Fill natural pink overlay as in user drawing
    overlay14 = p14.copy()
    cv2.fillPoly(overlay14, [res14["poly"]], (180, 180, 255))
    cv2.addWeighted(overlay14, 0.45, p14, 0.55, 0, p14)
    
    cv2.polylines(p14, [res14["poly"]], isClosed=True, color=(0, 255, 0), thickness=2)
    # Highlight the natural cutting curve in blue as in user drawing
    cv2.polylines(p14, [res14["cut_arc"]], isClosed=False, color=(255, 100, 50), thickness=3)
    # Mark the 2 notch points
    n1, n2 = res14["notches"]
    cv2.circle(p14, tuple(n1), 6, (0, 0, 255), -1)
    cv2.circle(p14, tuple(n2), 6, (0, 0, 255), -1)
    
    bx, by, bw, bh = res14["bbox"]
    cv2.rectangle(p14, (bx, by), (bx + bw, by + bh), (0, 255, 255), 2)
    cx, cy = res14["center"]
    cv2.line(p14, (bx, cy), (bx + bw, cy), (255, 150, 0), 2)
    cv2.rectangle(p14, (l14_x, l14_y), (l14_x + bw14, l14_y + bh14), (0, 0, 255), 2)
    cv2.putText(p14, "TOP BUBBLE #14 (NATURAL SQUIRCLE)", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 0), 2)
    
    # 2. Visual Preview for Bottom Balloon 15
    p15 = crop.copy()
    overlay15 = p15.copy()
    cv2.fillPoly(overlay15, [res15["poly"]], (180, 180, 255))
    cv2.addWeighted(overlay15, 0.45, p15, 0.55, 0, p15)
    
    cv2.polylines(p15, [res15["poly"]], isClosed=True, color=(0, 255, 0), thickness=2)
    cv2.polylines(p15, [res15["cut_arc"]], isClosed=False, color=(255, 100, 50), thickness=3)
    cv2.circle(p15, tuple(n1), 6, (0, 0, 255), -1)
    cv2.circle(p15, tuple(n2), 6, (0, 0, 255), -1)
    
    bx15, by15, bw15, bh15 = res15["bbox"]
    cv2.rectangle(p15, (bx15, by15), (bx15 + bw15, by15 + bh15), (0, 255, 255), 2)
    cx15, cy15 = res15["center"]
    cv2.line(p15, (bx15, cy15), (bx15 + bw15, cy15), (255, 150, 0), 2)
    cv2.rectangle(p15, (l15_x, l15_y), (l15_x + bw15, l15_y + bh15), (0, 0, 255), 2)
    cv2.putText(p15, "BOTTOM BUBBLE #15 (NATURAL OVAL)", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 0), 2)
    
    combined = np.hstack([p14, p15])
    out_path = OUTPUT_DIR / "natural_curve_split_sample14_15.png"
    save_image(out_path, combined)
    print(f"Natural Curve Split Preview saved -> {out_path}")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
