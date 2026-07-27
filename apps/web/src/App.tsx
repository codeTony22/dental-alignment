import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Header } from "./components/Header";
import { Footer } from "./components/Footer";
import { WorkflowRail } from "./components/WorkflowRail";
import { SelectionSummary } from "./components/SelectionSummary";
import { AlignmentActions } from "./components/AlignmentActions";
import { FitByPointsStage } from "./components/FitByPointsStage";
import type { StageId } from "./domain/workflow";
import { nextStage, workflowStages } from "./domain/workflow";
import { CaseSelect } from "./components/CaseSelect";
import { MarkDeclareStage } from "./components/MarkDeclareStage";
import type { MarkModeState } from "./components/ConfirmPanel";
import { ComparePartPane, compareEmptyReason } from "./components/ComparePartPane";
import { selectionColumnHandlers } from "./components/selectionColumnWiring";
import { ResultsTable } from "./components/ResultsTable";
import { GuidancePanel } from "./components/GuidancePanel";
import { FlagsAlerts } from "./components/FlagsAlerts";
import { PackageFileList } from "./components/PackageFileList";
import {
  ViewerControls,
  buildStage1Composite,
  STAGE1_LABEL,
  type StagedComposite,
  type StagedPartSource,
} from "./components/ViewerControls";
import { Legend } from "./components/Legend";
import {
  LibraryBrowser,
  catalogEntryKey,
  type LibraryBrowserState,
} from "./components/LibraryBrowser";
import { PartPreviewChip } from "./components/PartPreviewChip";
import { ControlsHint } from "./components/ControlsHint";
import { ErrorToast } from "./components/ErrorToast";
import { ViewOrientationBar } from "./components/ViewOrientationBar";
import { Viewer3D, type Viewer3DHandle } from "./viewer/Viewer3D";
import type { AnatomyViewId, MarkKind } from "./viewer/sceneController";
import { canonicalFromRaw } from "./viewer/partFrame";
import { PALETTE, type PartRole } from "./viewer/palette";
import { useElapsedSeconds } from "./hooks/useElapsedSeconds";
import {
  alignToCorrespondence,
  alignToMark,
  bestFitSite,
  confirmAlignment,
  fetchCases,
  fetchConstructions,
  fetchImplantPose,
  fetchLibrary,
  fetchLibraryCatalog,
  fetchPartFeatures,
  fetchReliefLimit,
  importPose,
  nudgeRotation,
  proposeSites,
  resetPartFeatures,
  runAutomation,
  savePartFeatures,
  scanUrlFor,
  ApiError,
  bestFitAlreadyOptimal,
} from "./api/client";
import { cachedMeshUrl } from "./api/meshCache";
import type {
  Case,
  ConfirmedSite,
  ConstructionPart,
  ImplantPose,
  LibraryCatalogEntry,
  LibraryCatalogGroup,
  LibraryVariant,
  NudgeRequest,
  ProposeResult,
  RunResult,
  RunSiteResult,
  Vec3,
} from "./domain/types";
import { resolveRouteTarget, routeSignature, type StageSubject } from "./viewer/siteRouting";
import type { LibrarySelection } from "./domain/librarySelection";
import { initialSelection, withActiveSite, withSites } from "./domain/librarySelection";
import { findVariantEntry, missingSelections } from "./domain/librarySelection";
import { authorizeRun, canRun, runBlockers } from "./domain/runGate";
import { achievedGingivalOffset } from "./domain/gingivalOffset";
import type { ReliefLimitState, SiteReliefLimit } from "./domain/reliefLimit";
import { ceilingReadout, reliefLimitKey } from "./domain/reliefLimit";
import { clampedSites } from "./domain/reliefClamp";
import type { RunRefusal } from "./domain/runRefusal";
import { runRefusalFrom } from "./domain/runRefusal";
import { ReliefClampNotice } from "./components/ReliefClampNotice";
import { RunRefusalNotice } from "./components/RunRefusalNotice";
import { VerifyStage } from "./components/VerifyStage";
import { RunActions } from "./components/RunActions";
import type { CatalogFetchState } from "./components/SelectionColumn";
import {
  BEST_FIT_DEFAULT_DIAMETER_MM,
  buildRunReport,
  captureNear,
  describeAlignToMark,
  describeBestFit,
  describeNotchResidual,
  findDuplicateTeeth,
  formatRunTimestamp,
  isRunStale,
  marksSignatureFor,
  subsamplePoints,
  translateMark,
  undeclaredSiteNumbers,
  withCacheBust,
} from "./domain/types";
import { ToothChart } from "./components/ToothChart";
import {
  addSiteBlockedReason as blockedReasonForAddSite,
  AUTO_TOOTH_NUMBER_DEFAULT,
  chartSitesFrom,
  nextToothNumber,
} from "./domain/toothChart";
import { PoseTransferPanel, type PoseImportState } from "./components/PoseTransferPanel";
import {
  buildPoseTransfer,
  canImport,
  importCompatibility,
  parsePoseTransfer,
  poseTransferFilename,
  serializePoseTransfer,
} from "./domain/poseTransfer";
import type { DraftFeature, PartAnnotation, PartFeatureKind } from "./domain/partFeatures";
import {
  draftKey,
  draftsAreDirty,
  draftsFrom,
  placeDraft,
  readClick,
  removeDraft,
  toFeatureInputs,
} from "./domain/partFeatures";
import type { CorrespondencePair, CorrespondenceResidual } from "./domain/correspondence";
import {
  describeCorrespondence,
  featurePair,
  freePair,
  sitePartKey,
  withPair,
  withoutPair,
} from "./domain/correspondence";
import type { PartAnnotatorContext, PartAnnotatorState } from "./components/PartAnnotator";
import type { CorrespondenceControls, CorrespondenceState } from "./components/CorrespondencePanel";
import "./styles.css";

const MARKER_RADIUS_MM = 1.5;

/**
 * The ACTIVE library-part preview (a LIBRARY BROWSER card), or null when the viewer shows the
 * scan/a composite. ONE preview at a time, owned by exactly one catalog card (the browser is
 * case-independent, so no confirm row owns it). The step-2 rows' "view part" swap that used to
 * share this state is RETIRED (client, 2026-07-26: "we should still see side by side the scan
 * and the model") — the docked ComparePartPane shows a row's variant BESIDE the scan instead of
 * replacing it; only the library browser's header preview keeps the old swap behaviour. The
 * catalog fields are snapshotted here so the viewer chip stays self-describing even while the
 * library refetches. `loading` covers both the initial load and a live card switch.
 */
interface ActivePartPreview {
  readonly catalogKey: string;
  readonly variant: string;
  readonly rimDiameterMm: number | null;
  readonly heightMm: number | null;
  readonly loading: boolean;
}

/** What startPartPreview needs from a previewable part (the cross-model LibraryCatalogEntry). */
interface PreviewablePart {
  readonly variant: string;
  readonly rimDiameterMm: number | null;
  readonly heightMm: number | null;
  readonly meshUrl: string;
}

/**
 * Hand a generated file to the browser's own download. The ONE piece of file IO in this app,
 * kept at module scope (not in a domain module) because it is pure platform plumbing — the
 * document it writes is built and serialized by domain/poseTransfer, which stays testable.
 */
