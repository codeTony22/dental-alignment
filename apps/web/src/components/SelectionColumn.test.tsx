/**
 * Static-markup tests for the DECODING SELECTION COLUMN (renderToStaticMarkup — node
 * environment, no jsdom, per the repo convention). What is pinned: the superseded archives are a
 * SEPARATE, dated group with their badges (never mixed into the current shelf), the duplicate
 * finding is named, a legacy shelf is offered but disabled with its reason, the case's
 * suggestions are visibly badged as suggestions, the construction dropdown is grouped by vendor
 * and starts on an explicit prompt, and the offset input carries the client's default, step and
 * bounds — with the refusal sentence when the box holds a typo.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { SelectionColumn, type SelectionColumnProps } from "./SelectionColumn";
import { initialSelection, withOffsetInput, withVariant } from "../domain/librarySelection";
import type { ReliefLimit } from "../domain/reliefLimit";
import type { ConstructionPart, LibraryCatalogEntry, LibraryCatalogGroup } from "../domain/types";

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

const GROUPS: LibraryCatalogGroup[] = [
  {
    model: "neodent-gm",
    legacy: false,
    variants: [
      makeEntry({ flags: ["duplicate"], duplicateOf: ["zimmer-4.5/6020"] }),
      makeEntry({
        id: "superseded-2026-07-13--5020",
        variant: "5020",
        filename: "superseded-2026-07-13/neodent-gm-5020.stl",
        flags: ["superseded"],
      }),
      makeEntry({ id: "broken", variant: "broken", flags: ["unloadable"] }),
    ],
  },
  { model: "zimmer-4.5", legacy: false, variants: [makeEntry({ id: "7030", variant: "7030" })] },
  { model: "vendor-legacy-library", legacy: true, variants: [makeEntry({ id: "legacy_master" })] },
];

const CONSTRUCTIONS: ConstructionPart[] = [
  {
    vendor: "atlantis",
    filename: "zimmer-4.5-scanbody.stl",
    pathId: "atlantis/zimmer-4.5-scanbody.stl",
    label: "atlantis — zimmer-4.5-scanbody",
  },
  {
    vendor: "dess",
    filename: "neodent-gm-scanbody.stl",
    pathId: "dess/neodent-gm-scanbody.stl",
    label: "dess — neodent-gm-scanbody",
  },
];

function props(overrides: Partial<SelectionColumnProps> = {}): SelectionColumnProps {
  return {
    selection: initialSelection({
      suggestedModel: "neodent-gm",
      suggestedConstruction: "dess/neodent-gm-scanbody.stl",
      jaw: "lower",
      sites: [{ tooth: 29 }],
    }),
    activeSiteNumber: 1,
    activeTooth: 29,
    libraryState: "ready",
    libraryError: null,
    groups: GROUPS,
    constructionsState: "ready",
    constructionsError: null,
    constructions: CONSTRUCTIONS,
    suggestedModel: "neodent-gm",
    suggestedConstruction: "dess/neodent-gm-scanbody.stl",
    onSelectModel: () => {},
    onSelectVariant: () => {},
    onSelectConstruction: () => {},
    onSelectJaw: () => {},
    onChangeOffset: () => {},
    achievedOffset: null,
    // the ceiling read-out is off by default here — its own describe block turns it on
    ceiling: { kind: "idle" },
    clamps: [],
    onRetry: () => {},
    ...overrides,
  };
}

describe("SelectionColumn — implant system", () => {
  it("lists every system, badges the case's suggestion, and marks the selected one", () => {
    const html = renderToStaticMarkup(<SelectionColumn {...props()} />);
    expect(html).toContain("neodent-gm");
    expect(html).toContain("zimmer-4.5");
    expect(html).toContain("library-badge--suggested");
    expect(html).toContain('aria-pressed="true"');
  });

  it("offers a legacy shelf DISABLED with the reason instead of hiding it", () => {
    const html = renderToStaticMarkup(<SelectionColumn {...props()} />);
    expect(html).toContain("Legacy shelf");
    expect(html).toContain("not an implant system");
    expect(html).toContain("disabled");
  });

  /* The shelf's `model` is the raw name of a client-owned data folder: the wire key, never copy. */
  it("names the legacy shelf neutrally — its data-folder name is not rendered", () => {
    const html = renderToStaticMarkup(<SelectionColumn {...props()} />);
    expect(html).not.toContain("vendor-legacy-library");
  });

  it("shows the restart hint when the running API predates the endpoint", () => {
    const html = renderToStaticMarkup(
      <SelectionColumn {...props({ libraryState: "unavailable" })} />,
    );
    expect(html).toContain("not available on the running API");
    expect(html).toContain("make serve");
  });
});

