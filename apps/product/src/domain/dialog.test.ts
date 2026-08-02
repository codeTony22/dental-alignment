/**
 * The dialog dismissal and focus-trap rules. Pure — every function here is data in,
 * data out, so this file stays node-only even now that jsdom has landed in this
 * package (§10-O.8): the DOM the effects need lives in the hooks that consume these
 * rules (`useDialogEscape.test.tsx`, `useDialogFocus.test.tsx`), never here.
 */
import { describe, expect, it } from "vitest";
import { FOCUSABLE_SELECTOR, dismissAllowed, isDismissKey, nextTrapIndex } from "./dialog";

describe("isDismissKey — Escape, and nothing else", () => {
  it("dismisses on Escape", () => {
    expect(isDismissKey("Escape")).toBe(true);
  });

  it("does NOT dismiss on Enter — that belongs to whatever has focus", () => {
    // a dialog that closed on Enter would discard the form the operator was submitting
    expect(isDismissKey("Enter")).toBe(false);
  });

  it("ignores every other key, including the ones that look like exits", () => {
    for (const key of ["Backspace", "Delete", "Tab", " ", "q", "Esc"]) {
      expect(isDismissKey(key)).toBe(false);
    }
  });
});

describe("dismissAllowed — an act in flight is not interruptible", () => {
  it("allows dismissal when nothing is running", () => {
    expect(dismissAllowed(false)).toBe(true);
  });

  it("REFUSES while busy — the act is already with the server", () => {
    /* Closing the surface that reports a payment or a sealing confirmation would leave
       the operator guessing at an outcome the server has already begun. Same reason
       every busy control in this app disables rather than disappears. */
    expect(dismissAllowed(true)).toBe(false);
  });
});

describe("nextTrapIndex — the Tab trap's wrap arithmetic (the DOM lives in useDialogFocus.test.tsx)", () => {
  it("answers null in an empty dialog — the caller decides what an empty trap does", () => {
    expect(nextTrapIndex(-1, 0, false)).toBeNull();
    expect(nextTrapIndex(-1, 0, true)).toBeNull();
  });

  it("Tab from the last control wraps to the first", () => {
    expect(nextTrapIndex(2, 3, false)).toBe(0);
  });

  it("Tab from the bare container — focus just moved in, nothing inside has it yet — goes to the first", () => {
    expect(nextTrapIndex(-1, 3, false)).toBe(0);
  });

  it("Shift-Tab from the first control wraps to the last", () => {
    expect(nextTrapIndex(0, 3, true)).toBe(2);
  });

  it("Shift-Tab from the bare container goes to the last", () => {
    expect(nextTrapIndex(-1, 3, true)).toBe(2);
  });

  it("a middle control answers null both ways — the browser's own Tab order is already right there", () => {
    expect(nextTrapIndex(1, 3, false)).toBeNull();
    expect(nextTrapIndex(1, 3, true)).toBeNull();
  });

  it("a single-control dialog wraps to itself, not out — Tab and Shift-Tab both land back on index 0", () => {
    expect(nextTrapIndex(0, 1, false)).toBe(0);
    expect(nextTrapIndex(0, 1, true)).toBe(0);
  });
});

describe("FOCUSABLE_SELECTOR — what the trap will and will not stop at", () => {
  it("excludes disabled controls", () => {
    expect(FOCUSABLE_SELECTOR).toContain(":not([disabled])");
  });

  it('excludes tabindex="-1" — the checkout\'s read-only add-card inputs ' +
    "(CheckoutPage.tsx) rely on this to never become a trap stop", () => {
    expect(FOCUSABLE_SELECTOR).toContain(':not([tabindex="-1"])');
  });
});
