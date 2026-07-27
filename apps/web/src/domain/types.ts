/**
 * Domain types mirroring the case-prep automation backend contract.
 * Kept framework-free: no React, no fetch — pure shapes + narrow helpers.
 */

export type Vec3 = readonly [number, number, number];

export interface SuggestedSite {
  readonly tooth: number;
  readonly center: Vec3;
  readonly declaredVariant: string | null;
  /** RealGUIDE-style registration points, when the model already has them: cap CENTER... */
  readonly centerMark: Vec3 | null;
  /** ...and a point on the cap's WIDEST rim edge. Together they give center+radius directly. */
  readonly rimMark: Vec3 | null;
}

/** The two arches a case can be. The backend validates the run's `jaw` against exactly these. */
export type Jaw = "upper" | "lower";

export const JAWS: readonly Jaw[] = ["upper", "lower"];

/** Narrow an open wire string to a Jaw, defaulting to "upper" — the server only ever sends one
 *  of the two, so this is a type bridge rather than a guess about clinical content. */
export function asJaw(value: string): Jaw {
  return value === "lower" ? "lower" : "upper";
}

/**
 * A case as NO-INFERENCE discovery serves it (client directive 2026-07-25: "the lab chooses,
 * the software never guesses"). Every scan folder with an STL is a case — a real upload named
 * "patient-4471" loads like any other. `suggestedModel`/`suggestedConstruction`/`jaw` are the
 * old folder-name match demoted to DEFAULTS the operator sees and can change; null means the
 * name matched nothing, and the run then cannot proceed until the operator picks (the software
 * will not fill it in). `vendor` is derived from the suggested construction, hence nullable too.
 */
export interface Case {
  readonly id: string;
  readonly doctor: string;
  readonly jaw: Jaw;
  readonly vendor: string | null;
  readonly scanUrl: string;
  /** The scan file this case was discovered from ("upper_jaw.stl") — WHICH upload this is. */
  readonly scanFilename: string | null;
  /** A DEFAULT implant system to preselect; null when the folder name matched no system. */
  readonly suggestedModel: string | null;
  /** A DEFAULT construction `path_id` to preselect; null when nothing matched. */
  readonly suggestedConstruction: string | null;
  readonly suggestedSites: readonly SuggestedSite[];
}

/** One choosable vendor construction part (GET /api/constructions). `pathId` is the catalog's
 *  own stable handle ("<vendor>/<filename>") and the only thing the run accepts — no name
 *  matching, no path the client assembles itself. */
export interface ConstructionPart {
  readonly vendor: string;
  readonly filename: string;
  readonly pathId: string;
  readonly label: string;
}

/**
 * Capture gate (intake ADVISORY): the industry mechanism — coded-cap workflows
 * refuse scans without the entire cap circumference, clearly visible code markings and
 * a >=1mm supragingival collar, WHILE THE PATIENT IS IN THE CHAIR. Verdicts arrive
 * per site with the propose payload; a "rescan" must be prominent before the operator
 * invests marks.
 */
export type CaptureVerdict = "pass" | "marginal" | "rescan";

export interface CaptureCheck {
  readonly name: string; // "rim_arc" | "code_band" | "collar_exposure"
  readonly value: number | null;
  readonly boundPass: number;
  readonly boundRescan: number;
  readonly verdict: CaptureVerdict;
  readonly message: string;
}

export interface CaptureAssessment {
  readonly verdict: CaptureVerdict;
  readonly checks: readonly CaptureCheck[];
}

/** A capture assessment anchored at a world position — machine proposals and curated
 *  suggested sites both produce one; confirm rows match by proximity (captureNear). */
export interface CaptureSite {
  readonly center: Vec3;
  readonly tooth: number | null;
  readonly capture: CaptureAssessment;
}

/** A confirm row inherits the capture verdict measured at (essentially) its own centre;
 *  beyond this radius no proposal/suggested assessment describes the row's cap. Sites are
 *  clinically >=8mm apart (cap_detection._MIN_SEPARATION_MM), so 4mm cannot cross-match. */
export const CAPTURE_MATCH_RADIUS_MM = 4;

/** The capture assessment measured nearest to `center` (within CAPTURE_MATCH_RADIUS_MM),
 *  or null when none is close enough to describe this site. */
export function captureNear(
  center: Vec3,
  sites: readonly CaptureSite[],
): CaptureAssessment | null {
  let best: { d2: number; capture: CaptureAssessment } | null = null;
  const limit = CAPTURE_MATCH_RADIUS_MM * CAPTURE_MATCH_RADIUS_MM;
  for (const s of sites) {
    const dx = s.center[0] - center[0];
    const dy = s.center[1] - center[1];
    const dz = s.center[2] - center[2];
    const d2 = dx * dx + dy * dy + dz * dz;
    if (d2 <= limit && (best === null || d2 < best.d2)) {
      best = { d2, capture: s.capture };
    }
  }
  return best?.capture ?? null;
}

/** The checks worth telling the operator about (tooltips/banner): everything not passing. */
export function captureIssues(capture: CaptureAssessment): readonly CaptureCheck[] {
  return capture.checks.filter((c) => c.verdict !== "pass");
}

export interface Proposal {
  readonly center: Vec3;
  readonly voidRatio: number;
  readonly rimBelowCuspsMm: number;
  /** null on payloads from a backend predating the capture gate. */
  readonly capture: CaptureAssessment | null;
}

export interface ProposeResult {
  readonly proposals: readonly Proposal[];
  readonly durationS: number;
  readonly cached: boolean;
  /** Every capture-assessed anchor this propose pass produced (proposals + the case's
   *  curated suggested sites) — the step-2 chips and banner read from here. */
  readonly captureSites: readonly CaptureSite[];
}

