"""
Unit and integration tests for Pipeline Cloud Integration (dobkle_cloud)
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest_asyncio.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_ocr_engines_includes_dobkle_cloud(async_client):
    """Verify GET /api/pipeline/ocr/engines includes dobkle_cloud with available status."""
    response = await async_client.get("/api/pipeline/ocr/engines")
    assert response.status_code == 200
    data = response.json()
    assert "engines" in data

    cloud_engine = next((e for e in data["engines"] if e.get("id") == "dobkle_cloud"), None)
    assert cloud_engine is not None
    assert cloud_engine["name"] == "☁️ DOBKLE Cloud OCR (AGY Server)"
    assert cloud_engine["category"] == "cloud"
    assert cloud_engine["available"] is True


@pytest.mark.asyncio
async def test_cloud_pipeline_health_endpoint(async_client):
    """Verify GET /api/cloud/dobkle/health is mounted and returns 200."""
    response = await async_client.get("/api/cloud/dobkle/health")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "online"
    assert data.get("service") == "DOBKLE Cloud AI Hub"
