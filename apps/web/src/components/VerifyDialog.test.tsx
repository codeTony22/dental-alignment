/**
 * THE ACKNOWLEDGMENT GATE (client's library-selection dialog, 2026-07-25). The single most
 * important behaviour in this dialog: Process is DISABLED until every required selection is made
 * AND every site has been reviewed — the client's own disclaimer says so, verbatim,
 * and it is quoted here so a reworded copy edit breaks the test rather than the promise.
 *
 * (renderToStaticMarkup, node environment: the 3D panes are injected by the stage and absent.)
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { REVIEW_DISCLAIMER, VerifyDialog, type VerifyDialogProps } from "./VerifyDialog";
import { initialSelection, withReviewed, withVariant } from "../domain/librarySelection";
import type { LibrarySelection } from "../domain/librarySelection";
import type { LibraryCatalogEntry, LibraryCatalogGroup } from "../domain/types";

const ENTRY: LibraryCatalogEntry = {
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
};

const GROUPS: LibraryCatalogGroup[] = [{ model: "neodent-gm", legacy: false, variants: [ENTRY] }];

function baseSelection(): LibrarySelection {
  return initialSelection({
    suggestedModel: "neodent-gm",
    suggestedConstruction: "dess/neodent-gm-scanbody.stl",
    jaw: "lower",
    sites: [{ tooth: 3 }, { tooth: 29 }],
  });
}

function props(selection: LibrarySelection, overrides: Partial<VerifyDialogProps> = {}): VerifyDialogProps {
  return {
    caseId: "neodent-gm",
    doctor: "Doctor Neodent GM",
    scanFilename: "upper_jaw.stl",
    selection,
    infoEntry: ENTRY,
    selectionColumn: {
      selection,
      activeSiteNumber: 1,
      activeTooth: 3,
      libraryState: "ready",
      libraryError: null,
      groups: GROUPS,
      constructionsState: "ready",
      constructionsError: null,
      constructions: [],
      suggestedModel: "neodent-gm",
      suggestedConstruction: "dess/neodent-gm-scanbody.stl",
      onSelectModel: () => {},
      onSelectVariant: () => {},
      onSelectConstruction: () => {},
      onSelectJaw: () => {},
      onChangeOffset: () => {},
      achievedOffset: null,
      ceiling: { kind: "idle" },
      clamps: [],
      onRetry: () => {},
    },
    clamps: [],
    panels: [],
    linked: false,
    busy: false,
    onToggleLayer: () => {},
    onChangeOpacity: () => {},
    onToggleLinked: () => {},
    onStepSite: () => {},
    onSelectSite: () => {},
    onToggleReviewed: () => {},
    onProcess: () => {},
    onClose: () => {},
    ...overrides,
  };
}

/** Everything chosen and every detection reviewed — the only state Process allows. */
function readySelection(): LibrarySelection {
  let selection = withVariant(baseSelection(), 0, "6020");
  selection = withVariant(selection, 1, "6020");
  selection = withReviewed(selection, 0, true);
  return withReviewed(selection, 1, true);
}

function processButton(html: string): string {
  const match = html.match(/<button[^>]*>(?:Processing…|OK · Process)<\/button>/);
  return match?.[0] ?? "";
}

describe("VerifyDialog", () => {
  it("is a modal dialog naming the case, the doctor and the scan file", () => {
    const html = renderToStaticMarkup(<VerifyDialog {...props(baseSelection())} />);
    expect(html).toContain('role="dialog"');
    expect(html).toContain('aria-modal="true"');
    expect(html).toContain("neodent-gm");
    expect(html).toContain("Doctor Neodent GM");
    expect(html).toContain("upper_jaw.stl");
  });

  it("quotes the client's disclaimer verbatim", () => {
    const html = renderToStaticMarkup(<VerifyDialog {...props(baseSelection())} />);
    expect(REVIEW_DISCLAIMER).toBe(
      "By clicking OK, I acknowledge that the library part selected matches the corresponding " +
        "scan data. The OK button will be enabled only after all sites have been reviewed.",
    );
    expect(html).toContain("all sites have been reviewed");
  });

  it("offers one reviewed checkbox per site, unticked and named by tooth", () => {
    const html = renderToStaticMarkup(<VerifyDialog {...props(baseSelection())} />);
    expect(html.match(/type="checkbox"/g)?.length).toBe(2);
    expect(html).toContain("Site 1 — tooth 3");
    expect(html).toContain("Site 2 — tooth 29");
    expect(html).not.toMatch(/type="checkbox"[^>]*checked/);
  });

  it("ticks the box for a site that HAS been reviewed", () => {
    const html = renderToStaticMarkup(<VerifyDialog {...props(readySelection())} />);
    expect(html.match(/type="checkbox"[^>]*checked/g)?.length).toBe(2);
  });

  it("cannot be reviewed before a cap is chosen for that site", () => {
    const html = renderToStaticMarkup(<VerifyDialog {...props(baseSelection())} />);
    expect(html).toMatch(/type="checkbox"[^>]*disabled/);
    expect(html).toContain("no cap chosen");
  });

  it("DISABLES Process until every selection is made and every detection reviewed", () => {
    const missingReview = withReviewed(readySelection(), 1, false);
    expect(processButton(renderToStaticMarkup(<VerifyDialog {...props(baseSelection())} />))).toContain(
      "disabled",
    );
    expect(processButton(renderToStaticMarkup(<VerifyDialog {...props(missingReview)} />))).toContain(
      "disabled",
    );
  });

  it("names what is still missing rather than a silent disabled button", () => {
    const html = renderToStaticMarkup(<VerifyDialog {...props(baseSelection())} />);
    expect(html).toContain("Still needed:");
    expect(html).toContain("the cap variant for site 1 (tooth 3)");
    expect(html).toContain("a review of sites 1, 2");
  });

  it("ENABLES Process once everything is chosen and reviewed", () => {
    const html = renderToStaticMarkup(<VerifyDialog {...props(readySelection())} />);
    expect(processButton(html)).not.toContain("disabled");
    expect(html).toContain("All 2 sites have been reviewed.");
    expect(html).not.toContain("Still needed:");
  });

  it("keeps Process down while a run is in flight, even when the gate is satisfied", () => {
    const html = renderToStaticMarkup(<VerifyDialog {...props(readySelection(), { busy: true })} />);
    expect(processButton(html)).toContain("disabled");
    expect(html).toContain("Processing…");
  });

  it("states exactly what will be processed — the selection the operator is signing", () => {
    const html = renderToStaticMarkup(<VerifyDialog {...props(readySelection())} />);
    expect(html).toContain("neodent-gm");
    expect(html).toContain("dess/neodent-gm-scanbody.stl");
    expect(html).toContain("lower jaw");
    expect(html).toContain("0.20 mm gingival relief");
  });

  it("says so honestly when nothing has been selected at all", () => {
    const empty = initialSelection({
      suggestedModel: null,
      suggestedConstruction: null,
      jaw: "upper",
      sites: [{ tooth: 3 }],
    });
    const html = renderToStaticMarkup(
      <VerifyDialog {...props(empty, { infoEntry: null })} />,
    );
    expect(html).toContain("— no implant system —");
    expect(html).toContain("— no construction part —");
    expect(processButton(html)).toContain("disabled");
  });
});

