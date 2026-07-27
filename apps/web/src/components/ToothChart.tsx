import { useState } from "react";
import type { Jaw } from "../domain/types";
import {
  ARCH_ROWS,
  cellsByTooth,
  buildToothCells,
  parseToothEntry,
  TOOTH_FLAG_TEXT,
  type ToothCell,
  type ToothChartSite,
} from "../domain/toothChart";

export interface ToothChartProps {
  /** The jaw the RUN is selected for — highlighted; the other arch is dimmed. */
  readonly jaw: Jaw;
  readonly sites: readonly ToothChartSite[];
  /** The SHARED site cursor, as a tooth number — the same one the stepper moves. */
  readonly activeTooth: number | null;
  /** The tooth whose "click its cap on the scan" pick is currently armed, if any. */
  readonly armedTooth: number | null;
  readonly autoNumber: boolean;
  /** What auto-numbering would use for the next site; null when the arch is full. */
  readonly nextTooth: number | null;
  /** Why a site cannot be added right now (null = it can). Carries the REASON, not just a
   *  boolean, because adding arms a click on the scan and another tool may already own it —
   *  a disabled control here has to say which one, like every other gate in this app. */
  readonly addBlockedReason: string | null;
  readonly onSelectTooth: (tooth: number, siteIndex: number) => void;
  readonly onAddTooth: (tooth: number) => void;
  readonly onToggleAutoNumber: (on: boolean) => void;
  readonly onCancelAdd: () => void;
}

/**
 * One tooth's state in words — the second half of its accessible name, and its tooltip. Written
 * out (not conveyed by colour alone) because colour is exactly what a chart cannot rely on: the flags
 * this reports are the ones an operator would otherwise have to go hunting for in three other
 * panels.
 */
export function toothStateSummary(cell: ToothCell): string {
  if (cell.siteIndex === null) {
    return cell.inCaseJaw ? "no site — add one here" : "no site (other arch)";
  }
  const parts = [
    `site ${cell.siteIndex + 1}`,
    cell.marked ? "marks placed" : "no marks yet",
    cell.reviewed ? "reviewed" : "not reviewed",
  ];
  for (const flag of cell.flags) parts.push(TOOTH_FLAG_TEXT[flag]);
  return parts.join(" · ");
}

/** The glyph the button carries under its number: the site's own state at a glance. */
function toothGlyph(cell: ToothCell): string {
  if (cell.siteIndex === null) return "";
  if (cell.flags.length > 0) return "!";
  if (cell.reviewed) return "✓";
  return cell.marked ? "◍" : "○";
}

function toothClassName(cell: ToothCell, armed: boolean): string {
  const classes = ["tooth-chart__tooth"];
  if (cell.siteIndex !== null) classes.push("tooth-chart__tooth--site");
  if (cell.active) classes.push("tooth-chart__tooth--active");
  if (cell.marked) classes.push("tooth-chart__tooth--marked");
  if (cell.reviewed) classes.push("tooth-chart__tooth--reviewed");
  if (cell.flags.length > 0) classes.push("tooth-chart__tooth--flagged");
  if (!cell.inCaseJaw) classes.push("tooth-chart__tooth--off-jaw");
  if (armed) classes.push("tooth-chart__tooth--armed");
  return classes.join(" ");
}

/**
 * THE DENTAL TOOTH CHART (RealGUIDE screenshot parity, 2026-07-25) — Universal numbering laid
 * out as the familiar arch diagram, used as the case's SITE PICKER.
 *
 * WHY IT IS A PICKER AND NOT A SECOND SELECTION. The stepper ('‹ 2 / 3 ›' in the verify dialog)
 * and this chart move the SAME cursor: `LibrarySelection.activeSiteIndex`, owned by App. The
 * chart takes `activeTooth` and reports clicks; it holds no selection of its own, so the two
 * controls cannot disagree about which site is being worked on. Two independent cursors is the
 * failure this shape rules out — an operator would have no way to tell which one the dialog
 * believed.
 *
 * WHAT A TOOTH SAYS. Its number, whether it carries a site, whether that site has marks, whether
 * it has been REVIEWED (the state the Process gate counts), and any flag it has earned — capture
 * rescan, unverified rotation, a disputed cap declaration, a duplicated number, or a site on the
 * wrong arch. Every one of those is in the accessible name and the tooltip, never colour alone.
 *
 * CLICKING AN EMPTY TOOTH OFFERS TO ADD A SITE THERE. It does not create one: a site needs a
 * position on the scan, so the click ARMS a one-shot pick ("click tooth 14's cap on the scan"),
 * and nothing exists until the operator places it. Cancel and Escape both abort — the same
 * non-destructive arm/place/cancel shape as every other marking tool here.
 *
 * KEYBOARD. Every tooth is a real button: tab reaches it, Enter/Space activates it, and its
 * accessible name is the full sentence ("Tooth 3 — upper right first molar — site 1 · marks
 * placed · reviewed"). Teeth on the other arch with no site are the only disabled ones — a site
 * cannot be added to the arch the run is not for, but an EXISTING site there stays selectable
 * (it is flagged, and the operator must be able to reach it to fix it).
 */
