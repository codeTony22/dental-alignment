/**
 * CROPPING THE SCAN to one site's cap region (the verify dialog's panes 2 and 3).
 *
 * The properties that matter: nothing is moved (a cropped triangle keeps its exact world
 * coordinates, or the region would no longer overlay the world-frame deviation mesh), nothing is
 * cut (a triangle survives whole or not at all — a sliced edge would invent geometry that is not
 * in the doctor's scan), and a malformed buffer cannot produce a half-triangle.
 */
import { describe, expect, it } from "vitest";
import { CAP_REGION_RADIUS_MM, centroidOf, cropTrianglesNear, triangleCount } from "./meshCrop";

/** One flat triangle with all three vertices near `x` on the x axis. */
function triangleAt(x: number): number[] {
  return [x, 0, 0, x + 0.1, 0.1, 0, x, 0.1, 0.1];
}

describe("cropTrianglesNear", () => {
  it("keeps the triangles near the centre and drops the rest, unmoved", () => {
    const positions = new Float32Array([...triangleAt(0), ...triangleAt(50), ...triangleAt(1)]);
    const cropped = cropTrianglesNear(positions, [0, 0, 0], 5);
    expect(triangleCount(cropped)).toBe(2);
    expect([...cropped.slice(0, 9)]).toEqual(triangleAt(0).map((v) => Math.fround(v)));
    expect(cropped[9]).toBeCloseTo(1, 5); // the second kept triangle is the one at x=1
  });

  it("keeps a triangle with ANY vertex inside — the rim is not sliced at the boundary", () => {
    // one vertex at the centre, the other two far outside the radius
    const straddling = new Float32Array([0, 0, 0, 40, 0, 0, 0, 40, 0]);
    expect(triangleCount(cropTrianglesNear(straddling, [0, 0, 0], 5))).toBe(1);
  });

  it("returns empty when nothing is near, rather than a partial buffer", () => {
    const cropped = cropTrianglesNear(new Float32Array(triangleAt(100)), [0, 0, 0], 9);
    expect(cropped).toHaveLength(0);
    expect(triangleCount(cropped)).toBe(0);
  });

  it("crops about the site's own centre, not the origin", () => {
    const positions = new Float32Array([...triangleAt(0), ...triangleAt(30)]);
    const cropped = cropTrianglesNear(positions, [30, 0, 0], 5);
    expect(triangleCount(cropped)).toBe(1);
    expect(cropped[0]).toBeCloseTo(30, 5);
  });

  it("ignores trailing coordinates that do not complete a triangle", () => {
    const ragged = new Float32Array([...triangleAt(0), 0, 0, 0, 1, 1]);
    expect(triangleCount(cropTrianglesNear(ragged, [0, 0, 0], 5))).toBe(1);
  });

  it("defaults to the cap-region radius", () => {
    const justInside = new Float32Array(triangleAt(CAP_REGION_RADIUS_MM - 0.5));
    const justOutside = new Float32Array(triangleAt(CAP_REGION_RADIUS_MM + 1));
    expect(triangleCount(cropTrianglesNear(justInside, [0, 0, 0]))).toBe(1);
    expect(triangleCount(cropTrianglesNear(justOutside, [0, 0, 0]))).toBe(0);
  });
});

describe("centroidOf", () => {
  it("averages the vertices, and answers null for an empty stream", () => {
    expect(centroidOf(new Float32Array([0, 0, 0, 2, 4, 6]))).toEqual([1, 2, 3]);
    expect(centroidOf(new Float32Array([]))).toBeNull();
  });
});
