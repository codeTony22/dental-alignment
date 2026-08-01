/**
 * The flow model's rules (plan §4), pinned: reachability per stage, adjust's
 * skippability, completion ticks, resume via furthestStage, and the route guard's
 * redirect decision. Pure functions — no React, no router, no fetch.
 */
import { describe, expect, it } from "vitest";
import {
  blockedReason,
  factsFromCaseSession,
  factsFromWorklistRow,
  furthestStage,
  isComplete,
  isReachable,
  resolveStagePath,
  STAGE_INFO,
  STAGE_ORDER,
  stageStates,
  stageSubLine,
  type FlowFacts,
} from "./flow";

/** A fact-builder so each test states only what it is about. */
function facts(overrides: Partial<FlowFacts> = {}): FlowFacts {
  return {
    siteTotal: 0,
    siteDeclared: 0,
    siteReady: 0,
    siteFlagged: 0,
    runState: "none",
    confirmed: false,
    released: false,
    detectionDone: false,
    choicesComplete: false,
    constructionChosen: false,
    ...overrides,
  };
}

describe("changing the part does NOT strand the case", () => {
  /* THE LOAD-BEARING CLAIM behind shipping the library page before `emit_from_poses`
     (§10-M). Changing the effective construction is a reset boundary: the BFF clears
     the current-run pointer and regresses every site's preview. The design's own
     gating then makes the library unreachable — it needs a DONE run — so the worry is
     that picking a part on page four locks the case out of pages four AND five with
     nowhere to go.

     It does not, and this pins why: the reset lands the operator back on Alignment,
     which is reachable, states what it needs, and re-runs. Verified as facts rather
     than by clicking, because every case on this fleet with a done run is also
     RELEASED, and proving a claim must not cost a confirmation. */
  const afterPartChange = facts({
    siteTotal: 2,
    siteDeclared: 2,
    siteReady: 0, // invalidate_preview regressed them
    siteFlagged: 0,
    runState: "none", // clear_current_run
    detectionDone: true,
    choicesComplete: true,
    constructionChosen: true, // the NEW part stands
  });

  it("leaves a reachable stage to land on, and it is Alignment", () => {
    expect(furthestStage(afterPartChange)).toBe("declare");
    expect(isReachable("declare", afterPartChange)).toBe(true);
  });

  it("closes the three stages that genuinely have nothing to show", () => {
    for (const stage of ["adjust", "library", "deliver"] as const) {
      expect(isReachable(stage, afterPartChange)).toBe(false);
      // and none of them goes dead silently — the rail says what is missing
      expect(blockedReason(stage, afterPartChange)).toMatch(/\S/);
    }
  });

  it("names the NEXT act, and never the part the operator just picked", () => {
    // the part IS chosen, so telling them to pick one would be a lie. What the reset
    // actually left them is a set of sites to review again — and Deliver names THAT
    // rather than the missing run, because reviewing is the act that comes first and
    // the run fires off the back of it. (Written expecting "no run exists yet"; the
    // ordering in blockedReason is better than the expectation was.)
    expect(blockedReason("library", afterPartChange)).toContain("once the run completes");
    const deliver = blockedReason("deliver", afterPartChange)!;
    expect(deliver).toContain("still awaiting review");
    expect(deliver).not.toContain("construction part");
  });

  it("re-opens the library the moment the re-run lands", () => {
    const reRun = { ...afterPartChange, siteReady: 2, runState: "done" };
    expect(isReachable("library", reRun)).toBe(true);
    expect(isReachable("deliver", reRun)).toBe(true);
    expect(furthestStage(reRun)).toBe("deliver");
  });
});

