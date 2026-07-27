/**
 * Anatomical orientation of a dental arch scan, from geometry alone (client ask 2026-07-14:
 * "prepare the 3d view to face the front camera and make easy, safe the step of looking for
 * the right face of the mouth"). Doctor scans arrive in arbitrary scanner frames — the upper
 * 276794487 scan is tilted enough that a world-axis camera showed the BACK wall, and oblique
 * default views are exactly where rim-border clicks slip past the rim edge (measured: the
 * redo's one bad click sat 0.9mm up the +x slope).
 *
 * Pure math, no THREE dependency — unit-tested against synthetic arches under arbitrary
 * rigid transforms; the sceneController consumes the frame for camera presets.
 *
 * The frame:
 * - `occlusal`: the arch is a shallow sheet, so its smallest-variance principal axis is the
 *   crowns direction. Sign is resolved by the mean vertex normal — an intraoral scanner only
 *   captures the EXPOSED (occlusal-facing) surface, so the average normal points at the
 *   scanned side. Without normals the sign stays as-computed (callers still get a valid axis).
 * - `anterior`: the in-plane axis toward the incisors. A dental arch is a U: at the apex
 *   (front teeth) the points cluster near the midline, at the open end (molars) they split
 *   into two lobes far from the midline — so the anterior end of the antero-posterior axis is
 *   the one whose extreme slice has the SMALLER lateral spread.
 */

export interface AnatomyFrame {
  readonly centroid: readonly [number, number, number];
  /** Unit vector toward the crowns / scanned side (the "up" of an occlusal view). */
  readonly occlusal: readonly [number, number, number];
  /** Unit vector toward the incisors (the front of the mouth), orthogonal to `occlusal`. */
  readonly anterior: readonly [number, number, number];
}

// Subsample cap: the frame is a bulk statistic; 100-160k-vertex scans don't need every vertex.
const MAX_SAMPLES = 20000;
// An arch is a SHEET: its thinnest axis carries far less variance than the in-plane axes. A
// blob-like part (or a cap template preview) has no such separation — refuse a frame there
// rather than orient the camera off noise. Ratio of smallest to middle eigenvalue.
const MAX_FLATNESS_RATIO = 0.6;
// Slice depth (fraction of points at each antero-posterior extreme) used for the U-apex test.
const APEX_SLICE_FRACTION = 0.25;
const MIN_POINTS = 300;

type Vec = [number, number, number];

function normalize(v: Vec): Vec | null {
  const n = Math.hypot(v[0], v[1], v[2]);
  if (n < 1e-12) return null;
  return [v[0] / n, v[1] / n, v[2] / n];
}

/**
 * Eigen-decomposition of a symmetric 3x3 matrix by cyclic Jacobi rotations — ~40 lines beats
 * pulling a linear-algebra dependency into the bundle for one covariance matrix. Returns
 * eigenvalues ascending with matching unit eigenvectors (columns).
 */
function symmetricEigen3(m: readonly number[][]): { values: number[]; vectors: Vec[] } {
  // working copies
  const a = [
    [m[0]![0]!, m[0]![1]!, m[0]![2]!],
    [m[1]![0]!, m[1]![1]!, m[1]![2]!],
    [m[2]![0]!, m[2]![1]!, m[2]![2]!],
  ];
  const v = [
    [1, 0, 0],
    [0, 1, 0],
    [0, 0, 1],
  ];
  for (let sweep = 0; sweep < 32; sweep += 1) {
    let off = 0;
    for (let p = 0; p < 3; p += 1) {
      for (let q = p + 1; q < 3; q += 1) off += a[p]![q]! * a[p]![q]!;
    }
    if (off < 1e-18) break;
    for (let p = 0; p < 3; p += 1) {
      for (let q = p + 1; q < 3; q += 1) {
        if (Math.abs(a[p]![q]!) < 1e-15) continue;
        const theta = (a[q]![q]! - a[p]![p]!) / (2 * a[p]![q]!);
        const t = Math.sign(theta || 1) / (Math.abs(theta) + Math.sqrt(theta * theta + 1));
        const c = 1 / Math.sqrt(t * t + 1);
        const s = t * c;
        for (let k = 0; k < 3; k += 1) {
          const akp = a[k]![p]!;
          const akq = a[k]![q]!;
          a[k]![p] = c * akp - s * akq;
          a[k]![q] = s * akp + c * akq;
        }
        for (let k = 0; k < 3; k += 1) {
          const apk = a[p]![k]!;
          const aqk = a[q]![k]!;
          a[p]![k] = c * apk - s * aqk;
          a[q]![k] = s * apk + c * aqk;
        }
        for (let k = 0; k < 3; k += 1) {
          const vkp = v[k]![p]!;
          const vkq = v[k]![q]!;
          v[k]![p] = c * vkp - s * vkq;
          v[k]![q] = s * vkp + c * vkq;
        }
      }
    }
  }
  const order = [0, 1, 2].sort((i, j) => a[i]![i]! - a[j]![j]!);
  return {
    values: order.map((i) => a[i]![i]!),
    vectors: order.map((i) => [v[0]![i]!, v[1]![i]!, v[2]![i]!] as Vec),
  };
}

