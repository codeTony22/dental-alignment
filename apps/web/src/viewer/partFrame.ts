/**
 * THE PART'S CANONICAL FRAME, derived client-side from the previewed mesh itself.
 *
 * A marked feature is (azimuth, radius, z) about the part's RIM CENTRE in the CANONICAL frame
 * — the frame `adapters/ingest.canonicalize_revolute` puts every template in. The library mesh
 * endpoint serves the catalog STL as saved, so to draw a mark on the previewed part (and to
 * send a click back as a canonical point) the viewer needs that frame. Two measured facts make
 * it derivable exactly, with no extra endpoint:
 *
 *  1. For every part in the catalog (all 12 current variants, measured 2026-07-25) the
 *     canonicalization is EXACTLY a translation by the mesh's own vertex centroid — its
 *     rotation is the identity, because the manufacturer CADs are saved axis-aligned and
 *     canonicalize_revolute prefers the file axis (it "wins ties within a 10% margin"). So
 *     canonical = raw − centroid, and the centroid is a two-line reduction over the geometry.
 *  2. The rim centre is not the origin of that frame (the coded cutout drags the vertex
 *     centroid 0.18–0.57mm sideways), so it is refitted here with the SAME construction the
 *     worker uses (domain/part_features.template_rim_centre → clock_signature's p97 top-band
 *     radius, 0.4mm ring, Kasa circle fit). Reproducing the construction rather than guessing
 *     "the file origin is the axis" keeps a drawn marker on the same landmark the server's
 *     azimuth names — the whole point of the correspondence flow.
 *
 * Fact 1 is a measurement, not an invariant, so it is GUARDED rather than trusted. The frame
 * is refused (null) unless the mesh actually reads as a revolute part standing on the FILE's
 * own +z: its rim must fit a circle (RING_FIT_MAX_RMS_MM) and its upper and lower
 * cross-sections must be concentric (AXIS_CONCENTRICITY_MAX_MM). A file saved tilted — the
 * only way canonicalize_revolute's rotation becomes non-identity — separates those two
 * centres in proportion to the tilt, and is refused from roughly 7° up. Below that the worker
 * itself keeps the file axis (it wins ties within a 10% margin), so the mapping is exact
 * anyway; the two thresholds therefore overlap in the SAFE direction — the worst outcome is
 * a part the panel declines to annotate, never a marker placed on the wrong landmark.
 *
 * ONE SUBTLETY, measured rather than assumed: the viewer's vertex set is NOT the worker's.
 * three.js's STLLoader yields the raw triangle soup (a vertex per triangle corner), while
 * trimesh MERGES duplicates on load — so the two centroids differ, by 0.007-0.035mm in xy and
 * up to 0.137mm in z across the catalog. The consequences are both negligible and bounded:
 * the fitted rim centre in ABSOLUTE coordinates agrees with the worker's to 0.0004-0.0018mm
 * (a Kasa fit does not care which frame its ring points arrived in, and the soup's duplicate
 * weighting is symmetric about the axis), so markers land on the landmark; and a click's
 * azimuth as the SERVER reads it is off by at most the xy centroid gap over the feature
 * radius — under 1.0° at a 2mm trench, well inside the server's own 11° snap window and far
 * inside operator click precision.
 *
 * Pure numerics — no three.js, no DOM — so the whole mapping is unit-testable.
 */

export type Point3 = readonly [number, number, number];

/** The mapping between the previewed mesh's own coordinates and the part's canonical frame. */
export interface PartFrame {
  /** canonical = raw − centroid (the vertex centroid of the previewed mesh). */
  readonly centroid: Point3;
  /** The fitted rim centre, canonical xy — the origin every feature azimuth is measured about. */
  readonly rimCentre: readonly [number, number];
  /** p97 top-band radius (mm) — the part's own scale, reported for the caller's copy. */
  readonly rmaxMm: number;
  /** RMS radial residual of the ring fit (mm) — how circular the rim actually read. */
  readonly ringFitRmsMm: number;
  /** Distance (mm) between the upper and lower cross-sections' fitted centres — how
   *  concentric the part is about the FILE's +z, i.e. how well fact 1 above actually holds. */
  readonly axisConcentricityMm: number;
}

