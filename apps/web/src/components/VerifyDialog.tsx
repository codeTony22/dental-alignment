import { useState, type ReactNode } from "react";
import type { LibraryCatalogEntry } from "../domain/types";
import type { LibrarySelection } from "../domain/librarySelection";
import {
  catalogGroupLabels,
  formatOffsetMm,
  processBlockers,
  canProcess,
  unreviewedSiteNumbers,
} from "../domain/librarySelection";
import { SelectionColumn, type SelectionColumnProps } from "./SelectionColumn";
import { InfoPanel } from "./InfoPanel";
import { SiteStepper } from "./SiteStepper";
import { VerifyPanels, type VerifyPanelId, type VerifyPanelSpec } from "./VerifyPanels";
import { ReliefClampNotice } from "./ReliefClampNotice";
import type { SiteReliefClamp } from "../domain/reliefClamp";

/**
 * THE ACKNOWLEDGMENT the operator signs, modelled on the client's own dialog (2026-07-25).
 * The sentence is load-bearing rather than decorative: the gate it describes ("only after all
 * sites have been reviewed") is exactly what `processBlockers` enforces.
 */
export const REVIEW_DISCLAIMER =
  "By clicking OK, I acknowledge that the library part selected matches the corresponding " +
  "scan data. The OK button will be enabled only after all sites have been reviewed.";

export interface VerifyDialogProps {
  readonly caseId: string;
  readonly doctor: string;
  readonly scanFilename: string | null;
  readonly selection: LibrarySelection;
  /** The catalog entry behind the ACTIVE site's chosen variant — the Information panel's subject. */
  readonly infoEntry: LibraryCatalogEntry | null;
  readonly selectionColumn: SelectionColumnProps;
  /**
   * What the LAST run actually applied where the requested relief was more than the part could
   * take. Rendered right above the acknowledgment, because this dialog is where the operator
   * signs off on "the library part selected matches the scan data", and signing that off without
   * being told the part was built to a reduced relief would make the acknowledgment untrue.
   */
  readonly clamps: readonly SiteReliefClamp[];
  readonly panels: readonly VerifyPanelSpec[];
  readonly linked: boolean;
  /** True while the run this dialog fired is in flight (Process stays down, panels keep showing). */
  readonly busy: boolean;
  readonly onToggleLayer: (panelId: VerifyPanelId, layerId: string) => void;
  readonly onChangeOpacity: (panelId: VerifyPanelId, layerId: string, opacity: number) => void;
  readonly onToggleLinked: () => void;
  readonly renderViewer?: (panelId: VerifyPanelId) => ReactNode;
  readonly onStepSite: (delta: number) => void;
  readonly onSelectSite: (index: number) => void;
  readonly onToggleReviewed: (index: number, reviewed: boolean) => void;
  readonly onProcess: () => void;
  readonly onClose: () => void;
}

/**
 * THE LIBRARY SELECTION & VERIFICATION DIALOG — the client's screenshot made real
 * (2026-07-25), and the gate their directive demands: "the lab chooses, the software never
 * guesses."
 *
 * The flow, left to right: the operator names the implant SYSTEM, the CAP VARIANT (the diameter)
 * for each marked site, and the CONSTRUCTION part, with the jaw and the gingival relief; the
 * Information panel states the chosen part's Ø × height from the library; the three panels put
 * the library part, the scanned cap and the deviation-coloured union in front of them; and only
 * once every site has been REVIEWED — and every required selection made — does Process light up.
 *
 * THE 3D IS THE PRODUCT (client, 2026-07-26). This dialog fills the viewport and gives every
 * pixel it can to the three panes: the selection column COLLAPSES to a rail, the Information
 * panel and the site stepper share one compact strip above the panels, each pane carries its own
 * maximise, and the acknowledgment is a footer BAR rather than the tall block that used to push
 * the panels down to thumbnails. Nothing was dropped to get there — the per-site review
 * checkboxes moved into the selection column, beside the sites they are about.
 *
 * This is the VERIFICATION ROUTE, not a replacement for the quick path: step 4's Run automation
 * still works with the same selection, which is why the state lives in App and this dialog is
 * presentational.
 */