/** A site as confirmed by the operator, ready to submit to /run. */
export interface ConfirmedSite {
  readonly tooth: number;
  readonly center: Vec3;
  readonly declaredVariant?: string;
  /** Operator-painted healing-cap patch, world-coord points on the loaded scan mesh (<=400, subsampled client-side). */
  readonly markedPoints?: readonly Vec3[];
  /** RealGUIDE-style registration point: a single click marking the cap's TOP CENTRE — just a
   *  locator when rimPoints is present (the rim circle fit supplies centre+radius); the sole
   *  centre source for legacy single-rimMark rows. */
  readonly centerMark?: Vec3;
  /** LEGACY single registration point: a click on the cap's WIDEST rim edge, paired with
   *  centerMark to give centre+radius directly. Still produced by curated prefills and still
   *  accepted by the backend, but superseded for new doctor input by rimPoints (multiple border
   *  clicks, robust to a single imprecise click via a circle fit). Prefer rimPoints when both
   *  could apply — see toWireRunSiteInput / marksSignatureFor. */
  readonly rimMark?: Vec3;
  /** Multiple points clicked around the cap's visible border/rim to find its width — the backend
   *  fits a circle through them (>=3 points) for a centre+radius robust to any single imprecise
   *  click. Replaces the legacy single rimMark for new doctor input; capped at 12 points
   *  server-side. A finished rim-marking session REPLACES this array wholesale (never appends
   *  across sessions), matching how centerMark/rimMark are replaced on every re-placement. */
  readonly rimPoints?: readonly Vec3[];
}

/** Server-side cap on rim_points per site (mirrors MAX_MARKED_POINTS for the brush patch). */
export const MAX_RIM_POINTS = 12;

/** The doctor-facing nudge threshold: fewer than this many rim points still submits fine (a
 *  single point behaves like the legacy rim mark, mathematically), but the circle fit that gives
 *  a robust centre+radius needs at least 3 — the UI nudges (not blocks) below that. */
export const RECOMMENDED_MIN_RIM_POINTS = 3;

/** Whether a site's rimPoints collection has reached the recommended minimum for a robust circle
 *  fit — drives the chip's amber-tint nudge (UI-only; the backend accepts fewer, see
 *  RECOMMENDED_MIN_RIM_POINTS). */
export function hasEnoughRimPoints(rimPoints: readonly Vec3[] | undefined): boolean {
  return (rimPoints?.length ?? 0) >= RECOMMENDED_MIN_RIM_POINTS;
}

/** Where the alignment seed for a site came from: the operator's brush stroke, a precise
 *  center+rim mark pair, or a plain click/proposal. */
export type SeedSource = "brush" | "marks" | "click";

/** How the cap was seated: closed-form rim geometry, or an ICP fallback when the rim was only partially visible. */
export type SeatMethod = "rim" | "icp";

/** The advisory gate's verdict for a site: never a silent auto-pass, but a graded signal for how much scrutiny it needs. */
export type GuidanceLevel = "ready" | "attention" | "action-needed";

/** One verdict + concrete operator-facing actions for a site — the centerpiece of the advisory gate UI. */
export interface Guidance {
  readonly level: GuidanceLevel;
  readonly actions: readonly string[];
}

/** One candidate size variant considered for a rim-seated site, with how well it seated. */
export interface VariantCandidate {
  readonly variant: string;
  readonly seatResidualMm: number;
}

export interface VariantAssessment {
  readonly identified: string;
  readonly declared: string | null;
  readonly measuredRimDiameterMm: number | null;  // null when the rim could not be measured
  // null when no margin was measured: the classifier refused (rim between two size
  // classes — see `flags`), or the library holds one diameter class and there is no
  // rival to measure against. Not zero: zero would mean two classes are indistinguishable.
  readonly diameterClassMarginMm: number | null;
  readonly flags: readonly string[];
  /**
   * Every candidate size variant considered, sorted best-first by seat residual — rim-seated
   * sites only (null for ICP-seated sites or legacy cached results predating this field).
   */
  readonly candidates: readonly VariantCandidate[] | null;
}

export interface SiteMeasurement {
  readonly mdSpanMm: number | null;  // null on terminal sites (one neighbour)
  readonly gapMesialMm: number;
  readonly gapDistalMm: number;
  readonly classification: string;
  readonly terminalSite: boolean;
}

export interface ProductionInfo {
  readonly screwChannelRadiusMm: number;
}

/**
 * Registration-error stats over the aligned surface — RealGUIDE's "Registration Error:
 * Average/Max". max includes screw-recess points where the template's bore has no surface.
 */
export interface FitStats {
  readonly avgMm: number;
  readonly maxMm: number;
}

