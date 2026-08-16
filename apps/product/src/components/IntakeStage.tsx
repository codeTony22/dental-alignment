/**
 * INTAKE (plan §4, §7 slice 4): the case opens HERE. Detection fires automatically
 * (once — keyed on session facts, domain/intake.shouldAutoDetect); capture-gate
 * verdicts surface BEFORE any work is invested — a rescan-grade verdict is a banner,
 * the chair-side moment; everything else is a per-site chip. The case-level choices
 * (construction part, jaw, gingival relief beside its ceiling) live in the panel.
 *
 * Direction of trust (AM-4): every mutation renders WHAT THE BFF RETURNS — optimistic
 * updates are deliberately absent. A PUT that the BFF refuses shows the refusal in the
 * backend's own words and the panel keeps showing the persisted state, not the wish.
 *
 * The banner and chips are REIMPLEMENTED small against the worker's verdict vocabulary
 * — not copied from the demo's JSX (the copy-debt ledger rule: this is product chrome,
 * not viewer physics).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  deleteRimPoints,
  postDetect,
  postMarkedSite,
  putChoices,
  putRemarkedSite,
  putRimPoints,
  type CaseSessionDetail,
  type ChoicesUpdate,
} from "../api/client";
import { blockedReason, factsFromCaseSession, isReachable } from "../domain/flow";
import {
  captureChipLabel,
  ceilingReadouts,
  choicesUpdateFrom,
  constructionOptions,
  turnaroundPillLabel,
  detectionMarkers,
  defaultToothForMark,
  EMPTY_MARK,
  markOnArmMark,
  adoptableProposals,
  markOnArmPick,
  markOnPlace,
  markPlacedWords,
  openingSiteFor,
  pickSiteAt,
  remarkRetiresSomething,
  remarkWords,
  rescanNotices,
  shouldAutoDetect,
  detectorDisagreement,
  discriminatorEvidenceSentence,
  curveHonestySentence,
  siteCentre,
  sitePickerOffered,
  siteEvidence,
  SITE_PICK_RADIUS_MM,
  type AdoptableProposal,
  type MarkDraft,
  OFF_SCAN_MISS_WORDS,
  MAX_RIM_POINTS,
  canFinishRimPoints,
  rimPointsCountWords,
  rimPointsPlacedWords,
  borderClickDisagreementWords,
} from "../domain/intake";
import { MainStage } from "./MainStage";
import { useDialogEscape } from "./useDialogEscape";
import { useDialogFocus } from "./useDialogFocus";

/** Detection's honest lifecycle on this mount — never a spinner over a lie. */
export type DetectPhase =
  | { readonly kind: "idle" }
  | { readonly kind: "detecting" }
  | { readonly kind: "failed"; readonly detail: string };

const JAW_CHOICES = ["upper", "lower"] as const;

interface CaptureBannerProps {
  readonly detail: CaseSessionDetail;
}

/** The chair-side moment: rescan-grade verdicts, surfaced before any work — in the
 * demo's red capture-banner language (a refused capture, not merely stale results). */
function CaptureBanner({ detail }: CaptureBannerProps) {
  const notices = rescanNotices(detail);
  if (notices.length === 0) return null;
  return (
    <div data-role="capture-banner" role="alert" className="capture-banner">
      <p className="capture-banner__title">
        Rescan recommended — the capture gate found problems before any work was
        invested.
      </p>
      <p className="capture-banner__item">
        If the patient is still in the chair, rescanning now costs minutes; marks placed
        on this capture would be wasted.
      </p>
      <ul className="capture-banner__list">
        {notices.map((notice, index) => (
          <li key={index} className="capture-banner__item">
            <strong>{notice.label}:</strong> {notice.message}
          </li>
        ))}
      </ul>
    </div>
  );
}

interface SiteListProps {
  readonly detail: CaseSessionDetail;
  /** The site the operator picked — the stage frames it. Null = the stage's own default. */
  readonly activeTooth: number | null;
  readonly onSelectSite: (tooth: number) => void;
  readonly pickArmed: boolean;
  readonly pickMiss: string | null;
  readonly onArmPick: () => void;
  readonly onCancelPick: () => void;
  /** Re-marking the ACTIVE site's centre (client 2026-08-01) — see RemarkSiteControl. */
  readonly remarkConfirming: boolean;
  readonly remarkArmed: boolean;
  readonly remarkSaving: boolean;
  readonly remarkError: string | null;
  readonly onAskRemark: () => void;
  readonly onConfirmRemark: () => void;
  readonly onCancelRemark: () => void;
  /** Adopting a detected cap no site carries (client 2026-08-04) — the missed-cap
   * door with the DETECTOR'S own centre; the operator only names the tooth. */
  readonly adoptSaving: boolean;
  readonly adoptError: string | null;
  readonly onAdopt: (center: readonly number[], tooth: number) => void;
  /** Adopting the detector's centre for an EXISTING site (the fleet table's lever):
   * the re-mark PUT with the detector's point, behind the same retirement consent. */
  readonly detectorConfirming: boolean;
  readonly detectorSaving: boolean;
  readonly detectorError: string | null;
  readonly onUseDetectorCentre: (tooth: number, point: readonly number[]) => void;
  readonly onConfirmDetectorCentre: (tooth: number, point: readonly number[]) => void;
  readonly onCancelDetectorCentre: () => void;
  /** RIM BORDER POINTS (§10-AL, task #33) — see RimPointsControl. Armed for at most
   *  one tooth at a time, like every other door onto the stage's pointer. */
  readonly rimPointsArmedTooth: number | null;
  readonly rimPointsLiveCount: number;
  readonly rimPointsSaving: boolean;
  readonly rimPointsDeleting: boolean;
  readonly rimPointsError: string | null;
  readonly onArmRimPoints: (tooth: number) => void;
  readonly onFinishRimPoints: () => void;
  readonly onCancelRimPoints: () => void;
  readonly onClearRimPoints: (tooth: number) => void;
}

/** One adoptable detected cap: the detector's facts, the operator's tooth number,
 * one act. The draft is local; the ACT is the adopt, and the landed detail (a new
 * site at `detected`, same ladder as every other) replaces everything. */
function AdoptProposalControl({
  proposal,
  defaultTooth,
  saving,
  error,
  onAdopt,
}: {
  readonly proposal: AdoptableProposal;
  /** The pre-filled label (client 2026-08-06, same rule as the missed-cap mark:
   *  domain/intake.defaultToothForMark) — adopting is one click, the field edits. */
  readonly defaultTooth?: number | null;
  readonly saving: boolean;
  readonly error: string | null;
  readonly onAdopt: (center: readonly number[], tooth: number) => void;
}) {
  const [tooth, setTooth] = useState(defaultTooth != null ? String(defaultTooth) : "");
  const parsed = Number(tooth);
  const usable = tooth.trim() !== "" && Number.isInteger(parsed) && parsed > 0;
  return (
    <div data-role="adopt-proposal" className="adopt-proposal">
      <span className="adopt-proposal__facts">
        Detected cap — {proposal.facts}
      </span>
      <label className="adopt-proposal__tooth">
        tooth
        <input
          data-role="adopt-tooth"
          className="scan-upload__input adopt-proposal__input"
          type="number"
          min={1}
          value={tooth}
          disabled={saving}
          onChange={(event) => setTooth(event.target.value)}
        />
      </label>
      <button
        type="button"
        data-role="adopt-go"
        className="button button--primary button--small"
        disabled={saving || !usable}
        onClick={() => onAdopt(proposal.center, parsed)}
      >
        {saving ? "Adopting…" : "Adopt as a site"}
      </button>
      {error !== null && (
        <span data-role="adopt-error" role="alert" className="panel__error">
          {error}
        </span>
      )}
    </div>
  );
}

/** The chip's demo clothes: pass/marginal/rescan traffic-light tones, muted "none". */
function captureChipClass(verdict: string | null): string {
  return verdict === null
    ? "chip chip--capture-none"
    : `chip chip--capture-${verdict}`;
}

interface RemarkSiteControlProps {
  readonly tooth: number;
  /** THE WORDS SHOWN, AWAITING CONSENT (client 2026-08-01) — true only while a
   * reset the BFF would actually cause has been named and not yet confirmed. */
  readonly confirming: boolean;
  /** the next stage click is the NEW centre for this tooth */
  readonly armed: boolean;
  readonly saving: boolean;
  /** the BFF's own refusal, verbatim */
  readonly error: string | null;
  readonly onAsk: () => void;
  readonly onConfirm: () => void;
  readonly onCancel: () => void;
}

