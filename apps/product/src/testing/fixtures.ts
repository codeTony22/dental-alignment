/**
 * Payload fixtures shaped exactly like the BFF's response models (api/client.ts is
 * the hand-written mirror), so component tests exercise the real seam shapes.
 */
import type {
  AssuranceSite,
  AssuranceView,
  CaptureAssessmentView,
  CaseSessionDetail,
  DetectedProposalView,
  DetectionView,
  SitePreviewPayload,
  SiteView,
  WorklistRow,
  WorklistRowError,
} from "../api/client";

export function captureAssessment(
  overrides: Partial<CaptureAssessmentView> = {},
): CaptureAssessmentView {
  return {
    verdict: "pass",
    rim_z_mm: 1.2,
    checks: [
      {
        name: "rim_arc",
        value: 0.92,
        bound_pass: 0.75,
        bound_rescan: 0.5,
        verdict: "pass",
        message: "92% of the rim arc is captured.",
      },
    ],
    ...overrides,
  };
}

/** A rescan-grade assessment whose worst check carries the worker's sentence. */
export function rescanAssessment(message: string): CaptureAssessmentView {
  return captureAssessment({
    verdict: "rescan",
    checks: [
      {
        name: "rim_arc",
        value: 0.31,
        bound_pass: 0.75,
        bound_rescan: 0.5,
        verdict: "rescan",
        message,
      },
    ],
  });
}

export function siteView(overrides: Partial<SiteView> = {}): SiteView {
  return {
    tooth: 30,
    status: "detected",
    declared_variant: null,
    suggested_variant: "RP",
    center: [1.0, 2.0, 3.0],
    capture: null,
    // the preview's seat facts: honestly absent until a preview has run (the BFF
    // clears them at every reset boundary with the rung that justified them)
    seat_method: null,
    rim_agreement_mm: null,
    ...overrides,
  };
}

export function detectedProposal(
  overrides: Partial<DetectedProposalView> = {},
): DetectedProposalView {
  return {
    center: [1.0, 2.0, 3.0],
    void_ratio: 0.1,
    rim_below_cusps_mm: 0.5,
    tooth_guess: 30,
    capture: captureAssessment(),
    ...overrides,
  };
}

export function detectionView(
  proposals: DetectedProposalView[] = [detectedProposal()],
): DetectionView {
  return { proposals };
}

/** A catalog entry row, shaped like adapters/library_catalog's serialized entries
 * (the BFF passes them through verbatim). */
export function catalogEntry(
  overrides: Partial<Record<string, unknown>> = {},
): Record<string, unknown> {
  return {
    id: "5020",
    variant: "5020",
    label: "5.0 × 2.0",
    rim_diameter_mm: 5.0,
    height_mm: 2.0,
    filename: "conical-4x4-5020.stl",
    sha256: "0".repeat(64),
    flags: [],
    duplicate_of: [],
    mesh_url: "/api/library/conical-4x4/5020/mesh",
    ...overrides,
  };
}

/** A catalog group as the worker serves it: model + legacy flag + variant entries. */
export function catalogGroup(
  model = "conical-4x4",
  variants: Array<Record<string, unknown>> = [catalogEntry()],
  legacy = false,
): Record<string, unknown> {
  return { model, legacy, variants };
}

export function caseSessionDetail(
  overrides: Partial<CaseSessionDetail> = {},
): CaseSessionDetail {
  return {
    case: {
      id: "case-a",
      doctor: "Dr. Rivera",
      jaw: "lower",
      scan_filename: "scan.stl",
      suggested_model: "conical-4x4",
      suggested_construction: null,
    },
    sites: [siteView({ tooth: 19 }), siteView({ tooth: 30 })],
    system: { effective_model: "conical-4x4", source: "suggested" },
    catalog: { groups: [], constructions: [] },
    relief_ceilings: [],
    detection: null,
    choices: {
      construction_path: null,
      jaw: null,
      gingival_offset_mm: null,
      gingival_offset_default_mm: 0.2,
      // this fixture case carries NO construction suggestion, so the effective
      // construction is honestly absent and completeness fails with it — the
      // BFF's attribution shapes, mirrored (client 2026-07-27)
      effective_construction: { value: null, source: "none" },
      effective_jaw: { value: "lower", source: "suggested" },
      effective_relief: { value: 0.2, source: "default" },
      complete: false,
    },
    session: {
      tenant_id: "local",
      adjust_visited: false,
      adjust_decision: null,
      run_state: "none",
      run_refusal: null,
      confirmed: false,
      payment_authorized: false,
      confirmation: null,
      payment: null,
      release: null,
      released: false,
    },
    ...overrides,
  };
}

/** A Declare-complete detail (5c): every site READY over a declared variant, the
 * choices complete, no current run — exactly the facts the run auto-fire reads. */
export function runnableDetail(
  overrides: Partial<CaseSessionDetail> = {},
): CaseSessionDetail {
  return caseSessionDetail({
    sites: [
      siteView({ tooth: 19, status: "ready", declared_variant: "5020" }),
      siteView({ tooth: 30, status: "ready", declared_variant: "6020" }),
    ],
    choices: {
      construction_path: "dess/conical-scanbody.stl",
      jaw: "lower",
      gingival_offset_mm: 0.2,
      gingival_offset_default_mm: 0.2,
      effective_construction: {
        value: "dess/conical-scanbody.stl",
        source: "chosen",
      },
      effective_jaw: { value: "lower", source: "chosen" },
      effective_relief: { value: 0.2, source: "chosen" },
      complete: true,
    },
    ...overrides,
  });
}

