import { describe, expect, it } from "vitest";
import {
  mapCase,
  mapLibraryVariants,
  mapNudgeResult,
  mapProposeResult,
  mapRunResult,
  toWireImportPose,
  toWireRunSiteInput,
} from "./mappers";
import {
  agreementState,
  MAX_MARKED_POINTS,
  type ConfirmedSite,
  type VariantAssessment,
  type Vec3,
} from "../domain/types";
import type {
  WireCaptureAssessment,
  WireCase,
  WireLibraryVariant,
  WireNudgeResult,
  WireProposeResult,
  WireRunResult,
  WireRunSiteResult,
} from "./wireTypes";
import type { PoseTransferDocument } from "../domain/poseTransfer";

const baseSite: ConfirmedSite = {
  tooth: 14,
  center: [1, 2, 3],
};

function makeLinePoints(count: number): Vec3[] {
  return Array.from({ length: count }, (_, i): Vec3 => [i, 0, 0]);
}

function makeWireRunSiteResult(overrides: Partial<WireRunSiteResult> = {}): WireRunSiteResult {
  return {
    tooth: 14,
    spec: "neodent-gm-5020",
    vendor: "dess",
    coverage: 0.5,
    alignment_error_mm: 1.1,
    advisory: "",
    variant: {
      identified: "5020",
      declared: null,
      measured_rim_diameter_mm: 5.1,
      diameter_class_margin_mm: 0.5,
      flags: [],
    },
    site_measurement: {
      md_span_mm: 10,
      gap_mesial_mm: 0.5,
      gap_distal_mm: 0.5,
      classification: "two-implant-capable (>=12mm)",
      terminal_site: false,
    },
    production: { screw_channel_radius_mm: 1.0 },
    seed_source: "click",
    auto_delta_mm: null,
    fit: { avg_mm: 0.28, max_mm: 2.4 },
    ...overrides,
  };
}

function makeWireRunResult(sites: WireRunSiteResult[]): WireRunResult {
  return {
    summary: { sites, package_files: [] },
    files_base: "/api/cases/neodent-gm/files/",
    duration_s: 1.2,
    cached: false,
  };
}

describe("toWireRunSiteInput", () => {
  it("omits marked_points when the site has no markedPoints", () => {
    const wire = toWireRunSiteInput(baseSite);
    expect(wire).not.toHaveProperty("marked_points");
    expect(wire).toEqual({ tooth: 14, center: [1, 2, 3] });
  });

  it("omits marked_points when markedPoints is an empty array", () => {
    const wire = toWireRunSiteInput({ ...baseSite, markedPoints: [] });
    expect(wire).not.toHaveProperty("marked_points");
  });

  it("includes marked_points as plain [x, y, z] arrays when present", () => {
    const markedPoints: Vec3[] = [
      [1, 1, 1],
      [2, 2, 2],
    ];
    const wire = toWireRunSiteInput({ ...baseSite, markedPoints });
    expect(wire.marked_points).toEqual([
      [1, 1, 1],
      [2, 2, 2],
    ]);
  });

  it("subsamples marked_points to the backend's cap (<=400) before submission", () => {
    const markedPoints = makeLinePoints(10_000);
    const wire = toWireRunSiteInput({ ...baseSite, markedPoints });
    expect(wire.marked_points).toBeDefined();
    expect(wire.marked_points?.length).toBeLessThanOrEqual(MAX_MARKED_POINTS);
    expect(wire.marked_points?.length).toBe(MAX_MARKED_POINTS);
  });

  it("still includes declared_variant alongside marked_points when both are present", () => {
    const wire = toWireRunSiteInput({
      ...baseSite,
      declaredVariant: "5020",
      markedPoints: [[0, 0, 0]],
    });
    expect(wire.declared_variant).toBe("5020");
    expect(wire.marked_points).toEqual([[0, 0, 0]]);
  });

  it("trims and omits a blank declaredVariant exactly as before (unaffected by marked_points)", () => {
    const wire = toWireRunSiteInput({ ...baseSite, declaredVariant: "   " });
    expect(wire).not.toHaveProperty("declared_variant");
  });

  it("omits center_mark/rim_mark when the site has no marks", () => {
    const wire = toWireRunSiteInput(baseSite);
    expect(wire).not.toHaveProperty("center_mark");
    expect(wire).not.toHaveProperty("rim_mark");
  });

  it("includes center_mark as a plain [x, y, z] array when present", () => {
    const wire = toWireRunSiteInput({ ...baseSite, centerMark: [5, 6, 7] });
    expect(wire.center_mark).toEqual([5, 6, 7]);
    expect(wire).not.toHaveProperty("rim_mark");
  });

  it("includes rim_mark as a plain [x, y, z] array when present", () => {
    const wire = toWireRunSiteInput({ ...baseSite, rimMark: [8, 9, 10] });
    expect(wire.rim_mark).toEqual([8, 9, 10]);
    expect(wire).not.toHaveProperty("center_mark");
  });

  it("includes both center_mark and rim_mark together, alongside markedPoints and declared_variant", () => {
    const wire = toWireRunSiteInput({
      ...baseSite,
      declaredVariant: "5020",
      markedPoints: [[0, 0, 0]],
      centerMark: [1, 1, 1],
      rimMark: [2, 2, 2],
    });
    expect(wire.declared_variant).toBe("5020");
    expect(wire.marked_points).toEqual([[0, 0, 0]]);
    expect(wire.center_mark).toEqual([1, 1, 1]);
    expect(wire.rim_mark).toEqual([2, 2, 2]);
  });
});

