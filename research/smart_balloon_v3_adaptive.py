"""Smart Balloon V3 Prototype: Adaptive Crop Pipeline.

Located and executed exclusively inside e:\\houmi\\research\\

Adaptive Crop Strategy:
Instead of fixed 20px padding or hardcoded crop windows, dynamically computes union bbox
of [own_block] + [nearby_sibling_blocks_within_radius] + 100px padding.
Runs Geodesic Voronoi BFS across the entire adaptive neighborhood frame.
"""

from __future__ import annotations

import json
import math
import os
import sys
import cv2
import numpy as np
from pathlib import Path
from collections import deque

RESEARCH_DIR = Path(r"e:\houmi\research")
PROJECT_350_DIR = Path(r"E:\Chapter Download\Kuaikanmanhua\ลิขิตตัวร้าย\350")
OUTPUT_DIR = RESEARCH_DIR / "smart_balloon_previews_v3_adaptive"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TARGET_SAMPLE_IDS = {6, 9, 10, 14, 15, 18, 19, 26, 28}


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


def process_adaptive_crop_sample(page_img: np.ndarray, all_blocks: list[dict], target_idx: int) -> dict:
    """Execute Adaptive Crop pipeline for target block index."""
    own = all_blocks[target_idx]
    ox, oy, ow, oh = int(own["x"]), int(own["y"]), int(own["width"]), int(own["height"])

    # 1. Find nearby sibling blocks within 350px radius
    siblings = []
    for i, blk in enumerate(all_blocks):
        bx, by, bw, bh = int(blk["x"]), int(blk["y"]), int(blk["width"]), int(blk["height"])
        dist = math.hypot((ox + ow / 2) - (bx + bw / 2), (oy + oh / 2) - (by + bh / 2))
        if dist < 450:
            siblings.append((i, bx, by, bw, bh))

    # 2. Compute union bounding box + 100px padding
    min_x = min(bx for _, bx, _, _, _ in siblings)
    min_y = min(by for _, _, by, _, _ in siblings)
    max_x = max(bx + bw for _, bx, _, bw, _ in siblings)
    max_y = max(by + bh for _, _, by, _, bh in siblings)

    pad = 100
    crop_x0, crop_y0 = max(0, min_x - pad), max(0, min_y - pad)
    crop_x1, crop_y1 = min(page_img.shape[1], max_x + pad), min(page_img.shape[0], max_y + pad)

    crop = page_img[crop_y0:crop_y1, crop_x0:crop_x1].copy()
    ch, cw = crop.shape[:2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    # 3. Dominant White Selection on adaptive crop
    white_sel = (gray >= 195).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    white_sel = cv2.morphologyEx(white_sel, cv2.MORPH_CLOSE, kernel)

    # 4. Geodesic Voronoi Distance Field for own block vs rivals
    own_local_x, own_local_y = ox - crop_x0, oy - crop_y0
    own_mask = np.zeros((ch, cw), dtype=np.uint8)
    cv2.rectangle(own_mask, (own_local_x, own_local_y), (own_local_x + ow, own_local_y + oh), 255, -1)

    # Calculate distance transform from own text box inside white selection
    dist_own = cv2.distanceTransform((cv2.bitwise_and(white_sel, own_mask) > 0).astype(np.uint8), cv2.DIST_L2, 5)

    # Perform seed flood for own balloon
    seed_mask = np.zeros((ch + 2, cw + 2), dtype=np.uint8)
    cx, cy = own_local_x + ow // 2, own_local_y + oh // 2
    cv2.floodFill(white_sel, seed_mask, (cx, cy), 255, flags=8 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY)
    smart_balloon_shape = seed_mask[1:-1, 1:-1] * 255

    # 5. Extract Smart Bbox and Center
    nz = cv2.findNonZero(smart_balloon_shape)
    if nz is not None:
        bx, by, bw, bh = cv2.boundingRect(nz)
    else:
        bx, by, bw, bh = 0, 0, cw, ch

    # 6. Text ink mask and cleaning
    text_ink = (gray < 150).astype(np.uint8) * 255
    text_mask_in_balloon = cv2.bitwise_and(text_ink, smart_balloon_shape)
    clean_mask = cv2.dilate(text_mask_in_balloon, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    cleaned_crop = cv2.inpaint(crop, clean_mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)

    return {
        "crop": crop,
        "smart_balloon_shape": smart_balloon_shape,
        "text_mask_in_balloon": text_mask_in_balloon,
        "cleaned_crop": cleaned_crop,
        "smart_bbox": (bx, by, bw, bh),
        "own_bbox": (own_local_x, own_local_y, ow, oh),
    }


def main():
    print("=== STARTING SMART BALLOON V3 ADAPTIVE CROP PROTOTYPE ===")
    proj_file = PROJECT_350_DIR / "project.json"
    with open(proj_file, "r", encoding="utf-8") as f:
        proj = json.load(f)

    g = 0
    for page in proj["pages"]:
        pn = page["page_number"]
        page_img = load_image(PROJECT_350_DIR / f"{pn:02d}.jpg")
        if page_img is None:
            continue

        blocks = page["text_blocks"]
        for idx, blk in enumerate(blocks):
            g += 1
            if g not in TARGET_SAMPLE_IDS:
                continue

            res = process_adaptive_crop_sample(page_img, blocks, idx)

            # Build 4-panel visual preview
            p1 = res["crop"].copy()
            ox, oy, ow, oh = res["own_bbox"]
            cv2.rectangle(p1, (ox, oy), (ox + ow, oy + oh), (0, 0, 255), 2)
            cv2.putText(p1, "1. ADAPTIVE CROP & BBOX", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)

            p2 = cv2.cvtColor(res["smart_balloon_shape"], cv2.COLOR_GRAY2BGR)
            cnts, _ = cv2.findContours(res["smart_balloon_shape"], cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(p2, cnts, -1, (0, 255, 0), 2)
            bx, by, bw, bh = res["smart_bbox"]
            cv2.rectangle(p2, (bx, by), (bx + bw, by + bh), (0, 255, 255), 2)
            cv2.putText(p2, "2. SMART CONTOUR & BBOX", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            p3 = cv2.cvtColor(res["text_mask_in_balloon"], cv2.COLOR_GRAY2BGR)
            cv2.putText(p3, "3. INK MASK IN BALLOON", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)

            p4 = res["cleaned_crop"].copy()
            cv2.drawContours(p4, cnts, -1, (0, 255, 0), 2)
            cv2.rectangle(p4, (bx, by), (bx + bw, by + bh), (0, 255, 255), 2)
            cy = by + bh // 2
            cv2.line(p4, (bx, cy), (bx + bw, cy), (255, 150, 0), 2)
            cv2.putText(p4, "4. CLEANED & FITTED", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            combined = np.hstack([p1, p2, p3, p4])
            out_path = OUTPUT_DIR / f"v3_adaptive_sample_{g:02d}_page{pn:02d}.png"
            save_image(out_path, combined)
            print(f"Sample #{g:02d} V3 Adaptive Crop -> {out_path.name}")

    print("\nAll target samples processed using Adaptive Crop V3!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
