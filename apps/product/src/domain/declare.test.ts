/**
 * DECLARE'S DISPLAY RULES (plan §4 Declare / AM-8, slice 5a), pinned framework-free:
 * which system cards render (non-legacy groups; the effective one attributed to the
 * server's `source`, never a local comparison), how variant cards split current from
 * superseded, the dims line, the visible-reset confirmation WORDS with the count in
 * them, and the active-site defaulting the queue and stage share.
 */
import { describe, expect, it } from "vitest";
import {
  caseSessionDetail,
  catalogEntry,
  catalogGroup,
  siteView,
} from "../testing/fixtures";
import {
  activeSiteFrom,
  declaredLabel,
  dimsLabel,
  resetCount,
  switchWords,
  systemCards,
  variantShelves,
} from "./declare";

const twoSystems = caseSessionDetail({
  catalog: {
    groups: [
      catalogGroup("conical-4x4"),
      catalogGroup("astra-ev", [catalogEntry({ id: "3010", variant: "3010" })]),
      catalogGroup("old-parts-library", [catalogEntry({ id: "4040" })], true),
    ],
    constructions: [],
  },
});

describe("systemCards", () => {
  it("lists non-legacy groups only — a legacy shelf is not a declarable system", () => {
    expect(systemCards(twoSystems).map((c) => c.model)).toEqual([
      "conical-4x4",
      "astra-ev",
    ]);
  });

  it("attributes the effective card from the server's source, with the suggested tag", () => {
    const cards = systemCards(twoSystems);
    expect(cards[0]).toMatchObject({
      model: "conical-4x4",
      effective: true,
      suggested: true, // system.source === "suggested" — the server said WHICH
    });
    expect(cards[1]).toMatchObject({ effective: false, suggested: false });
  });

  it("a declared system carries no suggested tag — it is the operator's act", () => {
    const declared = caseSessionDetail({
      ...twoSystems,
      system: { effective_model: "astra-ev", source: "declared" },
    });
    const cards = systemCards(declared);
    expect(cards.find((c) => c.model === "astra-ev")).toMatchObject({
      effective: true,
      suggested: false,
    });
  });

  it("drops a group whose model is not a string instead of rendering a lie", () => {
    const noisy = caseSessionDetail({
      catalog: { groups: [{ legacy: false }, catalogGroup()], constructions: [] },
    });
    expect(systemCards(noisy).map((c) => c.model)).toEqual(["conical-4x4"]);
  });
});

describe("variantShelves — the active system's cards", () => {
  const detail = caseSessionDetail({
    catalog: {
      groups: [
        catalogGroup("conical-4x4", [
          catalogEntry({ id: "5020", rim_diameter_mm: 5.0, height_mm: 2.0 }),
          catalogEntry({
            id: "superseded-2025-01-01--4010",
            variant: "4010",
            flags: ["superseded"],
            rim_diameter_mm: 4.0,
            height_mm: 1.0,
          }),
          { flags: [] }, // no id — undeclarable, dropped
        ]),
      ],
      constructions: [],
    },
  });

  it("splits current from superseded by the catalog's own flag", () => {
    const shelves = variantShelves(detail);
    expect(shelves.current.map((c) => c.id)).toEqual(["5020"]);
    expect(shelves.superseded.map((c) => c.id)).toEqual([
      "superseded-2025-01-01--4010",
    ]);
  });

  it("cards carry the catalog's Ø × height line", () => {
    const [card] = variantShelves(detail).current;
    expect(card?.dims).toBe("Ø 5.0 × 2.0 mm");
  });

  it("an effective system with no group yields empty shelves, never a throw", () => {
    const empty = caseSessionDetail({
      system: { effective_model: null, source: "none" },
    });
    expect(variantShelves(empty)).toEqual({ current: [], superseded: [] });
  });
});

describe("dimsLabel", () => {
  it("formats both numbers, and is honest when the catalog could not measure", () => {
    expect(dimsLabel(4.5, 3.1)).toBe("Ø 4.5 × 3.1 mm");
    expect(dimsLabel(null, 3.1)).toBe("dimensions unavailable");
    expect(dimsLabel(4.5, null)).toBe("dimensions unavailable");
  });
});

describe("the visible-reset confirmation (AM-8)", () => {
  it("counts sites that would lose their declaration", () => {
    const detail = caseSessionDetail({
      sites: [
        siteView({ tooth: 19, status: "declared", declared_variant: "5020" }),
        siteView({ tooth: 30 }),
        siteView({ tooth: 31, status: "declared", declared_variant: "6030" }),
      ],
    });
    expect(resetCount(detail)).toBe(2);
  });

  it("the words name the target system and the reset count", () => {
    const words = switchWords("astra-ev", 2);
    expect(words).toContain("astra-ev");
    expect(words).toContain("resets 2 declared sites");
  });

  it("one site reads singular — pedantry the operator will notice", () => {
    expect(switchWords("astra-ev", 1)).toContain("resets 1 declared site —");
  });
});

describe("activeSiteFrom — the queue and the stage share one active site", () => {
  const sites = [siteView({ tooth: 19 }), siteView({ tooth: 30 })];

  it("picks the clicked tooth", () => {
    expect(activeSiteFrom(sites, 30)?.tooth).toBe(30);
  });

  it("defaults to the first site when nothing was clicked yet", () => {
    expect(activeSiteFrom(sites, null)?.tooth).toBe(19);
  });

  it("a stale tooth (re-detected case) falls back to the first site", () => {
    expect(activeSiteFrom(sites, 42)?.tooth).toBe(19);
  });

  it("no sites at all is an honest null", () => {
    expect(activeSiteFrom([], null)).toBeNull();
  });
});

describe("declaredLabel", () => {
  it("names the declared variant, or an honest dash", () => {
    expect(declaredLabel(siteView({ declared_variant: "5020" }))).toBe("5020");
    expect(declaredLabel(siteView())).toBe("—");
  });
});
