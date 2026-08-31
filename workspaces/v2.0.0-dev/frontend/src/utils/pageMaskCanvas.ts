export const PAGE_MASK_COLOR = { red: 239, green: 68, blue: 68, alpha: 230 } as const;
// Keep Mark Mode responsive on long pages. The saved mask is normalized back
// to source dimensions by the API, so this is only an interaction buffer.
export const MAX_MASK_WORKING_PIXELS = 4_000_000;
export type PageMaskTool = 'brush' | 'eraser' | 'box';

export interface CanvasPoint {
  x: number;
  y: number;
}

export function shouldEraseMask(tool: PageMaskTool, pointerButton: number): boolean {
  return tool === 'eraser' || pointerButton === 2;
}

export function pointerToCanvasPoint(
  clientX: number,
  clientY: number,
  rect: Pick<DOMRect, 'left' | 'top' | 'width' | 'height'>,
  canvasWidth: number,
  canvasHeight: number,
): CanvasPoint {
  if (rect.width <= 0 || rect.height <= 0) return { x: 0, y: 0 };
  return {
    x: (clientX - rect.left) * (canvasWidth / rect.width),
    y: (clientY - rect.top) * (canvasHeight / rect.height),
  };
}

export function resolveMaskWorkingDimensions(
  width: number,
  height: number,
  maxPixels = MAX_MASK_WORKING_PIXELS,
): { width: number; height: number } {
  const sourceWidth = Math.max(1, Math.round(width));
  const sourceHeight = Math.max(1, Math.round(height));
  const pixelCount = sourceWidth * sourceHeight;
  if (pixelCount <= maxPixels) return { width: sourceWidth, height: sourceHeight };
  const scale = Math.sqrt(maxPixels / pixelCount);
  return {
    width: Math.max(1, Math.round(sourceWidth * scale)),
    height: Math.max(1, Math.round(sourceHeight * scale)),
  };
}

export function binaryMaskToOverlay(imageData: ImageData): ImageData {
  const pixels = imageData.data;
  for (let index = 0; index < pixels.length; index += 4) {
    const selected = pixels[index + 3] > 12
      && Math.max(pixels[index], pixels[index + 1], pixels[index + 2]) > 12;
    pixels[index] = PAGE_MASK_COLOR.red;
    pixels[index + 1] = PAGE_MASK_COLOR.green;
    pixels[index + 2] = PAGE_MASK_COLOR.blue;
    pixels[index + 3] = selected ? PAGE_MASK_COLOR.alpha : 0;
  }
  return imageData;
}

export function drawMaskSegment(
  context: CanvasRenderingContext2D,
  from: CanvasPoint,
  to: CanvasPoint,
  brushSize: number,
  erase: boolean,
): void {
  context.save();
  context.globalCompositeOperation = erase ? 'destination-out' : 'source-over';
  context.strokeStyle = `rgba(${PAGE_MASK_COLOR.red}, ${PAGE_MASK_COLOR.green}, ${PAGE_MASK_COLOR.blue}, ${PAGE_MASK_COLOR.alpha / 255})`;
  context.lineWidth = brushSize;
  context.lineCap = 'round';
  context.lineJoin = 'round';
  context.beginPath();
  context.moveTo(from.x, from.y);
  context.lineTo(to.x, to.y);
  context.stroke();
  context.restore();
}

export async function renderMaskDataUrl(
  canvas: HTMLCanvasElement,
  maskDataUrl: string,
  width?: number,
  height?: number,
  isOverlay = false,
): Promise<void> {
  const image = await new Promise<HTMLImageElement>((resolve, reject) => {
    const nextImage = new Image();
    nextImage.onload = () => resolve(nextImage);
    nextImage.onerror = () => reject(new Error('Unable to decode the page mask'));
    nextImage.src = maskDataUrl;
  });

  const working = resolveMaskWorkingDimensions(
    width || image.naturalWidth || image.width,
    height || image.naturalHeight || image.height,
  );
  canvas.width = working.width;
  canvas.height = working.height;
  const context = canvas.getContext('2d', { willReadFrequently: true });
  if (!context) throw new Error('Unable to initialize the page mask canvas');
  context.clearRect(0, 0, canvas.width, canvas.height);
  context.drawImage(image, 0, 0, canvas.width, canvas.height);
  if (!isOverlay) {
    const overlay = binaryMaskToOverlay(context.getImageData(0, 0, canvas.width, canvas.height));
    context.putImageData(overlay, 0, 0);
  }
}

export function initializeEmptyMaskCanvas(
  canvas: HTMLCanvasElement,
  width: number,
  height: number,
): void {
  const working = resolveMaskWorkingDimensions(width, height);
  canvas.width = working.width;
  canvas.height = working.height;
  canvas.getContext('2d', { willReadFrequently: true })?.clearRect(0, 0, canvas.width, canvas.height);
}
