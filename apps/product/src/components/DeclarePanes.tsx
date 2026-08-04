/**
 * DECLARE'S THREE LIVE PANES (plan §4 Declare / §7 slice 5b) — the product's whole
 * point on this stage (verify-UI doctrine: the panes ARE the product).
 *
 * SINCE SLICE 6 the panes themselves live in components/SitePanes (Adjust shows the
 * same three views of the same site, and two copies would be two geometries waiting to
 * disagree). What stays HERE is everything that is Declare's alone:
 *
 *   - the PRE-RUN PREVIEW: auto-fired per site (domain/declare.previewKeyFor +
 *     shouldAutoPreview — keyed on server facts, one request per distinct
 *     declaration+choices) and per-site NON-BLOCKING: stepping sites while one
 *     previews is legal; each site's slot settles on its own and a stale response
 *     never overwrites a newer ask.
 *   - the UNION CAPTION that says whose colouring is on screen — a preview and a
 *     shipped read look identical and mean different things.
 *   - THE REVIEW TICK, with the panes it attests (AM-8: "reviewed over panels, not a
 *     checkbox"), in the demo's acknowledgment-bar language: enabled only once the
 *     site is previewed; tick = POST review, untick = DELETE — the BFF's status
 *     machine judges both, this surface only offers what the server would accept and
 *     renders what came back (optimism OFF, AM-4).
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { type DeviationScaleId } from "viewer";
import {
  deleteReview,
  fetchCaseSession,
  fetchSeated,
  postPreview,
  postReview,
  type CaseSessionDetail,
  type SitePreviewPayload,
  type SiteView,
} from "../api/client";
import {
  attestationAction,
  attestationSentence,
  createPreviewFirer,
  paneNotices,
  previewKeyFor,
  reviewTick,
  seatedReadWanted,
  shouldAutoPreview,
  type PaneNotices,
  type PostPreviewFn,
  type PreviewPhase,
  type PreviewSlots,
  type PreviewFigures,
  type ReviewTickState,
  type ViewPresetId,
} from "../domain/declare";
import { SitePanesView, useSitePaneScene, type PaneId, type PaneLayers } from "./SitePanes";

// The slot types and their async guards live in domain/declare.ts since 5c (the 5b
// review's M1: the double-POST guard and the stale-response rejection are pure rules,
// tested there with an injectable postPreview); re-exported so the shape stays
// addressable beside the component that renders it.
export type { PreviewSlot, PreviewSlots } from "../domain/declare";
// the pane chrome's types moved to SitePanes (slice 6); re-exported so importers of
// this module keep working and the move stays an implementation detail
export type { PaneId, PaneLayerControl, PaneLayers } from "./SitePanes";

/** What the review wiring is doing, named — the surface states it (optimism OFF). */
export type ReviewSaving = "idle" | "ticking" | "unticking";

/** WHOSE colouring the union pane is showing (the demo's honesty, kept): a preview
 * and a shipped read look identical and mean different things, so the caption says.
 * Exported because Adjust states the other half of the same sentence. */
function seatPhrase(payload: SitePreviewPayload): string {
  const seat = payload.seat ?? null;
  const seated = seat?.seat_method ? `${seat.seat_method} seat` : "seated";
  const rim =
    seat?.rim_agreement_mm !== null && seat?.rim_agreement_mm !== undefined
      ? `, rim ${seat.rim_agreement_mm.toFixed(2)} mm`
      : "";
  return `${seated}${rim}`;
}

export function previewCaption(payload: SitePreviewPayload | null): string | null {
  if (payload === null) return null;
  return `preview — this selection seated now (${seatPhrase(payload)}); nothing processed yet`;
}

/** The SEATED lane's caption (§10-AE): the same sentence shape, the other truth —
 * this is the run's shipped fit, not a preview, and the rework act lives on
 * Adjustment. A flagged site's panes must never wear preview words. */
export function seatedRunCaption(payload: SitePreviewPayload | null): string | null {
  if (payload === null) return null;
  return `the run's own fit (${seatPhrase(payload)}) — rework belongs to Adjustment`;
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
  /** WHOSE payload the panes are wearing (§10-AE): the preview lane's, or the
   *  seated fallback's — the union caption follows. Default "preview". */
  readonly payloadSource?: "preview" | "seated";
  readonly seatedPhase?: "idle" | "loading" | "ready" | "error";
  readonly seatedError?: string | null;
  readonly tick: ReviewTickState;
  readonly reviewSaving: ReviewSaving;
  readonly reviewError: string | null;
  readonly onToggleReview: (ticked: boolean) => void;
  readonly onRetryPreview: () => void;
  /** The three live canvases — the container passes VerifyViewers; tests pass stubs. */
  readonly libraryViewer: ReactNode;
  readonly scanViewer: ReactNode;
  readonly unionViewer: ReactNode;
  readonly layers?: PaneLayers;
  readonly onToggleLayer?: (pane: PaneId, layerId: string) => void;
  readonly onChangeOpacity?: (pane: PaneId, layerId: string, opacity: number) => void;
  readonly linked?: boolean;
  readonly onToggleLinked?: () => void;
  readonly maximizedId?: PaneId | null;
  readonly onToggleMaximized?: (pane: PaneId) => void;
  /** Restore one pane's own framing — the panes' answer to the main stage's "This
   *  site" (client 2026-07-29). Optional so callers predating it render unchanged. */
  readonly onResetView?: ((pane: PaneId) => void) | null;
  readonly scaleId?: DeviationScaleId;
  readonly onSelectScale?: (id: DeviationScaleId) => void;
}

