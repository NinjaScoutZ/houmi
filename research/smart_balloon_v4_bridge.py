"""Smart Balloon V4: Isotropic Distance-Transform Body Estimation & Bridge-Aware Connection.

Located and executed exclusively inside e:\\houmi\\research\\

Key Advancements:
1. 2D Isotropic Distance Transform: Body(M, alpha) = {p in M : D(p) >= alpha * max(D)}
   Eliminates bridge overshoot across ANY direction (horizontal, diagonal, vertical).
2. Neck Point & Bridge Endpoint Detection:
   Identifies the narrowest isthmus and the true connection point leading to the partner balloon.
3. Convex Regularized Body Bounds:
   Constrains typesetting bounding box strictly to the balloon body sphere without stretching into the bridge.
"""

from __future__ import annotations

import json
import math
import os
import sys
import cv2
import numpy as np
from pathlib import Path
from skimage.morphology import skeletonize

RESEARCH_DIR = Path(r"e:\houmi\research")
PROJECT_350_DIR = Path(r"E:\Chapter Download\Kuaikanmanhua\ลิขิตตัวร้าย\350")
OUTPUT_DIR = RESEARCH_DIR / "smart_balloon_previews_v4_bridge"
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


def extract_body_by_distance(mask: np.ndarray, alpha: float = 0.28) -> np.ndarray:
    """Extract regularized core body using 2D isotropic distance transform."""
    dist = cv2.distanceTransform((mask > 0).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    if dist.max() == 0:
        return mask.copy()
    
    threshold = alpha * dist.max()
    body_seed = (dist >= threshold).astype(np.uint8) * 255
    
    # Smooth body contour and close small holes
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    body_mask = cv2.morphologyEx(body_seed, cv2.MORPH_CLOSE, kernel)
    
    # Keep largest connected component (main body)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(body_mask, connectivity=8)
    if n > 1:
        largest_idx = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
        body_mask = (labels == largest_idx).astype(np.uint8) * 255
        
    return body_mask


def find_neck_and_endpoint(mask: np.ndarray, body_mask: np.ndarray) -> tuple[tuple[int, int] | None, tuple[int, int] | None]:
    """Find the narrowest neck isthmus and the farthest bridge endpoint."""
    bridge_mask = mask.copy()
    bridge_mask[body_mask > 0] = 0
    
    if not bridge_mask.any():
        return None, None
        
    skel = skeletonize(mask > 0).astype(np.uint8)
    dist = cv2.distanceTransform((mask > 0).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    
    bridge_skel = skel & ~(body_mask > 0)
    ys, xs = np.where(bridge_skel > 0)
    
    neck_pt = None
    if len(xs) > 0:
        widths = dist[ys, xs]
        neck_idx = np.argmin(widths)
        neck_pt = (int(xs[neck_idx]), int(ys[neck_idx]))
        
    # Farthest bridge pixel from body centroid = true connection point
    M = cv2.moments(body_mask)
    if M["m00"] == 0:
        return neck_pt, None
    cx = int(M["m10"] / M["m00"])
    cy = int(M["m01"] / M["m00"])
    
    bys, bxs = np.where(bridge_mask > 0)
    if len(bxs) == 0:
        return neck_pt, None
        
    dists = np.hypot(bxs - cx, bys - cy)
    tip_idx = np.argmax(dists)
    endpoint = (int(bxs[tip_idx]), int(bys[tip_idx]))
    
    return neck_pt, endpoint


def process_v4_bridge_sample(page_img: np.ndarray, text_blocks: list[dict], target_idx: int) -> dict:
    """Execute V4 Isotropic Body & Bridge-Aware pipeline."""
    h, w = page_img.shape[:2]
    blk = text_blocks[target_idx]
    bx, by, bw, bh = int(blk["x"]), int(blk["y"]), int(blk["width"]), int(blk["height"])
    
    # 1. Full-page dominant white detection
    gray = cv2.cvtColor(page_img, cv2.COLOR_BGR2GRAY)
    white_sel = (gray >= 195).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13))
    white_sel = cv2.morphologyEx(white_sel, cv2.MORPH_CLOSE, kernel)
    
    # 2. Extract adaptive region for this block
    pad = max(bw, bh) + 80
    crop_x0, crop_y0 = max(0, bx - pad), max(0, by - pad)
    crop_x1, crop_y1 = min(w, bx + bw + pad), min(h, by + bh + pad)
    
    crop = page_img[crop_y0:crop_y1, crop_x0:crop_x1].copy()
    crop_gray = gray[crop_y0:crop_y1, crop_x0:crop_x1].copy()
    crop_white = white_sel[crop_y0:crop_y1, crop_x0:crop_x1].copy()
    ch, cw = crop.shape[:2]
    
    # Local seed flood for balloon
    local_bx, local_by = bx - crop_x0, by - crop_y0
    seed_mask = np.zeros((ch + 2, cw + 2), dtype=np.uint8)
    cv2.floodFill(crop_white, seed_mask, (local_bx + bw // 2, local_by + bh // 2), 255, flags=8 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY)
    full_mask = seed_mask[1:-1, 1:-1] * 255
    
    # 3. Extract regularized body using 2D isotropic distance transform
    body_mask = extract_body_by_distance(full_mask, alpha=0.28)
    
    # 4. Detect neck and bridge endpoint
    neck_pt, endpoint = find_neck_and_endpoint(full_mask, body_mask)
    
    # 5. Regularize body bounding box and center
    nz_body = cv2.findNonZero(body_mask)
    if nz_body is not None:
        rbx, rby, rbw, rbh = cv2.boundingRect(nz_body)
    else:
        rbx, rby, rbw, rbh = local_bx, local_by, bw, bh
        
    # Text ink mask and cleaning
    text_ink = (crop_gray < 150).astype(np.uint8) * 255
    text_mask_in_balloon = cv2.bitwise_and(text_ink, full_mask)
    clean_mask = cv2.dilate(text_mask_in_balloon, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    cleaned_crop = cv2.inpaint(crop, clean_mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
    
    return {
        "crop": crop,
        "full_mask": full_mask,
        "body_mask": body_mask,
        "neck_pt": neck_pt,
        "endpoint": endpoint,
        "regularized_bbox": (rbx, rby, rbw, rbh),
        "init_bbox": (local_bx, local_by, bw, bh),
        "text_mask_in_balloon": text_mask_in_balloon,
        "cleaned_crop": cleaned_crop,
    }


def main():
    print("=== STARTING SMART BALLOON V4 BRIDGE-AWARE PROTOTYPE ===")
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

            res = process_v4_bridge_sample(page_img, blocks, idx)
            
            # Panel 1: Original Crop + Red Initial Bbox
            p1 = res["crop"].copy()
            ix, iy, iw, ih = res["init_bbox"]
            cv2.rectangle(p1, (ix, iy), (ix + iw, iy + ih), (0, 0, 255), 2)
            cv2.putText(p1, "1. INITIAL BBOX (Red)", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 2)
            
            # Panel 2: Full Mask + Bridge Detection (Red Bridge, Cyan Connection Point)
            p2 = cv2.cvtColor(res["full_mask"], cv2.COLOR_GRAY2BGR)
            # Highlight bridge in red
            bridge_vis = (res["full_mask"] > 0) & ~(res["body_mask"] > 0)
            p2[bridge_vis] = (0, 0, 220)  # Red bridge
            
            cnts_body, _ = cv2.findContours(res["body_mask"], cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(p2, cnts_body, -1, (0, 255, 0), 2)  # Green body
            
            if res["neck_pt"]:
                cv2.circle(p2, res["neck_pt"], 6, (0, 255, 255), -1)  # Yellow neck isthmus
            if res["endpoint"]:
                cv2.circle(p2, res["endpoint"], 8, (255, 255, 0), -1)  # Cyan connection endpoint
                cv2.putText(p2, "True Bridge Tip", (res["endpoint"][0] - 60, res["endpoint"][1] - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)
            cv2.putText(p2, "2. BRIDGE & TRUE CONNECTION TIP", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 2)
            
            # Panel 3: Regularized Body Bbox (Zero Bridge Overshoot)
            p3 = cv2.cvtColor(res["body_mask"], cv2.COLOR_GRAY2BGR)
            cv2.drawContours(p3, cnts_body, -1, (0, 255, 0), 2)
            rbx, rby, rbw, rbh = res["regularized_bbox"]
            cv2.rectangle(p3, (rbx, rby), (rbx + rbw, rby + rbh), (0, 255, 255), 2)  # Yellow regularized bbox
            cv2.putText(p3, "3. REGULARIZED BODY (NO OVERSHOOT)", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 2)
            
            # Panel 4: Cleaned Crop + True Center Line
            p4 = res["cleaned_crop"].copy()
            cv2.drawContours(p4, cnts_body, -1, (0, 255, 0), 2)
            cv2.rectangle(p4, (rbx, rby), (rbx + rbw, rby + rbh), (0, 255, 255), 2)
            cy = rby + rbh // 2
            cv2.line(p4, (rbx, cy), (rbx + rbw, cy), (255, 150, 0), 2)
            cv2.putText(p4, "4. CLEANED & TRUE CENTER", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 2)
            
            combined = np.hstack([p1, p2, p3, p4])
            out_path = OUTPUT_DIR / f"v4_bridge_sample_{g:02d}_page{pn:02d}.png"
            save_image(out_path, combined)
            print(f"Sample #{g:02d} V4 Bridge-Aware -> {out_path.name}")
            
    print("\nAll target samples processed using V4 Bridge-Aware Pipeline!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
