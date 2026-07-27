/**
 * THE DEVIATION COLOURING — the union panel's third pane and its colorbar, from ONE ramp.
 *
 * The backend serves the union overlay as per-vertex signed millimetres plus a `scale` block
 * naming its own colormap ("RdBu_r") and clamp (±0.5mm) — the SAME convention the acceptance
 * difference-map PNG prints, so a doctor comparing the two sees one colour language. This module
 * is that ramp, in one place: the 3D mesh's vertex colours and the DOM colorbar's gradient both
 * come out of `deviationColorSrgb`, so the bar cannot drift from the surface it explains.
 *
 * RdBu_r (matplotlib's diverging red-blue, reversed) reads: BLUE = negative = the scan sits
 * INSIDE the cap surface; WHITE = agreement; RED = positive = the scan sits OUTSIDE it (the
 * server states this sign convention on every payload, and the panel prints it verbatim).
 *
 * Pure and three-free — no scene, no DOM — so the ramp is unit-testable in the node environment
 * like every other geometry/colour rule in this app.
 */

/** The 11-class RdBu stops (matplotlib), stated blue-first — i.e. already REVERSED into RdBu_r.
 *  Values are sRGB 0-255, exactly as the PNG's colormap emits them. */
const RD_BU_R_STOPS: readonly (readonly [number, number, number])[] = [
  [5, 48, 97], // -clamp: deep blue — scan well inside the cap
  [33, 102, 172],
  [67, 147, 195],
  [146, 197, 222],
  [209, 229, 240],
  [247, 247, 247], // 0: near-white — agreement
  [253, 219, 199],
  [244, 165, 130],
  [214, 96, 77],
  [178, 24, 43],
  [103, 0, 31], // +clamp: deep red — scan well outside the cap
];

/** Vertices the instrument could not read (no scan surface under them) are GREY, never a colour
 *  from the ramp: painting an unmeasured hole as "0.0mm, perfect" is the one lie this panel must
 *  not tell. Matches the `deviation_mm: null` entries the server sends. */
export const UNMEASURED_COLOR_HEX = "#9aa4b0";

/** Clamp a signed millimetre reading into the scale's ±clamp window, then map to 0..1. */
export function deviationFraction(mm: number, clampMm: number): number {
  if (clampMm <= 0) return 0.5;
  const clamped = Math.min(Math.max(mm, -clampMm), clampMm);
  return (clamped + clampMm) / (2 * clampMm);
}

/** The ramp sampled at 0..1, as sRGB components in 0-255 (linear interpolation between stops —
 *  the same piecewise-linear read matplotlib does for a listed colormap). */
export function rampSrgb255(fraction: number): [number, number, number] {
  const f = Math.min(Math.max(fraction, 0), 1);
  const scaled = f * (RD_BU_R_STOPS.length - 1);
  const lower = Math.floor(scaled);
  const upper = Math.min(lower + 1, RD_BU_R_STOPS.length - 1);
  const t = scaled - lower;
  const a = RD_BU_R_STOPS[lower] as readonly [number, number, number];
  const b = RD_BU_R_STOPS[upper] as readonly [number, number, number];
  return [
    a[0] + (b[0] - a[0]) * t,
    a[1] + (b[1] - a[1]) * t,
    a[2] + (b[2] - a[2]) * t,
  ];
}

/** "#rrggbb" for a signed deviation, or the unmeasured grey for null. */
export function deviationColorSrgb(mm: number | null, clampMm: number): string {
  if (mm === null || !Number.isFinite(mm)) return UNMEASURED_COLOR_HEX;
  const [r, g, b] = rampSrgb255(deviationFraction(mm, clampMm));
  const hex = (v: number) => Math.round(Math.min(Math.max(v, 0), 255)).toString(16).padStart(2, "0");
  return `#${hex(r)}${hex(g)}${hex(b)}`;
}

/**
 * sRGB -> linear-light, the transfer function three.js applies when it reads a hex colour under
 * its default colour management. Vertex colours bypass that conversion (they are handed to the
 * shader as-is, in the LINEAR working space), so the ramp has to be converted here or the mesh
 * renders visibly washed-out against a colorbar built from the same numbers.
 */
export function srgbToLinear(channel255: number): number {
  const c = Math.min(Math.max(channel255, 0), 255) / 255;
  return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}

