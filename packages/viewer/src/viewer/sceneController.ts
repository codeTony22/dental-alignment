/**
 * Imperative three.js scene controller. Pure side-effect module, no React.
 * Viewer3D (the React component) owns the lifecycle; this owns the WebGL scene.
 */
import * as THREE from "three";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { FEATURE_COLOR, PALETTE, type CompositePartSpec, type FeatureKind, type PartRole } from "./palette";
import { computeAnatomyFrame, type AnatomyFrame } from "./anatomyOrientation";
import { computePartFrame, rawFromFeature, type PartFrame } from "./partFrame";
import { fitCenterRingPlane, type CenterRingFit } from "./centerRing";

// Light blue backdrop (client request 2026-07-24) — airy, keeps contrast with the
// cream scan, green cap, and steel-blue construction.
const BACKGROUND_COLOR = 0xd8e8f2;
const SCAN_MATERIAL_COLOR = PALETTE.arch;
const PART_MATERIAL_COLOR = 0x9aa4b0;
const MARKER_COLOR = 0xff9800;
const MARKER_EMISSIVE = 0xff6f00;
const BRUSH_COLOR = 0x2fd070;
const BRUSH_POINT_SIZE = 2.2;
const BRUSH_MOVE_THROTTLE_MS = 30;

// Every registration-point/pose-indicator marker (proposal spheres, centre, legacy rim, rim-
// border dots, pose triads) renders THROUGH the scan/composite geometry — RealGUIDE's own
// convention for numbered registration points, and a real fix for tall caps whose curated centre
// mark sits at rim height BELOW the crown dome (live-verified: 1540 sampled vertices within
// 2.5mm xy of one such mark sit >0.3mm higher, occluding it under normal depth testing). Markers
// are INDICATORS, not physical objects on the scan surface, so depthTest/depthWrite are both off
// and renderOrder is pushed high so they draw after (visually on top of) the mesh regardless of
// which side of it they're geometrically on — including the far side, matching RealGUIDE
// screenshots where registration points glow through the model.
const MARKER_RENDER_ORDER = 999;

/**
 * A proposal marker occupies this SHARE of whatever is framed — it is not an absolute size.
 *
 * The product shipped a fixed 2.6mm radius, and on a site-framed pane that is a 5.2mm ball
 * over a ~4mm cap: the marker swallowed the very thing it was pointing at (client screenshot,
 * 2026-07-29). The demo had already learned this and fixed it the same way on 2026-07-26 —
 * its note says a fixed size "hid the very trench it named". A fraction of the framed radius
 * keeps the dot the same visual size whether the pane shows one tooth or the whole arch,
 * which is what "mark this point" has to mean across views at different scales.
 */
const MARKER_RADIUS_FRACTION = 0.035;

/** Proposal spheres are built at this radius and SCALED — one geometry, any framing. */
const MARKER_BASE_RADIUS_MM = 1;

/** Never let a marker vanish entirely on a very tight frame. */
const MARKER_MIN_RADIUS_MM = 0.05;

/** Apply the render-through-geometry indicator convention to a marker's material + object. */
function makeIndicatorVisible(material: THREE.Material, object: THREE.Object3D): void {
  material.depthTest = false;
  material.depthWrite = false;
  object.renderOrder = MARKER_RENDER_ORDER;
}

// RealGUIDE-style registration-point markers: a distinctive RED sphere for the cap CENTER, a
// distinctive BLUE sphere for the LEGACY single click on the cap's WIDEST rim edge (curated
// prefills only — see setSiteMarker/App.tsx). See palette.ts's doc comment for the full marker
// color reference.
const MARK_CENTER_COLOR = 0xe6362e;
const MARK_CENTER_EMISSIVE = 0x8c1a14;
const MARK_RIM_COLOR = 0x2f7fe6;
const MARK_RIM_EMISSIVE = 0x144a8c;
const MARK_SPHERE_RADIUS_MM = 0.6;
// Multi-click rim-BORDER points get their OWN teal/cyan color, deliberately distinct from the
// legacy rim mark's blue above — a client screenshot showed the two were indistinguishable on
// screen, actively misleading once a row had both a stale legacy sphere and new border dots (the
// mapper doesn't even send rim_mark once rimPoints exists — see toWireRunSiteInput). Rendered
// slightly smaller than the single center/rim mark spheres — there can be up to a dozen of them
// clustered around one cap's edge, and the doctor still needs to see the mesh underneath.
const RIM_POINT_COLOR = 0x17b6a8;
const RIM_POINT_EMISSIVE = 0x0c6259;
const RIM_POINT_SPHERE_RADIUS_MM = 0.4;
// Cosmetic prefill snap (setSiteMarker): a nearest-mesh-vertex match farther than this from the
// input point is treated as "not actually on this mesh" and the raw input is shown instead of
// teleporting the sphere to an unrelated part of the scan — curated marks are near-surface by
// construction, so a genuine snap target is always well under this.
const SNAP_MAX_DISTANCE_MM = 3;

/**
 * Padding around the site's neighbourhood radius when routing the stage to a cap. The same
 * close-fit factor the part preview uses — at a 45° FOV it puts the camera ~33 mm from a 9 mm
 * site region, showing ~27 mm of jaw: the cap at ~23% of the view with its neighbours and the
 * gum line still in frame. See viewer/siteRouting.ts for why the neighbourhood, not the cap.
 * (Exported here, private in the frozen original — the characterization test pins that this
 * IS the close-fit factor; recorded divergence, ledger row 3.)
 */
export const SITE_FIT_PADDING = 1.4;

/**
 * How long the routed move takes. Long enough to read as travel (so the operator keeps their
 * bearings on the arch), short enough that it never feels like waiting.
 */
const SITE_ROUTE_EASE_MS = 400;
// Shared identity-matrix instance for the snap's matrixWorld.equals() fast path — every scan/
// composite mesh in this controller is added at identity transform today (see loadStl/
// loadComposite), so this check is nearly always true and skips a per-vertex matrix multiply.
const IDENTITY_MATRIX4 = new THREE.Matrix4();

// CENTRE click placement: the cap's centre is a screw-recess HOLE, not a surface point (see
// resolveCenterPlacement's doc) — these tune the BALL of mesh vertices anchored at the raw
// raycast hit (v2: hit-anchored, not ray-line-anchored — see resolveCenterPlacement's doc for
// why v1's ray corridor let an overhanging neighbour pollute the result) used to find the
// surrounding top-edge depth, camera-angle independent.
const CENTER_BALL_RADIUS_MM = 3.0;
const CENTER_BALL_WIDE_RADIUS_MM = 4.5;
const CENTER_BALL_MIN_VERTICES = 20;
const CENTER_BALL_PERCENTILE = 0.1;

// Post-run seated-pose axis triad (RealGUIDE-style): three short line segments per site, drawn
// at the implant position, oriented by the pose_matrix rotation columns. Standard RGB axis
// convention (red=x, green=y, blue=z) — see palette.ts's marker-color doc. Pure line geometry
// (THREE.Line + LineBasicMaterial), not affected by lighting, so the colors read true regardless
// of scene lighting/material tinting.
const TRIAD_AXIS_COLOR_X = 0xe6362e; // red — reuses the centre-mark red (both are "the x axis
// of something", no clash: the centre mark is per-row during marking, the triad is post-run only)
const TRIAD_AXIS_COLOR_Y = 0x2fd070; // green — reuses the brush-stroke green (both mean "human/
// automation-confirmed", no clash: brush marks are pre-run inputs, the triad is a post-run output)
const TRIAD_AXIS_COLOR_Z = 0x2f7fe6; // blue — reuses the legacy-rim blue (both are registration-
// adjacent, no clash: legacy rim marks are pre-run inputs, the triad is a post-run output)
const TRIAD_AXIS_LENGTH_MM = 8;

// MARKED FEATURES (client ask 2026-07-24 — the manual correspondence flow). Two families,
// one color table (see palette.ts's FEATURE_COLOR):
//   - PART-feature markers: the library part's marks, drawn on the previewed part while
//     annotating, placed from (azimuth, radius, z) through the part's own derived frame.
//   - CORRESPONDENCE marks: where the operator says they see those same features on the
//     SCAN — plain world points from a click, keyed by the feature id they were named for.
// Sized between the centre/rim spheres (0.6) and the rim-border dots (0.4): a cap is 4-8mm
// across and several marks can sit on one part, so they must not swallow the geometry.
const FEATURE_MARKER_RADIUS_MM = 0.45;
// A SELECTED part-feature marker (the one a click will move) is drawn larger, not recolored —
// the color carries the KIND and must keep meaning the same thing in both halves of the flow.
const FEATURE_MARKER_SELECTED_RADIUS_MM = 0.72;
const FEATURE_MARKER_EMISSIVE_SCALE = 0.45;

/**
 * Linear-interpolated percentile of an ALREADY SORTED (ascending) numeric array, p in [0, 1].
 * Pure numeric helper — no THREE/DOM dependency. Was module-private in the frozen apps/web
 * original; EXPORTED here so the characterization test executes the exact function the
 * centre-click placement reads its corridor depth from (recorded divergence, ledger row 3).
 */
export function percentile(sortedAscending: readonly number[], p: number): number {
  if (sortedAscending.length === 1) return sortedAscending[0] as number;
  const rank = p * (sortedAscending.length - 1);
  const lowerIndex = Math.floor(rank);
  const upperIndex = Math.ceil(rank);
  const lower = sortedAscending[lowerIndex] as number;
  const upper = sortedAscending[upperIndex] as number;
  if (lowerIndex === upperIndex) return lower;
  const fraction = rank - lowerIndex;
  return lower + (upper - lower) * fraction;
}

export interface MarkerSpec {
  readonly center: readonly [number, number, number];
  readonly radiusMm: number;
}

/**
 * A seated implant's pose, as carried by the per-tooth "<case>-<tooth>-implant.json" package
 * file: `position` is the implant origin (world frame, mm), `poseMatrixColumns` are the pose
 * matrix's first three COLUMNS (each a unit-length local axis direction in world space) — the
 * shape App.tsx reads straight from the JSON's row-major pose_matrix (column j = [row0[j],
 * row1[j], row2[j]]), so no matrix-math utility is needed here beyond picking the columns apart.
 */
export interface PoseTriadSpec {
  readonly position: readonly [number, number, number];
  readonly axisX: readonly [number, number, number];
  readonly axisY: readonly [number, number, number];
  readonly axisZ: readonly [number, number, number];
}

/**
 * One marked feature to draw on the PREVIEWED LIBRARY PART: its canonical-frame polar
 * placement (the shape the features endpoint hands back), plus which one is currently
 * selected for a move. Positioned through the part's own derived frame — see partFrame.ts.
 */
export interface PartFeatureMarkerSpec {
  readonly key: string;
  readonly kind: FeatureKind;
  readonly azimuthDeg: number;
  readonly radiusMm: number;
  readonly zMm: number;
  readonly selected?: boolean;
}

export type ViewerFitMode = "wide" | "close";

/** Which registration point a single-shot mark click is placing. */
export type MarkKind = "center" | "rim";

/**
 * Anatomical camera presets (client ask 2026-07-14: "prepare the 3d view to face the front
 * camera and make easy, safe the step of looking for the right face of the mouth"): named
 * views derived from the scan's own geometry (see anatomyOrientation.ts), replacing the old
 * fixed world-axis corner view that on a tilted upper scan faced the BACK wall. "left"/
 * "right" are SCREEN-relative to the front view (which patient side that is depends on jaw
 * and scanner frame — screen-relative is the label an operator can act on without thinking).
 */
export type AnatomyViewId = "front" | "left" | "right" | "occlusal";

// Front/left/right presets look at the arch slightly from above the occlusal plane: an
// edge-on rim reads as a line, a slightly elevated one as an ellipse — the geometry the
// border-click gesture needs (the redo's bad click came from an oblique/occluded view).
const ANATOMY_ELEVATION_RAD = (18 * Math.PI) / 180;

// ---------------------------------------------------------------------------------------
// PURE CAMERA/MARKER RULES, extracted for the characterization test (copy-debt ledger
// row 3: recorded, behavior-preserving divergences from the frozen apps/web original,
// where each formula lived inline in a SceneController method — verified by reading the
// frozen source side by side). The class methods below CALL these; extraction is the only
// change, every formula is verbatim. Construction-time/WebGL behavior stays browser-only —
// see sceneController.characterization.test.ts's header for that boundary.
// ---------------------------------------------------------------------------------------

