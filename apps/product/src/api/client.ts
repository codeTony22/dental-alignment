/**
 * THE BFF CLIENT — the product's only network surface (plan §1.3, §3): the case-session
 * reads plus slice 4's two actions (detect — a compute trigger; choices — operator
 * acts), reached through the vite proxy so no backend host is hard-coded here.
 *
 * Types below mirror the BFF's response models BY HAND (bff/resources/case_sessions.py
 * — WorklistRow, CaseSessionDetail and their parts); they are small, so codegen would
 * cost more than it saves. Field names are the wire's snake_case, verbatim, so a
 * mismatch is a loud typecheck failure at the seam instead of a silent one downstream.
 *
 * Error posture: every fetch resolves to an ApiResult — a BFF that is down or refusing
 * becomes a STATED error with words a person can act on, never a rejected promise a
 * component forgets to catch (a blank screen is a lie about the morning's worklist).
 */

/** AM-3's job states plus the BFF's "none" for a case that has never run. */
export type RunState = "none" | "queued" | "running" | "done" | "refused";

/** The site queue's states (plan §2), as the BFF's SiteStatus enum spells them. */
export type SiteStatus =
  | "detected"
  | "declared"
  | "previewed"
  | "ready"
  | "flagged"
  | "adjusted";

export interface SiteRollup {
  total: number;
  declared: number;
  ready: number;
  flagged: number;
}

/**
 * A healthy worklist row — every session-derived fact present and `error` null.
 * The wire shape is a union (see WorklistRowError): the BFF's per-row error contract
 * (slice 5a) sends `error` with the store's refusal and ALL session-derived fields
 * null when a case's session could not be read, so one corrupt file never takes the
 * whole list down. domain/worklist.ts's guard tells the two shapes apart.
 */
export interface WorklistRow {
  id: string;
  doctor: string;
  jaw: string;
  suggested_model: string | null;
  sites: SiteRollup;
  run_state: RunState;
  confirmed: boolean;
  detected: boolean;
  choices_complete: boolean;
  error: null;
}

/** The contract's other face: identity from discovery + the BFF's stated refusal. */
export interface WorklistRowError {
  id: string;
  doctor: string;
  jaw: string;
  suggested_model: string | null;
  sites: null;
  run_state: null;
  confirmed: null;
  detected: null;
  choices_complete: null;
  error: string;
}

/** One capture check, as the worker's CaptureCheck.to_dict spells it. */
export interface CaptureCheckView {
  name: string;
  value: number | null;
  bound_pass: number;
  bound_rescan: number;
  verdict: string;
  message: string;
}

/** A site's capture assessment (worker CaptureAssessment.to_dict): the overall verdict
 * is the WORST check — "rescan" is the chair-side moment Intake must surface first. */
export interface CaptureAssessmentView {
  verdict: "pass" | "marginal" | "rescan" | string;
  rim_z_mm: number | null;
  checks: CaptureCheckView[];
}

export interface SiteView {
  tooth: number;
  status: SiteStatus;
  declared_variant: string | null;
  suggested_variant: string | null;
  center: number[] | null;
  capture: CaptureAssessmentView | null;
}

/** A detector proposal: centre + evidence + the NON-BINDING tooth guess + capture. */
export interface DetectedProposalView {
  center: number[];
  void_ratio: number;
  rim_below_cusps_mm: number;
  tooth_guess: number | null;
  capture: CaptureAssessmentView;
}

export interface DetectionView {
  proposals: DetectedProposalView[];
}

/** The operator's case-level choices as persisted; `complete` is the BFF's derivation
 * (this app never computes completion itself — trust direction, AM-4). */
export interface ChoicesView {
  construction_path: string | null;
  jaw: string | null;
  gingival_offset_mm: number | null;
  gingival_offset_default_mm: number;
  complete: boolean;
}

export interface CaseView {
  id: string;
  doctor: string;
  jaw: string;
  scan_filename: string;
  suggested_model: string | null;
  suggested_construction: string | null;
}

/** Worker-shaped catalog rows pass through untyped — Declare (slice 5a) gives them
 * their real shapes when it actually renders them. */
export interface CatalogView {
  groups: Array<Record<string, unknown>>;
  constructions: Array<Record<string, unknown>>;
}

export interface ReliefCeilingView {
  variant: string;
  construction_path: string | null;
  model: string | null;
  max_safe_mm: number | null;
  requested_default_mm: number | null;
  default_is_safe: boolean | null;
  limited_by: string | null;
  wall_mm_at_zero: number | null;
  wall_mm_at_default: number | null;
  shippable_at_zero: boolean | null;
  min_wall_rule_mm: number | null;
  searched_to_mm: number | null;
  note: string | null;
  error: string | null;
}

export interface SessionView {
  tenant_id: string;
  adjust_visited: boolean;
  run_state: RunState;
  confirmed: boolean;
  payment_authorized: boolean;
}

