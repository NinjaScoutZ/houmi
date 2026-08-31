import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np

from app.services.inpainter import (
    LamaONNXInpainter,
    _detect_uniform_fill_color,
    _effective_dilation_kernel,
    _effective_inpaint_context_padding,
    _find_inpaint_regions,
    _lama_uses_cuda,
    _should_use_solid_fill,
    build_automatic_page_mask,
    build_effective_page_mask,
    clean_page_text,
    get_adaptive_text_mask,
    get_or_build_effective_page_mask,
    invalidate_clean_assets,
    is_clean_asset_current,
    reclean_page_block,
    should_use_lama_inpaint,
    should_use_smart_mask,
    write_clean_manifest,
)
from app.services.text_mask import (
    MASK_MODE_COLOR_OR_COMPLEX,
    MASK_MODE_MONOCHROME_FLAT,
    classify_text_mask_mode,
    generate_monochrome_flat_text_mask,
)
from app.services.memory_cache import page_image_cache
from app.services.project_paths import inpaint_preview_asset_path, inpainted_asset_path, mask_asset_path, rendered_asset_path


class TestInpainterMaskPolicy(unittest.TestCase):
    def test_effective_page_mask_cache_reuses_matching_fingerprint(self):
        class FakeQuery:
            def __init__(self, page):
                self.page = page

            def filter(self, *_args):
                return self

            def first(self):
                return self.page

        class FakeDb:
            def __init__(self, page):
                self.page = page

            def query(self, *_args):
                return FakeQuery(self.page)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            project = SimpleNamespace(id="cache-project", settings={"local_folder": str(root)})
            block = SimpleNamespace(
                id="cache-block", block_index=0, x=5, y=5, width=10, height=10, extra_metadata={}
            )
            page = SimpleNamespace(
                id="cache-page",
                project_id=project.id,
                project=project,
                page_number=1,
                source_image_path=str(root / "source.png"),
                text_blocks=[block],
            )
            cv2.imwrite(page.source_image_path, np.full((30, 30, 3), 240, dtype=np.uint8))
            expected = np.zeros((30, 30), dtype=np.uint8)
            expected[5:15, 5:15] = 255

            with patch("app.services.inpainter.build_effective_page_mask", return_value=expected) as build:
                first = get_or_build_effective_page_mask(page.id, FakeDb(page))
                second = get_or_build_effective_page_mask(page.id, FakeDb(page))

            self.assertEqual(build.call_count, 1)
            np.testing.assert_array_equal(first, expected)
            np.testing.assert_array_equal(second, expected)

    def test_effective_page_mask_rejects_legacy_cache_without_editor_provenance(self):
        class FakeQuery:
            def __init__(self, page):
                self.page = page

            def filter(self, *_args):
                return self

            def first(self):
                return self.page

        class FakeDb:
            def __init__(self, page):
                self.page = page

            def query(self, *_args):
                return FakeQuery(self.page)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            project = SimpleNamespace(id="legacy-project", settings={"local_folder": str(root)})
            page = SimpleNamespace(
                id="legacy-page", project_id=project.id, project=project, page_number=1,
                source_image_path=str(root / "source.png"), text_blocks=[],
            )
            cv2.imwrite(page.source_image_path, np.full((20, 20, 3), 240, dtype=np.uint8))
            polluted = np.full((20, 20), 255, dtype=np.uint8)
            cv2.imwrite(str(mask_asset_path(page, "effective_mask.png")), polluted)
            manifest = mask_asset_path(page, "effective_mask_manifest.json")
            manifest.write_text('{"version":"2.5","fingerprint":"legacy"}', encoding="utf-8")
            rebuilt = np.zeros((20, 20), dtype=np.uint8)

            with patch("app.services.inpainter.build_effective_page_mask", return_value=rebuilt) as build:
                result = get_or_build_effective_page_mask(page.id, FakeDb(page))

            build.assert_called_once()
            np.testing.assert_array_equal(result, rebuilt)

    def test_effective_page_mask_returns_rebuild_when_cache_is_not_writable(self):
        class FakeQuery:
            def __init__(self, page):
                self.page = page

            def filter(self, *_args):
                return self

            def first(self):
                return self.page

        class FakeDb:
            def __init__(self, page):
                self.page = page

            def query(self, *_args):
                return FakeQuery(self.page)

        page = SimpleNamespace(id="readonly-page", project_id="project", project=SimpleNamespace(settings={}))
        rebuilt = np.zeros((12, 16), dtype=np.uint8)
        with (
            patch("app.services.inpainter.mask_asset_path", return_value=Path("missing-cache")),
            patch("app.services.inpainter.build_effective_page_mask", return_value=rebuilt),
            patch("app.services.inpainter._write_effective_page_mask_cache", side_effect=OSError("read only")),
        ):
            result = get_or_build_effective_page_mask(page.id, FakeDb(page))

        np.testing.assert_array_equal(result, rebuilt)

    def test_page_mask_composition_preserves_dense_custom_masks(self):
        class FakeQuery:
            def __init__(self, page):
                self.page = page

            def filter(self, *_args):
                return self

            def first(self):
                return self.page

        class FakeDb:
            def __init__(self, page):
                self.page = page

            def query(self, *_args):
                return FakeQuery(self.page)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            project = SimpleNamespace(id="mask-project", settings={"local_folder": str(root)})
            block = SimpleNamespace(
                id="dense-mask",
                block_index=0,
                x=30,
                y=30,
                width=40,
                height=40,
                extra_metadata={},
            )
            page = SimpleNamespace(
                id="mask-page",
                project_id=project.id,
                project=project,
                page_number=1,
                source_image_path=str(root / "source.png"),
                text_blocks=[block],
            )
            cv2.imwrite(page.source_image_path, np.full((100, 100, 3), 240, dtype=np.uint8))
            custom_path = mask_asset_path(page, f"mask_{block.id}.png")
            cv2.imwrite(str(custom_path), np.full((100, 100), 255, dtype=np.uint8))

            result = build_effective_page_mask(page.id, FakeDb(page))

            self.assertTrue(custom_path.exists())
            self.assertGreater(np.count_nonzero(result), 0)

    def test_automatic_page_mask_preview_does_not_delete_saved_masks(self):
        class FakeQuery:
            def __init__(self, page):
                self.page = page

            def filter(self, *_args):
                return self

            def first(self):
                return self.page

        class FakeDb:
            def __init__(self, page):
                self.page = page

            def query(self, *_args):
                return FakeQuery(self.page)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            project = SimpleNamespace(id="auto-project", settings={"local_folder": str(root)})
            block = SimpleNamespace(
                id="auto-block",
                block_index=0,
                x=10,
                y=10,
                width=20,
                height=20,
                extra_metadata={},
            )
            page = SimpleNamespace(
                id="auto-page",
                project_id=project.id,
                project=project,
                page_number=1,
                source_image_path=str(root / "source.png"),
                text_blocks=[block],
            )
            cv2.imwrite(page.source_image_path, np.full((60, 60, 3), 240, dtype=np.uint8))
            custom_path = mask_asset_path(page, f"mask_{block.id}.png")
            manual_path = mask_asset_path(page, "manual_mask.png")
            override_path = mask_asset_path(page, "page_mask_override.png")
            cv2.imwrite(str(custom_path), np.full((20, 20), 255, dtype=np.uint8))
            cv2.imwrite(str(manual_path), np.full((60, 60), 255, dtype=np.uint8))
            cv2.imwrite(str(override_path), np.full((60, 60), 255, dtype=np.uint8))
            automatic = np.zeros((60, 60), dtype=np.uint8)
            automatic[10:30, 10:30] = 255

            with patch("app.services.inpainter.get_automatic_block_mask", return_value=automatic):
                result = build_automatic_page_mask(page.id, FakeDb(page))

            self.assertTrue(custom_path.exists())
            self.assertTrue(manual_path.exists())
            self.assertTrue(override_path.exists())
            np.testing.assert_array_equal(result, automatic)

    def test_full_page_override_keeps_erased_automatic_regions_erased(self):
        class FakeQuery:
            def __init__(self, page):
                self.page = page

            def filter(self, *_args):
                return self

            def first(self):
                return self.page

        class FakeDb:
            def __init__(self, page):
                self.page = page

            def query(self, *_args):
                return FakeQuery(self.page)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            project = SimpleNamespace(id="override-project", settings={"local_folder": str(root)})
            block = SimpleNamespace(
                id="override-block", block_index=0, x=10, y=10, width=30, height=30, extra_metadata={}
            )
            page = SimpleNamespace(
                id="override-page",
                project_id=project.id,
                project=project,
                page_number=1,
                source_image_path=str(root / "source.png"),
                text_blocks=[block],
            )
            cv2.imwrite(page.source_image_path, np.full((60, 60, 3), 240, dtype=np.uint8))
            override = np.zeros((60, 60), dtype=np.uint8)
            override[20:25, 20:25] = 255
            cv2.imwrite(str(mask_asset_path(page, "page_mask_override.png")), override)
            automatic = np.full((60, 60), 255, dtype=np.uint8)

            with patch("app.services.inpainter.get_automatic_block_mask", return_value=automatic):
                result = build_effective_page_mask(page.id, FakeDb(page))

            np.testing.assert_array_equal(result, override)

    def test_region_reclean_rebuilds_dirty_crop_from_source_and_keeps_outer_pixels(self):
        class FakeQuery:
            def __init__(self, page):
                self.page = page

            def filter(self, *_args):
                return self

            def first(self):
                return self.page

        class FakeDb:
            def __init__(self, page):
                self.page = page
                self.commits = 0

            def query(self, *_args):
                return FakeQuery(self.page)

            def commit(self):
                self.commits += 1

        with TemporaryDirectory() as directory:
            root = Path(directory)
            project = SimpleNamespace(id="project-1", settings={})
            block = SimpleNamespace(id="block-1", block_index=0, x=150, y=150, width=50, height=50)
            page = SimpleNamespace(
                id="page-1",
                project_id=project.id,
                project=project,
                page_number=1,
                source_image_path=str(root / "source.png"),
                text_blocks=[block],
                inpainted_image_path=None,
                rendered_image_path=None,
            )
            source = np.full((300, 300, 3), 255, dtype=np.uint8)
            cv2.rectangle(source, (165, 165), (185, 185), (0, 0, 0), -1)
            cv2.imwrite(page.source_image_path, source)

            old_mask = np.zeros((50, 50), dtype=np.uint8)
            mask_path = mask_asset_path(page, "mask_block-1.png")
            cv2.imwrite(str(mask_path), old_mask)
            previous = np.full_like(source, 17)
            clean_path = inpainted_asset_path(page)
            cv2.imwrite(str(clean_path), previous)
            page.inpainted_image_path = str(clean_path)

            with patch("app.services.inpainter.PROJECTS_DIR", root / "internal"):
                write_clean_manifest(page)
                new_mask = np.zeros((50, 50), dtype=np.uint8)
                new_mask[15:36, 15:36] = 255
                cv2.imwrite(str(mask_path), new_mask)
                reclean_page_block(page.id, block.id, FakeDb(page))

                result = cv2.imread(str(clean_path))
                self.assertTrue(np.all(result[0:20, 0:20] == 17))
                self.assertFalse(np.array_equal(result[165:186, 165:186], source[165:186, 165:186]))
                self.assertTrue(is_clean_asset_current(page))

    def test_full_clean_does_not_mutate_cached_source_frame(self):
        class FakeQuery:
            def __init__(self, page):
                self.page = page

            def filter(self, *_args):
                return self

            def first(self):
                return self.page

        class FakeDb:
            def __init__(self, page):
                self.page = page

            def query(self, *_args):
                return FakeQuery(self.page)

            def commit(self):
                pass

        with TemporaryDirectory() as directory:
            root = Path(directory)
            project = SimpleNamespace(
                id="cache-project",
                settings={
                    "local_folder": str(root),
                    "cleanup_mask_strategy": "smart",
                    "force_lama_inpaint": False,
                    "default_image_inpaint_method": "telea",
                },
            )
            block = SimpleNamespace(
                id="cache-block",
                block_index=0,
                x=20,
                y=20,
                width=80,
                height=50,
                extra_metadata={},
            )
            page = SimpleNamespace(
                id="cache-page",
                project_id=project.id,
                project=project,
                page_number=1,
                source_image_path=str(root / "source.png"),
                text_blocks=[block],
                inpainted_image_path=None,
                rendered_image_path=None,
            )
            source = np.full((100, 140, 3), 232, dtype=np.uint8)
            cv2.putText(source, "TXT", (28, 56), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
            cv2.imwrite(page.source_image_path, source)
            page_image_cache.set_source_image(page.id, source)

            try:
                with patch("app.services.inpainter.PROJECTS_DIR", root / "internal"):
                    clean_page_text(page.id, FakeDb(page))

                np.testing.assert_array_equal(page_image_cache.get_source_image(page.id), source)
            finally:
                page_image_cache.invalidate_page(page.id)

    def test_clean_manifest_invalidates_missing_mask_and_outputs(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            project = SimpleNamespace(id="project-1", settings={"local_folder": str(root)})
            block = SimpleNamespace(id="block-1", block_index=0, x=2, y=3, width=20, height=10)
            page = SimpleNamespace(
                id="page-1",
                project_id=project.id,
                project=project,
                page_number=1,
                source_image_path=str(root / "source.png"),
                text_blocks=[block],
                inpainted_image_path=None,
                rendered_image_path=None,
            )
            Path(page.source_image_path).write_bytes(b"source")
            custom_mask = mask_asset_path(page, "mask_block-1.png")
            custom_mask.write_bytes(b"mask-v1")
            clean_path = inpainted_asset_path(page)
            preview_path = inpaint_preview_asset_path(page)
            render_path = rendered_asset_path(page)
            clean_path.write_bytes(b"clean")
            preview_path.write_bytes(b"preview")
            render_path.write_bytes(b"render")
            page.inpainted_image_path = str(clean_path)
            page.rendered_image_path = str(render_path)

            with patch("app.services.inpainter.PROJECTS_DIR", root / "internal"):
                write_clean_manifest(page)
                self.assertTrue(is_clean_asset_current(page))

                custom_mask.unlink()
                self.assertFalse(is_clean_asset_current(page))

                removed = invalidate_clean_assets(page)

            self.assertGreaterEqual(removed, 3)
            self.assertFalse(clean_path.exists())
            self.assertFalse(preview_path.exists())
            self.assertFalse(render_path.exists())
            self.assertIsNone(page.inpainted_image_path)
            self.assertIsNone(page.rendered_image_path)

    def test_detects_uniform_gray_balloon_background(self):
        crop = np.full((80, 120, 3), 232, dtype=np.uint8)
        mask = np.zeros((80, 120), dtype=np.uint8)
        cv2.putText(crop, "TXT", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
        cv2.putText(mask, "TXT", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, 255, 2)

        self.assertEqual(_detect_uniform_fill_color(crop, mask), [232, 232, 232])

    def test_routes_flat_monochrome_balloon_to_black_mask_system(self):
        crop = np.full((100, 180, 3), 240, dtype=np.uint8)
        cv2.putText(crop, "TXT", (22, 67), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (18, 18, 18), 3, cv2.LINE_AA)

        mode, diagnostics = classify_text_mask_mode(crop)
        mask = generate_monochrome_flat_text_mask(crop, dilation_kernel=2)

        self.assertEqual(mode, MASK_MODE_MONOCHROME_FLAT)
        self.assertGreater(diagnostics["flat_ratio"], 0.55)
        self.assertGreater(np.count_nonzero(mask), 0)
        self.assertLess(np.count_nonzero(mask) / mask.size, 0.30)

    def test_monochrome_mask_keeps_edge_near_text_separate_from_jpeg_noise(self):
        crop = np.full((120, 260, 3), 244, dtype=np.uint8)
        expected_text = np.zeros(crop.shape[:2], dtype=np.uint8)
        cv2.putText(crop, "EDGE", (72, 78), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (20, 20, 20), 3, cv2.LINE_AA)
        cv2.putText(expected_text, "EDGE", (72, 78), cv2.FONT_HERSHEY_SIMPLEX, 1.4, 255, 3, cv2.LINE_AA)

        # Simulate a dark exterior and a faint compression bridge. The old
        # 2-level threshold connected the final glyph to this edge mass and
        # rejected the whole connected component.
        crop[:, 245:] = 0
        crop[58:61, 218:245] = 241
        mask = generate_monochrome_flat_text_mask(crop, dilation_kernel=1)

        dark_text = (expected_text > 0) & (cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) < 235)
        covered = np.count_nonzero((mask > 0) & dark_text)
        exterior_coverage = np.count_nonzero(mask[:, 245:])

        self.assertGreater(covered / max(1, np.count_nonzero(dark_text)), 0.99)
        self.assertEqual(exterior_coverage, 0)

    def test_routes_colored_or_textured_crop_to_complex_mask_system(self):
        colored = np.full((100, 180, 3), (238, 238, 238), dtype=np.uint8)
        colored[:, :90] = (40, 80, 220)
        checker = np.indices((100, 180)).sum(axis=0) % 2
        textured = np.repeat((checker * 210 + 20)[:, :, None].astype(np.uint8), 3, axis=2)

        colored_mode, _ = classify_text_mask_mode(colored)
        textured_mode, _ = classify_text_mask_mode(textured)

        self.assertEqual(colored_mode, MASK_MODE_COLOR_OR_COMPLEX)
        self.assertEqual(textured_mode, MASK_MODE_COLOR_OR_COMPLEX)

    def test_rejects_textured_background(self):
        rng = np.random.default_rng(7)
        crop = rng.integers(0, 256, (80, 120, 3), dtype=np.uint8)
        mask = np.zeros((80, 120), dtype=np.uint8)

        self.assertIsNone(_detect_uniform_fill_color(crop, mask))

    def test_custom_editor_mask_never_uses_solid_fill_shortcut(self):
        self.assertTrue(_should_use_solid_fill(True, False))
        self.assertFalse(_should_use_solid_fill(True, True))
        self.assertFalse(_should_use_solid_fill(False, False))

    def test_lama_output_is_not_scaled_twice(self):
        class FakeSession:
            def run(self, *_args, **_kwargs):
                return [np.full((1, 3, 512, 512), 232.0, dtype=np.float32)]

        lama = LamaONNXInpainter.__new__(LamaONNXInpainter)
        lama.session = FakeSession()
        lama.input_name = "image"
        lama.mask_name = "mask"
        image = np.zeros((20, 20, 3), dtype=np.uint8)
        mask = np.full((20, 20), 255, dtype=np.uint8)

        result = lama.inpaint(image, mask)

        self.assertTrue(np.all(result == 232))

    def test_cpu_fallback_is_not_used_for_interactive_lama(self):
        class FakeSession:
            def get_providers(self):
                return ["CPUExecutionProvider"]

        lama = LamaONNXInpainter.__new__(LamaONNXInpainter)
        lama.session = FakeSession()
        self.assertFalse(_lama_uses_cuda(lama))

    def test_cleanup_profile_selects_smart_mask_and_lama_explicitly(self):
        settings = {
            "cleanup_mask_strategy": "smart",
            "force_lama_inpaint": True,
            "process_by_text_areas": False,
        }
        self.assertTrue(should_use_smart_mask(settings))
        self.assertTrue(should_use_lama_inpaint(settings))

    def test_fast_profile_uses_box_mask_and_telea(self):
        settings = {
            "cleanup_mask_strategy": "box",
            "force_lama_inpaint": False,
            "default_image_inpaint_method": "LamaInpaint",
        }
        self.assertFalse(should_use_smart_mask(settings))
        self.assertFalse(should_use_lama_inpaint(settings))

    def test_engine_override_resolution(self):
        from app.services.inpainter import resolve_inpaint_engine_name
        self.assertEqual(resolve_inpaint_engine_name({"inpaint_engine": "LamaInpaint"}), "lama")
        self.assertEqual(resolve_inpaint_engine_name({"inpaint_engine": "lama_onnx"}), "lama")
        self.assertEqual(resolve_inpaint_engine_name({"inpaint_engine": "telea"}), "telea")
        self.assertTrue(resolve_inpaint_engine_name({"inpaint_engine": "LamaInpaint"}) in {"manga_cleaner", "lama", "mat"})

    def test_legacy_projects_keep_adaptive_lama_defaults(self):
        self.assertTrue(should_use_smart_mask({}))
        self.assertTrue(should_use_lama_inpaint({}))

    def test_dilation_is_capped_by_text_box_size_and_kept_odd(self):
        self.assertEqual(_effective_dilation_kernel(24, 100, 50), 23)
        self.assertEqual(_effective_dilation_kernel(24, 200, 100), 23)
        self.assertEqual(_effective_dilation_kernel(5, 200, 100), 5)

    def test_grouping_reduces_inference_regions_without_expanding_real_mask(self):
        mask = np.zeros((80, 120), dtype=np.uint8)
        cv2.rectangle(mask, (20, 30), (25, 40), 255, -1)
        cv2.rectangle(mask, (33, 30), (38, 40), 255, -1)
        cv2.rectangle(mask, (46, 30), (51, 40), 255, -1)
        original = mask.copy()

        raw_contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        regions = _find_inpaint_regions(mask)

        self.assertEqual(len(raw_contours), 3)
        self.assertEqual(len(regions), 1)
        np.testing.assert_array_equal(mask, original)

    def test_context_padding_scales_for_wide_text_regions_without_changing_mask(self):
        # A 32 px fixed crop was not enough for wide dialogue strips. The
        # adaptive margin is for model context only; the input mask is still
        # unchanged by _find_inpaint_regions and is blended back precisely.
        self.assertEqual(_effective_inpaint_context_padding(32, 440, 100), 106)
        self.assertEqual(_effective_inpaint_context_padding(0, 10, 10), 64)
        self.assertEqual(_effective_inpaint_context_padding(220, 440, 100), 220)

    def test_tight_ocr_box_keeps_edge_glyph_without_masking_balloon_outline(self):
        image = np.full((160, 240, 3), 255, dtype=np.uint8)
        cv2.rectangle(image, (20, 20), (220, 140), (0, 0, 0), 2)
        cv2.putText(
            image,
            "TEXT",
            (48, 95),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.7,
            (0, 0, 0),
            4,
            cv2.LINE_AA,
        )

        # The OCR box deliberately cuts through the first T.
        mask = get_adaptive_text_mask(image, 55, 52, 181, 103, 3)

        self.assertGreater(np.count_nonzero(mask[:, 45:78]), 100)
        self.assertEqual(np.count_nonzero(mask[19:23, :]), 0)


if __name__ == "__main__":
    unittest.main()
    build_automatic_page_mask,
    build_effective_page_mask,