export function VerifyDialog({
  caseId,
  doctor,
  scanFilename,
  selection,
  infoEntry,
  selectionColumn,
  clamps,
  panels,
  linked,
  busy,
  onToggleLayer,
  onChangeOpacity,
  onToggleLinked,
  renderViewer,
  onStepSite,
  onSelectSite,
  onToggleReviewed,
  onProcess,
  onClose,
}: VerifyDialogProps) {
  const blockers = processBlockers(selection);
  const ready = canProcess(selection);
  const unreviewed = unreviewedSiteNumbers(selection);
  const activeSite = selection.sites[selection.activeSiteIndex] ?? null;
  const reviewedCount = selection.sites.length - unreviewed.length;

  /** The selection column's own visibility. Open by default — the operator arrives here to
   *  CHOOSE — and collapsible the moment they want the panels wider. */
  const [columnOpen, setColumnOpen] = useState(true);
  /** Which single pane owns the stage, or null for all three (see VerifyPanels). */
  const [maximizedId, setMaximizedId] = useState<VerifyPanelId | null>(null);

  return (
    <div className="decode-dialog-backdrop">
      <section
        className="decode-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="decode-dialog-heading"
      >
        <header className="decode-dialog__header">
          <div className="decode-dialog__identity">
            <button
              type="button"
              className="button button--ghost button--small"
              aria-pressed={columnOpen}
              aria-controls="decode-selection-column"
              onClick={() => setColumnOpen((open) => !open)}
              title={
                columnOpen
                  ? "Collapse the selection lists and give the width to the 3D"
                  : "Show the selection lists again"
              }
            >
              {columnOpen ? "‹ hide selection" : "› selection"}
            </button>
            <div>
              <h2 id="decode-dialog-heading" className="decode-dialog__title">
                Library selection &amp; verification
              </h2>
              <p className="decode-dialog__subject">
                {caseId} · {doctor}
                {scanFilename ? ` · ${scanFilename}` : ""}
              </p>
            </div>
          </div>
          <div className="decode-dialog__header-right">
            <span
              className={`decode-dialog__progress${
                selection.sites.length > 0 && unreviewed.length === 0
                  ? " decode-dialog__progress--complete"
                  : ""
              }`}
              role="status"
            >
              {reviewedCount} of {selection.sites.length} site
              {selection.sites.length === 1 ? "" : "s"} reviewed
            </span>
            <button
              type="button"
              className="button button--ghost button--small"
              onClick={onClose}
              title="Close without processing (Esc)"
            >
              ✕ close
            </button>
          </div>
        </header>

        <div
          className={`decode-dialog__body${
            columnOpen ? "" : " decode-dialog__body--column-collapsed"
          }`}
        >
          {columnOpen && (
            <div className="decode-dialog__column" id="decode-selection-column">
              <SelectionColumn {...selectionColumn} />

              {/* THE PER-SITE ACKNOWLEDGMENT, beside the sites it is about. It used to sit in a
                  tall block under the panels, which is what squeezed them; here it is next to
                  the very list whose variant each checkbox is confirming. */}
              <section className="decode-ack__sites-block" aria-labelledby="decode-ack-sites">
                <h3 id="decode-ack-sites" className="decode-section__title">
                  Reviewed
                </h3>
                <ul className="decode-ack__sites">
                  {selection.sites.map((site, index) => (
                    <li key={site.tooth}>
                      <label className="decode-ack__check">
                        <input
                          type="checkbox"
                          checked={site.reviewed}
                          disabled={site.variantId === null}
                          onChange={(e) => onToggleReviewed(index, e.target.checked)}
                        />
                        <span>
                          Site {index + 1} — tooth {site.tooth}
                          {site.variantId ? ` · ${site.variantId}` : " · no cap chosen"} reviewed
                        </span>
                      </label>
                    </li>
                  ))}
                </ul>
                {selection.sites.length > 0 && unreviewed.length === 0 && (
                  <p className="decode-ack__complete" role="status">
                    All {selection.sites.length} site
                    {selection.sites.length > 1 ? "s have" : " has"} been reviewed.
                  </p>
                )}
              </section>
            </div>
          )}

          <div className="decode-dialog__main">
            <div className="decode-dialog__top">
              <InfoPanel
                entry={infoEntry}
                model={selection.model}
                tooth={activeSite?.tooth ?? null}
                labels={catalogGroupLabels(selectionColumn.groups)}
              />
              <SiteStepper
                sites={selection.sites}
                activeIndex={selection.activeSiteIndex}
                onStep={onStepSite}
                onSelect={onSelectSite}
              />
            </div>

            <VerifyPanels
              panels={panels}
              onToggleLayer={onToggleLayer}
              onChangeOpacity={onChangeOpacity}
              linked={linked}
              onToggleLinked={onToggleLinked}
              maximizedId={maximizedId}
              onToggleMaximized={(id) => setMaximizedId((current) => (current === id ? null : id))}
              renderViewer={renderViewer}
            />
          </div>
        </div>

        {/* THE ACKNOWLEDGMENT BAR — ONE ROW (client, 2026-07-26: "Cancel and OK · Process are
            colliding"). The text column and the buttons are separate flex children with the
            buttons pinned at `flex: 0 0 auto`, so no amount of wording can ever push into them;
            the text side ellipsises instead, with the full sentence in the title. The clamp rides
            here in its COMPACT tone for the same reason it always did — a part built at a reduced
            relief is not the part the selection above describes unless the operator has been told
            — but its "why" line, which is stated in full on the results block, no longer costs
            this bar two extra lines of height that the 3D panes were paying for. */}
        <footer className="decode-ack" aria-labelledby="decode-ack-heading">
          <h3 id="decode-ack-heading" className="sr-only">
            Acknowledgment
          </h3>
          <div className="decode-ack__text">
            <ReliefClampNotice clamps={clamps} tone="compact" />
            <p className="decode-ack__disclaimer" title={REVIEW_DISCLAIMER}>
              {REVIEW_DISCLAIMER}
            </p>
            <p className="decode-ack__summary">
              Will process as: <strong>{selection.model ?? "— no implant system —"}</strong> ·{" "}
              <strong>{selection.constructionPathId ?? "— no construction part —"}</strong> ·{" "}
              {selection.jaw} jaw · {formatOffsetMm(selection.gingivalOffsetMm)} mm gingival relief
            </p>
            {!ready && blockers.length > 0 && (
              <p className="decode-ack__blockers" role="alert">
                Still needed: {blockers.join("; ")}.
              </p>
            )}
          </div>
          <div className="decode-ack__actions">
            <button type="button" className="button button--secondary" onClick={onClose}>
              Cancel
            </button>
            <button
              type="button"
              className="button button--primary"
              disabled={!ready || busy}
              onClick={onProcess}
              title={
                ready
                  ? "Process this case with the selection above"
                  : "Every selection must be made and every site reviewed first"
              }
            >
              {busy ? "Processing…" : "OK · Process"}
            </button>
          </div>
        </footer>
      </section>
    </div>
  );
}
