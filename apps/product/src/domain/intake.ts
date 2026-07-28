/**
 * INTAKE'S RULES (plan §4, §7 slice 4), framework-free: when the auto-detect fires,
 * what the capture verdicts mean for the banner and the chips, which markers the stage
 * shows, and how a single panel change becomes the FULL explicit choice document.
 *
 * Direction of trust (AM-4): every verdict and completion fact here is the BFF's
 * derivation — this module only decides how to DISPLAY them and what to send back as
 * the operator's own acts. Nothing computed here claims an outcome.
 */
import type {
  CaptureAssessmentView,
  CaseSessionDetail,
  ChoicesUpdate,
  DetectedProposalView,
  SiteView,
} from "../api/client";

/**
 * THE AUTO-FIRE DECISION (plan §4: detection fires AUTOMATICALLY on Intake) — keyed on
 * session FACTS plus a fired-marker, the demo's stage-routing lesson: an effect that
 * re-derives its trigger from render state re-fires forever; one that compares a stable
 * key fires once. Detection already done → never; already fired for this case in this
 * mount → never (the response, success or refusal, is what changes the facts).
 */
export function shouldAutoDetect(args: {
  readonly caseId: string;
  readonly detectionDone: boolean;
  readonly alreadyFiredFor: string | null;
}): boolean {
  return !args.detectionDone && args.alreadyFiredFor !== args.caseId;
}

/** The capture verdict vocabulary (worker capture_gate): worst check wins. */
export const RESCAN = "rescan";

export interface RescanNotice {
  /** Where the deficiency is: a curated tooth, or a detector finding without one. */
  readonly label: string;
  /** The worker's own sentence for the worst failing check. */
  readonly message: string;
}

function worstRescanMessage(capture: CaptureAssessmentView): string {
  const failing = capture.checks.find((c) => c.verdict === RESCAN);
  return failing?.message ?? "Capture quality is below the rescan threshold.";
}

/**
 * Every rescan-grade verdict in the payload — sites first (they carry teeth), then
 * unmatched proposals. Non-empty ⇒ the banner renders BEFORE any work is invested:
 * the plan's chair-side moment (the patient may still be in the chair; marks placed
 * on an unusable capture are marks wasted).
 */
export function rescanNotices(detail: CaseSessionDetail): readonly RescanNotice[] {
  const notices: RescanNotice[] = [];
  for (const site of detail.sites) {
    if (site.capture?.verdict === RESCAN) {
      notices.push({
        label: `Tooth ${site.tooth}`,
        message: worstRescanMessage(site.capture),
      });
    }
  }
  const matchedTeeth = new Set(
    detail.sites.map((s) => s.tooth),
  );
  for (const p of detail.detection?.proposals ?? []) {
    if (p.capture.verdict !== RESCAN) continue;
    if (p.tooth_guess !== null && matchedTeeth.has(p.tooth_guess)) continue; // the site row already says it
    notices.push({
      label: "Detected site (no tooth assigned yet)",
      message: worstRescanMessage(p.capture),
    });
  }
  return notices;
}

/** The chip's words per verdict — the demo's exact labels (parity fix, review finding 4):
 * "RESCAN" shouts by design (CaptureChip's rule: the one verdict where continuing wastes
 * marks must be prominent), pass/marginal stay chip-quiet. Unknown wire words fall back to
 * the verdict itself rather than a lie. */
const CAPTURE_CHIP_LABEL: Readonly<Record<string, string>> = {
  pass: "capture ✓",
  marginal: "capture marginal",
  rescan: "RESCAN",
};

/** The chip's words for one site — the verdict's label, or the honest "not assessed yet". */
export function captureChipLabel(capture: CaptureAssessmentView | null): string {
  if (capture === null) return "not assessed";
  return CAPTURE_CHIP_LABEL[capture.verdict] ?? capture.verdict;
}

/**
 * What the stage marks: every detector proposal, plus curated sites the detector did
 * not find (no proposal guessed their tooth) so a curated site never disappears from
 * the 3D just because the detector missed it. Radius = the worker's 2.6mm crop
 * fallback — a locator ring, not a measurement claim.
 */
export const MARKER_RADIUS_MM = 2.6;

export interface SiteMarker {
  readonly center: readonly [number, number, number];
  readonly radiusMm: number;
}

