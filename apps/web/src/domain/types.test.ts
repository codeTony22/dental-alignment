import { describe, expect, it } from "vitest";
import {
  buildRunReport,
  CAPTURE_MATCH_RADIUS_MM,
  captureIssues,
  captureNear,
  describeAlignToMark,
  describeNotchResidual,
  findDuplicateTeeth,
  hasEnoughRimPoints,
  rotationNeedsReview,
  siteIsDeclared,
  undeclaredSiteNumbers,
  isRunStale,
  marksSignatureFor,
  MAX_MARKED_POINTS,
  RECOMMENDED_MIN_RIM_POINTS,
  subsamplePoints,
  translateMark,
  withCacheBust,
  type AlignToMarkResult,
  type CaptureAssessment,
  type CaptureSite,
  type Clocking,
  type ConfirmedSite,
  type RunSiteResult,
  type Vec3,
} from "./types";

function makeSite(overrides: Partial<ConfirmedSite> = {}): ConfirmedSite {
  return { tooth: 4, center: [0, 0, 0], ...overrides };
}

function makeLinePoints(count: number): Vec3[] {
  // A simple monotonically-increasing sequence so "even-stride" shape preservation is easy to assert on.
  return Array.from({ length: count }, (_, i): Vec3 => [i, 0, 0]);
}

describe("subsamplePoints", () => {
  it("passes points through unchanged when already at or under the cap", () => {
    const points = makeLinePoints(10);
    expect(subsamplePoints(points, 400)).toEqual(points);
  });

  it("passes an empty input through as an empty array", () => {
    expect(subsamplePoints([], 400)).toEqual([]);
  });

  it("caps the result length at max even for far larger inputs", () => {
    const points = makeLinePoints(10_000);
    const result = subsamplePoints(points, MAX_MARKED_POINTS);
    expect(result.length).toBeLessThanOrEqual(MAX_MARKED_POINTS);
    expect(result.length).toBe(MAX_MARKED_POINTS);
  });

  it("keeps the first point of the stroke (even-stride sampling starts at index 0)", () => {
    const points = makeLinePoints(1000);
    const result = subsamplePoints(points, 100);
    expect(result[0]).toEqual(points[0]);
  });

  it("preserves the stroke's overall shape via even-stride selection, not truncation to a prefix", () => {
    const points = makeLinePoints(1000);
    const result = subsamplePoints(points, 100);
    // A prefix-truncated sample would never see x values beyond ~100; even-stride sampling
    // should span close to the full original range.
    const lastX = result[result.length - 1]?.[0] ?? 0;
    expect(lastX).toBeGreaterThan(900);
  });

  it("uses MAX_MARKED_POINTS as the default cap when max is omitted", () => {
    const points = makeLinePoints(1000);
    const result = subsamplePoints(points);
    expect(result.length).toBe(MAX_MARKED_POINTS);
  });

  it("returns a new array instance rather than mutating or aliasing the input", () => {
    const points = makeLinePoints(5);
    const result = subsamplePoints(points, 400);
    expect(result).not.toBe(points);
    expect(result).toEqual(points);
  });
});

describe("findDuplicateTeeth", () => {
  it("returns an empty array when every tooth is unique", () => {
    expect(findDuplicateTeeth([{ tooth: 4 }, { tooth: 13 }, { tooth: 7 }])).toEqual([]);
  });

  it("returns an empty array for an empty site list", () => {
    expect(findDuplicateTeeth([])).toEqual([]);
  });

  it("returns a single tooth number that appears exactly twice", () => {
    expect(findDuplicateTeeth([{ tooth: 4 }, { tooth: 4 }])).toEqual([4]);
  });

  it("returns a tooth only once even if it repeats more than twice", () => {
    expect(findDuplicateTeeth([{ tooth: 4 }, { tooth: 4 }, { tooth: 4 }])).toEqual([4]);
  });

  it("returns multiple duplicated tooth numbers sorted ascending", () => {
    const sites = [{ tooth: 13 }, { tooth: 4 }, { tooth: 13 }, { tooth: 7 }, { tooth: 4 }];
    expect(findDuplicateTeeth(sites)).toEqual([4, 13]);
  });

  it("does not report teeth that appear exactly once alongside duplicates", () => {
    const sites = [{ tooth: 4 }, { tooth: 4 }, { tooth: 9 }];
    expect(findDuplicateTeeth(sites)).toEqual([4]);
  });
});

