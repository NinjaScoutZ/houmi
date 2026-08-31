"""
Comic Publishing & Digital Archive Export Service for Houmi Studio.
Generates standard .CBZ comic archives (with ComicInfo.xml), high-res PDFs, and Webtoon platform slices.
"""
from typing import List, Dict, Any, Optional
from pathlib import Path
import zipfile
import io
import logging
from PIL import Image
from sqlalchemy.orm import Session

from app.models.all_models import Project, Page
from app.services.project_paths import (
    project_workspace_dir,
    rendered_asset_path,
    inpainted_asset_path,
)
from app.config import DATA_DIR

logger = logging.getLogger("houmi-comic-export")

WEBTOON_PLATFORM_PRESETS = {
    "webtoon": {"max_width": 800, "max_height": 1280, "name": "Naver Webtoon / LINE Webtoon"},
    "tapas": {"max_width": 960, "max_height": 1440, "name": "Tapas Media"},
    "kakao": {"max_width": 720, "max_height": 1200, "name": "KakaoPage"},
}


def _get_best_page_image_path(page: Page) -> Optional[Path]:
    """
    Get the most rendered/finalized image available for the page.
    Priority: Rendered > Inpainted/Clean > Source.
    """
    r_path = rendered_asset_path(page)
    if r_path.exists():
        return r_path

    c_path = inpainted_asset_path(page)
    if c_path.exists():
        return c_path

    if page.source_image_path:
        s_path = Path(page.source_image_path)
        if s_path.exists():
            return s_path

    return None


def generate_comic_info_xml(project: Project, page_count: int) -> str:
    """
    Generate standard ComicInfo.xml metadata schema for comic reader compatibility.
    """
    title = project.name or "Untitled Comic"
    src_lang = project.source_lang or "ja"
    tgt_lang = project.target_lang or "th"

    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<ComicInfo xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Title>{title}</Title>
  <Series>{title}</Series>
  <Summary>Translated from {src_lang} to {tgt_lang} using Houmi Studio.</Summary>
  <PageCount>{page_count}</PageCount>
  <LanguageISO>{tgt_lang}</LanguageISO>
  <Manga>YesAndRightToLeft</Manga>
  <Writer>Houmi Studio</Writer>
  <Translator>Houmi Studio</Translator>
</ComicInfo>
"""
    return xml.strip()


def export_project_cbz(project_id: str, db: Session, out_path: Optional[Path] = None) -> Path:
    """
    Export all pages of a project into a standardized .cbz archive with ComicInfo.xml.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError(f"Project '{project_id}' not found")

    pages = db.query(Page).filter(Page.project_id == project_id).order_by(Page.page_number).all()
    if not pages:
        raise ValueError(f"No pages found for project '{project_id}'")

    if not out_path:
        project_dir = project_workspace_dir(project)
        export_dir = project_dir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c for c in project.name if c.isalnum() or c in (" ", "-", "_")).strip()
        out_path = export_dir / f"{safe_name or 'comic'}.cbz"

    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        valid_pages = 0
        for idx, page in enumerate(pages, 1):
            img_path = _get_best_page_image_path(page)
            if img_path and img_path.exists():
                ext = img_path.suffix.lower() or ".png"
                archive_name = f"page_{idx:03d}{ext}"
                zip_file.write(img_path, arcname=archive_name)
                valid_pages += 1

        # Add ComicInfo.xml
        comic_info = generate_comic_info_xml(project, valid_pages)
        zip_file.writestr("ComicInfo.xml", comic_info)

    logger.info("Exported CBZ archive to %s with %d pages", out_path, valid_pages)
    return out_path


def export_project_pdf(project_id: str, db: Session, out_path: Optional[Path] = None) -> Path:
    """
    Export all rendered pages of a project into a single high-res PDF file.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError(f"Project '{project_id}' not found")

    pages = db.query(Page).filter(Page.project_id == project_id).order_by(Page.page_number).all()
    if not pages:
        raise ValueError(f"No pages found for project '{project_id}'")

    if not out_path:
        project_dir = project_workspace_dir(project)
        export_dir = project_dir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c for c in project.name if c.isalnum() or c in (" ", "-", "_")).strip()
        out_path = export_dir / f"{safe_name or 'comic'}.pdf"

    pil_images = []
    for page in pages:
        img_path = _get_best_page_image_path(page)
        if img_path and img_path.exists():
            try:
                img = Image.open(img_path)
                if img.mode == "RGBA":
                    bg = Image.new("RGB", img.size, (255, 255, 255))
                    bg.paste(img, mask=img.split()[3])
                    img = bg
                elif img.mode != "RGB":
                    img = img.convert("RGB")
                pil_images.append(img)
            except Exception as e:
                logger.warning("Could not read page %s for PDF export: %e", page.id, e)

    if not pil_images:
        raise ValueError("No valid image files could be read for PDF compilation")

    # Save multi-page PDF
    pil_images[0].save(
        out_path,
        "PDF",
        resolution=150.0,
        save_all=True,
        append_images=pil_images[1:],
    )

    logger.info("Exported PDF document to %s with %d pages", out_path, len(pil_images))
    return out_path


def export_webtoon_slices(
    project_id: str,
    platform: str,
    db: Session,
) -> Dict[str, Any]:
    """
    Slice long webtoon pages according to specific platform dimensions (Webtoon/Tapas/Kakao).
    """
    preset = WEBTOON_PLATFORM_PRESETS.get(platform.lower())
    if not preset:
        raise ValueError(f"Unknown platform preset '{platform}'. Available: {list(WEBTOON_PLATFORM_PRESETS.keys())}")

    max_w = preset["max_width"]
    max_h = preset["max_height"]

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError(f"Project '{project_id}' not found")

    pages = db.query(Page).filter(Page.project_id == project_id).order_by(Page.page_number).all()
    project_dir = project_workspace_dir(project)
    out_dir = project_dir / "exports" / f"slices_{platform.lower()}"
    out_dir.mkdir(parents=True, exist_ok=True)

    generated_slices = []
    global_slice_idx = 1

    for page in pages:
        img_path = _get_best_page_image_path(page)
        if not img_path or not img_path.exists():
            continue

        try:
            with Image.open(img_path) as img:
                orig_w, orig_h = img.size
                
                # Resize width to match max_width if necessary
                if orig_w != max_w:
                    scale = max_w / float(orig_w)
                    new_h = int(orig_h * scale)
                    img_scaled = img.resize((max_w, new_h), Image.Resampling.LANCZOS)
                else:
                    img_scaled = img
                    new_h = orig_h

                # Slice along height
                curr_y = 0
                while curr_y < new_h:
                    slice_h = min(max_h, new_h - curr_y)
                    box = (0, curr_y, max_w, curr_y + slice_h)
                    slice_crop = img_scaled.crop(box)
                    
                    slice_filename = f"slice_{global_slice_idx:04d}.png"
                    slice_path = out_dir / slice_filename
                    slice_crop.save(slice_path, "PNG", optimize=True)
                    
                    generated_slices.append({
                        "slice_index": global_slice_idx,
                        "filename": slice_filename,
                        "path": str(slice_path),
                        "width": max_w,
                        "height": slice_h,
                        "source_page": page.page_number,
                    })
                    
                    curr_y += slice_h
                    global_slice_idx += 1

        except Exception as e:
            logger.exception("Failed to slice page %s: %s", page.id, e)

    return {
        "status": "success",
        "platform": platform,
        "platform_name": preset["name"],
        "total_slices": len(generated_slices),
        "output_directory": str(out_dir),
        "slices": generated_slices,
    }
