/**
 * THE THREE PANES, SHARED (extracted in slice 6 from DeclarePanes, plan §4 Adjust:
 * "the SAME three panes as Declare — extract what is shared rather than copying it").
 *
 * Declare and Adjust show one operator the same three views of one site:
 *
 *   pane 1 — the declared LIBRARY PART in its canonical frame, down its file +z, up +x.
 *   pane 2 — the SCANNED CAP: the streamed arch cropped at the site's centre, framed
 *            down the seated pose's EXACT axis when one exists, else the jaw's occlusal
 *            proxy (the demo's honesty story: the proxy sat 6.2°-42.0° off the real
 *            axis across the fleet; the pose is exact by construction).
 *   pane 3 — the UNION: the payload coloured by deviation, pose-axis framed, up shared
 *            with pane 1 so the coded cutout reads at the same clock angle everywhere.
 *
 * What differs between the two stages is WHERE the union payload comes from — a
 * pre-run PREVIEW seat at Declare, the SHIPPED pose at Adjust — and what sits under
 * the panes: Declare's attestation bar, Adjust's toolbox. Both are slots here
 * (`payload`, `footer`), so the panes themselves have exactly one implementation and
 * the two stages cannot drift into showing different geometry for the same site.
 *
 * The chrome is the frozen demo's VerifyPanels, worn against product state (copy-debt
 * ledger row 9): the on-glass layer HUD, the deviation colorbar with its two scales
 * and its folded legend, per-pane maximize (the other two UNMOUNT — three live WebGL
 * contexts is the cost the control exists to spend elsewhere), and the link-orbits
 * toggle.
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
  type VerifyMarker,
} from "viewer";
import {
  scanUrlFor,
  type CaseSessionDetail,
  type SitePreviewPayload,
  type SiteView,
} from "../api/client";
import {
  indicesFrom,
  partCameraFrame,
  positionsFrom,
  siteFrameFor,
  variantMeshUrl,
} from "../domain/declare";

/** The pane ids — pane 1/2/3 in the module doc's order. */
export type PaneId = "library" | "scan" | "union";

/** Pane 1, 2, 3 — the order the operator counts in, and the order the toolbox's
 *  prompts cite ("Library part · pane 1", "Scanned cap · pane 2 or 3"). */
export const PANE_ORDER: readonly PaneId[] = ["library", "scan", "union"];

/** ONE source for each pane's heading, so the number in the switcher and the number in
 *  the heading can never disagree — they are the operator's whole address for a pane. */
export const PANE_TITLES: Readonly<Record<PaneId, string>> = {
  library: "1 · Library part",
  scan: "2 · Scanned cap",
  union: "3 · Union — coloured by deviation",
};

/**
 * Pane 2's caption. The TOOTH leads it (client 2026-07-30): the triangle count says how
 * much scan is on screen but not WHOSE, and the only other place the tooth number
 * appears is the queue rail — which scrolls, so on a long case the operator could have
 * three panes up and nothing on any of them naming the site.
 */
export function scanPaneCaption(
  tooth: number | null,
  triangles: number,
  radiusMm: number,
): string {
  const measured = `${triangles.toLocaleString()} triangles within ${radiusMm} mm of the site's centre`;
  return tooth === null ? measured : `Tooth ${tooth} · ${measured}`;
}

/**
 * Pane 1's caption. The variant CODE alone is not an identity — the same 5020 means a
 * different part under a different implant system, and the system is already on the
 * detail that drives the variant catalog, so saying it costs no fetch (client
 * 2026-07-30). Kept to one short segment: captions are single-line by design, and a
 * wrapping caption once stole height from all three stages at once.
 */
