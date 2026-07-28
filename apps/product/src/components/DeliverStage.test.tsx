/**
 * Deliver's surface (plan §4 Deliver; AM-1/AM-12), statically rendered per the repo
 * convention, around the client's 2026-07-27 corrections:
 *
 *  - #4 dispositions default to RELEASE: only a flagged row offers the withhold
 *    control; a clean row says "released" and asks nothing.
 *  - #5 the report is a MODAL: the stage carries the compact summary and one way in;
 *    the full table, the QC images and the row acts live behind it, with the confirm
 *    in its footer AND on the stage — one blocker list feeding both.
 *  - #6 delivery is one visible progression: Confirmed → Paid → Released, the payment
 *    stub labelled in words, the release naming what it will disclose BEFORE the act,
 *    and the artifacts grouped by site with sizes.
 *
 * The pure rules (blockers, steps, grouping, disclosure words) are
 * domain/deliver.test.ts's; the endpoint wiring is api/client.test.ts's.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { StaticRouter } from "react-router-dom";
import { DeliverStageView } from "./DeliverStage";
import { assuranceView, caseSessionDetail, siteView } from "../testing/fixtures";
import type { CaseSessionDetail } from "../api/client";

/** A detail whose session stands where Deliver opens: a done run, sites resolved. */
function deliverableDetail(
  overrides: Partial<CaseSessionDetail["session"]> = {},
): CaseSessionDetail {
  const base = caseSessionDetail({
    sites: [
      siteView({ tooth: 30, status: "flagged", declared_variant: "5020" }),
      siteView({ tooth: 19, status: "ready", declared_variant: "5020" }),
    ],
  });
  return {
    ...base,
    session: { ...base.session, run_state: "done", ...overrides },
  };
}

const CONFIRMED = {
  confirmed: true,
  confirmation: {
    at: "2026-07-27T12:00:00+00:00",
    run_id: "20260727-120000-abc123",
    evidence_sha256: "c0ffee".padEnd(64, "0"),
    dispositions: { "30": "release", "19": "release" },
    acknowledged_flags: [30],
  },
  release_preview: {
    file_count: 4,
    teeth: [19, 30],
    withheld_teeth: [],
    withheld_case_file_count: 0,
  },
};

const PAID = {
  payment_authorized: true,
  payment: { provider: "stub", at: "2026-07-27T12:01:00+00:00" },
};

const RELEASED = {
  released: true,
  release: {
    at: "2026-07-27T12:02:00+00:00",
    run_id: "20260727-120000-abc123",
    evidence_sha256: "c0ffee".padEnd(64, "0"),
    released_teeth: [19],
  },
};

function view(overrides: Partial<Parameters<typeof DeliverStageView>[0]> = {}) {
  return renderToStaticMarkup(
    <StaticRouter location="/case/case-a/deliver">
      <DeliverStageView
        detail={deliverableDetail()}
        assurance={{ kind: "ok", data: assuranceView() }}
        dispositions={{}}
        acknowledged={[]}
        expanded={[]}
        onDisposition={() => undefined}
        onAcknowledge={() => undefined}
        onToggleExpand={() => undefined}
        onConfirm={() => undefined}
        onPay={() => undefined}
        onRelease={() => undefined}
        onReloadEvidence={() => undefined}
        onDownload={() => undefined}
        {...overrides}
      />
    </StaticRouter>,
  );
}

describe("the stage's compact evidence, and the report behind a modal (#5)", () => {
  it("the stage summarizes each site in the SERVED order, with its gate chip", () => {
    const html = view();
    expect(html).toContain('data-role="evidence-summary"');
    const first = html.indexOf('data-role="evidence-line" data-tooth="30"');
    const second = html.indexOf('data-role="evidence-line" data-tooth="19"');
    expect(first).toBeGreaterThan(-1);
    expect(second).toBeGreaterThan(first); // worst-first, verbatim
    expect(html).toContain("rim 0.07 mm");
    expect(html).toContain("RMS 0.43 mm / p90 0.71 mm");
  });

  it("the full table is NOT on the stage until the report is opened", () => {
    const html = view();
    expect(html).toContain('data-role="open-report"');
    expect(html).not.toContain('data-role="assurance-table"');
    expect(html).not.toContain('data-role="report-dialog"');
  });

  it("open, the modal holds the whole table in the demo's dialog chrome", () => {
    const html = view({ reportOpen: true });
    expect(html).toContain('data-role="report-backdrop"');
    expect(html).toContain("decode-dialog-backdrop");
    expect(html).toMatch(/data-role="report-dialog"[^>]*class="decode-dialog"/);
    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-modal="true"');
    expect(html).toContain("decode-dialog__header");
    expect(html).toContain("decode-dialog__body");
    expect(html).toContain('data-role="report-close"');
    // the table, with every column, inside its own internal scroll
    expect(html).toMatch(/data-role="assurance-table"[^>]*class="results-table"/);
    expect(html).toContain("results-table-scroll");
    expect(html).toContain("scan-body agreement literature"); // industry references
  });

  it("a row's QC images live in the modal, behind the row expand", () => {
    const collapsed = view({ reportOpen: true });
    expect(collapsed).not.toContain("case-a-30-clockview.png");
    const html = view({ reportOpen: true, expanded: [30] });
    expect(html).toContain(
      'src="/api/case-sessions/case-a/runs/current/qc/case-a-30-clockview.png"',
    );
    expect(html).toContain('loading="lazy"');
  });

  it("an assurance fetch error states itself instead of an empty summary", () => {
    const html = view({
      assurance: { kind: "error", detail: "HTTP 404 — no completed current run" },
    });
    expect(html).toContain('data-role="assurance-error"');
    expect(html).toContain("no completed current run");
  });
});

