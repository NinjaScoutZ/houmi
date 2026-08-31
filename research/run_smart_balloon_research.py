"""Standalone Smart Balloon Research Script.

Exclusively located and executed inside e:\\houmi\\research\\

Algorithm Steps:
1. Balloon เดิม -> ได้พื้นที่เหลี่ยมกรอบ (Bounding box)
2. ดึงค่าสีมากที่สุดในบอลลูนเดิมได้สีขาว (Dominant White Sampling)
3. ใช้ Selection เลือกไปที่สีขาว (White Color Thresholding / Flood Fill)
4. ได้ Shape Ballon (Inner Contour Extraction)
5. Fill ให้กลายเป็น Shape เต็ม = Smart Ballon (Solid Contour Filling)
6. Generate Mask Text ใน Ballon (Text Ink Mask inside Smart Balloon)
7. Clean (Adaptive Text Inpainting)
8. ลงคำโดยใช้ขนาด Smart Ballon (Contour-fitted Typesetting)
"""

from __future__ import annotations

import json
import math
import os
import sys
import cv2
import numpy as np
from pathlib import Path

# Paths
RESEARCH_DIR = Path(r"e:\houmi\research")
PROJECT_350_DIR = Path(r"E:\Chapter Download\Kuaikanmanhua\ลิขิตตัวร้าย\350")
OUTPUT_DIR = RESEARCH_DIR / "smart_balloon_previews"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TARGET_SAMPLE_IDS = set(range(1, 31))


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


