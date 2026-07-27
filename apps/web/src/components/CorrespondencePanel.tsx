import type { PartFeature } from "../domain/partFeatures";
import type { CorrespondencePair, CorrespondenceResidual } from "../domain/correspondence";
import type { Vec3 } from "../domain/types";
import {
  MAX_CORRESPONDENCE_PAIRS,
  anchorableFeatures,
  canAddPair,
  pairKey,
  pairLabel,
  residualLabel,
  unpairedFeatures,
} from "../domain/correspondence";
import { featureLabel } from "../domain/partFeatures";
import { featureHex, freePointHex } from "../viewer/palette";

/** The features fetch's lifecycle as this panel sees it — "unavailable" is the 404 from a
 *  RUNNING backend that predates the features endpoint (restart hint, not an error). */
export type CorrespondenceState = "loading" | "ready" | "unavailable" | "error";

/**
 * Everything App owns for ONE row's correspondence flow. Static markup + pure helpers here;
 * the click/arm/POST transitions live in App handlers (repo convention).
 */
export interface CorrespondenceControls {
  readonly state: CorrespondenceState;
  readonly errorMessage: string | null;
  /** The part whose marks this row is naming ("zimmer-4.5" / "7030"). */
  readonly model: string;
  readonly variant: string;
  /** The library part's marks — the picker's options. */
  readonly features: readonly PartFeature[];
  /** True while these are the machine's own reading (this part has never been marked). */
  readonly autoSeeded: boolean;
  /** Pairs recorded so far, in the order the operator named them. */
  readonly pairs: readonly CorrespondencePair[];
  /** Feature whose scan click is currently armed (null = nothing waiting on the 3D scan). */
  readonly armedFeatureId: string | null;
  /** FREE POINT armed on the part (client ask 2026-07-26): the canonical-frame click whose
   *  scan match is awaited, or null. Mutually exclusive with `armedFeatureId`. */
  readonly armedFreePoint: Vec3 | null;
  /** True while the align-to-correspondence POST for this row is in flight. */
  readonly busy: boolean;
  /** The last applied result's per-pair residuals + RMS, kept until the next arm/apply. */
  readonly residuals: readonly CorrespondenceResidual[] | null;
  readonly residualRmsMm: number | null;
  readonly onArm: (featureId: string) => void;
  readonly onCancelArm: () => void;
  /** A click landed on the PART pane itself — place a free numbered point there (canonical
   *  frame) and arm the scan pane for its match. */
  readonly onPickPartPoint: (canonicalPoint: Vec3) => void;
  readonly onRemovePair: (key: string) => void;
  readonly onClearPairs: () => void;
  readonly onApply: () => void;
  readonly onClose: () => void;
}

const PANEL_TOOLTIP =
  "Name WHICH marked feature of the library part you are about to click on the scan, then " +
  "click it — or click anywhere on the part itself to place a free numbered point where the " +
  "detector found nothing. Explicit correspondence — unlike the one-click trench tool it " +
  "cannot bind to the wrong cutout on a multi-feature cap, and it works where the automatic " +
  "code reader has no signal at all. The rotation is still judged by the same gates as every " +
  "step.";

const RMS_TOOLTIP =
  "How well your own marks agree with each other, in millimetres at each feature's own " +
  "radius — the QC number of a multi-point correspondence. With a single pair there is " +
  "nothing to disagree with, so none is shown.";

/** The colored dot tying a picker row to its sphere in 3D and to the part's own marker.
 *  A free point (kind null) wears the dedicated free-point color — its number plus this
 *  color is what pairs the part-pane marker with its scan-pane match. */
function KindSwatch({ kind }: { readonly kind: PartFeature["kind"] | null }) {
  const color = kind === null ? freePointHex() : featureHex(kind);
  return (
    <span className="feature-swatch" style={{ backgroundColor: color }} aria-hidden="true" />
  );
}

/**
 * SCAN-SIDE CORRESPONDENCE (client ask 2026-07-24, half two): pick which library feature you
 * are about to mark, click the matching spot on the scan, repeat, then "Align to my marks".
 * The returned per-pair residuals (and their RMS) are shown so the operator can see their own
 * marks agree before trusting the rotation.
 *
 * Sits alongside — never replaces — the one-click "⌖ mark trench" tool: that stays the fast
 * path (nearest code feature), this is the explicit one for the caps where "nearest" is
 * ambiguous or the automatic reader is blind.
 */