/** The preview payload as the worker serves it (application/preview.py — the demo's
 * wire shape verbatim; worker test_preview.py pins the key set on the real tree). */
export function sitePreviewPayload(
  overrides: Partial<SitePreviewPayload> = {},
): SitePreviewPayload {
  return {
    case_id: "case-a",
    tooth: 19,
    implant_model: "conical-4x4",
    variant: "5020",
    frame: "jaw-scan world frame",
    units: "mm",
    pose: { axis: [0, 0, 1], x_axis: [1, 0, 0], origin: [1, 2, 3] },
    n_points: 3,
    points: [
      [0, 0, 0],
      [1, 0, 0],
      [0, 1, 0],
    ],
    faces: [[0, 1, 2]],
    deviation_mm: [0.1, -0.2, null],
    scale: {
      clamp_mm: 0.5,
      min_mm: -0.5,
      max_mm: 0.5,
      colormap: "RdBu_r",
      sign_convention: "+ = scan outside the cap surface",
      data_min_mm: -0.2,
      data_max_mm: 0.1,
      footprint_band_mm: 1.0,
    },
    stats: {
      rms_mm: 0.43,
      p90_mm: 0.71,
      n_footprint: 1200,
      n_samples: 4000,
      source: "area-uniform surface samples (the acceptance difference map)",
    },
    vertex_footprint_points: 900,
    reporting_only: true,
    preview: true,
    seat: { seat_method: "rim-seat", rim_agreement_mm: 0.07, fit: "ok" },
    ...overrides,
  };
}

export function worklistRow(overrides: Partial<WorklistRow> = {}): WorklistRow {
  return {
    id: "case-a",
    doctor: "Dr. Rivera",
    jaw: "lower",
    suggested_model: "conical-4x4",
    sites: { total: 2, declared: 0, ready: 0, flagged: 0 },
    run_state: "none",
    confirmed: false,
    released: false,
    detected: false,
    choices_complete: false,
    error: null,
    ...overrides,
  };
}

/** The per-row error contract's shape (slice 5a): identity + the BFF's refusal,
 * every session-derived fact honestly null. */
export function worklistErrorRow(
  overrides: Partial<WorklistRowError> = {},
): WorklistRowError {
  return {
    id: "case-corrupt",
    doctor: "Dr. Rivera",
    jaw: "lower",
    suggested_model: null,
    sites: null,
    run_state: null,
    confirmed: null,
    released: null,
    detected: null,
    choices_complete: null,
    error: "corrupt session file session.json — refusing to silently reset flow state",
    ...overrides,
  };
}

/** One assurance table row as the BFF projects it (bff/resources/deliver.py —
 * the run summary's facts beside the acceptance catalog's references). */
export function assuranceSite(overrides: Partial<AssuranceSite> = {}): AssuranceSite {
  return {
    tooth: 19,
    status: "ready",
    declared_variant: "5020",
    identified_variant: "5020",
    variant_agreement: "match",
    seat_method: "rim-seat",
    rim_agreement_mm: 0.07,
    rotation: { deg: 0.7, evidence: "codes", unverified: false },
    deviation_rms_mm: 0.43,
    deviation_p90_mm: 0.71,
    gate: { level: "ready", actions: [] },
    clamp: { requested_mm: 0.2, applied_mm: 0.2, clamped: false, reason: null },
    qc_images: ["case-a-19-clockview.png", "case-a-19-deviation.png"],
    references: {
      rim_agreement_mm: {
        key: "rim_agreement_mm",
        label: "Rim seating agreement (p90)",
        unit: "mm",
        value: 0.07,
        display: "0.07 mm",
        band: "pass",
        industry_ref: {
          value: "no direct commercial number; scan-body agreement literature 38–425 µm",
          source: "alignment-algorithm-survey addendum",
        },
        note: null,
      },
    },
    ...overrides,
  };
}

/** A flagged row: the run's evidence flags the site; its gate carries the words. */
export function flaggedAssuranceSite(
  overrides: Partial<AssuranceSite> = {},
): AssuranceSite {
  return assuranceSite({
    tooth: 30,
    status: "flagged",
    gate: {
      level: "attention",
      actions: [
        "The cap's ROTATION could not be verified — visually check the coded features.",
      ],
    },
    rotation: { deg: null, evidence: "none", unverified: true },
    qc_images: ["case-a-30-clockview.png", "case-a-30-deviation.png"],
    ...overrides,
  });
}

/** The table as the BFF serves it: worst-first, flags pinned on top (AM-12). */
export function assuranceView(overrides: Partial<AssuranceView> = {}): AssuranceView {
  return {
    case_id: "case-a",
    run_id: "20260727-120000-abc123",
    relief: {
      gingival_offset_requested_mm: 0.2,
      gingival_offset_applied_mm: 0.2,
      clamped: false,
    },
    sites: [flaggedAssuranceSite(), assuranceSite()],
    ...overrides,
  };
}
