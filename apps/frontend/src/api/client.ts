/**
 * UI-shaped REST client for apps/api (`/api/v1/...`).
 *
 * Mirrors the product adjust client methods (seated, landmarks, acceptance,
 * rotation, mark-trench, fit-by-points, best-fit, re-preview) plus the
 * technique runner. Fetch is injectable so tests serve fixtures.
 */
export type TechniqueMode = "deterministic" | "intelligence";

export interface CaseRow {
  readonly id: string;
  readonly doctor: string;
  readonly jaw: string;
  readonly suggested_model: string | null;
  readonly suggested_sites: readonly { tooth?: number; declared_variant?: string }[];
}

export interface CaseDetail {
  readonly id: string;
  readonly doctor: string;
  readonly jaw: string;
  readonly teeth: readonly number[];
  readonly suggested_sites: readonly Record<string, unknown>[];
}

export interface SignalEnvelope {
  readonly tooth?: number;
  readonly case_id?: string;
  readonly run_id?: string;
  readonly group_names: readonly string[];
  readonly groups: Record<string, Record<string, unknown>>;
  readonly outcome?: AdjustOutcomeView | null;
}

export interface AdjustOutcomeView {
  readonly tooth: number;
  readonly operation: string;
  readonly detail: string;
  readonly applied: boolean;
  readonly files?: readonly string[];
  readonly clocking?: Record<string, unknown> | null;
  readonly deviation?: Record<string, unknown> | null;
  readonly stale_metrics?: readonly string[];
  readonly nudge?: Record<string, unknown> | null;
  readonly applied_delta_deg?: number | null;
  readonly cumulative_deg?: number | null;
  readonly stability_excess_mm?: number | null;
  readonly best_fit?: Record<string, unknown> | null;
  readonly pairs?: readonly Record<string, unknown>[];
  readonly residual_rms_mm?: number | null;
  readonly cross_checked?: boolean | null;
  readonly translation_mm?: number | null;
  readonly fit_version?: number | null;
  readonly seat_branch?: string | null;
  readonly seat_band_mm?: number | null;
  readonly click_azimuth_deg?: number | null;
  readonly matched_feature_azimuth_deg?: number | null;
}

export interface ToolTraceView {
  readonly name: string;
  readonly classification: "READ" | "DRY_RUN" | "COMMIT";
  readonly ok: boolean;
  readonly detail: string;
  readonly result?: Record<string, unknown> | null;
  readonly refusal?: Record<string, unknown> | null;
}

export interface TechniqueResultView {
  readonly mode: TechniqueMode;
  readonly status: string;
  readonly detail: string;
  readonly case_id: string;
  readonly run_id: string;
  readonly tooth: number;
  readonly signal_groups: readonly string[];
  readonly signals_before: SignalEnvelope;
  readonly signals_after: SignalEnvelope;
  readonly outcome: AdjustOutcomeView | null;
  readonly refusals: readonly Record<string, unknown>[];
  readonly trace: readonly ToolTraceView[];
  readonly proposals: {
    readonly landmarks?: readonly Record<string, unknown>[];
    readonly note?: string;
  };
}

export interface TechniqueAskBody {
  readonly mode: TechniqueMode;
  readonly apply?: boolean;
  readonly matching_diameter_mm?: number;
  readonly step_deg?: number;
  readonly reset?: boolean;
  readonly scan_point?: readonly number[];
  readonly pairs?: readonly CorrespondencePairBody[];
}

export interface CorrespondencePairBody {
  readonly feature_id?: string;
  readonly part_point?: readonly number[];
  readonly part_point_end?: readonly number[];
  readonly scan_point: readonly number[];
  readonly scan_point_end?: readonly number[];
}

export interface LandmarkView {
  readonly id: string;
  readonly kind?: string;
  readonly point?: readonly number[];
  readonly lever_arm_mm?: number;
  readonly azimuth_deg?: number;
}

