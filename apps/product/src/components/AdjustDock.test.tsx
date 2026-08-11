/**
 * THE INSTRUMENT DOCK'S OWN MARKUP (§10-AN), statically rendered per the repo's
 * convention — `renderToStaticMarkup` in the node environment, no jsdom. Most of the
 * dock's BEHAVIOUR is already pinned through `AdjustStage.test.tsx` (which renders
 * `AdjustStageView`, which renders this component); what belongs here is the dock's
 * OWN structure the drawer never had — the glyph rail's order and tooltips, the
 * gauge/ring/slider/strip/map widgets, the "more room" toggle, and every place this
 * file deliberately diverges from the comp (no "rim reads" claim, no fixed "four",
 * no mock scatter formula).
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { AdjustDock, type AdjustDockProps } from "./AdjustDock";
import {
  newPairDraft,
  withPick,
  type AdjustQueueEntry,
  type UnverifiedClockNotice,
} from "../domain/adjust";
import type { AdjustOutcomeView, LandmarkView } from "../api/client";

const FLAGGED: AdjustQueueEntry = {
  tooth: 13,
  status: "flagged",
  flagged: true,
  optional: false,
  dropped: false,
  exceptionAcknowledged: false,
  evidenceCount: 0,
  receipts: [],
  declaredVariant: "5020",
  reasons: ["re-run the refinement at a matching diameter"],
};

function view(overrides: Partial<AdjustDockProps> = {}) {
  return renderToStaticMarkup(
    <AdjustDock
      tool="rotation"
      onSelectTool={() => undefined}
      active={FLAGGED}
      busy={false}
      cumulativeDeg={null}
      onRotate={() => undefined}
      onResetRotation={() => undefined}
      trenchArmed={false}
      onArmTrench={() => undefined}
      diameterMm={0.3}
      onChangeDiameter={() => undefined}
      onBestFit={() => undefined}
      pass={null}
      drafts={[]}
      pose={null}
      clock={null}
      onStartPair={() => undefined}
      onRemovePair={() => undefined}
      onRemovePoint={() => undefined}
      onReplacePair={() => undefined}
      onApplyPairs={() => undefined}
      onClearPairs={() => undefined}
      ghostsActive={false}
      autoMarkLandmarks={[]}
      autoMarkPhase="idle"
      autoMarkError={null}
      refusal={null}
      lastOutcome={null}
      activeStatus="flagged"
      onReconfirm={() => undefined}
      reconfirmSaving={false}
      reconfirmError={null}
      seatedPhase="ready"
      seatedPayloadPresent={true}
      receiptsCarried={false}
      onRePreview={() => undefined}
      rePreviewResult={null}
      rePreviewWorking={false}
      rePreviewError={null}
      onAcknowledgeException={() => undefined}
      acknowledgeSaving={false}
      acknowledgeError={null}
      onDrop={() => undefined}
      dropSaving={false}
      dropError={null}
      relief={null}
      dockTall={false}
      onToggleDockTall={() => undefined}
      cautionsOpen={false}
      onOpenCautions={() => undefined}
      onCloseCautions={() => undefined}
      {...overrides}
    />,
  );
}

describe("the rail — five glyph chips, the comp's own order (§10-AN)", () => {
  it("renders all five tools, the active one selected", () => {
    const html = view({ tool: "best-fit" });
    for (const tool of ["rotation", "mark-trench", "best-fit", "fit-by-points", "auto-mark"]) {
      expect(html).toContain(`data-tool="${tool}"`);
    }
    expect(html).toContain('data-tool="best-fit" aria-selected="true"');
  });

  it("orders the chips rotation, mark-trench, best-fit, fit-by-points, auto-mark", () => {
    const html = view();
    const positions = ["rotation", "mark-trench", "best-fit", "fit-by-points", "auto-mark"].map(
      (id) => html.indexOf(`data-tool="${id}"`),
    );
    expect(positions).toEqual([...positions].sort((a, b) => a - b));
  });

  it("carries the spec's own tooltips, with the amended clauses swapped out", () => {
    const html = view();
    expect(html).toMatch(/data-tool="rotation"[^>]*title="Rotation — Drag the handle/);
    expect(html).toMatch(/data-tool="mark-trench"[^>]*title="Mark trench — Click the coded trench/);
    // §10-AN amendment: never the withdrawn "rim reads" claim
    expect(html).not.toContain("what the scanned rim actually reads");
    expect(html).toMatch(/data-tool="best-fit"[^>]*title="Best fit[^"]*never a standing measurement/);
    // the comp's own unverified pair-count physics is dropped
    expect(html).not.toContain("the first four do the work");
    // the comp's fixed "four points" is dropped for the served count
    expect(html).not.toContain("proposes four points");
  });

  it("still opens on the rail before the acts — same DOM contract as the old drawer", () => {
    const html = view();
    expect(html.indexOf('data-role="tool-tabs"')).toBeLessThan(
      html.indexOf('data-role="drawer-acts"'),
    );
  });
});

describe("the header — title + live readout, honest absence with no served shift", () => {
  it("reads the rotation state with no served shift yet", () => {
    const html = view({ tool: "rotation" });
    expect(html).toContain('data-role="dock-tool-title"');
    expect(html).toContain("Rotation");
    expect(html).toMatch(/data-role="dock-tool-state"[^>]*>0° · the trench has not been read yet</);
  });

  it("reads the served shift once the last outcome carries one", () => {
    const html = view({
      tool: "rotation",
      lastOutcome: { applied: true, detail: "x", clocking: { notch_shift_deg: 4.2 }, pairs: [] } as unknown as AdjustOutcomeView,
    });
    expect(html).toContain("0° · 4.2° off the trench");
  });

  it("reads the best-fit dial's own value, with no invented rim comparison", () => {
    const html = view({ tool: "best-fit", diameterMm: 0.3 });
    expect(html).toContain("Ø0.30 mm");
    expect(html).not.toContain(" vs ");
    expect(html).not.toContain("rim reads");
  });

  it("adds the server's own suggestion once a best-fit pass carries one", () => {
    const html = view({
      tool: "best-fit",
      diameterMm: 0.3,
      pass: {
        message: "already the best fit",
        matchingDiameterMm: 0.3,
        suggestedDiameterMm: 0.6,
        canWiden: true,
      },
    });
    expect(html).toContain("Ø0.30 mm · server suggests Ø0.60 mm");
  });

  it("reads the pair count for fit-by-points, and the matched count for auto-mark", () => {
    expect(view({ tool: "fit-by-points", drafts: [] })).toContain("0 of 8 pairs placed");
    const landmarks: LandmarkView[] = [
      { id: "a", kind: "notch", point: [1, 0, 0], lever_arm_mm: 1, azimuth_deg: 0 },
    ];
    expect(
      view({ tool: "auto-mark", autoMarkLandmarks: landmarks, drafts: [] }),
    ).toContain("0 of 1 point matched");
  });

  it("says '—' when no site is selected", () => {
    expect(view({ active: null })).toMatch(/data-role="dock-tool-state"[^>]*>—</);
  });
});

describe("the 'more room' toggle — lifted to a prop (§10-AN slice C, the pane-grid coupling now wired one level up)", () => {
  it("renders the toggle, unpressed by default", () => {
    const html = view();
    expect(html).toContain('data-role="dock-more-room"');
    expect(html).toContain('aria-pressed="false"');
    expect(html).toContain("more room");
  });

  it("RETARGETED: reads `dockTall` from a prop, not local state — AdjustStageView owns it now", () => {
    // the pane grid needs the SAME value (comp-delta's paneGridStyle), so it can no
    // longer be private to this component; see AdjustDockProps' own note.
    const html = view({ dockTall: true });
    expect(html).toContain('aria-pressed="true"');
    expect(html).toContain("less room");
  });
});

describe("the pair-caution chip and its modal (§10-AN slice C, client 2026-08-06)", () => {
  const complete = withPick(
    withPick(newPairDraft("p1", false), "part", [4, 0, 0]),
    "scan",
    [4, 0, 0],
  );

  it("renders no chip with nothing to caution about", () => {
    const html = view({ tool: "fit-by-points", drafts: [] });
    expect(html).not.toContain('data-role="pair-caution-chip"');
  });

  it("renders the chip, counting the cautions, when one exists", () => {
    const html = view({ tool: "fit-by-points", drafts: [complete] });
    expect(html).toMatch(/data-role="pair-caution-chip"[^>]*>⚠ 1 caution</);
    // the modal itself stays closed until asked for
    expect(html).not.toContain('data-role="pair-cautions-dialog"');
  });

  it("opens on the `cautionsOpen` prop — the switch-confirm/reasons-dialog precedent — and lists the words verbatim", () => {
    const html = view({ tool: "fit-by-points", drafts: [complete], cautionsOpen: true });
    expect(html).toContain('data-role="pair-cautions-dialog"');
    expect(html).toContain('role="dialog"');
    expect(html).toContain("no agreement number");
  });
});

/**
 * THE UNVERIFIED CLOCK, FOLDED INTO THE SAME CHIP/DIALOG (§10-AN slice D, client
 * screenshots: at a short window the standing inline band — rendered by
 * AdjustStage.tsx, outside this dock's own max-height — pushed the page back into
 * scroll). RETARGETED from AdjustStage.test.tsx's "the unverified clock's
 * actionable surface" describe block, which pinned an inline `data-role=
 * "clock-unverified"` band; that band is gone, so every assertion here targets the
 * dialog rendered open via `cautionsOpen`, the same precedent `AdjustDockProps`'
 * own doc cites (switch-confirm / reasons-dialog: a static render pins a dialog
 * open through its own prop rather than a click).
 */
