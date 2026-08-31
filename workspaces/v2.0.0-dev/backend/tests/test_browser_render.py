from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.all_models import Page, Project
from app.services.browser_render import (
    BrowserRenderError,
    StaleBrowserRenderError,
    browser_render_is_fresh,
    browser_overlay_path,
    _render_relevant_metadata,
    page_render_revision,
    save_browser_render,
)


def _png_bytes(image: Image.Image) -> bytes:
    stream = BytesIO()
    image.save(stream, "PNG")
    return stream.getvalue()


@pytest.fixture()
def render_page(tmp_path: Path):
    source_path = tmp_path / "source.png"
    clean_path = tmp_path / "clean.png"
    Image.new("RGBA", (8, 6), (10, 20, 30, 255)).save(source_path)
    Image.new("RGBA", (8, 6), (40, 50, 60, 255)).save(clean_path)

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    project = Project(
        id="browser-project",
        name="Browser Render",
        settings={"local_folder": str(tmp_path)},
    )
    page = Page(
        id="browser-page",
        project=project,
        page_number=7,
        name="unrelated-name.jpg",
        width=8,
        height=6,
        source_image_path=str(source_path),
        inpainted_image_path=str(clean_path),
    )
    session.add_all([project, page])
    session.commit()
    try:
        yield session, page
    finally:
        session.close()


def test_browser_render_composites_exact_pixels_and_persists(render_page):
    session, page = render_page
    overlay = Image.new("RGBA", (8, 6), (0, 0, 0, 0))
    overlay.putpixel((3, 2), (255, 0, 0, 255))
    revision = page_render_revision(page, "clean")

    output = save_browser_render(page.id, _png_bytes(overlay), revision, "clean", session)

    assert output.name == "07.png"
    assert output.parent.name == "rendered"
    with Image.open(output) as result:
        assert result.getpixel((0, 0)) == (40, 50, 60, 255)
        assert result.getpixel((3, 2)) == (255, 0, 0, 255)
    assert page.rendered_image_path == str(output)
    with Image.open(browser_overlay_path(page)) as saved_overlay:
        assert saved_overlay.mode == "RGBA"
        assert saved_overlay.getpixel((0, 0)) == (0, 0, 0, 0)
        assert saved_overlay.getpixel((3, 2)) == (255, 0, 0, 255)
    assert browser_render_is_fresh(page)


def test_browser_render_rejects_wrong_dimensions_without_replacing_old_file(render_page):
    session, page = render_page
    output = Path(page.source_image_path).parent / "rendered" / "07.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"old-render")
    bad_overlay = Image.new("RGBA", (7, 6), (0, 0, 0, 0))

    with pytest.raises(BrowserRenderError, match="exactly 8x6"):
        save_browser_render(
            page.id,
            _png_bytes(bad_overlay),
            page_render_revision(page, "clean"),
            "clean",
            session,
        )

    assert output.read_bytes() == b"old-render"


def test_browser_render_rejects_stale_revision(render_page):
    session, page = render_page
    overlay = Image.new("RGBA", (8, 6), (0, 0, 0, 0))

    with pytest.raises(StaleBrowserRenderError):
        save_browser_render(page.id, _png_bytes(overlay), "stale", "clean", session)


def test_browser_render_rejects_non_png(render_page):
    session, page = render_page
    with pytest.raises(BrowserRenderError, match="PNG"):
        save_browser_render(
            page.id,
            b"not-an-image",
            page_render_revision(page, "clean"),
            "clean",
            session,
        )


def test_psd_export_bookkeeping_does_not_invalidate_browser_render(render_page):
    first = _render_relevant_metadata({
        "layout_region": {"x": 1},
        "psd_export_snapshot": {"hash": "one"},
    })
    second = _render_relevant_metadata({
        "layout_region": {"x": 1},
        "psd_export_snapshot": {"hash": "two"},
        "psd_export_history": {"export": {"hash": "three"}},
    })
    assert first == second == {"layout_region": {"x": 1}}
