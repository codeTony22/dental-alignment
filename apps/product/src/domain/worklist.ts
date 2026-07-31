/**
 * THE WORKLIST'S RULES — plan §4 "Worklist first" (AM-7): the `/` screen is the
 * 20-scan morning's home, one row per case, sorted so the blocked work is on top.
 *
 * THE EXACT SORT ORDER (tested in worklist.test.ts):
 *   band -1  unreadable entries — a row the guard could not read outranks everything,
 *            because work that cannot even be triaged is the most blocked there is;
 *   band 0   flagged — sites.flagged > 0: a human verdict is owed;
 *   band 1   in-progress — touched (any site declared, or a run exists) but not done;
 *   band 2   untouched — nothing declared, no run: fresh intake waiting its turn;
 *   band 3   confirmed — finished work sinks to the bottom. Confirmation WINS over
 *            flags: a confirmed case's flags were acknowledged row-by-row at Deliver
 *            (plan §4), so it is not open work any more.
 * Within a band, rows sort by case id so the order is deterministic across reloads.
 *
 * ON THE GUARD (classifyWorklist): since slice 5a the BFF's per-row error contract is
 * real — a corrupt session arrives as a row whose `error` carries the store's refusal
 * and whose session-derived facts are all null (api/client.WorklistRowError). Such a
 * row becomes an "unreadable" entry WITH the BFF's own words; the defensive fallback
 * (a malformed element matching neither shape) stays, rendering with `error: null` —
 * no invented diagnosis — so a half-broken payload still cannot crash the readable
 * rows beside it.
 *
 * Display logic only (AM-4): every number in a row is the BFF's derivation; this
 * module orders and words them, and computes where a row resumes (domain/flow.ts).
 */
import type { SiteRollup, WorklistRow } from "../api/client";
import { factsFromWorklistRow, furthestStage } from "./flow";

export type WorklistEntry =
  | { readonly kind: "row"; readonly row: WorklistRow }
  | {
      readonly kind: "unreadable";
      readonly index: number;
      readonly id: string | null;
      /** The BFF's stated refusal (the error contract), or null for the fallback. */
      readonly error: string | null;
    };

/** Bands 0-3 per the module doc; unreadable entries are handled by orderWorklist. */
export function worklistBand(row: WorklistRow): 0 | 1 | 2 | 3 {
  if (row.confirmed) return 3;
  if (row.sites.flagged > 0) return 0;
  if (row.sites.declared > 0 || row.run_state !== "none") return 1;
  return 2;
}

export function orderWorklist(
  entries: readonly WorklistEntry[],
): readonly WorklistEntry[] {
  const band = (entry: WorklistEntry): number =>
    entry.kind === "unreadable" ? -1 : worklistBand(entry.row);
  const key = (entry: WorklistEntry): string =>
    entry.kind === "unreadable" ? String(entry.index) : entry.row.id;
  return [...entries].sort(
    (a, b) => band(a) - band(b) || key(a).localeCompare(key(b)),
  );
}

/** Where opening the row lands: the session's furthest stage (AM-7 resume). */
export function resumeTarget(row: WorklistRow): string {
  return `/case/${row.id}/${furthestStage(factsFromWorklistRow(row))}`;
}

export function rollupLabel(sites: SiteRollup): string {
  return `${sites.declared} declared / ${sites.ready} ready / ${sites.flagged} flagged`;
}

export function runChip(runState: string): string {
  return runState === "none" ? "no run" : runState;
}

export function confirmChip(confirmed: boolean): string {
  return confirmed ? "confirmed" : "unconfirmed";
}

/**
 * HOW A SCAN ACTUALLY ARRIVES (design flow.dc.html 76-83; gap "a scan arrives",
 * 2026-07-31).
 *
 * The design prototype puts a dashed drop zone here — "Drop a scan file · STL or PLY ·
 * upper or lower jaw · watertight mesh", with a "browse files" button. It is scenery:
 * `browseUpload: () => this.pickScan(SCANS[0].id)` (flow.dc.html:1105) selects a
 * fixture. Shipping that zone would teach a workflow this installation does not have,
 * so the affordance is a STATEMENT instead, and every clause of it was checked against
 * the code that really mints cases (case_prep.application.cases.discover_cases).
 *
 * THREE OF THE PROTOTYPE'S FOUR CLAIMS ARE WRONG HERE, and the copy says so:
 *
 *  - "PLY" — discovery accepts STL and nothing else (cases.py). A PLY-only folder is
 *    not a case and never appears; pinned by
 *    worker tests/test_application.py::test_a_folder_holding_only_a_ply_is_not_a_case.
 *  - "watertight mesh" — measured 2026-07-31 over the client's shipped tree: 0 of 6
 *    real intraoral scans is watertight (two are not even a single body). Advertising
 *    watertightness as an acceptance criterion would have every scan this product has
 *    ever run read as invalid, and would send a lab hunting a scanner fault that is
 *    not there. Nothing checks it, and nothing should.
 *  - "Drop a scan file" — no file travels through this app at all. See
 *    SCAN_UPLOAD_ABSENT for what a real browser ingest would take.
 *
 * The one true claim is "upper or lower jaw", and even that is a SUGGESTION read off
 * the filename (cases.py:89), settled by the operator at Intake.
 *
 * Display copy, not a rule: nothing here is computed and nothing here is a verdict.
 * It lives in domain/ so the claims have one home and a test that pins them.
 */
