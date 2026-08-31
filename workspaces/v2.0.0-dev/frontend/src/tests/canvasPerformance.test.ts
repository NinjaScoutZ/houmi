import { describe, expect, it } from 'vitest';
import {
  fitCanvasWorkingDimensions,
  resolveCanvasControlMetrics,
  resolveCanvasPixelBudget,
  resolveCanvasRetinaScale,
  resolveCanvasZoomRetinaScale,
} from '../utils/canvasPerformance';

describe('canvas working resolution', () => {
  it('keeps normal manga pages at native preview resolution', () => {
    expect(fitCanvasWorkingDimensions(1200, 1800, 6_000_000)).toMatchObject({
      width: 1200,
      height: 1800,
      downsampled: false,
    });
  });

  it('bounds tall webtoon backing canvases while preserving aspect ratio', () => {
    const result = fitCanvasWorkingDimensions(1200, 18750, 6_000_000);
    expect(result.downsampled).toBe(true);
    expect(result.width * result.height).toBeLessThanOrEqual(6_010_000);
    expect(result.width / result.height).toBeCloseTo(1200 / 18750, 3);
  });

  it('gives performance mode a larger budget than balanced and eco', () => {
    expect(resolveCanvasPixelBudget('performance')).toBeGreaterThan(resolveCanvasPixelBudget('balanced'));
    expect(resolveCanvasPixelBudget('balanced')).toBeGreaterThan(resolveCanvasPixelBudget('eco'));
  });

  it('caps custom mode so user settings cannot recreate an unbounded canvas', () => {
    expect(resolveCanvasPixelBudget('custom', 99999)).toBe(12_000_000);
  });

  it('keeps eco at 1x while bounding crisp text rendering in stronger profiles', () => {
    expect(resolveCanvasRetinaScale('eco', 2.5)).toBe(1);
    expect(resolveCanvasRetinaScale('balanced', 2.5)).toBe(1.5);
    expect(resolveCanvasRetinaScale('performance', 2.5)).toBe(2);
    expect(resolveCanvasRetinaScale('performance', 1)).toBe(1);
  });

  it('raises backing resolution with visible zoom without unbounded allocation', () => {
    expect(resolveCanvasZoomRetinaScale('balanced', 1, 1)).toBe(1);
    expect(resolveCanvasZoomRetinaScale('balanced', 1, 1.75)).toBe(1.75);
    expect(resolveCanvasZoomRetinaScale('balanced', 2, 6)).toBe(2);
    expect(resolveCanvasZoomRetinaScale('performance', 1, 6)).toBe(2.5);
  });

  it('keeps balloon controls at a stable screen size while zooming', () => {
    const normal = resolveCanvasControlMetrics(1);
    const zoomed = resolveCanvasControlMetrics(4);

    expect(normal.cornerSize).toBe(9);
    expect(zoomed.cornerSize * 4).toBe(9);
    expect(zoomed.touchCornerSize * 4).toBe(24);
    expect(zoomed.borderScaleFactor * 4).toBe(1.25);
  });
});
