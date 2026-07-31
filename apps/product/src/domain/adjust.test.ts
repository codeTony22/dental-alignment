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
  diameterBandWords,
  flaggedExceptionWords,
  gateActions,
  isComplete,
  landmarkLabel,
  needsReconfirm,
  needsReconfirmStatus,
  newPairDraft,
  pairSetWords,
  observationWords,
  outcomeWords,
  pairBody,
  pairPrompt,
  pairSlot,
  pairSlots,
  pairWords,
  queueSummary,
  spanLeverCaution,
  reworkWords,
  staleMetricsPhrase,
  withPick,
  withoutPick,
  type AdjustQueueEntry,
} from "./adjust";
import { siteView } from "../testing/fixtures";

const ACTION =
  "The cap's ROTATION could not be verified — visually check the coded features " +
  "in view 1 (top-down) before accepting.";

function row(tooth: number, level = "ready", actions: string[] = []) {
  return { tooth, guidance: { level, actions } };
}

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

describe("the panes' words on this stage", () => {
  const entry: AdjustQueueEntry = {
    tooth: 13,
    status: "flagged",
    flagged: true,
    optional: false,
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
    expect(applyBlockedReason([])).toContain("at least one complete pair");
    expect(applyBlockedReason([newPairDraft("p1", false)])).toContain(
      "at least one complete pair",
    );
    const complete = withPick(
      withPick(newPairDraft("p1", false), "part", [1, 0, 1]),
      "scan",
      [5, 5, 5],
    );
    expect(applyBlockedReason([complete])).toBeNull();
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
    expect(applyBlockedReason(many)).toContain(`capped at ${MAX_PAIRS} pairs`);
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
