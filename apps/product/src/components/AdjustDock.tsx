/**
 * §10-AN — THE INSTRUMENT DOCK (2026-08-06). The Adjustment stage's tool drawer,
 * rebuilt to the client's new comp: a fixed header (five glyph tool chips, the
 * active tool's title and live readout, a dock-height toggle), ONE scrollable tool
 * body holding the active tool's own widget plus whatever the last act found, and a
 * fixed acts footer (re-preview, accept as flagged exception, drop, relief) that
 * never scrolls out of reach.
 *
 * THREE STANDING RULES CARRY OVER UNCHANGED FROM THE DRAWER THIS REPLACES:
 *
 * 1. Server sentences render VERBATIM. Every refusal, every outcome detail, every
 *    receipt is the BFF's own words, passed through — this file paraphrases nothing
 *    a gate said.
 * 2. OPTIMISM STAYS OFF. The gauge, the ring and the slider all show a PENDING value
 *    between acts — a local UI number the operator is aiming at — and the panes
 *    never move until the server's response replaces them. Committing (a drag
 *    release, a step, a snap, "run refinement") fires the SAME server act the old
 *    drawer's buttons fired; nothing here invents a new one.
 * 3. NO MOCK PHYSICS. The comp's own demo ships a fabricated deviation formula
 *    (`dev = 0.02 + rotErr/90*0.34 + …`) driving every number it draws; none of that
 *    formula is here. Every number this file draws reads exactly one served fact
 *    (`domain/adjust.ts`'s §10-AN section says which, and why) — arithmetic over a
 *    served scalar and a local UI value is display grading, not new physics.
 *
 * The five widgets are intentionally NOT one-to-one ports of the comp's own mock —
 * see the per-widget comments below and `domain/adjust.ts`'s own §10-AN header for
 * the specific claims that were dropped or reworded, and why.
 */
import { useEffect, useRef, useState } from "react";
import { useDialogEscape } from "./useDialogEscape";
import { useDialogFocus } from "./useDialogFocus";
import type {
  AdjustOutcomeView,
  LandmarkView,
  RePreviewView,
} from "../api/client";
import {
  ADJUST_DOCK_TOOLS,
  MAX_DIAMETER_MM,
  MIN_DIAMETER_MM,
  DEFAULT_DIAMETER_MM,
  ROTATION_STEPS,
  acceptExceptionOffer,
  applyBlockedReason,
  autoMarkDotPositions,
  autoMarkDotState,
  autoMarkSourceLabel,
  autoMarkSummary,
  autoMarkToolStateWords,
  bestFitFlagPositionPct,
  bestFitFlagWords,
  bestFitToolStateWords,
  clampDiameterMm,
  diameterBandWords,
  dockToolGood,
  dropLabel,
  dropNote,
  evidenceReceiptsTitle,
  flaggedExceptionWords,
  isComplete,
  observationWords,
  outcomeWords,
  pairCautions,
  pairCountHeaderWords,
  pairIdsFromSlot,
  pairSlot,
  pairSlots,
  pairSlotStrip,
  pairStatusLine,
  pairWords,
  receiptKindWords,
  receiptOutcomeWords,
  reconfirmControl,
  rePreviewButtonLabel,
  rePreviewRows,
  rePreviewWords,
  reworkWords,
  rotationGaugeFraction,
  rotationOffTrenchDeg,
  rotationToolStateWords,
  rotationTrenchTickDeg,
  scatterFillFraction,
  fitCrossCheckCaution,
  scatterWords,
  spanSplitRecoveryHint,
  splitSpanDraft,
  staleMetricsPhrase,
  trenchBand,
  trenchRingHint,
  trenchToolStateWords,
  unverifiedClockCautionLead,
  type AdjustQueueEntry,
  type AdjustToolId,
  type AlreadyOptimal,
  type ClockReferenceLike,
  type PairDraft,
  type PairSlot as PairSlotKey,
  type SeatedPhase,
  type UnverifiedClockNotice,
} from "../domain/adjust";

// --- shared small pieces (moved from AdjustStage.tsx — §10-AN: this is dock-body
// content now, so it lives with the rest of the dock) ---------------------------------

/**
 * PER-SITE RELIEF (§10-B/C): the site's own ask beside the case value, with the served
 * ceiling and the §10-AC disclosure. The draft is local; the ACT is the apply, and the
 * landed detail (a re-emit over a done run) replaces everything.
 */
function SiteReliefControl({
  siteValue,
  caseValue,
  ceilingLine,
  runDone,
  saving,
  error,
  onApply,
}: {
  readonly siteValue: number | null;
  readonly caseValue: number | null;
  readonly ceilingLine: string | null;
  readonly runDone: boolean;
  readonly saving: boolean;
  readonly error: string | null;
  readonly onApply: (value: number | null) => void;
}) {
  const [draft, setDraft] = useState<string>(
    siteValue !== null ? String(siteValue) : "",
  );
  useEffect(() => {
    setDraft(siteValue !== null ? String(siteValue) : "");
  }, [siteValue]);
  const parsed = draft.trim() === "" ? null : Number(draft);
  const usable = parsed === null || (Number.isFinite(parsed) && parsed >= 0);
  return (
    <div data-role="site-relief" className="site-relief">
      <span className="site-relief__label">
        Relief — this site
        <span className="site-relief__case">
          {siteValue !== null
            ? ` (case ${caseValue ?? "—"}mm, overridden)`
            : ` (case ${caseValue ?? "—"}mm stands)`}
        </span>
      </span>
      <label className="site-relief__field">
        <input
          data-role="site-relief-input"
          className="decode-offset__input"
          type="number"
          min={0}
          max={1}
          step={0.05}
          value={draft}
          disabled={saving}
          placeholder={caseValue !== null ? String(caseValue) : ""}
          onChange={(event) => setDraft(event.target.value)}
        />
        <span className="decode-offset__unit">mm</span>
      </label>
      <button
        type="button"
        data-role="site-relief-apply"
        className="button button--secondary button--small"
        disabled={saving || !usable || parsed === siteValue}
        title={
          runDone
            ? "Applying re-emits the package from the run's own poses — the fits " +
              "stand, and this site is cut at its own ask (the ceiling still clamps)."
            : "The override rides the next run; this site is cut at its own ask " +
              "(the ceiling still clamps)."
        }
        onClick={() => onApply(parsed)}
      >
        {saving
          ? "Applying…"
          : parsed === null && siteValue !== null
            ? "Clear the override"
            : "Apply to this site"}
      </button>
      {ceilingLine !== null && (
        <span data-role="site-relief-ceiling" className="site-relief__note">
          {ceilingLine}
        </span>
      )}
      {error !== null && (
        <span data-role="site-relief-error" role="alert" className="panel__error">
          {error}
        </span>
      )}
    </div>
  );
}

/**
 * THE PAIR LIST AND ITS APPLY CONTROL — the drafts a correspondence tool is building,
 * each broken into the marks it is made of, plus the one Apply act both
 * fit-by-points and auto-mark share (moved verbatim from AdjustStage.tsx — see that
 * file's history for why the two tools reuse one mechanic rather than two that could
 * drift).
 */
