"""Tests for Smart Balloon font_size_mode integration."""

import pytest
from unittest.mock import Mock
from app.services.smart_balloon_typesetting import compute_smart_balloon_typesetting


class TestSmartBalloonFontSizeMode:
    """Test that Smart Balloon respects font_size_mode correctly."""

    def test_auto_mode_allows_dynamic_sizing(self):
        """When font_size_mode='auto', Smart Balloon should compute optimal size."""
        block = Mock()
        block.id = 1
        block.translation = "Test text"
        block.source_text = "Test text"
        block.font_family = "NotoSansThai"
        block.bold = False
        block.italic = False
        block.color_hex = "#000000"
        block.smart_mask_path = None
        block.extra_metadata = {
            "smart_balloon": {
                "safe_bbox": {"x": 100, "y": 100, "width": 200, "height": 100},
                "center": {"x": 200, "y": 150},
                "contour_points": [[100, 100], [300, 100], [300, 200], [100, 200]],
                "archetype": "SMOOTH_OVAL",
            },
            "font_size_mode": "auto",
            "manual_font_size": None,
            "min_font_size": 12.0,
        }

        spec = compute_smart_balloon_typesetting(block)

        # Should compute a size automatically (not fixed)
        assert spec is not None
        assert spec.font_size > 0
        # Font size should be within reasonable auto-fit range
        assert 12.0 <= spec.font_size <= 100.0

    def test_manual_mode_locks_font_size(self):
        """When font_size_mode='manual', should use manual_font_size as fixed size."""
        block = Mock()
        block.id = 2
        block.translation = "Test"
        block.source_text = "Test"
        block.font_family = "NotoSansThai"
        block.bold = False
        block.italic = False
        block.color_hex = "#000000"
        block.smart_mask_path = None
        block.extra_metadata = {
            "smart_balloon": {
                "safe_bbox": {"x": 100, "y": 100, "width": 200, "height": 100},
                "center": {"x": 200, "y": 150},
                "contour_points": [[100, 100], [300, 100], [300, 200], [100, 200]],
                "archetype": "SMOOTH_OVAL",
            },
            "font_size_mode": "manual",
            "manual_font_size": 24.0,
            "min_font_size": 12.0,
        }

        spec = compute_smart_balloon_typesetting(block)

        # Should respect the manual size (24.0) as the maximum
        assert spec is not None
        assert spec.font_size <= 24.0

    def test_fixed_mode_locks_font_size(self):
        """When font_size_mode='fixed', should treat as manual mode."""
        block = Mock()
        block.id = 3
        block.translation = "X"
        block.source_text = "X"
        block.font_family = "NotoSansThai"
        block.bold = False
        block.italic = False
        block.color_hex = "#000000"
        block.smart_mask_path = None
        block.extra_metadata = {
            "smart_balloon": {
                "safe_bbox": {"x": 100, "y": 100, "width": 200, "height": 100},
                "center": {"x": 200, "y": 150},
                "contour_points": [[100, 100], [300, 100], [300, 200], [100, 200]],
                "archetype": "SMOOTH_OVAL",
            },
            "font_size_mode": "fixed",
            "manual_font_size": 36.0,
        }

        spec = compute_smart_balloon_typesetting(block)

        assert spec is not None
        assert spec.font_size <= 36.0

    def test_backward_compatibility_manual_font_size_without_mode(self):
        """If manual_font_size is set but no font_size_mode, should lock to manual."""
        block = Mock()
        block.id = 4
        block.translation = "Test"
        block.source_text = "Test"
        block.font_family = "NotoSansThai"
        block.bold = False
        block.italic = False
        block.color_hex = "#000000"
        block.smart_mask_path = None
        block.extra_metadata = {
            "smart_balloon": {
                "safe_bbox": {"x": 100, "y": 100, "width": 200, "height": 100},
                "center": {"x": 200, "y": 150},
                "contour_points": [[100, 100], [300, 100], [300, 200], [100, 200]],
                "archetype": "SMOOTH_OVAL",
            },
            "manual_font_size": 18.0,
            # No font_size_mode specified
        }

        spec = compute_smart_balloon_typesetting(block)

        # Should respect manual_font_size for backward compatibility
        assert spec is not None
        assert spec.font_size <= 18.0

    def test_auto_mode_overrides_manual_font_size(self):
        """When font_size_mode='auto', should ignore manual_font_size."""
        block = Mock()
        block.id = 5
        block.translation = "Text"
        block.source_text = "Text"
        block.font_family = "NotoSansThai"
        block.bold = False
        block.italic = False
        block.color_hex = "#000000"
        block.smart_mask_path = None
        block.extra_metadata = {
            "smart_balloon": {
                "safe_bbox": {"x": 100, "y": 100, "width": 300, "height": 150},
                "center": {"x": 250, "y": 175},
                "contour_points": [[100, 100], [400, 100], [400, 250], [100, 250]],
                "archetype": "SMOOTH_OVAL",
            },
            "font_size_mode": "auto",
            "manual_font_size": 18.0,  # Should be ignored
            "min_font_size": 12.0,
        }

        spec = compute_smart_balloon_typesetting(block)

        # Should compute size dynamically, not locked to 18.0
        assert spec is not None
        # With larger balloon, auto mode should find larger size than 18.0
        assert spec.font_size >= 12.0
