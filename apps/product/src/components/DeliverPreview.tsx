/**
 * THE 3D PREVIEW TABS (client 2026-08-01, verbatim from a screenshot of the demo:
 * "1 · Healing-cap alignment", "2 · Construction in arch", "3 · Construction alone —
 * tooth N" — "we also have the previews of the artifacts").
 *
 * Sits BESIDE the QC preview strip on Deliver, never instead of it: the QC renders
 * (DeliverStage's `qcPreviews`) are the flat evidence; these are the demo's
 * interactive views. REIMPLEMENTED against this product's own viewer package
 * (VerifyViewer + loadStlPositions, already used by SitePanes/DeclarePanes) — no code
 * copied from the demo's ViewerControls.tsx, so no copy-debt-ledger row: only the
 * three labels and the tab structure came from the client's screenshot, and words are
 * not code.
 *
 * ONE MESH PER TAB, NOT A CLIENT-BUILT COMPOSITE (domain/deliver.previewTabs's own
 * note). The demo composited scan + per-part STLs client-side; this product's worker
 * now bakes each of the three views as ONE pre-composited STL
 * (`arch-with-healingcaps.stl`, `arch-with-constructions.stl`,
 * `{tooth}-prosthesis_cad.stl`), so a tab loads exactly one file and tints the WHOLE
 * mesh by the tab's own role. That is an approximation for the two composite tabs —
 * their geometry mixes scan and part surfaces the file itself does not distinguish —
 * and exact for the one tab that IS a single part (construction alone). Per the
 * brief's own steer ("the default material is fine" where per-part colour is not
 * cheap), a flat tint stands in rather than a second client-side compositing engine.
 *
 * FRAMING follows the pane doctrine (verify-UI-directives: "a cap rendering 14px tall
 * in a viewport is a bug — frame so the subject fills its pane"): `frame={null}`
 * hands the job to `VerifyScene.frameAll()`, the SAME general-purpose fit MainStage's
 * "whole arch" and the library pane's own framing already use — right for a big arch
 * composite and a small lone construction alike, with no per-tab frame math needed.
 */
import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  PALETTE,
  ROLE_LABEL,
  VerifyViewer,
  computeAnatomyFrame,
  loadStlPositions,
  paletteHex,
  type VerifyLayerGeometry,
} from "viewer";
import { previewMeshUrl } from "../api/client";
import {
  constructionSiteFrame,
  previewLayerRows,
  visiblePreviewLayers,
  type PreviewLayerRow,
  type PreviewMeshRole,
  type PreviewTab,
} from "../domain/deliver";

export interface DeliverPreviewViewProps {
  readonly tabs: readonly PreviewTab[];
  readonly activeKey: string | null;
  readonly onSelectTab: (key: string) => void;
  readonly busy: boolean;
  readonly error: string | null;
  /** The 3D surface itself — the container passes the real viewer; tests pass a stub. */
  readonly viewerSlot: ReactNode;
  /**
   * THE ACTIVE TAB'S LAYERS, GROUPED — never offered for a single-layer tab (tabs 3/4):
   * hiding the one thing in the scene is not a visibility control, it is an off switch
   * with no "on" beside it, so the row (and its whole HUD) is simply absent there,
   * exactly like `PaneShell`'s own "no layers, no toggle" rule in SitePanes.
   */
  readonly layerRows?: readonly PreviewLayerRow[];
  /** Which roles are currently hidden — view-local in the container, read-only here. */
  readonly hiddenRoles?: ReadonlySet<PreviewMeshRole>;
  readonly onToggleLayer?: (role: PreviewMeshRole) => void;
}