function PairsList({
  drafts,
  busy,
  pose,
  onRemovePair,
  onRemovePoint,
  onReplacePair,
  onApplyPairs,
  onClearPairs,
  clearLabel,
  sourceLabelFor,
  clock,
}: {
  readonly drafts: readonly PairDraft[];
  readonly busy: boolean;
  readonly pose: { readonly origin: readonly number[]; readonly axis: readonly number[] } | null;
  readonly clock: ClockReferenceLike | null;
  readonly onRemovePair: (id: string) => void;
  readonly onRemovePoint: (id: string, slot: PairSlotKey) => void;
  /** THE SPLIT AFFORDANCE'S OWN ACT (client live-testing 2026-08-09: "the ability to
   *  unblock each of the blockers"). Mechanizes `require_span_off_axis`'s own
   *  remedy sentence — `splitSpanDraft` does the arithmetic, this replaces the ONE
   *  both-halves span draft with the TWO point pairs it returns. */
  readonly onReplacePair: (id: string, replacements: readonly PairDraft[]) => void;
  readonly onApplyPairs: () => void;
  readonly onClearPairs: () => void;
  readonly clearLabel: string;
  readonly sourceLabelFor?: (draft: PairDraft) => string | null;
}) {
  const applyBlocked = applyBlockedReason(drafts, pose, clock);
  const openDraft = drafts.find((d) => !isComplete(d)) ?? null;
  return (
    <>
      <p data-role="pair-status" role="status" className="panel__hint">
        {pairStatusLine(drafts, openDraft)}
      </p>
      {/* THE CROSS-CHECK ADVISORY AND THE SCREW-ACCESS SENTENCE MOVED (§10-AN
          slice C) — off this row and into the dock header's caution chip + modal
          (`pairCautions`, domain/adjust.ts), which lists both VERBATIM. Nothing here
          computes the caution any more; `applyBlockedReason` below still reads
          `markLeverGuard` to decide whether Apply is blocked, unchanged. */}
      <ul data-role="pair-list" className="adjust-pairs">
        {drafts.map((draft, index) => (
          <li key={draft.id} data-role="pair-row" data-span={draft.span}
              data-slot={pairSlot(draft)}
              className={`adjust-pairs__row${
                pairSlot(draft) === "complete" ? " adjust-pairs__row--complete" : ""
              }`}>
            {sourceLabelFor && sourceLabelFor(draft) !== null && (
              <span data-role="pair-source" className="adjust-pairs__source">
                {sourceLabelFor(draft)}
              </span>
            )}
            <span className="adjust-pairs__words">
              {pairWords(draft, index)}
            </span>
            <ol data-role="pair-slots" className="adjust-pairs__slots">
              {pairSlots(draft).map((slot) => (
                <li
                  key={slot.key}
                  data-role="pair-slot"
                  data-slot={slot.key}
                  data-placed={slot.placed}
                  data-active={slot.active}
                  className={`adjust-pairs__slot${
                    slot.placed ? " adjust-pairs__slot--placed" : ""
                  }${slot.active ? " adjust-pairs__slot--active" : ""}`}
                >
                  <span aria-hidden="true" className="adjust-pairs__slot-mark">
                    {slot.placed ? "✓" : slot.active ? "→" : "○"}
                  </span>
                  <span className="adjust-pairs__slot-where">
                    {slot.where}
                    {slot.placed && (
                      <button
                        type="button"
                        data-role="remove-point"
                        data-pair={draft.id}
                        data-slot={slot.key}
                        className="adjust-pairs__slot-clear"
                        aria-label={`Remove this mark on ${slot.where}`}
                        title="Remove just this mark"
                        disabled={busy}
                        onClick={() => onRemovePoint(draft.id, slot.key)}
                      >
                        undo
                      </button>
                    )}
                  </span>
                  <span className="adjust-pairs__slot-label">{slot.label}</span>
                </li>
              ))}
            </ol>
            {/* THE SPLIT AFFORDANCE (client live-testing 2026-08-09): only a COMPLETE
                both-halves span — the shape `splitSpanDraft` actually knows how to
                turn into two point pairs — offers this. A scan-only span has one
                part landmark; `splitSpanDraft` returns null for it, and a button
                that clicked to nothing would be worse than no button. */}
            {draft.span && draft.partSpan && isComplete(draft) && (
              <button
                type="button"
                data-role="split-pair"
                data-pair={draft.id}
                className="button button--ghost button--small"
                title="Turns this span into two ordinary point pairs, ends paired respectively — the server's own remedy for a span across the axis."
                disabled={busy}
                onClick={() => {
                  const halves = splitSpanDraft(draft);
                  if (halves !== null) onReplacePair(draft.id, halves);
                }}
              >
                Mark ends as two pairs
              </button>
            )}
            <button
              type="button"
              data-role="remove-pair"
              data-pair={draft.id}
              className="button button--ghost button--small"
              disabled={busy}
              onClick={() => onRemovePair(draft.id)}
            >
              Remove
            </button>
          </li>
        ))}
      </ul>
      <div className="adjust-tool__row">
        {applyBlocked === null ? (
          <button
            type="button"
            data-role="apply-pairs"
            className="button button--primary button--small"
            disabled={busy}
            onClick={onApplyPairs}
          >
            Apply the fit
          </button>
        ) : (
          <span
            data-role="apply-pairs"
            aria-disabled="true"
            title={applyBlocked}
            className="button button--secondary button--blocked"
          >
            Apply the fit
          </span>
        )}
        {drafts.length > 0 && (
          <button
            type="button"
            data-role="clear-pairs"
            className="button button--ghost button--small"
            disabled={busy}
            onClick={onClearPairs}
          >
            {clearLabel}
          </button>
        )}
      </div>
    </>
  );
}

/**
 * THE SCATTER METER — renders ONLY from a served residual on the last outcome
 * (§10-AN: "absent otherwise"). No colour banding against an invented tolerance
 * (`scatterFillFraction`'s own doctrine); one neutral fill, a number, nothing more.
 */
function ScatterMeter({ residualRmsMm }: { readonly residualRmsMm: number | null }) {
  const words = scatterWords(residualRmsMm);
  if (words === null) return null;
  const fraction = scatterFillFraction(residualRmsMm) ?? 0;
  return (
    <div data-role="scatter-meter" className="adjust-dock__scatter">
      <span className="adjust-dock__scatter-label">scatter</span>
      <span className="adjust-dock__scatter-track">
        <span
          className="adjust-dock__scatter-fill"
          style={{ width: `${(fraction * 100).toFixed(1)}%` }}
        />
      </span>
      <span data-role="scatter-value" className="adjust-dock__scatter-value">
        {words}
      </span>
    </div>
  );
}

// --- the five widgets -------------------------------------------------------------------