function downloadTextFile(filename: string, contents: string): void {
  const url = URL.createObjectURL(new Blob([contents], { type: "application/json" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

/** Convert raw [x, y, z] triples (as returned by the viewer's brush patch) into domain Vec3s, dropping malformed entries. */
function toVec3Points(raw: readonly number[][]): Vec3[] {
  const result: Vec3[] = [];
  for (const p of raw) {
    const [x, y, z] = p;
    if (x !== undefined && y !== undefined && z !== undefined) {
      result.push([x, y, z]);
    }
  }
  return result;
}

export default function App() {
  const viewerRef = useRef<Viewer3DHandle>(null);
  // stale-response guard: async propose/run resolutions for a PREVIOUS case must never
  // clobber the currently selected case's state (switching cases mid-run exposed this)
  const activeCaseIdRef = useRef<string | null>(null);

  /**
   * WHICH STAGE'S PANEL THE WORK COLUMN SHOWS. It is navigation, not a gate: every stage's
   * reachability is judged by domain/workflow against the case, and the run gate itself is
   * enforced at compile time (domain/runGate) regardless of where the operator happens to be.
   * The old `step` number was both at once — a render gate AND a progress read-out — which is
   * why the rail could show four completed steps over a case with no cap declared.
   */
  const [stage, setStage] = useState<StageId>("case");

  /**
   * Bumped every time the stage's CONTENT settles — the scan loaded, a composite loaded, a part
   * preview started or ended. It is the routing effect's trigger, and it has to be this rather
   * than a state change: every content load ends by re-framing the camera itself (loadStl →
   * frameOnBoundingSphere → setAnatomyView("front")), so a route computed before the mesh
   * arrives is silently overwritten by the load that follows it. Routing must run AFTER.
   */
  const [stageContentVersion, setStageContentVersion] = useState(0);
  const bumpStageContent = useCallback(() => setStageContentVersion((v) => v + 1), []);

  /**
   * The results drawer over the 3D stage. Open by default once a run lands (the operator asked
   * for those numbers), collapsible to a bar because the client's first complaint about this
   * screen was that the 3D never got to be big. It docks to the STAGE, not the work column: a
   * fifteen-column table in a 400px rail would scroll sideways forever.
   */
  const [drawerOpen, setDrawerOpen] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [cases, setCases] = useState<Case[]>([]);
  const [loadingCases, setLoadingCases] = useState(true);
  const [selectedCase, setSelectedCase] = useState<Case | null>(null);
  const [scanProgress, setScanProgress] = useState<number | null>(null);

  const [proposeBusy, setProposeBusy] = useState(false);
  const [proposeResult, setProposeResult] = useState<ProposeResult | null>(null);
  // Default OFF: the doctor's raw scan must stay clean until explicitly asked to show the
  // orange proposal markers. Reset to OFF on every case switch.
  const [showProposalMarkers, setShowProposalMarkers] = useState(false);
  // Mirrors showProposalMarkers for handleRunDetection's response handler: the toggle is not
  // disabled while a detection request is in flight, so the button can flip mid-flight — a
  // value captured in the async callback's closure at CLICK time would go stale by RESPONSE
  // time. Read the ref instead of the closure so the response always reflects the toggle's
  // state at the moment it lands, not the moment the request was fired.
  const showProposalMarkersRef = useRef(showProposalMarkers);
  useEffect(() => {
    showProposalMarkersRef.current = showProposalMarkers;
  }, [showProposalMarkers]);

  const [confirmedSites, setConfirmedSites] = useState<ConfirmedSite[]>([]);
  // Mirrors confirmedSites for handleStartMark's onPlaced callback: that callback is created
  // once (empty useCallback deps — enterMarkMode is armed long before the click resolves) and
  // needs to read the CURRENT row's prior marks at click-resolution time to decide whether to
  // translate the rim, but a functional setConfirmedSites updater runs later during re-render,
  // NOT synchronously inside the setConfirmedSites call — a value written from inside the
  // updater is not readable right after the call returns (and in StrictMode the updater may run
  // twice). Read this ref BEFORE calling setConfirmedSites instead, same pattern as
  // showProposalMarkersRef above.
  const confirmedSitesRef = useRef(confirmedSites);
  useEffect(() => {
    confirmedSitesRef.current = confirmedSites;
  }, [confirmedSites]);
  const [brushingIndex, setBrushingIndex] = useState<number | null>(null);
  const [markMode, setMarkMode] = useState<MarkModeState | null>(null);
  // Which row is currently collecting multi-click rim-BORDER points, if any — mirrors
  // brushingIndex's pattern (a row-scoped "in progress" mode with its own Done/Cancel banner).
  const [rimPointsIndex, setRimPointsIndex] = useState<number | null>(null);
  const [library, setLibrary] = useState<LibraryVariant[]>([]);
  const [libraryLoading, setLibraryLoading] = useState(false);

  // ---- THE LIBRARY SELECTION (client directive 2026-07-25: "the lab chooses, the
  // software never guesses"). It lives HERE, not inside the verify dialog, because BOTH routes
  // run with it: the dialog's Process and step 4's quick "Run automation". Two copies could
  // disagree about what the lab chose, and only one of them would be in the audit. ----
  const [selection, setSelection] = useState<LibrarySelection>(() =>
    initialSelection({ suggestedModel: null, suggestedConstruction: null, jaw: "upper", sites: [] }),
  );
  const [verifyOpen, setVerifyOpen] = useState(false);
  const [constructions, setConstructions] = useState<ConstructionPart[]>([]);
  const [constructionsState, setConstructionsState] = useState<CatalogFetchState>("loading");
  const [constructionsError, setConstructionsError] = useState<string | null>(null);

  const loadConstructions = useCallback(() => {
    setConstructionsState("loading");
    setConstructionsError(null);
    fetchConstructions()
      .then((parts) => {
        setConstructions(parts);
        setConstructionsState("ready");
      })
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 404) {
          // the RUNNING backend predates GET /api/constructions — the column's restart hint
          setConstructionsState("unavailable");
        } else {
          setConstructionsState("error");
          setConstructionsError(
            err instanceof ApiError ? err.message : "Failed to load the construction parts.",
          );
        }
      });
  }, []);

  useEffect(() => {
    loadConstructions();
  }, [loadConstructions]);

  // ---- THE RELIEF CEILING, FETCHED AT SELECTION TIME (client, 2026-07-25: "end-to-end
  // automation must complete"). The thin-wall gate is correct but fires at the END of the
  // pipeline; the same physics is available per (construction part x cap variant) up front, and
  // the operator should meet it while choosing the number, not after a failed run.
  //
  // Keyed by the pair, not by the site: two sites declaring the same cap are ONE lookup. The
  // `requested` ref is what stops the effect re-firing on its own state write — a ceiling is a
  // property of two files on disk, so within a session it is fetched once and kept. ----
  const [reliefLimits, setReliefLimits] = useState<ReadonlyMap<string, ReliefLimitState>>(new Map());
  const reliefLimitsRequestedRef = useRef<Set<string>>(new Set());

  const putReliefLimit = useCallback((key: string, state: ReliefLimitState) => {
    setReliefLimits((prev) => new Map(prev).set(key, state));
  }, []);

  useEffect(() => {
    const construction = selection.constructionPathId;
    const model = selection.model;
    if (construction === null || model === null) return;
    const variants = new Set(
      selection.sites.map((site) => site.variantId).filter((v): v is string => v !== null),
    );
    for (const variant of variants) {
      const key = reliefLimitKey(construction, model, variant);
      if (reliefLimitsRequestedRef.current.has(key)) continue;
      reliefLimitsRequestedRef.current.add(key);
      putReliefLimit(key, { kind: "loading" });
      fetchReliefLimit(construction, model, variant)
        .then((limit) => putReliefLimit(key, { kind: "ready", limit }))
        .catch((err: unknown) => {
          // A 404 is the RUNNING backend predating the endpoint — a restart hint beside the
          // input, never a toast: the run still clamps to the safe maximum and reports it.
          if (err instanceof ApiError && err.status === 404) {
            putReliefLimit(key, { kind: "unavailable" });
            return;
          }
          putReliefLimit(key, {
            kind: "error",
            message: err instanceof ApiError ? err.message : "the lookup failed",
          });
        });
    }
    // `reliefLimits` is a dependency ON PURPOSE, and the ref guard is what makes it safe: without
    // it, `retryReliefLimits` (which empties both the map and the guard) would clear the read-out
    // and never re-ask, since nothing else in the deps moves on a retry. Every re-run that is not
    // a retry finds its keys already claimed and does nothing.
  }, [selection, reliefLimits, putReliefLimit]);

  /** Re-ask for every ceiling (the column's Retry, and the dialog's catalog retry): drop what we
   *  learned so an "unavailable" verdict clears itself once the API is restarted. */
  const retryReliefLimits = useCallback(() => {
    reliefLimitsRequestedRef.current = new Set();
    setReliefLimits(new Map());
  }, []);

  /**
   * One selection change, applied in BOTH directions: a per-site cap variant chosen on EITHER
   * SelectionColumn mount is the same declaration step 2's table records, so it is written
   * straight back into the confirm rows (which is what the run actually submits as
   * `declared_variant`). Without this the
   * operator could choose 7030 in the dialog and ship whatever the row still said.
   *
   * CLEARING propagates too, and must: switching the implant system drops every chosen variant
   * (a zimmer id is not a neodent part), so the row's declaration goes with it — otherwise the
   * stale id would be re-adopted by the sync effect below and shipped against the WRONG library.
   * The rows are returned unchanged when nothing moved, so this cannot ping-pong with that effect.
   */
  const handleSelectionChange = useCallback((next: LibrarySelection) => {
    setSelection(next);
    setConfirmedSites((prev) => {
      let changed = false;
      const rows = prev.map((row) => {
        const site = next.sites.find((s) => s.tooth === row.tooth);
        if (!site) return row;
        const declared = row.declaredVariant ?? null;
        if (site.variantId === declared) return row;
        changed = true;
        return { ...row, declaredVariant: site.variantId ?? undefined };
      });
      return changed ? rows : prev;
    });
  }, []);

  // The confirm rows are the source of truth for WHICH sites exist: a row added, removed or
  // re-numbered in step 2 re-keys the selection (by tooth), carrying each site's choice and
  // review with it. Functional update — this must not re-run when the selection itself changes.
  useEffect(() => {
    setSelection((prev) => withSites(prev, confirmedSites));
  }, [confirmedSites]);
  // The active library-browser preview (see ActivePartPreview). The ref is written SYNCHRONOUSLY
  // alongside every state write (applyPartPreview below) — not via a post-render effect like
  // the other mirrors — because two card clicks can land between commits (rapid flips) and the
  // second must see the FIRST's retarget, or an A→B→A flip would early-return against A and
  // leave B's pending load to win.
  const [partPreview, setPartPreview] = useState<ActivePartPreview | null>(null);
  const partPreviewRef = useRef<ActivePartPreview | null>(null);
  const applyPartPreview = useCallback((next: ActivePartPreview | null) => {
    partPreviewRef.current = next;
    setPartPreview(next);
  }, []);
  // Stale-load guard for preview meshes: bumped whenever the preview target changes or the
  // preview ends, so an in-flight loadStl resolution for a SUPERSEDED part can never flip the
  // chip's loading state (same monotonic-epoch pattern as runEpochRef below, for previews).
  const previewLoadEpochRef = useRef(0);
  const cancelPendingPreviewLoads = useCallback(() => {
    previewLoadEpochRef.current += 1;
  }, []);
  // The signature of the marks the MOST RECENT run actually submitted — null before any run
  // (or right after a case switch resets it). Compared against the CURRENT marksSignature via
  // isRunStale() to drive the "marks changed — results are for the previous marks" banner. state
  // (not a ref): the banner/results-dimming must re-render when this changes, and it changes at
  // well-defined points only (a run's response landing), not on every keystroke.
  const [lastRunMarksSignature, setLastRunMarksSignature] = useState<string | null>(null);
  // recomputeBusy drives the "recomputing…" notice for the EXPLICIT recompute action only
  // (Recompute-alignment button or Confirm All while stale) — there is no debounce/timer to
  // manage any more (see the removed auto-recompute effect this replaced): runBusy already
  // covers the request lifecycle, this is purely which copy to show while runBusy is true.
  const [recomputeBusy, setRecomputeBusy] = useState(false);

  const [runBusy, setRunBusy] = useState(false);
  const [runResult, setRunResult] = useState<RunResult | null>(null);
  /**
   * THE LAST RUN'S REFUSAL, as a structured record rather than a toast (client, 2026-07-25).
   * The gingival-relief gate refuses the whole package when the relief would leave the screw
   * channel without a measurable wall — correct, and a sentence the operator has to READ: which
   * tooth, which part, what to change. A toast that fades cannot carry it. null = no refusal
   * standing; cleared when a new run starts and when the run artifacts are cleared.
   */
  const [runRefusal, setRunRefusal] = useState<RunRefusal | null>(null);
  // Tooth whose operator rotation-nudge request is in flight (disables that row's control) —
  // per-tooth rather than a single boolean so the other rows' controls stay honest.
  const [nudgeBusyTooth, setNudgeBusyTooth] = useState<number | null>(null);
  // Tooth whose doctor confirm/retract request is in flight (verification panel) — same
  // per-tooth pattern as nudgeBusyTooth, for the same honesty reason.
  const [confirmBusyTooth, setConfirmBusyTooth] = useState<number | null>(null);
  // Tooth whose one-shot ALIGN-TO-MARK trench click is currently armed on the 3D scan (null
  // when none) — one at a time, like the single-shot mark mode whose picking it reuses. The
  // ref mirrors it for the global Escape handler (same pattern as markModeRef below).
  const [markTrenchTooth, setMarkTrenchTooth] = useState<number | null>(null);
  const markTrenchToothRef = useRef<number | null>(null);
  useEffect(() => {
    markTrenchToothRef.current = markTrenchTooth;
  }, [markTrenchTooth]);

  // ---- TOOTH CHART (RealGUIDE screenshot parity, 2026-07-25) ----
  // Their "automated tooth number increasing" toggle. A workflow preference, so it lives here
  // rather than inside the chart — it survives a case switch, and the number it would use is
  // shown on the add button before anything is created.
  const [autoToothNumber, setAutoToothNumber] = useState(AUTO_TOOTH_NUMBER_DEFAULT);
  // The tooth whose NEW site is waiting for its position on the scan (null when nothing is
  // pending). Clicking an empty tooth does not create a site — a site needs a centre on the
  // arch — it arms a one-shot pick, exactly like every other marking tool here; the ref mirrors
  // it for the global Escape handler, same idiom as markTrenchToothRef above.
  const [addSiteTooth, setAddSiteTooth] = useState<number | null>(null);
  const addSiteToothRef = useRef<number | null>(null);
  useEffect(() => {
    addSiteToothRef.current = addSiteTooth;
  }, [addSiteTooth]);

  // ---- POSE TRANSFER ----
  // The seated poses the triad pass already fetched, kept instead of discarded: they are what
  // an export is MADE of, so exporting costs no extra request and can never disagree with the
  // triads on screen. Reset with every other run-scoped field.
  const [sitePoses, setSitePoses] = useState<ReadonlyMap<number, ImplantPose>>(new Map());
  const [importState, setImportState] = useState<PoseImportState>({ kind: "idle" });
  // The last APPLIED align-to-mark outcome line ("rotated +38.0° — code feature on your
  // mark; codes now read −1.4°"), shown under that tooth's rotation control until the next
  // arm/case switch. Refusals surface as the error toast instead (the server's own sentence).
  const [alignMarkNotice, setAlignMarkNotice] = useState<{ tooth: number; text: string } | null>(null);
  // Client-side "when the response landed" — the backend doesn't send a run timestamp, and the
  // client's own clock at the moment the result arrives is exactly what the doctor needs for
  // "when did I run this" (per-run metrics tracking on the client's side). Set alongside
  // setRunResult in handleRunAutomation; reset to null on case switch like every other run-scoped field.
  const [lastRunAt, setLastRunAt] = useState<Date | null>(null);
  // Belt-and-braces cache-busting token (see withCacheBust): a fresh Date.now() every time a run
  // response lands, appended as ?v=<token> to every files_base package-file URL the viewer
  // fetches. The server now sends Cache-Control: no-store, but an ALREADY-OPEN tab can still be
  // holding a browser-cached response from an earlier run's identically-named file — a new query
  // string forces a genuinely new fetch regardless of what the browser cached. null before any
  // run (nothing to bust yet); reset to null on case switch like every other run-scoped field.
  const [runVersion, setRunVersion] = useState<number | null>(null);
  // Brief "copied ✓" confirmation on the "Copy run report" button — cleared on a timer, not
  // persisted; purely a transient UI acknowledgement, so a plain useState (not ref-synced) is fine.
  const [reportCopied, setReportCopied] = useState(false);
  const [activeViewLabel, setActiveViewLabel] = useState<string | null>(null);
  const [legendRoles, setLegendRoles] = useState<PartRole[]>([]);
  // Whether the viewer currently shows the CLEAN INPUT SCAN (true) or something else — a
  // composite, its legacy merged fallback, or a library-part preview (false). Drives
  // ensureCleanScanView: marking tools must never arm over a non-scan view (client ask
  // 2026-07-14 — and the measured cause of the redo's bad border click: stage 1's green cap
  // occludes the true rim border, stage 2's arch has the cap region cut out entirely, so
  // clicks land past the hole/occlusion — high and outward on the slope). A ref, not state:
  // only the async tool-arming handlers read it, nothing renders from it.
  const viewIsScanRef = useRef(true);

  const proposeElapsedS = useElapsedSeconds(proposeBusy);
  const runElapsedS = useElapsedSeconds(runBusy);

  useEffect(() => {
    let cancelled = false;
    fetchCases()
      .then((result) => {
        if (cancelled) return;
        setCases(result);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setErrorMessage(err instanceof ApiError ? err.message : "Failed to load cases.");
      })
      .finally(() => {
        if (!cancelled) setLoadingCases(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSelectCase = useCallback(async (caseItem: Case) => {
    activeCaseIdRef.current = caseItem.id;
    // pessimistic until the new case's scan finishes loading below — a failed load must not
    // leave the previous case's "scan is on screen" verdict behind
    viewIsScanRef.current = false;
    bumpStageContent();
    setSelectedCase(caseItem);
    setProposeResult(null);
    setShowProposalMarkers(false);
    setRunResult(null);
    setLastRunAt(null);
    setRunVersion(null);
    setReportCopied(false);
    setActiveViewLabel(null);
    setLegendRoles([]);
    setRecomputeBusy(false);
    // runResult is cleared above (same render) — with it null, isRunStale has nothing to compare
    // against and the banner cannot render regardless of lastRunMarksSignature, but reset it too
    // for a clean start against whatever the new case's first run submits.
    setLastRunMarksSignature(null);
    setConfirmedSites(
      caseItem.suggestedSites.map((s) => ({
        tooth: s.tooth,
        center: s.center,
        declaredVariant: s.declaredVariant ?? undefined,
        centerMark: s.centerMark ?? undefined,
        rimMark: s.rimMark ?? undefined,
      })),
    );
    // The case's name-matched SUGGESTIONS are preselected — visibly, and still only binding once
    // the operator sends them back (the backend refuses a run that names nothing). A case that
    // matched nothing starts empty, which is exactly the state that must block a run rather than
    // being filled in for the lab.
    setSelection(
      initialSelection({
        suggestedModel: caseItem.suggestedModel,
        suggestedConstruction: caseItem.suggestedConstruction,
        jaw: caseItem.jaw,
        sites: caseItem.suggestedSites.map((s) => ({
          tooth: s.tooth,
          declaredVariant: s.declaredVariant,
        })),
      }),
    );
    setVerifyOpen(false);
    // painted patches / marks are tied to the previous case's mesh — never carry them across a case switch
    setBrushingIndex(null);
    setMarkMode(null);
    setRimPointsIndex(null);
    // an armed trench click (and its outcome line) belongs to the previous case's run
    setMarkTrenchTooth(null);
    setAlignMarkNotice(null);
    setBestFitNotice(null);
    setBestFitConfirmation(null);
    // a pending new-site placement, the previous case's seated poses, and any staged pose file
    // all describe the case being left
    setAddSiteTooth(null);
    setSitePoses(new Map());
    setImportState({ kind: "idle" });
    // a library-browser part preview describes no case, but its mesh occupies the stage the
    // new case's scan is about to claim — drop it (and discard any in-flight/debounced load)
    cancelPendingPreviewLoads();
    applyPartPreview(null);
    viewerRef.current?.disableBrush();
    viewerRef.current?.exitMarkMode();
    viewerRef.current?.exitPointPick();
    viewerRef.current?.cancelRimPoints();
    viewerRef.current?.clearAllBrushPatches();
    viewerRef.current?.clearAllSiteMarkers();
    viewerRef.current?.clearAllRimPoints();
    viewerRef.current?.clearAllPoseTriads();
    // the cap library is per-model (varies by case) — reset and refetch once per case switch
    setLibrary([]);
    setLibraryLoading(true);
    setStage("mark");
    setScanProgress(0);

    const caseId = caseItem.id;
    // the cap library itself is fetched by the model-driven effect below (it follows the
    // operator's chosen implant system, not just the case's suggestion)

    try {
      await viewerRef.current?.loadStl(scanUrlFor(caseItem.id), {
        fit: "wide",
        onProgress: (fraction) => setScanProgress(fraction),
        // the scan is an arch: compute its anatomical frame and open FACING THE FRONT of the
        // mouth (the old fixed corner view faced the back wall on tilted scanner frames)
        anatomy: true,
      });
      if (activeCaseIdRef.current !== caseId) return; // stale — user switched cases again
      viewIsScanRef.current = true;
      bumpStageContent();
      // Prefill: draw suggested_sites' center_mark/rim_mark marker spheres now that the scan
      // mesh is actually loaded (placing them earlier would have nothing to raycast/frame against).
      caseItem.suggestedSites.forEach((site, index) => {
        if (site.centerMark) {
          viewerRef.current?.setSiteMarker(index, "center", site.centerMark);
        }
        if (site.rimMark) {
          viewerRef.current?.setSiteMarker(index, "rim", site.rimMark);
        }
      });
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to load the scan.");
    } finally {
      setScanProgress(null);
    }
  }, [applyPartPreview, cancelPendingPreviewLoads]);

  /**
   * The step-2 cap picker's list follows THE CHOSEN IMPLANT SYSTEM, not the case's folder name:
   * switching the system (on either SelectionColumn mount) re-fetches the sizes for that system.
   * With no system chosen there is nothing to list — the picker says so (see ConfirmPanel's
   * hint) rather than showing another system's caps.
   */
  useEffect(() => {
    const caseId = selectedCase?.id ?? null;
    if (caseId === null) return undefined;
    const model = selection.model;
    if (model === null) {
      setLibrary([]);
      setLibraryLoading(false);
      return undefined;
    }
    let cancelled = false;
    setLibraryLoading(true);
    fetchLibrary(caseId, model)
      .then((result) => {
        if (cancelled || activeCaseIdRef.current !== caseId) return;
        setLibrary(result);
      })
      .catch((err: unknown) => {
        if (cancelled || activeCaseIdRef.current !== caseId) return;
        setErrorMessage(err instanceof ApiError ? err.message : "Failed to load the cap library.");
      })
      .finally(() => {
        if (cancelled || activeCaseIdRef.current !== caseId) return;
        setLibraryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedCase?.id, selection.model]);

  const handleRunDetection = useCallback(
    async (fresh: boolean) => {
      if (!selectedCase) return;
      const caseId = selectedCase.id;
      setProposeBusy(true);
      try {
        const result = await proposeSites(caseId, fresh);
        if (activeCaseIdRef.current !== caseId) return; // stale — user switched cases
        setProposeResult(result);
        // Proposals are off by default — the raw scan stays clean until the doctor explicitly
        // asks to see them via the "view proposals" toggle. A fresh detection pass replaces
        // proposeResult but must not silently turn markers on if they were already visible —
        // it also must not silently turn them off, so just redraw with whatever is current.
        // Read the REF, not the closed-over showProposalMarkers state: the toggle stays enabled
        // while this request is in flight, so the value at click time can be stale by the time
        // the response lands — the ref always reflects the toggle's state right now.
        if (showProposalMarkersRef.current) {
          viewerRef.current?.setMarkers(
            result.proposals.map((p) => ({ center: p.center, radiusMm: MARKER_RADIUS_MM })),
          );
        }
      } catch (err) {
        setErrorMessage(err instanceof ApiError ? err.message : "Detection failed.");
      } finally {
        setProposeBusy(false);
      }
    },
    [selectedCase],
  );

  const handleToggleProposalMarkers = useCallback(() => {
    setShowProposalMarkers((current) => {
      const next = !current;
      if (next && proposeResult) {
        viewerRef.current?.setMarkers(
          proposeResult.proposals.map((p) => ({ center: p.center, radiusMm: MARKER_RADIUS_MM })),
        );
      } else {
        viewerRef.current?.clearMarkers();
      }
      return next;
    });
  }, [proposeResult]);

  const handleChangeTooth = useCallback((index: number, tooth: number) => {
    setConfirmedSites((prev) =>
      prev.map((site, i) => (i === index ? { ...site, tooth } : site)),
    );
  }, []);

  /**
   * Monotonic run epoch, bumped by clearRunArtifacts: a run response that resolves AFTER the
   * doctor started re-marking (which cleared the results) must not land its now-stale results
   * back on screen — same stale-response pattern as activeCaseIdRef, for time instead of case.
   */
  const runEpochRef = useRef(0);

  /**
   * Clear every artifact of the previous run — results table, guidance, flags, stage buttons,
   * package list, report state, pose triads — so re-marking starts FRESH (client ask
   * 2026-07-15: "when clicking any of the signal buttons in step 3 if automations have ran we
   * need to clear and just start fresh"). Editing marks makes the previous run's output about
   * a gesture that no longer exists; dimming it behind a stale banner still left it competing
   * for attention while the doctor re-marks. Committed marker spheres/border dots/brush
   * patches are NOT touched — they are the doctor's INPUTS, not run output. Safe to call when
   * no run exists (every reset is a no-op then).
   */
  const clearRunArtifacts = useCallback(() => {
    runEpochRef.current += 1;
    setRunResult(null);
    // the refusal described a run of the marks being cleared — it goes with them
    setRunRefusal(null);
    setLastRunAt(null);
    setRunVersion(null);
    setLastRunMarksSignature(null);
    setReportCopied(false);
    setActiveViewLabel(null);
    setLegendRoles([]);
    setRecomputeBusy(false);
    // the align-to-mark control lives on the results rows being cleared — disarm any
    // pending trench click and drop its outcome line with them
    setMarkTrenchTooth(null);
    setAlignMarkNotice(null);
    // …and the chart's pending new-site placement, for the same reason: the exitPointPick
    // below kills whichever one-shot was armed, so every one-shot's state must follow it
    // down or its banner outlives the click it is still asking for (verifier, 2026-07-25)
    setAddSiteTooth(null);
    // the best-fit outcome line (and the "already optimal" confirmation) describes a seat
    // this clear is throwing away
    setBestFitNotice(null);
    setBestFitConfirmation(null);
    // the seated poses (and any pose file staged against them) belong to the run being cleared
    setSitePoses(new Map());
    setImportState({ kind: "idle" });
    viewerRef.current?.exitPointPick();
    viewerRef.current?.clearAllPoseTriads();
  }, []);

  /**
   * Restore the CLEAN INPUT SCAN before a marking tool arms, when the viewer is currently
   * showing anything else (client ask 2026-07-14: "when redoing the confirmation step 3 marks
   * we have to show a clean input scan again"). The measured failure this prevents: after a
   * run, the post-run reveal leaves a composite on screen — stage 1's aligned green cap
   * OCCLUDES the scanned cap's true rim border, and stage 2's arch part has the cap region
   * cut out — so redo border clicks aimed at the visible edge land past the rim on the slope
   * (the 276794487 redo's one bad click: 0.89mm high/outward → 12° tilted seat). Committed
   * marker spheres/border dots/brush patches survive the reload by design (see loadStl's doc).
   * Returns false when the scan could not be restored (load failure or case switched away) —
   * callers must NOT arm their tool then.
   */
  const ensureCleanScanView = useCallback(async (): Promise<boolean> => {
    if (viewIsScanRef.current) return true;
    const caseId = activeCaseIdRef.current;
    if (caseId === null) return false;
    // Whatever was on screen — a composite OR a library-part preview — is being replaced by
    // the scan: end the preview state up front (chip down immediately, any in-flight/debounced
    // part load discarded) so the overlay never claims "viewing library part" over the scan.
    // This is the ONE restore path (the chip's Back button, the row toggle, and Escape all
    // funnel here) — the same reload that marking tools already rely on.
    cancelPendingPreviewLoads();
    applyPartPreview(null);
    try {
      await viewerRef.current?.loadStl(scanUrlFor(caseId), { fit: "wide", anatomy: true });
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Failed to reload the scan.");
      return false;
    }
    if (activeCaseIdRef.current !== caseId) return false; // stale — user switched cases
    viewIsScanRef.current = true;
    bumpStageContent();
    setActiveViewLabel(null);
    setLegendRoles([]);
    // loadStl cleared the orange proposal markers with the old scene — keep the toggle honest
    setShowProposalMarkers(false);
    return true;
  }, [applyPartPreview, cancelPendingPreviewLoads]);

  /**
   * The single "back to the actual scan" action for a library-part preview (client ask
   * 2026-07-23) — the chip's Back button, the active row's "viewing ✓" toggle, and Escape all
   * call THIS, and this just defers to ensureCleanScanView: the exact restore path the marking
   * tools already use, so the reload removes ONLY the previewed part (committed marker spheres,
   * border dots, and brush patches survive a loadStl by design — see its doc).
   */
  const handleExitPartPreview = useCallback(() => {
    void ensureCleanScanView();
  }, [ensureCleanScanView]);

  /**
   * Load (or live-switch to) a library part as the viewer's single mesh (construction-blue,
   * close fit). Owned by a library-browser card (catalogKey) — the ONLY remaining swap path
   * (2026-07-26): the step-2 rows compare through the docked pane instead. The part loads
   * ALONE on the stage whether or not a case scan was on it (the sceneController's loadStl
   * replaces the whole scene, so no-case previews need nothing special). Preview state goes up
   * FIRST (chip renders immediately, loading=true) and resolves through the epoch guard, so a
   * superseded load (card switched again, preview exited, case switched) can never flip the
   * chip's state afterwards. Mesh bytes come through cachedMeshUrl — one fetch per part per
   * session, so flipping between cards/tabs is instant after the first view. On failure the
   * preview ends and the scan comes back when there is one — never a silent black scene with a
   * lying chip.
   */
  const startPartPreview = useCallback(
    (target: { catalogKey: string }, entry: PreviewablePart) => {
      const caseId = activeCaseIdRef.current;
      cancelPendingPreviewLoads(); // this load supersedes any pending/in-flight preview load
      const epoch = previewLoadEpochRef.current;
      // loadStl clears the controller's orange proposal markers as a side effect of replacing
      // the scene's mesh — sync the toggle off too, or the button would keep reading "hide
      // proposals" while nothing is actually drawn (and a second press would "hide"
      // already-cleared markers, silently turning them back on instead).
      setShowProposalMarkers(false);
      // a part preview replaces the scan on screen — marking tools must restore the scan first
      viewIsScanRef.current = false;
      bumpStageContent();
      applyPartPreview({
        catalogKey: target.catalogKey,
        variant: entry.variant,
        rimDiameterMm: entry.rimDiameterMm,
        heightMm: entry.heightMm,
        loading: true,
      });
      void (async () => {
        try {
          const url = await cachedMeshUrl(entry.meshUrl);
          if (previewLoadEpochRef.current !== epoch || activeCaseIdRef.current !== caseId) return;
          await viewerRef.current?.loadStl(url, { color: PALETTE.construction, fit: "close" });
          if (previewLoadEpochRef.current !== epoch || activeCaseIdRef.current !== caseId) return;
          const current = partPreviewRef.current;
          if (
            current !== null &&
            current.catalogKey === target.catalogKey &&
            current.variant === entry.variant
          ) {
            applyPartPreview({ ...current, loading: false });
          }
        } catch (err) {
          if (previewLoadEpochRef.current !== epoch || activeCaseIdRef.current !== caseId) return;
          setErrorMessage(err instanceof Error ? err.message : "Failed to load the library part.");
          if (activeCaseIdRef.current !== null) {
            void ensureCleanScanView(); // also ends the preview state (see its doc)
          } else {
            // no scan to restore (library-browser preview before any case) — just end the
            // preview so the chip never claims a part that failed to load
            cancelPendingPreviewLoads();
            applyPartPreview(null);
          }
        }
      })();
    },
    [applyPartPreview, cancelPendingPreviewLoads, ensureCleanScanView],
  );

  /**
   * Record a row's declared variant. The old preview-follow behaviour (live-switching a part
   * SWAPPED into the main stage) is retired with the swap itself (2026-07-26): "visibility of
   * the parts while choosing" is now the docked compare pane's job, and it follows the ACTIVE
   * site's declaration through the selection-sync effect above — a changed declaration reaches
   * the pane without this handler touching any preview state.
   */
  const handleChangeDeclaredVariant = useCallback((index: number, declaredVariant: string) => {
    setConfirmedSites((prev) =>
      prev.map((site, i) => (i === index ? { ...site, declaredVariant } : site)),
    );
  }, []);

  // ---- LIBRARY BROWSER (client ask 2026-07-23: the WHOLE shelf, classified, choosable) ----
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [catalogState, setCatalogState] = useState<"idle" | LibraryBrowserState>("idle");
  const [catalogGroups, setCatalogGroups] = useState<LibraryCatalogGroup[]>([]);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [activeLibraryModel, setActiveLibraryModel] = useState<string | null>(null);

  const loadCatalog = useCallback(() => {
    setCatalogState("loading");
    setCatalogError(null);
    fetchLibraryCatalog()
      .then((groups) => {
        setCatalogGroups(groups);
        setCatalogState("ready");
        // keep the user's tab across a reload; default to the first system on first load
        setActiveLibraryModel((current) =>
          current !== null && groups.some((g) => g.model === current)
            ? current
            : groups[0]?.model ?? null,
        );
      })
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 404) {
          // the RUNNING backend predates GET /api/library — the panel's restart hint, not a toast
          setCatalogState("unavailable");
        } else {
          setCatalogState("error");
          setCatalogError(err instanceof ApiError ? err.message : "Failed to load the part library.");
        }
      });
  }, []);

  /**
   * The catalog is needed as soon as a case is open, not only when the library dialog is
   * (2026-07-26): step 2's SelectionColumn lists these groups as system cards, and an empty list
   * on the step where variants are declared is exactly the gap the client reported. One fetch per
   * case, and never a re-fetch over a catalog already in hand.
   */
  useEffect(() => {
    if (!selectedCase) return;
    if (catalogState === "ready" || catalogState === "loading") return;
    loadCatalog();
  }, [selectedCase, catalogState, loadCatalog]);

  /** The shared Retry for BOTH SelectionColumn mounts (step 2's and the dialog's, 2026-07-26):
   *  re-fetch both catalogs and drop the ceiling lookups, so an "unavailable" verdict clears
   *  itself after a backend restart no matter where the operator is standing. */
  const handleRetryCatalogs = useCallback(() => {
    loadCatalog();
    loadConstructions();
    // the ceiling lookups ride on the same restart the other two are retried for
    retryReliefLimits();
  }, [loadCatalog, loadConstructions, retryReliefLimits]);

  /** Header toggle. Re-fetches on open unless a good catalog is already in hand — so an
   *  "unavailable" verdict is re-checked every time (the user may have just restarted the API). */
  const handleToggleLibrary = useCallback(() => {
    if (!libraryOpen && catalogState !== "ready" && catalogState !== "loading") {
      loadCatalog();
    }
    setLibraryOpen((open) => !open);
  }, [libraryOpen, catalogState, loadCatalog]);

  /**
   * A catalog card click: preview that part on the main stage — the library browser's own
   * header preview, deliberately KEPT on the old swap behaviour (2026-07-26: only the step-2
   * path was retired; the browser is case-independent and often has no scan to sit beside).
   * Clicking the already-previewed card toggles back to the scan when a case is loaded;
   * with no case there is nothing to go back to, so the click is a no-op (the part stays,
   * honestly chip-labelled, until another card or a case replaces it).
   */
  const handlePreviewCatalogEntry = useCallback(
    (group: LibraryCatalogGroup, entry: LibraryCatalogEntry) => {
      const key = catalogEntryKey(group.model, entry);
      if (partPreviewRef.current?.catalogKey === key) {
        if (activeCaseIdRef.current !== null) handleExitPartPreview();
        return;
      }
      startPartPreview({ catalogKey: key }, entry);
    },
    [handleExitPartPreview, startPartPreview],
  );

  // ---- LIBRARY-SIDE ANNOTATION (client ask 2026-07-24: "mark the holes/trenches in the
  // LIBRARY part"). A part is marked ONCE per catalog variant and every case that ships it
  // reuses the annotation, so this lives in the case-independent library browser, over the
  // previewed part itself: the marks are placed by clicking the 3D part. ----
  /** The catalog part being annotated (model + catalog id + the previewed card's key), null
   *  when the panel is closed. `catalogKey` is what ties the panel to the preview on screen —
   *  previewing anything else closes it (see the effect below). */
  const [annotateTarget, setAnnotateTarget] = useState<
    { readonly model: string; readonly variant: string; readonly catalogKey: string } | null
  >(null);
  const [annotateState, setAnnotateState] = useState<PartAnnotatorState>("loading");
  const [annotateError, setAnnotateError] = useState<string | null>(null);
  /** The server's last word on this part's marks — the baseline `draftsAreDirty` compares
   *  against, and the `autoSeeded` provenance the panel states. */
  const [annotationSaved, setAnnotationSaved] = useState<PartAnnotation | null>(null);
  const [annotateDrafts, setAnnotateDrafts] = useState<DraftFeature[]>([]);
  const [annotateSelected, setAnnotateSelected] = useState<string | null>(null);
  const [annotateKind, setAnnotateKind] = useState<PartFeatureKind>("trench");
  const [annotateArmed, setAnnotateArmed] = useState(false);
  const [annotateBusy, setAnnotateBusy] = useState(false);
  /** False when the previewed mesh yielded no derivable canonical frame (see partFrame.ts) —
   *  marks can then be neither drawn nor placed, and the panel says so instead of guessing. */
  const [annotateCanPlace, setAnnotateCanPlace] = useState(true);
  /** Monotonic source of LOCAL draft keys. Server feature ids are derived from the azimuth, so
   *  they move as a mark moves and cannot key a list being edited. */
  const draftSeqRef = useRef(0);
  const annotateArmedRef = useRef(false);
  useEffect(() => {
    annotateArmedRef.current = annotateArmed;
  }, [annotateArmed]);

  /** Adopt a server annotation as the new baseline AND the new draft list (load, save, reset). */
  const adoptAnnotation = useCallback((annotation: PartAnnotation) => {
    draftSeqRef.current = annotation.features.length;
    setAnnotationSaved(annotation);
    setAnnotateDrafts(draftsFrom(annotation.features));
    setAnnotateSelected(null);
    setAnnotateState("ready");
    setAnnotateError(null);
  }, []);

  /** Leave annotation mode: unsaved marks are discarded (they were never persisted) and the
   *  part's markers come off the mesh. Safe to call when nothing is open. */
  const closeAnnotator = useCallback(() => {
    setAnnotateTarget(null);
    setAnnotateDrafts([]);
    setAnnotateSelected(null);
    setAnnotateArmed(false);
    setAnnotationSaved(null);
    setAnnotateError(null);
    // exitPointPick is global — it takes whichever one-shot was armed, which may be the
    // chart's pending new-site placement, so that state comes down with it (see clearRunArtifacts)
    setAddSiteTooth(null);
    viewerRef.current?.exitPointPick();
    viewerRef.current?.clearPartFeatureMarkers();
  }, []);

  const handleAnnotateEntry = useCallback(
    (group: LibraryCatalogGroup, entry: LibraryCatalogEntry) => {
      const key = catalogEntryKey(group.model, entry);
      setAnnotateTarget({ model: group.model, variant: entry.id, catalogKey: key });
      setAnnotateState("loading");
      setAnnotateError(null);
      setAnnotateDrafts([]);
      setAnnotateSelected(null);
      setAnnotateArmed(false);
      fetchPartFeatures(group.model, entry.id)
        .then((annotation) => {
          // guard against a second card being annotated while this fetch was in flight
          if (partPreviewRef.current?.catalogKey !== key) return;
          adoptAnnotation(annotation);
        })
        .catch((err: unknown) => {
          if (partPreviewRef.current?.catalogKey !== key) return;
          if (err instanceof ApiError && err.status === 404) {
            // the RUNNING backend predates the features endpoints — restart hint, not an error
            setAnnotateState("unavailable");
          } else {
            setAnnotateState("error");
            setAnnotateError(err instanceof ApiError ? err.message : "Failed to load the part's marks.");
          }
        });
    },
    [adoptAnnotation],
  );

  // The panel annotates the part ON SCREEN. Any preview change — another card, a row's part,
  // "back to scan", a case switch — makes its marks describe a mesh that is no longer there,
  // so the panel closes with them. One effect covers every path into and out of a preview.
  useEffect(() => {
    if (annotateTarget === null) return;
    if (partPreview?.catalogKey !== annotateTarget.catalogKey) closeAnnotator();
  }, [annotateTarget, partPreview, closeAnnotator]);

  // Draw (and redraw) the part's markers whenever the marks or the selection change — only
  // once the preview's mesh has actually landed (`loading === false`), since the markers are
  // placed through that mesh's own derived frame. A part whose frame could not be justified
  // draws nothing and flips canPlace off; the panel states that rather than showing an
  // unmarked part as if it had no features.
  useEffect(() => {
    if (annotateTarget === null) return;
    if (partPreview?.loading !== false) return;
    viewerRef.current?.setPartFeatureMarkers(
      annotateDrafts.map((d) => ({
        key: d.key,
        kind: d.kind,
        azimuthDeg: d.azimuthDeg,
        radiusMm: d.radiusMm,
        zMm: d.zMm,
        selected: d.key === annotateSelected,
      })),
    );
    setAnnotateCanPlace((viewerRef.current?.getPartFrame() ?? null) !== null);
  }, [annotateTarget, annotateDrafts, annotateSelected, partPreview]);

  // The armed click resolves an arbitrary time after arming (the callback is created once, in
  // an empty-deps handler) — read the CURRENT kind/selection through refs, same idiom as
  // confirmedSitesRef.
  const annotateKindRef = useRef(annotateKind);
  useEffect(() => {
    annotateKindRef.current = annotateKind;
  }, [annotateKind]);
  const annotateSelectedRef = useRef(annotateSelected);
  useEffect(() => {
    annotateSelectedRef.current = annotateSelected;
  }, [annotateSelected]);

  /** Arm the next click on the previewed PART: with a mark selected the click MOVES it,
   *  otherwise it appends one of the current kind. The click resolves in the mesh's own
   *  coordinates and is converted into the part's canonical frame — the only frame a feature
   *  azimuth means anything in (see partFrame.ts). */
  const handleArmAnnotateClick = useCallback(() => {
    if (annotateTarget === null) return;
    const frame = viewerRef.current?.getPartFrame() ?? null;
    if (frame === null) {
      setAnnotateCanPlace(false);
      return;
    }
    // supersedes any pick already waiting (see handleArmCorrespondence) — including the
    // chart's pending new-site placement, whose banner would otherwise outlive its click
    setAddSiteTooth(null);
    setAnnotateArmed(true);
    viewerRef.current?.enterPointPick((point) => {
      setAnnotateArmed(false);
      const canonical = canonicalFromRaw(frame, point);
      const read = readClick(canonical, frame.rimCentre);
      draftSeqRef.current += 1;
      const key = draftKey(draftSeqRef.current);
      setAnnotateDrafts((prev) =>
        placeDraft(
          prev,
          { point: canonical, kind: annotateKindRef.current, key },
          read,
          annotateSelectedRef.current,
        ),
      );
      // A move consumes the selection: the mark is where the operator just said it is.
      setAnnotateSelected(null);
    });
  }, [annotateTarget]);

  const handleCancelAnnotateClick = useCallback(() => {
    setAnnotateArmed(false);
    viewerRef.current?.exitPointPick();
  }, []);

  const handleSaveAnnotation = useCallback(() => {
    const target = annotateTarget;
    if (target === null || annotateDrafts.length === 0) return;
    setAnnotateBusy(true);
    savePartFeatures(target.model, target.variant, toFeatureInputs(annotateDrafts))
      .then((annotation) => {
        if (partPreviewRef.current?.catalogKey !== target.catalogKey) return;
        adoptAnnotation(annotation);
      })
      .catch((err: unknown) => {
        setErrorMessage(err instanceof ApiError ? err.message : "Saving the part's marks failed.");
      })
      .finally(() => setAnnotateBusy(false));
  }, [annotateTarget, annotateDrafts, adoptAnnotation]);

  const handleResetAnnotation = useCallback(() => {
    const target = annotateTarget;
    if (target === null) return;
    setAnnotateBusy(true);
    resetPartFeatures(target.model, target.variant)
      .then((annotation) => {
        if (partPreviewRef.current?.catalogKey !== target.catalogKey) return;
        adoptAnnotation(annotation);
      })
      .catch((err: unknown) => {
        setErrorMessage(err instanceof ApiError ? err.message : "Resetting the part's marks failed.");
      })
      .finally(() => setAnnotateBusy(false));
  }, [annotateTarget, adoptAnnotation]);

  const handleStartBrush = useCallback(
    (index: number) => {
      void (async () => {
        // Re-marking starts FRESH: previous run output cleared (see clearRunArtifacts), then
        // never paint over a composite/part view — restore the clean scan first (see
        // ensureCleanScanView's doc), and only arm if that actually succeeded.
        clearRunArtifacts();
        if (!(await ensureCleanScanView())) return;
        // Brush, mark mode, and rim-points collection are all mutually exclusive
        // (sceneController.enableBrush already exits the other two internally) — keep the React
        // state mirrors in sync too.
        setMarkMode(null);
        setRimPointsIndex(null);
        setBrushingIndex(index);
        viewerRef.current?.enableBrush();
      })();
    },
    [clearRunArtifacts, ensureCleanScanView],
  );

  const handleFinishBrush = useCallback(() => {
    setBrushingIndex((current) => {
      if (current === null) return null;
      // Read the live stroke BEFORE committing — commitBrushPatch moves it into the row's
      // own Points object and clears the live buffer as a side effect.
      const rawPoints = viewerRef.current?.getBrushPatch() ?? [];
      const points = subsamplePoints(toVec3Points(rawPoints));
      setConfirmedSites((prev) =>
        prev.map((site, i) => (i === current ? { ...site, markedPoints: points } : site)),
      );
      viewerRef.current?.commitBrushPatch(current);
      viewerRef.current?.disableBrush();
      // Keep the green patch visible on the model until the run or an explicit clear.
      return null;
    });
  }, []);

  const handleClearBrushStroke = useCallback(() => {
    // Clearing the in-progress stroke must also drop any previously-committed patch for the
    // row being brushed — otherwise a stale markedPoints from an earlier "Done" survives and
    // ships on run even though the chip/glow look cleared. The "✕" (clear committed patch,
    // outside brushing mode) is unaffected — it already does this via handleClearMarkedPoints.
    setBrushingIndex((current) => {
      if (current !== null) {
        setConfirmedSites((prev) =>
          prev.map((site, i) => (i === current ? { ...site, markedPoints: undefined } : site)),
        );
        viewerRef.current?.clearCommittedPatch(current);
      }
      return current;
    });
    viewerRef.current?.clearBrush();
  }, []);

  const handleClearMarkedPoints = useCallback(
    (index: number) => {
      // Same fresh-start rule as handleClearMark — see its comment.
      clearRunArtifacts();
      void ensureCleanScanView();
      setConfirmedSites((prev) =>
        prev.map((site, i) => (i === index ? { ...site, markedPoints: undefined } : site)),
      );
      viewerRef.current?.clearCommittedPatch(index);
    },
    [clearRunArtifacts, ensureCleanScanView],
  );

  /**
   * Arm the next click on the scan mesh to place row `index`'s centre marker. `kind` is always
   * "center" from the UI today — the rim tool is now the multi-click handleStartRimPoints flow
   * below; "rim" here only still exists to support handleClearMark clearing a legacy rimMark
   * (curated prefills) and remains fully wired in the controller for that purpose.
   */
  const handleStartMark = useCallback((index: number, kind: MarkKind) => {
    void (async () => {
      // Re-marking starts FRESH (previous run output cleared), and never place a mark over a
      // composite/part view — restore the clean scan first (see ensureCleanScanView's doc: the
      // redo's bad border click was aimed over the post-run composite), and only arm if that
      // actually succeeded.
      clearRunArtifacts();
      if (!(await ensureCleanScanView())) return;
      // Mutually exclusive with the brush and rim-points collection, same reasoning as handleStartBrush.
      setBrushingIndex(null);
      setRimPointsIndex(null);
      setMarkMode({ rowIndex: index, kind });
      viewerRef.current?.enterMarkMode(index, kind, (point) => {
      // The controller already placed/replaced the marker sphere and exited mark mode by the
      // time this fires — mirror the resolved point into ConfirmedSite so it ships on /run.
      //
      // Centre+rim are ONE measurement (centre locates the cap, |rim - centre| is the measured
      // rim radius) — re-placing ONLY the centre while a LEGACY rim mark already exists must
      // carry that rim along with it (translateMark), or a fresh centre pairs with a radius
      // measured from the OLD centre and the click error bakes into the derived radius (see
      // translateMark's domain-layer doc for the measured seat-degradation this caused).
      // rimPoints are independent, scan-anchored border locations (not derived relative to the
      // centre) — re-placing the centre must NOT move them, so translation is skipped entirely
      // whenever the row has rimPoints (translateMark's own doc states this rule too). Re-placing
      // the rim (kind === "rim", legacy path) never moves the centre.
      //
      // Read the PRIOR row from confirmedSitesRef (not the closed-over confirmedSites — this
      // callback is created once via enterMarkMode's empty-deps handleStartMark, long before the
      // click resolves) and compute translatedRim up front, BEFORE calling setConfirmedSites. A
      // React 18 functional updater does not run synchronously inside the setState call — it
      // runs later during re-render (and may run twice under StrictMode) — so writing/reading a
      // value across the updater boundary is unsafe; the updater below is a pure function of
      // `prev`, with no outside reads or writes.
      const priorSite = confirmedSitesRef.current[index];
      const hasRimPoints = (priorSite?.rimPoints?.length ?? 0) > 0;
      const translatedRim: Vec3 | null =
        kind === "center" && !hasRimPoints && priorSite?.centerMark && priorSite?.rimMark
          ? translateMark(priorSite.rimMark, priorSite.centerMark, point)
          : null;

      setConfirmedSites((prev) =>
        prev.map((site, i) => {
          if (i !== index) return site;
          if (kind === "rim") {
            return { ...site, rimMark: point };
          }
          // kind === "center": carry the LEGACY rim along when translatedRim was computed (a
          // full prior centre+rimMark pair existed AND the row has no rimPoints); otherwise
          // there is nothing to preserve — behave exactly as before (just set the centre).
          return translatedRim !== null
            ? { ...site, centerMark: point, rimMark: translatedRim }
            : { ...site, centerMark: point };
        }),
      );
      if (translatedRim !== null) {
        // Cosmetic snap-to-surface only, same as prefill — the RAW translated value (not the
        // snapped one) is what's already in confirmedSites above and ships to the API.
        viewerRef.current?.setSiteMarker(index, "rim", translatedRim);
      }
      setMarkMode(null);
      });
    })();
  }, [clearRunArtifacts, ensureCleanScanView]);

  const handleCancelMark = useCallback(() => {
    setMarkMode(null);
    viewerRef.current?.exitMarkMode();
  }, []);

  const handleClearMark = useCallback(
    (index: number, kind: MarkKind) => {
      // Removing a mark is re-marking too: previous run output is about a gesture that no
      // longer exists — clear it and put the clean scan back (fire-and-forget; nothing arms).
      clearRunArtifacts();
      void ensureCleanScanView();
      setConfirmedSites((prev) =>
        prev.map((site, i) =>
          i === index ? { ...site, [kind === "center" ? "centerMark" : "rimMark"]: undefined } : site,
        ),
      );
      viewerRef.current?.clearSiteMarker(index, kind);
    },
    [clearRunArtifacts, ensureCleanScanView],
  );

  /** Arm multi-click collection of rim-BORDER points on row `index` — stays armed across several clicks. */
  const handleStartRimPoints = useCallback(
    (index: number) => {
      void (async () => {
        // Re-marking starts FRESH (previous run output cleared). Border clicks are THE seat
        // measurement — they especially must never be aimed over a composite (the redo's
        // 0.89mm-out click was exactly that; see ensureCleanScanView).
        clearRunArtifacts();
        if (!(await ensureCleanScanView())) return;
        // Mutually exclusive with the brush and single-shot mark mode, same reasoning as handleStartBrush.
        setBrushingIndex(null);
        setMarkMode(null);
        setRimPointsIndex(index);
        viewerRef.current?.enableRimPoints(index);
      })();
    },
    [clearRunArtifacts, ensureCleanScanView],
  );

  // Mirrors rimPointsIndex for handlers/listeners that must read the CURRENT value
  // without re-registering (Escape key) or that must never live inside a state
  // updater (finish). Declared before its first closure use.
  const rimPointsIndexRef = useRef<number | null>(null);
  useEffect(() => {
    rimPointsIndexRef.current = rimPointsIndex;
  }, [rimPointsIndex]);

  /**
   * The LEGACY single rim sphere (blue) and the multi-point border dots (teal) must never both
   * be visible for the same row — a client screenshot showed the two were indistinguishable
   * on-screen, and once rimPoints exists the legacy sphere is actively misleading (the mapper
   * doesn't even send rim_mark once rimPoints is non-empty — see toWireRunSiteInput). This is
   * now enforced INSIDE sceneController's finishRimPoints/clearRimPoints (a single centralized
   * invariant — see applyRimVisibilityInvariant there) rather than by every call site here
   * remembering to sync afterwards: App.tsx's only remaining job is to pass the row's CURRENT
   * legacy rimMark (or undefined) into those two calls; the controller decides visibility itself,
   * so a future re-draw path calling finishRimPoints/clearRimPoints can't forget this by omission.
   */
  const handleFinishRimPoints = useCallback(() => {
    // Read the active row from the ref, NEVER from inside a state updater: updaters run
    // during render and StrictMode double-invokes them — a side-effectful updater here
    // committed the points on the first pass and clobbered them with the (now empty)
    // live buffer on the replay (caught live: Done left no rimPoints and no spheres).
    const current = rimPointsIndexRef.current;
    if (current === null) return;
    // Read the live session's points BEFORE finishing — finishRimPoints moves them into
    // the row's own committed sphere array and clears the live buffer as a side effect
    // (mirrors handleFinishBrush reading getBrushPatch before commitBrushPatch).
    const rawPoints = viewerRef.current?.getRimPointsPatch() ?? [];
    const points = toVec3Points(rawPoints);
    // A finished session REPLACES the row's rimPoints wholesale — never appends across
    // sessions. An empty session (Done with zero clicks) clears any prior rimPoints too,
    // matching finishRimPoints' scene-side behavior (see its doc).
    setConfirmedSites((prev) =>
      prev.map((site, i) => (i === current ? { ...site, rimPoints: points.length > 0 ? points : undefined } : site)),
    );
    // Read the row's rimMark from the REF (pre-finish snapshot — this session never touches
    // rimMark, so it's still accurate) — finishRimPoints applies the legacy-sphere-visibility
    // invariant internally from this value plus its own now-committed rimPoints count.
    viewerRef.current?.finishRimPoints(current, confirmedSitesRef.current[current]?.rimMark);
    setRimPointsIndex(null);
  }, []);

  const handleCancelRimPoints = useCallback(() => {
    setRimPointsIndex(null);
    viewerRef.current?.cancelRimPoints();
  }, []);

  /** Disarm the align-to-mark trench click without POSTing — the row's "✕ cancel mark"
   *  button and Escape both land here (the keyboard path mirrors handleCancelMark's). */
  const handleCancelMarkTrench = useCallback(() => {
    setMarkTrenchTooth(null);
    viewerRef.current?.exitPointPick();
  }, []);

  /** Clear BOTH rimPoints and the legacy rimMark (and their spheres) for row `index` — the single
   *  ✕ next to ◐ clears whichever rim representation the row currently has. legacyRimMark is
   *  intentionally omitted from the clearRimPoints call: this action clears the legacy mark too
   *  (via the explicit clearSiteMarker right below), so there is nothing to re-show. */
  const handleClearRim = useCallback(
    (index: number) => {
      // Same fresh-start rule as handleClearMark — see its comment.
      clearRunArtifacts();
      void ensureCleanScanView();
      setConfirmedSites((prev) =>
        prev.map((site, i) => (i === index ? { ...site, rimMark: undefined, rimPoints: undefined } : site)),
      );
      viewerRef.current?.clearSiteMarker(index, "rim");
      viewerRef.current?.clearRimPoints(index);
    },
    [clearRunArtifacts, ensureCleanScanView],
  );

  // Escape cancels whichever single-click mark mode or multi-click rim-points session is active
  // — the keyboard equivalent of each banner's own Cancel button. Reads the CURRENT mode from
  // refs (markModeRef here; rimPointsIndexRef is declared above handleFinishRimPoints) so this
  // one global listener never needs to be torn down and re-added as those change. The listener
  // ITSELF is registered further down, after the correspondence handlers it also cancels.
  const markModeRef = useRef(markMode);
  useEffect(() => {
    markModeRef.current = markMode;
  }, [markMode]);

  /**
   * Resolve a staged part source to a fetchable URL: the scan endpoint (never versioned — an
   * /api/cases/.../scan request, not a files_base package file, always served fresh), or a
   * files_base-relative name with the current run's cache-bust token appended (withCacheBust is
   * a no-op when version is null, i.e. before any run). `version` is threaded as an explicit
   * parameter rather than read from runVersion state — see showComposite's doc for why.
   */
  const resolvePartUrl = useCallback(
    (source: StagedPartSource, caseId: string, filesBase: string, version: number | null): string =>
      source.kind === "scan" ? scanUrlFor(caseId) : withCacheBust(`${filesBase}${source.name}`, version),
    [],
  );

  /**
   * Core composite-view loader, parameterized on caseId/filesBase/version rather than reading
   * runResult/runVersion from closure state — so it works both for a user's ViewerControls click
   * (state is current by then) and for the immediate post-run auto-reveal, where the just-fetched
   * result (and the fresh cache-bust token minted alongside it) haven't landed in state yet when
   * this needs to fire. Passing the version through as a parameter, the same way caseId/filesBase
   * already are, guarantees the auto-reveal's fetches carry the NEW run's token, not a stale one
   * from before this render's setRunVersion call takes effect.
   */
  const showComposite = useCallback(
    async (composite: StagedComposite, label: string, caseId: string, filesBase: string, version: number | null) => {
      // Both loadComposite and its loadStl fallback below clear the controller's orange
      // proposal markers as a side effect of replacing the scene contents — sync the toggle off
      // up front so the "view/hide proposals" button never lies about what's actually drawn
      // (see startPartPreview for the same reasoning, applied to every other view change).
      setShowProposalMarkers(false);
      // a composite replaces any library-part preview too — chip down, stale loads discarded
      cancelPendingPreviewLoads();
      applyPartPreview(null);
      const isPartAlone = label.startsWith("3");
      const fit = isPartAlone ? "close" : "wide";

      const parts = composite.parts.map((part) => ({
        url: resolvePartUrl(part.source, caseId, filesBase, version),
        role: part.role,
      }));

      try {
        await viewerRef.current?.loadComposite(parts, fit);
        if (activeCaseIdRef.current !== caseId) return; // stale — user switched cases
        viewIsScanRef.current = false; // composite on screen — marking must restore the scan first
        bumpStageContent();
        setActiveViewLabel(label);
        setLegendRoles(viewerRef.current?.getCompositeRoles() ?? []);
      } catch (err) {
        // Composite parts can 404 on older cached runs (e.g. missing arch-capless.stl) — fall
        // back to the pre-merged single-mesh file rather than showing a broken view.
        if (composite.fallbackFile) {
          try {
            await viewerRef.current?.loadStl(withCacheBust(`${filesBase}${composite.fallbackFile}`, version), {
              fit,
              // the merged fallback is still arch-scale content — orient it anatomically too
              anatomy: true,
            });
            if (activeCaseIdRef.current !== caseId) return;
            viewIsScanRef.current = false; // merged run output, not the clean input scan
            bumpStageContent();
            // No per-role color-coding on this single merged mesh — flag it as the legacy view.
            setActiveViewLabel(`${label} (legacy view)`);
            setLegendRoles([]);
            return;
          } catch (fallbackErr) {
            setErrorMessage(
              fallbackErr instanceof Error ? fallbackErr.message : "Failed to load the mesh.",
            );
            return;
          }
        }
        setErrorMessage(err instanceof Error ? err.message : "Failed to load the mesh.");
      }
    },
    [applyPartPreview, cancelPendingPreviewLoads, resolvePartUrl],
  );

  /**
   * Draw (or replace) every site's post-run seated-pose axis triad (Item 3): fetches each
   * tooth's "<case>-<tooth>-implant.json" package file in parallel and hands the extracted pose
   * to the viewer. Best-effort per tooth — fetchImplantPose already swallows its own errors
   * (missing file, bad JSON, network) and returns null rather than throwing, since a triad is a
   * nice-to-have overlay that must never block or error out the rest of the results. Clears every
   * existing triad first so a recompute (which can change which teeth exist, or their poses)
   * never leaves a stale triad for a tooth the new result no longer has. `version` cache-busts
   * the implant.json fetch itself — same stale-tab-cache concern as the mesh files, and threaded
   * as an explicit parameter for the same reason as showComposite's `version`.
   */
  const drawPoseTriads = useCallback(
    async (caseId: string, filesBase: string, sites: readonly RunSiteResult[], version: number | null) => {
      viewerRef.current?.clearAllPoseTriads();
      const poses = await Promise.all(
        sites.map((s) => fetchImplantPose(filesBase, caseId, s.tooth, version)),
      );
      if (activeCaseIdRef.current !== caseId) return; // stale — user switched cases mid-fetch
      // The same fetch feeds two consumers: the triads on screen and the POSE EXPORT. Keeping
      // the parsed poses (rather than re-fetching them at export time) is what makes an export
      // "the pose you are looking at" by construction, not by coincidence.
      const byTooth = new Map<number, ImplantPose>();
      for (const pose of poses) {
        if (!pose) continue;
        byTooth.set(pose.tooth, pose);
        viewerRef.current?.setPoseTriad(pose.tooth, {
          position: pose.position,
          axisX: pose.axisX,
          axisY: pose.axisY,
          axisZ: pose.axisZ,
        });
      }
      setSitePoses(byTooth);
    },
    [],
  );

  /**
   * Run (or re-run) automation with the CURRENT marks. No longer auto-triggered by mark edits
   * (see isRunStale below) — every call is either the doctor's initial "Run automation" click,
   * the explicit "Recompute alignment" action once marks have drifted, or Confirm All firing a
   * recompute for a stale run (see handleConfirmAll).
   */
  const handleRunAutomation = useCallback(
    async (fresh: boolean) => {
      if (!selectedCase) return;
      const caseId = selectedCase.id;
      // THE ONE GATE, for EVERY process route (domain/runGate). This is the choke point every
      // route passes through — step 4's "Run automation", "⟳ rerun live", Confirm All's
      // recompute, and the dialog's OK · Process — and it judges the SAME conditions the
      // dialog's own button does, including the client's acknowledgment ("the OK button will be
      // enabled only after all sites have been reviewed"). The verifier found three
      // routes reaching this line with zero sites reviewed; they no longer can, and structurally
      // cannot again: `runAutomation` accepts only the branded selection `authorizeRun` mints.
      const auth = authorizeRun({
        selection,
        duplicateTeeth: findDuplicateTeeth(confirmedSites),
      });
      if (!auth.ok) {
        setErrorMessage(auth.reason);
        return;
      }
      setRunBusy(true);
      // A new attempt clears the previous refusal: the panel must describe THIS run, never leave
      // a fixed problem on screen while the next one is in flight.
      setRunRefusal(null);
      try {
        // Record the signature of the marks THIS run is submitting before the request goes out —
        // this becomes the new "what the run used" baseline that isRunStale compares the
        // doctor's LATER edits against.
        const submittedMarksSignature = marksSignatureFor(confirmedSites);
        // Captured BEFORE the await: if the doctor starts re-marking while this request is in
        // flight, clearRunArtifacts bumps the epoch and these results must never land.
        const epoch = runEpochRef.current;
        const result = await runAutomation(caseId, confirmedSites, fresh, auth.selection);
        if (activeCaseIdRef.current !== caseId) return; // stale — user switched cases
        if (runEpochRef.current !== epoch) return; // stale — re-marking cleared this run
        // Minted as a local const, THEN passed explicitly to showComposite/drawPoseTriads below
        // instead of relying on the setRunVersion call (a few lines down) having landed in state
        // by the time those fire — React state updates are not synchronous, so reading runVersion
        // from closure here could still see the PREVIOUS run's token. See their own docs.
        const version = Date.now();
        setRunResult(result);
        setLastRunAt(new Date());
        setRunVersion(version);
        setLastRunMarksSignature(submittedMarksSignature);
        // Reset first so a reveal failure degrades to "no active view" rather than leaving a
        // stale label/legend from whatever was shown before this run.
        setActiveViewLabel(null);
        setLegendRoles([]);
        // The reveal: auto-load stage 1 (scan + aligned caps, legend on) instead of leaving
        // the stale pre-run scene — reuse the EXACT composition ViewerControls builds for
        // "1 · Healing-cap alignment" so that button shows active too.
        const stage1 = buildStage1Composite(result.summary.sites, caseId);
        void showComposite(stage1, STAGE1_LABEL, caseId, result.filesBase, version);
        // Always show after a run (no toggle — Item 3 spec) — fire-and-forget, best-effort.
        void drawPoseTriads(caseId, result.filesBase, result.summary.sites, version);
      } catch (err) {
        /* THE HARD-FAIL PATH, MADE READABLE (client, 2026-07-25: the gingival-relief refusal
           "read as an unexplained error"). A refused run is not a transport failure: it carries
           the server's own sentence naming the tooth, the part and the number to change. It goes
           to a PERSISTENT panel with a next step — the transient toast is what the client met,
           and a sentence that long cannot be read before it disappears. Anything the domain
           cannot recognise as a refusal still falls through to the toast. */
        const refusal = runRefusalFrom(err);
        if (refusal !== null) setRunRefusal(refusal);
        else setErrorMessage(err instanceof ApiError ? err.message : "Automation run failed.");
      } finally {
        setRunBusy(false);
      }
    },
    [selectedCase, confirmedSites, selection, showComposite, drawPoseTriads],
  );

  /**
   * The verify dialog's OK: process with exactly the selection the operator acknowledged. The
   * dialog closes onto step 4, which owns the run's busy state, the results table and the staged
   * viewer reveal — the same destination the quick path lands on, so both routes end in one place.
   */
  const handleProcessFromDialog = useCallback(() => {
    setVerifyOpen(false);
    setStage("process");
    void handleRunAutomation(false);
  }, [handleRunAutomation]);

  /**
   * RE-SHOW THE ALIGNMENT for one site (client ask 2026-07-25): after a manual fit — the best fit
   * or the fit-by-points correspondence — the operator has to SEE what the fit did. The
   * three-panel verify is where that picture already lives (library part / scanned cap / union
   * coloured by the measured deviation), so a fit lands the operator there, on the site they just
   * fitted. The stage re-fetches its deviation off `runVersion`, which every applied fit mints
   * fresh — so the union pane shows the NEW seat, never the pre-fit read.
   */
  const revealAlignment = useCallback((tooth: number) => {
    setSelection((prev) => {
      const index = prev.sites.findIndex((s) => s.tooth === tooth);
      return index < 0 ? prev : withActiveSite(prev, index);
    });
    setVerifyOpen(true);
  }, []);

  // ---- MANUAL BEST FIT (the client's register/best-fit panel, 2026-07-25). The diameter and the
  // Apply toggle live HERE, not per row: an operator settles on a matching diameter for the case
  // and works down the sites with it. `bestFitUnavailable` is the running backend's 404 (the
  // endpoint predates this build) — stated in the panel, not raised as a toast per click. ----
  const [bestFitDiameterMm, setBestFitDiameterMm] = useState(BEST_FIT_DEFAULT_DIAMETER_MM);
  const [bestFitApply, setBestFitApply] = useState(true);
  const [bestFitUnavailable, setBestFitUnavailable] = useState(false);
  const [bestFitNotice, setBestFitNotice] = useState<{ tooth: number; text: string } | null>(null);
  /** The last "already optimal" 409 (client ask 2026-07-26): a machine-readable PASS — the
   *  certified pose already is the best fit at the dialled diameter — rendered in the
   *  confirmatory tone with a one-click wider search, never as the error toast. */
  const [bestFitConfirmation, setBestFitConfirmation] = useState<{
    readonly tooth: number;
    readonly message: string;
    /** The RUN's own diameter (not the live dial): the widen button only exists while the
     *  suggestion actually is wider — at the Ø2.00mm ceiling it capped to the dial itself
     *  and looped the identical search (review 2026-07-26). */
    readonly matchingDiameterMm: number;
    readonly suggestedDiameterMm: number;
  } | null>(null);

  /** Open the verification route. The two catalogs it chooses from are fetched on demand (and
   *  re-checked on every open, so an "unavailable" verdict clears itself once the API restarts). */
  const handleOpenVerify = useCallback(() => {
    if (catalogState !== "ready" && catalogState !== "loading") loadCatalog();
    if (constructionsState !== "ready" && constructionsState !== "loading") loadConstructions();
    setVerifyOpen(true);
  }, [catalogState, constructionsState, loadCatalog, loadConstructions]);

  /**
   * "Copy run report" — the feedback loop into chat/tickets. buildRunReport is a pure domain
   * function (case id + confirmedSites inputs + runResult outputs -> markdown string); this
   * handler's only job is the DOM side effect (clipboard write) and the transient "copied ✓"
   * confirmation. Guarded on selectedCase/runResult existing — the button itself is only rendered
   * inside that same guard, but the callback is defined once at the top level regardless.
   */
  const handleCopyRunReport = useCallback(async () => {
    if (!selectedCase || !runResult) return;
    const report = buildRunReport(selectedCase.id, confirmedSites, runResult.summary.sites);
    try {
      await navigator.clipboard.writeText(report);
      setReportCopied(true);
      setTimeout(() => setReportCopied(false), 2000);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Could not copy the run report to the clipboard.");
    }
  }, [selectedCase, runResult, confirmedSites]);

  /**
   * marksSignature drives the STALENESS check only now (isRunStale below) — it is NOT an effect
   * dependency and triggers nothing by itself. The client's complaint was that the old debounced
   * auto-recompute fired a fresh (~30-60s) run after EVERY individual mark edit: placing the
   * centre triggered a run, then finishing rim points triggered another, showing a half-marked
   * intermediate result and wasting runs. Centre and rim must be set together, THEN recomputed
   * once — so this is now purely informational: it tells the banner/results block whether the
   * marks on screen still match what the last run used.
   */
  const marksSignature = marksSignatureFor(confirmedSites);
  const runIsStale = runResult !== null && isRunStale(marksSignature, lastRunMarksSignature);

  /** The explicit "Recompute alignment" action — always a live (uncached) run, since the whole
   *  point is picking up the doctor's just-made edits. */
  const handleRecompute = useCallback(() => {
    setRecomputeBusy(true);
    handleRunAutomation(true).finally(() => setRecomputeBusy(false));
  }, [handleRunAutomation]);

  /**
   * Confirm All advances to step 4 — and per the client ("both need to be set and confirm all /
   * run after"), if a run already exists and the marks have since drifted (runIsStale), this ALSO
   * fires the recompute so the doctor doesn't have to separately notice the banner and press
   * Recompute after confirming. Guarded on runBusy (covers ANY run already in flight — the
   * banner's own Recompute, the "Run automation"/"rerun live" buttons, or a second Confirm All
   * click) so this can never double-fire a request: React applies the first click's setRunBusy
   * before a second click's handler runs, and handleRunAutomation's own `if (!selectedCase)
   * return;`-style guards aside, runBusy is the single source of truth for "a request is already
   * in flight" — checking it here is strictly broader (and simpler) than tracking
   * recomputeBusy separately for just this one call site.
   */
  const handleConfirmAll = useCallback(() => {
    // Confirm All lands the operator on the NEXT thing the case needs. With the library
    // selection folded into Mark & declare (2026-07-26), that is VERIFY before a run exists —
    // the selection was made right here, beside the marks — and the process step once one does.
    setStage(runResult === null ? "verify" : "process");
    // ...and per the client ("both need to be set and confirm all / run after"), a run whose
    // marks have since drifted is recomputed here, so the doctor does not have to separately
    // notice the banner. Only when the gate would actually let that run through: Confirm All
    // was the third acknowledgment bypass, and it must not fire a request handleRunAutomation
    // would refuse with a toast the operator never asked for.
    if (runIsStale && !runBusy && canRun({ selection, duplicateTeeth: findDuplicateTeeth(confirmedSites) })) {
      handleRecompute();
    }
  }, [runResult, runIsStale, runBusy, selection, confirmedSites, handleRecompute]);

  const handleShowComposite = useCallback(
    async (composite: StagedComposite, label: string) => {
      if (!selectedCase || !runResult) return;
      // A user-initiated stage-switch click, always well after the triggering run's setRunVersion
      // has landed in state — safe to read runVersion from closure here (unlike the post-run
      // auto-reveal in handleRunAutomation, which cannot wait for a render to pass its own token
      // through as an explicit parameter instead).
      await showComposite(composite, label, selectedCase.id, runResult.filesBase, runVersion);
    },
    [selectedCase, runResult, runVersion, showComposite],
  );

  /**
   * Operator rotation nudge (review-gate backstop): propose a gated rotation step (or reset)
   * for one seated site. On success the backend has already re-emitted that site's aligned-cap
   * STL + implant.json, so this folds the returned clocking/audit into the row, mints a fresh
   * cache-bust token, and reloads the stage-1 composite + pose triads — the operator SEES the
   * rotated cap, not a stale mesh. A 409 refusal carries the server's own reason (stability
   * excess or a certification gate) and surfaces as the toast; nothing on screen changes then.
   */
  const handleNudgeRotation = useCallback(
    (tooth: number, request: NudgeRequest) => {
      if (!selectedCase || !runResult || nudgeBusyTooth !== null) return;
      const caseId = selectedCase.id;
      const current = runResult;
      setNudgeBusyTooth(tooth);
      void (async () => {
        try {
          const out = await nudgeRotation(caseId, tooth, request);
          if (activeCaseIdRef.current !== caseId) return; // stale — user switched cases
          const sites = current.summary.sites.map((s) =>
            s.tooth === tooth ? { ...s, clocking: out.clocking, nudge: out.nudge } : s,
          );
          const updated = { ...current, summary: { ...current.summary, sites } };
          const version = Date.now();
          setRunResult(updated);
          setRunVersion(version);
          const stage1 = buildStage1Composite(sites, caseId);
          void showComposite(stage1, STAGE1_LABEL, caseId, current.filesBase, version);
          void drawPoseTriads(caseId, current.filesBase, sites, version);
        } catch (err) {
          setErrorMessage(err instanceof ApiError ? err.message : "Rotation nudge failed.");
        } finally {
          setNudgeBusyTooth(null);
        }
      })();
    },
    [selectedCase, runResult, nudgeBusyTooth, showComposite, drawPoseTriads],
  );

  /**
   * THE ROTATION DIAL FOR THE SITE THE VERIFY DIALOG IS SHOWING (client, 2026-07-26: rotation
   * "is kinda useless if it doesn't have a good view of what it does real time").
   *
   * Resolved here rather than inside the dialog because the thing being rotated is the SHIPPED
   * seat, which lives in runResult: null until this site has actually been processed, and null on
   * an icp seat, which has no rim ring to hold fixed. handleNudgeRotation already mints a fresh
   * runVersion on every applied step — that is the token the union pane re-fetches its deviation
   * on, which is what makes a step visible on the 3D the operator is looking at.
   */
  const verifyRotation = useMemo(() => {
    const tooth = selection.sites[selection.activeSiteIndex]?.tooth;
    if (tooth === undefined || !runResult) return null;
    const site = runResult.summary.sites.find((s) => s.tooth === tooth);
    if (!site || site.seatMethod !== "rim") return null;
    return {
      tooth,
      clocking: site.clocking,
      cumulativeDeg: site.nudge?.cumulativeDeg ?? 0,
      busy: nudgeBusyTooth === tooth,
      onNudge: handleNudgeRotation,
    };
  }, [selection, runResult, nudgeBusyTooth, handleNudgeRotation]);

  /**
   * ALIGN-TO-MARKED-TRENCH, the POST half (client ask 2026-07-24): the operator clicked the
   * cap's coded cutout/trench on the scan; the backend rotates the seated cap so its nearest
   * code feature lands on that mark — a PROPOSAL judged by the exact nudge gates. On success
   * the flow is identical to handleNudgeRotation (fold clocking/audit into the row, fresh
   * cache-bust token, stage-1 composite + triads reload) plus the outcome line under the
   * row's rotation control. A 409 refusal (or an out-of-range mark) carries the server's own
   * sentence and surfaces as the toast; nothing on screen changes then.
   */
  const handleAlignToMark = useCallback(
    (tooth: number, point: Vec3) => {
      if (!selectedCase || !runResult || nudgeBusyTooth !== null) return;
      const caseId = selectedCase.id;
      const current = runResult;
      setNudgeBusyTooth(tooth);
      void (async () => {
        try {
          const out = await alignToMark(caseId, tooth, point);
          if (activeCaseIdRef.current !== caseId) return; // stale — user switched cases
          const sites = current.summary.sites.map((s) =>
            s.tooth === tooth ? { ...s, clocking: out.clocking, nudge: out.nudge } : s,
          );
          const updated = { ...current, summary: { ...current.summary, sites } };
          const version = Date.now();
          setRunResult(updated);
          setRunVersion(version);
          setAlignMarkNotice({ tooth, text: describeAlignToMark(out) });
          const stage1 = buildStage1Composite(sites, caseId);
          void showComposite(stage1, STAGE1_LABEL, caseId, current.filesBase, version);
          void drawPoseTriads(caseId, current.filesBase, sites, version);
        } catch (err) {
          setErrorMessage(err instanceof ApiError ? err.message : "Align to mark failed.");
        } finally {
          setNudgeBusyTooth(null);
        }
      })();
    },
    [selectedCase, runResult, nudgeBusyTooth, showComposite, drawPoseTriads],
  );

  // The armed pick's click callback fires an arbitrary time after arming — invoke the
  // LATEST handler (fresh runResult/busy state; another row could have been nudged in
  // between), not the identity closed over at arm time. Same read-the-current-value-
  // through-a-ref idiom as confirmedSitesRef.
  const handleAlignToMarkRef = useRef(handleAlignToMark);
  useEffect(() => {
    handleAlignToMarkRef.current = handleAlignToMark;
  }, [handleAlignToMark]);

  /**
   * ALIGN-TO-MARKED-TRENCH, the arming half: restore the CLEAN INPUT SCAN first — the
   * trench must be clicked on the actual scanned surface, and after a run the stage-1
   * composite's green aligned cap overlays the scanned cap (on the weak-evidence rows this
   * tool backstops, that overlay's rotation is exactly what is wrong) — WITHOUT clearing
   * the run artifacts: this is a post-run correction of the shipped rotation, not a
   * re-marking of the run's inputs (contrast handleStartMark). Then arm the viewer's
   * one-shot on-surface pick; the click POSTs align-to-mark, Escape cancels.
   */
  const handleStartMarkTrench = useCallback(
    (tooth: number) => {
      if (nudgeBusyTooth !== null) return;
      void (async () => {
        setAlignMarkNotice(null);
        if (!(await ensureCleanScanView())) return;
        // supersedes any pick already waiting (see handleArmCorrespondence): the chart's
        // pending new-site placement must not keep claiming a click this one now owns
        setAddSiteTooth(null);
        setMarkTrenchTooth(tooth);
        viewerRef.current?.enterPointPick((point) => {
          setMarkTrenchTooth(null);
          handleAlignToMarkRef.current(tooth, point);
        });
      })();
    },
    [nudgeBusyTooth, ensureCleanScanView],
  );

  /**
   * MANUAL BEST FIT, the POST half (client ask 2026-07-25 — their register/best-fit panel): refine
   * one seated site by matching the scan surface within the operator's MATCHING DIAMETER. With
   * Apply off the server measures and reports without moving anything, so nothing on screen
   * changes and only the outcome line updates. With Apply on the flow is identical to every other
   * post-run pose correction (fold the returned numbers into the row, mint a fresh cache-bust
   * token, reload the stage-1 composite + triads) and then RE-SHOWS the alignment in the
   * three-panel verify — a fit is only believable next to the picture it produced.
   *
   * A 404 means the running backend predates the endpoint: the panel says so (restart make serve)
   * rather than a toast per click. Every other refusal carries the server's own sentence.
   */
  const runBestFit = useCallback(
    (tooth: number, diameterMm: number) => {
      if (!selectedCase || !runResult || nudgeBusyTooth !== null) return;
      const caseId = selectedCase.id;
      const current = runResult;
      setNudgeBusyTooth(tooth);
      void (async () => {
        try {
          const out = await bestFitSite(caseId, tooth, {
            matchingDiameterMm: diameterMm,
            apply: bestFitApply,
          });
          if (activeCaseIdRef.current !== caseId) return; // stale — user switched cases
          setBestFitUnavailable(false);
          setBestFitNotice({ tooth, text: describeBestFit(out) });
          setBestFitConfirmation(null); // a real outcome supersedes any earlier "already optimal"
          // Measure-only: the seat was NOT touched, so nothing on screen may move either.
          if (!out.applied) return;
          const sites = current.summary.sites.map((s) =>
            s.tooth === tooth
              ? {
                  ...s,
                  // Each field is folded ONLY when the server re-read it — a fit that reported no
                  // clocking must not erase the clocking the row already had.
                  fit: out.fit ?? s.fit,
                  rimAgreementMm: out.rimAgreementMm ?? s.rimAgreementMm,
                  clocking: out.clocking ?? s.clocking,
                  nudge: out.nudge ?? s.nudge,
                }
              : s,
          );
          const updated = { ...current, summary: { ...current.summary, sites } };
          const version = Date.now();
          setRunResult(updated);
          setRunVersion(version);
          const stage1 = buildStage1Composite(sites, caseId);
          void showComposite(stage1, STAGE1_LABEL, caseId, current.filesBase, version);
          void drawPoseTriads(caseId, current.filesBase, sites, version);
          revealAlignment(tooth);
        } catch (err) {
          if (err instanceof ApiError && err.status === 404) {
            setBestFitUnavailable(true);
            return;
          }
          // "ALREADY OPTIMAL" IS A PASS (client ask 2026-07-26): the server confirmed the
          // certified pose is the best fit at this diameter. Rendered as the confirmatory
          // panel state with its one-click wider search — recognised by the machine-readable
          // kind, never by matching prose. Every plain-string 409 stays the error it is.
          const optimal = bestFitAlreadyOptimal(err);
          if (optimal !== null) {
            setBestFitNotice(null);
            setBestFitConfirmation({
              tooth,
              message: optimal.message,
              matchingDiameterMm: optimal.matchingDiameterMm,
              suggestedDiameterMm: optimal.suggestedDiameterMm,
            });
            return;
          }
          setErrorMessage(err instanceof ApiError ? err.message : "The best fit failed.");
        } finally {
          setNudgeBusyTooth(null);
        }
      })();
    },
    [
      selectedCase,
      runResult,
      nudgeBusyTooth,
      bestFitApply,
      showComposite,
      drawPoseTriads,
      revealAlignment,
    ],
  );

  const handleBestFit = useCallback(
    (tooth: number) => runBestFit(tooth, bestFitDiameterMm),
    [runBestFit, bestFitDiameterMm],
  );

  /** The confirmation's one-click follow-up: adopt the suggested wider diameter (the dial
   *  follows, so the operator sees what is now set) and re-run immediately. */
  const handleBestFitWider = useCallback(
    (tooth: number, diameterMm: number) => {
      setBestFitDiameterMm(diameterMm);
      setBestFitConfirmation(null);
      runBestFit(tooth, diameterMm);
    },
    [runBestFit],
  );

  // ---- SCAN-SIDE NAMED CORRESPONDENCE (client ask 2026-07-24: "mark the corresponding
  // holes/trenches in the SCAN"). The explicit path alongside the one-click trench tool:
  // the operator says WHICH library feature each click is, so the rotation cannot bind to
  // the wrong cutout on a multi-feature cap — and it works where the automatic code reader
  // has no evidence at all. ONE row at a time (the flow owns clicks on the 3D scan). ----
  const [correspondenceTooth, setCorrespondenceTooth] = useState<number | null>(null);

  // ---- STAGE ROUTING (client, 2026-07-26: "Main panel needs to be positioned properly to avoid
  // the use to zoom in and find the cap, there needs to be a proper routing of the panel in the
  // right positioning").
  //
  // MEASURED before this existed: the camera sat 240mm from the arch centroid showing 199mm of
  // jaw, so the 6.16mm cap was 3.1% of the view — 14 pixels on the live 444px stage. The operator
  // had to orbit and scroll to find the thing they had just aligned, every time.
  //
  // The decision of WHERE to look (and, mostly, whether to look at all) is a pure function in
  // viewer/siteRouting so it can be tested without WebGL; what lives here is only the wiring: the
  // veto inputs App already holds, and one effect that fires when the ROUTE KEY changes. Keying
  // on the key rather than on `selection` is load-bearing — `withSites` never returns `prev`, so
  // every mark, brush, rim point and variant change mints a fresh selection object and an effect
  // keyed on it would re-route the camera on all of them.
  const [stageSubject, setStageSubject] = useState<StageSubject>("site");
  const routedKeyRef = useRef<string | null>(null);

  const routeTarget = useMemo(() => {
    const tooth = selection.sites[selection.activeSiteIndex]?.tooth ?? null;
    const row = tooth === null ? null : confirmedSites.find((r) => r.tooth === tooth) ?? null;
    return resolveRouteTarget({
      tooth,
      siteCenter: row ? row.centerMark ?? row.center : null,
      posePosition: tooth === null ? null : sitePoses.get(tooth)?.position ?? null,
      contentGeneration: stageContentVersion,
      subject: stageSubject,
      // Every pointer mode that owns the next click on the scan. The controller re-checks this
      // itself at apply time (see focusOnSite) because the cost of missing one is silent.
      toolActive:
        brushingIndex !== null ||
        markMode !== null ||
        rimPointsIndex !== null ||
        markTrenchTooth !== null ||
        addSiteTooth !== null,
      partPreviewActive: partPreview !== null,
      contentIsArch: stage !== "case" || confirmedSites.length > 0,
      modalOpen: verifyOpen || correspondenceTooth !== null,
    });
  }, [
    selection, confirmedSites, sitePoses, stageContentVersion, stageSubject, brushingIndex, markMode,
    rimPointsIndex, markTrenchTooth, addSiteTooth, partPreview, stage, verifyOpen,
    correspondenceTooth,
  ]);

  const routeKey = routeSignature(routeTarget);

  useEffect(() => {
    if (routeKey === null) return;
    if (routedKeyRef.current === routeKey) return;
    if (!routeTarget) return;
    // The controller returns false when it refuses (a tool armed under us between the memo and
    // this effect). Not recording the key then means the route is retried on the next change
    // rather than silently dropped.
    if (viewerRef.current?.focusOnSite(routeTarget.center, routeTarget.radiusMm)) {
      routedKeyRef.current = routeKey;
    }
  }, [routeKey, routeTarget]);

  /** The subject toggle. "Whole arch" is the operator's way home and takes effect immediately;
   *  "This site" re-arms routing by forgetting what was last routed to. */
  const handleSelectStageSubject = useCallback((next: StageSubject) => {
    setStageSubject(next);
    if (next === "arch") {
      routedKeyRef.current = null;
      viewerRef.current?.frameLoadedContent();
    } else {
      routedKeyRef.current = null;
    }
  }, []);
  const [correspondencePart, setCorrespondencePart] = useState<
    { readonly model: string; readonly variant: string } | null
  >(null);
  const [correspondenceState, setCorrespondenceState] = useState<CorrespondenceState>("loading");
  const [correspondenceError, setCorrespondenceError] = useState<string | null>(null);
  const [correspondenceAnnotation, setCorrespondenceAnnotation] = useState<PartAnnotation | null>(null);
  const [correspondencePairs, setCorrespondencePairs] = useState<CorrespondencePair[]>([]);
  /** Feature whose scan click is armed (null = nothing waiting on the 3D scan). */
  const [correspondenceArmed, setCorrespondenceArmed] = useState<string | null>(null);
  /** FREE POINT armed (client ask 2026-07-26): the canonical-frame click on the PART whose
   *  scan match is awaited. Mutually exclusive with `correspondenceArmed` — arming either
   *  half supersedes the other, the same one-armed-pick rule every scan tool follows. */
  const [correspondenceArmedPoint, setCorrespondenceArmedPoint] = useState<Vec3 | null>(null);
  /** The last APPLIED result's per-pair residuals + RMS, shown under the panel until the next
   *  apply/close — the QC number ("your marks agree to 0.34mm") the multi-pair fit produces. */
  const [correspondenceResiduals, setCorrespondenceResiduals] = useState<
    { readonly tooth: number; readonly pairs: readonly CorrespondenceResidual[]; readonly rmsMm: number } | null
  >(null);
  const [correspondenceNotice, setCorrespondenceNotice] = useState<
    { readonly tooth: number; readonly text: string } | null
  >(null);
  const correspondenceArmedRef = useRef<string | null>(null);
  useEffect(() => {
    correspondenceArmedRef.current = correspondenceArmed;
  }, [correspondenceArmed]);
  const correspondenceArmedPointRef = useRef<Vec3 | null>(null);
  useEffect(() => {
    correspondenceArmedPointRef.current = correspondenceArmedPoint;
  }, [correspondenceArmedPoint]);

  /** Close the FIT-BY-POINTS STAGE and drop its pairs — they are transient input to one POST, so
   *  nothing may survive that describes marks the operator can no longer see. The marks live on
   *  the stage's own scan pane (see FitByPointsStage), so closing it takes them with it. */
  const closeCorrespondence = useCallback(() => {
    setCorrespondenceTooth(null);
    setCorrespondencePart(null);
    setCorrespondenceAnnotation(null);
    setCorrespondencePairs([]);
    setCorrespondenceArmed(null);
    setCorrespondenceArmedPoint(null);
    setCorrespondenceResiduals(null);
    setCorrespondenceError(null);
  }, []);

  /**
   * Open the flow for one seated row: resolve WHICH catalog part it shipped (the row carries
   * "<model>-<variant>" plus the identified variant — see sitePartKey) and fetch that part's
   * marks. The picker lists exactly those, so "trench-02" means the same cutout here as it
   * does in the library browser and in the server's own annotation.
   */
  const handleOpenCorrespondence = useCallback(
    (tooth: number) => {
      const site = runResult?.summary.sites.find((s) => s.tooth === tooth) ?? null;
      if (site === null) return;
      const key = sitePartKey(site.spec, site.variant.identified);
      setCorrespondenceTooth(tooth);
      setCorrespondencePairs([]);
      setCorrespondenceArmed(null);
      setCorrespondenceArmedPoint(null);
      setCorrespondenceResiduals(null);
      setCorrespondenceError(null);
      setCorrespondenceAnnotation(null);
      if (key === null) {
        setCorrespondencePart(null);
        setCorrespondenceState("error");
        setCorrespondenceError(
          `Cannot tell which library part "${site.spec}" is — named correspondences need the part's marks.`,
        );
        return;
      }
      setCorrespondencePart(key);
      setCorrespondenceState("loading");
      fetchPartFeatures(key.model, key.variant)
        .then((annotation) => {
          if (activeCaseIdRef.current === null) return;
          setCorrespondenceAnnotation(annotation);
          setCorrespondenceState("ready");
        })
        .catch((err: unknown) => {
          if (err instanceof ApiError && err.status === 404) {
            // the RUNNING backend predates the features endpoint — the one-click trench tool
            // is unaffected, so this is a restart hint on this panel only, not a toast
            setCorrespondenceState("unavailable");
          } else {
            setCorrespondenceState("error");
            setCorrespondenceError(
              err instanceof ApiError ? err.message : "Failed to load the part's marks.",
            );
          }
        });
    },
    [runResult],
  );

  /**
   * ALIGN TO NAMED MARKS, the POST half: one pair gives the rotation outright, several give a
   * best fit plus per-pair residuals. On success the flow is identical to handleAlignToMark
   * (fold the returned clocking/audit into the row, mint a fresh cache-bust token, reload the
   * stage-1 composite + pose triads) plus the residual read-out. The recorded pairs and their
   * scan marks are then DROPPED: they described the pre-rotation pose, and the cap has moved.
   * A 409 refusal leaves everything — pairs, marks, pose — exactly as it was, so the operator
   * can adjust one mark rather than start over.
   */
  const handleApplyCorrespondence = useCallback(() => {
    const tooth = correspondenceTooth;
    if (tooth === null || !selectedCase || !runResult || nudgeBusyTooth !== null) return;
    if (correspondencePairs.length === 0) return;
    const caseId = selectedCase.id;
    const current = runResult;
    const pairs = correspondencePairs;
    setNudgeBusyTooth(tooth);
    void (async () => {
      try {
        const out = await alignToCorrespondence(caseId, tooth, pairs);
        if (activeCaseIdRef.current !== caseId) return; // stale — user switched cases
        const sites = current.summary.sites.map((s) =>
          s.tooth === tooth ? { ...s, clocking: out.clocking, nudge: out.nudge } : s,
        );
        const updated = { ...current, summary: { ...current.summary, sites } };
        const version = Date.now();
        setRunResult(updated);
        setRunVersion(version);
        setCorrespondenceNotice({ tooth, text: describeCorrespondence(out) });
        const stage1 = buildStage1Composite(sites, caseId);
        void showComposite(stage1, STAGE1_LABEL, caseId, current.filesBase, version);
        void drawPoseTriads(caseId, current.filesBase, sites, version);
        // THE LOOP CLOSES (client's sequence, 2026-07-26: "after confirming, re-show the
        // alignment"). The fit-by-points stage has done its job — its pairs described the
        // PRE-rotation pose and the cap has moved — so it comes down, and the operator lands on
        // the three panels looking at what their marks produced. The outcome line survives in the
        // AlignmentActions block; leaving the stage open would put the residual read behind the
        // very picture it is about.
        closeCorrespondence();
        revealAlignment(tooth);
      } catch (err) {
        setErrorMessage(err instanceof ApiError ? err.message : "Aligning to your marks failed.");
      } finally {
        setNudgeBusyTooth(null);
      }
    })();
  }, [
    correspondenceTooth,
    correspondencePairs,
    selectedCase,
    runResult,
    nudgeBusyTooth,
    showComposite,
    drawPoseTriads,
    closeCorrespondence,
    revealAlignment,
  ]);

  /**
   * Arm the scan click for ONE named feature.
   *
   * The click now lands on the FIT-BY-POINTS STAGE's own scan pane, not on the workflow's single
   * viewer (2026-07-26). That is the whole point of the stage: the client's reference shows the
   * numbered points on the part AND on the scan side by side, which a single stage that has to be
   * one or the other cannot do. It also removes this flow from the queue of one-shot tools
   * competing for the workflow viewer's single armed pick — arming here now touches no shared
   * state, so nothing else has to be disarmed for it.
   */
  const handleArmCorrespondence = useCallback(
    (featureId: string) => {
      if (nudgeBusyTooth !== null) return;
      if (!correspondenceAnnotation?.features.some((f) => f.id === featureId)) return;
      setCorrespondenceArmed(featureId);
      setCorrespondenceArmedPoint(null); // one armed pick at a time — a feature supersedes a free point
    },
    [nudgeBusyTooth, correspondenceAnnotation],
  );

  /**
   * FREE POINT, part half (client ask 2026-07-26): the stage's PART pane resolved a click into
   * the canonical frame — record it as the armed free point and wait for its scan match, exactly
   * like the feature flow. The stage refuses to arm this at all when the part frame cannot be
   * derived (it states the reason on the pane), so the point here is always mappable.
   */
  const handlePickPartPoint = useCallback(
    (canonicalPoint: Vec3) => {
      if (nudgeBusyTooth !== null) return;
      setCorrespondenceArmed(null); // ...and a free point supersedes an armed feature
      setCorrespondenceArmedPoint(canonicalPoint);
    },
    [nudgeBusyTooth],
  );

  /** The stage's scan pane resolved a click for the armed feature OR the armed free point —
   *  record the pair. The marker is drawn from `correspondencePairs` itself, so the dot and
   *  the list cannot disagree. */
  const handleFitPointPicked = useCallback(
    (point: Vec3) => {
      const featureId = correspondenceArmedRef.current;
      if (featureId !== null) {
        const feature = correspondenceAnnotation?.features.find((f) => f.id === featureId) ?? null;
        if (feature === null) return;
        setCorrespondenceArmed(null);
        setCorrespondencePairs((prev) => withPair(prev, featurePair(featureId, feature.kind, point)));
        return;
      }
      const partPoint = correspondenceArmedPointRef.current;
      if (partPoint === null) return;
      setCorrespondenceArmedPoint(null);
      setCorrespondencePairs((prev) => withPair(prev, freePair(partPoint, point)));
    },
    [correspondenceAnnotation],
  );

  const handleCancelCorrespondenceArm = useCallback(() => {
    setCorrespondenceArmed(null);
    setCorrespondenceArmedPoint(null);
  }, []);

  /** `key` is the pair's identity in the CURRENT list: a feature id, or a free point's
   *  positional "point-N" (domain/correspondence.pairKey). */
  const handleRemoveCorrespondencePair = useCallback((key: string) => {
    setCorrespondencePairs((prev) => withoutPair(prev, key));
  }, []);

  const handleClearCorrespondencePairs = useCallback(() => {
    setCorrespondencePairs([]);
  }, []);

  // An open correspondence describes ONE seated row of ONE case. A case switch or a cleared
  // run (re-marking, a fresh detection pass) removes those rows, so the flow closes with them
  // and its scan marks come off the model — never a pair list naming a row that is gone.
  // Expressed as an effect rather than a call inside handleSelectCase/clearRunArtifacts:
  // those are declared far above this state, and every path into "no case / no run" lands
  // here regardless of which one took it.
  useEffect(() => {
    if (selectedCase !== null && runResult !== null) return;
    setCorrespondenceNotice(null);
    if (correspondenceTooth !== null) closeCorrespondence();
  }, [selectedCase, runResult, correspondenceTooth, closeCorrespondence]);

  /**
   * THE TOOTH CHART's click on an OCCUPIED tooth: move the shared site cursor there.
   *
   * "Shared" is the whole design (see components/ToothChart): this writes the SAME
   * `LibrarySelection.activeSiteIndex` the verify dialog's '‹ n ›' stepper writes, so the chart
   * and the stepper cannot drift into two competing ideas of which site is being worked on.
   * Looked up by TOOTH rather than by row index — tooth is the only stable key the confirm rows
   * and the selection share (see withSites), and a row could have been re-numbered in between.
   */
  const handleSelectToothSite = useCallback((tooth: number) => {
    setSelection((prev) => {
      const index = prev.sites.findIndex((s) => s.tooth === tooth);
      return index < 0 ? prev : withActiveSite(prev, index);
    });
  }, []);

  // ---- THE DOCKED COMPARE PANE (client, 2026-07-26: "we should still see side by side the
  // scan and the model that we're selecting so we can compare"). The pane itself is
  // ComparePartPane; what lives here is only which state it reads: collapsed or not (operator's
  // choice — the width floor's auto-collapse is the pane's own), and the row-button handler
  // that points it at a row by moving the SHARED active-site cursor there. The pane never
  // holds its own "which part" state — it always shows the ACTIVE site's declared variant, so
  // the tooth chart, the table rows and the variant cards all drive it through one cursor. ----
  const [comparePaneCollapsed, setComparePaneCollapsed] = useState(false);

  const handleToggleComparePane = useCallback(() => {
    setComparePaneCollapsed((collapsed) => !collapsed);
  }, []);

  /** A row's "compare ⇥": move the shared cursor to that row's tooth and make sure the pane is
   *  open — the pane then shows that row's declared variant by construction. */
  const handleCompareSite = useCallback(
    (index: number) => {
      const tooth = confirmedSitesRef.current[index]?.tooth;
      if (tooth === undefined) return;
      handleSelectToothSite(tooth);
      setComparePaneCollapsed(false);
    },
    [handleSelectToothSite],
  );

  const handleCancelAddSite = useCallback(() => {
    setAddSiteTooth(null);
    viewerRef.current?.exitPointPick();
  }, []);

  /**
   * THE TOOTH CHART's click on an EMPTY tooth (and the "+ Add site" button): OFFER to add a site
   * there. A site is a tooth number AND a position on the arch, so nothing is created here — the
   * clean scan is restored and a one-shot pick is armed ("click tooth 14's healing cap on the
   * scan"). The site appears when the operator places it; Cancel and Escape both abort with
   * nothing changed. Same arm/place/cancel shape as the centre mark and the trench click, and
   * the scan is restored first for the same measured reason (ensureCleanScanView: a click aimed
   * over a composite lands on the overlay, not the scanned surface).
   *
   * The tooth number is decided BEFORE the click — by the chart (explicitly) or by the
   * auto-increment (the next free number) — so the duplicate-tooth guard has nothing to catch;
   * the re-check inside the placement callback is belt-and-braces against a row added elsewhere
   * while the pick was armed.
   *
   * The previous run's results are NOT cleared: a new site does not invalidate the sites that
   * were already seated. Adding one does change the marks signature, so the existing "marks
   * changed — results are for the previous marks" banner appears and offers the recompute.
   */
  const handleAddSiteAtTooth = useCallback(
    (tooth: number) => {
      if (!selectedCase || addSiteToothRef.current !== null) return;
      void (async () => {
        if (!(await ensureCleanScanView())) return;
        setAddSiteTooth(tooth);
        setStage((current) => (current === "case" ? "mark" : current));
        viewerRef.current?.enterPointPick((point) => {
          setAddSiteTooth(null);
          setConfirmedSites((prev) =>
            prev.some((s) => s.tooth === tooth) ? prev : [...prev, { tooth, center: point }],
          );
        });
      })();
    },
    [selectedCase, ensureCleanScanView],
  );

  // The single global Escape listener (see markModeRef's comment above for the ref idiom).
  // Registered HERE, below every cancel handler it calls, because a dependency array is
  // evaluated during render: naming a handler declared further down would hit its temporal
  // dead zone before the component ever mounted.
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (markModeRef.current !== null) {
        handleCancelMark();
      }
      if (rimPointsIndexRef.current !== null) {
        handleCancelRimPoints();
      }
      if (markTrenchToothRef.current !== null) {
        handleCancelMarkTrench();
      }
      // a pending new-site placement is armed the same way, and aborts the same way
      if (addSiteToothRef.current !== null) {
        handleCancelAddSite();
      }
      // both halves of the manual-correspondence flow arm the same one-shot pick
      if (annotateArmedRef.current) {
        handleCancelAnnotateClick();
      }
      if (correspondenceArmedRef.current !== null || correspondenceArmedPointRef.current !== null) {
        handleCancelCorrespondenceArm();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [
    handleCancelMark,
    handleCancelRimPoints,
    handleCancelMarkTrench,
    handleCancelAddSite,
    handleCancelAnnotateClick,
    handleCancelCorrespondenceArm,
  ]);

  /**
   * The doctor's manual sign-off from the verification panel: record (or retract) the
   * confirmation for one site and fold the returned record into the row, so the ✓ chip and
   * the panel state update in place. Purely a recorded human judgment — the backend never
   * changes a pose or a gate from it, so no mesh/triad reload is needed (contrast
   * handleNudgeRotation). A 404 ("run the automation first") surfaces as the toast.
   */
  const handleConfirmAlignment = useCallback(
    (tooth: number, confirmed: boolean, note?: string) => {
      if (!selectedCase || !runResult || confirmBusyTooth !== null) return;
      const caseId = selectedCase.id;
      const current = runResult;
      setConfirmBusyTooth(tooth);
      void (async () => {
        try {
          const out = await confirmAlignment(caseId, tooth, confirmed, note);
          if (activeCaseIdRef.current !== caseId) return; // stale — user switched cases
          const sites = current.summary.sites.map((s) =>
            s.tooth === tooth ? { ...s, doctorConfirmation: out.confirmation } : s,
          );
          setRunResult({ ...current, summary: { ...current.summary, sites } });
        } catch (err) {
          setErrorMessage(err instanceof ApiError ? err.message : "Recording the confirmation failed.");
        } finally {
          setConfirmBusyTooth(null);
        }
      })();
    },
    [selectedCase, runResult, confirmBusyTooth],
  );

  /**
   * POSE EXPORT — pure client work. Everything the file needs is already on screen: the seated
   * matrices the triad pass fetched (sitePoses), the selection that produced them, each row's
   * declared cap, and the row's own provenance (seat method, rotation audit, clock evidence,
   * the doctor's sign-off). Nothing is asked of the backend, so this works on any build.
   *
   * A site with no seated pose is REPORTED rather than quietly dropped: an export missing a site
   * would otherwise be discovered on the importing machine, which is the worst place to find it.
   */
  const handleExportPose = useCallback(
    (tooth: number | null) => {
      if (!selectedCase || !runResult) return;
      const { document: doc, skippedTeeth } = buildPoseTransfer({
        caseId: selectedCase.id,
        exportedAt: new Date(),
        selection: {
          model: selection.model,
          constructionPathId: selection.constructionPathId,
          jaw: selection.jaw,
          gingivalOffsetMm: selection.gingivalOffsetMm,
        },
        rows: runResult.summary.sites,
        poses: sitePoses,
        declaredByTooth: new Map(confirmedSites.map((s) => [s.tooth, s.declaredVariant ?? null])),
        onlyTeeth: tooth === null ? undefined : [tooth],
      });
      if (doc.sites.length === 0) {
        setErrorMessage(
          tooth === null
            ? "Nothing to export — no site has a seated pose yet."
            : `Nothing to export for tooth ${tooth} — it has no seated pose yet.`,
        );
        return;
      }
      downloadTextFile(
        poseTransferFilename(selectedCase.id, tooth),
        serializePoseTransfer(doc),
      );
      if (skippedTeeth.length > 0) {
        setErrorMessage(
          `Exported ${doc.sites.length} site(s) — tooth ${skippedTeeth.join(", ")} left out, no seated pose.`,
        );
      }
    },
    [selectedCase, runResult, selection, sitePoses, confirmedSites],
  );

  /**
   * POSE IMPORT, the reading half: parse the file and judge it against the case in front of the
   * operator BEFORE anything is proposed. Both halves are pure (domain/poseTransfer) — this only
   * does the IO and parks the verdict in state for the panel to render.
   */
  const handleChooseImportFile = useCallback(
    (file: File) => {
      if (!selectedCase) return;
      void (async () => {
        let text: string;
        try {
          text = await file.text();
        } catch {
          setImportState({
            kind: "parse-error",
            filename: file.name,
            message: "that file could not be read.",
          });
          return;
        }
        const parsed = parsePoseTransfer(text);
        if (parsed.kind === "error") {
          setImportState({ kind: "parse-error", filename: file.name, message: parsed.message });
          return;
        }
        setImportState({
          kind: "ready",
          filename: file.name,
          document: parsed.document,
          compatibility: importCompatibility(parsed.document, {
            caseId: selectedCase.id,
            selection: {
              model: selection.model,
              constructionPathId: selection.constructionPathId,
              jaw: selection.jaw,
              gingivalOffsetMm: selection.gingivalOffsetMm,
            },
            siteTeeth: confirmedSites.map((s) => s.tooth),
            declaredByTooth: new Map(
              confirmedSites.map((s) => [s.tooth, s.declaredVariant ?? null]),
            ),
          }),
        });
      })();
    },
    [selectedCase, selection, confirmedSites],
  );

  /**
   * POSE IMPORT, the writing half — and it is a PROPOSAL, never a local overwrite. Each
   * compatible site is POSTed one at a time and judged by the server's own gates (the same
   * stability bound and certification gates every rotation change answers to); the response is
   * the very same shape a nudge returns, so a restored seat folds into the row and refreshes the
   * composite/triads through the identical path (see handleNudgeRotation).
   *
   * A 404 means the RUNNING backend has no import route yet — a NAMED state the panel labels
   * "not yet available" with the route it needs, not a generic failure and never a silent local
   * apply. A 409/422 carries the server's own refusal sentence, shown verbatim.
   */
  const handleApplyImport = useCallback(() => {
    if (importState.kind !== "ready" || !selectedCase || !runResult) return;
    if (!canImport(importState.compatibility)) return;
    const caseId = selectedCase.id;
    const { document: doc, compatibility, filename } = importState;
    const current = runResult;
    void (async () => {
      const lines: string[] = [];
      let sites = current.summary.sites;
      let applied = 0;
      /**
       * Show what the server ACTUALLY accepted — called on the refusal path too. A file whose
       * second site is refused still moved the first: the backend re-emitted that site's meshes,
       * so leaving the screen on the pre-import seat would show a pose that no longer exists.
       * A no-op when nothing was applied.
       */
      const commitApplied = () => {
        if (applied === 0) return;
        const version = Date.now();
        setRunResult({ ...current, summary: { ...current.summary, sites } });
        setRunVersion(version);
        void showComposite(
          buildStage1Composite(sites, caseId),
          STAGE1_LABEL,
          caseId,
          current.filesBase,
          version,
        );
        void drawPoseTriads(caseId, current.filesBase, sites, version);
      };
      for (const tooth of compatibility.teeth) {
        const site = doc.sites.find((s) => s.tooth === tooth);
        if (site === undefined) continue;
        setImportState({ kind: "submitting", filename, tooth });
        try {
          const out = await importPose(caseId, tooth, doc, site);
          if (activeCaseIdRef.current !== caseId) return; // stale — user switched cases
          sites = sites.map((s) =>
            s.tooth === tooth ? { ...s, clocking: out.clocking, nudge: out.nudge } : s,
          );
          applied += 1;
          lines.push(
            `tooth ${tooth} — pose proposed and accepted; codes read ${describeNotchResidual(out.clocking)}`,
          );
        } catch (err) {
          if (activeCaseIdRef.current !== caseId) return;
          commitApplied();
          if (err instanceof ApiError && err.status === 404) {
            setImportState({ kind: "unavailable" });
            return;
          }
          setImportState({
            kind: "refused",
            message: err instanceof ApiError ? err.message : "Importing the pose failed.",
          });
          return;
        }
      }
      if (activeCaseIdRef.current !== caseId) return;
      setImportState({ kind: "applied", lines });
      commitApplied();
    })();
  }, [importState, selectedCase, runResult, showComposite, drawPoseTriads]);

  const duplicateTeeth = findDuplicateTeeth(confirmedSites);
  const hasDuplicateTeeth = duplicateTeeth.length > 0;
  /**
   * THE RUN GATE, read once for every process control OUTSIDE RunActions — today just the stale
   * banner's "Recompute alignment". That button was the fifth route: it judged only duplicate
   * teeth, so after a run it stayed live while the reviews were cleared underneath it (adding a
   * site, or changing the system/construction/relief, both drops reviews AND makes the run
   * stale). It never actually processed — handleRunAutomation's gate refused it — but a live
   * button that answers with a toast is the dead-button-with-no-reason the gate exists to avoid.
   * Same list, same sentence as RunActions prints.
   */
  const runGateBlockers = runBlockers({ selection, duplicateTeeth });
  const runGateClear = runGateBlockers.length === 0;
  // Declaration is REQUIRED (measured 2026-07-15: auto-identification is only 1/4 correct on
  // the labeled arches and flips diameter classes, whereas the doctor's declaration drives a
  // 4/4-correct alignment). A site left on "auto" blocks confirm + run — the automation still
  // measures the rim as an independent cross-check, but the doctor's pick is authoritative.
  const undeclaredSites = undeclaredSiteNumbers(confirmedSites);
  const hasUndeclared = undeclaredSites.length > 0;
  /**
   * OFFSET HONESTY (client ask 2026-07-25): what the LAST run's emitted parts actually achieved
   * against the requested gingival relief — requesting 0.20 mm measures ~0.13-0.15 mm through the
   * SDF round trip. Derived every render from runResult (a handful of sites), same rationale as
   * identifiedVariantByTooth below; null until a run has measured it, which both read-outs state
   * in words rather than echoing the request back as if confirmed.
   */
  const achievedOffset = runResult ? achievedGingivalOffset(runResult.summary.sites) : null;
  /**
   * THE CEILING the operator is shown beside the offset input, and THE CLAMP the last run had to
   * apply. Both derived every render from state that is already here, same rationale as
   * achievedOffset above.
   *
   * The ceiling is folded across EVERY chosen cap, not just the active site's: one relief is typed
   * for the whole case, so the number that governs is the tightest of the caps' ceilings. Showing
   * only the site the stepper happens to be on would let another site clamp unseen — which is the
   * exact surprise this feature exists to remove.
   */
  const chosenConstruction = selection.constructionPathId;
  const chosenModel = selection.model;
  const siteReliefLimits: SiteReliefLimit[] =
    chosenConstruction !== null && chosenModel !== null
      ? selection.sites.flatMap((site) => {
          if (site.variantId === null) return [];
          const state = reliefLimits.get(
            reliefLimitKey(chosenConstruction, chosenModel, site.variantId),
          );
          return state ? [{ tooth: site.tooth, variantId: site.variantId, state }] : [];
        })
      : [];
  const ceiling = ceilingReadout(siteReliefLimits);
  const reliefClamps = clampedSites(runResult?.summary.sites ?? []);
  const canConfirmAll = confirmedSites.length > 0 && !hasDuplicateTeeth && !hasUndeclared;
  // tooth -> identified variant from the LATEST run result, for the cap-variant picker's
  // "auto — suggested: X" hint (Item 1). Recomputed every render from runResult — cheap (a
  // handful of sites) and always in sync with the most recent run/recompute, no separate effect.
  const identifiedVariantByTooth = new Map(
    (runResult?.summary.sites ?? []).map((s) => [s.tooth, s.variant.identified] as const),
  );
  // Per confirm-row capture verdict: the detection pass assessed every proposal and
  // curated suggested site; a row inherits the assessment measured nearest its own
  // centre (within 4mm — see captureNear). Recomputed every render, same rationale as
  // identifiedVariantByTooth above. null (no chip) until detection has run.
  const siteCaptures = confirmedSites.map((s) =>
    proposeResult ? captureNear(s.center, proposeResult.captureSites) : null,
  );
  /**
   * THE TOOTH CHART's view of the case — the confirm rows, the per-site acknowledgment, the
   * capture verdicts and the last run's rows, folded into one per-tooth state (domain/toothChart).
   * Derived every render like siteCaptures above: a handful of sites, and it must never lag the
   * panels it summarises. `activeChartTooth` is the SHARED cursor read back out of the selection,
   * which is what keeps the chart and the verify dialog's stepper pointing at the same site.
   */
  const chartSites = chartSitesFrom({
    rows: confirmedSites,
    reviewedTeeth: selection.sites.filter((s) => s.reviewed).map((s) => s.tooth),
    captures: siteCaptures.map((c) => c?.verdict ?? null),
    runRows: runResult?.summary.sites ?? [],
    duplicateTeeth,
    jaw: selection.jaw,
  });
  const activeChartTooth = selection.sites[selection.activeSiteIndex]?.tooth ?? null;
  /**
   * WHAT THE COMPARE PANE SHOWS: the ACTIVE site's declared variant, resolved from the catalog
   * exactly the way the verify dialog resolves its pane 1 (findVariantEntry over the same
   * groups) — so the part beside the scan is the part the dialog would show, by construction.
   * Derived every render like the chart above. The pane mounts only on Mark & declare with a
   * case loaded, and comes down while a modal 3D surface is up (the verify dialog's three panes,
   * the fit-by-points stage): one extra live WebGL context is the budget, never two.
   */
  const compareEntry = findVariantEntry(
    catalogGroups,
    selection.model,
    selection.sites[selection.activeSiteIndex]?.variantId ?? null,
  );
  /** WHY compareEntry is null, when it is — review 2026-07-26: the pane must not ask for a
   *  declaration that already exists (catalog still loading / down) or that no site can yet
   *  receive; the sentence for each cause lives with the pane, the facts live here. */
  const compareWhyEmpty = compareEmptyReason({
    sitesMarked: selection.sites.length > 0,
    declared: (selection.sites[selection.activeSiteIndex]?.variantId ?? null) !== null,
    catalog: catalogState,
  });
  const comparePaneMounted =
    stage === "mark" && selectedCase !== null && !verifyOpen && correspondenceTooth === null;
  /** The tooth whose variant the pane is showing right now — the table's pressed-state input. */
  const compareTooth =
    comparePaneMounted && !comparePaneCollapsed && compareEntry !== null ? activeChartTooth : null;
  // What the "automated tooth number increasing" toggle would use for the next site — shown ON
  // the add button, so the number is visible before anything is created.
  const nextAutoTooth = nextToothNumber({
    jaw: selection.jaw,
    usedTeeth: confirmedSites.map((s) => s.tooth),
    lastTooth: confirmedSites[confirmedSites.length - 1]?.tooth ?? null,
  });
  /**
   * Why the chart cannot add a site right now — one sentence, or null when it can. Adding ARMS A
   * CLICK ON THE SCAN, and five other tools can already hold that one-shot pick. The list and its
   * sentences live in domain/toothChart (`addSiteBlockedReason`) so every owner is named in one
   * place and pinned by tests — it was an inline ternary here, and it named only four of the six.
   */
  const addSiteBlockedReason = blockedReasonForAddSite({
    brushing: brushingIndex !== null,
    placingMark: markMode !== null,
    rimPoints: rimPointsIndex !== null,
    trenchMark: markTrenchTooth !== null,
    correspondencePoint: correspondenceArmed !== null,
    libraryMark: annotateArmed,
    runInFlight: runBusy,
  });
  // Which sites have a seated pose on hand to export, and which do not (stated, not hidden).
  const runTeeth = (runResult?.summary.sites ?? []).map((s) => s.tooth);
  const exportableTeeth = runTeeth.filter((t) => sitePoses.has(t));
  const missingPoseTeeth = runTeeth.filter((t) => !sitePoses.has(t));

  /** The library browser's annotation panel, when one is open on the previewed card. */
  const annotatorContext: PartAnnotatorContext | null =
    annotateTarget === null
      ? null
      : {
          state: annotateState,
          errorMessage: annotateError,
          model: annotateTarget.model,
          variant: annotateTarget.variant,
          drafts: annotateDrafts,
          autoSeeded: annotationSaved?.autoSeeded ?? true,
          revisedAt: annotationSaved?.revisedAt ?? null,
          selectedKey: annotateSelected,
          kind: annotateKind,
          armed: annotateArmed,
          busy: annotateBusy,
          dirty: draftsAreDirty(annotateDrafts, annotationSaved?.features ?? []),
          canPlace: annotateCanPlace,
          onSelect: setAnnotateSelected,
          onChangeKind: setAnnotateKind,
          onArm: handleArmAnnotateClick,
          onCancelArm: handleCancelAnnotateClick,
          onRemove: (key: string) => setAnnotateDrafts((prev) => removeDraft(prev, key)),
          onSave: handleSaveAnnotation,
          onReset: handleResetAnnotation,
          onClose: closeAnnotator,
        };

  /** The FIT-BY-POINTS stage's controls — built only while a row has the flow open (one at a
   *  time: the pairs describe one seated site, and the stage is modal over the workflow). */
  const fitPointsRow: RunSiteResult | null =
    correspondenceTooth === null
      ? null
      : runResult?.summary.sites.find((s) => s.tooth === correspondenceTooth) ?? null;

  const fitPointsControls: CorrespondenceControls | null =
    fitPointsRow === null
      ? null
      : {
          state: correspondenceState,
          errorMessage: correspondenceError,
          model: correspondencePart?.model ?? "—",
          variant: correspondencePart?.variant ?? fitPointsRow.variant.identified,
          features: correspondenceAnnotation?.features ?? [],
          autoSeeded: correspondenceAnnotation?.autoSeeded ?? false,
          pairs: correspondencePairs,
          armedFeatureId: correspondenceArmed,
          armedFreePoint: correspondenceArmedPoint,
          busy: nudgeBusyTooth === fitPointsRow.tooth,
          residuals:
            correspondenceResiduals?.tooth === fitPointsRow.tooth
              ? correspondenceResiduals.pairs
              : null,
          residualRmsMm:
            correspondenceResiduals?.tooth === fitPointsRow.tooth
              ? correspondenceResiduals.rmsMm
              : null,
          onArm: handleArmCorrespondence,
          onCancelArm: handleCancelCorrespondenceArm,
          onPickPartPoint: handlePickPartPoint,
          onRemovePair: handleRemoveCorrespondencePair,
          onClearPairs: handleClearCorrespondencePairs,
          onApply: handleApplyCorrespondence,
          onClose: closeCorrespondence,
        };

  /** The library part the fit-by-points stage draws on its left — resolved out of the catalog
   *  the browser already fetched, so the flow costs no extra request. */
  const fitPointsEntry =
    correspondencePart === null
      ? null
      : findVariantEntry(catalogGroups, correspondencePart.model, correspondencePart.variant);
  const fitPointsCenter: Vec3 | null =
    correspondenceTooth === null
      ? null
      : (() => {
          const row = confirmedSites.find((s) => s.tooth === correspondenceTooth);
          return row ? row.centerMark ?? row.center : null;
        })();

  // ---- THE WORKFLOW, JUDGED AGAINST THE CASE (domain/workflow) ----
  const selectionComplete = missingSelections(selection).length === 0;
  const reviewedAll = selection.sites.length > 0 && selection.sites.every((s) => s.reviewed);
  const stages = workflowStages({
    hasCase: selectedCase !== null,
    siteCount: confirmedSites.length,
    declaredSiteCount: confirmedSites.filter((s) => (s.declaredVariant ?? null) !== null).length,
    selectionComplete,
    reviewedAll,
    hasRun: runResult !== null,
    runStale: runIsStale,
  });
  const suggestedStage = nextStage(stages);

  /** The results block, docked over the 3D stage (see `drawerOpen`). Everything a completed run
   *  produced — the corrections first, because that is the client's next question when an
   *  alignment is not right, then the numbers, the guidance, the staged views and the files. */
  const resultsDrawer =
    runResult && selectedCase ? (
      <section
        className={`stage-drawer${drawerOpen ? "" : " stage-drawer--collapsed"}`}
        aria-labelledby="stage-drawer-heading"
      >
        <header className="stage-drawer__bar">
          <button
            type="button"
            className="stage-drawer__toggle"
            aria-expanded={drawerOpen}
            onClick={() => setDrawerOpen((open) => !open)}
          >
            <span aria-hidden="true">{drawerOpen ? "▾" : "▸"}</span>
            <span id="stage-drawer-heading">
              Results — {runResult.summary.sites.length} site
              {runResult.summary.sites.length === 1 ? "" : "s"} aligned
            </span>
          </button>
          {lastRunAt && (
            <span className="stage-drawer__meta">
              {formatRunTimestamp(lastRunAt, runResult.durationS)}
            </span>
          )}
          <button
            type="button"
            className="button button--ghost button--small"
            onClick={() => void handleCopyRunReport()}
          >
            {reportCopied ? "copied ✓" : "Copy run report"}
          </button>
        </header>
        {drawerOpen && (
          <div className={runIsStale ? "stage-drawer__body results-block--stale" : "stage-drawer__body"}>
            {/* THE CORRECTIONS, FIRST AND VISIBLE (client, 2026-07-26): best fit and fit by
                points used to be reachable only by expanding a rotation control inside a cell
                of the table below. */}
            <AlignmentActions
              sites={runResult.summary.sites}
              context={{
                busyTooth: nudgeBusyTooth,
                armedTrenchTooth: markTrenchTooth,
                bestFit: {
                  matchingDiameterMm: bestFitDiameterMm,
                  apply: bestFitApply,
                  unavailable: bestFitUnavailable,
                  busyTooth: nudgeBusyTooth,
                  notice: bestFitNotice,
                  confirmation: bestFitConfirmation,
                  onChangeDiameter: setBestFitDiameterMm,
                  onToggleApply: setBestFitApply,
                  onRun: handleBestFit,
                  onSearchWider: handleBestFitWider,
                },
                correspondenceNotice: correspondenceNotice,
                markTrenchNotice: alignMarkNotice,
                onOpenFitByPoints: handleOpenCorrespondence,
                onStartMarkTrench: handleStartMarkTrench,
                onCancelMarkTrench: handleCancelMarkTrench,
                onReverify: revealAlignment,
              }}
            />
            <ResultsTable
              sites={runResult.summary.sites}
              onAdjustRotationIn3D={revealAlignment}
              verification={{
                caseId: selectedCase.id,
                filesBase: runResult.filesBase,
                runVersion,
                packageFiles: runResult.summary.packageFiles,
                onConfirm: handleConfirmAlignment,
                confirmBusyTooth,
              }}
            />
            <GuidancePanel sites={runResult.summary.sites} />
            <FlagsAlerts sites={runResult.summary.sites} />
            <ViewerControls
              sites={runResult.summary.sites}
              caseId={selectedCase.id}
              onShowComposite={handleShowComposite}
              activeLabel={activeViewLabel}
            />
            <PackageFileList
              files={runResult.summary.packageFiles}
              filesBase={runResult.filesBase}
              runVersion={runVersion}
            />
            {/* POSE TRANSFER: export is pure client work off the poses already fetched for the
                triads; import is an OPERATOR WRITE and goes out as a proposal for the server's
                gates to judge and audit (see handleApplyImport). */}
            <PoseTransferPanel
              caseId={selectedCase.id}
              exportableTeeth={exportableTeeth}
              missingPoseTeeth={missingPoseTeeth}
              importState={importState}
              onExport={handleExportPose}
              onChooseFile={handleChooseImportFile}
              onApplyImport={handleApplyImport}
              onClearImport={() => setImportState({ kind: "idle" })}
            />
          </div>
        )}
      </section>
    ) : null;

  return (
    <div className="app-shell">
      <Header libraryOpen={libraryOpen} onToggleLibrary={handleToggleLibrary} />
      <div className="workbench">
        {/* THE RAIL: the client's sequence, judged against the case (domain/workflow) and used
            as the navigation — the work column shows ONE stage's panel, so the shell stops
            being a scroll through every step at once and the 3D keeps the width. */}
        <WorkflowRail stages={stages} current={stage} onSelect={setStage} />

        <div className="workbench__work">
          {/* The library browser takes over the work column while it is open rather than
              covering the stage: its cards PREVIEW parts on the 3D viewer, which has to stay
              visible for the preview to be worth anything. */}
          {libraryOpen ? (
            <LibraryBrowser
              state={catalogState === "idle" ? "loading" : catalogState}
              errorMessage={catalogError}
              groups={catalogGroups}
              activeModel={activeLibraryModel}
              previewedKey={partPreview?.catalogKey ?? null}
              onSelectModel={setActiveLibraryModel}
              onPreviewEntry={handlePreviewCatalogEntry}
              onRetry={loadCatalog}
              onClose={handleToggleLibrary}
              onAnnotateEntry={handleAnnotateEntry}
              annotator={annotatorContext}
            />
          ) : (
            <>
              {/* THE DENTAL TOOTH CHART (their left rail): the case's sites drawn anatomically,
                  and the picker that drives the SAME cursor the verify dialog's stepper does.
                  It stays put across every stage — it is the site CURSOR, which verify and the
                  post-run corrections read just as much as marking does. */}
              {selectedCase && (
                <ToothChart
                  jaw={selection.jaw}
                  sites={chartSites}
                  activeTooth={activeChartTooth}
                  armedTooth={addSiteTooth}
                  autoNumber={autoToothNumber}
                  nextTooth={nextAutoTooth}
                  addBlockedReason={addSiteBlockedReason}
                  onSelectTooth={handleSelectToothSite}
                  onAddTooth={handleAddSiteAtTooth}
                  onToggleAutoNumber={setAutoToothNumber}
                  onCancelAdd={handleCancelAddSite}
                />
              )}

              {stage === "case" && (
                <CaseSelect
                  cases={cases}
                  selectedCaseId={selectedCase?.id ?? null}
                  loadingCases={loadingCases}
                  loadingScanProgress={scanProgress}
                  onSelect={handleSelectCase}
                />
              )}

              {/* STEP 2 — ONE FLOW (client, 2026-07-26): detect, the mark/declare table, and
                  the SAME SelectionColumn the verify dialog mounts, stacked in one work column.
                  The old separate Library-selection stop is deleted, not linked to. */}
              {stage === "mark" && selectedCase && (
                <MarkDeclareStage
                  propose={{
                    disabled: !selectedCase,
                    busy: proposeBusy,
                    elapsedS: proposeElapsedS,
                    result: proposeResult,
                    showMarkers: showProposalMarkers,
                    onRunDetection: handleRunDetection,
                    onToggleMarkers: handleToggleProposalMarkers,
                  }}
                  confirm={{
                    sites: confirmedSites,
                    captures: siteCaptures,
                    disabled: !canConfirmAll,
                    brushingIndex,
                    markMode,
                    rimPointsIndex,
                    library,
                    libraryLoading,
                    identifiedVariantByTooth,
                    compareTooth,
                    onChangeTooth: handleChangeTooth,
                    onChangeDeclaredVariant: handleChangeDeclaredVariant,
                    onCompare: handleCompareSite,
                    onSelectSite: handleSelectToothSite,
                    onStartBrush: handleStartBrush,
                    onFinishBrush: handleFinishBrush,
                    onClearBrushStroke: handleClearBrushStroke,
                    onClearMarkedPoints: handleClearMarkedPoints,
                    onStartMark: handleStartMark,
                    onCancelMark: handleCancelMark,
                    onClearMark: handleClearMark,
                    onStartRimPoints: handleStartRimPoints,
                    onFinishRimPoints: handleFinishRimPoints,
                    onCancelRimPoints: handleCancelRimPoints,
                    onClearRim: handleClearRim,
                    onConfirmAll: handleConfirmAll,
                    noSystemHint:
                      selection.model === null
                        ? "No implant system selected — choose one on the cards below; its cap sizes then appear in this column."
                        : null,
                  }}
                  selectionColumn={{
                    selection,
                    activeSiteNumber:
                      selection.sites.length > 0 ? selection.activeSiteIndex + 1 : null,
                    activeTooth: activeChartTooth,
                    libraryState: catalogState === "idle" ? "loading" : catalogState,
                    libraryError: catalogError,
                    groups: catalogGroups,
                    constructionsState,
                    constructionsError,
                    constructions,
                    suggestedModel: selectedCase.suggestedModel,
                    suggestedConstruction: selectedCase.suggestedConstruction,
                    // ONE wiring for BOTH mounts (see selectionColumnWiring): the dialog and
                    // this stage route every control through the same transitions into the
                    // same handleSelectionChange.
                    ...selectionColumnHandlers(selection, handleSelectionChange),
                    achievedOffset,
                    ceiling,
                    clamps: reliefClamps,
                    onRetry: handleRetryCatalogs,
                  }}
                />
              )}

              {stage === "verify" && selectedCase && (
                <SelectionSummary selection={selection} open={verifyOpen} onOpen={handleOpenVerify} />
              )}

              {stage === "process" && selectedCase && (
                <section className="panel" aria-labelledby="process-heading">
                  <h2 id="process-heading" className="panel__title">
                    Step 4 · Process
                    <span className="panel__title-case"> — {selectedCase.id}</span>
                  </h2>
                  {/* THE PROCESS ROUTES AND THEIR GATE, in one component (see RunActions): the
                      quick "Run automation", the review route, and "⟳ rerun live" all read ONE
                      blocker list — including the client's per-site acknowledgment — and print
                      it next to themselves, so a disabled button always says why. */}
                  <RunActions
                    selection={selection}
                    duplicateTeeth={duplicateTeeth}
                    undeclaredSiteNumbers={undeclaredSites}
                    runBusy={runBusy}
                    cached={runResult?.cached ?? false}
                    achievedOffset={achievedOffset}
                    onRun={() => handleRunAutomation(false)}
                    onRerunLive={() => handleRunAutomation(true)}
                    onOpenVerify={handleOpenVerify}
                  />

                  {runBusy && (
                    <div className="busy-state" role="status" aria-live="polite">
                      <span className="busy-state__spinner" aria-hidden="true" />
                      <span className="busy-state__message">
                        {recomputeBusy
                          ? "recomputing with the updated marks…"
                          : "aligning, identifying variant, boring screw channel…"}
                      </span>
                      <span className="busy-state__elapsed">{runElapsedS.toFixed(0)}s elapsed</span>
                    </div>
                  )}

                  {/* THE REFUSAL, READABLE (client, 2026-07-25). A run the backend refused is
                      not a transport error: the server's own sentence names the tooth, the
                      part, the measured channel radius and the number to lower. */}
                  {runRefusal && !runBusy && (
                    <RunRefusalNotice refusal={runRefusal} onDismiss={() => setRunRefusal(null)} />
                  )}

                  {/* THE CLAMP, ONCE FOR THE RUN. The per-row chip says which tooth; this says
                      it where nobody can miss it, because the delivered part carries a relief
                      the lab did not ask for. */}
                  {!runBusy && <ReliefClampNotice clamps={reliefClamps} />}

                  {runResult && runResult.cached && !runBusy && !runIsStale && (
                    <p className="panel__hint">precomputed — click ⟳ for a live run</p>
                  )}

                  {runIsStale && !runBusy && (
                    <div className="stale-banner" role="status" aria-live="polite">
                      <span className="stale-banner__text">
                        marks changed — results are for the previous marks
                      </span>
                      <button
                        type="button"
                        className="button button--primary button--small"
                        disabled={!runGateClear || recomputeBusy}
                        title={
                          runGateClear
                            ? "Re-run the automation with the marks now on screen"
                            : `Cannot process yet — still needed: ${runGateBlockers.join("; ")}`
                        }
                        onClick={handleRecompute}
                      >
                        Recompute alignment
                      </button>
                      {!runGateClear && (
                        <span className="stale-banner__blocked">
                          Still needed: {runGateBlockers.join("; ")}.
                        </span>
                      )}
                    </div>
                  )}
                </section>
              )}

              {/* The one nudge the rail cannot give by itself: where the case actually is,
                  offered as an action rather than as a jump the operator did not ask for. */}
              {suggestedStage !== stage && (
                <div className="panel__actions panel__actions--advance">
                  <button
                    type="button"
                    className="button button--primary"
                    onClick={() => setStage(suggestedStage)}
                  >
                    Continue → {stages.find((s) => s.id === suggestedStage)?.label}
                  </button>
                </div>
              )}
            </>
          )}
        </div>

        {/* THE STAGE: the 3D is the product, so it takes every pixel the shell can give it at
            every step (client, 2026-07-26). The results dock over it rather than beside it —
            a fifteen-column table needs this width, and it collapses to a bar when the
            operator wants the model back. While Mark & declare is open, the stage SPLITS:
            the scan keeps the main viewer (left, with its site routing untouched — the docked
            pane never hijacks it) and the compare pane shows the active site's declared
            variant beside it (client, 2026-07-26: "side by side the scan and the model"). */}
        <div className="workbench__stage">
          <div className="stage-split">
            <div className="viewer3d-wrap">
              <Viewer3D ref={viewerRef} ariaLabel="3D viewer of the doctor's scan and automation output" />
              <ViewOrientationBar
                onSelect={(view: AnatomyViewId) => viewerRef.current?.setAnatomyView(view)}
                subject={stageSubject}
                onSelectSubject={handleSelectStageSubject}
                siteAvailable={routeTarget !== null || stageSubject === "arch"}
              />
              <PartPreviewChip
                preview={
                  partPreview
                    ? {
                        variant: partPreview.variant,
                        rimDiameterMm: partPreview.rimDiameterMm,
                        heightMm: partPreview.heightMm,
                        // catalog previews belong to no row, hence no tooth on the chip
                        tooth: null,
                        loading: partPreview.loading,
                      }
                    : null
                }
                canReturnToScan={selectedCase !== null}
                onBackToScan={handleExitPartPreview}
              />
              <Legend roles={legendRoles} />
              <ControlsHint />
            </div>
            {comparePaneMounted && (
              <ComparePartPane
                variant={
                  compareEntry
                    ? {
                        variant: compareEntry.variant,
                        rimDiameterMm: compareEntry.rimDiameterMm,
                        heightMm: compareEntry.heightMm,
                        meshUrl: compareEntry.meshUrl,
                      }
                    : null
                }
                emptyReason={compareWhyEmpty}
                tooth={activeChartTooth}
                collapsed={comparePaneCollapsed}
                onToggleCollapsed={handleToggleComparePane}
              />
            )}
          </div>
          {resultsDrawer}
        </div>
      </div>
      <Footer />

      {/* THE VERIFICATION ROUTE (client's library-selection dialog, 2026-07-25) — a modal gate over the
          workflow, not a replacement for it: the process stage's quick path keeps working, and
          both land on the same results. */}
      {verifyOpen && selectedCase && (
        <VerifyStage
          caseItem={selectedCase}
          sites={confirmedSites}
          selection={selection}
          onSelectionChange={handleSelectionChange}
          catalogState={catalogState === "idle" ? "loading" : catalogState}
          catalogError={catalogError}
          groups={catalogGroups}
          constructionsState={constructionsState}
          constructionsError={constructionsError}
          constructions={constructions}
          onRetryCatalogs={handleRetryCatalogs}
          runBusy={runBusy}
          achievedOffset={achievedOffset}
          ceiling={ceiling}
          clamps={reliefClamps}
          refreshToken={runVersion}
          rotation={verifyRotation}
          onProcess={handleProcessFromDialog}
          onClose={() => setVerifyOpen(false)}
        />
      )}

      {/* FIT BY POINTS (client, 2026-07-26): the correspondence flow as a STAGE — the library
          part's numbered features on the left, the scanned cap on the right, the pair list
          between them. Everything it POSTs is unchanged; what changed is that it can be found. */}
      {fitPointsControls && fitPointsRow && selectedCase && correspondencePart && (
        <FitByPointsStage
          caseId={selectedCase.id}
          tooth={fitPointsRow.tooth}
          model={correspondencePart.model}
          variant={correspondencePart.variant}
          partMeshUrl={fitPointsEntry?.meshUrl ?? null}
          siteCenter={fitPointsCenter}
          controls={fitPointsControls}
          onPickScanPoint={handleFitPointPicked}
          onClose={closeCorrespondence}
        />
      )}

      {errorMessage && <ErrorToast message={errorMessage} onDismiss={() => setErrorMessage(null)} />}
    </div>
  );
}