/** The padding factor a fit mode frames with (was inline in frameOnSphereParams). "close"
 *  is the same close-fit factor SITE_FIT_PADDING routing reuses; "wide" is the load-time
 *  whole-arch view. */
export function fitPaddingFor(fit: ViewerFitMode): number {
  return fit === "close" ? 1.4 : 2.4;
}

/** Camera distance that shows `radiusMm` (clamped to a minimum working radius) with
 *  `paddingFactor` of air at `fovDeg` — the one framing formula every fit and route
 *  shares (was inline in frameOnSphereParams, focusOnSite and frameLoadedContent). */
export function fitDistanceMm(radiusMm: number, fovDeg: number, paddingFactor: number): number {
  const fovRadians = (fovDeg * Math.PI) / 180;
  return (Math.max(radiusMm, 0.01) * paddingFactor) / Math.sin(fovRadians / 2);
}

/** Near/far clip planes derived from a framing distance (was three inline copies of the
 *  same two expressions, one per framing method). */
export function clipPlanesFor(distance: number): { readonly near: number; readonly far: number } {
  return { near: Math.max(distance / 100, 0.01), far: distance * 100 };
}

/** A part-feature marker's radius: selection is a SIZE difference, never a color one (the
 *  color carries the KIND — see setPartFeatureMarkers). Was inline in that method. */
export function featureMarkerRadiusMm(selected: boolean | undefined): number {
  return selected ? FEATURE_MARKER_SELECTED_RADIUS_MM : FEATURE_MARKER_RADIUS_MM;
}

/** THE ROUTING VETO's composition: any pointer mode that owns the next click on the scan
 *  vetoes a camera route. All FOUR modes, including the brush — historically the missing
 *  one (see isBrushActive's doc). Was inline in isToolActive. */
export function anyPointerToolActive(modes: {
  readonly brush: boolean;
  readonly mark: boolean;
  readonly rimPoints: boolean;
  readonly pointPick: boolean;
}): boolean {
  return modes.brush || modes.mark || modes.rimPoints || modes.pointPick;
}

/**
 * The four anatomical presets' camera orientation for a frame: the unit view DIRECTION
 * (target → camera) and the camera UP (was inline in setAnatomyView — see that method's
 * doc for what each view means to the operator). Front/left/right look at the arch from
 * ANATOMY_ELEVATION_RAD above the occlusal plane; "occlusal" looks straight down the
 * occlusal axis with the anterior at the top of the screen.
 */
export function anatomyViewOrientation(
  frame: AnatomyFrame,
  view: AnatomyViewId,
  opts?: { readonly crownsDown?: boolean },
): {
  readonly direction: readonly [number, number, number];
  readonly up: readonly [number, number, number];
} {
  const occ = new THREE.Vector3(frame.occlusal[0], frame.occlusal[1], frame.occlusal[2]);
  const ant = new THREE.Vector3(frame.anterior[0], frame.anterior[1], frame.anterior[2]);
  // From the front view, +lat points to the viewer's RIGHT: screenRight = forward x up
  // with forward = -ant (camera looks from anterior toward posterior) and up = occ.
  const lat = new THREE.Vector3().crossVectors(ant.clone().negate(), occ).normalize();

  const inPlane = Math.cos(ANATOMY_ELEVATION_RAD);
  const elevated = Math.sin(ANATOMY_ELEVATION_RAD);
  let direction: THREE.Vector3;
  let up = occ.clone();
  switch (view) {
    case "front":
      direction = ant.clone().multiplyScalar(inPlane).addScaledVector(occ, elevated);
      break;
    case "left":
      direction = lat.clone().multiplyScalar(-inPlane).addScaledVector(occ, elevated);
      break;
    case "right":
      direction = lat.clone().multiplyScalar(inPlane).addScaledVector(occ, elevated);
      break;
    case "occlusal":
      direction = occ.clone();
      up = ant.clone();
      break;
  }
  /* THE ROLL FOLLOWS THE JAW (client 2026-08-09). An upper arch's crowns point DOWN in
     the patient, and `up = occlusal` renders them at the top of the screen on every
     scan — an upper jaw drawn like a lower one. Flipping the roll (and only the roll)
     puts the teeth where the operator expects them. The DIRECTION is deliberately
     untouched: its elevation term rides `occlusal`, which on an upper arch already
     points downward, so the camera is correctly on the side the teeth face. The
     occlusal preset is exempt — a plan view looks straight at the biting surfaces from
     the side they face on either jaw, and its roll is the anterior axis, not the
     crowns. NOT a transform of anything: §10-AM's rule is that the jaw names and
     cross-checks, never rotates, and a camera roll does neither. */
  if (opts?.crownsDown && view !== "occlusal") up.negate();
  direction.normalize();
  return { direction: [direction.x, direction.y, direction.z], up: [up.x, up.y, up.z] };
}

export type { CompositePartSpec, PartRole } from "./palette";

export class SceneController {
  private readonly renderer: THREE.WebGLRenderer;
  private readonly scene: THREE.Scene;
  private readonly camera: THREE.PerspectiveCamera;
  private readonly controls: OrbitControls;
  private readonly loader = new STLLoader();
  private readonly markerGroup: THREE.Group;
  /**
   * The doctor's scan surface — the mark/brush raycast target. Under loadStl this is the sole
   * loaded mesh; under loadComposite it is whichever composite part has role 'arch' (the
   * doctor's scan/arch), so mark-centre/mark-rim/brush keep working against the scan surface
   * inside a composite view instead of finding no mesh at all. null when no arch surface is
   * present in the current view (e.g. a stage-3 construction-alone composite).
   */
  private meshObject: THREE.Mesh | null = null;
  /**
   * True when meshObject is also an entry in compositeMeshes (i.e. loadComposite set it) — its
   * geometry/material are owned and disposed by clearComposite, so clearMesh must not also
   * dispose it (that would double-dispose the same THREE objects).
   */
  private meshObjectIsCompositePart = false;
  /** Meshes belonging to the current colored composite view (empty outside loadComposite). */
  private compositeMeshes: THREE.Mesh[] = [];
  /** Roles present in the current composite, for the legend. */
  private compositeRoles: PartRole[] = [];
  private resizeObserver: ResizeObserver;
  private animationHandle = 0;
  private disposed = false;
  /**
   * Bumped on every loadStl/loadComposite entry. Rapid staged-view clicks fire overlapping
   * loads; after each load's awaits resolve it must bail before touching the scene if this
   * has moved on — the controller-level mirror of App's activeCaseIdRef stale-response guard.
   */
  private loadGeneration = 0;

  // Brush tool state.
  // liveStroke is the in-progress stroke for whichever row is currently being painted; it is
  // cleared at the START of every new stroke (enableBrush) so marking cap A then cap B never
  // bleeds A's points into B. Each row's ACCEPTED ("Done") patch gets its own committed Points
  // object so clearing/replacing one row's glow never touches another row's.
  private readonly raycaster = new THREE.Raycaster();
  private readonly pointerNdc = new THREE.Vector2();
  /** The eased camera move in flight, or null. Driven by `animate` — see startCameraTween. */
  private cameraTween: {
    readonly fromTarget: THREE.Vector3;
    readonly toTarget: THREE.Vector3;
    readonly fromPosition: THREE.Vector3;
    readonly toPosition: THREE.Vector3;
    readonly startedAt: number;
    readonly durationMs: number;
  } | null = null;
  private brushEnabled = false;
  private brushPainting = false;
  private brushLastMoveAt = 0;
  private readonly liveStroke: THREE.Vector3[] = [];
  private liveStrokeObject: THREE.Points | null = null;
  private readonly committedPatches = new Map<number, THREE.Points>();

  // Single-shot mark mode: enterMarkMode(rowIndex, kind, onPlaced) arms the NEXT pointerdown
  // on the mesh to resolve one world point, place/replace that row's marker sphere for that
  // kind, notify the caller (React needs to learn the resolved point to update its own
  // ConfirmedSite state), and immediately exit mark mode. Per-row like committedPatches, but
  // keyed by kind too.
  private markMode: { rowIndex: number; kind: MarkKind; onPlaced: (point: [number, number, number]) => void } | null =
    null;
  private readonly siteMarkers = new Map<number, { center?: THREE.Mesh; rim?: THREE.Mesh }>();

  // One-shot point pick (the align-to-mark trench click): enterPointPick(onPicked) arms the
  // NEXT pointerdown on the mesh to resolve one plain on-surface world point, notify the
  // caller, and immediately exit — like enterMarkMode but owning NO marker sphere and NO row:
  // the click is a transient input to the align-to-mark endpoint, not a committed site mark,
  // so nothing must survive on screen (and no row's ⊕/◐ spheres may be clobbered by it).
  private pointPick: {
    onPicked: (point: [number, number, number]) => void;
    onMissed?: () => void;
  } | null = null;

  // Multi-click rim-BORDER points: enableRimPoints(rowIndex) arms EVERY subsequent pointerdown
  // (not just the next one) to raycast-place one small blue sphere and stay armed, mirroring the
  // brush's live-stroke-then-commit pattern rather than the single-shot mark mode's one-and-done.
  // rimPointsRowIndex is the row currently being collected (null when not armed); liveRimPoints
  // holds this session's raycast hits (both the resolved points and their rendered spheres, kept
  // in lockstep) and is cleared at the START of every new session (enableRimPoints), same
  // reasoning as the brush's liveStroke. A row's ACCEPTED ("Done") points move into their own
  // committed sphere array so replacing one row's rim points never touches another row's.
  private rimPointsRowIndex: number | null = null;
  private readonly liveRimPoints: THREE.Vector3[] = [];
  private readonly liveRimPointSpheres: THREE.Mesh[] = [];
  private readonly committedRimPoints = new Map<number, THREE.Mesh[]>();

  // Post-run seated-pose axis triads: one THREE.Group (3 line segments) per TOOTH (not row
  // index — triads are drawn straight from runResult.summary.sites, which is keyed by tooth
  // number, not the confirm-table's row index; a row's tooth number can be edited by the doctor,
  // but triads are only ever (re)drawn right after a run, when tooth numbers are exactly what the
  // backend just used). Same survive-view-changes-until-explicit-clear behavior as siteMarkers/
  // committedRimPoints (see loadStl/loadComposite's docs) — case switch disposes them via
  // clearAllPoseTriads.
  private readonly poseTriads = new Map<number, THREE.Group>();

  // MARKED FEATURES on the currently previewed LIBRARY PART. Unlike every other marker family
  // these do NOT survive a view change: they annotate one specific part mesh, so a marker that
  // outlived its part would sit in mid-air over the scan claiming to be a landmark on it. Both
  // loadStl and loadComposite drop them alongside the proposal markers.
  private readonly partFeatureMarkers = new Map<string, THREE.Mesh>();
  /**
   * The previewed part's canonical frame, derived from the loaded geometry (partFrame.ts) —
   * null whenever the current content is not a part whose frame could be justified (the scan,
   * a composite, or a part whose rim ring did not fit). Recomputed lazily on first use after a
   * load and cleared with the mesh, so it can never describe a mesh that is no longer shown.
   */
  private partFrame: PartFrame | null = null;
  private partFrameComputed = false;

  // CORRESPONDENCE marks on the SCAN: where the operator says they see each named library
  // feature. Keyed by feature id (one part feature cannot sit at two places on the scan — the
  // server refuses the repeat, and re-marking a feature must MOVE its dot, not add a second).
  // These DO survive a view change, like the centre/rim/pose indicators (see loadStl's doc):
  // they are the operator's in-progress input to the align-to-correspondence POST, and losing
  // them on a stage switch would leave the pair list describing marks no longer on screen.
  private readonly correspondenceMarks = new Map<string, THREE.Mesh>();

  // Shift+left-drag pan: LEFT stays ROTATE by default; holding Shift swaps it to PAN so the
  // operator can go "side to side" without needing the right mouse button.
  private shiftPanActive = false;

  /* THE JAW'S ROLL (client 2026-08-09). Held on the controller rather than passed per call
     because the presets fire from THREE places — the operator's own buttons, and the two
     auto-front calls that run when a scan or composite finishes loading. A per-call
     argument would have dressed the operator's clicks correctly and left every freshly
     loaded scan upside down, which is precisely the state the client reported. */
  private crownsDown = false;

