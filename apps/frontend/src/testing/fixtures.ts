import type { CaseRow, SignalEnvelope, TechniqueResultView } from "../api/client";
import { SIGNAL_GROUP_ORDER } from "../domain/signals";

export const SIGNAL_GROUPS = SIGNAL_GROUP_ORDER;

export function emptyGroup(): Record<string, unknown> {
  return {};
}

export function signalEnvelope(overrides: Partial<SignalEnvelope> = {}): SignalEnvelope {
  const groups: Record<string, Record<string, unknown>> = {};
  for (const name of SIGNAL_GROUP_ORDER) {
    groups[name] = { present: true };
  }
  groups["residue"] = { deviation_rms_mm: 0.43, deviation_p90_mm: 0.71 };
  groups["clocking"] = { notch_shift_deg: -1.0, rotation_unverified: false };
  groups["correspondence"] = { pair_count: 0, cross_checked: null };
  groups["certification"] = { guidance_level: "attention", rotation_unverified: false };
  groups["guidance"] = { level: "attention", actions: ["The cap's ROTATION could not be verified."] };
  groups["acceptance"] = {
    overall_band: "review",
    catalog_keys: ["fit_avg_mm", "deviation_rms_mm"],
    metrics: [
      { key: "deviation_rms_mm", label: "Surface deviation map — RMS", band: "review", display: "0.43 mm" },
    ],
  };
  groups["landmarks"] = { items: [{ id: "code-1", lever_arm_mm: 2.1 }], missing: false };
  groups["measurement_honesty"] = { stale_metrics: ["rim_agreement_mm"], cross_checked: null };
  groups["capture"] = { rim_arc_bins: 12 };
  groups["seat"] = { seat_method: "rim-seat", rim_agreement_mm: 0.07 };
  groups["fit"] = { fit_avg_mm: 0.21 };
  groups["stability"] = { confidence_grade: "high" };
  return {
    tooth: 4,
    case_id: "neodent-gm",
    run_id: "run-1",
    group_names: SIGNAL_GROUP_ORDER,
    groups,
    ...overrides,
  };
}

export function techniqueResult(
  mode: "deterministic" | "intelligence" = "intelligence",
  overrides: Partial<TechniqueResultView> = {},
): TechniqueResultView {
  const signals = signalEnvelope();
  return {
    mode,
    status: "applied",
    detail: mode === "intelligence" ? "walked the MCP surface" : "refined 0.12 mm",
    case_id: "neodent-gm",
    run_id: "run-1",
    tooth: 4,
    signal_groups: SIGNAL_GROUP_ORDER,
    signals_before: signals,
    signals_after: signals,
    outcome: {
      tooth: 4,
      operation: "best-fit",
      detail: "refined 0.12 mm",
      applied: true,
      stale_metrics: ["rim_agreement_mm", "guidance"],
    },
    refusals: [],
    trace: mode === "intelligence"
      ? [
          { name: "get_landmarks", classification: "READ", ok: true, detail: "1 landmarks" },
          { name: "get_seated", classification: "READ", ok: true, detail: "seated pose" },
          { name: "get_site_signals", classification: "READ", ok: true, detail: "full taxonomy" },
          { name: "get_acceptance", classification: "READ", ok: true, detail: "review" },
          { name: "dry_run_best_fit", classification: "DRY_RUN", ok: true, detail: "measured" },
          { name: "commit_best_fit", classification: "COMMIT", ok: true, detail: "refined 0.12 mm" },
        ]
      : [
          { name: "commit_best_fit", classification: "COMMIT", ok: true, detail: "refined 0.12 mm" },
        ],
    proposals: { landmarks: [{ id: "code-1" }], note: "part-half only" },
    ...overrides,
  };
}

export const CASES: readonly CaseRow[] = [
  {
    id: "neodent-gm",
    doctor: "Doctor Neodent GM",
    jaw: "upper",
    suggested_model: "neodent-gm",
    suggested_sites: [{ tooth: 4, declared_variant: "5020" }, { tooth: 13 }],
  },
];

export function servedFetch(handlers: Record<string, unknown>): typeof fetch {
  return (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    const key = `${method} ${url}`;
    if (!(key in handlers)) {
      return new Response(JSON.stringify({ detail: `unserved ${key}` }), { status: 404 });
    }
    const payload = handlers[key];
    if (payload && typeof payload === "object" && "status" in payload && "body" in payload) {
      const boxed = payload as { status: number; body: unknown };
      return new Response(JSON.stringify(boxed.body), { status: boxed.status });
    }
    return new Response(JSON.stringify(payload), { status: 200 });
  }) as typeof fetch;
}
