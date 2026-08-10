/**
 * THE CONSTRUCTION LIBRARY — page four of the client's 2026-08-01 flow (design
 * "ArTech End-to-End Flow": Intake · Alignment · Adjustment · Construction library ·
 * Delivery).
 *
 * IT OWNS NO PART LIST. The options are the catalog's, through
 * `intake.constructionOptions`, and the effective value plus its attribution are the
 * BFF's, through `deliver.constructionStepWords` — the same two sources Intake's
 * dropdown and Deliver's picker already read. The design comp carries a literal table
 * of four invented parts with prices and lead times; none of those fields exist in the
 * real catalog, so none of them are shown. Inventing a price on a presentational
 * surface would be this app quoting money the server never said.
 *
 * THE CHANGE IS DISCLOSED BEFORE IT IS MADE, through the same
 * `constructionChangeWords` Deliver's picker states, so the two surfaces cannot
 * describe one act differently. WHAT the words disclose changed with §10-AC:
 * `emit_from_poses` is BUILT — over a done run, a part (or relief) change RE-EMITS
 * the package from the run's own poses in seconds (the pose is provably
 * construction-independent, so nothing re-aligns and the fits the operator
 * reviewed stand); the confirmation still falls explicitly, and the design gate
 * can refuse the new pairing as a refused run. Without a done run the old full
 * reset is still the truth, and the old words still say it.
 *
 * ARMING A CANDIDATE PREVIEWS IT, ALONE (§10-M2's "natural next slice", 2026-08-02).
 * The stage's single preview pane REPLACES its content with the armed part's own
 * catalog mesh — not stacked beside the run's mesh, which is `PartPreview.tsx`'s own
 * module doc's decision, restated here because it is this page's layout, not that
 * component's: ONE pane is the comp's own shape, and the workbench grid's column
 * budget is already tight (plan §10-P.2). Disarming (Cancel, or committing so the
 * candidate clears) returns the pane to whatever it showed before.
 */
import { useEffect, useState } from "react";
import type { CaseSessionDetail } from "../api/client";
import { fetchRun, putChoices } from "../api/client";
import { constructionOptions } from "../domain/intake";
import {
  constructionChangeRetiresSomething,
  constructionChangeWords,
  constructionGroups,
  constructionStepWords,
  libraryForwardLabel,
  libraryNote,
  libraryPreviewCaption,
  libraryPreviewPending,
  libraryPreviewTab,
} from "../domain/deliver";
import { scanPaneRadiusMm } from "../domain/declare";
import { DeliverPreview } from "./DeliverPreview";
import { ErrorBanner } from "./ErrorBanner";
import { PartPreview } from "./PartPreview";

export interface LibraryStageViewProps {
  readonly detail: CaseSessionDetail;
  /** The current run's own package list, from GET /{id}/run — the same source
   *  Deliver's preview reads. Empty while it loads, which renders the honest gap
   *  rather than a flash of a preview that is not there yet. */
  readonly packageFiles: readonly string[];
  readonly saving: boolean;
  readonly error: string | null;
  /** A part picked but not yet committed — null unless it differs from the effective
   *  one, so re-picking what is already chosen is never an act. */
  readonly candidate: string | null;
  readonly onPick: (pathId: string) => void;
  readonly onCancel: () => void;
  readonly onCommit: () => void;
}

