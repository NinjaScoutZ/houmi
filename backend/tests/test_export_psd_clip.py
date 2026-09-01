"""
Comprehensive Unit Test Suite for Native 8BPS PSD and Clip Studio Paint Exporters
Module: backend/tests/test_export_psd_clip.py
"""

import io
import os
import struct
import sqlite3
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.all_models import Project, Page, TextBlock
from app.services.export_psd_clip import (
    PsdPackBits,
    Native8BPSWriter,
    ClipStudioWriter,
    export_page_to_native_psd_clip,
)


class TestNativePsdAndClipExport(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

        self.source_img_path = self.temp_path / "source.png"
        self.inpainted_img_path = self.temp_path / "inpainted.png"
        img = Image.new("RGBA", (400, 600), (255, 255, 255, 255))
        img.save(self.source_img_path)
        img.save(self.inpainted_img_path)

        self.engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

        self.project = Project(id="proj-001", name="Houmi Manga Project")
        self.db.add(self.project)

        self.page = Page(
            id="page-001",
            project_id=self.project.id,
            page_number=1,
            width=400,
            height=600,
            source_image_path=str(self.source_img_path),
            inpainted_image_path=str(self.inpainted_img_path),
        )
        self.db.add(self.page)

        self.block1 = TextBlock(
            id="blk-001",
            page_id=self.page.id,
            block_index=1,
            x=20.0,
            y=30.0,
            width=120.0,
            height=60.0,
            source_text="テスト文章",
            translation="ทดสอบข้อความภาษาไทย",
            font_family="Prompt",
            font_size=18.0,
        )
        self.db.add(self.block1)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.temp_dir.cleanup()

    def test_packbits_compression(self):
        data = b"ABCDEFG"
        encoded = PsdPackBits.encode_scanline(data)
        self.assertEqual(encoded[0], len(data) - 1)
        self.assertEqual(encoded[1:], data)

        data_rep = b"A" * 10
        encoded_rep = PsdPackBits.encode_scanline(data_rep)
        self.assertEqual(encoded_rep[0], (-9) & 0xFF)
        self.assertEqual(encoded_rep[1], ord(b"A"))

    def test_native_8bps_psd_generation(self):
        writer = Native8BPSWriter(width=400, height=600, dpi=600.0)
        writer.add_layer("00_Raw_Scan", image_rgba=Image.open(self.source_img_path))
        writer.add_layer("04_Text_Block", text_data={
            "text": "Hello Manga",
            "font_family": "CCWildWords",
            "font_size": 20.0,
            "x": 20.0,
            "y": 30.0,
        })

        bio = io.BytesIO()
        writer.write(bio)
        psd_bytes = bio.getvalue()

        self.assertTrue(psd_bytes.startswith(b"8BPS"))
        self.assertIn(b"\x03\xed", psd_bytes)
        self.assertIn(b"TySh", psd_bytes)

    def test_clip_studio_sqlite_generation(self):
        clip_path = self.temp_path / "test_output.clip"
        ClipStudioWriter.export_clip(
            output_path=clip_path,
            width=400,
            height=600,
            dpi=600.0,
            text_blocks=[{"text": "ทดสอบ", "font_family": "Kanit", "font_size": 16.0, "x": 10, "y": 20, "width": 50, "height": 30}],
        )

        self.assertTrue(clip_path.exists())
        conn = sqlite3.connect(str(clip_path))
        cursor = conn.cursor()
        cursor.execute("SELECT Width, Height FROM Canvas WHERE CanvasId = 1")
        self.assertEqual(cursor.fetchone(), (400, 600))
        conn.close()
