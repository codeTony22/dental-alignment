/**
 * THE MOCK CHECKOUT (client 2026-07-30: "it does not routes me to add credit card or
 * saved credit card mocks, also no way of going back").
 *
 * This page plays the ROLE of a payment provider's hosted checkout: Deliver links
 * here, and paying returns you to Deliver — the exact shape a real integration has,
 * so swapping in a real provider later changes this page's guts and nothing about the
 * flow around it. Three rules hold it honest:
 *
 *   - NO REAL CARD ENTRY, structurally. The "card" fields are readOnly mock values —
 *     there is no code path by which a real number could be typed here, which is the
 *     only acceptable shape for a demo card form. The saved-card rows are mocks with
 *     the word MOCK on them.
 *   - CANCEL IS A FIRST-CLASS EXIT. Backing out returns to Deliver having paid
 *     nothing — a checkout you can only leave by paying is a trap, not a screen.
 *   - PAYING RUNS BOTH LEGS the way a real redirect would: the authorization, then
 *     the return leg — which asserts NOTHING and merely re-reads the case. Only the
 *     BFF's own state says whether payment happened.
 */
import { useState } from "react";
import {
  postCheckoutReturn,
  postPayment,
  type CaseSessionDetail,
} from "../api/client";

type CheckoutPhase = "idle" | "paying" | "failed";

const SAVED_CARDS = [
  { id: "visa-4242", label: "Visa •••• 4242", holder: "DEMO CARDHOLDER" },
  { id: "mc-4444", label: "Mastercard •••• 4444", holder: "DEMO CARDHOLDER" },
] as const;

export interface CheckoutViewProps {
  readonly detail: CaseSessionDetail;
  readonly phase: CheckoutPhase;
  readonly error: string | null;
  readonly card: string;
  readonly onCard: (id: string) => void;
  readonly onPay: () => void;
  /** Every exit is CLOSE (client 2026-07-30: "might be better on a modal, so the
   *  client can still see their work on the background") — the work behind this
   *  dialog never went anywhere, so there is nothing to navigate back to. */
  readonly onCancel: () => void;
}

