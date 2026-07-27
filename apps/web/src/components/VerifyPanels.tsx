import type { ReactNode } from "react";
import type { DeviationScale, DeviationStats } from "../domain/types";
import {
  CONTACTS_MAX_MM,
  UNMEASURED_COLOR_HEX,
  clampNoteFor,
  contactsGradientCss,
  contactsTickLabels,
  deviationGradientCss,
  deviationTickLabels,
  type DeviationScaleId,
} from "../viewer/deviationColormap";
import { RotationDial, type RotationDialSpec } from "./RotationDial";

/** The client's three panes: the LIBRARY part, the SCANNED cap, and BOTH overlaid. */
export type VerifyPanelId = "library" | "scan" | "union";

/** One controllable layer inside a pane — the client's dialog puts an eye icon and an opacity
 *  slider on each. `swatch` is the CSS colour of the layer in 3D (null = the deviation ramp,
 *  which has its own colorbar instead of a single swatch). */
export interface VerifyLayerControl {
  readonly id: string;
  readonly label: string;
  readonly swatch: string | null;
  readonly visible: boolean;
  readonly opacity: number;
  /** False while the layer's geometry has not arrived (or cannot) — controls stay visible but
   *  disabled, so the pane's contents are never silently missing without a reason. */
  readonly available: boolean;
  readonly hint?: string;
}

export interface VerifyPanelSpec {
  readonly id: VerifyPanelId;
  readonly title: string;
  readonly caption: string;
  readonly layers: readonly VerifyLayerControl[];
  /** An honest state instead of an empty black canvas (loading, no run yet, nothing near the
   *  site, a failed fetch). null when the pane has something to show. */
  readonly notice: string | null;
  readonly busy: boolean;
  /** What the pane is busy DOING, when "loading…" would understate it — the pre-run preview is
   *  seconds of real alignment work, and a bare spinner reads as a stall. */
  readonly busyMessage?: string;
  /** The deviation scale + published stats — the union pane only. `scaleId` says WHICH colouring
   *  the mesh is currently wearing (our signed ±clamp, or the client's absolute Contacts bar);
   *  the pane offers both and the mesh follows the same id, so bar and surface never disagree. */
  readonly colorbar?: {
    readonly scale: DeviationScale;
    readonly stats: DeviationStats;
    readonly scaleId: DeviationScaleId;
    readonly onSelectScale: (id: DeviationScaleId) => void;
  } | null;
  /**
   * The operator rotation control, floated on this pane's 3D (client, 2026-07-26: rotation
   * "is kinda useless if it doesn't have a good view of what it does real time"). Union pane
   * only, and only once the site has a SHIPPED seat to rotate — a step re-emits the site's
   * package, which a pre-run preview has not produced yet.
   */
  readonly rotation?: RotationDialSpec | null;
}

export interface VerifyPanelsProps {
  readonly panels: readonly VerifyPanelSpec[];
  readonly onToggleLayer: (panelId: VerifyPanelId, layerId: string) => void;
  readonly onChangeOpacity: (panelId: VerifyPanelId, layerId: string, opacity: number) => void;
  readonly linked: boolean;
  readonly onToggleLinked: () => void;
  /**
   * The pane expanded to the whole stage, or null when all three share it (client, 2026-07-26:
   * "the 3D panels are the product — make them big", with a per-panel maximise). The other two
   * are UNMOUNTED while one is maximised, not merely hidden: three live WebGL contexts rendering
   * off-screen at every frame is exactly the cost this control exists to spend elsewhere.
   */
  readonly maximizedId?: VerifyPanelId | null;
  readonly onToggleMaximized?: (panelId: VerifyPanelId) => void;
  /** The live 3D pane for a panel. Omitted in static tests (and in any read-only embedding),
   *  which then render the pane's chrome and its notice with no canvas. */
  readonly renderViewer?: (panelId: VerifyPanelId) => ReactNode;
}

function OpacityPercent({ opacity }: { readonly opacity: number }) {
  return <span className="verify-layer__percent">{Math.round(opacity * 100)}%</span>;
}

/** The two scales the union pane offers, with the one-line difference stated on each — the
 *  selector is only honest if it says what changes, since both bars look plausible on a cap. */
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

