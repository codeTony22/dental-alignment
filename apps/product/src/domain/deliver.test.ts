/**
 * Deliver's DISPLAY rules (plan §4 Deliver; AM-12), pure and pinned: the confirm
 * button's inertia derivation (each missing piece NAMED — flow's blockedReason
 * doctrine at the button), the acknowledgment-per-flag rule as the UI enforces it
 * locally (the BFF re-refuses it server-side either way), the wire body assembly,
 * and the 409 re-confirm detection.
 *
 * The operator-name store's tests are GONE with the store (client 2026-07-27: "WE
 * dont need operator name the checkmark is sufficient") — see the module's note.
 */
import { describe, expect, it } from "vitest";
import {
  ATTESTATION_PENDING_CAVEAT,
  CHECKOUT_SEAL_WORDS,
  ackRequired,
  attestationCounts,
  attestationText,
  casePolicyWords,
  formatMoney,
  invoiceIsPlaceholder,
  orderLines,
  orderTotal,
  payButtonLabel,
  receiptWords,
  signoffRows,
  turnaroundWords,
  acknowledgmentPolicyWords,
  adjustmentsWords,
  assuranceCounts,
  assuranceCountsWords,
  confirmBlockers,
  confirmWireBody,
  crossCheckWords,
  effectiveDisposition,
  evidenceSummary,
  formatBytes,
  groupArtifacts,
  isEvidenceDrift409,
  needsAcknowledgment,
  releaseBlockers,
  releaseDisclosureWords,
  releaseSteps,
  releasedClosingWords,
  sealedTermsHref,
  staleMetricsWords,
  termsText,
  withholdOffered,
  qcPreviews,
} from "./deliver";
import {
  assuranceSite,
  assuranceView,
  caseSessionDetail,
  flaggedAssuranceSite,
  invoiceView,
} from "../testing/fixtures";
import type { ArtifactsView, AssuranceCorrespondence } from "../api/client";

const TWO_SITES = assuranceView(); // flagged tooth 30 pinned first, ready tooth 19

describe("confirmBlockers — inert until complete, each missing piece named", () => {
  it("names ONLY the flagged rows still unacknowledged — nothing else is outstanding", () => {
    // TWO blockers were deleted, both deliberately (client 2026-07-27): the actor's
    // name (#1) and the per-row disposition (#4 — every site defaults to release).
    // Pinned as absences so neither returns as a "missing validation" fix
    const blockers = confirmBlockers(TWO_SITES, {}, []);
    expect(blockers).toEqual([
      "tooth 30 is flagged — releasing it needs its own acknowledgment",
    ]);
    expect(blockers.join(" ")).not.toContain("name");
    expect(blockers.join(" ")).not.toContain("disposition");
  });

  it("a flagged site dispositioned RELEASE needs its own acknowledgment", () => {
    const blockers = confirmBlockers(TWO_SITES, { 30: "release", 19: "release" }, []);
    expect(blockers).toEqual([
      "tooth 30 is flagged — releasing it needs its own acknowledgment",
    ]);
  });

  it("acknowledging the flag clears the last blocker", () => {
    expect(
      confirmBlockers(TWO_SITES, { 30: "release", 19: "release" }, [30]),
    ).toEqual([]);
  });

  it("a WITHHELD flagged site needs no acknowledgment — there is no release to acknowledge", () => {
    expect(
      confirmBlockers(TWO_SITES, { 30: "withhold", 19: "release" }, []),
    ).toEqual([]);
  });

  it("two flagged releases each demand their own acknowledgment (AM-12: row by row)", () => {
    const view = assuranceView({
      sites: [
        flaggedAssuranceSite({ tooth: 30 }),
        flaggedAssuranceSite({ tooth: 19 }),
      ],
    });
    const blockers = confirmBlockers(view, { 30: "release", 19: "release" }, [30]);
    expect(blockers).toEqual([
      "tooth 19 is flagged — releasing it needs its own acknowledgment",
    ]);
  });
});

describe("ackRequired — which rows render the acknowledgment tick", () => {
  it("only a flagged row dispositioned release", () => {
    const flagged = flaggedAssuranceSite();
    expect(ackRequired(flagged, "release")).toBe(true);
    expect(ackRequired(flagged, "withhold")).toBe(false);
    expect(ackRequired(flagged, undefined)).toBe(true); // undecided still shows it
    expect(ackRequired(assuranceSite(), "release")).toBe(false);
  });
});

describe("confirmWireBody — the acts, wire-shaped", () => {
  it("keys dispositions by tooth-as-string, lists acknowledged flags, states terms", () => {
    expect(confirmWireBody({ 30: "release", 19: "withhold" }, [30], true)).toEqual({
      dispositions: { "30": "release", "19": "withhold" },
      acknowledged_flags: [30],
      terms_accepted: true,
    });
  });

  it("a false acceptance rides the wire honestly too — the server is the real gate", () => {
    expect(confirmWireBody({}, [], false)).toEqual({
      dispositions: {},
      acknowledged_flags: [],
      terms_accepted: false,
    });
  });
});

