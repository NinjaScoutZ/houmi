// @vitest-environment jsdom
import { describe, expect, test } from 'vitest';
import * as fabric from 'fabric';

describe('Balloon Canvas Scaling Behavior', () => {
  test('Fabric Canvas allows free non-uniform balloon scaling when uniformScaling is false', () => {
    const canvasEl = document.createElement('canvas');
    const canvas = new fabric.Canvas(canvasEl, {
      uniformScaling: false,
      uniScaleKey: 'shiftKey',
    });

    expect(canvas.uniformScaling).toBe(false);
    expect(canvas.uniScaleKey).toBe('shiftKey');

    const tb = new fabric.Textbox('Speech Balloon Text', {
      width: 100,
      height: 50,
      left: 10,
      top: 10,
    });
    canvas.add(tb);

    // 1. When uniformScaling = false without Shift: Corner drag scales width and height independently
    const transformFree = {
      target: tb,
      originX: 'left' as const,
      originY: 'top' as const,
      scaleX: 1,
      scaleY: 1,
      original: { scaleX: 1, scaleY: 1, left: 10, top: 10, width: 100, height: 50 },
      action: 'scale',
      corner: 'br',
    };
    fabric.controlsUtils.scalingEqually({ shiftKey: false } as any, transformFree as any, 300, 100);

    // ScaleX and ScaleY must be independent (not synced)
    expect(tb.scaleX).not.toEqual(tb.scaleY);
    const freeScaleX = tb.scaleX;
    const freeScaleY = tb.scaleY;

    // 2. When Shift is held down with uniformScaling = false: Corner drag scales proportionally
    tb.set({ scaleX: 1, scaleY: 1 });
    const transformShift = {
      target: tb,
      originX: 'left' as const,
      originY: 'top' as const,
      scaleX: 1,
      scaleY: 1,
      original: { scaleX: 1, scaleY: 1, left: 10, top: 10, width: 100, height: 50 },
      action: 'scale',
      corner: 'br',
    };
    fabric.controlsUtils.scalingEqually({ shiftKey: true } as any, transformShift as any, 300, 100);

    // ScaleX and ScaleY must be strictly synced
    expect(tb.scaleX).toEqual(tb.scaleY);

    canvas.dispose();
  });
});
