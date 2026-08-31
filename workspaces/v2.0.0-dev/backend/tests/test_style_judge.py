import json
import unittest
from unittest.mock import patch

from app.models.all_models import TextBlock, Page, Project
from app.services.typesetting.style_judge import (
    judge_style,
    apply_style_descriptor_to_block,
    judge_page_styles_batch_ai,
)
from app.services.typesetting import compute_block_typesetting
from app.services.typesetting.parity import semantic_parity, geometry_parity, build_export_view_from_spec


class TestStyleJudgeV1(unittest.TestCase):
    def _block(self, **kwargs):
        defaults = dict(
            id="sj-1",
            page_id="p1",
            block_index=0,
            x=10,
            y=10,
            width=200,
            height=80,
            source_text="hello",
            translation="สวัสดีครับ",
            font_family="Tahoma",
            font_size=24,
            bold=False,
            italic=False,
            text_direction="horizontal",
            text_align="center",
            balloon_type="bubble",
            color_hex="#111111",
            extra_metadata={},
        )
        defaults.update(kwargs)
        return TextBlock(**defaults)

    def test_dialogue_default_bubble(self):
        d = judge_style(self._block())
        # Semantic role id == Font Template id
        self.assertEqual(d.role, "bubble")
        self.assertEqual(d.suggested_template, "bubble")
        self.assertTrue(0.0 < d.confidence <= 1.0)

    def test_emphasis_from_exclamation(self):
        d = judge_style(self._block(translation="หยุดนะ!!!", balloon_type="bubble"))
        self.assertEqual(d.role, "emphasis")
        self.assertIn("MULTI_EXCLAMATION", d.reason_codes)
        self.assertEqual(d.suggested_template, "emphasis")

    def test_sfx_from_detector(self):
        d = judge_style(self._block(translation="ดง", balloon_type="sfx", width=60, height=120))
        self.assertEqual(d.role, "sfx")
        self.assertEqual(d.suggested_template, "sfx")

    def test_narration_wide_box(self):
        d = judge_style(
            self._block(
                translation="ในขณะนั้น ท้องฟ้ามืดครึ้ม",
                balloon_type="narrative",
                width=400,
                height=50,
            )
        )
        self.assertEqual(d.role, "narration")
        self.assertEqual(d.suggested_template, "narration")

    def test_apply_high_confidence_template(self):
        block = self._block(translation="หยุดนะ!!!")
        d = judge_style(block)
        # Explicit override path: caller forces apply with conf above threshold
        d.confidence = 0.95
        d.suggested_template = "emphasis"
        d.reason_codes = [c for c in d.reason_codes if c != "HEURISTIC_UNCALIBRATED"]
        summary = apply_style_descriptor_to_block(
            block, d, apply_template=True, confidence_auto_threshold=0.90
        )
        self.assertTrue(summary["applied"])
        self.assertEqual(block.extra_metadata.get("text_template_id"), "emphasis")
        self.assertTrue(block.bold)

    def test_batch_ai_selects_custom_client_preset_and_sets_geometry_fit_ceiling(self):
        block = self._block(
            width=260,
            height=100,
            translation="เบาเสียงหน่อยนะ",
        )
        settings = {
            "text_templates": {
                "client_soft_voice": {
                    "name": "เสียงกระซิบของลูกค้า",
                    "semantic_tag": "กระซิบอย่างอ่อนโยน",
                    "balloon_type": "bubble",
                    "font_stack": ["Missing Client Font", "Tahoma"],
                    "font_size": 40,
                    "min_font_size": 12,
                    "max_font_size": 72,
                    "auto_font_size": True,
                    "italic": True,
                },
                "client_impact": {
                    "name": "เสียงตะโกนของลูกค้า",
                    "semantic_tag": "ตะโกนรุนแรง",
                    "balloon_type": "emphasis",
                    "font_stack": ["Impact"],
                    "font_size": 64,
                    "min_font_size": 16,
                    "max_font_size": 110,
                    "auto_font_size": True,
                    "bold": True,
                },
            }
        }
        response = json.dumps({
            str(block.id): {
                "template_id": "client_soft_voice",
                "role": "whisper",
                "font_size_scale": 1.15,
                "confidence": 0.97,
                "reason": "บทพูดเบาในบอลลูนขนาดกลาง",
            }
        }, ensure_ascii=False)

        with patch("app.services.ocr._run_gemini_command", return_value=(response, True)) as ai:
            descriptors = judge_page_styles_batch_ai([block], project_settings=settings, page_height=1400)

        descriptor = descriptors[str(block.id)]
        self.assertEqual(descriptor.suggested_template, "client_soft_voice")
        self.assertEqual(descriptor.font_size_scale, 1.15)
        self.assertEqual(descriptor.font_size_target, 46.0)
        prompt = ai.call_args.args[0]
        self.assertIn("client_soft_voice", prompt)
        self.assertIn("Missing Client Font", prompt)
        self.assertIn('"geometry"', prompt)

        result = apply_style_descriptor_to_block(
            block,
            descriptor,
            project_settings=settings,
            apply_template=True,
            confidence_auto_threshold=0.90,
        )
        self.assertTrue(result["applied"])
        self.assertEqual(block.extra_metadata["font_stack"], ["Missing Client Font", "Tahoma"])
        self.assertEqual(block.extra_metadata["ai_font_size_target"], 46.0)

        spec = compute_block_typesetting(block, log_feedback=False)
        self.assertLessEqual(spec.font_size, 46.0)
        self.assertEqual(spec.requested_font_family, "Tahoma")

    def test_default_judge_confidence_capped_below_auto_apply(self):
        d = judge_style(self._block(translation="หยุดนะ!!!"))
        self.assertLess(d.confidence, 0.90)
        self.assertIn("HEURISTIC_UNCALIBRATED", d.reason_codes)

    def test_low_confidence_does_not_auto_apply(self):
        block = self._block()
        d = judge_style(block)
        d.confidence = 0.4
        d.suggested_template = "emphasis"
        summary = apply_style_descriptor_to_block(
            block, d, apply_template=True, confidence_auto_threshold=0.90
        )
        self.assertFalse(summary["applied"])
        self.assertEqual(summary["decision"], "deferred_low_confidence")
        self.assertNotEqual(block.extra_metadata.get("text_template_id"), "emphasis")

    def test_compute_embeds_style_descriptor(self):
        block = self._block(translation="ระวัง!!!")
        orig_meta = dict(block.extra_metadata or {})
        spec = compute_block_typesetting(block, log_feedback=False)
        # compute must not mutate block metadata (side-effect free)
        self.assertEqual(block.extra_metadata or {}, orig_meta)
        self.assertIsNotNone(spec.metrics.get("style_descriptor"))
        self.assertTrue(spec.reason_codes)
        self.assertEqual(spec.schema_version, "2.0.0")

    def test_suggest_only_does_not_claim_template_was_applied(self):
        block = self._block(
            translation="หยุดนะ!!!",
            extra_metadata={
                "layout_region": {
                    "x": 10,
                    "y": 10,
                    "width": 200,
                    "height": 80,
                    "shape": "bubble",
                    "source": "manual",
                    "confidence": 1.0,
                }
            },
        )
        spec = compute_block_typesetting(block, log_feedback=False)
        descriptor = spec.metrics["style_descriptor"]
        self.assertEqual(descriptor["suggested_template"], "emphasis")
        self.assertIsNone(spec.template_id)
        self.assertFalse(spec.bold)

        from app.services.typesetting.feedback import log_decision_from_spec

        with patch("app.services.typesetting.feedback.log_typesetting_decision"):
            event = log_decision_from_spec(spec, change_reason="defaulted")
        self.assertEqual(event["suggested_template"], "emphasis")
        self.assertIsNone(event["selected_template"])

    def test_detector_provenance_is_distinct_from_template_role(self):
        block = self._block(
            balloon_type="narrative",
            extra_metadata={
                "detected_balloon_type": "bubble",
                "template_balloon_type": "narrative",
            },
        )

        descriptor = judge_style(block)

        # role is template id; detector class still from detected_balloon_type
        self.assertEqual(descriptor.role, "bubble")
        self.assertEqual(descriptor.suggested_template, "bubble")
        self.assertIn("DETECTOR_BUBBLE", descriptor.reason_codes)
        self.assertNotIn("DETECTOR_NARRATIVE", descriptor.reason_codes)

    def test_imported_semantic_tag_is_not_style_judge_evidence(self):
        block = self._block(
            translation="ได้รับภารกิจใหม่",
            extra_metadata={
                "semantic_role": "system",
                "semantic_role_source": "ai_translation_import_tag",
                "semantic_role_confidence": 1.0,
            },
        )

        descriptor = judge_style(block)

        # Import tag must not force Style Judge role; heuristics only
        self.assertEqual(descriptor.role, "bubble")
        self.assertNotIn("AI_IMPORT_TAG_SYSTEM", descriptor.reason_codes)
        self.assertLess(descriptor.confidence, 0.90)


