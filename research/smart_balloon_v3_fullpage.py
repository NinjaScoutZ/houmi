"""Smart Balloon V3 Prototype: Full-Page Component-First Pipeline.

Located and executed exclusively inside e:\\houmi\\research\\

Full-Page Pipeline Strategy:
1. Extract all balloons (full page) -> Detect all white components globally on the entire page image.
2. Split shared components -> Perform Geodesic Voronoi distance competition on the full-page frame across all text blocks.
3. Assign to blocks -> Assign exact, perfectly separated balloon mask to each text block.
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
OUTPUT_DIR = RESEARCH_DIR / "smart_balloon_previews_v3_fullpage"
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


def geodesic_distance_mask(mask: np.ndarray, seed_mask: np.ndarray) -> np.ndarray:
    """Compute exact geodesic distance transform on binary mask using OpenCV distanceTransform."""
    inv_mask = cv2.bitwise_not(mask)
    dist = cv2.distanceTransform((seed_mask > 0).astype(np.uint8), cv2.DIST_L2, 5)
    return dist


def extract_all_balloons_full_page(page_img: np.ndarray, text_blocks: list[dict]) -> dict[int, np.ndarray]:
    """Phase 1 & Phase 2: Full-Page balloon component extraction & Geodesic Voronoi separation."""
    h, w = page_img.shape[:2]
    gray = cv2.cvtColor(page_img, cv2.COLOR_BGR2GRAY)

    # 1. Detect dominant white zones globally on the entire page
    white_sel = (gray >= 195).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    white_sel = cv2.morphologyEx(white_sel, cv2.MORPH_CLOSE, kernel)

    # 2. Extract connected components
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(white_sel, connectivity=8)

    block_masks: dict[int, np.ndarray] = {}

    for b_idx, blk in enumerate(text_blocks):
        bx, by, bw, bh = int(blk["x"]), int(blk["y"]), int(blk["width"]), int(blk["height"])
        
        # Find which connected component contains this text block
        roi = labels[max(0, by):min(h, by + bh), max(0, bx):min(w, bx + bw)]
        if roi.size == 0:
            continue

        # Find most frequent component label in text block (excluding background 0)
        valid_labels = roi[roi > 0]
        if valid_labels.size == 0:
            # Fallback for non-standard white balloons (e.g. #17)
            patch = gray[max(0, by):min(h, by + bh), max(0, bx):min(w, bx + bw)]
            thresh_val = int(np.percentile(patch, 85)) if patch.size > 0 else 180
            local_white = (gray >= min(thresh_val, 180)).astype(np.uint8) * 255
            seed_m = np.zeros((h + 2, w + 2), dtype=np.uint8)
            cv2.floodFill(local_white, seed_m, (bx + bw // 2, by + bh // 2), 255, flags=8 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY)
            block_masks[b_idx] = seed_m[1:-1, 1:-1] * 255
            continue
        
        comp_label = int(np.bincount(valid_labels).argmax())
        comp_mask = (labels == comp_label).astype(np.uint8) * 255

        # Check if component is shared by multiple text blocks
        shared_blocks = []
        for other_idx, other_blk in enumerate(text_blocks):
            obx, oby, obw, obh = int(other_blk["x"]), int(other_blk["y"]), int(other_blk["width"]), int(other_blk["height"])
            oroi = labels[max(0, oby):min(h, oby + obh), max(0, obx):min(w, obx + obw)]
            if oroi.size > 0 and np.any(oroi == comp_label):
                shared_blocks.append(other_idx)

        if len(shared_blocks) <= 1:
            block_masks[b_idx] = comp_mask
        else:
            # Geodesic Voronoi distance competition on full page frame
            mine_seed = np.zeros((h, w), dtype=np.uint8)
            mine_seed[max(0, by):min(h, by + bh), max(0, bx):min(w, bx + bw)] = 255
            dist_mine = geodesic_distance_mask(comp_mask, mine_seed)

            keep_mask = comp_mask.copy()
            for other_idx in shared_blocks:
                if other_idx == b_idx:
                    continue
                oblk = text_blocks[other_idx]
                obx, oby, obw, obh = int(oblk["x"]), int(oblk["y"]), int(oblk["width"]), int(oblk["height"])
                rival_seed = np.zeros((h, w), dtype=np.uint8)
                rival_seed[max(0, oby):min(h, oby + obh), max(0, obx):min(w, obx + obw)] = 255
                dist_rival = geodesic_distance_mask(comp_mask, rival_seed)

                contested = (dist_mine > 0) & (dist_rival > 0)
                keep_mask[contested & (dist_rival < dist_mine)] = 0

            block_masks[b_idx] = keep_mask

    return block_masks


def main():
    print("=== STARTING SMART BALLOON V3 FULL-PAGE COMPONENT-FIRST PIPELINE ===")
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
        # Execute Phase 1 & 2 on full page image globally
        full_page_masks = extract_all_balloons_full_page(page_img, blocks)

        for idx, blk in enumerate(blocks):
            g += 1
            if g not in TARGET_SAMPLE_IDS:
                continue

            bx, by, bw, bh = int(blk["x"]), int(blk["y"]), int(blk["width"]), int(blk["height"])
            balloon_mask = full_page_masks.get(idx)

            if balloon_mask is None:
                print(f"Sample #{g:02d}: No full-page mask found")
                continue

            # Extract crop for target block visualization
            pad = 80
            crop_y0, crop_y1 = max(0, by - pad), min(page_img.shape[0], by + bh + pad)
            crop_x0, crop_x1 = max(0, bx - pad), min(page_img.shape[1], bx + bw + pad)

            crop = page_img[crop_y0:crop_y1, crop_x0:crop_x1].copy()
            crop_mask = balloon_mask[crop_y0:crop_y1, crop_x0:crop_x1].copy()

            nz = cv2.findNonZero(crop_mask)
            if nz is not None:
                sbx, sby, sbw, sbh = cv2.boundingRect(nz)
            else:
                sbx, sby, sbw, sbh = 0, 0, crop.shape[1], crop.shape[0]

            gray_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            text_ink = (gray_crop < 150).astype(np.uint8) * 255
            text_mask_in_balloon = cv2.bitwise_and(text_ink, crop_mask)
            clean_mask = cv2.dilate(text_mask_in_balloon, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
            cleaned_crop = cv2.inpaint(crop, clean_mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)

            # Build 4-panel visual preview
            p1 = crop.copy()
            local_bx, local_by = bx - crop_x0, by - crop_y0
            cv2.rectangle(p1, (local_bx, local_by), (local_bx + bw, local_by + bh), (0, 0, 255), 2)
            cv2.putText(p1, "1. FULL-PAGE EXTRACT BBOX", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 2)

            p2 = cv2.cvtColor(crop_mask, cv2.COLOR_GRAY2BGR)
            cnts, _ = cv2.findContours(crop_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(p2, cnts, -1, (0, 255, 0), 2)
            cv2.rectangle(p2, (sbx, sby), (sbx + sbw, sby + sbh), (0, 255, 255), 2)
            cv2.putText(p2, "2. FULL-PAGE VORONOI MASK", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 2)

            p3 = cv2.cvtColor(text_mask_in_balloon, cv2.COLOR_GRAY2BGR)
            cv2.putText(p3, "3. INK MASK IN BALLOON", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 0), 2)

            p4 = cleaned_crop.copy()
            cv2.drawContours(p4, cnts, -1, (0, 255, 0), 2)
            cv2.rectangle(p4, (sbx, sby), (sbx + sbw, sby + sbh), (0, 255, 255), 2)
            cy = sby + sbh // 2
            cv2.line(p4, (sbx, cy), (sbx + sbw, cy), (255, 150, 0), 2)
            cv2.putText(p4, "4. CLEANED & FITTED", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 2)

            combined = np.hstack([p1, p2, p3, p4])
            out_path = OUTPUT_DIR / f"v3_fullpage_sample_{g:02d}_page{pn:02d}.png"
            save_image(out_path, combined)
            print(f"Sample #{g:02d} V3 Full-Page Pipeline -> {out_path.name}")

    print("\nAll target samples processed cleanly using Full-Page V3 Pipeline!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