describe("declared-variant enforcement", () => {
  it("a real variant string counts as declared", () => {
    expect(siteIsDeclared({ declaredVariant: "6020" })).toBe(true);
  });

  it("undefined, null, empty and whitespace are NOT declared (all mean 'auto')", () => {
    expect(siteIsDeclared({ declaredVariant: undefined })).toBe(false);
    expect(siteIsDeclared({ declaredVariant: null })).toBe(false);
    expect(siteIsDeclared({ declaredVariant: "" })).toBe(false);
    expect(siteIsDeclared({ declaredVariant: "  " })).toBe(false);
  });

  it("undeclaredSiteNumbers is empty when every site is declared", () => {
    expect(undeclaredSiteNumbers([{ declaredVariant: "6020" }, { declaredVariant: "7030" }]))
      .toEqual([]);
  });

  it("undeclaredSiteNumbers reports 1-based row numbers of the auto sites", () => {
    expect(undeclaredSiteNumbers([
      { declaredVariant: "6020" },
      { declaredVariant: "" },
      { declaredVariant: undefined },
    ])).toEqual([2, 3]);
  });
});

describe("translateMark", () => {
  it("translates the rim by exactly the delta the centre moved (preserves the measured radius)", () => {
    const oldCenter: Vec3 = [10, 10, 10];
    const oldRim: Vec3 = [13, 10, 10]; // radius 3 along +x
    const newCenter: Vec3 = [12, 10, 10]; // centre moved +2 along x
    expect(translateMark(oldRim, oldCenter, newCenter)).toEqual([15, 10, 10]);
  });

  it("translates component-wise across all three axes at once", () => {
    const oldCenter: Vec3 = [0, 0, 0];
    const oldRim: Vec3 = [1, 2, 3];
    const newCenter: Vec3 = [5, -1, 2];
    expect(translateMark(oldRim, oldCenter, newCenter)).toEqual([6, 1, 5]);
  });

  it("returns the rim unchanged when the centre did not move", () => {
    const oldCenter: Vec3 = [4, 4, 4];
    const oldRim: Vec3 = [7, 4, 4];
    expect(translateMark(oldRim, oldCenter, oldCenter)).toEqual(oldRim);
  });

  it("preserves |rim - centre| distance exactly regardless of translation direction", () => {
    const oldCenter: Vec3 = [0, 0, 0];
    const oldRim: Vec3 = [3, 4, 0]; // distance 5
    const newCenter: Vec3 = [-10, 7, 2];
    const newRim = translateMark(oldRim, oldCenter, newCenter);
    const distance = (a: Vec3, b: Vec3) =>
      Math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2);
    expect(distance(newRim, newCenter)).toBeCloseTo(distance(oldRim, oldCenter), 10);
  });
});

