/**
 * The flow model's rules (plan §4), pinned: reachability per stage, adjust's
 * skippability, completion ticks, resume via furthestStage, and the route guard's
 * redirect decision. Pure functions — no React, no router, no fetch.
 */
import { describe, expect, it } from "vitest";
import {
  factsFromCaseSession,
  factsFromWorklistRow,
  furthestStage,
  isComplete,
  isReachable,
  resolveStagePath,
  STAGE_INFO,
  STAGE_ORDER,
  stageStates,
  type FlowFacts,
} from "./flow";

/** A fact-builder so each test states only what it is about. */
function facts(overrides: Partial<FlowFacts> = {}): FlowFacts {
  return {
    siteTotal: 0,
    siteReady: 0,
    siteFlagged: 0,
    runState: "none",
    confirmed: false,
    detectionDone: false,
    choicesComplete: false,
    ...overrides,
  };
}

describe("the stage model", () => {
  it("orders the product's four stages — not the demo's", () => {
    expect(STAGE_ORDER).toEqual(["intake", "declare", "adjust", "deliver"]);
  });

  it("gives every stage a title and a one-liner", () => {
    for (const id of STAGE_ORDER) {
      expect(STAGE_INFO[id].title.length).toBeGreaterThan(0);
      expect(STAGE_INFO[id].oneLiner.length).toBeGreaterThan(0);
    }
  });
});

describe("reachability", () => {
  it("intake is always reachable — the case in hand is the ticket", () => {
    expect(isReachable("intake", facts())).toBe(true);
    expect(isReachable("intake", facts({ siteTotal: 3, confirmed: true }))).toBe(true);
  });

  it("declare needs detected sites", () => {
    expect(isReachable("declare", facts())).toBe(false);
    expect(isReachable("declare", facts({ siteTotal: 1 }))).toBe(true);
  });

  it("adjust needs a run, in any run state", () => {
    expect(isReachable("adjust", facts({ siteTotal: 2 }))).toBe(false);
    for (const runState of ["queued", "running", "done", "refused"]) {
      expect(isReachable("adjust", facts({ siteTotal: 2, runState }))).toBe(true);
    }
  });

  it("deliver needs every site ready, or flagged with a run", () => {
    // still under review: one site has no verdict yet
    expect(
      isReachable("deliver", facts({ siteTotal: 3, siteReady: 2, runState: "done" })),
    ).toBe(false);
    // all resolved, flags carry run evidence
    expect(
      isReachable(
        "deliver",
        facts({ siteTotal: 3, siteReady: 2, siteFlagged: 1, runState: "done" }),
      ),
    ).toBe(true);
    // a flag without a run has nothing to acknowledge
    expect(
      isReachable("deliver", facts({ siteTotal: 2, siteReady: 1, siteFlagged: 1 })),
    ).toBe(false);
    // no sites, nothing to deliver
    expect(isReachable("deliver", facts())).toBe(false);
  });

  it("adjust is SKIPPABLE — flagged sites never make it block deliver", () => {
    const flagged = facts({
      siteTotal: 4,
      siteReady: 3,
      siteFlagged: 1,
      runState: "done",
    });
    expect(isComplete("adjust", flagged)).toBe(false); // there IS something to adjust
    expect(isReachable("deliver", flagged)).toBe(true); // and deliver opens anyway
  });
});

describe("blocked stages explain WHY in one sentence", () => {
  it("each unreachable stage carries a reason; reachable ones carry none", () => {
    const fresh = facts(); // no sites, no run
    for (const state of stageStates(fresh)) {
      if (state.reachable) {
        expect(state.blockedReason).toBeNull();
      } else {
        expect(state.blockedReason).toMatch(/\S/);
      }
    }
  });

  it("deliver's reason names the actual blocker", () => {
    const underReview = stageStates(
      facts({ siteTotal: 3, siteReady: 1, runState: "done" }),
    ).find((s) => s.id === "deliver");
    expect(underReview?.blockedReason).toContain("awaiting review");

    const flaggedNoRun = stageStates(
      facts({ siteTotal: 2, siteReady: 1, siteFlagged: 1 }),
    ).find((s) => s.id === "deliver");
    expect(flaggedNoRun?.blockedReason).toContain("run");
  });
});

