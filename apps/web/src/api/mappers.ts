/**
 * Pure mappers: wire shapes -> domain types. No IO here.
 */
import type {
  WireAcceptance,
  WireAcceptanceMetric,
  WireAlignToCorrespondenceResult,
  WireAlignToMarkResult,
  WireBestFitResult,
  WireCorrespondenceResidual,
  WireGingivalOffsetReading,
  WireCorrespondencePairIn,
  WirePartAnnotation,
  WirePartFeature,
  WirePartFeatureIn,
  WireProduction,
  WireVec3,
  WireCaptureAssessment,
  WireCase,
  WireClocking,
  WireConfirmAlignmentResult,
  WireConstructionPart,
  WireReliefLimit,
  WireRunSelection,
  WireSiteDeviation,
  WireDoctorConfirmation,
  WireImplantRecord,
  WireImportPoseRequest,
  WireLibraryCatalogGroup,
  WireLibraryCatalogEntry,
  WireLibraryVariant,
  WireNudge,
  WireNudgeResult,
  WireProposal,
  WireProposeResult,
  WireRunResult,
  WireRunSiteResult,
  WireSuggestedSite,
  WireVariantCandidate,
} from "./wireTypes";
import { asJaw, subsamplePoints } from "../domain/types";
import type { ReliefLimit } from "../domain/reliefLimit";
import { PART_FEATURE_KINDS } from "../domain/partFeatures";
import type { PartAnnotation, PartFeature, PartFeatureInput } from "../domain/partFeatures";
import type { PoseTransferDocument, PoseTransferSite } from "../domain/poseTransfer";
import type {
  AlignToCorrespondenceResult,
  CorrespondencePair,
  CorrespondenceResidual,
} from "../domain/correspondence";
import type {
  Acceptance,
  AcceptanceMetric,
  AlignToMarkResult,
  BestFitResult,
  CaptureAssessment,
  CaptureSite,
  Case,
  Clocking,
  ConfirmAlignmentResult,
  ConfirmedSite,
  ConstructionPart,
  DoctorConfirmation,
  GingivalOffsetReading,
  RunSelection,
  SiteDeviation,
  ImplantPose,
  LibraryCatalogEntry,
  LibraryCatalogGroup,
  LibraryVariant,
  NudgeResult,
  NudgeState,
  Proposal,
  ProposeResult,
  RunResult,
  RunSiteResult,
  SuggestedSite,
  VariantCandidate,
  Vec3,
} from "../domain/types";
import type { WireRunSiteInput } from "./wireTypes";

function mapVariantCandidate(w: WireVariantCandidate): VariantCandidate {
  return {
    variant: w.variant,
    seatResidualMm: w.seat_residual_mm,
  };
}

/** The optional/absent wire fields collapse to honest defaults: no evidence tag reads as
 *  "none", no unverified flag reads as verified — matching what the backend's own tri-state
 *  contract writes when the fields are present. */
function mapClocking(w: WireClocking): Clocking {
  return {
    notchShiftDeg: w.notch_shift_deg,
    notchCorr: w.notch_corr,
    notchProminence: w.notch_prominence,
    evidence: w.evidence ?? "none",
    consistencyDeg: w.consistency_deg ?? null,
    rotationUnverified: w.rotation_unverified ?? false,
  };
}

function mapNudgeState(w: WireNudge): NudgeState {
  return { cumulativeDeg: w.cumulative_deg };
}

function mapAcceptanceMetric(w: WireAcceptanceMetric): AcceptanceMetric {
  return {
    key: w.key,
    label: w.label,
    unit: w.unit,
    // The wire audience is an open string; anything the UI doesn't recognize as the
    // doctor-facing verification set lands in the lab/QC group — never dropped.
    audience: w.audience === "doctor" ? "doctor" : "lab",
    industryRef: { value: w.industry_ref.value, source: w.industry_ref.source },
    bands: w.bands ? { passMax: w.bands.pass, reviewMax: w.bands.review } : null,
    note: w.note ?? null,
    value: w.value ?? null,
    display: w.display ?? null,
    band: w.band,
  };
}

