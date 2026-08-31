"""Canonical grapheme-aware tracking helpers shared by fitting and rendering."""

from __future__ import annotations

import unicodedata
from typing import Iterator


_ZWJ = "\u200d"


def _is_variation_selector(char: str) -> bool:
    codepoint = ord(char)
    return 0xFE00 <= codepoint <= 0xFE0F or 0xE0100 <= codepoint <= 0xE01EF


def _is_emoji_modifier(char: str) -> bool:
    return 0x1F3FB <= ord(char) <= 0x1F3FF


def _is_regional_indicator(char: str) -> bool:
    return 0x1F1E6 <= ord(char) <= 0x1F1FF


def split_grapheme_clusters(text: str) -> list[str]:
    """
    Split text into display clusters for tracking.

    This deliberately covers the Unicode cases relevant to Houmi without adding
    another runtime dependency: combining marks (including Thai tone/vowel
    marks), variation selectors, emoji modifiers, ZWJ sequences, CRLF, and
    regional-indicator pairs. It mirrors the browser's ``Intl.Segmenter`` much
    more closely than iterating Python code points.
    """
    clusters: list[str] = []
    regional_run = 0

    for char in text:
        if not clusters:
            clusters.append(char)
            regional_run = 1 if _is_regional_indicator(char) else 0
            continue

        category = unicodedata.category(char)
        previous = clusters[-1]
        attach = (
            category in {"Mn", "Mc", "Me"}
            or _is_variation_selector(char)
            or _is_emoji_modifier(char)
            or char == _ZWJ
            or previous.endswith(_ZWJ)
            or (previous == "\r" and char == "\n")
        )

        if _is_regional_indicator(char):
            if regional_run % 2 == 1:
                attach = True
            regional_run += 1
        else:
            regional_run = 0

        if attach:
            clusters[-1] += char
        else:
            clusters.append(char)

    return clusters


def tracking_spacing_px(font_size: float, tracking: float) -> float:
    """Convert Fabric/Photoshop tracking (thousandths of an em) to pixels."""
    return float(font_size) * (float(tracking) / 1000.0)


def measure_text_with_tracking(font, text: str, font_size: float, tracking: float = 0.0) -> float:
    """Measure visual line width plus tracking gaps between grapheme clusters."""
    if not text:
        return 0.0
    try:
        bbox = font.getbbox(text)
        width = float(bbox[2] - bbox[0])
    except Exception:
        try:
            width = float(font.getlength(text))
        except Exception:
            width = float(len(split_grapheme_clusters(text)) * font_size * 0.6)

    clusters = split_grapheme_clusters(text)
    if tracking and len(clusters) > 1:
        width += (len(clusters) - 1) * tracking_spacing_px(font_size, tracking)
    return width


def iter_tracked_graphemes(
    font,
    text: str,
    font_size: float,
    tracking: float,
) -> Iterator[tuple[str, float]]:
    """
    Yield ``(cluster, x_offset)`` while preserving the font's prefix advances.

    Prefix measurement retains kerning advances between clusters; each yielded
    cluster keeps Thai/Indic combining marks attached to its base glyph.
    """
    clusters = split_grapheme_clusters(text)
    spacing = tracking_spacing_px(font_size, tracking)
    prefix = ""
    fallback_advance = 0.0

    for index, cluster in enumerate(clusters):
        if index == 0:
            offset = 0.0
        else:
            try:
                offset = float(font.getlength(prefix)) + index * spacing
            except Exception:
                offset = fallback_advance + index * spacing
        yield cluster, offset
        prefix += cluster
        try:
            fallback_advance = float(font.getlength(prefix))
        except Exception:
            fallback_advance += float(font_size) * 0.6
