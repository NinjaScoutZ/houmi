"""
Test Smart Balloon V16 Adaptive Enhancement.

Tests adaptive background handling for:
1. Gray backgrounds (non-white)
2. Gradient backgrounds
3. Weak balloon strokes
4. Protruding tails/spikes
"""

import numpy as np
import cv2
import pytest
from app.services.smart_balloon_adaptive import (
    estimate_local_background_stats,
    reinforce_weak_balloon_edges,
    multi_seed_adaptive_flood_fill,
    process_smart_balloon_v16_adaptive,
)


def create_test_image_gray_background():
    """Create test image with balloon on gray background (200, 200, 200)."""
    img = np.full((600, 800, 3), 200, dtype=np.uint8)  # Gray background

    # Draw white balloon with dark stroke
    center = (400, 300)
    axes = (120, 80)
    cv2.ellipse(img, center, axes, 0, 0, 360, (255, 255, 255), -1)
    cv2.ellipse(img, center, axes, 0, 0, 360, (0, 0, 0), 3)

    # Add text bbox inside
    text_bbox = {
        "x": 320,
        "y": 240,
        "width": 160,
        "height": 120,
    }

    return img, text_bbox


def create_test_image_gradient_background():
    """Create test image with balloon on gradient background."""
    img = np.zeros((600, 800, 3), dtype=np.uint8)

    # Gradient background (180 -> 220)
    for y in range(600):
        brightness = int(180 + (220 - 180) * (y / 600.0))
        img[y, :] = (brightness, brightness, brightness)

    # Draw white balloon
    center = (400, 300)
    axes = (100, 100)
    cv2.ellipse(img, center, axes, 0, 0, 360, (255, 255, 255), -1)
    cv2.ellipse(img, center, axes, 0, 0, 360, (50, 50, 50), 2)

    text_bbox = {
        "x": 330,
        "y": 230,
        "width": 140,
        "height": 140,
    }

    return img, text_bbox


def create_test_image_weak_strokes():
    """Create test image with balloon having weak (faint) boundary strokes."""
    img = np.full((600, 800, 3), 240, dtype=np.uint8)  # Very light gray background

    # Draw white balloon with WEAK gray stroke (not black)
    center = (400, 300)
    axes = (120, 90)
    cv2.ellipse(img, center, axes, 0, 0, 360, (255, 255, 255), -1)
    cv2.ellipse(img, center, axes, 0, 0, 360, (160, 160, 160), 2)  # Weak gray stroke

    text_bbox = {
        "x": 310,
        "y": 230,
        "width": 180,
        "height": 140,
    }

    return img, text_bbox


def create_test_image_protruding_tail():
    """Create balloon with protruding tail/spike outside text bbox."""
    img = np.full((600, 800, 3), 245, dtype=np.uint8)

    # Main balloon body
    center = (400, 280)
    axes = (100, 80)
    cv2.ellipse(img, center, axes, 0, 0, 360, (255, 255, 255), -1)
    cv2.ellipse(img, center, axes, 0, 0, 360, (0, 0, 0), 3)

    # Protruding tail pointing down (extends 100px below)
    tail_pts = np.array([
        [390, 360],
        [400, 480],  # Tail tip far below
        [410, 360],
    ], dtype=np.int32)
    cv2.fillPoly(img, [tail_pts], (255, 255, 255))
    cv2.polylines(img, [tail_pts], False, (0, 0, 0), 2)

    text_bbox = {
        "x": 330,
        "y": 220,
        "width": 140,
        "height": 120,
    }

    return img, text_bbox


