"""
Semantic / geometry parity helpers for TypesettingSpec v2.

Renderers (Canvas preview path, PNG Pillow, PSD CLI) must consume the same Spec.
These helpers compare two Spec-like dicts or models without requiring pixel match.
"""

from __future__ import annotations

from typing import Any, Mapping


def _get(obj: Any, key: str, default=None):
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def semantic_parity(a: Any, b: Any) -> tuple[bool, list[str]]:
    """
    100% semantic parity checks between two specs / export snapshots.
    """
    mismatches: list[str] = []

    def eq(field: str, left, right, tol: float | None = None):
        if tol is not None:
            try:
                if abs(float(left) - float(right)) > tol:
                    mismatches.append(f"{field}: {left!r} != {right!r}")
            except (TypeError, ValueError):
                mismatches.append(f"{field}: {left!r} != {right!r}")
            return
        if left != right:
            mismatches.append(f"{field}: {left!r} != {right!r}")

    lines_a = list(_get(a, "explicit_lines") or [])
    lines_b = list(_get(b, "explicit_lines") or [])
    eq("explicit_lines", lines_a, lines_b)
    eq("line_count", len(lines_a), len(lines_b))
    eq(
        "font_postscript",
        _get(a, "font_postscript_name") or _get(a, "resolved_postscript_name"),
        _get(b, "font_postscript_name") or _get(b, "resolved_postscript_name"),
    )
    eq("font_size", _get(a, "font_size"), _get(b, "font_size"), tol=0.01)
    eq("line_height", _get(a, "line_height"), _get(b, "line_height"), tol=0.01)
    eq("tracking", _get(a, "tracking", 0), _get(b, "tracking", 0), tol=0.01)
    eq("bold", bool(_get(a, "bold", False)), bool(_get(b, "bold", False)))
    eq("italic", bool(_get(a, "italic", False)), bool(_get(b, "italic", False)))

    color_a = str(_get(a, "color_hex") or "").lower().lstrip("#")
    color_b = str(_get(b, "color_hex") or "").lower().lstrip("#")
    if color_a and color_b:
        eq("color_hex", color_a, color_b)

    stroke_a = float(_get(a, "stroke_width") or 0)
    stroke_b = float(_get(b, "stroke_width") or 0)
    eq("stroke_width", stroke_a, stroke_b, tol=0.01)
    eq(
        "stroke_color",
        str(_get(a, "stroke_color") or "").lower(),
        str(_get(b, "stroke_color") or "").lower(),
    )
    eq(
        "text_align",
        _get(a, "text_align") or _get(a, "horizontal_align"),
        _get(b, "text_align") or _get(b, "horizontal_align"),
    )
    eq("vertical_align", _get(a, "vertical_align"), _get(b, "vertical_align"))
    eq("writing_direction", _get(a, "writing_direction"), _get(b, "writing_direction"))
    eq("rotation_deg", _get(a, "rotation_deg", 0), _get(b, "rotation_deg", 0), tol=0.01)

    return (len(mismatches) == 0, mismatches)


def geometry_parity(
    a: Any,
    b: Any,
    *,
    center_tol_px: float = 2.0,
    center_tol_frac: float = 0.01,
) -> tuple[bool, list[str]]:
    """
    Center of layout_region within max(2px, 1% of box).
    """
    mismatches: list[str] = []
    ra = _get(a, "layout_region") or {}
    rb = _get(b, "layout_region") or {}
    if not isinstance(ra, Mapping):
        ra = {
            "x": _get(ra, "x", 0),
            "y": _get(ra, "y", 0),
            "width": _get(ra, "width", 0),
            "height": _get(ra, "height", 0),
        }
    if not isinstance(rb, Mapping):
        rb = {
            "x": _get(rb, "x", 0),
            "y": _get(rb, "y", 0),
            "width": _get(rb, "width", 0),
            "height": _get(rb, "height", 0),
        }

    ax = float(ra.get("x", 0)) + float(ra.get("width", 0)) / 2
    ay = float(ra.get("y", 0)) + float(ra.get("height", 0)) / 2
    bx = float(rb.get("x", 0)) + float(rb.get("width", 0)) / 2
    by = float(rb.get("y", 0)) + float(rb.get("height", 0)) / 2
    box = max(float(ra.get("width", 0)), float(ra.get("height", 0)), 1.0)
    tol = max(center_tol_px, center_tol_frac * box)
    if abs(ax - bx) > tol or abs(ay - by) > tol:
        mismatches.append(f"center: ({ax:.2f},{ay:.2f}) vs ({bx:.2f},{by:.2f}) tol={tol:.2f}")
    return (len(mismatches) == 0, mismatches)


def build_export_view_from_spec(spec: Any) -> dict[str, Any]:
    """Canonical fields a renderer/export must honor — single source of truth."""
    region = _get(spec, "layout_region")
    if hasattr(region, "model_dump"):
        region = region.model_dump()
    padding = _get(spec, "padding")
    if hasattr(padding, "model_dump"):
        padding = padding.model_dump()
    return {
        "explicit_lines": list(_get(spec, "explicit_lines") or []),
        "font_postscript_name": _get(spec, "font_postscript_name")
        or _get(spec, "resolved_postscript_name"),
        "font_fingerprint": _get(spec, "font_fingerprint"),
        "font_size": _get(spec, "font_size"),
        "line_height": _get(spec, "line_height"),
        "tracking": float(_get(spec, "tracking") or 0),
        "bold": bool(_get(spec, "bold", False)),
        "italic": bool(_get(spec, "italic", False)),
        "color_hex": _get(spec, "color_hex"),
        "stroke_width": float(_get(spec, "stroke_width") or 0),
        "stroke_color": _get(spec, "stroke_color"),
        "text_align": _get(spec, "text_align") or _get(spec, "horizontal_align"),
        "vertical_align": _get(spec, "vertical_align"),
        "writing_direction": _get(spec, "writing_direction"),
        "rotation_deg": float(_get(spec, "rotation_deg") or 0),
        "layout_region": region,
        "padding": padding,
        "render_fingerprint": _get(spec, "render_fingerprint"),
        "schema_version": _get(spec, "schema_version"),
        "decision_status": _get(spec, "decision_status"),
    }
