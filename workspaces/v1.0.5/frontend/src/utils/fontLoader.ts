/**
 * Houmi Unified Font Engine - Frontend Font Loader Utility
 * Manages dynamic CSS @font-face injection, FontFace API loading, and Canvas synchronization.
 */

export interface FontVariantMeta {
  variant_id: string;
  style: string;
  weight: number;
  css_style: string;
  postscript_name: string;
  full_name: string;
  supports_thai: boolean;
  file_size: number;
}

export interface FontFamilyMeta {
  family: string;
  category: 'bundled' | 'custom' | 'manga' | 'thai' | 'system';
  styles: string[];
  variants: FontVariantMeta[];
}

export interface FontListResponse {
  fonts: string[];
  details: Record<string, string[]>;
  families?: Record<string, FontFamilyMeta>;
}

const LINK_ELEMENT_ID = 'houmi-dynamic-font-styles';
const loadedFontCache = new Set<string>();

/**
 * Injects or refreshes the dynamic @font-face stylesheet link from /api/fonts/css.
 */
export function injectFontStylesheet(forceReload = false): void {
  if (typeof document === 'undefined') return;

  let linkEl = document.getElementById(LINK_ELEMENT_ID) as HTMLLinkElement | null;
  const href = `/api/fonts/css${forceReload ? `?t=${Date.now()}` : ''}`;

  if (!linkEl) {
    linkEl = document.createElement('link');
    linkEl.id = LINK_ELEMENT_ID;
    linkEl.rel = 'stylesheet';
    linkEl.href = href;
    document.head.appendChild(linkEl);
  } else if (forceReload) {
    linkEl.href = href;
  }
}

/**
 * Ensures that a specific font variant is fully loaded into the browser memory before rendering.
 * Uses the native CSS Font Loading API (document.fonts.load).
 */
export async function ensureFontLoaded(
  fontFamily: string,
  weight: string | number = 'normal',
  style: string = 'normal',
  sampleText: string = 'กขค ABC 123'
): Promise<boolean> {
  if (typeof document === 'undefined' || !document.fonts) return true;

  const cleanFamily = String(fontFamily || 'sans-serif').replace(/["\\]/g, '\\$&');
  const cleanWeight = typeof weight === 'number' ? weight : (weight === 'bold' ? 700 : 400);
  const cleanStyle = style === 'italic' || style === 'oblique' ? 'italic' : 'normal';
  const descriptor = `${cleanStyle} ${cleanWeight} 16px "${cleanFamily}"`;

  if (loadedFontCache.has(descriptor)) {
    return true;
  }

  try {
    // Ensure stylesheet is in DOM
    injectFontStylesheet();

    // Await font loading
    const loaded = await document.fonts.load(descriptor, sampleText);
    if (loaded && loaded.length > 0) {
      loadedFontCache.add(descriptor);
      return true;
    }
  } catch (err) {
    console.warn(`[FontLoader] Failed to load font "${descriptor}":`, err);
  }

  return false;
}

/**
 * Batch-loads an array of font descriptors before Canvas export or high-precision rendering.
 */
export async function ensureMultipleFontsLoaded(
  fonts: Array<{ family: string; weight?: string | number; style?: string; text?: string }>
): Promise<void> {
  if (typeof document === 'undefined' || !document.fonts) return;

  injectFontStylesheet();
  const promises = fonts.map((f) =>
    ensureFontLoaded(f.family, f.weight || 'normal', f.style || 'normal', f.text || 'ก')
  );

  await Promise.allSettled(promises);
  await document.fonts.ready;
}

const BUILTIN_SYSTEM_FONTS = new Set([
  'tahoma',
  'arial',
  'calibri',
  'times new roman',
  'courier new',
  'segoe ui',
  'sans-serif',
  'serif',
  'monospace',
]);

export function cleanFontKey(s: string): string {
  const cleaned = (s || '')
    .toLowerCase()
    .replace(/[^a-z0-9]/g, '')
    .replace(/phethai/g, 'phetai')
    .replace(/phentai/g, 'phetai')
    .replace(/tarminetine/g, 'tamaitine')
    .replace(/tarmintine/g, 'tamaitine')
    .replace(/v10/g, 'v1')
    .replace(/ver10/g, 'v1')
    .replace(/ver101/g, 'v1');
  return cleaned;
}

/**
 * Checks if a font family is registered and available on the machine or in data/fonts/.
 */
export function isFontAvailable(
  fontFamily: string,
  availableFamilies?: Record<string, FontFamilyMeta>,
  availableFonts?: string[]
): boolean {
  if (!fontFamily) return true;
  const lower = fontFamily.toLowerCase().trim().replace(/['"]/g, '');
  if (BUILTIN_SYSTEM_FONTS.has(lower)) return true;

  const targetClean = cleanFontKey(lower);

  const candidates: string[] = [];
  if (availableFamilies) {
    candidates.push(...Object.keys(availableFamilies));
    for (const meta of Object.values(availableFamilies)) {
      if (meta.family) candidates.push(meta.family);
      if (meta.variants && Array.isArray(meta.variants)) {
        for (const v of meta.variants) {
          if (v.full_name) candidates.push(v.full_name);
          if (v.postscript_name) candidates.push(v.postscript_name);
          if (v.variant_id) candidates.push(v.variant_id);
        }
      }
    }
  }
  if (availableFonts && Array.isArray(availableFonts)) {
    candidates.push(...availableFonts);
  }

  for (const c of candidates) {
    const cLower = c.toLowerCase().trim().replace(/['"]/g, '');
    if (cLower === lower) return true;
    const cClean = cleanFontKey(cLower);
    if (cClean === targetClean) return true;
    if (targetClean.startsWith('th') && targetClean.slice(2) === cClean) return true;
    if (cClean.startsWith('th') && cClean.slice(2) === targetClean) return true;
    // Suffix stripping
    for (const suffix of ['regular', 'bold', 'medium', 'demo', 'v1']) {
      if (targetClean.endsWith(suffix) && targetClean.slice(0, -suffix.length) === cClean) return true;
      if (cClean.endsWith(suffix) && cClean.slice(0, -suffix.length) === targetClean) return true;
    }
  }

  return false;
}

/**
 * Triggers backend rescan of all font directories and dynamically refreshes @font-face rules.
 */
export async function rescanFonts(): Promise<FontListResponse | null> {
  try {
    const res = await fetch('/api/fonts/rescan', { method: 'POST' });
    if (!res.ok) throw new Error('Rescan failed');
    const data: FontListResponse = await res.json();
    loadedFontCache.clear();
    injectFontStylesheet(true);
    return data;
  } catch (e) {
    console.error('[FontLoader] Failed to rescan fonts:', e);
    return null;
  }
}

