"""
ZIP Export Service for Houmi.
Bundles all PSD exports of a project into a single ZIP archive.
"""
import zipfile
import logging
from pathlib import Path
from sqlalchemy.orm import Session
from app.models.all_models import Project
from app.services.project_paths import project_export_path
from app.services.psd_export import export_page_to_psd

logger = logging.getLogger("houmi-zip-export")


def export_project_psd_zip(
    project_id: str,
    db: Session,
    text_mode: str = "paragraph",
) -> Path:
    """
    Export all pages of a project as individual PSD files
    bundled into a single ZIP archive.

    Args:
        project_id: Project UUID
        db: Database session

    Returns:
        Path to the generated ZIP file
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("Project not found")

    pages = sorted(project.pages, key=lambda p: p.page_number)
    if not pages:
        raise ValueError("No pages in project to export")

    # Sanitize filename
    safe_name = "".join(c for c in project.name if c.isalnum() or c in " _-").strip()
    if not safe_name:
        safe_name = project_id[:8]

    zip_path = project_export_path(project, f"{safe_name}_psd.zip")

    logger.info(f"Creating PSD ZIP for project '{project.name}' ({len(pages)} pages)")

    exported_count = 0
    errors = []

    with zipfile.ZipFile(str(zip_path), 'w', zipfile.ZIP_DEFLATED) as zf:
        for page in pages:
            try:
                psd_path = export_page_to_psd(page.id, db, force=True, text_mode=text_mode)
                # Add to ZIP with a clean filename
                arcname = f"page_{page.page_number:03d}.psd"
                zf.write(str(psd_path), arcname)
                exported_count += 1
                logger.info(f"Added page {page.page_number} to ZIP")
            except Exception as e:
                error_msg = f"Page {page.page_number}: {str(e)}"
                errors.append(error_msg)
                logger.error(f"Failed to export page {page.page_number} to PSD: {e}")

    if exported_count == 0:
        raise ValueError(f"No pages could be exported. Errors: {'; '.join(errors)}")

    logger.info(f"PSD ZIP created: {zip_path} ({exported_count} pages, {len(errors)} errors)")
    return zip_path


def export_project_jsx_zip(
    project_id: str,
    db: Session,
    text_mode: str = "point",
) -> Path:
    """
    Export all pages of a project as individual JSX ExtendScript files
    bundled into a single ZIP archive.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ValueError("Project not found")

    pages = sorted(project.pages, key=lambda p: p.page_number)
    if not pages:
        raise ValueError("No pages in project to export")

    safe_name = "".join(c for c in project.name if c.isalnum() or c in " _-").strip()
    if not safe_name:
        safe_name = project_id[:8]

    zip_path = project_export_path(project, f"{safe_name}_jsx_scripts.zip")

    logger.info(f"Creating JSX ZIP for project '{project.name}' ({len(pages)} pages)")

    from app.services.jsx_export import export_page_jsx

    exported_count = 0
    errors = []

    with zipfile.ZipFile(str(zip_path), 'w', zipfile.ZIP_DEFLATED) as zf:
        from app.services.project_paths import inpainted_asset_path
        for page in pages:
            try:
                jsx_path = export_page_jsx(page.id, db, text_mode=text_mode)
                arcname = f"page_{page.page_number:03d}.jsx"
                zf.write(str(jsx_path), arcname)
                
                # Bundle clean image if present
                clean_img = inpainted_asset_path(page)
                if not clean_img.exists() and page.inpainted_image_path:
                    clean_img = Path(page.inpainted_image_path)
                if clean_img.exists():
                    img_arcname = f"page_{page.page_number:03d}_clean.png"
                    zf.write(str(clean_img), img_arcname)
                    
                exported_count += 1
                logger.info(f"Added page {page.page_number} JSX & clean image to ZIP")
            except Exception as e:
                error_msg = f"Page {page.page_number}: {str(e)}"
                errors.append(error_msg)
                logger.error(f"Failed to export page {page.page_number} JSX: {e}")

    if exported_count == 0:
        raise ValueError(f"No pages could be exported to JSX. Errors: {'; '.join(errors)}")

    logger.info(f"JSX ZIP created: {zip_path} ({exported_count} pages, {len(errors)} errors)")
    return zip_path
