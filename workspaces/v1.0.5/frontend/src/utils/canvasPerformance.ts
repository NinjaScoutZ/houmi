export type CanvasPerformanceProfile = 'eco' | 'balanced' | 'performance' | 'custom';

const PROFILE_PIXEL_BUDGET: Record<Exclude<CanvasPerformanceProfile, 'custom'>, number> = {
  eco: 3_500_000,
  balanced: 6_000_000,
  performance: 10_000_000,
};

export interface CanvasWorkingDimensions {
  width: number;
  height: number;
  pixelBudget: number;
  downsampled: boolean;
}

/**
 * Device-pixel density for the transparent Fabric text layer.
 *
 * The page bitmap remains bounded by the working pixel budget.  Giving only
 * the text/handles layer a modest retina scale avoids blurry CSS-resampled
 * glyphs without returning to a full 7k-20k backing canvas.
 */
export const resolveCanvasRetinaScale = (
  profile: string | undefined,
  devicePixelRatio: number | undefined,
): number => {
  const dpr = Math.max(1, Number(devicePixelRatio) || 1);
  if (profile === 'eco') return 1;
  if (profile === 'performance') return Math.min(2, dpr);
  if (profile === 'custom') return Math.min(2, dpr);
  return Math.min(1.5, dpr);
};

/**
 * Backing scale for a CSS-zoomed Fabric canvas.
 *
 * CSS zoom alone stretches the existing glyph bitmap. Raise the backing scale
 * until it matches the visible zoom, with a profile-specific memory ceiling.
 */
export const resolveCanvasZoomRetinaScale = (
  profile: string | undefined,
  devicePixelRatio: number | undefined,
  zoom: number | undefined,
): number => {
  const base = resolveCanvasRetinaScale(profile, devicePixelRatio);
  const visibleZoom = Math.max(0.05, Number(zoom) || 1);
  const ceiling = profile === 'eco' ? 1.25 : profile === 'balanced' ? 2 : 2.5;
  return Math.min(ceiling, Math.max(base, visibleZoom));
};

export interface CanvasControlMetrics {
  borderScaleFactor: number;
  cornerSize: number;
  touchCornerSize: number;
}

/** Keep Fabric resize controls visually compact under CSS zoom. */
export const resolveCanvasControlMetrics = (zoom: number | undefined): CanvasControlMetrics => {
  const visibleZoom = Math.max(0.05, Number(zoom) || 1);
  return {
    borderScaleFactor: 1.25 / visibleZoom,
    cornerSize: 9 / visibleZoom,
    touchCornerSize: 24 / visibleZoom,
  };
};

export const resolveCanvasPixelBudget = (
  profile: string | undefined,
  customPreviewWidth?: number,
): number => {
  if (profile === 'custom') {
    // Preserve the existing Preview Width control semantics, but convert it to
    // a bounded area budget so very tall pages cannot allocate enormous
    // Fabric backing canvases.
    const width = Math.max(600, Math.min(2400, Number(customPreviewWidth) || 1200));
    return Math.max(3_500_000, Math.min(12_000_000, 6_000_000 * Math.pow(width / 1200, 2)));
  }
  if (profile === 'eco' || profile === 'performance') return PROFILE_PIXEL_BUDGET[profile];
  return PROFILE_PIXEL_BUDGET.balanced;
};

export const fitCanvasWorkingDimensions = (
  naturalWidth: number,
  naturalHeight: number,
  pixelBudget: number,
): CanvasWorkingDimensions => {
  const width = Math.max(1, Math.round(naturalWidth));
  const height = Math.max(1, Math.round(naturalHeight));
  const pixels = width * height;
  if (pixels <= pixelBudget) {
    return { width, height, pixelBudget, downsampled: false };
  }

  const scale = Math.sqrt(pixelBudget / pixels);
  return {
    width: Math.max(1, Math.round(width * scale)),
    height: Math.max(1, Math.round(height * scale)),
    pixelBudget,
    downsampled: true,
  };
};
