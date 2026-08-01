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
import {
  PaneFoot,
  PANE_STAGE_CHROME_PX,
  SitePanesView,
  paneColumns,
  planPaneLayout,
  scanPaneCaption,
  siteAxisLabel,
  type SitePanesViewProps,
} from "./SitePanes";
import { armedViewerClassName } from "viewer";
import { newPairDraft, paneArming, withPick } from "../domain/adjust";
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

/** One layer per pane — enough for the HUD to have something to render. */
const LAYERS = {
  library: [
    { id: "part", label: "library part", swatch: "#123456", visible: true, opacity: 1, available: true },
  ],
  scan: [
    { id: "scan", label: "scanned cap", swatch: "#654321", visible: true, opacity: 1, available: true },
  ],
  union: [
    { id: "scan", label: "scan", swatch: "#654321", visible: true, opacity: 0.45, available: true },
    { id: "deviation", label: "deviation", swatch: null, visible: true, opacity: 1, available: true },
  ],
} as const;

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

/**
 * THE MEASURED LAYOUT (gaps measured-pane-layout-and-solo-fallback and
 * tiny-stage-chrome-steps-aside).
 *
 * Every number below was measured in the running app on 2026-07-31, not derived from the
 * arithmetic in styles.css — that comment computes for ONE row of three and has been stale
 * since the ≤1600px rule started producing two rows. What the browser actually reports at
 * the product's own target sizes, Declare stage, grid = the .verify-panels__grid box:
 *
 *   1280x800 — grid 563px, panes 394x276, stage 221px (min-height 220 forcing a ~6px
 *              overflow past the pane's padding box, clipped by .verify-panel overflow:hidden)
 *   1280x720 — grid 497px, panes 394x243, stage stuck at its 220px floor and CLIPPED BY 38px
 *   1280x620 — grid 397px, panes 394x220, stage clipped by 61px
 *
 * and the chrome that has to live on that stage, measured on the union pane:
 * layer HUD 59px (two rows) + colorbar strip 76px = 135px of a 221px stage — 61% of the
 * pane covering the very cap being judged.
 */
describe("paneColumns — mirrors the media queries in styles.css", () => {
  it("gives three across only above the 1600px rule", () => {
    expect(paneColumns(1601)).toBe(3);
    expect(paneColumns(1920)).toBe(3);
  });

  it("gives two across at the product's own target width", () => {
    expect(paneColumns(1600)).toBe(2);
    expect(paneColumns(1280)).toBe(2);
    expect(paneColumns(1181)).toBe(2);
  });

  it("gives one across where the shell itself stacks", () => {
    expect(paneColumns(1180)).toBe(1);
    expect(paneColumns(900)).toBe(1);
  });
});

describe("planPaneLayout", () => {
  it("claims nothing before the grid has been measured — the unmeasured plan is today's layout", () => {
    const plan = planPaneLayout({ availH: 0, viewportW: 0 }, false);
    expect(plan.measured).toBe(false);
    expect(plan.solo).toBe(false);
    expect(plan.chrome).toBe("full");
  });

  it("computes the 1280x800 stage the browser actually renders (±the min-height overflow)", () => {
    const plan = planPaneLayout({ availH: 563, viewportW: 1280 }, false);
    expect(plan.rows).toBe(2);
    // measured 221px on screen, which is the 220px floor overflowing its row by ~6px
    expect(plan.stageH).toBe(275 - PANE_STAGE_CHROME_PX);
    expect(plan.stageH).toBeLessThan(221);
  });

  it("steps the chrome aside at 1280x800 — 61% of that stage is HUD and colorbar", () => {
    expect(planPaneLayout({ availH: 563, viewportW: 1280 }, false).chrome).toBe("compact");
  });

  it("takes the HUD off the glass at 1280x720, where the stage is clipped by 38px", () => {
    expect(planPaneLayout({ availH: 497, viewportW: 1280 }, false).chrome).toBe("tiny");
  });

  it("NEVER hides panes on its own — three stay up however short the stage (client 2026-08-01)", () => {
    /* The prototype's solo fallback shipped in R3 and the client hit it the same
       day: "The 3 views of the declare disappears i never said that i wanted
       independent views the idea is to see everything at once." The rule is now
       the client's, not the prototype's: the layout may shrink panes and step
       chrome aside, but only the OPERATOR's explicit maximize ever shows one
       pane. A short stage gets three small panes, honestly small. */
    const plan = planPaneLayout({ availH: 397, viewportW: 1280 }, false);
    expect(plan.solo).toBe(false);
    expect(plan.columns).toBe(2);
  });

  it("never forces solo on a pane the operator maximized — that IS the whole height", () => {
    const plan = planPaneLayout({ availH: 397, viewportW: 1280 }, true);
    expect(plan.solo).toBe(false);
    expect(plan.stageH).toBe(397 - PANE_STAGE_CHROME_PX);
  });

  it("keeps three panes at 1280x720 — a clipped-but-usable stage beats hiding two panes", () => {
    expect(planPaneLayout({ availH: 497, viewportW: 1280 }, false).solo).toBe(false);
  });

  it("puts a wide window's three panes on one row and leaves the chrome alone", () => {
    const plan = planPaneLayout({ availH: 640, viewportW: 1920 }, false);
    expect(plan.rows).toBe(1);
    expect(plan.stageH).toBe(640 - PANE_STAGE_CHROME_PX);
    expect(plan.chrome).toBe("full");
  });

  it("stacks three rows where the shell stacks, and says so in the stage height", () => {
    const plan = planPaneLayout({ availH: 900, viewportW: 1000 }, false);
    expect(plan.rows).toBe(3);
    expect(plan.stageH).toBe(Math.floor((900 - 24) / 3) - PANE_STAGE_CHROME_PX);
  });

  it("solo cannot engage at ANY height — the whole sweep", () => {
    for (const availH of [80, 150, 170, 250, 397, 600, 1200]) {
      expect(planPaneLayout({ availH, viewportW: 1280 }, false).solo).toBe(false);
    }
  });
});

