/**
 * DELIVER (plan §4 Deliver, slice 8; grill AM-1/AM-10/AM-12), rebuilt around the
 * client's 2026-07-27 corrections #4, #5 and #6:
 *
 *  - THE REPORT IS A MODAL (#5: "The reports can be shown in a modal"). The stage
 *    carries a COMPACT evidence summary — one line per site, worst-first exactly as
 *    the BFF serves it (this app never re-sorts evidence) — plus one prominent way
 *    in. The full assurance table (all columns, industry references, per-row QC
 *    images) lives in the modal, and so do the acts that belong beside the rows it
 *    shows: the per-flag acknowledgment and the withhold. Read and act in one place.
 *  - DISPOSITIONS DEFAULT TO RELEASE (#4: "What is disposition release vs withhold").
 *    A clean row shows no control at all and says quietly that it is released; only a
 *    FLAGGED row can be withheld, and only that act must be stated. The server agrees:
 *    an omitted disposition IS release.
 *  - DELIVERY IS ONE PROGRESSION (#6: "good UI for payment and release of information
 *    / artifacts"). Confirmed → Paid → Released, each step showing its state, its
 *    timestamp or its action or what it waits for; the release step NAMES what will be
 *    disclosed before the act; the artifacts land grouped BY SITE with names and sizes.
 *
 * ONE derived blocker list (domain/deliver.confirmBlockers) feeds both places the
 * surface offers to confirm from — the stage and the modal footer — so there can
 * never be two answers about whether this case is confirmable.
 *
 * Direction of trust (AM-4): optimism is OFF. Every POST's response is the whole new
 * detail, replacing the payload verbatim (onDetail); refusals render in the backend's
 * own words. The evidence-drift 409 ("the case changed since it was confirmed") keeps
 * its own flow: reload the evidence and ask again — never a silent retry.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchArtifactBlob,
  fetchArtifacts,
  fetchAssurance,
  postConfirm,
  postPayment,
  postRelease,
  qcImageUrl,
  type ArtifactsView,
  type AssuranceSite,
  type AssuranceView,
  type CaseSessionDetail,
  type FetchState,
} from "../api/client";
import {
  ackRequired,
  confirmBlockers,
  confirmWireBody,
  effectiveDisposition,
  evidenceSummary,
  formatBytes,
  groupArtifacts,
  isEvidenceDrift409,
  releaseDisclosureWords,
  releaseSteps,
  withholdOffered,
  type Disposition,
  type DispositionMap,
} from "../domain/deliver";

export type DeliverPhase = "idle" | "confirming" | "paying" | "releasing";

const PHASE_WORDS: Readonly<Record<Exclude<DeliverPhase, "idle">, string>> = {
  confirming: "Sealing the confirmation…",
  paying: "Recording the (stub) payment authorization…",
  releasing: "Releasing — re-deriving the evidence…",
};

/** The gate chip's tone from the verdict's own word — the demo's traffic lights. */
function gateChipClass(level: string): string {
  const word = level.toLowerCase();
  if (word.includes("ready")) return "chip chip--gate-ready";
  if (word.includes("attention") || word.includes("review")) return "chip chip--gate-attention";
  if (word.includes("action") || word.includes("fail")) return "chip chip--gate-action";
  return "chip chip--gate";
}

/** The identity-agreement chip: the backend's own word wears its tone. */
function agreementChipClass(agreement: string | null): string {
  if (agreement === "match") return "chip chip--band-pass";
  if (agreement === "mismatch") return "chip chip--band-fail";
  return "chip chip--agreement-auto";
}

/** THE ONE BLOCKER LIST, rendered wherever confirming is offered. A component, not
 * a copied loop: the stage and the modal footer must be looking at the same array,
 * and a shared renderer makes "two sources of truth" impossible to reintroduce by
 * accident. */
function ConfirmBlockers({ blockers }: { readonly blockers: readonly string[] }) {
  if (blockers.length === 0) return null;
  return (
    <ul data-role="confirm-blockers" className="blocker-list">
      {blockers.map((piece) => (
        <li key={piece}>{piece}</li>
      ))}
    </ul>
  );
}

