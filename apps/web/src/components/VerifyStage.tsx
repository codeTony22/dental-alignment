import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, fetchSiteDeviation, previewSiteAlignment } from "../api/client";
import { cachedMeshUrl } from "../api/meshCache";
import type {
  Case,
  ConfirmedSite,
  ConstructionPart,
  LibraryCatalogGroup,
  SiteDeviation,
  Vec3,
} from "../domain/types";
import { marksSignatureFor } from "../domain/types";
import type { AchievedGingivalOffset } from "../domain/gingivalOffset";
import type { CeilingReadout } from "../domain/reliefLimit";
import type { SiteReliefClamp } from "../domain/reliefClamp";
import type { LibrarySelection } from "../domain/librarySelection";
import {
  findVariantEntry,
  stepSite,
  withActiveSite,
  withReviewed,
} from "../domain/librarySelection";
import { selectionColumnHandlers } from "./selectionColumnWiring";
import { buildScaleColors, type DeviationScaleId } from "../viewer/deviationColormap";
import { CAP_REGION_RADIUS_MM, cropTrianglesNear, triangleCount } from "../viewer/meshCrop";
import { PALETTE, paletteHex } from "../viewer/palette";
import { computePartFrame } from "../viewer/partFrame";
import { computeAnatomyFrame } from "../viewer/anatomyOrientation";
import { OrbitLinkGroup, loadStlPositions, type VerifyLayerGeometry } from "../viewer/verifyScene";
import { scanPositionsFor } from "../viewer/scanPositions";
import { VerifyViewer, type VerifyViewerLayer } from "../viewer/VerifyViewer";
import { VerifyDialog } from "./VerifyDialog";
import type { CatalogFetchState } from "./SelectionColumn";
import type { VerifyPanelId, VerifyPanelSpec } from "./VerifyPanels";
import type { RotationDialSpec } from "./RotationDial";

/** Layer ids, per panel. Named constants because the layer control callbacks address them by
 *  string (the panel chrome is data-driven) and a typo would silently do nothing. */
const LAYER_PART = "part";
const LAYER_SCAN = "scan";
const LAYER_DEVIATION = "deviation";

/** The client's own defaults for the union pane: the scan half-transparent so the coloured cap
 *  reads through it, the cap solid. Panels 1-2 start fully opaque. */
const DEFAULT_LAYER_STATE: Readonly<Record<string, { visible: boolean; opacity: number }>> = {
  "library:part": { visible: true, opacity: 1 },
  "scan:scan": { visible: true, opacity: 1 },
  "union:scan": { visible: true, opacity: 0.45 },
  "union:deviation": { visible: true, opacity: 1 },
};

type LayerState = Record<string, { visible: boolean; opacity: number }>;

function layerKey(panelId: VerifyPanelId, layerId: string): string {
  return `${panelId}:${layerId}`;
}

/** The deviation fetch's lifecycle as the UNION pane sees it. "none" is the honest 404: this
 *  site has not been SHIPPED yet, so there is no packaged overlay to colour — which is the
 *  moment the pre-run preview below takes over. */
type DeviationState = "idle" | "loading" | "ready" | "none" | "error";

/**
 * The PRE-RUN PREVIEW's lifecycle (client, 2026-07-26: "verify must work on the first pass,
 * automatically"). "unavailable" is the RUNNING backend's 404 — it predates the endpoint — which
 * the pane states as a restart hint rather than as a failure, exactly like every other endpoint
 * this app added after the fact.
 */
type PreviewState = "idle" | "computing" | "ready" | "unavailable" | "error";

