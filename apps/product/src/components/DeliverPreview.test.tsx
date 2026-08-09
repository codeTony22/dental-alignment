/**
 * The 3D preview tabs' chrome (client 2026-08-01), statically rendered — the repo
 * convention: renderToStaticMarkup in node asserts the CONTROL SURFACE (which tabs
 * render, which one is selected, the honest busy/error states), never WebGL. Camera
 * work itself is the viewer package's own browser-only surface.
 *
 * The CONTAINER is also rendered statically here, the same way MainStage.test.tsx
 * renders MainStage directly: VerifyViewer's WebGL setup happens inside a
 * useEffect, which renderToStaticMarkup never runs, so the container's initial
 * markup is exactly its chrome plus the viewer's empty mount div.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { DeliverPreview, DeliverPreviewView } from "./DeliverPreview";
import { previewLayerRows, type PreviewMeshRole, type PreviewTab } from "../domain/deliver";

const stubViewer = <div data-role="viewer-stub" />;

// tab 1/2 carry TWO layers (arch + one part role) once the package includes the
// composite's pieces, not only the merged file — the shape `layerRows`/the layer
// HUD are built against; tab 3 stays single-layer, the fallback case
const TABS: readonly PreviewTab[] = [
  {
    key: "alignment",
    label: "1 · Healing-cap alignment",
    filename: "case-a-arch-with-healingcaps.stl",
    tooth: null,
    layers: [
      { filename: "case-a-arch-capless.stl", role: "arch" },
      { filename: "case-a-19-healingcap-aligned.stl", role: "cap" },
    ],
  },
  {
    key: "construction-in-arch",
    label: "2 · Construction in arch",
    filename: "case-a-arch-with-constructions.stl",
    tooth: null,
    layers: [
      { filename: "case-a-arch-capless.stl", role: "arch" },
      { filename: "case-a-19-scanbody-acme.stl", role: "construction" },
    ],
  },
  {
    key: "construction-tooth-19",
    label: "3 · Construction alone — tooth 19",
    filename: "case-a-19-prosthesis_cad.stl",
    tooth: 19,
    layers: [{ filename: "case-a-19-prosthesis_cad.stl", role: "construction" }],
  },
];

function view(overrides: Partial<Parameters<typeof DeliverPreviewView>[0]> = {}) {
  const tabs = overrides.tabs ?? TABS;
  const activeKey = overrides.activeKey ?? "alignment";
  // DEFAULTED THE SAME WAY THE CONTAINER DERIVES IT (`previewLayerRows(active)`),
  // so a test that only cares about the tab strip or the busy/error notices never
  // has to know the layer HUD exists — exactly like the container's own real prop.
  const active = tabs.find((tab) => tab.key === activeKey) ?? null;
  const layerRows = active !== null ? previewLayerRows(active) : [];
  return renderToStaticMarkup(
    <DeliverPreviewView
      tabs={TABS}
      activeKey="alignment"
      onSelectTab={() => undefined}
      busy={false}
      error={null}
      viewerSlot={stubViewer}
      layerRows={layerRows}
      {...overrides}
    />,
  );
}

describe("DeliverPreviewView — the tab strip", () => {
  it("renders one button per tab, in the given order, with the given labels", () => {
    const html = view();
    const alignment = html.indexOf("1 · Healing-cap alignment");
    const arch = html.indexOf("2 · Construction in arch");
    const tooth = html.indexOf("3 · Construction alone — tooth 19");
    expect(alignment).toBeGreaterThan(-1);
    expect(arch).toBeGreaterThan(alignment);
    expect(tooth).toBeGreaterThan(arch);
  });

  it("marks the active tab, and only the active tab", () => {
    const html = view({ activeKey: "construction-in-arch" });
    expect(html).toMatch(
      /data-key="construction-in-arch"[^>]*aria-selected="true"/,
    );
    expect(html).toMatch(/data-key="alignment"[^>]*aria-selected="false"/);
  });

  it("no tabs at all renders nothing — an honest absence, never an empty strip", () => {
    expect(view({ tabs: [] })).toBe("");
  });

  it("names the loading tab while busy", () => {
    const html = view({ busy: true, activeKey: "construction-in-arch" });
    expect(html).toContain("Loading 2 · Construction in arch");
  });

  it("renders a refusal in the loader's own words", () => {
    const html = view({ error: "the preview mesh did not load — 404" });
    expect(html).toContain('role="alert"');
    expect(html).toContain("the preview mesh did not load — 404");
  });

  it("mounts the viewer slot inside the canvas", () => {
    expect(view()).toContain('data-role="viewer-stub"');
  });
});

describe("DeliverPreview — the container, statically (effects do not run)", () => {
  it("mounts the real viewer surface and opens on the first tab", () => {
    const html = renderToStaticMarkup(<DeliverPreview caseId="case-a" tabs={TABS} />);
    expect(html).toContain('data-key="alignment"');
    expect(html).toMatch(/data-key="alignment"[^>]*aria-selected="true"/);
    // the package's VerifyViewer mount div, named for the tab it is about to load
    expect(html).toContain("Preview: 1 · Healing-cap alignment");
  });

  it("no tabs mounts nothing", () => {
    expect(renderToStaticMarkup(<DeliverPreview caseId="case-a" tabs={[]} />)).toBe("");
  });
});

/* THE PER-LAYER VISIBILITY TOGGLE (client 2026-08-09: "a tool like the panels to hide
 * certain parts of the library, construction, or scan … to make it appear more
 * visually appealing" — PRESENTATION ONLY over the 3D preview, never the artifacts
 * list or a download). Pinned here at the view level: a component with only props
 * (never fetches, never a request body) is the cheapest place a reviewer can see that
 * the toggle cannot possibly touch a served fact — there is no prop on
 * `DeliverPreviewProps`/`DeliverPreviewViewProps` through which it could. */