describe("SitePanesView — three panes, always (client 2026-08-01)", () => {
  it("shows all three at the height that used to trigger the solo fallback", () => {
    const markup = view({
      layoutPlan: planPaneLayout({ availH: 397, viewportW: 1280 }, false),
      onToggleMaximized: () => undefined,
    });
    expect(markup).not.toContain('data-role="pane-solo-note"');
    expect([...markup.matchAll(/class="verify-panel"/g)]).toHaveLength(3);
  });

  it("shows all three even at a height that can barely draw them", () => {
    const markup = view({
      layoutPlan: planPaneLayout({ availH: 150, viewportW: 1280 }, false),
      onToggleMaximized: () => undefined,
    });
    expect([...markup.matchAll(/class="verify-panel"/g)]).toHaveLength(3);
  });

  it("one pane exists only as the operator's own maximize, with the way back offered", () => {
    const markup = view({
      layoutPlan: planPaneLayout({ availH: 397, viewportW: 1280 }, true),
      maximizedId: "scan",
      onToggleMaximized: () => undefined,
    });
    expect([...markup.matchAll(/class="verify-panel"/g)]).toHaveLength(1);
    expect(markup).toContain("show all three");
  });
});

describe("SitePanesView — the chrome steps aside on a stage too small to carry it", () => {
  it("keeps the layer HUD on the glass while the stage can carry it", () => {
    expect(view({ layers: LAYERS })).toContain("verify-panel__hud--layers");
    expect(
      view({ layers: LAYERS, layoutPlan: planPaneLayout({ availH: 563, viewportW: 1280 }, false) }),
    ).toContain("verify-panel__hud--layers");
  });

  it("takes the HUD off the glass on a tiny stage and offers a way back to it", () => {
    const markup = view({
      layers: LAYERS,
      layoutPlan: planPaneLayout({ availH: 497, viewportW: 1280 }, false),
    });
    expect(markup).not.toContain("verify-panel__hud--layers");
    expect(markup).toContain('data-role="pane-hud-toggle"');
  });

  it("marks the stage so the colorbar and footer can shrink with it", () => {
    expect(view({ layoutPlan: planPaneLayout({ availH: 563, viewportW: 1280 }, false) })).toContain(
      "verify-panel__stage--compact",
    );
    expect(view({ layoutPlan: planPaneLayout({ availH: 497, viewportW: 1280 }, false) })).toContain(
      "verify-panel__stage--tiny",
    );
  });

  it("offers no HUD toggle on a pane that has no layers to toggle", () => {
    const markup = view({ layoutPlan: planPaneLayout({ availH: 497, viewportW: 1280 }, false) });
    expect(markup).not.toContain('data-role="pane-hud-toggle"');
  });

  /* A RAMP WITH NO SCALE IS NOT A MEASUREMENT (design review 2026-07-31). The tiny
     rule hid `__scales`, `__ticks` AND `__detail` — and `__ticks` IS the two end
     labels, so the union pane showed a deviation-coloured cap over a bare gradient
     with no numbers, no sign convention and no way to tell the signed ramp from the
     absolute rainbow (where red means either proud or sunk). On a three-column stage
     maximizing yields the identical height, so there was no route back to any of it.
     The chooser may go; the ramp's IDENTITY may not. */
  it("names the scale on a tiny stage, where the chooser cannot be shown", () => {
    const markup = view({
      layoutPlan: planPaneLayout({ availH: 497, viewportW: 1280 }, false),
    });
    expect(markup).toContain('data-role="colorbar-scale-name"');
    expect(markup).toContain("signed ±0.50 mm");
  });

  it("names the ABSOLUTE ramp when that is the one on the mesh — red means two things", () => {
    const markup = view({
      scaleId: "contacts",
      layoutPlan: planPaneLayout({ availH: 497, viewportW: 1280 }, false),
    });
    expect(markup).toContain('data-role="colorbar-scale-name"');
    expect(markup).toContain("contacts");
  });

  it("says nothing extra where the chooser itself is on screen", () => {
    const markup = view({
      layoutPlan: planPaneLayout({ availH: 563, viewportW: 1280 }, false),
      onSelectScale: () => undefined,
    });
    expect(markup).not.toContain('data-role="colorbar-scale-name"');
  });
});

