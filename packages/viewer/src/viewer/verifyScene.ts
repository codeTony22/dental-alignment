/**
 * ONE PANE of the three-panel verify (client's library-selection dialog, 2026-07-25): a small,
 * self-contained three.js scene showing a handful of NAMED LAYERS with per-layer visibility and
 * opacity, plus an orbit that can be mirrored into its sibling panes.
 *
 * Deliberately NOT SceneController. That controller owns the workflow's single stage — brush
 * painting, mark picking, rim-point collection, pose triads, anatomy presets, proposal markers —
 * none of which belongs in a read-only comparison pane, and three copies of it would arm three
 * sets of pointer handlers over the same workflow state. This is the other half: no picking, no
 * marks, no workflow; geometry in, opacity/visibility/orbit out.
 *
 * Geometry arrives as flat typed arrays (see meshCrop.ts / mappers.mapSiteDeviation) rather than
 * URLs, because the panes SHARE their source: the doctor's scan is parsed once for the whole
 * dialog and cropped per site, and the union pane's coloured mesh is the deviation payload the
 * API already sent. `loadStlPositions` is the one IO edge, exported for the dialog's own loader.
 *
 * CAMERA SYNC is by ORBIT, not by absolute pose: pane 1 shows a 6mm library part in its own
 * local frame while panes 2-3 show a cap region somewhere out in the scanner's world frame, so a
 * shared world camera would be meaningless. Sharing the spherical angles and a relative distance
 * makes "rotate all three together" behave exactly as an operator expects, at the cost of one
 * float per axis.
 */
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { mmPerPixelAtFocus, viewReadoutChanged, type PaneViewReadout } from "./paneReadout";
import { clampZoomScale } from "./zoom";

/** The pane background — the same light-blue backdrop the main viewer uses, so the dialog's
 *  panes and the workflow's stage read as one application. */
const BACKGROUND_COLOR = 0xd8e8f2;

/** How much of the framed radius the camera pulls back to: 2.6x reads as "the whole thing, with
 *  air around it" at the 45 degree FOV both viewers use. */
const FRAME_DISTANCE_FACTOR = 2.6;

/** The perspective camera's vertical field of view. Named because the pane's scale bar
 *  divides by its tangent — the number is no longer only a look, it is a measurement. */
const CAMERA_FOV_DEG = 45;

/** The orbit state mirrored between panes: two spherical angles and a distance RELATIVE to each
 *  pane's own framing (so a 6mm part and a 20mm scan region stay equally filled). */
/**
 * A camera pose expressed in the pane's OWN FRAMED BASIS (client 2026-08-04:
 * "does align all the panes in the same view and position of the camera").
 *
 * The previous shape mirrored WORLD spherical angles — only the target and the
 * distance unit were pane-local — so panes whose content lives in different
 * frames (the library part's canonical +z vs the scan's seated axis) could not
 * agree by construction: the operator looked down the cap in pane 2 and pane 1
 * mirrored to 177° off its OWN axis, upside down under a chip saying "rotating
 * together". Basis-relative mirroring makes the link's claim literal: the same
 * relative view of each pane's own content, absolutely, on every orbit.
 */
export interface VerifyOrbit {
  /** target→camera offset in the pane's framed basis, in framing-distance units. */
  readonly offset: readonly [number, number, number];
  /** camera.up in the same basis. */
  readonly up: readonly [number, number, number];
}

/** The pane's framed BASIS — columns right/up/back, back = the target→camera
 * direction at framing. Pure and exported: the link math must be pinnable in a
 * node test, because its failure mode (panes drifting apart while claiming to
 * be linked) is invisible to every markup test. */
export function basisFromDirectionUp(
  direction: THREE.Vector3,
  up: THREE.Vector3,
): THREE.Matrix3 {
  const back = direction.clone().normalize();
  const projected = up.clone().projectOnPlane(back);
  const upN =
    projected.lengthSq() > 1e-12
      ? projected.normalize()
      : Math.abs(back.z) > 0.9
        ? new THREE.Vector3(0, 1, 0)
        : new THREE.Vector3(0, 0, 1).projectOnPlane(back).normalize();
  const right = new THREE.Vector3().crossVectors(upN, back);
  return new THREE.Matrix3().set(
    right.x, upN.x, back.x,
    right.y, upN.y, back.y,
    right.z, upN.z, back.z,
  );
}

