/**
 * THE RELIEF CEILING, pinned (client, 2026-07-25 — "end-to-end automation must complete").
 *
 * What these tests are protecting:
 *  - the ceiling shown is the TIGHTEST of the chosen caps, not the active site's — a case whose
 *    tooth 3 takes 0.06 mm and whose tooth 14 takes 0.18 mm must read 0.06, or tooth 3 clamps
 *    unseen, which is the exact surprise the feature removes;
 *  - a request AT the ceiling does not warn (display precision), a request OVER it does;
 *  - the warning states the number, the wall rule and what the run will do — and never claims the
 *    UI will change the operator's number;
 *  - "not determined" and the 404 are their own honest states, never rendered as "unlimited".
 */
import { describe, expect, it } from "vitest";
import {
  bindingCeiling,
  ceilingReadout,
  ceilingWarning,
  describeCeiling,
  exceedsCeiling,
  reliefLimitKey,
  wallClause,
  type ReliefLimit,
  type SiteReliefLimit,
} from "./reliefLimit";

function limit(overrides: Partial<ReliefLimit> = {}): ReliefLimit {
  return {
    constructionPathId: "atlantis/neodent-gm-scanbody.stl",
    model: "neodent-gm",
    variant: "5030",
    maxSafeMm: 0.06,
    limitedBy: "channel wall",
    minWallMm: 0.5,
    measured: true,
    note: null,
    ...overrides,
  };
}

function site(tooth: number, state: SiteReliefLimit["state"], variantId = "5030"): SiteReliefLimit {
  return { tooth, variantId, state };
}

describe("reliefLimitKey", () => {
  it("keys a lookup by the three things the endpoint is asked about", () => {
    expect(reliefLimitKey("atlantis/x.stl", "neodent-gm", "5030")).toBe(
      "atlantis/x.stl neodent-gm 5030",
    );
    // a different cap on the same construction part is a DIFFERENT ceiling, not a cache hit
    expect(reliefLimitKey("atlantis/x.stl", "neodent-gm", "6030")).not.toBe(
      reliefLimitKey("atlantis/x.stl", "neodent-gm", "5030"),
    );
  });
});

describe("bindingCeiling — the tightest cap governs the case-wide relief", () => {
  it("picks the smallest measured ceiling and names its tooth", () => {
    const binding = bindingCeiling([
      site(14, { kind: "ready", limit: limit({ maxSafeMm: 0.18, variant: "6030" }) }, "6030"),
      site(3, { kind: "ready", limit: limit({ maxSafeMm: 0.06 }) }),
    ]);
    expect(binding?.maxSafeMm).toBe(0.06);
    expect(binding?.tooth).toBe(3);
  });

  it("ignores pairs the backend could not determine, rather than treating them as unlimited", () => {
    const binding = bindingCeiling([
      site(3, { kind: "ready", limit: limit({ maxSafeMm: null }) }),
      site(14, { kind: "ready", limit: limit({ maxSafeMm: 0.18 }) }),
    ]);
    expect(binding?.maxSafeMm).toBe(0.18);
    expect(binding?.tooth).toBe(14);
  });

  it("is null when nothing has produced a number yet", () => {
    expect(bindingCeiling([site(3, { kind: "loading" })])).toBeNull();
    expect(bindingCeiling([])).toBeNull();
  });

  it("keeps the first site on a tie, so the named tooth does not flicker between renders", () => {
    const sites = [
      site(3, { kind: "ready", limit: limit({ maxSafeMm: 0.06 }) }),
      site(14, { kind: "ready", limit: limit({ maxSafeMm: 0.06 }) }),
    ];
    expect(bindingCeiling(sites)?.tooth).toBe(3);
  });
});

describe("ceilingReadout — one state for the column, by actionability", () => {
  it("is idle with nothing chosen", () => {
    expect(ceilingReadout([])).toEqual({ kind: "idle" });
  });

  it("reports a ceiling as soon as one lands, flagged pending while siblings load", () => {
    const readout = ceilingReadout([
      site(3, { kind: "ready", limit: limit({ maxSafeMm: 0.06 }) }),
      site(14, { kind: "loading" }, "6030"),
    ]);
    expect(readout.kind).toBe("ready");
    if (readout.kind !== "ready") throw new Error("unreachable");
    expect(readout.binding.maxSafeMm).toBe(0.06);
    expect(readout.pending).toBe(true);
  });

  it("prefers a real error over any ceiling — a retry may fix it", () => {
    const readout = ceilingReadout([
      site(3, { kind: "ready", limit: limit() }),
      site(14, { kind: "error", message: "boom" }, "6030"),
    ]);
    expect(readout).toEqual({ kind: "error", message: "boom" });
  });

  it("reports the endpoint's absence over a partial ceiling (restart hint, not a failure)", () => {
    const readout = ceilingReadout([
      site(3, { kind: "ready", limit: limit() }),
      site(14, { kind: "unavailable" }, "6030"),
    ]);
    expect(readout).toEqual({ kind: "unavailable" });
  });

  it("says 'undetermined' when every pair answered without a number", () => {
    expect(ceilingReadout([site(3, { kind: "ready", limit: limit({ maxSafeMm: null }) })])).toEqual({
      kind: "undetermined",
    });
  });
});

describe("exceedsCeiling / ceilingWarning — a warning, never a silent substitution", () => {
  const binding = { maxSafeMm: 0.06, tooth: 3, limit: limit() };

  it("does not warn at or under the ceiling", () => {
    expect(exceedsCeiling(0.06, binding)).toBe(false);
    expect(exceedsCeiling(0.05, binding)).toBe(false);
    expect(ceilingWarning(0.06, binding)).toBeNull();
  });

  it("does not warn on a difference smaller than the displayed precision", () => {
    expect(exceedsCeiling(0.0603, { ...binding, maxSafeMm: 0.0602 })).toBe(false);
  });

  it("warns over the ceiling, naming the number, the wall rule and what the RUN will do", () => {
    expect(exceedsCeiling(0.2, binding)).toBe(true);
    const warning = ceilingWarning(0.2, binding) ?? "";
    expect(warning).toContain("0.20 mm is more than this construction part can take");
    expect(warning).toContain("maximum safe gingival relief is 0.06 mm");
    expect(warning).toContain("below 0.50 mm");
    expect(warning).toContain("The run will clamp to 0.06 mm and report it");
    // the UI never edits the operator's number for them
    expect(warning).toContain("lower the number here");
  });

  it("falls back to the generic wall clause when the backend did not name the rule", () => {
    expect(wallClause(limit({ minWallMm: null }))).toBe("below the design rule");
    expect(ceilingWarning(0.2, { ...binding, limit: limit({ minWallMm: null }) })).toContain(
      "below the design rule",
    );
  });
});

describe("describeCeiling", () => {
  it("is the brief's own line on a single-site case", () => {
    expect(describeCeiling({ maxSafeMm: 0.06, tooth: 3, limit: limit() }, 1)).toBe(
      "max safe for this part: 0.06 mm (limited by channel wall)",
    );
  });

  it("names the tooth that SETS the ceiling once several caps are in play", () => {
    expect(describeCeiling({ maxSafeMm: 0.06, tooth: 3, limit: limit() }, 3)).toBe(
      "max safe for this part: 0.06 mm (limited by channel wall) — set by tooth 3 (5030)",
    );
  });
});
