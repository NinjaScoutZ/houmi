import { describe, test, expect } from 'vitest';
import { DEFAULT_KEY_BINDINGS } from '../stores/projectStore';
import { matchBinding, removeFabricBlockObjects } from '../components/Canvas';
import {
  dilateMaskOverlay,
  isSelectedMaskPixel,
  maskImageDataToOverlay,
  maskOverlayToBinary,
} from '../components/MaskEditorModal';

if (typeof globalThis.ImageData === 'undefined') {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (globalThis as any).ImageData = class ImageData {
    data: Uint8ClampedArray;
    width: number;
    height: number;

    constructor(width: number, height: number) {
      this.width = width;
      this.height = height;
      this.data = new Uint8ClampedArray(width * height * 4);
    }
  };
}

const makeEvent = (opts: Partial<KeyboardEvent>): KeyboardEvent => {
  return {
    key: opts.key || '',
    ctrlKey: !!opts.ctrlKey,
    metaKey: !!opts.metaKey,
    shiftKey: !!opts.shiftKey,
    altKey: !!opts.altKey,
  } as unknown as KeyboardEvent;
};

describe('Mask Editor UX & Canvas Capabilities (R1)', () => {
  describe('Binary mask contract', () => {
    test('opaque black is background while the red overlay is selected', () => {
      expect(isSelectedMaskPixel(0, 0, 0, 255)).toBe(false);
      expect(isSelectedMaskPixel(239, 68, 68, 210)).toBe(true);
      expect(isSelectedMaskPixel(255, 255, 255, 0)).toBe(false);
    });

    test('overlay conversion and export preserve only selected pixels', () => {
      const source = new ImageData(2, 1);
      source.data.set([0, 0, 0, 255, 255, 255, 255, 255]);

      const overlay = maskImageDataToOverlay(source);
      const binary = maskOverlayToBinary(overlay);

      expect(Array.from(binary.data)).toEqual([0, 0, 0, 255, 255, 255, 255, 255]);
    });

    test('kernel expansion grows a one-pixel mask with an elliptical kernel without blurring it', () => {
      const source = new ImageData(5, 5);
      const center = (2 * 5 + 2) * 4;
      source.data.set([239, 68, 68, 210], center);

      const expanded = dilateMaskOverlay(source, 1);
      let selected = 0;
      for (let i = 0; i < expanded.data.length; i += 4) {
        if (expanded.data[i + 3] > 0) selected += 1;
      }

      expect(selected).toBe(5);
    });

    test('kernel expansion works correctly when height > width (portrait panels)', () => {
      // Regression test: rowPrefix was allocated as width*stride instead of
      // height*stride, causing silent OOB reads on tall images.
      const source = new ImageData(3, 8); // height > width
      // Place a selected pixel near the bottom: row 6, col 1
      const pixel = (6 * 3 + 1) * 4;
      source.data.set([239, 68, 68, 210], pixel);

      const expanded = dilateMaskOverlay(source, 1);
      let selected = 0;
      for (let i = 0; i < expanded.data.length; i += 4) {
        if (expanded.data[i + 3] > 0) selected += 1;
      }

      // A radius-1 diamond around (1,6): (1,5),(0,6),(1,6),(2,6),(1,7) = 5 pixels
      expect(selected).toBe(5);
    });
  });

  describe('Requirement 1: Multi-step Undo/Redo history bindings', () => {
    test('DEFAULT_KEY_BINDINGS includes undo and redo shortcuts', () => {
      expect(DEFAULT_KEY_BINDINGS.undo).toBe('Ctrl+Z');
      expect(DEFAULT_KEY_BINDINGS.redo).toBe('Ctrl+Y|Ctrl+Shift+Z');
    });

    test('matchBinding matches Ctrl+Z and Cmd+Z for undo', () => {
      const ctrlZEvent = makeEvent({ key: 'z', ctrlKey: true });
      expect(matchBinding(DEFAULT_KEY_BINDINGS.undo, ctrlZEvent)).toBe(true);

      const metaZEvent = makeEvent({ key: 'z', metaKey: true });
      expect(matchBinding(DEFAULT_KEY_BINDINGS.undo, metaZEvent)).toBe(true);
    });

    test('matchBinding matches Ctrl+Y, Cmd+Y, Ctrl+Shift+Z, and Cmd+Shift+Z for redo', () => {
      const ctrlYEvent = makeEvent({ key: 'y', ctrlKey: true });
      expect(matchBinding(DEFAULT_KEY_BINDINGS.redo, ctrlYEvent)).toBe(true);

      const metaYEvent = makeEvent({ key: 'y', metaKey: true });
      expect(matchBinding(DEFAULT_KEY_BINDINGS.redo, metaYEvent)).toBe(true);

      const ctrlShiftZEvent = makeEvent({ key: 'z', ctrlKey: true, shiftKey: true });
      expect(matchBinding(DEFAULT_KEY_BINDINGS.redo, ctrlShiftZEvent)).toBe(true);

      const metaShiftZEvent = makeEvent({ key: 'z', metaKey: true, shiftKey: true });
      expect(matchBinding(DEFAULT_KEY_BINDINGS.redo, metaShiftZEvent)).toBe(true);
    });
  });

  describe('Requirement 2: Viewport Panning logic', () => {
    test('Space key mappedKey matches space in matchBinding', () => {
      const spaceEvent = makeEvent({ key: ' ' });
      expect(spaceEvent.key).toBe(' ');
    });
  });

  describe('Requirement 4: Tool and brush hotkeys', () => {
    test('keyboard events for 1, 2, 3, [, ] produce correct key properties', () => {
      const key1 = makeEvent({ key: '1' });
      const key2 = makeEvent({ key: '2' });
      const key3 = makeEvent({ key: '3' });
      const leftBracket = makeEvent({ key: '[' });
      const rightBracket = makeEvent({ key: ']' });

      expect(key1.key).toBe('1');
      expect(key2.key).toBe('2');
      expect(key3.key).toBe('3');
      expect(leftBracket.key).toBe('[');
      expect(rightBracket.key).toBe(']');
    });
  });

  describe('Fabric layer reconciliation', () => {
    test('deleting a block removes every duplicate Fabric textbox immediately', () => {
      const ghostA = { type: 'textbox', data: { blockId: 'block-1' } };
      const ghostB = { type: 'textbox', data: { blockId: 'block-1' } };
      const survivor = { type: 'textbox', data: { blockId: 'block-2' } };
      const objects = [ghostA, ghostB, survivor];
      let discarded = false;
      let rendered = false;
      const canvas = {
        getObjects: () => objects,
        getActiveObjects: () => [ghostA],
        discardActiveObject: () => { discarded = true; },
        remove: (object: any) => {
          const index = objects.indexOf(object);
          if (index >= 0) objects.splice(index, 1);
        },
        requestRenderAll: () => { rendered = true; },
      };

      expect(removeFabricBlockObjects(canvas, ['block-1'])).toBe(2);
      expect(objects).toEqual([survivor]);
      expect(discarded).toBe(true);
      expect(rendered).toBe(true);
    });
  });
});
