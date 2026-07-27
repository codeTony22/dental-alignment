/**
 * THE LIBRARY SELECTION state machine (client directive 2026-07-25: "the lab chooses,
 * the software never guesses"). The properties pinned here are the ones the client's disclaimer
 * and the backend's 422 both depend on:
 *
 *  - a REVIEW is about a specific part, so changing what is selected invalidates it — the whole
 *    point of "I acknowledge that the library part selected matches the scan data";
 *  - a cap variant belongs to ONE system, so switching systems drops every chosen variant;
 *  - Process is refused, in words, until every required selection is made AND every site reviewed;
 *  - superseded archives are a SEPARATE group, and a legacy shelf is not a selectable system.
 */
import { describe, expect, it } from "vitest";
import {
  GINGIVAL_OFFSET_DEFAULT_MM,
  GINGIVAL_OFFSET_MAX_MM,
  activeSite,
  canProcess,
  catalogGroupLabels,
  findVariantEntry,
  formatOffsetMm,
  groupConstructionsByVendor,
  initialSelection,
  missingSelections,
  offsetError,
  parseGingivalOffset,
  partitionVariants,
  processBlockers,
  stepSite,
  supersededArchiveLabel,
  systemChoices,
  unreviewedSiteNumbers,
  withActiveSite,
  withConstruction,
  withJaw,
  withModel,
  withOffsetInput,
  withReviewed,
  withSites,
  withVariant,
} from "./librarySelection";
import { supersededBadgeText } from "../components/LibraryBrowser";
import type { ConstructionPart, LibraryCatalogEntry, LibraryCatalogGroup } from "./types";

function makeEntry(overrides: Partial<LibraryCatalogEntry> = {}): LibraryCatalogEntry {
  return {
    id: "6020",
    variant: "6020",
    label: "neodent-gm-6020",
    rimDiameterMm: 6.16,
    heightMm: 3.38,
    filename: "neodent-gm-6020.stl",
    sha256: "abc",
    flags: [],
    duplicateOf: [],
    meshUrl: "/api/library/neodent-gm/6020/mesh",
    ...overrides,
  };
}

const ARCHIVED = makeEntry({
  id: "superseded-2026-07-13--5020",
  variant: "5020",
  filename: "superseded-2026-07-13/neodent-gm-5020.stl",
  flags: ["superseded"],
});

const GROUPS: LibraryCatalogGroup[] = [
  {
    model: "neodent-gm",
    legacy: false,
    variants: [makeEntry(), makeEntry({ id: "6030", variant: "6030" }), ARCHIVED],
  },
  { model: "zimmer-4.5", legacy: false, variants: [makeEntry({ id: "7030", variant: "7030" })] },
  { model: "vendor-legacy-library", legacy: true, variants: [makeEntry({ id: "legacy_master" })] },
];

function twoSites() {
  return initialSelection({
    suggestedModel: "neodent-gm",
    suggestedConstruction: "dess/neodent-gm-scanbody.stl",
    jaw: "lower",
    sites: [{ tooth: 3 }, { tooth: 29 }],
  });
}

/** A selection with everything chosen and every site reviewed — the only state Process allows. */
function readyState() {
  let state = twoSites();
  state = withVariant(state, 0, "6020");
  state = withVariant(state, 1, "6030");
  state = withReviewed(state, 0, true);
  state = withReviewed(state, 1, true);
  return state;
}

describe("initialSelection", () => {
  it("preselects the case's suggestions and the client's 0.20mm relief, nothing reviewed", () => {
    const state = twoSites();
    expect(state.model).toBe("neodent-gm");
    expect(state.constructionPathId).toBe("dess/neodent-gm-scanbody.stl");
    expect(state.jaw).toBe("lower");
    expect(state.gingivalOffsetMm).toBe(GINGIVAL_OFFSET_DEFAULT_MM);
    expect(state.gingivalOffsetInput).toBe("0.20");
    expect(state.sites.map((s) => s.reviewed)).toEqual([false, false]);
  });

  it("starts EMPTY for a case whose folder name matched nothing — the state that must block a run", () => {
    const state = initialSelection({
      suggestedModel: null,
      suggestedConstruction: null,
      jaw: "upper",
      sites: [{ tooth: 3 }],
    });
    expect(state.model).toBeNull();
    expect(state.constructionPathId).toBeNull();
    expect(missingSelections(state)).toEqual([
      "the implant system",
      "the construction part",
      "the cap variant for site 1 (tooth 3)",
    ]);
  });

  it("adopts a variant already declared on the row (step 3's picker)", () => {
    const state = initialSelection({
      suggestedModel: "neodent-gm",
      suggestedConstruction: "dess/x.stl",
      jaw: "upper",
      sites: [{ tooth: 3, declaredVariant: "6020" }, { tooth: 5, declaredVariant: "  " }],
    });
    expect(state.sites[0]?.variantId).toBe("6020");
    expect(state.sites[1]?.variantId).toBeNull();
  });
});

