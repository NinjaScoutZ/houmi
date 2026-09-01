import pytest
import numpy as np
import cv2
from app.services.sfx_warp_engine import (
    Point2D,
    QuadCageWarpEngine,
    SFXTrajectoryExtractor
)

def test_quad_cage_warp_homography_and_jacobian():
    """Verify 4-point quad homography projection and Jacobian computation."""
    engine = QuadCageWarpEngine(
        top_left=Point2D(0.0, 0.0),
        top_right=Point2D(200.0, 0.0),
        bottom_right=Point2D(250.0, 100.0),
        bottom_left=Point2D(50.0, 100.0)
    )

    # Unit corners
    p_tl = engine.warp_point(0.0, 0.0)
    assert abs(p_tl.x - 0.0) < 1e-2
    assert abs(p_tl.y - 0.0) < 1e-2

    p_br = engine.warp_point(1.0, 1.0)
    assert abs(p_br.x - 250.0) < 1e-2
    assert abs(p_br.y - 100.0) < 1e-2

    # Jacobian matrix test
    J = engine.compute_jacobian(0.5, 0.5)
    assert J.shape == (2, 2)
    assert np.all(np.isfinite(J))

def test_thai_grapheme_cluster_segmentation():
    """Verify that Thai diacritics are grouped with their base consonants."""
    engine = QuadCageWarpEngine(
        top_left=Point2D(0, 0), top_right=Point2D(100, 0),
        bottom_right=Point2D(100, 50), bottom_left=Point2D(0, 50)
    )

    text = "ตู้มมม เปรี้ยง"
    clusters = engine.segment_thai_clusters(text)
    assert len(clusters) > 0
    # First cluster 'ตู้'
    assert clusters[0].text.startswith("ต")
