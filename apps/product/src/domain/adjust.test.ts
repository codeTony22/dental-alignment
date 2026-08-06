/**
 * ADJUST'S PURE RULES (slice 6). The physics is the worker's and the gates are the
 * BFF's; what is pinned here is what this app actually decides — ORDER, WORDS and the
 * one NARROWING that keeps a pass from wearing a refusal's clothes.
 */
import { describe, expect, it } from "vitest";
import type {
  AdjustOutcomeView,
  AdjustResultView,
  ApiResult,
  LandmarkView,
} from "../api/client";
import {
  evidenceReceiptLine,
  evidenceReceipts,
  evidenceReceiptsTitle,
  evidenceRideWords,
  receiptKindWords,
  receiptOutcomeWords,
  receiptsCarriedByReemit,
  ADJUST_TOOLS,
  DEFAULT_DIAMETER_MM,
  MAX_DIAMETER_MM,
  MAX_PAIRS,
  MIN_DIAMETER_MM,
  adjustPaneNotices,
  adjustQueue,
  adjustUnionCaption,
  alreadyOptimalFrom,
  applyBlockedReason,
  autoMarkDrafts,
  autoMarkSourceLabel,
  autoMarkSummary,
  crossCheckCaution,
  crossCheckCautionDetail,
  diameterBandWords,
  dropLabel,
  dropNote,
  droppedRowWords,
  flaggedExceptionWords,
  gateActions,
  ghostScanMarkers,
  isComplete,
  landmarkLabel,
  needsReconfirm,
  needsReconfirmStatus,
  outcomeMovedTheRow,
  paneArming,
  reconfirmControl,
  newPairDraft,
  pairSetWords,
  pairStatusLine,
  observationWords,
  outcomeWords,
  pairBody,
  pairPrompt,
  pairSlot,
  pairSlots,
  pairWords,
  queueSummary,
  rePreviewButtonLabel,
  rePreviewRows,
  rePreviewWords,
  spanLeverCaution,
  markLeverGuard,
  reworkWords,
  staleMetricsPhrase,
  unverifiedClockNotice,
  withPick,
  withoutPick,
  type AdjustQueueEntry,
  acceptExceptionOffer,
  exceptionDraftWords,
} from "./adjust";
import { rePreviewView, siteView } from "../testing/fixtures";

const ACTION =
  "The cap's ROTATION could not be verified — visually check the coded features " +
  "in view 1 (top-down) before accepting.";

function row(tooth: number, level = "ready", actions: string[] = []) {
  return { tooth, guidance: { level, actions } };
}

describe("acceptExceptionOffer — the comp's amber act, made a DRAFT (client 2026-08-02)", () => {
  const flagged = { flagged: true, dropped: false, exceptionAcknowledged: false };

  it("offers acceptance on a flagged, undropped site", () => {
    const offer = acceptExceptionOffer(flagged);
    expect(offer?.label).toBe("Accept as flagged exception");
    expect(offer?.title).toContain("pre-fills the row at Deliver");
  });

  it("offers the WITHDRAWAL once a draft stands — two-way, like the review tick", () => {
    const offer = acceptExceptionOffer({ ...flagged, exceptionAcknowledged: true });
    expect(offer?.label).toContain("withdraw");
    expect(offer?.title).toContain("Nothing was signed");
  });

  it("offers nothing on a clean site — there is no exception to accept", () => {
    expect(acceptExceptionOffer({ ...flagged, flagged: false })).toBeNull();
  });

  it("offers nothing on a dropped cap — it was answered the other way", () => {
    expect(acceptExceptionOffer({ ...flagged, dropped: true })).toBeNull();
  });

  it("offers nothing with no active site", () => {
    expect(acceptExceptionOffer(null)).toBeNull();
  });

  it("never claims the act SIGNS — the confirmation at Deliver is the signature", () => {
    for (const entry of [flagged, { ...flagged, exceptionAcknowledged: true }]) {
      const offer = acceptExceptionOffer(entry);
      expect(offer?.title).toContain("confirmation");
      expect(offer?.title).not.toContain("will sign");
      expect(offer?.label).not.toContain("signed");
    }
    expect(exceptionDraftWords()).toContain("Deliver's confirmation signs it");
  });
});

describe("the flagged-first queue", () => {
  const sites = [
    siteView({ tooth: 4, status: "ready", declared_variant: "5020" }),
    siteView({ tooth: 13, status: "flagged", declared_variant: "5020" }),
    siteView({ tooth: 19, status: "flagged", declared_variant: "4030" }),
  ];
  const rows = [
    row(4),
    row(13, "attention", [ACTION]),
    row(19, "action-needed", [ACTION]),
  ];

  it("puts flagged sites first, then orders by tooth for a stable list", () => {
    expect(adjustQueue(sites, rows).map((e) => e.tooth)).toEqual([13, 19, 4]);
  });

  it("marks the clean sites optional rather than hiding them", () => {
    const clean = adjustQueue(sites, rows).find((e) => e.tooth === 4)!;
    expect(clean.flagged).toBe(false);
    expect(clean.optional).toBe(true);
  });

  it("carries the GATE'S OWN action words, never a summary of our own", () => {
    const flagged = adjustQueue(sites, rows).find((e) => e.tooth === 13)!;
    expect(flagged.reasons).toEqual([ACTION]);
  });

  it("drops sites the run never aligned — a row that can only refuse is a promise to nowhere", () => {
    const queue = adjustQueue(sites, [row(13, "attention", [ACTION])]);
    expect(queue.map((e) => e.tooth)).toEqual([13]);
  });

  it("reads no actions off a row that carries none, and invents none", () => {
    expect(gateActions(row(4))).toEqual([]);
    expect(gateActions(undefined)).toEqual([]);
    expect(gateActions({ tooth: 4 })).toEqual([]);
  });

  it("summarises by counts and says when nothing is flagged", () => {
    expect(queueSummary(adjustQueue(sites, rows))).toContain("2 of 3 sites are flagged");
    const clean = adjustQueue([sites[0]!], [row(4)]);
    expect(queueSummary(clean)).toContain("Nothing is flagged");
    expect(queueSummary([])).toContain("nothing to rework");
  });
});

/**
 * DROPPING A CAP (design flow.dc.html dropSite 1345-1354, queue row 1183-1191; gap
 * `drop-a-cap-from-adjust`). The act itself is the BFF's — a per-site WITHHOLD
 * INTENT that pre-fills the confirmation's disposition — so what is pinned here is
 * only what this app decides: where a dropped row SORTS, and what the words are
 * allowed to claim.
 */
describe("a dropped cap", () => {
  const sites = [
    siteView({ tooth: 4, status: "ready", declared_variant: "5020" }),
    siteView({
      tooth: 13,
      status: "flagged",
      declared_variant: "5020",
      withhold_intent: true,
    }),
    siteView({ tooth: 19, status: "flagged", declared_variant: "4030" }),
  ];
  const rows = [row(4), row(13, "attention", [ACTION]), row(19, "attention", [ACTION])];

  it("sorts last — below even the clean sites, whatever its rung", () => {
    // the design's own rule (1178): dropped rows sink, and the flagged-first order
    // holds among everything above them. A dropped cap is the one row the operator
    // has already finished with.
    expect(adjustQueue(sites, rows).map((e) => e.tooth)).toEqual([19, 4, 13]);
  });

  it("is still flagged, because the run still flagged it", () => {
    // dropping changes what SHIPS, never what was measured — the row keeps the
    // verdict and the gate's own words, so bringing the cap back costs no re-read
    const dropped = adjustQueue(sites, rows).find((e) => e.tooth === 13)!;
    expect(dropped.dropped).toBe(true);
    expect(dropped.flagged).toBe(true);
    expect(dropped.reasons).toEqual([ACTION]);
  });

  it("counts as dropped in the summary, and stops being counted as work", () => {
    const summary = queueSummary(adjustQueue(sites, rows));
    expect(summary).toContain("1 dropped");
  });

  it("says nothing about drops when nobody has dropped anything", () => {
    expect(queueSummary(adjustQueue([sites[0]!], [row(4)]))).not.toContain("dropped");
  });

  it("labels the act and its reversal, both as things the operator DOES", () => {
    expect(dropLabel(false)).toContain("Drop this cap");
    expect(dropLabel(true)).toContain("Bring this cap back");
  });

  it("NEVER repeats the design's 'not aligned' — post-run that is a lie", () => {
    // design 1352 logs "dropped — not aligned, not billed". The alignment already
    // ran and this act deliberately leaves the pipeline alone, so the only honest
    // half is the second one.
    for (const words of [dropLabel(true), dropLabel(false), dropNote(true),
                         dropNote(false), droppedRowWords()]) {
      expect(words).not.toContain("not aligned");
      expect(words).not.toContain("won't be aligned");
    }
  });

  it("states what a drop actually does: nothing releases, nothing is billed", () => {
    const note = dropNote(true);
    expect(note).toContain("release");
    expect(note).toContain("bill");
    expect(droppedRowWords()).toContain("released");
    expect(droppedRowWords()).toContain("billed");
  });

  it("says the CONFIRMATION is what signs it — this stage signs nothing", () => {
    // the intent is a draft; the confirmation is the act. A surface that implied
    // the drop was final would be claiming a disclosure outcome in the browser.
    expect(dropNote(true)).toContain("Deliver");
  });

  it("offers the reversal in the same breath as the drop", () => {
    expect(dropNote(false)).toContain("undone");
  });
});