/**
 * THE CLAMP, ABOVE THE SIGNATURE (client, 2026-07-25). What this dialog's checkbox asserts is
 * that "the library part selected matches the corresponding scan data" — so if the run had to
 * build the part at a REDUCED relief, the operator must be told before they sign it. The notice
 * is rendered immediately above the acknowledgment for exactly that reason.
 */
describe("VerifyDialog — the relief clamp", () => {
  it("shows both numbers above the acknowledgment when the last run clamped", () => {
    const html = renderToStaticMarkup(
      <VerifyDialog
        {...props(readySelection(), {
          clamps: [
            { tooth: 3, requestedMm: 0.2, appliedMm: 0.06, limitMm: 0.06, minWallMm: 0.5, reason: null },
          ],
        })}
      />,
    );
    expect(html).toContain("0.20 mm requested");
    expect(html).toContain("0.06 mm applied");
    expect(html).toContain("Tooth 3");
    // …and it precedes the acknowledgment it qualifies
    expect(html.indexOf("relief-clamp")).toBeLessThan(html.indexOf("decode-ack__disclaimer"));
  });

  it("shows nothing when the run applied the relief the lab asked for", () => {
    const html = renderToStaticMarkup(<VerifyDialog {...props(readySelection())} />);
    expect(html).not.toContain("relief-clamp");
    // the summary still states the REQUEST, unchanged
    expect(html).toContain("0.20 mm gingival relief");
  });
});

/**
 * THE 3D PANELS ARE THE PRODUCT (client, 2026-07-26): "in the verification view the three STL
 * panels are currently small thumbnails in a crowded dialog … the selection lists are secondary."
 *
 * The dialog now fills the viewport and gives its width and height to the panes: the selection
 * column COLLAPSES, the per-site review checkboxes moved into it (they are about the sites the
 * column lists), and the acknowledgment is a footer BAR rather than the tall block that used to
 * push the panels down. What must NOT change is the gate itself — the block above still pins it.
 */
describe("VerifyDialog — the 3D gets the room", () => {
  it("can collapse the selection lists to give their width to the panels", () => {
    const open = renderToStaticMarkup(<VerifyDialog {...props(baseSelection())} />);
    expect(open).toContain("‹ hide selection");
    expect(open).toContain('aria-controls="decode-selection-column"');
    expect(open).toContain('id="decode-selection-column"');
    // open by default: the operator arrives here to CHOOSE
    expect(open).toContain('aria-pressed="true"');
  });

  it("keeps the per-site review beside the sites it is about, not under the panels", () => {
    const html = renderToStaticMarkup(<VerifyDialog {...props(baseSelection())} />);
    expect(html.match(/type="checkbox"/g)?.length).toBe(2);
    // …inside the collapsible column, ahead of the panels' own region
    expect(html.indexOf('id="decode-selection-column"')).toBeLessThan(html.indexOf("Site 1 — tooth 3"));
    expect(html.indexOf("Site 1 — tooth 3")).toBeLessThan(html.indexOf("verify-panels"));
  });

  it("puts the acknowledgment in a footer bar AFTER the panels, never above them", () => {
    const html = renderToStaticMarkup(<VerifyDialog {...props(readySelection())} />);
    expect(html.indexOf("verify-panels")).toBeLessThan(html.indexOf("decode-ack__disclaimer"));
    expect(html).toContain("<footer");
  });

  it("carries the review progress in the header, where it is never scrolled away from", () => {
    const none = renderToStaticMarkup(<VerifyDialog {...props(baseSelection())} />);
    const all = renderToStaticMarkup(<VerifyDialog {...props(readySelection())} />);
    expect(none).toContain("0 of 2 sites reviewed");
    expect(all).toContain("2 of 2 sites reviewed");
    expect(all).toContain("decode-dialog__progress--complete");
  });
});