describe("toWireRunSiteInput — rim_points precedence over legacy rim_mark", () => {
  it("omits rim_points when the site has no rimPoints", () => {
    const wire = toWireRunSiteInput(baseSite);
    expect(wire).not.toHaveProperty("rim_points");
  });

  it("omits rim_points when rimPoints is an empty array", () => {
    const wire = toWireRunSiteInput({ ...baseSite, rimPoints: [] });
    expect(wire).not.toHaveProperty("rim_points");
  });

  it("includes rim_points as plain [x, y, z] arrays when present", () => {
    const rimPoints: Vec3[] = [
      [1, 1, 1],
      [2, 2, 2],
      [3, 3, 3],
    ];
    const wire = toWireRunSiteInput({ ...baseSite, rimPoints });
    expect(wire.rim_points).toEqual([
      [1, 1, 1],
      [2, 2, 2],
      [3, 3, 3],
    ]);
  });

  it("sends rim_points and OMITS rim_mark when both are present (rim_points takes precedence)", () => {
    const wire = toWireRunSiteInput({
      ...baseSite,
      rimMark: [8, 9, 10],
      rimPoints: [[1, 1, 1], [2, 2, 2], [3, 3, 3]],
    });
    expect(wire.rim_points).toEqual([[1, 1, 1], [2, 2, 2], [3, 3, 3]]);
    expect(wire).not.toHaveProperty("rim_mark");
  });

  it("falls back to legacy rim_mark when rimPoints is absent (curated prefills)", () => {
    const wire = toWireRunSiteInput({ ...baseSite, rimMark: [8, 9, 10] });
    expect(wire.rim_mark).toEqual([8, 9, 10]);
    expect(wire).not.toHaveProperty("rim_points");
  });

  it("falls back to legacy rim_mark when rimPoints is present but empty", () => {
    const wire = toWireRunSiteInput({ ...baseSite, rimMark: [8, 9, 10], rimPoints: [] });
    expect(wire.rim_mark).toEqual([8, 9, 10]);
    expect(wire).not.toHaveProperty("rim_points");
  });

  it("center_mark is still sent alongside rim_points (centre is just a locator, independent field)", () => {
    const wire = toWireRunSiteInput({
      ...baseSite,
      centerMark: [1, 1, 1],
      rimPoints: [[2, 2, 2], [3, 3, 3], [4, 4, 4]],
    });
    expect(wire.center_mark).toEqual([1, 1, 1]);
    expect(wire.rim_points).toEqual([[2, 2, 2], [3, 3, 3], [4, 4, 4]]);
  });
});

function makeWireCase(overrides: Partial<WireCase> = {}): WireCase {
  return {
    id: "case-1",
    doctor: "Dr. Test",
    jaw: "upper",
    vendor: "dess",
    scan_url: "/api/cases/case-1/scan",
    suggested_sites: [{ tooth: 4, center: [1, 2, 3], declared_variant: null }],
    ...overrides,
  };
}

