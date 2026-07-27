/**
 * The VERIFY stage's panel in the work column. After the one-flow collapse (client, 2026-07-26)
 * the separate Library-selection stage is gone, so this summary lives on Verify ALONE: it
 * states the choice made in step 2, counts the acknowledgment, and names the door to the ONE
 * editor+review dialog. It is a summary and a door, never a second editor.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { SelectionSummary } from "./SelectionSummary";
import { initialSelection, withReviewed, withVariant } from "../domain/librarySelection";
import type { LibrarySelection } from "../domain/librarySelection";

function empty(): LibrarySelection {
  return initialSelection({
    suggestedModel: null,
    suggestedConstruction: null,
    jaw: "lower",
    sites: [{ tooth: 3 }, { tooth: 29 }],
  });
}

function chosen(): LibrarySelection {
  let selection = initialSelection({
    suggestedModel: "neodent-gm",
    suggestedConstruction: "dess/neodent-gm-scanbody.stl",
    jaw: "lower",
    sites: [{ tooth: 3 }, { tooth: 29 }],
  });
  selection = withVariant(selection, 0, "6020");
  selection = withVariant(selection, 1, "6030");
  return withReviewed(selection, 0, true);
}

describe("SelectionSummary", () => {
  it("carries the collapsed flow's numbering — Verify is step 3, and no Library-selection stage exists", () => {
    const html = renderToStaticMarkup(
      <SelectionSummary selection={chosen()} open={false} onOpen={() => undefined} />,
    );
    expect(html).toContain("Step 3 · Verify");
    expect(html).not.toContain("Library selection");
  });

  it("says 'not chosen' rather than leaving a blank where a choice belongs", () => {
    const html = renderToStaticMarkup(
      <SelectionSummary selection={empty()} open={false} onOpen={() => undefined} />,
    );
    expect(html.split("not chosen").length - 1).toBe(2); // system + construction
    expect(html.split("no cap chosen").length - 1).toBe(2); // both sites
  });

  it("states the chosen system, construction, jaw, relief and per-site cap", () => {
    const html = renderToStaticMarkup(
      <SelectionSummary selection={chosen()} open={false} onOpen={() => undefined} />,
    );
    expect(html).toContain("neodent-gm");
    expect(html).toContain("dess/neodent-gm-scanbody.stl");
    expect(html).toContain("lower");
    expect(html).toContain("0.20 mm");
    expect(html).toContain("tooth 3");
    expect(html).toContain("6020");
    expect(html).toContain("6030");
  });

  it("names what is still needed, in the run gate's own words", () => {
    const html = renderToStaticMarkup(
      <SelectionSummary selection={empty()} open={false} onOpen={() => undefined} />,
    );
    expect(html).toContain("Still needed:");
    expect(html).toContain("the implant system");
    expect(html).toContain("the construction part");
  });

  it("counts the acknowledgment, which is what the verify stage is for", () => {
    const html = renderToStaticMarkup(
      <SelectionSummary selection={chosen()} open={false} onOpen={() => undefined} />,
    );
    expect(html).toContain("1 of 2 sites reviewed");
  });

  it("opens the ONE review dialog — and says so differently when it is already open", () => {
    const shut = renderToStaticMarkup(
      <SelectionSummary selection={chosen()} open={false} onOpen={() => undefined} />,
    );
    const openNow = renderToStaticMarkup(
      <SelectionSummary selection={chosen()} open onOpen={() => undefined} />,
    );
    expect(shut).toContain("Open selection &amp; verification");
    expect(openNow).toContain("Back to selection &amp; verification");
  });
});
