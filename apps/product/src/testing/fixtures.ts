/**
 * Payload fixtures shaped exactly like the BFF's response models (api/client.ts is
 * the hand-written mirror), so component tests exercise the real seam shapes.
 */
import type {
  ActivityEntryView,
  AssuranceSite,
  AssuranceView,
  CaptureAssessmentView,
  CaseActivityView,
  CaseSessionDetail,
  DetectedProposalView,
  DetectionView,
  InvoiceView,
  RePreviewView,
  SiteAcceptanceMetric,
  SiteAcceptanceView,
  SiteAdjustmentView,
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
      teeth: [19, 30],
      scan_bytes: 31_800_000,
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
      turnaround: null,
      effective_construction: { value: null, source: "none" },
      effective_jaw: { value: "lower", source: "suggested" },
      effective_relief: { value: 0.2, source: "default" },
      // a case nobody expedited is a standard case — the standing default, and it
      // never gates `complete`
      effective_turnaround: { value: "standard", source: "default" },
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
      release_preview: null,
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
      turnaround: null,
      effective_jaw: { value: "lower", source: "chosen" },
      effective_relief: { value: 0.2, source: "chosen" },
      effective_turnaround: { value: "standard", source: "default" },
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
    teeth: [19, 30],
    scan_bytes: 31_800_000,
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
    // DISCOVERY facts survive the error contract: a corrupt session says nothing
    // about the data tree
    teeth: [19, 30],
    scan_bytes: 31_800_000,
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
    rotation: {
      deg: 0.7,
      evidence: "codes",
      unverified: false,
      // nobody hand-rotated this site: the run's own certified pose ships
      operator_cumulative_deg: null,
    },
    deviation_rms_mm: 0.43,
    deviation_p90_mm: 0.71,
    // the run's own words, and they still describe the pose that shipped
    gate: { level: "ready", actions: [], stale: false },
    clamp: { requested_mm: 0.2, applied_mm: 0.2, clamped: false, reason: null },
    production_note: null,
    stale_metrics: [],
    matching_diameter_mm: null,
    correspondence: null,
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
        // the catalog's own thresholds, so "how much room is left" is answered
        // from a cited number and never from a tolerance this app holds
        bands: { pass: 0.5, review: 1.6 },
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
      stale: false,
    },
    rotation: {
      deg: null,
      evidence: "none",
      unverified: true,
      operator_cumulative_deg: null,
    },
    qc_images: ["case-a-30-clockview.png", "case-a-30-deviation.png"],
    ...overrides,
  });
}

/** A site someone reworked by hand: the operator's cumulative rotation, the best-fit
 * dial it was refined at, and the correspondence the shipped pose stands on — the
 * three facts the alignment-metrics strip reads (gap
 * ``per-site-pairs-rotation-diameter``). Two of the three pairs came from spans,
 * hence 3 pairs / 5 observations. */
