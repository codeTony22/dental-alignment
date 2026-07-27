/**
 * Wire-shape types: the literal JSON the backend returns (snake_case).
 * These exist only at the API boundary; the rest of the app uses domain types.
 */

export type WireVec3 = readonly [number, number, number];

export interface WireSuggestedSite {
  tooth: number;
  center: WireVec3;
  declared_variant: string | null;
  // Optional: absent for cases the model hasn't pre-marked; prefills the picker's marker chips.
  center_mark?: WireVec3 | null;
  rim_mark?: WireVec3 | null;
}

/**
 * One case as the NO-INFERENCE discovery serves it (client directive 2026-07-25: "the lab
 * chooses, the software never guesses"). Every scan folder holding an STL is listed — none is
 * withheld for failing to spell an implant model in its folder name. `suggested_model` /
 * `suggested_construction` / `jaw` are the old name match demoted to a non-binding DEFAULT the
 * UI may preselect: any of them may be null, and the run only uses one that the operator sent
 * back explicitly. `vendor` is likewise derived from the suggested construction (null without one).
 */
export interface WireCase {
  id: string;
  doctor: string;
  jaw: string;
  vendor: string | null;
  scan_url: string;
  /** The scan file the case was discovered from — shown so the operator can see WHICH upload this is. */
  scan_filename?: string;
  /** A DEFAULT implant system, name-matched from the folder; null when nothing matched. */
  suggested_model?: string | null;
  /** A DEFAULT construction `path_id` (see WireConstructionPart); null when nothing matched. */
  suggested_construction?: string | null;
  suggested_sites: WireSuggestedSite[];
}

/** One row of GET /api/constructions — every construction STL on disk, chosen by `path_id`
 *  ("<vendor>/<filename>"). Replaces the old "any vendor dir / <model>-scanbody.stl" name
 *  resolution, which silently dropped any case whose model did not spell a filename. */
export interface WireConstructionPart {
  vendor: string;
  filename: string;
  path_id: string;
  label: string;
}

/**
 * Capture gate (master plan §1 SCAN / §8 item 11) — the industry intake mechanism run
 * per site server-side. INTAKE ADVISORY in the demo: verdicts surface as chips/banner
 * before the operator invests marks; the fail-closed upload gate arrives with a real
 * upload flow. Three cited checks: rim-arc coverage (the reference lab workflow requires
 * the entire cap circumference), code-band visibility (codes must be clearly visible),
 * collar exposure (>=1mm supragingival). Overall verdict = the worst check.
 */
export type WireCaptureVerdict = "pass" | "marginal" | "rescan";

export interface WireCaptureCheck {
  name: string; // "rim_arc" | "code_band" | "collar_exposure"
  value: number | null; // null = unmeasurable (flagged marginal, never a silent pass)
  bound_pass: number;
  bound_rescan: number;
  verdict: WireCaptureVerdict;
  message: string;
}

export interface WireCaptureAssessment {
  verdict: WireCaptureVerdict;
  rim_z_mm: number | null;
  checks: WireCaptureCheck[];
}

/** A capture block for one of the case's curated suggested sites (propose payload). */
export interface WireSuggestedCapture {
  tooth: number | null;
  center: WireVec3 | null;
  capture: WireCaptureAssessment;
}

export interface WireProposal {
  center: WireVec3;
  void_ratio: number;
  rim_below_cusps_mm: number;
  // Optional: absent on payloads from a backend predating the capture gate.
  capture?: WireCaptureAssessment | null;
}

export interface WireProposeResult {
  proposals: WireProposal[];
  duration_s: number;
  cached: boolean;
  // Optional: absent on payloads from a backend predating the capture gate.
  suggested_capture?: WireSuggestedCapture[];
}

