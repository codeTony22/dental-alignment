/**
 * THE WORKFLOW'S RULES (client, 2026-07-26: "it feels like two flows … let's have ONE cohesive
 * flow"). The separate "Library selection" STOP is deleted: the selection is made inside
 * Mark & declare, beside the rows that declare each cap — so the rail is FOUR stages, and
 * Mark & declare is complete only when the marks, the declarations AND the library selection
 * (system, construction part, valid relief) are all in. Completion stays measured against the
 * case, never against how far the operator has clicked, and an unreachable stage says why.
 */
import { describe, expect, it } from "vitest";
import { STAGE_ORDER, nextStage, stageNumber, workflowStages, type WorkflowInput } from "./workflow";

function input(overrides: Partial<WorkflowInput> = {}): WorkflowInput {
  return {
    hasCase: true,
    siteCount: 1,
    declaredSiteCount: 1,
    selectionComplete: true,
    reviewedAll: true,
    hasRun: true,
    runStale: false,
    ...overrides,
  };
}

function byId(stages: ReturnType<typeof workflowStages>) {
  return new Map(stages.map((s) => [s.id, s]));
}

describe("workflowStages — the client's ONE flow", () => {
  it("is four stages — the Library-selection stop is gone", () => {
    expect(STAGE_ORDER).toEqual(["case", "mark", "verify", "process"]);
    expect(workflowStages(input()).map((s) => s.label)).toEqual([
      "Case",
      "Mark & declare",
      "Verify",
      "Process",
    ]);
    expect(workflowStages(input()).map((s) => s.number)).toEqual([1, 2, 3, 4]);
    expect(stageNumber("verify")).toBe(3);
    expect(stageNumber("process")).toBe(4);
  });

  it("completes nothing but Case on a freshly loaded case", () => {
    const stages = byId(
      workflowStages(
        input({
          siteCount: 0,
          declaredSiteCount: 0,
          selectionComplete: false,
          reviewedAll: false,
          hasRun: false,
        }),
      ),
    );
    expect(stages.get("case")?.complete).toBe(true);
    expect(stages.get("mark")?.complete).toBe(false);
    expect(stages.get("verify")?.complete).toBe(false);
    expect(stages.get("process")?.complete).toBe(false);
  });

  it("does NOT complete Mark & declare while a marked site has no declared variant", () => {
    const stages = byId(workflowStages(input({ siteCount: 2, declaredSiteCount: 1 })));
    expect(stages.get("mark")?.complete).toBe(false);
    expect(stages.get("mark")?.detail).toContain("1 of 2 sites needs a cap variant");
  });

  it("does NOT complete Mark & declare while the library selection is incomplete — the absorbed stage still gates", () => {
    // every cap declared, but no system/construction chosen yet: the old Library-selection
    // stage's own condition, now judged INSIDE Mark & declare (the collapse must not lose it)
    const stages = byId(workflowStages(input({ selectionComplete: false })));
    expect(stages.get("mark")?.complete).toBe(false);
    expect(stages.get("mark")?.detail).toContain("choose the implant system and the construction part");
  });

  it("completes Mark & declare when marks, declarations and selection are all in", () => {
    const stages = byId(workflowStages(input({ siteCount: 2, declaredSiteCount: 2 })));
    expect(stages.get("mark")?.complete).toBe(true);
    expect(stages.get("mark")?.detail).toContain("2 sites marked and declared");
  });

  it("does NOT complete Verify on a case with no marked site, however 'reviewed' reads", () => {
    // vacuous truth is the bug this guards: "every site is reviewed" is trivially true of none
    const stages = byId(workflowStages(input({ siteCount: 0, declaredSiteCount: 0, reviewedAll: true })));
    expect(stages.get("verify")?.complete).toBe(false);
  });

  it("un-completes Process once the marks have drifted past the run on screen", () => {
    const fresh = byId(workflowStages(input()));
    const stale = byId(workflowStages(input({ runStale: true })));
    expect(fresh.get("process")?.complete).toBe(true);
    expect(stale.get("process")?.complete).toBe(false);
    expect(stale.get("process")?.detail).toContain("marks changed");
  });

  it("blocks every later stage with a sentence while no case is loaded", () => {
    const stages = workflowStages(input({ hasCase: false }));
    expect(stages[0]?.enabled).toBe(true);
    for (const stage of stages.slice(1)) {
      expect(stage.enabled).toBe(false);
      expect(stage.blockedReason).toBe("Load a case first.");
    }
  });

  it("blocks verify and process with a sentence while nothing is marked", () => {
    const stages = byId(workflowStages(input({ siteCount: 0, declaredSiteCount: 0 })));
    expect(stages.get("mark")?.enabled).toBe(true);
    for (const id of ["verify", "process"] as const) {
      expect(stages.get(id)?.enabled).toBe(false);
      expect(stages.get(id)?.blockedReason).toBe("Mark at least one healing cap first.");
    }
  });
});

describe("nextStage — where the case actually is", () => {
  it("points at the first unsatisfied REACHABLE stage", () => {
    expect(nextStage(workflowStages(input({ hasCase: false })))).toBe("case");
    expect(
      nextStage(workflowStages(input({ siteCount: 1, declaredSiteCount: 0, selectionComplete: false }))),
    ).toBe("mark");
    // the library selection now lives on Mark & declare — an unmade selection keeps the
    // operator THERE, where the system/construction lists are, not on a stage that no longer exists
    expect(nextStage(workflowStages(input({ selectionComplete: false })))).toBe("mark");
    expect(nextStage(workflowStages(input({ reviewedAll: false })))).toBe("verify");
    expect(nextStage(workflowStages(input({ hasRun: false })))).toBe("process");
  });

  it("rests on Process once the case has satisfied everything", () => {
    expect(nextStage(workflowStages(input()))).toBe("process");
  });
});