/**
 * RE-MARK THIS CAP'S CENTRE (client 2026-08-01, the tooth-29 gap: a detector
 * centre visibly off the cap, and no door to correct it). THE BLAST RADIUS IN
 * WORDS BEFORE THE ACT (the visible-reset doctrine — DeclareStage's
 * SwitchConfirm, mirrored): a re-mark that would retire a preview, a review, the
 * current run or anything signed over it says so and waits for an explicit
 * confirm BEFORE the pick is armed, never discovered as a reset after the click
 * already landed. A re-mark with nothing to retire (domain/intake.
 * remarkRetiresSomething) arms straight away — a confirmation over zero
 * consequences would be the checkbox-over-nothing AM-8 already forbids for a
 * system switch.
 */
function RemarkSiteControl({
  tooth,
  confirming,
  armed,
  saving,
  error,
  onAsk,
  onConfirm,
  onCancel,
}: RemarkSiteControlProps) {
  return (
    <div data-role="remark-site" className="panel__actions">
      {confirming ? (
        <div data-role="remark-confirm" role="alert" className="switch-confirm">
          <p className="switch-confirm__words">{remarkWords(tooth)}</p>
          <div className="switch-confirm__actions">
            <button
              type="button"
              data-role="remark-confirm-go"
              className="button button--primary button--small"
              onClick={onConfirm}
            >
              Re-mark this cap's centre
            </button>
            <button
              type="button"
              data-role="remark-confirm-cancel"
              className="button button--secondary button--small"
              onClick={onCancel}
            >
              Keep the current centre
            </button>
          </div>
        </div>
      ) : armed ? (
        <>
          <p data-role="remark-prompt" className="panel__hint">
            Click the new centre for tooth {tooth} on the scan.
          </p>
          <button
            type="button"
            data-role="remark-cancel"
            className="button button--ghost button--small"
            disabled={saving}
            onClick={onCancel}
          >
            Cancel
          </button>
        </>
      ) : (
        <button
          type="button"
          data-role="remark-ask"
          className="button button--ghost button--small"
          onClick={onAsk}
        >
          Re-mark this cap's centre
        </button>
      )}
      {saving && (
        <div data-role="remark-saving" className="busy-state" role="status">
          <span className="busy-state__spinner" aria-hidden="true" />
          <span>Saving the new centre…</span>
        </div>
      )}
      {error !== null && (
        <div data-role="remark-error" role="alert" className="panel__error">
          {error}
        </div>
      )}
    </div>
  );
}

interface RimPointsControlProps {
  readonly tooth: number;
  /** How many points a STANDING (already-PUT) session carries — `site.rim_points`'s
   *  own length, never the live in-progress count below. */
  readonly existingCount: number;
  /** ARMED: the next several clicks on the scan collect this site's rim border. */
  readonly armed: boolean;
  /** The running count the viewer's collect-mode has reported this session. */
  readonly liveCount: number;
  readonly saving: boolean;
  readonly deleting: boolean;
  /** the BFF's own refusal, verbatim (whichever of PUT/DELETE last failed) */
  readonly error: string | null;
  readonly onArm: () => void;
  readonly onFinish: () => void;
  readonly onCancel: () => void;
  readonly onClear: () => void;
}

/**
 * RIM BORDER POINTS (§10-AL, task #33 — client: "we lost the tool we had in the demo
 * where we made points around the border of the healing cap in the scan"). An INTAKE
 * capture aid: several clicks around a cap's visible rim feed the capture assessment's
 * rim-diameter read, never a seat (the BFF's own `RimPointsIn` doc; §10-AH already
 * measured that a pair-shaped re-mark seed loses to the bare click on the DEV metric,
 * so this tool is scoped to intake capture only, on purpose, not built toward ADJUST).
 *
 * `RemarkSiteControl`'s direct sibling in shape (idle / armed / saving, the BFF's own
 * refusal shown verbatim) but NOT a reset door: recording rim points changes no centre
 * and retires no preview, review or run, so there is no blast-radius confirmation to
 * show first the way re-marking the centre has one.
 */
function RimPointsControl({
  tooth,
  existingCount,
  armed,
  liveCount,
  saving,
  deleting,
  error,
  onArm,
  onFinish,
  onCancel,
  onClear,
}: RimPointsControlProps) {
  return (
    <div data-role="rim-points" className="panel__actions">
      {armed ? (
        <>
          <p data-role="rim-points-prompt" className="panel__hint">
            Click points around tooth {tooth}&rsquo;s visible border.{" "}
            {rimPointsCountWords(liveCount)}
          </p>
          <button
            type="button"
            data-role="rim-points-finish"
            className="button button--primary button--small"
            disabled={saving || !canFinishRimPoints(liveCount)}
            onClick={onFinish}
          >
            {saving ? "Saving…" : "Finish"}
          </button>
          <button
            type="button"
            data-role="rim-points-cancel"
            className="button button--ghost button--small"
            disabled={saving}
            onClick={onCancel}
          >
            Cancel
          </button>
        </>
      ) : (
        <>
          <button
            type="button"
            data-role="rim-points-ask"
            className="button button--ghost button--small"
            onClick={onArm}
          >
            Rim border points
          </button>
          {existingCount > 0 && (
            <>
              <span data-role="rim-points-count" className="chip chip--gate">
                {rimPointsPlacedWords(existingCount)}
              </span>
              <button
                type="button"
                data-role="rim-points-clear"
                className="button button--ghost button--small"
                disabled={deleting}
                onClick={onClear}
              >
                {deleting ? "Clearing…" : "Clear"}
              </button>
            </>
          )}
        </>
      )}
      {error !== null && (
        <div data-role="rim-points-error" role="alert" className="panel__error">
          {error}
        </div>
      )}
    </div>
  );
}

/**
 * The site queue's Intake face: tooth, status, the SERVER's evidence for this site,
 * capture chip — the demo's stepper list language.
 *
 * No longer read-only (client 2026-07-31): a row is the operator's pick, and the pick
 * is what the 3D stage frames. The row carries no confidence percentage even though
 * the design prototype has one — see domain/intake.siteEvidence for why there is no
 * such number to render.
 */