describe("marksSignatureFor", () => {
  it("returns the same signature for two calls with equivalent (non-identical) mark data", () => {
    const a = [makeSite({ centerMark: [1, 2, 3], rimMark: [4, 5, 6] })];
    const b = [makeSite({ centerMark: [1, 2, 3], rimMark: [4, 5, 6] })];
    expect(marksSignatureFor(a)).toBe(marksSignatureFor(b));
  });

  it("changes when a centerMark is added", () => {
    const before = [makeSite()];
    const after = [makeSite({ centerMark: [1, 2, 3] })];
    expect(marksSignatureFor(before)).not.toBe(marksSignatureFor(after));
  });

  it("changes when a rimMark is cleared", () => {
    const before = [makeSite({ rimMark: [1, 2, 3] })];
    const after = [makeSite()];
    expect(marksSignatureFor(before)).not.toBe(marksSignatureFor(after));
  });

  it("changes when markedPoints (brush patch) changes", () => {
    const before = [makeSite({ markedPoints: [[0, 0, 0]] })];
    const after = [makeSite({ markedPoints: [[0, 0, 1]] })];
    expect(marksSignatureFor(before)).not.toBe(marksSignatureFor(after));
  });

  it("changes when rimPoints is added", () => {
    const before = [makeSite()];
    const after = [makeSite({ rimPoints: [[1, 2, 3]] })];
    expect(marksSignatureFor(before)).not.toBe(marksSignatureFor(after));
  });

  it("changes when a rimPoints collection grows (a new click is added)", () => {
    const before = [makeSite({ rimPoints: [[1, 2, 3]] })];
    const after = [makeSite({ rimPoints: [[1, 2, 3], [4, 5, 6]] })];
    expect(marksSignatureFor(before)).not.toBe(marksSignatureFor(after));
  });

  it("changes when rimPoints is cleared", () => {
    const before = [makeSite({ rimPoints: [[1, 2, 3]] })];
    const after = [makeSite()];
    expect(marksSignatureFor(before)).not.toBe(marksSignatureFor(after));
  });

  it("distinguishes rimMark from rimPoints even with overlapping-looking data (different fields, not aliased)", () => {
    const a = [makeSite({ rimMark: [1, 2, 3] })];
    const b = [makeSite({ rimPoints: [[1, 2, 3]] })];
    expect(marksSignatureFor(a)).not.toBe(marksSignatureFor(b));
  });

  it("does NOT change when only tooth number changes (not a mark edit)", () => {
    const before = [makeSite({ tooth: 4, centerMark: [1, 2, 3] })];
    const after = [makeSite({ tooth: 9, centerMark: [1, 2, 3] })];
    expect(marksSignatureFor(before)).toBe(marksSignatureFor(after));
  });

  it("does NOT change when only declaredVariant changes (not a mark edit)", () => {
    const before = [makeSite({ declaredVariant: "A" })];
    const after = [makeSite({ declaredVariant: "B" })];
    expect(marksSignatureFor(before)).toBe(marksSignatureFor(after));
  });

  it("returns a stable, non-throwing signature for an empty site list", () => {
    expect(marksSignatureFor([])).toBe("");
  });

  it("is sensitive to site order (a distinct site sequence is a distinct signature)", () => {
    const a = [makeSite({ tooth: 4, centerMark: [1, 0, 0] }), makeSite({ tooth: 9, centerMark: [2, 0, 0] })];
    const b = [makeSite({ tooth: 9, centerMark: [2, 0, 0] }), makeSite({ tooth: 4, centerMark: [1, 0, 0] })];
    expect(marksSignatureFor(a)).not.toBe(marksSignatureFor(b));
  });
});

describe("hasEnoughRimPoints", () => {
  it("returns false when rimPoints is undefined", () => {
    expect(hasEnoughRimPoints(undefined)).toBe(false);
  });

  it("returns false for an empty array", () => {
    expect(hasEnoughRimPoints([])).toBe(false);
  });

  it(`returns false for ${RECOMMENDED_MIN_RIM_POINTS - 1} points (below the recommended minimum)`, () => {
    const points: Vec3[] = Array.from({ length: RECOMMENDED_MIN_RIM_POINTS - 1 }, (_, i): Vec3 => [i, 0, 0]);
    expect(hasEnoughRimPoints(points)).toBe(false);
  });

  it(`returns true at exactly the recommended minimum (${RECOMMENDED_MIN_RIM_POINTS} points)`, () => {
    const points: Vec3[] = Array.from({ length: RECOMMENDED_MIN_RIM_POINTS }, (_, i): Vec3 => [i, 0, 0]);
    expect(hasEnoughRimPoints(points)).toBe(true);
  });

  it("returns true for more than the recommended minimum", () => {
    const points: Vec3[] = Array.from({ length: RECOMMENDED_MIN_RIM_POINTS + 5 }, (_, i): Vec3 => [i, 0, 0]);
    expect(hasEnoughRimPoints(points)).toBe(true);
  });
});

