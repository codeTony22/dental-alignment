/**
 * THE PRODUCT'S FLOW MODEL — the four stages of plan §4: Intake → Declare → Adjust →
 * Deliver. This is the PRODUCT's stage model, not the demo's (case/mark/verify/process);
 * the demo's rail doctrine — navigation that tells the truth, a blocked stage carries the
 * sentence that says why — is reimplemented here against these stages, not copied.
 *
 * Direction of trust (grill AM-4): the BFF derives every FACT server-side — site
 * statuses, run state, confirmation — and no endpoint accepts a status back from this
 * app. This module derives only DISPLAY logic from the payload: which stage is
 * reachable, which is complete, what sentence a blocked stage shows, where a session
 * resumes. Nothing computed here is ever sent anywhere.
 *
 * Framework-free on purpose: no React, no router, no fetch. The input shapes below are
 * structural mirrors of the BFF's two GET resources (bff/resources/case_sessions.py),
 * so both payloads project into one `FlowFacts` and every rule has a single home.
 */
// The ONE definition of a usable centre, shared with the site list, the framing hint
// and the scan picker (audit 2026-07-31 — the rail held a looser one and over-claimed
// against the very rows beside it). intake.ts imports only TYPES from api/client, so
// this stays a pure-rules dependency.
import { asVec3 } from "./intake";

export type StageId = "intake" | "declare" | "adjust" | "deliver";

export const STAGE_ORDER: readonly StageId[] = [
  "intake",
  "declare",
  "adjust",
  "deliver",
];

export interface StageInfo {
  readonly title: string;
  readonly oneLiner: string;
}

export const STAGE_INFO: Readonly<Record<StageId, StageInfo>> = {
  intake: {
    title: "Intake",
    oneLiner: "Scan in, sites detected, case-level choices made.",
  },
  declare: {
    title: "Declare",
    oneLiner: "System and variants declared, every site reviewed over the panes.",
  },
  adjust: {
    title: "Adjust",
    oneLiner: "Optional — refit flagged sites; skipping never blocks delivery.",
  },
  deliver: {
    title: "Deliver",
    oneLiner: "Assurance reviewed, confirmation sealed, artifacts released.",
  },
};

/**
 * The facts the flow rules read — a projection of BFF payloads, never client-invented.
 * `runState` is kept as the raw wire string; the only comparison the rules make is
 * against "none" (AM-3 states: none | queued | running | done | refused), so an
 * unforeseen state is treated as "a run exists", which is what a run receipt means.
 */
export interface FlowFacts {
  readonly siteTotal: number;
  /** Sites past "detected" — an operator act has touched them (the BFF rollup's own
   * definition of `declared`; from the detail, every status except "detected"). */
  readonly siteDeclared: number;
  readonly siteReady: number;
  readonly siteFlagged: number;
  readonly runState: string;
  readonly confirmed: boolean;
  /** The BFF's CURRENT-run release verdict (slice 8): true only while the release
   * record still names the current done run — the deliver tick's one fact (a rail
   * tick must be the rail truth: released artifacts, not merely a confirmation). */
  readonly released: boolean;
  /** Detection ran and its record is persisted (slice 4) — a BFF fact, never inferred
   * from sites being present (curated suggestions exist before detection ever runs). */
  readonly detectionDone: boolean;
  /** EFFECTIVE case-level values all present — an explicit act, the case's
   * suggestion, or the standing relief default each count (client 2026-07-27) —
   * the BFF's derivation, verbatim. */
  readonly choicesComplete: boolean;
  /**
   * Sites carrying a usable centre — the honest predicate behind "Continue to
   * Declare", since a site with no centre has nothing for the run to align to
   * (`SiteView.center` is nullable, and a curated site can reach the surface without
   * one — bff/resources/case_sessions.py:459-461).
   *
   * ABSENT, not zero, when the payload in hand does not carry the fact: the
   * worklist's `SiteRollup` has no centred column (bff/resources/case_sessions.py:
   * 69-73). Silence is the honest projection there — a zero would have this module
   * invent a shortfall the server never reported.
   *
   * It is spoken, never enforced: nothing in `isReachable` reads it, because
   * tightening the Declare gate on it would newly block cases that ship today and
   * that is a client decision, not a display one.
   */
  readonly siteCentred?: number;
  /**
   * Sites the DETECTOR actually proposed — a site whose tooth a proposal guessed
   * (`detection.proposals[].tooth_guess`). NOT `siteTotal`: the missed-cap door
   * (bff/resources/case_sessions.py:503-513) creates session-only sites with a
   * `marked_center` and no proposal behind them, and the rail was the only surface
   * on the screen claiming the detector had seen those caps (audit 2026-07-31).
   *
   * ABSENT, like `siteCentred`, when the payload in hand does not carry it: the
   * worklist row projects no proposals, and a zero there would invent a shortfall.
   */
  readonly siteDetected?: number;
}