export interface CaseSessionDetail {
  case: CaseView;
  sites: SiteView[];
  catalog: CatalogView;
  relief_ceilings: ReliefCeilingView[];
  detection: DetectionView | null;
  choices: ChoicesView;
  session: SessionView;
}

/**
 * An HTTP failure keeps its status so pages can tell a REFUSAL from an OUTAGE
 * (a 404 for a stale bookmark is not a down service — the banner copy branches
 * on this in pages/CaseShell.tsx). A network-level failure has no status: nothing
 * answered, so "unreachable" is the honest diagnosis.
 */
export type ApiResult<T> =
  | { kind: "ok"; data: T }
  | { kind: "error"; detail: string; status?: number };

/** What a fetching component holds: the result, or the honest in-between. */
export type FetchState<T> = { kind: "loading" } | ApiResult<T>;

/**
 * A pydantic-shaped 422 carries a LIST of error rows; each row's `msg` holds the
 * backend's own sentence behind a "Value error, " prefix pydantic adds. The prefix is
 * machinery, the sentence is the refusal — surface the sentences, joined.
 */
export function refusalDetail(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((row: unknown) =>
        typeof row === "object" && row !== null &&
        typeof (row as Record<string, unknown>)["msg"] === "string"
          ? ((row as Record<string, unknown>)["msg"] as string).replace(
              /^Value error, /,
              "",
            )
          : null,
      )
      .filter((msg): msg is string => msg !== null);
    if (messages.length > 0) return messages.join("; ");
  }
  return null;
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch (err: unknown) {
    return {
      kind: "error",
      detail: err instanceof Error ? err.message : String(err),
    };
  }
  if (!response.ok) {
    // FastAPI refusals carry {"detail": ...} — a sentence, or pydantic's error rows.
    let detail = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      const stated = refusalDetail(body.detail);
      if (stated !== null) detail = `HTTP ${response.status} — ${stated}`;
    } catch {
      // a non-JSON error body still yields the status line above
    }
    return { kind: "error", detail, status: response.status };
  }
  try {
    return { kind: "ok", data: (await response.json()) as T };
  } catch (err: unknown) {
    return {
      kind: "error",
      detail: `unreadable response body — ${err instanceof Error ? err.message : String(err)}`,
    };
  }
}

/**
 * The worklist rows still arrive as unknowns: the per-row error contract (slice 5a)
 * makes each element a UNION (WorklistRow | WorklistRowError), and the discrimination
 * plus the defensive fallback for anything matching neither live in ONE place —
 * domain/worklist.classifyWorklist — rather than being half-asserted here.
 */
export async function fetchWorklist(): Promise<ApiResult<readonly unknown[]>> {
  const result = await fetchJson<unknown>("/api/case-sessions");
  if (result.kind === "error") return result;
  if (!Array.isArray(result.data)) {
    return { kind: "error", detail: "the worklist response was not a list of cases" };
  }
  return { kind: "ok", data: result.data as readonly unknown[] };
}

export async function fetchCaseSession(
  caseId: string,
): Promise<ApiResult<CaseSessionDetail>> {
  return fetchJson<CaseSessionDetail>(
    `/api/case-sessions/${encodeURIComponent(caseId)}`,
  );
}

/**
 * The scan-stream URL for a case (GET /api/case-sessions/{id}/scan — plan §7 slice 3).
 * A URL rather than a fetch: the main stage hands it straight to the viewer package's
 * STL loader, so the scan's megabytes never pass through this JSON client at all.
 */
export function scanUrlFor(caseId: string): string {
  return `/api/case-sessions/${encodeURIComponent(caseId)}/scan`;
}

/**
 * Fire detection (POST /{id}/detect — plan §4: automatic on Intake). A compute
 * TRIGGER: no body — the response is the whole updated detail, which the caller
 * renders verbatim (trust direction: the BFF derived it, this app displays it).
 * `fresh` is the explicit re-ask for a rescanned case.
 */
export async function postDetect(
  caseId: string,
  fresh = false,
): Promise<ApiResult<CaseSessionDetail>> {
  const query = fresh ? "?fresh=1" : "";
  return fetchJson<CaseSessionDetail>(
    `/api/case-sessions/${encodeURIComponent(caseId)}/detect${query}`,
    { method: "POST" },
  );
}

/** The full case-level choice document — PUT semantics: what is sent is what is
 * chosen, so the panel always submits its whole current state. */
export interface ChoicesUpdate {
  construction_path: string | null;
  jaw: string | null;
  gingival_offset_mm: number | null;
}

export async function putChoices(
  caseId: string,
  choices: ChoicesUpdate,
): Promise<ApiResult<CaseSessionDetail>> {
  return fetchJson<CaseSessionDetail>(
    `/api/case-sessions/${encodeURIComponent(caseId)}/choices`,
    {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(choices),
    },
  );
}
