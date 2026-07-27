/**
 * THE ACKNOWLEDGMENT BYPASS REGRESSION SUITE.
 *
 * The verifier's finding: three process routes reached the backend with ZERO sites reviewed.
 * These tests are the ones that must FAIL if any route regains a bypass:
 *
 *   - "refuses EVERY process route while a detection is unreviewed" — the gate itself, exercised
 *     through the four named routes (run / rerun-live / recompute / dialog-process). They all
 *     call `authorizeRun`, so one refusal covers all four by construction.
 *   - "mints an authorized selection ONLY when the gate is clear" — the branded selection cannot
 *     exist without a clear gate, and `runAutomation` accepts nothing else (compile-time half of
 *     the same guarantee; see api/client.ts's signature).
 *   - "names the reason instead of leaving a dead button" — the disabled reason the operator sees.
 *
 * The COMPILE-time half is not expressible as a runtime assertion: `AuthorizedRunSelection`'s
 * brand is a module-private unique symbol, so a route that skips the gate fails `pnpm typecheck`
 * rather than this file. Both halves are required; neither alone closes the door.
 */
import { describe, expect, it } from "vitest";
import {
  authorizeRun,
  canRun,
  refusalSentence,
  reviewProgressText,
  runBlockers,
  unreviewedNotice,
  type RunGateInput,
} from "./runGate";
import {
  initialSelection,
  withOffsetInput,
  withReviewed,
  withSites,
  withVariant,
  type LibrarySelection,
} from "./librarySelection";

/** Two marked sites, both caps chosen, NEITHER reviewed — the exact state the bypassing routes
 *  used to process from. */
function chosenButUnreviewed(): LibrarySelection {
  const base = initialSelection({
    suggestedModel: "neodent-gm",
    suggestedConstruction: "dess/neodent-gm-scanbody.stl",
    jaw: "lower",
    sites: [{ tooth: 3 }, { tooth: 29 }],
  });
  return withVariant(withVariant(base, 0, "6020"), 1, "7030");
}

function reviewed(selection: LibrarySelection): LibrarySelection {
  return selection.sites.reduce((acc, _site, i) => withReviewed(acc, i, true), selection);
}

function gate(selection: LibrarySelection, duplicateTeeth: readonly number[] = []): RunGateInput {
  return { selection, duplicateTeeth };
}

/**
 * The four process routes, as the app wires them. Every one of them ends in `authorizeRun`:
 *   run            — step 4's primary "Run automation"        (App.handleRunAutomation(false))
 *   rerun-live     — step 4's "⟳ rerun live"                  (App.handleRunAutomation(true))
 *   recompute      — Confirm All / the stale banner           (App.handleRecompute)
 *   dialog-process — the library-selection dialog's "OK · Process"        (App.handleProcessFromDialog)
 * Adding a route means adding it here; a route that does NOT authorize cannot compile a run
 * request at all (see the module doc).
 */
const PROCESS_ROUTES = ["run", "rerun-live", "recompute", "dialog-process"] as const;

