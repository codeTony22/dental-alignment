/**
 * THE RELIEF CEILING — the most gingival relief a chosen (construction part × cap variant) pair
 * can take before the screw channel's wall drops under the design rule.
 *
 * WHY THIS EXISTS (client, 2026-07-25, blocking their demo). The thin-wall export gate is
 * CORRECT — it refuses to ship a construction part whose channel wall has collapsed — but it
 * fires at the END of the pipeline, and at the lab's chosen 0.20 mm default it fires on about
 * half the fleet (measured: 4 of 9 warm cases, across BOTH vendors — the driver is cap size, not
 * vendor). The operator met it as an unexplained failure after a full run. The ceiling is that
 * same physics, measured by the worker BEFORE processing (GET /api/relief-limit) and put in front
 * of the operator at the moment they type the number.
 *
 * WHAT THIS MODULE WILL NOT DO. It does not re-derive the ceiling (the worker owns the
 * measurement and the MIN_WALL rule), it does not weaken the gate, and it does not clamp: a
 * number the operator did not choose is never substituted client-side. Its whole job is to STATE
 * the ceiling and to WARN — visibly, before Process — when the typed relief is over it. The run
 * clamps and reports; see domain/reliefClamp for the read-out of what actually happened.
 *
 * THE CEILING IS CASE-WIDE, THE CAPS ARE NOT. One relief is typed for the whole case, but every
 * site declares its own cap, and the ceiling belongs to a (construction × cap) PAIR. So the
 * number that governs is the TIGHTEST of the chosen caps' ceilings — `bindingCeiling` — and it
 * names the tooth that sets it. Showing only the active site's ceiling would let another site
 * clamp unseen, which is the exact surprise this feature was built to remove.
 */

/** The worker's measured ceiling for one (construction part × cap variant) pair. */
export interface ReliefLimit {
  readonly constructionPathId: string;
  readonly model: string;
  readonly variant: string;
  /** The ceiling in mm. null = the backend answered but could not determine it for this pair —
   *  reported as "not determined", never as "unlimited". */
  readonly maxSafeMm: number | null;
  /** What limits it, in the backend's own words (e.g. "channel wall"). */
  readonly limitedBy: string;
  /** The design rule the ceiling protects (mm), when the backend named it (0.5 today). */
  readonly minWallMm: number | null;
  /** True when the ceiling was measured on this pair; false when it is a conservative fallback. */
  readonly measured: boolean;
  /** Any extra sentence the backend attached, shown verbatim. */
  readonly note: string | null;
}

/** The fetch lifecycle for ONE pair's ceiling. "unavailable" is the specific 404: the RUNNING
 *  backend predates the endpoint (restart `make serve`) — stated as a hint, never as a failure,
 *  because the run still clamps and reports without it. */
export type ReliefLimitState =
  | { readonly kind: "loading" }
  | { readonly kind: "ready"; readonly limit: ReliefLimit }
  | { readonly kind: "unavailable" }
  | { readonly kind: "error"; readonly message: string };

/** One site's ceiling lookup: which tooth, which cap it declared, and what the fetch said. */
export interface SiteReliefLimit {
  readonly tooth: number;
  readonly variantId: string;
  readonly state: ReliefLimitState;
}

/** The ceiling that GOVERNS the case-wide relief: the tightest measured one, and its tooth. */
export interface BindingCeiling {
  readonly maxSafeMm: number;
  readonly tooth: number;
  readonly limit: ReliefLimit;
}

/**
 * What the selection column renders beside the offset input.
 *
 * `pending` on a ready readout is deliberate: another site's lookup is still in flight, so the
 * ceiling shown may still TIGHTEN. Saying so is cheaper than letting the number move silently.
 */
export type CeilingReadout =
  | { readonly kind: "idle" }
  | { readonly kind: "loading" }
  | { readonly kind: "unavailable" }
  | { readonly kind: "error"; readonly message: string }
  | { readonly kind: "undetermined" }
  | { readonly kind: "ready"; readonly binding: BindingCeiling; readonly pending: boolean };

/** Display/compare tolerance. The relief is chosen in 0.05 mm steps and shown to 2 dp, so a
 *  request that only differs from the ceiling in the 4th decimal is EQUAL for the operator —
 *  warning on it would be noise about a difference nobody can act on. */
export const CEILING_EPSILON_MM = 0.0005;

/** The cache key for one pair's ceiling — the three things the endpoint is asked about. */
export function reliefLimitKey(
  constructionPathId: string,
  model: string,
  variantId: string,
): string {
  return `${constructionPathId} ${model} ${variantId}`;
}

/**
 * The governing ceiling across the sites' chosen caps: the SMALLEST measured `maxSafeMm`. Ties go
 * to the first site in order, so the named tooth is stable across renders. null when no lookup
 * has produced a number yet (loading, 404, error, or every pair undetermined).
 */
