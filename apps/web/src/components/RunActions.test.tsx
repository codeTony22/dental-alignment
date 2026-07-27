/**
 * THE QUICK PATH'S HALF OF THE ACKNOWLEDGMENT GATE.
 *
 * The verifier's finding was that step 4's buttons ignored the per-site review state. These are
 * the tests that must FAIL if any of them regains a bypass:
 *
 *   - "disables EVERY process button while a detection is unreviewed" — covers the PRIMARY
 *     "Run automation" and "⟳ rerun live" in one assertion over every rendered process button.
 *   - "says WHY, in the operator's own numbers" — the disabled reason is visible ("3 sites not
 *     yet reviewed"), never a silently dead button.
 *   - "points at the review route, and promotes it while reviews are outstanding".
 *
 * (renderToStaticMarkup, node environment — the same convention as every other component test
 * here. The recompute route is not a button: it is Confirm All firing handleRunAutomation, which
 * is gated at runtime by domain/runGate and at compile time by AuthorizedRunSelection.)
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { RunActions, type RunActionsProps } from "./RunActions";
import { initialSelection, withReviewed, withVariant } from "../domain/librarySelection";
import type { LibrarySelection } from "../domain/librarySelection";

function baseSelection(): LibrarySelection {
  const base = initialSelection({
    suggestedModel: "neodent-gm",
    suggestedConstruction: "dess/neodent-gm-scanbody.stl",
    jaw: "lower",
    sites: [{ tooth: 3 }, { tooth: 14 }, { tooth: 29 }],
  });
  return base.sites.reduce((acc, _s, i) => withVariant(acc, i, "6020"), base);
}

function reviewedSelection(): LibrarySelection {
  return baseSelection().sites.reduce((acc, _s, i) => withReviewed(acc, i, true), baseSelection());
}

function props(selection: LibrarySelection, overrides: Partial<RunActionsProps> = {}): RunActionsProps {
  return {
    selection,
    duplicateTeeth: [],
    undeclaredSiteNumbers: [],
    runBusy: false,
    cached: true,
    achievedOffset: null,
    onRun: () => {},
    onRerunLive: () => {},
    onOpenVerify: () => {},
    ...overrides,
  };
}

/** Every button that STARTS A RUN — by their labels, so a renamed-but-still-ungated button is
 *  caught by the label list going stale rather than by the assertion silently passing. */
const PROCESS_BUTTON_LABELS = ["Run automation", "⟳ rerun live"];

function buttonFor(html: string, label: string): string {
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = html.match(new RegExp(`<button[^>]*>${escaped}</button>`));
  return match?.[0] ?? "";
}

describe("RunActions — the quick path cannot bypass the acknowledgment", () => {
  it("disables EVERY process button while a detection is unreviewed", () => {
    const html = renderToStaticMarkup(<RunActions {...props(baseSelection())} />);
    for (const label of PROCESS_BUTTON_LABELS) {
      const button = buttonFor(html, label);
      expect(button, `"${label}" was not rendered — has it been renamed?`).not.toBe("");
      expect(button, `"${label}" processes with unreviewed sites`).toContain("disabled");
    }
  });

  it("still disables them when only ONE site is left unreviewed", () => {
    let selection = withReviewed(baseSelection(), 0, true);
    selection = withReviewed(selection, 1, true);
    const html = renderToStaticMarkup(<RunActions {...props(selection)} />);
    for (const label of PROCESS_BUTTON_LABELS) {
      expect(buttonFor(html, label)).toContain("disabled");
    }
    expect(html).toContain("1 site not yet reviewed");
  });

  it("says WHY, in the operator's own numbers, rather than leaving a dead button", () => {
    const html = renderToStaticMarkup(<RunActions {...props(baseSelection())} />);
    expect(html).toContain("3 sites not yet reviewed");
    expect(html).toContain("0 of 3 sites reviewed");
    expect(html).toContain("Still needed:");
    expect(html).toContain("Verify &amp; process");
  });

  it("promotes the review route while reviews are outstanding, and demotes it after", () => {
    const blocked = renderToStaticMarkup(<RunActions {...props(baseSelection())} />);
    expect(buttonFor(blocked, "⧉ Verify &amp; process")).toContain("button--primary");
    const ready = renderToStaticMarkup(<RunActions {...props(reviewedSelection())} />);
    expect(buttonFor(ready, "⧉ Verify &amp; process")).toContain("button--secondary");
  });

  it("ENABLES the process buttons once every detection is reviewed", () => {
    const html = renderToStaticMarkup(<RunActions {...props(reviewedSelection())} />);
    for (const label of PROCESS_BUTTON_LABELS) {
      expect(buttonFor(html, label)).not.toContain("disabled");
    }
    expect(html).toContain("3 of 3 sites reviewed");
    expect(html).not.toContain("not yet reviewed");
    expect(html).not.toContain("Still needed:");
  });

  it("keeps them down for the OTHER blockers too (duplicate teeth, missing selection)", () => {
    const dupes = renderToStaticMarkup(
      <RunActions {...props(reviewedSelection(), { duplicateTeeth: [3] })} />,
    );
    expect(buttonFor(dupes, "Run automation")).toContain("disabled");
    expect(dupes).toContain("used more than once");

    const noSystem = initialSelection({
      suggestedModel: null,
      suggestedConstruction: null,
      jaw: "upper",
      sites: [{ tooth: 3 }],
    });
    const html = renderToStaticMarkup(<RunActions {...props(noSystem)} />);
    expect(buttonFor(html, "Run automation")).toContain("disabled");
    expect(html).toContain("— no implant system —");
  });

  it("keeps them down while a run is already in flight", () => {
    const html = renderToStaticMarkup(<RunActions {...props(reviewedSelection(), { runBusy: true })} />);
    for (const label of PROCESS_BUTTON_LABELS) {
      expect(buttonFor(html, label)).toContain("disabled");
    }
  });

  it("offers ⟳ rerun live only for a cached result", () => {
    const live = renderToStaticMarkup(
      <RunActions {...props(reviewedSelection(), { cached: false })} />,
    );
    expect(live).not.toContain("⟳ rerun live");
  });

  it("states the requested relief, and the ACHIEVED one beside it once measured", () => {
    const plain = renderToStaticMarkup(<RunActions {...props(reviewedSelection())} />);
    expect(plain).toContain("0.20 mm gingival relief requested");
    expect(plain).not.toContain("achieved");

    const measured = renderToStaticMarkup(
      <RunActions
        {...props(reviewedSelection(), {
          achievedOffset: {
            requestedMm: 0.2,
            medianMm: 0.14,
            minMm: 0.13,
            maxMm: 0.15,
            nSites: 3,
            method: null,
          },
        })}
      />,
    );
    expect(measured).toContain("0.20 mm gingival relief requested");
    expect(measured).toContain("0.14 mm achieved (median of 3 sites, 0.13–0.15) on the last run");
  });
});
