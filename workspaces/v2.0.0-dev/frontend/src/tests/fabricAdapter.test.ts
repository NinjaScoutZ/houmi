import { describe, test, expect, beforeAll } from 'vitest';
import {
  applyExplicitLineAdapter,
  removeExplicitLineAdapter,
  isExplicitLineAdapterApplied,
} from '../utils/fabricAdapter';

// Stub minimal browser environment elements required by Fabric when running in Node.js
if (typeof window === 'undefined') {
  const mockCanvasEl = {
    getContext: () => ({
      measureText: () => ({ width: 10 }),
      fillRect: () => {},
      clearRect: () => {},
      getImageData: () => ({ data: new Uint8ClampedArray(4) }),
      putImageData: () => {},
      createImageData: () => {},
      save: () => {},
      restore: () => {},
      translate: () => {},
      scale: () => {},
      rotate: () => {},
    }),
    style: {},
    width: 100,
    height: 100,
  };
  
  const mockDoc = {
    createElement: (tag: string) => {
      if (tag === 'canvas') return mockCanvasEl;
      return {};
    },
    addEventListener: () => {},
    removeEventListener: () => {},
  };

  (globalThis as unknown as { window: unknown }).window = {
    document: mockDoc,
    navigator: {
      userAgent: 'node',
    },
    devicePixelRatio: 1,
    addEventListener: () => {},
    removeEventListener: () => {},
  };
  
  (globalThis as unknown as { document: unknown }).document = mockDoc;
}

// Dynamically import fabric to prevent ES import hoisting from loading it before browser stubs run
let fabric: typeof import('fabric');

describe('Fabric Explicit Line Adapter Verification', () => {
  beforeAll(async () => {
    fabric = await import('fabric');
  });

  test('Fabric version compatibility check', () => {
    expect(fabric.version.startsWith('7.')).toBe(true);
  });

  test('initDimensions succeeds and geometries are preserved', () => {
    const tb = new fabric.Textbox('original text', {
      width: 100,
      height: 50,
      left: 10,
      top: 20,
    });
    
    // Check initial properties
    expect(tb.width).toBe(100);
    expect(tb.left).toBe(10);
    expect(tb.top).toBe(20);
    
    applyExplicitLineAdapter(tb, ['line 1', 'line 2']);
    expect(isExplicitLineAdapterApplied(tb)).toBe(true);
    
    // Verify initDimensions runs without throwing
    expect(() => tb.initDimensions()).not.toThrow();
    
    // Geometry is NOT corrupted
    expect(tb.width).toBe(100);
    expect(tb.left).toBe(10);
    expect(tb.top).toBe(20);
    
    // Remove adapter restores
    removeExplicitLineAdapter(tb);
    expect(isExplicitLineAdapterApplied(tb)).toBe(false);
  });

  test('returned arrays contract in non-editing state', () => {
    const tb = new fabric.Textbox('dummy', { width: 100 });
    const explicitLines = ['若为', '仙路'];
    
    applyExplicitLineAdapter(tb, explicitLines);
    
    // Retrieve split results via the overridden method
    const customTb = tb as unknown as { _splitTextIntoLines: (text: string) => {
      lines: string[];
      graphemeLines: string[][];
      _unwrappedLines: string[][];
      graphemeText: string[];
    } };
    const result = customTb._splitTextIntoLines('dummy');
    
    expect(result.lines).toEqual(explicitLines);
    expect(result.graphemeLines).toEqual([['若', '为'], ['仙', '路']]);
    expect(result._unwrappedLines).toEqual([['若', '为'], ['仙', '路']]);
    expect(result.graphemeText).toEqual(['若', '为', '\n', '仙', '路']);
  });

  test('editing delegates to original Fabric implementation', () => {
    const tb = new fabric.Textbox('hello world', { width: 40 });
    
    // Under normal wrapping, a narrow textbox wraps "hello world" into multiple lines
    applyExplicitLineAdapter(tb, ['explicit text']);
    
    // Force editing state
    tb.isEditing = true;
    
    const customTb = tb as unknown as { _splitTextIntoLines: (text: string) => { lines: string[] } };
    const result = customTb._splitTextIntoLines('hello world');
    
    // Should NOT match explicit lines, should delegate to original
    expect(result.lines).not.toEqual(['explicit text']);
  });

  test('removing the adapter restores normal wrapping and idempotency', () => {
    const tb = new fabric.Textbox('hello world', { width: 20 });
    const explicit = ['explicit'];
    
    // Multiple applies should be idempotent
    applyExplicitLineAdapter(tb, explicit);
    applyExplicitLineAdapter(tb, explicit);
    applyExplicitLineAdapter(tb, explicit);
    expect(isExplicitLineAdapterApplied(tb)).toBe(true);
    
    const customTb = tb as unknown as { _splitTextIntoLines: (text: string) => { lines: string[] } };
    let res = customTb._splitTextIntoLines('hello world');
    expect(res.lines).toEqual(explicit);
    
    // Remove restores original
    removeExplicitLineAdapter(tb);
    expect(isExplicitLineAdapterApplied(tb)).toBe(false);
    
    res = customTb._splitTextIntoLines('hello world');
    expect(res.lines).not.toEqual(explicit);
    
    // Multiple removes are idempotent
    removeExplicitLineAdapter(tb);
    removeExplicitLineAdapter(tb);
    expect(isExplicitLineAdapterApplied(tb)).toBe(false);
  });

  test('Fabric internal line-height multiplier parity', () => {
    const fontSize = 16;
    const absoluteLineHeight = 19.2; // absolute pixels
    const tb = new fabric.Textbox('dummy', {
      fontSize,
      lineHeight: absoluteLineHeight / fontSize,
    });
    
    // In Fabric, line height advance in pixels is computed as fontSize * lineHeight
    const calculatedAdvance = tb.fontSize * tb.lineHeight;
    expect(Math.abs(calculatedAdvance - absoluteLineHeight)).toBeLessThan(0.01);
  });
});
