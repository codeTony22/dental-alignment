import type { RunSiteResult } from "../domain/types";
import { describeNotchResidual, NOTCH_ALIGNED_TOLERANCE_DEG, rotationNeedsReview } from "../domain/types";

interface RotationVerdictProps {
  readonly site: RunSiteResult;
  /** Open the three-panel verify on this site, where the rotation control actually lives.
   *  Omitted (a read-only embedding) the cell is a pure read-out. */
  readonly onAdjustIn3D?: (tooth: number) => void;
}

const VERIFIED_TOOLTIP =
  "READ BY THE AUTOMATION, not chosen by anyone: the pipeline unwraps the cap's top face and " +
  "correlates its coded cutouts against the library part's own pattern, so the rotation is " +
  `MEASURED. Within ±${NOTCH_ALIGNED_TOLERANCE_DEG}° the codes agree with the seat and there is ` +
  "nothing to correct.";

const REVIEW_TOOLTIP =
  "The coded-cutout reader could not confirm this rotation (no signal, or the instruments " +
  "disagree). Open it in 3D to correct it against the picture — a number typed into a table is " +
  "not something anyone can judge.";

/**
 * THE ROTATION COLUMN — A VERDICT, NOT A CONTROL (client, 2026-07-26: "the client will not be
 * selecting what degrees to rotate — there is barely any automation there and impractical").
 *
 * They were reading the UI correctly and the UI was lying about the product. Rotation IS
 * automated here: it is read off the cap's coded cutouts by depth-image correlation and shipped
 * as a measurement. The ±3°/±15° steps that used to sit in this cell are a BACKSTOP for the
 * minority of sites where that reader has no signal — and putting a stepper in a table column
 * made a measured pipeline look like a manual one, next to a 3D view too far away to judge it by.
 *
 * So the cell now states what the automation measured, and the only button it offers OPENS THE
 * 3D. The stepper itself moved to the union pane of the verify dialog (see RotationDial), where
 * every step is visible on the seated cap as it happens.
 */
export function RotationVerdict({ site, onAdjustIn3D }: RotationVerdictProps) {
  // Only rim seats carry a rotational instrument — an icp seat has no rim ring to hold fixed.
  if (site.seatMethod !== "rim") return <span title="rotation control needs a rim seat">—</span>;

  const needsReview = rotationNeedsReview(site.clocking);
  const cumulative = site.nudge?.cumulativeDeg ?? 0;

  return (
    <div className="rotation-verdict">
      <span
        className={
          needsReview
            ? "rotation-verdict__residual rotation-verdict__residual--review"
            : "rotation-verdict__residual"
        }
        title={needsReview ? REVIEW_TOOLTIP : VERIFIED_TOOLTIP}
      >
        {describeNotchResidual(site.clocking)}
      </span>
      {!needsReview && <span className="rotation-verdict__source">read from the coded cutouts</span>}
      {cumulative !== 0 && (
        <span
          className="rotation-verdict__cumulative"
          title="Operator rotation applied on top of the automation's pose (audited in implant.json)"
        >
          operator {cumulative > 0 ? "+" : ""}
          {cumulative.toFixed(1)}°
        </span>
      )}
      {onAdjustIn3D && (
        <button
          type="button"
          className={`button button--small${needsReview ? " button--secondary" : " button--ghost"}`}
          title={needsReview ? REVIEW_TOOLTIP : "Open this seat in the three-panel verify"}
          onClick={() => onAdjustIn3D(site.tooth)}
        >
          {needsReview ? "↻ Correct in 3D" : "◱ See in 3D"}
        </button>
      )}
    </div>
  );
}