describe("the unverified clock, folded into the pair-caution dialog (§10-AN slice D)", () => {
  const complete = withPick(
    withPick(newPairDraft("p1", false), "part", [4, 0, 0]),
    "scan",
    [4, 0, 0],
  );

  // No apostrophes or quotes in this fixture, on purpose — renderToStaticMarkup
  // escapes them to HTML entities, and every other pin in this suite that checks a
  // rendered sentence verbatim avoids them for the same reason.
  const NOTICE: UnverifiedClockNotice = {
    facts: "The automatic reader could not verify this caps rotation on this scan.",
    act: "Auto-mark proposes rotation-defining landmarks toward a cross-checked fit.",
    armTool: "auto-mark",
  };

  it("renders no chip and no dialog content with no notice (the default)", () => {
    const html = view({ tool: "fit-by-points", drafts: [] });
    expect(html).not.toContain('data-role="pair-caution-chip"');
    expect(html).not.toContain('data-role="clock-caution"');
  });

  it("counts as one caution on its own", () => {
    const html = view({ clockNotice: NOTICE });
    expect(html).toMatch(/data-role="pair-caution-chip"[^>]*>⚠ 1 caution</);
  });

  it("sums with the pair cautions in the SAME chip, never a second one", () => {
    const html = view({ tool: "fit-by-points", drafts: [complete], clockNotice: NOTICE });
    expect(html).toMatch(/data-role="pair-caution-chip"[^>]*>⚠ 2 cautions</);
    // still one chip, not two
    expect(html.match(/data-role="pair-caution-chip"/g)).toHaveLength(1);
  });

  it("stays reachable whichever tool tab is open — the chip lives in the header, not the body", () => {
    for (const tool of ["fit-by-points", "best-fit", "rotation", "mark-trench", "auto-mark"] as const) {
      expect(view({ tool, clockNotice: NOTICE })).toMatch(
        /data-role="pair-caution-chip"[^>]*>⚠ 1 caution</,
      );
    }
  });

  it("lists the lead, the facts and the act verbatim in the dialog once opened, with the route to auto-mark", () => {
    const html = view({ clockNotice: NOTICE, cautionsOpen: true });
    expect(html).toContain('data-role="clock-caution"');
    expect(html).toContain('data-role="clock-caution-lead"');
    expect(html).toContain("auto-mark is the documented answer");
    expect(html).toContain('data-role="clock-caution-facts"');
    expect(html).toContain(NOTICE.facts);
    expect(html).toContain('data-role="clock-caution-act"');
    expect(html).toContain(NOTICE.act);
    expect(html).toContain('data-role="verify-rotation"');
    expect(html).toContain("Switch to auto-mark");
  });

  it("renders nothing about the clock when the dialog is closed — same precedent as the pair cautions", () => {
    const html = view({ clockNotice: NOTICE, cautionsOpen: false });
    expect(html).not.toContain('data-role="clock-caution"');
    expect(html).not.toContain(NOTICE.facts);
  });

  it("never claims the control will verify the rotation", () => {
    const html = view({ clockNotice: NOTICE, cautionsOpen: true });
    expect(html).not.toContain("will verify the rotation");
    expect(html).not.toContain("marks the rotation verified");
  });
});

