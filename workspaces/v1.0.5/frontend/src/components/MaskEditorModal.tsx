import React, { useEffect, useRef, useState } from 'react';
import { Brush, Eye, EyeOff, X, RotateCcw, Trash2, Loader2, ZoomIn, ZoomOut, Square, Hand, Undo, Redo, Sparkles, AlertTriangle, CheckCircle2, Info, Zap } from 'lucide-react';
import { useProjectStore } from '../stores/projectStore';
import { apiFetch } from '../api/runtime';

interface MaskEditorModalProps {
  blockId: string;
  blockIndex: number;
  pageId?: string;
  initialKernel?: number;
  highQualityMaskAvailable?: boolean;
  onClose: () => void;
  onSaved: (reclean: boolean, cleanMode?: string) => void | Promise<void>;
}

type Tool = 'paint' | 'rect' | 'segment' | 'pan';
type EditorNotice = { tone: 'info' | 'success' | 'error'; text: string } | null;

const MASK_COLOR = { r: 239, g: 68, b: 68, a: 210 } as const;
const MAX_HISTORY_STATES = 24;
const getErrorMessage = (error: unknown, fallback: string): string => (
  error instanceof Error ? error.message : fallback
);

export const isSelectedMaskPixel = (r: number, g: number, b: number, a: number): boolean => (
  a > 12 && Math.max(r, g, b) > 24
);

export const maskImageDataToOverlay = (source: ImageData): ImageData => {
  const output = new ImageData(source.width, source.height);
  for (let i = 0; i < source.data.length; i += 4) {
    if (!isSelectedMaskPixel(source.data[i], source.data[i + 1], source.data[i + 2], source.data[i + 3])) continue;
    output.data[i] = MASK_COLOR.r;
    output.data[i + 1] = MASK_COLOR.g;
    output.data[i + 2] = MASK_COLOR.b;
    output.data[i + 3] = MASK_COLOR.a;
  }
  return output;
};

export const maskOverlayToBinary = (source: ImageData): ImageData => {
  const output = new ImageData(source.width, source.height);
  for (let i = 0; i < source.data.length; i += 4) {
    const selected = isSelectedMaskPixel(source.data[i], source.data[i + 1], source.data[i + 2], source.data[i + 3]);
    const value = selected ? 255 : 0;
    output.data[i] = value;
    output.data[i + 1] = value;
    output.data[i + 2] = value;
    output.data[i + 3] = 255;
  }
  return output;
};

export const dilateMaskOverlay = (source: ImageData, radius: number): ImageData => {
  const safeRadius = Math.max(0, Math.floor(radius));
  if (safeRadius === 0) return maskImageDataToOverlay(source);
  const { width, height } = source;
  const stride = width + 1;
  const rowPrefix = new Uint32Array(height * stride);
  for (let y = 0; y < height; y += 1) {
    let rowSum = 0;
    for (let x = 0; x < width; x += 1) {
      const pixel = (y * width + x) * 4;
      rowSum += isSelectedMaskPixel(source.data[pixel], source.data[pixel + 1], source.data[pixel + 2], source.data[pixel + 3]) ? 1 : 0;
      rowPrefix[y * stride + x + 1] = rowSum;
    }
  }
  const output = new ImageData(width, height);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      let selected = false;
      for (let dy = -safeRadius; dy <= safeRadius && !selected; dy += 1) {
        const sourceY = y + dy;
        if (sourceY < 0 || sourceY >= height) continue;
        const horizontalRadius = Math.floor(Math.sqrt(safeRadius * safeRadius - dy * dy));
        const x0 = Math.max(0, x - horizontalRadius);
        const x1 = Math.min(width - 1, x + horizontalRadius);
        const rowOffset = sourceY * stride;
        selected = rowPrefix[rowOffset + x1 + 1] - rowPrefix[rowOffset + x0] > 0;
      }
      if (!selected) continue;
      const pixel = (y * width + x) * 4;
      output.data[pixel] = MASK_COLOR.r;
      output.data[pixel + 1] = MASK_COLOR.g;
      output.data[pixel + 2] = MASK_COLOR.b;
      output.data[pixel + 3] = MASK_COLOR.a;
    }
  }
  return output;
};

export const magneticFillMaskOverlay = (source: ImageData, maxBridgeGap: number = 45): ImageData => {
  const { width, height } = source;
  const output = new ImageData(width, height);
  for (let i = 0; i < source.data.length; i += 4) {
    if (isSelectedMaskPixel(source.data[i], source.data[i + 1], source.data[i + 2], source.data[i + 3])) {
      output.data[i] = MASK_COLOR.r;
      output.data[i + 1] = MASK_COLOR.g;
      output.data[i + 2] = MASK_COLOR.b;
      output.data[i + 3] = MASK_COLOR.a;
    }
  }

  for (let y = 0; y < height; y += 1) {
    let lastMaskedX = -1;
    for (let x = 0; x < width; x += 1) {
      const idx = (y * width + x) * 4;
      const isMasked = isSelectedMaskPixel(source.data[idx], source.data[idx + 1], source.data[idx + 2], source.data[idx + 3]);
      if (isMasked) {
        if (lastMaskedX !== -1 && (x - lastMaskedX) > 1 && (x - lastMaskedX) <= maxBridgeGap) {
          for (let fillX = lastMaskedX + 1; fillX < x; fillX += 1) {
            const fillIdx = (y * width + fillX) * 4;
            output.data[fillIdx] = MASK_COLOR.r;
            output.data[fillIdx + 1] = MASK_COLOR.g;
            output.data[fillIdx + 2] = MASK_COLOR.b;
            output.data[fillIdx + 3] = MASK_COLOR.a;
          }
        }
        lastMaskedX = x;
      }
    }
  }
  return output;
};

const drawMaskImage = (
  ctx: CanvasRenderingContext2D,
  image: CanvasImageSource,
  width: number,
  height: number,
  mode: 'replace' | 'add' | 'erase' = 'replace',
) => {
  const sourceCanvas = document.createElement('canvas');
  sourceCanvas.width = width;
  sourceCanvas.height = height;
  const sourceCtx = sourceCanvas.getContext('2d', { willReadFrequently: true });
  if (!sourceCtx) return;
  sourceCtx.drawImage(image, 0, 0, width, height);
  const source = sourceCtx.getImageData(0, 0, width, height);
  if (mode === 'replace') {
    ctx.putImageData(maskImageDataToOverlay(source), 0, 0);
    sourceCanvas.width = 0;
    sourceCanvas.height = 0;
    return;
  }
  const target = ctx.getImageData(0, 0, width, height);
  for (let i = 0; i < source.data.length; i += 4) {
    if (!isSelectedMaskPixel(source.data[i], source.data[i + 1], source.data[i + 2], source.data[i + 3])) continue;
    if (mode === 'erase') {
      target.data[i] = 0;
      target.data[i + 1] = 0;
      target.data[i + 2] = 0;
      target.data[i + 3] = 0;
    } else {
      target.data[i] = MASK_COLOR.r;
      target.data[i + 1] = MASK_COLOR.g;
      target.data[i + 2] = MASK_COLOR.b;
      target.data[i + 3] = MASK_COLOR.a;
    }
  }
  ctx.putImageData(target, 0, 0);
  sourceCanvas.width = 0;
  sourceCanvas.height = 0;
};

const loadImage = (src: string): Promise<HTMLImageElement> => new Promise((resolve, reject) => {
  const image = new Image();
  image.onload = () => resolve(image);
  image.onerror = () => reject(new Error('Unable to decode mask image'));
  image.src = src;
});