export interface ScanArrivalStep {
  readonly key: "folder" | "stl" | "name" | "jaw" | "appears" | "unchecked";
  readonly title: string;
  readonly detail: string;
}

export const SCAN_ARRIVAL: readonly ScanArrivalStep[] = [
  {
    key: "folder",
    title: "One folder per case, in this installation's scan root",
    detail:
      "The lab copies the case folder into the scan root this service was configured " +
      "with — the same place the morning's scans already land. The runbook names the " +
      "path for this installation.",
  },
  {
    key: "stl",
    title: "An STL inside it",
    detail:
      "Discovery looks for STL files and nothing else; the extension may be upper or " +
      "lower case. A folder with no STL is not a case, and a .ply on its own will not " +
      "appear here at all — convert it to STL first. If a folder holds several STLs " +
      "only the first by name becomes that case's scan and the others are ignored " +
      "without a warning, so keep one folder per case: a two-arch export belongs in " +
      "two folders, not one.",
  },
  {
    key: "name",
    title: "The folder name is the case",
    detail:
      "It becomes the case id and the doctor line on the rows above (a leading " +
      "“doctor-” is stripped, and only a leading one — patient-doctor-4471 keeps " +
      "its name in full). If the name contains a library system — " +
      "neodent-gm, zimmer-4.5 — that system's construction part is preselected at " +
      "Intake, longest match winning. A name matching no system is still a case; you " +
      "choose the part yourself.",
  },
  {
    key: "jaw",
    title: "The scan filename suggests the jaw",
    detail:
      "A filename containing “lower” reads as a lower jaw; anything else " +
      "reads as upper. It is only a suggestion — Intake's jaw control settles it.",
  },
  {
    key: "appears",
    title: "Reload to see it",
    detail:
      "This worklist re-reads the scan root every time it loads: nothing is cached and " +
      "no service needs restarting. Copy the folder in, then reload this page.",
  },
  {
    key: "unchecked",
    title: "Nothing here opens the mesh",
    detail:
      "Discovery reads names and directory shape only, so a case appears within " +
      "seconds of landing however large the scan is. The cost is that a file which is " +
      "not a readable mesh still gets a row, and only says so when Intake runs " +
      "detection on it, in the detector's own words. Watertightness is not a " +
      "requirement and is not checked — none of the client's own intraoral scans is " +
      "watertight.",
  },
];

/** Why there is no control here, said plainly so nobody hunts for the button the
 *  design drew. The honest alternative to a zone that pretends. */
export const SCAN_UPLOAD_ABSENT =
  "There is no browser upload. Files do not travel through this app — scans reach the " +
  "scan root the way the lab already moves them, and this worklist reads what is " +
  "there. Nothing on this page will accept a dragged file: if a case is missing here, " +
  "it is missing from the scan root.";

const isRollup = (value: unknown): value is SiteRollup => {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (["total", "declared", "ready", "flagged"] as const).every(
    (field) => typeof v[field] === "number",
  );
};

const isWorklistRow = (value: unknown): value is WorklistRow => {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v["id"] === "string" &&
    typeof v["doctor"] === "string" &&
    typeof v["jaw"] === "string" &&
    isRollup(v["sites"]) &&
    typeof v["run_state"] === "string" &&
    typeof v["confirmed"] === "boolean" &&
    typeof v["detected"] === "boolean" &&
    typeof v["choices_complete"] === "boolean"
  );
};

/** The error contract's shape: a string `error` beside a legible identity. Checked
 * BEFORE the healthy-row guard so a row that somehow carried both never renders as
 * workable — stated trouble outranks claimed facts. */
const errorOf = (value: unknown): string | null => {
  if (typeof value !== "object" || value === null) return null;
  const e = (value as Record<string, unknown>)["error"];
  return typeof e === "string" ? e : null;
};

export function classifyWorklist(
  data: readonly unknown[],
): readonly WorklistEntry[] {
  return data.map((raw, index): WorklistEntry => {
    const id =
      typeof raw === "object" && raw !== null &&
      typeof (raw as Record<string, unknown>)["id"] === "string"
        ? ((raw as Record<string, unknown>)["id"] as string)
        : null;
    const error = errorOf(raw);
    if (error !== null) return { kind: "unreadable", index, id, error };
    if (isWorklistRow(raw)) return { kind: "row", row: raw };
    return { kind: "unreadable", index, id, error: null };
  });
}
