/**
 * THE BFF CLIENT — the product's only network surface (plan §1.3, §3): the case-session
 * reads plus the actions (detect and preview — compute triggers; choices, system,
 * declarations and the review tick — operator acts), reached through the vite proxy
 * so no backend host is hard-coded here.
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
  /** Released is a CURRENT-run verdict (slice 8): the BFF's derivation — true only
   * while the release record still names the current done run. */
  released: boolean;
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
  released: null;
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
  /** THE PREVIEW'S SEAT FACTS (client 2026-07-27 #2): what this site's attestation
   * actually stood on — the two numbers a seat is judged by, persisted by the BFF's
   * preview route and cleared with the rung at every reset boundary. Declare's
   * move-forward summary reads these; null until this site has previewed. */
  seat_method: string | null;
  rim_agreement_mm: number | null;
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

/** One case-level choice as the automation consumes it (the SystemView pattern
 * mirrored per choice — client 2026-07-27): the effective value plus WHO supplied
 * it, so the Intake panel renders its "suggested"/"default" chips from server
 * facts, exactly like the system bar's tag. */
export interface EffectiveChoiceView<T> {
  value: T | null;
  source: "chosen" | "suggested" | "default" | "none";
}

/** The operator's case-level choices as persisted (raw acts, None until made),
 * beside the EFFECTIVE values preview/run actually consume; `complete` is the
 * BFF's derivation over the EFFECTIVE values (this app never computes completion
 * itself — trust direction, AM-4). */
