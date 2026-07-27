import { ROLE_LABEL, paletteHex, type PartRole } from "../viewer/palette";

interface LegendProps {
  /** Roles present in the currently loaded composite view; the legend is hidden when empty. */
  readonly roles: readonly PartRole[];
}

/** Small overlay, bottom-left of the viewer, naming each colored part role in the active composite. */
export function Legend({ roles }: LegendProps) {
  // one chip per distinct role — a composite may hold several parts of the same role
  const distinct = [...new Set(roles)];
  if (distinct.length === 0) return null;

  return (
    <div className="viewer-legend" role="list" aria-label="Composite view legend">
      {distinct.map((role) => (
        <span key={role} className="chip viewer-legend__chip" role="listitem">
          <span
            className="viewer-legend__swatch"
            style={{ backgroundColor: paletteHex(role) }}
            aria-hidden="true"
          />
          {ROLE_LABEL[role]}
        </span>
      ))}
    </div>
  );
}