/** This pane's camera pose → the shared basis-relative orbit. */
export function orbitInBasis(
  offsetWorld: THREE.Vector3,
  upWorld: THREE.Vector3,
  basis: THREE.Matrix3,
  baseDistance: number,
): VerifyOrbit {
  const inverse = basis.clone().transpose(); // orthonormal: transpose = inverse
  const unit = baseDistance > 0 ? baseDistance : 1;
  const local = offsetWorld.clone().divideScalar(unit).applyMatrix3(inverse);
  const upLocal = upWorld.clone().applyMatrix3(inverse);
  return {
    offset: [local.x, local.y, local.z],
    up: [upLocal.x, upLocal.y, upLocal.z],
  };
}

/** The shared orbit → THIS pane's world camera offset and up. The distance floor
 * keeps the old contract: a mirrored orbit never parks a camera inside its
 * subject. */
export function orbitFromBasis(
  orbit: VerifyOrbit,
  basis: THREE.Matrix3,
  baseDistance: number,
): { readonly offset: THREE.Vector3; readonly up: THREE.Vector3 } {
  const local = new THREE.Vector3(orbit.offset[0], orbit.offset[1], orbit.offset[2]);
  const length = local.length();
  if (length > 1e-9) local.multiplyScalar(Math.max(length, 0.05) / length);
  else local.set(0, 0, 0.05);
  const unit = baseDistance > 0 ? baseDistance : 1;
  const offset = local.applyMatrix3(basis).multiplyScalar(unit);
  const up = new THREE.Vector3(orbit.up[0], orbit.up[1], orbit.up[2]).applyMatrix3(basis);
  return { offset, up };
}

/** One layer's geometry: a flat non-indexed position stream, or positions + faces + per-vertex
 *  colours (the deviation mesh). `colors` are LINEAR floats — see deviationColormap. */
export interface VerifyLayerGeometry {
  readonly positions: Float32Array;
  readonly indices?: Uint32Array;
  readonly colors?: Float32Array;
  /** Flat colour when `colors` is absent. */
  readonly color?: number;
  /** A SPECULAR material instead of the matte Lambert (client 2026-08-10 on
   *  pane 2's cap: "we need more glossy white here") — a healing cap is
   *  polished titanium/PEEK, and gloss is what reads as material truth. */
  readonly glossy?: boolean;
}

interface Layer {
  readonly mesh: THREE.Mesh;
  readonly material: THREE.MeshLambertMaterial | THREE.MeshPhongMaterial;
}

/**
 * ONE NUMBERED POINT on a pane — the fit-by-points flow's whole vocabulary (client, 2026-07-26:
 * their reference shows numbered points on the scan AND on the library part, side by side).
 * `label` is what the operator reads, not an id: pair 1 on the part and pair 1 on the scan are
 * the same correspondence, which is only legible if both wear the same number.
 */
export interface VerifyMarker {
  readonly key: string;
  readonly position: readonly [number, number, number];
  /** The feature's own colour (see viewer/palette.featureHex) — shared with its list row. */
  readonly color: number;
  readonly label: string;
  /** Drawn hollow/dimmed: a point the flow knows about but the operator has not placed yet. */
  readonly pending?: boolean;
}

/**
 * Marker size AS A FRACTION OF THE PANE'S FRAMED RADIUS, not in millimetres.
 *
 * A fixed millimetre size cannot serve both panes: the same 1.2mm label is a discreet dot over an
 * 18mm scan region and a badge covering the landmark on a 6mm library part (seen live,
 * 2026-07-26 — the "1" hid the very trench it named). Sized against the framing instead, a marker
 * occupies the same share of every pane, which is what "the same point on both views" has to
 * mean when the two views are at different scales.
 */
const MARKER_RADIUS_FRACTION = 0.04;
const MARKER_LABEL_FRACTION = 0.14;

/** The sphere is built at this radius and SCALED — one geometry, any framing. */
const MARKER_BASE_RADIUS_MM = 1;

/** How far (px) the pointer may travel between down and up and still count as a CLICK rather
 *  than an orbit drag — the same threshold the main stage's picker uses. */
const PICK_DRAG_SLOP_PX = 4;

/** Draw a marker's number onto a small canvas for its sprite. Module-level (not per marker) so
 *  the 2D context is created once per label, and testable-by-inspection: no scene state. */