describe("the construction library — the fourth page", () => {
  const done = {
    siteTotal: 2, siteReady: 2, siteFlagged: 0, runState: "done", detectionDone: true,
  } as Partial<FlowFacts>;

  it("opens only once the run is done and every site has a verdict", () => {
    expect(isReachable("library", facts({ ...done }))).toBe(true);
    expect(isReachable("library", facts({ ...done, runState: "running" }))).toBe(false);
    expect(isReachable("library", facts({ ...done, siteReady: 1 }))).toBe(false);
  });

  it("says WHICH of the two is missing when it is blocked", () => {
    expect(blockedReason("library", facts({ ...done, runState: "running" })))
      .toContain("once the run completes");
    expect(blockedReason("library", facts({ ...done, siteReady: 1 })))
      .toContain("before you pick a construction part");
  });

  it("is complete when a part has been chosen, and not before", () => {
    expect(isComplete("library", facts({ ...done }))).toBe(false);
    expect(isComplete("library", facts({ ...done, constructionChosen: true }))).toBe(true);
  });

  it("GATES Delivery — the part is what Delivery prices and cuts", () => {
    // the design's own rule: deliver needs a done run, every site resolved AND a part
    expect(isReachable("deliver", facts({ ...done }))).toBe(false);
    expect(blockedReason("deliver", facts({ ...done })))
      .toContain("Pick a construction part in the library first");
    expect(isReachable("deliver", facts({ ...done, constructionChosen: true }))).toBe(true);
  });

  it("names the part-shaped shortfall ONLY when nothing else is missing", () => {
    // a case with no run is not missing a part — it is missing a run, and saying the
    // wrong thing sends the operator to the wrong page
    const noRun = facts({ siteTotal: 2, siteReady: 2, runState: "none" });
    expect(blockedReason("deliver", noRun)).toContain("no run exists yet");
  });

  it("resumes at the library, not past it, once the run lands", () => {
    expect(furthestStage(facts({ ...done }))).toBe("library");
    expect(furthestStage(facts({ ...done, constructionChosen: true }))).toBe("deliver");
  });

  it("speaks the part in its sub-line once one is chosen", () => {
    expect(stageSubLine("library", facts({ ...done }))).toContain("Pick the part");
    expect(stageSubLine("library", facts({ ...done, constructionChosen: true })))
      .toContain("cuts this part");
  });
});

