/**
 * THE PANE FOOTER'S TWO CLAIMS, pinned (gap pane-footer-scale-bar-and-axis-label).
 *
 * Both are claims about the LIVE camera, which is why they live here rather than in the
 * product: the product cannot see a camera, and a footer that guesses is worse than no
 * footer. What a node test can hold is the arithmetic and the WORDS — VerifyScene itself
 * is browser-only (WebGLRenderer in its constructor), so the scene reads its camera and
 * hands these functions numbers.
 *
 * The honesty constraint that shaped both: panes 2 and 3 frame down the seated pose axis
 * and then ORBIT FREELY (VerifyViewer frames once per target). A static "OCCLUSAL" string
 * — which is what the design prototype prints — starts lying on the first drag. So the
 * label is a live reading against the axis the pane framed on, and it says how far off it
 * is rather than naming a direction it no longer has.
 */
import { describe, expect, it } from "vitest";
import {
  mmPerPixelAtFocus,
  paneAxisLabel,
  paneScaleBar,
  viewReadoutChanged,
} from "./paneReadout";

describe("mmPerPixelAtFocus", () => {
  it("measures the focus plane's visible height over the viewport's pixels", () => {
    // 45° fov, 100mm away: visible height = 2 * 100 * tan(22.5°) = 82.84mm over 400px.
    const mmPerPx = mmPerPixelAtFocus(100, 45, 400);
    expect(mmPerPx).not.toBeNull();
    expect(mmPerPx!).toBeCloseTo((2 * 100 * Math.tan((22.5 * Math.PI) / 180)) / 400, 9);
  });

  it("halves when the camera dollies to half the distance — it is NOT a constant", () => {
    const near = mmPerPixelAtFocus(50, 45, 400)!;
    const far = mmPerPixelAtFocus(100, 45, 400)!;
    expect(near).toBeCloseTo(far / 2, 9);
  });

  it("refuses a viewport with no height rather than dividing by zero", () => {
    expect(mmPerPixelAtFocus(100, 45, 0)).toBeNull();
  });

  it("refuses a degenerate camera — no bar beats a wrong bar", () => {
    expect(mmPerPixelAtFocus(0, 45, 400)).toBeNull();
    expect(mmPerPixelAtFocus(Number.NaN, 45, 400)).toBeNull();
    expect(mmPerPixelAtFocus(100, 0, 400)).toBeNull();
    expect(mmPerPixelAtFocus(100, 180, 400)).toBeNull();
  });
});

describe("paneScaleBar", () => {
  it("picks the largest 1-2-5 step that still fits the bar's budget", () => {
    // 0.05 mm/px, 96px budget => 4.8mm fits; the ladder's answer is 2mm at 40px.
    expect(paneScaleBar(0.05, 96)).toEqual({ mm: 2, px: 40, label: "2 mm" });
  });

  it("moves down the ladder as the operator zooms in", () => {
    expect(paneScaleBar(0.01, 96)?.label).toBe("0.5 mm");
    expect(paneScaleBar(0.002, 96)?.label).toBe("0.1 mm");
  });

  it("moves up the ladder as the operator pulls back", () => {
    expect(paneScaleBar(0.5, 96)?.label).toBe("20 mm");
    expect(paneScaleBar(2, 96)?.label).toBe("100 mm");
  });

  it("draws the bar at the width the step actually measures", () => {
    const bar = paneScaleBar(0.02, 96)!;
    expect(bar.px).toBe(Math.round(bar.mm / 0.02));
    expect(bar.px).toBeLessThanOrEqual(96);
  });

  it("prints sub-millimetre steps without trailing zeros", () => {
    expect(paneScaleBar(0.001, 96)?.label).toBe("0.05 mm");
  });

  it("SHIPS NO BAR rather than a wrong one when nothing on the ladder reads", () => {
    // A camera so far out that even the ladder's top step is a stub, and one so close
    // that its bottom step overruns the budget: both get nothing, never a rounded lie.
    expect(paneScaleBar(1000, 96)).toBeNull();
    expect(paneScaleBar(0.0000001, 96)).toBeNull();
    expect(paneScaleBar(Number.NaN, 96)).toBeNull();
    expect(paneScaleBar(0, 96)).toBeNull();
  });
});

describe("paneAxisLabel", () => {
  const down: readonly [number, number, number] = [0, 0, 1];

  it("says the pane is looking down its own axis while it still is", () => {
    expect(paneAxisLabel({ viewDirection: down, mmPerPixel: 0.02 }, down, "the seated pose axis")).toBe(
      "down the seated pose axis",
    );
  });

  it("STOPS SAYING SO the moment the operator orbits away", () => {
    // The whole point of the gap: a static label would still read "OCCLUSAL" here.
    const orbited: readonly [number, number, number] = [1, 0, 0];
    expect(paneAxisLabel({ viewDirection: orbited, mmPerPixel: 0.02 }, down, "the seated pose axis")).toBe(
      "90° off the seated pose axis",
    );
  });

  it("reads the angle, not a bucket", () => {
    const tilted: readonly [number, number, number] = [Math.sin(0.5), 0, Math.cos(0.5)];
    expect(paneAxisLabel({ viewDirection: tilted, mmPerPixel: 0.02 }, down, "the pose axis")).toBe(
      `${Math.round((0.5 * 180) / Math.PI)}° off the pose axis`,
    );
  });

  it("treats the far side as 180° off, never as down the axis again", () => {
    const behind: readonly [number, number, number] = [0, 0, -1];
    expect(paneAxisLabel({ viewDirection: behind, mmPerPixel: 0.02 }, down, "the pose axis")).toBe(
      "180° off the pose axis",
    );
  });

  it("tolerates a couple of degrees of orbit slop before it starts counting", () => {
    const nudged: readonly [number, number, number] = [Math.sin(0.02), 0, Math.cos(0.02)];
    expect(paneAxisLabel({ viewDirection: nudged, mmPerPixel: 0.02 }, down, "the pose axis")).toBe(
      "down the pose axis",
    );
  });

  it("says what it actually is when the pane framed on nothing", () => {
    // No reference direction = the viewer's own three-quarter default; there is no axis
    // to be off, and inventing one would be the lie this label exists to avoid.
    expect(paneAxisLabel({ viewDirection: down, mmPerPixel: 0.02 }, null, "the pose axis")).toBe(
      "free view",
    );
    expect(paneAxisLabel({ viewDirection: down, mmPerPixel: 0.02 }, [0, 0, 0], "the pose axis")).toBe(
      "free view",
    );
  });

  it("says nothing at all before the camera has been read", () => {
    expect(paneAxisLabel(null, down, "the pose axis")).toBeNull();
  });
});

describe("viewReadoutChanged", () => {
  const base = { viewDirection: [0, 0, 1] as const, mmPerPixel: 0.02 };

  it("is true for the first reading", () => {
    expect(viewReadoutChanged(null, base)).toBe(true);
  });

  it("swallows the damping tail — a fraction of a degree is not a new reading", () => {
    const drift = {
      viewDirection: [Math.sin(0.002), 0, Math.cos(0.002)] as const,
      mmPerPixel: 0.020_05,
    };
    expect(viewReadoutChanged(base, drift)).toBe(false);
  });

  it("reports a real orbit", () => {
    expect(
      viewReadoutChanged(base, { viewDirection: [Math.sin(0.1), 0, Math.cos(0.1)], mmPerPixel: 0.02 }),
    ).toBe(true);
  });

  it("reports a real dolly even when the angle held", () => {
    expect(viewReadoutChanged(base, { viewDirection: [0, 0, 1], mmPerPixel: 0.024 })).toBe(true);
  });
});
