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

/**
 * THE ONE DEFINITION OF "A USABLE CENTRE" (audit 2026-07-31).
 *
 * Exactly three coordinates, all FINITE. The finiteness check is not defensive
 * pedantry: only the operator-mark route validates a 3-and-finite vector
 * (bff/resources/case_sessions.py:1264) — a CURATED site's `center` is an
 * unvalidated pass-through of the case record (:495-496), typed no more tightly
 * than `Optional[List[float]]`. A NaN coordinate then poisons every comparison
 * downstream (`NaN > radius` is false, so the site is not skipped; `NaN < best` is
 * also false, so it never wins either), which is a worse failure than not having a
 * point at all.
 *
 * Exported because flow.ts's rail count must use THIS predicate: the rail once
 * counted `center !== null` while the site list and the picker used this one, so a
 * two-coordinate centre had the rail printing "5 sites detected" over a row that
 * said "has no centre yet — the stage cannot frame it".
 */
export function asVec3(
  center: readonly number[] | null,
): readonly [number, number, number] | null {
  if (center === null || center.length !== 3) return null;
  const [x, y, z] = center as readonly [number, number, number];
  return Number.isFinite(x) && Number.isFinite(y) && Number.isFinite(z)
    ? [x, y, z]
    : null;
}

/** A site's centre as a usable 3-vector, or nothing — a short/absent vector is never
 *  padded into a point (the stage would then frame a place that does not exist). */
export function siteCentre(site: SiteView): readonly [number, number, number] | null {
  return asVec3(site.center);
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
    const center = asVec3(site.center);
    if (center !== null) markers.push({ center, radiusMm: MARKER_RADIUS_MM });
  }
  return markers;
}

/**
 * PICKING A SITE BY CLICKING IT ON THE SCAN (client 2026-07-31).
 *
 * The design prototype picks caps off a flat 2D arch schematic; this product has the
 * real scan on the stage, so the pick is resolved in millimetres: the click lands on
 * the mesh surface (the viewer's one-shot point pick) and the nearest site CENTRE
 * within reach owns it.
 *
 * 6mm, not the 2.6mm marker ring: the stored centre sits at rim height over the screw
 * recess while the click lands wherever the operator's ray met the cap's flank, so the
 * reach has to cover a whole cap from its own centre. Beyond it the operator plainly
 * meant something else and a MISS is the honest answer: snapping to the least-far site
 * would silently reframe the stage onto a tooth nobody clicked.
 *
 * WHY THIS DOES NOT RESOLVE BY NEAREST (audit 2026-07-31). The earlier justification
 * here was arithmetically false: `cap_detection._MIN_SEPARATION_MM = 8.0` bounds
 * centre-to-CENTRE distance, not click-to-centre, so with two centres 8mm apart a
 * click at 5mm from one is 3mm from the other and BOTH are inside a 6mm reach. Worse,
 * that filter is internal to the detector and governs neither of the two site sets
 * this searches: `POST /{case_id}/sites` (bff/resources/case_sessions.py:1244-1281)
 * validates tooth-uniqueness, 1..32 and a finite 3-vector and nothing about spacing,
 * so the missed-cap door can place a centre 1mm from an existing site.
 *
 * Dropping the reach to 4mm was the other option and was rejected: it would make a
 * legitimate flank click on a well-isolated cap miss, which is the common case, to
 * guard the rare one. Instead the rare one is SAID. An ambiguous click is refused out
 * loud, exactly the way a bare-arch click is said rather than snapped — the operator
 * settles it with one more click, and the stage never flies to a tooth on a guess.
 */
export const SITE_PICK_RADIUS_MM = 6.0;

/** What one click on the scan resolved to. `ambiguous` carries the teeth in reach,
 *  nearest first, so the surface can name them in the order the operator would look. */
export type SitePick =
  | { readonly kind: "site"; readonly tooth: number }
  | { readonly kind: "miss" }
  | { readonly kind: "ambiguous"; readonly teeth: readonly number[] };

export function pickSiteAt(
  sites: readonly SiteView[],
  point: readonly [number, number, number],
  radiusMm: number = SITE_PICK_RADIUS_MM,
): SitePick {
  const inReach: { tooth: number; distance: number }[] = [];
  for (const site of sites) {
    const centre = siteCentre(site);
    if (centre === null) continue;
    const distance = Math.hypot(
      centre[0] - point[0],
      centre[1] - point[1],
      centre[2] - point[2],
    );
    // written as "<= radius", not "> radius ⇒ skip": a NaN distance must FAIL the
    // test rather than slip through it (siteCentre already refuses non-finite
    // centres, so this is belt-and-braces on the arithmetic itself)
    if (!(distance <= radiusMm)) continue;
    inReach.push({ tooth: site.tooth, distance });
  }
  if (inReach.length === 0) return { kind: "miss" };
  inReach.sort((a, b) => a.distance - b.distance);
  if (inReach.length > 1) {
    return { kind: "ambiguous", teeth: inReach.map((entry) => entry.tooth) };
  }
  return { kind: "site", tooth: inReach[0]!.tooth };
}

/**
 * THE MISSED-CAP MARK, as the container holds it (client 2026-07-28; audit
 * 2026-07-31). Kept here rather than as four `useState`s in the component so the
 * one rule that got broken has a name and a test.
 */
