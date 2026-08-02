/**
 * THE UNRUN CONSTRUCTION PART, PREVIEWED ALONE (§10-M2's "natural next slice",
 * 2026-08-02) — statically rendered per the repo convention (renderToStaticMarkup
 * in node; WebGL itself lives behind a `viewerSlot` prop, stubbed here exactly as
 * DeliverPreview.test.tsx stubs it, since VerifyViewer's setup happens inside a
 * useEffect that renderToStaticMarkup never runs).
 *
 * Retargeted from nothing (new component): pinning the View half's markup contract
 * (data-role, the caption's presence, an honest absence when the row carries no
 * mesh_url) and the container's initial mount (mesh_url followed verbatim, never
 * assembled — the 404 wording is asserted via the View's `error` prop directly,
 * the same posture DeliverPreview.test.tsx uses, since effects never fire here).
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { PartPreview, PartPreviewView } from "./PartPreview";

const stubViewer = <div data-role="viewer-stub" />;

function view(overrides: Partial<Parameters<typeof PartPreviewView>[0]> = {}) {
  return renderToStaticMarkup(
    <PartPreviewView
      label="Conical scanbody"
      meshUrl="/api/constructions/dess/conical-scanbody.stl/mesh"
      busy={false}
      error={null}
      viewerSlot={stubViewer}
      {...overrides}
    />,
  );
}

describe("PartPreviewView — the armed candidate's own pane", () => {
  it("renders the pane and mounts the viewer slot inside its canvas", () => {
    const html = view();
    expect(html).toContain('data-role="library-part-preview"');
    expect(html).toContain('data-role="viewer-stub"');
  });

  it("names the part in the pane's own title", () => {
    expect(view()).toContain("Conical scanbody");
  });

  it("carries the unrun-part caption — never the run-mesh caption's words", () => {
    const html = view();
    expect(html).toContain('data-role="library-part-preview-caption"');
    // renderToStaticMarkup HTML-escapes the apostrophe (DeclarePanes.test.tsx /
    // MainStage.test.tsx's own convention for asserting on rendered text)
    expect(html).toContain("vendor&#x27;s catalog part");
    expect(html.toLowerCase()).not.toContain("run&#x27;s own");
  });

  it("names the loading part while busy", () => {
    const html = view({ busy: true });
    expect(html).toContain('data-role="library-part-preview-busy"');
    expect(html).toContain("Loading Conical scanbody");
  });

  it("renders a refusal that NAMES THE PART, never a generic failure", () => {
    // task doctrine: "a 404 names the part, never a generic failure" — the loader's
    // own message is three.js's fetch-status text, which never carries the BFF's
    // JSON detail, so the container (tested below) prefixes the part's own label
    const html = view({
      error: '"Conical scanbody" did not load: fetch for ".../mesh" responded with 404',
    });
    expect(html).toContain('data-role="library-part-preview-error"');
    expect(html).toContain('role="alert"');
    expect(html).toContain("Conical scanbody");
    expect(html).toContain("404");
  });

  it("an absent mesh_url renders the stated gap, never a client-assembled URL or a dead viewer", () => {
    // a row from a BFF that predates the construction-mesh route (the stale-server
    // trap) — CLAUDE.md is explicit that this app never invents a path
    const html = view({ meshUrl: null });
    expect(html).toContain('data-role="library-part-preview-pending"');
    expect(html).not.toContain('data-role="viewer-stub"');
    expect(html).not.toContain('data-role="library-part-preview-caption"');
  });
});

describe("PartPreview — the container, statically (effects do not run)", () => {
  it("mounts the real viewer surface, named for the armed part", () => {
    const html = renderToStaticMarkup(
      <PartPreview
        label="Conical scanbody"
        meshUrl="/api/constructions/dess/conical-scanbody.stl/mesh"
      />,
    );
    expect(html).toContain('data-role="library-part-preview"');
    expect(html).toContain("Preview: Conical scanbody");
  });

  it("a null mesh_url mounts the gap, not a viewer with nothing to load", () => {
    const html = renderToStaticMarkup(
      <PartPreview label="Conical scanbody" meshUrl={null} />,
    );
    expect(html).toContain('data-role="library-part-preview-pending"');
  });
});
