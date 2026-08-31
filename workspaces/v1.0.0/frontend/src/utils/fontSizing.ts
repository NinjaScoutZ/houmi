import type { TextBlock } from '../stores/projectStore';

export interface TextPadding {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

export interface TextRegion {
  x: number;
  y: number;
  width: number;
  height: number;
}

export const normalizeTextPadding = (value: unknown): TextPadding => {
  const padding = value && typeof value === 'object'
    ? value as Partial<Record<keyof TextPadding, unknown>>
    : {};
  const number = (entry: unknown) => {
    const parsed = Number(entry);
    return Number.isFinite(parsed) ? Math.max(0, parsed) : 0;
  };
  return {
    top: number(padding.top),
    right: number(padding.right),
    bottom: number(padding.bottom),
    left: number(padding.left),
  };
};

export const resolvePaddedTextRegion = (
  outer: TextRegion,
  paddingValue: unknown,
  rotationDeg = 0,
): TextRegion => {
  const padding = normalizeTextPadding(paddingValue);
  const radians = rotationDeg * Math.PI / 180;
  const width = Math.max(1, outer.width - padding.left - padding.right);
  const height = Math.max(1, outer.height - padding.top - padding.bottom);
  const localCenterOffsetX = (padding.left - padding.right) / 2;
  const localCenterOffsetY = (padding.top - padding.bottom) / 2;
  const centerOffsetX = Math.cos(radians) * localCenterOffsetX - Math.sin(radians) * localCenterOffsetY;
  const centerOffsetY = Math.sin(radians) * localCenterOffsetX + Math.cos(radians) * localCenterOffsetY;
  const centerX = outer.x + outer.width / 2 + centerOffsetX;
  const centerY = outer.y + outer.height / 2 + centerOffsetY;
  return {
    x: centerX - width / 2,
    y: centerY - height / 2,
    width,
    height,
  };
};

export const resolveOuterLayoutRegion = (
  inner: TextRegion,
  paddingValue: unknown,
  rotationDeg = 0,
): TextRegion => {
  const padding = normalizeTextPadding(paddingValue);
  const radians = rotationDeg * Math.PI / 180;
  const width = inner.width + padding.left + padding.right;
  const height = inner.height + padding.top + padding.bottom;
  const localCenterOffsetX = (padding.left - padding.right) / 2;
  const localCenterOffsetY = (padding.top - padding.bottom) / 2;
  const centerOffsetX = Math.cos(radians) * localCenterOffsetX - Math.sin(radians) * localCenterOffsetY;
  const centerOffsetY = Math.sin(radians) * localCenterOffsetX + Math.cos(radians) * localCenterOffsetY;
  const outerCenterX = inner.x + inner.width / 2 - centerOffsetX;
  const outerCenterY = inner.y + inner.height / 2 - centerOffsetY;
  return {
    x: outerCenterX - width / 2,
    y: outerCenterY - height / 2,
    width,
    height,
  };
};

export const isAutoFontSizeEnabled = (
  block: Pick<TextBlock, 'extra_metadata'> | null | undefined,
): boolean => {
  const metadata = block?.extra_metadata || {};
  const mode = metadata.font_size_mode;

  if (mode === 'manual' || mode === 'fixed') return false;
  if (typeof metadata.auto_font_size === 'boolean') return metadata.auto_font_size;
  return metadata.manual_font_size == null;
};