describe("a review is about a SPECIFIC part", () => {
  it("changing a site's cap clears THAT site's review only", () => {
    const next = withVariant(readyState(), 0, "6030");
    expect(next.sites.map((s) => s.reviewed)).toEqual([false, true]);
  });

  it("changing the implant system drops every variant AND every review", () => {
    const next = withModel(readyState(), "zimmer-4.5");
    expect(next.sites.map((s) => s.variantId)).toEqual([null, null]);
    expect(next.sites.map((s) => s.reviewed)).toEqual([false, false]);
  });

  it("changing the construction part clears every review (it ships in the same part)", () => {
    const next = withConstruction(readyState(), "atlantis/zimmer-4.5-scanbody.stl");
    expect(next.sites.every((s) => !s.reviewed)).toBe(true);
    // the caps themselves are untouched — the construction is a different choice
    expect(next.sites.map((s) => s.variantId)).toEqual(["6020", "6030"]);
  });

  it("changing the jaw clears every review", () => {
    expect(withJaw(readyState(), "upper").sites.every((s) => !s.reviewed)).toBe(true);
  });

  it("changing the relief clears every review — it changes the emitted surface", () => {
    const next = withOffsetInput(readyState(), "0.35");
    expect(next.gingivalOffsetMm).toBe(0.35);
    expect(next.sites.every((s) => !s.reviewed)).toBe(true);
  });

  it("re-selecting the SAME value is not a change and keeps the reviews", () => {
    const ready = readyState();
    expect(withModel(ready, "neodent-gm")).toBe(ready);
    expect(withConstruction(ready, "dess/neodent-gm-scanbody.stl")).toBe(ready);
    expect(withJaw(ready, "lower")).toBe(ready);
    expect(withVariant(ready, 0, "6020")).toBe(ready);
    expect(withOffsetInput(ready, "0.20").sites.every((s) => s.reviewed)).toBe(true);
  });
});

describe("the gingival profile offset", () => {
  it("accepts values inside the backend's own bounds", () => {
    expect(parseGingivalOffset("0")).toEqual({ kind: "ok", valueMm: 0 });
    expect(parseGingivalOffset("0.20")).toEqual({ kind: "ok", valueMm: 0.2 });
    expect(parseGingivalOffset(` ${GINGIVAL_OFFSET_MAX_MM} `)).toEqual({
      kind: "ok",
      valueMm: GINGIVAL_OFFSET_MAX_MM,
    });
  });

  it("refuses a typo rather than clamping it — 2mm would eat the part", () => {
    const parsed = parseGingivalOffset("2");
    expect(parsed.kind).toBe("error");
    expect(parsed.kind === "error" && parsed.message).toContain("between 0 and 1.00 mm");
  });

  it("refuses a negative, an empty box and a non-number", () => {
    expect(parseGingivalOffset("-0.1").kind).toBe("error");
    expect(parseGingivalOffset("   ").kind).toBe("error");
    expect(parseGingivalOffset("wide").kind).toBe("error");
  });

  it("keeps the raw text but NOT the bad value, and reports the error", () => {
    const next = withOffsetInput(twoSites(), "9");
    expect(next.gingivalOffsetInput).toBe("9");
    expect(next.gingivalOffsetMm).toBe(GINGIVAL_OFFSET_DEFAULT_MM); // last good value survives
    expect(offsetError(next)).toContain("between 0 and 1.00 mm");
    expect(missingSelections(next)).toContain("a valid gingival profile offset");
  });

  it("keeps a half-typed value on screen without rewriting it", () => {
    const next = withOffsetInput(twoSites(), "0.");
    expect(next.gingivalOffsetInput).toBe("0.");
  });

  it("formats to two decimals for display", () => {
    expect(formatOffsetMm(0.2)).toBe("0.20");
  });
});

