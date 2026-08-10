/**
 * THE PANE WORKSPACE'S SHARED POLICY. The link mechanism is the viewer package's;
 * what this app decides is the OPENING state and the words on the toggle.
 */
import { describe, expect, it } from "vitest";
import { PANES_OPEN_LINKED, paneLinkLabel, workspaceAnalysisText } from "./workspace";

describe("the pane link", () => {
  it("opens LINKED — the built toggle was reported missing because it opened off", () => {
    // client 2026-08-04; both stages import this one constant, so they cannot
    // open in different moods
    expect(PANES_OPEN_LINKED).toBe(true);
  });

  it("the toggle says the state it is in and the act it offers", () => {
    // Condensed 2026-08-05 (client, live-testing: "condense this buttons in
    // adjustments tab it takes a lot of space") — "rotating together" was the
    // longest word on the toolbar's control row. The button's own `title` still
    // carries the full sentence ("Rotate all three panels together (same angles
    // and zoom, each around its own content)"), so the word dropped from the
    // label is not lost, only moved off the row.
    expect(paneLinkLabel(true)).toBe("⛓ linked");
    expect(paneLinkLabel(false)).toBe("⛓ link panes");
  });
});

describe("workspaceAnalysisText — the workspace evidence digest (client 2026-08-10)", () => {
  it("carries the toolbar, the served numbers with bands, and the log verbatim", () => {
    const text = workspaceAnalysisText(
      "cap6020-neodent-gm",
      29,
      [{ id: "dev-rms", label: "DEV RMS (run)", value: "0.294 mm" }] as never,
      {
        tooth: 29,
        run_id: "r1",
        overall_band: "fail",
        missing: ["confidence_grade"],
        stale_metrics: ["rim_agreement_mm"],
        metrics: [
          {
            key: "deviation_rms",
            label: "Surface deviation map — RMS",
            unit: "mm",
            value: 0.29,
            display: "0.29 mm",
            band: "review",
            industry_ref: { value: "±0.5 mm map convention", source: "x" },
            note: null,
            bands: { pass: 0.2, review: 0.5 },
            audience: "both",
          },
        ],
        context: {},
      } as never,
      {
        case_id: "cap6020-neodent-gm",
        entries: [
          {
            at: "2026-08-10 01:41 UTC",
            event: "site-adjusted",
            detail:
              "fit-by-points — fit by 2 point pair(s) → 2 observation(s): rotated -14.7°",
            tooth: 29,
          },
        ],
        recorded: 109,
        window: 40,
        run_id: "r1",
        site_adjustments: [],
      } as never,
    );
    expect(text).toContain("cap6020-neodent-gm · tooth 29");
    expect(text).toContain("DEV RMS (run): 0.294 mm");
    expect(text).toContain("overall band: fail");
    expect(text).toContain(
      "Surface deviation map — RMS: review 0.29 mm (pass <= 0.2 · review <= 0.5)",
    );
    expect(text).toContain("confidence_grade: not measured");
    expect(text).toContain("stale after rework");
    expect(text).toContain("fit by 2 point pair(s) → 2 observation(s)");
  });
});
