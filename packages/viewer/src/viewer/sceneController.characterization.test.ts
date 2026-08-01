/**
 * CHARACTERIZATION of sceneController's PURE surfaces (grill AM-5: the 1,839-line
 * controller was copied with NO test of its own — this file pins what node can genuinely
 * execute, so the copy's most-used arithmetic cannot drift silently).
 *
 * THE HONEST BOUNDARY. SceneController is an imperative WebGL controller. Its constructor
 * builds a WebGLRenderer, an OrbitControls and canvas/window listeners; its load paths
 * fetch and parse STLs into a live scene; its pointer flows raycast against loaded meshes.
 * None of that exists in this node environment, and a heavy three.js/DOM mock would test
 * the mock, not the controller. The surfaces that therefore remain BROWSER-ONLY — pinned
 * today by the frozen demo's live usage (apps/web runbook), not by any unit test:
 *
 *   - construction/dispose (renderer, controls, ResizeObserver, listener wiring);
 *   - loadStl/loadComposite (fetch + parse + scene mutation + the stale-generation bail);
 *   - every pointer flow (brush stroke, mark placement, rim points, point pick, the
 *     centre-click corridor scan, snap-to-surface);
 *   - the camera tween's per-frame stepping (requestAnimationFrame-driven) and the
 *     OrbitControls up-quaternion re-sync (setCameraUp reaches into _quat/_quatInverse).
 *
 * What IS pinned here is the arithmetic those flows share, extracted verbatim in the copy
 * (recorded divergence, copy-debt ledger row 3 — extraction was behavior-preserving,
 * verified by reading the frozen original side by side):
 *
 *   - the four anatomical view DIRECTIONS for a given frame (setAnatomyView's math);
 *   - the framing distance formula and its padding factors, and the near/far derivation
 *     every framing method shares;
 *   - the marker scale rule (selection is a size difference, never a color one);
 *   - the routing veto's composition (isToolActive — all four pointer modes);
 *   - the percentile the centre-click placement reads its corridor depth from.
 */
import { describe, expect, it } from "vitest";
import {
  SITE_FIT_PADDING,
  anatomyViewOrientation,
  anyPointerToolActive,
  clipPlanesFor,
  featureMarkerRadiusMm,
  fitDistanceMm,
  fitPaddingFor,
  percentile,
} from "./sceneController";
import { SITE_FRAME_RADIUS_MM } from "./siteRouting";
import type { AnatomyFrame } from "./anatomyOrientation";

/** The canonical arch pose: crowns up (+z), incisors toward +y. */
const CANONICAL_FRAME: AnatomyFrame = {
  centroid: [0, 0, 0],
  occlusal: [0, 0, 1],
  anterior: [0, 1, 0],
};

const ELEVATION_RAD = (18 * Math.PI) / 180;

function dot(a: readonly number[], b: readonly number[]): number {
  return a[0]! * b[0]! + a[1]! * b[1]! + a[2]! * b[2]!;
}

function length(v: readonly number[]): number {
  return Math.hypot(v[0]!, v[1]!, v[2]!);
}

describe("anatomyViewOrientation — the four presets' camera math", () => {
  it("front looks from the anterior, elevated 18° above the occlusal plane, occlusal-up", () => {
    const { direction, up } = anatomyViewOrientation(CANONICAL_FRAME, "front");
    expect(direction[0]).toBeCloseTo(0, 10);
    expect(direction[1]).toBeCloseTo(Math.cos(ELEVATION_RAD), 10);
    expect(direction[2]).toBeCloseTo(Math.sin(ELEVATION_RAD), 10);
    expect(up).toEqual([0, 0, 1]);
  });

  it("occlusal looks straight down the occlusal axis with the anterior at the top of the screen", () => {
    const { direction, up } = anatomyViewOrientation(CANONICAL_FRAME, "occlusal");
    expect(direction[0]).toBeCloseTo(0, 10);
    expect(direction[1]).toBeCloseTo(0, 10);
    expect(direction[2]).toBeCloseTo(1, 10);
    expect(up).toEqual([0, 1, 0]); // the anterior axis — that IS the screen-top roll
  });

  it("left and right are mirror images across the front view's vertical plane", () => {
    const left = anatomyViewOrientation(CANONICAL_FRAME, "left").direction;
    const right = anatomyViewOrientation(CANONICAL_FRAME, "right").direction;
    expect(left[0]).toBeCloseTo(-right[0]!, 10); // opposite lateral components
    expect(left[1]).toBeCloseTo(right[1]!, 10);
    expect(left[2]).toBeCloseTo(right[2]!, 10); // same 18° elevation
  });

  it("handedness: canonical-frame LEFT sits on +x — mirror symmetry alone cannot see a swap", () => {
    // WHY this exists (slice 3 adversarial review): flipping the lateral axis's sign in
    // anatomyViewOrientation SWAPS the left and right presets, yet every other assertion in
    // this file survived that mutation — the mirror test above is itself swap-invariant.
    // This pins the absolute sign the frozen demo shipped with: lat = (-anterior)×occlusal,
    // so "left" looks from +x in the canonical frame. An operator clicking "left" and being
    // routed to the patient's other side is exactly the silent drift AM-5 forbids.
    const left = anatomyViewOrientation(CANONICAL_FRAME, "left").direction;
    expect(left[0]).toBeCloseTo(Math.cos(ELEVATION_RAD), 10);
    expect(left[1]).toBeCloseTo(0, 10);
    expect(left[2]).toBeCloseTo(Math.sin(ELEVATION_RAD), 10);
    expect(anatomyViewOrientation(CANONICAL_FRAME, "right").direction[0]).toBeCloseTo(
      -Math.cos(ELEVATION_RAD),
      10,
    );
  });

  it("every direction is unit length (the caller scales by the framing distance)", () => {
    for (const view of ["front", "left", "right", "occlusal"] as const) {
      expect(length(anatomyViewOrientation(CANONICAL_FRAME, view).direction)).toBeCloseTo(1, 10);
    }
  });

  it("the math is frame-relative, not world-axis: a tilted frame keeps the same anatomy", () => {
    // The arch rolled 90°: occlusal now +x, anterior still +y — the tilted-scanner case
    // the presets exist for (a world-axis camera faced the BACK wall on such a scan).
    const tilted: AnatomyFrame = { centroid: [0, 0, 0], occlusal: [1, 0, 0], anterior: [0, 1, 0] };
    for (const view of ["front", "left", "right"] as const) {
      const { direction } = anatomyViewOrientation(tilted, view);
      // Elevation is measured against the frame's OWN occlusal axis, wherever it points.
      expect(dot(direction, tilted.occlusal)).toBeCloseTo(Math.sin(ELEVATION_RAD), 10);
    }
    expect(dot(anatomyViewOrientation(tilted, "front").direction, tilted.anterior)).toBeCloseTo(
      Math.cos(ELEVATION_RAD),
      10,
    );
  });
});

