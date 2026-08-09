/**
 * Pure geometry for the avatar crop dialog. No DOM/canvas access here —
 * kept separate so the math is unit-testable without mounting a component.
 *
 * Model: a square "viewport" of CSS px `viewportSize` shows a circular crop
 * guide. The source image is displayed inside it at `fitCoverScale * zoom`,
 * offset by (offsetX, offsetY) CSS px from the viewport's top-left. Zoom
 * ranges from 1 (image just covers the viewport) upward.
 */

/** Scale factor so the image's shorter dimension exactly fills the viewport
 * (cover behavior — same as CSS `object-fit: cover`). */
export function fitCoverScale(imageWidth: number, imageHeight: number, viewportSize: number): number {
  return Math.max(viewportSize / imageWidth, viewportSize / imageHeight);
}

/** Clamp a pan offset so the displayed image always fully covers the
 * viewport (no blank space at any edge). `displayedWidth`/`displayedHeight`
 * are the image's rendered CSS px size at the current zoom — kept separate
 * (rather than a single `displayedSize`) because at `fitCoverScale` only
 * one axis is exactly viewport-sized; the other is typically larger, so
 * each axis needs its own clamp range. */
export function clampOffset(params: {
  offsetX: number;
  offsetY: number;
  displayedWidth: number;
  displayedHeight: number;
  viewportSize: number;
}): { x: number; y: number } {
  const clampAxis = (offset: number, displayedSize: number) => {
    const min = params.viewportSize - displayedSize; // negative or zero
    return Math.min(0, Math.max(min, offset));
  };
  return {
    x: clampAxis(params.offsetX, params.displayedWidth),
    y: clampAxis(params.offsetY, params.displayedHeight),
  };
}

/** Given the current pan/zoom state, compute the square source rectangle
 * (in original image pixel coordinates) that the viewport is showing —
 * this is what gets drawn into the output canvas. */
export function computeCropSourceRect(params: {
  imageWidth: number;
  imageHeight: number;
  viewportSize: number;
  offsetX: number;
  offsetY: number;
  zoom: number;
}): { sx: number; sy: number; sSize: number } {
  const scale = fitCoverScale(params.imageWidth, params.imageHeight, params.viewportSize) * params.zoom;
  return {
    sx: -params.offsetX / scale,
    sy: -params.offsetY / scale,
    sSize: params.viewportSize / scale,
  };
}
