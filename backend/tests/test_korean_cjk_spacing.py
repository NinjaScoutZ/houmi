import pytest
from app.services.typesetting.segmentation import segment_text
from app.services.typesetting.fitting import join_tokens

def test_korean_word_segmentation_and_joining():
    text = "안녕하세요 반갑습니다"
    tokens = segment_text(text)

    # Korean words should remain intact without breaking into individual Hangul letters
    assert "안녕하세요" in tokens
    assert "반갑습니다" in tokens

    # Joined text should preserve the space between words and no extra spaces
    joined = join_tokens(tokens)
    assert joined == text

def test_cjk_kanji_kana_joining():
    text = "こんにちは 世界"
    tokens = segment_text(text)
    joined = join_tokens(tokens)
    assert joined == text
