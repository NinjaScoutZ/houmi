"""
Translation Memory (TM) Service for Houmi Studio.
Handles searching, indexing, importing, and exporting translation pairs with usage frequency tracking.
"""
from typing import List, Dict, Any, Optional
import datetime
from sqlalchemy.orm import Session
from app.models.all_models import TranslationMemory, Project
import logging

logger = logging.getLogger("houmi-tm-service")


def search_tm(
    query: str,
    db: Session,
    source_lang: Optional[str] = None,
    target_lang: Optional[str] = None,
    project_id: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """
    Search translation memory for exact or substring matches.
    """
    if not query:
        return []

    q_str = query.strip()
    q = db.query(TranslationMemory)

    if source_lang and source_lang != "auto":
        q = q.filter(TranslationMemory.source_language == source_lang)
    if target_lang and target_lang != "auto":
        q = q.filter(TranslationMemory.target_language == target_lang)

    # Prioritize exact match or substring match
    q = q.filter(TranslationMemory.source_text.ilike(f"%{q_str}%"))
    q = q.order_by(TranslationMemory.frequency.desc(), TranslationMemory.last_used_at.desc())

    results = q.limit(limit).all()

    return [
        {
            "id": str(r.id),
            "source_text": r.source_text,
            "translation": r.translation,
            "source_language": r.source_language,
            "target_language": r.target_language,
            "frequency": r.frequency,
            "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
            "match_type": "exact" if r.source_text == q_str else "partial",
        }
        for r in results
    ]


def record_tm_entry(
    source_text: str,
    translation: str,
    source_lang: str,
    target_lang: str,
    db: Session,
    project_id: Optional[str] = None,
) -> TranslationMemory:
    """
    Upsert a translation pair in Translation Memory:
    Increments frequency and updates last_used_at if existing, otherwise creates a new record.
    """
    src = (source_text or "").strip()
    tgt = (translation or "").strip()
    if not src or not tgt:
        raise ValueError("Both source_text and translation must be non-empty")

    existing = (
        db.query(TranslationMemory)
        .filter(
            TranslationMemory.source_text == src,
            TranslationMemory.source_language == source_lang,
            TranslationMemory.target_language == target_lang,
        )
        .first()
    )

    now = datetime.datetime.utcnow()
    if existing:
        existing.translation = tgt
        existing.frequency = (existing.frequency or 1) + 1
        existing.last_used_at = now
        if project_id:
            existing.project_id = project_id
        entry = existing
    else:
        entry = TranslationMemory(
            source_text=src,
            translation=tgt,
            source_language=source_lang,
            target_language=target_lang,
            project_id=project_id,
            frequency=1,
            last_used_at=now,
        )
        db.add(entry)

    db.commit()
    db.refresh(entry)
    return entry


def import_tm_entries(
    entries: List[Dict[str, str]],
    db: Session,
    default_src_lang: str = "ja",
    default_tgt_lang: str = "th",
) -> Dict[str, Any]:
    """
    Bulk import list of {source_text, translation, source_lang?, target_lang?} dictionaries.
    """
    imported_count = 0
    now = datetime.datetime.utcnow()

    for item in entries:
        src = (item.get("source_text") or "").strip()
        tgt = (item.get("translation") or "").strip()
        if not src or not tgt:
            continue

        src_l = item.get("source_language") or default_src_lang
        tgt_l = item.get("target_language") or default_tgt_lang

        existing = (
            db.query(TranslationMemory)
            .filter(
                TranslationMemory.source_text == src,
                TranslationMemory.source_language == src_l,
                TranslationMemory.target_language == tgt_l,
            )
            .first()
        )

        if existing:
            existing.translation = tgt
            existing.frequency = (existing.frequency or 1) + 1
            existing.last_used_at = now
        else:
            new_entry = TranslationMemory(
                source_text=src,
                translation=tgt,
                source_language=src_l,
                target_language=tgt_l,
                frequency=1,
                last_used_at=now,
            )
            db.add(new_entry)

        imported_count += 1

    db.commit()
    return {"status": "success", "imported_count": imported_count}


def export_tm_entries(
    db: Session,
    source_lang: Optional[str] = None,
    target_lang: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Export all translation memory records matching language filters.
    """
    q = db.query(TranslationMemory)
    if source_lang:
        q = q.filter(TranslationMemory.source_language == source_lang)
    if target_lang:
        q = q.filter(TranslationMemory.target_language == target_lang)

    records = q.order_by(TranslationMemory.frequency.desc()).all()
    return [
        {
            "source_text": r.source_text,
            "translation": r.translation,
            "source_language": r.source_language,
            "target_language": r.target_language,
            "frequency": r.frequency,
            "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
        }
        for r in records
    ]
