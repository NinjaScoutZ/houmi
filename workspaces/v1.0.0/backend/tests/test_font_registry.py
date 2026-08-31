import os
import unittest
from pathlib import Path
from unittest.mock import patch
from app.services.font_registry import font_registry, FontRegistry, FontRegistryEntry

class TestFontRegistry(unittest.TestCase):
    def setUp(self):
        # Clear PRODUCTION_MODE env var before each test
        if "PRODUCTION_MODE" in os.environ:
            del os.environ["PRODUCTION_MODE"]

    def test_resolve_available_font(self):
        # Tahoma is widely available on Windows
        entry = font_registry.resolve_font("Tahoma", bold=False)
        self.assertEqual(entry.family, "Tahoma")
        self.assertFalse(entry.is_fallback)
        self.assertTrue(entry.file_path.exists())
        self.assertNotEqual(entry.fingerprint, "missing")

    def test_resolve_missing_font_normal_mode(self):
        # A font that does not exist on Windows system
        entry = font_registry.resolve_font("SomeNonExistentFontName", bold=False)
        # Should fall back to Tahoma or Arial
        self.assertTrue(entry.is_fallback)
        self.assertIn(entry.family, ["Tahoma", "Arial"])

    def test_arialmt_and_arial_boldmt_resolution(self):
        # ArialMT is a PostScript name alias for Arial. It must resolve as exact match (no fallback).
        entry = font_registry.resolve_font("ArialMT", bold=False)
        self.assertEqual(entry.family, "Arial")
        self.assertFalse(entry.is_fallback)

        # Arial-BoldMT is PostScript name alias for Arial Bold. It must resolve as exact match (no fallback).
        entry_bold = font_registry.resolve_font("Arial-BoldMT", bold=False)
        self.assertEqual(entry_bold.family, "Arial")
        self.assertEqual(entry_bold.style, "bold")
        self.assertFalse(entry_bold.is_fallback)

    def test_notosansthai_with_and_without_asset(self):
        # 1. Non-existent font should map to Tahoma with is_fallback=True
        entry = font_registry.resolve_font("NonExistentThaiFont999", bold=False)
        self.assertEqual(entry.family, "Tahoma")
        self.assertTrue(entry.is_fallback)

        # 2. Smart aliases for Thai comic fonts (e.g. TF PHETAI -> TF Phethai)
        entry_phetai = font_registry.resolve_font("TF PHETAI")
        self.assertIn(entry_phetai.family, ["TF Phethai", "Tahoma"])
        if entry_phetai.family == "TF Phethai":
            self.assertFalse(entry_phetai.is_fallback)

        # 3. With asset (mocked/registered): NotoSansThai should resolve exactly
        reg = FontRegistry()
        mock_entry = FontRegistryEntry(
            stable_id="notosansthai",
            family="Noto Sans Thai",
            postscript_name="NotoSansThai-Regular",
            file_path=Path("C:/Windows/Fonts/tahoma.ttf"), # dummy existing file
            style="regular",
            fingerprint="dummy_hash"
        )
        reg.registry["noto sans thai_regular"] = mock_entry
        reg.aliases["notosansthai"] = ("Noto Sans Thai", "regular")
        reg.aliases["noto sans thai"] = ("Noto Sans Thai", "regular")
        
        resolved = reg.resolve_font("NotoSansThai", bold=False)
        self.assertEqual(resolved.family, "Noto Sans Thai")
        self.assertFalse(resolved.is_fallback)

    def test_style_fallback_is_fallback(self):
        # Requesting bold-italic on Tahoma should fall back to regular or bold since Tahoma bold-italic is usually not in Windows standard fonts
        entry = font_registry.resolve_font("Tahoma", bold=True, italic=True)
        self.assertTrue(entry.is_fallback)

    def test_regular_style_fallback_preserves_family_when_only_bold_exists(self):
        reg = FontRegistry()
        reg.registry.clear()
        reg.aliases.clear()
        mock_entry = FontRegistryEntry(
            stable_id="thsarabunnew bold",
            family="TH Sarabun New",
            postscript_name="THSarabunNew-Bold",
            file_path=Path("dummy_path/THSarabunNew-Bold.ttf"),
            style="bold",
            fingerprint="dummy_hash",
        )
        reg.registry["th sarabun new_bold"] = mock_entry
        reg.aliases["th sarabun new"] = ("TH Sarabun New", "bold")

        resolved = reg.resolve_font("TH Sarabun New", bold=False)
        self.assertEqual(resolved.family, "TH Sarabun New")
        self.assertEqual(resolved.postscript_name, "THSarabunNew-Bold")

    def test_style_classifier_recognizes_native_face_names(self):
        self.assertEqual(FontRegistry._classify_style("Regular", "Example-Bold"), "bold")
        self.assertEqual(
            FontRegistry._classify_style("Regular", "Example-BoldItalic"),
            "bold_italic",
        )
        self.assertEqual(FontRegistry._classify_style("Oblique"), "italic")

    def test_get_family_details_and_variants(self):
        details = font_registry.get_family_details()
        self.assertIsInstance(details, dict)
        self.assertIn("Tahoma", details)
        tahoma_info = details["Tahoma"]
        self.assertEqual(tahoma_info["family"], "Tahoma")
        self.assertIn("regular", tahoma_info["styles"])
        self.assertTrue(len(tahoma_info["variants"]) > 0)
        first_variant = tahoma_info["variants"][0]
        self.assertIn("variant_id", first_variant)
        self.assertIn("weight", first_variant)
        self.assertIn("postscript_name", first_variant)

    def test_get_variant_by_id(self):
        # By stable_id
        entry = font_registry.get_variant_by_id("tahoma")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.family, "Tahoma")

        # By PostScript name
        entry_ps = font_registry.get_variant_by_id("ArialMT")
        self.assertIsNotNone(entry_ps)
        self.assertEqual(entry_ps.family, "Arial")

    def test_custom_font_registration(self):
        reg = FontRegistry()
        mock_entry = FontRegistryEntry(
            stable_id="custom_font_regular",
            family="Custom Comic",
            postscript_name="CustomComic-Regular",
            file_path=Path("C:/Windows/Fonts/tahoma.ttf"),
            style="regular",
            fingerprint="custom_hash",
            weight=400,
            full_name="Custom Comic Regular",
            category="custom"
        )
        reg.register_entry(mock_entry, category="custom")
        
        details = reg.get_family_details()
        self.assertIn("Custom Comic", details)
        self.assertEqual(details["Custom Comic"]["category"], "custom")
        
        resolved = reg.resolve_font("Custom Comic")
        self.assertEqual(resolved.family, "Custom Comic")
        self.assertFalse(resolved.is_fallback)

    def test_font_load_failure_production_mode(self):
        from app.services.renderer import get_font_handle
        os.environ["PRODUCTION_MODE"] = "1"
        
        # We mock ImageFont.truetype to raise an OSError when called.
        # This simulates a corrupt font file loading failure after the valid font resolves successfully.
        with patch("PIL.ImageFont.truetype", side_effect=OSError("File not found or corrupt")):
            with self.assertRaises(ValueError) as ctx:
                get_font_handle("Tahoma", 12)
            
            # Confirm that the error message is specifically the Production Font Error on file load path
            self.assertIn("Production Font Error: Failed to load font file", str(ctx.exception))
            self.assertIn("File not found or corrupt", str(ctx.exception))

if __name__ == "__main__":
    unittest.main()

