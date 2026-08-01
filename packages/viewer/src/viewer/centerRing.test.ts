/**
 * fitCenterRingPlane — the centre marker's camera-independent rim-ring anchor (client
 * complaint 2026-08-01: the orange site-centre marker reads as sitting on the cap's rim
 * instead of its centre, because the dot floats over the unscanned recess with no depth
 * cue). See centerRing.ts's header for the full diagnosis and why a ring, not a drop-line.
 */
import { describe, expect, it } from "vitest";
import {
  CENTER_RING_MIN_SPREAD_RATIO,
  CENTER_RING_MIN_VERTICES,
  fitCenterRingPlane,
  type Vec3,
} from "./centerRing";

/** N points evenly spaced on a circle of `radius` about the origin, in the plane spanned by
 *  `u`/`v` (both assumed unit and mutually orthogonal), i.e. with normal `u x v`. */
function circlePoints(radius: number, u: Vec3, v: Vec3, n = 48): Vec3[] {
  const points: Vec3[] = [];
  for (let i = 0; i < n; i += 1) {
    const theta = (i / n) * Math.PI * 2;
    const c = Math.cos(theta) * radius;
    const s = Math.sin(theta) * radius;
    points.push([u[0] * c + v[0] * s, u[1] * c + v[1] * s, u[2] * c + v[2] * s]);
  }
  return points;
}

function normalize(v: Vec3): Vec3 {
  const len = Math.hypot(v[0], v[1], v[2]);
  return [v[0] / len, v[1] / len, v[2] / len];
}

function absDot(a: Vec3, b: Vec3): number {
  return Math.abs(a[0] * b[0] + a[1] * b[1] + a[2] * b[2]);
}

describe("fitCenterRingPlane — degrades honestly before it guesses", () => {
  it("refuses a sparse ball (below CENTER_RING_MIN_VERTICES) rather than fit noise", () => {
    const points = circlePoints(3, [1, 0, 0], [0, 1, 0], CENTER_RING_MIN_VERTICES - 1);
    expect(fitCenterRingPlane([0, 0, 0], points)).toBeNull();
  });

  it("accepts exactly at the vertex floor", () => {
    const points = circlePoints(3, [1, 0, 0], [0, 1, 0], CENTER_RING_MIN_VERTICES);
    expect(fitCenterRingPlane([0, 0, 0], points)).not.toBeNull();
  });

  it("refuses a neighbourhood that reads as a LINE, not a disc — no plane through a line is any more justified than another", () => {
    // 30 points strung along the x axis: plenty of vertices, but only one spread direction.
    const line: Vec3[] = Array.from({ length: 30 }, (_, i) => [i * 0.1, 0, 0]);
    expect(fitCenterRingPlane([1, 0, 0], line)).toBeNull();
  });

  it("refuses a neighbourhood collapsed to (near) one point", () => {
    const cluster: Vec3[] = Array.from({ length: 30 }, () => [0, 0, 0]);
    expect(fitCenterRingPlane([0, 0, 0], cluster)).toBeNull();
  });
});

describe("fitCenterRingPlane — the fitted plane, on an unambiguous disc", () => {
  it("recovers the normal and radius of a flat circle in the XY plane exactly", () => {
    const fit = fitCenterRingPlane([0, 0, 0], circlePoints(3, [1, 0, 0], [0, 1, 0]));
    expect(fit).not.toBeNull();
    // Sign-agnostic: a ring drawn face-on or back-on looks identical (see the module doc).
    expect(absDot(fit!.normal, [0, 0, 1])).toBeCloseTo(1, 6);
    expect(fit!.radiusMm).toBeCloseTo(3, 6);
  });

  it("recovers a TILTED plane's own normal — never the world/occlusal axis as a proxy", () => {
    // 30° off world-z: exactly the kind of tilt an occlusal-axis shortcut would get wrong,
    // per the module doc's measured 6.2°-42.0° fleet spread.
    const theta = (30 * Math.PI) / 180;
    const u: Vec3 = [Math.cos(theta), 0, Math.sin(theta)];
    const v: Vec3 = [0, 1, 0];
    const expectedNormal = normalize([-Math.sin(theta), 0, Math.cos(theta)]); // u x v
    const fit = fitCenterRingPlane([0, 0, 0], circlePoints(2.5, u, v));
    expect(fit).not.toBeNull();
    expect(absDot(fit!.normal, expectedNormal)).toBeGreaterThan(0.999);
    expect(absDot(fit!.normal, [0, 0, 1])).toBeLessThan(0.87); // NOT the world/occlusal axis
    expect(fit!.radiusMm).toBeCloseTo(2.5, 6);
  });

  it("centres the ring on the GIVEN point, not the sampled vertices' own centroid", () => {
    // Same circle as the exact-recovery case, but the marker's point is offset 0.5mm from the
    // true circle centre — the honest thing resolveCenterPlacement's estimate can produce.
    // Every sampled point sits exactly 3mm from the true centre, so by the triangle
    // inequality every point is within [3-0.5, 3+0.5] of the OFFSET point — a radius outside
    // that band could only come from measuring against the vertices' own centroid instead.
    const points = circlePoints(3, [1, 0, 0], [0, 1, 0]);
    const fit = fitCenterRingPlane([0.5, 0, 0], points);
    expect(fit).not.toBeNull();
    expect(fit!.radiusMm).toBeGreaterThan(2.5);
    expect(fit!.radiusMm).toBeLessThan(3.5);
    expect(fit!.radiusMm).not.toBeCloseTo(3, 3); // the recentred-on-point case is NOT exact-3
  });

  it("the spread-ratio floor separates a real disc from a barely-thickened line", () => {
    // A circle's two in-plane eigenvalues are exactly equal (ratio 1) — comfortably clear
    // of CENTER_RING_MIN_SPREAD_RATIO — and this pins that constant's own scale so a future
    // change to it is a deliberate edit, not a silent drift.
    expect(CENTER_RING_MIN_SPREAD_RATIO).toBeLessThan(1);
    expect(CENTER_RING_MIN_SPREAD_RATIO).toBeGreaterThan(0);
  });
});
