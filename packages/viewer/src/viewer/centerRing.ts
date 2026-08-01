/**
 * THE CENTRE MARKER'S RIM RING — a camera-independent anchor for a floating dot.
 *
 * The client complaint (2026-08-01, twice now): "the center of the healing cap is wrong" — on
 * Intake, the orange site-centre marker (setMarkers' MarkerSpec dots) reads as sitting on the
 * cap's upper RIM instead of its centre. The stored point is not wrong (verified case
 * 295811960-neodent-gm: the site centre matches the detector proposal to 0.03mm, dead centre in
 * the occlusal view). The marker is a small sphere drawn with depthTest/depthWrite both off (see
 * sceneController's makeIndicatorVisible / MARKER_RENDER_ORDER doc) — it renders on top of
 * everything with NO occlusion and NO depth cue, because the cap's true centre is a screw-recess
 * HOLE the scanner never captured (see resolveCenterPlacement's doc in sceneController.ts): the
 * dot HOVERS over that hole at the visible top-ring height. From an oblique camera a depthless
 * floating dot projects nowhere near where the eye expects it, and nothing on screen says "this
 * is hovering, not resting" — so it reads as misplaced.
 *
 * THE FIX: draw a RING, not just the dot — a circle lying in the cap's own local top-ring plane,
 * centred on the (unmoved) stored point. A circle fit to the cap's OWN surrounding geometry
 * projects, from any angle, as an ellipse that visually coincides with the real rim right there
 * on screen; the dot sitting at its centre then reads unambiguously as "the centre of THAT rim"
 * without needing occlusion, rotation, or a second camera-relative cue. A drop-line/stem to "the
 * surface beneath" the dot was the other option on the table and is not viable here: the recess
 * is exactly the region the scanner did NOT capture, so there is no surface beneath the dot to
 * drop a line to — the only real geometry near a centre marker is the surrounding rim itself,
 * which is precisely what a ring, not a stem, is built from.
 *
 * The ring's plane is fit by PCA over mesh vertices sampled in a ball around the point (the same
 * kind of local sampling sceneController's CENTER_BALL_RADIUS_MM / CENTER_BALL_WIDE_RADIUS_MM /
 * CENTER_BALL_MIN_VERTICES already established for resolveCenterPlacement's corridor scan) —
 * never the jaw's occlusal axis as a shortcut: that proxy sits 6.2°-42.0° off the true cap axis
 * across the fleet, which at the top of that range would draw a ring that visibly does not match
 * the rim it claims to hug. The normal is deliberately UNSIGNED (a ring drawn face-on or back-on
 * looks identical, unlike a directed axis triad), so there is no sign-convention hazard here.
 *
 * Pure numerics — no three.js, no DOM — so the whole fit is unit-testable in the node
 * environment sceneController.characterization.test.ts already establishes for this file's
 * neighbours (anatomyOrientation.ts, partFrame.ts, meshCrop.ts).
 */

export type Vec3 = readonly [number, number, number];

/** A centre marker's ring fit: the local plane's unit NORMAL and the RADIUS (mm, real-world —
 *  the caller must NOT run this through the view-fraction marker scale that sizes the dot). */
export interface CenterRingFit {
  readonly normal: Vec3;
  readonly radiusMm: number;
}

/**
 * Below this many nearby vertices, a PCA fit is not trustworthy — mirrors the floor
 * sceneController's CENTER_BALL_MIN_VERTICES already established for trusting a computed value
 * from this exact kind of local ball (missing/sparse mesh: too few points to mean anything).
 */
export const CENTER_RING_MIN_VERTICES = 20;

/**
 * The eigenvalue-ratio floor for trusting a PCA-fitted plane's ORIENTATION. A rim's local
 * neighbourhood is a thin near-planar band: two comparably large in-plane eigenvalues and one
 * small out-of-plane one. When the second-largest eigenvalue is small relative to the largest,
 * the sampled neighbourhood reads as a LINE, not a disc — no particular plane through a line is
 * any more justified than another, so drawing a ring there would be a guess wearing the
 * costume of a measurement. 0.12 keeps real, roughly-circular rim samples (measured well above
 * this on synthetic and real-shaped test data) comfortably clear while rejecting genuinely
 * degenerate/linear samples.
 */
export const CENTER_RING_MIN_SPREAD_RATIO = 0.12;

function sub3(a: Vec3, b: Vec3): Vec3 {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}
function dot3(a: Vec3, b: Vec3): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}
function cross3(a: Vec3, b: Vec3): Vec3 {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
}
function length3(v: Vec3): number {
  return Math.hypot(v[0], v[1], v[2]);
}
function normalize3(v: Vec3): Vec3 {
  const len = length3(v);
  return len > 1e-12 ? [v[0] / len, v[1] / len, v[2] / len] : [0, 0, 0];
}
function scale3(v: Vec3, s: number): Vec3 {
  return [v[0] * s, v[1] * s, v[2] * s];
}

/** A symmetric 3x3 matrix as its 6 distinct entries. */
interface Sym3 {
  readonly xx: number;
  readonly yy: number;
  readonly zz: number;
  readonly xy: number;
  readonly xz: number;
  readonly yz: number;
}
function applySym3(m: Sym3, v: Vec3): Vec3 {
  return [
    m.xx * v[0] + m.xy * v[1] + m.xz * v[2],
    m.xy * v[0] + m.yy * v[1] + m.yz * v[2],
    m.xz * v[0] + m.yz * v[1] + m.zz * v[2],
  ];
}

/** A unit vector reliably NOT parallel to `v`, for seeding a second power iteration or building
 *  an in-plane basis — picks whichever world axis `v` is LEAST aligned with, so the cross
 *  product is never near-degenerate regardless of `v`'s own direction. */
