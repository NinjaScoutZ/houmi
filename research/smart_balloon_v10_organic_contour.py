"""Smart Balloon V10: Organic Contour-Following & Feature-Preserving Pipeline (Polished).

Located and executed exclusively inside e:\\houmi\\research\\

Principles:
1. Instance-Aware Unified Organic Tracing (retains true comic line art, neck curves, and speech tail).
2. Clean feature-preserving adaptive smoothing.
3. Rich Structured Output (SVG-ready polygon paths, Tail tip, Centroid per text block).
4. 4-Panel Organic Visualization:
   - Panel 1: INITIAL BBOXES (RED)
   - Panel 2: INSTANCE TEXT ANCHORS & SOFT REGIONS
   - Panel 3: TRACED ORGANIC OUTLINE (GREEN - 100% REAL COMIC SHAPE + TAIL)
   - Panel 4: CLEANED & TRUE CENTERS (INPAINT + DEDICATED CENTER LINES)
"""

from __future__ import annotations

import json
import math
import os
import sys
import cv2
import numpy as np
from pathlib import Path
from scipy.interpolate import splprep, splev
from scipy.ndimage import gaussian_filter1d

RESEARCH_DIR = Path(r"e:\houmi\research")
PROJECT_350_DIR = Path(r"E:\Chapter Download\Kuaikanmanhua\ลิขิตตัวร้าย\350")
OUTPUT_DIR = RESEARCH_DIR / "v10_organic_previews"
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


def detect_tail_tip(contour: np.ndarray, text_center: tuple[int, int]) -> tuple[int, int] | None:
    tc_x, tc_y = text_center
    pts = contour.reshape(-1, 2)
    dists = np.linalg.norm(pts - np.array([tc_x, tc_y]), axis=1)
    
    pts_f = pts.astype(np.float64)
    x = gaussian_filter1d(pts_f[:, 0], sigma=2.0, mode="wrap")
    y = gaussian_filter1d(pts_f[:, 1], sigma=2.0, mode="wrap")
    dx = np.gradient(x)
    dy = np.gradient(y)
    ddx = np.gradient(dx)
    ddy = np.gradient(dy)
    denom = np.maximum((dx**2 + dy**2)**1.5, 1e-6)
    curv = np.abs((dx * ddy - dy * ddx) / denom)
    
    max_d = np.max(dists)
    tail_candidates = [i for i in range(len(pts)) if dists[i] > 0.75 * max_d and curv[i] > np.percentile(curv, 85)]
    
    if tail_candidates:
        best_idx = max(tail_candidates, key=lambda i: dists[i])
        return int(pts[best_idx, 0]), int(pts[best_idx, 1])
    return None


def smooth_organic_contour(contour: np.ndarray, tail_tip: tuple[int, int] | None) -> np.ndarray:
    pts = contour.reshape(-1, 2).astype(np.float64)
    n_pts = len(pts)
    if n_pts < 10:
        return contour.reshape(-1, 1, 2)
        
    smooth_x = gaussian_filter1d(pts[:, 0], sigma=1.5, mode="wrap")
    smooth_y = gaussian_filter1d(pts[:, 1], sigma=1.5, mode="wrap")
    smoothed = np.column_stack([smooth_x, smooth_y])
    
    if tail_tip is not None:
        dists = np.linalg.norm(smoothed - np.array(tail_tip), axis=1)
        tip_idx = np.argmin(dists)
        smoothed[tip_idx] = [tail_tip[0], tail_tip[1]]
        
    return smoothed.astype(np.int32).reshape(-1, 1, 2)


