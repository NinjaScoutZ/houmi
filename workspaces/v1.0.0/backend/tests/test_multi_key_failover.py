import pytest
from unittest.mock import MagicMock, patch
from app.services.ai_provider_settings import (
    add_google_api_key,
    remove_google_api_key,
    reorder_google_api_keys,
    update_google_api_key_item,
    get_ordered_google_api_keys,
    get_ai_provider_preferences,
    update_ai_provider_preferences,
)
from app.services.ocr import _get_all_gemini_api_keys, _run_gemini_rest_ocr

def test_multi_key_management(tmp_path, monkeypatch):
    from app.services import ai_provider_settings
    monkeypatch.setattr(ai_provider_settings, "SETTINGS_PATH", tmp_path / "settings" / "ai_provider.json")
    # Clear keys first
    update_ai_provider_preferences(clear_google_api_key=True)

    # 1. Add Key #1 (Primary)
    pref1 = add_google_api_key(name="Key Primary", key="AIzaSyPrimary111111", priority=1)
    assert len(pref1["keys"]) == 1
    assert pref1["keys"][0]["name"] == "Key Primary"
    assert pref1["keys"][0]["priority"] == 1

    # 2. Add Key #2 (Secondary)
    pref2 = add_google_api_key(name="Key Secondary", key="AIzaSySecondary222222", priority=2)
    assert len(pref2["keys"]) == 2
    assert pref2["keys"][1]["name"] == "Key Secondary"
    assert pref2["keys"][1]["priority"] == 2

    # 3. Verify ordered keys returns raw keys in priority order
    ordered = get_ordered_google_api_keys()
    assert ordered == ["AIzaSyPrimary111111", "AIzaSySecondary222222"]

    # 4. Reorder: move Key Secondary to Priority 1
    key1_id = pref2["keys"][0]["id"]
    key2_id = pref2["keys"][1]["id"]
    pref_reordered = reorder_google_api_keys([key2_id, key1_id])

    ordered_after_reorder = get_ordered_google_api_keys()
    assert ordered_after_reorder == ["AIzaSySecondary222222", "AIzaSyPrimary111111"]

    # 5. Delete key
    pref_deleted = remove_google_api_key(key2_id)
    assert len(pref_deleted["keys"]) == 1

def test_multi_key_failover_on_429(tmp_path, monkeypatch):
    from app.services import ai_provider_settings
    monkeypatch.setattr(ai_provider_settings, "SETTINGS_PATH", tmp_path / "settings" / "ai_provider.json")
    update_ai_provider_preferences(clear_google_api_key=True)
    add_google_api_key(name="Key 1 (Rate Limited)", key="AIzaSyKey1Bad", priority=1)
    add_google_api_key(name="Key 2 (Working Backup)", key="AIzaSyKey2Good", priority=2)

    with patch("httpx.post") as mock_post, patch("pathlib.Path.read_bytes", return_value=b"fake_image_bytes"):
        # First call (Key 1) returns 429 Rate Limit
        mock_resp_429 = MagicMock()
        mock_resp_429.status_code = 429

        # Second call (Key 2) returns 200 OK
        mock_resp_200 = MagicMock()
        mock_resp_200.status_code = 200
        mock_resp_200.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Manga Text Line 1"}]}}]
        }

        mock_post.side_effect = [mock_resp_429, mock_resp_200]

        text, ok = _run_gemini_rest_ocr("Prompt", "test_dummy.png", model="gemini-2.5-flash")
        assert ok is True
        assert text == "Manga Text Line 1"
        assert mock_post.call_count == 2

        # Check headers of 2nd call used Key #2 ("AIzaSyKey2Good")
        assert mock_post.call_args_list[1].kwargs["headers"]["x-goog-api-key"] == "AIzaSyKey2Good"