export function libraryPaneCaption(
  variantLabel: string | null,
  systemLabel: string | null,
): string | null {
  if (variantLabel === null) return null;
  const system = systemLabel?.trim() ?? "";
  return system === "" ? variantLabel : `${variantLabel} · ${system}`;
}

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
  /** A clickable bottom strip (the union pane's retry) — the invite tone. */
  readonly invite?: ReactNode;
  /** THE ARMED TELL, ON THE GLASS (client 2026-07-30). The toolbox already named the
   *  pane a click belongs to ("Library part · pane 1") and flipped its button to
   *  "Armed" — but it said so UNDER the panes, so the operator read the instruction in
   *  one place and performed it in another. This is the same sentence where the click
   *  goes. It is a MESSAGE, never a control: `verify-panel__hint` is pointer-events:none
   *  because a notice overlay printed over this stage once swallowed exactly the click it
   *  was inviting (review 2026-07-26, styles.css). */
  readonly hint?: string | null;
  /** Lift the hint clear of the colorbar strip — the union pane's bottom is spoken for. */
  readonly hintRaised?: boolean;
  /** The demo's per-pane maximize (parity fix): true while this pane IS the stage. */
  readonly maximized?: boolean;
  /** Omitted (static tests that predate it), the heading renders without the control. */
  readonly onToggleMaximized?: (() => void) | null;
  /** THE WAY HOME (client 2026-07-29). The main stage has had "This site", "Whole arch"
   *  and the four direction presets since the parity slice; these panes had nothing —
   *  they framed correctly on mount and then, once orbited, could not be recovered
   *  short of changing site. Restores the pane's own framing: for panes 2 and 3 that is
   *  the top-of-cap view down the seated pose's axis, with the shared clock reference
   *  that makes a cutout land at the same screen angle in all three. */
  readonly onResetView?: (() => void) | null;
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
  hint = null,
  hintRaised = false,
  maximized = false,
  onToggleMaximized = null,
  onResetView = null,
}: PaneShellProps) {
  return (
    <section data-role={role} aria-label={title} className="verify-panel">
      <header className="verify-panel__header">
        <div className="verify-panel__heading">
          <h4 className="verify-panel__title">{title}</h4>
          {onResetView !== null && (
            <button
              type="button"
              data-role="pane-reset-view"
              className="verify-panel__reset"
              aria-label={`Restore the framing of ${title}`}
              title="Back to this pane's own view"
              onClick={onResetView}
            >
              ⌖
            </button>
          )}
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
        {!busy && hint !== null && hint !== "" && (
          <p
            data-role="pane-hint"
            className={`verify-panel__hint${hintRaised ? " verify-panel__hint--raised" : ""}`}
          >
            {hint}
          </p>
        )}
      </div>
    </section>
  );
}

/** The three notices, one per pane — the shape both stages' rules produce. */
export interface PaneNoticesShape {
  readonly part: string | null;
  readonly scan: string | null;
  readonly union: string | null;
}

export interface SitePanesViewProps {
  readonly variantLabel: string | null;
  /** The implant system behind that variant code — see libraryPaneCaption. OPTIONAL:
   *  both stages call this view, and one that only compiled for the caller who happened
   *  to be updated first would give back exactly what extracting these panes bought. */
  readonly systemLabel?: string | null;
  readonly notices: PaneNoticesShape;
  readonly partBusy: boolean;
  readonly scanBusy: boolean;
  readonly scanCaption: string | null;
  /** The union pane's own caption — WHOSE colouring is on screen. The two stages
   * answer differently (a preview seat vs the shipped fit) and neither may guess. */
  readonly unionCaption: string | null;
  readonly unionBusy: boolean;
  readonly unionBusyMessage: string | null;
  readonly payload: SitePreviewPayload | null;
  /** The three live canvases — the container passes VerifyViewers; tests pass stubs.
   *  (resetNonce is NOT a view prop: the hook threads it into the viewers it builds,
   *  so the view never sees it — an earlier edit landed it here by mistake and the
   *  fake root tsconfig hid the resulting type break for a whole session.) */
  readonly libraryViewer: ReactNode;
  readonly scanViewer: ReactNode;
  readonly unionViewer: ReactNode;
  /** A clickable bottom strip on the union pane (a retry) — the invite tone. */
  readonly unionInvite?: ReactNode;
  /** WHAT A CLICK ON THIS PANE WILL DO, said on the pane (see PaneShellProps.hint).
   *  Per-pane and optional throughout: Declare arms nothing and passes none. */
  readonly hints?: Partial<Record<PaneId, string | null>>;
  readonly layers?: PaneLayers;
  readonly onToggleLayer?: (pane: PaneId, layerId: string) => void;
  readonly onChangeOpacity?: (pane: PaneId, layerId: string, opacity: number) => void;
  readonly linked?: boolean;
  readonly onToggleLinked?: () => void;
  readonly maximizedId?: PaneId | null;
  /** Restore one pane's own framing — the panes' answer to the main stage's
   *  "This site" (client 2026-07-29). Optional: static tests predate it. */
  readonly onResetView?: ((pane: PaneId) => void) | null;
  readonly onToggleMaximized?: (pane: PaneId) => void;
  readonly scaleId?: DeviationScaleId;
  readonly onSelectScale?: (id: DeviationScaleId) => void;
  /** What sits UNDER the panes: Declare's attestation bar, Adjust's toolbox. */
  readonly footer?: ReactNode;
}

