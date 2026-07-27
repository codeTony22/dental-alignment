import type { LibraryCatalogEntry } from "../domain/types";
import { duplicateBadgeText, supersededBadgeText } from "./LibraryBrowser";

export interface InfoPanelProps {
  /** The catalog entry behind the site's chosen cap variant; null until one is chosen. */
  readonly entry: LibraryCatalogEntry | null;
  readonly model: string | null;
  readonly tooth: number | null;
  /** Catalog display labels (`catalogGroupLabels`) — a duplicate counterpart on a client-owned
   *  legacy shelf is named by the shelf's label, never by its data-folder name. */
  readonly labels: ReadonlyMap<string, string>;
}

/** "6.16 mm" / "—" when the catalog carries no dimension for this part. A dimension is never
 *  invented: an unreadable CAD says so rather than showing a plausible number. */
function dimension(valueMm: number | null): string {
  return valueMm !== null ? `${valueMm.toFixed(2)} mm` : "—";
}

/**
 * THE INFORMATION PANEL — the client's dialog shows Diameter and Height for the selected
 * library part, straight from the library. Same numbers as the catalog card and the picker chip
 * (one source: the server's measured `rim_diameter_mm` / `height_mm`), plus the file the run
 * would actually ship and the honest flags on it.
 */
export function InfoPanel({ entry, model, tooth, labels }: InfoPanelProps) {
  if (entry === null) {
    return (
      <section className="decode-info decode-info--empty" aria-labelledby="decode-info-heading">
        <h3 id="decode-info-heading" className="decode-info__title">
          Information
        </h3>
        <p className="panel__hint">
          No cap variant chosen{tooth !== null ? ` for tooth ${tooth}` : ""} — pick one on the left
          and its diameter, height and file appear here.
        </p>
      </section>
    );
  }

  const superseded = supersededBadgeText(entry);
  const duplicate = duplicateBadgeText(entry, labels);
  const unloadable = entry.flags.includes("unloadable");

  return (
    <section className="decode-info" aria-labelledby="decode-info-heading">
      <h3 id="decode-info-heading" className="decode-info__title">
        Information
        <span className="decode-info__subject">
          {model ? `${model} · ` : ""}
          {entry.variant}
          {tooth !== null ? ` — tooth ${tooth}` : ""}
        </span>
      </h3>
      <dl className="decode-info__grid">
        <div>
          <dt>Diameter</dt>
          <dd>{dimension(entry.rimDiameterMm)}</dd>
        </div>
        <div>
          <dt>Height</dt>
          <dd>{dimension(entry.heightMm)}</dd>
        </div>
        <div className="decode-info__file">
          <dt>Library file</dt>
          <dd>
            <code>{entry.filename}</code>
          </dd>
        </div>
      </dl>
      {(superseded || duplicate || unloadable) && (
        <div className="decode-info__badges">
          {superseded && <span className="library-badge library-badge--superseded">{superseded}</span>}
          {duplicate && <span className="library-badge library-badge--duplicate">{duplicate}</span>}
          {unloadable && <span className="library-badge library-badge--unloadable">unloadable</span>}
        </div>
      )}
    </section>
  );
}
