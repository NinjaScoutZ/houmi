"""
Translation Memory (TM) API Routes for Houmi Studio.
Provides endpoints for searching, adding, importing, and exporting translation pairs.
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.all_models import User
from app.security.dependencies import get_current_user_or_local, require_resource_access
from app.services.tm_service import search_tm, record_tm_entry, import_tm_entries, export_tm_entries

router = APIRouter(
    tags=["Translation Memory"],
    dependencies=[Depends(get_current_user_or_local), Depends(require_resource_access)],
)


class TMEntryRequest(BaseModel):
    source_text: str
    translation: str
    source_language: str = "ja"
    target_language: str = "th"
    project_id: Optional[str] = None


class TMImportRequest(BaseModel):
    entries: List[Dict[str, str]]
    default_source_lang: str = "ja"
    default_target_lang: str = "th"


@router.get("/tm/search")
def api_search_tm(
    q: str,
    src: Optional[str] = None,
    tgt: Optional[str] = None,
    limit: int = 10,
    db: Session = Depends(get_db),
):
    """
    Search Translation Memory for matching translations.
    """
    results = search_tm(q, db, source_lang=src, target_lang=tgt, limit=limit)
    return {
        "query": q,
        "count": len(results),
        "matches": results,
    }


@router.post("/tm/entries")
def api_add_tm_entry(
    request: TMEntryRequest,
    db: Session = Depends(get_db),
):
    """
    Add or update a translation pair in Translation Memory.
    """
    try:
        entry = record_tm_entry(
            request.source_text,
            request.translation,
            request.source_language,
            request.target_language,
            db,
            project_id=request.project_id,
        )
        return {
            "status": "success",
            "id": str(entry.id),
            "source_text": entry.source_text,
            "translation": entry.translation,
            "frequency": entry.frequency,
        }
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))


@router.post("/tm/import")
def api_import_tm(
    request: TMImportRequest,
    db: Session = Depends(get_db),
):
    """
    Bulk import translation pairs into Translation Memory.
    """
    res = import_tm_entries(
        request.entries,
        db,
        default_src_lang=request.default_source_lang,
        default_tgt_lang=request.default_target_lang,
    )
    return res


@router.get("/tm/export")
def api_export_tm(
    src: Optional[str] = None,
    tgt: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Export all Translation Memory pairs.
    """
    records = export_tm_entries(db, source_lang=src, target_lang=tgt)
    return {
        "count": len(records),
        "entries": records,
    }
