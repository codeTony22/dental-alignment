import type { AdjustOutcomeView, LandmarkView } from "../api/client";
import {
  ADJUST_TOOLS,
  DEFAULT_DIAMETER_MM,
  ROTATION_STEPS,
  type AdjustToolId,
} from "../domain/adjustBindings";

export interface AdjustDockProps {
  readonly tool: AdjustToolId;
  readonly onSelectTool: (id: AdjustToolId) => void;
  readonly busy: boolean;
  readonly diameterMm: number;
  readonly onChangeDiameter: (mm: number) => void;
  readonly onRotate: (step: number) => void;
  readonly onResetRotation: () => void;
  readonly onBestFit: (apply: boolean) => void;
  readonly onRePreview: () => void;
  readonly landmarks: readonly LandmarkView[];
  readonly lastOutcome: AdjustOutcomeView | null;
  readonly refusal: string | null;
}

export function AdjustDock({
  tool,
  onSelectTool,
  busy,
  diameterMm,
  onChangeDiameter,
  onRotate,
  onResetRotation,
  onBestFit,
  onRePreview,
  landmarks,
  lastOutcome,
  refusal,
}: AdjustDockProps) {
  const active = ADJUST_TOOLS.find((item) => item.id === tool);
  return (
    <aside data-role="adjust-dock" className="dock">
      <nav className="dock__rail" aria-label="Adjust tools">
        {ADJUST_TOOLS.map((item) => (
          <button
            key={item.id}
            type="button"
            data-role="adjust-tool"
            data-tool={item.id}
            className={tool === item.id ? "chip chip--on" : "chip"}
            onClick={() => onSelectTool(item.id)}
            disabled={busy}
          >
            {item.label}
          </button>
        ))}
      </nav>
      <p data-role="adjust-oneliner" className="dock__note">{active?.oneLiner}</p>

      {tool === "rotation" && (
        <div data-role="rotation-widget" className="dock__widget">
          {ROTATION_STEPS.map((step) => (
            <button
              key={step}
              type="button"
              data-role="rotation-step"
              disabled={busy}
              onClick={() => onRotate(step)}
            >
              {step > 0 ? `+${step}°` : `${step}°`}
            </button>
          ))}
          <button type="button" data-role="rotation-reset" disabled={busy} onClick={onResetRotation}>
            Reset
          </button>
        </div>
      )}

      {(tool === "best-fit" || tool === "fit-by-points") && (
        <div data-role="best-fit-widget" className="dock__widget">
          <label>
            Matching diameter
            <input
              data-role="diameter"
              type="number"
              min={0.05}
              max={2}
              step={0.05}
              value={diameterMm}
              disabled={busy}
              onChange={(event) => onChangeDiameter(Number(event.target.value) || DEFAULT_DIAMETER_MM)}
            />
            mm
          </label>
          <button type="button" disabled={busy} onClick={() => onBestFit(false)}>Measure</button>
          <button type="button" disabled={busy} onClick={() => onBestFit(true)}>Apply</button>
        </div>
      )}

      {tool === "auto-mark" && (
        <ol data-role="auto-mark-landmarks" className="dock__list">
          {landmarks.length === 0 ? (
            <li>No landmarks served for this site.</li>
          ) : landmarks.map((mark) => (
            <li key={mark.id} data-landmark={mark.id}>
              {mark.id}
              {mark.lever_arm_mm != null ? ` · lever ${mark.lever_arm_mm} mm` : ""}
            </li>
          ))}
        </ol>
      )}

      <div className="dock__footer">
        <button type="button" data-role="re-preview" disabled={busy} onClick={onRePreview}>
          Re-read pose
        </button>
      </div>

      {refusal !== null && (
        <p data-role="adjust-refusal" className="dock__refuse" role="alert">{refusal}</p>
      )}
      {lastOutcome !== null && (
        <p data-role="adjust-outcome" className="dock__outcome">
          {lastOutcome.operation} — {lastOutcome.detail}
          {lastOutcome.cross_checked === false ? " · single observation, unchecked" : ""}
        </p>
      )}
    </aside>
  );
}
