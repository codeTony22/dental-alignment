import { Fragment, useState } from "react";
import type { GuidanceLevel, RunSiteResult, SeatMethod, SeedSource, VariantAssessment } from "../domain/types";
import { agreementState } from "../domain/types";
import { RotationVerdict } from "./RotationVerdict";
import { VerificationPanel, type VerificationContext } from "./VerificationPanel";
import { clampChipText, describeClamp, siteReliefClamp } from "../domain/reliefClamp";

interface ResultsTableProps {
  readonly sites: readonly RunSiteResult[];
  /**
   * Open the three-panel verify on this site — WHERE THE ROTATION CONTROL LIVES (2026-07-26).
   * The Rotation column used to carry ±3°/±15° steps; a stepper in a table cell, with no view of
   * what a step does, made a measured pipeline look like a manual one. The column now reports
   * what the coded-cutout reader MEASURED, and this is the only thing it can do about it.
   * Omitted (a read-only embedding) the column is a pure read-out.
   */
  readonly onAdjustRotationIn3D?: (tooth: number) => void;
  /** Doctor verification panel wiring (acceptance numbers + confirm control) — omitted
   *  (read-only embedding) the Verify column and the confirmed chip are not rendered. */
  readonly verification?: VerificationContext;
}

/** Total column count with the Verify column — the expanded panel row spans all of them. */
const COLUMN_COUNT_WITH_VERIFY = 15;

// auto_delta_mm is measured against the human-marked site (brush patch centroid, or click
// center) — NOT against the automation's proposal center. Keep thead/td text in sync.
const AUTO_DELTA_TOOLTIP =
  "Distance between the human-marked site and the automation's nearest proposed site";

// RealGUIDE's "Registration Error: Average/Max" — keep thead/td text in sync.
const FIT_TOOLTIP =
  "Registration error over the aligned surface, like RealGUIDE's Registration Error report; " +
  "max includes screw-recess points the template's bore cannot cover.";

const SEAT_TOOLTIP =
  "rim = closed-form seat from the visible rim circle; icp = fallback registration (partial rim).";

const RIM_AGREEMENT_TOOLTIP =
  "How far the scanned rim ring sits from the seated part (90th percentile). Under ~1.0mm is a " +
  "tight seat; the old Coverage % counted gum the part can never explain.";

const CAP_SURFACE_EXPLAINED_TOOLTIP =
  "Share of the scanned cap surface within 0.35mm of the seated part — measured over the part's own footprint only.";

const READY_TOOLTIP = "All checks agree; accept after the visual check — never a silent auto-pass";

const CANDIDATES_TOOLTIP =
  "Seat residual per candidate size variant — when the top two are within 10% the scan " +
  "cannot separate them and guidance requires the doctor's declaration.";

const MAX_CANDIDATES_SHOWN = 3;

function formatFit(site: RunSiteResult): string {
  if (!site.fit) return "—";
  return `${site.fit.avgMm.toFixed(2)} / ${site.fit.maxMm.toFixed(2)}`;
}

function formatRimAgreement(site: RunSiteResult): string {
  return site.rimAgreementMm !== null ? site.rimAgreementMm.toFixed(2) : "—";
}

function formatCapSurfaceExplained(site: RunSiteResult): string {
  return site.capSurfaceExplainedPct !== null ? `${site.capSurfaceExplainedPct.toFixed(0)}% of cap surface` : "—";
}

/** "Rim seat (mm)" cell: the primary p90 rim-agreement distance, plus a compact muted secondary
 *  line for the OTHER honest alignment number (% of the cap's own footprint explained) — the two
 *  are shown together since either alone can be misread (a tight rim distance on a mostly-
 *  unexplained footprint, or vice versa, both merit a second look). Em-dash for either when null. */
function RimSeatCell({ site }: { site: RunSiteResult }) {
  return (
    <>
      {formatRimAgreement(site)}
      <div className="results-table__cap-surface" title={CAP_SURFACE_EXPLAINED_TOOLTIP}>
        {formatCapSurfaceExplained(site)}
      </div>
    </>
  );
}

/** Muted "variant residual · variant residual" line under the identified variant, best-first,
 *  capped at MAX_CANDIDATES_SHOWN — only rendered when there are >=2 candidates to compare. */
function CandidatesLine({ variant }: { variant: VariantAssessment }) {
  const candidates = variant.candidates;
  if (!candidates || candidates.length < 2) return null;
  const shown = candidates.slice(0, MAX_CANDIDATES_SHOWN);
  const text = shown.map((c) => `${c.variant} ${c.seatResidualMm.toFixed(2)}`).join(" · ");
  return (
    <div className="results-table__candidates" title={CANDIDATES_TOOLTIP}>
      {text}
    </div>
  );
}