class TestAdaptiveBackgroundStats:
    def test_white_background_detection(self):
        """Pure white background should return standard threshold."""
        img, bbox = create_test_image_gray_background()
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Manually set bright background
        img_white = np.full((600, 800), 245, dtype=np.uint8)
        local_bbox = {"x": 100, "y": 100, "width": 100, "height": 100}

        stats = estimate_local_background_stats(img_white, local_bbox)

        assert stats["bg_mean"] > 230, "Should detect bright background"
        assert stats["white_thresh"] >= 160, "White threshold should be reasonable"
        assert stats["lo_diff"] >= 25, "Should have reasonable tolerance"

    def test_gray_background_detection(self):
        """Gray background should return tighter threshold."""
        img, bbox = create_test_image_gray_background()
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Extract crop region
        pad = 50
        bx, by = int(bbox["x"]), int(bbox["y"])
        bw, bh = int(bbox["width"]), int(bbox["height"])
        sx0 = max(0, bx - pad)
        sy0 = max(0, by - pad)
        sx1 = min(800, bx + bw + pad)
        sy1 = min(600, by + bh + pad)
        crop = gray[sy0:sy1, sx0:sx1]

        local_bbox = {
            "x": bx - sx0,
            "y": by - sy0,
            "width": bw,
            "height": bh,
        }

        stats = estimate_local_background_stats(crop, local_bbox)

        # Gray background (200) should trigger tighter tolerance
        assert 180 <= stats["bg_mean"] <= 210, f"Should detect gray background, got {stats['bg_mean']}"
        assert stats["lo_diff"] <= 30, "Gray background should use tighter tolerance"
        assert stats["up_diff"] <= 30, "Gray background should use tighter tolerance"

    def test_gradient_background_detection(self):
        """Gradient background should be detected and handled."""
        img, bbox = create_test_image_gradient_background()
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        pad = 50
        bx, by = int(bbox["x"]), int(bbox["y"])
        bw, bh = int(bbox["width"]), int(bbox["height"])
        sx0 = max(0, bx - pad)
        sy0 = max(0, by - pad)
        sx1 = min(800, bx + bw + pad)
        sy1 = min(600, by + bh + pad)
        crop = gray[sy0:sy1, sx0:sx1]

        local_bbox = {
            "x": bx - sx0,
            "y": by - sy0,
            "width": bw,
            "height": bh,
        }

        stats = estimate_local_background_stats(crop, local_bbox)

        # Should detect gradient background mean
        assert 170 <= stats["bg_mean"] <= 220, "Should detect gradient background"
        assert stats["bg_std"] > 5, "Gradient should have some variance"


class TestWeakEdgeReinforcement:
    def test_reinforces_weak_strokes(self):
        """Weak gray strokes should be detected and reinforced."""
        img, bbox = create_test_image_weak_strokes()
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        pad = 50
        bx, by = int(bbox["x"]), int(bbox["y"])
        bw, bh = int(bbox["width"]), int(bbox["height"])
        sx0 = max(0, bx - pad)
        sy0 = max(0, by - pad)
        sx1 = min(800, bx + bw + pad)
        sy1 = min(600, by + bh + pad)
        crop = gray[sy0:sy1, sx0:sx1]

        local_bbox = {
            "x": bx - sx0,
            "y": by - sy0,
            "width": bw,
            "height": bh,
        }

        edge_barrier = reinforce_weak_balloon_edges(crop, local_bbox)

        # Should have detected edges around balloon
        edge_count = cv2.countNonZero(edge_barrier)
        assert edge_count > 500, "Should detect weak edges"


class TestMultiSeedFloodFill:
    def test_multi_seed_improves_coverage(self):
        """Multi-seed should achieve better coverage than single-seed."""
        img, bbox = create_test_image_gray_background()
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        pad = 50
        bx, by = int(bbox["x"]), int(bbox["y"])
        bw, bh = int(bbox["width"]), int(bbox["height"])
        sx0 = max(0, bx - pad)
        sy0 = max(0, by - pad)
        sx1 = min(800, bx + bw + pad)
        sy1 = min(600, by + bh + pad)
        crop = gray[sy0:sy1, sx0:sx1]

        local_bbox = {
            "x": bx - sx0,
            "y": by - sy0,
            "width": bw,
            "height": bh,
        }

        bg_stats = estimate_local_background_stats(crop, local_bbox)
        edge_barrier = reinforce_weak_balloon_edges(crop, local_bbox)

        result_mask = multi_seed_adaptive_flood_fill(crop, local_bbox, edge_barrier, bg_stats)

        # Should capture most of the balloon interior
        filled_area = cv2.countNonZero(result_mask)
        balloon_area = bw * bh
        coverage_ratio = filled_area / balloon_area

        assert coverage_ratio > 0.5, f"Should cover significant balloon area, got {coverage_ratio:.2f}"


