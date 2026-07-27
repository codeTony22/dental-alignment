/**
 * THE FIT-BY-POINTS STAGE (client, 2026-07-26): "their RealGUIDE reference shows numbered points
 * on the scan AND on the library part side by side."
 *
 * Static markup only (renderToStaticMarkup — node environment, no jsdom, per the repo
 * convention), which is exactly the right instrument here: the panes' WebGL scenes are created in
 * effects that a server render never runs, so what these tests see is the STRUCTURE — that both
 * views exist, that the pair rail is with them, and that the pane says what it is waiting for.
 * The 3D itself (numbered spheres, click-to-place) is VerifyScene's own contract.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { FitByPointsStage, partPaneNotice } from "./FitByPointsStage";
import type { CorrespondenceControls } from "./CorrespondencePanel";
import type { PartFeature } from "../domain/partFeatures";
import { featurePair, freePair } from "../domain/correspondence";

function feature(id: string, azimuthDeg: number, radiusMm = 2.0): PartFeature {
  return { id, kind: "trench", azimuthDeg, radiusMm, zMm: 1.8, source: "auto", definesRotation: radiusMm >= 0.5 };
}

const FEATURES: PartFeature[] = [feature("trench-01", -177), feature("trench-02", -136)];

function makeControls(overrides: Partial<CorrespondenceControls> = {}): CorrespondenceControls {
  return {
    state: "ready",
    errorMessage: null,
    model: "zimmer-4.5",
    variant: "7030",
    features: FEATURES,
    autoSeeded: false,
    pairs: [],
    armedFeatureId: null,
    armedFreePoint: null,
    busy: false,
    residuals: null,
    residualRmsMm: null,
    onArm: () => undefined,
    onCancelArm: () => undefined,
    onPickPartPoint: () => undefined,
    onRemovePair: () => undefined,
    onClearPairs: () => undefined,
    onApply: () => undefined,
    onClose: () => undefined,
    ...overrides,
  };
}

function render(overrides: Partial<CorrespondenceControls> = {}) {
  return renderToStaticMarkup(
    <FitByPointsStage
      caseId="cap7030-zimmer-4.5"
      tooth={29}
      model="zimmer-4.5"
      variant="7030"
      partMeshUrl="/api/library/zimmer-4.5/7030/mesh"
      siteCenter={[1, 2, 3]}
      controls={makeControls(overrides)}
      onPickScanPoint={() => undefined}
      onClose={() => undefined}
    />,
  );
}

describe("FitByPointsStage — both views, side by side", () => {
  it("shows the library part AND the scanned cap as two panes", () => {
    const html = render();
    expect(html).toContain("Library part — the marked features");
    expect(html).toContain("Scanned cap — click the matching spot");
    expect(html).toContain(
      'aria-label="The library part — its features numbered; click it to place a free point"',
    );
    expect(html).toContain('aria-label="The scanned cap region — click to place the matching point"');
    expect(html.indexOf("Library part")).toBeLessThan(html.indexOf("Scanned cap"));
  });

  it("names the case, the tooth and the part it is matching", () => {
    const html = render();
    expect(html).toContain("Fit by points — tooth 29");
    expect(html).toContain("cap7030-zimmer-4.5");
    expect(html).toContain("zimmer-4.5/7030");
  });

  it("carries the pair list, the picker and Apply in the same view", () => {
    const html = render();
    expect(html).toContain("Match features — zimmer-4.5/7030");
    expect(html).toContain("trench-01");
    expect(html).toContain("Align to my marks");
  });

  it("states which numbered point the scan pane is waiting for", () => {
    const html = render({ armedFeatureId: "trench-02" });
    // trench-02 is the SECOND anchorable feature, so it is point 2 on both views
    expect(html).toContain("waiting for point 2");
    expect(html).toContain("click point 2 on the scan");
    expect(html).toContain("verify-panel__stage--armed");
  });

  it("counts the points placed so far", () => {
    const html = render({
      pairs: [featurePair("trench-01", "trench", [1, 2, 3])],
    });
    expect(html).toContain("1 point placed");
  });

  it("lists a FREE pair as a numbered point alongside the feature rows", () => {
    // client ask 2026-07-26: arbitrary numbered points, RealGUIDE-style. The 3D markers
    // themselves are effect-driven (VerifyScene's contract); what a static render pins is
    // that the pair rail names the point by the same number its markers wear on both panes.
    const html = render({
      pairs: [featurePair("trench-01", "trench", [1, 2, 3]), freePair([0.5, -0.2, 1.8], [4, 5, 6])],
    });
    expect(html).toContain("2 points placed");
    expect(html).toContain("trench-01 ↔ marked");
    expect(html).toContain("point 1 ↔ marked");
  });

  it("states which free point the scan pane is waiting for after a part click", () => {
    const html = render({
      pairs: [freePair([0.5, -0.2, 1.8], [4, 5, 6])],
      armedFreePoint: [1.1, 0.3, 1.9],
    });
    // one free point is already placed, so the armed click is point 2 — on both panes
    expect(html).toContain("waiting for point 2");
    expect(html).toContain("click point 2 on the scan");
    expect(html).toContain("verify-panel__stage--armed");
  });

  it("invites a part click rather than clicking through to the scan flow", () => {
    const html = render();
    expect(html).toContain("click anywhere on it to place a free point");
    expect(html).toContain(
      'aria-label="The library part — its features numbered; click it to place a free point"',
    );
  });

  it("is a modal dialog with a way out", () => {
    const html = render();
    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-modal="true"');
    expect(html).toContain("✕ close");
  });

  it("says so rather than showing an empty pane when the part is not in the catalog", () => {
    const html = renderToStaticMarkup(
      <FitByPointsStage
        caseId="cap7030-zimmer-4.5"
        tooth={29}
        model="zimmer-4.5"
        variant="7030"
        partMeshUrl={null}
        siteCenter={[1, 2, 3]}
        controls={makeControls()}
        onPickScanPoint={() => undefined}
        onClose={() => undefined}
      />,
    );
    expect(html).toContain("The library part for zimmer-4.5/7030 is not in the catalog.");
  });

  it("says so rather than showing an empty pane when the site has no marked centre", () => {
    const html = renderToStaticMarkup(
      <FitByPointsStage
        caseId="cap7030-zimmer-4.5"
        tooth={29}
        model="zimmer-4.5"
        variant="7030"
        partMeshUrl="/api/library/zimmer-4.5/7030/mesh"
        siteCenter={null}
        controls={makeControls()}
        onPickScanPoint={() => undefined}
        onClose={() => undefined}
      />,
    );
    expect(html).toContain("This site has no marked centre.");
  });
});

describe("partPaneNotice — the part pane's stated reasons", () => {
  // The frame-refused state is unreachable in a static render (positions only load in
  // effects), so the pure helper the pane renders from is pinned directly.
  const base = {
    partError: null,
    partMeshUrl: "/api/library/zimmer-4.5/7030/mesh",
    hasPositions: true,
    hasFrame: true,
    featureMarkerCount: 1,
    freePointCount: 0,
    model: "zimmer-4.5",
    variant: "7030",
  };

  it("states that a refused frame also disables free-point placement — never a silent no-op", () => {
    const notice = partPaneNotice({ ...base, hasFrame: false });
    expect(notice?.text).toContain("no derivable frame");
    expect(notice?.text).toContain("free points cannot be placed");
    // a pane with no usable mesh beneath keeps the full veil — there is nothing to click
    expect(notice?.tone).toBe("veil");
  });

  it("invites a free point when the detector offers nothing anchorable — as an INVITE, not a veil", () => {
    // review 2026-07-26: this sentence asks for a click on the pane it sits over, so it
    // must not be the full-bleed veil that swallowed exactly that click (and the orbit).
    const notice = partPaneNotice({ ...base, featureMarkerCount: 0 });
    expect(notice?.text).toContain("click the part itself to place a free numbered point");
    expect(notice?.tone).toBe("invite");
  });

  it("clears the invitation once the operator has placed (or armed) a free point", () => {
    // the caption already counts the points — an invitation that never left would sit
    // over the very markers it produced (review 2026-07-26: "it never clears")
    expect(partPaneNotice({ ...base, featureMarkerCount: 0, freePointCount: 1 })).toBeNull();
  });

  it("needs no overlay when the pane is workable", () => {
    expect(partPaneNotice(base)).toBeNull();
  });
});
