/**
 * THE PART'S CANONICAL FRAME, derived from the previewed mesh (partFrame.ts). Everything the
 * manual-correspondence flow draws on the library part — and every click it sends back — goes
 * through this mapping, so the properties that matter are pinned here:
 *
 *  - the rim centre is FITTED, not assumed to be the mesh's centroid (on the real catalog the
 *    coded cutout drags the vertex centroid 0.18-0.57mm off the axis; a marker placed about the
 *    centroid would sit that far from the landmark its azimuth names);
 *  - a click and a drawn marker are exact inverses of each other;
 *  - a mesh that does not read as a revolute part standing on the file's own +z (a CAD saved
 *    TILTED) yields NO frame, so the caller declines to place marks rather than placing them
 *    somewhere plausible but wrong.
 *
 * The synthetic part mirrors the real catalog geometry: an outer wall at a fixed radius about
 * the AXIS, with extra vertices bunched on one side (the densely-tessellated cutout) so the
 * vertex centroid and the axis genuinely differ, exactly as they do on every real cap.
 */
import { describe, expect, it } from "vitest";
import {
  AXIS_CONCENTRICITY_MAX_MM,
  RING_FIT_MAX_RMS_MM,
  canonicalFromRaw,
  computePartFrame,
  kasaCentre,
  percentileSorted,
  rawFromCanonical,
  rawFromFeature,
} from "./partFrame";

/**
 * A cap-like vertex cloud: a wall at `radius` about (ax, ay) over a 3.5mm height, plus a dense
 * patch on one side to pull the vertex centroid off the axis. `tiltDeg` saves the part off its
 * own axis (the guard's negative case); `taper` narrows the foot, like every real cap.
 */
function makeCapCloud(opts: {
  ax: number;
  ay: number;
  az: number;
  radius: number;
  /** Degrees of tilt about x — how a CAD saved off its own axis presents. */
  tiltDeg?: number;
  /** Narrow the foot, like a real cap's tapered wall. */
  taper?: boolean;
}): number[] {
  const { ax, ay, az, radius } = opts;
  const tilt = ((opts.tiltDeg ?? 0) * Math.PI) / 180;
  const out: number[] = [];
  const push = (x: number, y: number, z: number) => {
    out.push(x, y * Math.cos(tilt) - z * Math.sin(tilt), y * Math.sin(tilt) + z * Math.cos(tilt));
  };
  const levels = 8;
  for (let l = 0; l < levels; l += 1) {
    const z = az + (l / (levels - 1)) * 3.5;
    const scale = opts.taper ? 0.78 + 0.22 * (l / (levels - 1)) : 1;
    for (let i = 0; i < 180; i += 1) {
      const th = (i / 180) * 2 * Math.PI;
      push(ax + scale * radius * Math.cos(th), ay + scale * radius * Math.sin(th), z);
    }
  }
  // The dense cutout patch: inner vertices clustered on the +x side, near the top face. These
  // are inside the ring band (they must not join the circle fit) but do move the centroid.
  for (let i = 0; i < 900; i += 1) {
    const th = (i / 900) * 0.9 - 0.45;
    const r = 0.6 * radius + 0.3 * radius * ((i % 7) / 7);
    push(ax + r * Math.cos(th), ay + r * Math.sin(th), az + 3.5 - 0.05 * ((i % 5) / 5));
  }
  return out;
}

describe("percentileSorted", () => {
  it("interpolates linearly between neighbours, like numpy's default", () => {
    // numpy.percentile([0, 1, 2, 3], 97) == 2.91
    expect(percentileSorted([0, 1, 2, 3], 0.97)).toBeCloseTo(2.91, 10);
    expect(percentileSorted([5], 0.5)).toBe(5);
    expect(percentileSorted([1, 2], 0)).toBe(1);
    expect(percentileSorted([1, 2], 1)).toBe(2);
  });
});

describe("kasaCentre", () => {
  it("recovers the centre of a circle from exact points on it", () => {
    const xs: number[] = [];
    const ys: number[] = [];
    for (let i = 0; i < 40; i += 1) {
      const th = (i / 40) * 2 * Math.PI;
      xs.push(-1.25 + 3.4 * Math.cos(th));
      ys.push(0.75 + 3.4 * Math.sin(th));
    }
    const centre = kasaCentre(xs, ys);
    expect(centre).not.toBeNull();
    expect((centre as [number, number])[0]).toBeCloseTo(-1.25, 8);
    expect((centre as [number, number])[1]).toBeCloseTo(0.75, 8);
  });

  it("recovers the centre from a PARTIAL arc — the real ring band is never the full circle", () => {
    const xs: number[] = [];
    const ys: number[] = [];
    for (let i = 0; i < 30; i += 1) {
      const th = Math.PI * 0.2 + (i / 30) * Math.PI * 1.1;
      xs.push(0.4 + 2.75 * Math.cos(th));
      ys.push(-0.2 + 2.75 * Math.sin(th));
    }
    const centre = kasaCentre(xs, ys) as [number, number];
    expect(centre[0]).toBeCloseTo(0.4, 6);
    expect(centre[1]).toBeCloseTo(-0.2, 6);
  });

  it("returns null when the system is singular (collinear points) or under-determined", () => {
    expect(kasaCentre([0, 1, 2, 3], [0, 1, 2, 3])).toBeNull();
    expect(kasaCentre([0, 1], [0, 1])).toBeNull();
  });
});

