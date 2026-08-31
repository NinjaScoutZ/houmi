import unittest

from app.services.detector import class_aware_nms


class DetectorPostprocessingTests(unittest.TestCase):
    def test_overlapping_predictions_keep_strongest_geometry_without_union_growth(self):
        strongest = {
            "x": 120.0,
            "y": 140.0,
            "width": 560.0,
            "height": 304.0,
            "confidence": 0.93,
            "detection_class": "text",
        }
        shifted_duplicate = {
            "x": 95.0,
            "y": 80.0,
            "width": 620.0,
            "height": 430.0,
            "confidence": 0.71,
            "detection_class": "text",
        }

        result = class_aware_nms([shifted_duplicate, strongest], 0.50)

        self.assertEqual(result, [strongest])
        self.assertEqual(result[0]["height"], 304.0)

    def test_overlapping_text_and_balloon_predictions_are_not_merged(self):
        text = {
            "x": 120.0,
            "y": 140.0,
            "width": 560.0,
            "height": 304.0,
            "confidence": 0.93,
            "detection_class": "text",
        }
        balloon = {
            "x": 90.0,
            "y": 70.0,
            "width": 640.0,
            "height": 450.0,
            "confidence": 0.89,
            "detection_class": "bubble",
        }

        result = class_aware_nms([text, balloon], 0.50)

        self.assertEqual(len(result), 2)
        self.assertEqual({box["detection_class"] for box in result}, {"text", "bubble"})

    def test_nested_single_line_prediction_is_suppressed_without_growing_parent(self):
        multi_line = {
            "x": 158.0,
            "y": 5310.0,
            "width": 512.0,
            "height": 312.0,
            "confidence": 0.94,
            "detection_class": "text",
        }
        nested_line = {
            "x": 171.0,
            "y": 5312.0,
            "width": 481.0,
            "height": 72.0,
            "confidence": 0.44,
            "detection_class": "text",
        }

        result = class_aware_nms([nested_line, multi_line], 0.50)

        self.assertEqual(result, [multi_line])

    def test_disabled_smart_balloon_preserves_original_bounding_box_without_modification(self):
        from app.config import get_enable_smart_balloon
        from app.services.layout_region import analyze_layout_region

        # 1. Verify config returns False when enable_smart_balloon is disabled in settings
        settings = {"enable_smart_balloon": False}
        self.assertFalse(get_enable_smart_balloon(settings))

        # 2. Verify analyze_layout_region preserves exact original bbox
        original_block = {
            "x": 100.0,
            "y": 500.0,
            "width": 745.0,
            "height": 379.0,
            "balloon_type": "bubble",
        }
        region = analyze_layout_region(None, original_block)

        self.assertEqual(region["x"], 100.0)
        self.assertEqual(region["y"], 500.0)
        self.assertEqual(region["width"], 745.0)
        self.assertEqual(region["height"], 379.0)

    def test_balloon_detector_cancels_early_when_requested(self):
        from app.services.detector import BalloonDetector
        detector = BalloonDetector()
        
        # Test cancel check callback returning True causes early exit
        cancelled = detector.detect("dummy_path.png", cancel_check=lambda: True)
        self.assertEqual(cancelled, [])


if __name__ == "__main__":
    unittest.main()


