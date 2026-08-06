/**
 * ADJUST (plan §4 Adjust, §5; slice 6) — the flagged-site rework surface.
 *
 * The client, 2026-07-28: "The adjust functionality is not build at all." It was a
 * placeholder, and Declare's fork offered a button that led to it. A promised
 * destination that does not exist is worse than no promise, so this is that
 * destination:
 *
 *   LEFT   — the flagged-first site queue: flagged sites at the top carrying the
 *            GATE'S OWN reason words, clean sites below and visibly optional.
 *            Selecting a site drives the panes and the tools.
 *   CENTRE — the SAME three panes as Declare (components/SitePanes), reading the
 *            SHIPPED pose rather than a pre-run preview. After any applied tool they
 *            re-render the NEW pose: the payload comes back with the tool's response.
 *   UNDER  — the toolbox: one tool visible, the other three one click away, and the
 *            one act that is not a correction — DROPPING the cap (2026-07-31). A
 *            rework that is not going to converge has an honest end, and until now
 *            it could only be said at Deliver, hours later, on the signing screen.
 *            The drop is a DRAFT of the confirmation's own disposition, reversible
 *            in the same place; nothing on this stage signs it.
 *
 * EVERY TOOL IS A GATED PROPOSAL and this surface never pretends otherwise. Optimism
 * is OFF: nothing moves on screen until the server says it moved. A refusal renders
 * VERBATIM — the gate's own sentence — and the pose on screen is always one that
 * passed the gates. The best-fit's already-optimal outcome is the one refusal that is
 * really a PASS: it renders GREEN with a one-click widen, because the demo shipped it
 * in the refusal's tone once and had to take that back.
 *
 * THE STAGE STAYS SKIPPABLE: it adds no rule to domain/flow.ts, and a case may reach
 * Deliver having never opened it.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useDialogEscape } from "./useDialogEscape";
import { useDialogFocus } from "./useDialogFocus";
import { useNavigate } from "react-router-dom";
import { FREE_POINT_COLOR, GHOST_POINT_COLOR, type VerifyMarker } from "viewer";
import {
  fetchLandmarks,
  fetchRun,
  fetchSeated,
  postBestFit,
  putSiteRelief,
  postFitByPoints,
  postMarkTrench,
  postRePreview,
  postReview,
  postRotation,
  putWithholdIntent,
  postAcknowledgeException,
  deleteAcknowledgeException,
  type AdjustOutcomeView,
  type AdjustResultView,
  type ApiResult,
  type CaseSessionDetail,
  type LandmarkView,
  type RePreviewView,
  type SitePreviewPayload,
  type SiteView,
} from "../api/client";
import {
  evidenceReceiptLine,
  evidenceReceipts,
  evidenceRideWords,
  ghostScanMarkers,
  receiptsCarriedByReemit,
  exceptionDraftWords,
  DEFAULT_DIAMETER_MM,
  adjustPaneNotices,
  adjustQueue,
  adjustUnionCaption,
  alreadyOptimalFrom,
  autoMarkDrafts,
  siteReliefCeilingLine,
  droppedRowWords,
  isComplete,
  newPairDraft,
  outcomeMovedTheRow,
  paneArming,
  pairBody,
  queueSummary,
  reasonCountWords,
  unverifiedClockNotice,
  type ClockReferenceLike,
  withPick,
  type AdjustQueueEntry,
  type AdjustToolId,
  type AlreadyOptimal,
  type UnverifiedClockNotice,
  withoutPick,
  type PairDraft,
  type PairSlot,
  type SeatedPhase,
} from "../domain/adjust";
import {
  alignmentStats,
  skipConsequenceWords,
  type ViewPresetId,
  type WorkspaceStat,
} from "../domain/declare";
import { PANES_OPEN_LINKED } from "../domain/workspace";
import { blockedReason, factsFromCaseSession } from "../domain/flow";
import { SitePanesView, useSitePaneScene, type PaneId } from "./SitePanes";
import { AdjustDock } from "./AdjustDock";
/* ONE toolbar for both stages, not two that drift — see WorkspaceToolbar's own note
   on why it is exported from Declare rather than sitting in its own module. */
import { clampZoomLevel } from "viewer";
import { WorkspaceToolbar } from "./DeclareStage";
import { WorkspaceInsight } from "./WorkspaceInsight";

/** What the surface is waiting on — named, so it never freezes silently. */
export type ToolPhase = "idle" | "working";

/**
 * THE NUMBERED MARKS, drawn where they were placed — one entry per PLACED point,
 * on the pane that took the click. Exported pure so the test can pin the one
 * invariant that broke (client 2026-08-04, twice): a SPAN BOTH draft's second
 * library click was recorded in the draft and NEVER DRAWN — this list carried
 * partPoint, scanPoint and scanPointEnd, and not partPointEnd, so the operator
 * watched their click "not take effect" while the checklist quietly ticked.
 * Labels mirror the scan span's own convention: a spanned half reads "2a"/"2b",
 * a single point reads "2".
 */
export function pairMarkers(
  drafts: readonly PairDraft[],
): Partial<Record<PaneId, readonly VerifyMarker[]>> {
  const part: VerifyMarker[] = [];
  const scan: VerifyMarker[] = [];
  drafts.forEach((draft, index) => {
    const label = `${index + 1}`;
    if (draft.partPoint !== null) {
      part.push({
        key: `${draft.id}-part`,
        position: draft.partPoint as [number, number, number],
        color: FREE_POINT_COLOR,
        label: draft.partSpan ? `${label}a` : label,
      });
    }
    if (draft.partPointEnd !== null) {
      part.push({
        key: `${draft.id}-part-end`,
        position: draft.partPointEnd as [number, number, number],
        color: FREE_POINT_COLOR,
        label: `${label}b`,
      });
    }
    if (draft.scanPoint !== null) {
      scan.push({
        key: `${draft.id}-scan`,
        position: draft.scanPoint as [number, number, number],
        color: FREE_POINT_COLOR,
        label: draft.span ? `${label}a` : label,
      });
    }
    if (draft.scanPointEnd !== null) {
      scan.push({
        key: `${draft.id}-scan-end`,
        position: draft.scanPointEnd as [number, number, number],
        color: FREE_POINT_COLOR,
        label: `${label}b`,
      });
    }
  });
  return { library: part, scan, union: scan };
}