function perpendicularSeed(v: Vec3): Vec3 {
  const alt: Vec3 = Math.abs(v[2]) < 0.9 ? [0, 0, 1] : [0, 1, 0];
  const seed = cross3(v, alt);
  return length3(seed) > 1e-9 ? normalize3(seed) : normalize3(cross3(v, [1, 0, 0]));
}

/**
 * Power iteration for the dominant (largest-|eigenvalue|) eigenpair of a symmetric matrix. A
 * fixed iteration count (no convergence tolerance) is simpler and exact enough at this scale —
 * a 3x3 covariance built from a few dozen mesh vertices, not a large ill-conditioned system.
 */
function dominantEigenpair(m: Sym3, seed: Vec3): { readonly vector: Vec3; readonly value: number } {
  let v = normalize3(seed);
  if (length3(v) === 0) v = [1, 0, 0];
  for (let i = 0; i < 50; i += 1) {
    const next = applySym3(m, v);
    const normalized = normalize3(next);
    if (length3(normalized) === 0) break; // the remaining matrix is ~zero — nothing left to find
    v = normalized;
  }
  const value = dot3(v, applySym3(m, v)); // Rayleigh quotient
  return { vector: v, value };
}

/** M with the `vector`/`value` eigenpair's contribution removed, so a second power iteration
 *  converges to the NEXT-largest eigenpair instead of the same one. */
function deflate(m: Sym3, vector: Vec3, value: number): Sym3 {
  return {
    xx: m.xx - value * vector[0] * vector[0],
    yy: m.yy - value * vector[1] * vector[1],
    zz: m.zz - value * vector[2] * vector[2],
    xy: m.xy - value * vector[0] * vector[1],
    xz: m.xz - value * vector[0] * vector[2],
    yz: m.yz - value * vector[1] * vector[2],
  };
}

/** Linear-interpolated median of an unsorted numeric array (same "rank = p*(n-1), interpolate"
 *  convention as sceneController's percentile/partFrame's percentileSorted — duplicated rather
 *  than imported so this module stays a standalone pure leaf, matching this file family's own
 *  established precedent). */
function median(values: readonly number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const n = sorted.length;
  if (n === 1) return sorted[0] as number;
  const rank = 0.5 * (n - 1);
  const lower = Math.floor(rank);
  const upper = Math.ceil(rank);
  const lo = sorted[lower] as number;
  const hi = sorted[upper] as number;
  return lower === upper ? lo : lo + (hi - lo) * (rank - lower);
}

/**
 * Fit the local plane a centre marker's dot should visually "hug", from mesh vertices sampled
 * around it (see this module's header). Returns null — draw the plain sphere, no ring — when
 * the neighbourhood cannot honestly justify one: too few vertices (missing/sparse mesh,
 * CENTER_RING_MIN_VERTICES), a neighbourhood so nearly a single point that no variance exists at
 * all, or one so nearly LINEAR that no particular plane through it is any better justified than
 * another (CENTER_RING_MIN_SPREAD_RATIO).
 *
 * `center` is the marker's own (unmoved, already-correct) point — the ring is centred on it, NOT
 * on `nearbyVertices`' own centroid, which may sit slightly off (the vertices are sampled from
 * whatever real geometry survived scanning around the point, not symmetric by construction).
 *
 * PCA over the sample: the ring's normal is the direction the neighbourhood spreads LEAST along
 * — two power iterations + deflation find the two largest-variance (in-plane) directions, and
 * their cross product IS the third (smallest-variance) eigenvector, exact because a real
 * symmetric matrix's eigenvectors are mutually orthogonal — no explicit eigensolver needed.
 */
export function fitCenterRingPlane(center: Vec3, nearbyVertices: readonly Vec3[]): CenterRingFit | null {
  const count = nearbyVertices.length;
  if (count < CENTER_RING_MIN_VERTICES) return null;

  let cx = 0;
  let cy = 0;
  let cz = 0;
  for (const v of nearbyVertices) {
    cx += v[0];
    cy += v[1];
    cz += v[2];
  }
  const centroid: Vec3 = [cx / count, cy / count, cz / count];

  let xx = 0;
  let yy = 0;
  let zz = 0;
  let xy = 0;
  let xz = 0;
  let yz = 0;
  for (const v of nearbyVertices) {
    const d = sub3(v, centroid);
    xx += d[0] * d[0];
    yy += d[1] * d[1];
    zz += d[2] * d[2];
    xy += d[0] * d[1];
    xz += d[0] * d[2];
    yz += d[1] * d[2];
  }
  const cov: Sym3 = { xx: xx / count, yy: yy / count, zz: zz / count, xy: xy / count, xz: xz / count, yz: yz / count };

  const first = dominantEigenpair(cov, [1, 0, 0]);
  if (!(first.value > 1e-12)) return null; // the whole ball collapses to (near) a single point

  const second = dominantEigenpair(deflate(cov, first.vector, first.value), perpendicularSeed(first.vector));
  if (!(second.value >= first.value * CENTER_RING_MIN_SPREAD_RATIO)) return null; // reads as a line, not a disc

  const normal = normalize3(cross3(first.vector, second.vector));
  if (length3(normal) < 1e-6) return null; // first/second collapsed near-parallel — no plane

  const radii: number[] = [];
  for (const v of nearbyVertices) {
    const fromCenter = sub3(v, center);
    const along = dot3(fromCenter, normal);
    const inPlane = sub3(fromCenter, scale3(normal, along));
    radii.push(length3(inPlane));
  }
  const radiusMm = median(radii);
  if (!(radiusMm > 0)) return null;

  return { normal, radiusMm };
}