describe("needsAcknowledgment — AM-12 extended to a production disclosure (plan §10-E)", () => {
  it("a flagged site needs it, same as always", () => {
    expect(needsAcknowledgment(flaggedAssuranceSite())).toBe(true);
  });

  it("a clean ready site needs nothing", () => {
    expect(needsAcknowledgment(assuranceSite())).toBe(false);
  });

  it("a READY site carrying a production_note needs it too — the flag decision", () => {
    // the note's own words are "cannot match", not "differs slightly": a
    // multi-variant case FLAGS rather than merely annotating (plan §10-E)
    const noted = assuranceSite({
      status: "ready",
      production_note:
        "single construction part shared across sites identifying 2 distinct " +
        "variants — per-variant construction parts needed",
    });
    expect(needsAcknowledgment(noted)).toBe(true);
    expect(withholdOffered(noted)).toBe(true);
    expect(ackRequired(noted, "release")).toBe(true);
    expect(ackRequired(noted, "withhold")).toBe(false);
  });

  it("the blocker names the true reason, never an unfired flag", () => {
    const noted = assuranceSite({
      tooth: 4,
      status: "ready",
      production_note: "single construction part shared across sites …",
    });
    const view = assuranceView({ sites: [noted] });
    const blockers = confirmBlockers(view, {}, []);
    expect(blockers).toEqual([
      "tooth 4 shares a construction part with a differently-declared variant" +
        " — releasing it needs its own acknowledgment",
    ]);
    expect(blockers[0]).not.toContain("is flagged");
  });
});

describe("confirmBlockers — the terms are the first blocker (plan §10-A)", () => {
  it("an unaccepted terms checkbox blocks confirming even over a clean table", () => {
    const clean = assuranceView({ sites: [assuranceSite()] });
    expect(confirmBlockers(clean, {}, [], false)).toEqual([
      "the terms — read and accept them before confirming",
    ]);
  });

  it("accepted terms plus a clean table is confirmable", () => {
    const clean = assuranceView({ sites: [assuranceSite()] });
    expect(confirmBlockers(clean, {}, [], true)).toEqual([]);
  });

  it("omitting the argument defaults to accepted — every pre-existing caller", () => {
    const clean = assuranceView({ sites: [assuranceSite()] });
    expect(confirmBlockers(clean, {}, [])).toEqual([]);
  });
});

describe("termsText — the placeholder (owed: the client's real legal text)", () => {
  it("names the case's own site count", () => {
    expect(termsText(2)).toContain("all 2 sites in this case");
    expect(termsText(1)).toContain("all 1 site in this case");
    expect(termsText(1)).not.toContain("1 sites");
  });

  it("says what accepting means", () => {
    expect(termsText(3)).toContain("I accept the alignment as shown");
    expect(termsText(3)).toContain("authorize release of the deliverables");
  });
});

describe("releaseBlockers — the chain's remaining steps, named", () => {
  it("names confirmation then payment", () => {
    const detail = caseSessionDetail();
    expect(releaseBlockers(detail.session)).toEqual([
      "the confirmation — confirm over the evidence first",
      "the payment authorization (stub)",
    ]);
  });

  it("empties when the chain is complete", () => {
    const detail = caseSessionDetail();
    expect(
      releaseBlockers({
        ...detail.session,
        confirmed: true,
        payment_authorized: true,
      }),
    ).toEqual([]);
  });
});

describe("the 409 re-confirm detection", () => {
  it("recognizes the BFF's changed-since-confirmed words on a 409", () => {
    expect(
      isEvidenceDrift409({
        kind: "error",
        status: 409,
        detail: "HTTP 409 — the case changed since it was confirmed — re-confirm over the current evidence",
      }),
    ).toBe(true);
  });

  it("any other refusal is not the re-confirm flow", () => {
    expect(
      isEvidenceDrift409({ kind: "error", status: 409, detail: "HTTP 409 — a run is already in flight" }),
    ).toBe(false);
    expect(
      isEvidenceDrift409({ kind: "error", detail: "ECONNREFUSED" }),
    ).toBe(false);
    expect(isEvidenceDrift409({ kind: "ok", data: null })).toBe(false);
  });
});

describe("the operator name store, DELETED (client 2026-07-27)", () => {
  it("the module exports no name loader or saver at all", async () => {
    // an absence test, deliberately: the three round-trip tests that used to live
    // here proved a sessionStorage name survived a reload. Nothing reads a name
    // now, and a store nobody reads is a place for a stale one to hide
    const module = await import("./deliver");
    expect(Object.keys(module)).not.toContain("loadOperator");
    expect(Object.keys(module)).not.toContain("saveOperator");
  });
});

describe("withholdOffered — only a flag can be held back (client #4)", () => {
  it("a flagged row offers the control; a clean row does not", () => {
    expect(withholdOffered(flaggedAssuranceSite())).toBe(true);
    expect(withholdOffered(assuranceSite())).toBe(false);
  });

  it("an untouched row IS released — the server's default, resolved here too", () => {
    expect(effectiveDisposition(assuranceSite(), {})).toBe("release");
    expect(effectiveDisposition(flaggedAssuranceSite(), { 30: "withhold" })).toBe(
      "withhold",
    );
  });
});

describe("evidenceSummary — the stage's compact read (client #5)", () => {
  it("one line per site in the SERVED order, carrying the three scanned numbers", () => {
    const lines = evidenceSummary(TWO_SITES);
    expect(lines.map((l) => l.tooth)).toEqual([30, 19]); // worst-first, verbatim
    expect(lines[0]).toMatchObject({ gate: "attention", flagged: true });
    expect(lines[1]!.words).toBe(
      "5020 · rim-seat, rim 0.07 mm · RMS 0.43 mm / p90 0.71 mm",
    );
  });

  it("a site missing a number says so rather than printing a bare dash", () => {
    const view = assuranceView({
      sites: [
        assuranceSite({ seat_method: null, rim_agreement_mm: null, deviation_rms_mm: null }),
      ],
    });
    expect(evidenceSummary(view)[0]!.words).toContain("seat not recorded");
    expect(evidenceSummary(view)[0]!.words).toContain("rim —");
  });

  it("carries the gate's FIRST action sentence verbatim — the run's words, never ours", () => {
    // the reason a row is flagged used to be two clicks away (the report modal, then
    // the row expand) on the very surface the confirmation seals
    const line = evidenceSummary(TWO_SITES)[0]!;
    expect(line.note).toBe(
      "The cap's ROTATION could not be verified — visually check the coded features.",
    );
    expect(line.noteFromRun).toBe(true);
  });

  it("a gate that raised no action says exactly that, in the gate's own word", () => {
    const line = evidenceSummary(TWO_SITES)[1]!;
    expect(line.note).toBe("No action was raised — this gate reads ready.");
    expect(line.noteFromRun).toBe(false);
  });

  it("an empty action string is not a sentence — the clean-row wording stands in", () => {
    const view = assuranceView({
      sites: [assuranceSite({ gate: { level: "ready", actions: ["  "] } })],
    });
    expect(evidenceSummary(view)[0]!.noteFromRun).toBe(false);
  });
});