export interface ApiError {
  readonly status: number;
  readonly detail: unknown;
}

export type FetchFn = typeof fetch;

async function readJson<T>(res: Response): Promise<T> {
  const body = await res.json() as T;
  if (!res.ok) {
    const error: ApiError = {
      status: res.status,
      detail: (body as { detail?: unknown }).detail ?? body,
    };
    throw error;
  }
  return body;
}

export class ApiClient {
  constructor(private readonly fetchFn: FetchFn = fetch, private readonly root = "") {}

  private url(path: string): string {
    return `${this.root}${path}`;
  }

  async listCases(): Promise<readonly CaseRow[]> {
    const body = await readJson<{ cases: CaseRow[] }>(
      await this.fetchFn(this.url("/api/v1/cases")));
    return body.cases;
  }

  async getCase(caseId: string): Promise<CaseDetail> {
    return readJson(await this.fetchFn(this.url(`/api/v1/cases/${caseId}`)));
  }

  async fetchSignals(caseId: string, tooth: number): Promise<SignalEnvelope> {
    return readJson(await this.fetchFn(
      this.url(`/api/v1/cases/${caseId}/sites/${tooth}/signals`)));
  }

  async fetchSeated(caseId: string, tooth: number): Promise<Record<string, unknown>> {
    return readJson(await this.fetchFn(
      this.url(`/api/v1/cases/${caseId}/sites/${tooth}/seated`)));
  }

  async fetchLandmarks(caseId: string, tooth: number): Promise<readonly LandmarkView[]> {
    const body = await readJson<{ landmarks: LandmarkView[] }>(
      await this.fetchFn(this.url(`/api/v1/cases/${caseId}/sites/${tooth}/landmarks`)));
    return body.landmarks;
  }

  async fetchAcceptance(caseId: string, tooth: number): Promise<Record<string, unknown>> {
    return readJson(await this.fetchFn(
      this.url(`/api/v1/cases/${caseId}/sites/${tooth}/acceptance`)));
  }

  async postRePreview(caseId: string, tooth: number): Promise<Record<string, unknown>> {
    return readJson(await this.fetchFn(
      this.url(`/api/v1/cases/${caseId}/sites/${tooth}/re-preview`),
      { method: "POST" }));
  }

  async postRotation(
    caseId: string, tooth: number, body: { step_deg?: number; reset?: boolean },
  ): Promise<{ outcome: AdjustOutcomeView }> {
    return readJson(await this.fetchFn(
      this.url(`/api/v1/cases/${caseId}/sites/${tooth}/rotation`),
      { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body) }));
  }

  async postMarkTrench(
    caseId: string, tooth: number, scan_point: readonly number[],
  ): Promise<{ outcome: AdjustOutcomeView }> {
    return readJson(await this.fetchFn(
      this.url(`/api/v1/cases/${caseId}/sites/${tooth}/mark-trench`),
      { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scan_point }) }));
  }

  async postFitByPoints(
    caseId: string, tooth: number, pairs: readonly CorrespondencePairBody[],
  ): Promise<{ outcome: AdjustOutcomeView }> {
    return readJson(await this.fetchFn(
      this.url(`/api/v1/cases/${caseId}/sites/${tooth}/fit-by-points`),
      { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pairs }) }));
  }

  async postBestFit(
    caseId: string, tooth: number,
    body: { matching_diameter_mm?: number; apply?: boolean },
  ): Promise<{ outcome: AdjustOutcomeView }> {
    return readJson(await this.fetchFn(
      this.url(`/api/v1/cases/${caseId}/sites/${tooth}/best-fit`),
      { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body) }));
  }

  async postTechnique(
    caseId: string, tooth: number, body: TechniqueAskBody,
  ): Promise<TechniqueResultView> {
    return readJson(await this.fetchFn(
      this.url(`/api/v1/cases/${caseId}/sites/${tooth}/technique`),
      { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body) }));
  }
}

export const defaultClient = new ApiClient();
