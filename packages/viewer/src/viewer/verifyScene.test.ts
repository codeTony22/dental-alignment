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
import { armedViewerClassName, shouldBroadcastOrbit } from "./verifyScene";

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