describe("the panes' words on this stage", () => {
  const entry: AdjustQueueEntry = {
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
  const base = {
    site: entry,
    partMeshKnown: true,
    partError: null,
    scanError: null,
    scanEmpty: false,
    seatedPhase: "ready" as const,
    seatedError: null,
  };

  it("says which site is missing before anything else", () => {
    const notices = adjustPaneNotices({ ...base, site: null });
    expect(notices.part).toContain("pick one from the queue");
    expect(notices.scan).toContain("pick one from the queue");
    expect(notices.union).toContain("pick one from the queue");
  });

  it("names the shipped FIT, not a preview — this stage reads what was delivered", () => {
    const notices = adjustPaneNotices({ ...base, seatedPhase: "idle" });
    expect(notices.union).toBe("The shipped fit has not been read for this site yet.");
  });

  it("serves the read's own error verbatim", () => {
    const notices = adjustPaneNotices({
      ...base,
      seatedPhase: "error",
      seatedError: "HTTP 422 — tooth 13 carries no verdict from the current run",
    });
    expect(notices.union).toContain("carries no verdict");
  });

  it("a ready read shows the colouring itself, with no notice over it", () => {
    expect(adjustPaneNotices(base).union).toBeNull();
  });
});

describe("the union caption says which pose is on screen", () => {
  const payload = { preview: false } as never;
  const applied = {
    applied: true,
    detail: "rotated +1.0° about the part axis (cumulative +1.0°)",
  } as AdjustOutcomeView;

  it("before any tool, it is the run's own fit", () => {
    expect(adjustUnionCaption(payload, null)).toContain("as the run delivered it");
  });

  it("after an applied tool, it is the NEW pose and says what moved it", () => {
    expect(adjustUnionCaption(payload, applied)).toBe(
      "the fit as it stands now — rotated +1.0° about the part axis (cumulative +1.0°)",
    );
  });

  it("with nothing loaded there is no caption to write", () => {
    expect(adjustUnionCaption(null, applied)).toBeNull();
  });
});

describe("the already-optimal PASS is narrowed out of the refusal path", () => {
  function refusal(detail: unknown, status = 409): ApiResult<AdjustResultView> {
    return { kind: "error", detail: "HTTP 409", status, refusal: detail };
  }

  it("recognises the structured pass and its widen", () => {
    const pass = alreadyOptimalFrom(
      refusal({
        kind: "already_optimal",
        message: "the certified pose is already the best fit…",
        matching_diameter_mm: 0.3,
        suggested_diameter_mm: 0.6,
      }),
    );
    expect(pass).not.toBeNull();
    expect(pass!.matchingDiameterMm).toBe(0.3);
    expect(pass!.suggestedDiameterMm).toBe(0.6);
    expect(pass!.canWiden).toBe(true);
  });

  it("offers no widen at the ceiling, where the suggestion caps to the dial itself", () => {
    const pass = alreadyOptimalFrom(
      refusal({
        kind: "already_optimal",
        message: "…and this is the widest matching band the tool searches",
        matching_diameter_mm: 2.0,
        suggested_diameter_mm: 2.0,
      }),
    );
    expect(pass!.canWiden).toBe(false);
  });

  it("a real gate refusal is NOT a pass — it renders in the refusal's own tone", () => {
    expect(alreadyOptimalFrom(refusal("the rim band would leave the scan"))).toBeNull();
  });

  it("a 422 validation refusal is not a pass either", () => {
    expect(
      alreadyOptimalFrom(refusal({ kind: "already_optimal" }, 422)),
    ).toBeNull();
  });

  it("a malformed structured body falls back to the plain refusal", () => {
    expect(
      alreadyOptimalFrom(
        refusal({ kind: "already_optimal", message: "x", matching_diameter_mm: "0.3" }),
      ),
    ).toBeNull();
  });

  it("an OK result is never a pass", () => {
    expect(
      alreadyOptimalFrom({ kind: "ok", data: {} as AdjustResultView }),
    ).toBeNull();
  });
});

describe("fit by points: the drafts the operator builds", () => {
  it("a point pair asks for the part mark, then the scan mark", () => {
    let draft = newPairDraft("p1", false);
    expect(pairSlot(draft)).toBe("part");
    expect(pairPrompt(draft)).toContain("LIBRARY PART");
    draft = withPick(draft, "part", [1, 0, 1]);
    expect(pairSlot(draft)).toBe("scan");
    expect(pairPrompt(draft)).toContain("SCAN");
    draft = withPick(draft, "scan", [5, 5, 5]);
    expect(pairSlot(draft)).toBe("complete");
    expect(isComplete(draft)).toBe(true);
  });

  it("a SPAN pair asks for BOTH ends of the feature on the scan", () => {
    let draft = withPick(newPairDraft("s1", true), "part", [1, 0, 1]);
    expect(pairPrompt(draft)).toContain("ONE END");
    draft = withPick(draft, "scan", [5, 5, 5]);
    expect(pairSlot(draft)).toBe("scan-end");
    expect(pairPrompt(draft)).toContain("OTHER END");
    draft = withPick(draft, "scan", [6, 5, 5]);
    expect(isComplete(draft)).toBe(true);
    expect(pairBody(draft)).toEqual({
      part_point: [1, 0, 1],
      scan_point: [5, 5, 5],
      scan_point_end: [6, 5, 5],
    });
  });

  it("a point pair sends no span end — the wire says exactly what was clicked", () => {
    const draft = withPick(
      withPick(newPairDraft("p1", false), "part", [1, 0, 1]),
      "scan",
      [5, 5, 5],
    );
    expect(pairBody(draft)).toEqual({ part_point: [1, 0, 1], scan_point: [5, 5, 5] });
  });

  it("a click nothing is waiting for is IGNORED, never an overwrite", () => {
    // the re-click pair-integrity record: an operator act is never silently replaced
    const placed = withPick(newPairDraft("p1", false), "part", [1, 0, 1]);
    expect(withPick(placed, "part", [9, 9, 9])).toEqual(placed);
    const complete = withPick(placed, "scan", [5, 5, 5]);
    expect(withPick(complete, "scan", [7, 7, 7])).toEqual(complete);
  });

  it("Apply names what is missing rather than going quietly dead", () => {
    expect(applyBlockedReason([], null, null)).toContain("at least one complete pair");
    expect(applyBlockedReason([newPairDraft("p1", false)], null, null)).toContain(
      "at least one complete pair",
    );
    const complete = withPick(
      withPick(newPairDraft("p1", false), "part", [1, 0, 1]),
      "scan",
      [5, 5, 5],
    );
    expect(applyBlockedReason([complete], null, null)).toBeNull();
  });

  it("refuses more than the server's own cap, in the server's own number", () => {
    const complete = withPick(
      withPick(newPairDraft("p", false), "part", [1, 0, 1]),
      "scan",
      [5, 5, 5],
    );
    const many = Array.from({ length: MAX_PAIRS + 1 }, (_, i) => ({
      ...complete,
      id: `p${i}`,
    }));
    expect(applyBlockedReason(many, null, null)).toContain(`capped at ${MAX_PAIRS} pairs`);
  });

  it("each pair's line says what it is and what it still needs", () => {
    expect(pairWords(newPairDraft("p1", false), 0)).toBe(
      "1. point — waiting for the part mark",
    );
    expect(pairWords(newPairDraft("s1", true), 1)).toBe(
      "2. span — waiting for the part mark",
    );
  });
});

describe("reading what a tool produced", () => {
  it("a span shows TWO observation rows under one label — the whole point of it", () => {
    const rows = [
      { feature_id: "point-1", observation: "midpoint", residual_mm: 0.041 },
      { feature_id: "point-1", observation: "direction", residual_mm: 0.112 },
    ];
    expect(rows.map(observationWords)).toEqual([
      "point-1 · span midpoint — misses by 0.041 mm",
      "point-1 · span direction — misses by 0.112 mm",
    ]);
  });

  it("a single-click pair shows one row", () => {
    expect(
      observationWords({ feature_id: "point-1", observation: "point", residual_mm: 0.2 }),
    ).toBe("point-1 · point — misses by 0.200 mm");
  });

  it("a dropped span direction says WHY, on the row the operator is reading", () => {
    // The suites' 2026-07-28 finding: the worker wrote this sentence to the record on
    // disk and the surface showed one unexplained row. The operator spends a second
    // click specifically to buy the rotational constraint — silently handing back one
    // observation is the no-op the whole tool is built not to do.
    const note =
      "the span runs 47° off its own radius — a chord across the feature, not " +
      "along it, so its direction names no clock angle (past 30°); the averaged " +
      "midpoint still counts";
    expect(
      observationWords({
        feature_id: "point-1",
        observation: "midpoint",
        residual_mm: 0.041,
        note,
      }),
    ).toBe(`point-1 · span midpoint — misses by 0.041 mm — ${note}`);
  });

  it("a row with nothing to explain carries no dangling dash", () => {
    expect(
      observationWords({ feature_id: "point-1", observation: "midpoint", residual_mm: 0.04 }),
    ).toBe("point-1 · span midpoint — misses by 0.040 mm");
  });

  it("a measured-only outcome says so — it did not move anything", () => {
    const measured = { applied: false, detail: "best-fit at a 0.30mm…" } as AdjustOutcomeView;
    expect(outcomeWords(measured)).toContain("Measured only");
  });

  it("an adjusted site needs its confirmation again", () => {
    expect(needsReconfirm("adjusted")).toBe(true);
    expect(needsReconfirm("ready")).toBe(false);
    expect(needsReconfirm("flagged")).toBe(false);
  });
});

describe("what a rework leaves behind on the run's report", () => {
  it("joins the stale metrics in the reader's language, not the wire's", () => {
    expect(staleMetricsPhrase(["rim_agreement_mm", "guidance"])).toBe(
      "the rim agreement and the gate verdict",
    );
    expect(staleMetricsPhrase(["guidance"])).toBe("the gate verdict");
  });

  it("passes an unknown key through rather than dropping it silently", () => {
    // the BFF owns this list; a name this app has no phrasing for is still a fact
    expect(staleMetricsPhrase(["some_new_metric"])).toBe("some_new_metric");
  });

  it("nothing stale is null, so no caller renders an empty clause", () => {
    expect(staleMetricsPhrase([])).toBeNull();
  });

  it("says it at the moment of the act, not two stages later", () => {
    // FINDING E's other half: the operator learns the consequence from the act. The
    // deviation was re-measured over the new pose; these two were not.
    const applied = {
      applied: true,
      detail: "rotated +5.0°",
      stale_metrics: ["rim_agreement_mm", "guidance"],
    } as unknown as AdjustOutcomeView;
    expect(reworkWords(applied)).toContain("the rim agreement and the gate verdict");
    expect(reworkWords(applied)).toContain("re-measures");
  });

  it("a measure-only outcome changed nothing, so it left nothing behind", () => {
    const measured = {
      applied: false,
      detail: "best-fit at a 0.30mm…",
      stale_metrics: ["guidance"],
    } as unknown as AdjustOutcomeView;
    expect(reworkWords(measured)).toBeNull();
  });
});

describe("the toolbox", () => {
  it("offers exactly the plan's five tools, in its order", () => {
    expect(ADJUST_TOOLS.map((t) => t.id)).toEqual([
      "fit-by-points",
      "best-fit",
      "rotation",
      "mark-trench",
      "auto-mark",
    ]);
  });

  it("the best-fit's one-liner states the pass BEFORE the operator meets it", () => {
    const bestFit = ADJUST_TOOLS.find((t) => t.id === "best-fit")!;
    expect(bestFit.oneLiner).toContain("PASS");
  });
});

describe("auto-mark — the software proposes the part half (client 2026-07-29)", () => {
  const landmarks: LandmarkView[] = [
    { id: "notch-a", kind: "notch", point: [1.5, 0, 2], lever_arm_mm: 1.5,
      azimuth_deg: 0 },
    { id: "notch-b", kind: "notch", point: [0, 0.9, 2], lever_arm_mm: 0.9,
      azimuth_deg: 90 },
  ];

  it("turns each landmark into a draft with the PART half already filled", () => {
    const drafts = autoMarkDrafts(landmarks);
    expect(drafts).toHaveLength(2);
    expect(drafts[0]!.partPoint).toEqual([1.5, 0, 2]);
    expect(drafts[0]!.scanPoint).toBeNull();
    expect(drafts[0]!.span).toBe(false);
  });

  it("a draft with its part half filled is already past the part slot", () => {
    // pairSlot is the EXISTING pair machinery — auto-mark seeds no new state machine,
    // it only pre-fills the same PairDraft withPick already understands
    const [draft] = autoMarkDrafts(landmarks);
    expect(pairSlot(draft!)).toBe("scan");
    expect(pairPrompt(draft!)).toContain("Click the same spot on the SCAN");
  });

  it("keeps every landmark's identity distinct even across an empty proposal", () => {
    expect(autoMarkDrafts([])).toEqual([]);
  });

  it("applying a landmark draft to the wire sends the served point, untouched", () => {
    // the same pairBody the manual flow uses — no second wire encoder for this tool
    const draft = withPick(autoMarkDrafts(landmarks)[0]!, "scan", [9, 9, 9]);
    expect(pairBody(draft)).toEqual({ part_point: [1.5, 0, 2], scan_point: [9, 9, 9] });
  });

  it("names a landmark by what it is and how far out it sits", () => {
    expect(landmarkLabel(landmarks[0]!)).toBe("notch — lever arm 1.50mm");
  });

  it("traces a draft back to the landmark that seeded it", () => {
    const [draft] = autoMarkDrafts(landmarks);
    expect(autoMarkSourceLabel(draft!, landmarks)).toBe("notch — lever arm 1.50mm");
  });

  it("says nothing for a draft auto-mark did not create", () => {
    expect(autoMarkSourceLabel(newPairDraft("p1", false), landmarks)).toBeNull();
  });

  it("summarises the count and the order promise", () => {
    expect(autoMarkSummary(landmarks)).toContain("2 landmarks proposed");
    expect(autoMarkSummary(landmarks)).toContain("best lever arm first");
  });

  it("a singular landmark reads as singular, not '1 landmarks'", () => {
    expect(autoMarkSummary([landmarks[0]!])).toContain("1 landmark proposed");
  });

  it("a part with nothing to propose says so honestly rather than an empty list", () => {
    expect(autoMarkSummary([])).toContain("no rotation-defining landmarks to propose");
  });
});

describe("pairSlots — the marks a pair is made of, named with their surface", () => {
  it("a point pair is TWO marks, and says which surface each belongs on", () => {
    const draft = newPairDraft("p1", false);
    const slots = pairSlots(draft);
    expect(slots).toHaveLength(2);
    expect(slots[0]!.where).toContain("Library part");
    expect(slots[1]!.where).toContain("Scanned cap");
    // Nothing placed yet, so the FIRST is the one the next click fills.
    expect(slots.map((s) => s.placed)).toEqual([false, false]);
    expect(slots.map((s) => s.active)).toEqual([true, false]);
  });

  it("a span pair honestly shows THREE marks — that is what it costs", () => {
    expect(pairSlots(newPairDraft("p1", true))).toHaveLength(3);
  });

  it("placing the part mark ticks it and moves the arrow to the scan", () => {
    const draft = withPick(newPairDraft("p1", false), "part", [1, 2, 3]);
    const slots = pairSlots(draft);
    expect(slots.map((s) => s.placed)).toEqual([true, false]);
    expect(slots.map((s) => s.active)).toEqual([false, true]);
  });

  it("a complete pair has every mark placed and no arrow left", () => {
    const draft = withPick(
      withPick(newPairDraft("p1", false), "part", [1, 2, 3]),
      "scan",
      [4, 5, 6],
    );
    const slots = pairSlots(draft);
    expect(slots.every((s) => s.placed)).toBe(true);
    expect(slots.some((s) => s.active)).toBe(false);
  });
});

describe("withoutPick — one mark leaves, the rest of the pair stands", () => {
  const complete = () =>
    withPick(withPick(newPairDraft("p1", false), "part", [1, 2, 3]), "scan", [4, 5, 6]);

  it("clearing the part mark keeps the scan mark", () => {
    const d = withoutPick(complete(), "part");
    expect(d.partPoint).toBeNull();
    expect(d.scanPoint).toEqual([4, 5, 6]);
  });

  it("clearing the scan mark keeps the part mark", () => {
    const d = withoutPick(complete(), "scan");
    expect(d.partPoint).toEqual([1, 2, 3]);
    expect(d.scanPoint).toBeNull();
  });

  it("a span's second end is PROMOTED when the first is cleared — never a hole", () => {
    let span = newPairDraft("s1", true);
    span = withPick(span, "part", [0, 0, 0]);
    span = withPick(span, "scan", [1, 0, 0]);
    span = withPick(span, "scan", [2, 0, 0]);
    expect(span.scanPointEnd).toEqual([2, 0, 0]);

    const cleared = withoutPick(span, "scan");
    // The surviving end slides into the first slot, so the next click fills the SECOND
    // end — not a state where slot 1 is empty while slot 2 is full.
    expect(cleared.scanPoint).toEqual([2, 0, 0]);
    expect(cleared.scanPointEnd).toBeNull();
    expect(pairSlot(cleared)).toBe("scan-end");
  });

  it("the cleared mark becomes the one the next click fills", () => {
    expect(pairSlot(withoutPick(complete(), "part"))).toBe("part");
  });
});

describe("spanLeverCaution — warn before the span earns a 422", () => {
  const pose = { origin: [0, 0, 0], axis: [0, 0, 1] };
  const span = (a: number[], b: number[]) => {
    let d = newPairDraft("s1", true);
    d = withPick(d, "part", [5, 0, 0]);
    d = withPick(d, "scan", a);
    return withPick(d, "scan", b);
  };

  it("warns on a diameter through the axis — the screw-access span", () => {
    // two ends opposite each other: the midpoint lands ON the axis
    const words = spanLeverCaution(span([2, 0, 0], [-2, 0, 0]), pose);
    expect(words).not.toBeNull();
    expect(words).toContain("crosses the screw access");
    expect(words).toContain("0.5mm");
  });

  it("stays quiet on a trench spanned along its own radius", () => {
    // both ends out on the same side: the midpoint keeps a real lever arm
    expect(spanLeverCaution(span([2, 0, 0], [3, 0, 0]), pose)).toBeNull();
  });

  it("measures PERPENDICULAR to the axis — depth along it is not a lever arm", () => {
    // ends differing only in z: no in-plane arm at all, so this must warn
    expect(spanLeverCaution(span([0, 0, 1], [0, 0, -1]), pose)).not.toBeNull();
  });

  it("says nothing about a point pair, or before both ends are placed", () => {
    let point = newPairDraft("p1", false);
    point = withPick(point, "part", [5, 0, 0]);
    point = withPick(point, "scan", [0, 0, 0]);
    expect(spanLeverCaution(point, pose)).toBeNull();

    let half = newPairDraft("s2", true);
    half = withPick(half, "part", [5, 0, 0]);
    half = withPick(half, "scan", [0, 0, 0]);
    expect(spanLeverCaution(half, pose)).toBeNull();
  });

  it("says nothing when no pose is known — it never guesses at the reference", () => {
    expect(spanLeverCaution(span([2, 0, 0], [-2, 0, 0]), null)).toBeNull();
  });
});

describe("the library span — two points on the part, not one", () => {
  const libSpan = () => newPairDraft("l1", true, true);

  it("asks for the library's OTHER end before it looks at the scan", () => {
    let d = libSpan();
    expect(pairSlot(d)).toBe("part");
    d = withPick(d, "part", [2, 0, 1]);
    expect(pairSlot(d)).toBe("part-end");
    d = withPick(d, "part", [2, 1, 1]);
    expect(pairSlot(d)).toBe("scan");
  });

  it("names each library click in the prompt", () => {
    let d = withPick(libSpan(), "part", [2, 0, 1]);
    expect(pairPrompt(d)).toContain("OTHER END");
    expect(pairPrompt(d)).toContain("LIBRARY");
  });

  it("carries both part ends onto the wire", () => {
    let d = libSpan();
    d = withPick(d, "part", [2, 0, 1]);
    d = withPick(d, "part", [2, 1, 1]);
    d = withPick(d, "scan", [1, 0, 0]);
    d = withPick(d, "scan", [2, 0, 0]);
    expect(isComplete(d)).toBe(true);
    const body = pairBody(d);
    expect(body.part_point_end).toEqual([2, 1, 1]);
    expect(body.scan_point_end).toEqual([2, 0, 0]);
  });

  it("FORCES the scan span, because a bearing and a point cannot be subtracted", () => {
    // the worker refuses a library span whose scan half is a single click; a surface
    // that let the operator build one would be offering an act that can only 422
    const d = newPairDraft("l2", false, true);
    expect(d.span).toBe(true);
  });

  it("shows FOUR slots — a four-click pair that lists three is lying about itself", () => {
    // shipped broken: `pairSlots` predates the library span, so the operator placed
    // four marks against a three-row checklist and the row for the second library
    // click never appeared — there was no `undo` for it either
    const slots = pairSlots(libSpan());
    expect(slots.map((s) => s.key)).toEqual(["part", "part-end", "scan", "scan-end"]);
    expect(slots[1]!.where).toContain("Library part");
    expect(slots[1]!.label).toContain("OTHER end");
  });

  it("marks the library end placed once it is placed, so undo can reach it", () => {
    let d = withPick(libSpan(), "part", [2, 0, 1]);
    expect(pairSlots(d)[1]!.active).toBe(true);
    d = withPick(d, "part", [2, 1, 1]);
    expect(pairSlots(d)[1]!.placed).toBe(true);
  });

  it("undoes either library end, promoting the survivor like the scan side does", () => {
    let d = withPick(withPick(libSpan(), "part", [2, 0, 1]), "part", [2, 1, 1]);
    // the SECOND end alone
    expect(withoutPick(d, "part-end").partPointEnd).toBeNull();
    expect(withoutPick(d, "part-end").partPoint).toEqual([2, 0, 1]);
    // the FIRST end promotes the survivor rather than stranding it — the scan half's
    // own rule (a draft holding only an END has no slot that could fill the start)
    const undone = withoutPick(d, "part");
    expect(undone.partPoint).toEqual([2, 1, 1]);
    expect(undone.partPointEnd).toBeNull();
  });

  it("keeps the LIBRARY pane armed for the span's second click", () => {
    // without this the operator can start a library span and then find pane 1 dead —
    // the draft waits for a click no pane will accept
    const waiting = withPick(libSpan(), "part", [2, 0, 1]);
    const arming = paneArming(waiting, false);
    expect(arming.armed.library).toBe(true);
    expect(arming.armed.scan).toBe(false);
    expect(arming.hints.library).toContain("OTHER END");
  });

  it("leaves an ordinary pair exactly as it was", () => {
    const plain = newPairDraft("p1", false);
    expect(plain.partSpan).toBe(false);
    expect(pairBody(withPick(withPick(plain, "part", [2, 0, 1]), "scan", [1, 0, 0])))
      .not.toHaveProperty("part_point_end");
  });
});

describe("markLeverGuard — the server's own quantity, so the client may refuse", () => {
  const pose = { origin: [0, 0, 0], axis: [0, 0, 1] };
  // THE WHOLE POINT: the MEASURED rim centre is not the pose origin. That gap is why
  // the old guard could only caution — refusing on the approximation risked refusing a
  // span the server would have accepted.
  const clock = { rim_centre: [1, 0, 0], min_lever_mm: 0.5 };
  const span = (a: number[], b: number[]) => {
    let d = newPairDraft("s1", true);
    d = withPick(d, "part", [5, 0, 0]);
    d = withPick(d, "scan", a);
    return withPick(d, "scan", b);
  };
  const point = (p: number[]) => {
    let d = newPairDraft("p1", false);
    d = withPick(d, "part", [5, 0, 0]);
    return withPick(d, "scan", p);
  };

  it("refuses a span about the MEASURED rim centre, where the approximation was quiet", () => {
    // midpoint lands on the measured centre (lever 0) but a full 1mm from the pose
    // origin — the old caution reads 1mm and says nothing at all
    const draft = span([2, 0, 0], [0, 0, 0]);
    expect(spanLeverCaution(draft, pose)).toBeNull();
    const guard = markLeverGuard(draft, pose, clock);
    expect(guard?.kind).toBe("refusal");
    expect(guard?.message).toContain("screw access");
  });

  it("refuses a SINGLE mark on the access — the case that had no warning at all", () => {
    const guard = markLeverGuard(point([1, 0, 0]), pose, clock);
    expect(guard?.kind).toBe("refusal");
  });

  it("reads the bound off the wire, never a mirrored constant", () => {
    // 0.6mm clears the mirrored 0.5 and fails the server's own 0.8
    const guard = markLeverGuard(point([1.6, 0, 0]), pose, {
      rim_centre: [1, 0, 0],
      min_lever_mm: 0.8,
    });
    expect(guard?.kind).toBe("refusal");
    expect(guard?.message).toContain("0.8");
  });

  it("stays silent on a mark out on the coded band", () => {
    expect(markLeverGuard(point([4, 0, 0]), pose, clock)).toBeNull();
  });

  it("PROJECTS ALONG THE AXIS — depth is not a lever arm", () => {
    // THE OPERATION THAT MAKES THIS NUMBER THE SERVER'S. The worker measures in the
    // canonical xy plane; this measures perpendicular to the pose axis. A mark 5mm
    // from the rim centre but entirely ALONG the axis has NO lever arm, and a guard
    // that took the plain 3-D distance would read 5mm and wave the screw access
    // through. Real poses are tilted (the occlusal proxy runs 6.2°-42.0° off the
    // real axis), so an axis-aligned-only test proves nothing here.
    const tilted = { origin: [0, 0, 0], axis: [0, 1, 0] };
    const deep = { rim_centre: [0, 0, 0], min_lever_mm: 0.5 };
    const guard = markLeverGuard(point([0, 5, 0]), tilted, deep);
    expect(guard?.kind).toBe("refusal");
    expect(guard?.message).toContain("0.00mm");
  });

  it("degrades rather than refusing on a reference it cannot measure", () => {
    // §10-F's whole contract: never block a correction the server would take. The API
    // layer casts the response without validating, so these shapes are reachable, and
    // BOTH used to end in a refusal — one reading "NaNmm", one throwing mid-render.
    const short = { rim_centre: [1], min_lever_mm: 0.5 };
    expect(markLeverGuard(point([1, 0, 0]), pose, short)).toBeNull();
    const noBound = { rim_centre: [1, 0, 0] } as unknown as {
      rim_centre: number[];
      min_lever_mm: number;
    };
    expect(() => markLeverGuard(point([1, 0, 0]), pose, noBound)).not.toThrow();
    expect(markLeverGuard(point([1, 0, 0]), pose, noBound)).toBeNull();
  });

  it("CAUTIONS rather than refuses when the reference has not arrived", () => {
    // without the server's quantity the client has only the pose origin, and an
    // approximation may warn but must never block a correction the server would take
    const guard = markLeverGuard(span([2, 0, 0], [-2, 0, 0]), pose, null);
    expect(guard?.kind).toBe("caution");
  });
});

describe("applyBlockedReason — a local refusal blocks Apply, a caution does not", () => {
  const pose = { origin: [0, 0, 0], axis: [0, 0, 1] };
  const clock = { rim_centre: [0, 0, 0], min_lever_mm: 0.5 };
  const onAccess = () => {
    let d = newPairDraft("p1", false);
    d = withPick(d, "part", [5, 0, 0]);
    return withPick(d, "scan", [0.1, 0, 0]);
  };

  it("blocks, naming WHICH pair, when a mark cannot anchor a rotation", () => {
    const good = () => {
      let d = newPairDraft("p0", false);
      d = withPick(d, "part", [5, 0, 0]);
      return withPick(d, "scan", [4, 0, 0]);
    };
    const words = applyBlockedReason([good(), onAccess()], pose, clock);
    expect(words).not.toBeNull();
    expect(words).toContain("screw access");
    // the worker's refusal names the offending pair so the repair is one undo; a
    // blocked control that only describes the fault leaves the operator hunting for
    // which of the marks on screen it means
    expect(words).toContain("Pair 2");
  });

  it("stays live when only the approximation is available", () => {
    expect(applyBlockedReason([onAccess()], pose, null)).toBeNull();
  });
});

describe("needsReconfirmStatus — the predicate over the WIRE'S raw status", () => {
  it("is true for the adjusted rung and false for every other one", () => {
    expect(needsReconfirmStatus("adjusted")).toBe(true);
    for (const other of ["detected", "declared", "previewed", "ready", "flagged"]) {
      expect(needsReconfirmStatus(other)).toBe(false);
    }
  });

  it("is false with no site selected — nothing to re-confirm", () => {
    expect(needsReconfirmStatus(null)).toBe(false);
  });

  it("agrees with needsReconfirm, which stays the one rule", () => {
    expect(needsReconfirmStatus("adjusted")).toBe(needsReconfirm("adjusted"));
  });
});

describe("the best-fit dial's own bounds, in words", () => {
  it("names the band and the default the run itself used", () => {
    const words = diameterBandWords();
    expect(words).toContain(MIN_DIAMETER_MM.toFixed(2));
    expect(words).toContain(MAX_DIAMETER_MM.toFixed(2));
    expect(words).toContain(DEFAULT_DIAMETER_MM.toFixed(2));
  });

  it("claims nothing about THIS site's rim — that number is not on this payload", () => {
    // the design's pre-run note reads its fixture's `diamTrue`; the product's
    // `rim_agreement_mm` is a different quantity (how well the rim agreed at the
    // seat), so no sentence here may compare the dial to it
    expect(diameterBandWords()).not.toMatch(/rim/i);
  });
});

describe("the pair set's own overview — the cap, before it is exceeded", () => {
  const complete = (id: string) =>
    withPick(withPick(newPairDraft(id, false), "part", [1, 0, 1]), "scan", [5, 5, 5]);

  it("states the cap before a single pair exists", () => {
    const words = pairSetWords([]);
    expect(words).toContain(`${MAX_PAIRS}`);
    expect(words).toContain("one complete pair is enough");
  });

  it("counts the complete ones against the cap, and names the half-built ones", () => {
    const words = pairSetWords([complete("a"), newPairDraft("b", true)]);
    expect(words).toContain(`1 of ${MAX_PAIRS} pairs complete`);
    expect(words).toContain("1 still being placed");
  });

  it("at the cap it says so — the operator learns the ceiling before Apply refuses", () => {
    const full = Array.from({ length: MAX_PAIRS }, (_, i) => complete(`p${i}`));
    const words = pairSetWords(full);
    expect(words).toContain(`${MAX_PAIRS} of ${MAX_PAIRS} pairs complete`);
    expect(words).toContain("remove one before placing another");
  });
});

/**
 * ONE STATUS LINE (client live-testing 2026-08-06: "so much text ... lack of UI/UX
 * design"). `pairStatusLine` is the single sentence that replaces the drawer's three
 * overlapping ones (the hint bar, the count sentence, and the Apply placeholder) — this
 * pins WHICH of the two source sentences wins in each state, never a third wording.
 */
describe("pairStatusLine — the ONE sentence that replaces three overlapping ones", () => {
  it("with nothing placed, states the floor and the ceiling together", () => {
    expect(pairStatusLine([], null)).toBe(pairSetWords([]));
    expect(pairStatusLine([], null)).toContain("one complete pair is enough");
  });

  it("with an open draft, names the exact next click over the count", () => {
    const draft = newPairDraft("p1", false);
    expect(pairStatusLine([draft], draft)).toBe(pairPrompt(draft));
    expect(pairStatusLine([draft], draft)).toContain("LIBRARY PART");
  });

  it("with every pair complete and none open, falls back to the count, not 'start a pair'", () => {
    const complete = withPick(
      withPick(newPairDraft("p1", false), "part", [1, 0, 1]),
      "scan",
      [5, 5, 5],
    );
    expect(pairStatusLine([complete], null)).toBe(pairSetWords([complete]));
    expect(pairStatusLine([complete], null)).toContain("1 of");
  });
});

/**
 * THE VACUOUS RMS, BEFORE THE CLICK (defect cap6020-neodent-gm, 2026-08-01).
 *
 * One pair fixes the rotation exactly, so the fit it produces has nothing to
 * cross-check it against. The operator used to learn this — if at all — from an
 * outcome sentence that claimed "marks agree to 0.000mm RMS". The set the Apply
 * control is about to send says it first.
 */
describe("the one-pair caution, before the fit is applied", () => {
  const complete = (id: string) =>
    withPick(withPick(newPairDraft(id, false), "part", [1, 0, 1]), "scan", [5, 5, 5]);
  const completeSpan = (id: string) =>
    withPick(
      withPick(withPick(newPairDraft(id, true), "part", [1, 0, 1]), "scan", [5, 5, 5]),
      "scan",
      [6, 5, 5],
    );

  it("warns on exactly one complete pair, and says what it costs", () => {
    const words = crossCheckCaution([complete("a")]);
    expect(words).not.toBeNull();
    expect(words).toContain("one observation");
    expect(words).toContain("no agreement number");
  });

  it("says the act is legitimate — it is a caution, never a refusal", () => {
    // the worker deliberately allows one correspondence, and a single pair is the
    // documented answer where the automatic reader has no evidence at all
    const words = crossCheckCaution([complete("a")])!;
    expect(words.toLowerCase()).toContain("legitimate");
    // and Apply stays live: the caution and the blocker are different questions
    expect(applyBlockedReason([complete("a")], null, null)).toBeNull();
  });

  it("is silent once a second pair stands", () => {
    expect(crossCheckCaution([complete("a"), complete("b")])).toBeNull();
  });

  it("is silent with nothing placed — there is no fit to caution about yet", () => {
    expect(crossCheckCaution([])).toBeNull();
    expect(crossCheckCaution([newPairDraft("a", false)])).toBeNull();
  });

  it("does not count half-built pairs as the second one", () => {
    const words = crossCheckCaution([complete("a"), newPairDraft("b", false)]);
    expect(words).not.toBeNull();
  });

  it("a lone SPAN leads with the actionable half; the radial/chord condition folds", () => {
    // RETARGETED (client live-testing 2026-08-06: "a lot of yellow text on the span
    // the scan tool" — this caution and `markLeverGuard`'s screw-access refusal were
    // stacking to ~8 lines of amber under one pair). The physics condition — a span
    // emits its direction ONLY where the server reads it as radial; a chord across
    // the feature contributes its midpoint alone — is unchanged, just no longer
    // forced onto the always-visible sentence: `crossCheckCaution` now states only
    // what the operator does next, and `crossCheckCautionDetail` carries the
    // qualifier for a fold (AdjustStage renders it behind a `<details>`).
    const words = crossCheckCaution([completeSpan("a")])!;
    expect(words).not.toContain("radial");
    expect(words).not.toContain("one observation.");
    expect(words.toLowerCase()).toContain("second pair");

    const detail = crossCheckCautionDetail([completeSpan("a")])!;
    expect(detail).toContain("radial");
  });

  it("the fold is silent for a POINT pair — no chord/radial ambiguity to explain", () => {
    expect(crossCheckCautionDetail([complete("a")])).toBeNull();
  });

  it("both halves are silent once a second pair stands, or nothing is placed", () => {
    expect(crossCheckCautionDetail([complete("a"), complete("b")])).toBeNull();
    expect(crossCheckCautionDetail([])).toBeNull();
  });
});

describe("the flagged-exception pointer (the act lives on Deliver's row)", () => {
  it("says a flagged site can still ship, and where the act is made", () => {
    const words = flaggedExceptionWords("flagged");
    expect(words).not.toBeNull();
    expect(words).toContain("exception");
    expect(words).toContain("Deliver");
  });

  it("promises no acceptance HERE — this stage sets no status", () => {
    // AM-4 / the no-status-fields doctrine: `accepted` may never be client-set, and
    // the sentence must not imply that clicking anything on Adjust does it
    const words = flaggedExceptionWords("flagged")!;
    expect(words).toContain("nothing on this stage accepts it");
  });

  it("says nothing on a site that is not flagged, or with none selected", () => {
    for (const other of ["ready", "adjusted", "previewed", "declared", "detected"]) {
      expect(flaggedExceptionWords(other)).toBeNull();
    }
    expect(flaggedExceptionWords(null)).toBeNull();
  });
});

/**
 * THE ROW THE STRIP READS MOVED SERVER-SIDE (design review 2026-07-31).
 *
 * `adjust._fold_outcome` rewrites the run's summary row — clocking, deviation_*,
 * correspondence — on every applied tool, and nothing in the response moves
 * `run_state`. The container's run-rows effect keys off `run_state`, so without an
 * explicit signal the ALIGNMENT strip kept printing the PRE-rework numbers beside an
 * outcome panel describing the new pose: on one screen the rotation tab read the fresh
 * residual (1.2°) and the toolbar cell the stale one (+7.4°).
 */
describe("outcomeMovedTheRow — when the run's summary row must be re-read", () => {
  const okResult = (applied: boolean): ApiResult<AdjustResultView> => ({
    kind: "ok",
    data: {
      outcome: {
        tooth: 19,
        operation: "rotation",
        detail: "rotated",
        applied,
        files: [],
        clocking: { notch_shift_deg: 1.2 },
        deviation: null,
        stale_metrics: [],
        nudge: null,
        applied_delta_deg: 5,
        cumulative_deg: 5,
        stability_excess_mm: null,
        best_fit: null,
        pairs: [],
        residual_rms_mm: null,
        // a rotation produces no residual at all — "not applicable", not "unchecked"
        cross_checked: null,
        click_azimuth_deg: null,
        matched_feature_azimuth_deg: null,
      },
      pane_payload: null,
      case: {} as AdjustResultView["case"],
    },
  });

  it("an APPLIED tool moved the row — re-read it", () => {
    expect(outcomeMovedTheRow(okResult(true))).toBe(true);
  });

  it("a measure-only call moved nothing — no re-read", () => {
    expect(outcomeMovedTheRow(okResult(false))).toBe(false);
  });

  it("a refusal moved nothing — the fit on screen is the one that passed the gates", () => {
    expect(
      outcomeMovedTheRow({ kind: "error", status: 409, detail: "refused", refusal: null }),
    ).toBe(false);
  });
});

/**
 * AN ATTESTATION NEEDS ITS EVIDENCE ON SCREEN (design review 2026-07-31).
 *
 * The re-confirmation rendered off the site's RUNG alone. With the seated read failed,
 * pane 3 says "The shipped fit could not be read." while the block beside it said
 * "confirm it again over the panes on the right" with an ENABLED button — and clicking
 * it satisfied Deliver's every-site-resolved gate with an attestation whose evidence
 * was never displayed.
 */
describe("reconfirmControl — the rung offers the act, the panes qualify it", () => {
  it("offers and enables it once the shipped fit is on the panes", () => {
    expect(reconfirmControl("adjusted", "ready", true)).toEqual({
      offered: true,
      enabled: true,
      reason: null,
    });
  });

  it("offers it but refuses the click while the shipped fit could not be read", () => {
    const control = reconfirmControl("adjusted", "error", false);
    expect(control.offered).toBe(true);
    expect(control.enabled).toBe(false);
    expect(control.reason).toContain("could not be read");
  });

  it("refuses it while the read is still in flight, with the honest reason", () => {
    const control = reconfirmControl("adjusted", "loading", false);
    expect(control.enabled).toBe(false);
    expect(control.reason).toContain("reading");
  });

  it("refuses it before any read has been asked for", () => {
    const control = reconfirmControl("adjusted", "idle", false);
    expect(control.enabled).toBe(false);
    expect(control.reason).not.toBeNull();
  });

  it("a READY phase with no payload is still no evidence — the panes are blank", () => {
    expect(reconfirmControl("adjusted", "ready", false).enabled).toBe(false);
  });

  it("a site that is not on the rung is not offered the act at all", () => {
    for (const status of ["ready", "flagged", "previewed", null] as const) {
      const control = reconfirmControl(status, "ready", true);
      expect(control.offered).toBe(false);
      expect(control.enabled).toBe(false);
    }
  });
});

/**
 * THE PANES SAY WHEN THEY ARE ARMED (client 2026-07-30, re-opened by the design review
 * 2026-07-31: the props existed and the only stage that installs pick listeners never
 * passed them, so the crosshair class and the on-glass hint were dead code).
 *
 * The router is the rule: a trench click is the SCAN's while the trench is armed;
 * otherwise the open draft's next empty slot decides which pane wants a click. Every
 * other pane must stay un-armed — arming all three for the whole stage is exactly the
 * lie this control exists to stop telling.
 */
describe("paneArming — which pane wants the next click, and what it will do", () => {
  it("arms nothing when no draft is open and the trench is not armed", () => {
    const arming = paneArming(null, false);
    expect(arming.armed).toEqual({ library: false, scan: false, union: false });
    expect(arming.hints).toEqual({ library: null, scan: null, union: null });
  });

  it("arms the LIBRARY pane alone while the pair wants its part half", () => {
    const arming = paneArming(newPairDraft("p1", false), false);
    expect(arming.armed).toEqual({ library: true, scan: false, union: false });
    expect(arming.hints.library).toContain("library part");
    expect(arming.hints.scan).toBeNull();
  });

  it("arms BOTH scan panes once the part half is placed — either one may take it", () => {
    const draft = withPick(newPairDraft("p1", false), "part", [0, 0, 1]);
    const arming = paneArming(draft, false);
    expect(arming.armed).toEqual({ library: false, scan: true, union: true });
    expect(arming.hints.scan).toBe(arming.hints.union);
    expect(arming.hints.scan).not.toBeNull();
  });

  it("a span's second scan click names the OTHER END, not the same spot again", () => {
    const draft = withPick(
      withPick(newPairDraft("p1", true), "part", [0, 0, 1]),
      "scan",
      [1, 0, 0],
    );
    const arming = paneArming(draft, false);
    expect(arming.armed.scan).toBe(true);
    expect(arming.hints.scan).toContain("OTHER END");
  });

  it("a complete pair arms nothing — a click nothing is waiting for is ignored", () => {
    const draft = withPick(
      withPick(newPairDraft("p1", false), "part", [0, 0, 1]),
      "scan",
      [1, 0, 0],
    );
    expect(paneArming(draft, false).armed).toEqual({
      library: false,
      scan: false,
      union: false,
    });
  });

  it("the armed trench takes the scan panes, exactly as the pick router does", () => {
    const draft = newPairDraft("p1", false); // still waiting on its PART half
    const arming = paneArming(draft, true);
    expect(arming.armed).toEqual({ library: true, scan: true, union: true });
    expect(arming.hints.scan).toContain("cutout");
    // the part half is untouched by the trench — the router only diverts scan clicks
    expect(arming.hints.library).toContain("library part");
  });
});

/**
 * RE-PREVIEW (gap `re-preview-a-site-without-applying-a-tool`, 2026-07-31). The
 * server route is already landed and body-less; what these pin is the WORDS this
 * app puts on top of `RePreviewView` — a promise of a re-READ, never an outcome,
 * and a rendering of `changed` that never re-derives its own comparison.
 */
describe("rePreviewButtonLabel — a re-read, promised, never an outcome", () => {
  it("names the act and states no verdict", () => {
    const label = rePreviewButtonLabel();
    expect(label).toBe("Re-read this site's numbers");
    // the design prototype's own label for this control is "this will pass" — a
    // client-side verdict this app is forbidden from making (client.ts:1262-1265)
    for (const verdict of ["pass", "fail", "ready", " ok", "will pass"]) {
      expect(label.toLowerCase()).not.toContain(verdict);
    }
  });
});

describe("rePreviewWords — the SERVER's changed flag, never a local comparison", () => {
  it("changed=false renders the unchanged sentence even where previous/rederived differ", () => {
    // mutating `previous` alone must never flip the words: only `view.changed` may
    const words = rePreviewWords(
      rePreviewView({ changed: false, previous: { deviation_rms_mm: 9.9 } }),
    );
    expect(words).toContain("nothing has moved");
  });

  it("changed=true says the numbers moved and that the earlier confirmation fell", () => {
    const words = rePreviewWords(rePreviewView({ changed: true }));
    expect(words).toContain("cleared");
  });
});

describe("rePreviewRows — previous beside rederived, the server's own keys and values", () => {
  it("names a known metric in the reader's language, values verbatim", () => {
    const rows = rePreviewRows(
      rePreviewView({
        previous: { deviation_rms_mm: 0.61, deviation_p90_mm: 0.9 },
        rederived: { deviation_rms_mm: 0.43, deviation_p90_mm: 0.71 },
      }),
    );
    const rms = rows.find((r) => r.key === "deviation_rms_mm")!;
    expect(rms.label).toBe("the deviation RMS");
    expect(rms.previous).toBe(0.61);
    expect(rms.rederived).toBe(0.43);
  });

  it("passes a metric name this app has no phrasing for through, rather than dropping it", () => {
    const rows = rePreviewRows(
      rePreviewView({ previous: { some_new_metric: 1 }, rederived: { some_new_metric: 2 } }),
    );
    const row = rows.find((r) => r.key === "some_new_metric")!;
    expect(row.label).toBe("some_new_metric");
    expect(row.previous).toBe(1);
    expect(row.rederived).toBe(2);
  });
});

/**
 * THE UNVERIFIED CLOCK'S ACTIONABLE SURFACE (§10-H's "STILL OPEN" line, closed
 * 2026-08-02). `rotation_unverified` is a machine fact no tool clears — every
 * applied tool's re-read returns only the three instrument numbers
 * (`application/adjust._clocking_fields`) and the BFF merges them over the old
 * block — so the notice this function describes must never promise the flag will
 * clear. The one human backstop the domain documents is a cross-checked
 * fit-by-points, and auto-mark is the tool built to produce it.
 */
describe("unverifiedClockNotice — disclosure + routing to auto-mark, never a promise to clear", () => {
  const UNVERIFIED_ROW = {
    tooth: 29,
    clocking: {
      notch_shift_deg: 21.7,
      notch_corr: 0.475,
      notch_prominence: 0.038,
      evidence: "none",
      rotation_unverified: true,
    },
  };

  it("returns null with no row for the tooth, or a row with no clocking block at all", () => {
    expect(unverifiedClockNotice([], 29)).toBeNull();
    expect(unverifiedClockNotice([{ tooth: 30 }], 29)).toBeNull();
    expect(unverifiedClockNotice([{ tooth: 29 }], 29)).toBeNull();
    expect(unverifiedClockNotice([{ tooth: 29, clocking: {} }], 29)).toBeNull();
    expect(unverifiedClockNotice([UNVERIFIED_ROW], null)).toBeNull();
  });

  it("returns null when the run verified the rotation", () => {
    const verified = {
      tooth: 6,
      clocking: { notch_shift_deg: 1.1, evidence: "codes", rotation_unverified: false },
    };
    expect(unverifiedClockNotice([verified], 6)).toBeNull();
  });

  it("states the server's own evidence word and arms auto-mark", () => {
    const notice = unverifiedClockNotice([UNVERIFIED_ROW], 29);
    expect(notice).not.toBeNull();
    expect(notice!.facts).toContain("none");
    expect(notice!.armTool).toBe("auto-mark");
    expect(notice!.act).toContain("cross-checked");
  });

  it("never promises the flag will clear", () => {
    const notice = unverifiedClockNotice([UNVERIFIED_ROW], 29)!;
    expect(notice.act).not.toContain("will verify");
    expect(notice.act).not.toContain("marks it verified");
    expect(notice.act).not.toContain("will be verified");
    expect(notice.act).not.toContain("marks the rotation verified");
    // the disclaimer is explicit, not merely absent
    expect(notice.act).toContain("does not mark this flag verified");
  });

  it("reads the clocking block, never the stale guidance sentence", () => {
    // cap7030's own row shape: the guidance sentence is STALE on this run
    // (rework.stale_metrics includes "guidance") — the notice must not quote it
    const row = {
      tooth: 29,
      clocking: { notch_shift_deg: 21.7, evidence: "none", rotation_unverified: true },
      guidance: {
        actions: ["The cap's ROTATION could not be verified — a stale sentence"],
      },
      rework: { stale_metrics: ["guidance"] },
    };
    const notice = unverifiedClockNotice([row], 29)!;
    expect(notice.facts).not.toContain("a stale sentence");
  });
});

/** §10-AD's surfacing half: the queue names surviving measurements as RIDING the
 * next run — never promising they apply (the gates still judge; the run's own
 * receipts say what happened). */
describe("evidenceRideWords", () => {
  it("counts in the operator's grammar", () => {
    expect(evidenceRideWords(1)).toBe("1 measurement rides the next run");
    expect(evidenceRideWords(3)).toBe("3 measurements ride the next run");
  });

  it("never promises an outcome", () => {
    expect(evidenceRideWords(2)).not.toContain("will apply");
    expect(evidenceRideWords(2)).not.toContain("re-applied");
  });
});

/**
 * AUTO-MARK'S GHOSTS (§10-AI, serving the fleet report's one seed-proof misfit:
 * cap7030's unverified rotation). The operator's hard part was WHERE to click on
 * the scan — their first live attempt refused at 2.5mm RMS because point-3 named
 * a different feature. The ghost is the CURRENT pose's own claim of where each
 * placed part point sits on the scan, drawn faint; clicking where the feature
 * actually is IS the correction, and the ghost-vs-click gap is the very rotation
 * being measured. Display-only: no physics reads a ghost.
 */
describe("ghostScanMarkers — where the current pose expects the next click", () => {
  const POSE = { origin: [10, 20, 30], axis: [0, 0, 1], x_axis: [1, 0, 0] };

  it("projects a placed part point through the pose for a draft awaiting its scan click", () => {
    const draft = withPick(newPairDraft("auto-1", false), "part", [2, 3, 4]);
    const ghosts = ghostScanMarkers([draft], POSE);
    expect(ghosts).toHaveLength(1);
    // identity basis: world = origin + point
    expect(ghosts[0]!.position).toEqual([12, 23, 34]);
    expect(ghosts[0]!.label).toBe("1?");
  });

  it("uses the pose's own basis, not the world's", () => {
    // x_axis y, axis z → part x lands on world y
    const rotated = { origin: [0, 0, 0], axis: [0, 0, 1], x_axis: [0, 1, 0] };
    const draft = withPick(newPairDraft("p", false), "part", [1, 0, 0]);
    const [ghost] = ghostScanMarkers([draft], rotated);
    expect(ghost!.position[0]).toBeCloseTo(0, 10);
    expect(ghost!.position[1]).toBeCloseTo(1, 10);
  });

  it("a draft whose scan half is already placed casts no ghost — the truth is on screen", () => {
    let draft = withPick(newPairDraft("p", false), "part", [2, 3, 4]);
    draft = withPick(draft, "scan", [9, 9, 9]);
    expect(ghostScanMarkers([draft], POSE)).toEqual([]);
  });

  it("a part span's second end casts its own b-ghost", () => {
    let draft = withPick(newPairDraft("s", true, true), "part", [1, 0, 0]);
    draft = withPick(draft, "part", [2, 0, 0]);
    const ghosts = ghostScanMarkers([draft], POSE);
    expect(ghosts.map((g) => g.label)).toEqual(["1a?", "1b?"]);
  });

  it("no pose, no ghosts — a guess drawn on the glass would be an invented claim", () => {
    const draft = withPick(newPairDraft("p", false), "part", [2, 3, 4]);
    expect(ghostScanMarkers([draft], null)).toEqual([]);
    expect(
      ghostScanMarkers([draft], { origin: [0, 0], axis: [0, 0, 1], x_axis: [1, 0, 0] }),
    ).toEqual([]);
  });
});

/** §10-AD's ANSWER half (audit 2026-08-04): the run's own receipts —
 * summary.evidence_reapplied, served verbatim on the run read — say what each
 * persisted measurement actually did. The ride words are the promise; these are
 * the answer, and the client's original complaint ("rerunning ... does not take
 * effect") is only closed when the operator can SEE the answer. */
describe("the run's re-apply receipts", () => {
  const SUMMARY: Record<string, unknown> = {
    evidence_reapplied: [
      { tooth: 4, kind: "mark", applied_at: "t1", outcome: "applied",
        operation: "align-to-mark", detail: "trench matched — clocking re-read" },
      { tooth: 4, kind: "best_fit", applied_at: "t2",
        outcome: "already-optimal",
        detail: "already within the certified bound" },
      { tooth: 13, kind: "pairs", applied_at: "t3", outcome: "refused",
        detail: "the marks disagree with each other — fit refused" },
    ],
  };

  it("narrows the wire shape defensively — junk renders as no receipts", () => {
    expect(evidenceReceipts(null)).toEqual([]);
    expect(evidenceReceipts({})).toEqual([]);
    expect(evidenceReceipts({ evidence_reapplied: "junk" })).toEqual([]);
    expect(
      evidenceReceipts({ evidence_reapplied: [42, { tooth: "x" }] }),
    ).toEqual([]);
  });

  it("passes the server's receipts through, detail verbatim", () => {
    const receipts = evidenceReceipts(SUMMARY);
    expect(receipts).toHaveLength(3);
    expect(receipts[0]).toMatchObject({
      tooth: 4,
      kind: "mark",
      outcome: "applied",
      detail: "trench matched — clocking re-read",
      appliedAt: "t1",
    });
  });

  it("attaches each site's receipts to its queue entry", () => {
    const sites = [
      siteView({ tooth: 4, status: "ready", declared_variant: "5020" }),
      siteView({ tooth: 13, status: "flagged", declared_variant: "5020" }),
    ];
    const rows = [row(4), row(13, "attention", [ACTION])];
    const queue = adjustQueue(sites, rows, evidenceReceipts(SUMMARY));
    expect(queue.find((e) => e.tooth === 4)!.receipts).toHaveLength(2);
    expect(queue.find((e) => e.tooth === 13)!.receipts).toHaveLength(1);
    // callers predating the third argument still get a defined, empty list
    expect(adjustQueue(sites, rows).find((e) => e.tooth === 4)!.receipts)
      .toEqual([]);
  });

  it("sums the queue line by outcome in a fixed order, silent at zero", () => {
    expect(evidenceReceiptLine([])).toBeNull();
    const receipts = evidenceReceipts(SUMMARY);
    expect(evidenceReceiptLine(receipts.filter((r) => r.tooth === 4)))
      .toBe("this run: 1 re-applied · 1 already optimal");
    expect(evidenceReceiptLine(receipts.filter((r) => r.tooth === 13)))
      .toBe("this run: 1 refused");
  });

  it("a re-emit's carried receipts never claim 'this run' — it re-applied nothing", () => {
    // review 2026-08-04: the panel beside this line says "the source run" — the
    // queue's half must not contradict it on the same screen
    const receipts = evidenceReceipts(SUMMARY).filter((r) => r.tooth === 4);
    expect(evidenceReceiptLine(receipts, true))
      .toBe("carried forward: 1 re-applied · 1 already optimal");
    expect(evidenceReceiptLine(receipts, true)).not.toContain("this run");
  });

  it("an unknown outcome is counted under its own verbatim word, never dropped", () => {
    // the pass-through doctrine: swallowing it would blank the line while also
    // standing down the ride-words fallback
    const receipts = evidenceReceipts({
      evidence_reapplied: [
        { tooth: 4, kind: "mark", applied_at: "t1", outcome: "vetoed",
          detail: "x" },
        { tooth: 4, kind: "pairs", applied_at: "t2", outcome: "applied",
          detail: "y" },
      ],
    });
    expect(evidenceReceiptLine(receipts)).toBe("this run: 1 re-applied · 1 vetoed");
  });

  it("speaks the tools' own names and the server's outcome words", () => {
    expect(receiptKindWords("mark")).toBe("trench mark");
    expect(receiptKindWords("pairs")).toBe("point pairs");
    expect(receiptKindWords("best_fit")).toBe("best fit");
    // an unknown kind passes through verbatim — never our invention
    expect(receiptKindWords("telepathy")).toBe("telepathy");
    expect(receiptOutcomeWords("applied")).toBe("re-applied");
    expect(receiptOutcomeWords("already-optimal")).toBe("already optimal");
    expect(receiptOutcomeWords("refused")).toBe("refused");
  });

  it("titles the block for both lanes — a run's own re-apply and a re-emit's carried poses", () => {
    expect(evidenceReceiptsTitle(false)).toBe("What this run re-applied");
    expect(evidenceReceiptsTitle(true)).toContain("source run");
    expect(receiptsCarriedByReemit({ mode: "reemit-from-poses" })).toBe(true);
    expect(receiptsCarriedByReemit({ mode: "anything-else" })).toBe(false);
    expect(receiptsCarriedByReemit(null)).toBe(false);
  });

  it("the union caption stops denying re-applied work", () => {
    const payload = { preview: false } as never;
    // two receipts stand on the pose the run delivered: the caption must not
    // claim "no operator adjustment" over the operator's own re-applied marks
    expect(adjustUnionCaption(payload, null, 2)).toBe(
      "the fit as the run delivered it — it stands on 2 re-applied operator " +
        "measurements",
    );
    expect(adjustUnionCaption(payload, null, 1)).toContain(
      "1 re-applied operator measurement",
    );
    // with none re-applied the standing sentence is still the honest one
    expect(adjustUnionCaption(payload, null, 0)).toContain(
      "no operator adjustment on this site yet",
    );
  });
});
