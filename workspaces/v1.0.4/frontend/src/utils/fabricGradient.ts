import * as fabric from 'fabric';
import type { GradientSpec } from './typesetting';

export function fabricFillFromSpec(spec: { color_hex?: string; gradient?: GradientSpec }, width: number, height: number): string | any {
  const gradient = spec.gradient;
  if (!gradient?.enabled || !Array.isArray(gradient.stops) || gradient.stops.length < 2) {
    return spec.color_hex || '#000000';
  }
  const angle = (Number(gradient.angle_deg || 0) * Math.PI) / 180;
  const dx = Math.cos(angle);
  const dy = Math.sin(angle);
  const cx = width / 2;
  const cy = height / 2;
  const span = Math.max(width, height) * Math.max(0.01, Number(gradient.scale || 100) / 100);
  const x1 = cx - dx * span / 2;
  const y1 = cy - dy * span / 2;
  const x2 = cx + dx * span / 2;
  const y2 = cy + dy * span / 2;
  let stops = gradient.stops.slice().sort((a, b) => a.position - b.position);
  if (gradient.reverse) stops = stops.slice().reverse().map((s) => ({ ...s, position: 1 - s.position })).sort((a, b) => a.position - b.position);
  return new (fabric as any).Gradient({
    type: gradient.type === 'radial' ? 'radial' : 'linear',
    coords: gradient.type === 'radial'
      ? { x1: cx, y1: cy, r1: 0, x2: cx, y2: cy, r2: span / 2 }
      : { x1, y1, x2, y2 },
    colorStops: stops.map((stop) => ({
      offset: Math.max(0, Math.min(1, Number(stop.position))),
      color: stop.color,
      opacity: Math.max(0, Math.min(1, Number(stop.opacity ?? 1) * Number(gradient.opacity ?? 1))),
    })),
  });
}

export function gradientSignature(gradient?: GradientSpec): string {
  return JSON.stringify(gradient || { enabled: false });
}
