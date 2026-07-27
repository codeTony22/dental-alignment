import type { LibrarySelection } from "../domain/librarySelection";
import { formatOffsetMm } from "../domain/librarySelection";
import type { AchievedGingivalOffset } from "../domain/gingivalOffset";
import { describeAchievedOffset } from "../domain/gingivalOffset";
import {
  REVIEW_ROUTE_LABEL,
  reviewProgressText,
  runBlockers,
  unreviewedNotice,
} from "../domain/runGate";

export interface RunActionsProps {
  readonly selection: LibrarySelection;
  /** Step-3 rows claiming the same tooth — a blocker the selection itself cannot see. */
  readonly duplicateTeeth: readonly number[];
  /** 1-based row numbers still missing a declared cap, for the explanatory sentence (the gate
   *  itself already lists them; this paragraph says WHY the declaration is required). */
  readonly undeclaredSiteNumbers: readonly number[];
  readonly runBusy: boolean;
  /** Whether the last result came from cache — only then is "⟳ rerun live" offered at all. */
  readonly cached: boolean;
  readonly achievedOffset: AchievedGingivalOffset | null;
  readonly onRun: () => void;
  readonly onRerunLive: () => void;
  readonly onOpenVerify: () => void;
}

/**
 * STEP 4's ACTION BAR — and the place the acknowledgment gate is made VISIBLE.
 *
 * The bypass this component exists to close (verifier finding, 2026-07-25): the three quick-path
 * routes each carried their own enabled-expression, and none of them consulted the per-site
 * review state, so "Run automation", "⟳ rerun live" and Confirm All's recompute all processed
 * cases with ZERO sites reviewed — while the dialog's own OK button correctly
 * refused. Here every process button reads ONE list — `runBlockers` — and the same list is
 * printed next to them, so a disabled button is never a mystery:
 *
 *     "3 sites not yet reviewed — open Verify & process…"
 *
 * (The runtime half of the gate lives in domain/runGate: `authorizeRun` mints the only value
 * `runAutomation` accepts, so a route that skips the check cannot even be compiled. This
 * component is the operator-facing half — the reason, and the door.)
 *
 * When reviews are what is outstanding, "⧉ Verify & process" takes the PRIMARY styling: the
 * review is not a checkbox to be found, it is the next step, and this is its entry point.
 */
export function RunActions({
  selection,
  duplicateTeeth,
  undeclaredSiteNumbers,
  runBusy,
  cached,
  achievedOffset,
  onRun,
  onRerunLive,
  onOpenVerify,
}: RunActionsProps) {
  const blockers = runBlockers({ selection, duplicateTeeth });
  const ready = blockers.length === 0;
  const unreviewed = unreviewedNotice(selection);
  const progress = reviewProgressText(selection);
  const disabledReason = ready
    ? undefined
    : `Cannot process yet — still needed: ${blockers.join("; ")}`;

  return (
    <>
      {duplicateTeeth.length > 0 && (
        <p className="panel__error" role="alert">
          Tooth number{duplicateTeeth.length > 1 ? "s" : ""} {duplicateTeeth.join(", ")} used more
          than once — each site needs its own tooth before running.
        </p>
      )}
      {undeclaredSiteNumbers.length > 0 && (
        <p className="panel__error" role="alert">
          Declare a cap variant for site{undeclaredSiteNumbers.length > 1 ? "s" : ""}{" "}
          {undeclaredSiteNumbers.join(", ")} before running — pick the doctor&apos;s cap from the
          library in step 2. The automation still measures the rim as an independent cross-check,
          but the declaration is required for a confident alignment.
        </p>
      )}

      {/* THE DECODING SELECTION, stated before either route runs (client directive 2026-07-25).
          The quick path uses exactly what this line says — a preselected suggestion is visible
          here, never silently applied. */}
      <p className={`decode-selection-line${ready ? "" : " decode-selection-line--incomplete"}`}>
        <span className="decode-selection-line__label">Library selection:</span>{" "}
        {selection.model ?? "— no implant system —"} ·{" "}
        {selection.constructionPathId ?? "— no construction part —"} · {selection.jaw} jaw ·{" "}
        {formatOffsetMm(selection.gingivalOffsetMm)} mm gingival relief requested
        {achievedOffset && (
          <span className="decode-selection-line__achieved">
            {" "}
            · {describeAchievedOffset(achievedOffset)} on the last run
          </span>
        )}
      </p>

      {/* THE ACKNOWLEDGMENT STATE, always visible — not only when it blocks. An operator who can
          watch "1 of 3 reviewed" become "3 of 3" understands the gate; one who meets a dead
          button does not. */}
      {progress && (
        <p
          className={`decode-review-state${unreviewed ? " decode-review-state--blocking" : ""}`}
          role={unreviewed ? "alert" : "status"}
        >
          <span className="decode-review-state__progress">{progress}</span>
          {unreviewed && (
            <>
              <span className="decode-review-state__blocked"> — {unreviewed}</span>
              <span className="decode-review-state__hint">
                {" "}
                Every site must be reviewed against the scan before processing; open “
                {REVIEW_ROUTE_LABEL}” to review them.
              </span>
            </>
          )}
        </p>
      )}

      {!ready && (
        <p className="panel__hint decode-blockers" role="status">
          Still needed: {blockers.join("; ")}.
        </p>
      )}

      <div className="panel__actions">
        <button
          type="button"
          className="button button--primary"
          disabled={runBusy || !ready}
          title={disabledReason}
          onClick={onRun}
        >
          Run automation
        </button>
        <button
          type="button"
          className={unreviewed ? "button button--primary" : "button button--secondary"}
          disabled={runBusy}
          onClick={onOpenVerify}
          title={
            unreviewed
              ? `Review each site's library part against the scan — ${unreviewed}`
              : "Review the library part against the scan, then process"
          }
        >
          ⧉ Verify &amp; process
        </button>
        {cached && (
          <button
            type="button"
            className="button button--ghost"
            disabled={runBusy || !ready}
            title={disabledReason ?? "Run a live (uncached) automation pass"}
            onClick={onRerunLive}
          >
            ⟳ rerun live
          </button>
        )}
      </div>
    </>
  );
}
