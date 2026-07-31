/**
 * The worklist's rules (plan §4 "Worklist first", AM-7), pinned: the blocked-first
 * sort order (flagged > in-progress > untouched > confirmed, unreadable entries above
 * all), resume-target computation, the row chips' words, and the per-row error
 * contract (slice 5a): a row the BFF could not derive session facts for arrives with
 * `error` set and every session-derived field null — the guard surfaces the BFF's own
 * words instead of inventing a diagnosis, and stays defensive about rows that match
 * neither shape.
 */
import { describe, expect, it } from "vitest";
import { worklistErrorRow, worklistRow } from "../testing/fixtures";
import {
  classifyWorklist,
  confirmChip,
  orderWorklist,
  resumeTarget,
  rollupLabel,
  runChip,
  SCAN_ARRIVAL,
  SCAN_UPLOAD_ABSENT,
  worklistBand,
  type WorklistEntry,
} from "./worklist";

const flagged = worklistRow({
  id: "case-flagged",
  sites: { total: 3, declared: 3, ready: 2, flagged: 1 },
  run_state: "done",
});
const inProgress = worklistRow({
  id: "case-progress",
  sites: { total: 2, declared: 1, ready: 0, flagged: 0 },
});
const untouched = worklistRow({ id: "case-untouched" });
const confirmed = worklistRow({
  id: "case-confirmed",
  sites: { total: 2, declared: 2, ready: 2, flagged: 0 },
  run_state: "done",
  confirmed: true,
});

describe("worklistBand — blocked-first (the documented order)", () => {
  it("flagged cases block the morning and come first", () => {
    expect(worklistBand(flagged)).toBe(0);
  });

  it("touched cases (any site declared, or a run) are in progress", () => {
    expect(worklistBand(inProgress)).toBe(1);
    expect(worklistBand(worklistRow({ run_state: "running" }))).toBe(1);
  });

  it("untouched cases wait behind in-progress ones", () => {
    expect(worklistBand(untouched)).toBe(2);
  });

  it("confirmed cases sink to the bottom — even with flags (they were acknowledged at Deliver)", () => {
    expect(worklistBand(confirmed)).toBe(3);
    expect(worklistBand({ ...flagged, confirmed: true })).toBe(3);
  });
});

describe("orderWorklist", () => {
  it("orders unreadable > flagged > in-progress > untouched > confirmed", () => {
    const unreadable: WorklistEntry = {
      kind: "unreadable",
      index: 4,
      id: null,
      error: null,
    };
    const entries: readonly WorklistEntry[] = [
      { kind: "row", row: confirmed },
      { kind: "row", row: untouched },
      { kind: "row", row: flagged },
      { kind: "row", row: inProgress },
      unreadable,
    ];
    const ordered = orderWorklist(entries);
    expect(
      ordered.map((e) => (e.kind === "row" ? e.row.id : "unreadable")),
    ).toEqual([
      "unreadable",
      "case-flagged",
      "case-progress",
      "case-untouched",
      "case-confirmed",
    ]);
  });

  it("is deterministic within a band: rows sort by case id", () => {
    const b = worklistRow({ id: "case-b" });
    const a = worklistRow({ id: "case-a" });
    const ordered = orderWorklist([
      { kind: "row", row: b },
      { kind: "row", row: a },
    ]);
    expect(ordered.map((e) => (e.kind === "row" ? e.row.id : "?"))).toEqual([
      "case-a",
      "case-b",
    ]);
  });
});

describe("resumeTarget — the row opens at the session's furthest stage", () => {
  it("a fresh case with detected sites resumes at declare", () => {
    expect(resumeTarget(untouched)).toBe("/case/case-untouched/declare");
  });

  it("a case with no sites resumes at intake", () => {
    const empty = worklistRow({
      id: "case-empty",
      sites: { total: 0, declared: 0, ready: 0, flagged: 0 },
    });
    expect(resumeTarget(empty)).toBe("/case/case-empty/intake");
  });

  it("a running case with unresolved sites resumes at adjust", () => {
    const running = worklistRow({
      id: "case-running",
      sites: { total: 3, declared: 3, ready: 1, flagged: 0 },
      run_state: "running",
    });
    expect(resumeTarget(running)).toBe("/case/case-running/adjust");
  });

  it("a fully resolved case resumes at deliver", () => {
    expect(resumeTarget(flagged)).toBe("/case/case-flagged/deliver");
  });
});