/** Structural mirror of a `WorklistRow` (GET /api/case-sessions). */
export interface WorklistRowLike {
  readonly sites: {
    readonly total: number;
    readonly declared: number;
    readonly ready: number;
    readonly flagged: number;
  };
  readonly run_state: string;
  readonly confirmed: boolean;
  readonly released: boolean;
  readonly detected: boolean;
  readonly choices_complete: boolean;
}

export function factsFromWorklistRow(row: WorklistRowLike): FlowFacts {
  return {
    siteTotal: row.sites.total,
    siteDeclared: row.sites.declared,
    siteReady: row.sites.ready,
    siteFlagged: row.sites.flagged,
    runState: row.run_state,
    confirmed: row.confirmed,
    released: row.released,
    detectionDone: row.detected,
    choicesComplete: row.choices_complete,
  };
}

/** Structural mirror of a `CaseSessionDetail` (GET /api/case-sessions/{id}). */
export interface CaseSessionLike {
  /** `center` is REQUIRED here though it is nullable: `SiteView.center` always
   * rides the wire (api/client.ts), and letting a caller omit it would make an
   * unmarked site and an unreported one look identical to the shortfall count.
   * `tooth` is what joins a site to the proposal that found it. */
  readonly sites: ReadonlyArray<{
    readonly tooth: number;
    readonly status: string;
    readonly center: ReadonlyArray<number> | null;
  }>;
  /** The detection RECORD — its presence is `detectionDone`, and its proposals are
   * the only evidence that the detector saw a given tooth at all. */
  readonly detection: {
    readonly proposals: ReadonlyArray<{ readonly tooth_guess: number | null }>;
  } | null;
  readonly choices: { readonly complete: boolean };
  readonly session: {
    readonly run_state: string;
    readonly confirmed: boolean;
    readonly released: boolean;
  };
}

export function factsFromCaseSession(payload: CaseSessionLike): FlowFacts {
  const guessed = new Set(
    (payload.detection?.proposals ?? [])
      .map((p) => p.tooth_guess)
      .filter((t): t is number => t !== null),
  );
  return {
    siteTotal: payload.sites.length,
    siteDeclared: payload.sites.filter((s) => s.status !== "detected").length,
    siteReady: payload.sites.filter((s) => s.status === "ready").length,
    siteFlagged: payload.sites.filter((s) => s.status === "flagged").length,
    runState: payload.session.run_state,
    confirmed: payload.session.confirmed,
    released: payload.session.released,
    detectionDone: payload.detection !== null,
    choicesComplete: payload.choices.complete,
    // intake.asVec3, not `center !== null`: same predicate as the site list's framing
    // hint and the scan picker, so the rail cannot over-report against its own rows
    siteCentred: payload.sites.filter((s) => asVec3(s.center) !== null).length,
    siteDetected: payload.sites.filter((s) => guessed.has(s.tooth)).length,
  };
}

const runExists = (facts: FlowFacts): boolean => facts.runState !== "none";

/** A COMPLETED current run — the only run state whose evidence Deliver may read
 * (5c's tighten; a queued/running/refused run has nothing signed-off to show). */
const runDone = (facts: FlowFacts): boolean => facts.runState === "done";

/** Every site carries a verdict: ready, or flagged (statuses like detected/declared/
 * previewed/adjusted are still on their way there and block Deliver). */
const allSitesResolved = (facts: FlowFacts): boolean =>
  facts.siteTotal > 0 && facts.siteReady + facts.siteFlagged === facts.siteTotal;

/**
 * Reachability, per stage (plan §4):
 *  - intake: always — the payload in hand IS a case, and Intake is where it lands.
 *  - declare: needs detected sites; with nothing detected there is nothing to declare.
 *  - adjust: needs a run — the fits it re-works are the run's output. It is SKIPPABLE:
 *    its completion appears in no other stage's rule, so it can never block Deliver.
 *  - deliver: every site resolved AND a COMPLETED current run (the 5c tighten this
 *    module carried as a note since 5a): the assurance table IS the run's evidence,
 *    so a case whose current run is missing, still computing, or refused has nothing
 *    to confirm — and the reset boundaries clear the run pointer on any post-run
 *    change, so a stale run can never open Deliver either.
 */
