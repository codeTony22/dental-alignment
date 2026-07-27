/**
 * THE THREE-PANEL VERIFY's chrome (renderToStaticMarkup — the 3D canvases are injected by the
 * stage through `renderViewer` and are absent here, which is exactly what makes the panel logic
 * testable in the node environment).
 *
 * Pinned: three named panes, an eye toggle and an opacity slider per layer, a layer whose
 * geometry has not arrived being DISABLED rather than silently missing, the honest notice a pane
 * shows instead of an empty canvas, and the colorbar carrying the server's own sign convention,
 * clamp note and PUBLISHED stats.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { VerifyPanels, type VerifyPanelSpec } from "./VerifyPanels";
import type { DeviationScale, DeviationStats } from "../domain/types";

const SCALE: DeviationScale = {
  clampMm: 0.5,
  minMm: -0.5,
  maxMm: 0.5,
  colormap: "RdBu_r",
  signConvention: "+ = scan outside the cap surface",
  dataMinMm: -4.6093,
  dataMaxMm: 4.2481,
  footprintBandMm: 1.2,
};

const STATS: DeviationStats = {
  rmsMm: 0.427,
  p90Mm: 0.732,
  nFootprint: 4910,
  nSamples: 12000,
  source: "area-uniform surface samples (the acceptance difference map)",
};

function panels(overrides: Partial<Record<"library" | "scan" | "union", Partial<VerifyPanelSpec>>> = {}): VerifyPanelSpec[] {
  return [
    {
      id: "library",
      title: "1 · Library part",
      caption: "neodent-gm 6020 — neodent-gm-6020.stl",
      layers: [
        { id: "part", label: "Library cap", swatch: "#2fa75f", visible: true, opacity: 1, available: true },
      ],
      notice: null,
      busy: false,
      ...overrides.library,
    },
    {
      id: "scan",
      title: "2 · Scanned cap",
      caption: "18,204 triangles within 9 mm of the mark",
      layers: [
        { id: "scan", label: "Scan region", swatch: "#f0e4cb", visible: true, opacity: 1, available: true },
      ],
      notice: null,
      busy: false,
      ...overrides.scan,
    },
    {
      id: "union",
      title: "3 · Union — coloured by deviation",
      caption: "the seated cap against the scan",
      layers: [
        { id: "scan", label: "Scan region", swatch: "#f0e4cb", visible: true, opacity: 0.45, available: true },
        { id: "deviation", label: "Seated cap (deviation)", swatch: null, visible: true, opacity: 1, available: true },
      ],
      notice: null,
      busy: false,
      colorbar: { scale: SCALE, stats: STATS, scaleId: "signed" as const, onSelectScale: () => {} },
      ...overrides.union,
    },
  ];
}

function render(specs: VerifyPanelSpec[], extra: Partial<Parameters<typeof VerifyPanels>[0]> = {}) {
  return renderToStaticMarkup(
    <VerifyPanels
      panels={specs}
      onToggleLayer={() => {}}
      onChangeOpacity={() => {}}
      linked={false}
      onToggleLinked={() => {}}
      {...extra}
    />,
  );
}

describe("VerifyPanels", () => {
  it("renders the client's three panes, in order", () => {
    const html = render(panels());
    expect(html).toContain("1 · Library part");
    expect(html).toContain("2 · Scanned cap");
    expect(html).toContain("3 · Union — coloured by deviation");
    expect(html.indexOf("1 · Library part")).toBeLessThan(html.indexOf("2 · Scanned cap"));
    expect(html.indexOf("2 · Scanned cap")).toBeLessThan(html.indexOf("3 · Union"));
  });

  it("gives every layer an eye toggle and an opacity slider", () => {
    const html = render(panels());
    expect(html.match(/class="verify-layer"/g)?.length).toBe(4); // 1 + 1 + 2 layers
    expect(html.match(/verify-layer__eye/g)?.length).toBeGreaterThanOrEqual(4);
    expect(html.match(/type="range"/g)?.length).toBe(4);
    expect(html).toContain('aria-label="Hide Library cap"');
    expect(html).toContain("45%"); // the union's scan starts half-transparent so the cap reads through
  });

  it("disables a layer whose geometry has not arrived, instead of hiding it", () => {
    const html = render(
      panels({
        union: {
          layers: [
            { id: "scan", label: "Scan region", swatch: "#f0e4cb", visible: true, opacity: 0.45, available: true },
            { id: "deviation", label: "Seated cap (deviation)", swatch: null, visible: true, opacity: 1, available: false },
          ],
        },
      }),
    );
    expect(html).toContain("Seated cap (deviation)");
    expect(html).toMatch(/aria-label="Hide Seated cap \(deviation\)"[^>]*disabled/);
  });

  it("shows an honest notice instead of an empty canvas", () => {
    const html = render(
      panels({ union: { notice: "No seated result for this site yet — the measured overlay appears once Process has run it." } }),
    );
    expect(html).toContain("No seated result for this site yet");
    expect(html).toContain("verify-panel__overlay--notice");
  });

  it("shows the busy state in place of the notice while loading", () => {
    const html = render(panels({ scan: { busy: true, notice: "should not show" } }));
    expect(html).toContain("loading…");
    expect(html).not.toContain("should not show");
  });

  it("hides a layer's slider behind the eye — a hidden layer's opacity is meaningless", () => {
    const html = render(
      panels({
        scan: {
          layers: [
            { id: "scan", label: "Scan region", swatch: "#f0e4cb", visible: false, opacity: 1, available: true },
          ],
        },
      }),
    );
    expect(html).toMatch(/id="opacity-scan-scan"[^>]*disabled/);
    expect(html).toContain('aria-label="Show Scan region"');
  });

  it("draws the colorbar with the server's convention, ticks, clamp note and published stats", () => {
    const html = render(panels());
    expect(html).toContain("linear-gradient(to right");
    expect(html).toContain("−0.50");
    expect(html).toContain("+0.50");
    expect(html).toContain("+ = scan outside the cap surface");
    expect(html).toContain("clamped — this site spans -4.61 to +4.25 mm");
    expect(html).toContain("RMS 0.427 mm");
    expect(html).toContain("p90 0.732 mm");
    expect(html).toContain("area-uniform surface samples");
    expect(html).toContain("not measured");
  });

  it("puts the colorbar on the union pane only", () => {
    const html = render(panels());
    expect(html.match(/verify-colorbar__bar/g)?.length).toBe(1);
  });

  it("offers the link-views toggle and reflects its state", () => {
    expect(render(panels())).toContain("⛓ link views");
    expect(render(panels(), { linked: true })).toContain("⛓ views linked");
    expect(render(panels(), { linked: true })).toContain('aria-pressed="true"');
  });

  it("renders the injected viewer for each pane when one is supplied", () => {
    const html = render(panels(), {
      renderViewer: (panelId) => <div data-testid={`viewer-${panelId}`} />,
    });
    expect(html).toContain('data-testid="viewer-library"');
    expect(html).toContain('data-testid="viewer-scan"');
    expect(html).toContain('data-testid="viewer-union"');
  });

  /**
   * THE TWO COLOUR SCALES (client ask 2026-07-25): ours (signed ±clamp, RdBu) and RealGUIDE's
   * "Contacts" (absolute 0.00-0.60). Both are offered on the union pane, each says what it shows,
   * and the SIGNED one is the only one that carries direction — which the Contacts legend states
   * out loud so switching bars can never quietly lose the proud/sunk distinction.
   */
  it("offers both colour scales on the union pane, labelled", () => {
    const html = render(panels());
    expect(html).toContain("Signed ±0.50 mm");
    expect(html).toContain("Contacts 0.00–0.60 mm");
    expect(html).toContain('role="radiogroup"');
  });

  it("shows the SIGNED scale's own convention, ticks and clamp note when selected", () => {
    const html = render(panels());
    expect(html).toContain("+ = scan outside the cap surface");
    expect(html).toContain("−0.50");
    expect(html).toContain("+0.50");
    expect(html).toContain("clamped — this site spans");
  });

  it("switches ticks and legend for the Contacts scale, and says it has no direction", () => {
    const html = render(
      panels({
        union: {
          colorbar: {
            scale: SCALE,
            stats: STATS,
            scaleId: "contacts" as const,
            onSelectScale: () => {},
          },
        },
      }),
    );
    expect(html).toContain("0.00");
    expect(html).toContain("0.60");
    expect(html).not.toContain("+0.50");
    expect(html).toContain("absolute distance — no direction");
    expect(html).toContain("switch to the signed scale to see proud vs sunk");
    // the ±clamp note belongs to the signed window; it must not ride along on an absolute bar
    expect(html).not.toContain("clamped — this site spans");
    // the PUBLISHED stats are the same measurement either way — the scale colours a read, it
    // does not re-measure it
    expect(html).toContain("RMS 0.427 mm");
  });

  it("marks the selected scale, and only that one", () => {
    const html = render(panels());
    expect(html.match(/verify-colorbar__scale--selected/g)?.length).toBe(1);
    expect(html).toMatch(/aria-checked="true"[^>]*class="verify-colorbar__scale verify-colorbar__scale--selected"/);
  });
});