describe("the Process gate", () => {
  it("names every missing selection, in the column's own order", () => {
    let state = initialSelection({
      suggestedModel: null,
      suggestedConstruction: null,
      jaw: "upper",
      sites: [{ tooth: 3 }, { tooth: 29 }],
    });
    state = withVariant(state, 0, "6020");
    expect(processBlockers(state)).toEqual([
      "the implant system",
      "the construction part",
      "the cap variant for site 2 (tooth 29)",
      "a review of sites 1, 2",
    ]);
    expect(canProcess(state)).toBe(false);
  });

  it("still refuses when everything is selected but a detection is unreviewed", () => {
    const state = withReviewed(readyState(), 1, false);
    expect(unreviewedSiteNumbers(state)).toEqual([2]);
    expect(processBlockers(state)).toEqual(["a review of site 2"]);
    expect(canProcess(state)).toBe(false);
  });

  it("allows Process only once every selection is made and every site reviewed", () => {
    expect(canProcess(readyState())).toBe(true);
    expect(processBlockers(readyState())).toEqual([]);
  });

  it("refuses a case with no marked sites at all", () => {
    const state = initialSelection({
      suggestedModel: "neodent-gm",
      suggestedConstruction: "dess/x.stl",
      jaw: "upper",
      sites: [],
    });
    expect(processBlockers(state)).toEqual(["at least one marked site"]);
  });
});

describe("the site stepper", () => {
  it("clamps at both ends rather than wrapping", () => {
    const state = twoSites();
    expect(stepSite(state, -1).activeSiteIndex).toBe(0);
    expect(stepSite(state, 1).activeSiteIndex).toBe(1);
    expect(stepSite(stepSite(state, 1), 1).activeSiteIndex).toBe(1);
    expect(withActiveSite(state, 99).activeSiteIndex).toBe(1);
  });

  it("reports the active site", () => {
    expect(activeSite(stepSite(twoSites(), 1))?.tooth).toBe(29);
    expect(activeSite(withSites(twoSites(), []))).toBeNull();
  });
});

describe("withSites — re-keying against the step-3 rows", () => {
  it("carries each site's choice and review by TOOTH, and drops a removed site", () => {
    const next = withSites(readyState(), [{ tooth: 29 }]);
    expect(next.sites).toEqual([{ tooth: 29, variantId: "6030", reviewed: true }]);
    expect(next.activeSiteIndex).toBe(0);
  });

  it("adds a new tooth unchosen and unreviewed", () => {
    const next = withSites(readyState(), [{ tooth: 3 }, { tooth: 29 }, { tooth: 14 }]);
    expect(next.sites[2]).toEqual({ tooth: 14, variantId: null, reviewed: false });
  });

  it("drops the variant AND the review when the row is put back on “auto”", () => {
    // THE BYPASS (verifier, 2026-07-25): review site 29 as 6030, then return to step 3 and
    // set that row's picker to "auto" (value ""). The selection used to keep claiming a
    // REVIEWED 6030 while the run submitted NO declaration — the backend auto-identified a
    // part nobody reviewed and the acknowledgment read as satisfied. Un-declaring is a
    // selection change like any other.
    const next = withSites(readyState(), [
      { tooth: 3, declaredVariant: "6020" },
      { tooth: 29, declaredVariant: "" },
    ]);
    expect(next.sites[1]).toEqual({ tooth: 29, variantId: null, reviewed: false });
    expect(processBlockers(next)).toContain("the cap variant for site 2 (tooth 29)");
    expect(next.sites[0]?.reviewed).toBe(true); // the untouched row keeps its review
  });

  it("leaves the choice alone for a row that states no declaration at all", () => {
    // a caller that does not carry the field is SILENT about the declaration (contrast the
    // explicit "" above) — re-keying on tooth numbers must not wipe the dialog's work
    const next = withSites(readyState(), [{ tooth: 3 }, { tooth: 29 }]);
    expect(next.sites.map((s) => [s.variantId, s.reviewed])).toEqual([
      ["6020", true],
      ["6030", true],
    ]);
  });

  it("treats a variant changed OUTSIDE the dialog as a selection change (review cleared)", () => {
    const next = withSites(readyState(), [
      { tooth: 3, declaredVariant: "6030" },
      { tooth: 29, declaredVariant: "6030" },
    ]);
    expect(next.sites[0]).toEqual({ tooth: 3, variantId: "6030", reviewed: false });
    expect(next.sites[1]?.reviewed).toBe(true); // unchanged for that row
  });
});