export interface ChoicesView {
  construction_path: string | null;
  jaw: string | null;
  gingival_offset_mm: number | null;
  gingival_offset_default_mm: number;
  effective_construction: EffectiveChoiceView<string>;
  effective_jaw: EffectiveChoiceView<string>;
  effective_relief: EffectiveChoiceView<number>;
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

/** Worker-shaped catalog rows stay untyped on the wire; domain/declare.ts extracts
 * the shapes Declare renders (a row missing its id is dropped, never guessed at) —
 * the same defensive posture as domain/intake's construction options. */
export interface CatalogView {
  groups: Array<Record<string, unknown>>;
  constructions: Array<Record<string, unknown>>;
}

/** WHICH implant system the case works against (AM-8): the BFF says whether the
 * effective model is the session's declared act or the case's suggestion — this app
 * renders the tag from `source`, never by comparing fields itself. */
export interface SystemView {
  effective_model: string | null;
  source: "declared" | "suggested" | "none";
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

/** The sealed confirmation's facts (slice 8, AM-10): the record verbatim. No
 * actor: the operator name was removed at the client's word (2026-07-27) — the
 * attestation act is the record, and `at` is what the act genuinely produced. */
export interface ConfirmationView {
  at: string;
  run_id: string;
  evidence_sha256: string;
  /** tooth-as-string → "release" | "withhold" (JSON object keys are strings). */
  dispositions: Record<string, string>;
  acknowledged_flags: number[];
}

/** The payment stub's record: provider "stub" keeps it honest forever. */
export interface PaymentView {
  provider: string;
  at: string;
}

export interface ReleaseView {
  at: string;
  run_id: string;
  evidence_sha256: string;
  released_teeth: number[];
}

/** WHAT A RELEASE WOULD DISCLOSE, before the act (client 2026-07-27 #6): counts and
 * the operator's own teeth, derived server-side through the artifact gate's own file
 * split. No file names — names are the disclosure this describes. */
export interface ReleasePreviewView {
  file_count: number;
  teeth: number[];
  withheld_teeth: number[];
  withheld_case_file_count: number;
}

/** The Delivery-vs-Skip fork as recorded (client 2026-07-27): what was decided,
 * when, over which run. A record of an ACT — nothing in flow.ts reads it. */
export interface AdjustDecisionView {
  decision: "skip" | "adjust";
  at: string;
  run_id: string;
}

export interface SessionView {
  tenant_id: string;
  adjust_visited: boolean;
  /** null until the fork is faced, and null again once a reset boundary clears
   * the run whose verdicts it was decided over. */
  adjust_decision: AdjustDecisionView | null;
  run_state: RunState;
  /** A refused run's words, VERBATIM (5c) — null unless run_state is "refused". */
  run_refusal: string | null;
  confirmed: boolean;
  payment_authorized: boolean;
  /** The disclosure chain's records (slice 8), verbatim where they exist. */
  confirmation: ConfirmationView | null;
  payment: PaymentView | null;
  release: ReleaseView | null;
  /** Present exactly while a confirmation covers the current done run — the release
   * step names its consequence from this, before the act. */
  release_preview: ReleasePreviewView | null;
  /** True only while the release record names the CURRENT done run — the rail's
   * deliver tick reads this, never the release record's bare existence. */
  released: boolean;
}

export interface CaseSessionDetail {
  case: CaseView;
  sites: SiteView[];
  system: SystemView;
  catalog: CatalogView;
  relief_ceilings: ReliefCeilingView[];
  detection: DetectionView | null;
  choices: ChoicesView;
  session: SessionView;
}

/** The seated pose block (5b): what the panes FRAME with — the exact axis the
 * alignment produced (the demo's 2026-07-26 lesson: the occlusal proxy sat
 * 6.2°-42.0° off the real axis; this is exact by construction). `x_axis` is the
 * shared up-vector that makes clock positions match across the three panes. */
export interface PreviewPose {
  axis: number[];
  x_axis: number[];
  origin: number[];
}

export interface PreviewScale {
  clamp_mm: number;
  min_mm: number;
  max_mm: number;
  colormap: string;
  sign_convention: string;
  data_min_mm: number | null;
  data_max_mm: number | null;
  footprint_band_mm: number;
}

/** The site's published acceptance numbers — the SAME RMS/p90 the difference map
 * prints and the run row will carry; the pane shows these, never a re-derivation. */
export interface PreviewStats {
  rms_mm: number | null;
  p90_mm: number | null;
  n_footprint: number;
  n_samples: number;
  source: string;
}

export interface PreviewSeat {
  seat_method: string | null;
  rim_agreement_mm: number | null;
  fit: string | null;
}

/**
 * The preview payload (POST /{id}/sites/{tooth}/preview — plan §7 slice 5b): the
 * union pane's whole render, response-only (the BFF persists only the seat FACTS).
 * Shape is the worker's deviation payload VERBATIM (application/preview.py — the
 * demo's wire shape, which the copied deviationColormap code was written against).
 */
export interface SitePreviewPayload {
  case_id: string;
  tooth: number;
  implant_model: string | null;
  variant: string | null;
  frame: string;
  units: string;
  pose: PreviewPose;
  n_points: number;
  points: number[][];
  faces: number[][];
  deviation_mm: (number | null)[];
  scale: PreviewScale;
  stats: PreviewStats;
  vertex_footprint_points: number;
  reporting_only: boolean;
  /** TRUE when this colouring came from a pre-run PREVIEW seat, false when it
   * describes a SHIPPED pose (Adjust's read). The two look identical on screen and
   * mean different things, so the caption branches on it. */
  preview: boolean;
  /** The seat facts ride along on the PREVIEW payload only — the shipped read has a
   * run row for them, and inventing the key would claim a measurement twice. */
  seat?: PreviewSeat | null;
}

/**
 * An HTTP failure keeps its status so pages can tell a REFUSAL from an OUTAGE
 * (a 404 for a stale bookmark is not a down service — the banner copy branches
 * on this in pages/CaseShell.tsx). A network-level failure has no status: nothing
 * answered, so "unreachable" is the honest diagnosis.
 */
export type ApiResult<T> =
  | { kind: "ok"; data: T }
  | {
      kind: "error";
      detail: string;
      status?: number;
      /**
       * The refusal body's `detail` value RAW, when it was not a plain sentence.
       * Almost every BFF refusal is one sentence and this stays undefined. The
       * exception earns its keep: the best-fit's already-optimal outcome is a
       * refusal that is really a PASS, and it carries machine-readable fields
       * (`kind`, `matching_diameter_mm`, `suggested_diameter_mm`) so the surface can
       * render it green with a one-click widen instead of the refusal tone the demo
       * learned to regret. Kept as `unknown`: domain code narrows it, transport does
       * not interpret it.
       */
      refusal?: unknown;
    };

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
    // FastAPI refusals carry {"detail": ...} — a sentence, pydantic's error rows, or
    // (slice 6's one structured case) an object the domain layer narrows.
    let detail = `HTTP ${response.status}`;
    let refusal: unknown;
    try {
      const body = (await response.json()) as { detail?: unknown };
      refusal = body.detail;
      const stated = refusalDetail(body.detail);
      if (stated !== null) detail = `HTTP ${response.status} — ${stated}`;
    } catch {
      // a non-JSON error body still yields the status line above
    }
    return { kind: "error", detail, status: response.status, refusal };
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

/**
 * Declare the case-scoped implant system (PUT /{id}/system — plan §4 Declare/AM-8).
 * Switching resets every site SERVER-side; this app asks the operator in words
 * first (components/DeclareStage) and then renders whatever came back — the reset
 * is the BFF's derivation, never performed locally.
 */
export async function putSystem(
  caseId: string,
  model: string,
): Promise<ApiResult<CaseSessionDetail>> {
  return fetchJson<CaseSessionDetail>(
    `/api/case-sessions/${encodeURIComponent(caseId)}/system`,
    {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ model }),
    },
  );
}