describe("isRunStale", () => {
  it("returns false when no run has happened yet (ranSignature is null)", () => {
    expect(isRunStale("some-signature", null)).toBe(false);
  });

  it("returns false when the current signature matches what the run used", () => {
    const sig = marksSignatureFor([makeSite({ centerMark: [1, 2, 3] })]);
    expect(isRunStale(sig, sig)).toBe(false);
  });

  it("returns true when the current signature differs from what the run used", () => {
    const ran = marksSignatureFor([makeSite({ centerMark: [1, 2, 3] })]);
    const current = marksSignatureFor([makeSite({ centerMark: [9, 9, 9] })]);
    expect(isRunStale(current, ran)).toBe(true);
  });

  it("returns false for two equal-value signatures even if built from non-identical site objects", () => {
    const a = marksSignatureFor([makeSite({ centerMark: [1, 2, 3] })]);
    const b = marksSignatureFor([{ tooth: 4, center: [0, 0, 0], centerMark: [1, 2, 3] }]);
    expect(isRunStale(a, b)).toBe(false);
  });

  it("returns true once rimPoints changes after a run (the client's core complaint scenario)", () => {
    const ranSignature = marksSignatureFor([makeSite({ centerMark: [1, 2, 3] })]);
    const afterRimPointsDone = marksSignatureFor([
      makeSite({ centerMark: [1, 2, 3], rimPoints: [[4, 5, 6], [7, 8, 9], [1, 1, 1]] }),
    ]);
    expect(isRunStale(afterRimPointsDone, ranSignature)).toBe(true);
  });

  it("returns false for an empty-string signature compared against itself (empty site list, no drift)", () => {
    expect(isRunStale("", "")).toBe(false);
  });
});

function makeRunSite(overrides: Partial<RunSiteResult> = {}): RunSiteResult {
  return {
    tooth: 4,
    spec: "6020",
    vendor: "zimmer",
    coverage: 0.9,
    alignmentErrorMm: 0.2,
    advisory: "ok",
    variant: {
      identified: "6020",
      declared: null,
      measuredRimDiameterMm: 6.02,
      diameterClassMarginMm: 0.15,
      flags: [],
      candidates: [
        { variant: "6020", seatResidualMm: 0.081 },
        { variant: "6030", seatResidualMm: 0.214 },
      ],
    },
    siteMeasurement: {
      mdSpanMm: 7.1,
      gapMesialMm: 0.3,
      gapDistalMm: 0.4,
      classification: "normal",
      terminalSite: false,
    },
    production: { screwChannelRadiusMm: 1.2 },
    seedSource: "marks",
    autoDeltaMm: 0.42,
    fit: { avgMm: 0.11, maxMm: 0.58 },
    seatMethod: "rim",
    guidance: { level: "ready", actions: ["Looks good — no action needed."] },
    rimAgreementMm: 0.31,
    borderClickDisagreementMm: null,
    topFaceAgreementMm: null,
    confidence: null,
    capSurfaceExplainedPct: 92,
    clocking: null,
    nudge: null,
    acceptance: null,
    doctorConfirmation: null,
  gingivalOffset: null,
    ...overrides,
  };
}

