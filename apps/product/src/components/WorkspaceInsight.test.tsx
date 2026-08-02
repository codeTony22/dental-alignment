/**
 * THE WORKSPACE'S PROVENANCE POPOVER, statically rendered per the repo convention
 * (renderToStaticMarkup in NODE — no jsdom, no events; the container's fetch effect
 * and the Escape/click-outside listeners are therefore uncovered here by
 * construction, exactly as `useDialogEscape.ts` states of itself). What belongs here
 * is which words render in which TONE, and above all the anti-arithmetic pin: this
 * surface must never compute a verdict this app already refuses to compute anywhere
 * else (domain/provenance.ts's own note on the design prototype's forbidden
 * deviation()/verdict()/tolerance).
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { WorkspaceInsightView, type WorkspaceInsightViewProps } from "./WorkspaceInsight";
import {
  activityEntry,
  caseActivityView,
  siteAcceptanceMetric,
  siteAcceptanceView,
  siteAdjustment,
} from "../testing/fixtures";

function view(overrides: Partial<WorkspaceInsightViewProps> = {}) {
  return renderToStaticMarkup(
    <WorkspaceInsightView
      tooth={19}
      caseId="case-a"
      open={false}
      onToggle={() => undefined}
      acceptance={{ kind: "ok", data: siteAcceptanceView() }}
      activity={{ kind: "ok", data: caseActivityView() }}
      {...overrides}
    />,
  );
}

describe("the toggle names what the popover can actually offer", () => {
  /* In the case HEADER (client 2026-08-02: "yes do this" to a universal entry point)
     there is no active site — the instance is permanently tooth-less, and a label
     promising site numbers there would promise a section that always reads "no active
     site". The label follows the tooth: with one, both halves; without, the log. */
  it("names both halves when a site is active", () => {
    // abbreviated to fit the comp's single-row strip; it still labels CONTENT and
    // never promises a verdict, which is the rule the wording answers to
    expect(view({ tooth: 19 })).toContain("Numbers &amp; log");
  });

  it("says 'Case log' alone when no site is active — the header's standing state", () => {
    const html = view({ tooth: null });
    expect(html).toContain(">Case log<");
    expect(html).not.toContain("Site numbers");
  });
});

describe("closed — the toggle only, nothing else", () => {
  it("renders the labelled toggle, collapsed", () => {
    const html = view({ open: false });
    expect(html).toContain('data-role="insight-toggle"');
    expect(html).toContain("Numbers &amp; log");
    expect(html).toMatch(/data-role="insight-toggle"[^>]*aria-expanded="false"/);
  });

  it("renders NO panel at all while closed", () => {
    const html = view({ open: false });
    expect(html).not.toContain('data-role="workspace-insight"');
  });
});

describe("open — a disclosure, deliberately NOT a modal dialog", () => {
  it("renders the panel with its own data-role", () => {
    const html = view({ open: true });
    expect(html).toContain('data-role="workspace-insight"');
    expect(html).toMatch(/data-role="insight-toggle"[^>]*aria-expanded="true"/);
  });

  it('carries neither role="dialog" NOR aria-modal — nothing behind it is inert', () => {
    // Retargeted 2026-08-02: the scout's own notes assumed role="dialog", which the
    // client direction for THIS control overturned in the same breath ("role=dialog
    // is wrong here — use an expanded/collapsed disclosure"). Every other overlay in
    // this app IS a modal dialog; this one is not, on purpose.
    const html = view({ open: true });
    expect(html).not.toContain('role="dialog"');
    expect(html).not.toContain("aria-modal");
  });

  it("the toggle names the panel via aria-controls — the standard disclosure wiring", () => {
    const html = view({ open: true });
    const panelId = /\sid="([^"]+)"/.exec(html)?.[1];
    expect(panelId).toBeTruthy();
    expect(html).toContain(`aria-controls="${panelId}"`);
  });
});

describe("THE ANTI-ARITHMETIC PIN — the server's band word wins, always", () => {
  it("a metric banded 'review' by the server renders the review chip even though its value reads past bands.review", () => {
    // If this surface ever re-derived a verdict from `value` vs `bands`, this metric
    // would render as a FAIL — bands.review is 0.5 and the value is 5.0. It must not.
    const html = view({
      acceptance: {
        kind: "ok",
        data: siteAcceptanceView({
          metrics: [
            siteAcceptanceMetric({
              key: "deviation_rms_mm",
              value: 5.0,
              display: "5.00 mm",
              band: "review",
              bands: { pass: 0.2, review: 0.5 },
            }),
          ],
        }),
      },
      open: true,
    });
    expect(html).toMatch(
      /data-role="acceptance-metric"[^>]*data-band="review"/,
    );
    expect(html).toContain("chip--band-review");
    expect(html).not.toContain("chip--band-fail");
  });
});

