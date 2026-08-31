import unittest
from unittest.mock import patch

import cv2
import numpy as np

from app.services.text_mask import (
    detect_colored_text_lines,
    detect_text_lines,
    generate_high_quality_text_mask,
    high_quality_text_mask_allowed,
    refine_detected_text_mask,
)


class TestHighQualityTextMask(unittest.TestCase):
    def test_safe_paddle_result_does_not_run_color_rescue(self):
        image = np.full((90, 240, 3), (120, 70, 30), dtype=np.uint8)
        cv2.putText(image, "TEXT", (25, 62), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 3, cv2.LINE_AA)

        class Predictor:
            def predict(self, _image):
                return [{
                    "dt_polys": np.array([[[16, 15], [190, 15], [190, 72], [16, 72]]], dtype=np.int32),
                    "dt_scores": np.array([0.93], dtype=np.float32),
                }]

        with patch(
            "app.services.text_mask.detect_colored_text_lines",
            side_effect=AssertionError("Color Rescue must not run after a safe Paddle result"),
        ):
            mask, regions, warnings = generate_high_quality_text_mask(
                image,
                dilation_kernel=2,
                predictor=Predictor(),
            )

        self.assertGreater(np.count_nonzero(mask), 0)
        self.assertEqual([region["source"] for region in regions], ["paddle"])
        self.assertEqual(warnings, [])

    def test_only_allows_the_expensive_detector_for_high_performance_profiles(self):
        self.assertFalse(high_quality_text_mask_allowed({"performance_profile": "eco"}))
        self.assertFalse(high_quality_text_mask_allowed({"performance_profile": "balanced"}))
        self.assertTrue(high_quality_text_mask_allowed({"performance_profile": "performance"}))
        self.assertFalse(high_quality_text_mask_allowed({
            "performance_profile": "custom",
            "performance_custom": {"prefer_gpu": True, "ocr_workers": 2},
        }))
        self.assertTrue(high_quality_text_mask_allowed({
            "performance_profile": "custom",
            "performance_custom": {"prefer_gpu": True, "ocr_workers": 3},
        }))

    def test_reads_real_line_polygons_from_paddle_style_prediction(self):
        class Predictor:
            def predict(self, _image):
                return [{
                    "rec_polys": [
                        [[10, 10], [90, 10], [90, 30], [10, 30]],
                        [[10, 42], [80, 42], [80, 60], [10, 60]],
                    ],
                    "rec_scores": [0.99, 0.95],
                }]

        detections = detect_text_lines(np.zeros((80, 120, 3), dtype=np.uint8), predictor=Predictor())

        self.assertEqual(len(detections), 2)
        self.assertEqual(detections[0].as_response()["height"], 21)
        self.assertAlmostEqual(detections[1].confidence or 0, 0.95)

    def test_reads_detector_only_numpy_predictions(self):
        class Predictor:
            def predict(self, _image):
                return [{
                    "dt_polys": np.array([
                        [[4, 5], [110, 5], [110, 28], [4, 28]],
                        [[3, 35], [116, 35], [116, 62], [3, 62]],
                    ], dtype=np.int32),
                    "dt_scores": np.array([0.91, 0.94], dtype=np.float32),
                }]

        detections = detect_text_lines(np.zeros((70, 120, 3), dtype=np.uint8), predictor=Predictor())

        self.assertEqual(len(detections), 2)
        self.assertAlmostEqual(detections[0].confidence or 0, 0.91, places=4)
        self.assertAlmostEqual(detections[1].confidence or 0, 0.94, places=4)

    def test_refinement_keeps_light_text_without_selecting_the_whole_textured_panel(self):
        rng = np.random.default_rng(42)
        image = np.full((100, 240, 3), (155, 92, 38), dtype=np.uint8)
        noise = rng.integers(-18, 19, image.shape, dtype=np.int16)
        image = np.clip(image.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        expected_text = np.zeros((100, 240), dtype=np.uint8)
        cv2.putText(image, "SYSTEM", (22, 64), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (250, 250, 250), 2, cv2.LINE_AA)
        cv2.putText(expected_text, "SYSTEM", (22, 64), cv2.FONT_HERSHEY_SIMPLEX, 1.2, 255, 2, cv2.LINE_AA)
        detections = detect_text_lines(image, predictor=type("Predictor", (), {
            "predict": lambda _self, _image: [{"rec_polys": [[[16, 22], [188, 22], [188, 72], [16, 72]]]}]
        })())

        mask, regions, warnings = refine_detected_text_mask(image, detections, dilation_kernel=2)
        overlap = np.count_nonzero(cv2.bitwise_and(mask, expected_text))

        self.assertEqual(len(regions), 1)
        self.assertLess(np.count_nonzero(mask), image.shape[0] * image.shape[1] * 0.30)
        self.assertGreater(overlap, np.count_nonzero(expected_text) * 0.55)
        self.assertEqual(warnings, [])

    def test_color_ink_pass_finds_multicolour_system_text_on_a_textured_panel(self):
        rng = np.random.default_rng(9)
        image = np.full((140, 300, 3), (156, 96, 38), dtype=np.uint8)
        image = np.clip(image.astype(np.int16) + rng.integers(-20, 21, image.shape, dtype=np.int16), 0, 255).astype(np.uint8)
        expected = np.zeros((140, 300), dtype=np.uint8)
        cv2.putText(image, "SYSTEM", (16, 58), cv2.FONT_HERSHEY_SIMPLEX, 1.15, (20, 185, 255), 2, cv2.LINE_AA)
        cv2.putText(image, "ALERT", (42, 116), cv2.FONT_HERSHEY_SIMPLEX, 1.15, (216, 72, 205), 2, cv2.LINE_AA)
        cv2.putText(expected, "SYSTEM", (16, 58), cv2.FONT_HERSHEY_SIMPLEX, 1.15, 255, 2, cv2.LINE_AA)
        cv2.putText(expected, "ALERT", (42, 116), cv2.FONT_HERSHEY_SIMPLEX, 1.15, 255, 2, cv2.LINE_AA)

        seed, detections = detect_colored_text_lines(image)
        overlap = np.count_nonzero(cv2.bitwise_and(seed, expected))

        self.assertGreaterEqual(len(detections), 2)
        self.assertTrue(all(detection.source == "color" for detection in detections))
        self.assertGreater(overlap, np.count_nonzero(expected) * 0.55)
        self.assertLess(np.count_nonzero(seed), image.shape[0] * image.shape[1] * 0.35)

    def test_color_ink_quality_gate_uses_seed_before_kernel_expansion(self):
        image = np.full((80, 220, 3), (142, 86, 34), dtype=np.uint8)
        seed = np.zeros((80, 220), dtype=np.uint8)
        cv2.putText(seed, "SYSTEM", (8, 57), cv2.FONT_HERSHEY_SIMPLEX, 1.25, 255, 7, cv2.LINE_AA)
        detection = type("Detection", (), {
            "polygon": np.array([[4, 10], [216, 10], [216, 70], [4, 70]], dtype=np.float32),
            "source": "color",
            "as_response": lambda _self: {"source": "color"},
        })()

        mask, regions, warnings = refine_detected_text_mask(
            image,
            [detection],
            dilation_kernel=5,
            color_seed=seed,
        )

    def test_contour_morphology_mask_generates_isolated_text_strokes(self):
        from app.services.text_mask import generate_contour_morphology_text_mask
        image = np.full((120, 300, 3), 255, dtype=np.uint8)
        # Black comic balloon text on white background
        cv2.putText(image, "HOUMI TEST", (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 3, cv2.LINE_AA)
        mask = generate_contour_morphology_text_mask(image, dilation_kernel=2)
        self.assertIsNotNone(mask)
        self.assertGreater(np.count_nonzero(mask), 50)
        self.assertLess(np.count_nonzero(mask), image.shape[0] * image.shape[1] * 0.50)

    def test_imagetrans_mask_generates_crisp_binarized_mask(self):
        from app.services.text_mask import generate_imagetrans_text_mask
        image = np.full((120, 300, 3), 255, dtype=np.uint8)
        cv2.putText(image, "MANGA", (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (10, 10, 10), 3, cv2.LINE_AA)
        mask = generate_imagetrans_text_mask(image, dilation_kernel=2)
        self.assertIsNotNone(mask)
        self.assertGreater(np.count_nonzero(mask), 50)

    def test_inpainter_dispatch_respects_all_configured_methods(self):
        from app.services.inpainter import get_configured_block_mask
        image = np.full((200, 300, 3), 255, dtype=np.uint8)
        cv2.putText(image, "SAMPLE", (40, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2, cv2.LINE_AA)

        # 1. Full Bounding Box
        box_mask = get_configured_block_mask(image, 20, 20, 200, 150, {"mask_gen_method": "balloon"})
        self.assertGreater(np.count_nonzero(box_mask), 1000)

        # 2. Contour Morphology
        contour_mask = get_configured_block_mask(image, 20, 20, 200, 150, {"mask_gen_method": "contour", "mask_dilation_kernel": 2})
        self.assertIsNotNone(contour_mask)
        self.assertGreater(np.count_nonzero(contour_mask), 10)

        # 3. ImageTrans
        it_mask = get_configured_block_mask(image, 20, 20, 200, 150, {"mask_gen_method": "imagetrans", "mask_dilation_kernel": 2})
        self.assertIsNotNone(it_mask)
        self.assertGreater(np.count_nonzero(it_mask), 10)


if __name__ == "__main__":
    unittest.main()
