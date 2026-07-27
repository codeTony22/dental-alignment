import type { DraftFeature, PartFeatureKind } from "../domain/partFeatures";
import {
  MAX_PART_FEATURES,
  MIN_LEVER_ARM_MM,
  PART_FEATURE_KINDS,
  annotationStateLine,
  draftDefinesRotation,
  featureLabel,
} from "../domain/partFeatures";
import { featureHex } from "../viewer/palette";

/** The annotation panel's own fetch/save lifecycle. "unavailable" is the specific 404: the
 *  RUNNING backend predates the features endpoints (the model/id always comes out of the
 *  catalog the same server just served, so an unknown-part 404 cannot arise here) — the
 *  panel shows the restart hint instead of an error, exactly like the catalog's own state. */
export type PartAnnotatorState = "loading" | "ready" | "unavailable" | "error";

/**
 * Everything App owns for the LIBRARY-SIDE annotation flow. The panel itself is static
 * markup + pure helpers (repo convention: interaction logic lives in App handlers and pure
 * functions with their own tests).
 */
export interface PartAnnotatorContext {
  readonly state: PartAnnotatorState;
  readonly errorMessage: string | null;
  /** Which catalog part is being annotated — the label the operator must be able to trust. */
  readonly model: string;
  readonly variant: string;
  readonly drafts: readonly DraftFeature[];
  /** True while these marks are still the machine's own reading (nothing persisted yet). */
  readonly autoSeeded: boolean;
  readonly revisedAt: string | null;
  /** Draft whose next part-click MOVES it (null = the next click appends a new mark). */
  readonly selectedKey: string | null;
  /** Kind a newly appended mark gets. */
  readonly kind: PartFeatureKind;
  /** True while a click on the 3D part is armed. */
  readonly armed: boolean;
  /** True while a save/reset request is in flight — every control disables. */
  readonly busy: boolean;
  /** Unsaved edits are on screen (drives Save's enabled state and the cue). */
  readonly dirty: boolean;
  /** False when the part's canonical frame could not be derived from the previewed mesh —
   *  marks cannot be located on it, so placing and drawing are both refused (never a marker
   *  in a plausible-but-wrong spot). */
  readonly canPlace: boolean;
  readonly onSelect: (key: string | null) => void;
  readonly onChangeKind: (kind: PartFeatureKind) => void;
  readonly onArm: () => void;
  readonly onCancelArm: () => void;
  readonly onRemove: (key: string) => void;
  readonly onSave: () => void;
  readonly onReset: () => void;
  readonly onClose: () => void;
}

const KIND_LABEL: Readonly<Record<PartFeatureKind, string>> = {
  trench: "trench",
  notch: "notch",
  flat: "flat",
  channel: "channel",
};

const PANEL_TOOLTIP =
  "Mark the holes/trenches on the LIBRARY part. The marks are saved against the catalog " +
  "variant, so every case that ships this part reuses them — and the scan side then names " +
  "which mark it is looking at instead of guessing the nearest one.";

const NO_FRAME_HINT =
  "This part's rim ring could not be fitted on the previewed mesh, so a mark cannot be " +
  "located on it. Marks are neither drawn nor placed here — nothing is guessed.";

/** The colored dot that ties a list row to its sphere in 3D (the SAME color table). */
function KindSwatch({ kind }: { readonly kind: PartFeatureKind }) {
  return (
    <span
      className="feature-swatch"
      style={{ backgroundColor: featureHex(kind) }}
      aria-hidden="true"
    />
  );
}

/**
 * PART ANNOTATION (client ask 2026-07-24, half one): "mark the holes/trenches in the LIBRARY
 * part". The auto-seeded features render as labelled markers ON the 3D part; clicking the part
 * adds a mark, or MOVES the selected one; each mark is selectable and removable; Save persists
 * the annotation for this catalog variant, "Reset to auto" drops it back to the machine's own
 * reading.
 *
 * The operator is confirming or correcting a reading, never starting from a blank part — so
 * the seed's provenance is stated up front ("machine reading — not saved yet" vs the revision
 * stamp), and the state line always names the variant the marks will be stored against.
 */