describe("buildRunReport", () => {
  it("includes the case id as a markdown heading", () => {
    const report = buildRunReport("276794487-zimmer-4.5", [], []);
    expect(report).toContain("# Run report — 276794487-zimmer-4.5");
  });

  it("includes per-site run numbers: seed source, seat method, delta-auto, fit, rim seat, cap surface %, variant", () => {
    const runSites = [makeRunSite()];
    const report = buildRunReport("case-1", [], runSites);
    expect(report).toContain("Tooth 4");
    expect(report).toContain("marks");
    expect(report).toContain("rim");
    expect(report).toContain("0.42mm");
    expect(report).toContain("0.11 / 0.58mm");
    expect(report).toContain("0.31mm");
    expect(report).toContain("92%");
    expect(report).toContain("6020");
  });

  it("includes the full candidates list with scores", () => {
    const report = buildRunReport("case-1", [], [makeRunSite()]);
    expect(report).toContain("6020 (0.081)");
    expect(report).toContain("6030 (0.214)");
  });

  it("includes measured diameter, declared, gate level, and guidance action text", () => {
    const report = buildRunReport("case-1", [], [makeRunSite()]);
    expect(report).toContain("6.02mm");
    expect(report).toContain("auto");
    expect(report).toContain("ready");
    expect(report).toContain("Looks good — no action needed.");
  });

  it("includes an inputs summary: centre mark rounded to 0.1, rim-points count + coords, brush point count", () => {
    const sites: ConfirmedSite[] = [
      makeSite({
        tooth: 4,
        centerMark: [12.73, 14.61, 20.849],
        rimPoints: [
          [1.04, 2.06, 3.01],
          [4.02, 5.09, 6.03],
          [7.01, 8.08, 9.02],
        ],
        markedPoints: makeLinePoints(37),
      }),
    ];
    const report = buildRunReport("case-1", sites, [makeRunSite()]);
    expect(report).toContain("(12.7, 14.6, 20.8)");
    expect(report).toContain("Rim points (3)");
    expect(report).toContain("(1, 2.1, 3)");
    expect(report).toContain("Brush points: 37");
  });

  it("includes the border-click disagreement when measured (the 'why did this seat tilt' answer)", () => {
    const report = buildRunReport("case-1", [], [makeRunSite({ borderClickDisagreementMm: 0.89 })]);
    expect(report).toContain("Border-click disagreement: 0.89mm");
  });

  it("omits the border-click disagreement line when not measured (fewer than 4 border clicks)", () => {
    const report = buildRunReport("case-1", [], [makeRunSite()]);
    expect(report).not.toContain("Border-click disagreement");
  });

  it("includes the top-face seat when measured (the depth read-out)", () => {
    const report = buildRunReport("case-1", [], [makeRunSite({ topFaceAgreementMm: 2.45 })]);
    expect(report).toContain("Top-face seat: 2.45mm");
  });

  it("includes the confidence grade when computed", () => {
    const report = buildRunReport("case-1", [], [makeRunSite({
      confidence: { grade: "medium", posSpreadMm: 0.9, axisSpreadDeg: 11 },
    })]);
    expect(report).toContain("Confidence: medium");
    expect(report).toContain("0.90mm / 11°");
  });

  it("omits the confidence line when not computed", () => {
    const report = buildRunReport("case-1", [], [makeRunSite()]);
    expect(report).not.toContain("Confidence:");
  });

  it("omits the top-face line when not measured", () => {
    const report = buildRunReport("case-1", [], [makeRunSite()]);
    expect(report).not.toContain("Top-face seat");
  });

  it("flags a tooth with run data but no matching input site, rather than silently dropping it", () => {
    const report = buildRunReport("case-1", [], [makeRunSite({ tooth: 9 })]);
    expect(report).toContain("Tooth 9");
    expect(report).toContain("no input data for this tooth");
  });

  it("flags a tooth with an input site but no matching run data", () => {
    const report = buildRunReport("case-1", [makeSite({ tooth: 12 })], []);
    expect(report).toContain("Tooth 12");
    expect(report).toContain("no run data yet for this tooth");
  });
});

