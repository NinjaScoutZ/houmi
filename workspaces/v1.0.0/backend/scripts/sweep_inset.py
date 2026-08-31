#!/usr/bin/env python3
"""Sweep smart balloon inset_ratio against GT masks.

Runs the V15 engine once per record, then re-applies apply_contour_inset on
the raw contour at several ratios and scores each against the ground-truth
interior mask. Reports aggregates overall and for audit-HIGH records only.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import cv2
import numpy as np

from app.services.smart_balloon import apply_contour_inset, process_smart_balloon_v15
from smart_balloon_bench.engines import load_gt_mask
from smart_balloon_bench.manifest import load_manifest
from smart_balloon_bench.metrics import compute_pair_metrics


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(BASE_DIR.parent / "datasets" / "smart_balloon_bench" / "manifest.jsonl"))
    parser.add_argument("--audit", default=str(BASE_DIR.parent / "datasets" / "smart_balloon_bench" / "gt_audit.json"))
    parser.add_argument("--insets", default="0.05,0.075,0.10,0.125,0.15")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    insets = [float(v) for v in args.insets.split(",")]
    audit_path = Path(args.audit)
    tiers = {}
    if audit_path.exists():
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        tiers = {r["record_id"]: r["tier"] for r in audit["results"]}

    records = [r for r in load_manifest(args.manifest) if r.gt_mask_path]
    if args.limit:
        records = records[: args.limit]

    per_inset = defaultdict(lambda: defaultdict(list))
    per_inset_high = defaultdict(lambda: defaultdict(list))

    for i, rec in enumerate(records, 1):
        from app.utils.image_utils import cv2_imread_unicode

        image = cv2_imread_unicode(rec.image_path)
        gt = load_gt_mask(rec.gt_mask_path, image.shape[:2]) if image is not None else None
        if image is None or gt is None:
            continue

        res = process_smart_balloon_v15(
            image,
            dict(rec.text_bbox),
            rival_boxes=rec.rival_boxes or None,
            inset_ratio=0.10,
        )
        if not res.get("success") or not res.get("raw_contour_points"):
            continue

        raw = np.asarray(res["raw_contour_points"], dtype=np.float32).reshape(-1, 1, 2)
        for ratio in insets:
            safe = apply_contour_inset(raw, inset_ratio=ratio)
            pts = safe.reshape(-1, 2).astype(np.int32)
            m = compute_pair_metrics(gt, pts, margin_px=8)
            for k, v in m.items():
                per_inset[ratio][k].append(v)
            if tiers.get(rec.record_id) == "HIGH":
                for k, v in m.items():
                    per_inset_high[ratio][k].append(v)

        if i % 50 == 0:
            print(f"[{i}/{len(records)}]")

    print("")
    print(f"{'inset':>7} | {'ALL n':>5} {'iou':>6} {'prec':>6} {'util':>6} {'cont':>6} | {'HIGH n':>6} {'iou':>6} {'prec':>6} {'util':>6} {'cont':>6}")
    for ratio in insets:
        def agg(store, key):
            vals = store[ratio][key]
            return sum(vals) / len(vals) if vals else 0.0
        n_all = len(per_inset[ratio]["mask_iou"])
        n_high = len(per_inset_high[ratio]["mask_iou"])
        print(
            f"{ratio:>7.3f} | {n_all:>5d} {agg(per_inset,'mask_iou'):>6.3f} "
            f"{agg(per_inset,'precision'):>6.3f} {agg(per_inset,'utilization'):>6.3f} {agg(per_inset,'containment'):>6.3f} "
            f"| {n_high:>6d} {agg(per_inset_high,'mask_iou'):>6.3f} "
            f"{agg(per_inset_high,'precision'):>6.3f} {agg(per_inset_high,'utilization'):>6.3f} {agg(per_inset_high,'containment'):>6.3f}"
        )

    out = {
        str(r): {k: sum(v) / len(v) for k, v in per_inset[r].items()} for r in insets if per_inset[r]["iou"]
    }
    out_path = BASE_DIR.parent / "data" / "benchmarks" / "smart_balloon" / "inset_sweep.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"\nsaved: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
