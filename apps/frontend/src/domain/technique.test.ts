import { describe, expect, it } from "vitest";
import { techniqueResult } from "../testing/fixtures";
import { SIGNAL_GROUP_ORDER } from "./signals";
import { missingSignalGroups, modeLabel, statusTone, traceByClass } from "./technique";

describe("technique mode words", () => {
  it("labels Intelligence the way the operator asked", () => {
    expect(modeLabel("intelligence")).toBe("Intelligence");
    expect(modeLabel("deterministic")).toBe("Deterministic");
  });

  it("already-optimal is a pass tone", () => {
    expect(statusTone("already_optimal")).toBe("pass");
    expect(statusTone("refused")).toBe("refuse");
  });

  it("splits the MCP trace by READ / DRY_RUN / COMMIT", () => {
    const result = techniqueResult("intelligence");
    expect(traceByClass(result.trace, "READ").map((s) => s.name)).toEqual([
      "get_landmarks", "get_seated", "get_site_signals", "get_acceptance",
    ]);
    expect(traceByClass(result.trace, "DRY_RUN").map((s) => s.name)).toEqual([
      "dry_run_best_fit",
    ]);
    expect(traceByClass(result.trace, "COMMIT").map((s) => s.name)).toEqual([
      "commit_best_fit",
    ]);
  });

  it("flags a reduced subset instead of silently dropping groups", () => {
    expect(missingSignalGroups(["seat", "fit"], SIGNAL_GROUP_ORDER)).toContain("capture");
    expect(missingSignalGroups(SIGNAL_GROUP_ORDER, SIGNAL_GROUP_ORDER)).toEqual([]);
  });
});
