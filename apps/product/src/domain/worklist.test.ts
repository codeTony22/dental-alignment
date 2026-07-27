/**
 * The worklist's rules (plan §4 "Worklist first", AM-7), pinned: the blocked-first
 * sort order (flagged > in-progress > untouched > confirmed, unreadable entries above
 * all), resume-target computation, the row chips' words, and the defensive per-row
 * guard (the BFF defines no per-row error contract yet — see the module doc).
 */
import { describe, expect, it } from "vitest";
import { worklistRow } from "../testing/fixtures";
import {
  classifyWorklist,
  confirmChip,
  orderWorklist,
  resumeTarget,
  rollupLabel,
  runChip,
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
    const unreadable: WorklistEntry = { kind: "unreadable", index: 4, id: null };
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

describe("classifyWorklist — the defensive per-row guard", () => {
  it("passes well-shaped rows through", () => {
    const entries = classifyWorklist([untouched, flagged]);
    expect(entries).toEqual([
      { kind: "row", row: untouched },
      { kind: "row", row: flagged },
    ]);
  });

  it("marks a malformed row unreadable, keeping its id when one is legible", () => {
    const broken = { id: "case-broken", doctor: "Dr. X" }; // no sites/run_state
    expect(classifyWorklist([untouched, broken])).toEqual([
      { kind: "row", row: untouched },
      { kind: "unreadable", index: 1, id: "case-broken" },
    ]);
  });

  it("survives entries that are not objects at all", () => {
    expect(classifyWorklist([42, null])).toEqual([
      { kind: "unreadable", index: 0, id: null },
      { kind: "unreadable", index: 1, id: null },
    ]);
  });
});
