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
  rescanNotices,
  shouldAutoDetect,
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
}

/** The chip's demo clothes: pass/marginal/rescan traffic-light tones, muted "none". */
function captureChipClass(verdict: string | null): string {
  return verdict === null
    ? "chip chip--capture-none"
    : `chip chip--capture-${verdict}`;
}

/** The site queue's Intake face: tooth, status, capture chip — the demo's stepper
 * list language, read-only on this stage. */
function SiteList({ detail }: SiteListProps) {
  const unassigned =
    detail.detection?.proposals.filter((p) => p.tooth_guess === null).length ?? 0;
  return (
    <section data-role="intake-sites" className="panel">
      <h3 className="panel__title">Sites</h3>
      <ul className="decode-stepper__overview">
        {detail.sites.map((site) => (
          <li key={site.tooth} className="decode-stepper__item">
            <span className="decode-stepper__position">
              Tooth {site.tooth}{" "}
              <span className="decode-stepper__tooth">{site.status}</span>
            </span>
            <span
              data-role="capture-chip"
              data-verdict={site.capture?.verdict ?? "none"}
              className={captureChipClass(site.capture?.verdict ?? null)}
              title={site.capture?.checks.map((c) => c.message).join(" ") ?? undefined}
            >
              {captureChipLabel(site.capture)}
            </span>
          </li>
        ))}
      </ul>
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

/** The case-level choices — rendered from the PERSISTED choices (pre-fills shown where
 * nothing is chosen yet), PUT whole on every change. Parity slice: the demo's
 * selection-card language — the decode select, the Upper/Lower pair, the relief input
 * beside its measured ceilings with the amber over-ceiling tone. */
export function ChoicesPanel({ detail, saving, error, onChoice }: ChoicesPanelProps) {
  const chosen = detail.choices;
  const construction =
    chosen.construction_path ?? detail.case.suggested_construction ?? "";
  const jaw = chosen.jaw ?? detail.case.jaw;
  const relief = chosen.gingival_offset_mm ?? chosen.gingival_offset_default_mm;
  return (
    <section data-role="intake-choices" className="panel">
      <h3 className="panel__title">Case-level choices</h3>
      <div className="decode-column">
        <div>
          <h4 className="decode-section__title">Construction part</h4>
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
          <h4 className="decode-section__title">Jaw</h4>
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
          <h4 className="decode-section__title">Gingival relief</h4>
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

export interface IntakeStageViewProps {
  readonly detail: CaseSessionDetail;
  readonly detectPhase: DetectPhase;
  readonly savingChoices: boolean;
  readonly choicesError: string | null;
  readonly onChoice: (patch: Partial<ChoicesUpdate>) => void;
  readonly onRetryDetect: () => void;
}

/** The stage's whole surface, pure payload → markup — statically testable. */
export function IntakeStageView({
  detail,
  detectPhase,
  savingChoices,
  choicesError,
  onChoice,
  onRetryDetect,
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
        <SiteList detail={detail} />
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
      onRetryDetect={fireDetect}
    />
  );
}
