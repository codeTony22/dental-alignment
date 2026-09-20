/**
 * Adjust-tool bindings the dock reuses — labels and one-liners from the product
 * Adjust toolbox, pointed at the REST case API instead of the BFF.
 */
export type AdjustToolId =
  | "fit-by-points"
  | "best-fit"
  | "rotation"
  | "mark-trench"
  | "auto-mark";

export interface AdjustToolInfo {
  readonly id: AdjustToolId;
  readonly label: string;
  readonly oneLiner: string;
}

export const ADJUST_TOOLS: readonly AdjustToolInfo[] = [
  {
    id: "fit-by-points",
    label: "Fit by points",
    oneLiner: "Mark a spot on the library part and the same spot on the scan.",
  },
  {
    id: "best-fit",
    label: "Best fit",
    oneLiner: "Re-run the pipeline's own refinement at a matching diameter.",
  },
  {
    id: "rotation",
    label: "Rotation",
    oneLiner: "Step the cap about its own axis. Reset restores the certified pose.",
  },
  {
    id: "mark-trench",
    label: "Mark trench",
    oneLiner: "Click the coded trench on the scan; the cap turns to match.",
  },
  {
    id: "auto-mark",
    label: "Auto-mark",
    oneLiner: "Served landmarks are the part half — the scan half stays the operator's.",
  },
];

export const ROTATION_STEPS: readonly number[] = [-15, -5, -1, 1, 5, 15];
export const DEFAULT_DIAMETER_MM = 0.3;
