/**
 * Static-markup component tests (renderToStaticMarkup — node environment, no jsdom, per the repo
 * convention) for the ROTATION SURFACES, after the client's 2026-07-26 verdict on the old one:
 * "this rotation is kinda useless if it doesn't have a good view of what it does real time, the
 * client will not be selecting what degrees to rotate — there is barely any automation there".
 *
 * They were reading the UI correctly. Rotation is MEASURED here (coded-cutout correlation), and a
 * degree-stepper in a cell of a fifteen-column table presented that measurement as a manual
 * choice, nowhere near a picture that could justify a step. So there are two surfaces now, and
 * these tests pin the split:
 *
 *   RotationVerdict — the table column. States what the automation measured and WHO measured it;
 *                     the only thing it can do is OPEN the 3D. No degrees.
 *   RotationDial    — the control, floated on the union pane's 3D, where each gated step is
 *                     visible on the seated cap as it lands.
 *
 * This file also exports the shared `makeRunSite` fixture (imported by AlignmentActions.test).
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { RotationVerdict } from "./RotationVerdict";
import { RotationDial } from "./RotationDial";
import { ResultsTable } from "./ResultsTable";
import type { Clocking, RunSiteResult } from "../domain/types";

function makeClocking(overrides: Partial<Clocking> = {}): Clocking {
  return {
    notchShiftDeg: -1.8,
    notchCorr: 0.61,
    notchProminence: 0.3,
    evidence: "codes",
    consistencyDeg: null,
    rotationUnverified: false,
    ...overrides,
  };
}

export function makeRunSite(overrides: Partial<RunSiteResult> = {}): RunSiteResult {
  return {
    tooth: 29,
    spec: "zimmer-4.5 7030",
    vendor: "atlantis",
    coverage: 0.62,
    alignmentErrorMm: 0.21,
    advisory: "",
    variant: {
      identified: "7030",
      declared: "7030",
      measuredRimDiameterMm: 7.05,
      diameterClassMarginMm: 0.4,
      flags: [],
      candidates: null,
    },
    siteMeasurement: {
      mdSpanMm: 8.1,
      gapMesialMm: 1.2,
      gapDistalMm: 1.4,
      classification: "molar",
      terminalSite: false,
    },
    production: { screwChannelRadiusMm: 1.25 },
    seedSource: "marks",
    autoDeltaMm: 0.8,
    fit: { avgMm: 0.18, maxMm: 1.4 },
    seatMethod: "rim",
    guidance: { level: "ready", actions: [] },
    rimAgreementMm: 0.4,
    borderClickDisagreementMm: null,
    topFaceAgreementMm: 0.3,
    confidence: null,
    capSurfaceExplainedPct: 82,
    clocking: makeClocking(),
    nudge: null,
    acceptance: null,
    doctorConfirmation: null,
    gingivalOffset: null,
    ...overrides,
  };
}

const REVIEW_CLOCKING = makeClocking({ rotationUnverified: true, notchShiftDeg: null, evidence: "none" });

describe("RotationVerdict — the table column reports, it does not steer", () => {
  it("carries NO degree steps — the client must never be asked to pick an angle in a table", () => {
    const html = renderToStaticMarkup(
      <RotationVerdict site={makeRunSite({ clocking: REVIEW_CLOCKING })} onAdjustIn3D={() => undefined} />,
    );
    expect(html).not.toContain("+3°");
    expect(html).not.toContain("+15°");
    expect(html).not.toContain("Reset");
  });

  it("says the number was MEASURED, and by which instrument, on a verified row", () => {
    const html = renderToStaticMarkup(<RotationVerdict site={makeRunSite()} />);
    expect(html).toContain("read from the coded cutouts");
  });

  it("offers exactly one action — open the 3D — and names it for what the row needs", () => {
    const healthy = renderToStaticMarkup(
      <RotationVerdict site={makeRunSite()} onAdjustIn3D={() => undefined} />,
    );
    const review = renderToStaticMarkup(
      <RotationVerdict site={makeRunSite({ clocking: REVIEW_CLOCKING })} onAdjustIn3D={() => undefined} />,
    );
    expect(healthy).toContain("◱ See in 3D");
    expect(review).toContain("↻ Correct in 3D");
    expect(review.match(/<button/g)?.length).toBe(1);
  });

  it("is a pure read-out with no wiring (a read-only embedding)", () => {
    const html = renderToStaticMarkup(<RotationVerdict site={makeRunSite()} />);
    expect(html).not.toContain("<button");
  });

  it("prints the operator's cumulative rotation once one has been applied", () => {
    const html = renderToStaticMarkup(
      <RotationVerdict site={makeRunSite({ clocking: REVIEW_CLOCKING, nudge: { cumulativeDeg: 6 } })} />,
    );
    expect(html).toContain("operator +6.0°");
  });

  it("icp seat: no rotation instrument at all (no rim ring to hold fixed)", () => {
    const html = renderToStaticMarkup(
      <RotationVerdict site={makeRunSite({ seatMethod: "icp", clocking: null })} />,
    );
    expect(html).toContain("rotation control needs a rim seat");
  });
});

describe("RotationDial — the control, on the 3D", () => {
  const dial = (overrides: Partial<Parameters<typeof RotationDial>[0]> = {}) =>
    renderToStaticMarkup(
      <RotationDial
        tooth={29}
        clocking={REVIEW_CLOCKING}
        cumulativeDeg={0}
        busy={false}
        onNudge={() => undefined}
        {...overrides}
      />,
    );

  it("offers the gated steps and the reset, with the residual read beside them", () => {
    const html = dial();
    expect(html).toContain("-15°");
    expect(html).toContain("+3°");
    expect(html).toContain("+15°");
    expect(html).toContain("Reset");
    expect(html).toContain("rotation-dial__residual");
  });

  it("disables Reset until the operator has actually moved the automation's pose", () => {
    expect(dial().match(/<button[^>]*disabled[^>]*>Reset/)).not.toBeNull();
    expect(dial({ cumulativeDeg: 6 }).match(/<button[^>]*disabled[^>]*>Reset/)).toBeNull();
  });

  it("goes down while a step is in flight — the pane is about to redraw", () => {
    expect(dial({ busy: true }).match(/<button[^>]*disabled[^>]*>\+3°/)).not.toBeNull();
    expect(dial().match(/<button[^>]*disabled[^>]*>\+3°/)).toBeNull();
  });

  it("prints the operator's cumulative rotation once one has been applied", () => {
    expect(dial({ cumulativeDeg: 6 })).toContain("operator +6.0°");
  });
});

describe("ResultsTable — the Rotation column after the split", () => {
  it("shows a verdict per row and no degree control anywhere in the table", () => {
    const sites = [
      makeRunSite({ tooth: 29, clocking: REVIEW_CLOCKING }),
      makeRunSite({ tooth: 30 }),
    ];
    const html = renderToStaticMarkup(
      <ResultsTable sites={sites} onAdjustRotationIn3D={() => undefined} />,
    );
    expect(html).not.toContain("+3°");
    expect(html).not.toContain("+15°");
    expect(html.split("↻ Correct in 3D").length - 1).toBe(1); // only the flagged row
    expect(html.split("◱ See in 3D").length - 1).toBe(1);
  });
});
