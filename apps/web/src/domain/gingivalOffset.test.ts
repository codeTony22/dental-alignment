/**
 * OFFSET HONESTY: the achieved clearance is a MEASUREMENT of the run's output, and it never
 * silently becomes the request (nor the request the achievement). The measured finding these
 * tests pin: asking 0.20 mm achieves ~0.13-0.15 mm median.
 */
import { describe, expect, it } from "vitest";
import {
  achievedGingivalOffset,
  describeAchievedOffset,
  offsetShortfall,
} from "./gingivalOffset";
import type { GingivalOffsetReading, RunSiteResult } from "./types";

function site(tooth: number, gingivalOffset: GingivalOffsetReading | null): RunSiteResult {
  return {
    tooth,
    spec: "neodent-gm-6020",
    vendor: "dess",
    coverage: 0.9,
    alignmentErrorMm: 0.1,
    advisory: "",
    variant: {
      identified: "6020",
      declared: "6020",
      measuredRimDiameterMm: 6.1,
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
    production: { screwChannelRadiusMm: 1.1 },
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

function reading(achievedMedianMm: number | null, extra: Partial<GingivalOffsetReading> = {}): GingivalOffsetReading {
  return {
    requestedMm: 0.2,
    achievedMedianMm,
    achievedMinMm: null,
    achievedMaxMm: null,
    method: null,
    // the clamp half of the reading (domain/reliefClamp) — off by default here: these tests are
    // about REQUESTED vs ACHIEVED, and an unclamped run is the case they describe
    appliedMm: null,
    clamped: false,
    limitMm: null,
    minWallMm: null,
    clampReason: null,
    ...extra,
  };
}

describe("achievedGingivalOffset", () => {
  it("reports the MEASURED median, not the requested value", () => {
    const achieved = achievedGingivalOffset([
      site(3, reading(0.13)),
      site(14, reading(0.15)),
      site(29, reading(0.14)),
    ]);
    expect(achieved).not.toBeNull();
    expect(achieved?.requestedMm).toBe(0.2);
    expect(achieved?.medianMm).toBeCloseTo(0.14, 6);
    expect(achieved?.nSites).toBe(3);
    expect(offsetShortfall(achieved!)).toBeCloseTo(0.06, 6);
  });

  it("is null when NOTHING measured — never an echo of the request", () => {
    expect(achievedGingivalOffset([site(3, null), site(14, null)])).toBeNull();
    expect(achievedGingivalOffset([site(3, reading(null))])).toBeNull();
    expect(achievedGingivalOffset([])).toBeNull();
  });

  it("excludes an unmeasured site rather than counting it as agreeing", () => {
    const achieved = achievedGingivalOffset([site(3, reading(0.13)), site(14, null)]);
    expect(achieved?.nSites).toBe(1);
    expect(achieved?.medianMm).toBeCloseTo(0.13, 6);
  });

  it("takes the spread from the backend's own per-site min/max when it reported one", () => {
    const achieved = achievedGingivalOffset([
      site(3, reading(0.14, { achievedMinMm: 0.11, achievedMaxMm: 0.17 })),
      site(14, reading(0.15, { achievedMinMm: 0.13, achievedMaxMm: 0.19 })),
    ]);
    expect(achieved?.minMm).toBeCloseTo(0.11, 6);
    expect(achieved?.maxMm).toBeCloseTo(0.19, 6);
  });

  it("averages the middle two on an even number of sites", () => {
    const achieved = achievedGingivalOffset([site(3, reading(0.12)), site(14, reading(0.16))]);
    expect(achieved?.medianMm).toBeCloseTo(0.14, 6);
  });

  it("keeps one outlier site from moving the number the operator reads", () => {
    const achieved = achievedGingivalOffset([
      site(3, reading(0.14)),
      site(14, reading(0.14)),
      site(29, reading(0.01)),
    ]);
    expect(achieved?.medianMm).toBeCloseTo(0.14, 6);
  });
});

describe("describeAchievedOffset", () => {
  it("states the median, the site count and the measured spread", () => {
    const achieved = achievedGingivalOffset([
      site(3, reading(0.13)),
      site(14, reading(0.15)),
      site(29, reading(0.14)),
    ]);
    expect(describeAchievedOffset(achieved!)).toBe("0.14 mm achieved (median of 3 sites, 0.13–0.15)");
  });

  it("drops a collapsed range rather than printing 0.14–0.14", () => {
    const achieved = achievedGingivalOffset([site(3, reading(0.14))]);
    expect(describeAchievedOffset(achieved!)).toBe("0.14 mm achieved (1 site)");
  });
});
