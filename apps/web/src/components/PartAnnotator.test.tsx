/**
 * Static-markup component tests (renderToStaticMarkup — node environment, no jsdom, per the
 * repo convention) for the LIBRARY-SIDE annotation mode (client ask 2026-07-24, half one):
 * the marks list with a swatch per kind, the state line, the add/move affordance and its armed
 * instruction, Save/Reset, the honest "this part has no derivable frame" refusal, and the 404
 * restart hint. The click-driven transitions (arm → place → save) live in App handlers and in
 * domain/partFeatures' pure rules, which have their own tests.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { PartAnnotator, type PartAnnotatorContext } from "./PartAnnotator";
import { LibraryBrowser } from "./LibraryBrowser";
import type { DraftFeature } from "../domain/partFeatures";
import type { LibraryCatalogGroup } from "../domain/types";
import { featureHex } from "../viewer/palette";

function draft(overrides: Partial<DraftFeature> = {}): DraftFeature {
  return {
    key: "draft-1",
    kind: "trench",
    azimuthDeg: -22.5,
    radiusMm: 1.47,
    zMm: 1.81,
    source: "auto",
    id: "trench-01",
    point: null,
    ...overrides,
  };
}

function makeContext(overrides: Partial<PartAnnotatorContext> = {}): PartAnnotatorContext {
  return {
    state: "ready",
    errorMessage: null,
    model: "neodent-gm",
    variant: "6020",
    drafts: [
      draft(),
      draft({ key: "draft-2", id: "trench-02", azimuthDeg: 72.2, radiusMm: 1.43 }),
      draft({ key: "draft-3", id: "channel", kind: "channel", azimuthDeg: 176.6, radiusMm: 0.075 }),
    ],
    autoSeeded: true,
    revisedAt: null,
    selectedKey: null,
    kind: "trench",
    armed: false,
    busy: false,
    dirty: false,
    canPlace: true,
    onSelect: () => {},
    onChangeKind: () => {},
    onArm: () => {},
    onCancelArm: () => {},
    onRemove: () => {},
    onSave: () => {},
    onReset: () => {},
    onClose: () => {},
    ...overrides,
  };
}

describe("PartAnnotator", () => {
  it("names the part being marked and states the counts the operator must be able to trust", () => {
    const html = renderToStaticMarkup(<PartAnnotator context={makeContext()} />);
    expect(html).toContain("Annotate features — neodent-gm/6020");
    expect(html).toContain("6020 · 3 features (3 auto, 0 operator)");
    // an auto seed is not persisted yet, and says so
    expect(html).toContain("machine reading — not saved yet");
  });

  it("lists every mark with its own kind color — the same table the 3D spheres use", () => {
    const html = renderToStaticMarkup(<PartAnnotator context={makeContext()} />);
    expect(html).toContain("trench-01 · -22.5° · r 1.47mm");
    expect(html).toContain("trench-02 · +72.2° · r 1.43mm");
    expect(html).toContain(featureHex("trench"));
    expect(html).toContain(featureHex("channel"));
  });

  it("says which mark cannot anchor a rotation instead of hiding it", () => {
    // the channel is seeded and drawn on purpose — the operator sees the bore and expects it
    const html = renderToStaticMarkup(<PartAnnotator context={makeContext()} />);
    expect(html).toContain("channel · +176.6° · r 0.07mm");
    expect(html).toContain("names the axis, not a clock angle");
  });

  it("offers ADD with nothing selected and MOVE once a mark is selected", () => {
    const add = renderToStaticMarkup(<PartAnnotator context={makeContext()} />);
    expect(add).toContain("＋ mark on the part");
    expect(add).not.toContain("⌖ move selected");

    const move = renderToStaticMarkup(
      <PartAnnotator context={makeContext({ selectedKey: "draft-2" })} />,
    );
    expect(move).toContain("⌖ move selected");
    expect(move).toContain("feature-row--selected");
  });

  it("swaps the add button for a cancel + instruction while a part click is armed", () => {
    const html = renderToStaticMarkup(<PartAnnotator context={makeContext({ armed: true })} />);
    expect(html).toContain("click the feature on the 3D part — Esc cancels");
    expect(html).toContain("✕ cancel");
    expect(html).not.toContain("＋ mark on the part");
  });

  it("tells the operator a MOVE is pending, not an add, when one was selected", () => {
    const html = renderToStaticMarkup(
      <PartAnnotator context={makeContext({ armed: true, selectedKey: "draft-1" })} />,
    );
    expect(html).toContain("click the part where that feature really is");
  });

  it("enables Save only on unsaved edits, and Reset only against a stored annotation", () => {
    const clean = renderToStaticMarkup(<PartAnnotator context={makeContext()} />);
    // auto-seeded + not dirty: nothing to save, nothing stored to reset
    expect(clean).toMatch(/Save marks/);
    expect(clean.match(/<button[^>]*disabled[^>]*>Save marks/)).not.toBeNull();
    expect(clean.match(/<button[^>]*disabled[^>]*>Reset to auto/)).not.toBeNull();

    const edited = renderToStaticMarkup(
      <PartAnnotator context={makeContext({ dirty: true, autoSeeded: false, revisedAt: "2026-07-25T10:00:00" })} />,
    );
    expect(edited).toContain("unsaved marks");
    expect(edited).toContain("saved 2026-07-25T10:00:00");
    expect(edited.match(/<button[^>]*disabled[^>]*>Save marks/)).toBeNull();
    expect(edited.match(/<button[^>]*disabled[^>]*>Reset to auto/)).toBeNull();
  });

  it("refuses to place marks on a mesh whose frame could not be derived, and says why", () => {
    const html = renderToStaticMarkup(<PartAnnotator context={makeContext({ canPlace: false })} />);
    expect(html).toContain("could not be fitted on the previewed mesh");
    expect(html.match(/<button[^>]*disabled[^>]*>＋ mark on the part/)).not.toBeNull();
  });

  it("shows the restart hint — not an error — when the running API predates the endpoint", () => {
    const html = renderToStaticMarkup(<PartAnnotator context={makeContext({ state: "unavailable" })} />);
    expect(html).toContain("not available on the running API");
    expect(html).toContain("make serve");
    expect(html).not.toContain("＋ mark on the part");
  });

  it("nudges toward Reset rather than a doomed empty save when every mark was removed", () => {
    const html = renderToStaticMarkup(
      <PartAnnotator context={makeContext({ drafts: [], dirty: true })} />,
    );
    expect(html).toContain("No marks on this part");
    expect(html.match(/<button[^>]*disabled[^>]*>Save marks/)).not.toBeNull();
  });
});

function makeGroups(): LibraryCatalogGroup[] {
  return [
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
}

describe("LibraryBrowser annotate affordance", () => {
  const base = {
    state: "ready" as const,
    errorMessage: null,
    groups: makeGroups(),
    activeModel: "neodent-gm",
    onSelectModel: () => {},
    onPreviewEntry: () => {},
    onRetry: () => {},
    onClose: () => {},
  };

  it("offers annotation only for the card actually IN the 3D viewer", () => {
    const notPreviewed = renderToStaticMarkup(
      <LibraryBrowser {...base} previewedKey={null} onAnnotateEntry={() => {}} annotator={null} />,
    );
    expect(notPreviewed).not.toContain("✎ Annotate features");

    const previewed = renderToStaticMarkup(
      <LibraryBrowser
        {...base}
        previewedKey="neodent-gm/6020"
        onAnnotateEntry={() => {}}
        annotator={null}
      />,
    );
    expect(previewed).toContain("✎ Annotate features");
    expect(previewed).toContain("6020 is in the 3D viewer");
  });

  it("renders no annotate affordance at all in a read-only embedding", () => {
    const html = renderToStaticMarkup(<LibraryBrowser {...base} previewedKey="neodent-gm/6020" />);
    expect(html).not.toContain("✎ Annotate features");
  });

  it("embeds the open annotation panel", () => {
    const html = renderToStaticMarkup(
      <LibraryBrowser
        {...base}
        previewedKey="neodent-gm/6020"
        onAnnotateEntry={() => {}}
        annotator={makeContext()}
      />,
    );
    expect(html).toContain("Annotate features — neodent-gm/6020");
    expect(html).toContain("6020 · 3 features (3 auto, 0 operator)");
  });
});