describe("missing and stale — never a pass, always visible", () => {
  it("a key in missing[] never renders as a measured metric, let alone a pass", () => {
    const html = view({
      acceptance: {
        kind: "ok",
        data: siteAcceptanceView({
          metrics: [siteAcceptanceMetric({ key: "rim_agreement_mm", band: "pass" })],
          missing: ["deviation_p90_mm"],
        }),
      },
      open: true,
    });
    expect(html).toMatch(/data-role="acceptance-missing"[^>]*data-metric="deviation_p90_mm"/);
    expect(html).not.toMatch(
      /data-role="acceptance-metric"[^>]*data-metric="deviation_p90_mm"/,
    );
    // its row carries the neutral chip, not the pass one
    const missingRow = html.slice(html.indexOf('data-role="acceptance-missing"'));
    expect(missingRow.slice(0, missingRow.indexOf("</li>"))).toContain("chip--band-missing");
  });

  it("a key in stale_metrics is visibly marked on its own row", () => {
    const html = view({
      acceptance: {
        kind: "ok",
        data: siteAcceptanceView({
          metrics: [siteAcceptanceMetric({ key: "guidance", band: "review" })],
          stale_metrics: ["guidance"],
        }),
      },
      open: true,
    });
    expect(html).toMatch(/data-role="metric-stale"/);
  });

  it("a metric NOT in stale_metrics carries no stale marker", () => {
    const html = view({
      acceptance: {
        kind: "ok",
        data: siteAcceptanceView({
          metrics: [siteAcceptanceMetric({ key: "guidance" })],
          stale_metrics: [],
        }),
      },
      open: true,
    });
    expect(html).not.toContain('data-role="metric-stale"');
  });
});

describe("acceptance absence — the 404 is a healthy answer, never the error tone", () => {
  it("renders the server's own pre-run sentence as a hint", () => {
    const html = view({
      acceptance: {
        kind: "error",
        detail: "no completed current run for case case-a",
        status: 404,
      },
      open: true,
    });
    expect(html).toContain('data-role="acceptance-absent"');
    expect(html).toContain("no completed current run for case case-a");
    expect(html).toMatch(/data-role="acceptance-absent"[^>]*data-tone="hint"/);
    expect(html).not.toMatch(/data-role="acceptance-absent"[^>]*role="alert"/);
  });

  it("keeps the standing failure tone for anything that is not the pre-run 404", () => {
    const html = view({
      acceptance: { kind: "error", detail: "the workspace could not be reached", status: 500 },
      open: true,
    });
    expect(html).toMatch(/data-role="acceptance-absent"[^>]*role="alert"/);
  });

  it("with no active site, the section says so — and the log still renders", () => {
    const html = view({ tooth: null, acceptance: null, open: true });
    expect(html).toContain('data-role="acceptance-empty"');
    expect(html).toContain('data-role="insight-activity"');
  });
});

describe("the case log — served order, verbatim words, honest emptiness", () => {
  it("renders entries in the server's own (newest-first) order", () => {
    const html = view({
      activity: {
        kind: "ok",
        data: caseActivityView({
          entries: [
            activityEntry({ event: "run-authorized", detail: "first" }),
            activityEntry({ event: "run-landed", detail: "second" }),
          ],
        }),
      },
      open: true,
    });
    expect(html.indexOf("run-authorized")).toBeGreaterThan(-1);
    expect(html.indexOf("run-authorized")).toBeLessThan(html.indexOf("run-landed"));
  });

  it("carries the event word, the detail and a UTC time for every entry", () => {
    const html = view({
      activity: {
        kind: "ok",
        data: caseActivityView({
          entries: [
            activityEntry({
              event: "site-adjusted",
              detail: "rotation — rotated +5.0° about the part axis",
              at: "2026-07-31T09:22:41+00:00",
              tooth: 19,
            }),
          ],
        }),
      },
      open: true,
    });
    expect(html).toContain("site-adjusted");
    expect(html).toContain("rotation — rotated +5.0° about the part axis");
    expect(html).toContain("2026-07-31 09:22 UTC");
    expect(html).toMatch(/data-role="activity-tooth"[^<]*·\s*tooth 19/);
  });

  it("omits the tooth marker on a case-level act (tooth is null)", () => {
    const html = view({
      activity: {
        kind: "ok",
        data: caseActivityView({
          entries: [activityEntry({ tooth: null })],
        }),
      },
      open: true,
    });
    expect(html).not.toContain('data-role="activity-tooth"');
  });

  it("says plainly that nothing has happened yet on an untouched case — not an error", () => {
    const html = view({
      activity: {
        kind: "ok",
        data: caseActivityView({ entries: [], recorded: 0, site_adjustments: [] }),
      },
      open: true,
    });
    expect(html).toContain('data-role="activity-empty"');
    expect(html).not.toContain('data-role="activity-error"');
  });

  it("carries `who` VERBATIM, disclaimer included — no actor is invented", () => {
    const html = view({
      activity: {
        kind: "ok",
        data: caseActivityView({
          site_adjustments: [siteAdjustment({ who: "operator (no identity is captured)" })],
        }),
      },
      open: true,
    });
    expect(html).toContain('data-role="adjustment-who"');
    expect(html).toContain("operator (no identity is captured)");
  });

  it("shows the window sentence only when recorded exceeds the window's own count", () => {
    const truncated = view({
      activity: {
        kind: "ok",
        data: caseActivityView({
          recorded: 137,
          entries: [activityEntry()],
        }),
      },
      open: true,
    });
    expect(truncated).toContain("Showing the last 1 of 137 acts recorded on this case.");

    const untouched = view({
      activity: {
        kind: "ok",
        data: caseActivityView({ recorded: 1, entries: [activityEntry()] }),
      },
      open: true,
    });
    expect(untouched).not.toContain("Showing the last");
  });
});
