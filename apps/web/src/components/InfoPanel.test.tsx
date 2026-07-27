/**
 * The INFORMATION PANEL (the client's dialog shows Diameter and Height for the selected
 * library part). Pinned: the numbers come from the catalog and are never invented — an entry with no
 * measured dimension prints "—", not a plausible figure — the shipped file is named, and the
 * part's honest flags travel with it.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { InfoPanel } from "./InfoPanel";
import { catalogGroupLabels } from "../domain/librarySelection";
import type { LibraryCatalogEntry } from "../domain/types";

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

const LABELS = catalogGroupLabels([
  { model: "neodent-gm", legacy: false },
  { model: "zimmer-4.5", legacy: false },
  { model: "vendor-legacy-library", legacy: true },
]);

describe("InfoPanel", () => {
  it("states the library's diameter and height for the chosen part", () => {
    const html = renderToStaticMarkup(
      <InfoPanel entry={makeEntry()} model="neodent-gm" tooth={29} labels={LABELS} />,
    );
    expect(html).toContain("Diameter");
    expect(html).toContain("6.16 mm");
    expect(html).toContain("Height");
    expect(html).toContain("3.38 mm");
    expect(html).toContain("neodent-gm-6020.stl");
    expect(html).toContain("tooth 29");
  });

  it("prints an em dash for a dimension the catalog could not measure", () => {
    const html = renderToStaticMarkup(
      <InfoPanel entry={makeEntry({ rimDiameterMm: null, heightMm: null })} model="neodent-gm" tooth={3} labels={LABELS} />,
    );
    expect(html).toContain("—");
    expect(html).not.toContain("mm</dd>");
  });

  it("carries the part's flags — a superseded or duplicated part says so here too", () => {
    const html = renderToStaticMarkup(
      <InfoPanel
        entry={makeEntry({
          id: "superseded-2026-07-13--5020",
          variant: "5020",
          filename: "superseded-2026-07-13/neodent-gm-5020.stl",
          flags: ["superseded", "duplicate"],
          duplicateOf: ["zimmer-4.5/5020"],
        })}
        model="neodent-gm"
        tooth={3}
        labels={LABELS}
      />,
    );
    expect(html).toContain("superseded 2026-07-13");
    expect(html).toContain("identical file to zimmer-4.5 5020");
  });

  it("asks for a choice rather than showing blanks when nothing is selected", () => {
    const html = renderToStaticMarkup(<InfoPanel entry={null} model="neodent-gm" tooth={29} labels={LABELS} />);
    expect(html).toContain("No cap variant chosen for tooth 29");
    expect(html).not.toContain("Diameter");
  });
});
