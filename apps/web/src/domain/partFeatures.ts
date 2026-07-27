/**
 * The LIBRARY PART's marked features — the operator's half of a manual correspondence
 * (client ask 2026-07-24, with screenshots: "mark the holes/trenches in the LIBRARY part,
 * and also mark the corresponding holes/trenches in the SCAN"). Mirrors the worker's
 * domain/part_features.py: a feature is a landmark on the part in its CANONICAL frame,
 * named by its AZIMUTH about the part's own rim centre; `radiusMm` is the lever arm that
 * turns an angular disagreement into millimetres the operator can judge.
 *
 * A part is marked ONCE per catalog variant and every case that ships that part reuses the
 * annotation — the productization point (mark the catalog, not each scan). The annotation is
 * SEEDED from the machine's own reading, so the operator CONFIRMS or CORRECTS a reading
 * rather than starting from a blank part.
 *
 * Framework-free (no React, no fetch, no three.js) like the rest of domain/.
 */
import type { Vec3 } from "./types";

/** The ubiquitous language of a marked part (worker: FEATURE_KINDS). "trench" is the coded
 *  cutout a lab tech reads rotation from; "notch"/"flat" are the other vendor keying styles
 *  the same correspondence math serves; "channel" is the screw bore. */
export const PART_FEATURE_KINDS = ["trench", "notch", "flat", "channel"] as const;
export type PartFeatureKind = (typeof PART_FEATURE_KINDS)[number];

/** Who placed a mark: the machine's own reading, or a human click (possibly snapped onto
 *  the machine's feature — the id then says which feature the mark agrees with). */
export type PartFeatureSource = "auto" | "operator";

/** One landmark on the library part, canonical frame. `definesRotation` is the server's own
 *  lever-arm verdict (radiusMm >= 0.5): a concentric bore names the AXIS, not a clock angle,
 *  so it is listed and drawn but refused as a correspondence anchor. */
export interface PartFeature {
  readonly id: string;
  readonly kind: PartFeatureKind;
  readonly azimuthDeg: number;
  readonly radiusMm: number;
  readonly zMm: number;
  readonly source: PartFeatureSource;
  readonly definesRotation: boolean;
}

/** A catalog part's marked features as the server holds them. `autoSeeded` is true when the
 *  part has never been marked and these are the machine's reading (nothing is persisted yet);
 *  `revisedAt` is null for such a seed. */
export interface PartAnnotation {
  readonly model: string;
  readonly variant: string;
  readonly autoSeeded: boolean;
  readonly revisedAt: string | null;
  readonly features: readonly PartFeature[];
}

/** Server cap on features per annotation (worker: MAX_PART_FEATURES) — a catalog cap reads
 *  1-3 coded trenches plus the channel, so 12 is generous; the PUT 422s above it. */
export const MAX_PART_FEATURES = 12;

/** Server lever-arm bound (worker: MIN_LEVER_ARM_MM) — mirrored so the UI can explain WHY a
 *  feature cannot anchor a rotation before the operator round-trips a 422. */
export const MIN_LEVER_ARM_MM = 0.5;

/**
 * The operator's in-progress edit of one part's marks. A draft is EITHER a feature that came
 * back from the server (`id` set, `point` null — re-sent by azimuth on save) OR a fresh click
 * on the 3D part (`id` null, `point` = the canonical-frame click — re-sent as a point so the
 * SERVER does the authoritative snap onto its own reading, exactly as feature_from_point does;
 * the azimuth/radius carried here are the client's provisional read of the same click, shown
 * immediately so the list is not blank while a save round-trips).
 *
 * `key` is a local stable identity for React lists and select/remove — never sent anywhere:
 * server ids are derived (an operator id IS its rounded azimuth), so they change as a mark
 * moves and cannot key a list being edited.
 */
export interface DraftFeature {
  readonly key: string;
  readonly kind: PartFeatureKind;
  readonly azimuthDeg: number;
  readonly radiusMm: number;
  readonly zMm: number;
  readonly source: PartFeatureSource;
  readonly id: string | null;
  readonly point: Vec3 | null;
}

/** Monotonic local keys ("draft-1", "draft-2", …) — pure, so the caller owns the counter and
 *  the same input always produces the same output (no ambient state, no RNG). */
export function draftKey(seq: number): string {
  return `draft-${seq}`;
}

/** Turn a server annotation into an editable draft list (identity edit: nothing moves). */
export function draftsFrom(features: readonly PartFeature[]): DraftFeature[] {
  return features.map((f, i) => ({
    key: draftKey(i + 1),
    kind: f.kind,
    azimuthDeg: f.azimuthDeg,
    radiusMm: f.radiusMm,
    zMm: f.zMm,
    source: f.source,
    id: f.id,
    point: null,
  }));
}

/** The provisional azimuth/radius of a canonical-frame click about the part's rim centre —
 *  the client's own read of the click it is about to send, so a fresh mark shows a number
 *  instead of a blank row. The SERVER's value (snapped to its own reading when the click
 *  lands close enough) replaces this on save; the two agree to the snap window by
 *  construction. `rimCentre` is the part frame's fitted rim centre in canonical xy. */
export function readClick(
  point: Vec3,
  rimCentre: readonly [number, number],
): { azimuthDeg: number; radiusMm: number; zMm: number } {
  const dx = point[0] - rimCentre[0];
  const dy = point[1] - rimCentre[1];
  return {
    azimuthDeg: (Math.atan2(dy, dx) * 180) / Math.PI,
    radiusMm: Math.hypot(dx, dy),
    zMm: point[2],
  };
}

