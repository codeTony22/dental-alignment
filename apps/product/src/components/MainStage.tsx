/**
 * THE MAIN STAGE (plan §7 slice 3): the product's 3D surface, built on the copied viewer
 * package — the first consumer AM-5's copy exists for. The 3D panes ARE the product; the
 * stage takes the space and the chrome around it stays thin.
 *
 * What this slice mounts: the doctor's scan streamed from the BFF's scan endpoint,
 * opening at the anatomical FRONT view (the safe rim-reading angle — the viewer computes
 * it from the scan's own geometry), and the demo's site routing: the stage frames the
 * active site's neighbourhood, with the subject toggle ("this site" / "whole arch") as
 * the operator's way out. The toggle is REIMPLEMENTED against the same StageSubject
 * vocabulary rather than copied — it is ~40 lines of product chrome, not viewer physics.
 *
 * What later slices add here: real site selection (4/5a feeds the active site), pointer
 * tools and their veto inputs (6), seated poses as routing targets (5c) — which is why
 * toolActive/posePosition are honest constants below, not missing wiring.
 */
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  Viewer3D,
  resolveRouteTarget,
  routeSignature,
  type AnatomyViewId,
  type MarkerSpec,
  type StageSubject,
  type Vec3,
  type Viewer3DHandle,
} from "viewer";
import { scanUrlFor, type SiteView } from "../api/client";

/** The scan-load lifecycle, stated honestly — the stage never fakes a loaded arch. */
export type ScanLoadState =
  | { readonly kind: "loading" }
  | { readonly kind: "ready" }
  | { readonly kind: "error"; readonly detail: string };

/**
 * A refusal is not an outage, on the stage exactly as on the shell (slice 2's banner
 * doctrine): a 404 in the loader's words means the BFF answered and this case has no
 * scan to stream; anything else keeps the plain did-not-load words.
 */
export function scanErrorHeadline(detail: string): string {
  return detail.includes("404")
    ? "The case service answered, but this case's scan is not there to stream."
    : "The scan did not load.";
}

/**
 * The demo's anatomical view presets (ViewOrientationBar's DIRECTION row, ported —
 * parity fix, ledger row 9; client ask 2026-07-14: make finding the right face easy).
 * One click = one named camera view derived from the scan's own geometry — no orbiting
 * hunt back to a face once the operator has dragged the camera somewhere strange.
 * "Left"/"Right" are screen-relative to the Front view (the copied AnatomyViewId's
 * doc says why they are not labeled by patient side); clicks are a safe no-op before
 * an anatomy frame exists (the controller's own rule).
 */
const VIEWS: readonly {
  readonly id: AnatomyViewId;
  readonly label: string;
  readonly title: string;
  /** The word the CAPTION uses for this view, carried on the same row as the button that
   *  selects it so the two cannot drift. The caption used to say "front view" whatever the
   *  camera was doing, because that word was hard-coded a hundred lines from the control
   *  that changed it (seen on screen 2026-08-01: Top selected, caption still claiming the
   *  front). A label naming a direction it is not looking from is the same defect the pane
   *  audit raised against a static OCCLUSAL string. */
  readonly caption: string;
}[] = [
  { id: "front", label: "Front", title: "Face the front of the mouth", caption: "front" },
  { id: "left", label: "Left", title: "View from the left of the front view", caption: "left" },
  { id: "right", label: "Right", title: "View from the right of the front view",
    caption: "right" },
  { id: "occlusal", label: "Top", title: "Look straight down at the crowns (occlusal view)",
    caption: "top" },
];

/** The caption's word for a view id. Falls back to the front — where the camera starts —
 *  rather than inventing a word for a view that does not exist. */
function viewCaption(view: AnatomyViewId): string {
  return VIEWS.find((row) => row.id === view)?.caption ?? "front";
}

interface OrientationBarProps {
  readonly subject: StageSubject;
  readonly siteAvailable: boolean;
  readonly activeView: AnatomyViewId;
  readonly onSelect: (subject: StageSubject) => void;
  readonly onSelectView: (view: AnatomyViewId) => void;
}

