import { describe, expect, test } from 'vitest';
import {
  isAutoFontSizeEnabled,
  resolveOuterLayoutRegion,
  resolvePaddedTextRegion,
} from '../utils/fontSizing';

describe('font size mode', () => {
  test('enables auto mode for explicit and legacy auto blocks', () => {
    expect(isAutoFontSizeEnabled({ extra_metadata: { font_size_mode: 'auto' } } as any)).toBe(true);
    expect(isAutoFontSizeEnabled({ extra_metadata: {} } as any)).toBe(true);
  });

  test('keeps manual and fixed template sizes unchanged', () => {
    expect(isAutoFontSizeEnabled({ extra_metadata: { font_size_mode: 'manual' } } as any)).toBe(false);
    expect(isAutoFontSizeEnabled({ extra_metadata: { font_size_mode: 'fixed' } } as any)).toBe(false);
    expect(isAutoFontSizeEnabled({ extra_metadata: { auto_font_size: false } } as any)).toBe(false);
  });
});

describe('padded text geometry', () => {
  test('uses the canonical inner box and round-trips the balloon bounds', () => {
    const outer = { x: 100, y: 200, width: 240, height: 120 };
    const padding = { top: 12, right: 18, bottom: 12, left: 18 };

    const inner = resolvePaddedTextRegion(outer, padding);
    expect(inner).toEqual({ x: 118, y: 212, width: 204, height: 96 });
    expect(resolveOuterLayoutRegion(inner, padding)).toEqual(outer);
  });

  test('rotates the padding offset with the text box', () => {
    const outer = { x: 100, y: 200, width: 240, height: 120 };
    const padding = { top: 10, right: 20, bottom: 10, left: 20 };

    const inner = resolvePaddedTextRegion(outer, padding, 90);
    expect(inner.x).toBeCloseTo(120);
    expect(inner.y).toBeCloseTo(210);
    expect(resolveOuterLayoutRegion(inner, padding, 90)).toEqual(outer);
  });
});