/**
 * Declare the active site's variant (PUT /{id}/sites/{tooth}/declaration — AM-8).
 * The detected→declared move happens in the BFF's status machine; the returned
 * detail is the whole new truth and replaces the payload verbatim (optimism OFF).
 */
export async function putDeclaration(
  caseId: string,
  tooth: number,
  variant: string,
): Promise<ApiResult<CaseSessionDetail>> {
  return fetchJson<CaseSessionDetail>(
    `/api/case-sessions/${encodeURIComponent(caseId)}/sites/${encodeURIComponent(
      String(tooth),
    )}/declaration`,
    {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ variant }),
    },
  );
}

function siteActionPath(caseId: string, tooth: number, action: string): string {
  return `/api/case-sessions/${encodeURIComponent(caseId)}/sites/${encodeURIComponent(
    String(tooth),
  )}/${action}`;
}

/**
 * Seat the site's declared cap and fetch its deviation colouring (POST
 * /{id}/sites/{tooth}/preview — plan §7 slice 5b). A compute TRIGGER like detect:
 * no body — the declaration and choices it seats with are the session's persisted
 * acts. The payload is response-only; the seat FACTS the BFF persisted arrive on
 * the next detail read, which the caller re-fetches after this resolves.
 */
export async function postPreview(
  caseId: string,
  tooth: number,
): Promise<ApiResult<SitePreviewPayload>> {
  return fetchJson<SitePreviewPayload>(siteActionPath(caseId, tooth, "preview"), {
    method: "POST",
  });
}

/**
 * The review tick (POST /{id}/sites/{tooth}/review — AM-8): the operator's
 * attestation over the live panes. No body at all — the act is the POST itself, so
 * there is no field a claimed outcome could ride in on. The BFF's status machine
 * refuses a tick over an unpreviewed site; the returned detail is the whole new
 * truth (the queue chip and the rail react to it).
 */
export async function postReview(
  caseId: string,
  tooth: number,
): Promise<ApiResult<CaseSessionDetail>> {
  return fetchJson<CaseSessionDetail>(siteActionPath(caseId, tooth, "review"), {
    method: "POST",
  });
}

/** The tick un-ticked (DELETE same path) — the attestation withdrawn; two-way like
 * the demo's checkbox. */
export async function deleteReview(
  caseId: string,
  tooth: number,
): Promise<ApiResult<CaseSessionDetail>> {
  return fetchJson<CaseSessionDetail>(siteActionPath(caseId, tooth, "review"), {
    method: "DELETE",
  });
}

/**
 * Fire the authorized full run (POST /{id}/run — plan §7 slice 5c). A compute
 * TRIGGER like detect and preview: NO body — the selection it runs is the session's
 * own persisted acts, and the authorization gate is server-minted (AM-8), so there
 * is nothing a client could claim with. The in-process worker completes
 * synchronously (~30–60 s on a real case): the response is the whole updated
 * detail — verdicts landed on the ladder, run_state done|refused, a refusal's
 * words on session.run_refusal, verbatim.
 */
