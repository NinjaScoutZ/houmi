"""Local-only storage for AI provider credentials and preferences.

Secrets deliberately live outside project settings and browser storage.  The
frontend receives only configuration/status metadata and masked key values,
never the full raw API keys. Supports Multi-Key priority management and auto-failover.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from app.config import DATA_DIR


SETTINGS_PATH = DATA_DIR / "settings" / "ai_provider.json"
VALID_PROVIDERS = {"auto", "google_api", "agy"}


def _load_raw_settings() -> dict[str, Any]:
    try:
        payload = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_raw_settings(payload: dict[str, Any]) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = SETTINGS_PATH.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary_path, SETTINGS_PATH)
    try:
        os.chmod(SETTINGS_PATH, 0o600)
    except OSError:
        pass


def _mask_key(key: str) -> str:
    cleaned = str(key or "").strip()
    if not cleaned:
        return ""
    if len(cleaned) <= 10:
        return cleaned[:3] + "..." + cleaned[-2:]
    return cleaned[:6] + "..." + cleaned[-4:]


def _normalize_keys_array(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Ensure raw settings contains a valid google_api_keys array.
    
    If legacy single 'google_api_key' exists, migrate it seamlessly to Key #1.
    """
    keys = raw.get("google_api_keys")
    if not isinstance(keys, list):
        keys = []

    # Check for legacy single google_api_key migration
    legacy_key = str(raw.get("google_api_key") or "").strip()
    if legacy_key and not any(item.get("key") == legacy_key for item in keys if isinstance(item, dict)):
        keys.insert(0, {
            "id": f"key_{uuid.uuid4().hex[:8]}",
            "name": "Primary Key (Default)",
            "key": legacy_key,
            "priority": 1,
            "enabled": True,
            "created_at": time.time(),
        })
        raw["google_api_keys"] = keys
        # Clean legacy string
        raw.pop("google_api_key", None)
        _write_raw_settings(raw)

    valid_items = []
    for idx, item in enumerate(keys):
        if not isinstance(item, dict) or not str(item.get("key") or "").strip():
            continue
        item_id = str(item.get("id") or f"key_{uuid.uuid4().hex[:8]}")
        item_name = str(item.get("name") or f"Key #{idx+1}").strip()
        item_key = str(item.get("key")).strip()
        item_priority = int(item.get("priority") or (idx + 1))
        item_enabled = bool(item.get("enabled", True))
        
        valid_items.append({
            "id": item_id,
            "name": item_name,
            "key": item_key,
            "priority": item_priority,
            "enabled": item_enabled,
            "created_at": item.get("created_at") or time.time(),
        })

    # Sort by priority ascending
    valid_items.sort(key=lambda x: x["priority"])
    # Normalize priority numbers to 1..N
    for i, k in enumerate(valid_items):
        k["priority"] = i + 1

    return valid_items


def get_ai_provider_preferences() -> dict[str, str]:
    """Return non-secret global settings for the font/style AI provider."""
    raw = _load_raw_settings()
    provider = str(raw.get("provider") or "auto").strip().lower()
    if provider not in VALID_PROVIDERS:
        provider = "auto"
    model_val = raw.get("model")
    model = str("gemini-3.7-flash" if model_val is None else model_val).strip()[:160]
    return {"provider": provider, "model": model}


def get_ai_provider_full_status() -> dict[str, Any]:
    """Return non-secret global settings and masked Multi-Key pool for frontend UI."""
    raw = _load_raw_settings()
    prefs = get_ai_provider_preferences()
    keys_list = _normalize_keys_array(raw)
    masked_keys = [
        {
            "id": k["id"],
            "name": k["name"],
            "key_mask": _mask_key(k["key"]),
            "priority": k["priority"],
            "enabled": k["enabled"],
        }
        for k in keys_list
    ]

    has_keys = any(k["enabled"] for k in keys_list) or bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))

    return {
        **prefs,
        "configured": has_keys,
        "has_google_api_key": has_keys,
        "configured_key_mask": masked_keys[0]["key_mask"] if masked_keys else (_mask_key(os.getenv("GOOGLE_API_KEY", "")) or None),
        "keys": masked_keys,
    }


def get_stored_google_api_key() -> str:
    """Return highest-priority active Google API key."""
    ordered = get_ordered_google_api_keys()
    return ordered[0] if ordered else ""


def get_ordered_google_api_keys() -> list[str]:
    """Return raw unmasked Google API keys in priority order (Priority 1 -> Priority 2 -> ...)."""
    raw = _load_raw_settings()
    has_explicit_keys_config = "google_api_keys" in raw or "google_api_key" in raw
    keys_list = _normalize_keys_array(raw)
    
    enabled_keys = [k["key"] for k in keys_list if k.get("enabled", True)]
    
    # Fallback to environment variables only if no explicit key config saved in json
    if not enabled_keys and not has_explicit_keys_config:
        env_key = (
            os.getenv("GOOGLE_API_KEY", "").strip()
            or os.getenv("GEMINI_API_KEY", "").strip()
            or os.getenv("HOUMI_GEMINI_API_KEY", "").strip()
        )
        if env_key:
            enabled_keys = [env_key]

    return enabled_keys


