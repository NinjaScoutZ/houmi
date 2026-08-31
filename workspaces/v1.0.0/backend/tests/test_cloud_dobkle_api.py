"""
Unit tests for DOBKLE Cloud Hub API Endpoints & Auth Gate
"""

import base64
import numpy as np
import cv2
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from unittest.mock import patch

from app.main import app


@pytest_asyncio.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def create_dummy_base64_image(width=100, height=100, color=(255, 255, 255)) -> str:
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:] = color
    _, buf = cv2.imencode(".png", img)
    return "data:image/png;base64," + base64.b64encode(buf).decode("utf-8")


def create_dummy_base64_mask(width=100, height=100, mask_box=(20, 20, 40, 40)) -> str:
    mask = np.zeros((height, width), dtype=np.uint8)
    x, y, w, h = mask_box
    mask[y:y+h, x:x+w] = 255
    _, buf = cv2.imencode(".png", mask)
    return "data:image/png;base64," + base64.b64encode(buf).decode("utf-8")


@pytest.mark.asyncio
async def test_cloud_hub_status(async_client):
    """Verify GET /api/cloud/dobkle/status returns online status and capabilities."""
    response = await async_client.get("/api/cloud/dobkle/status")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "online"
    assert data.get("service") == "DOBKLE Cloud AI Hub"
    assert "agy" in data
    assert "capabilities" in data
    assert "ocr" in data["capabilities"]
    assert "clean" in data["capabilities"]


@pytest.mark.asyncio
async def test_cloud_auth_rejection(async_client):
    """Verify requests with missing or invalid API keys are rejected with 401."""
    # Without header
    res_no_key = await async_client.post(
        "/api/cloud/dobkle/ocr",
        json={"crops": [{"id": "b1", "image_base64": create_dummy_base64_image()}]},
    )
    assert res_no_key.status_code == 401

    # With invalid key
    res_bad_key = await async_client.post(
        "/api/cloud/dobkle/ocr",
        headers={"X-Dobkle-Api-Key": "invalid_wrong_key_999"},
        json={"crops": [{"id": "b1", "image_base64": create_dummy_base64_image()}]},
    )
    assert res_bad_key.status_code == 401


@pytest.mark.asyncio
async def test_cloud_clean_endpoint(async_client):
    """Verify POST /api/cloud/dobkle/clean executes inpainting and returns cleaned base64."""
    img_b64 = create_dummy_base64_image(120, 120, color=(200, 200, 200))
    mask_b64 = create_dummy_base64_mask(120, 120, mask_box=(30, 30, 30, 30))

    response = await async_client.post(
        "/api/cloud/dobkle/clean",
        headers={"X-Dobkle-Api-Key": "dobkle_master_key"},
        json={
            "image_base64": img_b64,
            "mask_base64": mask_b64,
            "engine": "telea",
            "dilation": 2,
            "format": "png",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("ok") is True
    assert "cleaned_image_base64" in data
    assert data.get("width") == 120
    assert data.get("height") == 120


@pytest.mark.asyncio
async def test_cloud_ocr_endpoint_with_mock(async_client):
    """Verify POST /api/cloud/dobkle/ocr packages crops and parses Gemini response."""
    img_b64 = create_dummy_base64_image(80, 80)
    
    mock_gemini_json = """[
        {
            "box_id": "BOX_001_b1000000",
            "text": "Hello Dobkle Cloud!",
            "balloon_type": "shout",
            "color_hex": "#FF0000",
            "bold": true
        }
    ]"""

    with patch("app.services.cloud_dobkle_service._run_gemini_command") as mock_agy:
        mock_agy.return_value = (mock_gemini_json, True)

        response = await async_client.post(
            "/api/cloud/dobkle/ocr",
            headers={"X-Dobkle-Api-Key": "dobkle_master_key"},
            json={
                "crops": [{"id": "b1000000", "image_base64": img_b64}],
                "source_lang": "en",
                "ocr_depth": "full",
                "model": "flash",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("ok") is True
        assert len(data.get("results", [])) == 1
        result = data["results"][0]
        assert result.get("id") == "b1000000"
        assert result.get("text") == "Hello Dobkle Cloud!"
        assert result.get("balloon_type") == "shout"
        assert result.get("color_hex") == "#FF0000"
        assert result.get("bold") is True
