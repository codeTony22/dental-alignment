import { describe, expect, it } from "vitest";
import { computeAnatomyFrame } from "./anatomyOrientation";

type Vec3 = [number, number, number];

/**
 * Synthetic dental arch strip in a CANONICAL pose: a parabolic U (apex — the incisor end —
 * at y=0, arms opening toward +y like the molars), lying roughly in the xy plane with the
 * occlusal (crowns) direction at +z. Surface normals all face +z, mimicking how an intraoral
 * scanner only captures the exposed occlusal-facing surface.
 */
function makeArchPoints(): { positions: number[]; normals: number[] } {
  const positions: number[] = [];
  const normals: number[] = [];
  // deterministic pseudo-noise (no RNG dependency in tests)
  let seed = 42;
  const jitter = (): number => {
    seed = (seed * 1103515245 + 12345) % 2147483648;
    return seed / 2147483648;
  };
  for (let i = 0; i <= 400; i += 1) {
    const x = -25 + (50 * i) / 400;
    const yCurve = 0.04 * x * x;
    for (let k = 0; k < 6; k += 1) {
      positions.push(x + jitter() * 1.5, yCurve + jitter() * 6, jitter() * 3);
      normals.push(0, 0, 1);
    }
  }
  return { positions, normals };
}

function rotate(points: number[], r: (p: Vec3) => Vec3): number[] {
  const out: number[] = [];
  for (let i = 0; i < points.length; i += 3) {
    const [x, y, z] = r([points[i] as number, points[i + 1] as number, points[i + 2] as number]);
    out.push(x, y, z);
  }
  return out;
}

/** Rotation of 30 deg about x then 40 deg about z, plus a translation for positions. */
function makeTestRotation(): (p: Vec3) => Vec3 {
  const cx = Math.cos(Math.PI / 6);
  const sx = Math.sin(Math.PI / 6);
  const cz = Math.cos((40 * Math.PI) / 180);
  const sz = Math.sin((40 * Math.PI) / 180);
  return ([x, y, z]: Vec3): Vec3 => {
    const y1 = cx * y - sx * z;
    const z1 = sx * y + cx * z;
    const x2 = cz * x - sz * y1;
    const y2 = sz * x + cz * y1;
    return [x2, y2, z1];
  };
}

function dot(a: readonly number[], b: readonly number[]): number {
  return (a[0] as number) * (b[0] as number) + (a[1] as number) * (b[1] as number) + (a[2] as number) * (b[2] as number);
}

describe("computeAnatomyFrame", () => {
  it("recovers occlusal +z and anterior -y on the canonical arch", () => {
    const { positions, normals } = makeArchPoints();
    const frame = computeAnatomyFrame(positions, normals);
    expect(frame).not.toBeNull();
    // occlusal = smallest-variance axis, signed toward the scanned (normal-facing) side
    expect(dot(frame!.occlusal, [0, 0, 1])).toBeGreaterThan(0.98);
    // anterior = toward the U apex (incisors), which this arch has at low y
    expect(dot(frame!.anterior, [0, -1, 0])).toBeGreaterThan(0.95);
    // orthonormal
    expect(Math.abs(dot(frame!.anterior, frame!.occlusal))).toBeLessThan(1e-6);
  });

  it("recovers the same anatomical frame under an arbitrary rigid transform", () => {
    const { positions, normals } = makeArchPoints();
    const r = makeTestRotation();
    const rotated = rotate(positions, r).map((v, i) => v + ([7, -13, 42][i % 3] as number));
    const rotatedNormals = rotate(normals, r);
    const frame = computeAnatomyFrame(rotated, rotatedNormals);
    expect(frame).not.toBeNull();
    expect(dot(frame!.occlusal, r([0, 0, 1]))).toBeGreaterThan(0.98);
    expect(dot(frame!.anterior, r([0, -1, 0]))).toBeGreaterThan(0.93);
  });

  it("keeps a usable frame when normals are unavailable (sign may be ambiguous, axis is not)", () => {
    const { positions } = makeArchPoints();
    const frame = computeAnatomyFrame(positions);
    expect(frame).not.toBeNull();
    expect(Math.abs(dot(frame!.occlusal, [0, 0, 1]))).toBeGreaterThan(0.98);
  });

  it("returns null for degenerate inputs", () => {
    // far too few points
    expect(computeAnatomyFrame([0, 0, 0, 1, 1, 1, 2, 2, 2])).toBeNull();
    // an isotropic blob has no occlusal sheet direction
    const blob: number[] = [];
    let seed = 7;
    const jitter = (): number => {
      seed = (seed * 1103515245 + 12345) % 2147483648;
      return seed / 2147483648 - 0.5;
    };
    for (let i = 0; i < 3000; i += 1) {
      blob.push(jitter() * 20, jitter() * 20, jitter() * 20);
    }
    expect(computeAnatomyFrame(blob)).toBeNull();
  });
});
