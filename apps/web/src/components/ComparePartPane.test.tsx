/**
 * THE DOCKED COMPARE PANE (client, 2026-07-26: "if we're doing this selection, I think we
 * should still see side by side the scan and the model that we're selecting so we can
 * compare"). Static-markup tests (node env, renderToStaticMarkup) pin the pane's honest
 * states — empty, captioned, collapsed — and the pure decisions behind them (the notice
 * precedence, WHY the pane is empty, and the auto-collapse floor); the mesh load itself is
 * IO and lives behind the same cachedMeshUrl/loadStlPositions edges the verify dialog
 * already uses.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import {
  COMPARE_MAIN_STAGE_MIN_WIDTH_PX,
  COMPARE_PANE_MIN_WIDTH_PX,
  COMPARE_SPLIT_GAP_PX,
  ComparePartPane,
  compareAutoCollapsed,
  compareEmptyReason,
  comparePaneNotice,
} from "./ComparePartPane";

type PaneProps = Parameters<typeof ComparePartPane>[0];

function props(overrides: Partial<PaneProps> = {}): PaneProps {
  return {
    variant: {
      variant: "6020",
      rimDiameterMm: 6.16,
      heightMm: 3.38,
      meshUrl: "/api/library/neodent-gm/6020/mesh",
    },
    emptyReason: "no-declaration",
    tooth: 3,
    collapsed: false,
    onToggleCollapsed: () => undefined,
    ...overrides,
  };
}

describe("ComparePartPane — markup states", () => {
  it("captions the shown part with its name, Ø × height and tooth", () => {
    const html = renderToStaticMarkup(<ComparePartPane {...props()} />);
    expect(html).toContain("6020");
    expect(html).toContain("Ø6.16 × 3.38 mm");
    expect(html).toContain("(tooth 3)");
  });

  it("states the honest empty state when no variant is declared for the active site", () => {
    const html = renderToStaticMarkup(<ComparePartPane {...props({ variant: null, tooth: null })} />);
    expect(html).toContain("Choose a cap variant to compare");
    // nothing to render 3D for — no live viewer behind an empty notice
    expect(html).not.toContain("verify-viewer");
  });

  it("does NOT ask for a declaration when one exists but the catalog has not resolved it", () => {
    // review 2026-07-26: a declared-but-unresolved variant got "Choose a cap variant" — the
    // wrong sentence; the true blocker is the catalog, and the pane must say so.
    const html = renderToStaticMarkup(
      <ComparePartPane {...props({ variant: null, emptyReason: "catalog-pending", tooth: 3 })} />,
    );
    expect(html).not.toContain("Choose a cap variant");
    expect(html).toContain("cap catalog");
  });

  it("offers the collapse control (⇥) while open", () => {
    const html = renderToStaticMarkup(<ComparePartPane {...props()} />);
    expect(html).toContain("⇥");
    expect(html).toContain('aria-expanded="true"');
  });

  it("collapsed: a slim strip with the expand control (⇤) and NO viewer mounted", () => {
    const html = renderToStaticMarkup(<ComparePartPane {...props({ collapsed: true })} />);
    expect(html).toContain("compare-pane--collapsed");
    expect(html).toContain("⇤");
    expect(html).toContain('aria-expanded="false"');
    // the collapsed strip must not keep a live WebGL pane behind it — the budget is ONE
    // extra context while comparing, zero while collapsed
    expect(html).not.toContain("verify-viewer");
  });
});

describe("compareEmptyReason — WHY there is no part to show (review 2026-07-26)", () => {
  it("no marked sites outranks everything — nothing can hold a declaration yet", () => {
    expect(compareEmptyReason({ sitesMarked: false, declared: false, catalog: "ready" })).toBe(
      "no-sites",
    );
    expect(compareEmptyReason({ sitesMarked: false, declared: false, catalog: "loading" })).toBe(
      "no-sites",
    );
  });

  it("an undeclared active site asks for the declaration", () => {
    expect(compareEmptyReason({ sitesMarked: true, declared: false, catalog: "ready" })).toBe(
      "no-declaration",
    );
  });

  it("declared but the catalog fetch has not resolved yet — pending, not 'choose a variant'", () => {
    expect(compareEmptyReason({ sitesMarked: true, declared: true, catalog: "idle" })).toBe(
      "catalog-pending",
    );
    expect(compareEmptyReason({ sitesMarked: true, declared: true, catalog: "loading" })).toBe(
      "catalog-pending",
    );
  });

  it("declared but the catalog endpoint failed — unavailable, stated as such", () => {
    expect(compareEmptyReason({ sitesMarked: true, declared: true, catalog: "unavailable" })).toBe(
      "catalog-unavailable",
    );
    expect(compareEmptyReason({ sitesMarked: true, declared: true, catalog: "error" })).toBe(
      "catalog-unavailable",
    );
  });

  it("declared, catalog ready, still unresolved — the declared id is not in the catalog", () => {
    expect(compareEmptyReason({ sitesMarked: true, declared: true, catalog: "ready" })).toBe(
      "not-in-catalog",
    );
  });
});

describe("comparePaneNotice — precedence of the honest sentences", () => {
  it("asks for a declaration first — no variant means nothing to compare", () => {
    expect(comparePaneNotice("no-declaration", { kind: "idle" })).toContain("Choose a cap variant");
    // even a stale error from a previous variant never outranks the empty state
    expect(comparePaneNotice("no-declaration", { kind: "error", message: "boom" })).toContain(
      "Choose a cap variant",
    );
  });

  it("each empty reason gets its own true sentence — never the declaration ask", () => {
    expect(comparePaneNotice("no-sites", { kind: "idle" })).toContain("No marked sites");
    expect(comparePaneNotice("catalog-pending", { kind: "idle" })).toContain("catalog");
    expect(comparePaneNotice("catalog-unavailable", { kind: "idle" })).toContain("unavailable");
    expect(comparePaneNotice("not-in-catalog", { kind: "idle" })).toContain("not in the cap catalog");
    for (const reason of ["no-sites", "catalog-pending", "catalog-unavailable", "not-in-catalog"] as const) {
      expect(comparePaneNotice(reason, { kind: "idle" })).not.toContain("Choose a cap variant");
    }
  });

  it("passes the load failure through verbatim", () => {
    expect(comparePaneNotice(null, { kind: "error", message: "Loading the part mesh failed (500)" })).toBe(
      "Loading the part mesh failed (500)",
    );
  });

  it("stays silent while loading and once ready — those are not notices", () => {
    expect(comparePaneNotice(null, { kind: "loading" })).toBeNull();
    expect(comparePaneNotice(null, { kind: "ready" })).toBeNull();
  });
});

describe("compareAutoCollapsed — the width floor", () => {
  it("holds at the 1280x800 workbench split (~600px of stage)", () => {
    // measured from the grid: 1280 − 40 padding − 208 rail − 400 work − 32 gaps = 600
    expect(compareAutoCollapsed(600)).toBe(false);
  });

  it("collapses once the split cannot give the pane its floor beside a usable main stage", () => {
    // the split's own flex gap is part of the arithmetic — review 2026-07-26 caught the
    // 580–589px window where omitting it left the main stage 290–299px, under its floor
    const threshold =
      COMPARE_PANE_MIN_WIDTH_PX + COMPARE_SPLIT_GAP_PX + COMPARE_MAIN_STAGE_MIN_WIDTH_PX;
    expect(threshold).toBe(590);
    expect(compareAutoCollapsed(threshold)).toBe(false);
    expect(compareAutoCollapsed(threshold - 1)).toBe(true);
    expect(compareAutoCollapsed(580)).toBe(true);
  });
});
