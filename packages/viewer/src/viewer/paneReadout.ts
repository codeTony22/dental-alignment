/**
 * WHAT A PANE MAY HONESTLY SAY ABOUT ITS OWN CAMERA — the footer band's two claims
 * (gap pane-footer-scale-bar-and-axis-label, 2026-07-31).
 *
 * Until this the panes said NOTHING about scale or orientation: an operator judging a
 * 0.15mm deviation had no way to know whether the cap on screen was 6mm or 60mm across,
 * and no way to know where the camera had ended up after a drag.
 *
 * Both answers have to be LIVE, and that is the whole design pressure here:
 *
 *  - mm-per-pixel is a property of a PERSPECTIVE camera at ONE plane. It changes with
 *    every dolly, so it cannot be a constant baked into CSS; it is measured at the focus
 *    plane (the orbit target — the plane the framed subject sits on) and re-read whenever
 *    the camera moves.
 *  - the axis label cannot be a static string. Panes 2 and 3 frame down the seated pose's
 *    axis and then ORBIT FREELY (VerifyViewer re-frames only on a genuine target change),
 *    so the design prototype's fixed "OCCLUSAL" caption would begin lying on the operator's
 *    first drag. This reads the live camera against the axis the pane framed on and says
 *    how far off it now is.
 *
 * Pure functions, because VerifyScene is browser-only (WebGLRenderer in its constructor):
 * the scene reads its camera and hands these numbers, and these are what a node test holds.
 */

/** One reading of a pane's camera. `viewDirection` is the unit vector FROM the target
 *  TOWARD the camera — the same convention VerifyScene.frameOn takes, so a reading can be
 *  compared directly against the direction the pane was framed with. */
export interface PaneViewReadout {
  readonly viewDirection: readonly [number, number, number];
  /** Millimetres per CSS pixel AT THE FOCUS PLANE. Not a property of the pane — of the
   *  camera's current distance. */
  readonly mmPerPixel: number;
}

/** A scale bar the pane can draw: a round number of millimetres and the pixel length that
 *  actually measures it at the current camera. */
export interface PaneScaleBar {
  readonly mm: number;
  readonly px: number;
  readonly label: string;
}

/**
 * Millimetres per CSS pixel at the focus plane.
 *
 * A perspective camera's visible extent at distance d is 2·d·tan(fov/2); dividing by the
 * viewport's pixel height gives an ISOTROPIC mm/px (square pixels, aspect handled by the
 * projection), so the same number sizes a horizontal bar. It is only true AT THAT PLANE —
 * geometry nearer the camera measures larger — which is why the surface that prints it
 * says "at the focus plane" rather than "on the cap".
 *
 * null for any degenerate input: a bar drawn from a NaN is worse than no bar.
 */
export function mmPerPixelAtFocus(
  distanceMm: number,
  fovDeg: number,
  viewportHeightPx: number,
): number | null {
  if (!Number.isFinite(distanceMm) || distanceMm <= 0) return null;
  if (!Number.isFinite(fovDeg) || fovDeg <= 0 || fovDeg >= 180) return null;
  if (!Number.isFinite(viewportHeightPx) || viewportHeightPx <= 0) return null;
  const visibleMm = 2 * distanceMm * Math.tan((fovDeg * Math.PI) / 360);
  const mmPerPixel = visibleMm / viewportHeightPx;
  return Number.isFinite(mmPerPixel) && mmPerPixel > 0 ? mmPerPixel : null;
}

/** The steps a bar may claim. A 1-2-5 ladder because those are the numbers an operator
 *  reads off a bar without doing arithmetic; the range spans a 6mm library part at full
 *  zoom to a whole arch pulled back. */
const SCALE_STEPS_MM: readonly number[] = [0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100];

/** Below this a bar is a stub the eye cannot compare anything against — and a stub with a
 *  number beside it reads as a measurement it is not. */
const MIN_BAR_PX = 20;

