import type { SiteSelection } from "../domain/librarySelection";

export interface SiteStepperProps {
  readonly sites: readonly SiteSelection[];
  readonly activeIndex: number;
  readonly onStep: (delta: number) => void;
  readonly onSelect: (index: number) => void;
}

/** "6020" when the site has a cap, the prompt when it has not — the overview list reads
 *  "1 — 6020" exactly like the client's dialog. A superseded id keeps its archive qualifier so
 *  two same-numbered caps can never look identical in the list. */
export function siteOverviewLabel(site: SiteSelection, index: number): string {
  return `${index + 1} — ${site.variantId ?? "no cap chosen"}`;
}

/**
 * THE SITE STEPPER — '‹ n ›' across the case's marked sites (the client's dialog steps one
 * site at a time), plus the overview list so the operator can see every site's
 * choice and review state at a glance and jump straight to one.
 *
 * The ✓ is the ACKNOWLEDGMENT state, not the selection state: a site is ticked once it has been
 * reviewed in the three panels, which is what the Process gate counts.
 */
export function SiteStepper({ sites, activeIndex, onStep, onSelect }: SiteStepperProps) {
  if (sites.length === 0) {
    return (
      <div className="decode-stepper decode-stepper--empty">
        <p className="panel__hint">No marked sites — mark at least one cap in step 2.</p>
      </div>
    );
  }
  const active = sites[activeIndex];
  return (
    <div className="decode-stepper">
      <div className="decode-stepper__control">
        <button
          type="button"
          className="button button--ghost button--small"
          disabled={activeIndex <= 0}
          aria-label="Previous site"
          onClick={() => onStep(-1)}
        >
          ‹
        </button>
        <span className="decode-stepper__position" role="status" aria-live="polite">
          {activeIndex + 1} / {sites.length}
          {active ? <span className="decode-stepper__tooth"> · tooth {active.tooth}</span> : null}
        </span>
        <button
          type="button"
          className="button button--ghost button--small"
          disabled={activeIndex >= sites.length - 1}
          aria-label="Next site"
          onClick={() => onStep(1)}
        >
          ›
        </button>
      </div>
      <ol className="decode-stepper__overview">
        {sites.map((site, index) => (
          <li key={site.tooth}>
            <button
              type="button"
              className={`decode-stepper__item${index === activeIndex ? " decode-stepper__item--active" : ""}${
                site.reviewed ? " decode-stepper__item--reviewed" : ""
              }`}
              aria-current={index === activeIndex}
              onClick={() => onSelect(index)}
              title={site.reviewed ? "Reviewed" : "Not reviewed yet"}
            >
              <span className="decode-stepper__label">{siteOverviewLabel(site, index)}</span>
              <span className="decode-stepper__state" aria-hidden="true">
                {site.reviewed ? "✓" : "○"}
              </span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}
