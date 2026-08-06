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
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MutableRefObject,
  type ReactNode,
} from "react";
import {
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
  paneAxisLabel,
  paneScaleBar,
  scanPositionsFor,
  triangleCount,
  type DeviationScaleId,
  type PaneScaleBar,
  type PaneViewReadout,
  type Vec3,
  type VerifyLayerGeometry,
  type VerifyMarker,
} from "viewer";
import {
  scanUrlFor,
  type CaseSessionDetail,
  type PreviewPose,
  type SitePreviewPayload,
  type SiteView,
} from "../api/client";
import {
  indicesFrom,
  partCameraFrame,
  scanPaneRadiusMm,
  positionsFrom,
  presetFraming,
  siteFrameFor,
  type ViewPresetId,
  variantMeshUrl,
} from "../domain/declare";
import { paneLinkLabel } from "../domain/workspace";

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
  chrome = "full",
}: {
  readonly payload: SitePreviewPayload;
  readonly scaleId?: DeviationScaleId;
  readonly onSelectScale?: (id: DeviationScaleId) => void;
  /** A tiny stage sheds the CHOOSER; it may not shed the ramp's identity — see below. */
  readonly chrome?: PaneChrome;
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
        {/* THE COMP'S RESTING STRIP (read directly 2026-08-02): the thin ramp and ONE
            summary line — "▸ signed ±0.25 mm · legend & stats" — nothing else. Ours
            stacked the two scale pills and a tick row above the fold and the union
            pane paid four rows of chrome for it. The ramp keeps its identity at every
            size because the scale's NAME now lives in the always-visible summary line
            (the 2026-07-31 review's rule, satisfied harder than before); the chooser
            pills and the tick numbers are controls and small print, and they fold. */}
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
        <details className="verify-colorbar__detail">
          <summary className="verify-colorbar__summary">
            <span data-role="colorbar-scale-name" className="verify-colorbar__scalename">
              {contacts
                ? `contacts 0.00–${CONTACTS_MAX_MM.toFixed(2)} mm`
                : `signed ±${clampMm.toFixed(2)} mm`}
            </span>{" "}
            · legend &amp; stats
          </summary>
          {chrome !== "tiny" && onSelectScale !== undefined && (
            <ScaleSelector scaleId={scaleId} onSelectScale={onSelectScale} />
          )}
          <div className="verify-colorbar__ticks">
            {ticks.map((label) => (
              <span key={label}>{label}</span>
            ))}
          </div>
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

/* ==========================================================================================
 * THE MEASURED LAYOUT (client direction 2026-07-31, gaps measured-pane-layout-and-solo-
 * fallback + tiny-stage-chrome-steps-aside).
 *
 * Nothing in this app had ever measured itself: the pane sizes were CSS arithmetic in a
 * comment, and that comment computed for ONE row of three while the ≤1600px rule has been
 * producing TWO rows since the Adjust slice. Measured in the running app, Declare stage,
 * on the .verify-panels__grid box:
 *
 *   1280x800 — grid 563px → panes 394x276 → stage 221px, which is min-height:220px
 *              OVERFLOWING its row by ~6px and being clipped by .verify-panel's overflow:hidden
 *   1280x720 — grid 497px → panes 394x243 → stage clipped by 38px
 *   1280x620 — grid 397px → panes 394x220 → stage clipped by 61px
 *
 * and on that stage the chrome measures: layer HUD 59px (the union's two rows) + colorbar
 * strip 76px = 135px, i.e. 61% OF THE 1280x800 STAGE sitting on the cap being judged.
 *
 * So there are two different failures and they need two different answers:
 *
 *   - below a stage that can hold a cap at all, three panes are three unusable panes. One
 *     pane at the whole height, with the 1/2/3 switcher that already exists, is strictly
 *     better — the SOLO FALLBACK.
 *   - above that but still short, the geometry is fine and only the chrome is wrong. It
 *     steps aside: compact metrics first, then the layer HUD leaves the glass for a header
 *     toggle. Nothing is REMOVED at any size — every control stays reachable.
 * ========================================================================================== */

/** What the pane box costs its stage: 8px padding top, a two-line header, the 6px gap and
 *  8px padding bottom. MEASURED (pane 276px → stage top offset 53px → 61px of chrome), not
 *  computed from the stylesheet — the stylesheet's own arithmetic was stale. */
export const PANE_STAGE_CHROME_PX = 61;

/** .verify-panels__grid's gap. */
export const PANE_GRID_GAP_PX = 12;

/** Below this a stage cannot show a cap AND its chrome, so the layout stops trying to show
 *  three of them. 170px is the point at which the measured chrome bands (a HUD row, the
 *  colorbar strip) leave nothing for the geometry; it is also below .verify-panel__stage's
 *  own floor, so reaching it always means panes were already being clipped. */
export const SOLO_FALLBACK_STAGE_PX = 170;

/** Below this the chrome shrinks (1280x800 lands here — 214px of stage under 135px of HUD
 *  and colorbar). */
export const COMPACT_STAGE_PX = 260;

/** Below this the layer HUD stops defending its own floor on top of the cap and moves
 *  behind a header toggle (1280x720 lands here). */
export const TINY_STAGE_PX = 190;

/** How much room the chrome may take on this stage. Never a capability difference — a
 *  "tiny" pane still offers every control, one click further away. */
export type PaneChrome = "full" | "compact" | "tiny";

/** What the panes measure about themselves. `viewportW` and not the grid's own width
 *  because the column count is decided by MEDIA queries, which key off the viewport. */
export interface PaneStageMetrics {
  readonly availH: number;
  readonly viewportW: number;
}

export interface PaneLayoutPlan {
  /** false until the first observation — and an unmeasured plan is exactly today's layout,
   *  so a surface that never measures (every static test) renders unchanged. */
  readonly measured: boolean;
  readonly columns: 1 | 2 | 3;
  readonly rows: 1 | 2 | 3;
  /** The height .verify-panel__stage will actually get, in px. */
  readonly stageH: number;
  /** The multi-pane layout cannot carry a usable stage — show one pane at full height. */
  readonly solo: boolean;
  /**
   * THE SAME ARITHMETIC WITHOUT THE MAXIMIZE (design review 2026-07-31): could the
   * multi-pane layout carry a stage if nothing were maximized?
   *
   * `solo` cannot answer that — it is forced false whenever `maximized` is true, which
   * made the guard `maximizedId !== null && !plan.solo` dead code and put "⤡ show all
   * three" on a stage that answers it with one pane and "too short for three panes".
   * Any control promising the three-pane layout must ask THIS instead.
   */
  readonly soloIfUnmaximized: boolean;
  readonly chrome: PaneChrome;
}

export const UNMEASURED_PANE_LAYOUT: PaneLayoutPlan = {
  measured: false,
  columns: 3,
  rows: 1,
  stageH: 0,
  solo: false,
  soloIfUnmaximized: false,
  chrome: "full",
};

/**
 * How many panes sit across, MIRRORING styles.css: `@media (max-width: 1600px)` puts the
 * grid on two columns (:3273) and `@media (max-width: 1180px)` collapses the whole shell
 * (:2782). Duplicated here on purpose and pinned by a test: the height half of the layout
 * cannot be computed without knowing the column count, and reading it back off the computed
 * style would be circular — the solo fallback itself rewrites the grid's columns.
 */
export function paneColumns(viewportW: number): 1 | 2 | 3 {
  /* THE TWO-ACROSS TIER IS DEAD (client 2026-08-02: "the second scroll section …
     hides the 3 vertical panels view side by side"). It existed on the guess that
     three-across is slivers at 1440 — but two-up ALWAYS wraps the union pane to a
     second row, and a second row is a scroll at every height this app runs at, so
     the tier hid the verdict pane to protect the width of its inputs. Three across
     everywhere the split workbench exists; below 1180 the shell itself stacks. */
  if (viewportW <= 1180) return 1;
  return 3;
}

/**
 * The whole layout decision, as one pure function of what was measured.
 *
 * THE SOLO FALLBACK IS DEAD (client 2026-08-01, the day it shipped: "The 3 views of
 * the declare disappears i never said that i wanted independent views the idea is to
 * see everything at once"). It was the design prototype's rule — below a threshold,
 * hide two panes and offer a 1/2/3 switcher — and the client rejected it on sight.
 * The rule is now the client's: the layout may shrink panes and step chrome aside
 * (the compact/tiny ladder below), but NOTHING short of the operator's own maximize
 * ever shows fewer than three panes. Three small panes, honestly small, beat two
 * hidden ones. `solo`/`soloIfUnmaximized` stay in the plan's shape as permanent
 * falses so the callers keep one contract; if a future direction revives a fallback
 * it must arrive as the client's ask, not a measured guess.
 */
export function planPaneLayout(metrics: PaneStageMetrics, maximized: boolean): PaneLayoutPlan {
  const { availH, viewportW } = metrics;
  if (!(availH > 0)) return UNMEASURED_PANE_LAYOUT;
  const columns = paneColumns(viewportW);
  // 1 column stacks all three panes; 3 columns is ONE row — which is what makes the
  // grid scroll-free: multiRowH degenerates to availH and every pane is on screen.
  const rows: 1 | 2 | 3 = columns === 1 ? 3 : 1;
  const multiRowH = Math.floor((availH - PANE_GRID_GAP_PX * (rows - 1)) / rows);
  const multiStageH = multiRowH - PANE_STAGE_CHROME_PX;
  const stageH = maximized ? availH - PANE_STAGE_CHROME_PX : multiStageH;
  const chrome: PaneChrome =
    stageH < TINY_STAGE_PX ? "tiny" : stageH < COMPACT_STAGE_PX ? "compact" : "full";
  return { measured: true, columns, rows, stageH, solo: false, soloIfUnmaximized: false, chrome };
}

/** Measure the grid the panes live in. A ResizeObserver rather than a window listener alone
 *  because the grid's height moves when the arch strip folds, which no resize event reports. */
function usePaneLayoutPlan(maximized: boolean): {
  readonly gridRef: MutableRefObject<HTMLDivElement | null>;
  readonly plan: PaneLayoutPlan;
} {
  const gridRef = useRef<HTMLDivElement | null>(null);
  const [metrics, setMetrics] = useState<PaneStageMetrics>({ availH: 0, viewportW: 0 });
  useEffect(() => {
    const grid = gridRef.current;
    if (grid === null || typeof ResizeObserver === "undefined") return undefined;
    /* MEASURE OUTSIDE THE UPDATER. Reading layout inside a setState updater put the plan a
       whole resize behind the DOM (seen live 2026-07-31: a 477px grid still wearing the
       plan for 577px, and the solo fallback only arriving on the NEXT resize) — React may
       run an updater at a moment of its own choosing, and a DOM read there is not the read
       the observer was reporting. */
    const read = () => {
      const availH = Math.round(grid.getBoundingClientRect().height);
      const viewportW = window.innerWidth;
      setMetrics((now) =>
        // Ignore sub-pixel churn: a re-render per scrollbar rounding is a re-render for nothing.
        Math.abs(now.availH - availH) < 2 && now.viewportW === viewportW
          ? now
          : { availH, viewportW },
      );
    };
    read();
    const observer = new ResizeObserver(read);
    observer.observe(grid);
    window.addEventListener("resize", read);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", read);
    };
  }, []);
  return { gridRef, plan: planPaneLayout(metrics, maximized) };
}

