/**
 * Display bindings for the full adjust/MCP signal taxonomy.
 * Values are rendered verbatim; this module chooses order and labels only.
 */
export const SIGNAL_GROUP_ORDER: readonly string[] = [
  "capture",
  "measurement_honesty",
  "seat",
  "fit",
  "correspondence",
  "certification",
  "residue",
  "acceptance",
  "landmarks",
  "clocking",
  "stability",
  "guidance",
];

export const SIGNAL_GROUP_LABELS: Record<string, string> = {
  capture: "Capture",
  measurement_honesty: "Measurement honesty",
  seat: "Seat",
  fit: "Fit",
  correspondence: "Correspondence",
  certification: "Certification",
  residue: "Residue",
  acceptance: "Acceptance",
  landmarks: "Landmarks",
  clocking: "Clocking",
  stability: "Stability",
  guidance: "Guidance",
};

export function groupLabel(name: string): string {
  return SIGNAL_GROUP_LABELS[name] ?? name;
}

export function displayValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(3);
  }
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    if (value.length === 0) return "—";
    if (value.every((item) => typeof item === "string")) return value.join("; ");
    return `${value.length} items`;
  }
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    if (typeof record.display === "string") return record.display;
    if (typeof record.detail === "string") return record.detail;
    if (typeof record.level === "string") return record.level;
    return JSON.stringify(value);
  }
  return String(value);
}

export function scalarEntries(
  group: Record<string, unknown> | undefined,
): readonly { key: string; value: string }[] {
  if (group === undefined) return [];
  const skip = new Set(["click_precision_context", "metrics", "catalog_keys", "items", "actions"]);
  const rows: { key: string; value: string }[] = [];
  for (const [key, value] of Object.entries(group)) {
    if (skip.has(key)) continue;
    if (key === "missing" && value === true) {
      rows.push({ key, value: "not read (mesh not available or read failed)" });
      continue;
    }
    rows.push({ key, value: displayValue(value) });
  }
  return rows;
}

export function guidanceActions(group: Record<string, unknown> | undefined): readonly string[] {
  const actions = group?.["actions"];
  if (!Array.isArray(actions)) return [];
  return actions.filter((item): item is string => typeof item === "string");
}

export function acceptanceMetrics(
  group: Record<string, unknown> | undefined,
): readonly Record<string, unknown>[] {
  const metrics = group?.["metrics"];
  if (!Array.isArray(metrics)) return [];
  return metrics.filter((item): item is Record<string, unknown> =>
    typeof item === "object" && item !== null);
}

export function landmarkItems(
  group: Record<string, unknown> | undefined,
): readonly Record<string, unknown>[] {
  const items = group?.["items"];
  if (!Array.isArray(items)) return [];
  return items.filter((item): item is Record<string, unknown> =>
    typeof item === "object" && item !== null);
}
