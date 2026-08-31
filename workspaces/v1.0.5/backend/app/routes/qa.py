"""
Quality Assurance (QA) API Routes for Houmi Studio.
Provides endpoints for automated page and project sanity audits.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.all_models import Page, Project, User
from app.security.dependencies import ensure_project_access, get_current_user_or_local, require_resource_access
from app.services.qa_service import audit_page_qa, audit_project_qa

router = APIRouter(
    tags=["Quality Assurance"],
    dependencies=[Depends(get_current_user_or_local), Depends(require_resource_access)],
)
logger = logging.getLogger("houmi-qa-router")


@router.get("/pages/{page_id}/qa")
def get_page_qa_audit(
    page_id: str,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    """
    Run automated QA audit on a single page.
    Checks for text overflow, untranslated text, OCR confidence, and missing inpainting.
    """
    page = db.query(Page).filter(Page.id == page_id).first()
    if not page:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")
    ensure_project_access(page.project, current_user)

    result = audit_page_qa(page_id, db)
    return result


@router.get("/projects/{project_id}/qa")
def get_project_qa_audit(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_or_local),
):
    """
    Run automated QA audit across all pages in a project.
    Returns aggregated issue summaries and page-by-page breakdowns.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    ensure_project_access(project, current_user)

    result = audit_project_qa(project_id, db)
    return result
