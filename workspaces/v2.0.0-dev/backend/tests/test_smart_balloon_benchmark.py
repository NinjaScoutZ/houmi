"""Unit tests for the Smart Balloon benchmark harness."""

import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = BASE_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from smart_balloon_bench.manifest import (
    BenchRecord,
    assign_split,
    bootstrap_from_projects,
    load_manifest,
    save_manifest,
)
from smart_balloon_bench.metrics import aggregate_rows, compute_pair_metrics, rasterize_polygon
from smart_balloon_bench.engines import run_record


class TestAssignSplit:
    def test_deterministic(self):
        assert assign_split("project-a") == assign_split("project-a")

    def test_valid_outputs(self):
        for pid in [f"proj-{i}" for i in range(50)]:
            assert assign_split(pid) in {"train", "dev", "test"}

    def test_coverage_across_buckets(self):
        splits = {assign_split(f"p{i}") for i in range(200)}
        assert splits == {"train", "dev", "test"}


class TestManifestRoundtrip:
    def test_save_and_load(self, tmp_path):
        records = [
            BenchRecord(
                record_id="abc_p1_b000",
                project_id="abc",
                page_id="p1",
                block_index=0,
                image_path="img.png",
                text_bbox={"x": 10.0, "y": 20.0, "width": 100.0, "height": 80.0},
                balloon_type="bubble",
                rival_boxes=[{"x": 0, "y": 0, "width": 5, "height": 5}],
                gt_mask_path=None,
                split="dev",
            ),
            BenchRecord(
                record_id="abc_p2_b001",
                project_id="abc",
                page_id="p2",
                block_index=1,
                image_path="img2.png",
                text_bbox={"x": 1, "y": 2, "width": 3, "height": 4},
            ),
        ]
        out = tmp_path / "manifest.jsonl"
        n = save_manifest(records, out)
        assert n == 2
        loaded = load_manifest(out)
        assert loaded[0].record_id == "abc_p1_b000"
        assert loaded[0].text_bbox["width"] == 100.0
        assert loaded[0].rival_boxes[0]["height"] == 5
        assert loaded[1].split == "test"

    def test_load_missing_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_manifest(tmp_path / "nope.jsonl")


class TestBootstrap:
    def _make_project(self, root: Path):
        proj = root / "myproj" / "training"
        proj.mkdir(parents=True)
        pages_dir = root / "myproj" / "pages"
        pages_dir.mkdir(parents=True)
        img = np.zeros((200, 300, 3), dtype=np.uint8)
        cv2.imwrite(str(pages_dir / "p01.png"), img)
        data = {
            "project_id": "myproj",
            "pages": [
                {
                    "page_id": "p01",
                    "image": str(pages_dir / "p01.png"),
                    "balloons": [
                        {"block_id": "b1", "bbox": [10, 10, 60, 40], "type": "bubble"},
                        {"block_id": "b2", "bbox": [120, 20, 70, 45], "type": "caption"},
                        {"block_id": "bad", "bbox": [], "type": "bubble"},
                    ],
                }
            ],
        }
        (proj / "balloons.json").write_text(json.dumps(data), encoding="utf-8")

    def test_bootstrap_builds_records_with_rivals(self, tmp_path):
        self._make_project(tmp_path)
        out = tmp_path / "manifest.jsonl"
        summary = bootstrap_from_projects(tmp_path, out)
        assert summary["records"] == 2
        records = load_manifest(out)
        by_id = {r.record_id: r for r in records}
        b1 = next(r for r in records if r.block_index == 0)
        assert len(b1.rival_boxes) == 1
        assert b1.rival_boxes[0]["width"] == 70.0
        assert Path(b1.image_path).exists()
        assert set(by_id) and all(r.split in {"train", "dev", "test"} for r in records)

    def test_bootstrap_respects_limit_and_types(self, tmp_path):
        self._make_project(tmp_path)
        out = tmp_path / "m.jsonl"
        summary = bootstrap_from_projects(tmp_path, out, include_types={"caption"})
        assert summary["records"] == 1
        rec = load_manifest(out)[0]
        assert rec.balloon_type == "caption"


def make_oval_page() -> tuple[np.ndarray, dict[str, float], np.ndarray]:
    img = np.full((400, 500, 3), 245, dtype=np.uint8)
    cv2.ellipse(img, (250, 200), (170, 120), 15, 0, 360, (30, 30, 30), 6)
    cv2.ellipse(img, (250, 200), (167, 117), 15, 0, 360, (255, 255, 255), -1)
    cv2.putText(img, "TEST", (210, 210), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (40, 40, 40), 3)

    gt = np.zeros((400, 500), dtype=np.uint8)
    cv2.ellipse(gt, (250, 200), (164, 114), 15, 0, 360, 255, -1)

    bbox = {"x": 130.0, "y": 110.0, "width": 240.0, "height": 180.0}
    return img, bbox, gt


