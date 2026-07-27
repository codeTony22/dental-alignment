/**
 * MANUAL CORRESPONDENCE, the SCAN half (client ask 2026-07-24): the operator names WHICH
 * library feature they are about to mark, then clicks where they see it on the scan. Several
 * such pairs give a best-fit rotation plus a QC number the operator can read ("your marks
 * agree to 0.34mm") — the industry's manual-correspondence fallback (the industry 3-dot click
 * on the codes; Medit's 3 corresponding points).
 *
 * This is the EXPLICIT path. The one-shot "⌖ mark trench" stays the fast path: it binds the
 * click to the NEAREST code feature, which is exactly what becomes ambiguous on the 2-3
 * feature caps (zimmer-4.5-7030 reads trenches at -177.0 / -136.0 / -0.1°) and is blind where
 * the automatic reader has no evidence at all. Naming the feature removes both problems.
 *
 * Framework-free, like the rest of domain/.
 */
import type { PartFeature } from "./partFeatures";
import type { NudgeResult, Vec3 } from "./types";

/** Server cap on pairs per request (worker: _CORRESPONDENCE_MAX_PAIRS). */
export const MAX_CORRESPONDENCE_PAIRS = 8;

/**
 * One operator correspondence as the UI holds it: the PART half — EITHER a named library
 * feature OR a FREE POINT, an arbitrary canonical-frame click on the part itself (client ask
 * 2026-07-26: RealGUIDE's numbered clicks; on catalogs whose detector reads a single
 * rotation-defining feature the feature-only shape stranded the operator at one pair) — and
 * the point on the SCAN (world coords on the loaded scan mesh) where the operator sees it.
 * Exactly one of `featureId`/`partPoint` is set; build pairs through `featurePair`/`freePair`
 * so the invariant holds by construction.
 */
export interface CorrespondencePair {
  /** The named library feature, or null for a free point. */
  readonly featureId: string | null;
  /** The feature's kind (drives the marker/swatch color); null for a free point, which
   *  wears the dedicated free-point color instead. */
  readonly kind: PartFeature["kind"] | null;
  /** Free points only: the click on the LIBRARY PART, canonical frame. */
  readonly partPoint: Vec3 | null;
  readonly scanPoint: Vec3;
}

/** A pair anchored to a named library feature. */
export function featurePair(
  featureId: string,
  kind: PartFeature["kind"],
  scanPoint: Vec3,
): CorrespondencePair {
  return { featureId, kind, partPoint: null, scanPoint };
}

/** A free-point pair: an arbitrary spot on the part matched to a spot on the scan. */
export function freePair(partPoint: Vec3, scanPoint: Vec3): CorrespondencePair {
  return { featureId: null, kind: null, partPoint, scanPoint };
}

/**
 * A free pair's 1-based ordinal among the free pairs, in click order — the SAME positional
 * numbering the server stamps on the audit trail ("point-1", "point-2"), so the list row,
 * the markers on both panes, and the provenance stream all name one click the same way.
 * Null for feature pairs (their identity is the feature id).
 */
export function freePointNumber(
  pairs: readonly CorrespondencePair[],
  index: number,
): number | null {
  const pair = pairs[index];
  if (pair === undefined || pair.featureId !== null) return null;
  let ordinal = 0;
  for (let i = 0; i <= index; i += 1) {
    if (pairs[i]?.featureId === null) ordinal += 1;
  }
  return ordinal;
}

/** One pair's stable identity within the CURRENT list: the feature id, or the positional
 *  free-point key ("point-2"). Used for React keys and the remove control; free keys shift
 *  on removal exactly as the server's positional labels would, so the two never disagree. */
export function pairKey(pairs: readonly CorrespondencePair[], index: number): string {
  const pair = pairs[index];
  if (pair === undefined) return `pair-${index}`;
  return pair.featureId ?? `point-${freePointNumber(pairs, index) ?? index + 1}`;
}

/** The server's per-pair report after a best fit: what the mark asked for, what it got, and
 *  how far off it landed AT THAT FEATURE'S OWN RADIUS (the millimetres an operator can judge,
 *  not an abstract angle). */
export interface CorrespondenceResidual {
  readonly featureId: string;
  readonly featureAzimuthDeg: number;
  readonly clickAzimuthDeg: number;
  readonly deltaDeg: number;
  readonly residualDeg: number;
  readonly residualMm: number;
}

/** The align-to-correspondence response: the nudge response (the rotation was judged by the
 *  SAME ring-fixed stability bound and certification gates as every operator proposal) plus
 *  the per-pair residuals and their RMS. */
export interface AlignToCorrespondenceResult extends NudgeResult {
  readonly pairs: readonly CorrespondenceResidual[];
  readonly residualRmsMm: number;
}

/**
 * A run row names its part as "<model>-<variant>" (CapSpec.label, e.g. "zimmer-4.5-7030"),
 * and the annotation endpoints are keyed by model + variant separately. Split on the
 * IDENTIFIED variant rather than on the last hyphen: model names carry hyphens
 * ("neodent-gm", "zimmer-4.5") and so could a future variant code, whereas the row already
 * carries the exact variant the pipeline shipped. Falls back to the last-hyphen split when
 * the spec does not end with the identified variant (a legacy cached row), and returns null
 * when neither reading yields both halves — the picker then says it cannot name the part
 * instead of fetching a wrong one's marks.
 */
