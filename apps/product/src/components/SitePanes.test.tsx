/**
 * THE SHARED PANE SURFACE (SitePanesView), statically rendered per the repo convention —
 * the three viewer slots are props precisely so WebGL never enters a test.
 *
 * DeclarePanes.test.tsx and AdjustStage.test.tsx cover what each STAGE puts around the
 * panes; what belongs here is what the panes owe BOTH stages and neither may re-answer:
 *
 *   - the on-glass hint (does this pane want a click, and for what);
 *   - the 1/2/3 switcher, so moving between maximized panes is one click, not three;
 *   - the subtitles that say WHICH cap and WHICH implant system is on screen.
 *
 * Every prop these exercise is optional: SitePanesView is called by DeclareStage and
 * AdjustStage alike, and a pane surface that only compiled for one of them would be a
 * regression in the very thing the extraction bought.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { SitePanesView, scanPaneCaption, type SitePanesViewProps } from "./SitePanes";
import { sitePreviewPayload } from "../testing/fixtures";

function view(overrides: Partial<SitePanesViewProps> = {}) {
  return renderToStaticMarkup(
    <SitePanesView
      variantLabel="5020"
      notices={{ part: null, scan: null, union: null }}
      partBusy={false}
      scanBusy={false}
      scanCaption="Tooth 19 · 1,234 triangles within 9 mm of the site's centre"
      unionCaption="the previewed seat"
      unionBusy={false}
      unionBusyMessage={null}
      payload={sitePreviewPayload()}
      libraryViewer={<div data-role="stub-library-viewer" />}
      scanViewer={<div data-role="stub-scan-viewer" />}
      unionViewer={<div data-role="stub-union-viewer" />}
      {...overrides}
    />,
  );
}

/** The caption a pane renders, in document order (pane 1, 2, 3). */
function captions(markup: string): string[] {
  return [...markup.matchAll(/data-role="pane-caption"[^>]*>([^<]*)</g)].map((m) => m[1]!);
}

describe("SitePanesView — the on-glass hint", () => {
  it("says nothing on the glass when no pane is armed (both callers, today)", () => {
    expect(view()).not.toContain('data-role="pane-hint"');
  });

  it("prints the hint for the named pane only", () => {
    const markup = view({ hints: { scan: "click the matching spot to close pair 2" } });
    expect(markup).toContain("click the matching spot to close pair 2");
    expect([...markup.matchAll(/data-role="pane-hint"/g)]).toHaveLength(1);
  });

  it("can arm all three panes at once (fit-by-points arms the part AND the scan)", () => {
    const markup = view({
      hints: {
        library: "click to set point 1 on the library part",
        scan: "then click the same spot on the scan",
        union: "or close the pair here",
      },
    });
    expect([...markup.matchAll(/data-role="pane-hint"/g)]).toHaveLength(3);
  });

  it("wears the class the pointer-events guard hangs off", () => {
    // styles.css records the live bug this prevents: a notice overlay printed over the
    // stage swallowed the very click it was inviting (review 2026-07-26).
    expect(view({ hints: { scan: "click the trench" } })).toContain(
      'class="verify-panel__hint"',
    );
  });

  it("lifts the union pane's hint clear of the colorbar that owns its bottom strip", () => {
    expect(view({ hints: { union: "within tolerance" } })).toContain(
      "verify-panel__hint--raised",
    );
    expect(view({ hints: { union: "within tolerance" }, payload: null })).not.toContain(
      "verify-panel__hint--raised",
    );
  });

  it("treats an empty hint as no hint — a blank strip is chrome with nothing to say", () => {
    expect(view({ hints: { scan: "" } })).not.toContain('data-role="pane-hint"');
    expect(view({ hints: { scan: null } })).not.toContain('data-role="pane-hint"');
  });
});

describe("SitePanesView — the 1/2/3 switcher", () => {
  it("stays off the toolbar while all three panes are on screen", () => {
    expect(view({ onToggleLinked: () => undefined })).not.toContain(
      'data-role="pane-switch"',
    );
  });

  it("offers all three numbers while one pane is the stage", () => {
    const markup = view({
      onToggleLinked: () => undefined,
      maximizedId: "library",
      onToggleMaximized: () => undefined,
    });
    const switches = [...markup.matchAll(/data-role="pane-switch" data-pane="([a-z]+)"/g)];
    expect(switches.map((m) => m[1])).toEqual(["library", "scan", "union"]);
  });

  it("marks the pane that IS the stage, and only it", () => {
    const markup = view({
      onToggleLinked: () => undefined,
      maximizedId: "union",
      onToggleMaximized: () => undefined,
    });
    expect(markup).toContain(
      'data-role="pane-switch" data-pane="union" aria-pressed="true"',
    );
    expect(markup).toContain(
      'data-role="pane-switch" data-pane="scan" aria-pressed="false"',
    );
  });

  it("appears even for a caller that offers no link toggle", () => {
    // The toolbar used to render only when onToggleLinked was supplied; the switcher is
    // the maximized operator's ONLY way between panes and may not depend on that.
    const markup = view({ maximizedId: "scan", onToggleMaximized: () => undefined });
    expect(markup).toContain('data-role="pane-switch"');
    expect(markup).not.toContain("link views");
  });

  it("renders the switcher's numbers as the pane titles number them", () => {
    const markup = view({
      onToggleLinked: () => undefined,
      maximizedId: "library",
      onToggleMaximized: () => undefined,
    });
    expect(markup).toMatch(/data-pane="library"[^>]*>1</);
    expect(markup).toMatch(/data-pane="scan"[^>]*>2</);
    expect(markup).toMatch(/data-pane="union"[^>]*>3</);
  });
});

describe("SitePanesView — the subtitles say which cap and which system", () => {
  it("names the implant system beside the variant code on pane 1", () => {
    expect(captions(view({ systemLabel: "Straumann BLX" }))[0]).toBe(
      "5020 · Straumann BLX",
    );
  });

  it("falls back to the code alone when no system is known (callers predating the prop)", () => {
    expect(captions(view())[0]).toBe("5020");
  });

  it("prints no caption at all when nothing is declared", () => {
    const markup = view({ variantLabel: null, systemLabel: "Straumann BLX" });
    // pane 1 has no caption; panes 2 and 3 still do
    expect(captions(markup)).toHaveLength(2);
  });

  it("keeps the caption single-line — the full text stays in title=", () => {
    expect(view({ systemLabel: "Straumann BLX" })).toContain(
      'title="5020 · Straumann BLX"',
    );
  });
});

describe("scanPaneCaption", () => {
  it("leads with the tooth — the only other place it shows is the rail, which scrolls", () => {
    expect(scanPaneCaption(19, 1234, 9)).toBe(
      "Tooth 19 · 1,234 triangles within 9 mm of the site's centre",
    );
  });

  it("drops the tooth when there is no site — never prints 'Tooth null'", () => {
    expect(scanPaneCaption(null, 1234, 9)).toBe(
      "1,234 triangles within 9 mm of the site's centre",
    );
  });

  it("groups the triangle count the way the operator reads it", () => {
    expect(scanPaneCaption(3, 20500, 9)).toContain("20,500 triangles");
  });
});
