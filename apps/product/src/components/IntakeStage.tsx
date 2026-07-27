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

/** The chair-side moment: rescan-grade verdicts, surfaced before any work. */
function CaptureBanner({ detail }: CaptureBannerProps) {
  const notices = rescanNotices(detail);
  if (notices.length === 0) return null;
  return (
    <div data-role="capture-banner" role="alert">
      <strong>
        Rescan recommended — the capture gate found problems before any work was
        invested.
      </strong>{" "}
      <span>
        If the patient is still in the chair, rescanning now costs minutes; marks placed
        on this capture would be wasted.
      </span>
      <ul>
        {notices.map((notice, index) => (
          <li key={index}>
            {notice.label}: {notice.message}
          </li>
        ))}
      </ul>
    </div>
  );
}

interface SiteListProps {
  readonly detail: CaseSessionDetail;
}

/** The site queue's Intake face: tooth, status, capture chip. */
function SiteList({ detail }: SiteListProps) {
  const unassigned =
    detail.detection?.proposals.filter((p) => p.tooth_guess === null).length ?? 0;
  return (
    <section data-role="intake-sites">
      <h3>Sites</h3>
      <ul>
        {detail.sites.map((site) => (
          <li key={site.tooth}>
            Tooth {site.tooth} — {site.status}{" "}
            <span
              data-role="capture-chip"
              data-verdict={site.capture?.verdict ?? "none"}
              title={site.capture?.checks.map((c) => c.message).join(" ") ?? undefined}
            >
              {captureChipLabel(site.capture)}
            </span>
          </li>
        ))}
      </ul>
      {unassigned > 0 && (
        <p data-role="unassigned-proposals">
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
 * nothing is chosen yet), PUT whole on every change. */
export function ChoicesPanel({ detail, saving, error, onChoice }: ChoicesPanelProps) {
  const chosen = detail.choices;
  const construction =
    chosen.construction_path ?? detail.case.suggested_construction ?? "";
  const jaw = chosen.jaw ?? detail.case.jaw;
  const relief = chosen.gingival_offset_mm ?? chosen.gingival_offset_default_mm;
  return (
    <section data-role="intake-choices">
      <h3>Case-level choices</h3>
      <label>
        Construction part{" "}
        <select
          data-role="choice-construction"
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
      </label>
      <div data-role="choice-jaw" role="group" aria-label="Jaw">
        {JAW_CHOICES.map((candidate) => (
          <button
            key={candidate}
            type="button"
            aria-pressed={candidate === jaw}
            onClick={() => onChoice({ jaw: candidate })}
          >
            {candidate}
          </button>
        ))}
      </div>
      <label>
        Gingival relief (mm){" "}
        <input
          data-role="choice-relief"
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
      </label>
      <ul data-role="relief-ceilings">
        {ceilingReadouts(detail, chosen.gingival_offset_mm).map((readout) => (
          <li key={readout.variant} data-exceeded={readout.exceeded}>
            {readout.line}
          </li>
        ))}
      </ul>
      {saving && <p data-role="choices-saving">Saving choices…</p>}
      {error !== null && (
        <div data-role="choices-error" role="alert">
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
    <div data-role="intake-stage">
      <CaptureBanner detail={detail} />
      {detectPhase.kind === "detecting" && (
        <p data-role="detect-busy">Detecting caps…</p>
      )}
      {detectPhase.kind === "failed" && (
        <div data-role="detect-error" role="alert">
          <strong>Detection refused.</strong> <span>{detectPhase.detail}</span>{" "}
          <button type="button" onClick={onRetryDetect}>
            Try again
          </button>
        </div>
      )}
      <MainStage
        caseId={detail.case.id}
        scanFilename={detail.case.scan_filename}
        sites={detail.sites}
        markers={detectionMarkers(detail)}
      />
      <SiteList detail={detail} />
      <ChoicesPanel
        detail={detail}
        saving={savingChoices}
        error={choicesError}
        onChoice={onChoice}
      />
      {declareOpen ? (
        <Link data-role="continue-declare" to={`/case/${detail.case.id}/declare`}>
          Continue to Declare
        </Link>
      ) : (
        <span data-role="continue-declare" aria-disabled="true">
          Continue to Declare — {blockedReason("declare", facts)}
        </span>
      )}
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
