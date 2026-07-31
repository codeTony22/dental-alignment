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
import { armedViewerClassName } from "./verifyScene";

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
