/**
 * WHAT DISMISSES A DIALOG, and where the focus goes and is trapped.
 *
 * Every dialog in this app already carries `role="dialog"`, `aria-modal="true"`, a fixed
 * scrim and click-outside-to-close. Two things were still missing: none closed on
 * ESCAPE (fixed first, `useDialogEscape`), and none moved or trapped focus — so a
 * keyboard operator who opened one could Tab straight through it into the page behind
 * the scrim, and closing it left the browser's own guess in charge of where focus
 * landed next. The client's comp does neither either; this is one of the places the
 * product should not follow it.
 *
 * §10-O.8 (2026-08-02): jsdom arrives WITH this fix, not before it — a DOM-only
 * concern earns the DOM dependency it needs in the same slice, so jsdom never sits in
 * the tree ahead of the thing that justified it. What belongs HERE stays pure either
 * way: `isDismissKey`/`dismissAllowed` (which key, and whether an act in flight blocks
 * it) and `FOCUSABLE_SELECTOR`/`nextTrapIndex` (what counts as a stop, and the wrap
 * arithmetic at the first/last position) are plain data-in-data-out, pinned here in
 * node with no DOM at all. The effects that ACT on these rules — `useDialogEscape`,
 * `useDialogFocus` — need real elements, and now have jsdom to test against.
 */

/** The one key that dismisses a dialog. Not Backspace, not Enter — Enter belongs to
 *  whatever control has focus, and a dialog that closed on it would discard a form the
 *  operator was submitting. */
export function isDismissKey(key: string): boolean {
  return key === "Escape";
}

/**
 * Whether a dismissal should be honoured at all. A dialog mid-flight — a payment
 * authorizing, a confirmation sealing — must not vanish under the operator: the act is
 * already with the server, and closing the surface that reports it would leave them
 * guessing at the outcome. This is the same reason every busy control in the app
 * disables rather than hides.
 */
export function dismissAllowed(busy: boolean): boolean {
  return !busy;
}

/**
 * What counts as a stop inside the Tab trap. Mirrors the WAI-ARIA APG's focusable-
 * elements list; `[disabled]` and `tabindex="-1"` are excluded on purpose — the
 * checkout's read-only add-card inputs carry `tabIndex={-1}` precisely so a card
 * number nobody can edit never becomes something Tab lands on (CheckoutPage.tsx).
 */
export const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), input:not([disabled]):not([tabindex="-1"]), ' +
  'select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * The Tab trap's wrap arithmetic, and nothing else. `activeIndex` is the currently
 * focused control's position among the dialog's own focusable elements, or `-1` when
 * focus sits on the dialog's container rather than on any control inside it yet (the
 * state right after `useDialogFocus` moves focus in). `count` is how many focusable
 * elements the dialog holds; `backward` is whether the key was Shift-Tab.
 *
 * This answers ONLY the two positions where the browser's native Tab order would
 * otherwise carry focus OUT of the dialog — the last control moving forward, the
 * first control (or the bare container) moving backward — and returns the index to
 * wrap to. Everywhere else it returns `null`, meaning: this is a mid-list Tab, and the
 * browser's own order is already correct, so the caller should do nothing.
 *
 * `null` is also the answer when there is nothing to hold (`count === 0`) — but the
 * CALLER decides what to do about an empty dialog (Tab must still not be allowed to
 * carry focus out through the scrim), because that is a DOM concern, not an
 * arithmetic one, and does not belong in a pure function.
 */
export function nextTrapIndex(
  activeIndex: number,
  count: number,
  backward: boolean,
): number | null {
  if (count === 0) return null;
  if (backward) {
    // Shift-Tab wraps when it lands on the first control, or on the bare container.
    return activeIndex <= 0 ? count - 1 : null;
  }
  // Tab wraps when it lands on the last control, or on the bare container.
  return activeIndex === -1 || activeIndex === count - 1 ? 0 : null;
}
