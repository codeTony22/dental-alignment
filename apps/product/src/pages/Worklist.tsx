/**
 * "/" — THE WORKLIST (plan §4 "Worklist first", AM-7): the 20-scan morning's home
 * screen. One row per case from GET /api/case-sessions — doctor, jaw, the site
 * rollup, a run chip and a confirmation chip — sorted blocked-first (the exact order
 * lives with its rules in domain/worklist.ts) so the case that needs a human is the
 * first thing the morning sees. Opening a row resumes its session at the furthest
 * stage; the case shell's "next case" link lands back here.
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
  rollupLabel,
  runChip,
  type WorklistEntry,
} from "../domain/worklist";

const chipStyle: React.CSSProperties = {
  border: "1px solid currentColor",
  borderRadius: "999px",
  padding: "0 0.5rem",
  fontSize: "0.8em",
};

function WorklistEntryItem({ entry }: { readonly entry: WorklistEntry }) {
  if (entry.kind === "unreadable") {
    // The per-row error contract (slice 5a): the BFF's own refusal words render when
    // it stated them; the defensive fallback (a malformed element) keeps the honest
    // could-not-be-read line. Inert either way — a row without facts links nowhere.
    return (
      <li data-role="worklist-unreadable" style={{ opacity: 0.7 }}>
        Case entry {entry.id ?? `#${entry.index + 1}`} could not be read —{" "}
        {entry.error ?? "it needs attention the BFF cannot describe yet."}
      </li>
    );
  }
  const { row } = entry;
  return (
    <li data-role="worklist-row">
      <Link
        to={resumeTarget(row)}
        style={{ display: "flex", gap: "0.75rem", alignItems: "baseline", flexWrap: "wrap" }}
      >
        <strong>{row.doctor}</strong>
        <span data-role="row-jaw">{row.jaw}</span>
        <span data-role="row-rollup">{rollupLabel(row.sites)}</span>
        <span data-role="row-run" style={chipStyle}>
          {runChip(row.run_state)}
        </span>
        <span data-role="row-confirmed" style={chipStyle}>
          {confirmChip(row.confirmed)}
        </span>
      </Link>
    </li>
  );
}

interface WorklistScreenProps {
  readonly state: FetchState<readonly unknown[]>;
}

/** The presentational screen — every branch is a stated one, testable statically. */
export function WorklistScreen({ state }: WorklistScreenProps) {
  if (state.kind === "loading") {
    return <p data-role="worklist-loading">Loading the worklist…</p>;
  }
  if (state.kind === "error") {
    return <ErrorBanner detail={state.detail} />;
  }
  const entries = orderWorklist(classifyWorklist(state.data));
  return (
    <section data-role="worklist">
      <h2>Worklist</h2>
      {entries.length === 0 ? (
        <p data-role="worklist-empty">
          No cases yet — the case service found nothing to work on. New scans appear
          here as soon as they land in the data root.
        </p>
      ) : (
        <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "0.5rem" }}>
          {entries.map((entry) => (
            <WorklistEntryItem
              key={entry.kind === "row" ? entry.row.id : `unreadable-${entry.index}`}
              entry={entry}
            />
          ))}
        </ol>
      )}
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

  return <WorklistScreen state={state} />;
}