function asVec3(center: readonly number[]): readonly [number, number, number] | null {
  return center.length === 3
    ? [center[0]!, center[1]!, center[2]!]
    : null;
}

export function detectionMarkers(detail: CaseSessionDetail): readonly SiteMarker[] {
  const markers: SiteMarker[] = [];
  const proposals: readonly DetectedProposalView[] = detail.detection?.proposals ?? [];
  const guessedTeeth = new Set(
    proposals.map((p) => p.tooth_guess).filter((t): t is number => t !== null),
  );
  for (const p of proposals) {
    const center = asVec3(p.center);
    if (center !== null) markers.push({ center, radiusMm: MARKER_RADIUS_MM });
  }
  const unmatched = (site: SiteView) => !guessedTeeth.has(site.tooth);
  for (const site of detail.sites.filter(unmatched)) {
    const center = site.center !== null ? asVec3(site.center) : null;
    if (center !== null) markers.push({ center, radiusMm: MARKER_RADIUS_MM });
  }
  return markers;
}

/** The construction dropdown's rows, extracted from the worker-shaped catalog rows
 * (untyped on the wire until Declare gives them real shapes — slice 5a): a row without
 * a string path_id cannot be chosen and is dropped rather than rendered as a lie. */
export function constructionOptions(
  detail: CaseSessionDetail,
): readonly { readonly path_id: string; readonly label: string }[] {
  return detail.catalog.constructions.flatMap((row) => {
    const path = row["path_id"];
    if (typeof path !== "string") return [];
    const label = row["label"];
    return [{ path_id: path, label: typeof label === "string" ? label : path }];
  });
}

/**
 * A single panel change becomes the FULL choice document (PUT semantics — what is sent
 * is what is chosen). Unchanged fields carry the session's persisted choice when one
 * exists, else the PRE-FILL the plan names (§4: "pre-filled from the suggestion"):
 * construction from the case's name-matched suggestion, jaw from the scan-filename
 * reading, relief from the worker's default ask. The pre-fill only ever leaves this
 * app inside an operator-initiated PUT — one change makes the whole panel an explicit
 * act, which is exactly the demo's send-it-back-explicitly contract.
 */
export function choicesUpdateFrom(
  detail: CaseSessionDetail,
  patch: Partial<ChoicesUpdate>,
): ChoicesUpdate {
  const chosen = detail.choices;
  return {
    construction_path:
      patch.construction_path !== undefined
        ? patch.construction_path
        : (chosen.construction_path ?? detail.case.suggested_construction),
    jaw: patch.jaw !== undefined ? patch.jaw : (chosen.jaw ?? detail.case.jaw),
    gingival_offset_mm:
      patch.gingival_offset_mm !== undefined
        ? patch.gingival_offset_mm
        : (chosen.gingival_offset_mm ?? chosen.gingival_offset_default_mm),
  };
}

/**
 * The relief input's ceiling readout, per variant row the BFF served: the asked relief
 * against the pair's measured ceiling. An ask above the ceiling is NOT an error — the
 * run cuts at the ceiling and says so (the worker's ask-not-guarantee posture) — but
 * the operator must see it BEFORE investing work, which is Intake's whole point.
 */
export interface CeilingReadout {
  readonly variant: string;
  readonly line: string;
  readonly exceeded: boolean;
}

export function ceilingReadouts(
  detail: CaseSessionDetail,
  askedMm: number | null,
): readonly CeilingReadout[] {
  return detail.relief_ceilings.map((row) => {
    if (row.error !== null || row.max_safe_mm === null) {
      return {
        variant: row.variant,
        line: `${row.variant}: ceiling unavailable — ${row.error ?? "no reading"}`,
        exceeded: false,
      };
    }
    const asked = askedMm ?? detail.choices.gingival_offset_default_mm;
    const exceeded = asked > row.max_safe_mm;
    const ceiling = `${row.variant}: ceiling ${row.max_safe_mm.toFixed(2)}mm` +
      (row.limited_by !== null ? ` (limited by ${row.limited_by})` : "");
    return {
      variant: row.variant,
      line: exceeded
        ? `${ceiling} — the ${asked.toFixed(2)}mm ask will be cut at the ceiling`
        : ceiling,
      exceeded,
    };
  });
}
