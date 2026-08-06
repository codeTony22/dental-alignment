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
import type { PreviewTab } from "../domain/deliver";

const stubViewer = <div data-role="viewer-stub" />;

const TABS: readonly PreviewTab[] = [
  {
    key: "alignment",
    label: "1 · Healing-cap alignment",
    filename: "case-a-arch-with-healingcaps.stl",
    tooth: null,
    layers: [{ filename: "case-a-arch-with-healingcaps.stl", role: "arch" }],
  },
  {
    key: "construction-in-arch",
    label: "2 · Construction in arch",
    filename: "case-a-arch-with-constructions.stl",
    tooth: null,
    layers: [{ filename: "case-a-arch-with-constructions.stl", role: "arch" }],
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
  return renderToStaticMarkup(
    <DeliverPreviewView
      tabs={TABS}
      activeKey="alignment"
      onSelectTab={() => undefined}
      busy={false}
      error={null}
      viewerSlot={stubViewer}
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
