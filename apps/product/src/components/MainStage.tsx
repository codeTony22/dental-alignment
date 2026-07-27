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

interface SubjectToggleProps {
  readonly subject: StageSubject;
  readonly siteAvailable: boolean;
  readonly onSelect: (subject: StageSubject) => void;
}

/**
 * WHAT THE STAGE IS FRAMED ON — the demo stage's two-subject control, reimplemented.
 * "This site" keeps the camera on the active cap's neighbourhood; "Whole arch" is the
 * operator's way home and it stays put once chosen.
 */
function SubjectToggle({ subject, siteAvailable, onSelect }: SubjectToggleProps) {
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
    <div data-role="stage-subject" role="group" aria-label="What the view is framed on">
      {choices.map((choice) => (
        <button
          key={choice.id}
          type="button"
          aria-pressed={choice.id === subject}
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
  );
}

export interface MainStageViewProps {
  readonly scanState: ScanLoadState;
  readonly scanFilename: string;
  readonly subject: StageSubject;
  readonly siteAvailable: boolean;
  readonly activeTooth: number | null;
  readonly onSelectSubject: (subject: StageSubject) => void;
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
  viewerSlot,
}: MainStageViewProps) {
  return (
    <div data-role="main-stage">
      <div data-role="main-stage-canvas" style={{ minHeight: "24rem", position: "relative" }}>
        {viewerSlot}
      </div>
      <SubjectToggle subject={subject} siteAvailable={siteAvailable} onSelect={onSelectSubject} />
      {scanState.kind === "loading" && (
        <p data-role="stage-status">Loading {scanFilename}…</p>
      )}
      {scanState.kind === "error" && (
        <div data-role="stage-error" role="alert">
          <strong>{scanErrorHeadline(scanState.detail)}</strong> <span>{scanState.detail}</span>
        </div>
      )}
      {scanState.kind === "ready" && subject === "site" && activeTooth !== null && (
        <p data-role="stage-status">Framed on tooth {activeTooth} — front view.</p>
      )}
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
}

/** The container: streams the scan, opens FRONT, routes to the active site. */
export function MainStage({ caseId, scanFilename, sites, markers }: MainStageProps) {
  const viewerRef = useRef<Viewer3DHandle | null>(null);
  const [scanState, setScanState] = useState<ScanLoadState>({ kind: "loading" });
  const [subject, setSubject] = useState<StageSubject>("site");
  /** Bumped when the stage's content is replaced — half the route identity (see siteRouting). */
  const [contentGeneration, setContentGeneration] = useState(0);
  const routedKeyRef = useRef<string | null>(null);

  // The active site: the first with a usable centre. Slices 4/5a add real selection;
  // until then the stage still opens ON a site, which is the demo's default subject.
  const activeSite = useMemo(
    () => sites.find((s) => s.center !== null && s.center.length === 3) ?? null,
    [sites],
  );
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
  useEffect(() => {
    if (scanState.kind !== "ready") return;
    viewerRef.current?.setMarkers(markers ?? []);
  }, [markers, scanState.kind]);

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

  return (
    <MainStageView
      scanState={scanState}
      scanFilename={scanFilename}
      subject={subject}
      siteAvailable={siteCenter !== null}
      activeTooth={activeSite?.tooth ?? null}
      onSelectSubject={handleSelectSubject}
      viewerSlot={<Viewer3D ref={viewerRef} ariaLabel="3D viewer of the doctor's scan" />}
    />
  );
}