export interface RunSiteResult {
  readonly tooth: number;
  readonly spec: string;
  readonly vendor: string;
  /** Retained (still on the wire) but no longer displayed — see rimAgreementMm. */
  readonly coverage: number;
  readonly alignmentErrorMm: number;
  readonly advisory: string;
  readonly variant: VariantAssessment;
  readonly siteMeasurement: SiteMeasurement;
  readonly production: ProductionInfo;
  readonly seedSource: SeedSource;
  /**
   * Distance (mm) between the human-marked site (brush patch centroid, or click center) and
   * the automation's nearest independently-proposed site — the human-vs-machine comparison.
   * Reference point is the human site, not a specific aligned pose; null if unavailable.
   */
  readonly autoDeltaMm: number | null;
  /** Absent only for legacy cached run results computed before this field existed. */
  readonly fit: FitStats | null;
  /** Absent only for legacy cached run results computed before this field existed. */
  readonly seatMethod: SeatMethod | null;
  /** Absent only for legacy cached run results computed before this field existed. */
  readonly guidance: Guidance | null;
  /**
   * The doctor-facing seat number: p90 distance (mm) from the scan's visible rim ring to the
   * seated template. Replaces Coverage in the UI — coverage counts surrounding gingiva the cap
   * can never explain and structurally can't reach 100% on a partially visible cap, which reads
   * as "bad alignment" when the seat is actually excellent (e.g. under ~1.0mm is a tight seat).
   * null when not computable (non-cap libraries, or too sparse a visible rim ring to fit) —
   * also null on legacy cached run results computed before this field existed.
   */
  readonly rimAgreementMm: number | null;
  /**
   * Max leave-one-out plane distance (mm) over the doctor's rim-border clicks (needs >= 4
   * clicks; null below that or on legacy cached runs). The Copy-run-report loop's answer to
   * "why did this seat tilt": ~0.3 is ordinary click noise, ~0.9 means one click landed past
   * the rim edge on the slope and tilted the fitted circle (guidance names it too).
   */
  readonly borderClickDisagreementMm: number | null;
  /**
   * Mean distance (mm) of the posed part's TOP FACE to the scan — the DEPTH read-out. The rim
   * band and tilt are geometrically blind to a slide along a straight-walled part's own axis;
   * this is the number that sees it (healthy seats read ~0.2-0.6; the measured ride-high
   * failures read 1.96/2.45). null when not computable or on legacy cached runs.
   */
  readonly topFaceAgreementMm: number | null;
  /**
   * Per-site pose-stability confidence: how much the seat moves when the doctor's marks are
   * re-clicked within click-noise, graded together with the fit residuals so a stably-wrong
   * seat is not read as confident. null when not computed (opt-in on the server) or on legacy
   * runs. Advisory — grades the operator's review effort, never auto-manufactures.
   */
  readonly confidence: {
    readonly grade: "high" | "medium" | "low";
    readonly posSpreadMm: number;
    readonly axisSpreadDeg: number;
  } | null;
  /**
   * The second honest alignment number, shown alongside rimAgreementMm: % (0-100) of the CAP'S
   * OWN footprint surface explained by the seated part (within 0.35mm) — measured over the
   * part's own footprint only, unlike the old coverage which counted surrounding gum the cap can
   * never explain. null when not computable, or on legacy cached run results computed before
   * this field existed.
   */
  readonly capSurfaceExplainedPct: number | null;
  /**
   * Coded-cutout clock instrument (rim seats only): the rotational residual against the cap's
   * coded features — the number a lab tech's eye judges — plus which instrument anchored the
   * shipped rotation and whether it could be verified. null on icp seats and legacy cached runs.
   */
  readonly clocking: Clocking | null;
  /** Operator rotation-nudge audit for this row (running total), null until a nudge is applied. */
  readonly nudge: NudgeState | null;
  /**
   * The acceptance-numbers catalog judged against this row (the doctor verification panel's
   * data): each industry verification number with OUR measured value, the cited industry
   * reference, and a pass/review/fail/missing band. Derived server-side on every response;
   * null only on payloads from a backend predating the panel.
   */
  readonly acceptance: Acceptance | null;
  /**
   * The doctor's recorded manual sign-off for this site — a recorded human judgment layered
   * on top of the pipeline's output (it never changes a pose or a gate), persisted in
   * run.json so it survives reloads. null until the doctor confirms or retracts.
   */
  readonly doctorConfirmation: DoctorConfirmation | null;
  /**
   * What this site's emitted construction part ACHIEVED against the requested gingival relief
   * (see GingivalOffsetReading). null on backends predating the measurement — the UI then says
   * "not measured on this run" rather than implying the request was met.
   */
  readonly gingivalOffset: GingivalOffsetReading | null;
}

/** Band verdict for one acceptance metric. "missing" is an honest "not measured here" —
 *  the backend reports absent values as missing, never as silent passes. */
export type AcceptanceBand = "pass" | "review" | "fail" | "missing";

/** Which column of the verification panel a metric belongs to: the doctor-facing
 *  verification set, or the lab/QC-facing checks. */
export type AcceptanceAudience = "doctor" | "lab";

/** The industry reference number a doctor can hold ours against, with its citation. */
export interface IndustryRef {
  readonly value: string;
  readonly source: string;
}

/** One verification number: the plain-language check, our measured value (preformatted in
 *  `display`), the industry reference, and the band verdict. `bands` carries the
 *  pass/review thresholds for banded metrics (null for custom-verdict metrics). */
export interface AcceptanceMetric {
  readonly key: string;
  readonly label: string;
  readonly unit: string;
  readonly audience: AcceptanceAudience;
  readonly industryRef: IndustryRef;
  readonly bands: { readonly passMax: number; readonly reviewMax: number } | null;
  readonly note: string | null;
  readonly value: number | string | null;
  readonly display: string | null;
  readonly band: AcceptanceBand;
}

/** Row 16 of the catalog — operator click precision: explanatory copy, never a chip. */
export interface AcceptanceContext {
  readonly label: string;
  readonly text: string;
  readonly industryRef: IndustryRef;
}

export interface Acceptance {
  readonly metrics: readonly AcceptanceMetric[];
  readonly overall: {
    readonly band: AcceptanceBand;
    readonly missing: readonly string[];
  };
  readonly context: AcceptanceContext;
}

/** The doctor's persisted sign-off record: confirmed/retracted, their own words, when. */
export interface DoctorConfirmation {
  readonly confirmed: boolean;
  readonly note: string | null;
  readonly ts: string;
}

/** The confirm-alignment endpoint's response: the persisted record plus the acceptance
 *  overall band at sign-off time (provenance read-out only — never a computation input). */
export interface ConfirmAlignmentResult {
  readonly tooth: number;
  readonly confirmation: DoctorConfirmation;
  readonly acceptanceOverall: AcceptanceBand;
}