describe("the stage model", () => {
  it("orders the product's FIVE stages — not the demo's", () => {
    // the client's own flow (design "ArTech End-to-End Flow", 2026-08-01): the
    // construction library becomes a page of its own, between the rework and the
    // money. Keys are unchanged so every route, guard and session survives; only the
    // titles and the new rung move.
    expect(STAGE_ORDER).toEqual(["intake", "declare", "adjust", "library", "deliver"]);
  });

  it("carries the CLIENT'S titles, not the engineering keys", () => {
    expect(STAGE_INFO.declare.title).toBe("Alignment");
    expect(STAGE_INFO.adjust.title).toBe("Adjustment");
    expect(STAGE_INFO.library.title).toBe("Construction library");
    expect(STAGE_INFO.deliver.title).toBe("Delivery");
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

  it("deliver needs every site resolved AND a completed run (the 5c tighten)", () => {
    // still under review: one site has no verdict yet
    expect(
      isReachable("deliver", facts({ siteTotal: 3, siteReady: 2, runState: "done" })),
    ).toBe(false);
    // all resolved over a completed run AND a part picked — flagged or clean, Deliver
    // opens. The part is the client's 2026-08-01 addition: the construction library is
    // its own page and Delivery prices and cuts what was chosen there.
    expect(
      isReachable(
        "deliver",
        facts({ siteTotal: 3, siteReady: 2, siteFlagged: 1, runState: "done",
                constructionChosen: true }),
      ),
    ).toBe(true);
    expect(
      isReachable("deliver", facts({ siteTotal: 2, siteReady: 2, runState: "done",
                                     constructionChosen: true })),
    ).toBe(true);
    // DELIBERATE change (5c, carried as flow.ts's note since 5a): every site ready
    // no longer opens Deliver on its own — the assurance table IS the run's
    // evidence, so no run, a run still computing, or a refused run all block
    expect(
      isReachable("deliver", facts({ siteTotal: 2, siteReady: 2 })),
    ).toBe(false);
    for (const runState of ["queued", "running", "refused"]) {
      expect(
        isReachable("deliver", facts({ siteTotal: 2, siteReady: 2, runState })),
      ).toBe(false);
    }
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
      constructionChosen: true,
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

    // the 5c tighten's own words: an incomplete run is named WITH its state
    const runRefused = stageStates(
      facts({ siteTotal: 2, siteReady: 2, runState: "refused" }),
    ).find((s) => s.id === "deliver");
    expect(runRefused?.blockedReason).toContain("refused");
    const noRun = stageStates(
      facts({ siteTotal: 2, siteReady: 2 }),
    ).find((s) => s.id === "deliver");
    expect(noRun?.blockedReason).toContain("no run exists yet");
  });

  it("names the SHORTFALL, not just the rule — how many sites are still owed", () => {
    // The design's gate voice ("mark 2 more caps first"): a blocked control that says
    // only the rule leaves the operator counting rows by hand. The count is arithmetic
    // over facts already in hand — total minus the two verdicts — never a new status.
    const underReview = stageStates(
      facts({ siteTotal: 5, siteReady: 2, siteFlagged: 1, runState: "done" }),
    ).find((s) => s.id === "deliver");
    expect(underReview?.blockedReason).toContain("2 of 5");
    // and the rule itself survives the addition — the sentence still says WHY
    expect(underReview?.blockedReason).toContain("ready, or flagged");

    const one = stageStates(
      facts({ siteTotal: 3, siteReady: 2, runState: "done" }),
    ).find((s) => s.id === "deliver");
    expect(one?.blockedReason).toContain("1 of 3");
  });
});

describe("the rail's sub-line speaks the LIVE counts", () => {
  it("adjust names how many sites are flagged, in the design's own words", () => {
    expect(stageSubLine("adjust", facts({ siteTotal: 4, siteFlagged: 2, runState: "done" })))
      .toBe("2 flagged to rework.");
    // one flag is still a flag — the count is the point, not the plural
    expect(stageSubLine("adjust", facts({ siteTotal: 4, siteFlagged: 1, runState: "done" })))
      .toBe("1 flagged to rework.");
  });

  it("adjust says 'nothing to rework' once a run exists and no flags remain", () => {
    expect(stageSubLine("adjust", facts({ siteTotal: 2, siteReady: 2, runState: "done" })))
      .toContain("Nothing flagged");
    // before any run there is no count to speak — the static one-liner is the truth
    expect(stageSubLine("adjust", facts({ siteTotal: 2 }))).toBe(STAGE_INFO.adjust.oneLiner);
  });

  it("declare counts reviewed sites out of the total", () => {
    expect(stageSubLine("declare", facts({ siteTotal: 5, siteReady: 2 })))
      .toBe("2 of 5 sites reviewed.");
    expect(stageSubLine("declare", facts({ siteTotal: 5, siteReady: 5 })))
      .toBe("All 5 sites reviewed.");
    expect(stageSubLine("declare", facts())).toBe(STAGE_INFO.declare.oneLiner);
  });

  it("intake counts sites and names the centre shortfall (the declare gate's predicate)", () => {
    // Detection has not run: the sites in hand are the case's curated suggestions.
    expect(stageSubLine("intake", facts({ siteTotal: 3 })))
      .toBe("3 sites suggested — detection has not run yet.");
    // A site with no usable centre cannot be aligned; the honest predicate behind
    // "Continue to Declare" is every site having one, so the shortfall is spoken.
    expect(
      stageSubLine(
        "intake",
        facts({ siteTotal: 5, siteCentred: 3, detectionDone: true, choicesComplete: true }),
      ),
    ).toBe("2 of 5 sites still without a centre.");
    expect(
      stageSubLine(
        "intake",
        facts({
          siteTotal: 5,
          siteCentred: 5,
          siteDetected: 5,
          detectionDone: true,
          choicesComplete: false,
        }),
      ),
    ).toBe("5 sites detected — case-level choices still open.");
    expect(
      stageSubLine(
        "intake",
        facts({
          siteTotal: 5,
          siteCentred: 5,
          siteDetected: 5,
          detectionDone: true,
          choicesComplete: true,
        }),
      ),
    ).toBe("5 sites detected — case-level choices made.");
  });

  it("a payload that does not carry the centre count never invents a shortfall", () => {
    // The worklist's SiteRollup has no centred column, so `siteCentred` is absent
    // there — silence, not zero. Claiming "5 of 5 without a centre" off a fact the
    // payload never carried would be the client inventing a status.
    expect(
      stageSubLine(
        "intake",
        facts({ siteTotal: 5, siteDetected: 5, detectionDone: true, choicesComplete: true }),
      ),
    ).toBe("5 sites detected — case-level choices made.");
  });

  it("the rail never claims detection over a cap the operator marked by hand", () => {
    // Audit 2026-07-31. Detection finds 8 of 10 (the fleet number the missed-cap
    // door exists for); the operator marks the other two, which become session-only
    // sites with no proposal behind them. "10 sites detected" asserted the detector
    // saw caps the same screen's own panel says it missed.
    expect(
      stageSubLine(
        "intake",
        facts({
          siteTotal: 10,
          siteCentred: 10,
          siteDetected: 8,
          detectionDone: true,
          choicesComplete: true,
        }),
      ),
    ).toBe("8 detected, 2 marked by hand — case-level choices made.");
  });

  it("a payload that does not carry the detected count drops the word rather than guessing", () => {
    // The worklist row projects no proposals, so `siteDetected` is absent there. A
    // neutral count is the honest sentence; "5 sites detected" would be a claim the
    // payload never supported.
    expect(
      stageSubLine("intake", facts({ siteTotal: 5, detectionDone: true, choicesComplete: true })),
    ).toBe("5 sites — case-level choices made.");
  });

  it("deliver's sub-line reports the verdicts, then the release", () => {
    const resolved = facts({ siteTotal: 3, siteReady: 2, siteFlagged: 1,
                             runState: "done", constructionChosen: true });
    expect(stageSubLine("deliver", resolved)).toBe(
      "2 ready, 1 flagged — assurance ready to review.",
    );
    expect(stageSubLine("deliver", { ...resolved, confirmed: true })).toContain("Confirmed");
    expect(stageSubLine("deliver", { ...resolved, confirmed: true, released: true })).toContain(
      "released",
    );
    // unreachable: there are no verdicts to report yet, so the one-liner stands
    expect(stageSubLine("deliver", facts({ siteTotal: 3 }))).toBe(STAGE_INFO.deliver.oneLiner);
  });

  it("stageStates carries the sub-line for every stage", () => {
    const states = stageStates(
      facts({ siteTotal: 4, siteReady: 3, siteFlagged: 1, runState: "done" }),
    );
    for (const state of states) {
      expect(state.subLine).toMatch(/\S/);
    }
    expect(states.find((s) => s.id === "adjust")?.subLine).toBe("1 flagged to rework.");
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

  it("declare completes when every site is REVIEWED — ready via the tick (5b, AM-8)", () => {
    // Updated DELIBERATELY for slice 5b: the panes and the review tick landed, so
    // 5a's interim every-site-declared rule retires — Declare is done when the
    // operator has ATTESTED every site over the live panes, and only then.
    expect(isComplete("declare", facts())).toBe(false); // nothing to declare ≠ done
    expect(isComplete("declare", facts({ siteTotal: 2, siteDeclared: 2 }))).toBe(false);
    expect(
      isComplete("declare", facts({ siteTotal: 2, siteDeclared: 2, siteReady: 1 })),
    ).toBe(false);
    expect(
      isComplete("declare", facts({ siteTotal: 2, siteDeclared: 2, siteReady: 2 })),
    ).toBe(true);
    // flagged is 5c's run evidence, not a review — it does not complete Declare
    expect(
      isComplete(
        "declare",
        facts({ siteTotal: 2, siteDeclared: 2, siteReady: 1, siteFlagged: 1 }),
      ),
    ).toBe(false);
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

  it("deliver completes only on RELEASE — the rail truth (slice 8)", () => {
    const done = facts({ siteTotal: 1, siteReady: 1, runState: "done" });
    expect(isComplete("deliver", done)).toBe(false);
    // a confirmation alone is a step along the way, not delivery
    expect(isComplete("deliver", { ...done, confirmed: true })).toBe(false);
    expect(
      isComplete("deliver", { ...done, confirmed: true, released: true }),
    ).toBe(true);
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

  it("a fully resolved case resumes at deliver, flagged or clean — once a part is picked", () => {
    expect(
      furthestStage(
        facts({ siteTotal: 3, siteReady: 2, siteFlagged: 1, runState: "done",
                constructionChosen: true }),
      ),
    ).toBe("deliver");
    expect(
      furthestStage(facts({ siteTotal: 2, siteReady: 2, runState: "done",
                            confirmed: true, constructionChosen: true })),
    ).toBe("deliver");
    // and WITHOUT one it resumes at the library — the furthest stage that is actually
    // reachable, which is the whole contract of this function
    expect(
      furthestStage(facts({ siteTotal: 2, siteReady: 2, runState: "done" })),
    ).toBe("library");
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
      sites: { total: 3, declared: 3, ready: 2, flagged: 1 },
      run_state: "done",
      confirmed: false,
      released: false,
      detected: true,
      choices_complete: true,
    });
    const fromDetail = factsFromCaseSession({
      sites: [
        { tooth: 3, status: "ready", center: [0, 0, 0] },
        { tooth: 14, status: "ready", center: [1, 0, 0] },
        { tooth: 19, status: "flagged", center: [2, 0, 0] },
      ],
      detection: {
        proposals: [{ tooth_guess: 3 }, { tooth_guess: 14 }, { tooth_guess: 19 }],
      },
      choices: { complete: true, effective_construction: { value: "dess/ti-base" } },
      session: { run_state: "done", confirmed: false, released: false },
    });
    // The centre count and the DETECTED count are the two facts only the DETAIL
    // carries: the worklist's SiteRollup has no centred column and projects no
    // proposals (bff/resources/case_sessions.py:69-73), and the worklist renders no
    // rail, so the row leaves both ABSENT rather than guessing a zero. On every fact
    // the rules share, the two projections still agree exactly.
    const { siteCentred, siteDetected, ...sharedFromDetail } = fromDetail;
    expect(fromRow).toEqual(sharedFromDetail);
    expect(siteCentred).toBe(3);
    expect(siteDetected).toBe(3);
    expect(fromRow.siteCentred).toBeUndefined();
    expect(fromRow.siteDetected).toBeUndefined();
  });

  it("counts only sites with a usable centre — a null centre is not one", () => {
    // A curated site can reach the surface with no centre at all
    // (bff/resources/case_sessions.py:459-461), and a session-only site has none
    // until a human marks it. Neither can be aligned, so neither counts.
    const projected = factsFromCaseSession({
      sites: [
        { tooth: 3, status: "detected", center: [0, 0, 0] },
        { tooth: 14, status: "detected", center: null },
        { tooth: 19, status: "declared", center: [2, 0, 0] },
      ],
      detection: { proposals: [] },
      choices: { complete: false },
      session: { run_state: "none", confirmed: false, released: false },
    });
    expect(projected.siteTotal).toBe(3);
    expect(projected.siteCentred).toBe(2);
    // and the gate itself is UNCHANGED — a centreless site does not close Declare off
    // (no client word to tighten it; doing so would newly block cases that work today)
    expect(isReachable("declare", projected)).toBe(true);
  });

  it("the rail's centre count uses the SAME predicate as the picker and the framing hint", () => {
    // Audit 2026-07-31: `center !== null` and intake's `siteCentre` were two
    // definitions of "has a usable centre". `SiteView.center` is an unvalidated
    // pass-through of the case record (case_sessions.py:495-496) — only the
    // operator-mark path validates 3-and-finite (case_sessions.py:1264) — so a
    // curated `[12.4, 3.1]` had the rail printing "5 sites detected" while the same
    // screen's site list printed "has no centre yet" and the picker skipped it.
    const projected = factsFromCaseSession({
      sites: [
        { tooth: 3, status: "detected", center: [0, 0, 0] },
        { tooth: 14, status: "detected", center: [12.4, 3.1] },
        { tooth: 19, status: "detected", center: [1, Number.NaN, 2] },
        { tooth: 30, status: "detected", center: [1, 2, Number.POSITIVE_INFINITY] },
      ],
      detection: { proposals: [] },
      choices: { complete: true },
      session: { run_state: "none", confirmed: false, released: false },
    });
    expect(projected.siteTotal).toBe(4);
    expect(projected.siteCentred).toBe(1);
    expect(stageSubLine("intake", { ...projected, detectionDone: true })).toBe(
      "3 of 4 sites still without a centre.",
    );
  });

  it("counts DETECTED sites as the ones a proposal actually matched", () => {
    // The missed-cap door creates session-only sites with a marked centre and no
    // entry in detection.proposals (case_sessions.py:503-513). They are sites; they
    // are not detections.
    const projected = factsFromCaseSession({
      sites: [
        { tooth: 3, status: "detected", center: [0, 0, 0] },
        { tooth: 14, status: "detected", center: [8, 0, 0] },
        { tooth: 19, status: "detected", center: [16, 0, 0] },
      ],
      detection: { proposals: [{ tooth_guess: 3 }, { tooth_guess: null }] },
      choices: { complete: true },
      session: { run_state: "none", confirmed: false, released: false },
    });
    expect(projected.siteTotal).toBe(3);
    // the null-guess proposal matched no site — it is a detection without a tooth,
    // which the site list already counts separately as "unassigned"
    expect(projected.siteDetected).toBe(1);
  });

  it("detection facts project from the payload, not from sites existing", () => {
    const undetected = factsFromCaseSession({
      sites: [{ tooth: 3, status: "detected", center: [0, 0, 0] }],
      detection: null,
      choices: { complete: false },
      session: { run_state: "none", confirmed: false, released: false },
    });
    expect(undetected.detectionDone).toBe(false);
    expect(undetected.choicesComplete).toBe(false);
    expect(undetected.siteTotal).toBe(1); // curated suggestions predate detection
    expect(undetected.siteDetected).toBe(0); // no detection record, no detections
  });

  it("in-flight statuses (declared/previewed/adjusted) count as neither ready nor flagged", () => {
    const projected = factsFromCaseSession({
      sites: [
        { tooth: 3, status: "detected", center: [0, 0, 0] },
        { tooth: 14, status: "declared", center: [1, 0, 0] },
        { tooth: 19, status: "previewed", center: [2, 0, 0] },
        { tooth: 30, status: "adjusted", center: [3, 0, 0] },
        { tooth: 31, status: "ready", center: [4, 0, 0] },
      ],
      detection: null,
      choices: { complete: false },
      session: { run_state: "done", confirmed: false, released: false },
    });
    expect(projected.siteTotal).toBe(5);
    expect(projected.siteDeclared).toBe(4); // everything past "detected" is an act
    expect(projected.siteReady).toBe(1);
    expect(projected.siteFlagged).toBe(0);
    expect(isReachable("deliver", projected)).toBe(false);
  });
});
