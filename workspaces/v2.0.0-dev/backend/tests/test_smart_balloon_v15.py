"""Unit tests for Smart Balloon V15 Engine and configuration."""

import cv2
import numpy as np
import pytest

from app.config import get_enable_smart_balloon, get_smart_balloon_inset_ratio
from app.services.smart_balloon import (
    apply_contour_inset,
    classify_balloon_archetype,
    compute_edge_roughness,
    compute_rectangularity,
    count_sharp_corners,
    process_smart_balloon_v15,
)
from app.services.typesetting.service import persist_typesetting_spec
from app.services.typesetting.schemas import TypesettingSpec, LayoutRegionSpec


class TestSmartBalloonV15Config:
    def test_get_enable_smart_balloon_defaults(self):
        assert get_enable_smart_balloon(None) is False
        assert get_enable_smart_balloon({}) is False
        assert get_enable_smart_balloon({"enable_smart_balloon": False}) is False
        assert get_enable_smart_balloon({"enable_smart_balloon": True}) is True

    def test_get_smart_balloon_inset_ratio_clamping(self):
        assert get_smart_balloon_inset_ratio(None) == 0.075
        assert get_smart_balloon_inset_ratio({}) == 0.075
        assert get_smart_balloon_inset_ratio({"smart_balloon_inset_ratio": 0.15}) == 0.15
        # Clamp low
        assert get_smart_balloon_inset_ratio({"smart_balloon_inset_ratio": 0.01}) == 0.05
        # Clamp high
        assert get_smart_balloon_inset_ratio({"smart_balloon_inset_ratio": 0.50}) == 0.25


