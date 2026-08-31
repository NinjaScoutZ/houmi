import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import { generateAutomaticPageMask, loadEffectivePageMask, saveEffectivePageMask } from '../api/pageMask';
import {
  drawMaskSegment,
  initializeEmptyMaskCanvas,
  pointerToCanvasPoint,
  renderMaskDataUrl,
  shouldEraseMask,
  type CanvasPoint,
  type PageMaskTool,
} from '../utils/pageMaskCanvas';

const MAX_HISTORY_BYTES = 64 * 1024 * 1024;
type MaskHistoryEntry =
  | { kind: 'empty' }
  | { kind: 'overlay'; dataUrl: string }
  | { kind: 'pixels'; imageData: ImageData };

function trimMaskHistory(history: MaskHistoryEntry[]): void {
  const entryBytes = (entry: MaskHistoryEntry) => {
    if (entry.kind === 'pixels') return entry.imageData.data.byteLength;
    if (entry.kind === 'overlay') return entry.dataUrl.length * 2;
    return 0;
  };
  let totalBytes = history.reduce((total, entry) => total + entryBytes(entry), 0);
  while (history.length > 1 && totalBytes > MAX_HISTORY_BYTES) {
    totalBytes -= entryBytes(history.shift()!);
  }
}

interface PageMaskEditorOptions {
  pageId?: string;
  imageDimensions: { width: number; height: number };
  onStatus: (message: string, isLoading: boolean) => void;
  onSaved?: () => void | Promise<void>;
}

