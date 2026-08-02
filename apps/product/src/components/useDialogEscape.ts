/**
 * ESCAPE CLOSES A DIALOG. Every modal in this app carried `role="dialog"`,
 * `aria-modal="true"`, a fixed scrim and click-outside-to-close, and none of them
 * listened for Escape — so a keyboard operator could open the checkout, the arch, the
 * gate reasons or the full report and have no way out but the mouse.
 *
 * THE EFFECT ITSELF IS NOT COVERED BY THE SUITE, and that is worth saying rather than
 * implying: these tests render with `renderToStaticMarkup` in NODE, with no jsdom, so
 * nothing here can dispatch a keydown. The two RULES it applies — which key dismisses,
 * and whether a dismissal is allowed while an act is in flight — are pure and pinned in
 * `domain/dialog.test.ts`. Covering the listener means adding jsdom to this package,
 * which is a decision of its own and not one to smuggle in beside a modal fix.
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
