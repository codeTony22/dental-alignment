import type { LibraryCatalogEntry, LibraryCatalogGroup } from "../domain/types";
import { catalogGroupLabels } from "../domain/librarySelection";
import { formatVariantDims } from "./PartPreviewChip";
import { PartAnnotator, type PartAnnotatorContext } from "./PartAnnotator";

/**
 * The catalog fetch lifecycle as the PANEL sees it. "unavailable" is the specific 404 case:
 * the RUNNING backend predates GET /api/library (the endpoint ships with this build but the
 * user's `make serve` started earlier) — the panel shows the restart hint instead of breaking.
 */
export type LibraryBrowserState = "loading" | "ready" | "unavailable" | "error";

/** The unique key of one catalog entry across the whole shelf — model + id (id is unique
 *  within its group; two 6020s can coexist as current vs superseded with distinct ids). */
export function catalogEntryKey(model: string, entry: Pick<LibraryCatalogEntry, "id">): string {
  return `${model}/${entry.id}`;
}

/**
 * "identical file to neodent-gm 6020" — the honest byte-identity finding, named; null when the
 * entry is not a duplicate. Multiple counterparts join with ", ".
 *
 * A counterpart is `"<model>/<id>"`, and for a legacy shelf that model is the raw name of a
 * client-owned data folder the interface does not print — so the model half goes through the
 * same display labels the tabs use. Pass `labels` (from `catalogGroupLabels`) wherever the
 * catalog is on hand; without it the ref is shown as it came, which is correct for every real
 * implant system since their labels ARE their models.
 */
export function duplicateBadgeText(
  entry: LibraryCatalogEntry,
  labels?: ReadonlyMap<string, string>,
): string | null {
  if (!entry.flags.includes("duplicate") || entry.duplicateOf.length === 0) return null;
  const names = entry.duplicateOf.map((ref) => {
    const cut = ref.indexOf("/");
    const model = cut === -1 ? ref : ref.slice(0, cut);
    const rest = cut === -1 ? "" : ref.slice(cut + 1);
    const shown = labels?.get(model) ?? model;
    return `${shown} ${rest}`.trim().replace("--", " ");
  });
  return `identical file to ${names.join(", ")}`;
}

/** "superseded 2026-07-13" derived from the archive dir in the filename ("superseded-2026-07-13/…"),
 *  falling back to plain "superseded"; null when the entry is current. */
export function supersededBadgeText(entry: LibraryCatalogEntry): string | null {
  if (!entry.flags.includes("superseded")) return null;
  const dir = entry.filename.split("/")[0] ?? "";
  const date = dir.startsWith("superseded-") ? dir.slice("superseded-".length) : null;
  return date ? `superseded ${date}` : "superseded";
}

/**
 * The tab caption: the model dir name, with legacy groups saying so right on the tab. A legacy
 * shelf's model is the raw name of a client-owned data folder, which the interface does not
 * print — `catalogGroupLabels` hands back the neutral shelf name for it, and that is what the
 * tab says. `labels` is that map (from the same group list).
 */
export function groupTabLabel(
  group: Pick<LibraryCatalogGroup, "model" | "legacy">,
  labels: ReadonlyMap<string, string>,
): string {
  const label = labels.get(group.model) ?? group.model;
  return group.legacy ? `${label} (legacy)` : label;
}

interface LibraryBrowserProps {
  readonly state: LibraryBrowserState;
  /** Human-readable failure for state "error" (never shown for "unavailable" — that state
   *  has its own dedicated restart hint). */
  readonly errorMessage: string | null;
  readonly groups: readonly LibraryCatalogGroup[];
  /** Which model tab is active; null only while nothing is loaded yet. */
  readonly activeModel: string | null;
  /** catalogEntryKey of the entry currently previewed in the 3D viewer, if any. */
  readonly previewedKey: string | null;
  readonly onSelectModel: (model: string) => void;
  readonly onPreviewEntry: (group: LibraryCatalogGroup, entry: LibraryCatalogEntry) => void;
  readonly onRetry: () => void;
  readonly onClose: () => void;
  /** The ANNOTATION half (client ask 2026-07-24): mark this part's holes/trenches. Only the
   *  PREVIEWED card offers it — the marks are placed by clicking the part in the 3D viewer,
   *  so annotating a part that is not on screen would be meaningless. Omitted entirely in
   *  read-only embeddings, which then render no annotate affordance at all. */
  readonly onAnnotateEntry?: (group: LibraryCatalogGroup, entry: LibraryCatalogEntry) => void;
  /** The open annotation panel, when one is (null otherwise). */
  readonly annotator?: PartAnnotatorContext | null;
}

/**
 * The LIBRARY BROWSER (client ask 2026-07-23): the WHOLE shelf under data/real/library/caps,
 * classified — system tabs as the primary chooser (neodent-gm / zimmer-4.5 / legacy groups,
 * exactly the choice the client asked for), a card per part with its honest flags (superseded
 * archives and byte-identical duplicates surfaced, never hidden), click-to-preview onto the
 * main stage — the ONE remaining swap-style preview (2026-07-26): the step-2 rows compare
 * through the docked pane instead, but the browser is case-independent and often has no scan
 * for a part to sit beside, so its cards keep the swap.
 */
