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
 * PARITY SLICE: the panes wear the demo's verify-panel clothes (copy-debt ledger
 * row 9 — VerifyPanels' presentational markup, re-worn against product state): the
 * stage fills the pane's height, the LAYER controls float as the top-left on-glass
 * HUD (eye + opacity slider), the deviation COLORBAR is the union pane's bottom-strip
 * HUD (the same ramp the mesh wears — deviationGradientCss — with the signed ticks
 * and the payload's RMS/p90), and the honest words are overlay strips, never a
 * stacked paragraph stealing pane height.
 *
 * THE REVIEW TICK sits here, with the panes it attests (AM-8: "reviewed over panels,
 * not a checkbox"), in the demo's acknowledgment-bar language: enabled only once the
 * site is previewed; tick = POST review, untick = DELETE — the BFF's status machine
 * judges both, this surface only offers what the server would accept and renders
 * what came back (optimism OFF, AM-4).
 *
 * The preview AUTO-FIRES per site (domain/declare.previewKeyFor + shouldAutoPreview —
 * keyed on server facts, one request per distinct declaration+choices) and is
 * per-site NON-BLOCKING: stepping sites while one previews is legal; each site's
 * slot settles on its own and a stale response never overwrites a newer ask.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  CAP_REGION_RADIUS_MM,
  CONTACTS_MAX_MM,
  OrbitLinkGroup,
  PALETTE,
  UNMEASURED_COLOR_HEX,
  VerifyViewer,
  buildScaleColors,
  clampNoteFor,
  computeAnatomyFrame,
  computePartFrame,
  contactsGradientCss,
  contactsTickLabels,
  cropTrianglesNear,
  deviationGradientCss,
  deviationTickLabels,
  loadStlPositions,
  paletteHex,
  scanPositionsFor,
  triangleCount,
  type DeviationScaleId,
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
  attestationAction,
  attestationSentence,
  createPreviewFirer,
  indicesFrom,
  paneNotices,
  partCameraFrame,
  positionsFrom,
  previewKeyFor,
  reviewTick,
  shouldAutoPreview,
  siteFrameFor,
  variantMeshUrl,
  type PaneNotices,
  type PostPreviewFn,
  type PreviewPhase,
  type PreviewSlots,
  type ReviewTickState,
} from "../domain/declare";

// The slot types and their async guards live in domain/declare.ts since 5c (the 5b
// review's M1: the double-POST guard and the stale-response rejection are pure rules,
// tested there with an injectable postPreview); re-exported so the shape stays
// addressable beside the component that renders it.
export type { PreviewSlot, PreviewSlots } from "../domain/declare";

/** What the review wiring is doing, named — the surface states it (optimism OFF). */
export type ReviewSaving = "idle" | "ticking" | "unticking";

/** The pane ids — pane 1/2/3 in the module doc's order. */
export type PaneId = "library" | "scan" | "union";

/** One controllable layer inside a pane — the demo dialog's eye + opacity slider.
 * `swatch` is the layer's 3D colour (null = the deviation ramp, which has the
 * colorbar instead); `available` is false while the geometry has not arrived. */
export interface PaneLayerControl {
  readonly id: string;
  readonly label: string;
  readonly swatch: string | null;
  readonly visible: boolean;
  readonly opacity: number;
  readonly available: boolean;
}

export type PaneLayers = Readonly<Record<PaneId, readonly PaneLayerControl[]>>;

interface LayerHudProps {
  readonly pane: PaneId;
  readonly layers: readonly PaneLayerControl[];
  readonly onToggleLayer: (pane: PaneId, layerId: string) => void;
  readonly onChangeOpacity: (pane: PaneId, layerId: string, opacity: number) => void;
}

/** The top-left on-glass layer HUD — the demo's verify-layer rows, verbatim clothes. */
function LayerHud({ pane, layers, onToggleLayer, onChangeOpacity }: LayerHudProps) {
  return (
    <div className="verify-panel__hud verify-panel__hud--layers">
      {layers.map((layer) => (
        <div key={layer.id} className="verify-layer">
          <button
            type="button"
            className={`verify-layer__eye${layer.visible ? " verify-layer__eye--on" : ""}`}
            aria-pressed={layer.visible}
            aria-label={`${layer.visible ? "Hide" : "Show"} ${layer.label}`}
            disabled={!layer.available}
            onClick={() => onToggleLayer(pane, layer.id)}
          >
            {layer.visible ? "👁" : "🚫"}
          </button>
          {layer.swatch !== null && (
            <span className="verify-layer__swatch" style={{ background: layer.swatch }} />
          )}
          <span className="verify-layer__label">{layer.label}</span>
          <label className="sr-only" htmlFor={`opacity-${pane}-${layer.id}`}>
            {layer.label} opacity
          </label>
          <input
            id={`opacity-${pane}-${layer.id}`}
            className="verify-layer__slider"
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={layer.opacity}
            disabled={!layer.available || !layer.visible}
            onChange={(e) => onChangeOpacity(pane, layer.id, Number(e.target.value))}
          />
          <span className="verify-layer__percent">{Math.round(layer.opacity * 100)}%</span>
        </div>
      ))}
    </div>
  );
}

/** The two scales the union pane offers, with the one-line difference stated on each —
 * the demo's SCALE_CHOICES verbatim: the selector is only honest if it says what
 * changes, since both bars look plausible on a cap. */
const SCALE_CHOICES: readonly {
  readonly id: DeviationScaleId;
  readonly label: string;
  readonly hint: string;
}[] = [
  {
    id: "signed",
    label: "Signed ±0.50 mm",
    hint:
      "Ours (RdBu, the same convention the deviation PNG prints): shows DIRECTION — red = the " +
      "scan sits proud of the cap, blue = it sinks into it.",
  },
  {
    id: "contacts",
    label: `Contacts 0.00–${CONTACTS_MAX_MM.toFixed(2)} mm`,
    hint:
      "RealGUIDE's absolute rainbow: magnitude only, no direction — blue at 0.00 (agreement) " +
      "through to red at the top of the bar. Use the signed scale to tell proud from sunk.",
  },
];

function ScaleSelector({
  scaleId,
  onSelectScale,
}: {
  readonly scaleId: DeviationScaleId;
  readonly onSelectScale: (id: DeviationScaleId) => void;
}) {
  return (
    <div className="verify-colorbar__scales" role="radiogroup" aria-label="Deviation colour scale">
      {SCALE_CHOICES.map((choice) => (
        <button
          key={choice.id}
          type="button"
          role="radio"
          aria-checked={choice.id === scaleId}
          className={`verify-colorbar__scale${choice.id === scaleId ? " verify-colorbar__scale--selected" : ""}`}
          title={choice.hint}
          onClick={() => onSelectScale(choice.id)}
        >
          {choice.label}
        </button>
      ))}
    </div>
  );
}

/** The union pane's bottom-strip colorbar HUD: the SAME ramp the mesh wears (one
 * source — the copied deviationColormap, keyed by the shared scaleId so bar and
 * surface never disagree), its ticks, and the payload's PUBLISHED RMS/p90
 * (data-role="union-stats", the tested promise). The convention, the unmeasured
 * swatch, the clamp note and the stats' source live in the demo's legend-and-stats
 * FOLD — occasionally-needed small print must not cost the pane permanent 3D height. */
function ColorbarHud({
  payload,
  scaleId = "signed",
  onSelectScale,
}: {
  readonly payload: SitePreviewPayload;
  readonly scaleId?: DeviationScaleId;
  readonly onSelectScale?: (id: DeviationScaleId) => void;
}) {
  const clampMm = payload.scale.clamp_mm;
  const contacts = scaleId === "contacts";
  const clampNote = contacts
    ? null
    : clampNoteFor(payload.scale.data_min_mm, payload.scale.data_max_mm, clampMm);
  const ticks = contacts ? contactsTickLabels(CONTACTS_MAX_MM) : deviationTickLabels(clampMm);
  return (
    <div className="verify-panel__hud verify-panel__hud--scale">
      <div className="verify-colorbar">
        {onSelectScale !== undefined && (
          <ScaleSelector scaleId={scaleId} onSelectScale={onSelectScale} />
        )}
        <div
          className="verify-colorbar__bar"
          style={{ background: contacts ? contactsGradientCss() : deviationGradientCss() }}
          role="img"
          aria-label={
            contacts
              ? `Contacts scale from 0 to ${CONTACTS_MAX_MM} millimetres, absolute distance`
              : `Deviation scale from -${clampMm} to +${clampMm} millimetres`
          }
        />
        <div className="verify-colorbar__ticks">
          {ticks.map((label) => (
            <span key={label}>{label}</span>
          ))}
        </div>
        {/* THE WORDS, FOLDED — the demo's rule kept with its markup: the convention,
            the unmeasured swatch, the clamp note and the published stats are small
            print a QC read needs OCCASIONALLY; a <details> keeps every word in the
            document (and the accessibility tree) while the pane keeps its 3D height. */}
        <details className="verify-colorbar__detail">
          <summary className="verify-colorbar__summary">legend &amp; stats</summary>
          <p className="verify-colorbar__legend">
            <span className="verify-colorbar__convention">
              {contacts
                ? "absolute distance — no direction; switch to the signed scale to see proud vs sunk"
                : payload.scale.sign_convention}
            </span>
            <span className="verify-colorbar__unmeasured">
              <span
                className="verify-colorbar__swatch"
                style={{ background: UNMEASURED_COLOR_HEX }}
              />
              no scan surface under the vertex — not measured
            </span>
          </p>
          {clampNote !== null && <p className="verify-colorbar__clamp">{clampNote}</p>}
          <p data-role="union-stats" className="verify-colorbar__stats">
            Deviation over the footprint: RMS{" "}
            {payload.stats.rms_mm !== null ? `${payload.stats.rms_mm.toFixed(3)} mm` : "—"}
            {" · "}p90{" "}
            {payload.stats.p90_mm !== null ? `${payload.stats.p90_mm.toFixed(3)} mm` : "—"}{" "}
            <span className="verify-colorbar__source">({payload.stats.source})</span>
          </p>
        </details>
      </div>
    </div>
  );
}

interface PaneShellProps {
  readonly role: string;
  readonly title: string;
  readonly caption: string | null;
  readonly notice: string | null;
  readonly busy: boolean;
  readonly busyMessage: string | null;
  readonly viewer: ReactNode;
  /** The on-glass chrome (layer HUD, colorbar) — floats ON the stage. */
  readonly hud?: ReactNode;
  /** A clickable bottom strip (the union pane's preview retry) — the invite tone. */
  readonly invite?: ReactNode;
  /** The demo's per-pane maximize (parity fix): true while this pane IS the stage. */
  readonly maximized?: boolean;
  /** Omitted (static tests that predate it), the heading renders without the control. */
  readonly onToggleMaximized?: (() => void) | null;
}

/** One pane in the demo's verify-panel clothes: header (title + one-line caption),
 * then THE STAGE — the only thing with height; every word floats on it. */
function PaneShell({
  role,
  title,
  caption,
  notice,
  busy,
  busyMessage,
  viewer,
  hud,
  invite,
  maximized = false,
  onToggleMaximized = null,
}: PaneShellProps) {
  return (
    <section data-role={role} aria-label={title} className="verify-panel">
      <header className="verify-panel__header">
        <div className="verify-panel__heading">
          <h4 className="verify-panel__title">{title}</h4>
          {onToggleMaximized !== null && (
            <button
              type="button"
              className="verify-panel__maximize"
              aria-pressed={maximized}
              aria-label={
                maximized
                  ? `Restore ${title} to the three-panel view`
                  : `Maximise ${title}`
              }
              title={
                maximized
                  ? "Back to all three panels"
                  : "Expand this panel to the whole stage"
              }
              onClick={onToggleMaximized}
            >
              {maximized ? "⤡" : "⤢"}
            </button>
          )}
        </div>
        {caption !== null && (
          <p data-role="pane-caption" className="verify-panel__caption" title={caption}>
            {caption}
          </p>
        )}
      </header>
      <div className="verify-panel__stage">
        {viewer}
        {hud}
        {busy && (
          <div className="verify-panel__overlay" role="status" aria-live="polite">
            <span className="busy-state__spinner" aria-hidden="true" />
            <span data-role="pane-busy">{busyMessage ?? "Loading…"}</span>
          </div>
        )}
        {!busy && notice !== null && (
          <div
            className="verify-panel__overlay verify-panel__overlay--notice"
            role="status"
          >
            <span data-role="pane-notice">{notice}</span>
          </div>
        )}
        {invite}
      </div>
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
  /** The on-glass layer controls (parity slice). Omitted (static tests that predate
   * them), the panes render without the HUD — the container always passes them. */
  readonly layers?: PaneLayers;
  readonly onToggleLayer?: (pane: PaneId, layerId: string) => void;
  readonly onChangeOpacity?: (pane: PaneId, layerId: string, opacity: number) => void;
  /** The demo toolbar's link-orbits toggle (parity fix): panes orbit independently by
   * default and are LINKED on demand. Omitted, the toolbar does not render. */
  readonly linked?: boolean;
  readonly onToggleLinked?: () => void;
  /** The pane expanded to the whole stage, or null while all three share it — the
   * demo's per-pane maximize. The other two UNMOUNT (their viewer slots are simply
   * not rendered): three live WebGL contexts is the cost this control exists to
   * spend elsewhere. Handler omitted, the controls do not render. */
  readonly maximizedId?: PaneId | null;
  readonly onToggleMaximized?: (pane: PaneId) => void;
  /** WHICH colouring the union mesh is wearing (the demo's two-scale offer): the
   * container colours the mesh by the same id, so bar and surface never disagree.
   * Handler omitted, the selector does not render and the signed bar stands. */
  readonly scaleId?: DeviationScaleId;
  readonly onSelectScale?: (id: DeviationScaleId) => void;
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
  layers,
  onToggleLayer = () => undefined,
  onChangeOpacity = () => undefined,
  linked = false,
  onToggleLinked,
  maximizedId = null,
  onToggleMaximized,
  scaleId = "signed",
  onSelectScale,
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
  const hudFor = (pane: PaneId): ReactNode =>
    layers !== undefined && layers[pane].length > 0 ? (
      <LayerHud
        pane={pane}
        layers={layers[pane]}
        onToggleLayer={onToggleLayer}
        onChangeOpacity={onChangeOpacity}
      />
    ) : null;
  /** Maximised, the other two panes are UNMOUNTED, not hidden (the demo's rule). */
  const showPane = (pane: PaneId): boolean => maximizedId === null || maximizedId === pane;
  const maximizeFor = (pane: PaneId): (() => void) | null =>
    onToggleMaximized !== undefined ? () => onToggleMaximized(pane) : null;
  return (
    <div data-role="declare-panes" className="verify-panels">
      {onToggleLinked !== undefined && (
        <div className="verify-panels__toolbar">
          {maximizedId !== null && onToggleMaximized !== undefined && (
            <button
              type="button"
              className="button button--ghost button--small"
              onClick={() => onToggleMaximized(maximizedId)}
            >
              ⤡ show all three
            </button>
          )}
          <button
            type="button"
            className={`button button--ghost button--small${linked ? " button--active" : ""}`}
            aria-pressed={linked}
            disabled={maximizedId !== null}
            onClick={onToggleLinked}
            title={
              maximizedId !== null
                ? "Linking needs more than one panel on screen"
                : "Rotate all three panels together (same angles and zoom, each around its own content)"
            }
          >
            {linked ? "⛓ views linked" : "⛓ link views"}
          </button>
        </div>
      )}
      <div
        className={`verify-panels__grid${
          maximizedId !== null ? " verify-panels__grid--maximized" : ""
        }`}
      >
        {showPane("library") && (
          <PaneShell
            role="pane-library"
            title="1 · Library part"
            caption={variantLabel}
            notice={notices.part}
            busy={partBusy}
            busyMessage="Loading the library part…"
            viewer={libraryViewer}
            hud={hudFor("library")}
            maximized={maximizedId === "library"}
            onToggleMaximized={maximizeFor("library")}
          />
        )}
        {showPane("scan") && (
          <PaneShell
            role="pane-scan"
            title="2 · Scanned cap"
            caption={scanCaption}
            notice={notices.scan}
            busy={scanBusy}
            busyMessage="Loading the scan…"
            viewer={scanViewer}
            hud={hudFor("scan")}
            maximized={maximizedId === "scan"}
            onToggleMaximized={maximizeFor("scan")}
          />
        )}
        {showPane("union") && (
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
            hud={
              <>
                {hudFor("union")}
                {payload !== null && (
                  <ColorbarHud
                    payload={payload}
                    scaleId={scaleId}
                    onSelectScale={onSelectScale}
                  />
                )}
              </>
            }
            invite={
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
            maximized={maximizedId === "union"}
            onToggleMaximized={maximizeFor("union")}
          />
        )}
      </div>
      {/* THE ATTESTATION BAR, under the panes it attests — the demo's decode-ack bar
          shape (text side yields, the ACT never shrinks). Client 2026-07-27 #2: "The
          reviewed over the panes check mark needs to be better confirmed" — so the
          checkbox became a button-weight act with the SENTENCE beside it naming what
          is attested for this site, and withdrawing is equally explicit. The
          authorization itself has not moved: this is still the same ladder event
          (POST/DELETE .../review) that the run gate reads. */}
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
    </div>
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

/** One layer's presentational state (the HUD's) — the geometry itself stays memoed. */
interface LayerToggle {
  readonly visible: boolean;
  readonly opacity: number;
}

/** The union pane's scan opacity default: the client's own 0.45, kept from the demo. */
const LAYER_DEFAULTS: Readonly<Record<string, LayerToggle>> = {
  "library:part": { visible: true, opacity: 1 },
  "scan:scan": { visible: true, opacity: 1 },
  "union:scan": { visible: true, opacity: 0.45 },
  "union:deviation": { visible: true, opacity: 1 },
};

/** The container: scan + part meshes, the auto-fired preview slots, the tick's two
 * requests, the HUD's layer state, and the three VerifyViewers with their frames. */
export function DeclarePanes({
  detail,
  site,
  onDetail,
  postPreview: postPreviewFn = postPreview,
}: DeclarePanesProps) {
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

  // The demo toolbar's pane chrome (parity fix, ledger row 9) — all presentational,
  // container-local: orbit linking OFF by default (the demo's opening state), no pane
  // maximised, the signed scale on the union mesh and its bar alike.
  const [linked, setLinked] = useState(false);
  const [maximizedId, setMaximizedId] = useState<PaneId | null>(null);
  const [scaleId, setScaleId] = useState<DeviationScaleId>("signed");
  useEffect(() => {
    linkGroupRef.current.setEnabled(linked);
  }, [linked]);
  const handleToggleLinked = useCallback(() => setLinked((now) => !now), []);
  const handleToggleMaximized = useCallback((pane: PaneId) => {
    setMaximizedId((now) => (now === pane ? null : pane));
  }, []);

  // The HUD's layer state (presentational only): visibility/opacity per pane:layer,
  // seeded from the demo's defaults (union scan at 0.45).
  const [layerToggles, setLayerToggles] =
    useState<Readonly<Record<string, LayerToggle>>>(LAYER_DEFAULTS);
  const toggleOf = (pane: PaneId, layerId: string): LayerToggle =>
    layerToggles[`${pane}:${layerId}`] ??
    LAYER_DEFAULTS[`${pane}:${layerId}`] ?? { visible: true, opacity: 1 };
  const handleToggleLayer = useCallback((pane: PaneId, layerId: string) => {
    setLayerToggles((current) => {
      const key = `${pane}:${layerId}`;
      const now = current[key] ?? LAYER_DEFAULTS[key] ?? { visible: true, opacity: 1 };
      return { ...current, [key]: { ...now, visible: !now.visible } };
    });
  }, []);
  const handleChangeOpacity = useCallback(
    (pane: PaneId, layerId: string, opacity: number) => {
      setLayerToggles((current) => {
        const key = `${pane}:${layerId}`;
        const now = current[key] ?? LAYER_DEFAULTS[key] ?? { visible: true, opacity: 1 };
        return { ...current, [key]: { ...now, opacity } };
      });
    },
    [],
  );

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

  // Coloured by WHICHEVER scale the bar is showing (buildScaleColors is the one entry
  // point for both ramps — the demo's rule: mesh and colorbar can never disagree).
  const deviationGeometry: VerifyLayerGeometry | null = useMemo(() => {
    if (payload === null) return null;
    return {
      positions: positionsFrom(payload.points),
      indices: indicesFrom(payload.faces),
      colors: buildScaleColors(scaleId, payload.deviation_mm, payload.scale.clamp_mm),
    };
  }, [payload, scaleId]);

  // Pane 1: down the part's own file axis (+z), up +x — partCameraFrame (the pure
  // rule, unit-pinned in domain/declare.test.ts) over the viewer's fitted frame;
  // an unreadably-revolute mesh yields null and the default framing wins.
  const partFrame = useMemo(
    () =>
      partCameraFrame(
        partPositions !== null ? computePartFrame(partPositions) : null,
      ),
    [partPositions],
  );

  // Panes 2/3: siteFrameFor (the demo's seatedFrame/occlusal semantics as one pure,
  // unit-pinned rule) — the preview pose's EXACT axis when one exists, else the
  // jaw's occlusal proxy, computed ONCE per case's scan and memoized here.
  const occlusal = useMemo(() => {
    if (scanPositions === null) return null;
    return (computeAnatomyFrame(scanPositions)?.occlusal ?? null) as Vec3 | null;
  }, [scanPositions]);
  const pose = payload?.pose ?? null;
  const siteFrame = siteFrameFor(siteCenter, pose, occlusal, CAP_REGION_RADIUS_MM);

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

  // The HUD's control rows: swatches ARE the 3D colours (paletteHex — the list and
  // the model must read as the same thing); the deviation layer has the ramp instead.
  const layers: PaneLayers = {
    library: [
      {
        id: "part",
        label: "library part",
        swatch: paletteHex("cap"),
        ...toggleOf("library", "part"),
        available: partGeometry !== null,
      },
    ],
    scan: [
      {
        id: "scan",
        label: "scanned cap",
        swatch: paletteHex("arch"),
        ...toggleOf("scan", "scan"),
        available: scanGeometry !== null,
      },
    ],
    union: [
      {
        id: "scan",
        label: "scan",
        swatch: paletteHex("arch"),
        ...toggleOf("union", "scan"),
        available: scanGeometry !== null,
      },
      {
        id: "deviation",
        label: "preview deviation",
        swatch: null,
        ...toggleOf("union", "deviation"),
        available: deviationGeometry !== null,
      },
    ],
  };

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
      layers={layers}
      onToggleLayer={handleToggleLayer}
      onChangeOpacity={handleChangeOpacity}
      linked={linked}
      onToggleLinked={handleToggleLinked}
      maximizedId={maximizedId}
      onToggleMaximized={handleToggleMaximized}
      scaleId={scaleId}
      onSelectScale={setScaleId}
      libraryViewer={
        <VerifyViewer
          layers={[
            {
              id: "part",
              geometry: partGeometry,
              visible: toggleOf("library", "part").visible,
              opacity: toggleOf("library", "part").opacity,
            },
          ]}
          frame={partFrame}
          linkGroup={linkGroup}
          ariaLabel="The declared library part"
        />
      }
      scanViewer={
        <VerifyViewer
          layers={[
            {
              id: "scan",
              geometry: scanGeometry,
              visible: toggleOf("scan", "scan").visible,
              opacity: toggleOf("scan", "scan").opacity,
            },
          ]}
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
            {
              id: "scan",
              geometry: scanGeometry,
              visible: toggleOf("union", "scan").visible,
              opacity: toggleOf("union", "scan").opacity,
            },
            {
              id: "deviation",
              geometry: deviationGeometry,
              visible: toggleOf("union", "deviation").visible,
              opacity: toggleOf("union", "deviation").opacity,
            },
          ]}
          frame={siteFrame}
          linkGroup={linkGroup}
          ariaLabel="The scan and the previewed cap overlaid, coloured by deviation"
        />
      }
    />
  );
}
