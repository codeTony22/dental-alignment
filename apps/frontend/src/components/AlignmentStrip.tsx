import type { SignalEnvelope } from "../api/client";
import { displayValue } from "../domain/signals";

export interface AlignmentStripProps {
  readonly caseId: string | null;
  readonly tooth: number | null;
  readonly signals: SignalEnvelope | null;
}

function pick(group: Record<string, unknown> | undefined, key: string): string {
  return displayValue(group?.[key]);
}

export function AlignmentStrip({ caseId, tooth, signals }: AlignmentStripProps) {
  const residue = signals?.groups["residue"];
  const clocking = signals?.groups["clocking"];
  const certification = signals?.groups["certification"];
  const correspondence = signals?.groups["correspondence"];
  return (
    <section data-role="alignment-strip" className="alignment-strip" aria-label="Alignment figures">
      <span data-role="strip-case">{caseId ?? "—"}</span>
      <span data-role="strip-tooth">{tooth !== null ? `tooth ${tooth}` : "no site"}</span>
      <span data-stat="dev-rms">DEV RMS {pick(residue, "deviation_rms_mm")}</span>
      <span data-stat="dev-p90">P90 {pick(residue, "deviation_p90_mm")}</span>
      <span data-stat="rotation">
        ROT {pick(clocking, "notch_shift_deg")}
        {certification?.["rotation_unverified"] === true ? " · unverified" : ""}
      </span>
      <span data-stat="pairs">
        PAIRS {pick(correspondence, "pair_count")}
        {correspondence?.["cross_checked"] === false ? " · unchecked" : ""}
      </span>
    </section>
  );
}
