/**
 * Intake's pure rules (plan §4 slice 4): the auto-fire decision, the rescan banner's
 * contents, the marker set, the choice-document assembly, the ceiling readout. All
 * display/act logic — the verdicts themselves are the BFF's and arrive in the payload.
 */
import { describe, expect, it } from "vitest";
import {
  captureChipLabel,
  ceilingReadouts,
  choicesUpdateFrom,
  constructionOptions,
  detectionMarkers,
  rescanNotices,
  shouldAutoDetect,
} from "./intake";
import {
  captureAssessment,
  caseSessionDetail,
  detectedProposal,
  detectionView,
  rescanAssessment,
  siteView,
} from "../testing/fixtures";

describe("shouldAutoDetect — fire once, keyed on session facts", () => {
  it("fires for an undetected case this mount has not fired for", () => {
    expect(
      shouldAutoDetect({ caseId: "a", detectionDone: false, alreadyFiredFor: null }),
    ).toBe(true);
  });

  it("never fires when detection is already done — the demo's stage-routing lesson", () => {
    expect(
      shouldAutoDetect({ caseId: "a", detectionDone: true, alreadyFiredFor: null }),
    ).toBe(false);
  });

  it("never re-fires for the same case in the same mount (no render-loop refiring)", () => {
    expect(
      shouldAutoDetect({ caseId: "a", detectionDone: false, alreadyFiredFor: "a" }),
    ).toBe(false);
  });

  it("a DIFFERENT case re-arms the decision", () => {
    expect(
      shouldAutoDetect({ caseId: "b", detectionDone: false, alreadyFiredFor: "a" }),
    ).toBe(true);
  });
});

describe("rescanNotices — the chair-side banner's contents", () => {
  it("empty when every verdict is pass/marginal — no banner, chips only", () => {
    const detail = caseSessionDetail({
      sites: [siteView({ capture: captureAssessment({ verdict: "marginal" }) })],
      detection: detectionView(),
    });
    expect(rescanNotices(detail)).toEqual([]);
  });

  it("a rescan-grade site is named by tooth with the worker's own sentence", () => {
    const detail = caseSessionDetail({
      sites: [
        siteView({ tooth: 19, capture: rescanAssessment("Only 31% of the rim arc.") }),
        siteView({ tooth: 30, capture: captureAssessment() }),
      ],
    });
    expect(rescanNotices(detail)).toEqual([
      { label: "Tooth 19", message: "Only 31% of the rim arc." },
    ]);
  });

  it("a rescan-grade proposal matched to a listed site is not repeated", () => {
    const detail = caseSessionDetail({
      sites: [siteView({ tooth: 19, capture: rescanAssessment("Rim starved.") })],
      detection: detectionView([
        detectedProposal({
          tooth_guess: 19,
          capture: rescanAssessment("Rim starved."),
        }),
      ]),
    });
    expect(rescanNotices(detail)).toHaveLength(1);
  });

  it("an unmatched rescan-grade proposal still surfaces — no verdict is buried", () => {
    const detail = caseSessionDetail({
      sites: [],
      detection: detectionView([
        detectedProposal({
          tooth_guess: null,
          capture: rescanAssessment("Code band unreadable."),
        }),
      ]),
    });
    expect(rescanNotices(detail)).toEqual([
      {
        label: "Detected site (no tooth assigned yet)",
        message: "Code band unreadable.",
      },
    ]);
  });
});

describe("captureChipLabel", () => {
  // Parity fix (review finding 4): the demo's exact words — "RESCAN" shouts by design
  // (the one verdict where continuing wastes marks), pass/marginal stay chip-quiet.
  it("wears the demo's words per verdict, and the honest not-assessed", () => {
    expect(captureChipLabel(captureAssessment())).toBe("capture ✓");
    expect(captureChipLabel(captureAssessment({ verdict: "marginal" }))).toBe(
      "capture marginal",
    );
    expect(captureChipLabel(captureAssessment({ verdict: "rescan" }))).toBe("RESCAN");
    expect(captureChipLabel(null)).toBe("not assessed");
  });
});

describe("detectionMarkers — what the 3D stage rings", () => {
  it("marks every proposal, and curated sites the detector missed", () => {
    const detail = caseSessionDetail({
      sites: [
        siteView({ tooth: 19, center: [1, 2, 3] }),
        siteView({ tooth: 30, center: [9, 9, 9] }), // no proposal guessed 30
      ],
      detection: detectionView([
        detectedProposal({ tooth_guess: 19, center: [1.1, 2.1, 3.1] }),
      ]),
    });
    expect(detectionMarkers(detail)).toEqual([
      { center: [1.1, 2.1, 3.1], radiusMm: 2.6 },
      { center: [9, 9, 9], radiusMm: 2.6 },
    ]);
  });

  it("before detection: curated sites still ring — the stage never goes blank", () => {
    const detail = caseSessionDetail({ detection: null });
    expect(detectionMarkers(detail)).toHaveLength(2);
  });

  it("a site without a usable centre yields no marker rather than a wrong one", () => {
    const detail = caseSessionDetail({
      sites: [siteView({ center: null })],
      detection: detectionView([]),
    });
    expect(detectionMarkers(detail)).toEqual([]);
  });
});

