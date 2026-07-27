import type { RunSiteResult } from "../domain/types";

interface FlagsAlertsProps {
  readonly sites: readonly RunSiteResult[];
}

export function FlagsAlerts({ sites }: FlagsAlertsProps) {
  const flagged = sites.flatMap((site) =>
    site.variant.flags.map((flag) => ({ tooth: site.tooth, flag })),
  );

  if (flagged.length === 0) return null;

  return (
    <div className="flags-alerts" role="alert">
      <h3 className="flags-alerts__title">Flags</h3>
      {flagged.map((item, i) => (
        <div key={i} className="flags-alerts__item">
          <span className="flags-alerts__tooth">Tooth {item.tooth}</span>
          <span className="flags-alerts__text">{item.flag}</span>
        </div>
      ))}
    </div>
  );
}