function mapAcceptance(w: WireAcceptance): Acceptance {
  return {
    metrics: w.metrics.map(mapAcceptanceMetric),
    overall: { band: w.overall.band, missing: w.overall.missing },
    context: {
      label: w.context.label,
      text: w.context.text,
      industryRef: { value: w.context.industry_ref.value, source: w.context.industry_ref.source },
    },
  };
}

function mapDoctorConfirmation(w: WireDoctorConfirmation): DoctorConfirmation {
  return { confirmed: w.confirmed, note: w.note ?? null, ts: w.ts };
}

export function mapConfirmAlignmentResult(w: WireConfirmAlignmentResult): ConfirmAlignmentResult {
  return {
    tooth: w.tooth,
    confirmation: mapDoctorConfirmation(w.doctor_confirmation),
    acceptanceOverall: w.acceptance_overall,
  };
}

export function mapNudgeResult(w: WireNudgeResult): NudgeResult {
  return {
    tooth: w.tooth,
    appliedDeltaDeg: w.applied_delta_deg,
    cumulativeDeg: w.cumulative_deg,
    stabilityExcessMm: w.stability_excess_mm,
    clocking: mapClocking(w.clocking),
    nudge: mapNudgeState(w.nudge),
  };
}

export function mapAlignToMarkResult(w: WireAlignToMarkResult): AlignToMarkResult {
  return {
    ...mapNudgeResult(w),
    matchedFeatureAzimuthDeg: w.matched_feature_azimuth_deg,
    clickAzimuthDeg: w.click_azimuth_deg,
  };
}

function mapCorrespondenceResidual(w: WireCorrespondenceResidual): CorrespondenceResidual {
  return {
    featureId: w.feature_id,
    featureAzimuthDeg: w.feature_azimuth_deg,
    clickAzimuthDeg: w.click_azimuth_deg,
    deltaDeg: w.delta_deg,
    residualDeg: w.residual_deg,
    residualMm: w.residual_mm,
  };
}

export function mapAlignToCorrespondenceResult(
  w: WireAlignToCorrespondenceResult,
): AlignToCorrespondenceResult {
  return {
    ...mapNudgeResult(w),
    pairs: w.pairs.map(mapCorrespondenceResidual),
    residualRmsMm: w.residual_rms_mm,
  };
}

/**
 * One marked feature of a library part. The wire `kind`/`source` are open strings; an
 * unrecognized kind lands on "trench" (the coded cutout — the only kind the correspondence
 * flow is ever asked about today) and an unrecognized source on "operator", so a future
 * vendor keying style still LISTS and DRAWS rather than crashing the panel or silently
 * disappearing a mark the doctor placed. `defines_rotation` is the server's own verdict and
 * is never re-derived here — the lever-arm rule is the backend's to own.
 */
function mapPartFeature(w: WirePartFeature): PartFeature {
  const kind = PART_FEATURE_KINDS.find((k) => k === w.kind) ?? "trench";
  return {
    id: w.id,
    kind,
    azimuthDeg: w.azimuth_deg,
    radiusMm: w.radius_mm,
    zMm: w.z_mm,
    source: w.source === "auto" ? "auto" : "operator",
    definesRotation: w.defines_rotation,
  };
}

export function mapPartAnnotation(w: WirePartAnnotation): PartAnnotation {
  return {
    model: w.model,
    variant: w.variant,
    autoSeeded: w.auto_seeded,
    revisedAt: w.revised_at ?? null,
    features: w.features.map(mapPartFeature),
  };
}

/** The PUT body: exactly one placement per feature (the server 422s on both or neither). */
export function toWirePartFeatures(inputs: readonly PartFeatureInput[]): WirePartFeatureIn[] {
  return inputs.map((f) =>
    f.point !== null
      ? { kind: f.kind, point: [f.point[0], f.point[1], f.point[2]] as WireVec3 }
      : { kind: f.kind, azimuth_deg: f.azimuthDeg ?? 0 },
  );
}

