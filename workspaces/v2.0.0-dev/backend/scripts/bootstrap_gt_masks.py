#!/usr/bin/env python3
"""Bootstrap ground-truth balloon masks using SAM 2.1 (independent of V15/V16).

For each manifest record the text bbox is used as a SAM box prompt over the
FULL PAGE image (encoder embedding cached per page, so multi-balloon pages
only pay encoding once). Candidate masks pass sanity gates before being
accepted as GT:

  - text bbox coverage >= --min-bbox-cover (text must sit inside the balloon)
  - mask area within [min-area-factor, max-area-factor] x text bbox area
  - largest connected component only, internal holes filled
  - eroded by --erode-px so the border stroke is excluded from the interior

Accepted masks are written to datasets/smart_balloon_bench/gt/<record_id>.png
and the manifest is rewritten with gt_mask_path filled in. A QC contact sheet
per record (crop + overlay) is saved under qc/ for human spot checks.

Usage:
  python backend/scripts/bootstrap_gt_masks.py \
      --manifest datasets/smart_balloon_bench/manifest.jsonl \
      --limit 60 --splits dev,test
"""

from __future__ import annotations

import argparse
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

from app.services.sam_segmenter import smart_segment_box
from app.utils.image_utils import cv2_imread_unicode, cv2_imwrite_unicode

from smart_balloon_bench.manifest import BenchRecord, load_manifest, save_manifest


def _clean_candidate(mask: np.ndarray) -> np.ndarray | None:
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


def _passes_gates(
    mask: np.ndarray,
    bbox: dict[str, float],
    min_bbox_cover: float,
    min_area_factor: float,
    max_area_factor: float,
) -> tuple[bool, str]:
    tb_x0, tb_y0 = int(bbox["x"]), int(bbox["y"])
    tb_x1 = int(bbox["x"] + bbox["width"])
    tb_y1 = int(bbox["y"] + bbox["height"])
    h, w = mask.shape[:2]
    tb_x0, tb_y0 = max(0, tb_x0), max(0, tb_y0)
    tb_x1, tb_y1 = min(w, tb_x1), min(h, tb_y1)
    roi = mask[tb_y0:tb_y1, tb_x0:tb_x1]
    roi_area = max(1, roi.size)

    cover = float(np.count_nonzero(roi)) / roi_area
    if cover < min_bbox_cover:
        return False, f"bbox_cover_{cover:.2f}"

    mask_area = cv2.countNonZero(mask)
    bbox_area = float(bbox["width"]) * float(bbox["height"])
    ratio = mask_area / max(1.0, bbox_area)
    if ratio < min_area_factor:
        return False, f"area_too_small_ratio_{ratio:.2f}"
    if ratio > max_area_factor:
        return False, f"area_too_large_ratio_{ratio:.2f}"
    return True, f"cover_{cover:.2f}_ratio_{ratio:.2f}"


