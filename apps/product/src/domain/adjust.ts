/**
 * ADJUST'S PURE RULES (plan §4 Adjust, §5; slice 6) — the flagged-site rework surface's
 * display logic, framework-free and unit-pinned.
 *
 * Direction of trust (AM-4), unchanged and load-bearing here more than anywhere: every
 * millimetre, every gate verdict and every refusal sentence comes from the worker
 * through the BFF. This module decides ORDER (flagged first), WORDS THAT ARE OURS (the
 * pane notices, the tool labels, what a half-built pair still needs) and NARROWING (the
 * one structured refusal the surface must render differently). It computes no geometry
 * and paraphrases no gate: a reason shown beside a flagged site is the gate's own
 * action text, passed through.
 */
import type {
  AdjustOutcomeView,
  AdjustResultView,
  ApiResult,
  CorrespondencePairBody,
  LandmarkView,
  SitePreviewPayload,
  SiteStatus,
  SiteView,
} from "../api/client";

// --- the toolbox ---------------------------------------------------------------------

export type AdjustToolId =
  | "fit-by-points"
  | "best-fit"
  | "rotation"
  | "mark-trench"
  | "auto-mark";

export interface AdjustToolInfo {
  readonly id: AdjustToolId;
  readonly label: string;
  /** One line: what this tool does, in the operator's language, not the gate's. */
  readonly oneLiner: string;
}

/** The five tools in the plan's own order — fit by points, best fit, rotation dial,
 * mark trench, auto-mark. One is visible at a time; the others are one click away. */
export const ADJUST_TOOLS: readonly AdjustToolInfo[] = [
  {
    id: "fit-by-points",
    label: "Fit by points",
    oneLiner:
      "Mark a spot on the library part and the same spot on the scan. Two clicks " +
      "spanning a feature beat one guess at its centre.",
  },
  {
    id: "best-fit",
    label: "Best fit",
    oneLiner:
      "Re-run the pipeline's own refinement at a matching diameter you choose. " +
      "Nothing to correct is a PASS, not a failure.",
  },
  {
    id: "rotation",
    label: "Rotation",
    oneLiner:
      "Step the cap about its own axis, read against the coded cutout. Reset " +
      "restores the alignment the automation certified.",
  },
  {
    id: "mark-trench",
    label: "Mark trench",
    oneLiner:
      "Click the coded trench on the scan; the cap turns so its nearest code " +
      "feature lands there.",
  },
  {
    id: "auto-mark",
    label: "Auto-mark",
    oneLiner:
      "The software marks the points on the library part — you match the same spot " +
      "on the scan, in order. Every proposed point already has a valid lever arm.",
  },
];

/** server.py:1268 → the BFF's RotationIn, mirrored here so the dial cannot offer a
 * step the server would refuse. The presets are the demo's own coarse/fine feel. */
export const MAX_STEP_DEG = 45;
export const ROTATION_STEPS: readonly number[] = [-15, -5, -1, 1, 5, 15];

/** server.py:1768 → the BFF's FitByPointsIn: at most eight pairs. */
export const MAX_PAIRS = 8;

/** The best-fit dial's band (server.py:2012-2017 → the BFF's BestFitIn). The default
 * is the demo's own 0.3mm: a final polish, not a re-seat. */
export const MIN_DIAMETER_MM = 0.05;
export const MAX_DIAMETER_MM = 2.0;
export const DEFAULT_DIAMETER_MM = 0.3;

/**
 * THE DIAL'S BOUNDS, SAID OUT LOUD (design review 2026-07-31). The band was carried
 * only by the input's min/max attributes: an operator learned the ceiling by typing
 * past it and watching the field argue back, and learned the default by never having
 * touched it.
 *
 * The design's companion sentence — "the rim reads about X mm, this dial is Y off it"
 * — is deliberately NOT ported. It reads the prototype's invented `site.diamTrue`;
 * the product's nearest field, `SiteView.rim_agreement_mm`, measures how well the rim
 * agreed at the seat, which is a different quantity. Synthesising the comparison
 * client-side would be this app inventing a measurement (AM-4), so the words state
 * only what the constants above already are, and a server field would have to be
 * specified before the richer note can exist.
 */
export function diameterBandWords(): string {
  return (
    `The dial spans ${MIN_DIAMETER_MM.toFixed(2)}–${MAX_DIAMETER_MM.toFixed(2)} mm; ` +
    `${DEFAULT_DIAMETER_MM.toFixed(2)} mm is the polish the run itself used.`
  );
}

// --- the flagged-first queue -----------------------------------------------------------

/** One row of Adjust's site queue. `optional` is the honest half of the plan's "clean
 * sites below, visibly optional": they can be reworked, and nothing says they should
 * be. `reasons` are the GATE'S OWN action words from the run row — never our summary
 * of them, because the operator is about to act on what they say. */
export interface AdjustQueueEntry {
  readonly tooth: number;
  readonly status: SiteStatus;
  readonly flagged: boolean;
  readonly optional: boolean;
  /** The operator's standing WITHHOLD INTENT for this site, from the BFF
   * (`SiteView.withhold_intent`) — never derived here. A dropped cap sinks to the
   * bottom of the queue and keeps its verdict: dropping changes what SHIPS, never
   * what was measured. */
  readonly dropped: boolean;
  readonly declaredVariant: string | null;
  readonly reasons: readonly string[];
}

/** The gate's own action words for one run row (worker `guidance.actions`), passed
 * through. A row with no words yields none — an empty list is honest; an invented
 * sentence would not be. */
export function gateActions(row: Record<string, unknown> | undefined): readonly string[] {
  const guidance = row?.["guidance"];
  if (typeof guidance !== "object" || guidance === null) return [];
  const actions = (guidance as Record<string, unknown>)["actions"];
  if (!Array.isArray(actions)) return [];
  return actions.filter((a): a is string => typeof a === "string");
}

function rowFor(
  rows: ReadonlyArray<Record<string, unknown>>,
  tooth: number,
): Record<string, unknown> | undefined {
  return rows.find((r) => r["tooth"] === tooth);
}

