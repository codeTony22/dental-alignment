/**
 * /case/:id/:stage — THE CASE SHELL (plan §4, §7 slice 2).
 *
 * The container fetches the flow-shaped detail payload, projects it into flow facts
 * (AM-4: the BFF derives the facts; this app derives only display logic), and lets
 * the route guard decide: an unknown or unreachable stage segment redirects to the
 * session's furthest stage, so a stale bookmark or a hand-typed URL can never show a
 * stage the case has not earned. Browser Back/Forward are the back affordance —
 * no in-app back button (plan §4 Intake).
 *
 * Intake's body is BUILT (slice 4 — components/IntakeStage, which owns auto-detect and
 * the choices PUT) and so is Declare's (slice 5a — components/DeclareStage: site queue,
 * system bar, variant cards; 5b adds the live panes and the review tick). Both stages'
 * action responses replace the shell's payload via onDetail, so the whole rail
 * re-derives from what the BFF returned. The remaining bodies are placeholders naming
 * their building slice.
 */
import { useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import {
  fetchCaseSession,
  postCaseReset,
  type CaseSessionDetail,
  type FetchState,
} from "../api/client";
import {
  factsFromCaseSession,
  resolveStagePath,
  stageStates,
  type StageId,
} from "../domain/flow";
import { AdjustStage } from "../components/AdjustStage";
import { DeclareStage } from "../components/DeclareStage";
import { DeliverStage } from "../components/DeliverStage";
import { ErrorBanner } from "../components/ErrorBanner";
import { IntakeStage } from "../components/IntakeStage";
import { StageRail } from "../components/StageRail";

// Every stage now has a body: Intake (slice 4), Declare (5a/5b/5c), Adjust (slice 6 —
// the client's 2026-07-28 "the adjust functionality is not build at all", answered) and
// Deliver (slice 8). The placeholder map that named the slice still to come is gone
// with the last placeholder: a shell that can only render real stages cannot pretend.

interface CaseLoadErrorProps {
  readonly id: string;
  readonly error: Extract<FetchState<CaseSessionDetail>, { kind: "error" }>;
}

/**
 * A refusal is not an outage: a 404 means the BFF answered and this case is gone
 * (a stale bookmark, a removed session) — telling the operator to restart a healthy
 * service would misdiagnose it. Only the 404 gets the not-found words; every other
 * failure keeps the unreachable-service banner and its next move.
 */
export function CaseLoadError({ id, error }: CaseLoadErrorProps) {
  if (error.status === 404) {
    return (
      <ErrorBanner headline={`Case ${id} is no longer in the data root.`} detail={error.detail}>
        The case service is up — this case just is not there to open.{" "}
        <Link to="/">Back to the worklist</Link>
      </ErrorBanner>
    );
  }
  return <ErrorBanner detail={error.detail} />;
}

interface CaseShellViewProps {
  readonly detail: CaseSessionDetail;
  readonly stage: StageId;
  /** How Intake's actions replace the payload; the static tests pass nothing. */
  readonly onDetail?: (next: CaseSessionDetail) => void;
  /** Reset the whole case (client 2026-07-30). Null/omitted renders no control —
   *  static tests predate it, and a demo affordance is opt-in by construction. */
  readonly onResetCase?: (() => void) | null;
  readonly resetting?: boolean;
}

const IGNORE_DETAIL = () => undefined;

/** The presentational shell — pure payload → markup, testable without a fetch.
 *
 * Parity slice: the shell IS the demo's workbench — rail | work column | 3D-dominant
 * stage (the copied .workbench grid: 208px rail, minmax(320px,400px) work, 1fr stage).
 * Each built stage emits exactly two regions (.workbench__work + .workbench__stage);
 * the stage-body wrapper is `display: contents` so those regions sit as the grid's own
 * children without changing the tested DOM roles. */
export function CaseShellView({
  detail,
  stage,
  onDetail,
  onResetCase = null,
  resetting = false,
}: CaseShellViewProps) {
  const states = stageStates(factsFromCaseSession(detail));
  return (
    <section data-role="case-shell" className="case-shell">
      <header className="case-header">
        <h2 className="case-header__title">
          Case {detail.case.id} — {detail.case.doctor}
        </h2>
        <span data-role="case-jaw" className="chip chip--gate">
          {detail.case.jaw}
        </span>
        {/* RESET THE WHOLE CASE (client 2026-07-30: "there is a need for resetting
            the cases persistance"). It sits in the case HEADER, not on a stage,
            because it is not part of any stage's work — it discards all of it. The
            immutable run directories survive on disk; this clears the session that
            points at them, so a demo can be walked from the very start. */}
        {onResetCase !== null && (
          <button
            type="button"
            data-role="case-reset"
            className="button button--ghost button--small case-header__reset"
            disabled={resetting}
            onClick={onResetCase}
          >
            {resetting ? "Resetting…" : "Reset case (demo)"}
          </button>
        )}
        {/* AM-7's loop: the worklist is home, and "next case" returns there. */}
        {/* The way back lives in the app header now ("← All cases", on every route). This
            corner link said "Next case" first and went to the worklist — a label that
            described an action it did not perform, which is why the client could not find
            the way home (2026-07-27). One honest affordance beats two, one of them lying. */}
      </header>
      <div className="workbench">
        <StageRail states={states} current={stage} caseId={detail.case.id} />
        <section data-role="stage-body" className="stage-contents">
          {stage === "intake" ? (
            <IntakeStage detail={detail} onDetail={onDetail ?? IGNORE_DETAIL} />
          ) : stage === "declare" ? (
            <DeclareStage detail={detail} onDetail={onDetail ?? IGNORE_DETAIL} />
          ) : stage === "adjust" ? (
            <AdjustStage detail={detail} onDetail={onDetail ?? IGNORE_DETAIL} />
          ) : (
            <DeliverStage detail={detail} onDetail={onDetail ?? IGNORE_DETAIL} />
          )}
        </section>
      </div>
    </section>
  );
}

export function CaseShell() {
  const { id, stage } = useParams<{ id: string; stage: string }>();
  const [resetting, setResetting] = useState(false);
  const [state, setState] = useState<FetchState<CaseSessionDetail>>({
    kind: "loading",
  });

  useEffect(() => {
    if (id === undefined) return;
    let cancelled = false;
    setState({ kind: "loading" });
    void fetchCaseSession(id).then((result) => {
      if (!cancelled) setState(result);
    });
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (id === undefined) {
    // the route pattern guarantees an id; this is exhaustiveness, not a real path
    return <Navigate to="/" replace />;
  }
  if (state.kind === "loading") {
    return (
      <div className="page">
        <p data-role="case-loading" className="panel__hint">
          Loading case {id}…
        </p>
      </div>
    );
  }
  if (state.kind === "error") {
    return (
      <div className="page">
        <CaseLoadError id={id} error={state} />
      </div>
    );
  }

  const resolution = resolveStagePath(stage, factsFromCaseSession(state.data));
  if (resolution.kind === "redirect") {
    return <Navigate to={`/case/${id}/${resolution.to}`} replace />;
  }
  return (
    <CaseShellView
      detail={state.data}
      stage={resolution.stage}
      // an action's response IS the new payload — rendered verbatim (AM-4)
      onDetail={(next) => setState({ kind: "ok", data: next })}
      resetting={resetting}
      onResetCase={() => {
        setResetting(true);
        void postCaseReset(state.data.case.id).then((result) => {
          setResetting(false);
          if (result.kind === "ok") setState({ kind: "ok", data: result.data });
        });
      }}
    />
  );
}
