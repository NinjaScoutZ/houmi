import logging
import shutil
import tempfile
from urllib.parse import quote
import os
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Response
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.txt_exchange import export_to_txt, validate_and_import_txt, validate_txt_preview
from app.services.psd_export import export_page_to_psd
from app.services.psd_import import import_psd_to_page
from app.models.all_models import Project, Page, TextBlock
from app.services.project_serializer import save_project_json
from app.services.project_paths import rendered_asset_path
from app.security.dependencies import get_current_user_or_local, require_resource_access

logger = logging.getLogger("houmi-exchange")

router = APIRouter(
    tags=["Exchange"],
    dependencies=[Depends(get_current_user_or_local), Depends(require_resource_access)],
)

class ClearTranslationsRequest(BaseModel):
    scope: str
    block_ids: list[str] = Field(default_factory=list)
    page_id: str | None = None
    project_id: str | None = None
    clear_source: bool = False

@router.post("/translations/clear")
def clear_translations(req: ClearTranslationsRequest, db: Session = Depends(get_db)):
    if req.scope == "layers" and req.block_ids:
        blocks = db.query(TextBlock).filter(TextBlock.id.in_(req.block_ids)).all()
    elif req.scope == "page" and req.page_id:
        blocks = db.query(TextBlock).filter(TextBlock.page_id == req.page_id).all()
    elif req.scope == "project" and req.project_id:
        blocks = db.query(TextBlock).join(Page).filter(Page.project_id == req.project_id).all()
    else:
        raise HTTPException(status_code=400, detail="Invalid translation clear scope")

    project_ids: set[str] = set()
    page_ids: set[str] = set()
    for block in blocks:
        if block.page:
            block.page.rendered_image_path = None
            page_ids.add(block.page.id)
            project_ids.add(block.page.project_id)
            rendered = rendered_asset_path(block.page)
            if rendered.exists():
                rendered.unlink()
        
        if req.clear_source:
            db.delete(block)
        else:
            block.translation = ""
            metadata = dict(block.extra_metadata or {})
            metadata.pop("typesetting_spec", None)
            metadata.pop("suggested_spec_id", None)
            metadata.pop("suggested_spec_revision", None)
            metadata.pop("suggested_explicit_lines", None)
            metadata.pop("suggested_template_id", None)
            metadata.pop("text_template_id", None)
            metadata.pop("manual_font_size", None)
            for ai_layout_key in (
                "line_break_source",
                "ai_preferred_lines",
                "ai_layout_hint",
                "ai_layout_text",
            ):
                metadata.pop(ai_layout_key, None)
            for semantic_key in (
                "semantic_role",
                "semantic_role_label",
                "semantic_role_source",
                "semantic_role_tag",
                "semantic_role_confidence",
                "semantic_role_raw_translation",
                "semantic_role_template_id",
            ):
                metadata.pop(semantic_key, None)
            block.extra_metadata = metadata
    db.commit()
    for project_id in project_ids:
        save_project_json(project_id, db)
    return {"status": "success", "cleared_blocks": len(blocks), "page_ids": sorted(page_ids)}

@router.post("/export/txt", response_class=Response)
def export_txt(project_id: str, mode: str = "ocr", db: Session = Depends(get_db)):
    try:
        txt_content = export_to_txt(project_id, db, mode=mode)
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ValueError("Project not found")
        # TXT is an exchange file. Do not silently pin it to the image/project
        # folder: desktop Save As lets translators choose their own workspace.
        return Response(
            content=txt_content,
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename={mode}_{project_id}.txt",
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export TXT: {e}"
        )

@router.post("/import/txt")
async def import_txt(
    project_id: str,
    file: UploadFile = File(...),
    exclude_lines: str = "",
    db: Session = Depends(get_db)
):
    try:
        content = await file.read()
        txt_content = content.decode("utf-8-sig")  # Supports UTF-8 with BOM
        
        exclude_set = set()
        if exclude_lines:
            try:
                exclude_set = {int(x) for x in exclude_lines.split(",") if x.strip()}
            except ValueError:
                pass
                
        result = validate_and_import_txt(project_id, txt_content, db, exclude_lines=exclude_set)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to import TXT: {e}"
        )

@router.post("/import/txt/preview")
async def preview_import_txt(project_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        content = await file.read()
        txt_content = content.decode("utf-8-sig")
        result = validate_txt_preview(project_id, txt_content, db)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to preview TXT import: {e}"
        )

@router.post("/export/psd")
def export_psd(
    page_id: str,
    force: bool = True,
    text_mode: str = "paragraph",
    db: Session = Depends(get_db),
):
    try:
        psd_path = export_page_to_psd(page_id, db, force=force, text_mode=text_mode)
        return FileResponse(
            path=str(psd_path),
            media_type="image/vnd.adobe.photoshop",
            filename=psd_path.name,
            headers={"X-Houmi-Export-Path": quote(str(psd_path), safe="")},
        )
    except ValueError as e:
        if str(e).startswith("EXPORT_BLOCKED"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
        logger.warning(f"Export PSD blocked or failed with ValueError: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export PSD: {e}"
        )
    except Exception as e:
        logger.exception(f"Failed to export PSD: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export PSD: {e}"
        )

@router.post("/import/psd")
async def import_psd(page_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    # 1. Save uploaded PSD to temporary file
    temp_fd, temp_path_str = tempfile.mkstemp(suffix=".psd")
    try:
        with os.fdopen(temp_fd, 'wb') as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # 2. Run reverse import logic
        result = import_psd_to_page(page_id, temp_path_str, db)
        return result
    except ValueError as e:
        db.rollback()
        if str(e).startswith("IMPORT_FAILED"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to import PSD: {e}"
        )
    finally:
        if os.path.exists(temp_path_str):
            try:
                os.remove(temp_path_str)
            except Exception:
                pass
