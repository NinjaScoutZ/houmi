import pytest
from pathlib import Path
from app.services.dev_patch_service import record_dev_patch, get_dev_history

def test_record_and_read_dev_patch(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.dev_patch_service.PATCHES_DIR", tmp_path / "dev_patches")
    monkeypatch.setattr("app.services.dev_patch_service.MASTER_JSON_PATH", tmp_path / "dev_changelog.json")
    monkeypatch.setattr("app.services.dev_patch_service.CHANGELOG_MD_PATH", tmp_path / "CHANGELOG.md")

    patch_data = {
        "title": "Test Dev Feature",
        "summary": "Added dev patch logging service",
        "component_tags": ["Backend"],
        "changes": [{"category": "Added", "description": "Dev patch service"}]
    }

    record = record_dev_patch(patch_data)
    assert record["version_type"] == "Dev"
    assert "patch_id" in record

    history = get_dev_history()
    assert len(history["nodes"]) >= 1
    assert history["nodes"][0]["title"] == "Test Dev Feature"
