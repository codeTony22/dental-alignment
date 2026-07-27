/**
 * Composite-view color code — copied from apps/web/src/viewer/palette.ts on purpose.
 * The standalone bundle must be fully self-contained (it ships inside an offline view.html
 * with no network access and no dependency on the app's build), so this is a deliberate,
 * small duplication rather than a cross-target import. Keep these two files in sync by hand
 * if the app's palette ever changes.
 */

/** The three part roles a composite view can be built from. */
export type PartRole = "arch" | "cap" | "construction";

export const PALETTE: Readonly<Record<PartRole, number>> = {
  arch: 0xf2e3a6, // warm cream — same as the app's single-mesh scan color (RealGUIDE's tone)
  cap: 0x2fa75f, // green; distinct from brush-paint #2fd070 but same family —
  // intentional: "human marks green, machine's cap is green"
  construction: 0x7d93b8, // steel blue
};

export const ROLE_LABEL: Readonly<Record<PartRole, string>> = {
  arch: "Doctor's scan",
  cap: "Healing cap (aligned)",
  construction: "Construction",
};

const BACKGROUND_COLOR = 0x141a17;

export const STANDALONE_COLORS = {
  background: BACKGROUND_COLOR,
} as const;

/** CSS hex string ("#rrggbb") for a role's PALETTE color, for DOM/CSS consumers (e.g. the legend swatch). */
export function paletteHex(role: PartRole): string {
  return `#${PALETTE[role].toString(16).padStart(6, "0")}`;
}