/**
 * THE QUEUE, FLAGGED FIRST (plan §4 Adjust): flagged sites at the top with the gate's
 * reason; everything else below, visibly optional. Within each group the order is by
 * tooth, so the list is stable across reloads — a queue that reshuffles under the
 * operator is a queue they stop trusting.
 *
 * Sites the run never aligned are DROPPED: the tools refuse them server-side (there is
 * no fit to rework), and listing a row that can only refuse is a promise to nowhere —
 * the exact thing this whole stage exists to stop doing.
 *
 * A CAP THE OPERATOR DROPPED SINKS TO THE BOTTOM (design 1178) and is the one thing
 * that outranks the flagged-first rule: it is the row they have already finished
 * with. It is NOT hidden and it keeps its verdict — bringing it back must cost no
 * re-read of why it was flagged in the first place.
 */
export function adjustQueue(
  sites: readonly SiteView[],
  rows: ReadonlyArray<Record<string, unknown>>,
): readonly AdjustQueueEntry[] {
  const entries = sites
    .filter((site) => rowFor(rows, site.tooth) !== undefined)
    .map((site) => ({
      tooth: site.tooth,
      status: site.status,
      flagged: site.status === "flagged",
      optional: site.status !== "flagged",
      // the BFF's own field, passed through — this app derives no disposition
      dropped: site.withhold_intent === true,
      declaredVariant: site.declared_variant,
      reasons: gateActions(rowFor(rows, site.tooth)),
    }));
  return [...entries].sort((a, b) => {
    if (a.dropped !== b.dropped) return a.dropped ? 1 : -1;
    if (a.flagged !== b.flagged) return a.flagged ? -1 : 1;
    return a.tooth - b.tooth;
  });
}

/** The queue's one-line header — what the operator is looking at before they read a
 * single row. Counts only: the rows carry the reasons. */
export function queueSummary(entries: readonly AdjustQueueEntry[]): string {
  const dropped = entries.filter((e) => e.dropped).length;
  // a dropped cap is out of the WORK, so it is out of the work's counts — counting
  // it as flagged would keep asking for a rework the operator has already declined
  const live = entries.filter((e) => !e.dropped);
  const flagged = live.filter((e) => e.flagged).length;
  const tail = dropped === 0 ? "" : ` ${dropped} dropped.`;
  if (entries.length === 0) {
    return "No aligned sites on this run — there is nothing to rework.";
  }
  if (live.length === 0) {
    return "Every site on this run is dropped — nothing here releases or bills.";
  }
  if (flagged === 0) {
    return `Nothing is flagged. All ${live.length} site${
      live.length === 1 ? "" : "s"
    } passed their gates — reworking one is optional.${tail}`;
  }
  return `${flagged} of ${live.length} site${live.length === 1 ? "" : "s"} ${
    flagged === 1 ? "is" : "are"
  } flagged — those come first.${tail}`;
}

// --- dropping a cap (design flow.dc.html dropSite 1345-1354, queue row 1183-1191) -------
//
// THE DESIGN'S OWN WORDS ARE HALF WRONG HERE and it is worth saying why, because they
// are otherwise the words to copy. Its button reads "drop this cap — don't align or
// bill it" and its queue row "dropped — not aligned, not billed". On this stage the
// alignment has ALREADY RUN: the operator is standing in front of the shipped pose.
// The product's act deliberately does not touch the pipeline either (skipping the
// physics would make the decision irreversible without a re-run). So every sentence
// below states the half that is true — nothing releases for it, and it is not billed —
// and none of them claims anything about what was measured.
//
// NOTHING HERE IS A VERDICT. The act is the BFF's per-site withhold INTENT, which
// pre-fills the confirmation's disposition; the confirmation at Deliver is what signs
// it. These functions name what the operator DOES, never what the site IS.

/** The act's label, both directions — the reversal is a first-class control, not a
 * hidden undo (design 1345: "bring this cap back into the case"). */
export function dropLabel(dropped: boolean): string {
  return dropped
    ? "Bring this cap back into the case"
    : "Drop this cap — hold it back from the release and the bill";
}

/** The standing explanation beside the control: what the act does, and who signs it. */
export function dropNote(dropped: boolean): string {
  return dropped
    ? "This cap is held back: no construction releases for it and it is not billed. " +
        "It is a draft — the confirmation at Deliver is what signs it, and bringing " +
        "the cap back before then puts it straight back in."
    : "Dropping a cap holds it back from the release and the bill. It stays on this " +
        "queue with its verdict, and the drop can be undone here at any time.";
}

/** The dropped row's own line in the queue, in place of the flag/optional line. */
export function droppedRowWords(): string {
  return "dropped — nothing is released for it, and it is not billed";
}

// --- the panes' words on this stage ------------------------------------------------------

/** The seated read's lifecycle as the union pane sees it. */
export type SeatedPhase = "idle" | "loading" | "ready" | "error";

export interface AdjustNoticeInputs {
  readonly site: AdjustQueueEntry | null;
  readonly partMeshKnown: boolean;
  readonly partError: string | null;
  readonly scanError: string | null;
  readonly scanEmpty: boolean;
  readonly seatedPhase: SeatedPhase;
  readonly seatedError: string | null;
}

export interface AdjustNotices {
  readonly part: string | null;
  readonly scan: string | null;
  readonly union: string | null;
}

/**
 * THE HONEST WORDS over an empty pane, in ADJUST's voice. Declare's notices talk about
 * a preview that has not run; here the subject is the SHIPPED fit, and a pane with
 * nothing to show says which of the three things is missing. Order matters: the first
 * true reason is the actionable one.
 */
export function adjustPaneNotices(inputs: AdjustNoticeInputs): AdjustNotices {
  const noSite =
    inputs.site === null
      ? "No site selected — pick one from the queue to work on it."
      : null;
  const part = (() => {
    if (noSite) return noSite;
    if (inputs.partError) return inputs.partError;
    if (!inputs.partMeshKnown) {
      return "The catalog carries no mesh for this site's declared part.";
    }
    return null;
  })();
  const scan = (() => {
    if (inputs.scanError) return inputs.scanError;
    if (noSite) return noSite;
    if (inputs.scanEmpty) return "No scan surface near this site's centre.";
    return null;
  })();
  const union = (() => {
    if (noSite) return noSite;
    if (inputs.seatedPhase === "error") {
      return inputs.seatedError ?? "The shipped fit could not be read.";
    }
    if (inputs.seatedPhase === "idle") {
      return "The shipped fit has not been read for this site yet.";
    }
    return null; // loading = the busy state; ready = the colouring itself
  })();
  return { part, scan, union };
}

