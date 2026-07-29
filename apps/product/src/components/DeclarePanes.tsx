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
  shouldAutoPreview,
  type PaneNotices,
  type PostPreviewFn,
  type PreviewPhase,
  type PreviewSlots,
  type ReviewTickState,
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
export function previewCaption(payload: SitePreviewPayload | null): string | null {
  if (payload === null) return null;
  const seat = payload.seat ?? null;
  const seated = seat?.seat_method ? `${seat.seat_method} seat` : "seated";
  const rim =
    seat?.rim_agreement_mm !== null && seat?.rim_agreement_mm !== undefined
      ? `, rim ${seat.rim_agreement_mm.toFixed(2)} mm`
      : "";
  return `preview — this selection seated now (${seated}${rim}); nothing processed yet`;
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
  readonly layers?: PaneLayers;
  readonly onToggleLayer?: (pane: PaneId, layerId: string) => void;
  readonly onChangeOpacity?: (pane: PaneId, layerId: string, opacity: number) => void;
  readonly linked?: boolean;
  readonly onToggleLinked?: () => void;
  readonly maximizedId?: PaneId | null;
  readonly onToggleMaximized?: (pane: PaneId) => void;
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
      unionCaption={previewCaption(payload)}
      unionBusy={previewPhase === "computing" || scanBusy}
      unionBusyMessage={
        previewPhase === "computing"
          ? "seating this selection on the scan — preview, nothing is being processed…"
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
}

/** The container: the shared pane scene, the auto-fired preview slots, the tick's two
 * requests. */
export function DeclarePanes({
  detail,
  site,
  onDetail,
  postPreview: postPreviewFn = postPreview,
}: DeclarePanesProps) {
  const caseId = detail.case.id;
  const tooth = site?.tooth ?? null;
  const mountedRef = useRef(true);

  const [previews, setPreviews] = useState<PreviewSlots>({});
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
  const previewPhase: PreviewPhase =
    key === null || slot === undefined || slot.key !== key
      ? "idle"
      : slot.state === "ready"
        ? "ready"
        : slot.state;

  const scene = useSitePaneScene(detail, site, payload);

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
  });

  return (
    <DeclarePanesView
      site={site}
      variantLabel={site?.declared_variant ?? null}
      notices={notices}
      partBusy={scene.partBusy}
      scanBusy={scene.scanBusy}
      scanCaption={scene.scanCaption}
      previewPhase={previewPhase}
      payload={payload}
      tick={reviewTick(site)}
      reviewSaving={reviewSaving}
      reviewError={reviewError}
      onToggleReview={handleToggleReview}
      onRetryPreview={handleRetryPreview}
      layers={scene.layers}
      onToggleLayer={scene.onToggleLayer}
      onChangeOpacity={scene.onChangeOpacity}
      linked={scene.linked}
      onToggleLinked={scene.onToggleLinked}
      maximizedId={scene.maximizedId}
      onToggleMaximized={scene.onToggleMaximized}
      scaleId={scene.scaleId}
      onSelectScale={scene.onSelectScale}
      libraryViewer={scene.libraryViewer}
      scanViewer={scene.scanViewer}
      unionViewer={scene.unionViewer}
    />
  );
}