/**
 * The colorbar under the union pane: the SAME ramp the mesh is coloured by (one source — see
 * deviationColormap), and the site's PUBLISHED RMS/p90 (the difference map's own numbers, never a
 * second read of the same site).
 *
 * TWO SCALES, selectable (client ask 2026-07-25): our SIGNED ±clamp RdBu — whose sign convention
 * the server states and this prints verbatim — and RealGUIDE's ABSOLUTE "Contacts" rainbow. Each
 * is labelled with what it shows; the signed one is the only one that carries direction, and the
 * legend says so on both, so switching bars can never quietly lose the proud/sunk distinction.
 */
function DeviationColorbar({
  scale,
  stats,
  scaleId,
  onSelectScale,
}: {
  readonly scale: DeviationScale;
  readonly stats: DeviationStats;
  readonly scaleId: DeviationScaleId;
  readonly onSelectScale: (id: DeviationScaleId) => void;
}) {
  const contacts = scaleId === "contacts";
  const clampNote = contacts ? null : clampNoteFor(scale.dataMinMm, scale.dataMaxMm, scale.clampMm);
  const ticks = contacts ? contactsTickLabels(CONTACTS_MAX_MM) : deviationTickLabels(scale.clampMm);
  return (
    <div className="verify-colorbar">
      <ScaleSelector scaleId={scaleId} onSelectScale={onSelectScale} />
      <div
        className="verify-colorbar__bar"
        style={{ background: contacts ? contactsGradientCss() : deviationGradientCss() }}
        role="img"
        aria-label={
          contacts
            ? `Contacts scale from 0 to ${CONTACTS_MAX_MM} millimetres, absolute distance`
            : `Deviation scale from -${scale.clampMm} to +${scale.clampMm} millimetres`
        }
      />
      <div className="verify-colorbar__ticks">
        {ticks.map((label) => (
          <span key={label}>{label}</span>
        ))}
      </div>
      {/* THE WORDS, FOLDED (2026-07-26). The convention, the clamp note and the published stats
          are five lines of small print that a QC read needs OCCASIONALLY and that cost the pane
          ~150px of 3D PERMANENTLY — and, being taller than the row they sat in, they were what
          overflowed the panel and painted across the Cancel / OK bar. A <details> keeps every
          word in the document (and in the accessibility tree) while the pane keeps its height. */}
      <details className="verify-colorbar__detail">
        <summary className="verify-colorbar__summary">legend &amp; stats</summary>
        <p className="verify-colorbar__legend">
          <span className="verify-colorbar__convention">
            {contacts
              ? "absolute distance — no direction; switch to the signed scale to see proud vs sunk"
              : scale.signConvention}
          </span>
          <span className="verify-colorbar__unmeasured">
            <span className="verify-colorbar__swatch" style={{ background: UNMEASURED_COLOR_HEX }} />
            no scan surface under the vertex — not measured
          </span>
        </p>
        {clampNote && <p className="verify-colorbar__clamp">{clampNote}</p>}
        <p className="verify-colorbar__stats">
          Deviation over the footprint: RMS {stats.rmsMm !== null ? `${stats.rmsMm.toFixed(3)} mm` : "—"} ·
          p90 {stats.p90Mm !== null ? `${stats.p90Mm.toFixed(3)} mm` : "—"}{" "}
          <span className="verify-colorbar__source">({stats.source})</span>
        </p>
      </details>
    </div>
  );
}

/**
 * THE THREE-PANEL VERIFY (the centrepiece of the client's library-selection dialog, 2026-07-25): the
 * LIBRARY part, the SCANNED cap region, and BOTH overlaid with the union coloured by deviation.
 *
 * Each pane carries the client's own controls — an eye toggle and an opacity slider per layer —
 * and states what it cannot show rather than showing an empty canvas: the union pane before any
 * run says the deviation read arrives with the first Process, it does not draw an uncoloured
 * guess at where the cap would sit.
 *
 * CAMERA: panes orbit independently by default and can be LINKED by the toggle. Linking mirrors
 * the orbit ANGLES and a relative zoom rather than an absolute camera pose — the library part
 * sits in its own local frame while the scan panes sit out in the scanner's world frame, so a
 * shared absolute camera would point two of the three panes at empty space.
 */
