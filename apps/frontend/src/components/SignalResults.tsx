import type { TechniqueResultView } from "../api/client";
import {
  SIGNAL_GROUP_ORDER,
  acceptanceMetrics,
  groupLabel,
  guidanceActions,
  landmarkItems,
  scalarEntries,
} from "../domain/signals";
import { statusTone, statusWords, traceByClass } from "../domain/technique";

export interface SignalResultsProps {
  readonly result: TechniqueResultView | null;
  readonly error: string | null;
}

export function SignalResults({ result, error }: SignalResultsProps) {
  if (error !== null) {
    return (
      <div data-role="technique-error" className="results results--refuse" role="alert">
        {error}
      </div>
    );
  }
  if (result === null) {
    return (
      <div data-role="technique-empty" className="results results--empty">
        Choose Deterministic or Intelligence and try the technique. Every signal
        group the adjust / MCP seam already exposes will land here.
      </div>
    );
  }
  const groups = result.signals_after.groups;
  const tone = statusTone(result.status);
  return (
    <div data-role="technique-results" data-status={result.status} className={`results results--${tone}`}>
      <header className="results__head">
        <p data-role="technique-status" data-tone={tone}>
          {result.mode} · {result.status}
        </p>
        <p data-role="technique-detail">{statusWords(result)}</p>
      </header>

      {result.refusals.length > 0 && (
        <section data-role="technique-refusals" className="results__block">
          <h3>Refusals</h3>
          <ul>
            {result.refusals.map((item, index) => (
              <li key={`${item["kind"]}-${index}`}>
                {String(item["kind"] ?? "refused")}: {String(item["message"] ?? "")}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section data-role="technique-trace" className="results__block">
        <h3>Tool trace</h3>
        {(["READ", "DRY_RUN", "COMMIT"] as const).map((klass) => {
          const steps = traceByClass(result.trace, klass);
          return (
            <div key={klass} data-trace-class={klass}>
              <h4>{klass}</h4>
              {steps.length === 0 ? (
                <p className="muted">none</p>
              ) : (
                <ul>
                  {steps.map((step, index) => (
                    <li key={`${step.name}-${index}`} data-ok={step.ok}>
                      {step.name} — {step.detail}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </section>

      {result.outcome !== null && (
        <section data-role="technique-outcome" className="results__block">
          <h3>Outcome</h3>
          <p>{result.outcome.operation} — {result.outcome.detail}</p>
          {result.outcome.stale_metrics && result.outcome.stale_metrics.length > 0 && (
            <p data-role="stale-metrics" className="muted">
              stale: {result.outcome.stale_metrics.join(", ")}
            </p>
          )}
        </section>
      )}

      <section data-role="signal-groups" className="results__signals">
        {SIGNAL_GROUP_ORDER.map((name) => {
          const group = groups[name];
          const actions = name === "guidance" ? guidanceActions(group) : [];
          const metrics = name === "acceptance" ? acceptanceMetrics(group) : [];
          const landmarks = name === "landmarks" ? landmarkItems(group) : [];
          return (
            <article key={name} data-signal-group={name} className="signal-card">
              <h3>{groupLabel(name)}</h3>
              <dl>
                {scalarEntries(group).map((row) => (
                  <div key={row.key}>
                    <dt>{row.key}</dt>
                    <dd>{row.value}</dd>
                  </div>
                ))}
              </dl>
              {actions.length > 0 && (
                <ul data-role="guidance-actions">
                  {actions.map((action) => <li key={action}>{action}</li>)}
                </ul>
              )}
              {metrics.length > 0 && (
                <ul data-role="acceptance-metrics">
                  {metrics.map((metric) => (
                    <li key={String(metric["key"])} data-band={String(metric["band"])}>
                      {String(metric["label"] ?? metric["key"])} · {String(metric["band"])} ·{" "}
                      {String(metric["display"] ?? "—")}
                    </li>
                  ))}
                </ul>
              )}
              {landmarks.length > 0 && (
                <ul data-role="landmark-items">
                  {landmarks.map((mark, index) => (
                    <li key={String(mark["id"] ?? index)}>{String(mark["id"] ?? "landmark")}</li>
                  ))}
                </ul>
              )}
            </article>
          );
        })}
      </section>
    </div>
  );
}
