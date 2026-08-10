/**
 * DECLARE (plan §4 Declare / AM-8, slice 5a): the site queue on the LEFT (tooth,
 * status chip, capture chip, declared variant — click makes a site active), the
 * case-scoped SYSTEM bar on TOP (effective system with its server-attributed
 * "suggested" tag; switching asks in WORDS naming the reset count BEFORE any PUT —
 * the visible-reset doctrine), and the active site's VARIANT cards in the CENTRE
 * (Ø × height from the catalog payload, the superseded shelf collapsed behind a
 * labelled fold; a click IS the declaration PUT).
 *
 * Direction of trust (AM-4): optimism is OFF. Every PUT's response is the whole new
 * detail and replaces the payload verbatim (onDetail); a refusal renders in the
 * backend's own words while the surface keeps showing what is actually persisted.
 * The reset a system switch causes happens SERVER-side (bff status machine) — this
 * component only asks first and displays what came back.
 *
 * 5b lands the three live panes beside this queue (components/DeclarePanes — the
 * demo's VerifyStage semantics, rebuilt against BFF shapes) and WITH them the review
 * tick (AM-8: "reviewed over panels, not a checkbox"); Declare completes only when
 * every site is reviewed (domain/flow.ts).
 */
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useDialogEscape } from "./useDialogEscape";
import { useDialogFocus } from "./useDialogFocus";
import { useNavigate } from "react-router-dom";
import {
  fetchRun,
  postAdjustDecision,
  postRun,
  putDeclaration,
  putSystem,
  type AdjustDecisionView,
  type CaseSessionDetail,
  type SiteView,
} from "../api/client";
import {
  blockedReason,
  factsFromCaseSession,
  isReachable,
} from "../domain/flow";
import {
  VIEW_PRESETS,
  activeSiteFrom,
  alignmentStats,
  attestationSummary,
  declareCautionWords,
  declareQueueSummary,
  declaredLabel,
  siteIdentity,
  siteStateSentence,
  resetCount,
  runKeyFor,
  shouldAutoRun,
  skipConsequenceWords,
  switchWords,
  systemCards,
  recordedAtWords,
  variantShelves,
  type VariantCard,
  type PreviewFigures,
  type ViewPresetId,
  type WorkspaceStat,
} from "../domain/declare";
import { PANES_OPEN_LINKED, paneLinkLabel } from "../domain/workspace";
import { canZoom, clampZoomLevel } from "viewer";
import { captureChipLabel } from "../domain/intake";
import { DeclarePanes } from "./DeclarePanes";
import { MainStage } from "./MainStage";
import { WorkspaceInsight } from "./WorkspaceInsight";

/** What is in flight, named — the surface states it instead of freezing silently. */
export type DeclareSaving = "idle" | "system" | "declaration";

/** The run POST's client-side lifecycle (5c): the in-process worker completes the
 * whole run inside the request, so "firing" IS the progress state — the persisted
 * queued|running states only surface to OTHER readers (the worklist) meanwhile. */
export type RunPhase = "idle" | "firing";

/** The fork's own in-flight state (client 2026-07-27 #3): the decision POSTs, and
 * only a landed decision navigates — a recorded choice must not race the route. */
export type ForkSaving = "idle" | "skip" | "adjust";

interface SystemSelectProps {
  readonly detail: CaseSessionDetail;
  readonly onAskSwitch: (model: string) => void;
}

/**
 * THE SYSTEM PICKER IS A SELECT NOW (client 2026-08-02: "there is a lot of real
 * estate for the buttons … we need to be more cohesive and organized about the
 * information we show"). The cards' claims all survive the shrink: the EFFECTIVE
 * model is the selected option, the shelf size rides in each option's text, and the
 * server's suggested attribution marks its option — options carry data-model and the
 * suggested one data-role="suggested-tag", so the tests pin the same facts they
 * pinned on the cards.
 *
 * The consent ceremony is untouched: onChange asks, it never PUTs. The select is
 * CONTROLLED by the effective model, so until the operator consents in the
 * SwitchConfirm below it visibly springs back — the control never claims a switch
 * the server has not made.
 */
function SystemSelect({ detail, onAskSwitch }: SystemSelectProps) {
  const effective = detail.system.effective_model ?? "";
  return (
    <label className="declare-controls__field">
      <span className="declare-controls__label">Implant system</span>
      <select
        data-role="declare-system"
        className="decode-select"
        value={effective}
        onChange={(event) => {
          if (event.target.value !== "") onAskSwitch(event.target.value);
        }}
      >
        {effective === "" && <option value="">choose a system…</option>}
        {systemCards(detail).map((card) => (
          <option
            key={card.model}
            value={card.model}
            data-model={card.model}
            data-role={card.suggested ? "suggested-tag" : undefined}
          >
            {card.model} — {card.variantCount} part
            {card.variantCount === 1 ? "" : "s"}
            {card.suggested ? " · suggested" : ""}
          </option>
        ))}
      </select>
    </label>
  );
}

interface SwitchConfirmProps {
  readonly detail: CaseSessionDetail;
  readonly pendingSwitch: string;
  readonly onConfirm: () => void;
  readonly onCancel: () => void;
}

/** The visible-reset moment: the words carry the count, the PUT waits for consent —
 * amber (a consequence to consent to), never the danger red. */
function SwitchConfirm({ detail, pendingSwitch, onConfirm, onCancel }: SwitchConfirmProps) {
  return (
    <div data-role="system-switch-confirm" role="alert" className="switch-confirm">
      <p className="switch-confirm__words">
        {switchWords(pendingSwitch, resetCount(detail))}
      </p>
      <div className="switch-confirm__actions">
        <button type="button" className="button button--primary button--small" onClick={onConfirm}>
          Switch system
        </button>
        <button type="button" className="button button--secondary button--small" onClick={onCancel}>
          Keep {detail.system.effective_model ?? "the current system"}
        </button>
      </div>
    </div>
  );
}

interface SiteQueueProps {
  readonly detail: CaseSessionDetail;
  readonly activeTooth: number | null;
  /** The current run's verdict rows, empty before a run exists — the ONLY source of
   * a measured number on these rows (the client never re-derives one). */
  readonly runRows: ReadonlyArray<Record<string, unknown>>;
  readonly onSelectSite: (tooth: number) => void;
}

/** The site queue: every site, its server facts, one click = active — the demo's
 * stepper-list clothes (.decode-stepper__item), status/capture as chips. */
