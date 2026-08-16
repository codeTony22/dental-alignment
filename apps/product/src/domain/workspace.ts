/**
 * THE PANE WORKSPACE'S SHARED POLICY — what Alignment's and Adjustment's three-pane
 * workspaces agree on before either stage adds its own rules.
 */

/**
 * THE LINK'S OPENING STATE (client 2026-08-04: "Alignment and adjustment panels do
 * not share a global camera … create a toggle of this functionality").
 *
 * The toggle EXISTED on both stages (the viewer's OrbitLinkGroup mirrors a user
 * orbit into the sibling panes, each around its own content) — and it opened OFF
 * behind a terse chip, which is how a built feature gets reported as
 * missing. The panes are read side by side; rotating together is the reading the
 * comparison exists for, so LINKED is the opening state and unlinking is the
 * deliberate act. One constant, imported by both stages, so they cannot open in
 * different moods.
 */
export const PANES_OPEN_LINKED = true;

/** The toggle's face, shared by both stages for the same reason.
 *
 * The HTML prototype uses a single ⇹ glyph; pressed state is `aria-pressed` and
 * the green outline, and the button's `title` still spells the full sentence. */
export function paneLinkLabel(_linked: boolean): string {
  return "⇹";
}


// --- THE WORKSPACE ANALYSIS DIGEST (client 2026-08-10: "the evidence copy tool
// for the alignment page and adjustment page, to facilitate information
// gathering for debugging"). Composed from exactly what the Numbers & log
// panel already fetched — the served site numbers and the case log — plus the
// toolbar's own stats. Served words verbatim; nothing measured here. ------------

import type {
  CaseActivityView,
  SiteAcceptanceView,
} from "../api/client";
import type { WorkspaceStat } from "./declare";

export function workspaceAnalysisText(
  caseId: string,
  tooth: number | null,
  stats: readonly WorkspaceStat[],
  acceptance: SiteAcceptanceView | null,
  activity: CaseActivityView | null,
): string {
  const lines: string[] = [
    `# Workspace analysis digest — ${caseId}` +
      (tooth !== null ? ` · tooth ${tooth}` : ""),
  ];
  if (stats.length > 0) {
    lines.push("", "## Toolbar");
    for (const stat of stats) lines.push(`- ${stat.label}: ${stat.value}`);
  }
  if (acceptance !== null) {
    lines.push("", `## Site numbers (overall band: ${acceptance.overall_band})`);
    for (const m of acceptance.metrics) {
      const bounds =
        m.bands != null
          ? ` (pass <= ${m.bands.pass} · review <= ${m.bands.review})`
          : "";
      lines.push(
        `- ${m.label}: ${m.band} ${m.display ?? String(m.value)}${bounds}` +
          (m.note !== null ? ` — ${m.note}` : ""),
      );
    }
    for (const name of acceptance.missing ?? []) {
      lines.push(`- ${name}: not measured`);
    }
  }
  if (acceptance !== null && acceptance.stale_metrics.length > 0) {
    lines.push(
      `- stale after rework (row's own naming): ` +
        acceptance.stale_metrics.join(', '),
    );
  }
  if (activity !== null && activity.entries.length > 0) {
    lines.push("", `## Case log (last ${activity.entries.length} acts)`);
    for (const e of activity.entries) {
      lines.push(
        `- ${e.at} ${e.event}${e.tooth !== null ? ` · tooth ${e.tooth}` : ""}: ${e.detail}`,
      );
    }
  }
  lines.push(
    "",
    "## For the reviewer",
    "Served wording throughout. Read the log bottom-up for the causal chain;",
    "band edges and 'not measured' rows are where a complaint usually lives.",
  );
  return lines.join("\n");
}