describe("DeliverPreviewView — the layer toggle", () => {
  it("a composed tab (arch + cap) renders one row per role, each with its own eye/swatch/label", () => {
    const html = view();
    expect(html).toContain('data-role="deliver-mesh-preview-layers"');
    expect((html.match(/data-role="preview-layer-row"/g) ?? []).length).toBe(2);
    expect(html).toMatch(/data-layer-role="arch"/);
    expect(html).toMatch(/data-layer-role="cap"/);
    // the viewer package's own role words/colours — this panel invents neither
    // (renderToStaticMarkup HTML-escapes the apostrophe)
    expect(html).toContain("Doctor&#x27;s scan");
    expect(html).toContain("Healing cap (aligned)");
    expect(html).toContain("#f2e3a6"); // PALETTE.arch
    expect(html).toContain("#2fa75f"); // PALETTE.cap
  });

  it("every row starts VISIBLE (aria-pressed true, the 'on' eye) with no hiddenRoles given", () => {
    const html = view();
    expect(html).toMatch(/data-layer-role="arch"[^>]*aria-pressed="true"/);
    expect(html).toMatch(/data-layer-role="cap"[^>]*aria-pressed="true"/);
    expect(html).toContain("verify-layer__eye--on");
  });

  it("a role in hiddenRoles renders OFF — aria-pressed false, no --on class on that row", () => {
    const html = view({ hiddenRoles: new Set<PreviewMeshRole>(["cap"]) });
    expect(html).toMatch(/data-layer-role="arch"[^>]*aria-pressed="true"/);
    expect(html).toMatch(/data-layer-role="cap"[^>]*aria-pressed="false"/);
  });

  it("a single-layer tab (construction alone) renders no layer HUD at all", () => {
    const html = view({ activeKey: "construction-tooth-19" });
    expect(html).not.toContain('data-role="deliver-mesh-preview-layers"');
    expect(html).not.toContain('data-role="preview-layer-row"');
  });

  it("no active tab (an empty tabs list already returns nothing, but a dangling key must not crash) renders no HUD", () => {
    const html = view({ activeKey: "no-such-tab", layerRows: [] });
    expect(html).not.toContain('data-role="deliver-mesh-preview-layers"');
  });

  it("hiding every layer changes nothing OUTSIDE the layer HUD — the tab strip is untouched", () => {
    const shown = view({ hiddenRoles: new Set<PreviewMeshRole>() });
    const hiddenAll = view({ hiddenRoles: new Set<PreviewMeshRole>(["arch", "cap"]) });
    const tabStrip = (html: string): string =>
      html.slice(
        html.indexOf('data-role="deliver-mesh-preview-tabs"'),
        html.indexOf('data-role="deliver-mesh-preview-canvas"'),
      );
    expect(tabStrip(hiddenAll)).toBe(tabStrip(shown));
  });
});

describe("DeliverPreview — the container derives the layer rows and hides nothing by default", () => {
  it("a composed active tab's rows reach the view, all visible", () => {
    const html = renderToStaticMarkup(<DeliverPreview caseId="case-a" tabs={TABS} />);
    expect(html).toContain('data-role="deliver-mesh-preview-layers"');
    expect(html).toMatch(/data-layer-role="arch"[^>]*aria-pressed="true"/);
    expect(html).toMatch(/data-layer-role="cap"[^>]*aria-pressed="true"/);
  });

  it("switching to a single-layer tab shows no layer HUD (static: activeKey starts there)", () => {
    // activeKey defaults to the FIRST tab, so mount directly on the single-layer one
    // by handing a tabs list whose first entry is tab 3
    const single = [TABS[2]!];
    const html = renderToStaticMarkup(<DeliverPreview caseId="case-a" tabs={single} />);
    expect(html).not.toContain('data-role="deliver-mesh-preview-layers"');
  });
});
