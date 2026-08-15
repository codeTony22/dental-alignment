/**
 * THE ADJUST STAGE'S SURFACE (slice 6), statically rendered per the repo convention
 * (the panes arrive as a prop, so WebGL never enters a test). The pure rules are
 * pinned in domain/adjust.test.ts; what belongs here is WHICH WORDS RENDER WHERE —
 * and above all which TONE, because the two things this stage can get wrong are
 * showing a refusal as if nothing happened and showing a pass as if something failed.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { AdjustStageView, pairMarkers } from "./AdjustStage";
import { WorkspaceInsight } from "./WorkspaceInsight";
import {
  autoMarkDrafts,
  newPairDraft,
  withPick,
  type AdjustQueueEntry,
  type UnverifiedClockNotice,
} from "../domain/adjust";
import type { AdjustOutcomeView, LandmarkView } from "../api/client";
import { rePreviewView } from "../testing/fixtures";

const ACTION =
  "The cap's ROTATION could not be verified — visually check the coded features " +
  "in view 1 (top-down) before accepting.";

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
  reasons: [ACTION],
};

const CLEAN: AdjustQueueEntry = {
  tooth: 4,
  status: "ready",
  flagged: false,
  optional: true,
  dropped: false,
  exceptionAcknowledged: false,
      evidenceCount: 0,
      receipts: [],
  declaredVariant: "5020",
  reasons: [],
};

const DROPPED: AdjustQueueEntry = { ...FLAGGED, dropped: true };

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
      onRemovePoint={() => undefined}
      onApplyPairs={() => undefined}
      panes={<div data-role="stub-panes" />}
      activeStatus="flagged"
      {...overrides}
    />,
  );
}

describe("accepting a flagged exception, in advance (client 2026-08-02)", () => {
  const FLAGGED = {
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
  } as const;

  it("offers the amber act on a flagged active site, in the acts row's middle", () => {
    const html = view({ entries: [FLAGGED], activeTooth: 13 });
    const acts = html.slice(html.indexOf('data-role="drawer-acts"'));
    const inActs = acts.slice(0, acts.indexOf('data-role="drop"'));
    expect(inActs).toContain('data-role="accept-exception"');
    // comp order: re-read, accept, drop
    expect(inActs.indexOf('data-role="re-preview"')).toBeLessThan(
      inActs.indexOf('data-role="accept-exception"'),
    );
    expect(inActs.indexOf('data-role="accept-exception"')).toBeLessThan(
      inActs.indexOf('data-role="drop-site"'),
    );
  });

  it("offers nothing on a clean site, and nothing on a dropped one", () => {
    const clean = view({ entries: [{ ...FLAGGED, status: "ready", flagged: false, optional: true }], activeTooth: 13 });
    expect(clean).not.toContain('data-role="accept-exception"');
    const dropped = view({ entries: [{ ...FLAGGED, dropped: true }], activeTooth: 13 });
    expect(dropped).not.toContain('data-role="accept-exception"');
  });

  it("a standing draft renders pressed, offers the withdrawal, and marks the queue row", () => {
    const html = view({
      entries: [{ ...FLAGGED, exceptionAcknowledged: true }],
      activeTooth: 13,
    });
    expect(html).toMatch(/data-role="accept-exception"[^>]*aria-pressed="true"/);
    expect(html).toContain("withdraw");
    expect(html).toContain('data-role="queue-exception"');
    expect(html).toContain("Deliver&#x27;s confirmation signs it");
  });

  it("never claims the draft SIGNS anything — the words say what does", () => {
    const html = view({ entries: [FLAGGED], activeTooth: 13 });
    expect(html).not.toContain("will sign");
    expect(html).toMatch(/data-role="accept-exception"[^>]*title="[^"]*confirmation there is what signs/);
  });

  it("a refusal renders the BFF's words verbatim", () => {
    const html = view({
      entries: [FLAGGED],
      activeTooth: 13,
      acknowledgeError: "this site's verdict asks no acknowledgment — nothing to accept",
    });
    expect(html).toContain('data-role="acknowledge-error"');
    expect(html).toContain("asks no acknowledgment");
  });
});

describe("the tool panel wears the comp's own shape (read directly 2026-08-02)", () => {
  /* The comp opens straight on its tabs and closes on one row of site acts. The
     scrolling complaint that once pushed Drop into a head row is answered upstream
     now — §10-V.3 made the drawer take its content before the panes grow — so the
     foot is as reachable as the head was, and the arrangement can be the comp's. */
  it("gathers the site acts in ONE row at the panel's foot, after the tool body", () => {
    const html = view();
    expect(html).not.toContain('data-role="drawer-head"');
    const acts = html.slice(html.indexOf('data-role="drawer-acts"'));
    const inActs = acts.slice(0, acts.indexOf('data-role="drop"'));
    expect(inActs).toContain('data-role="re-preview"');
    expect(inActs).toContain('data-role="drop-site"');
    // after the tabs, not above them
    expect(html.indexOf('data-role="tool-tabs"')).toBeLessThan(
      html.indexOf('data-role="drawer-acts"'),
    );
  });

  it("keeps the drop's consequence attached to the control that causes it", () => {
    // the words are not lost — a consequential act still explains itself
    expect(view()).toMatch(/data-role="drop-site"[^>]*title="[^"]*release and the bill/);
  });

  it("an UNdropped site sheds the note that only restated its own button", () => {
    expect(view()).not.toContain('data-role="drop-note"');
  });
});

describe("the drawer head is one row, not a stack (client 2026-08-02)", () => {
  /* "Also on the tooling part" — the drawer opened with a heading row, then a
     re-read row, then the tabs: three bands before any tool. The heading and the
     re-read act now share one head row; the clock notice, when present, keeps its
     own full-width line below (it is a paragraph, not a control). */
  it("opens on its tabs — no heading the tabs already say", () => {
    const html = view();
    expect(html).not.toContain("Tools — tooth");
    // the tabs are the panel's first control: nothing but the (conditional) clock
    // notice may precede them
    const panel = html.slice(html.indexOf('data-role="adjust-toolbox"'));
    expect(panel.indexOf('data-role="tool-tabs"')).toBeLessThan(
      panel.indexOf('data-role="re-preview"'),
    );
  });
});

