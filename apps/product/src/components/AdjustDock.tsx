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
  crossCheckCaution,
  crossCheckCautionDetail,
  diameterBandWords,
  dockToolGood,
  dropLabel,
  dropNote,
  evidenceReceiptsTitle,
  flaggedExceptionWords,
  isComplete,
  markLeverGuard,
  observationWords,
  outcomeWords,
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
  scatterWords,
  staleMetricsPhrase,
  trenchBand,
  trenchRingHint,
  trenchToolStateWords,
  type AdjustQueueEntry,
  type AdjustToolId,
  type AlreadyOptimal,
  type ClockReferenceLike,
  type PairDraft,
  type PairSlot as PairSlotKey,
  type SeatedPhase,
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
      {crossCheckCaution(drafts) !== null && (() => {
        const lead = crossCheckCaution(drafts)!;
        const detail = crossCheckCautionDetail(drafts);
        return (
          <div
            data-role="cross-check-caution"
            role="status"
            className="adjust-pairs__caution adjust-pairs__caution--set"
          >
            <p className="adjust-pairs__caution-lead">{lead}</p>
            {detail !== null && (
              <details data-role="cross-check-caution-fold"
                        className="adjust-pairs__caution-fold">
                <summary className="adjust-pairs__caution-summary">
                  why a span can be one observation
                </summary>
                <p className="adjust-pairs__caution-line">{detail}</p>
              </details>
            )}
          </div>
        );
      })()}
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
            {(() => {
              const guard = markLeverGuard(draft, pose, clock);
              if (guard === null) return null;
              return (
                <p
                  data-role="mark-guard"
                  data-guard={guard.kind}
                  role={guard.kind === "refusal" ? "alert" : "status"}
                  className="adjust-pairs__caution"
                >
                  {guard.message}
                </p>
              );
            })()}
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
  onApplyPairs,
  onClearPairs,
  ghostsActive,
  residualRmsMm,
}: {
  readonly drafts: readonly PairDraft[];
  readonly busy: boolean;
  readonly pose: { readonly origin: readonly number[]; readonly axis: readonly number[] } | null;
  readonly clock: ClockReferenceLike | null;
  readonly onStartPair: (span: boolean, partSpan?: boolean) => void;
  readonly onRemovePair: (id: string) => void;
  readonly onRemovePoint: (id: string, slot: PairSlotKey) => void;
  readonly onApplyPairs: () => void;
  readonly onClearPairs: () => void;
  readonly ghostsActive: boolean;
  readonly residualRmsMm: number | null;
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
        onApplyPairs={onApplyPairs}
        onClearPairs={onClearPairs}
        clearLabel="Clear all pairs"
      />
      <ScatterMeter residualRmsMm={residualRmsMm} />
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
  onApplyPairs,
  onClearPairs,
  ghostsActive,
  residualRmsMm,
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
  readonly onApplyPairs: () => void;
  readonly onClearPairs: () => void;
  readonly ghostsActive: boolean;
  readonly residualRmsMm: number | null;
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
        onApplyPairs={onApplyPairs}
        onClearPairs={onClearPairs}
        clearLabel="Start the matching over"
        sourceLabelFor={(draft) => autoMarkSourceLabel(draft, autoMarkLandmarks)}
      />
      <ScatterMeter residualRmsMm={residualRmsMm} />
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
}: AdjustDockProps) {
  // §10-AN: "more room" is LOCAL to the dock — the pane-grid coupling the comp's own
  // `dockTall` also drives (a shrinking minHeight/maxHeight on the pane grid) is
  // deliberately NOT wired here. SitePanes' grid already measures its own container
  // and a hand-tuned second coupling is exactly the class of overlap that produced
  // the Cancel/Process collision this codebase's own doctrine warns against; the
  // dock growing taller on a short viewport is a real trade-off, stated here rather
  // than hidden inside a "fixed".
  const [dockTall, setDockTall] = useState(false);

  const notchShiftDeg =
    typeof lastOutcome?.clocking?.["notch_shift_deg"] === "number"
      ? (lastOutcome.clocking["notch_shift_deg"] as number)
      : null;
  const reconfirm = reconfirmControl(activeStatus, seatedPhase, seatedPayloadPresent);
  const exceptionWords = flaggedExceptionWords(activeStatus);
  const reworkNote = lastOutcome !== null ? reworkWords(lastOutcome) : null;

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
        <button
          type="button"
          data-role="dock-more-room"
          aria-pressed={dockTall}
          className="adjust-dock__more"
          onClick={() => setDockTall((now) => !now)}
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
                onApplyPairs={onApplyPairs}
                onClearPairs={onClearPairs}
                ghostsActive={ghostsActive}
                residualRmsMm={lastOutcome?.residual_rms_mm ?? null}
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
                onApplyPairs={onApplyPairs}
                onClearPairs={onClearPairs}
                ghostsActive={ghostsActive}
                residualRmsMm={lastOutcome?.residual_rms_mm ?? null}
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
    </div>
  );
}