/** The panes' whole surface, pure props → markup — statically testable (the viewer
 * slots are props precisely so WebGL never enters a test). */
export function SitePanesView({
  variantLabel,
  systemLabel = null,
  notices,
  partBusy,
  scanBusy,
  scanCaption,
  unionCaption,
  unionBusy,
  unionBusyMessage,
  payload,
  libraryViewer,
  scanViewer,
  unionViewer,
  unionInvite,
  hints = {},
  layers,
  onToggleLayer = () => undefined,
  onChangeOpacity = () => undefined,
  linked = false,
  onToggleLinked,
  maximizedId = null,
  onToggleMaximized,
  onResetView = null,
  scaleId = "signed",
  onSelectScale,
  footer,
}: SitePanesViewProps) {
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
  /* THE SWITCHER (client 2026-07-30). Maximizing was built; MOVING was not — going from
     a maximized pane 1 to a maximized pane 3 meant un-maximize, hunt for the other
     pane's ⤢, re-maximize. onToggleMaximized already switches directly when handed a
     different pane, so the whole fix is three buttons on the existing setter. It shows
     only while a pane IS the stage: with all three on screen there is nothing to
     switch between. */
  const switching = maximizedId !== null && onToggleMaximized !== undefined;
  return (
    <div data-role="declare-panes" className="verify-panels">
      {(onToggleLinked !== undefined || switching) && (
        <div className="verify-panels__toolbar">
          {switching && (
            <div
              className="verify-panels__switch"
              role="group"
              aria-label="Which pane is the stage"
            >
              {PANE_ORDER.map((pane, index) => (
                <button
                  key={pane}
                  type="button"
                  data-role="pane-switch"
                  data-pane={pane}
                  aria-pressed={maximizedId === pane}
                  className={`button button--ghost button--small${
                    maximizedId === pane ? " button--active" : ""
                  }`}
                  title={
                    maximizedId === pane
                      ? `${PANE_TITLES[pane]} — back to all three panels`
                      : `Show ${PANE_TITLES[pane]} on the whole stage`
                  }
                  onClick={() => onToggleMaximized?.(pane)}
                >
                  {index + 1}
                </button>
              ))}
            </div>
          )}
          {maximizedId !== null && onToggleMaximized !== undefined && (
            <button
              type="button"
              className="button button--ghost button--small"
              onClick={() => onToggleMaximized(maximizedId)}
            >
              ⤡ show all three
            </button>
          )}
          {onToggleLinked !== undefined && (
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
          )}
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
            title={PANE_TITLES.library}
            caption={libraryPaneCaption(variantLabel, systemLabel)}
            notice={notices.part}
            busy={partBusy}
            busyMessage="Loading the library part…"
            viewer={libraryViewer}
            hud={hudFor("library")}
            hint={hints.library ?? null}
            maximized={maximizedId === "library"}
            onToggleMaximized={maximizeFor("library")}
            onResetView={onResetView === null ? null : () => onResetView("library")}
          />
        )}
        {showPane("scan") && (
          <PaneShell
            role="pane-scan"
            title={PANE_TITLES.scan}
            caption={scanCaption}
            notice={notices.scan}
            busy={scanBusy}
            busyMessage="Loading the scan…"
            viewer={scanViewer}
            hud={hudFor("scan")}
            hint={hints.scan ?? null}
            maximized={maximizedId === "scan"}
            onToggleMaximized={maximizeFor("scan")}
            onResetView={onResetView === null ? null : () => onResetView("scan")}
          />
        )}
        {showPane("union") && (
          <PaneShell
            role="pane-union"
            title={PANE_TITLES.union}
            caption={unionCaption}
            notice={notices.union}
            busy={unionBusy}
            busyMessage={unionBusyMessage}
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
            invite={unionInvite}
            hint={hints.union ?? null}
            /* the colorbar owns this pane's bottom strip whenever a payload is on
               screen — the hint sits above it rather than under it */
            hintRaised={payload !== null}
            maximized={maximizedId === "union"}
            onToggleMaximized={maximizeFor("union")}
            onResetView={onResetView === null ? null : () => onResetView("union")}
          />
        )}
      </div>
      {footer}
    </div>
  );
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

export interface SitePaneScene {
  /** Per-pane re-frame requests + the act that bumps one — the panes' way home
   *  (client 2026-07-29). The hook threads the nonces into the viewers it builds;
   *  callers only ever hand `onResetView` to the view's reset control. */
  readonly resetNonce: Readonly<Record<PaneId, number>>;
  readonly onResetView: (pane: PaneId) => void;
  readonly partBusy: boolean;
  readonly scanBusy: boolean;
  readonly partError: string | null;
  readonly scanError: string | null;
  readonly partMeshKnown: boolean;
  readonly scanEmpty: boolean;
  readonly scanCaption: string | null;
  readonly layers: PaneLayers;
  readonly onToggleLayer: (pane: PaneId, layerId: string) => void;
  readonly onChangeOpacity: (pane: PaneId, layerId: string, opacity: number) => void;
  readonly linked: boolean;
  readonly onToggleLinked: () => void;
  readonly maximizedId: PaneId | null;
  readonly onToggleMaximized: (pane: PaneId) => void;
  readonly scaleId: DeviationScaleId;
  readonly onSelectScale: (id: DeviationScaleId) => void;
  readonly libraryViewer: ReactNode;
  readonly scanViewer: ReactNode;
  readonly unionViewer: ReactNode;
}

/**
 * THE PANES' GEOMETRY AND CHROME, once (extracted in slice 6): the case's scan fetched
 * and parsed per case, the declared part's mesh per variant, the site crop, the two
 * camera frames, the layer/opacity state and the three VerifyViewers.
 *
 * The union PAYLOAD is a parameter, not a fetch: Declare seats a pre-run preview and
 * Adjust reads the shipped pose, and this hook has no business knowing which. The
 * memo discipline is the demo's — derive once per input, so an unrelated re-render
 * never re-uploads a mesh to the GPU.
 */
export type PanePick = (point: [number, number, number]) => void;

/** What a stage may add ON TOP of the shared scene. Declare passes nothing; Adjust
 * arms picking and draws the numbered marks the fit-by-points flow collects.
 * `markers` must be a STABLE identity per content (the viewer diffs by reference) —
 * the caller memoizes, exactly as it does for geometry. */
export interface SitePaneSceneOptions {
  readonly markers?: Partial<Record<PaneId, readonly VerifyMarker[]>>;
  readonly onPick?: Partial<Record<PaneId, PanePick | null>>;
  /**
   * WHICH PANES ARE WAITING FOR A CLICK — the crosshair cursor (client 2026-07-30).
   *
   * Separate from `onPick` on purpose: Adjust installs one pick router on all three
   * panes for the whole stage and decides INSIDE it whether the click means anything, so
   * "has a listener" and "wants a click" are different facts. Reading the cursor off the
   * listener would arm all three panes for the entire stage, which is exactly the lie
   * this control exists to stop telling. Omitted, no pane claims to be armed.
   */
  readonly armed?: Partial<Record<PaneId, boolean>>;
}

export function useSitePaneScene(
  detail: CaseSessionDetail,
  site: SiteView | null,
  payload: SitePreviewPayload | null,
  options: SitePaneSceneOptions = {},
): SitePaneScene {
  const caseId = detail.case.id;
  const linkGroupRef = useRef(new OrbitLinkGroup());

  const [scanPositions, setScanPositions] = useState<Float32Array | null>(null);
  const [scanBusy, setScanBusy] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);

  const [partPositions, setPartPositions] = useState<Float32Array | null>(null);
  const [partBusy, setPartBusy] = useState(false);
  const [partError, setPartError] = useState<string | null>(null);

  const [linked, setLinked] = useState(false);
  const [maximizedId, setMaximizedId] = useState<PaneId | null>(null);
  const [scaleId, setScaleId] = useState<DeviationScaleId>("signed");
  /* PER-PANE, deliberately: resetting the union's view must not yank the library pane's
     orbit back with it. Each counter is its own re-frame request. */
  const [resetNonce, setResetNonce] = useState<Readonly<Record<PaneId, number>>>({
    library: 0,
    scan: 0,
    union: 0,
  });
  const onResetView = useCallback((pane: PaneId) => {
    setResetNonce((now) => ({ ...now, [pane]: now[pane] + 1 }));
  }, []);
  useEffect(() => {
    linkGroupRef.current.setEnabled(linked);
  }, [linked]);
  const onToggleLinked = useCallback(() => setLinked((now) => !now), []);
  const onToggleMaximized = useCallback((pane: PaneId) => {
    setMaximizedId((now) => (now === pane ? null : pane));
  }, []);

  const [layerToggles, setLayerToggles] =
    useState<Readonly<Record<string, LayerToggle>>>(LAYER_DEFAULTS);
  const toggleOf = (pane: PaneId, layerId: string): LayerToggle =>
    layerToggles[`${pane}:${layerId}`] ??
    LAYER_DEFAULTS[`${pane}:${layerId}`] ?? { visible: true, opacity: 1 };
  const onToggleLayer = useCallback((pane: PaneId, layerId: string) => {
    setLayerToggles((current) => {
      const key = `${pane}:${layerId}`;
      const now = current[key] ?? LAYER_DEFAULTS[key] ?? { visible: true, opacity: 1 };
      return { ...current, [key]: { ...now, visible: !now.visible } };
    });
  }, []);
  const onChangeOpacity = useCallback(
    (pane: PaneId, layerId: string, opacity: number) => {
      setLayerToggles((current) => {
        const key = `${pane}:${layerId}`;
        const now = current[key] ?? LAYER_DEFAULTS[key] ?? { visible: true, opacity: 1 };
        return { ...current, [key]: { ...now, opacity } };
      });
    },
    [],
  );

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

  const partFrame = useMemo(
    () =>
      partCameraFrame(
        partPositions !== null ? computePartFrame(partPositions) : null,
      ),
    [partPositions],
  );

  const occlusal = useMemo(() => {
    if (scanPositions === null) return null;
    return (computeAnatomyFrame(scanPositions)?.occlusal ?? null) as Vec3 | null;
  }, [scanPositions]);
  const siteFrame = siteFrameFor(siteCenter, payload?.pose ?? null, occlusal,
                                 CAP_REGION_RADIUS_MM);

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
        label: "deviation",
        swatch: null,
        ...toggleOf("union", "deviation"),
        available: deviationGeometry !== null,
      },
    ],
  };

  const linkGroup = linkGroupRef.current;
  return {
    partBusy,
    scanBusy,
    partError,
    scanError,
    partMeshKnown: partMeshUrl !== null,
    scanEmpty: scanCrop !== null && scanCrop.length === 0,
    scanCaption:
      scanCrop !== null && scanCrop.length > 0
        ? scanPaneCaption(site?.tooth ?? null, triangleCount(scanCrop), CAP_REGION_RADIUS_MM)
        : null,
    layers,
    onToggleLayer,
    onChangeOpacity,
    linked,
    onToggleLinked,
    maximizedId,
    onToggleMaximized,
    scaleId,
    onSelectScale: setScaleId,
    resetNonce,
    onResetView,
    libraryViewer: (
      <VerifyViewer
        frameNonce={resetNonce.library}
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
        markers={options.markers?.library}
        onPick={options.onPick?.library ?? null}
        armed={options.armed?.library ?? false}
        ariaLabel="The declared library part"
      />
    ),
    scanViewer: (
      <VerifyViewer
        frameNonce={resetNonce.scan}
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
        markers={options.markers?.scan}
        onPick={options.onPick?.scan ?? null}
        armed={options.armed?.scan ?? false}
        ariaLabel="The scanned cap region"
      />
    ),
    unionViewer: (
      <VerifyViewer
        frameNonce={resetNonce.union}
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
        markers={options.markers?.union}
        onPick={options.onPick?.union ?? null}
        armed={options.armed?.union ?? false}
        ariaLabel="The scan and the previewed cap overlaid, coloured by deviation"
      />
    ),
  };
}
