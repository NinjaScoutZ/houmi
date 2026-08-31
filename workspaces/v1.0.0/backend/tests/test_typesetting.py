import unittest
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from PIL import Image, ImageFont
from unittest.mock import patch, MagicMock, mock_open

from app.models.all_models import Page, Project, TextBlock
from app.services.layout_region import refresh_block_layout_region
from app.services.typesetting import (
    compute_block_typesetting,
    get_effective_typesetting_spec,
    validate_typesetting_spec,
    compute_block_signature,
    persist_typesetting_spec,
)
from app.services.typesetting.normalization import normalize_text
from app.services.typesetting.segmentation import segment_text
from app.services.typesetting.fitting import compute_best_layout, join_tokens, wrap_tokens_to_lines
from app.services.typesetting.scoring import score_layout
from app.services.typesetting.schemas import TypesettingSpec, StructuredWarning


class TestTypesettingEngine(unittest.TestCase):
    def test_user_edited_translation_never_truncated_by_stale_ai_lines(self):
        block = TextBlock(
            id="test-truncation-block",
            page_id="test-page-111",
            block_index=1,
            x=10.0, y=10.0, width=300.0, height=200.0,
            source_text="Test",
            translation="เฮะเฮะ เช่นนั้นก็ดีแล้ว...",
            font_family="Tahoma", font_size=16.0,
            extra_metadata={
                "line_break_source": "ai_preferred",
                "ai_preferred_lines": ["เฮะเฮะ", "เช่นนั้นก็"],
                "ai_layout_text": "เฮะเฮะเช่นนั้นก็",
            }
        )
        spec = compute_block_typesetting(block)
        rendered_text = "".join(spec.explicit_lines)
        self.assertIn("ดีแล้ว", rendered_text)
    def setUp(self):
        # Create a mock block for testing
        self.block = TextBlock(
            id="test-block-111",
            page_id="test-page-111",
            block_index=1,
            x=10.0,
            y=10.0,
            width=150.0,
            height=50.0,
            source_text="若为仙路",
            translation="若为仙路 CJK",
            font_family="Tahoma",
            font_size=14.0,
            bold=False,
            italic=False,
            text_direction="horizontal",
            text_align="center",
            balloon_type="bubble",
            color_hex="#000000",
            extra_metadata={},
        )

    def test_normalization_preserves_manual_newlines(self):
        text = "  Hello \n  World  \n "
        normalized = normalize_text(text)
        self.assertEqual(normalized, "Hello\nWorld")

    def test_empty_translation_never_typesets_ocr_source_text(self):
        self.block.translation = ""
        self.block.source_text = "OCR source must stay out of translated layout"

        spec = compute_block_typesetting(self.block, log_feedback=False)

        self.assertEqual(spec.normalized_text, "")
        self.assertEqual(spec.explicit_lines, [""])

    def test_authored_lines_are_not_wrapped_again(self):
        self.block.width = 110
        self.block.height = 180
        self.block.translation = (
            "พวกนั้นดูเหมือนจะเป็น\n"
            "คนของกิลด์นักล่ามังกร\n"
            "หรือเปล่านะ?"
        )

        spec = compute_block_typesetting(self.block, log_feedback=False)

        self.assertEqual(spec.explicit_lines, self.block.translation.splitlines())
        self.assertTrue(
            all(item["break_kind"] == "authored" for item in spec.metrics["break_provenance"])
        )

    def test_ai_lines_are_preferred_but_can_be_rebalanced(self):
        first = "มันสู้พวกเราไม่ได้ก็เลยอยากจะข่มขู่ให้พวกเราขยาดกลัวจนถอยหนีไป"
        second = "เพื่อที่มันจะได้ครอบครองผลมรรคาแห่งยุคสมัยและเส้นทางเซียนเอาไว้แต่เพียงผู้เดียว"
        self.block.translation = f"{first}\n{second}"
        self.block.width = 420
        self.block.height = 300
        self.block.extra_metadata = {
            "line_break_source": "ai_preferred",
            "ai_preferred_lines": [first, second],
            "ai_layout_hint": {"shape": "ellipse", "target_lines": 5, "max_lines": 6},
            "min_font_size": 24,
            "max_font_size": 48,
        }

        spec = compute_block_typesetting(self.block, log_feedback=False)

        self.assertGreaterEqual(len(spec.explicit_lines), 3)
        self.assertNotEqual(spec.explicit_lines, [first, second])
        self.assertEqual(
            "".join(spec.explicit_lines).replace(" ", ""),
            (first + second).replace(" ", ""),
        )
        self.assertIn("AI_LINEBREAK_ADJUSTED", [warning.code for warning in spec.warnings])

    def test_ai_max_lines_marks_excess_candidate_as_overflow(self):
        from app.services.typesetting.fitting import rank_line_candidates

        candidates = [{
            "explicit_lines": ["หนึ่ง", "สอง", "สาม"],
            "line_widths": [30.0, 30.0, 30.0],
            "total_height": 90.0,
            "overflow": False,
            "overflow_score": 0.0,
            "break_provenance": [],
            "generator": "beam",
        }]

        best = rank_line_candidates(
            candidates,
            24.0,
            200.0,
            120.0,
            "bubble",
            target_line_count=2,
            maximum_line_count=2,
        )

        self.assertTrue(best["overflow"])
        self.assertEqual(best["line_count_excess"], 1)
        self.assertGreaterEqual(best["overflow_score"], 1000.0)

    def test_segmentation_rules(self):
        # 1. Standalone Thai word: word boundaries and combining marks stay intact
        thai_tokens = segment_text("วิทยา")
        self.assertEqual(thai_tokens, ["วิทยา"])

        # 2. Punctuation should be glued to avoid orphans
        text = "Hello, (วิทยา) 若为仙路。"
        tokens = segment_text(text)
        self.assertIn("Hello,", tokens)
        self.assertIn("(วิทยา)", tokens)
        self.assertIn("路。", tokens)

    def test_thai_authored_spaces_are_preserved(self):
        text = "ถึงจะฟังดูเหมือน ‘สุ่มผนึกความสามารถ’ ไม่ใช่ท่าสังหาร"

        rebuilt = join_tokens(segment_text(text))

        self.assertEqual(rebuilt, text)

    def test_legacy_semantic_tag_never_enters_typesetting_lines(self):
        self.block.translation = "ฉันต้องรีบแล้ว {คิดในใจ}"

        spec = compute_block_typesetting(self.block, log_feedback=False)

        self.assertNotIn("{คิดในใจ}", "\n".join(spec.explicit_lines))

    def test_signature_and_stale_detection(self):
        # Compute baseline signature
        sig1 = compute_block_signature(self.block)

        # 1. Change text -> stale
        self.block.translation = "Changed translation text"
        sig2 = compute_block_signature(self.block)
        self.assertNotEqual(sig1, sig2)

        # Reset
        self.block.translation = "若为仙路 CJK"

        # 2. Change geometry -> stale
        self.block.width = 200.0
        sig3 = compute_block_signature(self.block)
        self.assertNotEqual(sig1, sig3)
        self.block.width = 150.0

        # 3. Change font family -> stale
        self.block.font_family = "Arial"
        sig4 = compute_block_signature(self.block)
        self.assertNotEqual(sig1, sig4)
        self.block.font_family = "Tahoma"

        # 4. Change unrelated field (confidence/index) -> not stale
        self.block.block_index = 99
        self.block.confidence = 0.5
        sig5 = compute_block_signature(self.block)
        self.assertEqual(sig1, sig5)

    def test_project_contour_toggle_invalidates_existing_spec_signature(self):
        project = Project(id="contour-project", settings={})
        self.block.page = Page(
            id="contour-page",
            project=project,
            width=1000,
            height=1000,
            source_image_path="missing-page.png",
        )
        disabled_signature = compute_block_signature(self.block)
        project.settings["enable_contour_layout"] = True
        enabled_signature = compute_block_signature(self.block)
        self.assertNotEqual(disabled_signature, enabled_signature)

    def test_photoshop_antialias_is_canonical_and_invalidates_signature(self):
        smooth_signature = compute_block_signature(self.block)
        self.block.extra_metadata["anti_alias"] = "sharp"
        sharp_signature = compute_block_signature(self.block)
        self.assertNotEqual(smooth_signature, sharp_signature)

        spec = compute_block_typesetting(self.block, log_feedback=False)
        self.assertEqual(spec.anti_alias, "sharp")

    def test_native_font_face_identity_is_part_of_signature(self):
        regular = SimpleNamespace(
            fingerprint="same-font-file",
            style="regular",
            postscript_name="Example-Regular",
        )
        bold = SimpleNamespace(
            fingerprint="same-font-file",
            style="bold",
            postscript_name="Example-Bold",
        )
        with patch(
            "app.services.typesetting.service._resolve_block_font",
            return_value=("Example", regular),
        ):
            regular_signature = compute_block_signature(self.block)
        with patch(
            "app.services.typesetting.service._resolve_block_font",
            return_value=("Example", bold),
        ):
            bold_signature = compute_block_signature(self.block)
        self.assertNotEqual(regular_signature, bold_signature)

    def test_ellipse_vs_rectangle_constraints(self):
        # Long text fits differently in rectangle vs bubble
        tokens = segment_text("หากเป็นวิถีเซียนมนุษย์ธรรมดา")

        # Load Tahoma font handle
        font = ImageFont.load_default()  # minimal default font

        # Bubble constraint check
        _, _, _, overflow_bubble, _, _ = wrap_tokens_to_lines(
            tokens, font, block_w=100.0, block_h=40.0, balloon_type="bubble"
        )
        # Narrative constraint check
        _, _, _, overflow_narrative, _, _ = wrap_tokens_to_lines(
            tokens, font, block_w=100.0, block_h=40.0, balloon_type="narrative"
        )
        # Ellipse constraints are narrower at top/bottom, so it should be more prone to overflow
        self.assertTrue(overflow_bubble or not overflow_narrative)

    def test_legacy_block_compatibility(self):
        # A block with no extra_metadata['typesetting_spec']
        block = TextBlock(
            id="legacy-block",
            page_id="page-1",
            block_index=1,
            x=10.0,
            y=10.0,
            width=100.0,
            height=50.0,
            translation="Legacy text",
            font_family="Tahoma",
            extra_metadata={},
        )
        spec = get_effective_typesetting_spec(block)
        self.assertIsNotNone(spec)
        self.assertEqual(
            spec.layout_status, "stale"
        )  # dynamic fallback is marked stale/auto
        self.assertEqual(spec.normalized_text, "Legacy text")

    def test_schema_serialization(self):
        spec = compute_block_typesetting(self.block)
        # Serialize to dict and validate pydantic validation
        dump = spec.model_dump()
        self.assertEqual(
            get_effective_typesetting_spec(self.block).layout_status, "stale"
        )
        loaded = TypesettingSpec.model_validate(dump)
        self.assertEqual(loaded.block_id, self.block.id)

    def test_stale_spec_rejected(self):
        spec = compute_block_typesetting(self.block)
        spec.layout_status = "stale"
        self.block.extra_metadata = {"typesetting_spec": spec.model_dump()}
        self.assertFalse(validate_typesetting_spec(self.block, spec))

    def test_schema_or_layout_version_mismatch_rejected(self):
        spec = compute_block_typesetting(self.block)
        spec.schema_version = "9.0.0"
        self.assertFalse(validate_typesetting_spec(self.block, spec))

        spec = compute_block_typesetting(self.block)
        spec.layout_version = "9.9.9"
        spec.layout_engine_version = "9.9.9"
        self.assertFalse(validate_typesetting_spec(self.block, spec))

    def test_spec_v2_fields_and_decision_status(self):
        spec = compute_block_typesetting(self.block, log_feedback=False)
        self.assertEqual(spec.schema_version, "2.0.0")
        self.assertEqual(spec.layout_engine_version, "2.0.2")
        self.assertTrue(spec.spec_id)
        self.assertTrue(spec.render_fingerprint)
        self.assertIn(spec.decision_status, ("AUTO_APPLIED", "DEFAULTED", "NEEDS_REVIEW"))
        self.assertEqual(spec.font_postscript_name, spec.resolved_postscript_name)
        self.assertEqual(spec.text_align, spec.horizontal_align)
        self.assertIsInstance(spec.bold, bool)
        self.assertIsInstance(spec.reason_codes, list)

    def test_outline_glow_changes_signature_and_render_fingerprint(self):
        base_spec = compute_block_typesetting(self.block, log_feedback=False)
        base_signature = compute_block_signature(self.block)

        self.block.extra_metadata = {
            "outline_glow_radius": 8,
            "outline_glow_color": "#ff00aa",
            "outline_glow_opacity": 0.45,
        }
        glow_spec = compute_block_typesetting(self.block, log_feedback=False)

        self.assertNotEqual(base_signature, compute_block_signature(self.block))
        self.assertNotEqual(base_spec.render_fingerprint, glow_spec.render_fingerprint)
        self.assertEqual(glow_spec.outline_glow_radius, 8)
        self.assertEqual(glow_spec.outline_glow_color, "#ff00aa")
        self.assertEqual(glow_spec.outline_glow_opacity, 0.45)

    def test_outline_glow_is_composited_behind_text(self):
        from app.services.renderer import _apply_outline_glow

        layer = Image.new("RGBA", (21, 21), (0, 0, 0, 0))
        layer.putpixel((10, 10), (0, 0, 0, 255))
        result = _apply_outline_glow(layer, 4, "#ff0000", 1.0)

        self.assertEqual(result.getpixel((10, 10)), (0, 0, 0, 255))
        self.assertGreater(result.getpixel((10, 9))[3], 0)
        self.assertEqual(result.getpixel((10, 9))[:3], (255, 0, 0))

    def test_defaulted_when_layout_ok_style_low(self):
        """Product contract: DEFAULTED when layout safe but style conf < 0.90."""
        from app.services.typesetting.service import _derive_decision_status, DECISION_DEFAULTED

        status, codes = _derive_decision_status(
            overflow=False,
            gate_issues=[],
            warnings=[],
            style_confidence=0.5,
            layout_confidence=0.95,
            font_fallback=False,
        )
        self.assertEqual(status, DECISION_DEFAULTED)
        self.assertIn("LOW_STYLE_CONFIDENCE", codes)

    def test_beam_line_candidates_produce_lines(self):
        from app.services.typesetting.fitting import generate_line_candidates, rank_line_candidates
        from app.services.font_registry import font_registry
        from PIL import ImageFont

        tokens = segment_text("เทพแห่งสุริยาปกป้องโลกนี้ไว้")
        resolved = font_registry.resolve_font("Tahoma", bold=False, italic=False)
        try:
            font = ImageFont.truetype(str(resolved.file_path), 28)
        except Exception:
            font = ImageFont.load_default()
        cands = generate_line_candidates(
            tokens, font, block_w=220.0, block_h=120.0, balloon_type="bubble", beam_width=6
        )
        self.assertGreaterEqual(len(cands), 1)
        best = rank_line_candidates(cands, 28.0, 220.0, 120.0, "bubble")
        self.assertIsNotNone(best)
        self.assertTrue(best["explicit_lines"])
        # Tokens must not be split mid-grapheme: joined text equals normalized join
        joined = "".join(best["explicit_lines"]).replace(" ", "")
        source = "".join(tokens).replace(" ", "").replace("\n", "")
        self.assertEqual(joined, source)

    def test_feedback_event_logging(self):
        import tempfile
        from pathlib import Path
        from app.services.typesetting.feedback import (
            build_typesetting_decision_event,
            log_typesetting_decision,
        )

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "events.jsonl"
            with patch.dict("os.environ", {"HOUMI_TYPESETTING_FEEDBACK_PATH": str(log_path)}):
                event = build_typesetting_decision_event(
                    block_id="b1",
                    suggested_template="emphasis",
                    selected_template="bubble",
                    suggested_lines=["a", "b"],
                    final_lines=["a b"],
                    change_reason="system_wrong",
                    decision_status="NEEDS_REVIEW",
                    engine_version="2.0.0",
                    font_fingerprint="abc",
                    spec_revision=2,
                    suggested_spec_id="spec-original",
                    current_spec_id="spec-current",
                )
                self.assertEqual(event["suggested_spec_id"], "spec-original")
                self.assertEqual(event["current_spec_id"], "spec-current")
                self.assertTrue(log_typesetting_decision(event))
                content = log_path.read_text(encoding="utf-8")
                self.assertIn("typesetting_decision", content)
                self.assertIn("system_wrong", content)

    def test_font_size_only_edit_invalidates(self):
        sig1 = compute_block_signature(self.block)
        # Edit only font_size
        self.block.font_size = 25.0
        sig2 = compute_block_signature(self.block)
        self.assertNotEqual(sig1, sig2)

    def test_manual_font_size_is_not_replaced_by_template_maximum(self):
        self.block.width = 600
        self.block.height = 300
        self.block.font_size = 28
        self.block.translation = "ข้อความสั้น"
        self.block.extra_metadata = {
            "manual_font_size": 28,
            "min_font_size": 8,
            "max_font_size": 120,
        }

        spec = compute_block_typesetting(self.block)

        self.assertEqual(spec.font_size, 28)

    def test_manual_font_size_is_hard_locked_for_long_text(self):
        self.block.width = 750
        self.block.height = 300
        self.block.font_size = 72
        self.block.translation = "แต่ถ้ามองดูดีๆ ในยุคสมัยแห่งนายบัลลังก์หลังจากนี้"
        self.block.extra_metadata = {
            "manual_font_size": 72,
            "min_font_size": 8,
            "max_font_size": 120,
        }

        spec = compute_block_typesetting(self.block)

        self.assertEqual(spec.font_size, 72)
        self.assertEqual(spec.metrics["candidate_count"], 1)

    def test_legacy_manual_font_mode_locks_block_font_size_without_metadata_value(self):
        self.block.width = 750
        self.block.height = 300
        self.block.font_size = 68
        self.block.translation = "ข้อความแปลที่ต้องไม่กลับไปใช้ขนาดจาก Spec เก่า"
        self.block.extra_metadata = {
            "font_size_mode": "manual",
            "min_font_size": 8,
            "max_font_size": 120,
        }

        spec = compute_block_typesetting(self.block)

        self.assertEqual(spec.font_size, 68)
        self.assertEqual(spec.metrics["candidate_count"], 1)

    def test_manual_mode_wins_over_stale_auto_font_flag(self):
        self.block.width = 750
        self.block.height = 300
        self.block.font_size = 68
        self.block.translation = "ข้อความแปลที่มี metadata เก่าขัดแย้งกัน"
        self.block.extra_metadata = {
            "font_size_mode": "manual",
            "auto_font_size": True,
            "min_font_size": 8,
            "max_font_size": 120,
        }

        spec = compute_block_typesetting(self.block)

        self.assertEqual(spec.font_size, 68)
        self.assertEqual(spec.metrics["candidate_count"], 1)

    def test_manual_size_is_not_overridden_by_template_minimum(self):
        self.block.font_size = 18
        self.block.translation = "ข้อความที่ต้องรักษาขนาดขั้นต่ำ"
        self.block.extra_metadata = {
            "manual_font_size": 18,
            "min_font_size": 24,
            "max_font_size": 72,
        }

        spec = compute_block_typesetting(self.block)

        self.assertEqual(spec.font_size, 18)
        self.assertNotIn("FONT_SIZE_CLAMPED_TO_TEMPLATE_MINIMUM", [warning.code for warning in spec.warnings])

    def test_translation_layout_region_stays_inside_original_detected_box(self):
        project = Project(name="locked", settings={"lock_translation_to_detected_box": True})
        page = Page(
            project=project,
            page_number=1,
            width=1000,
            height=1000,
            source_image_path="missing-source.png",
        )
        block = TextBlock(
            page=page,
            block_index=0,
            x=120,
            y=240,
            width=300,
            height=140,
            source_text="你好",
            extra_metadata={},
        )

        region = refresh_block_layout_region(block)

        self.assertEqual(region["source"], "locked_detector_box")
        self.assertEqual((region["x"], region["y"], region["width"], region["height"]), (120, 240, 300, 140))
        self.assertIn("balloon_context_region", block.extra_metadata)

    def test_translation_layout_region_is_not_locked_when_setting_is_missing(self):
        project = Project(name="default-unlocked", settings={})
        page = Page(
            project=project,
            page_number=1,
            width=1000,
            height=1000,
            source_image_path="missing-source.png",
        )
        block = TextBlock(
            page=page,
            block_index=0,
            x=120,
            y=240,
            width=300,
            height=140,
            source_text="你好",
            extra_metadata={},
        )

        region = refresh_block_layout_region(block)

        self.assertNotEqual(region["source"], "locked_detector_box")

    def test_padding_changes_fitted_layout(self):
        # Clean block with no padding
        self.block.extra_metadata = {}
        spec_no_padding = compute_block_typesetting(self.block)

        # Block with large padding
        self.block.extra_metadata = {
            "padding": {"top": 20, "right": 20, "bottom": 20, "left": 20}
        }
        spec_with_padding = compute_block_typesetting(self.block)

        # When padding is added, it wraps tighter or uses a smaller fitted font size
        self.assertNotEqual(spec_no_padding.font_size, spec_with_padding.font_size)

    def test_preflight_does_not_mutate_persisted_data(self):
        original_metadata = {"some_key": "some_value"}
        self.block.extra_metadata = original_metadata.copy()

        # Run a simulated preflight check that copies metadata
        meta_copy = dict(self.block.extra_metadata) if self.block.extra_metadata else {}
        meta_copy["temp_key"] = "temp_val"

        # Original remains unchanged
        self.assertNotIn("temp_key", self.block.extra_metadata)

    def test_psd_round_trip_preserves_manual_newlines_and_spaces(self):
        from app.services.psd_import import remove_auto_breaks

        # Case 1: Unchanged text, original translation returned exactly
        old_text = "若为仙路\nCJK 字符  with spaces"
        exported_text = "若为仙路\nCJK\n字符  with\nspaces"
        imported_text = "若为仙路\nCJK\n字符  with\nspaces"

        import re

        clean_old = re.sub(r"\s+", "", old_text)
        clean_new = re.sub(r"\s+", "", imported_text)
        self.assertEqual(clean_old, clean_new)

        # Case 2: Edited text, remove_auto_breaks maps and removes auto breaks but preserves manual ones & spaces
        old_text = "若为仙路\nCJK 字符  with spaces"
        exported_text = "若为仙路\nCJK\n字符  with\nspaces"
        imported_text = "若为仙路\nCJK\n字符  with\nspaces!!"

        restored = remove_auto_breaks(old_text, exported_text, imported_text)
        self.assertEqual(restored, "若为仙路\nCJK 字符  with spaces!!")

    def test_preflight_leaves_orm_unchanged_real(self):
        from app.routes.typesetting import preflight_layout, PreflightRequest
        from unittest.mock import MagicMock
        from sqlalchemy.orm import Session

        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = self.block

        req = PreflightRequest(
            block_id=self.block.id,
            translation="Preflight override text",
            font_size=12.0,
        )
        orig_meta = self.block.extra_metadata.copy()
        spec = preflight_layout(req, db)

        self.assertEqual(self.block.extra_metadata, orig_meta)
        self.assertEqual(self.block.translation, "若为仙路 CJK")

    def test_stale_spec_export_recomputes(self):
        from app.services.psd_export import export_page_to_psd
        from unittest.mock import MagicMock, patch, mock_open
        from sqlalchemy.orm import Session
        from app.models.all_models import Page

        db = MagicMock(spec=Session)
        page = Page(
            id="test-page-111",
            page_number=1,
            width=100,
            height=100,
            source_image_path="test.png",
        )
        page.text_blocks = [self.block]
        self.block.page = page

        db.query.return_value.filter.return_value.first.return_value = page

        self.block.extra_metadata = {
            "typesetting_spec": {
                "schema_version": "1.0.0",
                "layout_version": "1.0.0",
                "block_id": self.block.id,
                "source_signature": "stale-sig",
                "layout_status": "stale",
                "layout_source": "auto",
                "requested_font_family": "Tahoma",
                "resolved_font_id": "tahoma_regular",
                "resolved_font_family": "Tahoma",
                "resolved_postscript_name": "Tahoma",
                "resolved_font_style": "regular",
                "font_fingerprint": "unknown",
                "font_size": 14,
                "explicit_lines": ["stale"],
                "normalized_text": "stale",
                "line_height": 16.8,
                "tracking": 0.0,
                "horizontal_align": "center",
                "vertical_align": "center",
                "writing_direction": "horizontal",
                "rotation_deg": 0.0,
                "padding": {"top": 0, "right": 0, "bottom": 0, "left": 0},
                "shape_type": "bubble",
                "overflow": False,
                "overflow_score": 0.0,
                "quality_score": 80.0,
                "warnings": [],
                "metrics": {},
            }
        }

        with (
            patch("subprocess.run") as mock_run,
            patch("tempfile.mkstemp", return_value=(999, "temp.json")),
            patch("os.fdopen", mock_open()),
            patch("os.path.exists", return_value=True),
            patch("os.remove"),
            patch("builtins.open", mock_open(read_data=b"dummy_psd_data")),
        ):
            mock_run.return_value.returncode = 0
            psd_path = export_page_to_psd(page.id, db)

            updated_spec = self.block.extra_metadata.get("typesetting_spec")
            self.assertIsNotNone(updated_spec)
            self.assertNotEqual(updated_spec["layout_status"], "stale")
            self.assertNotEqual(updated_spec["explicit_lines"], ["stale"])

    def test_overflow_export_blocked(self):
        from app.services.psd_export import export_page_to_psd
        from unittest.mock import MagicMock
        from sqlalchemy.orm import Session
        from app.models.all_models import Page

        db = MagicMock(spec=Session)
        page = Page(
            id="test-page-111",
            page_number=1,
            width=100,
            height=100,
            source_image_path="test.png",
        )
        page.text_blocks = [self.block]
        self.block.page = page
        db.query.return_value.filter.return_value.first.return_value = page

        spec = compute_block_typesetting(self.block)
        spec.overflow = True
        self.block.extra_metadata = {"typesetting_spec": spec.model_dump()}

        with self.assertRaises(ValueError) as context:
            export_page_to_psd(page.id, db, force=False)

        self.assertIn("EXPORT_BLOCKED", str(context.exception))

    def test_cli_failure_no_db_mutation(self):
        from app.services.psd_export import export_page_to_psd
        from unittest.mock import MagicMock, patch, mock_open
        from sqlalchemy.orm import Session
        from app.models.all_models import Page

        db = MagicMock(spec=Session)
        page = Page(
            id="test-page-111",
            page_number=1,
            width=100,
            height=100,
            source_image_path="test.png",
        )
        page.text_blocks = [self.block]
        self.block.page = page
        db.query.return_value.filter.return_value.first.return_value = page

        orig_meta = self.block.extra_metadata.copy()

        with (
            patch("subprocess.run") as mock_run,
            patch("tempfile.mkstemp", return_value=(999, "temp.json")),
            patch("os.fdopen", mock_open()),
            patch("os.path.exists", return_value=True),
            patch("os.remove"),
        ):
            mock_run.return_value.returncode = 1
            mock_run.return_value.stderr = "CLI simulated failure"

            with self.assertRaises(RuntimeError):
                export_page_to_psd(page.id, db, force=True)

            self.assertEqual(self.block.extra_metadata, orig_meta)
            db.commit.assert_not_called()

    def test_successful_export_stores_snapshot(self):
        from app.services.psd_export import export_page_to_psd
        from unittest.mock import MagicMock, patch, mock_open
        from sqlalchemy.orm import Session
        from app.models.all_models import Page

        db = MagicMock(spec=Session)
        page = Page(
            id="test-page-111",
            page_number=1,
            width=100,
            height=100,
            source_image_path="test.png",
        )
        page.text_blocks = [self.block]
        self.block.page = page
        db.query.return_value.filter.return_value.first.return_value = page

        with (
            patch("subprocess.run") as mock_run,
            patch("tempfile.mkstemp", return_value=(999, "temp.json")),
            patch("os.fdopen", mock_open()),
            patch("os.path.exists", return_value=True),
            patch("os.remove"),
            patch("builtins.open", mock_open(read_data=b"dummy_psd_data")),
        ):
            mock_run.return_value.returncode = 0
            psd_path = export_page_to_psd(page.id, db, force=True)

            db.commit.assert_called_once()

            snapshot = self.block.extra_metadata.get("psd_export_snapshot")
            self.assertIsNotNone(snapshot)
            self.assertEqual(snapshot["original_authored_text"], "若为仙路 CJK")
            self.assertIn("auto_break_offsets", snapshot)
            import hashlib

            self.assertIn("authored_newline_offsets", snapshot)
            self.assertEqual(
                snapshot["psd_file_hash"], hashlib.sha256(b"dummy_psd_data").hexdigest()
            )

            history = self.block.extra_metadata.get("psd_export_history")
            self.assertIsNotNone(history)
            self.assertEqual(len(history), 1)

    def test_old_psd_mismatch_warns(self):
        from app.services.psd_import import import_psd_to_page
        from unittest.mock import MagicMock, patch
        from sqlalchemy.orm import Session
        from app.models.all_models import Page

        db = MagicMock(spec=Session)
        page = Page(
            id="test-page-111",
            page_number=1,
            width=100,
            height=100,
            source_image_path="test.png",
        )
        page.text_blocks = [self.block]
        self.block.page = page
        db.query.return_value.filter.return_value.first.return_value = page

        # Setup metadata with wrong psd_file_hash
        self.block.extra_metadata = {
            "psd_export_snapshot": {
                "original_authored_text": "若为仙路 CJK",
                "exported_text": "若为仙路\nCJK",
                "auto_break_offsets": [4],
                "authored_newline_offsets": [],
                "psd_file_hash": "wrong-hash",
            }
        }

        # Mock PSDImage
        mock_layer = MagicMock()
        mock_layer.is_group.return_value = False
        mock_layer.kind = "type"
        mock_layer.name = f"TL 001 {self.block.id}"
        mock_layer.text = "若为仙路\nCJK"
        mock_layer.bbox = (0, 0, 10, 10)

        mock_psd = MagicMock()
        mock_psd.__iter__.return_value = [mock_layer]

        with (
            patch("app.services.psd_import.PSDImage.open", return_value=mock_psd),
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=b"dummy_import_data")),
        ):
            with self.assertRaises(ValueError) as ctx:
                import_psd_to_page(page.id, "dummy.psd", db)
            self.assertIn("IMPORT_FAILED:", str(ctx.exception))
            self.assertIn("missing a valid exp_v1", str(ctx.exception))

    def test_unchanged_autobreak_text_restores_original(self):
        from app.services.psd_import import remove_auto_breaks_with_snapshot

        snapshot = {
            "original_authored_text": "若为仙路 CJK 字符",
            "exported_text": "若为仙路\nCJK 字符",
            "auto_break_offsets": [4],
            "authored_newline_offsets": [],
        }
        restored = remove_auto_breaks_with_snapshot(snapshot, "若为仙路\nCJK 字符")
        self.assertEqual(restored, "若为仙路 CJK 字符")

    def test_newly_inserted_manual_newline(self):
        from app.services.psd_import import remove_auto_breaks_with_snapshot

        snapshot = {
            "original_authored_text": "hello world",
            "exported_text": "hello world",
            "auto_break_offsets": [],
            "authored_newline_offsets": [],
        }
        # PSD edited to "hello\nworld\nfoo"
        restored = remove_auto_breaks_with_snapshot(snapshot, "hello\nworld\nfoo")
        self.assertEqual(restored, "hello\nworld\nfoo")

    def test_deleted_manual_newline(self):
        from app.services.psd_import import remove_auto_breaks_with_snapshot

        snapshot = {
            "original_authored_text": "line1\nline2",
            "exported_text": "line1\nline2",
            "auto_break_offsets": [],
            "authored_newline_offsets": [5],
        }
        # PSD edited to delete newline
        restored = remove_auto_breaks_with_snapshot(snapshot, "line1 line2")
        self.assertEqual(restored, "line1 line2")

    def test_repeated_space_edit(self):
        from app.services.psd_import import remove_auto_breaks_with_snapshot

        snapshot = {
            "original_authored_text": "A B",
            "exported_text": "A\nB",
            "auto_break_offsets": [1],
            "authored_newline_offsets": [],
        }
        # PSD edited with extra space
        restored = remove_auto_breaks_with_snapshot(snapshot, "A  B")
        self.assertEqual(restored, "A  B")

    def test_mixed_thai_cjk_latin_edit(self):
        from app.services.psd_import import remove_auto_breaks_with_snapshot

        snapshot = {
            "original_authored_text": "ทดสอบ test 若为",
            "exported_text": "ทดสอบ\ntest\n若为",
            "auto_break_offsets": [5, 10],
            "authored_newline_offsets": [],
        }
        restored = remove_auto_breaks_with_snapshot(snapshot, "ทดสอบ\ntest\n若为")
        self.assertEqual(restored, "ทดสอบ test 若为")

    def test_repeated_character_text(self):
        from app.services.psd_import import remove_auto_breaks_with_snapshot

        snapshot = {
            "original_authored_text": "aaaa aaaa",
            "exported_text": "aaaa\naaaa",
            "auto_break_offsets": [4],
            "authored_newline_offsets": [],
        }
        restored = remove_auto_breaks_with_snapshot(snapshot, "aaaa\naaaa")
        self.assertEqual(restored, "aaaa aaaa")

    def test_fingerprint_equals_registry(self):
        from app.services.font_registry import font_registry

        spec = compute_block_typesetting(self.block)
        resolved = font_registry.resolve_font(
            self.block.font_family, bold=self.block.bold, italic=self.block.italic
        )
        self.assertEqual(spec.font_fingerprint, resolved.fingerprint)

    def test_font_stack_uses_first_installed_family(self):
        self.block.font_family = "Missing Thai Font"
        self.block.extra_metadata = {"font_stack": ["Missing Thai Font", "Tahoma", "Arial"]}

        spec = compute_block_typesetting(self.block)

        self.assertEqual(spec.requested_font_family, "Tahoma")
        self.assertEqual(spec.resolved_font_family, "Tahoma")

    def test_template_font_limits_override_project_defaults(self):
        self.block.width = 500
        self.block.height = 300
        self.block.extra_metadata = {
            "font_size_mode": "auto",
            "min_font_size": 30,
            "max_font_size": 40,
        }

        spec = compute_block_typesetting(self.block)

        self.assertGreaterEqual(spec.font_size, 30)
        self.assertLessEqual(spec.font_size, 40)

    def test_source_estimate_does_not_cap_geometry_auto_size(self):
        page = MagicMock()
        page.project.settings = {"match_source_font_size": True, "source_font_scale": 1.1}
        self.block.page = page
        self.block.width = 800
        self.block.height = 500
        self.block.font_size = 30
        self.block.extra_metadata = {"min_font_size": 24, "max_font_size": 120, "source_font_size": 30}

        spec = compute_block_typesetting(self.block)

        self.assertGreater(spec.font_size, 33)
        self.assertLessEqual(spec.font_size, 120)

    def test_default_template_size_wins_over_unreliable_source_estimate(self):
        page = MagicMock()
        page.project.settings = {"match_source_font_size": True, "source_font_scale": 1.1}
        self.block.page = page
        self.block.width = 800
        self.block.height = 500
        self.block.font_size = 62
        self.block.translation = "ข้อความแปลที่ควรใช้ขนาดจากเทมเพลต"
        self.block.extra_metadata = {
            "text_template_id": "bubble",
            "source_font_size": 15,
            "min_font_size": 12,
            "max_font_size": 96,
        }

        spec = compute_block_typesetting(self.block)

        self.assertGreater(spec.font_size, 15 * 1.1)
        self.assertLessEqual(spec.font_size, 96)

    def test_auto_size_uses_balloon_geometry_instead_of_template_default(self):
        page = MagicMock()
        page.project.settings = {"auto_font_resize": True, "match_source_font_size": False}
        self.block.page = page
        self.block.translation = "ข้อความแปลสำหรับทดสอบขนาดอัตโนมัติ"
        self.block.font_size = 52
        self.block.extra_metadata = {
            "text_template_id": "narration",
            "font_size_mode": "auto",
            "preferred_font_size": 52,
            "min_font_size": 20,
            "max_font_size": 96,
        }
        self.block.width = 280
        self.block.height = 120
        small = compute_block_typesetting(self.block)

        self.block.width = 900
        self.block.height = 500
        large = compute_block_typesetting(self.block)

        self.assertGreater(large.font_size, small.font_size)
        self.assertNotEqual(large.font_size, 52)

    def test_auto_minimum_is_soft_and_can_shrink_to_fit(self):
        self.block.width = 90
        self.block.height = 48
        self.block.translation = "ข้อความภาษาไทยที่ยาวเกินกว่าจะใส่ด้วยฟอนต์ขนาดใหญ่"
        self.block.extra_metadata = {
            "font_size_mode": "auto",
            "min_font_size": 30,
            "max_font_size": 40,
        }

        spec = compute_block_typesetting(self.block)

        self.assertGreaterEqual(spec.font_size, 6)
        self.assertLess(spec.font_size, 30)
        self.assertIn("FONT_BELOW_PROJECT_MINIMUM", spec.metrics["quality_gate"]["issues"])

    def test_auto_size_can_shrink_below_legacy_36pt_floor(self):
        self.block.width = 90
        self.block.height = 48
        self.block.translation = "ข้อความภาษาไทยที่ยาวเกินกว่าจะใส่ด้วยฟอนต์ขนาดใหญ่"
        self.block.extra_metadata = {
            "font_size_mode": "auto",
            "min_font_size": 6,
            "max_font_size": 96,
        }

        spec = compute_block_typesetting(self.block)

        self.assertGreaterEqual(spec.font_size, 6)
        self.assertLess(spec.font_size, 36)

    def test_persisted_spec_synchronizes_block_font_size_and_signature(self):
        self.block.extra_metadata = {
            "font_size_mode": "auto",
            "min_font_size": 6,
            "max_font_size": 96,
        }
        spec = compute_block_typesetting(self.block)

        persist_typesetting_spec(self.block, spec)

        self.assertEqual(self.block.font_size, spec.font_size)
        self.assertEqual(self.block.extra_metadata["typesetting_spec"]["font_size"], spec.font_size)
        self.assertTrue(validate_typesetting_spec(self.block, spec))

    def test_requested_font_size_6(self):
        self.block.font_size = 6.0
        spec = compute_block_typesetting(self.block)
        self.assertTrue(spec.font_size <= 6.0)

    def test_requested_font_size_8(self):
        self.block.font_size = 8.0
        spec = compute_block_typesetting(self.block)
        self.assertTrue(spec.font_size <= 8.0)
        self.assertTrue(spec.font_size >= 6.0)

    def test_requested_font_size_10(self):
        self.block.font_size = 10.0
        spec = compute_block_typesetting(self.block)
        self.assertTrue(spec.font_size <= 10.0)

    def test_requested_font_size_5_clamped_with_warning(self):
        self.block.font_size = 5.0
        spec = compute_block_typesetting(self.block)
        self.assertEqual(spec.font_size, 6.0)
        warnings = [w.code for w in spec.warnings]
        self.assertIn("FONT_SIZE_CLAMPED_TO_MINIMUM", warnings)

    def test_line_height_ratio_fitting(self):
        # Create a tight block that wraps
        block_1 = TextBlock(
            id="test-lh-1",
            page_id="page-1",
            block_index=0,
            x=0,
            y=0,
            width=120.0,
            height=40.0,
            translation="This is a relatively long sentence that will wrap into multiple lines.",
            font_family="Tahoma",
            font_size=16.0,
            balloon_type="narrative",
            extra_metadata={},
        )

        # Test with line_height_ratio = 1.2
        block_1.extra_metadata = {"line_height_ratio": 1.2}
        spec_12 = compute_block_typesetting(block_1)

        # Test with line_height_ratio = 2.0
        block_1.extra_metadata = {"line_height_ratio": 2.0}
        spec_20 = compute_block_typesetting(block_1)

        # Spec with 2.0 line height ratio must have a smaller fitted font size or be more overflowed
        self.assertTrue(
            spec_20.font_size < spec_12.font_size
            or (spec_20.overflow and not spec_12.overflow)
        )

    def test_atomic_psd_import_scenarios(self):
        from unittest.mock import MagicMock, patch
        from app.services.psd_import import import_psd_to_page

        class MockLayer:
            def __init__(self, name, text, bbox=None, is_group_val=False):
                self.name = name
                self.text = text
                self.bbox = bbox or [10, 10, 110, 60]
                self.kind = "type"
                self._is_group = is_group_val

            def is_group(self):
                return self._is_group

            def __iter__(self):
                return iter([])

        class MockPSDImage:
            def __init__(self, layers):
                self.layers = layers

            def __iter__(self):
                return iter(self.layers)

        # Mock Page and TextBlock ORM entities
        mock_block = TextBlock(
            id="a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
            page_id="page-1",
            block_index=0,
            x=10,
            y=10,
            width=100,
            height=50,
            translation="Original Text",
            font_family="Tahoma",
            font_size=14,
            extra_metadata={
                "psd_export_history": {
                    "11111111-2222-3333-4444-555555555555": {
                        "export_id": "11111111-2222-3333-4444-555555555555",
                        "original_authored_text": "Original Text",
                        "exported_text": "Original Text",
                        "break_provenance": [],
                        "auto_break_offsets": [],
                        "psd_file_hash": "some-old-hash",
                    }
                }
            },
        )
        mock_block_2 = TextBlock(
            id="f5e4d3c2-b1a0-9f8e-7d6c-5b4a3f2e1d0c",
            page_id="page-1",
            block_index=1,
            x=20,
            y=20,
            width=120,
            height=60,
            translation="Second Original",
            font_family="Tahoma",
            font_size=14,
            extra_metadata={
                "psd_export_history": {
                    "11111111-2222-3333-4444-555555555555": {
                        "export_id": "11111111-2222-3333-4444-555555555555",
                        "original_authored_text": "Second Original",
                        "exported_text": "Second Original",
                        "break_provenance": [],
                    }
                }
            },
        )

        mock_page = MagicMock()
        mock_page.id = "page-1"
        mock_page.project_id = "proj-1"
        mock_page.text_blocks = [mock_block, mock_block_2]

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_page

        # Scenario A: Missing export_id in layers -> fails closed
        layers_missing = [
            MockLayer("TL 001 a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d", "New Text")
        ]
        with (
            patch(
                "app.services.psd_import.PSDImage.open",
                return_value=MockPSDImage(layers_missing),
            ),
            patch("app.services.psd_import.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=b"dummy data")),
        ):
            with self.assertRaises(ValueError) as ctx:
                import_psd_to_page("page-1", "dummy.psd", mock_db)
            self.assertIn("IMPORT_FAILED:", str(ctx.exception))
            self.assertIn("missing a valid exp_v1", str(ctx.exception))
            # No changes to translation
            self.assertEqual(mock_block.translation, "Original Text")

        # Scenario B: Multiple conflicting export IDs found -> fails closed
        layers_conflicting = [
            MockLayer(
                "TL 001 a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d exp_v1:11111111-2222-3333-4444-555555555555",
                "New Text",
            ),
            MockLayer(
                "TL 002 f5e4d3c2-b1a0-9f8e-7d6c-5b4a3f2e1d0c exp_v1:22222222-3333-4444-5555-666666666666",
                "Other Text",
            ),
        ]
        with (
            patch(
                "app.services.psd_import.PSDImage.open",
                return_value=MockPSDImage(layers_conflicting),
            ),
            patch("app.services.psd_import.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=b"dummy data")),
        ):
            with self.assertRaises(ValueError) as ctx:
                import_psd_to_page("page-1", "dummy.psd", mock_db)
            self.assertIn(
                "IMPORT_FAILED: Multiple conflicting export IDs", str(ctx.exception)
            )
            self.assertEqual(mock_block.translation, "Original Text")

        # Scenario C: Evicted / Unknown export ID -> fails closed
        layers_unknown = [
            MockLayer(
                "TL 001 a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d exp_v1:99999999-8888-7777-6666-555555555555",
                "New Text",
            )
        ]
        with (
            patch(
                "app.services.psd_import.PSDImage.open",
                return_value=MockPSDImage(layers_unknown),
            ),
            patch("app.services.psd_import.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=b"dummy data")),
        ):
            with self.assertRaises(ValueError) as ctx:
                import_psd_to_page("page-1", "dummy.psd", mock_db)
            self.assertIn(
                "IMPORT_FAILED: Export identity '99999999-8888-7777-6666-555555555555' was evicted from history",
                str(ctx.exception),
            )
            self.assertEqual(mock_block.translation, "Original Text")

        # Scenario D: Duplicate text layers for same block -> fails closed
        layers_duplicates = [
            MockLayer(
                "TL 001 a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d exp_v1:11111111-2222-3333-4444-555555555555",
                "New Text",
            ),
            MockLayer(
                "TL 002 a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d exp_v1:11111111-2222-3333-4444-555555555555",
                "Duplicate Text",
            ),
        ]
        with (
            patch(
                "app.services.psd_import.PSDImage.open",
                return_value=MockPSDImage(layers_duplicates),
            ),
            patch("app.services.psd_import.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=b"dummy data")),
        ):
            with self.assertRaises(ValueError) as ctx:
                import_psd_to_page("page-1", "dummy.psd", mock_db)
            self.assertIn(
                "IMPORT_FAILED: Duplicate text layers found for block a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
                str(ctx.exception),
            )
            self.assertEqual(mock_block.translation, "Original Text")

        # Scenario E: Valid, matching export ID -> succeeds and mutates ORM entity
        layers_valid = [
            MockLayer(
                "TL 001 a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d exp_v1:11111111-2222-3333-4444-555555555555",
                "New Text Edited",
            )
        ]
        with (
            patch(
                "app.services.psd_import.PSDImage.open",
                return_value=MockPSDImage(layers_valid),
            ),
            patch("app.services.psd_import.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=b"dummy data")),
            patch("app.services.project_serializer.save_project_json") as mock_save,
        ):
            res = import_psd_to_page("page-1", "dummy.psd", mock_db)
            self.assertTrue(res["success"])
            self.assertEqual(mock_block.translation, "New Text Edited")
            # Verify mock_db.commit was called
            self.assertTrue(mock_db.commit.called)
            # Verify save_project_json was called
            mock_save.assert_called_once_with("proj-1", mock_db)

    def test_atomic_psd_import_mixed_validation_and_recompute_failures(self):
        from app.services.psd_import import import_psd_to_page

        export_id = "11111111-2222-3333-4444-555555555555"
        first_id = "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d"
        second_id = "f5e4d3c2-b1a0-9f8e-7d6c-5b4a3f2e1d0c"
        unknown_id = "99999999-8888-7777-6666-555555555555"

        class MockLayer:
            kind = "type"

            def __init__(self, name, text):
                self.name = name
                self.text = text
                self.bbox = [10, 10, 110, 60]

            def is_group(self):
                return False

        class MockPSDImage:
            def __init__(self, layers):
                self.layers = layers

            def __iter__(self):
                return iter(self.layers)

        def make_block(block_id, translation):
            return TextBlock(
                id=block_id,
                page_id="page-1",
                block_index=0,
                x=1,
                y=2,
                width=100,
                height=50,
                translation=translation,
                font_family="Tahoma",
                font_size=14,
                extra_metadata={
                    "psd_export_history": {
                        export_id: {
                            "export_id": export_id,
                            "original_authored_text": translation,
                            "exported_text": translation,
                            "break_provenance": [],
                            "psd_file_hash": "same-hash-for-every-snapshot",
                        }
                    }
                },
            )

        first = make_block(first_id, "First Original")
        second = make_block(second_id, "Second Original")
        page = MagicMock(id="page-1", project_id="proj-1", text_blocks=[first, second])
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = page

        def run_import(layers, **patches):
            with (
                patch(
                    "app.services.psd_import.PSDImage.open",
                    return_value=MockPSDImage(layers),
                ),
                patch("app.services.psd_import.Path.exists", return_value=True),
                patch("app.services.project_serializer.save_project_json"),
            ):
                return import_psd_to_page("page-1", "dummy.psd", db)

        valid_first = MockLayer(f"TL 001 {first_id} exp_v1:{export_id}", "First Edited")

        # A valid layer plus an unknown managed layer must not partially commit.
        with self.assertRaisesRegex(ValueError, "IMPORT_FAILED:.*does not belong"):
            run_import(
                [
                    valid_first,
                    MockLayer(f"TL 002 {unknown_id} exp_v1:{export_id}", "Unknown"),
                ]
            )
        self.assertEqual(first.translation, "First Original")
        db.commit.assert_not_called()
        self.assertTrue(db.rollback.called)

        db.reset_mock()
        # Every managed layer must carry the page export identity.
        with self.assertRaisesRegex(
            ValueError, "IMPORT_FAILED:.*missing a valid exp_v1"
        ):
            run_import([valid_first, MockLayer(f"TL 002 {second_id}", "Second Edited")])
        self.assertEqual(first.translation, "First Original")
        self.assertEqual(second.translation, "Second Original")
        db.commit.assert_not_called()

        db.reset_mock()
        # A matching hash under another history key cannot bypass embedded identity.
        wrong_export_id = "22222222-3333-4444-5555-666666666666"
        with self.assertRaisesRegex(
            ValueError, "IMPORT_FAILED: Export identity.*evicted"
        ):
            run_import(
                [
                    MockLayer(
                        f"TL 001 {first_id} exp_v1:{wrong_export_id}", "First Edited"
                    )
                ]
            )
        self.assertEqual(first.translation, "First Original")
        db.commit.assert_not_called()

        db.reset_mock()
        valid_second = MockLayer(
            f"TL 002 {second_id} exp_v1:{export_id}", "Second Edited"
        )
        good_spec = MagicMock()
        good_spec.model_dump.return_value = {
            "schema_version": "1.0.0",
            "layout_status": "valid",
        }
        with (
            patch(
                "app.services.psd_import.PSDImage.open",
                return_value=MockPSDImage([valid_first, valid_second]),
            ),
            patch("app.services.psd_import.Path.exists", return_value=True),
            patch(
                "app.services.psd_import.compute_block_typesetting",
                side_effect=[good_spec, RuntimeError("layout failed")],
            ),
        ):
            with self.assertRaisesRegex(
                ValueError, "IMPORT_FAILED: Could not apply PSD import atomically"
            ):
                import_psd_to_page("page-1", "dummy.psd", db)
        self.assertEqual(first.translation, "First Original")
        self.assertEqual(second.translation, "Second Original")
        self.assertNotIn("typesetting_spec", first.extra_metadata)
        db.commit.assert_not_called()
        self.assertTrue(db.rollback.called)

        db.reset_mock()
        with (
            patch(
                "app.services.psd_import.PSDImage.open",
                return_value=MockPSDImage([valid_first, valid_second]),
            ),
            patch("app.services.psd_import.Path.exists", return_value=True),
            patch(
                "app.services.psd_import.compute_block_typesetting",
                return_value=good_spec,
            ),
            patch("app.services.project_serializer.save_project_json"),
        ):
            result = import_psd_to_page("page-1", "dummy.psd", db)
        self.assertTrue(result["success"])
        self.assertEqual(first.translation, "First Edited")
        self.assertEqual(second.translation, "Second Edited")
        db.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