/**
 * WHOSE colouring is on screen — Adjust's half of the sentence Declare's preview
 * caption states. A preview and a shipped read look identical and mean different
 * things, and after a tool lands the operator needs to know they are looking at the
 * NEW pose, not the one they just moved away from.
 */
export function adjustUnionCaption(
  payload: SitePreviewPayload | null,
  lastOutcome: AdjustOutcomeView | null,
): string | null {
  if (payload === null) return null;
  if (lastOutcome !== null && lastOutcome.applied) {
    return `the fit as it stands now — ${lastOutcome.detail}`;
  }
  return "the fit as the run delivered it — no operator adjustment on this site yet";
}

// --- the one structured refusal ------------------------------------------------------------

/** The best-fit's already-optimal outcome: a refusal by status, a PASS by meaning. */
export interface AlreadyOptimal {
  readonly message: string;
  readonly matchingDiameterMm: number;
  readonly suggestedDiameterMm: number;
  /** False at the operator ceiling, where the doubled suggestion caps to the dial
   * itself: offering a "widen" that re-runs the identical search is the loop the demo
   * shipped once and had to take back. */
  readonly canWiden: boolean;
}

/**
 * Narrow the BFF's structured 409 (bff/resources/adjust._refuse). Anything else — a
 * sentence, a pydantic row list, a transport failure — returns null and renders as the
 * plain refusal it is.
 */
export function alreadyOptimalFrom(
  result: ApiResult<AdjustResultView>,
): AlreadyOptimal | null {
  if (result.kind !== "error" || result.status !== 409) return null;
  const refusal = result.refusal;
  if (typeof refusal !== "object" || refusal === null) return null;
  const body = refusal as Record<string, unknown>;
  if (body["kind"] !== "already_optimal") return null;
  const message = body["message"];
  const dial = body["matching_diameter_mm"];
  const suggested = body["suggested_diameter_mm"];
  if (typeof message !== "string" || typeof dial !== "number" ||
      typeof suggested !== "number") {
    return null;
  }
  return {
    message,
    matchingDiameterMm: dial,
    suggestedDiameterMm: suggested,
    canWiden: suggested > dial,
  };
}

// --- fit by points: the drafts the operator builds ----------------------------------------

/** Which half of a pair the next click fills. */
export type PairSlot = "part" | "scan" | "scan-end" | "complete";

/**
 * One correspondence the operator is building. The PART half is a free canonical-frame
 * click on pane 1 (the wire also accepts a named `feature_id`; the surface offers free
 * points because that is what the client asked for on 2026-07-26 — catalogs whose
 * detector reads a single rotation-defining feature stranded them at one pair — and
 * because the product has no part-annotation read yet).
 *
 * `span` is the client's TWO-POINT ask: both ENDS of the feature instead of a guess at
 * its centre. The midpoint averages the click noise; the direction is a second
 * observation. Whether the direction actually counts is the worker's call, not this
 * surface's — a chordal span's midpoint still counts and its direction is dropped with
 * the reason stated.
 */
export interface PairDraft {
  readonly id: string;
  readonly span: boolean;
  readonly partPoint: readonly number[] | null;
  readonly scanPoint: readonly number[] | null;
  readonly scanPointEnd: readonly number[] | null;
}

export function newPairDraft(id: string, span: boolean): PairDraft {
  return { id, span, partPoint: null, scanPoint: null, scanPointEnd: null };
}

/** What this draft still needs — the surface's prompt, and the pick router's target. */
export function pairSlot(draft: PairDraft): PairSlot {
  if (draft.partPoint === null) return "part";
  if (draft.scanPoint === null) return "scan";
  if (draft.span && draft.scanPointEnd === null) return "scan-end";
  return "complete";
}

/** The prompt beside the marks — one sentence naming exactly the next click. */
export function pairPrompt(draft: PairDraft | null): string {
  if (draft === null) return "Start a pair to place marks.";
  switch (pairSlot(draft)) {
    case "part":
      return "Click the feature on the LIBRARY PART (pane 1).";
    case "scan":
      return draft.span
        ? "Click ONE END of that feature on the scan (pane 2 or 3)."
        : "Click the same spot on the SCAN (pane 2 or 3).";
    case "scan-end":
      return "Click the OTHER END of the feature on the scan.";
    case "complete":
      return "This pair is complete — add another, or apply the fit.";
  }
}

export function isComplete(draft: PairDraft): boolean {
  return pairSlot(draft) === "complete";
}

/** Record a click into the draft's next empty slot. A click on a pane the draft is not
 * waiting for is IGNORED rather than overwriting a placed mark: the re-click
 * pair-integrity record — an operator act is never silently replaced. */
export function withPick(
  draft: PairDraft,
  pane: "part" | "scan",
  point: readonly number[],
): PairDraft {
  const slot = pairSlot(draft);
  if (pane === "part" && slot === "part") return { ...draft, partPoint: [...point] };
  if (pane === "scan" && slot === "scan") return { ...draft, scanPoint: [...point] };
  if (pane === "scan" && slot === "scan-end") {
    return { ...draft, scanPointEnd: [...point] };
  }
  return draft;
}

/** The wire body for one COMPLETE draft. Incomplete drafts are never sent — the apply
 * control refuses first, naming what is missing. */
export function pairBody(draft: PairDraft): CorrespondencePairBody {
  const body: CorrespondencePairBody = {
    part_point: [...(draft.partPoint ?? [])],
    scan_point: [...(draft.scanPoint ?? [])],
  };
  if (draft.span && draft.scanPointEnd !== null) {
    return { ...body, scan_point_end: [...draft.scanPointEnd] };
  }
  return body;
}

/** Why the Apply control is inert, or null when it is live. Never a bare "disabled":
 * the blockedReason doctrine — a surface that cannot act says exactly what is
 * holding it. */
