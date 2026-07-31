/**
 * "/" — THE WORKLIST (plan §4 "Worklist first", AM-7): the 20-scan morning's home
 * screen. One row per case from GET /api/case-sessions — doctor, jaw, the site
 * rollup, a run chip and a confirmation chip — sorted blocked-first (the exact order
 * lives with its rules in domain/worklist.ts) so the case that needs a human is the
 * first thing the morning sees. Opening a row resumes its session at the furthest
 * stage; the case shell's "next case" link lands back here.
 *
 * Parity slice: rows wear the demo's card/row language (the copied chip vocabulary —
 * band colours for the rollup, gate tones for run/confirm) and the blocked-first
 * bands get visible captions, the flagged one in the attention amber. The captions
 * only NAME the order domain/worklist already computed — no re-sorting here.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchWorklist, type FetchState } from "../api/client";
import { ErrorBanner } from "../components/ErrorBanner";
import {
  classifyWorklist,
  confirmChip,
  orderWorklist,
  resumeTarget,
  runChip,
  SCAN_ARRIVAL,
  SCAN_UPLOAD_ABSENT,
  worklistBand,
  type WorklistEntry,
} from "../domain/worklist";

/** The run chip's tone per AM-3 state — the demo's traffic-light chip language. */
function runChipClass(runState: string): string {
  if (runState === "done") return "chip chip--band-pass";
  if (runState === "refused") return "chip chip--band-fail";
  if (runState === "none") return "chip chip--band-missing";
  return "chip chip--gate"; // queued | running — in-flight, neutral
}

interface WorklistEntryItemProps {
  readonly entry: WorklistEntry;
  /** The band caption, rendered above this row when it opens a new band. */
  readonly bandLabel: string | null;
  /** True for the blocked bands (unreadable/flagged) — the caption wears amber. */
  readonly attention: boolean;
}

function WorklistEntryItem({ entry, bandLabel, attention }: WorklistEntryItemProps) {
  const caption = bandLabel !== null && (
    <p className={`worklist-band${attention ? " worklist-band--attention" : ""}`}>
      {bandLabel}
    </p>
  );
  if (entry.kind === "unreadable") {
    // The per-row error contract (slice 5a): the BFF's own refusal words render when
    // it stated them; the defensive fallback (a malformed element) keeps the honest
    // could-not-be-read line. Inert either way — a row without facts links nowhere.
    return (
      <li data-role="worklist-unreadable">
        {caption}
        <div className="worklist-unreadable">
          Case entry {entry.id ?? `#${entry.index + 1}`} could not be read —{" "}
          {entry.error ?? "it needs attention the BFF cannot describe yet."}
        </div>
      </li>
    );
  }
  const { row } = entry;
  const rowClass = [
    "worklist-row",
    row.confirmed
      ? "worklist-row--confirmed"
      : row.sites.flagged > 0
        ? "worklist-row--flagged"
        : "",
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <li data-role="worklist-row" className={rowClass}>
      {caption}
      <Link to={resumeTarget(row)} className="worklist-row__link">
        <strong className="worklist-row__doctor">{row.doctor}</strong>
        <span data-role="row-jaw" className="chip chip--gate">
          {row.jaw}
        </span>
        <span data-role="row-rollup" className="worklist-row__chips">
          <span className="chip chip--band-missing">{row.sites.declared} declared</span>
          <span className="chip chip--band-pass">{row.sites.ready} ready</span>
          {row.sites.flagged > 0 && (
            <span className="chip chip--band-review">{row.sites.flagged} flagged</span>
          )}
        </span>
        {/* data-state carries AM-3's live job states (queued|running|done|refused)
            so the chip can style in-flight work without re-deriving anything */}
        <span
          data-role="row-run"
          data-state={row.run_state}
          className={runChipClass(row.run_state)}
        >
          {runChip(row.run_state)}
        </span>
        <span
          data-role="row-confirmed"
          className={row.confirmed ? "chip chip--band-pass" : "chip chip--band-missing"}
        >
          {confirmChip(row.confirmed)}
        </span>
      </Link>
    </li>
  );
}

