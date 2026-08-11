/**
 * THE VIEWER PACKAGE'S PUBLIC SURFACE (plan §3/AM-5, copy-debt ledger row 3). Named
 * exports only — each line is a decision about what the product may consume, so a new
 * export is a diff a reviewer sees, not a barrel side effect.
 *
 * Everything under src/viewer is a controlled COPY of the frozen demo's apps/web/src/viewer;
 * divergences are recorded in docs/engagement/copy-debt-ledger.md row 3.
 */

// The main stage: the imperative controller and its React shell.
export {
  SceneController,
  PART_COLOR,
  SCAN_COLOR,
  SITE_FIT_PADDING,
  anatomyViewOrientation,
  anyPointerToolActive,
  clipPlanesFor,
  featureMarkerRadiusMm,
  fitDistanceMm,
  fitPaddingFor,
  percentile,
} from "./viewer/sceneController";
export type {
  AnatomyViewId,
  MarkKind,
  MarkerSpec,
  PartFeatureMarkerSpec,
  PoseTriadSpec,
  ViewerFitMode,
} from "./viewer/sceneController";
export { Viewer3D, VIEWER_PART_COLOR, VIEWER_SCAN_COLOR } from "./viewer/Viewer3D";
export type { Viewer3DHandle } from "./viewer/Viewer3D";

// The three-panel verify pane: scene, orbit link, React shell.
export {
  OrbitLinkGroup,
  VerifyScene,
  armedViewerClassName,
  loadStlPositions,
} from "./viewer/verifyScene";
export type { VerifyLayerGeometry, VerifyMarker, VerifyOrbit } from "./viewer/verifyScene";
// What a pane may honestly say about its own camera — the footer band's scale bar and
// live axis label (the design's static "OCCLUSAL" caption would start lying on first drag).
export {
  mmPerPixelAtFocus,
  paneAxisLabel,
  paneScaleBar,
  viewReadoutChanged,
} from "./viewer/paneReadout";
export type { PaneScaleBar, PaneViewReadout } from "./viewer/paneReadout";
export { VerifyViewer } from "./viewer/VerifyViewer";
/* The zoom counter's arithmetic. The product needs `canZoom` to disable a spent button and
   ZOOM_STEP only to describe the step in a title; the clamp and the factor are the scene's
   business and are not re-exported. */
export { ZOOM_STEP, canZoom, clampZoomLevel } from "./viewer/zoom";
export type { VerifyViewerLayer } from "./viewer/VerifyViewer";

// Pure geometry/colour rules (all unit-tested in this package's node suite).
export { computeAnatomyFrame } from "./viewer/anatomyOrientation";
export type { AnatomyFrame } from "./viewer/anatomyOrientation";
export {
  AXIS_CONCENTRICITY_MAX_MM,
  RING_FIT_MAX_RMS_MM,
  canonicalFromRaw,
  computePartFrame,
  kasaCentre,
  percentileSorted,
  rawFromCanonical,
  rawFromFeature,
} from "./viewer/partFrame";
export type { PartFrame, Point3 } from "./viewer/partFrame";
export {
  CAP_REGION_RADIUS_MM,
  centroidOf,
  cropTrianglesInCylinder,
  cropTrianglesNear,
  triangleCount,
} from "./viewer/meshCrop";
export {
  buildSurfaceGrid,
  cropTrianglesNearSurface,
  posePositions,
} from "./viewer/meshDistance";
export type { SurfaceGrid } from "./viewer/meshDistance";
export {
  CONTACTS_MAX_MM,
  UNMEASURED_COLOR_HEX,
  buildDeviationColors,
  buildScaleColors,
  clampNoteFor,
  contactsColorSrgb,
  contactsFraction,
  contactsGradientCss,
  contactsRampSrgb255,
  contactsTickLabels,
  deviationColorSrgb,
  deviationFraction,
  deviationGradientCss,
  deviationTickLabels,
  rampSrgb255,
  srgbToLinear,
} from "./viewer/deviationColormap";
export type { DeviationScaleId } from "./viewer/deviationColormap";
export { SITE_FRAME_RADIUS_MM, resolveRouteTarget, routeSignature } from "./viewer/siteRouting";
export type { RouteInputs, RouteTarget, StageSubject } from "./viewer/siteRouting";

// The composite/marker colour code.
export {
  CAP_SCAN_COLOR,
  FEATURE_COLOR,
  FREE_POINT_COLOR,
  GHOST_POINT_COLOR,
  PALETTE,
  ROLE_LABEL,
  capScanHex,
  featureHex,
  freePointHex,
  paletteHex,
} from "./viewer/palette";
export type { CompositePartSpec, FeatureKind, PartRole } from "./viewer/palette";

// The once-per-case scan cache (caller supplies the URL — see the module's divergence note).
export { clearScanPositionsCache, scanPositionsFor } from "./viewer/scanPositions";

// The one domain type the viewer stack imports (see domain/types.ts's trim note).
export type { Vec3 } from "./domain/types";
