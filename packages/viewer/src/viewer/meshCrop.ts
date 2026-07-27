/**
 * THE SCANNED CAP REGION — cropping the arch down to the site the operator is verifying.
 *
 * The verify dialog puts three live 3D panels on screen at once, two of which want the doctor's
 * SCAN. That scan is 11-25 MB of triangles covering a whole arch; a panel that is supposed to
 * show ONE cap should not carry (or re-parse, or re-upload to the GPU) the other 30 teeth. So
 * the dialog parses the scan once and each panel gets a small crop around its site's centre.
 *
 * The crop is a plain triangle filter — a triangle survives when ANY of its three vertices is
 * within `radiusMm` of the centre — which keeps the cap's rim intact rather than slicing
 * triangles at the boundary (a cut edge would invent geometry that is not in the doctor's scan).
 * Nothing is welded, moved or re-normalled: the surviving triangles keep their exact world
 * coordinates, so the cropped region still overlays the deviation mesh (also world-frame) with
 * no transform at all.
 *
 * Pure typed-array in, typed-array out — no three.js, no DOM — so it is unit-testable in the
 * node environment.
 */

/** How wide a "cap region" is by default: a healing cap is ~4-8mm across, so ±9mm shows the cap,
 *  its emergence and enough neighbouring tissue to judge the seat, and nothing else. */
export const CAP_REGION_RADIUS_MM = 9;

/**
 * The triangles of `positions` (a flat, NON-indexed x,y,z stream — what STLLoader produces) with
 * any vertex within `radiusMm` of `center`, as a new flat stream. Returns an empty array when
 * nothing is near (the caller then shows an honest "nothing within Nmm of this site" state
 * rather than an empty black panel).
 *
 * Trailing coordinates that do not complete a triangle are ignored — a malformed buffer must not
 * produce a half-triangle with an undefined vertex.
 */
export function cropTrianglesNear(
  positions: ArrayLike<number>,
  center: readonly [number, number, number],
  radiusMm: number = CAP_REGION_RADIUS_MM,
): Float32Array {
  const r2 = radiusMm * radiusMm;
  const triangleCount = Math.floor(positions.length / 9);
  const kept: number[] = [];
  for (let t = 0; t < triangleCount; t += 1) {
    const base = t * 9;
    let near = false;
    for (let v = 0; v < 3 && !near; v += 1) {
      const dx = (positions[base + v * 3] as number) - center[0];
      const dy = (positions[base + v * 3 + 1] as number) - center[1];
      const dz = (positions[base + v * 3 + 2] as number) - center[2];
      near = dx * dx + dy * dy + dz * dz <= r2;
    }
    if (!near) continue;
    for (let i = 0; i < 9; i += 1) kept.push(positions[base + i] as number);
  }
  return new Float32Array(kept);
}

/** How many triangles a crop result holds — the panel's own "N triangles in this region" note. */
export function triangleCount(positions: ArrayLike<number>): number {
  return Math.floor(positions.length / 9);
}

/** The centroid of a flat position stream, or null when it is empty — the fallback framing
 *  target for a panel whose content has no site centre of its own (the library part). */
export function centroidOf(positions: ArrayLike<number>): [number, number, number] | null {
  const count = Math.floor(positions.length / 3);
  if (count === 0) return null;
  let x = 0;
  let y = 0;
  let z = 0;
  for (let i = 0; i < count; i += 1) {
    x += positions[i * 3] as number;
    y += positions[i * 3 + 1] as number;
    z += positions[i * 3 + 2] as number;
  }
  return [x / count, y / count, z / count];
}
