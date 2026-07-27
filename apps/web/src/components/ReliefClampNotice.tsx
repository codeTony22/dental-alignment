import type { SiteReliefClamp } from "../domain/reliefClamp";
import { CLAMP_WHY_LINE, clampHeadline, describeClamp } from "../domain/reliefClamp";

/**
 * WHERE the notice is mounted. The sentence is the same everywhere — only its weight changes:
 *
 *   "banner"  — the results block and the verify dialog: a full alert the operator cannot walk
 *               past, because a clamp is a change to what the LAB asked for.
 *   "compact" — beside the offset input in the selection column, where the requested number is
 *               still on screen and needs the applied one next to it.
 */
export type ReliefClampNoticeTone = "banner" | "compact";

export interface ReliefClampNoticeProps {
  readonly clamps: readonly SiteReliefClamp[];
  readonly tone?: ReliefClampNoticeTone;
}

/**
 * THE CLAMP, SAID OUT LOUD (client, 2026-07-25).
 *
 * The run may build a part at LESS relief than the lab asked for, when the requested relief would
 * leave the screw channel without a measurable wall. That is the right call — but it is a change
 * to the lab's instruction, and the one outcome nobody may discover later from a file. So this
 * renders in every place the operator can be looking after a run: the results block, the verify
 * dialog and the selection column.
 *
 * It says both numbers per tooth (never one), the reason in the backend's own words when it gave
 * one, and how to process without a clamp at all. It renders NOTHING when nothing was clamped —
 * a standing "no clamp" chip would train the eye to skip the place the real notice appears.
 */
export function ReliefClampNotice({ clamps, tone = "banner" }: ReliefClampNoticeProps) {
  if (clamps.length === 0) return null;
  const compact = tone === "compact";
  return (
    <section
      className={`relief-clamp relief-clamp--${tone}`}
      role="alert"
      aria-label="Gingival relief was clamped"
    >
      <h4 className="relief-clamp__title">
        <span aria-hidden="true">⚠ </span>
        {clampHeadline(clamps)}
      </h4>
      <ul className="relief-clamp__sites">
        {clamps.map((clamp) => (
          <li key={clamp.tooth} className="relief-clamp__site">
            <span className="relief-clamp__tooth">Tooth {clamp.tooth}</span>{" "}
            <span className="relief-clamp__numbers">{describeClamp(clamp)}</span>
            {clamp.reason && <span className="relief-clamp__reason"> — {clamp.reason}</span>}
          </li>
        ))}
      </ul>
      {!compact && <p className="relief-clamp__why">{CLAMP_WHY_LINE}</p>}
    </section>
  );
}
