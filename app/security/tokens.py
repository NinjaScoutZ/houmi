from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import (
    ACCESS_TOKEN_TTL_MINUTES,
    JWT_ALGORITHM,
    JWT_ISSUER,
    JWT_SECRET,
    REFRESH_TOKEN_TTL_DAYS,
)


password_hasher = PasswordHasher()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    if not password or len(password) < 8:
        raise ValueError("Password must contain at least 8 characters")
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def needs_password_rehash(password_hash: str) -> bool:
    try:
        return password_hasher.check_needs_rehash(password_hash)
    except (InvalidHashError, VerificationError):
        return False


def hash_opaque_token(token: str) -> str:
    """Hash a high-entropy opaque token before persisting it."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(*, user_id: str, role: str, session_id: str | None = None) -> str:
    now = utcnow()
    claims: dict[str, Any] = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_TTL_MINUTES),
        "iss": JWT_ISSUER,
        "jti": str(uuid.uuid4()),
    }
    if session_id:
        claims["sid"] = session_id
    return jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    claims = jwt.decode(
        token,
        JWT_SECRET,
        algorithms=[JWT_ALGORITHM],
        issuer=JWT_ISSUER,
        options={"require": ["sub", "type", "iat", "nbf", "exp", "iss", "jti"]},
    )
    if claims.get("type") != "access":
        raise jwt.InvalidTokenError("Token is not an access token")
    return claims


def issue_refresh_token() -> tuple[str, str, datetime]:
    raw_token = secrets.token_urlsafe(48)
    expires_at = utcnow() + timedelta(days=REFRESH_TOKEN_TTL_DAYS)
    return raw_token, hash_opaque_token(raw_token), expires_at
