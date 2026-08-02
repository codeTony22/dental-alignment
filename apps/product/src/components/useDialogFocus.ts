/**
 * FOCUS MOVES INTO A DIALOG WHEN IT OPENS, IS TRAPPED WHILE IT IS OPEN, AND COMES BACK
 * WHEN IT CLOSES (§10-O.8, 2026-08-02 — landing beside `useDialogEscape`, the sibling
 * gap its own header named: Escape closed a dialog, but nothing moved focus INTO one,
 * so a keyboard operator who opened the checkout, the arch, the gate reasons or the
 * full report was reading a surface that claimed `aria-modal="true"` while their next
 * Tab could carry them straight through it into the page behind the scrim).
 *
 * INITIAL FOCUS: the first element carrying `data-autofocus`, or — failing that — the
 * first focusable element in the dialog (`FOCUSABLE_SELECTOR`, domain/dialog.ts). Each
 * of the four call sites marks its own least-destructive control explicitly rather
 * than trusting DOM order to pick something safe: the checkout's first focusable
 * element in markup order is an Apple Pay MOCK button, and a fallback that lands
 * there would auto-pay on Enter the instant the dialog opened.
 *
 * THE TRAP lives on the dialog node itself, not on window: only Tab is intercepted,
 * and only at the two positions where the browser's native order would carry focus
 * OUT of the dialog (`nextTrapIndex` answers those two positions and nothing else —
 * a mid-list Tab is left to the browser, which already gets it right).
 *
 * RESTORE ON CLOSE: `document.activeElement` at the moment `open` flips true is
 * captured once, in a ref, and refocused on cleanup — never assumed to be the opener
 * button, because an artifact-preview CARD click and a keyboard-driven queue-why
 * button both open dialogs in this app and neither is "the opener" more than the
 * other. A successful payment (CheckoutPage.tsx) unmounts its own opener in the same
 * tick that closes the dialog, so the restore is guarded by `isConnected` — focus
 * falling through to `<body>` is a fine outcome; a throw on the happiest path is not.
 */
import { useEffect, useRef, type RefObject } from "react";
import { FOCUSABLE_SELECTOR, nextTrapIndex } from "../domain/dialog";

export function useDialogFocus(
  open: boolean,
  dialogRef: RefObject<HTMLElement | null>,
): void {
  // Stable across the component's life (useRef), so it is safe to leave out of the
  // effect's own dependency array below without the effect ever reading a stale one.
  const openerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return undefined;
    const dialog = dialogRef.current;
    if (dialog === null) return undefined;

    openerRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;

    const focusables = () =>
      Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
    const explicit = dialog.querySelector<HTMLElement>("[data-autofocus]");
    const initial = explicit ?? focusables()[0] ?? dialog;
    initial.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;
      const elements = focusables();
      if (elements.length === 0) {
        // Nothing inside to hand focus to — Tab must not carry the operator out
        // through the scrim of a surface that is still claiming to be modal.
        event.preventDefault();
        return;
      }
      const active = document.activeElement;
      const activeIndex = active instanceof HTMLElement ? elements.indexOf(active) : -1;
      const target = nextTrapIndex(activeIndex, elements.length, event.shiftKey);
      if (target === null) return; // mid-list — the browser's own Tab order is right
      event.preventDefault();
      elements[target]?.focus();
    };
    dialog.addEventListener("keydown", onKeyDown);

    return () => {
      dialog.removeEventListener("keydown", onKeyDown);
      const opener = openerRef.current;
      if (opener !== null && opener.isConnected) opener.focus();
    };
  }, [open, dialogRef]);
}
