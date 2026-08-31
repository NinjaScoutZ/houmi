import unittest
from types import SimpleNamespace

from app.services.layout_region import get_effective_layout_region
from app.services.smart_balloon_typesetting import compute_smart_balloon_typesetting
from app.services.typesetting.service import compute_block_typesetting


class TestDisabledSmartBalloon(unittest.TestCase):
    def setUp(self):
        # Create a mock block with both regular bbox (100, 100, 200, 150)
        # and Smart Balloon data (50, 40, 320, 260)
        self.project_disabled = SimpleNamespace(settings={"enable_smart_balloon": False})
        self.project_enabled = SimpleNamespace(settings={"enable_smart_balloon": True})
        self.page_disabled = SimpleNamespace(project=self.project_disabled, width=1000, height=1400)
        self.page_enabled = SimpleNamespace(project=self.project_enabled, width=1000, height=1400)

        self.block_disabled = SimpleNamespace(
            id="test_block_1",
            page=self.page_disabled,
            x=100.0,
            y=100.0,
            width=200.0,
            height=150.0,
            smart_x=50.0,
            smart_y=40.0,
            smart_width=320.0,
            smart_height=260.0,
            translation="ทดสอบปิดระบบ Smart Balloon",
            balloon_type="bubble",
            font_family="NotoSansThai",
            bold=False,
            italic=False,
            text_direction="horizontal",
            text_align="center",
            rotation_deg=0.0,
            color_hex="#000000",
            font_size=16.0,
            extra_metadata={
                "smart_balloon": {
                    "safe_bbox": {"x": 55.0, "y": 45.0, "width": 310.0, "height": 250.0},
                    "contour_points": [[50, 40], [370, 40], [370, 300], [50, 300]],
                    "archetype": "OVAL",
                },
                "layout_region": {
                    "x": 50.0,
                    "y": 40.0,
                    "width": 320.0,
                    "height": 260.0,
                    "source": "smart_balloon_v15",
                },
            },
        )

        self.block_enabled = SimpleNamespace(
            id="test_block_2",
            page=self.page_enabled,
            x=100.0,
            y=100.0,
            width=200.0,
            height=150.0,
            smart_x=50.0,
            smart_y=40.0,
            smart_width=320.0,
            smart_height=260.0,
            translation="ทดสอบเปิดระบบ Smart Balloon",
            balloon_type="bubble",
            font_family="NotoSansThai",
            bold=False,
            italic=False,
            text_direction="horizontal",
            text_align="center",
            rotation_deg=0.0,
            color_hex="#000000",
            font_size=16.0,
            extra_metadata={
                "smart_balloon": {
                    "safe_bbox": {"x": 55.0, "y": 45.0, "width": 310.0, "height": 250.0},
                    "contour_points": [[50, 40], [370, 40], [370, 300], [50, 300]],
                    "archetype": "OVAL",
                },
                "layout_region": {
                    "x": 50.0,
                    "y": 40.0,
                    "width": 320.0,
                    "height": 260.0,
                    "source": "smart_balloon_v15",
                },
            },
        )

    def test_layout_region_strictly_uses_detected_box_when_disabled(self):
        """When enable_smart_balloon is False, layout_region must ignore smart_x and return detected box."""
        region = get_effective_layout_region(self.block_disabled, settings={"enable_smart_balloon": False})
        self.assertEqual(region["x"], 100.0)
        self.assertEqual(region["y"], 100.0)
        self.assertEqual(region["width"], 200.0)
        self.assertEqual(region["height"], 150.0)
        self.assertNotEqual(region["source"], "smart_balloon")

    def test_layout_region_uses_smart_balloon_when_enabled(self):
        """When enable_smart_balloon is True, layout_region uses smart coordinates."""
        region = get_effective_layout_region(self.block_enabled, settings={"enable_smart_balloon": True})
        self.assertEqual(region["x"], 50.0)
        self.assertEqual(region["y"], 40.0)
        self.assertEqual(region["width"], 320.0)
        self.assertEqual(region["height"], 260.0)
        self.assertEqual(region["source"], "smart_balloon")

    def test_compute_smart_balloon_typesetting_returns_none_when_disabled(self):
        """Dedicated smart balloon typesetter must refuse execution when disabled."""
        spec = compute_smart_balloon_typesetting(self.block_disabled, project_settings={"enable_smart_balloon": False})
        self.assertIsNone(spec)

    def test_compute_block_typesetting_honors_disabled_setting(self):
        """Typesetting service must not produce a smart_balloon spec when setting is False."""
        spec = compute_block_typesetting(self.block_disabled)
        self.assertIsNotNone(spec)
        self.assertEqual(spec.layout_region.x, 100.0)
        self.assertEqual(spec.layout_region.y, 100.0)
        self.assertEqual(spec.layout_region.width, 200.0)
        self.assertEqual(spec.layout_region.height, 150.0)

    def test_signature_changes_when_smart_balloon_toggled(self):
        """Toggling Smart Balloon must change the block signature to invalidate stale specs."""
        from app.services.typesetting.service import compute_block_signature
        sig_disabled = compute_block_signature(self.block_disabled)
        sig_enabled = compute_block_signature(self.block_enabled)
        self.assertNotEqual(sig_disabled, sig_enabled)


if __name__ == "__main__":
    unittest.main()
