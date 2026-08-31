from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PIL import Image

from app.services.image_export import export_project_images


def _fake_db(project):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = project
    return db


def test_finished_image_export_writes_png_and_jpeg(tmp_path: Path):
    rendered = tmp_path / "rendered.png"
    Image.new("RGB", (32, 24), (20, 40, 60)).save(rendered)
    page = SimpleNamespace(id="page-1", page_number=1, name="01.jpg")
    project = SimpleNamespace(id="project-1", pages=[page])
    page.project = project

    with (
        patch("app.services.image_export.render_page_text", return_value=rendered),
        patch("app.services.image_export.browser_render_is_fresh", return_value=False),
    ):
        png_paths = export_project_images(project.id, _fake_db(project), "png")
        jpeg_paths = export_project_images(project.id, _fake_db(project), "jpeg")

    assert png_paths == [rendered]
    assert jpeg_paths == [rendered.with_suffix(".jpg")]
    assert Image.open(png_paths[0]).format == "PNG"
    assert Image.open(jpeg_paths[0]).format == "JPEG"


def test_finished_image_export_reuses_fresh_browser_render(tmp_path: Path):
    rendered = tmp_path / "rendered.png"
    Image.new("RGBA", (12, 10), (17, 34, 51, 255)).save(rendered)
    page = SimpleNamespace(id="page-7", page_number=7, name="arbitrary-cover-name.jpg")
    project = SimpleNamespace(id="project-1", pages=[page])
    page.project = project

    with (
        patch("app.services.image_export.browser_render_is_fresh", return_value=True),
        patch("app.services.image_export.rendered_asset_path", return_value=rendered),
        patch("app.services.image_export.render_page_text") as pillow_render,
    ):
        paths = export_project_images(project.id, _fake_db(project), "png")

    assert paths == [rendered]
    assert Image.open(paths[0]).getpixel((0, 0)) == (17, 34, 51, 255)
    pillow_render.assert_not_called()
