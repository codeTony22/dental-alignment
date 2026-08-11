/**
 * TEMPLATE-MATCHED ISOLATION's distance machinery (§10-AT front 1, client
 * 2026-08-10: "just take out the mesh of the healing cap"). A width cut cannot
 * separate tissue lying INSIDE the cap's footprint; distance to the POSED
 * library cap's surface can: scan triangles within the band are the surface at
 * the cap, everything shouldering away drops. Same contract as meshCrop:
 * nothing moved, nothing sliced, any-vertex keeps.
 */
import { describe, expect, it } from "vitest";
import {
  buildSurfaceGrid,
  cropTrianglesNearSurface,
  posePositions,
} from "./meshDistance";
import { triangleCount } from "./meshCrop";

/** One flat triangle around (x, y, z). */
function triangleAt(x: number, y = 0, z = 0): number[] {
  return [x, y, z, x + 0.1, y + 0.1, z, x, y + 0.1, z + 0.1];
}

describe("buildSurfaceGrid + cropTrianglesNearSurface", () => {
  it("keeps what lies within the band of the surface and drops the rest, unmoved", () => {
    const template = new Float32Array(triangleAt(0));
    const grid = buildSurfaceGrid(template);
    const scan = new Float32Array([
      ...triangleAt(0.2), // 0.2mm off the template — tissue ON the cap
      ...triangleAt(5), // 5mm away — tissue shouldering off
    ]);
    const kept = cropTrianglesNearSurface(scan, grid, 0.6);
    expect(triangleCount(kept)).toBe(1);
    expect([...kept.slice(0, 9)]).toEqual(triangleAt(0.2).map((v) => Math.fround(v)));
  });

  it("keeps a triangle with ANY vertex in band — the boundary is not sliced", () => {
    const grid = buildSurfaceGrid(new Float32Array(triangleAt(0)));
    const straddling = new Float32Array([0.1, 0, 0, 9, 0, 0, 0, 9, 0]);
    expect(triangleCount(cropTrianglesNearSurface(straddling, grid, 0.6))).toBe(1);
  });

  it("measures against the whole surface, not one corner — mid-face gaps close via centroids", () => {
    // one large template triangle: its centroid sample covers the middle a
    // vertex-only grid would miss at a tight band
    const big = new Float32Array([0, 0, 0, 8, 0, 0, 0, 8, 0]);
    const grid = buildSurfaceGrid(big);
    const midFace = new Float32Array(triangleAt(2.6, 2.6, 0.3));
    expect(triangleCount(cropTrianglesNearSurface(midFace, grid, 0.6))).toBe(1);
  });

  it("an empty band keeps nothing rather than a partial buffer", () => {
    const grid = buildSurfaceGrid(new Float32Array(triangleAt(0)));
    const far = new Float32Array(triangleAt(30));
    const kept = cropTrianglesNearSurface(far, grid, 0.6);
    expect(kept).toHaveLength(0);
  });
});

describe("posePositions — canonical template into the world frame", () => {
  it("applies the pose basis (z=axis, x=x_axis, y=z×x) about the origin", () => {
    // a 90° turn about z: x_axis = +y, so canonical +x lands on world +y
    const posed = posePositions(new Float32Array([1, 0, 0, 0, 1, 0, 0, 0, 1]), {
      origin: [10, 0, 0],
      axis: [0, 0, 1],
      x_axis: [0, 1, 0],
    });
    expect([...posed.slice(0, 3)].map((v) => Math.round(v * 1e6) / 1e6)).toEqual([10, 1, 0]);
    expect([...posed.slice(3, 6)].map((v) => Math.round(v * 1e6) / 1e6)).toEqual([9, 0, 0]);
    expect([...posed.slice(6, 9)].map((v) => Math.round(v * 1e6) / 1e6)).toEqual([10, 0, 1]);
  });

  it("refuses a malformed pose with null rather than guessing", () => {
    expect(posePositions(new Float32Array(3), {
      origin: [0, 0], axis: [0, 0, 1], x_axis: [1, 0, 0],
    })).toBeNull();
  });
});