describe("completion ticks", () => {
  it("intake completes when detection RAN and the choices are all made (slice 4)", () => {
    expect(isComplete("intake", facts())).toBe(false);
    // sites merely existing is NOT intake done: curated suggestions predate detection
    expect(isComplete("intake", facts({ siteTotal: 2 }))).toBe(false);
    expect(isComplete("intake", facts({ detectionDone: true }))).toBe(false);
    expect(isComplete("intake", facts({ choicesComplete: true }))).toBe(false);
    expect(
      isComplete("intake", facts({ detectionDone: true, choicesComplete: true })),
    ).toBe(true);
  });

  it("declare completes when every site is reviewed to ready or flagged", () => {
    expect(isComplete("declare", facts({ siteTotal: 2, siteReady: 1 }))).toBe(false);
    expect(
      isComplete("declare", facts({ siteTotal: 2, siteReady: 1, siteFlagged: 1 })),
    ).toBe(true);
  });

  it("adjust completes as 'nothing to adjust': a run and zero flags", () => {
    expect(isComplete("adjust", facts({ siteTotal: 2, siteReady: 2 }))).toBe(false);
    expect(
      isComplete("adjust", facts({ siteTotal: 2, siteReady: 2, runState: "done" })),
    ).toBe(true);
    expect(
      isComplete(
        "adjust",
        facts({ siteTotal: 2, siteReady: 1, siteFlagged: 1, runState: "done" }),
      ),
    ).toBe(false);
  });

  it("deliver completes only on confirmation", () => {
    const done = facts({ siteTotal: 1, siteReady: 1, runState: "done" });
    expect(isComplete("deliver", done)).toBe(false);
    expect(isComplete("deliver", { ...done, confirmed: true })).toBe(true);
  });
});

describe("furthestStage — where a session resumes (AM-7)", () => {
  it("an empty case resumes at intake", () => {
    expect(furthestStage(facts())).toBe("intake");
  });

  it("detected-but-unreviewed sites resume at declare", () => {
    expect(furthestStage(facts({ siteTotal: 3 }))).toBe("declare");
  });

  it("a running case with unresolved sites resumes at adjust (the last reachable)", () => {
    expect(
      furthestStage(facts({ siteTotal: 3, siteReady: 2, runState: "running" })),
    ).toBe("adjust");
  });

  it("a fully resolved case resumes at deliver, flagged or clean", () => {
    expect(
      furthestStage(
        facts({ siteTotal: 3, siteReady: 2, siteFlagged: 1, runState: "done" }),
      ),
    ).toBe("deliver");
    expect(
      furthestStage(facts({ siteTotal: 2, siteReady: 2, runState: "done", confirmed: true })),
    ).toBe("deliver");
  });
});

describe("resolveStagePath — the route guard's decision", () => {
  const midFlow = facts({ siteTotal: 2, siteReady: 1, runState: "running" });

  it("shows a known, reachable stage", () => {
    expect(resolveStagePath("declare", midFlow)).toEqual({
      kind: "show",
      stage: "declare",
    });
    expect(resolveStagePath("intake", facts())).toEqual({
      kind: "show",
      stage: "intake",
    });
  });

  it("redirects an unknown stage segment to the furthest stage", () => {
    expect(resolveStagePath("banana", midFlow)).toEqual({
      kind: "redirect",
      to: "adjust",
    });
  });

  it("redirects a missing stage segment to the furthest stage", () => {
    expect(resolveStagePath(undefined, midFlow)).toEqual({
      kind: "redirect",
      to: "adjust",
    });
  });

  it("redirects a known but unreachable stage — the URL cannot outrun the case", () => {
    expect(resolveStagePath("deliver", midFlow)).toEqual({
      kind: "redirect",
      to: "adjust",
    });
    expect(resolveStagePath("adjust", facts({ siteTotal: 1 }))).toEqual({
      kind: "redirect",
      to: "declare",
    });
  });
});

describe("the two payload projections agree", () => {
  it("a worklist row and its detail payload yield identical facts", () => {
    const fromRow = factsFromWorklistRow({
      sites: { total: 3, ready: 2, flagged: 1 },
      run_state: "done",
      confirmed: false,
      detected: true,
      choices_complete: true,
    });
    const fromDetail = factsFromCaseSession({
      sites: [{ status: "ready" }, { status: "ready" }, { status: "flagged" }],
      detection: { proposals: [] },
      choices: { complete: true },
      session: { run_state: "done", confirmed: false },
    });
    expect(fromRow).toEqual(fromDetail);
  });

  it("detection facts project from the payload, not from sites existing", () => {
    const undetected = factsFromCaseSession({
      sites: [{ status: "detected" }],
      detection: null,
      choices: { complete: false },
      session: { run_state: "none", confirmed: false },
    });
    expect(undetected.detectionDone).toBe(false);
    expect(undetected.choicesComplete).toBe(false);
    expect(undetected.siteTotal).toBe(1); // curated suggestions predate detection
  });

  it("in-flight statuses (declared/previewed/adjusted) count as neither ready nor flagged", () => {
    const projected = factsFromCaseSession({
      sites: [
        { status: "detected" },
        { status: "declared" },
        { status: "previewed" },
        { status: "adjusted" },
        { status: "ready" },
      ],
      detection: null,
      choices: { complete: false },
      session: { run_state: "done", confirmed: false },
    });
    expect(projected.siteTotal).toBe(5);
    expect(projected.siteReady).toBe(1);
    expect(projected.siteFlagged).toBe(0);
    expect(isReachable("deliver", projected)).toBe(false);
  });
});
