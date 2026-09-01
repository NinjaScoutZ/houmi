"""
Houmi Studio - Script-Aware Semantic & Visual Font Matcher
Selects optimal font families, styles, weights, and letter-spacings
based on balloon archetypes, script characteristics (Thai, Latin, CJK), and comic mood.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Any, Optional, List


@dataclass
class FontStyleRecommendation:
    font_family: str
    font_weight: int          # 300..900
    is_italic: bool
    line_height_multiplier: float
    letter_spacing_px: float
    recommended_font_size_pt: float
    archetype: str
    confidence: float


class ComicFontMatcher:
    """
    Script-aware font matching engine for Manga, Manhwa, and Webtoons.
    """

    # Font palettes mapped by language script and balloon archetype
    PALETTES: Dict[str, Dict[str, List[str]]] = {
        "th": {
            "shout": ["Prompt", "Kanit", "MangaImpact-Thai", "FC Iconic", "Impact"],
            "bubble": ["Prompt", "Mitr", "Kanit", "Noto Sans Thai"],
            "thought": ["Sarabun", "Chakra Petch", "Prompt"],
            "narration": ["Sarabun", "Prompt", "Noto Serif Thai"],
            "whisper": ["Sarabun", "Mitr", "Prompt"],
            "sfx": ["Kanit", "Prompt", "Impact"],
            "system": ["Prompt", "Kanit"],
        },
        "en": {
            "shout": ["CCWildWords", "Bangers", "Komika Axis", "Impact"],
            "bubble": ["CCWildWords", "Anime Ace", "Manga Temple", "Arial"],
            "thought": ["Anime Ace", "Komika Text", "Comic Sans MS"],
            "narration": ["Helvetica", "Times New Roman", "Anime Ace"],
            "whisper": ["Anime Ace", "Calibri"],
            "sfx": ["Impact", "Bangers", "CCWildWords"],
            "system": ["Arial", "Roboto"],
        },
        "ja": {
            "shout": ["MS Gothic", "Yu Gothic", "Hiragino Kaku Gothic Pro"],
            "bubble": ["MS Mincho", "Yu Mincho", "Hiragino Mincho Pro"],
            "thought": ["MS Mincho", "Yu Mincho"],
            "narration": ["MS Mincho", "Yu Mincho"],
            "whisper": ["MS Gothic"],
            "sfx": ["MS Gothic", "Impact"],
            "system": ["MS Gothic"],
        }
    }

    @classmethod
    def detect_script(cls, text: str) -> str:
        """Detects primary script: 'th' (Thai), 'ja' (Japanese), 'ko' (Korean), or 'en' (Latin)."""
        if not text:
            return "en"
        
        # Thai unicode range
        if re.search(r'[\u0E00-\u0E7F]', text):
            return "th"
        # Japanese (Hiragana/Katakana/Kanji)
        if re.search(r'[\u3040-\u30FF\u4E00-\u9FFF]', text):
            return "ja"
        # Korean Hangul
        if re.search(r'[\uAC00-\uD7AF\u1100-\u11FF]', text):
            return "ko"
        
        return "en"

    @classmethod
    def match_font_style(
        cls,
        text: str,
        balloon_type: str = "bubble",
        width_px: float = 150.0,
        height_px: float = 100.0,
        source_lang: Optional[str] = None,
        target_lang: str = "th",
    ) -> FontStyleRecommendation:
        """
        Calculates recommended font styling specification.
        """
        script = target_lang.lower() if target_lang else cls.detect_script(text)
        if script not in cls.PALETTES:
            script = "th" if cls.detect_script(text) == "th" else "en"

        b_type = (balloon_type or "bubble").lower().strip()
        if b_type not in cls.PALETTES[script]:
            b_type = "bubble"

        candidate_fonts = cls.PALETTES[script][b_type]
        selected_family = candidate_fonts[0]

        # Determine typography weights and stylistic rules
        weight = 400
        is_italic = False
        line_height = 1.25
        letter_spacing = 0.0

        if b_type == "shout":
            weight = 700
            line_height = 1.15
            letter_spacing = -0.5
        elif b_type == "thought" or b_type == "whisper":
            weight = 300
            is_italic = True
            line_height = 1.30
        elif b_type == "narration":
            weight = 500
            line_height = 1.25
        elif b_type == "sfx":
            weight = 800
            line_height = 1.0
            letter_spacing = 1.0

        # Adjust for Thai vertical marks
        if script == "th":
            line_height = max(line_height, 1.35)

        # Estimate optimal font size to fit bounding box
        char_count = max(1, len(text))
        aspect_ratio = width_px / max(1.0, height_px)
        approx_area = width_px * height_px
        est_font_size = max(11.0, min(36.0, (approx_area / (char_count * 1.8)) ** 0.5))

        return FontStyleRecommendation(
            font_family=selected_family,
            font_weight=weight,
            is_italic=is_italic,
            line_height_multiplier=line_height,
            letter_spacing_px=letter_spacing,
            recommended_font_size_pt=round(est_font_size, 1),
            archetype=b_type,
            confidence=0.95,
        )
