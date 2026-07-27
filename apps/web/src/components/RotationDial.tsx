import type { Clocking, NudgeRequest } from "../domain/types";
import { describeNotchResidual, NOTCH_ALIGNED_TOLERANCE_DEG, rotationNeedsReview } from "../domain/types";

/** What the union pane needs to offer a rotation control for the site it is showing. */
export interface RotationDialSpec {
  readonly tooth: number;
  readonly clocking: Clocking | null;
  /** Operator rotation applied on top of the automation's pose, in degrees. */
  readonly cumulativeDeg: number;
  /** True while this site's step is in flight — the pane is about to redraw. */
  readonly busy: boolean;
  readonly onNudge: (tooth: number, request: NudgeRequest) => void;
}

const STEPS_DEG = [-15, -3, 3, 15] as const;

const DIAL_TOOLTIP =
  "Rotate the seated cap about its own axis (the rim centre stays fixed). Every step is judged " +
  "by the same stability bound and certification gates as the automation's own clocking — a step " +
  "the seat cannot hold is refused with the reason, so this can never ship a pose the pipeline " +
  "would not.";

/**
 * THE ROTATION CONTROL, ON THE 3D (client, 2026-07-26: "this rotation is kinda useless if it
 * doesn't have a good view of what it does real time").
 *
 * It used to live in a cell of a fifteen-column table, nowhere near the picture that would tell
 * you whether a step helped. Here it floats on the union pane: press a step and the seated cap in
 * front of you re-seats and re-colours, with the residual beside the buttons RE-READ from the
 * cap's coded cutouts at the new pose. The operator steers until the codes agree and the
 * deviation colouring goes quiet — judged by eye against the thing itself.
 *
 * Each step is a SERVER-GATED PROPOSAL, deliberately, rather than a free client-side spin: a
 * dragged preview would happily show a pose the certification gates then refuse, which is a worse
 * lie than a slow control. What the pane draws is always a pose that passed.
 */
export function RotationDial({ tooth, clocking, cumulativeDeg, busy, onNudge }: RotationDialSpec) {
  const needsReview = rotationNeedsReview(clocking);
  return (
    <div className="rotation-dial" title={DIAL_TOOLTIP}>
      <div className="rotation-dial__head">
        <span className="rotation-dial__label">Rotation</span>
        <span
          className={
            needsReview
              ? "rotation-dial__residual rotation-dial__residual--review"
              : "rotation-dial__residual"
          }
          title={
            `The coded-cutout residual re-read at the pose on screen — within ` +
            `±${NOTCH_ALIGNED_TOLERANCE_DEG}° the codes agree with the seat.`
          }
        >
          {describeNotchResidual(clocking)}
        </span>
      </div>
      <div
        className="rotation-dial__buttons"
        role="group"
        aria-label={`Rotate tooth ${tooth} about its own axis`}
      >
        {STEPS_DEG.map((step) => (
          <button
            key={step}
            type="button"
            className="button button--secondary button--small"
            disabled={busy}
            onClick={() => onNudge(tooth, { kind: "step", deltaDeg: step })}
          >
            {step > 0 ? `+${step}°` : `${step}°`}
          </button>
        ))}
        <button
          type="button"
          className="button button--ghost button--small"
          disabled={busy || cumulativeDeg === 0}
          title="Restore the automation's own certified pose"
          onClick={() => onNudge(tooth, { kind: "reset" })}
        >
          Reset
        </button>
      </div>
      {cumulativeDeg !== 0 && (
        <span
          className="rotation-dial__cumulative"
          title="Operator rotation applied so far (audited in implant.json)"
        >
          operator {cumulativeDeg > 0 ? "+" : ""}
          {cumulativeDeg.toFixed(1)}°
        </span>
      )}
    </div>
  );
}
