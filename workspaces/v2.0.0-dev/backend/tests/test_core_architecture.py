import pytest
from app.core import APP_DIR, BASE_DIR, DATA_DIR, get_db, SessionLocal
from app.core.security import generate_opaque_token, hash_opaque_token, verify_opaque_token

def test_core_primitives_resolution():
    assert APP_DIR.exists()
    assert BASE_DIR.exists()
    assert DATA_DIR.exists()

def test_core_database_session():
    db = SessionLocal()
    assert db is not None
    db.close()

def test_core_security_primitives():
    token = generate_opaque_token(32)
    h = hash_opaque_token(token)
    assert verify_opaque_token(token, h) is True
    assert verify_opaque_token("wrong-token", h) is False
