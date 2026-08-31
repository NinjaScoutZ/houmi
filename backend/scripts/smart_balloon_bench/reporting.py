"""Report generation: JSON results, Markdown summary, and preview overlays."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np

from app.utils.image_utils import cv2_imread_unicode, cv2_imwrite_unicode

from .metrics import aggregate_rows

COLOR_GT = (0, 0, 255)
COLOR_SAFE = (0, 255, 0)
COLOR_BBOX = (255, 160, 0)


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def write_results_json(rows: list[dict[str, Any]], aggregates: dict[str, Any], out_path: Path) -> None:
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(),
        "row_count": len(rows),
        "aggregates": aggregates,
        "rows": rows,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def render_markdown_report(
    rows: list[dict[str, Any]],
    aggregates: dict[str, Any],
    engines: list[str],
    meta: dict[str, Any],
) -> str:
    lines: list[str] = []
    lines.append("# Smart Balloon Benchmark Report")
    lines.append("")
    lines.append(f"- generated_at_utc: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- git_commit: {git_commit()}")
    for key, val in meta.items():
        lines.append(f"- {key}: {val}")
    lines.append("")

    overall = aggregates.get("overall", {})
    lines.append(f"Total rows: {overall.get('n', 0)}")
    lines.append("")

    lines.append(_engine_table(aggregates, engines))

    type_groups: dict[str, list[str]] = {}
    arch_groups: dict[str, list[str]] = {}
    split_groups: dict[str, list[str]] = {}
    per_engine = aggregates.get("engines", {})
    for engine, subs in per_engine.items():
        for sub in subs:
            if sub.startswith("balloon_type:"):
                type_groups.setdefault(sub.split(":", 1)[1], []).append(engine)
            elif sub.startswith("archetype:"):
                arch_groups.setdefault(sub.split(":", 1)[1], []).append(engine)
            elif sub.startswith("split:"):
                split_groups.setdefault(sub.split(":", 1)[1], []).append(engine)

    if len(type_groups) > 1 or any(len(v) > 0 for v in type_groups.values()):
        lines.append("## Per balloon_type")
        lines.append("")
        lines.append("| balloon_type | " + " | ".join(engines) + " |")
        lines.append("|---|" + "---|" * len(engines))
        for t in sorted(type_groups):
            cells = []
            for e in engines:
                st = per_engine.get(e, {}).get(f"balloon_type:{t}", {})
                cells.append(_compact_stat(st))
            lines.append(f"| {t} | " + " | ".join(cells) + " |")
        lines.append("")

    lines.append("## Per detected archetype")
    lines.append("")
    lines.append("| archetype | " + " | ".join(engines) + " |")
    lines.append("|---|" + "---|" * len(engines))
    all_archs = sorted(arch_groups.keys())
    for a in all_archs:
        cells = []
        for e in engines:
            st = per_engine.get(e, {}).get(f"archetype:{a}", {})
            cells.append(_compact_stat(st))
        lines.append(f"| {a} | " + " | ".join(cells) + " |")
    lines.append("")

    lines.append("## Worst records (lowest IoU)")
    lines.append("")
    scored = [r for r in rows if r.get("has_gt") and r.get("metrics")]
    worst = sorted(scored, key=lambda r: r["metrics"]["mask_iou"])[:10]
    lines.append("| record_id | engine | iou | containment | util | method |")
    lines.append("|---|---|---|---|---|---|")
    for r in worst:
        m = r["metrics"]
        lines.append(
            f"| {r['record_id']} | {r['engine']} | {_fmt(m['mask_iou'])} "
            f"| {_fmt(m['containment'])} | {_fmt(m['utilization'])} | {r.get('method', '')} |"
        )
    lines.append("")
    return "\n".join(lines)


def _engine_table(aggregates: dict[str, Any], engines: list[str]) -> str:
    header = (
        "| engine | n | success | iou_mean | iou_median | precision | utilization "
        "| containment | p50_ms | p95_ms | top fallback |"
    )
    sep = "|---|" + "---|" * 10
    lines = [header, sep]
    per_engine = aggregates.get("engines", {})
    for e in engines:
        st = per_engine.get(e, {}).get("all", {})
        fallbacks = st.get("fallback_reasons") or {}
        top_fallback = max(fallbacks.items(), key=lambda kv: kv[1])[0] if fallbacks else "-"
        lines.append(
            f"| {e} | {st.get('n', 0)} | {_fmt(st.get('success_rate'))} "
            f"| {_fmt(st.get('iou_mean'))} | {_fmt(st.get('iou_median'))} "
            f"| {_fmt(st.get('precision_mean'))} | {_fmt(st.get('utilization_mean'))} "
            f"| {_fmt(st.get('containment_mean'))} | {_fmt(st.get('runtime_p50_ms'), 1)} "
            f"| {_fmt(st.get('runtime_p95_ms'), 1)} | {top_fallback} |"
        )
    return "\n".join(lines)


def _compact_stat(st: dict[str, Any]) -> str:
    return f"n={st.get('n', 0)} iou={_fmt(st.get('iou_mean'))}"


def save_preview(
    image_path: str,
    row: dict[str, Any],
    out_path: Path,
    context_pad: int = 120,
) -> bool:
    """Render one overlay preview: GT red (if mask known), safe polygon green, bbox orange."""
    payload = row.get("preview_payload") or {}
    shape = payload.get("image_shape")
    if not shape:
        return False

    img = cv2_imread_unicode(image_path)
    if img is None:
        return False

    bbox = payload.get("text_bbox") or {}
    bx, by = int(float(bbox.get("x", 0))), int(float(bbox.get("y", 0)))
    bw, bh = int(float(bbox.get("width", 0))), int(float(bbox.get("height", 0)))
    x0, y0 = max(0, bx - context_pad), max(0, by - context_pad)
    x1, y1 = min(img.shape[1], bx + bw + context_pad), min(img.shape[0], by + bh + context_pad)

    canvas = img[y0:y1, x0:x1].copy()
    cv2.rectangle(canvas, (bx - x0, by - y0), (bx + bw - x0, by + bh - y0), COLOR_BBOX, 2)

    gt_mask_path = row.get("_gt_mask_path")
    if gt_mask_path:
        gt = cv2_imread_unicode(str(gt_mask_path), flags=cv2.IMREAD_GRAYSCALE)
        if gt is not None and gt.shape[:2] == img.shape[:2]:
            cnts, _ = cv2.findContours((gt > 127).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(canvas, [c - np.array([x0, y0]) for c in cnts], -1, COLOR_GT, 2)

    safe_poly = payload.get("safe_polygon") or []
    if len(safe_poly) >= 3:
        pts = (np.asarray(safe_poly, dtype=np.int32) - np.array([x0, y0])).reshape(-1, 1, 2)
        cv2.polylines(canvas, [pts], True, COLOR_SAFE, 2)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    return bool(cv2_imwrite_unicode(str(out_path), canvas))


def summarize_counts(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = {"total": 0, "success": 0, "scored": 0}
    for r in rows:
        counts["total"] += 1
        if r.get("success"):
            counts["success"] += 1
        if r.get("has_gt"):
            counts["scored"] += 1
    return counts


def build_aggregates(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return aggregate_rows(rows)