export async function postRun(
  caseId: string,
): Promise<ApiResult<CaseSessionDetail>> {
  return fetchJson<CaseSessionDetail>(
    `/api/case-sessions/${encodeURIComponent(caseId)}/run`,
    { method: "POST" },
  );
}

/**
 * THE FORK, RECORDED (POST /{id}/adjust-decision — client 2026-07-27: "Skipping
 * adjust should be optional we should have two options one to skip and another to
 * delivery — Delivery vs Skip Adjustments"). An ACT: it moves no site and gates
 * nothing (flow.ts reachability never reads it — skip does not close Adjust), and a
 * later decision replaces it. The BFF refuses (422) unless a done run exists and
 * every site carries a verdict; the response is the whole new detail.
 */
export async function postAdjustDecision(
  caseId: string,
  decision: "skip" | "adjust",
): Promise<ApiResult<CaseSessionDetail>> {
  return fetchJson<CaseSessionDetail>(
    `/api/case-sessions/${encodeURIComponent(caseId)}/adjust-decision`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ decision }),
    },
  );
}

/**
 * The current run's persisted facts (GET /{id}/run — 5c): the job-shaped receipt,
 * the per-site verdict rows and the package file list (names relative to the
 * immutable run directory). Adjust's and Deliver's read surface; 404 while no
 * current run exists — including after a reset boundary cleared the pointer.
 * Rows stay wire-untyped like the catalog's: the worker's summary is the schema.
 */
export interface RunFactsView {
  run_id: string;
  job_id: string;
  state: RunState;
  refusal: string | null;
  summary: Record<string, unknown> | null;
  sites: Array<Record<string, unknown>>;
  package_files: string[];
}

export async function fetchRun(caseId: string): Promise<ApiResult<RunFactsView>> {
  return fetchJson<RunFactsView>(
    `/api/case-sessions/${encodeURIComponent(caseId)}/run`,
  );
}

// --- Deliver (slice 8): the evidence surface and the disclosure chain -----------------

/** The rotation facts as the run measured them (deg + instrument + unverified). */
export interface AssuranceRotation {
  deg: number | null;
  evidence: string | null;
  unverified: boolean;
}

export interface AssuranceClamp {
  requested_mm: number | null;
  applied_mm: number | null;
  clamped: boolean;
  reason: string | null;
}

/** The run's guidance verdict verbatim — level + the exact action words. */
export interface AssuranceGate {
  level: string;
  actions: string[];
}

/** One acceptance-catalog pairing (case_prep.domain.acceptance, verbatim): the
 * measured value beside the industry reference the doctor already knows. */
export interface AssuranceReference {
  key: string;
  label: string;
  unit: string;
  value: unknown;
  display: string | null;
  band: string;
  industry_ref: { value: string; source: string };
  note: string | null;
}

export interface AssuranceSite {
  tooth: number;
  status: string | null;
  declared_variant: string | null;
  identified_variant: string | null;
  /** The backend's own word: "match" | "mismatch" | "undeclared" | null. */
  variant_agreement: string | null;
  seat_method: string | null;
  rim_agreement_mm: number | null;
  rotation: AssuranceRotation;
  deviation_rms_mm: number | null;
  deviation_p90_mm: number | null;
  gate: AssuranceGate;
  clamp: AssuranceClamp;
  qc_images: string[];
  references: Record<string, AssuranceReference>;
}

/** The per-site verdict table's data (AM-12) — served worst-first by the BFF
 * (flagged pinned, then the worse gate); this app renders the order VERBATIM. */
export interface AssuranceView {
  case_id: string;
  run_id: string;
  relief: Record<string, unknown> | null;
  /**
   * The Delivery-vs-Skip fork as it stands: "skip" | "adjust", or null where the
   * fork was never faced. It rides on THIS document because sealing the word is
   * not showing it — the BFF folds it into the evidence hash, and a hash tells the
   * operator nothing about whether the fits were reworked before they sign.
   */
  adjustments: string | null;
  sites: AssuranceSite[];
}

