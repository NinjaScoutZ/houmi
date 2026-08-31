export interface RGBColor {
  r: number;
  g: number;
  b: number;
}

export interface HSBColor {
  h: number;
  s: number;
  b: number;
}

const clamp = (value: number, minimum: number, maximum: number) =>
  Math.min(maximum, Math.max(minimum, Number.isFinite(value) ? value : minimum));

export function normalizeHex(value: string): string | null {
  const trimmed = value.trim();
  const prefixed = trimmed.startsWith('#') ? trimmed : `#${trimmed}`;
  return /^#[0-9a-f]{6}$/i.test(prefixed) ? prefixed.toLowerCase() : null;
}

export function normalizeStoredHex(value: string): string | null {
  const normalized = normalizeHex(value);
  if (normalized) return normalized;
  const short = value.trim().match(/^#?([0-9a-f])([0-9a-f])([0-9a-f])$/i);
  return short
    ? `#${short[1]}${short[1]}${short[2]}${short[2]}${short[3]}${short[3]}`.toLowerCase()
    : null;
}

export function hexToRgb(value: string): RGBColor | null {
  const normalized = normalizeStoredHex(value);
  if (!normalized) return null;
  return {
    r: Number.parseInt(normalized.slice(1, 3), 16),
    g: Number.parseInt(normalized.slice(3, 5), 16),
    b: Number.parseInt(normalized.slice(5, 7), 16),
  };
}

export function rgbToHex({ r, g, b }: RGBColor): string {
  const channel = (value: number) => Math.round(clamp(value, 0, 255)).toString(16).padStart(2, '0');
  return `#${channel(r)}${channel(g)}${channel(b)}`;
}

export function rgbToHsb({ r, g, b }: RGBColor): HSBColor {
  const red = clamp(r, 0, 255) / 255;
  const green = clamp(g, 0, 255) / 255;
  const blue = clamp(b, 0, 255) / 255;
  const maximum = Math.max(red, green, blue);
  const minimum = Math.min(red, green, blue);
  const delta = maximum - minimum;
  let hue = 0;

  if (delta > 0) {
    if (maximum === red) hue = 60 * (((green - blue) / delta) % 6);
    else if (maximum === green) hue = 60 * ((blue - red) / delta + 2);
    else hue = 60 * ((red - green) / delta + 4);
  }
  if (hue < 0) hue += 360;

  return {
    h: hue,
    s: maximum === 0 ? 0 : (delta / maximum) * 100,
    b: maximum * 100,
  };
}

export function hsbToRgb({ h, s, b }: HSBColor): RGBColor {
  const hue = ((Number.isFinite(h) ? h : 0) % 360 + 360) % 360;
  const saturation = clamp(s, 0, 100) / 100;
  const brightness = clamp(b, 0, 100) / 100;
  const chroma = brightness * saturation;
  const section = hue / 60;
  const secondary = chroma * (1 - Math.abs((section % 2) - 1));
  const offset = brightness - chroma;
  let red = 0;
  let green = 0;
  let blue = 0;

  if (section < 1) [red, green] = [chroma, secondary];
  else if (section < 2) [red, green] = [secondary, chroma];
  else if (section < 3) [green, blue] = [chroma, secondary];
  else if (section < 4) [green, blue] = [secondary, chroma];
  else if (section < 5) [red, blue] = [secondary, chroma];
  else [red, blue] = [chroma, secondary];

  return {
    r: Math.round((red + offset) * 255),
    g: Math.round((green + offset) * 255),
    b: Math.round((blue + offset) * 255),
  };
}