/**
 * The align-to-correspondence body: a FEATURE pair travels as `feature_id`, a FREE POINT pair
 * (client ask 2026-07-26) as `part_point` — never both, mirroring the server's own
 * exactly-one-part-half rule so a malformed pair fails HERE, at build time, not as a 422 the
 * operator has to read.
 */
export function toWireCorrespondencePairs(
  pairs: readonly CorrespondencePair[],
): WireCorrespondencePairIn[] {
  return pairs.map((p) => {
    if (p.featureId !== null) return { feature_id: p.featureId, scan_point: p.scanPoint };
    if (p.partPoint !== null) return { part_point: p.partPoint, scan_point: p.scanPoint };
    throw new Error("a correspondence pair needs a feature id or a part point");
  });
}

function toVec3(v: readonly [number, number, number]): Vec3 {
  return [v[0], v[1], v[2]];
}

function mapSuggestedSite(w: WireSuggestedSite): SuggestedSite {
  return {
    tooth: w.tooth,
    center: toVec3(w.center),
    declaredVariant: w.declared_variant,
    centerMark: w.center_mark ? toVec3(w.center_mark) : null,
    rimMark: w.rim_mark ? toVec3(w.rim_mark) : null,
  };
}

/**
 * A listed case. The name-matched fields are DEFAULTS, never gates: `suggested_model` /
 * `suggested_construction` are absent on a backend predating the no-inference discovery and
 * null on a case whose folder name matched nothing — both collapse to null, which the UI reads
 * as "the operator must choose", not as "guess something". `vendor` is nullable for the same
 * reason (it is derived from the suggested construction).
 */
export function mapCase(w: WireCase): Case {
  return {
    id: w.id,
    doctor: w.doctor,
    jaw: asJaw(w.jaw),
    vendor: w.vendor ?? null,
    scanUrl: w.scan_url,
    scanFilename: w.scan_filename ?? null,
    suggestedModel: w.suggested_model ?? null,
    suggestedConstruction: w.suggested_construction ?? null,
    suggestedSites: w.suggested_sites.map(mapSuggestedSite),
  };
}

export function mapConstructionPart(w: WireConstructionPart): ConstructionPart {
  return { vendor: w.vendor, filename: w.filename, pathId: w.path_id, label: w.label };
}

export function mapConstructionParts(w: readonly WireConstructionPart[]): ConstructionPart[] {
  return w.map(mapConstructionPart);
}

function mapCaptureAssessment(w: WireCaptureAssessment): CaptureAssessment {
  return {
    verdict: w.verdict,
    checks: w.checks.map((c) => ({
      name: c.name,
      value: c.value,
      boundPass: c.bound_pass,
      boundRescan: c.bound_rescan,
      verdict: c.verdict,
      message: c.message,
    })),
  };
}

function mapProposal(w: WireProposal): Proposal {
  return {
    center: toVec3(w.center),
    voidRatio: w.void_ratio,
    rimBelowCuspsMm: w.rim_below_cusps_mm,
    // absent on payloads from a backend predating the capture gate -> honest null
    capture: w.capture ? mapCaptureAssessment(w.capture) : null,
  };
}

export function mapProposeResult(w: WireProposeResult): ProposeResult {
  const proposals = w.proposals.map(mapProposal);
  const captureSites: CaptureSite[] = proposals
    .filter((p) => p.capture !== null)
    .map((p) => ({ center: p.center, tooth: null, capture: p.capture as CaptureAssessment }));
  for (const s of w.suggested_capture ?? []) {
    if (s.center) {
      captureSites.push({
        center: toVec3(s.center),
        tooth: s.tooth,
        capture: mapCaptureAssessment(s.capture),
      });
    }
  }
  return {
    proposals,
    durationS: w.duration_s,
    cached: w.cached,
    captureSites,
  };
}