/** EVIDENCE class (AM-1): ungated — visible before any confirmation exists. */
export async function fetchAssurance(
  caseId: string,
): Promise<ApiResult<AssuranceView>> {
  return fetchJson<AssuranceView>(
    `/api/case-sessions/${encodeURIComponent(caseId)}/assurance`,
  );
}

/** A QC image's URL (EVIDENCE class, ungated) — handed to a lazy <img>, so the
 * bytes never pass through this JSON client. */
export function qcImageUrl(caseId: string, filename: string): string {
  return `/api/case-sessions/${encodeURIComponent(caseId)}/runs/current/qc/${encodeURIComponent(filename)}`;
}

// NO ACTOR HEADER (client 2026-07-27: "WE dont need operator name the checkmark is
// sufficient"). Every gating call used to carry `X-Operator` and the BFF 422'd
// without it. A self-typed name behind no authentication was a text field, not
// identity; the acts themselves are the record now, and real identity arrives with
// real auth (plan §8 / phase-2). Deliberate — do not re-add it as a missing header.

/** The confirmation's wire body: dispositions keyed tooth-as-string. */
export interface ConfirmBody {
  dispositions: Record<string, "release" | "withhold">;
  acknowledged_flags: number[];
}

export async function postConfirm(
  caseId: string,
  body: ConfirmBody,
): Promise<ApiResult<CaseSessionDetail>> {
  return fetchJson<CaseSessionDetail>(
    `/api/case-sessions/${encodeURIComponent(caseId)}/confirm`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    },
  );
}

/** The payment STUB: {authorize: true} or nothing — the UI labels the button as a
 * stub, and the BFF records provider "stub" so it stays tellable. */
export async function postPayment(
  caseId: string,
): Promise<ApiResult<CaseSessionDetail>> {
  return fetchJson<CaseSessionDetail>(
    `/api/case-sessions/${encodeURIComponent(caseId)}/payment`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ authorize: true }),
    },
  );
}

/** Release = disclosure (AM-1). Body-less: everything it consumes is already the
 * session's. A 409 carries the BFF's words — including "the case changed since it
 * was confirmed", which the UI answers with the re-confirm flow. */
export async function postRelease(
  caseId: string,
): Promise<ApiResult<CaseSessionDetail>> {
  return fetchJson<CaseSessionDetail>(
    `/api/case-sessions/${encodeURIComponent(caseId)}/release`,
    { method: "POST" },
  );
}

/** The released deliverables: names minus QC images minus withheld sites' files.
 * `withheld_case_files` are the case-wide files (overlay, manifest, jaw scan —
 * anything not attributable to a single released tooth) the BFF held back
 * BECAUSE sites are withheld; empty on a full release. */
/** One released deliverable: its name, its size on disk (null when the package
 * claims a file the run directory no longer holds — an honest gap, never a 0), and
 * the site it belongs to (null = case-wide). The BFF attributes it with the artifact
 * gate's own anchored rule; this app never re-parses a filename. */
export interface ArtifactFile {
  name: string;
  size_bytes: number | null;
  tooth: number | null;
}

export interface ArtifactsView {
  run_id: string;
  files: ArtifactFile[];
  withheld_teeth: number[];
  withheld_case_files: string[];
}

export async function fetchArtifacts(
  caseId: string,
): Promise<ApiResult<ArtifactsView>> {
  return fetchJson<ArtifactsView>(
    `/api/case-sessions/${encodeURIComponent(caseId)}/runs/current/artifacts`,
  );
}

/**
 * One deliverable's bytes: resolves to a Blob the component turns into an object
 * URL and clicks — or to the BFF's stated refusal. A FETCH rather than a bare
 * <a href> because the endpoint is release-gated and a refusal must be READ (a
 * bare href would navigate the browser into a JSON 409 the surface never sees).
 */
export async function fetchArtifactBlob(
  caseId: string,
  filename: string,
): Promise<ApiResult<Blob>> {
  const path = `/api/case-sessions/${encodeURIComponent(caseId)}/runs/current/artifacts/${encodeURIComponent(filename)}`;
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
  return { kind: "ok", data: await response.blob() };
}

