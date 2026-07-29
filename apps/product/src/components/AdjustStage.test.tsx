/**
 * THE ADJUST STAGE'S SURFACE (slice 6), statically rendered per the repo convention
 * (the panes arrive as a prop, so WebGL never enters a test). The pure rules are
 * pinned in domain/adjust.test.ts; what belongs here is WHICH WORDS RENDER WHERE —
 * and above all which TONE, because the two things this stage can get wrong are
 * showing a refusal as if nothing happened and showing a pass as if something failed.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { AdjustStageView } from "./AdjustStage";
import { newPairDraft, withPick, type AdjustQueueEntry } from "../domain/adjust";
import type { AdjustOutcomeView } from "../api/client";

const ACTION =
  "The cap's ROTATION could not be verified — visually check the coded features " +
  "in view 1 (top-down) before accepting.";

const FLAGGED: AdjustQueueEntry = {
  tooth: 13,
  status: "flagged",
  flagged: true,
  optional: false,
  declaredVariant: "5020",
  reasons: [ACTION],
};

const CLEAN: AdjustQueueEntry = {
  tooth: 4,
  status: "ready",
  flagged: false,
  optional: true,
  declaredVariant: "5020",
  reasons: [],
};

function view(overrides: Partial<Parameters<typeof AdjustStageView>[0]> = {}) {
  return renderToStaticMarkup(
    <AdjustStageView
      entries={[FLAGGED, CLEAN]}
      activeTooth={13}
      onSelectSite={() => undefined}
      tool="rotation"
      onSelectTool={() => undefined}
      phase="idle"
      refusal={null}
      pass={null}
      lastOutcome={null}
      cumulativeDeg={null}
      onRotate={() => undefined}
      onResetRotation={() => undefined}
      diameterMm={0.3}
      onChangeDiameter={() => undefined}
      onBestFit={() => undefined}
      trenchArmed={false}
      onArmTrench={() => undefined}
      drafts={[]}
      onStartPair={() => undefined}
      onRemovePair={() => undefined}
      onApplyPairs={() => undefined}
      panes={<div data-role="stub-panes" />}
      activeStatus="flagged"
      {...overrides}
    />,
  );
}

describe("the queue", () => {
  it("shows the flagged site with the GATE'S OWN reason, verbatim", () => {
    const html = view();
    expect(html).toContain('data-role="queue-site"');
    // the words as the gate wrote them (the apostrophe arrives HTML-escaped)
    expect(html).toContain(
      "ROTATION could not be verified — visually check the coded features",
    );
  });

  it("shows clean sites as visibly optional rather than hiding them", () => {
    expect(view()).toContain("passed its gates — reworking is optional");
  });

  it("a flagged site the gate gave no words for still says it is flagged", () => {
    const html = view({
      entries: [{ ...FLAGGED, reasons: [] }],
    });
    expect(html).toContain("the gate recorded no action words");
  });

  it("with nothing aligned the queue says so instead of showing an empty list", () => {
    expect(view({ entries: [], activeTooth: null })).toContain(
      "there is nothing to rework here",
    );
  });
});

describe("the toolbox", () => {
  it("offers all four tools with one selected — the others one click away", () => {
    const html = view();
    for (const tool of ["fit-by-points", "best-fit", "rotation", "mark-trench"]) {
      expect(html).toContain(`data-tool="${tool}"`);
    }
    expect(html).toContain('data-tool="rotation" aria-selected="true"');
  });

  it("with no site selected it says why, instead of offering acts that would refuse", () => {
    const html = view({ activeTooth: null });
    expect(html).toContain('data-role="tool-blocked"');
    expect(html).not.toContain('data-role="rotation-step"');
  });

  it("the rotation dial offers gated steps and the reset, with the residual beside them", () => {
    const html = view();
    expect(html).toContain('data-step="-15"');
    expect(html).toContain('data-step="15"');
    expect(html).toContain("Reset to the certified pose");
    expect(html).toContain("coded-cutout residual not read yet");
  });

  it("the residual and the cumulative rotation are the SERVER'S numbers", () => {
    const html = view({
      cumulativeDeg: 6,
      lastOutcome: {
        applied: true,
        detail: "rotated +5.0°",
        clocking: { notch_shift_deg: -1.8 },
        pairs: [],
      } as unknown as AdjustOutcomeView,
    });
    expect(html).toContain("coded-cutout residual -1.8° · cumulative +6.0°");
  });

  it("best fit offers the dial, Measure only and Apply", () => {
    const html = view({ tool: "best-fit" });
    expect(html).toContain('data-role="diameter-input"');
    expect(html).toContain('data-role="best-fit-measure"');
    expect(html).toContain('data-role="best-fit-apply"');
  });

  it("mark trench arms one click, and says it is armed", () => {
    expect(view({ tool: "mark-trench", trenchArmed: true })).toContain(
      "Armed — click the trench on the scan",
    );
  });
});

describe("fit by points", () => {
  it("offers SPAN mode EXPLICITLY beside the single-point pair", () => {
    const html = view({ tool: "fit-by-points" });
    expect(html).toContain('data-role="start-point-pair"');
    expect(html).toContain('data-role="start-span-pair"');
    expect(html).toContain("Add a SPAN pair (both ends)");
  });

  it("prompts for exactly the next click", () => {
    const draft = withPick(newPairDraft("s1", true), "part", [1, 0, 1]);
    expect(view({ tool: "fit-by-points", drafts: [draft] })).toContain(
      "Click ONE END of that feature on the scan",
    );
  });

  it("lists each pair with its own removal", () => {
    const html = view({
      tool: "fit-by-points",
      drafts: [newPairDraft("p1", false), newPairDraft("s1", true)],
    });
    expect(html).toContain('data-pair="p1"');
    expect(html).toContain('data-pair="s1"');
    expect(html).toContain('data-span="true"');
  });

  it("Apply states what is missing rather than going quietly dead", () => {
    const html = view({ tool: "fit-by-points", drafts: [] });
    expect(html).toContain('aria-disabled="true"');
    expect(html).toContain("Place at least one complete pair");
  });

  it("Apply goes live once a pair is complete", () => {
    const complete = withPick(
      withPick(newPairDraft("p1", false), "part", [1, 0, 1]),
      "scan",
      [5, 5, 5],
    );
    const html = view({ tool: "fit-by-points", drafts: [complete] });
    expect(html).toContain("Apply the fit");
    expect(html).not.toContain("Place at least one complete pair");
  });
});

describe("what comes back", () => {
  it("a refusal renders VERBATIM, and says nothing changed", () => {
    const words =
      "ring-fixed stability excess 0.51mm exceeds the 0.35mm certification bound — " +
      "the rim cannot hold this rotation still";
    const html = view({ refusal: words });
    expect(html).toContain('data-role="tool-refusal"');
    expect(html).toContain("0.35mm certification bound");
    expect(html).toContain("the fit on screen is the one that passed the gates");
  });

  it("the already-optimal outcome renders as a PASS, never in the refusal's tone", () => {
    // client ask 2026-07-26 — the demo shipped this as a refusal once and had to
    // take it back; the tone IS the requirement
    const html = view({
      pass: {
        message: "the certified pose is already the best fit within this matching diameter",
        matchingDiameterMm: 0.3,
        suggestedDiameterMm: 0.6,
        canWiden: true,
      },
    });
    expect(html).toContain('data-role="best-fit-pass"');
    expect(html).toContain("Nothing to correct.");
    expect(html).not.toContain('data-role="tool-refusal"');
    expect(html).toContain("Widen to Ø0.60 mm and look again");
  });

  it("at the ceiling the pass offers no widen — a widen that re-runs the same search is a loop", () => {
    const html = view({
      pass: {
        message: "…and this is the widest matching band the tool searches",
        matchingDiameterMm: 2,
        suggestedDiameterMm: 2,
        canWiden: false,
      },
    });
    expect(html).toContain('data-role="best-fit-pass"');
    expect(html).not.toContain('data-role="widen-search"');
  });

  it("an applied fit lists every OBSERVATION — a span shows both of its readings", () => {
    const html = view({
      lastOutcome: {
        applied: true,
        detail: "fit by 1 point pair(s) → 2 observation(s)",
        clocking: null,
        pairs: [
          { feature_id: "point-1", observation: "midpoint", residual_mm: 0.041 },
          { feature_id: "point-1", observation: "direction", residual_mm: 0.112 },
        ],
      } as unknown as AdjustOutcomeView,
    });
    expect(html).toContain("point-1 · span midpoint — misses by 0.041 mm");
    expect(html).toContain("point-1 · span direction — misses by 0.112 mm");
  });

  it("an applied tool tells the operator their confirmation no longer describes the site", () => {
    const html = view({
      activeStatus: "adjusted",
      lastOutcome: {
        applied: true,
        detail: "rotated +1.0°",
        clocking: null,
        pairs: [],
      } as unknown as AdjustOutcomeView,
    });
    expect(html).toContain('data-role="reconfirm-note"');
    expect(html).toContain("confirm it again over the panes before Deliver");
  });

  it("while a proposal is being judged the surface names the work", () => {
    const html = view({ phase: "working" });
    expect(html).toContain('data-role="tool-busy"');
    expect(html).toContain("the same gates that judged the automation");
  });
});