export const MaskEditorModal: React.FC<MaskEditorModalProps> = ({
  blockId,
  blockIndex,
  pageId,
  initialKernel,
  highQualityMaskAvailable: _highQualityMaskAvailable = true,
  onClose,
  onSaved,
}) => {
  // Core state
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string>('');
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [isSaving, setIsSaving] = useState(false);
  const [notice, setNotice] = useState<EditorNotice>(null);
  const [isDirty, setIsDirty] = useState(false);
  const [cropDataUrl, setCropDataUrl] = useState<string>('');
  const [maskDataUrl, setMaskDataUrl] = useState<string>('');
  const [cropWidth, setCropWidth] = useState<number>(0);
  const [cropHeight, setCropHeight] = useState<number>(0);

  const [activeTool, setActiveTool] = useState<Tool>('paint');
  const [brushSize, setBrushSize] = useState<number>(10);
  const [maskOpacity, setMaskOpacity] = useState<number>(0.6);
  const [maskVisible, setMaskVisible] = useState<boolean>(true);
  const activeProject = useProjectStore((state) => state.activeProject);
  const updateProjectSettings = useProjectStore((state) => state.updateProjectSettings);

  const initialKernelValue = Number(
    activeProject?.settings?.mask_dilation_kernel ?? initialKernel ?? 3
  );
  const [maskKernel, setMaskKernelState] = useState<number>(initialKernelValue);
  const [selectedMaskModel, setSelectedMaskModel] = useState<string>('unet');

  // Keep kernel state synced with project settings
  useEffect(() => {
    if (activeProject?.settings?.mask_dilation_kernel !== undefined) {
      setMaskKernelState(Number(activeProject.settings.mask_dilation_kernel));
    }
  }, [activeProject?.settings?.mask_dilation_kernel]);

  const handleKernelChange = (val: number) => {
    const clamped = Math.max(0, Math.min(50, val));
    setMaskKernelState(clamped);
    try {
      localStorage.setItem('houmi_mask_dilation_kernel', String(clamped));
    } catch {}
    if (activeProject) {
      updateProjectSettings(activeProject.id, {
        ...activeProject.settings,
        mask_dilation_kernel: clamped,
      });
    }
  };

  const initialInpaintEngine = activeProject?.settings?.inpaint_engine
    || activeProject?.settings?.active_inpaint_engine
    || (activeProject?.settings?.default_image_inpaint_method === 'Telea' ? 'telea' : 'lama_manga');

  const [selectedInpaintEngine, setSelectedInpaintEngine] = useState<string>(initialInpaintEngine);

  useEffect(() => {
    const engineFromSettings = activeProject?.settings?.inpaint_engine
      || activeProject?.settings?.active_inpaint_engine
      || (activeProject?.settings?.default_image_inpaint_method === 'Telea' ? 'telea' : 'lama_manga');
    if (engineFromSettings) {
      setSelectedInpaintEngine(engineFromSettings);
    }
  }, [
    activeProject?.settings?.inpaint_engine,
    activeProject?.settings?.active_inpaint_engine,
    activeProject?.settings?.default_image_inpaint_method,
  ]);

  const handleInpaintEngineChange = (val: string) => {
    setSelectedInpaintEngine(val);
    if (activeProject) {
      const updatedSettings = {
        ...activeProject.settings,
        inpaint_engine: val,
        active_inpaint_engine: val,
        default_image_inpaint_method: val === 'telea' ? 'Telea' : (val === 'mat' || val === 'mat_onnx') ? 'MAT' : 'LamaInpaint',
        force_lama_inpaint: val !== 'telea',
      };
      useProjectStore.setState((prev) => (prev.activeProject ? {
        activeProject: {
          ...prev.activeProject,
          settings: updatedSettings,
        },
      } : {}));
      updateProjectSettings(activeProject.id, updatedSettings).catch((err) => {
        console.warn('Failed saving inpaint engine setting:', err);
      });
    }
  };

  // Preview mode
  const [previewMode, setPreviewMode] = useState<boolean>(false);
  const [previewDataUrl, setPreviewDataUrl] = useState<string>('');
  const [isPreviewing, setIsPreviewing] = useState(false);

  // HQ Smart mask
  const [isDetectingText, setIsDetectingText] = useState(false);
  const [isSegmenting, setIsSegmenting] = useState(false);

  // Zoom & Pan
  const [zoom, setZoom] = useState(1);
  const [fitZoom, setFitZoom] = useState(1);
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const [panStart, setPanStart] = useState({ x: 0, y: 0 });

  // Drawing state
  const [isDrawing, setIsDrawing] = useState(false);
  const [mousePos, setMousePos] = useState<{ x: number; y: number } | null>(null);
  const [selectionStart, setSelectionStart] = useState<{ x: number; y: number } | null>(null);
  const [isRightButton, setIsRightButton] = useState(false);
  const selectionStartRef = useRef<{ x: number; y: number } | null>(null);
  const currentPointerRef = useRef<{ x: number; y: number } | null>(null);
  const lastPaintPointRef = useRef<{ x: number; y: number } | null>(null);
  const isRightButtonRef = useRef(false);
  const previousToolRef = useRef<Exclude<Tool, 'pan'>>('paint');
  const spacePanActiveRef = useRef(false);

  // History
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);
  const [historyLength, setHistoryLength] = useState(0);
  const historyStackRef = useRef<ImageData[]>([]);
  const redoStackRef = useRef<ImageData[]>([]);
  const drawingStartSnapshotRef = useRef<ImageData | null>(null);

  // Refs
  const cropCanvasRef = useRef<HTMLCanvasElement>(null);
  const maskCanvasRef = useRef<HTMLCanvasElement>(null);
  const editorViewportRef = useRef<HTMLDivElement>(null);
  const autoMaskDataRef = useRef<string>('');
  const initializedRef = useRef(false);

  const clampZoom = (value: number) => Math.max(0.25, Math.min(16, value));

  // History management
  const updateStackStates = () => {
    setCanUndo(historyStackRef.current.length > 0);
    setCanRedo(redoStackRef.current.length > 0);
    setHistoryLength(historyStackRef.current.length);
  };

  const captureMaskSnapshot = (): ImageData | null => {
    const canvas = maskCanvasRef.current;
    if (!canvas) return null;
    const ctx = canvas.getContext('2d');
    if (!ctx) return null;
    try {
      return ctx.getImageData(0, 0, canvas.width, canvas.height);
    } catch (e) {
      console.warn("Unable to capture mask history snapshot:", e);
      return null;
    }
  };

  const pushHistoryState = (snapshot = captureMaskSnapshot()) => {
    if (!snapshot) return;
    historyStackRef.current.push(snapshot);
    if (historyStackRef.current.length > MAX_HISTORY_STATES) historyStackRef.current.shift();
    redoStackRef.current = [];
    updateStackStates();
  };

  const invalidatePreview = () => {
    setPreviewMode(false);
    setPreviewDataUrl('');
  };

  const markMaskChanged = (message?: string) => {
    setIsDirty(true);
    invalidatePreview();
    if (message) setNotice({ tone: 'info', text: message });
  };

  const handleUndo = () => {
    const canvas = maskCanvasRef.current;
    if (!canvas || historyStackRef.current.length === 0) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    try {
      const currentSnapshot = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const previousState = historyStackRef.current.pop()!;
      redoStackRef.current.push(currentSnapshot);
      ctx.putImageData(previousState, 0, 0);
      updateStackStates();
      markMaskChanged('Undo: ย้อนการแก้ไขมาสก์แล้ว');
    } catch (e) {
      console.warn("Undo failed:", e);
    }
  };

  const handleRedo = () => {
    const canvas = maskCanvasRef.current;
    if (!canvas || redoStackRef.current.length === 0) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    try {
      const currentSnapshot = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const nextState = redoStackRef.current.pop()!;
      historyStackRef.current.push(currentSnapshot);
      if (historyStackRef.current.length > MAX_HISTORY_STATES) historyStackRef.current.shift();
      ctx.putImageData(nextState, 0, 0);
      updateStackStates();
      markMaskChanged('Redo: ทำการแก้ไขซ้ำแล้ว');
    } catch (e) {
      console.warn("Redo failed:", e);
    }
  };

  // Load mask data on mount
  useEffect(() => {
    const controller = new AbortController();
    const loadMaskData = async () => {
      try {
        setLoading(true);
        setLoadError('');
        setNotice(null);
        setIsDirty(false);
        setPreviewMode(false);
        setPreviewDataUrl('');
        setPanOffset({ x: 0, y: 0 });
        historyStackRef.current = [];
        redoStackRef.current = [];
        updateStackStates();
        initializedRef.current = false;

        let res = await apiFetch(`/api/pipeline/blocks/${blockId}/mask?kernel=${maskKernel}`, { signal: controller.signal });
        if (!res.ok) {
          res = await apiFetch(`/api/blocks/${blockId}/mask-crop?kernel=${maskKernel}`, { signal: controller.signal });
        }
        if (!res.ok) throw new Error(`Failed to load mask data: ${res.status}`);

        const data = await res.json();
        const cropUrl = data.crop_data_url || data.crop;
        const maskUrl = data.mask_data_url || data.mask;

        if (!cropUrl || !maskUrl) {
          throw new Error('Invalid mask response data format');
        }

        setCropDataUrl(cropUrl);
        setMaskDataUrl(maskUrl);
        autoMaskDataRef.current = maskUrl;

        try {
          const autoRes = await apiFetch(`/api/pipeline/blocks/${blockId}/mask?force_auto=true`, { signal: controller.signal });
          if (autoRes.ok) {
            const autoData = await autoRes.json();
            autoMaskDataRef.current = autoData.mask_data_url || autoData.mask || maskUrl;
          }
        } catch (autoError) {
          if ((autoError as Error).name !== 'AbortError') console.warn('Auto mask fallback unavailable:', autoError);
        }

        if (data.crop_width && data.crop_height) {
          setCropWidth(data.crop_width);
          setCropHeight(data.crop_height);
        } else {
          const tempImg = new Image();
          tempImg.onload = () => {
            setCropWidth(tempImg.naturalWidth);
            setCropHeight(tempImg.naturalHeight);
          };
          tempImg.src = cropUrl;
        }

        setLoading(false);
      } catch (err: unknown) {
        if (err instanceof Error && err.name === 'AbortError') return;
        console.error('Load mask error:', err);
        setLoadError(getErrorMessage(err, 'Unknown error'));
        setLoading(false);
      }
    };

    loadMaskData();
    return () => controller.abort();
  }, [blockId, loadAttempt]);

  // Initialize canvases when images load
  useEffect(() => {
    if (!cropDataUrl || !maskDataUrl) return;
    if (!cropCanvasRef.current || !maskCanvasRef.current) return;

    const cropCanvas = cropCanvasRef.current;
    const maskCanvas = maskCanvasRef.current;
    const cropCtx = cropCanvas.getContext('2d');
    const maskCtx = maskCanvas.getContext('2d');
    if (!cropCtx || !maskCtx) return;

    const cropImg = new Image();
    const maskImg = new Image();
    let cropLoaded = false;
    let maskLoaded = false;

    const tryRender = () => {
      if (!cropLoaded || !maskLoaded) return;

      cropCanvas.width = cropWidth;
      cropCanvas.height = cropHeight;
      maskCanvas.width = cropWidth;
      maskCanvas.height = cropHeight;

      cropCtx.drawImage(cropImg, 0, 0);
      drawMaskImage(maskCtx, maskImg, cropWidth, cropHeight, 'replace');
      initializedRef.current = true;

      // Calculate fit zoom
      if (editorViewportRef.current) {
        const vp = editorViewportRef.current;
        const fitW = (vp.clientWidth - 48) / cropWidth;
        const fitH = (vp.clientHeight - 48) / cropHeight;
        const fit = Math.min(fitW, fitH, 1);
        setFitZoom(fit);
        setZoom(fit);
        setPanOffset({ x: 0, y: 0 });
      }
    };

    cropImg.onload = () => { cropLoaded = true; tryRender(); };
    maskImg.onload = () => { maskLoaded = true; tryRender(); };
    cropImg.src = cropDataUrl;
    maskImg.src = maskDataUrl;
  }, [cropDataUrl, maskDataUrl, cropWidth, cropHeight]);

  // Canvas mouse coordinate helper
  const getCanvasMouseCoordinates = (event: React.MouseEvent): { x: number; y: number } | null => {
    const canvas = maskCanvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const x = Math.max(0, Math.min(canvas.width - 1, Math.floor((event.clientX - rect.left) * canvas.width / Math.max(1, rect.width))));
    const y = Math.max(0, Math.min(canvas.height - 1, Math.floor((event.clientY - rect.top) * canvas.height / Math.max(1, rect.height))));
    return { x, y };
  };

  // Drawing handlers
  const startDrawing = (event: React.MouseEvent) => {
    if (isSaving || isDetectingText || isSegmenting || previewMode || (event.button !== 0 && event.button !== 1 && event.button !== 2)) return;
    const coords = getCanvasMouseCoordinates(event);
    if (!coords) return;
    currentPointerRef.current = coords;

    const isSpacePan = spacePanActiveRef.current;
    if (activeTool === 'pan' || event.button === 1 || isSpacePan) {
      setIsPanning(true);
      setPanStart({ x: event.clientX - panOffset.x, y: event.clientY - panOffset.y });
      return;
    }

    // Ensure painting with left click NEVER triggers panning
    setIsPanning(false);

    isRightButtonRef.current = event.button === 2;
    setIsRightButton(event.button === 2);
    setIsDrawing(true);
    selectionStartRef.current = coords;
    setSelectionStart(coords);
    lastPaintPointRef.current = coords;

    const canvas = maskCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    drawingStartSnapshotRef.current = captureMaskSnapshot();

    if (activeTool === 'paint') {
      ctx.globalCompositeOperation = isRightButtonRef.current ? 'destination-out' : 'source-over';
      ctx.fillStyle = `rgba(${MASK_COLOR.r}, ${MASK_COLOR.g}, ${MASK_COLOR.b}, ${MASK_COLOR.a / 255})`;
      ctx.beginPath();
      ctx.arc(coords.x, coords.y, brushSize / 2, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalCompositeOperation = 'source-over';
    }
  };

  const draw = (event: React.MouseEvent) => {
    const coords = getCanvasMouseCoordinates(event);
    if (!coords) return;
    setMousePos(coords);
    currentPointerRef.current = coords;

    if (isPanning) {
      setPanOffset({
        x: event.clientX - panStart.x,
        y: event.clientY - panStart.y
      });
      return;
    }

    if (!isDrawing || activeTool === 'pan') return;

    const canvas = maskCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    if (activeTool === 'paint') {
      ctx.globalCompositeOperation = isRightButtonRef.current ? 'destination-out' : 'source-over';
      ctx.strokeStyle = `rgba(${MASK_COLOR.r}, ${MASK_COLOR.g}, ${MASK_COLOR.b}, ${MASK_COLOR.a / 255})`;
      ctx.lineWidth = brushSize;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.beginPath();
      const previous = lastPaintPointRef.current || coords;
      ctx.moveTo(previous.x, previous.y);
      ctx.lineTo(coords.x, coords.y);
      ctx.stroke();
      ctx.globalCompositeOperation = 'source-over';
      lastPaintPointRef.current = coords;
    }
  };

  const applySmartSegment = async (
    start: { x: number; y: number },
    end: { x: number; y: number },
    erase: boolean,
    beforeSnapshot: ImageData | null,
  ) => {
    const maskCanvas = maskCanvasRef.current;
    if (!maskCanvas) return;
    const maskCtx = maskCanvas.getContext('2d');
    if (!maskCtx) return;

    const x0 = Math.min(start.x, end.x);
    const y0 = Math.min(start.y, end.y);
    const x1 = Math.max(start.x, end.x);
    const y1 = Math.max(start.y, end.y);
    if (x1 - x0 < 3 || y1 - y0 < 3) return;

    setIsSegmenting(true);
    setNotice({ tone: 'info', text: erase ? 'Smart Segment กำลังเลือกรายละเอียดเพื่อลบ…' : 'Smart Segment กำลังเลือกรายละเอียดตัวอักษร…' });
    try {
      const response = await apiFetch(`/api/pipeline/blocks/${blockId}/mask/smart-segment`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ x0, y0, x1, y1, kernel: maskKernel }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Smart Segment failed');

      const samMask = await loadImage(data.mask);
      pushHistoryState(beforeSnapshot);
      drawMaskImage(maskCtx, samMask, maskCanvas.width, maskCanvas.height, erase ? 'erase' : 'add');
      markMaskChanged(erase ? 'ลบพื้นที่ที่ Smart Segment เลือกแล้ว' : 'เพิ่มพื้นที่จาก Smart Segment แล้ว');
    } catch (error: unknown) {
      console.error('Smart Segment failed:', error);
      setNotice({ tone: 'error', text: error instanceof Error ? error.message : 'Smart Segment ไม่สำเร็จ' });
    } finally {
      setIsSegmenting(false);
    }
  };

  const stopDrawing = () => {
    if (isPanning) {
      setIsPanning(false);
      return;
    }

    if (isDrawing) {
      const start = selectionStartRef.current;
      const end = currentPointerRef.current;
      const beforeSnapshot = drawingStartSnapshotRef.current;
      if (activeTool === 'segment' && start && end) {
        void applySmartSegment(start, end, isRightButtonRef.current, beforeSnapshot);
      } else if (activeTool === 'rect' && start && end) {
        const canvas = maskCanvasRef.current;
        const ctx = canvas?.getContext('2d');
        const x0 = Math.min(start.x, end.x);
        const y0 = Math.min(start.y, end.y);
        const width = Math.abs(end.x - start.x);
        const height = Math.abs(end.y - start.y);
        if (ctx && width >= 1 && height >= 1) {
          pushHistoryState(beforeSnapshot);
          ctx.globalCompositeOperation = isRightButtonRef.current ? 'destination-out' : 'source-over';
          ctx.fillStyle = `rgba(${MASK_COLOR.r}, ${MASK_COLOR.g}, ${MASK_COLOR.b}, ${MASK_COLOR.a / 255})`;
          ctx.fillRect(x0, y0, width, height);
          ctx.globalCompositeOperation = 'source-over';
          markMaskChanged(isRightButtonRef.current ? 'ลบพื้นที่สี่เหลี่ยมแล้ว' : 'เพิ่มพื้นที่สี่เหลี่ยมแล้ว');
        }
      } else if (activeTool === 'paint') {
        pushHistoryState(beforeSnapshot);
        markMaskChanged(isRightButtonRef.current ? 'ลบมาสก์ด้วยพู่กันแล้ว' : 'เพิ่มมาสก์ด้วยพู่กันแล้ว');
      }
      setIsDrawing(false);
      selectionStartRef.current = null;
      setSelectionStart(null);
      setIsRightButton(false);
      drawingStartSnapshotRef.current = null;
      lastPaintPointRef.current = null;
    }
  };

  // Clear and reset actions
  const handleClearAll = () => {
    const canvas = maskCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    pushHistoryState();
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    markMaskChanged('ล้างมาสก์ทั้งหมดแล้ว — กด Undo เพื่อย้อนกลับได้');
  };

  const handleResetToAuto = async () => {
    if (!maskCanvasRef.current) return;
    const canvas = maskCanvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    try {
      setIsDetectingText(true);
      setNotice({ tone: 'info', text: 'กำลังวิเคราะห์และดึงมาสก์อัตโนมัติใหม่…' });
      const autoRes = await apiFetch(`/api/pipeline/blocks/${blockId}/mask?force_auto=true&kernel=${maskKernel}`);
      if (autoRes.ok) {
        const autoData = await autoRes.json();
        const maskUrl = autoData.mask_data_url || autoData.mask;
        if (maskUrl) {
          autoMaskDataRef.current = maskUrl;
          const img = await loadImage(maskUrl);
          pushHistoryState();
          drawMaskImage(ctx, img, canvas.width, canvas.height, 'replace');
          markMaskChanged(`คืนค่าเป็นมาสก์อัตโนมัติ ขนาด ${maskKernel}px แล้ว`);
        }
      }
    } catch (error) {
      setNotice({ tone: 'error', text: error instanceof Error ? error.message : 'โหลดมาสก์อัตโนมัติไม่สำเร็จ' });
    } finally {
      setIsDetectingText(false);
    }
  };

  // Expand mask by kernel
  const expandMaskByKernel = () => {
    const canvas = maskCanvasRef.current;
    if (!canvas || maskKernel <= 0) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    pushHistoryState();
    const source = ctx.getImageData(0, 0, canvas.width, canvas.height);
    ctx.putImageData(dilateMaskOverlay(source, maskKernel), 0, 0);
    markMaskChanged(`ขยายขอบมาสก์ ${maskKernel}px แล้ว`);
  };

  // Apply Magnetic line fill
  const applyMagneticFill = () => {
    const canvas = maskCanvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    pushHistoryState();
    const source = ctx.getImageData(0, 0, canvas.width, canvas.height);
    ctx.putImageData(magneticFillMaskOverlay(source, 45), 0, 0);
    markMaskChanged('เชื่อมช่องว่างระหว่างคำเต็มบรรทัด (Magnetic Fill) เรียบร้อย');
  };

  // HQ Smart mask detection
  const handleHQSmartMask = async () => {
    if (!pageId) return;
    setIsDetectingText(true);
    setNotice({ tone: 'info', text: 'กำลังวิเคราะห์ภาพและสร้างมาสก์ด้วยระบบที่เหมาะสม…' });

    try {
      const res = await apiFetch(`/api/pipeline/blocks/${blockId}/mask/text-detect?kernel=${maskKernel}&method=${selectedMaskModel}`, {
        method: 'POST',
      });

      if (!res.ok) {
        let detail = 'Text detection failed';
        try {
          const payload = await res.json();
          detail = String(payload.detail || payload.message || detail);
        } catch { /* response was not JSON */ }
        throw new Error(detail);
      }
      const data = await res.json() as {
        mask?: string;
        regions?: Array<{ x: number; y: number; width: number; height: number }>;
        detected_line_count?: number;
        mask_mode?: 'monochrome_flat' | 'color_or_complex';
      };

      const canvas = maskCanvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      if (data.mask) {
        const hqMaskImg = await loadImage(data.mask);
        pushHistoryState();
        drawMaskImage(ctx, hqMaskImg, canvas.width, canvas.height, 'replace');
        const modeLabel = data.mask_mode === 'monochrome_flat' ? 'ระบบดำ' : 'ระบบสี';
        markMaskChanged(`สร้างมาสก์ด้วย${modeLabel}แล้ว`);
      } else if (data.regions) {
        pushHistoryState();
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = `rgba(${MASK_COLOR.r}, ${MASK_COLOR.g}, ${MASK_COLOR.b}, ${MASK_COLOR.a / 255})`;
        data.regions.forEach((region) => {
          if (region.width < canvas.width * 0.9 && region.height < canvas.height * 0.9) {
            ctx.fillRect(region.x, region.y, region.width, region.height);
          }
        });
        markMaskChanged(`สร้างมาสก์จากกรอบตัวอักษร ${data.regions.length} จุดแล้ว`);
      }
    } catch (err) {
      console.error('HQ detection error:', err);
      setNotice({ tone: 'error', text: err instanceof Error ? err.message : 'Text Detection ไม่สำเร็จ' });
    } finally {
      setIsDetectingText(false);
    }
  };

  const getBinaryMaskBlob = async (): Promise<Blob> => {
    const canvas = maskCanvasRef.current;
    if (!canvas) throw new Error('Mask canvas is not ready');
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('Mask canvas context is unavailable');
    const binaryCanvas = document.createElement('canvas');
    binaryCanvas.width = canvas.width;
    binaryCanvas.height = canvas.height;
    const binaryCtx = binaryCanvas.getContext('2d');
    if (!binaryCtx) throw new Error('Unable to prepare binary mask');
    binaryCtx.putImageData(maskOverlayToBinary(ctx.getImageData(0, 0, canvas.width, canvas.height)), 0, 0);
    return new Promise<Blob>((resolve, reject) => {
      binaryCanvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('Unable to encode binary mask')), 'image/png');
    });
  };

  // Preview inpaint
  const handlePreviewInpaint = async () => {
    if (!pageId) {
      setNotice({ tone: 'error', text: 'ไม่พบ Page ID สำหรับสร้าง Preview' });
      return;
    }
    setIsPreviewing(true);
    setNotice({ tone: 'info', text: 'กำลังสร้าง Preview เฉพาะบริเวณนี้…' });

    try {
      const maskBlob = await getBinaryMaskBlob();

      const reader = new FileReader();
      const maskBase64 = await new Promise<string>((resolve) => {
        reader.onload = () => resolve((reader.result as string).split(',')[1]);
        reader.readAsDataURL(maskBlob);
      });

      const res = await apiFetch(`/api/pipeline/blocks/${blockId}/inpaint-preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          mask_base64: maskBase64,
          engine: selectedInpaintEngine
        })
      });

      if (!res.ok) {
        const errorText = await res.text();
        throw new Error(`Preview failed (${res.status}): ${errorText}`);
      }

      const data = await res.json();
      const previewUrl = data.preview || data.preview_data_url || (data.preview_base64 ? `data:image/png;base64,${data.preview_base64}` : '');

      if (previewUrl) {
        setPreviewDataUrl(previewUrl);
        setPreviewMode(true);
        setNotice({ tone: 'success', text: 'Preview พร้อมแล้ว — กด Compare เพื่อสลับ Mask/ผลลัพธ์' });
      } else {
        throw new Error('Preview succeeded but no image was returned');
      }
    } catch (err: unknown) {
      console.error('Preview error:', err);
      setNotice({ tone: 'error', text: getErrorMessage(err, 'สร้าง Preview ไม่สำเร็จ') });
    } finally {
      setIsPreviewing(false);
    }
  };

  // Fast Telea Live Preview (5-15ms)
  const handleFastPreviewInpaint = async () => {
    if (!pageId) return;
    setIsPreviewing(true);

    try {
      const maskBlob = await getBinaryMaskBlob();
      const reader = new FileReader();
      const maskBase64 = await new Promise<string>((resolve) => {
        reader.onload = () => resolve((reader.result as string).split(',')[1]);
        reader.readAsDataURL(maskBlob);
      });

      const res = await apiFetch(`/api/pipeline/blocks/${blockId}/fast-preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mask_base64: maskBase64 }),
      });

      if (!res.ok) {
        throw new Error(`Fast preview failed (${res.status})`);
      }

      const data = await res.json();
      const previewUrl = data.preview_url;

      if (previewUrl) {
        setPreviewDataUrl(previewUrl);
        setPreviewMode(true);
        setNotice({ tone: 'success', text: 'Fast Preview (Telea ~10ms) พร้อมแล้ว' });
      }
    } catch (err: unknown) {
      console.error('Fast preview error:', err);
      handlePreviewInpaint();
    } finally {
      setIsPreviewing(false);
    }
  };

  // Save mask
  const handleSave = async (reclean: boolean) => {
    setIsSaving(true);
    setNotice({ tone: 'info', text: reclean ? 'กำลังบันทึกและนำ Mask ไปใช้…' : 'กำลังบันทึก Mask โดยยังไม่อัปเดตภาพ Clean…' });
    try {
      const blob = await getBinaryMaskBlob();

      const formData = new FormData();
      formData.append('file', blob, 'mask.png');
      const res = await apiFetch(`/api/pipeline/blocks/${blockId}/mask?reclean=${reclean ? 'true' : 'false'}&allow_full_page=true&engine=${selectedInpaintEngine}`, {
        method: 'POST',
        body: formData
      });

      if (!res.ok) {
        const errorText = await res.text();
        throw new Error(`Save failed (${res.status}): ${errorText}`);
      }
      const result = await res.json().catch(() => ({})) as { clean_mode?: string };
      const cleanMode = result.clean_mode;
      setIsDirty(false);
      setNotice({
        tone: cleanMode === 'needs_page_clean' || cleanMode === 'region_background' ? 'info' : 'success',
        text: cleanMode === 'needs_page_clean'
          ? 'บันทึกมาสก์แล้ว — ยังไม่มี Clean Base สำหรับรีคลีนเฉพาะช่อง จึงไม่ได้เริ่ม Full Page Clean'
          : cleanMode === 'region_background'
            ? 'บันทึกมาสก์แล้ว — กำลังคลีนเฉพาะบริเวณนี้เบื้องหลัง'
          : reclean ? 'บันทึกและคลีนเฉพาะบริเวณนี้เสร็จแล้ว' : 'บันทึกมาสก์แล้ว',
      });
      await onSaved(reclean, cleanMode);
      onClose();
    } catch (err: unknown) {
      console.error('Save error:', err);
      setNotice({ tone: 'error', text: getErrorMessage(err, 'บันทึกมาสก์ไม่สำเร็จ') });
    } finally {
      setIsSaving(false);
    }
  };

  const requestClose = () => {
    if (isSaving || isPreviewing || isDetectingText || isSegmenting) return;
    if (isDirty && !window.confirm('มีการแก้ไขมาสก์ที่ยังไม่ได้บันทึก ต้องการปิดและทิ้งการแก้ไขหรือไม่?')) return;
    onClose();
  };

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) {
        return;
      }

      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z' && !e.shiftKey) {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        handleUndo();
      } else if ((e.ctrlKey || e.metaKey) && (e.key.toLowerCase() === 'y' || (e.key.toLowerCase() === 'z' && e.shiftKey))) {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        handleRedo();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        if (previewMode) setPreviewMode(false);
        else requestClose();
      } else if (e.key === ' ' && !spacePanActiveRef.current) {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        if (activeTool !== 'pan') previousToolRef.current = activeTool;
        spacePanActiveRef.current = true;
        setActiveTool('pan');
      } else if (!e.ctrlKey && !e.metaKey && (e.key === 'b' || e.key === 'B' || e.key === '1')) {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        setActiveTool('paint');
      } else if (!e.ctrlKey && !e.metaKey && (e.key === 'r' || e.key === 'R' || e.key === '2')) {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        setActiveTool('rect');
      } else if (!e.ctrlKey && !e.metaKey && (e.key === 's' || e.key === 'S' || e.key === '3')) {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        setActiveTool('segment');
      } else if (e.key === 'h' || e.key === 'H') {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        if (previewDataUrl) setPreviewMode(prev => !prev);
      } else if (e.key === '[') {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        setBrushSize(b => Math.max(1, b - 2));
      } else if (e.key === ']') {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        setBrushSize(b => Math.min(50, b + 2));
      }
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.key === ' ' && spacePanActiveRef.current) {
        spacePanActiveRef.current = false;
        setActiveTool(previousToolRef.current);
      }
    };

    window.addEventListener('keydown', handleKeyDown, { capture: true });
    window.addEventListener('keyup', handleKeyUp, { capture: true });
    return () => {
      window.removeEventListener('keydown', handleKeyDown, { capture: true });
      window.removeEventListener('keyup', handleKeyUp, { capture: true });
    };
  }, [activeTool, previewMode, previewDataUrl, isDirty, isSaving, isPreviewing, isDetectingText, isSegmenting]);

  // Zoom with mouse wheel
  const handleWheel = (event: React.WheelEvent) => {
    event.preventDefault();

    const rect = editorViewportRef.current?.getBoundingClientRect();
    if (!rect) return;

    const mouseX = event.clientX - rect.left - rect.width / 2;
    const mouseY = event.clientY - rect.top - rect.height / 2;

    const oldZoom = zoom;
    const newZoom = clampZoom(oldZoom * (event.deltaY < 0 ? 1.15 : 1 / 1.15));

    // Zoom to cursor
    const zoomRatio = newZoom / oldZoom;
    setPanOffset(prev => ({
      x: mouseX - (mouseX - prev.x) * zoomRatio,
      y: mouseY - (mouseY - prev.y) * zoomRatio
    }));

    setZoom(newZoom);
  };

  const displayWidth = Math.round(cropWidth * zoom);
  const displayHeight = Math.round(cropHeight * zoom);
  const editorBusy = isSaving || isPreviewing || isDetectingText || isSegmenting;
  const selectTool = (tool: Tool) => {
    if (editorBusy) return;
    if (tool !== 'pan') previousToolRef.current = tool;
    setPreviewMode(false);
    setActiveTool(tool);
  };

  if (loading) {
    return (
      <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/80 backdrop-blur-sm">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-8 h-8 text-yellow-400 animate-spin motion-reduce:animate-none" />
          <p className="text-sm text-slate-300">กำลังเตรียมภาพและมาสก์…</p>
        </div>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/80 backdrop-blur-sm">
        <div className="bg-zinc-900 border border-red-500/30 rounded-xl p-6 max-w-md shadow-2xl">
          <h3 className="text-lg font-bold text-red-400 mb-2 flex items-center gap-2"><AlertTriangle size={18} /> เปิด Mask Editor ไม่สำเร็จ</h3>
          <p className="text-sm text-slate-300 mb-4">{loadError}</p>
          <div className="flex justify-end gap-2">
            <button onClick={onClose} className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-white rounded-lg transition-colors motion-reduce:transition-none">ปิด</button>
            <button onClick={() => setLoadAttempt(value => value + 1)} className="px-4 py-2 bg-yellow-500 text-black hover:bg-yellow-400 font-bold rounded-lg transition-colors motion-reduce:transition-none">ลองใหม่</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/90 backdrop-blur-sm">
      <div className="w-[96vw] h-[94vh] bg-[#0A0D12] border border-zinc-700/80 rounded-xl shadow-2xl flex flex-col overflow-hidden">

        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 bg-[#05070C] border-b border-zinc-800">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-9 h-9 rounded-lg bg-yellow-500/15 border border-yellow-500/30 flex items-center justify-center text-yellow-300"><Brush size={17} /></div>
            <div className="min-w-0">
              <h2 className="text-sm font-bold text-slate-100">แก้ไขพื้นที่ลบข้อความ <span className="text-yellow-400">#{blockIndex + 1}</span></h2>
              <p className="text-[10px] text-slate-500 mt-0.5">ซ้าย = เพิ่มมาสก์ · ขวา = ลบมาสก์ · Scroll = Zoom · Space = Pan</p>
            </div>
            <span className={`ml-2 rounded-full border px-2 py-0.5 text-[9px] font-bold ${isDirty ? 'border-amber-500/40 bg-amber-500/10 text-amber-300' : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'}`}>
              {isDirty ? 'UNSAVED' : 'SAVED'}
            </span>
          </div>

          <div className="flex items-center gap-2">
            {/* Solid Fill Color Patch button */}
            <button
              onClick={() => {
                const canvas = maskCanvasRef.current;
                if (!canvas) return;
                const ctx = canvas.getContext('2d');
                if (!ctx) return;
                pushHistoryState();
                ctx.fillStyle = `rgba(${MASK_COLOR.r}, ${MASK_COLOR.g}, ${MASK_COLOR.b}, ${MASK_COLOR.a})`;
                ctx.fillRect(0, 0, canvas.width, canvas.height);
                markMaskChanged('วาดแปะสีทึบคลีนฟองคำพูดเรียบร้อย');
              }}
              disabled={editorBusy}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-bold transition-all bg-amber-500/20 border border-amber-500/40 text-amber-300 hover:bg-amber-500/30 active:scale-95 cursor-pointer"
              title="Solid Color Paint: วาดแปะสีพื้นหลังทึบปิดทับตัวหนังสือทันที"
            >
              <Zap size={14} />
              <span>Solid Wipe</span>
            </button>

            {/* Dedicated Mask Model Selector & Explicit Scan Action */}
            <div className="flex items-center gap-1.5 bg-zinc-900/90 border border-cyan-500/40 rounded-lg px-2.5 py-1 shadow-sm">
              <span className="text-[11px] text-cyan-400 font-bold flex items-center gap-1">
                <span>🎭</span>
                <span>โมเดล:</span>
              </span>
              <select
                value={selectedMaskModel}
                onChange={(e) => setSelectedMaskModel(e.target.value)}
                disabled={editorBusy}
                className="bg-zinc-950 border border-zinc-700 rounded px-2 py-1 text-xs text-cyan-200 font-medium focus:outline-none focus:border-cyan-400 cursor-pointer"
                title="เลือกโมเดล/วิธีการสร้าง Mask"
              >
                <option value="unet">🎨 Manga UNet++ (Pixel Neural)</option>
                <option value="ctd">🤖 ComicTextDetector (CTD ONNX)</option>
                <option value="sam">🎯 Meta SAM 2.1 (Segment Anything)</option>
                <option value="contour">⚡ Adaptive Contours (มังงะขาวดำ)</option>
                <option value="imagetrans">📄 ImageTrans Otsu (Binarization)</option>
                <option value="balloon">📦 Full Bounding Box (Solid Rect)</option>
              </select>

              <button
                type="button"
                onClick={handleHQSmartMask}
                disabled={editorBusy}
                className="flex items-center gap-1 px-2.5 py-1 rounded text-xs font-bold transition-all bg-cyan-500/20 hover:bg-cyan-500/35 border border-cyan-500/50 text-cyan-200 active:scale-95 cursor-pointer shadow-sm"
                title="สแกนสร้าง Mask ทันทีด้วยโมเดลที่เลือก"
              >
                {isDetectingText ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
                <span>สแกน Mask</span>
              </button>
            </div>

            <button
              onClick={handleResetToAuto}
              disabled={editorBusy}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-bold transition-all bg-cyan-500/20 border border-cyan-500/40 text-cyan-300 hover:bg-cyan-500/30 active:scale-95 cursor-pointer"
              title="Direct Brush Clean: ลบอักษรและคืนค่ามาสก์อัตโนมัติทันที"
            >
              <Sparkles size={14} />
              <span>🧹 Direct Clean (ลบอักษร)</span>
            </button>

            <button onClick={handleUndo} disabled={!canUndo || editorBusy} className="p-2 rounded-lg border border-zinc-800 text-slate-400 hover:text-white hover:bg-zinc-800 disabled:opacity-30 transition-colors motion-reduce:transition-none" title="Undo (Ctrl+Z)"><Undo size={15} /></button>
            <button onClick={handleRedo} disabled={!canRedo || editorBusy} className="p-2 rounded-lg border border-zinc-800 text-slate-400 hover:text-white hover:bg-zinc-800 disabled:opacity-30 transition-colors motion-reduce:transition-none" title="Redo (Ctrl+Y)"><Redo size={15} /></button>

            <button
              onClick={() => setPreviewMode(prev => !prev)}
              disabled={!previewDataUrl || editorBusy}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-bold transition-all ${
                previewMode
                  ? 'bg-cyan-500/20 border border-cyan-500/50 text-cyan-300'
                  : 'bg-zinc-900 border border-zinc-700 text-slate-400 hover:text-cyan-300'
              } disabled:opacity-30 disabled:cursor-not-allowed motion-reduce:transition-none`}
              title="Toggle preview mode (H)"
            >
              {previewMode ? <EyeOff size={14} /> : <Eye size={14} />}
              <span>{previewMode ? 'กลับไปดู Mask' : 'Compare'}</span>
            </button>

            <button
              onClick={requestClose}
              className="p-1.5 rounded hover:bg-zinc-800 text-slate-400 hover:text-white transition-colors"
              title="Close (Esc)"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {notice && (
          <div className={`flex items-center gap-2 border-b px-4 py-2 text-xs ${notice.tone === 'error' ? 'border-red-500/25 bg-red-500/10 text-red-300' : notice.tone === 'success' ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300' : 'border-cyan-500/20 bg-cyan-500/[0.06] text-cyan-200'}`}>
            {notice.tone === 'error' ? <AlertTriangle size={14} /> : notice.tone === 'success' ? <CheckCircle2 size={14} /> : <Info size={14} />}
            <span className="truncate">{notice.text}</span>
            <button onClick={() => setNotice(null)} className="ml-auto text-current opacity-60 hover:opacity-100"><X size={13} /></button>
          </div>
        )}

        {/* Main Content */}
        <div className="flex flex-1 overflow-hidden">

          {/* Left Toolbar */}
          <div className="w-28 bg-[#05070C] border-r border-zinc-800 flex flex-col px-2 py-3 gap-1.5">
            <ToolButton
              icon={Brush}
              label="Brush"
              active={activeTool === 'paint'}
              onClick={() => selectTool('paint')}
              title="Brush Tool (B) - วาดพู่กันระบายพื้นที่ลบ"
              shortcut="B"
            />
            <ToolButton
              icon={Square}
              label="Box"
              active={activeTool === 'rect'}
              onClick={() => selectTool('rect')}
              title="Rectangle Tool (R) - ลากกรอบสี่เหลี่ยมคลุมตัวหนังสือ"
              shortcut="R"
            />
            <ToolButton
              icon={Zap}
              label="Solid Paint"
              active={false}
              onClick={() => {
                const canvas = maskCanvasRef.current;
                if (!canvas) return;
                const ctx = canvas.getContext('2d');
                if (!ctx) return;
                pushHistoryState();
                ctx.fillStyle = `rgba(${MASK_COLOR.r}, ${MASK_COLOR.g}, ${MASK_COLOR.b}, ${MASK_COLOR.a})`;
                ctx.fillRect(0, 0, canvas.width, canvas.height);
                markMaskChanged('แปะสีทึบปิดทับฟองคำพูดเรียบร้อย');
              }}
              title="Solid Color Paint - เติมสีทึบคลีนฟองคำพูดทันทีแบบ Koharu"
            />
            <ToolButton
              icon={Sparkles}
              label="Segment"
              active={activeTool === 'segment'}
              onClick={() => selectTool('segment')}
              title="Smart Segment (S) - ลากคลุมวัตถุเฉพาะจุด"
              shortcut="S"
            />

            <div className="w-full h-px bg-zinc-800 my-1.5" />

            <ToolButton
              icon={Hand}
              label="Pan"
              active={activeTool === 'pan'}
              onClick={() => selectTool('pan')}
              title="Pan Tool (Space)"
              shortcut="Space"
            />
            <div className="mt-3 rounded-lg border border-zinc-800 bg-zinc-900/40 p-2 text-[9px] leading-relaxed text-slate-500">
              ทุกเครื่องมือใช้<br /><span className="text-slate-300">คลิกซ้าย เพิ่ม</span><br /><span className="text-red-300">คลิกขวา ลบ</span>
            </div>
          </div>

          {/* Center Canvas Area */}
          <div className="flex-1 flex flex-col bg-[#0F131C] overflow-hidden">
            <div
              ref={editorViewportRef}
              onWheel={handleWheel}
              className="flex-1 overflow-hidden relative bg-[radial-gradient(circle_at_center,rgba(39,46,61,0.45),rgba(10,13,18,0.9))]"
              style={{ cursor: previewMode ? 'default' : activeTool === 'pan' || isPanning ? (isPanning ? 'grabbing' : 'grab') : activeTool === 'paint' ? 'crosshair' : 'crosshair' }}
            >
              <div
                className="absolute top-1/2 left-1/2 will-change-transform"
                style={{
                  transform: `translate(-50%, -50%) translate(${panOffset.x}px, ${panOffset.y}px)`,
                  transformOrigin: 'center center'
                }}
              >
                <div
                  className="relative checkered-mask-grid border border-zinc-700 shadow-2xl overflow-hidden"
                  style={{
                    width: displayWidth,
                    height: displayHeight,
                  }}
                  onMouseDown={startDrawing}
                  onMouseMove={draw}
                  onMouseUp={stopDrawing}
                  onMouseLeave={stopDrawing}
                  onContextMenu={(e) => e.preventDefault()}
                >
                  {/* Native HTML Crop Background Image for 100% guaranteed full-color rendering */}
                  {cropDataUrl && (
                    <img
                      src={cropDataUrl}
                      alt="Crop background"
                      draggable={false}
                      className="absolute inset-0 pointer-events-none select-none z-0"
                      style={{
                        width: displayWidth,
                        height: displayHeight,
                        imageRendering: zoom > 2 ? 'pixelated' : 'auto',
                      }}
                    />
                  )}

                  {/* Crop Canvas */}
                  <canvas
                    ref={cropCanvasRef}
                    className="absolute inset-0 pointer-events-none opacity-0"
                    style={{
                      width: displayWidth,
                      height: displayHeight,
                      imageRendering: zoom > 2 ? 'pixelated' : 'auto',
                    }}
                  />

                  {/* Mask Canvas */}
                  <canvas
                    ref={maskCanvasRef}
                    className="absolute inset-0 pointer-events-none"
                    style={{
                      width: displayWidth,
                      height: displayHeight,
                      opacity: maskVisible && !previewMode ? maskOpacity : 0,
                      imageRendering: zoom > 2 ? 'pixelated' : 'auto',
                    }}
                  />

                  {/* Preview Image */}
                  {previewMode && previewDataUrl && (
                    <img
                      src={previewDataUrl}
                      alt="Inpaint preview"
                      className="absolute inset-0 pointer-events-none"
                      style={{
                        width: displayWidth,
                        height: displayHeight,
                        imageRendering: zoom > 2 ? 'pixelated' : 'auto',
                      }}
                    />
                  )}

                  {/* Brush cursor */}
                  {mousePos && activeTool === 'paint' && !isPanning && (
                    <div
                      className="absolute rounded-full border-2 border-yellow-400 pointer-events-none"
                      style={{
                        left: `${mousePos.x * zoom}px`,
                        top: `${mousePos.y * zoom}px`,
                        width: `${brushSize * zoom}px`,
                        height: `${brushSize * zoom}px`,
                        transform: 'translate(-50%, -50%)',
                        mixBlendMode: 'difference',
                      }}
                    />
                  )}

                  {/* Selection box for rect/segment */}
                  {isDrawing && (activeTool === 'rect' || activeTool === 'segment') && selectionStart && mousePos && (
                    <div
                      className={`absolute border-2 border-dashed pointer-events-none ${isRightButton ? 'border-red-400 bg-red-500/10' : activeTool === 'segment' ? 'border-cyan-300 bg-cyan-500/10' : 'border-yellow-400 bg-yellow-500/10'}`}
                      style={{
                        left: `${Math.min(selectionStart.x, mousePos.x) * zoom}px`,
                        top: `${Math.min(selectionStart.y, mousePos.y) * zoom}px`,
                        width: `${Math.abs(mousePos.x - selectionStart.x) * zoom}px`,
                        height: `${Math.abs(mousePos.y - selectionStart.y) * zoom}px`,
                      }}
                    />
                  )}

                  {/* Smart Segment loading indicator */}
                  {(isSegmenting || isDetectingText || isSaving || isPreviewing) && (
                    <div className="absolute inset-0 flex items-center justify-center bg-black/30 pointer-events-none z-10">
                      <div className="flex items-center gap-2 bg-zinc-900/90 px-4 py-2 rounded-lg border border-cyan-500/50">
                        <Loader2 size={16} className="animate-spin motion-reduce:animate-none text-cyan-400" />
                        <span className="text-xs font-bold text-cyan-300">{isSaving ? 'Saving / Cleaning…' : isPreviewing ? 'Rendering Preview…' : isDetectingText ? 'Detecting Text…' : 'Smart Segment…'}</span>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Zoom controls bottom bar */}
            <div className="flex items-center justify-between px-4 py-2 bg-[#05070C] border-t border-zinc-800">
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setZoom(current => clampZoom(current / 1.25))}
                  className="p-1.5 rounded hover:bg-zinc-800 text-slate-400 hover:text-yellow-400 transition-colors"
                  title="Zoom Out"
                >
                  <ZoomOut size={16} />
                </button>
                <span className="text-xs font-mono text-slate-300 w-16 text-center">{Math.round(zoom * 100)}%</span>
                <button
                  onClick={() => setZoom(current => clampZoom(current * 1.25))}
                  className="p-1.5 rounded hover:bg-zinc-800 text-slate-400 hover:text-yellow-400 transition-colors"
                  title="Zoom In"
                >
                  <ZoomIn size={16} />
                </button>
                <button
                  onClick={() => { setZoom(fitZoom); setPanOffset({ x: 0, y: 0 }); }}
                  className="px-2 py-1 text-xs rounded bg-zinc-900 hover:bg-zinc-800 text-slate-400 hover:text-yellow-400 transition-colors"
                  title="Fit to viewport"
                >
                  Fit
                </button>
                <button
                  onClick={() => { setZoom(1); setPanOffset({ x: 0, y: 0 }); }}
                  className="px-2 py-1 text-xs rounded bg-zinc-900 hover:bg-zinc-800 text-slate-400 hover:text-yellow-400 transition-colors"
                  title="100% zoom"
                >
                  1:1
                </button>
              </div>

              <div className="text-xs text-slate-500">
                {cropWidth} × {cropHeight} px
              </div>
            </div>
          </div>

          {/* Right Properties Panel */}
          <div className="w-64 bg-[#05070C] border-l border-zinc-800 flex flex-col overflow-y-auto">
            <div className="p-4 space-y-4">

              {/* Inpaint Model Selection - Top Priority */}
              <PropertySection title="โมเดลคลีนภาพ (Inpaint Engine)">
                <div className="space-y-1">
                  <select
                    value={selectedInpaintEngine}
                    onChange={(e) => handleInpaintEngineChange(e.target.value)}
                    disabled={editorBusy}
                    className="w-full bg-zinc-900 border border-yellow-500/40 rounded-lg px-2.5 py-1.5 text-xs text-yellow-300 focus:outline-none focus:border-yellow-400 font-bold cursor-pointer"
                    aria-label="โมเดลคลีนภาพ"
                  >
                    <option value="lama_manga" className="bg-zinc-900 text-slate-200">⚡ AnimeMangaInpainting (GPU Server / LaMa SOTA 🌟)</option>
                    <option value="lama_onnx" className="bg-zinc-900 text-slate-200">Standard LaMa ONNX (ลบเกลี้ยงมาตรฐาน)</option>
                    <option value="mat" className="bg-zinc-900 text-slate-200">MAT ONNX (ฉากซับซ้อน Transformer)</option>
                    <option value="telea" className="bg-zinc-900 text-slate-200">OpenCV Telea (Fast CPU ~5ms)</option>
                  </select>
                  <p className="text-[10px] leading-relaxed text-slate-400">⚡ เมื่อเปิด inpaint_server อยู่ ตัวเลือกบนสุดจะส่งภาพไปคำนวณบน GPU Server (PyTorch CUDA) ทันที</p>
                </div>
              </PropertySection>

              <PropertySection title="เครื่องมือปัจจุบัน">
                <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
                  <div className="text-xs font-bold text-slate-200">{activeTool === 'paint' ? 'Brush — เก็บรายละเอียด' : activeTool === 'rect' ? 'Box — เพิ่ม/ลบเป็นพื้นที่' : activeTool === 'segment' ? 'Smart Segment — ดูดวัตถุในกรอบ' : 'Pan — เลื่อนภาพ'}</div>
                  <p className="mt-1 text-[10px] leading-relaxed text-slate-500">{activeTool === 'segment' ? 'ลากครอบเฉพาะตัวอักษรที่ต้องการ ระบบจะเลือกพิกเซลด้านในกรอบ' : activeTool === 'pan' ? 'ลากเพื่อเลื่อนภาพ หรือกด Space ค้างจากเครื่องมืออื่น' : 'คลิกซ้ายค้างเพื่อเพิ่ม คลิกขวาค้างเพื่อลบ'}</p>
                </div>
                {activeTool === 'paint' && <>
                  <PropertySlider
                    label="Brush Size"
                    value={brushSize}
                    onChange={setBrushSize}
                    min={1}
                    max={80}
                    unit="px"
                  />
                  <div className="text-[10px] text-slate-500">ใช้ปุ่ม [ และ ] ปรับขนาดเร็ว</div>
                </>}
              </PropertySection>

              {/* Mask Properties */}
              <PropertySection title="Mask">
                <PropertySlider
                  label="Opacity"
                  value={Math.round(maskOpacity * 100)}
                  onChange={(val) => setMaskOpacity(val / 100)}
                  min={0}
                  max={100}
                  unit="%"
                />
                <PropertySlider
                  label="Kernel"
                  value={maskKernel}
                  onChange={handleKernelChange}
                  min={0}
                  max={56}
                  unit="px"
                />
                <div className="grid grid-cols-2 gap-2 mt-2">
                  <button
                    onClick={expandMaskByKernel}
                    disabled={maskKernel <= 0}
                    className="px-2 py-1.5 text-[11px] font-bold rounded bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 hover:bg-cyan-500/20 disabled:opacity-30 disabled:cursor-not-allowed transition-colors text-center"
                    title="ขยายขอบมาสก์ตามขนาด Kernel"
                  >
                    ขยายขอบมาสก์
                  </button>
                  <button
                    onClick={applyMagneticFill}
                    className="px-2 py-1.5 text-[11px] font-bold rounded bg-amber-500/10 border border-amber-500/30 text-amber-300 hover:bg-amber-500/20 transition-colors text-center flex items-center justify-center gap-1"
                    title="เชื่อมช่องว่างระหว่างคำในแต่ละบรรทัดเข้าด้วยกัน ไม่ให้แหว่งกลาง"
                  >
                    <span>🧲</span>
                    <span>เชื่อมเต็มแถว</span>
                  </button>
                </div>
                <p className="text-[10px] leading-relaxed text-slate-500">Kernel ขยายขอบรอบด้าน · ปุ่ม 🧲 เชื่อมช่องว่างระหว่างคำในบรรทัดเดียวกัน</p>
              </PropertySection>

              {/* Visibility */}
              <PropertySection title="Visibility">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={maskVisible}
                    onChange={(e) => setMaskVisible(e.target.checked)}
                    className="w-4 h-4 accent-yellow-500"
                  />
                   <span className="text-xs text-slate-300">แสดง Mask Overlay</span>
                 </label>
                <p className="text-[10px] text-slate-500">การซ่อน Overlay ไม่ลบข้อมูลและยังบันทึกได้ตามปกติ</p>
              </PropertySection>

              <PropertySection title="Workflow">
                <ol className="space-y-2 text-[10px] leading-relaxed text-slate-500">
                  <li><span className="text-yellow-300">1.</span> สร้างมาสก์ด้วย "สแกนตัวอักษร AI" หรือ "Smart Segment"</li>
                  <li><span className="text-yellow-300">2.</span> เก็บขอบด้วย Brush/Box และ Preview</li>
                  <li><span className="text-yellow-300">3.</span> Save & Clean เพื่ออัปเดตภาพจริง</li>
                </ol>
                 <div className="rounded border border-zinc-800 px-2 py-1.5 text-[10px] text-slate-500">Undo history: {historyLength}/{MAX_HISTORY_STATES}</div>
              </PropertySection>

            </div>
          </div>

        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-between px-4 py-3 bg-[#05070C] border-t border-zinc-800">
          <div className="flex gap-2">
            <button
              onClick={() => void handleResetToAuto()}
              disabled={editorBusy}
              className="flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-lg bg-zinc-900 border border-zinc-800 text-slate-300 hover:bg-zinc-800 disabled:opacity-40 transition-colors motion-reduce:transition-none"
              title="ย้อนกลับไปใช้มาสก์เริ่มต้นของบล็อก (Reset Default Mask)"
            >
              <RotateCcw size={14} /> คืนค่าเริ่มต้น (Reset)
            </button>
            <button
              onClick={handleClearAll}
              disabled={editorBusy}
              className="flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-lg bg-red-950/20 border border-red-900/30 text-red-300 hover:bg-red-900/40 disabled:opacity-40 transition-colors motion-reduce:transition-none"
            >
              <Trash2 size={14} /> ล้างมาสก์
            </button>
          </div>

          <div className="flex gap-2">
            <button
              onClick={requestClose}
              disabled={editorBusy}
              className="px-4 py-2 text-xs font-bold rounded-lg bg-zinc-900 border border-zinc-800 text-slate-300 hover:bg-zinc-800 disabled:opacity-40 transition-colors motion-reduce:transition-none"
            >
              ยกเลิก
            </button>
            <button
              onClick={handleFastPreviewInpaint}
              disabled={editorBusy}
              className="flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors motion-reduce:transition-none"
              title="Fast Telea Preview (~10ms)"
            >
              {isPreviewing ? <Loader2 size={14} className="animate-spin motion-reduce:animate-none" /> : <Zap size={14} />}
              Fast Preview
            </button>
            <div className="flex items-center rounded-lg border border-cyan-500/40 bg-cyan-500/10 overflow-hidden">
              <select
                value={selectedInpaintEngine}
                onChange={(e) => handleInpaintEngineChange(e.target.value)}
                disabled={editorBusy}
                className="bg-zinc-900/90 text-xs font-bold text-cyan-300 px-2 py-2 focus:outline-none cursor-pointer border-r border-cyan-500/30 hover:bg-zinc-800 transition-colors"
                title="เลือกโมเดล AI สำหรับ Preview Clean"
                aria-label="เลือกโมเดล AI สำหรับ Preview Clean"
              >
                <option value="lama_manga" className="bg-zinc-900 text-slate-200">AnimeMangaInpainting 🌟</option>
                <option value="lama_onnx" className="bg-zinc-900 text-slate-200">LaMa ONNX</option>
                <option value="mat" className="bg-zinc-900 text-slate-200">MAT ONNX</option>
                <option value="telea" className="bg-zinc-900 text-slate-200">OpenCV Telea</option>
              </select>
              <button
                onClick={handlePreviewInpaint}
                disabled={editorBusy}
                className="flex items-center gap-1.5 px-3.5 py-2 text-xs font-bold text-cyan-300 hover:bg-cyan-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors motion-reduce:transition-none"
              >
                {isPreviewing ? <Loader2 size={14} className="animate-spin motion-reduce:animate-none" /> : <Eye size={14} />}
                {isPreviewing ? 'กำลัง Preview…' : 'Preview Clean'}
              </button>
            </div>
            <button
              onClick={() => void handleSave(true)}
              disabled={editorBusy}
              className="flex items-center gap-1.5 px-4 py-2 text-xs font-bold rounded-lg bg-yellow-500 text-black border border-yellow-300 hover:bg-yellow-400 disabled:opacity-50 disabled:cursor-not-allowed transition-colors motion-reduce:transition-none shadow-[0_0_18px_rgba(234,179,8,0.12)]"
            >
              {isSaving ? <Loader2 size={14} className="animate-spin motion-reduce:animate-none" /> : <Sparkles size={14} />}
              {isSaving ? 'กำลังบันทึก…' : 'Save & Apply'}
            </button>
          </div>
        </div>

      </div>
    </div>
  );
};

// Helper Components

interface ToolButtonProps {
  icon: React.ElementType;
  label: string;
  active: boolean;
  onClick: () => void;
  title: string;
  shortcut?: string;
  disabled?: boolean;
  className?: string;
}

const ToolButton: React.FC<ToolButtonProps> = ({ icon: Icon, label, active, onClick, title, shortcut, disabled, className }) => {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`
        relative w-full h-10 px-2.5 rounded-lg flex items-center gap-2 transition-colors motion-reduce:transition-none
        ${active ? 'bg-yellow-500/15 border border-yellow-500/35 text-yellow-300' : 'border border-transparent text-slate-400 hover:bg-zinc-800 hover:text-white'}
        ${disabled ? 'opacity-30 cursor-not-allowed' : 'cursor-pointer'}
        ${className || ''}
      `}
      title={title}
    >
      <Icon size={16} className="shrink-0" />
      <span className="text-[10px] font-bold">{label}</span>
      {shortcut && (
        <span className="ml-auto text-[8px] text-slate-600 font-mono bg-zinc-900 px-1 rounded">
          {shortcut}
        </span>
      )}
    </button>
  );
};

interface PropertySectionProps {
  title: string;
  children: React.ReactNode;
}

const PropertySection: React.FC<PropertySectionProps> = ({ title, children }) => {
  return (
    <div className="space-y-2">
      <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">{title}</h3>
      <div className="space-y-2">
        {children}
      </div>
    </div>
  );
};

interface PropertySliderProps {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min: number;
  max: number;
  unit?: string;
}

const PropertySlider: React.FC<PropertySliderProps> = ({ label, value, onChange, min, max, unit }) => {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-400 font-medium">{label}</span>
        <div className="flex items-center gap-1">
          <input
            type="number"
            min={min}
            max={max}
            value={value}
            onChange={(e) => {
              const parsed = parseInt(e.target.value, 10);
              onChange(isNaN(parsed) ? min : Math.max(min, Math.min(max, parsed)));
            }}
            className="w-12 bg-zinc-950 border border-zinc-700 rounded px-1.5 py-0.5 text-xs text-right font-mono text-amber-300 focus:outline-none focus:border-amber-400"
          />
          <span className="text-xs font-mono text-slate-400">{unit}</span>
        </div>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full h-1.5 bg-zinc-900 rounded appearance-none cursor-pointer accent-yellow-500"
      />
    </div>
  );
};
