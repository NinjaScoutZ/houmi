import cv2
import numpy as np
import pytest
from app.services.smart_balloon import extract_balloon_text_style, rgb_to_hex
from app.services.inpainter import inpaint_subregion_patch

def test_rgb_to_hex():
    assert rgb_to_hex(255, 255, 255) == '#ffffff'
    assert rgb_to_hex(0, 0, 0) == '#000000'
    assert rgb_to_hex(255, 0, 0) == '#ff0000'
    assert rgb_to_hex(0, 128, 255) == '#0080ff'

def test_extract_balloon_text_style():
    # Synthetic speech balloon: white background, black text
    img = np.ones((200, 200, 3), dtype=np.uint8) * 255
    cv2.putText(img, 'HELLO', (40, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 0), 3)

    style = extract_balloon_text_style(img, (20, 20, 160, 160))
    assert 'text_color' in style
    assert 'bg_color' in style
    assert style['bg_color'] == '#ffffff'
    assert style['text_color'] == '#000000'

def test_inpaint_subregion_patch():
    # Synthetic image with black text on white background
    img = np.ones((300, 300, 3), dtype=np.uint8) * 255
    cv2.circle(img, (150, 150), 30, (0, 0, 0), -1)

    # Mask over the black circle
    mask = np.zeros((300, 300), dtype=np.uint8)
    cv2.circle(mask, (150, 150), 35, 255, -1)

    patched_img, patch_bounds = inpaint_subregion_patch(img, mask, padding=32)
    assert patched_img is not None
    assert patched_img.shape == (300, 300, 3)
    x0, y0, x1, y1 = patch_bounds
    assert x0 < 150 < x1
    assert y0 < 150 < y1
    # Center pixel should no longer be pitch black
    center_val = np.mean(patched_img[150, 150])
    assert center_val > 100
