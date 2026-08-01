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
/**
 * NEW WIRE FIELDS ARE DECLARED OPTIONAL HERE, and the reason is worth stating once:
 * these types are ADDITIVE mirrors that many fixtures and tests construct as object
 * literals. The BFF always sends them; declaring them `?:` keeps a literal built
 * before the field existed legal, and a consumer that must have one narrows it at the
 * point of use. A field the BFF may genuinely omit is `| null`, never `?:` — the two
 * are deliberately different statements.
 */

export interface WorklistRow {
  id: string;
  doctor: string;
  jaw: string;
  suggested_model: string | null;
  /** The scan card's DISCOVERY facts (2026-07-31): the curated teeth and the scan
   * file's size on disk. Identity-class, so they stand even on an error row —
   * a corrupt session says nothing about the data tree. `scan_bytes` is null when
   * the file has gone since discovery listed it. */
  teeth?: number[];
  scan_bytes?: number | null;
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
  teeth?: number[];
  scan_bytes?: number | null;
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
  /** THE DROP, AS A DRAFT (design flow.dc.html dropSite 1345-1354): whether the
   * operator has said this site is to be WITHHELD at confirmation time. It is an
   * ACT, not a rung — every surface renders it as something the operator DID, never
   * as a verdict about the site. Optional on this type only because fixtures and
   * detail documents written before it exists omit it; the BFF always sends it. */
  withhold_intent?: boolean;
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

/** The turnaround ask (design speedChips 1159-1160): what the lab ASKED FOR, never
 * what any site IS — which is why it is admissible as an operator choice at all.
 * It fires NO reset boundary: a promise about WHEN touches no geometry, so
 * upgrading a case to rush costs no review, no preview and no run. */
export type Turnaround = "standard" | "rush";

/** The operator's case-level choices as persisted (raw acts, None until made),
 * beside the EFFECTIVE values preview/run actually consume; `complete` is the
 * BFF's derivation over the EFFECTIVE values (this app never computes completion
 * itself — trust direction, AM-4). */
export interface ChoicesView {
  construction_path: string | null;
  jaw: string | null;
  gingival_offset_mm: number | null;
  gingival_offset_default_mm: number;
  /** The turnaround ask (design speedChips): the raw act, null until made. */
  turnaround?: Turnaround | null;
  effective_construction: EffectiveChoiceView<string>;
  effective_jaw: EffectiveChoiceView<string>;
  effective_relief: EffectiveChoiceView<number>;
  /** "chosen" | "default" — never "suggested": no case fact suggests a turnaround,
   * and the standing default is the only fallback there is. */
  effective_turnaround?: EffectiveChoiceView<Turnaround>;
  /** DELIBERATELY unaffected by the turnaround: the standing default always answers
   * it, so a case is never incomplete for want of a commercial choice. */
  complete: boolean;
}

export interface CaseView {
  id: string;
  doctor: string;
  jaw: string;
  scan_filename: string;
  suggested_model: string | null;
  suggested_construction: string | null;
  /** The scan card's discovery facts, same as the worklist row's. */
  teeth?: number[];
  scan_bytes?: number | null;
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
  /** The agreement's new home (plan §10-A): confirm and accept terms is ONE
   * act. False on a confirmation sealed before the concept existed — never
   * implied true. */
  terms_accepted: boolean;
  terms_version: string | null;
}

/** The payment stub's record: provider "stub" keeps it honest forever.
 *
 * The amount is a RECEIPT, not a price: what this authorization actually charged,
 * under which rate card and turnaround. It can legitimately differ from the case's
 * CURRENT invoice — a turnaround change after payment reprices going forward and
 * fires no boundary — so a surface showing both must say which is which. Null on a
 * record persisted before pricing existed; never read as zero. */
export interface PaymentView {
  provider: string;
  at: string;
  amount_cents?: number | null;
  currency?: string | null;
  rate_card_version?: string | null;
  turnaround?: string | null;
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
 * THE SCAN'S MEASURED RIM CENTRE, in WORLD coordinates, beside the guard's own bound
 * (plan §10-F; worker: application/adjust.clock_reference, application/preview.
 * measured_rim_centre_world). This is the quantity `require_clock_lever` refuses
 * against — publishing it is what lets this app pre-refuse a mark on the screw access
 * locally instead of learning it from a 422.
 *
 * OPTIONAL on purpose: it rides every seated/tool/re-preview/Declare-preview payload
 * today, but a payload that predates it, or a future one that cannot measure a rim,
 * must degrade to the old CAUTION rather than to a wrong refusal — `markLeverGuard`
 * makes that split explicit.
 */
export interface ClockReference {
  rim_centre: number[];
  min_lever_mm: number;
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
  /** Present on every payload the worker builds today; see `ClockReference`. */
  clock_reference?: ClockReference | null;
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
  /** PUT semantics apply here too: a panel that renders the turnaround chips must
   * submit the field on EVERY choices write, or the next write un-chooses it back
   * to the standing default. Optional only so a panel that does not yet render it
   * keeps compiling. */
  turnaround?: Turnaround | null;
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
 * DROP THIS CAP / BRING IT BACK (PUT /{id}/sites/{tooth}/withhold — design
 * flow.dc.html dropSite 1345-1354).
 *
 * The DRAFT of the confirmation's own per-site disposition, made reachable from
 * Adjust instead of only from the signing screen. It records what the operator DOES
 * with the site — holds it back from the release and the bill — and never what the
 * site IS: no rung moves, and the run still aligns it.
 *
 * IT IS NOT THE SIGNATURE. Confirm still carries the disposition map and still
 * seals it; this only pre-fills what an unnamed site resolves to. Nothing about
 * withholding is decided here, and no verdict, price or gate is computed in the
 * browser — the returned detail is the whole new truth.
 */
export async function putWithholdIntent(
  caseId: string,
  tooth: number,
  withhold: boolean,
): Promise<ApiResult<CaseSessionDetail>> {
  return fetchJson<CaseSessionDetail>(siteActionPath(caseId, tooth, "withhold"), {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ withhold }),
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
  /** TWO ROTATIONS, NOT ONE (2026-07-31): `deg` is the MEASURED notch shift at the
   * shipped pose; this is how far a HUMAN turned the cap off the pipeline's
   * certified one, folded onto the row by the adjust tools. They answer different
   * questions — "is it clocked right?" and "how much of that did we do by hand?" —
   * and null here means nobody rotated this site. */
  operator_cumulative_deg?: number | null;
}

/** THE PAIRS a fit-by-points stood on (the design's PAIRS metric). `pairs` is what
 * the operator NAMED; `observations` is what those pairs produced (a two-point span
 * contributes two), so the two differ exactly when spans were used. `max_pairs` is
 * the server's own cap, carried so a chip reads "3/8" from a server fact.
 *
 * It describes the LAST APPLIED correspondence, not a running per-site tally: each
 * fit-by-points call replaces the pose outright, so a monotonic count would claim a
 * history the record does not carry. */
export interface AssuranceCorrespondence {
  pairs: number | null;
  observations: number | null;
  max_pairs: number | null;
  residual_rms_mm: number | null;
  /**
   * WHETHER `residual_rms_mm` IS A MEASUREMENT (defect cap6020-neodent-gm,
   * 2026-08-01). A fit built from ONE observation is exactly determined for rotation:
   * its residual is zero by construction, so the RMS over it is arithmetic and the
   * server reports no figure at all. `false` says the fit stands on a single
   * observation; `null` is a row folded before the fact existed and carrying no
   * observation count to derive it from — never "assume it was checked".
   *
   * Derived server-side and sealed with the rest of the row. This app renders it; it
   * never re-derives it from `observations`.
   */
  cross_checked: boolean | null;
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
  /**
   * WHETHER THESE WORDS STILL DESCRIBE THE POSE THAT SHIPPED (2026-07-31).
   *
   * A rework re-derives the row's measurements and cannot re-derive its guidance —
   * the gate stands on a dozen run-time inputs the shipped record does not carry —
   * so after a successful rework the rung moves while `actions` still describes the
   * pre-rework fit. The SERVER decides this (bff/resources/deliver.AssuranceGate);
   * a surface renders the flag, it never works the staleness out for itself.
   *
   * Optional on the wire only because a payload sealed before the field existed
   * carries no such key; the current BFF always sends it.
   */
  stale?: boolean;
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
  /** THE BAND'S OWN THRESHOLDS — value ≤ `pass` passes, ≤ `review` reviews, beyond
   * fails. Null on a metric whose verdict is not a scalar comparison. This is what
   * "how much room is left" is measured against, and it is the CATALOG's number
   * with a cited source, never a tolerance this app holds. */
  bands?: { pass: number; review: number } | null;
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
  /** THE DISCLOSURE GAP THIS FIELD CLOSES (plan §10-E, finding 2026-07-28): the
   * worker's own note when one construction part is shared across sites that
   * declared DIFFERENT variants — "single construction part shared across
   * sites identifying N distinct variants — per-variant construction parts
   * needed". Verbatim from ``row["production"]["note"]``; null on every
   * single-variant case. A site carrying this note needs its OWN row
   * acknowledgment before it can be released, the same AM-12 rule a flagged
   * site earns (domain/deliver.ackRequired) — the note's own words are "cannot
   * match", not "differs slightly". */
  production_note: string | null;
  /**
   * THE DISPOSITION THIS ROW IS STANDING ON, server-derived (audit 2026-07-31).
   *
   * A cap dropped at Adjust reached the invoice, the attestation sentence and the
   * sealed confirmation — but not this row. The table therefore printed the literal
   * word "released" over a dropped site, on the screen that signs it withheld, with
   * no control on the row to change it back. It is the same field Adjust reads
   * (`SiteView.withhold_intent`), projected onto the row that seals it, and
   * `confirm_case` writes the resolved disposition back onto it — so after a
   * confirmation this is not merely a draft, it is THE disposition.
   *
   * `domain/deliver.effectiveDisposition` resolves it exactly as the server does
   * (an explicit act, else this draft, else release). Optional so every fixture and
   * payload written before it existed keeps reading as "not dropped".
   */
  withhold_intent?: boolean;
  /** The numbers in this row that PREDATE an operator rework (the BFF's own list).
   * Adjust re-derives the deviation scalars and the clocking over the new pose; the
   * rim agreement and the guidance cannot be re-derived from the shipped record, so
   * they are named here rather than left to look current. Empty on every row the run
   * itself produced. */
  stale_metrics: string[];
  /** The matching diameter a best-fit was run at — the one number that explains why
   * a refinement moved what it moved. Null means this site ships the pipeline's own
   * refinement, never "we forgot". */
  matching_diameter_mm?: number | null;
  correspondence?: AssuranceCorrespondence | null;
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

// --- the invoice (design payLines/payTotal 1475-1480) ---------------------------------
//
// THE AMOUNT IS NEVER COMPUTED HERE. A price is the money-shaped cousin of a verdict:
// this app renders `total_cents` and the lines the BFF derived, and no request body it
// can send carries an amount at all — `postPayment` is still `{authorize: true}`.

/** One invoice line. `label` is a noun phrase with NO money in it — formatting is
 * presentation, so amounts arrive as integer cents and the UI formats them.
 *
 * `billed` is not `amount_cents === 0`: a rush turnaround is included at zero and IS
 * billed (it repriced every site above), while a withheld site is not billed at all. */
export interface InvoiceLine {
  key: "released_sites" | "exception_sites" | "turnaround" | "withheld_sites" | string;
  label: string;
  quantity: number;
  unit_amount_cents: number | null;
  amount_cents: number;
  billed: boolean;
}

/** What was ACTUALLY charged, off the payment record — beside, never instead of, the
 * current price. The two can legitimately differ after a turnaround change. */
export interface InvoicePaymentView {
  amount_cents: number | null;
  currency: string | null;
  rate_card_version: string | null;
  turnaround: string | null;
  at: string;
}

/** The priced case. `status` is "placeholder" until the client supplies a real price
 * list — the same word (and the same honesty) TERMS_TEXT_PLACEHOLDER carries, so a
 * surface can badge both from a server fact rather than deciding for itself. */
export interface InvoiceView {
  case_id: string;
  run_id: string;
  currency: string;
  rate_card_version: string;
  status: string;
  note: string;
  turnaround: string;
  turnaround_source: "chosen" | "default" | string;
  lines: InvoiceLine[];
  total_cents: number;
  paid: InvoicePaymentView | null;
  /**
   * THE DOCUMENT'S OWN IDENTITY — an opaque server digest, echoed back when
   * authorizing so the price READ and the price CHARGED are provably the same one
   * (audit 2026-07-31: a rival `turnaround` PUT repriced the case between the render
   * and the click, and the charge landed 200 at a figure no surface displayed).
   *
   * It is not an amount and must never become one: a client that could POST an
   * amount could pay $0 for a released case. This says only "this is the document I
   * was shown"; the server re-derives and compares for itself.
   */
  fingerprint?: string;
}

/** EVIDENCE class like the assurance: ungated, because an operator must be able to
 * read what a case costs BEFORE authorizing anything. 404 until a done current run
 * exists — there is nothing to price before the work exists. */
export async function fetchInvoice(
  caseId: string,
): Promise<ApiResult<InvoiceView>> {
  return fetchJson<InvoiceView>(
    `/api/case-sessions/${encodeURIComponent(caseId)}/invoice`,
  );
}

/** A QC image's URL (EVIDENCE class, ungated) — handed to a lazy <img>, so the
 * bytes never pass through this JSON client. */
export function qcImageUrl(caseId: string, filename: string): string {
  return `/api/case-sessions/${encodeURIComponent(caseId)}/runs/current/qc/${encodeURIComponent(filename)}`;
}

/**
 * A RUN MESH's URL, for the 3D preview tabs (client 2026-08-01: "the previews of the
 * artifacts") — EVIDENCE class, ungated like the QC images: an in-app RENDERED view
 * of what the run produced is what the operator judges before they sign and pay for
 * it, the same class as the QC renders and the invoice. The DOWNLOAD list stays
 * release-gated exactly as it is — this endpoint serves geometry for rendering only,
 * named by the server, never a path this client invents. Handed to the viewer
 * package's STL loader; the bytes never pass through this JSON client.
 */
export function previewMeshUrl(caseId: string, filename: string): string {
  return `/api/case-sessions/${encodeURIComponent(caseId)}/runs/current/preview-mesh/${encodeURIComponent(filename)}`;
}

// NO ACTOR HEADER (client 2026-07-27: "WE dont need operator name the checkmark is
// sufficient"). Every gating call used to carry `X-Operator` and the BFF 422'd
// without it. A self-typed name behind no authentication was a text field, not
// identity; the acts themselves are the record now, and real identity arrives with
// real auth (plan §8 / phase-2). Deliberate — do not re-add it as a missing header.

/** The confirmation's wire body: dispositions keyed tooth-as-string, plus the
 * terms acceptance (plan §10-A) — required, mirroring the payment stub's
 * ``authorize`` shape: the act happens by being SAID, never assumed. */
export interface ConfirmBody {
  dispositions: Record<string, "release" | "withhold">;
  acknowledged_flags: number[];
  terms_accepted: boolean;
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

/**
 * The payment STUB: the explicit act, plus the PRECONDITION naming the priced
 * document this browser displayed. The UI labels the button as a stub, and the BFF
 * records provider "stub" so it stays tellable.
 *
 * `invoiceFingerprint` IS NOT AN AMOUNT (audit 2026-07-31). No body this app can
 * send carries one and none ever will — a client that could POST an amount could
 * pay $0 for a released case. What rides here is the opaque digest the invoice
 * itself served, echoed back: the server re-derives the price at authorization time
 * and refuses 409 ("the price moved since you read it") when the two documents
 * differ. Without it, a `turnaround` PUT from a second tab moved the price from
 * $32.00 to $48.00 between the render and the click, and the charge landed at a
 * figure no surface ever displayed.
 */
export async function postPayment(
  caseId: string,
  invoiceFingerprint?: string | null,
): Promise<ApiResult<CaseSessionDetail>> {
  return fetchJson<CaseSessionDetail>(
    `/api/case-sessions/${encodeURIComponent(caseId)}/payment`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(
        invoiceFingerprint != null && invoiceFingerprint !== ""
          ? { authorize: true, invoice_fingerprint: invoiceFingerprint }
          : { authorize: true },
      ),
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

/**
 * THE RETURN FROM CHECKOUT (plan §10-A: "a checkout screen and a return").
 * ``reference`` is an opaque identifier only — this call asserts NOTHING about
 * payment, and the response is the SAME whole-detail shape every other action
 * returns: re-read the case, trust nothing the return leg itself claimed. The
 * actual authorization comes from ``postPayment`` alone; this exists so the UI
 * can model "coming back" without ever needing to interpret a "success" value
 * from an untrusted redirect.
 */
export async function postCheckoutReturn(
  caseId: string,
  reference: string,
): Promise<ApiResult<CaseSessionDetail>> {
  return fetchJson<CaseSessionDetail>(
    `/api/case-sessions/${encodeURIComponent(caseId)}/checkout/return`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ reference }),
    },
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
  /** The run-row numbers this act RE-DERIVED over the new pose. */
  deviation: Record<string, unknown> | null;
  /** The run-row numbers it could NOT re-derive, named — what the operator carries
   * into Deliver, where the confirmation seals them. */
  stale_metrics: string[];
  nudge: Record<string, unknown> | null;
  applied_delta_deg: number | null;
  cumulative_deg: number | null;
  stability_excess_mm: number | null;
  best_fit: Record<string, unknown> | null;
  /** ONE ROW PER OBSERVATION — a span contributes two (its midpoint and, when the
   * span reads as radial, its direction), each with its own residual. */
  pairs: Array<Record<string, unknown>>;
  residual_rms_mm: number | null;
  /**
   * WHETHER THAT RMS IS EVIDENCE (defect cap6020-neodent-gm, 2026-08-01). `false` on a
   * fit-by-points that landed on ONE observation — exactly determined, residual zero by
   * construction, and `residual_rms_mm` null for the same reason. `null` on every tool
   * that produces no residual at all: "not applicable" and "the number would have meant
   * nothing" are different answers, and only the server may give either.
   */
  cross_checked: boolean | null;
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

/**
 * WHAT A RE-READ FOUND (POST .../sites/{tooth}/re-preview — gap
 * `re-preview-a-site-without-applying-a-tool`, 2026-07-31). Measurements and names,
 * never a verdict.
 *
 * `rederived` is what the panes' instrument reads at the pose on disk; `previous` is
 * what the run row said before; `changed` is the SERVER's answer to whether anything
 * moved — the row was judged by it, and no comparison happens here.
 *
 * `stale_metrics` is the row's existing staleness, untouched: a re-read moves
 * nothing, so nothing becomes stale through it, and it cannot clear what an earlier
 * rework left behind either (only a full run re-derives those).
 */
export interface RePreviewView {
  tooth: number;
  run_id: string;
  changed: boolean;
  rederived: Record<string, number | null>;
  previous: Record<string, number | null>;
  stale_metrics: string[];
  pane_payload: SitePreviewPayload;
  case: CaseSessionDetail;
}

/**
 * RE-READ A SITE WITHOUT APPLYING A TOOL. Body-less: everything the server reads is
 * in the run directory, so there is nothing to send.
 *
 * A CONTROL THAT CALLS THIS MAY PROMISE A RE-READ AND NEVER AN OUTCOME. The design
 * prototype labels its own re-preview button with the verdict it expects ("this will
 * pass"); that is a client-side verdict, and this app does not make them. Label the
 * act, render what comes back.
 */
export async function postRePreview(
  caseId: string,
  tooth: number,
): Promise<ApiResult<RePreviewView>> {
  return fetchJson<RePreviewView>(siteActionPath(caseId, tooth, "re-preview"), {
    method: "POST",
  });
}

/** One acceptance metric for a single site, as the catalog evaluated it. The same
 * shape `AssuranceReference` carries on a Deliver row — one catalog, one wire
 * shape — plus the audience the domain assigns it ("doctor" | "lab"). */
export interface SiteAcceptanceMetric extends AssuranceReference {
  audience: string;
}

/**
 * ONE SITE'S ACCEPTANCE NUMBERS, for the workspace (GET .../sites/{tooth}/acceptance
 * — gap `deviation-budget-in-workspace`, 2026-07-31): each measured value beside the
 * band it falls in and the band's own thresholds, so Declare and Adjust can answer
 * "how much room is left, and on which metric?" from the numbers the pipeline already
 * computes and cites.
 *
 * NOT the design's three-lever budget: that divides a rotation error, a diameter
 * error and a residual scatter by a tolerance the browser holds. None of those exist
 * here, the product's deviation is measured over real mesh, and a tolerance
 * comparison never happens in this app.
 *
 * 404 without a done current run — pre-run there is genuinely nothing measured, which
 * is what a "no run yet" note is for, not something to fill with zeros.
 */
export interface SiteAcceptanceView {
  tooth: number;
  run_id: string;
  /** The catalog's own worst evaluated band over this row. */
  overall_band: string;
  /** Metric keys this row could not measure — never counted as passes. */
  missing: string[];
  metrics: SiteAcceptanceMetric[];
  /** Which of these numbers predate a rework (the row's own naming). */
  stale_metrics: string[];
  context: Record<string, unknown>;
}

export async function fetchSiteAcceptance(
  caseId: string,
  tooth: number,
): Promise<ApiResult<SiteAcceptanceView>> {
  return fetchJson<SiteAcceptanceView>(
    siteActionPath(caseId, tooth, "acceptance"),
  );
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

/**
 * Mark a cap the DETECTOR MISSED (client 2026-07-28). Detection finds 8 of the 10
 * sites on this fleet; without this a missed cap could not be worked at all.
 *
 * An operator ACT in the allowlist's sense — WHICH tooth and WHERE — never a status.
 * The site the BFF creates starts at `detected` and climbs the same ladder, so
 * marking buys work to do, not a rung. The centre is sent exactly as clicked: the
 * re-click pair-integrity rule says a human's mark is fixed here or refused, never
 * quietly re-centred downstream.
 */
export async function postMarkedSite(
  caseId: string,
  tooth: number,
  center: readonly number[],
): Promise<ApiResult<CaseSessionDetail>> {
  return fetchJson<CaseSessionDetail>(`/api/case-sessions/${encodeURIComponent(caseId)}/sites`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ tooth, center: [...center] }),
  });
}

/**
 * RE-MARK an EXISTING site's centre (PUT /{id}/sites/{tooth}/mark — client
 * 2026-08-01, the tooth-29 gap: the detector's proposed centre sat visibly off
 * the cap, and the operator had no door to correct it).
 *
 * `postMarkedSite`'s exact complement — the tooth is already the path, not the
 * body, because the site already exists. The centre is sent exactly as clicked,
 * same as a first mark: the re-click pair-integrity rule says a human's mark is
 * fixed here or refused, never quietly re-centred downstream, so a re-mark
 * REPLACES the old mark whole.
 *
 * THIS RESET IS NEVER SPRUNG. The BFF retires the site's preview and review, the
 * current run and any confirmation over it, but the words that say so
 * (domain/intake.remarkWords) must be shown and CONFIRMED before the click that
 * calls this is ever armed — this function only fires the already-consented act.
 */
export async function putRemarkedSite(
  caseId: string,
  tooth: number,
  center: readonly number[],
): Promise<ApiResult<CaseSessionDetail>> {
  return fetchJson<CaseSessionDetail>(siteActionPath(caseId, tooth, "mark"), {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ center: [...center] }),
  });
}

// --- Auto-mark (client 2026-07-29, item 3): the software proposes the part half -------

/**
 * ONE PROPOSED LANDMARK (GET .../sites/{tooth}/landmarks), the worker's own
 * ``clock_landmarks`` row verbatim: ``point`` is already in the part's CANONICAL
 * frame — the same frame pane 1 renders and a pane-1 click would produce — so it can
 * fill a correspondence pair's part half exactly as a free click does. Served best
 * lever arm FIRST: rotation error scales as 1/lever, so the first landmark is the one
 * whose match buys the most.
 */
export interface LandmarkView {
  id: string;
  kind: string;
  point: number[];
  lever_arm_mm: number;
  azimuth_deg: number;
}

/**
 * AUTO-MARK'S READ: the site's declared part's rotation-defining landmarks, filtered
 * and ordered by the worker (``PartFeature.defines_rotation``, lever arm descending).
 * A pure read, on the same precondition as every other Adjust tool — a 404/409/422
 * renders through the same `ApiResult` refusal path as everywhere else on this surface.
 */
export async function fetchLandmarks(
  caseId: string,
  tooth: number,
): Promise<ApiResult<LandmarkView[]>> {
  return fetchJson<LandmarkView[]>(siteActionPath(caseId, tooth, "landmarks"));
}

/**
 * START OVER (client 2026-07-30, the demo's door back): withdraw the confirmation,
 * the payment and the release together, so the delivery flow can be walked again.
 * Body-less — the act's whole content is the request; the server refuses when
 * nothing is signed, and everything below the signatures (the run, every site rung)
 * survives untouched.
 */
export async function postDeliveryReset(
  caseId: string,
): Promise<ApiResult<CaseSessionDetail>> {
  return fetchJson<CaseSessionDetail>(
    `/api/case-sessions/${encodeURIComponent(caseId)}/delivery/reset`,
    { method: "POST" },
  );
}

/** One terms version, verbatim from the BFF. `status` is "placeholder" until the
 *  client's real text lands — the surface renders that word rather than deciding
 *  for itself whether what it received is binding. */
export interface TermsDocumentView {
  version: string;
  title: string;
  status: string;
  body: string;
}

/**
 * Fetch a terms version — the CURRENT one when `version` is omitted (client
 * 2026-07-30). A confirmation records which version it accepted; this is what makes
 * that record resolvable rather than a string pointing at nothing.
 */
export async function fetchTerms(
  version?: string,
): Promise<ApiResult<TermsDocumentView>> {
  const path =
    version === undefined
      ? "/api/terms"
      : `/api/terms/${encodeURIComponent(version)}`;
  return fetchJson<TermsDocumentView>(path);
}

/**
 * RESET THE WHOLE CASE to fresh intake (client 2026-07-30: "there is a need for
 * resetting the cases persistance"). Body-less. Clears the session — system,
 * declarations, previews, detection, run and every signature — while the immutable
 * run directories stay on disk as history (AM-1).
 */
export async function postCaseReset(
  caseId: string,
): Promise<ApiResult<CaseSessionDetail>> {
  return fetchJson<CaseSessionDetail>(
    `/api/case-sessions/${encodeURIComponent(caseId)}/reset`,
    { method: "POST" },
  );
}

// --- the case's narrative (gap `session-activity-log`, 2026-07-31) --------------------
//
// THERE IS NO POST HERE, AND THERE NEVER WILL BE. The log is appended SERVER-SIDE
// inside the same write that lands each act (bff/session.record_activity), so an entry
// exists exactly when the act it names landed. The design prototype keeps its log in a
// browser array; a list this app maintained — or one the BFF would accept — would read
// as an audit trail while proving nothing, which is the same class of untruth as a
// client-claimed status.

/** One act, verbatim. No actor: this stack authenticates nobody, and `at` is the fact
 * the act genuinely produced. `tooth` is null on case-level acts. */
export interface ActivityEntryView {
  at: string;
  event: string;
  detail: string;
  tooth: number | null;
}

/** One entry off a site's shipped record in the run directory, as the WORKER wrote it
 * (`case_prep.application.adjust._finish_adjustment`). `who` reads "operator (no
 * identity is captured)" — carried verbatim, disclaimer included, because dropping it
 * would leave the word "operator" looking like an identity. */
export interface SiteAdjustmentView {
  tooth: number;
  at: string;
  operation: string;
  who: string;
  detail: string;
}

/**
 * The case's narrative. `entries` arrive NEWEST FIRST, ordered by the server.
 *
 * IT IS A WINDOW, NOT AN AUDIT TRAIL, and the shape says so: `recorded` counts every
 * act ever recorded while `window` is how many the log keeps, so a surface can say
 * "the last 40 of 137" rather than implying it is showing everything. The session
 * document is re-read per request and its size is pinned, which is why the log is
 * bounded at all.
 */
export interface CaseActivityView {
  case_id: string;
  entries: ActivityEntryView[];
  recorded: number;
  window: number;
  run_id: string | null;
  site_adjustments: SiteAdjustmentView[];
}

export async function fetchActivity(
  caseId: string,
): Promise<ApiResult<CaseActivityView>> {
  return fetchJson<CaseActivityView>(
    `/api/case-sessions/${encodeURIComponent(caseId)}/activity`,
  );
}
