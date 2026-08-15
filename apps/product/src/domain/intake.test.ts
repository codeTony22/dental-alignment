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
  defaultToothForMark,
  detectionMarkers,
  discriminatorEvidenceSentence,
  curveHonestySentence,
  EMPTY_MARK,
  markOnArmMark,
  markOnArmPick,
  markOnPlace,
  markPlacedWords,
  pickSiteAt,
  remarkRetiresSomething,
  remarkWords,
  rescanNotices,
  shouldAutoDetect,
  siteCentre,
  detectorDisagreement,
  adoptableProposals,
  openingSiteFor,
  sitePickerOffered,
  siteEvidence,
  type MarkDraft,
  OFF_SCAN_MISS_WORDS,
  turnaroundPillLabel,
  MIN_RIM_POINTS,
  MAX_RIM_POINTS,
  canFinishRimPoints,
  rimPointsCountWords,
  rimPointsPlacedWords,
  borderClickDisagreementWords,
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
  it("rings each SITE at the centre it actually stands on, not the raw proposal", () => {
    /* THE PRECEDENCE FLIPPED (client 2026-08-01). The marker used to draw the
       proposal's centre wherever a proposal guessed the tooth — so after the
       operator RE-MARKED a bad detector centre, the stage kept ringing the wrong
       point while the server, the run and the invoice all stood on the correction.
       SiteView.center is already the server's own resolution (the operator's mark,
       else the case record): the stage draws what the run will use. */
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
      { center: [1, 2, 3], radiusMm: 2.6 },
      { center: [9, 9, 9], radiusMm: 2.6 },
    ]);
  });

  it("rings an unclaimed candidate ONLY when its capture verdict is pass", () => {
    /* Client 2026-08-01, over a stage ringing four dots: "we just need to mark the
       proper healing cap we will work on, just mark when you are highly confident."
       On the case in their screenshot, THREE of the four rings were unclaimed
       candidates whose own capture gate said "rescan" — the gate's calibrated word
       for a capture it does not trust. The confidence word is the SERVER'S
       (capture.verdict, the calibrated capture gate), never a threshold invented
       here: pass rings, marginal and rescan stay off the stage and live in the
       unassigned-proposals panel line instead. */
    const detail = caseSessionDetail({
      sites: [siteView({ tooth: 19, center: [1, 2, 3] })],
      detection: detectionView([
        detectedProposal({ tooth_guess: 19, center: [1.1, 2.1, 3.1] }),
        detectedProposal({
          tooth_guess: null,
          center: [5, 5, 5],
          capture: { verdict: "pass", rim_z_mm: 4.0, checks: [] },
        }),
        detectedProposal({
          tooth_guess: null,
          center: [6, 6, 6],
          capture: { verdict: "rescan", rim_z_mm: 3.1, checks: [] },
        }),
        detectedProposal({
          tooth_guess: null,
          center: [7, 7, 7],
          capture: { verdict: "marginal", rim_z_mm: 5.0, checks: [] },
        }),
      ]),
    });
    expect(detectionMarkers(detail)).toEqual([
      { center: [1, 2, 3], radiusMm: 2.6 },
      { center: [5, 5, 5], radiusMm: 2.6 },
    ]);
  });

  it("an unclaimed candidate with NO capture assessment does not ring — absence is not confidence", () => {
    const detail = caseSessionDetail({
      sites: [],
      detection: detectionView([
        detectedProposal({ tooth_guess: null, center: [5, 5, 5], capture: undefined }),
      ]),
    });
    expect(detectionMarkers(detail)).toEqual([]);
  });

  it("a curated SITE always rings, whatever its capture said — it is the work", () => {
    const detail = caseSessionDetail({
      sites: [siteView({ tooth: 29, center: [2, 2, 2] })],
      detection: detectionView([
        detectedProposal({
          tooth_guess: 29,
          center: [2.1, 2.1, 2.1],
          capture: { verdict: "marginal", rim_z_mm: 5.0, checks: [] },
        }),
      ]),
    });
    expect(detectionMarkers(detail)).toEqual([{ center: [2, 2, 2], radiusMm: 2.6 }]);
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
      turnaround: null,
    });
  });

  it("CARRIES THE TURNAROUND, so one panel cannot un-choose another's rush", () => {
    /* PUT semantics, stated on the wire type itself (api/client.ts): a write that
       omits a field un-chooses it. This helper omitted `turnaround` entirely while
       LibraryStage's own write preserves it — so the two surfaces disagreed about one
       field, and an Intake choice would have silently reverted a rush to standard.
       Latent rather than live only because no control sets a rush yet; it is money-
       adjacent, and the next person to add those chips would have shipped the defect
       with them. */
    const rushed = caseSessionDetail({
      ...detail,
      choices: { ...detail.choices, turnaround: "rush" },
    });
    expect(choicesUpdateFrom(rushed, { jaw: "upper" }).turnaround).toBe("rush");
    // ...and an explicit change still wins over the standing value
    expect(choicesUpdateFrom(rushed, { turnaround: "standard" }).turnaround)
      .toBe("standard");
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
      turnaround: null,
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
          { path_id: "dess/a.stl", label: "dess — a", vendor: "dess" },
          { path_id: 42, label: "broken row" },
          { label: "no id at all" },
        ],
      },
    });
    expect(constructionOptions(detail)).toEqual([
      { path_id: "dess/a.stl", label: "dess — a", vendor: "dess", mesh_url: null },
    ]);
  });

  // Deliver's own copy of this picker (client 2026-08-01) groups by vendor — this
  // pins the field it reads off the SAME rows rather than a second catalog reader.
  it("carries the vendor along, honestly unknown when the row does not name one", () => {
    const detail = caseSessionDetail({
      catalog: {
        groups: [],
        constructions: [
          { path_id: "dess/a.stl", label: "dess — a", vendor: "dess" },
          { path_id: "b.stl", label: "no vendor field" },
        ],
      },
    });
    expect(constructionOptions(detail)).toEqual([
      { path_id: "dess/a.stl", label: "dess — a", vendor: "dess", mesh_url: null },
      { path_id: "b.stl", label: "no vendor field", vendor: "unknown vendor", mesh_url: null },
    ]);
  });

  // The unrun-part preview's one input (§10-M2's "natural next slice", 2026-08-02):
  // the row's own SERVED mesh_url, kept verbatim — never assembled client-side,
  // the same posture domain/declare.ts's variantMeshUrl already states for caps.
  it("keeps a string mesh_url, and nulls a missing or non-string one", () => {
    const detail = caseSessionDetail({
      catalog: {
        groups: [],
        constructions: [
          {
            path_id: "dess/a.stl",
            label: "dess — a",
            vendor: "dess",
            mesh_url: "/api/constructions/dess/a.stl/mesh",
          },
          { path_id: "b.stl", label: "no mesh_url field", vendor: "dess" },
          { path_id: "c.stl", label: "broken mesh_url", vendor: "dess", mesh_url: 7 },
        ],
      },
    });
    expect(constructionOptions(detail).map((o) => o.mesh_url)).toEqual([
      "/api/constructions/dess/a.stl/mesh",
      null,
      null,
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

  it("a MEASURED suggestion says so (client escalation 2026-08-09), not 'suggested'", () => {
    const detail = caseSessionDetail({
      sites: [
        siteView({
          tooth: 19,
          suggested_variant: "5020",
          suggested_variant_source: "measured",
        }),
      ],
      detection: detectionView([detectedProposal({ tooth_guess: 19 })]),
    });
    expect(siteEvidence(detail, detail.sites[0]!)[0]!.text).toBe("measured 5020");
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

describe("discriminatorEvidenceSentence — the detector's WHY, served since 488cf75 (pipeline 1a)", () => {
  it("composes the sentence from both served maps, mm to 1 decimal, ratio to 2", () => {
    const detail = caseSessionDetail({
      sites: [siteView({ tooth: 19 })],
      detection: detectionView([], {
        site_rim_below_cusps_mm: { "19": 5.94 },
        site_void_ratio: { "19": 0.314 },
      }),
    });
    expect(discriminatorEvidenceSentence(detail, detail.sites[0]!)).toBe(
      "found by its rim ring: 5.9mm below the cusp line, core/ring density 0.31",
    );
  });

  it("no detection record at all is honest absence, not a crash", () => {
    const detail = caseSessionDetail({
      sites: [siteView({ tooth: 19 })],
      detection: null,
    });
    expect(discriminatorEvidenceSentence(detail, detail.sites[0]!)).toBeNull();
  });

  it("a record predating the fields (both maps absent from the payload) is honest absence too", () => {
    const detail = caseSessionDetail({
      sites: [siteView({ tooth: 19 })],
      detection: detectionView([]),
    });
    expect(discriminatorEvidenceSentence(detail, detail.sites[0]!)).toBeNull();
  });

  it("EITHER value missing — a hand-marked site — is no sentence, never one built from a zero", () => {
    const detail = caseSessionDetail({
      sites: [siteView({ tooth: 19 })],
      detection: detectionView([], {
        site_rim_below_cusps_mm: { "19": 5.9 },
        site_void_ratio: { "19": null },
      }),
    });
    expect(discriminatorEvidenceSentence(detail, detail.sites[0]!)).toBeNull();
  });

  it("a different tooth's evidence never leaks onto this site's sentence", () => {
    const detail = caseSessionDetail({
      sites: [siteView({ tooth: 19 })],
      detection: detectionView([], {
        site_rim_below_cusps_mm: { "30": 5.9 },
        site_void_ratio: { "30": 0.31 },
      }),
    });
    expect(discriminatorEvidenceSentence(detail, detail.sites[0]!)).toBeNull();
  });
});

describe("curveHonestySentence — density prior + DP gap, never zeros for absence (P4.1)", () => {
  it("says density prior off when the served bool is false — False is a measurement", () => {
    const detail = caseSessionDetail({
      sites: [siteView({ tooth: 19 })],
      detection: detectionView([], { site_density_prior_used: { "19": false } }),
    });
    expect(curveHonestySentence(detail, detail.sites[0]!)).toBe("density prior off");
  });

  it("says density prior used when the served bool is true", () => {
    const detail = caseSessionDetail({
      sites: [siteView({ tooth: 19 })],
      detection: detectionView([], { site_density_prior_used: { "19": true } }),
    });
    expect(curveHonestySentence(detail, detail.sites[0]!)).toBe("density prior used");
  });

  it("a missing or null prior is honest absence, never 'off' invented from a gap", () => {
    const missing = caseSessionDetail({
      sites: [siteView({ tooth: 19 })],
      detection: detectionView([]),
    });
    expect(curveHonestySentence(missing, missing.sites[0]!)).toBeNull();
    const nulled = caseSessionDetail({
      sites: [siteView({ tooth: 19 })],
      detection: detectionView([], { site_density_prior_used: { "19": null } }),
    });
    expect(curveHonestySentence(nulled, nulled.sites[0]!)).toBeNull();
  });

  it("a real 0 DP gap is a measurement; a null gap is no clause", () => {
    const zero = caseSessionDetail({
      sites: [siteView({ tooth: 19 })],
      detection: detectionView([], { site_dp_gap_fraction: { "19": 0 } }),
    });
    expect(curveHonestySentence(zero, zero.sites[0]!)).toBe(
      "rim DP inferred across 0% of bearings",
    );
    const absent = caseSessionDetail({
      sites: [siteView({ tooth: 19 })],
      detection: detectionView([], { site_dp_gap_fraction: { "19": null } }),
    });
    expect(curveHonestySentence(absent, absent.sites[0]!)).toBeNull();
  });

  it("summarises the weakest finite bearing margin; empty or null is absence", () => {
    const present = caseSessionDetail({
      sites: [siteView({ tooth: 19 })],
      detection: detectionView([], {
        site_bearing_margin: { "19": [0.4, 0.05, 0.9] },
      }),
    });
    expect(curveHonestySentence(present, present.sites[0]!)).toBe(
      "weakest DP margin 0.05",
    );
    const empty = caseSessionDetail({
      sites: [siteView({ tooth: 19 })],
      detection: detectionView([], { site_bearing_margin: { "19": [] } }),
    });
    expect(curveHonestySentence(empty, empty.sites[0]!)).toBeNull();
    const nulled = caseSessionDetail({
      sites: [siteView({ tooth: 19 })],
      detection: detectionView([], { site_bearing_margin: { "19": null } }),
    });
    expect(curveHonestySentence(nulled, nulled.sites[0]!)).toBeNull();
  });

  it("joins the clauses that exist; a different tooth never leaks", () => {
    const detail = caseSessionDetail({
      sites: [siteView({ tooth: 19 })],
      detection: detectionView([], {
        site_density_prior_used: { "19": false, "30": true },
        site_dp_gap_fraction: { "19": 0.18 },
      }),
    });
    expect(curveHonestySentence(detail, detail.sites[0]!)).toBe(
      "density prior off · rim DP inferred across 18% of bearings",
    );
  });
});

describe("detectorDisagreement — the centre on screen vs the one the detector measured", () => {
  const detail = (siteCentre: number[] | null, proposals: number[][]) =>
    ({
      sites: [siteView({ tooth: 29, center: siteCentre })],
      detection: {
        proposals: proposals.map((c) => ({ center: c, tooth_guess: 29 })),
      },
    }) as never;

  it("says nothing when the two agree inside the operator's own click scatter", () => {
    expect(detectorDisagreement(detail([10, 0, 0], [[10.3, 0, 0]]), 29)).toBeNull();
  });

  it("reports the distance when they disagree by more than click noise", () => {
    // cap7030's real numbers: the curated seed is a FROZEN COPY of an old proposal
    // (its own sites.json says "centre = top proposal"), and today's detector lands
    // 7x closer to the cap's axis. The operator was shown the stale one.
    const found = detectorDisagreement(detail([10, 0, 0], [[11.74, 0, 0]]), 29);
    expect(found).not.toBeNull();
    expect(found!.mm).toBeCloseTo(1.74, 2);
    expect(found!.detected).toEqual([11.74, 0, 0]);
  });

  it("says nothing when the detector proposed nothing for that tooth", () => {
    expect(detectorDisagreement(detail([10, 0, 0], []), 29)).toBeNull();
  });

  it("says nothing when the site has no centre to compare", () => {
    expect(detectorDisagreement(detail(null, [[11.74, 0, 0]]), 29)).toBeNull();
  });

  it("compares against the NEAREST proposal, never an unrelated cap", () => {
    const found = detectorDisagreement(
      detail([10, 0, 0], [[40, 0, 0], [11.74, 0, 0]]),
      29,
    );
    expect(found!.mm).toBeCloseTo(1.74, 2);
  });

  it("an UNGUESSED proposal beyond the pick radius is another cap — silence (review 2026-08-04)", () => {
    // cap7020's real shape: the only proposal near enough to minimize distance
    // belonged to a DIFFERENT cap 9mm away. The one-click adopt commits this
    // point, so a global-minimum match would move the tooth onto its neighbour.
    const other = {
      sites: [siteView({ tooth: 3, center: [10, 0, 0] })],
      detection: { proposals: [{ center: [19.04, 0, 0], tooth_guess: null }] },
    } as never;
    expect(detectorDisagreement(other, 3)).toBeNull();
  });

  it("a proposal GUESSED for this tooth may disagree by more than the radius", () => {
    // the guess is the detector's own claim of identity — a large disagreement
    // there is exactly the finding the disclosure exists to surface
    const guessed = {
      sites: [siteView({ tooth: 3, center: [10, 0, 0] })],
      detection: { proposals: [{ center: [19.04, 0, 0], tooth_guess: 3 }] },
    } as never;
    expect(detectorDisagreement(guessed, 3)!.mm).toBeCloseTo(9.04, 2);
  });
});

/**
 * ADOPTING A DETECTED CAP (client 2026-08-04, the uploaded-arch deadlock: the
 * detector found the cap, no site carried it, Declare needs a site to open, and
 * the panel promised "Declare assigns teeth" — an act Declare never had).
 */
describe("adoptableProposals — detected caps no site carries yet", () => {
  it("offers a tooth-less proposal with the detector's own centre and facts", () => {
    const detail = caseSessionDetail({
      sites: [],
      detection: detectionView([
        detectedProposal({
          tooth_guess: null,
          center: [4.0, 5.0, 6.0],
          void_ratio: 0.47,
          rim_below_cusps_mm: 5.7,
        }),
      ]),
    });
    expect(adoptableProposals(detail)).toEqual([
      {
        index: 0,
        center: [4.0, 5.0, 6.0],
        facts: "recess void 0.47 · rim 5.70mm below cusps",
      },
    ]);
  });

  it("a proposal WITH a tooth guess is not adoptable — it has a name already", () => {
    const detail = caseSessionDetail({
      sites: [],
      detection: detectionView([detectedProposal({ tooth_guess: 30 })]),
    });
    expect(adoptableProposals(detail)).toEqual([]);
  });

  it("a proposal within the pick radius of an existing site IS that site", () => {
    // either the detector re-found a curated cap, or the operator already
    // adopted this one — offering it again would mint a duplicate site
    const detail = caseSessionDetail({
      sites: [siteView({ tooth: 3, center: [4.0, 5.0, 6.0] })],
      detection: detectionView([
        detectedProposal({ tooth_guess: null, center: [4.2, 5.1, 6.0] }),
      ]),
    });
    expect(adoptableProposals(detail)).toEqual([]);
  });

  it("adopting is possible on a case with no detection record at all — empty, no throw", () => {
    expect(adoptableProposals(caseSessionDetail({ detection: null }))).toEqual([]);
  });
});

/**
 * WHICH SITE THE STAGE OPENS ON (client 2026-08-04, reported as "Intake needs the
 * ability to re-center the cap that was selected … missing feature"). The act was
 * built; it renders only for the ACTIVE site, and the stage opened with none —
 * so the page offered no way in, and told a single-site case its site was "already
 * the active one" while its only row read aria-pressed="false".
 */
describe("openingSiteFor — the stage opens on a site, not on nothing", () => {
  const site = (tooth: number, centre: number[] | null) =>
    siteView({ tooth, center: centre });

  it("opens on the only site there is — where the re-mark control lives", () => {
    expect(openingSiteFor([site(29, [1, 2, 3])])).toBe(29);
  });

  it("opens on the FIRST site carrying a centre, skipping one that has none", () => {
    // selecting frames the scan on the site; a centreless site cannot be framed,
    // so opening on it would put the stage in a state its own words call impossible
    expect(openingSiteFor([site(4, null), site(13, [1, 2, 3]), site(19, [4, 5, 6])]))
      .toBe(13);
  });

  it("opens on nothing when nothing has a centre — honest over a dead selection", () => {
    expect(openingSiteFor([site(4, null), site(13, null)])).toBeNull();
    expect(openingSiteFor([])).toBeNull();
  });
});

describe("sitePickerOffered — a picker with one candidate is a dead control", () => {
  const site = (tooth: number, centre: number[] | null) =>
    siteView({ tooth, center: centre });

  it("is not offered when only one site could ever be picked", () => {
    // the client's report: the button armed a pick whose only possible outcome was
    // re-selecting the site already selected. A control that cannot change anything
    // is worse than absent — it reads as broken.
    const offered = sitePickerOffered([site(29, [1, 2, 3])]);
    expect(offered.offered).toBe(false);
    expect(offered.why).toContain("only one");
  });

  it("is not offered when no site carries a centre to pick by", () => {
    const offered = sitePickerOffered([site(29, null), site(30, null)]);
    expect(offered.offered).toBe(false);
    expect(offered.why).toContain("centre");
  });

  it("IS offered as soon as two sites can be told apart on the scan", () => {
    const offered = sitePickerOffered([site(29, [1, 2, 3]), site(30, [9, 9, 9])]);
    expect(offered.offered).toBe(true);
    expect(offered.why).toBeNull();
  });

  it("counts only the sites that a click could actually resolve to", () => {
    // one centred, one not: still nothing to choose between
    expect(sitePickerOffered([site(29, [1, 2, 3]), site(30, null)]).offered).toBe(false);
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
    source: null,
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
    expect(EMPTY_MARK).toEqual({
      armed: false,
      pending: null,
      tooth: "",
      source: null,
      error: null,
    });
  });
});

describe("the off-scan miss (client 2026-08-01: 'buttons are not working')", () => {
  it("says the pick is STILL armed — a miss is an attempt, not a cancellation", () => {
    expect(OFF_SCAN_MISS_WORDS).toContain("Still armed");
    expect(OFF_SCAN_MISS_WORDS).toContain("click the scan surface");
  });

  it("claims no radius — the sky has no distance to a site", () => {
    // the on-scan miss names SITE_PICK_RADIUS_MM; this one must not, because the
    // click resolved no point to measure from
    expect(OFF_SCAN_MISS_WORDS).not.toContain("mm");
  });
});

describe("re-marking an existing site's centre (client 2026-08-01, the tooth-29 gap)", () => {
  describe("remarkRetiresSomething — the blast radius, judged BEFORE the click is armed", () => {
    it("nothing to retire on a fresh site with no case run", () => {
      const detail = caseSessionDetail({ sites: [siteView({ tooth: 4, status: "detected" })] });
      expect(remarkRetiresSomething(siteView({ tooth: 4, status: "detected" }), detail)).toBe(
        false,
      );
    });

    it("still nothing once declared but not yet previewed", () => {
      const detail = caseSessionDetail({ sites: [siteView({ tooth: 4, status: "declared" })] });
      expect(remarkRetiresSomething(siteView({ tooth: 4, status: "declared" }), detail)).toBe(
        false,
      );
    });

    it("a preview or a review is something to retire", () => {
      const detail = caseSessionDetail();
      for (const rung of ["previewed", "ready", "flagged", "adjusted"] as const) {
        expect(
          remarkRetiresSomething(siteView({ tooth: 4, status: rung }), detail),
        ).toBe(true);
      }
    });

    it("a case-wide run is something to retire even for an undeclared site", () => {
      // the run is cropped around EVERY site's centre, not just the one moving —
      // it falls the instant any site's centre changes, so the words must warn
      // even about a site that itself never previewed
      const detail = caseSessionDetail({
        session: { ...caseSessionDetail().session, run_state: "done" },
      });
      expect(
        remarkRetiresSomething(siteView({ tooth: 4, status: "detected" }), detail),
      ).toBe(true);
    });
  });

  describe("remarkWords — the promise made BEFORE the pick is armed", () => {
    it("names the tooth and everything the BFF's boundary actually retires", () => {
      const words = remarkWords(29);
      expect(words).toContain("29");
      expect(words).toContain("retires");
      expect(words).toContain("preview");
      expect(words).toContain("review");
      expect(words).toContain("current run");
      expect(words).toContain("anything signed over it");
    });
  });
});

/**
 * THE RIM BORDER-POINTS INTAKE AID (§10-AL, task #33). The bounds are the BFF's own
 * RimPointsIn floor/ceiling (3..12), mirrored client-side so a refusal is never the
 * first the operator hears of the shape.
 */
describe("canFinishRimPoints / MIN_RIM_POINTS / MAX_RIM_POINTS — the BFF's own bound, mirrored", () => {
  it("the bound is exactly 3..12 — the BFF's RimPointsIn floor/ceiling", () => {
    expect(MIN_RIM_POINTS).toBe(3);
    expect(MAX_RIM_POINTS).toBe(12);
  });

  it("refuses below the floor and above the ceiling", () => {
    expect(canFinishRimPoints(0)).toBe(false);
    expect(canFinishRimPoints(2)).toBe(false);
    expect(canFinishRimPoints(13)).toBe(false);
  });

  it("accepts the floor, the ceiling, and everything between", () => {
    expect(canFinishRimPoints(3)).toBe(true);
    expect(canFinishRimPoints(7)).toBe(true);
    expect(canFinishRimPoints(12)).toBe(true);
  });
});

describe("rimPointsCountWords — the live prompt while a session is armed", () => {
  it("zero states the whole bound, not a bare instruction", () => {
    const words = rimPointsCountWords(0);
    expect(words).toContain("3");
    expect(words).toContain("12");
    expect(words).toContain("border");
  });

  it("below the floor names how many more are needed", () => {
    expect(rimPointsCountWords(1)).toContain("2 more");
    expect(rimPointsCountWords(2)).toContain("1 more");
  });

  it("at or past the ceiling says so — the maximum, not a silent stop", () => {
    expect(rimPointsCountWords(12)).toContain("maximum");
  });

  it("between the floor and the ceiling, Finish is offered", () => {
    expect(rimPointsCountWords(5)).toContain("Finish");
  });
});

describe("rimPointsPlacedWords — the standing-session row words (task #33 item 4)", () => {
  it("states the count exactly as the task's own wording", () => {
    expect(rimPointsPlacedWords(6)).toBe("6 rim points placed");
  });
});

describe("borderClickDisagreementWords — the run's own leave-one-out reading, said", () => {
  it("states the figure to two decimals with its own words, not a bare number", () => {
    const words = borderClickDisagreementWords(0.734);
    expect(words).toContain("0.73");
    expect(words).toContain("disagree");
  });
});

/**
 * THE TURNAROUND PILL'S WORDS (§10-AB.4). The money is the SERVED per-site unit —
 * bff.pricing's own cents, never a figure this app holds — and the label formats it,
 * nothing more. The comp's "24 h" / "4 h" lead times have no source and are absent.
 */
describe("turnaroundPillLabel — the served unit, formatted and nothing more", () => {
  it("prints whole dollars without cents noise", () => {
    expect(
      turnaroundPillLabel({ value: "standard", unit_amount_cents: 3200, currency: "USD" }),
    ).toBe("standard · $32/site");
  });

  it("keeps cents when the card carries them", () => {
    expect(
      turnaroundPillLabel({ value: "rush", unit_amount_cents: 4850, currency: "USD" }),
    ).toBe("rush · $48.50/site");
  });

  it("spells a non-USD currency by its code rather than guessing a symbol", () => {
    expect(
      turnaroundPillLabel({ value: "standard", unit_amount_cents: 3200, currency: "EUR" }),
    ).toBe("standard · 32 EUR/site");
  });

  it("never invents the comp's lead times", () => {
    const label = turnaroundPillLabel({
      value: "standard",
      unit_amount_cents: 3200,
      currency: "USD",
    });
    expect(label).not.toContain("24 h");
    expect(label).not.toContain("h ·");
  });
});

/* THE MARK NAMES ITS OWN TOOTH (client 2026-08-06, the arch upload case: "the tool
 * needs to let me mark it without asking me for which tooth"). The question stays
 * answerable — the input remains editable — but it stops BLOCKING: the placed mark
 * pre-fills the best available label. Provenance is honest: a covering detector
 * guess is the detector's; a free label says it is one, because on an upload with
 * no anchors any number is bookkeeping, not anatomy. */
describe("defaultToothForMark — the pre-filled label, provenance named", () => {
  const CENTER = [10, 0, 0] as const;

  it("a covering proposal's tooth guess wins, named as the detector's", () => {
    const d = defaultToothForMark({
      sites: [siteView({ tooth: 3 })],
      proposals: [detectedProposal({ tooth_guess: 12, center: [12, 0, 0] })],
      center: CENTER,
      jaw: "upper",
    });
    expect(d).toEqual({ tooth: 12, source: "detector" });
  });

  it("a proposal beyond the pick radius is another cap — its guess does not speak", () => {
    const d = defaultToothForMark({
      sites: [],
      proposals: [detectedProposal({ tooth_guess: 12, center: [19, 0, 0] })],
      center: CENTER,
      jaw: "upper",
    });
    expect(d).toEqual({ tooth: 1, source: "free-label" });
  });

  it("a guess already sitting on a site cannot be handed out twice", () => {
    const d = defaultToothForMark({
      sites: [siteView({ tooth: 12 })],
      proposals: [detectedProposal({ tooth_guess: 12, center: [12, 0, 0] })],
      center: CENTER,
      jaw: "upper",
    });
    expect(d).toEqual({ tooth: 1, source: "free-label" });
  });

  it("the free label is the jaw's next unoccupied number — upper counts 1-16, lower 17-32", () => {
    const upper = defaultToothForMark({
      sites: [siteView({ tooth: 1 }), siteView({ tooth: 2 })],
      proposals: [],
      center: CENTER,
      jaw: "upper",
    });
    expect(upper).toEqual({ tooth: 3, source: "free-label" });
    const lower = defaultToothForMark({
      sites: [],
      proposals: [],
      center: CENTER,
      jaw: "lower",
    });
    expect(lower).toEqual({ tooth: 17, source: "free-label" });
  });

  it("an unknown jaw still offers a label from the whole range; a full jaw offers none", () => {
    expect(
      defaultToothForMark({ sites: [], proposals: [], center: CENTER, jaw: null }),
    ).toEqual({ tooth: 1, source: "free-label" });
    const all = Array.from({ length: 16 }, (_, i) => siteView({ tooth: i + 1 }));
    expect(
      defaultToothForMark({ sites: all, proposals: [], center: CENTER, jaw: "upper" }),
    ).toBeNull();
  });
});

describe("markOnPlace — placing the centre fills the label without clobbering a typed one", () => {
  it("pre-fills an empty tooth and disarms", () => {
    const placed = markOnPlace(
      { ...EMPTY_MARK, armed: true },
      [1, 2, 3],
      { tooth: 12, source: "detector" },
    );
    expect(placed.pending).toEqual([1, 2, 3]);
    expect(placed.armed).toBe(false);
    expect(placed.tooth).toBe("12");
  });

  it("a tooth the operator already typed stands — their word beats the default", () => {
    const placed = markOnPlace(
      { ...EMPTY_MARK, armed: true, tooth: "9" },
      [1, 2, 3],
      { tooth: 12, source: "detector" },
    );
    expect(placed.tooth).toBe("9");
  });

  it("no default leaves the question as it was", () => {
    const placed = markOnPlace({ ...EMPTY_MARK, armed: true }, [1, 2, 3], null);
    expect(placed.tooth).toBe("");
  });
});

describe("markPlacedWords — the prompt says where the label came from", () => {
  it("names the detector, the free label, or asks as before", () => {
    expect(markPlacedWords("detector")).toContain("detector");
    expect(markPlacedWords("free-label")).toContain("free");
    expect(markPlacedWords("free-label")).toContain("edit");
    expect(markPlacedWords(null)).toBe("Centre placed. Which tooth is it?");
  });
});
