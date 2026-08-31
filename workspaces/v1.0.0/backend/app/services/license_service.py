import os
import json
import time
import hmac
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from app.config import DATA_DIR

logger = logging.getLogger("houmi-license-service")

LICENSE_FILE_PATH = DATA_DIR / "license.json"
LICENSE_SECRET = os.environ.get("HOUMI_LICENSE_SECRET", "houmi_super_secret_license_hmac_key_2026")


def _generate_token_signature(payload_str: str) -> str:
    """Generate SHA256 HMAC signature for license payload."""
    return hmac.new(
        LICENSE_SECRET.encode("utf-8"),
        payload_str.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def save_offline_license(
    user_id: str,
    username: str,
    redeem_code: str,
    expires_at: datetime,
    max_offline_days: int = 30
) -> Dict[str, Any]:
    """Save an HMAC-signed offline license token to local DATA_DIR."""
    expires_timestamp = int(expires_at.replace(tzinfo=timezone.utc).timestamp()) if expires_at.tzinfo else int(expires_at.timestamp())
    now_timestamp = int(time.time())

    payload = {
        "user_id": user_id,
        "username": username,
        "redeem_code": redeem_code,
        "issued_at": now_timestamp,
        "expires_at": expires_timestamp,
        "max_offline_days": max_offline_days,
        "last_verified_clock": now_timestamp,
    }

    payload_json = json.dumps(payload, sort_keys=True)
    signature = _generate_token_signature(payload_json)

    data = {
        "payload": payload,
        "signature": signature,
    }

    LICENSE_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LICENSE_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    logger.info(f"Offline license token saved for user {username}, expires: {expires_at}")
    return data


def verify_offline_license() -> Dict[str, Any]:
    """Verify local offline license file validity, clock rollback protection, and expiration status."""
    if not LICENSE_FILE_PATH.exists():
        return {
            "valid": False,
            "status": "unactivated",
            "message": "No active license token found. Redeem code required.",
            "days_left": 0,
        }

    try:
        with open(LICENSE_FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        payload = data.get("payload", {})
        signature = data.get("signature", "")

        payload_json = json.dumps(payload, sort_keys=True)
        expected_sig = _generate_token_signature(payload_json)

        if not hmac.compare_digest(signature, expected_sig):
            return {
                "valid": False,
                "status": "tampered",
                "message": "License token signature invalid or tampered.",
                "days_left": 0,
            }

        now = int(time.time())
        expires_at = payload.get("expires_at", 0)
        last_verified_clock = payload.get("last_verified_clock", 0)

        # Anti-clock rollback check: system clock must not be moved backward by > 1 hour
        if now < last_verified_clock - 3600:
            return {
                "valid": False,
                "status": "clock_tampered",
                "message": "System clock rollback detected. Online re-validation required.",
                "days_left": 0,
            }

        # Update last verified clock if moving forward
        if now > last_verified_clock:
            payload["last_verified_clock"] = now
            new_sig = _generate_token_signature(json.dumps(payload, sort_keys=True))
            with open(LICENSE_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump({"payload": payload, "signature": new_sig}, f, indent=2)

        if now >= expires_at:
            return {
                "valid": False,
                "status": "expired",
                "message": "License period expired. Please redeem a new code.",
                "days_left": 0,
            }

        seconds_left = max(0, expires_at - now)
        days_left = max(1, int(seconds_left // 86400))

        return {
            "valid": True,
            "status": "active",
            "message": f"License active ({days_left} days remaining)",
            "days_left": days_left,
            "expires_at": datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(),
            "user_id": payload.get("user_id"),
            "username": payload.get("username"),
            "redeem_code": payload.get("redeem_code"),
        }

    except Exception as exc:
        logger.error(f"License verification error: {exc}")
        return {
            "valid": False,
            "status": "error",
            "message": f"License verification error: {str(exc)}",
            "days_left": 0,
        }
