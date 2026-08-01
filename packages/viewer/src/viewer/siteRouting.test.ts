/**
 * THE ROUTING DECISION, as a pure function (client, 2026-07-26: "Main panel needs to be
 * positioned properly to avoid the use to zoom in and find the cap").
 *
 * Measured baseline that motivated it: on the live stage the camera sat 240 mm from the arch
 * centroid at a 45° FOV — 199 mm of visible height — so a 6.16 mm cap was 3.1% of the view,
 * **14 pixels** on a 444 px canvas. Framing on the site's own 9 mm neighbourhood puts the same
 * cap at 23% / ~100 px with its neighbours and the gum line still in frame.
 *
 * The camera move itself needs WebGL and is not unit-testable (repo convention: SceneController
 * is exercised in the browser, its pure helpers here — see anatomyOrientation, partFrame,
 * meshCrop). What IS testable, and is where every real bug lives, is the DECISION: which target,
 * how big, and — the part three adversarial risk lenses were spent on — WHEN THE ANSWER MUST BE
 * "don't move".
 */
import { describe, expect, it } from "vitest";
import {
  SITE_FRAME_RADIUS_MM,
  resolveRouteTarget,
  routeSignature,
  type RouteInputs,
} from "./siteRouting";
import type { Vec3 } from "../domain/types";

const CENTER: Vec3 = [12.5, 11.8, 20.3];
const POSE: Vec3 = [12.7, 11.6, 20.9];

function inputs(overrides: Partial<RouteInputs> = {}): RouteInputs {
  return {
    tooth: 29,
    siteCenter: CENTER,
    posePosition: null,
    contentGeneration: 1,
    subject: "site",
    toolActive: false,
    partPreviewActive: false,
    contentIsArch: true,
    modalOpen: false,
    ...overrides,
  };
}

describe("resolveRouteTarget — where the main stage should look", () => {
  it("frames the marked centre at the site neighbourhood radius", () => {
    expect(resolveRouteTarget(inputs())).toEqual({
      tooth: 29,
      center: CENTER,
      radiusMm: SITE_FRAME_RADIUS_MM,
      key: "1:29",
    });
  });

  /**
   * The seated implant origin is a MEASUREMENT of where the cap actually is; the marked centre
   * is where a human clicked, and is known to carry 0.3-0.6 mm of click noise. Once a run has
   * produced the former, it is the better thing to point a camera at.
   */
  it("prefers the measured seated pose over the human mark once a run has produced one", () => {
    expect(resolveRouteTarget(inputs({ posePosition: POSE }))?.center).toEqual(POSE);
  });

  it("uses the site's own 11 mm neighbourhood — the same region the verify panes crop to", () => {
    // One constant means the main stage and the verify panes cannot disagree about what
    // "this site" is. The crop's radius is reused, never re-guessed.
    expect(SITE_FRAME_RADIUS_MM).toBe(11);
  });
});

/**
 * THE VETOES. Each of these is a sequence an adversarial pass traced to a real line in this
 * repo, not a hypothetical. `controls.enabled = false` does NOT protect the camera — the render
 * loop calls controls.update() unconditionally and nothing gates the position writes — so a
 * route fired mid-tool genuinely moves the view, and the operator cannot even orbit back.
 */
describe("resolveRouteTarget — when it must NOT move", () => {
  it("refuses while any pointer tool is armed (brush, mark, rim points, pick)", () => {
    expect(resolveRouteTarget(inputs({ toolActive: true }))).toBeNull();
  });

  it("refuses while a library part is previewed — a part sits in its own frame, not the jaw's", () => {
    expect(resolveRouteTarget(inputs({ partPreviewActive: true }))).toBeNull();
  });

  it("refuses when the stage is not showing an arch at all", () => {
    expect(resolveRouteTarget(inputs({ contentIsArch: false }))).toBeNull();
  });

  /** Moving a stage nobody can see is not helpful — it is a surprise discovered on close. */
  it("refuses while a full-screen dialog covers the stage", () => {
    expect(resolveRouteTarget(inputs({ modalOpen: true }))).toBeNull();
  });

  /** The escape hatch. Once the operator says "whole arch", nothing may quietly undo that. */
  it("refuses whenever the operator has asked for the whole arch", () => {
    expect(resolveRouteTarget(inputs({ subject: "arch" }))).toBeNull();
    // ...even with a perfectly good site sitting right there
    expect(resolveRouteTarget(inputs({ subject: "arch", posePosition: POSE }))).toBeNull();
  });

  it("refuses when there is no site", () => {
    expect(resolveRouteTarget(inputs({ tooth: null, siteCenter: null }))).toBeNull();
  });

  it("refuses when the site has no centre to look at", () => {
    expect(resolveRouteTarget(inputs({ siteCenter: null }))).toBeNull();
  });

  it("refuses a non-finite centre rather than pointing the camera at NaN", () => {
    expect(resolveRouteTarget(inputs({ siteCenter: [0, Number.NaN, 0] }))).toBeNull();
    expect(resolveRouteTarget(inputs({ siteCenter: [0, Number.POSITIVE_INFINITY, 0] }))).toBeNull();
    // ...and falls back to the mark rather than refusing outright when only the POSE is bad
    expect(resolveRouteTarget(inputs({ posePosition: [Number.NaN, 0, 0] }))?.center).toEqual(CENTER);
  });
});

/**
 * THE RE-FIRE GUARD. `withSites` spreads state before `withActiveSite`'s identity bail-out
 * compares it, so it NEVER returns `prev` — every mark placed, brush finished, rim point
 * committed or variant changed mints a fresh `selection` object. An effect keyed on that object
 * would re-route the camera on all of them. Keying on the target's SIGNATURE instead means the
 * camera moves when the place to look changes, and at no other time.
 */
describe("routeSignature — the camera moves only when the target really changes", () => {
  it("is stable across identical targets from different object identities", () => {
    const a = resolveRouteTarget(inputs());
    const b = resolveRouteTarget(inputs({ siteCenter: [...CENTER] as Vec3 }));
    expect(routeSignature(a)).toBe(routeSignature(b));
  });

  it("changes when the operator picks a different site", () => {
    const a = resolveRouteTarget(inputs());
    const b = resolveRouteTarget(inputs({ tooth: 30 }));
    expect(routeSignature(a)).not.toBe(routeSignature(b));
  });

  it("changes when the SAME site is re-seated — a run, a nudge, a best fit", () => {
    const a = resolveRouteTarget(inputs());
    const b = resolveRouteTarget(inputs({ contentGeneration: 2, posePosition: POSE }));
    expect(routeSignature(a)).not.toBe(routeSignature(b));
  });

  /**
   * THE CHURN GUARD, and the reason the key excludes coordinates. `withSites` never returns
   * `prev`, so every mark edit mints a fresh `selection`; and marks move the site centre. Keying
   * on the centre would re-frame the camera on the operator's own fourth rim point.
   */
  it("does NOT change when a re-mark moves the centre within the same content", () => {
    const a = resolveRouteTarget(inputs());
    const b = resolveRouteTarget(inputs({ siteCenter: [CENTER[0] + 1.4, CENTER[1], CENTER[2]] }));
    expect(routeSignature(a)).toBe(routeSignature(b));
  });

  it("is null for a vetoed route, so a veto can never be mistaken for a target", () => {
    expect(routeSignature(null)).toBeNull();
    expect(routeSignature(resolveRouteTarget(inputs({ toolActive: true })))).toBeNull();
    expect(routeSignature(resolveRouteTarget(inputs({ subject: "arch" })))).toBeNull();
  });
});
