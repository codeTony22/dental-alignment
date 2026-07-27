/**
 * Static-markup component tests for the doctor verification panel (renderToStaticMarkup —
 * node environment, no jsdom): band chips per verdict, our-number vs industry-reference
 * columns, QC images, and the confirm/retract control's three states. The confirm flow's
 * wire behavior (URL/body/error surfacing) is covered in api/verification.test.ts; the
 * App-side handler is a thin fold-into-row like the nudge handler.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { VerificationPanel, type VerificationContext } from "./VerificationPanel";
import { ResultsTable } from "./ResultsTable";
import type { Acceptance, DoctorConfirmation, RunSiteResult } from "../domain/types";

const ACCEPTANCE: Acceptance = {
  metrics: [
    {
      key: "fit_avg_mm",
      label: "Registration error — average",
      unit: "mm",
      audience: "doctor",
      industryRef: { value: "RealGUIDE ships 0.28 mm avg", source: "docs/RUN-DEMO.md step 4" },
      bands: { passMax: 0.8, reviewMax: 1.5 },
      note: null,
      value: 0.42,
      display: "0.42 mm",
      band: "pass",
    },
    {
      key: "rotation_deg",
      label: "Rotation of the cap (codes line up)",
      unit: "deg",
      audience: "doctor",
      industryRef: { value: "<2° stable screw joint; >5° harmful", source: "Binon 1996" },
      bands: null,
      note: null,
      value: 23.8,
      display: "23.8 deg (recess)",
      band: "fail",
    },
    {
      key: "confidence_grade",
      label: "Confidence grade (pose stability under click noise)",
      unit: "",
      audience: "doctor",
      industryRef: { value: "no industry equivalent", source: "docs/research/fle-calibration.md" },
      bands: null,
      note: null,
      value: "medium",
      display: "medium (0.87 mm / 11 deg spread)",
      band: "review",
    },
    {
      key: "bore_void_off_mm",
      label: "Screw-recess landing",
      unit: "mm",
      audience: "lab",
      industryRef: { value: "shipped contract <=0.5 mm or flagged", source: "report §6" },
      bands: { passMax: 0.5, reviewMax: 0.75 },
      note: null,
      value: null,
      display: null,
      band: "missing",
    },
  ],
  overall: { band: "fail", missing: ["bore_void_off_mm"] },
  context: {
    label: "Operator click precision (context)",
    text: "click scatter xy p90 = 0.61 mm — why marks are locators.",
    industryRef: { value: "FLE p90 0.61 mm", source: "docs/research/fle-calibration.md" },
  },
};

function makeSite(overrides: Partial<RunSiteResult> = {}): RunSiteResult {
  return {
    tooth: 29,
    spec: "zimmer-4.5-7030",
    vendor: "atlantis",
    coverage: 0.45,
    alignmentErrorMm: 1.38,
    advisory: "",
    variant: {
      identified: "7030",
      declared: "7030",
      measuredRimDiameterMm: 5.09,
      diameterClassMarginMm: 1.0,
      flags: [],
      candidates: null,
    },
    siteMeasurement: {
      mdSpanMm: 11.2,
      gapMesialMm: 0.5,
      gapDistalMm: 0.9,
      classification: "ample (>=7mm)",
      terminalSite: false,
    },
    production: { screwChannelRadiusMm: 1.0 },
    seedSource: "marks",
    autoDeltaMm: 0.39,
    fit: { avgMm: 0.42, maxMm: 1.24 },
    seatMethod: "rim",
    guidance: { level: "ready", actions: [] },
    rimAgreementMm: 0.91,
    borderClickDisagreementMm: null,
    topFaceAgreementMm: 0.34,
    confidence: { grade: "medium", posSpreadMm: 0.87, axisSpreadDeg: 10.8 },
    capSurfaceExplainedPct: 45.8,
    clocking: null,
    nudge: null,
    acceptance: ACCEPTANCE,
    doctorConfirmation: null,
  gingivalOffset: null,
    ...overrides,
  };
}

function makeContext(overrides: Partial<VerificationContext> = {}): VerificationContext {
  return {
    caseId: "cap7030-zimmer-4.5",
    filesBase: "/api/cases/cap7030-zimmer-4.5/files/",
    runVersion: 1234,
    packageFiles: [
      "cap7030-zimmer-4.5-29-clockview.png",
      "cap7030-zimmer-4.5-29-deviation.png",
    ],
    onConfirm: () => undefined,
    confirmBusyTooth: null,
    ...overrides,
  };
}

describe("VerificationPanel — band chips and metric rows", () => {
  it("renders one chip per metric with the band's own class and text", () => {
    const html = renderToStaticMarkup(<VerificationPanel site={makeSite()} context={makeContext()} />);
    expect(html).toContain("chip--band-pass");
    expect(html).toContain("chip--band-review");
    expect(html).toContain("chip--band-fail");
    expect(html).toContain("chip--band-missing");
    // a missing value reads "not measured", never a silent pass
    expect(html).toContain("not measured");
  });

  it("shows OUR number next to the industry reference, per metric", () => {
    const html = renderToStaticMarkup(<VerificationPanel site={makeSite()} context={makeContext()} />);
    expect(html).toContain("0.42 mm");
    expect(html).toContain("RealGUIDE ships 0.28 mm avg");
    expect(html).toContain("23.8 deg (recess)");
    expect(html).toContain("stable screw joint");
  });

  it("groups the doctor verification set apart from the lab/QC checks and shows the overall band", () => {
    const html = renderToStaticMarkup(<VerificationPanel site={makeSite()} context={makeContext()} />);
    expect(html).toContain("Doctor verification set");
    expect(html).toContain("Lab / QC checks");
    expect(html).toContain("Verification numbers — tooth 29");
    // overall fail (the rotation row) leads the header
    expect(html.indexOf("chip--band-fail")).toBeLessThan(html.indexOf("Doctor verification set"));
  });

  it("renders the click-precision context as copy, and the QC images with cache-busted urls", () => {
    const html = renderToStaticMarkup(<VerificationPanel site={makeSite()} context={makeContext()} />);
    expect(html).toContain("why marks are locators");
    expect(html).toContain("/api/cases/cap7030-zimmer-4.5/files/cap7030-zimmer-4.5-29-clockview.png?v=1234");
    expect(html).toContain("/api/cases/cap7030-zimmer-4.5/files/cap7030-zimmer-4.5-29-deviation.png?v=1234");
    expect(html).toContain("Clock view");
    expect(html).toContain("Deviation map");
  });

  it("omits images the package did not emit, and stays honest without acceptance data", () => {
    const noImages = renderToStaticMarkup(
      <VerificationPanel site={makeSite()} context={makeContext({ packageFiles: [] })} />,
    );
    expect(noImages).not.toContain("<img");
    const noAcceptance = renderToStaticMarkup(
      <VerificationPanel site={makeSite({ acceptance: null })} context={makeContext()} />,
    );
    expect(noAcceptance).toContain("No verification data");
    expect(noAcceptance).not.toContain("chip--band");
  });
});

describe("VerificationPanel — confirm control states", () => {
  it("unconfirmed: offers the confirm button and the optional note input", () => {
    const html = renderToStaticMarkup(<VerificationPanel site={makeSite()} context={makeContext()} />);
    expect(html).toContain("Doctor: confirm this alignment");
    expect(html).toContain("optional note");
    expect(html).not.toContain("Retract confirmation");
  });

  it("confirmed: shows the sign-off record (with the doctor's note) and the retract control", () => {
    const confirmation: DoctorConfirmation = {
      confirmed: true,
      note: "codes visually aligned",
      ts: "2026-07-23T10:00:00",
    };
    const html = renderToStaticMarkup(
      <VerificationPanel site={makeSite({ doctorConfirmation: confirmation })} context={makeContext()} />,
    );
    expect(html).toContain("✓ confirmed by doctor");
    expect(html).toContain("2026-07-23T10:00:00");
    expect(html).toContain("codes visually aligned");
    expect(html).toContain("Retract confirmation");
    expect(html).not.toContain("Doctor: confirm this alignment");
  });

  it("retracted: the retraction stays visible (audit state, not a deletion) and confirm returns", () => {
    const confirmation: DoctorConfirmation = { confirmed: false, note: null, ts: "2026-07-23T10:05:00" };
    const html = renderToStaticMarkup(
      <VerificationPanel site={makeSite({ doctorConfirmation: confirmation })} context={makeContext()} />,
    );
    expect(html).toContain("confirmation retracted");
    expect(html).toContain("Doctor: confirm this alignment");
  });

  it("disables the controls while this site's request is in flight", () => {
    const html = renderToStaticMarkup(
      <VerificationPanel site={makeSite()} context={makeContext({ confirmBusyTooth: 29 })} />,
    );
    expect(html).toContain("disabled");
  });
});

describe("ResultsTable — verification wiring", () => {
  it("renders the Verify column and the confirmed chip next to the gate when wired", () => {
    const site = makeSite({
      doctorConfirmation: { confirmed: true, note: null, ts: "2026-07-23T10:00:00" },
    });
    const html = renderToStaticMarkup(<ResultsTable sites={[site]} verification={makeContext()} />);
    expect(html).toContain("Verify");
    expect(html).toContain("✓ confirmed");
  });

  it("renders neither the Verify column nor the chip in a read-only embedding", () => {
    const site = makeSite({
      doctorConfirmation: { confirmed: true, note: null, ts: "2026-07-23T10:00:00" },
    });
    const html = renderToStaticMarkup(<ResultsTable sites={[site]} />);
    expect(html).not.toContain("Verify");
    expect(html).not.toContain("✓ confirmed");
  });
});
