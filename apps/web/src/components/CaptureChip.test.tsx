/**
 * Capture-gate chips + banner (static markup, node environment — repo convention).
 * The contract under test: verdict -> traffic-light chip with the concrete recapture
 * messages in the tooltip, and a banner that is LOUD on rescan and silent otherwise
 * (the chair-side intake moment; advisory in the demo).
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { CaptureBanner, CaptureChip } from "./CaptureChip";
import type { CaptureAssessment, CaptureCheck, CaptureVerdict } from "../domain/types";

function check(overrides: Partial<CaptureCheck> = {}): CaptureCheck {
  return {
    name: "rim_arc",
    value: 1.0,
    boundPass: 0.92,
    boundRescan: 0.55,
    verdict: "pass",
    message: "Entire rim circumference captured (24/24 bearings).",
    ...overrides,
  };
}

function assessment(
  verdict: CaptureVerdict,
  checks: readonly CaptureCheck[] = [check()],
): CaptureAssessment {
  return { verdict, checks };
}

const RESCAN_MSG =
  "Rescan the rim on the tongue-facing (lingual) side — 46% of the ring is missing";

describe("CaptureChip", () => {
  it("renders a green pass chip with the all-clear tooltip", () => {
    const html = renderToStaticMarkup(<CaptureChip capture={assessment("pass")} />);
    expect(html).toContain("chip--capture-pass");
    expect(html).toContain("capture ✓");
    expect(html).toContain("All capture checks pass");
  });

  it("renders an amber marginal chip carrying the non-pass check messages", () => {
    const capture = assessment("marginal", [
      check(),
      check({ name: "collar_exposure", value: 0.64, verdict: "marginal", message: "Collar is only 0.64mm above the surrounding tissue" }),
    ]);
    const html = renderToStaticMarkup(<CaptureChip capture={capture} />);
    expect(html).toContain("chip--capture-marginal");
    expect(html).toContain("capture marginal");
    expect(html).toContain("Collar is only 0.64mm");
  });

  it("renders a loud red RESCAN chip", () => {
    const capture = assessment("rescan", [
      check({ value: 0.542, verdict: "rescan", message: RESCAN_MSG }),
    ]);
    const html = renderToStaticMarkup(<CaptureChip capture={capture} />);
    expect(html).toContain("chip--capture-rescan");
    expect(html).toContain("RESCAN");
    expect(html).toContain("46% of the ring is missing");
  });
});

describe("CaptureBanner", () => {
  it("is silent when every site passes or is merely marginal", () => {
    const html = renderToStaticMarkup(
      <CaptureBanner
        items={[
          { label: "Tooth 3", capture: assessment("pass") },
          { label: "Tooth 13", capture: assessment("marginal") },
        ]}
      />,
    );
    expect(html).toBe("");
  });

  it("shows the chair-side warning with each rescan-grade message, labeled by site", () => {
    const t7 = assessment("rescan", [
      check({ value: 0.542, verdict: "rescan", message: RESCAN_MSG }),
      check({ name: "collar_exposure", value: -0.29, verdict: "rescan", message: "Collar reads -0.29mm above the surrounding tissue" }),
      check({ name: "code_band", verdict: "pass" }),
    ]);
    const html = renderToStaticMarkup(
      <CaptureBanner
        items={[
          { label: "Tooth 7", capture: t7 },
          { label: "Tooth 3", capture: assessment("pass") },
        ]}
      />,
    );
    expect(html).toContain("capture-banner");
    expect(html).toContain("1 site needs a rescan");
    expect(html).toContain("while the patient is in the chair");
    expect(html).toContain("Tooth 7");
    expect(html).toContain("46% of the ring is missing");
    expect(html).toContain("Collar reads -0.29mm");
    // pass-grade sites contribute no list items
    expect(html).not.toContain("Tooth 3");
  });
});
