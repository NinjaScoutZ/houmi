import pytest
import numpy as np
import cv2
from app.services.smart_balloon_synthesizer import (
    Point2D,
    G2BoundaryCondition,
    G2HermiteSplineSynthesizer,
    GeodesicVoronoiSplitter
)

def test_quintic_bezier_g2_curvature_continuity():
    """Verify that solved quintic Bézier matches G2 boundary conditions analytically."""
    bc0 = G2BoundaryCondition(
        point=Point2D(0.0, 0.0),
        tangent=Point2D(1.0, 0.0),
        normal=Point2D(0.0, 1.0),
        curvature=0.05
    )
    bc1 = G2BoundaryCondition(
        point=Point2D(100.0, 50.0),
        tangent=Point2D(0.0, 1.0),
        normal=Point2D(-1.0, 0.0),
        curvature=0.02
    )

    ctrl_pts = G2HermiteSplineSynthesizer.solve_quintic_bezier_g2(bc0, bc1)
    assert len(ctrl_pts) == 6

    pos, curvatures = G2HermiteSplineSynthesizer.sample_quintic_bezier(ctrl_pts, 50)
    
    # Assert curvature continuity at ends
    assert abs(curvatures[0] - bc0.curvature) < 1e-4
    assert abs(curvatures[-1] - bc1.curvature) < 1e-4

def test_geodesic_distance_field():
    """Verify weighted geodesic distance field computation."""
    mask = np.zeros((100, 100), dtype=np.uint8)
    cv2.circle(mask, (50, 50), 30, 255, -1)
    
    dist_field = GeodesicVoronoiSplitter.compute_weighted_geodesic_distance(mask, (50, 50))
    assert dist_field[50, 50] == 0.0
    assert np.all(dist_field[mask == 0] == np.inf)
    assert dist_field[50, 70] > 0.0
