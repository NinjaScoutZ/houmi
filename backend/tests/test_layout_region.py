import unittest

import cv2
import numpy as np

from app.services.layout_region import (
    _resolve_shared_layout_regions,
    analyze_layout_region,
    migrate_project_translation_layout_policy,
    refresh_block_layout_regions,
)
from app.models.all_models import Page, Project, TextBlock
from app.services.typesetting import compute_block_signature, compute_block_typesetting


class LayoutRegionTests(unittest.TestCase):
    def test_returns_text_bbox_passthrough(self):
        image = np.full((400, 400, 3), 45, dtype=np.uint8)
        cv2.ellipse(image, (200, 200), (135, 105), 0, 0, 360, (250, 250, 250), -1)
        cv2.ellipse(image, (200, 200), (135, 105), 0, 0, 360, (10, 10, 10), 4)
        cv2.putText(image, "ABC", (155, 210), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (15, 15, 15), 3)
        block = {
            "x": 145.0,
            "y": 165.0,
            "width": 110.0,
            "height": 60.0,
            "balloon_type": "bubble",
        }

        region = analyze_layout_region(image, block)

        self.assertEqual(region["source"], "fallback_bbox")
        self.assertEqual(region["x"], block["x"])
        self.assertEqual(region["y"], block["y"])
        self.assertEqual(region["width"], block["width"])
        self.assertEqual(region["height"], block["height"])

    def test_rejects_white_page_background_as_balloon(self):
        image = np.full((300, 300, 3), 255, dtype=np.uint8)
        cv2.putText(image, "ABC", (110, 160), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
        block = {
            "x": 100.0,
            "y": 120.0,
            "width": 100.0,
            "height": 60.0,
            "balloon_type": "bubble",
        }

        region = analyze_layout_region(image, block)

        self.assertEqual(region["source"], "fallback_bbox")
        self.assertEqual(region["x"], block["x"])
        self.assertEqual(region["width"], block["width"])

    def test_typesetting_uses_layout_region_and_emits_quality_gate(self):
        block = TextBlock(
            id="layout-test",
            page_id="page-test",
            block_index=0,
            x=100,
            y=100,
            width=80,
            height=40,
            source_text="原文",
            translation="ข้อความแปลสำหรับจัดวางให้อยู่ตรงกลางบอลลูน",
            font_family="Tahoma",
            font_size=28,
            balloon_type="bubble",
            extra_metadata={
                "layout_region": {
                    "x": 60,
                    "y": 70,
                    "width": 180,
                    "height": 110,
                    "shape": "bubble",
                    "confidence": 0.9,
                    "source": "balloon_interior",
                    "safe_margin": 5,
                }
            },
        )

        signature_before = compute_block_signature(block)
        spec = compute_block_typesetting(block)
        block.extra_metadata["layout_region"]["x"] = 65
        signature_after = compute_block_signature(block)

        self.assertEqual(spec.layout_region.width, 180)
        self.assertGreater(spec.metrics["candidate_count"], 1)
        self.assertIn(
            spec.metrics["quality_gate"]["status"],
            {"passed", "needs_review", "defaulted"},
        )
        self.assertNotEqual(signature_before, signature_after)

    def test_bulk_refresh_preserves_manual_layout_region(self):
        manual_region = {
            "x": 12,
            "y": 24,
            "width": 120,
            "height": 80,
            "shape": "bubble",
            "confidence": 1,
            "source": "manual",
            "safe_margin": 0,
        }
        block = TextBlock(
            id="manual-layout",
            page_id="page-test",
            block_index=0,
            x=0,
            y=0,
            width=40,
            height=20,
            extra_metadata={"layout_region": dict(manual_region)},
        )

        regions = refresh_block_layout_regions([block])

        self.assertEqual(regions[0], manual_region)
        self.assertEqual(block.extra_metadata["layout_region"], manual_region)

    def test_shared_detected_component_falls_back_to_independent_safe_boxes(self):
        blocks = [
            TextBlock(id="a", x=50, y=100, width=300, height=100, extra_metadata={}),
            TextBlock(id="b", x=220, y=240, width=300, height=120, extra_metadata={}),
        ]
        regions = [
            {"x": 20, "y": 60, "width": 520, "height": 340, "source": "balloon_interior", "confidence": .9},
            {"x": 180, "y": 180, "width": 380, "height": 220, "source": "balloon_interior", "confidence": .9},
        ]

        resolved = _resolve_shared_layout_regions(blocks, regions)

        self.assertEqual(resolved[0]["source"], "overlap_safe_bbox")
        self.assertEqual(resolved[1]["source"], "overlap_safe_bbox")
        self.assertLess(resolved[0]["height"], 100)
        self.assertLess(resolved[1]["width"], 300)

    def test_policy_migration_restores_saved_balloon_context(self):
        context = {
            "x": 40.0,
            "y": 50.0,
            "width": 220.0,
            "height": 140.0,
            "shape": "bubble",
            "confidence": 0.9,
            "source": "balloon_interior",
            "safe_margin": 5.0,
        }
        project = Project(name="legacy", settings={"lock_translation_to_detected_box": True})
        page = Page(
            project=project,
            page_number=1,
            width=500,
            height=500,
            source_image_path="missing.png",
        )
        block = TextBlock(
            page=page,
            block_index=0,
            x=100,
            y=100,
            width=80,
            height=40,
            source_text="原文",
            translation="คำแปล",
            font_family="Tahoma",
            font_size=24,
            extra_metadata={
                "layout_region": {
                    "x": 100.0,
                    "y": 100.0,
                    "width": 80.0,
                    "height": 40.0,
                    "shape": "bubble",
                    "confidence": 0.9,
                    "source": "locked_detector_box",
                    "safe_margin": 0.0,
                },
                "balloon_context_region": context,
            },
        )

        migrated = migrate_project_translation_layout_policy(project)

        self.assertEqual(migrated, 1)
        self.assertFalse(project.settings["lock_translation_to_detected_box"])
        self.assertEqual(project.settings["translation_layout_policy_version"], 2)
        self.assertEqual(block.extra_metadata["layout_region"], context)
        self.assertNotIn("balloon_context_region", block.extra_metadata)


if __name__ == "__main__":
    unittest.main()