/** The band captions, in worklist order (band -1 unreadable … band 3 confirmed). */
const BAND_LABELS: Readonly<Record<number, string>> = {
  [-1]: "Needs attention — could not be read",
  0: "Flagged — a human verdict is owed",
  1: "In progress",
  2: "Fresh intake",
  3: "Confirmed",
};

const bandOf = (entry: WorklistEntry): number =>
  entry.kind === "unreadable" ? -1 : worklistBand(entry.row);

/**
 * WHERE THE DESIGN'S DROP ZONE WENT (design flow.dc.html 76-83, gap "a scan arrives").
 *
 * The prototype draws a dashed "Drop a scan file" rectangle with a "browse files"
 * button whose handler is `() => this.pickScan(SCANS[0].id)` — it selects a fixture.
 * There is no ingest behind it, and there is none in this product either: the BFF's
 * `data_root` is the worker's tree, READ-ONLY to the BFF by design (bff/config.py:20),
 * and every case's identity, doctor, jaw and library suggestion is read out of the
 * folder the lab created. A dashed rectangle that quietly loaded a fixture — or one
 * that accepted a file this installation has nowhere to put — would teach a workflow
 * that does not exist, which is strictly worse than no zone at all.
 *
 * So the zone states the route that IS real, in the operator's terms. It is prose and
 * a heading: no button, no input, nothing droppable. The claims are in
 * domain/worklist.SCAN_ARRIVAL with the measurements that refuted the prototype's.
 */
function ScanArrival() {
  return (
    <section data-role="scan-arrival" className="scan-arrival">
      <h3 className="scan-arrival__title">How a new scan reaches this worklist</h3>
      <ol className="scan-arrival__steps">
        {SCAN_ARRIVAL.map((step) => (
          <li key={step.key} data-step={step.key} className="scan-arrival__step">
            <strong className="scan-arrival__step-title">{step.title}</strong>
            <span className="scan-arrival__step-detail">{step.detail}</span>
          </li>
        ))}
      </ol>
      <p data-role="scan-upload-absent" className="scan-arrival__note">
        {SCAN_UPLOAD_ABSENT}
      </p>
    </section>
  );
}

interface WorklistScreenProps {
  readonly state: FetchState<readonly unknown[]>;
}

/** The presentational screen — every branch is a stated one, testable statically. */
export function WorklistScreen({ state }: WorklistScreenProps) {
  if (state.kind === "loading") {
    return (
      <p data-role="worklist-loading" className="panel__hint">
        Loading the worklist…
      </p>
    );
  }
  if (state.kind === "error") {
    return <ErrorBanner detail={state.detail} />;
  }
  const entries = orderWorklist(classifyWorklist(state.data));
  return (
    <section data-role="worklist" className="worklist">
      <h2 className="worklist__title">Worklist</h2>
      {entries.length === 0 ? (
        <p data-role="worklist-empty" className="panel__copy">
          No cases yet — the case service found nothing to work on. New scans appear
          here as soon as they land in the data root.
        </p>
      ) : (
        <ol className="worklist__list">
          {entries.map((entry, index) => {
            const band = bandOf(entry);
            const newBand = index === 0 || bandOf(entries[index - 1]!) !== band;
            return (
              <WorklistEntryItem
                key={entry.kind === "row" ? entry.row.id : `unreadable-${entry.index}`}
                entry={entry}
                bandLabel={newBand ? (BAND_LABELS[band] ?? null) : null}
                attention={band <= 0}
              />
            );
          })}
        </ol>
      )}
      {/* Below the work, not above it: the 20-scan morning opens this page to pick a
          case, not to read a procedure. It matters most on the empty list, which is
          exactly where it ends up being the only thing on screen. */}
      <ScanArrival />
    </section>
  );
}

export function WorklistPage() {
  const [state, setState] = useState<FetchState<readonly unknown[]>>({
    kind: "loading",
  });

  useEffect(() => {
    let cancelled = false;
    void fetchWorklist().then((result) => {
      if (!cancelled) setState(result);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="page">
      <WorklistScreen state={state} />
    </div>
  );
}
