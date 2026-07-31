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
import { useEffect, useRef, useState } from "react";
import {
  postCheckoutReturn,
  postPayment,
  type CaseSessionDetail,
} from "../api/client";

type CheckoutPhase = "idle" | "paying" | "failed";

export interface MockCard {
  readonly id: string;
  readonly brand: string;
  readonly last4: string;
  readonly holder: string;
  readonly expiry: string;
}

export const SAVED_CARDS: readonly [MockCard, ...MockCard[]] = [
  { id: "visa-4242", brand: "VISA", last4: "4242", holder: "DEMO CARDHOLDER", expiry: "12/34" },
  { id: "mc-4444", brand: "MC", last4: "4444", holder: "DEMO CARDHOLDER", expiry: "09/33" },
];

/**
 * The cards an "add a new card" can produce, in order.
 *
 * A demo must have NO path by which a real card number is typed, so adding a card
 * cannot mean an editable form. It means the demo hands you the next card off this
 * pool, pre-filled and visibly locked — the FLOW is real (choose to add, see the
 * details, confirm, it joins the list and becomes selected) while the DATA never
 * comes from a keyboard.
 */
export const ADDABLE_CARDS: readonly MockCard[] = [
  { id: "amex-0005", brand: "AMEX", last4: "0005", holder: "DEMO CARDHOLDER", expiry: "04/35" },
  { id: "visa-1881", brand: "VISA", last4: "1881", holder: "DEMO CARDHOLDER", expiry: "07/36" },
];

/** The next card this demo can add, or null once the pool is spent. */
export function nextAddableCard(
  existing: readonly MockCard[],
  pool: readonly MockCard[] = ADDABLE_CARDS,
): MockCard | null {
  return pool.find((row) => !existing.some((have) => have.id === row.id)) ?? null;
}