function RotationWidget({
  cumulativeDeg,
  notchShiftDeg,
  busy,
  onRotate,
  onResetRotation,
}: {
  readonly cumulativeDeg: number | null;
  readonly notchShiftDeg: number | null;
  readonly busy: boolean;
  readonly onRotate: (stepDeg: number) => void;
  readonly onResetRotation: () => void;
}) {
  // THE PENDING ANGLE (§10-AN decision 2): a LOCAL UI number, never sent until the
  // operator commits it. It always starts back at 0 — the handle's rest position —
  // because it names the NEXT step about to be proposed, not the site's cumulative
  // rotation (that number is `cumulativeDeg`, the server's own fact, read separately).
  const [pendingDeg, setPendingDeg] = useState(0);
  const gaugeRef = useRef<HTMLInputElement | null>(null);

  // COMMIT ON RELEASE, NOT ON EVERY TICK (§10-AN decision 2). React's onChange fires
  // on every drag tick (the DOM `input` event); the native `change` event fires once,
  // on release — exactly the "drag release … fires the server act" the decision asks
  // for. Wired as a native listener because that distinction has no React prop.
  useEffect(() => {
    const el = gaugeRef.current;
    if (el === null) return;
    const commit = () => {
      const value = Math.round(Number(el.value));
      if (value !== 0) onRotate(value);
      setPendingDeg(0);
    };
    el.addEventListener("change", commit);
    return () => el.removeEventListener("change", commit);
  }, [onRotate]);

  const offDeg = rotationOffTrenchDeg(pendingDeg, notchShiftDeg);
  const band = trenchBand(offDeg);
  const trenchTick = rotationTrenchTickDeg(notchShiftDeg);
  const atDeg = (deg: number) =>
    `calc(22px + ${rotationGaugeFraction(deg)} * (100% - 44px))`;

  return (
    <div className="adjust-dock__widget" data-role="rotation-widget">
      <div
        data-role="rotation-gauge"
        className="adjust-dock__gauge"
        aria-label="Pending rotation step"
      >
        <span className="adjust-dock__gauge-track" aria-hidden="true" />
        {[-45, -30, -15, 0, 15, 30, 45].map((tick) => (
          <span
            key={tick}
            aria-hidden="true"
            className={`adjust-dock__gauge-tick${
              tick % 45 === 0 ? " adjust-dock__gauge-tick--major" : ""
            }`}
            style={{ left: atDeg(tick) }}
          />
        ))}
        {[-45, 0, 45].map((tick) => (
          <span
            key={tick}
            aria-hidden="true"
            className="adjust-dock__gauge-tick-label"
            style={{ left: atDeg(tick) }}
          >
            {tick > 0 ? `+${tick}°` : `${tick}°`}
          </span>
        ))}
        {trenchTick !== null && Math.abs(trenchTick) <= 45 && (
          <>
            <span
              data-role="rotation-trench-tick"
              aria-hidden="true"
              className="adjust-dock__gauge-trench"
              style={{ left: atDeg(trenchTick) }}
            />
            <span
              aria-hidden="true"
              className="adjust-dock__gauge-trench-label"
              style={{ left: atDeg(trenchTick) }}
            >
              trench
            </span>
          </>
        )}
        <input
          ref={gaugeRef}
          type="range"
          data-role="rotation-gauge-input"
          className="adjust-dock__gauge-input"
          aria-label="Pending rotation step, degrees"
          min={-45}
          max={45}
          step={1}
          value={pendingDeg}
          disabled={busy}
          onChange={(event) => setPendingDeg(Number(event.target.value))}
        />
        <span
          data-role="rotation-handle"
          data-band={band}
          aria-hidden="true"
          className={`adjust-dock__gauge-handle adjust-dock__gauge-handle--${band}`}
          style={{ left: atDeg(pendingDeg) }}
        >
          {pendingDeg > 0 ? `+${pendingDeg}°` : `${pendingDeg}°`}
        </span>
      </div>
      <div className="adjust-tool__row">
        {ROTATION_STEPS.map((step) => (
          <button
            key={step}
            type="button"
            data-role="rotation-step"
            data-step={step}
            className="button button--secondary button--small"
            disabled={busy}
            onClick={() => onRotate(step)}
          >
            {step > 0 ? `+${step}°` : `${step}°`}
          </button>
        ))}
        <button
          type="button"
          data-role="rotation-snap"
          className="button button--primary button--small"
          disabled={busy || notchShiftDeg === null || trenchBand(notchShiftDeg) === "on"}
          onClick={() => notchShiftDeg !== null && onRotate(Math.round(notchShiftDeg))}
        >
          {notchShiftDeg !== null && trenchBand(notchShiftDeg) === "on"
            ? "already on the trench"
            : "snap to the trench"}
        </button>
        <button
          type="button"
          data-role="rotation-reset"
          className="button button--ghost button--small"
          disabled={busy}
          onClick={onResetRotation}
        >
          Reset to the certified pose
        </button>
      </div>
      <p data-role="rotation-residual" className="adjust-tool__readout">
        {(() => {
          const residual =
            notchShiftDeg !== null
              ? `coded-cutout residual ${notchShiftDeg.toFixed(1)}°`
              : "coded-cutout residual not read yet";
          const cumulative =
            cumulativeDeg !== null
              ? `cumulative ${cumulativeDeg > 0 ? "+" : ""}${cumulativeDeg.toFixed(1)}°`
              : "no operator rotation on this site";
          return `${residual} · ${cumulative}`;
        })()}
      </p>
    </div>
  );
}

/**
 * MARK TRENCH — the 92px ring, ADAPTED from the comp (§10-AN). The comp's own ring
 * lets the operator click ANYWHERE and turns the cap to that arbitrary bearing
 * ("cap turned to +N° — that is not the trench"); doing that honestly needs an
 * ABSOLUTE clock reading this app is never served (`notch_shift_deg` is a RESIDUAL,
 * not a clock position). So this ring offers the one action the served fact actually
 * supports: snapping the code feature onto the trench — the tooltip's own words
 * ("one click does what stepping the dial does by hand") describe exactly that act,
 * and it fires the SAME server call the rotation gauge's own snap button does.
 *
 * The EXISTING arm-and-click-on-the-scan flow (`postMarkTrench`, a real 3-D
 * measurement from where the operator actually clicks) is kept beside it — it is a
 * genuinely different, independent act the ring cannot replace, since the ring has
 * no mesh to click into.
 */
function MarkTrenchWidget({
  notchShiftDeg,
  busy,
  onRotate,
  trenchArmed,
  onArmTrench,
}: {
  readonly notchShiftDeg: number | null;
  readonly busy: boolean;
  readonly onRotate: (stepDeg: number) => void;
  readonly trenchArmed: boolean;
  readonly onArmTrench: () => void;
}) {
  const band = trenchBand(notchShiftDeg);
  const onTrench = band === "on";
  const disabled = busy || notchShiftDeg === null || onTrench;
  return (
    <div className="adjust-dock__widget" data-role="mark-trench-widget">
      <button
        type="button"
        data-role="trench-ring"
        className="adjust-dock__ring"
        disabled={disabled}
        title={trenchRingHint(notchShiftDeg)}
        aria-label="Snap the cap's code feature onto the scanned trench"
        onClick={() => notchShiftDeg !== null && onRotate(Math.round(notchShiftDeg))}
      >
        <span className="adjust-dock__ring-band" aria-hidden="true" />
        {Array.from({ length: 12 }, (_, i) => (
          <span
            key={i}
            aria-hidden="true"
            className="adjust-dock__ring-tick"
            style={{ transform: `rotate(${i * 30}deg)` }}
          />
        ))}
        {notchShiftDeg !== null && (
          <span
            data-role="trench-notch"
            aria-hidden="true"
            className="adjust-dock__ring-notch"
            style={{ transform: `rotate(${notchShiftDeg}deg)` }}
          />
        )}
        <span className="adjust-dock__ring-disc" aria-hidden="true" />
        <span
          data-role="trench-code-mark"
          data-band={band}
          aria-hidden="true"
          className={`adjust-dock__ring-code adjust-dock__ring-code--${band}`}
        />
      </button>
      <div className="adjust-dock__col">
        <p data-role="trench-hint" className="panel__hint">
          {trenchRingHint(notchShiftDeg)}
        </p>
        <div className="adjust-tool__row">
          <button
            type="button"
            data-role="arm-trench"
            aria-pressed={trenchArmed}
            className={`button button--small ${
              trenchArmed ? "button--primary" : "button--secondary"
            }`}
            disabled={busy}
            onClick={onArmTrench}
          >
            {trenchArmed
              ? "Armed — click the trench on the scan"
              : "Mark the trench on the scan"}
          </button>
        </div>
      </div>
    </div>
  );
}