/**
 * `pose` and `clock` are REQUIRED though both are nullable (review 2026-08-01). As
 * optional trailing params they type-checked when omitted and silently returned a live
 * Apply into a guaranteed 422 — the same silent-loss shape the BFF passthrough tests
 * exist to close. Null is a claim ("no reference in hand"); absence was an oversight,
 * and the type system can tell them apart.
 */
export function applyBlockedReason(
  drafts: readonly PairDraft[],
  pose: { readonly origin: readonly number[]; readonly axis: readonly number[] } | null,
  clock: ClockReferenceLike | null,
): string | null {
  const complete = drafts.filter(isComplete);
  if (complete.length === 0) {
    return "Place at least one complete pair — a spot on the part and where you see it on the scan.";
  }
  if (complete.length > MAX_PAIRS) {
    return `A correspondence is capped at ${MAX_PAIRS} pairs — remove ${
      complete.length - MAX_PAIRS
    }.`;
  }
  // THE LOCAL PRE-REFUSAL (client 2026-07-29). Only a `refusal` blocks: it is the
  // SERVER'S OWN quantity against the SERVER'S OWN bound, so a mark that fails it is
  // one the round trip would refuse anyway. A `caution` is the old approximation and
  // must never make this control inert — see `markLeverGuard`.
  for (const [index, draft] of complete.entries()) {
    const guard = markLeverGuard(draft, pose, clock);
    // NAME WHICH PAIR, like the worker's own refusal does. A blocked control that
    // describes the fault but not its owner leaves the operator hunting for which of
    // the marks on screen it means — the per-draft notice makes it discoverable, this
    // makes it addressable. Position in the SET, matching the slot labels.
    if (guard !== null && guard.kind === "refusal") {
      return `Pair ${index + 1}: ${guard.message}`;
    }
  }
  return null;
}

/**
 * THE SET'S OWN OVERVIEW — how many pairs stand, and the ceiling, BEFORE it is hit
 * (design review 2026-07-31). `MAX_PAIRS` surfaced only through `applyBlockedReason`,
 * which speaks once the cap is already exceeded: the operator met the limit by being
 * told to undo work they had just done. A ceiling is cheap to state in advance and
 * expensive to discover.
 *
 * "One complete pair is enough" is the same fact `applyBlockedReason` refuses on,
 * stated from the other side — the floor and the ceiling in one line.
 */
export function pairSetWords(drafts: readonly PairDraft[]): string {
  const complete = drafts.filter(isComplete).length;
  const open = drafts.length - complete;
  if (drafts.length === 0) {
    return (
      `No pairs placed yet — ${MAX_PAIRS} at most, and one complete pair is enough ` +
      `to apply.`
    );
  }
  const counted = `${complete} of ${MAX_PAIRS} pairs complete`;
  const half = open > 0 ? `, ${open} still being placed` : "";
  if (complete >= MAX_PAIRS) {
    return `${counted}${half} — that is the cap; remove one before placing another.`;
  }
  return `${counted}${half}.`;
}

/**
 * THE VACUOUS RMS, SAID BEFORE THE CLICK (defect cap6020-neodent-gm, 2026-08-01).
 *
 * A fit built from ONE observation is exactly determined for rotation: that single
 * delta IS the answer and its residual is zero by construction. The outcome used to
 * report that zero as "marks agree to 0.000mm RMS" — a quality number where no quality
 * number can exist — and a real case took a −50.9° rotation off a clean run on the
 * strength of it. The server no longer says that. This says it one act EARLIER, so the
 * choice is informed rather than discovered.
 *
 * A CAUTION, NEVER A BLOCKER. The worker deliberately allows one correspondence and
 * `applyBlockedReason` deliberately refuses at zero, not at one: a single pair is the
 * documented answer where the automatic reader has no evidence at all, and removing the
 * capability is not the fix. So this returns words and touches no control.
 *
 * IT PREDICTS NO VERDICT. Whether the fit really lands on one observation is the
 * server's to say — a two-point SPAN emits its direction only where the server reads it
 * as radial, and a chord across the feature contributes its midpoint alone. So the span
 * branch states the CONDITION rather than either answer, and the fact that decides it
 * arrives afterwards on `AdjustOutcomeView.cross_checked`, derived server-side.
 */
export function crossCheckCaution(drafts: readonly PairDraft[]): string | null {
  const complete = drafts.filter(isComplete);
  if (complete.length !== 1) return null;
  const only = complete[0]!;
  if (only.span) {
    return (
      "One pair only. This span counts as two observations only where the server " +
      "reads it as radial; a chord across the feature contributes its midpoint " +
      "alone, and then this fit stands on a single observation — the rotation is " +
      "fixed exactly, nothing disagrees with it, and no agreement number exists. " +
      "That is a legitimate fit where the automatic reader has no evidence. Place a " +
      "second pair if you want the rotation cross-checked."
    );
  }
  return (
    "One pair only — one observation. It fixes the rotation exactly, so there is " +
    "nothing to cross-check it against and the fit reports no agreement number: if " +
    "this mark is on the wrong feature, the cap turns by whatever it says and no " +
    "number here can tell. That is a legitimate fit where the automatic reader has " +
    "no evidence. Place a second pair elsewhere on the cap to get a residual you " +
    "can read."
  );
}

// --- auto-mark: the software proposes the part half (client 2026-07-29, item 3) ------
//
// "We also need another tool where we automatically mark the points in the library and
// the client has to match the same points on the scan." The worker already offers this
// read (GET .../sites/{tooth}/landmarks → `clock_landmarks`, best lever arm first,
// filtered to features that pass `PartFeature.defines_rotation`) — this half turns each
// proposed landmark into a PairDraft whose PART half is already filled, reusing every
// existing pair mechanic (`withPick`, `pairSlot`, `pairPrompt`, `pairBody`,
// `applyBlockedReason`) rather than inventing a second one.
//
// THIS STRUCTURALLY PREVENTS THE SCAN-SIDE LEVER REFUSAL (the worker's
// `require_clock_lever`, the guard `spanLeverCaution` above can only WARN about for a
// free click): every proposed point already passed `PartFeature.defines_rotation`, so
// its lever arm can never be inside the axis. A pair built on a served landmark cannot
// become the diametral span across the screw access that guard exists to catch — not
// because the operator was careful, but because no landmark offered here could ever
// seed one. The operator's whole remaining job is finding the SAME feature in a noisy
// scan: the one half only a human can do.