// --- Adjust (slice 6): the four tools and the read the panes open on -------------------

/**
 * One correspondence on the wire. The PART half is a named feature OR a free
 * canonical-frame click, exactly one. The SCAN half is one click — or, with
 * `scan_point_end`, THE SPAN: both ENDS of the feature (client ask 2026-07-26, plan
 * §5). The span's own bounds are the worker's; this app only carries the two points.
 */
export interface CorrespondencePairBody {
  feature_id?: string;
  part_point?: number[];
  scan_point: number[];
  scan_point_end?: number[];
}

/** What a tool produced — the application's own facts, passed through by the BFF.
 * Tool-specific fields are null where they do not apply. */
export interface AdjustOutcomeView {
  tooth: number;
  operation: string;
  detail: string;
  applied: boolean;
  files: string[];
  clocking: Record<string, unknown> | null;
  nudge: Record<string, unknown> | null;
  applied_delta_deg: number | null;
  cumulative_deg: number | null;
  stability_excess_mm: number | null;
  best_fit: Record<string, unknown> | null;
  /** ONE ROW PER OBSERVATION — a span contributes two (its midpoint and, when the
   * span reads as radial, its direction), each with its own residual. */
  pairs: Array<Record<string, unknown>>;
  residual_rms_mm: number | null;
  click_azimuth_deg: number | null;
  matched_feature_azimuth_deg: number | null;
}

/** An applied (or measured) tool: what it did, the NEW pose as the panes render it,
 * and the whole case detail — replaced verbatim, never patched locally (AM-4). */
export interface AdjustResultView {
  outcome: AdjustOutcomeView;
  pane_payload: SitePreviewPayload | null;
  case: CaseSessionDetail;
}

/** The site's SHIPPED pose as the three panes render it (GET .../sites/{tooth}/seated)
 * — the same payload shape the preview serves, from the same builder, so a pose read
 * before and after a rework is the same instrument on the same scale. */
export async function fetchSeated(
  caseId: string,
  tooth: number,
): Promise<ApiResult<SitePreviewPayload>> {
  return fetchJson<SitePreviewPayload>(siteActionPath(caseId, tooth, "seated"));
}

function adjustTool(
  caseId: string,
  tooth: number,
  action: string,
  body: unknown,
): Promise<ApiResult<AdjustResultView>> {
  return fetchJson<AdjustResultView>(siteActionPath(caseId, tooth, action), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

/** THE ROTATION DIAL: a gated step about the seated part's own axis, or the reset that
 * restores the pipeline's certified pose. The ±45° bound is the server's. */
export async function postRotation(
  caseId: string,
  tooth: number,
  body: { step_deg?: number; reset?: boolean },
): Promise<ApiResult<AdjustResultView>> {
  return adjustTool(caseId, tooth, "rotation", body);
}

/** MARK TRENCH: one click on the scan's coded cutout; the cap rotates so its nearest
 * code feature lands there — through the same gates as every other rotation. */
export async function postMarkTrench(
  caseId: string,
  tooth: number,
  scanPoint: readonly number[],
): Promise<ApiResult<AdjustResultView>> {
  return adjustTool(caseId, tooth, "mark-trench", { scan_point: [...scanPoint] });
}

/** FIT BY POINTS: named correspondences, single-click or SPAN. */
export async function postFitByPoints(
  caseId: string,
  tooth: number,
  pairs: readonly CorrespondencePairBody[],
): Promise<ApiResult<AdjustResultView>> {
  return adjustTool(caseId, tooth, "fit-by-points", { pairs: [...pairs] });
}

/** BEST FIT at the operator's matching diameter. `apply: false` MEASURES ONLY — the
 * refinement runs and the gates still judge it, but nothing is written. */
export async function postBestFit(
  caseId: string,
  tooth: number,
  body: { matching_diameter_mm: number; apply: boolean },
): Promise<ApiResult<AdjustResultView>> {
  return adjustTool(caseId, tooth, "best-fit", body);
}