describe("the assurance panel's own counts (design assuranceNote, flow.dc.html:1376)", () => {
  it("tallies the SERVED status words, in the order they were served", () => {
    // worst-first is the BFF's order and this app never re-sorts evidence — the
    // tally reads down the table the operator is looking at
    expect(assuranceCounts(TWO_SITES)).toEqual([
      { status: "flagged", count: 1 },
      { status: "ready", count: 1 },
    ]);
  });

  it("invents no vocabulary: a status this app has never heard of is counted by its own name", () => {
    const view = assuranceView({
      sites: [assuranceSite({ tooth: 19, status: "adjusted" })],
    });
    expect(assuranceCounts(view)).toEqual([{ status: "adjusted", count: 1 }]);
  });

  it("a row with no status is counted as unknown, never dropped from the total", () => {
    const view = assuranceView({ sites: [assuranceSite({ status: null })] });
    expect(assuranceCounts(view)).toEqual([{ status: "unknown", count: 1 }]);
  });

  it("reads in the worklist's own phrasing — count, word, slash", () => {
    expect(assuranceCountsWords(TWO_SITES)).toBe("2 sites · 1 flagged / 1 ready");
  });

  it("one site is one site — and an empty table claims no breakdown", () => {
    expect(
      assuranceCountsWords(assuranceView({ sites: [assuranceSite()] })),
    ).toBe("1 site · 1 ready");
    expect(assuranceCountsWords(assuranceView({ sites: [] }))).toBe("0 sites");
  });

  it("states no tolerance — this product has no single case tolerance number", () => {
    // the design's header ends "· tolerance 0.40 mm"; there is no such number here,
    // and every band comparison is the BFF's (AM-4). Pinned so nobody adds one.
    expect(assuranceCountsWords(TWO_SITES)).not.toContain("tolerance");
  });
});

describe("the exceptions policy, in the product's own act (not a status word)", () => {
  it("counts the rows that release only under an acknowledgment", () => {
    const words = acknowledgmentPolicyWords(TWO_SITES);
    expect(words).toContain("1 site releases only as an acknowledged exception");
    expect(words).toContain("acknowledgment rides in the confirmation");
  });

  it("plurals honestly, and counts a production-noted READY row too", () => {
    // the AM-12 rule is needsAcknowledgment, not status === flagged (plan §10-E)
    const view = assuranceView({
      sites: [
        flaggedAssuranceSite({ tooth: 30 }),
        assuranceSite({ tooth: 19, production_note: "shared construction part" }),
      ],
    });
    expect(acknowledgmentPolicyWords(view)).toContain(
      "2 sites release only as acknowledged exceptions",
    );
  });

  it("a clean table says so rather than staying silent", () => {
    const view = assuranceView({ sites: [assuranceSite()] });
    expect(acknowledgmentPolicyWords(view)).toContain("No site needs an acknowledgment");
  });

  it("a WITHHELD site is never described as releasing under an acknowledgment", () => {
    // Audit 2026-07-31. The header counted needsAcknowledgment alone, so on a table
    // where the operator withheld both flagged sites it asserted "2 sites release only
    // as acknowledged exceptions" while (a) neither row rendered a tick — ackRequired
    // is false once withheld — (b) confirmBlockers demanded nothing, and (c) the
    // server's own derive_invoice counted them as `withheld`, explicitly NOT as
    // exceptions. The whole content of the operator's act is that they do not release.
    const view = assuranceView({
      sites: [
        flaggedAssuranceSite({ tooth: 14 }),
        flaggedAssuranceSite({ tooth: 15 }),
        assuranceSite({ tooth: 19 }),
      ],
    });
    const words = acknowledgmentPolicyWords(view, { 14: "withhold", 15: "withhold" });
    expect(words).not.toContain("release only as");
    expect(words).toContain("No site releases as an acknowledged exception");
    expect(words).toContain("2 sites are withheld");
  });

  it("counts the same predicate the rows and the confirm gate stand on", () => {
    const view = assuranceView({
      sites: [flaggedAssuranceSite({ tooth: 14 }), flaggedAssuranceSite({ tooth: 15 })],
    });
    const words = acknowledgmentPolicyWords(view, { 15: "withhold" });
    expect(words).toContain("1 site releases only as an acknowledged exception");
    expect(words).toContain("1 site is withheld");
    // and the obligation it names is exactly what the gate still demands
    expect(confirmBlockers(view, { 15: "withhold" }, [])).toEqual([
      "tooth 14 is flagged — releasing it needs its own acknowledgment",
    ]);
  });

  it("with no dispositions in hand it reads exactly as it did — release is the default", () => {
    expect(acknowledgmentPolicyWords(TWO_SITES, {})).toBe(
      acknowledgmentPolicyWords(TWO_SITES),
    );
  });
});

