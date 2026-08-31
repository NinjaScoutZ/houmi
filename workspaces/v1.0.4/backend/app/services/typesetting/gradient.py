"""Deterministic Photoshop-style gradient generation for canonical text fills."""
from __future__ import annotations

import math
from typing import Any

from PIL import Image

from .schemas import GradientSpec
from .stroke import parse_hex_rgba


def _stops(spec: GradientSpec):
    stops = sorted(spec.stops, key=lambda s: float(s.position)) or []
    if len(stops) == 1:
        stops = [stops[0], stops[0].model_copy(update={"position": 1.0})]
    if spec.reverse:
        stops = [s.model_copy(update={"position": 1.0 - float(s.position)}) for s in reversed(stops)]
    return stops


def _sample(spec: GradientSpec, t: float):
    stops = _stops(spec)
    t = max(0.0, min(1.0, t))
    left, right = stops[0], stops[-1]
    for a, b in zip(stops, stops[1:]):
        if t <= float(b.position):
            left, right = a, b
            break
    span = max(1e-6, float(right.position) - float(left.position))
    u = max(0.0, min(1.0, (t - float(left.position)) / span))
    ca = parse_hex_rgba(left.color)
    cb = parse_hex_rgba(right.color)
    opacity_a = max(0.0, min(1.0, float(left.opacity)))
    opacity_b = max(0.0, min(1.0, float(right.opacity)))
    alpha = round((ca[3] * opacity_a + (cb[3] * opacity_b - ca[3] * opacity_a) * u) * max(0.0, min(1.0, float(spec.opacity))))
    return tuple(round(ca[i] + (cb[i] - ca[i]) * u) for i in range(3)) + (alpha,)


def gradient_image(width: int, height: int, spec: GradientSpec) -> Image.Image:
    """Return an RGBA gradient in local text-box coordinates.

    The coordinate model matches Photoshop's object-aligned gradient: angle is
    measured clockwise from left-to-right, scale changes the gradient span, and
    non-linear modes use the box centre.
    """
    width, height = max(1, int(width)), max(1, int(height))
    try:
        import numpy as np
        yy, xx = np.mgrid[0:height, 0:width]
        nx = (xx + 0.5) / width * 2.0 - 1.0
        ny = (yy + 0.5) / height * 2.0 - 1.0
        angle = math.radians(float(spec.angle_deg))
        ca, sa = math.cos(angle), math.sin(angle)
        linear = ((nx * ca) + (ny * sa)) * 0.5 + 0.5
        scale = max(1e-3, float(spec.scale) / 100.0)
        linear = (linear - 0.5) / scale + 0.5
        kind = spec.type
        if kind == "radial":
            value = np.sqrt(nx * nx + ny * ny) / math.sqrt(2.0)
        elif kind == "angle":
            value = (np.arctan2(ny, nx) - angle) / (2.0 * math.pi) + 0.5
        elif kind == "reflected":
            value = np.abs(linear * 2.0 - 1.0)
        elif kind == "diamond":
            value = np.maximum(np.abs(nx), np.abs(ny))
        else:
            value = linear
        value = np.clip(value, 0.0, 1.0)
        out = np.zeros((height, width, 4), dtype=np.uint8)
        stops = _stops(spec)
        # Interpolate each channel by stop intervals without per-pixel Python loops.
        for y in range(height):
            for x in range(width):
                out[y, x] = _sample(spec, float(value[y, x]))
        return Image.fromarray(out, "RGBA")
    except ImportError:  # pragma: no cover - numpy is bundled in production
        image = Image.new("RGBA", (width, height))
        px = image.load()
        for y in range(height):
            for x in range(width):
                nx, ny = (x + 0.5) / width * 2 - 1, (y + 0.5) / height * 2 - 1
                value = ((nx * math.cos(math.radians(spec.angle_deg))) + (ny * math.sin(math.radians(spec.angle_deg)))) / 2 + 0.5
                px[x, y] = _sample(spec, value)
        return image