describe("mapCase — suggestedSites centerMark/rimMark", () => {
  it("maps center_mark/rim_mark to camelCase Vec3s when present (prefill data)", () => {
    const wire = makeWireCase({
      suggested_sites: [
        {
          tooth: 4,
          center: [1, 2, 3],
          declared_variant: null,
          center_mark: [1, 2, 3],
          rim_mark: [4, 5, 3],
        },
      ],
    });
    const result = mapCase(wire);
    expect(result.suggestedSites[0]?.centerMark).toEqual([1, 2, 3]);
    expect(result.suggestedSites[0]?.rimMark).toEqual([4, 5, 3]);
  });

  it("maps centerMark/rimMark to null when absent (no pre-marked model)", () => {
    const wire = makeWireCase();
    const result = mapCase(wire);
    expect(result.suggestedSites[0]?.centerMark).toBeNull();
    expect(result.suggestedSites[0]?.rimMark).toBeNull();
  });

  it("maps centerMark/rimMark to null when explicitly null on the wire", () => {
    const wire = makeWireCase({
      suggested_sites: [
        { tooth: 4, center: [1, 2, 3], declared_variant: null, center_mark: null, rim_mark: null },
      ],
    });
    const result = mapCase(wire);
    expect(result.suggestedSites[0]?.centerMark).toBeNull();
    expect(result.suggestedSites[0]?.rimMark).toBeNull();
  });
});

describe("mapRunResult — fit", () => {
  it("maps fit.avg_mm/max_mm to camelCase avgMm/maxMm when present", () => {
    const wire = makeWireRunResult([makeWireRunSiteResult({ fit: { avg_mm: 0.28, max_mm: 2.4 } })]);
    const result = mapRunResult(wire);
    expect(result.summary.sites[0]?.fit).toEqual({ avgMm: 0.28, maxMm: 2.4 });
  });

  it("maps fit to null when absent from the wire payload (legacy cached run)", () => {
    const wire = makeWireRunSiteResult();
    // Simulate a legacy cached JSON blob computed before `fit` existed — the wire type
    // guarantees `fit` today, but real disk-cached data predating this feature will not.
    const { fit: _fit, ...withoutFit } = wire;
    const wireResult = makeWireRunResult([withoutFit as WireRunSiteResult]);
    const result = mapRunResult(wireResult);
    expect(result.summary.sites[0]?.fit).toBeNull();
  });

  it("does not affect sibling fields when fit is absent", () => {
    const wire = makeWireRunSiteResult({ tooth: 7, seed_source: "brush" });
    const { fit: _fit, ...withoutFit } = wire;
    const wireResult = makeWireRunResult([withoutFit as WireRunSiteResult]);
    const result = mapRunResult(wireResult);
    const site = result.summary.sites[0];
    expect(site?.tooth).toBe(7);
    expect(site?.seedSource).toBe("brush");
  });
});

describe("mapRunResult — seedSource", () => {
  it("passes through seed_source 'marks' (center_mark was sent) unchanged", () => {
    const wire = makeWireRunResult([makeWireRunSiteResult({ seed_source: "marks" })]);
    const result = mapRunResult(wire);
    expect(result.summary.sites[0]?.seedSource).toBe("marks");
  });

  it("passes through seed_source 'click' unchanged", () => {
    const wire = makeWireRunResult([makeWireRunSiteResult({ seed_source: "click" })]);
    const result = mapRunResult(wire);
    expect(result.summary.sites[0]?.seedSource).toBe("click");
  });
});

describe("mapRunResult — seatMethod / guidance", () => {
  it("maps seat_method through unchanged when present", () => {
    const wire = makeWireRunResult([makeWireRunSiteResult({ seat_method: "rim" })]);
    const result = mapRunResult(wire);
    expect(result.summary.sites[0]?.seatMethod).toBe("rim");
  });

  it("maps seatMethod to null when seat_method is absent (legacy cached run)", () => {
    const wire = makeWireRunResult([makeWireRunSiteResult()]);
    const result = mapRunResult(wire);
    expect(result.summary.sites[0]?.seatMethod).toBeNull();
  });

  it("maps guidance.level/actions to camelCase when present", () => {
    const wire = makeWireRunResult([
      makeWireRunSiteResult({
        guidance: {
          level: "attention",
          actions: ["Paint the cap area with the brush (🖌 Mark cap) and re-run."],
        },
      }),
    ]);
    const result = mapRunResult(wire);
    expect(result.summary.sites[0]?.guidance).toEqual({
      level: "attention",
      actions: ["Paint the cap area with the brush (🖌 Mark cap) and re-run."],
    });
  });

  it("maps guidance to null when absent (legacy cached run)", () => {
    const wire = makeWireRunResult([makeWireRunSiteResult()]);
    const result = mapRunResult(wire);
    expect(result.summary.sites[0]?.guidance).toBeNull();
  });
});