interface AssuranceRowProps {
  readonly caseId: string;
  readonly site: AssuranceSite;
  readonly disposition: Disposition;
  readonly acknowledged: boolean;
  readonly expanded: boolean;
  readonly onDisposition: (tooth: number, act: Disposition) => void;
  readonly onAcknowledge: (tooth: number, on: boolean) => void;
  readonly onToggleExpand: (tooth: number) => void;
}

/** One verdict row: the facts, each numeric beside its industry reference, the
 * operator's controls, and the QC evidence behind the expand — in the demo's
 * results-table language (chips, muted references, the clamp's requested→applied). */
function AssuranceRow({
  caseId,
  site,
  disposition,
  acknowledged,
  expanded,
  onDisposition,
  onAcknowledge,
  onToggleExpand,
}: AssuranceRowProps) {
  const rimRef = site.references["rim_agreement_mm"];
  const rmsRef = site.references["deviation_rms_mm"];
  const rotation = site.rotation;
  return (
    <>
      <tr
        data-role="assurance-row"
        data-tooth={site.tooth}
        data-status={site.status ?? "unknown"}
        data-flagged={site.status === "flagged"}
        className={site.status === "flagged" ? "assurance-row--flagged" : undefined}
      >
        <td>
          <strong>Tooth {site.tooth}</strong>{" "}
          <span
            data-role="status-chip"
            data-status={site.status ?? "unknown"}
            className="chip chip--status"
          >
            {site.status ?? "unknown"}
          </span>
        </td>
        <td data-role="cell-identity">
          declared {site.declared_variant ?? "—"} / measured{" "}
          {site.identified_variant ?? "—"}{" "}
          <span
            data-role="identity-agreement"
            className={agreementChipClass(site.variant_agreement)}
          >
            {site.variant_agreement ?? "unmeasured"}
          </span>
        </td>
        <td data-role="cell-seat">
          <span
            className={`chip chip--seat ${
              (site.seat_method ?? "").startsWith("rim") ? "chip--seat-rim" : "chip--seat-icp"
            }`}
          >
            {site.seat_method ?? "—"}
          </span>{" "}
          rim {site.rim_agreement_mm ?? "—"}
          {site.rim_agreement_mm !== null && " mm"}
          {rimRef && (
            <small data-role="industry-ref" className="results-table__candidates">
              {" "}
              vs {rimRef.industry_ref.value}
            </small>
          )}
        </td>
        <td data-role="cell-rotation">
          <span className="rotation-verdict">
            <span className="rotation-verdict__residual">
              {rotation.deg !== null ? `${rotation.deg}°` : "no reading"} (
              {rotation.evidence ?? "no evidence"})
            </span>
            {rotation.unverified && (
              <em
                data-role="rotation-unverified"
                className="rotation-verdict__residual rotation-verdict__residual--review"
              >
                {" "}
                rotation unverified
              </em>
            )}
          </span>
        </td>
        <td data-role="cell-deviation">
          RMS {site.deviation_rms_mm ?? "—"} / p90 {site.deviation_p90_mm ?? "—"} mm
          {rmsRef && (
            <small data-role="industry-ref" className="results-table__candidates">
              {" "}
              vs {rmsRef.industry_ref.value}
            </small>
          )}
        </td>
        <td data-role="cell-gate">
          <div className="results-table__gate-cell">
            <span data-role="gate-level" className={gateChipClass(site.gate.level)}>
              {site.gate.level}
            </span>
            {site.gate.actions.map((words) => (
              <p key={words} data-role="gate-words" className="results-table__candidates">
                {words}
              </p>
            ))}
          </div>
        </td>
        <td data-role="cell-clamp">
          {site.clamp.clamped ? (
            <>
              <span className="chip chip--relief-clamped">
                {site.clamp.requested_mm ?? "—"} → {site.clamp.applied_mm ?? "—"} mm
              </span>
              <p className="results-table__candidates">
                relief clamped — {site.clamp.reason ?? "no reason recorded"}
              </p>
            </>
          ) : (
            "relief as requested"
          )}
        </td>
        <td>
          <div className="assurance-controls">
            {/* THE DISPOSITION CONTROL RENDERS ONLY ON A FLAGGED ROW (client
                2026-07-27 #4). A clean site is released — the row SAYS so, quietly,
                instead of asking a question with one sane answer. */}
            {withholdOffered(site) ? (
              <span className="segmented">
                <button
                  type="button"
                  data-role="disposition-release"
                  aria-pressed={disposition === "release"}
                  className="segmented__option"
                  onClick={() => onDisposition(site.tooth, "release")}
                >
                  release
                </button>
                <button
                  type="button"
                  data-role="disposition-withhold"
                  aria-pressed={disposition === "withhold"}
                  className="segmented__option segmented__option--withhold"
                  onClick={() => onDisposition(site.tooth, "withhold")}
                >
                  withhold
                </button>
              </span>
            ) : (
              <span data-role="disposition-default" className="disposition-default">
                released
              </span>
            )}
            {ackRequired(site, disposition) && (
              <label data-role="acknowledge-flag" className="assurance-ack">
                <input
                  type="checkbox"
                  checked={acknowledged}
                  onChange={(event) => onAcknowledge(site.tooth, event.target.checked)}
                />
                acknowledge this flag
              </label>
            )}
            <button
              type="button"
              data-role="row-expand"
              aria-expanded={expanded}
              className="button button--ghost button--small"
              onClick={() => onToggleExpand(site.tooth)}
            >
              {expanded ? "hide QC evidence" : "QC evidence"}
            </button>
          </div>
        </td>
      </tr>
      {expanded && (
        <tr data-role="qc-row" data-tooth={site.tooth} className="results-table__verification-row">
          <td colSpan={8}>
            <div className="verification-panel">
              <div className="verification-panel__images">
                {site.qc_images.map((name) => (
                  // lazy: six sites are 12 renders — the scroll must not fetch what
                  // the operator never opens (plan §4: images behind row-expand)
                  <figure key={name}>
                    <img
                      data-role="qc-image"
                      loading="lazy"
                      src={qcImageUrl(caseId, name)}
                      alt={`QC render ${name}`}
                    />
                    <figcaption>{name}</figcaption>
                  </figure>
                ))}
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export interface DeliverStageViewProps {
  readonly detail: CaseSessionDetail;
  readonly assurance: FetchState<AssuranceView>;
  readonly dispositions: DispositionMap;
  readonly acknowledged: readonly number[];
  readonly expanded: readonly number[];
  /** The report modal's own state (client 2026-07-27 #5) — the container owns it so
   * Esc and the backdrop can close it; the View renders it. */
  readonly reportOpen?: boolean;
  readonly phase?: DeliverPhase;
  /** A refusal that is NOT the drift 409 — rendered in the backend's words. */
  readonly actionError?: string | null;
  /** The evidence-drift 409's words — triggers the re-confirm flow's rendering. */
  readonly staleWords?: string | null;
  /** The gated artifact list's fetch state; null until a release exists. */
  readonly artifacts?: FetchState<ArtifactsView> | null;
  /** True while "download all" is walking the list one file at a time. */
  readonly downloadingAll?: boolean;
  readonly onDisposition: (tooth: number, act: Disposition) => void;
  readonly onAcknowledge: (tooth: number, on: boolean) => void;
  readonly onToggleExpand: (tooth: number) => void;
  readonly onOpenReport?: () => void;
  readonly onCloseReport?: () => void;
  readonly onConfirm: () => void;
  readonly onPay: () => void;
  readonly onRelease: () => void;
  readonly onReloadEvidence: () => void;
  readonly onDownload: (filename: string) => void;
  readonly onDownloadAll?: () => void;
}

/** The stage's whole surface, pure payload → markup — statically testable. */
export function DeliverStageView({
  detail,
  assurance,
  dispositions,
  acknowledged,
  expanded,
  reportOpen = false,
  phase = "idle",
  actionError = null,
  staleWords = null,
  artifacts = null,
  downloadingAll = false,
  onDisposition,
  onAcknowledge,
  onToggleExpand,
  onOpenReport = () => undefined,
  onCloseReport = () => undefined,
  onConfirm,
  onPay,
  onRelease,
  onReloadEvidence,
  onDownload,
  onDownloadAll = () => undefined,
}: DeliverStageViewProps) {
  const session = detail.session;
  // ONE derivation, read by the stage's confirm and the modal footer's alike
  const blockers =
    assurance.kind === "ok"
      ? confirmBlockers(assurance.data, dispositions, acknowledged)
      : [];
  const confirmable = assurance.kind === "ok" && blockers.length === 0 && phase === "idle";
  const steps = releaseSteps(session);
  const disclosure = releaseDisclosureWords(session.release_preview);
  const statusOf = (tooth: number): string =>
    detail.sites.find((s) => s.tooth === tooth)?.status ?? "unknown";
  const groups = artifacts?.kind === "ok" ? groupArtifacts(artifacts.data.files) : [];

  const confirmButton = (key: string) => (
    <button
      key={key}
      type="button"
      data-role="confirm"
      className="button button--primary"
      disabled={!confirmable}
      onClick={onConfirm}
    >
      Confirm over this evidence
    </button>
  );

  return (
    // Two regions for the workbench grid: the DELIVERY progression takes the work
    // column (it is the thing being driven); the evidence takes the stage.
    <div data-role="deliver-stage" className="stage-contents">
      <div className="workbench__work">
        {/* the 409 re-confirm flow: the BFF's words + the one honest next move —
            amber: the evidence moved, nothing failed */}
        {staleWords !== null && (
          <div data-role="reconfirm" role="alert" className="switch-confirm">
            <p className="switch-confirm__words">{staleWords}</p>
            <div className="switch-confirm__actions">
              <button
                type="button"
                className="button button--secondary button--small"
                onClick={onReloadEvidence}
              >
                Reload the evidence to re-confirm
              </button>
            </div>
          </div>
        )}

        <section className="panel">
          <h3 className="panel__title">Delivery</h3>
          {/* THE VISIBLE PROGRESSION (client 2026-07-27 #6): three steps, each
              stating what it is — done with its time, current with its act, waiting
              with what it needs. No step is ever inert without saying why. */}
          <ol data-role="release-steps" className="release-steps">
            {steps.map((step, index) => (
              <li
                key={step.id}
                data-role="release-step"
                data-step={step.id}
                data-state={step.state}
                className={`release-step release-step--${step.state}`}
              >
                <span className="release-step__marker" aria-hidden="true">
                  {step.state === "done" ? "✓" : index + 1}
                </span>
                <div className="release-step__body">
                  <strong className="release-step__title">{step.title}</strong>
                  <span className="release-step__detail">{step.detail}</span>

                  {step.id === "confirmed" && step.state === "current" && (
                    <div className="release-step__actions">
                      {confirmButton("step-confirm")}
                    </div>
                  )}
                  {step.id === "confirmed" && <ConfirmBlockers blockers={blockers} />}

                  {step.id === "paid" && step.state === "current" && (
                    <div className="release-step__actions">
                      {/* labelled AS a stub, in words, on the control itself —
                          the record says provider "stub" for the same reason */}
                      <button
                        type="button"
                        data-role="payment-stub"
                        className="button button--secondary"
                        disabled={phase !== "idle"}
                        onClick={onPay}
                      >
                        Authorize payment (stub) — {detail.sites.length} site
                        {detail.sites.length === 1 ? "" : "s"} on case{" "}
                        {detail.case.id}
                      </button>
                      <p data-role="payment-stub-note" className="panel__hint">
                        A STUB: no provider is contacted and no money moves. The record
                        says so permanently (provider “stub”), so a stub-authorized
                        case stays tellable from a paid one once a real provider lands.
                      </p>
                    </div>
                  )}

                  {step.id === "released" && step.state === "current" && (
                    <div className="release-step__actions">
                      {/* what will be disclosed, BEFORE the act */}
                      {disclosure.length > 0 && (
                        <div data-role="release-disclosure" className="disclosure-note">
                          {disclosure.map((line) => (
                            <p key={line} className="disclosure-note__line">
                              {line}
                            </p>
                          ))}
                        </div>
                      )}
                      <button
                        type="button"
                        data-role="release"
                        className="button button--primary"
                        disabled={phase !== "idle"}
                        onClick={onRelease}
                      >
                        Release the artifacts
                      </button>
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </section>

        {session.released && artifacts !== null && (
          <section
            data-role="artifacts"
            aria-label="Released artifacts"
            className="panel"
          >
            <h3 className="panel__title">Artifacts</h3>
            {artifacts.kind === "loading" && (
              <p className="panel__hint">Listing the released artifacts…</p>
            )}
            {artifacts.kind === "error" && (
              <div data-role="artifacts-error" role="alert" className="panel__error">
                {artifacts.detail}
              </div>
            )}
            {artifacts.kind === "ok" && (
              <>
                <div className="panel__actions">
                  <button
                    type="button"
                    data-role="download-all"
                    className="button button--secondary button--small"
                    disabled={downloadingAll || artifacts.data.files.length === 0}
                    onClick={onDownloadAll}
                  >
                    {downloadingAll
                      ? "Downloading…"
                      : `Download all ${artifacts.data.files.length} files`}
                  </button>
                </div>
                {/* GROUPED BY SITE (client 2026-07-27 #6): a six-site package is
                    thirty near-identical names otherwise. The server attributed each
                    file — this only renders the buckets. */}
                {groups.map((group) => (
                  <div
                    key={group.tooth ?? "case-wide"}
                    data-role="artifact-group"
                    data-tooth={group.tooth ?? "case-wide"}
                    className="artifact-group"
                  >
                    <h4 className="artifact-group__title">
                      {group.title}{" "}
                      <span className="artifact-group__meta">
                        {group.files.length} file{group.files.length === 1 ? "" : "s"} ·{" "}
                        {formatBytes(group.totalBytes)}
                      </span>
                    </h4>
                    <ul className="package-files__list">
                      {group.files.map((file) => (
                        <li key={file.name} className="package-files__item">
                          {/* the endpoint is release-gated and answers refusals in
                              JSON, so the download is a fetch, never a bare href */}
                          <button
                            type="button"
                            data-role="artifact-download"
                            data-file={file.name}
                            className="package-files__link"
                            onClick={() => onDownload(file.name)}
                          >
                            {file.name}
                          </button>{" "}
                          <span className="artifact-group__size">
                            {formatBytes(file.size_bytes)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
                {artifacts.data.withheld_teeth.map((tooth) => (
                  <p key={tooth} data-role="withheld-site" className="withheld-note">
                    Tooth {tooth} — withheld; its files are not in the released set
                    and the site stays open ({statusOf(tooth)}).
                  </p>
                ))}
                {/* the BFF holds case-wide files back while any site is withheld
                    (they aggregate every site); the surface names each one so a
                    partial release never masquerades as the whole package */}
                {artifacts.data.withheld_case_files.length > 0 && (
                  <p data-role="withheld-case-files" className="withheld-note">
                    Held back with the withheld sites — case-wide files release only
                    when every site does: {artifacts.data.withheld_case_files.join(", ")}
                  </p>
                )}
              </>
            )}
          </section>
        )}

        {phase !== "idle" && (
          <div data-role="deliver-phase" className="busy-state" role="status">
            <span className="busy-state__spinner" aria-hidden="true" />
            <span>{PHASE_WORDS[phase]}</span>
          </div>
        )}
        {actionError !== null && (
          <div data-role="deliver-error" role="alert" className="panel__error">
            {actionError}
          </div>
        )}
      </div>

      <div className="workbench__stage">
        <section className="panel deliver-evidence" aria-label="Assurance evidence">
          <h3 className="panel__title">
            Assurance — worst first
            <span className="panel__title-case"> · {detail.case.id}</span>
          </h3>
          {assurance.kind === "loading" && (
            <div data-role="assurance-loading" className="busy-state" role="status">
              <span className="busy-state__spinner" aria-hidden="true" />
              <span>Loading the run’s assurance evidence…</span>
            </div>
          )}
          {assurance.kind === "error" && (
            <div data-role="assurance-error" role="alert" className="panel__error">
              {assurance.detail}
            </div>
          )}
          {assurance.kind === "ok" && (
            <>
              {/* THE COMPACT SUMMARY (client 2026-07-27 #5): enough that opening the
                  report is a decision, not a hunt. Served order, verbatim. */}
              <ul data-role="evidence-summary" className="evidence-summary">
                {evidenceSummary(assurance.data).map((line) => (
                  <li
                    key={line.tooth}
                    data-role="evidence-line"
                    data-tooth={line.tooth}
                    data-flagged={line.flagged}
                    className={`evidence-summary__line${
                      line.flagged ? " evidence-summary__line--flagged" : ""
                    }`}
                  >
                    <span className="evidence-summary__site">Tooth {line.tooth}</span>{" "}
                    <span data-role="gate-level" className={gateChipClass(line.gate)}>
                      {line.gate}
                    </span>{" "}
                    <span className="evidence-summary__words">{line.words}</span>
                  </li>
                ))}
              </ul>
              <div className="panel__actions">
                <button
                  type="button"
                  data-role="open-report"
                  className="button button--primary"
                  onClick={onOpenReport}
                >
                  Open the full report
                </button>
                {/* reachable from the stage too, once nothing is outstanding —
                    the same act, the same one blocker list beneath it */}
                {!session.confirmed && confirmButton("stage-confirm")}
              </div>
              <ConfirmBlockers blockers={blockers} />
            </>
          )}
        </section>
      </div>

      {/* THE REPORT MODAL (client 2026-07-27 #5) — the demo's dialog chrome: a fixed
          backdrop, a full-height card, header / scrolling body / acknowledgment-bar
          footer. Closes on Esc (the container binds it) and on the backdrop. */}
      {reportOpen && assurance.kind === "ok" && (
        <div
          data-role="report-backdrop"
          className="decode-dialog-backdrop"
          onClick={onCloseReport}
        >
          <section
            data-role="report-dialog"
            className="decode-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="report-dialog-heading"
            // the card is not the backdrop: a click inside must not dismiss
            onClick={(event) => event.stopPropagation()}
          >
            <header className="decode-dialog__header">
              <div>
                <h2 id="report-dialog-heading" className="decode-dialog__title">
                  Assurance report — worst first
                </h2>
                <p className="decode-dialog__subject">
                  {detail.case.id} · {detail.case.doctor} · run{" "}
                  {assurance.data.run_id}
                </p>
              </div>
              <button
                type="button"
                data-role="report-close"
                className="button button--ghost button--small"
                onClick={onCloseReport}
                title="Close the report (Esc)"
              >
                ✕ close
              </button>
            </header>
            <div className="decode-dialog__body decode-dialog__body--column-collapsed">
              <div className="results-table-scroll">
                <table data-role="assurance-table" className="results-table">
                  <thead>
                    <tr>
                      <th>Site</th>
                      <th>Identity</th>
                      <th>Seat</th>
                      <th>Rotation</th>
                      <th>Deviation</th>
                      <th>Gate</th>
                      <th>Relief</th>
                      <th>Disposition</th>
                    </tr>
                  </thead>
                  <tbody>
                    {assurance.data.sites.map((site) => (
                      <AssuranceRow
                        key={site.tooth}
                        caseId={detail.case.id}
                        site={site}
                        disposition={effectiveDisposition(site, dispositions)}
                        acknowledged={acknowledged.includes(site.tooth)}
                        expanded={expanded.includes(site.tooth)}
                        onDisposition={onDisposition}
                        onAcknowledge={onAcknowledge}
                        onToggleExpand={onToggleExpand}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <footer className="decode-ack">
              <div className="decode-ack__text">
                {session.confirmed && session.confirmation !== null ? (
                  <p data-role="sealed-confirmation" className="sealed-note">
                    Confirmed at {session.confirmation.at} — evidence{" "}
                    <code>{session.confirmation.evidence_sha256}</code>
                  </p>
                ) : (
                  <p className="decode-ack__disclaimer">
                    Confirming seals these rows and the QC images behind them; release
                    re-derives all of it and refuses on any change.
                  </p>
                )}
                <ConfirmBlockers blockers={blockers} />
              </div>
              <div className="decode-ack__actions">
                <button
                  type="button"
                  className="button button--secondary"
                  onClick={onCloseReport}
                >
                  Close
                </button>
                {confirmButton("modal-confirm")}
              </div>
            </footer>
          </section>
        </div>
      )}
    </div>
  );
}

export interface DeliverStageProps {
  readonly detail: CaseSessionDetail;
  /** The shell owns the payload; every action's response replaces it whole. */
  readonly onDetail: (next: CaseSessionDetail) => void;
}

/** The container: the evidence fetch, the modal's own state (Esc closes it), the
 * local acts (dispositions/acknowledgments/expands), and the three gated POSTs. */
export function DeliverStage({ detail, onDetail }: DeliverStageProps) {
  const caseId = detail.case.id;
  const mountedRef = useRef(true);
  const [assurance, setAssurance] = useState<FetchState<AssuranceView>>({
    kind: "loading",
  });
  const [dispositions, setDispositions] = useState<DispositionMap>({});
  const [acknowledged, setAcknowledged] = useState<readonly number[]>([]);
  const [expanded, setExpanded] = useState<readonly number[]>([]);
  const [reportOpen, setReportOpen] = useState(false);
  const [phase, setPhase] = useState<DeliverPhase>("idle");
  const [actionError, setActionError] = useState<string | null>(null);
  const [staleWords, setStaleWords] = useState<string | null>(null);
  const [artifacts, setArtifacts] = useState<FetchState<ArtifactsView> | null>(null);
  const [downloadingAll, setDownloadingAll] = useState(false);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // Esc closes the report — bound only while it is open, so the key means nothing
  // when there is no dialog to dismiss
  useEffect(() => {
    if (!reportOpen) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setReportOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [reportOpen]);

  const reloadEvidence = useCallback(() => {
    setAssurance({ kind: "loading" });
    setStaleWords(null);
    // stale acts must not survive a reload: the operator re-reads what is
    // actually there and dispositions again (the re-confirm flow's honesty)
    setDispositions({});
    setAcknowledged([]);
    void fetchAssurance(caseId).then((result) => {
      if (mountedRef.current) setAssurance(result);
    });
  }, [caseId]);

  // the evidence loads with the stage and re-loads if a NEW run lands underneath
  const runState = detail.session.run_state;
  useEffect(() => {
    setAssurance({ kind: "loading" });
    void fetchAssurance(caseId).then((result) => {
      if (mountedRef.current) setAssurance(result);
    });
  }, [caseId, runState]);

  // once released, the gated list is fetched — the release record is the gate
  const released = detail.session.released;
  useEffect(() => {
    if (!released) {
      setArtifacts(null);
      return;
    }
    setArtifacts({ kind: "loading" });
    void fetchArtifacts(caseId).then((result) => {
      if (mountedRef.current) setArtifacts(result);
    });
  }, [caseId, released]);

  const handleDisposition = useCallback((tooth: number, act: Disposition) => {
    setDispositions((current) => ({ ...current, [tooth]: act }));
    if (act === "withhold") {
      // a withheld site has no release to acknowledge — drop a stale tick
      setAcknowledged((current) => current.filter((t) => t !== tooth));
    }
  }, []);

  const handleAcknowledge = useCallback((tooth: number, on: boolean) => {
    setAcknowledged((current) =>
      on ? [...current.filter((t) => t !== tooth), tooth] : current.filter((t) => t !== tooth),
    );
  }, []);

  const handleToggleExpand = useCallback((tooth: number) => {
    setExpanded((current) =>
      current.includes(tooth)
        ? current.filter((t) => t !== tooth)
        : [...current, tooth],
    );
  }, []);

  /** One settling rule for all three gated POSTs: the response detail replaces the
   * payload; the drift 409 opens the re-confirm flow; any other refusal renders
   * in the backend's words. */
  const settle = useCallback(
    (result: Awaited<ReturnType<typeof postRelease>>) => {
      if (!mountedRef.current) return;
      setPhase("idle");
      if (result.kind === "ok") {
        setActionError(null);
        setStaleWords(null);
        onDetail(result.data);
      } else if (isEvidenceDrift409(result)) {
        setStaleWords(result.detail);
      } else {
        setActionError(result.detail);
      }
    },
    [onDetail],
  );

  const handleConfirm = useCallback(() => {
    setPhase("confirming");
    // the report closes on a confirmation: the reading is done, and the progression
    // the operator just advanced is on the stage behind it
    setReportOpen(false);
    void postConfirm(caseId, confirmWireBody(dispositions, acknowledged)).then(settle);
  }, [caseId, dispositions, acknowledged, settle]);

  const handlePay = useCallback(() => {
    setPhase("paying");
    void postPayment(caseId).then(settle);
  }, [caseId, settle]);

  const handleRelease = useCallback(() => {
    setPhase("releasing");
    void postRelease(caseId).then(settle);
  }, [caseId, settle]);

  const downloadOne = useCallback(
    async (filename: string): Promise<boolean> => {
      const result = await fetchArtifactBlob(caseId, filename);
      if (!mountedRef.current) return false;
      if (result.kind === "error") {
        setActionError(result.detail);
        return false;
      }
      const url = URL.createObjectURL(result.data);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.click();
      URL.revokeObjectURL(url);
      return true;
    },
    [caseId],
  );

  const handleDownload = useCallback(
    (filename: string) => {
      void downloadOne(filename);
    },
    [downloadOne],
  );

  /** "Download all" walks the list SEQUENTIALLY — each file is a gated fetch, and
   * firing a dozen at once would race the browser's download prompts and bury any
   * single refusal in the pile. One at a time, stopping at the first refusal, whose
   * words render like every other. */
  const handleDownloadAll = useCallback(() => {
    const listed = artifacts?.kind === "ok" ? artifacts.data.files : [];
    setDownloadingAll(true);
    void (async () => {
      for (const file of listed) {
        const ok = await downloadOne(file.name);
        if (!mountedRef.current) return;
        if (!ok) break;
      }
      if (mountedRef.current) setDownloadingAll(false);
    })();
  }, [artifacts, downloadOne]);

  return (
    <DeliverStageView
      detail={detail}
      assurance={assurance}
      dispositions={dispositions}
      acknowledged={acknowledged}
      expanded={expanded}
      reportOpen={reportOpen}
      phase={phase}
      actionError={actionError}
      staleWords={staleWords}
      artifacts={artifacts}
      downloadingAll={downloadingAll}
      onDisposition={handleDisposition}
      onAcknowledge={handleAcknowledge}
      onToggleExpand={handleToggleExpand}
      onOpenReport={() => setReportOpen(true)}
      onCloseReport={() => setReportOpen(false)}
      onConfirm={handleConfirm}
      onPay={handlePay}
      onRelease={handleRelease}
      onReloadEvidence={reloadEvidence}
      onDownload={handleDownload}
      onDownloadAll={handleDownloadAll}
    />
  );
}
