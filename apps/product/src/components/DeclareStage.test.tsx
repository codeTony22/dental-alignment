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
import type { CaseSessionDetail } from "../api/client";
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

  // gap `declare-queue-header`: Declare's queue had a bare title and went straight to
  // rows, while Adjust's carried its counts — progress mid-declaration was invisible.
  it("the queue heads with how far through the declaration the operator is", () => {
    const html = view();
    expect(html).toContain('data-role="queue-summary"');
    expect(html).toContain("0 of 2 sites reviewed");
  });

  it("an empty queue heads with nothing to review, never '0 of 0'", () => {
    const html = view({ detail: { ...detail, sites: [] } });
    expect(html).not.toContain("0 of 0");
    expect(html).toContain('data-role="declare-empty"');
  });

  // gap `queue-row-state-sentence`: the rows printed the wire's ladder word and no
  // measured number at all.
  it("each row states what the site is waiting for, not just the wire's word", () => {
    const html = view();
    expect(html).toMatch(/data-role="queue-state"[^>]*>[^<]*preview/i);
    expect(html).toContain("Awaiting your declaration");
  });

  it("pre-run the row SAYS no run has measured the fit — never a dash reading as zero", () => {
    const html = view({
      detail: {
        ...detail,
        sites: [siteView({ tooth: 19, status: "ready", declared_variant: "5020" })],
      },
    });
    expect(html).toContain("no run has measured");
  });

  it("with the run's rows in hand the number is the RUN's, read from its own row", () => {
    const html = view({
      detail: {
        ...detail,
        sites: [siteView({ tooth: 19, status: "flagged", declared_variant: "5020" })],
      },
      runRows: [{ tooth: 19, deviation_rms_mm: 0.184 }],
    });
    expect(html).toContain("0.184 mm");
  });
});

