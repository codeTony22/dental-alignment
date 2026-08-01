/**
 * INTAKE (plan §4, §7 slice 4): the case opens HERE. Detection fires automatically
 * (once — keyed on session facts, domain/intake.shouldAutoDetect); capture-gate
 * verdicts surface BEFORE any work is invested — a rescan-grade verdict is a banner,
 * the chair-side moment; everything else is a per-site chip. The case-level choices
 * (construction part, jaw, gingival relief beside its ceiling) live in the panel.
 *
 * Direction of trust (AM-4): every mutation renders WHAT THE BFF RETURNS — optimistic
 * updates are deliberately absent. A PUT that the BFF refuses shows the refusal in the
 * backend's own words and the panel keeps showing the persisted state, not the wish.
 *
 * The banner and chips are REIMPLEMENTED small against the worker's verdict vocabulary
 * — not copied from the demo's JSX (the copy-debt ledger rule: this is product chrome,
 * not viewer physics).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  postDetect,
  postMarkedSite,
  putChoices,
  type CaseSessionDetail,
  type ChoicesUpdate,
} from "../api/client";
import { blockedReason, factsFromCaseSession, isReachable } from "../domain/flow";
import {
  captureChipLabel,
  ceilingReadouts,
  choicesUpdateFrom,
  constructionOptions,
  detectionMarkers,
  EMPTY_MARK,
  markOnArmMark,
  markOnArmPick,
  pickSiteAt,
  rescanNotices,
  shouldAutoDetect,
  siteCentre,
  siteEvidence,
  SITE_PICK_RADIUS_MM,
  type MarkDraft,
  OFF_SCAN_MISS_WORDS,
} from "../domain/intake";
import { MainStage } from "./MainStage";

/** Detection's honest lifecycle on this mount — never a spinner over a lie. */
export type DetectPhase =
  | { readonly kind: "idle" }
  | { readonly kind: "detecting" }
  | { readonly kind: "failed"; readonly detail: string };

const JAW_CHOICES = ["upper", "lower"] as const;

interface CaptureBannerProps {
  readonly detail: CaseSessionDetail;
}

/** The chair-side moment: rescan-grade verdicts, surfaced before any work — in the
 * demo's red capture-banner language (a refused capture, not merely stale results). */
function CaptureBanner({ detail }: CaptureBannerProps) {
  const notices = rescanNotices(detail);
  if (notices.length === 0) return null;
  return (
    <div data-role="capture-banner" role="alert" className="capture-banner">
      <p className="capture-banner__title">
        Rescan recommended — the capture gate found problems before any work was
        invested.
      </p>
      <p className="capture-banner__item">
        If the patient is still in the chair, rescanning now costs minutes; marks placed
        on this capture would be wasted.
      </p>
      <ul className="capture-banner__list">
        {notices.map((notice, index) => (
          <li key={index} className="capture-banner__item">
            <strong>{notice.label}:</strong> {notice.message}
          </li>
        ))}
      </ul>
    </div>
  );
}

interface SiteListProps {
  readonly detail: CaseSessionDetail;
  /** The site the operator picked — the stage frames it. Null = the stage's own default. */
  readonly activeTooth: number | null;
  readonly onSelectSite: (tooth: number) => void;
  readonly pickArmed: boolean;
  readonly pickMiss: string | null;
  readonly onArmPick: () => void;
  readonly onCancelPick: () => void;
}

/** The chip's demo clothes: pass/marginal/rescan traffic-light tones, muted "none". */
function captureChipClass(verdict: string | null): string {
  return verdict === null
    ? "chip chip--capture-none"
    : `chip chip--capture-${verdict}`;
}

/**
 * The site queue's Intake face: tooth, status, the SERVER's evidence for this site,
 * capture chip — the demo's stepper list language.
 *
 * No longer read-only (client 2026-07-31): a row is the operator's pick, and the pick
 * is what the 3D stage frames. The row carries no confidence percentage even though
 * the design prototype has one — see domain/intake.siteEvidence for why there is no
 * such number to render.
 */
