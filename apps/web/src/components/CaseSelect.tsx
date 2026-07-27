import type { Case } from "../domain/types";

interface CaseSelectProps {
  readonly cases: readonly Case[];
  readonly selectedCaseId: string | null;
  readonly loadingCases: boolean;
  readonly loadingScanProgress: number | null;
  readonly onSelect: (caseItem: Case) => void;
}

export function CaseSelect({
  cases,
  selectedCaseId,
  loadingCases,
  loadingScanProgress,
  onSelect,
}: CaseSelectProps) {
  return (
    <section className="panel" aria-labelledby="step1-heading">
      <h2 id="step1-heading" className="panel__title">
        Step 1 · Select case
      </h2>
      {loadingCases && <p className="panel__hint">Loading cases…</p>}
      {!loadingCases && cases.length === 0 && (
        <p className="panel__hint">No cases available from the automation backend.</p>
      )}
      <div className="case-cards">
        {cases.map((c) => {
          const isSelected = c.id === selectedCaseId;
          return (
            <button
              key={c.id}
              type="button"
              className={`case-card${isSelected ? " case-card--selected" : ""}`}
              onClick={() => onSelect(c)}
              aria-pressed={isSelected}
            >
              <span className="case-card__doctor">{c.doctor}</span>
              <span className="case-card__jaw">{c.jaw}</span>
              {/* The vendor is DERIVED from the case's name-matched construction suggestion, so
                  it is nullable (client directive 2026-07-25: a folder named after the patient
                  suggests nothing) and it is not a fact about the case — the lab still chooses
                  the construction part. Labelled as a suggestion, and omitted entirely when
                  there is none rather than rendering an empty pill. */}
              {c.vendor !== null && (
                <span className="chip" title="suggested from the scan folder name — the construction part is chosen in Verify &amp; process">
                  {c.vendor} (suggested)
                </span>
              )}
            </button>
          );
        })}
      </div>
      {loadingScanProgress !== null && (
        <p className="panel__hint" role="status">
          Loading scan… {(loadingScanProgress * 100).toFixed(0)}% (file is ~15MB)
        </p>
      )}
    </section>
  );
}
