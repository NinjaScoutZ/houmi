import cv2
import numpy as np
import pytest

from app.services.mask.border_clamper import clamp_mask_to_balloon_interior


def test_clamp_mask_light_balloon_protects_dark_border():
    """Verify that on standard white dialogue balloons, dark border lines are clamped properly."""
    h, w = 100, 100
    # White balloon interior (gray = 255) with 2px black border (gray = 0) at x=0..99, y=0..99
    img = np.ones((h, w, 3), dtype=np.uint8) * 255
    cv2.rectangle(img, (0, 0), (w - 1, h - 1), (0, 0, 0), 2)

    # Initial text mask in the center
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.rectangle(mask, (20, 20), (80, 80), 255, -1)

    # Dilate mask so it overlaps the border
    leaked_mask = mask.copy()
    cv2.rectangle(leaked_mask, (0, 0), (99, 99), 255, 1)

    clamped = clamp_mask_to_balloon_interior(leaked_mask, img, margin_px=2)

    # Central text mask must be preserved
    assert clamped[50, 50] == 255
    # Outer border line at x=0, y=0 must be clamped to 0
    assert clamped[0, 0] == 0
    assert clamped[1, 1] == 0


def test_clamp_mask_dark_balloon_does_not_erase_text():
    """Verify that on dark spiky/screaming balloons, dark background is NOT treated as a border line."""
    h, w = 120, 120
    # Dark grey spiky balloon interior (gray = 45)
    img = np.ones((h, w, 3), dtype=np.uint8) * 45

    # Text mask inside the balloon
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.rectangle(mask, (25, 25), (95, 95), 255, -1)

    clamped = clamp_mask_to_balloon_interior(mask, img, margin_px=2)

    # On dark backgrounds, text mask MUST NOT be erased by distance transform
    assert clamped is not None
    assert np.count_nonzero(clamped) == np.count_nonzero(mask)
    assert np.array_equal(clamped, mask)
