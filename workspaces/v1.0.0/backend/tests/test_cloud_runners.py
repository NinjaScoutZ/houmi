"""
Unit tests for DOBKLE Cloud OCR & Inpainting Service Runners
"""

import os
import numpy as np
from PIL import Image
import cv2
import pytest
from unittest.mock import patch

from app.services.cloud_dobkle_service import (
    decode_base64_image,
    decode_base64_pil,
    encode_image_base64,
    pack_crops_to_pdf,
    run_cloud_clean,
    run_cloud_ocr,
    get_ocr_semaphore,
    get_clean_semaphore,
)


def test_encode_decode_base64():
    """Verify base64 image encoding and decoding round-trip across formats."""
    orig_img = np.zeros((64, 64, 3), dtype=np.uint8)
    orig_img[:, :] = (100, 150, 200)

    # WebP encoding
    webp_b64 = encode_image_base64(orig_img, format_ext="webp", quality=95)
    assert webp_b64.startswith("data:image/webp;base64,")
    decoded_webp = decode_base64_image(webp_b64)
    assert decoded_webp.shape == (64, 64, 3)

    # PNG encoding
    png_b64 = encode_image_base64(orig_img, format_ext="png")
    assert png_b64.startswith("data:image/png;base64,")
    decoded_png = decode_base64_image(png_b64)
    assert np.array_equal(decoded_png, orig_img)

    # PIL decoding
    pil_img = decode_base64_pil(png_b64)
    assert pil_img.size == (64, 64)


def test_pack_crops_to_pdf():
    """Verify multi-crop PDF collage generator."""
    crops = []
    for i in range(5):
        pil_crop = Image.new("RGB", (80 + i * 10, 60 + i * 10), color=(240, 240, 240))
        crops.append((f"block_{i+1}", pil_crop))

    pdf_path, id_map = pack_crops_to_pdf(crops, project_label="TEST_SUITE")
    try:
        assert os.path.exists(pdf_path)
        assert os.path.getsize(pdf_path) > 1000  # Valid PDF size
        assert len(id_map) == 5
        for idx in range(1, 6):
            expected_stable = f"BOX_{idx:03d}_block_{idx}"
            assert expected_stable in id_map
            assert id_map[expected_stable] == f"block_{idx}"
    finally:
        if os.path.exists(pdf_path):
            os.remove(pdf_path)


def test_run_cloud_clean_telea_and_zero_mask():
    """Verify clean runner with telea inpainting and zero-mask fast path."""
    img = np.full((100, 100, 3), 180, dtype=np.uint8)
    mask = np.zeros((100, 100), dtype=np.uint8)

    # 1. Zero mask -> returns identical copy instantly
    cleaned, timing = run_cloud_clean(img, mask, engine="telea")
    assert np.array_equal(cleaned, img)
    assert timing == 0.0

    # 2. Non-zero mask with dilation
    mask[40:60, 40:60] = 255
    cleaned_active, timing_active = run_cloud_clean(img, mask, engine="telea", dilation=2)
    assert cleaned_active.shape == (100, 100, 3)
    assert timing_active >= 0.0


def test_run_cloud_ocr_runner_full_and_text_only():
    """Verify OCR runner with full styling and text_only modes."""
    crops = [
        ("cid_001", Image.new("RGB", (70, 70), (255, 255, 255))),
        ("cid_002", Image.new("RGB", (80, 80), (255, 255, 255))),
    ]

    mock_response = """[
        {"box_id": "BOX_001_cid001", "text": "First bubble", "balloon_type": "bubble", "color_hex": "#000000"},
        {"box_id": "BOX_002_cid002", "text": "Second bubble", "balloon_type": "shout", "color_hex": "#FF0000", "bold": true}
    ]"""

    with patch("app.services.cloud_dobkle_service._run_gemini_command") as mock_agy:
        mock_agy.return_value = (mock_response, True)

        # Full depth
        res_full = run_cloud_ocr(crops, source_lang="ja", ocr_depth="full")
        assert res_full["ok"] is True
        assert res_full["total"] == 2
        assert res_full["mapped"] == 2
        assert res_full["results"][0]["text"] == "First bubble"
        assert res_full["results"][1]["text"] == "Second bubble"
        assert res_full["results"][1]["bold"] is True

        # Empty crops fast return
        res_empty = run_cloud_ocr([])
        assert res_empty["ok"] is True
        assert res_empty["total"] == 0


def test_concurrency_semaphores():
    """Verify semaphore initialization and limit values."""
    ocr_sem = get_ocr_semaphore()
    clean_sem = get_clean_semaphore()
    assert ocr_sem is not None
    assert clean_sem is not None