describe("dispositions default to release; only a flag can be withheld (#4)", () => {
  it("a clean row shows NO control and says it is released", () => {
    const html = view({ reportOpen: true });
    // two sites, one flagged: exactly one withhold control
    expect(html.match(/data-role="disposition-withhold"/g)).toHaveLength(1);
    expect(html.match(/data-role="disposition-default"/g)).toHaveLength(1);
    expect(html).toContain("released");
  });

  it("the flagged row still demands its own acknowledgment (the assurance rule)", () => {
    const html = view({ reportOpen: true });
    expect(html.match(/data-role="acknowledge-flag"/g)).toHaveLength(1);
    expect(html).toContain("tooth 30 is flagged — releasing it needs its own acknowledgment");
  });

  it("withholding the flagged row retires its acknowledgment demand entirely", () => {
    const html = view({ reportOpen: true, dispositions: { 30: "withhold" } });
    expect(html).not.toContain('data-role="acknowledge-flag"');
    expect(html).not.toContain('data-role="confirm-blockers"');
  });

  it("NO row is ever blocked for want of a disposition", () => {
    // the deleted blocker, pinned as an absence (client 2026-07-27 #4)
    expect(view()).not.toContain("needs a disposition");
  });
});

describe("one blocker list, both places the confirm is offered (#5)", () => {
  it("the same list renders on the stage and in the modal footer", () => {
    const html = view({ reportOpen: true });
    const lists = html.match(/data-role="confirm-blockers"/g) ?? [];
    expect(lists.length).toBe(3); // the step, the stage and the modal footer
    // and every one of them says the SAME thing — one derivation
    const occurrences =
      html.match(/tooth 30 is flagged — releasing it needs its own acknowledgment/g) ?? [];
    expect(occurrences.length).toBe(lists.length);
  });

  it("the confirm is inert while anything is outstanding, armed once nothing is", () => {
    expect(view()).toMatch(/data-role="confirm"[^>]*disabled/);
    const armed = view({ acknowledged: [30] });
    expect(armed).toMatch(/data-role="confirm"(?![^>]*disabled)/);
    expect(armed).not.toContain('data-role="confirm-blockers"');
  });

  it("the modal footer carries the confirm too — read and act in one place", () => {
    const html = view({ reportOpen: true, acknowledged: [30] });
    expect(html).toContain("decode-ack__actions");
    const footer = html.slice(html.indexOf("<footer"));
    expect(footer).toContain('data-role="confirm"');
  });
});

describe("the delivery progression — Confirmed, Paid, Released (#6)", () => {
  it("three steps, exactly one current, each saying what it is or waits for", () => {
    const html = view();
    expect(html).toContain('data-role="release-steps"');
    expect(html).toMatch(/data-step="confirmed"[^>]*data-state="current"/);
    expect(html).toMatch(/data-step="paid"[^>]*data-state="waiting"/);
    expect(html).toMatch(/data-step="released"[^>]*data-state="waiting"/);
    expect(html).toContain("Waiting for the confirmation.");
  });

  it("a confirmed case shows the seal's time and moves the current step on", () => {
    const html = view({ detail: deliverableDetail(CONFIRMED) });
    expect(html).toMatch(/data-step="confirmed"[^>]*data-state="done"/);
    expect(html).toContain("Sealed at 2026-07-27T12:00:00+00:00");
    expect(html).toMatch(/data-step="paid"[^>]*data-state="current"/);
  });

  it("the payment control names the case, the site count AND its stub nature", () => {
    const html = view({ detail: deliverableDetail(CONFIRMED) });
    expect(html).toContain('data-role="payment-stub"');
    expect(html).toContain("Authorize payment (stub) — 2 sites on case case-a");
    expect(html).toContain('data-role="payment-stub-note"');
    expect(html).toContain("no provider is contacted and no money moves");
  });

  it("once paid, the record's provider and time show, and release becomes current", () => {
    const html = view({ detail: deliverableDetail({ ...CONFIRMED, ...PAID }) });
    expect(html).toContain("Authorized at 2026-07-27T12:01:00+00:00 (stub)");
    expect(html).toMatch(/data-step="released"[^>]*data-state="current"/);
  });

  it("the release step NAMES what will be disclosed before the act", () => {
    const html = view({
      detail: deliverableDetail({
        ...CONFIRMED,
        ...PAID,
        release_preview: {
          file_count: 1,
          teeth: [19],
          withheld_teeth: [30],
          withheld_case_file_count: 4,
        },
      }),
    });
    expect(html).toContain('data-role="release-disclosure"');
    expect(html).toContain("Releasing discloses 1 file for tooth 19.");
    expect(html).toContain("Tooth 30 is withheld — its files stay back and the site stays open.");
    expect(html).toContain("4 case-wide files stay back too");
    // and it is said BEFORE the act, above the button that performs it
    expect(html.indexOf('data-role="release-disclosure"')).toBeLessThan(
      html.indexOf('data-role="release"'),
    );
  });
});

