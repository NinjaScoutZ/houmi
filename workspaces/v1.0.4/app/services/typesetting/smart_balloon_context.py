"""
Smart Balloon Spatial Context Service.

Provides spatial perception and contour geometry context for AI models (Gemini, Web LLMs, prompts)
so external and backend AI services can understand speech balloon shape, aspect ratio, line capacities,
and assist in breaking lines to fit speech balloons naturally.
"""
from __future__ import annotations

import math
import unicodedata
from typing import Any, Optional


def build_smart_balloon_spatial_context(block: Any, settings: Optional[dict] = None) -> dict:
    """
    Computes spatial context for a text block including contour bounds, aspect ratio,
    line capacity profile, and AI-formatted hint string.
    """
    settings = settings or {}
    meta = getattr(block, "extra_metadata", None) or {}

    # 1. Determine bounding dimensions (prefer Smart Balloon bounds if available, fallback to block bbox)
    smart_w = float(getattr(block, "smart_width", 0) or 0)
    smart_h = float(getattr(block, "smart_height", 0) or 0)
    block_w = float(getattr(block, "width", 0) or 0)
    block_h = float(getattr(block, "height", 0) or 0)

    width = smart_w if smart_w > 0 else block_w
    height = smart_h if smart_h > 0 else block_h
    width = max(20.0, width)
    height = max(20.0, height)

    aspect_ratio = round(width / height, 2)

    # 2. Shape classification
    balloon_type = str(getattr(block, "balloon_type", None) or "bubble").lower()
    if balloon_type in {"sfx", "free"}:
        shape_category = "free"
    elif balloon_type in {"narrative", "caption", "box", "rectangle"}:
        shape_category = "rectangle"
    else:
        if aspect_ratio >= 1.4:
            shape_category = "wide_oval"
        elif aspect_ratio <= 0.75:
            shape_category = "tall_oval"
        elif 0.85 <= aspect_ratio <= 1.15:
            shape_category = "round_bubble"
        else:
            shape_category = "ellipse"

    # 3. Line capacity & target lines estimation
    minimum_size = max(12.0, float(meta.get("min_font_size") or settings.get("min_font_size") or 24.0))
    preferred_size = max(minimum_size, float(meta.get("preferred_font_size") or getattr(block, "font_size", 0) or 42.0))
    line_height_ratio = max(0.8, float(meta.get("line_height_ratio") or 1.25))

    effective_h = height * 0.85  # Account for margin
    max_lines = max(1, min(8, int(effective_h // (minimum_size * line_height_ratio))))

    # Target line count calculation based on visual units of text
    raw_text = (getattr(block, "translation", None) or getattr(block, "source_text", None) or "").strip()
    visual_units = sum(1 for c in raw_text if not c.isspace() and not unicodedata.combining(c))

    width_factor = 0.78 if shape_category != "rectangle" else 0.92
    units_per_line = max(4.0, width * width_factor / max(1.0, preferred_size * 0.52))
    target_lines = max(1, min(max_lines, int(math.ceil(visual_units / units_per_line)) if visual_units > 0 else 3))

    # 4. Shape line pattern advice for AI models
    if shape_category in {"wide_oval", "ellipse", "round_bubble", "tall_oval"}:
        pattern = "Short-Long-Long-Short" if target_lines >= 3 else "Short-Long"
    else:
        pattern = "Uniform"

    # 5. Format standardized AI Prompt Tag
    ai_tag = (
        f"[[SMART_BALLOON_SPATIAL shape={shape_category} aspect={aspect_ratio} "
        f"w={int(width)} h={int(height)} target_lines={target_lines} max_lines={max_lines} "
        f"pattern={pattern}]]"
    )

    return {
        "shape": shape_category,
        "width": width,
        "height": height,
        "aspect_ratio": aspect_ratio,
        "target_lines": target_lines,
        "max_lines": max_lines,
        "pattern": pattern,
        "ai_tag": ai_tag,
    }


def parse_smart_balloon_spatial_tag(value: str) -> Optional[dict]:
    """
    Parses an AI-generated or prompt tag string containing spatial balloon context.
    """
    import re
    match = re.search(
        r"\[\[SMART_BALLOON_SPATIAL\s+"
        r"shape=([a-z_]+)\s+"
        r"aspect=([0-9.]+)\s+"
        r"w=(\d+)\s+h=(\d+)\s+"
        r"target_lines=(\d+)\s+max_lines=(\d+)"
        r"(?:\s+pattern=([A-Za-z-]+))?\]\]",
        value.strip(),
    )
    if not match:
        return None

    return {
        "shape": match.group(1),
        "aspect_ratio": float(match.group(2)),
        "width": int(match.group(3)),
        "height": int(match.group(4)),
        "target_lines": int(match.group(5)),
        "max_lines": int(match.group(6)),
        "pattern": match.group(7) or "Uniform",
    }