function SiteList({
  detail,
  activeTooth,
  onSelectSite,
  pickArmed,
  pickMiss,
  onArmPick,
  onCancelPick,
}: SiteListProps) {
  const unassigned =
    detail.detection?.proposals.filter((p) => p.tooth_guess === null).length ?? 0;
  const active = detail.sites.find((s) => s.tooth === activeTooth) ?? null;
  return (
    <section data-role="intake-sites" className="panel">
      <h3 className="panel__title">Sites</h3>
      <ul className="decode-stepper__overview">
        {detail.sites.map((site) => (
          <li key={site.tooth} className="intake-site">
            <button
              type="button"
              data-role="site-row"
              data-tooth={site.tooth}
              aria-pressed={site.tooth === activeTooth}
              className={`decode-stepper__item intake-site__row${
                site.tooth === activeTooth ? " decode-stepper__item--active" : ""
              }`}
              title="Frame this site on the scan"
              onClick={() => onSelectSite(site.tooth)}
            >
              <span className="decode-stepper__position">
                Tooth {site.tooth}{" "}
                <span className="decode-stepper__tooth">{site.status}</span>
              </span>
              <span data-role="site-evidence" className="intake-site__evidence">
                {siteEvidence(detail, site).map((fact) => (
                  <span
                    key={fact.key}
                    data-fact={fact.key}
                    className="intake-site__fact"
                    title={fact.title}
                  >
                    {fact.text}
                  </span>
                ))}
              </span>
              <span
                data-role="capture-chip"
                data-verdict={site.capture?.verdict ?? "none"}
                className={captureChipClass(site.capture?.verdict ?? null)}
                title={site.capture?.checks.map((c) => c.message).join(" ") ?? undefined}
              >
                {captureChipLabel(site.capture)}
              </span>
            </button>
          </li>
        ))}
      </ul>
      {active !== null && (
        <p data-role="site-framed" className="panel__hint">
          {siteCentre(active) !== null
            ? `Tooth ${active.tooth} is framed on the scan.`
            : `Tooth ${active.tooth} has no centre yet — the stage cannot frame it.`}
        </p>
      )}
      {/* The other direction of the same pick: point at the cap instead of reading the
          list. The stage's one-shot point pick resolves it (MainStage's markArmed door),
          and domain/intake.pickSiteAt turns the surface point into a tooth. */}
      {pickArmed ? (
        <p data-role="pick-prompt" className="panel__hint">
          Click a cap on the scan to select its site.{" "}
          <button
            type="button"
            data-role="pick-cancel"
            className="button button--ghost button--small"
            onClick={onCancelPick}
          >
            Cancel
          </button>
        </p>
      ) : (
        <div className="panel__actions">
          <button
            type="button"
            data-role="pick-arm"
            className="button button--secondary button--small"
            onClick={onArmPick}
          >
            Pick a site on the scan
          </button>
        </div>
      )}
      {pickMiss !== null && (
        <p data-role="pick-miss" className="panel__hint intake-site__miss">
          {pickMiss}
        </p>
      )}
      {unassigned > 0 && (
        <p data-role="unassigned-proposals" className="panel__hint">
          {unassigned} detected site{unassigned === 1 ? "" : "s"} without a curated
          tooth yet — Declare assigns teeth.
        </p>
      )}
    </section>
  );
}

export interface ChoicesPanelProps {
  readonly detail: CaseSessionDetail;
  readonly saving: boolean;
  readonly error: string | null;
  readonly onChoice: (patch: Partial<ChoicesUpdate>) => void;
}

/** The prefilled-choice chip (client 2026-07-27): the SERVER's attribution, worn
 * exactly like the system bar's "suggested" tag — "suggested" on a fallback the
 * case supplied, "default" on the standing relief. An operator's chosen value
 * carries no chip, and "none" has no value to tag. */
