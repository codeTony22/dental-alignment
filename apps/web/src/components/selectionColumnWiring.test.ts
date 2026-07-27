/**
 * ONE SELECTION, TWO MOUNTS (client, 2026-07-26: "one cohesive flow"). SelectionColumn now
 * mounts both in the verify dialog AND on the Mark & declare stage, and both must route every
 * control through the SAME LibrarySelection transitions into the SAME onSelectionChange — two
 * hand-rolled wirings would be two chances for the workbench and the dialog to disagree about
 * what the lab chose. These pin the shared builder: each handler is the domain transition it
 * claims to be, applied to the ACTIVE site where the control is per-site.
 */
import { describe, expect, it } from "vitest";
import { selectionColumnHandlers } from "./selectionColumnWiring";
import { initialSelection, withActiveSite, withReviewed, withVariant } from "../domain/librarySelection";
import type { LibrarySelection } from "../domain/librarySelection";

function selection(): LibrarySelection {
  let s = initialSelection({
    suggestedModel: "neodent-gm",
    suggestedConstruction: "dess/neodent-gm-scanbody.stl",
    jaw: "lower",
    sites: [{ tooth: 3 }, { tooth: 29 }],
  });
  s = withVariant(s, 0, "6020");
  s = withReviewed(s, 0, true);
  return s;
}

function capture() {
  const calls: LibrarySelection[] = [];
  return {
    calls,
    onSelectionChange: (next: LibrarySelection) => {
      calls.push(next);
    },
  };
}

describe("selectionColumnHandlers — every control goes through the one selection state", () => {
  it("a variant card click declares for the ACTIVE site (and drops only that site's review)", () => {
    const spy = capture();
    const active = withActiveSite(selection(), 1); // the stepper/tooth chart moved to site 2
    selectionColumnHandlers(active, spy.onSelectionChange).onSelectVariant("7030");
    expect(spy.calls).toHaveLength(1);
    const next = spy.calls[0]!;
    expect(next.sites[1]?.variantId).toBe("7030");
    expect(next.sites[1]?.reviewed).toBe(false);
    // site 1's declaration and review are untouched — the change was scoped to the active site
    expect(next.sites[0]?.variantId).toBe("6020");
    expect(next.sites[0]?.reviewed).toBe(true);
  });

  it("a system click switches the model and clears every declared variant with its review", () => {
    const spy = capture();
    selectionColumnHandlers(selection(), spy.onSelectionChange).onSelectModel("zimmer-4.5");
    const next = spy.calls[0]!;
    expect(next.model).toBe("zimmer-4.5");
    expect(next.sites.every((s) => s.variantId === null && !s.reviewed)).toBe(true);
  });

  it("the construction dropdown maps the empty prompt to null and clears the reviews", () => {
    const spy = capture();
    const handlers = selectionColumnHandlers(selection(), spy.onSelectionChange);
    handlers.onSelectConstruction("");
    expect(spy.calls[0]?.constructionPathId).toBeNull();
    handlers.onSelectConstruction("atlantis/zimmer-4.5-scanbody.stl");
    expect(spy.calls[1]?.constructionPathId).toBe("atlantis/zimmer-4.5-scanbody.stl");
    expect(spy.calls[1]?.sites[0]?.reviewed).toBe(false);
  });

  it("jaw and offset go through their own transitions", () => {
    const spy = capture();
    const handlers = selectionColumnHandlers(selection(), spy.onSelectionChange);
    handlers.onSelectJaw("upper");
    expect(spy.calls[0]?.jaw).toBe("upper");
    handlers.onChangeOffset("0.35");
    expect(spy.calls[1]?.gingivalOffsetMm).toBe(0.35);
    expect(spy.calls[1]?.gingivalOffsetInput).toBe("0.35");
  });
});