/**
 * THE FOOTER BAND: how big the thing on screen is, and where the camera is looking from.
 *
 * The axis half is where the design prototype had to be overruled. It prints a fixed
 * `st.view.toUpperCase()` — "OCCLUSAL" — on panes 2 and 3, but those panes frame down the
 * seated pose axis ONCE and then orbit freely, so that caption starts lying on the operator's
 * first drag. `axis` here is a live reading against the axis the pane framed on (see
 * viewer/paneReadout.paneAxisLabel): "down the seated pose axis" while it is, "37° off the
 * seated pose axis" once it is not.
 *
 * The bar half is likewise a measurement, not a decoration: a perspective camera's
 * millimetres-per-pixel changes with every dolly, so it comes from the live scene and the
 * pane ships NO bar rather than a stale one when no round step reads.
 */
export function PaneFoot({
  axis,
  bar,
  raised = false,
}: {
  readonly axis: string | null;
  readonly bar: PaneScaleBar | null;
  /** The union pane's bottom strip belongs to the colorbar — sit above it, like the hint. */
  readonly raised?: boolean;
}) {
  if (axis === null && bar === null) return null;
  return (
    <div
      data-role="pane-foot"
      className={`verify-panel__foot${raised ? " verify-panel__foot--raised" : ""}`}
    >
      {axis !== null ? (
        <span data-role="pane-axis" className="verify-panel__foot-axis">
          {axis}
        </span>
      ) : (
        <span />
      )}
      {bar !== null && (
        <span
          data-role="pane-scale"
          className="verify-panel__foot-scale"
          title="at the focus plane — a perspective camera measures larger nearer to it"
        >
          <span className="verify-panel__foot-bar" style={{ width: `${bar.px}px` }} />
          {bar.label}
        </span>
      )}
    </div>
  );
}