export interface MarkDraft {
  /** the next stage click is the CENTRE — false again the moment one is placed */
  readonly armed: boolean;
  /** a centre placed and awaiting its tooth; a mark is only a site once named */
  readonly pending: readonly number[] | null;
  readonly tooth: string;
  /** the BFF's own refusal, verbatim */
  readonly error: string | null;
}

export const EMPTY_MARK: MarkDraft = {
  armed: false,
  pending: null,
  tooth: "",
  error: null,
};

/**
 * ARMING THE SITE PICKER (audit 2026-07-31). Intake has two doors onto the viewer's
 * SINGLE one-shot point pick, so arming either must disarm the other — but disarming
 * is not discarding. `handleArmPick` used to reset the whole draft, which threw away
 * a placed-but-unnamed centre: the operator had marked the cap, typed its tooth, then
 * clicked "Pick a site on the scan" to check a neighbour, and the panel collapsed to
 * its idle button with no message and no centre, a fresh hunt in 3D to redo.
 *
 * That is precisely the quiet loss this surface's doctrine forbids (a human's mark is
 * fixed at the UI or refused, never dropped downstream), the panel already offers
 * "Discard the mark" so discarding is a deliberate act, and the sibling
 * `handleSelectSite` never reset the mark either. `armed` is already false once a
 * centre is placed, so a placed draft makes no claim on the point pick at all.
 */
export function markOnArmPick(mark: MarkDraft): MarkDraft {
  return mark.armed ? { ...mark, armed: false } : mark;
}

/** Arming the mark: a stale refusal from the last attempt is not about this one. */
export function markOnArmMark(mark: MarkDraft): MarkDraft {
  return { ...mark, armed: true, error: null };
}

/**
 * THE EVIDENCE A SITE ROW CARRIES (client 2026-07-31).
 *
 * The design prototype puts a confidence percentage on every row. There is no such
 * number: the worker's DetectedSite carries no confidence, and a percentage minted in
 * the browser would be a client-side verdict — exactly what this app must never do
 * (trust direction, AM-4). What the server DOES know per site is rendered instead, in
 * the worker's own units:
 *
 *  - the variant the operator declared, else the one the registration SUGGESTED;
 *  - void_ratio — the screw recess read as an absence of scan in the cap's core
 *    (auto_flow.ProposedSite): real caps measured 0.37-0.62 across the client's two
 *    arches, a palate slope (no recess at all) measured 0.79;
 *  - rim_below_cusps_mm — how far the rim sits under the neighbouring cusps: caps
 *    measured 0.0-0.66mm, the worst tissue artifacts 0.79-1.9mm.
 *
 * Both numbers are the DETECTOR's, so they only exist for a site a proposal guessed:
 * a hand-marked centre (the missed-cap door) has never been measured, and borrowing a
 * neighbour's numbers would be a lie.
 */
export interface SiteFact {
  readonly key: "variant" | "recess" | "rim";
  readonly text: string;
  /** Why the number means anything — the measured ranges, not a restatement. */
  readonly title: string;
}

export function siteEvidence(
  detail: CaseSessionDetail,
  site: SiteView,
): readonly SiteFact[] {
  const facts: SiteFact[] = [];
  const variant = site.declared_variant ?? site.suggested_variant;
  if (variant !== null) {
    facts.push({
      key: "variant",
      text: `${site.declared_variant !== null ? "declared" : "suggested"} ${variant}`,
      title:
        site.declared_variant !== null
          ? "The variant declared for this site. Declare is where it is changed."
          : "The variant registration suggested for this site — a proposal, not a declaration.",
    });
  }
  const proposal = (detail.detection?.proposals ?? []).find(
    (p) => p.tooth_guess === site.tooth,
  );
  if (proposal !== undefined) {
    facts.push({
      key: "recess",
      text: `recess void ${proposal.void_ratio.toFixed(2)}`,
      title:
        "Screw-recess evidence: the share of the cap's core with no scan in it. Real caps " +
        "measured 0.37–0.62 on the client's two arches; a palate slope measured 0.79.",
    });
    facts.push({
      key: "rim",
      text: `rim ${proposal.rim_below_cusps_mm.toFixed(2)}mm below cusps`,
      title:
        "How far this rim sits under the neighbouring cusps. Caps measured 0.0–0.66mm " +
        "across the client's two arches; the worst tissue artifacts 0.79–1.9mm.",
    });
  }
  return facts;
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
 * is what is chosen). Unchanged fields carry the BFF's EFFECTIVE values (client
 * 2026-07-27: the chosen-??-suggested-??-default derivation has ONE home, server-
 * side; this panel renders those values, so it submits exactly what it shows).
 * The pre-fill only ever leaves this app inside an operator-initiated PUT — one
 * change makes the whole panel an explicit act, which is exactly the demo's
 * send-it-back-explicitly contract — and the BFF's reset guard judges the change
 * over the same effective document, so pinning a prefill destroys no preview.
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
        : chosen.effective_construction.value,
    jaw: patch.jaw !== undefined ? patch.jaw : chosen.effective_jaw.value,
    gingival_offset_mm:
      patch.gingival_offset_mm !== undefined
        ? patch.gingival_offset_mm
        : chosen.effective_relief.value,
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
