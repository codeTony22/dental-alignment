/**
 * THE WORKSPACE'S PROVENANCE POPOVER (gap `deviation-budget-in-workspace`, 2026-08-02):
 * one control on the toolbar that answers "how much room is left, and on which
 * metric?" from the acceptance catalog's own numbers, and "what has happened on this
 * case?" from the server-written activity log — both endpoints built for exactly this
 * seam and never consumed until now.
 *
 * A DISCLOSURE, NOT A MODAL (client direction, 2026-08-02). Every other overlay in
 * this app is `role="dialog"` + `aria-modal="true"` behind a scrim, because closing
 * the case shell or the confirmation mid-flight would strand an act with the server.
 * This popover asserts nothing and blocks nothing behind it — the three panes and the
 * fork stay live and inert-free underneath it — so it wears the plain accessible
 * disclosure pattern instead (`aria-expanded` + `aria-controls` on the toggle, a
 * plain panel), never `role="dialog"`/`aria-modal`.
 *
 * COMPUTES NOTHING IT DISPLAYS. Every number, band word and threshold below is the
 * BFF's payload rendered verbatim through domain/provenance.ts's pure display rules —
 * see that module's own note on why (the design prototype's forbidden client-side
 * deviation()/verdict()/tolerance, flow.dc.html 1363-1372).
 */
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  fetchActivity,
  fetchSiteAcceptance,
  type ApiResult,
  type CaseActivityView,
  type FetchState,
  type SiteAcceptanceMetric,
  type SiteAcceptanceView,
} from "../api/client";
import {
  acceptanceAbsenceWords,
  bandChipClass,
  isMissingMetric,
  isStaleMetric,
  logWindowWords,
  staleSummaryWords,
  thresholdWords,
} from "../domain/provenance";
import { recordedAtWords } from "../domain/declare";
import { useDialogEscape } from "./useDialogEscape";

/** One measured metric row: the label the catalog gave it, its band chip, the
 *  measured display string and the catalog's own thresholds — never a value this
 *  surface compares itself. */
function AcceptanceMetricRow({
  metric,
  staleMetrics,
}: {
  readonly metric: SiteAcceptanceMetric;
  readonly staleMetrics: readonly string[];
}) {
  const thresholds = thresholdWords(metric);
  return (
    <li
      data-role="acceptance-metric"
      data-metric={metric.key}
      data-band={metric.band}
      className="workspace-insight__row"
    >
      <span className="workspace-insight__row-label">{metric.label}</span>{" "}
      <span data-role="metric-band" className={bandChipClass(metric.band)}>
        {metric.band}
      </span>{" "}
      <span data-role="metric-value" className="assurance-num">
        {metric.display ?? "—"}
      </span>
      {thresholds !== null && (
        <span data-role="metric-thresholds" className="assurance-sub">
          {" "}
          {thresholds}
        </span>
      )}
      {isStaleMetric(staleMetrics, metric.key) && (
        <span data-role="metric-stale" className="assurance-sub assurance-stale">
          predates a rework — not re-measured since
        </span>
      )}
    </li>
  );
}

/** A key the catalog could not measure at all — the neutral chip, NEVER the pass
 *  chip: this row exists precisely because there is nothing here to have passed. */
function AcceptanceMissingRow({ metricKey }: { readonly metricKey: string }) {
  return (
    <li data-role="acceptance-missing" data-metric={metricKey} className="workspace-insight__row">
      <span className="workspace-insight__row-label">{metricKey}</span>{" "}
      <span data-role="metric-band" className={bandChipClass("missing")}>
        not measured
      </span>
    </li>
  );
}

function AcceptanceSection({
  tooth,
  acceptance,
}: {
  readonly tooth: number | null;
  readonly acceptance: FetchState<SiteAcceptanceView> | null;
}) {
  return (
    <section
      data-role="insight-acceptance"
      aria-label="Acceptance numbers for this site"
      className="workspace-insight__section"
    >
      <h4 className="workspace-insight__heading">Site numbers</h4>
      {acceptance === null ? (
        <p data-role="acceptance-empty" className="panel__hint">
          Pick a site in the queue to see its acceptance numbers.
        </p>
      ) : acceptance.kind === "loading" ? (
        <p data-role="acceptance-loading" className="panel__hint" role="status">
          Reading tooth {tooth}&rsquo;s acceptance numbers…
        </p>
      ) : acceptance.kind === "error" ? (
        <AcceptanceAbsence result={acceptance} />
      ) : (
        <>
          <p data-role="acceptance-overall" className="workspace-insight__row">
            Overall band:{" "}
            <span className={bandChipClass(acceptance.data.overall_band)}>
              {acceptance.data.overall_band}
            </span>
          </p>
          <ul data-role="acceptance-metrics" className="workspace-insight__list">
            {acceptance.data.metrics
              .filter((metric) => !isMissingMetric(acceptance.data.missing, metric.key))
              .map((metric) => (
                <AcceptanceMetricRow
                  key={metric.key}
                  metric={metric}
                  staleMetrics={acceptance.data.stale_metrics}
                />
              ))}
            {acceptance.data.missing.map((key) => (
              <AcceptanceMissingRow key={key} metricKey={key} />
            ))}
          </ul>
          {staleSummaryWords(acceptance.data.stale_metrics) !== null && (
            <p data-role="acceptance-stale-summary" className="assurance-sub assurance-stale">
              {staleSummaryWords(acceptance.data.stale_metrics)}
            </p>
          )}
        </>
      )}
    </section>
  );
}

