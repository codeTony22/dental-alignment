/**
 * THE WORKSPACE'S PROVENANCE POPOVER — pure display rules only (gap
 * `deviation-budget-in-workspace`, 2026-08-02).
 *
 * `SiteAcceptanceView` (GET .../sites/{tooth}/acceptance) and `CaseActivityView`
 * (GET .../activity) already carry every number, band word and threshold the
 * catalog computed — this module renders NONE of its own arithmetic over them. That
 * is not a style preference: the design prototype's popover (flow.dc.html 1363-1372)
 * computed `deviation()` / `verdict()` against a client-held `tolerance`, and porting
 * any of that here would put a browser-side pass/fail beside the server's own —
 * exactly the disagreement this app's whole "optimism OFF" posture exists to prevent.
 * Every function below reads a word or a number the server already published and
 * decides nothing about whether a site is fit to ship.
 */
import { staleMetricsPhrase } from "./adjust";
import type { SiteAcceptanceMetric } from "../api/client";

/** The chip class for the catalog's OWN band word — never a number. A band this app
 *  has not met (including the rollup's own "missing") gets the neutral chip that
 *  already exists for exactly that word; nothing here compares a value to a
 *  threshold to decide a colour. */
export function bandChipClass(band: string): string {
  if (band === "pass") return "chip chip--band-pass";
  if (band === "review") return "chip chip--band-review";
  if (band === "fail") return "chip chip--band-fail";
  return "chip chip--band-missing";
}

/**
 * The catalog's own thresholds, verbatim, beside the metric's own unit — "pass ≤ 0.2
 * mm · review ≤ 0.5 mm" rather than a room-left percentage. Null when the metric's
 * band is not a scalar comparison at all (`bands` absent/null on the wire): a metric
 * with nothing to print a range for must render NOTHING, not a fabricated one.
 */
export function thresholdWords(metric: SiteAcceptanceMetric): string | null {
  if (metric.bands == null) return null;
  const unit = metric.unit.length > 0 ? ` ${metric.unit}` : "";
  return `pass ≤ ${metric.bands.pass}${unit} · review ≤ ${metric.bands.review}${unit}`;
}

/**
 * "Showing the last 40 of 137 recorded" — ONLY when the window actually cut
 * something, so a case with fewer acts than the window holds gets no sentence
 * implying a truncation that did not happen. `recorded`/`window` are the server's own
 * counts (session.py's ACTIVITY_WINDOW); this performs no windowing of its own.
 */
export function logWindowWords(recorded: number, shown: number): string | null {
  if (recorded <= shown) return null;
  return `Showing the last ${shown} of ${recorded} acts recorded on this case.`;
}

/** Membership only — `stale_metrics`/`missing` are the server's own key lists, and a
 *  metric's presence in either is a fact this reads, never one it derives. */
export function isStaleMetric(staleMetrics: readonly string[], key: string): boolean {
  return staleMetrics.includes(key);
}

export function isMissingMetric(missing: readonly string[], key: string): boolean {
  return missing.includes(key);
}

/**
 * The row-level staleness sentence, in THIS surface's own voice. `staleMetricsPhrase`
 * is Adjust's vocabulary for which keys predate a rework (shared here so the same
 * key reads the same words everywhere) — but Deliver's own sentence
 * (`staleMetricsWords`) ends "Confirming seals …", which is not true of a popover
 * that confirms nothing, so that half is NOT reused: only the named-list vocabulary
 * is shared, the sentence around it is this surface's own.
 */
export function staleSummaryWords(staleMetrics: readonly string[]): string | null {
  const named = staleMetricsPhrase(staleMetrics);
  if (named === null) return null;
  const one = staleMetrics.length === 1;
  return (
    `${named} below still ${one ? "describes" : "describe"} a read from before the ` +
    `most recent rework — nothing has re-measured it since.`
  );
}

/** The two tones an acceptance fetch can come back in. */
export interface AbsenceWords {
  readonly tone: "hint" | "error";
  readonly words: string;
}

/**
 * `/acceptance` 404s for two genuinely healthy reasons — no completed current run,
 * or a tooth the run never verdicted — and the BFF's own detail sentence already
 * says which (deliver.py:701-704). Routing either through the standing error tone
 * would print alarm over a healthy service, the same distinction CaseShell.tsx's
 * CaseLoadError draws for its own 404s. Anything else (a transport failure, a 500)
 * keeps the ordinary failure tone.
 */
export function acceptanceAbsenceWords(error: {
  readonly detail: string;
  readonly status?: number;
}): AbsenceWords {
  if (error.status === 404) {
    return { tone: "hint", words: error.detail };
  }
  return { tone: "error", words: error.detail };
}