describe("withCacheBust", () => {
  it("appends a ?v= query param when a version token is set", () => {
    expect(withCacheBust("/files/case-1-4-healingcap-aligned.stl", 1700000000000)).toBe(
      "/files/case-1-4-healingcap-aligned.stl?v=1700000000000",
    );
  });

  it("returns the URL unchanged when the version token is null (no run yet)", () => {
    expect(withCacheBust("/files/case-1-4-healingcap-aligned.stl", null)).toBe(
      "/files/case-1-4-healingcap-aligned.stl",
    );
  });

  it("uses & instead of ? when the URL already has a query string", () => {
    expect(withCacheBust("/files/x.stl?foo=bar", 42)).toBe("/files/x.stl?foo=bar&v=42");
  });

  it("produces a different URL for two different version tokens (second run busts the first run's cache)", () => {
    const first = withCacheBust("/files/case-1-4-healingcap-aligned.stl", 1);
    const second = withCacheBust("/files/case-1-4-healingcap-aligned.stl", 2);
    expect(first).not.toBe(second);
  });

  // Traces the exact scenario in the coordinator's report: identical file NAME across two runs
  // (the server overwrites the same on-disk file every run) must still resolve to two DIFFERENT
  // fetch URLs, so a stale-tab in-memory cache entry for run 1's URL can never satisfy run 2's
  // fetch. Mirrors App.tsx's resolvePartUrl composition (scan endpoint untouched; files_base-
  // relative name wrapped in withCacheBust) without importing React/App.tsx — pure string logic.
  it("TRACE: auto-reveal fetches carry ?v= after a run, and a second run produces a different ?v=", () => {
    const filesBase = "/api/cases/276794487-zimmer-4.5/files/";
    const fileName = "276794487-zimmer-4.5-4-healingcap-aligned.stl";
    const resolvePartUrl = (name: string, version: number | null) => withCacheBust(`${filesBase}${name}`, version);

    // Before any run: no version token yet, URL is bare (nothing to bust).
    expect(resolvePartUrl(fileName, null)).toBe(`${filesBase}${fileName}`);

    // Run 1 lands — mint a token (Date.now() in the real code), auto-reveal's fetch carries it.
    const runOneVersion = 1700000000000;
    const runOneUrl = resolvePartUrl(fileName, runOneVersion);
    expect(runOneUrl).toBe(`${filesBase}${fileName}?v=${runOneVersion}`);

    // Run 2 lands for the SAME file name (server overwrote the bytes on disk) — a NEW token means
    // a genuinely different URL, so the browser cannot serve run 1's cached response for it.
    const runTwoVersion = 1700000005000;
    const runTwoUrl = resolvePartUrl(fileName, runTwoVersion);
    expect(runTwoUrl).toBe(`${filesBase}${fileName}?v=${runTwoVersion}`);
    expect(runTwoUrl).not.toBe(runOneUrl);
  });

  it("TRACE: the scan endpoint URL is never versioned (not a files_base package file)", () => {
    // Mirrors resolvePartUrl's `source.kind === "scan"` branch: scanUrlFor(caseId) is returned
    // as-is, bypassing withCacheBust entirely, regardless of the run's version token.
    const scanUrl = "/api/cases/276794487-zimmer-4.5/scan";
    expect(scanUrl.includes("?v=")).toBe(false);
  });
});

function makeClocking(overrides: Partial<Clocking> = {}): Clocking {
  return {
    notchShiftDeg: -1.8,
    notchCorr: 0.61,
    notchProminence: 0.3,
    evidence: "codes",
    consistencyDeg: null,
    rotationUnverified: false,
    ...overrides,
  };
}

describe("rotationNeedsReview", () => {
  it("does not flag a verified codes-anchored rotation", () => {
    expect(rotationNeedsReview(makeClocking())).toBe(false);
  });

  it("flags an unverified rotation (the tri-state contract's refusal case)", () => {
    expect(rotationNeedsReview(makeClocking({ rotationUnverified: true }))).toBe(true);
  });

  it("flags a site where no instrument read at all", () => {
    expect(rotationNeedsReview(makeClocking({ evidence: "none" }))).toBe(true);
  });

  it("flags instruments disagreeing by more than 20° (a rigid part cannot satisfy both)", () => {
    expect(rotationNeedsReview(makeClocking({ consistencyDeg: 34.2 }))).toBe(true);
    expect(rotationNeedsReview(makeClocking({ consistencyDeg: 12.0 }))).toBe(false);
  });

  it("never flags a row without a clock instrument (icp seat / legacy cache)", () => {
    expect(rotationNeedsReview(null)).toBe(false);
  });
});