/**
 * One draft per proposed landmark, the part half already filled from the worker's own
 * feature geometry — in the part's CANONICAL frame, the same frame a pane-1 click would
 * produce (`clock_landmarks`' own contract). `pairSlot` therefore reads these drafts as
 * already past "part" the moment they exist: the operator's next click is always the
 * scan half, in the SAME order the landmarks were served (best lever arm first).
 */
export function autoMarkDrafts(landmarks: readonly LandmarkView[]): PairDraft[] {
  return landmarks.map((landmark) => ({
    id: `auto-${landmark.id}`,
    span: false,
    partPoint: [...landmark.point],
    scanPoint: null,
    scanPointEnd: null,
  }));
}

/** One proposed landmark's own identity, in words — WHAT it is and how far out on the
 * part it sits, so the operator knows why this is the one being asked for. */
export function landmarkLabel(landmark: LandmarkView): string {
  return `${landmark.kind} — lever arm ${landmark.lever_arm_mm.toFixed(2)}mm`;
}

/** Which proposed landmark seeded this draft, in words — null for a draft auto-mark did
 * not create (the fit-by-points flow's own drafts carry no server identity to show, and
 * this must render nothing for them rather than guessing). */
export function autoMarkSourceLabel(
  draft: PairDraft,
  landmarks: readonly LandmarkView[],
): string | null {
  const landmark = landmarks.find((l) => `auto-${l.id}` === draft.id);
  return landmark !== undefined ? landmarkLabel(landmark) : null;
}

/** The auto-mark tool's own header line — a count and the order promise, or the honest
 * word when the declared part carries nothing to propose (a template with no coded
 * relief at all: `clock_landmarks` filters everything out rather than guessing one). */
export function autoMarkSummary(landmarks: readonly LandmarkView[]): string {
  if (landmarks.length === 0) {
    return (
      "This part carries no rotation-defining landmarks to propose — try fit by " +
      "points instead."
    );
  }
  return (
    `${landmarks.length} landmark${landmarks.length === 1 ? "" : "s"} proposed, best ` +
    `lever arm first — match each one on the scan, in the same order they are numbered.`
  );
}

/** One pair's own line in the list: what it is, and what it still needs. */
export function pairWords(draft: PairDraft, index: number): string {
  const name = `${index + 1}. ${draft.span ? "span" : "point"}`;
  switch (pairSlot(draft)) {
    case "part":
      return `${name} — waiting for the part mark`;
    case "scan":
      return `${name} — waiting for the scan mark`;
    case "scan-end":
      return `${name} — waiting for the span's other end`;
    case "complete":
      return draft.span
        ? `${name} — both ends placed`
        : `${name} — placed`;
  }
}

// --- reading what a tool produced -----------------------------------------------------------

/**
 * One observation row's line: WHICH reading it is (a single point, a span's midpoint,
 * a span's direction), how far it missed by at the marked feature's own lever arm, and
 * — when the worker attached one — the sentence the operator is owed about this
 * reading.
 *
 * THE NOTE IS NOT DECORATION (suites 2026-07-28). A chordal span's direction is
 * dropped, and the worker has always written down why; it went to the record on disk
 * and the surface rendered one unexplained row. An operator who spends a second click
 * to buy a rotational constraint and silently receives one observation has been given
 * a no-op with a smile — the exact failure the "never a silent no-op" rule exists to
 * prevent. The sentence is the worker's, passed through (AM-4).
 */
export function observationWords(row: Record<string, unknown>): string {
  const label = typeof row["feature_id"] === "string" ? row["feature_id"] : "mark";
  const kind = typeof row["observation"] === "string" ? row["observation"] : "point";
  const residual = row["residual_mm"];
  const missed =
    typeof residual === "number" ? `misses by ${residual.toFixed(3)} mm` : "no residual";
  const named =
    kind === "midpoint"
      ? "span midpoint"
      : kind === "direction"
        ? "span direction"
        : "point";
  const note = typeof row["note"] === "string" && row["note"].length > 0
    ? ` — ${row["note"]}`
    : "";
  return `${label} · ${named} — ${missed}${note}`;
}

/** The applied tool's headline, from the BFF's own facts. Never our arithmetic: every
 * number here was measured server-side. */
export function outcomeWords(outcome: AdjustOutcomeView): string {
  if (!outcome.applied) return `Measured only — ${outcome.detail}`;
  return outcome.detail;
}

/** Whether this site now needs re-confirming: an applied tool moves the pose the
 * review attested, so the ladder drops it to `adjusted` and the operator must confirm
 * over the NEW panes before Deliver opens again. */
export function needsReconfirm(status: SiteStatus): boolean {
  return status === "adjusted";
}

/**
 * The same rule over the WIRE'S raw status string, with no site selected folded in.
 *
 * The surface carries `activeStatus` as `string | null` (it is the payload's own word,
 * and a rung this app has not met yet must not crash a render), and the only way to
 * reach `needsReconfirm` from there was a `as never` cast at the call site — which
 * type-checks anything, including the omission that hid this control off a fresh
 * outcome (design review 2026-07-31). One narrowing, in the module that owns the rule.
 */
export function needsReconfirmStatus(status: string | null): boolean {
  return status !== null && needsReconfirm(status as SiteStatus);
}

/** The re-confirmation as the surface must render it: whether the act exists at all,
 *  whether it may be performed right now, and — when it may not — why. */
export interface ReconfirmControl {
  readonly offered: boolean;
  readonly enabled: boolean;
  /** Present exactly when the act is offered and refused. */
  readonly reason: string | null;
}

/**
 * THE RUNG OFFERS THE ACT; THE PANES QUALIFY IT (design review 2026-07-31).
 *
 * The control rendered off `needsReconfirmStatus` alone, with no precondition on the
 * evidence being on screen. With the seated read failed — a transport error, a 404 —
 * pane 3 carries "The shipped fit could not be read." (adjustPaneNotices above) while
 * this block said "confirm it again over the panes on the right" beside an ENABLED
 * button: two sentences on one screen contradicting each other. Clicking POSTs /review,
 * flips the rung adjusted→ready and satisfies Deliver's every-site-resolved gate with
 * an attestation whose evidence was never displayed.
 *
 * The wording of the attestation is "over the panes", so the panes are a precondition,
 * not a nicety. Declare's equivalent control has stated a reason when inert since 5b
 * (declare.reviewTick); this is the same discipline on the same act. Under-claiming
 * beats offering an attestation over a blank pane.
 */