describe("the tool-refusal modal — opens on a NEW refusal, no effect required (§10-AN slice C)", () => {
  it("renders no modal with no refusal", () => {
    const html = view({ refusal: null });
    expect(html).not.toContain('data-role="tool-refusal-dialog"');
  });

  it("a refusal opens the modal, alongside the persistent inline region", () => {
    const html = view({ refusal: "the rim cannot hold this rotation still" });
    expect(html).toContain('data-role="tool-refusal"'); // the inline record stays
    expect(html).toContain('data-role="tool-refusal-dialog"');
    expect(html).toContain('role="alertdialog"');
    expect(html).toContain("the rim cannot hold this rotation still");
  });

  // THE SPLIT TOOL'S POINTER, FOLDED IN (client live-testing 2026-08-09) — a
  // CLIENT-AUTHORED sentence appended to the recovery note, never a reworded server
  // sentence. Present in BOTH the persistent inline region and the modal, since
  // both render the same recovery note; absent unless a complete both-halves span
  // actually stands to click the button on.
  describe("the split-tool pointer, appended to the recovery note", () => {
    const bothSpan = () => {
      let d = newPairDraft("s1", true, true);
      d = withPick(d, "part", [2, 0, 1]);
      d = withPick(d, "part", [2, 1, 1]);
      d = withPick(d, "scan", [1, 0, 0]);
      return withPick(d, "scan", [2, 0, 0]);
    };

    it("says nothing extra with no splittable span among the drafts", () => {
      const html = view({
        refusal: "the axis span was refused",
        drafts: [],
      });
      expect(html).not.toContain('data-role="split-hint"');
    });

    it("appends the pointer, in BOTH the inline region and the modal, once a complete both-halves span stands", () => {
      const html = view({
        refusal: "the axis span was refused",
        drafts: [bothSpan()],
      });
      const hints = [...html.matchAll(/data-role="split-hint"/g)];
      expect(hints).toHaveLength(2);
      expect(html).toContain("Mark ends as two pairs");
      // the served sentence is untouched, verbatim
      expect(html).toContain("the axis span was refused");
    });
  });
});