/**
 * Ring-fit residual above which the frame is refused: does the rim read as a CIRCLE at all?
 * Measured across the current catalog the fit reads 0.051–0.125mm (worst: the 6030s); 0.35mm
 * leaves ~2.8x headroom over the worst real part and rejects degenerate geometry (a part
 * lying on its side reads no rim ring at all).
 */
export const RING_FIT_MAX_RMS_MM = 0.35;

/**
 * Upper-vs-lower cross-section centre disagreement above which the frame is refused: is the
 * FILE's +z actually the revolution axis? A revolute part saved on its axis has concentric
 * cross-sections, so the two fitted centres coincide; a part saved TILTED by α separates them
 * by (band separation) · tan α — the exact failure mode the centroid-only mapping cannot
 * describe, and the one a circularity test alone misses (a 12° tilt still fits a circle to
 * 0.12mm, but moves the fitted centre 0.67mm).
 *
 * Measured across the current catalog: 0.010–0.126mm (worst: zimmer-4.5-8030). 0.30mm keeps
 * 2.4x headroom over that while rejecting anything tilted beyond ~7°.
 */
export const AXIS_CONCENTRICITY_MAX_MM = 0.3;

/** Fraction of the part's height each concentricity band spans (upper: the top 40%, lower:
 *  the bottom 40%) — far enough apart for a tilt to separate their centres, each thick
 *  enough to carry a well-populated ring. */
const CONCENTRICITY_BAND_FRACTION = 0.4;

/** Vertices within this depth of the top face form the band the rim radius is read from
 *  (worker: template_rim_centre's `ztop − 1.0`). */
const TOP_BAND_DEPTH_MM = 1.0;

/** The ring the circle is fitted through: everything at radius > rmax − this (worker: 0.4). */
const RING_WIDTH_MM = 0.4;

/** Below this many ring points the fit is not trustworthy (worker: `len(ring) >= 20`). */
const MIN_RING_POINTS = 20;

/** Percentile of the top band's radii taken as the rim radius (worker: 97). */
const RMAX_PERCENTILE = 0.97;

/**
 * Linear-interpolated percentile of an ALREADY SORTED (ascending) array, p in [0, 1] —
 * numpy.percentile's default ("linear") behaviour, which is what the worker's rmax uses.
 */
export function percentileSorted(sortedAscending: readonly number[], p: number): number {
  const n = sortedAscending.length;
  if (n === 0) return 0;
  if (n === 1) return sortedAscending[0] as number;
  const rank = p * (n - 1);
  const lower = Math.floor(rank);
  const upper = Math.ceil(rank);
  const lo = sortedAscending[lower] as number;
  const hi = sortedAscending[upper] as number;
  return lower === upper ? lo : lo + (hi - lo) * (rank - lower);
}

/**
 * Kasa circle fit: the least-squares centre of points assumed to lie on one circle, solving
 * [2x, 2y, 1]·[a, b, c] = x² + y² (the worker's `_kasa`, same algebra via the 3x3 normal
 * equations). Returns null on a singular system (collinear or degenerate input).
 */
export function kasaCentre(xs: readonly number[], ys: readonly number[]): [number, number] | null {
  const n = xs.length;
  if (n < 3 || ys.length !== n) return null;
  let sx = 0;
  let sy = 0;
  let sxx = 0;
  let syy = 0;
  let sxy = 0;
  let sz = 0;
  let sxz = 0;
  let syz = 0;
  for (let i = 0; i < n; i += 1) {
    const x = xs[i] as number;
    const y = ys[i] as number;
    const z = x * x + y * y;
    sx += x;
    sy += y;
    sxx += x * x;
    syy += y * y;
    sxy += x * y;
    sz += z;
    sxz += x * z;
    syz += y * z;
  }
  // Normal equations AᵀA·sol = Aᵀb with A row = [2x, 2y, 1], b = x²+y².
  const m: number[][] = [
    [4 * sxx, 4 * sxy, 2 * sx],
    [4 * sxy, 4 * syy, 2 * sy],
    [2 * sx, 2 * sy, n],
  ];
  const rhs = [2 * sxz, 2 * syz, sz];
  const sol = solve3(m, rhs);
  if (sol === null) return null;
  return [sol[0] as number, sol[1] as number];
}