  /** The preset currently showing, so a jaw change can re-apply it in place. */
  private lastAnatomyView: AnatomyViewId | null = null;

  // Anatomical frame of the CURRENT arch view (scan, or a composite's arch part) — null for
  // non-arch content (library-part previews, construction-alone composites) where anatomical
  // presets would be meaningless. Set by loadStl({anatomy:true})/loadComposite, consumed by
  // setAnatomyView. lastFrameCenter/lastFrameDistance mirror the most recent framing call so
  // presets keep the same subject distance the fit chose.
  private anatomyFrame: AnatomyFrame | null = null;
  private lastFrameCenter: THREE.Vector3 | null = null;
  private lastFrameDistance = 0;
  // The SUBJECT radius the last framing call fitted (not the camera distance) — proposal
  // markers are sized as a share of it, so the dot stays legible whether the pane holds one
  // tooth or the whole arch. 0 until something has been framed; markers fall back to their
  // base radius until then.
  private lastFrameRadius = 0;

  constructor(private readonly container: HTMLDivElement) {
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(BACKGROUND_COLOR);

    const { clientWidth, clientHeight } = container;
    this.camera = new THREE.PerspectiveCamera(
      45,
      Math.max(clientWidth, 1) / Math.max(clientHeight, 1),
      0.1,
      5000,
    );
    this.camera.position.set(0, 0, 150);

    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setSize(Math.max(clientWidth, 1), Math.max(clientHeight, 1));
    container.appendChild(this.renderer.domElement);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    // Pan in the screen plane (the intuitive lab-software behavior) rather than the
    // default orbit-target-plane panning.
    this.controls.screenSpacePanning = true;
    // Explicit (matches the default, but stated so the touch behavior is self-documenting
    // alongside the mouse-button remapping below).
    this.controls.touches.TWO = THREE.TOUCH.DOLLY_PAN;

    // Brighter, cooler-ground lighting (client request 2026-07-24: "scan is a bit
    // dark") — the ground bounce follows the light-blue backdrop instead of the old
    // near-black, and the fill lifts the shadowed slopes.
    const hemi = new THREE.HemisphereLight(0xffffff, 0x9fb4c4, 1.2);
    this.scene.add(hemi);
    const dir = new THREE.DirectionalLight(0xffffff, 0.9);
    dir.position.set(80, 120, 100);
    this.scene.add(dir);
    const fillDir = new THREE.DirectionalLight(0xffffff, 0.5);
    fillDir.position.set(-100, -60, -80);
    this.scene.add(fillDir);

    this.markerGroup = new THREE.Group();
    this.scene.add(this.markerGroup);

    this.resizeObserver = new ResizeObserver(() => this.handleResize());
    this.resizeObserver.observe(container);

    const canvas = this.renderer.domElement;
    canvas.addEventListener("pointerdown", this.handleBrushPointerDown);
    canvas.addEventListener("pointermove", this.handleBrushPointerMove);
    canvas.addEventListener("pointerup", this.handleBrushPointerUp);
    canvas.addEventListener("pointerleave", this.handleBrushPointerUp);
    canvas.addEventListener("pointerdown", this.handleMarkPointerDown);
    canvas.addEventListener("pointerdown", this.handleRimPointsPointerDown);
    canvas.addEventListener("pointerdown", this.handlePointPickPointerDown);

    window.addEventListener("keydown", this.handleShiftPanKeyDown);
    window.addEventListener("keyup", this.handleShiftPanKeyUp);
    window.addEventListener("blur", this.handleShiftPanWindowBlur);

    this.animate();
  }

  private animate = (): void => {
    if (this.disposed) return;
    this.animationHandle = requestAnimationFrame(this.animate);
    // The eased route runs BEFORE controls.update() so OrbitControls' damping smooths the
    // arrival instead of fighting it.
    this.stepCameraTween(performance.now());
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  };

  private handleResize(): void {
    const { clientWidth, clientHeight } = this.container;
    if (clientWidth === 0 || clientHeight === 0) return;
    this.camera.aspect = clientWidth / clientHeight;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(clientWidth, clientHeight);
  }

  /** Fetch and parse a single STL into a geometry, reporting load progress. */
  private loadStlGeometry(
    url: string,
    onProgress?: (fractionLoaded: number) => void,
  ): Promise<THREE.BufferGeometry> {
    return new Promise<THREE.BufferGeometry>((resolve, reject) => {
      this.loader.load(
        url,
        (geo) => resolve(geo),
        (evt) => {
          if (onProgress && evt.total > 0) {
            onProgress(evt.loaded / evt.total);
          }
        },
        (err) => reject(err instanceof Error ? err : new Error("Failed to load STL")),
      );
    });
  }

  /**
   * Load an STL from a URL, replacing whatever mesh is currently shown. Deliberately does NOT
   * touch siteMarkers (centre/legacy-rim spheres), committedRimPoints (teal border dots), or
   * poseTriads (post-run RGB axis triads) — this is also used mid-workflow (e.g. the picker's
   * "view part" preview, or the post-run stage reveal) while a row's marks are already committed
   * and still destined for /run; those marks' VISUAL representation should survive a view change
   * exactly like the brush's committed patch already does (see clearBrush below) — uniform across
   * all five "confirmed"/"seated" representations (brush patch, centre mark, legacy rim mark,
   * rim-border points, pose triad). Only an explicit clearAllSiteMarkers/clearAllRimPoints/
   * clearAllPoseTriads call (case switch) or the single-row clear variants (an operator action on
   * a specific row) removes them.
   */
  async loadStl(
    url: string,
    opts: {
      color?: number;
      fit?: ViewerFitMode;
      onProgress?: (fractionLoaded: number) => void;
      /**
       * True when the loaded mesh is a dental ARCH (the doctor's scan): computes the
       * anatomical frame and starts the camera at the FRONT view instead of the legacy
       * world-axis corner (which faced the back wall on tilted scans). Leave false for
       * part previews — a 6mm cap has no anatomy to orient by.
       */
      anatomy?: boolean;
    } = {},
  ): Promise<void> {
    const color = opts.color ?? SCAN_MATERIAL_COLOR;
    const fit = opts.fit ?? "wide";
    const generation = ++this.loadGeneration;

    const geometry = await this.loadStlGeometry(url, opts.onProgress);

    if (this.disposed || generation !== this.loadGeneration) {
      // Either torn down, or a later loadStl/loadComposite call started after this one —
      // discard this result rather than mixing it into whatever the newer call is building.
      geometry.dispose();
      return;
    }

    this.clearMesh();
    this.clearComposite();
    this.clearMarkers();
    // Part-feature markers annotate ONE part mesh — never let them outlive it (see their
    // field doc); the derived part frame goes with them.
    this.clearPartFeatureMarkers();
    // Only the in-progress stroke, not committed patches: loadStl is also used mid-workflow
    // (e.g. the picker's "view part" preview) while a row's patch is already committed and
    // its markedPoints are still destined for /run — that commit must survive the preview.
    this.clearBrush();

    geometry.computeVertexNormals();
    geometry.computeBoundingSphere();

    const material = new THREE.MeshLambertMaterial({ color, side: THREE.DoubleSide });
    const mesh = new THREE.Mesh(geometry, material);
    this.scene.add(mesh);
    this.meshObject = mesh;
    this.meshObjectIsCompositePart = false;

    this.anatomyFrame = opts.anatomy ? this.computeFrameFromGeometry(geometry) : null;
    this.frameOnBoundingSphere(geometry.boundingSphere, fit);
    if (this.anatomyFrame) {
      this.setAnatomyView("front");
    }
  }

  /**
   * Anatomical frame from a loaded BufferGeometry's position/normal attributes — null when
   * the cloud doesn't read as an arch sheet (computeAnatomyFrame's own gate), which safely
   * disables the presets rather than orienting the camera off noise.
   */
  private computeFrameFromGeometry(geometry: THREE.BufferGeometry): AnatomyFrame | null {
    const position = geometry.getAttribute("position") as THREE.BufferAttribute | undefined;
    if (!position) return null;
    const normal = geometry.getAttribute("normal") as THREE.BufferAttribute | undefined;
    return computeAnatomyFrame(
      position.array as ArrayLike<number>,
      normal ? (normal.array as ArrayLike<number>) : undefined,
    );
  }

  /**
   * Load several STL part files as one colored composite view: one THREE.Mesh per part,
   * each tinted by its role (see palette.ts), all sharing the world frame the backend
   * already poses them in — no per-part transforms are applied here.
   *
   * Same siteMarkers/committedRimPoints/poseTriads survival as loadStl (see its doc) — the
   * post-run stage reveal and stage-switch buttons both go through this method, and a row's
   * centre/legacy-rim/rim-border marks (plus any seated-pose triads) must stay visible (and stay
   * correctly hidden, per applyRimVisibilityInvariant) across that view change, not silently
   * reset or resurrected.
   */
  async loadComposite(parts: readonly CompositePartSpec[], fit: ViewerFitMode = "wide"): Promise<void> {
    const generation = ++this.loadGeneration;

    const loaded = await Promise.all(
      parts.map(async (part) => ({
        role: part.role,
        geometry: await this.loadStlGeometry(part.url),
      })),
    );

    if (this.disposed || generation !== this.loadGeneration) {
      // A newer loadStl/loadComposite call superseded this one while parts were in flight —
      // bail before touching the scene so overlapping staged-view clicks can never mix parts.
      loaded.forEach((l) => l.geometry.dispose());
      return;
    }

    this.clearMesh();
    this.clearComposite();
    this.clearMarkers();
    // Same reasoning as loadStl: a part's feature markers cannot outlive that part's mesh.
    this.clearPartFeatureMarkers();
    // Only the in-progress stroke, not committed patches — see loadStl for why.
    this.clearBrush();

    const unionBox = new THREE.Box3();
    for (const { role, geometry } of loaded) {
      geometry.computeVertexNormals();
      geometry.computeBoundingBox();

      const material = new THREE.MeshLambertMaterial({ color: PALETTE[role], side: THREE.DoubleSide });
      const mesh = new THREE.Mesh(geometry, material);
      this.scene.add(mesh);
      this.compositeMeshes.push(mesh);
      this.compositeRoles.push(role);

      if (geometry.boundingBox) {
        unionBox.union(geometry.boundingBox);
      }

      // The doctor's scan/arch surface is the mark/brush raycast target — point meshObject at
      // it (first 'arch' part wins; a composite normally carries at most one) so mark-centre/
      // mark-rim/brush keep working inside a composite view instead of finding no mesh at all.
      // Composites with no 'arch' part (e.g. stage-3 "construction alone") leave meshObject
      // null, same as today — there is no scan surface to raycast against there.
      if (role === "arch" && this.meshObject === null) {
        this.meshObject = mesh;
        this.meshObjectIsCompositePart = true;
      }
    }

    // Anatomical presets stay available in composite views too (the arch part IS the scan);
    // composites without an arch (stage-3 construction alone) get none, same as part previews.
    this.anatomyFrame =
      this.meshObject !== null && this.meshObjectIsCompositePart
        ? this.computeFrameFromGeometry(this.meshObject.geometry)
        : null;
    this.frameOnBox3(unionBox, fit);
    if (this.anatomyFrame) {
      this.setAnatomyView("front");
    }
  }

  /** Roles present in the currently loaded composite (empty when a single loadStl mesh is shown instead). */
  getCompositeRoles(): PartRole[] {
    return [...this.compositeRoles];
  }

  private clearComposite(): void {
    for (const mesh of this.compositeMeshes) {
      this.scene.remove(mesh);
      mesh.geometry.dispose();
      const material = mesh.material;
      if (Array.isArray(material)) {
        material.forEach((m) => m.dispose());
      } else {
        material.dispose();
      }
    }
    this.compositeMeshes = [];
    this.compositeRoles = [];
    // A composite view has no single part to annotate — invalidate the derived frame with it.
    this.partFrame = null;
    this.partFrameComputed = false;
    // meshObject may be pointing at one of the meshes just disposed above (loadComposite sets
    // it to the composite's 'arch' part) — drop the reference so a stray raycast/clearMesh call
    // never touches an already-disposed mesh.
    if (this.meshObjectIsCompositePart) {
      this.meshObject = null;
      this.meshObjectIsCompositePart = false;
    }
  }