/** The two QC images the verification panel shows inline for a site, when the package
 *  emitted them: the clock view (rotation evidence) and the signed deviation map (the
 *  industry's "color picture"). Pure lookup against the run's package file list. */
export function qcImagesFor(
  caseId: string,
  tooth: number,
  packageFiles: readonly string[],
): { readonly name: string; readonly label: string }[] {
  const candidates = [
    { name: `${caseId}-${tooth}-clockview.png`, label: "Clock view (rotation evidence)" },
    { name: `${caseId}-${tooth}-deviation.png`, label: "Deviation map (±0.5 mm convention)" },
  ];
  return candidates.filter((c) => packageFiles.includes(c.name));
}

/** The coded-cutout clock reading on a run row — see WireClocking for field semantics. */
export interface Clocking {
  readonly notchShiftDeg: number | null;
  readonly notchCorr: number;
  readonly notchProminence: number;
  readonly evidence: string;
  readonly consistencyDeg: number | null;
  readonly rotationUnverified: boolean;
}

/** The operator's running rotation total on a site (audit — mirrored in implant.json). */
export interface NudgeState {
  readonly cumulativeDeg: number;
}

/** One operator rotation request: a signed step in degrees, or a reset to the certified pose. */
export type NudgeRequest = { readonly kind: "step"; readonly deltaDeg: number } | { readonly kind: "reset" };

/** The nudge endpoint's response: applied step, audit total, and the coded-cutout residual
 *  RE-READ at the nudged pose (so the operator sees the codes agree: "-1.8° — aligned"). */
export interface NudgeResult {
  readonly tooth: number;
  readonly appliedDeltaDeg: number;
  readonly cumulativeDeg: number;
  readonly stabilityExcessMm: number | null;
  readonly clocking: Clocking;
  readonly nudge: NudgeState;
}

/** The align-to-mark endpoint's response: the nudge response plus the click/feature
 *  geometry (which template code feature was matched, and where the operator's click
 *  read on the clock) — the rotation was judged by the same gates as a nudge. */
export interface AlignToMarkResult extends NudgeResult {
  readonly matchedFeatureAzimuthDeg: number;
  readonly clickAzimuthDeg: number;
}

/** The client's register/best-fit MATCHING DIAMETER default (their own value, 2026-07-25): the
 *  distance within which scan surface is considered to belong to the part during the fit. */
export const BEST_FIT_DEFAULT_DIAMETER_MM = 0.3;
/** Bounds for the slider. Below ~0.05mm nothing matches at scanner resolution; past 2mm the fit
 *  starts pulling in neighbouring gingiva, which is exactly the seat error it should be fixing. */
export const BEST_FIT_MIN_DIAMETER_MM = 0.05;
export const BEST_FIT_MAX_DIAMETER_MM = 2.0;
export const BEST_FIT_DIAMETER_STEP_MM = 0.05;

/** One manual best-fit request: their matching diameter, and their Apply-Best-Fit toggle
 *  (`apply: false` measures the fit without moving the seated part). */
export interface BestFitRequest {
  readonly matchingDiameterMm: number;
  readonly apply: boolean;
}

/**
 * The best-fit endpoint's response. Only `tooth`/`matchingDiameterMm`/`applied` are guaranteed;
 * the rest is what the backend could measure (null where it could not), so the panel reports
 * what it actually has rather than printing zeros for numbers nobody computed.
 */
export interface BestFitResult {
  readonly tooth: number;
  readonly matchingDiameterMm: number;
  readonly applied: boolean;
  readonly nMatched: number | null;
  readonly rmsMm: number | null;
  readonly maxMm: number | null;
  readonly translationMm: number | null;
  readonly rotationDeg: number | null;
  /** The row's re-read numbers after applying — folded into the results table when present. */
  readonly fit: FitStats | null;
  readonly rimAgreementMm: number | null;
  readonly clocking: Clocking | null;
  readonly nudge: NudgeState | null;
}

/**
 * OFFSET HONESTY (measured 2026-07-25): what the emitted part achieved against the REQUESTED
 * gingival relief. Requesting 0.20 mm achieves ~0.13-0.15 mm median through the SDF round trip;
 * the request is reported as asked and the achievement as measured — never reconciled by
 * quietly rescaling one of them. null fields mean "not measured on this run".
 */
export interface GingivalOffsetReading {
  readonly requestedMm: number;
  readonly achievedMedianMm: number | null;
  readonly achievedMinMm: number | null;
  readonly achievedMaxMm: number | null;
  readonly method: string | null;
  /**
   * THE CLAMP (2026-07-25): what the run actually BUILT AT when the requested relief was more
   * than this part could take without collapsing the screw-channel wall. Three numbers now, all
   * distinct and all honest — requested (typed), applied (clamped), achieved (measured). null
   * `appliedMm` means the backend did not report one; it is never defaulted to the request.
   * See domain/reliefClamp for the read-out.
   */
  readonly appliedMm: number | null;
  readonly clamped: boolean;
  /** The ceiling that forced the clamp (mm), and the wall rule it protects. */
  readonly limitMm: number | null;
  readonly minWallMm: number | null;
  /** The backend's own sentence for why it clamped, shown verbatim. */
  readonly clampReason: string | null;
}

/** The pipeline's own adoption threshold (auto_flow rotates when |shift| > 6°) — under it the
 *  codes and the pose agree to within the instrument's working tolerance. */
export const NOTCH_ALIGNED_TOLERANCE_DEG = 6;

/**
 * Whether a site's rotation deserves the operator's eye up front — the review-gate cue that
 * auto-expands the rotation control (it stays available on demand for every rim seat):
 * the shipped rotation is unverified, no instrument read at all, or the two instruments
 * disagree by more than 20° (on a rigid part they cannot both be right).
 */
