import pytest
from app.services.font_matcher import ComicFontMatcher, FontStyleRecommendation

def test_script_detection():
    assert ComicFontMatcher.detect_script("ทดสอบภาษาไทย") == "th"
    assert ComicFontMatcher.detect_script("English comic dialogue") == "en"
    assert ComicFontMatcher.detect_script("こんにちは") == "ja"
    assert ComicFontMatcher.detect_script("안녕하세요") == "ko"

def test_font_style_matching_shout_vs_whisper():
    shout_rec = ComicFontMatcher.match_font_style("อย่านะ!", balloon_type="shout", target_lang="th")
    assert shout_rec.font_weight >= 700
    assert shout_rec.is_italic is False

    whisper_rec = ComicFontMatcher.match_font_style("แอบบอกหน่อย...", balloon_type="whisper", target_lang="th")
    assert whisper_rec.font_weight <= 400
    assert whisper_rec.is_italic is True
    assert whisper_rec.line_height_multiplier >= 1.35  # Thai safe leading
