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
 * ON THE DEFENSIVE GUARD (classifyWorklist): the BFF's WorklistRow defines NO per-row
 * error field today — a corrupt session file makes the whole endpoint refuse loudly
 * (bff/session.py), which the page surfaces as the error banner. The guard here only
 * protects the list against a malformed ELEMENT, rendering it as an inert
 * "unreadable" row instead of crashing every readable one. A real per-row error
 * contract is slice 5a's to define on the BFF — deliberately not invented here.
 *
 * Display logic only (AM-4): every number in a row is the BFF's derivation; this
 * module orders and words them, and computes where a row resumes (domain/flow.ts).
 */
import type { SiteRollup, WorklistRow } from "../api/client";
import { factsFromWorklistRow, furthestStage } from "./flow";

export type WorklistEntry =
  | { readonly kind: "row"; readonly row: WorklistRow }
  | { readonly kind: "unreadable"; readonly index: number; readonly id: string | null };

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
    typeof v["confirmed"] === "boolean"
  );
};

export function classifyWorklist(
  data: readonly unknown[],
): readonly WorklistEntry[] {
  return data.map((raw, index): WorklistEntry => {
    if (isWorklistRow(raw)) return { kind: "row", row: raw };
    const id =
      typeof raw === "object" && raw !== null &&
      typeof (raw as Record<string, unknown>)["id"] === "string"
        ? ((raw as Record<string, unknown>)["id"] as string)
        : null;
    return { kind: "unreadable", index, id };
  });
}
