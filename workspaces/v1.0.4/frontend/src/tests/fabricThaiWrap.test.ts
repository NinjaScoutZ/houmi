// @vitest-environment jsdom
import { describe, expect, test } from 'vitest';
import * as fabric from 'fabric';
import { segmentThaiText, shouldSplitCanvasTextByGrapheme, isThai } from '../utils/thaiTextWrapping';

describe('Fabric.js Thai Textbox Wrapping Behavior', () => {
  test('inspects how Fabric wraps Thai text with segmentThaiText and splitByGrapheme', () => {
    const raw = 'แต่พอรับรู้และดูดซับเข้าไป กลับแข็งแกร่งและทรงประสิทธิภาพอย่างคาดไม่ถึง';
    const segmented = segmentThaiText(raw);

    const tb = new fabric.Textbox(segmented, {
      width: 320,
      fontSize: 28,
      splitByGrapheme: shouldSplitCanvasTextByGrapheme(raw), // false
    });

    console.log('Fabric wrapped lines:', tb._textLines);
    console.log('Fabric textLines count:', tb._textLines?.length);

    // Verify that NO line ends with isolated leading vowel "แ"
    const lines = tb._textLines || [];
    for (const line of lines) {
      const lineStr = Array.isArray(line) ? line.join('') : String(line);
      console.log('Line:', lineStr);
      expect(lineStr.endsWith('กลับแ')).toBe(false);
      expect(lineStr.endsWith('อย่า')).toBe(false);
    }
  });
});
