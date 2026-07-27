import type { GuidanceLevel, RunSiteResult } from "../domain/types";

interface GuidancePanelProps {
  readonly sites: readonly RunSiteResult[];
}

const LEVEL_LABEL: Readonly<Record<GuidanceLevel, string>> = {
  ready: "READY · advisory",
  attention: "ATTENTION",
  "action-needed": "ACTION NEEDED",
};

const LEVEL_CHIP_CLASS: Readonly<Record<GuidanceLevel, string>> = {
  ready: "chip--gate-ready",
  attention: "chip--gate-attention",
  "action-needed": "chip--gate-action",
};

/**
 * The centerpiece of the advisory gate: one block per site, read top-to-bottom, telling the
 * operator exactly what to do next. Complements variant.flags (still rendered by FlagsAlerts
 * wherever it renders today) — this panel does not replace that, it adds the "what do I do
 * about it" layer on top of the raw flag text.
 */
export function GuidancePanel({ sites }: GuidancePanelProps) {
  const withGuidance = sites.filter((site) => site.guidance !== null);
  if (withGuidance.length === 0) return null;

  return (
    <section className="guidance-panel" aria-labelledby="guidance-panel-heading">
      <h3 id="guidance-panel-heading" className="guidance-panel__title">
        Guidance
      </h3>
      {withGuidance.map((site) => {
        const guidance = site.guidance;
        if (!guidance) return null;
        const isReady = guidance.level === "ready";
        return (
          <div key={site.tooth} className="guidance-panel__site">
            <div className="guidance-panel__site-header">
              <span className="guidance-panel__tooth">Tooth {site.tooth}</span>
              <span className={`chip ${LEVEL_CHIP_CLASS[guidance.level]}`}>
                {LEVEL_LABEL[guidance.level]}
              </span>
              {isReady && guidance.actions[0] !== undefined && (
                <span className="guidance-panel__ready-action">{guidance.actions[0]}</span>
              )}
            </div>
            {!isReady && (
              <ul className="guidance-panel__actions">
                {guidance.actions.map((action, i) => (
                  <li key={i}>{action}</li>
                ))}
              </ul>
            )}
          </div>
        );
      })}
    </section>
  );
}