def add_google_api_key(name: str, key: str, priority: int | None = None) -> dict[str, Any]:
    """Add a new Google API key to the priority pool."""
    cleaned_key = str(key or "").strip()
    if not cleaned_key:
        raise ValueError("Google API key must not be empty")

    raw = _load_raw_settings()
    keys = _normalize_keys_array(raw)

    cleaned_name = str(name or f"Key #{len(keys) + 1}").strip()
    target_priority = priority if priority is not None else (len(keys) + 1)

    new_id = f"key_{uuid.uuid4().hex[:8]}"
    new_item = {
        "id": new_id,
        "name": cleaned_name,
        "key": cleaned_key,
        "priority": target_priority,
        "enabled": True,
        "created_at": time.time(),
    }

    keys.append(new_item)
    raw["google_api_keys"] = keys
    _normalize_keys_array(raw)
    _write_raw_settings(raw)
    return get_ai_provider_full_status()


def remove_google_api_key(key_id: str) -> dict[str, Any]:
    """Remove a key from the pool by ID."""
    raw = _load_raw_settings()
    keys = _normalize_keys_array(raw)
    keys = [k for k in keys if k["id"] != key_id]
    raw["google_api_keys"] = keys
    _normalize_keys_array(raw)
    _write_raw_settings(raw)
    return get_ai_provider_full_status()


def update_google_api_key_item(
    key_id: str,
    *,
    name: str | None = None,
    enabled: bool | None = None,
    priority: int | None = None,
) -> dict[str, Any]:
    """Update name, priority, or enabled status of a specific key."""
    raw = _load_raw_settings()
    keys = _normalize_keys_array(raw)

    target = None
    for k in keys:
        if k["id"] == key_id:
            target = k
            break

    if not target:
        raise ValueError(f"Key ID {key_id} not found")

    if name is not None:
        target["name"] = str(name).strip() or target["name"]
    if enabled is not None:
        target["enabled"] = bool(enabled)
    if priority is not None:
        target["priority"] = max(1, int(priority))

    raw["google_api_keys"] = keys
    _normalize_keys_array(raw)
    _write_raw_settings(raw)
    return get_ai_provider_full_status()


def reorder_google_api_keys(key_ids: list[str]) -> dict[str, Any]:
    """Reorder keys based on an ordered array of key IDs."""
    raw = _load_raw_settings()
    keys = _normalize_keys_array(raw)

    id_to_key = {k["id"]: k for k in keys}
    reordered = []

    for idx, k_id in enumerate(key_ids):
        if k_id in id_to_key:
            item = id_to_key.pop(k_id)
            item["priority"] = idx + 1
            reordered.append(item)

    for remaining_id, item in id_to_key.items():
        item["priority"] = len(reordered) + 1
        reordered.append(item)

    raw["google_api_keys"] = reordered
    _normalize_keys_array(raw)
    _write_raw_settings(raw)
    return get_ai_provider_full_status()


def update_ai_provider_preferences(
    *,
    provider: str | None = None,
    model: str | None = None,
    google_api_key: str | None = None,
    clear_google_api_key: bool = False,
) -> dict[str, Any]:
    """Persist preferences and optionally add/clear API keys."""
    raw = _load_raw_settings()
    if provider is not None:
        normalized_provider = str(provider).strip().lower()
        if normalized_provider not in VALID_PROVIDERS:
            raise ValueError("provider must be auto, google_api, or agy")
        raw["provider"] = normalized_provider
    if model is not None:
        raw["model"] = str(model).strip()[:160]

    if clear_google_api_key:
        raw["google_api_keys"] = []
        raw.pop("google_api_key", None)
    elif google_api_key is not None:
        normalized_key = str(google_api_key).strip()
        if not normalized_key:
            raise ValueError("google_api_key must not be empty; use clear_google_api_key instead")
        # Add as new Primary Key (priority 1)
        keys = _normalize_keys_array(raw)
        # Shift existing priorities down
        for k in keys:
            k["priority"] += 1
        keys.insert(0, {
            "id": f"key_{uuid.uuid4().hex[:8]}",
            "name": f"Key #{len(keys) + 1}",
            "key": normalized_key,
            "priority": 1,
            "enabled": True,
            "created_at": time.time(),
        })
        raw["google_api_keys"] = keys
        _normalize_keys_array(raw)

    _write_raw_settings(raw)
    return get_ai_provider_preferences()
