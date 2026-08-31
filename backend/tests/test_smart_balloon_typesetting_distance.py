import pytest
import numpy as np
from types import SimpleNamespace
from app.services.smart_balloon_typesetting import (
    _detect_script_density_characteristics,
    fit_text_to_smart_balloon_shape,
    compute_smart_balloon_typesetting,
)

def test_script_density_detection():
    # 1. Thai script detection (has tone marks / multi-layer vowels)
    thai_meta = _detect_script_density_characteristics('สวัสดีครับทุกคน นี่คือการทดสอบ')
    assert thai_meta['script'] == 'thai'
    assert thai_meta['line_height_ratio'] >= 1.35
    assert thai_meta['target_density_min'] <= 0.60

    # 2. CJK script detection (Japanese / Chinese)
    cjk_meta = _detect_script_density_characteristics('こんにちは世界！これはテストです。')
    assert cjk_meta['script'] == 'cjk'
    assert cjk_meta['char_width_ratio'] == 1.00

    # 3. Latin script detection (English)
    latin_meta = _detect_script_density_characteristics('Hello world, this is a test!')
    assert latin_meta['script'] == 'latin'
    assert latin_meta['char_width_ratio'] <= 0.65

def test_shape_aware_distance_transform_fitting():
    # Create elliptical balloon contour points
    cx, cy, rx, ry = 150.0, 150.0, 100.0, 80.0
    angles = np.linspace(0, 2 * np.pi, 40, endpoint=False)
    pts = [[float(cx + rx * np.cos(a)), float(cy + ry * np.sin(a))] for a in angles]

    sb = {
        'contour_points': pts,
        'center': {'x': cx, 'y': cy},
        'archetype': 'SMOOTH_OVAL',
    }

    block = SimpleNamespace(
        id='block_test_1',
        x=50.0, y=70.0, width=200.0, height=160.0,
        translation='ข้อความภาษาไทยในบอลลูนคำพูด',
        source_text='Japanese text here',
        font_family='TH Sarabun New',
        font_size=24.0,
        extra_metadata={'smart_balloon': sb},
    )

    tokens = ['ข้อความ', 'ภาษาไทย', 'ใน', 'บอลลูน', 'คำพูด']
    
    # Run shape fitting with fallback font
    result = fit_text_to_smart_balloon_shape(
        block,
        sb,
        tokens,
        font_path='tests/fixtures/dummy.ttf',
        line_height_ratio=1.35,
        min_font_size=12.0,
    )

    assert result is not None
    assert 'font_size' in result
    assert result['font_size'] >= 12.0
    assert 'density_ratio' in result
    assert result['density_ratio'] > 0.0
    assert 'safe_margin' in result
    assert result['safe_margin'] >= 3.0
    assert len(result['explicit_lines']) >= 1

def test_compute_smart_balloon_typesetting_end_to_end():
    cx, cy, rx, ry = 100.0, 100.0, 80.0, 60.0
    angles = np.linspace(0, 2 * np.pi, 30, endpoint=False)
    pts = [[float(cx + rx * np.cos(a)), float(cy + ry * np.sin(a))] for a in angles]

    sb = {
        'contour_points': pts,
        'center': {'x': cx, 'y': cy},
        'archetype': 'SMOOTH_OVAL',
    }

    block = SimpleNamespace(
        id='block_test_2',
        x=20.0, y=40.0, width=160.0, height=120.0,
        translation='สวัสดีครับ!',
        source_text='',
        font_family='TH Sarabun New',
        font_size=20.0,
        bold=False,
        italic=False,
        color_hex='#000000',
        extra_metadata={'smart_balloon': sb},
    )

    spec = compute_smart_balloon_typesetting(block, project_settings={'enable_smart_balloon': True})
    assert spec is not None
    assert spec.layout_engine_version == 'smart_balloon_v16'
    assert spec.shape_type == 'smart_balloon'
    assert spec.metrics['is_smart_balloon'] is True
    assert spec.metrics['script'] == 'thai'