export interface WireRunSiteInput {
  tooth: number;
  center: WireVec3;
  declared_variant?: string;
  marked_points?: WireVec3[];
  // RealGUIDE-style registration points: center_mark = cap CENTER (locator only when rim_points
  // is present), rim_mark = a single point on the cap's WIDEST rim edge (legacy; still accepted,
  // still what curated prefills send). Together they hand the aligner center+radius directly.
  center_mark?: WireVec3;
  rim_mark?: WireVec3;
  // Multiple points clicked around the cap's visible border — the backend fits a circle through
  // them (>=3) for centre+radius robust to any single imprecise click. Capped at 12 server-side.
  // Sent instead of rim_mark for new doctor input; mutually exclusive in practice (see
  // toWireRunSiteInput), though the wire shape itself does not forbid both being present.
  rim_points?: WireVec3[];
}

/**
 * THE DECODING SELECTION on the run request (client directive 2026-07-25). `model` (the implant
 * system) and `construction_path` (a `path_id` from GET /api/constructions) are REQUIRED — the
 * backend refuses with one 422 sentence rather than falling back to the case's name-matched
 * suggestion, since that fallback IS the guess being removed. `jaw` overrides the suggestion read
 * off the scan filename; `gingival_offset_mm` is the tissue clearance the emitted construction is
 * relieved by (0.20 default, bounded 0-1.0 server-side). The per-site cap variant still travels as
 * each site's `declared_variant`.
 */
export interface WireRunRequest {
  sites: WireRunSiteInput[];
  fresh?: boolean;
  model: string;
  construction_path: string;
  jaw?: string;
  gingival_offset_mm?: number;
}

export interface WireVariantCandidate {
  variant: string;
  seat_residual_mm: number;
}

export interface WireVariantAssessment {
  identified: string;
  declared: string | null;
  measured_rim_diameter_mm: number | null;
  // null = NO MARGIN WAS MEASURED, from either of two causes the wire cannot tell apart:
  // the classifier REFUSED (the rim fell between two size classes — `flags` then carries
  // the ambiguity notice), or the library holds a SINGLE diameter class, which has no
  // rival class to measure a distance to. Never treat it as 0 — that reads as "two
  // classes are touching", the opposite of the one-class case.
  diameter_class_margin_mm: number | null;
  flags: string[];
  // Optional: absent on legacy cached run results computed before this field existed; null
  // for ICP-seated sites (candidates are only meaningful when a rim seat was found).
  candidates?: WireVariantCandidate[] | null;
}

export interface WireSiteMeasurement {
  md_span_mm: number | null;
  gap_mesial_mm: number;
  gap_distal_mm: number;
  classification: string;
  terminal_site: boolean;
}

export interface WireProduction {
  screw_channel_radius_mm: number;
  /**
   * THE CLAMP, AS THE WORKER ACTUALLY EMITS IT (verified against the live API 2026-07-25).
   * The worker stamps the relief decision onto the site's `production` block — NOT onto
   * `gingival_offset`, whose `requested_mm` is the value the part was CUT with (the applied
   * one). Reading the clamp only off `gingival_offset` made every real run look unclamped and
   * relabelled the applied number as the operator's request — the exact silent substitution
   * this feature exists to prevent. `mapGingivalOffset` folds both blocks together.
   */
  gingival_offset_requested_mm?: number | null;
  gingival_offset_applied_mm?: number | null;
  /** What the part was cut with (=== applied). Kept for readers that want one number. */
  gingival_offset_mm?: number | null;
  clamped?: boolean;
  /** "wall" | "channel" | "seal" | "none" — treated as opaque text, never switched on. */
  limited_by?: string | null;
  max_safe_mm?: number | null;
  clamp_reason?: string | null;
}

export interface WireFitStats {
  avg_mm: number;
  max_mm: number;
}

export interface WireGuidance {
  level: "ready" | "attention" | "action-needed";
  actions: string[];
}

