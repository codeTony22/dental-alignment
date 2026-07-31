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
import {
  assuranceSite,
  assuranceView,
  caseSessionDetail,
  invoiceView,
  siteView,
} from "../testing/fixtures";
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
    terms_accepted: true,
    terms_version: "placeholder-v1",
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
    // The scroll wrapper is GONE by design (client, 2026-07-27: "fit the modal view,
    // no need for the horizontal scroll"). Five fixed-width columns replace it.
    expect(html).not.toContain("results-table-scroll");
    expect(html).toContain("assurance-table-fit");
    // The industry sentences moved INTO the row expand (same client note): a reference
    // is read deliberately, not skimmed across a cell that forced the scroll.
    expect(html).not.toContain("scan-body agreement literature");
  });

  it("puts the industry references in the row expand, beside the images they explain", () => {
    const collapsed = view({ reportOpen: true });
    expect(collapsed).not.toContain("scan-body agreement literature");
    const expanded = view({ reportOpen: true, expanded: [30] });
    expect(expanded).toContain('data-role="row-detail"');
    expect(expanded).toContain("scan-body agreement literature");
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
  it("the same list renders in the two places the confirm is offered — and only there", () => {
    const html = view({ reportOpen: true });
    const lists = html.match(/data-role="confirm-blockers"/g) ?? [];
    const buttons = html.match(/data-role="confirm"/g) ?? [];
    expect(lists.length).toBe(2); // the progression's Confirmed step, the modal footer
    expect(buttons.length).toBe(2); // one beside each list, never a third
    // and both say the SAME thing — one derivation, stated twice
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

  it("the modal footer carries the confirm — read and act in one place", () => {
    const html = view({ reportOpen: true, acknowledged: [30] });
    expect(html).toContain("decode-ack__actions");
    const footer = html.slice(html.indexOf("<footer"));
    expect(footer).toContain('data-role="confirm"');
  });

  it("the evidence panel offers the REPORT, not a third confirm button", () => {
    const stage = view({ acknowledged: [30] });
    expect(stage).toContain('data-role="open-report"');
    expect((stage.match(/data-role="confirm"/g) ?? []).length).toBe(1);
  });

  it("a DONE Confirmed step carries no demand — a blocker with no button is a dead end", () => {
    // review 2026-07-28: un-ticking an acknowledgment after confirming printed the
    // demand under a "done ✓" step whose button had already gone. The list belongs
    // where the act is offered; the modal footer still carries both.
    const stage = view({ detail: deliverableDetail(CONFIRMED) });
    expect(stage).toMatch(/data-step="confirmed"[^>]*data-state="done"/);
    expect(stage).not.toContain('data-role="confirm-blockers"');
    const open = view({ detail: deliverableDetail(CONFIRMED), reportOpen: true });
    expect((open.match(/data-role="confirm-blockers"/g) ?? []).length).toBe(1);
    expect((open.match(/data-role="confirm"/g) ?? []).length).toBe(1);
  });
});

describe("the fork's decision, shown where the confirm is (review 2026-07-28)", () => {
  it("the sealed decision is READABLE — on the stage and in the report alike", () => {
    const html = view({
      reportOpen: true,
      assurance: { kind: "ok", data: assuranceView({ adjustments: "skip" }) },
    });
    const lines = html.match(/data-role="adjustments-note"/g) ?? [];
    expect(lines.length).toBe(2); // beside each place the confirm is offered
    expect(html).toContain("Adjustments skipped");
    expect(html).toContain("part of what confirming seals");
  });

  it("the other fork reads as the other fork", () => {
    const html = view({
      assurance: { kind: "ok", data: assuranceView({ adjustments: "adjust" }) },
    });
    expect(html).toContain("Adjustments taken up");
    expect(html).not.toContain("Adjustments skipped");
  });

  it("an unfaced fork says so — the operator is never told a decision that was not made", () => {
    const html = view();
    expect(html).toContain('data-role="adjustments-note"');
    expect(html).toContain("never faced");
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

  it("the paid step OPENS the mock checkout dialog instead of paying inline", () => {
    // Retargeted twice on 2026-07-30, both by the client: first the inline stub
    // became a real checkout surface ("does not routes me to add credit card or
    // saved credit card mocks"), then the surface became a DIALOG over this page
    // ("might be better on a modal, so the client can still see their work on the
    // background"). The control is a button that opens it; nothing navigates away.
    const html = view({ detail: deliverableDetail(CONFIRMED) });
    expect(html).toContain('data-role="go-to-checkout"');
    expect(html).toContain("Go to checkout (demo) — 2 sites");
    expect(html).toContain('data-role="payment-stub-note"');
    expect(html).toContain("return leg asserts nothing");
    expect(html).not.toContain('href="/case/case-a/checkout"');
    expect(html).not.toContain('data-role="payment-stub"');
  });

  it("the checkout dialog rides on the stage when the container opens it", () => {
    const html = view({
      detail: deliverableDetail(CONFIRMED),
      checkoutDialog: <div data-role="stub-checkout-dialog" />,
    });
    expect(html).toContain('data-role="stub-checkout-dialog"');
  });

  it("the door back appears once anything is signed, and names all three records", () => {
    const html = view({ detail: deliverableDetail(CONFIRMED) });
    expect(html).toContain('data-role="delivery-reset"');
    expect(html).toContain("withdraw confirmation, payment &amp; release");
  });

  it("with nothing signed there is no door back to offer", () => {
    const html = view();
    expect(html).not.toContain('data-role="delivery-reset"');
  });

  it("with no invoice yet the amount is unstated, never invented (#10-A)", () => {
    const html = view({ detail: deliverableDetail(CONFIRMED) });
    expect(html).toContain('data-role="checkout-screen"');
    expect(html).toContain('data-role="checkout-price"');
    expect(html).toContain("pricing not yet defined");
  });

  it("the derived invoice reaches the paid step — lines, then the SERVER's total", () => {
    const html = view({
      detail: deliverableDetail(CONFIRMED),
      invoice: { kind: "ok", data: invoiceView() },
    });
    expect(html).toContain('data-role="invoice-line" data-key="released_sites"');
    expect(html).toContain('data-role="invoice-line" data-key="exception_sites"');
    expect(html).toContain('data-role="checkout-total"');
    expect(html).toContain("$48.00");
    // and the lines are read BEFORE the total they do not add up to on screen
    expect(html.indexOf('data-key="released_sites"')).toBeLessThan(
      html.indexOf('data-role="checkout-total"'),
    );
  });

  it("the placeholder-rate banner STAYS beside the total, in the server's words", () => {
    const html = view({
      detail: deliverableDetail(CONFIRMED),
      invoice: { kind: "ok", data: invoiceView() },
    });
    expect(html).toContain('data-role="invoice-placeholder"');
    expect(html).toContain("PLACEHOLDER RATES");
    expect(html).toContain("are not a quotation");
    expect(html).toContain('data-role="invoice-turnaround"');
  });

  it("a refused invoice says so instead of leaving a blank where money goes", () => {
    const html = view({
      detail: deliverableDetail(CONFIRMED),
      invoice: { kind: "error", status: 404, detail: "no completed current run" },
    });
    expect(html).toContain('data-role="invoice-error"');
    expect(html).toContain("no completed current run");
    expect(html).not.toContain('data-role="checkout-total"');
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

describe("the agreement — confirm and accept terms is one act (plan §10-A)", () => {
  it("the checkbox and its PLACEHOLDER banner sit right above the confirm button", () => {
    const html = view({ acknowledged: [30] });
    expect(html).toContain('data-role="terms-acceptance"');
    expect(html).toContain('data-role="terms-placeholder-banner"');
    expect(html).toContain("PLACEHOLDER");
    expect(html).toContain('data-role="terms-checkbox"');
    expect(html.indexOf('data-role="terms-acceptance"')).toBeLessThan(
      html.indexOf('data-role="confirm"'),
    );
  });

  it("the terms text names the case's own site count until the invoice lands", () => {
    const html = view();
    expect(html).toContain("all 2 sites in this case");
  });

  it("with the invoice, the sentence ENUMERATES what is being released", () => {
    // gap ``clinical-responsibility-attestation``: "all N sites" never said that
    // some of those sites release only as acknowledged exceptions. Every count in
    // the sentence is the BFF's — the invoice's own line quantities.
    const html = view({ invoice: { kind: "ok", data: invoiceView() } });
    expect(html).toContain("clinical responsibility");
    expect(html).toContain("2 constructions");
    expect(html).toContain("1 as an acknowledged exception");
    expect(html).toContain('data-role="attestation-caveat"');
    expect(html).toContain("re-derived server-side");
  });

  it("the Clinical Responsibility Statement is reachable as its own document", () => {
    const html = view({ invoice: { kind: "ok", data: invoiceView() } });
    expect(html).toContain('data-role="clinical-terms-link"');
    expect(html).toContain('href="/terms/clinical-responsibility-placeholder-v1"');
  });

  it("unaccepted terms block confirming even over a clean, acknowledged table", () => {
    const html = view({ acknowledged: [30], termsAccepted: false });
    expect(html).toMatch(/data-role="confirm"[^>]*disabled/);
    expect(html).toContain("the terms — read and accept them before confirming");
  });

  it("accepted terms plus a clean table arms the confirm", () => {
    const html = view({ acknowledged: [30], termsAccepted: true });
    expect(html).toMatch(/data-role="confirm"(?![^>]*disabled)/);
    expect(html).not.toContain("read and accept them before confirming");
  });

  it("the checkbox reflects the accepted state either way", () => {
    const unchecked = view({ termsAccepted: false });
    expect(unchecked).not.toMatch(/data-role="terms-checkbox"[^>]*checked/);
    const checked = view({ termsAccepted: true });
    expect(checked).toMatch(/data-role="terms-checkbox"[^>]*checked/);
  });

  it("the modal footer carries the SAME agreement — one checkbox, stated twice", () => {
    const html = view({ reportOpen: true, acknowledged: [30] });
    const banners = html.match(/data-role="terms-acceptance"/g) ?? [];
    expect(banners.length).toBe(2); // the progression's Confirmed step, the modal footer
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

describe("a reworked row says which of its numbers predate the rework (finding E)", () => {
  it("the line rides in the ROW, not behind the expand — the signature covers it", () => {
    const html = view({
      reportOpen: true,
      assurance: {
        kind: "ok",
        data: assuranceView({
          sites: [
            assuranceSite({
              tooth: 19,
              stale_metrics: ["rim_agreement_mm", "guidance"],
            }),
          ],
        }),
      },
    });
    expect(html).toContain('data-role="stale-metrics"');
    expect(html).toContain("the rim agreement and the gate verdict");
    expect(html).toContain("Confirming seals them as they stand");
    // and the numbers themselves stay on the row: naming them is disclosure, not
    // deletion — a hidden number leaves the doctor nothing to weigh
    expect(html).toContain("0.07");
  });

  it("a row the run produced carries no such line at all", () => {
    expect(view({ reportOpen: true })).not.toContain('data-role="stale-metrics"');
  });
});

describe("the production note — a disclosure gap closed (plan §10-E)", () => {
  const NOTE =
    "single construction part shared across sites identifying 2 distinct " +
    "variants — per-variant construction parts needed";

  it("rides in the ROW beside the clamp story, verbatim from the worker", () => {
    const html = view({
      reportOpen: true,
      assurance: {
        kind: "ok",
        data: assuranceView({
          sites: [assuranceSite({ tooth: 19, production_note: NOTE })],
        }),
      },
    });
    expect(html).toContain('data-role="production-note"');
    expect(html).toContain(NOTE);
  });

  it("also rides in the row-expand detail, beside the relief clamp", () => {
    const html = view({
      reportOpen: true,
      expanded: [19],
      assurance: {
        kind: "ok",
        data: assuranceView({
          sites: [assuranceSite({ tooth: 19, production_note: NOTE })],
        }),
      },
    });
    expect(html).toContain('data-role="production-note-detail"');
  });

  it("a noted row offers the withhold control and demands acknowledgment even though it reads ready", () => {
    // THE FLAG DECISION, visible in the UI: the row is NOT status "flagged" —
    // it is the shared-part note alone earning the same AM-12 treatment
    const html = view({
      reportOpen: true,
      assurance: {
        kind: "ok",
        data: assuranceView({
          sites: [assuranceSite({ tooth: 19, status: "ready", production_note: NOTE })],
        }),
      },
    });
    expect(html).toMatch(/data-tooth="19"[^>]*data-status="ready"/);
    expect(html).toContain('data-role="disposition-withhold"');
    expect(html).toContain('data-role="acknowledge-flag"');
    expect(html).toContain(
      "tooth 19 shares a construction part with a differently-declared variant",
    );
  });

  it("a clean row carries no production note at all", () => {
    const html = view({ reportOpen: true });
    expect(html).not.toContain('data-role="production-note"');
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

describe("the assurance header states its own counts and its exceptions policy", () => {
  it("counts the served rows in the worklist's phrasing, beside the case", () => {
    const html = view();
    expect(html).toContain('data-role="assurance-counts"');
    expect(html).toContain("2 sites · 1 flagged / 1 ready");
  });

  it("names the acknowledgment obligation as the product's own act, not a status", () => {
    const html = view();
    expect(html).toContain('data-role="assurance-policy"');
    expect(html).toContain("1 site releases only as an acknowledged exception");
  });

  it("a clean table says no acknowledgment is owed rather than staying silent", () => {
    const html = view({
      assurance: { kind: "ok", data: assuranceView({ sites: [assuranceSite()] }) },
    });
    expect(html).toContain("No site needs an acknowledgment");
  });

  it("never says a WITHHELD site releases (audit 2026-07-31)", () => {
    // On one screen the header asserted "1 site releases only as an acknowledged
    // exception" while the row below it rendered no tick (ackRequired is false once
    // withheld), the confirm gate demanded nothing, and the server's derive_invoice
    // counted the site as `withheld`, explicitly not as an exception.
    const html = view({ reportOpen: true, dispositions: { 30: "withhold" } });
    expect(html).toContain('data-role="assurance-policy"');
    expect(html).not.toContain("releases only as an acknowledged exception");
    expect(html).toContain("No site releases as an acknowledged exception");
    expect(html).toContain("1 site is withheld");
    // and the row it describes really does offer no tick
    expect(html).not.toContain('data-role="acknowledge-flag"');
  });

  it("states NO tolerance number — this product has none to state", () => {
    // the design's header ends "· tolerance 0.40 mm"; every band comparison here is
    // the BFF's, per metric, against the acceptance catalog (AM-4)
    expect(view()).not.toContain("tolerance");
  });
});

describe("each evidence line carries its one sentence of WHY, on the stage", () => {
  it("the gate's first action rides in the row — the confirmation seals these rows", () => {
    // it used to take two clicks (open the report, expand the row) to learn why a row
    // was flagged, on the very surface that seals it
    const html = view();
    expect(html).toContain('data-role="evidence-note"');
    expect(html).toContain("ROTATION could not be verified");
    expect(html).toMatch(/data-role="evidence-note" data-verbatim="true"/);
  });

  it("a row whose gate raised nothing says so, in the gate's own word", () => {
    const html = view({
      assurance: { kind: "ok", data: assuranceView({ sites: [assuranceSite()] }) },
    });
    expect(html).toMatch(/data-role="evidence-note" data-verbatim="false"/);
    expect(html).toContain("No action was raised — this gate reads ready.");
  });
});

describe("the closing statement — the case finally says what shipped", () => {
  const releasedDetail = () =>
    deliverableDetail({ ...CONFIRMED, ...PAID, ...RELEASED });

  it("counts off the ARTIFACTS actually served, and names what stays open", () => {
    const html = view({
      detail: releasedDetail(),
      artifacts: {
        kind: "ok",
        data: {
          run_id: "20260727-120000-abc123",
          files: [
            { name: "case-a-19-cap.stl", size_bytes: 2048, tooth: 19 },
            { name: "case-a-19-scanbody.stl", size_bytes: 1024, tooth: 19 },
            { name: "case-a-manifest.json", size_bytes: 512, tooth: null },
          ],
          withheld_teeth: [30],
          withheld_case_files: [],
        },
      },
    });
    expect(html).toContain('data-role="released-closing"');
    expect(html).toContain("Released 3 files for 1 site, including 1 case-wide file.");
    expect(html).toContain("Tooth 30 stays open");
  });

  it("no listing, no claim: a refused artifact list closes nothing", () => {
    const html = view({
      detail: releasedDetail(),
      artifacts: { kind: "error", detail: "HTTP 409 — the evidence changed after release" },
    });
    expect(html).not.toContain('data-role="released-closing"');
  });

  it("nothing is closed before the release", () => {
    expect(view({ detail: deliverableDetail(CONFIRMED) })).not.toContain(
      'data-role="released-closing"',
    );
  });
});

describe("the checkout says what paying does, and links the sealed terms", () => {
  it("the footnote sits with the checkout button, pointing at the SEALED version", () => {
    const html = view({ detail: deliverableDetail(CONFIRMED) });
    expect(html).toContain('data-role="checkout-terms"');
    expect(html).toContain('href="/terms/placeholder-v1"');
    expect(html).toContain("releasing the artifacts is a separate act");
  });

  it("with no sealed version there is still a document to read", () => {
    // reachable only through a confirmation, so this is the defensive branch — the
    // link must never resolve to /terms/null
    const html = view({
      detail: deliverableDetail({
        ...CONFIRMED,
        confirmation: { ...CONFIRMED.confirmation, terms_version: null },
      }),
    });
    expect(html).toContain('data-role="checkout-terms"');
    expect(html).not.toContain("/terms/null");
  });
});

describe("the terms are a LINK to a routed document (client 2026-07-30)", () => {
  it("the acceptance links out to the current terms, in a new tab", () => {
    // a new tab because reading the agreement must not cost the operator the
    // confirmation they are part-way through
    const html = view();
    expect(html).toContain('data-role="terms-link"');
    expect(html).toContain('href="/terms"');
    expect(html).toContain('target="_blank"');
  });

  it("a sealed confirmation resolves the EXACT version it accepted", () => {
    const html = view({ detail: deliverableDetail(CONFIRMED) });
    expect(html).toContain('data-role="sealed-terms-link"');
    expect(html).toContain('href="/terms/placeholder-v1"');
    expect(html).toContain("Terms accepted: placeholder-v1");
  });

  it("with nothing sealed there is no version to resolve", () => {
    expect(view()).not.toContain('data-role="sealed-terms-link"');
  });
});
