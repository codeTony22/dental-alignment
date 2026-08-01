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
 * THE CHANGE IS DISCLOSED BEFORE IT IS MADE. Changing the effective construction is a
 * reset boundary server-side: it invalidates every preview and clears the current-run
 * pointer, because a different part means a different emitted package. That is the
 * same blast radius Deliver's own picker states, through the same
 * `constructionChangeWords`, so the two surfaces cannot describe one act differently.
 *
 * The plan's `emit_from_poses` (§4) would let a part change RE-EMIT instead of
 * re-running — the pose is provably construction-independent, so the alignment need
 * never be redone. It is priced and not built, so this page tells the truth about the
 * cost rather than pretending it is free.
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
import { DeliverPreview } from "./DeliverPreview";
import { ErrorBanner } from "./ErrorBanner";

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

  return (
    /* TWO CHILDREN, because `.stage-contents` is `display: contents` — a stage's own
       children become the workbench grid's columns. The picker is a CONTROL, so it
       belongs in the narrow work column beside every other stage's controls; the
       union preview is the SUBJECT, so it takes the stage. Rendering one wrapper put
       the whole page in the 356px control column (caught by running it, not by a
       test — every assertion here is on markup, and markup cannot see a column). */
    <>
      <div data-role="library-stage" className="workbench__work">
        {error !== null && <ErrorBanner detail={error} />}

        <section data-role="library-parts" className="panel">
          <h2 className="panel__title">Construction library</h2>
          <p data-role="library-note" className="panel__hint">
            {libraryNote(chosen)}
          </p>
          {groups.length === 0 ? (
            <p className="panel__hint">
              This data tree carries no construction parts, so there is nothing to pick.
            </p>
          ) : (
            groups.map((group) => (
              <div key={group.vendor} className="library-parts__group">
                <p className="library-parts__vendor">{group.vendor}</p>
                <ul className="library-parts__options">
                  {group.options.map((option) => {
                    const active = option.path_id === (candidate ?? info.pathId);
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
                          <span className="library-part__label">{option.label}</span>
                          {option.path_id === info.pathId && (
                            <span className="chip chip--ready">
                              {info.suggested ? "suggested" : "selected"}
                            </span>
                          )}
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

        <section className="panel">
          <div className="panel__actions">
            <a
              data-role="library-back"
              className="button button--ghost button--small"
              href={`/case/${caseId}/adjust`}
            >
              Back to Adjustment
            </a>
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
          </div>
        </section>
      </div>

      <section data-role="library-preview" className="workbench__stage">
        {/* NO PLACEHOLDER DISC. The design comp's preview reads no data at all and
            wears the scan cap's palette, so porting it would depict the cap and imply
            a union that is not there. Where the RUN built a real unified mesh this
            renders that; where it did not, the gap is stated. */}
        {previewTab === null ? (
          <p data-role="library-preview-pending" className="panel__hint">
            {libraryPreviewPending()}
          </p>
        ) : (
          <>
            <DeliverPreview caseId={caseId} tabs={[previewTab]} />
            <p data-role="library-preview-caption" className="panel__hint">
              {libraryPreviewCaption(info.label)}
            </p>
          </>
        )}
      </section>
    </>
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
