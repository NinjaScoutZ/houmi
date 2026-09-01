import pytest
import numpy as np
import cv2
from app.services.smart_balloon_optimizer import (
    MaximalInscribedRectangleOptimizer,
    InscribedRectangle
)

def test_maximal_inscribed_rectangle_circle():
    # Generate circular contour (R = 50, center = (100, 100))
    theta = np.linspace(0, 2 * np.pi, 100, endpoint=False)
    pts = np.stack([100 + 50 * np.cos(theta), 100 + 50 * np.sin(theta)], axis=1)
    contour = pts.reshape(-1, 1, 2).astype(np.int32)

    res = MaximalInscribedRectangleOptimizer.find_maximal_inscribed_rectangle(
        contour, target_aspect_ratio=1.0, safe_margin_ratio=0.05
    )
    assert res is not None
    assert isinstance(res, InscribedRectangle)
    assert res.width > 40.0
    assert res.height > 40.0
    assert abs(res.center_x - 100.0) < 5.0
    assert abs(res.center_y - 100.0) < 5.0

def test_maximal_inscribed_rectangle_ellipse():
    # Generate ellipse contour (a = 80, b = 40)
    theta = np.linspace(0, 2 * np.pi, 100, endpoint=False)
    pts = np.stack([200 + 80 * np.cos(theta), 200 + 40 * np.sin(theta)], axis=1)
    contour = pts.reshape(-1, 1, 2).astype(np.int32)

    res = MaximalInscribedRectangleOptimizer.find_maximal_inscribed_rectangle(
        contour, target_aspect_ratio=2.0, safe_margin_ratio=0.05
    )
    assert res is not None
    assert res.width > res.height
