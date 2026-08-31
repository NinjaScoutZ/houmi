import unittest
import numpy as np
import cv2

from app.services.text_mask import (
    generate_monochrome_flat_text_mask,
    generate_high_quality_text_mask,
)
from app.services.inpainter import (
    _should_use_solid_fill,
    _detect_uniform_fill_color,
)


class TestThaiSpacingAndMaskFixes(unittest.TestCase):
    def test_black_box_mask_generation_not_empty(self):
        """Verify that a dark/black box with white text generates a non-empty text mask."""
        # Create a black box (300x150) with white text drawn in the center
        img = np.zeros((150, 300, 3), dtype=np.uint8)
        # Fill with dark background (value ~15)
        img[:] = (15, 15, 15)
        # Draw white text characters in the middle
        cv2.putText(img, "TEST DIALOGUE", (25, 85), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (240, 240, 240), 3)

        # 1. Test monochrome flat mask on dark box
        mask = generate_monochrome_flat_text_mask(img, dilation_kernel=2)
        non_zero = np.count_nonzero(mask)
        self.assertGreater(non_zero, 50, "Monochrome mask for dark box must not be empty")

        # 2. Test high quality text mask routing
        hq_mask, regions, warnings = generate_high_quality_text_mask(img, dilation_kernel=2)
        hq_non_zero = np.count_nonzero(hq_mask)
        self.assertGreater(hq_non_zero, 50, "High-quality mask for dark box must not be empty")

    def test_lama_inpaint_disables_solid_white_brush_bypass(self):
        """Verify that selecting LaMa / force_lama_inpaint disables flat solid white fill."""
        # Case 1: force_lama_inpaint is True -> must return False (no solid fill bypass)
        settings_lama_forced = {
            "force_lama_inpaint": True,
            "inpaint_engine": "LamaInpaint",
            "cleanup_pipeline_profile": "smart_lama",
        }
        self.assertFalse(_should_use_solid_fill(True, False, settings=settings_lama_forced))

        # Case 2: default_image_inpaint_method is LamaInpaint -> must return False
        settings_lama_default = {
            "default_image_inpaint_method": "LamaInpaint",
        }
        self.assertFalse(_should_use_solid_fill(True, False, settings=settings_lama_default))

        # Case 3: MAT / manga_cleaner -> must return False
        settings_mat = {
            "inpaint_engine": "mat",
        }
        self.assertFalse(_should_use_solid_fill(True, False, settings=settings_mat))

        # Case 4: Legacy Telea / OpenCV / Box strategy without LaMa -> returns True for process_by_text_areas
        settings_box = {
            "cleanup_mask_strategy": "box",
            "inpaint_engine": "telea",
            "force_lama_inpaint": False,
        }
        self.assertTrue(_should_use_solid_fill(True, False, settings=settings_box))

    def test_inpaint_region_merging(self):
        """Verify that nearby disconnected glyph mask pieces are merged into a single region."""
        from app.services.inpainter import _find_inpaint_regions, _merge_overlapping_regions
        
        # Create a blank mask with 5 separate text lines belonging to the same speech bubble
        mask = np.zeros((500, 500), dtype=np.uint8)
        # 5 lines vertically stacked close to each other (y = 100, 130, 160, 190, 220)
        for y in [100, 130, 160, 190, 220]:
            mask[y:y+15, 100:300] = 255

        regions = _find_inpaint_regions(mask)
        # Instead of 5 fragmented regions, they should be merged into 1 unified balloon region
        self.assertEqual(len(regions), 1)
        bx, by, bw, bh = regions[0]
        self.assertLessEqual(bx, 100)
        self.assertLessEqual(by, 100)
        self.assertGreaterEqual(bx + bw, 300)
        self.assertGreaterEqual(by + bh, 235)


if __name__ == "__main__":
    unittest.main()
