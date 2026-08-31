import { describe, expect, test } from 'vitest';
import { binaryMaskToOverlay, PAGE_MASK_COLOR, pointerToCanvasPoint, resolveMaskWorkingDimensions, shouldEraseMask } from '../utils/pageMaskCanvas';

describe('page mask canvas contract', () => {
  test('renders only selected grayscale pixels as a transparent red overlay', () => {
    const image = { data: new Uint8ClampedArray([
      0, 0, 0, 255,
      255, 255, 255, 255,
      20, 20, 20, 0,
    ]) } as ImageData;

    const overlay = binaryMaskToOverlay(image).data;

    expect(Array.from(overlay.slice(0, 4))).toEqual([PAGE_MASK_COLOR.red, PAGE_MASK_COLOR.green, PAGE_MASK_COLOR.blue, 0]);
    expect(Array.from(overlay.slice(4, 8))).toEqual([PAGE_MASK_COLOR.red, PAGE_MASK_COLOR.green, PAGE_MASK_COLOR.blue, PAGE_MASK_COLOR.alpha]);
    expect(overlay[11]).toBe(0);
  });

  test('maps viewport coordinates into full-resolution mask coordinates', () => {
    const point = pointerToCanvasPoint(60, 120, { left: 10, top: 20, width: 200, height: 400 }, 1000, 2000);
    expect(point).toEqual({ x: 250, y: 500 });
  });

  test('uses right click as a temporary eraser like the block Mask Editor', () => {
    expect(shouldEraseMask('brush', 0)).toBe(false);
    expect(shouldEraseMask('brush', 2)).toBe(true);
    expect(shouldEraseMask('box', 2)).toBe(true);
    expect(shouldEraseMask('eraser', 0)).toBe(true);
  });

  test('caps the interactive backing canvas while preserving aspect ratio', () => {
    const dimensions = resolveMaskWorkingDimensions(800, 14000, 4_000_000);
    expect(dimensions.height).toBeLessThan(14000);
    expect(dimensions.width / dimensions.height).toBeCloseTo(800 / 14000, 3);
    expect(dimensions.width * dimensions.height).toBeLessThanOrEqual(4_000_000);
  });
});