/**
 * The stage's camera pill — the demo's ViewOrientationBar shape: the DIRECTION row
 * (Front/Left/Right/Top) over the SUBJECT row, and the two compose — "This site" then
 * "Top" is looking straight down at the cap. "Whole arch" is the operator's way home
 * and it stays put once chosen.
 */
function OrientationBar({ subject, siteAvailable, activeView, onSelect, onSelectView }: OrientationBarProps) {
  const choices: readonly {
    readonly id: StageSubject;
    readonly label: string;
    readonly title: string;
  }[] = [
    {
      id: "site",
      label: "◎ This site",
      title: "Frame the active site and its immediate neighbours.",
    },
    {
      id: "arch",
      label: "⊞ Whole arch",
      title: "Back out to the whole jaw. The view then stays where you put it.",
    },
  ];
  return (
    // Parity slice: the demo's dark pill overlay (.view-orient), floated ON the glass
    // top-left, instead of a bare row under the canvas.
    <div className="view-orient" role="group" aria-label="Camera views">
      <div className="view-orient__row" role="group" aria-label="Anatomical view presets">
        {VIEWS.map((view) => (
          <button
            key={view.id}
            type="button"
            // Pressed like the SUBJECT row directly beneath it, which has carried its state
            // since the parity slice. These four carried none at all — measured on screen
            // 2026-08-01, every one reported aria-pressed null — so nothing told the
            // operator which view they were in.
            aria-pressed={activeView === view.id}
            className={`view-orient__button${
              activeView === view.id ? " view-orient__button--active" : ""
            }`}
            title={view.title}
            onClick={() => onSelectView(view.id)}
          >
            {view.label}
          </button>
        ))}
      </div>
      <div
        data-role="stage-subject"
        className="view-orient__row"
        role="group"
        aria-label="What the view is framed on"
      >
        {choices.map((choice) => (
          <button
            key={choice.id}
            type="button"
            aria-pressed={choice.id === subject}
            className={`view-orient__button${
              choice.id === subject ? " view-orient__button--active" : ""
            }`}
            disabled={choice.id === "site" && !siteAvailable}
            title={
              choice.id === "site" && !siteAvailable
                ? "No site with a usable centre yet — there is nothing to frame."
                : choice.title
            }
            onClick={() => onSelect(choice.id)}
          >
            {choice.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export interface MainStageViewProps {
  readonly scanState: ScanLoadState;
  readonly scanFilename: string;
  readonly subject: StageSubject;
  readonly siteAvailable: boolean;
  readonly activeTooth: number | null;
  readonly onSelectSubject: (subject: StageSubject) => void;
  /** One click = one named camera view (the direction presets — parity fix). */
  readonly onSelectView: (view: AnatomyViewId) => void;
  /** Which named view the camera was last put in. Drives BOTH the pressed button and the
   *  caption's word, so the control and the sentence cannot disagree. */
  readonly activeView?: AnatomyViewId;
  /** The 3D surface itself — the container passes Viewer3D; tests pass a stub. */
  readonly viewerSlot: ReactNode;
}

/** The stage's chrome, pure payload → markup — statically testable without WebGL. */
export function MainStageView({
  scanState,
  scanFilename,
  subject,
  siteAvailable,
  activeTooth,
  onSelectSubject,
  onSelectView,
  activeView = "front",
  viewerSlot,
}: MainStageViewProps) {
  return (
    // The stage IS the glass (verify-UI directive): every word of chrome floats on the
    // canvas — the subject pill top-left, the drag hint bottom-right, and the honest
    // status/error strips along the bottom — so the 3D keeps every pixel of its box.
    <div data-role="main-stage" className="main-stage viewer3d-wrap">
      <div data-role="main-stage-canvas" className="main-stage__canvas">
        {viewerSlot}
        <OrientationBar
          subject={subject}
          siteAvailable={siteAvailable}
          activeView={activeView}
          onSelect={onSelectSubject}
          onSelectView={onSelectView}
        />
        <div className="viewer-controls-hint" aria-hidden="true">
          drag rotate · shift+drag / right-drag pan · scroll zoom
        </div>
        {scanState.kind === "loading" && (
          <p data-role="stage-status" className="main-stage__notice">
            Loading {scanFilename}…
          </p>
        )}
        {scanState.kind === "error" && (
          <div
            data-role="stage-error"
            role="alert"
            className="main-stage__notice main-stage__notice--error"
          >
            <strong>{scanErrorHeadline(scanState.detail)}</strong>{" "}
            <span>{scanState.detail}</span>
          </div>
        )}
        {scanState.kind === "ready" && subject === "site" && activeTooth !== null && (
          <p data-role="stage-status" className="main-stage__notice">
            Framed on tooth {activeTooth} — {viewCaption(activeView)} view.
          </p>
        )}
      </div>
    </div>
  );
}

export interface MainStageProps {
  readonly caseId: string;
  readonly scanFilename: string;
  readonly sites: readonly SiteView[];
  /** Detected-site rings (slice 4 Intake) — the copied viewer's marker surface.
   * Omitted = no markers, which keeps Declare's mount unchanged. */
  readonly markers?: readonly MarkerSpec[];
  /** Called when an ARMED click lands off the scan (the sky). The pick stays armed —
   *  a miss is an attempt, not a cancellation — and the surface says so. */
  readonly onMarkMissed?: (() => void) | null;
  /** The operator's active site (slice 5a — Declare's queue drives the routing).
   * Omitted/null = the stage's own default, the first site with a usable centre. */
  readonly activeTooth?: number | null;
  /** ARMED: the next click on the scan is the operator's mark for a cap the detector
   *  missed (client 2026-07-28). Omitted/false leaves the stage read-only, which is
   *  what every existing mount wants. */
  readonly markArmed?: boolean;
  readonly onMark?: ((point: readonly [number, number, number]) => void) | null;
}

/** The container: streams the scan, opens FRONT, routes to the active site. */
export function MainStage({
  caseId,
  scanFilename,
  sites,
  markers,
  onMarkMissed = null,
  activeTooth,
  markArmed = false,
  onMark = null,
}: MainStageProps) {
  const viewerRef = useRef<Viewer3DHandle | null>(null);
  const [scanState, setScanState] = useState<ScanLoadState>({ kind: "loading" });
  const [subject, setSubject] = useState<StageSubject>("site");
  // The camera starts on the front view (the controller's own default), and the caption
  // and the pressed button both read this rather than each carrying their own idea.
  const [activeView, setActiveView] = useState<AnatomyViewId>("front");
  /** Bumped when the stage's content is replaced — half the route identity (see siteRouting). */
  const [contentGeneration, setContentGeneration] = useState(0);
  const routedKeyRef = useRef<string | null>(null);

  // The active site: the operator's chosen tooth when one is named (Declare's queue,
  // slice 5a) — honestly NOT reframed onto some other site when that tooth has no
  // usable centre (the toggle disables instead of the stage framing a lie) — else
  // the stage's own default: the first site with a usable centre (the demo's rule).
  const activeSite = useMemo(() => {
    const usable = (s: SiteView) =>
      s.center !== null && s.center.length === 3;
    if (activeTooth !== null && activeTooth !== undefined) {
      return sites.find((s) => s.tooth === activeTooth) ?? null;
    }
    return sites.find(usable) ?? null;
  }, [sites, activeTooth]);
  const siteCenter: Vec3 | null = useMemo(() => {
    const c = activeSite?.center;
    return c && c.length === 3 ? [c[0]!, c[1]!, c[2]!] : null;
  }, [activeSite]);

  useEffect(() => {
    let cancelled = false;
    setScanState({ kind: "loading" });
    routedKeyRef.current = null;
    // anatomy: true — the viewer derives the anatomical frame and OPENS AT FRONT, the
    // safe rim-reading angle (sceneController.loadStl's own contract).
    void viewerRef.current
      ?.loadStl(scanUrlFor(caseId), { anatomy: true })
      .then(() => {
        if (cancelled) return;
        setScanState({ kind: "ready" });
        setContentGeneration((generation) => generation + 1);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setScanState({
          kind: "error",
          detail: err instanceof Error ? err.message : String(err),
        });
      });
    return () => {
      cancelled = true;
    };
  }, [caseId]);

  // Markers follow the payload, not click history: whatever the BFF's detection
  // record says, after every load and on every change (an empty list CLEARS — a
  // re-detected case must not keep stale rings).
  // KEYED ON CONTENT, NOT ARRAY IDENTITY (2026-08-01). IntakeStage passes
  // `markers={detectionMarkers(detail)}` — a fresh array on every render — so this
  // effect re-ran on every parent re-render, not just when detection changed. That was
  // merely wasteful while setMarkers only rebuilt spheres; it stopped being wasteful
  // when the centre RING landed, because fitting each ring scans the mesh vertices
  // around its marker. Same rings, same clearing semantics (an empty list still
  // CLEARS) — the work now happens when the markers actually differ.
  const markerKey = (markers ?? [])
    .map((m) => `${m.center[0]},${m.center[1]},${m.center[2]}`)
    .join("|");
  useEffect(() => {
    if (scanState.kind !== "ready") return;
    viewerRef.current?.setMarkers(markers ?? []);
    // markers is intentionally absent: markerKey IS its content, and depending on the
    // array too would defeat the whole point.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [markerKey, scanState.kind]);

  /* MARKING ARMS THE CONTROLLER'S OWN POINT PICK (client 2026-07-28). The machinery
     has existed since the viewer was lifted — enterPointPick is what the demo's mark
     tools used — it simply had no caller on this stage. Armed only while the operator
     asked for it: a stage that silently swallowed clicks would make orbiting the scan
     feel broken, and orbiting is what this stage is mostly for. */
  useEffect(() => {
    if (!markArmed || onMark === null) return;
    viewerRef.current?.enterPointPick((point) => onMark(point), onMarkMissed ?? undefined);
    // THE CLEANUP IS THE FIX (client 2026-08-01: "buttons are not working").
    // Disarming — the Cancel button, a site switch, unmount — used to leave the
    // controller's pick armed with the ORBIT CONTROLS DISABLED, permanently: arm,
    // cancel, and the scan would neither select nor rotate again. enterPointPick
    // turns the controls off; only exitPointPick turns them back on, and nothing
    // called it on the way out.
    return () => viewerRef.current?.exitPointPick();
  }, [markArmed, onMark, onMarkMissed]);

  const routeTarget = useMemo(
    () =>
      resolveRouteTarget({
        tooth: activeSite?.tooth ?? null,
        siteCenter,
        posePosition: null, // no runs in the product yet — slice 5c wires seated poses
        contentGeneration,
        subject,
        toolActive: false, // no pointer tools on this stage yet — slice 6 wires the veto
        partPreviewActive: false,
        contentIsArch: scanState.kind === "ready",
        modalOpen: false,
      }),
    [activeSite, siteCenter, contentGeneration, subject, scanState.kind],
  );
  const routeKey = routeSignature(routeTarget);

  useEffect(() => {
    if (routeKey === null || routeTarget === null) return;
    if (routedKeyRef.current === routeKey) return;
    // False = the viewer refused (its own backstop veto); not recording the key then
    // means the route is retried on the next change rather than silently dropped.
    if (viewerRef.current?.focusOnSite(routeTarget.center, routeTarget.radiusMm)) {
      routedKeyRef.current = routeKey;
    }
  }, [routeKey, routeTarget]);

  /** "Whole arch" takes effect immediately; "This site" re-arms routing by forgetting
   *  what was last routed to — the demo stage's exact rule. */
  const handleSelectSubject = useCallback((next: StageSubject) => {
    setSubject(next);
    routedKeyRef.current = null;
    if (next === "arch") viewerRef.current?.frameLoadedContent();
  }, []);

  /** A direction preset re-places the camera at the last remembered framing — the
   *  controller's own contract; a click before any anatomy frame exists is a no-op. */
  const handleSelectView = useCallback((view: AnatomyViewId) => {
    viewerRef.current?.setAnatomyView(view);
    setActiveView(view);
  }, []);

  return (
    <MainStageView
      scanState={scanState}
      scanFilename={scanFilename}
      subject={subject}
      siteAvailable={siteCenter !== null}
      activeTooth={activeSite?.tooth ?? null}
      onSelectSubject={handleSelectSubject}
      onSelectView={handleSelectView}
      activeView={activeView}
      viewerSlot={<Viewer3D ref={viewerRef} ariaLabel="3D viewer of the doctor's scan" />}
    />
  );
}
