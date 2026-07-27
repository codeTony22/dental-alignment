/**
 * Case-prep automation API client. Isolates all fetch/IO; callers get domain types back.
 */
import type {
  AlignToMarkResult,
  BestFitRequest,
  BestFitResult,
  Case,
  ConfirmAlignmentResult,
  ConfirmedSite,
  ConstructionPart,
  ImplantPose,
  LibraryCatalogGroup,
  LibraryVariant,
  NudgeRequest,
  NudgeResult,
  ProposeResult,
  RunResult,
  SiteDeviation,
  Vec3,
} from "../domain/types";
import { withCacheBust } from "../domain/types";
import type { AuthorizedRunSelection } from "../domain/runGate";
import type { ReliefLimit } from "../domain/reliefLimit";
import type { PartAnnotation, PartFeatureInput } from "../domain/partFeatures";
import type { PoseTransferDocument, PoseTransferSite } from "../domain/poseTransfer";
import type { AlignToCorrespondenceResult, CorrespondencePair } from "../domain/correspondence";
import {
  mapAlignToCorrespondenceResult,
  mapAlignToMarkResult,
  mapBestFitResult,
  mapCase,
  mapPartAnnotation,
  toWireCorrespondencePairs,
  toWirePartFeatures,
  mapConfirmAlignmentResult,
  mapConstructionParts,
  mapImplantPose,
  mapLibraryCatalog,
  mapLibraryVariants,
  mapNudgeResult,
  mapProposeResult,
  mapReliefLimit,
  mapRunResult,
  mapSiteDeviation,
  toWireImportPose,
  toWireRunSiteInput,
} from "./mappers";
import type {
  WireAlignToCorrespondenceRequest,
  WireAlignToCorrespondenceResult,
  WireAlignToMarkResult,
  WireBestFitResult,
  WireCase,
  WirePartAnnotation,
  WirePartFeaturesRequest,
  WireConfirmAlignmentResult,
  WireConstructionPart,
  WireImplantRecord,
  WireImportPoseRequest,
  WireLibraryCatalogGroup,
  WireLibraryVariant,
  WireNudgeResult,
  WireProposeResult,
  WireReliefLimit,
  WireRunRequest,
  WireRunResult,
  WireSiteDeviation,
} from "./wireTypes";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
    /** The server's raw `detail` body when it was an OBJECT rather than a plain sentence —
     *  today only the best-fit "already_optimal" confirmation (client ask 2026-07-26). Every
     *  string detail still lands in `message` alone, so no existing consumer changes; typed
     *  readers go through helpers like `bestFitAlreadyOptimal`, never through prose. */
    readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** The best-fit "already optimal" outcome, parsed from an ApiError — the machine-readable
 *  confirmation the server sends in place of a refusal sentence (kind "already_optimal").
 *  Null for anything else, including every plain-string 409, which keeps rendering as the
 *  error it is. NO prose matching: the discriminator is the `kind` field alone. */
export interface BestFitAlreadyOptimal {
  readonly message: string;
  readonly matchingDiameterMm: number;
  readonly suggestedDiameterMm: number;
}

export function bestFitAlreadyOptimal(err: unknown): BestFitAlreadyOptimal | null {
  if (!(err instanceof ApiError) || err.status !== 409) return null;
  if (err.detail === null || typeof err.detail !== "object") return null;
  const d = err.detail as {
    kind?: unknown;
    message?: unknown;
    matching_diameter_mm?: unknown;
    suggested_diameter_mm?: unknown;
  };
  if (d.kind !== "already_optimal") return null;
  if (typeof d.message !== "string") return null;
  if (typeof d.matching_diameter_mm !== "number" || typeof d.suggested_diameter_mm !== "number") {
    return null;
  }
  return {
    message: d.message,
    matchingDiameterMm: d.matching_diameter_mm,
    suggestedDiameterMm: d.suggested_diameter_mm,
  };
}

async function parseJsonOrThrow<T>(res: Response, action: string): Promise<T> {
  if (!res.ok) {
    let detail = "";
    try {
      detail = await res.text();
    } catch {
      // ignore — body may be empty/unreadable
    }
    throw new ApiError(
      `${action} failed (${res.status} ${res.statusText})${detail ? `: ${detail}` : ""}`,
      res.status,
    );
  }
  try {
    return (await res.json()) as T;
  } catch {
    throw new ApiError(`${action} returned an invalid response`);
  }
}

