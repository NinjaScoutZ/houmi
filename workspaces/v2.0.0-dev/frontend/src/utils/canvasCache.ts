// Canvas state caching to avoid full rebuild on page switches
import * as fabric from 'fabric';

export interface CachedCanvas {
  canvas: fabric.Canvas;
  pageId: string;
  timestamp: number;
  scrollPosition: { scrollTop: number; scrollLeft: number };
}

const MAX_CACHE_SIZE = 3; // Keep last 3 pages in memory
const canvasCache = new Map<string, CachedCanvas>();

/**
 * Checks whether canvas caching is enabled in settings or localStorage.
 */
export const isCanvasCacheEnabled = (settings?: Record<string, any> | null): boolean => {
  if (settings && typeof settings.enable_canvas_cache === 'boolean') {
    return settings.enable_canvas_cache;
  }
  try {
    const local = localStorage.getItem('houmi_enable_canvas_cache');
    if (local !== null) return local === 'true';
  } catch {
    // ignore
  }
  return true; // Default ON
};

export const getCachedCanvas = (pageId: string): fabric.Canvas | null => {
  const cached = canvasCache.get(pageId);
  if (!cached) return null;

  // Return cached canvas if less than 5 minutes old
  const age = Date.now() - cached.timestamp;
  if (age > 5 * 60 * 1000) {
    canvasCache.delete(pageId);
    return null;
  }

  return cached.canvas;
};

export const getCachedCanvasInfo = (pageId: string): CachedCanvas | null => {
  const cached = canvasCache.get(pageId);
  if (!cached) return null;
  const age = Date.now() - cached.timestamp;
  if (age > 5 * 60 * 1000) {
    canvasCache.delete(pageId);
    return null;
  }
  return cached;
};

export const cacheCanvas = (
  pageId: string,
  canvas: fabric.Canvas,
  scrollPosition: { scrollTop: number; scrollLeft: number }
) => {
  // Remove oldest if cache full
  if (canvasCache.size >= MAX_CACHE_SIZE) {
    const oldestKey = Array.from(canvasCache.entries())
      .sort((a, b) => a[1].timestamp - b[1].timestamp)[0][0];
    const oldest = canvasCache.get(oldestKey);
    if (oldest) {
      oldest.canvas.dispose();
    }
    canvasCache.delete(oldestKey);
  }

  canvasCache.set(pageId, {
    canvas,
    pageId,
    timestamp: Date.now(),
    scrollPosition,
  });
};

export const invalidateCache = (pageId?: string) => {
  if (pageId) {
    const cached = canvasCache.get(pageId);
    if (cached) {
      cached.canvas.dispose();
    }
    canvasCache.delete(pageId);
  } else {
    // Clear all
    canvasCache.forEach((cached) => cached.canvas.dispose());
    canvasCache.clear();
  }
};

export const getCachedScrollPosition = (pageId: string) => {
  const cached = canvasCache.get(pageId);
  return cached?.scrollPosition || { scrollTop: 0, scrollLeft: 0 };
};

export const getCacheSize = (): number => canvasCache.size;

