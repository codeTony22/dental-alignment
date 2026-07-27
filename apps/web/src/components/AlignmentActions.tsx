import { useState } from "react";
import type { RunSiteResult } from "../domain/types";
import { describeNotchResidual } from "../domain/types";
import { BestFitPanel, type BestFitControls } from "./BestFitPanel";

/**
 * The three per-site corrections, wired once for the whole block. Per-tooth state (busy, the
 * last outcome line) is resolved by tooth inside; the diameter/apply pair is table-wide because
 * an operator settles on a matching diameter for the case, not for one tooth.
 */
export interface AlignmentActionsContext {
  /** Tooth whose request is in flight (any of the three) — that row's buttons go down. */
  readonly busyTooth: number | null;
  /** Tooth whose one-shot trench click is armed on the 3D scan, or null. */
  readonly armedTrenchTooth: number | null;
  readonly bestFit: Omit<BestFitControls, "busy" | "notice" | "confirmation"> & {
    readonly busyTooth: number | null;
    readonly notice: { readonly tooth: number; readonly text: string } | null;
    /** The last "already optimal" outcome, by tooth (client ask 2026-07-26) — a PASS the
     *  row's panel renders in the confirmatory tone with its one-click wider search. Carries
     *  the run's OWN matching diameter so the panel can tell a real widening from the capped
     *  ceiling suggestion (review 2026-07-26). */
    readonly confirmation: {
      readonly tooth: number;
      readonly message: string;
      readonly matchingDiameterMm: number;
      readonly suggestedDiameterMm: number;
    } | null;
  };
  /** The last applied fit-by-points outcome line, by tooth. */
  readonly correspondenceNotice: { readonly tooth: number; readonly text: string } | null;
  /** The last applied align-to-trench outcome line, by tooth. */
  readonly markTrenchNotice: { readonly tooth: number; readonly text: string } | null;
  readonly onOpenFitByPoints: (tooth: number) => void;
  readonly onStartMarkTrench: (tooth: number) => void;
  readonly onCancelMarkTrench: () => void;
  readonly onReverify: (tooth: number) => void;
}

interface AlignmentActionsProps {
  readonly sites: readonly RunSiteResult[];
  readonly context: AlignmentActionsContext;
}

const FIT_BY_POINTS_TOOLTIP =
  "Name WHICH marked feature of the library part each scan click is, on both views side by " +
  "side. Unlike the one-click trench tool it cannot bind to the wrong cutout on a cap with two " +
  "or three of them, and it still works where the automatic code reader has no signal at all.";

const BEST_FIT_TOOLTIP =
  "Refine this seat by matching the scan's surface to the library part within a chosen matching " +
  "diameter — the dense-surface counterpart to the point-based fits.";

const MARK_TRENCH_TOOLTIP =
  "One click on the cap's coded cutout/trench on the scan, and the cap rotates so its nearest " +
  "code feature lands on your mark. The fast path; use Fit by points when 'nearest' is ambiguous.";

const REVERIFY_TOOLTIP =
  "Re-open the three-panel verify on this site — the library part, the scanned cap, and the " +
  "union coloured by the deviation this alignment actually achieved.";

/**
 * THE POST-ALIGNMENT CORRECTIONS, MADE FINDABLE (client, 2026-07-26).
 *
 * Every one of these already worked; none of them could be found. "Best fit" and "Fit by points"
 * lived inside a rotation control that only expands on rows the automation flagged, inside a cell
 * of a fifteen-column table that scrolls sideways — so the client, looking for the correspondence
 * flow they had asked for, concluded it had not been built.
 *
 * So they are a BLOCK, above the table, one strip per seated site, always visible after a run:
 * the tooth, how its rotation currently reads, and the four things an operator can do about a
 * seat that is not right — with the last outcome line for each printed underneath. The rotation
 * STEPS stay in the table where they belong (they are a numeric nudge, read against the residual
 * in the same row); what moved here is every action that OPENS something.
 */
