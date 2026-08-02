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
 * never be two answers about whether this case is confirmable. The FORK'S DECISION
 * (review 2026-07-28) travels the same way: the BFF folds "skipped" or "taken up"
 * into the evidence hash a confirmation covers, so the word is stated in words
 * beside each of those two places — a hash the operator cannot read is not a thing
 * they can be said to have seen.
 *
 * Direction of trust (AM-4): optimism is OFF. Every POST's response is the whole new
 * detail, replacing the payload verbatim (onDetail); refusals render in the backend's
 * own words. The evidence-drift 409 ("the case changed since it was confirmed") keeps
 * its own flow: reload the evidence and ask again — never a silent retry.
 */
import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { useDialogEscape } from "./useDialogEscape";
import { CheckoutDialog } from "../pages/CheckoutPage";
import { DeliverPreview } from "./DeliverPreview";
import {
  fetchArtifactBlob,
  fetchArtifacts,
  fetchAssurance,
  fetchInvoice,
  fetchRun,
  postConfirm,
  postDeliveryReset,
  postRelease,
  putChoices,
  qcImageUrl,
  type ArtifactsView,
  type AssuranceSite,
  type AssuranceView,
  type CaseSessionDetail,
  type FetchState,
  type InvoiceView,
  type RunFactsView,
} from "../api/client";
import { choicesUpdateFrom, constructionOptions } from "../domain/intake";
import {
  ATTESTATION_PENDING_CAVEAT,
  CHECKOUT_SEAL_WORDS,
  CLINICAL_TERMS_VERSION,
  ackRequired,
  attestationText,
  acknowledgmentPolicyWords,
  adjustmentsWords,
  assuranceCountsWords,
  confirmBlockers,
  confirmWireBody,
  constructionChangeRetiresSomething,
  constructionChangeWords,
  constructionGroups,
  constructionStepWords,
  effectiveDisposition,
  evidenceSummary,
  formatBytes,
  groupArtifacts,
  invoiceIsPlaceholder,
  isEvidenceDrift409,
  needsAcknowledgment,
  orderLines,
  orderTotal,
  previewTabs,
  receiptWords,
  releaseDisclosureWords,
  releaseSteps,
  releasedClosingWords,
  sealedTermsHref,
  staleMetricsWords,
  crossCheckWords,
  turnaroundWords,
  withholdOffered,
  type ConstructionGroup,
  type ConstructionOption,
  type ConstructionStepInfo,
  type Disposition,
  type DispositionMap,
  qcPreviews,
} from "../domain/deliver";

export type DeliverPhase = "idle" | "confirming" | "resetting" | "releasing";

