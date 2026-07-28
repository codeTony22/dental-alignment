/**
 * Declare's control surface (plan §4 Declare / AM-8, slice 5a), statically rendered
 * per the repo convention: the site queue speaks server statuses and chips, the
 * system bar attributes the effective system from the server's `source`, a switch
 * asks in WORDS (with the reset count) before any PUT, variant cards split current
 * from the labelled superseded fold, and the whole surface renders the persisted
 * payload — optimism OFF. The pure rules (cards, words, counts, active-site
 * defaulting) are pinned in domain/declare.test.ts; the PUT wiring functions are the
 * api client's, pinned in api/client.test.ts.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { StaticRouter } from "react-router-dom";
import { DeclareStage, DeclareStageView } from "./DeclareStage";
import {
  caseSessionDetail,
  catalogEntry,
  catalogGroup,
  rescanAssessment,
  siteView,
} from "../testing/fixtures";

const detail = caseSessionDetail({
  sites: [
    siteView({
      tooth: 19,
      status: "declared",
      declared_variant: "5020",
      capture: rescanAssessment("Only 31% of the rim arc is captured."),
    }),
    siteView({ tooth: 30 }),
  ],
  catalog: {
    groups: [
      catalogGroup("conical-4x4", [
        catalogEntry({ id: "5020", rim_diameter_mm: 5.0, height_mm: 2.0 }),
        catalogEntry({
          id: "superseded-2025-01-01--4010",
          variant: "4010",
          label: "4.0 × 1.0 (archived)",
          flags: ["superseded"],
        }),
      ]),
      catalogGroup("astra-ev", [catalogEntry({ id: "3010" })]),
    ],
    constructions: [],
  },
});

function view(overrides: Partial<Parameters<typeof DeclareStageView>[0]> = {}) {
  return renderToStaticMarkup(
    <StaticRouter location="/case/case-a/declare">
      <DeclareStageView
        detail={detail}
        activeTooth={null}
        pendingSwitch={null}
        saving="idle"
        error={null}
        onSelectSite={() => undefined}
        onAskSwitch={() => undefined}
        onConfirmSwitch={() => undefined}
        onCancelSwitch={() => undefined}
        onDeclare={() => undefined}
        {...overrides}
      />
    </StaticRouter>,
  );
}

describe("the site queue (left) — server statuses, never local ones", () => {
  it("each site: tooth, status chip, capture chip, declared variant or a dash", () => {
    const html = view();
    expect(html).toContain('data-role="declare-queue"');
    expect(html).toMatch(/data-role="status-chip"[^>]*data-status="declared"/);
    expect(html).toMatch(/data-role="status-chip"[^>]*data-status="detected"/);
    expect(html).toMatch(/data-verdict="rescan"/);
    expect(html).toContain("not assessed"); // tooth 30 has no capture yet — honest
    expect(html).toContain("5020"); // tooth 19's declared variant
    expect(html).toContain("—"); // tooth 30's honest dash
  });

  it("the active site is marked; the default active site is the first", () => {
    expect(view()).toMatch(/data-role="queue-site"[^>]*aria-pressed="true"[^>]*data-tooth="19"/);
    expect(view({ activeTooth: 30 })).toMatch(
      /data-role="queue-site"[^>]*aria-pressed="true"[^>]*data-tooth="30"/,
    );
  });
});

describe("the system bar (top) — the effective system says WHICH it is", () => {
  it("the effective card is marked and carries the suggested tag from the server", () => {
    const html = view();
    expect(html).toMatch(/data-role="system-card"[^>]*aria-pressed="true"[^>]*data-model="conical-4x4"/);
    expect(html).toContain('data-role="suggested-tag"');
  });

  it("a declared system drops the suggested tag — it is the operator's act", () => {
    const html = view({
      detail: {
        ...detail,
        system: { effective_model: "conical-4x4", source: "declared" },
      },
    });
    expect(html).not.toContain('data-role="suggested-tag"');
  });
});

describe("the visible-reset confirmation — words BEFORE the PUT (AM-8)", () => {
  it("a pending switch shows the words with the reset count, and both ways out", () => {
    const html = view({ pendingSwitch: "astra-ev" });
    expect(html).toContain('data-role="system-switch-confirm"');
    expect(html).toContain("Switching to astra-ev resets 1 declared site");
    expect(html).toContain("Switch system");
    expect(html).toContain("Keep conical-4x4");
  });

  it("no pending switch, no ceremony", () => {
    expect(view()).not.toContain('data-role="system-switch-confirm"');
  });
});

describe("variant cards (centre) — the active site declares from the catalog", () => {
  it("current cards render with the catalog's Ø × height line", () => {
    const html = view();
    expect(html).toContain('data-role="variant-cards"');
    expect(html).toMatch(/data-role="variant-card"[^>]*data-variant="5020"/);
    expect(html).toContain("Ø 5.0 × 2.0 mm");
  });

  it("the active site's declared variant is the pressed card", () => {
    // tooth 19 (default active) declared 5020 — its card renders as chosen
    expect(view()).toMatch(
      /data-role="variant-card"[^>]*data-variant="5020"[^>]*aria-pressed="true"/,
    );
    // with tooth 30 active (nothing declared), no card is pressed
    expect(view({ activeTooth: 30 })).not.toMatch(
      /data-role="variant-card"[^>]*aria-pressed="true"/,
    );
  });

  it("the superseded shelf collapses behind a LABELLED fold", () => {
    const html = view();
    expect(html).toContain('data-role="superseded-fold"');
    expect(html).toContain("Superseded shelf — 1 archived part");
    expect(html).toContain("4.0 × 1.0 (archived)");
  });

  it("no superseded parts, no fold at all", () => {
    const html = view({
      detail: {
        ...detail,
        catalog: {
          groups: [catalogGroup("conical-4x4", [catalogEntry({ id: "5020" })])],
          constructions: [],
        },
      },
    });
    expect(html).not.toContain('data-role="superseded-fold"');
  });
});

describe("in-flight and refused states — optimism OFF", () => {
  it("saving states are stated while a PUT is in flight", () => {
    expect(view({ saving: "declaration" })).toContain("Declaring variant…");
    expect(view({ saving: "system" })).toContain("Switching system…");
  });

  it("a refusal surfaces in the backend's words", () => {
    const html = view({
      error: "HTTP 422 — '9999' is not a part of the 'conical-4x4' library",
    });
    expect(html).toContain('data-role="declare-error"');
    expect(html).toContain("not a part of the");
  });
});

describe("continue — per flow.ts, lit by the run (5c)", () => {
  it("with no run, the continue affordance is inert and says why", () => {
    const html = view();
    expect(html).toMatch(/data-role="continue-on"[^>]*aria-disabled="true"/);
    expect(html).toContain("No run exists yet");
  });

  it("a done run over a flagged site links to Adjust — its queue has work", () => {
    const flagged = caseSessionDetail({
      ...detail,
      sites: [
        siteView({ tooth: 19, status: "flagged", declared_variant: "5020" }),
        siteView({ tooth: 30, status: "ready", declared_variant: "5020" }),
      ],
      session: { ...detail.session, run_state: "done" },
    });
    const html = view({ detail: flagged });
    expect(html).toMatch(/data-role="continue-on"[^>]*href="\/case\/case-a\/adjust"/);
  });

  it("a clean done run links straight to Deliver — skippable Adjust (plan §4)", () => {
    // DELIBERATE change from 5a's interim behavior (Adjust won as next-in-order):
    // with a completed run and nothing flagged, Adjust has nothing to offer and
    // the client's directive is Deliver directly reachable when clean.
    const resolved = caseSessionDetail({
      ...detail,
      sites: [siteView({ tooth: 19, status: "ready", declared_variant: "5020" })],
      session: { ...detail.session, run_state: "done" },
    });
    const html = view({ detail: resolved });
    expect(html).toMatch(/data-role="continue-on"[^>]*href="\/case\/case-a\/deliver"/);
    expect(html).toContain("nothing to adjust");
  });
});

describe("the run footer (5c) — progress in honest words", () => {
  const readyDetail = caseSessionDetail({
    ...detail,
    sites: [
      siteView({ tooth: 19, status: "ready", declared_variant: "5020" }),
      siteView({ tooth: 30, status: "ready", declared_variant: "5020" }),
    ],
  });

  it("a firing run names the work and its honest duration", () => {
    const html = view({ detail: readyDetail, runPhase: "firing" });
    expect(html).toContain('data-role="run-progress"');
    expect(html).toContain("Aligning 2 sites");
    expect(html).toContain("30–60");
  });

  it("a persisted queued|running state shows the same progress — another reader fired it", () => {
    for (const run_state of ["queued", "running"] as const) {
      const html = view({
        detail: {
          ...readyDetail,
          session: { ...readyDetail.session, run_state },
        },
      });
      expect(html).toContain('data-role="run-progress"');
    }
  });

  it("a refused run renders the pipeline's words VERBATIM with the explicit retry", () => {
    const words =
      "package NOT emitted: the relief ate the screw channel — re-run with a smaller gingival offset";
    const html = view({
      detail: {
        ...readyDetail,
        session: {
          ...readyDetail.session,
          run_state: "refused",
          run_refusal: words,
        },
      },
    });
    expect(html).toContain('data-role="run-refused"');
    expect(html).toContain("re-run with a smaller gingival offset");
    expect(html).toContain('data-role="run-retry"');
  });

  it("a transport failure is stated with its own retry — never a silent freeze", () => {
    const html = view({ detail: readyDetail, runError: "ECONNREFUSED" });
    expect(html).toContain('data-role="run-error"');
    expect(html).toContain("ECONNREFUSED");
    expect(html).toContain('data-role="run-retry"');
  });

  it("idle with no run shows no footer noise", () => {
    const html = view();
    expect(html).not.toContain('data-role="run-progress"');
    expect(html).not.toContain('data-role="run-refused"');
    expect(html).not.toContain('data-role="run-error"');
  });
});

describe("the DeclareStage container, statically (effects do not run)", () => {
  it("mounts queue, system bar, cards, the 3D stage AND the three panes with the tick", () => {
    const html = renderToStaticMarkup(
      <StaticRouter location="/case/case-a/declare">
        <DeclareStage detail={detail} onDetail={() => undefined} />
      </StaticRouter>,
    );
    expect(html).toContain('data-role="declare-queue"');
    expect(html).toContain('data-role="system-bar"');
    expect(html).toContain('data-role="variant-cards"');
    // the arch rides as a collapsible context STRIP (client 2026-07-27: the panes
    // are the subject of this stage) — open by default, foldable by the operator
    expect(html).toMatch(/<details[^>]*data-role="arch-fold"[^>]*open/);
    expect(html).toContain("Arch context");
    expect(html).toContain('data-role="main-stage"');
    // 5b: the three live panes and the review tick ride with the stage
    expect(html).toContain('data-role="declare-panes"');
    expect(html).toContain('data-role="pane-library"');
    expect(html).toContain('data-role="pane-scan"');
    expect(html).toContain('data-role="pane-union"');
    expect(html).toContain('data-role="review-tick"');
    expect(html).not.toContain('data-role="system-switch-confirm"');
    expect(html).not.toContain('data-role="declare-error"');
  });
});
