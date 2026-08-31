import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from app.services.typesetting.contour_fitting import (
    build_contour_width_profile,
    profile_for_block,
)
from app.services.typesetting.fitting import _line_allowed_width


class ContourFittingTests(unittest.TestCase):
    def test_profile_is_narrower_at_top_than_middle(self):
        mask = np.zeros((80, 140), dtype=np.uint8)
        cv2.ellipse(mask, (70, 40), (62, 34), 0, 0, 360, 255, -1)

        profile = build_contour_width_profile(mask, padding=2)
        self.assertIsNotNone(profile)
        assert profile is not None

        top = profile.allowed_width(0, 5, 12, 0, 140, 80)
        middle = profile.allowed_width(2, 5, 12, 0, 140, 80)
        self.assertGreater(middle, top)

    def test_provider_overrides_ellipse_width(self):
        provider = lambda *_args: 23.0
        self.assertEqual(
            _line_allowed_width(0, 1, 12, 0, 100, 60, "bubble", 0.88, 0.95, provider),
            23.0,
        )

    def test_profile_for_block_reads_page_space_mask(self):
        mask = np.zeros((100, 120), dtype=np.uint8)
        cv2.ellipse(mask, (60, 50), (42, 30), 0, 0, 360, 255, -1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mask.png"
            self.assertTrue(cv2.imwrite(str(path), mask))
            block = type("Block", (), {"smart_mask_path": str(path), "extra_metadata": {}})()
            profile = profile_for_block(
                block,
                {"x": 18, "y": 20, "width": 84, "height": 60},
                target_width=84,
                target_height=60,
            )
            self.assertIsNotNone(profile)

    def test_profile_for_block_discovers_legacy_mask_without_metadata(self):
        mask = np.zeros((80, 100), dtype=np.uint8)
        cv2.ellipse(mask, (50, 40), (38, 28), 0, 0, 360, 255, -1)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "page.png"
            mask_path = source.parent / "mask_legacy-1.png"
            self.assertTrue(cv2.imwrite(str(mask_path), mask))
            page = type(
                "Page",
                (),
                {"source_image_path": str(source), "page_number": 1, "project": None},
            )()
            block = type(
                "Block",
                (),
                {"id": "legacy-1", "page": page, "smart_mask_path": None, "extra_metadata": {}},
            )()
            profile = profile_for_block(
                block,
                {"x": 10, "y": 10, "width": 80, "height": 60},
                target_width=80,
                target_height=60,
            )
            self.assertIsNotNone(profile)


if __name__ == "__main__":
    unittest.main()
