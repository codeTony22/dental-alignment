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
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  fetchWorklist,
  postCaseReset,
  uploadScan,
  type FetchState,
} from "../api/client";
import { ErrorBanner } from "../components/ErrorBanner";
import {
  classifyWorklist,
  confirmChip,
  discoveryLine,
  orderWorklist,
  resetAllWords,
  resumeTarget,
  runChip,
  SCAN_ARRIVAL,
  SCAN_UPLOAD_NOTE,
  siteCountChip,
  suggestedUploadFolder,
  uploadedCaseTarget,
  uploadNameUsable,
  teethLine,
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

/**
 * One segment bar per site, coloured by the served counts (comp: the card's foot
 * strip). The counts are the BFF's rollup; the bars only draw them — ready first in
 * the pass green, then flagged in the review amber, the rest neutral. WHICH tooth is
 * which is not stated here because the rollup does not say.
 */
function SegmentStrip({ ready, flagged, total }: {
  readonly ready: number;
  readonly flagged: number;
  readonly total: number;
}) {
  if (total <= 0) return null;
  const tone = (index: number): string =>
    index < ready
      ? "worklist-card__bar worklist-card__bar--pass"
      : index < ready + flagged
        ? "worklist-card__bar worklist-card__bar--flag"
        : "worklist-card__bar";
  return (
    <span aria-hidden="true" className="worklist-card__segments">
      {Array.from({ length: total }, (_, index) => (
        <span key={index} className={tone(index)} />
      ))}
    </span>
  );
}

function WorklistEntryItem({ entry }: { readonly entry: WorklistEntry }) {
  if (entry.kind === "unreadable") {
    // The per-row error contract (slice 5a): the BFF's own refusal words render when
    // it stated them; the defensive fallback (a malformed element) keeps the honest
    // could-not-be-read line. Inert either way — a row without facts links nowhere.
    return (
      <li data-role="worklist-unreadable">
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
  const teeth = teethLine(row);
  return (
    <li data-role="worklist-row" className={rowClass}>
      <Link to={resumeTarget(row)} className="worklist-row__link">
        <span className="worklist-card__head">
          <strong className="worklist-row__doctor">{row.doctor}</strong>
          <span data-role="row-sites" className="chip chip--gate">
            {siteCountChip(row.sites)}
          </span>
        </span>
        {/* The comp card's meta line, from served facts only (domain/worklist). */}
        <span className="worklist-card__meta">{discoveryLine(row)}</span>
        <span className="worklist-card__meta">
          {teeth !== "" && <span className="worklist-card__teeth">{teeth}</span>}
          <span data-role="row-jaw" className="chip chip--gate">
            {row.jaw}
          </span>
        </span>
        <span className="worklist-card__chips">
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
            className={
              row.confirmed ? "chip chip--band-pass" : "chip chip--band-missing"
            }
          >
            {confirmChip(row.confirmed)}
          </span>
        </span>
        <SegmentStrip
          ready={row.sites.ready}
          flagged={row.sites.flagged}
          total={row.sites.total}
        />
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
 * THE DESIGN'S DROP ZONE, REAL NOW (§10-AB.3, 2026-08-02). Its 2026-07-31 refusal
 * was about the missing ingest, not the zone: the prototype's "browse files" loaded
 * a fixture and this installation had nowhere to put a file. The client then decided
 * the write path (POST /api/uploads → scans/<folder>/<file>.stl, the BFF's one
 * write into data_root), so the zone and its reason arrive together. The procedure
 * note below it stays, describing BOTH routes in.
 */
/** The drop zone's statically-testable face (§10-AB.3): three states, each a
 * stated one. The words are the storage policy's — one STL, one folder per case,
 * the folder name IS the case identity — and every refusal renders verbatim. */
export interface ScanDropZoneViewProps {
  readonly phase:
    | { readonly kind: "idle" }
    | {
        readonly kind: "armed";
        readonly filename: string;
        readonly folder: string;
        readonly error: string | null;
        readonly busy: boolean;
      }
    | { readonly kind: "done"; readonly caseId: string };
  readonly onBrowse?: () => void;
  readonly onFolder?: (name: string) => void;
  readonly onUpload?: () => void;
  readonly onCancel?: () => void;
}

export function ScanDropZoneView({
  phase,
  onBrowse = () => undefined,
  onFolder = () => undefined,
  onUpload = () => undefined,
  onCancel = () => undefined,
}: ScanDropZoneViewProps) {
  if (phase.kind !== "armed") {
    return (
      <section data-role="scan-upload" className="scan-upload">
        <span aria-hidden="true" className="scan-upload__tile">
          STL
        </span>
        <span className="scan-upload__text">
          <strong className="scan-upload__title">Drop a scan file</strong>
          <span className="scan-upload__sub">
            STL · upper or lower jaw · one folder per case
          </span>
        </span>
        {phase.kind === "done" && (
          /* No direction: since the upload OPENS the case (client 2026-08-04) the
             operator is normally already on it when this would render, and the
             zone no longer sits under the list it used to point at. */
          <span data-role="upload-done" className="scan-upload__done">
            Case {phase.caseId} landed.
          </span>
        )}
        <button
          type="button"
          data-role="upload-browse"
          className="button button--ghost button--small"
          onClick={onBrowse}
        >
          browse files
        </button>
      </section>
    );
  }
  return (
    <section data-role="scan-upload" className="scan-upload scan-upload--armed">
      <span className="scan-upload__text">
        <strong className="scan-upload__title">{phase.filename}</strong>
        <span className="scan-upload__sub">
          The folder name becomes the case id and the doctor line; a name containing
          a library system preselects its construction part.
        </span>
      </span>
      <label className="scan-upload__folder">
        case folder
        <input
          data-role="upload-folder"
          className="scan-upload__input"
          value={phase.folder}
          disabled={phase.busy}
          onChange={(event) => onFolder(event.target.value)}
        />
      </label>
      <button
        type="button"
        data-role="upload-go"
        className="button button--primary button--small"
        disabled={phase.busy || !uploadNameUsable(phase.folder)}
        onClick={onUpload}
      >
        {phase.busy ? "Uploading…" : "Upload this scan"}
      </button>
      <button
        type="button"
        data-role="upload-cancel"
        className="button button--ghost button--small"
        disabled={phase.busy}
        onClick={onCancel}
      >
        Cancel
      </button>
      {phase.error !== null && (
        <span data-role="upload-error" role="alert" className="panel__error">
          {phase.error}
        </span>
      )}
    </section>
  );
}

/** The drop zone's wiring: browse or drag in ONE file, name its folder, upload.
 * The dashed border is honest now — the zone really accepts the drag (§10-AB.3
 * retiring the 2026-07-31 refusal and its reason together). */
function ScanDropZone({ onUploaded }: { readonly onUploaded: (id: string) => void }) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [folder, setFolder] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [doneCase, setDoneCase] = useState<string | null>(null);

  const arm = (picked: File) => {
    setFile(picked);
    setFolder(suggestedUploadFolder(picked.name));
    setError(null);
    setDoneCase(null);
  };

  const upload = async () => {
    if (file === null) return;
    setBusy(true);
    setError(null);
    // the filename travels as-is when the name rule accepts it; otherwise the
    // sanitized stem keeps the jaw-suggesting words without the refused characters
    const filename = uploadNameUsable(file.name)
      ? file.name
      : `${suggestedUploadFolder(file.name)}.stl`;
    const result = await uploadScan(folder, filename, file);
    setBusy(false);
    if (result.kind === "ok") {
      setFile(null);
      setDoneCase(result.data.case_id);
      onUploaded(result.data.case_id);
    } else {
      setError(result.detail);
    }
  };

  const phase =
    file !== null
      ? ({ kind: "armed", filename: file.name, folder, error, busy } as const)
      : doneCase !== null
        ? ({ kind: "done", caseId: doneCase } as const)
        : ({ kind: "idle" } as const);

  return (
    <div
      className="scan-upload__zone"
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        const dropped = event.dataTransfer.files?.[0];
        if (dropped !== undefined) arm(dropped);
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".stl,.STL"
        hidden
        onChange={(event) => {
          const picked = event.target.files?.[0];
          if (picked !== undefined) arm(picked);
          event.target.value = "";
        }}
      />
      <ScanDropZoneView
        phase={phase}
        onBrowse={() => inputRef.current?.click()}
        onFolder={setFolder}
        onUpload={() => void upload()}
        onCancel={() => {
          setFile(null);
          setError(null);
        }}
      />
    </div>
  );
}

/** The whole-worklist demo reset's three faces — stated states, statically
 * testable; the ACT is the container's sequential POSTs. */
export interface ResetAllViewProps {
  readonly phase:
    | { readonly kind: "idle" }
    | { readonly kind: "confirming" }
    | { readonly kind: "working"; readonly done: number; readonly total: number }
    | { readonly kind: "error"; readonly detail: string };
  readonly count: number;
  readonly onAsk?: () => void;
  readonly onConfirm?: () => void;
  readonly onCancel?: () => void;
}

export function ResetAllView({
  phase,
  count,
  onAsk = () => undefined,
  onConfirm = () => undefined,
  onCancel = () => undefined,
}: ResetAllViewProps) {
  if (phase.kind === "working") {
    return (
      <div data-role="reset-all-working" className="busy-state" role="status">
        <span className="busy-state__spinner" aria-hidden="true" />
        <span>
          Resetting case {phase.done + 1} of {phase.total}…
        </span>
      </div>
    );
  }
  if (phase.kind === "confirming") {
    return (
      <div data-role="reset-all-confirm" role="alert" className="switch-confirm">
        <p className="switch-confirm__words">{resetAllWords(count)}</p>
        <div className="switch-confirm__actions">
          <button
            type="button"
            data-role="reset-all-go"
            className="button button--primary button--small"
            onClick={onConfirm}
          >
            Reset all cases
          </button>
          <button
            type="button"
            data-role="reset-all-cancel"
            className="button button--secondary button--small"
            onClick={onCancel}
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }
  return (
    <>
      <button
        type="button"
        data-role="reset-all-ask"
        className="button button--ghost button--small"
        onClick={onAsk}
      >
        Reset all cases (demo)
      </button>
      {phase.kind === "error" && (
        <span data-role="reset-all-error" role="alert" className="panel__error">
          {phase.detail}
        </span>
      )}
    </>
  );
}

/** The container: consent first (the visible-reset doctrine), then one POST per
 * case — the per-case reset's own endpoint, sequentially so a refusal names its
 * case and stops rather than scattering. */
function ResetAllControl({
  caseIds,
  onDone,
}: {
  readonly caseIds: readonly string[];
  readonly onDone: () => void;
}) {
  const [phase, setPhase] = useState<ResetAllViewProps["phase"]>({ kind: "idle" });
  const confirm = async () => {
    for (let i = 0; i < caseIds.length; i += 1) {
      setPhase({ kind: "working", done: i, total: caseIds.length });
      const result = await postCaseReset(caseIds[i]!);
      if (result.kind !== "ok") {
        setPhase({
          kind: "error",
          detail: `case ${caseIds[i]}: ${result.detail}`,
        });
        onDone(); // whatever DID reset is the new truth — re-read it
        return;
      }
    }
    setPhase({ kind: "idle" });
    onDone();
  };
  return (
    <ResetAllView
      phase={phase}
      count={caseIds.length}
      onAsk={() => setPhase({ kind: "confirming" })}
      onConfirm={() => void confirm()}
      onCancel={() => setPhase({ kind: "idle" })}
    />
  );
}

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
      <p data-role="scan-upload-note" className="scan-arrival__note">
        {SCAN_UPLOAD_NOTE}
      </p>
    </section>
  );
}

interface WorklistScreenProps {
  readonly state: FetchState<readonly unknown[]>;
  /** Fired when an upload lands, with the new case id — the page refetches. */
  readonly onUploaded?: (id: string) => void;
  /** Fired when the demo reset finishes (or stops on a refusal) — the page
   * refetches; whatever DID reset is the new truth. */
  readonly onReset?: () => void;
}

/** The presentational screen — every branch is a stated one, testable statically. */
export function WorklistScreen({
  state,
  onUploaded = () => undefined,
  onReset = () => undefined,
}: WorklistScreenProps) {
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
  // The blocked-first order is domain/worklist's; these groups only SLICE it so each
  // band can render as the comp's card grid under its caption. Concatenating the
  // groups reproduces `entries` exactly — no re-sorting here.
  const groups: { band: number; entries: WorklistEntry[] }[] = [];
  for (const entry of entries) {
    const band = bandOf(entry);
    const last = groups[groups.length - 1];
    if (last !== undefined && last.band === band) last.entries.push(entry);
    else groups.push({ band, entries: [entry] });
  }
  return (
    <section data-role="worklist" className="worklist">
      <h2 className="worklist__title">Worklist</h2>
      {/* The comp's lead, whole — its "drop a new scan" clause became TRUE when
          §10-AB.3 landed the real upload below. */}
      <p className="worklist__lead">
        Open a case from the worklist below, or drop a new scan. Detection proposes
        a variant per cap site; you declare the truth in Alignment.
      </p>
      {/* THE ACT THAT STARTS A CASE LEADS THE PAGE (client 2026-08-04: "'drop a
          scan file' should be at the top of the page"). This REVERSES the earlier
          "below the work, not above it" placement on the client's own ruling; the
          procedure note keeps the foot, because reading it is still not what the
          morning opens this page for. */}
      <ScanDropZone onUploaded={onUploaded} />
      {entries.length === 0 ? (
        <p data-role="worklist-empty" className="panel__copy">
          No cases yet — the case service found nothing to work on. New scans appear
          here as soon as they land in the data root.
        </p>
      ) : (
        groups.map((group) => (
          <section key={group.band} className="worklist__band-group">
            {BAND_LABELS[group.band] !== undefined && (
              <p
                className={`worklist-band${
                  group.band <= 0 ? " worklist-band--attention" : ""
                }`}
              >
                {BAND_LABELS[group.band]}
              </p>
            )}
            <ol className="worklist__grid">
              {group.entries.map((entry) => (
                <WorklistEntryItem
                  key={
                    entry.kind === "row" ? entry.row.id : `unreadable-${entry.index}`
                  }
                  entry={entry}
                />
              ))}
            </ol>
          </section>
        ))
      )}
      {entries.length > 0 && (
        /* THE DEMO RESET, WHOLE-LIST (client 2026-08-04: "In the home we need a
           button to reset all cases") — the per-case reset's own endpoint, once
           per case, behind the same consent ceremony every reset here gets. At
           the FOOT with the procedure note: it is housekeeping, not the work. */
        <div data-role="reset-all" className="worklist__reset-all">
          <ResetAllControl
            caseIds={entries
              .filter((entry) => entry.kind === "row")
              .map((entry) => (entry as { row: { id: string } }).row.id)}
            onDone={onReset}
          />
        </div>
      )}
      <ScanArrival />
    </section>
  );
}

export function WorklistPage() {
  const [state, setState] = useState<FetchState<readonly unknown[]>>({
    kind: "loading",
  });
  // bumped by the demo reset: whatever DID reset is the new truth — re-read it
  const [generation, setGeneration] = useState(0);
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    void fetchWorklist().then((result) => {
      if (!cancelled) setState(result);
    });
    return () => {
      cancelled = true;
    };
  }, [generation]);

  return (
    <div className="page">
      {/* AN UPLOAD OPENS ITS CASE (client 2026-08-04). This replaces a refetch of
          the worklist the operator is leaving: coming back re-mounts this page and
          re-reads it, and discovery is uncached server-side, so nothing needs to be
          kept warm. The stage is the case shell's own to resolve. */}
      <WorklistScreen
        state={state}
        onUploaded={(id) => navigate(uploadedCaseTarget(id))}
        onReset={() => setGeneration((current) => current + 1)}
      />
    </div>
  );
}