def _save_qc_sheet(
    image: np.ndarray,
    record: BenchRecord,
    gt_mask: np.ndarray,
    out_path: Path,
    pad: int = 140,
) -> None:
    bbox = record.text_bbox
    bx, by = int(bbox["x"]), int(bbox["y"])
    bw, bh = int(bbox["width"]), int(bbox["height"])
    x0, y0 = max(0, bx - pad), max(0, by - pad)
    x1, y1 = min(image.shape[1], bx + bw + pad), min(image.shape[0], by + bh + pad)

    canvas = image[y0:y1, x0:x1].copy()
    cnts, _ = cv2.findContours((gt_mask > 127).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    shifted = [c - np.array([x0, y0]) for c in cnts]
    canvas = canvas.copy()
    if shifted:
        overlay = canvas.copy()
        cv2.fillPoly(overlay, shifted, (180, 120, 255))
        canvas = cv2.addWeighted(overlay, 0.35, canvas, 0.65, 0)
        cv2.drawContours(canvas, shifted, -1, (0, 0, 255), 2)
    cv2.rectangle(canvas, (bx - x0, by - y0), (bx + bw - x0, by + bh - y0), (255, 160, 0), 2)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2_imwrite_unicode(str(out_path), canvas)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap GT masks via SAM 2.1")
    parser.add_argument("--manifest", default=str(BASE_DIR.parent / "datasets" / "smart_balloon_bench" / "manifest.jsonl"))
    parser.add_argument("--gt-dir", default=str(BASE_DIR.parent / "datasets" / "smart_balloon_bench" / "gt"))
    parser.add_argument("--qc-dir", default=str(BASE_DIR.parent / "datasets" / "smart_balloon_bench" / "qc"))
    parser.add_argument("--splits", default="dev,test")
    parser.add_argument("--types", default=None, help="comma list of balloon_type filters")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--per-project", type=int, default=None,
                        help="cap records per project and round-robin across projects for diversity")
    parser.add_argument("--min-bbox-cover", type=float, default=0.85)
    parser.add_argument("--min-area-factor", type=float, default=1.15)
    parser.add_argument("--max-area-factor", type=float, default=30.0)
    parser.add_argument("--erode-px", type=int, default=3)
    parser.add_argument("--skip-existing", action="store_true")
    args = parser.parse_args(argv)

    records = load_manifest(args.manifest)
    wanted_splits = {s.strip() for s in args.splits.split(",")} if args.splits else None
    wanted_types = {t.strip() for t in args.types.split(",")} if args.types else None

    targets = []
    for r in records:
        if wanted_splits and r.split not in wanted_splits:
            continue
        if wanted_types and r.balloon_type not in wanted_types:
            continue
        if args.skip_existing and r.gt_mask_path:
            continue
        targets.append(r)
    if args.per_project:
        by_project: dict[str, list[BenchRecord]] = {}
        for r in targets:
            by_project.setdefault(r.project_id, []).append(r)
        capped: list[BenchRecord] = []
        cursors = {pid: 0 for pid in by_project}
        while len(capped) < len(targets):
            progressed = False
            for pid in sorted(by_project):
                lst = by_project[pid]
                if cursors[pid] < min(args.per_project, len(lst)):
                    capped.append(lst[cursors[pid]])
                    cursors[pid] += 1
                    progressed = True
            if not progressed:
                break
        targets = capped
    if args.limit:
        targets = targets[: args.limit]

    gt_dir = Path(args.gt_dir)
    qc_dir = Path(args.qc_dir)
    gt_dir.mkdir(parents=True, exist_ok=True)

    accepted, rejected = [], Counter()
    page_cache: dict[str, np.ndarray] = {}

    def get_page(path: str) -> np.ndarray | None:
        key = str(Path(path))
        img = page_cache.get(key)
        if img is None:
            img = cv2_imread_unicode(key)
            if img is not None:
                if len(page_cache) > 4:
                    page_cache.clear()
                page_cache[key] = img
        return img

    updated_records: dict[str, BenchRecord] = {}
    for i, rec in enumerate(targets, 1):
        image = get_page(rec.image_path)
        if image is None:
            rejected["image_unreadable"] += 1
            print(f"[{i}/{len(targets)}] {rec.record_id}: SKIP image unreadable")
            continue

        bbox = rec.text_bbox
        x0 = max(0, int(bbox["x"]))
        y0 = max(0, int(bbox["y"]))
        x1 = min(image.shape[1], int(bbox["x"] + bbox["width"]))
        y1 = min(image.shape[0], int(bbox["y"] + bbox["height"]))
        if x1 - x0 < 8 or y1 - y0 < 8:
            rejected["bbox_too_small"] += 1
            continue

        raw = smart_segment_box(image, x0, y0, x1, y1)
        if raw is None:
            rejected["sam_unavailable"] += 1
            print("SAM unavailable - aborting (models missing?)")
            return 3

        cleaned = _clean_candidate(raw)
        if cleaned is None:
            rejected["no_component"] += 1
            print(f"[{i}/{len(targets)}] {rec.record_id}: REJECT no_component")
            continue

        ok, reason = _passes_gates(cleaned, bbox, args.min_bbox_cover, args.min_area_factor, args.max_area_factor)
        if not ok:
            rejected[reason.split("_r")[0]] += 1
            print(f"[{i}/{len(targets)}] {rec.record_id}: REJECT {reason}")
            continue

        k = max(3, args.erode_px * 2 + 1)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        interior = cv2.erode(cleaned, kernel)
        if cv2.countNonZero(interior) == 0:
            rejected["eroded_to_empty"] += 1
            print(f"[{i}/{len(targets)}] {rec.record_id}: REJECT eroded_to_empty")
            continue

        out_png = gt_dir / f"{rec.record_id}.png"
        cv2_imwrite_unicode(str(out_png), interior)
        rec.gt_mask_path = str(out_png)
        updated_records[rec.record_id] = rec
        accepted.append(rec.record_id)
        _save_qc_sheet(image, rec, interior, qc_dir / f"{rec.record_id}.png")
        print(f"[{i}/{len(targets)}] {rec.record_id}: OK ({reason})")

    if updated_records:
        for r in records:
            if r.record_id in updated_records:
                r.gt_mask_path = updated_records[r.record_id].gt_mask_path
        save_manifest(records, args.manifest)

    print("")
    print(f"GT bootstrap done: accepted={len(accepted)} rejected={sum(rejected.values())}")
    for reason, n in rejected.most_common():
        print(f"  reject {reason}: {n}")
    print(f"masks : {gt_dir}")
    print(f"qc    : {qc_dir}")
    print(f"manifest updated: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
