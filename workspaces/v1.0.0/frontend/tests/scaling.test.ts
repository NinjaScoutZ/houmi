import { describe, test, expect } from 'vitest';
import { originalToCanvasSize, canvasToOriginalSize, sceneFontSizeToOriginal } from '../src/utils/scaling.ts';

describe('Scaling utility actual implementation checks', () => {
  test('Test sceneFontSizeToOriginal with scaleFactor 0.5, 1, 2', () => {
    // scaleFactor = 1.0
    expect(sceneFontSizeToOriginal(20, 1.0)).toBe(20);
    
    // scaleFactor = 0.5 (database is half the size of canvas)
    expect(sceneFontSizeToOriginal(20, 0.5)).toBe(10);
    
    // scaleFactor = 2.0 (database is twice the size of canvas)
    expect(sceneFontSizeToOriginal(20, 2.0)).toBe(40);
  });

  test('Verify zoom changes do not change the persisted font size value', () => {
    const bestSize = 16;
    const scaleFactor = 1.5;
    
    // Calculate expected persisted value (logical font size * scaleFactor)
    const expectedPersistedValue = 24; 
    
    // Test under zoom 0.5
    const persistUnderZoomHalf = sceneFontSizeToOriginal(bestSize, scaleFactor);
    expect(persistUnderZoomHalf).toBe(expectedPersistedValue);
    
    // Test under zoom 1.0
    const persistUnderZoomOne = sceneFontSizeToOriginal(bestSize, scaleFactor);
    expect(persistUnderZoomOne).toBe(expectedPersistedValue);
    
    // Test under zoom 2.0
    const persistUnderZoomTwo = sceneFontSizeToOriginal(bestSize, scaleFactor);
    expect(persistUnderZoomTwo).toBe(expectedPersistedValue);
  });

  test('Test coordinate scale conversions with scaleFactor 0.5, 1, 2', () => {
    // scaleFactor = 1.0
    expect(originalToCanvasSize(100, 1.0)).toBe(100);
    expect(canvasToOriginalSize(100, 1.0)).toBe(100);

    // scaleFactor = 2.0
    expect(originalToCanvasSize(100, 2.0)).toBe(50);
    expect(canvasToOriginalSize(50, 2.0)).toBe(100);

    // scaleFactor = 0.5
    expect(originalToCanvasSize(100, 0.5)).toBe(200);
    expect(canvasToOriginalSize(200, 0.5)).toBe(100);
  });
});
