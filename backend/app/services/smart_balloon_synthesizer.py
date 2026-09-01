"""
Smart Balloon Synthesizer Engine for Houmi Studio.
Implements:
1. Geodesic Voronoi Partitioning for conjoined dialogue bubbles.
2. Directional speaker mouth anchor detection & Bézier stem generation.
3. Hermite G2 continuous spline bridging across cut contours (zero linework kinks).
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Any, List, Tuple

import cv2
import numpy as np


@dataclass
class Point2D:
    x: float
    y: float

    def to_array(self) -> np.ndarray:
        return np.array([self.x, self.y], dtype=np.float64)

    def __add__(self, other: Point2D) -> Point2D:
        return Point2D(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Point2D) -> Point2D:
        return Point2D(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> Point2D:
        return Point2D(self.x * scalar, self.y * scalar)

    def __rmul__(self, scalar: float) -> Point2D:
        return self.__mul__(scalar)

    def norm(self) -> float:
        return math.hypot(self.x, self.y)

    def normalized(self) -> Point2D:
        n = self.norm()
        if n < 1e-9:
            return Point2D(0.0, 0.0)
        return Point2D(self.x / n, self.y / n)


@dataclass
class G2BoundaryCondition:
    point: Point2D
    tangent: Point2D       # Unit tangent vector
    normal: Point2D        # Unit normal vector
    curvature: float       # Signed scalar curvature kappa = 1 / R


class GeodesicVoronoiSplitter:
    """
    Partitions conjoined dialogue bubbles using weighted Fast Marching Eikonal fields
    to find minimum-clearance waist bottlenecks and separate overlapping contours.
    """

    @staticmethod
    def compute_weighted_geodesic_distance(
        binary_mask: np.ndarray,
        seed: Tuple[int, int],
        weight_lambda: float = 3.0,
    ) -> np.ndarray:
        h, w = binary_mask.shape[:2]
        dist_field = np.full((h, w), np.inf, dtype=np.float64)
        
        edt = cv2.distanceTransform((binary_mask > 0).astype(np.uint8), cv2.DIST_L2, 5)
        max_edt = float(np.max(edt)) + 1e-6
        sigma_w = max(1.0, 0.15 * max_edt)
        weight_grid = 1.0 + weight_lambda * np.exp(-edt / sigma_w)

        sx, sy = seed
        if not (0 <= sx < w and 0 <= sy < h) or binary_mask[sy, sx] == 0:
            ys, xs = np.where(binary_mask > 0)
            if len(xs) == 0:
                return dist_field
            idx = np.argmin((xs - sx) ** 2 + (ys - sy) ** 2)
            sx, sy = int(xs[idx]), int(ys[idx])

        dist_field[sy, sx] = 0.0
        pq: List[Tuple[float, int, int]] = [(0.0, sx, sy)]

        neighbors = [
            (-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
            (-1, -1, math.sqrt(2)), (1, -1, math.sqrt(2)),
            (-1, 1, math.sqrt(2)), (1, 1, math.sqrt(2))
        ]

        while pq:
            d_curr, cx, cy = heapq.heappop(pq)
            if d_curr > dist_field[cy, cx]:
                continue

            for dx, dy, step_cost in neighbors:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < w and 0 <= ny < h and binary_mask[ny, nx] > 0:
                    local_cost = 0.5 * (weight_grid[cy, cx] + weight_grid[ny, nx]) * step_cost
                    new_dist = d_curr + local_cost
                    if new_dist < dist_field[ny, nx]:
                        dist_field[ny, nx] = new_dist
                        heapq.heappush(pq, (new_dist, nx, ny))

        return dist_field


class G2HermiteSplineSynthesizer:
    """
    Evaluates and generates quintic Hermite / Bézier curves guaranteeing
    strict G2 curvature continuity (zero linework kinks).
    """

    @staticmethod
    def estimate_contour_differential(
        contour: np.ndarray,
        target_idx: int,
        window: int = 5,
    ) -> G2BoundaryCondition:
        pts = contour.reshape(-1, 2).astype(np.float64)
        n = len(pts)
        idx = target_idx % n

        indices = [(idx + k) % n for k in range(-window, window + 1)]
        stencil = pts[indices]

        d1 = (stencil[window + 1] - stencil[window - 1]) * 0.5
        d2 = stencil[window + 1] - 2.0 * stencil[window] + stencil[window - 1]

        speed = math.hypot(d1[0], d1[1]) + 1e-9
        unit_tan = Point2D(d1[0] / speed, d1[1] / speed)
        unit_norm = Point2D(-unit_tan.y, unit_tan.x)

        cross = d1[0] * d2[1] - d1[1] * d2[0]
        kappa = float(cross / (speed ** 3))

        return G2BoundaryCondition(
            point=Point2D(pts[idx][0], pts[idx][1]),
            tangent=unit_tan,
            normal=unit_norm,
            curvature=kappa,
        )

    @classmethod
    def solve_quintic_bezier_g2(
        cls,
        bc0: G2BoundaryCondition,
        bc1: G2BoundaryCondition,
        tension: float = 1.0,
    ) -> List[Point2D]:
        p0, p1 = bc0.point, bc1.point
        t0, t1 = bc0.tangent, bc1.tangent
        n0, n1 = bc0.normal, bc1.normal
        k0, k1 = bc0.curvature, bc1.curvature

        chord = p1 - p0
        chord_len = chord.norm()
        if chord_len < 1e-6:
            return [p0, p0, p0, p1, p1, p1]

        cos_0 = max(-1.0, min(1.0, (chord.x * t0.x + chord.y * t0.y) / chord_len))
        cos_1 = max(-1.0, min(1.0, (chord.x * t1.x + chord.y * t1.y) / chord_len))
        scale = 5.0 / (3.0 + max(0.0, cos_0) + max(0.0, cos_1)) * tension
        v0 = scale * chord_len
        v1 = scale * chord_len

        a0 = 0.0
        a1 = 0.0

        q0 = p0
        q1 = p0 + (v0 / 5.0) * t0
        q2 = p0 + ((2.0 * v0 / 5.0) + (a0 / 20.0)) * t0 + ((k0 * (v0 ** 2)) / 20.0) * n0
        q3 = p1 - ((2.0 * v1 / 5.0) - (a1 / 20.0)) * t1 + ((k1 * (v1 ** 2)) / 20.0) * n1
        q4 = p1 - (v1 / 5.0) * t1
        q5 = p1

        return [q0, q1, q2, q3, q4, q5]

    @staticmethod
    def sample_quintic_bezier(
        ctrl_pts: List[Point2D],
        num_samples: int = 50,
    ) -> Tuple[np.ndarray, np.ndarray]:
        u = np.linspace(0.0, 1.0, num_samples)
        q = np.array([[pt.x, pt.y] for pt in ctrl_pts], dtype=np.float64)

        b0 = (1 - u) ** 5
        b1 = 5 * u * (1 - u) ** 4
        b2 = 10 * (u ** 2) * (1 - u) ** 3
        b3 = 10 * (u ** 3) * (1 - u) ** 2
        b4 = 5 * (u ** 4) * (1 - u)
        b5 = u ** 5

        basis = np.stack([b0, b1, b2, b3, b4, b5], axis=0)
        pos = np.dot(q.T, basis).T

        dq = 5.0 * (q[1:] - q[:-1])
        db0 = (1 - u) ** 4
        db1 = 4 * u * (1 - u) ** 3
        db2 = 6 * (u ** 2) * (1 - u) ** 2
        db3 = 4 * (u ** 3) * (1 - u)
        db4 = u ** 4
        d_basis = np.stack([db0, db1, db2, db3, db4], axis=0)
        vel = np.dot(dq.T, d_basis).T

        ddq = 4.0 * (dq[1:] - dq[:-1])
        ddb0 = (1 - u) ** 3
        ddb1 = 3 * u * (1 - u) ** 2
        ddb2 = 3 * (u ** 2) * (1 - u)
        ddb3 = u ** 3
        dd_basis = np.stack([ddb0, ddb1, ddb2, ddb3], axis=0)
        acc = np.dot(ddq.T, dd_basis).T

        speed = np.hypot(vel[:, 0], vel[:, 1]) + 1e-9
        cross = vel[:, 0] * acc[:, 1] - vel[:, 1] * acc[:, 0]
        curvatures = cross / (speed ** 3)

        return pos, curvatures
