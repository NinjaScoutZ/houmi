import unittest
import numpy as np
from PIL import Image
import tempfile
from pathlib import Path
from app.services.ocr import _parse_gemini_grid_response
from app.services.smart_balloon import extract_balloon_text_style, rgb_to_hex


class TestColorSystem(unittest.TestCase):
    def test_pdf_ocr_color_parsing(self):
        """Verify that color attributes (text color, stroke color, stroke width, gradients) from PDF OCR are parsed correctly."""
        mock_response = '''
[
  {
    "box_id": "BOX_001_A1B2C3D4",
    "text": "ตายซะเถอะ!",
    "balloon_type": "shout",
    "color_hex": "#FF0000",
    "stroke_color_hex": "#FFFFFF",
    "stroke_width_px": 4
  },
  {
    "box_id": "BOX_002_E5F6A7B8",
    "text": "อะไรกัน...",
    "balloon_type": "whisper",
    "color_hex": "#222222",
    "stroke_color_hex": null,
    "stroke_width_px": 0
  },
  {
    "box_id": "BOX_003_12345678",
    "text": "ドドド",
    "balloon_type": "sfx",
    "color_hex": "#FFCC00",
    "stroke_color_hex": "#000000",
    "stroke_width_px": 6,
    "gradient_colors": ["#FFCC00", "#FF3300"]
  }
]
'''
        expected_ids = {"BOX_001_A1B2C3D4", "BOX_002_E5F6A7B8", "BOX_003_12345678"}
        parsed = _parse_gemini_grid_response(mock_response, expected_ids)

        self.assertEqual(len(parsed), 3)
        self.assertEqual(parsed["BOX_001_A1B2C3D4"]["color_hex"], "#FF0000")
        self.assertEqual(parsed["BOX_001_A1B2C3D4"]["stroke_color_hex"], "#FFFFFF")
        self.assertEqual(parsed["BOX_001_A1B2C3D4"]["stroke_width_px"], 4)
        self.assertEqual(parsed["BOX_003_12345678"]["gradient_colors"], ["#FFCC00", "#FF3300"])

    def test_local_cv_color_and_stroke_extraction(self):
        """Verify computer vision color extraction from image crop."""
        # Create a synthetic white speech balloon with distinct black text
        h, w = 100, 100
        crop = np.ones((h, w, 3), dtype=np.uint8) * 255  # White BG

        # Draw black text in center
        crop[30:70, 30:70] = [0, 0, 0]

        style = extract_balloon_text_style(crop, (0, 0, w, h))

        self.assertIn("text_color", style)
        self.assertIn("bg_color", style)
        self.assertEqual(style["text_color"].lower(), "#000000")
        self.assertEqual(style["bg_color"].lower(), "#ffffff")

    def test_pdf_export_rgba_alpha_to_white_compositing(self):
        """Verify that RGBA images with transparency composite over white rather than turning black."""
        with tempfile.TemporaryDirectory() as temp_dir:
            img_rgba = Image.new("RGBA", (100, 100), (0, 0, 0, 0))  # Fully transparent
            out_pdf = Path(temp_dir) / "test_alpha.pdf"

            # Composite over white
            bg = Image.new("RGB", img_rgba.size, (255, 255, 255))
            bg.paste(img_rgba, mask=img_rgba.split()[3])

            # Pixel must be white (255, 255, 255), not black (0, 0, 0)
            self.assertEqual(bg.getpixel((50, 50)), (255, 255, 255))

            bg.save(out_pdf, "PDF", resolution=150.0)
            self.assertTrue(out_pdf.exists())
            self.assertGreater(out_pdf.stat().st_size, 100)


if __name__ == "__main__":
    unittest.main()
