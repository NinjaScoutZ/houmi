"""
Houmi Studio - Core Security, Tokens, and Permission Gates
"""

from __future__ import annotations

import secrets
from app.security.tokens import (
    create_access_token,
    decode_access_token,
    hash_opaque_token,
    hash_password,
    verify_password,
    issue_refresh_token,
)
from app.security.dependencies import (
    get_authenticated_user,
    get_current_user_or_local,
    require_admin,
    require_worker,
    require_pipeline_access,
    require_resource_access,
)


def generate_opaque_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def verify_opaque_token(token: str, expected_hash: str) -> bool:
    return hash_opaque_token(token) == expected_hash


__all__ = [
    "create_access_token",
    "decode_access_token",
    "generate_opaque_token",
    "hash_opaque_token",
    "verify_opaque_token",
    "hash_password",
    "verify_password",
    "issue_refresh_token",
    "get_authenticated_user",
    "get_current_user_or_local",
    "require_admin",
    "require_worker",
    "require_pipeline_access",
    "require_resource_access",
]
