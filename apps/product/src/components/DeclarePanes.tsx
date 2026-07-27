/**
 * THE THREE LIVE PANES (plan §4 Declare / §7 slice 5b) — the product's whole point on
 * this stage (verify-UI doctrine: the panes ARE the product). REBUILT against BFF
 * shapes; the pane SEMANTICS are the frozen demo's VerifyStage, kept deliberately:
 *
 *   pane 1 — the declared LIBRARY PART in its canonical frame, framed down its file
 *            +z with up +x (the copied partFrame; a mesh that does not read as a
 *            revolute part falls back to the default framing rather than aiming the
 *            camera off noise).
 *   pane 2 — the SCANNED CAP: the already-streamed arch cropped by the copied
 *            meshCrop at the site's centre (9 mm), framed down the preview pose's
 *            EXACT axis when a preview exists, else the jaw's occlusal direction —
 *            the demo's honesty story verbatim: the occlusal read is a proxy
 *            (6.2°-42.0° off across the fleet), the pose is exact by construction.
 *   pane 3 — the UNION: the preview payload coloured by the copied deviationColormap
 *            (signed ±clamp scale), pose-axis framing, up shared with pane 1's +x so
 *            the coded cutout reads at the same clock angle everywhere. RMS/p90 come
 *            from the payload's OWN stats — the published acceptance numbers, never
 *            a client-side re-derivation.
 *
 * THE REVIEW TICK sits here, with the panes it attests (AM-8: "reviewed over panels,
 * not a checkbox"): enabled only once the site is previewed; tick = POST review,
 * untick = DELETE — the BFF's status machine judges both, this surface only offers
 * what the server would accept and renders what came back (optimism OFF, AM-4).
 *
 * The preview AUTO-FIRES per site (domain/declare.previewKeyFor + shouldAutoPreview —
 * keyed on server facts, one request per distinct declaration+choices) and is
 * per-site NON-BLOCKING: stepping sites while one previews is legal; each site's
 * slot settles on its own and a stale response never overwrites a newer ask.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  CAP_REGION_RADIUS_MM,
  OrbitLinkGroup,
  PALETTE,
  VerifyViewer,
  buildDeviationColors,
  computeAnatomyFrame,
  computePartFrame,
  cropTrianglesNear,
  loadStlPositions,
  scanPositionsFor,
  triangleCount,
  type Vec3,
  type VerifyLayerGeometry,
} from "viewer";
import {
  deleteReview,
  fetchCaseSession,
  postPreview,
  postReview,
  scanUrlFor,
  type CaseSessionDetail,
  type SitePreviewPayload,
  type SiteView,
} from "../api/client";
import {
  indicesFrom,
  paneNotices,
  positionsFrom,
  previewKeyFor,
  reviewTick,
  shouldAutoPreview,
  variantMeshUrl,
  type PaneNotices,
  type PreviewPhase,
  type ReviewTickState,
} from "../domain/declare";

/** One site's preview slot: which key it answers for, and how far it got. The payload
 * lives HERE (client memory) only — the BFF stores facts, not meshes — so a reload
 * honestly re-asks (the auto-fire) rather than pretending to remember. */
export interface PreviewSlot {
  readonly key: string;
  readonly state: "computing" | "ready" | "error";
  readonly payload?: SitePreviewPayload;
  readonly error?: string;
}

export type PreviewSlots = Readonly<Record<number, PreviewSlot>>;

/** What the review wiring is doing, named — the surface states it (optimism OFF). */
export type ReviewSaving = "idle" | "ticking" | "unticking";

interface PaneShellProps {
  readonly role: string;
  readonly title: string;
  readonly caption: string | null;
  readonly notice: string | null;
  readonly busy: boolean;
  readonly busyMessage: string | null;
  readonly viewer: ReactNode;
  readonly children?: ReactNode;
}

