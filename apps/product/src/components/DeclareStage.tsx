/**
 * DECLARE (plan §4 Declare / AM-8, slice 5a): the site queue on the LEFT (tooth,
 * status chip, capture chip, declared variant — click makes a site active), the
 * case-scoped SYSTEM bar on TOP (effective system with its server-attributed
 * "suggested" tag; switching asks in WORDS naming the reset count BEFORE any PUT —
 * the visible-reset doctrine), and the active site's VARIANT cards in the CENTRE
 * (Ø × height from the catalog payload, the superseded shelf collapsed behind a
 * labelled fold; a click IS the declaration PUT).
 *
 * Direction of trust (AM-4): optimism is OFF. Every PUT's response is the whole new
 * detail and replaces the payload verbatim (onDetail); a refusal renders in the
 * backend's own words while the surface keeps showing what is actually persisted.
 * The reset a system switch causes happens SERVER-side (bff status machine) — this
 * component only asks first and displays what came back.
 *
 * 5b lands the three live panes beside this queue (components/DeclarePanes — the
 * demo's VerifyStage semantics, rebuilt against BFF shapes) and WITH them the review
 * tick (AM-8: "reviewed over panels, not a checkbox"); Declare completes only when
 * every site is reviewed (domain/flow.ts).
 */
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  postRun,
  putDeclaration,
  putSystem,
  type CaseSessionDetail,
} from "../api/client";
import {
  blockedReason,
  factsFromCaseSession,
  isComplete,
  isReachable,
} from "../domain/flow";
import {
  activeSiteFrom,
  declaredLabel,
  resetCount,
  runKeyFor,
  shouldAutoRun,
  switchWords,
  systemCards,
  variantShelves,
  type VariantCard,
} from "../domain/declare";
import { captureChipLabel } from "../domain/intake";
import { DeclarePanes } from "./DeclarePanes";
import { MainStage } from "./MainStage";

/** What is in flight, named — the surface states it instead of freezing silently. */
export type DeclareSaving = "idle" | "system" | "declaration";

/** The run POST's client-side lifecycle (5c): the in-process worker completes the
 * whole run inside the request, so "firing" IS the progress state — the persisted
 * queued|running states only surface to OTHER readers (the worklist) meanwhile. */
export type RunPhase = "idle" | "firing";

interface SystemBarProps {
  readonly detail: CaseSessionDetail;
  readonly onAskSwitch: (model: string) => void;
}

function SystemBar({ detail, onAskSwitch }: SystemBarProps) {
  return (
    <div data-role="system-bar" role="group" aria-label="Implant system">
      {systemCards(detail).map((card) => (
        <button
          key={card.model}
          type="button"
          data-role="system-card"
          aria-pressed={card.effective}
          data-model={card.model}
          onClick={() => onAskSwitch(card.model)}
        >
          {card.model}{" "}
          <span data-role="system-variant-count">{card.variantCount} parts</span>
          {card.suggested && <span data-role="suggested-tag"> suggested</span>}
        </button>
      ))}
    </div>
  );
}

interface SwitchConfirmProps {
  readonly detail: CaseSessionDetail;
  readonly pendingSwitch: string;
  readonly onConfirm: () => void;
  readonly onCancel: () => void;
}

/** The visible-reset moment: the words carry the count, the PUT waits for consent. */
function SwitchConfirm({ detail, pendingSwitch, onConfirm, onCancel }: SwitchConfirmProps) {
  return (
    <div data-role="system-switch-confirm" role="alert">
      <p>{switchWords(pendingSwitch, resetCount(detail))}</p>
      <button type="button" onClick={onConfirm}>
        Switch system
      </button>
      <button type="button" onClick={onCancel}>
        Keep {detail.system.effective_model ?? "the current system"}
      </button>
    </div>
  );
}

interface SiteQueueProps {
  readonly detail: CaseSessionDetail;
  readonly activeTooth: number | null;
  readonly onSelectSite: (tooth: number) => void;
}