/** Pose-stability confidence chip (opt-in): grades how much the seat wobbles under click
 *  noise, folded with the fit residuals. Advisory — nothing renders when not computed. */
function ConfidenceChip({ confidence }: { confidence: RunSiteResult["confidence"] }) {
  if (confidence === null) return null;
  const title = `Pose stable to ${confidence.posSpreadMm.toFixed(2)}mm / ${confidence.axisSpreadDeg.toFixed(0)}° when the marks are re-clicked within click-noise`;
  return (
    <span className={`chip chip--confidence chip--confidence-${confidence.grade}`} title={title}>
      {confidence.grade} confidence
    </span>
  );
}

/**
 * THE CLAMP CHIP (client, 2026-07-25) — "relief clamped 0.20 → 0.06 mm" in the row's verdict
 * cell, carrying the full sentence as its title.
 *
 * It sits with the gate chips deliberately: this row's part was built to a DIFFERENT relief than
 * the lab asked for, which is a fact about the delivered part, not a footnote. The banner above
 * the table says it once for the whole run; this says it on the row it happened to, so a
 * multi-site case cannot leave the operator guessing which tooth was reduced. Nothing renders
 * when the row was not clamped.
 */
function ReliefClampChip({ site }: { site: RunSiteResult }) {
  const clamp = siteReliefClamp(site);
  if (clamp === null) return null;
  return (
    <span className="chip chip--relief-clamped" title={describeClamp(clamp)}>
      {clampChipText(clamp)}
    </span>
  );
}

function GateChip({ level, hasAdvisory }: { level: GuidanceLevel | null; hasAdvisory: boolean }) {
  // Null-safe fallback: rows without guidance (legacy cache) keep the original static chip.
  if (level === null) {
    return <span className="chip chip--gate">{hasAdvisory ? "ADVISORY" : "AUTO"}</span>;
  }
  switch (level) {
    case "ready":
      return (
        <span className="chip chip--gate-ready" title={READY_TOOLTIP}>
          READY · advisory
        </span>
      );
    case "attention":
      return <span className="chip chip--gate-attention">ATTENTION</span>;
    case "action-needed":
      return <span className="chip chip--gate-action">ACTION NEEDED</span>;
  }
}

function SeedChip({ seedSource }: { seedSource: SeedSource }) {
  switch (seedSource) {
    case "brush":
      return <span className="chip chip--seed-brush">🖌 brush</span>;
    case "marks":
      return <span className="chip chip--seed-marks">⊕ marks</span>;
    case "click":
      return <span className="chip chip--seed-click">click</span>;
  }
}

function SeatChip({ seatMethod }: { seatMethod: SeatMethod | null }) {
  if (seatMethod === null) return <span title={SEAT_TOOLTIP}>—</span>;
  return (
    <span
      className={`chip chip--seat chip--seat-${seatMethod}`}
      title={SEAT_TOOLTIP}
    >
      {seatMethod}
    </span>
  );
}

function AgreementCell({ site }: { site: RunSiteResult }) {
  const state = agreementState(site.variant);
  switch (state.kind) {
    case "no-declaration":
      return (
        <span
          className="chip chip--agreement-auto"
          title="No declaration — variant identified from the scan; use the picker to set the doctor's choice"
        >
          auto
        </span>
      );
    case "disputed":
      return (
        <span className="agreement agreement--warn" aria-label="Needs review" title={state.flag}>
          ⚠
        </span>
      );
    case "confirmed":
      return (
        <span
          className="agreement agreement--ok"
          aria-label="Agrees"
          title="Doctor's pick confirmed by the independent rim measurement"
        >
          ✓
        </span>
      );
  }
}

const ROTATION_TOOLTIP =
  "What the automation MEASURED: the rotational residual against the cap's coded cutouts at the " +
  "shipped pose. Correcting it is done in 3D, where a step can be judged against the picture.";

const VERIFY_TOOLTIP =
  "The doctor verification panel: every industry acceptance number this alignment produced, " +
  "next to the reference it anchors to, with the QC images — and the doctor's own sign-off.";

