/**
 * THE STAGE RAIL — the product's four stages (plan §4) as the case shell's left rail.
 *
 * The demo's rail DOCTRINE, reimplemented for these stages: the rail IS the
 * navigation, its ticks come from the flow model judging the payload rather than
 * from click history, and a blocked stage carries the one sentence that says why
 * instead of being silently dead. Parity slice: the rail now wears the demo's
 * .workflow-rail clothes (numbered markers, tick states, the muted one-liner) —
 * the CSS is copied in styles.css (ledger row 9); this markup composes it.
 *
 * One departure from the demo, on purpose: stages are LINKS, not buttons — routes are
 * the product's navigation state and browser Back/Forward are the back affordance
 * (plan §4 Intake: "Back is a browser affordance"). The unreachable stage is a span
 * in the same clothes (.workflow-rail__step--blocked), never a dead control.
 */
import { Link } from "react-router-dom";
import type { StageId, StageState } from "../domain/flow";

interface StageRailProps {
  readonly states: readonly StageState[];
  readonly current: StageId;
  readonly caseId: string;
}

export function StageRail({ states, current, caseId }: StageRailProps) {
  return (
    <nav aria-label="Case stages" data-role="stage-rail" className="workflow-rail">
      <ol className="workflow-rail__list">
        {states.map((stage) => {
          const isCurrent = stage.id === current;
          const detail = stage.blockedReason ?? stage.oneLiner;
          const stepClass = [
            "workflow-rail__step",
            isCurrent ? "workflow-rail__step--current" : "",
            stage.complete ? "workflow-rail__step--complete" : "",
          ]
            .filter(Boolean)
            .join(" ");
          const body = (
            <>
              <span
                aria-hidden="true"
                data-role="stage-marker"
                className="workflow-rail__marker"
              >
                {stage.complete ? "✓" : String(stage.number)}
              </span>
              <span className="workflow-rail__text">
                <span data-role="stage-title" className="workflow-rail__label">
                  {stage.title}
                </span>
                <span data-role="stage-detail" className="workflow-rail__detail">
                  {detail}
                </span>
              </span>
            </>
          );
          return (
            <li key={stage.id} data-stage={stage.id} className="workflow-rail__item">
              {stage.reachable ? (
                <Link
                  to={`/case/${caseId}/${stage.id}`}
                  className={stepClass}
                  aria-current={isCurrent ? "step" : undefined}
                  aria-label={`Stage ${stage.number} — ${stage.title}: ${detail}`}
                  title={detail}
                >
                  {body}
                </Link>
              ) : (
                // Not a link: an unreachable stage is not navigable, and the sentence
                // below the title says why — never a dead control.
                <span
                  className={`${stepClass} workflow-rail__step--blocked`}
                  aria-disabled="true"
                  aria-label={`Stage ${stage.number} — ${stage.title}: ${detail}`}
                  title={detail}
                >
                  {body}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
