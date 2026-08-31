import base64
import unittest
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np
from fastapi import BackgroundTasks, UploadFile

from app.routes.pipeline import (
    _canonicalize_uploaded_mask,
    _encode_page_mask_data_url,
    get_block_mask,
    save_block_mask,
    save_page_effective_mask_route,
)
from app.services.inpainter import _clip_auto_mask_to_balloon, fill_mask_holes, get_automatic_block_mask


def _png_bytes(image: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise AssertionError("Unable to encode test PNG")
    return encoded.tobytes()


class MaskEditorContractTests(unittest.TestCase):
    def test_force_auto_preview_preserves_saved_custom_mask(self):
        class FakeQuery:
            def __init__(self, value):
                self.value = value

            def filter(self, *_args):
                return self

            def first(self):
                return self.value

        class FakeDb:
            def __init__(self, block):
                self.block = block

            def query(self, *_args):
                return FakeQuery(self.block)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.png"
            source = np.full((80, 80, 3), 240, dtype=np.uint8)
            cv2.imwrite(str(source_path), source)
            project = SimpleNamespace(settings={})
            page = SimpleNamespace(project=project, source_image_path=str(source_path))
            block = SimpleNamespace(
                id="block-1", page=page, x=30, y=30, width=10, height=10, extra_metadata={},
            )
            custom_path = root / "mask_block-1.png"
            saved_mask = np.full((80, 80), 255, dtype=np.uint8)
            cv2.imwrite(str(custom_path), saved_mask)
            db = FakeDb(block)

            with patch("app.services.project_paths.mask_asset_path", return_value=custom_path):
                saved_response = get_block_mask(block.id, force_auto=False, db=db)
                with patch("app.routes.pipeline.get_automatic_block_mask", return_value=np.zeros((80, 80), dtype=np.uint8)):
                    auto_response = get_block_mask(block.id, force_auto=True, db=db)

            saved_payload = base64.b64decode(saved_response["mask"].split(",", 1)[1])
            auto_payload = base64.b64decode(auto_response["mask"].split(",", 1)[1])
            saved_result = cv2.imdecode(np.frombuffer(saved_payload, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
            auto_result = cv2.imdecode(np.frombuffer(auto_payload, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)

            self.assertTrue(custom_path.exists())
            self.assertTrue(np.all(saved_result == 255))
            self.assertTrue(np.all(auto_result == 0))

    def test_automatic_block_mask_uses_editor_layout_crop(self):
        image = np.full((100, 120, 3), 240, dtype=np.uint8)
        block = SimpleNamespace(
            x=50,
            y=40,
            width=10,
            height=10,
            balloon_type="sfx",
            extra_metadata={
                "layout_region": {
                    "x": 30,
                    "y": 20,
                    "width": 50,
                    "height": 50,
                    "shape": "sfx",
                }
            },
        )

        def routed(crop, dilation_kernel):
            self.assertEqual(crop.shape[:2], (100, 110))
            return np.full(crop.shape[:2], 255, dtype=np.uint8), "monochrome_flat", {}

        with patch("app.services.text_mask.generate_routed_text_mask", side_effect=routed):
            mask = get_automatic_block_mask(image, block, {"mask_dilation_kernel": 3})

        self.assertEqual(mask.shape, image.shape[:2])
        self.assertGreater(np.count_nonzero(mask), 0)

    def test_auto_mask_is_clipped_to_confirmed_balloon_geometry(self):
        mask = np.full((20, 20), 255, dtype=np.uint8)
        block = SimpleNamespace(
            balloon_type="bubble",
            extra_metadata={
                "layout_region": {
                    "source": "balloon_interior",
                    "shape": "bubble",
                    "x": 4,
                    "y": 4,
                    "width": 12,
                    "height": 12,
                    "safe_margin": 0,
                }
            },
        )
        clipped = _clip_auto_mask_to_balloon(block, mask, 20, 20)
        self.assertEqual(int(clipped[0, 0]), 0)
        self.assertEqual(int(clipped[10, 10]), 255)

    def test_auto_mask_accepts_user_segmented_balloon_geometry(self):
        mask = np.full((30, 30), 255, dtype=np.uint8)
        block = SimpleNamespace(
            x=12,
            y=12,
            width=4,
            height=4,
            balloon_type="bubble",
            extra_metadata={
                "layout_region": {
                    "source": "manual",
                    "shape": "bubble",
                    "x": 5,
                    "y": 5,
                    "width": 20,
                    "height": 20,
                    "safe_margin": 0,
                }
            },
        )

        clipped = _clip_auto_mask_to_balloon(block, mask, 30, 30)

        self.assertEqual(int(clipped[15, 15]), 255)
        self.assertEqual(int(clipped[15, 7]), 255)
        self.assertEqual(int(clipped[0, 0]), 0)

    def test_auto_mask_without_confirmed_balloon_is_limited_to_source_bbox(self):
        mask = np.full((20, 20), 255, dtype=np.uint8)
        block = SimpleNamespace(
            x=5, y=6, width=7, height=8, balloon_type="bubble", extra_metadata={}
        )
        clipped = _clip_auto_mask_to_balloon(block, mask, 20, 20)
        self.assertEqual(int(np.count_nonzero(clipped)), 56)
        self.assertEqual(int(clipped[0, 0]), 0)
        self.assertEqual(int(clipped[8, 8]), 255)

    def test_fill_mask_holes_does_not_fill_whitespace_between_connected_lines(self):
        mask = np.zeros((24, 30), dtype=np.uint8)
        cv2.rectangle(mask, (3, 3), (26, 6), 255, -1)
        cv2.rectangle(mask, (3, 16), (26, 19), 255, -1)
        cv2.rectangle(mask, (3, 3), (6, 19), 255, -1)

        filled = fill_mask_holes(mask)

        self.assertEqual(int(filled[10, 15]), 0)
        np.testing.assert_array_equal(filled, mask)

    def test_fill_mask_holes_fills_only_enclosed_counter(self):
        mask = np.zeros((20, 20), dtype=np.uint8)
        cv2.rectangle(mask, (4, 4), (15, 15), 255, 2)

        filled = fill_mask_holes(mask)

        self.assertEqual(int(filled[10, 10]), 255)
        self.assertEqual(int(filled[1, 1]), 0)

    def test_mask_save_recleans_existing_clean_base_even_without_explicit_reclean(self):
        class FakeQuery:
            def __init__(self, value):
                self.value = value

            def filter(self, *_args):
                return self

            def first(self):
                return self.value

        class FakeDb:
            def __init__(self, block):
                self.block = block
                self.commits = 0

            def query(self, *_args):
                return FakeQuery(self.block)

            def commit(self):
                self.commits += 1

        with TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.png"
            cv2.imwrite(str(source_path), np.full((60, 60, 3), 240, dtype=np.uint8))
            project = SimpleNamespace(id="project-1", settings={"local_folder": str(root)})
            page = SimpleNamespace(id="page-1", project=project, source_image_path=str(source_path))
            block = SimpleNamespace(id="block-1", page=page, x=10, y=10, width=10, height=10, extra_metadata={})
            upload = UploadFile(filename="mask.png", file=BytesIO(_png_bytes(np.full((50, 50), 255, dtype=np.uint8))))
            background_tasks = BackgroundTasks()
            db = FakeDb(block)

            with (
                patch("app.services.project_paths.mask_asset_path", return_value=root / "mask_block-1.png"),
                patch("app.routes.pipeline.is_clean_asset_current", return_value=True),
                patch("app.routes.pipeline.reclean_page_block") as reclean,
            ):
                response = save_block_mask(
                    block_id=block.id,
                    background_tasks=background_tasks,
                    file=upload,
                    mask=None,
                    reclean=False,
                    allow_full_page=True,
                    engine=None,
                    db=db,
                )

            self.assertEqual(response["clean_mode"], "region_background")
            self.assertEqual(len(background_tasks.tasks), 1)
            self.assertEqual(db.commits, 1)
            reclean.assert_not_called()

    def test_block_mask_save_replaces_its_crop_in_existing_page_override(self):
        class FakeQuery:
            def __init__(self, value):
                self.value = value

            def filter(self, *_args):
                return self

            def first(self):
                return self.value

        class FakeDb:
            def __init__(self, block):
                self.block = block

            def query(self, *_args):
                return FakeQuery(self.block)

            def commit(self):
                pass

        with TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "source.png"
            cv2.imwrite(str(source_path), np.full((100, 100, 3), 240, dtype=np.uint8))
            project = SimpleNamespace(settings={})
            page = SimpleNamespace(
                id="page-1", project=project, source_image_path=str(source_path), width=100, height=100,
            )
            block = SimpleNamespace(id="block-1", page=page, x=40, y=40, width=10, height=10, extra_metadata={})
            override_path = root / "page_mask_override.png"
            cv2.imwrite(str(override_path), np.full((100, 100), 255, dtype=np.uint8))
            upload = UploadFile(filename="mask.png", file=BytesIO(_png_bytes(np.zeros((70, 70), dtype=np.uint8))))

            def resolve_mask_path(_page, name):
                return root / name

            with (
                patch("app.services.project_paths.mask_asset_path", side_effect=resolve_mask_path),
                patch("app.routes.pipeline.is_clean_asset_current", return_value=True),
            ):
                save_block_mask(
                    block_id=block.id,
                    background_tasks=BackgroundTasks(),
                    file=upload,
                    mask=None,
                    reclean=True,
                    allow_full_page=True,
                    engine=None,
                    db=FakeDb(block),
                )

            updated = cv2.imread(str(override_path), cv2.IMREAD_GRAYSCALE)
            self.assertTrue(np.all(updated[10:80, 10:80] == 0))
            self.assertEqual(int(updated[0, 0]), 255)

    def test_fast_save_persists_and_marks_clean_stale_without_deleting_it(self):
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
            override_path = Path(directory) / "page_mask_override.png"
            page = SimpleNamespace(id="page-1")
            db = FakeDb(page)
            binary = np.array([[0, 255]], dtype=np.uint8)
            upload = UploadFile(filename="mask.png", file=BytesIO(_png_bytes(binary)))

            with (
                patch("app.services.project_paths.mask_asset_path", return_value=override_path),
                patch("app.routes.pipeline.mark_clean_assets_stale") as mark_stale,
                patch("app.routes.pipeline.invalidate_clean_assets") as delete_clean,
                patch("app.routes.pipeline.clean_page_text") as clean,
            ):
                response = save_page_effective_mask_route(
                    page_id=page.id,
                    background_tasks=BackgroundTasks(),
                    file=upload,
                    mask=None,
                    reclean=False,
                    return_mask=False,
                    engine=None,
                    db=db,
                )

            self.assertEqual(response["status"], "success")
            self.assertTrue(override_path.exists())
            mark_stale.assert_called_once_with(page)
            delete_clean.assert_not_called()
            clean.assert_not_called()
            self.assertEqual(db.commits, 1)

    def test_block_mask_save_uses_page_dimensions_without_decoding_source(self):
        class FakeQuery:
            def __init__(self, block):
                self.block = block

            def filter(self, *_args):
                return self

            def first(self):
                return self.block

        class FakeDb:
            def __init__(self, block):
                self.block = block
                self.commits = 0

            def query(self, *_args):
                return FakeQuery(self.block)

            def commit(self):
                self.commits += 1

        with TemporaryDirectory() as directory:
            root = Path(directory)
            source_path = root / "large-source.png"
            source_path.write_bytes(b"image-header-is-not-decoded")
            project = SimpleNamespace(id="project-fast-save", settings={"local_folder": str(root)})
            page = SimpleNamespace(
                id="page-fast-save",
                project=project,
                source_image_path=str(source_path),
                width=60,
                height=60,
            )
            block = SimpleNamespace(
                id="block-fast-save", page=page, x=10, y=10, width=10, height=10, extra_metadata={}
            )
            upload = UploadFile(
                filename="mask.png",
                file=BytesIO(_png_bytes(np.full((50, 50), 255, dtype=np.uint8))),
            )
            db = FakeDb(block)

            with (
                patch("app.services.project_paths.mask_asset_path", return_value=root / "mask.png"),
                patch("app.routes.pipeline.is_clean_asset_current", return_value=False),
                patch("app.routes.pipeline.cv2.imread", side_effect=AssertionError("source image decoded")),
            ):
                response = save_block_mask(
                    block_id=block.id,
                    background_tasks=BackgroundTasks(),
                    file=upload,
                    mask=None,
                    reclean=False,
                    allow_full_page=True,
                    engine=None,
                    db=db,
                )

            self.assertEqual(response["status"], "success")
            self.assertEqual(response["clean_mode"], "stale_base_preserved")
            self.assertEqual(db.commits, 1)

    def test_editor_overlay_is_transparent_outside_selected_pixels(self):
        binary = np.array([[0, 255]], dtype=np.uint8)

        data_url = _encode_page_mask_data_url(binary, overlay=True)
        encoded = base64.b64decode(data_url.split(",", 1)[1])
        overlay = cv2.imdecode(np.frombuffer(encoded, dtype=np.uint8), cv2.IMREAD_UNCHANGED)

        self.assertEqual(overlay.shape, (1, 2, 4))
        self.assertEqual(overlay[0, 0].tolist(), [0, 0, 0, 0])
        self.assertEqual(overlay[0, 1].tolist(), [68, 68, 239, 230])

    def test_rgba_overlay_uses_color_and_alpha_without_masking_black_canvas(self):
        rgba = np.zeros((1, 3, 4), dtype=np.uint8)
        rgba[0, 0] = [0, 0, 0, 255]       # opaque canvas background
        rgba[0, 1] = [68, 68, 239, 153]   # red editor overlay in BGRA
        rgba[0, 2] = [255, 255, 255, 0]   # erased transparent pixel

        mask = _canonicalize_uploaded_mask(_png_bytes(rgba))

        self.assertEqual(mask.tolist(), [[0, 255, 0]])

    def test_grayscale_mask_is_normalized_to_strict_binary_values(self):
        grayscale = np.array([[0, 12, 13, 96, 255]], dtype=np.uint8)

        mask = _canonicalize_uploaded_mask(_png_bytes(grayscale))

        self.assertEqual(mask.tolist(), [[0, 0, 255, 255, 255]])


if __name__ == "__main__":
    unittest.main()
