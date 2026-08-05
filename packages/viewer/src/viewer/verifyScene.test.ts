/**
 * What of verifyScene node can honestly execute. The scene itself is browser-only (see
 * sceneController.characterization.test.ts's header for the boundary this package holds):
 * a WebGLRenderer, OrbitControls and a ResizeObserver are built in the constructor, so
 * nothing here instantiates VerifyScene.
 *
 * `armedViewerClassName` is the pure half of the ARMED-PANE tell (gap
 * on-glass-pane-hint-and-armed-cursor): a pane with a pick listener installed says so
 * with the cursor, and the cursor is a CSS concern keyed off this class — so the class
 * is what a node test can pin.
 */
import { describe, expect, it } from "vitest";
import * as THREE from "three";
import {
  armedViewerClassName,
  basisFromDirectionUp,
  orbitFromBasis,
  orbitInBasis,
  shouldBroadcastOrbit,
} from "./verifyScene";

/**
 * THE LINK'S BASIS MATH (client 2026-08-04: pane 1 sat 177° off its OWN axis,
 * upside down, under a chip saying "rotating together"). The old mirror shared
 * WORLD spherical angles, so panes whose content lives in different frames could
 * not agree by construction. These pin the new contract: the shared orbit is the
 * camera pose IN EACH PANE'S OWN FRAMED BASIS, so a mirrored pane always shows
 * the same relative view of its own content — whatever its axis points at.
 */
describe("the basis-relative orbit", () => {
  const v = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);

  it("round-trips a pose through its own basis exactly", () => {
    const basis = basisFromDirectionUp(v(0, 0, 1), v(1, 0, 0));
    const orbit = orbitInBasis(v(3, 4, 12), v(1, 0, 0), basis, 13);
    const back = orbitFromBasis(orbit, basis, 13);
    expect(back.offset.x).toBeCloseTo(3, 10);
    expect(back.offset.y).toBeCloseTo(4, 10);
    expect(back.offset.z).toBeCloseTo(12, 10);
    expect(back.up.angleTo(v(1, 0, 0))).toBeCloseTo(0, 10);
  });

  it("two panes with DIFFERENT axes show the same relative view — the 177° pin", () => {
    // pane 1: the library part, framed down its canonical +z, up +x
    const library = basisFromDirectionUp(v(0, 0, 1), v(1, 0, 0));
    // pane 2: the scan, framed down an arbitrary tilted seated axis
    const seated = v(0.42, -0.31, 0.85).normalize();
    const scan = basisFromDirectionUp(seated, v(0.9, 0.1, -0.4));
    // the operator drags pane 2 somewhere; pane 1 mirrors it
    const dragOffsetWorld = v(2.2, -1.1, 7.7);
    const dragUp = v(0.2, 0.9, 0.1).normalize();
    const shared = orbitInBasis(dragOffsetWorld, dragUp, scan, 9);
    const mirrored = orbitFromBasis(shared, library, 15);
    // THE INVARIANT: each camera sits at the same angle to ITS OWN pane's axis.
    const scanAngle = dragOffsetWorld.angleTo(seated);
    const libraryAngle = mirrored.offset.angleTo(v(0, 0, 1));
    expect(libraryAngle).toBeCloseTo(scanAngle, 10);
    // and the zoom mirrors as a RATIO of each pane's own framing distance
    expect(mirrored.offset.length() / 15).toBeCloseTo(
      dragOffsetWorld.length() / 9,
      10,
    );
  });

  it("mirroring is symmetric — sending the mirrored pose back reproduces the drag", () => {
    const a = basisFromDirectionUp(v(0, 1, 0), v(0, 0, 1));
    const b = basisFromDirectionUp(v(1, 0, 0), v(0, 1, 0));
    const offset = v(1, 2, 2);
    const up = v(0, 0, 1);
    const throughB = orbitFromBasis(orbitInBasis(offset, up, a, 3), b, 5);
    const backInA = orbitFromBasis(orbitInBasis(throughB.offset, throughB.up, b, 5), a, 3);
    expect(backInA.offset.distanceTo(offset)).toBeCloseTo(0, 10);
  });

  it("a mirrored orbit never parks the camera inside its subject — the distance floor", () => {
    const basis = basisFromDirectionUp(v(0, 0, 1), v(1, 0, 0));
    const tiny = orbitFromBasis(
      { offset: [0.001, 0, 0.001], up: [1, 0, 0] },
      basis,
      10,
    );
    expect(tiny.offset.length()).toBeGreaterThanOrEqual(0.5 - 1e-9);
  });

  it("a degenerate up falls back to a stable perpendicular, never NaN", () => {
    // up parallel to the axis: the projection vanishes and a naive normalize
    // would seed the whole basis with NaN
    const basis = basisFromDirectionUp(v(0, 0, 1), v(0, 0, 1));
    const e = basis.elements;
    expect(e.every((n) => Number.isFinite(n))).toBe(true);
    const orbit = orbitInBasis(v(1, 1, 1), v(0, 1, 0), basis, 1);
    expect(orbit.offset.every((n) => Number.isFinite(n))).toBe(true);
  });
});

describe("armedViewerClassName", () => {
  it("keeps the base class when the pane is read-only", () => {
    expect(armedViewerClassName(false)).toBe("verify-viewer");
  });

  it("adds the armed modifier when a pick listener is installed", () => {
    expect(armedViewerClassName(true)).toBe("verify-viewer verify-viewer--armed");
  });

  it("never drops the base class — the pane's size rules hang off it", () => {
    for (const armed of [true, false]) {
      expect(armedViewerClassName(armed).split(" ")).toContain("verify-viewer");
    }
  });
});

/**
 * WHAT COUNTS AS A USER ORBIT (design review 2026-07-31).
 *
 * `onOrbitChange`'s own docstring says it is "called whenever the USER moves this
 * pane's camera (never for an applied orbit)" — and a programmatic RE-FRAME is neither
 * a user move nor an applied orbit, so it fell through the guard. With "link views" on,
 * a preset click therefore made every pane broadcast its own re-framing and the last
 * pane to frame imposed its world-space spherical angles on the other two: pane 1
 * renders the library part in its canonical FILE frame while panes 2/3 live in the
 * jaw-scan world frame, so no pane ended up on the basis the preset asked for.
 *
 * The scene itself is browser-only (a WebGLRenderer in the constructor), so what a node
 * test can hold is the predicate every camera assignment now goes through.
 */
describe("shouldBroadcastOrbit — only a hand on the mouse mirrors to the siblings", () => {
  it("broadcasts an ordinary controls change to the link group", () => {
    expect(shouldBroadcastOrbit(false, true)).toBe(true);
  });

  it("stays silent while the camera is being ASSIGNED — a mirror or a re-frame", () => {
    expect(shouldBroadcastOrbit(true, true)).toBe(false);
  });

  it("stays silent with nobody listening, assigned or not", () => {
    expect(shouldBroadcastOrbit(false, false)).toBe(false);
    expect(shouldBroadcastOrbit(true, false)).toBe(false);
  });
});
