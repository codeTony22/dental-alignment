/**
 * The dialog dismissal rules. Pure — the listener that consumes them needs a DOM, and
 * this suite runs in node with no jsdom, which is stated at the hook that uses these.
 */
import { describe, expect, it } from "vitest";
import { dismissAllowed, isDismissKey } from "./dialog";

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
