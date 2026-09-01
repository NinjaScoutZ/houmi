"""
Houmi Studio - Thai SFX Trajectory & 4-Point Mesh Warp Engine
Implements Medial Axis Transform trajectory flow extraction and Thai Grapheme Cluster Jacobian tethering.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import List, Tuple, Optional

import cv2
import numpy as np


@dataclass
class Point2D:
    x: float
    y: float


@dataclass
class TrajectoryPoint:
    x: float
    y: float
    tangent_x: float
    tangent_y: float
    normal_x: float
    normal_y: float
    half_width: float
    arc_length: float


@dataclass
class ThaiGraphemeCluster:
    text: string
    base_consonant: str
    relative_u: float
    span_u: float


class SFXTrajectoryExtractor:
    """
    Extracts smooth flow trajectory and thickness profile from binary SFX mask using Distance Transform.
    """

    def extract_trajectory_from_mask(self, binary_mask: np.ndarray) -> List[TrajectoryPoint]:
        if binary_mask is None or np.count_nonzero(binary_mask) < 20:
            return []

        dist = cv2.distanceTransform((binary_mask > 0).astype(np.uint8), cv2.DIST_L2, 5)
        
        # Skeleton thinning via morphological open/erode
        skel = np.zeros_like(binary_mask)
        element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
        img = binary_mask.copy()

        while True:
            eroded = cv2.erode(img, element)
            temp = cv2.dilate(eroded, element)
            temp = cv2.subtract(img, temp)
            skel = cv2.bitwise_or(skel, temp)
            img = eroded.copy()
            if cv2.countNonZero(img) == 0:
                break

        pts = np.argwhere(skel > 0)
        if len(pts) < 4:
            pts = np.argwhere(binary_mask > 0)
            if len(pts) < 4:
                return []

        # Sort points by X axis (left to right flow)
        sorted_indices = np.argsort(pts[:, 1])
        pts_sorted = pts[sorted_indices]

        stride = max(1, len(pts_sorted) // 20)
        sampled = pts_sorted[::stride]

        trajectory: List[TrajectoryPoint] = []
        total_len = 0.0

        for i in range(len(sampled)):
            py, px = float(sampled[i][0]), float(sampled[i][1])
            if i < len(sampled) - 1:
                next_py, next_px = float(sampled[i+1][0]), float(sampled[i+1][1])
                dx, dy = next_px - px, next_py - py
            elif i > 0:
                prev_py, prev_px = float(sampled[i-1][0]), float(sampled[i-1][1])
                dx, dy = px - prev_px, py - prev_py
            else:
                dx, dy = 1.0, 0.0

            norm = math.hypot(dx, dy) + 1e-6
            tx, ty = dx / norm, dy / norm
            nx, ny = -ty, tx

            hw = float(dist[int(np.clip(py, 0, dist.shape[0]-1)), int(np.clip(px, 0, dist.shape[1]-1))])
            trajectory.append(TrajectoryPoint(px, py, tx, ty, nx, ny, hw, total_len))
            total_len += norm

        return trajectory


class QuadCageWarpEngine:
    """
    4-Point Quadrilateral Homography with Thai Grapheme Cluster Tethering.
    """

    def __init__(self, top_left: Point2D, top_right: Point2D, bottom_right: Point2D, bottom_left: Point2D):
        self.quad = [top_left, top_right, bottom_right, bottom_left]
        self.H = self._compute_homography()

    def _compute_homography(self) -> np.ndarray:
        src = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32)
        dst = np.array([[p.x, p.y] for p in self.quad], dtype=np.float32)
        H, _ = cv2.findHomography(src, dst)
        return H if H is not None else np.eye(3, dtype=np.float32)

    def warp_point(self, u: float, v: float) -> Point2D:
        pt = np.array([u, v, 1.0], dtype=np.float32)
        res = self.H @ pt
        w = res[2] if abs(res[2]) > 1e-6 else 1e-6
        return Point2D(float(res[0] / w), float(res[1] / w))

    def compute_jacobian(self, u: float, v: float) -> np.ndarray:
        H = self.H
        denom = H[2, 0] * u + H[2, 1] * v + H[2, 2]
        denom2 = denom * denom
        if abs(denom2) < 1e-8:
            return np.eye(2, dtype=np.float32)

        num_x = H[0, 0] * u + H[0, 1] * v + H[0, 2]
        num_y = H[1, 0] * u + H[1, 1] * v + H[1, 2]

        j11 = (H[0, 0] * denom - num_x * H[2, 0]) / denom2
        j12 = (H[0, 1] * denom - num_x * H[2, 1]) / denom2
        j21 = (H[1, 0] * denom - num_y * H[2, 0]) / denom2
        j22 = (H[1, 1] * denom - num_y * H[2, 1]) / denom2

        return np.array([[j11, j12], [j21, j22]], dtype=np.float32)

    def segment_thai_clusters(self, text: str) -> List[ThaiGraphemeCluster]:
        thai_pattern = re.compile(r'([ก-ฮ][ฺุู]?[ิีึืั็]?[่้๊๋์]?|[^\u0E00-\u0E7F]+|[\u0E00-\u0E7F])')
        matches = thai_pattern.findall(text)
        
        clusters: List[ThaiGraphemeCluster] = []
        accum_u = 0.0
        total_len = max(1, len(text))
        step_u = 1.0 / total_len

        for m in matches:
            span = len(m) * step_u
            base = m[0] if m else ""
            clusters.append(ThaiGraphemeCluster(
                text=m,
                base_consonant=base,
                relative_u=accum_u,
                span_u=span
            ))
            accum_u += span

        return clusters
