/**
 * The zoom arithmetic. Pure — the scene that consumes it needs WebGL, which this suite
 * does not have, so what is pinned here is the part that can be wrong silently: the
 * direction of the buttons, and the band the framing can survive.
 */
import { describe, expect, it } from "vitest";
import {
  MAX_ZOOM_LEVEL,
  MAX_ZOOM_SCALE,
  MIN_ZOOM_LEVEL,
  MIN_ZOOM_SCALE,
  ZOOM_STEP,
  canZoom,
  clampZoomLevel,
  clampZoomScale,
  zoomFactorBetween,
} from "./zoom";

describe("zoomFactorBetween — which way the buttons go", () => {
  it("does nothing when the level has not moved", () => {
    expect(zoomFactorBetween(3, 3)).toBe(1);
  });

  it("SHRINKS the distance when the level rises — a higher level is zoomed IN", () => {
    /* The one thing here that is wrong silently: swap the sign and the buttons simply
       trade places, every test that only checks "the camera moved" still passes, and the
       operator finds − pushes them further away. */
    expect(zoomFactorBetween(0, 1)).toBeCloseTo(1 / ZOOM_STEP, 12);
    expect(zoomFactorBetween(0, 1)).toBeLessThan(1);
  });

  it("GROWS the distance when the level falls", () => {
    expect(zoomFactorBetween(0, -1)).toBeCloseTo(ZOOM_STEP, 12);
  });

  it("composes: two presses are one press twice, whatever the path", () => {
    // this is what lets a pane apply only the delta it missed, rather than replaying
    expect(zoomFactorBetween(0, 2)).toBeCloseTo(
      zoomFactorBetween(0, 1) * zoomFactorBetween(1, 2),
      12,
    );
  });
});

describe("clampZoomScale — the band the framing survives", () => {
  it("passes an ordinary scale through untouched", () => {
    expect(clampZoomScale(1)).toBe(1);
    expect(clampZoomScale(0.5)).toBe(0.5);
  });

  it("holds the floor, below which the pane clips its own subject away", () => {
    /* `frameOn` sets near = distance / 500. Ride the camera to the target and the
       geometry crosses the near plane — the pane goes empty and reads as a load
       failure. */
    expect(clampZoomScale(0.0001)).toBe(MIN_ZOOM_SCALE);
    expect(clampZoomScale(0)).toBe(MIN_ZOOM_SCALE);
  });

  it("holds the ceiling", () => {
    expect(clampZoomScale(1e6)).toBe(MAX_ZOOM_SCALE);
  });

  it("treats a non-finite scale as no zoom rather than as an extreme", () => {
    // NaN fails BOTH comparisons in a min/max, so an unguarded clamp returns NaN and the
    // camera position becomes NaN — a black pane with no error anywhere
    expect(clampZoomScale(Number.NaN)).toBe(1);
    expect(clampZoomScale(Number.POSITIVE_INFINITY)).toBe(MAX_ZOOM_SCALE);
  });

  it("brackets the resting scale, so level 0 is inside its own band", () => {
    expect(MIN_ZOOM_SCALE).toBeLessThan(1);
    expect(MAX_ZOOM_SCALE).toBeGreaterThan(1);
  });
});

describe("clampZoomLevel — the counter cannot outrun the camera", () => {
  it("saturates rather than recording presses the camera never answered", () => {
    /* THE DEFECT THIS EXISTS FOR (found by opening it, 2026-08-02). With only the scale
       clamped, forty presses of + parked the camera at the floor — correctly — and left
       the counter at 42. The operator then pressed − about thirty-five times before
       anything on screen moved: a button that accepts every press and answers none. */
    expect(clampZoomLevel(42)).toBe(MAX_ZOOM_LEVEL);
    expect(clampZoomLevel(-42)).toBe(MIN_ZOOM_LEVEL);
  });

  it("one step back from a saturated counter moves the camera at once", () => {
    const spent = clampZoomLevel(42);
    expect(canZoom(spent, -1)).toBe(true);
    expect(zoomFactorBetween(spent, clampZoomLevel(spent - 1))).toBeCloseTo(ZOOM_STEP, 12);
  });

  it("leaves an ordinary level alone, and treats NaN as rest", () => {
    expect(clampZoomLevel(3)).toBe(3);
    expect(clampZoomLevel(0)).toBe(0);
    expect(clampZoomLevel(Number.NaN)).toBe(0);
  });

  it("the bounds are the band's own — one more step would leave it", () => {
    // derived from MIN/MAX_ZOOM_SCALE, so a change to the band moves these with it
    expect(zoomFactorBetween(0, MAX_ZOOM_LEVEL)).toBeGreaterThanOrEqual(MIN_ZOOM_SCALE);
    expect(zoomFactorBetween(0, MAX_ZOOM_LEVEL + 1)).toBeLessThan(MIN_ZOOM_SCALE);
    expect(zoomFactorBetween(0, MIN_ZOOM_LEVEL)).toBeLessThanOrEqual(MAX_ZOOM_SCALE);
    expect(zoomFactorBetween(0, MIN_ZOOM_LEVEL - 1)).toBeGreaterThan(MAX_ZOOM_SCALE);
  });
});

describe("canZoom — when a button has nothing left to do", () => {
  it("allows both directions at rest", () => {
    expect(canZoom(0, 1)).toBe(true);
    expect(canZoom(0, -1)).toBe(true);
  });

  it("stops zooming IN once the level has reached the floor", () => {
    let level = 0;
    while (canZoom(level, 1) && level < 100) level += 1;
    expect(level).toBeLessThan(100); // it terminates
    expect(canZoom(level, 1)).toBe(false);
    expect(canZoom(level, -1)).toBe(true); // ...and the way back is always open
  });

  it("stops zooming OUT once the level has reached the ceiling", () => {
    let level = 0;
    while (canZoom(level, -1) && level > -100) level -= 1;
    expect(level).toBeGreaterThan(-100);
    expect(canZoom(level, -1)).toBe(false);
    expect(canZoom(level, 1)).toBe(true);
  });

  it("reads the LEVEL, so the two directions are never both dead", () => {
    for (const level of [-9, -3, 0, 3, 9]) {
      expect(canZoom(level, 1) || canZoom(level, -1)).toBe(true);
    }
  });
});
