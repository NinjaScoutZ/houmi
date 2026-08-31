import unittest
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.all_models import Page, Project, TextBlock
from app.routes.exchange import ClearTranslationsRequest, clear_translations
from app.routes.blocks import BulkBlockUpdateItem, BulkBlockUpdateRequest, update_blocks_bulk
from app.schemas.all_schemas import TextBlockUpdate
from app.routes.pipeline import run_detect
from app.services.txt_exchange import (
    export_to_txt,
    parse_translation_annotation,
    validate_and_import_txt,
    validate_txt_preview,
)


class TxtExchangeTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.db = sessionmaker(bind=engine)()
        self.project = Project(name="Chinese project", source_lang="zh", target_lang="th")
        page = Page(
            project=self.project,
            page_number=1,
            name="001",
            width=1000,
            height=1500,
            source_image_path="source.png",
        )
        self.blocks = [
            TextBlock(page=page, block_index=0, x=10, y=10, width=200, height=100, source_text="你好"),
            TextBlock(page=page, block_index=1, x=10, y=120, width=200, height=100, source_text="再见"),
            TextBlock(page=page, block_index=2, x=10, y=230, width=200, height=100, source_text="谢谢"),
        ]
        self.db.add(self.project)
        self.db.commit()
        self.spec_patch = patch(
            "app.services.txt_exchange.compute_block_typesetting",
            return_value=SimpleNamespace(model_dump=lambda: {"layout_status": "valid"}),
        )
        self.spec_patch.start()

    def tearDown(self):
        self.spec_patch.stop()
        self.db.close()

    def test_ocr_export_matches_bubble_workflow(self):
        exported = export_to_txt(self.project.id, self.db, mode="ocr")
        self.assertEqual(exported, "//你好\n//再见\n//谢谢")

    def test_slash_slash_import_and_export(self):
        exported = export_to_txt(self.project.id, self.db, mode="ocr")
        self.assertEqual(exported, "//你好\n//再见\n//谢谢")

        content = """//你好
สวัสดี

//再见
ลาก่อน

//谢谢
ขอบคุณ
"""
        result = validate_and_import_txt(self.project.id, content, self.db)
        self.assertTrue(result["success"])
        self.assertEqual(result["format"], "slash_slash")
        self.assertEqual(result["updated_count"], 3)
        self.db.refresh(self.blocks[0])
        self.db.refresh(self.blocks[1])
        self.db.refresh(self.blocks[2])
        self.assertEqual(self.blocks[0].translation, "สวัสดี")
        self.assertEqual(self.blocks[1].translation, "ลาก่อน")
        self.assertEqual(self.blocks[2].translation, "ขอบคุณ")

    def test_imports_translation_added_below_ocr_label(self):
        content = """# Bubble 1
[คำต้นฉบับ]: 你好
สวัสดี

# Bubble 2
[คำต้นฉบับ]: 再见
ลาก่อน
"""
        result = validate_and_import_txt(self.project.id, content, self.db)
        self.assertTrue(result["success"])
        self.assertEqual(result["format"], "bubble")
        self.assertEqual(result["updated_count"], 2)
        self.db.refresh(self.blocks[0])
        self.db.refresh(self.blocks[1])
        self.assertEqual(self.blocks[0].translation, "สวัสดี")
        self.assertEqual(self.blocks[1].translation, "ลาก่อน")

    def test_parses_all_supported_ai_semantic_tags_only_at_the_end(self):
        cases = {
            "ฉันต้องรีบแล้ว {คิดในใจ}": ("ฉันต้องรีบแล้ว", "thought"),
            "หยุดนะ! {ตัวละครพูด}": ("หยุดนะ!", "bubble"),
            "สามวันต่อมา {คำบรรยาย}": ("สามวันต่อมา", "narration"),
            "ได้รับสกิลใหม่ { ระบบพูด }": ("ได้รับสกิลใหม่", "system"),
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                parsed = parse_translation_annotation(raw)
                self.assertEqual((parsed.text, parsed.semantic_role), expected)

        embedded = parse_translation_annotation("เขาพิมพ์คำว่า {ระบบพูด} ไว้ในจดหมาย")
        self.assertIsNone(embedded.semantic_role)
        self.assertEqual(embedded.text, "เขาพิมพ์คำว่า {ระบบพูด} ไว้ในจดหมาย")

    def test_import_strips_ai_tag_and_persists_semantic_role(self):
        content = """# Bubble 1
[คำต้นฉบับ]: 你好
[คำแปลไทย]: สวัสดี {ตัวละครพูด}

# Bubble 2
[คำต้นฉบับ]: 再见
[คำแปลไทย]: วันต่อมา {คำบรรยาย}

# Bubble 3
[คำต้นฉบับ]: 谢谢
[คำแปลไทย]: เขาจะรู้หรือยัง {คิดในใจ}
"""

        preview = validate_txt_preview(self.project.id, content, self.db)
        self.assertEqual(preview["preview_records"][0]["translation"], "สวัสดี")
        self.assertEqual(preview["preview_records"][0]["semantic_role"], "bubble")
        self.assertEqual(preview["preview_records"][1]["semantic_role_label"], "คำบรรยาย")

        result = validate_and_import_txt(self.project.id, content, self.db)
        self.assertTrue(result["success"])
        for block in self.blocks:
            self.db.refresh(block)
        self.assertEqual(self.blocks[0].translation, "สวัสดี")
        self.assertEqual(self.blocks[0].extra_metadata["semantic_role"], "bubble")
        self.assertEqual(self.blocks[0].extra_metadata["semantic_role_template_id"], "bubble")
        self.assertEqual(self.blocks[1].extra_metadata["semantic_role"], "narration")
        self.assertEqual(self.blocks[1].extra_metadata["semantic_role_template_id"], "narration")
        self.assertEqual(self.blocks[2].extra_metadata["semantic_role"], "thought")
        self.assertNotIn("{คิดในใจ}", self.blocks[2].translation)

    def test_import_preserves_ai_line_breaks_before_final_semantic_tag(self):
        content = """# Bubble 1
[คำต้นฉบับ]: 你好
[คำแปลไทย]: สวัสดี เราชื่อแดนนะ
นายชื่ออะไรงั้นเหรอ
เรามาจากโลกใหม่
{ตัวละครพูด}
"""

        preview = validate_txt_preview(self.project.id, content, self.db)
        expected = "สวัสดี เราชื่อแดนนะ\nนายชื่ออะไรงั้นเหรอ\nเรามาจากโลกใหม่"
        self.assertEqual(preview["preview_records"][0]["translation"], expected)
        self.assertEqual(preview["preview_records"][0]["semantic_role"], "bubble")

        result = validate_and_import_txt(self.project.id, content, self.db)

        self.assertTrue(result["success"])
        self.db.refresh(self.blocks[0])
        self.assertEqual(self.blocks[0].translation, expected)
        self.assertEqual(self.blocks[0].extra_metadata["semantic_role_tag"], "{ตัวละครพูด}")
        self.assertEqual(self.blocks[0].extra_metadata["line_break_source"], "ai_preferred")
        self.assertEqual(self.blocks[0].extra_metadata["ai_preferred_lines"], expected.splitlines())

    def test_import_uses_existing_translation_as_exact_ai_layout_text(self):
        block = self.blocks[0]
        block.translation = "Hello world ภาษาไทย"
        self.db.commit()

        content = """你好
[[HOUMI_LAYOUT shape=ellipse target_lines=2 max_lines=3]]
Hello
world ภาษาไทย
{ตัวละครพูด}
"""

        result = validate_and_import_txt(self.project.id, content, self.db)

        self.assertTrue(result["success"])
        self.db.refresh(block)
        self.assertEqual(block.extra_metadata["ai_layout_text"], "Hello world ภาษาไทย")

    def test_ai_layout_export_and_import_round_trip(self):
        block = self.blocks[0]
        block.translation = "ข้อความที่แปลเสร็จแล้ว"
        block.extra_metadata = {
            "layout_region": {
                "x": 5, "y": 5, "width": 320, "height": 240,
                "shape": "bubble", "source": "balloon_interior", "confidence": 0.9,
            },
            "min_font_size": 24,
            "preferred_font_size": 36,
            "semantic_role_label": "ตัวละครพูด",
        }
        self.db.commit()

        exported = export_to_txt(self.project.id, self.db, mode="ai_layout")

        self.assertNotIn("# Bubble", exported)
        self.assertIn("你好\n[[HOUMI_LAYOUT shape=ellipse target_lines=", exported)
        self.assertIn("max_lines=", exported)
        self.assertNotIn("{ตัวละครพูด}", exported)

        content = """你好
[[HOUMI_LAYOUT shape=ellipse target_lines=3 max_lines=4]]
สวัสดี เราชื่อแดนนะ
นายชื่ออะไรงั้นเหรอ
เรามาจากโลกใหม่
{ตัวละครพูด}
"""
        result = validate_and_import_txt(self.project.id, content, self.db)

        self.assertTrue(result["success"])
        self.db.refresh(block)
        self.assertEqual(block.extra_metadata["ai_layout_hint"]["target_lines"], 3)
        self.assertEqual(block.extra_metadata["ai_layout_hint"]["max_lines"], 4)
        self.assertEqual(block.extra_metadata["line_break_source"], "ai_preferred")

    def test_dual_slash_import_format(self):
        content = """//你好
//สวัสดี

//再见
//ลาก่อน
"""
        preview = validate_txt_preview(self.project.id, content, self.db)
        self.assertTrue(preview["success"])
        self.assertEqual(preview["summary"]["ok"], 2)
        records = preview["preview_records"]
        self.assertEqual(records[0]["source_text"], "你好")
        self.assertEqual(records[0]["translation"], "สวัสดี")
        self.assertEqual(records[1]["source_text"], "再见")
        self.assertEqual(records[1]["translation"], "ลาก่อน")
        self.project.settings = {
            "text_templates": {
                "system-ui": {
                    "font_stack": ["Tahoma"],
                    "font_size": 26,
                    "color_hex": "#ffffff",
                    "bold": True,
                    "balloon_type": "narrative",
                    "semantic_tag": "ระบบพูด",
                }
            },
        }
        self.db.commit()

        result = validate_and_import_txt(
            self.project.id, "你好\tได้รับสกิลใหม่ {ระบบพูด}\n", self.db
        )

        self.assertTrue(result["success"])
        self.db.refresh(self.blocks[0])
        self.assertEqual(self.blocks[0].translation, "ได้รับสกิลใหม่")
        self.assertEqual(self.blocks[0].extra_metadata["semantic_role"], "system-ui")
        self.assertEqual(
            self.blocks[0].extra_metadata["semantic_role_template_id"], "system-ui"
        )
        self.assertEqual(self.blocks[0].font_size, 26)

    def test_imports_two_column_tsv_like_converted_files(self):
        content = "你好\tสวัสดี\n再见\tลาก่อน\n谢谢\tขอบคุณ\n"
        result = validate_and_import_txt(self.project.id, content, self.db)
        self.assertTrue(result["success"])
        self.assertEqual(result["format"], "tsv")
        self.assertEqual(result["updated_count"], 3)

    def test_import_applies_project_default_font(self):
        self.project.settings = {"default_font_family": "Tahoma"}
        self.db.commit()

        result = validate_and_import_txt(self.project.id, "你好\tสวัสดี\n", self.db)

        self.assertTrue(result["success"])
        self.db.refresh(self.blocks[0])
        self.assertEqual(self.blocks[0].font_family, "Tahoma")
        self.assertEqual(self.blocks[0].extra_metadata["font_stack"], ["Tahoma"])

    def test_import_applies_complete_default_text_template(self):
        self.project.settings = {
            "default_text_template_id": "dialogue",
            "text_templates": {
                "dialogue": {
                    "font_stack": ["Tahoma"],
                    "font_size": 34,
                    "color_hex": "#223344",
                    "bold": True,
                    "italic": False,
                    "text_align": "center",
                    "text_direction": "horizontal",
                    "balloon_type": "bubble",
                    "line_height_ratio": 1.15,
                    "letter_spacing": 1.5,
                    "padding": {"top": 4, "right": 6, "bottom": 4, "left": 6},
                }
            },
        }
        self.db.commit()

        result = validate_and_import_txt(self.project.id, "你好\tสวัสดี\n", self.db)

        self.assertTrue(result["success"])
        self.db.refresh(self.blocks[0])
        self.assertEqual(self.blocks[0].font_family, "Tahoma")
        self.assertEqual(self.blocks[0].font_size, 34)
        self.assertEqual(self.blocks[0].color_hex, "#223344")
        self.assertTrue(self.blocks[0].bold)
        self.assertEqual(self.blocks[0].extra_metadata["text_template_id"], "dialogue")
        self.assertEqual(self.blocks[0].extra_metadata["line_height_ratio"], 1.15)

    def test_imports_blank_line_separated_source_translation_pairs(self):
        content = "你好\nสวัสดี\n\n再见\nลาก่อน\n\n谢谢\nขอบคุณ\n"
        result = validate_and_import_txt(self.project.id, content, self.db)
        self.assertTrue(result["success"])
        self.assertEqual(result["format"], "alternating")
        self.assertEqual(result["updated_count"], 3)

    def test_bulk_template_update_preserves_every_translation(self):
        expected = ["คำแปลหนึ่ง", "คำแปลสอง", "คำแปลสาม"]
        for block, translation in zip(self.blocks, expected):
            block.translation = translation
        self.db.commit()
        request = BulkBlockUpdateRequest(updates=[
            BulkBlockUpdateItem(
                block_id=block.id,
                data=TextBlockUpdate(
                    font_family="Tahoma",
                    font_size=42,
                    bold=True,
                    extra_metadata={"text_template_id": "emphasis", "font_stack": ["Tahoma"]},
                ),
            )
            for block in self.blocks
        ])
        fake_spec = SimpleNamespace(model_dump=lambda: {"layout_status": "valid", "font_size": 42})

        with patch("app.services.typesetting.compute_block_typesetting", return_value=fake_spec):
            updated = update_blocks_bulk(request, self.db)

        self.assertEqual([block.translation for block in updated], expected)
        self.assertTrue(all(block.font_size == 42 for block in updated))
        self.assertTrue(all(block.bold for block in updated))
        self.assertTrue(all(block.extra_metadata["text_template_id"] == "emphasis" for block in updated))
        self.assertTrue(all(block.extra_metadata["manual_font_size"] == 42 for block in updated))
        self.assertTrue(all(block.extra_metadata["font_size_mode"] == "manual" for block in updated))

    def test_source_mismatch_is_skipped_without_shifting_following_pairs(self):
        self.blocks[0].translation = "เดิมหนึ่ง"
        self.blocks[1].translation = "เดิมสอง"
        self.db.commit()
        content = "你好\tใหม่หนึ่ง\nข้อความผิดตำแหน่ง\tใหม่สอง\n"

        result = validate_and_import_txt(self.project.id, content, self.db)

        self.assertTrue(result["success"])
        self.assertEqual(result["updated_count"], 1)
        self.assertEqual(result["skipped_unmatched_count"], 1)
        self.db.refresh(self.blocks[0])
        self.db.refresh(self.blocks[1])
        self.assertEqual(self.blocks[0].translation, "ใหม่หนึ่ง")
        self.assertEqual(self.blocks[1].translation, "เดิมสอง")

    def test_smart_import_matches_reordered_source_pairs(self):
        content = "谢谢\nขอบคุณ\n\n你好\nสวัสดี\n"

        result = validate_and_import_txt(self.project.id, content, self.db)

        self.assertTrue(result["success"])
        self.assertEqual(result["updated_count"], 2)
        self.db.refresh(self.blocks[0])
        self.db.refresh(self.blocks[2])
        self.assertEqual(self.blocks[0].translation, "สวัสดี")
        self.assertEqual(self.blocks[2].translation, "ขอบคุณ")

    def test_preview_reports_line_layer_and_only_imports_safe_records(self):
        content = "你好\tสวัสดี\nข้อความที่ไม่ตรง\tควรถูกข้าม\n"

        preview = validate_txt_preview(self.project.id, content, self.db)

        self.assertTrue(preview["success"])
        self.assertEqual(preview["summary"]["importable"], 1)
        self.assertEqual(preview["preview_records"][0]["block_index"], 1)
        self.assertTrue(preview["preview_records"][0]["will_import"])
        self.assertFalse(preview["preview_records"][1]["will_import"])

        result = validate_and_import_txt(self.project.id, content, self.db)
        self.assertTrue(result["success"])
        self.assertEqual(result["updated_count"], 1)
        self.assertEqual(result["skipped_unmatched_count"], 1)
        self.db.refresh(self.blocks[0])
        self.assertEqual(self.blocks[0].translation, "สวัสดี")

    def test_all_unmatched_pairs_are_reported_without_mutating_project(self):
        content = "คนละบทหนึ่ง\nคำแปลหนึ่ง\n\nคนละบทสอง\nคำแปลสอง\n"

        result = validate_and_import_txt(self.project.id, content, self.db)

        self.assertTrue(result["success"])
        self.assertEqual(result["updated_count"], 0)
        self.assertEqual(result["skipped_unmatched_count"], 2)
        self.assertTrue(all(not block.translation for block in self.blocks))

    def test_detection_cannot_silently_delete_imported_translation(self):
        from fastapi import HTTPException

        self.blocks[0].translation = "ข้อความที่แปลแล้ว"
        self.db.commit()

        with self.assertRaises(HTTPException) as raised:
            run_detect(self.blocks[0].page_id, db=self.db)

        self.assertEqual(raised.exception.status_code, 409)

    def test_clear_translations_preserves_ocr_geometry_and_source_font(self):
        block = self.blocks[0]
        original_geometry = (block.x, block.y, block.width, block.height)
        block.translation = "ข้อความเก่า"
        block.font_size = 31
        block.extra_metadata = {
            "source_font_size": 29,
            "typesetting_spec": {"font_size": 62, "layout_version": "1.0.1"},
            "text_template_id": "old-template",
            "manual_font_size": 62,
            "mask_path": "mask.png",
            "semantic_role": "dialogue",
            "semantic_role_tag": "{ตัวละครพูด}",
            "semantic_role_raw_translation": "ข้อความเก่า {ตัวละครพูด}",
            "line_break_source": "ai_preferred",
            "ai_preferred_lines": ["ข้อความ", "เก่า"],
            "ai_layout_hint": {"target_lines": 2, "max_lines": 3},
            "ai_layout_text": "ข้อความเก่า",
        }
        self.db.commit()

        with patch("app.routes.exchange.save_project_json"):
            result = clear_translations(
                ClearTranslationsRequest(scope="page", page_id=block.page_id),
                db=self.db,
            )

        self.db.refresh(block)
        self.assertEqual(result["cleared_blocks"], 3)
        self.assertEqual(block.translation, "")
        self.assertEqual(block.source_text, "你好")
        self.assertEqual((block.x, block.y, block.width, block.height), original_geometry)
        self.assertEqual(block.extra_metadata["source_font_size"], 29)
        self.assertEqual(block.extra_metadata["mask_path"], "mask.png")
        self.assertNotIn("typesetting_spec", block.extra_metadata)
        self.assertNotIn("text_template_id", block.extra_metadata)
        self.assertNotIn("manual_font_size", block.extra_metadata)
        self.assertNotIn("semantic_role", block.extra_metadata)
        self.assertNotIn("semantic_role_tag", block.extra_metadata)
        self.assertNotIn("semantic_role_raw_translation", block.extra_metadata)
        self.assertNotIn("line_break_source", block.extra_metadata)
        self.assertNotIn("ai_preferred_lines", block.extra_metadata)
        self.assertNotIn("ai_layout_hint", block.extra_metadata)
        self.assertNotIn("ai_layout_text", block.extra_metadata)


if __name__ == "__main__":
    unittest.main()