describe("computePartFrame", () => {
  const AXIS = { ax: 0.9, ay: -0.4, az: 1.2, radius: 3.0 };

  it("fits the rim centre at the AXIS, not at the vertex centroid the cutout drags away", () => {
    const frame = computePartFrame(makeCapCloud(AXIS));
    expect(frame).not.toBeNull();
    const f = frame!;
    // The dense patch really did move the centroid off the axis — otherwise this test would
    // pass for the wrong reason (a frame that simply assumed centroid == axis).
    const centroidOffAxis = Math.hypot(f.centroid[0] - AXIS.ax, f.centroid[1] - AXIS.ay);
    expect(centroidOffAxis).toBeGreaterThan(0.15);
    // The rim centre, mapped back out of the canonical frame, IS the axis.
    expect(f.rimCentre[0] + f.centroid[0]).toBeCloseTo(AXIS.ax, 4);
    expect(f.rimCentre[1] + f.centroid[1]).toBeCloseTo(AXIS.ay, 4);
    expect(f.rmaxMm).toBeGreaterThan(AXIS.radius - 0.1);
    expect(f.ringFitRmsMm).toBeLessThan(0.01);
  });

  it("refuses a frame for a part saved TILTED off its own axis", () => {
    // The one way canonicalize_revolute's rotation stops being the identity — and the one
    // case the centroid-only mapping cannot describe. A circularity test alone misses it (a
    // tilted rim still fits a circle); the upper/lower concentricity check is what sees it.
    expect(computePartFrame(makeCapCloud({ ...AXIS, tiltDeg: 8 }))).toBeNull();
    expect(computePartFrame(makeCapCloud({ ...AXIS, tiltDeg: 30 }))).toBeNull();
    expect(computePartFrame(makeCapCloud({ ...AXIS, tiltDeg: 90 }))).toBeNull();
  });

  it("accepts a TAPERED wall — every real cap narrows towards its foot", () => {
    const frame = computePartFrame(makeCapCloud({ ...AXIS, taper: true }));
    expect(frame).not.toBeNull();
    // Concentric (the taper is symmetric about the axis), so the axis check passes...
    expect(frame!.axisConcentricityMm).toBeLessThan(AXIS_CONCENTRICITY_MAX_MM);
    // ...and the fitted centre still lands on the axis to a fraction of a millimetre. It is
    // not EXACT on a taper — the ring band then spans slightly different wall radii — but that
    // bias belongs to the construction itself, which the worker runs identically on the same
    // vertices; reproducing the server's centre is the requirement, not out-computing it.
    expect(Math.abs(frame!.rimCentre[0] + frame!.centroid[0] - AXIS.ax)).toBeLessThan(0.2);
    expect(Math.abs(frame!.rimCentre[1] + frame!.centroid[1] - AXIS.ay)).toBeLessThan(0.2);
  });

  it("keeps a genuine part's residuals far below both refusal bounds", () => {
    const frame = computePartFrame(makeCapCloud(AXIS)) as NonNullable<
      ReturnType<typeof computePartFrame>
    >;
    expect(frame.ringFitRmsMm).toBeLessThan(RING_FIT_MAX_RMS_MM);
    expect(frame.axisConcentricityMm).toBeLessThan(AXIS_CONCENTRICITY_MAX_MM);
  });

  it("returns null on geometry too sparse to fit a rim", () => {
    expect(computePartFrame([0, 0, 0, 1, 1, 1])).toBeNull();
    expect(computePartFrame([])).toBeNull();
  });
});

describe("canonicalFromRaw / rawFromFeature", () => {
  const frame = computePartFrame(
    makeCapCloud({ ax: 0.9, ay: -0.4, az: 1.2, radius: 3.0 }),
  ) as NonNullable<ReturnType<typeof computePartFrame>>;

  it("places a marked feature at its azimuth/radius about the FITTED rim centre", () => {
    const raw = rawFromFeature(frame, { azimuthDeg: 90, radiusMm: 2.0, zMm: 1.5 });
    // 90° at radius 2 about the axis (0.9, -0.4): straight up in +y from the axis.
    expect(raw[0]).toBeCloseTo(0.9, 4);
    expect(raw[1]).toBeCloseTo(-0.4 + 2.0, 4);
    expect(raw[2]).toBeCloseTo(1.5 + frame.centroid[2], 10);
  });

  it("round-trips: a click mapped to canonical and read back lands on the same point", () => {
    const click: [number, number, number] = [2.4, 0.3, 4.1];
    const canonical = canonicalFromRaw(frame, click);
    const back = rawFromFeature(frame, {
      azimuthDeg:
        (Math.atan2(canonical[1] - frame.rimCentre[1], canonical[0] - frame.rimCentre[0]) * 180) /
        Math.PI,
      radiusMm: Math.hypot(canonical[0] - frame.rimCentre[0], canonical[1] - frame.rimCentre[1]),
      zMm: canonical[2],
    });
    expect(back[0]).toBeCloseTo(click[0], 10);
    expect(back[1]).toBeCloseTo(click[1], 10);
    expect(back[2]).toBeCloseTo(click[2], 10);
  });

  it("rawFromCanonical inverts canonicalFromRaw exactly — a free point's marker lands on the click", () => {
    // client ask 2026-07-26: the free-point flow stores the canonical click and must draw
    // its numbered marker back on the very spot the operator clicked
    const click: [number, number, number] = [-1.7, 2.2, 0.9];
    const back = rawFromCanonical(frame, canonicalFromRaw(frame, click));
    expect(back[0]).toBeCloseTo(click[0], 12);
    expect(back[1]).toBeCloseTo(click[1], 12);
    expect(back[2]).toBeCloseTo(click[2], 12);
  });
});