async function safeFetch(input: string, init: RequestInit | undefined, action: string): Promise<Response> {
  try {
    return await fetch(input, init);
  } catch (err) {
    const reason = err instanceof Error ? err.message : String(err);
    throw new ApiError(`${action}: could not reach the automation backend (${reason})`);
  }
}

export async function fetchCases(): Promise<Case[]> {
  const res = await safeFetch("/api/cases", undefined, "Loading cases");
  const wire = await parseJsonOrThrow<WireCase[]>(res, "Loading cases");
  return wire.map(mapCase);
}

export function scanUrlFor(caseId: string): string {
  return `/api/cases/${encodeURIComponent(caseId)}/scan`;
}

/**
 * The FULL cross-model part catalog for the library BROWSER (GET /api/library —
 * case-independent). A 404 here has a specific meaning the caller must distinguish: the
 * RUNNING backend predates the endpoint (restart `make serve`), so the ApiError's status
 * is surfaced for the browser panel's "endpoint not available" state instead of a toast.
 */
export async function fetchLibraryCatalog(): Promise<LibraryCatalogGroup[]> {
  const res = await safeFetch("/api/library", undefined, "Loading the part library");
  const wire = await parseJsonOrThrow<WireLibraryCatalogGroup[]>(res, "Loading the part library");
  return mapLibraryCatalog(wire);
}

/**
 * The chosen implant system's healing-cap catalog for a case, so the doctor can pick a variant
 * before alignment. `model` names the system EXPLICITLY (client directive 2026-07-25); omitting
 * it falls back to the case's non-binding suggestion server-side, and a case with no suggestion
 * answers 409 rather than guessing — surfaced with its status so the caller can distinguish
 * "nothing selected yet" from a real failure.
 */
export async function fetchLibrary(caseId: string, model?: string | null): Promise<LibraryVariant[]> {
  const query = model ? `?model=${encodeURIComponent(model)}` : "";
  const res = await safeFetch(
    `/api/cases/${encodeURIComponent(caseId)}/library${query}`,
    undefined,
    "Loading the cap library",
  );
  const wire = await parseJsonOrThrow<WireLibraryVariant[]>(res, "Loading the cap library");
  return mapLibraryVariants(wire);
}

/**
 * Every vendor CONSTRUCTION part on disk (GET /api/constructions) — the operator picks one by
 * `pathId`. A 404 here has the same specific meaning as the catalog's: the RUNNING backend
 * predates the endpoint (restart `make serve`), so the status rides on the ApiError for the
 * selection column's "endpoint not available" state instead of a toast.
 */
export async function fetchConstructions(): Promise<ConstructionPart[]> {
  const res = await safeFetch("/api/constructions", undefined, "Loading the construction parts");
  const wire = await parseJsonOrThrow<WireConstructionPart[]>(res, "Loading the construction parts");
  return mapConstructionParts(wire);
}

/**
 * THE MAXIMUM SAFE GINGIVAL RELIEF for one (construction part x cap variant) pair
 * (GET /api/relief-limit) — the ceiling the export gate would enforce at the END of a run,
 * measured up front so the operator meets it while choosing the number.
 *
 * A 404 has the same specific meaning as /api/constructions' and /api/library's: the RUNNING
 * backend predates the endpoint (restart `make serve`). The status rides on the ApiError so the
 * selection column can show its inline hint instead of raising a toast — and the absence is not
 * dangerous: the run still clamps to the safe maximum and reports it.
 */
export async function fetchReliefLimit(
  constructionPathId: string,
  model: string,
  variant: string,
): Promise<ReliefLimit> {
  const query = new URLSearchParams({
    construction_path: constructionPathId,
    model,
    variant,
  }).toString();
  const res = await safeFetch(`/api/relief-limit?${query}`, undefined, "Loading the relief limit");
  const wire = await parseJsonOrThrow<WireReliefLimit>(res, "Loading the relief limit");
  return mapReliefLimit(wire);
}

/**
 * THE THREE-PANEL VERIFY's union colouring for one seated site: the posed cap mesh in the jaw
 * world frame with a signed millimetre per vertex, the colorbar bounds, and the site's PUBLISHED
 * acceptance stats. 404 means this site has not been seated yet (no run) — the panel's own
 * graceful state, so the status is surfaced on the ApiError rather than raised as a toast.
 */