/** Pure markup — statically testable; the container owns the flow. */
export function CheckoutView({
  detail,
  phase,
  error,
  card,
  onCard,
  onPay,
  onCancel,
}: CheckoutViewProps) {
  const confirmed =
    detail.session.confirmation !== null &&
    detail.session.confirmation?.terms_accepted === true;
  const paid = detail.session.payment_authorized;
  return (
    <div data-role="checkout-page" className="checkout-page">
      <header className="checkout-page__header">
        <h2 className="checkout-page__title">Checkout</h2>
        {/* the same unmissable tone as the terms placeholder: nobody may mistake
            this screen for a real payment surface */}
        <p data-role="checkout-demo-banner" className="terms-block__placeholder">
          DEMO — no provider is contacted, no money moves, no real card data exists
          on this page
        </p>
      </header>

      <section className="checkout-page__summary panel">
        <h3 className="panel__title">Order</h3>
        <p data-role="checkout-order">
          Case {detail.case.id} — {detail.sites.length} site
          {detail.sites.length === 1 ? "" : "s"}
        </p>
        <p data-role="checkout-price" className="checkout-screen__price">
          Amount due: <strong>PLACEHOLDER — pricing not yet defined</strong>
        </p>
      </section>

      {!confirmed && !paid ? (
        /* the payment gate's own precondition, said HERE rather than discovered as a
           409 after picking a card — the way back is the way forward */
        <section data-role="checkout-blocked" className="panel">
          <p className="panel__hint">
            Payment needs a standing confirmation that accepted the terms — this case
            does not have one yet.
          </p>
          <button type="button" className="button button--primary" onClick={onCancel}>
            Close — confirm first
          </button>
        </section>
      ) : paid ? (
        <section data-role="checkout-already-paid" className="panel">
          <p className="panel__hint">
            This case is already paid (demo record, provider “stub”).
          </p>
          <button type="button" className="button button--primary" onClick={onCancel}>
            Close
          </button>
        </section>
      ) : (
        <>
          <section className="panel">
            <h3 className="panel__title">Saved cards (mock)</h3>
            <ul data-role="saved-cards" className="checkout-cards">
              {SAVED_CARDS.map((row) => (
                <li key={row.id}>
                  <button
                    type="button"
                    data-role="saved-card"
                    data-card={row.id}
                    aria-pressed={card === row.id}
                    className={`checkout-card${
                      card === row.id ? " checkout-card--selected" : ""
                    }`}
                    onClick={() => onCard(row.id)}
                  >
                    <span className="checkout-card__label">{row.label}</span>
                    <span className="checkout-card__holder">{row.holder}</span>
                    <span className="checkout-card__mock">MOCK</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>

          <section className="panel">
            <h3 className="panel__title">Card details (mock — not editable)</h3>
            {/* readOnly BY DESIGN: a demo must have no path by which a real card
                number can be typed. These fields exist so the screen reads like the
                checkout it stands in for, and for no other reason. */}
            <div data-role="mock-card-form" className="checkout-form">
              <label className="checkout-form__field">
                Card number
                <input readOnly value="4242 4242 4242 4242" />
              </label>
              <label className="checkout-form__field checkout-form__field--short">
                Expiry
                <input readOnly value="12/34" />
              </label>
              <label className="checkout-form__field checkout-form__field--short">
                CVC
                <input readOnly value="•••" />
              </label>
            </div>
          </section>

          <div className="checkout-page__actions">
            <button
              type="button"
              data-role="checkout-pay"
              className="button button--primary"
              disabled={phase === "paying"}
              onClick={onPay}
            >
              {phase === "paying" ? "Paying (demo)…" : "Pay (demo)"}
            </button>
            <button
              type="button"
              data-role="checkout-cancel"
              className="button button--secondary"
              onClick={onCancel}
            >
              Cancel (nothing is charged)
            </button>
          </div>
          {error !== null && (
            <div data-role="checkout-error" role="alert" className="panel__error">
              {error}
            </div>
          )}
        </>
      )}
    </div>
  );
}

/**
 * THE CHECKOUT DIALOG (client 2026-07-30: "might be better on a modal, so the client
 * can still see their work on the background and paid"). The first version was a
 * separate ROUTE — a real redirect — and the work vanished behind it. As a dialog the
 * assurance stays visible underneath, paying updates the page in place, and cancel is
 * merely closing. The two-leg shape survives intact: authorize, then the return leg
 * that asserts nothing — only the BFF's record says whether payment happened.
 */
export function CheckoutDialog({
  detail,
  onDetail,
  onClose,
}: {
  readonly detail: CaseSessionDetail;
  readonly onDetail: (next: CaseSessionDetail) => void;
  readonly onClose: () => void;
}) {
  const [phase, setPhase] = useState<CheckoutPhase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [card, setCard] = useState<string>(SAVED_CARDS[0].id);

  const handlePay = () => {
    setPhase("paying");
    setError(null);
    void postPayment(detail.case.id).then((paid) => {
      if (paid.kind !== "ok") {
        setPhase("failed");
        setError(paid.detail);
        return;
      }
      void postCheckoutReturn(detail.case.id, `demo-${card}`).then((returned) => {
        onDetail(returned.kind === "ok" ? returned.data : paid.data);
        onClose();
      });
    });
  };

  return (
    <div
      data-role="checkout-backdrop"
      className="decode-dialog-backdrop"
      onClick={onClose}
    >
      <section
        data-role="checkout-dialog"
        className="decode-dialog decode-dialog--narrow"
        role="dialog"
        aria-modal="true"
        aria-label="Checkout (demo)"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="decode-dialog__body">
          <CheckoutView
            detail={detail}
            phase={phase}
            error={error}
            card={card}
            onCard={setCard}
            onPay={handlePay}
            onCancel={onClose}
          />
        </div>
      </section>
    </div>
  );
}