  private frameOnBoundingSphere(sphere: THREE.Sphere | null, fit: ViewerFitMode): void {
    if (!sphere) return;
    this.frameOnSphereParams(sphere.center, sphere.radius, fit);
  }

  private frameOnBox3(box: THREE.Box3, fit: ViewerFitMode): void {
    if (box.isEmpty()) return;
    const center = new THREE.Vector3();
    box.getCenter(center);
    const radius = box.getSize(new THREE.Vector3()).length() / 2;
    this.frameOnSphereParams(center, radius, fit);
  }

  private frameOnSphereParams(center: THREE.Vector3, radiusIn: number, fit: ViewerFitMode): void {
    const distance = fitDistanceMm(radiusIn, this.camera.fov, fitPaddingFor(fit));
    // remembered for the anatomical presets: same subject + distance, different direction
    this.lastFrameCenter = center.clone();
    this.lastFrameDistance = distance;
    this.lastFrameRadius = radiusIn;
    this.applyMarkerScale();

    this.controls.target.copy(center);
    const direction = new THREE.Vector3(0.4, 0.35, 1).normalize();
    this.camera.position.copy(center).addScaledVector(direction, distance);
    const clip = clipPlanesFor(distance);
    this.camera.near = clip.near;
    this.camera.far = clip.far;
    this.camera.updateProjectionMatrix();
    this.controls.update();
  }

  /** True when the current view has an anatomical frame (drives the preset buttons' UI). */
  hasAnatomyFrame(): boolean {
    return this.anatomyFrame !== null;
  }

  /**
   * True while the paint brush is armed. The other three pointer modes have had a getter since
   * they were written (isMarkModeActive / isRimPointsActive / isPointPickActive); the brush did
   * not, which left the veto hole exactly where the damage is invisible — a stroke interrupted by
   * a camera move ships its tail to /run as markedPoints, and individual brush points, unlike a
   * stray mark sphere, are never reviewable on screen.
   */
  isBrushActive(): boolean {
    return this.brushEnabled;
  }

  /** True while ANY pointer mode owns the next click on the scan — the routing veto. */
  isToolActive(): boolean {
    return anyPointerToolActive({
      brush: this.isBrushActive(),
      mark: this.isMarkModeActive(),
      rimPoints: this.isRimPointsActive(),
      pointPick: this.isPointPickActive(),
    });
  }

  /**
   * ROUTE THE STAGE TO A SITE (client, 2026-07-26: "Main panel needs to be positioned properly to
   * avoid the use to zoom in and find the cap").
   *
   * Measured before: the camera sat 240 mm from the arch centroid, showing 199 mm of jaw, so the
   * 6.16 mm cap was 3.1% of the view — 14 px on the live 444 px stage. Framing the site's own
   * neighbourhood makes it ~23%.
   *
   * Three things this deliberately does that a plain camera move would not:
   *
   *  1. It REFUSES while a pointer tool is armed. `controls.enabled = false` does not protect the
   *     camera — `animate` calls `controls.update()` every frame regardless and nothing gates the
   *     position writes — so this guard is the only thing standing between a route and a corrupted
   *     brush stroke or a mark placed along a ray the operator can no longer see. App checks the
   *     same condition; this is the backstop, because the cost of missing it is silent.
   *  2. It updates `lastFrameCenter`/`lastFrameDistance`, which are what the four anatomical
   *     presets reuse as "same subject, different direction". So after a route, Front/Left/Right/
   *     Top orbit the CAP instead of the whole arch — the presets get the fix for free, which is
   *     most of what "proper routing" means.
   *  3. It KEEPS THE CURRENT VIEW DIRECTION. Re-pointing is not re-orienting: an operator who has
   *     turned the jaw to look at the buccal side should arrive at the cap still looking at the
   *     buccal side. Only the fallback (no meaningful direction yet) uses the load-time angle.
   *
   * The move is EASED rather than snapped (client's choice) so the view reads as travelling to the
   * site — a teleport between two viewpoints costs the operator their bearings.
   *
   * Returns false when the route was refused, so the caller can tell "moved" from "declined".
   */
  focusOnSite(
    center: readonly [number, number, number],
    radiusMm: number,
    opts: { readonly animateMs?: number } = {},
  ): boolean {
    if (this.isToolActive()) return false;
    if (!Number.isFinite(center[0]) || !Number.isFinite(center[1]) || !Number.isFinite(center[2])) {
      return false;
    }
    // The same close-fit padding the part preview uses, applied to the site's neighbourhood
    // radius rather than to the cap alone — see SITE_FRAME_RADIUS_MM for why the neighbourhood
    // and not the cap.
    const distance = fitDistanceMm(radiusMm, this.camera.fov, SITE_FIT_PADDING);

    const target = new THREE.Vector3(center[0], center[1], center[2]);
    const current = this.camera.position.clone().sub(this.controls.target);
    const direction =
      current.lengthSq() > 1e-9
        ? current.normalize()
        : new THREE.Vector3(0.4, 0.35, 1).normalize();

    // The presets read these; setting them is what re-anchors the whole camera vocabulary on
    // the site rather than on the arch.
    this.lastFrameCenter = target.clone();
    this.lastFrameDistance = distance;
    this.lastFrameRadius = radiusMm;
    this.applyMarkerScale();

    const clip = clipPlanesFor(distance);
    this.camera.near = clip.near;
    this.camera.far = clip.far;
    this.camera.updateProjectionMatrix();

    this.startCameraTween(
      target,
      target.clone().addScaledVector(direction, distance),
      opts.animateMs ?? SITE_ROUTE_EASE_MS,
    );
    return true;
  }

  /**
   * Back out to everything currently loaded — the operator's way home from a site. Uses the wide
   * padding, so it restores the arch view the stage opens with.
   */
  frameLoadedContent(): boolean {
    if (this.isToolActive()) return false;
    const box = new THREE.Box3();
    if (this.meshObject) box.expandByObject(this.meshObject);
    for (const part of this.compositeMeshes) box.expandByObject(part);
    if (box.isEmpty()) return false;
    const center = new THREE.Vector3();
    box.getCenter(center);
    const radius = box.getSize(new THREE.Vector3()).length() / 2;

    const distance = fitDistanceMm(radius, this.camera.fov, fitPaddingFor("wide"));
    const current = this.camera.position.clone().sub(this.controls.target);
    const direction =
      current.lengthSq() > 1e-9 ? current.normalize() : new THREE.Vector3(0.4, 0.35, 1).normalize();

    this.lastFrameCenter = center.clone();
    this.lastFrameDistance = distance;
    this.lastFrameRadius = radius;
    this.applyMarkerScale();
    const clip = clipPlanesFor(distance);
    this.camera.near = clip.near;
    this.camera.far = clip.far;
    this.camera.updateProjectionMatrix();
    this.startCameraTween(center, center.clone().addScaledVector(direction, distance), SITE_ROUTE_EASE_MS);
    return true;
  }

  /**
   * Ease the camera from where it is to where it should be, driven by the existing render loop.
   * A new tween replaces any tween in flight (the operator changed their mind); ANY pointer-down
   * cancels it outright, because a camera still travelling under a click is the very thing the
   * veto above exists to prevent.
   */
  private startCameraTween(target: THREE.Vector3, position: THREE.Vector3, durationMs: number): void {
    // AN ANIMATION NOBODY CAN SEE IS JUST A SLOWER ASSIGNMENT. `requestAnimationFrame` — which
    // is the only thing that advances a tween — is paused while the document is hidden, so a
    // route fired in a background tab would otherwise leave the camera parked at its old pose
    // with a tween stuck at t=0. Snapping keeps the invariant that a route which returns true
    // has actually MOVED the camera, whether or not anyone was watching.
    if (typeof document !== "undefined" && document.visibilityState === "hidden") {
      durationMs = 0;
    }
    if (durationMs <= 0) {
      this.controls.target.copy(target);
      this.camera.position.copy(position);
      this.controls.update();
      this.cameraTween = null;
      return;
    }
    this.cameraTween = {
      fromTarget: this.controls.target.clone(),
      toTarget: target.clone(),
      fromPosition: this.camera.position.clone(),
      toPosition: position.clone(),
      startedAt: performance.now(),
      durationMs,
    };
  }

  /** Abandon an in-flight camera move, leaving the view wherever it had reached. */
  cancelCameraTween(): void {
    this.cameraTween = null;
  }

  /** One frame of the eased move. Smoothstep: no abrupt start or stop to read as a glitch. */
  private stepCameraTween(now: number): void {
    const tween = this.cameraTween;
    if (!tween) return;
    const raw = Math.min(Math.max((now - tween.startedAt) / tween.durationMs, 0), 1);
    const t = raw * raw * (3 - 2 * raw);
    this.controls.target.lerpVectors(tween.fromTarget, tween.toTarget, t);
    this.camera.position.lerpVectors(tween.fromPosition, tween.toPosition, t);
    if (raw >= 1) this.cameraTween = null;
  }

  /**
   * Move the camera to a named anatomical view of the current arch (no-op when the current
   * content has no anatomical frame — part previews, construction-alone composites). Keeps
   * the framing distance/target from the most recent load; only the direction and the
   * camera's up axis change. "front" faces the anterior teeth from slightly above the
   * occlusal plane (the safe rim-clicking view); "left"/"right" are screen-relative to that
   * front view; "occlusal" looks straight down at the crowns with the anterior at the top of
   * the screen.
   */
  /**
   * Which way the crowns hang, from the case's own jaw (client 2026-08-09). "upper" rolls
   * the anatomical presets so the teeth point DOWN, as they do in the patient; "lower" and
   * an unknown jaw keep the standing crowns-up roll. Re-applies immediately when a preset
   * is already showing, so changing the jaw at Intake turns the scan the right way up
   * without a reload. Presentation only — no geometry moves.
   */
  setJaw(jaw: string | null | undefined): void {
    const crownsDown = jaw === "upper";
    if (crownsDown === this.crownsDown) return;
    this.crownsDown = crownsDown;
    if (this.anatomyFrame && this.lastAnatomyView) this.setAnatomyView(this.lastAnatomyView);
  }

  setAnatomyView(view: AnatomyViewId): void {
    this.lastAnatomyView = view;
    const frame = this.anatomyFrame;
    const center = this.lastFrameCenter;
    if (!frame || !center || this.lastFrameDistance <= 0) return;

    // The direction/up math lives in anatomyViewOrientation (extracted, verbatim — see the
    // pure-rules block above); what stays here is the camera/controls application.
    const { direction, up } = anatomyViewOrientation(frame, view, {
      crownsDown: this.crownsDown,
    });
    this.setCameraUp(new THREE.Vector3(up[0], up[1], up[2]));
    this.camera.position
      .copy(center)
      .addScaledVector(new THREE.Vector3(direction[0], direction[1], direction[2]), this.lastFrameDistance);
    this.controls.target.copy(center);
    this.controls.update();
  }

  /**
   * Change the camera's up axis AND re-sync OrbitControls' internal up-quaternion.
   * OrbitControls captures `camera.up` ONCE at construction (`_quat = setFromUnitVectors(
   * object.up, +y)`, three 0.185 OrbitControls.js:406) and runs all of its spherical drag
   * math in that frozen y-is-up frame — so changing `camera.up` alone (as the anatomical
   * presets must, e.g. to a near−z occlusal axis on the upper scans) leaves drags computed
   * in the wrong frame: horizontal drags tumble and roll the model, reported by the client
   * as "the camera is super sensitive and moves the scan". `_quat`/`_quatInverse` are
   * underscore-private but stable in three 0.185's class-based OrbitControls; accessed via
   * a narrow structural cast, with a defensive existence check so a future three upgrade
   * that renames them degrades to the old (mis-framed but functional) behavior instead of
   * throwing mid-interaction.
   */
  private setCameraUp(up: THREE.Vector3): void {
    this.camera.up.copy(up);
    const internals = this.controls as unknown as {
      _quat?: THREE.Quaternion;
      _quatInverse?: THREE.Quaternion;
    };
    if (internals._quat && internals._quatInverse) {
      internals._quat.setFromUnitVectors(up, new THREE.Vector3(0, 1, 0));
      internals._quatInverse.copy(internals._quat).invert();
    }
  }

  // --- Brush tool -----------------------------------------------------

