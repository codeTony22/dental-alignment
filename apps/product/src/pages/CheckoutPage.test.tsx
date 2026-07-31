/**
 * THE MOCK CHECKOUT'S CONTRACT (client 2026-07-30). What matters here is what the
 * page must NEVER be as much as what it shows: no editable card field exists, the
 * demo banner is unmissable, cancel is a first-class exit, and the gate that payment
 * stands on is said up front rather than discovered as a 409.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { StaticRouter } from "react-router-dom";
import { CheckoutView } from "./CheckoutPage";
import { caseSessionDetail } from "../testing/fixtures";
import type { CaseSessionDetail } from "../api/client";

function confirmedDetail(): CaseSessionDetail {
  const base = caseSessionDetail();
  return {
    ...base,
    session: {
      ...base.session,
      confirmation: {
        at: "2026-07-30T12:00:00+00:00",
        run_id: "run-1",
        evidence_sha256: "abc",
        dispositions: {},
        acknowledged_flags: [],
        terms_accepted: true,
        terms_version: "placeholder-v0",
      },
    },
  };
}

function view(detail: CaseSessionDetail, over: Partial<Parameters<typeof CheckoutView>[0]> = {}) {
  return renderToStaticMarkup(
    <StaticRouter location={`/case/${detail.case.id}/checkout`}>
      <CheckoutView
        detail={detail}
        phase="idle"
        error={null}
        card="visa-4242"
        onCard={() => undefined}
        onPay={() => undefined}
        onCancel={() => undefined}
        {...over}
      />
    </StaticRouter>,
  );
}

describe("the mock checkout", () => {
  it("wears the DEMO banner where nobody can miss it", () => {
    const html = view(confirmedDetail());
    expect(html).toContain('data-role="checkout-demo-banner"');
    expect(html).toContain("no provider is contacted, no money moves");
  });

  it("offers saved-card MOCKS and a pay control, and the amount stays a placeholder", () => {
    const html = view(confirmedDetail());
    expect(html).toContain('data-role="saved-card"');
    // Retargeted 2026-07-31: the row became a brand chip + a full masked number
    // that never wraps, rather than one label that broke across two lines.
    expect(html).toContain("VISA");
    expect(html).toContain("•••• •••• •••• 4242");
    expect(html).toContain("MOCK");
    expect(html).toContain('data-role="checkout-pay"');
    expect(html).toContain("PLACEHOLDER — pricing not yet defined");
  });

  it("has NO editable card field — every input is readOnly, structurally", () => {
    const html = view(confirmedDetail());
    // static render: every <input> in the mock form must carry readonly; a single
    // editable field would be a path for a real card number, which this demo must
    // not have
    const inputs = html.match(/<input[^>]*>/g) ?? [];
    expect(inputs.length).toBeGreaterThan(0);
    for (const tag of inputs) {
      expect(tag).toContain("readonly");
    }
  });

  it("cancel is a first-class exit, charging nothing", () => {
    // Retargeted 2026-07-30 (same day): the checkout became a DIALOG over Deliver —
    // "back" now means CLOSE, because the work behind it never went anywhere.
    const html = view(confirmedDetail());
    expect(html).toContain('data-role="checkout-cancel"');
    expect(html).toContain("nothing is charged");
    expect(html).not.toContain('href="/case/case-a/deliver"');
  });

  it("without a confirmed-terms case it states the gate and offers the way back", () => {
    const html = view(caseSessionDetail());
    expect(html).toContain('data-role="checkout-blocked"');
    expect(html).toContain("needs a standing confirmation");
    // and no pay control exists to 409 against
    expect(html).not.toContain('data-role="checkout-pay"');
  });

  it("an already-paid case says so instead of offering to pay twice", () => {
    const base = confirmedDetail();
    const paid = {
      ...base,
      session: { ...base.session, payment_authorized: true },
    } as CaseSessionDetail;
    const html = view(paid);
    expect(html).toContain('data-role="checkout-already-paid"');
    expect(html).not.toContain('data-role="checkout-pay"');
  });
});

describe("the checkout's affordances (rebuilt 2026-07-31)", () => {
  it("the cards are a RADIOGROUP — one of several, which is what radios mean", () => {
    const html = view(confirmedDetail());
    expect(html).toContain('role="radiogroup"');
    expect(html).toContain('role="radio"');
    // the selected one is announced, not merely coloured
    expect(html).toContain('aria-checked="true"');
  });

  it("the locked fields track the SELECTED card, so the form is never a lie", () => {
    const html = view(confirmedDetail(), { card: "mc-4444" });
    expect(html).toContain("•••• •••• •••• 4444");
    expect(html).toContain("09/33");
  });

  it("paying disables both the pay control and the card choice", () => {
    const html = view(confirmedDetail(), { phase: "paying" });
    expect(html).toContain("Authorizing (demo)…");
    // a card swapped mid-authorization would describe a payment that already left
    expect(html).toMatch(/data-role="saved-card"[^>]*disabled/);
  });
});
