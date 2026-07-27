import { useEffect, useRef } from "react";
import {
  OrbitLinkGroup,
  VerifyScene,
  type VerifyLayerGeometry,
  type VerifyMarker,
} from "./verifyScene";
import type { Vec3 } from "../domain/types";

/** One layer as the PANE is asked to show it: geometry (null until it has loaded), plus the
 *  operator's eye toggle and opacity slider for it. */
export interface VerifyViewerLayer {
  readonly id: string;
  readonly geometry: VerifyLayerGeometry | null;
  readonly visible: boolean;
  readonly opacity: number;
}

interface VerifyViewerProps {
  readonly layers: readonly VerifyViewerLayer[];
  /**
   * Where to point the camera: a world centre + radius (the marked site), or null to frame
   * whatever is loaded (the library part, which lives in its own local frame).
   *
   * `viewDirection` is the axis to look DOWN — for a healing cap, the direction its top face
   * points in. Supplied, the pane opens looking straight at the top of the cap instead of from
   * a fixed world-space three-quarter angle that means nothing to the part in front of it.
   */
  readonly frame: {
    readonly center: Vec3;
    readonly radiusMm: number;
    readonly viewDirection?: Vec3 | null;
    /** The up-vector to roll the camera to — shared across panes so features read at the same
     *  clock angle in each. */
    readonly up?: Vec3 | null;
  } | null;
  /** The shared "link views" group — omitted for a standalone pane. */
  readonly linkGroup?: OrbitLinkGroup | null;
  /** Numbered points drawn over the geometry (the fit-by-points flow). Omitted = none. */
  readonly markers?: readonly VerifyMarker[];
  /** Arms click-to-place on this pane's geometry (the fit-by-points flow's scan half).
   *  Omitted, the pane stays read-only and a click is only ever an orbit. */
  readonly onPick?: ((point: [number, number, number]) => void) | null;
  readonly ariaLabel: string;
}

/** No markers, as a STABLE identity — a fresh `[]` default would re-run the marker effect on
 *  every render of a pane that has none, rebuilding nothing but churning the scene graph. */
const NO_MARKERS: readonly VerifyMarker[] = [];

/**
 * One live pane of the three-panel verify. A thin React shell over VerifyScene: it owns the
 * canvas' lifetime, pushes geometry/visibility/opacity down as props change, and joins the
 * orbit-link group so the three panes can be rotated together.
 *
 * Geometry is diffed by OBJECT IDENTITY — the dialog derives each layer's typed arrays once and
 * memoizes them, so a re-render caused by (say) an opacity slider does not re-upload a 20k
 * triangle scan crop to the GPU. Framing is re-applied only when the target itself changes, so
 * the operator's own orbit survives every unrelated re-render.
 */
export function VerifyViewer({
  layers,
  frame,
  linkGroup,
  markers = NO_MARKERS,
  onPick = null,
  ariaLabel,
}: VerifyViewerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const sceneRef = useRef<VerifyScene | null>(null);
  const uploadedRef = useRef(new Map<string, VerifyLayerGeometry>());
  const framedRef = useRef<string | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;
    const scene = new VerifyScene(container);
    sceneRef.current = scene;
    uploadedRef.current = new Map();
    framedRef.current = null;
    if (import.meta.env.DEV) {
      // dev-only hook for scripted browser verification (orbit mirroring across panes) —
      // the same affordance SceneController exposes as __artechScene for the main stage
      const registry = ((window as unknown as Record<string, unknown>).__artechVerifyScenes ??=
        {}) as Record<string, VerifyScene>;
      registry[ariaLabel] = scene;
    }
    return () => {
      scene.onOrbitChange(null);
      scene.dispose();
      sceneRef.current = null;
      if (import.meta.env.DEV) {
        const registry = (window as unknown as Record<string, unknown>).__artechVerifyScenes as
          | Record<string, VerifyScene>
          | undefined;
        if (registry) delete registry[ariaLabel];
      }
    };
  }, [ariaLabel]);

  // Join/leave the link group (and report this pane's own orbit into it).
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return undefined;
    if (!linkGroup) {
      scene.onOrbitChange(null);
      return undefined;
    }
    linkGroup.add(scene);
    scene.onOrbitChange((orbit) => linkGroup.broadcast(scene, orbit));
    return () => {
      scene.onOrbitChange(null);
      linkGroup.remove(scene);
    };
  }, [linkGroup]);

  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;
    const uploaded = uploadedRef.current;
    const seen = new Set<string>();
    for (const layer of layers) {
      seen.add(layer.id);
      if (layer.geometry === null) {
        if (uploaded.has(layer.id)) {
          scene.removeLayer(layer.id);
          uploaded.delete(layer.id);
        }
        continue;
      }
      if (uploaded.get(layer.id) !== layer.geometry) {
        scene.setLayer(layer.id, layer.geometry);
        uploaded.set(layer.id, layer.geometry);
      }
      scene.setLayerVisible(layer.id, layer.visible);
      scene.setLayerOpacity(layer.id, layer.opacity);
    }
    for (const id of [...uploaded.keys()]) {
      if (!seen.has(id)) {
        scene.removeLayer(id);
        uploaded.delete(id);
      }
    }
  }, [layers]);

  // The numbered points. Pushed on every change of the list itself (short, and its labels move
  // when a pair is removed — see VerifyScene.setMarkers for why that rules out a diff).
  useEffect(() => {
    sceneRef.current?.setMarkers(markers);
  }, [markers]);

  // The armed click. A ref-free effect: the LATEST handler is installed on every change, so a
  // pick always calls the callback the component is rendering with, never one closed over
  // earlier (the pair list this appends to moves under it between clicks).
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return undefined;
    scene.onPick(onPick);
    return () => scene.onPick(null);
  }, [onPick]);

  // Re-frame only on a genuine target change (a new site, or the first geometry landing) —
  // never on an opacity/visibility re-render, which would yank the operator's own orbit back.
  const frameKey = frame
    ? `${frame.center[0]},${frame.center[1]},${frame.center[2]}|${frame.radiusMm}|${
        frame.viewDirection ? frame.viewDirection.join(",") : "default"
      }|${frame.up ? frame.up.join(",") : "auto"}`
    : `all:${layers.filter((l) => l.geometry !== null).map((l) => l.id).join(",")}`;
  useEffect(() => {
    const scene = sceneRef.current;
    if (!scene) return;
    if (framedRef.current === frameKey) return;
    const hasGeometry = layers.some((l) => l.geometry !== null);
    if (!hasGeometry) return;
    if (frame) scene.frameOn(frame.center, frame.radiusMm, frame.viewDirection ?? null, frame.up ?? null);
    else scene.frameAll();
    framedRef.current = frameKey;
    // `layers` is read only to know whether anything is on screen yet; the geometry effect above
    // owns uploads, so re-running this on a layer change is intentional and cheap.
  }, [frameKey, frame, layers]);

  return <div ref={containerRef} className="verify-viewer" role="img" aria-label={ariaLabel} />;
}