export function VerifyPanels({
  panels,
  onToggleLayer,
  onChangeOpacity,
  linked,
  onToggleLinked,
  maximizedId = null,
  onToggleMaximized,
  renderViewer,
}: VerifyPanelsProps) {
  const shown = maximizedId ? panels.filter((p) => p.id === maximizedId) : panels;
  return (
    <section className="verify-panels" aria-label="Library part, scanned cap and union overlay">
      <div className="verify-panels__toolbar">
        {maximizedId && onToggleMaximized && (
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
      <div
        className={`verify-panels__grid${
          maximizedId ? " verify-panels__grid--maximized" : ""
        }`}
      >
        {shown.map((panel) => (
          <article key={panel.id} className={`verify-panel verify-panel--${panel.id}`}>
            <header className="verify-panel__header">
              <div className="verify-panel__heading">
                <h4 className="verify-panel__title">{panel.title}</h4>
                {onToggleMaximized && (
                  <button
                    type="button"
                    className="verify-panel__maximize"
                    aria-pressed={maximizedId === panel.id}
                    aria-label={
                      maximizedId === panel.id
                        ? `Restore ${panel.title} to the three-panel view`
                        : `Maximise ${panel.title}`
                    }
                    title={
                      maximizedId === panel.id
                        ? "Back to all three panels"
                        : "Expand this panel to the whole stage"
                    }
                    onClick={() => onToggleMaximized(panel.id)}
                  >
                    {maximizedId === panel.id ? "⤡" : "⤢"}
                  </button>
                )}
              </div>
              <p className="verify-panel__caption" title={panel.caption}>
                {panel.caption}
              </p>
            </header>
            {/* THE STAGE IS THE PANEL (client, 2026-07-26: "the panels need to be bigger").
                Every control that used to sit UNDER the 3D — the layer eyes and sliders, the
                deviation colorbar — now floats ON it. Two things follow: the three stages are
                the same height whatever chrome each carries (the union pane's colorbar no
                longer makes it the odd one out), and a pane can no longer overflow its own box
                and paint over the acknowledgment bar, which is what it was doing. */}
            <div className="verify-panel__stage">
              {renderViewer?.(panel.id)}

              <div className="verify-panel__hud verify-panel__hud--layers">
                {panel.layers.map((layer) => (
                  <div key={layer.id} className="verify-layer" title={layer.hint}>
                    <button
                      type="button"
                      className={`verify-layer__eye${layer.visible ? " verify-layer__eye--on" : ""}`}
                      aria-pressed={layer.visible}
                      aria-label={`${layer.visible ? "Hide" : "Show"} ${layer.label}`}
                      disabled={!layer.available}
                      onClick={() => onToggleLayer(panel.id, layer.id)}
                    >
                      {layer.visible ? "👁" : "🚫"}
                    </button>
                    {layer.swatch && (
                      <span className="verify-layer__swatch" style={{ background: layer.swatch }} />
                    )}
                    <span className="verify-layer__label">{layer.label}</span>
                    <label className="sr-only" htmlFor={`opacity-${panel.id}-${layer.id}`}>
                      {layer.label} opacity
                    </label>
                    <input
                      id={`opacity-${panel.id}-${layer.id}`}
                      className="verify-layer__slider"
                      type="range"
                      min={0}
                      max={1}
                      step={0.05}
                      value={layer.opacity}
                      disabled={!layer.available || !layer.visible}
                      onChange={(e) => onChangeOpacity(panel.id, layer.id, Number(e.target.value))}
                    />
                    <OpacityPercent opacity={layer.opacity} />
                  </div>
                ))}
              </div>

              {panel.rotation && (
                <div className="verify-panel__hud verify-panel__hud--rotate">
                  <RotationDial {...panel.rotation} />
                </div>
              )}

              {panel.colorbar && (
                <div className="verify-panel__hud verify-panel__hud--scale">
                  <DeviationColorbar
                    scale={panel.colorbar.scale}
                    stats={panel.colorbar.stats}
                    scaleId={panel.colorbar.scaleId}
                    onSelectScale={panel.colorbar.onSelectScale}
                  />
                </div>
              )}

              {panel.busy && (
                <div className="verify-panel__overlay" role="status" aria-live="polite">
                  <span className="busy-state__spinner" aria-hidden="true" />
                  <span>{panel.busyMessage ?? "loading…"}</span>
                </div>
              )}
              {!panel.busy && panel.notice && (
                <div className="verify-panel__overlay verify-panel__overlay--notice" role="status">
                  <span>{panel.notice}</span>
                </div>
              )}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