function BestFitWidget({
  diameterMm,
  onChangeDiameter,
  onBestFit,
  pass,
  busy,
}: {
  readonly diameterMm: number;
  readonly onChangeDiameter: (mm: number) => void;
  readonly onBestFit: (apply: boolean) => void;
  readonly pass: AlreadyOptimal | null;
  readonly busy: boolean;
}) {
  return (
    <div className="adjust-dock__widget" data-role="best-fit-widget">
      <div className="adjust-dock__dial-col">
        {pass !== null && (
          /* §10-AN AMENDMENT: renders ONLY off the last best-fit response's own
             suggestion — never a standing "rim reads" claim. */
          <span
            data-role="best-fit-flag"
            className="adjust-dock__flag"
            style={{ left: `${bestFitFlagPositionPct(pass.suggestedDiameterMm)}%` }}
          >
            {bestFitFlagWords(pass.suggestedDiameterMm)}
          </span>
        )}
        <input
          id="matching-diameter"
          data-role="diameter-input"
          type="range"
          className="adjust-dock__slider"
          min={MIN_DIAMETER_MM}
          max={MAX_DIAMETER_MM}
          step={0.05}
          value={diameterMm}
          disabled={busy}
          onChange={(e) => onChangeDiameter(Number(e.target.value))}
        />
        <span className="adjust-dock__slider-ticks" aria-hidden="true">
          {Array.from({ length: 9 }, (_, i) => (
            <span
              key={i}
              className={`adjust-dock__slider-tick${
                i % 4 === 0 ? " adjust-dock__slider-tick--major" : ""
              }`}
              style={{ left: `${(i / 8) * 100}%` }}
            />
          ))}
        </span>
        <div className="adjust-dock__scale" aria-hidden="true">
          <span>{MIN_DIAMETER_MM.toFixed(2)}</span>
          <span>1.00</span>
          <span>{MAX_DIAMETER_MM.toFixed(2)} mm</span>
        </div>
      </div>
      <div className="adjust-tool__row">
        <button
          type="button"
          data-role="diameter-nudge-down"
          className="button button--ghost button--small"
          disabled={busy}
          onClick={() => onChangeDiameter(clampDiameterMm(diameterMm - 0.05))}
        >
          − 0.05
        </button>
        <button
          type="button"
          data-role="diameter-nudge-up"
          className="button button--ghost button--small"
          disabled={busy}
          onClick={() => onChangeDiameter(clampDiameterMm(diameterMm + 0.05))}
        >
          + 0.05
        </button>
        <button
          type="button"
          data-role="diameter-reset"
          className="button button--ghost button--small"
          disabled={busy}
          onClick={() => onChangeDiameter(DEFAULT_DIAMETER_MM)}
        >
          Reset to Ø{DEFAULT_DIAMETER_MM.toFixed(2)} mm
        </button>
        <button
          type="button"
          data-role="best-fit-measure"
          className="button button--ghost button--small"
          disabled={busy}
          onClick={() => onBestFit(false)}
        >
          Measure only
        </button>
        <button
          type="button"
          data-role="best-fit-apply"
          className="button button--primary button--small"
          disabled={busy}
          onClick={() => onBestFit(true)}
        >
          Run refinement
        </button>
      </div>
      <p data-role="diameter-band" className="panel__hint">
        {diameterBandWords()}
      </p>
    </div>
  );
}

/** Slot strip shared by fit-by-points (the operator's own hand-built pairs). Locked
 *  and next slots are inert — starting a pair is already three explicit buttons below
 *  (point / span-the-scan / span-both), and this strip does not guess which one a bare
 *  numbered click would have meant (§10-AN: "do not invent an act"). */
function PairSlotStrip({
  drafts,
  onDropFrom,
}: {
  readonly drafts: readonly PairDraft[];
  readonly onDropFrom: (index: number) => void;
}) {
  return (
    <div data-role="pair-slot-strip" className="adjust-dock__slots">
      {pairSlotStrip(drafts).map((entry) => (
        <button
          key={entry.index}
          type="button"
          data-role="pair-slot-strip-item"
          data-index={entry.index}
          data-state={entry.state}
          data-spare={entry.spare}
          title={entry.title}
          disabled={entry.state !== "placed"}
          className={`adjust-dock__slot adjust-dock__slot--${entry.state}${
            entry.spare ? " adjust-dock__slot--spare" : ""
          }`}
          onClick={() => entry.state === "placed" && onDropFrom(entry.index)}
        >
          {entry.index}
        </button>
      ))}
    </div>
  );
}

function FitByPointsWidget({
  drafts,
  busy,
  pose,
  clock,
  onStartPair,
  onRemovePair,
  onRemovePoint,
  onReplacePair,
  onApplyPairs,
  onClearPairs,
  ghostsActive,
  residualRmsMm,
  crossChecked = null,
}: {
  readonly drafts: readonly PairDraft[];
  readonly busy: boolean;
  readonly pose: { readonly origin: readonly number[]; readonly axis: readonly number[] } | null;
  readonly clock: ClockReferenceLike | null;
  readonly onStartPair: (span: boolean, partSpan?: boolean) => void;
  readonly onRemovePair: (id: string) => void;
  readonly onRemovePoint: (id: string, slot: PairSlotKey) => void;
  readonly onReplacePair: (id: string, replacements: readonly PairDraft[]) => void;
  readonly onApplyPairs: () => void;
  readonly onClearPairs: () => void;
  readonly ghostsActive: boolean;
  readonly residualRmsMm: number | null;
  /** the sealed cross-check fact — false renders the single-observation caution */
  readonly crossChecked?: boolean | null;
}) {
  const openDraft = drafts.find((d) => !isComplete(d)) ?? null;
  return (
    <div data-role="fit-by-points-widget">
      <PairSlotStrip
        drafts={drafts}
        onDropFrom={(index) =>
          pairIdsFromSlot(drafts, index).forEach((id) => onRemovePair(id))
        }
      />
      {ghostsActive && (
        <p data-role="ghost-note" className="panel__hint">
          The faint amber marker shows where the current pose expects this point on
          the scan — click where you actually see the feature; the difference is the
          correction the fit measures.
        </p>
      )}
      <div className="adjust-tool__row">
        <button
          type="button"
          data-role="start-point-pair"
          className="button button--secondary button--small"
          disabled={busy || openDraft !== null}
          title="1 click on the library part, 1 on the scan."
          onClick={() => onStartPair(false)}
        >
          Point pair
        </button>
        <button
          type="button"
          data-role="start-span-pair"
          className="button button--secondary button--small"
          disabled={busy || openDraft !== null}
          title={
            "1 click on the library part, 2 on the scan. Two clicks spanning " +
            "one feature — both ends of the trench, or across a hole. The " +
            "midpoint averages the click noise; the direction is a second " +
            "reading the server judges on its own."
          }
          onClick={() => onStartPair(true)}
        >
          Span the scan
        </button>
        <button
          type="button"
          data-role="start-library-span-pair"
          className="button button--secondary button--small"
          disabled={busy || openDraft !== null}
          title={
            "2 clicks on the library part, 2 on the scan. Span the SAME " +
            "feature on both halves. The part's bearing stops being assumed " +
            "radial and becomes measured, which makes a chord across a " +
            "feature a reading the server can use instead of drop."
          }
          onClick={() => onStartPair(true, true)}
        >
          Span both
        </button>
      </div>
      <PairsList
        drafts={drafts}
        busy={busy}
        pose={pose}
        clock={clock}
        onRemovePair={onRemovePair}
        onRemovePoint={onRemovePoint}
        onReplacePair={onReplacePair}
        onApplyPairs={onApplyPairs}
        onClearPairs={onClearPairs}
        clearLabel="Clear all pairs"
      />
      <ScatterMeter residualRmsMm={residualRmsMm} />
      {fitCrossCheckCaution(crossChecked) !== null && (
        <p data-role="fit-single-observation-caution" className="adjust-pairs__caution">
          ⚠ {fitCrossCheckCaution(crossChecked)}
        </p>
      )}
    </div>
  );
}

