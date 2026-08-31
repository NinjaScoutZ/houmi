"""
Reversible Rollback Engine for Houmi OTA Delta Patches
Manages rollback snapshots and atomic reversion.
"""

from __future__ import annotations

import os
import json
import shutil
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import DATA_DIR
from app.patches.manifest import RollbackRecord, calculate_file_sha256

logger = logging.getLogger("houmi-rollback")

PATCHES_DIR = DATA_DIR / "patches"
CURRENT_PATCH_DIR = PATCHES_DIR / "current"
BACKUPS_DIR = PATCHES_DIR / "backups"
BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
ROLLBACK_LEDGER_FILE = PATCHES_DIR / "rollback_ledger.json"


def get_rollback_history() -> List[Dict[str, Any]]:
    """Return all available rollback snapshots."""
    if not ROLLBACK_LEDGER_FILE.exists():
        return []
    try:
        with open(ROLLBACK_LEDGER_FILE, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to read rollback ledger: {e}")
        return []


def create_rollback_snapshot(current_version: str) -> Optional[RollbackRecord]:
    """Create a zipped or folder snapshot of the current active patch before applying a new one."""
    if not CURRENT_PATCH_DIR.exists() or not any(CURRENT_PATCH_DIR.iterdir()):
        logger.info("No existing patch in current/ to snapshot.")
        return None

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    snapshot_name = f"backup_{current_version}_{timestamp}"
    snapshot_dir = BACKUPS_DIR / snapshot_name

    try:
        shutil.copytree(CURRENT_PATCH_DIR, snapshot_dir)
        record = RollbackRecord(
            version=current_version,
            applied_at=datetime.utcnow().isoformat(),
            backup_path=str(snapshot_dir),
            sha256="",
        )

        history = get_rollback_history()
        history.insert(0, record.model_dump())
        # Retain last 5 snapshots to save disk
        history = history[:5]

        with open(ROLLBACK_LEDGER_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)

        logger.info(f"Rollback snapshot created: {snapshot_dir}")
        return record
    except Exception as exc:
        logger.error(f"Failed to create rollback snapshot: {exc}")
        return None


def execute_rollback(target_version: Optional[str] = None) -> Dict[str, Any]:
    """Revert current active patch to the most recent or specified rollback snapshot."""
    history = get_rollback_history()
    if not history:
        raise RuntimeError("No rollback snapshots available in ledger.")

    target_record: Optional[Dict[str, Any]] = None
    if target_version:
        for rec in history:
            if rec.get("version") == target_version:
                target_record = rec
                break
        if not target_record:
            raise ValueError(f"Snapshot for version {target_version} not found in ledger.")
    else:
        target_record = history[0]

    backup_path = Path(target_record["backup_path"])
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup snapshot path missing on disk: {backup_path}")

    # Atomic swap: Staging restore
    staging_restore = PATCHES_DIR / "staging_restore"
    if staging_restore.exists():
        shutil.rmtree(staging_restore, ignore_errors=True)

    shutil.copytree(backup_path, staging_restore)

    # Move current to temp and staging to current
    temp_old = PATCHES_DIR / "temp_old_revert"
    if temp_old.exists():
        shutil.rmtree(temp_old, ignore_errors=True)

    if CURRENT_PATCH_DIR.exists():
        CURRENT_PATCH_DIR.rename(temp_old)

    staging_restore.rename(CURRENT_PATCH_DIR)

    if temp_old.exists():
        shutil.rmtree(temp_old, ignore_errors=True)

    logger.info(f"Successfully rolled back to version {target_record.get('version')}")
    return {
        "ok": True,
        "rolled_back_to": target_record.get("version"),
        "restored_from": str(backup_path),
        "timestamp": datetime.utcnow().isoformat(),
    }