  /**
   * Enable paint mode for a NEW stroke: disables orbit controls, clears the live stroke
   * buffer (previously committed patches for OTHER rows are untouched), and starts capturing
   * on the loaded scan mesh.
   */
  enableBrush(): void {
    if (this.brushEnabled) return;
    // Brush, single-shot mark mode, multi-click rim-points, and the one-shot point pick are
    // all mutually exclusive — each single-purposes pointerdown on the mesh differently.
    this.exitMarkMode();
    this.exitPointPick();
    if (this.rimPointsRowIndex !== null) {
      this.cancelRimPoints();
    }
    this.brushEnabled = true;
    this.liveStroke.length = 0;
    this.updateLiveStrokeObject();
    this.controls.enabled = false;
    this.renderer.domElement.style.cursor = "crosshair";
  }

  /** Disable paint mode and restore orbit controls. The live stroke (and any committed patches) are kept. */
  disableBrush(): void {
    this.brushEnabled = false;
    this.brushPainting = false;
    this.controls.enabled = true;
    this.renderer.domElement.style.cursor = "";
    // Re-sync LEFT to whatever Shift's current state is — it may have changed while the
    // brush (which ignores the mapping entirely) was active.
    this.controls.mouseButtons.LEFT = this.shiftPanActive ? THREE.MOUSE.PAN : THREE.MOUSE.ROTATE;
  }

  /** The current in-progress stroke ONLY (never includes other rows' committed patches). */
  getBrushPatch(): number[][] {
    return this.liveStroke.map((p) => [p.x, p.y, p.z]);
  }

  /** Discard the in-progress stroke and its glow. Committed patches for other rows are untouched. */
  clearBrush(): void {
    this.liveStroke.length = 0;
    this.updateLiveStrokeObject();
  }

  /**
   * Accept the live stroke as row `rowIndex`'s patch: move it into its own committed Points
   * object (replacing any previous commit for that row) and clear the live stroke buffer.
   */
  commitBrushPatch(rowIndex: number): void {
    this.disposeCommittedPatch(rowIndex);
    if (this.liveStroke.length > 0) {
      const points = this.buildPointsObject(this.liveStroke);
      this.scene.add(points);
      this.committedPatches.set(rowIndex, points);
    }
    this.liveStroke.length = 0;
    this.updateLiveStrokeObject();
  }

  /** Discard row `rowIndex`'s committed patch and its glow only — other rows are untouched. */
  clearCommittedPatch(rowIndex: number): void {
    this.disposeCommittedPatch(rowIndex);
  }

  /** Discard the live stroke and every row's committed patch (e.g. on case switch). */
  clearAllBrushPatches(): void {
    this.liveStroke.length = 0;
    this.updateLiveStrokeObject();
    for (const rowIndex of [...this.committedPatches.keys()]) {
      this.disposeCommittedPatch(rowIndex);
    }
  }

  private disposeCommittedPatch(rowIndex: number): void {
    const existing = this.committedPatches.get(rowIndex);
    if (!existing) return;
    this.scene.remove(existing);
    existing.geometry.dispose();
    (existing.material as THREE.Material).dispose();
    this.committedPatches.delete(rowIndex);
  }

  // --- Precise center/rim marks -----------------------------------------

  /**
   * Arm the NEXT pointerdown on the loaded scan mesh to resolve one world point and
   * place/replace row `rowIndex`'s `kind` marker sphere, call `onPlaced` with that point (so
   * React can update ConfirmedSite.centerMark/rimMark), then auto-exit mark mode. Disables
   * orbit controls (crosshair cursor) exactly like the brush, and is mutually exclusive with it
   * and with multi-click rim-points.
   */
  enterMarkMode(rowIndex: number, kind: MarkKind, onPlaced: (point: [number, number, number]) => void): void {
    // Marking, brushing, rim-points collection, and the one-shot point pick are all
    // mutually exclusive — starting one exits the others.
    if (this.brushEnabled) {
      this.disableBrush();
    }
    this.exitPointPick();
    if (this.rimPointsRowIndex !== null) {
      this.cancelRimPoints();
    }
    this.markMode = { rowIndex, kind, onPlaced };
    this.controls.enabled = false;
    this.renderer.domElement.style.cursor = "crosshair";
  }

  /** Cancel mark mode without placing a marker (e.g. the row/case changed underneath it). */
  exitMarkMode(): void {
    if (this.markMode === null) return;
    this.markMode = null;
    this.controls.enabled = true;
    this.renderer.domElement.style.cursor = "";
    this.controls.mouseButtons.LEFT = this.shiftPanActive ? THREE.MOUSE.PAN : THREE.MOUSE.ROTATE;
  }

  /** True while a single-shot mark click is armed (drives the crosshair/banner UI). */
  isMarkModeActive(): boolean {
    return this.markMode !== null;
  }

  // --- One-shot point pick (align-to-mark trench click) -----------------

  /**
   * Arm the NEXT pointerdown on the loaded scan mesh to resolve one plain on-surface world
   * point, call `onPicked` with it, and auto-exit — the ⊕/◐ picking mechanics (crosshair,
   * orbit disabled, raycast against the scan only) WITHOUT placing any marker sphere: the
   * picked point is a transient input (the align-to-mark POST), not a committed site mark.
   * Mutually exclusive with the brush, single-shot mark mode, and rim-points collection.
   */
  enterPointPick(
    onPicked: (point: [number, number, number]) => void,
    onMissed?: () => void,
  ): void {
    if (this.brushEnabled) {
      this.disableBrush();
    }
    this.exitMarkMode();
    if (this.rimPointsRowIndex !== null) {
      this.cancelRimPoints();
    }
    this.pointPick = { onPicked, onMissed };
    this.controls.enabled = false;
    this.renderer.domElement.style.cursor = "crosshair";
  }

  /** Cancel the armed point pick without resolving a point (Escape / case switch). */
  exitPointPick(): void {
    if (this.pointPick === null) return;
    this.pointPick = null;
    this.controls.enabled = true;
    this.renderer.domElement.style.cursor = "";
    this.controls.mouseButtons.LEFT = this.shiftPanActive ? THREE.MOUSE.PAN : THREE.MOUSE.ROTATE;
  }

  /** True while a one-shot point pick is armed (drives the banner/crosshair UI). */
  isPointPickActive(): boolean {
    return this.pointPick !== null;
  }

  /**
   * Place row `rowIndex`'s `kind` marker at a known world point — used for prefill
   * (suggested_sites' center_mark/rim_mark) and for the translated-rim placement in the
   * centre-translate flow. RIM markers are genuinely on-surface points (a rim border click, or
   * the legacy rim_mark), so the RENDERED sphere is snapped to the nearest mesh vertex before
   * placing — the backend-computed point may sit slightly off-surface and this keeps it visually
   * anchored to the scan. CENTRE markers are shown RAW, no snap: the centre is an INDICATOR over
   * a screw-recess hole the scanner never captured, not a surface point — nearest-vertex would
   * grab the hole's edge and visually shift a curated top-centre mark off-centre (curated centre
   * marks are already placed at the intended eye-judged height by construction). In both cases
   * the point passed in here is never mutated or returned anywhere — callers keep shipping the
   * original value to the API (what the sphere displays IS what's sent — see App.tsx).
   */
  setSiteMarker(rowIndex: number, kind: MarkKind, point: readonly [number, number, number]): void {
    const raw = new THREE.Vector3(point[0], point[1], point[2]);
    const resolved = kind === "rim" ? this.snapToMeshSurface(raw) : raw;
    this.placeSiteMarker(rowIndex, kind, resolved);
  }

  /**
   * Nearest point on the loaded scan mesh to `point` — the mesh's VERTEX closest to `point` in
   * world space (a plain scan over the BufferGeometry position attribute; 100-160k verts is
   * sub-ms, no BVH needed). Falls back to the raw `point` unchanged when no mesh is loaded, or
   * when the nearest vertex is farther than SNAP_MAX_DISTANCE_MM away (a genuinely off-surface
   * mark should show where it actually is, not teleport to an unrelated part of the mesh).
   *
   * Replaces an earlier world-Z raycast strategy (cast straight up/down through point's x/y,
   * take the nearest hit): on a scan whose occlusal direction is tilted or flipped relative to
   * world Z, that vertical ray can pass through the ridge and hit the wall BEHIND the actual
   * mark — several mm off, reading as gross misalignment to the doctor even though the STORED
   * mark (and everything sent to the backend) was correct all along. Nearest-vertex has no
   * preferred direction, so it isn't fooled by the scan's orientation.
   */
  private snapToMeshSurface(point: THREE.Vector3): THREE.Vector3 {
    const mesh = this.meshObject;
    if (!mesh) return point;

    const geometry = mesh.geometry;
    const positionAttr = geometry.getAttribute("position") as THREE.BufferAttribute | undefined;
    if (!positionAttr) return point;

    const isIdentityTransform = mesh.matrixWorld.equals(IDENTITY_MATRIX4);
    const vertex = new THREE.Vector3();
    let bestDistSq = Infinity;
    let bestX = point.x;
    let bestY = point.y;
    let bestZ = point.z;

    const array = positionAttr.array;
    for (let i = 0; i < positionAttr.count; i += 1) {
      const base = i * 3;
      let x = array[base] as number;
      let y = array[base + 1] as number;
      let z = array[base + 2] as number;
      if (!isIdentityTransform) {
        vertex.set(x, y, z).applyMatrix4(mesh.matrixWorld);
        x = vertex.x;
        y = vertex.y;
        z = vertex.z;
      }
      const dx = x - point.x;
      const dy = y - point.y;
      const dz = z - point.z;
      const distSq = dx * dx + dy * dy + dz * dz;
      if (distSq < bestDistSq) {
        bestDistSq = distSq;
        bestX = x;
        bestY = y;
        bestZ = z;
      }
    }

    if (bestDistSq > SNAP_MAX_DISTANCE_MM * SNAP_MAX_DISTANCE_MM) {
      return point;
    }
    return new THREE.Vector3(bestX, bestY, bestZ);
  }

  /** Discard row `rowIndex`'s `kind` marker only — other rows/kinds are untouched. */
  clearSiteMarker(rowIndex: number, kind: MarkKind): void {
    const entry = this.siteMarkers.get(rowIndex);
    if (!entry) return;
    const existing = entry[kind];
    if (!existing) return;
    this.scene.remove(existing);
    existing.geometry.dispose();
    (existing.material as THREE.Material).dispose();
    delete entry[kind];
    if (entry.center === undefined && entry.rim === undefined) {
      this.siteMarkers.delete(rowIndex);
    }
  }

  /** Discard every row's center/rim markers (e.g. on case switch). */
  clearAllSiteMarkers(): void {
    for (const rowIndex of [...this.siteMarkers.keys()]) {
      this.clearSiteMarker(rowIndex, "center");
      this.clearSiteMarker(rowIndex, "rim");
    }
  }

  private placeSiteMarker(rowIndex: number, kind: MarkKind, point: THREE.Vector3): void {
    this.clearSiteMarker(rowIndex, kind);

    const color = kind === "center" ? MARK_CENTER_COLOR : MARK_RIM_COLOR;
    const emissive = kind === "center" ? MARK_CENTER_EMISSIVE : MARK_RIM_EMISSIVE;
    const geometry = new THREE.SphereGeometry(MARK_SPHERE_RADIUS_MM, 20, 16);
    const material = new THREE.MeshStandardMaterial({
      color,
      emissive,
      emissiveIntensity: 0.9,
      roughness: 0.3,
    });
    const sphere = new THREE.Mesh(geometry, material);
    sphere.position.copy(point);
    makeIndicatorVisible(material, sphere);
    this.scene.add(sphere);

    const entry = this.siteMarkers.get(rowIndex) ?? {};
    entry[kind] = sphere;
    this.siteMarkers.set(rowIndex, entry);
  }

  // --- Multi-click rim-BORDER points -----------------------------------

  /**
   * Arm EVERY subsequent pointerdown (stays armed, unlike enterMarkMode's single-shot) to
   * raycast-place one small blue rim-point sphere on row `rowIndex` and remain armed for the
   * next click — the doctor clicks several points around the cap's visible border, each placed
   * immediately for visual feedback. Starts a FRESH session: any previous in-progress (not yet
   * "Done") clicks for another row are discarded (mirrors enableBrush's fresh-liveStroke
   * behavior); a row's previously COMMITTED rim points are untouched until this session finishes.
   * Mutually exclusive with the brush and single-shot mark mode — both are exited first.
   */
  enableRimPoints(rowIndex: number): void {
    if (this.brushEnabled) {
      this.disableBrush();
    }
    this.exitMarkMode();
    this.exitPointPick();
    this.discardLiveRimPoints();
    this.rimPointsRowIndex = rowIndex;
    this.controls.enabled = false;
    this.renderer.domElement.style.cursor = "crosshair";
  }

