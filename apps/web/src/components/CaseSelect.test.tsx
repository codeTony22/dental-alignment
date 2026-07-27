/**
 * The case list after the no-inference change (client directive 2026-07-25). A case's `vendor` is
 * DERIVED from the name-matched construction SUGGESTION, so it is nullable now — and it is a
 * suggestion, not a fact about the case.
 *
 * (renderToStaticMarkup, node environment — same convention as the other component suites.)
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { CaseSelect } from "./CaseSelect";
import type { Case } from "../domain/types";

function makeCase(over: Partial<Case> = {}): Case {
  return {
    id: "patient-4471",
    doctor: "Doctor Patient 4471",
    jaw: "upper",
    vendor: null,
    suggestedModel: null,
    suggestedConstruction: null,
    scanFilename: "upper_jaw.stl",
    scanUrl: "/api/cases/patient-4471/scan",
    suggestedSites: [],
    ...over,
  };
}

function markup(cases: readonly Case[]): string {
  return renderToStaticMarkup(
    <CaseSelect
      cases={cases}
      selectedCaseId={null}
      loadingCases={false}
      loadingScanProgress={null}
      onSelect={() => undefined}
    />,
  );
}

describe("CaseSelect", () => {
  it("lists a case whose folder name suggests no vendor, with no empty chip", () => {
    const html = markup([makeCase()]);
    expect(html).toContain("Doctor Patient 4471");
    // omitted, not rendered blank — an empty grey pill reads as a value that failed to load
    expect(html).not.toContain('class="chip"');
  });

  it("labels a name-matched vendor as a suggestion, never as the case's own fact", () => {
    const html = markup([makeCase({ id: "cap7030-zimmer-4.5", vendor: "atlantis" })]);
    expect(html).toContain("atlantis (suggested)");
  });
});
