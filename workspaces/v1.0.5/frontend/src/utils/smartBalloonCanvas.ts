/**
 * Smart Balloon Canvas Utilities
 *
 * Provides shape-adaptive text wrapping and polygon-based selection handles
 * for Fabric.js Textbox objects that render inside Smart Balloon contours.
 */

import * as fabric from 'fabric';

export interface SmartBalloonMetadata {
  contour_points?: Array<[number, number]>;
  raw_contour_points?: Array<[number, number]>;
  center?: { x: number; y: number };
  safe_bbox?: { x: number; y: number; width: number; height: number };
  row_width_constraints?: {
    enabled: boolean;
    row_widths: number[];
    height: number;
  };
  archetype?: string;
}

/**
 * Creates custom polygon-based control points for Smart Balloon textboxes.
 * The selection handles follow the actual balloon contour instead of a rectangular box.
 */
export function createPolygonControls(
  textbox: fabric.Textbox,
  contourPoints: Array<[number, number]>,
  scaleFactor: number
): void {
  if (!contourPoints || contourPoints.length < 3) return;

  // Scale contour points to canvas coordinates
  const scaled = contourPoints.map(([x, y]) => [x / scaleFactor, y / scaleFactor]);

  // Store original controls
  (textbox as any)._smartBalloonOriginalControls = textbox.controls;
  (textbox as any)._smartBalloonContour = scaled;

  // Custom border rendering to show polygon outline
  const originalRender = textbox._renderControls;
  textbox._renderControls = function(ctx: CanvasRenderingContext2D, styleOverride?: any) {
    const sbContour = (this as any)._smartBalloonContour;
    if (!sbContour || sbContour.length < 3) {
      return originalRender.call(this, ctx, styleOverride);
    }

    // Draw polygon border instead of rectangle
    ctx.save();
    ctx.lineWidth = 1 / (this.canvas?.getZoom() || 1);
    ctx.strokeStyle = this.borderColor || '#ff6b35';

    ctx.beginPath();
    const left = this.left || 0;
    const top = this.top || 0;

    sbContour.forEach((pt: [number, number], idx: number) => {
      const [x, y] = pt;
      if (idx === 0) {
        ctx.moveTo(x - left, y - top);
      } else {
        ctx.lineTo(x - left, y - top);
      }
    });
    ctx.closePath();
    ctx.stroke();

    // Minimal Figma-style selection: only four bbox corners. Side capsules,
    // rotation controls and center crosshairs are intentionally omitted.
    const xs = sbContour.map((pt: [number, number]) => pt[0]);
    const ys = sbContour.map((pt: [number, number]) => pt[1]);
    const corners: Array<[number, number]> = [
      [Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.min(...ys)],
      [Math.min(...xs), Math.max(...ys)], [Math.max(...xs), Math.max(...ys)],
    ];
    corners.forEach(([x, y]) => {
      const zoom = this.canvas?.getZoom() || 1;
      const size = Math.max(8, Math.min(12, this.cornerSize || 10)) / zoom;
      ctx.fillStyle = '#111318';
      ctx.strokeStyle = this.cornerStrokeColor || '#f59e0b';
      ctx.lineWidth = 1.25 / zoom;
      ctx.beginPath();
      ctx.roundRect(x - left - size / 2, y - top - size / 2, size, size, 2 / zoom);
      ctx.fill();
      ctx.stroke();
    });

    ctx.restore();
  };
}

/**
 * Removes polygon controls and restores standard rectangular controls.
 */
export function removePolygonControls(textbox: fabric.Textbox): void {
  const original = (textbox as any)._smartBalloonOriginalControls;
  if (original) {
    textbox.controls = original;
    delete (textbox as any)._smartBalloonOriginalControls;
    delete (textbox as any)._smartBalloonContour;
  }

  // Restore default rendering
  textbox._renderControls = (fabric.Textbox.prototype as any)._renderControls;
}

/**
 * Applies shape-adaptive line wrapping to a Fabric.js Textbox.
 * Each line's maximum width is constrained by the Smart Balloon contour at that vertical position.
 */