function SiteQueue({ detail, activeTooth, runRows, onSelectSite }: SiteQueueProps) {
  const active = activeSiteFrom(detail.sites, activeTooth);
  return (
    <aside data-role="declare-queue" aria-label="Site queue" className="panel">
      <h3 className="panel__title">Sites in this case</h3>
      {/* THE PROGRESS LINE (gap `declare-queue-header`): Adjust's queue has headed
          with its counts since slice 6 and Declare's did not, so the stage with a
          per-site obligation was the one that never said how many were left. Hidden
          on an empty queue only because `declare-empty` below says it better. */}
      {detail.sites.length > 0 && (
        <p data-role="queue-summary" className="panel__hint">
          {declareQueueSummary(detail.sites)}
        </p>
      )}
      <ul className="decode-stepper__overview">
        {detail.sites.map((site) => (
          <li key={site.tooth}>
            <button
              type="button"
              data-role="queue-site"
              aria-pressed={active?.tooth === site.tooth}
              data-tooth={site.tooth}
              className={`decode-stepper__item decode-stepper__item--stacked${
                active?.tooth === site.tooth ? " decode-stepper__item--active" : ""
              }${site.status === "ready" ? " decode-stepper__item--reviewed" : ""}`}
              onClick={() => onSelectSite(site.tooth)}
            >
              <span className="decode-stepper__position">Tooth {site.tooth}</span>
              <span className="decode-stepper__chips">
                <span
                  data-role="status-chip"
                  data-status={site.status}
                  className="chip chip--status"
                >
                  {site.status}
                </span>{" "}
                <span
                  data-role="capture-chip"
                  data-verdict={site.capture?.verdict ?? "none"}
                  className={
                    site.capture === null
                      ? "chip chip--capture-none"
                      : `chip chip--capture-${site.capture.verdict}`
                  }
                >
                  {captureChipLabel(site.capture)}
                </span>{" "}
                <span data-role="declared-variant" className="decode-stepper__declared">
                  {declaredLabel(site)}
                </span>
              </span>
              {/* THE ROW'S STATE IN WORDS (gap `queue-row-state-sentence`). The chip
                  above keeps the wire's rung — it is the colour key, and data-status
                  is what the stylesheet reads — but the operator gets a sentence that
                  names their next act, and the RUN's own number once one exists. */}
              <span data-role="queue-state" className="decode-stepper__state">
                {siteStateSentence(site, runRows)}
              </span>
            </button>
          </li>
        ))}
      </ul>
      {detail.sites.length === 0 && (
        <p data-role="declare-empty" className="panel__hint">
          No sites to declare on this case yet.
        </p>
      )}
    </aside>
  );
}

interface VariantChipProps {
  readonly card: VariantCard;
  readonly declared: boolean;
  /** True on the superseded shelf — the chip wears the archived tone. */
  readonly archived?: boolean;
  readonly onDeclare: (variantId: string) => void;
}

/** One catalog part, as a chip: code, dims, and — where detection proposed it — a
 *  BADGE on the face of the page. */
function VariantChip({ card, declared, archived, onDeclare }: VariantChipProps) {
  return (
    <button
      type="button"
      data-role="variant-card"
      data-variant={card.id}
      aria-pressed={declared}
      className={`decode-variant${declared ? " decode-variant--selected" : ""}${
        archived ? " decode-variant--archived" : ""
      }`}
      onClick={() => onDeclare(card.id)}
    >
      {/* the part's own face (client 2026-08-09): the SERVED top-view render —
          small beside the dense shelf's words, large in the archive dialog (CSS
          decides by context). Absent when the catalog serves no thumbnail. */}
      {card.topUrl !== null && (
        <img
          data-role="variant-top"
          className="decode-variant__thumb"
          src={card.topUrl}
          alt=""
          loading="lazy"
        />
      )}
      <span className="decode-variant__name">{card.label}</span>{" "}
      <span className="decode-variant__dims">{card.dims}</span>
      {card.suggested && (
        <span
          data-role="variant-suggested"
          className="library-badge library-badge--suggested"
        >
          {" "}
          {/* client escalation 2026-08-09: a MEASURED suggestion (detection's own
              honest height+diameter read) wears its own word on the same badge —
              the smallest honest change, never a redesigned chip */}
          {card.suggestedSource === "measured" ? "measured" : "sugg."}
        </span>
      )}
    </button>
  );
}

interface VariantChipsProps {
  readonly active: SiteView | null;
  readonly shelves: ReturnType<typeof variantShelves>;
  readonly onDeclare: (variantId: string) => void;
  readonly onOpenArchive: () => void;
}

/**
 * THE VARIANT PICKER, BACK TO CHIPS (client 2026-08-02, reversing their own earlier
 * ask the same day: "the implant variant should not be a dropdown and we need the
 * suggested").
 *
 * The reversal has a reason visible in the markup. Inside a collapsed select,
 * detection's proposal is a word in an option nobody reads until they open it — the
 * server has published `suggested_variant` per site since 5a precisely so the operator
 * can SEE what was proposed for the site they are declaring, and a dropdown put it back
 * out of sight. On a chip it is a badge on the page.
 *
 * The real-estate complaint that drove the dropdown was real, and it is answered by
 * the chips' SIZE rather than by hiding them: one dense wrapping row, not a grid of
 * cards. The superseded shelf stays behind its own fold — kept apart from the current
 * shelf, never mixed into it.
 */
function VariantChips({
  active,
  shelves,
  onDeclare,
  onOpenArchive,
}: VariantChipsProps) {
  return (
    <div
      data-role="variant-cards"
      className="declare-controls__field declare-controls__field--variant"
    >
      <span className="declare-controls__label">
        {active !== null ? `Variant for tooth ${active.tooth}` : "Variant"}
      </span>
      {active === null ? (
        <p className="panel__hint">Pick a site to declare its cap.</p>
      ) : (
        <>
          <div className="decode-variant-list">
            {shelves.current.map((card) => (
              <VariantChip
                key={card.id}
                card={card}
                declared={active.declared_variant === card.id}
                onDeclare={onDeclare}
              />
            ))}
          </div>
          {shelves.superseded.length > 0 && (
            <button
              type="button"
              data-role="superseded-open"
              className="decode-archive__title"
              aria-haspopup="dialog"
              onClick={onOpenArchive}
            >
              Superseded shelf — {shelves.superseded.length} archived part
              {shelves.superseded.length === 1 ? "" : "s"}
            </button>
          )}
        </>
      )}
    </div>
  );
}

export interface WorkspaceToolbarProps {
  readonly tooth: number | null;
  readonly systemModel: string | null;
  /** The active site's rung, rendered VERBATIM — the server's word, never ours. */
  readonly status: string | null;
  readonly stats: readonly WorkspaceStat[];
  /** The named viewpoints. Rendered only when `onSelectView` is supplied: a preset
   *  that cannot reach a camera is a control that lies about what a click does. */
  readonly viewPreset?: ViewPresetId;
  readonly onSelectView?: (preset: ViewPresetId) => void;
  /** False before a seated pose exists — the off-axis presets need the measured clock
   *  reference (domain/declare.presetFraming), and occlusal alone stays live.
   *
   *  DEFAULTS TO FALSE (design review 2026-07-31). It defaulted to TRUE, and the one
   *  caller that never supplied it — DeclareStage — therefore offered both off-axis
   *  presets before any preview existed: pane 1 swung side-on (partCameraFrame always
   *  carries up:[1,0,0]) while panes 2/3 stayed on the occlusal proxy with no clock
   *  reference to rotate about, and the toolbar latched the new view for all three.
   *  A preset that cannot reach a camera is a control that lies; the safe default is
   *  the one that cannot. */
  readonly viewPresetsAvailable?: boolean;
  /** THE WORKSPACE'S SHARED ZOOM COUNTER and its step. Rendered only when `onZoom` is
   *  supplied, by the same rule the presets follow.
   *
   *  ONE control for all three panes, not one per pane (client 2026-08-02, "global is
   *  probably better on adjustment views"). The comp zooms the pane under the cursor;
   *  ours cannot, because the three panes are read SIDE BY SIDE and a zoom that reached
   *  only one of them would make that comparison lie about scale. */
  readonly zoomLevel?: number;
  readonly onZoom?: (direction: 1 | -1) => void;
  /** THE LINK TOGGLE, moved here from the panes' own chrome row (client 2026-08-02:
   *  "There is three rows of buttons which takes a lot of real estate in the screen
   *  for the panels"). Linking is workspace chrome by the same argument as the zoom
   *  beside it — one act, all three cameras — and the row it held alone is gone;
   *  SitePanesView's own strip now returns only while a pane is maximized. */
  readonly linked?: boolean;
  readonly onToggleLinked?: () => void;
  /** A stage's own control that belongs on this strip (Declare's arch opener) — so
   *  the stage keeps ONE row of chrome above the panes rather than two. */
  readonly children?: ReactNode;
  /** BESIDE THE STATUS CHIP (§10-AN slice C): Declare's amber caution indicator —
   *  "reworked since the run" and rescan-grade capture notices, moved off the row
   *  into a modal this chip opens (client 2026-08-06: "any warnings ... need to come
   *  in as modals"). Sits right after `toolbar-status`, which is the "site's status"
   *  the task names as the chip's anchor. Omitted, nothing renders here — Adjust's
   *  own caution chip lives in the dock header instead (a different set of facts). */
  readonly cautionSlot?: ReactNode;
  /** The strip's LAST item, after the metrics — the comp ends its toolbar with
   *  "▸ budget & log", and ours ends with the insight popover for the same reason:
   *  the readouts finish the row, and the control that expands them sits with them. */
  readonly endSlot?: ReactNode;
}

