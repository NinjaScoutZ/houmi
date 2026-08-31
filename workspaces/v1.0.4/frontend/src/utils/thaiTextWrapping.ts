/**
 * Thai Word Segmentation and Safe Canvas Line Breaking Utilities.
 * Uses native browser Intl.Segmenter for sub-millisecond, syllable-safe Thai text processing.
 */

export const isThai = (text: string): boolean => {
  return /[\u0e00-\u0e7f]/.test(text);
};

export const isCjk = (text: string): boolean => {
  return /[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff66-\uff9f]/.test(text);
};

/**
 * Strips zero-width characters and invisible break markers that cause wide spacing
 * or missing glyph boxes in Canvas fonts.
 */
export const cleanThaiText = (text: string): string => {
  if (!text) return '';
  return text.replace(/[\u200b\u200c\u200d\u200e\u200f\ufeff]/g, '');
};

/**
 * Checks if canvas text should use splitByGrapheme.
 * CJK characters can split per grapheme, but Thai MUST NOT because Thai consists of
 * complex multi-character syllables, leading vowels, and combining tone marks.
 */
export const shouldSplitCanvasTextByGrapheme = (text: string): boolean => {
  return isCjk(text) && !isThai(text);
};

/**
 * Segments Thai text into syllables/words using Intl.Segmenter.
 */
export const getThaiWordSegments = (text: string): string[] => {
  if (!text || !isThai(text)) return text ? [text] : [];
  const clean = cleanThaiText(text);

  if (typeof Intl !== 'undefined' && (Intl as any).Segmenter) {
    try {
      const segmenter = new (Intl as any).Segmenter('th', { granularity: 'word' });
      const segments = Array.from(segmenter.segment(clean)) as Array<{ segment: string }>;
      return segments.map((s) => s.segment);
    } catch {
      return [clean];
    }
  }
  return [clean];
};

/**
 * Returns clean Thai text without corrupting with raw ZWSPs that cause wide spacing bugs in Canvas.
 */
export const segmentThaiText = (text: string): string => {
  return cleanThaiText(text);
};
