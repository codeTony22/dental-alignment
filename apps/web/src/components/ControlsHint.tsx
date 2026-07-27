/**
 * Small always-visible overlay, bottom-right of the viewer, reminding the operator how to
 * navigate the 3D scene. No state — the controls it describes (rotate/pan/zoom) never change.
 */
export function ControlsHint() {
  return (
    <div className="viewer-controls-hint" aria-hidden="true">
      drag rotate · shift+drag / right-drag pan · scroll zoom
    </div>
  );
}
