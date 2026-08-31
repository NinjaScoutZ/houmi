"""Flattened PNG/JPEG export for completed Houmi projects."""

from pathlib import Path

from PIL import Image
from sqlalchemy.orm import Session

from app.models.all_models import Project
from app.services.browser_render import browser_render_is_fresh
from app.services.project_paths import rendered_asset_path
from app.services.renderer import render_page_text


def export_project_images(project_id: str, db: Session, image_format: str) -> list[Path]:
    normalized = image_format.lower()
    if normalized == "jpg":
        normalized = "jpeg"
    if normalized not in {"png", "jpeg"}:
        raise ValueError("Image format must be png or jpeg")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("Project not found")
    pages = sorted(project.pages, key=lambda page: page.page_number)
    if not pages:
        raise ValueError("No pages in project to export")

    output_paths: list[Path] = []
    for page in pages:
        # A fresh Fabric render is already the exact editor preview.  Never
        # overwrite it by laying the text out a second time with Pillow.
        if browser_render_is_fresh(page):
            rendered_path = rendered_asset_path(page)
        else:
            rendered_path = Path(render_page_text(page.id, db))
        if normalized == "png":
            # The canonical PNG already lives under rendered/. Returning it
            # avoids creating a redundant NN_houmi.png beside source pages.
            output_path = rendered_path
        else:
            output_path = rendered_path.with_suffix(".jpg")
            with Image.open(rendered_path) as image:
                image.convert("RGB").save(output_path, "JPEG", quality=95, optimize=True)
        output_paths.append(output_path)
    return output_paths
