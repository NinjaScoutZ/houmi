import React, { useEffect, useRef, useState } from 'react';
import * as fabric from 'fabric';
import { injectFontStylesheet, ensureFontLoaded, ensureMultipleFontsLoaded } from '../utils/fontLoader';

// Configure Fabric.js Textbox word joiners and Free Rotate defaults.
if ((fabric.Textbox as any).ownDefaults) {
  (fabric.Textbox as any).ownDefaults._wordJoiners = /[ \t\r]/;
  (fabric.Textbox as any).ownDefaults.centeredRotation = true;
  (fabric.Textbox as any).ownDefaults.snapAngle = 0;
  (fabric.Textbox as any).ownDefaults.snapThreshold = 0;
}
if ((fabric as any).FabricObject && (fabric as any).FabricObject.ownDefaults) {
  (fabric as any).FabricObject.ownDefaults.centeredRotation = true;
  (fabric as any).FabricObject.ownDefaults.snapAngle = 0;
  (fabric as any).FabricObject.ownDefaults.snapThreshold = 0;
}

// Configure Fabric.js Textbox to support vertical centering inside the bounding box.
// This aligns the frontend editor layout with the backend renderer.
if ((fabric.Textbox as any).prototype) {
  (fabric.Textbox as any).prototype._getTopOffset = function(this: any) {
    let actualTextHeight = 0;
    if (this._textLines) {
      for (let i = 0; i < this._textLines.length; i++) {
        actualTextHeight += this.getHeightOfLine(i);
      }
    }
    if (actualTextHeight > 0 && this.height > actualTextHeight) {
      return -actualTextHeight / 2;
    }
    return -this.height / 2;
  };

  // Photoshop-style editing: Enter inserts a real authored line break.
  // Ctrl/Cmd+Enter commits and exits the text editor.
  const originalOnKeyDown = (fabric.Textbox as any).prototype.onKeyDown || (fabric.IText as any).prototype.onKeyDown;
  (fabric.Textbox as any).prototype.onKeyDown = function(this: any, e: KeyboardEvent) {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      this.exitEditing();
      return;
    }
    if (originalOnKeyDown) {
      originalOnKeyDown.call(this, e);
    }
  };

  // Thai-Aware Natural Word Wrapping:
  // Uses browser Intl.Segmenter to safely break Thai sentences at word boundaries
  // instead of treating whole Thai sentences as single unbroken words.
  const originalWrapLine = (fabric.Textbox as any).prototype._wrapLine;
  (fabric.Textbox as any).prototype._wrapLine = function(this: any, line: any, lineIndex: number, reservedSpace: number = 0) {
    const textStr = Array.isArray(line) ? line.join('') : String(line || '');
    if (/[\u0e00-\u0e7f]/.test(textStr) && typeof Intl !== 'undefined' && (Intl as any).Segmenter) {
      const maxWidth = this.width - reservedSpace;
      if (maxWidth > 10) {
        try {
          const segmenter = new (Intl as any).Segmenter('th', { granularity: 'word' });
          const words = Array.from(segmenter.segment(textStr)).map((s: any) => s.segment);
          const wrappedLines: any[] = [];
          let currentLine = '';

          for (const word of words) {
            const testLine = currentLine + word;
            const testWidth = this._measureLine ? this._measureLine(testLine).width : 0;
            if (currentLine && testWidth > maxWidth) {
              wrappedLines.push(currentLine.split(''));
              currentLine = word.trimStart();
            } else {
              currentLine += word;
            }
          }
          if (currentLine) {
            wrappedLines.push(currentLine.split(''));
          }
          if (wrappedLines.length > 0) {
            return wrappedLines;
          }
        } catch {
          // fallback to default
        }
      }
    }
    if (originalWrapLine) {
      return originalWrapLine.call(this, line, lineIndex, reservedSpace);
    }
    return [line];
  };
}