/** Declare's whole pane surface: the shared three panes, with the attestation bar as
 * their footer. Pure props → markup, statically testable. */
export function DeclarePanesView({
  site,
  variantLabel,
  notices,
  partBusy,
  scanBusy,
  scanCaption,
  previewPhase,
  payload,
  payloadSource = "preview",
  seatedPhase = "idle",
  seatedError = null,
  tick,
  reviewSaving,
  reviewError,
  onToggleReview,
  onRetryPreview,
  libraryViewer,
  scanViewer,
  unionViewer,
  layers,
  onToggleLayer,
  onChangeOpacity,
  linked,
  onToggleLinked,
  maximizedId = null,
  onToggleMaximized,
  onResetView = null,
  scaleId = "signed",
  onSelectScale,
}: DeclarePanesViewProps) {
  return (
    <SitePanesView
      variantLabel={variantLabel}
      notices={notices}
      partBusy={partBusy}
      scanBusy={scanBusy}
      scanCaption={scanCaption}
      unionCaption={
        seatedPhase === "error" && seatedError !== null
          ? `the shipped fit could not be read — ${seatedError}`
          : payloadSource === "seated"
            ? seatedRunCaption(payload)
            : previewCaption(payload)
      }
      unionBusy={previewPhase === "computing" || seatedPhase === "loading" || scanBusy}
      unionBusyMessage={
        previewPhase === "computing"
          ? "seating this selection on the scan — preview, nothing is being processed…"
          : seatedPhase === "loading"
            ? "reading the shipped fit for this site…"
            : null
      }
      payload={payload}
      libraryViewer={libraryViewer}
      scanViewer={scanViewer}
      unionViewer={unionViewer}
      unionInvite={
        previewPhase === "error" ? (
          <div className="verify-panel__overlay verify-panel__overlay--invite">
            <button
              type="button"
              data-role="preview-retry"
              className="button button--ghost button--small"
              onClick={onRetryPreview}
            >
              Try the preview again
            </button>
          </div>
        ) : null
      }
      layers={layers}
      onToggleLayer={onToggleLayer}
      onChangeOpacity={onChangeOpacity}
      linked={linked}
      onToggleLinked={onToggleLinked}
      maximizedId={maximizedId}
      onToggleMaximized={onToggleMaximized}
      onResetView={onResetView}
      scaleId={scaleId}
      onSelectScale={onSelectScale}
      footer={
        /* THE ATTESTATION BAR, under the panes it attests — the demo's decode-ack bar
           shape (text side yields, the ACT never shrinks). Client 2026-07-27 #2: "The
           reviewed over the panes check mark needs to be better confirmed" — so the
           checkbox became a button-weight act with the SENTENCE beside it naming what
           is attested for this site, and withdrawing is equally explicit. */
        <div data-role="review-tick-row" className="decode-ack">
          <div className="decode-ack__text">
            <p
              data-role="attestation-sentence"
              className="decode-ack__disclaimer"
              title={attestationSentence(site)}
            >
              {attestationSentence(site)}
            </p>
            {tick.reason !== null && (
              <span data-role="review-tick-reason" className="decode-ack__summary">
                {tick.reason}
              </span>
            )}
            {reviewSaving !== "idle" && (
              <span data-role="review-saving" className="decode-ack__summary">
                {reviewSaving === "ticking"
                  ? "Recording the attestation…"
                  : "Undoing…"}
              </span>
            )}
            {reviewError !== null && (
              <span data-role="review-error" role="alert" className="decode-ack__blockers">
                {reviewError}
              </span>
            )}
          </div>
          <div className="decode-ack__actions">
            <button
              type="button"
              data-role="review-tick"
              aria-pressed={tick.ticked}
              className={`button ${
                tick.ticked ? "button--secondary" : "button--primary"
              }`}
              disabled={!tick.enabled || reviewSaving !== "idle"}
              title={tick.reason ?? attestationSentence(site)}
              onClick={() => onToggleReview(!tick.ticked)}
            >
              {attestationAction(site)}
            </button>
          </div>
        </div>
      }
    />
  );
}

