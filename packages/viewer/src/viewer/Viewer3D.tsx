import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import {
  SceneController,
  type AnatomyViewId,
  type CompositePartSpec,
  type MarkerSpec,
  type MarkKind,
  type PartFeatureMarkerSpec,
  type PartRole,
  type PoseTriadSpec,
  type ViewerFitMode,
  PART_COLOR,
  SCAN_COLOR,
} from "./sceneController";
import type { FeatureKind } from "./palette";
import type { PartFrame } from "./partFrame";

export interface Viewer3DHandle {
  loadStl(
    url: string,
    opts?: {
      color?: number;
      fit?: ViewerFitMode;
      onProgress?: (fractionLoaded: number) => void;
      anatomy?: boolean;
    },
  ): Promise<void>;
  loadComposite(parts: readonly CompositePartSpec[], fit?: ViewerFitMode): Promise<void>;
  getCompositeRoles(): PartRole[];
  setAnatomyView(view: AnatomyViewId): void;
  hasAnatomyFrame(): boolean;
  /** Route the stage to a site's neighbourhood. False = refused (a tool is armed, or bad input). */
  focusOnSite(
    center: readonly [number, number, number],
    radiusMm: number,
    opts?: { readonly animateMs?: number },
  ): boolean;
  /** Back out to everything currently loaded — the operator's way home from a site. */
  frameLoadedContent(): boolean;
  /** True while any pointer tool owns the next click on the scan (the routing veto). */
  isToolActive(): boolean;
  setMarkers(markers: readonly MarkerSpec[]): void;
  clearMarkers(): void;
  enableBrush(): void;
  disableBrush(): void;
  getBrushPatch(): number[][];
  clearBrush(): void;
  commitBrushPatch(rowIndex: number): void;
  clearCommittedPatch(rowIndex: number): void;
  clearAllBrushPatches(): void;
  enterMarkMode(rowIndex: number, kind: MarkKind, onPlaced: (point: [number, number, number]) => void): void;
  exitMarkMode(): void;
  isMarkModeActive(): boolean;
  enterPointPick(
    onPicked: (point: [number, number, number]) => void,
    onMissed?: () => void,
  ): void;
  exitPointPick(): void;
  isPointPickActive(): boolean;
  setSiteMarker(rowIndex: number, kind: MarkKind, point: readonly [number, number, number]): void;
  clearSiteMarker(rowIndex: number, kind: MarkKind): void;
  clearAllSiteMarkers(): void;
  enableRimPoints(rowIndex: number): void;
  cancelRimPoints(): void;
  isRimPointsActive(): boolean;
  activeRimPointsRow(): number | null;
  getRimPointsPatch(): number[][];
  finishRimPoints(rowIndex: number, legacyRimMark?: readonly [number, number, number]): void;
  clearRimPoints(rowIndex: number, legacyRimMark?: readonly [number, number, number]): void;
  clearAllRimPoints(): void;
  setPoseTriad(tooth: number, spec: PoseTriadSpec): void;
  clearPoseTriad(tooth: number): void;
  clearAllPoseTriads(): void;
  /** The previewed library part's canonical frame (null when the current content has none) —
   *  the annotation mode needs it to turn a click into the canonical point the PUT wants. */
  getPartFrame(): PartFrame | null;
  /** Draw the library part's marks; returns how many landed (0 = no derivable frame). */
  setPartFeatureMarkers(specs: readonly PartFeatureMarkerSpec[]): number;
  clearPartFeatureMarkers(): void;
  setCorrespondenceMark(featureId: string, kind: FeatureKind, point: readonly [number, number, number]): void;
  clearCorrespondenceMark(featureId: string): void;
  clearAllCorrespondenceMarks(): void;
}

interface Viewer3DProps {
  readonly ariaLabel: string;
}