describe("the single-observation caution (§10-AT A1)", () => {
  // the client's tooth-20 night: four one-pair fits looped −120°/+8°/+1°/−2°
  // with no convergence signal — the meter's honest silence read as "fine".
  // The sealed fact (cross_checked: false) now SAYS it in the drawer.
  it("renders when the last fit stood on one observation", () => {
    const html = view({
      tool: "fit-by-points",
      lastOutcome: { applied: true, detail: "x", cross_checked: false,
                     residual_rms_mm: null, pairs: [] } as unknown as AdjustOutcomeView,
    });
    expect(html).toContain('data-role="fit-single-observation-caution"');
    expect(html).toContain("ONE observation");
    expect(html).toContain("Add a second pair");
  });

  it("stays silent for a cross-checked fit, and for a row that predates the fact", () => {
    const checked = view({
      tool: "fit-by-points",
      lastOutcome: { applied: true, detail: "x", cross_checked: true,
                     residual_rms_mm: 0.12, pairs: [] } as unknown as AdjustOutcomeView,
    });
    expect(checked).not.toContain('data-role="fit-single-observation-caution"');
    const unknown = view({
      tool: "fit-by-points",
      lastOutcome: { applied: true, detail: "x", cross_checked: null,
                     residual_rms_mm: null, pairs: [] } as unknown as AdjustOutcomeView,
    });
    expect(unknown).not.toContain('data-role="fit-single-observation-caution"');
  });
});