export function bindingCeiling(sites: readonly SiteReliefLimit[]): BindingCeiling | null {
  let best: BindingCeiling | null = null;
  for (const site of sites) {
    if (site.state.kind !== "ready") continue;
    const { limit } = site.state;
    if (limit.maxSafeMm === null) continue;
    if (best === null || limit.maxSafeMm < best.maxSafeMm) {
      best = { maxSafeMm: limit.maxSafeMm, tooth: site.tooth, limit };
    }
  }
  return best;
}

/**
 * The column's read-out state, folded from the per-site lookups. Precedence is chosen so the
 * operator always sees the most ACTIONABLE truth: a real error first (something is wrong and a
 * retry may fix it), then the endpoint's absence (a restart hint), then any ceiling we do have
 * (flagged `pending` while siblings load), then loading, then the honest "not determined".
 */
export function ceilingReadout(sites: readonly SiteReliefLimit[]): CeilingReadout {
  if (sites.length === 0) return { kind: "idle" };
  const errored = sites.find((s) => s.state.kind === "error");
  if (errored && errored.state.kind === "error") {
    return { kind: "error", message: errored.state.message };
  }
  if (sites.some((s) => s.state.kind === "unavailable")) return { kind: "unavailable" };
  const binding = bindingCeiling(sites);
  const pending = sites.some((s) => s.state.kind === "loading");
  if (binding !== null) return { kind: "ready", binding, pending };
  if (pending) return { kind: "loading" };
  return { kind: "undetermined" };
}

/** "0.06" — the ceiling's display form. Same 2 dp as the offset input's own read-out. */
export function formatCeilingMm(valueMm: number): string {
  return valueMm.toFixed(2);
}

/** True when the typed relief is over the governing ceiling by more than display precision. */
export function exceedsCeiling(requestedMm: number, binding: BindingCeiling): boolean {
  return requestedMm > binding.maxSafeMm + CEILING_EPSILON_MM;
}

/**
 * The read-out beside the input — the brief's own sentence:
 *   "max safe for this part: 0.06 mm (limited by channel wall)"
 * plus the tooth that SETS it whenever the case has more than one site, because on a multi-site
 * case the number is one cap's ceiling governing every cap.
 */
export function describeCeiling(binding: BindingCeiling, siteCount: number): string {
  const base = `max safe for this part: ${formatCeilingMm(binding.maxSafeMm)} mm (limited by ${binding.limit.limitedBy})`;
  return siteCount > 1 ? `${base} — set by tooth ${binding.tooth} (${binding.limit.variant})` : base;
}

/** The wall rule the ceiling protects, as a clause: "below 0.50 mm" or the generic fallback when
 *  the backend did not name the number (never invented client-side). */
export function wallClause(limit: ReliefLimit): string {
  return limit.minWallMm === null
    ? "below the design rule"
    : `below ${limit.minWallMm.toFixed(2)} mm`;
}

/**
 * THE PRE-PROCESS WARNING — shown inline beside the field, not as a blocker. null when the typed
 * relief fits under the ceiling.
 *
 * It says three things and nothing else: that the number is over, what the ceiling is and why,
 * and exactly what the run will do about it. The operator is left with the choice — lower it here
 * and process at a number they chose, or process anyway and read the clamp in the results.
 */
export function ceilingWarning(requestedMm: number, binding: BindingCeiling): string | null {
  if (!exceedsCeiling(requestedMm, binding)) return null;
  const max = formatCeilingMm(binding.maxSafeMm);
  return (
    `${requestedMm.toFixed(2)} mm is more than this construction part can take: the maximum safe ` +
    `gingival relief is ${max} mm, which is what keeps the screw-channel wall from thinning ` +
    `${wallClause(binding.limit)}. The run will clamp to ${max} mm and report it — lower the ` +
    `number here to process at a relief you chose.`
  );
}

/** The read-out when a pair answered but the backend could not measure a ceiling for it. */
export const CEILING_UNDETERMINED_LINE =
  "max safe for this part: not determined — the backend could not measure this pair's channel " +
  "wall, so the relief is only checked at the end of the run.";

/** The 404 hint: the RUNNING backend predates the endpoint. The gate downstream is unaffected —
 *  say what is missing (the preview) and what still protects the part (the run's own clamp). */
export const CEILING_UNAVAILABLE_LINE =
  "The relief-limit endpoint is not available on the running API — restart `make serve` " +
  "(apps/worker) to see the ceiling here. The run still clamps to the safe maximum and reports it.";

/** While the lookup is in flight. */
export const CEILING_LOADING_LINE = "measuring the safe relief for this part…";

/** Shown on a ready ceiling whose siblings are still loading — the number may still tighten. */
export const CEILING_PENDING_LINE = "…still measuring the other sites' caps; this may tighten.";
