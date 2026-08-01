/**
 * The rail's promises (slice 2): four stages with number/title/one-liner, reachable
 * stages are links, blocked stages are inert AND explain why in a sentence, the
 * current stage is marked, completed stages tick. renderToStaticMarkup + StaticRouter
 * — the repo's node-environment component convention.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { StaticRouter } from "react-router-dom";
import { stageStates, type FlowFacts } from "../domain/flow";
import { StageRail } from "./StageRail";

function railHtml(facts: FlowFacts, current: Parameters<typeof StageRail>[0]["current"] = "intake") {
  return renderToStaticMarkup(
    <StaticRouter location={`/case/c1/${current}`}>
      <StageRail states={stageStates(facts)} current={current} caseId="c1" />
    </StaticRouter>,
  );
}

const freshFacts: FlowFacts = {
  siteTotal: 2,
  siteDeclared: 0,
  siteReady: 0,
  siteFlagged: 0,
  runState: "none",
  confirmed: false,
  released: false,
  // intake done per slice 4's rule: detection ran AND the case-level choices made
  detectionDone: true,
  choicesComplete: true,
      constructionChosen: true,
};

describe("the stage rail", () => {
  it("renders all five stages with their numbers and the CLIENT'S titles", () => {
    const html = railHtml(freshFacts);
    for (const title of ["Intake", "Alignment", "Adjustment",
                         "Construction library", "Delivery"]) {
      expect(html).toContain(title);
    }
    // intake already ticks (detection ran, choices made); the rest still number
    expect(html).toContain(">✓<");
    expect(html).toContain(">2<");
    expect(html).toContain(">5<");
  });

  it("reachable stages are links into the case's routes", () => {
    const html = railHtml(freshFacts);
    expect(html).toContain('href="/case/c1/intake"');
    expect(html).toContain('href="/case/c1/declare"');
  });

  it("blocked stages are not links and carry their why-sentence", () => {
    const html = railHtml(freshFacts);
    expect(html).not.toContain('href="/case/c1/adjust"');
    expect(html).not.toContain('href="/case/c1/deliver"');
    expect(html).toContain("No run exists yet");
    expect(html).toContain("awaiting review");
  });

  it("marks the current stage for assistive tech", () => {
    const html = railHtml(freshFacts, "declare");
    expect(html).toContain('aria-current="step"');
  });

  it("ticks completed stages instead of numbering them", () => {
    const resolved: FlowFacts = {
      siteTotal: 2,
      siteDeclared: 2,
      siteReady: 2,
      siteFlagged: 0,
      runState: "done",
      confirmed: false,
      released: false,
      detectionDone: true,
      choicesComplete: true,
      constructionChosen: true,
    };
    const html = railHtml(resolved, "deliver");
    // intake, declare, adjust AND the library are complete on a clean, run case that
    // has picked its part — four ticks, with only Delivery left to earn its own
    expect(html.match(/✓/g)?.length).toBe(4);
  });

  it("the sub-line under a stage speaks the LIVE count, not the static one-liner", () => {
    const flagged: FlowFacts = {
      siteTotal: 4,
      siteDeclared: 4,
      siteReady: 3,
      siteFlagged: 1,
      runState: "done",
      confirmed: false,
      released: false,
      detectionDone: true,
      choicesComplete: true,
      constructionChosen: true,
    };
    const html = railHtml(flagged, "adjust");
    expect(html).toContain("1 flagged to rework.");
    // the fixed prose it replaces must be GONE — a reachable Adjust that says
    // "Optional — refit flagged sites" while one site is flagged is the rail lying
    expect(html).not.toContain("Optional — refit flagged sites");
    expect(html).toContain("3 of 4 sites reviewed.");
  });

  it("falls back to the one-liner where the facts hold no count to speak", () => {
    const empty: FlowFacts = {
      siteTotal: 0,
      siteDeclared: 0,
      siteReady: 0,
      siteFlagged: 0,
      runState: "none",
      confirmed: false,
      released: false,
      detectionDone: false,
      choicesComplete: false,
      constructionChosen: true,
    };
    // An empty case has nothing to count, so Intake keeps its standing sentence —
    // "0 of 0 sites" would be noise dressed as information.
    expect(railHtml(empty)).toContain("Scan in, sites detected");
  });

  it("Intake's sub-line names the centre shortfall behind the Declare gate", () => {
    const halfMarked: FlowFacts = {
      siteTotal: 4,
      siteDeclared: 0,
      siteReady: 0,
      siteFlagged: 0,
      siteCentred: 2,
      runState: "none",
      confirmed: false,
      released: false,
      detectionDone: true,
      choicesComplete: true,
      constructionChosen: true,
    };
    expect(railHtml(halfMarked)).toContain("2 of 4 sites still without a centre.");
  });

  it("a skipped adjust never blocks the deliver link (plan §4)", () => {
    const flagged: FlowFacts = {
      siteTotal: 3,
      siteDeclared: 3,
      siteReady: 2,
      siteFlagged: 1,
      runState: "done",
      confirmed: false,
      released: false,
      detectionDone: true,
      choicesComplete: true,
      constructionChosen: true,
    };
    const html = railHtml(flagged, "declare");
    expect(html).toContain('href="/case/c1/deliver"');
  });
});