/**
 * Compute the anatomical frame from xyz position triples (and optional matching normal
 * triples for the occlusal sign). Returns null when the cloud does not read as an arch sheet
 * (too few points, or no clearly thinnest axis) — callers fall back to their default framing.
 */
export function computeAnatomyFrame(
  positions: ArrayLike<number>,
  normals?: ArrayLike<number>,
): AnatomyFrame | null {
  const totalPoints = Math.floor(positions.length / 3);
  if (totalPoints < MIN_POINTS) return null;
  const stride = Math.max(1, Math.floor(totalPoints / MAX_SAMPLES));

  // centroid
  let cx = 0;
  let cy = 0;
  let cz = 0;
  let n = 0;
  for (let i = 0; i < totalPoints; i += stride) {
    cx += positions[i * 3] as number;
    cy += positions[i * 3 + 1] as number;
    cz += positions[i * 3 + 2] as number;
    n += 1;
  }
  cx /= n;
  cy /= n;
  cz /= n;

  // covariance (symmetric)
  let xx = 0;
  let xy = 0;
  let xz = 0;
  let yy = 0;
  let yz = 0;
  let zz = 0;
  for (let i = 0; i < totalPoints; i += stride) {
    const dx = (positions[i * 3] as number) - cx;
    const dy = (positions[i * 3 + 1] as number) - cy;
    const dz = (positions[i * 3 + 2] as number) - cz;
    xx += dx * dx;
    xy += dx * dy;
    xz += dx * dz;
    yy += dy * dy;
    yz += dy * dz;
    zz += dz * dz;
  }
  const cov = [
    [xx / n, xy / n, xz / n],
    [xy / n, yy / n, yz / n],
    [xz / n, yz / n, zz / n],
  ];
  const eig = symmetricEigen3(cov);
  const [thin, middle] = [eig.values[0]!, eig.values[1]!];
  if (!(middle > 1e-9) || thin / middle > MAX_FLATNESS_RATIO) return null;

  let occ = eig.vectors[0]!;
  const ap = eig.vectors[1]!; // antero-posterior candidate (middle variance)
  const lateral = eig.vectors[2]!; // left-right (largest variance)

  // occlusal sign: the scanner captured the exposed side, so the mean normal points there
  if (normals && normals.length >= totalPoints * 3) {
    let s = 0;
    for (let i = 0; i < totalPoints; i += stride) {
      s +=
        (normals[i * 3] as number) * occ[0] +
        (normals[i * 3 + 1] as number) * occ[1] +
        (normals[i * 3 + 2] as number) * occ[2];
    }
    if (s < 0) occ = [-occ[0], -occ[1], -occ[2]];
  }

  // anterior sign: project every sample onto (ap, lateral); the AP extreme whose slice has
  // the smaller lateral spread is the U apex = the incisor end.
  const apCoords: number[] = [];
  const latCoords: number[] = [];
  for (let i = 0; i < totalPoints; i += stride) {
    const dx = (positions[i * 3] as number) - cx;
    const dy = (positions[i * 3 + 1] as number) - cy;
    const dz = (positions[i * 3 + 2] as number) - cz;
    apCoords.push(dx * ap[0] + dy * ap[1] + dz * ap[2]);
    latCoords.push(dx * lateral[0] + dy * lateral[1] + dz * lateral[2]);
  }
  const order = apCoords.map((_, i) => i).sort((i, j) => (apCoords[i] as number) - (apCoords[j] as number));
  const sliceSize = Math.max(20, Math.floor(order.length * APEX_SLICE_FRACTION));
  const spread = (indices: readonly number[]): number => {
    let mean = 0;
    for (const i of indices) mean += latCoords[i] as number;
    mean /= indices.length;
    let variance = 0;
    for (const i of indices) {
      const d = (latCoords[i] as number) - mean;
      variance += d * d;
    }
    return Math.sqrt(variance / indices.length);
  };
  const lowSpread = spread(order.slice(0, sliceSize));
  const highSpread = spread(order.slice(order.length - sliceSize));
  let anterior: Vec = highSpread < lowSpread ? ap : [-ap[0], -ap[1], -ap[2]];

  // re-orthogonalize anterior against the (possibly sign-flipped) occlusal axis
  const d = anterior[0] * occ[0] + anterior[1] * occ[1] + anterior[2] * occ[2];
  const orth = normalize([anterior[0] - d * occ[0], anterior[1] - d * occ[1], anterior[2] - d * occ[2]]);
  if (!orth) return null;
  anterior = orth;

  return { centroid: [cx, cy, cz], occlusal: occ, anterior };
}