describe("fitDistanceMm / fitPaddingFor — the one framing formula", () => {
  it("the site framing radius at 45° FOV with the close padding sits ~40 mm out", () => {
    // reads the CONSTANT, not a literal: this characterizes the routing geometry, so
    // it must move when the radius moves rather than silently describing an old one
    const distance = fitDistanceMm(SITE_FRAME_RADIUS_MM, 45, SITE_FIT_PADDING);
    expect(distance).toBeGreaterThan(39);
    expect(distance).toBeLessThan(42); // 11 * 1.4 / sin(22.5°) ≈ 40.2
  });

  it("close is the routing padding (1.4), wide backs out to 2.4", () => {
    expect(fitPaddingFor("close")).toBe(SITE_FIT_PADDING);
    expect(fitPaddingFor("close")).toBe(1.4);
    expect(fitPaddingFor("wide")).toBe(2.4);
  });

  it("a degenerate radius clamps to the minimum working radius instead of collapsing to 0", () => {
    const distance = fitDistanceMm(0, 45, 2.4);
    expect(distance).toBeGreaterThan(0);
    expect(distance).toBeCloseTo(fitDistanceMm(0.01, 45, 2.4), 12);
  });
});

describe("clipPlanesFor — near/far derived from the framing distance", () => {
  it("brackets the subject two orders of magnitude each way", () => {
    const { near, far } = clipPlanesFor(33);
    expect(near).toBeCloseTo(0.33, 10);
    expect(far).toBeCloseTo(3300, 10);
  });

  it("near never collapses below the working floor on a tiny part preview", () => {
    expect(clipPlanesFor(0.5).near).toBe(0.01);
  });
});

describe("featureMarkerRadiusMm — selection is a size, never a color", () => {
  it("a selected marker grows (0.45 → 0.72 mm); the kind's color is untouched by selection", () => {
    expect(featureMarkerRadiusMm(undefined)).toBe(0.45);
    expect(featureMarkerRadiusMm(false)).toBe(0.45);
    expect(featureMarkerRadiusMm(true)).toBe(0.72);
    expect(featureMarkerRadiusMm(true)).toBeGreaterThan(featureMarkerRadiusMm(false));
  });
});

describe("anyPointerToolActive — the routing veto's composition", () => {
  const idle = { brush: false, mark: false, rimPoints: false, pointPick: false };

  it("no armed tool, no veto", () => {
    expect(anyPointerToolActive(idle)).toBe(false);
  });

  it("each of the four modes vetoes alone — including the brush, historically the missing one", () => {
    expect(anyPointerToolActive({ ...idle, brush: true })).toBe(true);
    expect(anyPointerToolActive({ ...idle, mark: true })).toBe(true);
    expect(anyPointerToolActive({ ...idle, rimPoints: true })).toBe(true);
    expect(anyPointerToolActive({ ...idle, pointPick: true })).toBe(true);
  });
});

describe("percentile — the centre-click corridor's depth read", () => {
  it("endpoints and a single element behave as numpy's linear percentile", () => {
    expect(percentile([7], 0.5)).toBe(7);
    expect(percentile([1, 2, 3], 0)).toBe(1);
    expect(percentile([1, 2, 3], 1)).toBe(3);
  });

  it("interpolates linearly between ranks (the p10 depth is a blend, not a snap)", () => {
    expect(percentile([0, 10], 0.5)).toBe(5);
    expect(percentile([0, 10, 20], 0.25)).toBe(5);
    // the actual centre-placement read: p10 of a sorted depth list
    expect(percentile([10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20], 0.1)).toBe(11);
  });
});
