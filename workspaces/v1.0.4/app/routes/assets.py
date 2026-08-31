from __future__ import annotations

import hashlib
import mimetypes
import uuid
import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import ASSET_STORAGE_DIR, USER_STORAGE_QUOTA_BYTES
from app.database import get_db
from app.models.all_models import Asset, Project, User
from app.security.dependencies import ensure_project_access, get_authenticated_user, require_resource_access
from app.services.asset_service import MAX_ASSET_BYTES, validate_asset_payload


router = APIRouter(tags=["Assets"])


def _safe_storage_path(storage_key: str) -> Path:
    root = ASSET_STORAGE_DIR.resolve()
    candidate = (root / storage_key).resolve()
    if candidate != root and root not in candidate.parents:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return candidate


def _asset_payload(asset: Asset) -> dict:
    return {
        "id": asset.id,
        "project_id": asset.project_id,
        "original_filename": asset.original_filename,
        "media_type": asset.media_type,
        "byte_size": asset.byte_size,
        "width": asset.width,
        "height": asset.height,
        "status": asset.status,
        "created_at": asset.created_at,
    }


@router.post("/assets", status_code=status.HTTP_201_CREATED)
async def upload_asset(
    file: UploadFile = File(...),
    project_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_authenticated_user),
):
    if project_id:
        ensure_project_access(db.query(Project).filter(Project.id == project_id).first(), current_user)

    payload = await file.read(MAX_ASSET_BYTES + 1)
    try:
        validated = validate_asset_payload(
            payload,
            declared_media_type=file.content_type,
            filename=file.filename,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    used_bytes = db.query(func.coalesce(func.sum(Asset.byte_size), 0)).filter(
        Asset.owner_id == current_user.id,
        Asset.deleted_at.is_(None),
    ).scalar() or 0
    if int(used_bytes) + validated.byte_size > USER_STORAGE_QUOTA_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="User storage quota exceeded")

    asset_id = str(uuid.uuid4())
    suffix = Path(file.filename or "asset").suffix.lower()
    if not suffix:
        suffix = mimetypes.guess_extension(validated.media_type) or ".bin"
    storage_key = f"{current_user.id}/{asset_id}{suffix}"
    path = _safe_storage_path(storage_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)

    asset = Asset(
        id=asset_id,
        owner_id=current_user.id,
        project_id=project_id,
        storage_key=storage_key,
        original_filename=(file.filename or "asset")[:255],
        media_type=validated.media_type,
        byte_size=validated.byte_size,
        width=validated.width,
        height=validated.height,
        sha256=hashlib.sha256(payload).hexdigest(),
    )
    try:
        db.add(asset)
        db.commit()
        db.refresh(asset)
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    return _asset_payload(asset)


@router.get("/assets")
def list_assets(
    project_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_authenticated_user),
):
    query = db.query(Asset).filter(Asset.owner_id == current_user.id, Asset.deleted_at.is_(None))
    if project_id:
        ensure_project_access(db.query(Project).filter(Project.id == project_id).first(), current_user)
        query = query.filter(Asset.project_id == project_id)
    return [_asset_payload(asset) for asset in query.order_by(Asset.created_at.desc()).all()]


@router.get("/assets/{asset_id}")
def get_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_authenticated_user),
    _: User = Depends(require_resource_access),
):
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.deleted_at.is_(None)).first()
    if asset is None or (current_user.role != "admin" and asset.owner_id != current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return _asset_payload(asset)


@router.get("/assets/{asset_id}/download")
def download_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_authenticated_user),
    _: User = Depends(require_resource_access),
):
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.deleted_at.is_(None)).first()
    if asset is None or (current_user.role != "admin" and asset.owner_id != current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    path = _safe_storage_path(asset.storage_key)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset content is missing")
    asset.last_accessed_at = datetime.datetime.utcnow()
    db.commit()
    return FileResponse(path, media_type=asset.media_type, filename=asset.original_filename)


@router.delete("/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_authenticated_user),
    _: User = Depends(require_resource_access),
):
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.deleted_at.is_(None)).first()
    if asset is None or (current_user.role != "admin" and asset.owner_id != current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    asset.status = "deleted"
    asset.deleted_at = datetime.datetime.utcnow()
    db.commit()
    return None