describe("the queue", () => {
  it("shows the flagged site with a COUNT of the gate's reasons, not the words", () => {
    const html = view();
    expect(html).toContain('data-role="queue-site"');
    // Retargeted 2026-07-29: five lines of amber per flagged site pushed the queue past
    // its own card, so the ROW keeps the fact and a count, while the gate's words move
    // to the dialog below. The row must NOT carry them any more.
    expect(html).toContain('data-role="queue-flag"');
    expect(html).toContain("flagged — 1 reason");
    expect(html).not.toContain(
      "ROTATION could not be verified — visually check the coded features",
    );
    // ...and the way to read them is on screen, as a SIBLING of the row button
    expect(html).toContain('data-role="queue-why"');
  });

  it("keeps the reasons dialog SHUT unless a tooth was actually asked for", () => {
    // The guard was `reasonsFor !== null`, which an omitted prop (undefined) sailed
    // straight through — opening a dialog headed "Tooth  — why the run flagged it".
    expect(view()).not.toContain('data-role="reasons-dialog"');
  });

  it("opens the dialog on the asked-for tooth, with the gate's words VERBATIM", () => {
    const html = view({ reasonsFor: 13 });
    expect(html).toContain('data-role="reasons-dialog"');
    expect(html).toContain("Tooth 13 — why the run flagged it");
    expect(html).toContain(
      "ROTATION could not be verified — visually check the coded features",
    );
  });

  it("carries the focus wiring (§10-O.8): a focusable container, Close marked as the landing spot", () => {
    // renderToStaticMarkup runs no effects and commits no refs — this pins ONLY that
    // the markup CARRIES the wiring (`tabindex="-1"`, `data-autofocus`); the trap and
    // restore behaviour themselves are `useDialogFocus.test.tsx`'s job, against a real
    // jsdom fixture.
    const html = view({ reasonsFor: 13 });
    expect(html).toMatch(/data-role="reasons-dialog"[^>]*tabindex="-1"/);
    expect(html).toMatch(/data-role="reasons-close"[^>]*data-autofocus=""/);
  });

  it("says so plainly when a flagged site carries no words at all", () => {
    // A site can be flagged with nothing recorded; the dialog must not render empty.
    expect(view({ reasonsFor: 4 })).toContain(
      "Flagged by the run — the gate recorded no action words.",
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
  it("offers all five tools with one selected — the others one click away", () => {
    const html = view();
    for (const tool of [
      "fit-by-points",
      "best-fit",
      "rotation",
      "mark-trench",
      "auto-mark",
    ]) {
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

  it("says what the act left stale on the run's report, where the act happened", () => {
    // FINDING E's other half (review 2026-07-28): the operator meets these two numbers
    // again on Deliver's table, under their own signature. Learning it there for the
    // first time is learning it too late.
    const html = view({
      lastOutcome: {
        applied: true,
        detail: "rotated +5.0°",
        pairs: [],
        stale_metrics: ["rim_agreement_mm", "guidance"],
      } as unknown as AdjustOutcomeView,
    });
    expect(html).toContain('data-role="rework-note"');
    expect(html).toContain("the rim agreement and the gate verdict");
  });

  it("an outcome with nothing stale carries no such note", () => {
    const html = view({
      lastOutcome: {
        applied: true,
        detail: "restored the pipeline's certified pose",
        pairs: [],
        stale_metrics: [],
      } as unknown as AdjustOutcomeView,
    });
    expect(html).not.toContain('data-role="rework-note"');
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
    // RETARGETED (client live-testing 2026-08-06: "so much text"): the visible
    // label shrank to the tool's name; the wire's own casing ("the SCAN") no
    // longer appears on the button face — see the title-attribute test below.
    expect(html).toContain(">Span the scan<");
  });

  it("names the click-count breakdown in each button's TITLE, not its label " +
     "(client 2026-08-04, retargeted 2026-08-06)", () => {
    // The original defect: "add a span in both ends doesnt mark the library with 2
    // points (just one)". Correct behaviour — "both ends" meant both ends of the
    // feature on the SCAN — but no label said which half it spanned, so the
    // operator chose the wrong door. The live-testing pass then flagged the FIX
    // itself as part of "so much text": three buttons each carrying a full click
    // breakdown on their face. The breakdown is not deleted — it moved to `title`,
    // reachable on hover/focus — and the visible label is just the tool's name.
    const html = view({ tool: "fit-by-points" });
    expect(html).toContain(">Point pair<");
    expect(html).toContain(">Span the scan<");
    expect(html).toContain(">Span both<");
    expect(html).toMatch(
      /data-role="start-point-pair"[^>]*title="1 click on the library part, 1 on the scan\./,
    );
    expect(html).toMatch(
      /data-role="start-span-pair"[^>]*title="1 click on the library part, 2 on the scan\./,
    );
    expect(html).toMatch(
      /data-role="start-library-span-pair"[^>]*title="2 clicks on the library part, 2 on the scan\./,
    );
    // the visible labels carry no click-count any more — the whole point of the move
    expect(html).not.toContain("Point pair ·");
    expect(html).not.toContain("Span the SCAN ·");
    expect(html).not.toContain("Span BOTH ·");
    // the ambiguous words the original fix retired stay retired
    expect(html).not.toContain("(both ends)");
    expect(html).not.toContain("(both halves)");
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
    // RETARGETED (client live-testing 2026-08-06): the blocked control used to
    // CARRY its reason as visible text — "a big greyed placeholder". The reason is
    // not dropped: it rides `title` now, the same convention "Go to Deliver" uses
    // when it is blocked — and the visible label stays "Apply the fit" either way.
    const html = view({ tool: "fit-by-points", drafts: [] });
    expect(html).toContain('aria-disabled="true"');
    expect(html).toMatch(
      /data-role="apply-pairs"[^>]*title="Place at least one complete pair/,
    );
    expect(html).toMatch(/data-role="apply-pairs"[^>]*>\s*Apply the fit\s*</);
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

  it("a hand-built pair carries no server-side source label", () => {
    // fit-by-points passes no `sourceLabelFor` to PairsList — a pair the operator
    // started by hand has no landmark identity to show
    const html = view({
      tool: "fit-by-points",
      drafts: [newPairDraft("p1", false)],
    });
    expect(html).not.toContain('data-role="pair-source"');
  });
});

describe("auto-mark — the software proposes the part half (client 2026-07-29)", () => {
  const LANDMARKS: LandmarkView[] = [
    { id: "notch-a", kind: "notch", point: [1.5, 0, 2], lever_arm_mm: 1.5,
      azimuth_deg: 0 },
    { id: "notch-b", kind: "notch", point: [0, 0.9, 2], lever_arm_mm: 0.9,
      azimuth_deg: 90 },
  ];

  it("says it is reading the proposal while the request is in flight", () => {
    const html = view({ tool: "auto-mark", autoMarkPhase: "loading" });
    expect(html).toContain('data-role="auto-mark-loading"');
  });

  it("a refusal from the landmarks read renders VERBATIM, like every other refusal", () => {
    const html = view({
      tool: "auto-mark",
      autoMarkPhase: "error",
      autoMarkError: "tooth 4 has no shipped pose in this run — nothing to adjust",
    });
    expect(html).toContain('data-role="auto-mark-error"');
    expect(html).toContain("nothing to adjust");
  });

  it("the ready state numbers the proposal and promises the matching order", () => {
    const html = view({
      tool: "auto-mark",
      autoMarkPhase: "ready",
      autoMarkLandmarks: LANDMARKS,
      drafts: autoMarkDrafts(LANDMARKS),
    });
    expect(html).toContain('data-role="auto-mark-summary"');
    expect(html).toContain("2 landmarks proposed");
    expect(html).toContain("best lever arm first");
    // RETARGETED (client live-testing 2026-08-06): the standalone `pair-prompt`
    // paragraph above the pair list retired into `PairsList`'s own ONE status
    // line (`data-role="pair-status"`, `pairStatusLine`) — same words, one home.
    // The PART half is already filled server-side, so the line asks for the SCAN
    // half of the first (open) landmark.
    expect(html).toContain('data-role="pair-status"');
    expect(html).toContain("Click the same spot on the SCAN");
  });

  it("a part with nothing to propose says so rather than showing an empty list", () => {
    const html = view({
      tool: "auto-mark",
      autoMarkPhase: "ready",
      autoMarkLandmarks: [],
      drafts: [],
    });
    expect(html).toContain("no rotation-defining landmarks to propose");
    // RETARGETED: with nothing proposed there is no OPEN draft to name a next
    // click for, so the status line falls back to the count sentence, never the
    // scan-half prompt that only makes sense once a landmark exists to match.
    expect(html).not.toContain("Click the same spot on the SCAN");
  });

  it("never offers the manual start-pair buttons — the pairs are the server's proposal", () => {
    const html = view({
      tool: "auto-mark",
      autoMarkPhase: "ready",
      autoMarkLandmarks: LANDMARKS,
      drafts: autoMarkDrafts(LANDMARKS),
    });
    expect(html).not.toContain('data-role="start-point-pair"');
    expect(html).not.toContain('data-role="start-span-pair"');
  });

  it("each row names WHICH landmark seeded it — kind and lever arm", () => {
    const html = view({
      tool: "auto-mark",
      autoMarkPhase: "ready",
      autoMarkLandmarks: LANDMARKS,
      drafts: autoMarkDrafts(LANDMARKS),
    });
    expect(html).toContain('data-role="pair-source"');
    expect(html).toContain("notch — lever arm 1.50mm");
    expect(html).toContain("notch — lever arm 0.90mm");
  });

  it("reuses the SAME pair-list and apply control fit-by-points renders", () => {
    // structural check: no second Apply mechanism exists for this tool
    const html = view({
      tool: "auto-mark",
      autoMarkPhase: "ready",
      autoMarkLandmarks: LANDMARKS,
      drafts: autoMarkDrafts(LANDMARKS),
    });
    expect(html).toContain('data-role="pair-list"');
    // RETARGETED (client live-testing 2026-08-06): the reason now rides `title`,
    // not the button's visible text — see "Apply states what is missing" above.
    expect(html).toMatch(
      /data-role="apply-pairs"[^>]*title="Place at least one complete pair/,
    );
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

  it("an applied tool tells the operator their confirmation no longer describes the site — and offers the act", () => {
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
    // Retargeted 2026-07-29: the sentence used to say "before Deliver" and end there,
    // which made it an instruction the operator could not carry out without navigating
    // back to Declare. It now points at the panes beside it AND the act is on screen.
    expect(html).toContain("confirm it again over the panes on the right");
    expect(html).toContain('data-role="reconfirm-tick"');
    expect(html).toContain("Confirm this fit over the panes");
  });

  it("the re-confirm control names what it is doing while it saves, and surfaces a refusal verbatim", () => {
    const applied = {
      applied: true,
      detail: "rotated +1.0°",
      clocking: null,
      pairs: [],
    } as unknown as AdjustOutcomeView;
    const saving = view({
      activeStatus: "adjusted",
      lastOutcome: applied,
      reconfirmSaving: true,
    });
    expect(saving).toContain("Recording the confirmation…");

    const refused = view({
      activeStatus: "adjusted",
      lastOutcome: applied,
      reconfirmError: "this site has no seat record to confirm over",
    });
    expect(refused).toContain('data-role="reconfirm-error"');
    expect(refused).toContain("this site has no seat record to confirm over");
  });

  it("while a proposal is being judged the surface names the work", () => {
    const html = view({ phase: "working" });
    expect(html).toContain('data-role="tool-busy"');
    expect(html).toContain("the same gates that judged the automation");
  });
});

describe("re-confirming a site reached ANY way (not only off a fresh outcome)", () => {
  const APPLIED = {
    applied: true,
    detail: "rotated +1.0°",
    clocking: null,
    pairs: [],
  } as unknown as AdjustOutcomeView;

  it("an ADJUSTED site opened from the queue offers the act with no outcome in hand", () => {
    // THE DEAD END (verified 2026-07-31): the control lived inside the outcome block,
    // so a click on the queue — which clears lastOutcome — left an `adjusted` site with
    // nothing to confirm it, and Declare's tick refuses a site it never previewed while
    // Deliver refuses the case for being "still unresolved". Reload had the same effect.
    const html = view({ activeTooth: 13, activeStatus: "adjusted", lastOutcome: null });
    expect(html).toContain('data-role="reconfirm"');
    expect(html).toContain('data-role="reconfirm-tick"');
    expect(html).toContain("Confirm this fit over the panes");
  });

  it("the outcome DETAIL is what lastOutcome decides — not whether the act exists", () => {
    const html = view({ activeStatus: "adjusted", lastOutcome: null });
    expect(html).not.toContain('data-role="tool-outcome"');
    expect(html).toContain('data-role="reconfirm-tick"');
  });

  it("the outcome renders BESIDE the act when a tool just applied one", () => {
    const html = view({ activeStatus: "adjusted", lastOutcome: APPLIED });
    expect(html).toContain('data-role="tool-outcome"');
    expect(html).toContain('data-role="reconfirm-tick"');
  });

  it("a site on any other rung is offered no re-confirmation — there is nothing to redo", () => {
    for (const status of ["ready", "flagged", "previewed"]) {
      expect(view({ activeStatus: status })).not.toContain('data-role="reconfirm-tick"');
    }
  });

  /* THE ATTESTATION NEEDS THE EVIDENCE ON SCREEN (design review 2026-07-31). With the
     seated read failed, pane 3 says "The shipped fit could not be read." while this
     block said "confirm it again over the panes on the right" beside an ENABLED
     button — two sentences on one screen contradicting each other, and the click POSTs
     /review and satisfies Deliver's every-site-resolved gate over a blank pane. */
  it("refuses the act, with a reason, while the shipped fit is not on the panes", () => {
    const html = view({
      activeStatus: "adjusted",
      lastOutcome: null,
      seatedPhase: "error",
      seatedPayloadPresent: false,
    });
    expect(html).toContain('data-role="reconfirm-tick"');
    expect(html).toMatch(/data-role="reconfirm-tick"[^>]*disabled=""/);
    expect(html).toContain('data-role="reconfirm-blocked"');
    expect(html).toContain("could not be read");
  });

  it("enables it once the panes are actually showing the fit being attested", () => {
    const html = view({
      activeStatus: "adjusted",
      lastOutcome: null,
      seatedPhase: "ready",
      seatedPayloadPresent: true,
    });
    expect(html).toMatch(/data-role="reconfirm-tick"(?![^>]*disabled)/);
    expect(html).not.toContain('data-role="reconfirm-blocked"');
  });

  it("under-claims by default: a caller that says nothing about the panes gets no act", () => {
    // the safe default is the one that cannot sign over evidence nobody showed
    const html = view({ activeStatus: "adjusted", lastOutcome: null });
    expect(html).toMatch(/data-role="reconfirm-tick"[^>]*disabled=""/);
  });

  it("a refusal from another tool does not take the standing re-confirmation away", () => {
    // the site is still `adjusted`: whatever the last tool did or failed to do, the
    // pose on screen is one the earlier confirmation no longer describes
    const html = view({
      activeStatus: "adjusted",
      lastOutcome: null,
      refusal: "the rim band would leave the scan",
    });
    expect(html).toContain('data-role="reconfirm-tick"');
  });
});

describe("the way onward from Adjust's own rail", () => {
  it("carries a footer with both directions — never only the top rail", () => {
    const html = view();
    expect(html).toContain('data-role="adjust-advance"');
    /* IN THE QUEUE COLUMN now (comp): the footer sits before the stage's toolbar in
       DOM order, because it is the column's foot, not a stage-wide bar. */
    expect(html.indexOf('data-role="adjust-advance"')).toBeLessThan(
      html.indexOf('data-role="workspace-toolbar"'),
    );
    expect(html).toContain('data-role="adjust-back"');
    expect(html).toContain('data-role="adjust-forward"');
    expect(html).toContain("Back to Alignment");
  });

  it("says what leaving the rest of the queue costs — Declare's own words", () => {
    const html = view({ flaggedCount: 2 });
    expect(html).toContain('data-role="adjust-skip-consequence"');
    expect(html).toContain("2 flagged sites stay exactly as the run left them");
    expect(html).toContain("acknowledge it there");
  });

  it("with nothing flagged the same sentence says adjusting was optional", () => {
    expect(view({ flaggedCount: 0 })).toContain("Nothing is flagged — adjusting is optional.");
  });

  it("a blocked Deliver is inert AND says why, in the flow's own sentence", () => {
    const why =
      "Sites are still awaiting review — 1 of 3 still have no verdict; every site " +
      "must be ready, or flagged, before Deliver.";
    const html = view({ deliverBlockedReason: why });
    expect(html).toContain("still have no verdict");
    expect(html).toContain('data-role="adjust-forward" aria-disabled="true"');
    expect(html).not.toContain("Done adjusting — go to Deliver");
  });

  /* SMALLER DOORS (client 2026-08-02: "Smaller buttons here to give more space to the
     tools panel"). The bar's height was mostly the blocked control: the whole reason
     sentence lived INSIDE it, so a two-line sentence made a two-line button. */
  it("the fork's controls are the small pair, like Declare's", () => {
    const html = view();
    expect(html).toMatch(/data-role="adjust-back"[^>]*class="[^"]*button--small/);
    expect(html).toMatch(/data-role="adjust-forward"[^>]*class="[^"]*button--small/);
  });

  it("the blocked reason is PROSE beside the door, not the door's own label", () => {
    const why =
      "Sites are still awaiting review — 1 of 3 still have no verdict; every site " +
      "must be ready, or flagged, before Deliver.";
    const html = view({ deliverBlockedReason: why });
    // the control reads as a control...
    expect(html).toMatch(/data-role="adjust-forward"[^>]*>Go to Deliver</);
    // ...and the reason is still NAMED, visibly, in the same bar (blockedReason doctrine)
    expect(html).toContain('data-role="adjust-forward-reason"');
    expect(html).toContain("still have no verdict");
    // the inert control also explains itself on its own, for a pointer or a reader
    expect(html).toMatch(new RegExp(`title="[^"]*still have no verdict`));
  });

  it("an unblocked Deliver has no reason line at all", () => {
    expect(view()).not.toContain('data-role="adjust-forward-reason"');
  });
});

describe("the best-fit dial's affordances", () => {
  it("shows the band and the default without making the operator probe the input", () => {
    const html = view({ tool: "best-fit" });
    expect(html).toContain('data-role="diameter-band"');
    expect(html).toContain("0.05");
    expect(html).toContain("2.00");
    expect(html).toContain("0.30");
  });

  it("offers the way back to the run's own polish", () => {
    const html = view({ tool: "best-fit", diameterMm: 1.4 });
    expect(html).toContain('data-role="diameter-reset"');
    expect(html).toContain("Reset to Ø0.30 mm");
  });

  it("states no comparison against THIS site's rim — no such number is on the payload", () => {
    // the design's pre-run note reads a fixture field (`diamTrue`) the product has no
    // server equivalent for; rim_agreement_mm measures something else entirely
    expect(view({ tool: "best-fit" })).not.toContain("The rim reads about");
  });
});

describe("the pair set: its ceiling, and starting over", () => {
  const complete = withPick(
    withPick(newPairDraft("p1", false), "part", [1, 0, 1]),
    "scan",
    [5, 5, 5],
  );

  it("names the 8-pair ceiling BEFORE it is exceeded", () => {
    // RETARGETED (client live-testing 2026-08-06): the ceiling sentence now rides
    // the drawer's ONE status line (`data-role="pair-status"`) rather than its own
    // `pair-set` paragraph — merged with the hint bar and the Apply placeholder,
    // which said overlapping things. The words themselves are unchanged.
    const html = view({ tool: "fit-by-points", drafts: [] });
    expect(html).toContain('data-role="pair-status"');
    expect(html).toContain("8 at most");
  });

  /* THE VACUOUS RMS, BEFORE THE CLICK (defect cap6020-neodent-gm, 2026-08-01). The
     operator applied one pair, the cap turned −50.9°, and the outcome said "marks
     agree to 0.000mm RMS" — a residual that is zero by construction. The caution
     used to ride inline, beside a LIVE Apply; the act stays possible. RETARGETED
     (§10-AN slice C, client 2026-08-06: "any warnings ... need to come in as
     modals") — it is now the dock header's caution chip + the modal it opens
     (`cautionsOpen` pinned via props, the switch-confirm/reasons-dialog precedent),
     never a second refusal-shaped surface. */
  it("cautions the one-pair fit beside the Apply that will run it", () => {
    const closed = view({ tool: "fit-by-points", drafts: [complete] });
    expect(closed).toMatch(/data-role="pair-caution-chip"[^>]*>⚠ 1 caution/);
    const open = view({ tool: "fit-by-points", drafts: [complete], cautionsOpen: true });
    expect(open).toContain('data-role="pair-caution-list"');
    expect(open).toContain("no agreement number");
    // and the control is still live — this is disclosure, not a refusal
    expect(open).toContain('data-role="apply-pairs"');
    expect(open).toContain("Apply the fit");
  });

  /* THE PRE-REFUSAL'S WIRING (review 2026-08-01). The BFF passthrough is pinned by
     tests because dropping it would silence the guard with nothing failing — and the
     same argument applies one layer up: without this test, deleting
     `clock={payload?.clock_reference ?? null}` or either `clock={clock}` prop leaves
     the whole product suite green and the operator back on the 422. RETARGETED
     (§10-AN slice C): the per-pair `mark-guard` paragraph is gone; the same
     sentence now lists in the caution modal, named "Pair 1" exactly as the
     blocked Apply button's own `title` names it. */
  it("refuses a mark on the screw access locally, and makes Apply say so", () => {
    const onAccess = withPick(
      withPick(newPairDraft("p1", false), "part", [2, 0, 1]),
      "scan",
      [5.1, 5, 5],
    );
    const props = {
      tool: "fit-by-points" as const,
      drafts: [onAccess],
      pose: { origin: [5, 5, 5], axis: [0, 0, 1] },
      clock: { rim_centre: [5, 5, 5], min_lever_mm: 0.5 },
    };
    const open = view({ ...props, cautionsOpen: true });
    expect(open).toContain('data-role="pair-caution-list"');
    expect(open).toContain("Pair 1: This mark sits");
    expect(open).toContain("screw access");
    // and the control is INERT with the reason reachable on it — not live into a
    // 422. RETARGETED (client live-testing 2026-08-06): the reason used to be the
    // span's own visible text; it now rides `title`, naming which pair, same as
    // before, on hover/focus rather than filling the button's face.
    expect(view(props)).toMatch(/data-role="apply-pairs"[^>]*title="Pair 1/);
  });

  it("keeps Apply live when the server's reference has not arrived", () => {
    // the old approximation may caution, but it must never block: refusing on it
    // could refuse a correction the server would have accepted (plan §10-F)
    const onAccess = withPick(
      withPick(newPairDraft("p1", false), "part", [2, 0, 1]),
      "scan",
      [5.1, 5, 5],
    );
    const html = view({
      tool: "fit-by-points",
      drafts: [onAccess],
      pose: { origin: [5, 5, 5], axis: [0, 0, 1] },
      clock: null,
      cautionsOpen: true,
    });
    // RETARGETED (§10-AN slice C): the caution still exists (the chip and the modal
    // both name it) — what must never happen is the Apply control going inert.
    expect(html).toContain('data-role="pair-caution-list"');
    expect(html).toContain("Apply the fit");
  });

  it("drops the caution once a second pair stands", () => {
    const second = withPick(
      withPick(newPairDraft("p2", false), "part", [2, 0, 1]),
      "scan",
      [6, 5, 5],
    );
    // RETARGETED (§10-AN slice C): the chip itself is the tell now — it renders
    // only where `pairCautions` has something to say.
    expect(view({ tool: "fit-by-points", drafts: [complete, second] })).not.toContain(
      'data-role="pair-caution-chip"',
    );
  });

  it("cautions auto-mark's single accepted proposal the same way — one mechanic", () => {
    const landmarks: LandmarkView[] = [
      { id: "notch-a", kind: "notch", point: [1.5, 0, 2], lever_arm_mm: 1.5,
        azimuth_deg: 0 },
    ];
    const html = view({
      tool: "auto-mark",
      autoMarkLandmarks: landmarks,
      drafts: [withPick(autoMarkDrafts(landmarks)[0]!, "scan", [5, 5, 5])],
    });
    // RETARGETED (§10-AN slice C): same chip, same mechanic, for auto-mark's pairs.
    expect(html).toMatch(/data-role="pair-caution-chip"[^>]*>⚠ 1 caution/);
  });

  it("offers one bulk clear once anything is placed", () => {
    const html = view({ tool: "fit-by-points", drafts: [complete] });
    expect(html).toContain('data-role="clear-pairs"');
    expect(html).toContain("Clear all pairs");
  });

  it("offers no clear when there is nothing to clear", () => {
    expect(view({ tool: "fit-by-points", drafts: [] })).not.toContain(
      'data-role="clear-pairs"',
    );
  });

  it("auto-mark's bulk act is a START OVER — its drafts are the server's proposal", () => {
    const landmarks: LandmarkView[] = [
      { id: "notch-a", kind: "notch", point: [1.5, 0, 2], lever_arm_mm: 1.5,
        azimuth_deg: 0 },
    ];
    const html = view({
      tool: "auto-mark",
      autoMarkPhase: "ready",
      autoMarkLandmarks: landmarks,
      drafts: autoMarkDrafts(landmarks),
    });
    expect(html).toContain('data-role="clear-pairs"');
    expect(html).toContain("Start the matching over");
  });
});

describe("a flagged site's OTHER way out (the act itself lives on Deliver)", () => {
  it("says a flagged site can ship as an exception, and where that is acknowledged", () => {
    const html = view({ activeStatus: "flagged" });
    expect(html).toContain('data-role="flagged-exception"');
    expect(html).toContain("exception");
    expect(html).toContain("Deliver");
  });

  it("offers no accept control here — this stage sets no status", () => {
    const html = view({ activeStatus: "flagged" });
    expect(html).not.toContain('data-role="accept-flagged"');
    expect(html).toContain("nothing on this stage accepts it");
  });

  it("says nothing on a site that is not flagged", () => {
    expect(view({ activeStatus: "ready" })).not.toContain(
      'data-role="flagged-exception"',
    );
  });
});

/**
 * THE WORKSPACE TOOLBAR ON ADJUST (gaps `workspace-toolbar-site-chip`,
 * `alignment-metrics-strip`, `named-view-presets`). Adjust had NO stage toolbar at
 * all: the tooth number appeared only in the toolbox heading and the queue rows, both
 * inside the scrolling work column. Worse, every alignment fact was tool-scoped — an
 * operator on the mark-trench tab could not see the pairs, one on the rotation tab
 * could not see the deviation. The same strip Declare grew answers both.
 */
describe("the workspace toolbar over the panes", () => {
  it("names the active tooth and the effective system", () => {
    const html = view({ systemModel: "conical-4x4" });
    expect(html).toContain('data-role="workspace-toolbar"');
    expect(html).toContain('data-role="site-chip"');
    expect(html).toContain("Tooth 13");
    expect(html).toContain("conical-4x4");
  });

  it("the status chip is the SERVER's rung for the active site, verbatim", () => {
    expect(view()).toMatch(
      /data-role="toolbar-status"[^>]*data-status="flagged"[^>]*>flagged</,
    );
  });

  it("the strip carries VARIANT, DEV RMS, ROTATION and PAIRS — the comp's four chips restored (§10-AN slice C)", () => {
    /* RETARGETED (§10-AN slice C, client 2026-08-06 comp read directly: "match the
       designs"). The 2026-08-06 ruling this test used to pin ("we can only allow
       one row … why do we need this DEV RMS") traded the figures for pane height —
       but the ROW SHAPE was the ask, not the absence of the figures: the client's
       later design puts all four back on one nowrap row (still one line; the panes
       keep the space) and this supersedes the earlier removal. DEV P90 stays off
       the strip (still in Numbers & log) — the comp shows four chips, not five. */
    const html = view({
      tool: "rotation",
      stats: [
        { id: "variant", label: "VARIANT", value: "5020" },
        { id: "dev-rms", label: "DEV RMS", value: "0.041 mm" },
        { id: "dev-p90", label: "DEV P90", value: "0.077 mm" },
        { id: "rotation", label: "ROTATION", value: "+3.2°" },
        { id: "pairs", label: "PAIRS", value: "3 / 8" },
      ],
    });
    expect(html).toContain('data-role="alignment-strip"');
    for (const id of ["variant", "dev-rms", "rotation", "pairs"]) {
      expect(html).toMatch(new RegExp(`data-stat="${id}"`));
    }
    expect(html).toContain("0.041 mm");
    expect(html).toContain("+3.2°");
    expect(html).toContain("3 / 8");
    // DEV P90 is published to Numbers & log, never the strip
    expect(html).not.toMatch(/data-stat="dev-p90"/);
    expect(html).not.toContain("0.077 mm");
  });

  it("with no site selected the chip says so rather than going blank", () => {
    const html = view({ activeTooth: null, activeStatus: null });
    expect(html).toContain("No site selected");
    expect(html).toContain('data-role="workspace-toolbar"');
  });

  it("the toolbar sits with the PANES, not inside the scrolling work column", () => {
    /* Anchored on the QUEUE, which since 2026-08-02 is the only thing the work column
       holds — the tools and the forward acts moved into the stage column beneath the
       panes. This used to compare against `workbench__work-footer`, which was a fine
       proxy while that footer was the work column's last child and a wrong one the
       moment it moved too. The claim being made is unchanged: the toolbar belongs to
       the panes, not to the scrolling column beside them. */
    const html = view();
    const queue = html.indexOf('data-role="adjust-queue"');
    expect(queue).toBeGreaterThan(-1);
    expect(html.indexOf('data-role="workspace-toolbar"')).toBeGreaterThan(queue);
  });

  /*
   * THE CHAINED RE-RUN (client ruling 2026-08-15: "we need to have the ability
   * to apply the fit to re-run, or have another button in adjustment that
   * re-runs, having two is confusing"). RETARGETED from the standalone
   * "Re-run the alignment" button (client 2026-08-09) this queue panel used to
   * offer: that decision is superseded — applying ANY adjustment now fires the
   * re-run itself (`settle` → `appliedToolChainsRerun` → `fireRerun`), so the
   * button retires and `rerunning`/`rerunError` alone drive what renders here.
   */
  it("no button — a static render can never offer the retired standalone act, in any state", () => {
    expect(view()).not.toContain('data-role="rerun-alignment"');
    expect(view({ rerunning: true })).not.toContain('data-role="rerun-alignment"');
    expect(
      view({ rerunError: "a run is already in flight for case 'x'" }),
    ).not.toContain('data-role="rerun-alignment"');
  });

  it("while the chained re-run is in flight the queue panel says so, with a spinner", () => {
    const html = view({ rerunning: true });
    const queue = html.indexOf('data-role="adjust-queue"');
    const band = html.indexOf('data-role="run-progress"');
    expect(band).toBeGreaterThan(queue);
    expect(html).toMatch(/data-role="run-progress"[^>]*role="status"/);
    expect(html).toContain('busy-state__spinner');
    expect(html).toContain(
      "marks, pairs and best fits re-apply after the automation",
    );
  });

  it("idle — no progress band and no error", () => {
    const html = view({ rerunning: false, rerunError: null });
    expect(html).not.toContain('data-role="run-progress"');
    expect(html).not.toContain('data-role="rerun-error"');
  });

  it("a chained re-run's failure renders in the queue panel, verbatim — same words the retired button showed", () => {
    const html = view({
      rerunning: false,
      rerunError: "a run is already in flight for case 'x'",
    });
    expect(html).toContain("a run is already in flight");
    expect(html).not.toContain('data-role="run-progress"');
  });

  it("failure honesty: the run's own error never hides the apply that already landed", () => {
    /* §10-AD's contract, pinned at the render layer (item 4 of the 2026-08-15
       ruling): a chained re-run that fails does NOT roll back the tool's own
       already-landed apply. `lastOutcome` (what the tool did) and `rerunError`
       (the chain's own failure) are independent props fed by independent
       state slots in the container — this proves the View renders BOTH
       together rather than one crowding out the other. */
    const outcome: AdjustOutcomeView = {
      tooth: 13,
      operation: "rotation",
      detail: "rotated +9.9°",
      applied: true,
      files: [],
      clocking: null,
      deviation: null,
      stale_metrics: [],
      nudge: null,
      applied_delta_deg: 9.9,
      cumulative_deg: 9.9,
      stability_excess_mm: null,
      best_fit: null,
      pairs: [],
      residual_rms_mm: null,
      cross_checked: null,
      click_azimuth_deg: null,
      matched_feature_azimuth_deg: null,
    };
    const html = view({
      lastOutcome: outcome,
      rerunning: false,
      rerunError: "a run is already in flight for case 'x'",
    });
    expect(html).toContain("rotated +9.9°");
    expect(html).toContain("a run is already in flight");
  });

  it("named view presets render only when a handler can apply them", () => {
    expect(view()).not.toContain('data-role="view-preset"');
    const wired = view({ onSelectView: () => undefined, viewPreset: "occlusal" });
    expect(wired).toMatch(
      /data-role="view-preset"[^>]*data-preset="occlusal"[^>]*aria-pressed="true"/,
    );
  });

  /* THE PROVENANCE POPOVER (gap `deviation-budget-in-workspace`). Adjust had NO
     toolbar children slot at all before this — `insightSlot` is assembled by the
     container (it needs this stage's caseId, which the View is never given, same
     reasoning as `panes`). Pinned at the VIEW layer, same as every other toolbar
     control in this file: severing the container's wiring is a code-reading concern,
     but the View forgetting to place the slot INSIDE the toolbar is what this guards. */
  it("carries the site-numbers-and-case-log toggle inside the toolbar, wherever the container hands it one", () => {
    expect(view()).not.toContain('data-role="insight-toggle"');
    const html = view({
      insightSlot: <WorkspaceInsight caseId="case-a" tooth={13} />,
    });
    const toolbar = html.slice(html.indexOf('data-role="workspace-toolbar"'));
    expect(toolbar.slice(0, toolbar.indexOf("</div>") + 6)).toContain(
      'data-role="insight-toggle"',
    );
  });
});

/**
 * DROPPING A CAP (design flow.dc.html dropSite 1345-1354, template 471; gap
 * `drop-a-cap-from-adjust`). The act is the BFF's per-site withhold INTENT — a
 * draft the confirmation signs — so what is checked here is the TONE and the
 * REACH: that the reversal is as findable as the act, that the row says what
 * happened without claiming what the site is, and that nothing on this surface
 * pretends the drop is final.
 */
describe("dropping a cap", () => {
  it("offers the act on the selected site, in the operator's own terms", () => {
    const html = view();
    expect(html).toContain('data-role="drop-site"');
    expect(html).toContain("Drop this cap");
    expect(html).toContain("hold it back from the release and the bill");
  });

  it("offers the REVERSAL in the same place, not as a hidden undo", () => {
    const html = view({ entries: [DROPPED, CLEAN], activeTooth: 13 });
    expect(html).toContain('data-role="drop-site"');
    expect(html).toContain("Bring this cap back into the case");
    expect(html).toContain('data-dropped="true"');
  });

  it("says the confirmation at Deliver is what signs it", () => {
    const html = view({ entries: [DROPPED, CLEAN], activeTooth: 13 });
    expect(html).toContain('data-role="drop-note"');
    expect(html).toContain("Deliver");
  });

  it("the dropped row reads as an ACT, never as a rung", () => {
    const html = view({ entries: [DROPPED, CLEAN], activeTooth: 13 });
    expect(html).toContain('data-role="queue-dropped"');
    expect(html).toContain("nothing is released for it, and it is not billed");
  });

  it("never claims a dropped cap was not aligned — the run already ran", () => {
    const html = view({ entries: [DROPPED, CLEAN], activeTooth: 13 });
    expect(html).not.toContain("not aligned");
  });

  it("a dropped row stops asking for the rework the operator declined", () => {
    // the flag line is the queue's ASK; a cap that is on its way out of the case
    // must not keep asking to be reworked, though the reasons stay one click away
    const html = view({ entries: [DROPPED, CLEAN], activeTooth: 13 });
    expect(html).not.toContain('data-role="queue-flag"');
    expect(html).toContain('data-role="queue-why"');
  });

  it("shows the refusal VERBATIM when the act is refused", () => {
    const html = view({ dropError: "the case changed underneath this write" });
    expect(html).toContain('data-role="drop-error"');
    expect(html).toContain("the case changed underneath this write");
  });

  it("names the wait rather than freezing silently", () => {
    const html = view({ dropSaving: true });
    expect(html).toContain("Recording");
    expect(html).toMatch(/data-role="drop-site"[^>]*disabled/);
  });

  it("offers nothing to drop when no site is selected", () => {
    const html = view({ activeTooth: null, activeStatus: null });
    expect(html).not.toContain('data-role="drop-site"');
  });
});

/**
 * RE-READING A SITE WITHOUT APPLYING A TOOL (gap
 * `re-preview-a-site-without-applying-a-tool`, 2026-07-31). An applied tool already
 * updates the panes (`AdjustResultView.pane_payload`, replaced verbatim); this
 * control's whole job is the read WITHOUT a tool — after a rework elsewhere, or a
 * stale row. RETARGETED (§10-AN, 2026-08-06): it now lives in the instrument dock's
 * own FIXED FOOTER (`AdjustDock.tsx`, `data-role="drawer-acts"`) rather than above
 * the tool tabs — it is not any one correction tool's act, so it must stay reachable
 * whichever tab is open, the same reasoning the clock-unverified notice below shares.
 */
describe("re-reading a site's numbers, without applying a tool", () => {
  it("renders for an active site, and promises a re-read rather than an outcome", () => {
    const html = view();
    expect(html).toContain('data-role="re-preview"');
    // renderToStaticMarkup escapes the label's own apostrophe (site&#x27;s) — matched
    // either side of it rather than the raw string, like every other apostrophed
    // label in this suite
    expect(html).toContain("Re-read this site");
    expect(html).toContain("numbers");
    // the design prototype's own label for this control is "this will pass" — a
    // client-side verdict this app is forbidden from making
    expect(html).not.toContain("this will pass");
  });

  it("renders nothing when no site is selected", () => {
    expect(view({ activeTooth: null })).not.toContain('data-role="re-preview"');
  });

  it("is disabled while a tool is being judged, so the two writes cannot race", () => {
    const html = view({ phase: "working" });
    expect(html).toMatch(/data-role="re-preview"[^>]*disabled=""/);
  });

  it("is disabled while the site's initial seated read is still in flight — a narrower race", () => {
    // the container's own GET .../seated for a freshly-selected site replaces
    // `payload` unconditionally when it lands; a re-read that resolved FIRST would
    // otherwise be clobbered by that stale response landing after it
    const html = view({ seatedPhase: "loading" });
    expect(html).toMatch(/data-role="re-preview"[^>]*disabled=""/);
  });

  it("stays live once the seated read has failed — recovering from that IS the point", () => {
    const html = view({ seatedPhase: "error" });
    expect(html).not.toMatch(/data-role="re-preview"[^>]*disabled=""/);
  });

  it("names its own in-flight state, and disables itself for it", () => {
    const html = view({ rePreviewPhase: "working" });
    expect(html).toMatch(/data-role="re-preview"[^>]*disabled=""/);
    expect(html).toContain("Re-reading");
  });

  it("renders what the re-read found, verbatim, only once a result exists", () => {
    expect(view()).not.toContain('data-role="re-preview-result"');
    const html = view({ rePreviewResult: rePreviewView({ changed: true }) });
    expect(html).toContain('data-role="re-preview-result"');
    expect(html).toContain("cleared");
  });

  it("lists what moved, the row's earlier figure beside the pose on disk now — server numbers", () => {
    const html = view({
      rePreviewResult: rePreviewView({
        changed: true,
        previous: { deviation_rms_mm: 0.61 },
        rederived: { deviation_rms_mm: 0.43 },
      }),
    });
    expect(html).toContain('data-role="re-preview-rows"');
    expect(html).toContain("0.61");
    expect(html).toContain("0.43");
  });

  it("names the metrics a re-read could not refresh, using the shared vocabulary", () => {
    const html = view({
      rePreviewResult: rePreviewView({ stale_metrics: ["rim_agreement_mm", "guidance"] }),
    });
    expect(html).toContain("the rim agreement and the gate verdict");
  });

  it("a refusal or transport error renders verbatim, with no auto-retry", () => {
    const html = view({ rePreviewError: "the run directory for this case has moved" });
    expect(html).toContain('data-role="re-preview-error"');
    expect(html).toContain("the run directory for this case has moved");
    // the result block and the error block are mutually exclusive — a stale result
    // from an earlier click must not sit beside a fresh refusal
    expect(html).not.toContain('data-role="re-preview-result"');
  });
});

/**
 * THE UNVERIFIED CLOCK'S ACTIONABLE SURFACE (§10-H's "STILL OPEN" line, closed
 * 2026-08-02) — RETARGETED (§10-AN slice D, client screenshots: at a short window
 * the standing inline band this describe block used to pin — `data-role=
 * "clock-unverified"`, a `flex-shrink: 0` box between the panes and the dock —
 * pushed the whole page back into scroll). The decision that changed: the notice
 * is no longer a surface of its OWN; it is one more entry in AdjustDock's caution
 * chip/dialog, counted and rendered the same way a pair caution is. The exhaustive
 * behaviour pins (the count, closed-by-default, the words verbatim, the routed
 * control, the no-claim guarantee) now live in AdjustDock.test.tsx, beside the
 * component that actually owns the chip and the dialog — the switch-confirm/
 * reasons-dialog precedent, a dialog rendered open through its own lifted prop
 * rather than a click. This file keeps only what is still ITS job: the container's
 * `clockNotice` reaches AdjustDock unchanged, and the old standing band is gone.
 */
describe("the unverified clock's actionable surface — folded into AdjustDock's caution dialog", () => {
  // No apostrophes or quotes in this fixture on purpose — renderToStaticMarkup
  // escapes them to HTML entities, and every other assertion in this suite that
  // pins a rendered sentence verbatim avoids them for the same reason.
  const NOTICE: UnverifiedClockNotice = {
    facts: "The automatic reader could not verify this caps rotation on this scan.",
    act: "Auto-mark proposes rotation-defining landmarks toward a cross-checked fit.",
    armTool: "auto-mark",
  };

  it("passes clockNotice through to the dock, which counts it in the caution chip", () => {
    const html = view({ clockNotice: NOTICE });
    expect(html).toMatch(/data-role="pair-caution-chip"[^>]*>⚠ 1 caution</);
  });

  it("renders no standing band between the panes and the dock any more", () => {
    const html = view({ clockNotice: NOTICE });
    expect(html).not.toContain('data-role="clock-unverified"');
  });

  it("renders no chip when the container found nothing to say (a verified site)", () => {
    expect(view({ clockNotice: null })).not.toContain('data-role="pair-caution-chip"');
  });

  it("renders no chip by default — a static caller predating this prop", () => {
    expect(view()).not.toContain('data-role="pair-caution-chip"');
  });

  it("surfaces the facts, the act and the route to auto-mark once the dialog opens, through the lifted cautionsOpen prop", () => {
    const html = view({ clockNotice: NOTICE, cautionsOpen: true });
    expect(html).toContain('data-role="clock-caution"');
    expect(html).toContain(NOTICE.facts);
    expect(html).toContain(NOTICE.act);
    expect(html).toContain('data-role="verify-rotation"');
  });
});

describe("the ghost note (§10-AI) — the pose's claim, captioned honestly", () => {
  it("renders beside the pair prompt while ghosts are on the glass", () => {
    const html = view({
      tool: "fit-by-points",
      drafts: [withPick(newPairDraft("p", false), "part", [1, 0, 1])],
      ghostsActive: true,
    });
    expect(html).toContain('data-role="ghost-note"');
    expect(html).toContain("where the current pose expects");
    expect(html).toContain("the difference is the correction");
    // never a promise that the ghost is TRUTH — it is the pose's own claim
    expect(html).not.toContain("where the feature is");
  });

  it("absent with no ghosts, and for static callers predating the prop", () => {
    expect(view({ tool: "fit-by-points" })).not.toContain(
      'data-role="ghost-note"',
    );
  });

  it("rides AUTO-MARK's body too — where matching a proposal is the whole job", () => {
    const landmark: LandmarkView = {
      id: "t1", kind: "trench", point: [1, 0, 1],
      lever_arm_mm: 2.1, azimuth_deg: 40,
    };
    const html = view({
      tool: "auto-mark",
      autoMarkPhase: "ready",
      autoMarkLandmarks: [landmark],
      drafts: autoMarkDrafts([landmark]),
      ghostsActive: true,
    });
    expect(html).toContain('data-role="ghost-note"');
  });
});

describe("pairMarkers — every placed point is DRAWN (client 2026-08-04, twice)", () => {
  it("a SPAN BOTH draft draws two library markers, a/b like the scan's own", () => {
    // the reported bug: the second library click was recorded and never drawn —
    // the operator watched it "not take effect" while the checklist ticked
    let draft = newPairDraft("s1", true, true);
    draft = withPick(draft, "part", [1, 0, 1]);
    draft = withPick(draft, "part", [2, 0, 1]);
    draft = withPick(draft, "scan", [5, 0, 1]);
    draft = withPick(draft, "scan", [6, 0, 1]);
    const markers = pairMarkers([draft]);
    expect(markers.library?.map((m) => m.label)).toEqual(["1a", "1b"]);
    expect(markers.library?.[1]?.position).toEqual([2, 0, 1]);
    expect(markers.scan?.map((m) => m.label)).toEqual(["1a", "1b"]);
  });

  it("a plain point pair keeps the bare number on both panes", () => {
    let draft = newPairDraft("p1", false);
    draft = withPick(draft, "part", [1, 0, 1]);
    draft = withPick(draft, "scan", [5, 0, 1]);
    const markers = pairMarkers([draft]);
    expect(markers.library?.map((m) => m.label)).toEqual(["1"]);
    expect(markers.scan?.map((m) => m.label)).toEqual(["1"]);
  });
});

describe("a placed pair folds to one line (client 2026-08-04)", () => {
  it("a complete draft wears the compact clothes; an open one keeps the checklist", () => {
    const complete = withPick(
      withPick(newPairDraft("p1", false), "part", [1, 0, 1]),
      "scan",
      [2, 0, 1],
    );
    const open = newPairDraft("p2", false);
    const html = view({ tool: "fit-by-points", drafts: [complete, open] });
    const rows = html.split('data-role="pair-row"');
    expect(rows[1]).toContain("adjust-pairs__row--complete");
    expect(rows[2]).not.toContain("adjust-pairs__row--complete");
    // the per-mark undos survive the fold — the refusal flow names exactly one
    // mark to re-place, and folding must not cost that exit
    expect(rows[1]).toContain('data-role="remove-point"');
  });
});

/** §10-AD's surfacing half: the queue row says the operator's measurements ride the
 * next run — the mechanism's visible face, worded as a fact about the SELECTION,
 * never a promised outcome. */
describe("the queue's evidence line", () => {
  it("renders the ride words when the site holds measurements", () => {
    const html = view({
      entries: [{ ...FLAGGED, evidenceCount: 2 }],
    });
    expect(html).toContain('data-role="queue-evidence"');
    expect(html).toContain("2 measurements ride the next run");
  });

  it("stays silent at zero — no empty claim", () => {
    const html = view({ entries: [FLAGGED] });
    expect(html).not.toContain('data-role="queue-evidence"');
  });
});

/** §10-AD's ANSWER half (audit 2026-08-04): after a run, the row and the site
 * panel say what each persisted measurement actually DID — the server's own
 * receipts, detail verbatim. The promise line ("rides the next run") stands
 * down where the answer is on screen: both at once would read as a promise
 * about a run that already answered. */
describe("the run's re-apply receipts", () => {
  const RECEIPTS = [
    { tooth: 13, kind: "mark", outcome: "applied", appliedAt: "t1",
      detail: "trench matched — clocking re-read" },
    { tooth: 13, kind: "best_fit", outcome: "already-optimal", appliedAt: "t2",
      detail: "already within the certified bound" },
    { tooth: 13, kind: "pairs", outcome: "refused", appliedAt: "t3",
      detail: "the marks disagree with each other — fit refused" },
  ];

  it("the queue row answers with counts and stands down the stale promise", () => {
    const html = view({
      entries: [{ ...FLAGGED, evidenceCount: 3, receipts: RECEIPTS }],
    });
    expect(html).toContain('data-role="queue-receipts"');
    expect(html).toContain(
      "this run: 1 re-applied · 1 already optimal · 1 refused",
    );
    expect(html).not.toContain('data-role="queue-evidence"');
  });

  it("the site panel lists each receipt with the server's sentence verbatim", () => {
    const html = view({ entries: [{ ...FLAGGED, receipts: RECEIPTS }] });
    expect(html).toContain('data-role="evidence-receipts"');
    expect(html).toContain("What this run re-applied");
    expect(html).toContain('data-outcome="applied"');
    expect(html).toContain("trench mark — re-applied");
    expect(html).toContain("trench matched — clocking re-read");
    expect(html).toContain("point pairs — refused");
    expect(html).toContain("the marks disagree with each other — fit refused");
  });

  it("already-optimal wears the pass tone, never the refusal one", () => {
    const html = view({ entries: [{ ...FLAGGED, receipts: [RECEIPTS[1]!] }] });
    expect(html).toContain('data-outcome="already-optimal"');
    expect(html).toContain("best fit — already optimal");
    expect(html).not.toContain("run-refusal");
  });

  it("a re-emit's carried receipts title the block honestly — and the queue row agrees", () => {
    const html = view({
      entries: [{ ...FLAGGED, receipts: [RECEIPTS[0]!] }],
      receiptsCarried: true,
    });
    expect(html).toContain("What the source run re-applied");
    // review 2026-08-04: the row and the panel are one screen — the row must not
    // attribute to this run an act the panel says the source run performed
    expect(html).toContain("carried forward: 1 re-applied");
    expect(html).not.toContain("this run: 1 re-applied");
  });

  it("a dropped cap's PANEL keeps the receipts — facts, not asks", () => {
    // the queue row is the ASK and a dropped cap stops asking; the receipts are
    // measurements of the standing run, and dropping changes what ships, never
    // what was measured
    const html = view({
      entries: [{ ...FLAGGED, dropped: true, receipts: [RECEIPTS[0]!] }],
    });
    expect(html).toContain('data-role="evidence-receipts"');
  });

  it("stays silent with no receipts — no empty panel, and static callers predate the props", () => {
    expect(view()).not.toContain('data-role="evidence-receipts"');
    expect(view()).not.toContain('data-role="queue-receipts"');
  });

  it("a dropped cap's row stops showing receipts — the row has stopped asking", () => {
    const html = view({
      entries: [{ ...FLAGGED, dropped: true, receipts: RECEIPTS }],
    });
    expect(html).not.toContain('data-role="queue-receipts"');
  });
});

/** PER-SITE RELIEF (§10-B/C): the control renders the served facts — the site's own
 * ask or the standing case value — with the §10-AC disclosure; static tests pin the
 * words and the roles (the act itself is the container's PUT). */
describe("the per-site relief control", () => {
  const RELIEF = {
    siteValue: null,
    caseValue: 0.2,
    ceilingLine: "ceiling 0.08mm for 5020 — a larger ask is cut at the ceiling",
    runDone: true,
    saving: false,
    error: null,
    onApply: () => undefined,
  };

  it("renders the case value standing and the served ceiling", () => {
    const html = view({ relief: RELIEF });
    expect(html).toContain('data-role="site-relief"');
    expect(html).toContain("case 0.2mm stands");
    expect(html).toContain("ceiling 0.08mm for 5020");
  });

  it("over a done run, discloses the re-emit — never a full re-run", () => {
    // RETARGETED (client live-testing 2026-08-06): the row used to stack TWO
    // caption sentences under it — the served ceiling (kept, above, as its own
    // line) and this re-emit disclosure. The disclosure now rides the Apply
    // button's `title`, the same convention "Go to Deliver" and the pair Apply
    // control both use when there is something to say about a click before it is
    // made — never a second full-width sentence under the row.
    const html = view({ relief: RELIEF });
    expect(html).toMatch(
      /data-role="site-relief-apply"[^>]*title="Applying re-emits the package from the run&#x27;s own poses/,
    );
    expect(html).not.toContain("re-processes the case");
    // no second caption paragraph — one line survives (the ceiling), not two
    const relief = html.slice(html.indexOf('data-role="site-relief"'));
    expect(relief.match(/site-relief__note/g)?.length).toBe(1);
  });

  it("an override names itself, and the refusal renders verbatim", () => {
    const html = view({
      relief: { ...RELIEF, siteValue: 0.05,
                error: "gingival_offset_mm must be a clearance between 0 and 1.5mm" },
    });
    expect(html).toContain("overridden");
    expect(html).toContain('data-role="site-relief-error"');
    expect(html).toContain("clearance between 0 and");
  });
});
