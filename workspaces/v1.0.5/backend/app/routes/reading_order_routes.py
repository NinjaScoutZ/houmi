"""
Reading Order API Routes for Houmi Studio.
Provides endpoints for calculating reading flow lines and persisting dialogue sequence order.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.all_models import Page, User
from app.security.dependencies import ensure_project_access, get_current_user_or_local, require_resource_access
from app.services.reading_order_service import get_page_reading_order, apply_page_reading_order

router = APIRouter(
    tags=["Reading Order"],
    dependencies=[Depends(get_current_user_or_local), Depends(require_resource_access)],
)


class ApplyReadingOrderRequest(BaseModel):
    block_ids: List[str]


@router.get("/pages/{page_id}/reading-order")
def api_get_page_reading_order(
    page_id: str,
    mode: Optional[str] = "manga_rtl",
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    """
    Get 2D speech bubble reading flow lines and computed sequence.
    Modes:
    - manga_rtl: Japanese Manga (Top-to-Bottom, Right-to-Left)
    - webtoon_ltr: Korean / Vertical Webtoon (Continuous vertical scroll)
    - western_ltr: Western Comics (Top-to-Bottom, Left-to-Right)
    """
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")
    ensure_project_access(page.project, current_user)

    result = get_page_reading_order(page_id, mode=mode, db=db)
    return result


@router.post("/pages/{page_id}/reading-order/apply")
def api_apply_page_reading_order(
    page_id: str,
    request: ApplyReadingOrderRequest,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    """
    Persist new block_index values on a page according to chosen reading sequence.
    """
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")
    ensure_project_access(page.project, current_user)

    result = apply_page_reading_order(page_id, request.block_ids, db)
    return result