/**
 * The per-vertex colour attribute for the union mesh: three LINEAR floats per point, ramped from
 * the signed reading (grey where the read is null). Built here rather than in the scene so the
 * mapping is testable without a WebGL context.
 */
export function buildDeviationColors(
  deviationMm: readonly (number | null)[],
  clampMm: number,
): Float32Array {
  const colors = new Float32Array(deviationMm.length * 3);
  const greyLinear = [
    srgbToLinear(parseInt(UNMEASURED_COLOR_HEX.slice(1, 3), 16)),
    srgbToLinear(parseInt(UNMEASURED_COLOR_HEX.slice(3, 5), 16)),
    srgbToLinear(parseInt(UNMEASURED_COLOR_HEX.slice(5, 7), 16)),
  ] as const;
  deviationMm.forEach((mm, i) => {
    if (mm === null || !Number.isFinite(mm)) {
      colors[i * 3] = greyLinear[0];
      colors[i * 3 + 1] = greyLinear[1];
      colors[i * 3 + 2] = greyLinear[2];
      return;
    }
    const [r, g, b] = rampSrgb255(deviationFraction(mm, clampMm));
    colors[i * 3] = srgbToLinear(r);
    colors[i * 3 + 1] = srgbToLinear(g);
    colors[i * 3 + 2] = srgbToLinear(b);
  });
  return colors;
}

/** The colorbar's CSS gradient, sampled from the SAME ramp the mesh uses (11 stops, left =
 *  -clamp). `linear-gradient(to right, …)` — the bar is drawn horizontally under the panel. */
export function deviationGradientCss(): string {
  const stops = RD_BU_R_STOPS.map((_, i) => {
    const fraction = i / (RD_BU_R_STOPS.length - 1);
    return `${deviationColorSrgb(fraction * 2 - 1, 1)} ${(fraction * 100).toFixed(0)}%`;
  });
  return `linear-gradient(to right, ${stops.join(", ")})`;
}

/** The five tick labels under the bar: -clamp, -clamp/2, 0, +clamp/2, +clamp, signed and in mm
 *  ("−0.50", "0", "+0.50"). Signs are explicit because the sign IS the clinical meaning here. */
export function deviationTickLabels(clampMm: number): string[] {
  const decimals = clampMm < 1 ? 2 : 1;
  const at = (v: number) => {
    if (v === 0) return "0";
    return `${v > 0 ? "+" : "−"}${Math.abs(v).toFixed(decimals)}`;
  };
  return [at(-clampMm), at(-clampMm / 2), at(0), at(clampMm / 2), at(clampMm)];
}

// ---- THE "CONTACTS" SCALE (RealGUIDE's, offered alongside ours) ----------------------------
//
// The client's viewer colours the same overlay on an ABSOLUTE 0.00-0.60 mm rainbow labelled
// "Contacts": magnitude only, no sign. It is offered here as a SELECTABLE scale rather than a
// replacement, because the two answer different questions and a lab reads both:
//
//   signed ±0.5 RdBu  — WHICH WAY the scan misses the part (red = scan proud of the cap, blue =
//                       scan sunk into it). Direction is what tells a tech whether the cap is
//                       riding high or biting in; it is also the convention our own deviation
//                       PNG prints, so the two artifacts stay one colour language.
//   contacts 0-0.6    — HOW FAR, on the scale the client's own software uses, so a number they
//                       have been reading for years still reads the same here.
//
// Blue at 0.00 (agreement) through green/yellow to red at 0.60+ (the largest distance shown) —
// the mapping is stated verbatim under the bar, so no vendor convention is assumed by the reader.

/** The client's own upper bound for the Contacts bar. */
export const CONTACTS_MAX_MM = 0.6;

/** Which colouring the union pane is currently using. */
export type DeviationScaleId = "signed" | "contacts";

/** The rainbow stops, 0.00-first (sRGB 0-255): deep blue → cyan → green → yellow → orange → red. */
const CONTACTS_STOPS: readonly (readonly [number, number, number])[] = [
  [13, 71, 161], // 0.00 — agreement
  [25, 118, 210],
  [0, 172, 193],
  [67, 160, 71],
  [205, 220, 57],
  [251, 140, 0],
  [211, 47, 47], // >= max — the largest distance the bar shows
];

