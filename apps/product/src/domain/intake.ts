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
  // SITES FIRST, AT THE CENTRE THEY ACTUALLY STAND ON (client 2026-08-01). This
  // used to draw every PROPOSAL and fall back to the site only where no proposal
  // guessed its tooth — so after the operator re-marked a bad detector centre, the
  // stage kept ringing the detector's point while the server, the run and the
  // invoice all stood on the correction. SiteView.center is already the server's
  // own precedence (the operator's mark, else the case record): the stage must
  // draw what the run will use, or the picture disagrees with the physics.
  const markers: SiteMarker[] = [];
  const siteTeeth = new Set(detail.sites.map((s) => s.tooth));
  for (const site of detail.sites) {
    const center = asVec3(site.center);
    if (center !== null) markers.push({ center, radiusMm: MARKER_RADIUS_MM });
  }
  // Proposals no site has claimed ring ONLY when the capture gate's own verdict is
  // "pass" (client 2026-08-01: "just mark when you are highly confident" — said over
  // a stage ringing three candidates the gate itself had judged RESCAN). The word is
  // the server's calibrated capture verdict, never a threshold invented here, and
  // absence of a verdict is absence of confidence, not a pass. The quieter
  // candidates are still named by the unassigned-proposals panel line, and the
  // missed-cap door still lets the operator mark any cap by eye.
  const proposals: readonly DetectedProposalView[] = detail.detection?.proposals ?? [];
  for (const p of proposals) {
    if (p.tooth_guess !== null && siteTeeth.has(p.tooth_guess)) continue;
    if (p.capture?.verdict !== "pass") continue;
    const center = asVec3(p.center);
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
/**
 * AN ARMED CLICK THAT LANDED OFF THE SCAN (client 2026-08-01: "buttons are not
 * working"). Until this existed the click vanished silently — the pick stayed armed
 * with the orbit controls disabled and no message, so the stage read as dead. The
 * pick STAYS armed (a miss is an attempt, not a cancellation), and this sentence
 * says what to do instead.
 */
export const OFF_SCAN_MISS_WORDS =
  "That click landed off the scan — click the scan surface itself. " +
  "Still armed: try again, or cancel.";

export const SITE_PICK_RADIUS_MM = 6.0;

/** What one click on the scan resolved to. `ambiguous` carries the teeth in reach,
 *  nearest first, so the surface can name them in the order the operator would look. */
export type SitePick =
  | { readonly kind: "site"; readonly tooth: number }
  | { readonly kind: "miss" }
  | { readonly kind: "ambiguous"; readonly teeth: readonly number[] };

/**
 * THE CENTRE ON SCREEN IS NOT ALWAYS THE ONE THE DETECTOR MEASURED (client 2026-08-01:
 * "centre is wrong from the beginning").
 *
 * `SiteView.center` prefers the operator's mark, then the CASE'S CURATED centre
 * (bff/resources/case_sessions.py) — the live detector's proposal is not in that chain
 * at all. On the fleet's labelled arches the curated centre is a FROZEN COPY of an old
 * proposal (cap7030's own sites.json says so: "centre = top proposal"), and the
 * detector has moved since: measured 2026-08-01 on cap7030 tooth 29, the curated seed
 * sits 1.739mm from the cap's shipped axis while today's detector proposes 0.253mm —
 * seven times closer. The operator is shown the stale one, on a cap of radius 3.25mm,
 * which is exactly the visibly off-centre marker they reported.
 *
 * THIS ONLY DISCLOSES. It does not re-centre anything: a centre is one measurement
 * owned at its source, and five attempts at backend self-correction broke calibrated
 * contracts (the re-click pair-integrity record). The operator already has the act —
 * "Re-mark this cap's centre" — and what they were missing is the reason to use it.
 *
 * THE BOUND is the fleet's measured operator click scatter, p90 0.61mm (the same
 * figure `MIN_SPAN_MM` is derived from in the worker's adjust module). Below it the two
 * centres differ by less than one click's own noise and there is nothing to say.
 */
export const CENTRE_DISAGREEMENT_MM = 0.61;

export function detectorDisagreement(
  detail: CaseSessionDetail,
  tooth: number,
): { readonly mm: number; readonly detected: readonly number[] } | null {
  const site = detail.sites.find((s) => s.tooth === tooth);
  const shown = site ? siteCentre(site) : null;
  if (shown === null) return null;
  let best: { mm: number; detected: readonly number[] } | null = null;
  for (const proposal of detail.detection?.proposals ?? []) {
    const centre = asVec3(proposal.center);
    if (centre === null) continue;
    const mm = Math.hypot(
      centre[0] - shown[0],
      centre[1] - shown[1],
      centre[2] - shown[2],
    );
    if (best === null || mm < best.mm) best = { mm, detected: centre };
  }
  if (best === null || best.mm <= CENTRE_DISAGREEMENT_MM) return null;
  return best;
}

/**
 * SHOULD THE SITE PICKER BE OFFERED AT ALL (client 2026-08-01: "this button does
 * nothing")?
 *
 * It did do something — it armed a pick. But a pick resolves to one of the sites it
 * can reach, so on a case with a single pickable site its only possible outcome was
 * re-selecting the site already selected. The operator armed a mode, clicked, and
 * watched nothing change; a control that cannot change anything reads as broken, and
 * being told WHY costs one sentence.
 *
 * The count is of sites a click could actually RESOLVE to — `pickSiteAt` skips any
 * site without a usable centre, so a site with no centre is not a candidate however
 * it renders in the list.
 */
export function sitePickerOffered(
  sites: readonly SiteView[],
): { readonly offered: boolean; readonly why: string | null } {
  const pickable = sites.filter((site) => siteCentre(site) !== null).length;
  if (pickable === 0) {
    return {
      offered: false,
      why: "No site on this case carries a centre yet, so there is nothing on the scan to pick.",
    };
  }
  if (pickable === 1) {
    return {
      offered: false,
      why: "This case has only one site with a centre — it is already the active one, so there is nothing to pick between.",
    };
  }
  return { offered: true, why: null };
}

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
 * RE-MARKING AN EXISTING SITE'S CENTRE (client 2026-08-01, the tooth-29 gap: the
 * detector's proposed centre sat visibly off the cap on case cap6020-neodent-gm,
 * and the operator had no door to correct it). `post_marked_site`'s own words
 * named the reason a re-mark refused there — "a different act with different
 * consequences" — without building the act; `PUT .../sites/{tooth}/mark` is that
 * act, and THE BLAST RADIUS MUST BE SAID BEFORE THE CLICK IS ARMED, the same
 * visible-reset doctrine `declare.switchWords` already carries for a system
 * switch: a control that arms first and explains the reset only after the point
 * lands has already spent the operator's undo.
 */