/** Strip the ladder's trailing zeros: "0.5 mm", not "0.50 mm"; "1 mm", not "1.0 mm". */
function stepLabel(mm: number): string {
  return `${Number(mm.toFixed(2))} mm`;
}

/**
 * The largest ladder step that fits the bar's pixel budget and is still long enough to
 * read. Returns null when NOTHING on the ladder qualifies — the deliberate outcome for a
 * camera so far out or so close in that no round number lands: the pane then ships no bar
 * rather than a bar whose number is a rounding artefact.
 */
export function paneScaleBar(mmPerPixel: number, maxPx = 96): PaneScaleBar | null {
  if (!Number.isFinite(mmPerPixel) || mmPerPixel <= 0) return null;
  let best: PaneScaleBar | null = null;
  for (const mm of SCALE_STEPS_MM) {
    const px = Math.round(mm / mmPerPixel);
    if (px < MIN_BAR_PX || px > maxPx) continue;
    best = { mm, px, label: stepLabel(mm) };
  }
  return best;
}

/** Within this the pane is still, for an operator's purposes, looking down the axis it
 *  framed on — orbit damping alone leaves a degree or so of slop, and a label that
 *  flickered to "1° off" on every settle would read as noise, not as a reading. */
const ON_AXIS_DEG = 2;

/**
 * WHERE THE CAMERA IS NOW, said against the axis the pane framed on.
 *
 * `reference` is the direction the pane was framed with (the seated pose axis for panes
 * 2/3, the part's own axis for pane 1) and `referenceLabel` names it in the operator's
 * words. With no reference — the viewer's default three-quarter angle, used when nothing
 * has an axis of its own — the honest answer is that this is a free view, not an invented
 * anatomical direction.
 */
export function paneAxisLabel(
  readout: PaneViewReadout | null,
  reference: readonly [number, number, number] | null,
  referenceLabel: string,
): string | null {
  if (readout === null) return null;
  const deg = angleBetweenDeg(readout.viewDirection, reference);
  if (deg === null) return "free view";
  return deg <= ON_AXIS_DEG ? `down ${referenceLabel}` : `${Math.round(deg)}° off ${referenceLabel}`;
}

/** Degrees between two directions, or null when either is not a direction. Signed by
 *  construction: the far side of the subject is 180° off, never 0° again. */
function angleBetweenDeg(
  a: readonly [number, number, number],
  b: readonly [number, number, number] | null,
): number | null {
  if (b === null) return null;
  const la = Math.hypot(a[0], a[1], a[2]);
  const lb = Math.hypot(b[0], b[1], b[2]);
  if (!(la > 1e-9) || !(lb > 1e-9)) return null;
  const dot = (a[0] * b[0] + a[1] * b[1] + a[2] * b[2]) / (la * lb);
  return (Math.acos(Math.min(Math.max(dot, -1), 1)) * 180) / Math.PI;
}

/** Below these a new reading says nothing the last one did not. */
const READOUT_ANGLE_EPS_DEG = 0.5;
const READOUT_SCALE_EPS = 0.01;

/**
 * Is this reading worth publishing?
 *
 * OrbitControls fires "change" on EVERY damped frame, so an un-gated readout would push a
 * React state update at 60fps for the whole tail of a flick. The gate is set below what
 * either surface can show — the label rounds to a whole degree, the bar to a ladder
 * step — so nothing visible is ever suppressed.
 */
export function viewReadoutChanged(
  previous: PaneViewReadout | null,
  next: PaneViewReadout,
): boolean {
  if (previous === null) return true;
  const deg = angleBetweenDeg(previous.viewDirection, next.viewDirection);
  if (deg === null || deg > READOUT_ANGLE_EPS_DEG) return true;
  if (previous.mmPerPixel <= 0) return true;
  return Math.abs(next.mmPerPixel - previous.mmPerPixel) / previous.mmPerPixel > READOUT_SCALE_EPS;
}
