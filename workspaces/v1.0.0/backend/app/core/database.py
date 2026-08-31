"""
Houmi Studio - Core Database Engine & Session Provider
"""

from __future__ import annotations

from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from app.core.config import DATABASE_URL, RUNTIME_MODE
from app.database import engine as app_engine, SessionLocal as app_SessionLocal, Base as app_Base, get_db as app_get_db

engine = app_engine
SessionLocal = app_SessionLocal
Base = app_Base
get_db = app_get_db

__all__ = [
    "engine",
    "SessionLocal",
    "Base",
    "get_db",
]
