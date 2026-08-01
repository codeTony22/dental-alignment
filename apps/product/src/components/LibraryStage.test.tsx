/**
 * THE CONSTRUCTION LIBRARY PAGE (client 2026-08-01, page four of five).
 *
 * What is pinned here is only what this app decides: that the part rows come from the
 * CATALOG rather than from a table of its own, that the forward act is inert until a
 * part is effective, that changing one discloses its blast radius BEFORE the PUT, and
 * that the preview panel refuses to imply a union it does not render.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { LibraryStageView } from "./LibraryStage";
import { runnableDetail } from "../testing/fixtures";

/** A real-shaped catalog: the page must render THESE, never a table of its own. */
const CATALOG = {
  groups: [],
  constructions: [
    { path_id: "dess/conical-scanbody.stl", label: "Conical scanbody", vendor: "dess" },
    { path_id: "atlantis/ti-base.stl", label: "Ti base", vendor: "atlantis" },
  ],
};

function view(overrides: Partial<Parameters<typeof LibraryStageView>[0]> = {}) {
  return renderToStaticMarkup(
    <LibraryStageView
      detail={runnableDetail({ catalog: CATALOG })}
      saving={false}
      error={null}
      candidate={null}
      onPick={() => undefined}
      onCancel={() => undefined}
      onCommit={() => undefined}
      {...overrides}
    />,
  );
}

describe("the construction library page", () => {
  it("renders the CATALOG's parts, not a table of its own", () => {
    const html = view();
    expect(html).toContain('data-role="library-parts"');
    expect(html).toContain('data-role="library-part"');
    // the design comp's four invented parts, with their invented prices, must not
    // appear: none of these fields exist in the real catalog
    for (const invented of ["Titanium base", "Custom abutment", "$18 / site", "3 days"]) {
      expect(html).not.toContain(invented);
    }
  });

  it("refuses to imply a preview it does not render", () => {
    const html = view();
    expect(html).toContain('data-role="library-preview-pending"');
    expect(html).toContain("not built yet");
  });

  it("holds the forward act inert until a part is effective", () => {
    const none = runnableDetail({ catalog: CATALOG });
    const html = view({
      detail: {
        ...none,
        choices: {
          ...none.choices,
          effective_construction: { value: null, source: "none" },
        },
      },
    });
    expect(html).toContain("Pick a construction part first");
    expect(html).not.toContain(`href="/case/${none.case.id}/deliver"`);
  });

  it("opens Delivery once a part is effective", () => {
    const html = view();
    expect(html).toContain("Continue to Delivery");
    expect(html).toContain("/deliver");
  });

  it("always offers the way back to Adjustment", () => {
    expect(view()).toContain('data-role="library-back"');
  });

  it("states the blast radius BEFORE the change, never after it", () => {
    // the visible-reset doctrine, third home: the operator reads what a change costs
    // while they can still decline it
    const html = view({ candidate: "dess/ti-base" });
    expect(html).toContain('data-role="library-confirm"');
    expect(html).toContain("re-processes the case");
    expect(html).toContain('data-role="library-cancel"');
  });

  it("says nothing about a change nobody has proposed", () => {
    expect(view()).not.toContain('data-role="library-confirm"');
  });

  it("renders the BFF's refusal verbatim when one arrives", () => {
    expect(view({ error: "the construction part is unknown to this data tree" }))
      .toContain("unknown to this data tree");
  });
});
