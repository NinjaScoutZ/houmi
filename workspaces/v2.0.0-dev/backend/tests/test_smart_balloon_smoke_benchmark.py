"""Smoke benchmark: run the mask benchmark on a few GT records inside pytest.

Guards the Smart Balloon production path against silent regressions.
Skips gracefully when the GT manifest or SAM models are unavailable, so CI
machines without local data still pass.
"""

import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = BASE_DIR / "scripts"
for p in (str(BASE_DIR), str(SCRIPTS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from smart_balloon_bench.manifest import load_manifest  # noqa: E402

MANIFEST = BASE_DIR.parent / "datasets" / "smart_balloon_bench" / "manifest.jsonl"
SMOKE_N = 6


def _gt_records():
    if not MANIFEST.exists():
        pytest.skip("GT manifest not found")
    records = [r for r in load_manifest(MANIFEST) if r.gt_mask_path]
    if not records:
        pytest.skip("no GT records in manifest")
    return records[:SMOKE_N]


class TestSmartBalloonSmokeBenchmark:
    def test_v15_smoke_on_gt_records(self):
        from smart_balloon_bench.engines import run_record

        records = _gt_records()
        rows = [run_record(r, "v15") for r in records]
        assert len(rows) == len(records)
        successes = [r for r in rows if r["success"]]
        assert successes, "V15 failed on every smoke record"
        scored = [r for r in successes if r.get("has_gt")]
        for r in scored:
            assert r["metrics"]["mask_iou"] >= 0.0
        elapsed = [r["elapsed_ms"] for r in rows]
        assert max(elapsed) < 10_000, f"V15 smoke latency exploded: {elapsed}"

    def test_prod_smoke_on_gt_records(self):
        pytest.importorskip("onnxruntime")
        from app.config import SAM_ENCODER_PATH, SAM_DECODER_PATH

        if not (SAM_ENCODER_PATH.exists() and SAM_DECODER_PATH.exists()):
            pytest.skip("SAM models not installed")

        from smart_balloon_bench.engines import run_record

        records = _gt_records()
        rows = [run_record(r, "prod") for r in records]
        assert len(rows) == len(records)
        successes = [r for r in rows if r["success"]]
        assert len(successes) >= len(records) - 1, (
            f"prod path failed on too many smoke records: {[r['fallback_reason'] for r in rows]}"
        )
        for r in successes:
            if r.get("has_gt"):
                assert r["metrics"]["precision"] > 0.0
