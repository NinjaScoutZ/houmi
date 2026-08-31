"""Tests for fast Telea inpaint preview endpoint."""

import base64
import cv2
import numpy as np
from unittest.mock import Mock, patch
from app.routes.pipeline import generate_block_fast_telea_preview, InpaintPreviewRequest


def test_fast_preview_endpoint(tmp_path):
    source_img_path = tmp_path / "source.png"
    img = np.ones((400, 400, 3), dtype=np.uint8) * 200
    cv2.imwrite(str(source_img_path), img)

    mask = np.ones((100, 100), dtype=np.uint8) * 255
    _, encoded = cv2.imencode(".png", mask)
    mask_b64 = f"data:image/png;base64,{base64.b64encode(encoded).decode('utf-8')}"

    mock_block = Mock()
    mock_block.id = "block_fast_1"
    mock_block.x = 50
    mock_block.y = 50
    mock_block.width = 100
    mock_block.height = 100
    mock_block.page = Mock()
    mock_block.page.id = "page_fast_1"
    mock_block.page.source_image_path = str(source_img_path)

    mock_db = Mock()
    mock_db.query().filter().first.return_value = mock_block

    request = InpaintPreviewRequest(mask_base64=mask_b64)
    response = generate_block_fast_telea_preview("block_fast_1", request, mock_db)

    assert response["status"] == "success"
    assert "preview_url" in response
    assert response["preview_url"].startswith("data:image/jpeg;base64,")