export function ToothChart({
  jaw,
  sites,
  activeTooth,
  armedTooth,
  autoNumber,
  nextTooth,
  addBlockedReason,
  onSelectTooth,
  onAddTooth,
  onToggleAutoNumber,
  onCancelAdd,
}: ToothChartProps) {
  const [manualEntry, setManualEntry] = useState("");
  const [manualError, setManualError] = useState<string | null>(null);
  const cells = cellsByTooth(buildToothCells({ jaw, sites, activeTooth }));
  const usedTeeth = sites.map((s) => s.tooth);
  const canAdd = addBlockedReason === null;

  const addManually = () => {
    const parsed = parseToothEntry(manualEntry, { jaw, usedTeeth });
    if (parsed.kind === "error") {
      setManualError(parsed.message);
      return;
    }
    setManualError(null);
    setManualEntry("");
    onAddTooth(parsed.tooth);
  };

  return (
    <section className="panel tooth-chart" aria-labelledby="tooth-chart-heading">
      <h2 id="tooth-chart-heading" className="panel__title">
        Tooth chart
        <span className="panel__title-case"> — {jaw} jaw</span>
      </h2>
      <p className="panel__copy">
        Universal numbering, upper 1–16 and lower 17–32. Click a tooth to work on its site — the
        chart and the site stepper move the same cursor. Click an empty tooth on the{" "}
        {jaw} arch to add a site there.
      </p>

      {armedTooth !== null && (
        <div className="brush-banner" role="status" aria-live="polite">
          <span className="brush-banner__text">
            Click tooth {armedTooth}&apos;s healing cap on the scan…
          </span>
          <div className="brush-banner__actions">
            <button type="button" className="button button--secondary" onClick={onCancelAdd}>
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="tooth-chart__arch">
        {ARCH_ROWS.map((row) => (
          <div
            key={row.jaw}
            className={`tooth-chart__row${row.jaw === jaw ? " tooth-chart__row--case-jaw" : " tooth-chart__row--other-jaw"}`}
          >
            <span className="tooth-chart__row-label">
              {row.label}
              {row.jaw === jaw && <span className="tooth-chart__row-badge"> this case</span>}
            </span>
            <div className="tooth-chart__quadrants">
              {row.quadrants.map((quadrant) => (
                <ul key={quadrant.label} className="tooth-chart__quadrant" aria-label={quadrant.label}>
                  {quadrant.teeth.map((tooth) => {
                    const cell = cells.get(tooth);
                    if (!cell) return null;
                    const armed = armedTooth === tooth;
                    const summary = toothStateSummary(cell);
                    const isEmpty = cell.siteIndex === null;
                    const disabled = isEmpty && (!cell.inCaseJaw || !canAdd || armedTooth !== null);
                    return (
                      <li key={tooth}>
                        <button
                          type="button"
                          className={toothClassName(cell, armed)}
                          aria-label={`${cell.label} — ${summary}`}
                          aria-current={cell.active ? "true" : undefined}
                          title={`${cell.label}\n${summary}`}
                          disabled={disabled}
                          onClick={() =>
                            cell.siteIndex === null
                              ? onAddTooth(tooth)
                              : onSelectTooth(tooth, cell.siteIndex)
                          }
                        >
                          <span className="tooth-chart__number">{tooth}</span>
                          <span className="tooth-chart__glyph" aria-hidden="true">
                            {toothGlyph(cell)}
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              ))}
            </div>
          </div>
        ))}
      </div>

      <ul className="tooth-chart__legend">
        <li>
          <span className="tooth-chart__glyph" aria-hidden="true">
            ○
          </span>{" "}
          site, no marks
        </li>
        <li>
          <span className="tooth-chart__glyph" aria-hidden="true">
            ◍
          </span>{" "}
          marks placed
        </li>
        <li>
          <span className="tooth-chart__glyph" aria-hidden="true">
            ✓
          </span>{" "}
          reviewed
        </li>
        <li>
          <span className="tooth-chart__glyph" aria-hidden="true">
            !
          </span>{" "}
          needs attention
        </li>
      </ul>

      {/* AUTOMATED TOOTH NUMBER INCREASING (their toggle): on, a new site takes the next free
          number after the last one; off, the operator types it. Either way the number is chosen
          BEFORE the site exists, so the duplicate-tooth guard has nothing to catch. */}
      <div className="tooth-chart__add">
        <label className="tooth-chart__auto-toggle">
          <input
            type="checkbox"
            checked={autoNumber}
            onChange={(e) => onToggleAutoNumber(e.target.checked)}
          />{" "}
          Automatic tooth number increasing
        </label>

        {autoNumber ? (
          <button
            type="button"
            className="button button--secondary button--small"
            disabled={!canAdd || nextTooth === null || armedTooth !== null}
            title={
              addBlockedReason ??
              (nextTooth === null
                ? `Every tooth on the ${jaw} arch already has a site`
                : `Add a site on tooth ${nextTooth} — the next free number on the ${jaw} arch`)
            }
            onClick={() => nextTooth !== null && onAddTooth(nextTooth)}
          >
            + Add site{nextTooth !== null ? ` (tooth ${nextTooth})` : ""}
          </button>
        ) : (
          <span className="tooth-chart__manual">
            <label className="tooth-chart__manual-label" htmlFor="tooth-chart-manual">
              Tooth
            </label>
            <input
              id="tooth-chart-manual"
              type="number"
              className="confirm-table__input confirm-table__input--tooth"
              value={manualEntry}
              aria-invalid={manualError !== null}
              disabled={!canAdd || armedTooth !== null}
              onChange={(e) => {
                setManualEntry(e.target.value);
                setManualError(null);
              }}
            />
            <button
              type="button"
              className="button button--secondary button--small"
              disabled={!canAdd || armedTooth !== null}
              onClick={addManually}
            >
              + Add site
            </button>
          </span>
        )}
      </div>

      {manualError && (
        <p className="panel__error" role="alert">
          {manualError}
        </p>
      )}
      {nextTooth === null && autoNumber && (
        <p className="panel__hint">
          Every tooth on the {jaw} arch already has a site — there is no free number left to add
          one on.
        </p>
      )}
    </section>
  );
}
