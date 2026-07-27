/**
 * THE TOOTH CHART's rendered contract. Pinned: all 32 teeth present, each one's ACCESSIBLE NAME
 * carrying the anatomical label and the full state sentence (colour is never the only carrier),
 * the case's jaw marked and the other arch dimmed, the shared cursor shown as aria-current, an
 * empty tooth on the other arch not being an add target, and the auto-number toggle naming the
 * number it would use.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ToothChart, toothStateSummary } from "./ToothChart";
import type { ToothChartSite } from "../domain/toothChart";

const SITES: ToothChartSite[] = [
  { tooth: 3, marked: true, reviewed: true, flags: [] },
  { tooth: 14, marked: false, reviewed: false, flags: ["capture-rescan"] },
];

function render(over: Partial<Parameters<typeof ToothChart>[0]> = {}) {
  return renderToStaticMarkup(
    <ToothChart
      jaw="upper"
      sites={SITES}
      activeTooth={3}
      armedTooth={null}
      autoNumber
      nextTooth={4}
      addBlockedReason={null}
      onSelectTooth={() => {}}
      onAddTooth={() => {}}
      onToggleAutoNumber={() => {}}
      onCancelAdd={() => {}}
      {...over}
    />,
  );
}

describe("toothStateSummary", () => {
  it("says what an occupied tooth's site actually is, flags included", () => {
    expect(
      toothStateSummary({
        tooth: 3,
        jaw: "upper",
        label: "Tooth 3 — upper right first molar",
        siteIndex: 0,
        marked: true,
        reviewed: true,
        active: true,
        inCaseJaw: true,
        flags: ["rotation-unverified"],
      }),
    ).toBe("site 1 · marks placed · reviewed · rotation unverified");
  });

  it("offers an empty tooth on the case's jaw, and does not offer one on the other arch", () => {
    const base = {
      tooth: 5,
      jaw: "upper" as const,
      label: "Tooth 5 — upper right first premolar",
      siteIndex: null,
      marked: false,
      reviewed: false,
      active: false,
      flags: [],
    };
    expect(toothStateSummary({ ...base, inCaseJaw: true })).toBe("no site — add one here");
    expect(toothStateSummary({ ...base, inCaseJaw: false })).toBe("no site (other arch)");
  });
});

describe("ToothChart", () => {
  it("renders every Universal tooth as a button with an anatomical accessible name", () => {
    const html = render();
    for (let tooth = 1; tooth <= 32; tooth += 1) {
      expect(html).toContain(`>${tooth}</span>`);
    }
    expect(html).toContain("Tooth 3 — upper right first molar — site 1 · marks placed · reviewed");
    expect(html).toContain("Tooth 30 — lower right first molar");
  });

  it("marks the case's jaw and dims the other arch", () => {
    const upper = render();
    expect(upper).toContain("tooth-chart__row--case-jaw");
    expect(upper).toContain("this case");
    expect(upper).toContain("tooth-chart__tooth--off-jaw");
    const lower = render({ jaw: "lower", sites: [], activeTooth: null, nextTooth: 17 });
    expect(lower).toContain("Lower arch · 17–32");
    expect(lower).toContain("tooth-chart__row--other-jaw");
  });

  it("shows the shared cursor as aria-current on the active site's tooth", () => {
    const html = render();
    expect(html).toMatch(/aria-current="true"[^>]*>?/);
    expect(html).toContain("tooth-chart__tooth--active");
    // moving the cursor moves the marker — the chart never holds a second selection
    expect(render({ activeTooth: 14 })).toContain("tooth-chart__tooth--active");
  });

  it("reports a site's flags in its name, not only in colour", () => {
    expect(render()).toContain("capture needs a rescan");
  });

  /** The button element for one tooth, isolated from the rest of the arch. */
  function toothButton(html: string, tooth: number): string {
    const at = html.indexOf(`aria-label="Tooth ${tooth} `);
    expect(at).toBeGreaterThan(-1);
    const opens = html.lastIndexOf("<button", at);
    return html.slice(opens, html.indexOf(">", at));
  }

  it("disables empty teeth on the other arch (a site cannot be added off-jaw)", () => {
    // tooth 30 is empty and on the lower arch while the run is selected upper
    expect(toothButton(render(), 30)).toContain('disabled=""');
    // …while an empty tooth on the case's own arch is an add target
    expect(toothButton(render(), 5)).not.toContain("disabled");
  });

  it("keeps an EXISTING off-jaw site clickable, flagged, so the operator can fix it", () => {
    const html = render({
      sites: [{ tooth: 30, marked: false, reviewed: false, flags: ["off-jaw"] }],
      activeTooth: null,
    });
    expect(html).toContain("site is on the other arch than the selected jaw");
    expect(toothButton(html, 30)).not.toContain("disabled");
  });

  it("names the number auto-increment would use, and says when the arch is full", () => {
    expect(render()).toContain("+ Add site (tooth 4)");
    const full = render({ nextTooth: null });
    expect(full).toContain("Every tooth on the upper arch already has a site");
    expect(full).toContain('disabled="" title="Every tooth on the upper arch already has a site"');
  });

  it("offers manual entry instead when auto-numbering is off", () => {
    const html = render({ autoNumber: false });
    expect(html).toContain('for="tooth-chart-manual"');
    expect(html).toContain('id="tooth-chart-manual"');
    expect(html).not.toContain("+ Add site (tooth 4)");
    expect(html).toContain("Automatic tooth number increasing");
  });

  it("says WHY adding is refused rather than presenting a dead control", () => {
    const html = render({
      addBlockedReason: "Finish or cancel the brush stroke first — it owns clicks on the scan.",
    });
    expect(html).toContain(
      'disabled="" title="Finish or cancel the brush stroke first — it owns clicks on the scan."',
    );
    // …and the empty teeth stop offering themselves too, for the same reason
    expect(toothButton(html, 5)).toContain('disabled=""');
  });

  it("shows the arm banner while a new site's scan click is pending, and blocks other adds", () => {
    const html = render({ armedTooth: 4 });
    expect(html).toContain("Click tooth 4&#x27;s healing cap on the scan…");
    expect(html).toContain("Cancel");
    // the empty teeth stop offering themselves while one placement is already pending
    expect(toothButton(html, 5)).toContain('disabled=""');
  });
});