export function PartAnnotator({ context }: { readonly context: PartAnnotatorContext }) {
  const {
    state,
    errorMessage,
    model,
    variant,
    drafts,
    autoSeeded,
    revisedAt,
    selectedKey,
    kind,
    armed,
    busy,
    dirty,
    canPlace,
  } = context;
  const atCap = drafts.length >= MAX_PART_FEATURES;

  return (
    <section className="part-annotator" aria-labelledby="annotate-heading">
      <div className="part-annotator__header">
        <h3 id="annotate-heading" className="part-annotator__title" title={PANEL_TOOLTIP}>
          Annotate features — {model}/{variant}
        </h3>
        <button
          type="button"
          className="button button--ghost button--small"
          onClick={context.onClose}
          title="Leave annotation mode (unsaved marks are discarded)"
        >
          ✕ done
        </button>
      </div>

      {state === "loading" && (
        <div className="busy-state" role="status" aria-live="polite">
          <span className="busy-state__spinner" aria-hidden="true" />
          <span className="busy-state__message">reading this part's marks…</span>
        </div>
      )}

      {state === "unavailable" && (
        <p className="panel__error" role="alert">
          <span>
            The part-features endpoint is not available on the running API — restart{" "}
            <code>make serve</code> (apps/worker) to pick up this build, then reopen the
            annotation panel. Everything else keeps working meanwhile.
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
          <p className="part-annotator__state" role="status">
            {annotationStateLine(variant, drafts)}
            {autoSeeded ? (
              <span className="part-annotator__provenance"> · machine reading — not saved yet</span>
            ) : revisedAt !== null ? (
              <span className="part-annotator__provenance"> · saved {revisedAt}</span>
            ) : null}
            {dirty && <span className="part-annotator__dirty"> · unsaved marks</span>}
          </p>

          {!canPlace && (
            <p className="panel__error" role="alert">
              <span>{NO_FRAME_HINT}</span>
            </p>
          )}

          <div className="part-annotator__tools">
            <label className="part-annotator__kind">
              <span>new mark</span>
              <select
                value={kind}
                disabled={busy || !canPlace}
                onChange={(e) => context.onChangeKind(e.target.value as PartFeatureKind)}
              >
                {PART_FEATURE_KINDS.map((k) => (
                  <option key={k} value={k}>
                    {KIND_LABEL[k]}
                  </option>
                ))}
              </select>
            </label>
            {armed ? (
              <button
                type="button"
                className="button button--ghost button--small"
                onClick={context.onCancelArm}
                title="Stop waiting for the click on the part"
              >
                ✕ cancel
              </button>
            ) : (
              <button
                type="button"
                className="button button--primary button--small"
                disabled={busy || !canPlace || (selectedKey === null && atCap)}
                onClick={context.onArm}
                title={
                  selectedKey !== null
                    ? "Click the part to MOVE the selected mark"
                    : atCap
                      ? `A part annotation is capped at ${MAX_PART_FEATURES} marks`
                      : "Click the part to add a mark"
                }
              >
                {selectedKey !== null ? "⌖ move selected" : "＋ mark on the part"}
              </button>
            )}
          </div>

          {armed && (
            <p className="part-annotator__hint" role="status">
              {selectedKey !== null
                ? "click the part where that feature really is — Esc cancels"
                : "click the feature on the 3D part — Esc cancels"}
            </p>
          )}

          <ul className="part-annotator__list">
            {drafts.map((draft) => {
              const selected = draft.key === selectedKey;
              const anchors = draftDefinesRotation(draft);
              return (
                <li
                  key={draft.key}
                  className={`feature-row${selected ? " feature-row--selected" : ""}`}
                >
                  <button
                    type="button"
                    className="feature-row__select"
                    aria-pressed={selected}
                    disabled={busy}
                    onClick={() => context.onSelect(selected ? null : draft.key)}
                    title={
                      selected
                        ? "Selected — the next click on the part moves this mark"
                        : "Select this mark, then click the part to move it"
                    }
                  >
                    <KindSwatch kind={draft.kind} />
                    <span className="feature-row__label">{featureLabel(draft)}</span>
                    <span className="feature-row__source">{draft.source}</span>
                  </button>
                  {!anchors && (
                    <span
                      className="feature-row__note"
                      title={`Inside ${MIN_LEVER_ARM_MM}mm of the part's rim centre a landmark names the axis, not a clock angle — it is drawn and stored, but cannot anchor a rotation.`}
                    >
                      names the axis, not a clock angle
                    </span>
                  )}
                  <button
                    type="button"
                    className="button button--ghost button--small"
                    disabled={busy}
                    onClick={() => context.onRemove(draft.key)}
                    title="Remove this mark"
                  >
                    ✕
                  </button>
                </li>
              );
            })}
          </ul>

          {drafts.length === 0 && (
            <p className="panel__hint">
              No marks on this part — add at least one before saving (the endpoint refuses an
              empty annotation; use "Reset to auto" to go back to the machine's reading).
            </p>
          )}

          <div className="part-annotator__actions">
            <button
              type="button"
              className="button button--primary button--small"
              disabled={busy || !dirty || drafts.length === 0}
              onClick={context.onSave}
              title="Persist these marks for this catalog variant"
            >
              Save marks
            </button>
            <button
              type="button"
              className="button button--secondary button--small"
              disabled={busy || autoSeeded}
              onClick={context.onReset}
              title="Drop the stored annotation and go back to the machine's own reading"
            >
              Reset to auto
            </button>
            {busy && <span className="part-annotator__hint">working…</span>}
          </div>
        </>
      )}
    </section>
  );
}