export interface DeclarePanesProps {
  readonly detail: CaseSessionDetail;
  readonly site: SiteView | null;
  /** The shell owns the payload; the review responses replace it whole (AM-4). */
  readonly onDetail: (next: CaseSessionDetail) => void;
  /** Injectable transport (5b review M1): defaults to the real client fn; the async
   * guards it feeds are pure and tested in domain/declare.test.ts with a fake. */
  readonly postPreview?: PostPreviewFn;
  /** The named viewpoint DeclareStage's toolbar is asking all three panes to take
   *  (gap `named-view-presets`). Omitted leaves every pane on its own framing. */
  readonly viewPreset?: ViewPresetId;
  /** Bumped by the stage on every preset click, re-selection included — see
   *  SitePaneSceneOptions.viewPresetNonce. */
  readonly viewPresetNonce?: number;
  /** The workspace's shared zoom counter, forwarded to all three panes unchanged —
   *  see SitePaneSceneOptions.zoomLevel. */
  readonly zoomLevel?: number;
  /** The stage-owned link state, forwarded into the scene — the toggle lives in the
   *  workspace toolbar now (client 2026-08-02). */
  readonly linked?: boolean;
  /**
   * WHAT THE PREVIEW PUBLISHED, REPORTED UP (design review 2026-07-31).
   *
   * The preview payload lives here — it is client memory, per site, keyed on server
   * facts — but two things ABOVE the panes need facts from it and had no way to reach
   * them: the toolbar's off-axis presets need to know whether a seated pose exists
   * (without it they rotated pane 1 alone while claiming all three), and the ALIGNMENT
   * strip printed "—" for a deviation the union pane below was already showing.
   *
   * Reported rather than lifted: hoisting the whole slot map into DeclareStage would
   * move the auto-fire, its double-POST guard and its stale-response rejection away
   * from the component they were written for. Facts only, and every one the server's.
   */
  readonly onPreviewFigures?: (figures: PreviewFigures | null) => void;
}

/** The container: the shared pane scene, the auto-fired preview slots, the tick's two
 * requests. */
