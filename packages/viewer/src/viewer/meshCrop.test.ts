/**
 * CROPPING THE SCAN to one site's cap region (the verify dialog's panes 2 and 3).
 *
 * The properties that matter: nothing is moved (a cropped triangle keeps its exact world
 * coordinates, or the region would no longer overlay the world-frame deviation mesh), nothing is
 * cut (a triangle survives whole or not at all — a sliced edge would invent geometry that is not
 * in the doctor's scan), and a malformed buffer cannot produce a half-triangle.
 */
import { describe, expect, it } from "vitest";
import {
  CAP_REGION_RADIUS_MM,
  centroidOf,
  cropTrianglesInCylinder,
  cropTrianglesNear,
  triangleCount,
} from "./meshCrop";

/** One flat triangle with all three vertices near `x` on the x axis. */
function triangleAt(x: number): number[] {
  return [x, 0, 0, x + 0.1, 0.1, 0, x, 0.1, 0.1];
}

describe("cropTrianglesInCylinder — the cap-only crop (client 2026-08-10)", () => {
  // "just take out the mesh of the healing cap": a sphere cannot separate a
  // SUBMERGED cap from the gum at the same height — only the cap's own rim
  // radius about its own axis can. Same contract as cropTrianglesNear:
  // nothing moved, nothing sliced, any-vertex keeps.
  it("keeps what lies within the rim radius of the axis, inside the height band", () => {
    const positions = new Float32Array([
      ...triangleAt(0), // on the axis — the cap
      ...triangleAt(6), // 6mm out radially — the gum ring
    ]);
    const kept = cropTrianglesInCylinder(positions, [0, 0, 0], [0, 0, 1], 3, 2, 5);
    expect(triangleCount(kept)).toBe(1);
    expect([...kept.slice(0, 9)]).toEqual(triangleAt(0).map((v) => Math.fround(v)));
  });

  it("bounds the cylinder axially — above the top and below the base it keeps nothing", () => {
    const above = new Float32Array([0, 0, 5, 0.1, 0, 5, 0, 0.1, 5]);
    const below = new Float32Array([0, 0, -9, 0.1, 0, -9, 0, 0.1, -9]);
    const inside = new Float32Array([0, 0, -3, 0.1, 0, -3, 0, 0.1, -3]);
    const all = new Float32Array([...above, ...below, ...inside]);
    expect(triangleCount(cropTrianglesInCylinder(all, [0, 0, 0], [0, 0, 1], 3, 2, 5))).toBe(1);
  });

  it("measures radially about the AXIS, not the centre — a deep flank survives", () => {
    // 2mm off-axis but 4mm below the centre: a sphere of radius 3 loses it,
    // the cylinder keeps it — this is the tall cap's lower flank
    const flank = new Float32Array([2, 0, -4, 2.1, 0, -4, 2, 0.1, -4]);
    expect(triangleCount(cropTrianglesNear(flank, [0, 0, 0], 3))).toBe(0);
    expect(triangleCount(cropTrianglesInCylinder(flank, [0, 0, 0], [0, 0, 1], 3, 2, 5))).toBe(1);
  });

  it("follows a tilted axis", () => {
    // the axis leans along +x: a point 4mm along it is ON the axis, not 4mm off
    const along = new Float32Array([4, 0, 0, 4.1, 0, 0, 4, 0.1, 0]);
    expect(
      triangleCount(cropTrianglesInCylinder(along, [0, 0, 0], [1, 0, 0], 1, 5, 5)),
    ).toBe(1);
    expect(
      triangleCount(cropTrianglesInCylinder(along, [0, 0, 0], [0, 0, 1], 1, 5, 5)),
    ).toBe(0);
  });
});

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
