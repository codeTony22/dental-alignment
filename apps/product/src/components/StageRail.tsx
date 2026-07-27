/**
 * THE STAGE RAIL — the product's four stages (plan §4) as the case shell's left rail.
 *
 * The demo's rail DOCTRINE, reimplemented for these stages (deliberately not copied —
 * no ledger row needed): the rail IS the navigation, its ticks come from the flow
 * model judging the payload rather than from click history, and a blocked stage
 * carries the one sentence that says why instead of being silently dead.
 *
 * One departure from the demo, on purpose: stages are LINKS, not buttons — routes are
 * the product's navigation state and browser Back/Forward are the back affordance
 * (plan §4 Intake: "Back is a browser affordance").
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
    <nav aria-label="Case stages" data-role="stage-rail">
      <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "0.5rem" }}>
        {states.map((stage) => {
          const isCurrent = stage.id === current;
          const marker = stage.complete ? "✓" : String(stage.number);
          const detail = stage.blockedReason ?? stage.oneLiner;
          const body = (
            <>
              <span aria-hidden="true" data-role="stage-marker">
                {marker}
              </span>{" "}
              <span data-role="stage-title">{stage.title}</span>
              <span
                data-role="stage-detail"
                style={{ display: "block", fontSize: "0.85em" }}
              >
                {detail}
              </span>
            </>
          );
          return (
            <li key={stage.id} data-stage={stage.id}>
              {stage.reachable ? (
                <Link
                  to={`/case/${caseId}/${stage.id}`}
                  aria-current={isCurrent ? "step" : undefined}
                  aria-label={`Stage ${stage.number} — ${stage.title}: ${detail}`}
                  style={{ fontWeight: isCurrent ? 700 : 400 }}
                >
                  {body}
                </Link>
              ) : (
                // Not a link: an unreachable stage is not navigable, and the sentence
                // below the title says why — never a dead control.
                <span
                  aria-disabled="true"
                  aria-label={`Stage ${stage.number} — ${stage.title}: ${detail}`}
                  style={{ opacity: 0.55 }}
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
