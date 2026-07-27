import type { Vec3 } from "../domain/types";
import { CAP_REGION_RADIUS_MM } from "./meshCrop";

/**
 * THE SITE NEIGHBOURHOOD — how much of the jaw the main stage shows around the active cap.
 *
 * It is deliberately the SAME 9 mm region the verify panes crop the scan to (see meshCrop), not a
 * second number: the main stage and the verify panes must agree about what "this site" means, and
 * one constant cannot drift from itself.
 *
 * The client chose this band over both extremes, and the measurements say they were right. At a
 * 45° FOV a 9 mm framing radius puts the camera ~33 mm out and shows ~27 mm of jaw, so:
 *
 *   - the 6.16 mm cap reads 23% of the view (~100 px on the live 444 px stage) — up from 3.1%
 *     and 14 px when the camera framed the whole arch, which is the complaint this answers;
 *   - the cap's NEIGHBOURS and the gum line stay in frame, so the operator can still tell which
 *     tooth this is and whether the collar clears the tissue — judgements a cap-tight view
 *     silently removes;
 *   - the 8 mm pose triad stays inside the frame (at cap-tight framing its arms run off both
 *     edges), and the size-attenuated brush dots stay ~36 px rather than ~80 px blobs.
 */
export const SITE_FRAME_RADIUS_MM = CAP_REGION_RADIUS_MM;

/**
 * WHAT THE STAGE IS FRAMED ON. Subject and DIRECTION compose: the operator picks a subject here,
 * then a direction with the existing Front/Left/Right/Top presets. Those presets need no change —
 * they read the remembered centre and distance fresh on every call, so once the remembered
 * subject is the site, they orbit the site.
 */
export type StageSubject = "arch" | "site";

/** Where the main stage should point, how much around it to show, and its identity. */
export interface RouteTarget {
  readonly tooth: number;
  readonly center: Vec3;
  readonly radiusMm: number;
  /**
   * The identity that decides whether this is a NEW place to look. Content generation + tooth,
   * and deliberately NOT the coordinates — see routeSignature.
   */
  readonly key: string;
}

/**
 * Everything the decision depends on. Assembled by App from state it already holds — this module
 * deliberately knows nothing about React, the scene, or how any of it is stored.
 */
export interface RouteInputs {
  /** The active site's tooth, or null when there is no active site. */
  readonly tooth: number | null;
  /** The site's human-marked centre (`centerMark ?? center`), or null when it has none. */
  readonly siteCenter: Vec3 | null;
  /** The MEASURED seated implant origin for this tooth, once a run has produced one. */
  readonly posePosition: Vec3 | null;
  /**
   * Bumped whenever the stage's content is replaced — a run, a correction, a re-load. Half of
   * the route identity, and what makes "the same tooth, freshly re-seated" a new place to look
   * while "the same tooth, unchanged" is not.
   */
  readonly contentGeneration: number;
  /** What the operator has asked the stage to be framed on. */
  readonly subject: StageSubject;
  /** True while a brush, mark, rim-point, point-pick or add-site click is armed on the scan. */
  readonly toolActive: boolean;
  /** True while a library part is previewed instead of the jaw. */
  readonly partPreviewActive: boolean;
  /** True when the stage is showing an arch at all (not a part or a construction alone). */
  readonly contentIsArch: boolean;
  /** True while a full-screen dialog covers the stage (verify, fit-by-points). */
  readonly modalOpen: boolean;
}

function isFinitePoint(p: Vec3 | null): p is Vec3 {
  return p !== null && Number.isFinite(p[0]) && Number.isFinite(p[1]) && Number.isFinite(p[2]);
}

/**
 * WHERE THE MAIN STAGE SHOULD LOOK — or null for "do not move the camera".
 *
 * The null cases are the substance of this function, not its edge cases. Each was traced to a
 * real sequence in this app, and the reason they matter more than usual is a structural fact
 * about the viewer: `controls.enabled = false` does NOT protect the camera. The render loop calls
 * `controls.update()` unconditionally and nothing gates the camera-position writes, so a route
 * fired while a tool is armed genuinely moves the view — and it is WORSE than during free orbit,
 * because with the controls off the operator cannot orbit back, so their next click lands
 * somewhere they never aimed. Concretely: a brush stroke straddling two viewpoints (whose tail
 * ships to /run as markedPoints and, unlike a stray mark sphere, is never reviewable on screen),
 * a centre mark resolved along a ray the operator no longer sees, or a rim-point series collected
 * against a camera that moved between clicks.
 *
 * The non-finite guard is not defensive padding either: a NaN centre would put NaN into the
 * remembered framing distance, and `setAnatomyView`'s `<= 0` guard does not catch NaN (`NaN <= 0`
 * is false) — so one bad coordinate would permanently kill all four view presets, silently.
 *
 * Preferring the seated pose over the mark is a small honesty point: the pose is a MEASUREMENT of
 * where the cap is; the mark is where a human clicked, and carries a measured 0.3-0.6 mm of
 * noise. A bad pose falls back to the mark rather than refusing — a camera target is not
 * load-bearing enough to justify showing nothing.
 */
export function resolveRouteTarget(inputs: RouteInputs): RouteTarget | null {
  if (inputs.subject !== "site") return null;
  if (inputs.toolActive) return null;
  if (inputs.partPreviewActive) return null;
  if (inputs.modalOpen) return null;
  if (!inputs.contentIsArch) return null;
  if (inputs.tooth === null) return null;

  const center = isFinitePoint(inputs.posePosition)
    ? inputs.posePosition
    : isFinitePoint(inputs.siteCenter)
      ? inputs.siteCenter
      : null;
  if (center === null) return null;

  return {
    tooth: inputs.tooth,
    center,
    radiusMm: SITE_FRAME_RADIUS_MM,
    key: `${inputs.contentGeneration}:${inputs.tooth}`,
  };
}

/**
 * A STABLE IDENTITY for a target, so the camera moves when the place to look changes and at no
 * other time.
 *
 * This exists because of a specific trap: `withSites` spreads state before `withActiveSite`'s
 * identity bail-out compares it, so it NEVER returns the previous object. Every mark placed,
 * brush finished, rim point committed and variant changed therefore mints a fresh `selection`,
 * and an effect keyed on that object would re-route the camera on all of them — the exact
 * "software keeps yanking my view" failure that makes auto-framing worse than none.
 *
 * The key is CONTENT GENERATION + TOOTH, and excludes the coordinates on purpose — the opposite
 * choice from `marksSignatureFor`, which exists to notice mark movement. Placing the fourth rim
 * point must not re-frame the camera on the fourth rim point; re-seating the cap, which bumps the
 * generation, must.
 */
export function routeSignature(target: RouteTarget | null): string | null {
  return target === null ? null : target.key;
}