export async function fetchSiteDeviation(caseId: string, tooth: number): Promise<SiteDeviation> {
  const res = await safeFetch(
    `/api/cases/${encodeURIComponent(caseId)}/sites/${tooth}/deviation`,
    undefined,
    "Loading the deviation overlay",
  );
  const wire = await parseJsonOrThrow<WireSiteDeviation>(res, "Loading the deviation overlay");
  return mapSiteDeviation(wire);
}

/**
 * THE PRE-RUN ALIGNMENT PREVIEW (client, 2026-07-26: "verify must work on the first pass").
 * Seats ONE marked site's chosen cap and returns the union pane's colouring — the SAME payload
 * shape (and the same instrument, and the same scale) as `fetchSiteDeviation`, flagged
 * `preview: true`. Nothing is emitted: no package, no run row, no run-gate bypass.
 *
 * The body is the run's own — the operator's selection plus the marked sites — because the
 * preview must be produced from exactly the inputs Process would use; a preview built from
 * anything else would be verifying a different alignment than the one about to ship.
 *
 * A 404 means the RUNNING backend predates the endpoint (restart `make serve`), which the union
 * pane states as its pre-run notice rather than raising a toast — the same treatment
 * /api/constructions and /api/library already get. A 422 (incomplete selection, no declared cap,
 * a tooth that was not sent) and a 409 (the marks could not be seated) carry the server's own
 * sentence.
 */
export async function previewSiteAlignment(
  caseId: string,
  tooth: number,
  sites: readonly ConfirmedSite[],
  selection: {
    readonly model: string;
    readonly constructionPathId: string;
    readonly jaw: string;
    readonly gingivalOffsetMm: number;
  },
): Promise<SiteDeviation> {
  const body: WireRunRequest = {
    sites: sites.map(toWireRunSiteInput),
    fresh: false,
    model: selection.model,
    construction_path: selection.constructionPathId,
    jaw: selection.jaw,
    gingival_offset_mm: selection.gingivalOffsetMm,
  };
  const res = await safeFetch(
    `/api/cases/${encodeURIComponent(caseId)}/sites/${tooth}/preview-alignment`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
    "Previewing the alignment",
  );
  await throwServerDetail(res, "Previewing the alignment");
  const wire = await parseJsonOrThrow<WireSiteDeviation>(res, "Previewing the alignment");
  return mapSiteDeviation(wire);
}

export async function proposeSites(caseId: string, fresh = false): Promise<ProposeResult> {
  const query = fresh ? "?fresh=true" : "";
  const res = await safeFetch(
    `/api/cases/${encodeURIComponent(caseId)}/propose${query}`,
    { method: "POST" },
    "Running detection",
  );
  const wire = await parseJsonOrThrow<WireProposeResult>(res, "Running detection");
  return mapProposeResult(wire);
}

/**
 * Run the automation with the operator's DECODING SELECTION (client directive 2026-07-25: "the
 * lab chooses, the software never guesses"). The selection is not optional on the wire — the
 * backend 422s with one operator-readable sentence when the implant system or the construction
 * part is missing, and it will NOT fall back to the case's suggestion. The suggestion may be
 * what fills `selection` here, but only because a human saw it and sent it back.
 *
 * `selection` is an `AuthorizedRunSelection`: the ONLY producer of that type is
 * domain/runGate's `authorizeRun`, and it produces one only when every required selection is
 * made AND every site has been reviewed. That is deliberate — the acknowledgment
 * gate was bypassable from three UI routes precisely because each route re-implemented the
 * check; now a route that skips it cannot construct an argument for this function.
 *
 * A 422 refusal carries the server's own sentence (the same `detail` contract as the rotation
 * gates), so the operator reads "choose the construction part…" rather than a status line.
 */
export async function runAutomation(
  caseId: string,
  sites: readonly ConfirmedSite[],
  fresh = false,
  selection: AuthorizedRunSelection,
): Promise<RunResult> {
  const body: WireRunRequest = {
    sites: sites.map(toWireRunSiteInput),
    fresh,
    model: selection.model,
    construction_path: selection.constructionPathId,
    jaw: selection.jaw,
    gingival_offset_mm: selection.gingivalOffsetMm,
  };
  const res = await safeFetch(
    `/api/cases/${encodeURIComponent(caseId)}/run`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
    "Running automation",
  );
  await throwServerDetail(res, "Running automation");
  const wire = await parseJsonOrThrow<WireRunResult>(res, "Running automation");
  return mapRunResult(wire);
}