/** |mm| mapped into 0..1 across the 0..maxMm window (anything beyond saturates at the top). */
export function contactsFraction(mm: number, maxMm: number): number {
  if (maxMm <= 0) return 0;
  return Math.min(Math.abs(mm) / maxMm, 1);
}

export function contactsRampSrgb255(fraction: number): [number, number, number] {
  const f = Math.min(Math.max(fraction, 0), 1);
  const scaled = f * (CONTACTS_STOPS.length - 1);
  const lower = Math.floor(scaled);
  const upper = Math.min(lower + 1, CONTACTS_STOPS.length - 1);
  const t = scaled - lower;
  const a = CONTACTS_STOPS[lower] as readonly [number, number, number];
  const b = CONTACTS_STOPS[upper] as readonly [number, number, number];
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
}

/** "#rrggbb" for an absolute deviation on the Contacts scale, or the unmeasured grey for null —
 *  the same "never paint an unread vertex as agreement" rule the signed scale follows. */
export function contactsColorSrgb(mm: number | null, maxMm: number): string {
  if (mm === null || !Number.isFinite(mm)) return UNMEASURED_COLOR_HEX;
  const [r, g, b] = contactsRampSrgb255(contactsFraction(mm, maxMm));
  const hex = (v: number) => Math.round(Math.min(Math.max(v, 0), 255)).toString(16).padStart(2, "0");
  return `#${hex(r)}${hex(g)}${hex(b)}`;
}

export function contactsGradientCss(): string {
  const stops = CONTACTS_STOPS.map((_, i) => {
    const fraction = i / (CONTACTS_STOPS.length - 1);
    return `${contactsColorSrgb(fraction, 1)} ${(fraction * 100).toFixed(0)}%`;
  });
  return `linear-gradient(to right, ${stops.join(", ")})`;
}

/** Five unsigned ticks — "0.00", "0.15", "0.30", "0.45", "0.60". No signs: this scale has none,
 *  which is exactly the difference the selector's label states. */
export function contactsTickLabels(maxMm: number): string[] {
  return [0, 0.25, 0.5, 0.75, 1].map((f) => (f * maxMm).toFixed(2));
}

/**
 * The per-vertex colour attribute for whichever scale the pane is showing — ONE entry point, so
 * the mesh and its colorbar can never end up on different ramps. `clampMm` is the signed scale's
 * ±window; the Contacts scale uses its own CONTACTS_MAX_MM.
 */
export function buildScaleColors(
  scaleId: DeviationScaleId,
  deviationMm: readonly (number | null)[],
  clampMm: number,
): Float32Array {
  if (scaleId === "signed") return buildDeviationColors(deviationMm, clampMm);
  const colors = new Float32Array(deviationMm.length * 3);
  const greyLinear = [
    srgbToLinear(parseInt(UNMEASURED_COLOR_HEX.slice(1, 3), 16)),
    srgbToLinear(parseInt(UNMEASURED_COLOR_HEX.slice(3, 5), 16)),
    srgbToLinear(parseInt(UNMEASURED_COLOR_HEX.slice(5, 7), 16)),
  ] as const;
  deviationMm.forEach((mm, i) => {
    if (mm === null || !Number.isFinite(mm)) {
      colors[i * 3] = greyLinear[0];
      colors[i * 3 + 1] = greyLinear[1];
      colors[i * 3 + 2] = greyLinear[2];
      return;
    }
    const [r, g, b] = contactsRampSrgb255(contactsFraction(mm, CONTACTS_MAX_MM));
    colors[i * 3] = srgbToLinear(r);
    colors[i * 3 + 1] = srgbToLinear(g);
    colors[i * 3 + 2] = srgbToLinear(b);
  });
  return colors;
}

/** "clamped: this site spans −4.61 to +4.25 mm" — the honest note next to the bar when the data
 *  runs past the ±clamp window (it usually does: the cap's walls have no scan surface behind
 *  them). null when the data fits inside the window, or when the server sent no data bounds. */
export function clampNoteFor(
  dataMinMm: number | null,
  dataMaxMm: number | null,
  clampMm: number,
): string | null {
  if (dataMinMm === null || dataMaxMm === null) return null;
  if (dataMinMm >= -clampMm && dataMaxMm <= clampMm) return null;
  return `clamped — this site spans ${dataMinMm.toFixed(2)} to ${dataMaxMm > 0 ? "+" : ""}${dataMaxMm.toFixed(2)} mm`;
}
