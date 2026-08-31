"""Stroke draw-through from TypesettingSpec fields (Pillow path)."""

from __future__ import annotations

from typing import Any, Sequence, Tuple


def parse_hex_rgba(hex_color: str | None, default: Tuple[int, int, int, int] = (0, 0, 0, 255)) -> Tuple[int, int, int, int]:
    if not hex_color:
        return default
    h = str(hex_color).lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        if len(h) >= 8:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16))
        if len(h) >= 6:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)
    except ValueError:
        return default
    return default


def stroke_draw_kwargs(stroke_width: float | int | None, stroke_color: str | None) -> dict[str, Any]:
    """
    Build Pillow ImageDraw.text kwargs for outline stroke from Spec fields.
    Returns empty dict when stroke is effectively off.
    """
    try:
        width = float(stroke_width or 0)
    except (TypeError, ValueError):
        width = 0.0
    if width <= 0.05:
        return {}
    # Pillow stroke_width is in pixels; Spec may store half-outline design units — use round ≥ 1
    px = max(1, int(round(width)))
    return {
        "stroke_width": px,
        "stroke_fill": parse_hex_rgba(stroke_color, default=(255, 255, 255, 255)),
    }


def draw_text_with_spec_stroke(
    draw: Any,
    xy: Sequence[float],
    text: str,
    *,
    font: Any,
    fill: Tuple[int, int, int, int],
    stroke_width: float | int | None = 0,
    stroke_color: str | None = "#ffffff",
) -> None:
    """Draw one line honoring Spec stroke_width / stroke_color when present."""
    kwargs = stroke_draw_kwargs(stroke_width, stroke_color)
    draw.text(tuple(xy), text, fill=fill, font=font, **kwargs)