export function sitePartKey(
  spec: string,
  identifiedVariant: string,
): { readonly model: string; readonly variant: string } | null {
  const suffix = `-${identifiedVariant}`;
  if (identifiedVariant !== "" && spec.endsWith(suffix)) {
    const model = spec.slice(0, -suffix.length);
    if (model !== "") return { model, variant: identifiedVariant };
  }
  const cut = spec.lastIndexOf("-");
  if (cut <= 0 || cut === spec.length - 1) return null;
  return { model: spec.slice(0, cut), variant: spec.slice(cut + 1) };
}

/** Features that may anchor a correspondence — the concentric ones (the screw bore) name the
 *  axis, not a clock angle, and the server refuses them with that sentence. Filtered out of
 *  the picker up front so the operator is never offered a mark that cannot be used. */
export function anchorableFeatures(features: readonly PartFeature[]): PartFeature[] {
  return features.filter((f) => f.definesRotation);
}

/** Features still unpaired, in list order — one part feature cannot sit at two places on the
 *  scan (the server 422s on a repeated id), so the picker only offers what is left. Free
 *  points never take a feature off the board. */
export function unpairedFeatures(
  features: readonly PartFeature[],
  pairs: readonly CorrespondencePair[],
): PartFeature[] {
  const taken = new Set(pairs.map((p) => p.featureId).filter((id): id is string => id !== null));
  return anchorableFeatures(features).filter((f) => !taken.has(f.id));
}

/** Whether another FEATURE pair may be added: an anchorable feature is still free and the
 *  server's cap has room. */
export function canAddPair(
  features: readonly PartFeature[],
  pairs: readonly CorrespondencePair[],
): boolean {
  return pairs.length < MAX_CORRESPONDENCE_PAIRS && unpairedFeatures(features, pairs).length > 0;
}

/** Whether another FREE POINT may be placed — free points only need cap room (several are
 *  legal; each one IS its own spot on the part). */
export function canAddFreePoint(pairs: readonly CorrespondencePair[]): boolean {
  return pairs.length < MAX_CORRESPONDENCE_PAIRS;
}

/** Record (or re-record) one pair. Re-marking a FEATURE replaces its point rather than
 *  adding a second pair for the same id (which the server would refuse); a free point
 *  always appends — each click is a new numbered point. */
export function withPair(
  pairs: readonly CorrespondencePair[],
  pair: CorrespondencePair,
): CorrespondencePair[] {
  if (pair.featureId !== null) {
    const existing = pairs.findIndex((p) => p.featureId === pair.featureId);
    if (existing >= 0) return pairs.map((p, i) => (i === existing ? pair : p));
  }
  return [...pairs, pair];
}

/** Drop one pair by its key (feature id, or the positional "point-N" of a free pair). */
export function withoutPair(
  pairs: readonly CorrespondencePair[],
  key: string,
): CorrespondencePair[] {
  return pairs.filter((_p, i) => pairKey(pairs, i) !== key);
}

/** The pair list's line for one recorded correspondence: "trench-02 ↔ marked" for a
 *  feature, "point 1 ↔ marked" for a free point (its positional number — the same one the
 *  markers wear and the server audits). */
export function pairLabel(pairs: readonly CorrespondencePair[], index: number): string {
  const pair = pairs[index];
  if (pair === undefined) return "";
  if (pair.featureId !== null) return `${pair.featureId} ↔ marked`;
  return `point ${freePointNumber(pairs, index) ?? index + 1} ↔ marked`;
}

/**
 * The applied outcome line: what rotation the server derived from the operator's marks, how
 * well those marks agree with each other, and what the coded-cutout instrument reads at the
 * new pose (re-read server-side — an honest "no code signal" on the weak-evidence sites this
 * flow exists to backstop, where the automatic reader has nothing).
 *
 * With ONE pair there is nothing to disagree with (the rotation lands the named feature
 * exactly on the mark, residual 0 by construction) — saying "your marks agree to 0.00mm"
 * would dress a tautology up as a measurement, so the agreement clause is omitted.
 */
export function describeCorrespondence(result: AlignToCorrespondenceResult): string {
  const d = result.appliedDeltaDeg;
  const rotated = `rotated ${d > 0 ? "+" : ""}${d.toFixed(1)}° from ${result.pairs.length} mark${
    result.pairs.length === 1 ? "" : "s"
  }`;
  const agreement =
    result.pairs.length > 1 ? `; your marks agree to ${result.residualRmsMm.toFixed(2)}mm` : "";
  const shift = result.clocking.notchShiftDeg;
  const codes =
    shift === null
      ? "; no code signal at this pose"
      : `; codes now read ${shift > 0 ? "+" : ""}${shift.toFixed(1)}°`;
  return `${rotated}${agreement}${codes}`;
}

/** One residual row's read-out: "trench-02 · +1.9° · 0.05mm off". */
export function residualLabel(residual: CorrespondenceResidual): string {
  const deg = `${residual.residualDeg > 0 ? "+" : ""}${residual.residualDeg.toFixed(1)}°`;
  return `${residual.featureId} · ${deg} · ${residual.residualMm.toFixed(2)}mm off`;
}