/** Gaussian elimination with partial pivoting on a 3x3 system; null when singular. */
function solve3(m: number[][], rhs: number[]): number[] | null {
  const a = m.map((row, i) => [...row, rhs[i] as number]);
  for (let col = 0; col < 3; col += 1) {
    let pivot = col;
    for (let r = col + 1; r < 3; r += 1) {
      if (Math.abs((a[r] as number[])[col] as number) > Math.abs((a[pivot] as number[])[col] as number)) {
        pivot = r;
      }
    }
    const pivotRow = a[pivot] as number[];
    if (Math.abs(pivotRow[col] as number) < 1e-12) return null;
    a[pivot] = a[col] as number[];
    a[col] = pivotRow;
    const lead = (a[col] as number[])[col] as number;
    for (let r = 0; r < 3; r += 1) {
      if (r === col) continue;
      const row = a[r] as number[];
      const factor = (row[col] as number) / lead;
      if (factor === 0) continue;
      for (let c = col; c < 4; c += 1) {
        row[c] = (row[c] as number) - factor * ((a[col] as number[])[c] as number);
      }
    }
  }
  return [0, 1, 2].map((i) => ((a[i] as number[])[3] as number) / ((a[i] as number[])[i] as number));
}

/**
 * Derive the previewed part's frame from its flat [x, y, z, x, y, z, …] vertex positions.
 * Returns null when the geometry is too sparse to fit a rim ring, or when the ring is not
 * circular enough to justify the centroid-only mapping (see RING_FIT_MAX_RMS_MM) — the caller
 * must then decline to draw or place marks rather than place them somewhere plausible.
 */
export function computePartFrame(positions: ArrayLike<number>): PartFrame | null {
  const count = Math.floor(positions.length / 3);
  if (count < MIN_RING_POINTS) return null;

  let cx = 0;
  let cy = 0;
  let cz = 0;
  for (let i = 0; i < count; i += 1) {
    cx += positions[i * 3] as number;
    cy += positions[i * 3 + 1] as number;
    cz += positions[i * 3 + 2] as number;
  }
  cx /= count;
  cy /= count;
  cz /= count;

  // Canonical coordinates are the raw ones minus that centroid; everything below is canonical.
  let ztop = -Infinity;
  for (let i = 0; i < count; i += 1) {
    const z = (positions[i * 3 + 2] as number) - cz;
    if (z > ztop) ztop = z;
  }

  const topRadii: number[] = [];
  for (let i = 0; i < count; i += 1) {
    const z = (positions[i * 3 + 2] as number) - cz;
    if (z <= ztop - TOP_BAND_DEPTH_MM) continue;
    const x = (positions[i * 3] as number) - cx;
    const y = (positions[i * 3 + 1] as number) - cy;
    topRadii.push(Math.hypot(x, y));
  }
  if (topRadii.length === 0) return null;
  topRadii.sort((a, b) => a - b);
  const rmax = percentileSorted(topRadii, RMAX_PERCENTILE);

  // The ring is taken over the WHOLE part (not just the top band) — the worker's construction.
  const ringX: number[] = [];
  const ringY: number[] = [];
  for (let i = 0; i < count; i += 1) {
    const x = (positions[i * 3] as number) - cx;
    const y = (positions[i * 3 + 1] as number) - cy;
    if (Math.hypot(x, y) <= rmax - RING_WIDTH_MM) continue;
    ringX.push(x);
    ringY.push(y);
  }
  if (ringX.length < MIN_RING_POINTS) return null;
  const centre = kasaCentre(ringX, ringY);
  if (centre === null) return null;

  let sumR = 0;
  const radii: number[] = new Array(ringX.length);
  for (let i = 0; i < ringX.length; i += 1) {
    const r = Math.hypot((ringX[i] as number) - centre[0], (ringY[i] as number) - centre[1]);
    radii[i] = r;
    sumR += r;
  }
  const meanR = sumR / radii.length;
  let sumSq = 0;
  for (const r of radii) sumSq += (r - meanR) * (r - meanR);
  const rms = Math.sqrt(sumSq / radii.length);
  if (!Number.isFinite(rms) || rms > RING_FIT_MAX_RMS_MM) return null;

  // Is the FILE's +z really the revolution axis? Two cross-sections, far apart in z, must be
  // concentric — see AXIS_CONCENTRICITY_MAX_MM for why a circularity test alone cannot say.
  const centroid: Point3 = [cx, cy, cz];
  let zMin = Infinity;
  for (let i = 0; i < count; i += 1) {
    const z = (positions[i * 3 + 2] as number) - cz;
    if (z < zMin) zMin = z;
  }
  const height = ztop - zMin;
  if (!(height > 0)) return null;
  const upper = bandRingCentre(positions, centroid, zMin + (1 - CONCENTRICITY_BAND_FRACTION) * height, ztop);
  const lower = bandRingCentre(positions, centroid, zMin, zMin + CONCENTRICITY_BAND_FRACTION * height);
  if (upper === null || lower === null) return null;
  const concentricity = Math.hypot(upper[0] - lower[0], upper[1] - lower[1]);
  if (!Number.isFinite(concentricity) || concentricity > AXIS_CONCENTRICITY_MAX_MM) return null;

  return {
    centroid,
    rimCentre: centre,
    rmaxMm: rmax,
    ringFitRmsMm: rms,
    axisConcentricityMm: concentricity,
  };
}

