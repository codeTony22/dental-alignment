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

/** The same catalog, but its rows now carry the served mesh_url (application/catalog.py's
 * `construction_parts` wrapper, landed da698b5) — the unrun-part preview's one input. */
const CATALOG_WITH_MESH = {
  groups: [],
  constructions: [
    {
      path_id: "dess/conical-scanbody.stl",
      label: "Conical scanbody",
      vendor: "dess",
      mesh_url: "/api/constructions/dess/conical-scanbody.stl/mesh",
    },
    { path_id: "atlantis/ti-base.stl", label: "Ti base", vendor: "atlantis" },
  ],
};

function view(overrides: Partial<Parameters<typeof LibraryStageView>[0]> = {}) {
  return renderToStaticMarkup(
    <LibraryStageView
      detail={runnableDetail({ catalog: CATALOG })}
      packageFiles={[]}
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

  /* THE EFFECTIVE-BUT-UNRUN PART (follow-up to §10-M2's armed slice, client
     "do what is recommended" 2026-08-02). A case can hold an effective construction
     while no run receipt is readable — the armed path landed first and left this
     showing the bare pending gap even though the catalog mesh to answer it with was
     already served. Same doctrine, same pane: the part alone, never an implied union. */
  it("previews the EFFECTIVE part when no run mesh exists and its row carries a mesh_url", () => {
    const html = view({
      detail: runnableDetail({ catalog: CATALOG_WITH_MESH }),
      packageFiles: [],
    });
    expect(html).toContain('data-role="library-part-preview"');
    expect(html).not.toContain('data-role="library-preview-pending"');
  });

  it("still states the pending gap when the effective row has no mesh_url", () => {
    // the default CATALOG's rows predate the served mesh_url — a guessed URL is worse
    // than the stated gap, so the gap stands
    const html = view({ packageFiles: [] });
    expect(html).toContain('data-role="library-preview-pending"');
    expect(html).not.toContain('data-role="library-part-preview"');
  });

  it("still states the pending gap when nothing is effective at all", () => {
    const detail = runnableDetail({ catalog: CATALOG_WITH_MESH });
    const html = view({
      detail: {
        ...detail,
        choices: {
          ...detail.choices,
          effective_construction: { value: null, source: "none" },
        },
      },
      packageFiles: [],
    });
    expect(html).toContain('data-role="library-preview-pending"');
  });

  it("the run's own mesh still wins over the effective-part preview", () => {
    // the union the run actually built is strictly more informative than the part alone
    const html = view({
      detail: runnableDetail({ catalog: CATALOG_WITH_MESH }),
      packageFiles: ["case-arch-with-constructions.stl"],
    });
    expect(html).toContain('data-role="library-preview-caption"');
    expect(html).not.toContain('data-role="library-part-preview"');
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
    // while they can still decline it (this fixture predates a run, so the full
    // reset words are still the truth here)
    const html = view({ candidate: "dess/ti-base" });
    expect(html).toContain('data-role="library-confirm"');
    expect(html).toContain("re-processes the case");
    expect(html).toContain('data-role="library-cancel"');
  });

  it("over a done run, the disclosed cost is the re-emit (§10-AC)", () => {
    const base = runnableDetail({ catalog: CATALOG });
    const html = view({
      detail: {
        ...base,
        session: { ...base.session, run_state: "done" },
      },
      candidate: "dess/ti-base",
    });
    expect(html).toContain("re-emits the package from the run&#x27;s own poses");
    expect(html).not.toContain("re-processes the case");
  });

  it("says nothing about a change nobody has proposed", () => {
    expect(view()).not.toContain('data-role="library-confirm"');
  });

  it("renders the BFF's refusal verbatim when one arrives", () => {
    expect(view({ error: "the construction part is unknown to this data tree" }))
      .toContain("unknown to this data tree");
  });

  it("renders the RUN's own unified mesh when the package carries one", () => {
    // the client's ask, answered with geometry that already exists: the library page
    // is only reachable over a done run, so -arch-with-constructions.stl is on disk
    const html = view({ packageFiles: ["case-arch-with-constructions.stl"] });
    expect(html).not.toContain('data-role="library-preview-pending"');
    expect(html).toContain('data-role="library-preview-caption"');
    expect(html).toContain("cannot change it until the case is re-run");
  });

  it("shows the gap, not a fake, when the run built no unified mesh", () => {
    const html = view({ packageFiles: ["case-lower.stl"] });
    expect(html).toContain('data-role="library-preview-pending"');
  });
});

