/**
 * Payload fixtures shaped exactly like the BFF's response models (api/client.ts is
 * the hand-written mirror), so component tests exercise the real seam shapes.
 */
import type {
  CaseSessionDetail,
  SiteView,
  WorklistRow,
} from "../api/client";

export function siteView(overrides: Partial<SiteView> = {}): SiteView {
  return {
    tooth: 30,
    status: "detected",
    declared_variant: null,
    suggested_variant: "RP",
    center: [1.0, 2.0, 3.0],
    ...overrides,
  };
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
    ...overrides,
  };
}