describe("staleMetricsWords — what a reworked row's numbers still describe", () => {
  it("a row the run produced claims nothing predates it", () => {
    expect(staleMetricsWords(assuranceSite())).toBeNull();
  });

  it("names the stale numbers in the reader's language, not the wire's", () => {
    const words = staleMetricsWords(
      assuranceSite({ stale_metrics: ["rim_agreement_mm", "guidance"] }),
    );
    expect(words).toContain("the rim agreement");
    expect(words).toContain("the gate verdict");
    expect(words).not.toContain("rim_agreement_mm");
  });

  it("says what confirming does with them — the whole reason the line exists", () => {
    // FINDING E (review 2026-07-28): the confirmation SEALS this document. A doctor
    // signing a table must be able to see which of its numbers describe the fit that
    // is on the site now and which describe the one the run produced.
    const words = staleMetricsWords(assuranceSite({ stale_metrics: ["guidance"] }));
    expect(words).toContain("Confirming seals");
  });

  it("passes an unknown key through rather than dropping it silently", () => {
    // the BFF owns this list; a name this app has no phrasing for is still a fact the
    // operator must see
    expect(staleMetricsWords(assuranceSite({ stale_metrics: ["some_new_metric"] })))
      .toContain("some_new_metric");
  });
});

/**
 * THE VACUOUS RMS, ON THE ROW THE SIGNATURE COVERS (defect cap6020-neodent-gm,
 * 2026-08-01). A fit built from one pair rotated a site −50.9° and reported "marks
 * agree to 0.000mm RMS"; the site left at 0.451mm RMS / 0.745mm p90. The row this app
 * renders before a confirmation carried no trace of it.
 */
describe("crossCheckWords — whether this row's fit had anything to check it", () => {
  const withPairs = (block: Partial<AssuranceCorrespondence>) =>
    assuranceSite({
      correspondence: {
        pairs: 1,
        observations: 1,
        max_pairs: 8,
        residual_rms_mm: null,
        cross_checked: false,
        ...block,
      },
    });

  it("says nothing on a site that stands on no correspondence at all", () => {
    expect(crossCheckWords(assuranceSite({ correspondence: null }))).toBeNull();
  });

  it("says nothing on a cross-checked fit — that row's RMS speaks for itself", () => {
    expect(
      crossCheckWords(
        withPairs({ pairs: 3, observations: 5, residual_rms_mm: 0.08, cross_checked: true }),
      ),
    ).toBeNull();
  });

  it("names the fact and what confirming does with it", () => {
    const words = crossCheckWords(withPairs({}))!;
    expect(words).toContain("single observation");
    expect(words).toContain("no agreement number");
    expect(words).toContain("Confirming seals");
  });

  it("renders the SERVER's word, never a count compared in this browser", () => {
    // the observation count is on the wire, and the temptation is to read
    // `observations === 1` here. "Is this number a measurement?" is a judgment about
    // evidence, and this codebase does not make those in a browser: a server that
    // says cross_checked is silent about a one-observation row, and this must obey it.
    expect(crossCheckWords(withPairs({ cross_checked: true }))).toBeNull();
    expect(crossCheckWords(withPairs({ cross_checked: null }))).toBeNull();
  });
});

describe("adjustmentsWords — the fork, readable beside the confirm", () => {
  it("says which way the fork went, in the words Declare used", () => {
    expect(adjustmentsWords(assuranceView({ adjustments: "skip" }))).toContain(
      "Adjustments skipped",
    );
    expect(adjustmentsWords(assuranceView({ adjustments: "adjust" }))).toContain(
      "Adjustments taken up",
    );
  });

  it("an unfaced fork says nothing happened — never an implied decision", () => {
    const words = adjustmentsWords(assuranceView({ adjustments: null }));
    expect(words).toContain("never faced");
    expect(words).not.toContain("skipped");
  });

  it("every answer says the decision is part of what confirming seals", () => {
    for (const decision of ["skip", "adjust", null]) {
      expect(adjustmentsWords(assuranceView({ adjustments: decision }))).toContain(
        "part of what confirming seals",
      );
    }
  });
});

describe("releaseSteps — one progression, exactly one current step (client #6)", () => {
  const session = (over: Record<string, unknown> = {}) => ({
    ...caseSessionDetail().session,
    ...over,
  });

  it("nothing done: confirm is current, the rest wait and say what for", () => {
    const steps = releaseSteps(session());
    expect(steps.map((s) => s.state)).toEqual(["current", "waiting", "waiting"]);
    expect(steps[1]!.detail).toContain("Waiting for the confirmation");
    expect(steps[2]!.detail).toContain("confirmation and the payment");
  });

  it("a done step carries its timestamp, never a bare tick", () => {
    const steps = releaseSteps(
      session({
        confirmed: true,
        confirmation: {
          at: "2026-07-27T12:00:00+00:00",
          run_id: "r",
          evidence_sha256: "x",
          dispositions: {},
          acknowledged_flags: [],
        },
      }),
    );
    expect(steps[0]).toMatchObject({ state: "done" });
    expect(steps[0]!.detail).toContain("2026-07-27T12:00:00+00:00");
    expect(steps[1]!.state).toBe("current");
  });

  it("paid and released each become done in turn, with their own records", () => {
    const steps = releaseSteps(
      session({
        confirmed: true,
        confirmation: {
          at: "t1", run_id: "r", evidence_sha256: "x",
          dispositions: {}, acknowledged_flags: [],
        },
        payment_authorized: true,
        payment: { provider: "stub", at: "t2" },
        released: true,
        release: {
          at: "t3", run_id: "r", evidence_sha256: "x", released_teeth: [19],
        },
      }),
    );
    expect(steps.map((s) => s.state)).toEqual(["done", "done", "done"]);
    expect(steps[1]!.detail).toContain("stub");
    expect(steps[2]!.detail).toContain("t3");
  });
});

