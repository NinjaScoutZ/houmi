"""
Comic Publishing & Digital Archive Export API Routes for Houmi Studio.
Provides endpoints for downloading CBZ archives, PDF chapters, and executing Webtoon platform slicers.
"""
from typing import Optional
from pathlib import Path
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.all_models import Project, User
from app.security.dependencies import ensure_project_access, get_current_user_or_local, require_resource_access
from app.services.comic_export import export_project_cbz, export_project_pdf, export_webtoon_slices, WEBTOON_PLATFORM_PRESETS

router = APIRouter(
    tags=["Comic Publishing & Export"],
    dependencies=[Depends(get_current_user_or_local), Depends(require_resource_access)],
)


class WebtoonSliceRequest(BaseModel):
    platform: str = "webtoon"  # "webtoon" | "tapas" | "kakao"


@router.get("/projects/{project_id}/export/cbz")
def api_download_cbz(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    """
    Generate and download the project as a standardized .cbz comic archive.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    ensure_project_access(project, current_user)

    try:
        cbz_path = export_project_cbz(project_id, db)
        safe_filename = f"{project.name or 'comic'}.cbz"
        return FileResponse(
            path=str(cbz_path),
            filename=safe_filename,
            media_type="application/vnd.comicbook+zip",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(safe_filename)}"}
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to generate CBZ: {e}")


@router.get("/projects/{project_id}/export/pdf")
def api_download_pdf(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    """
    Generate and download the project as a high-res multi-page PDF document.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    ensure_project_access(project, current_user)

    try:
        pdf_path = export_project_pdf(project_id, db)
        safe_filename = f"{project.name or 'comic'}.pdf"
        return FileResponse(
            path=str(pdf_path),
            filename=safe_filename,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(safe_filename)}"}
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to generate PDF: {e}")


@router.post("/projects/{project_id}/export/webtoon-slices")
def api_export_webtoon_slices(
    project_id: str,
    request: WebtoonSliceRequest,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    """
    Slice webtoon pages according to publishing specs (Webtoon 800x1280, Tapas 960x1440, Kakao 720x1200).
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    ensure_project_access(project, current_user)

    try:
        result = export_webtoon_slices(project_id, request.platform, db)
        return result
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Slicing failed: {e}")


@router.get("/export/webtoon-presets")
def api_get_webtoon_presets():
    """
    List available webtoon publishing platform slice presets.
    """
    return WEBTOON_PLATFORM_PRESETS