/**
 * THE 3D PANELS ARE THE PRODUCT (client, 2026-07-26): "they must dominate … and a per-panel
 * maximise/expand control."
 *
 * Maximising UNMOUNTS the other two rather than hiding them — three live WebGL contexts
 * rendering off-screen at every frame is exactly the cost this control exists to spend on the
 * one pane the operator is actually reading.
 */
describe("VerifyPanels — per-panel maximise", () => {
  it("offers a maximise control on every pane when the caller wires one", () => {
    const html = render(panels(), { onToggleMaximized: () => {} });
    expect(html.match(/verify-panel__maximize/g)?.length).toBe(3);
    expect(html).toContain('aria-label="Maximise 1 · Library part"');
    expect(html).toContain('aria-label="Maximise 3 · Union — coloured by deviation"');
  });

  it("renders no maximise control at all without that wiring", () => {
    expect(render(panels())).not.toContain("verify-panel__maximize");
  });

  it("gives the whole stage to the maximised pane and drops the other two", () => {
    const html = render(panels(), { onToggleMaximized: () => {}, maximizedId: "union" });
    expect(html).toContain("verify-panels__grid--maximized");
    expect(html).toContain("3 · Union — coloured by deviation");
    expect(html).not.toContain("1 · Library part");
    expect(html).not.toContain("2 · Scanned cap");
    expect(html).toContain('aria-label="Restore 3 · Union — coloured by deviation to the three-panel view"');
    expect(html).toContain("⤡ show all three");
  });

  it("cannot link views while only one pane is on screen", () => {
    const all = render(panels(), { onToggleMaximized: () => {} });
    const one = render(panels(), { onToggleMaximized: () => {}, maximizedId: "scan" });
    expect(all.match(/<button[^>]*disabled[^>]*>⛓ link views/)).toBeNull();
    expect(one.match(/<button[^>]*disabled[^>]*>⛓ link views/)).not.toBeNull();
  });

  it("says what a pane is busy doing when 'loading…' would understate it", () => {
    const html = render(
      panels({ union: { busy: true, busyMessage: "seating this selection on the scan — preview…" } }),
    );
    expect(html).toContain("seating this selection on the scan — preview…");
    expect(html).not.toContain(">loading…<");
  });
});
