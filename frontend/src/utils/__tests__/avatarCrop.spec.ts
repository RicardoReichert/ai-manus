import { describe, it, expect } from 'vitest';
import { fitCoverScale, clampOffset, computeCropSourceRect } from '../avatarCrop';

describe('fitCoverScale', () => {
  it('scales a wider-than-viewport image so its height fills the viewport', () => {
    // 400x200 image, 100x100 viewport -> must scale by 0.5 (100/200) to cover height
    expect(fitCoverScale(400, 200, 100)).toBeCloseTo(0.5);
  });

  it('scales a taller-than-viewport image so its width fills the viewport', () => {
    // 200x400 image, 100x100 viewport -> must scale by 0.5 (100/200) to cover width
    expect(fitCoverScale(200, 400, 100)).toBeCloseTo(0.5);
  });

  it('a square image at viewport size scales to exactly 1', () => {
    expect(fitCoverScale(100, 100, 100)).toBeCloseTo(1);
  });
});

describe('clampOffset', () => {
  it('keeps the displayed image covering the viewport (no blank edges), clamping each axis independently', () => {
    // displayedWidth 150, displayedHeight 250, 100 viewport:
    // x must stay within [-50, 0], y must stay within [-150, 0]
    const result = clampOffset({
      offsetX: 10, offsetY: -200, displayedWidth: 150, displayedHeight: 250, viewportSize: 100,
    });
    expect(result.x).toBe(0);    // clamped up from 10 (would show blank left/top edge)
    expect(result.y).toBe(-150); // clamped down from -200 (would show blank bottom edge)
  });

  it('passes through an offset that is already within bounds', () => {
    const result = clampOffset({
      offsetX: -20, offsetY: -30, displayedWidth: 150, displayedHeight: 150, viewportSize: 100,
    });
    expect(result).toEqual({ x: -20, y: -30 });
  });
});

describe('computeCropSourceRect', () => {
  it('computes the full image as the source rect at zoom=1, no pan, square image', () => {
    // 200x200 image, 100 viewport, baseScale=0.5 (cover), zoom=1, no offset
    const rect = computeCropSourceRect({
      imageWidth: 200, imageHeight: 200, viewportSize: 100,
      offsetX: 0, offsetY: 0, zoom: 1,
    });
    expect(rect.sx).toBeCloseTo(0);
    expect(rect.sy).toBeCloseTo(0);
    expect(rect.sSize).toBeCloseTo(200); // whole image is the source at scale 0.5
  });

  it('zooming in shrinks the source rect (crops in tighter)', () => {
    const rect = computeCropSourceRect({
      imageWidth: 200, imageHeight: 200, viewportSize: 100,
      offsetX: 0, offsetY: 0, zoom: 2,
    });
    expect(rect.sSize).toBeCloseTo(100); // 2x zoom -> half the source region
  });

  it('a pan offset shifts the source rect origin', () => {
    // scale = baseScale(0.5) * zoom(1) = 0.5; offsetX -20 CSS px -> source shifts by 20/0.5 = 40
    const rect = computeCropSourceRect({
      imageWidth: 200, imageHeight: 200, viewportSize: 100,
      offsetX: -20, offsetY: 0, zoom: 1,
    });
    expect(rect.sx).toBeCloseTo(40);
    expect(rect.sy).toBeCloseTo(0);
  });
});