describe("releaseDisclosureWords — what the act will disclose, said first (client #6)", () => {
  it("no preview, no promise — never an invented one", () => {
    expect(releaseDisclosureWords(null)).toEqual([]);
  });

  it("a full release names the count and the sites", () => {
    const words = releaseDisclosureWords({
      file_count: 6, teeth: [4, 13], withheld_teeth: [], withheld_case_file_count: 0,
    });
    expect(words).toEqual(["Releasing discloses 6 files for tooth 4, tooth 13."]);
  });

  it("a withheld site is named AS staying open, and the case-wide hold counted", () => {
    const words = releaseDisclosureWords({
      file_count: 1, teeth: [4], withheld_teeth: [13], withheld_case_file_count: 4,
    });
    expect(words[0]).toBe("Releasing discloses 1 file for tooth 4.");
    expect(words[1]).toContain("Tooth 13 is withheld");
    expect(words[1]).toContain("the site stays open");
    expect(words[2]).toContain("4 case-wide files stay back");
  });
});

describe("the artifacts, grouped and sized (client #6)", () => {
  it("buckets by site in package order, case-wide LAST, with totals", () => {
    const groups = groupArtifacts([
      { name: "case-a-manifest.json", size_bytes: 512, tooth: null },
      { name: "case-a-19-cap.stl", size_bytes: 2048, tooth: 19 },
      { name: "case-a-30-cap.stl", size_bytes: 1024, tooth: 30 },
      { name: "case-a-19-scanbody.stl", size_bytes: 1024, tooth: 19 },
    ]);
    expect(groups.map((g) => g.tooth)).toEqual([19, 30, null]);
    expect(groups[0]!.title).toBe("Tooth 19");
    expect(groups[0]!.files.map((f) => f.name)).toEqual([
      "case-a-19-cap.stl",
      "case-a-19-scanbody.stl",
    ]);
    expect(groups[0]!.totalBytes).toBe(3072);
    expect(groups[2]!.title).toBe("Case-wide files");
  });

  it("an empty list groups into nothing, never a phantom bucket", () => {
    expect(groupArtifacts([])).toEqual([]);
  });

  it("sizes read as people read them; a missing size stays UNKNOWN, not zero", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
    expect(formatBytes(null)).toContain("size unknown");
  });
});

describe("the closing note — what actually shipped, counted from the served list", () => {
  const artifacts = (over: Partial<ArtifactsView> = {}): ArtifactsView => ({
    run_id: "20260727-120000-abc123",
    files: [],
    withheld_teeth: [],
    withheld_case_files: [],
    ...over,
  });

  it("counts the files and the sites the RELEASE actually served", () => {
    // never a client-side expectation of what should have shipped: the withheld path
    // means the two can legitimately differ, and this sentence must track the disclosure
    const words = releasedClosingWords(
      artifacts({
        files: [
          { name: "a-19-cap.stl", size_bytes: 1, tooth: 19 },
          { name: "a-19-sb.stl", size_bytes: 1, tooth: 19 },
          { name: "a-30-cap.stl", size_bytes: 1, tooth: 30 },
          { name: "a-manifest.json", size_bytes: 1, tooth: null },
        ],
      }),
    );
    expect(words).toBe(
      "Released 4 files for 2 sites, including 1 case-wide file. " +
        "Nothing was withheld — this run is closed.",
    );
  });

  it("a withheld site keeps the case OPEN and the sentence says so", () => {
    const words = releasedClosingWords(
      artifacts({
        files: [{ name: "a-19-cap.stl", size_bytes: 1, tooth: 19 }],
        withheld_teeth: [30],
      }),
    );
    expect(words).toContain("Released 1 file for 1 site.");
    expect(words).toContain("Tooth 30 stays open");
    expect(words).not.toContain("Nothing was withheld");
  });

  it("two withheld sites are both named, and nothing shipped is never called closed", () => {
    const words = releasedClosingWords(artifacts({ withheld_teeth: [30, 19] }));
    expect(words).toContain("Teeth 30, 19 stay open");
    expect(words).toContain("No files were disclosed");
    // audit 2026-07-31: "closed for the sites that shipped" over an EMPTY served list
    // named a set of sites that is empty — under-claiming is the whole point here.
    expect(words).not.toContain("this run is closed");
    expect(words).not.toContain("closed for the sites");
  });

  it("a file the run directory no longer holds is a GAP, never folded into the count", () => {
    // The BFF sets size_bytes: None for "a file the package claims but disk no longer
    // holds — visible as a gap rather than smoothed into a zero" (deliver.py:1158-1170),
    // and clicking that row 404s (fetch_artifact, deliver.py:1230). Counting the LISTED
    // rows laundered that disclosed gap back into a total and then called the run closed
    // from the very page the download fails on.
    const words = releasedClosingWords(
      artifacts({
        files: [
          { name: "a-19-cap.stl", size_bytes: 1, tooth: 19 },
          { name: "a-19-sb.stl", size_bytes: 1, tooth: 19 },
          { name: "a-30-cap.stl", size_bytes: null, tooth: 30 },
        ],
      }),
    );
    expect(words).toContain("Released 2 files for 1 site.");
    expect(words).toContain("1 listed file is no longer in the run directory");
    expect(words).not.toContain("this run is closed");
  });

  it("every listed file missing means nothing was disclosed at all", () => {
    const words = releasedClosingWords(
      artifacts({
        files: [
          { name: "a-19-cap.stl", size_bytes: null, tooth: 19 },
          { name: "a-30-cap.stl", size_bytes: null, tooth: 30 },
        ],
      }),
    );
    expect(words).toContain("No files were disclosed");
    expect(words).toContain("2 listed files are no longer in the run directory");
    expect(words).not.toContain("this run is closed");
  });

  it("a full, intact release is still the one thing allowed to say closed", () => {
    expect(
      releasedClosingWords(
        artifacts({ files: [{ name: "a-19-cap.stl", size_bytes: 4, tooth: 19 }] }),
      ),
    ).toBe("Released 1 file for 1 site. Nothing was withheld — this run is closed.");
  });
});