/**
 * ADD or MOVE, the single click-placement rule of the annotation mode: with a draft selected
 * the click MOVES that mark (its slot in the list, its kind, and its local key survive — the
 * operator is correcting one landmark, not adding a second one next to it); with nothing
 * selected the click APPENDS a new mark of `kind`. Refuses to grow past MAX_PART_FEATURES
 * (the server's own cap) rather than round-tripping a 422 the operator cannot act on.
 *
 * Pure: returns the next draft list, or the input unchanged when the cap blocks an append.
 */
export function placeDraft(
  drafts: readonly DraftFeature[],
  placement: { readonly point: Vec3; readonly kind: PartFeatureKind; readonly key: string },
  read: { readonly azimuthDeg: number; readonly radiusMm: number; readonly zMm: number },
  selectedKey: string | null,
): DraftFeature[] {
  const moved: DraftFeature = {
    key: placement.key,
    kind: placement.kind,
    azimuthDeg: read.azimuthDeg,
    radiusMm: read.radiusMm,
    zMm: read.zMm,
    // A click is always the operator's mark, whatever the mark it replaces was — the same
    // rule the server applies (feature_from_point always returns source="operator").
    source: "operator",
    // The id is the SERVER's to derive from this point (snap or free-hand) — carrying the
    // replaced feature's id forward would claim an agreement that has not been measured.
    id: null,
    point: placement.point,
  };
  if (selectedKey !== null && drafts.some((d) => d.key === selectedKey)) {
    return drafts.map((d) => (d.key === selectedKey ? { ...moved, key: d.key, kind: d.kind } : d));
  }
  if (drafts.length >= MAX_PART_FEATURES) return [...drafts];
  return [...drafts, moved];
}

/** Drop one mark by local key. */
export function removeDraft(drafts: readonly DraftFeature[], key: string): DraftFeature[] {
  return drafts.filter((d) => d.key !== key);
}

/** How many marks came from the machine vs a human — the state line's numbers. */
export function draftCounts(drafts: readonly DraftFeature[]): { auto: number; operator: number } {
  let auto = 0;
  let operator = 0;
  for (const d of drafts) {
    if (d.source === "auto") auto += 1;
    else operator += 1;
  }
  return { auto, operator };
}

/**
 * The annotation mode's state line: "6020 · 3 features (2 auto, 1 operator)". The variant is
 * named because one browser panel edits whichever card is previewed, and a mark saved against
 * the wrong variant is a silently mis-clocked part on every future case that ships it.
 */
export function annotationStateLine(variant: string, drafts: readonly DraftFeature[]): string {
  const { auto, operator } = draftCounts(drafts);
  const noun = drafts.length === 1 ? "feature" : "features";
  return `${variant} · ${drafts.length} ${noun} (${auto} auto, ${operator} operator)`;
}

/** One feature's compact identity line: "trench-02 · +72.2° · r 1.43mm". */
export function featureLabel(feature: {
  readonly id: string | null;
  readonly kind: PartFeatureKind;
  readonly azimuthDeg: number;
  readonly radiusMm: number;
}): string {
  const az = `${feature.azimuthDeg > 0 ? "+" : ""}${feature.azimuthDeg.toFixed(1)}°`;
  return `${feature.id ?? feature.kind} · ${az} · r ${feature.radiusMm.toFixed(2)}mm`;
}

/**
 * Whether the draft list differs from what the server last handed back — drives the Save
 * button's enabled state and the "unsaved marks" cue. Compares the geometry the operator can
 * see (kind + azimuth + radius, to the tenth of a degree / hundredth of a mm the UI prints),
 * not object identity: reloading the same annotation must never read as an edit. Any draft
 * carrying a fresh click (`point`) is by definition an edit, even if it landed on the same
 * azimuth — the server may snap it and change its source/id.
 */
export function draftsAreDirty(
  drafts: readonly DraftFeature[],
  saved: readonly PartFeature[],
): boolean {
  if (drafts.some((d) => d.point !== null)) return true;
  if (drafts.length !== saved.length) return true;
  return drafts.some((d, i) => {
    const s = saved[i];
    if (s === undefined) return true;
    return (
      d.kind !== s.kind ||
      d.azimuthDeg.toFixed(1) !== s.azimuthDeg.toFixed(1) ||
      d.radiusMm.toFixed(2) !== s.radiusMm.toFixed(2)
    );
  });
}

/** One feature as the PUT wants it: a fresh click travels as a `point` (the server snaps it
 *  onto its own reading); an untouched mark travels as its azimuth. */
export interface PartFeatureInput {
  readonly kind: PartFeatureKind;
  readonly azimuthDeg: number | null;
  readonly point: Vec3 | null;
}

/** The PUT body's feature list — exactly one placement per feature (the server 422s on both
 *  or neither), preserving list order so the operator's reading order is what gets stored. */
export function toFeatureInputs(drafts: readonly DraftFeature[]): PartFeatureInput[] {
  return drafts.map((d) =>
    d.point !== null
      ? { kind: d.kind, azimuthDeg: null, point: d.point }
      : { kind: d.kind, azimuthDeg: d.azimuthDeg, point: null },
  );
}

/**
 * Marks that cannot anchor a rotation, by local key — the concentric ones (inside the
 * server's lever arm). Surfaced as a per-row caption rather than as a block: the channel is
 * seeded and drawn on purpose (the operator sees the bore and expects it in the list), it
 * simply cannot be one half of a correspondence.
 */
export function draftDefinesRotation(draft: DraftFeature): boolean {
  return draft.radiusMm >= MIN_LEVER_ARM_MM;
}