export interface CheckoutViewProps {
  readonly detail: CaseSessionDetail;
  readonly phase: CheckoutPhase;
  readonly error: string | null;
  readonly cards: readonly MockCard[];
  readonly card: string;
  readonly onCard: (id: string) => void;
  /** The add-a-card panel's open state and its two acts. */
  readonly adding: boolean;
  readonly onStartAdd: () => void;
  readonly onCancelAdd: () => void;
  readonly onAddCard: (card: MockCard) => void;
  /** A wallet button (client 2026-07-31) — the same two-leg flow, named. */
  readonly onWalletPay: (wallet: string) => void;
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
  cards,
  card,
  onCard,
  adding,
  onStartAdd,
  onCancelAdd,
  onAddCard,
  onWalletPay,
  onPay,
  onCancel,
}: CheckoutViewProps) {
  const confirmed =
    detail.session.confirmation !== null &&
    detail.session.confirmation?.terms_accepted === true;
  const paid = detail.session.payment_authorized;
  const siteCount = detail.sites.length;
  // may be null: an empty card list is a state the type allows, and a checkout with
  // no method should say so rather than render a details panel about nothing
  const selected = cards.find((row) => row.id === card) ?? cards[0] ?? null;
  const busy = phase === "paying";
  const pending = nextAddableCard(cards);

  /* Opening the panel grows the dialog past its height, and the sticky pay bar then
     sits over the panel's own Add/Cancel (measured 2026-07-31: CTA bottom 644 vs bar
     top 582). The bar is sticky, not fixed, so it yields at the end of the scroll —
     the panel only has to bring itself into view. Effects do not run under
     renderToStaticMarkup, so this costs the static tests nothing. */
  const panelRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (adding) panelRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [adding]);

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
          {/* EXPRESS CHECKOUT (client 2026-07-31: "add in apple pay and android paid
              button mocks"). Wallets sit ABOVE the card list and under their own
              divider, which is where every real checkout puts them — they are a way
              to skip the card entirely, not another card. Both are MOCKS and say so;
              each runs the same two-leg flow the card button does. */}
          <section className="checkout-section">
            <h3 className="checkout-section__title">Express checkout</h3>
            <div data-role="wallets" className="checkout-wallets">
              <button
                type="button"
                data-role="wallet-pay"
                data-wallet="apple-pay"
                className="checkout-wallet checkout-wallet--apple"
                disabled={busy}
                onClick={() => onWalletPay("apple-pay")}
              >
                {/* THE WORDS, not the logos. "" is an Apple-font private-use
                    character: measured 2026-07-31 it painted at width 0 in a
                    non-Apple browser, leaving a black button that just said "Pay".
                    Drawing the real marks instead would mean reproducing two
                    trademarks on a fake payment button — the opposite of what a
                    mock should do. Text renders everywhere and forges nothing. */}
                <span className="checkout-wallet__word">Apple Pay</span>
                <span className="checkout-wallet__mock">MOCK</span>
              </button>
              <button
                type="button"
                data-role="wallet-pay"
                data-wallet="google-pay"
                className="checkout-wallet checkout-wallet--google"
                disabled={busy}
                onClick={() => onWalletPay("google-pay")}
              >
                <span className="checkout-wallet__word">Google Pay</span>
                <span className="checkout-wallet__mock">MOCK</span>
              </button>
            </div>
            <p className="checkout-divider">
              <span>or pay with a card</span>
            </p>
          </section>

          <section className="checkout-section">
            <h3 className="checkout-section__title">
              Payment method
              <span className="checkout-section__lock" aria-hidden="true">
                🔒 nothing here is typed
              </span>
            </h3>
            {/* a RADIOGROUP, not a row of pressed buttons: picking one of several
                mutually exclusive cards is exactly what radios mean, and screen
                readers get the "1 of N" for free */}
            <ul
              data-role="saved-cards"
              className="checkout-cards"
              role="radiogroup"
              aria-label="Saved cards (mock)"
            >
              {cards.map((row) => {
                const active = row.id === selected?.id;
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
                        className={`checkout-card__brand checkout-card__brand--${row.brand.toLowerCase()}`}
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

            {/* ADD A NEW CARD (client 2026-07-31: "Add a new card needs to be
                better"). It was not there at all — the only card surface was the
                locked detail of whichever card was already selected. */}
            {!adding && pending !== null && (
              <button
                type="button"
                data-role="add-card-open"
                className="checkout-add"
                disabled={busy}
                onClick={onStartAdd}
              >
                <span className="checkout-add__plus" aria-hidden="true">
                  +
                </span>
                Add a new card
              </button>
            )}
            {!adding && pending === null && (
              <p data-role="add-card-exhausted" className="checkout-form__note">
                Every demo card is already on this case — the pool is not a keyboard,
                so there are no more to add.
              </p>
            )}

            {adding && pending !== null && (
              /* The FLOW is real — choose to add, see the details, confirm, it joins
                 the list and becomes selected. The DATA never comes from a keyboard:
                 a demo must have no path by which a real card number is typed, so
                 the fields are pre-filled and readOnly like every other card field
                 on this page. */
              <div ref={panelRef} data-role="add-card-panel" className="checkout-add-panel">
                <div className="checkout-add-panel__head">
                  <strong>New card</strong>
                  <span className="checkout-card__mock">MOCK</span>
                  {/* the dismiss lives in the HEAD, and Add sits at the end of the
                      field row: a second action BAR here would land under the
                      dialog's sticky pay bar (measured 2026-07-31) — two competing
                      footers, one of them hidden. One bar per dialog. */}
                  <button
                    type="button"
                    data-role="add-card-cancel"
                    className="checkout-add-panel__dismiss"
                    aria-label="Cancel adding a card"
                    onClick={onCancelAdd}
                  >
                    ×
                  </button>
                </div>
                <div data-role="mock-new-card-form" className="checkout-form">
                  <label className="checkout-form__field">
                    <span className="checkout-form__label">Card number</span>
                    <input
                      readOnly
                      tabIndex={-1}
                      value={`•••• •••• •••• ${pending.last4}`}
                    />
                  </label>
                  <label className="checkout-form__field checkout-form__field--short">
                    <span className="checkout-form__label">Expiry</span>
                    <input readOnly tabIndex={-1} value={pending.expiry} />
                  </label>
                  <label className="checkout-form__field checkout-form__field--short">
                    <span className="checkout-form__label">CVC</span>
                    <input readOnly tabIndex={-1} value="•••" />
                  </label>
                  <button
                    type="button"
                    data-role="add-card-confirm"
                    className="button button--primary button--small checkout-add-panel__go"
                    onClick={() => onAddCard(pending)}
                  >
                    Add
                  </button>
                </div>
                <p className="checkout-form__note">
                  Pre-filled by the demo — this page accepts no typed card data.
                </p>
              </div>
            )}
          </section>

          {/* THE "CARD DETAILS" SECTION IS GONE (2026-07-31). It restated the
              selected card row verbatim — same masked number, same expiry, plus a
              CVC that was literally "•••" — and those 135px were the entire reason
              the dialog scrolled and buried the Pay button. The selected row IS the
              card's details; the lock now lives on the section that owns them. */}

          {error !== null && (
            <div data-role="checkout-error" role="alert" className="panel__error">
              {error}
            </div>
          )}

          {/* the actions sit in a footer bar: the primary act leads, the way out is
              always beside it */}
          <footer className="checkout-page__actions">
            <button
              type="button"
              data-role="checkout-pay"
              className="button button--primary checkout-pay"
              disabled={busy || selected === null}
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
  const [cards, setCards] = useState<readonly MockCard[]>(SAVED_CARDS);
  const [card, setCard] = useState<string>(SAVED_CARDS[0].id);
  const [adding, setAdding] = useState(false);

  /** Both legs, named by whatever method paid — the reference is the only place the
   *  method appears, because the SERVER records provider "stub" either way: a wallet
   *  mock must not be able to describe itself as a different provider than it is. */
  const pay = (method: string) => {
    setPhase("paying");
    setError(null);
    void postPayment(detail.case.id).then((paid) => {
      if (paid.kind !== "ok") {
        setPhase("failed");
        setError(paid.detail);
        return;
      }
      void postCheckoutReturn(detail.case.id, `demo-${method}`).then((returned) => {
        onDetail(returned.kind === "ok" ? returned.data : paid.data);
        onClose();
      });
    });
  };

  const handlePay = () => pay(card);

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
            cards={cards}
            card={card}
            onCard={setCard}
            adding={adding}
            onStartAdd={() => setAdding(true)}
            onCancelAdd={() => setAdding(false)}
            onAddCard={(added) => {
              // added AND selected: adding a card you then have to go and pick is a
              // step the operator did not ask for
              setCards((now) => [...now, added]);
              setCard(added.id);
              setAdding(false);
            }}
            onWalletPay={pay}
            onPay={handlePay}
            onCancel={onClose}
          />
        </div>
      </section>
    </div>
  );
}
