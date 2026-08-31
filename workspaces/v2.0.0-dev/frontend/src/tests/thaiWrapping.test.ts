import { describe, expect, test } from 'vitest';
import {
  isThai,
  isCjk,
  shouldSplitCanvasTextByGrapheme,
  segmentThaiText,
} from '../utils/thaiTextWrapping';
import { autoFitTextboxFontSize } from '../components/Canvas';

describe('Thai Word Segmentation & Canvas Text Wrapping', () => {
  test('correctly identifies Thai and CJK text', () => {
    expect(isThai('ยัยผู้หญิงคนนี้')).toBe(true);
    expect(isThai('Hello World')).toBe(false);
    expect(isCjk('这是一段中文')).toBe(true);
    expect(isCjk('ยัยผู้หญิงคนนี้')).toBe(false);
  });

  test('only splits by grapheme for CJK without Thai', () => {
    expect(shouldSplitCanvasTextByGrapheme('这是中文')).toBe(true);
    expect(shouldSplitCanvasTextByGrapheme('日本語')).toBe(true);
    expect(shouldSplitCanvasTextByGrapheme('ยัยผู้หญิงคนนี้ เป็นไปได้ยังไง')).toBe(false);
    expect(shouldSplitCanvasTextByGrapheme('Hello world')).toBe(false);
  });

  test('cleans and segments Thai words without inserting corrupting ZWSPs', () => {
    const rawCase1 = 'ยัยผู้หญิงคนนี้\u200b เป็นไปได้ยังไง';
    const cleaned1 = segmentThaiText(rawCase1);

    // Cleaned string must NOT contain zero-width space
    expect(cleaned1).not.toContain('\u200b');
    expect(cleaned1).toBe('ยัยผู้หญิงคนนี้ เป็นไปได้ยังไง');
  });

  test('short exclamations like "ฮู้ว..." receive optical font scaling in large balloons', () => {
    const textbox: any = {
      text: 'ฮู้ว...',
      width: 300,
      height: 150,
      fontSize: 12,
      lineHeight: 1.2,
      data: { balloonType: 'bubble', minFontSize: 12, maxFontSize: 96 },
      set(values: Record<string, unknown>) { Object.assign(this, values); },
      _splitText() { this._textLines = [['ฮู้ว...']]; },
      getHeightOfLineImpl() { return this.fontSize; },
      getHeightOfLine() { return this.fontSize * this.lineHeight; },
      getLineWidth() { return this.fontSize * 2.5; },
      initDimensions() {},
      setCoords() {},
    };

    autoFitTextboxFontSize(textbox, { requestRenderAll: () => {} }, 1, true);

    // Short text in a 150px height balloon must scale to a balanced optical size (>= 28px), not 12px
    expect(textbox.fontSize).toBeGreaterThanOrEqual(28);
  });
});
