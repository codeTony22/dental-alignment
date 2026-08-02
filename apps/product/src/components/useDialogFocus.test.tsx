// @vitest-environment jsdom
/**
 * useDialogFocus, DRIVEN AGAINST A FIXTURE, NOT A REAL STAGE (§10-O.8, 2026-08-02).
 *
 * The real dialogs cannot mount here: the arch dialog carries a WebGL `MainStage` and
 * the checkout calls `scrollIntoView` (CheckoutPage.tsx), neither of which jsdom
 * implements. What the hook DOES — initial focus, the Tab trap's wrap, the
 * restore-on-close — is a DOM behaviour independent of what is inside the dialog, so a
 * small fixture (an opener button + a conditionally-mounted `tabIndex={-1}` section
 * holding N buttons, shaped exactly like the app's own dialog sections) proves it. The
 * four real dialogs are wired to the hook and pinned only as STATIC MARKUP
 * (`tabindex="-1"`, `data-autofocus`) in their own `*.test.tsx` files — that split is
 * this repo's existing line between "does the behaviour work" and "is the surface
 * wired to it", not a new one drawn for this slice.
 *
 * No @testing-library: `createRoot` + `act` directly (react 18.3.1 exports `act`).
 * `IS_REACT_ACT_ENVIRONMENT` must be set for `act` to flush effects synchronously.
 */
import { act } from "react";
import { StrictMode, useRef } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useDialogFocus } from "./useDialogFocus";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
  true;

let container: HTMLDivElement;
let root: Root | null = null;

beforeEach(() => {
  container = document.createElement("div");
  document.body.appendChild(container);
});

afterEach(() => {
  if (root !== null) {
    act(() => root?.unmount());
    root = null;
  }
  container.remove();
});

function must<T>(el: T | null): T {
  if (el === null) throw new Error("fixture element missing — the test's own setup is wrong");
  return el;
}

interface FixtureProps {
  readonly open: boolean;
  readonly count?: number;
  readonly autofocusIndex?: number | null;
  readonly strict?: boolean;
}

/** A dialog fixture shaped like the app's real ones: an opener the test focuses
 *  itself (exactly as a click would, in a browser), then a conditionally-mounted
 *  section (`tabIndex={-1}`, matching every real dialog's own wiring) holding N
 *  focusable buttons. */
function Fixture({ open, count = 3, autofocusIndex = null, strict = false }: FixtureProps) {
  const dialogRef = useRef<HTMLDivElement | null>(null);
  useDialogFocus(open, dialogRef);
  const body = (
    <div>
      <button data-testid="opener">Open</button>
      {open && (
        <div ref={dialogRef} tabIndex={-1} data-testid="dialog">
          {Array.from({ length: count }, (_, i) => (
            <button
              key={i}
              data-testid={`control-${i}`}
              data-autofocus={i === autofocusIndex ? "" : undefined}
            >
              control {i}
            </button>
          ))}
        </div>
      )}
    </div>
  );
  return strict ? <StrictMode>{body}</StrictMode> : body;
}

function render(props: FixtureProps) {
  root = createRoot(container);
  act(() => {
    root?.render(<Fixture {...props} />);
  });
}

function rerender(props: FixtureProps) {
  act(() => {
    root?.render(<Fixture {...props} />);
  });
}

function opener(): HTMLButtonElement {
  return must(container.querySelector<HTMLButtonElement>('[data-testid="opener"]'));
}

function control(i: number): HTMLButtonElement {
  return must(container.querySelector<HTMLButtonElement>(`[data-testid="control-${i}"]`));
}

function dialogNode(): HTMLElement {
  return must(container.querySelector<HTMLElement>('[data-testid="dialog"]'));
}

/** Dispatches a Tab (or Shift-Tab) keydown on `el` and returns whether the browser's
 *  own default survived — `dispatchEvent` answers `false` exactly when a listener
 *  called `preventDefault()`, which is the trap's own signal that it took over. */
function tab(el: Element, shiftKey = false): boolean {
  const event = new KeyboardEvent("keydown", {
    key: "Tab",
    bubbles: true,
    cancelable: true,
    shiftKey,
  });
  return el.dispatchEvent(event);
}

