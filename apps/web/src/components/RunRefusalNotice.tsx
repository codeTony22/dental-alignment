import type { RunRefusal } from "../domain/runRefusal";

export interface RunRefusalNoticeProps {
  readonly refusal: RunRefusal;
  readonly onDismiss: () => void;
}

/**
 * THE REFUSAL, MADE ACTIONABLE (client, 2026-07-25: "it read as an unexplained error").
 *
 * A refused run is not a transport failure and must not look like one. This is a PERSISTENT panel
 * in step 4 — not the transient toast the client met — laid out as the three things they needed:
 *
 *   what happened  (the title),
 *   why            (the SERVER'S own sentence, verbatim: it names the tooth, the part, the
 *                   measured channel radius and the relief that was asked for),
 *   what to do     (the next step, naming the control to change).
 *
 * Nothing here softens the refusal or offers a way around it: the gate is correct, and a part
 * whose screw channel has no measurable wall is not shippable at any relief. The panel's whole
 * job is to make the fix obvious instead of leaving a status code on screen.
 */
export function RunRefusalNotice({ refusal, onDismiss }: RunRefusalNoticeProps) {
  return (
    <section
      className={`run-refusal run-refusal--${refusal.kind}`}
      role="alert"
      aria-labelledby="run-refusal-title"
    >
      <div className="run-refusal__head">
        <h3 id="run-refusal-title" className="run-refusal__title">
          <span aria-hidden="true">⛔ </span>
          {refusal.title}
        </h3>
        <button
          type="button"
          className="button button--ghost button--small"
          onClick={onDismiss}
          aria-label="Dismiss the refusal"
        >
          ✕
        </button>
      </div>
      <p className="run-refusal__detail">{refusal.detail}</p>
      <p className="run-refusal__next">
        <span className="run-refusal__next-label">Next step: </span>
        {refusal.nextStep}
      </p>
      {refusal.status !== null && (
        <p className="run-refusal__status">
          The backend refused this run ({refusal.status}) and emitted no package — nothing partial
          was written for this case.
        </p>
      )}
    </section>
  );
}