export function LibraryStageView({
  detail,
  packageFiles,
  saving,
  error,
  candidate,
  onPick,
  onCancel,
  onCommit,
}: LibraryStageViewProps) {
  const options = constructionOptions(detail);
  const info = constructionStepWords(detail.choices, options);
  const groups = constructionGroups(options);
  const chosen = info.pathId !== null;
  const caseId = detail.case.id;
  // the run's OWN unified mesh, where it built one — this page is only reachable over
  // a done run, so the file the route serves is on disk by construction
  const previewTab = libraryPreviewTab(packageFiles);
  // THE ARMED CANDIDATE (§10-M2's "natural next slice", 2026-08-02): a part picked
  // but not yet committed has no run behind it at all, so there is no union to show
  // for it — only the catalog's own mesh, alone. `candidate` is already the arming
  // state the confirm step below reads; this is the same fact, read a second way.
  const armedOption =
    candidate !== null ? options.find((o) => o.path_id === candidate) ?? null : null;
  // the case's EFFECTIVE part, for the run-less fallback below — same lookup, the
  // standing choice instead of the one being weighed
  const effectiveOption =
    info.pathId !== null ? options.find((o) => o.path_id === info.pathId) ?? null : null;

  return (
    /* ONE CENTERED PAGE, spanning the workbench (comp page pass 2026-08-02, §10-AA):
       the comp's library is a title, a lead, part CARDS on the left and the preview
       column on the right — not a control column beside a stage. `.stage-page` spans
       both workbench columns (grid-column: 1 / -1), which is what makes a single
       wrapper safe: the previous two-children layout existed because a lone wrapper
       landed in the 356px control column, and the span rule retires that failure at
       the grid rather than by markup shape. */
    <div data-role="library-stage" className="stage-page">
      <div className="stage-page__inner">
        {error !== null && <ErrorBanner detail={error} />}

        <h2 className="stage-page__title">Construction library</h2>
        <p data-role="library-note" className="stage-page__lead">
          {libraryNote(chosen)}
        </p>

        <div className="library-page__body">
          <div className="library-page__parts">
            <section data-role="library-parts" className="library-parts">
              {groups.length === 0 ? (
                <p className="panel__hint">
                  This data tree carries no construction parts, so there is nothing to
                  pick.
                </p>
              ) : (
                groups.map((group) => (
                  <div key={group.vendor} className="library-parts__group">
                    <p className="library-parts__vendor">{group.vendor}</p>
                    <ul className="library-parts__grid">
                      {group.options.map((option) => {
                        const active = option.path_id === (candidate ?? info.pathId);
                        const effective = option.path_id === info.pathId;
                        return (
                          <li key={option.path_id}>
                            <button
                              type="button"
                              data-role="library-part"
                              data-part={option.path_id}
                              data-active={active ? "true" : "false"}
                              className={
                                active
                                  ? "library-part library-part--on"
                                  : "library-part"
                              }
                              disabled={saving}
                              onClick={() => onPick(option.path_id)}
                            >
                              <span className="library-part__head">
                                <span className="library-part__label">
                                  {option.label}
                                </span>
                                {/* the comp's card chip: the effective row always reads
                                    "selected" (client 2026-08-06, §10-AO — the word
                                    "suggested" goes on THIS page only; Intake's and
                                    Alignment's effective-choice chips still name the
                                    server's own attribution verbatim), any other row
                                    wears the neutral invite */}
                                {effective ? (
                                  <span className="chip chip--ready">selected</span>
                                ) : (
                                  <span className="chip chip--gate">select</span>
                                )}
                              </span>
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                ))
              )}
            </section>

            {candidate !== null && (
              <section data-role="library-confirm" className="panel">
                <p className="panel__hint">
                  {constructionChangeWords(
                    options.find((o) => o.path_id === candidate)?.label ?? candidate,
                    detail.session.confirmed,
                    detail.session.run_state === "done",
                  )}
                </p>
                <div className="panel__actions">
                  <button
                    type="button"
                    data-role="library-commit"
                    className="button button--primary button--small"
                    disabled={saving}
                    onClick={onCommit}
                  >
                    {constructionChangeRetiresSomething(detail.session)
                      ? "Change the part and retire the run"
                      : "Set this part"}
                  </button>
                  <button
                    type="button"
                    data-role="library-cancel"
                    className="button button--ghost button--small"
                    disabled={saving}
                    onClick={onCancel}
                  >
                    Keep the current part
                  </button>
                </div>
              </section>
            )}
          </div>

          <section data-role="library-preview" className="library-preview">
            {/* NO PLACEHOLDER DISC. The design comp's preview reads no data at all and
                wears the scan cap's palette, so porting it would depict the cap and
                imply a union that is not there. Where the RUN built a real unified
                mesh this renders that; where it did not, the gap is stated. */}
            {armedOption !== null ? (
              // DECISION (client direction, 2026-08-02): an ARMED candidate REPLACES
              // the pane's content rather than stacking a second pane beside the
              // run's own mesh — ONE pane, the comp's own shape. Disarming (Cancel,
              // or committing so the candidate clears) returns the pane to whatever
              // it showed before: the run's own union above, or the stated gap.
              <PartPreview
                label={armedOption.label}
                meshUrl={armedOption.mesh_url ?? null}
              />
            ) : previewTab === null && effectiveOption?.mesh_url ? (
              /* THE EFFECTIVE-BUT-UNRUN PART (client "do what is recommended",
                 2026-08-02). No run receipt is readable, but the case already holds
                 an effective construction and the catalog serves its mesh — same
                 pane, same §10-M2 doctrine as the armed branch: the part alone,
                 implying no union nobody computed. A row without a mesh_url still
                 falls through to the stated gap — a guessed URL is worse than an
                 honest absence. */
              <PartPreview label={info.label} meshUrl={effectiveOption.mesh_url} />
            ) : previewTab === null ? (
              <p data-role="library-preview-pending" className="panel__hint">
                {libraryPreviewPending()}
              </p>
            ) : (
              <>
                <DeliverPreview
                  caseId={caseId}
                  tabs={[previewTab]}
                  /* client 2026-08-10: "Construction page should do the same —
                     looking at the top of the construction site". Centres are
                     the served sites'; the band is the workspace panes' own
                     cap-tight radius, so the two pages frame alike. */
                  siteFrame={{
                    centers: detail.sites.map((s) => s.center),
                    /* the workspace band plus 4mm of arch context: this pane is
                       several times a workspace pane's size, and at the bare
                       band the part filled it as an abstract close-up — the
                       neighbouring anatomy is what makes it read as standing
                       IN the arch */
                    bandMm: scanPaneRadiusMm(detail) + 4,
                  }}
                />
                <p data-role="library-preview-caption" className="panel__hint">
                  {libraryPreviewCaption(info.label)}
                </p>
              </>
            )}

            {/* The comp keeps the page's acts at the preview card's foot (template
                L537-550), forward leading; the disabled forward stays visible in the
                0.45-opacity convention rather than vanishing. */}
            <div className="library-preview__acts">
              {chosen ? (
                <a
                  data-role="library-forward"
                  className="button button--primary button--small"
                  href={`/case/${caseId}/deliver`}
                >
                  {libraryForwardLabel(true)}
                </a>
              ) : (
                <span
                  data-role="library-forward"
                  className="button button--primary button--small"
                  aria-disabled="true"
                >
                  {libraryForwardLabel(false)}
                </span>
              )}
              <a
                data-role="library-back"
                className="button button--ghost button--small"
                href={`/case/${caseId}/adjust`}
              >
                Back to Adjustment
              </a>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

export function LibraryStage({
  detail,
  onDetail,
}: {
  readonly detail: CaseSessionDetail;
  readonly onDetail: (next: CaseSessionDetail) => void;
}) {
  const [candidate, setCandidate] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [packageFiles, setPackageFiles] = useState<readonly string[]>([]);

  // the run's own receipt, the same read Deliver's preview makes. A failure is not
  // surfaced as an error here: the page's JOB is picking a part, and it does that with
  // or without a preview — so a missing receipt degrades to the stated gap.
  useEffect(() => {
    let live = true;
    void fetchRun(detail.case.id).then((result) => {
      if (live && result.kind === "ok") setPackageFiles(result.data.package_files);
    });
    return () => {
      live = false;
    };
  }, [detail.case.id]);

  const commit = async () => {
    if (candidate === null) return;
    setSaving(true);
    setError(null);
    const result = await putChoices(detail.case.id, {
      construction_path: candidate,
      jaw: detail.choices.jaw,
      gingival_offset_mm: detail.choices.gingival_offset_mm,
      turnaround: detail.choices.turnaround ?? null,
    });
    setSaving(false);
    if (result.kind === "ok") {
      setCandidate(null);
      onDetail(result.data);
    } else {
      setError(result.detail);
    }
  };

  return (
    <LibraryStageView
      detail={detail}
      packageFiles={packageFiles}
      saving={saving}
      error={error}
      candidate={candidate}
      onPick={(id) =>
        // re-picking what is already effective is not an act — the reset boundary is
        // keyed on the EFFECTIVE value changing, so offering to "confirm" a no-op
        // would promise a blast radius that will not happen
        setCandidate(
          id ===
            constructionStepWords(detail.choices, constructionOptions(detail)).pathId
            ? null
            : id,
        )
      }
      onCancel={() => setCandidate(null)}
      onCommit={commit}
    />
  );
}