export const Viewer3D = forwardRef<Viewer3DHandle, Viewer3DProps>(function Viewer3D(
  { ariaLabel },
  forwardedRef,
) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const controllerRef = useRef<SceneController | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const controller = new SceneController(container);
    controllerRef.current = controller;
    if (import.meta.env.DEV) {
      // dev-only hook for scripted browser verification (world->screen projection)
      (window as unknown as Record<string, unknown>).__artechScene = controller;
    }
    return () => {
      controller.dispose();
      controllerRef.current = null;
      if (import.meta.env.DEV) {
        delete (window as unknown as Record<string, unknown>).__artechScene;
      }
    };
  }, []);

  useImperativeHandle(
    forwardedRef,
    () => ({
      async loadStl(url, opts) {
        const controller = controllerRef.current;
        if (!controller) return;
        await controller.loadStl(url, opts);
      },
      async loadComposite(parts, fit) {
        const controller = controllerRef.current;
        if (!controller) return;
        await controller.loadComposite(parts, fit);
      },
      getCompositeRoles() {
        return controllerRef.current?.getCompositeRoles() ?? [];
      },
      setAnatomyView(view) {
        controllerRef.current?.setAnatomyView(view);
      },
      hasAnatomyFrame() {
        return controllerRef.current?.hasAnatomyFrame() ?? false;
      },
      focusOnSite(center, radiusMm, opts) {
        return controllerRef.current?.focusOnSite(center, radiusMm, opts) ?? false;
      },
      frameLoadedContent() {
        return controllerRef.current?.frameLoadedContent() ?? false;
      },
      isToolActive() {
        return controllerRef.current?.isToolActive() ?? false;
      },
      setMarkers(markers) {
        controllerRef.current?.setMarkers(markers);
      },
      clearMarkers() {
        controllerRef.current?.clearMarkers();
      },
      enableBrush() {
        controllerRef.current?.enableBrush();
      },
      disableBrush() {
        controllerRef.current?.disableBrush();
      },
      getBrushPatch() {
        return controllerRef.current?.getBrushPatch() ?? [];
      },
      clearBrush() {
        controllerRef.current?.clearBrush();
      },
      commitBrushPatch(rowIndex) {
        controllerRef.current?.commitBrushPatch(rowIndex);
      },
      clearCommittedPatch(rowIndex) {
        controllerRef.current?.clearCommittedPatch(rowIndex);
      },
      clearAllBrushPatches() {
        controllerRef.current?.clearAllBrushPatches();
      },
      enterMarkMode(rowIndex, kind, onPlaced) {
        controllerRef.current?.enterMarkMode(rowIndex, kind, onPlaced);
      },
      exitMarkMode() {
        controllerRef.current?.exitMarkMode();
      },
      isMarkModeActive() {
        return controllerRef.current?.isMarkModeActive() ?? false;
      },
      enterPointPick(onPicked, onMissed) {
        controllerRef.current?.enterPointPick(onPicked, onMissed);
      },
      exitPointPick() {
        controllerRef.current?.exitPointPick();
      },
      isPointPickActive() {
        return controllerRef.current?.isPointPickActive() ?? false;
      },
      setSiteMarker(rowIndex, kind, point) {
        controllerRef.current?.setSiteMarker(rowIndex, kind, point);
      },
      clearSiteMarker(rowIndex, kind) {
        controllerRef.current?.clearSiteMarker(rowIndex, kind);
      },
      clearAllSiteMarkers() {
        controllerRef.current?.clearAllSiteMarkers();
      },
      enableRimPoints(rowIndex) {
        controllerRef.current?.enableRimPoints(rowIndex);
      },
      cancelRimPoints() {
        controllerRef.current?.cancelRimPoints();
      },
      isRimPointsActive() {
        return controllerRef.current?.isRimPointsActive() ?? false;
      },
      activeRimPointsRow() {
        return controllerRef.current?.activeRimPointsRow() ?? null;
      },
      getRimPointsPatch() {
        return controllerRef.current?.getRimPointsPatch() ?? [];
      },
      finishRimPoints(rowIndex, legacyRimMark) {
        controllerRef.current?.finishRimPoints(rowIndex, legacyRimMark);
      },
      clearRimPoints(rowIndex, legacyRimMark) {
        controllerRef.current?.clearRimPoints(rowIndex, legacyRimMark);
      },
      clearAllRimPoints() {
        controllerRef.current?.clearAllRimPoints();
      },
      setPoseTriad(tooth, spec) {
        controllerRef.current?.setPoseTriad(tooth, spec);
      },
      clearPoseTriad(tooth) {
        controllerRef.current?.clearPoseTriad(tooth);
      },
      clearAllPoseTriads() {
        controllerRef.current?.clearAllPoseTriads();
      },
      getPartFrame() {
        return controllerRef.current?.getPartFrame() ?? null;
      },
      setPartFeatureMarkers(specs) {
        return controllerRef.current?.setPartFeatureMarkers(specs) ?? 0;
      },
      clearPartFeatureMarkers() {
        controllerRef.current?.clearPartFeatureMarkers();
      },
      setCorrespondenceMark(featureId, kind, point) {
        controllerRef.current?.setCorrespondenceMark(featureId, kind, point);
      },
      clearCorrespondenceMark(featureId) {
        controllerRef.current?.clearCorrespondenceMark(featureId);
      },
      clearAllCorrespondenceMarks() {
        controllerRef.current?.clearAllCorrespondenceMarks();
      },
    }),
    [],
  );

  return <div ref={containerRef} className="viewer3d" role="img" aria-label={ariaLabel} />;
});

export const VIEWER_PART_COLOR = PART_COLOR;
export const VIEWER_SCAN_COLOR = SCAN_COLOR;
