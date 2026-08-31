"""Pytest suite for Next-Gen Mask Engine Architecture (Two-Zone Classifier, Precision Monochrome Engine, Glowing Text, Border Clamping)."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.services.mask import (
    MASK_MODE_COLOR_OR_COMPLEX,
    MASK_MODE_MONOCHROME_FLAT,
    classify_text_mask_mode,
    clamp_mask_to_balloon_interior,
    generate_monochrome_flat_text_mask,
)
from app.services.text_mask import generate_routed_text_mask


def test_two_zone_classifier_white_balloon_with_colorful_outside():
    """Verify Zone A analysis correctly ignores high chroma outside the dialogue balloon."""
    # Create 200x200 crop: White balloon in center, bright red background outside
    img = np.zeros((200, 200, 3), dtype=np.uint8)
    img[:, :] = [0, 0, 255]  # Bright red exterior (Zone B)

    # Draw white oval balloon inside (Zone A)
    cv2.ellipse(img, (100, 100), (70, 70), 0, 0, 360, (255, 255, 255), -1)
    # Draw black text inside balloon
    cv2.putText(img, "TEST", (60, 110), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)

    mode, diagnostics = classify_text_mask_mode(img)
    assert mode == MASK_MODE_MONOCHROME_FLAT
    assert diagnostics["interior_chroma"] <= 15.0
    assert diagnostics["has_enclosure"] is True


def test_two_zone_classifier_full_color_artwork():
    """Verify full-color artwork or SFX with textured interior routes to color_or_complex."""
    # Create textured colorful crop
    img = np.zeros((200, 200, 3), dtype=np.uint8)
    # Gradient of magenta and cyan
    for y in range(200):
        for x in range(200):
            img[y, x] = [x, 50, y]

    mode, diagnostics = classify_text_mask_mode(img)
    assert mode == MASK_MODE_COLOR_OR_COMPLEX
    assert diagnostics["interior_chroma"] > 15.0


def test_1px_boundary_disconnection_glyph():
    """Verify that a letter touching the 1px crop border is disconnected and not discarded with the frame."""
    # Create 100x100 white crop with black outer border
    img = np.full((100, 100, 3), 255, dtype=np.uint8)
    img[0, :] = 0
    img[-1, :] = 0
    img[:, 0] = 0
    img[:, -1] = 0

    # Draw a black letter starting at x=0 (touching the border)
    img[30:70, 0:25] = 0
    # Draw a regular centered text letter
    img[30:70, 45:70] = 0

    mask = generate_monochrome_flat_text_mask(img, dilation_kernel=1, remove_outer_contours=True)
    assert mask is not None
    # Both letters (including the one touching x=0) must be captured in the mask
    assert np.count_nonzero(mask[35:65, 5:20]) > 0
    assert np.count_nonzero(mask[35:65, 50:65]) > 0


def test_primary_balloon_barrier_dark_corners():
    """Verify that a white balloon on dark corners does not leak mask into the dark background corners."""
    # Create 300x150 crop with black corners and large white oval balloon
    img = np.zeros((150, 300, 3), dtype=np.uint8)
    cv2.ellipse(img, (150, 75), (140, 70), 0, 0, 360, (255, 255, 255), -1)

    # Black text inside balloon
    cv2.putText(img, "HELLO", (60, 85), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 3)

    mask = generate_monochrome_flat_text_mask(img, dilation_kernel=2, remove_outer_contours=True)
    assert mask is not None

    # Text area must be masked
    assert np.count_nonzero(mask[60:90, 70:200]) > 0
    # Corners (outside the balloon) MUST be 0 (no leakage into black corners)
    assert np.count_nonzero(mask[0:15, 0:15]) == 0
    assert np.count_nonzero(mask[135:150, 0:15]) == 0
    assert np.count_nonzero(mask[0:15, 285:300]) == 0
    assert np.count_nonzero(mask[135:150, 285:300]) == 0


def test_glowing_text_on_dark_background_absorption():
    """Verify that light text with glowing outer halo on dark background has halo absorbed without outer frame leakage."""
    # Create dark background image (gray ~50)
    img = np.full((120, 250, 3), 50, dtype=np.uint8)
    # White border around box
    img[2, :] = 255
    img[-3, :] = 255
    img[:, 2] = 255
    img[:, -3] = 255

    # Core white text with diffuse halo
    cv2.putText(img, "GLOWING", (30, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 4)
    # Add diffuse glow around text
    blurred = cv2.GaussianBlur(img, (15, 15), 0)
    img = np.maximum(img, (blurred * 0.6).astype(np.uint8))

    mask = generate_monochrome_flat_text_mask(img, dilation_kernel=2, remove_outer_contours=True)
    assert mask is not None

    # Text and glow area must be covered
    assert np.count_nonzero(mask[40:85, 25:220]) > 0
    # Outer frame line must remain unmasked (preserved for inpainting)
    assert np.count_nonzero(mask[0:2, :]) == 0
    assert np.count_nonzero(mask[-2:, :]) == 0


def test_distance_aware_border_clamping():
    """Verify clamp_mask_to_balloon_interior prevents mask from eroding the balloon contour border."""
    img = np.full((100, 100, 3), 255, dtype=np.uint8)
    # Draw thick black balloon stroke
    cv2.rectangle(img, (10, 10), (90, 90), (0, 0, 0), 4)

    # An oversized mask that crosses into the black border
    oversized_mask = np.zeros((100, 100), dtype=np.uint8)
    oversized_mask[8:92, 8:92] = 255

    clamped = clamp_mask_to_balloon_interior(oversized_mask, img, margin_px=2)
    # Clamped mask must not touch the black border at (10, 10)
    assert clamped[10, 10] == 0
    assert clamped[10, 50] == 0
    # Interior must remain preserved
    assert clamped[50, 50] == 255