function mapRunSiteResult(w: WireRunSiteResult): RunSiteResult {
  return {
    tooth: w.tooth,
    spec: w.spec,
    vendor: w.vendor,
    coverage: w.coverage,
    alignmentErrorMm: w.alignment_error_mm,
    advisory: w.advisory,
    variant: {
      identified: w.variant.identified,
      declared: w.variant.declared,
      measuredRimDiameterMm: w.variant.measured_rim_diameter_mm,
      diameterClassMarginMm: w.variant.diameter_class_margin_mm,
      flags: w.variant.flags,
      // Absent (legacy cache) or explicitly null (ICP-seated site) both collapse to null.
      candidates: w.variant.candidates ? w.variant.candidates.map(mapVariantCandidate) : null,
    },
    siteMeasurement: {
      mdSpanMm: w.site_measurement.md_span_mm,
      gapMesialMm: w.site_measurement.gap_mesial_mm,
      gapDistalMm: w.site_measurement.gap_distal_mm,
      classification: w.site_measurement.classification,
      terminalSite: w.site_measurement.terminal_site,
    },
    production: {
      screwChannelRadiusMm: w.production.screw_channel_radius_mm,
    },
    seedSource: w.seed_source,
    autoDeltaMm: w.auto_delta_mm,
    // Defensive: the live contract always sends fit, but a legacy cached run result on disk
    // (computed before this field existed) can still come back without it.
    fit: w.fit ? { avgMm: w.fit.avg_mm, maxMm: w.fit.max_mm } : null,
    // Both optional: absent on legacy cached run results computed before they existed.
    seatMethod: w.seat_method ?? null,
    guidance: w.guidance ? { level: w.guidance.level, actions: w.guidance.actions } : null,
    // Absent (legacy cache) or explicitly null (not computable) both collapse to null.
    rimAgreementMm: w.rim_agreement_mm ?? null,
    borderClickDisagreementMm: w.border_click_disagreement_mm ?? null,
    topFaceAgreementMm: w.top_face_agreement_mm ?? null,
    confidence: w.confidence
      ? {
          grade: w.confidence.grade,
          posSpreadMm: w.confidence.pose_pos_spread_mm,
          axisSpreadDeg: w.confidence.pose_axis_spread_deg,
        }
      : null,
    capSurfaceExplainedPct: w.cap_surface_explained_pct ?? null,
    // Absent (legacy cache / icp seat) collapses to null — no clock instrument to show.
    clocking: w.clocking ? mapClocking(w.clocking) : null,
    nudge: w.nudge ? mapNudgeState(w.nudge) : null,
    // Absent (backend predating the verification panel) collapses to null — no panel data.
    acceptance: w.acceptance ? mapAcceptance(w.acceptance) : null,
    doctorConfirmation: w.doctor_confirmation ? mapDoctorConfirmation(w.doctor_confirmation) : null,
    gingivalOffset: w.gingival_offset
      ? mapGingivalOffset(w.gingival_offset, w.production)
      : null,
  };
}

/**
 * The offset honesty block. Every ACHIEVED number is optional and stays null when absent —
 * "not measured" must never render as "achieved exactly what you asked for". The CLAMP half is
 * read the same way: `clamped` defaults to false and `appliedMm` to null, so a backend that says
 * nothing is read as "not clamped / not reported", never as "applied exactly what you asked".
 *
 * TWO BLOCKS, ONE READING (fixed 2026-07-25 against the live API). The worker writes the clamp
 * into the site's `production` block, while `gingival_offset` carries the achieved-clearance
 * measurement and a `requested_mm` that is really the APPLIED value (the relief the part was cut
 * with). Reading only `gingival_offset` therefore reported every real clamped run as UNCLAMPED
 * and printed the applied number under the label "requested" — the operator would have seen
 * 0.08 mm described as their own choice after typing 0.20 mm. So `production` wins for all four
 * clamp facts and for the true ask, and `gingival_offset`'s clamp fields remain accepted as a
 * fallback. Neither number is ever invented: an absent ask falls back to the cut value, which is
 * what a pre-clamp backend meant by it.
 */
