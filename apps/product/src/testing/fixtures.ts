/**
 * Payload fixtures shaped exactly like the BFF's response models (api/client.ts is
 * the hand-written mirror), so component tests exercise the real seam shapes.
 */
import type {
  CaptureAssessmentView,
  CaseSessionDetail,
  DetectedProposalView,
  DetectionView,
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
      complete: false,
    },
    session: {
      tenant_id: "local",
      adjust_visited: false,
      run_state: "none",
      confirmed: false,
      payment_authorized: false,
    },
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
    detected: null,
    choices_complete: null,
    error: "corrupt session file session.json — refusing to silently reset flow state",
    ...overrides,
  };
}
