"""
Patch & Release Manifest Models with Cryptographic Integrity Verification
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


def calculate_file_sha256(file_path: Path) -> str:
    """Compute SHA-256 hex digest of a given file."""
    if not file_path.exists():
        raise FileNotFoundError(f"File not found for hash calculation: {file_path}")
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class PatchEntry(BaseModel):
    rel_path: str
    sha256: str
    size_bytes: int


class PatchManifest(BaseModel):
    version: str
    tag: str
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    patch_notes: str = ""
    size_mb: float = 0.0
    sha256_checksum: str = ""
    target_username: Optional[str] = None
    min_required_core_version: str = "1.0.0"
    files: List[PatchEntry] = Field(default_factory=list)


class RollbackRecord(BaseModel):
    version: str
    applied_at: str
    backup_path: str
    sha256: str
