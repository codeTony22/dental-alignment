/**
 * Technique-mode display rules. No measurements — words only.
 *
 * Deterministic = one-shot pipeline refinement (best-fit) without an agent loop.
 * Intelligence  = walk the MCP READ / DRY_RUN / COMMIT surface; never invent
 *                 scan points or metrics.
 */
import type { TechniqueMode, TechniqueResultView, ToolTraceView } from "../api/client";

export const TECHNIQUE_MODES: readonly TechniqueMode[] = ["deterministic", "intelligence"];

export interface TechniqueModeInfo {
  readonly id: TechniqueMode;
  readonly label: string;
  readonly oneLiner: string;
}

export const TECHNIQUE_MODE_INFO: readonly TechniqueModeInfo[] = [
  {
    id: "deterministic",
    label: "Deterministic",
    oneLiner:
      "The pipeline's own refinement at the matching diameter. One act, no agent loop.",
  },
  {
    id: "intelligence",
    label: "Intelligence",
    oneLiner:
      "Drive alignment through the MCP tool surface — every signal read, then a dry-run, then a commit if the gates allow. Landmarks stay proposals; scan clicks are never invented.",
  },
];

export function modeLabel(mode: TechniqueMode): string {
  return TECHNIQUE_MODE_INFO.find((info) => info.id === mode)?.label ?? mode;
}

export function statusTone(status: string): "pass" | "flag" | "refuse" | "neutral" {
  if (status === "applied" || status === "already_optimal" || status === "measured") {
    return status === "already_optimal" || status === "applied" ? "pass" : "neutral";
  }
  if (status === "refused") return "refuse";
  return "flag";
}

export function statusWords(result: TechniqueResultView): string {
  if (result.status === "already_optimal") {
    return result.detail || "Already the best fit in this band — a pass, not a failure.";
  }
  return result.detail;
}

export function traceByClass(
  trace: readonly ToolTraceView[],
  classification: ToolTraceView["classification"],
): readonly ToolTraceView[] {
  return trace.filter((step) => step.classification === classification);
}

export function missingSignalGroups(
  served: readonly string[],
  expected: readonly string[],
): readonly string[] {
  const have = new Set(served);
  return expected.filter((name) => !have.has(name));
}