describe("the artifacts — grouped by site, with names and sizes (#6)", () => {
  const releasedDetail = () =>
    deliverableDetail({ ...CONFIRMED, ...PAID, ...RELEASED });

  const artifacts = {
    kind: "ok" as const,
    data: {
      run_id: "20260727-120000-abc123",
      files: [
        { name: "case-a-19-healingcap-aligned.stl", size_bytes: 2048, tooth: 19 },
        { name: "case-a-19-scanbody.stl", size_bytes: 1024, tooth: 19 },
        { name: "case-a-manifest.json", size_bytes: 512, tooth: null },
      ],
      withheld_teeth: [30],
      withheld_case_files: ["case-a-upper-overlay.stl"],
    },
  };

  it("files bucket by site, case-wide last, each with a readable size", () => {
    const html = view({ detail: releasedDetail(), artifacts });
    expect(html).toMatch(/data-role="artifact-group"[^>]*data-tooth="19"/);
    expect(html).toMatch(/data-role="artifact-group"[^>]*data-tooth="case-wide"/);
    expect(html.indexOf('data-tooth="19"')).toBeLessThan(
      html.indexOf('data-tooth="case-wide"'),
    );
    expect(html).toContain("2 files · 3.0 KB");
    expect(html).toContain("2.0 KB");
    expect(html).toContain("512 B");
  });

  it("every file is a fetch button — the endpoint is gated, so never a bare href", () => {
    const html = view({ detail: releasedDetail(), artifacts });
    expect(html).toMatch(
      /data-role="artifact-download" data-file="case-a-19-healingcap-aligned.stl"/,
    );
    expect(html).not.toContain('href="/api/case-sessions/case-a/runs/current/artifacts');
    expect(html).toContain('data-role="download-all"');
    expect(html).toContain("Download all 3 files");
  });

  it("a withheld site is shown withheld, with its OPEN status and the case-wide hold", () => {
    const html = view({ detail: releasedDetail(), artifacts });
    expect(html).toContain('data-role="withheld-site"');
    expect(html).toContain("Tooth 30");
    expect(html).toContain("the site stays open (flagged)");
    expect(html).toContain('data-role="withheld-case-files"');
    expect(html).toContain("case-a-upper-overlay.stl");
  });

  it("a listing refusal renders in the backend's words", () => {
    const html = view({
      detail: releasedDetail(),
      artifacts: { kind: "error", detail: "HTTP 409 — the confirmation changed after release" },
    });
    expect(html).toContain('data-role="artifacts-error"');
    expect(html).toContain("confirmation changed after release");
  });
});

describe("the 409 re-confirm flow, phases and errors", () => {
  it("the drift 409 renders the BFF's words and the reload affordance", () => {
    const html = view({
      detail: deliverableDetail(CONFIRMED),
      staleWords:
        "HTTP 409 — the case changed since it was confirmed — re-confirm over the current evidence",
      acknowledged: [30],
    });
    expect(html).toContain('data-role="reconfirm"');
    expect(html).toContain("changed since it was confirmed");
    expect(html).toContain("Reload the evidence");
  });

  it("a confirming phase names the work", () => {
    expect(view({ phase: "confirming", acknowledged: [30] })).toContain(
      "Sealing the confirmation…",
    );
  });

  it("an action refusal renders in the backend's words", () => {
    const html = view({
      actionError: "HTTP 422 — releasing a flagged site requires its own acknowledgment",
    });
    expect(html).toContain('data-role="deliver-error"');
    expect(html).toContain("requires its own acknowledgment");
  });
});

describe("the parity chrome (ledger row 9): the demo's results-table language", () => {
  it("the table keeps its clothes inside the dialog", () => {
    const html = view({ reportOpen: true });
    expect(html).toMatch(/data-role="assurance-table"[^>]*class="results-table"/);
    expect(html).toContain("assurance-row--flagged");
    expect(html).toMatch(/data-role="gate-level"[^>]*class="chip chip--gate/);
    expect(html).toMatch(/data-role="status-chip"[^>]*class="chip chip--status"/);
  });

  it("the sealed confirmation is the quiet block with the hash in mono", () => {
    const html = view({ reportOpen: true, detail: deliverableDetail(CONFIRMED) });
    expect(html).toMatch(/data-role="sealed-confirmation"[^>]*class="sealed-note"/);
    expect(html).toContain("Confirmed at 2026-07-27T12:00:00+00:00");
  });

  it("the modal footer wears the acknowledgment bar", () => {
    const html = view({ reportOpen: true });
    expect(html).toContain('class="decode-ack"');
    expect(html).toContain("decode-ack__text");
    expect(html).toContain("decode-ack__actions");
  });
});
