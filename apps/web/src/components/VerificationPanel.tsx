import { useState } from "react";
import type { AcceptanceBand, AcceptanceMetric, RunSiteResult } from "../domain/types";
import { qcImagesFor, withCacheBust } from "../domain/types";

/** Everything the panel needs beyond the site row itself — grouped so ResultsTable can
 *  thread one optional object through instead of five loose props. */
export interface VerificationContext {
  readonly caseId: string;
  readonly filesBase: string;
  readonly runVersion: number | null;
  readonly packageFiles: readonly string[];
  /** Records the doctor's sign-off (confirmed=false retracts). Note only travels on confirm. */
  readonly onConfirm: (tooth: number, confirmed: boolean, note?: string) => void;
  /** Tooth whose confirm request is in flight (disables that site's controls). */
  readonly confirmBusyTooth: number | null;
}

interface VerificationPanelProps {
  readonly site: RunSiteResult;
  readonly context: VerificationContext;
}

const BAND_TEXT: Record<AcceptanceBand, string> = {
  pass: "pass",
  review: "review",
  fail: "fail",
  missing: "not measured",
};

const BAND_TOOLTIP =
  "Proposed acceptance band: every threshold anchors to a cited industry number or a " +
  "constant the pipeline already enforces. 'not measured' is honest — an absent value " +
  "is never counted as a pass.";

const CONFIRM_TOOLTIP =
  "Records your manual sign-off on this site's verification numbers. The record is kept " +
  "with the run and in the audit history; it never changes the alignment itself.";

export function BandChip({ band }: { band: AcceptanceBand }) {
  return (
    <span className={`chip chip--band chip--band-${band}`} title={BAND_TOOLTIP}>
      {BAND_TEXT[band]}
    </span>
  );
}

function MetricRow({ metric }: { metric: AcceptanceMetric }) {
  return (
    <tr className="verification-panel__metric">
      <td title={metric.note ?? undefined}>{metric.label}</td>
      <td className="verification-panel__value">{metric.display ?? "—"}</td>
      <td className="verification-panel__ref" title={metric.industryRef.source}>
        {metric.industryRef.value}
      </td>
      <td>
        <BandChip band={metric.band} />
      </td>
    </tr>
  );
}

function MetricsGroup({ heading, metrics }: { heading: string; metrics: readonly AcceptanceMetric[] }) {
  if (metrics.length === 0) return null;
  return (
    <>
      <tr className="verification-panel__group">
        <th scope="rowgroup" colSpan={4}>
          {heading}
        </th>
      </tr>
      {metrics.map((m) => (
        <MetricRow key={m.key} metric={m} />
      ))}
    </>
  );
}

/** The doctor's sign-off control: confirm with an optional note, or retract an earlier
 *  confirmation. The current record (confirmed/retracted, note, timestamp) always shows —
 *  a retraction is a visible state, not a deletion (the audit stream keeps every step). */
function ConfirmControl({ site, context }: VerificationPanelProps) {
  const [note, setNote] = useState("");
  const busy = context.confirmBusyTooth === site.tooth;
  const record = site.doctorConfirmation;

  if (record?.confirmed) {
    return (
      <div className="verification-panel__confirm" title={CONFIRM_TOOLTIP}>
        <span className="chip chip--band-pass">✓ confirmed by doctor · {record.ts}</span>
        {record.note && <span className="verification-panel__note">“{record.note}”</span>}
        <button
          type="button"
          className="button button--ghost button--small"
          disabled={busy}
          onClick={() => context.onConfirm(site.tooth, false)}
        >
          Retract confirmation
        </button>
      </div>
    );
  }

  return (
    <div className="verification-panel__confirm" title={CONFIRM_TOOLTIP}>
      {record && (
        <span className="verification-panel__note">confirmation retracted · {record.ts}</span>
      )}
      <input
        type="text"
        className="verification-panel__note-input"
        placeholder="optional note (e.g. codes visually aligned)"
        maxLength={500}
        value={note}
        disabled={busy}
        onChange={(e) => setNote(e.target.value)}
      />
      <button
        type="button"
        className="button button--primary button--small"
        disabled={busy}
        onClick={() => context.onConfirm(site.tooth, true, note)}
      >
        Doctor: confirm this alignment
      </button>
    </div>
  );
}

/**
 * The per-site doctor verification panel (client ask 2026-07-23): every acceptance-catalog
 * metric as a row — plain-language check, OUR measured number, the industry reference it
 * anchors to, and a pass/review/fail/"not measured" chip — plus the two QC images the
 * package emitted (clock view + deviation map) and the doctor's confirm/retract control.
 * Purely a read-out + recorded sign-off: nothing here changes the alignment.
 */
export function VerificationPanel({ site, context }: VerificationPanelProps) {
  const acceptance = site.acceptance;
  if (!acceptance) {
    return (
      <div className="verification-panel">
        <p className="panel__hint">No verification data on this run (older backend) — re-run the automation.</p>
      </div>
    );
  }
  const doctorMetrics = acceptance.metrics.filter((m) => m.audience === "doctor");
  const labMetrics = acceptance.metrics.filter((m) => m.audience === "lab");
  const images = qcImagesFor(context.caseId, site.tooth, context.packageFiles);

  return (
    <div className="verification-panel">
      <div className="verification-panel__header">
        <strong>Verification numbers — tooth {site.tooth}</strong>
        <BandChip band={acceptance.overall.band} />
      </div>
      <div className="verification-panel__table-scroll">
        <table className="verification-panel__table">
          <thead>
            <tr>
              <th scope="col">Check</th>
              <th scope="col">Our number</th>
              <th scope="col">Industry reference</th>
              <th scope="col" title={BAND_TOOLTIP}>
                Band
              </th>
            </tr>
          </thead>
          <tbody>
            <MetricsGroup heading="Doctor verification set" metrics={doctorMetrics} />
            <MetricsGroup heading="Lab / QC checks" metrics={labMetrics} />
          </tbody>
        </table>
      </div>
      <p className="verification-panel__context" title={acceptance.context.industryRef.source}>
        {acceptance.context.label}: {acceptance.context.text}
      </p>
      {images.length > 0 && (
        <div className="verification-panel__images">
          {images.map((img) => (
            <figure key={img.name}>
              <img
                src={withCacheBust(`${context.filesBase}${img.name}`, context.runVersion)}
                alt={img.label}
              />
              <figcaption>{img.label}</figcaption>
            </figure>
          ))}
        </div>
      )}
      <ConfirmControl site={site} context={context} />
    </div>
  );
}
