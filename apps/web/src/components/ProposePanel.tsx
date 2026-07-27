import type { ProposeResult } from "../domain/types";
import { BusyState } from "./BusyState";
import { CaptureBanner, CaptureChip } from "./CaptureChip";

interface ProposePanelProps {
  readonly disabled: boolean;
  readonly busy: boolean;
  readonly elapsedS: number;
  readonly result: ProposeResult | null;
  /** Whether the orange proposal markers are currently drawn on the scan (default OFF — the
   *  doctor's raw scan stays clean until explicitly asked to show them). */
  readonly showMarkers: boolean;
  readonly onRunDetection: (fresh: boolean) => void;
  readonly onToggleMarkers: () => void;
}

export function ProposePanel({
  disabled,
  busy,
  elapsedS,
  result,
  showMarkers,
  onRunDetection,
  onToggleMarkers,
}: ProposePanelProps) {
  return (
    <section className="panel" aria-labelledby="step2-heading">
      <h2 id="step2-heading" className="panel__title">
        Step 2 · Detect caps (optional)
      </h2>
      <div className="panel__actions">
        <button
          type="button"
          className="button button--primary"
          disabled={disabled || busy}
          onClick={() => onRunDetection(false)}
        >
          Run detection
        </button>
        {result && result.cached && (
          <button
            type="button"
            className="button button--ghost"
            disabled={busy}
            onClick={() => onRunDetection(true)}
            title="Run a live (uncached) detection pass"
          >
            ⟳ rerun live
          </button>
        )}
        {result && (
          <button
            type="button"
            className={`button button--secondary${showMarkers ? " button--active" : ""}`}
            onClick={onToggleMarkers}
            aria-pressed={showMarkers}
            title="Toggle the orange proposal markers on the 3D scan"
          >
            {showMarkers ? "hide proposals" : "view proposals"}
          </button>
        )}
      </div>

      {busy && <BusyState message="automation scanning the arch…" elapsedS={elapsedS} />}

      {result && result.cached && !busy && (
        <p className="panel__hint">precomputed — click ⟳ for a live run</p>
      )}

      {/* The intake gate's chair-side moment: a rescan verdict on ANY assessed site
          (machine proposal or curated suggestion) shows before marks are invested. */}
      {result && (
        <CaptureBanner
          items={result.captureSites.map((s, i) => ({
            label: s.tooth !== null ? `Tooth ${s.tooth}` : `Site ${i + 1}`,
            capture: s.capture,
          }))}
        />
      )}

      {result && (
        <ul className="proposal-list">
          {result.proposals.map((p, i) => (
            <li key={i} className="proposal-list__item">
              Proposal {i + 1} — void {p.voidRatio.toFixed(2)}, {p.rimBelowCuspsMm.toFixed(1)}mm below cusps{" "}
              {p.capture && <CaptureChip capture={p.capture} />}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
