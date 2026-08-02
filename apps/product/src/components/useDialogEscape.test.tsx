// @vitest-environment jsdom
/**
 * useDialogEscape, NOW COVERED (§10-O.8, 2026-08-02) — see the hook's own header for
 * why this file did not exist before jsdom did. The four real call sites stay pinned
 * as static markup in their own test files (`role="dialog"`, `aria-modal="true"`,
 * closing on the backdrop); what belongs HERE is the listener itself, which none of
 * those files can dispatch a keydown against.
 *
 * No @testing-library: `createRoot` + `act` directly, exactly as `useDialogFocus.test.tsx`
 * does — the two hooks now share one small-DOM testing idiom in this package.
 */
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useDialogEscape } from "./useDialogEscape";

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

function Fixture({
  open,
  onClose,
  busy = false,
}: {
  readonly open: boolean;
  readonly onClose: () => void;
  readonly busy?: boolean;
}) {
  useDialogEscape(open, onClose, busy);
  return <div data-testid="surface">a dialog surface, standing in for any of the four</div>;
}

function mount(props: { open: boolean; onClose: () => void; busy?: boolean }) {
  root = createRoot(container);
  act(() => {
    root?.render(<Fixture {...props} />);
  });
}

function press(key: string): void {
  act(() => {
    window.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
  });
}

describe("Escape closes, and only Escape", () => {
  it("calls onClose exactly once on Escape", () => {
    const onClose = vi.fn();
    mount({ open: true, onClose });
    press("Escape");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("ignores Enter and Tab — neither belongs to the dialog", () => {
    const onClose = vi.fn();
    mount({ open: true, onClose });
    press("Enter");
    press("Tab");
    expect(onClose).not.toHaveBeenCalled();
  });

  it("does nothing while the dialog is not open — the listener is not even bound", () => {
    const onClose = vi.fn();
    mount({ open: false, onClose });
    press("Escape");
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe("busy refuses the dismissal — an act already with the server must not vanish under it", () => {
  it("does not call onClose while busy", () => {
    const onClose = vi.fn();
    mount({ open: true, onClose, busy: true });
    press("Escape");
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe("the capture-phase contract — a control inside the dialog cannot trap the operator", () => {
  it("stops a bubble-phase window listener from ever seeing the key", () => {
    const onClose = vi.fn();
    const bubbleListener = vi.fn();
    window.addEventListener("keydown", bubbleListener); // bubble phase, added by the test
    mount({ open: true, onClose });
    press("Escape");
    expect(onClose).toHaveBeenCalledTimes(1);
    // the hook's capture-phase listener calls stopPropagation() before onClose(),
    // so a plain bubble-phase listener registered on the same target (window) never runs
    expect(bubbleListener).not.toHaveBeenCalled();
    window.removeEventListener("keydown", bubbleListener);
  });
});