class TestEndToEndV16:
    def test_gray_background_balloon(self):
        """End-to-end test on gray background."""
        img, bbox = create_test_image_gray_background()

        result = process_smart_balloon_v16_adaptive(img, bbox)

        assert result["success"], "Should successfully process gray background balloon"
        assert result["version"] == "v16_adaptive"
        assert "raw_bbox" in result
        assert "safe_bbox" in result
        assert "center" in result

        # Verify bounds are reasonable
        raw_bbox = result["raw_bbox"]
        assert 50 < raw_bbox["width"] < 300, "Raw width should be reasonable"
        assert 30 < raw_bbox["height"] < 200, "Raw height should be reasonable"

    def test_gradient_background_balloon(self):
        """End-to-end test on gradient background."""
        img, bbox = create_test_image_gradient_background()

        result = process_smart_balloon_v16_adaptive(img, bbox)

        assert result["success"], "Should successfully process gradient background balloon"
        assert result["bg_stats"]["bg_mean"] < 230, "Should detect non-white background"

    def test_weak_stroke_balloon(self):
        """End-to-end test on weak stroke balloon."""
        img, bbox = create_test_image_weak_strokes()

        result = process_smart_balloon_v16_adaptive(img, bbox)

        assert result["success"], "Should successfully process weak stroke balloon"

    def test_protruding_tail_balloon(self):
        """End-to-end test on balloon with protruding tail."""
        img, bbox = create_test_image_protruding_tail()

        result = process_smart_balloon_v16_adaptive(img, bbox)

        assert result["success"], "Should successfully process balloon with protruding tail"

        # Verify tail is captured (raw height should extend beyond text bbox)
        raw_bbox = result["raw_bbox"]
        assert raw_bbox["height"] > bbox["height"] * 1.2, "Should capture protruding tail"


