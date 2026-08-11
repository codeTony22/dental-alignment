/**
 * Composite-view color code. STL carries no color/material info, so the staged
 * deliverable views compose separate world-posed part files client-side, each
 * tinted by its role. Kept as one named constant per role so the viewer, the
 * legend, and any future export all agree on the same colors.
 *
 * The scene's OTHER colors (proposal markers, mark-mode/rim-point spheres, the brush stroke) are
 * click/state-driven, not composite-part roles, so their constants live in sceneController.ts
 * next to the code that places them — but the full palette, for reference, is:
 *   - proposal markers (orange, #ff9800): auto-detected candidate sites, off by default
 *   - centre mark (red, #e6362e): single click, the cap's top-centre indicator
 *   - LEGACY single rim mark (blue, #2f7fe6): one click on the widest rim edge; superseded for
 *     new doctor input by the multi-point border collection below, but still what curated
 *     prefills send
 *   - multi-point rim-BORDER dots (teal/cyan, #17b6a8): several clicks around the cap's visible
 *     border. Deliberately NOT the same blue as the legacy rim mark — a client screenshot showed
 *     the two were indistinguishable on screen, which was actively misleading once a row had
 *     both a stale legacy sphere and new border dots. Teal was picked because every other hue in
 *     the scene is already spoken for (orange/red/green/steel-blue/legacy-blue above) and it
 *     reads cleanly against both the cream scan (#f0e4cb) and the light-blue viewer background
 *     (#141a17) without competing with the red centre marker the way magenta would.
 *   - brush stroke (green, #2fd070): operator-painted healing-cap patch
 *   - construction part (steel blue, #7d93b8): composite role, listed above too
 *   - POST-RUN seated-pose axis triad (RealGUIDE-style, standard RGB axis convention): red
 *     #e6362e = x, green #2fd070 = y, blue #2f7fe6 = z — three short line segments per seated
 *     site, drawn from the "<case>-<tooth>-implant.json" package file's pose matrix. Reuses the
 *     centre-mark red / brush-stroke green / legacy-rim blue values rather than inventing new
 *     ones: no visual clash, since marks are pre-run INPUTS and the triad is a post-run OUTPUT —
 *     they are never the doctor-facing concept at the same point in the workflow.
 *
 * ALL scene markers (proposals, centre, legacy rim, rim-border dots, pose triads) render THROUGH
 * the scan/composite geometry (depthTest/depthWrite off, high renderOrder) — RealGUIDE's own
 * convention for registration-point indicators, and required for tall caps whose curated marks
 * can sit below the crown dome and would otherwise be invisibly occluded. See sceneController.ts's
 * MARKER_RENDER_ORDER/makeIndicatorVisible.
 */

/** The three part roles a composite view can be built from. */
export type PartRole = "arch" | "cap" | "construction" | "socket";

/** A single STL to load and tint as part of a composite view, all in one shared world frame. */
export interface CompositePartSpec {
  readonly url: string;
  readonly role: PartRole;
}

export const PALETTE: Readonly<Record<PartRole, number>> = {
  arch: 0xf2e3a6, // LIGHT YELLOW — the scan material, matched to RealGUIDE's own tone (client ask
  // 2026-07-25). Was 0xe8e2d4, a desaturated near-grey ivory that read cold beside their
  // screenshots; this is the same lightness family with the warmth their scan material has
  // (hue ~41°, sat ~15% vs ~9%). Both other roles stay legible against it — the cap green
  // 0x2fa75f and the construction steel-blue 0x7d93b8 are far darker and far more saturated,
  // and every scene marker below was already chosen to read against a cream arch.
  cap: 0x2fa75f, // green; distinct from brush-paint #2fd070 but same family —
  // intentional: "human marks green, machine's cap is green"
  construction: 0x7d93b8, // steel blue
  socket: 0xb9ab84, // the CUT surface (client 2026-08-09: "can't see depth at
  // all") — the socket liner emitted as its own preview layer so the recess
  // reads against the arch. Same warm family as the scan, one step darker and
  // greyer: contrast enough to see the dish, never a colour that shouts.
};

export const ROLE_LABEL: Readonly<Record<PartRole, string>> = {
  arch: "Doctor's scan",
  cap: "Healing cap (aligned)",
  construction: "Construction",
  socket: "Socket (derived)",
};

/** CSS hex string ("#rrggbb") for a role's PALETTE color, for DOM/CSS consumers (e.g. the legend swatch). */
export function paletteHex(role: PartRole): string {
  return `#${PALETTE[role].toString(16).padStart(6, "0")}`;
}

