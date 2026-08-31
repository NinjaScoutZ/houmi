import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import ai_provider_settings


def test_global_ai_provider_preferences_keep_google_key_out_of_public_config(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings" / "ai_provider.json"
    monkeypatch.setattr(ai_provider_settings, "SETTINGS_PATH", settings_path)

    saved = ai_provider_settings.update_ai_provider_preferences(
        provider="google_api",
        model="gemini-2.5-flash",
        google_api_key="secret-key",
    )

    assert saved == {"provider": "google_api", "model": "gemini-2.5-flash"}
    assert ai_provider_settings.get_ai_provider_preferences() == saved
    assert ai_provider_settings.get_stored_google_api_key() == "secret-key"
    assert "secret-key" not in json.dumps(ai_provider_settings.get_ai_provider_preferences())


def test_global_ai_provider_key_can_be_removed_without_resetting_preference(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings" / "ai_provider.json"
    monkeypatch.setattr(ai_provider_settings, "SETTINGS_PATH", settings_path)
    ai_provider_settings.update_ai_provider_preferences(
        provider="agy",
        model="",
        google_api_key="secret-key",
    )

    saved = ai_provider_settings.update_ai_provider_preferences(clear_google_api_key=True)

    assert saved == {"provider": "agy", "model": ""}
    assert ai_provider_settings.get_stored_google_api_key() == ""


def test_global_ai_provider_rejects_unknown_provider(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_provider_settings, "SETTINGS_PATH", tmp_path / "ai_provider.json")

    with pytest.raises(ValueError, match="provider must be"):
        ai_provider_settings.update_ai_provider_preferences(provider="unknown")


def test_ai_provider_status_endpoint_never_returns_the_google_key(tmp_path, monkeypatch):
    monkeypatch.setattr(
        ai_provider_settings,
        "SETTINGS_PATH",
        tmp_path / "settings" / "ai_provider.json",
    )
    ai_provider_settings.update_ai_provider_preferences(
        provider="google_api",
        google_api_key="secret-key-that-must-not-appear",
    )

    response = TestClient(app).get("/api/settings/ai-provider")

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "google_api"
    assert data["has_google_api_key"] is True
    assert "secret-key-that-must-not-appear" not in response.text
