import pytest
from app.services.typesetting.segmentation import segment_text

def test_thai_long_compound_syllable_segmentation():
    # Long Thai compound noun
    text = "ผู้บัญชาการทหารสูงสุดกำลังเดินทางมา"
    tokens = segment_text(text)

    assert len(tokens) >= 2
    # Ensure total text joins back to original without loss
    assert "".join(tokens) == text

def test_thai_idiom_segmentation():
    text = "ทุกคนมารวมตัวกันอย่างพร้อมหน้าพร้อมตา"
    tokens = segment_text(text)

    assert "".join(tokens) == text
    assert any("พร้อม" in t for t in tokens)