describe("mapRunResult — rimAgreementMm", () => {
  it("maps rim_agreement_mm through unchanged when present", () => {
    const wire = makeWireRunResult([makeWireRunSiteResult({ rim_agreement_mm: 0.55 })]);
    const result = mapRunResult(wire);
    expect(result.summary.sites[0]?.rimAgreementMm).toBe(0.55);
  });

  it("maps rimAgreementMm to null when rim_agreement_mm is absent (legacy cached run)", () => {
    const wire = makeWireRunResult([makeWireRunSiteResult()]);
    const result = mapRunResult(wire);
    expect(result.summary.sites[0]?.rimAgreementMm).toBeNull();
  });

  it("maps rimAgreementMm to null when rim_agreement_mm is explicitly null (not computable)", () => {
    const wire = makeWireRunResult([makeWireRunSiteResult({ rim_agreement_mm: null })]);
    const result = mapRunResult(wire);
    expect(result.summary.sites[0]?.rimAgreementMm).toBeNull();
  });

  it("maps border_click_disagreement_mm through when present", () => {
    const wire = makeWireRunResult([makeWireRunSiteResult({ border_click_disagreement_mm: 0.89 })]);
    const result = mapRunResult(wire);
    expect(result.summary.sites[0]?.borderClickDisagreementMm).toBe(0.89);
  });

  it("maps borderClickDisagreementMm to null when absent (legacy cached run)", () => {
    const wire = makeWireRunResult([makeWireRunSiteResult()]);
    const result = mapRunResult(wire);
    expect(result.summary.sites[0]?.borderClickDisagreementMm).toBeNull();
  });

  it("maps top_face_agreement_mm through when present", () => {
    const wire = makeWireRunResult([makeWireRunSiteResult({ top_face_agreement_mm: 2.45 })]);
    const result = mapRunResult(wire);
    expect(result.summary.sites[0]?.topFaceAgreementMm).toBe(2.45);
  });

  it("maps the confidence block through when present", () => {
    const wire = makeWireRunResult([makeWireRunSiteResult({
      confidence: { grade: "medium", pose_pos_spread_mm: 0.9, pose_axis_spread_deg: 11 },
    })]);
    const c = mapRunResult(wire).summary.sites[0]?.confidence;
    expect(c).toEqual({ grade: "medium", posSpreadMm: 0.9, axisSpreadDeg: 11 });
  });

  it("maps confidence to null when absent (opt-in / legacy run)", () => {
    const result = mapRunResult(makeWireRunResult([makeWireRunSiteResult()]));
    expect(result.summary.sites[0]?.confidence).toBeNull();
  });

  it("maps topFaceAgreementMm to null when absent (legacy cached run)", () => {
    const wire = makeWireRunResult([makeWireRunSiteResult()]);
    const result = mapRunResult(wire);
    expect(result.summary.sites[0]?.topFaceAgreementMm).toBeNull();
  });

  it("does not affect sibling fields (coverage stays on the domain object, just unused by the UI)", () => {
    const wire = makeWireRunResult([makeWireRunSiteResult({ rim_agreement_mm: 0.41, coverage: 0.41 })]);
    const result = mapRunResult(wire);
    expect(result.summary.sites[0]?.coverage).toBe(0.41);
    expect(result.summary.sites[0]?.rimAgreementMm).toBe(0.41);
  });
});