/** One pane's chrome: title, live canvas slot, the honest notice, the busy words. */
function PaneShell({
  role,
  title,
  caption,
  notice,
  busy,
  busyMessage,
  viewer,
  children,
}: PaneShellProps) {
  return (
    <section data-role={role} aria-label={title}>
      <h4>{title}</h4>
      <div style={{ position: "relative", minHeight: "14rem" }}>{viewer}</div>
      {caption !== null && <p data-role="pane-caption">{caption}</p>}
      {busy && (
        <p data-role="pane-busy">{busyMessage ?? "Loading…"}</p>
      )}
      {notice !== null && (
        <p data-role="pane-notice" role="status">
          {notice}
        </p>
      )}
      {children}
    </section>
  );
}

export interface DeclarePanesViewProps {
  readonly site: SiteView | null;
  readonly variantLabel: string | null;
  readonly notices: PaneNotices;
  readonly partBusy: boolean;
  readonly scanBusy: boolean;
  readonly scanCaption: string | null;
  readonly previewPhase: PreviewPhase;
  readonly payload: SitePreviewPayload | null;
  readonly tick: ReviewTickState;
  readonly reviewSaving: ReviewSaving;
  readonly reviewError: string | null;
  readonly onToggleReview: (ticked: boolean) => void;
  readonly onRetryPreview: () => void;
  /** The three live canvases — the container passes VerifyViewers; tests pass stubs. */
  readonly libraryViewer: ReactNode;
  readonly scanViewer: ReactNode;
  readonly unionViewer: ReactNode;
}

/** The panes' whole surface, pure payload → markup — statically testable (the
 * viewer slots are props precisely so WebGL never enters a test). */
export function DeclarePanesView({
  site,
  variantLabel,
  notices,
  partBusy,
  scanBusy,
  scanCaption,
  previewPhase,
  payload,
  tick,
  reviewSaving,
  reviewError,
  onToggleReview,
  onRetryPreview,
  libraryViewer,
  scanViewer,
  unionViewer,
}: DeclarePanesViewProps) {
  const seat = payload?.seat ?? null;
  const unionCaption = (() => {
    if (payload === null) return null;
    const seated = seat?.seat_method ? `${seat.seat_method} seat` : "seated";
    const rim =
      seat?.rim_agreement_mm !== null && seat?.rim_agreement_mm !== undefined
        ? `, rim ${seat.rim_agreement_mm.toFixed(2)} mm`
        : "";
    // a preview and a shipped read look identical and mean different things —
    // the caption states WHOSE colouring this is (the demo's honesty, kept)
    return `preview — this selection seated now (${seated}${rim}); nothing processed yet`;
  })();
  return (
    <div data-role="declare-panes">
      <PaneShell
        role="pane-library"
        title="1 · Library part"
        caption={variantLabel}
        notice={notices.part}
        busy={partBusy}
        busyMessage="Loading the library part…"
        viewer={libraryViewer}
      />
      <PaneShell
        role="pane-scan"
        title="2 · Scanned cap"
        caption={scanCaption}
        notice={notices.scan}
        busy={scanBusy}
        busyMessage="Loading the scan…"
        viewer={scanViewer}
      />
      <PaneShell
        role="pane-union"
        title="3 · Union — coloured by deviation"
        caption={unionCaption}
        notice={notices.union}
        busy={previewPhase === "computing" || scanBusy}
        busyMessage={
          previewPhase === "computing"
            ? "seating this selection on the scan — preview, nothing is being processed…"
            : null
        }
        viewer={unionViewer}
      >
        {payload !== null && (
          <p data-role="union-stats">
            RMS{" "}
            {payload.stats.rms_mm !== null ? `${payload.stats.rms_mm.toFixed(3)} mm` : "—"}
            {" · "}p90{" "}
            {payload.stats.p90_mm !== null ? `${payload.stats.p90_mm.toFixed(3)} mm` : "—"}
          </p>
        )}
        {previewPhase === "error" && (
          <button type="button" data-role="preview-retry" onClick={onRetryPreview}>
            Try the preview again
          </button>
        )}
      </PaneShell>
      <div data-role="review-tick-row">
        <label>
          <input
            type="checkbox"
            data-role="review-tick"
            checked={tick.ticked}
            disabled={!tick.enabled || reviewSaving !== "idle"}
            onChange={(event) => onToggleReview(event.target.checked)}
          />{" "}
          Reviewed over the panes
          {site !== null ? ` — tooth ${site.tooth}` : ""}
        </label>
        {tick.reason !== null && (
          <span data-role="review-tick-reason">{tick.reason}</span>
        )}
        {reviewSaving !== "idle" && (
          <span data-role="review-saving">
            {reviewSaving === "ticking" ? "Recording the review…" : "Withdrawing the review…"}
          </span>
        )}
        {reviewError !== null && (
          <span data-role="review-error" role="alert">
            {reviewError}
          </span>
        )}
      </div>
    </div>
  );
}