describe("catalog shaping", () => {
  it("offers non-legacy groups as systems and refuses a legacy shelf with the reason", () => {
    const choices = systemChoices(GROUPS);
    expect(choices.map((c) => [c.model, c.selectable])).toEqual([
      ["neodent-gm", true],
      ["zimmer-4.5", true],
      ["vendor-legacy-library", false],
    ]);
    expect(choices[2]?.unavailableReason).toContain("not an implant system");
  });

  /* A legacy group's `model` is the raw name of a client-owned data folder (kept as the wire key
     that addresses its files). The LABEL is what the interface prints, and it is neutral. */
  it("labels a legacy shelf neutrally while keeping its folder name as the wire key", () => {
    const choices = systemChoices(GROUPS);
    expect(choices.map((c) => c.label)).toEqual(["neodent-gm", "zimmer-4.5", "Legacy shelf"]);
    expect(choices[2]?.model).toBe("vendor-legacy-library");
  });

  it("numbers several legacy shelves so their labels stay distinguishable", () => {
    const labels = catalogGroupLabels([
      { model: "neodent-gm", legacy: false },
      { model: "one-library", legacy: true },
      { model: "two-library", legacy: true },
    ]);
    expect(labels.get("neodent-gm")).toBe("neodent-gm");
    expect(labels.get("one-library")).toBe("Legacy shelf 1");
    expect(labels.get("two-library")).toBe("Legacy shelf 2");
  });

  it("splits superseded archives into their own dated group, current parts first", () => {
    const { current, archives } = partitionVariants(GROUPS[0]?.variants ?? []);
    expect(current.map((e) => e.id)).toEqual(["6020", "6030"]);
    expect(archives).toHaveLength(1);
    expect(archives[0]?.label).toBe("Superseded 2026-07-13");
    expect(archives[0]?.entries.map((e) => e.id)).toEqual(["superseded-2026-07-13--5020"]);
  });

  it("keeps two archive dates apart", () => {
    const older = makeEntry({
      id: "superseded-2025-01-02--4020",
      filename: "superseded-2025-01-02/neodent-gm-4020.stl",
      flags: ["superseded"],
    });
    const { archives } = partitionVariants([ARCHIVED, older, makeEntry()]);
    expect(archives.map((a) => a.label)).toEqual(["Superseded 2025-01-02", "Superseded 2026-07-13"]);
  });

  it("reads the same archive date as the library browser's own badge", () => {
    // one parse, two presentations — the group HEADING is Sentence case, the card BADGE lowercase
    expect(supersededArchiveLabel(ARCHIVED)?.toLowerCase()).toBe(supersededBadgeText(ARCHIVED));
    expect(supersededArchiveLabel(makeEntry())).toBeNull();
  });

  it("groups the construction parts by vendor", () => {
    const parts: ConstructionPart[] = [
      { vendor: "atlantis", filename: "zimmer-4.5-scanbody.stl", pathId: "atlantis/zimmer-4.5-scanbody.stl", label: "atlantis — zimmer-4.5-scanbody" },
      { vendor: "dess", filename: "neodent-gm-scanbody.stl", pathId: "dess/neodent-gm-scanbody.stl", label: "dess — neodent-gm-scanbody" },
      { vendor: "atlantis", filename: "other.stl", pathId: "atlantis/other.stl", label: "atlantis — other" },
    ];
    const grouped = groupConstructionsByVendor(parts);
    expect(grouped.map((g) => g.vendor)).toEqual(["atlantis", "dess"]);
    expect(grouped[0]?.parts.map((p) => p.filename)).toEqual(["zimmer-4.5-scanbody.stl", "other.stl"]);
  });

  it("resolves a chosen variant id back to its catalog entry, archived ids included", () => {
    expect(findVariantEntry(GROUPS, "neodent-gm", "superseded-2026-07-13--5020")).toBe(ARCHIVED);
    expect(findVariantEntry(GROUPS, "neodent-gm", "7030")).toBeNull(); // belongs to the other system
    expect(findVariantEntry(GROUPS, null, "6020")).toBeNull();
  });
});