describe("PaneFoot — how big it is, and where the camera actually is", () => {
  it("prints the bar at the width the step measures, with its number beside it", () => {
    const markup = renderToStaticMarkup(
      <PaneFoot axis="down the seated pose axis" bar={{ mm: 1, px: 50, label: "1 mm" }} />,
    );
    expect(markup).toContain('data-role="pane-scale"');
    expect(markup).toContain("width:50px");
    expect(markup).toContain("1 mm");
  });

  it("prints the live axis reading, not a fixed anatomical word", () => {
    const markup = renderToStaticMarkup(<PaneFoot axis="37° off the seated pose axis" bar={null} />);
    expect(markup).toContain('data-role="pane-axis"');
    expect(markup).toContain("37° off the seated pose axis");
    expect(markup).not.toContain('data-role="pane-scale"');
  });

  it("renders nothing at all when the camera has said nothing yet", () => {
    expect(renderToStaticMarkup(<PaneFoot axis={null} bar={null} />)).toBe("");
  });
});

describe("siteAxisLabel", () => {
  it("names the EXACT axis when a pose seated the cap", () => {
    expect(siteAxisLabel({ axis: [0, 0, 1], x_axis: [1, 0, 0], origin: [0, 0, 0] })).toBe(
      "the seated pose axis",
    );
  });

  it("names the PROXY when there is no pose — the demo measured it 6.2°-42.0° off", () => {
    expect(siteAxisLabel(null)).toBe("the occlusal proxy");
  });

  it("names the proxy for a malformed axis too — that is what the frame fell back to", () => {
    expect(siteAxisLabel({ axis: [0, 1], x_axis: [1, 0, 0], origin: [0, 0, 0] })).toBe(
      "the occlusal proxy",
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

/**
 * THE ARMED TELL, END TO END (design review 2026-07-31).
 *
 * R2's headline "the panes say when they are armed" never reached the running app:
 * AdjustStage — the only stage that installs pick listeners — passed neither `armed` to
 * useSitePaneScene nor `hints` to SitePanesView, so `.verify-viewer--armed` and the
 * whole on-glass hint path were dead. WebGL cannot enter a node test, so what is held
 * here is every link of the chain except the React wiring: the pick router's rule, the
 * class the cursor hangs off, and the hint the pane prints.
 */
describe("the pane that wants the click says so", () => {
  it("puts the crosshair on the LIBRARY pane while the pair wants its part half", () => {
    const armed = paneArming(newPairDraft("p1", false), false).armed;
    expect(armedViewerClassName(armed.library)).toContain("verify-viewer--armed");
    expect(armedViewerClassName(armed.scan)).not.toContain("verify-viewer--armed");
    expect(armedViewerClassName(armed.union)).not.toContain("verify-viewer--armed");
  });

  it("moves it to BOTH scan panes once the part half is placed", () => {
    const draft = withPick(newPairDraft("p1", false), "part", [0, 0, 1]);
    const armed = paneArming(draft, false).armed;
    expect(armedViewerClassName(armed.scan)).toContain("verify-viewer--armed");
    expect(armedViewerClassName(armed.union)).toContain("verify-viewer--armed");
    expect(armedViewerClassName(armed.library)).not.toContain("verify-viewer--armed");
  });

  it("prints that pane's hint ON the glass, where the click goes", () => {
    const draft = withPick(newPairDraft("p1", true), "part", [0, 0, 1]);
    const markup = view({ hints: paneArming(draft, false).hints });
    expect(markup).toContain('data-role="pane-hint"');
    expect(markup).toContain("Click ONE END of that feature here.");
    // pane 1 is done with this pair: it says nothing
    expect([...markup.matchAll(/data-role="pane-hint"/g)]).toHaveLength(2);
  });

  it("says nothing on any pane while nothing is armed", () => {
    const markup = view({ hints: paneArming(null, false).hints });
    expect(markup).not.toContain('data-role="pane-hint"');
  });
});
