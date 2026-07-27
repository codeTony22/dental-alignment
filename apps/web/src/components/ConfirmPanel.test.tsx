/**
 * Static-markup component tests for the step-2 Mark & declare table (renderToStaticMarkup —
 * node environment, no jsdom, per the repo convention).
 *
 * TWO RETIREMENTS PINNED HERE (client, 2026-07-26: "ONE cohesive flow"):
 *  - the plain implant-system <select> ("confirm-system") is GONE — the system is chosen on
 *    the SelectionColumn cards mounted right below this table, the same component the verify
 *    dialog mounts;
 *  - the "view part" button that SWAPPED the part into the main stage is GONE — each declared
 *    row now carries a "compare ⇥" control that points the docked compare pane at that row's
 *    variant, so the scan never leaves the screen.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ConfirmPanel } from "./ConfirmPanel";
import type { CaptureAssessment, ConfirmedSite, LibraryVariant } from "../domain/types";

const LIBRARY: readonly LibraryVariant[] = [
  { variant: "6020", rimDiameterMm: 6.16, heightMm: 3.38, meshUrl: "/api/library/6020.stl" },
  { variant: "7030", rimDiameterMm: 7.09, heightMm: 4.4, meshUrl: "/api/library/7030.stl" },
  { variant: "legacy-nodims", rimDiameterMm: null, heightMm: null, meshUrl: "/api/library/x.stl" },
];

function makeSites(): ConfirmedSite[] {
  return [
    { tooth: 3, center: [0, 0, 0], declaredVariant: "6020" },
    { tooth: 14, center: [1, 1, 1], declaredVariant: "7030" },
  ];
}

type PanelProps = Parameters<typeof ConfirmPanel>[0];

function renderPanel(overrides: Partial<PanelProps> = {}): string {
  const props: PanelProps = {
    sites: makeSites(),
    captures: [],
    disabled: false,
    brushingIndex: null,
    markMode: null,
    rimPointsIndex: null,
    library: LIBRARY,
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
    ...overrides,
  };
  return renderToStaticMarkup(<ConfirmPanel {...props} />);
}

function count(html: string, needle: string): number {
  return html.split(needle).length - 1;
}

describe("ConfirmPanel — the retired seams stay retired (2026-07-26)", () => {
  it("never renders the plain implant-system select — the SelectionColumn cards own that choice", () => {
    expect(renderPanel()).not.toContain("confirm-system");
  });

  it("never renders the old main-stage swap button", () => {
    const html = renderPanel();
    expect(html).not.toContain(">view part<");
    expect(html).not.toContain("viewing ✓");
  });
});

describe("ConfirmPanel — the compare control (docked pane, scan stays on screen)", () => {
  it("every declared row offers 'compare ⇥', none pressed while the pane shows no row's variant", () => {
    const html = renderPanel();
    expect(count(html, "compare ⇥")).toBe(2);
    expect(html).not.toContain('aria-pressed="true"');
  });

  it("the row whose variant the pane is showing reads pressed; the other stays normal", () => {
    const html = renderPanel({ compareTooth: 3 });
    expect(count(html, 'aria-pressed="true"')).toBe(1);
    expect(count(html, 'aria-pressed="false"')).toBe(1);
    // row order is tooth 3 then tooth 14 — the pressed control belongs to tooth 3's row
    expect(html.indexOf('aria-pressed="true"')).toBeLessThan(html.indexOf('aria-pressed="false"'));
  });

  it("undeclared row: no compare control and no dims text (nothing selected to compare)", () => {
    const html = renderPanel({
      sites: [{ tooth: 3, center: [0, 0, 0] }],
    });
    expect(html).not.toContain("compare ⇥");
    expect(html).not.toContain("confirm-table__dims");
  });
});

describe("ConfirmPanel — selected variant's dimensions stay visible", () => {
  it("shows the chosen part's Ø × height as plain text next to the compare control", () => {
    const html = renderPanel();
    // one dims span per declared row, carrying that row's OWN variant dims
    expect(count(html, "confirm-table__dims")).toBe(2);
    expect(html).toContain(">Ø6.16 × 3.38 mm</span>");
    expect(html).toContain(">Ø7.09 × 4.4 mm</span>");
  });

  it("omits the dims text (but keeps the compare control) when the catalog has no dims for the variant", () => {
    const html = renderPanel({
      sites: [{ tooth: 3, center: [0, 0, 0], declaredVariant: "legacy-nodims" }],
    });
    expect(html).toContain("compare ⇥");
    expect(html).not.toContain("confirm-table__dims");
  });
});

describe("capture-gate surfacing (intake advisory, before marks are invested)", () => {
  const rescan: CaptureAssessment = {
    verdict: "rescan",
    checks: [
      {
        name: "rim_arc",
        value: 0.542,
        boundPass: 0.92,
        boundRescan: 0.55,
        verdict: "rescan",
        message: "Rescan the rim on the tongue-facing (lingual) side — 46% of the ring is missing",
      },
    ],
  };
  const pass: CaptureAssessment = { verdict: "pass", checks: [] };

  it("shows a per-row capture chip when an assessment exists, a placeholder otherwise", () => {
    const html = renderPanel({ captures: [rescan, null] });
    expect(html).toContain("chip--capture-rescan");
    expect(html).toContain("RESCAN");
    expect(html).toContain("confirm-table__capture-none");
  });

  it("raises the red chair-side banner naming the rescan site's tooth and instruction", () => {
    const html = renderPanel({ captures: [rescan, pass] });
    expect(html).toContain("capture-banner");
    expect(html).toContain("Tooth 3");
    expect(html).toContain("46% of the ring is missing");
    expect(html).toContain("while the patient is in the chair");
  });

  it("stays banner-free when every assessed site passes", () => {
    const html = renderPanel({ captures: [pass, pass] });
    expect(html).not.toContain("capture-banner");
  });
});

/**
 * The dialog's SelectionColumn and this table declare the SAME thing, so the row must be able
 * to state a cap the top-level library list does not carry — an archived catalog id — instead
 * of rendering a blank select.
 */
describe("ConfirmPanel — archived declarations", () => {
  it("carries a cap chosen on the selection cards that this list does not hold (an archived id)", () => {
    const html = renderPanel({
      sites: [{ tooth: 3, center: [0, 0, 0], declaredVariant: "superseded-2026-07-13--5020" }],
    });
    expect(html).toContain('value="superseded-2026-07-13--5020"');
    expect(html).toContain("chosen on the selection cards");
  });

  it("does not invent that extra option for a variant the list already has", () => {
    expect(renderPanel()).not.toContain("chosen on the selection cards");
  });

  it("states why the cap list is empty rather than silently offering nothing", () => {
    const html = renderPanel({
      library: [],
      noSystemHint: "No implant system selected — choose one on the cards below.",
    });
    expect(html).toContain("No implant system selected");
  });
});