export interface WireRunSiteResult {
  tooth: number;
  spec: string;
  vendor: string;
  // Retained on the wire (still sent by the backend) but no longer surfaced in the UI — it counts
  // surrounding gingiva the cap can never explain and structurally can't reach 100% on a
  // partially visible cap, which reads as "bad alignment" when it isn't. See rim_agreement_mm.
  coverage: number;
  alignment_error_mm: number;
  advisory: string;
  variant: WireVariantAssessment;
  site_measurement: WireSiteMeasurement;
  production: WireProduction;
  seed_source: "brush" | "marks" | "click";
  auto_delta_mm: number | null;
  fit: WireFitStats;
  // Optional: absent on legacy cached run results computed before this field existed.
  seat_method?: "rim" | "icp";
  guidance?: WireGuidance;
  // The honest doctor-facing seat number, replacing Coverage in the UI: p90 distance (mm) from
  // the scan's visible rim ring to the posed template. null when not computable (non-cap
  // libraries, or too sparse a visible ring to fit) — also absent on legacy cached results
  // computed before this field existed, which collapses to the same null via the mapper.
  rim_agreement_mm?: number | null;
  // Max leave-one-out plane distance over the doctor's rim-border clicks (n>=4) — the "why did
  // this seat tilt" reporting number (~0.3 is click noise, ~0.9 is one click past the rim edge).
  // null below 4 border clicks; absent on legacy cached results.
  border_click_disagreement_mm?: number | null;
  // Mean top-face->scan distance (mm) — the DEPTH read-out (band/tilt are blind to a slide
  // along a straight wall; healthy ~0.2-0.6, ride-high failures 1.96/2.45). null when not
  // computable; absent on legacy cached results.
  top_face_agreement_mm?: number | null;
  // Per-site pose-stability confidence (opt-in on the server): a graded read-out of how much
  // the seat wobbles under click noise, folded with the fit residuals. null/absent when not
  // computed (battery / legacy runs). Advisory only — does not drive auto-pass.
  confidence?: {
    grade: "high" | "medium" | "low";
    pose_pos_spread_mm: number;
    pose_axis_spread_deg: number;
  } | null;
  // The second honest alignment number, shown alongside rim_agreement_mm: % of the CAP'S OWN
  // footprint surface explained by the seated part (within 0.35mm), measured over the part's own
  // footprint only — unlike the old ROI coverage, this doesn't count surrounding gum. null when
  // not computable; also absent on legacy cached results computed before this field existed.
  cap_surface_explained_pct?: number | null;
  // Coded-cutout clock instrument (rim seats only): the rotational residual against the cap's
  // coded features, which instrument anchored the rotation, and the cross-instrument check.
  // null on icp seats; absent on legacy cached results.
  clocking?: WireClocking | null;
  // Present after an operator rotation nudge folded into the cached run row (see the
  // nudge-rotation endpoint) — the audit half of the row's clocking state.
  nudge?: WireNudge | null;
  // The acceptance-numbers catalog judged against this row (worker domain/acceptance.py) —
  // derived at serve time on every response; absent only on payloads from a backend
  // predating the verification panel.
  acceptance?: WireAcceptance | null;
  // The doctor's recorded manual sign-off (confirm-alignment endpoint) — persisted in
  // run.json, so it comes back with the run payload across reloads. Absent until the
  // doctor confirms (or retracts) this site's alignment.
  doctor_confirmation?: WireDoctorConfirmation | null;
  // What this site's emitted construction part ACTUALLY achieved against the requested
  // gingival relief (see WireGingivalOffsetReading). Absent on backends predating the
  // measurement — never inferred client-side.
  gingival_offset?: WireGingivalOffsetReading | null;
}

export type WireAcceptanceBand = "pass" | "review" | "fail" | "missing";

export interface WireIndustryRef {
  value: string;
  source: string;
}

/** One catalog metric judged against the site row: the spec fields (label in the doctor's
 *  language, unit, audience, cited industry reference, pass/review thresholds) plus the
 *  evaluated value/display/band. `band: "missing"` is an honest "not measured here" —
 *  the backend never silently passes an absent value. */
export interface WireAcceptanceMetric {
  key: string;
  label: string;
  unit: string;
  audience: string;
  industry_ref: WireIndustryRef;
  bands: { pass: number; review: number } | null;
  note: string | null;
  value: number | string | null;
  display: string | null;
  band: WireAcceptanceBand;
}