export function AlignmentActions({ sites, context }: AlignmentActionsProps) {
  /** Which site has its best-fit controls unfolded — the diameter/apply pair is two more rows of
   *  chrome, and an operator uses it on one site at a time. */
  const [openBestFit, setOpenBestFit] = useState<number | null>(null);

  if (sites.length === 0) return null;

  return (
    <section className="align-actions" aria-labelledby="align-actions-heading">
      <div className="align-actions__header">
        <h3 id="align-actions-heading" className="align-actions__title">
          If the alignment is not right
        </h3>
        <p className="align-actions__hint">
          Correct the seat, then re-verify it in the three panels. Every correction is a proposal —
          the same gates judge it as the automation's own pose.
        </p>
      </div>
      <ul className="align-actions__list">
        {sites.map((site) => {
          const busy = context.busyTooth === site.tooth;
          const armed = context.armedTrenchTooth === site.tooth;
          const bestFitOpen = openBestFit === site.tooth;
          return (
            <li key={site.tooth} className="align-actions__site">
              <div className="align-actions__row">
                <span className="align-actions__tooth">tooth {site.tooth}</span>
                <span className="align-actions__residual">
                  {describeNotchResidual(site.clocking)}
                </span>
                <div className="align-actions__buttons" role="group" aria-label={`Correct tooth ${site.tooth}`}>
                  <button
                    type="button"
                    className={`button button--small${bestFitOpen ? " button--active button--ghost" : " button--secondary"}`}
                    aria-expanded={bestFitOpen}
                    disabled={busy || armed}
                    title={BEST_FIT_TOOLTIP}
                    onClick={() => setOpenBestFit(bestFitOpen ? null : site.tooth)}
                  >
                    ⊚ Best fit
                  </button>
                  <button
                    type="button"
                    className="button button--secondary button--small"
                    disabled={busy || armed}
                    title={FIT_BY_POINTS_TOOLTIP}
                    onClick={() => context.onOpenFitByPoints(site.tooth)}
                  >
                    ⇔ Fit by points
                  </button>
                  {armed ? (
                    <button
                      type="button"
                      className="button button--ghost button--small"
                      title="Stop waiting for the trench click"
                      onClick={context.onCancelMarkTrench}
                    >
                      ✕ cancel mark
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="button button--ghost button--small"
                      disabled={busy}
                      title={MARK_TRENCH_TOOLTIP}
                      onClick={() => context.onStartMarkTrench(site.tooth)}
                    >
                      ⌖ Mark trench
                    </button>
                  )}
                  <button
                    type="button"
                    className="button button--ghost button--small"
                    disabled={busy || armed}
                    title={REVERIFY_TOOLTIP}
                    onClick={() => context.onReverify(site.tooth)}
                  >
                    ◱ Re-verify
                  </button>
                </div>
              </div>

              {bestFitOpen && (
                <BestFitPanel
                  tooth={site.tooth}
                  controls={{
                    matchingDiameterMm: context.bestFit.matchingDiameterMm,
                    apply: context.bestFit.apply,
                    unavailable: context.bestFit.unavailable,
                    busy: context.bestFit.busyTooth === site.tooth || busy,
                    notice:
                      context.bestFit.notice?.tooth === site.tooth
                        ? context.bestFit.notice.text
                        : null,
                    confirmation:
                      context.bestFit.confirmation?.tooth === site.tooth
                        ? {
                            message: context.bestFit.confirmation.message,
                            matchingDiameterMm: context.bestFit.confirmation.matchingDiameterMm,
                            suggestedDiameterMm: context.bestFit.confirmation.suggestedDiameterMm,
                          }
                        : null,
                    onChangeDiameter: context.bestFit.onChangeDiameter,
                    onToggleApply: context.bestFit.onToggleApply,
                    onRun: context.bestFit.onRun,
                    onSearchWider: context.bestFit.onSearchWider,
                  }}
                />
              )}

              {armed && (
                <span className="align-actions__notice" role="status">
                  click the coded trench on the scan — Esc cancels
                </span>
              )}
              {!armed && context.markTrenchNotice?.tooth === site.tooth && (
                <span className="align-actions__notice" role="status">
                  {context.markTrenchNotice.text}
                </span>
              )}
              {context.correspondenceNotice?.tooth === site.tooth && (
                <span className="align-actions__notice" role="status">
                  {context.correspondenceNotice.text}
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
