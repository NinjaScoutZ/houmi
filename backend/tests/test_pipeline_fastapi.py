import sys
from pathlib import Path
sys.path.insert(0, str(Path(r"E:\houmi\backend").resolve()))

import pytest
import httpx
from app.main import app

@pytest.mark.anyio
async def test_api_health():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get("/api/system/check-update")
        assert res.status_code == 200
        print("Health check: PASS")

@pytest.mark.anyio
async def test_api_projects():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        res = await client.get("/api/projects")
        assert res.status_code == 200
        print(f"Projects count: {len(res.json())} - PASS")


if __name__ == "__main__":
    test_api_health()
    test_api_projects()
    print("ALL IN-PROCESS FASTAPI PIPELINE TESTS PASSED!")
