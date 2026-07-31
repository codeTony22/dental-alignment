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
  ackRequired,
  adjustmentsWords,
  confirmBlockers,
  confirmWireBody,
  effectiveDisposition,
  evidenceSummary,
  formatBytes,
  groupArtifacts,
  isEvidenceDrift409,
  needsAcknowledgment,
  releaseBlockers,
  releaseDisclosureWords,
  releaseSteps,
  staleMetricsWords,
  termsText,
  withholdOffered,
} from "./deliver";
import {
  assuranceSite,
  assuranceView,
  caseSessionDetail,
  flaggedAssuranceSite,
} from "../testing/fixtures";

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