  /**
   * Exit rim-points collection WITHOUT committing — the Cancel/Escape path. This session's
   * clicks (and their spheres) are discarded; the row's previously committed rim points (from an
   * earlier finished session) are untouched, same as clearBrush leaving committed patches alone.
   */
  cancelRimPoints(): void {
    this.discardLiveRimPoints();
    this.rimPointsRowIndex = null;
    this.controls.enabled = true;
    this.renderer.domElement.style.cursor = "";
    this.controls.mouseButtons.LEFT = this.shiftPanActive ? THREE.MOUSE.PAN : THREE.MOUSE.ROTATE;
  }

  /** True while a multi-click rim-points session is armed (drives the banner/crosshair UI). */
  isRimPointsActive(): boolean {
    return this.rimPointsRowIndex !== null;
  }

  /** The row currently collecting rim points, or null when not armed. */
  activeRimPointsRow(): number | null {
    return this.rimPointsRowIndex;
  }

  /** This session's in-progress rim-point clicks ONLY (never includes other rows' committed points). */
  getRimPointsPatch(): number[][] {
    return this.liveRimPoints.map((p) => [p.x, p.y, p.z]);
  }

  /**
   * Finish the session: commit this session's clicks as row `rowIndex`'s rim points, REPLACING
   * any previously committed rim points for that row wholesale (never appends across sessions —
   * matches how centerMark/rimMark are replaced on every re-placement). Exits rim-points mode
   * and restores orbit controls. A session with zero clicks still "finishes" (clears any prior
   * committed points for the row) — callers that want to preserve an empty session untouched
   * should call cancelRimPoints() instead.
   *
   * `legacyRimMark`, when given, is the row's CURRENT legacy single rim mark (if any exists in
   * state) — passing it lets this method enforce the legacy-sphere-visibility invariant itself
   * (see applyRimVisibilityInvariant) instead of leaving the caller to remember to call a
   * separate sync step after every finish. Callers that never touch legacy rim marks can omit it.
   */
  finishRimPoints(rowIndex: number, legacyRimMark?: readonly [number, number, number]): void {
    this.clearRimPointSpheres(rowIndex);
    if (this.liveRimPoints.length > 0) {
      const spheres = this.liveRimPointSpheres.splice(0, this.liveRimPointSpheres.length);
      this.committedRimPoints.set(rowIndex, spheres);
    }
    this.liveRimPoints.length = 0;
    this.rimPointsRowIndex = null;
    this.controls.enabled = true;
    this.renderer.domElement.style.cursor = "";
    this.controls.mouseButtons.LEFT = this.shiftPanActive ? THREE.MOUSE.PAN : THREE.MOUSE.ROTATE;
    this.applyRimVisibilityInvariant(rowIndex, legacyRimMark);
  }

  /**
   * Discard row `rowIndex`'s COMMITTED rim points and their spheres only — other rows/the live
   * session are untouched. `legacyRimMark`, when given, is the row's CURRENT legacy rim mark (if
   * any) — passing it re-applies the visibility invariant (see applyRimVisibilityInvariant) so
   * clearing rim points (e.g. the "N pts" chip's X) correctly re-shows a surviving legacy sphere.
   * Omit it for callers that intend to clear the legacy mark too (e.g. the combined "clear rim"
   * action, which calls clearSiteMarker itself right alongside this).
   */
  clearRimPoints(rowIndex: number, legacyRimMark?: readonly [number, number, number]): void {
    this.clearRimPointSpheres(rowIndex);
    if (legacyRimMark !== undefined) {
      this.applyRimVisibilityInvariant(rowIndex, legacyRimMark);
    }
  }

  private clearRimPointSpheres(rowIndex: number): void {
    const existing = this.committedRimPoints.get(rowIndex);
    if (!existing) return;
    for (const sphere of existing) {
      this.disposeRimPointSphere(sphere);
    }
    this.committedRimPoints.delete(rowIndex);
  }

  /** Discard every row's committed rim points (e.g. on case switch), plus any in-progress session. */
  clearAllRimPoints(): void {
    this.discardLiveRimPoints();
    this.rimPointsRowIndex = null;
    for (const rowIndex of [...this.committedRimPoints.keys()]) {
      this.clearRimPointSpheres(rowIndex);
    }
  }

  /**
   * THE single source of truth for whether row `rowIndex`'s LEGACY rim sphere (blue) should be
   * visible: never at the same time as that row's committed rim-BORDER points (teal dots) — a
   * client screenshot showed the two were indistinguishable on screen, and once rimPoints exists
   * the legacy sphere is actively misleading (the mapper doesn't even send rim_mark once
   * rimPoints is non-empty — see App.tsx's toWireRunSiteInput usage). Centralized here (not left
   * to callers to remember) precisely because there were multiple call sites that could each
   * independently forget to re-apply this after touching rimPoints — see finishRimPoints/
   * clearRimPoints above, both of which route through this rather than leaving App.tsx to orchestrate
   * clearSiteMarker/setSiteMarker calls by hand.
   */
  private applyRimVisibilityInvariant(rowIndex: number, legacyRimMark: readonly [number, number, number] | undefined): void {
    const hasRimPoints = (this.committedRimPoints.get(rowIndex)?.length ?? 0) > 0;
    if (hasRimPoints) {
      this.clearSiteMarker(rowIndex, "rim");
    } else if (legacyRimMark !== undefined) {
      this.setSiteMarker(rowIndex, "rim", legacyRimMark);
    } else {
      this.clearSiteMarker(rowIndex, "rim");
    }
  }

  // --- Post-run seated-pose axis triads (RealGUIDE-style) ---------------

  /**
   * Draw (or replace) tooth `tooth`'s seated-pose axis triad: three ~TRIAD_AXIS_LENGTH_MM line
   * segments originating at `spec.position`, one per pose-matrix rotation column (red=x,
   * green=y, blue=z — see the TRIAD_AXIS_COLOR_* docs). Marks WHERE and WHICH WAY the automation
   * actually seated the part, independent of which STL view is currently loaded (scan or any
   * composite) — same survive-view-changes-until-explicit-clear behavior as siteMarkers/
   * committedRimPoints (see loadStl/loadComposite's docs), disposed only by clearAllPoseTriads
   * (case switch) or a later setPoseTriad call for the SAME tooth (replaces, not appends).
   */
  setPoseTriad(tooth: number, spec: PoseTriadSpec): void {
    this.clearPoseTriad(tooth);

    const group = new THREE.Group();
    const origin = new THREE.Vector3(spec.position[0], spec.position[1], spec.position[2]);
    const axes: readonly [readonly [number, number, number], number][] = [
      [spec.axisX, TRIAD_AXIS_COLOR_X],
      [spec.axisY, TRIAD_AXIS_COLOR_Y],
      [spec.axisZ, TRIAD_AXIS_COLOR_Z],
    ];
    for (const [axis, color] of axes) {
      const direction = new THREE.Vector3(axis[0], axis[1], axis[2]);
      // pose_matrix columns are already unit-length rotation-matrix columns, but normalize
      // defensively — a malformed/legacy record with a non-unit column must not silently draw a
      // mis-scaled triad.
      if (direction.lengthSq() > 0) {
        direction.normalize();
      }
      const endpoint = origin.clone().addScaledVector(direction, TRIAD_AXIS_LENGTH_MM);
      const geometry = new THREE.BufferGeometry().setFromPoints([origin, endpoint]);
      const material = new THREE.LineBasicMaterial({ color });
      const line = new THREE.Line(geometry, material);
      // The triad marks a pose INSIDE the arch — same render-through-geometry indicator
      // convention as every other marker kind (see MARKER_RENDER_ORDER's doc).
      makeIndicatorVisible(material, line);
      group.add(line);
    }

    this.scene.add(group);
    this.poseTriads.set(tooth, group);
  }

  /** Discard tooth `tooth`'s axis triad only — other teeth are untouched. */
  clearPoseTriad(tooth: number): void {
    const existing = this.poseTriads.get(tooth);
    if (!existing) return;
    this.disposeTriadGroup(existing);
    this.poseTriads.delete(tooth);
  }

  /** Discard every tooth's axis triad (e.g. on case switch). */
  clearAllPoseTriads(): void {
    for (const tooth of [...this.poseTriads.keys()]) {
      this.clearPoseTriad(tooth);
    }
  }

  private disposeTriadGroup(group: THREE.Group): void {
    this.scene.remove(group);
    for (const child of group.children) {
      if (child instanceof THREE.Line) {
        child.geometry.dispose();
        (child.material as THREE.Material).dispose();
      }
    }
  }

  // --- MARKED FEATURES: the library part's marks, and their scan counterparts ----------

  /**
   * The previewed part's canonical frame, or null when the current content has none (the
   * scan, a composite) or when its rim ring could not be fitted well enough to justify one
   * (see partFrame.ts's RING_FIT_MAX_RMS_MM). Callers MUST treat null as "this part cannot be
   * annotated here" — the alternative is drawing a landmark somewhere plausible but wrong,
   * which on this flow means a mis-clocked part on every future case that ships it.
   *
   * Computed once per loaded mesh and memoized (a scan is ~150k vertices and the reduction is
   * O(n) twice): `partFrameComputed` distinguishes "not tried yet" from "tried, no frame".
   */
  getPartFrame(): PartFrame | null {
    if (this.partFrameComputed) return this.partFrame;
    this.partFrameComputed = true;
    this.partFrame = null;
    const mesh = this.meshObject;
    // A composite is never a single part to annotate — only the standalone preview mesh is.
    if (!mesh || this.meshObjectIsCompositePart) return null;
    const position = mesh.geometry.getAttribute("position") as THREE.BufferAttribute | undefined;
    if (!position) return null;
    this.partFrame = computePartFrame(position.array as ArrayLike<number>);
    return this.partFrame;
  }

  /**
   * Draw (replacing wholesale) the marked features of the currently previewed LIBRARY PART.
   * Returns the number of markers drawn — 0 when the part has no derivable frame, which the
   * caller surfaces as "the marks cannot be located on this mesh" rather than silently showing
   * an empty part. Selection is a SIZE difference, never a color one (the color is the kind).
   */
  setPartFeatureMarkers(specs: readonly PartFeatureMarkerSpec[]): number {
    this.clearPartFeatureMarkers();
    const frame = this.getPartFrame();
    if (frame === null) return 0;
    for (const spec of specs) {
      const [x, y, z] = rawFromFeature(frame, spec);
      const sphere = this.buildFeatureSphere(spec.kind, featureMarkerRadiusMm(spec.selected));
      sphere.position.set(x, y, z);
      this.scene.add(sphere);
      this.partFeatureMarkers.set(spec.key, sphere);
    }
    return this.partFeatureMarkers.size;
  }

  /** Remove every part-feature marker (also called whenever the shown mesh is replaced). */
  clearPartFeatureMarkers(): void {
    for (const sphere of this.partFeatureMarkers.values()) {
      this.disposeMarkerSphere(sphere);
    }
    this.partFeatureMarkers.clear();
  }

  /**
   * Place (or MOVE — one feature, one place) the operator's scan mark for `featureId`, in the
   * same color the part's marker carries for that kind, so a pair reads as one thing across
   * the two views. Plain world point: a correspondence click genuinely IS a surface point.
   */
  setCorrespondenceMark(featureId: string, kind: FeatureKind, point: readonly [number, number, number]): void {
    this.clearCorrespondenceMark(featureId);
    const sphere = this.buildFeatureSphere(kind, FEATURE_MARKER_RADIUS_MM);
    sphere.position.set(point[0], point[1], point[2]);
    this.scene.add(sphere);
    this.correspondenceMarks.set(featureId, sphere);
  }

  /** Discard one feature's scan mark only — other pairs are untouched. */
  clearCorrespondenceMark(featureId: string): void {
    const existing = this.correspondenceMarks.get(featureId);
    if (!existing) return;
    this.disposeMarkerSphere(existing);
    this.correspondenceMarks.delete(featureId);
  }