const PHASE_WORDS: Readonly<Record<Exclude<DeliverPhase, "idle">, string>> = {
  confirming: "Sealing the confirmation…",
  resetting: "Withdrawing the confirmation, payment and release…",
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

/** THE FORK, STATED WHEREVER THE CONFIRM IS (review 2026-07-28). Same discipline as
 * the blocker list: one derivation, one renderer, beside each of the two places the
 * surface offers to sign — the decision is inside the hash the signature covers, so
 * it must be legible before the signature, not only after a dispute. */
function AdjustmentsNote({ words }: { readonly words: string }) {
  return (
    <p data-role="adjustments-note" className="panel__hint">
      {words}
    </p>
  );
}

/** THE AGREEMENT, WHEREVER THE CONFIRM IS (plan §10-A: "confirm and accept
 * terms" is one act). Same discipline as ``ConfirmBlockers``/``AdjustmentsNote``
 * — one derivation, one renderer, beside each of the two places the surface
 * offers to sign, so the checkbox and the button can never be in the same
 * place. The placeholder banner is UNMISSABLE on purpose (client 2026-07-27's
 * own rule for the payment stub, applied to the terms text too): the real
 * legal language is the client's to supply. */
function TermsAcceptance({
  siteCount,
  invoice,
  accepted,
  disabled,
  onChange,
}: {
  readonly siteCount: number;
  /** The derived invoice, whose line quantities ARE the enumeration (gap
   *  ``clinical-responsibility-attestation``) — null until it lands, and then the
   *  sentence falls back to the site count rather than claiming zero. */
  readonly invoice: InvoiceView | null;
  readonly accepted: boolean;
  readonly disabled: boolean;
  readonly onChange: (accepted: boolean) => void;
}) {
  return (
    <div data-role="terms-acceptance" className="terms-block">
      <p data-role="terms-placeholder-banner" className="terms-block__placeholder">
        PLACEHOLDER — pending the client&rsquo;s final Terms and Conditions text.
      </p>
      <label className="terms-block__label">
        <input
          type="checkbox"
          data-role="terms-checkbox"
          checked={accepted}
          disabled={disabled}
          onChange={(event) => onChange(event.target.checked)}
        />
        <span data-role="terms-text">
          {/* THE SENTENCE NAMES WHAT IS BEING RELEASED (gap
              ``clinical-responsibility-attestation``, 2026-07-31). It used to name a
              site count and nothing else — never the sites released under
              acknowledgment, never the withheld — so the signature covered a state of
              affairs the words declined to describe. Every count in it is the BFF's
              (the invoice's own line quantities, classified by the same
              ``_needs_acknowledgment`` predicate this confirm gate stands on). */}
          {attestationText(invoice, siteCount)}{" "}
          {/* THE TERMS ARE A LINK (client 2026-07-30). A NEW TAB, deliberately:
              reading the agreement must never cost the operator the confirmation
              they are part-way through — and a legal document wants a URL you can
              print, save or send on, which is why this is a route and not another
              modal. /terms serves the CURRENT version — the same server constant
              a new acceptance records — so what is read and what gets sealed
              cannot be different documents. */}
          <a
            data-role="terms-link"
            className="terms-block__link"
            href="/terms"
            target="_blank"
            rel="noreferrer"
          >
            Read the Terms and Conditions ↗
          </a>{" "}
          {/* THE SECOND DOCUMENT (gap ``clinical-responsibility-attestation``). The
              terms INCORPORATE it by version rather than asking for a second tick:
              one signature, sealed once, with both texts resolvable from it. */}
          <a
            data-role="clinical-terms-link"
            className="terms-block__link"
            href={`/terms/${encodeURIComponent(CLINICAL_TERMS_VERSION)}`}
            target="_blank"
            rel="noreferrer"
          >
            Read the Clinical Responsibility Statement ↗
          </a>
        </span>
      </label>
      {invoice !== null && (
        <p data-role="attestation-caveat" className="terms-block__caveat">
          {ATTESTATION_PENDING_CAVEAT}
        </p>
      )}
    </div>
  );
}

interface ConstructionStepProps {
  /** The effective construction, resolved against the picker's own rows — the
   *  server's value and attribution, never re-derived here. */
  readonly info: ConstructionStepInfo;
  readonly groups: readonly ConstructionGroup[];
  readonly editing: boolean;
  /** A candidate picked but not yet confirmed — null until the operator chooses
   *  something OTHER than the effective construction. */
  readonly pending: string | null;
  readonly saving: boolean;
  readonly error: string | null;
  /** Whether a confirmation is standing to fall — feeds constructionChangeWords so
   *  the blast-radius sentence never claims a consequence that is not real. */
  readonly confirmed: boolean;
  readonly onEdit: () => void;
  readonly onCancelEdit: () => void;
  readonly onPick: (pathId: string) => void;
  readonly onCancelPending: () => void;
  readonly onConfirmChange: () => void;
}

/**
 * THE CONSTRUCTION STEP (client 2026-08-01: "we also forgot the selection of the
 * construction, and we need to put the construction library after the Confirmation
 * in the Delivery step"). Positioned as its OWN `<li>` between Confirmed and Paid in
 * the release ladder's `<ol>` (DeliverStageView, below) — not folded into
 * `releaseSteps`'s done/current/waiting state machine, because this step is never
 * "finished": the effective construction is always shown and always changeable, so
 * giving it a state would either freeze the ladder's "exactly one current step"
 * invariant or contradict it.
 *
 * The picker is a SECOND copy of Intake's own construction select — reusing
 * `domain/intake.constructionOptions`/`domain/deliver.constructionGroups`, never a
 * second catalog reader — because the client's own ask was to put the library HERE
 * too, not to remove it from Intake.
 */
function ConstructionStep({
  info,
  groups,
  editing,
  pending,
  saving,
  error,
  confirmed,
  onEdit,
  onCancelEdit,
  onPick,
  onCancelPending,
  onConfirmChange,
}: ConstructionStepProps) {
  const pendingOption: ConstructionOption | null =
    pending !== null
      ? groups.flatMap((group) => group.options).find((option) => option.path_id === pending) ??
        null
      : null;
  return (
    <li
      data-role="release-step"
      data-step="construction"
      className="release-step release-step--construction"
    >
      <span className="release-step__marker" aria-hidden="true">
        ⚙
      </span>
      <div className="release-step__body">
        <strong className="release-step__title">Construction</strong>
        <span data-role="construction-current" className="release-step__detail">
          {info.pathId === null ? (
            info.label
          ) : (
            <>
              {info.label}
              {info.vendor !== null && <> · {info.vendor}</>}
              {info.suggested && (
                <span
                  data-role="construction-suggested"
                  className="library-badge library-badge--suggested"
                >
                  {" "}
                  suggested
                </span>
              )}
            </>
          )}
        </span>
        {!editing && (
          <div className="release-step__actions">
            <button
              type="button"
              data-role="construction-edit"
              className="button button--ghost button--small"
              onClick={onEdit}
            >
              Change construction part
            </button>
          </div>
        )}
        {editing && (
          <div className="release-step__actions construction-edit">
            <select
              data-role="construction-select"
              aria-label="Construction part"
              className="decode-select"
              value={pending ?? info.pathId ?? ""}
              disabled={saving}
              onChange={(event) => onPick(event.target.value)}
            >
              <option value="">choose a construction part…</option>
              {groups.map((group) => (
                <optgroup key={group.vendor} label={group.vendor}>
                  {group.options.map((option) => (
                    <option key={option.path_id} value={option.path_id}>
                      {option.label}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            {/* THE BLAST RADIUS, BEFORE THE PUT (the visible-reset doctrine —
                DeclareStage's SwitchConfirm, mirrored a third time). */}
            {pending !== null && pendingOption !== null && (
              <div
                data-role="construction-change-confirm"
                role="alert"
                className="switch-confirm"
              >
                <p data-role="construction-change-words" className="switch-confirm__words">
                  {constructionChangeWords(pendingOption.label, confirmed)}
                </p>
                <div className="switch-confirm__actions">
                  <button
                    type="button"
                    data-role="construction-confirm-change"
                    className="button button--primary button--small"
                    disabled={saving}
                    onClick={onConfirmChange}
                  >
                    {saving ? "Changing…" : `Change to ${pendingOption.label}`}
                  </button>
                  <button
                    type="button"
                    data-role="construction-cancel-change"
                    className="button button--secondary button--small"
                    disabled={saving}
                    onClick={onCancelPending}
                  >
                    Keep {info.label}
                  </button>
                </div>
              </div>
            )}
            <button
              type="button"
              data-role="construction-close-edit"
              className="button button--ghost button--small"
              disabled={saving}
              onClick={onCancelEdit}
            >
              Close
            </button>
          </div>
        )}
        {error !== null && (
          <div data-role="construction-error" role="alert" className="panel__error">
            {error}
          </div>
        )}
      </div>
    </li>
  );
}

interface AssuranceRowProps {
  readonly caseId: string;
  readonly site: AssuranceSite;
  /** ALREADY RESOLVED by `effectiveDisposition` — the operator's act, else the drop
   *  recorded at Adjust, else release. The row never re-resolves it. */
  readonly disposition: Disposition;
  /** Whether the release|withhold pair renders here — `withholdOffered` over the
   *  EFFECTIVE disposition, so a row this screen is about to withhold is always
   *  reversible on this screen. */
  readonly offersWithhold: boolean;
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
  offersWithhold,
  acknowledged,
  expanded,
  onDisposition,
  onAcknowledge,
  onToggleExpand,
}: AssuranceRowProps) {
  const rimRef = site.references["rim_agreement_mm"];
  const rmsRef = site.references["deviation_rms_mm"];
  const rotation = site.rotation;
  // WHAT THIS ROW'S NUMBERS STILL DESCRIBE after an operator rework. It rides in the
  // ROW, not behind the expand: the confirmation seals this table, and a reader must
  // not have to open a panel to learn that some of what they are signing predates the
  // fit on the site (review 2026-07-28, finding E).
  const stale = staleMetricsWords(site);
  // WHETHER THIS ROW'S FIT HAD ANYTHING TO CHECK IT (defect cap6020-neodent-gm,
  // 2026-08-01). Same placement and same reason as `stale`: a confirmation seals this
  // table, and "the RMS beside this rotation was arithmetic" is not a fact a reader
  // should have to open a panel to find. The server's own word — never a count this
  // browser compared.
  const crossCheck = crossCheckWords(site);
  return (
    <>
      <tr
        data-role="assurance-row"
        data-tooth={site.tooth}
        data-status={site.status ?? "unknown"}
        data-flagged={site.status === "flagged"}
        data-needs-acknowledgment={needsAcknowledgment(site)}
        // the resolved disposition, IN THE MARKUP: a reviewer reading the row must
        // be able to tell what confirming does with it (audit 2026-07-31)
        data-disposition={disposition}
        className={
          needsAcknowledgment(site) ? "assurance-row--flagged" : undefined
        }
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
          <span className="assurance-num">{site.declared_variant ?? "—"}</span>
          {site.identified_variant !== site.declared_variant && (
            <span className="assurance-sub"> measured {site.identified_variant ?? "—"}</span>
          )}{" "}
          <span
            data-role="identity-agreement"
            className={agreementChipClass(site.variant_agreement)}
          >
            {site.variant_agreement ?? "unmeasured"}
          </span>
        </td>
        {/* SEAT + ROTATION + DEVIATION in one cell: three numbers an operator reads
            together as "how did this align?". Their industry sentences live in the expand. */}
        <td data-role="cell-alignment">
          <div className="assurance-metrics">
            <span data-role="cell-seat">
              <span
                className={`chip chip--seat ${
                  (site.seat_method ?? "").startsWith("rim") ? "chip--seat-rim" : "chip--seat-icp"
                }`}
              >
                {site.seat_method ?? "—"}
              </span>{" "}
              <span className="assurance-num">
                {site.rim_agreement_mm ?? "—"}
                {site.rim_agreement_mm !== null && " mm"}
              </span>
            </span>
            <span data-role="cell-rotation" className="rotation-verdict">
              <span className="rotation-verdict__residual">
                {rotation.deg !== null ? `${rotation.deg}°` : "no reading"}
              </span>
              <span className="assurance-sub"> {rotation.evidence ?? "no evidence"}</span>
              {rotation.unverified && (
                <em
                  data-role="rotation-unverified"
                  className="rotation-verdict__residual rotation-verdict__residual--review"
                >
                  {" "}
                  unverified
                </em>
              )}
            </span>
            <span data-role="cell-deviation">
              <span className="assurance-sub">RMS </span>
              <span className="assurance-num">{site.deviation_rms_mm ?? "—"}</span>
              <span className="assurance-sub"> / p90 </span>
              <span className="assurance-num">{site.deviation_p90_mm ?? "—"} mm</span>
            </span>
          </div>
        </td>
        {/* GATE + RELIEF: the two verdicts about whether this site may ship. The gate's
            action words and the clamp's reason are sentences — they belong in the expand. */}
        <td data-role="cell-verdict">
          <div className="results-table__gate-cell">
            <span data-role="gate-level" className={gateChipClass(site.gate.level)}>
              {site.gate.level}
            </span>
            {site.clamp.clamped ? (
              <span data-role="cell-clamp" className="chip chip--relief-clamped">
                relief {site.clamp.requested_mm ?? "—"} → {site.clamp.applied_mm ?? "—"} mm
              </span>
            ) : (
              <span data-role="cell-clamp" className="assurance-sub">
                relief as requested
              </span>
            )}
            {stale !== null && (
              <span data-role="stale-metrics" className="assurance-sub assurance-stale">
                {stale}
              </span>
            )}
            {/* THE VACUOUS RMS (defect cap6020-neodent-gm, 2026-08-01). Beside the
                staleness line and for the same reason: both say which of this row's
                numbers a signature would be covering under false pretences. This cell
                is where the row's SENTENCES live — the rotation cell holds figures. */}
            {crossCheck !== null && (
              <span
                data-role="cross-check"
                className="assurance-sub assurance-cross-check"
              >
                {crossCheck}
              </span>
            )}
            {/* THE DISCLOSURE GAP THIS CLOSES (plan §10-E): a shared construction
                part across differently-declared variants, verbatim from the
                worker. Beside the clamp story, not instead of it — and it rides
                in the ROW like ``stale-metrics`` does, because the acknowledgment
                this earns (``needsAcknowledgment``) applies whether or not the
                report is ever opened. */}
            {site.production_note !== null && (
              <span data-role="production-note" className="chip chip--production-note">
                {site.production_note}
              </span>
            )}
          </div>
        </td>
        <td>
          <div className="assurance-controls">
            {/* THE DISPOSITION CONTROL RENDERS ON A FLAGGED ROW (client 2026-07-27
                #4) — a clean site headed for release SAYS so quietly instead of
                asking a question with one sane answer — AND ON ANY ROW THIS SCREEN
                IS ABOUT TO WITHHOLD (audit 2026-07-31). Gating it on the flag alone
                made a cap dropped at Adjust a one-way door: the row printed the
                literal word "released", confirming from it withheld the site and
                every case-wide file, and the reversal existed only back on Adjust. */}
            {offersWithhold ? (
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
          <td colSpan={5}>
            <div className="verification-panel">
              {/* THE SENTENCES LIVE HERE (client, 2026-07-27): industry references, the
                  gate's own action words and the clamp's reason are read deliberately, in
                  one place, beside the images they explain — not wrapped into table cells
                  that forced a horizontal scroll across the whole report. */}
              <dl data-role="row-detail" className="assurance-detail">
                {rimRef && (
                  <>
                    <dt>Seat reference</dt>
                    <dd data-role="industry-ref">vs {rimRef.industry_ref.value}</dd>
                  </>
                )}
                {rmsRef && (
                  <>
                    <dt>Deviation reference</dt>
                    <dd data-role="industry-ref">vs {rmsRef.industry_ref.value}</dd>
                  </>
                )}
                {site.gate.actions.length > 0 && (
                  <>
                    <dt>Gate</dt>
                    <dd>
                      {site.gate.actions.map((words) => (
                        <p key={words} data-role="gate-words">
                          {words}
                        </p>
                      ))}
                    </dd>
                  </>
                )}
                {site.clamp.clamped && (
                  <>
                    <dt>Relief clamp</dt>
                    <dd>{site.clamp.reason ?? "no reason recorded"}</dd>
                  </>
                )}
                {site.production_note !== null && (
                  <>
                    <dt>Production</dt>
                    <dd data-role="production-note-detail">{site.production_note}</dd>
                  </>
                )}
              </dl>
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
  /** The derived invoice (gap ``invoice-on-the-surfaces``) — optional, because every
   *  static test written before the money existed passes none, and a surface without
   *  it says the amount is undefined rather than inventing one. */
  readonly invoice?: FetchState<InvoiceView> | null;
  readonly dispositions: DispositionMap;
  readonly acknowledged: readonly number[];
  readonly expanded: readonly number[];
  /** The report modal's own state (client 2026-07-27 #5) — the container owns it so
   * Esc and the backdrop can close it; the View renders it. */
  readonly reportOpen?: boolean;
  /** The agreement (plan §10-A) — false until the operator ticks it; the
   * container owns it so it can be reset on a re-confirm cycle. */
  readonly termsAccepted?: boolean;
  readonly phase?: DeliverPhase;
  /** A refusal that is NOT the drift 409 — rendered in the backend's words. */
  readonly actionError?: string | null;
  /** The evidence-drift 409's words — triggers the re-confirm flow's rendering. */
  readonly staleWords?: string | null;
  /** The gated artifact list's fetch state; null until a release exists. */
  readonly artifacts?: FetchState<ArtifactsView> | null;
  /** True while "download all" is walking the list one file at a time. */
  readonly downloadingAll?: boolean;
  /** The current run's package file list (client 2026-08-01) — feeds the 3D preview
   *  tabs (`previewTabs`); null until every static test written before it existed
   *  keeps compiling, and the tabs then simply do not render (an honest absence). */
  readonly runFacts?: FetchState<RunFactsView> | null;
  /** THE CONSTRUCTION STEP's own interactive state (client 2026-08-01) — the
   *  container owns it so a re-confirm cycle or a fresh detail can reset it. */
  readonly constructionEditing?: boolean;
  readonly constructionPending?: string | null;
  readonly constructionSaving?: boolean;
  readonly constructionError?: string | null;
  readonly onConstructionEdit?: () => void;
  readonly onConstructionCancelEdit?: () => void;
  readonly onConstructionPick?: (pathId: string) => void;
  readonly onConstructionCancelPending?: () => void;
  readonly onConstructionConfirm?: () => void;
  readonly onDisposition: (tooth: number, act: Disposition) => void;
  readonly onAcknowledge: (tooth: number, on: boolean) => void;
  readonly onToggleExpand: (tooth: number) => void;
  readonly onOpenReport?: () => void;
  readonly onCloseReport?: () => void;
  readonly onTermsChange?: (accepted: boolean) => void;
  readonly onConfirm: () => void;
  /** The demo's door back (client 2026-07-30) — optional: static tests predate it. */
  readonly onStartOver?: () => void;
  /** Opens the checkout DIALOG; the container renders it via `checkoutDialog`. */
  readonly onOpenCheckout?: () => void;
  readonly checkoutDialog?: React.ReactNode;
  readonly onRelease: () => void;
  readonly onReloadEvidence: () => void;
  readonly onDownload: (filename: string) => void;
  readonly onDownloadAll?: () => void;
}

/** The stage's whole surface, pure payload → markup — statically testable. */
export function DeliverStageView({
  detail,
  assurance,
  invoice = null,
  dispositions,
  acknowledged,
  expanded,
  reportOpen = false,
  // Defaults TRUE, mirroring domain/deliver.confirmBlockers's own default
  // (plan §10-A): every test written before the terms step existed keeps its
  // prior behavior unchanged; the container passes the real checkbox state.
  termsAccepted = true,
  phase = "idle",
  actionError = null,
  staleWords = null,
  artifacts = null,
  downloadingAll = false,
  runFacts = null,
  constructionEditing = false,
  constructionPending = null,
  constructionSaving = false,
  constructionError = null,
  onConstructionEdit = () => undefined,
  onConstructionCancelEdit = () => undefined,
  onConstructionPick = () => undefined,
  onConstructionCancelPending = () => undefined,
  onConstructionConfirm = () => undefined,
  onDisposition,
  onAcknowledge,
  onToggleExpand,
  onOpenReport = () => undefined,
  onCloseReport = () => undefined,
  onTermsChange = () => undefined,
  onConfirm,
  onStartOver = () => undefined,
  onOpenCheckout = () => undefined,
  checkoutDialog = null,
  onRelease,
  onReloadEvidence,
  onDownload,
  onDownloadAll = () => undefined,
}: DeliverStageViewProps) {
  const session = detail.session;
  // THE CONSTRUCTION STEP's pure derivations — the picker's rows (Intake's own
  // catalog reader, regrouped by vendor) and the effective construction resolved
  // against them (never re-derived; the BFF's own value and attribution).
  const constructionOptionsList = constructionOptions(detail);
  const constructionGroupsList = constructionGroups(constructionOptionsList);
  const constructionInfo = constructionStepWords(detail.choices, constructionOptionsList);
  // ONE derivation, read by the stage's confirm and the modal footer's alike
  const blockers =
    assurance.kind === "ok"
      ? confirmBlockers(assurance.data, dispositions, acknowledged, termsAccepted)
      : [];
  const confirmable = assurance.kind === "ok" && blockers.length === 0 && phase === "idle";
  // ONE reading of the fork too — the stage's copy and the modal's are the same string
  const forkWords = assurance.kind === "ok" ? adjustmentsWords(assurance.data) : null;
  const steps = releaseSteps(session);
  const disclosure = releaseDisclosureWords(session.release_preview);
  // the priced document, or null — one reading, shared by the attestation sentence,
  // the order summary and the checkout dialog behind it
  const invoiceData = invoice?.kind === "ok" ? invoice.data : null;
  const statusOf = (tooth: number): string =>
    detail.sites.find((s) => s.tooth === tooth)?.status ?? "unknown";
  const groups = artifacts?.kind === "ok" ? groupArtifacts(artifacts.data.files) : [];
  // THE 3D PREVIEW TABS (client 2026-08-01) — matched against the run's OWN package
  // file list; the teeth are the assurance's own worst-first site order, so a tab
  // reads in the same order as the table above it. `runFacts` may still be loading
  // or absent (every static test written before it existed) — the tabs are then
  // simply not there yet, never a placeholder.
  const packageFiles = runFacts?.kind === "ok" ? runFacts.data.package_files : [];
  // Escape closes the full-report modal.
  useDialogEscape(reportOpen, onCloseReport);
  const previewTeeth = assurance.kind === "ok" ? assurance.data.sites.map((s) => s.tooth) : [];
  const meshPreviewTabs = previewTabs(packageFiles, previewTeeth);

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
          <h3 className="panel__title">
            Delivery
            {(detail.session.confirmation !== null ||
              detail.session.payment_authorized ||
              detail.session.released) && (
              /* THE DOOR BACK (client 2026-07-30: "once paid i cant go back").
                 Withdraws the confirmation, the payment and the release TOGETHER —
                 an explicit act against real server state, not a demo mode where the
                 money record evaporates. The run and every site rung survive; the
                 second walk re-derives and re-seals through the same gates. */
              <button
                type="button"
                data-role="delivery-reset"
                className="button button--ghost button--small delivery-reset"
                disabled={phase !== "idle"}
                onClick={onStartOver}
              >
                Start over (demo) — withdraw confirmation, payment &amp; release
              </button>
            )}
          </h3>
          {/* THE VISIBLE PROGRESSION (client 2026-07-27 #6): three steps, each
              stating what it is — done with its time, current with its act, waiting
              with what it needs. No step is ever inert without saying why. */}
          <ol data-role="release-steps" className="release-steps">
            {steps.map((step, index) => (
              <Fragment key={step.id}>
              <li
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
                  {step.id === "confirmed" &&
                    step.state === "done" &&
                    detail.session.confirmation?.terms_version != null && (
                      /* THE AUDIT PATH (client 2026-07-30): the sealed record names
                         a terms version, and this resolves it — reading back exactly
                         the document that signature covered, even once newer terms
                         land under a different version. */
                      <a
                        data-role="sealed-terms-link"
                        className="release-step__terms"
                        href={`/terms/${encodeURIComponent(
                          detail.session.confirmation.terms_version,
                        )}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Terms accepted: {detail.session.confirmation.terms_version} ↗
                      </a>
                    )}

                  {step.id === "confirmed" && step.state === "current" && (
                    <>
                      {/* what the signature is about to seal, before it is given */}
                      {forkWords !== null && <AdjustmentsNote words={forkWords} />}
                      {/* THE AGREEMENT (plan §10-A): confirm and accept terms is
                          one act — the checkbox sits directly above the button
                          it gates. */}
                      <TermsAcceptance
                        siteCount={detail.sites.length}
                        invoice={invoiceData}
                        accepted={termsAccepted}
                        disabled={phase !== "idle"}
                        onChange={onTermsChange}
                      />
                      <div className="release-step__actions">
                        {confirmButton("step-confirm")}
                      </div>
                      {/* the demand belongs WITH the act (review 2026-07-28): under a
                          done ✓ step the button is gone, and a list of what is missing
                          with nothing to press is a dead end — the modal footer is
                          where a confirmed case re-confirms from */}
                      <ConfirmBlockers blockers={blockers} />
                    </>
                  )}

                  {/* WHAT WAS ACTUALLY CHARGED, ON THE STEP THAT SAYS IT WAS PAID
                      (audit 2026-07-31). The receipt lived inside the invoice block,
                      and that whole block is gated on the paid step being CURRENT —
                      so `releaseSteps` flipped the step to "done" the instant the
                      payment landed and took the amount, the rate card and the
                      turnaround away with it. The checkout dialog could not fill the
                      gap either: `pay()` always closes it on the return leg. After
                      payment no surface in the product stated the figure, while the
                      BFF's activity log held the cents.

                      Read off `session.payment` — the record itself — rather than
                      the invoice: the invoice is the case's price NOW and can
                      legitimately have moved (a turnaround change reprices going
                      forward and fires no boundary). The receipt must describe the
                      charge that happened. */}
                  {step.id === "paid" && step.state === "done" &&
                    receiptWords(session.payment) !== null && (
                      <p data-role="paid-receipt" className="release-step__receipt">
                        {receiptWords(session.payment)}
                      </p>
                    )}

                  {step.id === "paid" && step.state === "current" && (
                    <div className="release-step__actions">
                      {/* THE CHECKOUT SCREEN (plan §10-A: "a checkout screen and
                          a return"). THE DERIVED INVOICE LANDS HERE (gap
                          ``invoice-on-the-surfaces``, 2026-07-31): the lines the BFF
                          priced, then ITS total — `total_cents` rendered, never the
                          sum of what is on screen, because an amount the browser
                          arrived at is the money-shaped cousin of a claimed verdict.
                          The placeholder banner stays while the server calls the
                          rates a placeholder: these are the design prototype's
                          figures, not the client's price list, and a total that
                          reads like a quotation when it is not is worse than none. */}
                      <div data-role="checkout-screen" className="checkout-screen">
                        {invoice !== null && invoice.kind === "ok" ? (
                          <div className="checkout-screen__invoice">
                            <dl className="checkout-order">
                              {orderLines(invoice.data).map((line) => (
                                <div
                                  key={line.key}
                                  data-role="invoice-line"
                                  data-key={line.key}
                                  className={`checkout-order__row${
                                    line.billed ? "" : " checkout-order__row--unbilled"
                                  }`}
                                >
                                  <dt>
                                    {line.label}
                                    {line.unit !== null && (
                                      <span className="checkout-order__unit">
                                        {" "}
                                        · {line.unit}
                                      </span>
                                    )}
                                  </dt>
                                  <dd>{line.amount}</dd>
                                </div>
                              ))}
                              <div className="checkout-order__row checkout-order__row--total">
                                <dt>Amount due</dt>
                                <dd data-role="checkout-price">
                                  <strong data-role="checkout-total">
                                    {orderTotal(invoice.data)}
                                  </strong>
                                </dd>
                              </div>
                            </dl>
                            <p
                              data-role="invoice-turnaround"
                              className="checkout-order__note"
                            >
                              {turnaroundWords(invoice.data)}
                            </p>
                            {invoiceIsPlaceholder(invoice.data) && (
                              <p
                                data-role="invoice-placeholder"
                                className="checkout-order__placeholder-banner"
                              >
                                {invoice.data.note}
                              </p>
                            )}
                            {receiptWords(invoice.data.paid) !== null && (
                              <p
                                data-role="invoice-receipt"
                                className="checkout-order__receipt"
                              >
                                {receiptWords(invoice.data.paid)}
                              </p>
                            )}
                          </div>
                        ) : invoice !== null && invoice.kind === "error" ? (
                          /* a refusal in the BFF's own words: a blank where money
                             goes reads as "free", which is the one thing it is not */
                          <div
                            data-role="invoice-error"
                            role="alert"
                            className="panel__error"
                          >
                            {invoice.detail}
                          </div>
                        ) : (
                          <p data-role="checkout-price" className="checkout-screen__price">
                            Amount due:{" "}
                            <strong>
                              {invoice !== null
                                ? "pricing the case…"
                                : "pricing not yet defined"}
                            </strong>
                          </p>
                        )}
                        {/* THE CHECKOUT DIALOG (client 2026-07-30, twice): first
                            "no way … to add credit card or saved credit card
                            mocks" — so an inline stub became a real checkout
                            surface — then "might be better on a modal, so the
                            client can still see their work on the background".
                            The dialog keeps the assurance visible underneath, and
                            paying updates THIS page in place. */}
                        <button
                          type="button"
                          data-role="go-to-checkout"
                          className="button button--primary"
                          onClick={onOpenCheckout}
                        >
                          Go to checkout (demo) — {detail.sites.length} site
                          {detail.sites.length === 1 ? "" : "s"}
                        </button>
                        <p data-role="payment-stub-note" className="panel__hint">
                          The checkout is a DEMO: saved-card mocks, non-editable
                          card fields, no provider, no money. Its return leg asserts
                          nothing — this case's own record is the only thing that
                          says whether payment happened.
                        </p>
                        {/* WHAT PAYING DOES, BEFORE the checkout opens. The dialog
                            covers this page, so the sentence belongs at the point the
                            operator commits to paying — the last thing read before the
                            money surface, not a footnote inside it. The link resolves
                            the version the CONFIRMATION sealed, so the document beside
                            the payment is the one this case is bound by even after
                            newer terms land. Paying re-accepts nothing. */}
                        <p data-role="checkout-terms" className="panel__hint checkout-terms">
                          {CHECKOUT_SEAL_WORDS}{" "}
                          <a
                            data-role="checkout-terms-link"
                            className="terms-block__link terms-block__link--inline"
                            href={sealedTermsHref(detail.session.confirmation)}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Read the sealed Terms and Conditions ↗
                          </a>
                        </p>
                      </div>
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
              {/* THE CONSTRUCTION STEP (client 2026-08-01), positioned right AFTER
                  Confirmed and before Paid — the client's own words. It is not part
                  of `steps`'s done/current/waiting machine: the effective
                  construction is always shown and always changeable, so it never
                  "finishes", and folding it in would either freeze or break the
                  ladder's "exactly one current step" invariant. */}
              {step.id === "confirmed" && (
                <ConstructionStep
                  info={constructionInfo}
                  groups={constructionGroupsList}
                  editing={constructionEditing}
                  pending={constructionPending}
                  saving={constructionSaving}
                  error={constructionError}
                  confirmed={detail.session.confirmed}
                  onEdit={onConstructionEdit}
                  onCancelEdit={onConstructionCancelEdit}
                  onPick={onConstructionPick}
                  onCancelPending={onConstructionCancelPending}
                  onConfirmChange={onConstructionConfirm}
                />
              )}
              </Fragment>
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
                {/* THE CLOSING STATEMENT. The progression's Released step gives the
                    TIME; nothing said the AMOUNT, so a finished case never actually
                    said it was finished. Counted off THIS response — the list the
                    release served — never off release_preview: a withheld site makes
                    those two legitimately differ, and this sentence describes the
                    disclosure that happened. */}
                <p data-role="released-closing" className="released-closing">
                  {releasedClosingWords(artifacts.data)}
                </p>
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

      {checkoutDialog}
      <div className="workbench__stage">
        <section className="panel deliver-evidence" aria-label="Assurance evidence">
          <h3 className="panel__title">
            Assurance — worst first
            <span className="panel__title-case"> · {detail.case.id}</span>
          </h3>
          {/* THE HEADER'S OWN ARITHMETIC (design assuranceNote, flow.dc.html:1376).
              The panel named the case and went straight into the rows, so the size
              and shape of what is about to be signed had to be counted by eye. The
              counts are display arithmetic over statuses the BFF derived — this
              counts rows, it never decides what a row is — and the second line names
              the acknowledgment obligation as the ACT it is, rather than minting a
              status word the server never sent. */}
          {assurance.kind === "ok" && (
            <p className="deliver-evidence__rollup">
              <span data-role="assurance-counts" className="deliver-evidence__counts">
                {assuranceCountsWords(assurance.data)}
              </span>
              <span data-role="assurance-policy" className="deliver-evidence__policy">
                {/* the DISPOSITIONS ride in (audit 2026-07-31): without them this
                    header asserted that sites the operator had withheld "release
                    only as acknowledged exceptions", contradicting the rows below
                    it, the confirm gate, and the server's own invoice split */}
                {acknowledgmentPolicyWords(assurance.data, dispositions)}
              </span>
            </p>
          )}
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
                {evidenceSummary(assurance.data, dispositions).map((line) => (
                  <li
                    key={line.tooth}
                    data-role="evidence-line"
                    data-tooth={line.tooth}
                    data-flagged={line.flagged}
                    data-disposition={line.disposition}
                    className={`evidence-summary__line${
                      line.flagged ? " evidence-summary__line--flagged" : ""
                    }${
                      line.disposition === "withhold"
                        ? " evidence-summary__line--withheld"
                        : ""
                    }`}
                  >
                    <span className="evidence-summary__site">Tooth {line.tooth}</span>{" "}
                    {/* THE CONFIRM FIRES FROM THIS PANEL (audit 2026-07-31), so a
                        cap the signature is about to drop cannot read here as an
                        unremarkable line — the chip names it before the button. */}
                    {line.disposition === "withhold" && (
                      <span data-role="evidence-withheld" className="chip chip--withheld">
                        withheld
                      </span>
                    )}{" "}
                    <span data-role="gate-level" className={gateChipClass(line.gate)}>
                      {line.gate}
                    </span>{" "}
                    <span className="evidence-summary__words">{line.words}</span>
                    {/* THE ROW'S ONE SENTENCE OF WHY, on the surface the confirmation
                        SEALS. It was two clicks away — open the report, expand the
                        row — and the gate's words are the whole reason a row is
                        flagged. `data-verbatim` marks whether this is the run's own
                        sentence or the no-action fallback: a reviewer reading the
                        markup must be able to tell the two apart. */}
                    <span
                      data-role="evidence-note"
                      data-verbatim={line.noteFromRun}
                      className="evidence-summary__note"
                    >
                      {line.note}
                    </span>
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
              </div>
              {/* THE 3D PREVIEW TABS (client 2026-08-01: "we also have the previews
                  of the artifacts") — the demo's three named views of the run's own
                  result, ABOVE the flat QC strip below: these are the interactive
                  views, the QC renders stay the flat evidence. `DeliverPreview`
                  renders nothing at all when the package names none of the three
                  files (an honest absence). */}
              <DeliverPreview caseId={detail.case.id} tabs={meshPreviewTabs} />
              {/* THE THREE MAIN ARTIFACTS, PREVIEWED (client 2026-08-01): the run's
                  own pictures of the fit — alignment proof, clock view, deviation
                  map — on the page, not one click away inside the report. Each card
                  opens the full report, which stays the one place the whole row is
                  read. Filenames come from the assurance's own list; nothing here
                  constructs one. */}
              {qcPreviews(assurance.data).length > 0 && (
                <ul data-role="artifact-previews" className="deliver-previews">
                  {qcPreviews(assurance.data).map((preview) => (
                    <li key={preview.filename} className="deliver-previews__item">
                      <button
                        type="button"
                        data-role="artifact-preview"
                        data-filename={preview.filename}
                        className="deliver-previews__card"
                        title={`${preview.label} — tooth ${preview.tooth}. Opens the full report.`}
                        onClick={onOpenReport}
                      >
                        <img
                          className="deliver-previews__image"
                          src={qcImageUrl(detail.case.id, preview.filename)}
                          alt={`${preview.label}, tooth ${preview.tooth}`}
                          loading="lazy"
                        />
                        <span className="deliver-previews__caption">
                          {preview.label}
                          <span className="deliver-previews__tooth">
                            tooth {preview.tooth}
                          </span>
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              {/* the confirm itself lives in TWO places and only two: the modal's
                  footer bar (read and act in one place) and the progression's
                  Confirmed step in the work column (reachable without reopening the
                  report). Both read the same `blockers` array, and the list renders
                  beside each — one truth about confirmability, stated twice. */}
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
              <div className="assurance-table-fit">
                <table data-role="assurance-table" className="results-table">
                  <thead>
                    <tr>
                      {/* FIVE COLUMNS, NO HORIZONTAL SCROLL (client, 2026-07-27: "this
                          table can be consolidated … fit the modal view, no need for the
                          horizontal scroll — it makes it harder to see"). Eight columns each
                          carrying a reference SENTENCE could not fit any modal; the numbers
                          are what a row is scanned for, so the sentences moved into the
                          expand beside the QC images where they are read, not skimmed. */}
                      <th>Site</th>
                      <th>Cap</th>
                      <th>Alignment</th>
                      <th>Verdict</th>
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
                        offersWithhold={withholdOffered(site, dispositions)}
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
                {/* the fork rides in that seal, so it is legible beside the act —
                    the table shows the run's facts, this shows what was DONE */}
                <AdjustmentsNote words={adjustmentsWords(assurance.data)} />
                {/* the agreement, beside the act here too (plan §10-A) — the
                    footer is the other place a confirm (or a re-confirm) fires
                    from, so it needs the same checkbox the stage does */}
                <TermsAcceptance
                  siteCount={detail.sites.length}
                  invoice={invoiceData}
                  accepted={termsAccepted}
                  disabled={phase !== "idle"}
                  onChange={onTermsChange}
                />
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
  const [invoice, setInvoice] = useState<FetchState<InvoiceView>>({
    kind: "loading",
  });
  const [dispositions, setDispositions] = useState<DispositionMap>({});
  const [acknowledged, setAcknowledged] = useState<readonly number[]>([]);
  const [expanded, setExpanded] = useState<readonly number[]>([]);
  // THE AGREEMENT (plan §10-A): unticked until the operator explicitly checks
  // it — never pre-filled, the same posture every effective choice already
  // takes (ARCHITECTURE.md §6: the lab chooses, the software never chooses
  // for them).
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [reportOpen, setReportOpen] = useState(false);
  const [phase, setPhase] = useState<DeliverPhase>("idle");
  const [actionError, setActionError] = useState<string | null>(null);
  const [staleWords, setStaleWords] = useState<string | null>(null);
  const [artifacts, setArtifacts] = useState<FetchState<ArtifactsView> | null>(null);
  const [downloadingAll, setDownloadingAll] = useState(false);
  // THE RUN'S PACKAGE FILE LIST (client 2026-08-01) — feeds the 3D preview tabs
  // (`previewTabs`). Read-only like the assurance/invoice fetches: no gate to pass,
  // evidence class, ungated (see the BFF's preview-mesh endpoint doctrine).
  const [runFacts, setRunFacts] = useState<FetchState<RunFactsView>>({ kind: "loading" });
  // THE CONSTRUCTION STEP's own interactive state (client 2026-08-01) — separate
  // from `phase`: changing the construction is its own act, not one of the three
  // gated POSTs the rest of this container drives.
  const [constructionEditing, setConstructionEditing] = useState(false);
  const [constructionPending, setConstructionPending] = useState<string | null>(null);
  const [constructionSaving, setConstructionSaving] = useState(false);
  const [constructionError, setConstructionError] = useState<string | null>(null);

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
    // actually there, re-accepts the terms, and dispositions again (the
    // re-confirm flow's honesty)
    setDispositions({});
    setAcknowledged([]);
    setTermsAccepted(false);
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

  /* THE PRICE, RE-READ WHENEVER WHAT IS BEING PRICED MOVES (gap
     ``invoice-on-the-surfaces``). `derive_invoice` classifies sites against the
     STANDING CONFIRMATION's dispositions, so a confirmation landing (or being
     withdrawn) changes both the amount AND the attestation sentence's counts; the
     payment record adds the receipt. Keying on the two records' timestamps re-reads
     on exactly those transitions and on nothing else. */
  const confirmedAt = detail.session.confirmation?.at ?? null;
  const paidAt = detail.session.payment?.at ?? null;
  useEffect(() => {
    setInvoice({ kind: "loading" });
    void fetchInvoice(caseId).then((result) => {
      if (mountedRef.current) setInvoice(result);
    });
  }, [caseId, runState, confirmedAt, paidAt]);

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

  // The package file list — same trigger as the assurance re-load: a new run
  // renames or drops the files the preview tabs can offer.
  useEffect(() => {
    setRunFacts({ kind: "loading" });
    void fetchRun(caseId).then((result) => {
      if (mountedRef.current) setRunFacts(result);
    });
  }, [caseId, runState]);

  const handleConstructionEdit = useCallback(() => {
    setConstructionEditing(true);
    setConstructionError(null);
  }, []);

  const handleConstructionCancelEdit = useCallback(() => {
    setConstructionEditing(false);
    setConstructionPending(null);
    setConstructionError(null);
  }, []);

  // THE ONE PUT, whichever door fires it (a direct apply or the confirmed change
  // below) — the WHOLE choices document, PUT semantics (Intake's own assembly rule,
  // `choicesUpdateFrom`), so this second copy of the picker can never un-choose the
  // jaw or the relief by omission.
  const fireConstructionChange = useCallback(
    (pathId: string) => {
      setConstructionSaving(true);
      setConstructionError(null);
      void putChoices(
        caseId,
        choicesUpdateFrom(detail, { construction_path: pathId }),
      ).then((result) => {
        if (!mountedRef.current) return;
        setConstructionSaving(false);
        if (result.kind === "ok") {
          onDetail(result.data);
          setConstructionEditing(false);
          setConstructionPending(null);
        } else {
          setConstructionError(result.detail);
        }
      });
    },
    [caseId, detail, onDetail],
  );

  /** The visible-reset doctrine, precisely (DeclareStage's `handleAskSwitch`,
   * mirrored a third time): a pick that would RETIRE the current run (and
   * everything standing on it) asks in words first; a pick back onto the
   * effective construction offers nothing to confirm at all (the server's own
   * "identical re-PUT resets nothing" equality guard); and — on the rare reachable
   * case with no run yet — a pick that would retire nothing extra beyond the
   * ordinary choices-change reset applies directly, the same checkbox-over-nothing
   * rule the system switch and the re-mark door both already follow. */
  const handleConstructionPick = useCallback(
    (pathId: string) => {
      if (pathId === "" || pathId === detail.choices.effective_construction.value) {
        setConstructionPending(null);
        return;
      }
      if (!constructionChangeRetiresSomething(detail.session)) {
        fireConstructionChange(pathId);
        return;
      }
      setConstructionPending(pathId);
    },
    [detail, fireConstructionChange],
  );

  const handleConstructionCancelPending = useCallback(() => {
    setConstructionPending(null);
  }, []);

  const handleConstructionConfirm = useCallback(() => {
    if (constructionPending !== null) fireConstructionChange(constructionPending);
  }, [constructionPending, fireConstructionChange]);

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
    void postConfirm(
      caseId,
      confirmWireBody(dispositions, acknowledged, termsAccepted),
    ).then(settle);
  }, [caseId, dispositions, acknowledged, termsAccepted, settle]);

  const handleTermsChange = useCallback((accepted: boolean) => {
    setTermsAccepted(accepted);
  }, []);

  /**
   * THE CHECKOUT + RETURN (plan §10-A). Authorizing is the trusted act
   * (``postPayment`` — the stand-in for a provider's own confirmation); the
   * RETURN LEG that follows carries only a locally-made identifier and
   * asserts nothing — its response is what actually settles the UI, modeling
   * "you're back, here is what is actually true" rather than trusting
   * whatever brought the browser back. If authorization itself refuses,
   * there is no checkout to "return" from, so it settles right there.
   */
  /* THE CHECKOUT DIALOG'S open-state lives here because paying must update THIS
     page's detail — the dialog itself owns the two-leg flow (CheckoutDialog). */
  const [checkoutOpen, setCheckoutOpen] = useState(false);

  const handleStartOver = useCallback(() => {
    setPhase("resetting");
    setActionError(null);
    void postDeliveryReset(caseId).then((result) => {
      if (!mountedRef.current) return;
      setPhase("idle");
      if (result.kind === "ok") onDetail(result.data);
      else setActionError(result.detail);
    });
  }, [caseId, onDetail]);

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
      invoice={invoice}
      dispositions={dispositions}
      acknowledged={acknowledged}
      expanded={expanded}
      reportOpen={reportOpen}
      termsAccepted={termsAccepted}
      phase={phase}
      actionError={actionError}
      staleWords={staleWords}
      artifacts={artifacts}
      downloadingAll={downloadingAll}
      runFacts={runFacts}
      constructionEditing={constructionEditing}
      constructionPending={constructionPending}
      constructionSaving={constructionSaving}
      constructionError={constructionError}
      onConstructionEdit={handleConstructionEdit}
      onConstructionCancelEdit={handleConstructionCancelEdit}
      onConstructionPick={handleConstructionPick}
      onConstructionCancelPending={handleConstructionCancelPending}
      onConstructionConfirm={handleConstructionConfirm}
      onDisposition={handleDisposition}
      onAcknowledge={handleAcknowledge}
      onToggleExpand={handleToggleExpand}
      onOpenReport={() => setReportOpen(true)}
      onCloseReport={() => setReportOpen(false)}
      onTermsChange={handleTermsChange}
      onConfirm={handleConfirm}
      onStartOver={handleStartOver}
      onOpenCheckout={() => setCheckoutOpen(true)}
      checkoutDialog={
        checkoutOpen ? (
          <CheckoutDialog
            detail={detail}
            // HANDED DOWN, never re-fetched: the dialog restates the very numbers
            // this stage is rendering behind it (gap ``pay-modal-metric-signoff``),
            // and two fetches of the same document are two answers waiting to differ
            assurance={assurance.kind === "ok" ? assurance.data : null}
            // THE FETCH STATE CROSSES THE BOUNDARY WHOLE (audit 2026-07-31).
            // Flattening to `kind === "ok" ? data : null` here is what let a FAILED
            // invoice render as "PLACEHOLDER — pricing not yet defined" over a live
            // Pay button: the dialog could not tell a refusal from an absence.
            invoice={invoice}
            // and the same resolved dispositions the stage is signing over, so the
            // checkout's strip cannot bill for a site the invoice beside it withholds
            dispositions={dispositions}
            onDetail={onDetail}
            onClose={() => setCheckoutOpen(false)}
          />
        ) : null
      }
      onRelease={handleRelease}
      onReloadEvidence={reloadEvidence}
      onDownload={handleDownload}
      onDownloadAll={handleDownloadAll}
    />
  );
}
