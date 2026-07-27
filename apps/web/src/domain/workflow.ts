/**
 * THE WORKFLOW, AS THE CLIENT DESCRIBES IT — ONE FLOW (2026-07-26: "it feels like two flows …
 * let's have ONE cohesive flow, include all the features"):
 *
 *   load case → mark & declare (marks + the library selection, in one place)
 *   → verify (3 panels + acknowledge) → process
 *   → if the alignment is not right: best fit or fit by points → re-verify → complete/export
 *
 * The previous rail had a separate "Library selection" stage between marking and verifying.
 * That stop is DELETED, not renumbered around: the selection lists live inside Mark & declare
 * now, so its condition (system + construction chosen, relief valid) is judged as part of that
 * stage's completion. Two rules carry over unchanged:
 *
 *  1. COMPLETION IS MEASURED, never assumed. A stage is complete when the case satisfies it, so
 *     the rail cannot show ticks over a case with no cap declared or no system chosen. The last
 *     correction loop is part of it: a run that the marks have since drifted past is NOT a
 *     complete Process.
 *  2. REACHABILITY IS EXPLAINED. A stage that cannot be opened says why in one sentence, which
 *     is what makes the sequence obvious without a manual.
 *
 * Framework-free (no React, no fetch) like the rest of domain/ — the rail renders this, and the
 * rules are unit-testable without a DOM.
 */

export type StageId = "case" | "mark" | "verify" | "process";

/** Left-to-right order. Exported because the rail, the "next" action and the tests all need the
 *  same sequence, and three copies of it would be three chances to disagree. */
export const STAGE_ORDER: readonly StageId[] = ["case", "mark", "verify", "process"];

/** What the workflow can see about the case in front of the operator. Every field is a fact
 *  already derived elsewhere in the app — this module only decides what they MEAN for the rail. */
export interface WorkflowInput {
  readonly hasCase: boolean;
  /** Marked sites (confirm rows) — a case with none has nothing to select a cap for. */
  readonly siteCount: number;
  /** Of those, how many carry the doctor's declared cap variant (the run's hard requirement). */
  readonly declaredSiteCount: number;
  /** Implant system + construction part chosen, every site's cap declared, relief valid — the
   *  absorbed Library-selection condition, now part of Mark & declare (2026-07-26). */
  readonly selectionComplete: boolean;
  /** Every site ticked in the acknowledgment — the gate Process is branded by. */
  readonly reviewedAll: boolean;
  readonly hasRun: boolean;
  /** The marks have moved since the run that is on screen — the results describe a gesture that
   *  no longer exists, so Process is not finished. */
  readonly runStale: boolean;
}

export interface WorkflowStage {
  readonly id: StageId;
  /** 1-based, for the rail's marker. */
  readonly number: number;
  readonly label: string;
  /** The one line under the label: what this stage is for, or how far it has got. */
  readonly detail: string;
  readonly complete: boolean;
  /** False when opening it would show a panel with nothing to act on. */
  readonly enabled: boolean;
  /** Why it is not reachable yet — null when it is. */
  readonly blockedReason: string | null;
}

const LABELS: Readonly<Record<StageId, string>> = {
  case: "Case",
  mark: "Mark & declare",
  verify: "Verify",
  process: "Process",
};

export function stageNumber(id: StageId): number {
  return STAGE_ORDER.indexOf(id) + 1;
}

/** Mark & declare's one line: the first thing it still needs, or how far it has got. Ordered the
 *  way the panel stack is — marks, then per-site declarations, then the selection lists. */
function markDetail(input: WorkflowInput): string {
  const hasSites = input.siteCount > 0;
  if (!hasSites) return "mark each healing cap on the scan";
  const undeclared = input.siteCount - input.declaredSiteCount;
  if (undeclared > 0) {
    return `${undeclared} of ${input.siteCount} site${input.siteCount === 1 ? "" : "s"} needs a cap variant`;
  }
  if (!input.selectionComplete) return "choose the implant system and the construction part";
  return `${input.siteCount} site${input.siteCount === 1 ? "" : "s"} marked and declared`;
}

/** The workflow's four stages, judged against the case. Pure: same input, same rail. */
export function workflowStages(input: WorkflowInput): WorkflowStage[] {
  const hasSites = input.siteCount > 0;
  const allDeclared = hasSites && input.declaredSiteCount === input.siteCount;

  const noCase = "Load a case first.";
  const noSites = "Mark at least one healing cap first.";

  const stages: WorkflowStage[] = [
    {
      id: "case",
      number: 1,
      label: LABELS.case,
      detail: input.hasCase ? "scan loaded" : "choose the doctor's scan",
      complete: input.hasCase,
      enabled: true,
      blockedReason: null,
    },
    {
      id: "mark",
      number: 2,
      label: LABELS.mark,
      detail: markDetail(input),
      // The absorbed Library-selection condition gates here too: a declared case whose system
      // or construction is still unchosen has not finished Mark & declare (2026-07-26).
      complete: allDeclared && input.selectionComplete,
      enabled: input.hasCase,
      blockedReason: input.hasCase ? null : noCase,
    },
    {
      id: "verify",
      number: 3,
      label: LABELS.verify,
      detail: input.reviewedAll && hasSites
        ? "every site reviewed"
        : "compare the library part, the scanned cap and the deviation",
      complete: hasSites && input.reviewedAll,
      enabled: input.hasCase && hasSites,
      blockedReason: !input.hasCase ? noCase : hasSites ? null : noSites,
    },
    {
      id: "process",
      number: 4,
      label: LABELS.process,
      detail: !input.hasRun
        ? "align, bore the channel, emit the package"
        : input.runStale
          ? "marks changed since this run — recompute"
          : "aligned — correct the seat or export",
      complete: input.hasRun && !input.runStale,
      enabled: input.hasCase && hasSites,
      blockedReason: !input.hasCase ? noCase : hasSites ? null : noSites,
    },
  ];
  return stages;
}

/** Where the operator should be: the first stage the case has not satisfied, or the last one
 *  when it has satisfied them all. Drives the rail's "continue" action, never a forced jump. */
export function nextStage(stages: readonly WorkflowStage[]): StageId {
  const pending = stages.find((s) => !s.complete && s.enabled);
  return pending?.id ?? (stages[stages.length - 1]?.id ?? "case");
}