describe("the checkout's terms footnote (design payment modal; plan §10-A)", () => {
  it("points at the version the standing confirmation SEALED, not whatever is current", () => {
    expect(sealedTermsHref({ terms_version: "placeholder-v1" })).toBe(
      "/terms/placeholder-v1",
    );
  });

  it("falls back to the current document when nothing is sealed yet", () => {
    expect(sealedTermsHref(null)).toBe("/terms");
    expect(sealedTermsHref({ terms_version: null })).toBe("/terms");
  });

  it("escapes a version that would otherwise forge a path", () => {
    expect(sealedTermsHref({ terms_version: "v1/../admin" })).toBe(
      "/terms/v1%2F..%2Fadmin",
    );
  });

  it("says what paying does — and what it does NOT do", () => {
    expect(CHECKOUT_SEAL_WORDS).toContain("this run");
    expect(CHECKOUT_SEAL_WORDS).toContain("releasing the artifacts is a separate act");
  });
});

// --- the invoice, FORMATTED and never computed (gap invoice-on-the-surfaces) ---------

describe("formatMoney — a server amount SPLIT into its printed parts", () => {
  it("prints whole dollars and cents from integer cents", () => {
    expect(formatMoney(4800, "USD")).toBe("$48.00");
    expect(formatMoney(3205, "USD")).toBe("$32.05");
    expect(formatMoney(0, "USD")).toBe("$0.00");
  });

  it("names an unknown currency rather than inventing a symbol for it", () => {
    expect(formatMoney(4800, "EUR")).toBe("48.00 EUR");
  });
});

describe("orderLines / orderTotal — the served figures, verbatim", () => {
  it("renders every served line with its own amount, in the served order", () => {
    const lines = orderLines(invoiceView());
    expect(lines.map((l) => l.key)).toEqual([
      "released_sites",
      "exception_sites",
      "turnaround",
    ]);
    expect(lines[0]!.label).toBe("1 released site");
    expect(lines[0]!.amount).toBe("$32.00");
    expect(lines[1]!.amount).toBe("$16.00");
  });

  it("shows a per-unit rate only where the server priced one", () => {
    const lines = orderLines(invoiceView());
    expect(lines[0]!.unit).toBe("$32.00 each");
    expect(lines[2]!.unit).toBeNull(); // the turnaround line has no unit
  });

  it("an unbilled line says NOT BILLED rather than a misleading $0.00", () => {
    const lines = orderLines(
      invoiceView({
        lines: [
          {
            key: "withheld_sites",
            label: "1 withheld site, not released",
            quantity: 1,
            unit_amount_cents: null,
            amount_cents: 0,
            billed: false,
          },
        ],
      }),
    );
    expect(lines[0]!.amount).toBe("not billed");
    expect(lines[0]!.billed).toBe(false);
  });

  it("THE TOTAL IS THE SERVER'S — never the sum of the lines rendered", () => {
    // a doctored line set must not move the total: if this ever fails, someone
    // reintroduced client-side arithmetic over money
    const doctored = invoiceView({
      lines: [
        {
          key: "released_sites",
          label: "1 released site",
          quantity: 1,
          unit_amount_cents: 999_999,
          amount_cents: 999_999,
          billed: true,
        },
      ],
      total_cents: 4800,
    });
    expect(orderTotal(doctored)).toBe("$48.00");
  });
});

describe("the placeholder rates stay visible (gap invoice-on-the-surfaces)", () => {
  it("reads the placeholder state off the SERVER's own word", () => {
    expect(invoiceIsPlaceholder(invoiceView())).toBe(true);
    expect(invoiceIsPlaceholder(invoiceView({ status: "final" }))).toBe(false);
  });

  it("the turnaround line names the word and where it came from", () => {
    expect(turnaroundWords(invoiceView())).toBe(
      "Standard turnaround — the standing default.",
    );
    expect(
      turnaroundWords(
        invoiceView({ turnaround: "rush", turnaround_source: "chosen" }),
      ),
    ).toBe("Rush turnaround — chosen for this case.");
  });
});

describe("payButtonLabel — the priced button (design payLabel 1481-1482)", () => {
  it("prices the act it performs", () => {
    expect(payButtonLabel(invoiceView(), false)).toBe("Pay $48.00 (demo)");
  });

  it("says nothing about money it does not have", () => {
    expect(payButtonLabel(null, false)).toBe("Pay (demo)");
  });

  it("authorizing wins over the price — the amount already left", () => {
    expect(payButtonLabel(invoiceView(), true)).toBe("Authorizing (demo)…");
  });
});

describe("receiptWords — what was CHARGED, beside what it costs now", () => {
  it("states the charged amount, its card version and its turnaround", () => {
    const words = receiptWords({
      amount_cents: 6400,
      currency: "USD",
      rate_card_version: "placeholder-v1",
      turnaround: "rush",
      at: "2026-07-31T09:00:00+00:00",
    });
    expect(words).toContain("$64.00");
    expect(words).toContain("rush");
    expect(words).toContain("placeholder-v1");
    expect(words).toContain("2026-07-31T09:00:00+00:00");
  });

  it("a record from before amounts were kept says so instead of printing $0.00", () => {
    const words = receiptWords({
      amount_cents: null,
      currency: null,
      rate_card_version: null,
      turnaround: null,
      at: "2026-07-27T12:01:00+00:00",
    });
    expect(words).toContain("no amount was recorded");
    expect(words).not.toContain("$0.00");
  });

  it("no payment, no receipt", () => {
    expect(receiptWords(null)).toBeNull();
  });
});

// --- the attestation's enumeration (gap clinical-responsibility-attestation) ---------