  /** Discard every scan-side correspondence mark (pair list cleared, applied, case switch). */
  clearAllCorrespondenceMarks(): void {
    for (const featureId of [...this.correspondenceMarks.keys()]) {
      this.clearCorrespondenceMark(featureId);
    }
  }

  private buildFeatureSphere(kind: FeatureKind, radiusMm: number): THREE.Mesh {
    const color = FEATURE_COLOR[kind];
    const geometry = new THREE.SphereGeometry(radiusMm, 18, 14);
    const material = new THREE.MeshStandardMaterial({
      color,
      // Darkened own-hue emissive, so every kind glows in its own color without a second
      // hand-picked constant per kind (the centre/rim marks predate this and keep their pairs).
      emissive: new THREE.Color(color).multiplyScalar(FEATURE_MARKER_EMISSIVE_SCALE),
      emissiveIntensity: 0.9,
      roughness: 0.3,
    });
    const sphere = new THREE.Mesh(geometry, material);
    // Same render-through-geometry indicator convention as every other marker kind — a coded
    // trench sits in a recess the mesh itself would otherwise occlude from most angles.
    makeIndicatorVisible(material, sphere);
    return sphere;
  }

  private disposeMarkerSphere(sphere: THREE.Mesh): void {
    this.scene.remove(sphere);
    sphere.geometry.dispose();
    (sphere.material as THREE.Material).dispose();
  }

  /** Discard this session's in-progress clicks and their spheres (used by both a fresh enableRimPoints and cancelRimPoints). */
  private discardLiveRimPoints(): void {
    for (const sphere of this.liveRimPointSpheres) {
      this.disposeRimPointSphere(sphere);
    }
    this.liveRimPointSpheres.length = 0;
    this.liveRimPoints.length = 0;
  }

  private disposeRimPointSphere(sphere: THREE.Mesh): void {
    this.scene.remove(sphere);
    sphere.geometry.dispose();
    (sphere.material as THREE.Material).dispose();
  }

  private placeRimPointSphere(point: THREE.Vector3): THREE.Mesh {
    const geometry = new THREE.SphereGeometry(RIM_POINT_SPHERE_RADIUS_MM, 16, 12);
    const material = new THREE.MeshStandardMaterial({
      color: RIM_POINT_COLOR,
      emissive: RIM_POINT_EMISSIVE,
      emissiveIntensity: 0.9,
      roughness: 0.3,
    });
    const sphere = new THREE.Mesh(geometry, material);
    sphere.position.copy(point);
    makeIndicatorVisible(material, sphere);
    this.scene.add(sphere);
    return sphere;
  }

  private readonly handleRimPointsPointerDown = (event: PointerEvent): void => {
    if (this.rimPointsRowIndex === null || !this.meshObject) return;
    // Placement clicks are raycast hits on the loaded scan mesh — on-surface by construction,
    // no snap-to-surface needed (unlike setSiteMarker's cosmetic snap for backend-computed points).
    const point = this.raycastClientPoint(event.clientX, event.clientY);
    if (!point) return;
    this.liveRimPoints.push(point);
    this.liveRimPointSpheres.push(this.placeRimPointSphere(point));
  };

  private readonly handleMarkPointerDown = (event: PointerEvent): void => {
    if (this.markMode === null || !this.meshObject) return;
    const { kind } = this.markMode;
    // CENTRE clicks resolve to the corridor-p10 placement (the cap's centre is a screw-recess
    // hole — see resolveCenterPlacement's doc); RIM clicks (legacy single-shot path) are a plain
    // on-surface raycast hit, since a rim border point genuinely IS a surface point.
    const point = kind === "center" ? this.resolveCenterPlacement(event.clientX, event.clientY) : this.raycastClientPoint(event.clientX, event.clientY);
    if (!point) return;
    const { rowIndex, onPlaced } = this.markMode;
    this.placeSiteMarker(rowIndex, kind, point);
    this.exitMarkMode();
    onPlaced([point.x, point.y, point.z]);
  };

  private readonly handlePointPickPointerDown = (event: PointerEvent): void => {
    if (this.pointPick === null || !this.meshObject) return;
    // A plain on-surface raycast hit — the picked trench point genuinely IS a surface
    // point (unlike the centre mark's recess-hole corridor placement).
    const point = this.raycastClientPoint(event.clientX, event.clientY);
    if (!point) {
      // A click on the SKY is an attempt, not a resolution: stay armed — the
      // operator is mid-act — and tell the caller, so the surface can say it out
      // loud. Until 2026-08-01 this returned silently: armed, orbit controls
      // disabled, no message — the whole stage read as dead, which is exactly how
      // the client reported it ("buttons are not working").
      this.pointPick.onMissed?.();
      return;
    }
    const { onPicked } = this.pointPick;
    this.exitPointPick();
    onPicked([point.x, point.y, point.z]);
  };

  private readonly handleBrushPointerDown = (event: PointerEvent): void => {
    if (!this.brushEnabled || !this.meshObject) return;
    this.brushPainting = true;
    this.paintAtClientPoint(event.clientX, event.clientY);
  };

  private readonly handleBrushPointerMove = (event: PointerEvent): void => {
    if (!this.brushEnabled || !this.brushPainting || !this.meshObject) return;
    const now = performance.now();
    if (now - this.brushLastMoveAt < BRUSH_MOVE_THROTTLE_MS) return;
    this.brushLastMoveAt = now;
    this.paintAtClientPoint(event.clientX, event.clientY);
  };

  private readonly handleBrushPointerUp = (): void => {
    this.brushPainting = false;
  };

  // --- Shift+left-drag pan --------------------------------------------

  private readonly handleShiftPanKeyDown = (event: KeyboardEvent): void => {
    if (event.key !== "Shift" || this.shiftPanActive) return;
    this.shiftPanActive = true;
    // While the brush is active, OrbitControls is deliberately disabled (see enableBrush) —
    // remapping LEFT to PAN here must not resurrect rotate/pan behavior underneath the brush.
    if (this.brushEnabled) return;
    this.controls.mouseButtons.LEFT = THREE.MOUSE.PAN;
  };

  private readonly handleShiftPanKeyUp = (event: KeyboardEvent): void => {
    if (event.key !== "Shift") return;
    this.restoreLeftMouseButton();
  };

  private readonly handleShiftPanWindowBlur = (): void => {
    // A window/tab switch while Shift is held never fires keyup — always restore on blur.
    this.restoreLeftMouseButton();
  };

  private restoreLeftMouseButton(): void {
    this.shiftPanActive = false;
    this.controls.mouseButtons.LEFT = THREE.MOUSE.ROTATE;
  }

  private paintAtClientPoint(clientX: number, clientY: number): void {
    const point = this.raycastClientPoint(clientX, clientY);
    if (!point) return;
    this.liveStroke.push(point);
    this.updateLiveStrokeObject();
  }

  /**
   * Raycast a client (screen) point against the loaded scan mesh ONLY, returning the world-
   * space hit point — shared by the brush and the single-shot rim mark tool (and the legacy
   * "rim" kind of enterMarkMode) so both resolve points in exactly the same coordinate frame.
   * The single-shot CENTRE placement does NOT use this directly — see resolveCenterPlacement,
   * which needs the ray itself (not just its first hit) for the corridor scan.
   */
  private raycastClientPoint(clientX: number, clientY: number): THREE.Vector3 | null {
    const hit = this.raycastClientHit(clientX, clientY);
    return hit ? hit.point.clone() : null;
  }

  /**
   * Sets this.raycaster from a client (screen) point and intersects the loaded scan mesh,
   * returning the first hit (or null off-mesh/no-mesh). this.raycaster.ray is valid after this
   * call regardless of whether a hit was found — callers that need the ray itself even on a
   * miss (there are none today; every mark tool requires an on-mesh hit to arm at all) can read
   * it directly after calling this.
   */
  private raycastClientHit(clientX: number, clientY: number): THREE.Intersection | null {
    const mesh = this.meshObject;
    if (!mesh) return null;
    const rect = this.renderer.domElement.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return null;
    this.pointerNdc.x = ((clientX - rect.left) / rect.width) * 2 - 1;
    this.pointerNdc.y = -((clientY - rect.top) / rect.height) * 2 + 1;

    this.raycaster.setFromCamera(this.pointerNdc, this.camera);
    const hits = this.raycaster.intersectObject(mesh, false);
    return hits[0] ?? null;
  }

  /**
   * Resolve where the CENTRE marker should be placed for a click at (clientX, clientY). The
   * cap's centre is a screw-recess HOLE — the scanner cannot capture it (detection finds caps BY
   * that void) — so the raw raycast hit P through the hole lands on whatever is behind it (the
   * recess bottom / inner wall — P sits in the click's LOCAL POCKET), which is camera-angle
   * dependent and can be several mm from where a human would judge "the top centre of the cap"
   * by eye.
   *
   * v2 (hit-anchored ball, not a ray corridor): collect mesh vertices within
   * CENTER_BALL_RADIUS_MM of P ITSELF — not of the ray line — widening to
   * CENTER_BALL_WIDE_RADIUS_MM if that ball is too sparse. Anchoring at P (where the doctor
   * actually clicked) rather than sweeping the whole ray keeps the search local to the clicked
   * pocket: the cap's top ring sits ~1-2mm above and ~1-2.5mm radially from a recess hit, while
   * an overhanging NEIGHBOUR structure that happens to cross the ray far from P (measured 4-6mm
   * from a deep P on one real adversarial case) falls outside even the widened ball. A pure
   * ray-corridor (v1) had no such anchor — it swept the ray's entire length and let a neighbour
   * leaning over the cap pollute the corridor. Project the ball's vertices onto the picking ray
   * (t = (v - rayOrigin) . rayDir, dropping t < 0) and take a low percentile of that depth — the
   * nearest-to-eye edge of the clicked pocket, i.e. the visible top ring level, hovering over the
   * hole. An INDICATOR of "the top centre", not a literal on-surface point (the backend already
   * treats centerMark as a locator and ignores its depth precision; see App.tsx/toWireRunSiteInput
   * — no backend change needed).
   *
   * Falls back to the raw raycast hit when the ball (even widened) has no vertices at all — an
   * edge case on very sparse meshes, not expected on real scans. Returns null when the click
   * doesn't hit the mesh at all (unchanged behavior — clicking off-mesh already does nothing).
   */
  private resolveCenterPlacement(clientX: number, clientY: number): THREE.Vector3 | null {
    const mesh = this.meshObject;
    const hit = this.raycastClientHit(clientX, clientY);
    if (!mesh || !hit) return null;

    const geometry = mesh.geometry;
    const positionAttr = geometry.getAttribute("position") as THREE.BufferAttribute | undefined;
    if (!positionAttr) return hit.point.clone();

    // this.raycaster.ray is in WORLD space already (setFromCamera builds it from the camera's
    // world matrix) — the ball/projection comparisons need vertices in world space too.
    const ray = this.raycaster.ray;
    const hitPoint = hit.point;
    const isIdentityTransform = mesh.matrixWorld.equals(IDENTITY_MATRIX4);
    const vertex = new THREE.Vector3();
    const array = positionAttr.array;

    const collectBallDepths = (radiusMm: number): number[] => {
      const radiusSq = radiusMm * radiusMm;
      const depths: number[] = [];
      for (let i = 0; i < positionAttr.count; i += 1) {
        const base = i * 3;
        vertex.set(array[base] as number, array[base + 1] as number, array[base + 2] as number);
        if (!isIdentityTransform) {
          vertex.applyMatrix4(mesh.matrixWorld);
        }
        // Anchored at the RAW HIT P, not the ray line — a 3D distance-to-point ball, so a
        // neighbouring structure the ray merely passes near (far from P along the ray) cannot
        // pollute it, unlike v1's distance-to-ray-line corridor.
        if (vertex.distanceToSquared(hitPoint) > radiusSq) continue;
        // Project onto the ray: t = (v - origin) . direction (direction is unit length, per
        // THREE.Raycaster's contract) — depth along the picking ray, camera-relative.
        const t = vertex.clone().sub(ray.origin).dot(ray.direction);
        if (t < 0) continue; // behind the camera along this ray — not a real ball member
        depths.push(t);
      }
      return depths;
    };

    let depths = collectBallDepths(CENTER_BALL_RADIUS_MM);
    if (depths.length < CENTER_BALL_MIN_VERTICES) {
      depths = collectBallDepths(CENTER_BALL_WIDE_RADIUS_MM);
    }
    if (depths.length === 0) {
      return hit.point.clone();
    }

    depths.sort((a, b) => a - b);
    const tP10 = percentile(depths, CENTER_BALL_PERCENTILE);
    return ray.origin.clone().addScaledVector(ray.direction, tP10);
  }