export interface WireAcceptance {
  metrics: WireAcceptanceMetric[];
  overall: {
    band: WireAcceptanceBand;
    counts: Record<string, number>;
    missing: string[];
  };
  // Row 16 of the catalog: operator click precision — explanatory copy, never a chip.
  context: {
    label: string;
    text: string;
    industry_ref: WireIndustryRef;
  };
}

/** The doctor's manual sign-off record on a site row — a recorded human judgment layered
 *  on top of the pipeline's output; it never changes a pose or a gate computation. */
export interface WireDoctorConfirmation {
  confirmed: boolean;
  note: string | null;
  ts: string;
}

/** POST /api/cases/{id}/sites/{tooth}/confirm-alignment response: the persisted record
 *  plus the acceptance overall band at sign-off time (provenance read-out only). */
export interface WireConfirmAlignmentResult {
  tooth: number;
  doctor_confirmation: WireDoctorConfirmation;
  acceptance_overall: WireAcceptanceBand;
}

export interface WireClocking {
  // Rotation (deg, CCW about the part's own axis) that would align the pose with the scanned
  // coded cutouts — the residual a lab tech's eye judges. null = no signal read.
  notch_shift_deg: number | null;
  notch_corr: number;
  notch_prominence: number;
  // Which instrument anchored the shipped rotation: "codes" | "codes+recess" | "recess" | "none".
  evidence?: string;
  // |codes - recess| disagreement (deg) when both instruments read — >20° routes attention.
  consistency_deg?: number | null;
  // True when neither instrument could verify the shipped rotation (or the confirm re-read
  // failed) — the review gate's cue to offer the operator nudge up front.
  rotation_unverified?: boolean;
}

/** The operator-nudge audit on a run row / nudge response: the last step and the running total. */
export interface WireNudge {
  operator_delta_deg: number;
  cumulative_deg: number;
}

/** POST /api/cases/{id}/sites/{tooth}/nudge-rotation response: the applied step, the audit
 *  total, the ring-fixed stability excess (null on reset — the certified pose needs no
 *  re-judging), and the coded-cutout residual RE-READ at the nudged pose. */
export interface WireNudgeResult {
  tooth: number;
  applied_delta_deg: number;
  cumulative_deg: number;
  stability_excess_mm: number | null;
  clocking: WireClocking;
  nudge: WireNudge;
  files: string[];
}

/** POST /api/cases/{id}/sites/{tooth}/align-to-mark response: the nudge response plus the
 *  click/feature geometry — which template code-feature azimuth was matched, and the
 *  operator's click azimuth about the measured rim centre (both deg, canonical frame). */
export interface WireAlignToMarkResult extends WireNudgeResult {
  matched_feature_azimuth_deg: number;
  click_azimuth_deg: number;
}

/**
 * One marked feature of a LIBRARY PART (GET/PUT/DELETE
 * /api/library/{model}/{variant}/features — client ask 2026-07-24). Canonical frame:
 * `azimuth_deg` is CCW about the part's own rim centre, `radius_mm` is the lever arm,
 * `z_mm` names the plane the feature is read in. `defines_rotation` is the server's
 * lever-arm verdict (radius >= 0.5mm) — a concentric bore names the axis, not a clock
 * angle, so it is listed and drawn but refused as a correspondence anchor.
 */
export interface WirePartFeature {
  id: string;
  kind: string;
  azimuth_deg: number;
  radius_mm: number;
  z_mm: number;
  source: string;
  defines_rotation: boolean;
}

/** The features payload. `auto_seeded` true = nothing is persisted for this part yet and
 *  these are the MACHINE's own reading (`revised_at` is then null). */
export interface WirePartAnnotation {
  model: string;
  variant: string;
  auto_seeded: boolean;
  revised_at: string | null;
  features: WirePartFeature[];
  // DELETE only: whether an operator annotation was actually there to drop.
  reverted?: boolean;
}

/** One feature as the PUT accepts it: EXACTLY ONE of `point` (a canonical-frame click on
 *  the part, which the server snaps onto its own reading when it lands close enough) or
 *  `azimuth_deg` (typed/untouched, placed at the coded band's mid-radius). */