/**
 * THE COMP'S PAGE CLOTHES (page pass 2026-08-02, §10-AA): the library is a centered
 * PAGE — part cards left, the preview column right with the acts at its foot — not a
 * control column beside a stage. What stays pinned above (no invented parts, no
 * prices, provenance captions, gating) is untouched by the re-dress.
 */
describe("the comp's page clothes", () => {
  it("spans the workbench as one centered page", () => {
    expect(view()).toMatch(/data-role="library-stage"[^>]*class="stage-page/);
  });

  it("offers a non-effective part as a card wearing the comp's select chip", () => {
    const html = view();
    // the effective row keeps its suggested/selected chip; the OTHER row invites
    expect(html).toContain(">select<");
  });

  it("keeps the acts at the preview column's foot, forward leading", () => {
    const html = view();
    const preview = html.slice(html.indexOf('data-role="library-preview"'));
    expect(preview).toContain('data-role="library-forward"');
    expect(preview).toContain('data-role="library-back"');
    expect(preview.indexOf('data-role="library-forward"')).toBeLessThan(
      preview.indexOf('data-role="library-back"'),
    );
  });
});

// --- the unrun-part preview (§10-M2's "natural next slice", 2026-08-02): arming a
// candidate replaces the pane's content with the CATALOG's own mesh for that part,
// because there is no run behind an unarmed candidate for a union to exist from.
describe("the construction library page's ARMED-candidate preview", () => {
  it("replaces the pane with the candidate's own catalog mesh, not the gap", () => {
    const html = view({
      detail: runnableDetail({ catalog: CATALOG_WITH_MESH }),
      candidate: "dess/conical-scanbody.stl",
    });
    expect(html).toContain('data-role="library-part-preview"');
    expect(html).toContain("Conical scanbody");
    expect(html).not.toContain('data-role="library-preview-pending"');
  });

  it("carries the unrun-part caption, never the run-mesh caption's words", () => {
    const html = view({
      detail: runnableDetail({ catalog: CATALOG_WITH_MESH }),
      candidate: "dess/conical-scanbody.stl",
    });
    expect(html).toContain('data-role="library-part-preview-caption"');
    // renderToStaticMarkup HTML-escapes the apostrophe (DeclarePanes.test.tsx /
    // MainStage.test.tsx's own convention for asserting on rendered text)
    expect(html).toContain("vendor&#x27;s catalog part");
    // the run-mesh caption's own words (libraryPreviewCaption) must not appear —
    // a candidate that has not run cannot borrow the run's "re-run" language
    expect(html).not.toContain("cannot change it until the case is re-run");
  });

  it("REPLACES the run's own mesh too — one pane, not two stacked (§10-P.2's budget)", () => {
    // DECISION recorded in LibraryStage.tsx's own doc comment: replace-in-one-pane,
    // not stacked panes. Arming a candidate while a run mesh already exists still
    // swaps the pane, because the candidate is what the operator is JUDGING right
    // now — showing the OLD run's mesh beside it would answer a question nobody
    // asked and bury the one they did.
    const html = view({
      detail: runnableDetail({ catalog: CATALOG_WITH_MESH }),
      candidate: "dess/conical-scanbody.stl",
      packageFiles: ["case-arch-with-constructions.stl"],
    });
    expect(html).toContain('data-role="library-part-preview"');
    expect(html).not.toContain('data-role="library-preview-caption"');
    expect(html).not.toContain('data-role="deliver-mesh-preview-tabs"');
  });

  it("a candidate whose row carries no mesh_url states the gap, never a guessed URL", () => {
    const html = view({
      detail: runnableDetail({ catalog: CATALOG_WITH_MESH }),
      candidate: "atlantis/ti-base.stl",
    });
    expect(html).toContain('data-role="library-part-preview"');
    expect(html).toContain('data-role="library-part-preview-pending"');
  });

  it("disarming (candidate back to null) returns the pane to what it showed before", () => {
    // no separate state machine to pin here: candidate=null is exactly the "says
    // nothing about a change nobody has proposed" branch already covered above —
    // this test only pins that the ARMED-candidate role itself is gone with it
    const html = view({
      detail: runnableDetail({ catalog: CATALOG_WITH_MESH }),
      candidate: null,
      packageFiles: ["case-arch-with-constructions.stl"],
    });
    expect(html).not.toContain('data-role="library-part-preview"');
    expect(html).toContain('data-role="library-preview-caption"');
  });
});