export function reconfirmControl(
  status: string | null,
  seatedPhase: SeatedPhase,
  hasPayload: boolean,
): ReconfirmControl {
  const offered = needsReconfirmStatus(status);
  if (!offered) return { offered: false, enabled: false, reason: null };
  if (seatedPhase === "ready" && hasPayload) {
    return { offered: true, enabled: true, reason: null };
  }
  const reason =
    seatedPhase === "error"
      ? "The shipped fit could not be read, so the panes are not showing it — and this " +
        "confirmation attests those panes. Reselect the site to read it again."
      : seatedPhase === "loading"
        ? "Still reading the shipped fit — the panes are not showing it yet."
        : "The shipped fit has not been read for this site yet, so there is nothing on " +
          "the panes to confirm.";
  return { offered: true, enabled: false, reason };
}

/** Which panes want the next click, and what that click will do — one entry per pane,
 *  in SitePanes' own keys (the shape both `armed` and `hints` are passed as). */
export interface PaneArming {
  readonly armed: {
    readonly library: boolean;
    readonly scan: boolean;
    readonly union: boolean;
  };
  readonly hints: {
    readonly library: string | null;
    readonly scan: string | null;
    readonly union: string | null;
  };
}

/** The trench's one sentence, on the glass where the click goes. */
const TRENCH_HINT = "Click the coded cutout — the cap rotates its nearest code feature to it.";

/** What the open draft's next click is, said ON the pane rather than under it. The
 *  toolbox's own prompt names the pane ("pane 2 or 3"); here the pane IS the answer. */
function draftHint(draft: PairDraft): string | null {
  switch (pairSlot(draft)) {
    case "part":
      return "Click the feature on the library part.";
    case "scan":
      return draft.span
        ? "Click ONE END of that feature here."
        : "Click the same spot here.";
    case "scan-end":
      return "Click the OTHER END of the feature here.";
    case "complete":
      return null;
  }
}

/**
 * WHICH PANE IS ARMED (client 2026-07-30; re-opened by the design review 2026-07-31 —
 * the props existed on both SitePanes and VerifyViewer, the CSS existed, and the one
 * stage that installs pick listeners passed neither, so the crosshair and the on-glass
 * hint were dead code for the whole slice).
 *
 * This is exactly AdjustStage.handlePick's routing, read out loud: a scan click is the
 * TRENCH's while the trench is armed, and otherwise fills the open draft's next empty
 * slot. Deriving it from "has a pick listener" instead would arm all three panes for
 * the whole stage — the precise lie the control exists to stop telling — because Adjust
 * installs one router on all three and decides inside it.
 *
 * Both scan panes arm together: the router accepts the scan half from pane 2 or pane 3,
 * and a pane that would accept a click must say so.
 */
export function paneArming(
  openDraft: PairDraft | null,
  trenchArmed: boolean,
): PaneArming {
  const slot = openDraft === null ? null : pairSlot(openDraft);
  const wantsPart = slot === "part";
  const wantsScan = slot === "scan" || slot === "scan-end";
  const hint = openDraft === null ? null : draftHint(openDraft);
  const scanHint = trenchArmed ? TRENCH_HINT : wantsScan ? hint : null;
  return {
    armed: {
      library: wantsPart,
      scan: trenchArmed || wantsScan,
      union: trenchArmed || wantsScan,
    },
    hints: {
      library: wantsPart ? hint : null,
      scan: scanHint,
      union: scanHint,
    },
  };
}

/**
 * DID THIS TOOL MOVE THE RUN'S SUMMARY ROW (design review 2026-07-31)?
 *
 * `adjust._fold_outcome` (bff/resources/adjust.py:324-372) rewrites the row's
 * `clocking`, `deviation_*` and `correspondence` on every applied tool — and nothing in
 * the response moves `run_state`, which is what the container's run-rows effect keys
 * off. So the ALIGNMENT strip kept printing PRE-rework numbers beside an outcome panel
 * describing the new pose: on one screen the rotation tab read the fresh residual
 * (1.2°) and the toolbar's ROTATION cell the stale one (+7.4°), both labelled as the
 * run's. PAIRS was worse — the count was moved server-side precisely so it would
 * survive a reload, and the strip still showed the old one immediately after the
 * operator applied the pairs that produced it.
 *
 * The response cannot simply carry the new row: `_result` builds an AdjustResultView
 * from the OUTCOME, not from the summary row, and the row is a server derivation over
 * more than one act. So the honest signal is "re-read it", and this is the predicate.
 */
export function outcomeMovedTheRow(result: ApiResult<AdjustResultView>): boolean {
  return result.kind === "ok" && result.data.outcome.applied;
}

/**
 * THE OTHER WAY OUT OF A FLAG, POINTED AT — never performed here (design review
 * 2026-07-31; the design's "accept as flagged exception" button, template 1348).
 *
 * Adjust offered five tools and a re-confirmation, all of which mean "rework this
 * until it is not flagged". The product has always had a second answer — a flagged
 * site is a legitimate shipping outcome (deliver.py's `_RESOLVED_RUNGS` carries
 * 'flagged'), released only once the operator acknowledges THAT row on Deliver
 * (AM-12) — and nothing on this stage said so, so the only visible exit from a flag
 * that will not lift was to keep grinding at it.
 *
 * THE ACT IS NOT LIFTED HERE, deliberately. Acknowledgment is row-by-row on Deliver's
 * own table ("a bulk yes-to-all cannot exist on this wire"), it must be made against
 * the evidence the operator is about to sign, and an acknowledgment recorded on Adjust
 * would survive a later rework that moved the very fit it acknowledged. `accepted` is
 * also not a status this app may ever set (AM-4). So this is a POINTER: one sentence,
 * no control, no status.
 */