describe("mapRunResult — capSurfaceExplainedPct", () => {
  it("maps cap_surface_explained_pct through unchanged when present", () => {
    const wire = makeWireRunResult([makeWireRunSiteResult({ cap_surface_explained_pct: 78 })]);
    const result = mapRunResult(wire);
    expect(result.summary.sites[0]?.capSurfaceExplainedPct).toBe(78);
  });

  it("maps capSurfaceExplainedPct to null when cap_surface_explained_pct is absent (legacy cached run)", () => {
    const wire = makeWireRunResult([makeWireRunSiteResult()]);
    const result = mapRunResult(wire);
    expect(result.summary.sites[0]?.capSurfaceExplainedPct).toBeNull();
  });

  it("maps capSurfaceExplainedPct to null when cap_surface_explained_pct is explicitly null (not computable)", () => {
    const wire = makeWireRunResult([makeWireRunSiteResult({ cap_surface_explained_pct: null })]);
    const result = mapRunResult(wire);
    expect(result.summary.sites[0]?.capSurfaceExplainedPct).toBeNull();
  });

  it("is independent of rimAgreementMm (the two honest numbers map separately)", () => {
    const wire = makeWireRunResult([
      makeWireRunSiteResult({ rim_agreement_mm: 0.55, cap_surface_explained_pct: 78 }),
    ]);
    const result = mapRunResult(wire);
    expect(result.summary.sites[0]?.rimAgreementMm).toBe(0.55);
    expect(result.summary.sites[0]?.capSurfaceExplainedPct).toBe(78);
  });
});

describe("mapRunResult — variant.candidates", () => {
  it("maps candidates to camelCase VariantCandidate[], preserving best-first order", () => {
    const wire = makeWireRunResult([
      makeWireRunSiteResult({
        variant: {
          identified: "6020",
          declared: null,
          measured_rim_diameter_mm: 6.1,
          diameter_class_margin_mm: 0.4,
          flags: [],
          candidates: [
            { variant: "6020", seat_residual_mm: 0.491 },
            { variant: "5030", seat_residual_mm: 0.528 },
          ],
        },
      }),
    ]);
    const result = mapRunResult(wire);
    expect(result.summary.sites[0]?.variant.candidates).toEqual([
      { variant: "6020", seatResidualMm: 0.491 },
      { variant: "5030", seatResidualMm: 0.528 },
    ]);
  });

  it("maps candidates to null when explicitly null (ICP-seated site)", () => {
    const wire = makeWireRunResult([
      makeWireRunSiteResult({
        variant: {
          identified: "5020",
          declared: null,
          measured_rim_diameter_mm: 5.1,
          diameter_class_margin_mm: 0.5,
          flags: [],
          candidates: null,
        },
      }),
    ]);
    const result = mapRunResult(wire);
    expect(result.summary.sites[0]?.variant.candidates).toBeNull();
  });

  it("maps candidates to null when absent (legacy cached run)", () => {
    const wire = makeWireRunResult([makeWireRunSiteResult()]);
    const result = mapRunResult(wire);
    expect(result.summary.sites[0]?.variant.candidates).toBeNull();
  });
});

describe("agreementState", () => {
  const base: VariantAssessment = {
    identified: "5020",
    declared: null,
    measuredRimDiameterMm: 5.1,
    diameterClassMarginMm: 0.5,
    flags: [],
    candidates: null,
  };

  it("returns no-declaration when the doctor left it on auto", () => {
    expect(agreementState(base)).toEqual({ kind: "no-declaration" });
  });

  it("returns confirmed when declared is set and no flag disputes it", () => {
    expect(agreementState({ ...base, declared: "5020" })).toEqual({ kind: "confirmed" });
  });

  it("returns confirmed even with unrelated flags present, as long as none mention 'declared'", () => {
    const v = { ...base, declared: "5020", flags: ["registration could not seat cleanly"] };
    expect(agreementState(v)).toEqual({ kind: "confirmed" });
  });

  it("returns disputed with the flag text when a flag mentions the declaration mismatch", () => {
    const disputeFlag =
      "measured rim diameter 7.25mm suggests 7020/7030 but the doctor declared 5020 — verify before construction (billing + fit)";
    const v = { ...base, declared: "5020", flags: [disputeFlag] };
    expect(agreementState(v)).toEqual({ kind: "disputed", flag: disputeFlag });
  });

  it("picks the first flag that mentions 'declared' when multiple flags are present", () => {
    const disputeFlag = "measured rim diameter suggests X but the doctor declared Y";
    const v = {
      ...base,
      declared: "5020",
      flags: ["registration could not seat cleanly", disputeFlag],
    };
    expect(agreementState(v)).toEqual({ kind: "disputed", flag: disputeFlag });
  });
});