export interface VerifyStageProps {
  readonly caseItem: Case;
  /** The step-2 rows — the source of each site's marked centre (what the scan panes frame on). */
  readonly sites: readonly ConfirmedSite[];
  readonly selection: LibrarySelection;
  readonly onSelectionChange: (next: LibrarySelection) => void;
  readonly catalogState: CatalogFetchState;
  readonly catalogError: string | null;
  readonly groups: readonly LibraryCatalogGroup[];
  readonly constructionsState: CatalogFetchState;
  readonly constructionsError: string | null;
  readonly constructions: readonly ConstructionPart[];
  readonly onRetryCatalogs: () => void;
  readonly runBusy: boolean;
  /** What the LAST run actually achieved against the requested gingival relief — shown beside
   *  the request in the selection column. null before any measured run. */
  readonly achievedOffset: AchievedGingivalOffset | null;
  /**
   * THE CEILING for the chosen (construction part x caps): what the selection column shows beside
   * the offset input, and warns against when the typed relief is over it. Owned by App because the
   * quick path in step 4 processes with the very same selection.
   */
  readonly ceiling: CeilingReadout;
  /** What the LAST run applied where it had to clamp the relief — empty when nothing clamped. */
  readonly clamps: readonly SiteReliefClamp[];
  /**
   * Bumped whenever the seated result changes underneath the dialog — a run, a nudge, an
   * align-to-mark, a best fit. The union pane re-fetches its deviation on it, so "re-show the
   * alignment after a fit" actually shows the NEW alignment rather than the pre-fit read.
   */
  readonly refreshToken: number | null;
  /**
   * THE ROTATION CONTROL FOR THE ACTIVE SITE, resolved by App (client, 2026-07-26). null when
   * this site has no shipped seat to rotate — a rotation step re-emits the site's package, which
   * a pre-run preview has not produced, so offering the control before Process would be a button
   * that can only fail. Each applied step bumps `refreshToken`, which is what makes the union
   * pane redraw the NEW pose: the point of moving the control onto the 3D in the first place.
   */
  readonly rotation: RotationDialSpec | null;
  readonly onProcess: () => void;
  readonly onClose: () => void;
}

/**
 * THE VERIFY DIALOG'S STAGE: everything the three panels need to actually show something.
 *
 * It owns the meshes (and only the meshes) — the selection itself lives in App, because the
 * quick path in step 4 runs with the very same selection and neither route may quietly disagree
 * with the other about what was chosen.
 *
 * The scan is parsed ONCE per case and CROPPED per site (see meshCrop): three live WebGL panes
 * must not each carry a 22 MB arch to show one 6 mm cap. The union pane's coloured mesh is the
 * deviation payload the API already computes for the acceptance difference map — the same
 * instrument, never a second opinion — and it is honest about what it is: a read of the LAST
 * COMPLETED RUN for this site, flagged when the operator has since selected a different part.
 */
