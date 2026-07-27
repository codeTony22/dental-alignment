import {
  BEST_FIT_DIAMETER_STEP_MM,
  BEST_FIT_MAX_DIAMETER_MM,
  BEST_FIT_MIN_DIAMETER_MM,
} from "../domain/types";

/**
 * The manual best fit's wiring for ONE row (App owns the diameter/apply state so it persists
 * across rows and across a re-render of the results table — an operator who has settled on 0.5mm
 * matching should not have to re-set it per tooth).
 */
export interface BestFitControls {
  readonly matchingDiameterMm: number;
  /** The client's Apply-Best-Fit toggle: off = measure the fit and report it without moving. */
  readonly apply: boolean;
  readonly busy: boolean;
  /** True when the RUNNING backend has no best-fit endpoint (a 404) — the panel says restart
   *  rather than leaving the button looking broken. */
  readonly unavailable: boolean;
  /** The last outcome line for THIS row (describeBestFit), or null. */
  readonly notice: string | null;
  /** THIS row's "already optimal" outcome (client ask 2026-07-26): the certified pose already
   *  is the best fit at the chosen diameter. A PASS, rendered in the confirmatory tone with a
   *  one-click wider search — never in the error tone the true refusals get. Both diameters are
   *  the RUN's own (the dial may have moved since): the widen button exists only while the
   *  suggestion actually is wider (review 2026-07-26 — at the Ø2.00mm ceiling it was a no-op
   *  loop re-running the identical search). */
  readonly confirmation: {
    readonly message: string;
    readonly matchingDiameterMm: number;
    readonly suggestedDiameterMm: number;
  } | null;
  readonly onChangeDiameter: (mm: number) => void;
  readonly onToggleApply: (apply: boolean) => void;
  readonly onRun: (tooth: number) => void;
  /** Set the diameter to the suggested wider value and re-run immediately. */
  readonly onSearchWider: (tooth: number, diameterMm: number) => void;
}

const BEST_FIT_TOOLTIP =
  "Refine this seat by matching the scan's surface to the library part — the client's " +
  "register/best-fit best fit. Only scan surface within the MATCHING DIAMETER of the part takes " +
  "part, so a tight diameter refines an already-close seat and a wide one can drag in " +
  "neighbouring gingiva. Judged by the same gates as every other pose change.";

const DIAMETER_TOOLTIP =
  "How far from the library part scan surface may sit and still be treated as belonging to it. " +
  "0.30 mm is the lab default.";

const APPLY_TOOLTIP =
  "On: the fit re-seats the part and the site's files are re-emitted. Off: the fit is measured " +
  "and reported, and the seated pose is left exactly where it is.";

/**
 * MANUAL FIT (the client's register/best-fit panel, 2026-07-25) — the dense-surface counterpart to
 * the two rotation-only tools it sits beside: "⌖ mark trench" binds one click, "⇔ match features"
 * binds named marks, and this matches the WHOLE visible surface within a chosen diameter.
 *
 * It is deliberately a PROPOSAL like the others: the Apply toggle lets an operator read the fit's
 * own numbers first (how much surface it found, what residual it reached, how far it wants to
 * move the seat) and commit only then. After an applied fit the caller re-shows the alignment in
 * the three-panel verify — the fit is only believable next to the picture it produced.
 */
export function BestFitPanel({
  tooth,
  controls,
}: {
  readonly tooth: number;
  readonly controls: BestFitControls;
}) {
  const diameterId = `best-fit-diameter-${tooth}`;
  const applyId = `best-fit-apply-${tooth}`;
  const confirmation = controls.confirmation;
  return (
    <div className="best-fit" title={BEST_FIT_TOOLTIP}>
      <div className="best-fit__row">
        <label className="best-fit__label" htmlFor={diameterId} title={DIAMETER_TOOLTIP}>
          Matching diameter
        </label>
        <input
          id={diameterId}
          className="best-fit__slider"
          type="range"
          min={BEST_FIT_MIN_DIAMETER_MM}
          max={BEST_FIT_MAX_DIAMETER_MM}
          step={BEST_FIT_DIAMETER_STEP_MM}
          value={controls.matchingDiameterMm}
          disabled={controls.busy || controls.unavailable}
          onChange={(e) => controls.onChangeDiameter(Number(e.target.value))}
        />
        <output className="best-fit__value" htmlFor={diameterId}>
          {controls.matchingDiameterMm.toFixed(2)} mm
        </output>
      </div>
      <div className="best-fit__row">
        <label className="best-fit__apply" htmlFor={applyId} title={APPLY_TOOLTIP}>
          <input
            id={applyId}
            type="checkbox"
            checked={controls.apply}
            disabled={controls.busy || controls.unavailable}
            onChange={(e) => controls.onToggleApply(e.target.checked)}
          />
          <span>Apply best fit</span>
        </label>
        <button
          type="button"
          className="button button--secondary button--small"
          disabled={controls.busy || controls.unavailable}
          title={BEST_FIT_TOOLTIP}
          onClick={() => controls.onRun(tooth)}
        >
          {controls.busy ? "fitting…" : controls.apply ? "⊚ Best fit" : "⊚ Measure fit"}
        </button>
      </div>
      {controls.unavailable && (
        <p className="panel__error best-fit__unavailable" role="alert">
          The best-fit endpoint is not available on the running API — restart <code>make serve</code>{" "}
          (apps/worker) to pick up this build.
        </p>
      )}
      {!controls.apply && !controls.unavailable && (
        <span className="best-fit__hint">
          measure only — the seated pose stays where it is until you tick Apply
        </span>
      )}
      {controls.notice && (
        <span className="best-fit__notice" role="status">
          {controls.notice}
        </span>
      )}
      {confirmation && (
        // A PASS, not a failure (client ask 2026-07-26): the server confirmed the certified
        // pose already is the best fit in this band — green/check tone, with the one-click
        // wider search the operator would otherwise have to dial in by hand.
        <div className="best-fit__confirm" role="status">
          <span className="best-fit__confirm-message">✓ {confirmation.message}</span>
          {/* No button at the ceiling (review 2026-07-26): the capped suggestion equals the
              dial there, and "Search wider (Ø2.00mm)" just re-ran the identical search — the
              server's message already says this band is the widest. */}
          {confirmation.suggestedDiameterMm > confirmation.matchingDiameterMm && (
            <button
              type="button"
              className="button button--secondary button--small"
              disabled={controls.busy || controls.unavailable}
              title="Set the matching diameter to the suggested wider value and run the fit again"
              onClick={() => controls.onSearchWider(tooth, confirmation.suggestedDiameterMm)}
            >
              Search wider (Ø{confirmation.suggestedDiameterMm.toFixed(2)}mm)
            </button>
          )}
        </div>
      )}
    </div>
  );
}
