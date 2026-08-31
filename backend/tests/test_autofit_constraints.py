import unittest
from app.services.renderer import find_fitting_font_size

class TestAutofitConstraints(unittest.TestCase):
    def test_bubble_vs_narrative_constraints(self):
        # A line of text that fits better in a rectangle (narrative) than an ellipse (bubble)
        text = "หากเป็นวิถีเซียนมนุษย์ธรรมดา"
        font_family = "Tahoma"
        
        # Bounding box dimensions
        width = 160.0
        height = 60.0
        
        # Test fitting as bubble
        _, bubble_size = find_fitting_font_size(
            text_val=text,
            font_name=font_family,
            bold=False,
            block_w=width,
            block_h=height,
            balloon_type="bubble"
        )
        
        # Test fitting as narrative
        _, narrative_size = find_fitting_font_size(
            text_val=text,
            font_name=font_family,
            bold=False,
            block_w=width,
            block_h=height,
            balloon_type="narrative"
        )
        
        # Because a narrative box uses a simple rectangle (safety margin 95%),
        # whereas a bubble uses an elliptical constraint (safety margin + curvature limits),
        # the narrative box should allow a larger font size for horizontal layouts.
        self.assertGreater(narrative_size, bubble_size, 
                           f"Expected narrative size ({narrative_size}) to be larger than bubble size ({bubble_size}) due to ellipse curvature constraints")

    def test_autofit_creates_at_most_one_fallback_warning(self):
        import logging
        logger = logging.getLogger("houmi-font-registry")
        with self.assertLogs(logger, level="WARNING") as log_ctx:
            find_fitting_font_size(
                text_val="ทดสอบ",
                font_name="SomeNonExistentFontName",
                bold=False,
                block_w=100,
                block_h=50,
                balloon_type="bubble"
            )
        # Verify that the fallback warning was logged exactly once (instead of once per binary search iteration)
        self.assertEqual(len(log_ctx.output), 1, f"Expected exactly 1 fallback warning, got {len(log_ctx.output)}")

if __name__ == "__main__":
    unittest.main()