class TestV16SchemaAlignment:
    REQUIRED_KEYS = {
        "success", "method", "version", "archetype",
        "smart_x", "smart_y", "smart_width", "smart_height",
        "raw_bbox", "safe_bbox", "center",
        "crop_mask", "crop_offset", "mask_area",
        "contour_points", "raw_contour_points",
        "row_width_constraints", "metadata",
    }

    def test_result_schema_matches_v15_contract(self):
        img, bbox = create_test_image_gray_background()

        result = process_smart_balloon_v16_adaptive(img, bbox)

        assert result["success"], "V16 should succeed on gray background balloon"
        missing = self.REQUIRED_KEYS - set(result.keys())
        assert not missing, f"Missing V15 contract keys: {missing}"
        assert result["method"] == "smart_balloon_v16_adaptive"
        assert result["archetype"] != "adaptive"
        assert result["archetype"] in {"SPIKY_FUZZY", "RECTANGULAR", "ANGULAR", "SMOOTH_OVAL"}
        assert isinstance(result["crop_mask"], np.ndarray)
        assert result["crop_mask"].ndim == 2
        assert result["mask_area"] > 0
        assert len(result["crop_offset"]) == 2
        assert len(result["raw_contour_points"]) >= 3
        assert len(result["contour_points"]) >= 3
        assert isinstance(result["row_width_constraints"], dict)
        assert result["row_width_constraints"].get("enabled") is True
        assert "confidence" in result["metadata"]
        assert "elapsed_sec" in result["metadata"]

    def test_smart_bounds_consistent_with_safe_bbox(self):
        img, bbox = create_test_image_gray_background()

        result = process_smart_balloon_v16_adaptive(img, bbox)

        safe_bbox = result["safe_bbox"]
        assert result["smart_x"] == pytest.approx(safe_bbox["x"])
        assert result["smart_y"] == pytest.approx(safe_bbox["y"])
        assert result["smart_width"] == pytest.approx(safe_bbox["width"])
        assert result["smart_height"] == pytest.approx(safe_bbox["height"])

    def _make_conjoined_scene(self):
        img = np.full((700, 900, 3), 245, dtype=np.uint8)

        union = np.zeros((700, 900), dtype=np.uint8)
        cv2.ellipse(union, (350, 300), (130, 95), 0, 0, 360, 255, -1)
        cv2.ellipse(union, (470, 340), (130, 95), 0, 0, 360, 255, -1)
        img[union > 0] = (255, 255, 255)

        cnts, _ = cv2.findContours(union, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        cv2.drawContours(img, cnts, -1, (0, 0, 0), 3)

        primary_bbox = {"x": 290, "y": 240, "width": 120, "height": 110}
        rival_bbox = {
            "x": 430,
            "y": 310,
            "width": 90,
            "height": 70,
        }
        return img, primary_bbox, rival_bbox

    def test_conjoined_rival_defers_to_v15(self):
        img, bbox, rival = self._make_conjoined_scene()
        from app.services.smart_balloon import process_smart_balloon_v15

        v16_direct = process_smart_balloon_v16_adaptive(
            img, bbox, rival_boxes=[rival]
        )
        assert v16_direct.get("success") is False
        assert v16_direct.get("fallback") == "conjoined_deferred_to_v15"

        dispatched = process_smart_balloon_v15(
            img, bbox, rival_boxes=[rival], use_adaptive=True
        )
        assert dispatched["success"], "Dispatcher should fall back to V15 and succeed"

    def test_near_duplicate_rival_does_not_defer(self):
        img, bbox, _ = self._make_conjoined_scene()

        near_duplicate = dict(bbox)
        result = process_smart_balloon_v16_adaptive(
            img, bbox, rival_boxes=[near_duplicate]
        )
        assert result["success"], "Near-duplicate rival must not trigger conjoined deferral"

    def test_dispatcher_returns_v16_schema_when_enabled(self):
        img, bbox = create_test_image_gray_background()
        from app.services.smart_balloon import process_smart_balloon_v15

        res = process_smart_balloon_v15(img, bbox, use_adaptive=True)
        assert res["success"]
        assert res.get("method") == "smart_balloon_v16_adaptive"
        assert "crop_mask" in res and res["crop_mask"] is not None
        assert "raw_contour_points" in res


class TestV16ConfigDefault:
    def test_adaptive_default_is_opt_in(self):
        from app.config import get_smart_balloon_adaptive_enabled

        assert get_smart_balloon_adaptive_enabled(None) is False
        assert get_smart_balloon_adaptive_enabled({}) is False
        assert get_smart_balloon_adaptive_enabled({"smart_balloon_adaptive": True}) is True
        assert get_smart_balloon_adaptive_enabled({"smart_balloon_adaptive": False}) is False

    def test_compute_smart_balloon_bounds_respects_settings(self):
        from app.services.detector import compute_smart_balloon_bounds

        img, bbox = create_test_image_gray_background()

        res_off = compute_smart_balloon_bounds(img, dict(bbox), settings={"smart_balloon_adaptive": False})
        assert res_off.get("method") == "smart_balloon_v15"

        res_on = compute_smart_balloon_bounds(img, dict(bbox), settings={"smart_balloon_adaptive": True})
        assert res_on.get("method") == "smart_balloon_v16_adaptive"


class TestSamBoxFallback:
    def _make_gradient_box_page(self):
        img = np.zeros((700, 900, 3), dtype=np.uint8)
        for y in range(700):
            brightness = int(140 + (170 - 140) * (y / 700.0))
            img[y, :] = (brightness, brightness, brightness)

        box_mask = np.zeros((700, 900), dtype=np.uint8)
        cv2.rectangle(box_mask, (250, 180), (650, 520), 255, -1)
        img[box_mask > 0] = np.clip(img[box_mask > 0].astype(int) + 55, 0, 255).astype(np.uint8)

        for sx in range(258, 650, 18):
            cv2.line(img, (sx, 185), (sx, 515), (100, 100, 100), 8)
        for sy in range(186, 520, 18):
            cv2.line(img, (255, sy), (645, sy), (100, 100, 100), 8)

        cnts, _ = cv2.findContours(box_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        cv2.drawContours(img, cnts, -1, (25, 25, 25), 4)

        bbox = {"x": 300, "y": 240, "width": 300, "height": 220}
        gt_mask = np.zeros((700, 900), dtype=np.uint8)
        cv2.rectangle(gt_mask, (254, 184), (646, 516), 255, -1)
        return img, bbox, gt_mask

    def test_fallback_triggers_and_returns_full_schema(self, monkeypatch):
        import app.services.sam_segmenter as sam_mod
        from app.services.detector import compute_smart_balloon_bounds

        img, bbox, gt_mask = self._make_gradient_box_page()

        def fake_segment(image_bgr, x0, y0, x1, y1):
            out = np.zeros(image_bgr.shape[:2], dtype=np.uint8)
            cv2.rectangle(out, (250, 180), (650, 520), 255, -1)
            return out

        monkeypatch.setattr(sam_mod, "smart_segment_box", fake_segment)

        res = compute_smart_balloon_bounds(
            img, dict(bbox), settings={"smart_balloon_adaptive": False}
        )
        assert res.get("success") is True
        assert res["method"] == "sam_box_fallback"
        for key in ("smart_x", "smart_width", "crop_mask", "crop_offset",
                    "contour_points", "raw_contour_points", "row_width_constraints", "metadata"):
            assert key in res, f"missing {key}"
        assert res["mask_area"] > 0

    def test_fallback_skipped_when_sam_unavailable(self, monkeypatch):
        import app.services.sam_segmenter as sam_mod
        from app.services.detector import compute_smart_balloon_bounds

        img, bbox, _ = self._make_gradient_box_page()
        monkeypatch.setattr(sam_mod, "smart_segment_box", lambda *a, **k: None)

        res = compute_smart_balloon_bounds(
            img, dict(bbox), settings={"smart_balloon_adaptive": False}
        )
        assert res.get("method") != "sam_box_fallback"

    def test_fallback_gate_rejects_small_mask(self, monkeypatch):
        import app.services.sam_segmenter as sam_mod
        from app.services.detector import compute_smart_balloon_bounds

        img, bbox, _ = self._make_gradient_box_page()

        def fake_segment(image_bgr, x0, y0, x1, y1):
            out = np.zeros(image_bgr.shape[:2], dtype=np.uint8)
            cv2.rectangle(out, (x0, y0), (x0 + 20, y0 + 20), 255, -1)
            return out

        monkeypatch.setattr(sam_mod, "smart_segment_box", fake_segment)

        res = compute_smart_balloon_bounds(
            img, dict(bbox), settings={"smart_balloon_adaptive": False}
        )
        assert res.get("method") != "sam_box_fallback"

    def test_v15_still_wins_on_white_balloon(self):
        from app.services.detector import compute_smart_balloon_bounds

        img = np.full((600, 800, 3), 245, dtype=np.uint8)
        cv2.ellipse(img, (400, 300), (150, 100), 0, 0, 360, (255, 255, 255), -1)
        cv2.ellipse(img, (400, 300), (150, 100), 0, 0, 360, (0, 0, 0), 3)
        bbox = {"x": 320, "y": 240, "width": 160, "height": 120}

        res = compute_smart_balloon_bounds(img, dict(bbox), settings={"smart_balloon_adaptive": False})
        assert res.get("success") is True
        assert res.get("method") == "smart_balloon_v15"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
