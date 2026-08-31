import * as fabric from 'fabric';

export const MINIMAL_BALLOON_CONTROL_VISIBILITY = {
  tl: true, tr: true, bl: true, br: true,
  mt: false, mb: false, ml: false, mr: false, mtr: false,
} as const;

export function renderMinimalBalloonCorner(
  this: fabric.Control,
  ctx: CanvasRenderingContext2D,
  left: number,
  top: number,
  _styleOverride: object | undefined,
  object: fabric.Object,
): void {
  const size = Math.max(8, Math.min(12, Number((this as fabric.Control & { cornerSize?: number }).cornerSize) || 10));
  const stroke = String((object as fabric.Object & { cornerStrokeColor?: string }).cornerStrokeColor || '#f59e0b');
  ctx.save();
  ctx.translate(left, top);
  ctx.beginPath();
  ctx.roundRect(-size / 2, -size / 2, size, size, 2);
  ctx.fillStyle = '#111318';
  ctx.fill();
  ctx.lineWidth = 1.25;
  ctx.strokeStyle = stroke;
  ctx.stroke();
  ctx.restore();
}

export function applyMinimalBalloonControls(object: fabric.Textbox, strokeColor?: string): void {
  object.set({
    cornerStyle: 'rect',
    cornerColor: '#111318',
    cornerStrokeColor: strokeColor || object.cornerStrokeColor || '#f59e0b',
    transparentCorners: false,
    borderScaleFactor: 1,
  });
  object.setControlsVisibility(MINIMAL_BALLOON_CONTROL_VISIBILITY);
  for (const key of ['tl', 'tr', 'bl', 'br'] as const) {
    const control = object.controls?.[key];
    if (control) control.render = renderMinimalBalloonCorner;
  }
}
