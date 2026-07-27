/**
 * Capture-quality chips + banner (master plan §1 SCAN / §8 item 11).
 *
 * The industry pattern the demo mirrors: coded-cap workflows refuse inadequate
 * scans AT INTAKE — entire cap circumference, code markings clearly visible, collar
 * >=1mm supragingival — with a concrete recapture instruction WHILE THE PATIENT IS IN
 * THE CHAIR. A "rescan" verdict must be prominent BEFORE the operator invests marks;
 * pass/marginal stay chip-sized. Advisory in the demo (no upload flow yet): nothing
 * here blocks the run.
 */
import type { CaptureAssessment, CaptureVerdict } from "../domain/types";
import { captureIssues } from "../domain/types";

const CHIP_LABEL: Record<CaptureVerdict, string> = {
  pass: "capture ✓",
  marginal: "capture marginal",
  rescan: "RESCAN",
};

/** One site's capture verdict as a chip; the concrete recapture messages ride the tooltip. */
export function CaptureChip({ capture }: { readonly capture: CaptureAssessment }) {
  const issues = captureIssues(capture);
  const title =
    issues.length > 0
      ? issues.map((c) => c.message).join("\n")
      : "All capture checks pass: rim circumference, coded band, collar exposure.";
  return (
    <span className={`chip chip--capture chip--capture-${capture.verdict}`} title={title}>
      {CHIP_LABEL[capture.verdict]}
    </span>
  );
}

export interface CaptureBannerItem {
  /** Doctor-facing anchor for the messages: "Tooth 7", "Proposal 2", ... */
  readonly label: string;
  readonly capture: CaptureAssessment;
}

/**
 * The prominent intake warning: renders ONLY when at least one site verdict is
 * "rescan" — the one state where continuing wastes operator marks on a scan no
 * algorithm can rescue (the t7 lesson: discovered at the END of the pipeline).
 */
export function CaptureBanner({ items }: { readonly items: readonly CaptureBannerItem[] }) {
  const rescans = items.filter((it) => it.capture.verdict === "rescan");
  if (rescans.length === 0) return null;
  return (
    <div className="capture-banner" role="alert">
      <p className="capture-banner__title">
        Capture quality: {rescans.length} site{rescans.length > 1 ? "s" : ""} need
        {rescans.length > 1 ? "" : "s"} a rescan — catch it while the patient is in the
        chair (the coded-cap industry pattern: inadequate scans are refused at intake,
        not discovered after design).
      </p>
      <ul className="capture-banner__list">
        {rescans.map((it) =>
          captureIssues(it.capture)
            .filter((c) => c.verdict === "rescan")
            .map((c) => (
              <li key={`${it.label}-${c.name}`} className="capture-banner__item">
                <strong>{it.label}:</strong> {c.message}
              </li>
            )),
        )}
      </ul>
    </div>
  );
}
