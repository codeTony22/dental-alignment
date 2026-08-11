/**
 * TEMPLATE-MATCHED ISOLATION (§10-AT front 1, client 2026-08-10: "just take
 * out the mesh of the healing cap"). The width cut (meshCrop's cylinder)
 * cannot separate tissue lying INSIDE the cap's own footprint — it is the
 * same scanned surface. Distance to the POSED library cap can: a scan
 * triangle within the band IS the surface at the cap; one shouldering away
 * is tissue or neighbouring anatomy, and drops.
 *
 * The distance is measured against a POINT SAMPLING of the template surface —
 * every soup vertex plus every triangle centroid — on a uniform grid hash.
 * Sampling error is bounded by the template's own tessellation (CAD caps
 * tessellate at ~0.2–0.5mm), which is why the band carries slack rather than
 * pretending to exact point-to-surface distance. Same contract as meshCrop:
 * nothing moved, nothing sliced, any-vertex keeps.
 */

export interface SurfaceGrid {
  readonly cellMm: number;
  /** cell key "ix,iy,iz" → flat xyz sample coordinates */
  readonly cells: ReadonlyMap<string, readonly number[]>;
}

export function buildSurfaceGrid(
  positions: ArrayLike<number>,
  cellMm = 0.6,
): SurfaceGrid {
  const cells = new Map<string, number[]>();
  const push = (x: number, y: number, z: number): void => {
    const key = `${Math.floor(x / cellMm)},${Math.floor(y / cellMm)},${Math.floor(z / cellMm)}`;
    let bucket = cells.get(key);
    if (bucket === undefined) {
      bucket = [];
      cells.set(key, bucket);
    }
    bucket.push(x, y, z);
  };
  const triangles = Math.floor(positions.length / 9);
  for (let t = 0; t < triangles; t += 1) {
    const b = t * 9;
    let cx = 0;
    let cy = 0;
    let cz = 0;
    for (let v = 0; v < 3; v += 1) {
      const x = positions[b + v * 3] as number;
      const y = positions[b + v * 3 + 1] as number;
      const z = positions[b + v * 3 + 2] as number;
      push(x, y, z);
      cx += x / 3;
      cy += y / 3;
      cz += z / 3;
    }
    push(cx, cy, cz);
  }
  return { cellMm, cells };
}

function nearSurface(
  grid: SurfaceGrid,
  x: number,
  y: number,
  z: number,
  bandMm: number,
): boolean {
  const reach = Math.max(1, Math.ceil(bandMm / grid.cellMm));
  const ix = Math.floor(x / grid.cellMm);
  const iy = Math.floor(y / grid.cellMm);
  const iz = Math.floor(z / grid.cellMm);
  const band2 = bandMm * bandMm;
  for (let dx = -reach; dx <= reach; dx += 1) {
    for (let dy = -reach; dy <= reach; dy += 1) {
      for (let dz = -reach; dz <= reach; dz += 1) {
        const bucket = grid.cells.get(`${ix + dx},${iy + dy},${iz + dz}`);
        if (bucket === undefined) continue;
        for (let i = 0; i < bucket.length; i += 3) {
          const ex = x - (bucket[i] as number);
          const ey = y - (bucket[i + 1] as number);
          const ez = z - (bucket[i + 2] as number);
          if (ex * ex + ey * ey + ez * ez <= band2) return true;
        }
      }
    }
  }
  return false;
}

export function cropTrianglesNearSurface(
  positions: ArrayLike<number>,
  grid: SurfaceGrid,
  bandMm: number,
): Float32Array {
  const triangles = Math.floor(positions.length / 9);
  const kept: number[] = [];
  for (let t = 0; t < triangles; t += 1) {
    const b = t * 9;
    let near = false;
    for (let v = 0; v < 3 && !near; v += 1) {
      near = nearSurface(
        grid,
        positions[b + v * 3] as number,
        positions[b + v * 3 + 1] as number,
        positions[b + v * 3 + 2] as number,
        bandMm,
      );
    }
    if (!near) continue;
    for (let i = 0; i < 9; i += 1) kept.push(positions[b + i] as number);
  }
  return new Float32Array(kept);
}

/** The pane's pose convention (domain/adjust's ghost math, verbatim): a basis
 *  of z = the seated axis, x = the pose's own x_axis, y = z×x, about origin.
 *  null on any malformed triple — a camera or a crop must never guess. */
export function posePositions(
  positions: ArrayLike<number>,
  pose: {
    readonly origin: readonly number[];
    readonly axis: readonly number[];
    readonly x_axis: readonly number[];
  },
): Float32Array | null {
  const ok = (v: readonly number[]): boolean =>
    v.length === 3 && v.every((c) => Number.isFinite(c));
  if (!ok(pose.origin) || !ok(pose.axis) || !ok(pose.x_axis)) return null;
  const [ox, oy, oz] = pose.origin as readonly [number, number, number];
  const z = pose.axis as readonly [number, number, number];
  const x = pose.x_axis as readonly [number, number, number];
  const y: readonly [number, number, number] = [
    z[1] * x[2] - z[2] * x[1],
    z[2] * x[0] - z[0] * x[2],
    z[0] * x[1] - z[1] * x[0],
  ];
  const out = new Float32Array(positions.length);
  for (let i = 0; i < positions.length; i += 3) {
    const px = positions[i] as number;
    const py = positions[i + 1] as number;
    const pz = positions[i + 2] as number;
    out[i] = ox + x[0] * px + y[0] * py + z[0] * pz;
    out[i + 1] = oy + x[1] * px + y[1] * py + z[1] * pz;
    out[i + 2] = oz + x[2] * px + y[2] * py + z[2] * pz;
  }
  return out;
}
