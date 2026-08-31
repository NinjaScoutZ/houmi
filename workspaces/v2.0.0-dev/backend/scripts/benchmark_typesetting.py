#!/usr/bin/env python3
"""Typesetting-level benchmark: render real glyphs and measure containment.

For each GT record this script runs the production balloon engine, fits
synthetic test strings (Thai / Japanese / Chinese / English) with the real
`fit_text_to_smart_balloon_shape` pipeline, renders the resulting layout with
PIL, and measures the fraction of glyph pixels that land inside the
ground-truth balloon interior — the "glyph-alpha containment" metric from
smart_balloon_research_v0.4.md, which is closer to what users see than
polygon IoU.

Primary use: A/B inset_ratio configs on rendered pixels.

Usage:
  python backend/scripts/benchmark_typesetting.py --insets 0.10,0.075 --limit 120
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.services.detector import compute_smart_balloon_bounds
from app.services.smart_balloon_typesetting import fit_text_to_smart_balloon_shape
from app.services.typesetting.segmentation import segment_text
from app.utils.image_utils import cv2_imread_unicode

from smart_balloon_bench.engines import load_gt_mask
from smart_balloon_bench.manifest import load_manifest

FONT_PATHS = {
    "tha": "C:/Windows/Fonts/leelawad.ttf",
    "jpn": "C:/Windows/Fonts/msgothic.ttc",
    "zhs": "C:/Windows/Fonts/msyh.ttc",
    "eng": "C:/Windows/Fonts/arial.ttf",
}

TEST_STRINGS = {
    "tha": ["สวัสดีครับ", "นี่คือพลังที่แท้จริงของดาบเล่มนี้ต่างหาก"],
    "jpn": ["新しい太陽だ", "この気迫まさに王級ではないのか"],
    "zhs": ["圣耀降临", "这是一轮新的太阳将原来的太阳取而代之"],
    "eng": ["What?!", "This is the true power of this blade"],
}


def render_glyph_mask(
    page_w: int,
    page_h: int,
    layout: dict,
    font: ImageFont.FreeTypeFont,
) -> np.ndarray:
    """Render the fitted layout onto a page-size canvas, return glyph mask."""
    img = Image.new("L", (page_w, page_h), 255)
    draw = ImageDraw.Draw(img)
    lines = layout["explicit_lines"]
    cx = float(layout["center"]["x"])
    cy = float(layout["center"]["y"])
    size = float(layout["font_size"])
    lh = size * float(layout.get("line_height_ratio", 1.25))
    total_h = float(layout["total_height"])
    top = cy - total_h / 2.0
    for i, line in enumerate(lines):
        ly = top + (i + 0.5) * lh
        draw.text((cx, ly), line, font=font, fill=0, anchor="mm")
    arr = np.asarray(img)
    return (arr < 128).astype(np.uint8) * 255


def glyph_metrics(glyph: np.ndarray, gt: np.ndarray, margin_px: int = 8) -> dict | None:
    total = int(np.count_nonzero(glyph))
    if total == 0:
        return None
    inside = int(np.count_nonzero(cv2_bitwise_and(glyph, gt)))
    k = max(3, margin_px * 2 + 1)
    kernel = cv2_get_erode_kernel(k)
    gt_eroded = cv2_erode(gt, kernel)
    inside_eroded = int(np.count_nonzero(cv2_bitwise_and(glyph, gt_eroded)))
    return {
        "containment": round(inside / total, 4),
        "containment_margin": round(inside_eroded / total, 4),
        "overflow": int(inside < total),
        "glyph_px": total,
    }


def cv2_bitwise_and(a, b):
    import cv2

    return cv2.bitwise_and(a, b)


def cv2_erode(a, kernel):
    import cv2

    return cv2.erode(a, kernel)


def cv2_get_erode_kernel(k):
    import cv2

    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(BASE_DIR.parent / "datasets" / "smart_balloon_bench" / "manifest.jsonl"))
    parser.add_argument("--audit", default=str(BASE_DIR.parent / "datasets" / "smart_balloon_bench" / "gt_audit.json"))
    parser.add_argument("--insets", default="0.10,0.075")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--min-font", type=float, default=20.0)
    parser.add_argument("--out", default=str(BASE_DIR.parent / "data" / "benchmarks" / "smart_balloon" / "typeset_bench.json"))
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

    fonts = {}
    for key, path in FONT_PATHS.items():
        try:
            ImageFont.truetype(path, 24)
            fonts[key] = path
        except Exception:
            print(f"font missing for {key}: {path}")

    agg = defaultdict(lambda: defaultdict(list))
    rows = []
    t0 = time.perf_counter()

    for i, rec in enumerate(records, 1):
        image = cv2_imread_unicode(rec.image_path)
        if image is None:
            continue
        gt = load_gt_mask(rec.gt_mask_path, image.shape[:2])
        if gt is None:
            continue
        page_h, page_w = image.shape[:2]
        tier = tiers.get(rec.record_id, "NA")

        for inset in insets:
            try:
                res = compute_smart_balloon_bounds(
                    image,
                    {**dict(rec.text_bbox), "balloon_type": rec.balloon_type},
                    rival_boxes=rec.rival_boxes or None,
                    inset_ratio=inset,
                    settings={"smart_balloon_adaptive": False},
                )
            except Exception:
                res = {"success": False}
            if not res.get("success"):
                agg[inset]["engine_fail"].append(1)
                continue
            agg[inset]["engine_ok"].append(1)

            for script, texts in TEST_STRINGS.items():
                if script not in fonts:
                    continue
                for t_idx, text in enumerate(texts):
                    length_bucket = "short" if t_idx == 0 else "long"
                    try:
                        layout = fit_text_to_smart_balloon_shape(
                            block={"bbox": res.get("safe_bbox")},
                            sb=res,
                            tokens=segment_text(text),
                            font_path=fonts[script],
                        )
                    except Exception:
                        layout = None
                    if not layout or not layout.get("explicit_lines"):
                        agg[inset]["fit_fail"].append(1)
                        continue

                    try:
                        font = ImageFont.truetype(fonts[script], int(layout["font_size"]))
                    except Exception:
                        agg[inset]["font_fail"].append(1)
                        continue

                    glyph = render_glyph_mask(page_w, page_h, layout, font)
                    m = glyph_metrics(glyph, gt)
                    if m is None:
                        continue

                    m.update({
                        "record_id": rec.record_id,
                        "tier": tier,
                        "inset": inset,
                        "script": script,
                        "length": length_bucket,
                        "font_size": layout["font_size"],
                        "too_small": int(layout["font_size"] < args.min_font),
                        "n_lines": len(layout["explicit_lines"]),
                    })
                    rows.append(m)
                    g = agg[inset]
                    for k in ("containment", "containment_margin"):
                        g[k].append(m[k])
                    g["overflow"].append(m["overflow"])
                    g["too_small"].append(m["too_small"])
                    g["font_size"].append(m["font_size"])
                    key = f"{script}:{length_bucket}"
                    for k in ("containment", "overflow"):
                        g[f"{key}:{k}"].append(m[k])

        if i % 25 == 0 or i == len(records):
            print(f"[{i}/{len(records)}] elapsed {time.perf_counter() - t0:.0f}s")

    print("")
    header = (
        f"{'inset':>6} | {'cfgs':>5} {'contain':>7} {'cont+8px':>8} {'overflow':>8} "
        f"{'small':>5} {'font_px':>7} | per-script containment (short/long)"
    )
    print(header)
    for inset in insets:
        g = agg[inset]
        n = len(g["containment"])
        if n == 0:
            print(f"{inset:>6.3f} | no data")
            continue
        per_script = []
        for script in TEST_STRINGS:
            s = g.get(f"{script}:short:containment", [])
            l = g.get(f"{script}:long:containment", [])
            if s and l:
                per_script.append(f"{script} {sum(s)/len(s):.3f}/{sum(l)/len(l):.3f}")
        print(
            f"{inset:>6.3f} | {n:>5d} {sum(g['containment'])/n:>7.4f} "
            f"{sum(g['containment_margin'])/n:>8.4f} {sum(g['overflow'])/n:>8.4f} "
            f"{sum(g['too_small'])/n:>5.3f} {sum(g['font_size'])/n:>7.1f} | " + "  ".join(per_script)
        )

    out_payload = {
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "insets": insets,
        "records": len(records),
        "rows": rows,
        "summary": {
            str(inset): {
                k: (sum(v) / len(v) if v else None) for k, v in agg[inset].items()
            }
            for inset in insets
        },
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_payload, ensure_ascii=False), encoding="utf-8")
    print(f"saved: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