export function usePageMaskEditor({ pageId, imageDimensions, onStatus, onSaved }: PageMaskEditorOptions) {
  const [isActive, setIsActive] = useState(false);
  const [tool, setTool] = useState<PageMaskTool>('brush');
  const [brushSize, setBrushSize] = useState(24);
  const [opacity, setOpacity] = useState(0.65);
  const [isDetecting, setIsDetecting] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [canUndo, setCanUndo] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const cursorRef = useRef<HTMLDivElement | null>(null);
  const historyRef = useRef<MaskHistoryEntry[]>([]);
  const drawingRef = useRef(false);
  const drawStartRef = useRef<CanvasPoint | null>(null);
  const previousPointRef = useRef<CanvasPoint | null>(null);
  const eraseGestureRef = useRef(false);
  const maskContextRef = useRef<CanvasRenderingContext2D | null>(null);
  const pendingStrokePointsRef = useRef<CanvasPoint[]>([]);
  const strokeFrameRef = useRef<number | null>(null);
  const requestVersionRef = useRef(0);

  const resetHistory = useCallback(() => {
    const canvas = canvasRef.current;
    const context = maskContextRef.current || canvas?.getContext('2d', { willReadFrequently: true });
    if (canvas && context) {
      maskContextRef.current = context;
      historyRef.current = [{ kind: 'pixels', imageData: context.getImageData(0, 0, canvas.width, canvas.height) }];
    } else {
      historyRef.current = [{ kind: 'empty' }];
    }
    setCanUndo(false);
  }, []);

  const appendCurrentHistory = useCallback(() => {
    const canvas = canvasRef.current;
    const context = maskContextRef.current || canvas?.getContext('2d', { willReadFrequently: true });
    if (!canvas || !context) return;
    maskContextRef.current = context;
    historyRef.current.push({ kind: 'pixels', imageData: context.getImageData(0, 0, canvas.width, canvas.height) });
    trimMaskHistory(historyRef.current);
    setCanUndo(historyRef.current.length > 1);
  }, []);

  const commitHistory = useCallback(() => {
    const canvas = canvasRef.current;
    const context = maskContextRef.current || canvas?.getContext('2d', { willReadFrequently: true });
    if (!canvas || !context) return;
    maskContextRef.current = context;
    const snapshot = context.getImageData(0, 0, canvas.width, canvas.height);
    historyRef.current.push({ kind: 'pixels', imageData: snapshot });
    trimMaskHistory(historyRef.current);
    setCanUndo(historyRef.current.length > 1);
  }, []);

  const flushStrokePoints = useCallback(() => {
    strokeFrameRef.current = null;
    const canvas = canvasRef.current;
    const context = maskContextRef.current || canvas?.getContext('2d', { willReadFrequently: true });
    if (!canvas || !context || !drawingRef.current || tool === 'box') {
      pendingStrokePointsRef.current = [];
      return;
    }
    maskContextRef.current = context;
    const points = pendingStrokePointsRef.current.splice(0);
    for (const point of points) {
      const previous = previousPointRef.current || point;
      drawMaskSegment(context, previous, point, brushSize, eraseGestureRef.current);
      previousPointRef.current = point;
    }
  }, [brushSize, tool]);

  const applyResponseMask = useCallback(async (
    maskDataUrl: string,
    width?: number,
    height?: number,
    reset = false,
  ) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    await renderMaskDataUrl(canvas, maskDataUrl, width, height, true);
    if (reset) resetHistory();
    else appendCurrentHistory();
  }, [appendCurrentHistory, resetHistory]);

  useEffect(() => {
    if (!isActive || !pageId) return;
    const controller = new AbortController();
    const requestVersion = ++requestVersionRef.current;
    onStatus('Loading page mask...', true);
    void loadEffectivePageMask(pageId, controller.signal)
      .then(async data => {
        if (requestVersion !== requestVersionRef.current) return;
        if (!data.mask_data_url) throw new Error('Page mask response did not include an overlay');
        await applyResponseMask(data.mask_data_url, data.width, data.height, true);
        if (requestVersion === requestVersionRef.current) onStatus('Page Mask Mode ready', false);
      })
      .catch(error => {
        if (controller.signal.aborted) return;
        const canvas = canvasRef.current;
        if (canvas && imageDimensions.width > 0 && imageDimensions.height > 0) {
          initializeEmptyMaskCanvas(canvas, imageDimensions.width, imageDimensions.height);
          resetHistory();
        }
        onStatus(error instanceof Error ? error.message : 'Failed to load the page mask', false);
      });
    return () => {
      controller.abort();
      if (requestVersionRef.current === requestVersion) requestVersionRef.current += 1;
    };
  }, [applyResponseMask, imageDimensions.height, imageDimensions.width, isActive, onStatus, pageId, resetHistory]);

  useEffect(() => {
    if (!isActive) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) return;
      if (event.key === '[' || event.key === ']') {
        setBrushSize(current => Math.max(4, Math.min(100, current + (event.key === '[' ? -4 : 4))));
        event.preventDefault();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isActive]);

  const clear = useCallback(() => {
    const canvas = canvasRef.current;
    const context = maskContextRef.current || canvas?.getContext('2d', { willReadFrequently: true });
    if (!canvas || !context) return;
    maskContextRef.current = context;
    context.clearRect(0, 0, canvas.width, canvas.height);
    commitHistory();
  }, [commitHistory]);

  const undo = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || historyRef.current.length <= 1) return;
    historyRef.current.pop();
    const previous = historyRef.current.at(-1);
    setCanUndo(historyRef.current.length > 1);
    if (!previous || previous.kind === 'empty') {
      (maskContextRef.current || canvas.getContext('2d', { willReadFrequently: true }))?.clearRect(0, 0, canvas.width, canvas.height);
    } else if (previous.kind === 'pixels') {
      (maskContextRef.current || canvas.getContext('2d', { willReadFrequently: true }))?.putImageData(previous.imageData, 0, 0);
    } else {
      void renderMaskDataUrl(canvas, previous.dataUrl, canvas.width, canvas.height, true);
    }
  }, []);

  const autoDetect = useCallback(async () => {
    if (!pageId || isDetecting) return;
    setIsDetecting(true);
    onStatus('Generating automatic text mask...', true);
    const requestVersion = ++requestVersionRef.current;
    try {
      const data = await generateAutomaticPageMask(pageId);
      if (requestVersion !== requestVersionRef.current) return;
      if (!data.mask_data_url) throw new Error('Automatic mask response did not include an overlay');
      await applyResponseMask(data.mask_data_url, data.width, data.height);
      if (requestVersion === requestVersionRef.current) {
        onStatus('Automatic mask ready. Review it before saving.', false);
      }
    } catch (error) {
      if (requestVersion === requestVersionRef.current) {
        onStatus(error instanceof Error ? error.message : 'Failed to generate the automatic page mask', false);
      }
    } finally {
      setIsDetecting(false);
    }
  }, [applyResponseMask, isDetecting, onStatus, pageId]);

  const saveAndClean = useCallback(async () => {
    const canvas = canvasRef.current;
    if (!pageId || !canvas || isSaving) return;
    setIsSaving(true);
    onStatus('Saving page mask...', true);
    try {
      const blob = await new Promise<Blob>((resolve, reject) => {
        canvas.toBlob(value => value ? resolve(value) : reject(new Error('Unable to encode the page mask')), 'image/png');
      });
      await saveEffectivePageMask(pageId, blob);
      setIsActive(false);
      onStatus('Page mask saved. Cleaning page in background...', true);
      // saveEffectivePageMask already enqueues the clean. Calling the generic
      // inpaint pipeline here used to upload the Fabric mask a second time and
      // then block the UI on a synchronous full-page clean.
      // Refresh metadata opportunistically; it must not extend the save
      // critical path or wait for unrelated debounced text updates.
      void Promise.resolve(onSaved?.()).catch(error => {
        console.warn('Page mask saved, but metadata refresh failed:', error);
      });
      onStatus('Page mask saved. Cleaning page in background...', true);
    } catch (error) {
      onStatus(error instanceof Error ? error.message : 'Failed to save and clean the page mask', false);
    } finally {
      setIsSaving(false);
    }
  }, [isSaving, onSaved, onStatus, pageId]);

  const pointFromClient = (canvas: HTMLCanvasElement, clientX: number, clientY: number) => (
    pointerToCanvasPoint(clientX, clientY, canvas.getBoundingClientRect(), canvas.width, canvas.height)
  );

  const pointFromEvent = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current!;
    return pointFromClient(canvas, event.clientX, event.clientY);
  };

  const finishDrawing = useCallback((point?: CanvasPoint) => {
    const canvas = canvasRef.current;
    flushStrokePoints();
    const context = maskContextRef.current || canvas?.getContext('2d', { willReadFrequently: true });
    if (!drawingRef.current || !canvas || !context) return;
    maskContextRef.current = context;
    if (tool === 'box' && point && drawStartRef.current) {
      const start = drawStartRef.current;
      context.save();
      context.globalCompositeOperation = eraseGestureRef.current ? 'destination-out' : 'source-over';
      context.fillStyle = 'rgba(239, 68, 68, 0.9)';
      context.fillRect(
        Math.min(start.x, point.x),
        Math.min(start.y, point.y),
        Math.abs(point.x - start.x),
        Math.abs(point.y - start.y),
      );
      context.restore();
    }
    drawingRef.current = false;
    drawStartRef.current = null;
    previousPointRef.current = null;
    eraseGestureRef.current = false;
    commitHistory();
  }, [commitHistory, flushStrokePoints, tool]);

  const onPointerDown = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    if (!isActive || (event.button !== 0 && event.button !== 2)) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    const point = pointFromEvent(event);
    drawingRef.current = true;
    drawStartRef.current = point;
    previousPointRef.current = point;
    eraseGestureRef.current = shouldEraseMask(tool, event.button);
    if (tool !== 'box') {
      const context = maskContextRef.current || canvasRef.current?.getContext('2d', { willReadFrequently: true });
      if (context) drawMaskSegment(context, point, point, brushSize, eraseGestureRef.current);
      maskContextRef.current = context || null;
    }
  };

  const onPointerMove = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const cursor = cursorRef.current;
    if (cursor) {
      cursor.style.display = 'block';
      cursor.style.left = `${event.clientX - rect.left}px`;
      cursor.style.top = `${event.clientY - rect.top}px`;
    }
    if (!drawingRef.current || !isActive || tool === 'box') return;
    const canvas = canvasRef.current;
    const context = maskContextRef.current || canvas?.getContext('2d', { willReadFrequently: true });
    if (!canvas || !context) return;
    maskContextRef.current = context;
    const samples = event.nativeEvent.getCoalescedEvents?.() || [event.nativeEvent];
    for (const sample of samples) {
      const point = pointerToCanvasPoint(sample.clientX, sample.clientY, rect, canvas.width, canvas.height);
      pendingStrokePointsRef.current.push(point);
    }
    if (strokeFrameRef.current === null) {
      strokeFrameRef.current = requestAnimationFrame(flushStrokePoints);
    }
  };

  const onPointerUp = (event: ReactPointerEvent<HTMLCanvasElement>) => {
    finishDrawing(pointFromEvent(event));
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };

  const onPointerCancel = () => {
    if (tool === 'box') {
      drawingRef.current = false;
      drawStartRef.current = null;
      previousPointRef.current = null;
      eraseGestureRef.current = false;
    } else {
      finishDrawing();
    }
    if (cursorRef.current) cursorRef.current.style.display = 'none';
  };

  useEffect(() => () => {
    if (strokeFrameRef.current !== null) cancelAnimationFrame(strokeFrameRef.current);
  }, []);

  return {
    isActive,
    setIsActive,
    tool,
    setTool,
    brushSize,
    setBrushSize,
    opacity,
    setOpacity,
    isDetecting,
    isSaving,
    canUndo,
    canvasRef,
    cursorRef,
    clear,
    undo,
    autoDetect,
    saveAndClean,
    onPointerDown,
    onPointerMove,
    onPointerUp,
    onPointerCancel,
    onPointerLeave: () => {
      if (cursorRef.current) cursorRef.current.style.display = 'none';
    },
  };
}
