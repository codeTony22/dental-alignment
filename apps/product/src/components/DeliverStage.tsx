/**
 * DELIVER (plan §4 Deliver, slice 8; grill AM-1/AM-10/AM-11/AM-12): the assurance
 * table — worst-first exactly as the BFF SERVES it (flags pinned; this app never
 * re-sorts evidence) — with row-expand QC images from the ungated evidence
 * endpoint, per-row dispositions, the per-flag acknowledgment tick, the confirm
 * button inert until complete (each missing piece named under it — flow.ts's
 * blockedReason doctrine at a button), the sealed state, the payment button
 * labelled AS a stub, release, and the gated artifact list with withheld sites
 * shown as withheld beside their open status.
 *
 * Direction of trust (AM-4): optimism is OFF. Every POST's response is the whole
 * new detail, replacing the payload verbatim (onDetail); refusals render in the
 * backend's own words. The evidence-drift 409 ("the case changed since it was
 * confirmed") gets its own flow: the surface offers to RELOAD the evidence and
 * asks the operator again — never a silent retry over stale numbers.
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
  isEvidenceDrift409,
  loadOperator,
  releaseBlockers,
  saveOperator,
  type Disposition,
  type DispositionMap,
} from "../domain/deliver";

export type DeliverPhase = "idle" | "confirming" | "paying" | "releasing";

const PHASE_WORDS: Readonly<Record<Exclude<DeliverPhase, "idle">, string>> = {
  confirming: "Sealing the confirmation…",
  paying: "Recording the (stub) payment authorization…",
  releasing: "Releasing — re-deriving the evidence…",
};

interface AssuranceRowProps {
  readonly caseId: string;
  readonly site: AssuranceSite;
  readonly disposition: Disposition | undefined;
  readonly acknowledged: boolean;
  readonly expanded: boolean;
  readonly onDisposition: (tooth: number, act: Disposition) => void;
  readonly onAcknowledge: (tooth: number, on: boolean) => void;
  readonly onToggleExpand: (tooth: number) => void;
}

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
  readonly operatorName: string;
  readonly dispositions: DispositionMap;
  readonly acknowledged: readonly number[];
  readonly expanded: readonly number[];
  readonly phase?: DeliverPhase;
  /** A refusal that is NOT the drift 409 — rendered in the backend's words. */
  readonly actionError?: string | null;
  /** The evidence-drift 409's words — triggers the re-confirm flow's rendering. */
  readonly staleWords?: string | null;
  /** The gated artifact list's fetch state; null until a release exists. */
  readonly artifacts?: FetchState<ArtifactsView> | null;
  readonly onOperatorName: (name: string) => void;
  readonly onDisposition: (tooth: number, act: Disposition) => void;
  readonly onAcknowledge: (tooth: number, on: boolean) => void;
  readonly onToggleExpand: (tooth: number) => void;
  readonly onConfirm: () => void;
  readonly onPay: () => void;
  readonly onRelease: () => void;
  readonly onReloadEvidence: () => void;
  readonly onDownload: (filename: string) => void;
}