describe("initial focus", () => {
  it("falls back to the first focusable element when nothing carries data-autofocus", () => {
    render({ open: false });
    opener().focus();
    rerender({ open: true });
    expect(document.activeElement).toBe(control(0));
  });

  it("lands on the data-autofocus element instead — even one that is not first in the DOM", () => {
    render({ open: false });
    opener().focus();
    rerender({ open: true, autofocusIndex: 2 });
    expect(document.activeElement).toBe(control(2));
  });
});

describe("the Tab trap", () => {
  it("Tab on the last control wraps to the first, taking over the browser's own default", () => {
    render({ open: true });
    control(2).focus();
    const notPrevented = tab(control(2));
    expect(notPrevented).toBe(false);
    expect(document.activeElement).toBe(control(0));
  });

  it("Shift-Tab on the first control wraps to the last", () => {
    render({ open: true });
    control(0).focus();
    const notPrevented = tab(control(0), true);
    expect(notPrevented).toBe(false);
    expect(document.activeElement).toBe(control(2));
  });

  it("a middle control's Tab is left alone — the browser's own order is already correct there", () => {
    render({ open: true });
    control(1).focus();
    const notPrevented = tab(control(1));
    expect(notPrevented).toBe(true); // NOT prevented — nextTrapIndex answered null
    expect(document.activeElement).toBe(control(1)); // the hook did not move it
  });

  it("zero focusables: Tab is prevented outright and focus stays on the dialog container", () => {
    render({ open: true, count: 0 });
    expect(document.activeElement).toBe(dialogNode()); // the ultimate fallback target
    const notPrevented = tab(dialogNode());
    expect(notPrevented).toBe(false);
    expect(document.activeElement).toBe(dialogNode());
  });
});

describe("restoring focus on close", () => {
  it("closing (open -> false) restores focus to whatever had it when the dialog opened", () => {
    render({ open: false });
    opener().focus();
    rerender({ open: true });
    expect(document.activeElement).toBe(control(0));
    rerender({ open: false });
    expect(document.activeElement).toBe(opener());
  });

  it("a disconnected opener does not throw, and focus falls through to the body", () => {
    // The real case: a paid checkout's onDetail+onClose land together (CheckoutPage.tsx),
    // and the same re-render that removes the dialog can remove the opener too.
    render({ open: false });
    opener().focus();
    rerender({ open: true });
    opener().remove();
    expect(() => rerender({ open: false })).not.toThrow();
    expect(document.activeElement).toBe(document.body);
  });
});

describe("StrictMode's double-invoked effects", () => {
  it("still land focus on the dialog's first control, and still restore exactly once on close", () => {
    render({ open: false, strict: true });
    opener().focus();
    // StrictMode runs this effect mount -> cleanup -> mount before this line returns;
    // if the phantom cleanup's restore and the second mount's re-capture were not
    // idempotent, focus would have drifted back to the opener instead of the dialog.
    rerender({ open: true, strict: true });
    expect(document.activeElement).toBe(control(0));
    rerender({ open: false, strict: true });
    expect(document.activeElement).toBe(opener());
  });

  it("leave exactly one keydown listener bound on the dialog node, never a leaked second", () => {
    render({ open: false, strict: true });
    const addSpy = vi.spyOn(HTMLElement.prototype, "addEventListener");
    const removeSpy = vi.spyOn(HTMLElement.prototype, "removeEventListener");
    opener().focus();
    rerender({ open: true, strict: true });
    const dialog: HTMLElement = dialogNode();
    const netKeydownListeners = () => {
      const added = addSpy.mock.calls.filter(
        (args, i) => addSpy.mock.instances[i] === dialog && args[0] === "keydown",
      ).length;
      const removed = removeSpy.mock.calls.filter(
        (args, i) => removeSpy.mock.instances[i] === dialog && args[0] === "keydown",
      ).length;
      return added - removed;
    };
    // If StrictMode's phantom pass's listener were never removed, this would read 2.
    expect(netKeydownListeners()).toBe(1);
    rerender({ open: false, strict: true });
    expect(netKeydownListeners()).toBe(0);
    addSpy.mockRestore();
    removeSpy.mockRestore();
  });
});