export function ResultsTable({
  sites,
  onAdjustRotationIn3D,
  verification,
}: ResultsTableProps) {
  // Which teeth have their verification panel expanded — per-table UI state; the panel's
  // data itself lives on the site row (acceptance/doctorConfirmation), so nothing is lost
  // on collapse.
  const [expandedTeeth, setExpandedTeeth] = useState<ReadonlySet<number>>(new Set());
  const toggleExpanded = (tooth: number) =>
    setExpandedTeeth((prev) => {
      const next = new Set(prev);
      if (next.has(tooth)) next.delete(tooth);
      else next.add(tooth);
      return next;
    });

  return (
    // Scroll container: 14 columns exceed the main column's width on most screens, and a bare
    // <table> refuses to shrink below its min-content width — it painted straight across the
    // grid gap INTO the 3D viewer (client screenshot, 2026-07-15). Wide content scrolls inside
    // its own panel; the page layout never collides.
    <div className="results-table-scroll">
    <table className="results-table">
      <thead>
        <tr>
          <th scope="col">Tooth</th>
          <th scope="col">Seed</th>
          <th scope="col" title={SEAT_TOOLTIP}>
            Seat
          </th>
          <th scope="col" title={AUTO_DELTA_TOOLTIP}>
            Δ auto (mm)
          </th>
          <th scope="col" title={FIT_TOOLTIP}>
            Fit avg/max (mm)
          </th>
          <th scope="col" title={CANDIDATES_TOOLTIP}>
            Identified variant
          </th>
          <th scope="col">Measured rim Ø (mm)</th>
          <th scope="col">Declared</th>
          <th scope="col">Agreement</th>
          <th scope="col">MD span (mm)</th>
          <th scope="col">Classification</th>
          <th scope="col" title={RIM_AGREEMENT_TOOLTIP}>
            Rim seat (mm)
          </th>
          <th scope="col" title={ROTATION_TOOLTIP}>
            Rotation
          </th>
          <th scope="col">Gate</th>
          {verification && (
            <th scope="col" title={VERIFY_TOOLTIP}>
              Verify
            </th>
          )}
        </tr>
      </thead>
      <tbody>
        {sites.map((site) => (
          <Fragment key={site.tooth}>
          <tr>
            <td>{site.tooth}</td>
            <td>
              <SeedChip seedSource={site.seedSource} />
            </td>
            <td>
              <SeatChip seatMethod={site.seatMethod} />
            </td>
            <td title={AUTO_DELTA_TOOLTIP}>{site.autoDeltaMm?.toFixed(2) ?? "—"}</td>
            <td title={FIT_TOOLTIP}>{formatFit(site)}</td>
            <td>
              <strong>{site.variant.identified}</strong>
              <CandidatesLine variant={site.variant} />
            </td>
            <td>{site.variant.measuredRimDiameterMm?.toFixed(2) ?? "—"}</td>
            <td>{site.variant.declared ?? "—"}</td>
            <td>
              <AgreementCell site={site} />
            </td>
            <td>{site.siteMeasurement.mdSpanMm?.toFixed(2) ?? "terminal"}</td>
            <td>{site.siteMeasurement.classification}</td>
            <td title={RIM_AGREEMENT_TOOLTIP}>
              <RimSeatCell site={site} />
            </td>
            <td title={ROTATION_TOOLTIP}>
              <RotationVerdict site={site} onAdjustIn3D={onAdjustRotationIn3D} />
            </td>
            <td>
              <div className="results-table__gate-cell">
                <GateChip level={site.guidance?.level ?? null} hasAdvisory={Boolean(site.advisory)} />
                <ReliefClampChip site={site} />
                <ConfidenceChip confidence={site.confidence} />
                {verification && site.doctorConfirmation?.confirmed && (
                  <span
                    className="chip chip--band-pass"
                    title={`Doctor confirmed this alignment at ${site.doctorConfirmation.ts}`}
                  >
                    ✓ confirmed
                  </span>
                )}
              </div>
            </td>
            {verification && (
              <td>
                <button
                  type="button"
                  className="button button--ghost button--small"
                  title={VERIFY_TOOLTIP}
                  aria-expanded={expandedTeeth.has(site.tooth)}
                  onClick={() => toggleExpanded(site.tooth)}
                >
                  {expandedTeeth.has(site.tooth) ? "▾ numbers" : "▸ numbers"}
                </button>
              </td>
            )}
          </tr>
          {verification && expandedTeeth.has(site.tooth) && (
            <tr className="results-table__verification-row">
              <td colSpan={COLUMN_COUNT_WITH_VERIFY}>
                <VerificationPanel site={site} context={verification} />
              </td>
            </tr>
          )}
          </Fragment>
        ))}
      </tbody>
    </table>
    </div>
  );
}
