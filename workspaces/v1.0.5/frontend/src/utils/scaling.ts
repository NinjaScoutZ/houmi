/**
 * Converts a dimension or coordinate from original image space (database) to canvas logical space.
 */
export const originalToCanvasSize = (originalSize: number, scaleFactor: number): number => {
  if (scaleFactor <= 0) return originalSize;
  return originalSize / scaleFactor;
};

/**
 * Converts a dimension or coordinate from canvas logical space to original image space (database).
 */
export const canvasToOriginalSize = (canvasSize: number, scaleFactor: number): number => {
  if (scaleFactor <= 0) return canvasSize;
  return canvasSize * scaleFactor;
};

/**
 * Backward compatibility alias: sceneFontSizeToOriginal converts canvas scene font size to original database size.
 */
export const sceneFontSizeToOriginal = canvasToOriginalSize;
