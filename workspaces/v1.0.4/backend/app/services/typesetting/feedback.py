"""Minimal feedback event logging for typesetting decisions (Phase 0 instrumentation)."""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import DATA_DIR

logger = logging.getLogger("houmi-typesetting-feedback")

_LOCK = threading.Lock()
_DEFAULT_LOG_DIR = DATA_DIR / "feedback"
_DEFAULT_LOG_FILE = _DEFAULT_LOG_DIR / "typesetting_events.jsonl"

# Valid change_reason values (B+ Quality Contract)
CHANGE_REASONS = frozenset(
    {
        "accepted",
        "system_wrong",
        "user_preference",
        "suggested",  # system produced a suggestion (no user action yet)
        "auto_applied",
        "defaulted",
        "needs_review",
    }
)


def _log_path() -> Path:
    override = os.environ.get("HOUMI_TYPESETTING_FEEDBACK_PATH")
    if override:
        return Path(override)
    return _DEFAULT_LOG_FILE


def build_typesetting_decision_event(
    *,
    block_id: str,
    suggested_template: Optional[str] = None,
    selected_template: Optional[str] = None,
    suggested_lines: Optional[List[str]] = None,
    final_lines: Optional[List[str]] = None,
    change_reason: str = "suggested",
    decision_status: Optional[str] = None,
    engine_version: str = "",
    font_fingerprint: str = "",
    spec_revision: int = 1,
    suggested_spec_id: Optional[str] = None,
    current_spec_id: Optional[str] = None,
    style_confidence: Optional[float] = None,
    layout_confidence: Optional[float] = None,
    reason_codes: Optional[List[str]] = None,
    project_id: Optional[str] = None,
    page_id: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    reason = change_reason if change_reason in CHANGE_REASONS else "suggested"
    event: Dict[str, Any] = {
        "event": "typesetting_decision",
        "block_id": block_id,
        "suggested_template": suggested_template,
        "selected_template": selected_template,
        "suggested_lines": list(suggested_lines or []),
        "final_lines": list(final_lines if final_lines is not None else (suggested_lines or [])),
        "change_reason": reason,
        "decision_status": decision_status,
        "engine_version": engine_version,
        "font_fingerprint": font_fingerprint,
        "spec_revision": int(spec_revision),
        "suggested_spec_id": suggested_spec_id,
        "current_spec_id": current_spec_id,
        "style_confidence": style_confidence,
        "layout_confidence": layout_confidence,
        "reason_codes": list(reason_codes or []),
        "project_id": project_id,
        "page_id": page_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        event["extra"] = extra
    return event


def log_typesetting_decision(event: Dict[str, Any]) -> bool:
    """
    Append one JSONL feedback event. Never raises to callers — logging must not
    break the typesetting path.
    """
    try:
        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event, ensure_ascii=False, default=str)
        with _LOCK:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        return True
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to write typesetting feedback event: %s", exc)
        return False


def log_decision_from_spec(
    spec: Any,
    *,
    change_reason: str = "suggested",
    selected_template: Optional[str] = None,
    final_lines: Optional[List[str]] = None,
    project_id: Optional[str] = None,
    page_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build + persist an event from a TypesettingSpec-like object."""
    metrics = getattr(spec, "metrics", None) or {}
    descriptor = metrics.get("style_descriptor") if isinstance(metrics, dict) else None
    suggested_template = (
        descriptor.get("suggested_template")
        if isinstance(descriptor, dict)
        else None
    )
    applied_template = getattr(spec, "template_id", None)
    event = build_typesetting_decision_event(
        block_id=getattr(spec, "block_id", "") or "",
        suggested_template=suggested_template,
        selected_template=selected_template if selected_template is not None else applied_template,
        suggested_lines=list(getattr(spec, "explicit_lines", None) or []),
        final_lines=final_lines,
        change_reason=change_reason,
        decision_status=getattr(spec, "decision_status", None),
        engine_version=getattr(spec, "layout_engine_version", None)
        or getattr(spec, "layout_version", "")
        or "",
        font_fingerprint=getattr(spec, "font_fingerprint", "") or "",
        spec_revision=int(getattr(spec, "revision", 1) or 1),
        suggested_spec_id=getattr(spec, "spec_id", None),
        current_spec_id=getattr(spec, "spec_id", None),
        style_confidence=getattr(spec, "style_confidence", None),
        layout_confidence=getattr(spec, "layout_confidence", None),
        reason_codes=list(getattr(spec, "reason_codes", None) or []),
        project_id=project_id,
        page_id=page_id,
    )
    log_typesetting_decision(event)
    return event
