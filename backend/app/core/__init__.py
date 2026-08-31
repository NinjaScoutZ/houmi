"""
Houmi Studio - Core Architecture Subsystem
Stable production primitives: config, database, events, security.
"""

from app.core.config import APP_DIR, BASE_DIR, DATA_DIR, RUNTIME_MODE
from app.core.database import engine, SessionLocal, Base, get_db
from app.core.events import lifespan
from app.core.security import get_authenticated_user, require_admin

__all__ = [
    "APP_DIR",
    "BASE_DIR",
    "DATA_DIR",
    "RUNTIME_MODE",
    "engine",
    "SessionLocal",
    "Base",
    "get_db",
    "lifespan",
    "get_authenticated_user",
    "require_admin",
]
