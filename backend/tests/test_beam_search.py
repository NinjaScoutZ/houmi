import pytest
from app.services.typesetting.beam_search import (
    TypesettingBeamSearchOptimizer,
    LineBreakState
)

def test_beam_search_latin_paragraph_wrapping():
    optimizer = TypesettingBeamSearchOptimizer(beam_width=5)
    tokens = ["This", "is", "a", "clean", "speech", "balloon", "dialogue", "test", "for", "manga"]
    allowed_widths = [120.0, 140.0, 120.0]
    
    # Simple monospace measurement function
    def measure_fn(text: str) -> float:
        return float(len(text) * 10.0)

    lines = optimizer.optimize_line_breaks(
        tokens=tokens,
        allowed_widths=allowed_widths,
        measure_text_fn=measure_fn
    )

    assert len(lines) > 0
    # Total joined text must equal original words
    assert " ".join(lines) == " ".join(tokens)
    # Check that no line exceeds allowed width significantly
    for idx, line in enumerate(lines):
        assert measure_fn(line) <= allowed_widths[min(idx, len(allowed_widths) - 1)] + 10.0

def test_beam_search_thai_word_boundary_wrapping():
    optimizer = TypesettingBeamSearchOptimizer(beam_width=5)
    tokens = ["สวัสดี", "ครับ", "นี่คือ", "การทดสอบ", "ตัดคำ", "ภาษาไทย"]
    allowed_widths = [80.0, 100.0, 80.0]

    def measure_thai_fn(text: str) -> float:
        return float(len(text) * 8.0)

    lines = optimizer.optimize_line_breaks(
        tokens=tokens,
        allowed_widths=allowed_widths,
        measure_text_fn=measure_thai_fn
    )

    assert len(lines) > 0
    # Joined Thai lines must not have extra spaces between Thai syllables
    joined_text = "".join(lines)
    assert joined_text == "".join(tokens)