/**
 * Whether re-marking THIS site's centre would retire anything the BFF's boundary
 * (`put_remarked_site`) actually retires: a preview or review past DECLARED (the
 * physics derived from the OLD centre), or a run standing over the WHOLE case —
 * the run is cropped around every site's centre at once, so it falls the instant
 * ANY site's centre moves, even one that itself never previewed. A site still at
 * detected/declared with no case run has nothing to retire; asking there would be
 * the checkbox-over-nothing `DeclareStage.handleAskSwitch` already refuses to ask
 * for a system switch that resets zero declarations.
 */
export function remarkRetiresSomething(
  site: SiteView,
  detail: CaseSessionDetail,
): boolean {
  const pastDeclared = site.status !== "detected" && site.status !== "declared";
  return pastDeclared || detail.session.run_state !== "none";
}

/**
 * THE VISIBLE-RESET WORDS (`declare.switchWords`'s pattern, mirrored): named
 * consequences, said before the pick is armed. "Anything signed over it" is
 * deliberate and exact, not loose scare language — `put_remarked_site` is the one
 * reset boundary in this app that ALSO retires a standing confirmation (the three
 * siblings — choices, system, declaration — leave it standing, protected by a
 * gate instead), precisely so this sentence can be kept literally rather than
 * merely become true three requests later behind a refusal nobody was shown.
 */
export function remarkWords(tooth: number): string {
  return (
    `Re-marking tooth ${tooth}'s centre retires this site's preview and review, ` +
    `the current run and anything signed over it — the run was cropped around ` +
    `the centre you are about to move.`
  );
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
 * a string path_id cannot be chosen and is dropped rather than rendered as a lie.
 *
 * `vendor` rides along (worker's `construction_entries`: every row is
 * `{vendor, filename, path_id, label}`) — ADDITIVE (client 2026-08-01, Deliver's own
 * copy of this picker groups by vendor); Intake's flat `<select>` ignores the extra
 * field, so this stays the one catalog reader both surfaces share. */
export function constructionOptions(
  detail: CaseSessionDetail,
): readonly { readonly path_id: string; readonly label: string; readonly vendor: string }[] {
  return detail.catalog.constructions.flatMap((row) => {
    const path = row["path_id"];
    if (typeof path !== "string") return [];
    const label = row["label"];
    const vendor = row["vendor"];
    return [
      {
        path_id: path,
        label: typeof label === "string" ? label : path,
        vendor: typeof vendor === "string" ? vendor : "unknown vendor",
      },
    ];
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
    // THE TURNAROUND RIDES TOO. This is a PUT of the whole panel, and the wire type
    // says so in as many words: "a panel that renders the turnaround chips must submit
    // the field on EVERY choices write, or the next write un-chooses it back to the
    // standing default". Omitting it here while LibraryStage's own write preserves it
    // made two surfaces disagree about one field — an Intake choice would have quietly
    // reverted a rush to standard. Latent only because no control sets a rush yet; the
    // field is money-adjacent, so it is carried now rather than when the chips land.
    // The RAW act is the right source: `turnaround` is what the operator chose, where
    // `effective_turnaround` folds in a default this write must not promote to a choice.
    turnaround:
      patch.turnaround !== undefined ? patch.turnaround : (chosen.turnaround ?? null),
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