function mapGingivalOffset(
  w: WireGingivalOffsetReading,
  production?: WireProduction,
): GingivalOffsetReading {
  const askedMm = production?.gingival_offset_requested_mm;
  const appliedMm = production?.gingival_offset_applied_mm ?? w.applied_mm ?? null;
  return {
    requestedMm: typeof askedMm === "number" && Number.isFinite(askedMm) ? askedMm : w.requested_mm,
    achievedMedianMm: w.achieved_median_mm ?? null,
    achievedMinMm: w.achieved_min_mm ?? null,
    achievedMaxMm: w.achieved_max_mm ?? null,
    method: w.method ?? null,
    appliedMm,
    clamped: production?.clamped === true || w.clamped === true,
    limitMm: production?.max_safe_mm ?? w.limit_mm ?? null,
    minWallMm: w.min_wall_mm ?? null,
    clampReason: production?.clamp_reason ?? w.clamp_reason ?? null,
  };
}

/**
 * THE RELIEF CEILING for one (construction part x cap variant) pair.
 *
 * `max_safe_offset_mm` is the contract; `max_safe_mm` is accepted as a synonym because the
 * worker and web halves of this endpoint were built in the same hour and the shorter spelling
 * appeared in the worker's first cut. Both are read as the SAME number and neither is invented:
 * when both are absent the ceiling is null, which the UI states as "not determined" rather than
 * as "no limit". `limitedBy` falls back to the only thing that limits it today, in the same
 * words the export gate uses.
 */
export function mapReliefLimit(w: WireReliefLimit): ReliefLimit {
  const maxSafe = w.max_safe_offset_mm ?? w.max_safe_mm ?? null;
  return {
    constructionPathId: w.construction_path,
    model: w.model,
    variant: w.variant,
    maxSafeMm: typeof maxSafe === "number" && Number.isFinite(maxSafe) ? maxSafe : null,
    limitedBy: w.limited_by ?? "channel wall",
    // the worker spells the rule `min_wall_rule_mm`; both spellings are the SAME number, and
    // reading only one left the ceiling warning unable to name the 0.50 mm rule it protects
    minWallMm: w.min_wall_mm ?? w.min_wall_rule_mm ?? null,
    measured: w.measured !== false,
    note: w.note ?? null,
  };
}

/**
 * The manual best fit. Everything past tooth/diameter/applied is optional on the wire (a
 * measure-only run re-emits nothing, an ICP seat has no clocking), so each field collapses to
 * null rather than to a fabricated zero — the panel prints only what was actually measured.
 */
export function mapBestFitResult(w: WireBestFitResult): BestFitResult {
  return {
    tooth: w.tooth,
    matchingDiameterMm: w.matching_diameter_mm,
    applied: w.applied,
    nMatched: w.n_matched ?? null,
    rmsMm: w.rms_mm ?? null,
    maxMm: w.max_mm ?? null,
    translationMm: w.translation_mm ?? null,
    rotationDeg: w.rotation_deg ?? null,
    fit: w.fit ? { avgMm: w.fit.avg_mm, maxMm: w.fit.max_mm } : null,
    rimAgreementMm: w.rim_agreement_mm ?? null,
    clocking: w.clocking ? mapClocking(w.clocking) : null,
    nudge: w.nudge ? mapNudgeState(w.nudge) : null,
  };
}

function mapLibraryVariant(w: WireLibraryVariant): LibraryVariant {
  return {
    variant: w.variant,
    rimDiameterMm: w.rim_diameter_mm,
    heightMm: w.height_mm,
    meshUrl: w.mesh_url,
  };
}

export function mapLibraryVariants(w: readonly WireLibraryVariant[]): LibraryVariant[] {
  return w.map(mapLibraryVariant);
}

function mapLibraryCatalogEntry(w: WireLibraryCatalogEntry): LibraryCatalogEntry {
  return {
    id: w.id,
    variant: w.variant,
    label: w.label,
    rimDiameterMm: w.rim_diameter_mm,
    heightMm: w.height_mm,
    filename: w.filename,
    sha256: w.sha256,
    flags: w.flags,
    duplicateOf: w.duplicate_of,
    meshUrl: w.mesh_url,
  };
}