/** The LEFT rail of Declare: every site, its server facts, one click = active. */
function SiteQueue({ detail, activeTooth, onSelectSite }: SiteQueueProps) {
  const active = activeSiteFrom(detail.sites, activeTooth);
  return (
    <aside data-role="declare-queue" aria-label="Site queue">
      <ul>
        {detail.sites.map((site) => (
          <li key={site.tooth}>
            <button
              type="button"
              data-role="queue-site"
              aria-pressed={active?.tooth === site.tooth}
              data-tooth={site.tooth}
              onClick={() => onSelectSite(site.tooth)}
            >
              Tooth {site.tooth}{" "}
              <span data-role="status-chip" data-status={site.status}>
                {site.status}
              </span>{" "}
              <span
                data-role="capture-chip"
                data-verdict={site.capture?.verdict ?? "none"}
              >
                {captureChipLabel(site.capture)}
              </span>{" "}
              <span data-role="declared-variant">{declaredLabel(site)}</span>
            </button>
          </li>
        ))}
      </ul>
      {detail.sites.length === 0 && (
        <p data-role="declare-empty">No sites to declare on this case yet.</p>
      )}
    </aside>
  );
}

interface VariantCardButtonProps {
  readonly card: VariantCard;
  readonly declared: boolean;
  readonly onDeclare: (variantId: string) => void;
}

function VariantCardButton({ card, declared, onDeclare }: VariantCardButtonProps) {
  return (
    <button
      type="button"
      data-role="variant-card"
      data-variant={card.id}
      aria-pressed={declared}
      onClick={() => onDeclare(card.id)}
    >
      <strong>{card.label}</strong> <span>{card.dims}</span>
    </button>
  );
}

export interface DeclareStageViewProps {
  readonly detail: CaseSessionDetail;
  readonly activeTooth: number | null;
  /** A system switch awaiting the operator's worded consent, or null. */
  readonly pendingSwitch: string | null;
  readonly saving: DeclareSaving;
  readonly error: string | null;
  /** The auto-fired run's client lifecycle (5c); defaults idle for static tests. */
  readonly runPhase?: RunPhase;
  /** A run POST that never reached an outcome (transport/409) — stated with retry. */
  readonly runError?: string | null;
  readonly onRetryRun?: () => void;
  readonly onSelectSite: (tooth: number) => void;
  readonly onAskSwitch: (model: string) => void;
  readonly onConfirmSwitch: () => void;
  readonly onCancelSwitch: () => void;
  readonly onDeclare: (variantId: string) => void;
  /** The three live panes + the review tick (5b) — the container passes the
   * DeclarePanes container; View tests may omit it (the panes have their own). */
  readonly panesSlot?: ReactNode;
}