describe("attestationCounts — a LOOKUP of the server's own line quantities", () => {
  it("reads each class off the line the server keyed for it", () => {
    expect(attestationCounts(invoiceView())).toEqual({
      released: 1,
      exceptions: 1,
      withheld: 0,
    });
  });

  it("an omitted line is zero — the server omits a line with nothing in it", () => {
    const clean = invoiceView({
      lines: [
        {
          key: "released_sites",
          label: "2 released sites",
          quantity: 2,
          unit_amount_cents: 3200,
          amount_cents: 6400,
          billed: true,
        },
      ],
    });
    expect(attestationCounts(clean)).toEqual({
      released: 2,
      exceptions: 0,
      withheld: 0,
    });
  });
});

describe("attestationText — the sentence names what is being released", () => {
  it("enumerates the released constructions and the acknowledged exceptions", () => {
    const words = attestationText(invoiceView(), 2);
    expect(words).toContain("2 constructions");
    expect(words).toContain("1 as an acknowledged exception");
    expect(words).toContain("clinical responsibility");
  });

  it("names the withheld sites as staying OPEN, never as merely unbilled", () => {
    const words = attestationText(
      invoiceView({
        lines: [
          {
            key: "released_sites",
            label: "1 released site",
            quantity: 1,
            unit_amount_cents: 3200,
            amount_cents: 3200,
            billed: true,
          },
          {
            key: "withheld_sites",
            label: "1 withheld site, not released",
            quantity: 1,
            unit_amount_cents: null,
            amount_cents: 0,
            billed: false,
          },
        ],
      }),
      2,
    );
    expect(words).toContain("1 withheld site");
    expect(words).toContain("stays open");
  });

  it("a case with nothing exceptional says so plainly — no empty clauses", () => {
    const words = attestationText(
      invoiceView({
        lines: [
          {
            key: "released_sites",
            label: "3 released sites",
            quantity: 3,
            unit_amount_cents: 3200,
            amount_cents: 9600,
            billed: true,
          },
        ],
      }),
      3,
    );
    expect(words).toContain("3 constructions");
    expect(words).not.toContain("exception");
    expect(words).not.toContain("withheld");
  });

  it("falls back to the site-count text when the invoice has not arrived", () => {
    // an unfetched invoice must not silently become "0 constructions"
    expect(attestationText(null, 2)).toBe(termsText(2));
  });

  it("the caveat states that withholding re-derives the sentence on confirm", () => {
    expect(ATTESTATION_PENDING_CAVEAT).toContain("Withholding a site");
    expect(ATTESTATION_PENDING_CAVEAT).toContain("re-derived");
  });
});

// --- the checkout's metric restatement (gap pay-modal-metric-signoff) ----------------

describe("signoffRows — the numbers the money is being asked for", () => {
  it("restates each site in the SERVED order, worst first", () => {
    const rows = signoffRows(TWO_SITES);
    expect(rows.map((r) => r.tooth)).toEqual([30, 19]);
  });

  it("carries the identity, the deviation and the server's own words", () => {
    const [flagged, ready] = signoffRows(TWO_SITES);
    expect(flagged!.variant).toBe("5020");
    expect(flagged!.deviation).toBe("0.43 mm");
    // THE CHIP IS THE SERVER'S WORD, never a comparison made here
    expect(flagged!.status).toBe("flagged");
    expect(flagged!.gate).toBe("attention");
    expect(flagged!.flagged).toBe(true);
    expect(ready!.flagged).toBe(false);
  });

  it("an unmeasured deviation stays a dash — never a zero", () => {
    const rows = signoffRows(
      assuranceView({ sites: [assuranceSite({ deviation_rms_mm: null })] }),
    );
    expect(rows[0]!.deviation).toBe("—");
  });

  it("an undeclared site says so rather than printing an empty cell", () => {
    const rows = signoffRows(
      assuranceView({ sites: [assuranceSite({ declared_variant: null })] }),
    );
    expect(rows[0]!.variant).toBe("no cap declared");
  });
});

describe("the sign-off row's two chips (2026-07-31)", () => {
  it("drops the gate chip when it would only repeat the status", () => {
    // Seen on screen: a site whose status and gate level both read "ready"
    // rendered "ready ready" to someone about to pay, which reads as a bug.
    const rows = signoffRows(
      assuranceView({
        sites: [assuranceSite({ tooth: 29, status: "ready", gate: { level: "ready", actions: [] } })],
      }),
    );
    expect(rows[0]!.status).toBe("ready");
    expect(rows[0]!.gate).toBeNull();
  });

  it("keeps it where the gate says something the status does not", () => {
    // The divergence is the whole reason the second chip exists: the ladder says
    // where the site stands, the acceptance catalog says what it thinks of it.
    const rows = signoffRows(
      assuranceView({
        sites: [assuranceSite({ tooth: 29, status: "ready", gate: { level: "advisory", actions: [] } })],
      }),
    );
    expect(rows[0]!.gate).toBe("advisory");
  });
});


describe("casePolicyWords — the design's toleranceLine, minus the tolerance", () => {
  it("states the relief and the turnaround, each with its source", () => {
    const words = casePolicyWords(caseSessionDetail().choices);
    expect(words).toContain("relief 0.20 mm");
    expect(words).toContain("standard turnaround");
  });

  it("NEVER prints a case tolerance — no such number exists in this product", () => {
    // the design's line reads "Case tolerance 0.40 mm · …"; every band comparison
    // here belongs to the acceptance catalog and is made server-side, per metric
    expect(casePolicyWords(caseSessionDetail().choices)).not.toContain("tolerance");
  });

  it("an unset relief is stated as unset, not as 0.00 mm", () => {
    const choices = caseSessionDetail().choices;
    const words = casePolicyWords({
      ...choices,
      effective_relief: { value: null, source: "none" },
    });
    expect(words).toContain("relief not set");
    expect(words).not.toContain("0.00 mm");
  });
});

// --- ONE resolved disposition, everywhere (audit 2026-07-31) --------------------------

/** A CLEAN, READY site the operator dropped at Adjust — the exact row that used to
 *  render the literal word "released" on the screen that signs it withheld. */