/**
 * WHICH AXIS PANES 2/3 FRAMED ON, in the operator's words — the same rule
 * domain/declare.siteFrameFor uses to pick one, so the label can never name an axis the
 * camera was not pointed down. The distinction is the demo's honesty story: the occlusal
 * proxy sat 6.2°-42.0° off the real axis across the fleet, the pose is exact by construction.
 */
export function siteAxisLabel(pose: PreviewPose | null): string {
  return pose !== null && pose.axis.length === 3 ? "the seated pose axis" : "the occlusal proxy";
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
  /** How much room this stage can spare its chrome — see the measured-layout block above. */
  readonly chrome?: PaneChrome;
  /** false parks the layer HUD behind the header toggle (only ever on a tiny stage). */
  readonly showHud?: boolean;
  /** Offered only when the HUD is parked AND this pane has layers worth un-parking. */
  readonly onToggleHud?: (() => void) | null;
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
  chrome = "full",
  showHud = true,
  onToggleHud = null,
}: PaneShellProps) {
  return (
    <section data-role={role} aria-label={title} className="verify-panel">
      <header className="verify-panel__header">
        <div className="verify-panel__heading">
          <h4 className="verify-panel__title">{title}</h4>
          {onToggleHud !== null && (
            /* THE PARKED HUD'S WAY BACK. On a stage this short the layer rows and the
               colorbar together covered 61% of the cap (measured 2026-07-31 at 1280x800),
               so the rows step off the glass — but nothing is removed: this is the same
               controls, one click away, and it is in the header because the glass is
               precisely what has run out. */
            <button
              type="button"
              data-role="pane-hud-toggle"
              className="verify-panel__hudtoggle"
              aria-pressed={showHud}
              aria-label={showHud ? `Hide the layers of ${title}` : `Show the layers of ${title}`}
              title={showHud ? "Hide the layer controls" : "Show the layer controls"}
              onClick={onToggleHud}
            >
              {showHud ? "◧" : "◫"}
            </button>
          )}
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
      <div
        className={`verify-panel__stage${
          chrome === "full" ? "" : ` verify-panel__stage--${chrome}`
        }`}
      >
        {viewer}
        {/* `hud` is already the parked/unparked answer — the colorbar is NOT parked with the
            layer rows: it is the union pane's verdict legend, not a control panel. */}
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
  /** The measured layout. Omitted, the view measures its own grid; a node test injects one
   *  so every window size this app has to survive is renderable without a browser. */
  readonly layoutPlan?: PaneLayoutPlan;
  /** Which pane becomes the stage when the window cannot carry three. Pane 2 by default:
   *  it is the one pane that always has geometry on BOTH stages (pane 1 waits on a
   *  declaration, pane 3 on a payload), so the fallback never lands on an empty pane. */
  readonly soloPane?: PaneId;
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
  layoutPlan,
  soloPane = "scan",
}: SitePanesViewProps) {
  const measured = usePaneLayoutPlan(maximizedId !== null);
  const plan = layoutPlan ?? measured.plan;
  /* THE SOLO FALLBACK. Below a stage that can hold a cap at all, three panes are three
     unusable panes; one pane at the whole height plus the 1/2/3 switcher is strictly more
     of the product. An explicit maximize always wins over the fallback. */
  const stageId: PaneId | null = maximizedId ?? (plan.solo ? soloPane : null);
  /* The layer rows leave the glass only where the glass has run out, and only where there
     are rows to park: a pane with no layers gets no toggle for nothing. */
  const [hudOpen, setHudOpen] = useState(false);
  const parked = plan.chrome === "tiny" && !hudOpen;
  const hasLayers = (pane: PaneId): boolean =>
    layers !== undefined && layers[pane].length > 0;
  const hudFor = (pane: PaneId): ReactNode =>
    hasLayers(pane) && !parked ? (
      <LayerHud
        pane={pane}
        layers={layers![pane]}
        onToggleLayer={onToggleLayer}
        onChangeOpacity={onChangeOpacity}
      />
    ) : null;
  const hudToggleFor = (pane: PaneId): (() => void) | null =>
    plan.chrome === "tiny" && hasLayers(pane) ? () => setHudOpen((now) => !now) : null;
  /** Maximised, the other two panes are UNMOUNTED, not hidden (the demo's rule). */
  const showPane = (pane: PaneId): boolean => stageId === null || stageId === pane;
  const maximizeFor = (pane: PaneId): (() => void) | null =>
    onToggleMaximized !== undefined ? () => onToggleMaximized(pane) : null;
  /* THE SWITCHER (client 2026-07-30). Maximizing was built; MOVING was not — going from
     a maximized pane 1 to a maximized pane 3 meant un-maximize, hunt for the other
     pane's ⤢, re-maximize. onToggleMaximized already switches directly when handed a
     different pane, so the whole fix is three buttons on the existing setter. It shows
     only while a pane IS the stage: with all three on screen there is nothing to
     switch between. */
  const switching = stageId !== null && onToggleMaximized !== undefined;
  return (
    <div data-role="declare-panes" className="verify-panels">
      {(onToggleLinked !== undefined || switching) && (
        <div className="verify-panels__toolbar">
          {plan.solo && maximizedId === null && (
            /* SAY WHY only one pane is on screen. A surface that silently drops two of the
               three panes it is named for reads as a bug, not as a fallback. */
            <p data-role="pane-solo-note" className="verify-panels__note">
              too short for three panes — one at a time
            </p>
          )}
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
                  aria-pressed={stageId === pane}
                  className={`button button--ghost button--small${
                    stageId === pane ? " button--active" : ""
                  }`}
                  title={
                    stageId !== pane
                      ? `Show ${PANE_TITLES[pane]} on the whole stage`
                      : plan.soloIfUnmaximized
                        ? /* The tooltip used to promise "back to all three panels" while
                             the note beside it said "too short for three panes" — one
                             control, two contradictory sentences (design review
                             2026-07-31). */
                          `${PANE_TITLES[pane]} — the stage is too short for three panes`
                        : `${PANE_TITLES[pane]} — back to all three panels`
                  }
                  onClick={() => onToggleMaximized?.(pane)}
                >
                  {index + 1}
                </button>
              ))}
            </div>
          )}
          {/* Not offered while the stage could not carry all three ANYWAY: there is no
              all-three to go back to, and a control that cannot do what it says is worse
              than no control. Judged on `soloIfUnmaximized` — `!plan.solo` was dead code
              here, since planPaneLayout forces solo=false whenever a pane is maximized
              (design review 2026-07-31). */}
          {maximizedId !== null && !plan.soloIfUnmaximized && onToggleMaximized !== undefined && (
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
              disabled={stageId !== null}
              onClick={onToggleLinked}
              title={
                stageId !== null
                  ? "Linking needs more than one panel on screen"
                  : "Rotate all three panels together (same angles and zoom, each around its own content)"
              }
            >
              {paneLinkLabel(linked)}
            </button>
          )}
        </div>
      )}
      <div
        ref={measured.gridRef}
        className={`verify-panels__grid${
          stageId !== null ? " verify-panels__grid--maximized" : ""
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
            chrome={plan.chrome}
            showHud={!parked}
            onToggleHud={hudToggleFor("library")}
            maximized={stageId === "library"}
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
            chrome={plan.chrome}
            showHud={!parked}
            onToggleHud={hudToggleFor("scan")}
            maximized={stageId === "scan"}
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
                    chrome={plan.chrome}
                  />
                )}
              </>
            }
            invite={unionInvite}
            hint={hints.union ?? null}
            /* the colorbar owns this pane's bottom strip whenever a payload is on
               screen — the hint sits above it rather than under it */
            hintRaised={payload !== null}
            chrome={plan.chrome}
            showHud={!parked}
            onToggleHud={hudToggleFor("union")}
            maximized={stageId === "union"}
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
  /**
   * THE NAMED VIEWPOINT the workspace toolbar is asking all three panes to take
   * (gap `named-view-presets`, 2026-07-31). Applied to whatever frame each pane
   * already computed, so every pane keeps its own centre and radius and only the
   * direction moves — which is what makes one click mean the same thing in three
   * panes. Omitted or "occlusal" leaves every frame exactly as it was, so a caller
   * that does not offer the control pays nothing.
   */
  readonly viewPreset?: ViewPresetId;
  /**
   * A VIEWPOINT MUST BE RETURNABLE TO (design review 2026-07-31).
   *
   * The preset button latched as selected, but re-clicking it produced the same
   * `frameKey`, which VerifyViewer's `framedRef` guard short-circuits — so after any
   * orbit the toolbar claimed a viewpoint the cameras had left and its own control was
   * inert. The whole stated rationale for naming a direction is "a viewpoint the
   * operator can RETURN to" (domain/declare.presetFraming's note), which that does not
   * meet. The stage bumps this on EVERY preset click, re-selection included; it rides
   * with each pane's own reset nonce, so either act re-frames and neither cancels the
   * other.
   */
  readonly viewPresetNonce?: number;
  /** THE WORKSPACE'S SHARED ZOOM COUNTER, handed to all three panes unchanged. One
   *  number, not three: the panes are read side by side and a zoom that reached only
   *  one of them would make that comparison lie about scale (client 2026-08-02). */
  readonly zoomLevel?: number;
  /** CONTROLLED LINK STATE (client 2026-08-02, the three-rows complaint). When the
   *  stage owns the toggle — it lives in the workspace toolbar now, beside the zoom
   *  it is kin to — the hook takes the value and keeps only the OrbitLinkGroup
   *  plumbing. Omitted, the hook's own state stands (the older callers and tests). */
  readonly linked?: boolean;
  /** THE HELD POSE (domain/declare.poseHeldBy — client 2026-08-05: "touching the
   *  variant tooth buttons put the middle panel camera to the back of the scan").
   *  While a re-preview computes, `payload` is null and panes 2/3 would demote to
   *  the occlusal proxy; a caller that still holds the last measured pose passes it
   *  here and the camera keeps the seated axis it earned. */
  readonly heldPose?: PreviewPose | null;
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

  const [internalLinked, setLinked] = useState(false);
  // controlled when the stage owns the toggle (see SitePaneSceneOptions.linked)
  const linked = options.linked ?? internalLinked;
  const [maximizedId, setMaximizedId] = useState<PaneId | null>(null);
  const [scaleId, setScaleId] = useState<DeviationScaleId>("signed");
  /* PER-PANE while UNLINKED (resetting the union's view must not yank the library
     pane's orbit back with it) — and ALL THREE while LINKED (client 2026-08-04:
     "Back to the pane's own view doesn't move all 3 panes"). Linked panes are one
     camera in three suits: the mirror works on orbit DELTAS, so resetting one pane
     alone would desynchronize exactly the shared basis the link promises, and the
     next drag would mirror from disagreeing starting points. */
  const [resetNonce, setResetNonce] = useState<Readonly<Record<PaneId, number>>>({
    library: 0,
    scan: 0,
    union: 0,
  });
  const linkedRef = useRef(false);
  const onResetView = useCallback((pane: PaneId) => {
    setResetNonce((now) =>
      linkedRef.current
        ? { library: now.library + 1, scan: now.scan + 1, union: now.union + 1 }
        : { ...now, [pane]: now[pane] + 1 },
    );
  }, []);
  useEffect(() => {
    linkGroupRef.current.setEnabled(linked);
    linkedRef.current = linked;
  }, [linked]);
  const onToggleLinked = useCallback(() => setLinked((now) => !now), []);
  const onToggleMaximized = useCallback((pane: PaneId) => {
    setMaximizedId((now) => (now === pane ? null : pane));
  }, []);

  /* THE FOOTER BAND'S FEED (gap pane-footer-scale-bar-and-axis-label). One reading per pane,
     pushed by that pane's own scene whenever its camera moves — the scene gates the stream
     (viewReadoutChanged) so a damped flick is a handful of updates, not sixty. The callbacks
     are memoized because an unstable identity re-subscribes, and subscribing emits. */
  const [readouts, setReadouts] = useState<Readonly<Record<PaneId, PaneViewReadout | null>>>({
    library: null,
    scan: null,
    union: null,
  });
  const onLibraryView = useCallback(
    (r: PaneViewReadout) => setReadouts((now) => ({ ...now, library: r })),
    [],
  );
  const onScanView = useCallback(
    (r: PaneViewReadout) => setReadouts((now) => ({ ...now, scan: r })),
    [],
  );
  const onUnionView = useCallback(
    (r: PaneViewReadout) => setReadouts((now) => ({ ...now, union: r })),
    [],
  );

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

  // PANE 2's CAP-TIGHT BAND (§10-AE.2, keyed to the DECLARED cap since the client's
  // 2026-08-04 second tightening): display only — the crop, the frame and the
  // caption all read this ONE number so the pane can never claim a band it is not
  // drawing.
  const scanRadiusMm = scanPaneRadiusMm(detail, site?.declared_variant ?? null);

  const scanCrop = useMemo(() => {
    if (scanPositions === null || siteCenter === null) return null;
    return cropTrianglesNear(scanPositions, siteCenter, scanRadiusMm);
  }, [scanPositions, siteCenter, scanRadiusMm]);

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

  /* THE PRESET IS A ROTATION OF THE FRAME EACH PANE ALREADY HAS, never a frame of
     its own — see domain/declare.presetFraming. It cannot apply where the roll is
     unmeasured (pre-preview, panes 2/3 frame down the jaw's occlusal PROXY with no
     clock reference), and the pane then keeps its own framing rather than dropping to
     nothing — WITH its own axis label, which is the half that used to go missing:
     reference and label came from different frames, so a side-on pane read "down the
     seated pose axis" at exactly 90° off it (design review 2026-07-31). */
  const viewPreset = options.viewPreset ?? "occlusal";
  const partFraming = useMemo(() => {
    const base = partCameraFrame(
      partPositions !== null ? computePartFrame(partPositions) : null,
    );
    return presetFraming(base, viewPreset);
  }, [partPositions, viewPreset]);
  const partFrame = partFraming.frame;

  const occlusal = useMemo(() => {
    if (scanPositions === null) return null;
    return (computeAnatomyFrame(scanPositions)?.occlusal ?? null) as Vec3 | null;
  }, [scanPositions]);
  /* ONE pose for frame AND axis label (the 1375 rule extended): the payload's own,
     else the held one — never the proxy while a measured axis is still in hand. */
  const posePresented = payload?.pose ?? options.heldPose ?? null;
  const siteFrameBase = siteFrameFor(siteCenter, posePresented, occlusal,
                                     scanRadiusMm);
  const siteFraming = presetFraming(siteFrameBase, viewPreset);
  const siteFrame = siteFraming.frame;

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

  /* THE FOOTER BAND, PER PANE. It rides inside the viewer node rather than being a prop of
     the view: the band is a reading of THIS pane's camera, so it belongs with the canvas it
     reads — and that way both stages get it from the one place that builds the canvases,
     instead of each stage having to remember to thread a readout through. */
  /* NAME THE DIRECTION THE PANE IS ACTUALLY ON. Under a preset that applied, that is
     the preset's own viewpoint; otherwise it is the pane's own axis. The two can never
     be sourced separately again — presetFraming returns them together. */
  const siteAxis = siteFraming.presetLabel ?? siteAxisLabel(posePresented);
  const partAxis = partFraming.presetLabel ?? "the part's own axis";
  const footFor = (
    pane: PaneId,
    reference: readonly [number, number, number] | null,
    label: string,
    hasGeometry: boolean,
    raised = false,
  ): ReactNode => {
    if (!hasGeometry) return null;
    const readout = readouts[pane];
    return (
      <PaneFoot
        axis={paneAxisLabel(readout, reference, label)}
        bar={readout === null ? null : paneScaleBar(readout.mmPerPixel)}
        raised={raised}
      />
    );
  };

  /* Either act is a request to re-frame this pane, and VerifyViewer folds this number
     into its frame key — so a re-selected preset re-frames (which is what makes a named
     viewpoint returnable to) without cancelling a per-pane ⌖. */
  const presetNonce = options.viewPresetNonce ?? 0;
  const zoomLevel = options.zoomLevel ?? 0;
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
        ? scanPaneCaption(site?.tooth ?? null, triangleCount(scanCrop), scanRadiusMm)
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
      <>
      <VerifyViewer
        frameNonce={resetNonce.library + presetNonce}
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
        zoomLevel={zoomLevel}
        markers={options.markers?.library}
        onPick={options.onPick?.library ?? null}
        armed={options.armed?.library ?? false}
        onViewChange={onLibraryView}
        ariaLabel="The declared library part"
      />
      {footFor("library", partFrame?.viewDirection ?? null, partAxis,
               partGeometry !== null)}
      </>
    ),
    scanViewer: (
      <>
      <VerifyViewer
        frameNonce={resetNonce.scan + presetNonce}
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
        zoomLevel={zoomLevel}
        markers={options.markers?.scan}
        onPick={options.onPick?.scan ?? null}
        armed={options.armed?.scan ?? false}
        onViewChange={onScanView}
        ariaLabel="The scanned cap region"
      />
      {footFor("scan", siteFrame?.viewDirection ?? null, siteAxis, scanGeometry !== null)}
      </>
    ),
    unionViewer: (
      <>
      <VerifyViewer
        frameNonce={resetNonce.union + presetNonce}
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
        zoomLevel={zoomLevel}
        markers={options.markers?.union}
        onPick={options.onPick?.union ?? null}
        armed={options.armed?.union ?? false}
        onViewChange={onUnionView}
        ariaLabel="The scan and the previewed cap overlaid, coloured by deviation"
      />
      {/* raised whenever the colorbar owns this pane's bottom strip — the same rule the
          on-glass hint follows, for the same reason */}
      {footFor("union", siteFrame?.viewDirection ?? null, siteAxis,
               scanGeometry !== null || deviationGeometry !== null, payload !== null)}
      </>
    ),
  };
}