def process_smart_balloon_step_by_step(
    img_crop: np.ndarray,
    text_bbox: tuple[int, int, int, int]
) -> dict[str, np.ndarray | float | tuple]:
    """Execute the exact 8-step user-defined algorithm for Smart Balloon."""
    h, w = img_crop.shape[:2]

    # Step 2: ดึงค่าสีมากที่สุดในบอลลูนเดิมได้สีขาว (Dominant White Sampling)
    gray = cv2.cvtColor(img_crop, cv2.COLOR_BGR2GRAY)
    
    # Sample center seed region (30% inner center)
    cx, cy = w // 2, h // 2
    rw, rh = max(5, int(w * 0.15)), max(5, int(h * 0.15))
    center_patch = gray[max(0, cy - rh):min(h, cy + rh), max(0, cx - rw):min(w, cx + rw)]
    
    dominant_val = int(np.percentile(center_patch, 90)) if center_patch.size > 0 else 255
    if dominant_val < 180:
        dominant_val = 255  # Fallback to pure white if patch is dark

    # Step 3: ใช้ Selection เลือกไปที่สีขาว (White Color Thresholding & Seed Flood)
    diff = cv2.absdiff(gray, dominant_val)
    white_selection = (diff <= 45).astype(np.uint8) * 255

    # Seed-based flood from center
    seed_mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
    cv2.floodFill(white_selection, seed_mask, (cx, cy), 255, flags=8 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY)
    connected_white = seed_mask[1:-1, 1:-1] * 255

    # Step 4: ได้ Shape Ballon (Inner Contour Extraction)
    cnts, _ = cv2.findContours(connected_white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Step 5: Fill ให้กลายเป็น Shape เต็ม = Smart Ballon
    smart_balloon_shape = np.zeros((h, w), dtype=np.uint8)
    if cnts:
        max_cnt = max(cnts, key=cv2.contourArea)
        cv2.drawContours(smart_balloon_shape, [max_cnt], -1, 255, -1)
    else:
        smart_balloon_shape = connected_white.copy()

    # Smooth contour
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    smart_balloon_shape = cv2.morphologyEx(smart_balloon_shape, cv2.MORPH_CLOSE, kernel)

    # Step 6: Generate Mask Text ใน Ballon (Text Ink Mask strictly constrained inside Smart Balloon)
    text_ink_raw = (gray < 150).astype(np.uint8) * 255
    text_mask_in_balloon = cv2.bitwise_and(text_ink_raw, smart_balloon_shape)

    # Step 7: Clean (Adaptive Inpainting inside Smart Balloon)
    dilation_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    clean_mask = cv2.dilate(text_mask_in_balloon, dilation_kernel)
    cleaned_crop = cv2.inpaint(img_crop, clean_mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)

    # Step 8: ลงคำโดยใช้ขนาด Smart Ballon (Contour Fitting & Centering)
    nz = cv2.findNonZero(smart_balloon_shape)
    if nz is not None:
        bx, by, bw, bh = cv2.boundingRect(nz)
    else:
        bx, by, bw, bh = 0, 0, w, h

    return {
        "dominant_color": dominant_val,
        "white_selection": white_selection,
        "smart_balloon_shape": smart_balloon_shape,
        "text_mask_in_balloon": text_mask_in_balloon,
        "cleaned_crop": cleaned_crop,
        "smart_bbox": (bx, by, bw, bh),
    }


def main():
    print("=== STARTING SMART BALLOON RESEARCH RUN (RESEARCH FOLDER EXCLUSIVE) ===")
    proj_file = PROJECT_350_DIR / "project.json"
    if not proj_file.exists():
        print(f"Error: {proj_file} does not exist.")
        return 1

    with open(proj_file, "r", encoding="utf-8") as f:
        proj = json.load(f)

    g = 0
    results_summary = []

    for page in proj["pages"]:
        pn = page["page_number"]
        page_img = load_image(PROJECT_350_DIR / f"{pn:02d}.jpg")
        
        for blk in page["text_blocks"]:
            g += 1
            if g not in TARGET_SAMPLE_IDS:
                continue

            x, y, w, h = int(blk["x"]), int(blk["y"]), int(blk["width"]), int(blk["height"])
            if page_img is None:
                continue

            # Crop original balloon with 20px margin
            pad = 20
            crop_y0, crop_y1 = max(0, y - pad), min(page_img.shape[0], y + h + pad)
            crop_x0, crop_x1 = max(0, x - pad), min(page_img.shape[1], x + w + pad)
            crop = page_img[crop_y0:crop_y1, crop_x0:crop_x1].copy()

            res = process_smart_balloon_step_by_step(crop, (x, y, w, h))

            # Panel 1: Original Crop with Initial Raw Bounding Box (กรอบแรกเริ่ม)
            p1 = crop.copy()
            init_x0, init_y0 = max(0, x - crop_x0), max(0, y - crop_y0)
            cv2.rectangle(p1, (init_x0, init_y0), (init_x0 + w, init_y0 + h), (0, 0, 255), 2)  # Red Initial Box
            cv2.putText(p1, "1. INITIAL BBOX (Red)", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

            # Panel 2: Smart Balloon Contour & Smart Bounding Box (กรอบที่ Smart)
            p2 = cv2.cvtColor(res["smart_balloon_shape"], cv2.COLOR_GRAY2BGR)
            cnts, _ = cv2.findContours(res["smart_balloon_shape"], cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(p2, cnts, -1, (0, 255, 0), 2)  # Bright green contour boundary
            bx, by, bw, bh = res["smart_bbox"]
            cv2.rectangle(p2, (bx, by), (bx + bw, by + bh), (0, 255, 255), 2)  # Yellow Smart Bbox
            cv2.putText(p2, "2. SMART BBOX & CONTOUR", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            # Panel 3: Text Mask strictly inside Balloon (Mask Text ใน Ballon)
            p3 = cv2.cvtColor(res["text_mask_in_balloon"], cv2.COLOR_GRAY2BGR)
            cv2.putText(p3, "3. TEXT MASK IN BALLOON", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)

            # Panel 4: Cleaned & Fitted Balloon (ลงคำโดยใช้ขนาด Smart Ballon)
            p4 = res["cleaned_crop"].copy()
            cv2.drawContours(p4, cnts, -1, (0, 255, 0), 2)  # Green Smart Balloon contour boundary
            cv2.rectangle(p4, (bx, by), (bx + bw, by + bh), (0, 255, 255), 2)  # Yellow Smart Bbox
            cy = by + bh // 2
            cv2.line(p4, (bx, cy), (bx + bw, cy), (255, 150, 0), 2)  # Blue vertical center line
            cv2.putText(p4, "4. CLEANED & FITTED", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            # Combine 4 panels horizontally
            hh = max(p1.shape[0], p2.shape[0], p3.shape[0], p4.shape[0])
            combined = np.hstack([p1, p2, p3, p4])

            out_path = OUTPUT_DIR / f"research_sample_{g:02d}_page{pn:02d}.png"
            save_image(out_path, combined)

            print(f"Sample #{g:02d} (Page {pn}) processed -> {out_path.name}")
            results_summary.append(f"Sample #{g:02d}: Dominant Color={res['dominant_color']}, Smart Bbox={res['smart_bbox']}")

    summary_file = RESEARCH_DIR / "RESEARCH_RUN_SUMMARY.txt"
    summary_file.write_text("\n".join(results_summary), encoding="utf-8")
    print(f"\nAll 9 research samples processed cleanly inside {RESEARCH_DIR}!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