export function mapLibraryCatalog(w: readonly WireLibraryCatalogGroup[]): LibraryCatalogGroup[] {
  return w.map((group) => ({
    model: group.model,
    legacy: group.legacy,
    variants: group.variants.map(mapLibraryCatalogEntry),
  }));
}

/** The selection echo. Tooth keys arrive as strings (JSON object keys) and are parsed back to
 *  numbers; an unparseable key is dropped rather than landing as NaN in the map. */
function mapRunSelection(w: WireRunSelection): RunSelection {
  const variants = new Map<number, string | null>();
  for (const [tooth, variant] of Object.entries(w.variants ?? {})) {
    const n = Number(tooth);
    if (Number.isFinite(n)) variants.set(n, variant ?? null);
  }
  return {
    model: w.model,
    constructionPathId: w.construction_path,
    vendor: w.vendor,
    jaw: asJaw(w.jaw),
    gingivalOffsetMm: w.gingival_offset_mm,
    variantByTooth: variants,
  };
}

export function mapRunResult(w: WireRunResult): RunResult {
  return {
    summary: {
      sites: w.summary.sites.map(mapRunSiteResult),
      packageFiles: w.summary.package_files,
    },
    filesBase: w.files_base,
    durationS: w.duration_s,
    cached: w.cached,
    // absent (backend predating the decoding selection) collapses to null — the acknowledgment
    // read-out then says nothing rather than repeating what the client believes it sent
    selection: w.selection ? mapRunSelection(w.selection) : null,
  };
}

/**
 * The union panel's deviation mesh. Points and faces are packed into typed arrays here (at the
 * API boundary, once) rather than in the viewer: an 11k-point real payload is ~830 KB of JSON,
 * and the three.js BufferGeometry wants exactly these flat arrays. `deviation_mm` keeps its
 * per-point nulls — "no scan surface under this vertex" is a state the colouring must show as
 * unmeasured, and flattening it to 0 would paint a hole as a perfect fit.
 */
export function mapSiteDeviation(w: WireSiteDeviation): SiteDeviation {
  const points = new Float32Array(w.points.length * 3);
  w.points.forEach((p, i) => {
    points[i * 3] = p[0];
    points[i * 3 + 1] = p[1];
    points[i * 3 + 2] = p[2];
  });
  const faces = new Uint32Array(w.faces.length * 3);
  w.faces.forEach((f, i) => {
    faces[i * 3] = f[0];
    faces[i * 3 + 1] = f[1];
    faces[i * 3 + 2] = f[2];
  });
  return {
    caseId: w.case_id,
    tooth: w.tooth,
    implantModel: w.implant_model ?? null,
    variant: w.variant ?? null,
    frame: w.frame,
    nPoints: w.n_points,
    points,
    faces,
    deviationMm: w.deviation_mm.map((v) => (typeof v === "number" && Number.isFinite(v) ? v : null)),
    scale: {
      clampMm: w.scale.clamp_mm,
      minMm: w.scale.min_mm,
      maxMm: w.scale.max_mm,
      colormap: w.scale.colormap,
      signConvention: w.scale.sign_convention,
      dataMinMm: w.scale.data_min_mm ?? null,
      dataMaxMm: w.scale.data_max_mm ?? null,
      footprintBandMm: w.scale.footprint_band_mm,
    },
    stats: {
      rmsMm: w.stats.rms_mm ?? null,
      p90Mm: w.stats.p90_mm ?? null,
      nFootprint: w.stats.n_footprint,
      nSamples: w.stats.n_samples,
      source: w.stats.source,
    },
    vertexFootprintPoints: w.vertex_footprint_points,
    // Absent on a backend that predates the preview endpoint — a payload with no flag is a
    // SHIPPED read (the only kind such a build serves), never an unlabelled preview.
    preview: w.preview === true,
    seat: w.seat
      ? {
          seatMethod: w.seat.seat_method ?? null,
          rimAgreementMm: w.seat.rim_agreement_mm ?? null,
          fit: w.seat.fit ? { avgMm: w.seat.fit.avg_mm, maxMm: w.seat.fit.max_mm } : null,
        }
      : null,
    // The seated cap's own frame. Guarded on the arrays actually being there: a server
    // predating the field simply omits it, and the pane falls back rather than reading undefined.
    pose:
      w.pose && Array.isArray(w.pose.axis) && Array.isArray(w.pose.x_axis)
        ? {
            axis: toVec3(w.pose.axis),
            xAxis: toVec3(w.pose.x_axis),
            origin: toVec3(w.pose.origin),
          }
        : null,
  };
}