/** The two zoom acts. `in` steps the level UP, which the viewer reads as a SMALLER
 *  camera distance — the sign lives in viewer/zoom.ts and is pinned there. */
const ZOOM_ACTS = [
  { id: "out", direction: -1, glyph: "−", label: "Zoom out", title: "Zoom all panes out" },
  { id: "in", direction: 1, glyph: "+", label: "Zoom in", title: "Zoom all panes in" },
] as const satisfies readonly {
  readonly id: string;
  readonly direction: 1 | -1;
  readonly glyph: string;
  readonly label: string;
  readonly title: string;
}[];

/** The comp's four toolbar chips (§10-AN slice C): VARIANT, DEV RMS, ROTATION,
 *  PAIRS — `alignmentStats` also publishes DEV P90, which stays off the strip (still
 *  in the Numbers & log panel) so the row matches the comp's own four, not five. */
const STRIP_STAT_IDS: ReadonlySet<string> = new Set([
  "variant",
  "dev-rms",
  "rotation",
  "pairs",
]);

/**
 * THE WORKSPACE TOOLBAR — the identity anchor the pane-dominant layout cost us.
 *
 * Declare and Adjust share a workspace and had no shared toolbar: Adjust had none at
 * all, Declare's held exactly one control (the arch dialog opener). Meanwhile the
 * tooth number lived only in the work column's panel headings and the queue rows —
 * every one of which SCROLLS (workbench__work-scroll) — so on a long case an operator
 * could have three live panes up and nothing on screen naming whose site they showed.
 *
 * It is exported from this module rather than split into its own file so the two
 * stages cannot drift into two different toolbars; the natural later home is
 * components/WorkspaceToolbar.tsx once something outside Declare/Adjust wants it.
 *
 * WHAT DOES NOT PORT (design flow.dc.html 206-266): the design's strip colours its
 * chip from a client-side `verdict()` and its MAX DEV from a client-side
 * `deviation()` against a client-side `tolerance`. Here the chip is the server's
 * `SiteView.status` string and the numbers are the run's own published figures — this
 * component computes nothing it displays.
 */
export function WorkspaceToolbar({
  tooth,
  systemModel,
  status,
  stats,
  viewPreset = "occlusal",
  onSelectView,
  viewPresetsAvailable = false,
  zoomLevel = 0,
  onZoom,
  linked = false,
  onToggleLinked,
  children,
  cautionSlot = null,
  endSlot,
}: WorkspaceToolbarProps) {
  const identity = siteIdentity(tooth, systemModel);
  return (
    <div
      data-role="workspace-toolbar"
      className="stage-toolbar workspace-toolbar"
      role="group"
      aria-label="Workspace"
    >
      <span data-role="site-chip" className="workspace-toolbar__site">
        <span aria-hidden="true">⊞</span> {identity.tooth}
        <span className="workspace-toolbar__site-system">{identity.system}</span>
      </span>
      {children}
      {onSelectView !== undefined && (
        <span
          className="workspace-toolbar__views"
          role="group"
          aria-label="Named viewpoints"
        >
          {VIEW_PRESETS.map((preset) => (
            <button
              key={preset.id}
              type="button"
              data-role="view-preset"
              data-preset={preset.id}
              aria-pressed={viewPreset === preset.id}
              /* occlusal IS each pane's own framing, so it survives a missing pose;
                 the off-axis two need the measured roll and say nothing without it */
              disabled={!viewPresetsAvailable && preset.id !== "occlusal"}
              title={
                viewPresetsAvailable || preset.id === "occlusal"
                  ? preset.title
                  : "Needs this site's seated pose — nothing has measured its clock yet."
              }
              className={`button button--ghost button--small${
                viewPreset === preset.id ? " button--active" : ""
              }`}
              onClick={() => onSelectView(preset.id)}
            >
              {preset.label}
            </button>
          ))}
        </span>
      )}
      {onZoom !== undefined && (
        <span className="workspace-toolbar__zoom" role="group" aria-label="Zoom all panes">
          {ZOOM_ACTS.map((act) => (
            <button
              key={act.direction}
              type="button"
              data-role="zoom"
              data-direction={act.id}
              /* The band belongs to packages/viewer — this asks whether a step remains,
                 it does not decide where the camera may go. */
              disabled={!canZoom(zoomLevel, act.direction)}
              title={act.title}
              aria-label={act.label}
              className="button button--ghost button--small"
              onClick={() => onZoom(act.direction)}
            >
              <span aria-hidden="true">{act.glyph}</span>
            </button>
          ))}
        </span>
      )}
      {onToggleLinked !== undefined && (
        <button
          type="button"
          data-role="pane-link"
          aria-pressed={linked}
          className={`button button--ghost button--small${linked ? " button--active" : ""}`}
          onClick={onToggleLinked}
          /* No disabled-while-maximized state up here: the toolbar cannot see the
             maximize, and the toggle is a standing preference either way — it takes
             effect the moment three panes are back on screen. */
          title="Rotate all three panels together (same angles and zoom, each around its own content)"
        >
          {paneLinkLabel(linked)}
        </button>
      )}
      <span data-role="alignment-strip" className="workspace-toolbar__metrics">
        <span className="workspace-toolbar__metrics-label">ALIGNMENT</span>
        <span
          data-role="toolbar-status"
          data-status={status ?? "none"}
          className="chip chip--status"
        >
          {status ?? "no site selected"}
        </span>
        {cautionSlot}
        {/* THE FOUR CHIPS ARE BACK (§10-AN slice C, client 2026-08-06 comp read
            directly: "match the designs" — VARIANT, DEV RMS (our honest label, never
            the comp's client-computed "MAX DEV"), ROTATION, PAIRS). The 2026-08-06
            one-row ruling that had trimmed this to VARIANT alone stands for the ROW
            SHAPE (nowrap, one line — the panes still get the space back), not for the
            figures: the client's later design supersedes their earlier removal. The
            same four still appear in the Numbers & log panel too (WorkspaceInsight);
            this is a second location for the same served facts, not a second source
            of them. The title carries the full value for the day one ellipsizes. */}
        {stats
          .filter((stat) => STRIP_STAT_IDS.has(stat.id))
          .map((stat) => (
          <span
            key={stat.id}
            data-role="alignment-stat"
            data-stat={stat.id}
            title={stat.value}
            className="workspace-toolbar__stat"
          >
            <span className="workspace-toolbar__stat-key">{stat.label}</span>
            <span className="workspace-toolbar__stat-value">{stat.value}</span>
          </span>
        ))}
      </span>
      {endSlot}
    </div>
  );
}

