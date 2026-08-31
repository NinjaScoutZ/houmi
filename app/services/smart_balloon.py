"""Smart Balloon V15 Engine: Universal Multi-Archetype Adaptive Balloon Segmentation.

Features:
1. Pure Raw White Binary Mask Extraction (zero destructive morphology on line art).
2. 4-Archetype Cascading Shape Classifier:
   - SPIKY_FUZZY: Thought bubbles, scream auras (roughness > 1.8) -> 100% raw spike preservation.
   - RECTANGULAR: Caption boxes (rect_ratio > 0.82 & aspect > 1.6) -> Rounded Rectangle fitting.
   - ANGULAR: Pointed fantasy bubbles (corners <= 10 & rect < 0.80) -> Douglas-Peucker simplification.
   - SMOOTH_OVAL: Standard dialogue balloons -> Dynamic Waist Constriction + Bézier Arc Bridge.
3. Centroid-Anchored Safe Inset Margin (5% - 20%, default 10%) for text fitting.
4. Graceful Fallback to SAM 2.1 or standard bbox when dealing with dark/gradient panels.
"""

from __future__ import annotations

import logging
import math
import time
from typing import Any, Literal

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d

logger = logging.getLogger(__name__)

SMART_BALLOON_VERSION = "v15"
BalloonArchetype = Literal["SPIKY_FUZZY", "RECTANGULAR", "ANGULAR", "SMOOTH_OVAL", "UNKNOWN"]


# =========================================================================
# 1. Feature Extraction & Cascading Classifier
# =========================================================================

def compute_edge_roughness(contour: np.ndarray, sigma: float = 5.0) -> float:
    """Compute radial variance to detect spiky/fuzzy feathered edges."""
    pts = contour.reshape(-1, 2).astype(np.float32)
    if len(pts) < 15:
        return 0.0
    M = cv2.moments(contour)
    if M["m00"] <= 0:
        return 0.0
    cx, cy = M["m10"] / M["m00"], M["m01"] / M["m00"]
    distances = np.linalg.norm(pts - np.array([cx, cy], dtype=np.float32), axis=1)
    smooth_dist = gaussian_filter1d(distances, sigma=sigma, mode="wrap")
    return float(np.std(distances - smooth_dist))


def detect_fuzzy_edge_density(
    raw_gray: np.ndarray,
    contour: np.ndarray,
    band_thickness: int = 35,
) -> tuple[bool, float]:
    """
    Measures edge pixel density in the outer ring directly outside the balloon interior from the raw image.
    Spiky, fuzzy, thought clouds, and scream auras contain dense stroke bursts extending into the outer ring.
    """
    if raw_gray is None or contour is None or len(contour) < 5:
        return False, 0.0

    ch, cw = raw_gray.shape[:2]
    peri = cv2.arcLength(contour, True)
    if peri < 10:
        return False, 0.0

    # Canny edge detector on raw grayscale image
    edges = cv2.Canny(raw_gray, 50, 150)

    # Base contour mask of interior
    mask = np.zeros((ch, cw), dtype=np.uint8)
    cv2.drawContours(mask, [contour], -1, 255, -1)

    # Outer ring outside the white mask
    k_size = max(15, min(band_thickness, 45))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_size, k_size))
    dilated = cv2.dilate(mask, kernel)
    outer_ring = cv2.subtract(dilated, mask)

    ring_area = int(cv2.countNonZero(outer_ring))
    if ring_area < 50:
        return False, 0.0

    edge_pixels_in_ring = int(np.count_nonzero((edges > 0) & (outer_ring > 0)))
    density = edge_pixels_in_ring / float(ring_area)
    edge_per_peri = edge_pixels_in_ring / float(peri)

    # Clean single stroke has edge_per_peri <= 1.35.
    # Fuzzy, feathered, hairy, or spiky balloons have dense multi-stroke bursts (edge_per_peri >= 1.45 and density >= 0.095).
    is_fuzzy = (density >= 0.095 and edge_per_peri >= 1.45) or (edge_per_peri >= 2.0)
    return is_fuzzy, float(round(density, 3))