export function applyShapeAdaptiveWrapping(
  textbox: fabric.Textbox,
  rowWidthConstraints: { enabled: boolean; row_widths: number[]; height: number },
  scaleFactor: number,
  safeBbox: { x: number; y: number; width: number; height: number }
): void {
  if (!rowWidthConstraints?.enabled || !rowWidthConstraints.row_widths) {
    return;
  }

  const rowWidths = rowWidthConstraints.row_widths.map(w => w / scaleFactor);
  const constraintHeight = rowWidthConstraints.height / scaleFactor;

  // Store constraint data on textbox
  (textbox as any)._smartBalloonRowWidths = rowWidths;
  (textbox as any)._smartBalloonConstraintHeight = constraintHeight;
  (textbox as any)._smartBalloonSafeBbox = {
    x: safeBbox.x / scaleFactor,
    y: safeBbox.y / scaleFactor,
    width: safeBbox.width / scaleFactor,
    height: safeBbox.height / scaleFactor,
  };

  // Override Fabric's _wrapLine method to respect row-wise width constraints
  const originalWrapLine = (textbox as any)._wrapLine;
  (textbox as any)._wrapLine = function(
    this: fabric.Textbox,
    _line: any,
    lineIndex: number,
    desiredWidth: number,
    reservedSpace?: number
  ) {
    const rowWidths = (this as any)._smartBalloonRowWidths;
    const bbox = (this as any)._smartBalloonSafeBbox;

    if (!rowWidths || !bbox) {
      return originalWrapLine.call(this, _line, lineIndex, desiredWidth, reservedSpace);
    }

    // Calculate which vertical slice this line occupies
    const lineHeight = (this.fontSize || 16) * (this.lineHeight || 1.2);
    const textTop = this.top || 0;
    const lineTop = textTop + lineIndex * lineHeight;

    // Map line position to row index in constraint array
    const relativeY = lineTop - bbox.y;
    const rowIdx = Math.floor(relativeY);

    if (rowIdx < 0 || rowIdx >= rowWidths.length) {
      return originalWrapLine.call(this, _line, lineIndex, desiredWidth, reservedSpace);
    }

    // Use the actual available width at this vertical position
    const actualMaxWidth = rowWidths[rowIdx];
    const effectiveWidth = Math.max(20, Math.min(actualMaxWidth, desiredWidth));

    return originalWrapLine.call(this, _line, lineIndex, effectiveWidth, reservedSpace);
  };
}

/**
 * Removes shape-adaptive wrapping and restores standard rectangular wrapping.
 */
export function removeShapeAdaptiveWrapping(textbox: fabric.Textbox): void {
  delete (textbox as any)._smartBalloonRowWidths;
  delete (textbox as any)._smartBalloonConstraintHeight;
  delete (textbox as any)._smartBalloonSafeBbox;

  // Restore original _wrapLine
  (textbox as any)._wrapLine = (fabric.Textbox.prototype as any)._wrapLine;
}

/**
 * Positions a textbox at the Smart Balloon visual centroid instead of the bbox center.
 * Vertically centers the actual rendered text height around the centroid cy.
 */
export function positionAtCentroid(
  textbox: fabric.Textbox,
  centroid: { x: number; y: number },
  scaleFactor: number,
  actualTextHeight?: number
): void {
  const cx = centroid.x / scaleFactor;
  const cy = centroid.y / scaleFactor;

  // Center the text block at the centroid
  const textWidth = textbox.width || 100;
  const realH = typeof actualTextHeight === 'number' && Number.isFinite(actualTextHeight) && actualTextHeight > 0
    ? actualTextHeight
    : ((fabric.Textbox.prototype as any).calcTextHeight.call(textbox) || 20);

  textbox.set({
    left: cx - textWidth / 2,
    top: cy - realH / 2,
  });
}

// Helper: Compute convex hull indices for corner handle placement
function _computeConvexHullIndices(points: Array<[number, number]>): number[] {
  if (points.length < 3) return [];

  // Simple gift wrapping algorithm for convex hull
  const n = points.length;
  const hull: number[] = [];

  // Find leftmost point
  let leftmost = 0;
  for (let i = 1; i < n; i++) {
    if (points[i][0] < points[leftmost][0]) leftmost = i;
  }

  let p = leftmost;
  do {
    hull.push(p);
    let q = (p + 1) % n;

    for (let i = 0; i < n; i++) {
      const cross = _crossProduct(points[p], points[i], points[q]);
      if (cross > 0) q = i;
    }

    p = q;
  } while (p !== leftmost && hull.length < n);

  return hull;
}

function _crossProduct(o: [number, number], a: [number, number], b: [number, number]): number {
  return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
}
