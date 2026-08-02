/**
 * WHAT DISMISSES A DIALOG, and where the focus goes.
 *
 * Every dialog in this app already carries `role="dialog"`, `aria-modal="true"`, a fixed
 * scrim and click-outside-to-close. None of them closed on ESCAPE, and none moved focus
 * — so a keyboard operator could open the checkout and have no way out of it but the
 * mouse, and a screen-reader user was left reading the page behind a modal that claimed
 * to be modal. The client's comp has neither either; this is one of the places the
 * product should not follow it.
 *
 * The KEY TEST is pure and lives here so it can be pinned; the effect that listens for
 * it needs a DOM and this suite runs in node, which is stated where the hook is used.
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
