import os
import unittest
import tempfile
from pathlib import Path
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.all_models import Project, Page, TextBlock
from app.services.psd_export import export_page_to_psd
from app.services.psd_import import import_psd_to_page, _photoshop_text_geometry
from psd_tools import PSDImage

from tests.test_helpers import ensure_psd_cli_built


class TestPsdRoundtrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_psd_cli_built()

    def setUp(self):
        # Create temp folder for mock project files
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

        # Create dummy source and inpainted images
        self.source_img_path = self.temp_path / "source.png"
        self.inpainted_img_path = self.temp_path / "inpainted.png"
        img = Image.new("RGBA", (200, 300), (255, 255, 255, 255))
        img.save(self.source_img_path)
        img.save(self.inpainted_img_path)

        # Set up clean in-memory database
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        import uuid
        proj_id = f"proj-{uuid.uuid4().hex[:12]}"
        page_id = f"page-{uuid.uuid4().hex[:12]}"

        # Insert mock project and page
        self.project = Project(
            id=proj_id,
            name="Test Project",
            source_lang="ja",
            target_lang="th",
        )
        self.db.add(self.project)

        self.page = Page(
            id=page_id,
            project_id=self.project.id,
            page_number=1,
            width=200,
            height=300,
            source_image_path=str(self.source_img_path),
            inpainted_image_path=str(self.inpainted_img_path),
        )
        self.db.add(self.page)

        # Insert TextBlocks covering regular, bold, italic, bold-italic, and synthetic faux styles
        # Block 1: Regular
        self.block1 = TextBlock(
            id="a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
            page_id=self.page.id,
            block_index=1,
            x=10.0,
            y=20.0,
            width=80.0,
            height=40.0,
            source_text="若为仙路",
            translation="若为仙路 CJK 字符",  # Actual CJK translation
            font_family="Arial",
            font_size=14.0,
            bold=False,
            italic=False,
            balloon_type="bubble",
            color_hex="#ff0000",
        )
        # Block 2: Bold (Legacy UUID format)
        self.block2 = TextBlock(
            id="blk-f5e4d3c2-b1a0-9f8e-7d6c-5b4a3f2e1d0c",  # Legacy blk-UUID
            page_id=self.page.id,
            block_index=2,
            x=5.0,
            y=120.0,
            width=150.0,
            height=50.0,
            source_text="テスト文章",
            translation="ทดสอบข้อความภาษาไทย CJK",
            font_family="Arial",
            font_size=12.0,
            bold=True,
            italic=False,
            balloon_type="narrative",
            color_hex="#000000",
        )
        # Block 3: Italic
        self.block3 = TextBlock(
            id="c3b2a1d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
            page_id=self.page.id,
            block_index=3,
            x=15.0,
            y=60.0,
            width=80.0,
            height=30.0,
            source_text="Italic source",
            translation="ทดสอบตัวเอียง",
            font_family="Arial",
            font_size=12.0,
            bold=False,
            italic=True,
            balloon_type="bubble",
        )
        # Block 4: Bold-Italic
        self.block4 = TextBlock(
            id="d4c3b2a1-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
            page_id=self.page.id,
            block_index=4,
            x=15.0,
            y=90.0,
            width=80.0,
            height=30.0,
            source_text="Bold Italic source",
            translation="ทดสอบหนาเอียง",
            font_family="Arial",
            font_size=12.0,
            bold=True,
            italic=True,
            balloon_type="bubble",
        )
        # Block 5: Synthetic Italic (Tahoma bold-italic falls back to Tahoma bold)
        self.block5 = TextBlock(
            id="e5d4c3b2-a1f6-7a8b-9c0d-1e2f3a4b5c6d",
            page_id=self.page.id,
            block_index=5,
            x=30.0,
            y=150.0,
            width=80.0,
            height=30.0,
            source_text="Synthetic source",
            translation="ทดสอบตัวเอียงเทียม",
            font_family="Tahoma",
            font_size=12.0,
            bold=True,
            italic=True,
            balloon_type="bubble",
        )
        # Block 6: Noto bold-italic (falls back to Tahoma Regular, faux flags false)
        self.block6 = TextBlock(
            id="f6e5d4c3-b2a1-9f8e-7d6c-5b4a3f2e1d0c",
            page_id=self.page.id,
            block_index=6,
            x=40.0,
            y=180.0,
            width=80.0,
            height=30.0,
            source_text="Noto fallback source",
            translation="ทดสอบ Noto fallback",
            font_family="NotoSansThai",
            font_size=12.0,
            bold=True,
            italic=True,
            balloon_type="bubble",
        )
        self.db.add(self.block1)
        self.db.add(self.block2)
        self.db.add(self.block3)
        self.db.add(self.block4)
        self.db.add(self.block5)
        self.db.add(self.block6)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.temp_dir.cleanup()

    def test_photoshop_geometry_uses_paragraph_box_instead_of_glyph_bbox(self):
        class Layer:
            bbox = (130, 240, 190, 270)
            transform = (1.0, 0.0, 0.0, 1.0, 100.0, 200.0)
            engine_dict = {
                "Rendered": {
                    "Shapes": {
                        "Children": [{
                            "Cookie": {
                                "Photoshop": {"BoxBounds": [18.0, 30.0, 222.0, 108.0]}
                            }
                        }]
                    }
                }
            }

        geometry = _photoshop_text_geometry(
            Layer(),
            {
                "psd_geometry_version": "2",
                "padding": {"top": 12, "right": 18, "bottom": 12, "left": 18},
            },
        )

        self.assertEqual(
            geometry,
            {"x": 100.0, "y": 200.0, "width": 240.0, "height": 120.0, "rotation_deg": 0.0},
        )

        Layer.transform = (0.0, 1.0, -1.0, 0.0, 280.0, 140.0)
        rotated = _photoshop_text_geometry(
            Layer(),
            {
                "psd_geometry_version": "2",
                "padding": {"top": 12, "right": 18, "bottom": 12, "left": 18},
            },
        )
        self.assertAlmostEqual(rotated["x"], 100.0)
        self.assertAlmostEqual(rotated["y"], 200.0)
        self.assertAlmostEqual(rotated["rotation_deg"], 90.0)

    def test_psd_roundtrip_flow(self):
        # 1. Export PSD via the exporter calling the Rust CLI
        psd_path = export_page_to_psd(self.page.id, self.db, force=True, text_mode="paragraph")
        self.assertTrue(psd_path.exists())
        self.assertEqual(psd_path.name, "page_001.psd")

        # 2. Inspect exported layers using psd-tools
        psd = PSDImage.open(psd_path)
        text_layers = [l for l in psd if l.kind == "type"]

        # Verify layers were exported correctly
        self.assertEqual(len(text_layers), 6)

        # Check layer naming and content mapping
        layer_names = [l.name for l in text_layers]
        self.assertTrue(
            any("a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d" in name for name in layer_names)
        )
        self.assertTrue(
            any(
                "blk-f5e4d3c2-b1a0-9f8e-7d6c-5b4a3f2e1d0c" in name
                for name in layer_names
            )
        )
        self.assertTrue(
            any("f6e5d4c3-b2a1-9f8e-7d6c-5b4a3f2e1d0c" in name for name in layer_names)
        )

        # Photoshop displays PSD layer records in reverse order. Base image
        # records must precede Type records so editable text appears above them.
        record_names = [layer.name for layer in psd]
        first_text_record = min(
            index for index, layer in enumerate(psd) if layer.kind == "type"
        )
        self.assertLess(record_names.index("Original Image"), first_text_record)
        if "Inpainted" in record_names:
            self.assertLess(record_names.index("Inpainted"), first_text_record)

        # Check resolved PostScript names and styles in FontSet & StyleSheetSet
        for layer in text_layers:
            font_set = layer.resource_dict.get("FontSet", [])
            font_names = [f.get("Name") for f in font_set]

            style_run = layer.engine_dict.get("StyleRun", {})
            run_array = style_run.get("RunArray", [])
            self.assertTrue(len(run_array) > 0)
            run_data = run_array[0].get("StyleSheet", {}).get("StyleSheetData", {})

            faux_bold = run_data.get("FauxBold", False)
            faux_italic = run_data.get("FauxItalic", False)

            # Balloon copy must be native Photoshop paragraph/area text. Point
            # text is converted on first edit and triggers the layout-change
            # warning that previously required the user to press Transform.
            shapes = layer.engine_dict.get("Rendered", {}).get("Shapes", {})
            shape_children = shapes.get("Children", [])
            self.assertTrue(shape_children)
            photoshop_cookie = (
                shape_children[0].get("Cookie", {}).get("Photoshop", {})
            )
            self.assertEqual(photoshop_cookie.get("ShapeType"), 1)
            self.assertEqual(len(photoshop_cookie.get("BoxBounds", [])), 4)

            block_id = next(block.id for block in self.page.text_blocks if block.id in layer.name)
            exported_block = next(block for block in self.page.text_blocks if block.id == block_id)
            spec = exported_block.extra_metadata["typesetting_spec"]
            padding = spec["padding"]
            box_bounds = [float(value) for value in photoshop_cookie["BoxBounds"]]
            self.assertAlmostEqual(float(run_data["FontSize"]), spec["font_size"], places=4)
            self.assertAlmostEqual(float(run_data["Leading"]), spec["line_height"], places=4)
            self.assertAlmostEqual(box_bounds[0], padding["left"], places=4)
            self.assertAlmostEqual(box_bounds[2], spec["layout_region"]["width"] - padding["right"], places=4)
            is_thai = any(0x0E00 <= ord(c) <= 0x0E7F for c in (exported_block.translation or ""))
            expected_bottom = spec["layout_region"]["height"] - padding["bottom"] + (spec["font_size"] * 0.20 if is_thai else 0.0)
            self.assertAlmostEqual(box_bounds[3], expected_bottom, places=4)
            self.assertAlmostEqual(float(layer.transform[4]), spec["layout_region"]["x"], places=4)
            self.assertAlmostEqual(float(layer.transform[5]), spec["layout_region"]["y"], places=4)

            if "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d" in layer.name:
                # Regular: ArialMT, FauxBold=False, FauxItalic=False
                self.assertIn("ArialMT", font_names)
                self.assertFalse(faux_bold)
                self.assertFalse(faux_italic)
            elif "blk-f5e4d3c2-b1a0-9f8e-7d6c-5b4a3f2e1d0c" in layer.name:
                # Bold: Arial-BoldMT, FauxBold=False, FauxItalic=False
                self.assertIn("Arial-BoldMT", font_names)
                self.assertFalse(faux_bold)
                self.assertFalse(faux_italic)
            elif "c3b2a1d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d" in layer.name:
                # Italic: Arial-ItalicMT, FauxBold=False, FauxItalic=False
                self.assertIn("Arial-ItalicMT", font_names)
                self.assertFalse(faux_bold)
                self.assertFalse(faux_italic)
            elif "d4c3b2a1-e5f6-7a8b-9c0d-1e2f3a4b5c6d" in layer.name:
                # Bold-Italic: Arial-BoldItalicMT, FauxBold=False, FauxItalic=False
                self.assertIn("Arial-BoldItalicMT", font_names)
                self.assertFalse(faux_bold)
                self.assertFalse(faux_italic)
            elif "e5d4c3b2-a1f6-7a8b-9c0d-1e2f3a4b5c6d" in layer.name:
                # Tahoma has no bold-italic face: use the real bold face plus FauxItalic.
                self.assertIn("Tahoma-Bold", font_names)
                self.assertFalse(faux_bold)
                self.assertTrue(faux_italic)
            elif "f6e5d4c3-b2a1-9f8e-7d6c-5b4a3f2e1d0c" in layer.name:
                # Noto bold-italic resolves to native NotoSansThai-Bold or falls back to Tahoma-Bold with FauxItalic
                self.assertTrue(
                    any(n in font_names for n in ["NotoSansThai-Bold", "NotoSansThai", "Tahoma-Bold", "Tahoma"])
                )
                self.assertTrue(faux_italic)

        # 3. Change values in the database first to verify the importer actually updates them
        self.block1.translation = "Changed Translation 1"
        self.block1.x = 99.0
        self.block1.y = 99.0
        self.block1.width = 99.0
        self.block1.height = 99.0

        self.block2.translation = "Changed Translation 2"
        self.block2.x = 88.0
        self.block2.y = 88.0
        self.block2.width = 88.0
        self.block2.height = 88.0

        self.block6.translation = "Changed Translation 6"
        self.block6.x = 77.0
        self.block6.y = 77.0
        self.block6.width = 77.0
        self.block6.height = 77.0
        self.db.commit()

        # 4. Mock PSDImage.open to add unrelated Photoshop text layers. They are
        # not Houmi-managed (`TL ` prefix), so the importer must ignore them.
        from unittest.mock import patch

        class MockLayer:
            def __init__(
                self, name, kind="type", text="Mock Text", bbox=(0, 0, 10, 10)
            ):
                self.name = name
                self.kind = kind
                self.text = text
                self.bbox = bbox

            def is_group(self):
                return False

        real_open = PSDImage.open

        def mock_open(path):
            psd_obj = real_open(path)
            layers = list(psd_obj)
            layers.append(MockLayer("Photoshop Note", text="Invalid Layer Content"))
            layers.append(MockLayer("Translator Comment", text="Non-existent block"))
            return layers

        with patch("app.services.psd_import.PSDImage.open", side_effect=mock_open):
            res = import_psd_to_page(self.page.id, str(psd_path), self.db)

        # Translation-layer geometry is restored into layout_region while the
        # source OCR/mask bbox remains independent.
        self.db.refresh(self.block1)
        self.db.refresh(self.block2)
        self.db.refresh(self.block6)

        self.assertEqual(self.block1.translation, "若为仙路 CJK 字符")
        self.assertEqual(self.block1.x, 99.0)
        self.assertEqual(self.block1.y, 99.0)
        self.assertEqual(self.block1.width, 99.0)
        self.assertEqual(self.block1.height, 99.0)
        self.assertEqual(self.block1.extra_metadata["layout_region"]["x"], 10.0)
        self.assertEqual(self.block1.extra_metadata["layout_region"]["y"], 20.0)
        self.assertEqual(self.block1.extra_metadata["layout_region"]["width"], 80.0)
        self.assertEqual(self.block1.extra_metadata["layout_region"]["height"], 40.0)

        self.assertEqual(self.block2.translation, "ทดสอบข้อความภาษาไทย CJK")
        self.assertEqual(self.block2.x, 88.0)
        self.assertEqual(self.block2.y, 88.0)
        self.assertEqual(self.block2.width, 88.0)
        self.assertEqual(self.block2.height, 88.0)
        self.assertEqual(self.block2.extra_metadata["layout_region"]["x"], 5.0)
        self.assertEqual(self.block2.extra_metadata["layout_region"]["y"], 120.0)
        self.assertEqual(self.block2.extra_metadata["layout_region"]["width"], 150.0)
        self.assertAlmostEqual(self.block2.extra_metadata["layout_region"]["height"], 53.0, delta=3.0)

        self.assertEqual(self.block6.translation, "ทดสอบ Noto fallback")
        self.assertEqual(self.block6.x, 77.0)
        self.assertEqual(self.block6.y, 77.0)
        self.assertEqual(self.block6.width, 77.0)
        self.assertEqual(self.block6.height, 77.0)
        self.assertEqual(self.block6.extra_metadata["layout_region"]["x"], 40.0)
        self.assertEqual(self.block6.extra_metadata["layout_region"]["y"], 180.0)
        self.assertEqual(self.block6.extra_metadata["layout_region"]["width"], 80.0)
        self.assertAlmostEqual(self.block6.extra_metadata["layout_region"]["height"], 32.2, delta=3.0)

        # Unmanaged Photoshop layers do not affect the managed import transaction.
        self.assertTrue(res["success"])
        self.assertEqual(res["errors"], [])
        self.assertEqual(len(res["updated_blocks"]), 6)

        # Confirm that updates list returned the actual block.id (no mismatch with DB representation)
        updated_ids = [u["id"] for u in res["updated_blocks"]]
        self.assertIn(self.block1.id, updated_ids)
        self.assertIn(self.block2.id, updated_ids)
        self.assertIn(self.block6.id, updated_ids)

    def test_point_text_export_is_explicit_opt_in(self):
        psd_path = export_page_to_psd(self.page.id, self.db, force=True, text_mode="point")
        psd = PSDImage.open(psd_path)
        text_layers = [layer for layer in psd if layer.kind == "type"]

        self.assertEqual(len(text_layers), 6)
        for layer in text_layers:
            shapes = layer.engine_dict.get("Rendered", {}).get("Shapes", {})
            child = shapes.get("Children", [])[0]
            photoshop_cookie = child.get("Cookie", {}).get("Photoshop", {})
            self.assertEqual(photoshop_cookie.get("ShapeType"), 0)


if __name__ == "__main__":
    unittest.main()
