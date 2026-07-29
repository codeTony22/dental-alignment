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
 *   UNDER  — the toolbox: one tool visible, the other three one click away.
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
import { FREE_POINT_COLOR, type VerifyMarker } from "viewer";
import {
  fetchRun,
  fetchSeated,
  postBestFit,
  postFitByPoints,
  postMarkTrench,
  postRotation,
  type AdjustOutcomeView,
  type AdjustResultView,
  type ApiResult,
  type CaseSessionDetail,
  type SitePreviewPayload,
  type SiteView,
} from "../api/client";
import {
  ADJUST_TOOLS,
  DEFAULT_DIAMETER_MM,
  MAX_DIAMETER_MM,
  MIN_DIAMETER_MM,
  ROTATION_STEPS,
  adjustPaneNotices,
  adjustQueue,
  adjustUnionCaption,
  alreadyOptimalFrom,
  applyBlockedReason,
  isComplete,
  needsReconfirm,
  newPairDraft,
  observationWords,
  outcomeWords,
  pairBody,
  pairPrompt,
  pairSlot,
  pairWords,
  queueSummary,
  reworkWords,
  withPick,
  type AdjustQueueEntry,
  type AdjustToolId,
  type AlreadyOptimal,
  type PairDraft,
  type SeatedPhase,
} from "../domain/adjust";
import { SitePanesView, useSitePaneScene, type PaneId } from "./SitePanes";

/** What the surface is waiting on — named, so it never freezes silently. */
export type ToolPhase = "idle" | "working";

export interface AdjustStageViewProps {
  readonly entries: readonly AdjustQueueEntry[];
  readonly activeTooth: number | null;
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
  readonly onStartPair: (span: boolean) => void;
  readonly onRemovePair: (id: string) => void;
  readonly onApplyPairs: () => void;
  /** The panes, already assembled by the container (tests pass a stub). */
  readonly panes: React.ReactNode;
  /** The site's rung, for the re-confirm nudge after an applied tool. */
  readonly activeStatus: string | null;
}

function ToolTabs({
  tool,
  onSelectTool,
}: {
  readonly tool: AdjustToolId;
  readonly onSelectTool: (t: AdjustToolId) => void;
}) {
  return (
    <div data-role="tool-tabs" role="tablist" aria-label="Correction tools"
         className="adjust-tools">
      {ADJUST_TOOLS.map((info) => (
        <button
          key={info.id}
          type="button"
          role="tab"
          data-role="tool-tab"
          data-tool={info.id}
          aria-selected={tool === info.id}
          title={info.oneLiner}
          className={`adjust-tools__tab${
            tool === info.id ? " adjust-tools__tab--active" : ""
          }`}
          onClick={() => onSelectTool(info.id)}
        >
          {info.label}
        </button>
      ))}
    </div>
  );
}

