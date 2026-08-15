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
    // §10-O.8 (2026-08-02): the container is focusable (useDialogFocus's fallback
    // target when nothing is marked), and Close — never the footer's "Confirm over
    // this evidence" — is the explicit landing spot. The trap/restore behaviour
    // itself lives in useDialogFocus.test.tsx; renderToStaticMarkup fires no effects.
    expect(html).toMatch(/data-role="report-dialog"[^>]*tabindex="-1"/);
    expect(html).toMatch(/data-role="report-close"[^>]*data-autofocus=""/);
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

  it("the MODAL's per-row QC images stay behind the row expand", () => {
    /* Retargeted 2026-08-01: this used to assert the filename appeared NOWHERE
       until a row expanded — the premise the client overrode the same day ("we
       need to show the 3 main artifacts as a preview in the Deliver Page"). The
       page-level preview strip now shows them by design; what this test still
       guards is the MODAL's own economy — its full-size qc-image rows render
       only behind the expand, not on every open. */
    const collapsed = view({ reportOpen: true });
    expect(collapsed).not.toContain('data-role="qc-image"');
    const html = view({ reportOpen: true, expanded: [30] });
    expect(html).toContain('data-role="qc-image"');
    expect(html).toContain(
      'src="/api/case-sessions/case-a/runs/current/qc/case-a-30-clockview.png"',
    );
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

const CATALOG_WITH_CONSTRUCTIONS = {
  groups: [],
  constructions: [
    { path_id: "dess/conical-scanbody.stl", label: "Conical scan body", vendor: "dess" },
    { path_id: "neodent/gm.stl", label: "GM scan body", vendor: "neodent" },
  ],
};

function detailWithConstruction(
  overrides: Partial<CaseSessionDetail["session"]> = {},
  source: "chosen" | "suggested" | "default" | "none" = "chosen",
): CaseSessionDetail {
  const base = deliverableDetail(overrides);
  return {
    ...base,
    catalog: CATALOG_WITH_CONSTRUCTIONS,
    choices: {
      ...base.choices,
      construction_path: "dess/conical-scanbody.stl",
      effective_construction: { value: "dess/conical-scanbody.stl", source },
    },
  };
}

describe("the Construction step (client 2026-08-01): after Confirmed, before Paid", () => {
  it("sits between the Confirmed and Paid steps in the ladder", () => {
    const html = view();
    const confirmed = html.indexOf('data-step="confirmed"');
    const construction = html.indexOf('data-step="construction"');
    const paid = html.indexOf('data-step="paid"');
    expect(confirmed).toBeGreaterThan(-1);
    expect(construction).toBeGreaterThan(confirmed);
    expect(paid).toBeGreaterThan(construction);
  });

  it("no construction chosen yet says so, never a blank", () => {
    expect(view()).toContain("No construction part chosen yet");
  });

  it("shows the effective construction — label, vendor and the suggested tag", () => {
    const html = view({ detail: detailWithConstruction({}, "suggested") });
    expect(html).toContain('data-role="construction-current"');
    expect(html).toContain("Conical scan body");
    expect(html).toContain("dess");
    expect(html).toContain('data-role="construction-suggested"');
  });

  it("an operator's own chosen construction wears no suggested tag", () => {
    const html = view({ detail: detailWithConstruction() });
    expect(html).not.toContain('data-role="construction-suggested"');
  });

  it("the picker is closed by default, offering only the change affordance", () => {
    const html = view({ detail: detailWithConstruction() });
    expect(html).toContain('data-role="construction-edit"');
    expect(html).not.toContain('data-role="construction-select"');
  });

  it("open, the picker groups the SAME rows Intake reads, by vendor", () => {
    const html = view({ detail: detailWithConstruction(), constructionEditing: true });
    expect(html).toContain('data-role="construction-select"');
    expect(html).toMatch(/<optgroup label="dess">/);
    expect(html).toMatch(/<optgroup label="neodent">/);
    expect(html).toContain("Conical scan body");
    expect(html).toContain("GM scan body");
  });

  it("a picked candidate shows the blast radius BEFORE the PUT — never silent", () => {
    const html = view({
      detail: detailWithConstruction(CONFIRMED),
      constructionEditing: true,
      constructionPending: "neodent/gm.stl",
    });
    expect(html).toContain('data-role="construction-change-confirm"');
    expect(html).toContain('data-role="construction-change-words"');
    /* AMENDED (§10-AC): over a DONE run the change RE-EMITS from the run's own
       poses — the disclosure-before-act rule is unchanged, the disclosed
       consequence shrank with the behaviour. */
    expect(html).toContain("re-emits the package from the run&#x27;s own poses");
    expect(html).toContain("the fits stand, nothing re-aligns");
    expect(html).not.toContain("re-bores and re-renders everything");
    expect(html).toContain("the standing confirmation falls");
    expect(html).toContain('data-role="construction-confirm-change"');
    expect(html).toContain('data-role="construction-cancel-change"');
  });

  it("with nothing confirmed yet, the words never claim a confirmation falls", () => {
    const html = view({
      detail: detailWithConstruction(),
      constructionEditing: true,
      constructionPending: "neodent/gm.stl",
    });
    expect(html).toContain('data-role="construction-change-words"');
    expect(html).not.toContain("confirmation falls");
  });

  it("no pending pick shows no blast-radius panel — a re-selection of the current value is not a change", () => {
    const html = view({ detail: detailWithConstruction(), constructionEditing: true });
    expect(html).not.toContain('data-role="construction-change-confirm"');
  });

  it("busy and error states render honestly", () => {
    const busy = view({
      detail: detailWithConstruction(),
      constructionEditing: true,
      constructionPending: "neodent/gm.stl",
      constructionSaving: true,
    });
    expect(busy).toContain("Changing…");
    const errored = view({
      detail: detailWithConstruction(),
      constructionEditing: true,
      constructionError: "HTTP 422 — unknown construction part",
    });
    expect(errored).toContain('data-role="construction-error"');
    expect(errored).toContain("unknown construction part");
  });
});

describe("the 3D preview tabs — the demo's three views of the run's result (client 2026-08-01)", () => {
  function runFactsOk(packageFiles: readonly string[]) {
    return {
      kind: "ok" as const,
      data: {
        run_id: "r1",
        job_id: "r1",
        state: "done" as const,
        refusal: null,
        summary: null,
        sites: [],
        package_files: [...packageFiles],
      },
    };
  }

  it("renders a tab per file the package actually names", () => {
    const html = view({
      runFacts: runFactsOk([
        "case-a-arch-with-healingcaps.stl",
        "case-a-arch-with-constructions.stl",
        "case-a-19-prosthesis_cad.stl",
      ]),
    });
    expect(html).toContain('data-role="deliver-mesh-preview"');
    expect(html).toContain("1 · Healing-cap alignment");
    expect(html).toContain("2 · Construction in arch");
    expect(html).toContain("3 · Construction alone — tooth 19");
  });

  it("a file the package does not name is simply not a tab — no placeholder", () => {
    const html = view({ runFacts: runFactsOk(["case-a-arch-with-healingcaps.stl"]) });
    expect(html).toContain("1 · Healing-cap alignment");
    expect(html).not.toContain("Construction in arch");
    expect(html).not.toContain("Construction alone");
  });

  it("no package files yet renders no preview panel at all", () => {
    expect(view({ runFacts: { kind: "loading" } })).not.toContain(
      'data-role="deliver-mesh-preview"',
    );
    expect(view({ runFacts: null })).not.toContain('data-role="deliver-mesh-preview"');
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

  // AT pipeline 4c: the manifest's own facts (triangle count, watertight),
  // threaded onto the row as a muted suffix — decision under test: whether the
  // download row shows the facts the manifest measured, honestly absent when
  // it did not.
  it("a row with facts gains a muted suffix — triangle count and open/closed", () => {
    const withFacts = {
      kind: "ok" as const,
      data: {
        run_id: "20260727-120000-abc123",
        files: [
          {
            name: "case-a-19-healingcap-aligned.stl",
            size_bytes: 2048,
            tooth: 19,
            facts: { triangle_count: 12345, watertight: false },
          },
          {
            name: "case-a-manifest.json",
            size_bytes: 512,
            tooth: null,
            facts: { triangle_count: 900, watertight: true },
          },
        ],
        withheld_teeth: [],
        withheld_case_files: [],
      },
    };
    const html = view({ detail: releasedDetail(), artifacts: withFacts });
    expect(html).toMatch(/data-role="artifact-facts"[^>]*>12,345 triangles · open</);
    expect(html).toMatch(/data-role="artifact-facts"[^>]*>900 triangles · closed</);
  });

  it("a row with no facts (an old manifest, a non-mesh file) renders no suffix — honest absence, never a zero", () => {
    const html = view({ detail: releasedDetail(), artifacts });
    expect(html).not.toContain('data-role="artifact-facts"');
    expect(html).not.toContain("triangles");
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

  /* THE PAID INVOICE, RIDING THE BUNDLE (client 2026-08-09: "when downloading the
   * mesh you get the 4 requirements … plus the invoice that they paid for"). This
   * surface never special-cases it: `list_artifacts` (BFF) appends it like any
   * other case-wide file (`tooth: null`) ONLY once payment is authorized, and this
   * component's own `groupArtifacts`/`handleDownloadAll` are already generic over
   * `artifacts.data.files` — so the pins here are about what the FIXTURE proves,
   * never a special code path added for this one row. */
  describe("the paid invoice rides the listing like any other case-wide file", () => {
    const withInvoice = {
      kind: "ok" as const,
      data: {
        run_id: "20260727-120000-abc123",
        files: [
          { name: "case-a-19-healingcap-aligned.stl", size_bytes: 2048, tooth: 19 },
          { name: "case-a-manifest.json", size_bytes: 512, tooth: null },
          { name: "invoice", size_bytes: 906, tooth: null },
        ],
        withheld_teeth: [],
        withheld_case_files: [],
      },
    };

    it("renders as a download button in the case-wide group, absent before payment", () => {
      const paid = view({ detail: releasedDetail(), artifacts: withInvoice });
      expect(paid).toMatch(/data-role="artifact-download" data-file="invoice"/);
      expect(paid).toMatch(
        /data-role="artifact-group"[^>]*data-tooth="case-wide"/,
      );

      // the SAME fixture shape, minus the row — the honest "before payment" state:
      // nothing here special-cases its absence, it is just not in the served list
      const unpaid = view({
        detail: releasedDetail(),
        artifacts: {
          ...withInvoice,
          data: { ...withInvoice.data, files: withInvoice.data.files.slice(0, 2) },
        },
      });
      expect(unpaid).not.toMatch(/data-file="invoice"/);
    });

    it("download-all's own count includes it — the button walks `files`, unfiltered", () => {
      const html = view({ detail: releasedDetail(), artifacts: withInvoice });
      expect(html).toContain("Download all 3 files");
    });
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

/**
 * THE VACUOUS RMS, ON THE ROW THAT SIGNS (defect cap6020-neodent-gm, 2026-08-01).
 * A fit built from one pair turned a site −50.9° and reported "marks agree to 0.000mm
 * RMS" — arithmetic, not evidence. The assurance table carried no trace of it, so a
 * confirmation could be signed over a quality number that never existed.
 */
describe("a fit with nothing to cross-check it says so on the row", () => {
  const oneObservation = (overrides = {}) =>
    assuranceSite({
      tooth: 19,
      correspondence: {
        pairs: 1,
        observations: 1,
        max_pairs: 8,
        residual_rms_mm: null,
        cross_checked: false,
      },
      ...overrides,
    });

  it("rides in the ROW, beside the other things confirming seals", () => {
    const html = view({
      reportOpen: true,
      assurance: {
        kind: "ok",
        data: assuranceView({ sites: [oneObservation()] }),
      },
    });
    expect(html).toContain('data-role="cross-check"');
    expect(html).toContain("single observation");
    expect(html).toContain("no agreement number");
    expect(html).toContain("Confirming seals it as it stands");
  });

  it("a cross-checked fit carries no such line", () => {
    const html = view({
      reportOpen: true,
      assurance: {
        kind: "ok",
        data: assuranceView({
          sites: [
            assuranceSite({
              tooth: 19,
              correspondence: {
                pairs: 3,
                observations: 5,
                max_pairs: 8,
                residual_rms_mm: 0.08,
                cross_checked: true,
              },
            }),
          ],
        }),
      },
    });
    expect(html).not.toContain('data-role="cross-check"');
  });

  it("a row standing on no correspondence at all carries none either", () => {
    expect(view({ reportOpen: true })).not.toContain('data-role="cross-check"');
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

describe("the unverified rotation routes back to the tools (client 2026-08-02)", () => {
  /* The em was deliberately inert — the acknowledgment gate already forces the operator
     to face the flag here — and the client ruled the other way: "yes route it to
     adjust". It becomes a LINK to the Adjustment stage, wearing the same server word;
     what it still must not do is promise the flag clears, so the only added words name
     the destination, never an outcome. */
  it("renders the unverified mark as a link to the Adjustment stage", () => {
    const html = view({
      reportOpen: true,
      assurance: {
        kind: "ok",
        data: assuranceView({
          sites: [assuranceSite({ rotation: { deg: 21.7, evidence: "none", unverified: true } })],
        }),
      },
    });
    expect(html).toMatch(
      /<a[^>]*data-role="rotation-unverified"[^>]*href="\/case\/case-a\/adjust"|<a[^>]*href="\/case\/case-a\/adjust"[^>]*data-role="rotation-unverified"/,
    );
    expect(html).toContain("unverified");
  });

  it("the link promises a destination, never an outcome", () => {
    const html = view({
      reportOpen: true,
      assurance: {
        kind: "ok",
        data: assuranceView({
          sites: [assuranceSite({ rotation: { deg: 21.7, evidence: "none", unverified: true } })],
        }),
      },
    });
    expect(html).not.toContain("will verify");
    expect(html).not.toContain("marks it verified");
  });

  it("a verified rotation carries no link at all", () => {
    const html = view({
      reportOpen: true,
      assurance: {
        kind: "ok",
        data: assuranceView({
          sites: [assuranceSite({ rotation: { deg: 21.7, evidence: "codes", unverified: false } })],
        }),
      },
    });
    expect(html).not.toContain('data-role="rotation-unverified"');
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

  it("speaks of tolerance ONLY as the served bands — never a verdict of its own", () => {
    /* AMENDED (§10-AB.2, client 2026-08-02). This pin was born as a blanket absence:
       the design's header ended "· tolerance 0.40 mm" off a prop, and this product
       had no tolerance to state. The client then asked for a displayed tolerance AS
       A SERVED FACT, so the rule sharpened rather than fell: the word may appear
       exactly once, inside the tolerance-bands line (the catalog bands the rows
       already carry), and the client-side verdict phrases stay forbidden. */
    const html = view();
    // one spoken mention (the line's own head); the only other match is the
    // data-role hook naming the line, which is chrome, not a claim
    expect((html.match(/Tolerance/g) ?? []).length).toBe(1);
    expect((html.match(/tolerance(?!-bands)/g) ?? []).length).toBe(0);
    const bandsAt = html.indexOf('data-role="tolerance-bands"');
    expect(bandsAt).toBeGreaterThanOrEqual(0);
    expect(html.indexOf("Tolerance bands (served)")).toBeGreaterThan(bandsAt);
    expect(html).not.toContain("in tolerance");
    expect(html).not.toContain("Case tolerance");
    // and with nothing served, the word is gone entirely — the old absence rule
    const bare = assuranceSite();
    const none = view({
      assurance: {
        kind: "ok",
        data: assuranceView({ sites: [{ ...bare, references: {} }] }),
      },
    });
    expect(none).not.toContain("tolerance");
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

// --- the dropped cap reaches the screen that signs it (audit 2026-07-31) -------------

/** A CLEAN, READY site dropped at Adjust. Before the fix this row rendered the
 *  literal word "released" while confirming from it withheld the site plus every
 *  case-wide file, with no control on the row to change it back. */
const DROPPED_CLEAN = assuranceSite({
  tooth: 19,
  status: "ready",
  withhold_intent: true,
});

describe("a site dropped at Adjust, on the screen that signs it", () => {
  const dropped = assuranceView({ sites: [DROPPED_CLEAN] });

  it("NEVER renders the word 'released' for it", () => {
    const html = view({
      reportOpen: true,
      assurance: { kind: "ok", data: dropped },
      dispositions: {},
    });
    const row = html.slice(html.indexOf('data-role="assurance-row" data-tooth="19"'));
    const cell = row.slice(0, row.indexOf("</tr>"));
    expect(cell).not.toContain(">released<");
    expect(cell).toContain('data-disposition="withhold"');
  });

  it("offers the way back on the row itself, not only on Adjust", () => {
    const html = view({
      reportOpen: true,
      assurance: { kind: "ok", data: dropped },
      dispositions: {},
    });
    expect(html).toContain('data-role="disposition-release"');
    expect(html).toContain('data-role="disposition-withhold"');
    expect(html).not.toContain('data-role="disposition-default"');
  });

  it("pressing release on it puts the row back to the quiet default", () => {
    const html = view({
      reportOpen: true,
      assurance: { kind: "ok", data: dropped },
      dispositions: { 19: "release" },
    });
    expect(html).toContain('data-disposition="release"');
  });

  it("the panel header stops saying every row releases as it stands", () => {
    const html = view({ assurance: { kind: "ok", data: dropped }, dispositions: {} });
    expect(html).not.toContain("every row here releases as it stands");
  });

  it("the compact summary the confirm sits beside names it too", () => {
    // the stage's own confirm fires from this panel, so a cap the signature is
    // about to drop must not read here as an unremarkable line
    const html = view({ assurance: { kind: "ok", data: dropped }, dispositions: {} });
    expect(html).toContain('data-role="evidence-withheld"');
    expect(html).toMatch(/data-role="evidence-line"[^>]*data-disposition="withhold"/);
  });
});

describe("what was CHARGED, after the payment (audit 2026-07-31)", () => {
  it("the receipt survives the Paid step going done", () => {
    // the whole invoice block — receipt included — was gated on the paid step being
    // CURRENT, and releaseSteps flips it to "done" the instant payment lands, so
    // post-payment no surface in the product stated the amount
    const html = view({
      detail: deliverableDetail({
        ...CONFIRMED,
        payment_authorized: true,
        payment: {
          provider: "stub",
          at: "2026-07-31T09:00:00+00:00",
          amount_cents: 3200,
          currency: "USD",
          rate_card_version: "placeholder-v1",
          turnaround: "standard",
        },
      }),
      invoice: { kind: "ok", data: invoiceView() },
    });
    expect(html).toContain('data-role="release-step" data-step="paid" data-state="done"');
    expect(html).toContain('data-role="paid-receipt"');
    expect(html).toContain("Charged $32.00");
    expect(html).toContain("rate card placeholder-v1");
  });

  it("a record from before amounts were kept says so rather than printing $0.00", () => {
    const html = view({
      detail: deliverableDetail({ ...CONFIRMED, ...PAID }),
    });
    expect(html).toContain('data-role="paid-receipt"');
    expect(html).toContain("no amount was recorded");
    expect(html).not.toContain("Charged $0.00");
  });
});

describe("the three main artifacts, previewed under the report button (client 2026-08-01)", () => {
  it("renders each QC image as a labelled card that opens the full report", () => {
    const html = view();
    expect(html).toContain('data-role="artifact-previews"');
    // the fixture's two QC images, by the server's own filenames
    expect(html).toContain('data-filename="case-a-19-clockview.png"');
    expect(html).toContain("Clock view");
    expect(html).toContain("Deviation map");
    // the image is fetched off the evidence surface, never a constructed path
    expect(html).toContain("/runs/current/qc/case-a-19-clockview.png");
  });

  it("sits AFTER the open-report button — a preview, not a replacement", () => {
    const html = view();
    expect(html.indexOf('data-role="open-report"')).toBeLessThan(
      html.indexOf('data-role="artifact-previews"'),
    );
  });
});

/**
 * THE COMP'S PAGE CLOTHES (page pass 2026-08-02, §10-AA): Delivery is a centered
 * PAGE — title row leading with the signing-off lead, the progression and the
 * evidence as its two card columns. The re-dress moves NO pinned region's internal
 * order: disclosure still precedes release, lines still precede the total, the
 * blocker list still renders once per confirm site.
 */
describe("the comp's page clothes", () => {
  it("wears the centered page with the title row leading", () => {
    const html = view();
    expect(html).toMatch(/data-role="deliver-stage"[^>]*class="stage-page/);
    const headAt = html.indexOf('class="deliver-page__head"');
    const bodyAt = html.indexOf('class="deliver-page__body"');
    expect(headAt).toBeGreaterThanOrEqual(0);
    expect(bodyAt).toBeGreaterThan(headAt);
    const head = html.slice(headAt, bodyAt);
    expect(head).toContain(">Delivery<");
    expect(head).toContain("signing off");
  });

  it("keeps the door back in the title row once something is signed", () => {
    const html = view({ detail: deliverableDetail(CONFIRMED) });
    const head = html.slice(
      html.indexOf('class="deliver-page__head"'),
      html.indexOf('class="deliver-page__body"'),
    );
    expect(head).toContain('data-role="delivery-reset"');
  });

  it("the lead names the effective part only when one is effective", () => {
    // the fixture's effective construction is honestly absent — the lead must not
    // invent a part name for it (the comp's lead assumes one always exists)
    const html = view();
    expect(html).not.toContain("null for");
  });
});

/**
 * THE SERVED TOLERANCE BANDS ON THE ASSURANCE HEADER (§10-AB.2). The words are
 * toleranceBandsWords' (pinned in domain/deliver.test.ts); what this pins is the
 * surface: the line renders under the policy line when the rows carry served bands,
 * and is ABSENT — not zeroed, not defaulted — when they don't.
 */
describe("the tolerance-bands line", () => {
  it("renders the served bands beside the assurance counts", () => {
    const html = view();
    expect(html).toContain('data-role="tolerance-bands"');
    expect(html).toContain("Tolerance bands (served)");
    expect(html).toContain("pass ≤ 0.50 mm");
  });

  it("is absent when the rows serve no bands", () => {
    const bare = assuranceSite();
    const html = view({
      assurance: {
        kind: "ok",
        data: assuranceView({ sites: [{ ...bare, references: {} }] }),
      },
    });
    expect(html).not.toContain('data-role="tolerance-bands"');
  });
});

describe("the report dialog's copy-for-analysis act (client 2026-08-09)", () => {
  it("the open report offers Copy for analysis beside close", () => {
    const html = view({ reportOpen: true });
    const dialog = html.indexOf('data-role="report-dialog"');
    const copy = html.indexOf('data-role="copy-analysis"');
    expect(dialog).toBeGreaterThan(-1);
    expect(copy).toBeGreaterThan(dialog);
    expect(html).toContain("Copy for analysis");
  });
});

describe("the Delivery re-run act beside the door back (client 2026-08-09)", () => {
  it("renders next to the start-over control, disabled while a confirmation stands", () => {
    const html = view({
      onRerunAlignment: () => undefined,
      detail: deliverableDetail(CONFIRMED),
    });
    const reset = html.indexOf('data-role="delivery-reset"');
    const rerun = html.indexOf('data-role="delivery-rerun"');
    expect(rerun).toBeGreaterThan(-1);
    expect(reset).toBeGreaterThan(-1);
    expect(html).toMatch(/data-role="delivery-rerun"[^>]*disabled/);
    expect(html).toContain("withdraw the confirmation first");
  });

  it("with no confirmation standing the act is live", () => {
    const html = view({
      onRerunAlignment: () => undefined,
      detail: deliverableDetail(),
    });
    expect(html).toContain('data-role="delivery-rerun"');
    expect(html).not.toMatch(/data-role="delivery-rerun"[^>]*disabled/);
  });

  it("no handler, no button", () => {
    expect(view()).not.toContain('data-role="delivery-rerun"');
  });
});
