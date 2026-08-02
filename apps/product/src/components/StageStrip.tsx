/**
 * THE NO-CASE STAGE STRIP (client comp, page pass 2026-08-02). The comp's dark header
 * carries the five-stage rail on EVERY page; with no case open, Intake leads and the
 * rest sit dimmed with a why-tooltip. This is that state for the product's non-case
 * routes: a PREVIEW of the flow, not a navigation — there is no case to navigate
 * into, so every step is a span and the way in is the worklist below the band.
 *
 * It wears the same .workflow-rail clothes as the case band's StageRail rather than
 * its own, so the strip cannot drift from the rail it previews. Titles and one-liners
 * come from the flow model (STAGE_INFO) — this component names nothing itself.
 */
import { STAGE_INFO, STAGE_ORDER } from "../domain/flow";

const OPEN_A_CASE = "Open a case from the worklist first.";

export function StageStrip() {
  return (
    <nav
      aria-label="Case stages — no case open"
      data-role="stage-preview"
      className="workflow-rail workflow-rail--preview"
    >
      <ol className="workflow-rail__list">
        {STAGE_ORDER.map((id, index) => {
          const info = STAGE_INFO[id];
          const leading = index === 0;
          const stepClass = leading
            ? "workflow-rail__step workflow-rail__step--current"
            : "workflow-rail__step workflow-rail__step--blocked";
          return (
            <li key={id} data-stage={id} className="workflow-rail__item">
              <span
                className={stepClass}
                aria-disabled="true"
                title={leading ? "Open a case from the worklist." : OPEN_A_CASE}
              >
                <span
                  aria-hidden="true"
                  data-role="stage-marker"
                  className="workflow-rail__marker"
                >
                  {String(index + 1)}
                </span>
                <span className="workflow-rail__text">
                  <span data-role="stage-title" className="workflow-rail__label">
                    {info.title}
                  </span>
                  <span data-role="stage-detail" className="workflow-rail__detail">
                    {info.oneLiner}
                  </span>
                </span>
              </span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