export function flaggedExceptionWords(status: string | null): string | null {
  if (status !== "flagged") return null;
  return (
    "Reworking is not the only way out. A flagged site can still ship, as an " +
    "acknowledged exception: Deliver refuses to release one without an " +
    "acknowledgment on its own row, and that row is where the act is made — " +
    "nothing on this stage accepts it for you."
  );
}

// --- what a rework leaves behind on the run's report (review 2026-07-28, finding E) ----

/** The wire's metric keys in the reader's language. A key with no phrasing here is
 * passed through rather than dropped: the BFF owns this list, and a name this app has
 * not met yet is still a fact the operator must see. */
const STALE_METRIC_NAMES: Readonly<Record<string, string>> = {
  rim_agreement_mm: "the rim agreement",
  guidance: "the gate verdict",
  deviation_rms_mm: "the deviation RMS",
  deviation_p90_mm: "the deviation p90",
};

/**
 * The run-row numbers a rework could NOT re-derive, named and joined — the ONE
 * vocabulary for this, shared with Deliver (which seals them) so the stage that causes
 * the staleness and the stage that signs it name the same things the same way. Null
 * when nothing is stale, so every caller renders nothing rather than an empty clause.
 */
export function staleMetricsPhrase(keys: readonly string[]): string | null {
  // read defensively, like every other wire narrowing here (gateActions,
  // alreadyOptimalFrom): a BFF that predates this field must render nothing, never
  // throw inside the panel the operator is reading
  if (!Array.isArray(keys) || keys.length === 0) return null;
  const named = keys.map((key) => STALE_METRIC_NAMES[key] ?? key);
  if (named.length === 1) return named[0]!;
  return `${named.slice(0, -1).join(", ")} and ${named[named.length - 1]}`;
}

/**
 * WHAT THE ACT JUST DID TO THE RUN'S REPORT, said at the moment it happens.
 *
 * The tool re-derives the deviation over the new pose; the rim agreement and the gate
 * verdict it cannot, and those are what the operator will meet again on Deliver's
 * table. Saying it here — beside the outcome, not two stages later — is the same rule
 * as every refusal in this surface: the person acting learns the consequence from the
 * act, not from discovering it downstream.
 */
export function reworkWords(outcome: AdjustOutcomeView): string | null {
  if (!outcome.applied) return null;
  const named = staleMetricsPhrase(outcome.stale_metrics);
  if (named === null) return null;
  return (
    `The run's report still carries ${named} from before this change — Deliver ` +
    `marks them as predating the rework, and the next full run re-measures them.`
  );
}

/** One of the marks a pair is made of, with where it goes and whether it is placed. */
export interface PairSlotView {
  readonly key: PairSlot;
  /** WHICH surface this mark belongs on — the thing the operator kept having to guess. */
  readonly where: string;
  readonly label: string;
  readonly placed: boolean;
  /** True for the slot the NEXT click fills. */
  readonly active: boolean;
}

/**
 * A pair, broken into the marks it is actually made of (client 2026-07-29: "the match by
 * points need to mark which points (2 points) we want to mark and match in the scan or
 * the library").
 *
 * The surface already named the next click in a sentence, but a sentence only ever
 * describes ONE step: an operator could not see that a point pair is TWO marks, which two
 * surfaces they belong to, or how much of the pair was already done. Enumerating the
 * slots makes the shape of the act visible before it is begun — and a span honestly
 * shows THREE, because that is what it costs.
 */
export function pairSlots(draft: PairDraft): readonly PairSlotView[] {
  const slot = pairSlot(draft);
  const slots: PairSlotView[] = [
    {
      key: "part",
      where: "Library part · pane 1",
      label: "the feature on the part",
      placed: draft.partPoint !== null,
      active: slot === "part",
    },
    {
      key: "scan",
      where: "Scanned cap · pane 2 or 3",
      label: draft.span ? "one END of that feature" : "the same spot on the scan",
      placed: draft.scanPoint !== null,
      active: slot === "scan",
    },
  ];
  if (draft.span) {
    slots.push({
      key: "scan-end",
      where: "Scanned cap · pane 2 or 3",
      label: "the OTHER end of the feature",
      placed: draft.scanPointEnd !== null,
      active: slot === "scan-end",
    });
  }
  return slots;
}

/**
 * Clear ONE mark from a pair, leaving the rest of it standing (client 2026-07-29:
 * "Points need to be able to be removed one by one not all at once").
 *
 * Removing the whole pair was the only exit, so a misplaced second click cost the
 * first one too. This does NOT weaken the re-click pair-integrity rule: that rule
 * forbids a mark being SILENTLY replaced by a stray click, and this is the opposite —
 * an explicit act, on a named mark, that the operator asked for.
 *
 * A span's two scan ends collapse in order: clearing the first end promotes the second
 * into its place rather than leaving a hole the slot machinery would mis-read as
 * "waiting for the first end" while the second sits filled.
 */
export function withoutPick(draft: PairDraft, slot: PairSlot): PairDraft {
  switch (slot) {
    case "part":
      return { ...draft, partPoint: null };
    case "scan":
      return draft.span && draft.scanPointEnd !== null
        ? { ...draft, scanPoint: draft.scanPointEnd, scanPointEnd: null }
        : { ...draft, scanPoint: null };
    case "scan-end":
      return { ...draft, scanPointEnd: null };
    default:
      return draft;
  }
}

/** How many gate reasons a flagged row is standing on, in words — the row states the
 *  COUNT so the operator knows whether opening the dialog is worth it, while the words
 *  themselves stay in the dialog (client 2026-07-29). */
export function reasonCountWords(count: number): string {
  if (count <= 0) return "the gate recorded no action words";
  return count === 1 ? "1 reason" : `${count} reasons`;
}

/** The server's own bound, mirrored for the WARNING below. Kept beside the sentence
 *  that quotes it so the two cannot drift apart silently; the SERVER remains the
 *  authority — this constant never refuses anything. */
export const MIN_CLOCK_LEVER_MM = 0.5;