describe("mapLibraryVariants", () => {
  it("maps snake_case wire fields to camelCase domain fields", () => {
    const wire: WireLibraryVariant[] = [
      { variant: "5020", rim_diameter_mm: 4.6, height_mm: 3.4, mesh_url: "/api/cases/c1/library/5020/mesh" },
    ];
    expect(mapLibraryVariants(wire)).toEqual([
      { variant: "5020", rimDiameterMm: 4.6, heightMm: 3.4, meshUrl: "/api/cases/c1/library/5020/mesh" },
    ]);
  });

  it("passes through null dims (rim_diameter_mm/height_mm may be null)", () => {
    const wire: WireLibraryVariant[] = [
      { variant: "6030", rim_diameter_mm: null, height_mm: null, mesh_url: "/api/cases/c1/library/6030/mesh" },
    ];
    expect(mapLibraryVariants(wire)).toEqual([
      { variant: "6030", rimDiameterMm: null, heightMm: null, meshUrl: "/api/cases/c1/library/6030/mesh" },
    ]);
  });

  it("maps an empty catalog to an empty array", () => {
    expect(mapLibraryVariants([])).toEqual([]);
  });
});

describe("clocking + operator nudge mapping", () => {
  it("maps the coded-cutout clock instrument onto the run row", () => {
    const wire = makeWireRunSiteResult({
      clocking: {
        notch_shift_deg: -23.8,
        notch_corr: 0.502,
        notch_prominence: 0.079,
        evidence: "recess",
        consistency_deg: 12.5,
        rotation_unverified: true,
      },
      nudge: { operator_delta_deg: 3, cumulative_deg: 18 },
    });
    const site = mapRunResult(makeWireRunResult([wire])).summary.sites[0]!;
    expect(site.clocking).toEqual({
      notchShiftDeg: -23.8,
      notchCorr: 0.502,
      notchProminence: 0.079,
      evidence: "recess",
      consistencyDeg: 12.5,
      rotationUnverified: true,
    });
    expect(site.nudge).toEqual({ cumulativeDeg: 18 });
  });

  it("collapses absent clocking/nudge (legacy cache, icp seat) to null", () => {
    const site = mapRunResult(makeWireRunResult([makeWireRunSiteResult()])).summary.sites[0]!;
    expect(site.clocking).toBeNull();
    expect(site.nudge).toBeNull();
  });

  it("defaults the tri-state fields honestly when the wire omits them", () => {
    const wire = makeWireRunSiteResult({
      clocking: { notch_shift_deg: null, notch_corr: 0, notch_prominence: 0 },
    });
    const site = mapRunResult(makeWireRunResult([wire])).summary.sites[0]!;
    expect(site.clocking).toEqual({
      notchShiftDeg: null,
      notchCorr: 0,
      notchProminence: 0,
      evidence: "none",
      consistencyDeg: null,
      rotationUnverified: false,
    });
  });
});

describe("mapNudgeResult", () => {
  it("maps the nudge response, including the re-read residual", () => {
    const wire: WireNudgeResult = {
      tooth: 29,
      applied_delta_deg: -15,
      cumulative_deg: -12,
      stability_excess_mm: 0.04,
      clocking: { notch_shift_deg: -1.8, notch_corr: 0.61, notch_prominence: 0.3 },
      nudge: { operator_delta_deg: -15, cumulative_deg: -12 },
      files: ["c-29-healingcap-aligned.stl", "c-29-implant.json"],
    };
    expect(mapNudgeResult(wire)).toEqual({
      tooth: 29,
      appliedDeltaDeg: -15,
      cumulativeDeg: -12,
      stabilityExcessMm: 0.04,
      clocking: {
        notchShiftDeg: -1.8,
        notchCorr: 0.61,
        notchProminence: 0.3,
        evidence: "none",
        consistencyDeg: null,
        rotationUnverified: false,
      },
      nudge: { cumulativeDeg: -12 },
    });
  });

  it("passes through the null stability excess of a reset (no re-judging needed)", () => {
    const wire: WireNudgeResult = {
      tooth: 29,
      applied_delta_deg: -18,
      cumulative_deg: 0,
      stability_excess_mm: null,
      clocking: { notch_shift_deg: 23.8, notch_corr: 0.5, notch_prominence: 0.08 },
      nudge: { operator_delta_deg: -18, cumulative_deg: 0 },
      files: [],
    };
    expect(mapNudgeResult(wire).stabilityExcessMm).toBeNull();
    expect(mapNudgeResult(wire).cumulativeDeg).toBe(0);
  });
});

