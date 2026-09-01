import pytest
import numpy as np
import cv2
from app.services.mask.screentone_inpainter import (
    AdaptiveScreentoneInpainter,
    ScreentoneParameters
)

def test_screentone_parameter_extraction_synthetic():
    """Verify that a synthetic 60 LPI dot matrix at 45 degrees is accurately detected."""
    dpi = 600
    inpainter = AdaptiveScreentoneInpainter(dpi=dpi)
    
    h, w = 256, 256
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    
    # 60 LPI -> period = 10px -> f0 = 0.10 cycles/px
    target_lpi = 60.0
    f0 = target_lpi / dpi
    theta_rad = np.radians(45.0)
    
    u_rot = x * np.cos(theta_rad) + y * np.sin(theta_rad)
    v_rot = -x * np.sin(theta_rad) + y * np.cos(theta_rad)
    
    # Generate binary dot lattice
    xi = f0 * u_rot - np.floor(f0 * u_rot)
    eta = f0 * v_rot - np.floor(f0 * v_rot)
    dist_center = np.sqrt((xi - 0.5)**2 + (eta - 0.5)**2)
    dot_pattern = np.where(dist_center < 0.25, np.uint8(0), np.uint8(255))
    
    params = inpainter.extract_screentone_parameters(dot_pattern)
    assert params.is_screentone is True
    assert abs(params.lpi - target_lpi) < 3.0  # within 3 LPI tolerance
    assert abs(params.theta_deg - 45.0) < 3.0  # within 3 degrees tolerance

def test_screentone_inpainting_preserves_dimensions():
    """Verify end-to-end inpaint function with a circular text mask."""
    inpainter = AdaptiveScreentoneInpainter(dpi=600)
    img = np.full((128, 128), 200, dtype=np.uint8)
    mask = np.zeros((128, 128), dtype=np.uint8)
    cv2.circle(mask, (64, 64), 20, 255, -1)
    
    result = inpainter.inpaint(img, mask)
    assert result.shape == img.shape
    assert result.dtype == np.uint8