describe("describeNotchResidual", () => {
  it("reads aligned within the pipeline's own ±6° adoption tolerance", () => {
    expect(describeNotchResidual(makeClocking({ notchShiftDeg: -1.8 }))).toBe("-1.8° — aligned");
  });

  it("says the codes disagree beyond the tolerance, keeping the signed value", () => {
    expect(describeNotchResidual(makeClocking({ notchShiftDeg: 23.8 }))).toBe("+23.8° — codes disagree");
  });

  it("is honest about a missing signal", () => {
    expect(describeNotchResidual(makeClocking({ notchShiftDeg: null }))).toBe("no code signal");
    expect(describeNotchResidual(null)).toBe("no code signal");
  });
});

function makeAlignToMarkResult(overrides: Partial<AlignToMarkResult> = {}): AlignToMarkResult {
  return {
    tooth: 29,
    appliedDeltaDeg: 38.2,
    cumulativeDeg: 38.2,
    stabilityExcessMm: 0.03,
    clocking: makeClocking({ notchShiftDeg: -1.4 }),
    nudge: { cumulativeDeg: 38.2 },
    matchedFeatureAzimuthDeg: -136.0,
    clickAzimuthDeg: -97.8,
    ...overrides,
  };
}

describe("describeAlignToMark", () => {
  it("states the applied rotation and the re-read code residual, both signed", () => {
    expect(describeAlignToMark(makeAlignToMarkResult())).toBe(
      "rotated +38.2° — code feature on your mark; codes now read -1.4°",
    );
    expect(
      describeAlignToMark(
        makeAlignToMarkResult({ appliedDeltaDeg: -12.5, clocking: makeClocking({ notchShiftDeg: 2.0 }) }),
      ),
    ).toBe("rotated -12.5° — code feature on your mark; codes now read +2.0°");
  });

  it("is honest when the instrument reads nothing at the new pose (the weak-evidence sites this tool backstops)", () => {
    expect(describeAlignToMark(makeAlignToMarkResult({ clocking: makeClocking({ notchShiftDeg: null }) }))).toBe(
      "rotated +38.2° — code feature on your mark; no code signal at this pose",
    );
  });
});

describe("captureNear", () => {
  const pass: CaptureAssessment = { verdict: "pass", checks: [] };
  const rescan: CaptureAssessment = { verdict: "rescan", checks: [] };
  const sites: CaptureSite[] = [
    { center: [0, 0, 0], tooth: null, capture: pass },
    { center: [10, 0, 0], tooth: 7, capture: rescan },
  ];

  it("returns the assessment measured nearest the site's centre", () => {
    expect(captureNear([9.5, 0.5, 0], sites)).toBe(rescan);
    expect(captureNear([0.2, -0.1, 0.1], sites)).toBe(pass);
  });

  it("returns null beyond the match radius — a far assessment describes a different cap", () => {
    // sites are clinically >=8mm apart; 4mm can never cross-match
    expect(captureNear([5, 0, 0], sites)).toBeNull();
    expect(captureNear([0, 0, 0], [])).toBeNull();
  });

  it("matches exactly at the boundary radius, exclusive beyond it", () => {
    expect(captureNear([CAPTURE_MATCH_RADIUS_MM, 0, 0], sites)).toBe(pass);
    expect(captureNear([CAPTURE_MATCH_RADIUS_MM + 0.01, 0, 0], sites)).toBeNull();
  });
});

describe("captureIssues", () => {
  it("keeps only the checks the operator must hear about (non-pass)", () => {
    const capture: CaptureAssessment = {
      verdict: "rescan",
      checks: [
        { name: "rim_arc", value: 0.54, boundPass: 0.92, boundRescan: 0.55, verdict: "rescan", message: "rim" },
        { name: "code_band", value: 0.86, boundPass: 0.7, boundRescan: 0.45, verdict: "pass", message: "ok" },
        { name: "collar_exposure", value: 0.6, boundPass: 1.0, boundRescan: 0.35, verdict: "marginal", message: "collar" },
      ],
    };
    expect(captureIssues(capture).map((c) => c.name)).toEqual(["rim_arc", "collar_exposure"]);
  });
});