function droppedCleanSite() {
  return assuranceSite({ tooth: 4, status: "ready", withhold_intent: true });
}

describe("the dropped cap reaches the row it is signed over", () => {
  it("resolves to withhold with no local act at all — the server's own precedence", () => {
    // body → draft → release, exactly as confirm_case resolves it. Before this the
    // browser resolved an untouched row straight to "release" while the server
    // resolved the SAME row to "withhold", so one screen said both.
    expect(effectiveDisposition(droppedCleanSite(), {})).toBe("withhold");
    expect(effectiveDisposition(assuranceSite(), {})).toBe("release");
  });

  it("an explicit act on this screen still outranks the draft, both ways", () => {
    expect(effectiveDisposition(droppedCleanSite(), { 4: "release" })).toBe("release");
    expect(effectiveDisposition(assuranceSite({ tooth: 4 }), { 4: "withhold" })).toBe(
      "withhold",
    );
  });

  it("offers the control on the dropped row, so there is a way back from it", () => {
    // the one-way door: the control was gated on needsAcknowledgment alone, so a
    // clean dropped site had no `release` button — the reversal existed only on Adjust
    expect(withholdOffered(droppedCleanSite(), {})).toBe(true);
    expect(withholdOffered(assuranceSite(), {})).toBe(false);
    expect(withholdOffered(assuranceSite({ tooth: 4 }), { 4: "withhold" })).toBe(true);
  });

  it("the policy header stops claiming every row releases as it stands", () => {
    const view = assuranceView({ sites: [droppedCleanSite()] });
    const words = acknowledgmentPolicyWords(view, {});
    expect(words).not.toContain("every row here releases as it stands");
    expect(words).toContain("withheld");
  });

  it("demands no acknowledgment for a flagged row already headed for withhold", () => {
    const view = assuranceView({
      sites: [flaggedAssuranceSite({ withhold_intent: true })],
    });
    expect(confirmBlockers(view, {}, [])).toEqual([]);
  });

  it("the caveat no longer claims the counts are the CONFIRMED dispositions only", () => {
    // false whenever _billing_dispositions takes its draft branch — which is the
    // whole pre-confirmation stretch of the flow
    expect(ATTESTATION_PENDING_CAVEAT).not.toContain("actually confirmed");
    expect(ATTESTATION_PENDING_CAVEAT).toContain("dropped");
  });
});

describe("signoffRows — the checkout's row must classify what it charges for", () => {
  it("marks the withheld site the invoice on the same dialog says is not billed", () => {
    const rows = signoffRows(assuranceView({ sites: [droppedCleanSite()] }));
    expect(rows[0]!.disposition).toBe("withhold");
  });

  it("carries the production note — the whole reason the row is an exception", () => {
    const note =
      "single construction part shared across sites identifying 2 distinct " +
      "variants — per-variant construction parts needed";
    const rows = signoffRows(
      assuranceView({
        sites: [assuranceSite({ tooth: 19, status: "ready", production_note: note })],
      }),
    );
    expect(rows[0]!.productionNote).toBe(note);
  });

  it("flags on needsAcknowledgment, not on the ladder rung", () => {
    // the divergent row: the run left the rung at "ready", the BFF pins it first,
    // demands its acknowledgment and bills it at HALF rate. Rendering it as an
    // unremarkable clean row left "1 acknowledged exception, at half rate"
    // attributable to nothing on screen.
    const rows = signoffRows(
      assuranceView({
        sites: [
          assuranceSite({ tooth: 19, status: "ready", production_note: "shared part" }),
        ],
      }),
    );
    expect(rows[0]!.status).toBe("ready");
    expect(rows[0]!.flagged).toBe(true);
  });
});

describe("qcPreviews — the three main artifacts, previewed on the page (client 2026-08-01)", () => {
  it("labels each of the run's three QC images by what it shows, tooth first", () => {
    // "show the 3 main artifacts as a preview in the Deliver Page, below the open
    // full report button" — the run's own pictures of the fit: the alignment
    // proof, the clock view, the deviation map. Filenames are the SERVER's list
    // verbatim; only the human label is derived, from the suffix the worker's own
    // writer uses.
    const rows = qcPreviews(
      assuranceView({
        sites: [
          assuranceSite({
            tooth: 29,
            qc_images: [
              "case-a-29-alignment-proof.png",
              "case-a-29-clockview.png",
              "case-a-29-deviation.png",
            ],
          }),
        ],
      }),
    );
    expect(rows).toEqual([
      { tooth: 29, filename: "case-a-29-alignment-proof.png", label: "Alignment proof" },
      { tooth: 29, filename: "case-a-29-clockview.png", label: "Clock view" },
      { tooth: 29, filename: "case-a-29-deviation.png", label: "Deviation map" },
    ]);
  });

  it("keeps the assurance's own worst-first site order", () => {
    const rows = qcPreviews(
      assuranceView({
        sites: [
          assuranceSite({ tooth: 30, qc_images: ["c-30-deviation.png"] }),
          assuranceSite({ tooth: 19, qc_images: ["c-19-deviation.png"] }),
        ],
      }),
    );
    expect(rows.map((r) => r.tooth)).toEqual([30, 19]);
  });

  it("a filename the labeller does not recognise keeps the server's name verbatim", () => {
    const rows = qcPreviews(
      assuranceView({
        sites: [assuranceSite({ tooth: 29, qc_images: ["case-a-29-seat-check.png"] })],
      }),
    );
    expect(rows[0]!.label).toBe("case-a-29-seat-check.png");
  });

  it("no QC images means no previews — never a placeholder card", () => {
    const rows = qcPreviews(
      assuranceView({ sites: [assuranceSite({ tooth: 29, qc_images: [] })] }),
    );
    expect(rows).toEqual([]);
  });
});
