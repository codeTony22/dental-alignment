/**
 * Static-markup tests for the workflow rail. Collapsed to FOUR stages (client, 2026-07-26:
 * "ONE cohesive flow" — the separate Library-selection stop is deleted, its lists live inside
 * Mark & declare). The rail is NAVIGATION as well as a read-out, so what matters is that it
 * names the four stages in order, ticks only what the case has satisfied, and refuses — with
 * the reason on the control itself — to open a stage that has nothing to act on.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { WorkflowRail } from "./WorkflowRail";
import { workflowStages } from "../domain/workflow";

const FRESH_CASE = workflowStages({
  hasCase: true,
  siteCount: 0,
  declaredSiteCount: 0,
  selectionComplete: false,
  reviewedAll: false,
  hasRun: false,
  runStale: false,
});

const DONE = workflowStages({
  hasCase: true,
  siteCount: 1,
  declaredSiteCount: 1,
  selectionComplete: true,
  reviewedAll: true,
  hasRun: true,
  runStale: false,
});

describe("WorkflowRail", () => {
  it("names the collapsed flow's four stages in their order", () => {
    const html = renderToStaticMarkup(
      <WorkflowRail stages={FRESH_CASE} current="mark" onSelect={() => undefined} />,
    );
    for (const label of ["Case", "Mark &amp; declare", "Verify", "Process"]) {
      expect(html).toContain(label);
    }
    // the deleted stage must not survive as a label anywhere on the rail
    expect(html).not.toContain("Library selection");
    expect(html.indexOf("Mark &amp; declare")).toBeLessThan(html.indexOf("Verify"));
    expect(html.indexOf("Verify")).toBeLessThan(html.indexOf("Process"));
  });

  it("marks the current stage for assistive tech and for the eye", () => {
    const html = renderToStaticMarkup(
      <WorkflowRail stages={FRESH_CASE} current="mark" onSelect={() => undefined} />,
    );
    expect(html).toContain('aria-current="step"');
    expect(html.split('aria-current="step"').length - 1).toBe(1);
    expect(html).toContain("workflow-rail__step--current");
  });

  it("ticks only what the case has actually satisfied", () => {
    const fresh = renderToStaticMarkup(
      <WorkflowRail stages={FRESH_CASE} current="mark" onSelect={() => undefined} />,
    );
    const done = renderToStaticMarkup(<WorkflowRail stages={DONE} current="process" onSelect={() => undefined} />);
    expect(fresh.split("✓").length - 1).toBe(1); // the loaded case only
    expect(done.split("✓").length - 1).toBe(4);
  });

  it("disables an unreachable stage and puts the reason on the control", () => {
    const html = renderToStaticMarkup(
      <WorkflowRail stages={FRESH_CASE} current="mark" onSelect={() => undefined} />,
    );
    // nothing is marked yet, so verify/process cannot be opened
    expect(html.split("disabled").length - 1).toBe(2);
    expect(html).toContain("Mark at least one healing cap first.");
  });
});

describe("WorkflowRail — accessible naming", () => {
  it("names each step by its stage, not by its detail line alone", () => {
    const html = renderToStaticMarkup(
      <WorkflowRail stages={FRESH_CASE} current="mark" onSelect={() => undefined} />,
    );
    expect(html).toContain('aria-label="Step 1 — Case: scan loaded"');
    // an unreachable stage announces WHICH stage, then why — it read as a bare
    // "Mark at least one healing cap first." with no subject before this
    expect(html).toContain(
      'aria-label="Step 3 — Verify: Mark at least one healing cap first."',
    );
  });
});