def compute_edge_roughness_from_raw_image(
    raw_gray: np.ndarray,
    contour: np.ndarray,
    sample_width: int = 25,
) -> float:
    """
    Computes gradient variance across normal profiles along the raw contour to detect fine fuzzy strokes.
    """
    if raw_gray is None or contour is None or len(contour) < 10:
        return 0.0

    contour_pts = contour.reshape(-1, 2)
    step = max(3, len(contour_pts) // 60)
    samples = contour_pts[::step]
    if len(samples) < 5:
        return 0.0

    roughness_samples: list[float] = []
    ch, cw = raw_gray.shape[:2]

    for pt in samples:
        x, y = int(pt[0]), int(pt[1])
        match_indices = np.where((contour_pts[:, 0] == pt[0]) & (contour_pts[:, 1] == pt[1]))[0]
        if len(match_indices) == 0:
            continue
        idx = int(match_indices[0])
        prev_pt = contour_pts[(idx - 5) % len(contour_pts)]
        next_pt = contour_pts[(idx + 5) % len(contour_pts)]

        tangent = (next_pt - prev_pt).astype(np.float32)
        norm_len = float(np.linalg.norm(tangent)) + 1e-6
        normal = np.array([-tangent[1], tangent[0]], dtype=np.float32) / norm_len

        half_w = sample_width // 2
        profile: list[float] = []
        for dist in range(-half_w, half_w + 1):
            sx = int(round(x + normal[0] * dist))
            sy = int(round(y + normal[1] * dist))
            if 0 <= sx < cw and 0 <= sy < ch:
                profile.append(float(raw_gray[sy, sx]))

        if len(profile) > 5:
            grad = np.diff(profile)
            roughness_samples.append(float(np.std(grad)))

    return float(round(np.std(roughness_samples), 2)) if len(roughness_samples) > 4 else 0.0


def compute_rectangularity(contour: np.ndarray) -> tuple[float, float]:
    """Returns (rect_ratio, aspect_ratio)."""
    rect = cv2.minAreaRect(contour)
    box = cv2.boxPoints(rect)
    box_area = cv2.contourArea(box)
    contour_area = cv2.contourArea(contour)
    rect_ratio = (contour_area / box_area) if box_area > 0 else 0.0
    w, h = rect[1]
    aspect_ratio = max(w, h) / (min(w, h) + 1e-6)
    return float(rect_ratio), float(aspect_ratio)


def count_sharp_corners(contour: np.ndarray, crop_w: int = 0, crop_h: int = 0) -> int:
    """
    Counts sharp polygonal corners (interior angle < 130 degrees),
    excluding corners on crop boundaries and clustering corners from localized speech tails.
    """
    perimeter = cv2.arcLength(contour, True)
    if perimeter == 0:
        return 0
    approx = cv2.approxPolyDP(contour, 0.008 * perimeter, True)
    if len(approx) < 4:
        return 0
    pts = approx.reshape(-1, 2).astype(np.float32)
    n = len(pts)
    M = cv2.moments(contour)
    cx, cy = (M["m10"] / M["m00"], M["m01"] / M["m00"]) if M["m00"] > 0 else (float(np.mean(pts[:, 0])), float(np.mean(pts[:, 1])))

    sharp_angles_from_center: list[float] = []

    for i in range(n):
        p_prev = pts[i - 1]
        p_curr = pts[i]
        p_next = pts[(i + 1) % n]
        if crop_w > 0 and crop_h > 0:
            if p_curr[0] <= 4 or p_curr[0] >= crop_w - 4 or p_curr[1] <= 4 or p_curr[1] >= crop_h - 4:
                continue
        v1 = p_prev - p_curr
        v2 = p_next - p_curr
        n1 = float(np.linalg.norm(v1))
        n2 = float(np.linalg.norm(v2))
        if n1 > 0 and n2 > 0:
            cos_a = float(np.dot(v1, v2) / (n1 * n2))
            cos_a = max(-1.0, min(1.0, cos_a))
            angle_deg = float(np.arccos(cos_a) * (180.0 / np.pi))
            if angle_deg < 130.0:
                center_ang = float(np.arctan2(p_curr[1] - cy, p_curr[0] - cx) * 180.0 / np.pi)
                sharp_angles_from_center.append(center_ang)

    if not sharp_angles_from_center:
        return 0

    # Cluster corners within 45 degrees of each other (a single speech tail produces 2-3 corners within 30 deg)
    sorted_angles = sorted(sharp_angles_from_center)
    distinct_corner_clusters = 0
    last_ang = -999.0
    for ang in sorted_angles:
        if abs(ang - last_ang) > 45.0:
            distinct_corner_clusters += 1
            last_ang = ang

    return distinct_corner_clusters


def classify_balloon_archetype(
    contour: np.ndarray,
    text_bbox: dict,
    crop_w: int = 0,
    crop_h: int = 0,
    raw_gray: np.ndarray | None = None,
) -> tuple[BalloonArchetype, dict[str, Any]]:
    """Cascading shape classifier: SPIKY_FUZZY > RECTANGULAR > ANGULAR > SMOOTH_OVAL."""
    area = cv2.contourArea(contour)
    if area < 100:
        return "SMOOTH_OVAL", {"reason": "area_too_small"}

    roughness = compute_edge_roughness(contour)
    rect_ratio, aspect_ratio = compute_rectangularity(contour)
    sharp_corners = count_sharp_corners(contour, crop_w=crop_w, crop_h=crop_h)

    # Edge density and raw image gradient analysis
    is_fuzzy_density = False
    edge_density = 0.0
    raw_roughness = 0.0
    if raw_gray is not None:
        is_fuzzy_density, edge_density = detect_fuzzy_edge_density(raw_gray, contour)
        if edge_density > 0.08 or roughness > 1.2:
            raw_roughness = compute_edge_roughness_from_raw_image(raw_gray, contour)

    # FFT frequency analysis for high-frequency perimeter fluctuations
    high_freq_ratio = 0.0
    pts = contour.reshape(-1, 2).astype(np.float32)
    if len(pts) >= 16:
        M = cv2.moments(contour)
        if M["m00"] > 0:
            cx, cy = M["m10"] / M["m00"], M["m01"] / M["m00"]
            distances = np.linalg.norm(pts - np.array([cx, cy], dtype=np.float32), axis=1)
            try:
                fft_vals = np.fft.rfft(distances)
                power = np.abs(fft_vals) ** 2
                tot_p = float(np.sum(power))
                if tot_p > 1e-6 and len(power) > 4:
                    high_p = float(np.sum(power[len(power) // 4:]))
                    high_freq_ratio = float(round(high_p / tot_p, 3))
            except Exception:
                pass

    # Check if polygon is a pure rectangular caption box
    peri = cv2.arcLength(contour, True)
    approx = cv2.approxPolyDP(contour, 0.04 * peri, True)
    is_pure_rect = False
    if len(approx) == 4 and rect_ratio > 0.85:
        pts_rect = approx.reshape(4, 2)
        angles = []
        for i in range(4):
            v1 = pts_rect[i - 1] - pts_rect[i]
            v2 = pts_rect[(i + 1) % 4] - pts_rect[i]
            cos_a = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6)
            angle = np.arccos(np.clip(cos_a, -1.0, 1.0)) * 180 / np.pi
            angles.append(angle)
        if all(70 <= a <= 110 for a in angles):
            is_pure_rect = True

    hull = cv2.convexHull(contour)
    hull_area = float(cv2.contourArea(hull))
    solidity = float(area / hull_area) if hull_area > 0 else 1.0

    # Geometric Template Fitting: Ellipse Fitting IoU & Rectangle Fitting IoU
    ellipse_iou = 0.0
    if len(contour) >= 5 and crop_w > 0 and crop_h > 0:
        try:
            ell = cv2.fitEllipse(contour)
            ell_mask = np.zeros((crop_h, crop_w), dtype=np.uint8)
            cv2.ellipse(ell_mask, ell, 255, -1)
            cnt_mask = np.zeros((crop_h, crop_w), dtype=np.uint8)
            cv2.drawContours(cnt_mask, [contour], -1, 255, -1)
            inter = int(np.count_nonzero(cnt_mask & ell_mask))
            union = int(np.count_nonzero(cnt_mask | ell_mask))
            ellipse_iou = float(round(inter / max(1.0, union), 3))
        except Exception:
            pass

    rect_iou = 0.0
    if len(contour) >= 4 and crop_w > 0 and crop_h > 0:
        try:
            rect = cv2.minAreaRect(contour)
            box = cv2.boxPoints(rect).astype(np.int32)
            rect_mask = np.zeros((crop_h, crop_w), dtype=np.uint8)
            cv2.fillPoly(rect_mask, [box], 255)
            cnt_mask = np.zeros((crop_h, crop_w), dtype=np.uint8)
            cv2.drawContours(cnt_mask, [contour], -1, 255, -1)
            rect_inter = int(np.count_nonzero(cnt_mask & rect_mask))
            rect_union = int(np.count_nonzero(cnt_mask | rect_mask))
            rect_iou = float(round(rect_inter / max(1.0, rect_union), 3))
        except Exception:
            pass

    meta = {
        "roughness": round(roughness, 2),
        "raw_roughness": raw_roughness,
        "edge_density": edge_density,
        "high_freq_ratio": high_freq_ratio,
        "rect_ratio": round(rect_ratio, 2),
        "sharp_corners": sharp_corners,
        "aspect_ratio": round(aspect_ratio, 2),
        "solidity": round(solidity, 3),
        "ellipse_iou": ellipse_iou,
        "rect_iou": rect_iou,
    }

    # 1. SPIKY_FUZZY Archetype:
    # Requires genuine contour roughness (many jagged teeth all around), high-frequency FFT fluctuations,
    # or a dense fuzzy feathered aura around the raw boundary (raw_roughness >= 22.0 and is_fuzzy_density).
    is_spiky_fuzzy = False
    if (roughness > 2.2 and sharp_corners >= 8) or (high_freq_ratio > 0.16 and sharp_corners >= 6):
        if is_fuzzy_density or roughness > 2.8 or high_freq_ratio > 0.20 or sharp_corners >= 10:
            is_spiky_fuzzy = True
    elif is_fuzzy_density and edge_density >= 0.095 and raw_roughness >= 22.0:
        # A round thought balloon with dense fuzzy stroke perimeter
        is_spiky_fuzzy = True

    if is_spiky_fuzzy:
        return "SPIKY_FUZZY", meta
    elif is_pure_rect or (rect_iou >= 0.90 and roughness < 1.15):
        return "RECTANGULAR", meta
    elif sharp_corners >= 3 and rect_ratio < 0.85:
        return "ANGULAR", meta
    elif (ellipse_iou >= 0.70 and solidity >= 0.86 and roughness < 1.30) or (solidity >= 0.88 and roughness < 1.30):
        return "SMOOTH_OVAL", meta
    elif rect_ratio > 0.85 and aspect_ratio > 1.5:
        return "RECTANGULAR", meta
    else:
        return "SMOOTH_OVAL", meta


# =========================================================================
# 2. Dynamic Waist Constriction & Feature-Preserving Reconstruction
# =========================================================================

def find_true_waist_concave_points(
    combined_cnt: np.ndarray,
    c1: tuple[int, int] | None = None,
    c2: tuple[int, int] | None = None,
) -> tuple[np.ndarray, np.ndarray, bool]:
    """
    Finds the deepest inward neck pinches between two conjoined balloons
    strictly along the axis connecting c1 and c2.
    Returns (p_left, p_right, has_genuine_waist).
    """
    pts = combined_cnt.reshape(-1, 2)
    if len(pts) < 6 or c1 is None or c2 is None:
        return pts[0], pts[len(pts) // 2], False

    c1_arr = np.array(c1, dtype=np.float32)
    c2_arr = np.array(c2, dtype=np.float32)
    axis_vec = c2_arr - c1_arr
    axis_len = float(np.linalg.norm(axis_vec))
    if axis_len < 1e-3:
        return pts[0], pts[len(pts) // 2], False

    u_axis = axis_vec / axis_len
    # Normal perpendicular to axis (left is positive, right is negative)
    u_norm = np.array([-u_axis[1], u_axis[0]], dtype=np.float32)

    # Project all contour points onto axis and normal
    rel_pts = pts.astype(np.float32) - c1_arr
    t_proj = np.dot(rel_pts, u_axis) / axis_len  # t in [0, 1] between c1 and c2
    d_norm = np.dot(rel_pts, u_norm)             # perpendicular distance

    # 1. Primary: Use Convexity Defects filtered strictly between c1 and c2 (t in [0.15, 0.85])
    left_defects = []
    right_defects = []

    try:
        hull_idx = cv2.convexHull(pts[:, None, :], returnPoints=False)
        if hull_idx is not None and len(hull_idx) >= 3:
            defects = cv2.convexityDefects(pts[:, None, :], hull_idx)
            if defects is not None:
                for i in range(len(defects)):
                    s, e, f, d = defects[i].flatten()
                    pt_f = pts[f]
                    rel_f = pt_f.astype(np.float32) - c1_arr
                    t_f = float(np.dot(rel_f, u_axis) / axis_len)
                    d_f = float(np.dot(rel_f, u_norm))
                    depth = d / 256.0

                    # Strictly filter defects in intermediate zone between c1 and c2
                    if 0.15 <= t_f <= 0.85:
                        if d_f > 0:
                            left_defects.append((depth, pt_f, abs(t_f - 0.5)))
                        else:
                            right_defects.append((depth, pt_f, abs(t_f - 0.5)))
    except Exception:
        pass

    has_genuine_waist = bool(
        (len(left_defects) > 0 and left_defects[0][0] >= 6.0)
        or (len(right_defects) > 0 and right_defects[0][0] >= 6.0)
    )

    # Pick deepest defect on left side
    p_left = None
    if left_defects:
        left_defects.sort(key=lambda x: x[0], reverse=True)
        p_left = left_defects[0][1]

    # Pick deepest defect on right side
    p_right = None
    if right_defects:
        right_defects.sort(key=lambda x: x[0], reverse=True)
        p_right = right_defects[0][1]

    # 2. Fallback for either side: find narrowest neck point near midpoint (t in [0.20, 0.80])
    mask_mid = (t_proj >= 0.20) & (t_proj <= 0.80)

    if p_left is None:
        mask_left = mask_mid & (d_norm > 0)
        if np.any(mask_left):
            cand_pts = pts[mask_left]
            cand_norm = d_norm[mask_left]
            p_left = cand_pts[np.argmin(cand_norm)]
        else:
            p_left = np.array([int(round(c1[0] + u_norm[0] * 50)), int(round(c1[1] + u_norm[1] * 50))])

    if p_right is None:
        mask_right = mask_mid & (d_norm <= 0)
        if np.any(mask_right):
            cand_pts = pts[mask_right]
            cand_norm = np.abs(d_norm[mask_right])
            p_right = cand_pts[np.argmin(cand_norm)]
        else:
            p_right = np.array([int(round(c1[0] - u_norm[0] * 50)), int(round(c1[1] - u_norm[1] * 50))])

    # Ensure left waist has smaller x (or consistent ordering)
    if p_left[0] > p_right[0]:
        p_left, p_right = p_right, p_left

    return np.array(p_left), np.array(p_right), has_genuine_waist


def generate_natural_bridge(ellipse: tuple, pt_start: tuple | np.ndarray, pt_end: tuple | np.ndarray, num_samples: int = 50) -> np.ndarray:
    """
    Generates a smooth parametric ellipse bridge from pt_start to pt_end.
    Guarantees 0-pixel gap: exactly touches pt_start at index 0 and pt_end at index -1.
    """
    (xc, yc), (d1, d2), angle = ellipse
    a, b = max(1.0, d1 / 2.0), max(1.0, d2 / 2.0)
    rad = np.deg2rad(angle)
    cos_a, sin_a = np.cos(rad), np.sin(rad)
    
    def to_local(p):
        dx, dy = p[0] - xc, p[1] - yc
        x_rot = cos_a * dx + sin_a * dy
        y_rot = -sin_a * dx + cos_a * dy
        return np.arctan2(y_rot / b, x_rot / a)
    
    t_start = to_local(pt_start)
    t_end = to_local(pt_end)
    
    if t_end < t_start: 
        t_end += 2 * np.pi
    if (t_end - t_start) > np.pi: 
        t_start, t_end = t_end, t_start + 2 * np.pi
        
    t_vals = np.linspace(t_start, t_end, num_samples)
    x_loc = a * np.cos(t_vals)
    y_loc = b * np.sin(t_vals)
    
    x_glob = xc + (cos_a * x_loc - sin_a * y_loc)
    y_glob = yc + (sin_a * x_loc + cos_a * y_loc)
    
    return np.column_stack((x_glob, y_glob)).astype(np.int32)


def reconstruct_raw_balloon_top(
    raw_combined_cnt: np.ndarray,
    left_waist: np.ndarray,
    right_waist: np.ndarray,
    text_bbox: dict | None = None,
) -> np.ndarray:
    """
    Reconstructs upper balloon using Zero-Distortion Boundary Completion:
    100% original raw upper arc + smooth parametric ellipse bridge.
    """
    main_cnt = raw_combined_cnt.reshape(-1, 2)
    idx1 = min(range(len(main_cnt)), key=lambda i: np.linalg.norm(main_cnt[i] - left_waist))
    idx2 = min(range(len(main_cnt)), key=lambda i: np.linalg.norm(main_cnt[i] - right_waist))

    if idx1 < idx2:
        seg_a = main_cnt[idx1 : idx2 + 1]
        seg_b = np.vstack([main_cnt[idx2:], main_cnt[: idx1 + 1]])
    else:
        seg_a = main_cnt[idx2 : idx1 + 1]
        seg_b = np.vstack([main_cnt[idx1:], main_cnt[: idx2 + 1]])

    top_seg = seg_a if seg_a[:, 1].mean() < seg_b[:, 1].mean() else seg_b

    # Fit ellipse on uncorrupted raw upper segment
    if len(top_seg) >= 6:
        try:
            ellipse_upper = cv2.fitEllipseDirect(top_seg[:, None, :])
            bridge_upper = generate_natural_bridge(ellipse_upper, top_seg[-1], top_seg[0], num_samples=50)
            full_poly = np.vstack([top_seg, bridge_upper])
            return full_poly.reshape(-1, 1, 2)
        except Exception:
            pass

    # Fallback to smooth Bezier arc
    p_start = top_seg[-1].astype(np.float32)
    p_end = top_seg[0].astype(np.float32)
    mid_x = (p_start[0] + p_end[0]) / 2.0
    ctrl_y = float(max(p_start[1], p_end[1]) + 20)
    t_vals = np.linspace(0, 1, 40)
    bottom_arc = []
    for t in t_vals:
        px = (1 - t) ** 2 * p_start[0] + 2 * (1 - t) * t * mid_x + t**2 * p_end[0]
        py = (1 - t) ** 2 * p_start[1] + 2 * (1 - t) * t * ctrl_y + t**2 * p_end[1]
        bottom_arc.append([int(round(px)), int(round(py))])

    full_poly = np.vstack([top_seg, np.array(bottom_arc)])
    return full_poly.reshape(-1, 1, 2)


def reconstruct_raw_balloon_bottom(
    raw_combined_cnt: np.ndarray,
    left_waist: np.ndarray,
    right_waist: np.ndarray,
    text_bbox: dict | None = None,
) -> np.ndarray:
    """
    Reconstructs lower balloon using Zero-Distortion Boundary Completion:
    100% original raw lower arc + smooth parametric ellipse bridge.
    """
    main_cnt = raw_combined_cnt.reshape(-1, 2)
    idx1 = min(range(len(main_cnt)), key=lambda i: np.linalg.norm(main_cnt[i] - left_waist))
    idx2 = min(range(len(main_cnt)), key=lambda i: np.linalg.norm(main_cnt[i] - right_waist))

    if idx1 < idx2:
        seg_a = main_cnt[idx1 : idx2 + 1]
        seg_b = np.vstack([main_cnt[idx2:], main_cnt[: idx1 + 1]])
    else:
        seg_a = main_cnt[idx2 : idx1 + 1]
        seg_b = np.vstack([main_cnt[idx1:], main_cnt[: idx2 + 1]])

    bottom_seg = seg_a if seg_a[:, 1].mean() > seg_b[:, 1].mean() else seg_b

    # Fit ellipse on uncorrupted raw lower segment
    if len(bottom_seg) >= 6:
        try:
            ellipse_lower = cv2.fitEllipseDirect(bottom_seg[:, None, :])
            bridge_lower = generate_natural_bridge(ellipse_lower, bottom_seg[-1], bottom_seg[0], num_samples=50)
            full_poly = np.vstack([bottom_seg, bridge_lower])
            return full_poly.reshape(-1, 1, 2)
        except Exception:
            pass

    # Fallback to smooth Bezier arc
    p_start = bottom_seg[-1].astype(np.float32)
    p_end = bottom_seg[0].astype(np.float32)
    mid_x = (p_start[0] + p_end[0]) / 2.0
    ctrl_y = float(min(p_start[1], p_end[1]) - 20)
    t_vals = np.linspace(0, 1, 40)
    top_arc = []
    for t in t_vals:
        px = (1 - t) ** 2 * p_start[0] + 2 * (1 - t) * t * mid_x + t**2 * p_end[0]
        py = (1 - t) ** 2 * p_start[1] + 2 * (1 - t) * t * ctrl_y + t**2 * p_end[1]
        top_arc.append([int(round(px)), int(round(py))])

    full_poly = np.vstack([bottom_seg, np.array(top_arc)])
    return full_poly.reshape(-1, 1, 2)


def apply_contour_inset(contour: np.ndarray, inset_ratio: float = 0.10) -> np.ndarray:
    """Scales a contour inward towards its centroid by inset_ratio (Safe Text Margin)."""
    scale_factor = 1.0 - max(0.05, min(0.25, inset_ratio))
    pts = contour.reshape(-1, 2).astype(np.float32)
    M = cv2.moments(contour)
    if M["m00"] > 0:
        cx = M["m10"] / M["m00"]
        cy = M["m01"] / M["m00"]
    else:
        cx = float(np.mean(pts[:, 0]))
        cy = float(np.mean(pts[:, 1]))

    center = np.array([cx, cy], dtype=np.float32)
    inset_pts = center + scale_factor * (pts - center)
    return inset_pts.astype(np.int32).reshape(-1, 1, 2)


def _compute_row_width_constraints(
    contour: np.ndarray,
    bbox_x: float = 0.0,
    bbox_y: float = 0.0,
    bbox_w: float = 0.0,
    bbox_h: float = 0.0,
) -> dict[str, Any]:
    """
    Computes per-row width constraints for shape-adaptive text wrapping.
    Returns a dictionary with row-wise maximum widths relative to the balloon shape.
    """
    pts = contour.reshape(-1, 2).astype(np.float32)
    if len(pts) < 3:
        return {"enabled": False}

    # Bounding box of the contour itself ensures zero coordinate drift
    bx, by, bw, bh = cv2.boundingRect(pts.astype(np.int32))
    if bw <= 0 or bh <= 0:
        return {"enabled": False}

    local_h = int(bh) + 10
    local_w = int(bw) + 10
    mask = np.zeros((local_h, local_w), dtype=np.uint8)

    # Translate contour to local coordinates with 5px padding
    local_pts = (pts - np.array([bx - 5, by - 5], dtype=np.float32)).astype(np.int32)
    cv2.fillPoly(mask, [local_pts], 255)

    # Compute width at each row with safe text margin
    row_widths = []
    for y in range(local_h):
        white_pixels = np.count_nonzero(mask[y])
        row_widths.append(float(white_pixels))

    # Smooth the widths to avoid jitter
    from scipy.ndimage import gaussian_filter1d
    smoothed = gaussian_filter1d(row_widths, sigma=3.0)

    return {
        "enabled": True,
        "row_widths": [max(0.0, float(round(w * 0.85, 1))) for w in smoothed.tolist()],
        "height": local_h,
    }


# =========================================================================
# 3. Core Engine Coordinator
# =========================================================================

def process_smart_balloon_v15(
    image: np.ndarray,
    text_bbox: dict,
    rival_boxes: list[dict] | None = None,
    inset_ratio: float = 0.10,
    white_thresh: int = 180,
    use_adaptive: bool = False,
) -> dict[str, Any]:
    """
    Executes the Smart Balloon V15 feature-preserving pipeline.

    Returns rich metadata containing raw bounds, 10% safe bounds, archetype, and contours.

    NEW in V15.1: Set use_adaptive=True to enable V16 adaptive background processing
    for gray/gradient backgrounds and weak balloon strokes.
    """
    # Try V16 adaptive enhancement first if enabled
    if use_adaptive:
        try:
            from app.services.smart_balloon_adaptive import process_smart_balloon_v16_adaptive
            v16_result = process_smart_balloon_v16_adaptive(
                image, text_bbox, rival_boxes=rival_boxes, inset_ratio=inset_ratio
            )
            if v16_result.get("success"):
                logger.info("Smart Balloon V16 adaptive processing succeeded")
                return v16_result
            else:
                logger.warning(
                    "Smart Balloon V16 failed (%s), falling back to V15",
                    v16_result.get("fallback", "unknown"),
                )
        except Exception as exc:
            logger.warning("Smart Balloon V16 exception: %s, falling back to V15", exc)

    # Original V15 logic below (unchanged)
    t0 = time.time()
    img_h, img_w = image.shape[:2]
    bx, by = float(text_bbox["x"]), float(text_bbox["y"])
    bw, bh = float(text_bbox["width"]), float(text_bbox["height"])

    # Define local crop with adaptive padding to avoid clipping tall spikes/tails
    pad_x = max(160, int(bw * 0.35))
    pad_y = max(220, int(bh * 1.50))
    sx0 = max(0, int(bx - pad_x))
    sy0 = max(0, int(by - pad_y))
    sx1 = min(img_w, int(bx + bw + pad_x))
    sy1 = min(img_h, int(by + bh + pad_y))

    crop = image[sy0:sy1, sx0:sx1]
    if crop.size == 0:
        return _fallback_result(bx, by, bw, bh, "empty_crop")

    ch, cw = crop.shape[:2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    local_bx = bx - sx0
    local_by = by - sy0

    # 1. Stroke-Protected White Interior Extraction (Dark Edge Barrier)
    # Detect dark boundary stroke lines (line art) & Canny edges to prevent leaking outside balloon into light background / SFX
    dark_thresh = (gray < 110).astype(np.uint8) * 255
    canny_edges = cv2.Canny(gray, 40, 120)
    edge_barrier = cv2.bitwise_or(dark_thresh, canny_edges)
    k_edge = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    edge_barrier = cv2.dilate(edge_barrier, k_edge)

    cx_seed = int(local_bx + bw / 2.0)
    cy_seed = int(local_by + bh / 2.0)
    cx_seed = max(0, min(cw - 1, cx_seed))
    cy_seed = max(0, min(ch - 1, cy_seed))

    # If seed point is on edge_barrier (e.g. text character), search within text box for a white seed
    if edge_barrier[cy_seed, cx_seed] > 0 or gray[cy_seed, cx_seed] < white_thresh:
        found_seed = False
        for dy_s in range(-int(bh * 0.4), int(bh * 0.4), 4):
            for dx_s in range(-int(bw * 0.4), int(bw * 0.4), 4):
                nx_s = max(0, min(cw - 1, cx_seed + dx_s))
                ny_s = max(0, min(ch - 1, cy_seed + dy_s))
                if edge_barrier[ny_s, nx_s] == 0 and gray[ny_s, nx_s] >= white_thresh:
                    cx_seed, cy_seed = nx_s, ny_s
                    found_seed = True
                    break
            if found_seed:
                break

    # Build flood fill mask where dark boundary strokes act as hard impassable barriers
    flood_mask = np.zeros((ch + 2, cw + 2), dtype=np.uint8)
    flood_mask[1:-1, 1:-1] = (edge_barrier > 0).astype(np.uint8) * 1

    # Flood fill from text box seed point: stops immediately at dark stroke line
    filled_img = gray.copy()
    cv2.floodFill(filled_img, flood_mask, (cx_seed, cy_seed), 255, loDiff=35, upDiff=35, flags=4 | cv2.FLOODFILL_FIXED_RANGE | (255 << 8))

    raw_flooded = (flood_mask[1:-1, 1:-1] == 255).astype(np.uint8) * 255
    connected_white = raw_flooded.copy()

    # If seed landed on dark text character stroke, sample a 5-point cross neighborhood
    if cv2.countNonZero(connected_white) < (bw * bh * 0.20):
        for dx_s, dy_s in [(0, -int(bh * 0.25)), (0, int(bh * 0.25)), (-int(bw * 0.25), 0), (int(bw * 0.25), 0)]:
            nx_s = max(0, min(cw - 1, cx_seed + dx_s))
            ny_s = max(0, min(ch - 1, cy_seed + dy_s))
            if gray[ny_s, nx_s] >= white_thresh:
                flood_mask = np.zeros((ch + 2, cw + 2), dtype=np.uint8)
                flood_mask[1:-1, 1:-1] = (edge_barrier > 0).astype(np.uint8) * 1
                cv2.floodFill(filled_img, flood_mask, (nx_s, ny_s), 255, loDiff=35, upDiff=35, flags=4 | cv2.FLOODFILL_FIXED_RANGE | (255 << 8))
                cand_white = (flood_mask[1:-1, 1:-1] == 255).astype(np.uint8) * 255
                if cv2.countNonZero(cand_white) > cv2.countNonZero(connected_white):
                    connected_white = cand_white
                    raw_flooded = cand_white
                    cx_seed, cy_seed = nx_s, ny_s

    # Sever narrow 1-6px leakage channels (isthmuses) leading out of the balloon into gutters/adjacent panels
    if cv2.countNonZero(connected_white) >= (bw * bh * 0.20):
        open_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        opened_white = cv2.morphologyEx(connected_white, cv2.MORPH_OPEN, open_k)
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(opened_white)
        if num_labels > 1:
            tb_x0, tb_y0 = max(0, int(local_bx)), max(0, int(local_by))
            tb_x1, tb_y1 = min(cw, int(local_bx + bw)), min(ch, int(local_by + bh))
            best_lbl = 0
            best_score = -1.0
            for lbl in range(1, num_labels):
                comp_mask = (labels == lbl)
                overlap = int(np.count_nonzero(comp_mask[tb_y0:tb_y1, tb_x0:tb_x1]))
                area = stats[lbl, cv2.CC_STAT_AREA]
                score = overlap * 3.0 + area * 0.1
                if score > best_score and overlap > 0:
                    best_score = score
                    best_lbl = lbl
            if best_lbl > 0:
                cleaned_comp = (labels == best_lbl).astype(np.uint8) * 255
                restored = cv2.dilate(cleaned_comp, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
                connected_white = cv2.bitwise_and(restored, raw_flooded)

    # Fallback to stroke-blocked thresholding if flood fill didn't capture sufficient area
    if cv2.countNonZero(connected_white) < (bw * bh * 0.20):
        raw_white = (gray >= white_thresh).astype(np.uint8) * 255
        raw_white[edge_barrier > 0] = 0  # STRICTLY enforce dark stroke barrier
        close_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))  # Small kernel to avoid jumping dark borders
        closed_white = cv2.morphologyEx(raw_white, cv2.MORPH_CLOSE, close_k)
        closed_white[edge_barrier > 0] = 0

        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(closed_white)
        if num_labels > 1:
            tb_x0, tb_y0 = max(0, int(local_bx)), max(0, int(local_by))
            tb_x1, tb_y1 = min(cw, int(local_bx + bw)), min(ch, int(local_by + bh))
            tb_roi_mask = np.zeros((ch, cw), dtype=bool)
            tb_roi_mask[tb_y0:tb_y1, tb_x0:tb_x1] = True

            best_label = None
            best_score = -1.0
            for label in range(1, num_labels):
                area = stats[label, cv2.CC_STAT_AREA]
                if area < (bw * bh * 0.15):
                    continue
                comp_mask = labels == label
                overlap = int(np.count_nonzero(comp_mask & tb_roi_mask))
                score = overlap * 2.0 + area * 0.4
                if score > best_score:
                    best_score = score
                    best_label = label

            if best_label is not None:
                connected_white = (labels == best_label).astype(np.uint8) * 255
                c_center = centroids[best_label]
                cx_seed = int(round(c_center[0]))
                cy_seed = int(round(c_center[1]))

    # Fill internal text holes and close text bridges so text inside the balloon doesn't form jagged cavities
    k_text_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (19, 19))
    closed_text = cv2.morphologyEx(connected_white, cv2.MORPH_CLOSE, k_text_close)
    cnts_fill, _ = cv2.findContours(closed_text, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if cnts_fill:
        solid_white = np.zeros_like(connected_white)
        cv2.drawContours(solid_white, cnts_fill, -1, 255, -1)
        connected_white = solid_white

    cnts, _ = cv2.findContours(connected_white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cnts:
        return _fallback_result(bx, by, bw, bh, "no_white_contour")

    main_cnt = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(main_cnt) < (bw * bh * 0.4):
        return _fallback_result(bx, by, bw, bh, "contour_too_small")

    # Sanity gate: the chosen component must actually cover the text bbox.
    # Without this, flood fill that leaks into a neighbouring white region
    # reports a false-positive success with glyphs placed in the wrong balloon.
    check_mask = np.zeros((ch, cw), dtype=np.uint8)
    cv2.fillPoly(check_mask, [main_cnt], 255)
    tb_x0g, tb_y0g = max(0, int(local_bx)), max(0, int(local_by))
    tb_x1g, tb_y1g = min(cw, int(local_bx + bw)), min(ch, int(local_by + bh))
    bbox_cover = float(np.count_nonzero(check_mask[tb_y0g:tb_y1g, tb_x0g:tb_x1g])) / max(1, (tb_x1g - tb_x0g) * (tb_y1g - tb_y0g))
    if bbox_cover < 0.35:
        return _fallback_result(bx, by, bw, bh, "text_bbox_not_covered")

    # Raw contour for classification
    raw_main_cnt_for_classify = main_cnt

    # 2. Archetype classification on raw contour (before morphology smoothing) with raw image edge analysis
    # Use raw_main_cnt_for_classify if available (preserves spikes/fuzzy edges), otherwise fall back to processed main_cnt
    classify_cnt = raw_main_cnt_for_classify if raw_main_cnt_for_classify is not None and cv2.contourArea(raw_main_cnt_for_classify) >= (bw * bh * 0.3) else main_cnt
    local_bbox = {"x": local_bx, "y": local_by, "width": bw, "height": bh}
    archetype, meta = classify_balloon_archetype(classify_cnt, local_bbox, crop_w=cw, crop_h=ch, raw_gray=gray)

    # 3. Check for conjoined balloons if rival_boxes provided
    poly = main_cnt
    if rival_boxes and len(rival_boxes) > 0:
        # Check if any rival box overlaps this white component AND is a distinct separate bubble.
        # We use bbox overlap ratio as the primary signal — if two YOLO boxes overlap heavily
        # they are almost certainly two halves of a conjoined balloon, not a duplicate detection.
        for r_box in rival_boxes:
            r_cx = int(r_box["x"] + r_box["width"] / 2.0) - sx0
            r_cy = int(r_box["y"] + r_box["height"] / 2.0) - sy0

            # Compute overlap between this block's bbox and the rival's bbox (in crop coords)
            r_x0 = int(r_box["x"]) - sx0
            r_y0 = int(r_box["y"]) - sy0
            r_x1 = r_x0 + int(r_box["width"])
            r_y1 = r_y0 + int(r_box["height"])
            t_x0 = int(bx) - sx0
            t_y0 = int(by) - sy0
            t_x1 = t_x0 + int(bw)
            t_y1 = t_y0 + int(bh)
            ix = max(0, min(t_x1, r_x1) - max(t_x0, r_x0))
            iy = max(0, min(t_y1, r_y1) - max(t_y0, r_y0))
            overlap_area = ix * iy
            rival_area = int(r_box["width"]) * int(r_box["height"])
            target_area = bw * bh
            overlap_ratio = overlap_area / max(1, min(rival_area, target_area))

            # Check if rival block is inside the same white connected component
            is_same_white_blob = bool(0 <= r_cx < cw and 0 <= r_cy < ch and connected_white[r_cy, r_cx] > 0)
            
            if not is_same_white_blob and overlap_ratio < 0.10:
                continue

            # Secondary guard: skip only when the two DETECTOR box centers are extremely close
            own_cx = int(bx + bw / 2.0) - sx0
            own_cy_det = int(by + bh / 2.0) - sy0
            dist_det = float(np.hypot(own_cx - r_cx, own_cy_det - r_cy))
            min_sep_det = float(max(bw, bh) * 0.05)  # only block near-identical detector boxes
            if dist_det < min_sep_det:
                continue

            if is_same_white_blob or overlap_ratio >= 0.10:
                # Check for genuine conjoined twin waist pinch before slicing
                c1 = (own_cx, own_cy_det)
                c2 = (r_cx, r_cy)
                left_w, right_w, has_genuine_waist = find_true_waist_concave_points(main_cnt, c1, c2)
                if has_genuine_waist:
                    if own_cy_det < r_cy:
                        poly = reconstruct_raw_balloon_top(main_cnt, left_w, right_w, local_bbox)
                    else:
                        poly = reconstruct_raw_balloon_bottom(main_cnt, left_w, right_w, local_bbox)
                    archetype, meta = classify_balloon_archetype(poly, local_bbox, crop_w=cw, crop_h=ch, raw_gray=gray)
                    logger.debug(
                        "Conjoined balloon detected: overlap_ratio=%.2f dist_det=%.1f; sliced at waist",
                        overlap_ratio, dist_det,
                    )
                    break

    # 4. Inset Safe Margin Transform (10% standard)
    # For text typesetting and safe bounding box, isolate the Main Bubble Body (removing narrow speech tail pointers & speedlines).
    # For SPIKY_FUZZY bubbles, we skip aggressive morphology opening to preserve 100% of the raw fuzzy/spiky boundary.
    body_poly = poly
    poly_mask = np.zeros((ch, cw), dtype=np.uint8)
    cv2.fillPoly(poly_mask, [poly], 255)
    dist_map = cv2.distanceTransform(poly_mask, cv2.DIST_L2, 5)
    max_r = float(np.max(dist_map)) if np.max(dist_map) > 0 else 10.0

    if archetype != "SPIKY_FUZZY":
        # Distance-proportional morphological opening to cleanly sever speech tails from main oval body
        ksize = max(13, min(int(max_r * 0.45), int(min(bw, bh) * 0.40), 75))
        if ksize % 2 == 0:
            ksize += 1
        open_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
        body_mask = cv2.morphologyEx(poly_mask, cv2.MORPH_OPEN, open_k)
        body_cnts, _ = cv2.findContours(body_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if body_cnts:
            best_body = max(body_cnts, key=cv2.contourArea)
            if cv2.contourArea(best_body) >= (cv2.contourArea(poly) * 0.25):
                body_poly = best_body

    safe_poly = apply_contour_inset(body_poly, inset_ratio=inset_ratio)

    # Simplify contours to eliminate 1-pixel staircase noise and reduce payload
    peri_raw = cv2.arcLength(body_poly, True)
    poly_simple = cv2.approxPolyDP(body_poly, 0.002 * peri_raw, True) if peri_raw > 0 else body_poly

    peri_safe = cv2.arcLength(safe_poly, True)
    safe_poly_simple = cv2.approxPolyDP(safe_poly, 0.002 * peri_safe, True) if peri_safe > 0 else safe_poly

    # Convert contours back to absolute page coordinates
    abs_raw_cnt = poly_simple.reshape(-1, 2) + np.array([sx0, sy0])
    abs_safe_cnt = safe_poly_simple.reshape(-1, 2) + np.array([sx0, sy0])

    # Calculate raw & safe bounding boxes
    rx, ry, rw, rh = cv2.boundingRect(abs_raw_cnt)
    sx, sy, sw, sh = cv2.boundingRect(abs_safe_cnt)

    # Visual Centroid of the balloon body
    M = cv2.moments(body_poly)
    if M["m00"] > 0:
        abs_cx = float(sx0 + M["m10"] / M["m00"])
        abs_cy = float(sy0 + M["m01"] / M["m00"])
    else:
        abs_cx = float(sx + sw / 2.0)
        abs_cy = float(sy + sh / 2.0)

    # Generate crop mask
    crop_mask = np.zeros((ch, cw), dtype=np.uint8)
    cv2.fillPoly(crop_mask, [poly], 255)

    elapsed = time.time() - t0
    meta["elapsed_sec"] = round(elapsed, 4)
    meta["inset_ratio"] = inset_ratio
    meta["confidence"] = round(min(0.99, max(0.80, float(cv2.contourArea(poly) / max(1.0, float(bw * bh))))), 2)

    # Compute row-wise width constraints for shape-adaptive text wrapping
    row_width_data = _compute_row_width_constraints(safe_poly, sx, sy, sw, sh)

    return {
        "success": True,
        "method": "smart_balloon_v15",
        "archetype": archetype,
        "smart_x": float(sx),
        "smart_y": float(sy),
        "smart_width": float(sw),
        "smart_height": float(sh),
        "raw_bbox": {"x": float(rx), "y": float(ry), "width": float(rw), "height": float(rh)},
        "safe_bbox": {"x": float(sx), "y": float(sy), "width": float(sw), "height": float(sh)},
        "center": {"x": abs_cx, "y": abs_cy},
        "crop_mask": crop_mask,
        "crop_offset": (sx0, sy0),
        "mask_area": int(cv2.countNonZero(crop_mask)),
        "contour_points": abs_safe_cnt.tolist(),
        "raw_contour_points": abs_raw_cnt.tolist(),
        "row_width_constraints": row_width_data,
        "metadata": meta,
    }


def _fallback_result(bx: float, by: float, bw: float, bh: float, reason: str) -> dict[str, Any]:
    """Generates a fallback result matching the input text bbox."""
    return {
        "success": False,
        "method": f"fallback_{reason}",
        "archetype": "UNKNOWN",
        "smart_x": float(bx),
        "smart_y": float(by),
        "smart_width": float(bw),
        "smart_height": float(bh),
        "raw_bbox": {"x": float(bx), "y": float(by), "width": float(bw), "height": float(bh)},
        "safe_bbox": {"x": float(bx), "y": float(by), "width": float(bw), "height": float(bh)},
        "center": {"x": float(bx + bw / 2.0), "y": float(by + bh / 2.0)},
        "crop_mask": None,
        "crop_offset": (int(bx), int(by)),
        "mask_area": int(bw * bh),
        "contour_points": [],
        "raw_contour_points": [],
        "metadata": {"fallback_reason": reason},
    }


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convert RGB integers to hex string (#RRGGBB)."""
    return f"#{max(0, min(255, int(r))):02x}{max(0, min(255, int(g))):02x}{max(0, min(255, int(b))):02x}"


def extract_balloon_text_style(
    image_bgr: np.ndarray,
    bbox: tuple[int, int, int, int],
    text_mask: Optional[np.ndarray] = None,
) -> dict[str, Any]:
    """
    Extracts text color, balloon background color, stroke/outline color,
    stroke width, and rotation angle from a comic speech balloon region.
    """
    bx, by, bw, bh = [int(v) for v in bbox]
    if image_bgr is None or bw <= 2 or bh <= 2:
        return {
            "text_color": "#000000",
            "bg_color": "#ffffff",
            "stroke_color": None,
            "stroke_width": 0,
            "rotation_deg": 0.0,
            "has_stroke": False,
        }

    ih, iw = image_bgr.shape[:2]
    x0, y0 = max(0, bx), max(0, by)
    x1, y1 = min(iw, bx + bw), min(ih, by + bh)
    crop = image_bgr[y0:y1, x0:x1]
    if crop.size == 0:
        return {
            "text_color": "#000000",
            "bg_color": "#ffffff",
            "stroke_color": None,
            "stroke_width": 0,
            "rotation_deg": 0.0,
            "has_stroke": False,
        }

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    ch, cw = gray.shape[:2]

    # 1. Determine Background Color from outer border margin (sample 5-10% inset border)
    margin = max(2, min(int(min(ch, cw) * 0.08), 12))
    outer_pixels = np.concatenate([
        crop[:margin, :].reshape(-1, 3),
        crop[-margin:, :].reshape(-1, 3),
        crop[:, :margin].reshape(-1, 3),
        crop[:, -margin:].reshape(-1, 3)
    ])
    bg_median = np.median(outer_pixels, axis=0).astype(int)
    bg_color = rgb_to_hex(bg_median[2], bg_median[1], bg_median[0])
    bg_brightness = float(np.mean(bg_median))

    # 2. Obtain binary text mask based on background polarity
    if text_mask is not None and text_mask.shape == gray.shape:
        local_mask = (text_mask > 0).astype(np.uint8) * 255
    else:
        # Otsu adaptive threshold
        _, inv_thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        _, norm_thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # If background is bright (>= 128), text is darker pixels (inv_thresh)
        # If background is dark (< 128), text is lighter pixels (norm_thresh)
        local_mask = inv_thresh if bg_brightness >= 128 else norm_thresh
        
        # Guard: text mask should not overwhelm > 65% of the total box area
        if np.count_nonzero(local_mask) > (ch * cw * 0.65):
            local_mask = 255 - local_mask

    text_pixels_idx = np.where(local_mask > 0)
    bg_pixels_idx = np.where(local_mask == 0)

    # 3. Extract Text (Foreground) Color
    if len(text_pixels_idx[0]) > 10:
        fg_bgr = crop[text_pixels_idx]
        fg_median = np.median(fg_bgr, axis=0).astype(int)
        text_color = rgb_to_hex(fg_median[2], fg_median[1], fg_median[0])
    else:
        text_color = "#000000" if bg_brightness >= 128 else "#ffffff"

    # 4. Stroke & Outline Extraction
    stroke_color = None
    stroke_width = 0
    has_stroke = False

    if len(text_pixels_idx[0]) > 20:
        # Dilate mask slightly to capture outer border ring
        k_stroke = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        dilated = cv2.dilate(local_mask, k_stroke, iterations=1)
        stroke_ring = cv2.subtract(dilated, local_mask)
        stroke_pixels_idx = np.where(stroke_ring > 0)

        if len(stroke_pixels_idx[0]) > 15:
            stroke_bgr = crop[stroke_pixels_idx]
            stroke_median = np.median(stroke_bgr, axis=0).astype(int)
            fg_arr = np.array([int(text_color[5:7], 16), int(text_color[3:5], 16), int(text_color[1:3], 16)]) # BGR
            bg_arr = np.array([int(bg_color[5:7], 16), int(bg_color[3:5], 16), int(bg_color[1:3], 16)])

            dist_to_fg = np.linalg.norm(stroke_median - fg_arr)
            dist_to_bg = np.linalg.norm(stroke_median - bg_arr)

            # If stroke color differs significantly from both text and background
            if dist_to_fg > 35 and dist_to_bg > 30:
                has_stroke = True
                stroke_color = rgb_to_hex(stroke_median[2], stroke_median[1], stroke_median[0])
                stroke_width = 2
            elif dist_to_fg > 50 and dist_to_bg <= 30:
                # Text has distinct contrast with surrounding background, could have clean halo
                pass

    # 5. Estimate Rotation Angle
    rotation_deg = 0.0
    contours, _ = cv2.findContours(local_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        largest_cnt = max(contours, key=cv2.contourArea)
        if len(largest_cnt) >= 5:
            (_, _), (_, _), angle = cv2.minAreaRect(largest_cnt)
            # Normalize angle to [-45, 45] range
            if angle < -45:
                angle += 90
            elif angle > 45:
                angle -= 90
            if abs(angle) > 2.0:
                rotation_deg = round(float(angle), 1)

    return {
        "text_color": text_color,
        "bg_color": bg_color,
        "stroke_color": stroke_color,
        "stroke_width": stroke_width,
        "rotation_deg": rotation_deg,
        "has_stroke": has_stroke,
    }

