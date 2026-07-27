/**
 * THE MANUAL BEST FIT (client's register/best-fit panel, 2026-07-25). What is pinned: their
 * control (a Matching Diameter, defaulting to their 0.3 mm), their Apply-Best-Fit toggle, and
 * the honesty that follows from it — with Apply off the button says MEASURE and the panel says
 * the seat will not move.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { BestFitPanel, type BestFitControls } from "./BestFitPanel";
import { BEST_FIT_DEFAULT_DIAMETER_MM, describeBestFit } from "../domain/types";
import type { BestFitResult } from "../domain/types";

function controls(overrides: Partial<BestFitControls> = {}): BestFitControls {
  return {
    matchingDiameterMm: BEST_FIT_DEFAULT_DIAMETER_MM,
    apply: true,
    busy: false,
    unavailable: false,
    notice: null,
    confirmation: null,
    onChangeDiameter: () => {},
    onToggleApply: () => {},
    onRun: () => {},
    onSearchWider: () => {},
    ...overrides,
  };
}

function result(overrides: Partial<BestFitResult> = {}): BestFitResult {
  return {
    tooth: 3,
    matchingDiameterMm: 0.3,
    applied: true,
    nMatched: 1284,
    rmsMm: 0.082,
    maxMm: 0.31,
    translationMm: 0.061,
    rotationDeg: 0.42,
    fit: null,
    rimAgreementMm: null,
    clocking: null,
    nudge: null,
    ...overrides,
  };
}

describe("BestFitPanel", () => {
  it("offers the client's Matching Diameter slider at their 0.3 mm default", () => {
    const html = renderToStaticMarkup(<BestFitPanel tooth={3} controls={controls()} />);
    expect(html).toContain('type="range"');
    expect(html).toContain('value="0.3"');
    expect(html).toContain("Matching diameter");
    expect(html).toContain("0.30 mm");
    expect(BEST_FIT_DEFAULT_DIAMETER_MM).toBe(0.3);
  });

  it("offers the Apply-Best-Fit toggle, and says what OFF means", () => {
    const on = renderToStaticMarkup(<BestFitPanel tooth={3} controls={controls()} />);
    expect(on).toMatch(/type="checkbox"[^>]*checked/);
    expect(on).toContain("⊚ Best fit");

    const off = renderToStaticMarkup(<BestFitPanel tooth={3} controls={controls({ apply: false })} />);
    expect(off).not.toMatch(/type="checkbox"[^>]*checked/);
    expect(off).toContain("⊚ Measure fit");
    expect(off).toContain("the seated pose stays where it is");
  });

  it("disables every control while this row's fit is in flight", () => {
    const html = renderToStaticMarkup(<BestFitPanel tooth={3} controls={controls({ busy: true })} />);
    expect(html.match(/disabled/g)?.length).toBe(3); // slider, checkbox, button
    expect(html).toContain("fitting…");
  });

  it("says the endpoint is missing instead of leaving a broken button", () => {
    const html = renderToStaticMarkup(
      <BestFitPanel tooth={3} controls={controls({ unavailable: true })} />,
    );
    expect(html).toContain("not available on the running API");
    expect(html).toContain("make serve");
    expect(html.match(/disabled/g)?.length).toBe(3);
  });

  it("shows this row's own outcome line", () => {
    const html = renderToStaticMarkup(
      <BestFitPanel tooth={3} controls={controls({ notice: describeBestFit(result()) })} />,
    );
    expect(html).toContain("best fit applied at Ø0.30 mm matching");
    expect(html).toContain("1,284 points matched");
    expect(html).toContain("RMS 0.082 mm");
    expect(html).toContain("moved 0.061 mm / 0.42°");
  });

  it("renders 'already optimal' as a CONFIRMATION with the one-click wider search", () => {
    // client ask 2026-07-26: this outcome is a PASS phrased as one — check tone, green
    // class, and the widen button carrying the server's own suggested diameter. Never the
    // error tone the true refusals get.
    const html = renderToStaticMarkup(
      <BestFitPanel
        tooth={3}
        controls={controls({
          confirmation: {
            message:
              "the certified pose is already the best fit within this matching diameter — nothing to correct at Ø0.30mm; widen to search further",
            matchingDiameterMm: 0.3,
            suggestedDiameterMm: 0.6,
          },
        })}
      />,
    );
    expect(html).toContain("best-fit__confirm");
    expect(html).toContain("✓");
    expect(html).toContain("already the best fit within this matching diameter");
    expect(html).toContain("Search wider (Ø0.60mm)");
    expect(html).not.toContain("panel__error");
  });

  it("suppresses the widen button at the ceiling instead of offering a no-op loop", () => {
    // review 2026-07-26: at Ø2.00mm the server's doubled suggestion caps to the dial
    // itself, so "Search wider (Ø2.00mm)" re-ran the identical search forever. The
    // confirmation (still a pass) stays; the button goes when there is nothing wider.
    const html = renderToStaticMarkup(
      <BestFitPanel
        tooth={3}
        controls={controls({
          matchingDiameterMm: 2.0,
          confirmation: {
            message:
              "the certified pose is already the best fit within this matching diameter — nothing to correct at Ø2.00mm, and this is the widest matching band the tool searches",
            matchingDiameterMm: 2.0,
            suggestedDiameterMm: 2.0,
          },
        })}
      />,
    );
    expect(html).toContain("best-fit__confirm");
    expect(html).toContain("✓");
    expect(html).toContain("widest matching band");
    expect(html).not.toContain("Search wider");
    expect(html).not.toContain("panel__error");
  });

  it("shows no confirmation block on an ordinary outcome", () => {
    const html = renderToStaticMarkup(<BestFitPanel tooth={3} controls={controls()} />);
    expect(html).not.toContain("best-fit__confirm");
    expect(html).not.toContain("Search wider");
  });
});

describe("describeBestFit", () => {
  it("says out loud when the seat was NOT moved", () => {
    const text = describeBestFit(result({ applied: false }));
    expect(text).toContain("MEASURED ONLY");
    expect(text).toContain("the seat was not moved");
    expect(text).toContain("would move");
  });

  it("prints only the numbers the backend actually reported", () => {
    const text = describeBestFit(
      result({ nMatched: null, rmsMm: null, translationMm: null, rotationDeg: null }),
    );
    expect(text).toBe("best fit applied at Ø0.30 mm matching — no numbers reported");
  });
});