/** The stage's whole surface, pure props → markup — statically testable. */
export function AdjustStageView({
  entries,
  activeTooth,
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
  onApplyPairs,
  panes,
  activeStatus,
}: AdjustStageViewProps) {
  const active = entries.find((e) => e.tooth === activeTooth) ?? null;
  const busy = phase === "working";
  const applyBlocked = applyBlockedReason(drafts);
  const openDraft = drafts.find((d) => !isComplete(d)) ?? null;
  const toolInfo = ADJUST_TOOLS.find((t) => t.id === tool)!;
  const reworkNote = lastOutcome !== null ? reworkWords(lastOutcome) : null;
  return (
    <div data-role="adjust-stage" className="stage-contents">
      <div className="workbench__work">
        <aside data-role="adjust-queue" aria-label="Site queue" className="panel">
          <h3 className="panel__title">Sites</h3>
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
                  }${entry.optional ? " decode-stepper__item--optional" : ""}`}
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
                  {entry.flagged ? (
                    <ul data-role="queue-reasons" className="adjust-queue__reasons">
                      {entry.reasons.length > 0 ? (
                        entry.reasons.map((reason) => (
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
                  ) : (
                    <span data-role="queue-optional" className="adjust-queue__optional">
                      passed its gates — reworking is optional
                    </span>
                  )}
                </button>
              </li>
            ))}
          </ul>
          {entries.length === 0 && (
            <p data-role="adjust-empty" className="panel__hint">
              No aligned sites on this run — there is nothing to rework here.
            </p>
          )}
        </aside>

        <section data-role="adjust-toolbox" aria-label="Correction tools"
                 className="panel">
          <h3 className="panel__title">
            {active !== null ? `Tools — tooth ${active.tooth}` : "Tools"}
          </h3>
          <ToolTabs tool={tool} onSelectTool={onSelectTool} />
          <p data-role="tool-oneliner" className="panel__hint">{toolInfo.oneLiner}</p>

          {active === null ? (
            <p data-role="tool-blocked" className="panel__hint">
              Pick a site in the queue — the tools act on one site's fit.
            </p>
          ) : (
            <div data-role="tool-body" data-tool={tool} className="adjust-tool">
              {tool === "rotation" && (
                <>
                  <p data-role="rotation-residual" className="adjust-tool__readout">
                    {rotationReadout(lastOutcome, cumulativeDeg)}
                  </p>
                  <div className="adjust-tool__row">
                    {ROTATION_STEPS.map((step) => (
                      <button
                        key={step}
                        type="button"
                        data-role="rotation-step"
                        data-step={step}
                        className="button button--secondary button--small"
                        disabled={busy}
                        onClick={() => onRotate(step)}
                      >
                        {step > 0 ? `+${step}°` : `${step}°`}
                      </button>
                    ))}
                    <button
                      type="button"
                      data-role="rotation-reset"
                      className="button button--ghost button--small"
                      disabled={busy}
                      onClick={onResetRotation}
                    >
                      Reset to the certified pose
                    </button>
                  </div>
                </>
              )}

              {tool === "best-fit" && (
                <>
                  <label className="adjust-tool__field" htmlFor="matching-diameter">
                    Matching diameter (mm)
                    <input
                      id="matching-diameter"
                      data-role="diameter-input"
                      type="number"
                      min={MIN_DIAMETER_MM}
                      max={MAX_DIAMETER_MM}
                      step={0.05}
                      value={diameterMm}
                      disabled={busy}
                      onChange={(e) => onChangeDiameter(Number(e.target.value))}
                    />
                  </label>
                  <div className="adjust-tool__row">
                    <button
                      type="button"
                      data-role="best-fit-measure"
                      className="button button--ghost button--small"
                      disabled={busy}
                      onClick={() => onBestFit(false)}
                    >
                      Measure only
                    </button>
                    <button
                      type="button"
                      data-role="best-fit-apply"
                      className="button button--primary button--small"
                      disabled={busy}
                      onClick={() => onBestFit(true)}
                    >
                      Apply best fit
                    </button>
                  </div>
                </>
              )}

              {tool === "mark-trench" && (
                <div className="adjust-tool__row">
                  <button
                    type="button"
                    data-role="arm-trench"
                    aria-pressed={trenchArmed}
                    className={`button button--small ${
                      trenchArmed ? "button--primary" : "button--secondary"
                    }`}
                    disabled={busy}
                    onClick={onArmTrench}
                  >
                    {trenchArmed
                      ? "Armed — click the trench on the scan"
                      : "Mark the trench on the scan"}
                  </button>
                </div>
              )}

              {tool === "fit-by-points" && (
                <>
                  <p data-role="pair-prompt" className="adjust-tool__readout">
                    {pairPrompt(openDraft)}
                  </p>
                  <div className="adjust-tool__row">
                    <button
                      type="button"
                      data-role="start-point-pair"
                      className="button button--secondary button--small"
                      disabled={busy || openDraft !== null}
                      onClick={() => onStartPair(false)}
                    >
                      Add a point pair
                    </button>
                    <button
                      type="button"
                      data-role="start-span-pair"
                      className="button button--secondary button--small"
                      disabled={busy || openDraft !== null}
                      title={
                        "Two clicks spanning one feature — both ends of the trench, or " +
                        "across a hole. The midpoint averages the click noise; the " +
                        "direction is a second reading the server judges on its own."
                      }
                      onClick={() => onStartPair(true)}
                    >
                      Add a SPAN pair (both ends)
                    </button>
                  </div>
                  <ul data-role="pair-list" className="adjust-pairs">
                    {drafts.map((draft, index) => (
                      <li key={draft.id} data-role="pair-row" data-span={draft.span}
                          data-slot={pairSlot(draft)} className="adjust-pairs__row">
                        <span className="adjust-pairs__words">
                          {pairWords(draft, index)}
                        </span>
                        <button
                          type="button"
                          data-role="remove-pair"
                          data-pair={draft.id}
                          className="button button--ghost button--small"
                          disabled={busy}
                          onClick={() => onRemovePair(draft.id)}
                        >
                          Remove
                        </button>
                      </li>
                    ))}
                  </ul>
                  <div className="adjust-tool__row">
                    {applyBlocked === null ? (
                      <button
                        type="button"
                        data-role="apply-pairs"
                        className="button button--primary button--small"
                        disabled={busy}
                        onClick={onApplyPairs}
                      >
                        Apply the fit
                      </button>
                    ) : (
                      <span
                        data-role="apply-pairs"
                        aria-disabled="true"
                        className="button button--secondary button--blocked"
                      >
                        {applyBlocked}
                      </span>
                    )}
                  </div>
                </>
              )}
            </div>
          )}

          {busy && (
            <div data-role="tool-busy" className="busy-state" role="status">
              <span className="busy-state__spinner" aria-hidden="true" />
              <span>
                Judging the proposal — the same gates that judged the automation…
              </span>
            </div>
          )}

          {/* THE PASS THAT WEARS A REFUSAL'S STATUS — rendered green, with the widen.
              (client ask 2026-07-26; the demo shipped this in the refusal's tone and
              had to take it back.) */}
          {pass !== null && (
            <div data-role="best-fit-pass" className="adjust-pass" role="status">
              <strong className="adjust-pass__title">Nothing to correct.</strong>
              <p className="adjust-pass__detail">{pass.message}</p>
              {pass.canWiden && (
                <button
                  type="button"
                  data-role="widen-search"
                  className="button button--ghost button--small"
                  disabled={busy}
                  onClick={() => {
                    onChangeDiameter(pass.suggestedDiameterMm);
                    onBestFit(false);
                  }}
                >
                  Widen to Ø{pass.suggestedDiameterMm.toFixed(2)} mm and look again
                </button>
              )}
            </div>
          )}

          {refusal !== null && (
            <div data-role="tool-refusal" role="alert" className="run-refusal">
              <strong className="run-refusal__title">The adjustment was refused.</strong>
              <p className="run-refusal__detail">{refusal}</p>
              <p className="run-refusal__next">
                Nothing changed — the fit on screen is the one that passed the gates.
              </p>
            </div>
          )}

          {lastOutcome !== null && refusal === null && pass === null && (
            <div data-role="tool-outcome" className="adjust-outcome" role="status">
              <p className="adjust-outcome__detail">{outcomeWords(lastOutcome)}</p>
              {lastOutcome.pairs.length > 0 && (
                <ul data-role="observation-list" className="adjust-outcome__pairs">
                  {lastOutcome.pairs.map((row, i) => (
                    <li key={i} className="adjust-outcome__pair">
                      {observationWords(row)}
                    </li>
                  ))}
                </ul>
              )}
              {lastOutcome.applied && activeStatus !== null &&
                needsReconfirm(activeStatus as never) && (
                  <p data-role="reconfirm-note" className="adjust-outcome__note">
                    This site's fit moved, so its earlier confirmation no longer
                    describes it — confirm it again over the panes before Deliver.
                  </p>
                )}
              {reworkNote !== null && (
                <p data-role="rework-note" className="adjust-outcome__note">
                  {reworkNote}
                </p>
              )}
            </div>
          )}
        </section>
      </div>
      <div className="workbench__stage">{panes}</div>
    </div>
  );
}

/** The rotation dial's read-out: the coded-cutout residual the operator is steering
 * toward, plus where the cumulative rotation stands. Server numbers only. */
function rotationReadout(
  outcome: AdjustOutcomeView | null,
  cumulativeDeg: number | null,
): string {
  const shift = outcome?.clocking?.["notch_shift_deg"];
  const residual =
    typeof shift === "number"
      ? `coded-cutout residual ${shift.toFixed(1)}°`
      : "coded-cutout residual not read yet";
  const cumulative =
    cumulativeDeg !== null
      ? `cumulative ${cumulativeDeg > 0 ? "+" : ""}${cumulativeDeg.toFixed(1)}°`
      : "no operator rotation on this site";
  return `${residual} · ${cumulative}`;
}

export interface AdjustStageProps {
  readonly detail: CaseSessionDetail;
  readonly onDetail: (next: CaseSessionDetail) => void;
}

/** The container: the run's rows, the seated read per site, the four tools' requests,
 * and the picking that feeds fit-by-points and mark-trench. */
export function AdjustStage({ detail, onDetail }: AdjustStageProps) {
  const caseId = detail.case.id;
  const mountedRef = useRef(true);
  const [rows, setRows] = useState<ReadonlyArray<Record<string, unknown>>>([]);
  const [activeTooth, setActiveTooth] = useState<number | null>(null);
  const [tool, setTool] = useState<AdjustToolId>("fit-by-points");
  const [phase, setPhase] = useState<ToolPhase>("idle");
  const [refusal, setRefusal] = useState<string | null>(null);
  const [pass, setPass] = useState<AlreadyOptimal | null>(null);
  const [lastOutcome, setLastOutcome] = useState<AdjustOutcomeView | null>(null);
  const [payload, setPayload] = useState<SitePreviewPayload | null>(null);
  const [seatedPhase, setSeatedPhase] = useState<SeatedPhase>("idle");
  const [seatedError, setSeatedError] = useState<string | null>(null);
  const [diameterMm, setDiameterMm] = useState(DEFAULT_DIAMETER_MM);
  const [trenchArmed, setTrenchArmed] = useState(false);
  const [drafts, setDrafts] = useState<readonly PairDraft[]>([]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // The run's verdict rows — the queue's reasons come from them, verbatim.
  useEffect(() => {
    void fetchRun(caseId).then((result) => {
      if (!mountedRef.current) return;
      setRows(result.kind === "ok" ? result.data.sites : []);
    });
  }, [caseId, detail.session.run_state]);

  const entries = useMemo(() => adjustQueue(detail.sites, rows), [detail.sites, rows]);
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

  // Switching sites clears the half-built work: a draft pair belongs to the site whose
  // panes it was placed over, and carrying it across would be a mark about nothing.
  const handleSelectSite = useCallback((tooth: number) => {
    setActiveTooth(tooth);
    setDrafts([]);
    setTrenchArmed(false);
    setRefusal(null);
    setPass(null);
    setLastOutcome(null);
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
      if (result.data.pane_payload !== null) setPayload(result.data.pane_payload);
      onDetail(result.data.case);
      setDrafts([]);
      setTrenchArmed(false);
    },
    [onDetail],
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
    [caseId, activeTooth, trenchArmed, openDraft, run],
  );

  /** The numbered marks, drawn where they were placed. Memoized by content: the
   * viewer diffs markers by identity, so a fresh array per render would churn the
   * scene graph on every keystroke elsewhere. */
  const markers = useMemo(() => {
    const part: VerifyMarker[] = [];
    const scan: VerifyMarker[] = [];
    drafts.forEach((draft, index) => {
      const label = `${index + 1}`;
      if (draft.partPoint !== null) {
        part.push({
          key: `${draft.id}-part`,
          position: draft.partPoint as [number, number, number],
          color: FREE_POINT_COLOR,
          label,
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
    return { library: part, scan, union: scan } as Partial<
      Record<PaneId, readonly VerifyMarker[]>
    >;
  }, [drafts]);

  const pickHandlers = useMemo(
    () => ({
      library: handlePick("part"),
      scan: handlePick("scan"),
      union: handlePick("scan"),
    }),
    [handlePick],
  );

  const scene = useSitePaneScene(detail, activeSite, payload, {
    markers,
    onPick: pickHandlers,
  });

  const notices = adjustPaneNotices({
    site: activeEntry,
    partMeshKnown: scene.partMeshKnown,
    partError: scene.partError,
    scanError: scene.scanError,
    scanEmpty: scene.scanEmpty,
    seatedPhase,
    seatedError,
  });

  const panes = (
    <SitePanesView
      variantLabel={activeSite?.declared_variant ?? null}
      notices={notices}
      partBusy={scene.partBusy}
      scanBusy={scene.scanBusy}
      scanCaption={scene.scanCaption}
      unionCaption={adjustUnionCaption(payload, lastOutcome)}
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
      linked={scene.linked}
      onToggleLinked={scene.onToggleLinked}
      maximizedId={scene.maximizedId}
      onToggleMaximized={scene.onToggleMaximized}
      scaleId={scene.scaleId}
      onSelectScale={scene.onSelectScale}
    />
  );

  return (
    <AdjustStageView
      entries={entries}
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
      onStartPair={(span) =>
        setDrafts((current) => [
          ...current,
          newPairDraft(`pair-${current.length + 1}-${Date.now()}`, span),
        ])
      }
      onRemovePair={(id) => setDrafts((current) => current.filter((d) => d.id !== id))}
      onApplyPairs={handleApplyPairs}
      panes={panes}
      activeStatus={activeSite?.status ?? null}
    />
  );
}