const rotateIconSvg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="#f97316" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>`;
const rotateIconImg = typeof window !== 'undefined' && typeof Image !== 'undefined' ? new Image() : null;
if (rotateIconImg) {
  rotateIconImg.src = `data:image/svg+xml;utf8,${encodeURIComponent(rotateIconSvg)}`;
}

const renderRotateIcon = function(this: any, ctx: CanvasRenderingContext2D, left: number, top: number, styleOverride: any, fabricObject: any) {
  const size = this.cornerSize || 24;
  ctx.save();
  ctx.translate(left, top);
  
  // Background circle
  ctx.beginPath();
  ctx.arc(0, 0, size / 2, 0, 2 * Math.PI);
  ctx.fillStyle = '#18181b'; // zinc-900
  ctx.fill();
  ctx.lineWidth = 1.5;
  ctx.strokeStyle = '#f97316'; // orange-500
  ctx.stroke();

  if (rotateIconImg && rotateIconImg.complete) {
    ctx.drawImage(rotateIconImg, -size / 2, -size / 2, size, size);
  }
  ctx.restore();
};

import { useProjectStore, type TextBlock } from '../stores/projectStore';
import { ZoomIn, ZoomOut, Move, Type, Trash2, Sparkles, ScanText, ScanLine, Keyboard, Image as ImageIcon, X, ChevronLeft, ChevronRight, Eye, EyeOff, Maximize2, Minus, Plus, Loader2, CheckCircle2 } from 'lucide-react';
import { apiFetch } from '../api/runtime';
import { canvasToOriginalSize } from '../utils/scaling';
import { applyExplicitLineAdapter, removeExplicitLineAdapter } from '../utils/fabricAdapter';
import { isValidCanonicalSpec } from '../utils/typesetting';
import { resolveDecisionBadge } from '../utils/decisionStatus';
import { fabricStrokeFromSpec, fabricStrokeNeedsUpdate } from '../utils/fabricStroke';
import { fabricGlowFromSpec, fabricGlowNeedsUpdate } from '../utils/fabricGlow';
import { fabricFillFromSpec, gradientSignature } from '../utils/fabricGradient';
import {
  applyMultiEffectTextRenderer,
  buildMangaEffects,
  multiEffectNeedsUpdate,
  multiEffectSignature,
} from '../utils/fabricMultiEffect';
import { resolveCanvasLayoutRegion, resolveCanvasTextView, getEffectiveEnableSmartBalloon } from '../utils/canvasView';
import {
  isAutoFontSizeEnabled,
  normalizeTextPadding,
  resolveOuterLayoutRegion,
  resolvePaddedTextRegion,
} from '../utils/fontSizing';
import {
  createPolygonControls,
  removePolygonControls,
  applyShapeAdaptiveWrapping,
  removeShapeAdaptiveWrapping,
  positionAtCentroid,
  type SmartBalloonMetadata,
} from '../utils/smartBalloonCanvas';
import {
  fitCanvasWorkingDimensions,
  resolveCanvasControlMetrics,
  resolveCanvasPixelBudget,
  resolveCanvasZoomRetinaScale,
} from '../utils/canvasPerformance';
import { CanvasAlignmentToolbar } from './CanvasAlignmentToolbar';
import { CanvasContextMenu } from './CanvasContextMenu';
import { FloatingLetteringBar } from './FloatingLetteringBar';
import { MaskToolbar } from './MaskToolbar';
import { usePageMaskEditor } from '../hooks/usePageMaskEditor';

interface CanvasProps {
  onOpenMaskEditor?: (blockId: string) => void;
  onRunOCR?: (blockIds?: string[]) => void;
  onRunInpaintPreview?: () => void;
  onEnsureInpainted?: () => Promise<boolean>;
  onRunFontJudge?: () => void;
  deferAutomaticFullCleanForPageId?: string | null;
  onRefreshPage?: () => void | Promise<void>;
  onRefitPageText?: () => void | Promise<void>;
  onResetPageMasks?: () => void | Promise<void>;
  onResetProjectMasks?: () => void | Promise<void>;
  liveMaskOverlay?: boolean;
  cleanPreviewRevision?: number;
  cleanPreviewRequest?: { pageId: string; revision: number } | null;
  showBottomPageNavigator?: boolean;
  useTypesettingLayout?: boolean;
  showFloatingLetteringBar?: boolean;
  onCloseFloatingLetteringBar?: () => void;
}

export const removeFabricBlockObjects = (
  canvas: {
    getObjects: () => any[];
    getActiveObjects?: () => any[];
    discardActiveObject?: () => unknown;
    remove: (object: any) => unknown;
    requestRenderAll?: () => unknown;
  },
  blockIds: string[],
): number => {
  const ids = new Set(blockIds);
  const targets = canvas.getObjects().filter((object: any) => (
    object?.type === 'textbox' && ids.has(object?.data?.blockId)
  ));
  if (targets.length === 0) return 0;

  const activeObjects = canvas.getActiveObjects?.() || [];
  if (targets.some((target: any) => activeObjects.includes(target))) {
    canvas.discardActiveObject?.();
  }
  targets.forEach((target: any) => canvas.remove(target));
  canvas.requestRenderAll?.();
  return targets.length;
};

export const suppressTextboxDecorationsForCapture = (
  textboxes: fabric.Textbox[],
): (() => void) => {
  const states = textboxes.map((textbox) => ({
    textbox,
    render: textbox._render,
    hasBorders: textbox.hasBorders,
    hasControls: textbox.hasControls,
  }));

  textboxes.forEach((textbox) => {
    // Export only Fabric's text pixels. Instance render overrides also draw
    // editor-only overflow/warning outlines around the balloon region.
    textbox._render = fabric.Textbox.prototype._render;
    textbox.set({ hasBorders: false, hasControls: false });
  });

  return () => {
    states.forEach(({ textbox, render, hasBorders, hasControls }) => {
      textbox._render = render;
      textbox.set({ hasBorders, hasControls });
    });
  };
};

export const matchBinding = (binding: string | undefined, e: KeyboardEvent): boolean => {
  if (!binding) return false;
  if (binding.includes('|')) {
    return binding.split('|').some(option => matchBinding(option.trim(), e));
  }
  const parts = binding.split('+');
  const needsCtrl = parts.includes('Ctrl');
  const needsShift = parts.includes('Shift');
  const needsAlt = parts.includes('Alt');

  const baseKey = parts[parts.length - 1].toLowerCase();
  
  const hasCtrl = e.ctrlKey || e.metaKey;
  const hasShift = e.shiftKey;
  const hasAlt = e.altKey;
  
  const currentKey = e.key.toLowerCase();
  
  let mappedKey = currentKey;
  if (e.key === ' ') mappedKey = 'space';
  
  return (
    needsCtrl === hasCtrl &&
    needsShift === hasShift &&
    needsAlt === hasAlt &&
    (baseKey === mappedKey || 
     (baseKey === 'delete' && e.key === 'Delete') || 
     (baseKey === 'escape' && e.key === 'Escape') || 
     (baseKey === 'tab' && e.key === 'Tab'))
  );
};

import {
  isCjk,
  isThai,
  shouldSplitCanvasTextByGrapheme,
  segmentThaiText,
  cleanThaiText,
} from '../utils/thaiTextWrapping';

export { isCjk, isThai, shouldSplitCanvasTextByGrapheme, segmentThaiText, cleanThaiText };

export const autoFitTextboxFontSize = (textbox: any, _canvas: any, sf: number, _skipBackendUpdate = false) => {
  const text = textbox.text || '';
  if (!text.trim()) return;

  const needsSplit = shouldSplitCanvasTextByGrapheme(text);
  textbox.set({ splitByGrapheme: needsSplit });

  const W = textbox.width;
  const H = textbox.height;
  const balloonType = textbox.data?.balloonType || 'bubble';
  const cleanLength = text.replace(/\s+/g, '').length;
  const isShortText = cleanLength <= 10;

  // Smart quality floor based on balloon height H:
  // For large speech balloons, font size should never shrink to tiny ant sizes (10-12px)
  // For short text / exclamations (e.g. "ฮู้ว..."), provide optical fill so it doesn't float as a tiny speck
  const minimumOriginal = (balloonType === 'bubble' && H >= 80)
    ? (isShortText ? Math.max(24, Math.round(H * 0.22)) : Math.max(16, Math.round(H * 0.12)))
    : (isShortText ? Math.max(20, Math.round(H * 0.18)) : 12);

  const configuredMaximum = Number(textbox.data?.maxFontSize);
  const maximumOriginal = Number.isFinite(configuredMaximum) && configuredMaximum > 0
    ? Math.max(minimumOriginal, configuredMaximum)
    : (isShortText
        ? Math.max(minimumOriginal, Math.min(W * sf * 0.45, H * sf * 0.45))
        : Math.max(140, Math.min(W * sf, H * sf) * 0.45));

  const minimumScene = Math.max(1, Math.ceil(minimumOriginal / Math.max(sf, Number.EPSILON)));
  const maximumScene = Math.max(minimumScene, Math.floor(maximumOriginal / Math.max(sf, Number.EPSILON)));

  // Safety margins
  const maxAllowedHeight = H * 0.92;
  const ellipseSafetyFactor = 0.93; // 93% width safety for smooth curve fitting
  const rectSafetyFactor = 0.95;

  let low = minimumScene;
  let high = maximumScene;
  let bestSize = low;

  // Save original width before test fitting
  const originalWidth = textbox.width;
  // For oval speech balloons, set an optimal wrap width (85% of W) so text wraps into balanced multi-line stacks
  if (balloonType === 'bubble' && isCjk(text) && cleanLength > 15) {
    textbox.set({ width: Math.max(60, W * 0.85) });
  }

  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    textbox.set({ fontSize: mid });

    // Trigger Fabric layout calculations
    textbox._splitText();
    
    const actualHeight = (fabric.Textbox.prototype as any).calcTextHeight.call(textbox);

    let fits = true;
    if (actualHeight > maxAllowedHeight) {
      fits = false;
    } else {
      const linesCount = textbox._textLines.length;
      const lineHeight = textbox.fontSize * textbox.lineHeight;
      
      for (let i = 0; i < linesCount; i++) {
        const lineWidth = textbox.getLineWidth(i);
        
        if (balloonType === 'bubble') {
          // Vertical center of this line relative to text top
          const lineCenterFromTextTop = i * lineHeight + lineHeight / 2;
          const y = lineCenterFromTextTop - actualHeight / 2;
          const halfH = H / 2;
          const normalizedY = Math.abs(y) / halfH;
          
          if (normalizedY >= 0.96) {
            fits = false;
            break;
          }
          
          const allowedWidth = W * Math.sqrt(Math.max(0, 1 - normalizedY * normalizedY)) * ellipseSafetyFactor;
          if (lineWidth > allowedWidth) {
            fits = false;
            break;
          }
        } else {
          if (lineWidth > W * rectSafetyFactor) {
            fits = false;
            break;
          }
        }
      }
    }

    if (fits) {
      bestSize = mid;
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }

  // Restore original width container
  textbox.set({ width: originalWidth });
  textbox.set({ fontSize: bestSize });

  // Commit Fabric's wrapped-line state
  textbox.initDimensions?.();
  textbox.setCoords?.();
  textbox.dirty = true;
  _canvas?.requestRenderAll?.();

  // Keep Canvas, Inspector, and the in-memory canonical spec in sync immediately.
  // Persistence is optional so rapid fitting can never create an API feedback loop.
  if (textbox.data?.blockId) {
    const databaseFontSize = Math.max(
      minimumOriginal,
      Math.round(canvasToOriginalSize(bestSize, sf)),
    );
    
    const page = useProjectStore.getState().activePage;
    const currentBlock = page?.text_blocks?.find(b => b.id === textbox.data.blockId);
      
    if (currentBlock && (
      currentBlock.font_size !== databaseFontSize
      || currentBlock.extra_metadata?.typesetting_spec?.font_size !== databaseFontSize
    )) {
      const prevMeta = currentBlock.extra_metadata || {};
      // Sync the fitted font size into the typesetting_spec as well so that
      // code paths reading spec.font_size don't see a stale value.
      const previousSpecSize = Number(prevMeta.typesetting_spec?.font_size);
      const previousLineHeight = Number(prevMeta.typesetting_spec?.line_height);
      const lineHeightRatio = previousSpecSize > 0 && previousLineHeight > 0
        ? previousLineHeight / previousSpecSize
        : Number(prevMeta.line_height_ratio || 1.2);
      const syncedSpec = prevMeta.typesetting_spec
        ? {
            ...prevMeta.typesetting_spec,
            font_size: databaseFontSize,
            line_height: databaseFontSize * lineHeightRatio,
          }
        : prevMeta.typesetting_spec;
      useProjectStore.getState().syncAutoFitFontSize(textbox.data.blockId, databaseFontSize);
      if (!_skipBackendUpdate) {
        void useProjectStore.getState().updateBlock(textbox.data.blockId, {
          font_size: databaseFontSize,
          extra_metadata: {
            ...prevMeta,
            typesetting_spec: syncedSpec,
            manual_font_size: null,
            font_size_mode: 'auto',
          },
        }, true);
      }
    }
  }
};

// Measuring wrapped Fabric text is relatively expensive. Coalesce rapid
// keystrokes so typing does not run the complete binary-search fitter on every
// input event. A final synchronous fit still runs when editing ends.
const pendingAutoFitTimers = new WeakMap<object, ReturnType<typeof setTimeout>>();

export const scheduleAutoFitTextboxFontSize = (textbox: fabric.Textbox, canvas: fabric.Canvas, sf: number) => {
  const pending = pendingAutoFitTimers.get(textbox);
  if (pending) clearTimeout(pending);

  const timer = setTimeout(() => {
    pendingAutoFitTimers.delete(textbox);
    if (!textbox.canvas || textbox.canvas !== canvas) return;
    autoFitTextboxFontSize(textbox, canvas, sf, true);
    canvas.requestRenderAll();
  }, 80);
  pendingAutoFitTimers.set(textbox, timer);
};

export const cancelScheduledAutoFit = (textbox: fabric.Textbox) => {
  const pending = pendingAutoFitTimers.get(textbox);
  if (pending) {
    clearTimeout(pending);
    pendingAutoFitTimers.delete(textbox);
  }
};

const Canvas: React.FC<CanvasProps> = ({ onOpenMaskEditor, onRunOCR, onRunInpaintPreview, onEnsureInpainted, onRunFontJudge, deferAutomaticFullCleanForPageId: _deferAutomaticFullCleanForPageId, onRefreshPage, onRefitPageText, onResetPageMasks, onResetProjectMasks, liveMaskOverlay = false, cleanPreviewRevision = 0, cleanPreviewRequest = null, showBottomPageNavigator = true, useTypesettingLayout = true, showFloatingLetteringBar = true, onCloseFloatingLetteringBar }) => {
  const canvasElRef = useRef<HTMLCanvasElement>(null);
  const fabricCanvasRef = useRef<fabric.Canvas | null>(null);
  const workspaceRef = useRef<HTMLDivElement>(null);
  const [imgDimensions, setImgDimensions] = useState<{ width: number; height: number }>({ width: 750, height: 1000 });
  const imgDimensionsRef = useRef<{ width: number; height: number }>({ width: 750, height: 1000 });
  
  const activePage = useProjectStore((state) => state.activePage);
  const selectedBlock = useProjectStore((state) => state.selectedBlock);
  const selectedBlocks = useProjectStore((state) => state.selectedBlocks);
  const updateBlock = useProjectStore((state) => state.updateBlock);
  const deleteBlocks = useProjectStore((state) => state.deleteBlocks);
  const createBlock = useProjectStore((state) => state.createBlock);
  const setStatus = useProjectStore((state) => state.setStatus);
  const activeProject = useProjectStore((state) => state.activeProject);
  const selectPage = useProjectStore((state) => state.selectPage);
  
  const storeZoom = useProjectStore((state) => state.zoomLevel);
  const keyBindings = useProjectStore((state) => state.keyBindings);
  const setStoreZoom = useProjectStore((state) => state.setZoomLevel);
  const zoomFrameRef = useRef<number | null>(null);
  const pendingZoomRef = useRef<number | null>(null);
  const zoomLevelRef = useRef<number>(1);
  const canvasRetinaScaleRef = useRef<number>(1);
  
  const [scaleFactor, setScaleFactor] = useState<number>(1.0);
  const scaleFactorRef = useRef<number>(1.0);
  
  useEffect(() => {
    injectFontStylesheet();
  }, []);

  const [isZoomAutoFit, setIsZoomAutoFit] = useState<boolean>(true);
  const isZoomAutoFitRef = useRef<boolean>(true);
  useEffect(() => {
    isZoomAutoFitRef.current = isZoomAutoFit;
  }, [isZoomAutoFit]);
  
  const zoomLevel = storeZoom !== null ? storeZoom : 1.0;
  zoomLevelRef.current = zoomLevel;
  const setZoomLevel = (valOrFunc: number | ((prev: number) => number)) => {
    if (typeof valOrFunc === 'function') {
      const currentZoom = useProjectStore.getState().zoomLevel ?? 1.0;
      setStoreZoom(valOrFunc(currentZoom));
    } else {
      setStoreZoom(valOrFunc);
    }
  };
  
  // Canvas mode. Full-page mask editing owns its lifecycle in usePageMaskEditor.
  const [canvasMode, setCanvasMode] = useState<'select' | 'text' | 'drawBlock'>('select');
  const canvasModeRef = useRef<'select' | 'text' | 'drawBlock'>('select');
  const isMaskModeRef = useRef<boolean>(false);
  const [isBalloonLayoutMode, setIsBalloonLayoutMode] = useState(false);
  const [isBalloonSegmenting, setIsBalloonSegmenting] = useState(false);
  const [isBalloonSizeUpdating, setIsBalloonSizeUpdating] = useState(false);
  const [balloonSelection, setBalloonSelection] = useState<{
    startX: number;
    startY: number;
    currentX: number;
    currentY: number;
  } | null>(null);
  const balloonSelectionRef = useRef<typeof balloonSelection>(null);
  const {
    isActive: isMaskMode,
    setIsActive: setIsMaskMode,
    tool: maskTool,
    setTool: setMaskTool,
    brushSize: pageBrushSize,
    setBrushSize: setPageBrushSize,
    opacity: pageMaskOpacity,
    setOpacity: setPageMaskOpacity,
    isDetecting: isMaskDetecting,
    isSaving: isMaskSaving,
    canUndo: canMaskUndo,
    canvasRef: pageMaskCanvasRef,
    cursorRef: pageMaskCursorRef,
    clear: handleClearPageMask,
    undo: handleUndoPageMask,
    autoDetect: handlePageAutoMask,
    saveAndClean: handleSavePageMaskAndClean,
    onPointerDown: handlePageMaskPointerDown,
    onPointerMove: handlePageMaskPointerMove,
    onPointerUp: handlePageMaskPointerUp,
    onPointerCancel: handlePageMaskPointerCancel,
    onPointerLeave: handlePageMaskPointerLeave,
  } = usePageMaskEditor({
    pageId: activePage?.id,
    imageDimensions: imgDimensions,
    onStatus: setStatus,
    onSaved: async () => {
      setCleanImageVersion(Date.now());
      await onRefreshPage?.();
    },
  });
  
  // Snapping and Keyboard Shortcuts states/refs
  const [showShortcutsModal, setShowShortcutsModal] = useState<boolean>(false);
  const [shortcutsOverlayCollapsed, setShortcutsOverlayCollapsed] = useState<boolean>(() => {
    try {
      return localStorage.getItem('houmi_shortcuts_collapsed') === 'true';
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem('houmi_shortcuts_collapsed', String(shortcutsOverlayCollapsed));
    } catch (e) {
      console.warn(e);
    }
  }, [shortcutsOverlayCollapsed]);

  const alignmentGuidesRef = useRef<{ type: 'v' | 'h'; val: number }[]>([]);
  const interactionActiveRef = useRef(false);
  const activeInteractionObjectRef = useRef<fabric.FabricObject | null>(null);

  // Bottom Bar display controls
  const [showTranslated, setShowTranslated] = useState<boolean>(() => {
    try {
      const saved = localStorage.getItem('houmi_show_translated');
      return saved !== null ? saved === 'true' : false;
    } catch {
      return false;
    }
  });
  const [showTypesetting, setShowTypesetting] = useState<boolean>(() => {
    try {
      const saved = localStorage.getItem('houmi_show_typesetting');
      return saved !== null ? saved === 'true' : true;
    } catch {
      return true;
    }
  });
  // Clean preview mode must ALWAYS default to false (Original image) on startup.
  // It is only enabled on-demand when the user explicitly clicks the toggle or saves a mask.
  const [showInpainted, setShowInpainted] = useState<boolean>(() => {
    try {
      localStorage.removeItem('houmi_show_inpainted');
    } catch {
      // ignore
    }
    return false;
  });
  const [isPreparingInpainted, setIsPreparingInpainted] = useState(false);
  const [cleanImageVersion, setCleanImageVersion] = useState(0);
  const [cleanImageUnavailable, setCleanImageUnavailable] = useState(false);
  const [cleanJustFinished, setCleanJustFinished] = useState(false);
  const handledCleanPreviewRequestRef = useRef<number | null>(null);
  const blockRenderSignaturesRef = useRef<Map<string, string>>(new Map());
  const blockRenderContextRef = useRef('');
  const isExportCaptureRef = useRef(false);
  const lastPageIdRef = useRef<string | null>(null);
  const lastScrollPosRef = useRef<{ scrollTop: number; scrollLeft: number }>({ scrollTop: 0, scrollLeft: 0 });

  // Mask badge tooltip state
  const [maskTooltip, setMaskTooltip] = useState<{ x: number; y: number; type: string; blockId: string } | null>(null);

  // Seed the imperative refs from the persisted React state. A new Fabric
  // canvas is created for every page, so hard-coded ref defaults made an
  // already-enabled mode behave as if it were off until the user toggled it.
  const showTranslatedRef = useRef<boolean>(showTranslated);
  const showTypesettingRef = useRef<boolean>(showTypesetting);
  const showInpaintedRef = useRef<boolean>(showInpainted);
  const liveMaskOverlayRef = useRef<boolean>(!!liveMaskOverlay);
  const [isImageLoaded, setIsImageLoaded] = useState<boolean>(false);

  const onEnsureInpaintedRef = useRef(onEnsureInpainted);
  onEnsureInpaintedRef.current = onEnsureInpainted;
  const onRefreshPageRef = useRef(onRefreshPage);
  const lastCleanPreviewRevisionRef = useRef<number>(cleanPreviewRevision || 0);

  // When an external inpaint completion or mask update triggers a new revision, refresh clean cache if active
  useEffect(() => {
    if (cleanPreviewRevision && cleanPreviewRevision > lastCleanPreviewRevisionRef.current) {
      lastCleanPreviewRevisionRef.current = cleanPreviewRevision;
      setCleanImageUnavailable(false);
      setCleanImageVersion(Date.now());
    }
  }, [cleanPreviewRevision]);

  // When switching page or toggling clean mode
  useEffect(() => {
    setCleanImageUnavailable(false);
    setCleanImageVersion(Date.now());
  }, [activePage?.id, activePage?.inpainted_image_path, showInpainted]);

  // Intelligent Adjacent Page Preloader (Phase 9 - Preload adjacent page images into browser HTTP cache)
  useEffect(() => {
    const pages = activeProject?.pages;
    if (!pages || !activePage) return;
    const currentIndex = pages.findIndex(p => p.id === activePage.id);
    if (currentIndex === -1) return;

    // Preload next, previous, and +2 pages ahead for instant switching
    const preloadIndices = [currentIndex + 1, currentIndex - 1, currentIndex + 2];
    preloadIndices.forEach(idx => {
      if (idx >= 0 && idx < pages.length) {
        const p = pages[idx];
        const targetUrl = (showInpainted && p.inpainted_image_path)
          ? `/api/pages/${p.id}/image?clean=true`
          : `/api/pages/${p.id}/preview`;
        const preImg = new Image();
        preImg.decoding = 'async';
        preImg.src = targetUrl;
      }
    });
  }, [activePage?.id, activeProject?.pages, showInpainted]);

  // A custom block mask starts an asynchronous region reclean. Refresh clean cache when ready.
  useEffect(() => {
    if (
      !cleanPreviewRequest
      || cleanPreviewRequest.pageId !== activePage?.id
      || handledCleanPreviewRequestRef.current === cleanPreviewRequest.revision
    ) return;

    handledCleanPreviewRequestRef.current = cleanPreviewRequest.revision;
    setCleanImageUnavailable(false);
    setCleanImageVersion(Date.now());
  }, [activePage?.id, cleanPreviewRequest]);

  const [maskOpacity, setMaskOpacity] = useState<number>(0.6);
  const [maskVisible, setMaskVisible] = useState<boolean>(() => !!liveMaskOverlay);
  const maskOpacityRef = useRef<number>(maskOpacity);
  const maskVisibleRef = useRef<boolean>(maskVisible);

  const isSpacePressedRef = useRef(false);
  const isPanningRef = useRef(false);
  const panStartRef = useRef({ x: 0, y: 0, scrollLeft: 0, scrollTop: 0 });

  useEffect(() => {
    maskOpacityRef.current = maskOpacity;
    fabricCanvasRef.current?.requestRenderAll();
  }, [maskOpacity]);

  useEffect(() => {
    if (liveMaskOverlay !== undefined) {
      setMaskVisible(!!liveMaskOverlay);
    }
  }, [liveMaskOverlay]);

  useEffect(() => {
    maskVisibleRef.current = maskVisible;
    liveMaskOverlayRef.current = maskVisible;
    fabricCanvasRef.current?.requestRenderAll();
  }, [maskVisible]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const isInput = target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable);
      if (!isInput && (e.code === 'Space' || e.key === ' ')) {
        const activeObj = fabricCanvasRef.current?.getActiveObject();
        if (!(activeObj as any)?.isEditing) {
          isSpacePressedRef.current = true;
          if (workspaceRef.current) {
            workspaceRef.current.style.cursor = 'grab';
          }
          if (e.target === document.body || (workspaceRef.current && workspaceRef.current.contains(e.target as Node))) {
            e.preventDefault();
          }
        }
      }
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.code === 'Space' || e.key === ' ') {
        isSpacePressedRef.current = false;
        if (!isPanningRef.current && workspaceRef.current) {
          workspaceRef.current.style.cursor = '';
        }
      }
    };

    const handleWindowMouseMove = (e: MouseEvent) => {
      if (isPanningRef.current && workspaceRef.current) {
        const dx = e.clientX - panStartRef.current.x;
        const dy = e.clientY - panStartRef.current.y;
        workspaceRef.current.scrollLeft = panStartRef.current.scrollLeft - dx;
        workspaceRef.current.scrollTop = panStartRef.current.scrollTop - dy;
        e.preventDefault();
      }
    };

    const handleWindowMouseUp = () => {
      if (isPanningRef.current) {
        isPanningRef.current = false;
        if (workspaceRef.current) {
          workspaceRef.current.style.cursor = isSpacePressedRef.current ? 'grab' : '';
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    window.addEventListener('mousemove', handleWindowMouseMove);
    window.addEventListener('mouseup', handleWindowMouseUp);

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
      window.removeEventListener('mousemove', handleWindowMouseMove);
      window.removeEventListener('mouseup', handleWindowMouseUp);
    };
  }, []);

  useEffect(() => {
    showTranslatedRef.current = showTranslated;
    try {
      localStorage.setItem('houmi_show_translated', String(showTranslated));
    } catch (e) {
      console.warn(e);
    }
  }, [showTranslated]);

  useEffect(() => {
    try {
      localStorage.setItem('houmi_show_typesetting', String(showTypesetting));
    } catch (e) {
      console.warn(e);
    }
  }, [showTypesetting]);

  const handleCleanImageToggle = async (checked: boolean) => {
    setCleanImageUnavailable(false);
    if (!checked) {
      setShowInpainted(false);
      setStatus('แสดงภาพต้นฉบับ', false);
      return;
    }
    setShowInpainted(true);
    if (isPreparingInpainted) return;

    if (!activePage?.inpainted_image_path && onEnsureInpainted) {
      setIsPreparingInpainted(true);
      setStatus('กำลังเตรียมภาพคลีนสำหรับหน้านี้...', true);
      const succeeded = await onEnsureInpainted();
      setIsPreparingInpainted(false);
      if (!succeeded) {
        setStatus('ไม่สามารถสร้างภาพคลีนสำหรับหน้านี้ได้', false);
        return;
      }
      setCleanJustFinished(true);
      setTimeout(() => setCleanJustFinished(false), 2200);
      await onRefreshPage?.();
    }

    setCleanImageUnavailable(false);
    setCleanImageVersion(Date.now());
    setStatus('แสดงภาพคลีน (ลบตัวอักษรแล้ว)', false);
  };

  useEffect(() => {
    liveMaskOverlayRef.current = !!liveMaskOverlay;
    fabricCanvasRef.current?.requestRenderAll();
  }, [liveMaskOverlay]);

  useEffect(() => {
    // Re-apply all display modes to the newly-created page canvas. Besides
    // keeping the refs current, clearing the signature cache guarantees that
    // the first render on the new page is not skipped as an unchanged frame.
    showTranslatedRef.current = showTranslated;
    showTypesettingRef.current = showTypesetting;
    liveMaskOverlayRef.current = !!liveMaskOverlay;
    blockRenderSignaturesRef.current.clear();
    blockRenderContextRef.current = '';
    if (isImageLoaded) fabricCanvasRef.current?.requestRenderAll();
  }, [activePage?.id, showTranslated, showTypesetting, showInpainted, liveMaskOverlay, isImageLoaded]);

  const isProgrammaticSelectionChangeRef = useRef(false);
  const selectionAnchorBlockIdRef = useRef<string | null>(null);
  useEffect(() => {
    selectionAnchorBlockIdRef.current = null;
    setIsBalloonLayoutMode(false);
    setBalloonSelection(null);
    balloonSelectionRef.current = null;
  }, [activePage?.id]);

  const setBalloonSelectionState = (selection: typeof balloonSelection) => {
    balloonSelectionRef.current = selection;
    setBalloonSelection(selection);
  };

  const toggleBalloonLayoutMode = () => {
    if (isBalloonLayoutMode) {
      setIsBalloonLayoutMode(false);
      setBalloonSelectionState(null);
      setStatus('Balloon Layout mode closed', false);
      return;
    }
    if (!selectedBlock) {
      setStatus('Select one text layer before opening Balloon Layout mode', false);
      return;
    }
    setCanvasMode('select');
    setIsMaskMode(false);
    setIsBalloonLayoutMode(true);
    setStatus('Balloon Layout mode ready', false);
  };

  const balloonPoint = (event: React.PointerEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    return {
      x: Math.max(0, Math.min(rect.width, event.clientX - rect.left)),
      y: Math.max(0, Math.min(rect.height, event.clientY - rect.top)),
    };
  };

  const handleBalloonPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!isBalloonLayoutMode || isBalloonSegmenting || event.button !== 0) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    const point = balloonPoint(event);
    setBalloonSelectionState({
      startX: point.x,
      startY: point.y,
      currentX: point.x,
      currentY: point.y,
    });
  };

  const handleBalloonPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const current = balloonSelectionRef.current;
    if (!current || !event.currentTarget.hasPointerCapture(event.pointerId)) return;
    const point = balloonPoint(event);
    setBalloonSelectionState({ ...current, currentX: point.x, currentY: point.y });
  };

  const finishBalloonSelection = async (event: React.PointerEvent<HTMLDivElement>) => {
    const selection = balloonSelectionRef.current;
    if (!selection || !activePage || !selectedBlock || isBalloonSegmenting) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    const rect = event.currentTarget.getBoundingClientRect();
    const left = Math.min(selection.startX, selection.currentX);
    const top = Math.min(selection.startY, selection.currentY);
    const right = Math.max(selection.startX, selection.currentX);
    const bottom = Math.max(selection.startY, selection.currentY);
    if (right - left < 8 || bottom - top < 8 || rect.width <= 0 || rect.height <= 0) {
      setBalloonSelectionState(null);
      setStatus('Balloon selection is too small', false);
      return;
    }

    const sourceWidth = activePage.width || imgDimensions.width * scaleFactorRef.current;
    const sourceHeight = activePage.height || imgDimensions.height * scaleFactorRef.current;
    const payload = {
      x0: Math.round(left * sourceWidth / rect.width),
      y0: Math.round(top * sourceHeight / rect.height),
      x1: Math.round(right * sourceWidth / rect.width),
      y1: Math.round(bottom * sourceHeight / rect.height),
    };
    setIsBalloonSegmenting(true);
    setStatus('Segmenting balloon and fitting text...', true);
    try {
      const response = await apiFetch(`/api/blocks/${selectedBlock.id}/layout/segment`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const result = await response.json().catch(() => ({})) as { layout_region?: { width: number; height: number } };
      await onRefreshPage?.();
      blockRenderSignaturesRef.current.delete(selectedBlock.id);
      const dimensionsMsg = result.layout_region ? ` (${Math.round(result.layout_region.width)}×${Math.round(result.layout_region.height)} px)` : '';
      setStatus(`🎈 Smart Balloon applied${dimensionsMsg}`, false);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Failed to segment balloon', false);
    } finally {
      setIsBalloonSegmenting(false);
      setBalloonSelectionState(null);
    }
  };

  // Find Balloon states
  const [showFindModal, setShowFindModal] = useState<boolean>(false);
  const [findText, setFindText] = useState<string>('');
  const [findIndex, setFindIndex] = useState<number>(0);
  const findInputRef = useRef<HTMLInputElement>(null);
  const pendingWarpBlockIdRef = useRef<string | null>(null);
  const [contextMenu, setContextMenu] = useState<{
    x: number;
    y: number;
    blockId?: string;
  } | null>(null);

  useEffect(() => {
    const handleWindowClick = () => {
      setContextMenu(null);
    };
    window.addEventListener('click', handleWindowClick);
    return () => {
      window.removeEventListener('click', handleWindowClick);
    };
  }, []);

  // Expose the exact text overlay produced by the live Fabric/Chromium
  // renderer. The backend composites this transparent PNG over the original
  // clean image; it must never lay the text out a second time with Pillow.
  useEffect(() => {
    if (!activePage || !isImageLoaded) {
      useProjectStore.setState({ getCanvasRenderCapture: null, canvasRenderPageId: null });
      return;
    }

    const capturePageId = activePage.id;
    useProjectStore.setState({
      canvasRenderPageId: capturePageId,
      getCanvasRenderCapture: async (forceTranslated = true) => {
        const canvas = fabricCanvasRef.current;
        const currentPage = useProjectStore.getState().activePage;
        if (!canvas || !currentPage || currentPage.id !== capturePageId) return null;

        // Final output is translated output. If the user was reviewing source
        // text, switch the live canvas once and wait until every Fabric object
        // reflects the translated canonical spec before capturing it.
        if (forceTranslated && !showTranslatedRef.current) {
          setShowTranslated(true);
          let synchronized = false;
          for (let frame = 0; frame < 60; frame += 1) {
            await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
            const byId = new Map<string, fabric.Textbox>();
            canvas.getObjects().forEach((obj: any) => {
              if (obj.type === 'textbox' && obj.data?.blockId) byId.set(obj.data.blockId, obj);
            });
            synchronized = showTranslatedRef.current && currentPage.text_blocks.every((block) => (
              byId.get(block.id)?.text === resolveCanvasTextView(block, true).text
            ));
            if (synchronized) break;
          }
          if (!synchronized) throw new Error('Translated preview did not finish synchronizing');
        }

        const textboxes = canvas.getObjects().filter((obj: any) => (
          obj.type === 'textbox' && obj.visible && Boolean(obj.data?.blockId)
        )) as fabric.Textbox[];

        // Font loading is asynchronous in Chromium. Capturing before it has
        // completed is a common source of one-frame fallback-font exports.
        if (document.fonts) {
          injectFontStylesheet();
          await ensureMultipleFontsLoaded(
            textboxes.map((tb) => ({
              family: tb.fontFamily || 'sans-serif',
              weight: tb.fontWeight || 'normal',
              style: tb.fontStyle || 'normal',
              text: tb.text || 'ก',
            }))
          );
        }

        textboxes.forEach((textbox) => {
          (textbox as any).initDimensions?.();
          textbox.setCoords();
        });

        await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));

        const activeObject = canvas.getActiveObject();
        const wasEditing = Boolean((activeObject as any)?.isEditing);
        const selectionStart = (activeObject as any)?.selectionStart;
        const selectionEnd = (activeObject as any)?.selectionEnd;
        const multiplier = scaleFactorRef.current;
        isExportCaptureRef.current = true;
        let restoreTextboxDecorations: (() => void) | null = null;

        try {
          if (wasEditing) (activeObject as any).exitEditing?.();
          canvas.discardActiveObject();
          restoreTextboxDecorations = suppressTextboxDecorationsForCapture(textboxes);
          canvas.renderAll();

          let outputCanvas = canvas.toCanvasElement(multiplier, {
            filter: (obj: any) => (
              obj.type === 'textbox'
              && obj.visible
              && Boolean(obj.data?.blockId)
              && Boolean(obj.data?.hasFinalTranslation)
            ),
          });

          // Adaptive preview dimensions are rounded. Normalize a possible
          // one-pixel rounding difference to the authoritative source size.
          if (outputCanvas.width !== currentPage.width || outputCanvas.height !== currentPage.height) {
            const normalized = document.createElement('canvas');
            normalized.width = currentPage.width;
            normalized.height = currentPage.height;
            const context = normalized.getContext('2d');
            if (!context) throw new Error('Unable to create final render canvas');
            context.drawImage(outputCanvas, 0, 0, normalized.width, normalized.height);
            outputCanvas = normalized;
          }

          const blob = await new Promise<Blob>((resolve, reject) => {
            outputCanvas.toBlob((result) => {
              if (result) resolve(result);
              else reject(new Error('Browser failed to encode the render overlay'));
            }, 'image/png');
          });

          return {
            pageId: capturePageId,
            blob,
            backgroundKind: currentPage.inpainted_image_path ? 'clean' : 'source',
          };
        } finally {
          restoreTextboxDecorations?.();
          isExportCaptureRef.current = false;
          if (activeObject) {
            canvas.setActiveObject(activeObject);
            if (wasEditing) {
              (activeObject as any).enterEditing?.();
              if (typeof selectionStart === 'number') (activeObject as any).selectionStart = selectionStart;
              if (typeof selectionEnd === 'number') (activeObject as any).selectionEnd = selectionEnd;
            }
          }
          canvas.requestRenderAll();
        }
      },
    });

    return () => {
      const state = useProjectStore.getState();
      if (state.canvasRenderPageId === capturePageId) {
        useProjectStore.setState({ getCanvasRenderCapture: null, canvasRenderPageId: null });
      }
    };
  }, [activePage?.id, activePage?.inpainted_image_path, isImageLoaded]);

  // Sync mode reference & Canvas Configurations
  useEffect(() => {
    showTypesettingRef.current = showTypesetting;
    canvasModeRef.current = canvasMode;
    
    const canvas = fabricCanvasRef.current;
    if (!canvas) return;
    
    // Never draw unmanaged Fabric paths over the page. Those paths were not a
    // saved inpaint mask and made the old “Mask Brush” button look functional
    // while producing no editable result.
    canvas.isDrawingMode = false;
    
    // Toggle Selectability of Textboxes based on mode and typesetting mode (disable in mask mode)
    const isInteractive = (canvasMode === 'select' || canvasMode === 'text') && (showTypesetting || !showTranslated) && !isMaskMode;
    const textEditingOnly = canvasMode === 'text';
    canvas.selection = isInteractive && !textEditingOnly;
    canvas.getObjects().forEach((obj: any) => {
      if (obj.type === 'textbox') {
        obj.selectable = isInteractive && obj.visible;
        obj.evented = isInteractive && obj.visible;
        obj.editable = showTypesetting && canvasMode === 'text';
        obj.lockMovementX = textEditingOnly;
        obj.lockMovementY = textEditingOnly;
        obj.lockRotation = textEditingOnly;
        obj.lockScalingX = textEditingOnly;
        obj.lockScalingY = textEditingOnly;
        obj.hasControls = !textEditingOnly;
        obj.setControlsVisibility(textEditingOnly
          ? { tl: false, tr: false, bl: false, br: false, mt: false, mb: false, ml: false, mr: false, mtr: false }
          : { tl: true, tr: true, bl: true, br: true, mt: true, mb: true, ml: true, mr: true, mtr: true });
        if (obj.controls?.mtr) obj.controls.mtr.render = renderRotateIcon;
      } else {
        // Paths and other objects should not be selectable or block drag selection
        obj.selectable = false;
        obj.evented = false;
      }
    });

    // Apply native Fabric default and hover cursors based on canvasMode and isMaskMode
    const currentCursor = isMaskMode
      ? 'crosshair'
      : canvasMode === 'text'
        ? 'text'
      : canvasMode === 'drawBlock'
        ? 'cell'
        : 'default';
    canvas.defaultCursor = currentCursor;
    canvas.hoverCursor = isInteractive ? 'pointer' : 'default';

    canvas.requestRenderAll();
  }, [canvasMode, showTypesetting, showTranslated, isMaskMode, activePage?.id, isImageLoaded]);

  // showInpainted is declared above with persistence

  // Deriving matching blocks for the Find Balloon feature across all pages in the project
  const matchingBlocks = findText.trim() && activeProject ? (
    activeProject.pages.flatMap(page => 
      (page.text_blocks || [])
        .filter(b => 
          (b.source_text && b.source_text.toLowerCase().includes(findText.toLowerCase())) ||
          (b.translation && b.translation.toLowerCase().includes(findText.toLowerCase()))
        )
        .map(block => ({
          pageId: page.id,
          pageNumber: page.page_number,
          pageName: page.name || `Page ${page.page_number}`,
          block
        }))
    )
  ) : [];

  const warpToBlock = (block: TextBlock) => {
    useProjectStore.setState({ selectedBlock: block, selectedBlocks: [block] });

    const canvas = fabricCanvasRef.current;
    if (canvas) {
      const found = canvas.getObjects().find(o => (o as any).data?.blockId === block.id);
      if (found) {
        canvas.setActiveObject(found);
        canvas.requestRenderAll();
      }
    }

    const workspace = workspaceRef.current;
    if (workspace) {
      const blockCenterX = (block.x + block.width / 2) / scaleFactorRef.current * zoomLevel;
      const blockCenterY = (block.y + block.height / 2) / scaleFactorRef.current * zoomLevel;
      
      const viewW = workspace.clientWidth;
      const viewH = workspace.clientHeight;
      
      workspace.scrollLeft = blockCenterX + 40 - viewW / 2;
      workspace.scrollTop = blockCenterY + 40 - viewH / 2;
    }
  };

  const navigateToMatch = async (match: { pageId: string; block: TextBlock }) => {
    if (!activePage) return;
    if (activePage.id === match.pageId) {
      warpToBlock(match.block);
    } else {
      pendingWarpBlockIdRef.current = match.block.id;
      await useProjectStore.getState().selectPage(match.pageId);
    }
  };

  useEffect(() => {
    if (isImageLoaded && pendingWarpBlockIdRef.current && activePage) {
      const targetId = pendingWarpBlockIdRef.current;
      pendingWarpBlockIdRef.current = null;
      const block = activePage.text_blocks.find(b => b.id === targetId);
      if (block) {
        warpToBlock(block);
      }
    }
  }, [isImageLoaded, activePage?.id]);

  const navigateFind = (direction: 'next' | 'prev') => {
    if (matchingBlocks.length === 0) return;
    let nextIdx = findIndex;
    if (direction === 'next') {
      nextIdx = (findIndex + 1) % matchingBlocks.length;
    } else {
      nextIdx = (findIndex - 1 + matchingBlocks.length) % matchingBlocks.length;
    }
    setFindIndex(nextIdx);
    navigateToMatch(matchingBlocks[nextIdx]);
  };

  const handleFindKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (matchingBlocks.length > 0) {
        if (e.shiftKey) {
          navigateFind('prev');
        } else {
          navigateFind('next');
        }
      }
    } else if (e.key === 'Escape') {
      setShowFindModal(false);
      e.preventDefault();
      workspaceRef.current?.focus();
    }
  };

  // Sync drag mode reference
  useEffect(() => {
    isMaskModeRef.current = isMaskMode;
  }, [isMaskMode]);

  // Keyboard Shortcuts (Figma/Photoshop Standards + Quick Typesetting Mode)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      // If typing inside an input/textarea, skip shortcuts except Escape, Enter, Tab
      const isInput = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable;

      // Find Balloon Shortcut (Custom key binding)
      if (matchBinding(keyBindings.findBalloon, e)) {
        e.preventDefault();
        setShowFindModal(true);
        setTimeout(() => {
          findInputRef.current?.focus();
          findInputRef.current?.select();
        }, 50);
        return;
      }

      // Export OCR Shortcut (Custom key binding)
      if (matchBinding(keyBindings.exportOcrTxt, e)) {
        e.preventDefault();
        return;
      }

      // Undo/Redo Shortcuts (Custom key bindings & fallback defaults)
      const isUndoKey = matchBinding(keyBindings.undo, e) || ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z' && !e.shiftKey);
      const isRedoKey = matchBinding(keyBindings.redo, e) || ((e.ctrlKey || e.metaKey) && (e.key.toLowerCase() === 'y' || (e.key.toLowerCase() === 'z' && e.shiftKey)));

      if (isUndoKey) {
        if (!isInput) {
          e.preventDefault();
          useProjectStore.getState().undo();
          return;
        }
      }
      if (isRedoKey) {
        if (!isInput) {
          e.preventDefault();
          useProjectStore.getState().redo();
          return;
        }
      }

      if (matchBinding(keyBindings.deselectBlock, e) || e.key === 'Escape') {
        if (showFindModal) {
          setShowFindModal(false);
          e.preventDefault();
          return;
        }
        const activeObj = fabricCanvasRef.current?.getActiveObject();
        if (activeObj) {
          if ((activeObj as any).isEditing) {
            (activeObj as any).exitEditing();
          }
          fabricCanvasRef.current?.discardActiveObject();
          fabricCanvasRef.current?.requestRenderAll();
        }
        useProjectStore.setState({ selectedBlock: null, selectedBlocks: [] });
        if (isInput) target.blur();
        e.preventDefault();
        return;
      }

      // Photoshop-style Text Tool. T activates text editing; if a layer is
      // already selected it enters editing immediately, otherwise the next
      // textbox click chooses the insertion point.
      if (!isInput && !(fabricCanvasRef.current?.getActiveObject() as any)?.isEditing && matchBinding(keyBindings.textEditMode, e)) {
        e.preventDefault();
        setCanvasMode('text');
        setIsMaskMode(false);
        setShowTypesetting(true);
        const blockId = useProjectStore.getState().selectedBlock?.id;
        if (blockId) {
          requestAnimationFrame(() => {
            const canvas = fabricCanvasRef.current;
            const textbox = canvas?.getObjects().find(object => (object as any).data?.blockId === blockId) as any;
            if (!canvas || !textbox || textbox.type !== 'textbox') return;
            textbox.set({ editable: true });
            canvas.setActiveObject(textbox);
            textbox.enterEditing();
            textbox.focus();
            canvas.requestRenderAll();
          });
        }
        return;
      }

      if (e.key === 'Enter' && !e.shiftKey) {
        if (!isInput && selectedBlock && canvasModeRef.current === 'text') {
          const canvas = fabricCanvasRef.current;
          if (canvas) {
            const found = canvas.getObjects().find(o => (o as any).data?.blockId === selectedBlock.id);
            if (found && found.type === 'textbox') {
              canvas.setActiveObject(found);
              (found as any).enterEditing();
              (found as any).focus();
              canvas.requestRenderAll();
              e.preventDefault();
            }
          }
        }
        return;
      }

      const isCycleNext = matchBinding(keyBindings.cycleNextBlock, e);
      const isCyclePrev = matchBinding(keyBindings.cyclePrevBlock, e);
      if (isCycleNext || isCyclePrev) {
        if (activePage && activePage.text_blocks.length > 0) {
          const blocks = [...activePage.text_blocks].sort((a, b) => a.block_index - b.block_index);
          const currentIndex = selectedBlock ? blocks.findIndex(b => b.id === selectedBlock.id) : -1;
          
          let nextIndex = 0;
          if (isCyclePrev) {
            nextIndex = currentIndex - 1;
            if (nextIndex < 0) nextIndex = blocks.length - 1;
          } else {
            nextIndex = currentIndex + 1;
            if (nextIndex >= blocks.length) nextIndex = 0;
          }
          
          const nextBlock = blocks[nextIndex];
          useProjectStore.setState({ selectedBlock: nextBlock, selectedBlocks: [nextBlock] });
          
          const canvas = fabricCanvasRef.current;
          if (canvas) {
            const found = canvas.getObjects().find(o => (o as any).data?.blockId === nextBlock.id);
            if (found) {
              canvas.setActiveObject(found);
              canvas.requestRenderAll();
              if (isInput && found.type === 'textbox') {
                (found as any).enterEditing();
                (found as any).focus();
              }
            }
          }
          e.preventDefault();
        }
        return;
      }

      if (isInput || (fabricCanvasRef.current?.getActiveObject() as any)?.isEditing) {
        return;
      }

      // Style Copy & Paste (Ctrl+C / Ctrl+V)
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'c') {
        const activeObj = fabricCanvasRef.current?.getActiveObject();
        if (activeObj && selectedBlock) {
          e.preventDefault();
          const copiedStyle = {
            font_family: selectedBlock.font_family,
            font_size: selectedBlock.font_size,
            color_hex: selectedBlock.color_hex,
            bold: selectedBlock.bold,
            italic: selectedBlock.italic,
            text_align: selectedBlock.text_align,
            text_direction: selectedBlock.text_direction,
            balloon_type: selectedBlock.balloon_type,
          };
          localStorage.setItem('houmi_copied_style', JSON.stringify(copiedStyle));
          setStatus("Copied styles to clipboard", false);
        }
      }

      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'v') {
        const savedStyleStr = localStorage.getItem('houmi_copied_style');
        if (savedStyleStr && (selectedBlock || selectedBlocks.length > 0)) {
          e.preventDefault();
          try {
            const copiedStyle = JSON.parse(savedStyleStr);
            setStatus("Pasting styles...", false);
            const targets = selectedBlocks.length > 0 ? selectedBlocks : (selectedBlock ? [selectedBlock] : []);
            (async () => {
              for (const b of targets) {
                await updateBlock(b.id, copiedStyle);
              }
              setStatus("Pasted styles successfully", false);
            })();
          } catch (err) {
            console.error("Failed to parse copied style:", err);
          }
        }
      }

      // Duplicate Block (Ctrl+D)
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'd') {
        if (selectedBlock && activePage) {
          e.preventDefault();
          createBlock(activePage.id, {
            x: selectedBlock.x + 20,
            y: selectedBlock.y + 20,
            width: selectedBlock.width,
            height: selectedBlock.height,
            source_text: selectedBlock.source_text,
            translation: selectedBlock.translation,
            font_family: selectedBlock.font_family,
            font_size: selectedBlock.font_size,
            color_hex: selectedBlock.color_hex || selectedBlock.font_color || '#000000',
            stroke_color: selectedBlock.stroke_color,
            stroke_width: selectedBlock.stroke_width,
            text_align: selectedBlock.text_align,
            text_direction: selectedBlock.text_direction || 'horizontal',
          });
          setStatus("Duplicated block", false);
          return;
        }
      }

      // Merge Blocks (Ctrl+M)
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'm') {
        if (selectedBlocks.length > 1 && activePage) {
          e.preventDefault();
          useProjectStore.getState().mergeBlocks(activePage.id, selectedBlocks.map(b => b.id));
          return;
        }
      }

      if (matchBinding(keyBindings.selectMode, e)) {
        setCanvasMode('select');
        setIsMaskMode(false);
      }
      if (matchBinding(keyBindings.drawBoxMode, e)) {
        setCanvasMode('select');
        setIsMaskMode(false);
      }
      if (matchBinding(keyBindings.brushMode, e)) {
        const blockId = useProjectStore.getState().selectedBlock?.id;
        if (blockId && onOpenMaskEditor) {
          e.preventDefault();
          onOpenMaskEditor(blockId);
        } else {
          setStatus('Select one text layer before opening Mask Editor', false);
        }
        return;
      }
      if (matchBinding(keyBindings.toggleInpainted, e) || (!e.ctrlKey && !e.altKey && !e.metaKey && e.key.toLowerCase() === 'a')) {
        void handleCleanImageToggle(!showInpainted);
        e.preventDefault();
      }
      if (matchBinding(keyBindings.toggleTranslated, e)) {
        setShowTranslated(prev => !prev);
        e.preventDefault();
      }
      if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) {
        const canvas = fabricCanvasRef.current;
        const activeObj = canvas?.getActiveObject();
        if (canvas && activeObj) {
          e.preventDefault();
          const nudgeVal = e.shiftKey ? 10 : 1;
          
          if (e.key === 'ArrowLeft') {
            activeObj.set({ left: (activeObj.left || 0) - nudgeVal });
          } else if (e.key === 'ArrowRight') {
            activeObj.set({ left: (activeObj.left || 0) + nudgeVal });
          } else if (e.key === 'ArrowUp') {
            activeObj.set({ top: (activeObj.top || 0) - nudgeVal });
          } else if (e.key === 'ArrowDown') {
            activeObj.set({ top: (activeObj.top || 0) + nudgeVal });
          }
          
          activeObj.setCoords();
          canvas.requestRenderAll();
          canvas.fire('object:modified', { target: activeObj });
        }
        return;
      }
      if (isMaskMode) {
        if (e.key === '[') {
          e.preventDefault();
          setPageBrushSize(prev => Math.max(2, prev - 4));
          return;
        }
        if (e.key === ']') {
          e.preventDefault();
          setPageBrushSize(prev => Math.min(120, prev + 4));
          return;
        }
      }
      if (matchBinding(keyBindings.deleteBlock, e)) {
        handleDeleteBox();
      }
    };

    const handleKeyUp = (_e: KeyboardEvent) => {
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, [selectedBlock, activePage, showInpainted, showFindModal]);

  // Zoom on Ctrl + Mouse Wheel (Figma Style with zoom-to-mouse centering)
  useEffect(() => {
    const el = workspaceRef.current;
    if (!el) return;

    const handleWheel = (e: WheelEvent) => {
      if (e.ctrlKey) {
        e.preventDefault();
        const factor = e.deltaY < 0 ? 1.15 : 0.85;
        
        setIsZoomAutoFit(false);
        
        const previousZoom = pendingZoomRef.current ?? useProjectStore.getState().zoomLevel ?? 1.0;
        let nextZoom = previousZoom * factor;
        if (nextZoom > 6.0) nextZoom = 6.0;
        if (nextZoom < 0.05) nextZoom = 0.05;
        pendingZoomRef.current = nextZoom;
          
          // Get mouse cursor position relative to workspace window
          const rect = el.getBoundingClientRect();
          const mouseX = e.clientX - rect.left;
          const mouseY = e.clientY - rect.top;
          
          // Calculate where the cursor points in unzoomed canvas space
          const canvasX = (mouseX + el.scrollLeft) / previousZoom;
          const canvasY = (mouseY + el.scrollTop) / previousZoom;
          
          // Instantly adjust scroll coordinates on next frame so zoom remains centered on pointer
          requestAnimationFrame(() => {
            el.scrollLeft = canvasX * nextZoom - mouseX;
            el.scrollTop = canvasY * nextZoom - mouseY;
          });
        if (zoomFrameRef.current === null) {
          zoomFrameRef.current = requestAnimationFrame(() => {
            const zoom = pendingZoomRef.current;
            pendingZoomRef.current = null;
            zoomFrameRef.current = null;
            if (zoom !== null) setStoreZoom(zoom);
          });
        }
      }
    };

    el.addEventListener('wheel', handleWheel, { passive: false });
    return () => {
      el.removeEventListener('wheel', handleWheel);
      if (zoomFrameRef.current !== null) cancelAnimationFrame(zoomFrameRef.current);
      zoomFrameRef.current = null;
      pendingZoomRef.current = null;
    };
  }, [isImageLoaded, setIsZoomAutoFit]);

  // Pan / Scroll Canvas by dragging (Figma Style)
  useEffect(() => {
    const el = workspaceRef.current;
    if (!el) return;

    let isDown = false;
    let startX: number;
    let startY: number;
    let scrollLeft: number;
    let scrollTop: number;

    const handleMouseDown = (e: MouseEvent) => {
      const isMiddleClick = e.button === 1;
      const isSpacePan = e.button === 0 && isSpacePressedRef.current;
      const isAltPan = e.altKey;

      if (isMiddleClick || isSpacePan || isAltPan) {
        isDown = true;
        el.style.cursor = 'grabbing';
        startX = e.pageX - el.offsetLeft;
        startY = e.pageY - el.offsetTop;
        scrollLeft = el.scrollLeft;
        scrollTop = el.scrollTop;
        e.preventDefault();
      }
    };

    const handleMouseLeave = () => {
      isDown = false;
      el.style.cursor = isMaskModeRef.current ? 'crosshair' : 'default';
    };

    const handleMouseUp = () => {
      isDown = false;
      el.style.cursor = isMaskModeRef.current ? 'crosshair' : 'default';
    };

    const handleMouseMove = (e: MouseEvent) => {
      if (!isDown) return;
      e.preventDefault();
      const x = e.pageX - el.offsetLeft;
      const y = e.pageY - el.offsetTop;
      const walkX = (x - startX) * 1.5;
      const walkY = (y - startY) * 1.5;
      el.scrollLeft = scrollLeft - walkX;
      el.scrollTop = scrollTop - walkY;
    };

    el.addEventListener('mousedown', handleMouseDown);
    el.addEventListener('mouseleave', handleMouseLeave);
    el.addEventListener('mouseup', handleMouseUp);
    el.addEventListener('mousemove', handleMouseMove);

    return () => {
      el.removeEventListener('mousedown', handleMouseDown);
      el.removeEventListener('mouseleave', handleMouseLeave);
      el.removeEventListener('mouseup', handleMouseUp);
      el.removeEventListener('mousemove', handleMouseMove);
    };
  }, [isImageLoaded]);

  // Update Fabric click coordinates offset cache when zoomLevel, page, window, or workspace container resizes
  useEffect(() => {
    const canvas = fabricCanvasRef.current;
    if (!canvas) return;

    // Recalculate immediately
    canvas.calcOffset();

    const handleResize = () => {
      canvas.calcOffset();
      if (isZoomAutoFitRef.current && imgDimensionsRef.current.width > 0 && workspaceRef.current) {
        const wsWidth = workspaceRef.current.clientWidth || 700;
        let newZoom = Math.min(1.0, (wsWidth - 80) / imgDimensionsRef.current.width);
        if (newZoom < 0.05) newZoom = 0.05;
        setZoomLevel(newZoom);
      }
    };

    window.addEventListener('resize', handleResize);

    // Use ResizeObserver to detect layout changes (like sidebar toggles) affecting container size
    const container = workspaceRef.current;
    let observer: ResizeObserver | null = null;
    if (container) {
      observer = new ResizeObserver(() => {
        canvas.calcOffset();
        if (isZoomAutoFitRef.current && imgDimensionsRef.current.width > 0) {
          const wsWidth = container.clientWidth || 700;
          let newZoom = Math.min(1.0, (wsWidth - 80) / imgDimensionsRef.current.width);
          if (newZoom < 0.05) newZoom = 0.05;
          setZoomLevel(newZoom);
        }
      });
      observer.observe(container);
    }

    return () => {
      window.removeEventListener('resize', handleResize);
      if (observer) {
        observer.disconnect();
      }
    };
  }, [zoomLevel, activePage?.id]);

  // Expose base64 mask generation to Zustand store
  useEffect(() => {
    useProjectStore.setState({
      getCanvasMaskBlob: async () => {
        const canvas = fabricCanvasRef.current;
        if (!canvas) return null;

        const objects = canvas.getObjects();
        const maskPaths = objects.filter((obj) => obj.type === 'path');
        if (maskPaths.length === 0) return null;
        const originalStates = new Map<any, { visible: boolean; stroke?: any; fill?: any }>();
        const activeObj = canvas.getActiveObject();
        canvas.discardActiveObject();

        const oldBgColor = canvas.backgroundColor;

        // Save current zoom and dimensions
        const oldZoom = canvas.getZoom();
        const oldWidth = canvas.getWidth();
        const oldHeight = canvas.getHeight();

        // Temporarily reset zoom to 1.0 and size to logical dimensions for export
        canvas.setZoom(1.0);
        const logicalW = imgDimensionsRef.current.width;
        const logicalH = imgDimensionsRef.current.height;
        canvas.setDimensions({ width: logicalW, height: logicalH });

        // Set background color to black
        canvas.backgroundColor = '#000000';

        // Filter and make paths solid white, hide textboxes
        objects.forEach((obj: any) => {
          originalStates.set(obj, {
            visible: obj.visible,
            stroke: obj.stroke,
            fill: obj.fill
          });
          
          if (obj.type === 'path') {
            obj.set({
              stroke: '#ffffff',
              fill: '#ffffff',
              visible: true
            });
          } else {
            obj.set({ visible: false });
          }
        });

        canvas.renderAll();

        // Export safely using toDataURL and convert to Blob
        let blob: Blob | null = null;
        try {
          const dataUrl = canvas.toDataURL({
            format: 'png',
            multiplier: scaleFactorRef.current || 1.0,
          });
          if (dataUrl && dataUrl.startsWith('data:')) {
            const res = await fetch(dataUrl);
            blob = await res.blob();
          }
        } catch (exportErr) {
          console.warn('Canvas toDataURL export warning:', exportErr);
        }

        // Restore
        canvas.backgroundColor = oldBgColor;

        objects.forEach((obj: any) => {
          const state = originalStates.get(obj);
          if (state) {
            obj.set({
              visible: state.visible,
              stroke: state.stroke,
              fill: state.fill
            });
          }
        });

        if (activeObj) {
          canvas.setActiveObject(activeObj);
        }

        // Restore zoom and dimensions
        canvas.setZoom(oldZoom);
        canvas.setDimensions({ width: oldWidth, height: oldHeight });
        canvas.renderAll();
        
        return blob;
      }
    });

    return () => {
      useProjectStore.setState({ getCanvasMaskBlob: null });
    };
  }, []);

  // Initialize Fabric Canvas AND load preview dimensions natively
  useEffect(() => {
    if (!canvasElRef.current || !activePage) return;

    setStatus(`Initializing page ${activePage.page_number}...`, false);
    setIsImageLoaded(false);
    setScaleFactor(1.0);
    scaleFactorRef.current = 1.0;
    blockRenderSignaturesRef.current.clear();
    blockRenderContextRef.current = '';

    // Reset scroll positions ONLY when navigating to a new page
    const isNewPage = lastPageIdRef.current !== activePage.id;
    lastPageIdRef.current = activePage.id;

    if (workspaceRef.current) {
      if (isNewPage) {
        lastScrollPosRef.current = { scrollTop: 0, scrollLeft: 0 };
        workspaceRef.current.scrollTop = 0;
        workspaceRef.current.scrollLeft = 0;
      } else {
        workspaceRef.current.scrollTop = lastScrollPosRef.current.scrollTop;
        workspaceRef.current.scrollLeft = lastScrollPosRef.current.scrollLeft;
      }
    }

    const performanceProfile = String(activeProject?.settings?.performance_profile || 'balanced');
    const retinaScale = resolveCanvasZoomRetinaScale(
      performanceProfile,
      window.devicePixelRatio,
      zoomLevelRef.current,
    );
    canvasRetinaScaleRef.current = retinaScale;
    const canvas = new fabric.Canvas(canvasElRef.current, {
      width: 800,
      height: 600,
      backgroundColor: 'transparent',
      fireRightClick: true,
      stopContextMenu: true,
      selectionColor: 'rgba(249, 115, 22, 0.15)',
      selectionBorderColor: '#f97316',
      selectionLineWidth: 1.5,
      enableRetinaScaling: retinaScale > 1,
      renderOnAddRemove: false,
      uniformScaling: false,
      uniScaleKey: 'shiftKey',
    });

    // Fabric normally uses the full OS DPR. Bound it per performance profile:
    // text stays crisp, while backing allocation remains predictable.
    (canvas as fabric.Canvas & { getRetinaScaling: () => number }).getRetinaScaling = () => canvasRetinaScaleRef.current;

    fabricCanvasRef.current = canvas;

    // Draw Box Outlines and Index Number Badges (Houzi Style)
    canvas.on('after:render', (opt) => {
      if (isExportCaptureRef.current) return;
      // Draw outlines ONLY if typesetting mode is on
      const shouldDraw = showTypesettingRef.current;
      if (!shouldDraw) return;
      
      const ctx = opt.ctx;
      if (!ctx) return;
      const visualZoom = Math.max(0.05, zoomLevelRef.current);
      const activeObjects = canvas.getActiveObjects();
      const selectedBlockIds = new Set(useProjectStore.getState().selectedBlocks.map(block => block.id));
      
      // Save canvas context and apply viewport transform (zoom and pan)
      ctx.save();
      const vpt = canvas.viewportTransform;
      if (vpt) {
        ctx.transform(vpt[0], vpt[1], vpt[2], vpt[3], vpt[4], vpt[5]);
      }
      
      // During a transform, decorate only the object(s) being manipulated.
      // Scanning every textbox in `after:render` made drag cost grow linearly
      // with page size even though only one box could have changed.
      const interactionTarget = activeInteractionObjectRef.current as any;
      const overlayObjects: any[] = interactionActiveRef.current && interactionTarget
        ? (interactionTarget.type === 'activeSelection' && typeof interactionTarget.getObjects === 'function'
            ? interactionTarget.getObjects()
            : [interactionTarget])
        : canvas.getObjects();

      const renderedBlockIds = new Set<string>();
      overlayObjects.forEach((obj: any) => {
        if (obj.type !== 'textbox' || !obj.data?.blockId) return;
        if (!obj.visible) return;
        const blockId = String(obj.data.blockId);
        if (renderedBlockIds.has(blockId)) return;
        renderedBlockIds.add(blockId);
        
        ctx.save();
        const matrix = obj.calcTransformMatrix();
        const isSelected = activeObjects.includes(obj) || selectedBlockIds.has(obj.data.blockId);
        const isHovered = (obj as any)._isHovered;
        const confidence = obj.data?.confidence ?? 1.0;

        const activeBlock = useProjectStore.getState().activePage?.text_blocks?.find((b: any) => b.id === blockId);
        const activeProj = useProjectStore.getState().activeProject;
        const isSmartBalloonEnabled = getEffectiveEnableSmartBalloon(activeProj?.settings);
        const sbMeta = activeBlock?.extra_metadata?.smart_balloon;
        const contourPts = sbMeta?.contour_points || sbMeta?.raw_contour_points;
        const archetype = sbMeta?.archetype || 'UNKNOWN';

        if (isSmartBalloonEnabled && activeBlock && (activeBlock.smart_x != null || (Array.isArray(contourPts) && contourPts.length > 2))) {
          const sf = scaleFactorRef.current || 1;
          const smX = (activeBlock.smart_x ?? activeBlock.x) / sf;
          const smY = (activeBlock.smart_y ?? activeBlock.y) / sf;
          const smW = (activeBlock.smart_width ?? activeBlock.width) / sf;
          const smH = (activeBlock.smart_height ?? activeBlock.height) / sf;

          ctx.save();

          // Distinctive Archetype Palettes
          let baseRgb = '236, 72, 153'; // default pink
          let badgeBg = 'rgba(219, 39, 119, 0.95)';
          let archetypeIcon = '🎈 Smart Balloon';

          if (archetype === 'ANGULAR') {
            baseRgb = '16, 185, 129'; // emerald green
            badgeBg = 'rgba(5, 150, 105, 0.95)';
            archetypeIcon = '⚡ Angular Shape';
          } else if (archetype === 'SPIKY_FUZZY') {
            baseRgb = '168, 85, 247'; // purple
            badgeBg = 'rgba(147, 51, 234, 0.95)';
            archetypeIcon = '💥 Spiky Shape';
          } else if (archetype === 'RECTANGULAR') {
            baseRgb = '14, 165, 233'; // sky blue
            badgeBg = 'rgba(2, 132, 199, 0.95)';
            archetypeIcon = '🔲 Caption Box';
          } else if (archetype === 'SMOOTH_OVAL') {
            baseRgb = '245, 158, 11'; // amber orange
            badgeBg = 'rgba(217, 119, 6, 0.95)';
            archetypeIcon = '💬 Smooth Oval';
          }

          const strokeColor = isSelected
            ? `rgba(${baseRgb}, 0.98)`
            : isHovered
              ? `rgba(${baseRgb}, 0.90)`
              : `rgba(${baseRgb}, 0.70)`;

          const fillColor = isSelected
            ? `rgba(${baseRgb}, 0.16)`
            : isHovered
              ? `rgba(${baseRgb}, 0.08)`
              : `rgba(${baseRgb}, 0.03)`;

          const strokeWidth = (isSelected ? 2.4 : (isHovered ? 1.8 : 1.2)) / visualZoom;
          const dashPattern = isSelected
            ? [6 / visualZoom, 4 / visualZoom]
            : isHovered
              ? [5 / visualZoom, 3 / visualZoom]
              : [4 / visualZoom, 4 / visualZoom];

          ctx.beginPath();
          if (Array.isArray(contourPts) && contourPts.length > 2) {
            // Draw exact polygon shape matching the manga balloon contour
            ctx.moveTo(contourPts[0][0] / sf, contourPts[0][1] / sf);
            for (let pi = 1; pi < contourPts.length; pi++) {
              ctx.lineTo(contourPts[pi][0] / sf, contourPts[pi][1] / sf);
            }
            ctx.closePath();
          } else {
            ctx.rect(smX, smY, smW, smH);
          }

          ctx.fillStyle = fillColor;
          ctx.fill();
          ctx.strokeStyle = strokeColor;
          ctx.lineWidth = strokeWidth;
          ctx.setLineDash(dashPattern);
          ctx.stroke();

          // Draw Smart Balloon Badge Label when Selected or Hovered
          if (isSelected || isHovered) {
            const badgeText = `${archetypeIcon} (${Math.round(smW * sf)}×${Math.round(smH * sf)})`;
            const fontPx = Math.max(9, Math.min(12, 11 / visualZoom));
            ctx.font = `bold ${fontPx}px monospace`;
            const textWidth = ctx.measureText(badgeText).width;
            const badgeH = fontPx + 6 / visualZoom;
            const badgeY = Math.max(0, smY - badgeH);
            ctx.fillStyle = badgeBg;
            ctx.fillRect(smX, badgeY, textWidth + 10 / visualZoom, badgeH);
            ctx.fillStyle = '#ffffff';
            ctx.fillText(badgeText, smX + 5 / visualZoom, badgeY + fontPx - 2 / visualZoom);
          }

          ctx.restore();
        }

        ctx.transform(matrix[0], matrix[1], matrix[2], matrix[3], matrix[4], matrix[5]);
        
        const w = obj.width;
        const h = obj.height;
        // Fabric transform origin is at the CENTER of the object,
        // so top-left in local coords is (-w/2, -h/2)
        const tlX = -w / 2;
        const tlY = -h / 2;
        
        // Draw live mask overlay if active
        if (liveMaskOverlayRef.current) {
          const activeProj = useProjectStore.getState().activeProject;
          const dilationKernel = activeProj?.settings?.mask_dilation_kernel ?? 3;
          const dilationCanvas = dilationKernel / scaleFactorRef.current;
          
          ctx.save();
          const dX = tlX - dilationCanvas;
          const dY = tlY - dilationCanvas;
          const dW = w + 2 * dilationCanvas;
          const dH = h + 2 * dilationCanvas;
          
          ctx.beginPath();
          ctx.rect(dX, dY, dW, dH);
          ctx.fillStyle = 'rgba(239, 68, 68, 0.25)'; // Red semi-transparent
          ctx.fill();
          ctx.strokeStyle = 'rgba(239, 68, 68, 0.5)';
          ctx.lineWidth = 1 / visualZoom;
          ctx.setLineDash([4 / visualZoom, 4 / visualZoom]);
          ctx.stroke();
          ctx.restore();
        }
        
        const hasSmartBalloon = isSmartBalloonEnabled && Boolean(
          activeBlock && (activeBlock.smart_x != null || (Array.isArray(contourPts) && contourPts.length > 2))
        );

        let boxStroke = isSelected ? '#f59e0b' : '#eab308';
        let boxFill = isSelected ? 'rgba(245, 158, 11, 0.06)' : 'rgba(234, 179, 8, 0.035)';

        // Suppress yellow rectangle when Smart Balloon contour is active (Smart Balloon is the 100% true balloon)
        if (!hasSmartBalloon) {
          
          if (!isSelected) {
            if (isHovered) {
              boxStroke = '#fbbf24';
              boxFill = 'rgba(251, 191, 36, 0.04)';
            } else if (obj.data?.decisionStroke) {
              // B+ decision status colors (typeset mode with Spec)
              boxStroke = obj.data.decisionStroke as string;
              const ds = String(obj.data.decisionStatus || '');
              boxFill =
                ds === 'NEEDS_REVIEW' ? 'rgba(251, 191, 36, 0.10)'
                  : ds === 'DEFAULTED' ? 'rgba(56, 189, 248, 0.08)'
                    : ds === 'AUTO_APPLIED' ? 'rgba(52, 211, 153, 0.07)'
                      : 'rgba(113, 113, 122, 0.06)';
            } else if (confidence >= 0.8) {
              boxStroke = '#22c55e'; // Green
              boxFill = 'rgba(34, 197, 94, 0.06)';
            } else if (confidence >= 0.45) {
              boxStroke = '#eab308'; // Yellow
              boxFill = 'rgba(234, 179, 8, 0.06)';
            } else {
              boxStroke = '#ef4444'; // Red
              boxFill = 'rgba(239, 68, 68, 0.08)';
            }
          }
          
          const boxLineWidth = (isSelected ? 1.5 : (isHovered ? 1.25 : 0.75)) / visualZoom;
          
          // Draw rounded rectangle at correct top-left
          ctx.beginPath();
          if (typeof ctx.roundRect === 'function') {
            ctx.roundRect(tlX, tlY, w, h, 3 / visualZoom);
          } else {
            ctx.rect(tlX, tlY, w, h);
          }
          ctx.fillStyle = boxFill;
          ctx.fill();
          ctx.strokeStyle = boxStroke;
          ctx.lineWidth = boxLineWidth;
          ctx.stroke();
        }

        // Draw circular index badge at top-left corner of the box
        const blockIndex = obj.data?.blockIndex;
        if (blockIndex !== undefined && blockIndex !== null && blockIndex !== '') {
          const badgeRadius = (isSelected || isHovered ? 8 : 7) / visualZoom;
          const badgeX = tlX;
          const badgeY = tlY;

          let badgeColor = boxStroke;
          if (hasSmartBalloon) {
            if (archetype === 'ANGULAR') badgeColor = '#059669';
            else if (archetype === 'SPIKY_FUZZY') badgeColor = '#9333ea';
            else if (archetype === 'RECTANGULAR') badgeColor = '#0284c7';
            else if (archetype === 'SMOOTH_OVAL') badgeColor = '#d97706';
            else badgeColor = '#db2777';
          }

          ctx.beginPath();
          ctx.arc(badgeX, badgeY, badgeRadius, 0, 2 * Math.PI);
          ctx.fillStyle = badgeColor;
          ctx.fill();
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = 1 / visualZoom;
          ctx.stroke();

          ctx.fillStyle = '#ffffff';
          const fontSize = 9 / visualZoom;
          ctx.font = `600 ${fontSize}px sans-serif`;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(`${blockIndex}`, badgeX, badgeY);
        }

        // Draw mask type indicator badge at bottom-right corner
        const maskType = obj.data?.maskType;
        if (maskType && maskType !== 'box') {
          const maskBadgeSize = 12 / visualZoom;
          const brX = tlX + w;
          const brY = tlY + h;
          const maskBadgeX = brX - maskBadgeSize / 2;
          const maskBadgeY = brY - maskBadgeSize / 2;

          // Background circle
          ctx.beginPath();
          ctx.arc(maskBadgeX, maskBadgeY, maskBadgeSize / 2, 0, 2 * Math.PI);
          ctx.fillStyle = maskType === 'custom' ? '#10b981' : '#f59e0b';
          ctx.fill();
          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = 1 / visualZoom;
          ctx.stroke();

          ctx.fillStyle = '#ffffff';
          const iconFontSize = 7 / visualZoom;
          ctx.font = `600 ${iconFontSize}px sans-serif`;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          const icon = maskType === 'custom' ? 'M' : 'A';
          ctx.fillText(icon, maskBadgeX, maskBadgeY);
        }

        ctx.restore();
      });
      
      // Draw alignment guides (Figma Snapping Guides)
      if (alignmentGuidesRef.current && alignmentGuidesRef.current.length > 0) {
        ctx.save();
        ctx.strokeStyle = '#eab308'; // Glowing gold/amber line
        ctx.lineWidth = 1 / visualZoom;
        ctx.setLineDash([6 / visualZoom, 4 / visualZoom]);
        
        const pageW = imgDimensionsRef.current.width;
        const pageH = imgDimensionsRef.current.height;

        alignmentGuidesRef.current.forEach((g) => {
          ctx.beginPath();
          if (g.type === 'v') {
            ctx.moveTo(g.val, 0);
            ctx.lineTo(g.val, pageH);
          } else {
            ctx.moveTo(0, g.val);
            ctx.lineTo(pageW, g.val);
          }
          ctx.stroke();
        });
        ctx.restore();
      }

      // Restore canvas context after drawing all objects
      ctx.restore();
    });

    // Mouse hover highlights on OCR text boxes
    canvas.on('mouse:over', (e) => {
      const target = e.target;
      if (target && target.type === 'textbox' && (target as any).data?.blockId) {
        (target as any)._isHovered = true;
        canvas.requestRenderAll();
      }
    });
    canvas.on('mouse:out', (e) => {
      const target = e.target;
      if (target && target.type === 'textbox') {
        (target as any)._isHovered = false;
        canvas.requestRenderAll();
      }
      // Clear tooltip when mouse leaves any block
      setMaskTooltip(null);
    });

    // Mask badge hover detection
    canvas.on('mouse:move', (e) => {
      const pointer = canvas.getScenePoint(e.e);
      const objects = canvas.getObjects();

      let foundBadge = false;
      for (const obj of objects) {
        if (obj.type !== 'textbox' || !(obj as any).data?.blockId) continue;

        const maskType = (obj as any).data?.maskType;
        if (!maskType || maskType === 'box') continue;

        // Get object bounds in canvas coordinates
        const matrix = (obj as any).calcTransformMatrix();
        const w = (obj as any).width;
        const h = (obj as any).height;

        // Transform local coords to canvas coords
        const brLocal = { x: w / 2, y: h / 2 }; // Bottom-right in local coords
        const brCanvas = fabric.util.transformPoint(brLocal, matrix);

        const visualZoom = Math.max(0.05, zoomLevelRef.current);
        const maskBadgeSize = 12 / visualZoom;
        const badgeRadius = maskBadgeSize / 2;

        // Check if pointer is within badge circle
        const dx = pointer.x - brCanvas.x;
        const dy = pointer.y - brCanvas.y;
        const distance = Math.sqrt(dx * dx + dy * dy);

        if (distance <= badgeRadius) {
          // Convert canvas coords to viewport coords for tooltip positioning
          const vpt = canvas.viewportTransform!;
          const screenX = (brCanvas.x * vpt[0] + vpt[4]) * visualZoom;
          const screenY = (brCanvas.y * vpt[3] + vpt[5]) * visualZoom;

          setMaskTooltip({
            x: screenX,
            y: screenY,
            type: maskType,
            blockId: (obj as any).data.blockId
          });
          foundBadge = true;
          break;
        }
      }

      if (!foundBadge) {
        setMaskTooltip(null);
      }
    });

    // Bounding Box Drag-to-Draw Logic (Matches Houzilocal custom cell creation)
    let isDrawingRect = false;
    let isRightClickDrawing = false;
    let rightClickTarget: any = null;
    let rightClickCoords = { x: 0, y: 0 };
    let rectStart = { x: 0, y: 0 };
    let dragRect: fabric.Rect | null = null;

    canvas.on('mouse:down', (opt) => {
      // Handle custom right click context menu on text blocks
      const isRightClick = (opt as any).button === 3 || (opt.e as any).button === 2;
      
      if (isRightClick) {
        rightClickTarget = opt.target;
        rightClickCoords = {
          x: (opt.e as any).clientX,
          y: (opt.e as any).clientY
        };
        isRightClickDrawing = true;
      } else {
        rightClickTarget = null;
        isRightClickDrawing = false;
        setContextMenu(null);
      }

      // If panning or space is pressed, do not draw box
      const isMiddleClick = (opt.e as any).button === 1;
      const isSpacePan = (opt.e as any).button === 0 && isSpacePressedRef.current;
      if (isMiddleClick || isSpacePan || (opt.e as any).altKey) {
        if (isMiddleClick || isSpacePan) {
          isPanningRef.current = true;
          panStartRef.current = {
            x: (opt.e as any).clientX,
            y: (opt.e as any).clientY,
            scrollLeft: workspaceRef.current?.scrollLeft || 0,
            scrollTop: workspaceRef.current?.scrollTop || 0,
          };
          if (workspaceRef.current) {
            workspaceRef.current.style.cursor = 'grabbing';
          }
        }
        return;
      }

      const mode = canvasModeRef.current;
      if (mode === 'text') {
        const textbox = opt.target as any;
        if (textbox?.type === 'textbox' && textbox.data?.blockId) {
          const currentPage = useProjectStore.getState().activePage;
          const block = currentPage?.text_blocks.find(item => item.id === textbox.data.blockId);
          if (block) useProjectStore.setState({ selectedBlock: block, selectedBlocks: [block] });
          textbox.set({ editable: true });
          canvas.setActiveObject(textbox);
          textbox.enterEditing();
          if (typeof textbox.getSelectionStartFromPointer === 'function') {
            const cursor = textbox.getSelectionStartFromPointer(opt.e);
            textbox.setSelectionStart(cursor);
            textbox.setSelectionEnd(cursor);
          }
          textbox.focus();
          canvas.requestRenderAll();
        }
        return;
      }
      if (mode !== 'select' && mode !== 'drawBlock') return;
      if (mode === 'select' && !isRightClick) return;

      isDrawingRect = true;
      interactionActiveRef.current = true;
      activeInteractionObjectRef.current = null;
      canvas.selection = false; // Disable default selection box when drawing
      
      const pointer = canvas.getScenePoint(opt.e);
      
      // Clamp start coordinates to image boundaries
      const imgW = imgDimensionsRef.current.width;
      const imgH = imgDimensionsRef.current.height;
      const startX = Math.max(0, Math.min(imgW, pointer.x));
      const startY = Math.max(0, Math.min(imgH, pointer.y));
      rectStart = { x: startX, y: startY };

      // Discard active Fabric selection and store selectedBlock on start
      canvas.discardActiveObject();
      useProjectStore.setState({ selectedBlock: null, selectedBlocks: [] });

      dragRect = new fabric.Rect({
        left: startX,
        top: startY,
        width: 0,
        height: 0,
        fill: 'rgba(17, 117, 230, 0.1)',
        stroke: 'rgb(17, 117, 230)',
        strokeWidth: 1,
        selectable: false,
        evented: false,
        originX: 'left',
        originY: 'top',
      });

      canvas.add(dragRect);
    });

    canvas.on('mouse:move', (opt) => {
      if (!isDrawingRect || !dragRect) return;

      canvas.setCursor('cell');

      const pointer = canvas.getScenePoint(opt.e);
      
      // Clamp coordinates to image boundaries during move
      const imgW = imgDimensionsRef.current.width;
      const imgH = imgDimensionsRef.current.height;
      const clampX = Math.max(0, Math.min(imgW, pointer.x));
      const clampY = Math.max(0, Math.min(imgH, pointer.y));

      const left = Math.min(rectStart.x, clampX);
      const top = Math.min(rectStart.y, clampY);
      const width = Math.abs(rectStart.x - clampX);
      const height = Math.abs(rectStart.y - clampY);

      dragRect.set({ left, top, width, height });
      canvas.requestRenderAll();
    });

    canvas.on('mouse:up', async () => {
      alignmentGuidesRef.current = [];
      interactionActiveRef.current = false;
      activeInteractionObjectRef.current = null;
      
      // Restore canvas selection state
      const mode = canvasModeRef.current;
      const isInteractive = (mode === 'select' || mode === 'text') && (showTypesettingRef.current || !showTranslatedRef.current) && !isMaskModeRef.current;
      canvas.selection = isInteractive;

      let dragged = false;
      let left = 0, top = 0, width = 0, height = 0;

      if (isDrawingRect && dragRect) {
        isDrawingRect = false;
        left = dragRect.left || 0;
        top = dragRect.top || 0;
        width = dragRect.width || 0;
        height = dragRect.height || 0;

        canvas.remove(dragRect);
        dragRect = null;
        canvas.requestRenderAll();
        
        if (width > 5 && height > 5) {
          dragged = true;
        }
      }

      if (isRightClickDrawing) {
        isRightClickDrawing = false;
        if (!dragged) {
          // If right click was released without dragging, open context menu
          if (rightClickTarget && (rightClickTarget as any).data?.blockId) {
            const blockId = (rightClickTarget as any).data.blockId;
            canvas.setActiveObject(rightClickTarget);
            canvas.requestRenderAll();
            
            const currentPage = useProjectStore.getState().activePage;
            const block = currentPage?.text_blocks.find(b => b.id === blockId);
            if (block) {
              useProjectStore.setState({ selectedBlock: block, selectedBlocks: [block] });
            }
            
            setContextMenu({
              x: rightClickCoords.x,
              y: rightClickCoords.y,
              blockId: blockId
            });
          } else {
            setContextMenu({ x: rightClickCoords.x, y: rightClickCoords.y });
          }
          return;
        }
      }

      if (dragged) {
        const sf = scaleFactorRef.current;
        const pageId = activePage.id;
        
        await createBlock(pageId, {
          x: left * sf,
          y: top * sf,
          width: width * sf,
          height: height * sf,
          translation: 'พิมพ์คำแปลใหม่'
        });
      }
    });

    // Selection Events
    const updateSelection = (selectedObjects: any[], newlySelected: any[] = [], shiftKey = false) => {
      const selectedBlockIds = selectedObjects
        .filter(obj => obj && obj.data?.blockId)
        .map(obj => obj.data.blockId);
      
      // Read fresh state from store to avoid stale closure over activePage
      const currentPage = useProjectStore.getState().activePage;
      const ordered = [...(currentPage?.text_blocks || [])].sort((a, b) => a.block_index - b.block_index);
      if (shiftKey) {
        const targetId = newlySelected.map((object) => object?.data?.blockId).filter(Boolean).at(-1)
          || selectedBlockIds.at(-1);
        const anchorId = selectionAnchorBlockIdRef.current || useProjectStore.getState().selectedBlock?.id;
        const anchorIndex = ordered.findIndex((block) => block.id === anchorId);
        const targetIndex = ordered.findIndex((block) => block.id === targetId);
        if (anchorIndex >= 0 && targetIndex >= 0) {
          const range = ordered.slice(Math.min(anchorIndex, targetIndex), Math.max(anchorIndex, targetIndex) + 1);
          useProjectStore.setState({ selectedBlock: ordered[targetIndex], selectedBlocks: range });
          return;
        }
      }
      const blocks = ordered.filter(b => selectedBlockIds.includes(b.id));
      const primaryBlock = blocks[0] || null;
      selectionAnchorBlockIdRef.current = primaryBlock?.id || null;
      
      useProjectStore.setState({
        selectedBlock: primaryBlock,
        selectedBlocks: blocks
      });
    };

    canvas.on('selection:created', (e) => {
      if (isProgrammaticSelectionChangeRef.current) return;
      updateSelection(canvas.getActiveObjects(), e.selected || [], Boolean((e.e as MouseEvent | undefined)?.shiftKey));
    });

    canvas.on('selection:updated', (e) => {
      if (isProgrammaticSelectionChangeRef.current) return;
      updateSelection(canvas.getActiveObjects(), e.selected || [], Boolean((e.e as MouseEvent | undefined)?.shiftKey));
    });

    canvas.on('before:selection:cleared', () => {
      if (isProgrammaticSelectionChangeRef.current) return;
      const activeObj = canvas.getActiveObject();
      if (activeObj && (activeObj as any).isEditing) {
        (activeObj as any).exitEditing();
      }
    });

    canvas.on('selection:cleared', () => {
      if (isProgrammaticSelectionChangeRef.current) return;
      useProjectStore.setState({ selectedBlock: null, selectedBlocks: [] });
    });

    type SnapCandidate = {
      left: number;
      top: number;
      right: number;
      bottom: number;
      centerX: number;
      centerY: number;
    };
    let snapCandidateTarget: fabric.FabricObject | null = null;
    let snapCandidates: SnapCandidate[] = [];
    let pendingSnapTarget: fabric.FabricObject | null = null;
    let snapAnimationFrame: number | null = null;

    const prepareSnapCandidates = (target: fabric.FabricObject) => {
      if (snapCandidateTarget === target) return;
      snapCandidateTarget = target;
      snapCandidates = canvas.getObjects()
        .filter(o => o !== target && o.type === 'textbox' && o.visible)
        .map(o => {
          const left = o.left || 0;
          const top = o.top || 0;
          const width = (o.width || 0) * (o.scaleX || 1);
          const height = (o.height || 0) * (o.scaleY || 1);
          return {
            left,
            top,
            right: left + width,
            bottom: top + height,
            centerX: left + width / 2,
            centerY: top + height / 2,
          };
        });
    };

    const markTransformActive = (e: { target?: fabric.FabricObject }) => {
      if (!e.target) return;
      interactionActiveRef.current = true;
      activeInteractionObjectRef.current = e.target;
    };

    canvas.on('object:scaling', markTransformActive);
    canvas.on('object:resizing', markTransformActive);
    canvas.on('object:rotating', markTransformActive);

    // Object Snapping and Guides during Move. Pointer devices can emit hundreds
    // of events per second, while the display can present only one result per
    // animation frame. Coalescing here keeps movement responsive and makes snap
    // work deterministic at the screen refresh rate.
    const applyMoveSnapping = (target: fabric.FabricObject) => {
      const SNAP_THRESHOLD = 6; // pixels in canvas coordinates
      prepareSnapCandidates(target);

      let snapX: number | null = null;
      let snapY: number | null = null;
      const guides: { type: 'v' | 'h'; val: number }[] = [];

      const tLeft = target.left || 0;
      const tTop = target.top || 0;
      const tWidth = (target.width || 0) * (target.scaleX || 1);
      const tHeight = (target.height || 0) * (target.scaleY || 1);
      const tCenterX = tLeft + tWidth / 2;
      const tCenterY = tTop + tHeight / 2;
      const tRight = tLeft + tWidth;
      const tBottom = tTop + tHeight;

      // 1. Page Center Snapping
      const pageW = imgDimensionsRef.current.width;
      const pageH = imgDimensionsRef.current.height;
      const pageCenterX = pageW / 2;
      const pageCenterY = pageH / 2;

      // Check page vertical midline snap
      if (Math.abs(tCenterX - pageCenterX) < SNAP_THRESHOLD) {
        snapX = pageCenterX - tWidth / 2;
        guides.push({ type: 'v', val: pageCenterX });
      }
      // Check page horizontal midline snap
      if (Math.abs(tCenterY - pageCenterY) < SNAP_THRESHOLD) {
        snapY = pageCenterY - tHeight / 2;
        guides.push({ type: 'h', val: pageCenterY });
      }

      // 2. Element Snapping. Geometry is cached once per drag instead of
      // rebuilding/filtering every Fabric pointer event.
      for (const o of snapCandidates) {

        // X Snapping (Left, Center, Right)
        if (snapX === null) {
          if (Math.abs(tLeft - o.left) < SNAP_THRESHOLD) {
            snapX = o.left;
            guides.push({ type: 'v', val: o.left });
          } else if (Math.abs(tLeft - o.right) < SNAP_THRESHOLD) {
            snapX = o.right;
            guides.push({ type: 'v', val: o.right });
          } else if (Math.abs(tRight - o.left) < SNAP_THRESHOLD) {
            snapX = o.left - tWidth;
            guides.push({ type: 'v', val: o.left });
          } else if (Math.abs(tRight - o.right) < SNAP_THRESHOLD) {
            snapX = o.right - tWidth;
            guides.push({ type: 'v', val: o.right });
          } else if (Math.abs(tCenterX - o.centerX) < SNAP_THRESHOLD) {
            snapX = o.centerX - tWidth / 2;
            guides.push({ type: 'v', val: o.centerX });
          }
        }

        // Y Snapping (Top, Center, Bottom)
        if (snapY === null) {
          if (Math.abs(tTop - o.top) < SNAP_THRESHOLD) {
            snapY = o.top;
            guides.push({ type: 'h', val: o.top });
          } else if (Math.abs(tTop - o.bottom) < SNAP_THRESHOLD) {
            snapY = o.bottom;
            guides.push({ type: 'h', val: o.bottom });
          } else if (Math.abs(tBottom - o.top) < SNAP_THRESHOLD) {
            snapY = o.top - tHeight;
            guides.push({ type: 'h', val: o.top });
          } else if (Math.abs(tBottom - o.bottom) < SNAP_THRESHOLD) {
            snapY = o.bottom - tHeight;
            guides.push({ type: 'h', val: o.bottom });
          } else if (Math.abs(tCenterY - o.centerY) < SNAP_THRESHOLD) {
            snapY = o.centerY - tHeight / 2;
            guides.push({ type: 'h', val: o.centerY });
          }
        }

        if (snapX !== null && snapY !== null) break;
      }

      // Store guides ref for visual alignment indicator without hijacking free motion
      alignmentGuidesRef.current = guides;
      canvas.requestRenderAll();
    };

    canvas.on('object:moving', (e) => {
      const target = e.target;
      if (!target) return;
      if (canvasModeRef.current === 'text') return;
      interactionActiveRef.current = true;
      activeInteractionObjectRef.current = target;
      pendingSnapTarget = target;
      if (snapAnimationFrame !== null) return;
      snapAnimationFrame = requestAnimationFrame(() => {
        snapAnimationFrame = null;
        const latestTarget = pendingSnapTarget;
        pendingSnapTarget = null;
        if (latestTarget) applyMoveSnapping(latestTarget);
      });
    });

    // Object Modification Handler
    canvas.on('object:modified', async (e) => {
      alignmentGuidesRef.current = [];
      interactionActiveRef.current = false;
      activeInteractionObjectRef.current = null;
      snapCandidateTarget = null;
      snapCandidates = [];
      pendingSnapTarget = null;
      if (snapAnimationFrame !== null) {
        cancelAnimationFrame(snapAnimationFrame);
        snapAnimationFrame = null;
      }
      canvas.requestRenderAll();

      const obj = e.target as any;
      if (!obj || !obj.data?.blockId) return;
      // Text mode owns caret/text editing only. Geometry changes are accepted
      // exclusively in Select & Draw mode so a drag near glyphs cannot move a layer.
      if (canvasModeRef.current === 'text') return;

      const blockId = obj.data.blockId;
      const sf = scaleFactorRef.current;
      const activePage = useProjectStore.getState().activePage;
      let block = activePage?.text_blocks?.find(b => b.id === blockId);
      
      const canvasLeft = obj.left || 0;
      const canvasTop = obj.top || 0;
      const canvasWidth = (obj.width || 0) * (obj.scaleX || 1);
      const canvasHeight = (obj.height || 0) * (obj.scaleY || 1);
      const rotation = obj.angle || 0;
      const layoutPadding = normalizeTextPadding(obj.data?.layoutPadding);
      const outerRegion = resolveOuterLayoutRegion(
        {
          x: canvasLeft * sf,
          y: canvasTop * sf,
          width: canvasWidth * sf,
          height: canvasHeight * sf,
        },
        layoutPadding,
        rotation,
      );

      // Resizing a Balloon changes its layout region, not the type size. The
      // previous scale-to-font conversion made a corner drag unexpectedly grow
      // the text and made the box increasingly difficult to correct.
      const sizeChanged = (obj.scaleX && obj.scaleX !== 1) || (obj.scaleY && obj.scaleY !== 1) || Math.abs((obj.width || 0) - canvasWidth) > 0.001 || Math.abs((obj.height || 0) - canvasHeight) > 0.001;
      if (sizeChanged) {
        obj.set({
          width: canvasWidth,
          height: canvasHeight,
          scaleX: 1,
          scaleY: 1
        });
        obj.calcTextHeight = function() {
          return canvasHeight;
        };
        obj.initDimensions();
        obj.setCoords();
        if (isAutoFontSizeEnabled(block)) {
          // Geometry is persisted below; keep this fit local so it cannot issue
          // a second request for the same resize operation.
          autoFitTextboxFontSize(obj, canvas, scaleFactorRef.current, true);
          canvas.requestRenderAll();
        }
      }

      const isSmartBalloonEnabled = getEffectiveEnableSmartBalloon(
        useProjectStore.getState().activeProject?.settings
      );
      const hasSmartBalloon = isSmartBalloonEnabled && Boolean(
        block?.smart_x != null || block?.extra_metadata?.smart_balloon
      );

      const dx = outerRegion.x - (block?.x ?? outerRegion.x);
      const dy = outerRegion.y - (block?.y ?? outerRegion.y);

      let updatedSb = block?.extra_metadata?.smart_balloon ? { ...block.extra_metadata.smart_balloon } : undefined;
      if (updatedSb) {
        if (updatedSb.safe_bbox) {
          updatedSb.safe_bbox = {
            ...updatedSb.safe_bbox,
            x: outerRegion.x,
            y: outerRegion.y,
            width: outerRegion.width,
            height: outerRegion.height,
          };
        }
        if (updatedSb.raw_bbox) {
          updatedSb.raw_bbox = {
            ...updatedSb.raw_bbox,
            x: (updatedSb.raw_bbox.x ?? 0) + dx,
            y: (updatedSb.raw_bbox.y ?? 0) + dy,
          };
        }
        if (Array.isArray(updatedSb.contour_points)) {
          updatedSb.contour_points = updatedSb.contour_points.map(([px, py]: [number, number]) => [px + dx, py + dy]);
        }
        if (Array.isArray(updatedSb.raw_contour_points)) {
          updatedSb.raw_contour_points = updatedSb.raw_contour_points.map(([px, py]: [number, number]) => [px + dx, py + dy]);
        }
      }

      // Calculate dynamic font size matching the newly scaled/resized box
      const finalFontSize = (isAutoFontSizeEnabled(block) && obj.fontSize)
        ? Math.max(12, Math.round(obj.fontSize * scaleFactorRef.current))
        : (block?.font_size ?? 18);

      const { typesetting_spec: _staleSpec, ...cleanMetadata } = block?.extra_metadata || {};

      const updatePayload: Partial<TextBlock> = {
        x: outerRegion.x,
        y: outerRegion.y,
        width: outerRegion.width,
        height: outerRegion.height,
        font_size: finalFontSize,
        ...(hasSmartBalloon ? {
          smart_x: outerRegion.x,
          smart_y: outerRegion.y,
          smart_width: outerRegion.width,
          smart_height: outerRegion.height,
        } : {}),
        rotation_deg: rotation,
        extra_metadata: {
          ...cleanMetadata,
          ...(updatedSb ? { smart_balloon: updatedSb } : {}),
          text_bbox: {
            x: outerRegion.x,
            y: outerRegion.y,
            width: outerRegion.width,
            height: outerRegion.height,
          },
          layout_region: {
            ...(block?.extra_metadata?.layout_region || {}),
            x: outerRegion.x,
            y: outerRegion.y,
            width: outerRegion.width,
            height: outerRegion.height,
            confidence: 1,
            source: 'manual',
            reason: 'user_adjusted',
          },
        },
      };

      await updateBlock(blockId, updatePayload);
    });

    // Handle Text Modification (updates UI locally in real-time without database calls to prevent typing lag)
    canvas.on('text:changed', (e) => {
      const obj = e.target as any;
      if (obj && obj.type === 'textbox' && obj.data?.blockId) {
        interactionActiveRef.current = true;
        activeInteractionObjectRef.current = obj;
        const page = useProjectStore.getState().activePage;
        const block = page?.text_blocks?.find(b => b.id === obj.data.blockId);
        if (isAutoFontSizeEnabled(block)) {
          scheduleAutoFitTextboxFontSize(obj, canvas, scaleFactorRef.current);
        }
      }
    });

    // Handle editing transitions to strip/add zero-width spaces for Thai word-wrapping
    canvas.on('text:editing:entered' as any, (e: any) => {
      const obj = e.target as any;
      if (obj && obj.type === 'textbox') {
        interactionActiveRef.current = true;
        activeInteractionObjectRef.current = obj;
        let cleanText = (obj.text || '').replace(/\u200B/g, '');
        const activePage = useProjectStore.getState().activePage;
        const block = activePage?.text_blocks?.find(b => b.id === obj.data?.blockId);
        const isSpecBacked = showTranslatedRef.current && isValidCanonicalSpec(block?.extra_metadata?.typesetting_spec);
        if (isSpecBacked) {
          // The display adapter normally supplies explicit lines without
          // changing textbox.text. Fabric disables that adapter while editing,
          // which previously made the raw translation re-wrap immediately and
          // jump away from the layout the user clicked. Materialise the chosen
          // lines as real newlines before the edit session begins.
          const spec = block!.extra_metadata!.typesetting_spec;
          cleanText = spec.explicit_lines.join('\n').replace(/\u200B/g, '');
          removeExplicitLineAdapter(obj);
        }
        obj.set({
          text: cleanText,
          splitByGrapheme: isSpecBacked ? false : shouldSplitCanvasTextByGrapheme(cleanText)
        });
        canvas.requestRenderAll();
      }
    });

    canvas.on('text:editing:exited' as any, async (e: any) => {
      const obj = e.target as any;
      if (obj && obj.type === 'textbox') {
        interactionActiveRef.current = false;
        activeInteractionObjectRef.current = null;
        cancelScheduledAutoFit(obj);
        const rawText = obj.text || '';
        const blockId = obj.data?.blockId;
        
        const activePage = useProjectStore.getState().activePage;
        const block = activePage?.text_blocks?.find(b => b.id === blockId);
        const isSpecBacked = showTranslatedRef.current && isValidCanonicalSpec(block?.extra_metadata?.typesetting_spec);
        const isAutoMode = isAutoFontSizeEnabled(block);

        // The adapter closes over the pre-edit explicit lines. Remove it before
        // committing so the edited text/newlines remain visible while the fresh
        // backend spec is being computed.
        if (isSpecBacked) {
          removeExplicitLineAdapter(obj);
        }
        
        if (!isSpecBacked) {
          const formattedText = cleanThaiText(rawText);
          obj.set({
            text: formattedText,
            splitByGrapheme: shouldSplitCanvasTextByGrapheme(rawText)
          });
        } else {
          obj.set({
            text: cleanThaiText(rawText),
            splitByGrapheme: false
          });
        }
        if (isAutoMode) {
          autoFitTextboxFontSize(obj, canvas, scaleFactorRef.current, true);
        }
        canvas.requestRenderAll();

        // Commit final text to the database once editing is finished
        if (blockId) {
          const cleanText = rawText.replace(/\u200B/g, '');
          if (showTranslatedRef.current) {
            const { typesetting_spec: _staleSpec, ...freshMetadata } = block?.extra_metadata || {};
            await updateBlock(blockId, {
              translation: cleanText,
              extra_metadata: {
                ...freshMetadata,
                line_break_source: 'manual_hard',
                ai_preferred_lines: null,
                ai_layout_hint: null,
                ai_layout_text: null,
              },
            });
          } else {
            await updateBlock(blockId, {
              source_text: cleanText
            });
          }
        }
      }
    });

    // Clean image mode intentionally loads the canonical clean PNG.  The regular
    // workspace still uses preview.jpg, so normal navigation never decodes a
    // 7k-20k source image just to edit text.
    const pageId = activePage.id;
    const hasInpaintAsset = Boolean(activePage.inpainted_image_path);
    const hasCleanImage = showInpainted && hasInpaintAsset && !cleanImageUnavailable;
    const primaryUrl = hasCleanImage
      ? `/api/pages/${pageId}/image?clean=true&v=${cleanImageVersion}-${cleanPreviewRevision}`
      : `/api/pages/${pageId}/preview`;
    const fallbackUrl = `/api/pages/${pageId}/preview`;

    const handleLoadedImage = (loadedImg: HTMLImageElement) => {
      if (!fabricCanvasRef.current || fabricCanvasRef.current !== canvas) return;

      const naturalW = loadedImg.naturalWidth || activePage.width || 800;
      const naturalH = loadedImg.naturalHeight || activePage.height || 600;
      const performanceProfile = String(activeProject?.settings?.performance_profile || 'balanced');
      const customPreviewWidth = Number(activeProject?.settings?.performance_custom?.preview_width || 1200);
      const pixelBudget = resolveCanvasPixelBudget(performanceProfile, customPreviewWidth);
      const workingDimensions = fitCanvasWorkingDimensions(naturalW, naturalH, pixelBudget);
      const drawW = workingDimensions.width;
      const drawH = workingDimensions.height;

      console.log(
        `[Canvas] Working dimensions: ${drawW}x${drawH}` +
        (workingDimensions.downsampled ? ` (source ${naturalW}x${naturalH}, adaptive budget)` : ''),
      );
      setStatus(`Page loaded successfully`, false);
      
      imgDimensionsRef.current = { width: drawW, height: drawH };
      setImgDimensions({ width: drawW, height: drawH });

      const realScaleFactor = (activePage.width || drawW) / drawW;
      setScaleFactor(realScaleFactor);
      scaleFactorRef.current = realScaleFactor;

      // Set dimensions of canvas to match image dimensions
      canvas.setDimensions({ width: drawW, height: drawH });
      setIsImageLoaded(true);

      // Preserving manual zoom level if user has disabled auto fit
      if (isZoomAutoFitRef.current) {
        // Calculate initial zoom to fit workspace width
        const workspaceWidth = workspaceRef.current?.clientWidth || 700;
        let initZoom = Math.min(1.0, (workspaceWidth - 80) / drawW);
        if (initZoom < 0.05) initZoom = 0.05;
        setZoomLevel(initZoom);
      } else {
        setIsZoomAutoFit(false);
        isZoomAutoFitRef.current = false;
      }

      // Restore scroll position on same-page reload, reset only on new page navigation.
      if (workspaceRef.current) {
        const ws = workspaceRef.current;
        const savedScroll = { ...lastScrollPosRef.current };
        const pId = activePage.id;
        requestAnimationFrame(() => {
          if (!ws) return;
          if (lastPageIdRef.current === pId && (savedScroll.scrollTop > 0 || savedScroll.scrollLeft > 0)) {
            ws.scrollTop = savedScroll.scrollTop;
            ws.scrollLeft = savedScroll.scrollLeft;
          } else if (lastPageIdRef.current !== pId) {
            ws.scrollTop = 0;
            ws.scrollLeft = 0;
          }
        });
      }

      canvas.requestRenderAll();
    };

    const htmlImg = new Image();
    htmlImg.onload = () => handleLoadedImage(htmlImg);
    htmlImg.onerror = () => {
      console.warn(`[Canvas] Primary image load failed (${primaryUrl}), falling back to preview.jpg`);
      if (primaryUrl !== fallbackUrl) {
        const fallbackImg = new Image();
        fallbackImg.onload = () => handleLoadedImage(fallbackImg);
        fallbackImg.onerror = () => {
          console.error(`[Canvas] Fallback image load also failed (${fallbackUrl})`);
          setStatus('Page image unavailable', false);
          setIsImageLoaded(true); // Always release loading spinner
        };
        fallbackImg.src = fallbackUrl;
      } else {
        setStatus('Page image unavailable', false);
        setIsImageLoaded(true); // Always release loading spinner
      }
    };
    htmlImg.src = primaryUrl;

    return () => {
      if (snapAnimationFrame !== null) cancelAnimationFrame(snapAnimationFrame);
      htmlImg.onload = null;
      htmlImg.onerror = null;
      htmlImg.src = '';
      if (fabricCanvasRef.current) {
        try {
          fabricCanvasRef.current.dispose();
        } catch (_) {}
        fabricCanvasRef.current = null;
      }
    };
  }, [
    activePage?.id,
    activePage?.inpainted_image_path,
    activeProject?.settings?.performance_profile,
    activeProject?.settings?.performance_custom?.preview_width,
    showInpainted,
    cleanImageVersion,
    cleanPreviewRevision,
    cleanImageUnavailable,
  ]);

  // Dynamically update Fabric Canvas dimensions and zoom
  useEffect(() => {
    const canvas = fabricCanvasRef.current;
    if (!canvas) return;

    // CSS zoom keeps long pages responsive, while a bounded zoom-aware retina
    // backing prevents translated glyphs from becoming a stretched bitmap.
    if (canvas.getZoom() !== 1) canvas.setZoom(1);
    const performanceProfile = String(activeProject?.settings?.performance_profile || 'balanced');
    const nextRetinaScale = resolveCanvasZoomRetinaScale(
      performanceProfile,
      window.devicePixelRatio,
      zoomLevel,
    );
    const retinaChanged = Math.abs(canvasRetinaScaleRef.current - nextRetinaScale) > 0.01;
    if (retinaChanged) canvasRetinaScaleRef.current = nextRetinaScale;
    if (retinaChanged || canvas.width !== imgDimensions.width || canvas.height !== imgDimensions.height) {
      canvas.setDimensions({ width: imgDimensions.width, height: imgDimensions.height });
    }
    canvas.setDimensions({
      width: imgDimensions.width * zoomLevel,
      height: imgDimensions.height * zoomLevel,
    }, { cssOnly: true });
    if (canvas.wrapperEl) {
      canvas.wrapperEl.style.width = `${imgDimensions.width * zoomLevel}px`;
      canvas.wrapperEl.style.height = `${imgDimensions.height * zoomLevel}px`;
    }
    canvas.calcOffset();
    canvas.requestRenderAll();
  }, [zoomLevel, imgDimensions, activePage?.id, activeProject?.settings?.performance_profile]);

  // Synchronize TextBlocks from Zustand store to Fabric Canvas objects
  useEffect(() => {
    const canvas = fabricCanvasRef.current;
    if (!canvas || !activePage || !isImageLoaded) return;


    const canvasBoxMap = new Map<string, fabric.Textbox>();
    const duplicateTextboxes: fabric.Textbox[] = [];
    const activeCanvasObjects = new Set(canvas.getActiveObjects());
    const currentTextboxes: fabric.Textbox[] = [];
    canvas.getObjects().forEach(obj => {
      if (obj.type === 'textbox') {
        currentTextboxes.push(obj as fabric.Textbox);
      } else if (obj.type === 'activeSelection' || obj.type === 'group') {
        const children = typeof (obj as any).getObjects === 'function' ? (obj as any).getObjects() : [];
        children.forEach((gObj: any) => {
          if (gObj.type === 'textbox') {
            currentTextboxes.push(gObj as fabric.Textbox);
          }
        });
      }
    });
    currentTextboxes.forEach(tb => {
      const blockId = (tb as any).data?.blockId;
      if (!blockId) return;
      const existing = canvasBoxMap.get(blockId);
      if (!existing) {
        canvasBoxMap.set(blockId, tb);
      } else if (activeCanvasObjects.has(tb) && !activeCanvasObjects.has(existing)) {
        duplicateTextboxes.push(existing);
        canvasBoxMap.set(blockId, tb);
      } else {
        duplicateTextboxes.push(tb);
      }
    });
    if (duplicateTextboxes.length > 0) {
      duplicateTextboxes.forEach(textbox => canvas.remove(textbox));
      canvas.requestRenderAll();
    }

    if (canvas.getActiveObject()?.type === 'activeSelection') {
      blockRenderSignaturesRef.current.clear();
      isProgrammaticSelectionChangeRef.current = true;
      canvas.discardActiveObject();
      isProgrammaticSelectionChangeRef.current = false;
    }

    const activeObj = canvas.getActiveObject();
    const isEditingAny = activeObj && (activeObj as any).isEditing;
    const isInteractive = (canvasMode === 'select' || canvasMode === 'text') && (showTypesetting || !showTranslated) && !isMaskMode;
    const textEditingOnly = canvasMode === 'text';
    const renderContext = [activePage.id, scaleFactor, showTranslated, showTypesetting, canvasMode, isMaskMode, useTypesettingLayout].join('|');
    if (blockRenderContextRef.current !== renderContext) {
      blockRenderContextRef.current = renderContext;
      blockRenderSignaturesRef.current.clear();
    }
    const nextRenderSignatures = new Map<string, string>();
    let hasRenderWork = false;
    const controlMetrics = resolveCanvasControlMetrics(zoomLevel);

    // 1. Add or Update textboxes from store
    const sortedBlocks = [...activePage.text_blocks].sort((a, b) => a.block_index - b.block_index);
    sortedBlocks.forEach((block, i) => {
      const displayIndex = i + 1;
      const spec = block.extra_metadata?.typesetting_spec;
      const hasSpec = isValidCanonicalSpec(spec);
      // Canonical TypesettingSpec contains the translated lines and translated
      // layout. It must never be applied while the source view is active.
      const textView = resolveCanvasTextView(block, showTranslated);
      const usesCanonicalSpec = textView.usesCanonicalSpec && hasSpec;
      const storedManualFontSize = Number(block.extra_metadata?.manual_font_size);
      const hasManualFontSize = (
        block.extra_metadata?.font_size_mode === 'manual'
        || (Number.isFinite(storedManualFontSize) && storedManualFontSize > 0)
      );
      // A manual font edit must be visible immediately and must not be
      // overwritten by the prior TypesettingSpec while the recompute request
      // is in flight. The server rebuilds the same canonical Spec afterwards,
      // so Canvas, PNG/JPEG, and PSD converge on one size.
      const isAutoFontSize = isAutoFontSizeEnabled(block);
      const displayFontSize = (usesCanonicalSpec && !hasManualFontSize)
        ? spec.font_size
        : (hasManualFontSize && Number.isFinite(storedManualFontSize) && storedManualFontSize > 0
          ? storedManualFontSize
          : block.font_size);
      const displayLineHeightRatio = (usesCanonicalSpec && !hasManualFontSize)
        ? spec.line_height / spec.font_size
        : Number(block.extra_metadata?.line_height_ratio ?? (usesCanonicalSpec ? spec.line_height / spec.font_size : 1.2));
      const isSmartBalloonEnabled = getEffectiveEnableSmartBalloon(activeProject?.settings);
      // Review mode uses the detector's canonical box. Typesetting mode can
      // opt into the independently calculated layout_region when available.
      const resolvedRegion = resolveCanvasLayoutRegion(
        block,
        usesCanonicalSpec ? spec : undefined,
        useTypesettingLayout,
        isSmartBalloonEnabled,
      );
      const usesLayoutRegion = resolvedRegion.usesLayoutRegion;
      const displayRegion = resolvedRegion.region;
      const displayRotation = usesCanonicalSpec ? spec.rotation_deg : block.rotation_deg;
      const layoutPadding = normalizeTextPadding(
        usesCanonicalSpec ? spec.padding : block.extra_metadata?.padding,
      );
      const paddedTextRegion = resolvePaddedTextRegion(
        displayRegion,
        layoutPadding,
        displayRotation,
      );
      const x = paddedTextRegion.x / scaleFactor;
      const y = paddedTextRegion.y / scaleFactor;
      const width = paddedTextRegion.width / scaleFactor;
      const height = paddedTextRegion.height / scaleFactor;
      
      const textVal = textView.text;
      const isVisible = block.is_visible !== false && block.extra_metadata?.is_visible !== false;
      const isLocked = block.is_locked === true || block.extra_metadata?.is_locked === true;

      const existingTb = canvasBoxMap.get(block.id);
      const decisionBadge = resolveDecisionBadge(spec);
      const configuredMinimum = Number(block.extra_metadata?.min_font_size);
      const minFontSize = Number.isFinite(configuredMinimum) && configuredMinimum > 0
        ? configuredMinimum
        : 6;
      const configuredMaximum = Number(block.extra_metadata?.max_font_size);
      const maxFontSize = Number.isFinite(configuredMaximum) && configuredMaximum > 0
        ? Math.max(minFontSize, configuredMaximum)
        : Math.max(140, Math.min(displayRegion.width, displayRegion.height) * 0.45);
      const blockGradient = usesCanonicalSpec ? spec?.gradient : (block.extra_metadata?.gradient || block.extra_metadata?.detected_gradient);
      const blockMangaEffects = buildMangaEffects(usesCanonicalSpec ? spec : null, block.extra_metadata);
      const renderSignature = [
        displayIndex, textVal, x, y, width, height, block.rotation_deg,
        block.color_hex, block.font_size, block.font_family, block.bold,
        block.italic, block.text_align, block.balloon_type, block.confidence,
        usesCanonicalSpec ? spec.source_signature : '',
        usesCanonicalSpec ? spec.layout_status : '',
        displayFontSize,
        usesCanonicalSpec ? spec.resolved_font_family : '',
        usesCanonicalSpec ? spec.explicit_lines?.join('\n') : '',
        usesCanonicalSpec ? (spec.decision_status || '') : '',
        layoutPadding.top, layoutPadding.right, layoutPadding.bottom, layoutPadding.left,
        minFontSize, maxFontSize, isAutoFontSize ? 'auto' : 'manual',
        controlMetrics.cornerSize, controlMetrics.touchCornerSize,
        decisionBadge.status, isVisible ? 'v' : 'h', isLocked ? 'l' : 'u',
        isSmartBalloonEnabled ? 'sb_on' : 'sb_off',
        gradientSignature(blockGradient),
        multiEffectSignature(blockMangaEffects),
      ].join('|');
      nextRenderSignatures.set(block.id, renderSignature);

      if (existingTb && blockRenderSignaturesRef.current.get(block.id) === renderSignature) {
        canvasBoxMap.delete(block.id);
        return;
      }
      hasRenderWork = true;

      if (existingTb) {
        const isEditingThis = activeObj === existingTb && isEditingAny;

        if (!isEditingThis) {
          const newFontSize = displayFontSize / scaleFactor;
          
          let newFontWeight = block.bold ? 'bold' : 'normal';
          let newFontStyle = block.italic ? 'italic' : 'normal';
          if (usesCanonicalSpec) {
            // Fabric/Canvas can synthesize bold/italic when the selected family
            // has no dedicated face, matching Photoshop Faux styles.
            newFontWeight = spec.bold ? 'bold' : 'normal';
            newFontStyle = spec.italic ? 'italic' : 'normal';
          }
          
          const formattedText = cleanThaiText(textVal);
          const needsSplit = shouldSplitCanvasTextByGrapheme(textVal);

          const hasSmartBalloon = isSmartBalloonEnabled && Boolean(
            block.smart_x != null || block.extra_metadata?.smart_balloon?.contour_points
          );

          // Warning / overflow border color & customization
          let statusColor = '#f97316';
          if (usesCanonicalSpec) {
            if (spec.layout_status === 'overflow') {
              statusColor = '#ff3b30';
            } else if (spec.layout_status === 'warning') {
              statusColor = '#ffcc00';
            }
          }

          const specLineHeightVal = displayLineHeightRatio;
          const specFamilyVal = usesCanonicalSpec ? spec.resolved_font_family : block.font_family;
          const specAlignVal = usesCanonicalSpec ? (spec.text_align || spec.horizontal_align) : block.text_align;
          const specAngleVal = displayRotation;
          const specCharSpacingVal = usesCanonicalSpec
            ? Number((spec as { tracking?: number }).tracking ?? 0)
            : Number(block.extra_metadata?.tracking ?? block.extra_metadata?.letter_spacing ?? 0);
          const strokeProps = usesCanonicalSpec
            ? fabricStrokeFromSpec(spec)
            : fabricStrokeFromSpec({
                stroke_width: Number(block.extra_metadata?.stroke_width ?? 0),
                stroke_color: String(block.extra_metadata?.stroke_color ?? ''),
              });
          const glowProps = usesCanonicalSpec
            ? fabricGlowFromSpec(spec)
            : fabricGlowFromSpec({
                outline_glow_radius: Number(block.extra_metadata?.outline_glow_radius ?? 0),
                outline_glow_color: String(block.extra_metadata?.outline_glow_color ?? '#ffffff'),
                outline_glow_opacity: Number(block.extra_metadata?.outline_glow_opacity ?? 0),
                outer_glow: block.extra_metadata?.detected_outer_glow || block.extra_metadata?.outer_glow,
              });

          const resolvedFill = fabricFillFromSpec({
            color_hex: block.color_hex || (usesCanonicalSpec && (spec as { color_hex?: string }).color_hex) || '#000000',
            gradient: blockGradient,
          }, width, height);

          // Check if properties actually changed to avoid layout re-calculation.
          // Stroke/strokeWidth/paintFirst MUST be included — stroke-only Spec
          // updates (e.g. template outline) would otherwise leave Fabric stale.
          const hasChanged = 
            existingTb.text !== formattedText ||
            existingTb.splitByGrapheme !== needsSplit ||
            existingTb.left !== x ||
            existingTb.top !== y ||
            existingTb.width !== width ||
            existingTb.height !== height ||
            existingTb.angle !== specAngleVal ||
            existingTb.fill !== resolvedFill ||
            existingTb.fontSize !== newFontSize ||
            existingTb.fontFamily !== specFamilyVal ||
            existingTb.textAlign !== specAlignVal ||
            existingTb.fontWeight !== newFontWeight ||
            existingTb.fontStyle !== newFontStyle ||
            existingTb.lineHeight !== specLineHeightVal ||
            existingTb.charSpacing !== specCharSpacingVal ||
            fabricStrokeNeedsUpdate(existingTb as { stroke?: string; strokeWidth?: number; paintFirst?: string }, strokeProps) ||
            fabricGlowNeedsUpdate(existingTb.shadow as any, glowProps) ||
            multiEffectNeedsUpdate((existingTb as any).mangaEffects, blockMangaEffects) ||
            existingTb.objectCaching !== false ||
            existingTb.visible !== isVisible ||
            existingTb.selectable !== (isInteractive && isVisible) ||
            existingTb.evented !== (isInteractive && isVisible) ||
            existingTb.borderColor !== statusColor ||
            existingTb.cornerStrokeColor !== statusColor ||
            (existingTb as any).data?.usesCanonicalSpec !== usesCanonicalSpec ||
            (existingTb as any).data?.minFontSize !== minFontSize ||
            (existingTb as any).data?.maxFontSize !== maxFontSize ||
            (existingTb as any).data?.autoFontSize !== isAutoFontSize ||
            JSON.stringify((existingTb as any).data?.layoutPadding || {}) !== JSON.stringify(layoutPadding) ||
            (existingTb as any).editable !== (showTypesetting && canvasMode === 'text');

          if (hasChanged) {
            existingTb.calcTextHeight = function(this: fabric.Textbox) {
              return height;
            };

            if (usesCanonicalSpec) {
              applyExplicitLineAdapter(existingTb, spec.explicit_lines);
            } else {
              removeExplicitLineAdapter(existingTb);
            }

            // Apply Smart Balloon shape-adaptive features
            const sbMeta = block.extra_metadata?.smart_balloon as SmartBalloonMetadata | undefined;
            if (hasSmartBalloon && sbMeta) {
              // 1. Apply polygon-based selection handles
              if (sbMeta.contour_points && sbMeta.contour_points.length > 3) {
                createPolygonControls(existingTb, sbMeta.contour_points, scaleFactor);
              }
              // 2. Apply shape-adaptive text wrapping
              if (sbMeta.row_width_constraints?.enabled && sbMeta.safe_bbox) {
                applyShapeAdaptiveWrapping(
                  existingTb,
                  sbMeta.row_width_constraints,
                  scaleFactor,
                  sbMeta.safe_bbox
                );
              }
            } else {
              // Remove Smart Balloon features if not applicable
              removePolygonControls(existingTb);
              removeShapeAdaptiveWrapping(existingTb);
            }

            existingTb.set({
              text: formattedText,
              left: x,
              top: y,
              width: width,
              height: height,
              scaleX: 1,
              scaleY: 1,
              fontSize: newFontSize,
              fontFamily: specFamilyVal,
              fill: resolvedFill,
              textAlign: specAlignVal,
              fontWeight: newFontWeight,
              fontStyle: newFontStyle,
              lineHeight: specLineHeightVal,
              charSpacing: specCharSpacingVal,
              angle: specAngleVal,
              stroke: strokeProps.stroke,
              strokeWidth: strokeProps.strokeWidth,
              paintFirst: strokeProps.paintFirst || 'fill',
              shadow: (!blockMangaEffects.dropShadow && !blockMangaEffects.outerGlow && glowProps)
                ? new fabric.Shadow(glowProps)
                : null,
              // The Fabric layer is CSS-scaled independently from the page
              // image. Reusing a bitmap text cache makes glyphs visibly soft.
              objectCaching: false,
              visible: isVisible,
              selectable: isInteractive && isVisible,
              evented: isInteractive && isVisible,
              editable: showTypesetting && canvasMode === 'text' && !isLocked,
              lockMovementX: textEditingOnly || isLocked,
              lockMovementY: textEditingOnly || isLocked,
              lockRotation: textEditingOnly || isLocked,
              lockScalingX: textEditingOnly || isLocked,
              lockScalingY: textEditingOnly || isLocked,
              hasControls: !textEditingOnly && !isLocked,
              splitByGrapheme: needsSplit,
              borderColor: statusColor,
              borderScaleFactor: controlMetrics.borderScaleFactor,
              borderOpacityWhenMoving: 1,
              cornerStyle: 'rect',
              cornerColor: '#ffffff',
              cornerStrokeColor: statusColor,
              cornerSize: controlMetrics.cornerSize,
              touchCornerSize: controlMetrics.touchCornerSize,
              transparentCorners: false,
              // Fabric's padding is part of the rendered textbox geometry, not
              // just a hit-target. The canonical TypesettingSpec already owns
              // per-side padding; a hard-coded 8px here made Preview/PNG/PSD
              // drift and caused text to look smaller until Photoshop Transform.
              centeredRotation: true,
              snapAngle: 0,
              snapThreshold: 0,
              padding: 0,
            });
            (existingTb as any).mangaEffects = blockMangaEffects;
            applyMultiEffectTextRenderer(existingTb);

            (existingTb as any).initDimensions?.();
            existingTb.setCoords();
            existingTb.setControlsVisibility((textEditingOnly || isLocked)
              ? { tl: false, tr: false, bl: false, br: false, mt: false, mb: false, ml: false, mr: false, mtr: false }
              : { tl: true, tr: true, bl: true, br: true, mt: true, mb: true, ml: true, mr: true, mtr: true });
            if (existingTb.controls?.mtr) existingTb.controls.mtr.render = renderRotateIcon;

            (existingTb as any).data = {
              blockId: block.id,
              blockIndex: displayIndex,
              confidence: block.confidence,
              balloonType: block.balloon_type,
              minFontSize,
              maxFontSize,
              autoFontSize: isAutoFontSize,
              layoutPadding,
              usesLayoutRegion,
              usesCanonicalSpec,
              hasFinalTranslation: Boolean((block.translation || '').trim()),
              decisionStatus: usesCanonicalSpec ? decisionBadge.status : undefined,
              decisionStroke: usesCanonicalSpec ? decisionBadge.stroke : undefined,
              isLocked,
              isVisible,
              maskType: block.mask_type,
            };
            (existingTb as any).initDimensions();
            if (specFamilyVal) {
              ensureFontLoaded(specFamilyVal, newFontWeight, newFontStyle, formattedText).then((loaded) => {
                if (loaded) {
                  (existingTb as any).initDimensions?.();
                  existingTb.setCoords();
                  canvas.requestRenderAll();
                }
              });
            }
            if (isAutoFontSize) {
              removeExplicitLineAdapter(existingTb);
              autoFitTextboxFontSize(existingTb, canvas, scaleFactorRef.current, true);
            }
          }
        } else {
          // Sidebar typography controls must remain live while the Fabric textbox
          // is in editing mode. Preserve the user's caret/text, but apply style.
          const isSel = isInteractive && isVisible;
          const editingFontSize = displayFontSize / scaleFactor;
          const editingFontFamily = usesCanonicalSpec ? spec.resolved_font_family : block.font_family;
          const editingFontWeight = usesCanonicalSpec ? Boolean(spec.bold) : Boolean(block.bold);
          const editingFontItalic = usesCanonicalSpec ? Boolean(spec.italic) : Boolean(block.italic);
          const editingGradient = usesCanonicalSpec ? spec?.gradient : (block.extra_metadata?.gradient || block.extra_metadata?.detected_gradient);
          const editingMangaEffects = buildMangaEffects(usesCanonicalSpec ? spec : null, block.extra_metadata);
          const editingFill = block.color_hex || (usesCanonicalSpec && spec.color_hex ? spec.color_hex : '#000000');
          const editingResolvedFill = fabricFillFromSpec({
            color_hex: editingFill,
            gradient: editingGradient,
          }, existingTb.width || width, existingTb.height || height);
          const editingAlign = usesCanonicalSpec ? (spec.text_align || spec.horizontal_align) : block.text_align;
          const editingTracking = usesCanonicalSpec
            ? Number(spec.tracking ?? 0)
            : Number(block.extra_metadata?.tracking ?? block.extra_metadata?.letter_spacing ?? 0);
          const editingStroke = usesCanonicalSpec
            ? fabricStrokeFromSpec(spec)
            : fabricStrokeFromSpec({
                stroke_width: Number(block.extra_metadata?.stroke_width ?? 0),
                stroke_color: String(block.extra_metadata?.stroke_color ?? ''),
              });
          const editingGlow = usesCanonicalSpec
            ? fabricGlowFromSpec(spec)
            : fabricGlowFromSpec({
                outline_glow_radius: Number(block.extra_metadata?.outline_glow_radius ?? 0),
                outline_glow_color: String(block.extra_metadata?.outline_glow_color ?? '#ffffff'),
                outline_glow_opacity: Number(block.extra_metadata?.outline_glow_opacity ?? 0),
                outer_glow: block.extra_metadata?.detected_outer_glow || block.extra_metadata?.outer_glow,
              });
          const caretStart = existingTb.selectionStart;
          const caretEnd = existingTb.selectionEnd;
          existingTb.set({
            visible: isVisible,
            selectable: isSel,
            evented: isSel,
            editable: showTypesetting && canvasMode === 'text' && !isLocked,
            lockMovementX: textEditingOnly || isLocked,
            lockMovementY: textEditingOnly || isLocked,
            lockRotation: textEditingOnly || isLocked,
            lockScalingX: textEditingOnly || isLocked,
            lockScalingY: textEditingOnly || isLocked,
            hasControls: !textEditingOnly && !isLocked,
            fontSize: editingFontSize,
            fontFamily: editingFontFamily,
            fill: editingResolvedFill,
            textAlign: editingAlign,
            fontWeight: editingFontWeight ? 'bold' : 'normal',
            fontStyle: editingFontItalic ? 'italic' : 'normal',
            lineHeight: displayLineHeightRatio,
            charSpacing: editingTracking,
            stroke: editingStroke.stroke,
            strokeWidth: editingStroke.strokeWidth,
            paintFirst: editingStroke.paintFirst || 'fill',
            shadow: (!editingMangaEffects.dropShadow && !editingMangaEffects.outerGlow && editingGlow)
              ? new fabric.Shadow(editingGlow)
              : null,
            borderScaleFactor: controlMetrics.borderScaleFactor,
            borderOpacityWhenMoving: 1,
            cornerStyle: 'rect',
            cornerColor: '#ffffff',
            cornerStrokeColor: '#f97316',
            cornerSize: controlMetrics.cornerSize,
            touchCornerSize: controlMetrics.touchCornerSize,
            transparentCorners: false,
             // Keep Fabric geometry aligned with the canonical spec. Selection
             // handles remain usable via cornerSize/touchCornerSize above.
             padding: 0,
          });
          (existingTb as any).mangaEffects = editingMangaEffects;
          applyMultiEffectTextRenderer(existingTb);
          existingTb.setControlsVisibility((textEditingOnly || isLocked)
            ? { tl: false, tr: false, bl: false, br: false, mt: false, mb: false, ml: false, mr: false, mtr: false }
            : { tl: true, tr: true, bl: true, br: true, mt: true, mb: true, ml: true, mr: true, mtr: true });
          if (existingTb.controls?.mtr) existingTb.controls.mtr.render = renderRotateIcon;
          existingTb.initDimensions();
          existingTb.setCoords();
          // Keep the active caret/range stable while sidebar controls update
          // font size repeatedly. Fabric may clamp these values during layout.
          const textLength = existingTb.text?.length || 0;
          existingTb.selectionStart = Math.min(caretStart, textLength);
          existingTb.selectionEnd = Math.min(caretEnd, textLength);
          if (canvas.getActiveObject() !== existingTb) {
            isProgrammaticSelectionChangeRef.current = true;
            canvas.setActiveObject(existingTb);
            isProgrammaticSelectionChangeRef.current = false;
          }
        }
        // Remove from map to indicate it is still present
        canvasBoxMap.delete(block.id);
      } else {
        // Create new textbox
        const formattedText = cleanThaiText(textVal);
        const needsSplit = shouldSplitCanvasTextByGrapheme(textVal);
        
        const hasSmartBalloon = isSmartBalloonEnabled && Boolean(
          block.smart_x != null || block.extra_metadata?.smart_balloon?.contour_points
        );

        let statusColor = '#f97316';
        if (usesCanonicalSpec) {
          if (spec.layout_status === 'overflow') {
            statusColor = '#ff3b30';
          } else if (spec.layout_status === 'warning') {
            statusColor = '#ffcc00';
          }
        }

        const newFontSize = displayFontSize / scaleFactor;
        
        let newFontWeight = block.bold ? 'bold' : 'normal';
        let newFontStyle = block.italic ? 'italic' : 'normal';
        if (usesCanonicalSpec) {
          newFontWeight = spec.bold ? 'bold' : 'normal';
          newFontStyle = spec.italic ? 'italic' : 'normal';
        }

        const specLineHeightVal = displayLineHeightRatio;
        const specFamilyVal = usesCanonicalSpec ? spec.resolved_font_family : block.font_family;
        const specAlignVal = usesCanonicalSpec ? (spec.text_align || spec.horizontal_align) : block.text_align;
        const specAngleVal = usesCanonicalSpec ? spec.rotation_deg : block.rotation_deg;
        const specCharSpacingVal = usesCanonicalSpec
          ? Number((spec as { tracking?: number }).tracking ?? 0)
          : Number(block.extra_metadata?.tracking ?? block.extra_metadata?.letter_spacing ?? 0);
        const newStrokeProps = usesCanonicalSpec
          ? fabricStrokeFromSpec(spec)
          : fabricStrokeFromSpec({
              stroke_width: Number(block.extra_metadata?.stroke_width ?? 0),
              stroke_color: String(block.extra_metadata?.stroke_color ?? ''),
            });
        const newGlowProps = usesCanonicalSpec
          ? fabricGlowFromSpec(spec)
          : fabricGlowFromSpec({
              outline_glow_radius: Number(block.extra_metadata?.outline_glow_radius ?? 0),
              outline_glow_color: String(block.extra_metadata?.outline_glow_color ?? '#ffffff'),
              outline_glow_opacity: Number(block.extra_metadata?.outline_glow_opacity ?? 0),
              outer_glow: block.extra_metadata?.detected_outer_glow || block.extra_metadata?.outer_glow,
            });

        const newResolvedFill = fabricFillFromSpec({
          color_hex: block.color_hex || (usesCanonicalSpec && (spec as { color_hex?: string }).color_hex) || '#000000',
          gradient: blockGradient,
        }, width, height);

        const textbox = new fabric.Textbox(formattedText, {
          left: x,
          top: y,
          width: width,
          height: height,
          originX: 'left',
          originY: 'top',
          fontSize: newFontSize,
          fontFamily: specFamilyVal,
          fill: newResolvedFill,
          textAlign: specAlignVal,
          fontWeight: newFontWeight,
          fontStyle: newFontStyle,
          lineHeight: specLineHeightVal,
          charSpacing: specCharSpacingVal,
          angle: specAngleVal,
          stroke: newStrokeProps.stroke,
          strokeWidth: newStrokeProps.strokeWidth,
          paintFirst: newStrokeProps.paintFirst || 'fill',
          shadow: (!blockMangaEffects.dropShadow && !blockMangaEffects.outerGlow && newGlowProps)
            ? new fabric.Shadow(newGlowProps)
            : null,
          objectCaching: false,
          visible: isVisible,
          selectable: isInteractive && isVisible,
          evented: isInteractive && isVisible,
          editable: showTypesetting && canvasMode === 'text' && !isLocked,
          lockMovementX: textEditingOnly || isLocked,
          lockMovementY: textEditingOnly || isLocked,
          lockRotation: textEditingOnly || isLocked,
          lockScalingX: textEditingOnly || isLocked,
          lockScalingY: textEditingOnly || isLocked,
          hasControls: !textEditingOnly && !isLocked,
          
          borderColor: statusColor,
          borderScaleFactor: controlMetrics.borderScaleFactor,
          borderOpacityWhenMoving: 1,
          cornerStyle: 'rect',
          cornerColor: '#ffffff',
          cornerStrokeColor: statusColor,
          cornerSize: controlMetrics.cornerSize,
          touchCornerSize: controlMetrics.touchCornerSize,
          centeredRotation: true,
          snapAngle: 0,
          snapThreshold: 0,
          padding: 0,
          lockScalingFlip: true,
          
          splitByGrapheme: needsSplit,
          data: {
            blockId: block.id,
            blockIndex: displayIndex,
            confidence: block.confidence,
            balloonType: block.balloon_type,
            minFontSize,
            maxFontSize,
            autoFontSize: isAutoFontSize,
            layoutPadding,
            usesLayoutRegion,
            usesCanonicalSpec,
            hasFinalTranslation: Boolean((block.translation || '').trim()),
            decisionStatus: usesCanonicalSpec ? decisionBadge.status : undefined,
            decisionStroke: usesCanonicalSpec ? decisionBadge.stroke : undefined,
            isLocked,
            isVisible,
            maskType: block.mask_type,
          }
        } as any);
        (textbox as any).mangaEffects = blockMangaEffects;
        applyMultiEffectTextRenderer(textbox);
        if (isLocked) {
          textbox.setControlsVisibility({ tl: false, tr: false, bl: false, br: false, mt: false, mb: false, ml: false, mr: false, mtr: false });
        } else {
          textbox.setControlsVisibility({ tl: true, tr: true, bl: true, br: true, mt: true, mb: true, ml: true, mr: true, mtr: true });
        }
        if (textbox.controls?.mtr) textbox.controls.mtr.render = renderRotateIcon;

        textbox.calcTextHeight = function(this: fabric.Textbox) {
          // Always return the balloon bounding-box height so Fabric never
          // grows the textbox beyond the detected balloon region.
          return height;
        };

        if (usesCanonicalSpec) {
          applyExplicitLineAdapter(textbox, spec.explicit_lines);
        }

        // Apply Smart Balloon shape-adaptive features for new textboxes
        const sbMeta = block.extra_metadata?.smart_balloon as SmartBalloonMetadata | undefined;
        if (hasSmartBalloon && sbMeta) {
          // 1. Apply polygon-based selection handles
          if (sbMeta.contour_points && sbMeta.contour_points.length > 3) {
            createPolygonControls(textbox, sbMeta.contour_points, scaleFactor);
          }

          // 2. Apply shape-adaptive text wrapping
          if (sbMeta.row_width_constraints?.enabled && sbMeta.safe_bbox) {
            applyShapeAdaptiveWrapping(
              textbox,
              sbMeta.row_width_constraints,
              scaleFactor,
              sbMeta.safe_bbox
            );
          }

        }

        (textbox as any).initDimensions();
        textbox.setCoords();

        textbox.setControlsVisibility(textEditingOnly
          ? { tl: false, tr: false, bl: false, br: false, mt: false, mb: false, ml: false, mr: false, mtr: false }
          : { tl: true, tr: true, bl: true, br: true, mt: true, mb: true, ml: true, mr: true, mtr: true });
        if (textbox.controls?.mtr) textbox.controls.mtr.render = renderRotateIcon;
        canvas.add(textbox);
        if (specFamilyVal) {
          ensureFontLoaded(specFamilyVal, newFontWeight, newFontStyle, formattedText).then((loaded) => {
            if (loaded) {
              (textbox as any).initDimensions?.();
              textbox.setCoords();
              canvas.requestRenderAll();
            }
          });
        }
        const actualH = (fabric.Textbox.prototype as any).calcTextHeight.call(textbox);
        if (!usesCanonicalSpec && isAutoFontSize) {
          removeExplicitLineAdapter(textbox);
          autoFitTextboxFontSize(textbox, canvas, scaleFactorRef.current, true);
        } else if (actualH > height * 0.95) {
          // Manual mode intentionally preserves the requested font size even
          // when the fixed balloon reports overflow.
          canvas.requestRenderAll();
        }
      }
    });

    // 2. Remove textboxes that are no longer in the store
    let activeRemoved = false;
    if (canvasBoxMap.size > 0) hasRenderWork = true;
    canvasBoxMap.forEach((tb) => {
      if (canvas.getActiveObjects().includes(tb)) {
        activeRemoved = true;
      }
      canvas.remove(tb);
    });
    if (activeRemoved) {
      canvas.discardActiveObject();
    }

    blockRenderSignaturesRef.current = nextRenderSignatures;
    if (hasRenderWork) canvas.requestRenderAll();
  }, [activePage?.text_blocks, isImageLoaded, scaleFactor, showTranslated, showTypesetting, canvasMode, activePage?.id, isMaskMode, useTypesettingLayout, zoomLevel]);



  const selectedBlockIdsSignature = selectedBlocks.map((block) => block.id).join('|');

  // Sync selectedBlocks from store to Fabric Canvas selection. Style changes
  // replace block objects in Zustand, but must not reset Fabric text editing or
  // selection when the selected IDs themselves did not change.
  useEffect(() => {
    const canvas = fabricCanvasRef.current;
    if (!canvas || !isImageLoaded) return;

    const currentSelection = useProjectStore.getState();
    const currentSelectedBlocks = currentSelection.selectedBlocks;
    const currentSelectedBlock = currentSelection.selectedBlock;
    const activeObjects = canvas.getActiveObjects();
    const activeBlockIds = activeObjects.map(o => (o as any).data?.blockId).filter(Boolean);
    const storeBlockIds = currentSelectedBlocks.map(b => b.id);
    const hasFabricActiveSelection = canvas.getActiveObject()?.type === 'activeSelection';

    // If they already match, do nothing to prevent infinite loops or resetting selection
    const arraysMatch = activeBlockIds.length === storeBlockIds.length && 
                        activeBlockIds.every(id => storeBlockIds.includes(id));
    if (arraysMatch && !hasFabricActiveSelection) return;

    if (hasFabricActiveSelection) {
      isProgrammaticSelectionChangeRef.current = true;
      canvas.discardActiveObject();
      isProgrammaticSelectionChangeRef.current = false;
    }

    if (currentSelectedBlocks.length === 0) {
      isProgrammaticSelectionChangeRef.current = true;
      canvas.discardActiveObject();
      canvas.requestRenderAll();
      isProgrammaticSelectionChangeRef.current = false;
    } else if (currentSelectedBlocks.length === 1) {
      const found = canvas.getObjects().find(o => (o as any).data?.blockId === currentSelectedBlocks[0].id);
      if (found) {
        isProgrammaticSelectionChangeRef.current = true;
        canvas.setActiveObject(found);
        canvas.requestRenderAll();
        isProgrammaticSelectionChangeRef.current = false;
      }
    } else {
      // Keep batch selection in Zustand instead of grouping Fabric textboxes.
      // ActiveSelection converts child positions to group-relative coordinates
      // and can blank custom Textbox caches after an async bulk preset response.
      // A single primary object owns keyboard/transform controls, while every
      // selected layer still receives the selected overlay and batch updates.
      const primaryId = currentSelectedBlock?.id && storeBlockIds.includes(currentSelectedBlock.id)
        ? currentSelectedBlock.id
        : storeBlockIds[0];
      const primary = canvas.getObjects().find(object => (object as any).data?.blockId === primaryId);
      if (primary) {
        isProgrammaticSelectionChangeRef.current = true;
        canvas.setActiveObject(primary);
        canvas.requestRenderAll();
        isProgrammaticSelectionChangeRef.current = false;
      }
    }

    if (currentSelectedBlock && workspaceRef.current) {
      const blockCenterX = (currentSelectedBlock.x + currentSelectedBlock.width / 2) / scaleFactorRef.current * zoomLevel;
      const blockCenterY = (currentSelectedBlock.y + currentSelectedBlock.height / 2) / scaleFactorRef.current * zoomLevel;
      const viewW = workspaceRef.current.clientWidth || 700;
      const viewH = workspaceRef.current.clientHeight || 500;
      const targetLeft = Math.max(0, blockCenterX + 40 - viewW / 2);
      const targetTop = Math.max(0, blockCenterY + 40 - viewH / 2);
      workspaceRef.current.scrollTo({
        left: targetLeft,
        top: targetTop,
        behavior: 'smooth'
      });
    }
  }, [selectedBlockIdsSignature, selectedBlock?.id, activePage?.id, isImageLoaded]);

  // Adjust zoom utility
  const handleZoom = (type: 'in' | 'out' | 'reset') => {
    let newZoom = zoomLevel;
    if (type === 'in') {
      newZoom *= 1.25;
      setIsZoomAutoFit(false);
    }
    if (type === 'out') {
      newZoom *= 0.8;
      setIsZoomAutoFit(false);
    }
    if (type === 'reset') {
      const wsWidth = workspaceRef.current?.clientWidth || 700;
      newZoom = Math.min(1.0, (wsWidth - 80) / imgDimensions.width);
      setIsZoomAutoFit(true);
    }

    if (newZoom > 6.0) newZoom = 6.0;
    if (newZoom < 0.05) newZoom = 0.05;
    setZoomLevel(newZoom);
  };

  // Add box manually (fallback) - unused
  // const handleAddBox = async () => {
  //   if (!activePage) return;
  //   const x = (activePage.width / 2) - 100;
  //   const y = (activePage.height / 2) - 50;
  //   await createBlock(activePage.id, {
  //     x, y, width: 200, height: 100, translation: 'พิมพ์คำแปลใหม่'
  //   });
  // };

  // Delete box
  const deleteCanvasBlocks = async (blockIds: string[]) => {
    if (blockIds.length === 0) return;
    await deleteBlocks(blockIds);
    const remainingIds = new Set(
      useProjectStore.getState().activePage?.text_blocks.map(block => block.id) || [],
    );
    const confirmedDeletedIds = blockIds.filter(blockId => !remainingIds.has(blockId));
    if (confirmedDeletedIds.length === 0) return;

    confirmedDeletedIds.forEach(blockId => blockRenderSignaturesRef.current.delete(blockId));
    const canvas = fabricCanvasRef.current;
    if (canvas) removeFabricBlockObjects(canvas, confirmedDeletedIds);
  };

  const handleDeleteBox = async () => {
    if (selectedBlocks.length > 0) {
      fabricCanvasRef.current?.discardActiveObject();
      fabricCanvasRef.current?.requestRenderAll();
      await deleteCanvasBlocks(selectedBlocks.map(b => b.id));
    } else if (selectedBlock) {
      fabricCanvasRef.current?.discardActiveObject();
      fabricCanvasRef.current?.requestRenderAll();
      await deleteCanvasBlocks([selectedBlock.id]);
    }
  };

  const pageId = activePage?.id;
  const projId = activePage?.project_id;
  const hasInpaintAsset = Boolean(activePage?.inpainted_image_path);
  const useClean = showInpainted && hasInpaintAsset && !cleanImageUnavailable;
  const previewUrl = pageId && projId
    ? useClean
      ? `/api/pages/${pageId}/image?clean=true&v=${cleanImageVersion}-${cleanPreviewRevision}`
       : `/api/pages/${pageId}/preview`
    : "";

  const isSmartBalloonEnabled = getEffectiveEnableSmartBalloon(activeProject?.settings);
  const selectedBalloonResolution = selectedBlock && selectedBlocks.length === 1
    ? resolveCanvasLayoutRegion(
        selectedBlock,
        isValidCanonicalSpec(selectedBlock.extra_metadata?.typesetting_spec)
          ? selectedBlock.extra_metadata.typesetting_spec
          : undefined,
        useTypesettingLayout,
        isSmartBalloonEnabled,
      )
    : null;
  const selectedBalloonRegion = selectedBalloonResolution?.region ?? null;

  const adjustSelectedBalloonSize = async (axis: 'width' | 'height', direction: -1 | 1) => {
    if (!selectedBlock || !activePage || !selectedBalloonResolution || isBalloonSizeUpdating) return;
    const region = selectedBalloonResolution.region;
    const currentSize = axis === 'width' ? region.width : region.height;
    const delta = Math.max(4, Math.round(currentSize * 0.05));
    const pageLimit = axis === 'width' ? activePage.width : activePage.height;
    const nextSize = Math.max(8, Math.min(pageLimit || Number.MAX_SAFE_INTEGER, currentSize + direction * delta));
    const centerX = region.x + region.width / 2;
    const centerY = region.y + region.height / 2;
    const nextRegion = {
      ...region,
      x: axis === 'width' ? centerX - nextSize / 2 : region.x,
      y: axis === 'height' ? centerY - nextSize / 2 : region.y,
      width: axis === 'width' ? nextSize : region.width,
      height: axis === 'height' ? nextSize : region.height,
    };

    setIsBalloonSizeUpdating(true);
    try {
      await updateBlock(selectedBlock.id, {
        x: nextRegion.x,
        y: nextRegion.y,
        width: nextRegion.width,
        height: nextRegion.height,
        extra_metadata: {
          ...(selectedBlock.extra_metadata || {}),
          text_bbox: {
            x: nextRegion.x,
            y: nextRegion.y,
            width: nextRegion.width,
            height: nextRegion.height,
          },
          ...(selectedBalloonResolution.usesLayoutRegion ? {
            layout_region: {
              ...(selectedBlock.extra_metadata?.layout_region || {}),
              ...nextRegion,
              confidence: 1,
              source: 'manual',
              reason: 'user_adjusted',
            },
          } : {}),
        },
      });
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Failed to resize balloon', false);
    } finally {
      setIsBalloonSizeUpdating(false);
    }
  };

  // Dynamic cursor style based on modes
  const canvasCursor = isBalloonLayoutMode
    ? 'crosshair'
    : isMaskMode
    ? 'crosshair'
    : canvasMode === 'text'
      ? 'text'
    : canvasMode === 'drawBlock'
      ? 'cell'
      : 'default';

  return (
    <div className="flex flex-col flex-1 h-full select-none">
      {/* Floating Photoshop-style Mask Toolbar - pinned to viewport via portal-level fixed */}
      {isMaskMode && (
        <MaskToolbar
          activeTool={maskTool}
          setActiveTool={setMaskTool}
          brushSize={pageBrushSize}
          setBrushSize={setPageBrushSize}
          maskOpacity={pageMaskOpacity}
          setMaskOpacity={setPageMaskOpacity}
          onClear={handleClearPageMask}
          onAutoDetect={handlePageAutoMask}
          onSaveAndClean={handleSavePageMaskAndClean}
          onClose={() => setIsMaskMode(false)}
          isDetecting={isMaskDetecting}
          isSaving={isMaskSaving}
          canUndo={canMaskUndo}
          onUndo={handleUndoPageMask}
        />
      )}

      {/* Brush cursor ring is now rendered inside the canvas wrapper (overflow-hidden)
          so it auto-clips when mouse exits the canvas — see line ~3787 */}
      {/* Top Toolbar */}
      <div className="flex items-center justify-between p-3.5 border-b border-zinc-800 glass-panel">
        <div className="flex items-center gap-3">
          {/* Grouped mode selectors (Figma/Houzilocal style) */}
          <div className="flex items-center bg-zinc-950/90 p-1 rounded-md border border-zinc-900/60 gap-1 font-pixel shadow-inner">
            <button 
              onClick={() => { setCanvasMode('select'); setIsMaskMode(false); setIsBalloonLayoutMode(false); }}
              className={`flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-md transition-all duration-150 cursor-pointer border ${
                canvasMode === 'select' 
                  ? 'pixel-btn-magenta shadow-[0_2px_10px_rgba(234,179,8,0.25)] border-yellow-600' 
                  : 'pixel-btn-purple hover:text-yellow-400 hover:border-yellow-400/50'
              }`}
              title="Select / Draw Box (คลิกซ้ายเลือก/ย้าย | คลิกขวาค้างวาดกล่อง) (V / M)"
            >
              <Move size={15} />
              <span>Select & Draw</span>
            </button>

            <button
              onClick={() => { setCanvasMode('text'); setIsMaskMode(false); setIsBalloonLayoutMode(false); setShowTypesetting(true); }}
              className={`flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-md transition-all duration-150 cursor-pointer border ${
                canvasMode === 'text'
                  ? 'bg-cyan-500 text-black border-cyan-300 shadow-[0_2px_10px_rgba(34,211,238,0.25)]'
                  : 'pixel-btn-purple hover:text-cyan-300 hover:border-cyan-500/50'
              }`}
              title="Text Tool — กด T แล้วคลิกข้อความเพื่อแก้ไขบรรทัด"
            >
              <Type size={15} />
              <span>Text</span>
            </button>

            <button
              type="button"
              onClick={toggleBalloonLayoutMode}
              disabled={isBalloonSegmenting}
              aria-label={isBalloonLayoutMode ? 'Close Balloon Layout' : 'Open Balloon Layout'}
              className={`size-8 flex items-center justify-center rounded-md transition-colors duration-150 cursor-pointer border ${
                isBalloonLayoutMode
                  ? 'bg-emerald-400 text-zinc-950 border-emerald-300'
                  : 'bg-zinc-900 text-slate-400 border-zinc-800 hover:text-emerald-300 hover:border-emerald-500/50'
              } ${isBalloonSegmenting ? 'opacity-60 cursor-wait' : ''}`}
              title="Balloon Layout: เลือก text layer แล้วลากกรอบครอบบอลลูน"
            >
              <ScanLine size={15} />
            </button>

            <button 
              onClick={() => {
                if (onRunOCR) {
                  const targetIds = selectedBlocks.map(b => b.id);
                  onRunOCR(targetIds);
                }
              }}
              className="flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-md transition-all duration-150 cursor-pointer pixel-btn-purple hover:text-yellow-400 hover:border-yellow-400/50"
              title="Run OCR (สแกนและแปลภาษานี้)"
            >
              <ScanText size={15} className="text-yellow-500" />
              <span>OCR</span>
            </button>

            <button 
              onClick={() => {
                if (onRunInpaintPreview) onRunInpaintPreview();
              }}
              className="flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-md transition-all duration-150 cursor-pointer pixel-btn-purple hover:text-yellow-400 hover:border-yellow-400/50"
              title="Preview Inpaint (ดูผลลัพธ์การลบอักษรก่อนบันทึก)"
            >
              <Sparkles size={15} className="text-yellow-500 animate-pulse" />
              <span>Preview Inpaint</span>
            </button>

            <button
              type="button"
              disabled={!selectedBlock && selectedBlocks.length === 0}
              onClick={async () => {
                const targets = selectedBlocks.length > 0 ? selectedBlocks : selectedBlock ? [selectedBlock] : [];
                useProjectStore.getState().setStatus("⚡ คำนวณ Smart Balloon พิกเซลจริง...", true);
                for (const b of targets) {
                  try {
                    const resp = await apiFetch(`/api/pipeline/blocks/${b.id}/smart-balloon/recompute`, { method: 'POST' });
                    if (resp.ok) {
                      const data = await resp.json();
                      updateBlock(b.id, {
                        smart_x: data.smart_x,
                        smart_y: data.smart_y,
                        smart_width: data.smart_width,
                        smart_height: data.smart_height,
                        smart_mask_path: data.smart_mask_path,
                        extra_metadata: { ...(b.extra_metadata || {}), manual_font_size: null, font_size_mode: 'auto', contour_layout: true }
                      });
                    }
                  } catch (err) {
                    console.error("Smart Balloon recompute failed for block:", b.id, err);
                  }
                }
                useProjectStore.getState().setStatus("✅ คำนวณ Smart Balloon สำเร็จ!", false);
              }}
              className="flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-md transition-all duration-150 cursor-pointer border bg-emerald-500/15 border-emerald-500/40 text-emerald-300 hover:bg-emerald-500/25 hover:border-emerald-400 shadow-[0_0_10px_rgba(16,185,129,0.25)] disabled:cursor-not-allowed disabled:opacity-35"
              title="🎈 Auto-Fit Smart Balloon: คำนวณขอบและขนาดฟอนต์อัตโนมัติ 65%-75%"
            >
              <Sparkles size={14} className="text-emerald-400 animate-pulse" />
              <span>🎈 Auto-Fit Smart Balloon</span>
            </button>

            <button
              type="button"
              disabled={!selectedBlock}
              onClick={() => {
                if (selectedBlock && onOpenMaskEditor) onOpenMaskEditor(selectedBlock.id);
              }}
              className="flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-md transition-all duration-150 cursor-pointer border pixel-btn-purple hover:text-rose-300 hover:border-rose-500/50 disabled:cursor-not-allowed disabled:opacity-35"
              title={selectedBlock ? 'Open the saved Text Mask Editor (B)' : 'Select one text layer first'}
            >
              <span aria-hidden="true">🖌️</span>
              <span>Open Mask Editor</span>
            </button>

            {onRunFontJudge && (
              <button 
                type="button"
                disabled={!selectedBlock}
                onClick={onRunFontJudge}
                className="flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-md transition-all duration-150 cursor-pointer border pixel-btn-purple hover:text-yellow-400 hover:border-yellow-400/50 disabled:cursor-not-allowed disabled:opacity-35"
                title="Run Font Judge for selected block"
              >
                <span aria-hidden="true">✒️</span>
                <span>Font Judge</span>
              </button>
            )}
          </div>

          {selectedBlock && (
            <button 
              onClick={handleDeleteBox}
              className="flex items-center gap-2 px-3.5 py-2 text-xs font-bold rounded-md text-red-300 bg-red-950/20 hover:bg-red-950/40 border border-red-900/30 transition-all duration-200 font-pixel shadow-sm cursor-pointer"
              title="Delete Box (Del)"
            >
              <Trash2 size={16} /> Delete Block
            </button>
          )}
        </div>
        
        {/* Zoom & Shortcuts details */}
        <div className="flex items-center gap-2.5 bg-zinc-950/45 px-3 py-1.5 rounded-md border border-zinc-900/60 shadow-inner">
          <button 
            onClick={() => setShowShortcutsModal(true)} 
            className="p-1 rounded-md bg-zinc-900/40 text-slate-400 hover:bg-zinc-850 hover:text-amber-400 transition-all border border-zinc-850/20 cursor-pointer flex items-center justify-center"
            title="Keyboard Shortcuts Guide"
          >
            <Keyboard size={14} />
          </button>
          <div className="h-4 w-[1px] bg-zinc-800" />
          <button 
            onClick={() => handleZoom('out')} 
            className="p-1 rounded-md bg-zinc-900/40 text-slate-400 hover:bg-zinc-850 hover:text-amber-400 transition-all duration-150 border border-zinc-850/20 cursor-pointer"
            title="Zoom Out"
          >
            <ZoomOut size={14} />
          </button>
          <span className="text-xs font-extrabold text-slate-300 min-w-12 text-center tabular-nums">{Math.round(zoomLevel * 100)}%</span>
          <button 
            onClick={() => handleZoom('in')} 
            className="p-1 rounded-md bg-zinc-900/40 text-slate-400 hover:bg-zinc-850 hover:text-amber-400 transition-all duration-150 border border-zinc-850/20 cursor-pointer"
            title="Zoom In"
          >
            <ZoomIn size={14} />
          </button>
          <button 
            onClick={() => handleZoom('reset')} 
            className={`text-xs font-bold transition-all duration-150 px-1.5 py-0.5 rounded font-pixel text-[8px] cursor-pointer border ${
              isZoomAutoFit 
                ? 'text-green-400 border-green-500/20 bg-green-500/5 hover:text-green-300' 
                : 'text-slate-400 border-zinc-800 hover:text-amber-400 hover:border-yellow-400/20 bg-zinc-900/40'
            }`}
            title={isZoomAutoFit ? "กำลังเปิดใช้อยู่ (คลิกเพื่อคำนวณใหม่)" : "คลิกเพื่อปรับขนาดให้พอดีอัตโนมัติ"}
          >
            {isZoomAutoFit ? '🟢 Auto-Fit' : '⚪ Fit Screen'}
          </button>
        </div>
      </div>
 
      {/* Editor Canvas workspace */}
      <div 
        ref={workspaceRef}
        onScroll={(e) => {
          lastScrollPosRef.current = {
            scrollTop: e.currentTarget.scrollTop,
            scrollLeft: e.currentTarget.scrollLeft,
          };
        }}
        onMouseDown={(e) => {
          const isMiddleClick = e.button === 1;
          const isSpacePan = e.button === 0 && isSpacePressedRef.current;
          if (isMiddleClick || isSpacePan) {
            isPanningRef.current = true;
            panStartRef.current = {
              x: e.clientX,
              y: e.clientY,
              scrollLeft: workspaceRef.current?.scrollLeft || 0,
              scrollTop: workspaceRef.current?.scrollTop || 0,
            };
            if (workspaceRef.current) {
              workspaceRef.current.style.cursor = 'grabbing';
            }
          }
        }}
        className="flex-1 overflow-auto canvas-grid-bg p-10 flex justify-center items-start relative min-h-0"
      >
        {/* Floating Ambient Inpaint Status Pill */}
        {(isPreparingInpainted || cleanJustFinished) && (
          <div className="absolute top-6 left-1/2 -translate-x-1/2 z-50 pointer-events-none transition-all duration-300 animate-in fade-in slide-in-from-top-3">
            <div className={`flex items-center gap-2.5 px-4 py-2 rounded-full border shadow-2xl backdrop-blur-md font-sans text-xs font-semibold ${
              cleanJustFinished 
                ? 'bg-emerald-950/90 border-emerald-500/60 text-emerald-300 shadow-emerald-500/20'
                : 'bg-zinc-900/95 border-amber-500/50 text-amber-300 shadow-amber-500/15'
            }`}>
              {cleanJustFinished ? (
                <>
                  <CheckCircle2 size={15} className="text-emerald-400 animate-bounce" />
                  <span>ภาพคลีนพร้อมแสดงผลแล้ว</span>
                </>
              ) : (
                <>
                  <Loader2 size={15} className="text-amber-400 animate-spin" />
                  <span className="flex items-center gap-2">
                    <span>กำลังคลีนภาพอัตโนมัติ (AI Inpainting)...</span>
                    {activePage?.page_number && (
                      <span className="px-1.5 py-0.5 rounded bg-amber-500/15 text-[10px] text-amber-300 font-mono">
                        หน้า {activePage.page_number}
                      </span>
                    )}
                  </span>
                </>
              )}
            </div>
          </div>
        )}

        {/* Dynamic Wrapper size for standard browser scrollbar handling */}
        <div
          style={{
            width: `${imgDimensions.width * zoomLevel}px`,
            height: `${imgDimensions.height * zoomLevel}px`,
            maxWidth: 'none',
            maxHeight: 'none',
          }}
          className={`relative rounded-sm border bg-zinc-950 shadow-2xl overflow-visible shrink-0 max-w-none max-h-none transition-colors duration-150 ${
            isPreparingInpainted 
              ? 'border-amber-500/40 shadow-amber-500/10 ring-1 ring-amber-500/30' 
              : 'border-zinc-800 shadow-yellow-500/5'
          }`}
        >
          {/* soft pulse Skeleton Loader during page-switching */}
          {!isImageLoaded && (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-zinc-950/90 z-20">
              <div className="absolute inset-0 skeleton-checkered-mask opacity-25 animate-pulse" />
              <div className="flex flex-col items-center gap-3 z-10 text-center font-sans">
                <div className="relative flex items-center justify-center w-12 h-12">
                  <div className="absolute w-full h-full rounded-full border-2 border-yellow-500/10 border-t-yellow-500 animate-spin" />
                  <ImageIcon size={20} className="text-yellow-500/40 animate-pulse" />
                </div>
                <div className="flex flex-col items-center gap-0.5">
                  <span className="text-[10px] text-slate-400 font-bold tracking-widest uppercase font-pixel animate-pulse">Switching Page...</span>
                  <span className="text-[9px] text-slate-500 font-sans">loading canvas workspace</span>
                </div>
              </div>
            </div>
          )}

          {/* Native HTML <img> Tag for background rendering (Matches Houzilocal exactly!) */}
          {previewUrl && (
            <img 
              key={`${pageId}-${useClean ? 'clean' : 'original'}-${cleanImageVersion}-${cleanPreviewRevision}`}
               src={previewUrl}
               onLoad={() => {
                 setIsImageLoaded(true);
               }}
               onError={() => {
                 if (useClean) {
                   setCleanImageUnavailable(true);
                   setStatus('ภาพคลีนยังไม่ได้ถูกสร้าง (กดขั้นตอน 4. Clean เพื่อสร้าง)', false);
                 }
                 setIsImageLoaded(true);
               }}
              alt="Page background" 
              draggable={false}
              className={`absolute top-0 left-0 pointer-events-none select-none z-0 ${
                isImageLoaded ? 'opacity-100' : 'opacity-0'
              }`}
              style={{
                width: `${imgDimensions.width * zoomLevel}px`,
                height: `${imgDimensions.height * zoomLevel}px`,
                maxWidth: 'none',
                maxHeight: 'none',
              }}
            />
          )}

          {/* Transparent Fabric Canvas Layer on top */}
          <div 
            className={`absolute top-0 left-0 z-10 ${
              isImageLoaded ? 'opacity-100' : 'opacity-0'
            }`}
            style={{
              width: `${imgDimensions.width * zoomLevel}px`,
              height: `${imgDimensions.height * zoomLevel}px`,
              cursor: canvasCursor,
              maxWidth: 'none',
              maxHeight: 'none',
            }}
          >
            <canvas ref={canvasElRef} />
          </div>

          {/* Interactive Page Mask Canvas Layer when in Mask Mode */}
          <canvas
            ref={pageMaskCanvasRef}
            className="absolute top-0 left-0 transition-opacity duration-200"
            style={{
              width: `${imgDimensions.width * zoomLevel}px`,
              height: `${imgDimensions.height * zoomLevel}px`,
              opacity: isMaskMode ? pageMaskOpacity : 0,
              pointerEvents: isMaskMode ? 'auto' : 'none',
              zIndex: isMaskMode ? 40 : -1,
              cursor: isMaskMode ? (maskTool === 'box' ? 'crosshair' : 'none') : 'default',
              touchAction: 'none',
            }}
            onPointerDown={handlePageMaskPointerDown}
            onPointerMove={handlePageMaskPointerMove}
            onPointerUp={handlePageMaskPointerUp}
            onPointerCancel={handlePageMaskPointerCancel}
            onPointerLeave={handlePageMaskPointerLeave}
            onContextMenu={(event) => event.preventDefault()}
          />

          {/* Experimental balloon selector. It edits layout geometry only. */}
          <div
            className="absolute top-0 left-0"
            style={{
              width: `${imgDimensions.width * zoomLevel}px`,
              height: `${imgDimensions.height * zoomLevel}px`,
              pointerEvents: isBalloonLayoutMode ? 'auto' : 'none',
              zIndex: isBalloonLayoutMode ? 35 : -1,
              cursor: isBalloonSegmenting ? 'progress' : 'crosshair',
              touchAction: 'none',
            }}
            onPointerDown={handleBalloonPointerDown}
            onPointerMove={handleBalloonPointerMove}
            onPointerUp={(event) => void finishBalloonSelection(event)}
            onPointerCancel={() => setBalloonSelectionState(null)}
            onContextMenu={(event) => event.preventDefault()}
          >
            {balloonSelection && (
              <div
                className="absolute border-2 border-emerald-300 bg-emerald-400/10 pointer-events-none rounded-sm shadow-[0_0_15px_rgba(16,185,129,0.3)]"
                style={{
                  left: Math.min(balloonSelection.startX, balloonSelection.currentX),
                  top: Math.min(balloonSelection.startY, balloonSelection.currentY),
                  width: Math.abs(balloonSelection.currentX - balloonSelection.startX),
                  height: Math.abs(balloonSelection.currentY - balloonSelection.startY),
                }}
              >
                <div className="absolute -top-7 right-0 px-2 py-0.5 bg-emerald-950/90 border border-emerald-400 text-emerald-300 font-mono text-[10px] font-bold rounded shadow-lg whitespace-nowrap">
                  🎈 SAM Segment: {Math.round(Math.abs(balloonSelection.currentX - balloonSelection.startX) * scaleFactorRef.current)} × {Math.round(Math.abs(balloonSelection.currentY - balloonSelection.startY) * scaleFactorRef.current)} px
                </div>
              </div>
            )}
          </div>

          {/* Brush Circle Cursor — absolute inside overflow-hidden wrapper = auto-clips at edges */}
          {isMaskMode && (maskTool === 'brush' || maskTool === 'eraser') && (
            <div
              ref={pageMaskCursorRef}
              className="absolute rounded-full border-2 border-amber-400 pointer-events-none"
              style={{
                display: 'none',
                left: 0,
                top: 0,
                width: `${pageBrushSize * zoomLevel}px`,
                height: `${pageBrushSize * zoomLevel}px`,
                transform: 'translate(-50%, -50%)',
                zIndex: 45,
              }}
            />
          )}

          {/* Mask Badge Tooltip */}
          {maskTooltip && (
            <div
              className="absolute z-50 px-3 py-2 bg-zinc-900/95 border border-zinc-700 rounded-md shadow-xl text-xs text-white pointer-events-none animate-fade-in"
              style={{
                left: `${maskTooltip.x + 10}px`,
                top: `${maskTooltip.y - 10}px`,
              }}
            >
              <div className="font-bold mb-1">
                {maskTooltip.type === 'custom' ? '✏️ Custom Mask' : '🤖 Adaptive Mask'}
              </div>
              <div className="text-zinc-400 text-[10px]">
                {maskTooltip.type === 'custom'
                  ? 'User-drawn mask (highest accuracy)'
                  : 'Auto-generated with balloon detection'}
              </div>
            </div>
          )}

          {/* Floating Lettering Bar for fast styling directly above active textbox */}
          {showFloatingLetteringBar && selectedBlock && selectedBlocks.length === 1 && !isMaskMode && showTypesetting && (
            <FloatingLetteringBar
              blockId={selectedBlock.id}
              canvasScale={zoomLevel / scaleFactor}
              blockX={selectedBlock.x}
              blockY={selectedBlock.y}
              blockWidth={selectedBlock.width}
              blockHeight={selectedBlock.height}
              onClose={onCloseFloatingLetteringBar}
              onAutoFit={(id) => {
                const tb = fabricCanvasRef.current?.getObjects().find((obj: any) => obj.data?.blockId === id) as fabric.Textbox;
                if (tb) {
                  removeExplicitLineAdapter(tb);
                  autoFitTextboxFontSize(tb, fabricCanvasRef.current, scaleFactorRef.current, false);
                }
              }}
              onDuplicate={async (id) => {
                const target = activePage?.text_blocks.find((b) => b.id === id);
                if (target && activePage) {
                  await createBlock(activePage.id, {
                    x: target.x + 20,
                    y: target.y + 20,
                    width: target.width,
                    height: target.height,
                    source_text: target.source_text,
                    translation: target.translation,
                    font_family: target.font_family,
                    font_size: target.font_size,
                    color_hex: target.color_hex,
                    bold: target.bold,
                    italic: target.italic,
                    text_align: target.text_align,
                    text_direction: target.text_direction,
                    balloon_type: target.balloon_type,
                    extra_metadata: { ...target.extra_metadata },
                  });
                  setStatus('Duplicated block', false);
                }
              }}
              onDelete={async (id) => {
                await deleteBlocks([id]);
                setStatus('Deleted block', false);
              }}
            />
          )}
        </div>

        <CanvasAlignmentToolbar
          selectedBlockIds={selectedBlocks.map((b) => b.id)}
          onClearSelection={() => useProjectStore.setState({ selectedBlock: null, selectedBlocks: [] })}
        />

        {contextMenu && (
          <CanvasContextMenu
            x={contextMenu.x}
            y={contextMenu.y}
            blockId={contextMenu.blockId || selectedBlock?.id || null}
            selectedBlockIds={selectedBlocks.map((b) => b.id)}
            onClose={() => setContextMenu(null)}
            onRunOCR={(id) => onRunOCR?.([id])}
            onCleanMask={(id) => onOpenMaskEditor?.(id)}
            onAutoFitFont={(id) => {
              const b = activePage?.text_blocks.find((x) => x.id === id);
              if (b) {
                const text = b.translation || b.source_text || '';
                const area = b.width * b.height;
                const charCount = Math.max(1, text.length);
                const estSize = Math.max(10, Math.min(72, Math.round(Math.sqrt(area / (charCount * 1.6)))));
                updateBlock(b.id, { font_size: estSize });
              }
            }}
            onDeleteBlock={(id) => deleteCanvasBlocks([id])}
            onDeleteAndInpaint={(id) => useProjectStore.getState().deleteAndInpaintBlock(id)}
            onMakeSplit={(id, dir) => useProjectStore.getState().splitBlock(id, dir)}
            onCopyStyle={(id) => useProjectStore.getState().copyBlockStyle(id)}
            onPasteStyle={(id) => useProjectStore.getState().pasteBlockStyle(id)}
            hasCopiedStyle={!!useProjectStore.getState().copiedStyle}
            onExtractStyle={async (id) => {
              const b = activePage?.text_blocks.find((x) => x.id === id);
              if (b && activePage) {
                try {
                  const res = await apiFetch('/pipeline/extract-style', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                      page_id: activePage.id,
                      bbox: [Math.round(b.x), Math.round(b.y), Math.round(b.width), Math.round(b.height)],
                      block_id: b.id,
                    }),
                  });
                  if (res.ok) {
                    const data = await res.json();
                    if (data.style) {
                      updateBlock(b.id, {
                        color_hex: data.style.text_color,
                        font_color: data.style.text_color,
                        stroke_color: data.style.stroke_color || b.stroke_color,
                        stroke_width: data.style.stroke_width || b.stroke_width,
                      });
                    }
                  }
                } catch (e) {
                  console.error('Extract style failed:', e);
                }
              }
            }}
            onMergeBlocks={(ids) => {
              if (activePage) useProjectStore.getState().mergeBlocks(activePage.id, ids);
            }}
            onEqualizeSize={(ids, dim) => {
              if (!activePage) return;
              const blks = activePage.text_blocks.filter((b) => ids.includes(b.id));
              if (blks.length < 2) return;
              const target = dim === 'width' ? blks[0].width : blks[0].height;
              blks.slice(1).forEach((b) => {
                updateBlock(b.id, { [dim]: target });
              });
            }}
            onSortReadingOrder={(ids) => {
              if (!activePage) return;
              const blks = [...activePage.text_blocks.filter((b) => ids.includes(b.id))];
              blks.sort((a, b) => (a.y === b.y ? b.x - a.x : a.y - b.y));
              useProjectStore.setState({ selectedBlocks: blks });
            }}
            isVisible={
              contextMenu.blockId
                ? activePage?.text_blocks.find((b) => b.id === contextMenu.blockId)?.is_visible !== false
                : selectedBlock?.is_visible !== false
            }
            isLocked={
              contextMenu.blockId
                ? activePage?.text_blocks.find((b) => b.id === contextMenu.blockId)?.is_locked === true
                : selectedBlock?.is_locked === true
            }
            onToggleVisibility={(id) => {
              const b = activePage?.text_blocks.find((x) => x.id === id);
              if (b) {
                const nextVis = b.is_visible === false ? true : false;
                updateBlock(b.id, { is_visible: nextVis, extra_metadata: { ...b.extra_metadata, is_visible: nextVis } });
              }
            }}
            onToggleLock={(id) => {
              const b = activePage?.text_blocks.find((x) => x.id === id);
              if (b) {
                const nextLock = b.is_locked ? false : true;
                updateBlock(b.id, { is_locked: nextLock, extra_metadata: { ...b.extra_metadata, is_locked: nextLock } });
              }
            }}
            onReorderZIndex={(id, action) => {
              if (activePage) useProjectStore.getState().reorderBlockZIndex(activePage.id, id, action);
            }}
            onRefreshPage={() => void onRefreshPage?.()}
            onRefitPageText={() => void onRefitPageText?.()}
            onResetPageMasks={() => void onResetPageMasks?.()}
            onResetProjectMasks={() => void onResetProjectMasks?.()}
          />
        )}

        {/* Figma-style Keyboard Shortcut Overlay */}
        {shortcutsOverlayCollapsed ? (
          <button
            onClick={() => setShortcutsOverlayCollapsed(false)}
            className="absolute bottom-4 left-4 p-2 rounded-full border border-zinc-800 bg-zinc-950/90 shadow-2xl hover:border-amber-400/40 text-slate-400 hover:text-yellow-400 transition-all z-20 flex items-center justify-center cursor-pointer animate-fade-in"
            title="แสดงปุ่มลัดคีย์บอร์ด (Show Keyboard Shortcuts)"
          >
            <Keyboard size={14} />
          </button>
        ) : (
          <div className="absolute bottom-4 left-4 p-4 rounded-sm border border-zinc-800 bg-zinc-950/90 shadow-2xl max-w-[240px] z-20 transition-all duration-300 hover:border-amber-400/40 animate-fade-in">
            <div className="flex justify-between items-center mb-1.5">
              <h4 className="text-[10px] font-bold text-amber-400 uppercase tracking-widest flex items-center gap-1.5 font-pixel">
                <Sparkles size={12} className="text-yellow-400 animate-pulse" /> Keyboard Shortcuts
              </h4>
              <button
                onClick={() => setShortcutsOverlayCollapsed(true)}
                className="text-slate-500 hover:text-slate-300 transition-colors p-0.5 rounded cursor-pointer flex items-center justify-center"
                title="ซ่อนปุ่มลัด (Hide)"
              >
                <X size={10} />
              </button>
            </div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 mt-1.5 font-semibold text-[11px] font-sans">
              <div className="flex items-center gap-1.5 text-slate-300">
                <kbd className="px-1.5 py-0.5 rounded-sm bg-zinc-900 border border-zinc-800 text-[10px] font-mono text-slate-400 shadow">V / M</kbd>
                <span>Select & Draw</span>
              </div>
              <div className="flex items-center gap-1.5 text-slate-300">
                <kbd className="px-1.5 py-0.5 rounded-sm bg-zinc-900 border border-zinc-800 text-[10px] font-mono text-slate-400 shadow">B</kbd>
                <span>Open Mask Editor</span>
              </div>
              <div className="flex items-center gap-1.5 text-slate-300">
                <kbd className="px-1.5 py-0.5 rounded-sm bg-zinc-900 border border-zinc-800 text-[10px] font-mono text-slate-400 shadow">Right Drag</kbd>
                <span>Draw Box</span>
              </div>
              <div className="flex items-center gap-1.5 text-slate-300">
                <kbd className="px-1.5 py-0.5 rounded-sm bg-zinc-900 border border-zinc-800 text-[10px] font-mono text-slate-400 shadow">Del</kbd>
                <span>Delete Block</span>
              </div>
              <div className="col-span-2 flex items-center gap-1.5 text-slate-300 mt-1">
                <kbd className="px-1.5 py-0.5 rounded-sm bg-zinc-900 border border-zinc-800 text-[10px] font-mono text-slate-400 shadow">Space + Drag</kbd>
                <span>Pan Canvas</span>
              </div>
              <div className="col-span-2 flex items-center gap-1.5 text-slate-300 mt-1 border-t border-zinc-900 pt-1">
                <kbd className="px-1.5 py-0.5 rounded-sm bg-zinc-900 border border-zinc-800 text-[10px] font-mono text-slate-400 shadow">Ctrl + Shift + S</kbd>
                <span>Export OCR TXT</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Bottom Control Bar (Figma / Manga Studio Style) */}
      <div className="flex flex-wrap items-center justify-between gap-2 p-2 border-t border-zinc-900 bg-zinc-950 font-pixel text-[10px] select-none shrink-0 z-10 min-h-[44px]">
        <div className="flex items-center flex-wrap gap-2 text-slate-400 min-w-0">
          {/* Zoom Spinner Input */}
          <div className="flex items-center bg-zinc-900 border border-zinc-800 rounded-sm px-1.5 py-0.5 shrink-0">
            <input 
              type="number" 
              value={Math.round(zoomLevel * 100)}
              onChange={(e) => {
                const val = parseInt(e.target.value);
                if (!isNaN(val)) {
                  let nz = val / 100;
                  if (nz > 6.0) nz = 6.0;
                  if (nz < 0.05) nz = 0.05;
                  setZoomLevel(nz);
                }
              }}
              className="w-9 bg-transparent text-center text-slate-200 border-none outline-none font-bold font-mono focus:ring-0 text-[10px] p-0"
            />
            <span className="text-[9px] text-slate-500 font-extrabold ml-0.5">%</span>
          </div>

          {selectedBalloonRegion && (
            <div
              className="flex h-7 items-center overflow-hidden rounded border border-zinc-800 bg-zinc-900 text-[10px] text-slate-300"
              aria-label="Balloon size"
            >
              <div className="flex h-full items-center border-r border-zinc-800 px-1.5" title="Balloon size">
                <Maximize2 size={12} className="text-emerald-400" />
              </div>
              <span className="w-10 text-center font-mono tabular-nums" title="Width">
                W {Math.round(selectedBalloonRegion.width)}
              </span>
              <button
                type="button"
                className="size-6 flex items-center justify-center border-l border-zinc-800 hover:bg-zinc-800 hover:text-white disabled:opacity-40"
                onClick={() => void adjustSelectedBalloonSize('width', -1)}
                disabled={isBalloonSizeUpdating}
                aria-label="Decrease balloon width"
                title="Decrease width"
              >
                <Minus size={11} />
              </button>
              <button
                type="button"
                className="size-6 flex items-center justify-center border-l border-zinc-800 hover:bg-zinc-800 hover:text-white disabled:opacity-40"
                onClick={() => void adjustSelectedBalloonSize('width', 1)}
                disabled={isBalloonSizeUpdating}
                aria-label="Increase balloon width"
                title="Increase width"
              >
                <Plus size={11} />
              </button>
              <span className="w-10 border-l border-zinc-800 text-center font-mono tabular-nums" title="Height">
                H {Math.round(selectedBalloonRegion.height)}
              </span>
              <button
                type="button"
                className="size-6 flex items-center justify-center border-l border-zinc-800 hover:bg-zinc-800 hover:text-white disabled:opacity-40"
                onClick={() => void adjustSelectedBalloonSize('height', -1)}
                disabled={isBalloonSizeUpdating}
                aria-label="Decrease balloon height"
                title="Decrease height"
              >
                <Minus size={11} />
              </button>
              <button
                type="button"
                className="size-6 flex items-center justify-center border-l border-zinc-800 hover:bg-zinc-800 hover:text-white disabled:opacity-40"
                onClick={() => void adjustSelectedBalloonSize('height', 1)}
                disabled={isBalloonSizeUpdating}
                aria-label="Increase balloon height"
                title="Increase height"
              >
                <Plus size={11} />
              </button>
            </div>
          )}

          {/* Checkbox: Translated */}
          <label className="flex items-center gap-1.5 cursor-pointer hover:text-yellow-400 transition-colors py-0.5 text-[10px] whitespace-nowrap shrink-0">
            <input 
              type="checkbox"
              checked={showTranslated}
              onChange={(e) => setShowTranslated(e.target.checked)}
              className="w-3.5 h-3.5 rounded-sm border-zinc-800 bg-zinc-900 text-yellow-500 focus:ring-yellow-500 accent-yellow-500 cursor-pointer"
            />
            <span>Translated</span>
          </label>

          {/* Checkbox: แสดงภาพคลีน (Clean Image) */}
          <label className="flex items-center gap-1.5 cursor-pointer hover:text-yellow-400 transition-colors py-0.5 text-[10px] whitespace-nowrap shrink-0" title="แสดงภาพที่คลีนลบตัวอักษรแล้ว (หากยังไม่เคยคลีนจะสั่งคลีนทันที)">
            <input 
              type="checkbox"
              checked={showInpainted}
              disabled={isPreparingInpainted}
              onChange={(e) => void handleCleanImageToggle(e.target.checked)}
              className="w-3.5 h-3.5 rounded-sm border-zinc-800 bg-zinc-900 text-yellow-500 focus:ring-yellow-500 accent-yellow-500 cursor-pointer"
            />
            <span>{isPreparingInpainted ? 'กำลังคลีนภาพ…' : 'แสดงภาพคลีน'}</span>
          </label>

          {/* Checkbox: Typesetting mode */}
          <label className="flex items-center gap-1.5 cursor-pointer hover:text-yellow-400 transition-colors py-0.5 text-[10px] whitespace-nowrap shrink-0">
            <input 
              type="checkbox"
              checked={showTypesetting}
              onChange={(e) => setShowTypesetting(e.target.checked)}
              className="w-3.5 h-3.5 rounded-sm border-zinc-800 bg-zinc-900 text-yellow-500 focus:ring-yellow-500 accent-yellow-500 cursor-pointer"
            />
            <span>Typesetting mode</span>
          </label>

          {/* Checkbox: Mask mode */}
          <label className={`flex items-center gap-1.5 cursor-pointer transition-colors py-0.5 px-2 rounded text-[10px] whitespace-nowrap shrink-0 font-medium ${
            isMaskMode ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40 font-semibold shadow-sm' : 'hover:text-yellow-400'
          }`}>
            <input 
              type="checkbox"
              checked={isMaskMode}
              onChange={(e) => {
                setIsMaskMode(e.target.checked);
                if (e.target.checked) setIsBalloonLayoutMode(false);
              }}
              className="w-3.5 h-3.5 rounded-sm border-zinc-800 bg-zinc-900 text-amber-500 focus:ring-amber-500 accent-amber-500 cursor-pointer"
            />
            <span>Mask mode</span>
          </label>

          {/* Mask Opacity & Visibility Controls */}
          <div className="flex items-center gap-1.5 px-1.5 py-0.5 bg-zinc-900 border border-zinc-800 rounded-sm shrink-0">
            <button
              type="button"
              onClick={() => setMaskVisible(v => !v)}
              className={`p-0.5 rounded transition-colors cursor-pointer ${maskVisible ? 'text-yellow-400 hover:bg-zinc-800' : 'text-slate-500 hover:bg-zinc-800'}`}
              title={maskVisible ? 'Hide Mask Overlay' : 'Show Mask Overlay'}
            >
              {maskVisible ? <Eye size={13} /> : <EyeOff size={13} />}
            </button>
            <span className="text-[9px] text-slate-400 font-bold font-mono min-w-6 text-center">
              {Math.round(maskOpacity * 100)}%
            </span>
            <input
              type="range"
              min="0"
              max="100"
              value={Math.round(maskOpacity * 100)}
              onChange={(e) => setMaskOpacity(Number(e.target.value) / 100)}
              title="Mask Opacity"
              className="w-12 accent-yellow-500 cursor-pointer h-1 bg-zinc-950 rounded appearance-none"
            />
          </div>
        </div>

        {/* Sleek Page Navigation Control with Mouse Wheel Scrolling & Dropdown Selector */}
        {showBottomPageNavigator && activePage && activeProject && activeProject.pages.length > 1 && (
          <div 
            className="flex items-center gap-1.5 select-none px-2 py-0.5 bg-zinc-900/90 backdrop-blur-md border border-zinc-800/80 rounded-xl shadow-xl hover:border-amber-500/30 transition-all duration-200 shrink-0 z-20 my-0.5"
            onWheel={(e) => {
              e.preventDefault();
              const pages = activeProject.pages;
              const currentIdx = pages.findIndex(p => p.id === activePage.id);
              if (e.deltaY > 0 && currentIdx < pages.length - 1) {
                selectPage(pages[currentIdx + 1].id);
              } else if (e.deltaY < 0 && currentIdx > 0) {
                selectPage(pages[currentIdx - 1].id);
              }
            }}
            title="หมุนลูกกลิ้งเมาส์ (Mouse Wheel) ตรงนี้เพื่อสลับหน้าถัดไป/ก่อนหน้าได้ทันที"
          >
            {/* Previous page button */}
            <button
              onClick={() => {
                const pages = activeProject.pages;
                const currentIdx = pages.findIndex(p => p.id === activePage.id);
                if (currentIdx > 0) selectPage(pages[currentIdx - 1].id);
              }}
              disabled={activeProject.pages.findIndex(p => p.id === activePage.id) === 0}
              className="w-7 h-7 flex items-center justify-center rounded-lg bg-zinc-850 border border-zinc-700 text-slate-300 hover:text-amber-400 hover:bg-amber-500/20 hover:border-amber-500/40 active:scale-95 transition-all disabled:opacity-20 disabled:pointer-events-none cursor-pointer text-xs shadow-sm shrink-0"
              title="หน้าก่อนหน้า (Previous Page) — หรือใช้วีลเมาส์เลื่อนขึ้น"
            >
              <ChevronLeft size={14} />
            </button>

            {/* Page dots / pills */}
            <div className="flex items-center gap-1 max-w-[140px] sm:max-w-[220px] overflow-x-auto scrollbar-none px-1 py-0.5">
              {activeProject.pages.map((page) => {
                const isActive = page.id === activePage.id;
                return (
                  <button
                    key={page.id}
                    onClick={() => selectPage(page.id)}
                    className={`shrink-0 transition-all duration-200 cursor-pointer p-1 rounded-md flex items-center justify-center hover:bg-zinc-800 ${
                      isActive ? 'scale-110' : ''
                    }`}
                    title={`หน้า ${page.page_number}${page.name ? ` — ${page.name}` : ''}`}
                  >
                    <div
                      className={`transition-all duration-200 ${
                        isActive
                          ? 'w-5 h-2 rounded-full bg-amber-400 shadow-[0_0_8px_rgba(245,158,11,0.6)] ring-1 ring-amber-300'
                          : 'w-2 h-2 rounded-full bg-zinc-600 hover:bg-amber-400/80 hover:scale-125'
                      }`}
                    />
                  </button>
                );
              })}
            </div>

            {/* Next page button */}
            <button
              onClick={() => {
                const pages = activeProject.pages;
                const currentIdx = pages.findIndex(p => p.id === activePage.id);
                if (currentIdx < pages.length - 1) selectPage(pages[currentIdx + 1].id);
              }}
              disabled={activeProject.pages.findIndex(p => p.id === activePage.id) === activeProject.pages.length - 1}
              className="w-7 h-7 flex items-center justify-center rounded-lg bg-zinc-850 border border-zinc-700 text-slate-300 hover:text-amber-400 hover:bg-amber-500/20 hover:border-amber-500/40 active:scale-95 transition-all disabled:opacity-20 disabled:pointer-events-none cursor-pointer text-xs shadow-sm shrink-0"
              title="หน้าถัดไป (Next Page) — หรือใช้วีลเมาส์เลื่อนลง"
            >
              <ChevronRight size={14} />
            </button>

            {/* Interactive Page Dropdown & Wheel Picker */}
            <div className="flex items-center gap-1 pl-1 border-l border-zinc-800 shrink-0">
              <select
                value={activePage.id}
                onChange={(e) => selectPage(e.target.value)}
                className="px-2 py-1 bg-zinc-950 hover:bg-zinc-900 border border-zinc-800 focus:border-amber-500/60 rounded-md text-[11px] font-bold text-amber-400 cursor-pointer focus:outline-none transition-colors font-mono shadow-inner"
                title="คลิกเพื่อเลือกเลขหน้า หรือใช้ลูกกลิ้งเมาส์เลื่อนเพื่อเปลี่ยนหน้า"
              >
                {activeProject.pages.map((p) => (
                  <option key={p.id} value={p.id} className="bg-slate-900 text-slate-200 font-sans">
                    หน้า {p.page_number} / {activeProject.pages.length} {p.name ? `(${p.name})` : ''}
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}

        {/* Right side page info (filename) */}
        {activePage && (
          <div className="text-slate-500 font-pixel text-[9px] uppercase tracking-wider shrink-0 hidden lg:block">
            {activePage.name || `Page ${activePage.page_number}`}
          </div>
        )}
      </div>

      {/* Keyboard Shortcuts Glassy Modal */}
      {showShortcutsModal && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-filter backdrop-blur-sm flex items-center justify-center z-[99999] animate-fade-in">
          <div className="w-[450px] p-6 rounded-2xl border border-white/10 glass-panel-heavy shadow-2xl relative overflow-hidden text-slate-200 font-sans animate-slide-up">
            <div className="absolute top-[-30%] left-[-30%] w-[60%] h-[60%] bg-yellow-500/5 rounded-full filter blur-[40px] pointer-events-none" />
            
            <h3 className="text-base font-extrabold text-white mb-4.5 flex items-center gap-2 font-pixel">
              <Keyboard size={18} className="text-yellow-500" /> Keyboard Shortcuts Guide
            </h3>
            
            <div className="flex flex-col gap-4 max-h-[350px] overflow-y-auto pr-1">
              <div className="grid grid-cols-1 gap-4 font-medium text-xs">
                <div className="flex flex-col gap-2">
                  <span className="text-[9px] font-bold text-yellow-500 uppercase tracking-widest font-pixel">Workspace Navigation</span>
                  <div className="flex flex-col gap-1.5 pl-1">
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400">Pan canvas view</span>
                      <kbd className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-[10px] font-mono text-slate-300 shadow">Space + Drag</kbd>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400">Zoom in / out</span>
                      <kbd className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-[10px] font-mono text-slate-300 shadow">Ctrl + Scroll</kbd>
                    </div>
                  </div>
                </div>

                <div className="flex flex-col gap-2 border-t border-zinc-900 pt-3">
                  <span className="text-[9px] font-bold text-yellow-500 uppercase tracking-widest font-pixel">Canvas Modes</span>
                  <div className="flex flex-col gap-1.5 pl-1">
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400">Select & Draw Mode</span>
                      <kbd className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-[10px] font-mono text-slate-300 shadow">V / M</kbd>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400">Draw Box (Right Click Drag)</span>
                      <kbd className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-[10px] font-mono text-slate-300 shadow">Right Drag</kbd>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400">Open Mask Editor for selected layer</span>
                      <kbd className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-[10px] font-mono text-slate-300 shadow">B</kbd>
                    </div>
                  </div>
                </div>

                <div className="flex flex-col gap-2 border-t border-zinc-900 pt-3">
                  <span className="text-[9px] font-bold text-yellow-500 uppercase tracking-widest font-pixel">Block Operations</span>
                  <div className="flex flex-col gap-1.5 pl-1">
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400">Cycle to next block</span>
                      <kbd className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-[10px] font-mono text-slate-300 shadow">Tab</kbd>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400">Cycle to previous block</span>
                      <kbd className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-[10px] font-mono text-slate-300 shadow">Shift + Tab</kbd>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400">Delete active block</span>
                      <kbd className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-[10px] font-mono text-slate-300 shadow">Del</kbd>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400">Deselect active block</span>
                      <kbd className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-[10px] font-mono text-slate-300 shadow">Esc</kbd>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400">Nudge block (1px)</span>
                      <kbd className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-[10px] font-mono text-slate-300 shadow">Arrows</kbd>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400">Nudge block (10px)</span>
                      <kbd className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-[10px] font-mono text-slate-300 shadow">Shift + Arrows</kbd>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400">Copy styling style</span>
                      <kbd className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-[10px] font-mono text-slate-300 shadow">Ctrl + C</kbd>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400">Paste styling style</span>
                      <kbd className="px-1.5 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-[10px] font-mono text-slate-300 shadow">Ctrl + V</kbd>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            
            <div className="flex justify-end border-t border-zinc-900 pt-4.5 mt-4.5 shrink-0 font-pixel">
              <button 
                onClick={() => setShowShortcutsModal(false)}
                className="px-4.5 py-2 text-xs font-bold rounded-sm bg-zinc-900 border border-zinc-800 text-slate-300 hover:bg-zinc-850 hover:text-amber-400 transition-all cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
      {showFindModal && (
        <div className="absolute top-16 right-4 z-40 w-72 p-3.5 rounded-sm border border-zinc-800 bg-zinc-950 shadow-2xl glass-panel-heavy font-sans flex flex-col gap-2 animate-slide-up">
          <div className="flex justify-between items-center">
            <h4 className="text-[10px] font-bold text-amber-400 uppercase tracking-widest flex items-center gap-1.5 font-pixel">
              🔍 Find Balloon (ค้นหากล่อง)
            </h4>
            <button
              type="button"
              onClick={() => {
                setShowFindModal(false);
                workspaceRef.current?.focus();
              }}
              className="text-[9px] text-slate-500 hover:text-slate-300 font-sans cursor-pointer font-bold"
            >
              Close (Esc)
            </button>
          </div>
          <div className="relative">
            <input
              ref={findInputRef}
              type="text"
              placeholder="พิมพ์ข้อความ OCR หรือคำแปลเพื่อค้นหาทุกหน้า..."
              value={findText}
              onChange={(e) => {
                const query = e.target.value;
                setFindText(query);
                
                if (query.trim() && activeProject && activePage) {
                  const matches = activeProject.pages.flatMap(page => 
                    (page.text_blocks || [])
                      .filter(b => 
                        (b.source_text && b.source_text.toLowerCase().includes(query.toLowerCase())) ||
                        (b.translation && b.translation.toLowerCase().includes(query.toLowerCase()))
                      )
                      .map(block => ({
                        pageId: page.id,
                        pageNumber: page.page_number,
                        pageName: page.name || `Page ${page.page_number}`,
                        block
                      }))
                  );
                  
                  if (matches.length > 0) {
                    const currentPageMatchIdx = matches.findIndex(m => m.pageId === activePage.id);
                    if (currentPageMatchIdx !== -1) {
                      setFindIndex(currentPageMatchIdx);
                      warpToBlock(matches[currentPageMatchIdx].block);
                    } else {
                      setFindIndex(0);
                    }
                  } else {
                    setFindIndex(0);
                  }
                } else {
                  setFindIndex(0);
                }
              }}
              onKeyDown={handleFindKeyDown}
              className="w-full px-3 py-2 text-xs rounded-sm text-slate-250 bg-zinc-900 border border-zinc-850 focus:outline-none focus:border-yellow-500/50 transition-all placeholder-slate-650 font-sans"
              title="พิมพ์ข้อความที่ต้องการหาครอบคลุมทุกหน้าในโปรเจกต์"
            />
            {findText.trim() && (
              <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[9px] text-slate-500 font-mono">
                {matchingBlocks.length > 0 
                  ? `${findIndex + 1}/${matchingBlocks.length} (หน้า ${matchingBlocks[findIndex]?.pageNumber || ''})` 
                  : '0/0'}
              </span>
            )}
          </div>
          {matchingBlocks.length > 0 && (
            <div className="flex justify-between items-center mt-1">
              <span className="text-[8px] text-slate-500 font-sans">กด Enter เพื่อวาร์ปไปฟองถัดไป</span>
              <div className="flex gap-1.5">
                <button
                  type="button"
                  onClick={() => navigateFind('prev')}
                  className="px-2 py-1 bg-zinc-900 border border-zinc-850 text-[10px] text-slate-400 hover:bg-zinc-850 hover:text-yellow-400 rounded-sm cursor-pointer transition-colors"
                >
                  ◀ Prev
                </button>
                <button
                  type="button"
                  onClick={() => navigateFind('next')}
                  className="px-2 py-1 bg-zinc-900 border border-zinc-850 text-[10px] text-slate-400 hover:bg-zinc-850 hover:text-yellow-400 rounded-sm cursor-pointer transition-colors"
                >
                  Next ▶
                </button>
              </div>
            </div>
          )}
          {findText.trim() && matchingBlocks.length === 0 && (
            <div className="text-center py-2.5 text-slate-500 font-sans text-[10px]">
              ไม่พบคำค้นหาในโปรเจกต์นี้
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default Canvas;
