import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_dev_map_routes():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/dev-map/history")
        assert res.status_code == 200
        data = res.json()
        assert "nodes" in data

        ctx_res = await ac.get("/api/dev-map/context")
        assert ctx_res.status_code == 200

        post_res = await ac.post("/api/dev-map/record", json={
            "title": "API Test Patch",
            "summary": "Testing endpoint",
            "component_tags": ["Test"]
        })
        assert post_res.status_code == 200
        assert post_res.json()["version_type"] == "Dev"
