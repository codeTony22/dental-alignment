/**
 * Intake's control surface (plan §4 slice 4), statically rendered per the repo
 * convention: the banner-before-work doctrine, the honest detect lifecycle, the chips,
 * the choices panel showing PERSISTED state (pre-fills where nothing is chosen), and
 * the refusal surfaced in the backend's words. The auto-fire DECISION and the choice-
 * document assembly are pure and pinned in domain/intake.test.ts; the PUT/POST wiring
 * functions are the api client's, pinned in api/client.test.ts.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { StaticRouter } from "react-router-dom";
import { IntakeStage, IntakeStageView } from "./IntakeStage";
import {
  captureAssessment,
  caseSessionDetail,
  detectedProposal,
  detectionView,
  rescanAssessment,
  siteView,
} from "../testing/fixtures";

function view(overrides: Partial<Parameters<typeof IntakeStageView>[0]> = {}) {
  return renderToStaticMarkup(
    <StaticRouter location="/case/case-a/intake">
      <IntakeStageView
        detail={caseSessionDetail()}
        detectPhase={{ kind: "idle" }}
        savingChoices={false}
        choicesError={null}
        onChoice={() => undefined}
        onRetryDetect={() => undefined}
        {...overrides}
      />
    </StaticRouter>,
  );
}

describe("the capture banner — verdicts BEFORE work (the chair-side moment)", () => {
  it("absent when nothing is rescan-grade", () => {
    expect(view()).not.toContain('data-role="capture-banner"');
  });

  it("a rescan-grade site raises the banner with the worker's sentence", () => {
    const html = view({
      detail: caseSessionDetail({
        sites: [
          siteView({ tooth: 19, capture: rescanAssessment("Only 31% of the rim arc.") }),
        ],
      }),
    });
    expect(html).toContain('data-role="capture-banner"');
    expect(html).toContain("Rescan recommended");
    expect(html).toContain("patient is still in the chair");
    expect(html).toContain("Tooth 19");
    expect(html).toContain("Only 31% of the rim arc.");
  });
});

describe("the detect lifecycle, honestly named", () => {
  it("detecting shows the busy state", () => {
    expect(view({ detectPhase: { kind: "detecting" } })).toContain("Detecting caps…");
  });

  it("a refusal shows the backend's words and a retry", () => {
    const html = view({
      detectPhase: {
        kind: "failed",
        detail: "HTTP 422 — the scan upper.stl holds no surface to detect on",
      },
    });
    expect(html).toContain('data-role="detect-error"');
    expect(html).toContain("holds no surface");
    expect(html).toContain("Try again");
  });
});

describe("the site list with capture chips", () => {
  it("each site carries its verdict chip; unassessed is named, not blank", () => {
    const html = view({
      detail: caseSessionDetail({
        sites: [
          siteView({ tooth: 19, capture: captureAssessment({ verdict: "marginal" }) }),
          siteView({ tooth: 30, capture: null }),
        ],
      }),
    });
    // Parity fix (review finding 4): the chip speaks the demo's words, not the bare verdict.
    expect(html).toMatch(/data-verdict="marginal"[^>]*>capture marginal/);
    expect(html).toContain("not assessed");
  });

  it("unmatched detections are counted, not hidden — Declare assigns teeth", () => {
    const html = view({
      detail: caseSessionDetail({
        detection: detectionView([detectedProposal({ tooth_guess: null })]),
      }),
    });
    expect(html).toContain("1 detected site without a curated tooth yet");
  });
});

describe("the choices panel — the BFF's effective values, with their source chips", () => {
  const withCatalog = caseSessionDetail({
    case: {
      id: "case-a",
      doctor: "Dr. Rivera",
      jaw: "lower",
      scan_filename: "scan.stl",
      suggested_model: "conical-4x4",
      suggested_construction: "dess/a.stl",
    },
    catalog: {
      groups: [],
      constructions: [{ path_id: "dess/a.stl", label: "dess — a" }],
    },
    // the BFF's effective document for this case (client 2026-07-27): suggestion
    // covers construction and jaw, the standing default covers relief
    choices: {
      construction_path: null,
      jaw: null,
      gingival_offset_mm: null,
      gingival_offset_default_mm: 0.2,
      effective_construction: { value: "dess/a.stl", source: "suggested" },
      effective_jaw: { value: "lower", source: "suggested" },
      effective_relief: { value: 0.2, source: "default" },
      complete: true,
    },
  });

  it("renders the effective values with their source chips, like the system bar", () => {
    const html = view({ detail: withCatalog });
    expect(html).toMatch(/data-role="choice-construction"[^>]*>/);
    expect(html).toContain('<option value="dess/a.stl" selected="">');
    expect(html).toMatch(/aria-pressed="true"[^>]*>lower/);
    expect(html).toMatch(/data-role="choice-relief"[^>]*value="0.2"/);
    // the chips are the SERVER's attribution, never a client-side comparison
    expect(html).toMatch(/data-role="choice-source"[^>]*data-choice="construction"[^>]*>[^<]*suggested/);
    expect(html).toMatch(/data-role="choice-source"[^>]*data-choice="jaw"[^>]*>[^<]*suggested/);
    expect(html).toMatch(/data-role="choice-source"[^>]*data-choice="relief"[^>]*>[^<]*default/);
  });

  it("a persisted choice wins over the pre-fill and drops its chip", () => {
    const html = view({
      detail: caseSessionDetail({
        ...withCatalog,
        choices: {
          construction_path: null,
          jaw: "upper",
          gingival_offset_mm: 0.1,
          gingival_offset_default_mm: 0.2,
          effective_construction: { value: "dess/a.stl", source: "suggested" },
          effective_jaw: { value: "upper", source: "chosen" },
          effective_relief: { value: 0.1, source: "chosen" },
          complete: true,
        },
      }),
    });
    expect(html).toMatch(/aria-pressed="true"[^>]*>upper/);
    expect(html).toMatch(/data-role="choice-relief"[^>]*value="0.1"/);
    // chosen values carry no chip; the still-suggested construction keeps its own
    expect(html).not.toMatch(/data-role="choice-source"[^>]*data-choice="jaw"/);
    expect(html).not.toMatch(/data-role="choice-source"[^>]*data-choice="relief"/);
    expect(html).toMatch(/data-role="choice-source"[^>]*data-choice="construction"/);
  });

  it("the ceiling readout renders per variant row", () => {
    const html = view({
      detail: caseSessionDetail({
        relief_ceilings: [
          {
            variant: "5020",
            construction_path: "dess/a.stl",
            model: "conical-4x4",
            max_safe_mm: 0.13,
            requested_default_mm: 0.2,
            default_is_safe: false,
            limited_by: "wall",
            wall_mm_at_zero: 0.6,
            wall_mm_at_default: null,
            shippable_at_zero: true,
            min_wall_rule_mm: 0.4,
            searched_to_mm: 0.5,
            note: "x",
            error: null,
          },
        ],
      }),
    });
    expect(html).toContain("ceiling 0.13mm");
    expect(html).toContain("cut at the ceiling"); // default ask 0.2 exceeds it
  });

  it("a 422 surfaces in the backend's words", () => {
    const html = view({
      choicesError:
        "HTTP 422 — jaw must be one of upper, lower, got 'sideways'",
    });
    expect(html).toContain('data-role="choices-error"');
    expect(html).toContain("jaw must be one of upper, lower");
  });

  it("saving is stated while the PUT is in flight (optimism is OFF)", () => {
    expect(view({ savingChoices: true })).toContain("Saving choices…");
  });
});

describe("continue to Declare — per flow.ts, sites detected", () => {
  it("enabled as a link when the case has sites", () => {
    const html = view();
    expect(html).toMatch(
      /data-role="continue-declare"[^>]*href="\/case\/case-a\/declare"/,
    );
  });

  it("disabled with the flow's own reason when nothing is detected", () => {
    const html = view({ detail: caseSessionDetail({ sites: [] }) });
    expect(html).toMatch(/data-role="continue-declare"[^>]*aria-disabled="true"/);
    expect(html).toContain("Nothing to declare yet");
  });
});

describe("the IntakeStage container, statically (effects do not run)", () => {
  it("mounts the stage surface: 3D, site list, choices — honest pre-flight", () => {
    const html = renderToStaticMarkup(
      <StaticRouter location="/case/case-a/intake">
        <IntakeStage detail={caseSessionDetail()} onDetail={() => undefined} />
      </StaticRouter>,
    );
    expect(html).toContain('data-role="main-stage"');
    expect(html).toContain('data-role="intake-sites"');
    expect(html).toContain('data-role="intake-choices"');
    // detection has not fired statically — no busy claim, no banner, no error
    expect(html).not.toContain("Detecting caps");
    expect(html).not.toContain('data-role="detect-error"');
  });
});

describe("marking a cap the detector missed (client 2026-07-28)", () => {
  it("offers the door, closed, when nothing is in flight", () => {
    const html = view();
    expect(html).toContain('data-role="mark-arm"');
    expect(html).toContain("Mark a missed cap");
    // no prompt and no tooth field until the operator asks
    expect(html).not.toContain('data-role="mark-prompt"');
    expect(html).not.toContain('data-role="mark-tooth"');
  });

  it("armed, it asks for the CENTRE and nothing else", () => {
    const html = view({ markArmed: true });
    expect(html).toContain("Click the centre of the cap on the scan");
    // the tooth is asked for AFTERWARDS — holding a number in your head while
    // hunting a cap in 3D is the version this deliberately avoids
    expect(html).not.toContain('data-role="mark-tooth"');
  });

  it("with a centre placed it asks which tooth, and only then offers to add", () => {
    const html = view({ markPending: [1, 2, 3], markTooth: "7" });
    expect(html).toContain("Centre placed. Which tooth is it?");
    expect(html).toContain('data-role="mark-tooth"');
    expect(html).toContain('data-role="mark-submit"');
  });

  it("cannot submit without a tooth", () => {
    const html = view({ markPending: [1, 2, 3], markTooth: "" });
    expect(html).toMatch(/data-role="mark-submit"[^>]*disabled/);
  });

  it("shows the BFF's own refusal rather than a summary of it", () => {
    const html = view({
      markPending: [1, 2, 3],
      markTooth: "13",
      markError: "tooth 13 is already a site on case 'neodent-gm'",
    });
    expect(html).toContain('data-role="mark-error"');
    expect(html).toContain("already a site");
  });
});