export interface WirePartFeatureIn {
  kind: string;
  azimuth_deg?: number;
  point?: WireVec3;
}

export interface WirePartFeaturesRequest {
  features: WirePartFeatureIn[];
}

/** One pair of POST /api/cases/{id}/sites/{tooth}/align-to-correspondence: the PART half is
 *  EITHER the library feature by id OR `part_point` — a FREE canonical-frame click on the part
 *  itself (client ask 2026-07-26) — plus the world point on the SCAN where the operator sees
 *  it. Exactly one of the two part halves per pair (the server 422s otherwise). */
export interface WireCorrespondencePairIn {
  feature_id?: string;
  part_point?: WireVec3;
  scan_point: WireVec3;
}

export interface WireAlignToCorrespondenceRequest {
  pairs: WireCorrespondencePairIn[];
}

/** The server's per-pair report after the best fit: `residual_mm` is the arc the mark
 *  misses by AT THAT FEATURE'S OWN RADIUS — millimetres the operator can judge. */
export interface WireCorrespondenceResidual {
  feature_id: string;
  feature_azimuth_deg: number;
  click_azimuth_deg: number;
  delta_deg: number;
  residual_deg: number;
  residual_mm: number;
}

/** align-to-correspondence response: the nudge response (same gates, same re-emit, same
 *  audit) plus the per-pair residuals and their RMS. */
export interface WireAlignToCorrespondenceResult extends WireNudgeResult {
  pairs: WireCorrespondenceResidual[];
  residual_rms_mm: number;
}

/**
 * POST /api/cases/{id}/sites/{tooth}/best-fit — the client's register/best-fit "Best fit" with
 * their MATCHING DIAMETER (mm) and their Apply-Best-Fit toggle. Everything past
 * `tooth`/`matching_diameter_mm`/`applied` is optional on purpose: a measure-only run has no
 * re-emitted files, an ICP seat has no clocking, and the row's re-read fit stats are a
 * convenience the panel degrades gracefully without (it then just reports the match itself).
 */
export interface WireBestFitResult {
  tooth: number;
  matching_diameter_mm: number;
  /** False when the operator asked to MEASURE only — the seated pose was not touched. */
  applied: boolean;
  /** Scan points that fell inside the matching diameter of the part (the fit's own support). */
  n_matched?: number;
  rms_mm?: number | null;
  max_mm?: number | null;
  /** Magnitude of the pose correction the fit proposes/applied. */
  translation_mm?: number | null;
  rotation_deg?: number | null;
  /** The row's re-read numbers after applying, folded back into the results table. */
  fit?: WireFitStats | null;
  rim_agreement_mm?: number | null;
  clocking?: WireClocking | null;
  nudge?: WireNudge | null;
  files?: string[];
}

/**
 * THE OFFSET HONESTY BLOCK (measured 2026-07-25): requesting 0.20 mm of gingival relief achieves
 * ~0.13-0.15 mm median on the emitted part, because the SDF round trip (voxelize → offset →
 * re-mesh) closes part of the requested clearance. The request is NEVER silently rescaled to
 * match — the backend reports what it actually achieved and the UI shows both numbers side by
 * side. Absent on runs from a backend predating the measurement, which the UI reads as "not
 * measured on this run" rather than as agreement.
 */
export interface WireGingivalOffsetReading {
  requested_mm: number;
  achieved_median_mm?: number | null;
  achieved_min_mm?: number | null;
  achieved_max_mm?: number | null;
  /** How the achieved clearance was measured, in the backend's own words. */
  method?: string | null;
  /**
   * THE CLAMP (2026-07-25, "end-to-end automation must complete"). When the requested relief is
   * more than this (construction part x cap) pair can take without collapsing the screw-channel
   * wall, the run APPLIES the pair's ceiling instead of refusing at the end — and says so here.
   * `applied_mm` is what the emitted part was actually built at; it is NEVER assumed equal to
   * `requested_mm` client-side (absent = the backend did not clamp, or predates the clamp).
   */
  applied_mm?: number | null;
  clamped?: boolean;
  /** The ceiling that forced the clamp, and the wall rule it protects. */
  limit_mm?: number | null;
  min_wall_mm?: number | null;
  /** The backend's own sentence for why it clamped. */
  clamp_reason?: string | null;
}