function AutoMarkMap({ drafts, landmarks }: {
  readonly drafts: readonly PairDraft[];
  readonly landmarks: readonly LandmarkView[];
}) {
  const positions = autoMarkDotPositions(landmarks);
  return (
    <div data-role="auto-mark-map" className="adjust-dock__map" aria-hidden="true">
      <span className="adjust-dock__map-disc" />
      {positions.map((pos, index) => {
        const state = autoMarkDotState(drafts, index);
        return (
          <span
            key={pos.id}
            data-role="auto-mark-dot"
            data-state={state}
            className={`adjust-dock__dot adjust-dock__dot--${state}`}
            style={{ left: `${pos.leftPct}%`, top: `${pos.topPct}%` }}
          >
            {index + 1}
          </span>
        );
      })}
    </div>
  );
}

function AutoMarkWidget({
  autoMarkLandmarks,
  autoMarkPhase,
  autoMarkError,
  drafts,
  busy,
  pose,
  clock,
  onRemovePair,
  onRemovePoint,
  onReplacePair,
  onApplyPairs,
  onClearPairs,
  ghostsActive,
  residualRmsMm,
  crossChecked = null,
}: {
  readonly autoMarkLandmarks: readonly LandmarkView[];
  readonly autoMarkPhase: SeatedPhase;
  readonly autoMarkError: string | null;
  readonly drafts: readonly PairDraft[];
  readonly busy: boolean;
  readonly pose: { readonly origin: readonly number[]; readonly axis: readonly number[] } | null;
  readonly clock: ClockReferenceLike | null;
  readonly onRemovePair: (id: string) => void;
  readonly onRemovePoint: (id: string, slot: PairSlotKey) => void;
  readonly onReplacePair: (id: string, replacements: readonly PairDraft[]) => void;
  readonly onApplyPairs: () => void;
  readonly onClearPairs: () => void;
  readonly ghostsActive: boolean;
  readonly residualRmsMm: number | null;
  /** the sealed cross-check fact — false renders the single-observation caution */
  readonly crossChecked?: boolean | null;
}) {
  return (
    <div data-role="auto-mark-widget">
      <div className="adjust-dock__widget">
        <AutoMarkMap drafts={drafts} landmarks={autoMarkLandmarks} />
        <div className="adjust-dock__col">
          {autoMarkPhase === "loading" && (
            <p data-role="auto-mark-loading" className="adjust-tool__readout">
              Reading the library's proposed landmarks…
            </p>
          )}
          {autoMarkPhase === "error" && (
            <p data-role="auto-mark-error" role="alert" className="panel__error">
              {autoMarkError}
            </p>
          )}
          {autoMarkPhase === "ready" && (
            <>
              <p data-role="auto-mark-summary" className="panel__hint">
                {autoMarkSummary(autoMarkLandmarks)}
              </p>
              {ghostsActive && (
                <p data-role="ghost-note" className="panel__hint">
                  The faint amber marker shows where the current pose expects this
                  point on the scan — click where you actually see the feature; the
                  difference is the correction the fit measures.
                </p>
              )}
            </>
          )}
        </div>
      </div>
      <PairsList
        drafts={drafts}
        busy={busy}
        pose={pose}
        clock={clock}
        onRemovePair={onRemovePair}
        onRemovePoint={onRemovePoint}
        onReplacePair={onReplacePair}
        onApplyPairs={onApplyPairs}
        onClearPairs={onClearPairs}
        clearLabel="Start the matching over"
        sourceLabelFor={(draft) => autoMarkSourceLabel(draft, autoMarkLandmarks)}
      />
      <ScatterMeter residualRmsMm={residualRmsMm} />
      {fitCrossCheckCaution(crossChecked) !== null && (
        <p data-role="fit-single-observation-caution" className="adjust-pairs__caution">
          ⚠ {fitCrossCheckCaution(crossChecked)}
        </p>
      )}
    </div>
  );
}

// --- the dock itself ---------------------------------------------------------------------

export interface AdjustDockProps {
  readonly tool: AdjustToolId;
  readonly onSelectTool: (tool: AdjustToolId) => void;
  readonly active: AdjustQueueEntry | null;
  readonly busy: boolean;

  readonly cumulativeDeg: number | null;
  readonly onRotate: (stepDeg: number) => void;
  readonly onResetRotation: () => void;

  readonly trenchArmed: boolean;
  readonly onArmTrench: () => void;

  readonly diameterMm: number;
  readonly onChangeDiameter: (mm: number) => void;
  readonly onBestFit: (apply: boolean) => void;
  readonly pass: AlreadyOptimal | null;

  readonly drafts: readonly PairDraft[];
  readonly pose: { readonly origin: readonly number[]; readonly axis: readonly number[] } | null;
  readonly clock: ClockReferenceLike | null;
  readonly onStartPair: (span: boolean, partSpan?: boolean) => void;
  readonly onRemovePair: (id: string) => void;
  readonly onRemovePoint: (id: string, slot: PairSlotKey) => void;
  /** THE SPLIT AFFORDANCE'S ACT (client live-testing 2026-08-09) — see `PairsList`'s
   *  own doc. Required, like its siblings above: an omitted callback here would
   *  silently ship a button that clicks to nothing. */
  readonly onReplacePair: (id: string, replacements: readonly PairDraft[]) => void;
  readonly onApplyPairs: () => void;
  readonly onClearPairs: () => void;
  readonly ghostsActive: boolean;

  readonly autoMarkLandmarks: readonly LandmarkView[];
  readonly autoMarkPhase: SeatedPhase;
  readonly autoMarkError: string | null;

  readonly refusal: string | null;
  readonly lastOutcome: AdjustOutcomeView | null;

  readonly activeStatus: string | null;
  readonly onReconfirm: () => void;
  readonly reconfirmSaving: boolean;
  readonly reconfirmError: string | null;
  readonly seatedPhase: SeatedPhase;
  readonly seatedPayloadPresent: boolean;

  readonly receiptsCarried: boolean;

  readonly onRePreview: () => void;
  readonly rePreviewResult: RePreviewView | null;
  readonly rePreviewWorking: boolean;
  readonly rePreviewError: string | null;

  readonly onAcknowledgeException: (tooth: number, give: boolean) => void;
  readonly acknowledgeSaving: boolean;
  readonly acknowledgeError: string | null;

  readonly onDrop: (tooth: number, withhold: boolean) => void;
  readonly dropSaving: boolean;
  readonly dropError: string | null;

  readonly relief: {
    readonly siteValue: number | null;
    readonly caseValue: number | null;
    readonly ceilingLine: string | null;
    readonly runDone: boolean;
    readonly saving: boolean;
    readonly error: string | null;
    readonly onApply: (value: number | null) => void;
  } | null;

  /**
   * THE DOCK-HEIGHT TOGGLE, LIFTED (§10-AN slice C). "more room" used to be state
   * this component kept to itself — but the comp's own `dockTall` ALSO caps the pane
   * grid (comp-delta's `paneGridStyle`), and the pane grid lives one level up in
   * AdjustStageView. Controlled from there now (mirroring the switch-confirm/
   * reasons-dialog precedent: a data-driven toggle is a prop, not local state, so the
   * one value drives both the dock's own max-height AND the pane grid's).
   */
  readonly dockTall: boolean;
  readonly onToggleDockTall: () => void;

  /**
   * THE PAIR-CAUTION MODAL (§10-AN slice C, client 2026-08-06: "any warnings ...
   * need to come in as modals"). Also lifted, for the same testability reason —
   * a static render can pin the dialog open via this prop, exactly like
   * `reasonsFor`/`pendingSwitch` elsewhere on this app.
   */
  readonly cautionsOpen: boolean;
  readonly onOpenCautions: () => void;
  readonly onCloseCautions: () => void;