describe("run gate — the acknowledgment cannot be bypassed", () => {
  it("refuses EVERY process route while a detection is unreviewed", () => {
    const input = gate(chosenButUnreviewed());
    for (const route of PROCESS_ROUTES) {
      const auth = authorizeRun(input);
      expect(auth.ok, `route "${route}" processed with unreviewed sites`).toBe(false);
      expect(canRun(input), `route "${route}" reported a clear gate`).toBe(false);
    }
  });

  it("still refuses when only ONE of several sites is unreviewed", () => {
    const partly = withReviewed(chosenButUnreviewed(), 0, true);
    expect(canRun(gate(partly))).toBe(false);
    expect(runBlockers(gate(partly))).toContain("a review of site 2");
  });

  it("mints an authorized selection ONLY when the gate is clear", () => {
    const auth = authorizeRun(gate(reviewed(chosenButUnreviewed())));
    expect(auth.ok).toBe(true);
    if (!auth.ok) return;
    expect(auth.selection.model).toBe("neodent-gm");
    expect(auth.selection.constructionPathId).toBe("dess/neodent-gm-scanbody.stl");
    expect(auth.selection.jaw).toBe("lower");
    expect(auth.selection.gingivalOffsetMm).toBe(0.2);
  });

  it("names the reason instead of leaving a dead button", () => {
    const refusal = authorizeRun(gate(chosenButUnreviewed()));
    expect(refusal.ok).toBe(false);
    if (refusal.ok) return;
    expect(refusal.reason).toContain("a review of sites 1, 2");
    expect(refusal.reason).toContain("Verify & process");
    expect(unreviewedNotice(chosenButUnreviewed())).toBe("2 sites not yet reviewed");
  });

  it("counts one unreviewed site in the singular", () => {
    const one = initialSelection({
      suggestedModel: "neodent-gm",
      suggestedConstruction: "dess/x.stl",
      jaw: "upper",
      sites: [{ tooth: 3 }],
    });
    expect(unreviewedNotice(withVariant(one, 0, "6020"))).toBe("1 site not yet reviewed");
  });

  it("re-blocks a route once a REVIEWED selection changes under it", () => {
    // Changing the cap on site 2 drops that site's review (librarySelection's rule) — the gate
    // must follow it back down, or an operator could review 6020 and process 7030.
    const ready = reviewed(chosenButUnreviewed());
    expect(canRun(gate(ready))).toBe(true);
    const switched = withVariant(ready, 1, "6020");
    expect(canRun(gate(switched))).toBe(false);
    expect(unreviewedNotice(switched)).toBe("1 site not yet reviewed");
  });

  it("re-blocks EVERY route once a step-3 row is put back on “auto”", () => {
    // The bypass this closes (verifier, 2026-07-25): the operator reviewed the site, then
    // returned to step 3 and cleared that row's cap declaration. The selection kept claiming a
    // reviewed 7030 while the run submitted NO declaration, so the backend auto-identified a
    // part nobody reviewed — the acknowledgment reading "1 of 1 reviewed" the whole time.
    const ready = reviewed(chosenButUnreviewed());
    expect(canRun(gate(ready))).toBe(true);
    const cleared = withSites(ready, [
      { tooth: 3, declaredVariant: "6020" },
      { tooth: 29, declaredVariant: "" },
    ]);
    for (const route of PROCESS_ROUTES) {
      expect(canRun(gate(cleared)), `route "${route}" processed an undeclared row`).toBe(false);
    }
    expect(runBlockers(gate(cleared))).toContain("the cap variant for site 2 (tooth 29)");
    expect(unreviewedNotice(cleared)).toBe("1 site not yet reviewed");
    expect(authorizeRun(gate(cleared)).ok).toBe(false);
  });

  it("does NOT re-demand a review for a plain recompute (marks changed, product did not)", () => {
    // The recompute route re-seats the SAME reviewed product with edited marks — the gate is
    // about the product choice, not about re-running the geometry.
    const ready = reviewed(chosenButUnreviewed());
    expect(canRun(gate(ready))).toBe(true);
    expect(canRun(gate(ready))).toBe(true);
  });

  it("blocks on the step-3 problems the selection cannot see", () => {
    const ready = reviewed(chosenButUnreviewed());
    const dupes = runBlockers(gate(ready, [3]));
    expect(dupes[0]).toContain("one tooth number per site");
    expect(canRun(gate(ready, [3]))).toBe(false);
  });

  it("blocks on the required selections, before any review is even possible", () => {
    const empty = initialSelection({
      suggestedModel: null,
      suggestedConstruction: null,
      jaw: "upper",
      sites: [{ tooth: 3 }],
    });
    const blockers = runBlockers(gate(empty));
    expect(blockers).toContain("the implant system");
    expect(blockers).toContain("the construction part");
    expect(blockers).toContain("the cap variant for site 1 (tooth 3)");
    expect(blockers).toContain("a review of site 1");
  });

  it("blocks a case with no marked sites at all", () => {
    const none = initialSelection({
      suggestedModel: "neodent-gm",
      suggestedConstruction: "dess/x.stl",
      jaw: "upper",
      sites: [],
    });
    expect(runBlockers(gate(none))).toContain("at least one marked site");
  });

  it("blocks an out-of-range gingival relief (the request is judged, never rescaled)", () => {
    const bad = withOffsetInput(reviewed(chosenButUnreviewed()), "3");
    expect(runBlockers(gate(bad))).toContain("a valid gingival profile offset");
  });

  it("reports review progress while the operator works through the sites", () => {
    const selection = chosenButUnreviewed();
    expect(reviewProgressText(selection)).toBe("0 of 2 sites reviewed");
    expect(reviewProgressText(withReviewed(selection, 0, true))).toBe("1 of 2 sites reviewed");
    expect(reviewProgressText(reviewed(selection))).toBe("2 of 2 sites reviewed");
  });

  it("says nothing at all when the gate is clear", () => {
    const ready = reviewed(chosenButUnreviewed());
    expect(runBlockers(gate(ready))).toEqual([]);
    expect(refusalSentence(gate(ready))).toBe("");
    expect(unreviewedNotice(ready)).toBeNull();
  });
});