/**
 * GET /api/relief-limit?construction_path=…&model=…&variant=… — the MAXIMUM SAFE RELIEF for one
 * (construction part x cap variant) pair, measured by the worker with the export gate's own
 * instrument, so the operator meets the ceiling when they choose the number rather than as a
 * failed package half an hour later.
 *
 * `max_safe_offset_mm: null` is an honest "could not be determined for this pair" — the UI says
 * exactly that and never renders it as "no limit". A 404 means the RUNNING backend predates the
 * endpoint (restart `make serve`); the run's own clamp still protects the part either way.
 */
export interface WireReliefLimit {
  construction_path: string;
  model: string;
  variant: string;
  max_safe_offset_mm: number | null;
  /** Accepted spelling from the worker's first cut of this endpoint — see mapReliefLimit. */
  max_safe_mm?: number | null;
  /** What sets the ceiling, in the backend's own words ("channel wall"). */
  limited_by?: string | null;
  /** The design rule the ceiling protects (design_rules.MIN_WALL_MM). The worker spells this
   *  `min_wall_rule_mm`; both are read as the same number (see mapReliefLimit). */
  min_wall_mm?: number | null;
  min_wall_rule_mm?: number | null;
  /** False when the number is a conservative fallback rather than a measurement on this pair. */
  measured?: boolean;
  note?: string | null;
}

export interface WireLibraryVariant {
  variant: string;
  rim_diameter_mm: number | null;
  height_mm: number | null;
  mesh_url: string;
}

/**
 * One entry of the FULL cross-model catalog (GET /api/library — case-independent, unlike
 * WireLibraryVariant's per-case picker above). `id` is unique within its model group and is
 * the mesh URL's path segment (plain variant for current parts, "<subdir>--<variant>" for
 * superseded archives). `flags` are computed honestly server-side from the bytes on disk:
 * "superseded" (archived under superseded-YYYY-MM-DD/), "legacy" (an old *-library dir),
 * "unloadable" (trimesh cannot read the file — listed, not hidden), "duplicate" (byte-identical
 * to another catalog file, whose model/id is named in `duplicate_of`).
 */
export interface WireLibraryCatalogEntry {
  id: string;
  variant: string;
  label: string;
  rim_diameter_mm: number | null;
  height_mm: number | null;
  filename: string;
  sha256: string;
  flags: string[];
  duplicate_of: string[];
  mesh_url: string;
}

export interface WireLibraryCatalogGroup {
  model: string;
  legacy: boolean;
  variants: WireLibraryCatalogEntry[];
}

export interface WireRunSummary {
  sites: WireRunSiteResult[];
  package_files: string[];
}

/** The selection a run was produced under, echoed back verbatim (server-side `vendor` is
 *  derived from the chosen construction `path_id`) — the acknowledgment panel shows what the
 *  operator actually authorized rather than what the UI believes it sent. Absent on payloads
 *  from a backend predating the decoding selection. */
export interface WireRunSelection {
  model: string;
  construction_path: string;
  vendor: string;
  jaw: string;
  gingival_offset_mm: number;
  variants: Record<string, string | null>;
}

export interface WireRunResult {
  summary: WireRunSummary;
  files_base: string;
  duration_s: number;
  cached: boolean;
  selection?: WireRunSelection | null;
}

/**
 * GET /api/cases/{id}/sites/{tooth}/deviation — the THREE-PANEL VERIFY's union colouring: the
 * seated library cap as a renderable mesh in the JAW WORLD FRAME (so it overlays the scan with
 * no client-side transform) with one signed millimetre per point. REPORTING ONLY: the same
 * instrument the acceptance difference map uses, never a second opinion — `stats` are the PNG's
 * own published RMS/p90 (area-uniform samples), not a vertex-weighted re-derivation, and
 * `vertex_footprint_points` is the coloured mesh's own coverage under its own name.
 * `deviation_mm[i]` is null where the read is not finite (no scan surface under that vertex).
 * 404 before a run has seated this site.
 */
