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
  { id: "visa-4242", brand: "VISA", last4: "4242", holder: "DEMO CARDHOLDER", expiry: "12/34" },
  { id: "mc-4444", brand: "MC", last4: "4444", holder: "DEMO CARDHOLDER", expiry: "09/33" },
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

/** A dead-end state (nothing to confirm yet, or already paid) — one shape, so the two
 *  cases cannot drift into looking like different products. */
function CheckoutNotice({
  role,
  tone,
  title,
  words,
  action,
  onCancel,
}: {
  readonly role: string;
  readonly tone: "wait" | "done";
  readonly title: string;
  readonly words: string;
  readonly action: string;
  readonly onCancel: () => void;
}) {
  return (
    <div data-role={role} className={`checkout-notice checkout-notice--${tone}`}>
      <span className="checkout-notice__mark" aria-hidden="true">
        {tone === "done" ? "✓" : "!"}
      </span>
      <div className="checkout-notice__body">
        <strong className="checkout-notice__title">{title}</strong>
        <p className="checkout-notice__words">{words}</p>
      </div>
      <button type="button" className="button button--secondary" onClick={onCancel}>
        {action}
      </button>
    </div>
  );
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
  const siteCount = detail.sites.length;
  const selected = SAVED_CARDS.find((row) => row.id === card) ?? SAVED_CARDS[0];
  const busy = phase === "paying";

  return (
    <div data-role="checkout-page" className="checkout-page">
      <header className="checkout-page__header">
        <div>
          <h2 className="checkout-page__title">Checkout</h2>
          <p className="checkout-page__case">
            {detail.case.id} · {detail.case.doctor}
          </p>
        </div>
        {/* the same unmissable tone as the terms placeholder: nobody may mistake
            this screen for a real payment surface */}
        <p data-role="checkout-demo-banner" className="checkout-page__demo">
          DEMO — no provider is contacted, no money moves, and no real card data
          exists on this page
        </p>
      </header>

      {/* THE ORDER, as line items rather than a sentence: a checkout's first job is
          to say exactly what is being bought before it asks for money. */}
      <section className="checkout-section">
        <h3 className="checkout-section__title">Order</h3>
        <dl className="checkout-order">
          <div className="checkout-order__row">
            <dt>Case</dt>
            <dd data-role="checkout-order">
              {detail.case.id} — {siteCount} site{siteCount === 1 ? "" : "s"}
            </dd>
          </div>
          <div className="checkout-order__row">
            <dt>Deliverables</dt>
            <dd>Aligned parts + assurance report</dd>
          </div>
          <div className="checkout-order__row checkout-order__row--total">
            <dt>Amount due</dt>
            <dd data-role="checkout-price">
              <span className="checkout-order__placeholder">
                PLACEHOLDER — pricing not yet defined
              </span>
            </dd>
          </div>
        </dl>
      </section>

      {!confirmed && !paid ? (
        /* the payment gate's own precondition, said HERE rather than discovered as a
           409 after picking a card — the way back is the way forward */
        <CheckoutNotice
          role="checkout-blocked"
          tone="wait"
          title="Not ready to pay yet"
          words={
            "Payment needs a standing confirmation that accepted the terms — " +
            "this case does not have one yet."
          }
          action="Close — confirm first"
          onCancel={onCancel}
        />
      ) : paid ? (
        <CheckoutNotice
          role="checkout-already-paid"
          tone="done"
          title="Already paid"
          words={
            "This case carries a demo payment record (provider “stub”). " +
            "Nothing further is charged."
          }
          action="Close"
          onCancel={onCancel}
        />
      ) : (
        <>
          <section className="checkout-section">
            <h3 className="checkout-section__title">Payment method</h3>
            {/* a RADIOGROUP, not a row of pressed buttons: picking one of several
                mutually exclusive cards is exactly what radios mean, and screen
                readers get the "1 of 2" for free */}
            <ul
              data-role="saved-cards"
              className="checkout-cards"
              role="radiogroup"
              aria-label="Saved cards (mock)"
            >
              {SAVED_CARDS.map((row) => {
                const active = row.id === selected.id;
                return (
                  <li key={row.id}>
                    <button
                      type="button"
                      role="radio"
                      data-role="saved-card"
                      data-card={row.id}
                      aria-checked={active}
                      className={`checkout-card${
                        active ? " checkout-card--selected" : ""
                      }`}
                      disabled={busy}
                      onClick={() => onCard(row.id)}
                    >
                      <span className="checkout-card__radio" aria-hidden="true" />
                      <span
                        className={`checkout-card__brand checkout-card__brand--${row.id}`}
                        aria-hidden="true"
                      >
                        {row.brand}
                      </span>
                      <span className="checkout-card__lines">
                        <span className="checkout-card__label">
                          •••• •••• •••• {row.last4}
                        </span>
                        <span className="checkout-card__holder">
                          {row.holder} · expires {row.expiry}
                        </span>
                      </span>
                      <span className="checkout-card__mock">MOCK</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>

          <section className="checkout-section">
            <h3 className="checkout-section__title">
              Card details
              <span className="checkout-section__lock" aria-hidden="true">
                🔒 locked
              </span>
            </h3>
            {/* readOnly BY DESIGN — there must be no code path by which a real card
                number can be typed into a demo. Styled as LOCKED rather than
                broken: the previous dashed-input treatment read as a form that had
                failed to load (client 2026-07-30). */}
            <div data-role="mock-card-form" className="checkout-form">
              <label className="checkout-form__field">
                <span className="checkout-form__label">Card number</span>
                <input readOnly tabIndex={-1} value={`•••• •••• •••• ${selected.last4}`} />
              </label>
              <label className="checkout-form__field checkout-form__field--short">
                <span className="checkout-form__label">Expiry</span>
                <input readOnly tabIndex={-1} value={selected.expiry} />
              </label>
              <label className="checkout-form__field checkout-form__field--short">
                <span className="checkout-form__label">CVC</span>
                <input readOnly tabIndex={-1} value="•••" />
              </label>
            </div>
            <p className="checkout-form__note">
              Mock values, not editable — this demo holds no card data to enter.
            </p>
          </section>

          {error !== null && (
            <div data-role="checkout-error" role="alert" className="panel__error">
              {error}
            </div>
          )}

          {/* the actions sit in a footer bar: the primary act leads, the way out is
              always beside it, and the reassurance rides under both */}
          <footer className="checkout-page__actions">
            <button
              type="button"
              data-role="checkout-pay"
              className="button button--primary checkout-pay"
              disabled={busy}
              onClick={onPay}
            >
              {busy ? "Authorizing (demo)…" : "Pay (demo)"}
            </button>
            <button
              type="button"
              data-role="checkout-cancel"
              className="button button--secondary"
              disabled={busy}
              onClick={onCancel}
            >
              Cancel (nothing is charged)
            </button>
          </footer>
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
        className="decode-dialog decode-dialog--checkout"
        role="dialog"
        aria-modal="true"
        aria-label="Checkout (demo)"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="decode-dialog__body decode-dialog__body--plain">
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