function inPlaneRadius(
  point: readonly number[],
  origin: readonly number[],
  axis: readonly number[],
): number {
  const d = [point[0]! - origin[0]!, point[1]! - origin[1]!, point[2]! - origin[2]!];
  const n = Math.hypot(axis[0]!, axis[1]!, axis[2]!) || 1;
  const u = [axis[0]! / n, axis[1]! / n, axis[2]! / n];
  const along = d[0]! * u[0]! + d[1]! * u[1]! + d[2]! * u[2]!;
  // the component of d PERPENDICULAR to the axis — the lever arm the clock rides on
  return Math.hypot(
    d[0]! - along * u[0]!,
    d[1]! - along * u[1]!,
    d[2]! - along * u[2]!,
  );
}

/**
 * WARN before a span earns the scan-side lever refusal (client 2026-07-29: the tool
 * "should refuse before you place the span, not after").
 *
 * A span across the SCREW ACCESS is a diameter through the part axis: its midpoint
 * names the axis rather than a clock angle, and the server refuses it. Until now the
 * operator learned that only from a 422 after both clicks were placed.
 *
 * This is a CAUTION, never a block, and that distinction is deliberate. The server
 * measures against the scan's MEASURED rim centre, derived from its clock signature;
 * the client has only the seated pose's origin. They agree closely but not exactly,
 * so blocking on this number could refuse a span the server would have accepted —
 * silently costing the operator a legitimate correction. Warning costs nothing and is
 * right about the case that matters. Exposing the measured rim centre on the payload
 * would let this become a true pre-refusal; see the plan.
 */
export function spanLeverCaution(
  draft: PairDraft,
  pose: { readonly origin: readonly number[]; readonly axis: readonly number[] } | null,
): string | null {
  if (!draft.span || pose === null) return null;
  const a = draft.scanPoint;
  const b = draft.scanPointEnd;
  if (a === null || b === null) return null;
  const mid = [
    (a[0]! + b[0]!) / 2,
    (a[1]! + b[1]!) / 2,
    (a[2]! + b[2]!) / 2,
  ];
  const radius = inPlaneRadius(mid, pose.origin, pose.axis);
  if (radius >= MIN_CLOCK_LEVER_MM) return null;
  return (
    `This span looks like it crosses the screw access: its midpoint sits about ` +
    `${radius.toFixed(2)}mm from the cap's centre, and a span whose midpoint is ` +
    `inside ${MIN_CLOCK_LEVER_MM}mm names the AXIS rather than a clock angle — the ` +
    `server will refuse it. Undo one end and span a coded trench along its own ` +
    `radius instead.`
  );
}

/**
 * THE MEASURED RIM CENTRE, as the worker publishes it (plan §10-F; worker half landed
 * in 08edf02 and the BFF forwards it). `rim_centre` is in WORLD coordinates and
 * `min_lever_mm` is the guard's own bound — read off the wire rather than mirrored, so
 * the server stays the single authority on both the reference and the threshold.
 */
export interface ClockReferenceLike {
  readonly rim_centre: readonly number[];
  readonly min_lever_mm: number;
}

export type LeverGuard = {
  /** `refusal` only when the SERVER'S OWN quantity was in hand. */
  readonly kind: "refusal" | "caution";
  readonly message: string;
};

/**
 * THE CLIENT-SIDE PRE-REFUSAL the client asked for (2026-07-29: "refuse before you
 * place the span, not after").
 *
 * §10-F recorded why this could only ever CAUTION: the server measures a mark's arm
 * from the scan's MEASURED rim centre, and the client had only the seated pose's
 * origin — close, but not the same point, so refusing on it risked refusing a span the
 * server would have taken. That gap is now closed: `clock_reference` carries the
 * server's own centre and bound, so with it in hand this measures the SAME quantity
 * `require_clock_lever` does and may refuse locally with no risk of disagreeing.
 *
 * WITHOUT it, the old approximation is all there is, so the old verdict is all this
 * returns — a caution. The distinction rides on the result rather than being inferred,
 * because "the server will refuse this" and "this looks wrong from here" are different
 * claims and only one of them may block a control.
 *
 * Covers a SINGLE mark as well as a span. The server has always guarded both
 * (`require_clock_lever(..., span=False)`); the client warned about neither until the
 * span case, so a lone click on the access earned a 422 with no warning at all.
 */
export function markLeverGuard(
  draft: PairDraft,
  pose: { readonly origin: readonly number[]; readonly axis: readonly number[] } | null,
  clock: ClockReferenceLike | null,
): LeverGuard | null {
  if (clock === null) {
    const words = spanLeverCaution(draft, pose);
    return words === null ? null : { kind: "caution", message: words };
  }
  if (pose === null) return null;
  const a = draft.scanPoint;
  if (a === null) return null;
  let probe: readonly number[] = a;
  if (draft.span) {
    const b = draft.scanPointEnd;
    if (b === null) return null;
    probe = [(a[0]! + b[0]!) / 2, (a[1]! + b[1]!) / 2, (a[2]! + b[2]!) / 2];
  }
  const radius = inPlaneRadius(probe, clock.rim_centre, pose.axis);
  // DEGRADE, NEVER REFUSE, ON A REFERENCE WE CANNOT MEASURE (review 2026-08-01). The
  // API layer casts the response rather than validating it, so a short `rim_centre` or
  // an absent `min_lever_mm` is reachable — and both used to land in the refusal
  // branch, because `NaN >= x` and `x >= undefined` are alike false. One produced a
  // permanently inert Apply reading "NaNmm"; the other threw inside render. A guard
  // whose whole justification is "never block a correction the server would take" must
  // fail OPEN on its own inputs.
  if (!Number.isFinite(radius) || !Number.isFinite(clock.min_lever_mm)) return null;
  if (radius >= clock.min_lever_mm) return null;
  const bound = clock.min_lever_mm.toFixed(2);
  return {
    kind: "refusal",
    message: draft.span
      ? `This span crosses the screw access: its midpoint sits ${radius.toFixed(2)}mm ` +
        `from the cap's measured rim centre, and inside ${bound}mm a mark names the ` +
        `part AXIS rather than a clock angle — neither end of it can anchor a ` +
        `rotation. Undo one end and span a coded trench along its own radius instead.`
      : `This mark sits ${radius.toFixed(2)}mm from the cap's measured rim centre — ` +
        `that is the screw access, and inside ${bound}mm a mark names the part AXIS ` +
        `rather than a clock angle, so it cannot anchor a rotation. Click the coded ` +
        `trench out on the cap's face instead.`,
  };
}
