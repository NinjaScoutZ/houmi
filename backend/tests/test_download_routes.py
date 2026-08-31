import pytest
from httpx import ASGITransport, AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_download_landing_page_and_archives():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Test /download landing page HTML
        res_dl = await ac.get("/download")
        assert res_dl.status_code == 200
        assert "Houmi Studio" in res_dl.text
        assert "คลังเวอร์ชันทั้งหมด" in res_dl.text

        # 2. Test /api/download/latest
        res_latest = await ac.get("/api/download/latest")
        assert res_latest.status_code in (200, 404)

        # 3. Test /api/download/release/1.0.4
        res_v104 = await ac.get("/api/download/release/1.0.4")
        assert res_v104.status_code in (200, 404)