function ChoiceSourceChip({
  source,
  choice,
}: {
  readonly source: "chosen" | "suggested" | "default" | "none";
  readonly choice: string;
}) {
  if (source === "chosen" || source === "none") return null;
  return (
    <span
      data-role="choice-source"
      data-choice={choice}
      className="library-badge library-badge--suggested"
    >
      {source}
    </span>
  );
}

/** The case-level choices — rendered from the BFF's EFFECTIVE values (client
 * 2026-07-27: the same chosen-??-suggested-??-default document the previews seat
 * with, each with its source chip), PUT whole on every change — the operator
 * changes them by the existing PUT; nothing here auto-writes a default. Parity
 * slice: the demo's selection-card language — the decode select, the Upper/Lower
 * pair, the relief input beside its measured ceilings with the amber
 * over-ceiling tone. */
export function ChoicesPanel({ detail, saving, error, onChoice }: ChoicesPanelProps) {
  const chosen = detail.choices;
  const construction = chosen.effective_construction.value ?? "";
  const jaw = chosen.effective_jaw.value;
  const relief = chosen.effective_relief.value ?? chosen.gingival_offset_default_mm;
  return (
    <section data-role="intake-choices" className="panel">
      <h3 className="panel__title">Case-level choices</h3>
      <div className="decode-column">
        <div>
          <h4 className="decode-section__title">
            Construction part
            <ChoiceSourceChip
              source={chosen.effective_construction.source}
              choice="construction"
            />
          </h4>
          <select
            data-role="choice-construction"
            className={`decode-select${construction === "" ? " decode-select--needs" : ""}`}
            value={construction}
            onChange={(event) =>
              onChoice({ construction_path: event.target.value || null })
            }
          >
            <option value="">choose a construction part…</option>
            {constructionOptions(detail).map((option) => (
              <option key={option.path_id} value={option.path_id}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <h4 className="decode-section__title">
            Jaw
            <ChoiceSourceChip source={chosen.effective_jaw.source} choice="jaw" />
          </h4>
          <div data-role="choice-jaw" className="decode-jaw" role="group" aria-label="Jaw">
            {JAW_CHOICES.map((candidate) => (
              <button
                key={candidate}
                type="button"
                aria-pressed={candidate === jaw}
                className={`decode-jaw__option${
                  candidate === jaw ? " decode-jaw__option--selected" : ""
                }`}
                onClick={() => onChoice({ jaw: candidate })}
              >
                {candidate}
              </button>
            ))}
          </div>
        </div>
        <div>
          <h4 className="decode-section__title">
            Gingival relief
            <ChoiceSourceChip source={chosen.effective_relief.source} choice="relief" />
          </h4>
          <label className="decode-offset">
            <input
              data-role="choice-relief"
              className="decode-offset__input"
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={relief}
              onChange={(event) => {
                const parsed = Number(event.target.value);
                onChoice({
                  gingival_offset_mm: Number.isFinite(parsed) ? parsed : null,
                });
              }}
            />
            <span className="decode-offset__unit">mm</span>
          </label>
          <ul data-role="relief-ceilings" className="relief-ceilings">
            {ceilingReadouts(detail, chosen.gingival_offset_mm).map((readout) => (
              <li
                key={readout.variant}
                data-exceeded={readout.exceeded}
                className="relief-ceilings__item"
              >
                {readout.line}
              </li>
            ))}
          </ul>
        </div>
      </div>
      {saving && (
        <div data-role="choices-saving" className="busy-state" role="status">
          <span className="busy-state__spinner" aria-hidden="true" />
          <span>Saving choices…</span>
        </div>
      )}
      {error !== null && (
        <div data-role="choices-error" role="alert" className="panel__error">
          {error}
        </div>
      )}
    </section>
  );
}


export interface MarkMissedCapProps {
  readonly armed: boolean;
  /** The centre placed but not yet named — a mark is only a site once it has a tooth. */
  readonly pending: readonly number[] | null;
  readonly saving: boolean;
  readonly error: string | null;
  readonly onArm: () => void;
  readonly onCancel: () => void;
  readonly onTooth: (tooth: string) => void;
  readonly tooth: string;
  readonly onSubmit: () => void;
}

/**
 * MARK A CAP THE DETECTOR MISSED (client 2026-07-28).
 *
 * Detection finds 8 of the 10 sites on this fleet. The other two were unworkable —
 * a site's centre lived only in the case record, which the ingest writes and an
 * operator cannot. This is the door.
 *
 * TWO STEPS, deliberately: place the centre, THEN name the tooth. Asking for the
 * tooth first would make the operator hold a number in their head while hunting the
 * cap in 3D; asking afterwards lets them point at what they can see and label it
 * once it is unambiguous. The centre is sent exactly as clicked — the re-click
 * pair-integrity rule says a human's mark is fixed here or refused, never quietly
 * re-centred downstream.
 */
export function MarkMissedCap({
  armed,
  pending,
  saving,
  error,
  onArm,
  onCancel,
  onTooth,
  tooth,
  onSubmit,
}: MarkMissedCapProps) {
  return (
    <section data-role="mark-missed" className="panel">
      <h3 className="panel__title">A cap the detection missed</h3>
      {!armed && pending === null ? (
        <>
          <p className="panel__hint">
            Detection does not always find every cap. If you can see one the list
            above does not have, mark it here.
          </p>
          <button
            type="button"
            data-role="mark-arm"
            className="button button--secondary button--small"
            onClick={onArm}
          >
            Mark a missed cap
          </button>
        </>
      ) : pending === null ? (
        <>
          <p data-role="mark-prompt" className="panel__hint">
            Click the centre of the cap on the scan.
          </p>
          <button
            type="button"
            data-role="mark-cancel"
            className="button button--ghost button--small"
            onClick={onCancel}
          >
            Cancel
          </button>
        </>
      ) : (
        <>
          <p data-role="mark-placed" className="panel__hint">
            Centre placed. Which tooth is it?
          </p>
          <label className="decode-offset">
            <input
              data-role="mark-tooth"
              className="decode-offset__input"
              type="number"
              min={1}
              max={32}
              value={tooth}
              onChange={(event) => onTooth(event.target.value)}
            />
          </label>
          <div className="panel__actions">
            <button
              type="button"
              data-role="mark-submit"
              className="button button--primary button--small"
              disabled={saving || tooth.trim() === ""}
              onClick={onSubmit}
            >
              {saving ? "Adding the site…" : "Add this site"}
            </button>
            <button
              type="button"
              data-role="mark-cancel"
              className="button button--ghost button--small"
              disabled={saving}
              onClick={onCancel}
            >
              Discard the mark
            </button>
          </div>
        </>
      )}
      {error !== null && (
        <div data-role="mark-error" role="alert" className="panel__error">
          {error}
        </div>
      )}
    </section>
  );
}

export interface IntakeStageViewProps {
  readonly detail: CaseSessionDetail;
  readonly detectPhase: DetectPhase;
  readonly savingChoices: boolean;
  readonly choicesError: string | null;
  readonly onChoice: (patch: Partial<ChoicesUpdate>) => void;
  readonly onRetryDetect: () => void;
  /** Marking a cap detection missed (client 2026-07-28). */
  readonly markArmed?: boolean;
  readonly markPending?: readonly number[] | null;
  readonly markTooth?: string;
  readonly markSaving?: boolean;
  readonly markError?: string | null;
  readonly onArmMark?: () => void;
  readonly onCancelMark?: () => void;
  readonly onMarkTooth?: (tooth: string) => void;
  readonly onStagePoint?: (point: readonly [number, number, number]) => void;
  /** An armed click that hit only the sky — the pick stays armed; the panel says so. */
  readonly onStageMiss?: () => void;
  readonly onSubmitMark?: () => void;
  /** Picking a site — from its row, or by clicking the cap on the scan (client 2026-07-31). */
  readonly activeTooth?: number | null;
  readonly onSelectSite?: (tooth: number) => void;
  readonly pickArmed?: boolean;
  readonly pickMiss?: string | null;
  readonly onArmPick?: () => void;
  readonly onCancelPick?: () => void;
}

/** The stage's whole surface, pure payload → markup — statically testable. */
export function IntakeStageView({
  detail,
  detectPhase,
  savingChoices,
  choicesError,
  onChoice,
  onRetryDetect,
  markArmed = false,
  markPending = null,
  markTooth = "",
  markSaving = false,
  markError = null,
  onArmMark = () => undefined,
  onCancelMark = () => undefined,
  onMarkTooth = () => undefined,
  onStagePoint = () => undefined,
  onStageMiss = () => undefined,
  onSubmitMark = () => undefined,
  activeTooth = null,
  onSelectSite = () => undefined,
  pickArmed = false,
  pickMiss = null,
  onArmPick = () => undefined,
  onCancelPick = () => undefined,
}: IntakeStageViewProps) {
  const facts = factsFromCaseSession(detail);
  const declareOpen = isReachable("declare", facts);
  return (
    // Two regions for the workbench grid (display: contents on the root): the WORK
    // column carries the panels, the STAGE keeps the 3D big — the demo's proportions.
    <div data-role="intake-stage" className="stage-contents">
      <div className="workbench__work">
        <CaptureBanner detail={detail} />
        {detectPhase.kind === "detecting" && (
          <div data-role="detect-busy" className="busy-state" role="status">
            <span className="busy-state__spinner" aria-hidden="true" />
            <span>Detecting caps…</span>
          </div>
        )}
        {detectPhase.kind === "failed" && (
          <div data-role="detect-error" role="alert" className="run-refusal">
            <strong className="run-refusal__title">Detection refused.</strong>
            <p className="run-refusal__detail">{detectPhase.detail}</p>
            <p className="run-refusal__next">
              <button
                type="button"
                className="button button--ghost button--small"
                onClick={onRetryDetect}
              >
                Try again
              </button>
            </p>
          </div>
        )}
        <SiteList
          detail={detail}
          activeTooth={activeTooth}
          onSelectSite={onSelectSite}
          pickArmed={pickArmed}
          pickMiss={pickMiss}
          onArmPick={onArmPick}
          onCancelPick={onCancelPick}
        />
        <MarkMissedCap
          armed={markArmed}
          pending={markPending}
          saving={markSaving}
          error={markError}
          onArm={onArmMark}
          onCancel={onCancelMark}
          onTooth={onMarkTooth}
          tooth={markTooth}
          onSubmit={onSubmitMark}
        />
        <ChoicesPanel
          detail={detail}
          saving={savingChoices}
          error={choicesError}
          onChoice={onChoice}
        />
        <div className="panel__actions panel__actions--advance">
          {declareOpen ? (
            <Link
              data-role="continue-declare"
              className="button button--primary"
              to={`/case/${detail.case.id}/declare`}
            >
              Continue to Declare
            </Link>
          ) : (
            <span
              data-role="continue-declare"
              aria-disabled="true"
              className="button button--secondary button--blocked"
            >
              Continue to Declare — {blockedReason("declare", facts)}
            </span>
          )}
        </div>
      </div>
      <div className="workbench__stage">
        <MainStage
          caseId={detail.case.id}
          scanFilename={detail.case.scan_filename}
          sites={detail.sites}
          markers={detectionMarkers(detail)}
          activeTooth={activeTooth}
          // ONE point-pick door, two callers (client 2026-07-31): the stage arms the
          // viewer's one-shot pick while EITHER the missed-cap mark or the site picker
          // is armed, and the container routes the resolved point to whichever asked.
          markArmed={markArmed || pickArmed}
          onMark={onStagePoint}
          onMarkMissed={onStageMiss}
        />
      </div>
    </div>
  );
}

export interface IntakeStageProps {
  readonly detail: CaseSessionDetail;
  /** The shell owns the payload; every action's response replaces it whole. */
  readonly onDetail: (next: CaseSessionDetail) => void;
}

/** The container: auto-fires detection once, wires the choices PUT, renders truth. */
export function IntakeStage({ detail, onDetail }: IntakeStageProps) {
  const caseId = detail.case.id;
  const firedRef = useRef<string | null>(null);

  /* MARKING A MISSED CAP (client 2026-07-28). Three states, and the middle one is
     the reason this is not a single form: ARMED (the next scan click is the centre),
     PLACED (a centre exists, awaiting its tooth), and idle. Optimism is OFF like
     everywhere else on this app — the site appears because the BFF returned a detail
     saying so, never because the click landed.

     ONE draft, not four useStates (audit 2026-07-31): the transitions that must not
     lose a placed centre are then named rules in domain/intake with their own tests,
     instead of four setters a caller can forget one of. `markSaving` stays separate —
     it is the request's phase, not part of what the operator drafted. */
  const [mark, setMark] = useState<MarkDraft>(EMPTY_MARK);
  const [markSaving, setMarkSaving] = useState(false);

  const resetMark = useCallback(() => setMark(EMPTY_MARK), []);

  const handleMarkPlaced = useCallback((point: readonly [number, number, number]) => {
    // the click is spent; naming the tooth comes next
    setMark((prev) => ({ ...prev, armed: false, pending: [...point] }));
  }, []);

  /* PICKING A SITE (client 2026-07-31). Purely a VIEW act — which site the stage
     frames and which row reads as chosen. Nothing here is persisted and nothing here
     is a verdict, so no PUT: the case's own facts are untouched by looking at a cap.
     The scan-side pick borrows the same one-shot point pick the missed-cap mark uses
     (the viewer arms exactly one), so the two modes are mutually exclusive by
     construction — arming either disarms the other. */
  const [activeTooth, setActiveTooth] = useState<number | null>(null);
  const [pickArmed, setPickArmed] = useState(false);
  const [pickMiss, setPickMiss] = useState<string | null>(null);

  const handleSelectSite = useCallback((tooth: number) => {
    setActiveTooth(tooth);
    setPickArmed(false);
    setPickMiss(null);
  }, []);

  const handleArmPick = useCallback(() => {
    setPickArmed(true);
    setPickMiss(null);
    // one point pick, one owner — DISARM the mark, never discard it (audit
    // 2026-07-31: this used to reset the whole draft, silently destroying a placed
    // centre the operator had hunted down in 3D). The rule lives in domain/intake.
    setMark(markOnArmPick);
  }, []);

  const handleCancelPick = useCallback(() => {
    setPickArmed(false);
    setPickMiss(null);
  }, []);

  /* The stage resolved a surface point. Whoever armed the pick owns it — the site
     picker first, because arming it disarms the mark. A click that lands on no cap is
     SAID, not snapped to the least-far site: the operator would otherwise watch the
     stage fly to a tooth they did not click. */
  /* An armed click that hit only the sky. The viewer KEEPS the pick armed (the fix
     of 2026-08-01 — before that the click vanished with the controls still off), so
     this only says it out loud, in whichever panel armed the click. */
  const handleStageMiss = useCallback(() => {
    if (pickArmed) setPickMiss(OFF_SCAN_MISS_WORDS);
    else setMark((now) => ({ ...now, error: OFF_SCAN_MISS_WORDS }));
  }, [pickArmed]);

  const handleStagePoint = useCallback(
    (point: readonly [number, number, number]) => {
      if (!pickArmed) {
        handleMarkPlaced(point);
        return;
      }
      setPickArmed(false);  // the viewer's pick is one-shot; so is this arming
      const pick = pickSiteAt(detail.sites, point);
      if (pick.kind === "miss") {
        setPickMiss(
          `No site within ${SITE_PICK_RADIUS_MM.toFixed(1)}mm of that click — ` +
            "try the centre of a cap, or pick the row instead.",
        );
        return;
      }
      if (pick.kind === "ambiguous") {
        // Said, not guessed (audit 2026-07-31): two centres can sit inside one reach,
        // and resolving by nearest would frame a tooth the operator did not click.
        setPickMiss(
          `That click is within ${SITE_PICK_RADIUS_MM.toFixed(1)}mm of ` +
            `${pick.teeth.length} sites (${pick.teeth.map((t) => `tooth ${t}`).join(", ")}) — ` +
            "click nearer the cap you mean, or pick its row.",
        );
        return;
      }
      setPickMiss(null);
      setActiveTooth(pick.tooth);
    },
    [detail.sites, handleMarkPlaced, pickArmed],
  );

  const handleSubmitMark = useCallback(() => {
    const tooth = Number(mark.tooth);
    const pending = mark.pending;
    if (pending === null || !Number.isInteger(tooth)) return;
    setMarkSaving(true);
    setMark((prev) => ({ ...prev, error: null }));
    void postMarkedSite(caseId, tooth, pending).then((result) => {
      setMarkSaving(false);
      // ApiResult is a {kind} union — same wrong-shape bug as the reconfirm handler
      // (result.ok/.value/.error exist on nothing), caught in the same sweep
      if (result.kind === "ok") {
        onDetail(result.data);
        resetMark();
        return;
      }
      // the BFF's own words — a 409 on an existing tooth explains itself better
      // than anything this layer could summarise
      setMark((prev) => ({ ...prev, error: result.detail }));
    });
  }, [caseId, mark.pending, mark.tooth, onDetail, resetMark]);
  const mountedRef = useRef(true);
  const [detectPhase, setDetectPhase] = useState<DetectPhase>({ kind: "idle" });
  const [savingChoices, setSavingChoices] = useState(false);
  const [choicesError, setChoicesError] = useState<string | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const fireDetect = useCallback(() => {
    setDetectPhase({ kind: "detecting" });
    void postDetect(caseId).then((result) => {
      if (!mountedRef.current) return;
      if (result.kind === "ok") {
        setDetectPhase({ kind: "idle" });
        onDetail(result.data);
      } else {
        setDetectPhase({ kind: "failed", detail: result.detail });
      }
    });
  }, [caseId, onDetail]);

  const detectionDone = detail.detection !== null;
  useEffect(() => {
    if (
      !shouldAutoDetect({
        caseId,
        detectionDone,
        alreadyFiredFor: firedRef.current,
      })
    ) {
      return;
    }
    firedRef.current = caseId; // marked BEFORE the async settles — one fire per case
    fireDetect();
  }, [caseId, detectionDone, fireDetect]);

  const handleChoice = useCallback(
    (patch: Partial<ChoicesUpdate>) => {
      setSavingChoices(true);
      void putChoices(caseId, choicesUpdateFrom(detail, patch)).then((result) => {
        if (!mountedRef.current) return;
        setSavingChoices(false);
        if (result.kind === "ok") {
          setChoicesError(null);
          onDetail(result.data);
        } else {
          setChoicesError(result.detail);
        }
      });
    },
    [caseId, detail, onDetail],
  );

  return (
    <IntakeStageView
      detail={detail}
      detectPhase={detectPhase}
      savingChoices={savingChoices}
      choicesError={choicesError}
      onChoice={handleChoice}
      markArmed={mark.armed}
      markPending={mark.pending}
      markTooth={mark.tooth}
      markSaving={markSaving}
      markError={mark.error}
      onArmMark={() => {
        setMark(markOnArmMark);
        setPickArmed(false); // one point pick, one owner
        setPickMiss(null);
      }}
      onCancelMark={resetMark}
      onMarkTooth={(tooth) => setMark((prev) => ({ ...prev, tooth }))}
      onStagePoint={handleStagePoint}
      onStageMiss={handleStageMiss}
      onSubmitMark={handleSubmitMark}
      onRetryDetect={fireDetect}
      activeTooth={activeTooth}
      onSelectSite={handleSelectSite}
      pickArmed={pickArmed}
      pickMiss={pickMiss}
      onArmPick={handleArmPick}
      onCancelPick={handleCancelPick}
    />
  );
}