export function VerifyStage({
  caseItem,
  sites,
  selection,
  onSelectionChange,
  catalogState,
  catalogError,
  groups,
  constructionsState,
  constructionsError,
  constructions,
  onRetryCatalogs,
  runBusy,
  achievedOffset,
  ceiling,
  clamps,
  refreshToken,
  rotation,
  onProcess,
  onClose,
}: VerifyStageProps) {
  const [layerState, setLayerState] = useState<LayerState>({ ...DEFAULT_LAYER_STATE });
  const [linked, setLinked] = useState(false);
  const linkGroupRef = useRef(new OrbitLinkGroup());

  const [scanPositions, setScanPositions] = useState<Float32Array | null>(null);
  const [scanBusy, setScanBusy] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);

  const [partPositions, setPartPositions] = useState<Float32Array | null>(null);
  const [partBusy, setPartBusy] = useState(false);
  const [partError, setPartError] = useState<string | null>(null);

  /** Which colouring the union pane wears: our SIGNED ±clamp RdBu (direction) or the client's
   *  ABSOLUTE "Contacts" rainbow (magnitude). Per-dialog UI state — it colours the read, it
   *  never changes what was measured. */
  const [scaleId, setScaleId] = useState<DeviationScaleId>("signed");

  const [deviation, setDeviation] = useState<SiteDeviation | null>(null);
  const [deviationState, setDeviationState] = useState<DeviationState>("idle");
  const [deviationError, setDeviationError] = useState<string | null>(null);

  const [preview, setPreview] = useState<SiteDeviation | null>(null);
  const [previewState, setPreviewState] = useState<PreviewState>("idle");
  const [previewError, setPreviewError] = useState<string | null>(null);

  const activeSite = selection.sites[selection.activeSiteIndex] ?? null;
  const activeTooth = activeSite?.tooth ?? null;
  const activeRow = sites.find((s) => s.tooth === activeTooth) ?? null;
  /** What the scan panes frame on: the operator's own centre mark when they placed one, else the
   *  row's centre. Never a derived/guessed point — both come from the doctor's input. */
  const siteCenter: Vec3 | null = activeRow ? activeRow.centerMark ?? activeRow.center : null;
  const variantEntry = findVariantEntry(groups, selection.model, activeSite?.variantId ?? null);

  useEffect(() => {
    linkGroupRef.current.setEnabled(linked);
  }, [linked]);

  // Escape closes the dialog — the same convention the part preview and the marking banners use.
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  // The doctor's scan: fetched and parsed once for the whole dialog, then cropped per site.
  useEffect(() => {
    let cancelled = false;
    setScanPositions(null);
    setScanError(null);
    setScanBusy(true);
    scanPositionsFor(caseItem.id)
      .then((positions) => {
        if (cancelled) return;
        setScanPositions(positions);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setScanError(err instanceof Error ? err.message : "Failed to load the scan.");
      })
      .finally(() => {
        if (!cancelled) setScanBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [caseItem.id]);

  // The chosen library part. Mesh bytes come through the shared blob cache, so stepping between
  // sites that declare the same cap costs one fetch, not two.
  const partMeshUrl = variantEntry?.meshUrl ?? null;
  useEffect(() => {
    if (partMeshUrl === null) {
      setPartPositions(null);
      setPartError(null);
      return undefined;
    }
    let cancelled = false;
    setPartPositions(null);
    setPartError(null);
    setPartBusy(true);
    cachedMeshUrl(partMeshUrl)
      .then((url) => loadStlPositions(url))
      .then((positions) => {
        if (cancelled) return;
        setPartPositions(positions);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setPartError(err instanceof Error ? err.message : "Failed to load the library part.");
      })
      .finally(() => {
        if (!cancelled) setPartBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [partMeshUrl]);

  // The union pane's measured overlay for the active site. A 404 is this site's honest "not
  // seated yet" state, not an error — the run has simply not happened for it.
  useEffect(() => {
    if (activeTooth === null) {
      setDeviation(null);
      setDeviationState("idle");
      return undefined;
    }
    let cancelled = false;
    setDeviation(null);
    setDeviationError(null);
    setDeviationState("loading");
    fetchSiteDeviation(caseItem.id, activeTooth)
      .then((payload) => {
        if (cancelled) return;
        setDeviation(payload);
        setDeviationState("ready");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && (err.status === 404 || err.status === 409)) {
          setDeviationState("none");
          return;
        }
        setDeviationError(err instanceof ApiError ? err.message : "Failed to load the deviation overlay.");
        setDeviationState("error");
      });
    return () => {
      cancelled = true;
    };
  }, [caseItem.id, activeTooth, runBusy, refreshToken]);

  /**
   * Does the SHIPPED read describe the part the operator currently has selected? A run seats
   * whatever was chosen at the time; changing the variant afterwards leaves a colouring of the
   * previous part on screen, which is the one thing a verification pane must never do quietly.
   */
  const chosenVariant = activeSite?.variantId ?? null;
  const shippedMatchesSelection =
    deviation !== null &&
    (deviation.variant === null || chosenVariant === null || deviation.variant === chosenVariant);

  /**
   * THE PRE-RUN PREVIEW, FIRED AUTOMATICALLY (client, 2026-07-26). Verification exists to happen
   * BEFORE Process; until now the union pane could only colour a shipped pose, so on a case
   * nobody had run it said "no seated result yet" — verification that only works after the thing
   * it is meant to gate.
   *
   * So: whenever the shipped read cannot answer for the CURRENT selection (never run, or run
   * with a different cap) and the selection is complete enough to seat something, the stage asks
   * the backend to seat this one site and colour it. Nothing is emitted (see the endpoint's own
   * doc) and nothing here blocks — the pane shows a computing state and the rest of the dialog
   * stays live, so the operator can keep stepping sites or changing the choice.
   *
   * The effect is keyed on the whole selection AND on the marks, not just the tooth: a different
   * cap, construction part, jaw, relief — or a moved mark — is a different preview, and the
   * request key is what stops the read from re-firing on unrelated re-renders.
   */
  const marksKey = marksSignatureFor(sites);
  const previewKey =
    activeTooth !== null &&
    chosenVariant !== null &&
    selection.model !== null &&
    selection.constructionPathId !== null &&
    !(deviationState === "ready" && shippedMatchesSelection) &&
    deviationState !== "loading" &&
    deviationState !== "idle"
      ? [
          caseItem.id,
          activeTooth,
          selection.model,
          chosenVariant,
          selection.constructionPathId,
          selection.jaw,
          selection.gingivalOffsetMm,
          marksKey,
        ].join("|")
      : null;

  useEffect(() => {
    if (previewKey === null) return undefined;
    let cancelled = false;
    setPreview(null);
    setPreviewError(null);
    setPreviewState("computing");
    previewSiteAlignment(caseItem.id, activeTooth as number, sites, {
      model: selection.model as string,
      constructionPathId: selection.constructionPathId as string,
      jaw: selection.jaw,
      gingivalOffsetMm: selection.gingivalOffsetMm,
    })
      .then((payload) => {
        if (cancelled) return;
        setPreview(payload);
        setPreviewState("ready");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          setPreviewState("unavailable");
          return;
        }
        setPreviewError(err instanceof ApiError ? err.message : "The alignment preview failed.");
        setPreviewState("error");
      });
    return () => {
      cancelled = true;
    };
    // Every input this effect reads is folded into previewKey — the selection's fields and the
    // marks' signature — so keying on that one string is both complete and the thing that keeps
    // it to ONE request per distinct preview.
  }, [previewKey, caseItem.id, activeTooth, sites, selection]);

  /** The colouring the union pane actually shows: the SHIPPED read when it answers for the
   *  current selection, otherwise the preview. Never a mix — one pose, one colouring. */
  const unionSource: SiteDeviation | null =
    deviationState === "ready" && shippedMatchesSelection ? deviation : preview;

  /** The cap region: the scan's triangles near this site, computed once per (scan, site). */
  const scanCrop = useMemo(() => {
    if (scanPositions === null || siteCenter === null) return null;
    return cropTrianglesNear(scanPositions, siteCenter, CAP_REGION_RADIUS_MM);
  }, [scanPositions, siteCenter]);

  const scanGeometry: VerifyLayerGeometry | null = useMemo(
    () => (scanCrop && scanCrop.length > 0 ? { positions: scanCrop, color: PALETTE.arch } : null),
    [scanCrop],
  );

  const partGeometry: VerifyLayerGeometry | null = useMemo(
    () => (partPositions ? { positions: partPositions, color: PALETTE.cap } : null),
    [partPositions],
  );

  const deviationGeometry: VerifyLayerGeometry | null = useMemo(() => {
    if (unionSource === null) return null;
    return {
      positions: unionSource.points,
      indices: unionSource.faces,
      // ONE entry point for both scales — the bar under the pane is drawn from the same module,
      // so the surface and its legend cannot end up on different ramps.
      colors: buildScaleColors(scaleId, unionSource.deviationMm, unionSource.scale.clampMm),
    };
  }, [unionSource, scaleId]);

  const layerOf = useCallback(
    (panelId: VerifyPanelId, layerId: string, geometry: VerifyLayerGeometry | null): VerifyViewerLayer => {
      const state = layerState[layerKey(panelId, layerId)] ?? { visible: true, opacity: 1 };
      return { id: layerId, geometry, visible: state.visible, opacity: state.opacity };
    },
    [layerState],
  );

  const libraryLayers = useMemo(
    () => [layerOf("library", LAYER_PART, partGeometry)],
    [layerOf, partGeometry],
  );
  const scanLayers = useMemo(() => [layerOf("scan", LAYER_SCAN, scanGeometry)], [layerOf, scanGeometry]);
  const unionLayers = useMemo(
    () => [layerOf("union", LAYER_SCAN, scanGeometry), layerOf("union", LAYER_DEVIATION, deviationGeometry)],
    [layerOf, scanGeometry, deviationGeometry],
  );

  /**
   * FACING THE TOP OF THE CAP (client, 2026-07-26). Every pane used to open from one fixed
   * world-space three-quarter angle — an angle chosen with no reference to the part in front of
   * it, which is why the library pane showed a disc edge-on while the scan panes looked at the
   * cap's flank. Each pane now opens looking down the axis its own subject actually stands on:
   *
   *   pane 1 — the library part's FILE axis (+z). computePartFrame does not merely assume that:
   *            it refuses (null) unless the mesh really reads as a revolute part standing on +z
   *            (rim circularity + cross-section concentricity), and a refusal falls back to the
   *            old framing rather than pointing the camera off noise.
   *   panes 2/3 — the jaw's OCCLUSAL direction, measured from the whole arch. This is the honest
   *            approximation, and worth naming as one: it is the direction caps protrude in, not
   *            a per-cap axis read. A cap tilted in the bone is off by its own tilt (a few
   *            degrees on this fleet) — enough to open the pane on the top face, which is what
   *            was asked, and never enough to pass for a measurement. The MEASURED axis is what
   *            the union pane's colouring is derived from; this only aims the camera.
   */
  const partFrame = useMemo(() => {
    if (partPositions === null) return null;
    const pf = computePartFrame(partPositions);
    if (!pf) return null;
    // The rim centre is canonical xy (canonical = raw − centroid); the target's z is the part's
    // own mid-height, which is what a top-down camera should be aimed through.
    const center: Vec3 = [
      pf.rimCentre[0] + pf.centroid[0],
      pf.rimCentre[1] + pf.centroid[1],
      pf.centroid[2],
    ];
    // The part's own radius, not the crop constant the scan panes use — a 6mm cap framed at the
    // scan's 9mm region radius would sit in the middle of the pane as a small disc.
    // +x is the canonical frame's reference direction — the same one the seated pose's x_axis
    // is, so the library pane and the scan panes agree on where "zero degrees" is.
    return {
      center,
      radiusMm: pf.rmaxMm * 1.6,
      viewDirection: [0, 0, 1] as Vec3,
      up: [1, 0, 0] as Vec3,
    };
  }, [partPositions]);

  const occlusal = useMemo(() => {
    if (scanPositions === null) return null;
    return (computeAnatomyFrame(scanPositions)?.occlusal ?? null) as Vec3 | null;
  }, [scanPositions]);

  /**
   * THE SCAN PANES' FRAME, from the SEATED POSE ITSELF (2026-07-26).
   *
   * The occlusal direction below was an honest proxy and a bad one: measured across this fleet it
   * sits 6.2°-42.0° off the cap's real axis (median ~13°; worst 42.0° on zimmer-4.5 t7), which is
   * exactly what the client reported — pane 1 square-on and panes 2/3 looking at the cap from
   * somewhere else. The deviation payload now carries the pose the run actually shipped, so these
   * panes aim down the SAME axis the alignment produced. Verified against the packaged
   * implant.json on all 10 sites: 0.000°-0.054°.
   *
   * `up` is the pose's own x-axis, and it is what makes the three panes comparable rather than
   * merely each-correct: pane 1 rolls to the part's canonical +x, these roll to the seated frame's
   * +x, so a coded cutout appears at the same clock angle in all three.
   *
   * A payload without a pose block (an older server) falls back to the occlusal proxy — worse, but
   * still better than the fixed world angle it replaced, and it says so here rather than silently.
   */
  const seatedFrame = unionSource?.pose ?? null;

  const frame = siteCenter
    ? {
        center: siteCenter,
        radiusMm: CAP_REGION_RADIUS_MM,
        viewDirection: seatedFrame ? seatedFrame.axis : occlusal,
        up: seatedFrame ? seatedFrame.xAxis : null,
      }
    : null;

  const renderViewer = useCallback(
    (panelId: VerifyPanelId) => {
      const linkGroup = linkGroupRef.current;
      if (panelId === "library") {
        return (
          <VerifyViewer
            layers={libraryLayers}
            frame={partFrame}
            linkGroup={linkGroup}
            ariaLabel="The selected library part"
          />
        );
      }
      if (panelId === "scan") {
        return (
          <VerifyViewer
            layers={scanLayers}
            frame={frame}
            linkGroup={linkGroup}
            ariaLabel="The scanned cap region"
          />
        );
      }
      return (
        <VerifyViewer
          layers={unionLayers}
          frame={frame}
          linkGroup={linkGroup}
          ariaLabel="The scan and the seated cap overlaid, coloured by deviation"
        />
      );
    },
    [libraryLayers, scanLayers, unionLayers, frame],
  );

  /**
   * The union pane's honest notice. Order matters: it answers "why is there nothing to look at",
   * and the first true reason is the actionable one. A pre-run preview that is still computing is
   * NOT a notice — it is the pane's busy state, so the operator is told work is happening rather
   * than told the site was never run.
   */
  const unionNotice = (() => {
    if (activeTooth === null) return "No marked site selected — mark a cap first.";
    if (unionSource !== null) return null;
    if (chosenVariant === null) return "Choose this site's cap variant to preview its alignment.";
    if (selection.model === null || selection.constructionPathId === null) {
      return "Choose the implant system and the construction part — the preview seats the cap with them.";
    }
    if (previewState === "unavailable") {
      return (
        "The alignment preview is not available on the running API — restart make serve " +
        "(apps/worker). The overlay still appears once Process has run this site."
      );
    }
    if (previewState === "error") return previewError ?? "The alignment preview failed.";
    if (deviationState === "error") return deviationError ?? "The deviation overlay could not be loaded.";
    if (deviationState === "none" && previewState === "idle") {
      return "No seated result for this site yet — the measured overlay appears once Process has run it.";
    }
    return "The deviation read carried no mesh.";
  })();

  /** Whose colouring is on screen — the caption states it, because a preview and a shipped read
   *  look identical and mean different things about what has actually been produced. */
  const unionCaption = (() => {
    if (unionSource === null) return "the seated cap against the scan";
    if (unionSource.preview) {
      const seat = unionSource.seat;
      const seated = seat?.seatMethod ? `${seat.seatMethod} seat` : "seated";
      const rim =
        seat?.rimAgreementMm !== null && seat?.rimAgreementMm !== undefined
          ? `, rim ${seat.rimAgreementMm.toFixed(2)} mm`
          : "";
      return `preview — this selection seated now (${seated}${rim}); nothing processed yet`;
    }
    return "the seated cap against the scan, from the last completed run for this site";
  })();

  const scanNotice = (() => {
    if (scanError) return scanError;
    if (siteCenter === null) return "This site has no marked centre — mark the cap in step 2.";
    if (scanCrop !== null && scanCrop.length === 0) {
      return `No scan surface within ${CAP_REGION_RADIUS_MM} mm of this site's mark.`;
    }
    return null;
  })();

  const partNotice = (() => {
    if (partError) return partError;
    if (variantEntry === null) return "Choose a cap variant on the left to load its library part.";
    return null;
  })();

  const panels: VerifyPanelSpec[] = [
    {
      id: "library",
      title: "1 · Library part",
      caption: variantEntry
        ? `${selection.model ?? ""} ${variantEntry.variant} — ${variantEntry.filename}`
        : "the library part you selected",
      layers: [
        {
          id: LAYER_PART,
          label: "Library cap",
          swatch: paletteHex("cap"),
          visible: layerState[layerKey("library", LAYER_PART)]?.visible ?? true,
          opacity: layerState[layerKey("library", LAYER_PART)]?.opacity ?? 1,
          available: partGeometry !== null,
        },
      ],
      notice: partNotice,
      busy: partBusy,
    },
    {
      id: "scan",
      title: "2 · Scanned cap",
      caption:
        scanCrop !== null
          ? `${triangleCount(scanCrop).toLocaleString()} triangles within ${CAP_REGION_RADIUS_MM} mm of the mark`
          : "the doctor's scan around this site's mark",
      layers: [
        {
          id: LAYER_SCAN,
          label: "Scan region",
          swatch: paletteHex("arch"),
          visible: layerState[layerKey("scan", LAYER_SCAN)]?.visible ?? true,
          opacity: layerState[layerKey("scan", LAYER_SCAN)]?.opacity ?? 1,
          available: scanGeometry !== null,
        },
      ],
      notice: scanNotice,
      busy: scanBusy,
    },
    {
      id: "union",
      title: "3 · Union — coloured by deviation",
      caption: unionCaption,
      layers: [
        {
          id: LAYER_SCAN,
          label: "Scan region",
          swatch: paletteHex("arch"),
          visible: layerState[layerKey("union", LAYER_SCAN)]?.visible ?? true,
          opacity: layerState[layerKey("union", LAYER_SCAN)]?.opacity ?? 0.45,
          available: scanGeometry !== null,
        },
        {
          id: LAYER_DEVIATION,
          label: "Seated cap (deviation)",
          swatch: null,
          visible: layerState[layerKey("union", LAYER_DEVIATION)]?.visible ?? true,
          opacity: layerState[layerKey("union", LAYER_DEVIATION)]?.opacity ?? 1,
          available: deviationGeometry !== null,
        },
      ],
      notice: unionNotice,
      busy: deviationState === "loading" || previewState === "computing" || scanBusy,
      busyMessage:
        previewState === "computing"
          ? "seating this selection on the scan — preview, nothing is being processed…"
          : undefined,
      colorbar: unionSource
        ? {
            scale: unionSource.scale,
            stats: unionSource.stats,
            scaleId,
            onSelectScale: setScaleId,
          }
        : null,
      // Only over a SHIPPED colouring: rotating a pre-run preview would step a pose that was
      // never emitted, and the pane in front of the operator would not be showing the result.
      rotation: rotation && unionSource !== null && !unionSource.preview ? rotation : null,
    },
  ];

  const handleToggleLayer = useCallback((panelId: VerifyPanelId, layerId: string) => {
    setLayerState((prev) => {
      const key = layerKey(panelId, layerId);
      const current = prev[key] ?? DEFAULT_LAYER_STATE[key] ?? { visible: true, opacity: 1 };
      return { ...prev, [key]: { ...current, visible: !current.visible } };
    });
  }, []);

  const handleChangeOpacity = useCallback(
    (panelId: VerifyPanelId, layerId: string, opacity: number) => {
      setLayerState((prev) => {
        const key = layerKey(panelId, layerId);
        const current = prev[key] ?? DEFAULT_LAYER_STATE[key] ?? { visible: true, opacity: 1 };
        return { ...prev, [key]: { ...current, opacity } };
      });
    },
    [],
  );

  return (
    <VerifyDialog
      caseId={caseItem.id}
      doctor={caseItem.doctor}
      scanFilename={caseItem.scanFilename}
      selection={selection}
      infoEntry={variantEntry}
      selectionColumn={{
        selection,
        activeSiteNumber: activeSite ? selection.activeSiteIndex + 1 : null,
        activeTooth,
        libraryState: catalogState,
        libraryError: catalogError,
        groups,
        constructionsState,
        constructionsError,
        constructions,
        suggestedModel: caseItem.suggestedModel,
        suggestedConstruction: caseItem.suggestedConstruction,
        // ONE wiring for BOTH mounts (2026-07-26): the same builder step 2's column uses, so
        // the dialog cannot drift into its own idea of what a card click means.
        ...selectionColumnHandlers(selection, onSelectionChange),
        achievedOffset,
        ceiling,
        clamps,
        onRetry: onRetryCatalogs,
      }}
      clamps={clamps}
      panels={panels}
      linked={linked}
      busy={runBusy}
      onToggleLayer={handleToggleLayer}
      onChangeOpacity={handleChangeOpacity}
      onToggleLinked={() => setLinked((v) => !v)}
      renderViewer={renderViewer}
      onStepSite={(delta: number) => onSelectionChange(stepSite(selection, delta))}
      onSelectSite={(index: number) => onSelectionChange(withActiveSite(selection, index))}
      onToggleReviewed={(index: number, reviewed: boolean) =>
        onSelectionChange(withReviewed(selection, index, reviewed))
      }
      onProcess={onProcess}
      onClose={onClose}
    />
  );
}