class TestMetrics:
    def test_rasterize_and_pair_metrics_perfect_match(self):
        poly = [[25, 25], [75, 25], [75, 75], [25, 75]]
        mask = rasterize_polygon(poly, (120, 120))
        assert int(np.count_nonzero(mask)) == 51 * 51

        big = [[0, 0], [100, 0], [100, 100], [0, 100]]
        gt = rasterize_polygon(big, (120, 120))
        m = compute_pair_metrics(gt, poly, margin_px=4)
        assert m["precision"] == pytest.approx(1.0)
        assert m["containment"] == pytest.approx(1.0)

    def test_pair_metrics_shrunk_polygon_penalized(self):
        full = [[0, 0], [200, 0], [200, 200], [0, 200]]
        small = [[50, 50], [150, 50], [150, 150], [50, 150]]
        gt = rasterize_polygon(full, (220, 220))
        m = compute_pair_metrics(gt, small, margin_px=2)
        assert 0.0 < m["mask_iou"] < 1.0
        assert m["precision"] == pytest.approx(1.0)
        assert m["utilization"] < 0.5

    def test_empty_polygon_zeroes(self):
        gt = rasterize_polygon([[0, 0], [10, 0], [10, 10]], (20, 20))
        m = compute_pair_metrics(gt, [])
        assert m["mask_iou"] == 0.0


class TestAggregation:
    def test_aggregate_math(self):
        rows = []
        for i, engine in enumerate(["v15", "bbox"]):
            for j in range(4):
                rows.append({
                    "record_id": f"r{j}",
                    "engine": engine,
                    "balloon_type": "bubble",
                    "split": "test",
                    "success": j % 4 != 3,
                    "archetype": "SMOOTH_OVAL",
                    "fallback_reason": None if j % 4 != 3 else "contour_too_small",
                    "has_gt": j % 4 != 3,
                    "elapsed_ms": 10.0 + i + j,
                    "metrics": {"mask_iou": 0.5 + 0.1 * j, "precision": 0.9, "utilization": 0.7, "containment": 0.95} if j % 4 != 3 else None,
                })
        agg = aggregate_rows(rows)
        overall = agg["overall"]
        assert overall["n"] == 8
        v15 = agg["engines"]["v15"]["all"]
        assert v15["n"] == 4
        assert v15["success_rate"] == pytest.approx(0.75)
        assert v15["iou_mean"] == pytest.approx((0.5 + 0.6 + 0.7) / 3, abs=1e-3)
        assert v15["runtime_p95_ms"] >= v15["runtime_p50_ms"]
        assert v15["fallback_reasons"] == {"contour_too_small": 1}
        bbox = agg["engines"]["bbox"]["balloon_type:bubble"]
        assert bbox["n"] == 4


class TestRunRecordOnSynthetic:
    def test_v15_beats_bbox_baseline(self, tmp_path):
        img, bbox, gt = make_oval_page()
        img_path = tmp_path / "page.png"
        cv2.imwrite(str(img_path), img)
        gt_path = tmp_path / "gt.png"
        cv2.imwrite(str(gt_path), gt)

        record = BenchRecord(
            record_id="syn_001",
            project_id="syn",
            page_id="p01",
            block_index=0,
            image_path=str(img_path),
            text_bbox=bbox,
            balloon_type="bubble",
            rival_boxes=[],
            gt_mask_path=str(gt_path),
            split="dev",
        )

        row_v15 = run_record(record, "v15")
        row_bbox = run_record(record, "bbox")
        row_v16 = run_record(record, "v16")

        assert row_v15["success"] is True
        assert row_v15["has_gt"] is True
        assert row_v15["metrics"]["mask_iou"] > 0.55
        assert row_v15["metrics"]["containment"] > 0.90

        assert row_bbox["method"] == "baseline_text_bbox"
        assert row_bbox["metrics"]["mask_iou"] < row_v15["metrics"]["mask_iou"]

        assert row_v16["success"] is True
        assert row_v16["elapsed_ms"] >= 0.0

    def test_missing_image_row(self, tmp_path):
        record = BenchRecord(
            record_id="gone",
            project_id="g",
            page_id="p",
            block_index=0,
            image_path=str(tmp_path / "missing.png"),
            text_bbox={"x": 0, "y": 0, "width": 10, "height": 10},
        )
        row = run_record(record, "v15")
        assert row["success"] is False
        assert row["fallback_reason"] == "image_unreadable"

    def test_no_gt_still_times(self, tmp_path):
        img, bbox, _ = make_oval_page()
        img_path = tmp_path / "page.png"
        cv2.imwrite(str(img_path), img)
        record = BenchRecord(
            record_id="nogt",
            project_id="s",
            page_id="p",
            block_index=0,
            image_path=str(img_path),
            text_bbox=bbox,
            gt_mask_path=None,
        )
        row = run_record(record, "v15")
        assert row["success"] is True
        assert row["has_gt"] is False
        assert row["metrics"] is None