export interface DeclareStageViewProps {
  readonly detail: CaseSessionDetail;
  readonly activeTooth: number | null;
  /** A system switch awaiting the operator's worded consent, or null. */
  readonly pendingSwitch: string | null;
  readonly saving: DeclareSaving;
  readonly error: string | null;
  /** The current run's verdict rows (GET /{id}/run), which is where a queue row's
   * measured deviation comes from — never a client re-derivation. Empty (the default)
   * is the honest pre-run state, and the rows SAY so rather than print a dash. */
  readonly runRows?: ReadonlyArray<Record<string, unknown>>;
  /** The auto-fired run's client lifecycle (5c); defaults idle for static tests. */
  readonly runPhase?: RunPhase;
  /** A run POST that never reached an outcome (transport/409) — stated with retry. */
  readonly runError?: string | null;
  readonly onRetryRun?: () => void;
  /** The Delivery-vs-Skip fork (client 2026-07-27 #3): which decision is in flight,
   * the BFF's refusal if one came back, and the two acts. Defaulted so the View
   * stays statically renderable. */
  readonly forkSaving?: ForkSaving;
  readonly forkError?: string | null;
  readonly onSkipAdjustments?: () => void;
  readonly onAdjustFits?: () => void;
  readonly onSelectSite: (tooth: number) => void;
  readonly onAskSwitch: (model: string) => void;
  readonly onConfirmSwitch: () => void;
  readonly onCancelSwitch: () => void;
  readonly onDeclare: (variantId: string) => void;
  /** THE NAMED VIEWPOINTS (gap `named-view-presets`). Passed through to the toolbar,
   * which renders the control group only when a handler exists — see the note on the
   * stage's toolbar below for why this stage supplies none yet. */
  readonly viewPreset?: ViewPresetId;
  readonly onSelectView?: (preset: ViewPresetId) => void;
  readonly viewPresetsAvailable?: boolean;
  /** THE SHARED ZOOM (client 2026-08-02). Passed to the toolbar, which renders the pair
   * only when a handler exists, and to the panes, which apply the steps they have not
   * applied yet. Held by the CONTAINER rather than here so all three panes and the two
   * buttons read one number — see WorkspaceToolbarProps for why it is not per-pane. */
  readonly zoomLevel?: number;
  readonly onZoom?: (direction: 1 | -1) => void;
  /** The link toggle's state and act — held by the container like the zoom, because
   *  the toolbar and the panes both read it (see WorkspaceToolbarProps). */
  readonly linked?: boolean;
  readonly onToggleLinked?: () => void;
  /** What the PREVIEW published for the active site, while no run has measured it
   *  (design review 2026-07-31) — see domain/declare.alignmentStats. */
  readonly previewFigures?: PreviewFigures | null;
  /** The three live panes + the review tick (5b) — the container passes the
   * DeclarePanes container; View tests may omit it (the panes have their own). */
  readonly panesSlot?: ReactNode;
  /** THE CAUTION MODAL (§10-AN slice C — the switch-confirm/reasons-dialog precedent:
   *  a data-driven dialog is a PROP, not view-local state, so a static render can pin
   *  it open). Held by the container like `pendingSwitch`; the View only asks "is it
   *  open" and calls back to close it. Optional with an inert default: static callers
   *  predate it. */
  readonly cautionsOpen?: boolean;
  readonly onOpenCautions?: () => void;
  readonly onCloseCautions?: () => void;
  /** THE RE-RUN ON ALIGNMENT (client 2026-08-09: "I want the re-run in the
   *  alignment page"). The same full authorized run the confirm act fires,
   *  offered again once a run's rows exist — §10-AD re-applies the operator's
   *  evidence after the automation. Null/omitted = no button. */
  readonly onRerunAlignment?: (() => void) | null;
  /** Why the run gate would refuse right now (client's 422, 2026-08-10: the
   *  button fired into "still needs: tooth N reviewed"). Non-null DISABLES the
   *  button and rides its title, so the gate speaks before the round trip. */
  readonly rerunBlockedReason?: string | null;
  /** THE SUPERSEDED SHELF, OUT OF FLOW (client 2026-08-09: opening it "shrinks the
   *  panels — the panels need to be always the main center of attention and size
   *  should not change"). A prop for the same reason `cautionsOpen` is one: a static
   *  render can pin it open. Optional with an inert default. */
  readonly archiveOpen?: boolean;
  readonly onOpenArchive?: () => void;
  readonly onCloseArchive?: () => void;
}

