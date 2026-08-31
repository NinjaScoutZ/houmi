"""Smart Balloon V14: Universal Multi-Type Adaptive Balloon Pipeline (Per-Instance Classification).

Located and executed exclusively inside e:\\houmi\\research\\

Implements:
1. Per-Instance Automatic Shape Classification (Cascading Priority):
   - SPIKY_FUZZY: Thought auras, scream bubbles (roughness > 2.2) -> 3x3 kernel, 1 iter only.
   - RECTANGULAR: Caption boxes (rect_ratio > 0.75 & aspect > 1.8) -> Rounded Rectangle Fitting.
   - ANGULAR: Pointed fantasy bubbles (corners <= 10 & rect < 0.75) -> Douglas-Peucker.
   - SMOOTH_OVAL: Standard speech bubbles -> Dynamic Pinch + Bézier Healing + Tail Pinning.
2. Type-Specific Adaptive Reconstruction with Feature Preservation.
3. 4-Panel Visualization with Type Metadata & Color-Coded Overlays.
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
from typing import Literal

RESEARCH_DIR = Path(r"e:\houmi\research")
CHAPTER_112_DIR = Path(r"E:\Chapter Download\Kuaikanmanhua\ดาว\112")
OUTPUT_DIR = RESEARCH_DIR / "v14_universal_previews"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BalloonType = Literal["SPIKY_FUZZY", "RECTANGULAR", "ANGULAR", "SMOOTH_OVAL"]


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


# =========================================================================
# 1. Cascading Shape Classifier (Priority: SPIKY > RECT > ANGULAR > SMOOTH)
# =========================================================================

def compute_edge_roughness(contour: np.ndarray) -> float:
    """Compute radial variance to detect spiky/fuzzy edges."""
    pts = contour.reshape(-1, 2).astype(np.float32)
    if len(pts) < 10:
        return 0.0
    
    # Centroid
    M = cv2.moments(contour)
    if M["m00"] == 0:
        return 0.0
    cx = M["m10"] / M["m00"]
    cy = M["m01"] / M["m00"]
    
    # Radial distances
    distances = np.linalg.norm(pts - [cx, cy], axis=1)
    
    # Smooth baseline
    smooth_dist = gaussian_filter1d(distances, sigma=10, mode='wrap')
    
    # High-frequency variance
    roughness = float(np.std(distances - smooth_dist))
    return roughness


def compute_rectangularity(contour: np.ndarray) -> tuple[float, float]:
    """Returns (rect_ratio, aspect_ratio)."""
    rect = cv2.minAreaRect(contour)
    box = cv2.boxPoints(rect)
    box_area = cv2.contourArea(box)
    contour_area = cv2.contourArea(contour)
    
    rect_ratio = (contour_area / box_area) if box_area > 0 else 0.0
    
    w, h = rect[1]
    aspect_ratio = max(w, h) / (min(w, h) + 1e-6)
    
    return float(rect_ratio), float(aspect_ratio)


def count_corners(contour: np.ndarray) -> int:
    """Count distinct corners via aggressive Douglas-Peucker."""
    perimeter = cv2.arcLength(contour, True)
    epsilon = 0.015 * perimeter
    approx = cv2.approxPolyDP(contour, epsilon, True)
    return len(approx)


def classify_instance_shape(contour: np.ndarray, text_bbox: tuple[int, int, int, int]) -> tuple[BalloonType, dict]:
    """Cascading classifier: SPIKY > RECT > ANGULAR > SMOOTH."""
    area = cv2.contourArea(contour)
    if area < 100:
        return "SMOOTH_OVAL", {}
    
    # Metric 1: Roughness (SPIKY_FUZZY)
    roughness = compute_edge_roughness(contour)
    # Metric 2: Rectangularity + Aspect (RECTANGULAR)
    rect_ratio, aspect_ratio = compute_rectangularity(contour)
    # Metric 3: Corner Count (ANGULAR)
    corner_count = count_corners(contour)
    
    if roughness > 1.5:
        return "SPIKY_FUZZY", {"roughness": round(roughness, 2)}
    
    if rect_ratio > 0.75 and aspect_ratio > 1.8:
        return "RECTANGULAR", {"rect_ratio": round(rect_ratio, 2), "aspect": round(aspect_ratio, 2)}
    
    if corner_count <= 10 and rect_ratio < 0.75:
        return "ANGULAR", {"corners": corner_count, "roughness": round(roughness, 2)}
    
    # Default: SMOOTH_OVAL
    return "SMOOTH_OVAL", {"roughness": round(roughness, 2)}


# =========================================================================
# 2. Voronoi Instance Separation
# =========================================================================

def separate_balloons_voronoi(combined_mask: np.ndarray, text_centers: list[tuple[int, int]]) -> list[np.ndarray]:
    """Voronoi partitioning based on text centers."""
    ch, cw = combined_mask.shape
    y_grid, x_grid = np.ogrid[:ch, :cw]
    label_map = np.zeros((ch, cw), dtype=np.uint8)
    
    for balloon_id, (cx, cy) in enumerate(text_centers, start=1):
        dist_sq = (x_grid - cx)**2 + (y_grid - cy)**2
        
        if balloon_id == 1:
            label_map[combined_mask > 0] = balloon_id
        else:
            for prev_id in range(1, balloon_id):
                prev_cx, prev_cy = text_centers[prev_id - 1]
                prev_dist_sq = (x_grid - prev_cx)**2 + (y_grid - prev_cy)**2
                
                mask_prev = (label_map == prev_id)
                closer_to_current = (dist_sq < prev_dist_sq) & mask_prev
                label_map[closer_to_current] = balloon_id
            
            unassigned = (combined_mask > 0) & (label_map == 0)
            label_map[unassigned] = balloon_id
    
    separated_masks = []
    for balloon_id in range(1, len(text_centers) + 1):
        separated_masks.append((label_map == balloon_id).astype(np.uint8) * 255)
    
    return separated_masks


# =========================================================================
# 3. Type-Specific Reconstruction Functions
# =========================================================================

def reconstruct_spiky_fuzzy(mask: np.ndarray, text_bbox: tuple[int, int, int, int]) -> np.ndarray:
    """Preserve fine feather detail with minimal smoothing."""
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    cleaned = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    
    cnts, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        return np.array([])
    
    main_cnt = max(cnts, key=cv2.contourArea)
    pts = main_cnt.reshape(-1, 2)
    sx = gaussian_filter1d(pts[:, 0].astype(np.float64), sigma=0.8, mode="wrap")
    sy = gaussian_filter1d(pts[:, 1].astype(np.float64), sigma=0.8, mode="wrap")
    return np.column_stack([sx, sy]).astype(np.int32).reshape(-1, 1, 2)


def reconstruct_rectangular(mask: np.ndarray, text_bbox: tuple[int, int, int, int]) -> np.ndarray:
    """Fit rounded rectangle based on text bbox."""
    tx, ty, tw, th = text_bbox
    padding = 25
    
    x = max(0, tx - padding)
    y = max(0, ty - padding)
    w = tw + 2 * padding
    h = th + 2 * padding
    
    corner_radius = max(6, int(min(w, h) * 0.15))
    
    rect_mask = np.zeros(mask.shape, dtype=np.uint8)
    cv2.rectangle(rect_mask, (x, y), (x + w, y + h), 255, -1)
    
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (corner_radius, corner_radius))
    rect_mask = cv2.erode(rect_mask, kernel)
    rect_mask = cv2.dilate(rect_mask, kernel)
    
    cnts, _ = cv2.findContours(rect_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return np.array([])
    
    return max(cnts, key=cv2.contourArea)


def reconstruct_angular(mask: np.ndarray, text_bbox: tuple[int, int, int, int]) -> np.ndarray:
    """Preserve sharp corners with Douglas-Peucker."""
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    cleaned = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    
    cnts, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        return np.array([])
    
    main_cnt = max(cnts, key=cv2.contourArea)
    epsilon = 0.008 * cv2.arcLength(main_cnt, True)
    return cv2.approxPolyDP(main_cnt, epsilon, True)


def detect_tail_tip(main_cnt: np.ndarray, text_center: tuple[int, int]) -> tuple[int, int] | None:
    """Detect speech tail tip."""
    tc_x, tc_y = text_center
    pts = main_cnt.reshape(-1, 2)
    if len(pts) < 10:
        return None
    
    dists = np.linalg.norm(pts - np.array([tc_x, tc_y]), axis=1)
    max_d = np.max(dists)
    
    tail_candidates = [i for i in range(len(pts)) if dists[i] > 0.70 * max_d]
    
    if tail_candidates:
        best_idx = max(tail_candidates, key=lambda i: dists[i])
        return int(pts[best_idx, 0]), int(pts[best_idx, 1])
    
    return None


def reconstruct_smooth_oval(mask: np.ndarray, text_bbox: tuple[int, int, int, int], text_center: tuple[int, int]) -> np.ndarray:
    """Standard smooth oval with Bézier healing."""
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    cleaned = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=3)
    
    cnts, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        return np.array([])
    
    main_cnt = max(cnts, key=cv2.contourArea)
    pts = main_cnt.reshape(-1, 2).astype(np.float64)
    x = gaussian_filter1d(pts[:, 0], sigma=4.0, mode="wrap")
    y = gaussian_filter1d(pts[:, 1], sigma=4.0, mode="wrap")
    
    smooth_contour = np.column_stack([x, y]).astype(np.int32)
    return smooth_contour.reshape(-1, 1, 2)


# =========================================================================
# 4. Main Page Processor
# =========================================================================

def process_page_universal(page_path: Path, page_number: int, project_data: dict, block_indices: tuple[int, int] = (0, 1)) -> None:
    """Process a single page with universal multi-type balloon handling."""
    t0 = time.time()
    
    page_img = load_image(page_path)
    if page_img is None:
        print(f"Failed to load {page_path}")
        return
    
    page_data = [p for p in project_data["pages"] if p["page_number"] == page_number]
    if not page_data:
        print(f"No data for page {page_number}")
        return
    
    text_blocks = page_data[0]["text_blocks"]
    if len(text_blocks) <= max(block_indices):
        print(f"Page {page_number} does not have enough blocks, skipping")
        return
    
    blk1 = text_blocks[block_indices[0]]
    blk2 = text_blocks[block_indices[1]]
    
    bx1, by1, bw1, bh1 = int(blk1["x"]), int(blk1["y"]), int(blk1["width"]), int(blk1["height"])
    bx2, by2, bw2, bh2 = int(blk2["x"]), int(blk2["y"]), int(blk2["width"]), int(blk2["height"])
    
    # Sort top to bottom
    if by1 > by2:
        bx1, by1, bw1, bh1, bx2, by2, bw2, bh2 = bx2, by2, bw2, bh2, bx1, by1, bw1, bh1
        blk1, blk2 = blk2, blk1
        
    pad = 120
    min_x = max(0, min(bx1, bx2) - pad)
    min_y = max(0, min(by1, by2) - pad)
    max_x = min(page_img.shape[1], max(bx1 + bw1, bx2 + bw2) + pad)
    max_y = min(page_img.shape[0], max(by1 + bh1, by2 + bh2) + pad)
    
    crop = page_img[min_y:max_y, min_x:max_x].copy()
    ch, cw = crop.shape[:2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    
    adjusted_blocks = [
        {"bbox": (bx1 - min_x, by1 - min_y, bw1, bh1), "text": blk1.get("text", "")},
        {"bbox": (bx2 - min_x, by2 - min_y, bw2, bh2), "text": blk2.get("text", "")}
    ]
    
    # Extract raw white for un-blurred classification
    raw_white = (gray >= 185).astype(np.uint8) * 255
    pure_white = cv2.morphologyEx(raw_white, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    
    combined_mask = np.zeros((ch, cw), dtype=np.uint8)
    text_centers = []
    for blk in adjusted_blocks:
        bx, by, bw, bh = blk["bbox"]
        cx = int(bx + bw / 2.0)
        cy = int(by + bh / 2.0)
        text_centers.append((cx, cy))
        seed = np.zeros((ch + 2, cw + 2), dtype=np.uint8)
        cv2.floodFill(pure_white.copy(), seed, (cx, cy), 255, flags=8 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY)
        combined_mask = cv2.bitwise_or(combined_mask, seed[1:-1, 1:-1] * 255)
    
    # Separate instances via Voronoi
    separated_masks = separate_balloons_voronoi(combined_mask, text_centers)
    
    # Classify each instance
    balloon_data = []
    for i, (seg_mask, blk) in enumerate(zip(separated_masks, adjusted_blocks)):
        cnts, _ = cv2.findContours(seg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not cnts:
            continue
        
        main_cnt = max(cnts, key=cv2.contourArea)
        balloon_type, metadata = classify_instance_shape(main_cnt, blk["bbox"])
        
        print(f"Page {page_number} Balloon {i+1}: {balloon_type} {metadata}")
        
        # Type-specific reconstruction
        if balloon_type == "SPIKY_FUZZY":
            contour = reconstruct_spiky_fuzzy(seg_mask, blk["bbox"])
        elif balloon_type == "RECTANGULAR":
            contour = reconstruct_rectangular(seg_mask, blk["bbox"])
        elif balloon_type == "ANGULAR":
            contour = reconstruct_angular(seg_mask, blk["bbox"])
        else:  # SMOOTH_OVAL
            contour = reconstruct_smooth_oval(seg_mask, blk["bbox"], text_centers[i])
        
        tail_tip = detect_tail_tip(contour, text_centers[i]) if balloon_type == "SMOOTH_OVAL" else None
        
        balloon_data.append({
            "id": i + 1,
            "type": balloon_type,
            "contour": contour,
            "tail_tip": tail_tip,
            "text_bbox": blk["bbox"],
            "metadata": metadata
        })
    
    # 4-Panel Visualization
    type_colors = {
        "SPIKY_FUZZY": (255, 100, 255),   # Purple
        "RECTANGULAR": (100, 100, 255),   # Blue
        "ANGULAR": (100, 255, 100),       # Green
        "SMOOTH_OVAL": (255, 200, 100)    # Orange
    }
    
    # Panel 1: Original + BBoxes
    p1 = crop.copy()
    for blk in adjusted_blocks:
        bx, by, bw, bh = blk["bbox"]
        cv2.rectangle(p1, (bx, by), (bx + bw, by + bh), (0, 0, 255), 3)
    cv2.putText(p1, "1. INITIAL BBOXES", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    
    # Panel 2: Separated Instances (Color-Coded by Type)
    p2 = crop.copy()
    for b_data in balloon_data:
        color = type_colors[b_data["type"]]
        mask_viz = np.zeros((ch, cw, 3), dtype=np.uint8)
        cv2.drawContours(mask_viz, [b_data["contour"]], -1, color, -1)
        p2 = cv2.addWeighted(p2, 0.7, mask_viz, 0.3, 0)
        
        bx, by, _, _ = b_data["text_bbox"]
        cv2.putText(p2, b_data["type"], (bx, max(25, by - 10)), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 2)
    cv2.putText(p2, "2. CLASSIFIED INSTANCES", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
    
    # Panel 3: Extracted Contours
    p3 = crop.copy()
    for b_data in balloon_data:
        color = type_colors[b_data["type"]]
        cv2.drawContours(p3, [b_data["contour"]], -1, color, 3)
        if b_data["tail_tip"]:
            cv2.circle(p3, b_data["tail_tip"], 7, (0, 0, 255), -1)
    cv2.putText(p3, "3. ADAPTIVE CONTOURS", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
    
    # Panel 4: Cleaned (Inpainted Text)
    text_ink = (gray < 155).astype(np.uint8) * 255
    total_text_mask = np.zeros((ch, cw), dtype=np.uint8)
    
    for b_data in balloon_data:
        mask_single = np.zeros((ch, cw), dtype=np.uint8)
        cv2.drawContours(mask_single, [b_data["contour"]], -1, 255, -1)
        t_mask = cv2.bitwise_and(text_ink, mask_single)
        total_text_mask = cv2.bitwise_or(total_text_mask, t_mask)
    
    clean_mask = cv2.dilate(total_text_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    p4 = crop.copy()
    p4[clean_mask > 0] = [255, 255, 255]
    
    for b_data in balloon_data:
        color = type_colors[b_data["type"]]
        cv2.drawContours(p4, [b_data["contour"]], -1, color, 2)
    cv2.putText(p4, "4. CLEANED & TYPED", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
    
    # Combine panels
    out_img = np.hstack([p1, p2, p3, p4])
    out_file = OUTPUT_DIR / f"v14_page{page_number:02d}.png"
    save_image(out_file, out_img)
    
    elapsed = time.time() - t0
    print(f"Page {page_number} processed in {elapsed:.2f}s -> {out_file}\n")


def main():
    print("=== RUNNING SMART BALLOON V14 UNIVERSAL PIPELINE ===")
    proj = json.load(open(CHAPTER_112_DIR / "project.json", encoding="utf-8"))
    
    # Process page 10 (SPIKY_FUZZY example)
    process_page_universal(CHAPTER_112_DIR / "10.jpg", 10, proj, block_indices=(0, 1))
    
    # Process page 20 (ANGULAR example)
    process_page_universal(CHAPTER_112_DIR / "20.jpg", 20, proj, block_indices=(0, 1))
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