/** The stage's whole surface, pure payload → markup — statically testable. */
export function DeliverStageView({
  detail,
  assurance,
  operatorName,
  dispositions,
  acknowledged,
  expanded,
  phase = "idle",
  actionError = null,
  staleWords = null,
  artifacts = null,
  onOperatorName,
  onDisposition,
  onAcknowledge,
  onToggleExpand,
  onConfirm,
  onPay,
  onRelease,
  onReloadEvidence,
  onDownload,
}: DeliverStageViewProps) {
  const session = detail.session;
  const blockers =
    assurance.kind === "ok"
      ? confirmBlockers(assurance.data, dispositions, acknowledged, operatorName)
      : [];
  const releaseMissing = releaseBlockers(session);
  const statusOf = (tooth: number): string =>
    detail.sites.find((s) => s.tooth === tooth)?.status ?? "unknown";
  return (
    // Two regions for the workbench grid: the EVIDENCE takes the stage (the demo's
    // drawer doctrine — wide output takes the stage's width and scrolls inside its
    // own panel); the disclosure chain lives in the work column.
    <div data-role="deliver-stage" className="stage-contents">
      <div className="workbench__work">
        <section className="panel">
          <h3 className="panel__title">Operator</h3>
          <label data-role="operator-field" className="operator-field">
            Operator name — the confirmation, payment and release records name you:
            <input
              data-role="operator-name"
              className="operator-field__input"
              value={operatorName}
              onChange={(event) => onOperatorName(event.target.value)}
              placeholder="your name"
            />
          </label>
        </section>

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
          <h3 className="panel__title">Confirm</h3>
          {session.confirmed && session.confirmation !== null && (
            <div data-role="sealed-confirmation" className="sealed-note">
              Confirmed by {session.confirmation.operator} at {session.confirmation.at} —
              evidence <code>{session.confirmation.evidence_sha256}</code>
            </div>
          )}
          <div data-role="confirm-controls" className="panel__actions">
            <button
              type="button"
              data-role="confirm"
              className="button button--primary"
              disabled={assurance.kind !== "ok" || blockers.length > 0 || phase !== "idle"}
              onClick={onConfirm}
            >
              Confirm over this evidence
            </button>
          </div>
          {blockers.length > 0 && (
            <ul data-role="confirm-blockers" className="blocker-list">
              {blockers.map((piece) => (
                <li key={piece}>{piece}</li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel">
          <h3 className="panel__title">Payment</h3>
          {session.payment_authorized && session.payment !== null ? (
            <p data-role="payment-done" className="sealed-note">
              Payment authorized ({session.payment.provider}) by {session.payment.operator}{" "}
              at {session.payment.at}
            </p>
          ) : (
            <>
              {/* labelled AS a stub (AM-11): the button never pretends a provider */}
              <div className="panel__actions">
                <button
                  type="button"
                  data-role="payment-stub"
                  className="button button--secondary"
                  disabled={!session.confirmed || phase !== "idle"}
                  onClick={onPay}
                >
                  Authorize payment (stub)
                </button>
              </div>
              {!session.confirmed && (
                <p data-role="payment-blocked" className="panel__hint">
                  Confirm over the evidence first.
                </p>
              )}
            </>
          )}
        </section>

        <section className="panel">
          <h3 className="panel__title">Release</h3>
          {session.released && session.release !== null ? (
            <div data-role="released" className="sealed-note">
              Released by {session.release.operator} at {session.release.at} — evidence{" "}
              <code>{session.release.evidence_sha256}</code>
            </div>
          ) : (
            <>
              <div className="panel__actions">
                <button
                  type="button"
                  data-role="release"
                  className="button button--primary"
                  disabled={releaseMissing.length > 0 || phase !== "idle"}
                  onClick={onRelease}
                >
                  Release the artifacts
                </button>
              </div>
              {releaseMissing.length > 0 && (
                <ul data-role="release-blockers" className="blocker-list">
                  {releaseMissing.map((piece) => (
                    <li key={piece}>{piece}</li>
                  ))}
                </ul>
              )}
            </>
          )}

          {session.released && artifacts !== null && (
            <section data-role="artifacts" aria-label="Released artifacts">
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
                  <h4 className="package-files__title">Released files</h4>
                  <ul data-role="artifact-list" className="package-files__list">
                    {artifacts.data.files.map((file) => (
                      <li key={file} className="package-files__item">
                        {/* the gated endpoint needs the operator header, so the
                            download is a fetch, never a bare <a href> */}
                        <button
                          type="button"
                          data-role="artifact-download"
                          data-file={file}
                          className="package-files__link"
                          onClick={() => onDownload(file)}
                        >
                          {file}
                        </button>
                      </li>
                    ))}
                  </ul>
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
        </section>

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
                      disposition={dispositions[site.tooth]}
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
          )}
        </section>
      </div>
    </div>
  );
}

export interface DeliverStageProps {
  readonly detail: CaseSessionDetail;
  /** The shell owns the payload; every action's response replaces it whole. */
  readonly onDetail: (next: CaseSessionDetail) => void;
}

const sessionStorageOrNull = (): Storage | null =>
  typeof window === "undefined" ? null : window.sessionStorage;

/** The container: the evidence fetch, the operator's persisted name, the local
 * acts (dispositions/acknowledgments/expands), and the three gated POSTs. */
export function DeliverStage({ detail, onDetail }: DeliverStageProps) {
  const caseId = detail.case.id;
  const mountedRef = useRef(true);
  const [assurance, setAssurance] = useState<FetchState<AssuranceView>>({
    kind: "loading",
  });
  const [operatorName, setOperatorName] = useState(() =>
    loadOperator(sessionStorageOrNull()),
  );
  const [dispositions, setDispositions] = useState<DispositionMap>({});
  const [acknowledged, setAcknowledged] = useState<readonly number[]>([]);
  const [expanded, setExpanded] = useState<readonly number[]>([]);
  const [phase, setPhase] = useState<DeliverPhase>("idle");
  const [actionError, setActionError] = useState<string | null>(null);
  const [staleWords, setStaleWords] = useState<string | null>(null);
  const [artifacts, setArtifacts] = useState<FetchState<ArtifactsView> | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

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

  // once released, the gated list is fetched with the operator's name on it
  const released = detail.session.released;
  useEffect(() => {
    if (!released) {
      setArtifacts(null);
      return;
    }
    setArtifacts({ kind: "loading" });
    void fetchArtifacts(caseId, operatorName).then((result) => {
      if (mountedRef.current) setArtifacts(result);
    });
  }, [caseId, released, operatorName]);

  const handleOperatorName = useCallback((name: string) => {
    setOperatorName(name);
    saveOperator(sessionStorageOrNull(), name);
  }, []);

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
    void postConfirm(
      caseId,
      operatorName,
      confirmWireBody(dispositions, acknowledged),
    ).then(settle);
  }, [caseId, operatorName, dispositions, acknowledged, settle]);

  const handlePay = useCallback(() => {
    setPhase("paying");
    void postPayment(caseId, operatorName).then(settle);
  }, [caseId, operatorName, settle]);

  const handleRelease = useCallback(() => {
    setPhase("releasing");
    void postRelease(caseId, operatorName).then(settle);
  }, [caseId, operatorName, settle]);

  const handleDownload = useCallback(
    (filename: string) => {
      void fetchArtifactBlob(caseId, filename, operatorName).then((result) => {
        if (!mountedRef.current) return;
        if (result.kind === "error") {
          setActionError(result.detail);
          return;
        }
        const url = URL.createObjectURL(result.data);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = filename;
        anchor.click();
        URL.revokeObjectURL(url);
      });
    },
    [caseId, operatorName],
  );

  return (
    <DeliverStageView
      detail={detail}
      assurance={assurance}
      operatorName={operatorName}
      dispositions={dispositions}
      acknowledged={acknowledged}
      expanded={expanded}
      phase={phase}
      actionError={actionError}
      staleWords={staleWords}
      artifacts={artifacts}
      onOperatorName={handleOperatorName}
      onDisposition={handleDisposition}
      onAcknowledge={handleAcknowledge}
      onToggleExpand={handleToggleExpand}
      onConfirm={handleConfirm}
      onPay={handlePay}
      onRelease={handleRelease}
      onReloadEvidence={reloadEvidence}
      onDownload={handleDownload}
    />
  );
}