/** The panel's chrome, pure payload → markup — statically testable without WebGL. */
export function DeliverPreviewView({
  tabs,
  activeKey,
  onSelectTab,
  busy,
  error,
  viewerSlot,
  layerRows = [],
  hiddenRoles = new Set(),
  onToggleLayer = () => undefined,
}: DeliverPreviewViewProps) {
  // AN HONEST ABSENCE, TESTED (task doctrine): a run whose package names none of the
  // three files renders no panel at all — never an empty tab strip over a blank pane.
  if (tabs.length === 0) return null;
  const active = tabs.find((tab) => tab.key === activeKey) ?? null;
  return (
    <section
      data-role="deliver-mesh-preview"
      aria-label="3D preview of the run's result"
      className="panel deliver-mesh-preview"
    >
      <h3 className="panel__title">3D preview</h3>
      <div
        data-role="deliver-mesh-preview-tabs"
        className="deliver-mesh-preview__tabs"
        role="tablist"
        aria-label="Preview views"
      >
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            data-role="preview-tab"
            data-key={tab.key}
            role="tab"
            aria-selected={tab.key === activeKey}
            className={`button button--secondary button--small${
              tab.key === activeKey ? " button--active" : ""
            }`}
            onClick={() => onSelectTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div data-role="deliver-mesh-preview-canvas" className="deliver-mesh-preview__canvas">
        {viewerSlot}
        {/* ONLY WHERE THERE IS SOMETHING TO CHOOSE BETWEEN (client 2026-08-09: "a tool
            like the panels to hide certain parts … to make it appear more visually
            appealing"). Presentation only — see visiblePreviewLayers's own doctrine —
            and borrows the workspace panes' own on-glass layer-row chrome
            (SitePanes.tsx's LayerHud) rather than inventing a second one. */}
        {layerRows.length > 1 && (
          <div
            data-role="deliver-mesh-preview-layers"
            className="verify-panel__hud verify-panel__hud--layers"
          >
            {layerRows.map((row) => {
              const visible = !hiddenRoles.has(row.role);
              return (
                <div key={row.role} data-role="preview-layer-row" className="verify-layer">
                  <button
                    type="button"
                    data-role="preview-layer-toggle"
                    data-layer-role={row.role}
                    className={`verify-layer__eye${visible ? " verify-layer__eye--on" : ""}`}
                    aria-pressed={visible}
                    aria-label={`${visible ? "Hide" : "Show"} ${ROLE_LABEL[row.role]}`}
                    onClick={() => onToggleLayer(row.role)}
                  >
                    {visible ? "👁" : "🚫"}
                  </button>
                  <span
                    className="verify-layer__swatch"
                    style={{ background: paletteHex(row.role) }}
                  />
                  <span className="verify-layer__label">{ROLE_LABEL[row.role]}</span>
                </div>
              );
            })}
          </div>
        )}
        {busy && (
          <p data-role="deliver-mesh-preview-busy" className="deliver-mesh-preview__notice">
            Loading {active?.label ?? "the preview"}…
          </p>
        )}
        {error !== null && (
          <div
            data-role="deliver-mesh-preview-error"
            role="alert"
            className="deliver-mesh-preview__notice"
          >
            {error}
          </div>
        )}
      </div>
    </section>
  );
}

export interface DeliverPreviewProps {
  readonly caseId: string;
  /** domain/deliver.previewTabs's own result — the container fetches nothing about
   * WHICH tabs exist; it only loads the ACTIVE one's bytes. */
  readonly tabs: readonly PreviewTab[];
  /** Frame the scene AT the construction sites instead of the whole mesh
   * (client 2026-08-10, the library page: "looking at the top of the
   * construction site"). The centres are the served site centres; the band is
   * the same cap-tight display radius the workspace panes use. The occlusal
   * direction is measured off the loaded mesh itself — the same read pane 2
   * aims by — so the camera looks down at the sites' tops. Omitted (Delivery's
   * own previews) nothing changes: the whole-mesh fit stands. */
  readonly siteFrame?: {
    readonly centers: readonly (readonly number[] | null)[];
    readonly bandMm: number;
  } | null;
}

/** The container: which tab is active, and that tab's mesh bytes. */
export function DeliverPreview({ caseId, tabs, siteFrame = null }: DeliverPreviewProps) {
  const [activeKey, setActiveKey] = useState<string | null>(tabs[0]?.key ?? null);

  // A tab list that no longer carries the active key (a fresh run renamed or dropped
  // it) falls back to the first tab rather than a dangling selection.
  useEffect(() => {
    if (tabs.length === 0) {
      if (activeKey !== null) setActiveKey(null);
      return;
    }
    if (!tabs.some((tab) => tab.key === activeKey)) setActiveKey(tabs[0]!.key);
  }, [tabs, activeKey]);

  const active = tabs.find((tab) => tab.key === activeKey) ?? null;

  /* THE HIDDEN-LAYER TOGGLE (client 2026-08-09), view-local by design — like
     DeclareStageView's `archOpen`: whether a layer is hidden is presentation, not
     case state. Nothing downstream reads it (the artifacts list and every download
     handler read the run's own record, never this component's state), so it earns
     no prop and rides no request. Reset on every tab switch AND on mount, both by
     the same effect: a hide the operator set on tab 1 must not silently carry onto
     tab 2's differently-composed scene. */
  const [hiddenRoles, setHiddenRoles] = useState<ReadonlySet<PreviewMeshRole>>(
    () => new Set(),
  );
  useEffect(() => {
    setHiddenRoles(new Set());
  }, [activeKey]);
  const onToggleLayer = (role: PreviewMeshRole): void => {
    setHiddenRoles((now) => {
      const next = new Set(now);
      if (next.has(role)) next.delete(role);
      else next.add(role);
      return next;
    });
  };
  const layerRows = active !== null ? previewLayerRows(active) : [];

  // ALL of the active tab's layers, or none: the scene is arch + parts composed
  // (client 2026-08-06: "only the healing cap is green"), and a half-loaded scene —
  // green caps floating with no arch, or an arch missing its caps — would misstate
  // the very alignment this preview exists to show.
  const [meshes, setMeshes] = useState<readonly Float32Array[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const layerKey = active?.layers.map((layer) => layer.filename).join("|") ?? "";
  useEffect(() => {
    if (active === null) {
      setMeshes(null);
      setError(null);
      return undefined;
    }
    let cancelled = false;
    setMeshes(null);
    setError(null);
    setBusy(true);
    Promise.all(
      active.layers.map((layer) =>
        loadStlPositions(previewMeshUrl(caseId, layer.filename)),
      ),
    )
      .then((loaded) => {
        if (!cancelled) setMeshes(loaded);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "The preview mesh did not load.");
        }
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
      });
    return () => {
      cancelled = true;
    };
    // keyed on the layer FILENAMES — the effect re-fires on a genuine tab change,
    // not on a fresh (but equal) tabs array from an unrelated re-render
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId, layerKey]);

  // THE HIDDEN ROLES ARE APPLIED HERE ONLY — every file the tab names is still
  // fetched above regardless of visibility (so re-showing a role is instant, the
  // bytes already arrived); a hidden role's layer is simply absent from what this
  // build hands the viewer, per `visiblePreviewLayers`'s own doctrine.
  const layers =
    active !== null && meshes !== null
      ? visiblePreviewLayers(active, hiddenRoles).map((layer) => {
          const index = active.layers.indexOf(layer);
          return {
            id: `${layer.role}-${index}`,
            geometry: {
              positions: meshes[index]!,
              color: PALETTE[layer.role],
            } satisfies VerifyLayerGeometry,
            visible: true,
            opacity: 1,
          };
        })
      : [{ id: "preview", geometry: null, visible: true, opacity: 1 }];

  // THE SITE FRAME (client 2026-08-10, the library page): aim at the sites'
  // tops once the mesh is loaded — the occlusal read comes off the loaded
  // geometry itself, the same measurement pane 2 aims by. Without the prop, or
  // before the bytes land, frame stays null and the whole-mesh fit stands.
  const firstMesh = meshes !== null && meshes.length > 0 ? meshes[0]! : null;
  const paneFrame = useMemo(() => {
    if (siteFrame === null || firstMesh === null) return null;
    const occ = (computeAnatomyFrame(firstMesh)?.occlusal ?? null) as
      | readonly [number, number, number]
      | null;
    return constructionSiteFrame(siteFrame.centers, occ, siteFrame.bandMm);
  }, [siteFrame, firstMesh]);

  return (
    <DeliverPreviewView
      tabs={tabs}
      activeKey={activeKey}
      onSelectTab={setActiveKey}
      busy={busy}
      error={error}
      layerRows={layerRows}
      hiddenRoles={hiddenRoles}
      onToggleLayer={onToggleLayer}
      viewerSlot={
        <VerifyViewer
          layers={layers}
          frame={paneFrame}
          ariaLabel={active !== null ? `Preview: ${active.label}` : "No preview selected"}
        />
      }
    />
  );
}
