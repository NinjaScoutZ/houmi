import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app
from app.services.changelog_service import get_all_changelogs, get_changelog_by_version, add_or_update_changelog
from app.services.gdrive_backup import get_gdrive_auth_status

def test_changelog_service_crud():
    logs = get_all_changelogs()
    assert isinstance(logs, list)
    assert len(logs) >= 1

    entry = get_changelog_by_version("1.0.4")
    assert entry is not None
    assert "Production Architecture" in entry.get("title", "")

    # Add a test changelog
    saved = add_or_update_changelog(
        version="1.0.9-test",
        title="Test Update",
        summary="Automated test entry",
        categories={"features": ["Test feature"]},
        is_latest=False
    )
    assert saved["version"] == "1.0.9-test"

def test_gdrive_auth_status():
    status = get_gdrive_auth_status()
    assert "connected" in status
    assert status["connected"] is True
    assert status["email"] == "workingappapt@gmail.com"

@pytest.mark.asyncio
async def test_changelogs_api_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/system/changelogs")
        assert res.status_code == 200
        data = res.json()
        assert "changelogs" in data or isinstance(data, list)