export function reworkedAssuranceSite(
  overrides: Partial<AssuranceSite> = {},
): AssuranceSite {
  return assuranceSite({
    status: "adjusted",
    rotation: {
      deg: 1.4,
      evidence: "codes",
      unverified: false,
      operator_cumulative_deg: 12.5,
    },
    matching_diameter_mm: 0.45,
    correspondence: {
      pairs: 3,
      observations: 5,
      max_pairs: 8,
      residual_rms_mm: 0.08,
    },
    stale_metrics: ["rim_agreement_mm", "guidance"],
    // the rework re-derived the measurements and could not re-derive the gate, so
    // the words beside this row predate it — the server says so, the surface reads
    // it (gap ``re-preview-a-site-without-applying-a-tool``)
    gate: { level: "attention", actions: ["Re-read this site over its new panes."],
            stale: true },
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
    adjustments: null,
    sites: [flaggedAssuranceSite(), assuranceSite()],
    ...overrides,
  };
}

/** The priced case as the BFF derives it (bff/pricing.py). Amounts are integer
 * CENTS and the rates are PLACEHOLDERS — `status: "placeholder"` is a server fact
 * the surface badges, exactly like the terms text. Nothing here is ever computed
 * client-side; a price is the money-shaped cousin of a verdict. */
export function invoiceView(overrides: Partial<InvoiceView> = {}): InvoiceView {
  return {
    case_id: "case-a",
    run_id: "20260727-120000-abc123",
    currency: "USD",
    rate_card_version: "placeholder-v1",
    status: "placeholder",
    note:
      "PLACEHOLDER RATES — pending the client's price list. The figures are the " +
      "design prototype's ($32 per site standard, $48 rush, exceptions at half " +
      "rate) and are not a quotation.",
    turnaround: "standard",
    turnaround_source: "default",
    lines: [
      {
        key: "released_sites",
        label: "1 released site",
        quantity: 1,
        unit_amount_cents: 3200,
        amount_cents: 3200,
        billed: true,
      },
      {
        key: "exception_sites",
        label: "1 acknowledged exception, at half rate",
        quantity: 1,
        unit_amount_cents: 1600,
        amount_cents: 1600,
        billed: true,
      },
      {
        // included at zero and still BILLED — it repriced every line above
        key: "turnaround",
        label: "Standard turnaround",
        quantity: 1,
        unit_amount_cents: null,
        amount_cents: 0,
        billed: true,
      },
    ],
    total_cents: 4800,
    paid: null,
    ...overrides,
  };
}

/** One acceptance metric as the catalog evaluated it for a single site
 * (bff/resources/deliver.SiteAcceptanceView) — the measured value, the band it
 * falls in, and the band's OWN thresholds beside its cited industry reference. */
export function siteAcceptanceMetric(
  overrides: Partial<SiteAcceptanceMetric> = {},
): SiteAcceptanceMetric {
  return {
    key: "deviation_rms_mm",
    label: "Surface deviation map — RMS",
    unit: "mm",
    audience: "doctor",
    value: 0.43,
    display: "0.43 mm",
    band: "review",
    bands: { pass: 0.2, review: 0.5 },
    industry_ref: {
      value: "±0.5 mm map convention; 200 µm misfit-acceptability line",
      source: "alignment-perfection-strategy §1; PMC10756734",
    },
    note: "the same scalar printed on the deviation map (shared stats source)",
    ...overrides,
  };
}

/** One site's acceptance evaluation as the workspace reads it. NOT the design's
 * three-lever budget: every number here is measured over real mesh and every
 * threshold is the catalog's, not a tolerance held in the browser. */
export function siteAcceptanceView(
  overrides: Partial<SiteAcceptanceView> = {},
): SiteAcceptanceView {
  return {
    tooth: 19,
    run_id: "20260727-120000-abc123",
    overall_band: "review",
    missing: [],
    metrics: [
      siteAcceptanceMetric(),
      siteAcceptanceMetric({
        key: "rim_agreement_mm",
        label: "Rim seating agreement (p90)",
        value: 0.07,
        display: "0.07 mm",
        band: "pass",
        bands: { pass: 0.5, review: 1.6 },
        note: null,
      }),
    ],
    stale_metrics: [],
    context: {},
    ...overrides,
  };
}

/** One act on the case's narrative. Never constructed by the app in production —
 * the BFF appends these inside the write that lands each act. */
export function activityEntry(
  overrides: Partial<ActivityEntryView> = {},
): ActivityEntryView {
  return {
    at: "2026-07-31T09:15:00+00:00",
    event: "run-authorized",
    detail: "run 20260727-120000-abc123 authorized over 2 reviewed sites",
    tooth: null,
    ...overrides,
  };
}

/** One entry off a site's shipped record, as the worker wrote it — `who` carries
 * its own disclaimer verbatim. */
export function siteAdjustment(
  overrides: Partial<SiteAdjustmentView> = {},
): SiteAdjustmentView {
  return {
    tooth: 19,
    at: "2026-07-31T09:22:41",
    operation: "rotation",
    who: "operator (no identity is captured)",
    detail: "rotated +5.0° about the part axis",
    ...overrides,
  };
}

/** The case's narrative as the BFF serves it: newest first, bounded, and honest
 * about what the window does not hold (`recorded` vs `window`). */
export function caseActivityView(
  overrides: Partial<CaseActivityView> = {},
): CaseActivityView {
  return {
    case_id: "case-a",
    entries: [
      activityEntry({
        event: "site-adjusted",
        detail: "rotation — rotated +5.0° about the part axis",
        tooth: 19,
        at: "2026-07-31T09:22:41+00:00",
      }),
      activityEntry({
        event: "run-landed",
        detail: "run 20260727-120000-abc123 completed — verdicts written for 2 sites, 1 flagged",
        at: "2026-07-31T09:16:04+00:00",
      }),
      activityEntry(),
    ],
    recorded: 3,
    window: 40,
    run_id: "20260727-120000-abc123",
    site_adjustments: [siteAdjustment()],
    ...overrides,
  };
}

/** WHAT A RE-READ FOUND, with nothing having moved: the row still describes the
 * pose on disk. `changed` is the server's answer, never a comparison made here. */
export function rePreviewView(
  overrides: Partial<RePreviewView> = {},
): RePreviewView {
  return {
    tooth: 19,
    run_id: "20260727-120000-abc123",
    changed: false,
    rederived: { deviation_rms_mm: 0.43, deviation_p90_mm: 0.71 },
    previous: { deviation_rms_mm: 0.43, deviation_p90_mm: 0.71 },
    stale_metrics: [],
    pane_payload: sitePreviewPayload(),
    case: caseSessionDetail(),
    ...overrides,
  };
}