/**
 * MARKED-FEATURE colors, one per feature kind (client ask 2026-07-24 — the manual
 * correspondence flow). ONE table serves both halves of that flow: the markers drawn on the
 * LIBRARY PART while annotating, and the operator's corresponding marks on the SCAN. They are
 * the same colors on purpose — a pair is only readable if "the magenta trench on the part" and
 * "the magenta dot on the scan" are visibly the same thing.
 *
 * Distinct from every existing scene color (proposal orange #ff9800, centre red #e6362e,
 * legacy-rim blue #2f7fe6, rim-border teal #17b6a8, brush green #2fd070, cream arch, steel-blue
 * construction) and readable against both the cream part/scan and the light-blue backdrop:
 *   - trench (magenta #e040fb): the coded cutout — the kind this flow is actually about, so it
 *     gets the loudest hue. Deliberately NOT the centre mark's red, which it would otherwise
 *     be confused with on a scan that still carries centre/rim marks.
 *   - notch (amber #ffb300) and flat (violet #8b5cf6): the other vendor keying styles the same
 *     correspondence math serves; no catalog part reads them today.
 *   - channel (cyan #00b8d4): the screw bore. Seeded and drawn because the operator sees the
 *     hole and expects it in the list, but every catalog channel is concentric with the rim
 *     centre, so the server refuses it as a rotation anchor (it names the axis, not a clock
 *     angle) — the UI greys it in the picker rather than hiding it.
 */
export const FEATURE_COLOR: Readonly<Record<FeatureKind, number>> = {
  trench: 0xe040fb,
  notch: 0xffb300,
  flat: 0x8b5cf6,
  channel: 0x00b8d4,
};

/** The four marked-feature kinds (mirrors the worker's FEATURE_KINDS). Declared here rather
 *  than imported from domain/ so the viewer layer stays self-contained; domain/partFeatures.ts
 *  owns the same union for the API/UI side and the two are pinned together by a test. */
export type FeatureKind = "trench" | "notch" | "flat" | "channel";

/** CSS hex string for a feature kind's marker color — the swatch in the annotation list and
 *  the correspondence picker must match the sphere in 3D exactly. */
export function featureHex(kind: FeatureKind): string {
  return `#${FEATURE_COLOR[kind].toString(16).padStart(6, "0")}`;
}

/**
 * FREE numbered correspondence points (client ask 2026-07-26 — RealGUIDE's arbitrary clicks
 * on the part and the scan). NOT a feature kind: a free point has no detector identity, so it
 * must not wear a kind's color — its number plus THIS color is what ties the part-pane marker
 * to its scan-pane match. Light blue, distinct from every kind above and from every scene
 * color in the module doc; the channel's cyan (#00b8d4) is deeper and never shares a pane
 * with free points (concentric bores are not anchorable, so the fit-by-points panes never
 * draw them).
 */
export const FREE_POINT_COLOR = 0x40c4ff;
/** The ghost of a pending mark — where the CURRENT pose claims a placed part
 * point sits on the scan (display-only; §10-AI). Amber, the repo's own
 * "a consequence to weigh" tone, and dimmer than a real mark. */
export const GHOST_POINT_COLOR = 0xd9a441;

/** CSS hex string for the free-point color — the pair list's swatch must match the sphere. */
export function freePointHex(): string {
  return `#${FREE_POINT_COLOR.toString(16).padStart(6, "0")}`;
}

/**
 * THE CAP-CROP LAYER'S COLOR (client 2026-08-06, §10-AO: "the scanned healing cap renders
 * white"). Panes 2/3's scan crop is the same doctor's-scan mesh as the whole-arch surfaces
 * (Arch context dialog, Delivery previews, worklist), but tightened to just the cap
 * (declare.ts scanPaneRadiusMm) the arch's usual cream/tan (PALETTE.arch, #f2e3a6) reads as
 * an unnaturally warm, almost golden cap rather than a scanned tooth surface — the client's
 * literal complaint was that a healing cap this tight should read close to its own material,
 * bone-white. NOT PALETTE.arch, and NOT a new PartRole entry: the cap-crop mesh never goes
 * through the composite STL loader (it is a client-cropped VerifyLayerGeometry, set directly
 * in SitePanes.tsx), and the whole-arch surfaces above keep PALETTE.arch untouched. NOT pure
 * white (#ffffff) — flat white kills the scene's Lambert shading (no surface has anywhere left
 * to go darker, so the crop reads as a shadowless cutout instead of a scanned solid); #f2f1ec
 * is bone-white with just enough value headroom for shading to read.
 */
// 0xf2f1ec → 0xf7f6f2 (client 2026-08-10: "we need more glossy white here") —
// one step whiter, still not pure white, and the crop layer now renders with
// a SPECULAR material (VerifyLayerGeometry.glossy) so the cap reads polished.
export const CAP_SCAN_COLOR = 0xf7f6f2;

/** CSS hex string for the cap-crop layer's color — legend swatches must match the mesh. */
export function capScanHex(): string {
  return `#${CAP_SCAN_COLOR.toString(16).padStart(6, "0")}`;
}
