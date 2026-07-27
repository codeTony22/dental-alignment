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
 * Stage bodies are placeholders naming their building slice; the rail, the guard and
 * the payload plumbing are this slice's product.
 */
import { useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import {
  fetchCaseSession,
  type CaseSessionDetail,
  type FetchState,
} from "../api/client";
import {
  factsFromCaseSession,
  resolveStagePath,
  stageStates,
  type StageId,
} from "../domain/flow";
import { ErrorBanner } from "../components/ErrorBanner";
import { MainStage } from "../components/MainStage";
import { StageRail } from "../components/StageRail";

/**
 * Each body names the slice that builds (the rest of) it, so the shell never pretends.
 * Intake and Declare now carry the MAIN STAGE (slice 3) above their placeholder line —
 * the 3D is the product; the rest of each body stays a placeholder for slices 4/5a.
 */
const STAGE_BODY: Readonly<Record<StageId, string>> = {
  intake: "Slice 4 builds the rest of Intake: auto-detect on load, capture verdicts, case-level choices.",
  declare: "Slice 5a builds the rest of Declare: site queue, system bar, variant cards, review ticks.",
  adjust: "Adjust — slice 6 builds this (flagged queue, the four tools; skippable by design).",
  deliver: "Deliver — slice 8 builds this (assurance table, sealed confirmation, gated release).",
};

/** The stages whose bodies mount the main stage today (plan §7 slice 3). */
const STAGES_WITH_MAIN_STAGE: readonly StageId[] = ["intake", "declare"];

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
}

/** The presentational shell — pure payload → markup, testable without a fetch. */
export function CaseShellView({ detail, stage }: CaseShellViewProps) {
  const states = stageStates(factsFromCaseSession(detail));
  return (
    <section data-role="case-shell">
      <header
        style={{ display: "flex", alignItems: "baseline", gap: "1rem", flexWrap: "wrap" }}
      >
        <h2 style={{ margin: 0 }}>
          Case {detail.case.id} — {detail.case.doctor}
        </h2>
        <span data-role="case-jaw">{detail.case.jaw}</span>
        {/* AM-7's loop: the worklist is home, and "next case" returns there. */}
        <Link to="/" data-role="next-case">
          Next case — back to the worklist
        </Link>
      </header>
      <div style={{ display: "flex", gap: "2rem", marginTop: "1rem" }}>
        <StageRail states={states} current={stage} caseId={detail.case.id} />
        <section data-role="stage-body" style={{ flex: 1 }}>
          {STAGES_WITH_MAIN_STAGE.includes(stage) && (
            <MainStage
              caseId={detail.case.id}
              scanFilename={detail.case.scan_filename}
              sites={detail.sites}
            />
          )}
          <p>{STAGE_BODY[stage]}</p>
        </section>
      </div>
    </section>
  );
}

export function CaseShell() {
  const { id, stage } = useParams<{ id: string; stage: string }>();
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
    return <p data-role="case-loading">Loading case {id}…</p>;
  }
  if (state.kind === "error") {
    return <CaseLoadError id={id} error={state} />;
  }

  const resolution = resolveStagePath(stage, factsFromCaseSession(state.data));
  if (resolution.kind === "redirect") {
    return <Navigate to={`/case/${id}/${resolution.to}`} replace />;
  }
  return <CaseShellView detail={state.data} stage={resolution.stage} />;
}