export interface AdjustStageViewProps {
  readonly entries: readonly AdjustQueueEntry[];
  readonly activeTooth: number | null;
  /** §10-AD's answer half: true when the standing run is a §10-AC re-emit whose
   * receipts were CARRIED with the copied poses — the block's title says so. */
  readonly receiptsCarried?: boolean;
  /** §10-AI: ghost markers are on the scan panes — the note says what they claim. */
  readonly ghostsActive?: boolean;
  /** §10-B/C: the active site's relief facts + the apply act. */
  readonly relief?: {
    readonly siteValue: number | null;
    readonly caseValue: number | null;
    readonly ceilingLine: string | null;
    readonly runDone: boolean;
    readonly saving: boolean;
    readonly error: string | null;
    readonly onApply: (value: number | null) => void;
  } | null;
  readonly onSelectSite: (tooth: number) => void;
  readonly tool: AdjustToolId;
  readonly onSelectTool: (tool: AdjustToolId) => void;
  readonly phase: ToolPhase;
  /** A refusal, VERBATIM — the gate's own sentence, never our summary of it. */
  readonly refusal: string | null;
  /** The one refusal that is really a pass; renders green, never in the refusal tone. */
  readonly pass: AlreadyOptimal | null;
  readonly lastOutcome: AdjustOutcomeView | null;
  /** The rotation dial. */
  readonly cumulativeDeg: number | null;
  readonly onRotate: (stepDeg: number) => void;
  readonly onResetRotation: () => void;
  /** Best fit. */
  readonly diameterMm: number;
  readonly onChangeDiameter: (mm: number) => void;
  readonly onBestFit: (apply: boolean) => void;
  /** Mark trench: armed = the next scan click is the mark. */
  readonly trenchArmed: boolean;
  readonly onArmTrench: () => void;
  /** Fit by points. */
  readonly drafts: readonly PairDraft[];
  readonly onStartPair: (span: boolean, partSpan?: boolean) => void;
  readonly onRemovePair: (id: string) => void;
  /** Clear ONE mark, leaving the rest of the pair (client 2026-07-29). */
  readonly onRemovePoint: (id: string, slot: PairSlot) => void;
  readonly onApplyPairs: () => void;
  /** START OVER, on the ACTIVE tool's set only (design review 2026-07-31). Optional
   *  with an inert default: static callers predate it. */
  readonly onClearPairs?: () => void;
  /** The panes, already assembled by the container (tests pass a stub). */
  readonly panes: React.ReactNode;
  /** The site's rung, for the re-confirm nudge after an applied tool. */
  readonly activeStatus: string | null;
  /** The re-confirmation act, offered where the fit was changed (client 2026-07-29).
   *  Optional with inert defaults: static tests predate the trio. */
  readonly onReconfirm?: () => void;
  readonly reconfirmSaving?: boolean;
  readonly reconfirmError?: string | null;
  /**
   * WHETHER THE EVIDENCE IS ON SCREEN — the re-confirmation's other precondition
   * (design review 2026-07-31; see domain/adjust.reconfirmControl).
   *
   * Both default to the UNDER-claim: a caller that has said nothing about the panes
   * gets an inert control with its reason, never an enabled attestation over a pane
   * that may be showing "The shipped fit could not be read."
   */
  readonly seatedPhase?: SeatedPhase;
  readonly seatedPayloadPresent?: boolean;
  /** The seated pose, for the pre-flight span caution (client 2026-07-29). Null until
   *  a payload has landed; the caution simply stays quiet then. */
  readonly pose?: { readonly origin: readonly number[]; readonly axis: readonly number[] } | null;
  /** The server's MEASURED rim centre and its own bound (plan §10-F). With it the
   *  lever guard becomes a local pre-refusal; without it, the old caution. */
  readonly clock?: ClockReferenceLike | null;
  /** Which tooth's gate reasons the dialog is showing, if any (client 2026-07-29).
   *  OPTIONAL with a null default: static callers predate the dialog, and a bare
   *  `!== null` check let an omitted prop (undefined) open an empty dialog — caught by
   *  the suite the moment the reasons moved off the row. */
  readonly reasonsFor?: number | null;
  readonly onOpenReasons?: (tooth: number) => void;
  readonly onCloseReasons?: () => void;
  /** AUTO-MARK (client 2026-07-29, item 3): the site's proposed landmarks, best lever
   *  arm first, and the read's own lifecycle. `drafts` above already carries the pairs
   *  they seeded — this is only the landmarks' own identity, for the summary line and
   *  each row's source label. OPTIONAL with an idle/empty default: static callers
   *  predate this tool. */
  readonly autoMarkLandmarks?: readonly LandmarkView[];
  readonly autoMarkPhase?: SeatedPhase;
  /** A refusal from the landmarks read, VERBATIM — same posture as every other
   *  refusal on this surface. */
  readonly autoMarkError?: string | null;
  /** THE STAGE'S OWN FOOTER (design review 2026-07-31): the queue rail had no
   *  forward or back, so an operator who had just reworked the last flagged site
   *  had to go hunting the top rail. NAVIGATION ONLY — these assert no status and
   *  record nothing; the words are Declare's fork's own, so the two doors describe
   *  the same consequence. Optional with inert defaults: static callers predate it. */
  readonly flaggedCount?: number;
  /** flow.ts's `blockedReason("deliver", facts)`, verbatim — null when Deliver is
   *  reachable. Never re-derived here: reachability is one rule, in one module. */
  readonly deliverBlockedReason?: string | null;
  readonly onBack?: () => void;
  readonly onForward?: () => void;
  /** THE WORKSPACE TOOLBAR (gaps `workspace-toolbar-site-chip`,
   *  `alignment-metrics-strip`). Adjust had no stage toolbar at all, so the site's
   *  identity and every alignment figure lived inside the scrolling work column —
   *  and each figure inside ONE tool's tab. `stats` arrives already formatted from
   *  domain/declare.alignmentStats over the run's own rows: this component holds no
   *  number it did not receive. Optional with empty defaults: static callers predate
   *  the strip. */
  /** DROPPING A CAP (design flow.dc.html dropSite 1345-1354; gap
   *  `drop-a-cap-from-adjust`). The act is the BFF's per-site withhold INTENT, which
   *  PRE-FILLS the confirmation's disposition — this surface signs nothing and
   *  computes nothing: it sends the operator's word and renders what came back.
   *  Both directions go through the one handler, because the reversal must be
   *  exactly as reachable as the act. Optional with inert defaults: static callers
   *  predate it. */
  readonly onDrop?: (tooth: number, withhold: boolean) => void;
  readonly dropSaving?: boolean;
  /** The comp's amber middle act (client 2026-08-02): give/withdraw the DRAFT
   * acknowledgment of a flagged site as a shipping exception. Deliver still signs. */
  readonly onAcknowledgeException?: (tooth: number, give: boolean) => void;
  readonly acknowledgeSaving?: boolean;
  readonly acknowledgeError?: string | null;
  /** A refusal, VERBATIM — same posture as every other refusal on this surface. */
  readonly dropError?: string | null;
  readonly systemModel?: string | null;
  readonly stats?: readonly WorkspaceStat[];
  readonly viewPreset?: ViewPresetId;
  readonly onSelectView?: (preset: ViewPresetId) => void;
  readonly viewPresetsAvailable?: boolean;
  /** The shared zoom counter and its step — see WorkspaceToolbarProps. One number for
   *  the whole workspace, held by the container. */
  readonly zoomLevel?: number;
  readonly onZoom?: (direction: 1 | -1) => void;
  /** The stage-owned link state for the toolbar's toggle — see WorkspaceToolbarProps. */
  readonly linked?: boolean;
  readonly onToggleLinked?: () => void;
  /** THE PROVENANCE POPOVER (gap `deviation-budget-in-workspace`), already assembled
   *  by the container — same pattern as `panes` above, and for the same reason: the
   *  real control needs this stage's caseId, which the View was never given. Optional
   *  with a null default: static callers predate it, exactly like every other
   *  toolbar addition on this surface. */
  readonly insightSlot?: React.ReactNode;
  /**
   * RE-PREVIEW (gap `re-preview-a-site-without-applying-a-tool`, 2026-07-31): a
   * re-READ of the site's numbers off the pose already on disk, with NO tool applied.
   * An applied tool already refreshes the panes; this is the read without one — after
   * a rework elsewhere, or a row the operator suspects is stale. `onRePreview` fires
   * the body-less POST; `rePreviewResult` is what came back, rendered verbatim, never
   * a verdict this app derived. Optional with inert defaults: static callers predate
   * the trio.
   */
  readonly rePreviewResult?: RePreviewView | null;
  readonly onRePreview?: () => void;
  /** The re-read's OWN in-flight state — independent of `phase`, the same way
   *  reconfirm and drop each carry their own rather than sharing the tools' shared
   *  busy flag (they are not tools; see the file-level comment beside the render). */
  readonly rePreviewPhase?: ToolPhase;
  /** A refusal or transport error, VERBATIM — no auto-retry; the control itself is
   *  the retry, exactly like every other act on this surface. */
  readonly rePreviewError?: string | null;
  /**
   * THE UNVERIFIED CLOCK'S ACTIONABLE SURFACE (§10-H's "STILL OPEN" line, closed
   * 2026-08-02): null unless the active site's run row carries
   * `clocking.rotation_unverified === true`. The container computes this from the
   * SAME rows the ALIGNMENT strip and the queue's flag reasons already read
   * (`domain/adjust.unverifiedClockNotice`) — the View renders it, and decides
   * nothing about when it applies. Optional with a null default: static callers
   * predate it.
   */
  readonly clockNotice?: UnverifiedClockNotice | null;
}