export function isReachable(stage: StageId, facts: FlowFacts): boolean {
  switch (stage) {
    case "intake":
      return true;
    case "declare":
      return facts.siteTotal > 0;
    case "adjust":
      return runExists(facts);
    case "deliver":
      return allSitesResolved(facts) && runDone(facts);
  }
}

/** The one sentence a blocked stage shows — the WHY, not just a dead entry. */
export function blockedReason(stage: StageId, facts: FlowFacts): string | null {
  if (isReachable(stage, facts)) return null;
  switch (stage) {
    case "intake":
      return null; // unreachable-intake cannot happen; kept for exhaustiveness
    case "declare":
      return "Nothing to declare yet — Intake has not detected any implant sites on this scan.";
    case "adjust":
      return "No run exists yet — Adjust reworks the fits that Declare's authorized run produces.";
    case "deliver":
      if (facts.siteTotal === 0) {
        return "Nothing to deliver — this case has no implant sites yet.";
      }
      if (!allSitesResolved(facts)) {
        // NAME THE SHORTFALL, not just the rule (design's gate voice, "mark 2 more
        // caps first"): a blocked control that recites the rule leaves the operator
        // counting rows by hand to find out how far off they are. The number is
        // arithmetic over facts the BFF already derived — never a client verdict.
        const pending = facts.siteTotal - facts.siteReady - facts.siteFlagged;
        return `Sites are still awaiting review — ${pending} of ${facts.siteTotal} still have no verdict; every site must be ready, or flagged, before Deliver.`;
      }
      if (facts.runState === "none") {
        return "Deliver reads the run's evidence — no run exists yet; it fires when Declare completes.";
      }
      return `Deliver reads the run's evidence — the current run is ${facts.runState}, not completed.`;
  }
}

/**
 * Completion, per stage — a display verdict for the rail's tick, never a gate:
 *  - intake: detection RAN and the EFFECTIVE case-level choices are all present
 *    (plan §4 slice 4; client 2026-07-27 — suggestions and the standing relief
 *    default count, so a well-suggested case completes Intake without a panel
 *    visit). Both facts are the BFF's derivations.
 *  - declare: every site REVIEWED — the operator's tick over the three live panes
 *    set it `ready` (AM-8; the 5a interim rule "every site declared" retired when
 *    5b landed the panes and the tick). Ready ONLY: a flagged site is 5c's run
 *    evidence, not a review — Declare is done when the operator has attested every
 *    site, and the run gate (5c's AuthorizedRunSelection) reads the same fact.
 *  - adjust: a run exists and nothing is flagged — the plan's "nothing to adjust".
 *  - deliver: RELEASED (slice 8 — the rail truth): the artifacts are disclosed for
 *    the current run. A confirmation alone is a step along the way, not delivery —
 *    the BFF derives `released` as a current-run verdict, so a post-release change
 *    honestly unticks the stage.
 */
export function isComplete(stage: StageId, facts: FlowFacts): boolean {
  switch (stage) {
    case "intake":
      return facts.detectionDone && facts.choicesComplete;
    case "declare":
      return facts.siteTotal > 0 && facts.siteReady === facts.siteTotal;
    case "adjust":
      return runExists(facts) && facts.siteFlagged === 0;
    case "deliver":
      return facts.released;
  }
}

/** "3 sites" / "1 site" — the count leads, because the count is the news. */
function nSites(n: number): string {
  return `${n} ${n === 1 ? "site" : "sites"}`;
}

/**
 * THE SUB-LINE UNDER A STAGE'S TITLE — the same slot the static one-liner filled,
 * now speaking the case's LIVE counts (design rail, `sub` at flow.dc.html:865).
 *
 * Why this exists: a reachable Adjust read "Optional — refit flagged sites; skipping
 * never blocks delivery" whether nothing or nine sites were flagged, so the rail's
 * one line of prose per stage was the only part of the shell that never moved. The
 * counts were already in `FlowFacts` — this only says them out loud.
 *
 * Every branch is arithmetic over BFF-derived facts. Nothing here compares a
 * tolerance, decides a verdict, or invents a status; where the facts hold no count
 * worth speaking (an empty case, a stage whose evidence has not arrived) the
 * standing one-liner is still the truth and stands.
 */
