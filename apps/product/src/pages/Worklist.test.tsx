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
    // Parity slice: the one-string "3 declared / 2 ready / 1 flagged" became three
    // CHIPS in the demo's band tones (the 20-scan morning scans colours, not a
    // sentence) — same numbers, same rollup, asserted per chip.
    expect(html).toContain("3 declared");
    expect(html).toContain("2 ready");
    expect(html).toContain("1 flagged");
    expect(html).toMatch(/chip--band-review[^>]*>1 flagged/); // flagged wears amber
    expect(html).toContain("done");
    expect(html).toContain("unconfirmed");
  });

  /**
   * THE COMP'S CARD CLOTHES (client comp, page pass 2026-08-02). The comp's intake
   * worklist is a GRID of compact cards — name + site-count chip, a discovery meta
   * line, the teeth, and one segment bar per site. Every fact on the card is the
   * BFF's own (counts, model, bytes, teeth); the comp's batch codes and clinic names
   * have no source here and are NOT invented.
   */
  it("renders as a grid of comp cards — count chip, discovery meta, teeth, segments", () => {
    const html = screenHtml({ kind: "ok", data: [row] });
    expect(html).toContain('class="worklist__grid"');
    expect(html).toMatch(/data-role="row-sites"[^>]*>3 sites</);
    // discovery facts, real ones: rollup total · suggested model · scan size
    expect(html).toContain("3 cap sites · conical-4x4 · 31.8 MB");
    expect(html).toContain("teeth 19, 30");
    // one bar per site, coloured by the served counts: 2 ready, 1 flagged
    expect((html.match(/worklist-card__bar worklist-card__bar--pass/g) ?? []).length).toBe(2);
    expect((html.match(/worklist-card__bar worklist-card__bar--flag/g) ?? []).length).toBe(1);
  });

  it("speaks singular for a one-site case and drops absent discovery facts", () => {
    const html = screenHtml({
      kind: "ok",
      data: [
        worklistRow({
          sites: { total: 1, declared: 0, ready: 0, flagged: 0 },
          suggested_model: null,
          scan_bytes: null,
          teeth: [],
        }),
      ],
    });
    expect(html).toMatch(/data-role="row-sites"[^>]*>1 site</);
    expect(html).toContain("1 cap site");
    // no model, no bytes, no teeth — the line carries only what discovery stated
    expect(html).not.toContain("null");
    expect(html).not.toContain("NaN");
    expect(html).not.toContain("teeth <");
  });

  it("links to the session's furthest stage (AM-7 resume)", () => {
    const html = screenHtml({ kind: "ok", data: [row] });
    expect(html).toContain('href="/case/case-flagged/library"');
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

describe("the page head", () => {
  it("keeps the honest title and wears the comp's lead — no upload implication", () => {
    const html = screenHtml({ kind: "ok", data: [worklistRow()] });
    expect(html).toContain("Worklist");
    // the comp's lead promises "or drop a new scan" — this product has no browser
    // upload (see the scan-arrival pins below), so the lead carries only the true half
    expect(html).toContain("declare the truth in Alignment");
    expect(html).not.toContain("drop a new scan");
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

/**
 * THE SCAN-ARRIVAL PANEL (design flow.dc.html 76-83; gap "a scan arrives", 2026-07-31).
 *
 * The prototype's dashed "Drop a scan file" zone is scenery — its `browseUpload` is
 * `() => this.pickScan(SCANS[0].id)` (flow.dc.html:1105), which selects a fixture. This
 * product ships the honest affordance instead, so these tests police the two halves of
 * honesty: it must SAY how scans actually reach this installation, and it must offer no
 * control that could be mistaken for an upload.
 */
describe("the scan-arrival panel", () => {
  it("states the real route onto this worklist", () => {
    const html = screenHtml({ kind: "ok", data: [worklistRow()] });
    expect(html).toContain('data-role="scan-arrival"');
    expect(html).toContain("How a new scan reaches this worklist");
    // the two rules an operator with a folder in hand needs, rendered (not just
    // exported): what counts as the scan file, and what happens to the extras
    expect(html).toContain("Discovery looks for STL files");
    expect(html).toContain("first by name");
  });

  it("offers nothing that behaves like an upload", () => {
    const html = screenHtml({ kind: "ok", data: [worklistRow()] });
    // scoped to the panel's own markup: a control elsewhere on the screen is not this
    // test's business, but a control INSIDE the zone is exactly what must never exist
    const panel = html.slice(html.indexOf('data-role="scan-arrival"'));
    expect(panel).not.toContain("<button");
    expect(panel).not.toContain("<input");
    expect(panel).not.toContain("browse files");
    expect(panel).not.toContain("Drop a scan file");
    expect(panel).toContain("There is no browser upload");
  });

  it("is loudest on the empty worklist — the one time the operator asks 'where?'", () => {
    const html = screenHtml({ kind: "ok", data: [] });
    expect(html).toContain('data-role="worklist-empty"');
    expect(html).toContain('data-role="scan-arrival"');
  });

  it("stays out of the way while loading and when the BFF is unreachable", () => {
    expect(screenHtml({ kind: "loading" })).not.toContain('data-role="scan-arrival"');
    expect(
      screenHtml({ kind: "error", detail: "the case service is unreachable" }),
    ).not.toContain('data-role="scan-arrival"');
  });
});
