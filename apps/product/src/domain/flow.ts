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
  /** Detection ran and its record is persisted (slice 4) — a BFF fact, never inferred
   * from sites being present (curated suggestions exist before detection ever runs). */
  readonly detectionDone: boolean;
  /** All three case-level choices explicitly made — the BFF's derivation, verbatim. */
  readonly choicesComplete: boolean;
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
    detectionDone: row.detected,
    choicesComplete: row.choices_complete,
  };
}

/** Structural mirror of a `CaseSessionDetail` (GET /api/case-sessions/{id}). */
export interface CaseSessionLike {
  readonly sites: ReadonlyArray<{ readonly status: string }>;
  readonly detection: object | null;
  readonly choices: { readonly complete: boolean };
  readonly session: {
    readonly run_state: string;
    readonly confirmed: boolean;
  };
}

export function factsFromCaseSession(payload: CaseSessionLike): FlowFacts {
  return {
    siteTotal: payload.sites.length,
    siteDeclared: payload.sites.filter((s) => s.status !== "detected").length,
    siteReady: payload.sites.filter((s) => s.status === "ready").length,
    siteFlagged: payload.sites.filter((s) => s.status === "flagged").length,
    runState: payload.session.run_state,
    confirmed: payload.session.confirmed,
    detectionDone: payload.detection !== null,
    choicesComplete: payload.choices.complete,
  };
}

const runExists = (facts: FlowFacts): boolean => facts.runState !== "none";

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
 *  - deliver: every site ready, or flagged with a run behind it (the flag IS run
 *    evidence; a flag without a run has nothing to acknowledge). Slice 8's assurance
 *    table may tighten this with run-completion facts; the site rule is the plan's.
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
      return allSitesResolved(facts) && (facts.siteFlagged === 0 || runExists(facts));
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
        return "Sites are still awaiting review — every site must be ready, or flagged, before Deliver.";
      }
      return "Flagged sites need their run's evidence before Deliver — no run exists yet.";
  }
}

/**
 * Completion, per stage — a display verdict for the rail's tick, never a gate:
 *  - intake: detection RAN and the case-level choices are all made (plan §4 slice 4 —
 *    sites merely existing is not Intake done: curated suggestions predate detection,
 *    and the choices are Intake's other half). Both facts are the BFF's derivations.
 *  - declare: every site DECLARED (slice 5a). ONE deliberate deviation from the
 *    plan's slice table, honoured rather than hacked: the tick that sets a site
 *    `ready` is "the operator's review tick over the three live Declare panes"
 *    (AM-8), and the panes arrive in 5b — so the REVIEW tick arrives in 5b with
 *    them. A tick rendered now would be a checkbox over nothing, exactly what AM-8
 *    forbids. 5b extends this completion to every-site-reviewed (ready | flagged).
 *  - adjust: a run exists and nothing is flagged — the plan's "nothing to adjust".
 *  - deliver: the confirmation is sealed.
 */
export function isComplete(stage: StageId, facts: FlowFacts): boolean {
  switch (stage) {
    case "intake":
      return facts.detectionDone && facts.choicesComplete;
    case "declare":
      return facts.siteTotal > 0 && facts.siteDeclared === facts.siteTotal;
    case "adjust":
      return runExists(facts) && facts.siteFlagged === 0;
    case "deliver":
      return facts.confirmed;
  }
}

export interface StageState {
  readonly id: StageId;
  readonly number: number;
  readonly title: string;
  readonly oneLiner: string;
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
