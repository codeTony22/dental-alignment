/**
 * ADJUST'S PURE RULES (slice 6). The physics is the worker's and the gates are the
 * BFF's; what is pinned here is what this app actually decides — ORDER, WORDS and the
 * one NARROWING that keeps a pass from wearing a refusal's clothes.
 */
import { describe, expect, it } from "vitest";
import type { AdjustOutcomeView, AdjustResultView, ApiResult } from "../api/client";
import {
  ADJUST_TOOLS,
  MAX_PAIRS,
  adjustPaneNotices,
  adjustQueue,
  adjustUnionCaption,
  alreadyOptimalFrom,
  applyBlockedReason,
  gateActions,
  isComplete,
  needsReconfirm,
  newPairDraft,
  observationWords,
  outcomeWords,
  pairBody,
  pairPrompt,
  pairSlot,
  pairWords,
  queueSummary,
  withPick,
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

describe("the toolbox", () => {
  it("offers exactly the plan's four tools, in its order", () => {
    expect(ADJUST_TOOLS.map((t) => t.id)).toEqual([
      "fit-by-points",
      "best-fit",
      "rotation",
      "mark-trench",
    ]);
  });

  it("the best-fit's one-liner states the pass BEFORE the operator meets it", () => {
    const bestFit = ADJUST_TOOLS.find((t) => t.id === "best-fit")!;
    expect(bestFit.oneLiner).toContain("PASS");
  });
});
