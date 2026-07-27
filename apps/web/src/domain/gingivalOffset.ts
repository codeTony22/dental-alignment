/**
 * OFFSET HONESTY — the requested relief vs the relief the emitted part actually carries.
 *
 * Measured 2026-07-25: requesting the lab default 0.20 mm of gingival relief achieves ~0.13-0.15
 * mm median on the delivered construction part, because the relief is applied through an SDF
 * round trip (voxelize → inward offset → re-mesh) and the re-mesh closes part of the requested
 * clearance. Two dishonest fixes were available and are NOT taken:
 *
 *   - silently rescaling the request (ask for 0.28 so 0.20 comes out) — the operator would then
 *     be reading a number nobody asked for, and the rescale factor is not constant across parts;
 *   - printing the request as if it were the result — which is what the UI did before this.
 *
 * Instead both numbers are shown side by side with their provenance: REQUESTED is an input the
 * operator typed, ACHIEVED is a measurement of the run's own output. This module is the pure
 * arithmetic behind that read-out (aggregating the per-site readings the run returns) and the
 * one sentence that explains the difference.
 */
import type { GingivalOffsetReading, RunSiteResult } from "./types";

/** The aggregate across a run's sites — what the selection column shows beside the input. */
export interface AchievedGingivalOffset {
  /** The relief the run was ASKED for, as the sites themselves recorded it. */
  readonly requestedMm: number;
  readonly medianMm: number;
  readonly minMm: number;
  readonly maxMm: number;
  /** How many sites actually carried a measurement (never the site count — an unmeasured site
   *  is excluded, not counted as agreeing). */
  readonly nSites: number;
  /** The backend's own words for how it measured, when it said. */
  readonly method: string | null;
}

/** Median of a non-empty sorted-able list — the middle value, or the mean of the middle two.
 *  Median (not mean) because one site whose relief could not be cut is an outlier, not a
 *  reason to move the number the operator reads for the other three. */
function median(values: readonly number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 1) return sorted[mid] as number;
  return (((sorted[mid - 1] as number) + (sorted[mid] as number)) / 2);
}

/**
 * The run's achieved relief, or null when NOTHING measured it (a backend predating the
 * measurement, or a run whose sites all failed to report). null is the honest state: the UI
 * says "not measured on this run" rather than echoing the request back as if confirmed.
 */
export function achievedGingivalOffset(
  sites: readonly RunSiteResult[],
): AchievedGingivalOffset | null {
  const readings: GingivalOffsetReading[] = [];
  for (const site of sites) {
    const reading = site.gingivalOffset;
    if (reading && reading.achievedMedianMm !== null && Number.isFinite(reading.achievedMedianMm)) {
      readings.push(reading);
    }
  }
  if (readings.length === 0) return null;
  const achieved = readings.map((r) => r.achievedMedianMm as number);
  // Per-site min/max when the backend reported the spread WITHIN a site; otherwise the spread
  // across the sites' own medians. Either way it is measured, never assumed symmetric.
  const mins = readings.map((r) => r.achievedMinMm ?? (r.achievedMedianMm as number));
  const maxes = readings.map((r) => r.achievedMaxMm ?? (r.achievedMedianMm as number));
  return {
    requestedMm: (readings[0] as GingivalOffsetReading).requestedMm,
    medianMm: median(achieved),
    minMm: Math.min(...mins),
    maxMm: Math.max(...maxes),
    nSites: readings.length,
    method: readings.find((r) => r.method !== null)?.method ?? null,
  };
}

/** "0.14 mm achieved (median of 3 sites, 0.13–0.15)" — the measured read-out beside the input.
 *  The range is dropped when it collapses (a single site, or every site identical): a range of
 *  one number reads as noise. */
export function describeAchievedOffset(achieved: AchievedGingivalOffset): string {
  const spread =
    achieved.maxMm - achieved.minMm > 0.005
      ? ` (median of ${achieved.nSites} site${achieved.nSites > 1 ? "s" : ""}, ${achieved.minMm.toFixed(
          2,
        )}–${achieved.maxMm.toFixed(2)})`
      : ` (${achieved.nSites} site${achieved.nSites > 1 ? "s" : ""})`;
  return `${achieved.medianMm.toFixed(2)} mm achieved${spread}`;
}

/** True when the run's own measurement disagrees with what was asked by more than a rounding
 *  hair — the case the explanation line exists for (and, measured, the normal case at 0.20). */
export function offsetShortfall(achieved: AchievedGingivalOffset): number {
  return achieved.requestedMm - achieved.medianMm;
}

/** The ONE-LINE explanation the brief asks for. Stated as measurement + mechanism, with the
 *  promise that the request itself is untouched. */
export const OFFSET_HONESTY_LINE =
  "Requested is what the run asks for; achieved is measured on the part it emitted — the SDF " +
  "round trip that cuts the relief closes some of it back, so the achieved clearance reads " +
  "under the request. The request is never silently rescaled to compensate.";

/** What the read-out says before any run has measured this case. */
export const OFFSET_NOT_MEASURED_LINE = "achieved clearance: not measured on this run yet";