export function rotationNeedsReview(clocking: Clocking | null): boolean {
  if (clocking === null) return false;
  if (clocking.rotationUnverified) return true;
  if (clocking.evidence === "none") return true;
  if (clocking.consistencyDeg !== null && clocking.consistencyDeg > 20) return true;
  return false;
}

/**
 * The operator-facing residual line under the rotation control: the signed coded-cutout
 * residual with a verdict at the pipeline's own tolerance ("-1.8° — aligned"), or an honest
 * "no code signal" when the instrument read nothing at this pose.
 */
export function describeNotchResidual(clocking: Clocking | null): string {
  if (clocking === null || clocking.notchShiftDeg === null) return "no code signal";
  const v = clocking.notchShiftDeg;
  const signed = `${v > 0 ? "+" : ""}${v.toFixed(1)}°`;
  return Math.abs(v) <= NOTCH_ALIGNED_TOLERANCE_DEG ? `${signed} — aligned` : `${signed} — codes disagree`;
}

/**
 * The operator-facing outcome line after an applied align-to-mark: what rotation the
 * server applied to land the code feature on their mark, and what the coded-cutout
 * instrument reads at the new pose (re-read server-side — "codes now read −1.4°", or an
 * honest "no code signal" on the weak-evidence sites this tool backstops).
 */
export function describeAlignToMark(result: AlignToMarkResult): string {
  const d = result.appliedDeltaDeg;
  const rotated = `rotated ${d > 0 ? "+" : ""}${d.toFixed(1)}° — code feature on your mark`;
  const shift = result.clocking.notchShiftDeg;
  if (shift === null) return `${rotated}; no code signal at this pose`;
  return `${rotated}; codes now read ${shift > 0 ? "+" : ""}${shift.toFixed(1)}°`;
}

/**
 * The operator-facing outcome line after a manual best fit. States, in this order: whether the
 * part actually MOVED (the Apply toggle), how much surface the fit had to work with at the
 * chosen matching diameter, the residual it reached, and how far it moved the seat. Every
 * clause is dropped when its number was not measured — a fit that reports nothing says
 * "no numbers reported" rather than printing zeros nobody computed.
 */
export function describeBestFit(result: BestFitResult): string {
  const head = result.applied
    ? `best fit applied at Ø${result.matchingDiameterMm.toFixed(2)} mm matching`
    : `best fit MEASURED ONLY at Ø${result.matchingDiameterMm.toFixed(2)} mm matching (the seat was not moved)`;
  const parts: string[] = [];
  if (result.nMatched !== null) parts.push(`${result.nMatched.toLocaleString()} points matched`);
  if (result.rmsMm !== null) parts.push(`RMS ${result.rmsMm.toFixed(3)} mm`);
  if (result.translationMm !== null || result.rotationDeg !== null) {
    const moved = [
      result.translationMm !== null ? `${result.translationMm.toFixed(3)} mm` : null,
      result.rotationDeg !== null ? `${result.rotationDeg.toFixed(2)}°` : null,
    ].filter((v): v is string => v !== null);
    parts.push(`${result.applied ? "moved" : "would move"} ${moved.join(" / ")}`);
  }
  return parts.length > 0 ? `${head} — ${parts.join(", ")}` : `${head} — no numbers reported`;
}

/** One entry in the model's healing-cap library: a variant the doctor can explicitly choose. */
export interface LibraryVariant {
  readonly variant: string;
  readonly rimDiameterMm: number | null;
  readonly heightMm: number | null;
  readonly meshUrl: string;
}

/**
 * One entry of the FULL cross-model part catalog (the library BROWSER — case-independent,
 * unlike LibraryVariant's per-case step-2 picker). `id` is unique within its model group;
 * `flags`/`duplicateOf` carry the server's honest classification (superseded / legacy /
 * unloadable / duplicate-with-named-counterpart "model/id").
 */
export interface LibraryCatalogEntry {
  readonly id: string;
  readonly variant: string;
  readonly label: string;
  readonly rimDiameterMm: number | null;
  readonly heightMm: number | null;
  readonly filename: string;
  readonly sha256: string;
  readonly flags: readonly string[];
  readonly duplicateOf: readonly string[];
  readonly meshUrl: string;
}

/** One system tab of the library browser: a model dir under library/caps, or a legacy dir. */
export interface LibraryCatalogGroup {
  readonly model: string;
  readonly legacy: boolean;
  readonly variants: readonly LibraryCatalogEntry[];
}

export interface RunSummary {
  readonly sites: readonly RunSiteResult[];
  readonly packageFiles: readonly string[];
}

/** What the backend says this run was authorized with — echoed from the request, plus the
 *  vendor it derived from the chosen construction. null on payloads from a backend predating
 *  the decoding selection. */
export interface RunSelection {
  readonly model: string;
  readonly constructionPathId: string;
  readonly vendor: string;
  readonly jaw: Jaw;
  readonly gingivalOffsetMm: number;
  /** tooth -> the cap variant declared for it (null where the site declared none). */
  readonly variantByTooth: ReadonlyMap<number, string | null>;
}

export interface RunResult {
  readonly summary: RunSummary;
  readonly filesBase: string;
  readonly durationS: number;
  readonly cached: boolean;
  readonly selection: RunSelection | null;
}

/**
 * The per-site deviation read behind the three-panel verify's UNION overlay: the seated library
 * cap as a renderable mesh in the JAW WORLD FRAME (it overlays the scan with no client-side
 * transform) plus one signed millimetre per point. REPORTING ONLY — the same instrument the
 * acceptance difference map uses. `deviationMm[i]` is null where the read is not finite (no scan
 * surface under that vertex), which the colouring shows as "not measured" rather than as zero.
 */
