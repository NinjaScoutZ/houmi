"""License management routes for local desktop client.

These endpoints are mounted ONLY in local desktop mode (RUNTIME_MODE=local).
They allow the frontend to save and check offline license tokens that were
obtained from the Central Server (https://houmi.click).
"""
from __future__ import annotations

import datetime
import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

logger = logging.getLogger("houmi-license")

router = APIRouter(prefix="/license", tags=["License"])


class SaveTokenRequest(BaseModel):
    """Payload sent by the frontend after successful auth with Central Server."""
    user_id: str = Field(default="central_user")
    username: str = Field(default="user")
    status: str = Field(default="redeemed")  # "redeemed" or "logged_in"
    expires_at: str = Field(...)  # ISO 8601 datetime string
    redeem_code: str | None = Field(default=None)
    permissions: list[str] = Field(default_factory=list)


@router.post("/save-token")
def save_token(payload: SaveTokenRequest):
    """Save an offline license token received from Central Server.

    The frontend calls this after a successful login/redeem on
    https://houmi.click so the desktop app can work offline for up to 30 days.
    """
    from app.services.license_service import save_offline_license

    try:
        exp_dt = datetime.datetime.fromisoformat(
            payload.expires_at.replace("Z", "+00:00")
        ).replace(tzinfo=None)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid expires_at datetime format",
        )

    now = datetime.datetime.utcnow()
    max_offline_days = max(1, (exp_dt - now).days)

    save_offline_license(
        user_id=payload.user_id,
        username=payload.username,
        redeem_code=payload.redeem_code or "central-auth",
        expires_at=exp_dt,
        max_offline_days=min(max_offline_days, 30),
    )
    logger.info("Offline license saved for user %s, expires %s", payload.username, exp_dt)
    return {
        "ok": True,
        "message": "Offline license token saved successfully",
        "expires_at": str(exp_dt),
        "max_offline_days": min(max_offline_days, 30),
    }


@router.get("/status")
def get_license_status():
    """Check local offline license status and remaining days."""
    from app.services.license_service import verify_offline_license
    return verify_offline_license()