describe("mapProposeResult — capture gate", () => {
  const wireCapture: WireCaptureAssessment = {
    verdict: "rescan",
    rim_z_mm: 1.01,
    checks: [
      {
        name: "rim_arc",
        value: 0.542,
        bound_pass: 0.92,
        bound_rescan: 0.55,
        verdict: "rescan",
        message: "Rescan the rim on the tongue-facing (lingual) side — 46% of the ring is missing",
      },
    ],
  };

  it("maps each proposal's capture block to camelCase, and folds proposals + suggested sites into captureSites", () => {
    const wire: WireProposeResult = {
      proposals: [
        { center: [1, 2, 3], void_ratio: 0.2, rim_below_cusps_mm: 5.5, capture: wireCapture },
      ],
      duration_s: 2.0,
      cached: true,
      suggested_capture: [
        { tooth: 7, center: [21, 36.2, 19.5], capture: { ...wireCapture, verdict: "pass" } },
      ],
    };
    const mapped = mapProposeResult(wire);
    expect(mapped.proposals[0]?.capture?.verdict).toBe("rescan");
    expect(mapped.proposals[0]?.capture?.checks[0]).toEqual({
      name: "rim_arc",
      value: 0.542,
      boundPass: 0.92,
      boundRescan: 0.55,
      verdict: "rescan",
      message: "Rescan the rim on the tongue-facing (lingual) side — 46% of the ring is missing",
    });
    expect(mapped.captureSites).toHaveLength(2);
    expect(mapped.captureSites[0]).toMatchObject({ center: [1, 2, 3], tooth: null });
    expect(mapped.captureSites[1]).toMatchObject({ center: [21, 36.2, 19.5], tooth: 7 });
    expect(mapped.captureSites[1]?.capture.verdict).toBe("pass");
  });

  it("collapses an absent capture (legacy backend payload) to null and an empty captureSites", () => {
    const wire: WireProposeResult = {
      proposals: [{ center: [1, 2, 3], void_ratio: 0.2, rim_below_cusps_mm: 5.5 }],
      duration_s: 2.0,
      cached: true,
    };
    const mapped = mapProposeResult(wire);
    expect(mapped.proposals[0]?.capture).toBeNull();
    expect(mapped.captureSites).toEqual([]);
  });
});

describe("toWireImportPose", () => {
  const doc: PoseTransferDocument = {
    format: "artech.pose-transfer",
    version: 1,
    caseId: "276794487-zimmer-4.5",
    exportedAt: "2026-07-25T12:00:00.000Z",
    selection: {
      model: "neodent-gm",
      constructionPathId: "zimmer/ti-base.stl",
      jaw: "upper",
      gingivalOffsetMm: 0.2,
    },
    sites: [
      {
        tooth: 3,
        variantId: "6020",
        poseMatrix: [
          [0, -1, 0, 10],
          [1, 0, 0, -4],
          [0, 0, 1, 2.5],
          [0, 0, 0, 1],
        ],
        provenance: {
          seedSource: "marks",
          seatMethod: "rim",
          nudgeCumulativeDeg: 12.5,
          rotationUnverified: false,
          clockEvidence: "codes",
          identifiedVariant: "6020",
          doctorConfirmed: null,
          doctorNote: null,
          doctorConfirmedAt: null,
        },
      },
    ],
  };

  it("sends the matrix UNCHANGED and the rest as audit provenance", () => {
    const body = toWireImportPose(doc, doc.sites[0] as (typeof doc.sites)[number]);
    // the pipeline's own implant.json matrix, not a re-derivation
    expect(body.pose_matrix).toBe(doc.sites[0]?.poseMatrix);
    expect(body.source).toEqual({
      case_id: "276794487-zimmer-4.5",
      exported_at: "2026-07-25T12:00:00.000Z",
      format_version: 1,
      model: "neodent-gm",
      variant: "6020",
      construction_path: "zimmer/ti-base.stl",
      jaw: "upper",
      gingival_offset_mm: 0.2,
      nudge_cumulative_deg: 12.5,
      seat_method: "rim",
    });
  });
});
