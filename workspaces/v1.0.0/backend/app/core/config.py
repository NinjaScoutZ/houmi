"""
Houmi Studio - Core Configuration & Runtime Environment
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# Re-export from existing config to guarantee 100% backward compatibility
from app.config import (
    APP_DIR,
    BASE_DIR,
    DATA_DIR,
    PROJECTS_DIR,
    ASSET_STORAGE_DIR,
    RUNTIME_MODE,
    DATABASE_URL,
    PORT,
    HOST,
    _FROZEN,
)

CENTRAL_HOST = os.environ.get("HOUMI_CENTRAL_HOST", "https://houmi.click").rstrip("/")

CORE_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR

__all__ = [
    "APP_DIR",
    "BASE_DIR",
    "DATA_DIR",
    "PROJECTS_DIR",
    "ASSET_STORAGE_DIR",
    "RUNTIME_MODE",
    "DATABASE_URL",
    "PORT",
    "HOST",
    "CENTRAL_HOST",
    "_FROZEN",
    "CORE_DIR",
    "ROOT_DIR",
]
