import type { TextBlock } from '../stores/projectStore';
import { isValidCanonicalSpec } from './typesetting';
import { isAutoFontSizeEnabled } from './fontSizing';

export interface CanvasTextView {
  text: string;
  usesCanonicalSpec: boolean;
}

export interface CanvasLayoutRegion {
  x: number;
  y: number;
  width: number;
  height: number;
  shape?: string;
  confidence?: number;
  source?: string;
  safe_margin?: number;
}

const semanticTagAtEnd = /\{[^{}]+\}\s*$/;

/** Strip any brace-wrapped tag at end of translation text for display. */
export function stripSemanticTranslationTags(value: string): string {
  let cleaned = value || '';
  while (semanticTagAtEnd.test(cleaned)) {
    cleaned = cleaned.replace(semanticTagAtEnd, '').trimEnd();
  }
  return cleaned;
}

export function resolveCanvasTextView(block: TextBlock, showTranslated: boolean): CanvasTextView {
  const translation = stripSemanticTranslationTags(block.translation || '');
  // OCR belongs to review data, not the visible Text Layer. Keep an untranslated
  // balloon empty in every canvas view so it cannot trigger a visual auto-fit.
  if (!translation.trim()) {
    return { text: '', usesCanonicalSpec: false };
  }

  const spec = block.extra_metadata?.typesetting_spec;
  if (showTranslated) {
    if (isValidCanonicalSpec(spec)) {
      const explicitText = Array.isArray(spec.explicit_lines) && spec.explicit_lines.length > 0
        ? spec.explicit_lines.join('\n')
        : translation;
      return {
        text: stripSemanticTranslationTags(explicitText),
        usesCanonicalSpec: true,
      };
    }
    return {
      text: translation,
      usesCanonicalSpec: false,
    };
  }

  return {
    text: '',
    usesCanonicalSpec: false,
  };
}

const isUsableLayoutRegion = (value: unknown): value is CanvasLayoutRegion => {
  if (!value || typeof value !== 'object') return false;
  const region = value as Record<string, unknown>;
  return ['x', 'y', 'width', 'height'].every((key) => (
    typeof region[key] === 'number' && Number.isFinite(region[key])
  )) && Number(region.width) > 0 && Number(region.height) > 0;
};

export const getEffectiveEnableSmartBalloon = (
  projectSettings?: Record<string, any> | null
): boolean => {
  // 1. Check active project settings first
  if (projectSettings && typeof projectSettings === 'object') {
    if (typeof projectSettings.enable_smart_balloon === 'boolean') {
      return projectSettings.enable_smart_balloon;
    }
    if (typeof projectSettings.enable_smart_balloon === 'string') {
      return projectSettings.enable_smart_balloon === 'true';
    }
  }

  // 2. Fallback to global stored setting in localStorage
  try {
    const stored = localStorage.getItem('houmi_g_enable_smart_balloon');
    if (stored !== null) {
      const parsed = JSON.parse(stored);
      if (typeof parsed === 'boolean') return parsed;
      if (typeof parsed === 'string') return parsed === 'true';
    }
  } catch {
    // ignore
  }

  try {
    const legacy = localStorage.getItem('houmi_setting_enable_smart_balloon');
    if (legacy !== null) {
      return legacy === 'true';
    }
  } catch {
    // ignore
  }

  // Standard mode preserves stable detector bounding box without shrinking
  return false;
};

export function resolveCanvasLayoutRegion(
  block: TextBlock,
  canonicalSpec?: { layout_region?: unknown },
  useTypesettingRegion = false,
  enableSmartBalloon = true,
): { region: CanvasLayoutRegion; usesLayoutRegion: boolean } {
  if (useTypesettingRegion && enableSmartBalloon) {
    // If Smart Balloon safe bbox or smart coordinates exist, anchor translation text inside the Smart Balloon
    const sbMeta = block.extra_metadata?.smart_balloon;
    const safeBox = sbMeta?.safe_bbox;
    if (isUsableLayoutRegion(safeBox)) {
      return { region: safeBox, usesLayoutRegion: true };
    }
    if (
      block.smart_x != null &&
      block.smart_y != null &&
      Number(block.smart_width ?? 0) > 10 &&
      Number(block.smart_height ?? 0) > 10
    ) {
      return {
        region: {
          x: Number(block.smart_x),
          y: Number(block.smart_y),
          width: Number(block.smart_width),
          height: Number(block.smart_height),
        },
        usesLayoutRegion: true,
      };
    }

    const typesettingRegion = block.extra_metadata?.layout_region;
    if (isUsableLayoutRegion(typesettingRegion)) {
      const regionSource = (typesettingRegion as any)?.source;
      if (regionSource !== 'smart_balloon' && regionSource !== 'smart_balloon_v15') {
        return { region: typesettingRegion, usesLayoutRegion: true };
      }
    }
  }

  const specRegion = canonicalSpec?.layout_region as CanvasLayoutRegion | undefined;
  if (isUsableLayoutRegion(specRegion) && useTypesettingRegion) {
    const specSource = (specRegion as any)?.source;
    if (enableSmartBalloon || (specSource !== 'smart_balloon' && specSource !== 'smart_balloon_v15')) {
      return { region: specRegion, usesLayoutRegion: true };
    }
  }

  // Live canvas editing and display uses the block's current coordinates (centered on Detect, movable by user)
  return {
    region: {
      x: block.x,
      y: block.y,
      width: block.width,
      height: block.height,
    },
    usesLayoutRegion: false,
  };
}