describe("the row's words", () => {
  it("rollupLabel states declared / ready / flagged", () => {
    expect(rollupLabel(flagged.sites)).toBe("3 declared / 2 ready / 1 flagged");
  });

  it("runChip names the run state, honestly absent when none", () => {
    expect(runChip("none")).toBe("no run");
    expect(runChip("queued")).toBe("queued");
    expect(runChip("refused")).toBe("refused");
  });

  it("confirmChip states confirmation either way", () => {
    expect(confirmChip(true)).toBe("confirmed");
    expect(confirmChip(false)).toBe("unconfirmed");
  });
});

describe("classifyWorklist — the per-row error contract and the defensive guard", () => {
  it("passes well-shaped rows through", () => {
    const entries = classifyWorklist([untouched, flagged]);
    expect(entries).toEqual([
      { kind: "row", row: untouched },
      { kind: "row", row: flagged },
    ]);
  });

  it("an error row (the BFF's slice-5a contract) is unreadable WITH the BFF's words", () => {
    const errorRow = worklistErrorRow({
      id: "case-corrupt",
      error: "corrupt session file … — refusing to silently reset flow state",
    });
    expect(classifyWorklist([untouched, errorRow])).toEqual([
      { kind: "row", row: untouched },
      {
        kind: "unreadable",
        index: 1,
        id: "case-corrupt",
        error: "corrupt session file … — refusing to silently reset flow state",
      },
    ]);
  });

  it("marks a malformed row unreadable with no invented diagnosis (error: null)", () => {
    const broken = { id: "case-broken", doctor: "Dr. X" }; // no sites/run_state
    expect(classifyWorklist([untouched, broken])).toEqual([
      { kind: "row", row: untouched },
      { kind: "unreadable", index: 1, id: "case-broken", error: null },
    ]);
  });

  it("survives entries that are not objects at all", () => {
    expect(classifyWorklist([42, null])).toEqual([
      { kind: "unreadable", index: 0, id: null, error: null },
      { kind: "unreadable", index: 1, id: null, error: null },
    ]);
  });
});

/**
 * THE SCAN-ARRIVAL STATEMENT (design flow.dc.html 76-83; gap "a scan arrives",
 * 2026-07-31). These tests exist to keep the panel's copy TRUE, because the design
 * prototype pressures it toward two claims that are false here — see SCAN_ARRIVAL's
 * own doc for the measurements that refuted them.
 */
describe("the scan-arrival statement", () => {
  const prose = SCAN_ARRIVAL.map((step) => `${step.title} ${step.detail}`).join(" ");

  it("has a stable, unique key per step and says something in each", () => {
    const keys = SCAN_ARRIVAL.map((step) => step.key);
    expect(new Set(keys).size).toBe(keys.length);
    for (const step of SCAN_ARRIVAL) {
      expect(step.title.length).toBeGreaterThan(0);
      expect(step.detail.length).toBeGreaterThan(0);
    }
  });

  it("states the discovery rules a case is actually minted by", () => {
    expect(prose).toContain("*.stl");
    expect(prose).toContain("The folder name is the case");
    expect(prose).toContain("lower"); // the jaw suggestion's one keyword
  });

  it("refuses the prototype's PLY claim — discovery globs *.stl and nothing else", () => {
    expect(prose).toContain("a .ply on its own will not appear here");
  });

  it("refuses the prototype's watertight claim — 0 of 6 client scans are watertight", () => {
    expect(prose).toContain("Watertightness is not a requirement");
  });

  it("never invites a browser drag — this app moves no files", () => {
    // "drop" is the prototype's whole verb. If it ever reappears here, an operator
    // will try dragging a file onto a page that cannot accept one.
    expect(prose.toLowerCase()).not.toContain("drop");
    expect(SCAN_UPLOAD_ABSENT.toLowerCase()).not.toContain("drop");
    expect(SCAN_UPLOAD_ABSENT).toContain("no browser upload");
  });
});