export interface SiteDeviation {
  readonly caseId: string;
  readonly tooth: number;
  readonly implantModel: string | null;
  readonly variant: string | null;
  readonly frame: string;
  readonly nPoints: number;
  readonly points: Float32Array;
  readonly faces: Uint32Array;
  readonly deviationMm: readonly (number | null)[];
  readonly scale: DeviationScale;
  readonly stats: DeviationStats;
  /** How much of the COLOURED mesh falls in the inspection band — a coverage read-out for the
   *  panel, never a second acceptance number (see stats, which are the published ones). */
  readonly vertexFootprintPoints: number;
  /**
   * TRUE when this colouring came from the PRE-RUN preview seat rather than from a shipped
   * package (client, 2026-07-26: "verify must work on the first pass"). The alignment pass, the
   * instrument and the scale are identical — what differs is that nothing was emitted — so the
   * union pane says which one it is looking at instead of letting the two read alike.
   */
  readonly preview: boolean;
  /** The two numbers the results table would print for this seat, when the read carried them
   *  (the preview does; the shipped read leaves them null — the row already carries them). */
  readonly seat: DeviationSeat | null;
  /**
   * THE SEATED CAP'S OWN FRAME, straight off the pose the run shipped (2026-07-26). `axis` points
   * out of the cap's top face; `xAxis` is the frame's reference direction, which gives the panes a
   * SHARED up-vector so a coded cutout appears at the same clock angle in every one of them.
   *
   * null on a payload from a server predating the field — the pane then falls back to the jaw's
   * occlusal direction, which is honest but measured 6.2°-42.0° off the true axis on this fleet.
   */
  readonly pose: DeviationPose | null;
}

/** The seated pose's frame, as the viewer needs it. Exact by construction — this is the pose the
 *  run emitted, not an estimate of it (a client-side axis fit was tried and refused: it read
 *  26.9° and 48.3° off on two of the twelve catalog parts). */
export interface DeviationPose {
  readonly axis: Vec3;
  readonly xAxis: Vec3;
  readonly origin: Vec3;
}

/** The preview's own seat read-out: how it seated and how tight, from the same row Process
 *  would produce — so a pre-run preview is comparable to the run that follows it. */
export interface DeviationSeat {
  readonly seatMethod: SeatMethod | null;
  readonly rimAgreementMm: number | null;
  readonly fit: FitStats | null;
}

export interface DeviationScale {
  readonly clampMm: number;
  readonly minMm: number;
  readonly maxMm: number;
  readonly colormap: string;
  readonly signConvention: string;
  /** What this site's data actually spans, so the UI can say "clamped" honestly. */
  readonly dataMinMm: number | null;
  readonly dataMaxMm: number | null;
  readonly footprintBandMm: number;
}

/** The site's PUBLISHED acceptance numbers (area-uniform surface samples — the difference map's
 *  own), carried alongside the mesh so the panel never prints a second, vertex-weighted RMS. */
export interface DeviationStats {
  readonly rmsMm: number | null;
  readonly p90Mm: number | null;
  readonly nFootprint: number;
  readonly nSamples: number;
  readonly source: string;
}

/**
 * A seated implant's pose, as extracted from the per-tooth package deliverable
 * "<case>-<tooth>-implant.json" — used ONLY to draw the post-run RealGUIDE-style axis triad
 * (position + the pose matrix's three rotation-column directions). Framework-agnostic (no
 * three.js here — see sceneController's PoseTriadSpec, which App.tsx maps this into).
 */
export interface ImplantPose {
  readonly tooth: number;
  readonly position: Vec3;
  readonly axisX: Vec3;
  readonly axisY: Vec3;
  readonly axisZ: Vec3;
}

/** True when the identified variant agrees with what the doctor declared, with no safety flags. */
export function variantAgrees(v: VariantAssessment): boolean {
  if (v.flags.length > 0) return false;
  if (v.declared === null) return false;
  return v.declared.trim().toLowerCase() === v.identified.trim().toLowerCase();
}

/**
 * The picker-aware, tri-state read of a site's Agreement column:
 * - "no-declaration": the doctor left it on auto — nothing to agree/disagree with yet.
 * - "disputed": a flag calls out a mismatch between the declared and measured variant.
 * - "confirmed": a declaration was made and the independent measurement did not dispute it.
 */
export type AgreementState =
  | { readonly kind: "no-declaration" }
  | { readonly kind: "disputed"; readonly flag: string }
  | { readonly kind: "confirmed" };

/** Find the flag (if any) that specifically disputes the doctor's declared variant. */
function findDeclarationDisputeFlag(flags: readonly string[]): string | undefined {
  return flags.find((f) => f.toLowerCase().includes("declared"));
}

/** Derive the tri-state agreement read for a site's variant assessment (see AgreementState). */
export function agreementState(v: VariantAssessment): AgreementState {
  if (v.declared === null) return { kind: "no-declaration" };
  const disputeFlag = findDeclarationDisputeFlag(v.flags);
  if (disputeFlag !== undefined) return { kind: "disputed", flag: disputeFlag };
  return { kind: "confirmed" };
}

/**
 * Tooth numbers that appear on more than one site, sorted ascending — the server 422s on
 * duplicate tooth numbers ("each site needs its own tooth"), so this drives client-side
 * validation to catch it before submission rather than round-tripping the 422.
 */
export function findDuplicateTeeth(sites: readonly { readonly tooth: number }[]): number[] {
  const seen = new Set<number>();
  const duplicates = new Set<number>();
  for (const site of sites) {
    if (seen.has(site.tooth)) {
      duplicates.add(site.tooth);
    } else {
      seen.add(site.tooth);
    }
  }
  return [...duplicates].sort((a, b) => a - b);
}

/** A site has a real declared cap variant when the picker is off "auto" (empty/undefined). */
export function siteIsDeclared(site: { readonly declaredVariant?: string | null }): boolean {
  return site.declaredVariant != null && site.declaredVariant.trim() !== "";
}

