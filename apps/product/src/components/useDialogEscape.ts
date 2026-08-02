/**
 * ESCAPE CLOSES A DIALOG. Every modal in this app carried `role="dialog"`,
 * `aria-modal="true"`, a fixed scrim and click-outside-to-close, and none of them
 * listened for Escape — so a keyboard operator could open the checkout, the arch, the
 * gate reasons or the full report and have no way out but the mouse.
 *
 * THE EFFECT ITSELF IS NOW COVERED (§10-O.8, 2026-08-02): jsdom landed in this package
 * in the same slice that added `useDialogFocus`, its sibling gap (focus never moved
 * INTO a dialog, either) — so the listener no longer needs to be hand-verified.
 * `useDialogEscape.test.tsx` drives it with `createRoot`/`act` against a fixture,
 * pinning the capture-phase-plus-`stopPropagation` contract (a bubble-phase listener
 * added by the test never sees the key), the busy refusal, and that only Escape acts.
 * The two RULES the listener applies — which key dismisses, and whether a dismissal is
 * allowed while an act is in flight — stay pure and pinned in `domain/dialog.test.ts`,
 * which stays node-only: nothing about that arithmetic needed a DOM, so it never got one.
 */
import { useEffect } from "react";
import { dismissAllowed, isDismissKey } from "../domain/dialog";

export function useDialogEscape(
  open: boolean,
  onClose: () => void,
  busy = false,
): void {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (!isDismissKey(event.key)) return;
      if (!dismissAllowed(busy)) return;
      // stop the key reaching anything behind the scrim — a dialog is modal or it is not
      event.stopPropagation();
      onClose();
    };
    // capture, so a control inside the dialog that swallows keydown cannot trap the
    // operator inside the surface the key exists to leave
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [open, onClose, busy]);
}
