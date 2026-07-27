/**
 * Static-markup tests for the collapsed Mark & declare stage (client, 2026-07-26: "ONE cohesive
 * flow"). This component IS the deleted seam's replacement, so what is pinned is composition:
 * the step-2 work column mounts detect, the mark/declare table and the SAME SelectionColumn the
 * verify dialog mounts — in that order — and the old dialect (the plain "confirm-system"
 * implant-system select) renders nowhere in the stack.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { MarkDeclareStage } from "./MarkDeclareStage";
import { initialSelection } from "../domain/librarySelection";
import type { ConstructionPart, LibraryCatalogGroup } from "../domain/types";

const GROUPS: LibraryCatalogGroup[] = [
  {
    model: "neodent-gm",
    legacy: false,
    variants: [
      {
        id: "6020",
        variant: "6020",
        label: "neodent-gm-6020",
        rimDiameterMm: 6.16,
        heightMm: 3.38,
        filename: "neodent-gm-6020.stl",
        sha256: "abc",
        flags: [],
        duplicateOf: [],
        meshUrl: "/api/library/neodent-gm/6020/mesh",
      },
    ],
  },
];

const CONSTRUCTIONS: ConstructionPart[] = [
  {
    vendor: "dess",
    filename: "neodent-gm-scanbody.stl",
    pathId: "dess/neodent-gm-scanbody.stl",
    label: "dess — neodent-gm-scanbody",
  },
];

type StageProps = Parameters<typeof MarkDeclareStage>[0];

function props(): StageProps {
  return {
    propose: {
      disabled: false,
      busy: false,
      elapsedS: 0,
      result: null,
      showMarkers: false,
      onRunDetection: () => undefined,
      onToggleMarkers: () => undefined,
    },
    confirm: {
      sites: [{ tooth: 3, center: [0, 0, 0], declaredVariant: "6020" }],
      captures: [],
      disabled: false,
      brushingIndex: null,
      markMode: null,
      rimPointsIndex: null,
      library: [],
      libraryLoading: false,
      identifiedVariantByTooth: new Map<number, string>(),
      compareTooth: null,
      onChangeTooth: () => undefined,
      onChangeDeclaredVariant: () => undefined,
      onCompare: () => undefined,
      onSelectSite: () => undefined,
      onStartBrush: () => undefined,
      onFinishBrush: () => undefined,
      onClearBrushStroke: () => undefined,
      onClearMarkedPoints: () => undefined,
      onStartMark: () => undefined,
      onCancelMark: () => undefined,
      onClearMark: () => undefined,
      onStartRimPoints: () => undefined,
      onFinishRimPoints: () => undefined,
      onCancelRimPoints: () => undefined,
      onClearRim: () => undefined,
      onConfirmAll: () => undefined,
    },
    selectionColumn: {
      selection: initialSelection({
        suggestedModel: "neodent-gm",
        suggestedConstruction: "dess/neodent-gm-scanbody.stl",
        jaw: "lower",
        sites: [{ tooth: 3 }],
      }),
      activeSiteNumber: 1,
      activeTooth: 3,
      libraryState: "ready",
      libraryError: null,
      groups: GROUPS,
      constructionsState: "ready",
      constructionsError: null,
      constructions: CONSTRUCTIONS,
      suggestedModel: "neodent-gm",
      suggestedConstruction: "dess/neodent-gm-scanbody.stl",
      onSelectModel: () => undefined,
      onSelectVariant: () => undefined,
      onSelectConstruction: () => undefined,
      onSelectJaw: () => undefined,
      onChangeOffset: () => undefined,
      achievedOffset: null,
      ceiling: { kind: "idle" },
      clamps: [],
      onRetry: () => undefined,
    },
  };
}

describe("MarkDeclareStage — the seam is deleted, not polished", () => {
  it("mounts the SAME SelectionColumn the verify dialog mounts (system cards, variant cards, construction)", () => {
    const html = renderToStaticMarkup(<MarkDeclareStage {...props()} />);
    // the column's own vocabulary — cards, not a naked select
    expect(html).toContain("decode-column");
    expect(html).toContain("decode-system");
    expect(html).toContain("1 · Implant system");
    expect(html).toContain("2 · Cap variant");
    expect(html).toContain("3 · Construction part");
  });

  it("stacks detect → mark/declare table → selection lists, in the client's order", () => {
    const html = renderToStaticMarkup(<MarkDeclareStage {...props()} />);
    expect(html.indexOf("Detect caps")).toBeLessThan(html.indexOf("confirm-table"));
    expect(html.indexOf("confirm-table")).toBeLessThan(html.indexOf("decode-column"));
  });

  it("renders the old implant-system select nowhere in the stack", () => {
    expect(renderToStaticMarkup(<MarkDeclareStage {...props()} />)).not.toContain("confirm-system");
  });

  it("titles the selection block as part of step 2 — not as a stage of its own", () => {
    const html = renderToStaticMarkup(<MarkDeclareStage {...props()} />);
    expect(html).toContain("Library selection");
    expect(html).not.toContain("Step 3 · Library selection");
  });
});
