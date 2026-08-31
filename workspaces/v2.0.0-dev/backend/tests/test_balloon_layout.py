import unittest
from types import SimpleNamespace

import numpy as np

from app.services.balloon_layout import segment_balloon_layout


class BalloonLayoutTests(unittest.TestCase):
    def test_segment_derives_locked_inner_region_from_selected_balloon(self):
        image = np.full((100, 120, 3), 240, dtype=np.uint8)
        block = SimpleNamespace(balloon_type="bubble")

        def fake_segmenter(crop, x0, y0, x1, y1):
            mask = np.zeros(crop.shape[:2], dtype=np.uint8)
            mask[14:74, 16:94] = 255
            return mask

        region, mask, crop_bounds = segment_balloon_layout(
            image, (30, 25, 90, 70), block, segmenter=fake_segmenter
        )

        self.assertEqual(region["source"], "manual")
        self.assertEqual(region["method"], "sam2_balloon")
        self.assertTrue(region["locked"])
        self.assertGreater(region["width"], 20)
        self.assertGreater(region["height"], 20)
        self.assertGreater(region["x"], crop_bounds[0])
        self.assertGreater(region["y"], crop_bounds[1])
        self.assertGreater(np.count_nonzero(mask), 0)

    def test_segment_rejects_tiny_selection(self):
        image = np.full((40, 40, 3), 240, dtype=np.uint8)
        block = SimpleNamespace(balloon_type="bubble")
        with self.assertRaisesRegex(ValueError, "too small"):
            segment_balloon_layout(
                image, (10, 10, 14, 14), block, segmenter=lambda *_args: None
            )


if __name__ == "__main__":
    unittest.main()
