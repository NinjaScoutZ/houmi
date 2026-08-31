#!/usr/bin/env python3
"""Audit pseudo-GT confidence by cross-validating two independent SAM prompts.

For every record that already has a box-prompt GT mask, this script runs a
SECOND, independent SAM strategy — positive point prompts (center + 4 bbox
corners) on the full page — and compares the two masks.

Agreement tiers:
  iou >= 0.85  -> HIGH   (two strategies agree; treat as verified-by-agreement)
  0.70-0.85    -> MEDIUM
  iou <  0.70  -> LOW    (flagged for human review, QC sheet written)

Outputs:
  datasets/smart_balloon_bench/gt_audit.json   per-record results
  datasets/smart_balloon_bench/review/<id>.png overlay for LOW records
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import cv2
import numpy as np

from app.services.sam_segmenter import smart_segment_points
from app.utils.image_utils import cv2_imread_unicode, cv2_imwrite_unicode

from smart_balloon_bench.manifest import load_manifest


def clean_largest(mask: np.ndarray) -> np.ndarray | None:
    binary = (mask > 0).astype(np.uint8) * 255
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary)
    if num_labels <= 1:
        return None
    best = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    comp = (labels == best).astype(np.uint8) * 255
    cnts, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    solid = np.zeros_like(comp)
    cv2.drawContours(solid, cnts, -1, 255, -1)
    return solid


def mask_iou(a: np.ndarray, b: np.ndarray) -> float:
    inter = cv2.countNonZero(cv2.bitwise_and(a, b))
    union = cv2.countNonZero(cv2.bitwise_or(a, b))
    return inter / union if union else 0.0


def save_review_sheet(image, record, gt_mask, point_mask, out_path, pad=140):
    bbox = record.text_bbox
    bx, by = int(bbox["x"]), int(bbox["y"])
    bw, bh = int(bbox["width"]), int(bbox["height"])
    x0, y0 = max(0, bx - pad), max(0, by - pad)
    x1, y1 = min(image.shape[1], bx + bw + pad), min(image.shape[0], by + bh + pad)
    canvas = image[y0:y1, x0:x1].copy()

    def contours_of(m):
        c, _ = cv2.findContours((m > 127).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return [k - np.array([x0, y0]) for k in c]

    cv2.drawContours(canvas, contours_of(gt_mask), -1, (0, 0, 255), 3)
    cv2.drawContours(canvas, contours_of(point_mask), -1, (0, 255, 0), 1)
    cv2.rectangle(canvas, (bx - x0, by - y0), (bx + bw - x0, by + bh - y0), (255, 160, 0), 2)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2_imwrite_unicode(str(out_path), canvas)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(BASE_DIR.parent / "datasets" / "smart_balloon_bench" / "manifest.jsonl"))
    parser.add_argument("--out", default=str(BASE_DIR.parent / "datasets" / "smart_balloon_bench" / "gt_audit.json"))
    parser.add_argument("--review-dir", default=str(BASE_DIR.parent / "datasets" / "smart_balloon_bench" / "review"))
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    records = [r for r in load_manifest(args.manifest) if r.gt_mask_path]
    if args.limit:
        records = records[: args.limit]

    results = []
    tiers = Counter()
    review_dir = Path(args.review_dir)

    for i, rec in enumerate(records, 1):
        image = cv2_imread_unicode(rec.image_path)
        gt = cv2_imread_unicode(rec.gt_mask_path, flags=cv2.IMREAD_GRAYSCALE)
        if image is None or gt is None:
            tiers["unreadable"] += 1
            continue
        gt_bin = (gt > 127).astype(np.uint8) * 255

        bbox = rec.text_bbox
        bx, by = bbox["x"], bbox["y"]
        bw, bh = bbox["width"], bbox["height"]
        points = [
            (bx + bw / 2, by + bh / 2),
            (bx + bw * 0.25, by + bh * 0.25),
            (bx + bw * 0.75, by + bh * 0.25),
            (bx + bw * 0.25, by + bh * 0.75),
            (bx + bw * 0.75, by + bh * 0.75),
        ]
        raw = smart_segment_points(image, [(float(p[0]), float(p[1])) for p in points])
        pm = clean_largest(raw) if raw is not None else None
        if pm is None:
            iou = 0.0
        else:
            iou = mask_iou(gt_bin, pm)

        tier = "HIGH" if iou >= 0.85 else ("MEDIUM" if iou >= 0.70 else "LOW")
        tiers[tier] += 1
        if tier == "LOW":
            save_review_sheet(image, rec, gt_bin, pm if pm is not None else np.zeros_like(gt_bin), review_dir / f"{rec.record_id}.png")

        results.append({
            "record_id": rec.record_id,
            "project_id": rec.project_id,
            "split": rec.split,
            "iou_box_vs_points": round(iou, 4),
            "tier": tier,
        })
        if i % 25 == 0 or i == len(records):
            print(f"[{i}/{len(records)}] audited")

    summary = {
        "n": len(results),
        "tiers": dict(tiers),
        "high_confidence_share": round(tiers["HIGH"] / max(1, len(results)), 3),
        "results": results,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"audit done: {summary['n']} records | tiers={summary['tiers']} | high_share={summary['high_confidence_share']}")
    print(f"out: {args.out}")
    print(f"review queue: {review_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
