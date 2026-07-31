/**
 * THE MOCK CHECKOUT'S CONTRACT (client 2026-07-30). What matters here is what the
 * page must NEVER be as much as what it shows: no editable card field exists, the
 * demo banner is unmissable, cancel is a first-class exit, and the gate that payment
 * stands on is said up front rather than discovered as a 409.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { StaticRouter } from "react-router-dom";
import { ADDABLE_CARDS, CheckoutView, SAVED_CARDS, nextAddableCard } from "./CheckoutPage";
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
        cards={SAVED_CARDS}
        card="visa-4242"
        onCard={() => undefined}
        adding={false}
        onStartAdd={() => undefined}
        onCancelAdd={() => undefined}
        onAddCard={() => undefined}
        onWalletPay={() => undefined}
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

  it("has NO editable card field — when idle there is no input AT ALL", () => {
    // Retargeted 2026-07-31 alongside the removal of the duplicated "Card details"
    // section: the strongest possible form of "a real number cannot be typed here"
    // is that the idle checkout renders no text input whatsoever.
    const html = view(confirmedDetail());
    expect(html.match(/<input[^>]*>/g) ?? []).toHaveLength(0);
    expect(html).not.toContain('data-role="mock-card-form"');
  });

  it("the only inputs that ever exist — the add-card panel's — are readOnly", () => {
    const html = view(confirmedDetail(), { adding: true });
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

  it("the selected card ROW carries its own number and expiry — no second copy to drift", () => {
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

describe("express checkout: the wallet mocks (client 2026-07-31)", () => {
  it("offers Apple Pay and Google Pay ABOVE the card list, both marked MOCK", () => {
    const html = view(confirmedDetail());
    expect(html).toContain('data-wallet="apple-pay"');
    expect(html).toContain('data-wallet="google-pay"');
    expect(html).toContain("or pay with a card");
    // placement is the point: a wallet is a way to SKIP the card, so it must not
    // read as one more card in the list
    expect(html.indexOf('data-role="wallets"')).toBeLessThan(
      html.indexOf('data-role="saved-cards"'),
    );
  });

  it("neither wallet claims to be real — the MOCK badge is on the button itself", () => {
    const html = view(confirmedDetail());
    const wallets = html.match(/<button[^>]*data-role="wallet-pay"[\s\S]*?<\/button>/g) ?? [];
    expect(wallets).toHaveLength(2);
    for (const button of wallets) expect(button).toContain("MOCK");
  });

  it("a blocked or already-paid case offers no wallet either", () => {
    // the gate is the CASE's, not the payment method's: a wallet that worked while
    // the card was refused would be a way around the confirmation requirement
    expect(view(caseSessionDetail())).not.toContain('data-role="wallet-pay"');
    const base = confirmedDetail();
    const paid = {
      ...base,
      session: { ...base.session, payment_authorized: true },
    } as CaseSessionDetail;
    expect(view(paid)).not.toContain('data-role="wallet-pay"');
  });

  it("authorizing disables the wallets too", () => {
    const html = view(confirmedDetail(), { phase: "paying" });
    expect(html).toMatch(/data-role="wallet-pay"[^>]*disabled/);
  });
});

describe("adding a card (client 2026-07-31: 'needs to be better')", () => {
  it("offers the add control while the pool still has a card", () => {
    const html = view(confirmedDetail());
    expect(html).toContain('data-role="add-card-open"');
    expect(html).toContain("Add a new card");
    expect(html).not.toContain('data-role="add-card-panel"');
  });

  it("the open panel shows the NEXT pool card, pre-filled and locked", () => {
    const html = view(confirmedDetail(), { adding: true });
    expect(html).toContain('data-role="add-card-panel"');
    expect(html).toContain("•••• •••• •••• 0005"); // amex, the first addable
    expect(html).toContain('data-role="add-card-confirm"');
    expect(html).toContain('data-role="add-card-cancel"');
    // and it is STILL true that no input on this page can be typed into
    for (const tag of html.match(/<input[^>]*>/g) ?? []) {
      expect(tag).toContain("readonly");
    }
  });

  it("says so honestly once the pool is spent, rather than offering a dead button", () => {
    const html = view(confirmedDetail(), {
      cards: [...SAVED_CARDS, ...ADDABLE_CARDS],
    });
    expect(html).toContain('data-role="add-card-exhausted"');
    expect(html).not.toContain('data-role="add-card-open"');
  });
});

describe("nextAddableCard", () => {
  it("returns the first pool card not already held", () => {
    expect(nextAddableCard(SAVED_CARDS)?.id).toBe("amex-0005");
    expect(nextAddableCard([...SAVED_CARDS, ADDABLE_CARDS[0]!])?.id).toBe("visa-1881");
  });

  it("returns null — never a repeat — once every pool card is held", () => {
    expect(nextAddableCard([...SAVED_CARDS, ...ADDABLE_CARDS])).toBeNull();
  });
});
