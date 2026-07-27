import type { CaptureAssessment, ConfirmedSite, LibraryVariant } from "../domain/types";
import { findDuplicateTeeth, hasEnoughRimPoints, RECOMMENDED_MIN_RIM_POINTS } from "../domain/types";
import type { MarkKind } from "../viewer/sceneController";
import { CaptureBanner, CaptureChip } from "./CaptureChip";
import { formatVariantDims } from "./PartPreviewChip";

const AUTO_OPTION_VALUE = "";

function libraryOptionLabel(v: LibraryVariant): string {
  const dims =
    v.rimDiameterMm !== null && v.heightMm !== null
      ? ` — Ø${v.rimDiameterMm} × ${v.heightMm} mm`
      : "";
  return `${v.variant}${dims}`;
}

/** The unselected option's label: declaration is REQUIRED (measured 2026-07-15: auto-ID is
 *  only 1/4 correct on the labeled arches vs 4/4 when the doctor declares), so this reads as a
 *  PROMPT, not a neutral "auto" default. Once a run has produced a measurement for this tooth,
 *  the automation's reading is surfaced as a hint the doctor confirms against — "declare
 *  (rim measures ≈ 6020)" — without making the empty value itself a valid declaration. */
function autoOptionLabel(suggestedVariant: string | undefined): string {
  return suggestedVariant
    ? `— declare cap variant (rim measures ≈ ${suggestedVariant}) —`
    : `— declare cap variant —`;
}

/** Which site row + which mark kind is currently armed for a single-shot click, if any. */
export interface MarkModeState {
  readonly rowIndex: number;
  readonly kind: MarkKind;
}

interface ConfirmPanelProps {
  readonly sites: readonly ConfirmedSite[];
  /** Per-row capture-gate verdict, index-aligned with `sites` (null = no assessment
   *  near that row's centre yet — e.g. detection hasn't run). Advisory chips + a
   *  prominent rescan banner BEFORE the operator invests marks (master plan §1 SCAN). */
  readonly captures: ReadonlyArray<CaptureAssessment | null>;
  readonly disabled: boolean;
  readonly brushingIndex: number | null;
  readonly markMode: MarkModeState | null;
  /** Which row is currently collecting multi-click rim-border points, if any. */
  readonly rimPointsIndex: number | null;
  /** The model's healing-cap catalog for the active case; empty while loading or if fetch failed. */
  readonly library: readonly LibraryVariant[];
  readonly libraryLoading: boolean;
  /** tooth -> the latest run's identified variant for that tooth, if a run result exists — drives
   *  the "auto — suggested: X" hint on the auto option (see autoOptionLabel). Empty before any run. */
  readonly identifiedVariantByTooth: ReadonlyMap<number, string>;
  /**
   * The tooth whose declared variant the DOCKED COMPARE PANE is currently showing, or null when
   * the pane is collapsed/empty. Replaces the retired partPreviewIndex (client, 2026-07-26): the
   * old "view part" SWAPPED the part into the main stage; the compare pane sits BESIDE the scan,
   * so the row control is a pointer at that pane, never a takeover of the stage.
   */
  readonly compareTooth: number | null;
  readonly onChangeTooth: (index: number, tooth: number) => void;
  readonly onChangeDeclaredVariant: (index: number, declaredVariant: string) => void;
  /** Point the docked compare pane at row `index`'s declared variant (App moves the active-site
   *  cursor there and opens the pane). */
  readonly onCompare: (index: number) => void;
  /** Clicking anywhere in a row moves the shared active-site cursor to that row's tooth — the
   *  same cursor the tooth chart and the verify dialog's stepper write (client, 2026-07-26: the
   *  variant cards declare for the ACTIVE site, so the table must be able to set it too). */
  readonly onSelectSite: (tooth: number) => void;
  readonly onStartBrush: (index: number) => void;
  readonly onFinishBrush: () => void;
  readonly onClearBrushStroke: () => void;
  readonly onClearMarkedPoints: (index: number) => void;
  readonly onStartMark: (index: number, kind: MarkKind) => void;
  readonly onCancelMark: () => void;
  readonly onClearMark: (index: number, kind: MarkKind) => void;
  readonly onStartRimPoints: (index: number) => void;
  readonly onFinishRimPoints: () => void;
  readonly onCancelRimPoints: () => void;
  /** Clears BOTH rimPoints and the legacy rimMark for a row (whichever the row currently has). */
  readonly onClearRim: (index: number) => void;
  readonly onConfirmAll: () => void;
  /** Why the variant list is empty, when it is — e.g. no implant system chosen yet. The picker
   *  states the reason instead of silently offering nothing. */
  readonly noSystemHint?: string | null;
}