describe("the rotation gauge widget", () => {
  it("renders the pending-angle input, the step chips and the reset", () => {
    const html = view({ tool: "rotation" });
    expect(html).toContain('data-role="rotation-gauge-input"');
    expect(html).toContain('data-role="rotation-step" data-step="-15"');
    expect(html).toContain('data-role="rotation-step" data-step="15"');
    expect(html).toContain("Reset to the certified pose");
  });

  it("draws no trench tick with no served shift", () => {
    const html = view({ tool: "rotation", lastOutcome: null });
    expect(html).not.toContain('data-role="rotation-trench-tick"');
  });

  it("draws the trench tick once a shift is served, and offers the snap", () => {
    const html = view({
      tool: "rotation",
      lastOutcome: { applied: true, detail: "x", clocking: { notch_shift_deg: 12 }, pairs: [] } as unknown as AdjustOutcomeView,
    });
    expect(html).toContain('data-role="rotation-trench-tick"');
    expect(html).toMatch(/data-role="rotation-snap"[^>]*>\s*snap to the trench/);
  });

  it("disables the snap and says so once the pending angle already reads on-trench", () => {
    const html = view({
      tool: "rotation",
      lastOutcome: { applied: true, detail: "x", clocking: { notch_shift_deg: 2 }, pairs: [] } as unknown as AdjustOutcomeView,
    });
    expect(html).toMatch(/data-role="rotation-snap"[^>]*disabled=""/);
    expect(html).toContain("already on the trench");
  });
});

describe("the mark-trench ring widget", () => {
  it("renders the ring, disabled with no served shift", () => {
    const html = view({ tool: "mark-trench", lastOutcome: null });
    expect(html).toMatch(/data-role="trench-ring"[^>]*disabled=""/);
    expect(html).toContain("nothing to click onto");
  });

  it("enables the ring once a shift is served and off the trench", () => {
    const html = view({
      tool: "mark-trench",
      lastOutcome: { applied: true, detail: "x", clocking: { notch_shift_deg: 20 }, pairs: [] } as unknown as AdjustOutcomeView,
    });
    expect(html).not.toMatch(/data-role="trench-ring"[^>]*disabled=""/);
    expect(html).toContain('data-role="trench-notch"');
  });

  it("keeps the EXISTING arm-and-click-on-the-scan act beside the ring", () => {
    const html = view({ tool: "mark-trench", trenchArmed: true });
    expect(html).toContain('data-role="arm-trench"');
    expect(html).toContain("Armed — click the trench on the scan");
  });
});