  /**
   * THE UNVERIFIED CLOCK'S ACTIONABLE SURFACE, FOLDED IN (§10-AN slice D, client
   * screenshots: at a short window the standing inline band pushed the page back
   * into scroll). Null unless the active site's run row carries
   * `clocking.rotation_unverified === true` (`domain/adjust.unverifiedClockNotice`
   * — the container computes it from the SAME rows the toolbar and the queue's
   * flag reasons already read; this component decides nothing about when it
   * applies). It used to stand between the panes and the dock as its own band;
   * now it is ONE MORE entry in the caution chip's count and its dialog, with the
   * SAME sentences (`.facts`/`.act`, verbatim, no longer behind their own nested
   * `<details>` — the modal already has the room) and the SAME act, wired through
   * the `onSelectTool` this component already owns. Optional with a null default:
   * static callers predate it.
   */
  readonly clockNotice?: UnverifiedClockNotice | null;
}

export function AdjustDock({
  tool,
  onSelectTool,
  active,
  busy,
  cumulativeDeg,
  onRotate,
  onResetRotation,
  trenchArmed,
  onArmTrench,
  diameterMm,
  onChangeDiameter,
  onBestFit,
  pass,
  drafts,
  pose,
  clock,
  onStartPair,
  onRemovePair,
  onRemovePoint,
  onReplacePair,
  onApplyPairs,
  onClearPairs,
  ghostsActive,
  autoMarkLandmarks,
  autoMarkPhase,
  autoMarkError,
  refusal,
  lastOutcome,
  activeStatus,
  onReconfirm,
  reconfirmSaving,
  reconfirmError,
  seatedPhase,
  seatedPayloadPresent,
  receiptsCarried,
  onRePreview,
  rePreviewResult,
  rePreviewWorking,
  rePreviewError,
  onAcknowledgeException,
  acknowledgeSaving,
  acknowledgeError,
  onDrop,
  dropSaving,
  dropError,
  relief,
  dockTall,
  onToggleDockTall,
  cautionsOpen,
  onOpenCautions,
  onCloseCautions,
  clockNotice = null,
}: AdjustDockProps) {
  // §10-AN slice C: "more room" is now LIFTED (AdjustDockProps' own doc explains
  // why) — the pane-grid coupling the comp's own `dockTall` also drives is wired at
  // AdjustStageView, where the pane grid lives. This file only reads the value.
  const cautions = pairCautions(drafts, pose, clock);
  // §10-AN slice D: the unverified-clock notice folds into the SAME chip/dialog —
  // one more entry, counted, never a second surface with its own open/close state.
  const cautionCount = cautions.length + (clockNotice !== null ? 1 : 0);
  // Escape closes the pair-caution dialog; focus moves in, is trapped, and comes
  // back on close (§10-O.8) — see useDialogFocus.
  useDialogEscape(cautionsOpen, onCloseCautions);
  const cautionsDialogRef = useRef<HTMLElement | null>(null);
  useDialogFocus(cautionsOpen, cautionsDialogRef);

  // THE TOOL-REFUSAL MODAL (§10-AN slice C). `dismissedRefusal` is the LAST refusal
  // text the operator closed; the modal is open whenever the CURRENT refusal differs
  // from it — which is true the instant a NEW refusal lands (no effect needed: this
  // is a plain render-time comparison, so a static render pins the dialog open just
  // by setting `refusal`, the switch-confirm/reasons-dialog precedent applied to a
  // value this component already owns rather than one lifted for the purpose). The
  // inline `tool-refusal` region below stays too (§10-AN's own ask: "keep the inline
  // region as the persistent record") — closing the modal never removes it.
  const [dismissedRefusal, setDismissedRefusal] = useState<string | null>(null);
  const refusalModalOpen = refusal !== null && refusal !== dismissedRefusal;
  useDialogEscape(refusalModalOpen, () => setDismissedRefusal(refusal));
  const refusalDialogRef = useRef<HTMLElement | null>(null);
  useDialogFocus(refusalModalOpen, refusalDialogRef);

  const notchShiftDeg =
    typeof lastOutcome?.clocking?.["notch_shift_deg"] === "number"
      ? (lastOutcome.clocking["notch_shift_deg"] as number)
      : null;
  const reconfirm = reconfirmControl(activeStatus, seatedPhase, seatedPayloadPresent);
  const exceptionWords = flaggedExceptionWords(activeStatus);
  const reworkNote = lastOutcome !== null ? reworkWords(lastOutcome) : null;
  // THE SPLIT TOOL'S POINTER (client live-testing 2026-08-09), folded into the
  // post-422 recovery note below — see `spanSplitRecoveryHint`'s own doc for why
  // this is null (and says nothing) unless the split button is actually on screen.
  const splitHint = spanSplitRecoveryHint(drafts);

  const good = (id: AdjustToolId) =>
    dockToolGood(id, {
      offDeg: rotationOffTrenchDeg(0, notchShiftDeg),
      bestFitPass: pass !== null,
      drafts,
      landmarksCount: autoMarkLandmarks.length,
    });

  const activeInfo = ADJUST_DOCK_TOOLS.find((t) => t.id === tool)!;
  const stateWords = (() => {
    if (active === null) return "—";
    switch (tool) {
      case "rotation":
        return rotationToolStateWords(0, notchShiftDeg);
      case "mark-trench":
        return trenchToolStateWords(notchShiftDeg);
      case "best-fit":
        return bestFitToolStateWords(
          diameterMm,
          pass !== null ? pass.suggestedDiameterMm : null,
        );
      case "fit-by-points":
        return pairCountHeaderWords(drafts);
      case "auto-mark":
        return autoMarkToolStateWords(drafts, autoMarkLandmarks);
    }
  })();

  return (
    <div
      data-role="adjust-dock"
      className={`adjust-dock${dockTall ? " adjust-dock--tall" : ""}`}
    >
      <div className="adjust-dock__header">
        <div data-role="tool-tabs" role="tablist" aria-label="Correction tools"
             className="adjust-dock__rail">
          {ADJUST_DOCK_TOOLS.map((info) => (
            <button
              key={info.id}
              type="button"
              role="tab"
              data-role="tool-tab"
              data-tool={info.id}
              aria-selected={tool === info.id}
              title={info.tooltip}
              className={`adjust-dock__chip${
                tool === info.id ? " adjust-dock__chip--active" : ""
              }${good(info.id) ? " adjust-dock__chip--good" : ""}`}
              onClick={() => onSelectTool(info.id)}
            >
              <span aria-hidden="true">{info.glyph}</span>
              <span className="sr-only">{info.label}</span>
            </button>
          ))}
        </div>
        <div className="adjust-dock__title">
          <strong data-role="dock-tool-title" className="adjust-dock__tool-title">
            {activeInfo.label}
          </strong>
          <span
            data-role="dock-tool-state"
            className={`adjust-dock__tool-state${
              active !== null && good(tool) ? " adjust-dock__tool-state--good" : ""
            }`}
          >
            {stateWords}
          </span>
        </div>
        {cautionCount > 0 && (
          /* THE CAUTION CHIP (§10-AN slice C, client 2026-08-06: "any warnings or
             things of the sort need to come in as modals"). Replaces the inline
             cross-check advisory and the per-pair screw-access sentence, which
             together were the exact "lot of yellow text" the 2026-08-06 shortening
             had already trimmed once — this trims the CONTROL ROW, not the words:
             every sentence still renders, verbatim, in the dialog below.

             §10-AN slice D folds the unverified-clock notice into the SAME count —
             the count is `cautionCount`, not `cautions.length`, so the chip never
             under-reports while a standing clock caution is the ONLY thing to say. */
          <button
            type="button"
            data-role="pair-caution-chip"
            className="chip chip--exception caution-chip"
            onClick={onOpenCautions}
          >
            ⚠ {cautionCount === 1 ? "1 caution" : `${cautionCount} cautions`}
          </button>
        )}
        <button
          type="button"
          data-role="dock-more-room"
          aria-pressed={dockTall}
          className="adjust-dock__more"
          onClick={onToggleDockTall}
        >
          {dockTall ? "less room" : "more room"}
        </button>
      </div>

      <div data-role="tool-body" data-tool={tool} className="adjust-dock__body">
        {active === null ? (
          <p data-role="tool-blocked" className="panel__hint">
            Pick a site in the queue — the tools act on one site's fit.
          </p>
        ) : (
          <div className="adjust-tool">
            {tool === "rotation" && (
              <RotationWidget
                cumulativeDeg={cumulativeDeg}
                notchShiftDeg={notchShiftDeg}
                busy={busy}
                onRotate={onRotate}
                onResetRotation={onResetRotation}
              />
            )}
            {tool === "mark-trench" && (
              <MarkTrenchWidget
                notchShiftDeg={notchShiftDeg}
                busy={busy}
                onRotate={onRotate}
                trenchArmed={trenchArmed}
                onArmTrench={onArmTrench}
              />
            )}
            {tool === "best-fit" && (
              <BestFitWidget
                diameterMm={diameterMm}
                onChangeDiameter={onChangeDiameter}
                onBestFit={onBestFit}
                pass={pass}
                busy={busy}
              />
            )}
            {tool === "fit-by-points" && (
              <FitByPointsWidget
                drafts={drafts}
                busy={busy}
                pose={pose}
                clock={clock}
                onStartPair={onStartPair}
                onRemovePair={onRemovePair}
                onRemovePoint={onRemovePoint}
                onReplacePair={onReplacePair}
                onApplyPairs={onApplyPairs}
                onClearPairs={onClearPairs}
                ghostsActive={ghostsActive}
                residualRmsMm={lastOutcome?.residual_rms_mm ?? null}
                crossChecked={lastOutcome?.cross_checked ?? null}
              />
            )}
            {tool === "auto-mark" && (
              <AutoMarkWidget
                autoMarkLandmarks={autoMarkLandmarks}
                autoMarkPhase={autoMarkPhase}
                autoMarkError={autoMarkError}
                drafts={drafts}
                busy={busy}
                pose={pose}
                clock={clock}
                onRemovePair={onRemovePair}
                onRemovePoint={onRemovePoint}
                onReplacePair={onReplacePair}
                onApplyPairs={onApplyPairs}
                onClearPairs={onClearPairs}
                ghostsActive={ghostsActive}
                residualRmsMm={lastOutcome?.residual_rms_mm ?? null}
                crossChecked={lastOutcome?.cross_checked ?? null}
              />
            )}
          </div>
        )}

        {busy && (
          <div data-role="tool-busy" className="busy-state" role="status">
            <span className="busy-state__spinner" aria-hidden="true" />
            <span>
              Judging the proposal — the same gates that judged the automation…
            </span>
          </div>
        )}

        {pass !== null && (
          <div data-role="best-fit-pass" className="adjust-pass" role="status">
            <strong className="adjust-pass__title">Nothing to correct.</strong>
            <p className="adjust-pass__detail">{pass.message}</p>
            {pass.canWiden && (
              <button
                type="button"
                data-role="widen-search"
                className="button button--ghost button--small"
                disabled={busy}
                onClick={() => {
                  onChangeDiameter(pass.suggestedDiameterMm);
                  onBestFit(false);
                }}
              >
                Widen to Ø{pass.suggestedDiameterMm.toFixed(2)} mm and look again
              </button>
            )}
          </div>
        )}

        {refusal !== null && (
          <div data-role="tool-refusal" role="alert" className="run-refusal">
            <strong className="run-refusal__title">The adjustment was refused.</strong>
            <p className="run-refusal__detail">{refusal}</p>
            <p className="run-refusal__next">
              Nothing changed — the fit on screen is the one that passed the gates.
              Your marks are still placed: undo just the one the message names and
              re-place it, rather than starting the pair again.
              {splitHint !== null && (
                <span data-role="split-hint"> {splitHint}</span>
              )}
            </p>
          </div>
        )}

        {lastOutcome !== null && refusal === null && pass === null && (
          <div data-role="tool-outcome" className="adjust-outcome" role="status">
            <p className="adjust-outcome__detail">{outcomeWords(lastOutcome)}</p>
            {lastOutcome.pairs.length > 0 && (
              <ul data-role="observation-list" className="adjust-outcome__pairs">
                {lastOutcome.pairs.map((row, i) => (
                  <li key={i} className="adjust-outcome__pair">
                    {observationWords(row)}
                  </li>
                ))}
              </ul>
            )}
            {lastOutcome.applied && activeStatus !== null && !reconfirm.offered && (
              <p data-role="reconfirm-done" className="adjust-outcome__confirmed">
                Confirmed. This site is ready again, and the confirmation now
                describes the fit on screen.
              </p>
            )}
            {reworkNote !== null && (
              <p data-role="rework-note" className="adjust-outcome__note">
                {reworkNote}
              </p>
            )}
          </div>
        )}

        {reconfirm.offered && (
          <div data-role="reconfirm" className="adjust-reconfirm">
            <p data-role="reconfirm-note" className="adjust-outcome__note">
              This site's fit moved, so its earlier confirmation no longer
              describes it — confirm it again over the panes on the right.
            </p>
            <button
              type="button"
              data-role="reconfirm-tick"
              className="button button--primary"
              disabled={reconfirmSaving || !reconfirm.enabled}
              title={reconfirm.reason ?? undefined}
              onClick={onReconfirm}
            >
              {reconfirmSaving
                ? "Recording the confirmation…"
                : "Confirm this fit over the panes"}
            </button>
            {reconfirm.reason !== null && (
              <p data-role="reconfirm-blocked" className="adjust-outcome__note">
                {reconfirm.reason}
              </p>
            )}
            {reconfirmError !== null && (
              <span data-role="reconfirm-error" role="alert" className="panel__error">
                {reconfirmError}
              </span>
            )}
          </div>
        )}

        {exceptionWords !== null && (
          <p data-role="flagged-exception" className="adjust-exception">
            {exceptionWords}
          </p>
        )}

        {active !== null && active.receipts.length > 0 && (
          <div data-role="evidence-receipts" className="adjust-receipts">
            <h4 className="adjust-receipts__title">
              {evidenceReceiptsTitle(receiptsCarried)}
            </h4>
            <ul className="adjust-receipts__list">
              {active.receipts.map((receipt, index) => (
                <li
                  key={`${receipt.kind}-${receipt.appliedAt ?? index}`}
                  data-role="evidence-receipt"
                  data-outcome={receipt.outcome}
                  className="adjust-receipts__item"
                >
                  <strong className="adjust-receipts__verdict">
                    {receiptKindWords(receipt.kind)} —{" "}
                    {receiptOutcomeWords(receipt.outcome)}.
                  </strong>{" "}
                  {receipt.detail}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {active !== null && (
        <div data-role="drawer-acts" className="drawer-acts adjust-dock__footer">
          <div className="adjust-reread">
            <button
              type="button"
              data-role="re-preview"
              className="button button--primary button--small"
              disabled={busy || rePreviewWorking || seatedPhase === "loading"}
              onClick={onRePreview}
            >
              {rePreviewWorking ? "Re-reading this site's numbers…" : rePreviewButtonLabel()}
            </button>
            {rePreviewError !== null ? (
              <div data-role="re-preview-error" role="alert" className="run-refusal">
                <strong className="run-refusal__title">
                  The re-read did not reach an outcome.
                </strong>
                <p className="run-refusal__detail">{rePreviewError}</p>
              </div>
            ) : (
              rePreviewResult !== null && (
                <div data-role="re-preview-result" role="status" className="adjust-outcome">
                  <p className="adjust-outcome__detail">
                    {rePreviewWords(rePreviewResult)}
                  </p>
                  {rePreviewRows(rePreviewResult).length > 0 && (
                    <ul data-role="re-preview-rows" className="adjust-outcome__pairs">
                      {rePreviewRows(rePreviewResult).map((row) => (
                        <li
                          key={row.key}
                          data-role="re-preview-row"
                          data-metric={row.key}
                          className="adjust-outcome__pair"
                        >
                          {row.label}: {row.previous ?? "—"} → {row.rederived ?? "—"}
                        </li>
                      ))}
                    </ul>
                  )}
                  {staleMetricsPhrase(rePreviewResult.stale_metrics) !== null && (
                    <p data-role="re-preview-stale" className="adjust-outcome__note">
                      Still carries {staleMetricsPhrase(rePreviewResult.stale_metrics)}{" "}
                      from before this read — a re-read cannot derive it; only a
                      full run can.
                    </p>
                  )}
                </div>
              )
            )}
          </div>
          {acceptExceptionOffer(active) !== null && (
            <button
              type="button"
              data-role="accept-exception"
              aria-pressed={active.exceptionAcknowledged}
              className="button button--amber button--small"
              disabled={acknowledgeSaving}
              title={acceptExceptionOffer(active)!.title}
              onClick={() =>
                onAcknowledgeException(active.tooth, !active.exceptionAcknowledged)
              }
            >
              {acknowledgeSaving
                ? "Recording the draft…"
                : acceptExceptionOffer(active)!.label}
            </button>
          )}
          <button
            type="button"
            data-role="drop-site"
            data-dropped={active.dropped}
            className={`button button--small ${
              active.dropped ? "button--secondary" : "button--ghost"
            }`}
            disabled={dropSaving}
            title={dropNote(active.dropped)}
            onClick={() => onDrop(active.tooth, !active.dropped)}
          >
            {dropSaving ? "Recording the decision…" : dropLabel(active.dropped)}
          </button>
        </div>
      )}
      {active !== null && relief !== null && (
        <SiteReliefControl
          siteValue={relief.siteValue}
          caseValue={relief.caseValue}
          ceilingLine={relief.ceilingLine}
          runDone={relief.runDone}
          saving={relief.saving}
          error={relief.error}
          onApply={relief.onApply}
        />
      )}
      {active !== null && (
        <div data-role="drop" className="adjust-drop">
          {active.dropped && (
            <p data-role="drop-note" className="adjust-drop__note">
              {dropNote(active.dropped)}
            </p>
          )}
          {acknowledgeError !== null && (
            <span data-role="acknowledge-error" role="alert" className="panel__error">
              {acknowledgeError}
            </span>
          )}
          {dropError !== null && (
            <span data-role="drop-error" role="alert" className="panel__error">
              {dropError}
            </span>
          )}
        </div>
      )}
      {/* THE PAIR-CAUTION MODAL (§10-AN slice C). Same decode-dialog chrome as every
          other dialog this app has — scrim, role="dialog", escape + focus trap —
          listing `pairCautions`' sentences VERBATIM, nothing folded or shortened. */}
      {cautionsOpen && (
        <div
          data-role="pair-cautions-backdrop"
          className="decode-dialog-backdrop"
          onClick={onCloseCautions}
        >
          <section
            ref={cautionsDialogRef}
            data-role="pair-cautions-dialog"
            className="decode-dialog decode-dialog--narrow"
            role="dialog"
            aria-modal="true"
            aria-labelledby="pair-cautions-heading"
            tabIndex={-1}
            onClick={(event) => event.stopPropagation()}
          >
            <header className="decode-dialog__header">
              <div>
                <h2 id="pair-cautions-heading" className="decode-dialog__title">
                  {cautionCount === 1 ? "1 caution" : `${cautionCount} cautions`}
                </h2>
                <p className="decode-dialog__subject">
                  The server's own words. Nothing here is a summary of them.
                </p>
              </div>
              <button
                type="button"
                data-role="pair-cautions-close"
                data-autofocus=""
                className="button button--ghost button--small"
                onClick={onCloseCautions}
              >
                Close
              </button>
            </header>
            <div className="decode-dialog__body">
              <ul data-role="pair-caution-list" className="adjust-queue__reasons">
                {clockNotice !== null && (
                  /* THE UNVERIFIED CLOCK, FOLDED IN (§10-AN slice D). Same three
                     things the standing band used to carry — the lead, the run's
                     own evidence word (`.facts`), and the documented answer
                     (`.act`) — now inside the ONE caution surface, with NO nested
                     `<details>`: the modal already has the room a control row does
                     not (`pairCautions`' own doctrine, applied here too). The act
                     stays a live control, not a sentence: it routes to auto-mark
                     through the SAME `onSelectTool` the rail uses, and never
                     claims the click will verify anything (`unverifiedClockNotice`'s
                     own doctrine — this file adds no claim of its own). */
                  <li
                    key="clock-caution"
                    data-role="clock-caution"
                    className="adjust-queue__reason adjust-queue__reason--clock"
                  >
                    <p
                      data-role="clock-caution-lead"
                      className="adjust-clock-notice__lead"
                    >
                      {unverifiedClockCautionLead()}
                    </p>
                    <p
                      data-role="clock-caution-facts"
                      className="adjust-clock-notice__line"
                    >
                      {clockNotice.facts}
                    </p>
                    <p
                      data-role="clock-caution-act"
                      className="adjust-clock-notice__line"
                    >
                      {clockNotice.act}
                    </p>
                    <button
                      type="button"
                      data-role="verify-rotation"
                      className="button button--secondary button--small"
                      onClick={() => onSelectTool(clockNotice.armTool)}
                    >
                      Switch to auto-mark
                    </button>
                  </li>
                )}
                {cautions.map((caution) => (
                  <li key={caution.id} className="adjust-queue__reason">
                    {caution.message}
                  </li>
                ))}
              </ul>
            </div>
          </section>
        </div>
      )}
      {/* THE TOOL-REFUSAL MODAL (§10-AN slice C, client 2026-08-06: "any warnings or
          things of the sort need to come in as modals"). role="alertdialog": unlike
          the caution chip above, a refusal was not asked for — it is the answer to
          the act the operator just took, so it opens itself. The inline
          `tool-refusal` region above stays as the persistent record; dismissing this
          only closes the modal. */}
      {refusalModalOpen && (
        <div
          data-role="tool-refusal-backdrop"
          className="decode-dialog-backdrop"
          onClick={() => setDismissedRefusal(refusal)}
        >
          <section
            ref={refusalDialogRef}
            data-role="tool-refusal-dialog"
            className="decode-dialog decode-dialog--narrow"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="tool-refusal-heading"
            tabIndex={-1}
            onClick={(event) => event.stopPropagation()}
          >
            <header className="decode-dialog__header">
              <div>
                <h2 id="tool-refusal-heading" className="decode-dialog__title">
                  The adjustment was refused.
                </h2>
              </div>
              <button
                type="button"
                data-role="tool-refusal-close"
                data-autofocus=""
                className="button button--ghost button--small"
                onClick={() => setDismissedRefusal(refusal)}
              >
                Close
              </button>
            </header>
            <div className="decode-dialog__body">
              <p className="run-refusal__detail">{refusal}</p>
              <p className="run-refusal__next">
                Nothing changed — the fit on screen is the one that passed the gates.
                Your marks are still placed: undo just the one the message names and
                re-place it, rather than starting the pair again.
                {splitHint !== null && (
                  <span data-role="split-hint"> {splitHint}</span>
                )}
              </p>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