def process_organic_balloons_v10(crop: np.ndarray, text_blocks: list[dict]) -> tuple[np.ndarray, dict]:
    ch, cw = crop.shape[:2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    
    # 1. Pure White Shared Interior Extraction
    pure_white = (gray >= 195).astype(np.uint8) * 255
    pure_white = cv2.morphologyEx(pure_white, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
    pure_white = cv2.morphologyEx(pure_white, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    
    # Unified floodfill for conjoined cluster
    combined_mask = np.zeros((ch, cw), dtype=np.uint8)
    text_centers = []
    for blk in text_blocks:
        bx, by, bw, bh = blk["bbox"]
        cx = int(bx + bw / 2.0)
        cy = int(by + bh / 2.0)
        text_centers.append((cx, cy))
        seed = np.zeros((ch + 2, cw + 2), dtype=np.uint8)
        cv2.floodFill(pure_white.copy(), seed, (cx, cy), 255, flags=8 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY)
        combined_mask = cv2.bitwise_or(combined_mask, seed[1:-1, 1:-1] * 255)
        
    # 2. Extract the Full Unified Hand-Drawn Organic Contour
    cnts, _ = cv2.findContours(combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    main_cnt = max(cnts, key=cv2.contourArea)
    
    tail_tip = detect_tail_tip(main_cnt, text_centers[1])
    smooth_cnt = smooth_organic_contour(main_cnt, tail_tip)
    
    # 3. Soft Region & Dedicated Center Localization for each text block
    c1, c2 = text_centers[0], text_centers[1]
    y_grid, x_grid = np.ogrid[:ch, :cw]
    d1 = np.sqrt((x_grid - c1[0])**2 + (y_grid - c1[1])**2)
    d2 = np.sqrt((x_grid - c2[0])**2 + (y_grid - c2[1])**2)
    
    soft_reg1 = (combined_mask > 0) & (d1 <= d2)
    soft_reg2 = (combined_mask > 0) & (d2 < d1)
    
    # Individual Center Lines
    M1 = cv2.moments(soft_reg1.astype(np.uint8))
    cx1 = int(M1["m10"] / M1["m00"]) if M1["m00"] > 0 else c1[0]
    cy1 = int(M1["m01"] / M1["m00"]) if M1["m00"] > 0 else c1[1]
    nz1 = cv2.findNonZero(soft_reg1.astype(np.uint8))
    rx1, ry1, rw1, rh1 = cv2.boundingRect(nz1)
    
    M2 = cv2.moments(soft_reg2.astype(np.uint8))
    cx2 = int(M2["m10"] / M2["m00"]) if M2["m00"] > 0 else c2[0]
    cy2 = int(M2["m01"] / M2["m00"]) if M2["m00"] > 0 else c2[1]
    nz2 = cv2.findNonZero(soft_reg2.astype(np.uint8))
    rx2, ry2, rw2, rh2 = cv2.boundingRect(nz2)
    
    # 4. Text Ink Extraction & Clean Inpainting
    text_ink = (gray < 155).astype(np.uint8) * 255
    text_mask = cv2.bitwise_and(text_ink, combined_mask)
    
    clean_mask = cv2.dilate(text_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    cleaned = cv2.inpaint(crop, clean_mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
    cleaned[clean_mask > 0] = [255, 255, 255]
    
    # 5. Build 4-Panel Visualization
    
    # Panel 1: INITIAL BBOXES (RED)
    p1 = crop.copy()
    for blk in text_blocks:
        bx, by, bw, bh = blk["bbox"]
        cv2.rectangle(p1, (bx, by), (bx + bw, by + bh), (0, 0, 255), 3)
    cv2.putText(p1, "1. INITIAL BBOXES (RED)", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (0, 0, 255), 2)
    
    # Panel 2: INSTANCE LABELS (OVERLAP PRESERVED)
    p2 = crop.copy()
    ov2 = p2.copy()
    ov2[soft_reg1] = [255, 200, 200]
    ov2[soft_reg2] = [200, 255, 200]
    cv2.addWeighted(ov2, 0.40, p2, 0.60, 0, p2)
    cv2.circle(p2, c1, 6, (255, 0, 0), -1)
    cv2.circle(p2, c2, 6, (0, 180, 0), -1)
    cv2.putText(p2, "2. INSTANCE ANCHORS & ZONES", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 150, 255), 2)
    
    # Panel 3: TRACED ORGANIC OUTLINE (GREEN)
    p3 = crop.copy()
    ov3 = p3.copy()
    cv2.fillPoly(ov3, [smooth_cnt], (240, 240, 255))
    cv2.addWeighted(ov3, 0.35, p3, 0.65, 0, p3)
    cv2.drawContours(p3, [smooth_cnt], -1, (0, 255, 0), 3)
    if tail_tip is not None:
        cv2.circle(p3, tail_tip, 7, (0, 0, 255), -1)  # Red dot on tail tip
    cv2.putText(p3, "3. TRACED ORGANIC OUTLINE + TAIL", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
    
    # Panel 4: CLEANED & TRUE CENTERS
    p4 = cleaned.copy()
    cv2.drawContours(p4, [smooth_cnt], -1, (0, 255, 0), 3)
    # Center line for Top Balloon
    cv2.line(p4, (rx1, cy1), (rx1 + rw1, cy1), (255, 150, 0), 3)
    cv2.circle(p4, (cx1, cy1), 6, (255, 100, 0), -1)
    # Center line for Bottom Balloon
    cv2.line(p4, (rx2, cy2), (rx2 + rw2, cy2), (255, 150, 0), 3)
    cv2.circle(p4, (cx2, cy2), 6, (255, 100, 0), -1)
    cv2.putText(p4, "4. CLEANED & TRUE CENTERS", (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
    
    data_out = {
        "unified_contour": smooth_cnt.reshape(-1, 2).tolist(),
        "tail_tip": tail_tip,
        "balloons": [
            {"id": 1, "text": text_blocks[0]["text"], "center": (cx1, cy1), "bbox": (rx1, ry1, rw1, rh1)},
            {"id": 2, "text": text_blocks[1]["text"], "center": (cx2, cy2), "bbox": (rx2, ry2, rw2, rh2)},
        ]
    }
    
    return np.hstack([p1, p2, p3, p4]), data_out


def main():
    print("=== STARTING POLISHED SMART BALLOON V10 ===")
    page_img = load_image(PROJECT_350_DIR / "03.jpg")
    proj = json.load(open(PROJECT_350_DIR / "project.json", encoding="utf-8"))
    p3 = [p for p in proj["pages"] if p["page_number"] == 3][0]
    blocks = p3["text_blocks"]
    
    blk14 = blocks[1]  # Top Balloon
    blk15 = blocks[2]  # Bottom Balloon
    
    bx14, by14, bw14, bh14 = int(blk14["x"]), int(blk14["y"]), int(blk14["width"]), int(blk14["height"])
    bx15, by15, bw15, bh15 = int(blk15["x"]), int(blk15["y"]), int(blk15["width"]), int(blk15["height"])
    
    min_x = 220
    min_y = 5900
    max_x = 1150
    max_y = 6850
    
    crop = page_img[min_y:max_y, min_x:max_x].copy()
    
    l14_x, l14_y = bx14 - min_x, by14 - min_y
    l15_x, l15_y = bx15 - min_x, by15 - min_y
    
    text_data = [
        {"bbox": (l14_x, l14_y, bw14, bh14), "text": blk14.get("text", "")},
        {"bbox": (l15_x, l15_y, bw15, bh15), "text": blk15.get("text", "")}
    ]
    
    v10_4panel, data_dict = process_organic_balloons_v10(crop, text_data)
    
    out_file = OUTPUT_DIR / "v10_organic_conjoined_page03.png"
    save_image(out_file, v10_4panel)
    print(f"V10 Organic 4-Panel Preview saved -> {out_file}")
    
    with open(OUTPUT_DIR / "balloon_data_v10.json", "w", encoding="utf-8") as f:
        json.dump(data_dict, f, indent=2, ensure_ascii=False)
        
    print("\nPolished Smart Balloon V10 Pipeline completed successfully!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