class TestParityHelpers(unittest.TestCase):
    def test_semantic_and_geometry_match(self):
        block = TextBlock(
            id="p-1",
            page_id="pg",
            block_index=0,
            x=100,
            y=200,
            width=300,
            height=150,
            translation="ทดสอบบรรทัด",
            font_family="Tahoma",
            font_size=20,
            color_hex="#112233",
            bold=True,
            italic=False,
            text_align="center",
            balloon_type="bubble",
            extra_metadata={},
        )
        spec = compute_block_typesetting(block, log_feedback=False)
        view = build_export_view_from_spec(spec)
        ok, issues = semantic_parity(spec, view)
        self.assertTrue(ok, issues)
        ok_g, g_issues = geometry_parity(spec, view)
        self.assertTrue(ok_g, g_issues)

    def test_semantic_detects_line_mismatch(self):
        a = {"explicit_lines": ["a", "b"], "font_size": 12, "font_postscript_name": "X"}
        b = {"explicit_lines": ["a"], "font_size": 12, "font_postscript_name": "X"}
        ok, issues = semantic_parity(a, b)
        self.assertFalse(ok)
        self.assertTrue(any("explicit_lines" in i or "line_count" in i for i in issues))

    def test_semantic_detects_tracking_mismatch(self):
        a = {
            "explicit_lines": ["ไทย"],
            "font_size": 24,
            "line_height": 28.8,
            "tracking": 0,
            "font_postscript_name": "Tahoma",
        }
        b = {**a, "tracking": 50}
        ok, issues = semantic_parity(a, b)
        self.assertFalse(ok)
        self.assertTrue(any("tracking" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
