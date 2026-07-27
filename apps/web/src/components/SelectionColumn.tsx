import type { ConstructionPart, Jaw, LibraryCatalogEntry, LibraryCatalogGroup } from "../domain/types";
import { JAWS } from "../domain/types";
import type { LibrarySelection } from "../domain/librarySelection";
import {
  GINGIVAL_OFFSET_MAX_MM,
  GINGIVAL_OFFSET_MIN_MM,
  GINGIVAL_OFFSET_STEP_MM,
  formatOffsetMm,
  catalogGroupLabels,
  groupConstructionsByVendor,
  offsetError,
  partitionVariants,
  systemChoices,
} from "../domain/librarySelection";
import type { AchievedGingivalOffset } from "../domain/gingivalOffset";
import {
  OFFSET_HONESTY_LINE,
  OFFSET_NOT_MEASURED_LINE,
  describeAchievedOffset,
} from "../domain/gingivalOffset";
import type { CeilingReadout } from "../domain/reliefLimit";
import {
  CEILING_LOADING_LINE,
  CEILING_PENDING_LINE,
  CEILING_UNAVAILABLE_LINE,
  CEILING_UNDETERMINED_LINE,
  ceilingWarning,
  describeCeiling,
  exceedsCeiling,
} from "../domain/reliefLimit";
import type { SiteReliefClamp } from "../domain/reliefClamp";
import { ReliefClampNotice } from "./ReliefClampNotice";
import { duplicateBadgeText, supersededBadgeText } from "./LibraryBrowser";
import { formatVariantDims } from "./PartPreviewChip";

/** The fetch lifecycle for the two catalogs this column is built from. "unavailable" is the
 *  specific 404: the RUNNING backend predates the endpoint (restart `make serve`) — the column
 *  says so rather than looking empty. */
export type CatalogFetchState = "loading" | "ready" | "unavailable" | "error";

export interface SelectionColumnProps {
  readonly selection: LibrarySelection;
  /** Which site (1-based) the cap-variant list is choosing for — the stepper's current one. */
  readonly activeSiteNumber: number | null;
  readonly activeTooth: number | null;
  readonly libraryState: CatalogFetchState;
  readonly libraryError: string | null;
  readonly groups: readonly LibraryCatalogGroup[];
  readonly constructionsState: CatalogFetchState;
  readonly constructionsError: string | null;
  readonly constructions: readonly ConstructionPart[];
  /** The case's non-binding DEFAULTS, badged as such wherever they appear. */
  readonly suggestedModel: string | null;
  readonly suggestedConstruction: string | null;
  readonly onSelectModel: (model: string) => void;
  readonly onSelectVariant: (variantId: string) => void;
  readonly onSelectConstruction: (pathId: string) => void;
  readonly onSelectJaw: (jaw: Jaw) => void;
  readonly onChangeOffset: (raw: string) => void;
  /** What the LAST run MEASURED on the part it emitted, against the requested relief above.
   *  null = nothing has measured it yet, which the read-out says in those words. */
  readonly achievedOffset: AchievedGingivalOffset | null;
  /**
   * THE CEILING, AT SELECTION TIME (client, 2026-07-25). The maximum relief the chosen
   * construction part can take across the chosen caps, fetched as soon as both are named. Shown
   * beside the input; when the typed value is over it, the field is marked and the warning is
   * printed HERE — before Process, not after a failed run.
   */
  readonly ceiling: CeilingReadout;
  /** What the LAST run actually applied where it had to clamp — empty when nothing was clamped. */
  readonly clamps: readonly SiteReliefClamp[];
  readonly onRetry: () => void;
}

const CONSTRUCTION_PROMPT = "— choose the construction part —";

const OFFSET_HINT =
  "Clearance the emitted construction part is relieved by against the gingival profile — " +
  "0.20 mm is the lab default; 0 skips the relief entirely.";

function UnavailableNote({ what }: { what: string }) {
  return (
    <p className="panel__error" role="alert">
      <span>
        The {what} endpoint is not available on the running API — restart <code>make serve</code>{" "}
        (apps/worker) to pick up this build.
      </span>
    </p>
  );
}

/** One cap-variant card: the size, its catalog dimensions, and the honest flags (superseded
 *  archive / byte-identical duplicate / unloadable) that the library browser already surfaces —
 *  the same helpers, so a part reads identically in both places. */
