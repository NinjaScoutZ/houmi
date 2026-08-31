import unittest
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.all_models import Base, Project, Page, TextBlock
from app.services.qa_service import audit_block_qa, audit_page_qa, audit_project_qa


class TestQAService(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        # Create test project and page
        self.project = Project(
            id=str(uuid.uuid4()),
            name="QA Test Project",
            source_lang="zh",
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

    def test_untranslated_bubble_detected(self):
        block = TextBlock(
            id=str(uuid.uuid4()),
            page_id=self.page.id,
            block_index=0,
            x=100,
            y=100,
            width=200,
            height=100,
            source_text="你好世界",
            translation="",
        )
        issues = audit_block_qa(block)
        codes = [i["code"] for i in issues]
        self.assertIn("UNTRANSLATED_BUBBLE", codes)

    def test_empty_block_detected(self):
        block = TextBlock(
            id=str(uuid.uuid4()),
            page_id=self.page.id,
            block_index=1,
            x=100,
            y=100,
            width=200,
            height=100,
            source_text="",
            translation="",
        )
        issues = audit_block_qa(block)
        codes = [i["code"] for i in issues]
        self.assertIn("EMPTY_BLOCK", codes)

    def test_low_ocr_confidence_detected(self):
        block = TextBlock(
            id=str(uuid.uuid4()),
            page_id=self.page.id,
            block_index=2,
            x=100,
            y=100,
            width=200,
            height=100,
            source_text="模糊文本",
            translation="ข้อความเบลอ",
            confidence=0.32,
        )
        issues = audit_block_qa(block)
        codes = [i["code"] for i in issues]
        self.assertIn("LOW_OCR_CONFIDENCE", codes)

    def test_text_overflow_detected(self):
        # Long text inside a very small container
        long_translation = "นี่คือข้อความที่ยาวมากกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกก"
        block = TextBlock(
            id=str(uuid.uuid4()),
            page_id=self.page.id,
            block_index=3,
            x=100,
            y=100,
            width=50,  # very narrow
            height=30,
            source_text="短文",
            translation=long_translation,
            font_size=28.0,
        )
        issues = audit_block_qa(block)
        codes = [i["code"] for i in issues]
        self.assertIn("TEXT_OVERFLOW", codes)

    def test_thai_floating_diacritic_detected(self):
        # Starts with floating tone mark without consonant
        corrupted_text = "้สวัสดี"
        block = TextBlock(
            id=str(uuid.uuid4()),
            page_id=self.page.id,
            block_index=4,
            x=100,
            y=100,
            width=200,
            height=100,
            source_text="你好",
            translation=corrupted_text,
        )
        issues = audit_block_qa(block)
        codes = [i["code"] for i in issues]
        self.assertIn("THAI_FLOATING_DIACRITIC", codes)

    def test_clean_block_has_no_issues(self):
        block = TextBlock(
            id=str(uuid.uuid4()),
            page_id=self.page.id,
            block_index=5,
            x=100,
            y=100,
            width=300,
            height=150,
            source_text="你好",
            translation="สวัสดี",
            confidence=0.95,
            font_size=20.0,
        )
        issues = audit_block_qa(block)
        self.assertEqual(issues, [])

    def test_audit_page_and_project(self):
        b1 = TextBlock(
            id=str(uuid.uuid4()),
            page_id=self.page.id,
            block_index=0,
            x=100,
            y=100,
            width=200,
            height=100,
            source_text="你好",
            translation="",
        )
        b2 = TextBlock(
            id=str(uuid.uuid4()),
            page_id=self.page.id,
            block_index=1,
            x=100,
            y=250,
            width=300,
            height=150,
            source_text="再见",
            translation="ลาก่อน",
            confidence=0.98,
        )
        self.db.add_all([b1, b2])
        self.db.commit()

        page_res = audit_page_qa(str(self.page.id), self.db)
        self.assertEqual(page_res["total_blocks"], 2)
        self.assertGreaterEqual(page_res["total_issues"], 1)

        project_res = audit_project_qa(str(self.project.id), self.db)
        self.assertEqual(project_res["total_pages"], 1)
        self.assertEqual(project_res["total_blocks"], 2)
        self.assertGreaterEqual(project_res["total_issues"], 1)


if __name__ == "__main__":
    unittest.main()