/** The stage's whole surface, pure payload → markup — statically testable. */
export function DeclareStageView({
  detail,
  activeTooth,
  pendingSwitch,
  saving,
  error,
  runRows = [],
  runPhase = "idle",
  runError = null,
  onRetryRun,
  forkSaving = "idle",
  forkError = null,
  onSkipAdjustments = () => undefined,
  onAdjustFits = () => undefined,
  onSelectSite,
  onAskSwitch,
  onConfirmSwitch,
  onCancelSwitch,
  onDeclare,
  viewPreset,
  onSelectView,
  viewPresetsAvailable,
  zoomLevel,
  onZoom,
  linked,
  onToggleLinked,
  previewFigures = null,
  panesSlot,
  cautionsOpen = false,
  onOpenCautions = () => undefined,
  onCloseCautions = () => undefined,
  onRerunAlignment = null,
  rerunBlockedReason = null,
  archiveOpen = false,
  onOpenArchive = () => undefined,
  onCloseArchive = () => undefined,
}: DeclareStageViewProps) {
  const facts = factsFromCaseSession(detail);
  const active = activeSiteFrom(detail.sites, activeTooth);
  /* Local by design: whether the arch dialog is open is presentation, not case state —
     nothing downstream reads it, so it earns no prop. Static tests render it CLOSED,
     which is also the honest default: the panes are the subject of this stage. */
  const [archOpen, setArchOpen] = useState(false);
  // Escape closes the arch-context dialog.
  useDialogEscape(archOpen, () => setArchOpen(false));
  // Focus moves in, is trapped, and comes back on close (§10-O.8) — see useDialogFocus.
  const archDialogRef = useRef<HTMLElement | null>(null);
  useDialogFocus(archOpen, archDialogRef);
  // THE CAUTION MODAL (§10-AN slice C): "reworked since the run" + a rescan-grade
  // capture verdict, moved off the row into ONE dialog an amber chip opens.
  useDialogEscape(cautionsOpen, onCloseCautions);
  const cautionsDialogRef = useRef<HTMLElement | null>(null);
  useDialogFocus(cautionsOpen, cautionsDialogRef);
  // THE ARCHIVE (client 2026-08-09) — same chrome, same escape and focus discipline.
  useDialogEscape(archiveOpen, onCloseArchive);
  const archiveDialogRef = useRef<HTMLElement | null>(null);
  useDialogFocus(archiveOpen, archiveDialogRef);
  const cautionWords = declareCautionWords(active, runRows);
  // Per-SITE shelves: the detector's proposal is a fact about the active site, so the
  // same catalog marks a different card as the operator moves down the queue.
  const shelves = variantShelves(detail, active);
  // ONE computation feeds two homes: the strip's variant pill and the Numbers & log
  // panel's Alignment section (the one-row direction, 2026-08-06).
  const declareToolbarStats = alignmentStats(
    runRows,
    active?.tooth ?? null,
    active?.declared_variant ?? null,
    previewFigures,
  );
  // THE FORK'S ONE PRECONDITION: a done run whose verdicts cover every site (the
  // BFF's own 422 for the decision route). Adjust's reachability is deliberately NOT
  // the gate — a refused run opens Adjust while offering nothing to decide about.
  //
  // It reads LIBRARY, not Deliver (client 2026-08-01). That was exactly Deliver's
  // reachability until the construction library became a page of its own; Deliver now
  // also needs a part picked TWO PAGES LATER, so gating the fork on it made the whole
  // move-forward block vanish from this stage until work that happens after it.
  // Library's reachability is the condition Deliver used to hold alone, which is the
  // one this fork always meant.
  const forkOpen = isReachable("library", facts);
  const summary = attestationSummary(detail.sites);
  const decided: AdjustDecisionView | null = detail.session.adjust_decision;
  // THE RUN'S PROGRESS SURFACE (5c): in flight client-side, or persisted as
  // queued|running (another tab/operator fired it — AM-3's states render either way)
  const runInFlight =
    runPhase === "firing" ||
    facts.runState === "queued" ||
    facts.runState === "running";
  const runRefusal =
    facts.runState === "refused"
      ? (detail.session.run_refusal ??
        "The run was refused — the worker recorded no words.")
      : null;
  return (
    // Two regions for the workbench grid (display: contents on the root): the WORK
    // column carries system/queue/variants; the STAGE is the three panes' — they
    // are the SUBJECT here (client 2026-07-27: "those 3 panels need to be bigger"),
    // ≥55% of the stage height guaranteed by construction (see styles.css's
    // --split arithmetic), while the arch shrinks to a collapsible context strip.
    <div data-role="declare-stage" className="stage-contents">
      <div className="workbench__work workbench__work--footered">
        {/* THE SCROLLING BODY. Everything above the fork scrolls; the fork itself is a
            SIBLING of this box, not a descendant (client 2026-07-29: "Skip adjustment
            and Adjust the fit buttons should always show, there should not be a need to
            scroll down"). A previous attempt made the fork `position: sticky` inside
            this column, which cannot work: a sticky element is bounded by its own
            containing block, so once the block holding it sat entirely below the fold
            the buttons were simply gone. Taking the fork OUT of the scroll area is the
            only version that is true at every scroll position. */}
        <div className="workbench__work-scroll">
        <SiteQueue
          detail={detail}
          activeTooth={activeTooth}
          runRows={runRows}
          onSelectSite={onSelectSite}
        />
        {saving !== "idle" && (
          <div data-role="declare-saving" className="busy-state" role="status">
            <span className="busy-state__spinner" aria-hidden="true" />
            <span>{saving === "system" ? "Switching system…" : "Declaring variant…"}</span>
          </div>
        )}
        {error !== null && (
          <div data-role="declare-error" role="alert" className="panel__error">
            {error}
          </div>
        )}
        {/* THE RUN FOOTER (5c, plan §1.2 compute-early): the auto-fired run's
            progress in honest words — a refusal renders VERBATIM with the
            explicit retry (like an errored preview slot, it never auto-refires). */}
        {runInFlight ? (
          <div data-role="run-progress" className="busy-state" role="status">
            <span className="busy-state__spinner" aria-hidden="true" />
            <span>
              Aligning {facts.siteTotal} site{facts.siteTotal === 1 ? "" : "s"} —
              30–60 s; the case stays open and the panes stay live.
            </span>
          </div>
        ) : runRefusal !== null ? (
          <div data-role="run-refused" role="alert" className="run-refusal">
            <strong className="run-refusal__title">The run was refused.</strong>
            <p className="run-refusal__detail">{runRefusal}</p>
            <p className="run-refusal__next">
              <button
                type="button"
                data-role="run-retry"
                className="button button--ghost button--small"
                onClick={onRetryRun}
              >
                Run again
              </button>
            </p>
          </div>
        ) : runError !== null ? (
          <div data-role="run-error" role="alert" className="run-refusal">
            <strong className="run-refusal__title">The run did not reach an outcome.</strong>
            <p className="run-refusal__detail">{runError}</p>
            <p className="run-refusal__next">
              <button
                type="button"
                data-role="run-retry"
                className="button button--ghost button--small"
                onClick={onRetryRun}
              >
                Try the run again
              </button>
            </p>
          </div>
        ) : null}
        {/* THE MOMENT OF MOVING FORWARD (client 2026-07-27 #2 + #3). Two things
            happen here that the single Continue never did:

            1. THE SET IS FACED. Once every site is attested the summary states, one
               line per site, what each tick actually stood on — tooth, declared cap,
               and the seat facts the preview produced. Short of that, the sites
               still owed are NAMED (the blockedReason doctrine).
            2. THE FORK IS EXPLICIT. "Skip adjustments — go to the construction
               library" and "Adjust
               the fits" replace one button that silently chose for the operator.
               Each RECORDS the decision (it rides into the evidence bundle) and then
               navigates. Reachability is untouched: skipping never closes Adjust. */}
        </div>

        {/* THE FORK, IN THE COLUMN'S OWN FOOT (comp, read directly 2026-08-02: its
            sticky footer pins the stage nav at the bottom of the queue column —
            "review every site first · 0/1" over "run first" — and the full width
            under the panes stays with the declaration controls). The set-faced
            summary and the consequence sentence ride with the doors they inform. */}
          <div
            data-role="declare-advance"
            className="workbench__work-footer panel__actions panel__actions--advance"
          >
            {/* THE RE-RUN ON ALIGNMENT (client 2026-08-09) — offered whenever a
                run's rows exist, blocked fork or not: the automation may simply
                be asked to try again, and §10-AD re-applies the operator's
                evidence after it. */}
            {onRerunAlignment !== null && runRows.length > 0 && (
              <button
                type="button"
                data-role="rerun-alignment"
                className="button button--ghost button--small"
                disabled={
                  runPhase === "firing" || forkSaving !== "idle" ||
                  rerunBlockedReason !== null
                }
                title={
                  rerunBlockedReason ??
                  "Fire the full alignment again — your marks, pairs and " +
                    "best fits re-apply after the automation"
                }
                onClick={onRerunAlignment}
              >
                {runPhase === "firing" ? "Re-running…" : "Re-run the alignment"}
              </button>
            )}
            {forkOpen ? (
              <>
                <ul data-role="attestation-summary" className="attestation-summary">
                  {summary.map((line) => (
                    <li
                      key={line.tooth}
                      data-role="attestation-line"
                      data-tooth={line.tooth}
                      data-attested={line.attested}
                      className={
                        line.attested
                          ? "attestation-summary__line"
                          : "attestation-summary__line attestation-summary__line--owed"
                      }
                    >
                      {line.words}
                    </li>
                  ))}
                </ul>
                <p data-role="skip-consequence" className="panel__hint">
                  {skipConsequenceWords(facts.siteFlagged)}
                </p>
                <div className="declare-fork">
                  <button
                    type="button"
                    data-role="fork-skip"
                    className={`button button--small ${
                      facts.siteFlagged > 0 ? "button--secondary" : "button--primary"
                    }`}
                    disabled={forkSaving !== "idle"}
                    onClick={onSkipAdjustments}
                  >
                    Skip adjustments — go to the construction library
                  </button>
                  <button
                    type="button"
                    data-role="fork-adjust"
                    className={`button button--small ${
                      facts.siteFlagged > 0 ? "button--primary" : "button--secondary"
                    }`}
                    disabled={forkSaving !== "idle"}
                    onClick={onAdjustFits}
                  >
                    Adjust the fits
                  </button>
                </div>
                {decided !== null && (
                  <p data-role="fork-recorded" className="panel__hint">
                    Recorded: {decided.decision === "skip"
                      ? "adjustments skipped"
                      : "adjustments taken up"} · {recordedAtWords(decided.at)} — rides
                    into the evidence; a different choice here replaces it.
                  </p>
                )}
                {forkError !== null && (
                  <div data-role="fork-error" role="alert" className="panel__error">
                    {forkError}
                  </div>
                )}
              </>
            ) : (
              <>
                <span
                  data-role="fork-skip"
                  aria-disabled="true"
                  className="button button--small button--secondary button--blocked"
                >
                  {/* the reason for the page this fork LEADS TO. It quoted Deliver's,
                      which since the library landed can read "pick a construction part
                      in the library first" — advice about a page two stages on, offered
                      as the reason this door is shut. */}
                  Skip adjustments — {blockedReason("library", facts)}
                </span>
                <span
                  data-role="fork-adjust"
                  aria-disabled="true"
                  className="button button--small button--secondary button--blocked"
                >
                  Adjust the fits — {blockedReason("deliver", facts)}
                </span>
              </>
            )}
          </div>
      </div>
      <div className="workbench__stage workbench__stage--split">
        {/* THE ARCH IS A DIALOG NOW, not a standing strip (client 2026-07-30: "small
            panels, the view is cut off ... maybe the arch context view can just be a
            modal"). The always-open strip cost the panes a third of the stage and
            pushed the union pane below the fold — orientation was taxing the very
            surface it existed to orient. As a dialog the arch costs one click when
            wanted and zero pixels when not, and the WebGL viewer only MOUNTS while
            open, which is one fewer live context the three panes compete with. */}
        {/* THE STRIP CARRIES THE SITE NOW, not just the arch opener (gaps
            `workspace-toolbar-site-chip` + `alignment-metrics-strip`). The chip is
            the SERVER's rung and the numbers are the run's own rows — the same rows
            the queue's sentences read — so this surface adds a location, never a
            claim. The presets DO reach the three pane cameras (useSitePaneScene's
            frame construction), and whether the off-axis two can is a fact about the
            preview: `viewPresetsAvailable` is the container's answer, reported up out
            of DeclarePanes, because a preset that cannot reach a camera is a control
            that lies. */}
        <WorkspaceToolbar
          tooth={active?.tooth ?? null}
          systemModel={detail.system.effective_model}
          status={active?.status ?? null}
          stats={declareToolbarStats}
          viewPreset={viewPreset}
          onSelectView={onSelectView}
          viewPresetsAvailable={viewPresetsAvailable}
          zoomLevel={zoomLevel}
          onZoom={onZoom}
          linked={linked}
          onToggleLinked={onToggleLinked}
          cautionSlot={
            cautionWords.length > 0 ? (
              /* THE CAUTION CHIP (§10-AN slice C): "reworked since the run" +
                 a rescan-grade capture verdict, moved off the row (the demo's own
                 shortening precedent, applied a second time — see domain/adjust's
                 pairCautions doc). Renders ONLY where there is something to say. */
              <button
                type="button"
                data-role="declare-caution-chip"
                className="chip chip--exception caution-chip"
                onClick={onOpenCautions}
              >
                ⚠ {cautionWords.length === 1 ? "1 caution" : `${cautionWords.length} cautions`}
              </button>
            ) : null
          }
          /* THE PROVENANCE POPOVER ends the strip (comp: its toolbar closes on
             "▸ budget & log"). `detail` is the refresh key: CaseShell replaces it
             wholesale only when an act lands, so an open popover re-asks exactly
             when there is something new. The SAME stats feed its Alignment
             section — the strip's former figures, one click away (2026-08-06). */
          endSlot={
            <WorkspaceInsight
              caseId={detail.case.id}
              tooth={active?.tooth ?? null}
              refreshKey={detail}
              stats={declareToolbarStats}
            />
          }
        >
          <button
            type="button"
            data-role="arch-open"
            className="button button--secondary button--small"
            onClick={() => setArchOpen(true)}
            /* Condensed 2026-08-05 (client, live-testing: "condense this buttons
               in adjustments tab it takes a lot of space") — the visible label
               drops "— the whole scan"; the title keeps the full phrase so the
               control's purpose is still one hover away. */
            title="Arch context — the whole scan"
          >
            ⊞ Arch context
          </button>
        </WorkspaceToolbar>
        {panesSlot}
        {/* ONE CONTROLS ROW, NOT TWO CARD DECKS (client 2026-08-02: "There is
            multiple scrolling sections here which is really weird, we need to be more
            cohesive and organized"). The drawer held two full panels — system cards
            and a variant card grid — which is what pushed the page into its second
            scroll. Both pickers are selects on one slim row now; the panes above get
            the pixels back, and the drawer never has enough content left to scroll. */}
        <div className="workspace-drawer workspace-drawer--declare">
          <div data-role="declare-controls" className="declare-controls">
            <SystemSelect detail={detail} onAskSwitch={onAskSwitch} />
            <VariantChips
              active={active}
              shelves={shelves}
              onDeclare={onDeclare}
              onOpenArchive={onOpenArchive}
            />
          </div>
          {pendingSwitch !== null && (
            <SwitchConfirm
              detail={detail}
              pendingSwitch={pendingSwitch}
              onConfirm={onConfirmSwitch}
              onCancel={onCancelSwitch}
            />
          )}
        </div>
      </div>
      {archOpen && (
        <div
          data-role="arch-backdrop"
          className="decode-dialog-backdrop"
          onClick={() => setArchOpen(false)}
        >
          <section
            ref={archDialogRef}
            data-role="arch-dialog"
            className="decode-dialog decode-dialog--stage"
            role="dialog"
            aria-modal="true"
            aria-labelledby="arch-dialog-heading"
            tabIndex={-1}
            onClick={(event) => event.stopPropagation()}
          >
            <header className="decode-dialog__header">
              <h2 id="arch-dialog-heading" className="decode-dialog__title">
                Arch context — the whole scan with its sites
              </h2>
              {/* data-autofocus, not the first-focusable fallback: MainStage's own
                  view-preset buttons render after this one in the DOM, and a body
                  that reorders them must not silently move the landing spot. */}
              <button
                type="button"
                data-role="arch-close"
                data-autofocus=""
                className="button button--ghost button--small"
                onClick={() => setArchOpen(false)}
              >
                Close
              </button>
            </header>
            <div className="decode-dialog__body decode-dialog__body--stage">
              <MainStage
                caseId={detail.case.id}
                scanFilename={detail.case.scan_filename}
                sites={detail.sites}
                activeTooth={active?.tooth ?? null}
                jaw={detail.choices.effective_jaw.value}
              />
            </div>
          </section>
        </div>
      )}
      {/* THE SUPERSEDED SHELF, OUT OF THE DRAWER'S FLOW (client 2026-08-09: "it
          shrinks the panels — the panels need to be always the main center of
          attention and size should not change").

          It was a `<details>` fold inside the drawer, and the drawer is `flex: 0 1
          auto` under `max-height: min(238px, 27vh)` — so its height tracked its own
          content and every toggle traded height with the panes above it. The obvious
          fix, pinning the drawer to a fixed band, is WRONG here: a constant band must
          be sized for the drawer's tallest state, so it would shrink the panes
          permanently to buy stability — the opposite of the ask. The chips leave the
          flow instead. The drawer keeps one control whose size never changes, the
          panes keep every pixel they have, and the shelf opens in the dialog idiom
          this surface already uses four times over. */}
      {archiveOpen && shelves.superseded.length > 0 && (
        <div
          data-role="superseded-backdrop"
          className="decode-dialog-backdrop"
          onClick={onCloseArchive}
        >
          <section
            ref={archiveDialogRef}
            data-role="superseded-dialog"
            className="decode-dialog decode-dialog--narrow"
            role="dialog"
            aria-modal="true"
            aria-labelledby="superseded-dialog-heading"
            tabIndex={-1}
            onClick={(event) => event.stopPropagation()}
          >
            <header className="decode-dialog__header">
              <div>
                <h2 id="superseded-dialog-heading" className="decode-dialog__title">
                  Superseded shelf — {shelves.superseded.length} archived part
                  {shelves.superseded.length === 1 ? "" : "s"}
                </h2>
                <p className="decode-dialog__subject">
                  Kept apart from the current shelf, never mixed into it.
                </p>
              </div>
              <button
                type="button"
                data-role="superseded-close"
                data-autofocus=""
                className="button button--ghost button--small"
                onClick={onCloseArchive}
              >
                Close
              </button>
            </header>
            <div className="decode-dialog__body">
              {/* Declarable from here: this is a shelf, not a read-only list. The
                  chip's own act is unchanged — it closes the dialog after, so the
                  operator lands back on the panes with the declaration made. */}
              <div className="decode-variant-list">
                {shelves.superseded.map((card) => (
                  <VariantChip
                    key={card.id}
                    card={card}
                    declared={active?.declared_variant === card.id}
                    archived
                    onDeclare={(variantId) => {
                      onDeclare(variantId);
                      onCloseArchive();
                    }}
                  />
                ))}
              </div>
            </div>
          </section>
        </div>
      )}
      {/* THE CAUTION MODAL (§10-AN slice C, client 2026-08-06: "any warnings or
          things of the sort need to come in as modals"). Same decode-dialog chrome
          as every other dialog on this surface — scrim, role="dialog", escape +
          focus trap — listing the sentences VERBATIM, in the same words
          `siteStateSentence`/`worstRescanMessage` already speak elsewhere. */}
      {cautionsOpen && (
        <div
          data-role="declare-cautions-backdrop"
          className="decode-dialog-backdrop"
          onClick={onCloseCautions}
        >
          <section
            ref={cautionsDialogRef}
            data-role="declare-cautions-dialog"
            className="decode-dialog decode-dialog--narrow"
            role="dialog"
            aria-modal="true"
            aria-labelledby="declare-cautions-heading"
            tabIndex={-1}
            onClick={(event) => event.stopPropagation()}
          >
            <header className="decode-dialog__header">
              <div>
                <h2 id="declare-cautions-heading" className="decode-dialog__title">
                  Tooth {active?.tooth ?? "—"} — cautions
                </h2>
                <p className="decode-dialog__subject">
                  The server's own words. Nothing here is a summary of them.
                </p>
              </div>
              <button
                type="button"
                data-role="declare-cautions-close"
                data-autofocus=""
                className="button button--ghost button--small"
                onClick={onCloseCautions}
              >
                Close
              </button>
            </header>
            <div className="decode-dialog__body">
              <ul data-role="declare-caution-list" className="adjust-queue__reasons">
                {cautionWords.map((words) => (
                  <li key={words} className="adjust-queue__reason">
                    {words}
                  </li>
                ))}
              </ul>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

export interface DeclareStageProps {
  readonly detail: CaseSessionDetail;
  /** The shell owns the payload; every action's response replaces it whole. */
  readonly onDetail: (next: CaseSessionDetail) => void;
}

/** The container: active-site state, the worded switch ceremony, the two PUTs,
 * and the run's auto-fire (5c). */
export function DeclareStage({ detail, onDetail }: DeclareStageProps) {
  const caseId = detail.case.id;
  const mountedRef = useRef(true);
  const [activeTooth, setActiveTooth] = useState<number | null>(null);
  const [pendingSwitch, setPendingSwitch] = useState<string | null>(null);
  const [saving, setSaving] = useState<DeclareSaving>("idle");
  const [error, setError] = useState<string | null>(null);
  const [runPhase, setRunPhase] = useState<RunPhase>("idle");
  const [runError, setRunError] = useState<string | null>(null);
  const [forkSaving, setForkSaving] = useState<ForkSaving>("idle");
  const [forkError, setForkError] = useState<string | null>(null);
  const [runRows, setRunRows] = useState<ReadonlyArray<Record<string, unknown>>>([]);
  // THE NAMED VIEWPOINT (gap `named-view-presets`), held by the STAGE so one click
  // moves all three panes — a per-pane preset would just be three orbits again.
  const [viewPreset, setViewPreset] = useState<ViewPresetId>("occlusal");
  /* Every preset click re-frames, re-selection included: a named viewpoint the
     operator cannot RETURN to after orbiting away is not a viewpoint (design review
     2026-07-31). */
  const [viewPresetNonce, setViewPresetNonce] = useState(0);
  /* THE SHARED ZOOM COUNTER (client 2026-08-02). Held HERE, above both the toolbar and
     the panes, because it is one number for the workspace — see WorkspaceToolbarProps.
     Unbounded on purpose: the band lives in viewer/zoom.ts, where the near/far planes it
     protects are, and `canZoom` stops the button before the counter runs away. */
  const [zoomLevel, setZoomLevel] = useState(0);
  /* THE LINK STATE, same home as the zoom for the same reason: the toolbar's toggle
     and the panes' OrbitLinkGroup both read one value. Opens LINKED — the shared
     policy (domain/workspace, client 2026-08-04). */
  const [linked, setLinked] = useState(PANES_OPEN_LINKED);
  const handleToggleLinked = useCallback(() => setLinked((now) => !now), []);
  // THE CAUTION MODAL (§10-AN slice C) — held here like `pendingSwitch`, so the View
  // stays "pure props → markup" and a static render can pin it open via a prop.
  const [cautionsOpen, setCautionsOpen] = useState(false);
  // The archive shelf's dialog (client 2026-08-09) — held here for the same reason.
  const [archiveOpen, setArchiveOpen] = useState(false);
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
  /* WHAT THE PREVIEW PUBLISHED, held here because two things ABOVE the panes need it:
     the off-axis presets need to know a seated pose exists (AdjustStage has always
     done this — `payload?.pose != null` — and this stage passed nothing at all, so the
     view's default enabled them against no clock reference), and the ALIGNMENT strip
     printed "—" for the very RMS/p90 the union pane below was displaying. `setState`
     is a stable identity, so DeclarePanes' report effect does not re-subscribe. */
  const [previewFigures, setPreviewFigures] = useState<PreviewFigures | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // THE QUEUE ROWS' NUMBER, AND ONLY FROM THE RUN. Declare stays open after the run
  // lands (the fork lives here), so its rows can carry the measured deviation — but
  // only the run's own verdict rows may supply it, exactly as Adjust reads them
  // (AdjustStage's fetchRun effect). Anything short of a DONE run has no rows to
  // read, and the rows then say "no run has measured this fit yet" rather than
  // printing a dash a reader takes for a zero. The endpoint 404s while no current
  // run exists — a refusal is emptiness here, never an error to raise at the
  // operator, because the run's own footer already states what happened.
  useEffect(() => {
    if (detail.session.run_state !== "done") {
      setRunRows([]);
      return;
    }
    void fetchRun(caseId).then((result) => {
      if (!mountedRef.current) return;
      setRunRows(result.kind === "ok" ? result.data.sites : []);
    });
  }, [caseId, detail.session.run_state]);

  // THE AUTO-FIRE (plan §1.2 compute-early; the automation directive): when the
  // detail shows choices complete + every site ready + no current run, POST once.
  // Facts-keyed like detect and the previews (runKeyFor/shouldAutoRun): the fired
  // ref is marked BEFORE the async settles so a doubled effect run cannot POST a
  // 30–60 s job twice, and a refused run does NOT re-fire — retry is the
  // operator's explicit act in the footer.
  const runKey = runKeyFor(detail);
  const runFiredRef = useRef<string | null>(null);
  const fireRun = useCallback(
    (firedKey: string) => {
      runFiredRef.current = firedKey;
      setRunPhase("firing");
      void postRun(caseId).then((result) => {
        if (!mountedRef.current) return;
        setRunPhase("idle");
        if (result.kind === "ok") {
          setRunError(null);
          // verdicts landed SERVER-side; the response is the whole new truth
          onDetail(result.data);
        } else {
          // transport/409/422 — the run never reached a persisted outcome; the
          // words render with the explicit retry
          setRunError(result.detail);
        }
      });
    },
    [caseId, onDetail],
  );
  useEffect(() => {
    if (runKey !== null && shouldAutoRun({ key: runKey, firedKey: runFiredRef.current })) {
      fireRun(runKey);
    }
  }, [runKey, fireRun]);

  const handleRetryRun = useCallback(() => {
    // a refused run has no key (run_state past "none"): mint a one-off fired key
    // so the explicit act always fires exactly once
    fireRun(runKey ?? `retry-${Date.now()}`);
  }, [runKey, fireRun]);

  /** THE FORK'S ONE HANDLER (client 2026-07-27 #3): record the decision, THEN
   * navigate. Record-then-move, deliberately — a decision that never landed must not
   * leave the operator on the next stage believing it did, so a refusal keeps them
   * here with the BFF's words. The response is the whole new detail (optimism OFF),
   * and reachability is untouched either way: this is evidence, never a gate. */
  const fireFork = useCallback(
    (decision: "skip" | "adjust", to: string) => {
      setForkSaving(decision);
      void postAdjustDecision(caseId, decision).then((result) => {
        if (!mountedRef.current) return;
        setForkSaving("idle");
        if (result.kind === "ok") {
          setForkError(null);
          onDetail(result.data);
          navigate(to);
        } else {
          setForkError(result.detail);
        }
      });
    },
    [caseId, onDetail, navigate],
  );

  const fireSystem = useCallback(
    (model: string) => {
      setSaving("system");
      void putSystem(caseId, model).then((result) => {
        if (!mountedRef.current) return;
        setSaving("idle");
        setPendingSwitch(null);
        if (result.kind === "ok") {
          setError(null);
          onDetail(result.data);
        } else {
          setError(result.detail);
        }
      });
    },
    [caseId, onDetail],
  );

  /** The visible-reset doctrine, precisely: a switch that would DESTROY declarations
   * asks in words first; one that resets nothing (nothing declared yet, or pinning
   * the already-effective system as an explicit act) PUTs directly — a confirmation
   * over zero consequences would be the checkbox-over-nothing AM-8 forbids. */
  const handleAskSwitch = useCallback(
    (model: string) => {
      const destroys =
        model !== detail.system.effective_model && resetCount(detail) > 0;
      if (destroys) {
        setPendingSwitch(model);
      } else {
        fireSystem(model);
      }
    },
    [detail, fireSystem],
  );

  const handleConfirmSwitch = useCallback(() => {
    if (pendingSwitch !== null) fireSystem(pendingSwitch);
  }, [pendingSwitch, fireSystem]);

  const handleDeclare = useCallback(
    (variantId: string) => {
      const active = activeSiteFrom(detail.sites, activeTooth);
      if (active === null) return; // no sites — the cards are not rendered anyway
      setSaving("declaration");
      void putDeclaration(caseId, active.tooth, variantId).then((result) => {
        if (!mountedRef.current) return;
        setSaving("idle");
        if (result.kind === "ok") {
          setError(null);
          onDetail(result.data);
        } else {
          setError(result.detail);
        }
      });
    },
    [caseId, detail, activeTooth, onDetail],
  );

  return (
    <DeclareStageView
      viewPreset={viewPreset}
      onSelectView={handleSelectView}
      viewPresetsAvailable={previewFigures?.poseAvailable ?? false}
      previewFigures={previewFigures}
      detail={detail}
      activeTooth={activeTooth}
      pendingSwitch={pendingSwitch}
      saving={saving}
      error={error}
      runRows={runRows}
      runPhase={runPhase}
      runError={runError}
      onRetryRun={handleRetryRun}
      forkSaving={forkSaving}
      forkError={forkError}
      onSkipAdjustments={() => fireFork("skip", `/case/${caseId}/library`)}
      onAdjustFits={() => fireFork("adjust", `/case/${caseId}/adjust`)}
      onSelectSite={setActiveTooth}
      onAskSwitch={handleAskSwitch}
      onConfirmSwitch={handleConfirmSwitch}
      onCancelSwitch={() => setPendingSwitch(null)}
      onDeclare={handleDeclare}
      zoomLevel={zoomLevel}
      onZoom={handleZoom}
      linked={linked}
      onToggleLinked={handleToggleLinked}
      cautionsOpen={cautionsOpen}
      onRerunAlignment={() => fireRun(runKey ?? "manual")}
      rerunBlockedReason={
        runKey === null
          ? "the run gate will refuse: every site must be reviewed over the " +
            "panes first — an adjusted site needs its re-review tick"
          : null
      }
      onOpenCautions={() => setCautionsOpen(true)}
      onCloseCautions={() => setCautionsOpen(false)}
      archiveOpen={archiveOpen}
      onOpenArchive={() => setArchiveOpen(true)}
      onCloseArchive={() => setArchiveOpen(false)}
      panesSlot={
        <DeclarePanes
          detail={detail}
          site={activeSiteFrom(detail.sites, activeTooth)}
          onDetail={onDetail}
          viewPreset={viewPreset}
          viewPresetNonce={viewPresetNonce}
          zoomLevel={zoomLevel}
          linked={linked}
          onPreviewFigures={setPreviewFigures}
        />
      }
    />
  );
}