/**
 * 1-based row numbers of sites still left on "auto" — the ones missing a declared variant.
 * Declaration is a REQUIRED intake field (measured 2026-07-15: auto-identification is only
 * 1/4 correct on the labeled arches and flips diameter classes, whereas the doctor's
 * declaration drives a 4/4-correct alignment). Empty array = every site declared, safe to run.
 */
export function undeclaredSiteNumbers(
  sites: readonly { readonly declaredVariant?: string | null }[],
): number[] {
  const out: number[] = [];
  sites.forEach((site, i) => {
    if (!siteIsDeclared(site)) out.push(i + 1);
  });
  return out;
}

/**
 * The centre+rim marks are ONE measurement, not two independent points: the centre locates the
 * cap and |rim - centre| is the doctor's measured rim radius. Re-placing ONLY the centre while
 * leaving a stale rim in place would pair a fresh centre with a radius measured from the OLD
 * centre — the click error bakes into the derived radius and the seat degrades (measured on real
 * cases: 40-59 degree tilts, 2-4mm slides, identified-variant class flips). So re-placing the
 * centre must carry the rim along with it: translate the rim by the same delta the centre moved,
 * preserving the measured radius/orientation exactly. Only meaningful when BOTH marks already
 * exist — with no prior rim there is nothing to preserve, so callers should pass rimMark through
 * unchanged (see App.tsx's handleStartMark, which only calls this when oldRim is present).
 *
 * Applies ONLY to the legacy single rimMark. rimPoints are independent, scan-anchored border
 * locations (not derived relative to the centre) — re-placing the centre must NOT move them; skip
 * this translation entirely when a row has rimPoints (see App.tsx's handleStartMark).
 */
export function translateMark(oldRim: Vec3, oldCenter: Vec3, newCenter: Vec3): Vec3 {
  return [
    oldRim[0] + (newCenter[0] - oldCenter[0]),
    oldRim[1] + (newCenter[1] - oldCenter[1]),
    oldRim[2] + (newCenter[2] - oldCenter[2]),
  ];
}

/**
 * A pure fingerprint of just the mark/patch fields (centerMark, rimMark, rimPoints,
 * markedPoints) across all sites — tooth-number or declared-variant edits intentionally do not
 * change this, since those aren't "marks changed". Two calls with equivalent mark data
 * (regardless of object identity) produce the same string, so callers can detect "marks are
 * unchanged since X" by comparing a stored signature rather than relying on a one-shot "skip the
 * next fire" flag.
 */
export function marksSignatureFor(sites: readonly ConfirmedSite[]): string {
  return sites
    .map((s) =>
      JSON.stringify([s.centerMark ?? null, s.rimMark ?? null, s.rimPoints ?? null, s.markedPoints ?? null]),
    )
    .join("|");
}

/**
 * Whether an existing run result is STALE relative to the marks currently on screen: the doctor
 * edited a mark/patch (centre, rim, rim points, or brush patch) after the last run consumed
 * `ranSignature`, and no recompute has happened since. Compares two marksSignatureFor() outputs
 * — never re-derives them itself, so it stays agnostic to what "marks changed" means (that rule
 * lives in marksSignatureFor alone). `ranSignature` is null when no run has happened yet (or the
 * ref was reset, e.g. on a case switch) — nothing to be stale relative to, so that's never stale.
 *
 * Replaces the old debounced-auto-recompute design: rather than firing a fresh run ~800ms after
 * EVERY individual edit (centre placed -> run, rim finished -> another run, doctor sees
 * half-marked intermediate results and wastes runs), this only DETECTS drift; the caller decides
 * when to act on it (an explicit "Recompute alignment" button, or Confirm All) — see App.tsx.
 */
export function isRunStale(currentSignature: string, ranSignature: string | null): boolean {
  if (ranSignature === null) return false;
  return currentSignature !== ranSignature;
}

/**
 * "HH:MM:SS · N.Ns" display for the Process heading's last-run line — the timestamp is the
 * CLIENT's clock at the moment the run response landed (the backend doesn't send one; when the
 * doctor's own screen received it is what matters for "when did I run this"), the duration is
 * the run's own reported durationS. Pure formatting only — callers own capturing `at`.
 */
export function formatRunTimestamp(at: Date, durationS: number): string {
  const time = at.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  return `${time} · ${durationS.toFixed(1)}s`;
}

/** Rounds a Vec3's components to 0.1 for the "Copy run report" inputs summary — full backend
 *  precision is noise for a human-readable report; the client-side click precision itself is
 *  nowhere near 0.1mm anyway. Pure numeric helper. */
function roundVec3(v: Vec3): Vec3 {
  const round1 = (n: number) => Math.round(n * 10) / 10;
  return [round1(v[0]), round1(v[1]), round1(v[2])];
}

function formatVec3(v: Vec3): string {
  const [x, y, z] = roundVec3(v);
  return `(${x}, ${y}, ${z})`;
}

/**
 * A compact MARKDOWN run report for pasting into chat/ticket systems (Item 4's "feedback loop
 * into chat") — case id, when the run landed, then per-site: seed/seat/Δauto/fit/rim-seat/cap-
 * surface%, the identified variant with its FULL candidates list (scores), measured Ø, declared,
 * gate level + every guidance action text, and the INPUTS summary the doctor actually gave
 * (centre mark, rim-points count + coords, brush point count) rounded to 0.1mm for readability.
 *
 * `sites` (ConfirmedSite, the doctor's inputs) and `runSites` (RunSiteResult, the backend's
 * outputs) are matched by TOOTH NUMBER — the only key both share. A tooth present in one but not
 * the other (e.g. the doctor added a row after the run that produced runSites) still gets a
 * section, with the missing half read as "no run data yet" / "no input data" rather than being
 * silently dropped — a report that quietly omits a site is worse than one that flags a mismatch.
 *
 * Pure and framework-free: no clipboard access here — see App.tsx's handleCopyRunReport for that.
 */
