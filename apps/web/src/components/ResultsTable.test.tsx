/**
 * THE CLAMP, ON THE ROW IT HAPPENED TO (client, 2026-07-25).
 *
 * The run banner says a clamp happened; this says WHICH TOOTH — the distinction that matters on a
 * multi-site case, where one cap's ceiling governs the whole run and only some sites end up
 * reduced. A row that was not clamped carries nothing, so the chip's presence is itself the
 * signal.
 *
 * Static markup (renderToStaticMarkup — node environment, repo convention). The table's
 * interactive columns are omitted here on purpose: they have their own components and tests, and
 * this file is about the one cell the relief work added.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ResultsTable } from "./ResultsTable";
import type { GingivalOffsetReading, RunSiteResult } from "../domain/types";

function reading(overrides: Partial<GingivalOffsetReading> = {}): GingivalOffsetReading {
  return {
    requestedMm: 0.2,
    achievedMedianMm: null,
    achievedMinMm: null,
    achievedMaxMm: null,
    method: null,
    appliedMm: null,
    clamped: false,
    limitMm: null,
    minWallMm: null,
    clampReason: null,
    ...overrides,
  };
}

function site(tooth: number, gingivalOffset: GingivalOffsetReading | null): RunSiteResult {
  return {
    tooth,
    spec: "neodent-gm-5030",
    vendor: "atlantis",
    coverage: 0.9,
    alignmentErrorMm: 0.1,
    advisory: "",
    variant: {
      identified: "5030",
      declared: "5030",
      measuredRimDiameterMm: 5.1,
      diameterClassMarginMm: 0.2,
      flags: [],
      candidates: null,
    },
    siteMeasurement: {
      mdSpanMm: 8,
      gapMesialMm: 1,
      gapDistalMm: 1,
      classification: "bounded",
      terminalSite: false,
    },
    production: { screwChannelRadiusMm: 1.153 },
    seedSource: "marks",
    autoDeltaMm: 0.2,
    fit: { avgMm: 0.08, maxMm: 0.4 },
    seatMethod: "rim",
    guidance: null,
    rimAgreementMm: 0.3,
    borderClickDisagreementMm: null,
    topFaceAgreementMm: null,
    confidence: null,
    capSurfaceExplainedPct: null,
    clocking: null,
    nudge: null,
    acceptance: null,
    doctorConfirmation: null,
    gingivalOffset,
  };
}

describe("ResultsTable — the relief-clamp chip", () => {
  it("chips the clamped row with both numbers, and the full sentence as its title", () => {
    const html = renderToStaticMarkup(
      <ResultsTable
        sites={[site(3, reading({ clamped: true, appliedMm: 0.06, limitMm: 0.06, minWallMm: 0.5 }))]}
      />,
    );
    expect(html).toContain("relief clamped 0.20 → 0.06 mm");
    expect(html).toContain("chip--relief-clamped");
    expect(html).toContain(
      "gingival relief 0.20 mm requested → 0.06 mm applied (the maximum this construction part " +
        "can take without thinning the channel wall below 0.50 mm)",
    );
  });

  it("chips ONLY the rows that were clamped", () => {
    const html = renderToStaticMarkup(
      <ResultsTable
        sites={[
          site(3, reading({ clamped: true, appliedMm: 0.06, minWallMm: 0.5 })),
          site(14, reading({ achievedMedianMm: 0.14 })),
        ]}
      />,
    );
    expect(html.match(/chip--relief-clamped/g)).toHaveLength(1);
  });

  it("says nothing at all on a run where the requested relief was applied in full", () => {
    const html = renderToStaticMarkup(<ResultsTable sites={[site(3, reading())]} />);
    expect(html).not.toContain("relief clamped");
  });

  it("says nothing on a legacy run that carries no gingival reading", () => {
    const html = renderToStaticMarkup(<ResultsTable sites={[site(3, null)]} />);
    expect(html).not.toContain("relief clamped");
  });
});