describe("the best-fit slider widget", () => {
  it("renders the slider, the scale labels, the nudge chips and both real acts", () => {
    const html = view({ tool: "best-fit" });
    expect(html).toContain('data-role="diameter-input"');
    expect(html).toContain('data-role="diameter-nudge-down"');
    expect(html).toContain('data-role="diameter-nudge-up"');
    expect(html).toContain('data-role="diameter-reset"');
    expect(html).toContain('data-role="best-fit-measure"');
    expect(html).toContain('data-role="best-fit-apply"');
    expect(html).toContain("Run refinement");
    expect(html).toContain('data-role="diameter-band"');
  });

  it("renders no flag with no served suggestion", () => {
    expect(view({ tool: "best-fit", pass: null })).not.toContain('data-role="best-fit-flag"');
  });

  it("renders the flag ONLY off the last response's own suggestion — never a rim claim", () => {
    const html = view({
      tool: "best-fit",
      pass: {
        message: "already the best fit",
        matchingDiameterMm: 0.3,
        suggestedDiameterMm: 0.6,
        canWiden: true,
      },
    });
    expect(html).toContain('data-role="best-fit-flag"');
    expect(html).toContain("server suggests Ø0.60");
    expect(html).not.toContain("rim reads");
  });
});

describe("fit by points — the eight-slot strip, our own pair model", () => {
  it("renders eight slots, slot 1 next and the rest locked", () => {
    const html = view({ tool: "fit-by-points", drafts: [] });
    expect(html).toContain('data-role="pair-slot-strip"');
    const items = [...html.matchAll(/data-role="pair-slot-strip-item" data-index="(\d)" data-state="(\w+)"/g)];
    expect(items).toHaveLength(8);
    expect(items[0]![2]).toBe("next");
    expect(items[1]![2]).toBe("locked");
  });

  it("marks a placed pair, and the fifth slot as a spare", () => {
    const complete = withPick(
      withPick(newPairDraft("p1", false), "part", [1, 0, 1]),
      "scan",
      [5, 5, 5],
    );
    const five = [complete, complete, complete, complete, complete];
    const html = view({ tool: "fit-by-points", drafts: five });
    expect(html).toMatch(/data-index="1" data-state="placed"/);
    expect(html).toMatch(/data-index="5" data-state="placed" data-spare="true"/);
  });

  it("keeps the three real start-pair buttons and the pair list beneath the strip", () => {
    const html = view({ tool: "fit-by-points" });
    expect(html).toContain('data-role="start-point-pair"');
    expect(html).toContain('data-role="start-span-pair"');
    expect(html).toContain('data-role="start-library-span-pair"');
    expect(html).toContain('data-role="pair-status"');
  });

  it("offers no 'place the next pair for me' button — no equivalent act exists (§10-AN)", () => {
    const html = view({ tool: "fit-by-points" });
    expect(html).not.toContain("place the next pair for me");
  });

  // THE SPLIT AFFORDANCE (client live-testing 2026-08-09: "there needs to be more
  // tooling added that solves the specific blocker" — the ±180° arbiter's own
  // remedy, "mark its two ends as two separate pairs", mechanized as a button).
  describe("the split affordance — only on a COMPLETE both-halves span row", () => {
    const bothSpan = (id: string) => {
      let d = newPairDraft(id, true, true);
      d = withPick(d, "part", [2, 0, 1]);
      d = withPick(d, "part", [2, 1, 1]);
      d = withPick(d, "scan", [1, 0, 0]);
      return withPick(d, "scan", [2, 0, 0]);
    };

    it("renders the button on a complete both-halves span", () => {
      const html = view({ tool: "fit-by-points", drafts: [bothSpan("s1")] });
      expect(html).toMatch(
        /data-role="split-pair" data-pair="s1"[^>]*>\s*Mark ends as two pairs\s*</,
      );
    });

    it("renders no button for an ordinary point pair", () => {
      const point = withPick(
        withPick(newPairDraft("p1", false), "part", [1, 0, 1]),
        "scan",
        [5, 5, 5],
      );
      const html = view({ tool: "fit-by-points", drafts: [point] });
      expect(html).not.toContain('data-role="split-pair"');
    });

    it("renders no button for a SCAN-ONLY span — splitSpanDraft returns null for it", () => {
      const scanOnly = withPick(
        withPick(
          withPick(newPairDraft("s2", true), "part", [5, 0, 0]),
          "scan",
          [1, 0, 0],
        ),
        "scan",
        [2, 0, 0],
      );
      const html = view({ tool: "fit-by-points", drafts: [scanOnly] });
      expect(html).not.toContain('data-role="split-pair"');
    });

    it("renders no button while the both-halves span is still incomplete", () => {
      let open = newPairDraft("s3", true, true);
      open = withPick(open, "part", [2, 0, 1]);
      const html = view({ tool: "fit-by-points", drafts: [open] });
      expect(html).not.toContain('data-role="split-pair"');
    });

    it("also renders on auto-mark's pair list — the same PairsList, the same rule", () => {
      const html = view({ tool: "auto-mark", drafts: [bothSpan("s4")] });
      expect(html).toContain('data-role="split-pair" data-pair="s4"');
    });
  });

  it("the scatter meter is absent with no served residual, present once one lands", () => {
    expect(view({ tool: "fit-by-points", lastOutcome: null })).not.toContain(
      'data-role="scatter-meter"',
    );
    const html = view({
      tool: "fit-by-points",
      lastOutcome: {
        applied: true,
        detail: "x",
        clocking: null,
        pairs: [],
        residual_rms_mm: 0.12,
      } as unknown as AdjustOutcomeView,
    });
    expect(html).toContain('data-role="scatter-meter"');
    expect(html).toContain("0.12 mm");
  });
});