export function stageSubLine(stage: StageId, facts: FlowFacts): string {
  const standing = STAGE_INFO[stage].oneLiner;
  const total = facts.siteTotal;
  switch (stage) {
    case "intake": {
      if (total === 0) return standing;
      if (!facts.detectionDone) {
        // Sites before detection are the case's CURATED suggestions — calling them
        // "detected" here would claim a run that has not happened.
        return `${nSites(total)} suggested — detection has not run yet.`;
      }
      // The shortfall behind the Declare gate, spoken but not enforced. `undefined`
      // means the payload never carried the fact, which is not the same as zero.
      const centred = facts.siteCentred;
      if (centred !== undefined && centred < total) {
        return `${total - centred} of ${nSites(total)} still without a centre.`;
      }
      // COUNT WHAT THE SENTENCE NAMES (audit 2026-07-31). "N sites detected" over
      // `siteTotal` asserted detection across hand-marked caps — on a screen whose
      // own panel ("A cap the detection missed") is what created them and whose rows
      // render no detector evidence for them, because there is none. Detection finds
      // 8 of 10 on this fleet, which is the whole reason that door exists.
      const detected = facts.siteDetected;
      const tail = facts.choicesComplete
        ? "case-level choices made."
        : "case-level choices still open.";
      if (detected === undefined) {
        // the payload never carried the fact (the worklist row) — drop the word
        // rather than claim it
        return `${nSites(total)} — ${tail}`;
      }
      const byHand = total - detected;
      return byHand > 0
        ? `${detected} detected, ${byHand} marked by hand — ${tail}`
        : `${nSites(total)} detected — ${tail}`;
    }
    case "declare": {
      if (total === 0) return standing;
      // Ready ONLY, matching isComplete("declare"): the review tick is the act
      // being counted, and a flag is the run's evidence rather than a review.
      return facts.siteReady === total
        ? `All ${nSites(total)} reviewed.`
        : `${facts.siteReady} of ${nSites(total)} reviewed.`;
    }
    case "adjust": {
      // The design's own words (flow.dc.html:865) — the work waiting, in one count.
      if (facts.siteFlagged > 0) return `${facts.siteFlagged} flagged to rework.`;
      if (!runExists(facts)) return standing;
      return "Nothing flagged — no rework owed.";
    }
    case "deliver": {
      if (facts.released) return "Artifacts released for the current run.";
      if (facts.confirmed) return "Confirmed — artifacts not released yet.";
      if (!isReachable("deliver", facts)) return standing;
      return facts.siteFlagged > 0
        ? `${facts.siteReady} ready, ${facts.siteFlagged} flagged — assurance ready to review.`
        : `All ${nSites(total)} ready — assurance ready to review.`;
    }
  }
}

export interface StageState {
  readonly id: StageId;
  readonly number: number;
  readonly title: string;
  readonly oneLiner: string;
  /** The live-count sentence the rail shows — falls back to `oneLiner` where the
   * facts hold no count worth speaking. */
  readonly subLine: string;
  readonly reachable: boolean;
  readonly complete: boolean;
  /** Present exactly when the stage is not reachable. */
  readonly blockedReason: string | null;
}

/** The rail's whole truth in one pass — what each of the four stages may render. */
export function stageStates(facts: FlowFacts): readonly StageState[] {
  return STAGE_ORDER.map((id, index) => ({
    id,
    number: index + 1,
    title: STAGE_INFO[id].title,
    oneLiner: STAGE_INFO[id].oneLiner,
    subLine: stageSubLine(id, facts),
    reachable: isReachable(id, facts),
    complete: isComplete(id, facts),
    blockedReason: blockedReason(id, facts),
  }));
}

/**
 * Where a session resumes (plan §4 worklist, AM-7: "opening a row resumes its session
 * at its furthest stage"): the LAST reachable stage in order. Intake is always
 * reachable, so the fallback is total.
 */
export function furthestStage(facts: FlowFacts): StageId {
  return (
    [...STAGE_ORDER].reverse().find((stage) => isReachable(stage, facts)) ?? "intake"
  );
}

export function isStageId(raw: string): raw is StageId {
  return (STAGE_ORDER as readonly string[]).includes(raw);
}

export type StageResolution =
  | { readonly kind: "show"; readonly stage: StageId }
  | { readonly kind: "redirect"; readonly to: StageId };

/**
 * The route guard's decision for `/case/:id/:stage`: an unknown stage segment, a
 * missing one, or a stage the facts say is unreachable all redirect to the furthest
 * stage — the URL is never allowed to outrun the case.
 */
export function resolveStagePath(
  raw: string | undefined,
  facts: FlowFacts,
): StageResolution {
  if (raw !== undefined && isStageId(raw) && isReachable(raw, facts)) {
    return { kind: "show", stage: raw };
  }
  return { kind: "redirect", to: furthestStage(facts) };
}
