#!/usr/bin/env python3
"""Smart Balloon benchmark harness CLI.

Subcommands:
  bootstrap   Build a manifest skeleton from data/projects/*/training/balloons.json
  run         Execute engines over a manifest and emit JSON + Markdown reports

Examples:
  python backend/scripts/benchmark_smart_balloon.py bootstrap \
      --output datasets/smart_balloon_bench/manifest.jsonl

  python backend/scripts/benchmark_smart_balloon.py run \
      --manifest datasets/smart_balloon_bench/manifest.jsonl \
      --engines bbox,v15,v16 --previews 12
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from smart_balloon_bench.engines import ENGINE_NAMES, run_record
from smart_balloon_bench.manifest import bootstrap_from_projects, load_manifest
from smart_balloon_bench.reporting import (
    build_aggregates,
    render_markdown_report,
    save_preview,
    write_results_json,
)


def cmd_bootstrap(args: argparse.Namespace) -> int:
    summary = bootstrap_from_projects(
        data_dir=args.data_dir,
        output_manifest=args.output,
        limit=args.limit,
        include_types=set(args.types.split(",")) if args.types else None,
    )
    print("bootstrap complete")
    for key in ("records", "projects"):
        print(f"  {key}: {summary.get(key)}")
    if "splits" in summary:
        print(f"  splits: {summary['splits']}")
        print(f"  types: {summary['types']}")
    print(f"  output: {summary.get('output', args.output)}")
    print("next step: annotate gt masks (255 = interior) and set gt_mask_path per record")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    records = load_manifest(args.manifest)
    engines = [e.strip() for e in args.engines.split(",") if e.strip()]
    invalid = [e for e in engines if e not in ENGINE_NAMES]
    if invalid:
        print(f"unknown engines: {invalid}; available: {ENGINE_NAMES}", file=sys.stderr)
        return 2

    if args.splits:
        wanted = {s.strip() for s in args.splits.split(",")}
        records = [r for r in records if r.split in wanted]

    if args.gt_only:
        records = [r for r in records if r.gt_mask_path]

    if args.limit:
        records = records[: args.limit]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir) if args.out_dir else BASE_DIR.parent / "data" / "benchmarks" / "smart_balloon" / stamp

    total = len(records) * len(engines)
    rows = []
    started = time.perf_counter()
    for i, record in enumerate(records, 1):
        for engine in engines:
            row = run_record(
                record,
                engine,
                inset_ratio=args.inset_ratio,
                margin_px=args.margin_px,
            )
            rows.append(row)
            status = "ok" if row["success"] else f"fb:{row.get('fallback_reason')}"
            score = f" iou={row['metrics']['mask_iou']:.3f}" if row.get("has_gt") else ""
            print(f"[{i * len(engines):5d}/{total}] {record.record_id} {engine:4s} {status}{score} ({row['elapsed_ms']:.0f}ms)")
    elapsed = time.perf_counter() - started

    aggregates = build_aggregates(rows)

    results_path = out_dir / f"results_{stamp}.json"
    write_results_json(rows, aggregates, results_path)

    meta = {
        "manifest": str(args.manifest),
        "engines": engines,
        "records": len(records),
        "inset_ratio": args.inset_ratio,
        "margin_px": args.margin_px,
        "wall_time_sec": round(elapsed, 1),
    }
    report_path = out_dir / f"report_{stamp}.md"
    report_path.write_text(render_markdown_report(rows, aggregates, engines, meta), encoding="utf-8")

    if args.previews > 0:
        preview_dir = out_dir / "previews"
        saved = 0
        for row in rows:
            if saved >= args.previews:
                break
            rec = next((r for r in records if r.record_id == row["record_id"]), None)
            if rec is None:
                continue
            if save_preview(rec.image_path, row, preview_dir / f"{row['record_id']}__{row['engine']}.png"):
                saved += 1
        print(f"previews saved: {saved} -> {preview_dir}")

    scored = [r for r in rows if r.get("has_gt")]
    print("")
    print(f"run complete in {elapsed:.1f}s | rows={len(rows)} scored={len(scored)}")
    print(f"results : {results_path}")
    print(f"report  : {report_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smart Balloon benchmark harness")
    sub = parser.add_subparsers(dest="command", required=True)

    p_boot = sub.add_parser("bootstrap", help="build manifest from project training data")
    p_boot.add_argument("--data-dir", default=str(BASE_DIR.parent / "data" / "projects"))
    p_boot.add_argument("--output", default=str(BASE_DIR.parent / "datasets" / "smart_balloon_bench" / "manifest.jsonl"))
    p_boot.add_argument("--limit", type=int, default=None)
    p_boot.add_argument("--types", default=None, help="comma-separated balloon types to keep (default all)")
    p_boot.set_defaults(func=cmd_bootstrap)

    p_run = sub.add_parser("run", help="run engines over a manifest")
    p_run.add_argument("--manifest", required=True)
    p_run.add_argument("--out-dir", default=None)
    p_run.add_argument("--engines", default="bbox,v15,v16")
    p_run.add_argument("--splits", default=None, help="comma list e.g. dev,test (default all)")
    p_run.add_argument("--gt-only", action="store_true", help="only records that have a ground-truth mask")
    p_run.add_argument("--limit", type=int, default=None)
    p_run.add_argument("--inset-ratio", type=float, default=0.10)
    p_run.add_argument("--margin-px", type=int, default=8)
    p_run.add_argument("--previews", type=int, default=0)
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