describe("auto-mark — the proposal map, placed by served bearing", () => {
  const LANDMARKS: LandmarkView[] = [
    { id: "a", kind: "notch", point: [1, 0, 0], lever_arm_mm: 1.2, azimuth_deg: 0 },
    { id: "b", kind: "notch", point: [0, 1, 0], lever_arm_mm: 0.8, azimuth_deg: 180 },
  ];

  it("draws one dot per served landmark", () => {
    const html = view({
      tool: "auto-mark",
      autoMarkPhase: "ready",
      autoMarkLandmarks: LANDMARKS,
    });
    expect(html).toContain('data-role="auto-mark-map"');
    const dots = [...html.matchAll(/data-role="auto-mark-dot"/g)];
    expect(dots).toHaveLength(2);
  });

  it("keeps the existing summary/loading/error states and the pair list", () => {
    expect(
      view({ tool: "auto-mark", autoMarkPhase: "loading" }),
    ).toContain('data-role="auto-mark-loading"');
    expect(
      view({ tool: "auto-mark", autoMarkPhase: "error", autoMarkError: "nothing to adjust" }),
    ).toContain("nothing to adjust");
    expect(
      view({ tool: "auto-mark", autoMarkPhase: "ready", autoMarkLandmarks: LANDMARKS }),
    ).toContain('data-role="pair-status"');
  });
});

describe("the fixed footer — our own act set, unchanged words", () => {
  it("re-preview, accept-exception and drop render in the comp's own order", () => {
    const html = view();
    const acts = html.slice(html.indexOf('data-role="drawer-acts"'));
    const inActs = acts.slice(0, acts.indexOf('data-role="drop"'));
    expect(inActs.indexOf('data-role="re-preview"')).toBeLessThan(
      inActs.indexOf('data-role="accept-exception"'),
    );
    expect(inActs.indexOf('data-role="accept-exception"')).toBeLessThan(
      inActs.indexOf('data-role="drop-site"'),
    );
  });

  it("renders the relief control only when the container supplies one", () => {
    expect(view({ relief: null })).not.toContain('data-role="site-relief"');
    const html = view({
      relief: {
        siteValue: null,
        caseValue: 0.2,
        ceilingLine: null,
        runDone: true,
        saving: false,
        error: null,
        onApply: () => undefined,
      },
    });
    expect(html).toContain('data-role="site-relief"');
  });

  it("no acts render with no active site — nothing here promises an act on nothing", () => {
    const html = view({ active: null });
    expect(html).not.toContain('data-role="drawer-acts"');
    expect(html).toContain('data-role="tool-blocked"');
  });
});
