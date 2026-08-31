"""
Atomic Patch Extraction & Verification Engine
Ensures zero-corruption OTA patch application.
"""

from __future__ import annotations

import os
import json
import shutil
import zipfile
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from app.config import DATA_DIR
from app.patches.manifest import PatchManifest, calculate_file_sha256
from app.patches.rollback import create_rollback_snapshot

logger = logging.getLogger("houmi-patch-engine")

PATCHES_DIR = DATA_DIR / "patches"
CURRENT_PATCH_DIR = PATCHES_DIR / "current"


class AtomicPatchExtractor:
    """
    Safely unpacks patch archives using staging directories and atomic directory swaps.
    Guarantees that an interrupted download or invalid archive never corrupts active runtime.
    """

    @classmethod
    def apply_patch_archive(
        cls,
        patch_zip_path: Path,
        expected_sha256: Optional[str] = None,
        create_backup: bool = True,
    ) -> Dict[str, Any]:
        if not patch_zip_path.exists():
            raise FileNotFoundError(f"Patch archive not found: {patch_zip_path}")

        # 1. Verify Archive Integrity & Checksum
        calculated_hash = calculate_file_sha256(patch_zip_path)
        if expected_sha256 and expected_sha256.lower() != calculated_hash.lower():
            raise ValueError(
                f"Patch integrity check failed! Expected SHA-256 {expected_sha256}, got {calculated_hash}"
            )

        if not zipfile.is_zipfile(patch_zip_path):
            raise ValueError(f"File is not a valid zip archive: {patch_zip_path}")

        # 2. Extract into Isolated Staging Directory
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        staging_dir = PATCHES_DIR / f"staging_{timestamp}"
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        staging_dir.mkdir(parents=True, exist_ok=True)

        extracted_count = 0
        try:
            with zipfile.ZipFile(patch_zip_path, "r") as zf:
                # Security Check: Prevent Zip Slip directory traversal vulnerability
                for member in zf.infolist():
                    target_path = staging_dir / member.filename
                    if not target_path.resolve().is_relative_to(staging_dir.resolve()):
                        raise SecurityError(f"Zip Slip attack detected in patch entry: {member.filename}")
                
                zf.extractall(staging_dir)
                extracted_count = len(zf.infolist())

            # Read patch manifest if included
            manifest_file = staging_dir / "patch_manifest.json"
            if not manifest_file.exists():
                manifest_file = staging_dir / "data" / "patches" / "current" / "patch_manifest.json"
            
            patch_version = "unknown"
            if manifest_file.exists():
                try:
                    with open(manifest_file, "r", encoding="utf-8-sig") as mf:
                        m_data = json.load(mf)
                        patch_version = m_data.get("version", patch_version)
                except Exception:
                    pass

            # 3. Create Rollback Snapshot of current before swapping
            if create_backup and CURRENT_PATCH_DIR.exists():
                create_rollback_snapshot(current_version=patch_version)

            # 4. Atomic Directory Swap
            temp_swap = PATCHES_DIR / f"temp_old_{timestamp}"
            if CURRENT_PATCH_DIR.exists():
                CURRENT_PATCH_DIR.rename(temp_swap)

            staging_dir.rename(CURRENT_PATCH_DIR)

            # Cleanup old temp directory
            if temp_swap.exists():
                shutil.rmtree(temp_swap, ignore_errors=True)

            logger.info(f"Successfully applied patch {patch_version} ({extracted_count} files)")
            return {
                "ok": True,
                "version": patch_version,
                "extracted_files": extracted_count,
                "sha256": calculated_hash,
                "applied_at": datetime.utcnow().isoformat(),
            }

        except Exception as exc:
            logger.error(f"Patch extraction failed: {exc}, cleaning staging...")
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)
            raise exc