  /** Build a standalone glowing Points object from a snapshot of points (used for commits). */
  private buildPointsObject(points: readonly THREE.Vector3[]): THREE.Points {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(this.toPositionArray(points), 3));
    geometry.computeBoundingSphere();
    const material = new THREE.PointsMaterial({
      color: BRUSH_COLOR,
      size: BRUSH_POINT_SIZE,
      sizeAttenuation: true,
    });
    return new THREE.Points(geometry, material);
  }

  private toPositionArray(points: readonly THREE.Vector3[]): Float32Array {
    const positions = new Float32Array(points.length * 3);
    points.forEach((p, i) => {
      positions[i * 3] = p.x;
      positions[i * 3 + 1] = p.y;
      positions[i * 3 + 2] = p.z;
    });
    return positions;
  }

  private updateLiveStrokeObject(): void {
    if (this.liveStroke.length === 0) {
      if (this.liveStrokeObject) {
        this.scene.remove(this.liveStrokeObject);
        this.liveStrokeObject.geometry.dispose();
        (this.liveStrokeObject.material as THREE.Material).dispose();
        this.liveStrokeObject = null;
      }
      return;
    }

    const positions = this.toPositionArray(this.liveStroke);

    if (!this.liveStrokeObject) {
      this.liveStrokeObject = this.buildPointsObject(this.liveStroke);
      this.scene.add(this.liveStrokeObject);
      return;
    }

    const geometry = this.liveStrokeObject.geometry;
    const existing = geometry.getAttribute("position") as THREE.BufferAttribute | undefined;
    if (existing && existing.array.length === positions.length) {
      existing.set(positions);
      existing.needsUpdate = true;
    } else {
      geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    }
    geometry.computeBoundingSphere();
  }

  /**
   * Size every proposal marker's DOT against the CURRENT framing (see MARKER_RADIUS_FRACTION).
   * Rings (see buildCenterRingLine) are deliberately SKIPPED here — a ring's radius is fit in real
   * millimetres from the cap's own rim, and rescaling it by the view-fraction rule that sizes
   * the dot would drift it away from the actual geometry it is supposed to hug (the whole point
   * is that it matches the rim from any framing, not just the one active when it was drawn).
   *
   * Called both when markers are placed and again on every framing change — the mount order
   * is markers-then-frame at least as often as the reverse, so a pane that frames after its
   * markers arrive must not leave them at the wrong scale. Before this existed the product
   * used a fixed 2.6mm radius and the ball buried the cap it was marking.
   */
  private applyMarkerScale(): void {
    const radius =
      this.lastFrameRadius > 0
        ? Math.max(this.lastFrameRadius * MARKER_RADIUS_FRACTION, MARKER_MIN_RADIUS_MM)
        : MARKER_BASE_RADIUS_MM;
    for (const child of this.markerGroup.children) {
      if (child instanceof THREE.Mesh) {
        child.scale.setScalar(radius / MARKER_BASE_RADIUS_MM);
      }
    }
  }

  /**
   * Mesh vertices within `radiusMm` of `center` (plain distance-to-POINT, not to a picking ray
   * — setMarkers places markers from data, never a click, so there is no ray to anchor to; see
   * fitCenterRingPlane's doc for why this is still the right local sample). Empty when no mesh
   * is loaded or it carries no position attribute — the ring fit degrades to "no ring" from an
   * empty sample, same fallback as a genuinely sparse one.
   */
  private collectNearbyVertices(center: THREE.Vector3, radiusMm: number): (readonly [number, number, number])[] {
    const mesh = this.meshObject;
    if (!mesh) return [];
    const positionAttr = mesh.geometry.getAttribute("position") as THREE.BufferAttribute | undefined;
    if (!positionAttr) return [];

    const isIdentityTransform = mesh.matrixWorld.equals(IDENTITY_MATRIX4);
    const vertex = new THREE.Vector3();
    const array = positionAttr.array;
    const radiusSq = radiusMm * radiusMm;
    const out: (readonly [number, number, number])[] = [];
    for (let i = 0; i < positionAttr.count; i += 1) {
      const base = i * 3;
      vertex.set(array[base] as number, array[base + 1] as number, array[base + 2] as number);
      if (!isIdentityTransform) vertex.applyMatrix4(mesh.matrixWorld);
      if (vertex.distanceToSquared(center) > radiusSq) continue;
      out.push([vertex.x, vertex.y, vertex.z]);
    }
    return out;
  }

  /** The same tight-then-widen ball resolveCenterPlacement's corridor scan uses (see its doc
   *  and CENTER_BALL_RADIUS_MM/CENTER_BALL_WIDE_RADIUS_MM/CENTER_BALL_MIN_VERTICES), reused
   *  here as the ring fit's raw sample — fitCenterRingPlane applies its own (separate,
   *  intentionally duplicated — see that module's doc) minimum-vertex floor regardless. */
  private nearbyVerticesForRing(center: THREE.Vector3): (readonly [number, number, number])[] {
    const tight = this.collectNearbyVertices(center, CENTER_BALL_RADIUS_MM);
    if (tight.length >= CENTER_BALL_MIN_VERTICES) return tight;
    return this.collectNearbyVertices(center, CENTER_BALL_WIDE_RADIUS_MM);
  }

  /**
   * The ring line for a fitted plane — a flat 48-gon standing in for a circle (WebGL has no
   * primitive circle; a segment count this high is visually indistinguishable from one at the
   * radii these rings are drawn at). `u`/`v` are an ARBITRARY orthonormal in-plane basis (any
   * starting axis not parallel to the normal works — see perpendicularSeed's twin in
   * centerRing.ts): the ring has no preferred roll, unlike the pose triad's axes, so there is
   * no "which way is up in-plane" question to get wrong here.
   */
  private buildCenterRingLine(center: THREE.Vector3, ring: CenterRingFit): THREE.Line {
    const normal = new THREE.Vector3(ring.normal[0], ring.normal[1], ring.normal[2]);
    const arbitrary = Math.abs(normal.y) < 0.9 ? new THREE.Vector3(0, 1, 0) : new THREE.Vector3(1, 0, 0);
    const u = new THREE.Vector3().crossVectors(normal, arbitrary).normalize();
    const v = new THREE.Vector3().crossVectors(normal, u).normalize();

    const segments = 48;
    const points: THREE.Vector3[] = [];
    for (let i = 0; i <= segments; i += 1) {
      const theta = (i / segments) * Math.PI * 2;
      points.push(
        center
          .clone()
          .addScaledVector(u, Math.cos(theta) * ring.radiusMm)
          .addScaledVector(v, Math.sin(theta) * ring.radiusMm),
      );
    }
    const geometry = new THREE.BufferGeometry().setFromPoints(points);
    const material = new THREE.LineBasicMaterial({ color: MARKER_COLOR });
    const line = new THREE.Line(geometry, material);
    // Same render-through-geometry indicator convention as the dot it accompanies (see
    // makeIndicatorVisible's doc) — a ring drawn WITH depth testing would half-vanish behind
    // the very rim it exists to trace, which is worse than the dot alone.
    makeIndicatorVisible(material, line);
    return line;
  }

  /**
   * Drop glowing marker spheres at the given points, in the same coordinate frame as the loaded
   * mesh — plus, wherever the local mesh honestly supports it, a ring in the cap's own top-ring
   * plane hugging the rim around each dot (see centerRing.ts's header for the full diagnosis:
   * the client-reported "marker sits on the rim, not the centre" defect, and why a ring anchors
   * a hovering dot from any camera angle where a plain sphere cannot). Degrades to the plain
   * dot alone — never a ring at a guessed orientation — on a missing/sparse mesh or a
   * neighbourhood too linear to fit (fitCenterRingPlane returns null; see its doc).
   */
  setMarkers(markers: readonly MarkerSpec[]): void {
    this.clearMarkers();
    for (const marker of markers) {
      const centerVec = new THREE.Vector3(marker.center[0], marker.center[1], marker.center[2]);

      // Built at the BASE radius and scaled by applyMarkerScale below — marker.radiusMm is
      // deliberately not used as an absolute size (see MARKER_RADIUS_FRACTION).
      const geometry = new THREE.SphereGeometry(MARKER_BASE_RADIUS_MM, 20, 16);
      const material = new THREE.MeshStandardMaterial({
        color: MARKER_COLOR,
        emissive: MARKER_EMISSIVE,
        emissiveIntensity: 0.85,
        roughness: 0.35,
      });
      const sphere = new THREE.Mesh(geometry, material);
      sphere.position.copy(centerVec);
      // Same render-through-geometry indicator convention as every other marker kind — a
      // proposal sphere is exactly as much "not a physical object on the surface" as the rest.
      makeIndicatorVisible(material, sphere);
      this.markerGroup.add(sphere);

      const ring = fitCenterRingPlane(
        [centerVec.x, centerVec.y, centerVec.z],
        this.nearbyVerticesForRing(centerVec),
      );
      if (ring) {
        this.markerGroup.add(this.buildCenterRingLine(centerVec, ring));
      }
    }
    this.applyMarkerScale();
  }

  clearMarkers(): void {
    for (const child of [...this.markerGroup.children]) {
      this.markerGroup.remove(child);
      if (child instanceof THREE.Mesh) {
        child.geometry.dispose();
        if (Array.isArray(child.material)) {
          child.material.forEach((m) => m.dispose());
        } else {
          child.material.dispose();
        }
      } else if (child instanceof THREE.Line) {
        child.geometry.dispose();
        const material = child.material;
        if (Array.isArray(material)) {
          material.forEach((m) => m.dispose());
        } else {
          material.dispose();
        }
      }
    }
  }

  private clearMesh(): void {
    // The derived part frame describes THIS mesh — drop it whenever the mesh goes, so a later
    // getPartFrame can never answer about geometry that is no longer on screen.
    this.partFrame = null;
    this.partFrameComputed = false;
    if (!this.meshObject) return;
    if (this.meshObjectIsCompositePart) {
      // Owned by compositeMeshes — clearComposite() disposes it. Disposing it here too would
      // double-dispose the same THREE geometry/material; just drop the reference.
      this.meshObject = null;
      this.meshObjectIsCompositePart = false;
      return;
    }
    this.scene.remove(this.meshObject);
    this.meshObject.geometry.dispose();
    const material = this.meshObject.material;
    if (Array.isArray(material)) {
      material.forEach((m) => m.dispose());
    } else {
      material.dispose();
    }
    this.meshObject = null;
  }

  dispose(): void {
    this.disposed = true;
    cancelAnimationFrame(this.animationHandle);
    this.resizeObserver.disconnect();
    const canvas = this.renderer.domElement;
    canvas.removeEventListener("pointerdown", this.handleBrushPointerDown);
    canvas.removeEventListener("pointermove", this.handleBrushPointerMove);
    canvas.removeEventListener("pointerup", this.handleBrushPointerUp);
    canvas.removeEventListener("pointerleave", this.handleBrushPointerUp);
    canvas.removeEventListener("pointerdown", this.handleMarkPointerDown);
    canvas.removeEventListener("pointerdown", this.handleRimPointsPointerDown);
    canvas.removeEventListener("pointerdown", this.handlePointPickPointerDown);
    window.removeEventListener("keydown", this.handleShiftPanKeyDown);
    window.removeEventListener("keyup", this.handleShiftPanKeyUp);
    window.removeEventListener("blur", this.handleShiftPanWindowBlur);
    this.clearAllBrushPatches();
    this.clearAllSiteMarkers();
    this.clearAllRimPoints();
    this.clearAllPoseTriads();
    this.clearPartFeatureMarkers();
    this.clearAllCorrespondenceMarks();
    this.clearMesh();
    this.clearComposite();
    this.clearMarkers();
    this.controls.dispose();
    this.renderer.dispose();
    if (this.renderer.domElement.parentElement === this.container) {
      this.container.removeChild(this.renderer.domElement);
    }
  }
}

export const PART_COLOR = PART_MATERIAL_COLOR;
export const SCAN_COLOR = SCAN_MATERIAL_COLOR;