export interface WireSiteDeviation {
  case_id: string;
  tooth: number;
  implant_model: string | null;
  variant: string | null;
  frame: string;
  units: string;
  n_points: number;
  points: WireVec3[];
  faces: readonly [number, number, number][];
  deviation_mm: (number | null)[];
  scale: {
    clamp_mm: number;
    min_mm: number;
    max_mm: number;
    colormap: string;
    sign_convention: string;
    data_min_mm: number | null;
    data_max_mm: number | null;
    footprint_band_mm: number;
  };
  stats: {
    rms_mm: number | null;
    p90_mm: number | null;
    n_footprint: number;
    n_samples: number;
    source: string;
  };
  vertex_footprint_points: number;
  reporting_only: boolean;
  /** Absent on builds that predate the pre-run preview (2026-07-26) — a shipped read then. */
  preview?: boolean;
  /** Only the preview carries it: the seat numbers the results table would print. */
  seat?: {
    seat_method: "rim" | "icp" | null;
    rim_agreement_mm: number | null;
    fit: { avg_mm: number; max_mm: number } | null;
  } | null;
  /**
   * The SEATED CAP'S OWN FRAME (2026-07-26) — the pose the run shipped, so the verify panes can
   * look straight down the cap instead of down a proxy direction that measured up to 42° off.
   * Absent on a server predating the field; the pane falls back and says so.
   */
  pose?: {
    axis: [number, number, number];
    x_axis: [number, number, number];
    origin: [number, number, number];
  } | null;
}

/**
 * The per-tooth "<case>-<tooth>-implant.json" package file — one of the paid-record deliverables
 * (see apps/worker's output_package.py), fetched client-side ONLY to draw the post-run seated-
 * pose axis triad (RealGUIDE-style); the run itself never needs this, it's a package artifact.
 * `pose_matrix` is row-major 4x4: rows 0-2 columns 0-2 are the rotation (each COLUMN is a unit
 * local axis direction in world space), column 3 rows 0-2 is the translation (== `position`).
 * `position`/`axis` are the same translation/local-Z-axis pulled out separately by the backend
 * for convenience; the triad only needs pose_matrix (all three rotation columns), not `axis`
 * alone (that's just column 2, the implant's long axis).
 */
export interface WireImplantRecord {
  case_id: string;
  tooth: number;
  pose_matrix: readonly [
    readonly [number, number, number, number],
    readonly [number, number, number, number],
    readonly [number, number, number, number],
    readonly [number, number, number, number],
  ];
  position: WireVec3;
  axis: WireVec3;
}

/** A row of a 4x4 row-major pose matrix (the shape WireImplantRecord writes). */
export type WirePoseRow4 = readonly [number, number, number, number];

/**
 * WHERE AN IMPORTED POSE CAME FROM — audit provenance, never a computation input. The server
 * records it alongside the write so a seat restored on this machine can be traced to the
 * session that earned it (which build, which case, which selection, which adjustments).
 */
export interface WireImportPoseSource {
  case_id: string;
  exported_at: string;
  format_version: number;
  model: string | null;
  variant: string | null;
  construction_path: string | null;
  jaw: string;
  gingival_offset_mm: number;
  nudge_cumulative_deg: number | null;
  seat_method: string | null;
}

/**
 * POST /api/cases/{id}/sites/{tooth}/import-pose request — a PROPOSED pose for one seated site,
 * expressed in that jaw's world frame exactly as "<case>-<tooth>-implant.json" writes it. It is
 * an operator write like the nudge: the server judges it with the same stability/certification
 * gates and audits it; the client never applies a pose itself.
 */
export interface WireImportPoseRequest {
  pose_matrix: readonly [WirePoseRow4, WirePoseRow4, WirePoseRow4, WirePoseRow4];
  source: WireImportPoseSource;
}
