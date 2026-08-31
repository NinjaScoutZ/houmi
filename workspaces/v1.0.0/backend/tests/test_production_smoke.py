import os
import unittest
import tempfile
from pathlib import Path
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.all_models import Project, Page, TextBlock
from app.services.renderer import find_fitting_font_size, render_page_text
from app.services.psd_export import export_page_to_psd

from tests.test_helpers import ensure_psd_cli_built

class TestProductionSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Simulate environment of run_desktop.py
        os.environ["PRODUCTION_MODE"] = "1"
        ensure_psd_cli_built()

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

        # Create dummy source image
        self.source_img_path = self.temp_path / "source.png"
        img = Image.new("RGBA", (200, 300), (255, 255, 255, 255))
        img.save(self.source_img_path)

        # In-memory database
        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        # Mock project, page
        self.project = Project(
            id="smoke-proj",
            name="Smoke Project",
            source_lang="ja",
            target_lang="th"
        )
        self.db.add(self.project)

        self.page = Page(
            id="smoke-page",
            project_id=self.project.id,
            page_number=1,
            width=200,
            height=300,
            source_image_path=str(self.source_img_path)
        )
        self.db.add(self.page)

        # Insert default block using NotoSansThai (as requested)
        self.block = TextBlock(
            id="smoke-block-uuid-1111",
            page_id=self.page.id,
            block_index=1,
            x=10.0,
            y=20.0,
            width=80.0,
            height=40.0,
            source_text="若为仙路",
            translation="ทดสอบภาษาไทยในโหมดโปรดักชัน",
            font_family="NotoSansThai",  # Default configuration font
            font_size=14.0,
            balloon_type="bubble",
            color_hex="#ff0000"
        )
        self.db.add(self.block)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.temp_dir.cleanup()
        if "PRODUCTION_MODE" in os.environ:
            del os.environ["PRODUCTION_MODE"]

    def test_production_smoke_flow(self):
        # 1. Auto-fit must function properly under PRODUCTION_MODE=1
        font, fitted_size = find_fitting_font_size(
            text_val=self.block.translation,
            font_name=self.block.font_family,
            bold=self.block.bold,
            block_w=self.block.width,
            block_h=self.block.height,
            balloon_type=self.block.balloon_type,
            italic=self.block.italic
        )
        self.assertIsNotNone(font)
        self.assertGreater(fitted_size, 0)

        # 2. Rendering page text must succeed without raising production exceptions
        try:
            rendered_path = render_page_text(self.page.id, self.db)
            self.assertTrue(rendered_path.exists())
            rendered_path.unlink()  # clean up
        except Exception as e:
            self.fail(f"render_page_text failed under Production Mode: {e}")

        # 3. PSD font preflight & export must succeed without raising exceptions
        try:
            psd_path = export_page_to_psd(self.page.id, self.db, force=True)
            self.assertTrue(psd_path.exists())
            psd_path.unlink()  # clean up
        except Exception as e:
            self.fail(f"export_page_to_psd preflight or generation failed under Production Mode: {e}")

if __name__ == "__main__":
    unittest.main()
