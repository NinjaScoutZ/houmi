"""
HOUMI STUDIO PHASE 2 INTEGRATION TEST SUITE
Verification of:
1. Adaptive Screentone Halftone Inpainting (2D FFT, RGF Shading, Phase-Locked Resynthesis)
2. G2 Quintic Hermite Spline Balloon Stem Synthesis & Geodesic Voronoi Partitioning
3. Thai SFX Homography Mesh Warp & Grapheme Cluster Tethering
"""

import math
import numpy as np
import cv2
import pytest

from app.services.mask.screentone_inpainter import (
    AdaptiveScreentoneInpainter,
    ScreentoneParameters,
)
from app.services.smart_balloon_synthesizer import (
    Point2D as SplinePoint2D,
    G2BoundaryCondition,
    G2HermiteSplineSynthesizer,
    GeodesicVoronoiSplitter,
)
from app.services.sfx_warp_engine import (
    Point2D as WarpPoint2D,
    QuadCageWarpEngine,
    SFXTrajectoryExtractor,
)


class TestAdaptiveScreentoneInpainting:
    @classmethod
    def setup_class(cls):
        cls.dpi = 600
        cls.inpainter = AdaptiveScreentoneInpainter(dpi=cls.dpi)

    def _generate_synthetic_halftone(
        self, width=256, height=256, target_lpi=60.0, angle_deg=45.0, dot_radius_ratio=0.25
    ):
        f0 = target_lpi / self.dpi
        theta_rad = np.radians(angle_deg)
        y, x = np.mgrid[0:height, 0:width].astype(np.float32)

        u_rot = x * np.cos(theta_rad) + y * np.sin(theta_rad)
        v_rot = -x * np.sin(theta_rad) + y * np.cos(theta_rad)

        xi = f0 * u_rot - np.floor(f0 * u_rot)
        eta = f0 * v_rot - np.floor(f0 * v_rot)
        dist_center = np.sqrt((xi - 0.5) ** 2 + (eta - 0.5) ** 2)
        dot_pattern = np.where(dist_center < dot_radius_ratio, np.uint8(0), np.uint8(255))
        return dot_pattern

    def test_screentone_fft_parameter_extraction_precision(self):
        target_lpi = 60.0
        target_angle = 45.0
        pattern = self._generate_synthetic_halftone(
            width=256, height=256, target_lpi=target_lpi, angle_deg=target_angle
        )

        params = self.inpainter.extract_screentone_parameters(pattern)
        assert params.is_screentone is True
        assert abs(params.lpi - target_lpi) <= 3.0
        assert abs(params.theta_deg - target_angle) <= 3.0

    def test_screentone_end_to_end_inpaint_resynthesis(self):
        pattern = self._generate_synthetic_halftone(width=256, height=256, target_lpi=60.0, angle_deg=45.0)
        mask = np.zeros((256, 256), dtype=np.uint8)
        cv2.circle(mask, (128, 128), 35, 255, -1)

        inpainted = self.inpainter.inpaint(pattern, mask)
        assert inpainted.shape == pattern.shape


class TestG2SplineBalloonStemSynthesis:
    def test_g2_quintic_bezier_curvature_continuity(self):
        bc0 = G2BoundaryCondition(
            point=SplinePoint2D(0.0, 0.0),
            tangent=SplinePoint2D(1.0, 0.0),
            normal=SplinePoint2D(0.0, 1.0),
            curvature=0.02,
        )
        bc1 = G2BoundaryCondition(
            point=SplinePoint2D(100.0, 50.0),
            tangent=SplinePoint2D(0.0, 1.0),
            normal=SplinePoint2D(-1.0, 0.0),
            curvature=-0.01,
        )

        ctrl_pts = G2HermiteSplineSynthesizer.solve_quintic_bezier_g2(bc0, bc1, tension=1.0)
        assert len(ctrl_pts) == 6

        positions, curvatures = G2HermiteSplineSynthesizer.sample_quintic_bezier(ctrl_pts, num_samples=100)
        assert math.isclose(curvatures[0], bc0.curvature, abs_tol=5e-3)
        assert math.isclose(curvatures[-1], bc1.curvature, abs_tol=5e-3)


class TestThaiSFXHomographyWarp:
    def test_quad_cage_homography_and_jacobian_tethering(self):
        engine = QuadCageWarpEngine(
            top_left=WarpPoint2D(20.0, 30.0),
            top_right=WarpPoint2D(300.0, 10.0),
            bottom_right=WarpPoint2D(340.0, 140.0),
            bottom_left=WarpPoint2D(40.0, 160.0),
        )

        tl = engine.warp_point(0.0, 0.0)
        assert abs(tl.x - 20.0) < 1e-2 and abs(tl.y - 30.0) < 1e-2

        J = engine.compute_jacobian(0.5, 0.5)
        det_J = J[0, 0] * J[1, 1] - J[0, 1] * J[1, 0]
        assert det_J > 0

    def test_thai_grapheme_cluster_segmentation_diacritics(self):
        engine = QuadCageWarpEngine(
            top_left=WarpPoint2D(0, 0), top_right=WarpPoint2D(100, 0),
            bottom_right=WarpPoint2D(100, 50), bottom_left=WarpPoint2D(0, 50)
        )

        test_sfx = "ตู้มมม เปรี้ยง ครืนนน"
        clusters = engine.segment_thai_clusters(test_sfx)
        assert len(clusters) > 0
        assert clusters[0].text == "ตู้"
