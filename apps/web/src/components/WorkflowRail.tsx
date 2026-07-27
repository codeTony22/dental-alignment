import type { StageId, WorkflowStage } from "../domain/workflow";

interface WorkflowRailProps {
  readonly stages: readonly WorkflowStage[];
  readonly current: StageId;
  readonly onSelect: (stage: StageId) => void;
}

/**
 * THE WORKFLOW RAIL — the client's sequence, made obvious and made navigable (2026-07-26).
 *
 * It replaces the old step rail, which was a passive read-out of four numbers stacked above a
 * tall column of panels. Two changes, both in service of "make that path obvious":
 *
 *  - IT IS THE NAVIGATION. Each stage is a button; the work column shows exactly ONE stage's
 *    panel, so the shell stops being a scroll through every step at once and the 3D keeps the
 *    space that used to go to panels the operator was finished with.
 *  - IT TELLS THE TRUTH. Ticks come from domain/workflow judging the CASE, not from how far the
 *    operator has clicked, and a stage that cannot be opened yet carries the sentence that says
 *    why rather than being silently dead.
 */
export function WorkflowRail({ stages, current, onSelect }: WorkflowRailProps) {
  return (
    <nav className="workflow-rail" aria-label="Workflow">
      <ol className="workflow-rail__list">
        {stages.map((stage) => {
          const isCurrent = stage.id === current;
          return (
            <li key={stage.id} className="workflow-rail__item">
              <button
                type="button"
                className={[
                  "workflow-rail__step",
                  isCurrent ? "workflow-rail__step--current" : "",
                  stage.complete ? "workflow-rail__step--complete" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                aria-current={isCurrent ? "step" : undefined}
                disabled={!stage.enabled}
                // Named explicitly: the marker is a bare glyph and the detail line is the only
                // other text, so a screen reader was announcing an unreachable stage as
                // "Load a case first." with no idea which stage that was.
                aria-label={`Step ${stage.number} — ${stage.label}: ${stage.blockedReason ?? stage.detail}`}
                title={stage.blockedReason ?? stage.detail}
                onClick={() => onSelect(stage.id)}
              >
                <span className="workflow-rail__marker" aria-hidden="true">
                  {stage.complete ? "✓" : stage.number}
                </span>
                <span className="workflow-rail__text">
                  <span className="workflow-rail__label">{stage.label}</span>
                  <span className="workflow-rail__detail">
                    {stage.blockedReason ?? stage.detail}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
