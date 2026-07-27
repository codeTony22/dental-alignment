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
  siteReady: 0,
  siteFlagged: 0,
  runState: "none",
  confirmed: false,
};

describe("the stage rail", () => {
  it("renders all four stages with their numbers and titles", () => {
    const html = railHtml(freshFacts);
    for (const title of ["Intake", "Declare", "Adjust", "Deliver"]) {
      expect(html).toContain(title);
    }
    // intake already ticks (detection yielded sites); the rest still number
    expect(html).toContain(">✓<");
    expect(html).toContain(">2<");
    expect(html).toContain(">4<");
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
      siteReady: 2,
      siteFlagged: 0,
      runState: "done",
      confirmed: false,
    };
    const html = railHtml(resolved, "deliver");
    // intake, declare and adjust are complete on a clean, run case
    expect(html.match(/✓/g)?.length).toBe(3);
  });

  it("a skipped adjust never blocks the deliver link (plan §4)", () => {
    const flagged: FlowFacts = {
      siteTotal: 3,
      siteReady: 2,
      siteFlagged: 1,
      runState: "done",
      confirmed: false,
    };
    const html = railHtml(flagged, "declare");
    expect(html).toContain('href="/case/c1/deliver"');
  });
});
