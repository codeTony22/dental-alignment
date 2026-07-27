/**
 * THE CLAMP READ-OUT, pinned (client, 2026-07-25).
 *
 * The one thing these tests exist to prevent: a run that quietly built the part at a different
 * relief than the lab asked for. So the strictness is deliberate — a reading is only reported as
 * clamped when it SAYS clamped and carries a lower applied number; anything short of that reads
 * as "not clamped", because printing a fabricated "applied" would be the very substitution the
 * brief forbids.
 */
import { describe, expect, it } from "vitest";
import type { GingivalOffsetReading, RunSiteResult } from "./types";
import {
  clampChipText,
  clampHeadline,
  clampedSites,
  describeClamp,
  hasClamp,
  siteReliefClamp,
} from "./reliefClamp";

function reading(overrides: Partial<GingivalOffsetReading> = {}): GingivalOffsetReading {
  return {
    requestedMm: 0.2,
    achievedMedianMm: null,
    achievedMinMm: null,
    achievedMaxMm: null,
    method: null,
    appliedMm: null,
    clamped: false,
    limitMm: null,
    minWallMm: null,
    clampReason: null,
    ...overrides,
  };
}

function site(tooth: number, gingivalOffset: GingivalOffsetReading | null): RunSiteResult {
  return {
    tooth,
    spec: "neodent-gm-5030",
    vendor: "atlantis",
    coverage: 0.9,
    alignmentErrorMm: 0.1,
    advisory: "",
    variant: {
      identified: "5030",
      declared: "5030",
      measuredRimDiameterMm: 5.1,
      diameterClassMarginMm: 0.2,
      flags: [],
      candidates: null,
    },
    siteMeasurement: {
      mdSpanMm: 8,
      gapMesialMm: 1,
      gapDistalMm: 1,
      classification: "bounded",
      terminalSite: false,
    },
    production: { screwChannelRadiusMm: 1.153 },
    seedSource: "marks",
    autoDeltaMm: 0.2,
    fit: { avgMm: 0.08, maxMm: 0.4 },
    seatMethod: "rim",
    guidance: null,
    rimAgreementMm: 0.3,
    borderClickDisagreementMm: null,
    topFaceAgreementMm: null,
    confidence: null,
    capSurfaceExplainedPct: null,
    clocking: null,
    nudge: null,
    acceptance: null,
    doctorConfirmation: null,
    gingivalOffset,
  };
}

describe("siteReliefClamp — only a real clamp is reported as one", () => {
  it("reads the two numbers, the ceiling and the reason off a clamped site", () => {
    const clamp = siteReliefClamp(
      site(
        3,
        reading({
          appliedMm: 0.06,
          clamped: true,
          limitMm: 0.06,
          minWallMm: 0.5,
          clampReason: "the channel wall would drop under the rule",
        }),
      ),
    );
    expect(clamp).toEqual({
      tooth: 3,
      requestedMm: 0.2,
      appliedMm: 0.06,
      limitMm: 0.06,
      minWallMm: 0.5,
      reason: "the channel wall would drop under the rule",
    });
  });

  it("is null when nothing was clamped", () => {
    expect(siteReliefClamp(site(3, reading()))).toBeNull();
  });

  it("is null when the backend has no gingival reading at all (legacy run)", () => {
    expect(siteReliefClamp(site(3, null))).toBeNull();
  });

  it("REFUSES to report a clamp with no applied number — a fabricated one would be the lie", () => {
    expect(siteReliefClamp(site(3, reading({ clamped: true, appliedMm: null })))).toBeNull();
  });

  it("refuses an 'applied' that is not lower than the request — that is not a clamp", () => {
    expect(siteReliefClamp(site(3, reading({ clamped: true, appliedMm: 0.2 })))).toBeNull();
    expect(siteReliefClamp(site(3, reading({ clamped: true, appliedMm: 0.25 })))).toBeNull();
  });
});

describe("clampedSites / hasClamp", () => {
  const sites = [
    site(3, reading({ clamped: true, appliedMm: 0.06, minWallMm: 0.5 })),
    site(14, reading({ achievedMedianMm: 0.14 })),
    site(29, reading({ clamped: true, appliedMm: 0.1, minWallMm: 0.5 })),
  ];

  it("returns only the clamped sites, in the run's own order", () => {
    expect(clampedSites(sites).map((c) => c.tooth)).toEqual([3, 29]);
  });

  it("hasClamp agrees with the list", () => {
    expect(hasClamp(sites)).toBe(true);
    expect(hasClamp([site(14, reading())])).toBe(false);
    expect(hasClamp([])).toBe(false);
  });
});

describe("the sentences", () => {
  const clamp = {
    tooth: 3,
    requestedMm: 0.2,
    appliedMm: 0.06,
    limitMm: 0.06,
    minWallMm: 0.5,
    reason: null,
  };

  it("describeClamp is the brief's own sentence, both numbers named", () => {
    expect(describeClamp(clamp)).toBe(
      "gingival relief 0.20 mm requested → 0.06 mm applied (the maximum this construction part " +
        "can take without thinning the channel wall below 0.50 mm)",
    );
  });

  it("falls back to the generic rule when the backend did not name the wall number", () => {
    expect(describeClamp({ ...clamp, minWallMm: null })).toContain("below the design rule");
  });

  it("clampChipText is the compact table form", () => {
    expect(clampChipText(clamp)).toBe("relief clamped 0.20 → 0.06 mm");
  });

  it("clampHeadline names the teeth, singular and plural", () => {
    expect(clampHeadline([clamp])).toBe("The gingival relief you asked for was reduced on tooth 3.");
    expect(clampHeadline([clamp, { ...clamp, tooth: 14 }])).toBe(
      "The gingival relief you asked for was reduced on teeth 3 and 14.",
    );
    expect(clampHeadline([clamp, { ...clamp, tooth: 14 }, { ...clamp, tooth: 29 }])).toBe(
      "The gingival relief you asked for was reduced on teeth 3, 14 and 29.",
    );
  });
});
