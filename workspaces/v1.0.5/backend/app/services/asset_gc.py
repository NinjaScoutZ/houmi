from __future__ import annotations

import datetime
import logging
from pathlib import Path
from sqlalchemy.orm import Session

from app.models.all_models import Asset, Page, RemoteJob

logger = logging.getLogger("houmi-asset-gc")

def purge_expired_assets(db: Session, dry_run: bool = False) -> dict[str, int]:
    """Scans and purges expired, uploading-stale, or orphaned assets from storage."""
    now = datetime.datetime.utcnow()
    stale_upload_time = now - datetime.timedelta(hours=24)
    
    purged_count = 0
    bytes_reclaimed = 0

    # 1. Purge assets marked as 'deleted' or 'uploading' stale (> 24 hours)
    expired_assets = (
        db.query(Asset)
        .filter(
            (Asset.status == "deleted") |
            ((Asset.status == "uploading") & (Asset.created_at < stale_upload_time)) |
            ((Asset.retention_until.is_not(None)) & (Asset.retention_until < now))
        )
        .all()
    )

    for asset in expired_assets:
        # Check if active page or job relies on this asset
        is_referenced = (
            db.query(Page).filter((Page.source_image_path == asset.storage_key) | (Page.rendered_image_path == asset.storage_key)).first() is not None or
            db.query(RemoteJob).filter(RemoteJob.result_asset_id == asset.id).first() is not None
        )
        if is_referenced:
            continue

        file_path = Path(asset.storage_key)
        if file_path.exists() and file_path.is_file():
            if not dry_run:
                try:
                    file_size = file_path.stat().st_size
                    file_path.unlink()
                    bytes_reclaimed += file_size
                except Exception as e:
                    logger.error("Failed to delete physical file %s: %s", file_path, e)
        
        if not dry_run:
            db.delete(asset)
            purged_count += 1

    if not dry_run:
        db.commit()

    logger.info("Asset GC complete: purged %d assets, reclaimed %.2f MB", purged_count, bytes_reclaimed / (1024 * 1024))
    return {"purged_count": purged_count, "bytes_reclaimed": bytes_reclaimed}
