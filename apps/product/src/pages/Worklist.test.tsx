/**
 * The worklist screen's promises (slice 2b): a row states doctor, jaw, the rollup and
 * both chips, and links to its resume target; the markup shows blocked-first order;
 * the two empty states are stated in words (no cases; BFF unreachable); a malformed
 * row degrades to an inert unreadable entry instead of taking the list down.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { StaticRouter } from "react-router-dom";
import { worklistErrorRow, worklistRow } from "../testing/fixtures";
import { WorklistPage, WorklistScreen } from "./Worklist";

function screenHtml(state: Parameters<typeof WorklistScreen>[0]["state"]) {
  return renderToStaticMarkup(
    <StaticRouter location="/">
      <WorklistScreen state={state} />
    </StaticRouter>,
  );
}

describe("a worklist row", () => {
  const row = worklistRow({
    id: "case-flagged",
    doctor: "Dr. Rivera",
    jaw: "lower",
    sites: { total: 3, declared: 3, ready: 2, flagged: 1 },
    run_state: "done",
  });

  it("states doctor, jaw, the site rollup and both chips", () => {
    const html = screenHtml({ kind: "ok", data: [row] });
    expect(html).toContain("Dr. Rivera");
    expect(html).toContain("lower");
    expect(html).toContain("3 declared / 2 ready / 1 flagged");
    expect(html).toContain("done");
    expect(html).toContain("unconfirmed");
  });

  it("links to the session's furthest stage (AM-7 resume)", () => {
    const html = screenHtml({ kind: "ok", data: [row] });
    expect(html).toContain('href="/case/case-flagged/deliver"');
  });

  it("the run chip carries AM-3's live state (5c) — queued|running|done|refused", () => {
    for (const run_state of ["queued", "running", "done", "refused"] as const) {
      const html = screenHtml({
        kind: "ok",
        data: [worklistRow({ run_state })],
      });
      expect(html).toMatch(
        new RegExp(`data-role="row-run"[^>]*data-state="${run_state}"`),
      );
      expect(html).toContain(`>${run_state}<`); // the chip's words are the state's
    }
  });
});

describe("the blocked-first order reaches the markup", () => {
  it("renders flagged before in-progress before untouched before confirmed", () => {
    const html = screenHtml({
      kind: "ok",
      data: [
        worklistRow({
          id: "case-confirmed",
          sites: { total: 1, declared: 1, ready: 1, flagged: 0 },
          run_state: "done",
          confirmed: true,
        }),
        worklistRow({ id: "case-untouched" }),
        worklistRow({
          id: "case-flagged",
          sites: { total: 2, declared: 2, ready: 1, flagged: 1 },
          run_state: "done",
        }),
        worklistRow({
          id: "case-progress",
          sites: { total: 2, declared: 1, ready: 0, flagged: 0 },
        }),
      ],
    });
    const positions = [
      "case-flagged",
      "case-progress",
      "case-untouched",
      "case-confirmed",
    ].map((id) => html.indexOf(`href="/case/${id}/`));
    expect(positions.every((p) => p >= 0)).toBe(true);
    expect([...positions].sort((a, b) => a - b)).toEqual(positions);
  });
});

describe("the empty states", () => {
  it("no cases: says so instead of showing an empty void", () => {
    const html = screenHtml({ kind: "ok", data: [] });
    expect(html).toContain("No cases yet");
  });

  it("BFF unreachable: the stated banner, not a blank screen", () => {
    const html = screenHtml({ kind: "error", detail: "fetch failed" });
    expect(html).toContain("The case service is unreachable.");
    expect(html).toContain("fetch failed");
  });
});

describe("a malformed row", () => {
  it("degrades to an inert unreadable entry; readable rows still render", () => {
    const html = screenHtml({
      kind: "ok",
      data: [worklistRow({ id: "case-good" }), { id: "case-broken" }],
    });
    expect(html).toContain('href="/case/case-good/');
    expect(html).toContain("could not be read");
    expect(html).toContain("case-broken");
    expect(html).not.toContain('href="/case/case-broken/');
  });
});

describe("an error row (the BFF's per-row contract, slice 5a)", () => {
  it("renders the BFF's own refusal words, inert, above readable rows", () => {
    const html = screenHtml({
      kind: "ok",
      data: [
        worklistRow({ id: "case-good" }),
        worklistErrorRow({
          id: "case-corrupt",
          error: "corrupt session file session.json — refusing to silently reset",
        }),
      ],
    });
    // the BFF's words, verbatim — the row states its trouble instead of zeros
    expect(html).toContain("refusing to silently reset");
    expect(html).toContain("case-corrupt");
    expect(html).not.toContain('href="/case/case-corrupt/');
    // and it outranks the readable row (band -1: most blocked there is)
    expect(html.indexOf("case-corrupt")).toBeLessThan(
      html.indexOf('href="/case/case-good/'),
    );
  });
});

describe("the worklist container", () => {
  it("shows its pre-flight loading state (effects do not run statically)", () => {
    const html = renderToStaticMarkup(
      <StaticRouter location="/">
        <WorklistPage />
      </StaticRouter>,
    );
    expect(html).toContain("Loading the worklist");
  });
});