export function DeclarePanes({
  detail,
  site,
  onDetail,
  postPreview: postPreviewFn = postPreview,
  viewPreset,
  viewPresetNonce,
  zoomLevel,
  linked,
  onPreviewFigures,
}: DeclarePanesProps) {
  const caseId = detail.case.id;
  const tooth = site?.tooth ?? null;
  const mountedRef = useRef(true);

  const [previews, setPreviews] = useState<PreviewSlots>({});
  // THE SEATED FALLBACK's slots (§10-AE): per tooth, the shipped fit for sites the
  // ladder will not preview. A read, never an act — see domain/declare.
  const [seatedSlots, setSeatedSlots] = useState<
    Record<number, {
      readonly phase: "loading" | "ready" | "error";
      readonly payload: SitePreviewPayload | null;
      readonly error: string | null;
    }>
  >({});
  const [reviewSaving, setReviewSaving] = useState<ReviewSaving>("idle");
  const [reviewError, setReviewError] = useState<string | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // THE AUTO-FIRED PREVIEW (per-site, non-blocking): fire exactly when the pure
  // helper says so. The async guards live in the firer (domain/declare.ts, tested
  // there with an injectable post): claiming is synchronous so a doubled effect run
  // cannot double-POST, and a settling response only writes a slot that still holds
  // ITS key — a stale answer never overwrites a newer ask.
  const key = previewKeyFor(detail, tooth);
  const slot = tooth !== null ? previews[tooth] : undefined;
  const firer = useMemo(
    () =>
      createPreviewFirer({
        caseId,
        post: postPreviewFn,
        update: setPreviews,
        isLive: () => mountedRef.current,
        onSettled: (result) => {
          if (result.kind === "ok") {
            // the site moved declared→previewed SERVER-side; re-read the whole
            // truth rather than patching a status locally (trust direction, AM-4)
            void fetchCaseSession(caseId).then((fresh) => {
              if (mountedRef.current && fresh.kind === "ok") onDetail(fresh.data);
            });
          }
        },
      }),
    [caseId, postPreviewFn, onDetail],
  );
  useEffect(() => {
    if (tooth === null || key === null) return;
    if (!shouldAutoPreview({ key, slotKey: slot?.key ?? null })) return;
    firer.maybeFire(tooth, key);
  }, [tooth, key, slot?.key, firer]);

  const payload =
    slot !== undefined && slot.key === key && slot.state === "ready"
      ? (slot.payload ?? null)
      : null;

  // THE SEATED FALLBACK (§10-AE): fire the read exactly when the pure rule says the
  // preview lane is closed over a done run; a settled slot never re-fires.
  const wantSeated = seatedReadWanted({
    tooth,
    previewKey: key,
    runState: detail.session.run_state,
    siteStatus: site?.status ?? null,
  });
  const seatedSlot = tooth !== null && wantSeated ? seatedSlots[tooth] : undefined;
  useEffect(() => {
    if (!wantSeated || tooth === null) return;
    if (seatedSlot !== undefined) return;
    setSeatedSlots((slots) => ({
      ...slots,
      [tooth]: { phase: "loading", payload: null, error: null },
    }));
    void fetchSeated(caseId, tooth).then((result) => {
      if (!mountedRef.current) return;
      setSeatedSlots((slots) => ({
        ...slots,
        [tooth]:
          result.kind === "ok"
            ? { phase: "ready", payload: result.data, error: null }
            : { phase: "error", payload: null, error: result.detail },
      }));
    });
  }, [wantSeated, tooth, caseId, seatedSlot]);
  const seatedPayload =
    seatedSlot?.phase === "ready" ? (seatedSlot.payload ?? null) : null;
  // the SCENE wears whichever payload exists; the preview FIGURES stay the preview
  // lane's own (the strip's (run) numbers already speak for the shipped fit)
  const panePayload = payload ?? seatedPayload;
  const previewPhase: PreviewPhase =
    key === null || slot === undefined || slot.key !== key
      ? "idle"
      : slot.state === "ready"
        ? "ready"
        : slot.state;

  const scene = useSitePaneScene(detail, site, panePayload, {
    viewPreset,
    viewPresetNonce,
    zoomLevel,
    linked,
  });

  /* Reported on the PRIMITIVES, not on the payload object: the payload is replaced
     wholesale on every settle, and an effect keyed on it would re-report identical
     figures on every unrelated re-render of the slot map. */
  const posePresent = payload?.pose != null;
  const rmsMm = payload?.stats.rms_mm ?? null;
  const p90Mm = payload?.stats.p90_mm ?? null;
  const statsSource = payload?.stats.source ?? null;
  const hasPayload = payload !== null;
  useEffect(() => {
    if (onPreviewFigures === undefined) return;
    onPreviewFigures(
      hasPayload
        ? {
            poseAvailable: posePresent,
            rmsMm,
            p90Mm,
            // the payload's own word for what measured it, never one of ours
            source: statsSource ?? "preview",
          }
        : null,
    );
  }, [onPreviewFigures, hasPayload, posePresent, rmsMm, p90Mm, statsSource]);

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
    if (tooth !== null && key !== null) firer.fire(tooth, key);
  }, [tooth, key, firer]);

  const notices = paneNotices({
    site,
    choicesComplete: detail.choices.complete,
    partMeshKnown: scene.partMeshKnown,
    partError: scene.partError,
    scanError: scene.scanError,
    scanEmpty: scene.scanEmpty,
    previewPhase,
    previewError: slot?.state === "error" ? (slot.error ?? null) : null,
    // the seated fallback's fit is on the panes — "the preview has not run"
    // would contradict the colouring it overlays (§10-AE.1)
    shippedReadPresent: seatedPayload !== null,
  });

  return (
    /* No link props flow to the view: the toggle moved to the workspace toolbar, and
       with nothing to hold, SitePanesView's chrome row stands down except while a pane
       is maximized (client 2026-08-02, the three-rows complaint). */
    <DeclarePanesView
      site={site}
      variantLabel={site?.declared_variant ?? null}
      notices={notices}
      partBusy={scene.partBusy}
      scanBusy={scene.scanBusy}
      scanCaption={scene.scanCaption}
      previewPhase={previewPhase}
      payload={panePayload}
      payloadSource={payload !== null ? "preview" : seatedPayload !== null ? "seated" : "preview"}
      seatedPhase={wantSeated ? (seatedSlot?.phase ?? "idle") : "idle"}
      seatedError={wantSeated ? (seatedSlot?.error ?? null) : null}
      tick={reviewTick(site)}
      reviewSaving={reviewSaving}
      reviewError={reviewError}
      onToggleReview={handleToggleReview}
      onRetryPreview={handleRetryPreview}
      layers={scene.layers}
      onToggleLayer={scene.onToggleLayer}
      onChangeOpacity={scene.onChangeOpacity}
      maximizedId={scene.maximizedId}
      onToggleMaximized={scene.onToggleMaximized}
      onResetView={scene.onResetView}
      scaleId={scene.scaleId}
      onSelectScale={scene.onSelectScale}
      libraryViewer={scene.libraryViewer}
      scanViewer={scene.scanViewer}
      unionViewer={scene.unionViewer}
    />
  );
}