export function buildRunReport(caseId: string, sites: readonly ConfirmedSite[], runSites: readonly RunSiteResult[]): string {
  const runByTooth = new Map(runSites.map((r) => [r.tooth, r] as const));
  const siteByTooth = new Map(sites.map((s) => [s.tooth, s] as const));
  const allTeeth = [...new Set([...runByTooth.keys(), ...siteByTooth.keys()])].sort((a, b) => a - b);

  const lines: string[] = [];
  lines.push(`# Run report — ${caseId}`);
  lines.push("");

  for (const tooth of allTeeth) {
    const r = runByTooth.get(tooth);
    const s = siteByTooth.get(tooth);
    lines.push(`## Tooth ${tooth}`);

    if (r) {
      lines.push(`- Seed: ${r.seedSource}`);
      lines.push(`- Seat: ${r.seatMethod ?? "—"}`);
      lines.push(`- Δ auto: ${r.autoDeltaMm !== null ? `${r.autoDeltaMm.toFixed(2)}mm` : "—"}`);
      lines.push(`- Fit avg/max: ${r.fit ? `${r.fit.avgMm.toFixed(2)} / ${r.fit.maxMm.toFixed(2)}mm` : "—"}`);
      lines.push(`- Rim seat: ${r.rimAgreementMm !== null ? `${r.rimAgreementMm.toFixed(2)}mm` : "—"}`);
      if (r.borderClickDisagreementMm !== null) {
        lines.push(`- Border-click disagreement: ${r.borderClickDisagreementMm.toFixed(2)}mm`);
      }
      if (r.topFaceAgreementMm !== null) {
        lines.push(`- Top-face seat: ${r.topFaceAgreementMm.toFixed(2)}mm`);
      }
      if (r.confidence !== null) {
        lines.push(
          `- Confidence: ${r.confidence.grade} (pose stable to ${r.confidence.posSpreadMm.toFixed(2)}mm / ${r.confidence.axisSpreadDeg.toFixed(0)}° under click noise)`,
        );
      }
      lines.push(
        `- Cap surface explained: ${r.capSurfaceExplainedPct !== null ? `${r.capSurfaceExplainedPct.toFixed(0)}%` : "—"}`,
      );
      lines.push(`- Identified variant: ${r.variant.identified}`);
      if (r.variant.candidates && r.variant.candidates.length > 0) {
        const candidateText = r.variant.candidates.map((c) => `${c.variant} (${c.seatResidualMm.toFixed(3)})`).join(", ");
        lines.push(`- Candidates: ${candidateText}`);
      }
      lines.push(`- Measured Ø: ${r.variant.measuredRimDiameterMm !== null ? `${r.variant.measuredRimDiameterMm.toFixed(2)}mm` : "—"}`);
      lines.push(`- Declared: ${r.variant.declared ?? "auto"}`);
      lines.push(`- Gate: ${r.guidance ? r.guidance.level : "—"}`);
      if (r.guidance && r.guidance.actions.length > 0) {
        for (const action of r.guidance.actions) {
          lines.push(`  - ${action}`);
        }
      }
    } else {
      lines.push(`- (no run data yet for this tooth)`);
    }

    lines.push(`- Inputs:`);
    if (s) {
      lines.push(`  - Centre mark: ${s.centerMark ? formatVec3(s.centerMark) : "not set"}`);
      const rimPointsCount = s.rimPoints?.length ?? 0;
      if (rimPointsCount > 0) {
        const coordsText = (s.rimPoints ?? []).map(formatVec3).join(", ");
        lines.push(`  - Rim points (${rimPointsCount}): ${coordsText}`);
      } else if (s.rimMark) {
        lines.push(`  - Rim mark (legacy): ${formatVec3(s.rimMark)}`);
      } else {
        lines.push(`  - Rim points: not set`);
      }
      lines.push(`  - Brush points: ${s.markedPoints?.length ?? 0}`);
    } else {
      lines.push(`  - (no input data for this tooth)`);
    }

    lines.push("");
  }

  return lines.join("\n").trimEnd();
}

/**
 * Belt-and-braces cache-busting for package files under files_base: the server now sends
 * Cache-Control: no-store on /files responses, but an ALREADY-OPEN tab can still be holding a
 * browser-cached response from a genuinely-bad earlier run — the file name is identical across
 * runs even though the on-disk bytes get overwritten (that's the root cause of the "sideways
 * cap" report: fresh table metrics next to a stale mesh from a memory-cached fetch). Appending a
 * per-run version query param forces a new URL, and therefore a new fetch, every run.
 *
 * `version` is a per-run token (e.g. Date.now() when the run response lands) — null before any
 * run has happened yet, in which case the URL is returned unchanged (nothing to bust: there is
 * no prior run's cached response to collide with). Deliberately NOT applied to immutable assets
 * (the healing-cap library's meshUrl) — see the call sites in App.tsx for which URLs this wraps.
 */
export function withCacheBust(url: string, version: number | null): string {
  if (version === null) return url;
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}v=${version}`;
}

/** Backend cap on marked_points per site — the brush patch must be subsampled below this before submission. */
export const MAX_MARKED_POINTS = 400;

/** Evenly subsample a point list down to at most `max` points (every Nth point), preserving stroke order/shape. */
export function subsamplePoints(points: readonly Vec3[], max: number = MAX_MARKED_POINTS): Vec3[] {
  if (points.length <= max) return [...points];
  const step = points.length / max;
  const result: Vec3[] = [];
  for (let i = 0; i < max; i += 1) {
    const point = points[Math.floor(i * step)];
    if (point !== undefined) result.push(point);
  }
  return result;
}