function labelTexture(label: string, color: number): THREE.Texture {
  const size = 64;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    ctx.fillStyle = `#${color.toString(16).padStart(6, "0")}`;
    ctx.beginPath();
    ctx.arc(size / 2, size / 2, size / 2 - 2, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "#ffffff";
    ctx.lineWidth = 4;
    ctx.stroke();
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 36px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(label, size / 2, size / 2 + 2);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  return texture;
}

/**
 * THE ARMED PANE SAYS SO UNDER THE POINTER (client 2026-07-30).
 *
 * A pane with a pick listener installed behaves completely differently from its
 * neighbours — a click PLACES a point instead of doing nothing — and until this there
 * was no tell on the glass at all: the operator learned a pane was live by clicking it.
 * The cursor is the cheapest honest signal, and it belongs to the container (cursor
 * inherits, so the canvas inside it follows) rather than to an inline style, so the
 * product's stylesheet keeps the decision.
 *
 * A pure function because VerifyScene itself is browser-only (WebGLRenderer in the
 * constructor); this is the half a node test can hold.
 */
export function armedViewerClassName(armed: boolean): string {
  return armed ? "verify-viewer verify-viewer--armed" : "verify-viewer";
}

/**
 * Does this controls "change" event mean a HAND ON THE MOUSE — the only kind of camera
 * move that may be mirrored onto the linked panes?
 *
 * `onOrbitChange`'s contract is "called whenever the USER moves this pane's camera
 * (never for an applied orbit)", and a programmatic re-frame is neither: it is an
 * ASSIGNMENT of a camera position, exactly like a mirrored orbit, and broadcasting it
 * makes the last pane to frame overwrite its siblings (design review 2026-07-31). Pure
 * because VerifyScene itself is browser-only; this is the half a node test can hold.
 */
export function shouldBroadcastOrbit(
  assigningCamera: boolean,
  hasListener: boolean,
): boolean {
  return !assigningCamera && hasListener;
}

/** Fetch + parse one STL into a flat, non-indexed position stream. The single IO edge here; the
 *  dialog calls it once per distinct file (through the app's blob cache) and slices the result. */
export async function loadStlPositions(url: string): Promise<Float32Array> {
  const { STLLoader } = await import("three/examples/jsm/loaders/STLLoader.js");
  const geometry = await new STLLoader().loadAsync(url);
  const source = geometry.index ? geometry.toNonIndexed() : geometry;
  const position = source.getAttribute("position");
  const array = new Float32Array(position.array as ArrayLike<number>);
  source.dispose();
  if (source !== geometry) geometry.dispose();
  return array;
}

/**
 * The "link views" group: every mounted pane registers itself, and while linking is ON a user
 * orbit in one pane is mirrored into the others (around each pane's OWN target and framing —
 * see the module doc). Membership is independent of the toggle, so linking can be switched on
 * mid-session without remounting anything.
 */
export class OrbitLinkGroup {
  private readonly members = new Set<VerifyScene>();
  private enabled = false;

  add(scene: VerifyScene): void {
    this.members.add(scene);
  }

  remove(scene: VerifyScene): void {
    this.members.delete(scene);
  }

  setEnabled(enabled: boolean): void {
    this.enabled = enabled;
  }

  /** Mirror `orbit` into every pane except the one it came from. No-op while linking is off. */
  broadcast(source: VerifyScene, orbit: VerifyOrbit): void {
    if (!this.enabled) return;
    for (const member of this.members) {
      if (member !== source) member.applyOrbit(orbit);
    }
  }
}

export class VerifyScene {
  private readonly renderer: THREE.WebGLRenderer;
  private readonly scene: THREE.Scene;
  private readonly camera: THREE.PerspectiveCamera;
  private readonly controls: OrbitControls;
  private readonly layers = new Map<string, Layer>();
  /** The numbered points drawn over the layers — one group, replaced wholesale (see setMarkers). */
  private markerGroup: THREE.Group | null = null;
  /** Each marker's sphere, its label sprite and the world point they mark — kept so a re-framing
   *  can re-scale them (their size is a fraction of the framing, not a constant). */
  private markerParts: {
    readonly sphere: THREE.Mesh;
    readonly sprite: THREE.Sprite;
    readonly position: readonly [number, number, number];
  }[] = [];
  private readonly raycaster = new THREE.Raycaster();
  private pickListener: ((point: [number, number, number]) => void) | null = null;
  private pointerDownAt: { x: number; y: number } | null = null;
  private readonly resizeObserver: ResizeObserver;
  private animationHandle = 0;
  private disposed = false;
  /** The distance the current framing chose — the unit `VerifyOrbit.offset` is measured
   *  in, so a mirrored orbit means "the same relative zoom", not "the same millimetres". */
  private baseDistance = 1;
  /** The framed basis the shared orbit is expressed in — set by every frameOn. */
  private frameBasis = new THREE.Matrix3();
  /** Shift+left-drag pans, exactly like the main stage — the panes' navigation
   *  must feel like ONE app's (client 2026-08-04: "not like the main one"). */
  private shiftPanActive = false;
  /** True while an externally-applied orbit is being written, so the resulting controls "change"
   *  event is not echoed back to the panes that sent it (which would ping-pong forever). */
  private applyingOrbit = false;
  private orbitListener: ((orbit: VerifyOrbit) => void) | null = null;
  /** The footer band's source (gap pane-footer-scale-bar-and-axis-label): the pane can only
   *  say how big the subject is and where the camera is looking if the SCENE says so — no
   *  amount of CSS knows a perspective camera's distance. Gated by viewReadoutChanged
   *  because "change" fires every damped frame. */
  private viewListener: ((readout: PaneViewReadout) => void) | null = null;
  private lastView: PaneViewReadout | null = null;

  constructor(private readonly container: HTMLDivElement) {
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(BACKGROUND_COLOR);

    const width = Math.max(container.clientWidth, 1);
    const height = Math.max(container.clientHeight, 1);
    this.camera = new THREE.PerspectiveCamera(CAMERA_FOV_DEG, width / height, 0.05, 5000);
    this.camera.position.set(0, 0, 60);

    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setSize(width, height);
    container.appendChild(this.renderer.domElement);

    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.screenSpacePanning = true;
    this.controls.addEventListener("change", this.handleControlsChange);
    this.renderer.domElement.addEventListener("pointerdown", this.handlePointerDown);
    this.renderer.domElement.addEventListener("pointerup", this.handlePointerUp);
    // the main stage's own mappings (client 2026-08-04: the pane navigation must
    // feel like the workflow viewer's): shift+left-drag pans; right-drag pan and
    // scroll zoom are OrbitControls defaults both viewers already share
    window.addEventListener("keydown", this.handleShiftPanKeyDown);
    window.addEventListener("keyup", this.handleShiftPanKeyUp);
    window.addEventListener("blur", this.handleShiftPanWindowBlur);

    // Same lighting recipe as the main stage (client 2026-07-24: "the scan is a bit dark") so a
    // part looks the same here as it does on the workflow's viewer.
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x9fb4c4, 1.2));
    const key = new THREE.DirectionalLight(0xffffff, 0.9);
    key.position.set(80, 120, 100);
    this.scene.add(key);
    const fill = new THREE.DirectionalLight(0xffffff, 0.5);
    fill.position.set(-100, -60, -80);
    this.scene.add(fill);

    this.resizeObserver = new ResizeObserver(() => this.handleResize());
    this.resizeObserver.observe(container);
    this.animate();
  }

  private animate = (): void => {
    if (this.disposed) return;
    this.animationHandle = requestAnimationFrame(this.animate);
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  };

  private handleResize(): void {
    const width = this.container.clientWidth;
    const height = this.container.clientHeight;
    if (width === 0 || height === 0) return;
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
    // mm-per-pixel is per PIXEL: the same camera over a shorter pane measures differently,
    // so a resize invalidates the scale bar exactly as an orbit does.
    this.emitView();
  }

  private handleControlsChange = (): void => {
    // The view readout fires even for an APPLIED orbit: a pane mirrored from its sibling has
    // genuinely moved, and its footer would otherwise keep describing where it used to be.
    // Only the orbit BROADCAST is suppressed, which is what stops the ping-pong.
    this.emitView();
    if (!shouldBroadcastOrbit(this.applyingOrbit, this.orbitListener !== null)) return;
    this.orbitListener!(this.getOrbit());
  };

  /**
   * Run a CAMERA ASSIGNMENT with the resulting "change" event kept out of the link group.
   *
   * Both callers assign a camera outright rather than reporting a hand on the mouse: a
   * mirrored orbit (applyOrbit) and a re-frame (frameOn). Only the first was guarded, so
   * with "link views" on a preset click made every pane broadcast its own re-framing and
   * the LAST pane to frame imposed its world-space spherical angles on the other two —
   * and since pane 1 renders the library part in its canonical FILE frame while panes 2/3
   * live in the jaw-scan world frame, no pane ended up on the basis the preset asked for
   * (design review 2026-07-31).
   */
  private assigningCamera<T>(fn: () => T): T {
    const was = this.applyingOrbit;
    this.applyingOrbit = true;
    try {
      return fn();
    } finally {
      this.applyingOrbit = was;
    }
  }

  private handlePointerDown = (event: PointerEvent): void => {
    this.pointerDownAt = { x: event.clientX, y: event.clientY };
  };

  /**
   * A CLICK on the pane's geometry, resolved to a world point — the scan half of the
   * fit-by-points flow. Orbiting must stay orbiting, so a pointer that travelled more than
   * PICK_DRAG_SLOP_PX between down and up is a camera move and never a placement. Markers are
   * deliberately NOT raycast against: clicking a point you already placed should re-place it on
   * the surface under it, not on the sphere in front of it.
   */
  private handlePointerUp = (event: PointerEvent): void => {
    const down = this.pointerDownAt;
    this.pointerDownAt = null;
    if (down === null || this.pickListener === null) return;
    if (Math.abs(event.clientX - down.x) > PICK_DRAG_SLOP_PX) return;
    if (Math.abs(event.clientY - down.y) > PICK_DRAG_SLOP_PX) return;
    const rect = this.renderer.domElement.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;
    const ndc = new THREE.Vector2(
      ((event.clientX - rect.left) / rect.width) * 2 - 1,
      -(((event.clientY - rect.top) / rect.height) * 2 - 1),
    );
    this.raycaster.setFromCamera(ndc, this.camera);
    const meshes = [...this.layers.values()].filter((l) => l.mesh.visible).map((l) => l.mesh);
    if (meshes.length === 0) return;
    const hit = this.raycaster.intersectObjects(meshes, false)[0];
    if (!hit) return;
    this.pickListener([hit.point.x, hit.point.y, hit.point.z]);
  };

  /** Arm (or disarm, with null) click-to-place on this pane's geometry. */
  onPick(listener: ((point: [number, number, number]) => void) | null): void {
    this.pickListener = listener;
  }

  /**
   * Replace every numbered point on this pane. Wholesale rather than incremental because the
   * list is short (the correspondence cap is a handful of pairs) and a diff would have to track
   * label changes too — renumbering after a removal moves every marker's label, which is exactly
   * the case an incremental path gets wrong.
   */
  setMarkers(markers: readonly VerifyMarker[]): void {
    this.clearMarkers();
    if (markers.length === 0) return;
    const group = new THREE.Group();
    for (const marker of markers) {
      const sphere = new THREE.Mesh(
        new THREE.SphereGeometry(MARKER_BASE_RADIUS_MM, 16, 12),
        new THREE.MeshBasicMaterial({
          color: marker.color,
          transparent: marker.pending === true,
          opacity: marker.pending === true ? 0.35 : 1,
          depthTest: false,
        }),
      );
      sphere.position.set(marker.position[0], marker.position[1], marker.position[2]);
      sphere.renderOrder = 10;
      group.add(sphere);

      const sprite = new THREE.Sprite(
        new THREE.SpriteMaterial({
          map: labelTexture(marker.label, marker.color),
          depthTest: false,
          transparent: true,
        }),
      );
      sprite.renderOrder = 11;
      group.add(sprite);
      this.markerParts.push({ sphere, sprite, position: marker.position });
    }
    this.scene.add(group);
    this.markerGroup = group;
    this.applyMarkerScale();
  }

  /** Size every marker against the CURRENT framing (see MARKER_RADIUS_FRACTION). Called when
   *  markers are placed and again whenever the pane re-frames, so a pane that framed after its
   *  markers arrived — which is the mount order — never leaves them at the wrong scale. */
  private applyMarkerScale(): void {
    const framedRadius = this.baseDistance / FRAME_DISTANCE_FACTOR;
    const radius = Math.max(framedRadius * MARKER_RADIUS_FRACTION, 0.01);
    const label = Math.max(framedRadius * MARKER_LABEL_FRACTION, 0.02);
    for (const { sphere, sprite, position } of this.markerParts) {
      sphere.scale.setScalar(radius / MARKER_BASE_RADIUS_MM);
      sprite.scale.set(label, label, label);
      // the label floats just clear of its own sphere, never on top of the landmark
      sprite.position.set(position[0], position[1], position[2] + radius + label * 0.6);
    }
  }

  clearMarkers(): void {
    this.markerParts = [];
    const group = this.markerGroup;
    if (group === null) return;
    this.scene.remove(group);
    group.traverse((obj) => {
      if (obj instanceof THREE.Mesh) {
        obj.geometry.dispose();
        (obj.material as THREE.Material).dispose();
      } else if (obj instanceof THREE.Sprite) {
        obj.material.map?.dispose();
        obj.material.dispose();
      }
    });
    this.markerGroup = null;
  }

  /** Replace (or create) one named layer's geometry. Normals are computed here — a cropped scan
   *  region and a deviation payload both arrive as bare positions. */
  setLayer(id: string, geometry: VerifyLayerGeometry): void {
    this.removeLayer(id);
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(geometry.positions, 3));
    if (geometry.indices) geo.setIndex(new THREE.BufferAttribute(geometry.indices, 1));
    if (geometry.colors) geo.setAttribute("color", new THREE.BufferAttribute(geometry.colors, 3));
    geo.computeVertexNormals();
    geo.computeBoundingSphere();
    const material = geometry.glossy
      ? new THREE.MeshPhongMaterial({
          color: geometry.colors ? 0xffffff : (geometry.color ?? 0xf2e3a6),
          vertexColors: geometry.colors !== undefined,
          side: THREE.DoubleSide,
          specular: 0x777777,
          shininess: 60,
        })
      : new THREE.MeshLambertMaterial({
          color: geometry.colors ? 0xffffff : (geometry.color ?? 0xf2e3a6),
          vertexColors: geometry.colors !== undefined,
          side: THREE.DoubleSide,
        });
    const mesh = new THREE.Mesh(geo, material);
    this.scene.add(mesh);
    this.layers.set(id, { mesh, material });
  }

  hasLayer(id: string): boolean {
    return this.layers.has(id);
  }

  removeLayer(id: string): void {
    const layer = this.layers.get(id);
    if (!layer) return;
    this.scene.remove(layer.mesh);
    layer.mesh.geometry.dispose();
    layer.material.dispose();
    this.layers.delete(id);
  }

  clearLayers(): void {
    for (const id of [...this.layers.keys()]) this.removeLayer(id);
  }

  setLayerVisible(id: string, visible: boolean): void {
    const layer = this.layers.get(id);
    if (layer) layer.mesh.visible = visible;
  }

  /**
   * Per-layer opacity (the client's own control). depthWrite follows opacity: a fully opaque
   * layer writes depth as usual, a see-through one does not — otherwise the scan's near wall
   * would depth-occlude the cap the operator is trying to see THROUGH it.
   */
  setLayerOpacity(id: string, opacity: number): void {
    const layer = this.layers.get(id);
    if (!layer) return;
    const clamped = Math.min(Math.max(opacity, 0), 1);
    layer.material.opacity = clamped;
    layer.material.transparent = clamped < 1;
    layer.material.depthWrite = clamped >= 1;
    layer.material.needsUpdate = true;
  }

  /**
   * Point the camera at a world position, pulled back to show `radiusMm` around it. Also
   * (re)sets the distance unit orbit mirroring is measured in.
   *
   * `viewDirection` is the unit vector FROM the target TOWARD the camera — for a healing cap
   * that is the direction its top face looks in, so passing the cap's own axis puts the camera
   * straight above it (client, 2026-07-26: "position all the panels … facing the top of the
   * cap"). Omitted, the pane keeps the fixed three-quarter angle, which is right for anything
   * with no axis of its own to look down.
   */
  /**
   * Apply a camera change WITHOUT the operator's leftover orbit momentum landing on top
   * of it.
   *
   * OrbitControls only clears its accumulators when damping is OFF: with damping on,
   * `update()` merely DECAYS `sphericalDelta`/`panOffset`, so whatever spin was still in
   * flight keeps being applied on the frames after a re-frame and drags the camera off
   * the view just set. Measured 2026-07-29 with a real drag: orbiting a pane away and
   * then re-framing it landed somewhere different every time and never on the framing
   * the pane was born with — the "camera is a bit weird" report.
   *
   * Toggling damping off for exactly one update takes the branch that ZEROES both
   * accumulators, then restores the setting so ordinary dragging keeps its feel.
   */
  private settleControls(): void {
    const damping = this.controls.enableDamping;
    this.controls.enableDamping = false;
    this.controls.update();
    this.controls.enableDamping = damping;
  }

  frameOn(
    center: readonly [number, number, number],
    radiusMm: number,
    viewDirection?: readonly [number, number, number] | null,
    upHint?: readonly [number, number, number] | null,
  ): void {
    // A RE-FRAME IS NOT A USER ORBIT (see assigningCamera). Guarding it is what lets a
    // named viewpoint reach three linked panes at once: without it the panes framed in
    // tree order and each broadcast overwrote its siblings' basis.
    this.assigningCamera(() => this.frameOnNow(center, radiusMm, viewDirection, upHint));
  }

  private frameOnNow(
    center: readonly [number, number, number],
    radiusMm: number,
    viewDirection?: readonly [number, number, number] | null,
    upHint?: readonly [number, number, number] | null,
  ): void {
    const target = new THREE.Vector3(center[0], center[1], center[2]);
    const distance = Math.max(radiusMm, 0.5) * FRAME_DISTANCE_FACTOR;
    this.baseDistance = distance;
    this.controls.target.copy(target);
    const requested = viewDirection
      ? new THREE.Vector3(viewDirection[0], viewDirection[1], viewDirection[2])
      : null;
    const direction =
      requested && requested.lengthSq() > 1e-12
        ? requested.normalize()
        : new THREE.Vector3(0.35, 0.45, 1).normalize();
    // Looking straight down an axis leaves the camera's roll undefined, and OrbitControls'
    // default up (+Y) is degenerate when the axis IS +Y — the view flips or spins. Pick any
    // stable perpendicular; every pane then holds a fixed roll instead of drifting.
    if (requested) {
      // THE SHARED CLOCK REFERENCE (2026-07-26). With a caller-supplied up — the seated pose's
      // own x-axis for the scan panes, the part's +x for the library pane — a coded cutout lands
      // at the SAME screen angle in all three panes, which is the entire reason for showing them
      // side by side. Without one, any perpendicular will do to stop the roll drifting.
      const hint = upHint ? new THREE.Vector3(upHint[0], upHint[1], upHint[2]) : null;
      const seed =
        hint && hint.lengthSq() > 1e-12
          ? hint
          : Math.abs(direction.y) > 0.9
            ? new THREE.Vector3(0, 0, 1)
            : new THREE.Vector3(0, 1, 0);
      const up = seed.clone().projectOnPlane(direction);
      this.syncCameraUp(
        up.lengthSq() > 1e-9 ? up.normalize() : new THREE.Vector3(0, 0, 1),
      );
    } else {
      // no requested direction: keep the pane's standing up, re-synced so the
      // drag frame below is coherent with it
      this.syncCameraUp(this.camera.up.clone());
    }
    // the basis the shared orbit is expressed in — EVERY framing resets it, so a
    // linked orbit after any re-frame maps through the frame the pane now has
    this.frameBasis = basisFromDirectionUp(direction, this.camera.up);
    this.camera.position.copy(target).addScaledVector(direction, distance);
    this.camera.near = Math.max(distance / 500, 0.05);
    this.camera.far = distance * 50;
    this.camera.updateProjectionMatrix();
    this.settleControls();
    // the framing IS the marker scale's unit — re-size them with it
    this.applyMarkerScale();
    this.emitView();
  }

  /** Frame everything currently loaded (the library part, which has no site centre of its own). */
  frameAll(): void {
    const box = new THREE.Box3();
    for (const { mesh } of this.layers.values()) {
      mesh.geometry.computeBoundingBox();
      if (mesh.geometry.boundingBox) box.union(mesh.geometry.boundingBox);
    }
    if (box.isEmpty()) return;
    const center = new THREE.Vector3();
    box.getCenter(center);
    const size = new THREE.Vector3();
    box.getSize(size);
    // HALF THE DIAGONAL, not half the largest side: the pane looks at the part from a
    // three-quarter angle, where a 7mm-wide, 5mm-tall cap projects ~11mm corner to corner —
    // framing on the widest SIDE cropped it against the pane's edges (seen live).
    this.frameOn([center.x, center.y, center.z], size.length() / 2);
  }

  getOrbit(): VerifyOrbit {
    return orbitInBasis(
      this.camera.position.clone().sub(this.controls.target),
      this.camera.up,
      this.frameBasis,
      this.baseDistance,
    );
  }

  /** Mirror another pane's orbit onto this one — the SAME pose in THIS pane's own
   *  framed basis, absolutely (client 2026-08-04: the old world-angle mirror put
   *  the library pane 177° off its own axis while the chip said "rotating
   *  together"). Up mirrors with it: a rolled sibling and an unrolled pane are
   *  not the same view. */
  applyOrbit(orbit: VerifyOrbit): void {
    this.assigningCamera(() => {
      const pose = orbitFromBasis(orbit, this.frameBasis, this.baseDistance);
      this.camera.position.copy(this.controls.target).add(pose.offset);
      if (pose.up.lengthSq() > 1e-9) this.syncCameraUp(pose.up.normalize());
      // Same reason as frameOn: a mirrored orbit is an ASSIGNMENT of a camera position,
      // and this pane's own leftover momentum has no business being added to the pane it
      // is mirroring — that is how linked views drift apart while claiming to be linked.
      this.settleControls();
    });
  }

  /**
   * Change the camera's up axis AND re-sync OrbitControls' internal up-quaternion —
   * the main stage's own fix (sceneController.setCameraUp), ported: OrbitControls
   * captures `camera.up` ONCE at construction and runs every drag in that frozen
   * y-up frame, so a pane framed down an arbitrary seated axis dragged "weird" —
   * horizontal drags tumbled and rolled the model (client 2026-08-04: "not like
   * the main one that is more cohesive and natural"). Underscore-private but
   * stable in three 0.185; degrades to the old behavior if renamed.
   */
  private syncCameraUp(up: THREE.Vector3): void {
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

  // --- Shift+left-drag pan (the main stage's own mapping, ported) --------------------

  private readonly handleShiftPanKeyDown = (event: KeyboardEvent): void => {
    if (event.key !== "Shift" || this.shiftPanActive) return;
    this.shiftPanActive = true;
    this.controls.mouseButtons.LEFT = THREE.MOUSE.PAN;
  };

  private readonly handleShiftPanKeyUp = (event: KeyboardEvent): void => {
    if (event.key !== "Shift") return;
    this.restoreLeftMouseButton();
  };

  private readonly handleShiftPanWindowBlur = (): void => {
    // a window/tab switch while Shift is held never fires keyup — restore on blur
    this.restoreLeftMouseButton();
  };

  private restoreLeftMouseButton(): void {
    this.shiftPanActive = false;
    this.controls.mouseButtons.LEFT = THREE.MOUSE.ROTATE;
  }

  /**
   * Step this pane's camera in or out by `factor`, about the framing it already has.
   *
   * A MULTIPLIER, not a destination: the toolbar's −/+ and the operator's scroll wheel
   * both move the same camera, and a zoom that assigned an absolute distance would drag
   * the view back to the button's opinion every time the button moved. Multiplying leaves
   * whatever the wheel did in place and steps from there.
   *
   * The step is clamped in SCALE space (multiples of the framing distance) rather than in
   * millimetres, because that is the space the near/far planes were derived in — see
   * MIN_ZOOM_SCALE. Guarded like `applyOrbit`: a button press is an assignment of a camera
   * position, and the controls' leftover momentum has no business being added to it.
   */
  zoomBy(factor: number): void {
    if (!Number.isFinite(factor) || factor <= 0) return;
    const offset = this.camera.position.clone().sub(this.controls.target);
    const radius = offset.length();
    if (!(radius > 0) || !(this.baseDistance > 0)) return;
    const next = clampZoomScale((radius * factor) / this.baseDistance) * this.baseDistance;
    this.assigningCamera(() => {
      this.camera.position
        .copy(this.controls.target)
        .add(offset.multiplyScalar(next / radius));
      this.settleControls();
    });
    // the pane's scale bar is a function of the distance we just changed
    this.emitView();
  }

  /** Called whenever the USER moves this pane's camera (never for an applied orbit). */
  onOrbitChange(listener: ((orbit: VerifyOrbit) => void) | null): void {
    this.orbitListener = listener;
  }

  /**
   * WHAT THE PANE MAY SAY ABOUT ITSELF RIGHT NOW: the direction the camera is looking from
   * and the millimetres one CSS pixel covers at the focus plane.
   *
   * mmPerPixel is null-able through mmPerPixelAtFocus and collapses to 0 here only when the
   * container has not been laid out yet; the surface treats a non-positive value as "no bar",
   * which is the point — a scale bar that is wrong is worse than a pane with no scale bar.
   */
  getViewReadout(): PaneViewReadout {
    const offset = this.camera.position.clone().sub(this.controls.target);
    const distance = offset.length();
    const direction = distance > 1e-9 ? offset.divideScalar(distance) : new THREE.Vector3(0, 0, 1);
    const mmPerPixel = mmPerPixelAtFocus(distance, CAMERA_FOV_DEG, this.container.clientHeight);
    return {
      viewDirection: [direction.x, direction.y, direction.z],
      mmPerPixel: mmPerPixel ?? 0,
    };
  }

  /** Subscribe to the readout. Fires once immediately on subscribe so a freshly mounted pane
   *  does not sit label-less until the operator happens to touch it. */
  onViewChange(listener: ((readout: PaneViewReadout) => void) | null): void {
    this.viewListener = listener;
    this.lastView = null;
    if (listener !== null) this.emitView();
  }

  private emitView(): void {
    const listener = this.viewListener;
    if (listener === null) return;
    const next = this.getViewReadout();
    if (!viewReadoutChanged(this.lastView, next)) return;
    this.lastView = next;
    listener(next);
  }

  dispose(): void {
    this.disposed = true;
    this.viewListener = null;
    cancelAnimationFrame(this.animationHandle);
    this.resizeObserver.disconnect();
    this.controls.removeEventListener("change", this.handleControlsChange);
    this.renderer.domElement.removeEventListener("pointerdown", this.handlePointerDown);
    this.renderer.domElement.removeEventListener("pointerup", this.handlePointerUp);
    window.removeEventListener("keydown", this.handleShiftPanKeyDown);
    window.removeEventListener("keyup", this.handleShiftPanKeyUp);
    window.removeEventListener("blur", this.handleShiftPanWindowBlur);
    this.pickListener = null;
    this.controls.dispose();
    this.clearMarkers();
    this.clearLayers();
    this.renderer.dispose();
    if (this.renderer.domElement.parentElement === this.container) {
      this.container.removeChild(this.renderer.domElement);
    }
  }
}
