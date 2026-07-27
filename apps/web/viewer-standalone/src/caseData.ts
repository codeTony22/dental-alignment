import type { PartRole } from "./palette";

/** One inlined STL part: which role it plays in a composite, and its base64-encoded bytes. */
export interface CasePart {
  readonly name: string;
  readonly role: PartRole;
  readonly b64: string;
}

/** Per-site summary row for the header meta table — mirrors the app's RunSiteResult, flattened. */
export interface CaseSiteMeta {
  readonly tooth: number;
  readonly variant: string;
  readonly fitAvgMm: number | null;
  readonly fitMaxMm: number | null;
  readonly seatMethod: "rim" | "icp" | null;
  readonly guidanceLevel: "ready" | "attention" | "action-needed" | null;
}

export interface CaseMeta {
  readonly sites: readonly CaseSiteMeta[];
}

/** The full payload the emitter writes as window.__CASE__ before loading this bundle. */
export interface CaseData {
  readonly caseId: string;
  readonly parts: readonly CasePart[];
  readonly meta: CaseMeta;
}

/** One of the three staged deliverable views, as a set of parts to render together. */
export interface StagedView {
  readonly label: string;
  readonly parts: readonly CasePart[];
}

/**
 * Group parts by role — deliberately "dumb": which file plays which role is entirely the
 * emitter's decision (parts[].role), this just buckets what it's given.
 */
export function groupPartsByRole(parts: readonly CasePart[]): Record<PartRole, CasePart[]> {
  const groups: Record<PartRole, CasePart[]> = { arch: [], cap: [], construction: [] };
  for (const part of parts) {
    groups[part.role].push(part);
  }
  return groups;
}

/**
 * The three staged views, built purely from role grouping:
 * 1. Healing-cap alignment: every arch part + every cap part.
 * 2. Construction in arch: every arch part + every construction part.
 * 3. Construction alone, one view per tooth (from meta.sites, matched to a construction part
 *    by name containing "-{tooth}-"; falls back to showing all construction parts together if
 *    a per-tooth match can't be found, so this degrades gracefully rather than showing nothing).
 */
export function buildStagedViews(parts: readonly CasePart[], meta: CaseMeta): StagedView[] {
  const groups = groupPartsByRole(parts);

  const views: StagedView[] = [
    {
      label: "Healing-cap alignment",
      parts: [...groups.arch, ...groups.cap],
    },
    {
      label: "Construction in arch",
      parts: [...groups.arch, ...groups.construction],
    },
  ];

  for (const site of meta.sites) {
    const toothMarker = `-${site.tooth}-`;
    const matches = groups.construction.filter((p) => p.name.includes(toothMarker));
    const partsForTooth = matches.length > 0 ? matches : groups.construction;
    views.push({
      label: `Construction alone — tooth ${site.tooth}`,
      parts: partsForTooth,
    });
  }

  return views;
}
