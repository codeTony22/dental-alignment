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
  EMPTY_MARK,
  markOnArmMark,
  markOnArmPick,
  pickSiteAt,
  rescanNotices,
  shouldAutoDetect,
  siteCentre,
  siteEvidence,
  type MarkDraft,
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

describe("siteEvidence — what the server already knows about a site", () => {
  it("names the suggested variant and the detector's two measured numbers", () => {
    const detail = caseSessionDetail({
      sites: [siteView({ tooth: 19, suggested_variant: "5020" })],
      detection: detectionView([
        detectedProposal({ tooth_guess: 19, void_ratio: 0.42, rim_below_cusps_mm: 0.31 }),
      ]),
    });
    const facts = siteEvidence(detail, detail.sites[0]!);
    expect(facts.map((f) => f.key)).toEqual(["variant", "recess", "rim"]);
    expect(facts[0]!.text).toBe("suggested 5020");
    expect(facts[1]!.text).toBe("recess void 0.42");
    expect(facts[2]!.text).toBe("rim 0.31mm below cusps");
  });

  it("a declared variant supersedes the suggestion — the operator's act wins the row", () => {
    const detail = caseSessionDetail({
      sites: [siteView({ tooth: 19, declared_variant: "6030", suggested_variant: "5020" })],
      detection: detectionView([detectedProposal({ tooth_guess: 19 })]),
    });
    expect(siteEvidence(detail, detail.sites[0]!)[0]!.text).toBe("declared 6030");
  });

  it("no suggestion and no declaration: the row says nothing rather than guessing", () => {
    const detail = caseSessionDetail({
      sites: [siteView({ tooth: 19, suggested_variant: null })],
      detection: detectionView([]),
    });
    expect(siteEvidence(detail, detail.sites[0]!)).toEqual([]);
  });

  it("an operator-marked site the detector never proposed carries no measured numbers", () => {
    // client 2026-07-28: a hand-marked centre has no void ratio and no rim depth — the
    // detector never measured it. Showing another site's numbers here would be a lie.
    const detail = caseSessionDetail({
      sites: [siteView({ tooth: 7, suggested_variant: "5020" })],
      detection: detectionView([detectedProposal({ tooth_guess: 19 })]),
    });
    expect(siteEvidence(detail, detail.sites[0]!).map((f) => f.key)).toEqual(["variant"]);
  });
});

describe("pickSiteAt — choosing a site by clicking it on the scan", () => {
  const sites = [
    siteView({ tooth: 19, center: [0, 0, 0] }),
    siteView({ tooth: 30, center: [14, 0, 0] }),
  ];

  it("a click near a cap picks that site's tooth", () => {
    expect(pickSiteAt(sites, [1.5, 0.5, 0])).toEqual({ kind: "site", tooth: 19 });
  });

  it("a click on bare arch picks nothing rather than the least-far site", () => {
    expect(pickSiteAt([siteView({ tooth: 19, center: [0, 0, 0] })], [40, 0, 0])).toEqual({
      kind: "miss",
    });
  });

  it("sites without a usable centre cannot be picked", () => {
    expect(pickSiteAt([siteView({ tooth: 19, center: null })], [0, 0, 0])).toEqual({
      kind: "miss",
    });
    // audit 2026-07-31: a non-finite coordinate made Math.hypot NaN, and every
    // comparison against NaN is false — the site was neither skipped by the radius
    // test nor able to displace a better match. It is simply not a usable centre.
    expect(
      pickSiteAt([siteView({ tooth: 19, center: [0, Number.NaN, 0] })], [0, 0, 0]),
    ).toEqual({ kind: "miss" });
    expect(pickSiteAt([siteView({ tooth: 19, center: [0, 0] })], [0, 0, 0])).toEqual({
      kind: "miss",
    });
  });

  it("a click inside TWO caps' reach is refused as ambiguous, never resolved by nearest", () => {
    // Audit 2026-07-31. The 8mm detector minimum separation bounds CENTRE-TO-CENTRE
    // distance, not click-to-centre, so a 6mm reach genuinely can cover two caps —
    // and hand-marked sites bypass the separation filter entirely. Nearest-wins there
    // silently reframed the stage onto a tooth nobody clicked, which is exactly what
    // the radius was documented to prevent.
    const adjacent = [
      siteView({ tooth: 19, center: [0, 0, 0] }),
      siteView({ tooth: 20, center: [8, 0, 0] }),
    ];
    expect(pickSiteAt(adjacent, [5, 0, 0])).toEqual({
      kind: "ambiguous",
      teeth: [20, 19], // nearest first, so the surface can name them in order
    });
  });

  it("a cap well clear of its neighbour still resolves to one tooth", () => {
    expect(pickSiteAt(sites, [13, 0, 0])).toEqual({ kind: "site", tooth: 30 });
  });
});

describe("siteCentre — the honest 3-vector, or nothing", () => {
  it("returns the centre when the payload carries three numbers", () => {
    expect(siteCentre(siteView({ center: [1, 2, 3] }))).toEqual([1, 2, 3]);
  });

  it("null centre and short vectors are nothing, not a partial point", () => {
    expect(siteCentre(siteView({ center: null }))).toBeNull();
    expect(siteCentre(siteView({ center: [1, 2] }))).toBeNull();
  });

  it("a non-finite coordinate is not a point — the server validates marks, not curation", () => {
    // Only the operator-mark route checks 3-and-finite (case_sessions.py:1264); a
    // curated `center` is an unvalidated pass-through of the case record, so the
    // client's notion of a usable point has to carry the same check.
    expect(siteCentre(siteView({ center: [Number.NaN, 0, 0] }))).toBeNull();
    expect(siteCentre(siteView({ center: [0, Number.POSITIVE_INFINITY, 0] }))).toBeNull();
  });
});

describe("the two doors onto the stage's ONE point pick (audit 2026-07-31)", () => {
  const placed: MarkDraft = {
    armed: false,
    pending: [1, 2, 3],
    tooth: "14",
    error: null,
  };

  it("arming the site picker disarms the mark but never discards a placed centre", () => {
    // The operator placed a centre, typed its tooth, then armed the picker to check a
    // neighbour before submitting. Dropping the centre there costs a fresh hunt in 3D
    // and says nothing — while the panel offers "Discard the mark" as a deliberate act.
    expect(markOnArmPick(placed)).toEqual(placed);
    expect(markOnArmPick({ ...EMPTY_MARK, armed: true })).toEqual(EMPTY_MARK);
  });

  it("arming the mark clears a stale refusal and nothing else", () => {
    expect(markOnArmMark({ ...EMPTY_MARK, error: "tooth 14 already has a site" })).toEqual({
      ...EMPTY_MARK,
      armed: true,
    });
    expect(markOnArmMark(placed)).toEqual({ ...placed, armed: true });
  });

  it("discarding is the only thing that empties the draft", () => {
    expect(EMPTY_MARK).toEqual({ armed: false, pending: null, tooth: "", error: null });
  });
});