export interface DeclarePanesProps {
  readonly detail: CaseSessionDetail;
  readonly site: SiteView | null;
  /** The shell owns the payload; the review responses replace it whole (AM-4). */
  readonly onDetail: (next: CaseSessionDetail) => void;
}

/** The container: scan + part meshes, the auto-fired preview slots, the tick's two
 * requests, and the three VerifyViewers with their frames. */
export function DeclarePanes({ detail, site, onDetail }: DeclarePanesProps) {
  const caseId = detail.case.id;
  const tooth = site?.tooth ?? null;
  const mountedRef = useRef(true);
  const linkGroupRef = useRef(new OrbitLinkGroup());

  const [scanPositions, setScanPositions] = useState<Float32Array | null>(null);
  const [scanBusy, setScanBusy] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);

  const [partPositions, setPartPositions] = useState<Float32Array | null>(null);
  const [partBusy, setPartBusy] = useState(false);
  const [partError, setPartError] = useState<string | null>(null);

  const [previews, setPreviews] = useState<PreviewSlots>({});
  const [reviewSaving, setReviewSaving] = useState<ReviewSaving>("idle");
  const [reviewError, setReviewError] = useState<string | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // The doctor's scan: fetched and parsed once per case (the package's one-entry
  // cache), then cropped per site below.
  useEffect(() => {
    let cancelled = false;
    setScanPositions(null);
    setScanError(null);
    setScanBusy(true);
    scanPositionsFor(caseId, scanUrlFor(caseId))
      .then((positions) => {
        if (!cancelled) setScanPositions(positions);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setScanError(err instanceof Error ? err.message : "The scan did not load.");
        }
      })
      .finally(() => {
        if (!cancelled) setScanBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [caseId]);

  // The declared variant's library part, via the SERVED mesh_url (pane 1).
  const partMeshUrl = variantMeshUrl(detail, site?.declared_variant ?? null);
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
    loadStlPositions(partMeshUrl)
      .then((positions) => {
        if (!cancelled) setPartPositions(positions);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setPartError(
            err instanceof Error ? err.message : "The library part did not load.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setPartBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [partMeshUrl]);

  // THE AUTO-FIRED PREVIEW (per-site, non-blocking): fire exactly when the pure
  // helper says so; the slot is claimed synchronously so a re-render cannot double-
  // fire, and a settling response only writes a slot that still holds ITS key.
  const key = previewKeyFor(detail, tooth);
  const slot = tooth !== null ? previews[tooth] : undefined;
  // marked BEFORE the async settles (Intake's shouldAutoDetect lesson): the slot
  // state lags a render behind, so without this a doubled effect run could POST twice
  const firedRef = useRef<Record<number, string>>({});
  const firePreview = useCallback(
    (forTooth: number, forKey: string) => {
      firedRef.current[forTooth] = forKey;
      setPreviews((prev) => ({
        ...prev,
        [forTooth]: { key: forKey, state: "computing" },
      }));
      void postPreview(caseId, forTooth).then((result) => {
        if (!mountedRef.current) return;
        setPreviews((prev) => {
          const current = prev[forTooth];
          if (current === undefined || current.key !== forKey) return prev; // a newer ask owns the slot
          if (result.kind === "ok") {
            return { ...prev, [forTooth]: { key: forKey, state: "ready", payload: result.data } };
          }
          return { ...prev, [forTooth]: { key: forKey, state: "error", error: result.detail } };
        });
        if (result.kind === "ok") {
          // the site moved declared→previewed SERVER-side; re-read the whole truth
          // rather than patching a status locally (trust direction, AM-4)
          void fetchCaseSession(caseId).then((fresh) => {
            if (mountedRef.current && fresh.kind === "ok") onDetail(fresh.data);
          });
        }
      });
    },
    [caseId, onDetail],
  );
  useEffect(() => {
    if (tooth === null || key === null) return;
    if (!shouldAutoPreview({ key, slotKey: slot?.key ?? null })) return;
    if (firedRef.current[tooth] === key) return; // already in flight for THIS key
    firePreview(tooth, key);
  }, [tooth, key, slot?.key, firePreview]);

  const payload =
    slot !== undefined && slot.key === key && slot.state === "ready"
      ? (slot.payload ?? null)
      : null;
  const previewPhase: PreviewPhase =
    key === null || slot === undefined || slot.key !== key
      ? "idle"
      : slot.state === "ready"
        ? "ready"
        : slot.state;

  // THE TICK'S TWO REQUESTS — both body-less; the response detail replaces the
  // payload whole and the queue chip and rail react to it.
  const handleToggleReview = useCallback(
    (ticked: boolean) => {
      if (tooth === null) return;
      setReviewSaving(ticked ? "ticking" : "unticking");
      const request = ticked ? postReview : deleteReview;
      void request(caseId, tooth).then((result) => {
        if (!mountedRef.current) return;
        setReviewSaving("idle");
        if (result.kind === "ok") {
          setReviewError(null);
          onDetail(result.data);
        } else {
          setReviewError(result.detail);
        }
      });
    },
    [caseId, tooth, onDetail],
  );

  const handleRetryPreview = useCallback(() => {
    if (tooth !== null && key !== null) firePreview(tooth, key);
  }, [tooth, key, firePreview]);

  // --- geometry + frames (the demo's memo discipline: derive once per input so an
  // --- unrelated re-render never re-uploads a mesh to the GPU) -----------------------

  const siteCenter: Vec3 | null = useMemo(() => {
    const c = site?.center;
    return c && c.length === 3 ? [c[0]!, c[1]!, c[2]!] : null;
  }, [site]);

  const scanCrop = useMemo(() => {
    if (scanPositions === null || siteCenter === null) return null;
    return cropTrianglesNear(scanPositions, siteCenter, CAP_REGION_RADIUS_MM);
  }, [scanPositions, siteCenter]);

  const scanGeometry: VerifyLayerGeometry | null = useMemo(
    () =>
      scanCrop && scanCrop.length > 0
        ? { positions: scanCrop, color: PALETTE.arch }
        : null,
    [scanCrop],
  );

  const partGeometry: VerifyLayerGeometry | null = useMemo(
    () => (partPositions ? { positions: partPositions, color: PALETTE.cap } : null),
    [partPositions],
  );

  const deviationGeometry: VerifyLayerGeometry | null = useMemo(() => {
    if (payload === null) return null;
    return {
      positions: positionsFrom(payload.points),
      indices: indicesFrom(payload.faces),
      colors: buildDeviationColors(payload.deviation_mm, payload.scale.clamp_mm),
    };
  }, [payload]);

  // Pane 1: down the part's own file axis (+z), up +x — the canonical frame's
  // reference direction, the same one the seated pose's x_axis is, so pane 1 and
  // panes 2/3 agree where "zero degrees" sits.
  const partFrame = useMemo(() => {
    if (partPositions === null) return null;
    const pf = computePartFrame(partPositions);
    if (!pf) return null; // not readably revolute — default framing beats aiming off noise
    const center: Vec3 = [
      pf.rimCentre[0] + pf.centroid[0],
      pf.rimCentre[1] + pf.centroid[1],
      pf.centroid[2],
    ];
    return {
      center,
      radiusMm: pf.rmaxMm * 1.6,
      viewDirection: [0, 0, 1] as Vec3,
      up: [1, 0, 0] as Vec3,
    };
  }, [partPositions]);

  // Panes 2/3: the preview pose's EXACT axis when one exists, else the jaw's
  // occlusal proxy — the demo's exact honesty story (the proxy aims the camera,
  // only ever the measured pose colours anything).
  const occlusal = useMemo(() => {
    if (scanPositions === null) return null;
    return (computeAnatomyFrame(scanPositions)?.occlusal ?? null) as Vec3 | null;
  }, [scanPositions]);
  const pose = payload?.pose ?? null;
  // the wire carries number[]; a malformed triple falls back to the occlusal proxy
  // rather than aiming a camera off a short array
  const vec3 = (v: readonly number[] | null | undefined): Vec3 | null =>
    v != null && v.length === 3 ? [v[0]!, v[1]!, v[2]!] : null;
  const siteFrame = siteCenter
    ? {
        center: siteCenter,
        radiusMm: CAP_REGION_RADIUS_MM,
        viewDirection: (pose ? vec3(pose.axis) : null) ?? occlusal,
        up: pose ? vec3(pose.x_axis) : null,
      }
    : null;

  const notices = paneNotices({
    site,
    choicesComplete: detail.choices.complete,
    partMeshKnown: partMeshUrl !== null,
    partError,
    scanError,
    scanEmpty: scanCrop !== null && scanCrop.length === 0,
    previewPhase,
    previewError: slot?.state === "error" ? (slot.error ?? null) : null,
  });

  const linkGroup = linkGroupRef.current;
  return (
    <DeclarePanesView
      site={site}
      variantLabel={site?.declared_variant ?? null}
      notices={notices}
      partBusy={partBusy}
      scanBusy={scanBusy}
      scanCaption={
        scanCrop !== null && scanCrop.length > 0
          ? `${triangleCount(scanCrop).toLocaleString()} triangles within ${CAP_REGION_RADIUS_MM} mm of the site's centre`
          : null
      }
      previewPhase={previewPhase}
      payload={payload}
      tick={reviewTick(site)}
      reviewSaving={reviewSaving}
      reviewError={reviewError}
      onToggleReview={handleToggleReview}
      onRetryPreview={handleRetryPreview}
      libraryViewer={
        <VerifyViewer
          layers={[{ id: "part", geometry: partGeometry, visible: true, opacity: 1 }]}
          frame={partFrame}
          linkGroup={linkGroup}
          ariaLabel="The declared library part"
        />
      }
      scanViewer={
        <VerifyViewer
          layers={[{ id: "scan", geometry: scanGeometry, visible: true, opacity: 1 }]}
          frame={siteFrame}
          linkGroup={linkGroup}
          ariaLabel="The scanned cap region"
        />
      }
      unionViewer={
        <VerifyViewer
          layers={[
            // the client's own defaults, kept: the scan half-transparent so the
            // coloured cap reads through it
            { id: "scan", geometry: scanGeometry, visible: true, opacity: 0.45 },
            { id: "deviation", geometry: deviationGeometry, visible: true, opacity: 1 },
          ]}
          frame={siteFrame}
          linkGroup={linkGroup}
          ariaLabel="The scan and the previewed cap overlaid, coloured by deviation"
        />
      }
    />
  );
}