export function ConfirmPanel({
  sites,
  captures,
  disabled,
  brushingIndex,
  markMode,
  rimPointsIndex,
  library,
  libraryLoading,
  identifiedVariantByTooth,
  compareTooth,
  onChangeTooth,
  onChangeDeclaredVariant,
  onCompare,
  onSelectSite,
  onStartBrush,
  onFinishBrush,
  onClearBrushStroke,
  onClearMarkedPoints,
  onStartMark,
  onCancelMark,
  onClearMark,
  onStartRimPoints,
  onFinishRimPoints,
  onCancelRimPoints,
  onClearRim,
  onConfirmAll,
  noSystemHint,
}: ConfirmPanelProps) {
  const duplicateTeeth = findDuplicateTeeth(sites);
  const hasDuplicateTeeth = duplicateTeeth.length > 0;

  return (
    <section className="panel" aria-labelledby="step2-confirm-heading">
      <h2 id="step2-confirm-heading" className="panel__title">
        Step 2 · Mark &amp; declare
      </h2>
      <p className="panel__copy">
        The operator confirms each site — the clinical safety gate. Declare the placed
        healing-cap variant from the model&apos;s library (required; the automation
        independently cross-checks it and flags disagreement). Optionally paint the
        healing-cap area on the model, mark the cap&apos;s top centre, or click several
        points around its visible border to find its width, to guide exactly where
        alignment should seed from.
      </p>

      {/* A rescan-grade capture on a to-be-confirmed site shows BEFORE marks are
          invested — the chair-side moment the coded-cap industry gates on. */}
      <CaptureBanner
        items={sites.flatMap((site, i) =>
          captures[i] ? [{ label: `Tooth ${site.tooth}`, capture: captures[i] }] : [],
        )}
      />

      <table className="confirm-table">
        <thead>
          <tr>
            <th scope="col">Tooth</th>
            <th scope="col">Capture</th>
            <th scope="col">Cap variant</th>
            <th scope="col">Healing-cap patch</th>
            <th scope="col">Registration marks</th>
            <th scope="col">
              <span className="sr-only">Confirmed</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {sites.map((site, index) => {
            const isBrushingThisRow = brushingIndex === index;
            const isBrushingOtherRow = brushingIndex !== null && brushingIndex !== index;
            const isMarkingThisRow = markMode !== null && markMode.rowIndex === index;
            const isMarkingOtherRow = markMode !== null && markMode.rowIndex !== index;
            const isCollectingRimThisRow = rimPointsIndex === index;
            const isCollectingRimOtherRow = rimPointsIndex !== null && rimPointsIndex !== index;
            const isBusyElsewhere = isBrushingOtherRow || isMarkingOtherRow || isCollectingRimOtherRow;
            const patchCount = site.markedPoints?.length ?? 0;
            const rimPointCount = site.rimPoints?.length ?? 0;
            const selectedValue = site.declaredVariant ?? AUTO_OPTION_VALUE;
            const selectedLibraryEntry = library.find((v) => v.variant === selectedValue) ?? null;
            const isDuplicateTooth = duplicateTeeth.includes(site.tooth);
            const suggestedVariant = identifiedVariantByTooth.get(site.tooth);
            const isComparingThisRow = compareTooth !== null && compareTooth === site.tooth;
            const selectedDims = selectedLibraryEntry
              ? formatVariantDims(selectedLibraryEntry.rimDiameterMm, selectedLibraryEntry.heightMm)
              : null;
            const hasDeclaration = selectedValue !== AUTO_OPTION_VALUE;
            return (
              // Any click in the row moves the shared site cursor — the compare pane, the
              // variant cards and the tooth chart all follow it (client, 2026-07-26).
              <tr key={index} onClick={() => onSelectSite(site.tooth)}>
                <td>
                  <label className="sr-only" htmlFor={`tooth-${index}`}>
                    Tooth number for site {index + 1}
                  </label>
                  <input
                    id={`tooth-${index}`}
                    type="number"
                    className={`confirm-table__input confirm-table__input--tooth${isDuplicateTooth ? " confirm-table__input--error" : ""}`}
                    aria-invalid={isDuplicateTooth}
                    value={site.tooth}
                    onChange={(e) => onChangeTooth(index, Number(e.target.value))}
                  />
                </td>
                <td>
                  {/* Scan-quality verdict for this site (advisory intake gate); "—"
                      until a detection pass has assessed a nearby centre. */}
                  {captures[index] ? (
                    <CaptureChip capture={captures[index]} />
                  ) : (
                    <span className="confirm-table__capture-none" aria-hidden="true">
                      —
                    </span>
                  )}
                </td>
                <td>
                  <label className="sr-only" htmlFor={`variant-${index}`}>
                    Cap variant for tooth {site.tooth}
                  </label>
                  <div className="confirm-table__variant-cell">
                    <select
                      id={`variant-${index}`}
                      className={`confirm-table__input confirm-table__input--variant${
                        selectedValue === AUTO_OPTION_VALUE ? " confirm-table__input--needs-declare" : ""
                      }`}
                      value={selectedValue}
                      disabled={libraryLoading}
                      aria-invalid={selectedValue === AUTO_OPTION_VALUE}
                      onChange={(e) => onChangeDeclaredVariant(index, e.target.value)}
                    >
                      <option value={AUTO_OPTION_VALUE}>{autoOptionLabel(suggestedVariant)}</option>
                      {library.map((v) => (
                        <option key={v.variant} value={v.variant}>
                          {libraryOptionLabel(v)}
                        </option>
                      ))}
                      {/* A cap chosen on the SelectionColumn cards need not be in THIS list — an
                          archived variant ("superseded-2026-07-13--6020") is a catalog id the
                          top-level library does not carry. Carry it as its own option so the row
                          states what it will ship instead of rendering an empty select. */}
                      {selectedValue !== AUTO_OPTION_VALUE && selectedLibraryEntry === null && (
                        <option value={selectedValue}>{selectedValue} — chosen on the selection cards</option>
                      )}
                    </select>
                    {hasDeclaration && (
                      <>
                        {/* The chosen part's dimensions stay visible WITHOUT opening the dropdown
                            (client ask 2026-07-23: visibility of the parts while choosing). */}
                        {selectedDims && (
                          <span className="confirm-table__dims" title="Selected variant — rim diameter × height">
                            {selectedDims}
                          </span>
                        )}
                        {/* THE COMPARE CONTROL (client, 2026-07-26: "we should still see side by
                            side the scan and the model"). The old "view part" REPLACED the scan
                            with the part; this points the docked pane at this row's variant while
                            the scan keeps the main stage. */}
                        <button
                          type="button"
                          className={`button button--ghost button--small${isComparingThisRow ? " button--active" : ""}`}
                          aria-pressed={isComparingThisRow}
                          onClick={() => onCompare(index)}
                          title={
                            isComparingThisRow
                              ? "The compare pane is showing this row's variant beside the scan"
                              : "Show this row's variant in the compare pane beside the scan"
                          }
                        >
                          compare ⇥
                        </button>
                      </>
                    )}
                  </div>
                </td>
                <td>
                  {isBrushingThisRow ? (
                    <div className="brush-banner" role="status" aria-live="polite">
                      <span className="brush-banner__text">Painting… drag on the model</span>
                      <div className="brush-banner__actions">
                        <button type="button" className="button button--primary" onClick={onFinishBrush}>
                          Done
                        </button>
                        <button
                          type="button"
                          className="button button--secondary"
                          onClick={onClearBrushStroke}
                        >
                          Clear stroke
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="confirm-table__patch-cell">
                      <button
                        type="button"
                        className="button button--secondary button--small"
                        disabled={isBusyElsewhere}
                        onClick={() => onStartBrush(index)}
                      >
                        🖌 Mark cap
                      </button>
                      {patchCount > 0 && (
                        <span className="chip chip--patch">
                          patch · {patchCount} pts
                          <button
                            type="button"
                            className="chip__remove"
                            aria-label={`Clear painted patch for tooth ${site.tooth}`}
                            onClick={() => onClearMarkedPoints(index)}
                          >
                            ✕
                          </button>
                        </span>
                      )}
                    </div>
                  )}
                </td>
                <td>
                  {isMarkingThisRow ? (
                    <div className="brush-banner" role="status" aria-live="polite">
                      <span className="brush-banner__text">Click the cap centre on the model…</span>
                      <div className="brush-banner__actions">
                        <button type="button" className="button button--secondary" onClick={onCancelMark}>
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : isCollectingRimThisRow ? (
                    <div className="brush-banner" role="status" aria-live="polite">
                      <span className="brush-banner__text">
                        Click several points around the cap&apos;s visible border…
                        {rimPointCount > 0 && ` (${rimPointCount} so far)`}
                      </span>
                      <div className="brush-banner__actions">
                        <button type="button" className="button button--primary" onClick={onFinishRimPoints}>
                          Done
                        </button>
                        <button
                          type="button"
                          className="button button--secondary"
                          onClick={onCancelRimPoints}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="confirm-table__patch-cell">
                      <button
                        type="button"
                        className="button button--secondary button--small"
                        disabled={isBusyElsewhere}
                        onClick={() => onStartMark(index, "center")}
                        title="Click once on the 3D scan at the cap's top centre"
                      >
                        ⊕ centre
                      </button>
                      {site.centerMark && (
                        <span className="chip chip--mark-center">
                          ⊕ set
                          <button
                            type="button"
                            className="chip__remove"
                            aria-label={`Clear the centre mark for tooth ${site.tooth}`}
                            onClick={() => onClearMark(index, "center")}
                          >
                            ✕
                          </button>
                        </span>
                      )}
                      <button
                        type="button"
                        className="button button--secondary button--small"
                        disabled={isBusyElsewhere}
                        onClick={() => onStartRimPoints(index)}
                        title="Click several points around the cap's visible border to find its width"
                      >
                        ◐ rim
                      </button>
                      {rimPointCount > 0 ? (
                        <span
                          className={`chip chip--mark-rim-points${hasEnoughRimPoints(site.rimPoints) ? "" : " chip--mark-rim-low"}`}
                          title={
                            hasEnoughRimPoints(site.rimPoints)
                              ? undefined
                              : `${RECOMMENDED_MIN_RIM_POINTS}+ points recommended`
                          }
                        >
                          ◐ {rimPointCount} pts
                          <button
                            type="button"
                            className="chip__remove"
                            aria-label={`Clear the rim points for tooth ${site.tooth}`}
                            onClick={() => onClearRim(index)}
                          >
                            ✕
                          </button>
                        </span>
                      ) : (
                        site.rimMark && (
                          <span className="chip chip--mark-rim">
                            ◐ set
                            <button
                              type="button"
                              className="chip__remove"
                              aria-label={`Clear the rim mark for tooth ${site.tooth}`}
                              onClick={() => onClearRim(index)}
                            >
                              ✕
                            </button>
                          </span>
                        )
                      )}
                    </div>
                  )}
                </td>
                <td>
                  <span className="confirm-table__check" aria-hidden="true">
                    ✓
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {hasDuplicateTeeth && (
        <p className="panel__error" role="alert">
          Tooth number{duplicateTeeth.length > 1 ? "s" : ""} {duplicateTeeth.join(", ")} used more
          than once — each site needs its own tooth before confirming.
        </p>
      )}

      {noSystemHint && <p className="panel__hint">{noSystemHint}</p>}

      <div className="panel__actions">
        <button
          type="button"
          className="button button--primary"
          disabled={disabled || hasDuplicateTeeth}
          onClick={onConfirmAll}
        >
          Confirm all
        </button>
      </div>
    </section>
  );
}
