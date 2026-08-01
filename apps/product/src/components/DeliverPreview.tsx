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
import { useEffect, useState, type ReactNode } from "react";
import { PALETTE, VerifyViewer, loadStlPositions, type VerifyLayerGeometry } from "viewer";
import { previewMeshUrl } from "../api/client";
import type { PreviewTab } from "../domain/deliver";

export interface DeliverPreviewViewProps {
  readonly tabs: readonly PreviewTab[];
  readonly activeKey: string | null;
  readonly onSelectTab: (key: string) => void;
  readonly busy: boolean;
  readonly error: string | null;
  /** The 3D surface itself — the container passes the real viewer; tests pass a stub. */
  readonly viewerSlot: ReactNode;
}

/** The panel's chrome, pure payload → markup — statically testable without WebGL. */
export function DeliverPreviewView({
  tabs,
  activeKey,
  onSelectTab,
  busy,
  error,
  viewerSlot,
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
}

/** The container: which tab is active, and that tab's mesh bytes. */
export function DeliverPreview({ caseId, tabs }: DeliverPreviewProps) {
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

  const [positions, setPositions] = useState<Float32Array | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (active === null) {
      setPositions(null);
      setError(null);
      return undefined;
    }
    let cancelled = false;
    setPositions(null);
    setError(null);
    setBusy(true);
    loadStlPositions(previewMeshUrl(caseId, active.filename))
      .then((loaded) => {
        if (!cancelled) setPositions(loaded);
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
    // active is read only by its stable filename — the effect re-fires on a genuine
    // tab change, not on a fresh (but equal) tabs array from an unrelated re-render
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId, active?.filename]);

  const geometry: VerifyLayerGeometry | null =
    positions !== null && active !== null ? { positions, color: PALETTE[active.role] } : null;

  return (
    <DeliverPreviewView
      tabs={tabs}
      activeKey={activeKey}
      onSelectTab={setActiveKey}
      busy={busy}
      error={error}
      viewerSlot={
        <VerifyViewer
          layers={[{ id: "preview", geometry, visible: true, opacity: 1 }]}
          frame={null}
          ariaLabel={active !== null ? `Preview: ${active.label}` : "No preview selected"}
        />
      }
    />
  );
}
