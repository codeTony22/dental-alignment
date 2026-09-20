import type { TechniqueMode } from "../api/client";
import { TECHNIQUE_MODE_INFO } from "../domain/technique";

export interface TechniqueStripProps {
  readonly mode: TechniqueMode;
  readonly onChangeMode: (mode: TechniqueMode) => void;
  readonly onRun: () => void;
  readonly busy: boolean;
  readonly disabled: boolean;
}

export function TechniqueStrip({
  mode,
  onChangeMode,
  onRun,
  busy,
  disabled,
}: TechniqueStripProps) {
  const active = TECHNIQUE_MODE_INFO.find((info) => info.id === mode);
  return (
    <section data-role="technique-strip" className="technique-strip" aria-label="Alignment technique">
      <div className="technique-strip__modes" role="radiogroup" aria-label="Technique mode">
        {TECHNIQUE_MODE_INFO.map((info) => (
          <button
            key={info.id}
            type="button"
            role="radio"
            aria-checked={mode === info.id}
            data-role="technique-mode"
            data-mode={info.id}
            className={mode === info.id ? "chip chip--on" : "chip"}
            onClick={() => onChangeMode(info.id)}
            disabled={busy}
          >
            {info.label}
          </button>
        ))}
      </div>
      <p data-role="technique-oneliner" className="technique-strip__note">
        {active?.oneLiner}
      </p>
      <button
        type="button"
        data-role="technique-run"
        className="btn"
        onClick={onRun}
        disabled={busy || disabled}
      >
        {busy ? "Running…" : "Try technique"}
      </button>
    </section>
  );
}