/**
 * MANUAL BEST FIT (the client's register/best-fit panel, 2026-07-25): refine one seated site by
 * matching the scan's surface to the library part within a MATCHING DIAMETER — their own
 * control, their own 0.3 mm default. `apply: false` measures without moving the part (a dry
 * run the operator can read before committing), `apply: true` re-seats it and the backend
 * re-emits that site's aligned STL + implant.json exactly as a nudge does.
 *
 * A refusal (the same stability/certification gates every pose change is judged by) carries the
 * server's own sentence; a 404 means the RUNNING backend predates the endpoint — the status
 * rides on the ApiError so the panel can say "restart make serve" instead of raising a toast.
 */
export async function bestFitSite(
  caseId: string,
  tooth: number,
  request: BestFitRequest,
): Promise<BestFitResult> {
  const res = await safeFetch(
    `/api/cases/${encodeURIComponent(caseId)}/sites/${tooth}/best-fit`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        matching_diameter_mm: request.matchingDiameterMm,
        apply: request.apply,
      }),
    },
    "Running the best fit",
  );
  await throwServerDetail(res, "Running the best fit");
  const wire = await parseJsonOrThrow<WireBestFitResult>(res, "Running the best fit");
  return mapBestFitResult(wire);
}

/**
 * The operator rotation nudge at the review gate: propose a signed rotation step (or a reset
 * to the pipeline's certified pose) for one seated site. The backend judges the proposal with
 * the same ring-fixed stability bound and certification gates as its own clocking pass — a
 * refusal comes back as a 409 whose body carries the human-readable reason in `detail`, which
 * this surfaces as the ApiError message (not the generic "(409 Conflict): {json}" wrapping)
 * so the UI can show the server's own sentence to the operator.
 */
export async function nudgeRotation(caseId: string, tooth: number, request: NudgeRequest): Promise<NudgeResult> {
  const body = request.kind === "reset" ? { reset: true } : { delta_deg: request.deltaDeg };
  const res = await safeFetch(
    `/api/cases/${encodeURIComponent(caseId)}/sites/${tooth}/nudge-rotation`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
    "Nudging the rotation",
  );
  await throwServerDetail(res, "Nudging the rotation");
  const wire = await parseJsonOrThrow<WireNudgeResult>(res, "Nudging the rotation");
  return mapNudgeResult(wire);
}

/**
 * ALIGN-TO-MARKED-TRENCH: the operator clicked the cap's coded cutout/trench on the scan;
 * the backend rotates the seated cap so its nearest code feature lands on that mark — a
 * PROPOSAL judged by the exact nudge machinery (ring-fixed stability bound + certification
 * gates), never a bypass. A refusal (or an out-of-range mark) surfaces the server's own
 * sentence as the ApiError message, same pattern as nudgeRotation.
 */
export async function alignToMark(caseId: string, tooth: number, point: Vec3): Promise<AlignToMarkResult> {
  const res = await safeFetch(
    `/api/cases/${encodeURIComponent(caseId)}/sites/${tooth}/align-to-mark`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ point }),
    },
    "Aligning to the mark",
  );
  await throwServerDetail(res, "Aligning to the mark");
  const wire = await parseJsonOrThrow<WireAlignToMarkResult>(res, "Aligning to the mark");
  return mapAlignToMarkResult(wire);
}

/**
 * The LIBRARY PART's marked features (client ask 2026-07-24, half one): the persisted
 * operator annotation for one catalog part, or the MACHINE's own reading when the part has
 * never been marked (`autoSeeded` says which). A 404 has the same specific meaning as the
 * catalog's — the RUNNING backend predates these endpoints (restart `make serve`) — since
 * the model/id pair always comes out of the catalog the same server just served, so an
 * "unknown part" 404 cannot happen in the UI's own flow; the status is surfaced on the
 * ApiError for the panel's "endpoint not available" state instead of a toast.
 */
