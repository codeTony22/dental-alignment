/**
 * THE CLAMP READ-OUT — what the run ACTUALLY applied when the operator's gingival relief was more
 * than the chosen part could take.
 *
 * THREE NUMBERS, NOT TWO (the ubiquitous language this module fixes in place):
 *
 *   REQUESTED — what the lab typed. Never rewritten, never rescaled, never re-typed for them.
 *   APPLIED   — what the run used, after clamping to the part's ceiling. May be lower.
 *   ACHIEVED  — what the emitted part measures (domain/gingivalOffset). Lower again, because the
 *               SDF round trip closes part of the clearance back.
 *
 * The clamp is the middle one, and it is the one that MUST NOT BE MISSED: it is a change to what
 * the lab asked for, made by the software, in the interest of not shipping a part whose screw
 * channel has no wall left. Silence here would be the worst of both worlds — the operator would
 * read the requested number in the UI and hold a part built to a different one.
 *
 * So every read-out this module produces names both numbers and the reason, and the component
 * that renders it (components/ReliefClampNotice) is mounted in all three places the operator can
 * be looking: the results block, the verify dialog, and the selection column beside the input.
 */
import type { GingivalOffsetReading, RunSiteResult } from "./types";

/** One site whose relief was clamped: the two numbers, the ceiling, and the backend's reason. */
export interface SiteReliefClamp {
  readonly tooth: number;
  readonly requestedMm: number;
  readonly appliedMm: number;
  /** The ceiling the run clamped to (usually === appliedMm); null when it did not say. */
  readonly limitMm: number | null;
  /** The wall rule the ceiling protects (mm), when the backend named it. */
  readonly minWallMm: number | null;
  /** The backend's own sentence for why, shown verbatim when present. */
  readonly reason: string | null;
}

/**
 * This site's clamp, or null when nothing was clamped. Deliberately strict: a reading must SAY
 * `clamped` and carry a numeric applied value that is actually lower than the request. A backend
 * that reports `clamped` with no applied number has told us nothing we can print honestly, and a
 * fabricated "applied" would be exactly the silent substitution the brief forbids.
 */
export function siteReliefClamp(site: RunSiteResult): SiteReliefClamp | null {
  const reading: GingivalOffsetReading | null = site.gingivalOffset;
  if (reading === null || !reading.clamped) return null;
  const applied = reading.appliedMm;
  if (applied === null || !Number.isFinite(applied)) return null;
  if (applied >= reading.requestedMm) return null;
  return {
    tooth: site.tooth,
    requestedMm: reading.requestedMm,
    appliedMm: applied,
    limitMm: reading.limitMm,
    minWallMm: reading.minWallMm,
    reason: reading.clampReason,
  };
}

/** Every clamped site in the run, in the run's own site order. Empty = nothing was clamped. */
export function clampedSites(sites: readonly RunSiteResult[]): SiteReliefClamp[] {
  const out: SiteReliefClamp[] = [];
  for (const site of sites) {
    const clamp = siteReliefClamp(site);
    if (clamp !== null) out.push(clamp);
  }
  return out;
}

/** The wall clause, from the backend's number or the generic rule — never invented here. */
function wallClause(clamp: SiteReliefClamp): string {
  return clamp.minWallMm === null
    ? "below the design rule"
    : `below ${clamp.minWallMm.toFixed(2)} mm`;
}

/**
 * THE SENTENCE, verbatim from the brief:
 *
 *   "gingival relief 0.20 mm requested → 0.06 mm applied (the maximum this construction part can
 *    take without thinning the channel wall below 0.5 mm)"
 */
export function describeClamp(clamp: SiteReliefClamp): string {
  return (
    `gingival relief ${clamp.requestedMm.toFixed(2)} mm requested → ` +
    `${clamp.appliedMm.toFixed(2)} mm applied (the maximum this construction part can take ` +
    `without thinning the channel wall ${wallClause(clamp)})`
  );
}

/** The compact form for a table cell: "relief clamped 0.20 → 0.06 mm". */
export function clampChipText(clamp: SiteReliefClamp): string {
  return `relief clamped ${clamp.requestedMm.toFixed(2)} → ${clamp.appliedMm.toFixed(2)} mm`;
}

/**
 * The banner's heading: WHICH teeth were clamped, stated as a change to the lab's own instruction
 * rather than as a status. Plural-aware; the caller only renders it when the list is non-empty.
 */
export function clampHeadline(clamps: readonly SiteReliefClamp[]): string {
  const teeth = clamps.map((c) => c.tooth);
  const which =
    teeth.length === 1 ? `tooth ${teeth[0]}` : `teeth ${teeth.slice(0, -1).join(", ")} and ${teeth[teeth.length - 1]}`;
  return `The gingival relief you asked for was reduced on ${which}.`;
}

/** The one line that explains WHY the clamp is not a defect — the gate, stated positively. */
export const CLAMP_WHY_LINE =
  "The part was built at the reduced relief so its screw channel keeps a measurable wall. " +
  "Nothing was silently substituted: the request stands as you typed it, and this is what the " +
  "run applied instead. Lower the requested relief to the number above to process without a clamp.";

/** True when any site in a run was clamped — the cheap check components gate their notice on. */
export function hasClamp(sites: readonly RunSiteResult[]): boolean {
  return sites.some((site) => siteReliefClamp(site) !== null);
}
