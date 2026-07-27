/**
 * THE BFF CLIENT — the product's only network surface (plan §1.3, §3): two GET
 * resources, reached through the vite proxy so no backend host is hard-coded here.
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

export interface WorklistRow {
  id: string;
  doctor: string;
  jaw: string;
  suggested_model: string | null;
  sites: SiteRollup;
  run_state: RunState;
  confirmed: boolean;
}

export interface SiteView {
  tooth: number;
  status: SiteStatus;
  declared_variant: string | null;
  suggested_variant: string | null;
  center: number[] | null;
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
  session: SessionView;
}

export type ApiResult<T> =
  | { kind: "ok"; data: T }
  | { kind: "error"; detail: string };

/** What a fetching component holds: the result, or the honest in-between. */
export type FetchState<T> = { kind: "loading" } | ApiResult<T>;

async function fetchJson<T>(path: string): Promise<ApiResult<T>> {
  let response: Response;
  try {
    response = await fetch(path);
  } catch (err: unknown) {
    return {
      kind: "error",
      detail: err instanceof Error ? err.message : String(err),
    };
  }
  if (!response.ok) {
    // FastAPI refusals carry {"detail": ...}; surface it when present.
    let detail = `HTTP ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = `HTTP ${response.status} — ${body.detail}`;
    } catch {
      // a non-JSON error body still yields the status line above
    }
    return { kind: "error", detail };
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
 * The worklist rows arrive as unknowns on purpose: the BFF defines no per-row error
 * contract yet (its worklist endpoint 500s whole if one session file is corrupt — see
 * bff/session.py's loud-refusal posture), so the worklist module guards each row
 * defensively instead of this client asserting a shape it cannot promise per-row.
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
