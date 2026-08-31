"""Manifest handling for the Smart Balloon benchmark harness.

A manifest is a JSONL file where each line is one benchmark record:
a single text block on a single page with its detector bbox, balloon type,
optional ground-truth interior mask, and a split assignment.

Splits are assigned deterministically per project (story) — never by random
page shuffle — so that pages of the same style never leak across splits
(see docs/reports/smart_balloon_research_v0.4.md).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator


@dataclass
class BenchRecord:
    record_id: str
    project_id: str
    page_id: str
    block_index: int
    image_path: str
    text_bbox: dict[str, float]
    balloon_type: str = "bubble"
    rival_boxes: list[dict[str, Any]] = field(default_factory=list)
    gt_mask_path: str | None = None
    split: str = "test"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BenchRecord":
        known = {
            "record_id", "project_id", "page_id", "block_index", "image_path",
            "text_bbox", "balloon_type", "rival_boxes", "gt_mask_path",
            "split", "notes",
        }
        return cls(**{k: v for k, v in payload.items() if k in known})


def assign_split(project_id: str, ratios: tuple[float, float, float] = (0.70, 0.15, 0.15)) -> str:
    """Deterministically map a project id onto train/dev/test via md5 hashing."""
    digest = hashlib.md5(project_id.encode("utf-8")).hexdigest()
    bucket = int(digest[:12], 16) / float(16 ** 12)
    train_r, dev_r = ratios[0], ratios[0] + ratios[1]
    if bucket < train_r:
        return "train"
    if bucket < dev_r:
        return "dev"
    return "test"


def save_manifest(records: Iterator[BenchRecord] | list[BenchRecord], path: Path | str) -> int:
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")
            count += 1
    return count


def load_manifest(path: Path | str) -> list[BenchRecord]:
    manifest_path = Path(path)
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")
    records: list[BenchRecord] = []
    with manifest_path.open("r", encoding="utf-8") as fh:
        for line_no, raw_line in enumerate(fh, 1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                records.append(BenchRecord.from_dict(json.loads(line)))
            except (json.JSONDecodeError, TypeError) as exc:
                raise ValueError(f"bad manifest record at line {line_no}: {exc}") from exc
    return records


def _resolve_page_image(
    balloons_file: Path,
    project_dir: Path,
    image_ref: str,
    page_id: str,
) -> Path | None:
    img_path = Path(image_ref)
    if not img_path.is_absolute():
        candidate = project_dir / image_ref
        if candidate.exists():
            return candidate
    if not img_path.exists():
        fallback = project_dir / page_id / img_path.name
        if fallback.exists():
            return fallback
        return None
    return img_path


def bootstrap_from_projects(
    data_dir: Path | str,
    output_manifest: Path | str,
    limit: int | None = None,
    include_types: set[str] | None = None,
    ratios: tuple[float, float, float] = (0.70, 0.15, 0.15),
) -> dict[str, Any]:
    """Build a manifest skeleton from data/projects/*/training/balloons.json.

    Every other balloon on the same page becomes a rival box so that conjoined
    balloon splitting is exercised the same way the production pipeline does.
    Ground-truth masks are absent at this stage; annotate them later and fill
    `gt_mask_path` (records without GT still yield timing/success metrics).
    """
    root = Path(data_dir)
    json_files = sorted(root.glob("*/training/balloons.json"))
    records: list[BenchRecord] = []
    projects_seen: set[str] = set()

    for jf in json_files:
        project_dir = jf.parent.parent
        try:
            content = json.loads(jf.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        project_id = content.get("project_id", project_dir.name)
        projects_seen.add(project_id)

        for pg in content.get("pages", []):
            image_ref = pg.get("image")
            balloons = pg.get("balloons") or []
            if not image_ref or not balloons:
                continue
            page_id = str(pg.get("page_id", ""))
            image_path = _resolve_page_image(jf, project_dir, image_ref, page_id)
            if image_path is None:
                continue

            valid_balloons = []
            for idx, b in enumerate(balloons):
                bbox = b.get("bbox") or []
                if len(bbox) < 4 or bbox[2] <= 0 or bbox[3] <= 0:
                    continue
                valid_balloons.append((idx, b))

            for pos, (idx, b) in enumerate(valid_balloons):
                bx, by, bw, bh = [float(v) for v in b["bbox"][:4]]
                btype = str(b.get("type", "bubble"))
                if include_types is not None and btype not in include_types:
                    continue
                rivals = [
                    {
                        "x": float(o["bbox"][0]),
                        "y": float(o["bbox"][1]),
                        "width": float(o["bbox"][2]),
                        "height": float(o["bbox"][3]),
                    }
                    for _, o in valid_balloons if o is not b
                ]
                records.append(BenchRecord(
                    record_id=f"{project_id[:12]}_{page_id}_b{idx:03d}",
                    project_id=project_id,
                    page_id=page_id,
                    block_index=idx,
                    image_path=str(image_path),
                    text_bbox={"x": bx, "y": by, "width": bw, "height": bh},
                    balloon_type=btype,
                    rival_boxes=rivals,
                    gt_mask_path=None,
                    split=assign_split(project_id, ratios),
                ))
                if limit is not None and len(records) >= limit:
                    save_manifest(records, output_manifest)
                    return {"records": len(records), "projects": len({r.project_id for r in records})}

    save_manifest(records, output_manifest)
    splits: dict[str, int] = {}
    types_count: dict[str, int] = {}
    for r in records:
        splits[r.split] = splits.get(r.split, 0) + 1
        types_count[r.balloon_type] = types_count.get(r.balloon_type, 0) + 1
    return {
        "records": len(records),
        "projects": len(projects_seen),
        "splits": splits,
        "types": types_count,
        "output": str(output_manifest),
    }