export async function fetchPartFeatures(model: string, variant: string): Promise<PartAnnotation> {
  const res = await safeFetch(featuresUrl(model, variant), undefined, "Loading the part's marks");
  const wire = await parseJsonOrThrow<WirePartAnnotation>(res, "Loading the part's marks");
  return mapPartAnnotation(wire);
}

/**
 * Persist the operator's marks for one catalog part. A mark placed by CLICK travels as a
 * canonical-frame `point` so the SERVER performs the authoritative snap onto its own reading
 * (same id, same geometry — that is what keeps a human mark and the clock instrument talking
 * about the same cutout); an untouched mark travels as its azimuth. Every stored mark comes
 * back with source "operator" — the annotation is now the human's. A 422 (empty list, too
 * many features, a click off the part or inside the lever arm, two marks on the same feature)
 * carries the server's own sentence, same pattern as nudgeRotation.
 */
export async function savePartFeatures(
  model: string,
  variant: string,
  features: readonly PartFeatureInput[],
): Promise<PartAnnotation> {
  const body: WirePartFeaturesRequest = { features: toWirePartFeatures(features) };
  const res = await safeFetch(
    featuresUrl(model, variant),
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
    "Saving the part's marks",
  );
  await throwServerDetail(res, "Saving the part's marks");
  const wire = await parseJsonOrThrow<WirePartAnnotation>(res, "Saving the part's marks");
  return mapPartAnnotation(wire);
}

/** Revert one catalog part to the machine's own reading (drops the stored annotation). The
 *  response is the auto seed the part falls back to — nothing is left in an unknown state. */
export async function resetPartFeatures(model: string, variant: string): Promise<PartAnnotation> {
  const res = await safeFetch(
    featuresUrl(model, variant),
    { method: "DELETE" },
    "Resetting the part's marks",
  );
  await throwServerDetail(res, "Resetting the part's marks");
  const wire = await parseJsonOrThrow<WirePartAnnotation>(res, "Resetting the part's marks");
  return mapPartAnnotation(wire);
}

function featuresUrl(model: string, variant: string): string {
  return `/api/library/${encodeURIComponent(model)}/${encodeURIComponent(variant)}/features`;
}

/**
 * ALIGN TO NAMED MARKS (client ask 2026-07-24, half two): the operator named WHICH library
 * feature each scan click corresponds to, so the rotation is EXPLICIT rather than bound to
 * the nearest code feature — the ambiguity align-to-mark cannot resolve on a 2-3 feature cap,
 * and the only instrument at all where the automatic code reader has no evidence. A pair may
 * also be a FREE POINT (client ask 2026-07-26): an arbitrary canonical-frame click on the
 * part, travelling as `part_point` (see toWireCorrespondencePairs). One pair gives the
 * rotation directly; several give a best fit plus the per-pair residuals ("your marks agree
 * to 0.34mm"). Still a PROPOSAL judged by the exact nudge machinery — a refusal surfaces the
 * server's own sentence, same pattern as alignToMark.
 */
export async function alignToCorrespondence(
  caseId: string,
  tooth: number,
  pairs: readonly CorrespondencePair[],
): Promise<AlignToCorrespondenceResult> {
  const body: WireAlignToCorrespondenceRequest = {
    pairs: toWireCorrespondencePairs(pairs),
  };
  const res = await safeFetch(
    `/api/cases/${encodeURIComponent(caseId)}/sites/${tooth}/align-to-correspondence`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
    "Aligning to your marks",
  );
  await throwServerDetail(res, "Aligning to your marks");
  const wire = await parseJsonOrThrow<WireAlignToCorrespondenceResult>(res, "Aligning to your marks");
  return mapAlignToCorrespondenceResult(wire);
}

/**
 * IMPORT A POSE (client ask 2026-07-25, RealGUIDE screenshot parity): propose a previously
 * exported alignment for one site. It is an OPERATOR WRITE and travels the same road as the
 * nudge, align-to-mark and correspondence flows — the client PROPOSES, the server's gates judge
 * (stability bound + certification), the write is audited, and the response is the very same
 * `NudgeResult` shape those flows return, so a restored seat folds into the row identically.
 *
 * A 404 here is the SPECIFIC case the panel must distinguish, exactly like /api/constructions
 * and /api/library before it: the RUNNING backend predates this endpoint (restart `make serve`),
 * so the status rides on the ApiError rather than being raised as a generic failure toast. A 409
 * or 422 carries the server's own refusal sentence, shown verbatim.
 */