export function LibraryBrowser({
  state,
  errorMessage,
  groups,
  activeModel,
  previewedKey,
  onSelectModel,
  onPreviewEntry,
  onRetry,
  onClose,
  onAnnotateEntry,
  annotator,
}: LibraryBrowserProps) {
  const activeGroup = groups.find((g) => g.model === activeModel) ?? null;
  const labels = catalogGroupLabels(groups);
  // The annotate affordance belongs to the card that is actually IN the viewer: marks are
  // placed by clicking the part in 3D, so offering it on a part that is not on screen would
  // arm a click with nothing to click.
  const previewedEntry =
    activeGroup?.variants.find((e) => catalogEntryKey(activeGroup.model, e) === previewedKey) ?? null;

  return (
    <section className="panel library-browser" aria-labelledby="library-heading">
      <div className="library-browser__header">
        <h2 id="library-heading" className="panel__title">
          Part library — full catalog
        </h2>
        <button
          type="button"
          className="button button--ghost button--small"
          onClick={onClose}
          title="Close the library browser"
        >
          ✕ close
        </button>
      </div>

      {state === "loading" && (
        <div className="busy-state" role="status" aria-live="polite">
          <span className="busy-state__spinner" aria-hidden="true" />
          <span className="busy-state__message">scanning the part library…</span>
        </div>
      )}

      {state === "unavailable" && (
        <p className="panel__error" role="alert">
          {/* one span: panel__error is a flex row, and bare text + <code> siblings would
              otherwise become separate flex items with odd gaps (seen live) */}
          <span>
            The library endpoint is not available on the running API — restart{" "}
            <code>make serve</code> (apps/worker) to pick up this build, then reopen the
            library. The rest of the demo keeps working meanwhile.
          </span>
        </p>
      )}

      {state === "error" && (
        <div className="library-browser__error">
          <p className="panel__error" role="alert">
            {errorMessage ?? "Failed to load the part library."}
          </p>
          <button type="button" className="button button--secondary button--small" onClick={onRetry}>
            Retry
          </button>
        </div>
      )}

      {state === "ready" && groups.length === 0 && (
        <p className="panel__hint">No library parts found under data/real/library/caps.</p>
      )}

      {state === "ready" && groups.length > 0 && (
        <>
          <p className="panel__copy">
            Every part on the shelf, classified by implant system — including superseded
            archives and byte-identical duplicates, flagged honestly. Click a part to load it
            in the 3D viewer.
          </p>
          <div className="library-browser__tabs" role="tablist" aria-label="Implant system">
            {groups.map((group) => (
              <button
                key={group.model}
                type="button"
                role="tab"
                aria-selected={group.model === activeModel}
                className={`library-tab${group.model === activeModel ? " library-tab--active" : ""}${
                  group.legacy ? " library-tab--legacy" : ""
                }`}
                onClick={() => onSelectModel(group.model)}
              >
                {groupTabLabel(group, labels)}
                <span className="library-tab__count">{group.variants.length}</span>
              </button>
            ))}
          </div>
          {activeGroup && (
            <div
              className="library-cards"
              role="tabpanel"
              aria-label={`${labels.get(activeGroup.model) ?? activeGroup.model} parts`}
            >
              {activeGroup.variants.map((entry) => {
                const key = catalogEntryKey(activeGroup.model, entry);
                const unloadable = entry.flags.includes("unloadable");
                const dims = formatVariantDims(entry.rimDiameterMm, entry.heightMm);
                const duplicate = duplicateBadgeText(entry, labels);
                const superseded = supersededBadgeText(entry);
                const isPreviewed = previewedKey === key;
                return (
                  <button
                    key={key}
                    type="button"
                    className={`library-card${isPreviewed ? " library-card--active" : ""}${
                      superseded || entry.flags.includes("legacy") ? " library-card--muted" : ""
                    }`}
                    disabled={unloadable}
                    aria-pressed={isPreviewed}
                    onClick={() => onPreviewEntry(activeGroup, entry)}
                    title={
                      unloadable
                        ? "This file cannot be read as a mesh — listed for completeness only"
                        : isPreviewed
                          ? "Currently in the 3D viewer"
                          : "Load this part in the 3D viewer"
                    }
                  >
                    <span className="library-card__variant">{entry.variant}</span>
                    <span className="library-card__dims">{dims ?? "dimensions unavailable"}</span>
                    <span className="library-card__filename">{entry.filename}</span>
                    {(duplicate || superseded || entry.flags.includes("legacy") || unloadable || isPreviewed) && (
                      <span className="library-card__badges">
                        {isPreviewed && <span className="library-badge library-badge--viewing">viewing ✓</span>}
                        {duplicate && (
                          <span className="library-badge library-badge--duplicate">{duplicate}</span>
                        )}
                        {superseded && (
                          <span className="library-badge library-badge--superseded">{superseded}</span>
                        )}
                        {entry.flags.includes("legacy") && (
                          <span className="library-badge library-badge--legacy">legacy library</span>
                        )}
                        {unloadable && (
                          <span className="library-badge library-badge--unloadable">unloadable</span>
                        )}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          )}
          {onAnnotateEntry && activeGroup && previewedEntry !== null && (
            <div className="library-browser__annotate-bar">
              <span className="library-browser__annotate-text">
                {previewedEntry.variant} is in the 3D viewer — mark its holes/trenches once and
                every case that ships this part reuses the marks.
              </span>
              <button
                type="button"
                className="button button--secondary button--small"
                disabled={annotator !== null && annotator !== undefined}
                onClick={() => onAnnotateEntry(activeGroup, previewedEntry)}
                title="Mark this part's coded features, so a scan click can name WHICH one it is"
              >
                ✎ Annotate features
              </button>
            </div>
          )}
        </>
      )}

      {annotator && <PartAnnotator context={annotator} />}
    </section>
  );
}
