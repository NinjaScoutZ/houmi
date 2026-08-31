export interface FabricGlowProps {
  color: string;
  blur: number;
  offsetX: number;
  offsetY: number;
  affectStroke: boolean;
  nonScaling: boolean;
}

function rgbaColor(hex: string, opacity: number): string {
  const clean = String(hex || '#ffffff').replace('#', '');
  const expanded = clean.length === 3
    ? clean.split('').map(char => char + char).join('')
    : clean.slice(0, 6).padEnd(6, 'f');
  const parseChannel = (value: string) => {
    const parsed = Number.parseInt(value, 16);
    return Number.isFinite(parsed) ? parsed : 255;
  };
  const red = parseChannel(expanded.slice(0, 2));
  const green = parseChannel(expanded.slice(2, 4));
  const blue = parseChannel(expanded.slice(4, 6));
  return `rgba(${red}, ${green}, ${blue}, ${Math.max(0, Math.min(1, opacity))})`;
}

export function fabricGlowFromSpec(spec: any): FabricGlowProps | null {
  // 1. Try new OuterGlowSpec schema
  const og = spec?.outer_glow;
  if (og && og.enabled !== false && Number(og.size ?? og.blur ?? og.radius ?? 0) > 0) {
    const radius = Math.max(0, Number(og.size ?? og.blur ?? og.radius ?? 6));
    const opacity = Number(og.opacity ?? 0.9);
    const colorHex = String(og.color ?? og.color_hex ?? '#ffffff');
    if (radius > 0.05 && opacity > 0) {
      return {
        color: rgbaColor(colorHex, opacity),
        blur: radius,
        offsetX: 0,
        offsetY: 0,
        affectStroke: true,
        nonScaling: false,
      };
    }
  }

  // 2. Fallback to legacy outline_glow_* fields
  const radius = Number(spec?.outline_glow_radius ?? 0);
  const opacity = Number(spec?.outline_glow_opacity ?? 0);
  if (!Number.isFinite(radius) || radius <= 0.05 || !Number.isFinite(opacity) || opacity <= 0) {
    return null;
  }
  return {
    color: rgbaColor(String(spec?.outline_glow_color || '#ffffff'), opacity),
    blur: radius,
    offsetX: 0,
    offsetY: 0,
    affectStroke: true,
    nonScaling: false,
  };
}

export function fabricGlowNeedsUpdate(
  current: Partial<FabricGlowProps> | null | undefined,
  next: FabricGlowProps | null,
): boolean {
  if (!current && !next) return false;
  if (!current || !next) return true;
  return current.color !== next.color
    || Number(current.blur || 0) !== next.blur
    || Number(current.offsetX || 0) !== 0
    || Number(current.offsetY || 0) !== 0;
}
