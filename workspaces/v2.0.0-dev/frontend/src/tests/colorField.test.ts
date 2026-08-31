import { describe, expect, test } from 'vitest';
import { hexToRgb, hsbToRgb, normalizeHex, normalizeStoredHex, rgbToHex, rgbToHsb } from '../utils/color';

describe('ColorField color conversions', () => {
  test('normalizes complete six-digit hex values only', () => {
    expect(normalizeHex(' A1b2C3 ')).toBe('#a1b2c3');
    expect(normalizeHex('#FFFFFF')).toBe('#ffffff');
    expect(normalizeHex('#fff')).toBeNull();
    expect(normalizeHex('gg0000')).toBeNull();
    expect(normalizeStoredHex('#fff')).toBe('#ffffff');
  });

  test('converts between hex and RGB with bounded channels', () => {
    expect(hexToRgb('#1234ab')).toEqual({ r: 18, g: 52, b: 171 });
    expect(hexToRgb('invalid')).toBeNull();
    expect(rgbToHex({ r: 300, g: -20, b: 127.6 })).toBe('#ff0080');
  });

  test('converts canonical HSB hues to RGB', () => {
    expect(hsbToRgb({ h: 0, s: 100, b: 100 })).toEqual({ r: 255, g: 0, b: 0 });
    expect(hsbToRgb({ h: 120, s: 100, b: 100 })).toEqual({ r: 0, g: 255, b: 0 });
    expect(hsbToRgb({ h: 240, s: 100, b: 100 })).toEqual({ r: 0, g: 0, b: 255 });
    expect(hsbToRgb({ h: 360, s: 100, b: 100 })).toEqual({ r: 255, g: 0, b: 0 });
  });

  test('reports Photoshop-style hue, saturation, and brightness ranges', () => {
    expect(rgbToHsb({ r: 255, g: 0, b: 0 })).toEqual({ h: 0, s: 100, b: 100 });
    expect(rgbToHsb({ r: 128, g: 128, b: 128 })).toMatchObject({ h: 0, s: 0 });
    expect(rgbToHsb({ r: 128, g: 128, b: 128 }).b).toBeCloseTo(50.196, 3);
  });

  test.each(['#000000', '#ffffff', '#123456', '#ff7f00', '#31c7a2', '#8b5cf6'])(
    'round-trips %s through HSB without channel drift',
    (hex) => {
      const rgb = hexToRgb(hex);
      expect(rgb).not.toBeNull();
      expect(rgbToHex(hsbToRgb(rgbToHsb(rgb!)))).toBe(hex);
    },
  );
});
