import pytest
from app.services.typesetting.segmentation import segment_text
from app.services.smart_balloon_typesetting import fit_text_to_smart_balloon_shape

def test_short_thai_exclamation_optical_scale_and_single_line():
    """
    Tests that short words like 'ฮู้ว...' are not split across lines
    and scale to a visually balanced optical font size.
    """
    text = "ฮู้ว..."
    tokens = segment_text(text)
    sb = {"safe_bbox": {"x": 0, "y": 0, "width": 300, "height": 150}, "center": {"x": 150, "y": 75}}
    
    # Run shape fitting with default font fallback
    res = fit_text_to_smart_balloon_shape(None, sb, tokens, "C:/Windows/Fonts/tahoma.ttf")
    
    assert res is not None, "Fitting must return a valid layout"
    assert res["explicit_lines"] == ["ฮู้ว..."], f"Expected single line, got {res['explicit_lines']}"
    assert res["font_size"] >= 50.0, f"Font size should be optically scaled (>= 50), got {res['font_size']}"

def test_thai_multi_line_keeps_words_intact_case1():
    """
    Tests that 'ยัยผู้หญิงคนนี้ เป็นไปได้ยังไง...' never splits 'ยังไง' across lines.
    """
    text = "ยัยผู้หญิงคนนี้ เป็นไปได้ยังไงที่จะมีการควบคุมบัลลังก์ที่แข็งแกร่งขนาดนี้!"
    tokens = segment_text(text)
    sb = {"safe_bbox": {"x": 0, "y": 0, "width": 280, "height": 260}, "center": {"x": 140, "y": 130}}
    
    res = fit_text_to_smart_balloon_shape(None, sb, tokens, "C:/Windows/Fonts/tahoma.ttf")
    
    assert res is not None
    lines = res["explicit_lines"]
    
    # Confirm 'ยังไง' is fully intact on one line, never split into 'ยังไ' and 'ง'
    assert any("ยังไง" in line for line in lines), f"'ยังไง' must remain together in one line. Lines: {lines}"
    assert not any(line.endswith("ยังไ") for line in lines), f"Line must not end with broken 'ยังไ'. Lines: {lines}"

def test_thai_multi_line_keeps_words_intact_case2():
    """
    Tests that 'ส่วนอีกสองบัลลังก์ที่เหลือ ค่อยเก็บไว้ก่อนแล้วกัน' never splits 'ค่อยเก็บ'.
    """
    text = "ส่วนอีกสองบัลลังก์ที่เหลือ ค่อยเก็บไว้ก่อนแล้วกัน"
    tokens = segment_text(text)
    sb = {"safe_bbox": {"x": 0, "y": 0, "width": 300, "height": 160}, "center": {"x": 150, "y": 80}}
    
    res = fit_text_to_smart_balloon_shape(None, sb, tokens, "C:/Windows/Fonts/tahoma.ttf")
    
    assert res is not None
    lines = res["explicit_lines"]
    
    # Confirm 'ค่อยเก็บ' is fully intact on one line, never split into 'ค่อยเ' and 'ก็บ'
    assert any("ค่อยเก็บ" in line for line in lines), f"'ค่อยเก็บ' must remain together in one line. Lines: {lines}"
    assert not any(line.endswith("ค่อยเ") for line in lines), f"Line must not end with broken 'ค่อยเ'. Lines: {lines}"