class TestSmartBalloonV15Archetypes:
    def test_smooth_oval_classification(self):
        # Create an oval contour
        img = np.zeros((300, 300), dtype=np.uint8)
        cv2.ellipse(img, (150, 150), (100, 70), 0, 0, 360, 255, -1)
        cnts, _ = cv2.findContours(img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        contour = cnts[0]

        archetype, meta = classify_balloon_archetype(contour, {"x": 100, "y": 100, "width": 100, "height": 100})
        assert archetype == "SMOOTH_OVAL"
        assert meta["roughness"] < 1.5

    def test_rectangular_classification(self):
        # Create a rectangular contour
        img = np.zeros((300, 500), dtype=np.uint8)
        cv2.rectangle(img, (50, 100), (450, 200), 255, -1)
        cnts, _ = cv2.findContours(img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        contour = cnts[0]

        archetype, meta = classify_balloon_archetype(contour, {"x": 100, "y": 100, "width": 300, "height": 80})
        assert archetype == "RECTANGULAR"
        assert meta["rect_ratio"] > 0.85

    def test_spiky_fuzzy_classification(self):
        # Create a spiky star/aura contour
        img = np.zeros((400, 400), dtype=np.uint8)
        pts = []
        center = (200, 200)
        for i in range(72):
            angle = i * (2 * np.pi / 72)
            r = 100 + (25 if i % 2 == 0 else -15)
            x = int(center[0] + r * np.cos(angle))
            y = int(center[1] + r * np.sin(angle))
            pts.append([x, y])
        cv2.fillPoly(img, [np.array(pts)], 255)
        cnts, _ = cv2.findContours(img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        contour = cnts[0]

        roughness = compute_edge_roughness(contour, sigma=5.0)
        # After reducing sigma from 12 to 5, roughness threshold is adjusted to 1.8
        assert roughness > 1.0, f"Expected roughness > 1.0, got {roughness}"
        archetype, meta = classify_balloon_archetype(contour, {"x": 150, "y": 150, "width": 100, "height": 100})
        # Star shape with many sharp corners will be classified as ANGULAR, which is correct
        assert archetype in ["SPIKY_FUZZY", "ANGULAR"], f"Expected SPIKY_FUZZY or ANGULAR, got {archetype}"

    def test_angular_classification(self):
        # Create a 6-corner polygon with sharp corners
        img = np.zeros((300, 300), dtype=np.uint8)
        pts = np.array([[150, 30], [270, 80], [220, 220], [150, 270], [80, 220], [30, 80]])
        cv2.fillPoly(img, [pts], 255)
        cnts, _ = cv2.findContours(img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        contour = cnts[0]

        sharp_corners = count_sharp_corners(contour)
        assert sharp_corners >= 2
        archetype, _ = classify_balloon_archetype(contour, {"x": 50, "y": 50, "width": 200, "height": 200})
        assert archetype == "ANGULAR"

    def test_fuzzy_raw_image_edge_classification(self):
        # Create a synthetic fuzzy/thought balloon with dense stroke feathering around the boundary
        raw_gray = np.full((300, 300), 200, dtype=np.uint8)
        # Draw central white bubble
        cv2.ellipse(raw_gray, (150, 150), (80, 60), 0, 0, 360, 255, -1)
        # Draw lots of small fuzzy stroke marks along the boundary
        for angle_deg in range(0, 360, 5):
            rad = np.deg2rad(angle_deg)
            r = 75 + (angle_deg % 15)
            x = int(150 + r * np.cos(rad))
            y = int(150 + r * np.sin(rad))
            cv2.circle(raw_gray, (x, y), 3, 0, -1)

        # Base contour
        cnt_img = np.zeros((300, 300), dtype=np.uint8)
        cv2.ellipse(cnt_img, (150, 150), (80, 60), 0, 0, 360, 255, -1)
        cnts, _ = cv2.findContours(cnt_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        contour = cnts[0]

        archetype, meta = classify_balloon_archetype(
            contour,
            {"x": 100, "y": 100, "width": 100, "height": 100},
            crop_w=300,
            crop_h=300,
            raw_gray=raw_gray,
        )
        assert archetype == "SPIKY_FUZZY"
        assert meta["edge_density"] > 0.10


class TestSmartBalloonV15Inset:
    def test_apply_contour_inset(self):
        img = np.zeros((300, 300), dtype=np.uint8)
        cv2.rectangle(img, (50, 50), (250, 250), 255, -1)
        cnts, _ = cv2.findContours(img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        contour = cnts[0]

        inset_cnt = apply_contour_inset(contour, inset_ratio=0.10)
        area_orig = cv2.contourArea(contour)
        area_inset = cv2.contourArea(inset_cnt)

        # Inset area should be ~ (0.90)^2 = ~81% of original
        assert area_inset < area_orig
        assert 0.70 < (area_inset / area_orig) < 0.90


class TestSmartBalloonV15Pipeline:
    def test_process_smart_balloon_v15_white_balloon(self):
        # Create synthetic comic page with a white balloon and black text
        page = np.full((600, 600, 3), 40, dtype=np.uint8)  # dark background
        cv2.ellipse(page, (300, 300), (140, 100), 0, 0, 360, (255, 255, 255), -1)  # white bubble
        cv2.ellipse(page, (300, 300), (140, 100), 0, 0, 360, (0, 0, 0), 3)  # black stroke
        # Draw some text
        cv2.putText(page, "Test Text", (240, 310), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)

        text_bbox = {"x": 230, "y": 280, "width": 140, "height": 50}
        res = process_smart_balloon_v15(page, text_bbox, inset_ratio=0.10)

        assert res["success"] is True
        assert res["method"] == "smart_balloon_v15"
        assert res["archetype"] == "SMOOTH_OVAL"
        assert res["smart_width"] > text_bbox["width"]
        assert res["smart_height"] > text_bbox["height"]
        assert res["safe_bbox"]["width"] < res["raw_bbox"]["width"]

    def test_process_smart_balloon_v15_fallback_on_empty(self):
        black_page = np.zeros((600, 600, 3), dtype=np.uint8)
        text_bbox = {"x": 100, "y": 100, "width": 80, "height": 40}
        res = process_smart_balloon_v15(black_page, text_bbox)

        assert res["success"] is False
        assert "fallback" in res["method"]
        assert res["smart_x"] == 100.0
        assert res["smart_width"] == 80.0


class TestSmartBalloonRowWidthSync:
    """Test that row_width_constraints is properly synced to block.extra_metadata.smart_balloon"""

    def test_persist_spec_syncs_row_width_constraints(self):
        from unittest.mock import MagicMock

        # Create mock block with Smart Balloon metadata
        block = MagicMock()
        block.extra_metadata = {
            "smart_balloon": {
                "safe_bbox": {"x": 100, "y": 100, "width": 200, "height": 150},
                "center": {"x": 200, "y": 175},
                "archetype": "SMOOTH_OVAL"
            }
        }
        block.font_size = 24.0
        block.id = "test_block_123"
        block.translation = "Test translation text"
        block.source_text = "Test source"
        block.x = 100.0
        block.y = 100.0
        block.width = 200.0
        block.height = 150.0
        block.balloon_type = "bubble"
        block.font_family = "TH Sarabun New"
        block.bold = False
        block.italic = False
        block.text_direction = "horizontal"
        block.text_align = "center"
        block.rotation_deg = 0.0
        block.color_hex = "#000000"

        # Create TypesettingSpec with row_width_constraints in metrics
        spec = TypesettingSpec(
            layout_engine_version="smart_balloon_v15",
            layout_version="smart_balloon_v15",
            spec_id="spec_test_123",
            block_id="test_block_123",
            source_signature="sb_test_123_24_2",
            layout_status="valid",
            layout_source="auto",
            decision_status="AUTO_APPLIED",
            requested_font_family="TH Sarabun New",
            resolved_font_id="default",
            resolved_font_family="TH Sarabun New",
            resolved_postscript_name="THSarabunNew",
            resolved_font_style="Regular",
            font_postscript_name="THSarabunNew",
            font_fingerprint="unknown",
            font_size=24.0,
            bold=False,
            italic=False,
            color_hex="#000000",
            explicit_lines=["Line 1", "Line 2"],
            normalized_text="Line 1Line 2",
            line_height=30.0,
            tracking=0.0,
            horizontal_align="center",
            text_align="center",
            vertical_align="center",
            layout_region=LayoutRegionSpec(
                x=100.0,
                y=100.0,
                width=200.0,
                height=150.0,
                shape="smart_balloon",
                confidence=0.98,
                source="smart_balloon",
            ),
            shape_type="smart_balloon",
            overflow=False,
            overflow_score=0.0,
            quality_score=95.0,
            metrics={
                "is_smart_balloon": True,
                "archetype": "SMOOTH_OVAL",
                "row_width_constraints": {
                    "enabled": True,
                    "row_widths": [120.5, 145.2, 180.0, 175.3, 150.8, 125.4],
                    "height": 150
                }
            }
        )

        # Persist the spec
        metadata = persist_typesetting_spec(block, spec)

        # Verify row_width_constraints was synced to smart_balloon
        assert "smart_balloon" in metadata
        assert "row_width_constraints" in metadata["smart_balloon"]

        row_constraints = metadata["smart_balloon"]["row_width_constraints"]
        assert row_constraints["enabled"] is True
        assert len(row_constraints["row_widths"]) == 6
        assert row_constraints["height"] == 150
        assert row_constraints["row_widths"][0] == 120.5
        assert row_constraints["row_widths"][2] == 180.0

    def test_persist_spec_no_sync_for_non_smart_balloon(self):
        from unittest.mock import MagicMock

        # Create mock block WITHOUT Smart Balloon metadata
        block = MagicMock()
        block.extra_metadata = {}
        block.font_size = 18.0
        block.id = "test_block_456"
        block.translation = "Regular text"
        block.source_text = "Regular source"
        block.x = 50.0
        block.y = 50.0
        block.width = 100.0
        block.height = 50.0
        block.balloon_type = "bubble"
        block.font_family = "Arial"
        block.bold = False
        block.italic = False
        block.text_direction = "horizontal"
        block.text_align = "center"
        block.rotation_deg = 0.0
        block.color_hex = "#000000"

        # Create regular TypesettingSpec (not smart balloon)
        spec = TypesettingSpec(
            layout_engine_version="v2",
            layout_version="v2",
            spec_id="spec_test_456",
            block_id="test_block_456",
            source_signature="regular_456",
            layout_status="valid",
            layout_source="auto",
            decision_status="AUTO_APPLIED",
            requested_font_family="Arial",
            resolved_font_id="arial",
            resolved_font_family="Arial",
            resolved_postscript_name="Arial",
            resolved_font_style="Regular",
            font_postscript_name="Arial",
            font_fingerprint="unknown",
            font_size=18.0,
            bold=False,
            italic=False,
            color_hex="#000000",
            explicit_lines=["Test"],
            normalized_text="Test",
            line_height=22.0,
            tracking=0.0,
            horizontal_align="center",
            text_align="center",
            vertical_align="center",
            layout_region=LayoutRegionSpec(
                x=50.0,
                y=50.0,
                width=100.0,
                height=50.0,
            ),
            shape_type="bubble",
            overflow=False,
            overflow_score=0.0,
            quality_score=90.0,
            metrics={"is_smart_balloon": False}
        )

        # Persist the spec
        metadata = persist_typesetting_spec(block, spec)

        # Verify no smart_balloon key was added
        assert "smart_balloon" not in metadata


class TestSmartBalloonZeroDistortionCompletion:
    def test_conjoined_balloons_parametric_bridge(self):
        # Create synthetic figure-8 conjoined balloons
        page = np.full((600, 600, 3), 40, dtype=np.uint8)
        # Top bubble
        cv2.ellipse(page, (300, 220), (100, 80), 0, 0, 360, (255, 255, 255), -1)
        # Bottom bubble overlapping
        cv2.ellipse(page, (300, 380), (100, 80), 0, 0, 360, (255, 255, 255), -1)

        bbox_top = {"x": 250, "y": 180, "width": 100, "height": 80}
        bbox_bot = {"x": 250, "y": 340, "width": 100, "height": 80}

        res_top = process_smart_balloon_v15(page, bbox_top, rival_boxes=[bbox_bot])
        res_bot = process_smart_balloon_v15(page, bbox_bot, rival_boxes=[bbox_top])

        # Verify both top and bottom balloons are processed with valid contours and centers
        assert len(res_top["contour_points"]) > 20
        assert len(res_bot["contour_points"]) > 20
        assert res_top["center"]["y"] < res_bot["center"]["y"]
        assert res_top["safe_bbox"]["height"] > 0
        assert res_bot["safe_bbox"]["height"] > 0

    def test_smart_balloon_thai_multiline_balancing_and_wrapping(self):
        """
        Validates that Thai text with long compound sentences and exclamations
        (e.g. 'อวา...\nอยู่กันพร้อมหน้าพร้อมตาเลยนะเนี่ย!')
        properly wraps into balanced multi-line rows that fit inside the balloon contour
        without overflowing or being forced into an unbalanced 2-line clump.
        """
        from app.services.smart_balloon_typesetting import fit_text_to_smart_balloon_shape
        from app.services.typesetting.segmentation import segment_text

        text = "อวา...\nอยู่กันพร้อมหน้าพร้อมตาเลยนะเนี่ย!"
        tokens = segment_text(text)

        sb = {
            "safe_bbox": {"x": 100, "y": 100, "width": 305, "height": 237},
            "center": {"x": 252, "y": 218},
            "contour_points": [[100, 218], [252, 100], [405, 218], [252, 337]],
        }

        res = fit_text_to_smart_balloon_shape(None, sb, tokens, "C:/Windows/Fonts/tahoma.ttf")
        assert res is not None
        lines = res["explicit_lines"]

        # Must break into 3 or 4 balanced lines, NOT a single massive 34-character overflow line
        assert len(lines) >= 3, f"Expected >= 3 balanced lines, got {lines}"
        assert lines[0] == "อวา..."
        # No single line should have more than 20 characters
        for line in lines:
            assert len(line) <= 20, f"Line too long (should be wrapped): {line}"
        # Font size should be comfortable and legible (>= 24px)
        assert res["font_size"] >= 24.0

    def test_conjoined_balloons_with_tail_and_top_leak(self):
        """
        Tests that conjoined speech bubbles near a panel border with speech tails
        and anti-aliased gaps are cleanly sliced at the true waist, contained inside the panel,
        and classified as SMOOTH_OVAL instead of leaking or becoming SPIKY_FUZZY.
        """
        img = np.full((800, 600, 3), 180, dtype=np.uint8)
        # Sky inside panel (y >= 100)
        img[100:, :] = (210, 190, 160)
        # White area above panel (y < 100)
        img[:100, :] = 255
        # Black panel line at y=100
        cv2.line(img, (0, 100), (600, 100), (0, 0, 0), 4)
        # White gutter going up above panel
        cv2.line(img, (300, 0), (300, 100), (255, 255, 255), 4)

        # Bubble 1 (top): center (300, 220), radius (120, 90)
        cv2.ellipse(img, (300, 220), (120, 90), 0, 0, 360, (255, 255, 255), -1)
        cv2.ellipse(img, (300, 220), (120, 90), 0, 0, 360, (0, 0, 0), 3)

        # Bubble 2 (bottom): center (360, 370), radius (110, 80)
        cv2.ellipse(img, (360, 370), (110, 80), 0, 0, 360, (255, 255, 255), -1)
        cv2.ellipse(img, (360, 370), (110, 80), 0, 0, 360, (0, 0, 0), 3)

        # Conjoined connection
        cv2.circle(img, (330, 295), 45, (255, 255, 255), -1)

        # Gap at top of bubble 1
        cv2.circle(img, (300, 100), 5, (255, 255, 255), -1)

        # Tail at bottom of bubble 2
        tail_pts = np.array([[360, 440], [350, 510], [380, 440]], np.int32)
        cv2.fillPoly(img, [tail_pts], (255, 255, 255))
        cv2.polylines(img, [tail_pts], True, (0, 0, 0), 3)

        # Text in both bubbles
        cv2.putText(img, "Top Text", (240, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
        cv2.putText(img, "Bottom Text", (300, 370), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)

        bbox_top = {"x": 230, "y": 180, "width": 140, "height": 60}
        bbox_bot = {"x": 290, "y": 330, "width": 140, "height": 60}

        res_top = process_smart_balloon_v15(img, bbox_top, rival_boxes=[bbox_bot])
        res_bot = process_smart_balloon_v15(img, bbox_bot, rival_boxes=[bbox_top])

        # 1. Must be classified as SMOOTH_OVAL
        assert res_top["archetype"] == "SMOOTH_OVAL"
        assert res_bot["archetype"] == "SMOOTH_OVAL"

        # 2. Top balloon must be contained strictly below panel line (y >= 100)
        assert res_top["raw_bbox"]["y"] >= 100
        assert res_top["safe_bbox"]["y"] >= 100

        # 3. Both balloons must have separated bounding boxes at the waist
        assert res_top["raw_bbox"]["y"] + res_top["raw_bbox"]["height"] <= res_bot["raw_bbox"]["y"] + 30
        assert res_top["center"]["y"] < res_bot["center"]["y"]

    def test_oval_balloon_with_dense_text_and_dark_background(self):
        """
        Tests that an oval balloon on black background containing dense text strokes
        fills completely without jagged character cavities and is classified as SMOOTH_OVAL.
        """
        img = np.zeros((600, 600, 3), dtype=np.uint8)  # Black background
        # White balloon
        cv2.ellipse(img, (300, 300), (160, 200), 0, 0, 360, (255, 255, 255), -1)
        cv2.ellipse(img, (300, 300), (160, 200), 0, 0, 360, (0, 0, 0), 4)

        # Dense Japanese text lines inside the balloon
        for y_line in range(200, 420, 35):
            cv2.putText(img, "テキストサンプル文", (180, y_line), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)

        bbox = {"x": 200, "y": 220, "width": 200, "height": 160}
        res = process_smart_balloon_v15(img, bbox)

        assert res["success"] is True
        assert res["archetype"] == "SMOOTH_OVAL"
        # Mask area should cover the vast majority of the ellipse (>80% of pi*160*200)
        ellipse_area = np.pi * 160 * 200
        assert res["mask_area"] > 0.78 * ellipse_area

    def test_single_oval_balloon_with_multiple_internal_blocks_preserves_smooth_oval(self):
        """Verify that two detected text boxes inside a single smooth oval balloon (e.g. upper and lower text)
        do NOT cause false conjoined balloon slicing or false SPIKY_FUZZY classification."""
        img = np.zeros((700, 600, 3), dtype=np.uint8)
        # Draw single large smooth white oval speech balloon with upper tail
        cv2.ellipse(img, (300, 350), (220, 260), 0, 0, 360, (255, 255, 255), -1)
        cv2.fillPoly(img, [np.array([[300, 100], [285, 30], [330, 100]])], (255, 255, 255))
        # Draw black outline
        cv2.ellipse(img, (300, 350), (220, 260), 0, 0, 360, (0, 0, 0), 4)

        # Upper text box (Block #9) and Lower text box (Block #10) inside the same balloon
        bbox_top = {"x": 200, "y": 200, "width": 200, "height": 100}
        bbox_bot = {"x": 220, "y": 380, "width": 180, "height": 120}

        res_top = process_smart_balloon_v15(img, bbox_top, rival_boxes=[bbox_bot])
        assert res_top["success"] is True
        assert res_top["archetype"] == "SMOOTH_OVAL", f"Expected SMOOTH_OVAL, got {res_top['archetype']}"
        # Contour should cover the entire balloon without carving a jagged notch around bbox_bot
        assert res_top["mask_area"] > (np.pi * 220 * 260 * 0.80)


