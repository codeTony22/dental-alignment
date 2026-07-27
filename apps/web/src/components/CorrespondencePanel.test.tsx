/**
 * Static-markup component tests (renderToStaticMarkup — node environment, no jsdom, per the
 * repo convention) for the SCAN-SIDE correspondence flow (client ask 2026-07-24, half two):
 * the feature picker (only marks that CAN anchor a rotation, only ones not already paired),
 * the pair list, the armed instruction, the residual read-out ("your marks agree to 0.07mm")
 * and the 404 restart hint.
 *
 * The panel itself is unchanged; where it LIVES is not. It used to render inside the rotation
 * control of one table cell, which is why the client could not find the flow at all — it is now
 * the rail of the FitByPointsStage, whose two-pane placement is pinned in that component's own
 * suite. What stays here is the panel's own behaviour, which is what the stage renders.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { CorrespondencePanel, type CorrespondenceControls } from "./CorrespondencePanel";
import type { PartFeature } from "../domain/partFeatures";
import { featurePair, freePair } from "../domain/correspondence";
import { featureHex, freePointHex } from "../viewer/palette";

function feature(id: string, azimuthDeg: number, radiusMm = 2.0): PartFeature {
  return {
    id,
    kind: "trench",
    azimuthDeg,
    radiusMm,
    zMm: 1.8,
    source: "auto",
    definesRotation: radiusMm >= 0.5,
  };
}

const FEATURES: PartFeature[] = [
  feature("trench-01", -177.0, 2.06),
  feature("trench-02", -136.0, 2.08),
  feature("trench-03", -0.1, 2.0),
  { ...feature("channel", -173.1, 0.03), kind: "channel", definesRotation: false },
];

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
    onArm: () => {},
    onCancelArm: () => {},
    onPickPartPoint: () => {},
    onRemovePair: () => {},
    onClearPairs: () => {},
    onApply: () => {},
    onClose: () => {},
    ...overrides,
  };
}

describe("CorrespondencePanel", () => {
  it("names the part whose marks are being matched", () => {
    const html = renderToStaticMarkup(<CorrespondencePanel controls={makeControls()} />);
    expect(html).toContain("Match features — zimmer-4.5/7030");
  });

  it("offers every anchorable feature — and NOT the concentric bore the server would refuse", () => {
    const html = renderToStaticMarkup(<CorrespondencePanel controls={makeControls()} />);
    expect(html).toContain("trench-01");
    expect(html).toContain("trench-02");
    expect(html).toContain("trench-03");
    expect(html).not.toContain(">channel<");
    expect(html).toContain(featureHex("trench"));
  });

  it("drops a feature from the picker once it is paired, and lists the pair", () => {
    const html = renderToStaticMarkup(
      <CorrespondencePanel
        controls={makeControls({
          pairs: [featurePair("trench-02", "trench", [1, 2, 3])],
        })}
      />,
    );
    expect(html).toContain("trench-02 ↔ marked");
    // the picker still offers the other two, but not the one already placed
    const picker = html.slice(html.indexOf("correspondence__picker"));
    expect(picker).toContain("trench-01");
    expect(picker).toContain("trench-03");
    expect(picker).not.toContain("trench-02");
  });

  it("swaps the picker for the armed instruction naming the feature being marked", () => {
    const html = renderToStaticMarkup(
      <CorrespondencePanel controls={makeControls({ armedFeatureId: "trench-03" })} />,
    );
    expect(html).toContain("click trench-03 on the scan — Esc cancels");
    expect(html).not.toContain("correspondence__picker");
  });

  it("cannot apply with no pairs recorded, and can once there is one", () => {
    const empty = renderToStaticMarkup(<CorrespondencePanel controls={makeControls()} />);
    expect(empty.match(/<button[^>]*disabled[^>]*>Align to my marks/)).not.toBeNull();

    const withPair = renderToStaticMarkup(
      <CorrespondencePanel
        controls={makeControls({ pairs: [featurePair("trench-01", "trench", [0, 0, 0])] })}
      />,
    );
    expect(withPair.match(/<button[^>]*disabled[^>]*>Align to my marks/)).toBeNull();
  });

  it("lists a FREE point as 'point N' in the free-point color, with its remove control", () => {
    // client ask 2026-07-26: arbitrary numbered points, RealGUIDE-style
    const html = renderToStaticMarkup(
      <CorrespondencePanel
        controls={makeControls({
          pairs: [featurePair("trench-01", "trench", [0, 0, 0]), freePair([1, 0, 2], [4, 5, 6])],
        })}
      />,
    );
    expect(html).toContain("trench-01 ↔ marked");
    expect(html).toContain("point 1 ↔ marked");
    expect(html).toContain(freePointHex());
    // one remove button per pair, feature and free alike
    expect(html.match(/title="Drop this pair"/g)?.length).toBe(2);
  });

  it("says which free point the scan pane is waiting for while one is armed", () => {
    const html = renderToStaticMarkup(
      <CorrespondencePanel
        controls={makeControls({
          pairs: [freePair([1, 0, 2], [4, 5, 6])],
          armedFreePoint: [0.4, -1.1, 2.0],
        })}
      />,
    );
    expect(html).toContain("click point 2 on the scan — Esc cancels");
    expect(html).not.toContain("correspondence__picker");
    // an armed pick blocks Apply, free point or feature alike
    expect(html.match(/<button[^>]*disabled[^>]*>Align to my marks/)).not.toBeNull();
  });

  it("reports the per-pair residuals, with the agreement number only when it means something", () => {
    const twoPairs = renderToStaticMarkup(
      <CorrespondencePanel
        controls={makeControls({
          residualRmsMm: 0.072,
          residuals: [
            {
              featureId: "trench-01",
              featureAzimuthDeg: -177,
              clickAzimuthDeg: -167,
              deltaDeg: 10,
              residualDeg: 2,
              residualMm: 0.072,
            },
            {
              featureId: "trench-02",
              featureAzimuthDeg: -136,
              clickAzimuthDeg: -130,
              deltaDeg: 6,
              residualDeg: -2,
              residualMm: 0.073,
            },
          ],
        })}
      />,
    );
    expect(twoPairs).toContain("your marks agree to 0.07mm");
    expect(twoPairs).toContain("trench-01 · +2.0° · 0.07mm off");
    expect(twoPairs).toContain("trench-02 · -2.0° · 0.07mm off");

    // A single pair lands the feature exactly on the mark by construction — showing an
    // agreement number would dress a tautology up as a measurement.
    const onePair = renderToStaticMarkup(
      <CorrespondencePanel
        controls={makeControls({
          residualRmsMm: 0,
          residuals: [
            {
              featureId: "trench-01",
              featureAzimuthDeg: -177,
              clickAzimuthDeg: -139,
              deltaDeg: 38,
              residualDeg: 0,
              residualMm: 0,
            },
          ],
        })}
      />,
    );
    expect(onePair).not.toContain("your marks agree");
    expect(onePair).toContain("trench-01 · 0.0° · 0.00mm off");
  });

  it("says the marks are the machine's reading when the part has never been annotated", () => {
    const html = renderToStaticMarkup(<CorrespondencePanel controls={makeControls({ autoSeeded: true })} />);
    expect(html).toContain("using the machine&#x27;s reading of this part");
  });

  it("shows the restart hint when the running API predates the features endpoint", () => {
    const html = renderToStaticMarkup(<CorrespondencePanel controls={makeControls({ state: "unavailable" })} />);
    expect(html).toContain("not available on the running API");
    expect(html).toContain("mark trench");
  });

  it("offers free points instead of blocking when the part carries nothing anchorable", () => {
    // Before 2026-07-26 this state DEAD-ENDED the flow; free points make it workable, so the
    // hint invites a part click and the pair list + Apply stay available.
    const html = renderToStaticMarkup(
      <CorrespondencePanel controls={makeControls({ features: [FEATURES[3] as PartFeature] })} />,
    );
    expect(html).toContain("no feature that can anchor a rotation");
    expect(html).toContain("Click the part itself to place free numbered points");
    expect(html).toContain("Align to my marks");
  });
});

