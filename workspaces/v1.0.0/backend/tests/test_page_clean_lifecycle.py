import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from app.routes.pages import get_page, get_page_clean_status, get_page_image
from app.routes.pipeline import (
    _plan_resumable_page_pipeline,
    batch_jobs,
    run_batch_pipeline_task,
)
from app.services.inpainter import mark_clean_assets_stale


class _FakeQuery:
    def __init__(self, value):
        self.value = value

    def filter(self, *_args):
        return self

    def first(self):
        return self.value


class _FakeDb:
    def __init__(self, value):
        self.value = value

    def query(self, *_args):
        return _FakeQuery(self.value)

    def close(self):
        pass


class PageCleanLifecycleTests(unittest.TestCase):
    def test_resume_plan_never_redetects_an_existing_page(self):
        page = SimpleNamespace(text_blocks=[SimpleNamespace(source_text="已识别")])

        self.assertEqual(_plan_resumable_page_pipeline(page, clean_current=True), [])
        self.assertEqual(_plan_resumable_page_pipeline(page, clean_current=False), ["inpaint"])

    def test_resume_plan_fills_only_missing_work(self):
        empty_page = SimpleNamespace(text_blocks=[])
        partial_page = SimpleNamespace(text_blocks=[SimpleNamespace(source_text="")])

        self.assertEqual(
            _plan_resumable_page_pipeline(empty_page, clean_current=False),
            ["detect", "ocr", "inpaint"],
        )
        self.assertEqual(
            _plan_resumable_page_pipeline(partial_page, clean_current=True),
            ["ocr"],
        )

    def test_custom_workflow_filters_resume_stages_without_changing_the_plan(self):
        page = SimpleNamespace(text_blocks=[])

        self.assertEqual(
            _plan_resumable_page_pipeline(page, clean_current=False, requested_steps={"ocr"}),
            ["ocr"],
        )
        self.assertEqual(
            _plan_resumable_page_pipeline(page, clean_current=False, requested_steps={"inpaint"}),
            ["inpaint"],
        )

    def test_batch_resume_skips_a_current_page_without_redetecting(self):
        page = SimpleNamespace(
            id="page-1",
            page_number=1,
            text_blocks=[SimpleNamespace(source_text="already scanned")],
        )
        project = SimpleNamespace(id="project-1", pages=[page])
        db = _FakeDb(project)

        with (
            patch("app.routes.pipeline.get_db", return_value=iter([db])),
            patch("app.routes.pipeline.is_clean_asset_current", return_value=True),
            patch("app.routes.pipeline.balloon_detector.detect") as detect,
        ):
            run_batch_pipeline_task(project.id, steps_str="resume")

        detect.assert_not_called()
        self.assertEqual(batch_jobs[project.id]["status"], "success")

    def test_page_workflow_honors_cancel_requested_before_worker_starts(self):
        from app.routes.pipeline import page_jobs, run_page_pipeline_task

        page = SimpleNamespace(id="page-cancel", text_blocks=[])
        db = _FakeDb(page)
        page_jobs[page.id] = {"status": "queued", "cancel_requested": True}

        with (
            patch("app.routes.pipeline.get_db", return_value=iter([db])),
            patch("app.routes.pipeline.is_clean_asset_current", return_value=False),
            patch("app.routes.pipeline.run_detect") as detect,
        ):
            run_page_pipeline_task(page.id, "project-1")

        detect.assert_not_called()
        self.assertEqual(page_jobs[page.id]["status"], "cancelled")

    def test_batch_pipeline_marks_cancelled_and_stops_when_inpainting_cancelled(self):
        page = SimpleNamespace(
            id="page-1",
            page_number=1,
            text_blocks=[],
            source_image_path="test.png",
        )
        project = SimpleNamespace(id="project-cancel", pages=[page], source_lang="ja", settings={})
        page.project = project
        db = _FakeDb(project)

        def mock_clean(page_id, db, cancel_check=None):
            batch_jobs[project.id]["cancel_requested"] = True
            if cancel_check and cancel_check():
                raise RuntimeError("Inpainting cancelled by user")

        with (
            patch("app.routes.pipeline.get_db", return_value=iter([db])),
            patch("app.routes.pipeline.is_clean_asset_current", return_value=False),
            patch("app.routes.pipeline.clean_page_text", side_effect=mock_clean),
        ):
            run_batch_pipeline_task(project.id, steps_str="inpaint")

        self.assertEqual(batch_jobs[project.id]["status"], "cancelled")

    def test_get_page_is_read_only_while_clean_manifest_is_temporarily_stale(self):
        page = SimpleNamespace(
            id="page-1",
            project_id="project-1",
            project=SimpleNamespace(id="project-1", settings={}),
            page_number=1,
            name="page.png",
            width=10,
            height=10,
            source_image_path="missing.png",
            inpainted_image_path=None,
            rendered_image_path=None,
            status="pending",
            text_blocks=[],
        )
        db = _FakeDb(page)

        with (
            patch("app.routes.pages.ensure_project_access"),
            patch("app.routes.pages._existing_clean_base_path", return_value=None),
            patch("app.routes.pages.invalidate_clean_assets") as invalidate,
        ):
            result = get_page(page.id, db=db, current_user=None)

        self.assertEqual(result["id"], page.id)
        invalidate.assert_not_called()

    def test_clean_status_does_not_delete_existing_stale_base(self):
        with TemporaryDirectory() as directory:
            clean_path = Path(directory) / "inpainted.png"
            clean_path.write_bytes(b"clean")
            page = SimpleNamespace(
                id="page-1",
                project=SimpleNamespace(id="project-1"),
                inpainted_image_path=str(clean_path),
            )

            with (
                patch("app.routes.pages.ensure_project_access"),
                patch("app.routes.pages.is_clean_asset_current", return_value=False),
                patch("app.routes.pages.invalidate_clean_assets") as invalidate,
            ):
                result = get_page_clean_status(page.id, db=_FakeDb(page), current_user=None)

            self.assertFalse(result["current"])
            self.assertTrue(result["has_clean_base"])
            self.assertTrue(clean_path.exists())
            invalidate.assert_not_called()

    def test_stale_clean_base_is_served_instead_of_returning_conflict(self):
        with TemporaryDirectory() as directory:
            clean_path = Path(directory) / "inpainted.png"
            clean_path.write_bytes(b"clean")
            page = SimpleNamespace(
                id="page-1",
                project=SimpleNamespace(id="project-1", settings={}),
                source_image_path=str(Path(directory) / "source.png"),
                inpainted_image_path=str(clean_path),
            )

            with (
                patch("app.routes.pages.ensure_project_access"),
                patch("app.routes.pages.is_clean_asset_current", return_value=False),
            ):
                response = get_page_image(page.id, clean=True, db=_FakeDb(page), current_user=None)

            self.assertEqual(Path(response.path), clean_path)

    def test_marking_stale_removes_only_manifest(self):
        with TemporaryDirectory() as directory:
            clean_path = Path(directory) / "inpainted.png"
            manifest_path = Path(directory) / "manifest.json"
            clean_path.write_bytes(b"clean")
            manifest_path.write_text("{}", encoding="utf-8")

            with patch("app.services.inpainter.clean_manifest_path", return_value=manifest_path):
                removed = mark_clean_assets_stale(SimpleNamespace())

            self.assertEqual(removed, 1)
            self.assertFalse(manifest_path.exists())
            self.assertTrue(clean_path.exists())


if __name__ == "__main__":
    unittest.main()