function VariantOption({
  entry,
  selected,
  labels,
  onSelect,
}: {
  readonly entry: LibraryCatalogEntry;
  readonly selected: boolean;
  /** Catalog display labels — keeps a duplicate counterpart that lives on a client-owned
   *  legacy shelf from printing that shelf's folder name. */
  readonly labels: ReadonlyMap<string, string>;
  readonly onSelect: (variantId: string) => void;
}) {
  const unloadable = entry.flags.includes("unloadable");
  const dims = formatVariantDims(entry.rimDiameterMm, entry.heightMm);
  const duplicate = duplicateBadgeText(entry, labels);
  const superseded = supersededBadgeText(entry);
  return (
    <button
      type="button"
      className={`decode-variant${selected ? " decode-variant--selected" : ""}${
        superseded ? " decode-variant--archived" : ""
      }`}
      aria-pressed={selected}
      disabled={unloadable}
      onClick={() => onSelect(entry.id)}
      title={
        unloadable
          ? "This file cannot be read as a mesh — listed for completeness only"
          : `Select ${entry.variant} for this site`
      }
    >
      <span className="decode-variant__name">{entry.variant}</span>
      <span className="decode-variant__dims">{dims ?? "dimensions unavailable"}</span>
      {(duplicate || superseded || unloadable) && (
        <span className="decode-variant__badges">
          {superseded && <span className="library-badge library-badge--superseded">{superseded}</span>}
          {duplicate && <span className="library-badge library-badge--duplicate">{duplicate}</span>}
          {unloadable && <span className="library-badge library-badge--unloadable">unloadable</span>}
        </span>
      )}
    </button>
  );
}

/**
 * THE CEILING READ-OUT beside the offset input: "max safe for this part: 0.06 mm (limited by
 * channel wall)".
 *
 * Every non-ready state is SPOKEN rather than left blank, because a blank space beside a number
 * reads as "no limit" — which is exactly the belief that produced the client's blocked package:
 *
 *   loading      — the lookup is in flight;
 *   pending      — a ceiling is shown but a sibling cap is still being measured, so it may tighten;
 *   undetermined — the backend answered and could not measure this pair;
 *   unavailable  — the RUNNING API predates the endpoint (restart hint, plus the reassurance that
 *                  the run clamps anyway);
 *   error        — with the retry the rest of the column already offers.
 */
function CeilingReadoutLine({
  ceiling,
  siteCount,
  onRetry,
}: {
  readonly ceiling: CeilingReadout;
  readonly siteCount: number;
  readonly onRetry: () => void;
}) {
  switch (ceiling.kind) {
    case "idle":
      return null;
    case "loading":
      return <p className="decode-offset__ceiling decode-offset__ceiling--pending">{CEILING_LOADING_LINE}</p>;
    case "unavailable":
      return <p className="decode-offset__ceiling decode-offset__ceiling--pending">{CEILING_UNAVAILABLE_LINE}</p>;
    case "undetermined":
      return (
        <p className="decode-offset__ceiling decode-offset__ceiling--pending">
          {CEILING_UNDETERMINED_LINE}
        </p>
      );
    case "error":
      return (
        <p className="decode-offset__ceiling decode-offset__ceiling--error">
          Could not measure the safe relief for this part: {ceiling.message}{" "}
          <button type="button" className="button button--ghost button--small" onClick={onRetry}>
            Retry
          </button>
        </p>
      );
    case "ready":
      return (
        <p className="decode-offset__ceiling">
          {describeCeiling(ceiling.binding, siteCount)}
          {ceiling.pending && (
            <span className="decode-offset__ceiling-pending"> {CEILING_PENDING_LINE}</span>
          )}
        </p>
      );
  }
}

/**
 * THE DECODING SELECTION COLUMN — the left rail of the client's selection dialog (2026-07-25):
 * implant SYSTEM, then the CAP VARIANT (the diameter) for the site the stepper is on, then the
 * CONSTRUCTION part, the jaw, and the gingival profile offset.
 *
 * Every control here is a choice the LAB makes. Where the case carries a name-matched default it
 * is preselected and badged "suggested" — a default an operator can see and change is not the
 * silent guess the client's directive removed (the backend still requires it to be sent back
 * explicitly, and refuses the run otherwise).
 *
 * Superseded archives are shown in their OWN clearly separated group rather than mixed into the
 * current parts, with the same badges the library browser uses; legacy shelves are listed but
 * disabled with the reason, since the run has no cap library to load for them.
 */