export function CorrespondencePanel({ controls }: { readonly controls: CorrespondenceControls }) {
  const {
    state,
    errorMessage,
    model,
    variant,
    features,
    autoSeeded,
    pairs,
    armedFeatureId,
    armedFreePoint,
    busy,
    residuals,
    residualRmsMm,
  } = controls;

  const anchorable = anchorableFeatures(features);
  const available = unpairedFeatures(features, pairs);
  const canAdd = canAddPair(features, pairs);
  // What the armed pick is called on screen: the feature's own id, or the free point's
  // would-be positional number (one past the free points already placed).
  const armedName =
    armedFeatureId ??
    (armedFreePoint !== null
      ? `point ${pairs.filter((p) => p.featureId === null).length + 1}`
      : null);

  return (
    <div className="correspondence" title={PANEL_TOOLTIP}>
      <div className="correspondence__header">
        <span className="correspondence__title">
          Match features — {model}/{variant}
        </span>
        <button
          type="button"
          className="button button--ghost button--small"
          onClick={controls.onClose}
          title="Close the correspondence flow (recorded marks are discarded)"
        >
          ✕ close
        </button>
      </div>

      {state === "loading" && (
        <span className="correspondence__hint" role="status">
          reading this part's marks…
        </span>
      )}

      {state === "unavailable" && (
        <p className="panel__error" role="alert">
          <span>
            The part-features endpoint is not available on the running API — restart{" "}
            <code>make serve</code> (apps/worker) to use named correspondences. The one-click
            "⌖ mark trench" tool is unaffected.
          </span>
        </p>
      )}

      {state === "error" && (
        <p className="panel__error" role="alert">
          {errorMessage ?? "Failed to load this part's marks."}
        </p>
      )}

      {state === "ready" && (
        <>
          {autoSeeded && (
            <span className="correspondence__hint">
              using the machine's reading of this part — annotate it in the library browser to
              mark the features yourself
            </span>
          )}

          {/* No anchorable feature no longer blocks the flow (client ask 2026-07-26):
              free points are placed on the part pane itself, so the pair list and the
              actions stay — only the feature picker has nothing to offer. */}
          {anchorable.length === 0 && (
            <p className="panel__hint">
              This part carries no feature that can anchor a rotation — every mark on it is
              concentric with the rim centre, which names the axis, not a clock angle. Click
              the part itself to place free numbered points instead.
            </p>
          )}

          <ol className="correspondence__pairs">
            {pairs.map((pair, index) => (
              <li key={pairKey(pairs, index)} className="correspondence__pair">
                <KindSwatch kind={pair.kind} />
                <span className="correspondence__pair-label">{pairLabel(pairs, index)}</span>
                <button
                  type="button"
                  className="button button--ghost button--small"
                  disabled={busy}
                  onClick={() => controls.onRemovePair(pairKey(pairs, index))}
                  title="Drop this pair"
                >
                  ✕
                </button>
              </li>
            ))}
          </ol>

          {armedName !== null ? (
            <div className="correspondence__armed">
              <span className="correspondence__arm-hint" role="status">
                click {armedName} on the scan — Esc cancels
              </span>
              <button
                type="button"
                className="button button--ghost button--small"
                onClick={controls.onCancelArm}
              >
                ✕ cancel
              </button>
            </div>
          ) : (
            <div className="correspondence__picker" role="group" aria-label="Pick a feature to mark">
              {available.map((feature) => (
                <button
                  key={feature.id}
                  type="button"
                  className="button button--secondary button--small correspondence__pick"
                  disabled={busy || !canAdd}
                  onClick={() => controls.onArm(feature.id)}
                  title={`Mark ${featureLabel(feature)} on the scan`}
                >
                  <KindSwatch kind={feature.kind} />
                  {feature.id}
                </button>
              ))}
              {anchorable.length > 0 && available.length === 0 && (
                <span className="correspondence__hint">
                  every markable feature of this part is paired
                  {pairs.length >= MAX_CORRESPONDENCE_PAIRS
                    ? ` (${MAX_CORRESPONDENCE_PAIRS}-pair cap reached)`
                    : ""}
                </span>
              )}
            </div>
          )}

          <div className="correspondence__actions">
            <button
              type="button"
              className="button button--primary button--small"
              disabled={busy || pairs.length === 0 || armedName !== null}
              onClick={controls.onApply}
              title="Rotate the seated cap so your named marks line up — judged by the same gates as every rotation step"
            >
              Align to my marks
            </button>
            <button
              type="button"
              className="button button--ghost button--small"
              disabled={busy || pairs.length === 0}
              onClick={controls.onClearPairs}
              title="Drop every recorded pair and start over"
            >
              Clear marks
            </button>
            {busy && <span className="correspondence__hint">aligning…</span>}
          </div>

          {residuals !== null && residuals.length > 0 && (
            <div className="correspondence__residuals">
              {residualRmsMm !== null && residuals.length > 1 && (
                <span className="correspondence__rms" title={RMS_TOOLTIP}>
                  your marks agree to {residualRmsMm.toFixed(2)}mm
                </span>
              )}
              <ul className="correspondence__residual-list">
                {residuals.map((r) => (
                  <li key={r.featureId} className="correspondence__residual">
                    {residualLabel(r)}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}