/**
 * Extract the axis-triad pose from a fetched "<case>-<tooth>-implant.json" record:
 * pose_matrix is row-major 4x4 — each ROTATION COLUMN j is [row0[j], row1[j], row2[j]], a unit
 * local axis direction in world space; column 3 rows 0-2 is the translation, identical to the
 * separate `position` field the backend also writes (we read `position` directly rather than
 * re-deriving it from the matrix, since it's already there and unambiguous either way).
 */
export function mapImplantPose(w: WireImplantRecord): ImplantPose {
  const m = w.pose_matrix;
  const column = (j: number): Vec3 => [m[0][j] as number, m[1][j] as number, m[2][j] as number];
  return {
    tooth: w.tooth,
    position: toVec3(w.position),
    axisX: column(0),
    axisY: column(1),
    axisZ: column(2),
  };
}

export function toWireRunSiteInput(s: ConfirmedSite): WireRunSiteInput {
  let input: WireRunSiteInput = {
    tooth: s.tooth,
    center: [s.center[0], s.center[1], s.center[2]],
  };
  if (s.declaredVariant !== undefined && s.declaredVariant.trim() !== "") {
    input = { ...input, declared_variant: s.declaredVariant.trim() };
  }
  if (s.markedPoints !== undefined && s.markedPoints.length > 0) {
    input = {
      ...input,
      marked_points: subsamplePoints(s.markedPoints).map((p) => [p[0], p[1], p[2]]),
    };
  }
  if (s.centerMark !== undefined) {
    input = { ...input, center_mark: [s.centerMark[0], s.centerMark[1], s.centerMark[2]] };
  }
  // rim_points (multi-click border collection) supersedes the legacy single rim_mark for new
  // doctor input — send rim_points whenever the row has any, and only fall back to the legacy
  // rim_mark when rimPoints is absent/empty (curated prefills, which still populate rimMark).
  if (s.rimPoints !== undefined && s.rimPoints.length > 0) {
    input = { ...input, rim_points: s.rimPoints.map((p) => [p[0], p[1], p[2]]) };
  } else if (s.rimMark !== undefined) {
    input = { ...input, rim_mark: [s.rimMark[0], s.rimMark[1], s.rimMark[2]] };
  }
  return input;
}

/**
 * One site of a parsed pose file as the import endpoint's body. The matrix goes over
 * UNCHANGED — it is the pipeline's own `implant.json` shape, and re-deriving it here would put
 * a second opinion about the pose between the two halves of a round trip. Everything under
 * `source` is audit provenance the server records with the write.
 */
export function toWireImportPose(
  doc: PoseTransferDocument,
  site: PoseTransferSite,
): WireImportPoseRequest {
  return {
    pose_matrix: site.poseMatrix,
    source: {
      case_id: doc.caseId,
      exported_at: doc.exportedAt,
      format_version: doc.version,
      model: doc.selection.model,
      variant: site.variantId,
      construction_path: doc.selection.constructionPathId,
      jaw: doc.selection.jaw,
      gingival_offset_mm: doc.selection.gingivalOffsetMm,
      nudge_cumulative_deg: site.provenance.nudgeCumulativeDeg,
      seat_method: site.provenance.seatMethod,
    },
  };
}
