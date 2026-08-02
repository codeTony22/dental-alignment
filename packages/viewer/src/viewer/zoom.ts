/**
 * ZOOM AS A COUNTER, NOT A CAMERA.
 *
 * The workspace toolbar's −/+ zoom the panes. The client's comp zooms ONE pane, the one
 * under the cursor; ours zooms all of them together (client ruling, 2026-08-02: "global
 * is probably better on adjustment views"), and the reason is the same reason the three
 * panes exist at all — they are read side by side, and a zoom that changes only one of
 * them makes the comparison lie about scale.
 *
 * The surface therefore holds ONE signed integer for the whole workspace, and each pane
 * applies the DELTA it has not applied yet. A counter rather than an absolute distance,
 * because the operator also has the scroll wheel: an absolute zoom would yank the camera
 * back to the button's idea of where it should be every time the button moved, and the
 * two controls would fight. A relative step composes with the wheel instead, which is
 * what a −/+ means everywhere else.
 *
 * All of this is arithmetic, so it lives here and is pinned in node — the scene that
 * consumes it needs WebGL and cannot be.
 */

/** One press. 1.25 is ~4 presses to double, which reads as a step rather than a jump. */
export const ZOOM_STEP = 1.25;

/**
 * How close and how far a button may take the camera, as a multiple of the pane's own
 * framing distance. The floor is not taste: `frameOn` sets `near = distance / 500`, and
 * the geometry starts crossing the near plane before the camera reaches the target, so a
 * zoom with no floor ends in a pane that has clipped its own subject away. The ceiling is
 * the same argument against `far = distance * 50`, with far more headroom.
 */
export const MIN_ZOOM_SCALE = 0.2;
export const MAX_ZOOM_SCALE = 5;

/**
 * The multiplier that carries a pane from zoom level `from` to level `to`.
 *
 * Signs: a HIGHER level is zoomed IN, and zooming in means a SMALLER distance — so the
 * factor inverts. Getting this backwards is silent (the buttons simply swap), which is
 * why it is one function with its own test rather than an exponent written inline.
 */
export function zoomFactorBetween(from: number, to: number): number {
  return ZOOM_STEP ** (from - to);
}

/** Hold a distance scale inside the framing's safe band. */
export function clampZoomScale(scale: number): number {
  // NaN only — it fails BOTH comparisons in a min/max and would sail through as NaN, and a
  // NaN camera position is a black pane with no error anywhere. ±Infinity is a perfectly
  // ordinary out-of-band scale and clamps like any other.
  if (Number.isNaN(scale)) return 1;
  return Math.min(Math.max(scale, MIN_ZOOM_SCALE), MAX_ZOOM_SCALE);
}

/**
 * The furthest the counter may travel in each direction — the level at which the band
 * above is reached, and past which a press would only be recorded, never seen.
 *
 * DERIVED, not chosen: change a bound or the step and these follow, which is the point.
 */
export const MAX_ZOOM_LEVEL = Math.floor(Math.log(1 / MIN_ZOOM_SCALE) / Math.log(ZOOM_STEP));
export const MIN_ZOOM_LEVEL = -Math.floor(Math.log(MAX_ZOOM_SCALE) / Math.log(ZOOM_STEP));

/**
 * Hold the COUNTER inside the band, not merely the scale it asks for.
 *
 * FOUND BY OPENING IT (2026-08-02). Clamping only the scale left the counter free to run:
 * forty presses of + parked the camera at the floor — correctly — and left `zoomLevel` at
 * 42, so the operator then had to press − about thirty-five times before anything on
 * screen moved. The button was not dead, which is worse than dead: it accepted every
 * press and answered none of them.
 *
 * Saturating the counter is what makes a spent control HONEST. At the floor the level is
 * the floor's level, `canZoom` reports the truth, and one press of − steps the camera
 * back immediately.
 */
export function clampZoomLevel(level: number): number {
  if (Number.isNaN(level)) return 0;
  return Math.min(Math.max(level, MIN_ZOOM_LEVEL), MAX_ZOOM_LEVEL);
}

/**
 * Whether a −/+ at this level can still do anything, so the button can disable rather
 * than click into nothing.
 *
 * Answered from the LEVEL, not from a live camera, and the limit is worth stating: a pane
 * the operator has already WHEELED to the floor will disable a step later than it truly
 * ran out. Polling three cameras for a button's disabled attribute would couple a control
 * to a render loop, and the wheel has no counter of its own to consult. What was NOT
 * acceptable — and is fixed above — is the button's own presses running away from it.
 */
export function canZoom(level: number, direction: 1 | -1): boolean {
  const at = clampZoomLevel(level);
  return direction === 1 ? at < MAX_ZOOM_LEVEL : at > MIN_ZOOM_LEVEL;
}