function SiteList({
  detail,
  activeTooth,
  onSelectSite,
  pickArmed,
  pickMiss,
  onArmPick,
  onCancelPick,
  remarkConfirming,
  remarkArmed,
  remarkSaving,
  remarkError,
  onAskRemark,
  onConfirmRemark,
  onCancelRemark,
  adoptSaving,
  adoptError,
  onAdopt,
  detectorConfirming,
  detectorSaving,
  detectorError,
  onUseDetectorCentre,
  onConfirmDetectorCentre,
  onCancelDetectorCentre,
  rimPointsArmedTooth,
  rimPointsLiveCount,
  rimPointsSaving,
  rimPointsDeleting,
  rimPointsError,
  onArmRimPoints,
  onFinishRimPoints,
  onCancelRimPoints,
  onClearRimPoints,
}: SiteListProps) {
  const picker = sitePickerOffered(detail.sites);
  const adoptable = adoptableProposals(detail);
  const active = detail.sites.find((s) => s.tooth === activeTooth) ?? null;
  return (
    <section data-role="intake-sites" className="panel">
      <h3 className="panel__title">Sites</h3>
      <ul className="decode-stepper__overview">
        {detail.sites.map((site) => {
          const discriminator = discriminatorEvidenceSentence(detail, site);
          const curveHonesty = curveHonestySentence(detail, site);
          const rimPointCount = site.rim_points?.length ?? 0;
          const borderDisagreement = site.border_click_disagreement_mm ?? null;
          const stacked =
            discriminator !== null ||
            curveHonesty !== null ||
            borderDisagreement !== null;
          return (
            <li key={site.tooth} className="intake-site">
              <button
                type="button"
                data-role="site-row"
                data-tooth={site.tooth}
                aria-pressed={site.tooth === activeTooth}
                className={`decode-stepper__item intake-site__row${
                  stacked ? " decode-stepper__item--stacked" : ""
                }${site.tooth === activeTooth ? " decode-stepper__item--active" : ""}`}
                title="Frame this site on the scan"
                onClick={() => onSelectSite(site.tooth)}
              >
                <span className="decode-stepper__position">
                  Tooth {site.tooth}{" "}
                  <span className="decode-stepper__tooth">{site.status}</span>
                </span>
                <span data-role="site-evidence" className="intake-site__evidence">
                  {siteEvidence(detail, site).map((fact) => (
                    <span
                      key={fact.key}
                      data-fact={fact.key}
                      className="intake-site__fact"
                      title={fact.title}
                    >
                      {fact.text}
                    </span>
                  ))}
                </span>
                {/* THE RIM BORDER-POINTS ECHO (§10-AL, task #33 item 4): the operator's
                    own standing measurement, on the SAME fact styling siteEvidence's
                    array renders — absent for a site nobody has clicked points on. */}
                {rimPointCount > 0 && (
                  <span
                    data-role="site-rim-points-count"
                    className="intake-site__fact"
                    title="Rim border points recorded for this site — feeds this site's capture read, never its seat."
                  >
                    {rimPointsPlacedWords(rimPointCount)}
                  </span>
                )}
                <span
                  data-role="capture-chip"
                  data-verdict={site.capture?.verdict ?? "none"}
                  className={captureChipClass(site.capture?.verdict ?? null)}
                  title={site.capture?.checks.map((c) => c.message).join(" ") ?? undefined}
                >
                  {captureChipLabel(site.capture)}
                </span>
                {/* THE DETECTOR'S OWN WHY (clinical-pipeline-plan.md 1a): the same
                    full-width muted line Declare's queue uses for its state
                    sentence — a third thing that belongs under the row, not
                    squeezed into the evidence column's chips. Absent entirely for
                    a hand-marked site or a record predating the fields, never a
                    sentence built from a zeroed measurement. */}
                {discriminator !== null && (
                  <span data-role="site-discriminator" className="decode-stepper__state">
                    {discriminator}
                  </span>
                )}
                {curveHonesty !== null && (
                  <span data-role="site-curve-honesty" className="decode-stepper__state">
                    {curveHonesty}
                  </span>
                )}
                {/* THE BORDER CLICKS' OWN DISAGREEMENT (§10-AL, task #33 item 4) — the
                    same muted full-width line as the discriminator above, served only
                    post-run and only when the run's row read four or more border
                    clicks to disagree over. */}
                {borderDisagreement !== null && (
                  <span data-role="site-border-disagreement" className="decode-stepper__state">
                    {borderClickDisagreementWords(borderDisagreement)}
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
      {active !== null && (
        <>
          <p data-role="site-framed" className="panel__hint">
            {siteCentre(active) !== null
              ? `Tooth ${active.tooth} is framed on the scan.`
              : `Tooth ${active.tooth} has no centre yet — the stage cannot frame it.`}
          </p>
          {(() => {
            /* THE STALE CURATED CENTRE, SAID OUT LOUD (client 2026-08-01: "centre is
               wrong from the beginning") — and since 2026-08-04, ANSWERABLE IN ONE
               CLICK. The fleet table put numbers on it: the cases the client calls
               well-aligned carry centres agreeing with the live detector to
               0.03-0.23mm; the ones they call wrong disagree by 2.2-9.0mm. The act
               is the EXISTING re-mark PUT with the detector's own point — operator
               consent stays (cap7020's curated seed BEATS its detector proposal, so
               a silent preference would break the fleet's best case), and the same
               retirement ceremony fires when a preview/review would fall. */
            const off = detectorDisagreement(detail, active.tooth);
            if (off === null) return null;
            return (
              <div data-role="centre-disagreement" className="panel__hint">
                {/* No provenance claim: the shown centre may be the case's seed OR
                    the operator's own re-mark (which siteCentre prefers), and on
                    cap6020 the re-mark measured BETTER than the detector — the
                    sentence states the disagreement and leaves the verdict to the
                    operator looking at the marker. */}
                <p className="intake-centre__words">
                  The detector reads this cap&rsquo;s centre {off.mm.toFixed(2)}mm
                  from the centre shown. If the marker looks off the cap, adopt the
                  detector&rsquo;s centre or re-mark it by hand.
                </p>
                {detectorConfirming ? (
                  <div
                    data-role="detector-centre-confirm"
                    role="alert"
                    className="switch-confirm"
                  >
                    <p className="switch-confirm__words">
                      {remarkWords(active.tooth)}
                    </p>
                    <div className="switch-confirm__actions">
                      <button
                        type="button"
                        data-role="detector-centre-go"
                        className="button button--primary button--small"
                        disabled={detectorSaving}
                        onClick={() => onConfirmDetectorCentre(active.tooth, off.detected)}
                      >
                        Adopt the detector&rsquo;s centre
                      </button>
                      <button
                        type="button"
                        data-role="detector-centre-cancel"
                        className="button button--secondary button--small"
                        disabled={detectorSaving}
                        onClick={onCancelDetectorCentre}
                      >
                        Keep the centre shown
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    type="button"
                    data-role="use-detector-centre"
                    className="button button--secondary button--small"
                    disabled={detectorSaving}
                    onClick={() => onUseDetectorCentre(active.tooth, off.detected)}
                  >
                    {detectorSaving
                      ? "Adopting the detector's centre…"
                      : `Use the detector's centre (${off.mm.toFixed(2)}mm away)`}
                  </button>
                )}
                {detectorError !== null && (
                  <span
                    data-role="detector-centre-error"
                    role="alert"
                    className="panel__error"
                  >
                    {detectorError}
                  </span>
                )}
              </div>
            );
          })()}
          <RemarkSiteControl
            tooth={active.tooth}
            confirming={remarkConfirming}
            armed={remarkArmed}
            saving={remarkSaving}
            error={remarkError}
            onAsk={onAskRemark}
            onConfirm={onConfirmRemark}
            onCancel={onCancelRemark}
          />
          <RimPointsControl
            tooth={active.tooth}
            existingCount={active.rim_points?.length ?? 0}
            armed={rimPointsArmedTooth === active.tooth}
            liveCount={rimPointsLiveCount}
            saving={rimPointsSaving}
            deleting={rimPointsDeleting}
            error={rimPointsError}
            onArm={() => onArmRimPoints(active.tooth)}
            onFinish={onFinishRimPoints}
            onCancel={onCancelRimPoints}
            onClear={() => onClearRimPoints(active.tooth)}
          />
        </>
      )}
      {/* The other direction of the same pick: point at the cap instead of reading the
          list. The stage's one-shot point pick resolves it (MainStage's markArmed door),
          and domain/intake.pickSiteAt turns the surface point into a tooth. */}
      {pickArmed ? (
        <p data-role="pick-prompt" className="panel__hint">
          Click a cap on the scan to select its site.{" "}
          <button
            type="button"
            data-role="pick-cancel"
            className="button button--ghost button--small"
            onClick={onCancelPick}
          >
            Cancel
          </button>
        </p>
      ) : picker.offered ? (
        <div className="panel__actions">
          <button
            type="button"
            data-role="pick-arm"
            className="button button--secondary button--small"
            onClick={onArmPick}
          >
            Pick a site on the scan
          </button>
        </div>
      ) : (
        /* A PICK THAT CANNOT CHANGE ANYTHING IS NOT OFFERED (client 2026-08-01: "this
           button does nothing"). It armed a mode whose only outcome was re-selecting
           the site already selected. The reason is stated rather than the control
           silently vanishing — a missing button is its own small mystery. */
        <p data-role="pick-unavailable" className="panel__hint">
          {picker.why}
        </p>
      )}
      {pickMiss !== null && (
        <p data-role="pick-miss" className="panel__hint intake-site__miss">
          {pickMiss}
        </p>
      )}
      {adoptable.length > 0 && (
        /* THE UPLOADED-ARCH DEADLOCK (client 2026-08-04). This line used to say
           "Declare assigns teeth" — an act Declare never had, promised on a case
           the flow would not let past Intake (Declare needs a site, and a
           tooth-less proposal never became one). The adopt rows ARE the way
           forward now: the detector's centre, the operator's tooth number, the
           missed-cap door's own act. */
        <>
          <p data-role="unassigned-proposals" className="panel__hint">
            The detector found {adoptable.length} cap
            {adoptable.length === 1 ? "" : "s"} no site carries yet — name the
            tooth to adopt {adoptable.length === 1 ? "it" : "each"} as a site.
          </p>
          {adoptable.map((proposal) => (
            <AdoptProposalControl
              key={proposal.index}
              proposal={proposal}
              defaultTooth={
                defaultToothForMark({
                  sites: detail.sites,
                  proposals: [],
                  center: proposal.center,
                  jaw: detail.choices.effective_jaw.value ?? null,
                })?.tooth ?? null
              }
              saving={adoptSaving}
              error={adoptError}
              onAdopt={onAdopt}
            />
          ))}
        </>
      )}
    </section>
  );
}

export interface ChoicesPanelProps {
  readonly detail: CaseSessionDetail;
  readonly saving: boolean;
  readonly error: string | null;
  readonly onChoice: (patch: Partial<ChoicesUpdate>) => void;
  /** §10-AM built: the jaw cross-check's caution dialog, open-state via PROP —
   *  the §10-AN slice-C precedent (AdjustDock's `cautionsOpen`) applied here so a
   *  static render can pin the dialog open without simulating a click. Optional
   *  with defaults: every existing caller (and every fixture predating this)
   *  renders it closed. */
  readonly jawAdvisoryOpen?: boolean;
  readonly onOpenJawAdvisory?: () => void;
  readonly onCloseJawAdvisory?: () => void;
}

/** The prefilled-choice chip (client 2026-07-27): the SERVER's attribution, worn
 * exactly like the system bar's "suggested" tag — "suggested" on a fallback the
 * case supplied, "default" on the standing relief, "read from the scan" on the
 * jaw's new §10-AM rung (the raw word "scan" alone would not say where a reading
 * comes from). An operator's chosen value carries no chip, and "none" has no
 * value to tag. */
function ChoiceSourceChip({
  source,
  choice,
}: {
  readonly source: "chosen" | "scan" | "suggested" | "default" | "none";
  readonly choice: string;
}) {
  if (source === "chosen" || source === "none") return null;
  return (
    <span
      data-role="choice-source"
      data-choice={choice}
      className="library-badge library-badge--suggested"
    >
      {source === "scan" ? "read from the scan" : source}
    </span>
  );
}

/** The case-level choices — rendered from the BFF's EFFECTIVE values (client
 * 2026-07-27: the same chosen-??-suggested-??-default document the previews seat
 * with, each with its source chip), PUT whole on every change — the operator
 * changes them by the existing PUT; nothing here auto-writes a default. Parity
 * slice: the demo's selection-card language — the decode select, the Upper/Lower
 * pair, the relief input beside its measured ceilings with the amber
 * over-ceiling tone. */
export function ChoicesPanel({
  detail,
  saving,
  error,
  onChoice,
  jawAdvisoryOpen = false,
  onOpenJawAdvisory = () => undefined,
  onCloseJawAdvisory = () => undefined,
}: ChoicesPanelProps) {
  const chosen = detail.choices;
  const construction = chosen.effective_construction.value ?? "";
  const jaw = chosen.effective_jaw.value;
  const relief = chosen.effective_relief.value ?? chosen.gingival_offset_default_mm;
  // §10-AM built: non-null exactly when the SERVER found a contradiction between
  // the scan's own reading and the effective jaw — composed server-side, rendered
  // verbatim (never recomposed here). The RAW reading (for the one-click fix's
  // button highlight) lives on `detection`, not `choices`: `effective_jaw` only
  // carries it while nothing is chosen, and the advisory only exists once
  // something IS (§10-AM: a cross-check, never a silent correction).
  const jawAdvisory = chosen.jaw_advisory ?? null;
  const geometryJaw = detail.detection?.jaw_reading ?? null;
  const jawAdvisoryDialogRef = useRef<HTMLElement | null>(null);
  useDialogEscape(jawAdvisoryOpen, onCloseJawAdvisory);
  useDialogFocus(jawAdvisoryOpen, jawAdvisoryDialogRef);
  return (
    <section data-role="intake-choices" className="panel">
      <h3 className="panel__title">Case-level choices</h3>
      <div className="decode-column">
        <div>
          <h4 className="decode-section__title">
            Construction part
            <ChoiceSourceChip
              source={chosen.effective_construction.source}
              choice="construction"
            />
          </h4>
          <select
            data-role="choice-construction"
            className={`decode-select${construction === "" ? " decode-select--needs" : ""}`}
            value={construction}
            onChange={(event) =>
              onChoice({ construction_path: event.target.value || null })
            }
          >
            <option value="">choose a construction part…</option>
            {constructionOptions(detail).map((option) => (
              <option key={option.path_id} value={option.path_id}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <h4 className="decode-section__title">
            Jaw
            <ChoiceSourceChip source={chosen.effective_jaw.source} choice="jaw" />
            {/* THE JAW CROSS-CHECK CHIP (§10-AM built). Non-null `jaw_advisory` IS
                the trigger — this app never re-derives the contradiction, only
                renders that one served fact exists. The advisory never blocks:
                jaw stays the operator's choice, one click away on the buttons
                below (the geometry's own answer, highlighted). */}
            {jawAdvisory !== null && (
              <button
                type="button"
                data-role="jaw-advisory-chip"
                className="chip chip--exception caution-chip"
                onClick={onOpenJawAdvisory}
              >
                ⚠ check jaw
              </button>
            )}
          </h4>
          <div data-role="choice-jaw" className="decode-jaw" role="group" aria-label="Jaw">
            {JAW_CHOICES.map((candidate) => {
              const isGeometryAnswer = jawAdvisory !== null && candidate === geometryJaw;
              return (
                <button
                  key={candidate}
                  type="button"
                  aria-pressed={candidate === jaw}
                  data-geometry-answer={isGeometryAnswer ? "true" : undefined}
                  className={`decode-jaw__option${
                    candidate === jaw ? " decode-jaw__option--selected" : ""
                  }${isGeometryAnswer ? " decode-jaw__option--geometry" : ""}`}
                  onClick={() => onChoice({ jaw: candidate })}
                >
                  {candidate}
                </button>
              );
            })}
          </div>
        </div>
        <div>
          <h4 className="decode-section__title">
            Gingival relief
            <ChoiceSourceChip source={chosen.effective_relief.source} choice="relief" />
          </h4>
          <label className="decode-offset">
            <input
              data-role="choice-relief"
              className="decode-offset__input"
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={relief}
              onChange={(event) => {
                const parsed = Number(event.target.value);
                onChoice({
                  gingival_offset_mm: Number.isFinite(parsed) ? parsed : null,
                });
              }}
            />
            <span className="decode-offset__unit">mm</span>
          </label>
          <ul data-role="relief-ceilings" className="relief-ceilings">
            {ceilingReadouts(detail, chosen.gingival_offset_mm).map((readout) => (
              <li
                key={readout.variant}
                data-exceeded={readout.exceeded}
                className="relief-ceilings__item"
              >
                {readout.line}
              </li>
            ))}
          </ul>
        </div>
        {/* THE TURNAROUND CHOOSER (§10-AB.4, unblocked by AB.1's confirmed card):
            pills like the jaw's, money the server's — each option prints its served
            per-site unit via turnaroundPillLabel. No served options, no chooser:
            a pill with invented money is exactly what this panel must never grow. */}
        {(chosen.turnaround_options ?? []).length > 0 && (
          <div>
            <h4 className="decode-section__title">
              Turnaround
              <ChoiceSourceChip
                source={chosen.effective_turnaround?.source ?? "default"}
                choice="turnaround"
              />
            </h4>
            <div
              data-role="choice-turnaround"
              className="decode-jaw"
              role="group"
              aria-label="Turnaround"
            >
              {(chosen.turnaround_options ?? []).map((option) => (
                <button
                  key={option.value}
                  type="button"
                  aria-pressed={option.value === chosen.effective_turnaround?.value}
                  className={`decode-jaw__option${
                    option.value === chosen.effective_turnaround?.value
                      ? " decode-jaw__option--selected"
                      : ""
                  }`}
                  onClick={() =>
                    onChoice({ turnaround: option.value as "standard" | "rush" })
                  }
                >
                  {turnaroundPillLabel(option)}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
      {saving && (
        <div data-role="choices-saving" className="busy-state" role="status">
          <span className="busy-state__spinner" aria-hidden="true" />
          <span>Saving choices…</span>
        </div>
      )}
      {error !== null && (
        <div data-role="choices-error" role="alert" className="panel__error">
          {error}
        </div>
      )}
      {/* THE JAW ADVISORY MODAL (§10-AM built). Same decode-dialog chrome as every
          other dialog in this app (AdjustDock's pair-caution dialog is the direct
          precedent) — scrim, role="dialog", escape + focus trap — carrying the
          server's own sentence VERBATIM, nothing folded or paraphrased. */}
      {jawAdvisoryOpen && jawAdvisory !== null && (
        <div
          data-role="jaw-advisory-backdrop"
          className="decode-dialog-backdrop"
          onClick={onCloseJawAdvisory}
        >
          <section
            ref={jawAdvisoryDialogRef}
            data-role="jaw-advisory-dialog"
            className="decode-dialog decode-dialog--narrow"
            role="dialog"
            aria-modal="true"
            aria-labelledby="jaw-advisory-heading"
            tabIndex={-1}
            onClick={(event) => event.stopPropagation()}
          >
            <header className="decode-dialog__header">
              <div>
                <h2 id="jaw-advisory-heading" className="decode-dialog__title">
                  Check the jaw choice
                </h2>
                <p className="decode-dialog__subject">
                  The server's own words. Nothing here is a summary of them.
                </p>
              </div>
              <button
                type="button"
                data-role="jaw-advisory-close"
                data-autofocus=""
                className="button button--ghost button--small"
                onClick={onCloseJawAdvisory}
              >
                Close
              </button>
            </header>
            <div className="decode-dialog__body">
              <p data-role="jaw-advisory-text">{jawAdvisory}</p>
            </div>
          </section>
        </div>
      )}
    </section>
  );
}


export interface MarkMissedCapProps {
  readonly armed: boolean;
  /** The centre placed but not yet named — a mark is only a site once it has a tooth. */
  readonly pending: readonly number[] | null;
  readonly saving: boolean;
  readonly error: string | null;
  readonly onArm: () => void;
  readonly onCancel: () => void;
  readonly onTooth: (tooth: string) => void;
  readonly tooth: string;
  /** Where the pre-filled tooth came from — the prompt names it (markPlacedWords). */
  readonly source?: "detector" | "free-label" | null;
  readonly onSubmit: () => void;
}

/**
 * MARK A CAP THE DETECTOR MISSED (client 2026-07-28).
 *
 * Detection finds 8 of the 10 sites on this fleet. The other two were unworkable —
 * a site's centre lived only in the case record, which the ingest writes and an
 * operator cannot. This is the door.
 *
 * TWO STEPS, deliberately: place the centre, THEN name the tooth. Asking for the
 * tooth first would make the operator hold a number in their head while hunting the
 * cap in 3D; asking afterwards lets them point at what they can see and label it
 * once it is unambiguous. The centre is sent exactly as clicked — the re-click
 * pair-integrity rule says a human's mark is fixed here or refused, never quietly
 * re-centred downstream.
 */
export function MarkMissedCap({
  armed,
  pending,
  saving,
  error,
  onArm,
  onCancel,
  onTooth,
  tooth,
  source = null,
  onSubmit,
}: MarkMissedCapProps) {
  return (
    <section data-role="mark-missed" className="panel">
      <h3 className="panel__title">A cap the detection missed</h3>
      {!armed && pending === null ? (
        <>
          <p className="panel__hint">
            Detection does not always find every cap. If you can see one the list
            above does not have, mark it here.
          </p>
          <button
            type="button"
            data-role="mark-arm"
            className="button button--secondary button--small"
            onClick={onArm}
          >
            Mark a missed cap
          </button>
        </>
      ) : pending === null ? (
        <>
          <p data-role="mark-prompt" className="panel__hint">
            Click the centre of the cap on the scan.
          </p>
          <button
            type="button"
            data-role="mark-cancel"
            className="button button--ghost button--small"
            onClick={onCancel}
          >
            Cancel
          </button>
        </>
      ) : (
        <>
          <p data-role="mark-placed" className="panel__hint">
            {markPlacedWords(source)}
          </p>
          <label className="decode-offset">
            <input
              data-role="mark-tooth"
              className="decode-offset__input"
              type="number"
              min={1}
              max={32}
              value={tooth}
              onChange={(event) => onTooth(event.target.value)}
            />
          </label>
          <div className="panel__actions">
            <button
              type="button"
              data-role="mark-submit"
              className="button button--primary button--small"
              disabled={saving || tooth.trim() === ""}
              onClick={onSubmit}
            >
              {saving ? "Adding the site…" : "Add this site"}
            </button>
            <button
              type="button"
              data-role="mark-cancel"
              className="button button--ghost button--small"
              disabled={saving}
              onClick={onCancel}
            >
              Discard the mark
            </button>
          </div>
        </>
      )}
      {error !== null && (
        <div data-role="mark-error" role="alert" className="panel__error">
          {error}
        </div>
      )}
    </section>
  );
}

export interface IntakeStageViewProps {
  readonly detail: CaseSessionDetail;
  readonly detectPhase: DetectPhase;
  readonly savingChoices: boolean;
  readonly choicesError: string | null;
  readonly onChoice: (patch: Partial<ChoicesUpdate>) => void;
  readonly onRetryDetect: () => void;
  /** Marking a cap detection missed (client 2026-07-28). */
  readonly markArmed?: boolean;
  readonly markPending?: readonly number[] | null;
  readonly markTooth?: string;
  readonly markSource?: "detector" | "free-label" | null;
  readonly markSaving?: boolean;
  readonly markError?: string | null;
  readonly onArmMark?: () => void;
  readonly onCancelMark?: () => void;
  readonly onMarkTooth?: (tooth: string) => void;
  readonly onStagePoint?: (point: readonly [number, number, number]) => void;
  /** An armed click that hit only the sky — the pick stays armed; the panel says so. */
  readonly onStageMiss?: () => void;
  readonly onSubmitMark?: () => void;
  /** Picking a site — from its row, or by clicking the cap on the scan (client 2026-07-31). */
  readonly activeTooth?: number | null;
  readonly onSelectSite?: (tooth: number) => void;
  readonly pickArmed?: boolean;
  readonly pickMiss?: string | null;
  readonly onArmPick?: () => void;
  readonly onCancelPick?: () => void;
  /** Re-marking the ACTIVE site's centre (client 2026-08-01, the tooth-29 gap). */
  readonly remarkConfirming?: boolean;
  readonly remarkArmed?: boolean;
  readonly remarkSaving?: boolean;
  readonly remarkError?: string | null;
  readonly onAskRemark?: () => void;
  readonly onConfirmRemark?: () => void;
  readonly onCancelRemark?: () => void;
  /** Adopting a detected cap no site carries (client 2026-08-04). */
  readonly adoptSaving?: boolean;
  readonly adoptError?: string | null;
  readonly onAdopt?: (center: readonly number[], tooth: number) => void;
  /** Adopting the detector's centre for an existing site (the fleet table's lever). */
  readonly detectorConfirming?: boolean;
  readonly detectorSaving?: boolean;
  readonly detectorError?: string | null;
  readonly onUseDetectorCentre?: (tooth: number, point: readonly number[]) => void;
  readonly onConfirmDetectorCentre?: (tooth: number, point: readonly number[]) => void;
  readonly onCancelDetectorCentre?: () => void;
  /** RIM BORDER POINTS (§10-AL, task #33) — see RimPointsControl. */
  readonly rimPointsArmedTooth?: number | null;
  readonly rimPointsLiveCount?: number;
  readonly rimPointsSaving?: boolean;
  readonly rimPointsDeleting?: boolean;
  readonly rimPointsError?: string | null;
  readonly onArmRimPoints?: (tooth: number) => void;
  readonly onRimPointsChanged?: (points: readonly (readonly [number, number, number])[]) => void;
  readonly onFinishRimPoints?: () => void;
  readonly onCancelRimPoints?: () => void;
  readonly onClearRimPoints?: (tooth: number) => void;
  /** §10-AM built: the jaw cross-check's caution dialog, threaded to `ChoicesPanel`. */
  readonly jawAdvisoryOpen?: boolean;
  readonly onOpenJawAdvisory?: () => void;
  readonly onCloseJawAdvisory?: () => void;
}

/** The stage's whole surface, pure payload → markup — statically testable. */
export function IntakeStageView({
  detail,
  detectPhase,
  savingChoices,
  choicesError,
  onChoice,
  onRetryDetect,
  markArmed = false,
  markPending = null,
  markTooth = "",
  markSource = null,
  markSaving = false,
  markError = null,
  onArmMark = () => undefined,
  onCancelMark = () => undefined,
  onMarkTooth = () => undefined,
  onStagePoint = () => undefined,
  onStageMiss = () => undefined,
  onSubmitMark = () => undefined,
  activeTooth = null,
  onSelectSite = () => undefined,
  pickArmed = false,
  pickMiss = null,
  onArmPick = () => undefined,
  onCancelPick = () => undefined,
  remarkConfirming = false,
  remarkArmed = false,
  remarkSaving = false,
  remarkError = null,
  onAskRemark = () => undefined,
  onConfirmRemark = () => undefined,
  onCancelRemark = () => undefined,
  adoptSaving = false,
  adoptError = null,
  onAdopt = () => undefined,
  detectorConfirming = false,
  detectorSaving = false,
  detectorError = null,
  onUseDetectorCentre = () => undefined,
  onConfirmDetectorCentre = () => undefined,
  onCancelDetectorCentre = () => undefined,
  rimPointsArmedTooth = null,
  rimPointsLiveCount = 0,
  rimPointsSaving = false,
  rimPointsDeleting = false,
  rimPointsError = null,
  onArmRimPoints = () => undefined,
  onRimPointsChanged = () => undefined,
  onFinishRimPoints = () => undefined,
  onCancelRimPoints = () => undefined,
  onClearRimPoints = () => undefined,
  jawAdvisoryOpen = false,
  onOpenJawAdvisory = () => undefined,
  onCloseJawAdvisory = () => undefined,
}: IntakeStageViewProps) {
  const facts = factsFromCaseSession(detail);
  const declareOpen = isReachable("declare", facts);
  const centred = facts.siteCentred ?? 0;
  return (
    /* Two regions for the workbench grid (display: contents on the root) — MIRRORED
       for this stage (comp page pass 2026-08-02, §10-AA): the comp's intake leads
       with the SCAN, its per-site rows directly under the viewer, and keeps the
       control cards in a narrow right column. The stage child renders first; the
       `.workbench:has(...)` rule in styles.css flips the grid's columns to match. */
    <div data-role="intake-stage" className="stage-contents">
      <div className="workbench__stage workbench__stage--intake">
        <section className="scan-panel">
          <header className="scan-panel__head">
            <h3 className="scan-panel__title">
              Scan {detail.case.scan_filename} · {detail.case.jaw}
            </h3>
            {/* the comp's "N / M marked" chip, from served facts: sites whose centre
                the payload carries, over the payload's site count */}
            <span data-role="centred-count" className="chip chip--gate">
              {centred} / {facts.siteTotal} centred
            </span>
          </header>
          <div className="scan-panel__stage">
            <MainStage
              caseId={detail.case.id}
              scanFilename={detail.case.scan_filename}
              sites={detail.sites}
              markers={detectionMarkers(detail)}
              activeTooth={activeTooth}
              /* The effective jaw, not the raw reading: if the operator has overridden
                 what the scan says, the view follows THEIR answer (client 2026-08-09). */
              jaw={detail.choices.effective_jaw.value}
              // ONE point-pick door, THREE callers (client 2026-07-31, extended
              // 2026-08-01): the stage arms the viewer's one-shot pick while the
              // missed-cap mark, the site picker OR a confirmed re-mark is armed, and
              // the container routes the resolved point to whichever asked.
              markArmed={markArmed || pickArmed || remarkArmed}
              onMark={onStagePoint}
              onMarkMissed={onStageMiss}
              // RIM BORDER POINTS' OWN DOOR (§10-AL, task #33) — the viewer's SEPARATE
              // multi-click collect-mode, not the single-shot pick markArmed shares
              // above; armed for at most one tooth, mutually exclusive with the pick
              // by the container's own "one door, one owner" discipline (see
              // IntakeStage's handleArmRimPoints).
              rimPointsTooth={rimPointsArmedTooth}
              onRimPointsChanged={onRimPointsChanged}
              rimPointsMaxPoints={MAX_RIM_POINTS}
            />
          </div>
          <SiteList
            detail={detail}
            activeTooth={activeTooth}
            onSelectSite={onSelectSite}
            pickArmed={pickArmed}
            pickMiss={pickMiss}
            onArmPick={onArmPick}
            onCancelPick={onCancelPick}
            remarkConfirming={remarkConfirming}
            remarkArmed={remarkArmed}
            remarkSaving={remarkSaving}
            remarkError={remarkError}
            onAskRemark={onAskRemark}
            onConfirmRemark={onConfirmRemark}
            onCancelRemark={onCancelRemark}
            adoptSaving={adoptSaving}
            adoptError={adoptError}
            onAdopt={onAdopt}
            detectorConfirming={detectorConfirming}
            detectorSaving={detectorSaving}
            detectorError={detectorError}
            onUseDetectorCentre={onUseDetectorCentre}
            onConfirmDetectorCentre={onConfirmDetectorCentre}
            onCancelDetectorCentre={onCancelDetectorCentre}
            rimPointsArmedTooth={rimPointsArmedTooth}
            rimPointsLiveCount={rimPointsLiveCount}
            rimPointsSaving={rimPointsSaving}
            rimPointsDeleting={rimPointsDeleting}
            rimPointsError={rimPointsError}
            onArmRimPoints={onArmRimPoints}
            onFinishRimPoints={onFinishRimPoints}
            onCancelRimPoints={onCancelRimPoints}
            onClearRimPoints={onClearRimPoints}
          />
        </section>
      </div>
      <div className="workbench__work">
        <CaptureBanner detail={detail} />
        {detectPhase.kind === "detecting" && (
          <div data-role="detect-busy" className="busy-state" role="status">
            <span className="busy-state__spinner" aria-hidden="true" />
            <span>Detecting implant sites…</span>
          </div>
        )}
        {detectPhase.kind === "failed" && (
          <div data-role="detect-error" role="alert" className="run-refusal">
            <strong className="run-refusal__title">Detection refused.</strong>
            <p className="run-refusal__detail">{detectPhase.detail}</p>
            <p className="run-refusal__next">
              <button
                type="button"
                className="button button--ghost button--small"
                onClick={onRetryDetect}
              >
                Try again
              </button>
            </p>
          </div>
        )}
        <MarkMissedCap
          armed={markArmed}
          pending={markPending}
          saving={markSaving}
          error={markError}
          onArm={onArmMark}
          onCancel={onCancelMark}
          onTooth={onMarkTooth}
          tooth={markTooth}
          source={markSource}
          onSubmit={onSubmitMark}
        />
        <ChoicesPanel
          detail={detail}
          saving={savingChoices}
          error={choicesError}
          onChoice={onChoice}
          jawAdvisoryOpen={jawAdvisoryOpen}
          onOpenJawAdvisory={onOpenJawAdvisory}
          onCloseJawAdvisory={onCloseJawAdvisory}
        />
        <div className="panel__actions panel__actions--advance">
          {declareOpen ? (
            <Link
              data-role="continue-declare"
              className="button button--primary"
              to={`/case/${detail.case.id}/declare`}
            >
              {centred === facts.siteTotal
                ? `Continue to Alignment · all ${facts.siteTotal} caps`
                : `Continue to Alignment · ${centred} of ${facts.siteTotal} caps`}
            </Link>
          ) : (
            <span
              data-role="continue-declare"
              aria-disabled="true"
              className="button button--secondary button--blocked"
            >
              Continue to Alignment — {blockedReason("declare", facts)}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

export interface IntakeStageProps {
  readonly detail: CaseSessionDetail;
  /** The shell owns the payload; every action's response replaces it whole. */
  readonly onDetail: (next: CaseSessionDetail) => void;
}

/** The container: auto-fires detection once, wires the choices PUT, renders truth. */
export function IntakeStage({ detail, onDetail }: IntakeStageProps) {
  const caseId = detail.case.id;
  const firedRef = useRef<string | null>(null);
  // §10-AM built: the jaw cross-check's caution dialog — owned here, exactly the
  // §10-AN slice-C precedent (AdjustStage's `cautionsOpen`).
  const [jawAdvisoryOpen, setJawAdvisoryOpen] = useState(false);

  /* MARKING A MISSED CAP (client 2026-07-28). Three states, and the middle one is
     the reason this is not a single form: ARMED (the next scan click is the centre),
     PLACED (a centre exists, awaiting its tooth), and idle. Optimism is OFF like
     everywhere else on this app — the site appears because the BFF returned a detail
     saying so, never because the click landed.

     ONE draft, not four useStates (audit 2026-07-31): the transitions that must not
     lose a placed centre are then named rules in domain/intake with their own tests,
     instead of four setters a caller can forget one of. `markSaving` stays separate —
     it is the request's phase, not part of what the operator drafted. */
  const [mark, setMark] = useState<MarkDraft>(EMPTY_MARK);
  const [markSaving, setMarkSaving] = useState(false);

  const resetMark = useCallback(() => setMark(EMPTY_MARK), []);

  const handleMarkPlaced = useCallback(
    (point: readonly [number, number, number]) => {
      // the click is spent — and the label fills itself (client 2026-08-06: "let me
      // mark it without asking me for which tooth"): the covering proposal's guess
      // when one speaks, else the jaw's next free number, provenance named.
      const fallback = defaultToothForMark({
        sites: detail.sites,
        proposals: detail.detection?.proposals ?? [],
        center: point,
        jaw: detail.choices.effective_jaw.value ?? null,
      });
      setMark((prev) => markOnPlace(prev, point, fallback));
    },
    [detail],
  );

  /* PICKING A SITE (client 2026-07-31). Purely a VIEW act — which site the stage
     frames and which row reads as chosen. Nothing here is persisted and nothing here
     is a verdict, so no PUT: the case's own facts are untouched by looking at a cap.
     The scan-side pick borrows the same one-shot point pick the missed-cap mark uses
     (the viewer arms exactly one), so the two modes are mutually exclusive by
     construction — arming either disarms the other. */
  const [activeTooth, setActiveTooth] = useState<number | null>(null);
  const [pickArmed, setPickArmed] = useState(false);
  const [pickMiss, setPickMiss] = useState<string | null>(null);

  /* RIM BORDER POINTS (§10-AL, task #33). Its own door onto the viewer's SEPARATE
     multi-click collect-mode (MainStage's rimPointsTooth/onRimPointsChanged, not the
     single-shot point pick the three doors above share) — but the SAME "one door, one
     owner" discipline: arming it disarms the pick/mark/remark doors below (see
     handleArmRimPoints), and each of THEM disarms this one in turn, so the operator is
     never shown two doors open onto the scan at once. rimPointsDraft mirrors the
     viewer's own live session via onRimPointsChanged — read at Finish time rather than
     pulled imperatively, since nothing outside MainStage can reach the controller. */
  const [rimPointsArmedTooth, setRimPointsArmedTooth] = useState<number | null>(null);
  const [rimPointsDraft, setRimPointsDraft] = useState<
    readonly (readonly [number, number, number])[]
  >([]);
  const [rimPointsSaving, setRimPointsSaving] = useState(false);
  const [rimPointsDeleting, setRimPointsDeleting] = useState(false);
  const [rimPointsError, setRimPointsError] = useState<string | null>(null);

  /* THE STAGE OPENS ON A SITE (client 2026-08-04). Until now it opened on none, and
     since the re-mark control renders only for the ACTIVE site, the act was
     unreachable without first clicking a row nothing asked the operator to click —
     on a single-site case the page even said the site was "already the active one".
     Adjust's queue has always opened on its first flagged site for the same reason.
     Only the OPENING is defaulted: once a tooth is chosen (or cleared by a pick),
     this leaves it alone. */
  useEffect(() => {
    if (activeTooth !== null) return;
    const opening = openingSiteFor(detail.sites);
    if (opening !== null) setActiveTooth(opening);
  }, [activeTooth, detail.sites]);

  const handleSelectSite = useCallback((tooth: number) => {
    setActiveTooth(tooth);
    setPickArmed(false);
    setPickMiss(null);
    // a re-mark in flight is ABOUT the previously active site — a new selection
    // makes its words (and any armed pick) stale, so it is discarded, not carried.
    // The detector-centre confirm falls with it (review 2026-08-04: it COMMITS a
    // write, and its consent was judged for the previous tooth).
    setRemarkConfirming(false);
    setRemarkArmed(false);
    setRemarkError(null);
    setDetectorConfirming(false);
    setDetectorError(null);
    // an in-progress rim-points session is ABOUT the previously active site too — a
    // new selection makes it stale for the same reason the re-mark words above are
    // (RimPointsControl only renders for the ACTIVE site), so it is discarded.
    setRimPointsArmedTooth(null);
    setRimPointsError(null);
  }, []);

  const handleArmPick = useCallback(() => {
    setPickArmed(true);
    setPickMiss(null);
    // one point pick, one owner — DISARM the mark, never discard it (audit
    // 2026-07-31: this used to reset the whole draft, silently destroying a placed
    // centre the operator had hunted down in 3D). The rule lives in domain/intake.
    setMark(markOnArmPick);
    setRemarkConfirming(false);
    setRemarkArmed(false);
    setRemarkError(null);
    setDetectorConfirming(false);
    setDetectorError(null);
    // the rim-points door is a SEPARATE viewer mechanism (task #33) but the same
    // one-door discipline applies — arming the pick must not leave a rim-points
    // session armed underneath it
    setRimPointsArmedTooth(null);
    setRimPointsError(null);
  }, []);

  const handleCancelPick = useCallback(() => {
    setPickArmed(false);
    setPickMiss(null);
  }, []);

  /* ADOPTING THE DETECTOR'S CENTRE for an EXISTING site (the fleet table's first
     lever, 2026-08-04): the same re-mark PUT the hand flow lands, with the
     detector's own point — never a silent correction (cap7020's curated seed
     BEATS its detector proposal; the operator adjudicates), and the same
     retirement ceremony when a preview/review/run pointer would fall. */
  const [detectorConfirming, setDetectorConfirming] = useState(false);
  const [detectorSaving, setDetectorSaving] = useState(false);
  const [detectorError, setDetectorError] = useState<string | null>(null);
  const commitDetectorCentre = useCallback(
    (tooth: number, point: readonly number[]) => {
      setDetectorSaving(true);
      setDetectorError(null);
      void putRemarkedSite(caseId, tooth, point).then((result) => {
        setDetectorSaving(false);
        setDetectorConfirming(false);
        if (result.kind === "ok") onDetail(result.data);
        else setDetectorError(result.detail);
      });
    },
    [caseId, onDetail],
  );
  const handleUseDetectorCentre = useCallback(
    (tooth: number, point: readonly number[]) => {
      // one point pick, one owner (review 2026-08-04 #9): adopting must disarm
      // the scan-click doors, or a stray click re-marks over the adopted centre
      setPickArmed(false);
      setPickMiss(null);
      setRemarkConfirming(false);
      setRemarkArmed(false);
      setRimPointsArmedTooth(null);
      const site = detail.sites.find((s) => s.tooth === tooth);
      if (site !== undefined && remarkRetiresSomething(site, detail)) {
        setDetectorConfirming(true);
      } else {
        commitDetectorCentre(tooth, point);
      }
    },
    [detail, commitDetectorCentre],
  );
  const handleCancelDetectorCentre = useCallback(() => {
    setDetectorConfirming(false);
    setDetectorError(null);
  }, []);

  /* ADOPTING A DETECTED CAP (client 2026-08-04, the uploaded-arch deadlock): the
     missed-cap door's own POST with the detector's centre — the operator names
     only the tooth. On success the adopted site becomes the active one, so the
     framing and the re-mark door land exactly where the work continues. */
  const [adoptSaving, setAdoptSaving] = useState(false);
  const [adoptError, setAdoptError] = useState<string | null>(null);
  const handleAdopt = useCallback(
    (center: readonly number[], tooth: number) => {
      setAdoptSaving(true);
      setAdoptError(null);
      void postMarkedSite(caseId, tooth, center).then((result) => {
        setAdoptSaving(false);
        if (result.kind === "ok") {
          onDetail(result.data);
          setActiveTooth(tooth);
        } else {
          setAdoptError(result.detail);
        }
      });
    },
    [caseId, onDetail],
  );

  /* RE-MARKING THE ACTIVE SITE'S CENTRE (client 2026-08-01, the tooth-29 gap).
     THE BLAST RADIUS IN WORDS BEFORE THE ACT (the visible-reset doctrine —
     DeclareStage's SwitchConfirm, mirrored): asking either arms the pick straight
     away (nothing to retire — domain/intake.remarkRetiresSomething) or shows the
     words first and waits for an explicit confirm. Either way it shares the
     stage's ONE point pick with the missed-cap mark and the site picker, so
     arming it disarms them and vice versa — the same "one pick, one owner"
     doctrine, extended to a third door. */
  const [remarkConfirming, setRemarkConfirming] = useState(false);
  const [remarkArmed, setRemarkArmed] = useState(false);
  const [remarkSaving, setRemarkSaving] = useState(false);
  const [remarkError, setRemarkError] = useState<string | null>(null);

  const handleAskRemark = useCallback(() => {
    const active = detail.sites.find((s) => s.tooth === activeTooth) ?? null;
    if (active === null) return;
    setRemarkError(null);
    // the rim-points door is a separate viewer mechanism (task #33) but the same
    // one-door discipline applies, whichever branch below this takes
    setRimPointsArmedTooth(null);
    if (remarkRetiresSomething(active, detail)) {
      setRemarkConfirming(true);
      setRemarkArmed(false);
      return;
    }
    setRemarkConfirming(false);
    setRemarkArmed(true);
    setMark(markOnArmPick);
    setPickArmed(false);
    setPickMiss(null);
  }, [activeTooth, detail]);

  const handleConfirmRemark = useCallback(() => {
    setRemarkConfirming(false);
    setRemarkArmed(true);
    setMark(markOnArmPick);
    setPickArmed(false);
    setPickMiss(null);
  }, []);

  const handleCancelRemark = useCallback(() => {
    setRemarkConfirming(false);
    setRemarkArmed(false);
    setRemarkError(null);
  }, []);

  const handleRemarkResolved = useCallback(
    (point: readonly [number, number, number]) => {
      if (activeTooth === null) return;
      const tooth = activeTooth;
      setRemarkArmed(false);
      setRemarkSaving(true);
      setRemarkError(null);
      void putRemarkedSite(caseId, tooth, point).then((result) => {
        setRemarkSaving(false);
        // ApiResult is a {kind} union — result.kind === "ok" → result.data, the
        // detail replaces WHOLE (AM-4: what the BFF derived, never a local patch)
        if (result.kind === "ok") {
          onDetail(result.data);
          return;
        }
        setRemarkError(result.detail);
      });
    },
    [activeTooth, caseId, onDetail],
  );

  /* The stage resolved a surface point. Whoever armed the pick owns it — a
     confirmed re-mark first (it is the most recently armed of the three by
     construction: asking for it disarms the other two), then the site picker,
     then the missed-cap mark. A click that lands on no cap is SAID, not snapped
     to the least-far site: the operator would otherwise watch the stage fly to a
     tooth they did not click. */
  /* An armed click that hit only the sky. The viewer KEEPS the pick armed (the fix
     of 2026-08-01 — before that the click vanished with the controls still off), so
     this only says it out loud, in whichever panel armed the click. */
  const handleStageMiss = useCallback(() => {
    if (remarkArmed) {
      setRemarkError(OFF_SCAN_MISS_WORDS);
      return;
    }
    if (pickArmed) setPickMiss(OFF_SCAN_MISS_WORDS);
    else setMark((now) => ({ ...now, error: OFF_SCAN_MISS_WORDS }));
  }, [pickArmed, remarkArmed]);

  const handleStagePoint = useCallback(
    (point: readonly [number, number, number]) => {
      if (remarkArmed) {
        handleRemarkResolved(point);
        return;
      }
      if (!pickArmed) {
        handleMarkPlaced(point);
        return;
      }
      setPickArmed(false);  // the viewer's pick is one-shot; so is this arming
      const pick = pickSiteAt(detail.sites, point);
      if (pick.kind === "miss") {
        setPickMiss(
          `No site within ${SITE_PICK_RADIUS_MM.toFixed(1)}mm of that click — ` +
            "try the centre of a cap, or pick the row instead.",
        );
        return;
      }
      if (pick.kind === "ambiguous") {
        // Said, not guessed (audit 2026-07-31): two centres can sit inside one reach,
        // and resolving by nearest would frame a tooth the operator did not click.
        setPickMiss(
          `That click is within ${SITE_PICK_RADIUS_MM.toFixed(1)}mm of ` +
            `${pick.teeth.length} sites (${pick.teeth.map((t) => `tooth ${t}`).join(", ")}) — ` +
            "click nearer the cap you mean, or pick its row.",
        );
        return;
      }
      setPickMiss(null);
      setActiveTooth(pick.tooth);
    },
    [detail.sites, handleMarkPlaced, handleRemarkResolved, pickArmed, remarkArmed],
  );

  const handleSubmitMark = useCallback(() => {
    const tooth = Number(mark.tooth);
    const pending = mark.pending;
    if (pending === null || !Number.isInteger(tooth)) return;
    setMarkSaving(true);
    setMark((prev) => ({ ...prev, error: null }));
    void postMarkedSite(caseId, tooth, pending).then((result) => {
      setMarkSaving(false);
      // ApiResult is a {kind} union — same wrong-shape bug as the reconfirm handler
      // (result.ok/.value/.error exist on nothing), caught in the same sweep
      if (result.kind === "ok") {
        onDetail(result.data);
        resetMark();
        return;
      }
      // the BFF's own words — a 409 on an existing tooth explains itself better
      // than anything this layer could summarise
      setMark((prev) => ({ ...prev, error: result.detail }));
    });
  }, [caseId, mark.pending, mark.tooth, onDetail, resetMark]);

  /* RIM BORDER POINTS' OWN ACTS (§10-AL, task #33). Arming disarms every other door
     (the discipline extended a fourth time, see handleArmPick's own comment for the
     first three); Finish reads the DRAFT this render already holds (mirrored from the
     viewer's live callback via handleRimPointsChanged) rather than reaching into
     MainStage for it — nothing outside that component can reach the controller, and
     nothing needs to: the draft here is never stale, because onRimPointsChanged fires
     synchronously with every click. */
  const handleRimPointsChanged = useCallback(
    (points: readonly (readonly [number, number, number])[]) => {
      setRimPointsDraft(points);
    },
    [],
  );

  const handleArmRimPoints = useCallback((tooth: number) => {
    setPickArmed(false);
    setPickMiss(null);
    setMark(markOnArmPick);
    setRemarkConfirming(false);
    setRemarkArmed(false);
    setRemarkError(null);
    setDetectorConfirming(false);
    setDetectorError(null);
    setRimPointsDraft([]);
    setRimPointsError(null);
    setRimPointsArmedTooth(tooth);
  }, []);

  const handleFinishRimPoints = useCallback(() => {
    const tooth = rimPointsArmedTooth;
    if (tooth === null) return;
    const points = rimPointsDraft;
    // disarm FIRST (the viewer's own cleanup discards the on-screen dots either way —
    // see MainStage's rimPointsTooth doc) so a second Finish click mid-flight cannot
    // fire a second PUT for the same session
    setRimPointsArmedTooth(null);
    setRimPointsSaving(true);
    setRimPointsError(null);
    void putRimPoints(caseId, tooth, points).then((result) => {
      setRimPointsSaving(false);
      if (result.kind === "ok") {
        onDetail(result.data);
        return;
      }
      // the BFF's own words — the 3..12 refusal explains its own shape better than
      // anything this layer could summarise
      setRimPointsError(result.detail);
    });
  }, [caseId, onDetail, rimPointsArmedTooth, rimPointsDraft]);

  const handleCancelRimPoints = useCallback(() => {
    setRimPointsArmedTooth(null);
    setRimPointsError(null);
  }, []);

  const handleClearRimPoints = useCallback(
    (tooth: number) => {
      setRimPointsDeleting(true);
      setRimPointsError(null);
      void deleteRimPoints(caseId, tooth).then((result) => {
        setRimPointsDeleting(false);
        if (result.kind === "ok") {
          onDetail(result.data);
          return;
        }
        setRimPointsError(result.detail);
      });
    },
    [caseId, onDetail],
  );

  const mountedRef = useRef(true);
  const [detectPhase, setDetectPhase] = useState<DetectPhase>({ kind: "idle" });
  const [savingChoices, setSavingChoices] = useState(false);
  const [choicesError, setChoicesError] = useState<string | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const fireDetect = useCallback(() => {
    setDetectPhase({ kind: "detecting" });
    void postDetect(caseId).then((result) => {
      if (!mountedRef.current) return;
      if (result.kind === "ok") {
        setDetectPhase({ kind: "idle" });
        onDetail(result.data);
      } else {
        setDetectPhase({ kind: "failed", detail: result.detail });
      }
    });
  }, [caseId, onDetail]);

  const detectionDone = detail.detection !== null;
  useEffect(() => {
    if (
      !shouldAutoDetect({
        caseId,
        detectionDone,
        alreadyFiredFor: firedRef.current,
      })
    ) {
      return;
    }
    firedRef.current = caseId; // marked BEFORE the async settles — one fire per case
    fireDetect();
  }, [caseId, detectionDone, fireDetect]);

  const handleChoice = useCallback(
    (patch: Partial<ChoicesUpdate>) => {
      setSavingChoices(true);
      void putChoices(caseId, choicesUpdateFrom(detail, patch)).then((result) => {
        if (!mountedRef.current) return;
        setSavingChoices(false);
        if (result.kind === "ok") {
          setChoicesError(null);
          onDetail(result.data);
        } else {
          setChoicesError(result.detail);
        }
      });
    },
    [caseId, detail, onDetail],
  );

  return (
    <IntakeStageView
      detail={detail}
      detectPhase={detectPhase}
      savingChoices={savingChoices}
      choicesError={choicesError}
      onChoice={handleChoice}
      markArmed={mark.armed}
      markPending={mark.pending}
      markTooth={mark.tooth}
      markSource={mark.source}
      markSaving={markSaving}
      markError={mark.error}
      onArmMark={() => {
        setMark(markOnArmMark);
        setPickArmed(false); // one point pick, one owner
        setPickMiss(null);
        setRemarkConfirming(false);
        setRemarkArmed(false);
        setRemarkError(null);
        setRimPointsArmedTooth(null); // the fourth door, disarmed the same way
      }}
      onCancelMark={resetMark}
      onMarkTooth={(tooth) => setMark((prev) => ({ ...prev, tooth }))}
      onStagePoint={handleStagePoint}
      onStageMiss={handleStageMiss}
      onSubmitMark={handleSubmitMark}
      onRetryDetect={fireDetect}
      activeTooth={activeTooth}
      onSelectSite={handleSelectSite}
      pickArmed={pickArmed}
      pickMiss={pickMiss}
      onArmPick={handleArmPick}
      onCancelPick={handleCancelPick}
      remarkConfirming={remarkConfirming}
      remarkArmed={remarkArmed}
      remarkSaving={remarkSaving}
      remarkError={remarkError}
      onAskRemark={handleAskRemark}
      onConfirmRemark={handleConfirmRemark}
      onCancelRemark={handleCancelRemark}
      adoptSaving={adoptSaving}
      adoptError={adoptError}
      onAdopt={handleAdopt}
      detectorConfirming={detectorConfirming}
      detectorSaving={detectorSaving}
      detectorError={detectorError}
      onUseDetectorCentre={handleUseDetectorCentre}
      onConfirmDetectorCentre={commitDetectorCentre}
      onCancelDetectorCentre={handleCancelDetectorCentre}
      rimPointsArmedTooth={rimPointsArmedTooth}
      rimPointsLiveCount={rimPointsDraft.length}
      rimPointsSaving={rimPointsSaving}
      rimPointsDeleting={rimPointsDeleting}
      rimPointsError={rimPointsError}
      onArmRimPoints={handleArmRimPoints}
      onRimPointsChanged={handleRimPointsChanged}
      onFinishRimPoints={handleFinishRimPoints}
      onCancelRimPoints={handleCancelRimPoints}
      onClearRimPoints={handleClearRimPoints}
      jawAdvisoryOpen={jawAdvisoryOpen}
      onOpenJawAdvisory={() => setJawAdvisoryOpen(true)}
      onCloseJawAdvisory={() => setJawAdvisoryOpen(false)}
    />
  );
}
