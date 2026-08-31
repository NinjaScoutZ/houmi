from __future__ import annotations

import logging
import re
import shutil
import subprocess
import time
from typing import Any

logger = logging.getLogger("houmi-gemini-quota")

_QUOTA_STATUS: dict[str, Any] = {
    "quota_exceeded": False,
    "reason": None,
    "cooldown_reset": None,
    "last_checked_at": None,
    "provider": "AGY / Gemini AI",
}


def get_quota_status() -> dict[str, Any]:
    return dict(_QUOTA_STATUS)


def set_quota_exceeded(reason: str, cooldown_reset: str | None = None) -> None:
    _QUOTA_STATUS["quota_exceeded"] = True
    _QUOTA_STATUS["reason"] = reason
    _QUOTA_STATUS["cooldown_reset"] = cooldown_reset
    _QUOTA_STATUS["last_checked_at"] = time.time()
    logger.warning("AI Quota Exceeded recorded: %s (Reset: %s)", reason, cooldown_reset)


def reset_quota_status() -> None:
    _QUOTA_STATUS["quota_exceeded"] = False
    _QUOTA_STATUS["reason"] = None
    _QUOTA_STATUS["cooldown_reset"] = None
    _QUOTA_STATUS["last_checked_at"] = time.time()


def parse_and_record_quota_error(output_str: str) -> bool:
    """Inspect stderr/stdout string for Gemini/AGY quota limit errors.
    If matched, update global quota state and return True.
    """
    if not output_str:
        return False

    text = str(output_str)
    if (
        "Individual quota reached" in text
        or "429 Too Many Requests" in text
        or "Quota exceeded" in text
        or "RESOURCE_EXHAUSTED" in text
    ):
        match = re.search(r"Resets in\s+([^\.\n]+)", text, re.IGNORECASE)
        cooldown = match.group(1).strip() if match else None

        reason = "Individual quota reached"
        if cooldown:
            reason += f" (Resets in {cooldown})"
        elif "429" in text:
            reason = "HTTP 429 Rate Limit Exceeded"

        set_quota_exceeded(reason, cooldown)
        return True
    return False


def check_agy_cli_status() -> dict[str, Any]:
    """Test AGY CLI availability and check quota status directly."""
    agy_path = shutil.which("agy")
    if not agy_path:
        return {
            "available": False,
            "quota_exceeded": False,
            "reason": "AGY CLI not found in PATH",
            "cooldown_reset": None,
            "last_checked_at": time.time(),
        }

    try:
        res = subprocess.run(
            ["agy", "--dangerously-skip-permissions", "--print", "hello"],
            capture_output=True,
            text=True,
            timeout=15,
            encoding="utf-8",
            errors="replace",
            shell=(subprocess.os.name == "nt"),
        )
        combined = (res.stdout or "") + "\n" + (res.stderr or "")
        if parse_and_record_quota_error(combined):
            st = get_quota_status()
            st["available"] = True
            return st

        if res.returncode == 0:
            reset_quota_status()
            st = get_quota_status()
            st["available"] = True
            return st
        else:
            return {
                "available": True,
                "quota_exceeded": _QUOTA_STATUS["quota_exceeded"],
                "reason": res.stderr.strip() or "AGY CLI execution failed",
                "cooldown_reset": _QUOTA_STATUS["cooldown_reset"],
                "last_checked_at": time.time(),
            }
    except Exception as exc:
        return {
            "available": True,
            "quota_exceeded": _QUOTA_STATUS["quota_exceeded"],
            "reason": f"Check error: {exc}",
            "cooldown_reset": _QUOTA_STATUS["cooldown_reset"],
            "last_checked_at": time.time(),
        }
