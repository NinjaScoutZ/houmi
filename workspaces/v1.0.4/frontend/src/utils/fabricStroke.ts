/**
 * Map TypesettingSpec stroke fields onto Fabric Textbox-compatible props.
 * Fabric uses stroke + strokeWidth on the text object for outline.
 */

export interface FabricStrokeProps {
  stroke: string | undefined;
  strokeWidth: number;
  paintFirst?: 'stroke' | 'fill';
}

/** Minimal Fabric-like object fields used for dirty checks. */
export interface FabricStrokeReadable {
  stroke?: string | null;
  strokeWidth?: number | null;
  paintFirst?: string | null;
}

export function fabricStrokeFromSpec(spec: {
  stroke_width?: number | null;
  stroke_color?: string | null;
} | null | undefined): FabricStrokeProps {
  if (!spec) {
    return { stroke: undefined, strokeWidth: 0 };
  }
  const w = Number(spec.stroke_width ?? 0);
  if (!Number.isFinite(w) || w <= 0.05) {
    return { stroke: undefined, strokeWidth: 0 };
  }
  // Fabric strokeWidth is in object space; Spec stores design px at layout size.
  // Use rounded px ≥ 1 so thin 1px outlines remain visible.
  const px = Math.max(1, Math.round(w));
  const color = (spec.stroke_color || '#ffffff').toString();
  return {
    stroke: color.startsWith('#') ? color : `#${color}`,
    strokeWidth: px,
    paintFirst: 'stroke',
  };
}

/**
 * True when an existing Fabric text object must be updated for stroke draw-through.
 * Used by Canvas hasChanged so stroke-only Spec updates are not skipped.
 */
export function fabricStrokeNeedsUpdate(
  existing: FabricStrokeReadable | null | undefined,
  next: FabricStrokeProps,
): boolean {
  const curStroke = existing?.stroke == null || existing.stroke === ''
    ? undefined
    : String(existing.stroke);
  const curWidth = Number(existing?.strokeWidth ?? 0) || 0;
  const curPaint = (existing?.paintFirst as string | undefined) || undefined;

  const nextStroke = next.stroke == null || next.stroke === ''
    ? undefined
    : String(next.stroke);
  const nextWidth = Number(next.strokeWidth ?? 0) || 0;
  const nextPaint = next.paintFirst || (nextWidth > 0 ? 'stroke' : undefined);

  if (curStroke !== nextStroke) return true;
  if (curWidth !== nextWidth) return true;
  // Only compare paintFirst when stroke is active; Fabric default is fill
  if (nextWidth > 0 && curPaint !== nextPaint) return true;
  if (nextWidth === 0 && curWidth !== 0) return true;
  return false;
}