/**
 * The fitted centre of one z-band's outer ring (canonical coordinates) — the concentricity
 * check's instrument. Same construction as the rim centre, restricted to the band and using
 * the band's own p97 radius, so a tapered part's narrower foot still yields a well-populated
 * ring. Null when the band cannot support a fit.
 */
function bandRingCentre(
  positions: ArrayLike<number>,
  centroid: Point3,
  zLo: number,
  zHi: number,
): [number, number] | null {
  const count = Math.floor(positions.length / 3);
  const bandX: number[] = [];
  const bandY: number[] = [];
  const radii: number[] = [];
  for (let i = 0; i < count; i += 1) {
    const z = (positions[i * 3 + 2] as number) - centroid[2];
    if (z < zLo || z > zHi) continue;
    const x = (positions[i * 3] as number) - centroid[0];
    const y = (positions[i * 3 + 1] as number) - centroid[1];
    bandX.push(x);
    bandY.push(y);
    radii.push(Math.hypot(x, y));
  }
  if (radii.length < MIN_RING_POINTS) return null;
  const sorted = [...radii].sort((a, b) => a - b);
  const threshold = percentileSorted(sorted, RMAX_PERCENTILE) - RING_WIDTH_MM;
  const ringX: number[] = [];
  const ringY: number[] = [];
  for (let i = 0; i < radii.length; i += 1) {
    if ((radii[i] as number) <= threshold) continue;
    ringX.push(bandX[i] as number);
    ringY.push(bandY[i] as number);
  }
  if (ringX.length < MIN_RING_POINTS) return null;
  return kasaCentre(ringX, ringY);
}

/** A click on the previewed mesh, in the part's canonical frame — what the PUT body wants. */
export function canonicalFromRaw(frame: PartFrame, point: Point3): [number, number, number] {
  return [
    point[0] - frame.centroid[0],
    point[1] - frame.centroid[1],
    point[2] - frame.centroid[2],
  ];
}

/** The inverse mapping: where a canonical-frame point (a recorded free-point click, client
 *  ask 2026-07-26) sits on the previewed mesh, so its numbered marker lands back on the very
 *  spot that was clicked. */
export function rawFromCanonical(frame: PartFrame, point: Point3): [number, number, number] {
  return [
    point[0] + frame.centroid[0],
    point[1] + frame.centroid[1],
    point[2] + frame.centroid[2],
  ];
}

/** Where a marked feature sits on the previewed mesh: its (azimuth, radius) about the fitted
 *  rim centre, at its own z plane, mapped back out of the canonical frame. */
export function rawFromFeature(
  frame: PartFrame,
  feature: { readonly azimuthDeg: number; readonly radiusMm: number; readonly zMm: number },
): [number, number, number] {
  const rad = (feature.azimuthDeg * Math.PI) / 180;
  return [
    frame.rimCentre[0] + feature.radiusMm * Math.cos(rad) + frame.centroid[0],
    frame.rimCentre[1] + feature.radiusMm * Math.sin(rad) + frame.centroid[1],
    feature.zMm + frame.centroid[2],
  ];
}
