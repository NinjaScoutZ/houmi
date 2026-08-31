"""
SFX API Routes for Houmi Studio.
Provides endpoints for Onomatopoeia lookup, preset catalogs, and block SFX workflow configuration.
"""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.all_models import TextBlock, User
from app.security.dependencies import ensure_project_access, get_current_user_or_local, require_resource_access
from app.services.sfx_dictionary import lookup_sfx, suggest_sfx_translation, get_sfx_catalog

router = APIRouter(
    tags=["Sound Effects (SFX)"],
    dependencies=[Depends(get_current_user_or_local), Depends(require_resource_access)],
)


class SFXWorkflowRequest(BaseModel):
    workflow_mode: str  # "subtitle_overlay" | "inpaint_redraw" | "original_only"
    translation: Optional[str] = None
    stroke_color: Optional[str] = None
    stroke_width: Optional[float] = None
    font_family: Optional[str] = None


@router.get("/sfx/lookup")
def api_lookup_sfx(
    q: str,
    lang: Optional[str] = "auto",
):
    """
    Search SFX database for matching sound effects in Japanese, Korean, or Chinese.
    """
    matches = lookup_sfx(q, lang=lang)
    suggested = suggest_sfx_translation(q)
    return {
        "query": q,
        "lang": lang,
        "suggested_translation": suggested,
        "matches": matches,
    }


@router.get("/sfx/catalog")
def api_get_sfx_catalog(
    category: Optional[str] = None,
    lang: Optional[str] = None,
):
    """
    Get list of SFX presets filtered by category (impact, ambient, motion, emotion, magic) or language.
    """
    items = get_sfx_catalog(category=category, lang=lang)
    return {
        "count": len(items),
        "items": items,
    }


@router.post("/blocks/{block_id}/sfx-workflow")
def api_configure_block_sfx_workflow(
    block_id: str,
    request: SFXWorkflowRequest,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    """
    Configure a text block as an SFX block with specific workflow mode:
    - subtitle_overlay: Keep original comic SFX drawing, place small translation overlay next to it.
    - inpaint_redraw: Inpaint raw SFX and render large stylized comic font over clean image.
    - original_only: Retain raw drawing without text overlay.
    """
    block = db.query(TextBlock).filter(TextBlock.id == block_id).first()
    if not block:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found")
    ensure_project_access(block.page.project, current_user)

    block.balloon_type = "sfx"
    
    meta = dict(block.extra_metadata or {})
    meta["sfx_workflow_mode"] = request.workflow_mode
    if request.stroke_color:
        meta["stroke_color"] = request.stroke_color
    if request.stroke_width is not None:
        meta["stroke_width"] = request.stroke_width
    block.extra_metadata = meta

    if request.translation:
        block.translation = request.translation
    elif not block.translation and block.source_text:
        auto_suggest = suggest_sfx_translation(block.source_text)
        if auto_suggest:
            block.translation = auto_suggest

    if request.font_family:
        block.font_family = request.font_family

    db.commit()
    db.refresh(block)

    return {
        "status": "success",
        "block_id": str(block.id),
        "balloon_type": block.balloon_type,
        "sfx_workflow_mode": request.workflow_mode,
        "translation": block.translation,
    }
