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
    ...overrides,
  };
}