export async function importPose(
  caseId: string,
  tooth: number,
  doc: PoseTransferDocument,
  site: PoseTransferSite,
): Promise<NudgeResult> {
  const body: WireImportPoseRequest = toWireImportPose(doc, site);
  const res = await safeFetch(
    `/api/cases/${encodeURIComponent(caseId)}/sites/${tooth}/import-pose`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
    "Importing the pose",
  );
  await throwServerDetail(res, "Importing the pose");
  const wire = await parseJsonOrThrow<WireNudgeResult>(res, "Importing the pose");
  return mapNudgeResult(wire);
}

/**
 * Throw the server's OWN sentence (the FastAPI `detail` body) as the ApiError message when a
 * response failed — the gates' refusal reasons are written for the operator, so the toast
 * must show them verbatim rather than "(409 Conflict): {json}". Extracted from the
 * nudgeRotation/alignToMark/confirmAlignment flows, which all had this block inline.
 * No-op on a successful response, so callers can call it unconditionally before parsing.
 *
 * A detail may also be an OBJECT (client ask 2026-07-26: the best-fit "already optimal"
 * confirmation): its `message` string becomes the ApiError message — every consumer that
 * only reads `.message` keeps working — and the object itself rides on `.detail` for the
 * typed readers.
 */
async function throwServerDetail(res: Response, action: string): Promise<void> {
  if (res.ok) return;
  let message: string | null = null;
  let detail: unknown;
  try {
    const payload = (await res.json()) as { detail?: unknown };
    if (typeof payload.detail === "string") {
      message = payload.detail;
    } else if (payload.detail !== null && typeof payload.detail === "object") {
      detail = payload.detail;
      const m = (payload.detail as { message?: unknown }).message;
      if (typeof m === "string") message = m;
    }
  } catch {
    // fall through to the generic message
  }
  throw new ApiError(
    message ?? `${action} failed (${res.status} ${res.statusText})`,
    res.status,
    detail,
  );
}

/**
 * The doctor's manual sign-off on a site's alignment (the verification panel's confirm
 * control): records confirmed/retracted + an optional note into the site's run record and
 * the audit stream. Purely a recorded human judgment — the backend never changes a pose or
 * a gate from it. A 404 (no run yet / unknown site) surfaces the server's own sentence,
 * same pattern as nudgeRotation.
 */
export async function confirmAlignment(
  caseId: string,
  tooth: number,
  confirmed: boolean,
  note?: string,
): Promise<ConfirmAlignmentResult> {
  const body: { confirmed: boolean; note?: string } = { confirmed };
  if (note !== undefined && note.trim() !== "") body.note = note.trim();
  const res = await safeFetch(
    `/api/cases/${encodeURIComponent(caseId)}/sites/${tooth}/confirm-alignment`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
    "Recording the confirmation",
  );
  await throwServerDetail(res, "Recording the confirmation");
  const wire = await parseJsonOrThrow<WireConfirmAlignmentResult>(res, "Recording the confirmation");
  return mapConfirmAlignmentResult(wire);
}

/**
 * Fetch one tooth's "<case>-<tooth>-implant.json" package file (a plain static file under
 * filesBase, not an /api/cases/... endpoint — same URL shape PackageFileList already links to)
 * and extract its seated pose for the post-run axis triad. Returns null on any failure (missing
 * file, malformed JSON, network error) rather than throwing — a triad is a nice-to-have overlay,
 * not something that should surface an error toast or block the rest of the results from showing.
 * `version` cache-busts the request (withCacheBust; a no-op when null) — same belt-and-braces
 * concern as the mesh files: an open tab could otherwise reuse a browser-cached implant.json from
 * an earlier run for this same case/tooth.
 */
export async function fetchImplantPose(
  filesBase: string,
  caseId: string,
  tooth: number,
  version: number | null = null,
): Promise<ImplantPose | null> {
  const url = withCacheBust(`${filesBase}${caseId}-${tooth}-implant.json`, version);
  try {
    const res = await fetch(url);
    if (!res.ok) return null;
    const wire = (await res.json()) as WireImplantRecord;
    return mapImplantPose(wire);
  } catch {
    return null;
  }
}
