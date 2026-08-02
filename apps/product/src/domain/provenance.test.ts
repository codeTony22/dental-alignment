/**
 * THE PURE RULES BEHIND THE WORKSPACE'S PROVENANCE POPOVER. Pinned here, not in the
 * component test, because these are exactly the places a client-side "helpful"
 * shortcut would smuggle in the comp's forbidden arithmetic (deviation()/verdict()/
 * tolerance, flow.dc.html 1363-1372) — every assertion below is about a WORD or a
 * COUNT the server already published, never a comparison this app performs.
 */
import { describe, expect, it } from "vitest";
import {
  acceptanceAbsenceWords,
  bandChipClass,
  isMissingMetric,
  isStaleMetric,
  logWindowWords,
  staleSummaryWords,
  thresholdWords,
} from "./provenance";
import { siteAcceptanceMetric } from "../testing/fixtures";

describe("bandChipClass — the SERVER's word wears the tone, never a number", () => {
  it("maps the three catalog bands to their existing chips", () => {
    expect(bandChipClass("pass")).toBe("chip chip--band-pass");
    expect(bandChipClass("review")).toBe("chip chip--band-review");
    expect(bandChipClass("fail")).toBe("chip chip--band-fail");
  });

  it("falls back to the neutral chip for anything else, INCLUDING the rollup's own 'missing'", () => {
    expect(bandChipClass("missing")).toBe("chip chip--band-missing");
    expect(bandChipClass("unmeasured")).toBe("chip chip--band-missing");
    expect(bandChipClass("")).toBe("chip chip--band-missing");
  });
});

describe("thresholdWords — the catalog's OWN bands, verbatim, with the metric's unit", () => {
  it("prints pass/review verbatim beside the unit", () => {
    const metric = siteAcceptanceMetric({
      unit: "mm",
      bands: { pass: 0.2, review: 0.5 },
    });
    expect(thresholdWords(metric)).toBe("pass ≤ 0.2 mm · review ≤ 0.5 mm");
  });

  it("returns null when the band is not a scalar comparison — nothing is fabricated", () => {
    const metric = siteAcceptanceMetric({ bands: null });
    expect(thresholdWords(metric)).toBeNull();
  });

  it("omits the unit's own leading space when the metric carries none", () => {
    const metric = siteAcceptanceMetric({ unit: "", bands: { pass: 1, review: 2 } });
    expect(thresholdWords(metric)).toBe("pass ≤ 1 · review ≤ 2");
  });
});

describe("logWindowWords — 'the last N of M', only where the window actually cut something", () => {
  it("says so when the case recorded more than the window shows", () => {
    expect(logWindowWords(137, 40)).toBe(
      "Showing the last 40 of 137 acts recorded on this case.",
    );
  });

  it("renders NOTHING at the boundary — recorded === shown is not a truncation", () => {
    expect(logWindowWords(3, 3)).toBeNull();
  });

  it("renders nothing when the case has fewer acts than the window holds", () => {
    expect(logWindowWords(1, 3)).toBeNull();
  });
});

describe("stale/missing — key membership only, nothing derived", () => {
  it("isStaleMetric reads stale_metrics by key", () => {
    expect(isStaleMetric(["rim_agreement_mm", "guidance"], "guidance")).toBe(true);
    expect(isStaleMetric(["rim_agreement_mm"], "deviation_rms_mm")).toBe(false);
  });

  it("isMissingMetric reads missing by key", () => {
    expect(isMissingMetric(["deviation_p90_mm"], "deviation_p90_mm")).toBe(true);
    expect(isMissingMetric([], "deviation_p90_mm")).toBe(false);
  });
});

describe("staleSummaryWords — shares Adjust's named-list vocabulary, not Deliver's sentence", () => {
  it("names one stale key in its own singular voice", () => {
    expect(staleSummaryWords(["guidance"])).toBe(
      "the gate verdict below still describes a read from before the most recent " +
        "rework — nothing has re-measured it since.",
    );
  });

  it("joins more than one and never borrows Deliver's 'Confirming seals' clause", () => {
    const words = staleSummaryWords(["rim_agreement_mm", "guidance"]);
    expect(words).toContain("the rim agreement and the gate verdict");
    expect(words).not.toContain("Confirming seals");
  });

  it("returns null when nothing is stale", () => {
    expect(staleSummaryWords([])).toBeNull();
  });
});

describe("acceptanceAbsenceWords — the pre-run 404 is a healthy answer, not an outage", () => {
  it("treats a 404 as a hint, in the server's own words", () => {
    const words = acceptanceAbsenceWords({
      detail: "tooth 19 carries no verdict from case case-a's current run",
      status: 404,
    });
    expect(words).toEqual({
      tone: "hint",
      words: "tooth 19 carries no verdict from case case-a's current run",
    });
  });

  it("keeps the standing failure tone for anything else", () => {
    expect(acceptanceAbsenceWords({ detail: "network error", status: undefined })).toEqual({
      tone: "error",
      words: "network error",
    });
    expect(acceptanceAbsenceWords({ detail: "internal error", status: 500 })).toEqual({
      tone: "error",
      words: "internal error",
    });
  });
});