/** The 404-pre-run branch, worded as the honest state it is (HARD RULE: never the
 *  standing error tone for a healthy "nothing measured yet") — and every other
 *  failure kept in the ordinary tone, so an actual outage does not read as calm. */
function AcceptanceAbsence({ result }: { readonly result: Extract<ApiResult<SiteAcceptanceView>, { kind: "error" }> }) {
  const absence = acceptanceAbsenceWords(result);
  return (
    <p
      data-role="acceptance-absent"
      data-tone={absence.tone}
      role={absence.tone === "error" ? "alert" : undefined}
      className={absence.tone === "hint" ? "panel__hint" : "panel__error"}
    >
      {absence.words}
    </p>
  );
}

function ActivitySection({ activity }: { readonly activity: FetchState<CaseActivityView> }) {
  if (activity.kind === "loading") {
    return (
      <section data-role="insight-activity" aria-label="Case log" className="workspace-insight__section">
        <h4 className="workspace-insight__heading">Case log</h4>
        <p data-role="activity-loading" className="panel__hint" role="status">
          Reading the case log…
        </p>
      </section>
    );
  }
  if (activity.kind === "error") {
    return (
      <section data-role="insight-activity" aria-label="Case log" className="workspace-insight__section">
        <h4 className="workspace-insight__heading">Case log</h4>
        <p data-role="activity-error" role="alert" className="panel__error">
          {activity.detail}
        </p>
      </section>
    );
  }
  const view = activity.data;
  const windowWords = logWindowWords(view.recorded, view.entries.length);
  return (
    <section data-role="insight-activity" aria-label="Case log" className="workspace-insight__section">
      <h4 className="workspace-insight__heading">Case log</h4>
      {windowWords !== null && (
        <p data-role="activity-window" className="panel__hint">
          {windowWords}
        </p>
      )}
      {view.entries.length === 0 ? (
        // "nothing has happened yet" is the server's own honest answer to an
        // untouched case (activity.py:153-154) — an empty log is a 200, never a 404,
        // and this renders that as a fact, not an absence of data.
        <p data-role="activity-empty" className="panel__hint">
          Nothing has happened on this case yet.
        </p>
      ) : (
        <ol data-role="activity-log" className="workspace-insight__list">
          {view.entries.map((entry, index) => (
            <li
              key={index}
              data-role="activity-entry"
              data-event={entry.event}
              className="workspace-insight__row"
            >
              <span className="workspace-insight__row-time">{recordedAtWords(entry.at)}</span>{" "}
              <span className="workspace-insight__row-event">{entry.event}</span>{" "}
              <span className="workspace-insight__row-detail">{entry.detail}</span>
              {entry.tooth !== null && (
                <span data-role="activity-tooth" className="assurance-sub">
                  {" "}
                  · tooth {entry.tooth}
                </span>
              )}
            </li>
          ))}
        </ol>
      )}
      {view.site_adjustments.length > 0 && (
        <>
          <h5 className="workspace-insight__subheading">This site&rsquo;s shipped record</h5>
          <ul data-role="site-adjustments" className="workspace-insight__list">
            {view.site_adjustments.map((row, index) => (
              <li
                key={index}
                data-role="site-adjustment-entry"
                data-tooth={row.tooth}
                className="workspace-insight__row"
              >
                <span className="workspace-insight__row-time">{recordedAtWords(row.at)}</span>{" "}
                <span className="workspace-insight__row-event">{row.operation}</span>{" "}
                <span className="workspace-insight__row-detail">{row.detail}</span>{" "}
                {/* `who` carries its own disclaimer and rides in VERBATIM — dropping
                    it would leave the bare word "operator" looking like an identity
                    (client.ts's own note on SiteAdjustmentView). */}
                <span data-role="adjustment-who" className="assurance-sub">
                  {row.who}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

export interface WorkspaceInsightViewProps {
  readonly tooth: number | null;
  readonly caseId: string;
  readonly open: boolean;
  /** ONE act, both directions: the toggle button, the close button and (while open)
   *  Escape and click-outside all call this same handler — none of them "assert" a
   *  status, this is presentation state local to the popover. */
  readonly onToggle: () => void;
  /** null = no active site: the section says so rather than fetching nothing, and
   *  the log below still reads — the case log is not scoped to one tooth. */
  readonly acceptance: FetchState<SiteAcceptanceView> | null;
  readonly activity: FetchState<CaseActivityView>;
}

const PANEL_ID = "workspace-insight-panel";

/** The pure surface: every branch above is driven entirely by these props, so this
 *  renders deterministically from a payload with no DOM/network of its own — the
 *  local hooks below (Escape, click-outside) never fire under `renderToStaticMarkup`
 *  (no commit, no DOM), exactly like `useDialogEscape`'s own note explains; they run
 *  only once this is mounted in a browser via the `WorkspaceInsight` container. */
export function WorkspaceInsightView({
  tooth,
  caseId,
  open,
  onToggle,
  acceptance,
  activity,
}: WorkspaceInsightViewProps): ReactNode {
  const wrapRef = useRef<HTMLSpanElement | null>(null);
  // Escape closes it — the one dialog-adjacent behaviour this disclosure still wants;
  // useDialogEscape is generic over "a key should close this while open" and does not
  // require role="dialog" to be true of what it is closing.
  useDialogEscape(open, onToggle);
  // CLICK OUTSIDE MAY CLOSE IT (client direction, 2026-08-02: "keep it simple and
  // honest"). No focus trap, no portal — a disclosure the operator can dismiss by
  // looking away from is exactly as safe as one dismissed by a close button, because
  // nothing behind it is inert. UNCOVERED BY THE SUITE for the same reason
  // `useDialogEscape` states: these tests render with `renderToStaticMarkup` in NODE,
  // which never runs an effect at all.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (wrapRef.current === null) return;
      if (wrapRef.current.contains(event.target as Node)) return;
      onToggle();
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open, onToggle]);

  return (
    <span data-role="workspace-insight-wrap" className="workspace-insight" ref={wrapRef}>
      <button
        type="button"
        data-role="insight-toggle"
        aria-expanded={open}
        aria-controls={PANEL_ID}
        className={`button button--ghost button--small${open ? " button--active" : ""}`}
        onClick={onToggle}
      >
        Site numbers &amp; case log
      </button>
      {open && (
        <section
          id={PANEL_ID}
          data-role="workspace-insight"
          aria-label={`Site numbers and case log — case ${caseId}`}
          className="workspace-insight__panel"
        >
          <button
            type="button"
            data-role="insight-close"
            className="button button--ghost button--small workspace-insight__close"
            onClick={onToggle}
          >
            Close
          </button>
          <AcceptanceSection tooth={tooth} acceptance={acceptance} />
          <ActivitySection activity={activity} />
        </section>
      )}
    </span>
  );
}

export interface WorkspaceInsightProps {
  readonly caseId: string;
  readonly tooth: number | null;
  /** Refetch trigger while the popover is already open — an act landing (a run, a
   *  rework) must not go unseen behind an open disclosure. Object identity is enough:
   *  both stages replace their whole `detail` payload only when an act actually
   *  lands (`onDetail`), never on an unrelated re-render, so passing `detail` itself
   *  is the honest key — see the effect below for why this is the ONE signal, never
   *  a poll and never a client-side append (the comp's `pushLog` array, forbidden). */
  readonly refreshKey?: unknown;
}

/** The container: owns open/closed state and fetches both views on open. */
export function WorkspaceInsight({ caseId, tooth, refreshKey }: WorkspaceInsightProps) {
  const [open, setOpen] = useState(false);
  const [acceptance, setAcceptance] = useState<FetchState<SiteAcceptanceView> | null>(null);
  const [activity, setActivity] = useState<FetchState<CaseActivityView>>({ kind: "loading" });
  const mountedRef = useRef(true);
  // MONOTONE REQUEST ID, not cleanup-cancellation (AdjustStage's auto-mark war story,
  // 2026-07-30 — "auto-mark stays stuck"): this effect's own dependencies (open,
  // tooth, refreshKey) change WHILE a request is in flight, and a cleanup that
  // cancelled its own fetch discarded the very answer it was waiting for, freezing
  // the panel on "loading" forever. A result is stale only when a NEWER request has
  // been minted, never merely because this effect re-ran.
  const requestRef = useRef(0);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    const request = ++requestRef.current;
    setActivity({ kind: "loading" });
    void fetchActivity(caseId).then((result) => {
      if (requestRef.current !== request || !mountedRef.current) return;
      setActivity(result);
    });
    if (tooth === null) {
      // no active site: the acceptance section says so — there is genuinely nothing
      // to ask the catalog about yet, which is not the same absence as a 404.
      setAcceptance(null);
      return;
    }
    setAcceptance({ kind: "loading" });
    void fetchSiteAcceptance(caseId, tooth).then((result) => {
      if (requestRef.current !== request || !mountedRef.current) return;
      setAcceptance(result);
    });
    // `refreshKey` is read only to re-run this effect while the popover stays open —
    // it decides nothing about WHAT is fetched, only WHEN to ask again.
  }, [open, caseId, tooth, refreshKey]);

  const handleToggle = useCallback(() => setOpen((was) => !was), []);

  return (
    <WorkspaceInsightView
      tooth={tooth}
      caseId={caseId}
      open={open}
      onToggle={handleToggle}
      acceptance={acceptance}
      activity={activity}
    />
  );
}
