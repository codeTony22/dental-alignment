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
  type PreviewFigures,
  type ViewPresetId,
  type WorkspaceStat,
} from "../domain/declare";
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
      <h3 className="panel__title">Site queue</h3>
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

interface VariantSelectProps {
  readonly active: SiteView | null;
  readonly shelves: ReturnType<typeof variantShelves>;
  readonly onDeclare: (variantId: string) => void;
}

/**
 * THE VARIANT DROPDOWN — the client's own words (2026-08-02): "the implant variant
 * selection needs to be drop down". Six cards became one control, and every claim
 * the cards made moved INTO it rather than being dropped:
 *
 *   - each option carries the catalog's Ø × height line, because a bare code is a
 *     guess and the dims are what the operator is actually choosing between;
 *   - the DECLARED variant is the selected option — the server's fact, controlled;
 *   - detection's proposal wears data-role="variant-suggested" and says so in its
 *     text, and vanishes the moment the operator declares (their act supersedes it);
 *   - the superseded shelf is a LABELLED optgroup, kept apart from the current
 *     shelf, never mixed into it — still declarable, still marked archived.
 *
 * The empty option never fires onDeclare: there is no undeclare act on this page,
 * and a change handler that invented one would be a client-side status write.
 */
function VariantSelect({ active, shelves, onDeclare }: VariantSelectProps) {
  const optionFor = (card: (typeof shelves.current)[number]) => (
    <option
      key={card.id}
      value={card.id}
      data-variant={card.id}
      data-role={card.suggested ? "variant-suggested" : undefined}
    >
      {card.label} — {card.dims}
      {card.suggested ? " · suggested" : ""}
    </option>
  );
  return (
    <label className="declare-controls__field declare-controls__field--variant">
      <span className="declare-controls__label">
        {active !== null ? `Variant for tooth ${active.tooth}` : "Variant"}
      </span>
      <select
        data-role="declare-variant"
        className="decode-select"
        value={active?.declared_variant ?? ""}
        disabled={active === null}
        onChange={(event) => {
          if (event.target.value !== "") onDeclare(event.target.value);
        }}
      >
        <option value="">
          {active !== null ? "declare a cap variant…" : "pick a site first"}
        </option>
        {shelves.current.map(optionFor)}
        {shelves.superseded.length > 0 && (
          <optgroup
            data-role="superseded-shelf"
            label={`Superseded shelf — ${shelves.superseded.length} archived part${
              shelves.superseded.length === 1 ? "" : "s"
            }`}
          >
            {shelves.superseded.map(optionFor)}
          </optgroup>
        )}
      </select>
    </label>
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
  /** A stage's own control that belongs on this strip (Declare's arch opener) — so
   *  the stage keeps ONE row of chrome above the panes rather than two. */
  readonly children?: ReactNode;
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
  children,
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
      <span data-role="alignment-strip" className="workspace-toolbar__metrics">
        <span className="workspace-toolbar__metrics-label">ALIGNMENT</span>
        <span
          data-role="toolbar-status"
          data-status={status ?? "none"}
          className="chip chip--status"
        >
          {status ?? "no site selected"}
        </span>
        {stats.map((stat) => (
          <span
            key={stat.id}
            data-role="alignment-stat"
            data-stat={stat.id}
            className="workspace-toolbar__stat"
          >
            <span className="workspace-toolbar__stat-key">{stat.label}</span>
            <span className="workspace-toolbar__stat-value">{stat.value}</span>
          </span>
        ))}
      </span>
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
  /** What the PREVIEW published for the active site, while no run has measured it
   *  (design review 2026-07-31) — see domain/declare.alignmentStats. */
  readonly previewFigures?: PreviewFigures | null;
  /** The three live panes + the review tick (5b) — the container passes the
   * DeclarePanes container; View tests may omit it (the panes have their own). */
  readonly panesSlot?: ReactNode;
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
  previewFigures = null,
  panesSlot,
}: DeclareStageViewProps) {
  const facts = factsFromCaseSession(detail);
  const active = activeSiteFrom(detail.sites, activeTooth);
  /* Local by design: whether the arch dialog is open is presentation, not case state —
     nothing downstream reads it, so it earns no prop. Static tests render it CLOSED,
     which is also the honest default: the panes are the subject of this stage. */
  const [archOpen, setArchOpen] = useState(false);
  // Escape closes the arch-context dialog.
  useDialogEscape(archOpen, () => setArchOpen(false));
  // Per-SITE shelves: the detector's proposal is a fact about the active site, so the
  // same catalog marks a different card as the operator moves down the queue.
  const shelves = variantShelves(detail, active);
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
          stats={alignmentStats(
            runRows,
            active?.tooth ?? null,
            active?.declared_variant ?? null,
            previewFigures,
          )}
          viewPreset={viewPreset}
          onSelectView={onSelectView}
          viewPresetsAvailable={viewPresetsAvailable}
          zoomLevel={zoomLevel}
          onZoom={onZoom}
        >
          <button
            type="button"
            data-role="arch-open"
            className="button button--secondary button--small"
            onClick={() => setArchOpen(true)}
          >
            ⊞ Arch context — the whole scan
          </button>
          {/* THE PROVENANCE POPOVER (gap `deviation-budget-in-workspace`), beside the
              arch opener — the toolbar's OTHER standing control, not a second row of
              chrome. `detail` is passed as the refresh key: CaseShell only replaces it
              wholesale when an act actually lands (onDetail), so an already-open
              popover re-asks exactly when there is something new to show. */}
          <WorkspaceInsight
            caseId={detail.case.id}
            tooth={active?.tooth ?? null}
            refreshKey={detail}
          />
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
            <VariantSelect active={active} shelves={shelves} onDeclare={onDeclare} />
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
        <div className="workspace-advance">
          <div
            data-role="declare-advance"
            className="workbench__work-footer panel__actions panel__actions--advance"
          >
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
      </div>
      {archOpen && (
        <div
          data-role="arch-backdrop"
          className="decode-dialog-backdrop"
          onClick={() => setArchOpen(false)}
        >
          <section
            data-role="arch-dialog"
            className="decode-dialog decode-dialog--stage"
            role="dialog"
            aria-modal="true"
            aria-labelledby="arch-dialog-heading"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="decode-dialog__header">
              <h2 id="arch-dialog-heading" className="decode-dialog__title">
                Arch context — the whole scan with its sites
              </h2>
              <button
                type="button"
                data-role="arch-close"
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
              />
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
      panesSlot={
        <DeclarePanes
          detail={detail}
          site={activeSiteFrom(detail.sites, activeTooth)}
          onDetail={onDetail}
          viewPreset={viewPreset}
          viewPresetNonce={viewPresetNonce}
          zoomLevel={zoomLevel}
          onPreviewFigures={setPreviewFigures}
        />
      }
    />
  );
}