describe("choicesUpdateFrom — one change makes the whole panel explicit", () => {
  // the derivation has ONE home, server-side (client 2026-07-27): the panel
  // renders the BFF's effective values and submits exactly what it shows
  const detail = caseSessionDetail({
    case: {
      id: "case-a",
      doctor: "Dr. Rivera",
      jaw: "lower",
      scan_filename: "scan.stl",
      suggested_model: "conical-4x4",
      suggested_construction: "dess/conical-scanbody.stl",
    },
    choices: {
      construction_path: null,
      jaw: null,
      gingival_offset_mm: null,
      gingival_offset_default_mm: 0.2,
      effective_construction: {
        value: "dess/conical-scanbody.stl",
        source: "suggested",
      },
      effective_jaw: { value: "lower", source: "suggested" },
      effective_relief: { value: 0.2, source: "default" },
      complete: true,
    },
  });

  it("an unchanged field carries the server's effective value", () => {
    expect(choicesUpdateFrom(detail, { jaw: "upper" })).toEqual({
      construction_path: "dess/conical-scanbody.stl", // the case's suggestion
      jaw: "upper",
      gingival_offset_mm: 0.2, // the standing default
    });
  });

  it("a persisted choice beats the pre-fill (the BFF attributes it 'chosen')", () => {
    const chosen = caseSessionDetail({
      ...detail,
      choices: {
        construction_path: "atlantis/other.stl",
        jaw: "upper",
        gingival_offset_mm: 0.1,
        gingival_offset_default_mm: 0.2,
        effective_construction: { value: "atlantis/other.stl", source: "chosen" },
        effective_jaw: { value: "upper", source: "chosen" },
        effective_relief: { value: 0.1, source: "chosen" },
        complete: true,
      },
    });
    expect(choicesUpdateFrom(chosen, { gingival_offset_mm: 0.05 })).toEqual({
      construction_path: "atlantis/other.stl",
      jaw: "upper",
      gingival_offset_mm: 0.05,
    });
  });

  it("with no suggestion and no choice, construction stays honestly null", () => {
    const bare = caseSessionDetail();
    expect(choicesUpdateFrom(bare, { jaw: "lower" }).construction_path).toBeNull();
  });
});

describe("constructionOptions — worker catalog rows, defensively typed", () => {
  it("keeps rows with a string path_id and drops the rest", () => {
    const detail = caseSessionDetail({
      catalog: {
        groups: [],
        constructions: [
          { path_id: "dess/a.stl", label: "dess — a" },
          { path_id: 42, label: "broken row" },
          { label: "no id at all" },
        ],
      },
    });
    expect(constructionOptions(detail)).toEqual([
      { path_id: "dess/a.stl", label: "dess — a" },
    ]);
  });
});

describe("ceilingReadouts — the relief ask beside its measured ceiling", () => {
  const ceilingRow = {
    variant: "5020",
    construction_path: "dess/a.stl",
    model: "conical-4x4",
    max_safe_mm: 0.13,
    requested_default_mm: 0.2,
    default_is_safe: false,
    limited_by: "wall",
    wall_mm_at_zero: 0.6,
    wall_mm_at_default: null,
    shippable_at_zero: true,
    min_wall_rule_mm: 0.4,
    searched_to_mm: 0.5,
    note: "ceilings below the default",
    error: null,
  };

  it("an ask above the ceiling is named — cut at the ceiling, not an error", () => {
    const detail = caseSessionDetail({ relief_ceilings: [ceilingRow] });
    const [readout] = ceilingReadouts(detail, 0.2);
    expect(readout!.exceeded).toBe(true);
    expect(readout!.line).toContain("ceiling 0.13mm");
    expect(readout!.line).toContain("limited by wall");
    expect(readout!.line).toContain("cut at the ceiling");
  });

  it("an ask under the ceiling reads plainly", () => {
    const detail = caseSessionDetail({ relief_ceilings: [ceilingRow] });
    const [readout] = ceilingReadouts(detail, 0.1);
    expect(readout!.exceeded).toBe(false);
    expect(readout!.line).not.toContain("cut at the ceiling");
  });

  it("no chosen relief measures the default ask — what the run would use", () => {
    const detail = caseSessionDetail({ relief_ceilings: [ceilingRow] });
    const [readout] = ceilingReadouts(detail, null);
    expect(readout!.exceeded).toBe(true); // default 0.2 > ceiling 0.13
  });

  it("an error row states the refusal instead of a number", () => {
    const detail = caseSessionDetail({
      relief_ceilings: [
        { ...ceilingRow, max_safe_mm: null, error: "unknown variant '9999'" },
      ],
    });
    const [readout] = ceilingReadouts(detail, null);
    expect(readout!.line).toContain("ceiling unavailable");
    expect(readout!.line).toContain("unknown variant '9999'");
    expect(readout!.exceeded).toBe(false);
  });
});