describe("SelectionColumn — cap variants", () => {
  it("separates the superseded archive into its own dated group with the badge", () => {
    const html = renderToStaticMarkup(<SelectionColumn {...props()} />);
    expect(html).toContain("Superseded 2026-07-13");
    expect(html).toContain("library-badge--superseded");
    // the archived card is inside the archive block, after the current shelf
    expect(html.indexOf("decode-archive")).toBeGreaterThan(html.indexOf("decode-variant-list"));
  });

  it("names the byte-identical duplicate on the card", () => {
    const html = renderToStaticMarkup(<SelectionColumn {...props()} />);
    expect(html).toContain("identical file to zimmer-4.5 6020");
  });

  it("lists an unloadable part, disabled", () => {
    const html = renderToStaticMarkup(<SelectionColumn {...props()} />);
    expect(html).toContain("library-badge--unloadable");
  });

  it("marks the site's chosen variant as pressed", () => {
    const selection = withVariant(props().selection, 0, "superseded-2026-07-13--5020");
    const html = renderToStaticMarkup(<SelectionColumn {...props({ selection })} />);
    expect(html).toMatch(/decode-variant--selected/);
  });

  it("says which site it is choosing for", () => {
    const html = renderToStaticMarkup(<SelectionColumn {...props()} />);
    expect(html).toContain("site 1");
    expect(html).toContain("tooth 29");
  });

  it("asks for a system first when none is chosen", () => {
    const selection = initialSelection({
      suggestedModel: null,
      suggestedConstruction: null,
      jaw: "upper",
      sites: [{ tooth: 3 }],
    });
    const html = renderToStaticMarkup(
      <SelectionColumn {...props({ selection, suggestedModel: null, suggestedConstruction: null })} />,
    );
    expect(html).toContain("Choose an implant system first");
  });
});

describe("SelectionColumn — construction, jaw and relief", () => {
  it("groups the construction options by vendor, with an explicit prompt option", () => {
    const html = renderToStaticMarkup(<SelectionColumn {...props()} />);
    expect(html).toContain('optgroup label="atlantis"');
    expect(html).toContain('optgroup label="dess"');
    expect(html).toContain("— choose the construction part —");
    expect(html).toContain("neodent-gm-scanbody.stl (suggested)");
  });

  it("flags the dropdown as needing a choice when nothing is selected", () => {
    const selection = initialSelection({
      suggestedModel: "neodent-gm",
      suggestedConstruction: null,
      jaw: "upper",
      sites: [{ tooth: 3 }],
    });
    const html = renderToStaticMarkup(<SelectionColumn {...props({ selection })} />);
    expect(html).toContain("decode-select--needs");
    expect(html).toContain('aria-invalid="true"');
  });

  it("shows the jaw as a two-option radio group with the case's own jaw checked", () => {
    const html = renderToStaticMarkup(<SelectionColumn {...props()} />);
    expect(html).toContain('role="radiogroup"');
    // exactly one option is checked, and it is the LOWER one this case carries
    expect(html.match(/aria-checked="true"/g)).toHaveLength(1);
    expect(html).toMatch(/aria-checked="true"[^>]*>Lower</);
    expect(html).toMatch(/aria-checked="false"[^>]*>Upper</);
  });

  it("carries the client's offset default, step and bounds, plus the one-line explanation", () => {
    const html = renderToStaticMarkup(<SelectionColumn {...props()} />);
    expect(html).toContain('value="0.20"');
    expect(html).toContain('step="0.05"');
    expect(html).toContain('min="0"');
    expect(html).toContain('max="1"');
    expect(html).toContain("0.20 mm is the lab default");
  });

  it("shows the refusal sentence (and keeps the typed text) for an out-of-range relief", () => {
    const selection = withOffsetInput(props().selection, "2");
    const html = renderToStaticMarkup(<SelectionColumn {...props({ selection })} />);
    expect(html).toContain('value="2"');
    expect(html).toContain("between 0 and 1.00 mm");
    // "requested", not "applied": the box is a REQUEST — what the part achieves is measured
    // separately and printed beside it (see the offset-honesty tests below).
    expect(html).toContain("requested: 0.20 mm");
    expect(html).toContain("decode-offset__input--error");
  });

  /**
   * OFFSET HONESTY (measured 2026-07-25 — asking 0.20 mm achieves ~0.13-0.15 mm through the SDF
   * round trip). The request stays exactly as typed; the achievement is a separate, measured
   * read-out; and before any run has measured it the column SAYS SO rather than echoing the
   * request back as if it had been confirmed.
   */
  it("says the achieved clearance is not measured yet, before any run", () => {
    const html = renderToStaticMarkup(<SelectionColumn {...props()} />);
    expect(html).toContain("achieved clearance: not measured on this run yet");
    expect(html).not.toContain("mm achieved");
  });

  it("shows the MEASURED clearance beside the request once a run has one", () => {
    const html = renderToStaticMarkup(
      <SelectionColumn
        {...props({
          achievedOffset: {
            requestedMm: 0.2,
            medianMm: 0.14,
            minMm: 0.13,
            maxMm: 0.15,
            nSites: 3,
            method: "SDF round-trip re-measure",
          },
        })}
      />,
    );
    // both numbers, neither rewritten to agree with the other
    expect(html).toContain("requested: 0.20 mm");
    expect(html).toContain("0.14 mm achieved (median of 3 sites, 0.13–0.15)");
    expect(html).toContain("SDF round-trip re-measure");
    expect(html).toContain("The request is never silently rescaled to compensate.");
    expect(html).toContain('value="0.20"');
  });
});