describe("the system select — the effective system says WHICH it is", () => {
  /* CARDS BECAME A SELECT (client 2026-08-02: "there is a lot of real estate for the
     buttons … we need to be more cohesive"). The claims are unchanged — the effective
     model is the selected option, the suggested attribution is the server's — only the
     clothing shrank from two full-width cards to one control. */
  it("selects the effective model and carries the suggested tag from the server", () => {
    const html = view();
    expect(html).toContain('data-role="declare-system"');
    expect(html).toMatch(
      /<option[^>]*data-model="conical-4x4"[^>]*selected|<option[^>]*selected[^>]*data-model="conical-4x4"/,
    );
    expect(html).toContain('data-role="suggested-tag"');
  });

  it("names each system WITH its shelf size — the count was the card's one fact worth keeping", () => {
    expect(view()).toMatch(/data-model="conical-4x4"[^>]*>[^<]*2 parts/);
    // and the singular shelf stays grammatical — "1 part", never "1 parts"
    expect(view()).toMatch(/data-model="astra-ev"[^>]*>[^<]*1 part</);
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

describe("the variant dropdown — the active site declares from the catalog", () => {
  /* THE CLIENT'S OWN WORDS (2026-08-02): "the implant variant selection needs to be
     drop down". Six cards became one select; every claim the cards made — dims from
     the catalog, the declared one marked, detection's proposal attributed, the
     superseded shelf separate — moved into it rather than being dropped. */
  it("current options carry the catalog's Ø × height line", () => {
    const html = view();
    expect(html).toContain('data-role="declare-variant"');
    expect(html).toMatch(/<option[^>]*data-variant="5020"/);
    expect(html).toContain("Ø 5.0 × 2.0 mm");
  });

  it("the active site's declared variant is the selected option", () => {
    // tooth 19 (default active) declared 5020 — its option renders as chosen
    expect(view()).toMatch(
      /<option[^>]*data-variant="5020"[^>]*selected|<option[^>]*selected[^>]*data-variant="5020"/,
    );
    // with tooth 30 active (nothing declared), no variant option is selected
    expect(view({ activeTooth: 30 })).not.toMatch(
      /<option[^>]*data-variant=[^>]*selected|<option[^>]*selected[^>]*data-variant=/,
    );
  });

  it("the superseded shelf is a LABELLED optgroup, never mixed into the current shelf", () => {
    const html = view();
    expect(html).toContain('data-role="superseded-shelf"');
    expect(html).toContain("Superseded shelf — 1 archived part");
    expect(html).toContain("4.0 × 1.0 (archived)");
    // the archived option sits INSIDE the optgroup, after it opens
    expect(html.indexOf("4.0 × 1.0 (archived)")).toBeGreaterThan(
      html.indexOf('data-role="superseded-shelf"'),
    );
  });

  it("no superseded parts, no optgroup at all", () => {
    const html = view({
      detail: {
        ...detail,
        catalog: {
          groups: [catalogGroup("conical-4x4", [catalogEntry({ id: "5020" })])],
          constructions: [],
        },
      },
    });
    expect(html).not.toContain('data-role="superseded-shelf"');
  });

  // gap `variant-suggested-badge`: the server has served `suggested_variant` per site
  // since 5a and no surface read it — the operator could not see which part detection
  // proposed for the site they are declaring.
  it("the option detection proposed for the ACTIVE site is attributed", () => {
    const html = view({
      activeTooth: 30,
      detail: {
        ...detail,
        sites: [
          detail.sites[0]!,
          siteView({ tooth: 30, suggested_variant: "5020" }),
        ],
      },
    });
    expect(html).toMatch(
      /<option[^>]*data-variant="5020"[^>]*data-role="variant-suggested"|<option[^>]*data-role="variant-suggested"[^>]*data-variant="5020"/,
    );
    expect(html).toContain("suggested");
    // exactly one option wears it — the proposal is for ONE part, not a shelf tone
    expect(html.match(/data-role="variant-suggested"/g)).toHaveLength(1);
  });

  it("the attribution vanishes once that site is declared — the operator's act supersedes it", () => {
    const html = view({
      activeTooth: 30,
      detail: {
        ...detail,
        sites: [
          detail.sites[0]!,
          siteView({
            tooth: 30,
            suggested_variant: "5020",
            declared_variant: "5020",
          }),
        ],
      },
    });
    expect(html).not.toContain('data-role="variant-suggested"');
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

describe("the moment of moving forward — the set faced, the fork explicit", () => {
  /** A done run whose sites all carry verdicts: exactly where the fork is offered. */
  function forked(sites: CaseSessionDetail["sites"]): CaseSessionDetail {
    return caseSessionDetail({
      ...detail,
      sites,
      session: { ...detail.session, run_state: "done" },
    });
  }

  const cleanRun = () =>
    forked([
      siteView({
        tooth: 19,
        status: "ready",
        declared_variant: "5020",
        seat_method: "rim-seat",
        rim_agreement_mm: 0.07,
      }),
    ]);

  const flaggedRun = () =>
    forked([
      siteView({ tooth: 19, status: "flagged", declared_variant: "5020" }),
      siteView({
        tooth: 30,
        status: "ready",
        declared_variant: "5020",
        seat_method: "rim-seat",
        rim_agreement_mm: 0.11,
      }),
    ]);

  it("with no run, BOTH acts are inert and carry the flow's reason", () => {
    // the single Continue is gone (client 2026-07-27 #3): a blocked fork shows
    // both doors shut, each saying why, rather than one ambiguous button
    const html = view();
    expect(html).toMatch(/data-role="fork-skip"[^>]*aria-disabled="true"/);
    expect(html).toMatch(/data-role="fork-adjust"[^>]*aria-disabled="true"/);
    expect(html).toContain("Sites are still awaiting review");
    expect(html).not.toContain('data-role="continue-on"');
  });

  it("the summary states, per site, what each attestation stood on", () => {
    // client 2026-07-27 #2: "maybe at the time to move forward to the next step"
    const html = view({ detail: cleanRun() });
    expect(html).toContain('data-role="attestation-summary"');
    expect(html).toMatch(/data-role="attestation-line"[^>]*data-tooth="19"/);
    expect(html).toContain("Tooth 19 · 5020 · rim-seat, rim 0.07 mm");
  });

  it("an unattested site is NAMED in the summary instead of a line about a seat", () => {
    const html = view({ detail: flaggedRun() });
    expect(html).toMatch(/data-role="attestation-line"[^>]*data-attested="false"/);
    expect(html).toContain("Tooth 19 · 5020 · not attested (flagged)");
  });

  it("both acts render; Adjust leads when anything is flagged, and the skip states its cost", () => {
    const html = view({ detail: flaggedRun() });
    expect(html).toMatch(/data-role="fork-adjust"[^>]*class="button button--small button--primary"/);
    expect(html).toMatch(/data-role="fork-skip"[^>]*class="button button--small button--secondary"/);
    expect(html).toContain("1 flagged site stays");
    expect(html).toContain("own acknowledgment");
  });

  it("with nothing flagged the skip leads, and says there is nothing to rework", () => {
    const html = view({ detail: cleanRun() });
    expect(html).toMatch(/data-role="fork-skip"[^>]*class="button button--small button--primary"/);
    expect(html).toContain("Nothing is flagged");
  });

  it("names where the skip actually GOES — the library, not Delivery", () => {
    // the fork skips the ADJUSTMENT stage, and since 2026-08-01 the next page is the
    // construction library, not Delivery. The label said Deliver while the handler
    // routed to /library — caught by walking the app, not by a test over markup.
    const html = view({ detail: cleanRun() });
    expect(html).toContain("construction library");
    expect(html).not.toContain("go to Deliver");
  });

  it("a BLOCKED skip quotes the reason for the page it leads to", () => {
    // it quoted Deliver's, which since the library landed can read "pick a
    // construction part in the library first" — advice about a page two stages on,
    // offered as the reason this fork is shut. The fork is gated on the library, so
    // the library's reason is the only honest one to print.
    const html = view();
    expect(html).toMatch(/data-role="fork-skip"[^>]*aria-disabled="true"/);
    expect(html).not.toContain("Pick a construction part in the library first");
  });

  it("a recorded decision is shown, with the note that it rides into the evidence", () => {
    const decided = cleanRun();
    const html = view({
      detail: {
        ...decided,
        session: {
          ...decided.session,
          adjust_decision: {
            decision: "skip",
            at: "2026-07-28T09:00:00+00:00",
            run_id: "20260728-090000-abc123",
          },
        },
      },
    });
    expect(html).toContain('data-role="fork-recorded"');
    expect(html).toContain("adjustments skipped");
    // Retargeted 2026-07-30: the raw ISO instant (microseconds and all) was machine
    // text on an operator surface — the note now renders the minute, labelled UTC.
    expect(html).toContain("2026-07-28 09:00 UTC");
    expect(html).not.toContain("2026-07-28T09:00:00+00:00");
    // ...and the consequence in one clause (the old three-line version was part of
    // the footer bloat the client called out)
    expect(html).toContain("rides into the evidence");
  });

  it("a refused decision keeps the operator here, in the BFF's words", () => {
    const html = view({
      detail: cleanRun(),
      forkError: "HTTP 422 — every site needs its verdict before the fork",
    });
    expect(html).toContain('data-role="fork-error"');
    expect(html).toContain("every site needs its verdict");
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
    expect(html).toContain('data-role="declare-system"');
    expect(html).toContain('data-role="declare-variant"');
    // Retargeted 2026-07-30: the arch was a standing strip, open by default, and it
    // cost the panes a third of the stage — the union pane sank below the fold
    // (client: "small panels, the view is cut off ... maybe the arch context view
    // can just be a modal"). It is now a DIALOG behind one button: closed by
    // default, the WebGL viewer unmounted until asked for. The panes get the pixels.
    expect(html).toContain('data-role="arch-open"');
    expect(html).toContain("Arch context");
    expect(html).not.toContain('data-role="arch-dialog"');
    expect(html).not.toContain('data-role="main-stage"');
    // 5b: the three live panes and the review tick ride with the stage
    expect(html).toContain('data-role="declare-panes"');
    expect(html).toContain('data-role="pane-library"');
    expect(html).toContain('data-role="pane-scan"');
    expect(html).toContain('data-role="pane-union"');
    expect(html).toContain('data-role="review-tick"');
    expect(html).not.toContain('data-role="system-switch-confirm"');
    expect(html).not.toContain('data-role="declare-error"');
  });

  /* R3's claim "buccal and mesial grey out before a preview exists" was FALSE on this
     stage: the container rendered the toolbar without `viewPresetsAvailable` at all, so
     the view's own default (true) enabled both. Effects do not run in a static render,
     which is exactly the state this asserts — mounted, nothing previewed yet. */
  it("greys the off-axis presets until a preview lands — no preview exists at mount", () => {
    const html = renderToStaticMarkup(
      <StaticRouter location="/case/case-a/declare">
        <DeclareStage detail={detail} onDetail={() => undefined} />
      </StaticRouter>,
    );
    expect(html).toMatch(
      /data-role="view-preset"[^>]*data-preset="side-a"[^>]*disabled=""/,
    );
    expect(html).toMatch(
      /data-role="view-preset"[^>]*data-preset="side-b"[^>]*disabled=""/,
    );
    expect(html).not.toMatch(
      /data-role="view-preset"[^>]*data-preset="occlusal"[^>]*disabled=""/,
    );
  });
});

/**
 * THE WORKSPACE TOOLBAR (gaps `workspace-toolbar-site-chip`, `alignment-metrics-strip`,
 * `named-view-presets`). The panes were deliberately made to dominate this stage
 * (client 2026-07-27), and what that cost was the site's own identity: the tooth
 * number lives in the work column's headings and the queue rows, and all of those
 * scroll. The strip must therefore be OUTSIDE the scroll area, name the site, and
 * carry the server's own facts — never a verdict of ours.
 */
describe("the workspace toolbar over the panes", () => {
  it("names the tooth and the effective system beside the panes", () => {
    const html = view({ activeTooth: 30 });
    expect(html).toContain('data-role="workspace-toolbar"');
    expect(html).toContain('data-role="site-chip"');
    expect(html).toContain("Tooth 30");
    expect(html).toContain("conical-4x4");
  });

  it("the status chip renders the SERVER's rung verbatim — no locally computed verdict", () => {
    const html = view({ activeTooth: 19 });
    expect(html).toMatch(
      /data-role="toolbar-status"[^>]*data-status="declared"[^>]*>declared</,
    );
  });

  it("the ALIGNMENT strip carries variant, both published deviations, rotation, pairs", () => {
    const html = view({
      activeTooth: 19,
      runRows: [
        {
          tooth: 19,
          deviation_rms_mm: 0.0412,
          deviation_p90_mm: 0.0871,
          clocking: { notch_shift_deg: -1.42 },
          correspondence: { pairs: 3, max_pairs: 8 },
        },
      ],
    });
    expect(html).toContain('data-role="alignment-strip"');
    expect(html).toContain("ALIGNMENT");
    expect(html).toContain("0.041 mm");
    expect(html).toContain("0.087 mm");
    expect(html).toContain("-1.4°");
    expect(html).toContain("3 / 8");
  });

  it("PAIRS is a dash while the server carries no correspondence for the site", () => {
    const html = view({ activeTooth: 19, runRows: [{ tooth: 19 }] });
    expect(html).toMatch(/data-stat="pairs"[\s\S]{0,200}?—<\/span>/);
    expect(html).not.toContain("0 / 8");
  });

  it("the strip states no tolerance and no pass/fail — those are server-derived", () => {
    const html = view({ activeTooth: 19, runRows: [{ tooth: 19, deviation_rms_mm: 0.9 }] });
    expect(html).not.toContain("in tolerance");
    expect(html).not.toContain("out of tolerance");
  });

  it("the arch dialog opener rides IN the toolbar — one strip of chrome, not two", () => {
    const html = view();
    const toolbar = html.slice(html.indexOf('data-role="workspace-toolbar"'));
    expect(toolbar.slice(0, toolbar.indexOf("</div>") + 6)).toContain(
      'data-role="arch-open"',
    );
  });

  /* THE PROVENANCE POPOVER (gap `deviation-budget-in-workspace`) rides beside the
     arch opener in the SAME children slot — pinned here so severing either mount
     (this stage forgetting to render `<WorkspaceInsight>`, or the component itself
     losing its toggle) fails a test instead of going unnoticed until a demo. */
  it("carries the site-numbers-and-case-log toggle beside the arch opener", () => {
    const html = view();
    const toolbar = html.slice(html.indexOf('data-role="workspace-toolbar"'));
    expect(toolbar.slice(0, toolbar.indexOf("</div>") + 6)).toContain(
      'data-role="insight-toggle"',
    );
  });

  it("the zoom step renders only where the stage can actually apply it", () => {
    // Same rule as the presets: a control with no handler is a control that lies.
    expect(view()).not.toContain('data-role="zoom"');
    const wired = view({ onZoom: () => undefined });
    expect(wired).toMatch(/data-role="zoom"[^>]*data-direction="out"/);
    expect(wired).toMatch(/data-role="zoom"[^>]*data-direction="in"/);
  });

  it("the zoom is ONE control for the whole workspace, not one per pane", () => {
    /* Client ruling 2026-08-02: "global is probably better on adjustment views". The
       three panes are read side by side, so a zoom that reached only one of them would
       make that comparison lie about scale — and this is the assertion that catches a
       later refactor moving the buttons into the pane chrome. */
    const wired = view({ onZoom: () => undefined });
    expect(wired.match(/data-role="zoom"/g)).toHaveLength(2);
    const toolbar = wired.slice(wired.indexOf('data-role="workspace-toolbar"'));
    expect(toolbar.indexOf('data-role="zoom"')).toBeGreaterThan(-1);
  });

  it("a spent zoom direction DISABLES rather than clicking into nothing", () => {
    // the band is packages/viewer's; the toolbar only asks whether a step remains
    const floored = view({ onZoom: () => undefined, zoomLevel: 99 });
    expect(floored).toMatch(/data-direction="in"[^>]*disabled/);
    expect(floored).not.toMatch(/data-direction="out"[^>]*disabled/);
  });

  it("the named view presets render only where the stage can actually apply them", () => {
    // Dead controls are worse than absent ones: with no handler the group is not
    // rendered at all (see DeclareStageView's note on the pane-camera seam).
    expect(view()).not.toContain('data-role="view-preset"');
    const wired = view({
      onSelectView: () => undefined,
      viewPreset: "side-a",
      viewPresetsAvailable: true,
    });
    expect(wired).toMatch(/data-role="view-preset"[^>]*data-preset="occlusal"/);
    expect(wired).toMatch(
      /data-role="view-preset"[^>]*data-preset="side-a"[^>]*aria-pressed="true"/,
    );
    expect(wired).toMatch(/data-role="view-preset"[^>]*data-preset="side-b"/);
  });

  it("off-axis presets are inert until a seated pose supplies the clock reference", () => {
    const html = view({ onSelectView: () => undefined, viewPresetsAvailable: false });
    expect(html).toMatch(
      /data-role="view-preset"[^>]*data-preset="side-a"[^>]*disabled=""/,
    );
    // occlusal is exactly the framing the pane already has, so it always works
    expect(html).not.toMatch(
      /data-role="view-preset"[^>]*data-preset="occlusal"[^>]*disabled=""/,
    );
  });

  /* THE SAFE DEFAULT IS THE ONE THAT CANNOT LIE (design review 2026-07-31). The flag
     defaulted to TRUE, so the one caller that never supplied it — DeclareStage —
     offered both off-axis presets before any preview existed: pane 1 swung side-on
     (partCameraFrame always carries up:[1,0,0]) while panes 2/3 stayed on the occlusal
     proxy, and the toolbar claimed the new view for all three. */
  it("assumes NO clock reference until a caller says otherwise", () => {
    const html = view({ onSelectView: () => undefined });
    expect(html).toMatch(
      /data-role="view-preset"[^>]*data-preset="side-a"[^>]*disabled=""/,
    );
    expect(html).toMatch(
      /data-role="view-preset"[^>]*data-preset="side-b"[^>]*disabled=""/,
    );
  });

  it("the toolbar is NOT inside the work column's scroll box — that is the whole point", () => {
    /* Anchored on the SITE QUEUE, the work column's only remaining occupant since the
       system, the variants and the forward acts moved into the stage column beneath
       the panes (2026-08-02). The old anchor was `workbench__work-footer`, which was
       the column's last child until it moved as well. */
    const html = view();
    const scroll = html.indexOf("workbench__work-scroll");
    const queue = html.indexOf('data-role="site-queue"');
    const toolbar = html.indexOf('data-role="workspace-toolbar"');
    expect(scroll).toBeGreaterThan(-1);
    expect(toolbar).toBeGreaterThan(scroll);
    if (queue > -1) expect(toolbar).toBeGreaterThan(queue);
  });
});

/**
 * THE STRIP AND THE PANE UNDER IT MUST NOT DISAGREE (design review 2026-07-31).
 *
 * On Declare before the run, every numeric cell of the strip labelled ALIGNMENT read
 * "—" while the union pane below published the SAME site's RMS and p90 from
 * `payload.stats`. A dash in a deviation column reads as a measured zero — which is
 * precisely why the queue rows in the same commit say "no run has measured this fit
 * yet" instead of one.
 */
describe("the ALIGNMENT strip before any run", () => {
  it("says NO RUN YET rather than a dash, and names whose figures it is showing", () => {
    const html = view({
      activeTooth: 19,
      previewFigures: {
        poseAvailable: true,
        rmsMm: 0.0861,
        p90Mm: 0.1423,
        source: "preview",
      },
    });
    expect(html).toContain("0.086 mm");
    expect(html).toContain("0.142 mm");
    expect(html).toContain("DEV RMS (preview)");
    // the preview measures no clocking residual and places no pairs
    expect(html).toMatch(/data-stat="rotation"[\s\S]{0,200}?no run yet</);
  });

  it("with neither a run nor a preview it states the absence, not a number", () => {
    const html = view({ activeTooth: 19 });
    expect(html).toMatch(/data-stat="dev-rms"[\s\S]{0,200}?no run yet</);
  });
});
