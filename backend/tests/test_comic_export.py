import unittest
import uuid
from pathlib import Path
import tempfile
import zipfile
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.all_models import Base, Project, Page
from app.services.comic_export import (
    generate_comic_info_xml,
    export_project_cbz,
    export_project_pdf,
    export_webtoon_slices,
    WEBTOON_PLATFORM_PRESETS,
)


class TestComicExport(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)

        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        # Create dummy project
        self.project = Project(
            id=str(uuid.uuid4()),
            name="Epic Webtoon",
            source_lang="ko",
            target_lang="th",
        )
        self.db.add(self.project)

        # Create 2 dummy images on disk
        self.img1_path = self.base_path / "page_01.png"
        img1 = Image.new("RGB", (800, 2400), color=(255, 255, 255))
        img1.save(self.img1_path)

        self.img2_path = self.base_path / "page_02.png"
        img2 = Image.new("RGB", (800, 1600), color=(240, 240, 240))
        img2.save(self.img2_path)

        self.p1 = Page(
            id=str(uuid.uuid4()),
            project_id=self.project.id,
            page_number=1,
            name="page_01.png",
            width=800,
            height=2400,
            source_image_path=str(self.img1_path),
            rendered_image_path=str(self.img1_path),
        )
        self.p2 = Page(
            id=str(uuid.uuid4()),
            project_id=self.project.id,
            page_number=2,
            name="page_02.png",
            width=800,
            height=1600,
            source_image_path=str(self.img2_path),
            rendered_image_path=str(self.img2_path),
        )
        self.db.add_all([self.p1, self.p2])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.temp_dir.cleanup()

    def test_generate_comic_info_xml(self):
        xml = generate_comic_info_xml(self.project, 2)
        self.assertIn("<Title>Epic Webtoon</Title>", xml)
        self.assertIn("<PageCount>2</PageCount>", xml)
        self.assertIn("<LanguageISO>th</LanguageISO>", xml)

    def test_export_project_cbz(self):
        cbz_out = self.base_path / "test_comic.cbz"
        res_path = export_project_cbz(self.project.id, self.db, out_path=cbz_out)
        self.assertTrue(res_path.exists())

        # Verify CBZ ZIP structure
        with zipfile.ZipFile(res_path, "r") as z:
            names = z.namelist()
            self.assertIn("ComicInfo.xml", names)
            self.assertIn("page_001.png", names)
            self.assertIn("page_002.png", names)

    def test_export_project_pdf(self):
        pdf_out = self.base_path / "test_comic.pdf"
        res_path = export_project_pdf(self.project.id, self.db, out_path=pdf_out)
        self.assertTrue(res_path.exists())
        self.assertGreater(res_path.stat().st_size, 1000)

    def test_export_webtoon_slices(self):
        result = export_webtoon_slices(self.project.id, "webtoon", self.db)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["platform"], "webtoon")
        self.assertGreaterEqual(result["total_slices"], 3)
        for s in result["slices"]:
            self.assertEqual(s["width"], 800)
            self.assertLessEqual(s["height"], 1280)
            self.assertTrue(Path(s["path"]).exists())


if __name__ == "__main__":
    unittest.main()
