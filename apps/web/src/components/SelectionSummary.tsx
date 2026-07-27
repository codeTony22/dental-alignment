import type { LibrarySelection } from "../domain/librarySelection";
import {
  formatOffsetMm,
  missingSelections,
  unreviewedSiteNumbers,
} from "../domain/librarySelection";

interface SelectionSummaryProps {
  readonly selection: LibrarySelection;
  /** True while the dialog is already open — the button then reads as a return, not a launch. */
  readonly open: boolean;
  readonly onOpen: () => void;
}

/**
 * THE VERIFY STAGE'S PANEL in the work column. After the one-flow collapse (client, 2026-07-26:
 * "ONE cohesive flow") the separate Library-selection stage is gone — the selection is made in
 * step 2, beside the marks — so this summary lives on Verify alone: it STATES what step 2 chose,
 * counts the acknowledgment, and names the door to the review dialog. The dialog stays the ONE
 * place the acknowledgment is signed, beside the three panels that judge it — one editor, one
 * authorization, one audit.
 */
export function SelectionSummary({ selection, open, onOpen }: SelectionSummaryProps) {
  const missing = missingSelections(selection);
  const unreviewed = unreviewedSiteNumbers(selection);
  const reviewed = selection.sites.length - unreviewed.length;

  return (
    <section className="panel selection-summary" aria-labelledby="selection-summary-heading">
      <h2 id="selection-summary-heading" className="panel__title">
        Step 3 · Verify
      </h2>
      <p className="panel__copy">
        Compare the library part, the scanned cap and the deviation-coloured union — then
        acknowledge each site.
      </p>

      <dl className="selection-summary__list">
        <div className="selection-summary__row">
          <dt>Implant system</dt>
          <dd>{selection.model ?? <span className="selection-summary__missing">not chosen</span>}</dd>
        </div>
        <div className="selection-summary__row">
          <dt>Construction part</dt>
          <dd>
            {selection.constructionPathId ?? (
              <span className="selection-summary__missing">not chosen</span>
            )}
          </dd>
        </div>
        <div className="selection-summary__row">
          <dt>Jaw · relief</dt>
          <dd>
            {selection.jaw} · {formatOffsetMm(selection.gingivalOffsetMm)} mm
          </dd>
        </div>
        <div className="selection-summary__row">
          <dt>Caps</dt>
          <dd>
            {selection.sites.length === 0 ? (
              <span className="selection-summary__missing">no marked site</span>
            ) : (
              <ul className="selection-summary__sites">
                {selection.sites.map((site) => (
                  <li key={site.tooth}>
                    tooth {site.tooth} —{" "}
                    {site.variantId ?? (
                      <span className="selection-summary__missing">no cap chosen</span>
                    )}
                    {site.reviewed ? " ✓" : ""}
                  </li>
                ))}
              </ul>
            )}
          </dd>
        </div>
      </dl>

      <p className="selection-summary__review" role="status">
        {reviewed} of {selection.sites.length} site{selection.sites.length === 1 ? "" : "s"} reviewed
      </p>

      {missing.length > 0 && (
        <p className="panel__hint selection-summary__missing-line">
          Still needed: {missing.join("; ")}.
        </p>
      )}

      <div className="panel__actions">
        <button type="button" className="button button--primary" onClick={onOpen}>
          {open ? "Back to selection & verification" : "Open selection & verification"}
        </button>
      </div>
    </section>
  );
}
