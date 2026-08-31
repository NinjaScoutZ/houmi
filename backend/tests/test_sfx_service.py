import unittest
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.all_models import Base, Project, Page, TextBlock
from app.services.sfx_dictionary import lookup_sfx, suggest_sfx_translation, get_sfx_catalog


class TestSFXService(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        self.project = Project(
            id=str(uuid.uuid4()),
            name="SFX Test Project",
            source_lang="ja",
            target_lang="th",
        )
        self.db.add(self.project)

        self.page = Page(
            id=str(uuid.uuid4()),
            project_id=self.project.id,
            page_number=1,
            name="01.png",
            width=1000,
            height=1500,
            source_image_path="dummy.png",
        )
        self.db.add(self.page)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_lookup_japanese_sfx(self):
        results = lookup_sfx("ドドド", lang="ja")
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["orig"], "ドドド")
        self.assertIn("ตึกตัก", results[0]["thai"])

    def test_lookup_korean_sfx(self):
        results = lookup_sfx("콰쾅", lang="ko")
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["orig"], "콰쾅")
        self.assertIn("เปรี้ยง", results[0]["thai"])

    def test_lookup_chinese_sfx(self):
        results = lookup_sfx("轰", lang="zh")
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["orig"], "轰")
        self.assertIn("ตู้ม", results[0]["thai"])

    def test_suggest_sfx_translation(self):
        th = suggest_sfx_translation("バン")
        self.assertEqual(th, "ปัง!")

        th_zh = suggest_sfx_translation("啪")
        self.assertIn("เพียะ", th_zh)

    def test_catalog_category_filtering(self):
        impact_items = get_sfx_catalog(category="impact")
        self.assertGreater(len(impact_items), 0)
        for item in impact_items:
            self.assertEqual(item["category"], "impact")

    def test_sfx_block_configuration(self):
        block = TextBlock(
            id=str(uuid.uuid4()),
            page_id=self.page.id,
            block_index=0,
            x=150,
            y=200,
            width=80,
            height=120,
            source_text="ドドド",
            balloon_type="sfx",
            extra_metadata={"sfx_workflow_mode": "subtitle_overlay"},
        )
        self.db.add(block)
        self.db.commit()

        loaded = self.db.query(TextBlock).filter(TextBlock.id == block.id).first()
        self.assertEqual(loaded.balloon_type, "sfx")
        self.assertEqual(loaded.extra_metadata.get("sfx_workflow_mode"), "subtitle_overlay")


if __name__ == "__main__":
    unittest.main()