/**
 * THE CEILING AT SELECTION TIME (client, 2026-07-25 — "end-to-end automation must complete").
 *
 * The bug this closes: the lab's 0.20 mm default ate the screw channel of an atlantis/neodent-gm
 * 5030 and the package was refused AFTER the whole pipeline ran. The ceiling is the same physics
 * measured up front, so what these tests hold is the ORDER of events: the operator learns the
 * maximum, and that they are over it, BEFORE Process — and the warning never becomes a blocker,
 * because the run is allowed to clamp and report.
 */
function ceilingLimit(overrides: Partial<ReliefLimit> = {}): ReliefLimit {
  return {
    constructionPathId: "atlantis/neodent-gm-scanbody.stl",
    model: "neodent-gm",
    variant: "5030",
    maxSafeMm: 0.06,
    limitedBy: "channel wall",
    minWallMm: 0.5,
    measured: true,
    note: null,
    ...overrides,
  };
}

describe("SelectionColumn — the relief ceiling, before processing", () => {
  it("states the maximum safe relief beside the input once the part and cap are chosen", () => {
    const html = renderToStaticMarkup(
      <SelectionColumn
        {...props({
          ceiling: {
            kind: "ready",
            binding: { maxSafeMm: 0.06, tooth: 29, limit: ceilingLimit() },
            pending: false,
          },
        })}
      />,
    );
    expect(html).toContain("max safe for this part: 0.06 mm (limited by channel wall)");
  });

  it("MARKS THE FIELD and says why when the typed relief is over the ceiling", () => {
    const html = renderToStaticMarkup(
      <SelectionColumn
        {...props({
          ceiling: {
            kind: "ready",
            binding: { maxSafeMm: 0.06, tooth: 29, limit: ceilingLimit() },
            pending: false,
          },
        })}
      />,
    );
    // the default 0.20 is over the 0.06 ceiling — the exact configuration the client was blocked on
    expect(html).toContain("decode-offset__input--over-ceiling");
    expect(html).toContain("0.20 mm is more than this construction part can take");
    expect(html).toContain("The run will clamp to 0.06 mm and report it");
    // a WARNING, not a blocker: the parse-error marking stays off, so Process stays live
    expect(html).not.toContain("decode-offset__input--error");
    expect(html).toContain('aria-invalid="false"');
  });

  it("says nothing about the ceiling when the typed relief fits under it", () => {
    const selection = withOffsetInput(props().selection, "0.05");
    const html = renderToStaticMarkup(
      <SelectionColumn
        {...props({
          selection,
          ceiling: {
            kind: "ready",
            binding: { maxSafeMm: 0.06, tooth: 29, limit: ceilingLimit() },
            pending: false,
          },
        })}
      />,
    );
    expect(html).toContain("max safe for this part: 0.06 mm");
    expect(html).not.toContain("decode-offset__input--over-ceiling");
    expect(html).not.toContain("more than this construction part can take");
  });

  it("degrades to the usual restart hint when the running API has no such endpoint", () => {
    const html = renderToStaticMarkup(
      <SelectionColumn {...props({ ceiling: { kind: "unavailable" } })} />,
    );
    expect(html).toContain("relief-limit endpoint is not available on the running API");
    expect(html).toContain("restart `make serve`");
    // and it reassures rather than alarms: the gate downstream is unaffected
    expect(html).toContain("The run still clamps to the safe maximum and reports it");
    // with nothing measured, nothing is claimed about the typed value
    expect(html).not.toContain("decode-offset__input--over-ceiling");
  });

  it("says 'not determined' rather than leaving a blank that would read as 'no limit'", () => {
    const html = renderToStaticMarkup(
      <SelectionColumn {...props({ ceiling: { kind: "undetermined" } })} />,
    );
    expect(html).toContain("max safe for this part: not determined");
  });

  it("warns that a shown ceiling may still tighten while another cap is being measured", () => {
    const html = renderToStaticMarkup(
      <SelectionColumn
        {...props({
          ceiling: {
            kind: "ready",
            binding: { maxSafeMm: 0.06, tooth: 29, limit: ceilingLimit() },
            pending: true,
          },
        })}
      />,
    );
    expect(html).toContain("this may tighten");
  });

  it("offers a retry when the lookup itself failed", () => {
    const html = renderToStaticMarkup(
      <SelectionColumn {...props({ ceiling: { kind: "error", message: "boom" } })} />,
    );
    expect(html).toContain("Could not measure the safe relief for this part: boom");
    expect(html).toContain("Retry");
  });

  it("shows the LAST run's clamp beside the input, both numbers", () => {
    const html = renderToStaticMarkup(
      <SelectionColumn
        {...props({
          clamps: [
            { tooth: 29, requestedMm: 0.2, appliedMm: 0.06, limitMm: 0.06, minWallMm: 0.5, reason: null },
          ],
        })}
      />,
    );
    expect(html).toContain("0.20 mm requested");
    expect(html).toContain("0.06 mm applied");
  });
});