/** The stage's whole surface, pure payload → markup — statically testable. */
export function DeclareStageView({
  detail,
  activeTooth,
  pendingSwitch,
  saving,
  error,
  runPhase = "idle",
  runError = null,
  onRetryRun,
  onSelectSite,
  onAskSwitch,
  onConfirmSwitch,
  onCancelSwitch,
  onDeclare,
  panesSlot,
}: DeclareStageViewProps) {
  const facts = factsFromCaseSession(detail);
  const active = activeSiteFrom(detail.sites, activeTooth);
  const shelves = variantShelves(detail);
  const adjustOpen = isReachable("adjust", facts);
  const deliverOpen = isReachable("deliver", facts);
  // THE RUN'S PROGRESS SURFACE (5c): in flight client-side, or persisted as
  // queued|running (another tab/operator fired it — AM-3's states render either way)
  const runInFlight =
    runPhase === "firing" ||
    facts.runState === "queued" ||
    facts.runState === "running";
  const runRefusal =
    facts.runState === "refused"
      ? (detail.session.run_refusal ??
        "The run was refused — the worker recorded no words.")
      : null;
  return (
    <div data-role="declare-stage">
      <SystemBar detail={detail} onAskSwitch={onAskSwitch} />
      {pendingSwitch !== null && (
        <SwitchConfirm
          detail={detail}
          pendingSwitch={pendingSwitch}
          onConfirm={onConfirmSwitch}
          onCancel={onCancelSwitch}
        />
      )}
      <div style={{ display: "flex", gap: "1.5rem", marginTop: "1rem" }}>
        <SiteQueue
          detail={detail}
          activeTooth={activeTooth}
          onSelectSite={onSelectSite}
        />
        <div style={{ flex: 1 }}>
          <MainStage
            caseId={detail.case.id}
            scanFilename={detail.case.scan_filename}
            sites={detail.sites}
            activeTooth={active?.tooth ?? null}
          />
          {panesSlot}
          <section data-role="variant-cards" aria-label="Variant cards">
            <h3>
              {active !== null
                ? `Variants for tooth ${active.tooth}`
                : "Variants"}
            </h3>
            {shelves.current.map((card) => (
              <VariantCardButton
                key={card.id}
                card={card}
                declared={active?.declared_variant === card.id}
                onDeclare={onDeclare}
              />
            ))}
            {shelves.superseded.length > 0 && (
              <details data-role="superseded-fold">
                <summary>
                  Superseded shelf — {shelves.superseded.length} archived part
                  {shelves.superseded.length === 1 ? "" : "s"}
                </summary>
                {shelves.superseded.map((card) => (
                  <VariantCardButton
                    key={card.id}
                    card={card}
                    declared={active?.declared_variant === card.id}
                    onDeclare={onDeclare}
                  />
                ))}
              </details>
            )}
          </section>
          {saving !== "idle" && (
            <p data-role="declare-saving">
              {saving === "system" ? "Switching system…" : "Declaring variant…"}
            </p>
          )}
          {error !== null && (
            <div data-role="declare-error" role="alert">
              {error}
            </div>
          )}
          {/* THE RUN FOOTER (5c, plan §1.2 compute-early): the auto-fired run's
              progress in honest words — a refusal renders VERBATIM with the
              explicit retry (like an errored preview slot, it never auto-refires). */}
          {runInFlight ? (
            <p data-role="run-progress">
              Aligning {facts.siteTotal} site{facts.siteTotal === 1 ? "" : "s"} —
              30–60 s; the case stays open and the panes stay live.
            </p>
          ) : runRefusal !== null ? (
            <div data-role="run-refused" role="alert">
              <p>{runRefusal}</p>
              <button type="button" data-role="run-retry" onClick={onRetryRun}>
                Run again
              </button>
            </div>
          ) : runError !== null ? (
            <div data-role="run-error" role="alert">
              <p>{runError}</p>
              <button type="button" data-role="run-retry" onClick={onRetryRun}>
                Try the run again
              </button>
            </div>
          ) : null}
          {/* Continue per flow.ts: Deliver directly when Adjust has nothing to
              offer (plan §4 — skippable Adjust), else Adjust over its flagged
              queue, else the honest blocked sentence. A done run lights these. */}
          {deliverOpen && isComplete("adjust", facts) ? (
            <Link data-role="continue-on" to={`/case/${detail.case.id}/deliver`}>
              Continue to Deliver — nothing to adjust
            </Link>
          ) : adjustOpen ? (
            <Link data-role="continue-on" to={`/case/${detail.case.id}/adjust`}>
              Continue to Adjust
            </Link>
          ) : (
            <span data-role="continue-on" aria-disabled="true">
              Continue — {blockedReason("adjust", facts)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

export interface DeclareStageProps {
  readonly detail: CaseSessionDetail;
  /** The shell owns the payload; every action's response replaces it whole. */
  readonly onDetail: (next: CaseSessionDetail) => void;
}

/** The container: active-site state, the worded switch ceremony, the two PUTs,
 * and the run's auto-fire (5c). */
export function DeclareStage({ detail, onDetail }: DeclareStageProps) {
  const caseId = detail.case.id;
  const mountedRef = useRef(true);
  const [activeTooth, setActiveTooth] = useState<number | null>(null);
  const [pendingSwitch, setPendingSwitch] = useState<string | null>(null);
  const [saving, setSaving] = useState<DeclareSaving>("idle");
  const [error, setError] = useState<string | null>(null);
  const [runPhase, setRunPhase] = useState<RunPhase>("idle");
  const [runError, setRunError] = useState<string | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // THE AUTO-FIRE (plan §1.2 compute-early; the automation directive): when the
  // detail shows choices complete + every site ready + no current run, POST once.
  // Facts-keyed like detect and the previews (runKeyFor/shouldAutoRun): the fired
  // ref is marked BEFORE the async settles so a doubled effect run cannot POST a
  // 30–60 s job twice, and a refused run does NOT re-fire — retry is the
  // operator's explicit act in the footer.
  const runKey = runKeyFor(detail);
  const runFiredRef = useRef<string | null>(null);
  const fireRun = useCallback(
    (firedKey: string) => {
      runFiredRef.current = firedKey;
      setRunPhase("firing");
      void postRun(caseId).then((result) => {
        if (!mountedRef.current) return;
        setRunPhase("idle");
        if (result.kind === "ok") {
          setRunError(null);
          // verdicts landed SERVER-side; the response is the whole new truth
          onDetail(result.data);
        } else {
          // transport/409/422 — the run never reached a persisted outcome; the
          // words render with the explicit retry
          setRunError(result.detail);
        }
      });
    },
    [caseId, onDetail],
  );
  useEffect(() => {
    if (runKey !== null && shouldAutoRun({ key: runKey, firedKey: runFiredRef.current })) {
      fireRun(runKey);
    }
  }, [runKey, fireRun]);

  const handleRetryRun = useCallback(() => {
    // a refused run has no key (run_state past "none"): mint a one-off fired key
    // so the explicit act always fires exactly once
    fireRun(runKey ?? `retry-${Date.now()}`);
  }, [runKey, fireRun]);

  const fireSystem = useCallback(
    (model: string) => {
      setSaving("system");
      void putSystem(caseId, model).then((result) => {
        if (!mountedRef.current) return;
        setSaving("idle");
        setPendingSwitch(null);
        if (result.kind === "ok") {
          setError(null);
          onDetail(result.data);
        } else {
          setError(result.detail);
        }
      });
    },
    [caseId, onDetail],
  );

  /** The visible-reset doctrine, precisely: a switch that would DESTROY declarations
   * asks in words first; one that resets nothing (nothing declared yet, or pinning
   * the already-effective system as an explicit act) PUTs directly — a confirmation
   * over zero consequences would be the checkbox-over-nothing AM-8 forbids. */
  const handleAskSwitch = useCallback(
    (model: string) => {
      const destroys =
        model !== detail.system.effective_model && resetCount(detail) > 0;
      if (destroys) {
        setPendingSwitch(model);
      } else {
        fireSystem(model);
      }
    },
    [detail, fireSystem],
  );

  const handleConfirmSwitch = useCallback(() => {
    if (pendingSwitch !== null) fireSystem(pendingSwitch);
  }, [pendingSwitch, fireSystem]);

  const handleDeclare = useCallback(
    (variantId: string) => {
      const active = activeSiteFrom(detail.sites, activeTooth);
      if (active === null) return; // no sites — the cards are not rendered anyway
      setSaving("declaration");
      void putDeclaration(caseId, active.tooth, variantId).then((result) => {
        if (!mountedRef.current) return;
        setSaving("idle");
        if (result.kind === "ok") {
          setError(null);
          onDetail(result.data);
        } else {
          setError(result.detail);
        }
      });
    },
    [caseId, detail, activeTooth, onDetail],
  );

  return (
    <DeclareStageView
      detail={detail}
      activeTooth={activeTooth}
      pendingSwitch={pendingSwitch}
      saving={saving}
      error={error}
      runPhase={runPhase}
      runError={runError}
      onRetryRun={handleRetryRun}
      onSelectSite={setActiveTooth}
      onAskSwitch={handleAskSwitch}
      onConfirmSwitch={handleConfirmSwitch}
      onCancelSwitch={() => setPendingSwitch(null)}
      onDeclare={handleDeclare}
      panesSlot={
        <DeclarePanes
          detail={detail}
          site={activeSiteFrom(detail.sites, activeTooth)}
          onDetail={onDetail}
        />
      }
    />
  );
}
