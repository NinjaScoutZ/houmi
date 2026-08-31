import unittest
from unittest.mock import patch

import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.all_models import Page, Project, TextBlock
from app.routes.pipeline import (
    _process_ocr_evidence_results,
    classify_ocr_text_evidence,
    run_detect,
)


class PipelineTextEvidenceTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.project = Project(name="evidence", source_lang="ko", target_lang="th")
        self.page = Page(
            project=self.project,
            page_number=1,
            width=1000,
            height=1500,
            source_image_path="source.png",
        )
        self.db.add(self.project)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _auto_block(self, index: int, source_text: str = "") -> TextBlock:
        block = TextBlock(
            page=self.page,
            block_index=index,
            x=10,
            y=10 + index * 100,
            width=200,
            height=80,
            source_text=source_text,
            confidence=0.99,
            extra_metadata={
                "layer_origin": "auto_detection",
                "detected_balloon_type": "bubble",
                "layout_region": {
                    "x": 5,
                    "y": 5 + index * 100,
                    "width": 220,
                    "height": 100,
                    "source": "balloon_interior",
                },
            },
        )
        self.db.add(block)
        self.db.flush()
        return block

    def test_classifier_rejects_empty_and_ellipsis_only(self):
        self.assertEqual(classify_ocr_text_evidence("", True), ("reject", "empty_ocr"))
        self.assertEqual(
            classify_ocr_text_evidence("…\n...", True),
            ("reject", "punctuation_only"),
        )
        self.assertEqual(
            classify_ocr_text_evidence("신문이라…", True),
            ("confirmed", "valid_text"),
        )
        self.assertEqual(
            classify_ocr_text_evidence("", False),
            ("needs_review", "ocr_failed"),
        )

    def test_gate_prunes_high_confidence_noise_but_keeps_ocr_failure(self):
        ellipsis = self._auto_block(0)
        failed = self._auto_block(1)
        valid = self._auto_block(2)

        summary = _process_ocr_evidence_results(
            [
                (ellipsis, "…", True),
                (failed, "", False),
                (valid, "신문이라", True),
            ],
            self.project,
            self.db,
        )
        self.db.flush()

        self.assertIsNone(self.db.get(TextBlock, ellipsis.id))
        self.assertIsNotNone(self.db.get(TextBlock, failed.id))
        self.assertEqual(failed.extra_metadata["text_evidence_state"], "needs_review")
        self.assertEqual(valid.source_text, "신문이라")
        self.assertEqual(valid.extra_metadata["text_evidence_state"], "confirmed")
        self.assertEqual(summary, {"updated": 1, "pruned": 1, "review": 1})

    def test_gate_never_prunes_existing_or_manually_adjusted_layer(self):
        existing = self._auto_block(0, source_text="기존 텍스트")
        manual = self._auto_block(1)
        manual.extra_metadata = {
            **manual.extra_metadata,
            "layout_region": {
                **manual.extra_metadata["layout_region"],
                "source": "manual",
            },
        }

        summary = _process_ocr_evidence_results(
            [(existing, "…", True), (manual, "…", True)],
            self.project,
            self.db,
        )
        self.db.flush()

        self.assertIsNotNone(self.db.get(TextBlock, existing.id))
        self.assertIsNotNone(self.db.get(TextBlock, manual.id))
        self.assertEqual(summary["pruned"], 0)

    @patch("app.routes.pipeline.run_ocr")
    @patch("app.routes.pipeline.apply_default_text_template")
    @patch("app.routes.pipeline.analyze_layout_region")
    @patch("app.routes.pipeline.cv2.imdecode")
    @patch("app.routes.pipeline.np.fromfile")
    @patch("app.routes.pipeline.balloon_detector.detect")
    def test_detect_runs_text_evidence_gate_before_returning(
        self,
        detect,
        fromfile,
        imdecode,
        analyze,
        apply_template,
        run_ocr_mock,
    ):
        detect.return_value = [{
            "x": 10,
            "y": 20,
            "width": 100,
            "height": 50,
            "rotation_deg": 0,
            "confidence": 0.9,
            "balloon_type": "bubble",
        }]
        fromfile.return_value = np.array([1], dtype=np.uint8)
        imdecode.return_value = np.zeros((10, 10, 3), dtype=np.uint8)
        analyze.return_value = {
            "x": 5,
            "y": 10,
            "width": 120,
            "height": 70,
            "shape": "bubble",
            "confidence": 0.8,
            "source": "balloon_interior",
            "safe_margin": 2,
        }
        run_ocr_mock.return_value = {
            "ocr_updated_blocks_count": 1,
            "pruned_blocks_count": 0,
            "review_blocks_count": 0,
        }

        result = run_detect(self.page.id, backend="glm", promote_with_ocr=True, db=self.db)

        block = self.db.query(TextBlock).one()
        self.assertEqual(block.extra_metadata["layer_origin"], "auto_detection")
        self.assertEqual(block.extra_metadata["text_evidence_state"], "pending")
        self.assertEqual(
            block.extra_metadata["text_bbox"],
            {"x": 10, "y": 20, "width": 100, "height": 50},
        )
        self.assertEqual(block.extra_metadata["detection_class"], "text")
        run_ocr_mock.assert_called_once_with(
            self.page.id,
            backend="glm",
            force=True,
            db=self.db,
        )
        self.assertEqual(result["promoted_blocks_count"], 1)

        # Re-running detection replaces the page candidates; it must not append
        # another copy of every block.
        run_detect(
            self.page.id,
            backend="glm",
            promote_with_ocr=False,
            db=self.db,
        )
        self.assertEqual(self.db.query(TextBlock).count(), 1)


if __name__ == "__main__":
    unittest.main()