/** The stage's whole surface, pure props → markup — statically testable. */
export function AdjustStageView({
  entries,
  activeTooth,
  receiptsCarried = false,
  ghostsActive = false,
  relief = null,
  onSelectSite,
  tool,
  onSelectTool,
  phase,
  refusal,
  pass,
  lastOutcome,
  cumulativeDeg,
  onRotate,
  onResetRotation,
  diameterMm,
  onChangeDiameter,
  onBestFit,
  trenchArmed,
  onArmTrench,
  drafts,
  onStartPair,
  onRemovePair,
  onRemovePoint,
  onApplyPairs,
  onClearPairs = () => undefined,
  panes,
  activeStatus,
  onReconfirm = () => undefined,
  reconfirmSaving = false,
  reconfirmError = null,
  seatedPhase = "idle",
  seatedPayloadPresent = false,
  pose = null,
  clock = null,
  reasonsFor = null,
  onOpenReasons = () => undefined,
  onCloseReasons = () => undefined,
  autoMarkLandmarks = [],
  autoMarkPhase = "idle",
  autoMarkError = null,
  onDrop = () => undefined,
  dropSaving = false,
  onAcknowledgeException = () => undefined,
  acknowledgeSaving = false,
  acknowledgeError = null,
  dropError = null,
  flaggedCount = 0,
  deliverBlockedReason = null,
  onBack = () => undefined,
  onForward = () => undefined,
  systemModel = null,
  stats = [],
  viewPreset,
  onSelectView,
  viewPresetsAvailable,
  zoomLevel,
  onZoom,
  linked,
  onToggleLinked,
  insightSlot = null,
  rePreviewResult = null,
  onRePreview = () => undefined,
  rePreviewPhase = "idle",
  rePreviewError = null,
  clockNotice = null,
}: AdjustStageViewProps) {
  const active = entries.find((e) => e.tooth === activeTooth) ?? null;
  const busy = phase === "working";
  // Escape closes the gate-reasons dialog.
  useDialogEscape(reasonsFor !== null, onCloseReasons);
  // Focus moves in, is trapped, and comes back on close (§10-O.8) — see useDialogFocus.
  const reasonsDialogRef = useRef<HTMLElement | null>(null);
  useDialogFocus(reasonsFor !== null, reasonsDialogRef);

  const reasonsShown =
    reasonsFor === null
      ? []
      : (entries.find((e) => e.tooth === reasonsFor)?.reasons ?? []);
  return (
    <div data-role="adjust-stage" className="stage-contents">
      {/* The work column scrolls ABOVE a footer that never does — the same opt-in
          Declare uses, so the way onward stays on screen at every scroll position. */}
      <div className="workbench__work workbench__work--footered">
        <div className="workbench__work-scroll">
        <aside data-role="adjust-queue" aria-label="Site queue" className="panel">
          <h3 className="panel__title">Adjustment queue — flagged first</h3>
          <p data-role="queue-summary" className="panel__hint">
            {queueSummary(entries)}
          </p>
          <ul className="decode-stepper__overview">
            {entries.map((entry) => (
              <li key={entry.tooth}>
                <button
                  type="button"
                  data-role="queue-site"
                  data-tooth={entry.tooth}
                  data-flagged={entry.flagged}
                  aria-pressed={entry.tooth === activeTooth}
                  className={`decode-stepper__item${
                    entry.tooth === activeTooth ? " decode-stepper__item--active" : ""
                  }${entry.optional ? " decode-stepper__item--optional" : ""}${
                    entry.dropped ? " decode-stepper__item--dropped" : ""
                  }`}
                  onClick={() => onSelectSite(entry.tooth)}
                >
                  <span className="decode-stepper__position">Tooth {entry.tooth}</span>
                  <span className="decode-stepper__chips">
                    <span
                      data-role="status-chip"
                      data-status={entry.status}
                      className="chip chip--status"
                    >
                      {entry.status}
                    </span>{" "}
                    <span className="decode-stepper__declared">
                      {entry.declaredVariant ?? "no variant declared"}
                    </span>
                  </span>
                  {entry.exceptionAcknowledged && !entry.dropped && (
                    <span data-role="queue-exception" className="adjust-queue__exception">
                      {exceptionDraftWords()}
                    </span>
                  )}
                  {entry.receipts.length > 0 && !entry.dropped ? (
                    /* §10-AD's ANSWER: the standing run's own receipts, counted.
                       The promise line stands down here — both at once would read
                       as a promise about a run that already answered. */
                    <span data-role="queue-receipts" className="adjust-queue__evidence">
                      {evidenceReceiptLine(entry.receipts, receiptsCarried)}
                    </span>
                  ) : entry.evidenceCount > 0 && !entry.dropped ? (
                    /* §10-AD: the operator's marks survive — said where the rework
                       lives, so re-running never reads as losing the work again */
                    <span data-role="queue-evidence" className="adjust-queue__evidence">
                      {evidenceRideWords(entry.evidenceCount)}
                    </span>
                  ) : null}
                  {entry.dropped ? (
                    /* A DROPPED CAP STOPS ASKING (design queue row 1183-1191). The
                       flag line is the queue's ASK — "rework me" — and a cap the
                       operator has taken out of the case must not keep asking. The
                       WHY control stays a sibling below, because the verdict is
                       still true and bringing the cap back must cost no re-read. */
                    <span data-role="queue-dropped" className="adjust-queue__dropped">
                      {droppedRowWords()}
                    </span>
                  ) : entry.flagged ? (
                    /* The gate's words used to sit here in full — five lines of amber per
                       flagged site, which pushed the queue past its card and left the
                       operator scrolling a list whose whole job is to be scannable
                       (client 2026-07-29: "the Sites it cut ... should be clickable and
                       in a modal to save real estate"). The ROW keeps the fact; the
                       WORDS move to the dialog below. */
                    <span data-role="queue-flag" className="adjust-queue__flag">
                      flagged — {reasonCountWords(entry.reasons.length)}
                    </span>
                  ) : (
                    <span data-role="queue-optional" className="adjust-queue__optional">
                      passed its gates — reworking is optional
                    </span>
                  )}
                </button>
                {entry.flagged && (
                  /* A SIBLING of the row, not a child: the row is itself a button, and a
                     button inside a button is invalid markup that browsers resolve by
                     dropping one of them. Selecting the site stays the row's job. */
                  <button
                    type="button"
                    data-role="queue-why"
                    data-tooth={entry.tooth}
                    className="adjust-queue__why"
                    onClick={() => onOpenReasons(entry.tooth)}
                  >
                    Why it was flagged
                  </button>
                )}
              </li>
            ))}
          </ul>
          {entries.length === 0 && (
            <p data-role="adjust-empty" className="panel__hint">
              No aligned sites on this run — there is nothing to rework here.
            </p>
          )}
        </aside>

        </div>

        {/* THE WAY ONWARD, IN THE COLUMN'S OWN FOOT (comp, read directly 2026-08-02:
            its sticky footer — template 465-469 — pins the stage nav at the bottom of
            the QUEUE column, forward above back, and leaves the full width under the
            panes to the tools; slice B had moved this across to a stage-wide bar).
            NAVIGATION ONLY: neither control records anything and neither asserts a
            status — the consequence sentence and the blocked reason are Declare's
            fork's own words, so the two doors out of the rework loop cannot describe
            the same case differently. */}
          <div
            data-role="adjust-advance"
            className="workbench__work-footer panel__actions panel__actions--advance"
          >
            <p data-role="adjust-skip-consequence" className="panel__hint">
              {skipConsequenceWords(flaggedCount)}
            </p>
            {/* THE REASON IS PROSE, NOT A LABEL (client 2026-08-02: "Smaller buttons
                here to give more space to the tools panel"). The bar's height was
                mostly this one control: the whole blockedReason sentence lived INSIDE
                the span, so a two-line sentence made a two-line button. The reason is
                still NAMED and still visible — the doctrine is that a shut door says
                why, not that the door must be the sentence — and the inert control
                also carries it in `title`, so it explains itself to a pointer or a
                screen reader without depending on the line beside it. */}
            {deliverBlockedReason !== null && (
              <p data-role="adjust-forward-reason" className="panel__hint">
                {deliverBlockedReason}
              </p>
            )}
            <div className="adjust-fork">
              {deliverBlockedReason === null ? (
                <button
                  type="button"
                  data-role="adjust-forward"
                  className="button button--primary button--small"
                  onClick={onForward}
                >
                  Done adjusting — go to Deliver
                </button>
              ) : (
                <span
                  data-role="adjust-forward"
                  aria-disabled="true"
                  title={deliverBlockedReason}
                  className="button button--secondary button--small button--blocked"
                >
                  Go to Deliver
                </span>
              )}
              <button
                type="button"
                data-role="adjust-back"
                className="button button--secondary button--small"
                onClick={onBack}
              >
                Back to Alignment
              </button>
            </div>
          </div>
      </div>
      {/* THE STAGE GETS DECLARE'S TOOLBAR (design template 206-266). Adjust's own
          identity problem was worse than Declare's: the tooth appeared only in the
          toolbox heading ("Tools — tooth N") and the queue rows, both inside the
          scroll box, and the alignment facts were each locked in one tool's TAB.
          Same strip, same rules, same server facts. */}
      <div className="workbench__stage workbench__stage--split">
        <WorkspaceToolbar
          tooth={activeTooth}
          systemModel={systemModel}
          status={activeStatus}
          stats={stats}
          viewPreset={viewPreset}
          onSelectView={onSelectView}
          viewPresetsAvailable={viewPresetsAvailable}
          zoomLevel={zoomLevel}
          onZoom={onZoom}
          linked={linked}
          onToggleLinked={onToggleLinked}
          endSlot={insightSlot}
        />
        {panes}
        <div className="workspace-drawer workspace-drawer--dock">
          <section data-role="adjust-toolbox" aria-label="Correction tools"
                   className="panel">
            {/* THE PANEL OPENS ON ITS TABS (comp, read directly 2026-08-02): no
                heading — the tabs name the tool, the toolbar's chip names the tooth.
                The SITE-level acts (re-read, drop) sit in ONE row at the panel's
                FOOT, which is the comp's own arrangement; with the drawer no longer
                scrolling (§10-V.3 fixed the flex order) the foot is as reachable as
                the head was. The clock notice stays above the tabs — a standing
                fact about the site, not an act on it. */}

            {clockNotice !== null && (
              /* THE UNVERIFIED CLOCK'S ACTIONABLE SURFACE (§10-H's "STILL OPEN" line,
                 closed 2026-08-02). Amber, the tone this product already uses for "a
                 consequence to weigh" — nothing here failed a gate the operator can
                 fix by clicking, and nothing here is accepted. The button ROUTES to
                 auto-mark; it never claims completing that tool will mark this flag
                 verified (see `unverifiedClockNotice`'s own doctrine). */
              /* ONE LINE + the act; the full reading behind a fold (client
                 2026-08-04: "This takes a lot of real estate"). The queue set the
                 precedent — the row keeps the fact, the words move behind a door —
                 and the sentences inside the fold are UNCHANGED, verbatim. */
              <div data-role="clock-unverified" role="status" className="adjust-clock-notice">
                <div className="adjust-clock-notice__row">
                  <span data-role="clock-unverified-lead" className="adjust-clock-notice__lead">
                    The rotation could not be verified automatically — auto-mark
                    is the documented answer.
                  </span>
                  <button
                    type="button"
                    data-role="verify-rotation"
                    className="button button--secondary button--small"
                    onClick={() => onSelectTool(clockNotice.armTool)}
                  >
                    Switch to auto-mark
                  </button>
                </div>
                <details data-role="clock-unverified-words" className="adjust-clock-notice__fold">
                  <summary className="adjust-clock-notice__summary">
                    why, and what auto-mark records
                  </summary>
                  <p data-role="clock-unverified-facts" className="adjust-clock-notice__line">
                    {clockNotice.facts}
                  </p>
                  <p data-role="clock-unverified-act" className="adjust-clock-notice__line">
                    {clockNotice.act}
                  </p>
                </details>
              </div>
            )}

            <AdjustDock
              tool={tool}
              onSelectTool={onSelectTool}
              active={active}
              busy={busy}
              cumulativeDeg={cumulativeDeg}
              onRotate={onRotate}
              onResetRotation={onResetRotation}
              trenchArmed={trenchArmed}
              onArmTrench={onArmTrench}
              diameterMm={diameterMm}
              onChangeDiameter={onChangeDiameter}
              onBestFit={onBestFit}
              pass={pass}
              drafts={drafts}
              pose={pose}
              clock={clock}
              onStartPair={onStartPair}
              onRemovePair={onRemovePair}
              onRemovePoint={onRemovePoint}
              onApplyPairs={onApplyPairs}
              onClearPairs={onClearPairs}
              ghostsActive={ghostsActive}
              autoMarkLandmarks={autoMarkLandmarks}
              autoMarkPhase={autoMarkPhase}
              autoMarkError={autoMarkError}
              refusal={refusal}
              lastOutcome={lastOutcome}
              activeStatus={activeStatus}
              onReconfirm={onReconfirm}
              reconfirmSaving={reconfirmSaving}
              reconfirmError={reconfirmError}
              seatedPhase={seatedPhase}
              seatedPayloadPresent={seatedPayloadPresent}
              receiptsCarried={receiptsCarried}
              onRePreview={onRePreview}
              rePreviewResult={rePreviewResult}
              rePreviewWorking={rePreviewPhase === "working"}
              rePreviewError={rePreviewError}
              onAcknowledgeException={onAcknowledgeException}
              acknowledgeSaving={acknowledgeSaving}
              acknowledgeError={acknowledgeError}
              onDrop={onDrop}
              dropSaving={dropSaving}
              dropError={dropError}
              relief={relief}
            />
          </section>
        </div>
      </div>

      {/* THE GATE'S WORDS, ON DEMAND (client 2026-07-29). Same dialog chrome as
          Deliver's report — backdrop, card, scrolling body — so the product has one
          modal idiom rather than two. Closes on the backdrop and on its own control. */}
      {reasonsFor !== null && (
        <div
          data-role="reasons-backdrop"
          className="decode-dialog-backdrop"
          onClick={onCloseReasons}
        >
          <section
            ref={reasonsDialogRef}
            data-role="reasons-dialog"
            className="decode-dialog decode-dialog--narrow"
            role="dialog"
            aria-modal="true"
            aria-labelledby="reasons-dialog-heading"
            tabIndex={-1}
            onClick={(event) => event.stopPropagation()}
          >
            <header className="decode-dialog__header">
              <div>
                <h2 id="reasons-dialog-heading" className="decode-dialog__title">
                  Tooth {reasonsFor} — why the run flagged it
                </h2>
                <p className="decode-dialog__subject">
                  The gate's own words. Nothing here is a summary of them.
                </p>
              </div>
              {/* THE ONLY CONTROL THIS DIALOG HAS (the reasons list below is plain text,
                  not interactive) — data-autofocus is explicit rather than left to the
                  first-focusable fallback, so a body that later grows a link or button
                  cannot silently steal the landing spot from the safe one. */}
              <button
                type="button"
                data-role="reasons-close"
                data-autofocus=""
                className="button button--ghost button--small"
                onClick={onCloseReasons}
              >
                Close
              </button>
            </header>
            <div className="decode-dialog__body">
              <ul data-role="queue-reasons" className="adjust-queue__reasons">
                {reasonsShown.length > 0 ? (
                  reasonsShown.map((reason) => (
                    <li key={reason} className="adjust-queue__reason">
                      {reason}
                    </li>
                  ))
                ) : (
                  <li className="adjust-queue__reason">
                    Flagged by the run — the gate recorded no action words.
                  </li>
                )}
              </ul>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

export interface AdjustStageProps {
  readonly detail: CaseSessionDetail;
  readonly onDetail: (next: CaseSessionDetail) => void;
}

/** The container: the run's rows, the seated read per site, the four tools' requests,
 * and the picking that feeds fit-by-points and mark-trench. */
export function AdjustStage({ detail, onDetail }: AdjustStageProps) {
  const caseId = detail.case.id;
  const navigate = useNavigate();
  const mountedRef = useRef(true);
  const [rows, setRows] = useState<ReadonlyArray<Record<string, unknown>>>([]);
  const [activeTooth, setActiveTooth] = useState<number | null>(null);
  const [tool, setTool] = useState<AdjustToolId>("fit-by-points");
  const [phase, setPhase] = useState<ToolPhase>("idle");
  const [refusal, setRefusal] = useState<string | null>(null);
  const [pass, setPass] = useState<AlreadyOptimal | null>(null);
  const [lastOutcome, setLastOutcome] = useState<AdjustOutcomeView | null>(null);
  const [payload, setPayload] = useState<SitePreviewPayload | null>(null);
  // §10-B/C: the per-site relief act — the landed detail (a re-emit over a done
  // run) replaces everything, optimism OFF as always
  const [reliefSaving, setReliefSaving] = useState(false);
  const [reliefError, setReliefError] = useState<string | null>(null);
  const [seatedPhase, setSeatedPhase] = useState<SeatedPhase>("idle");
  const [seatedError, setSeatedError] = useState<string | null>(null);
  const [diameterMm, setDiameterMm] = useState(DEFAULT_DIAMETER_MM);
  const [trenchArmed, setTrenchArmed] = useState(false);
  // AUTO-MARK (client 2026-07-29, item 3) keeps its OWN draft set, separate from
  // fit-by-points' hand-built one: switching tabs must never silently discard a pair
  // the operator is mid-way through building by hand, and the two mean different
  // things — one the operator found, one the worker proposed. `drafts` below is the
  // ACTIVE set for whichever tool is selected; every existing consumer (openDraft,
  // markers, handlePick, apply) keeps reading through that one name unchanged.
  const [fitDrafts, setFitDrafts] = useState<readonly PairDraft[]>([]);
  const [autoDrafts, setAutoDrafts] = useState<readonly PairDraft[]>([]);
  const [autoMarkLandmarks, setAutoMarkLandmarks] =
    useState<readonly LandmarkView[]>([]);
  const [autoMarkPhase, setAutoMarkPhase] = useState<SeatedPhase>("idle");
  /** Monotone id for the landmarks read — a result is stale only when a NEWER request
   *  exists, never merely because the phase moved (see the fetch effect's note). */
  const autoMarkRequestRef = useRef(0);
  const [autoMarkError, setAutoMarkError] = useState<string | null>(null);
  const drafts = tool === "auto-mark" ? autoDrafts : fitDrafts;
  const setDrafts = tool === "auto-mark" ? setAutoDrafts : setFitDrafts;

  /* RE-PREVIEW (gap `re-preview-a-site-without-applying-a-tool`, 2026-07-31): its OWN
   * in-flight/result/error state, independent of `phase` — the same reason reconfirm
   * and drop each carry their own rather than sharing the tools' shared busy flag. It
   * is not a tool: it applies nothing, so it does not belong in `settle`'s path. */
  const [rePreviewPhase, setRePreviewPhase] = useState<ToolPhase>("idle");
  const [rePreviewResult, setRePreviewResult] = useState<RePreviewView | null>(null);
  const [rePreviewError, setRePreviewError] = useState<string | null>(null);
  /** Monotone id, exactly like `autoMarkRequestRef` — a response is stale only when a
   *  NEWER request exists (a site switch), never merely because the phase moved. */
  const rePreviewRequestRef = useRef(0);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  /* THE RUN'S VERDICT ROWS — the queue's reasons come from them, verbatim, and so do
     the ALIGNMENT strip's five figures.

     `rowsNonce` is why this effect can fire without the run state moving. An applied
     tool rewrites this site's summary row SERVER-side (adjust._fold_outcome) and moves
     no run state, so keying only on `run_state` froze `rows` for the rest of the
     session: the toolbar kept printing the pre-rework clocking and pair count beside an
     outcome panel describing the new pose, and `adjustQueue`'s gate reasons read the
     same stale rows (design review 2026-07-31). */
  const [rowsNonce, setRowsNonce] = useState(0);
  /* §10-AD's answer half rides the SAME response the rows already come from:
     summary.evidence_reapplied is the run's own receipts — the audit (2026-08-04)
     found this container fetching the summary and keeping only the sites. */
  const [runSummary, setRunSummary] = useState<Record<string, unknown> | null>(null);
  useEffect(() => {
    void fetchRun(caseId).then((result) => {
      if (!mountedRef.current) return;
      setRows(result.kind === "ok" ? result.data.sites : []);
      setRunSummary(result.kind === "ok" ? result.data.summary : null);
    });
  }, [caseId, detail.session.run_state, rowsNonce]);

  const receipts = useMemo(() => evidenceReceipts(runSummary), [runSummary]);
  const entries = useMemo(
    () => adjustQueue(detail.sites, rows, receipts),
    [detail.sites, rows, receipts],
  );
  // The footer's facts: the SAME projection the rail judges, so Adjust's own door to
  // Deliver can never open on a case the rail calls blocked (or vice versa).
  const facts = useMemo(() => factsFromCaseSession(detail), [detail]);
  /* §10-H's "STILL OPEN" line, closed 2026-08-02: from the SAME rows the ALIGNMENT
   * strip and the queue's flag reasons already read — no second fetch, no client-side
   * derivation of the flag itself, only whether to show the notice about it. */
  const clockNotice = useMemo(
    () => unverifiedClockNotice(rows, activeTooth),
    [rows, activeTooth],
  );
  // The queue opens on the first FLAGGED site — the stage's whole reason for existing.
  useEffect(() => {
    if (activeTooth === null && entries.length > 0) {
      setActiveTooth(entries[0]!.tooth);
    }
  }, [entries, activeTooth]);

  const activeEntry = entries.find((e) => e.tooth === activeTooth) ?? null;
  const activeSite: SiteView | null =
    detail.sites.find((s) => s.tooth === activeTooth) ?? null;

  // THE SEATED READ: the shipped fit as the panes render it, per site. Re-read when
  // the site changes; an applied tool hands back the NEW payload directly (no refetch
  // — the response IS the new pose, and re-asking would show the same thing slower).
  useEffect(() => {
    if (activeTooth === null) {
      setPayload(null);
      setSeatedPhase("idle");
      return;
    }
    let cancelled = false;
    setPayload(null);
    setSeatedError(null);
    setSeatedPhase("loading");
    void fetchSeated(caseId, activeTooth).then((result) => {
      if (cancelled || !mountedRef.current) return;
      if (result.kind === "ok") {
        setPayload(result.data);
        setSeatedPhase("ready");
      } else {
        setSeatedError(result.detail);
        setSeatedPhase("error");
      }
    });
    return () => {
      cancelled = true;
    };
  }, [caseId, activeTooth]);

  // AUTO-MARK'S READ (client 2026-07-29, item 3): the site's proposed landmarks,
  // fetched once per site while the tool is open. `autoMarkPhase !== "idle"` gates the
  // fetch so tabbing away and back does not re-ask — the landmarks are the declared
  // template's own feature geometry, and that does not change under an operator's
  // clicks; `handleSelectSite` and a successful apply are what put it back to "idle".
  useEffect(() => {
    if (tool !== "auto-mark" || activeTooth === null || autoMarkPhase !== "idle") {
      return;
    }
    /* SUPERSESSION, NOT CLEANUP-CANCELLATION (client 2026-07-30: "Auto-mark stays
       stuck"). The first version cancelled the fetch in the effect's cleanup — but
       `autoMarkPhase` is a dependency, so setting it to "loading" re-ran the effect
       and the cleanup CANCELLED ITS OWN REQUEST: the 200 arrived 0.4s later and was
       discarded, and the phase stayed "loading" forever. A result is stale only when
       a NEWER request has been minted (a site/tool switch), never merely because the
       phase moved — which is exactly what a monotone request id expresses. */
    const request = ++autoMarkRequestRef.current;
    setAutoMarkPhase("loading");
    setAutoMarkError(null);
    void fetchLandmarks(caseId, activeTooth).then((result) => {
      if (autoMarkRequestRef.current !== request || !mountedRef.current) return;
      if (result.kind === "ok") {
        setAutoMarkLandmarks(result.data);
        setAutoMarkPhase("ready");
        // seed the drafts only when this round has none yet — re-entering the tool
        // after a partial match must not throw the operator's scan clicks away
        setAutoDrafts((current) =>
          current.length > 0 ? current : autoMarkDrafts(result.data),
        );
      } else {
        setAutoMarkError(result.detail);
        setAutoMarkPhase("error");
      }
    });
  }, [tool, caseId, activeTooth, autoMarkPhase]);

  // Switching sites clears the half-built work: a draft pair belongs to the site whose
  // panes it was placed over, and carrying it across would be a mark about nothing.
  const handleSelectSite = useCallback((tooth: number) => {
    setActiveTooth(tooth);
    setFitDrafts([]);
    setAutoDrafts([]);
    setAutoMarkLandmarks([]);
    setAutoMarkPhase("idle");
    setAutoMarkError(null);
    setTrenchArmed(false);
    setRefusal(null);
    setPass(null);
    setLastOutcome(null);
    // A newer site supersedes the re-read's words — they described the PREVIOUS
    // site's row, and rendering them under a different tooth would misattribute the
    // fact. The ref invalidates any response still in flight for the site just left,
    // the same monotone-id discipline autoMarkRequestRef uses one effect over.
    rePreviewRequestRef.current += 1;
    setRePreviewPhase("idle");
    setRePreviewResult(null);
    setRePreviewError(null);
  }, []);

  /** Every tool lands here: optimism OFF — the response is the new truth, a refusal is
   * the gate's own words, and the already-optimal pass is narrowed out of the refusal
   * path before anything renders in the refusal's tone. */
  const settle = useCallback(
    (result: ApiResult<AdjustResultView>) => {
      if (!mountedRef.current) return;
      setPhase("idle");
      const optimal = alreadyOptimalFrom(result);
      if (optimal !== null) {
        setPass(optimal);
        setRefusal(null);
        setLastOutcome(null);
        return;
      }
      setPass(null);
      if (result.kind === "error") {
        setRefusal(result.detail);
        return;
      }
      setRefusal(null);
      setLastOutcome(result.data.outcome);
      // The row this site's strip reads was just rewritten server-side; ask for it
      // again rather than let the toolbar describe the pose the operator moved away
      // from. The PAYLOAD needs no such round trip — the response IS the new pose.
      if (outcomeMovedTheRow(result)) setRowsNonce((n) => n + 1);
      if (result.data.pane_payload !== null) setPayload(result.data.pane_payload);
      onDetail(result.data.case);
      // A newer act — a TOOL, actually applied — supersedes whatever the re-read last
      // said: its words described the site before this act, and the row it read has
      // just moved again.
      setRePreviewResult(null);
      setRePreviewError(null);
      setFitDrafts([]);
      // auto-mark's landmarks are static (the declared template's own geometry, not
      // the pose) — re-seeding straight from what is already known starts a fresh
      // round of matching without a second read the server would answer identically
      setAutoDrafts(autoMarkDrafts(autoMarkLandmarks));
      setTrenchArmed(false);
    },
    [onDetail, autoMarkLandmarks],
  );

  const run = useCallback(
    (request: () => Promise<ApiResult<AdjustResultView>>) => {
      setPhase("working");
      setRefusal(null);
      setPass(null);
      void request().then(settle);
    },
    [settle],
  );

  const handleRotate = useCallback(
    (stepDeg: number) => {
      if (activeTooth === null) return;
      run(() => postRotation(caseId, activeTooth, { step_deg: stepDeg }));
    },
    [caseId, activeTooth, run],
  );

  const handleResetRotation = useCallback(() => {
    if (activeTooth === null) return;
    run(() => postRotation(caseId, activeTooth, { reset: true }));
  }, [caseId, activeTooth, run]);

  const handleBestFit = useCallback(
    (apply: boolean) => {
      if (activeTooth === null) return;
      run(() =>
        postBestFit(caseId, activeTooth, {
          matching_diameter_mm: diameterMm,
          apply,
        }),
      );
    },
    [caseId, activeTooth, diameterMm, run],
  );

  /** START OVER on the ACTIVE tool's set, and only that one — the two sets are kept
   * apart on purpose (see the state above), so a clear must never reach across.
   *
   * Auto-mark's "clear" is a RE-SEED, not an emptying: its drafts are the worker's own
   * proposal, and emptying them would leave the tool with nothing to match and no way
   * to ask again (the landmarks fetch is gated on `autoMarkPhase === "idle"`). This is
   * exactly what `settle` already does after a successful apply. */
  const handleClearPairs = useCallback(() => {
    if (tool === "auto-mark") {
      setAutoDrafts(autoMarkDrafts(autoMarkLandmarks));
      return;
    }
    setFitDrafts([]);
  }, [tool, autoMarkLandmarks]);

  const handleApplyPairs = useCallback(() => {
    if (activeTooth === null) return;
    const bodies = drafts.filter(isComplete).map(pairBody);
    run(() => postFitByPoints(caseId, activeTooth, bodies));
  }, [caseId, activeTooth, drafts, run]);

  const openDraft = drafts.find((d) => !isComplete(d)) ?? null;

  /** ONE PICK ROUTER for both pointer tools. A click on the scan is the trench mark
   * while the trench tool is armed; otherwise it fills the open pair's next slot. A
   * click nothing is waiting for is IGNORED — never an overwrite of a placed mark
   * (the re-click pair-integrity record). */
  const handlePick = useCallback(
    (pane: "part" | "scan") => (point: [number, number, number]) => {
      if (pane === "scan" && trenchArmed && activeTooth !== null) {
        setTrenchArmed(false);
        run(() => postMarkTrench(caseId, activeTooth, point));
        return;
      }
      if (openDraft === null) return;
      setDrafts((current) =>
        current.map((d) => (d.id === openDraft.id ? withPick(d, pane, point) : d)),
      );
    },
    // `tool` picks WHICH draft set `setDrafts` (derived above) actually writes to —
    // omitting it would let this closure keep writing to the tool that was active
    // when it last re-memoized, silently losing a click after a tab switch.
    [caseId, activeTooth, trenchArmed, openDraft, run, tool],
  );

  /** The numbered marks, drawn where they were placed. Memoized by content: the
   * viewer diffs markers by identity, so a fresh array per render would churn the
   * scene graph on every keystroke elsewhere. */
  /* AUTO-MARK'S GHOSTS (§10-AI): where the CURRENT pose claims each placed
     part point sits on the scan — faint, question-marked, display-only. The
     ghost guides the eye; the operator's click stands alone, and the
     ghost-vs-click gap IS the rotation being measured. */
  const ghosts = useMemo(
    () => ghostScanMarkers(drafts, payload?.pose ?? null),
    [drafts, payload],
  );
  const markers = useMemo(() => {
    const base = pairMarkers(drafts);
    if (ghosts.length === 0) return base;
    const drawn = ghosts.map((ghost) => ({
      key: ghost.key,
      position: ghost.position as [number, number, number],
      color: GHOST_POINT_COLOR,
      label: ghost.label,
    }));
    return {
      ...base,
      scan: [...(base.scan ?? []), ...drawn],
      union: [...(base.union ?? []), ...drawn],
    };
  }, [drafts, ghosts]);

  const pickHandlers = useMemo(
    () => ({
      library: handlePick("part"),
      scan: handlePick("scan"),
      union: handlePick("scan"),
    }),
    [handlePick],
  );

  // THE NAMED VIEWPOINT (gap `named-view-presets`). Held by the stage, not the pane,
  // because one click has to move all three — which is the whole point of naming a
  // direction rather than dragging one pane to it.
  const [viewPreset, setViewPreset] = useState<ViewPresetId>("occlusal");
  /* EVERY preset click is a request to re-frame, re-selection included — that is what
     makes a named viewpoint one the operator can RETURN to after orbiting away from it
     (design review 2026-07-31). */
  const [viewPresetNonce, setViewPresetNonce] = useState(0);
  /* THE SHARED ZOOM COUNTER (client 2026-08-02: "global is probably better on
     adjustment views"). One number for the whole workspace, for the same reason the
     preset above is one: the panes are read side by side. */
  const [zoomLevel, setZoomLevel] = useState(0);
  // the link toggle rides the toolbar now — same home as the zoom, same reason.
  // Opens LINKED — the shared policy (domain/workspace, client 2026-08-04).
  const [linked, setLinked] = useState(PANES_OPEN_LINKED);
  const handleToggleLinked = useCallback(() => setLinked((now) => !now), []);
  const handleZoom = useCallback((direction: 1 | -1) => {
    /* CLAMPED AT THE COUNTER, not only at the camera: an unbounded counter accepts
       presses the camera cannot answer, and the operator then presses the other way
       thirty times before anything moves. See clampZoomLevel. */
    setZoomLevel((now) => clampZoomLevel(now + direction));
  }, []);
  const handleSelectView = useCallback((preset: ViewPresetId) => {
    setViewPreset(preset);
    setViewPresetNonce((n) => n + 1);
  }, []);
  /* WHICH PANE WANTS THE NEXT CLICK, said ON the glass (client 2026-07-30). Adjust is
     the only stage that installs pick listeners and it passed neither `armed` nor
     `hints`, so the crosshair cursor and the on-glass hint were dead code and the
     operator armed a tool, read "Library part · pane 1" in the scrolling work column,
     and clicked into a pane that gave no tell. The rule is the pick router's own,
     stated once in domain/adjust.paneArming. */
  const arming = useMemo(
    () => paneArming(openDraft, trenchArmed),
    [openDraft, trenchArmed],
  );
  const scene = useSitePaneScene(detail, activeSite, payload, {
    markers,
    onPick: pickHandlers,
    armed: arming.armed,
    viewPreset,
    viewPresetNonce,
    zoomLevel,
    linked,
  });
  // The off-axis presets need a MEASURED roll. Before a preview lands, panes 2/3 frame
  // down the jaw's occlusal proxy with no clock reference, so buccal/mesial would be a
  // guessed angle wearing an anatomical name — the toolbar greys them instead.
  const viewPresetsAvailable = payload?.pose != null;
  // ONE computation feeds two homes: the strip's variant pill and the Numbers & log
  // panel's Alignment section (the one-row direction, 2026-08-06).
  const adjustToolbarStats = alignmentStats(
    rows, activeTooth, activeSite?.declared_variant ?? null);

  const notices = adjustPaneNotices({
    site: activeEntry,
    partMeshKnown: scene.partMeshKnown,
    partError: scene.partError,
    scanError: scene.scanError,
    scanEmpty: scene.scanEmpty,
    seatedPhase,
    seatedError,
  });

  /* THE RE-CONFIRMATION (client 2026-07-29). Same endpoint Declare's tick uses — the
     act is identical, only its location is new, so the status ladder and the seat
     record stay the single source of what a confirmation means. Optimism stays OFF
     here like everywhere else on this surface: the rung changes because the SERVER
     returned a detail saying so, never because the button was pressed. */
  const [reconfirmSaving, setReconfirmSaving] = useState(false);
  const [reconfirmError, setReconfirmError] = useState<string | null>(null);
  const [reasonsFor, setReasonsFor] = useState<number | null>(null);

  const handleReconfirm = useCallback(() => {
    if (activeTooth === null) return;
    setReconfirmSaving(true);
    setReconfirmError(null);
    void postReview(detail.case.id, activeTooth).then((result) => {
      setReconfirmSaving(false);
      /* ApiResult is a {kind} union — the first version tested `result.ok` and read
         `result.value`/`result.error`, none of which EXIST on this shape. The click
         landed server-side (the rung flipped to ready) and the response was then
         thrown away reading `.detail` off undefined, so the surface never moved:
         "I cant click" was a click that worked and was never shown. Found live; the
         typechecker that should have caught it was checking zero files (the root
         tsconfig is a references shell with files: []) — fixed alongside. */
      if (result.kind === "ok") {
        onDetail(result.data);
        return;
      }
      setReconfirmError(result.detail);
    });
  }, [activeTooth, detail.case.id, onDetail]);

  /* RE-PREVIEW (gap `re-preview-a-site-without-applying-a-tool`, 2026-07-31). A
     re-READ of the site's numbers off the pose already on disk — body-less, because
     everything the route reads is already in the run directory. It is NOT a tool
     (`run`/`settle` above): it applies nothing, so it gets its own optimism-OFF
     handler rather than sharing the tools' `phase`. On success it replaces the pane
     payload verbatim (the same replacement an applied tool makes), adopts the whole
     case detail (the server may have cleared this site's confirmation), and bumps
     `rowsNonce` ONLY where the server says something moved — never a local guess. */
  const handleRePreview = useCallback(() => {
    if (activeTooth === null) return;
    const request = ++rePreviewRequestRef.current;
    setRePreviewPhase("working");
    setRePreviewError(null);
    void postRePreview(caseId, activeTooth).then((result) => {
      // stale only when a NEWER request exists (the operator switched sites while
      // this one was in flight) — never merely because the phase moved
      if (!mountedRef.current || rePreviewRequestRef.current !== request) return;
      setRePreviewPhase("idle");
      if (result.kind === "error") {
        setRePreviewError(result.detail);
        return;
      }
      setRePreviewResult(result.data);
      setPayload(result.data.pane_payload);
      onDetail(result.data.case);
      if (result.data.changed) setRowsNonce((n) => n + 1);
    });
  }, [caseId, activeTooth, onDetail]);

  /* THE DROP (gap `drop-a-cap-from-adjust`). One handler, both directions — the
     reversal is the same request with `false`, so it can never fall behind the act.
     Optimism stays OFF: the row moves because the SERVER returned a detail saying
     the intent landed, and a refusal renders in the gate's own words. */
  const [dropSaving, setDropSaving] = useState(false);
  const [dropError, setDropError] = useState<string | null>(null);

  const [acknowledgeSaving, setAcknowledgeSaving] = useState(false);
  const [acknowledgeError, setAcknowledgeError] = useState<string | null>(null);
  const handleAcknowledgeException = useCallback(
    (tooth: number, give: boolean) => {
      setAcknowledgeSaving(true);
      setAcknowledgeError(null);
      const act = give ? postAcknowledgeException : deleteAcknowledgeException;
      void act(caseId, tooth).then((result) => {
        if (!mountedRef.current) return;
        setAcknowledgeSaving(false);
        if (result.kind === "ok") {
          onDetail(result.data);
          return;
        }
        // the BFF's refusal verbatim — eligibility is ITS rule, never re-derived here
        setAcknowledgeError(result.detail);
      });
    },
    [caseId, onDetail],
  );

  const handleDrop = useCallback(
    (tooth: number, withhold: boolean) => {
      setDropSaving(true);
      setDropError(null);
      void putWithholdIntent(caseId, tooth, withhold).then((result) => {
        if (!mountedRef.current) return;
        setDropSaving(false);
        // ApiResult is a {kind} union — `.ok`/`.value` do not exist on it, and
        // reading them has silently discarded a landed write twice in this app
        if (result.kind === "ok") {
          onDetail(result.data);
          return;
        }
        setDropError(result.detail);
      });
    },
    [caseId, onDetail],
  );

  const panes = (
    /* No link props — the toggle is the toolbar's now (client 2026-08-02); the panes'
       own chrome row returns only while a pane is maximized. */
    <SitePanesView
      variantLabel={activeSite?.declared_variant ?? null}
      notices={notices}
      partBusy={scene.partBusy}
      scanBusy={scene.scanBusy}
      scanCaption={scene.scanCaption}
      unionCaption={adjustUnionCaption(
        payload,
        lastOutcome,
        /* the caption must not deny the operator's own re-applied work (the
           audit's caption misclaim) — count this site's applied receipts */
        receipts.filter(
          (r) => r.tooth === activeTooth && r.outcome === "applied",
        ).length,
      )}
      unionBusy={seatedPhase === "loading" || scene.scanBusy || phase === "working"}
      unionBusyMessage={
        phase === "working"
          ? "judging the proposal against the certification gates…"
          : seatedPhase === "loading"
            ? "reading the shipped fit for this site…"
            : null
      }
      payload={payload}
      libraryViewer={scene.libraryViewer}
      scanViewer={scene.scanViewer}
      unionViewer={scene.unionViewer}
      layers={scene.layers}
      onToggleLayer={scene.onToggleLayer}
      onChangeOpacity={scene.onChangeOpacity}
      maximizedId={scene.maximizedId}
      onToggleMaximized={scene.onToggleMaximized}
      onResetView={scene.onResetView}
      scaleId={scene.scaleId}
      onSelectScale={scene.onSelectScale}
      hints={arming.hints}
    />
  );

  return (
    <AdjustStageView
      relief={
        activeTooth === null
          ? null
          : {
              siteValue:
                detail.sites.find((x) => x.tooth === activeTooth)
                  ?.gingival_offset_mm ?? null,
              caseValue: detail.choices.effective_relief?.value ?? null,
              ceilingLine: siteReliefCeilingLine(
                detail.relief_ceilings,
                detail.sites.find((x) => x.tooth === activeTooth)
                  ?.declared_variant ?? null,
              ),
              runDone: detail.session.run_state === "done",
              saving: reliefSaving,
              error: reliefError,
              onApply: (value) => {
                setReliefSaving(true);
                setReliefError(null);
                void putSiteRelief(caseId, activeTooth, value).then((result) => {
                  if (!mountedRef.current) return;
                  setReliefSaving(false);
                  if (result.kind === "ok") onDetail(result.data);
                  else setReliefError(result.detail);
                });
              },
            }
      }
      viewPreset={viewPreset}
      onSelectView={handleSelectView}
      viewPresetsAvailable={viewPresetsAvailable}
      zoomLevel={zoomLevel}
      onZoom={handleZoom}
      linked={linked}
      onToggleLinked={handleToggleLinked}
      entries={entries}
      receiptsCarried={receiptsCarriedByReemit(runSummary)}
      ghostsActive={ghosts.length > 0}
      activeTooth={activeTooth}
      onSelectSite={handleSelectSite}
      tool={tool}
      onSelectTool={setTool}
      phase={phase}
      refusal={refusal}
      pass={pass}
      lastOutcome={lastOutcome}
      cumulativeDeg={lastOutcome?.cumulative_deg ?? null}
      onRotate={handleRotate}
      onResetRotation={handleResetRotation}
      diameterMm={diameterMm}
      onChangeDiameter={setDiameterMm}
      onBestFit={handleBestFit}
      trenchArmed={trenchArmed}
      onArmTrench={() => setTrenchArmed((now) => !now)}
      drafts={drafts}
      onStartPair={(span, partSpan = false) =>
        setDrafts((current) => [
          ...current,
          newPairDraft(`pair-${current.length + 1}-${Date.now()}`, span, partSpan),
        ])
      }
      onRemovePair={(id) => setDrafts((current) => current.filter((d) => d.id !== id))}
      onRemovePoint={(id, slot) =>
        setDrafts((current) =>
          current.map((d) => (d.id === id ? withoutPick(d, slot) : d)),
        )
      }
      onApplyPairs={handleApplyPairs}
      onClearPairs={handleClearPairs}
      panes={panes}
      activeStatus={activeSite?.status ?? null}
      onReconfirm={handleReconfirm}
      reconfirmSaving={reconfirmSaving}
      reconfirmError={reconfirmError}
      seatedPhase={seatedPhase}
      seatedPayloadPresent={payload !== null}
      pose={payload?.pose ?? null}
      clock={payload?.clock_reference ?? null}
      reasonsFor={reasonsFor}
      onOpenReasons={setReasonsFor}
      onCloseReasons={() => setReasonsFor(null)}
      autoMarkLandmarks={autoMarkLandmarks}
      autoMarkPhase={autoMarkPhase}
      autoMarkError={autoMarkError}
      onDrop={handleDrop}
      dropSaving={dropSaving}
      dropError={dropError}
      onAcknowledgeException={handleAcknowledgeException}
      acknowledgeSaving={acknowledgeSaving}
      acknowledgeError={acknowledgeError}
      onRePreview={handleRePreview}
      rePreviewPhase={rePreviewPhase}
      rePreviewResult={rePreviewResult}
      rePreviewError={rePreviewError}
      /* §10-H's "STILL OPEN" line, closed: from the SAME rows the strip and the
         queue already read — no second fetch, no derivation of the flag itself. */
      clockNotice={clockNotice}
      /* The footer's facts come from the ONE flow model, not from a second count
         taken here: `blockedReason` is what the rail itself shows for Deliver, and
         `siteFlagged` is the BFF's rollup. Navigation only — no POST, no status. */
      flaggedCount={facts.siteFlagged}
      deliverBlockedReason={blockedReason("deliver", facts)}
      /* The strip's facts, all of them the run's own row for THIS site — the same
         rows the queue's flag reasons come from, so the toolbar and the queue cannot
         describe one site two ways. PAIRS reads the row's `correspondence` block and
         renders a dash where the server wrote none (never an invented 0 / 8). */
      systemModel={detail.system.effective_model}
      stats={adjustToolbarStats}
      onBack={() => navigate(`/case/${caseId}/declare`)}
      onForward={() => navigate(`/case/${caseId}/deliver`)}
      /* THE PROVENANCE POPOVER: assembled here, not in the View, because it needs
         this stage's caseId — same reasoning as `panes` above. `detail` is the
         refresh key: it is only replaced wholesale when an act actually lands.
         The SAME stats feed its Alignment section (one-row direction, 2026-08-06). */
      insightSlot={
        <WorkspaceInsight
          caseId={caseId}
          tooth={activeTooth}
          refreshKey={detail}
          stats={adjustToolbarStats}
        />
      }
    />
  );
}