export function SelectionColumn({
  selection,
  activeSiteNumber,
  activeTooth,
  libraryState,
  libraryError,
  groups,
  constructionsState,
  constructionsError,
  constructions,
  suggestedModel,
  suggestedConstruction,
  onSelectModel,
  onSelectVariant,
  onSelectConstruction,
  onSelectJaw,
  onChangeOffset,
  achievedOffset,
  ceiling,
  clamps,
  onRetry,
}: SelectionColumnProps) {
  const systems = systemChoices(groups);
  const labels = catalogGroupLabels(groups);
  const activeGroup = groups.find((g) => g.model === selection.model) ?? null;
  const { current, archives } = partitionVariants(activeGroup?.variants ?? []);
  const activeVariantId = selection.sites[selection.activeSiteIndex]?.variantId ?? null;
  const vendorGroups = groupConstructionsByVendor(constructions);
  const offsetMessage = offsetError(selection);
  /* THE CEILING CHECK. Judged against the value that PARSED (the number a run would submit), not
     the raw text — a half-typed "0." must not flash a warning about a number nobody entered. It
     is a WARNING, never a blocker: the field keeps `aria-invalid` for the genuine parse refusal
     above, and the over-ceiling case gets its own marking, because the run WILL proceed (clamped
     and reported) and the operator is entitled to choose that. */
  const binding = ceiling.kind === "ready" ? ceiling.binding : null;
  const overCeiling =
    binding !== null && offsetMessage === null && exceedsCeiling(selection.gingivalOffsetMm, binding);
  const ceilingMessage = binding !== null ? ceilingWarning(selection.gingivalOffsetMm, binding) : null;

  return (
    <div className="decode-column">
      <section className="decode-section" aria-labelledby="decode-system-heading">
        <h3 id="decode-system-heading" className="decode-section__title">
          1 · Implant system
        </h3>
        {libraryState === "loading" && <p className="panel__hint">loading the part library…</p>}
        {libraryState === "unavailable" && <UnavailableNote what="part library" />}
        {libraryState === "error" && (
          <div className="library-browser__error">
            <p className="panel__error" role="alert">
              {libraryError ?? "Failed to load the part library."}
            </p>
            <button type="button" className="button button--secondary button--small" onClick={onRetry}>
              Retry
            </button>
          </div>
        )}
        {libraryState === "ready" && (
          <ul className="decode-system-list">
            {systems.map((system) => (
              <li key={system.model}>
                <button
                  type="button"
                  className={`decode-system${system.model === selection.model ? " decode-system--selected" : ""}`}
                  aria-pressed={system.model === selection.model}
                  disabled={!system.selectable}
                  title={system.unavailableReason ?? `Choose the ${system.label} system`}
                  onClick={() => onSelectModel(system.model)}
                >
                  <span className="decode-system__name">{system.label}</span>
                  <span className="decode-system__count">{system.variantCount} parts</span>
                  {system.model === suggestedModel && (
                    <span className="library-badge library-badge--suggested">suggested</span>
                  )}
                  {!system.selectable && (
                    <span className="library-badge library-badge--legacy">{system.unavailableReason}</span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="decode-section" aria-labelledby="decode-variant-heading">
        <h3 id="decode-variant-heading" className="decode-section__title">
          2 · Cap variant
          {activeSiteNumber !== null && (
            <span className="decode-section__scope">
              {" "}
              — site {activeSiteNumber}
              {activeTooth !== null ? ` (tooth ${activeTooth})` : ""}
            </span>
          )}
        </h3>
        {selection.model === null ? (
          <p className="panel__hint">Choose an implant system first — the cap sizes belong to it.</p>
        ) : activeSiteNumber === null ? (
          <p className="panel__hint">No marked sites on this case yet — mark a cap in step 2.</p>
        ) : (
          <>
            <div className="decode-variant-list">
              {current.map((entry) => (
                <VariantOption
                  key={entry.id}
                  entry={entry}
                  selected={entry.id === activeVariantId}
                  labels={labels}
                  onSelect={onSelectVariant}
                />
              ))}
            </div>
            {archives.map((archive) => (
              <div key={archive.label} className="decode-archive">
                <h4 className="decode-archive__title">{archive.label}</h4>
                <p className="decode-archive__note">
                  Archived parts. Choosable — a superseded cap enters a run only because a human
                  named it.
                </p>
                <div className="decode-variant-list">
                  {archive.entries.map((entry) => (
                    <VariantOption
                      key={entry.id}
                      entry={entry}
                      selected={entry.id === activeVariantId}
                      labels={labels}
                      onSelect={onSelectVariant}
                    />
                  ))}
                </div>
              </div>
            ))}
          </>
        )}
      </section>

      <section className="decode-section" aria-labelledby="decode-construction-heading">
        <h3 id="decode-construction-heading" className="decode-section__title">
          3 · Construction part
        </h3>
        {constructionsState === "loading" && <p className="panel__hint">loading the construction parts…</p>}
        {constructionsState === "unavailable" && <UnavailableNote what="construction parts" />}
        {constructionsState === "error" && (
          <div className="library-browser__error">
            <p className="panel__error" role="alert">
              {constructionsError ?? "Failed to load the construction parts."}
            </p>
            <button type="button" className="button button--secondary button--small" onClick={onRetry}>
              Retry
            </button>
          </div>
        )}
        {constructionsState === "ready" && (
          <>
            <label className="sr-only" htmlFor="decode-construction">
              Construction part
            </label>
            <select
              id="decode-construction"
              className={`decode-select${selection.constructionPathId === null ? " decode-select--needs" : ""}`}
              value={selection.constructionPathId ?? ""}
              aria-invalid={selection.constructionPathId === null}
              onChange={(e) => onSelectConstruction(e.target.value)}
            >
              <option value="">{CONSTRUCTION_PROMPT}</option>
              {vendorGroups.map((group) => (
                <optgroup key={group.vendor} label={group.vendor}>
                  {group.parts.map((part) => (
                    <option key={part.pathId} value={part.pathId}>
                      {part.filename}
                      {part.pathId === suggestedConstruction ? " (suggested)" : ""}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </>
        )}
      </section>

      <section className="decode-section" aria-labelledby="decode-jaw-heading">
        <h3 id="decode-jaw-heading" className="decode-section__title">
          Jaw
        </h3>
        <div className="decode-jaw" role="radiogroup" aria-labelledby="decode-jaw-heading">
          {JAWS.map((jaw) => (
            <button
              key={jaw}
              type="button"
              role="radio"
              aria-checked={selection.jaw === jaw}
              className={`decode-jaw__option${selection.jaw === jaw ? " decode-jaw__option--selected" : ""}`}
              onClick={() => onSelectJaw(jaw)}
            >
              {jaw === "upper" ? "Upper" : "Lower"}
            </button>
          ))}
        </div>
      </section>

      <section className="decode-section" aria-labelledby="decode-offset-heading">
        <h3 id="decode-offset-heading" className="decode-section__title">
          Gingival profile offset
        </h3>
        <div className="decode-offset">
          <input
            id="decode-offset"
            type="number"
            className={`decode-offset__input${offsetMessage ? " decode-offset__input--error" : ""}${
              overCeiling ? " decode-offset__input--over-ceiling" : ""
            }`}
            min={GINGIVAL_OFFSET_MIN_MM}
            max={GINGIVAL_OFFSET_MAX_MM}
            step={GINGIVAL_OFFSET_STEP_MM}
            value={selection.gingivalOffsetInput}
            aria-invalid={offsetMessage !== null}
            aria-describedby={`decode-offset-hint${overCeiling ? " decode-offset-ceiling-warning" : ""}`}
            onChange={(e) => onChangeOffset(e.target.value)}
          />
          <span className="decode-offset__unit">mm</span>
          <span className="decode-offset__applied">
            requested: {formatOffsetMm(selection.gingivalOffsetMm)} mm
          </span>
        </div>
        {/* THE CEILING, BEFORE PROCESSING (client, 2026-07-25). The gingival-relief gate was
            correct but fired at the END of the pipeline, on about half the fleet at the lab's own
            0.20 mm default. This is the same physics, measured up front and put where the number
            is chosen — with the honest states for "still measuring", "could not determine" and
            "this API build has no such endpoint" rather than a blank space. */}
        <CeilingReadoutLine
          ceiling={ceiling}
          siteCount={selection.sites.length}
          onRetry={onRetry}
        />
        {ceilingMessage && (
          <p id="decode-offset-ceiling-warning" className="decode-offset__ceiling-warning" role="status">
            {ceilingMessage}
          </p>
        )}
        {/* What the LAST run had to do about it, if it came to that. */}
        <ReliefClampNotice clamps={clamps} tone="compact" />
        {/* OFFSET HONESTY (measured 2026-07-25): the box above is the REQUEST; this is what the
            last run's emitted part actually carries. Two numbers, both true, neither adjusted to
            flatter the other — see domain/gingivalOffset for why rescaling was refused. */}
        <p
          className={`decode-offset__achieved${achievedOffset === null ? " decode-offset__achieved--unmeasured" : ""}`}
        >
          {achievedOffset === null ? OFFSET_NOT_MEASURED_LINE : describeAchievedOffset(achievedOffset)}
          {achievedOffset?.method && (
            <span className="decode-offset__method"> · {achievedOffset.method}</span>
          )}
        </p>
        <p id="decode-offset-hint" className="decode-section__hint">
          {OFFSET_HINT}
        </p>
        {achievedOffset !== null && (
          <p className="decode-section__hint decode-offset__honesty">{OFFSET_HONESTY_LINE}</p>
        )}
        {offsetMessage && (
          <p className="panel__error" role="alert">
            {offsetMessage}
          </p>
        )}
      </section>
    </div>
  );
}
