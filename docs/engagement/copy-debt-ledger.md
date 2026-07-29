# Copy-debt ledger — what the product deliberately duplicates from the frozen demo

The demo (apps/web + case_prep/server.py) is frozen at commit `8125cbf`; the product builds
beside it (plan §3, grill AM-5). Duplication is therefore a DECISION, and this ledger is where
every instance is recorded — an unrecorded copy is drift, a recorded one is debt with a name.
Retirement plan: when the demo is retired, each entry collapses into its product home and the
row moves to Retired.

| # | What | From (frozen) | To (product) | Lines (≈) | Recorded | Retires by |
|---|---|---|---|---|---|---|
| 1 | Case discovery (case table construction: model-name match, first-STL scan pick, jaw-from-filename, doctor-label rules) | server.py:86-154, 374-386 | case_prep/application/cases.py | 150 | slice 1 (`5c7c4b8`) | demo retirement |
| 2 | Catalog reads (library groups, constructions, relief ceiling) as refusal-raising functions | server.py endpoint bodies | case_prep/application/catalog.py | 200 | slice 1 (`5c7c4b8`) | demo retirement |
| 3 | Viewer stack (verifyScene, VerifyViewer, sceneController, partFrame, meshCrop, deviationColormap, siteRouting, anatomyOrientation, palette, scanPositions, Viewer3D) + their 5 test files, plus a 13-line domain/types Vec3 subset | apps/web/src/viewer + domain/types.ts | packages/viewer/src | measured 4,698 / 16 files (as landed 4,771 — divergences below) | slice 3 (`3487c16`) | demo retirement |
| 4 | Server-side validation corpus (catalog membership, explicit-selection 422, relief bounds, point caps, ±45°, 15mm, ≤8 pairs, lever arm, diameter bounds) — copied VERBATIM then EXTENDED with coordinate finiteness | server.py request models | bff request models | 300 | recording STARTED slice 4 (see row 4 record); remainder slices 5a-8 (AM-9) | demo retirement |
| 5 | The adjust tools' judging: the rotation nudge + its gates, align-to-mark, align-to-correspondence, the manual best-fit | server.py:1268-1608 (`_NUDGE_*`, `_read_clock_at`, `_load_rotation_site`, `_certification_gates`, `_judge_rotation`, `_reemit_site`, `_finish_adjustment`, `_adopt_rotation`, `POST /nudge-rotation`), 1611-1742 (`_MARK_MAX_DISTANCE_MM`, `POST /align-to-mark`), 1745-1994 (`_CORRESPONDENCE_MAX_PAIRS`, `_site_click_azimuth`, `POST /align-to-correspondence`), 1997-2244 (`_BEST_FIT_*`, `_pose_move`, `_fit_residual`, `POST /best-fit`). NOT lifted: the `_append_*_history` streams (1290-1312, 1639-1667, 1805-1832, 2054-2082), `_update_run_row` (1337-1375), `confirm-alignment` (2247-2324) | case_prep/application/adjust.py | 520 (as landed; the two-point span is NEW physics beside the copy — see row 5 record) | slice 6 (`716ce65`; the module's own bytes rode into `d1bece6` — see the row 5 record's last note) | demo retirement |
| 6 | Detection + capture assembly (propose orchestration; crowns-frame capture context; centre+radius precedence; per-proposal + curated-site capture blocks) | server.py:733-853 (`_capture_context`, `_capture_block`, `_site_capture_inputs`, `_with_capture`, `_run_sites_capture`, `POST /propose`; 856+ is `_append_run_history`, NOT lifted) | case_prep/application/detection.py | 120 | slice 4 | demo retirement |
| 7 | Pre-run preview: the deviation payload builder + the one-site preview seat | server.py:1038 (`_DEVIATION_ROUND`), 1068-1156 (`_deviation_payload`), 1176-1257 (`_PREVIEW_DIRNAME` + `preview_site_alignment`) | case_prep/application/preview.py | 170 | slice 5b | demo retirement |
| 8 | The full run: explicit-selection gate + run orchestration (everything on: product, QC, confidence, package emission) | server.py:893-916 (`_required_selection`), 933-1011 (`POST /run`) | case_prep/application/run.py | 150 | slice 5c | demo retirement |
| 9 | THE DESIGN SYSTEM (parity slice, client correction 2026-07-27: "we lost the good UI/UX"): the demo stylesheet copied as the product's base, plus the presentational JSX patterns the parity surfaces re-wear (see row 9 record) | apps/web/src/styles.css (3,967 lines) + named components' presentational markup | apps/product/src/styles.css + product components | 1,950 CSS verbatim (+814 product-own below the PRODUCT ADDITIONS marker; file total 2,773) | parity-i/ii/iii + parity fix + the report-modal re-copy (2026-07-28) | demo retirement |

Rules:
- A new copy lands ONLY with a row here, in the same commit.
- Divergence inside a copied region is forbidden in the frozen direction (the demo never
  changes) and recorded in the product direction (note in the row when the product's version
  intentionally departs — e.g. slice 1's frozen dataclass vs the demo's mutable cfg-dict).
- The conformance check for a slice includes: does the diff touch a copied region without a
  ledger update?

Row 3 record (slice 3, 2026-07-27) — trims and divergences, per the rules above:
- TRIMS vs the plan's ~11,700 / ~35 estimate: `librarySelection` (domain) and `meshCache`
  (api) are in that estimate but NO viewer module imports either — verified by grep — so
  neither was copied (librarySelection semantics arrive with Declare, slice 5a, and get
  their own row if copied then). `domain/types.ts` (1,008 lines) trimmed to the ONE name
  the viewer stack imports: `Vec3` (13 lines). The estimate's `VerifyStage`/App wiring was
  always REBUILD-not-copy (plan AM-5).
- `scanPositions.scanPositionsFor` now takes the scan URL from the caller (+4 lines): the
  demo resolved it via its api client's `scanUrlFor`; the package owns no route shape.
- `sceneController`: pure helpers extracted and EXPORTED for the characterization test
  (+69 lines): `fitPaddingFor`, `fitDistanceMm`, `clipPlanesFor`, `featureMarkerRadiusMm`,
  `anyPointerToolActive`, `anatomyViewOrientation`, plus `percentile` and
  `SITE_FIT_PADDING` made public. Formulas verbatim, class methods now call them —
  behavior-preserving, verified by side-by-side read; the copied WebGL surfaces stay
  browser-only and are documented (not mocked) in sceneController.characterization.test.ts.
- `src/env.d.ts` (new, 15 lines) declares the one `import.meta.env` field the kept
  dev-registry guards read; apps/web got it from vite/client.
- NOT debt: the demo's ViewOrientationBar subject toggle was REIMPLEMENTED in
  apps/product/src/components/MainStage.tsx (~40 lines of product chrome), not copied.

Row 4 record (recording started slice 4, 2026-07-27) — what has actually been copied so
far, into `apps/bff/src/bff/resources/case_sessions.py` (`ChoicesIn` + the choices
handler):
- jaw enum: server.py:215 (`JAWS`) + 253-258 (`_known_jaw`), verbatim.
- relief bounds incl. finiteness: server.py:165-167 (`_MAX_GINGIVAL_OFFSET_MM`) +
  260-266 (`_sane_offset`). Divergences: `np.isfinite` → `math.isfinite` (identical
  semantics, the BFF owns no numpy); the field is Optional (a choice not yet made is
  None, never a guessed default — the demo's RunIn always carries one because a run
  needs one; a choices document does not).
- construction-part membership: the rule of server.py:341-344 (`_construction_for`'s
  refusal; 345-346 are its cfg-cache lines, deliberately NOT copied), reached through
  `application.catalog.require_construction` (added slice 4; wording per catalog.py's
  existing refusal) — membership, never a path join.
- NEW, not a copy (the corpus' promised extension): the BFF's 422 handler
  (`bff/main.py validation_refusal`) keeps refusals serializable when the offending
  input is non-finite — FastAPI's default handler 500s echoing NaN. The demo never hits
  this because its NaN checks sit behind fields FastAPI can echo; recorded so nobody
  hunts server.py for its origin.
- Slice 5a additions (2026-07-27): implant-system membership (the demo's
  `_library_for` first check, server.py:287-334's directory-name rule) and variant
  membership by catalog entry id — both reached through `application.catalog`'s
  `require_library_model`/`require_variant` (new functions in the already-recorded
  row-2 lift, same refusal sentences as `_library_for`); the BFF's system/declaration
  routes serve those sentences verbatim. NEW, not a copy: `extra="forbid"` on every
  BFF request model (the demo's FastAPI models silently drop unknown fields; the
  product refuses them — see test_case_sessions' introspection test).
- Slice 6 additions (2026-07-28), into `bff/resources/adjust.py`'s request models:
  the ±45° nudge bound and its sentence (server.py:1268 + 1281-1287), the ≤8 pairs cap
  and its sentence (1768 + 1859-1862), the best-fit diameter band (2012-2017 +
  2043-2051), and the ONE-part-half rule per pair (1794-1798). Divergences: the field
  is `step_deg` (the product's ubiquitous language — the demo's `delta_deg` named a
  quantity, the step names the act), and `np.isfinite` → `math.isfinite` as in row 4's
  first entry. NEW, not a copy — the corpus' promised EXTENSION: length-3 + finiteness
  on EVERY client coordinate (`_finite_triple` over `scan_point`, `scan_point_end`,
  `part_point`), where the demo checked only the marks it happened to receive. The
  15mm mark distance and the 0.5mm lever arm are deliberately NOT re-stated here —
  they need the seated pose and the part, so they live once, in the application lift
  (row 5), and the BFF serves their sentences.
- Still to record as they are copied: explicit-selection 422, unique teeth, point caps
  (the marking UI's, when Intake gets one).

NOTE row (slice 5a, 2026-07-27) — a semantic port, NOT a code copy (recorded so the
conformance check knows the resemblance is deliberate): the BFF's
`PUT /api/case-sessions/{id}/system` reimplements the demo's system-switch semantics
SERVER-side — switching the model drops every site's chosen variant and (in the
product's ladder) regresses its status to `detected`; a same-model PUT changes
nothing. Reference rule: apps/web/src/domain/librarySelection.ts:96-108
(`clearAllReviews` + `withModel` — the equality guard AND the reset lines that are
the ported semantics). No TypeScript was copied: the state lives in the case session
now and the client only displays what the BFF returns (plan AM-4/AM-8); the
transition itself runs through `bff/status.py`. Retires with the demo, alongside
row 3.
Extension (5a fix, 2026-07-27; PORTED slice 5b, 2026-07-27): the demo's COMPANION
rule — a construction, jaw or relief change clears EVERY site's review, because
"they all describe the same shipped part" (librarySelection.ts:10-16;
`withConstruction`/`withJaw`/`withOffsetInput`, 111-138) — now lives server-side at
the named boundary: `put_choices` runs every site through `bff/status.py`'s
`invalidate_preview` (later rungs drop to declared, preview facts clear) exactly
when the replacement differs — the demo's own equality guards, so an identical
re-PUT resets nothing. Declared variants survive, as in the demo. The review tick
itself is the machine's `review_ready`/`withdraw_review` behind body-less
POST/DELETE routes (AM-8's reviewed-over-panels doctrine, two-way like the demo's
checkbox). A semantic port like the rest of this row — no TypeScript copied.

Row 7 record (slice 5b, 2026-07-27) — divergences, per the rules above:
- `_deviation_payload` → `preview.deviation_payload`: field-for-field VERBATIM (the
  copied deviationColormap/pane code renders exactly this dict; pinned by worker
  test_preview.py's key-set assertion). `_DEVIATION_ROUND` rides along at 4.
- NO serve-time cache and NO persistent `preview/` directory: the demo cached per
  (case, tooth, selection, marks) and worked under `OUT/<case>/preview`; the product's
  preview is a pure derivation in a scratch dir that dies inside the call — the BFF
  persists the seat FACTS (previewed rung, seat_method, rim_agreement_mm) into the
  case session and the payload mesh is response-only. Same no-cache posture as row 6's
  detection lift; phase 2 jobs the multi-second derivation (plan §3/AM-3).
- The selection arrives as an explicit `PreviewSelection` derived by the BFF from the
  SESSION (operator acts), not the demo's `RunIn` request body; the demo's
  marked-sites 422s ("not among the marked sites sent" / "no declared cap variant")
  become the BFF preview route's own 422 naming what the session still needs. Marks
  come from the case's curated sites.json AS GIVEN (no marking UI yet).
- `_required_selection` (the explicit-selection gate, 893-916) is deliberately NOT
  copied here — it stays row 5's, lifted when 5c's run needs its exact sentence.
- Row 5's range shrank accordingly (1179-1257 moved here; `_DEVIATION_ROUND` and
  `_deviation_payload` sat outside row 5's stated range and enter the ledger with
  this row).

NOTE row (slice 5b, 2026-07-27) — a REBUILD with named borrowings, NOT a code copy
(recorded so the conformance check knows the resemblance is deliberate): the product's
`apps/product/src/components/DeclarePanes.tsx` reimplements the frozen demo's
VerifyStage pane SEMANTICS against BFF shapes (plan AM-5 named VerifyStage as
rebuild-not-copy from the start): top-of-cap framing per pane, the exact-axis-from-
pose story with the occlusal fallback, the shared up-vector, the union's 0.45 scan
opacity, and — kept verbatim as OPERATOR-FACING WORDS, not code — the busy sentence
("seating this selection on the scan — preview, nothing is being processed…") and the
preview caption shape ("preview — this selection seated now (…); nothing processed
yet"). The ~15-line partFrame framing memo (centre from rimCentre+centroid, radius
rmaxMm*1.6, view [0,0,1], up [1,0,0]) matches VerifyStage.tsx:428-449 numerically —
those constants are the framing DECISION the client accepted on 2026-07-26 and must
not drift between apps. Retires with the demo, alongside rows 3 and 7.

Row 6 record (slice 4, 2026-07-27) — divergences, per the rules above:
- The demo's THREE cache layers are deliberately NOT copied (per-process cfg dict,
  `proposals.json`, `capture.json`): the demo's propose endpoint re-fires per click, the
  product's BFF persists the detection result into the case session — `detect(case)` is a
  pure derivation, cached by its caller or not at all.
- `duration_s`/`cached` dropped from the result: serve-time telemetry, not detection facts.
- `tooth_guess` (proposal → nearest curated site within 5mm inherits its tooth, else
  None) is NEW product logic, not a copy — the demo's proposals carry no tooth; recorded
  here so nobody hunts server.py for its origin.
- Refusals raise `ScanUnreadable` instead of the demo's implicit 500 on an unreadable
  scan; the BFF maps to 422 (the demo direction is unchanged).
- Row 5's range shrank accordingly (capture assembly 741-830 + propose 832-853 moved
  here); the explicit-selection gate stays row 5 at its true lines (893-916).

Row 8 record (slice 5c, 2026-07-27) — divergences, per the rules above:
- `_required_selection` (893-916) → `run._require_selection`: sentence, field naming
  and suggestion hint VERBATIM (the product client renders these words); the demo's
  `HTTPException(422, ...)` becomes `RunRefused` raised — job-shaped callers cannot
  422, so every refusal travels as words on the port's REFUSED state. Row 5 narrowed
  accordingly (the gate leaves it; adjust-tool judging 1259-2324 remains).
- Run orchestration (933-1011) → `run.run_case`: same `run_auto_case` call with
  everything ON (generate_product/render_qc/compute_confidence/emit_package — plan
  §1.2: the worker emits at run time; disclosure gates later). Deliberately NOT
  copied: the serve-time cache + `run.json` reuse (`_run_cache_key`, `_cache` —
  product runs land in immutable run dirs, a re-run is a NEW run_id per AM-1), the
  run-history append, the `selection`/`files_base`/`duration_s` response shaping
  (the BFF owns transport), and the per-response capture blocks (Intake's detect
  owns capture in the product). `proposals=None` for now: the human-vs-machine
  `auto_delta_mm` compare returns with a later slice (the row key stays, reads None).
- `out_dir` is THE CALLER'S run directory — a parameter; application code names no
  reports path (AM-1 immutability is enforced one layer up, in
  `bff/ports/worker.InProcessWorker`, which refuses an existing run dir before any
  physics runs and leaves `refusal.json` as a refused run's whole content).
- Fidelity pinned READ-ONLY: worker test_run.py compares the summary/row/verdict
  key-sets and the package file list against the demo's EXISTING warmed
  `reports/live-demo/neodent-gm/run.json` for the same selection — never by
  re-running the demo endpoint (which would emit into the frozen data plane).
- Crash containment (5c fix, 2026-07-27; no demo counterpart — the demo lets FastAPI
  500 and keeps no run dirs or receipts): an UNEXPECTED exception in the physics is a
  FAILED job state (distinct from REFUSED — a crash is not a verdict), the run dir is
  cleaned to `failure.json` alone (AM-1's honesty half), and the run route WITHDRAWS
  its queued receipt whenever no verdict can land (submit raised, worker FAILED, or
  the landing lost its CAS twice) — an abandoned queued receipt wedged the case with
  no recovery route (the slice-5c verification's refuted claim).

Row 9 record (parity slice, 2026-07-28) — the earlier "reimplement-small, don't copy demo
JSX" constraint was LIFTED for visual chrome by the client's correction; this row is where
that copying is named. All measured by the port script (scratch `port_styles.py`):
- STYLESHEET: apps/web/src/styles.css (3,967 lines, frozen 8125cbf) → the base of
  apps/product/src/styles.css. 1,873 lines KEPT VERBATIM (tokens, reset, shell/header,
  workbench grid, panels, buttons, the whole chip vocabulary that survives — gate/
  confidence/seat/capture/band/relief-clamped/agreement-auto — busy-state, capture-banner,
  results-table + rotation-verdict, agreement, package-files, workflow-rail, viewer3d,
  view-orient (+active/disabled states), library-badge base + suggested/superseded/legacy,
  viewer-controls-hint, toast, verification-panel, decode section/system/variant/archive/
  select/jaw/offset(+ceiling+warning), relief-clamp, run-refusal, decode-stepper,
  verify-panels/panel/HUD/layer/colorbar, decode-ack). 2,095 lines DELETED — the
  demo-only surfaces the product lacks: library button+browser/tabs/cards, case cards,
  seed/patch/mark chips + chip__remove, confirm-table, brush-banner, stale-banner +
  results-block, proposal-list, rotation-dial/nudge, best-fit, guidance-panel,
  flags-alerts, viewer-controls, viewer-legend, part-annotator/feature/correspondence,
  part-preview-chip, app-footer, decode-dialog chrome + decode-info + selection-line +
  review-state + blockers, tooth-chart, pose-transfer, stage-drawer, align-actions,
  fit-points, selection-summary, stage-split/compare-pane, and the demo's media blocks
  (re-scoped versions live in the additions). Everything below the file's PRODUCT
  ADDITIONS marker (561 lines; file total 2,448) is product-own chrome, not a copy.
- DIVERGENCES inside the copied sheet's use: `.viewer3d` background overridden to the
  verify panes' light blue (#d8e8f2) — the product's scene clears light (verify-UI
  directive), the demo's cleared dark; rail steps are LINKS (routes are navigation
  state), so `a.workflow-rail__step` + `--blocked` span rules were added; the demo's
  1180/960px media rules were re-written scoped to surviving selectors only.
- PRESENTATIONAL JSX PATTERNS copied near-verbatim (all against product data/handlers,
  no flow logic): Header markup → pages/Shell.tsx (wordmark/sublabel/context, no library
  button); WorkflowRail markup → components/StageRail.tsx (marker/text/label/detail
  structure + class set); ViewOrientationBar's subject row → components/MainStage.tsx
  (the dark-pill overlay + --active pattern; supersedes row 3's "reimplemented ~40
  lines" note for the toggle's LOOK — the vocabulary/behaviour remain the product's);
  ControlsHint's sentence + chip → MainStage; CaptureChip/CaptureBanner class language
  → IntakeStage; VerifyPanels' HUD/layer/colorbar markup → components/DeclarePanes.tsx
  (parity-ii); results-table/VerificationPanel/ReliefClampNotice class language →
  components/DeliverStage.tsx (parity-iii); SelectionColumn's decode-system/decode-variant/
  decode-jaw/decode-select markup → DeclareStage + IntakeStage; SiteStepper's decode-stepper
  item language → DeclareStage's queue and IntakeStage's site list; RunRefusalNotice's
  title/detail/next structure → DeclareStage, IntakeStage and ErrorBanner; BusyState's
  spinner markup → every busy surface; PackageFileList's title/list/item/link structure →
  DeliverStage's artifacts block (links become buttons — the operator-header gate means an
  artifact is never a bare href). Parity fix (review findings 1/3): ViewOrientationBar's
  DIRECTION row (Front/Left/Right/Top, titles verbatim) → MainStage's pill; VerifyPanels'
  toolbar (link-orbits toggle + "show all three"), per-pane maximize (heading + --maximized
  grid, others UNMOUNT), the two-scale ScaleSelector (SCALE_CHOICES verbatim; the union mesh
  follows the bar through the copied buildScaleColors) and the legend-and-stats fold (with
  the unmeasured swatch) → DeclarePanes; CaptureChip's exact labels ("capture ✓" /
  "capture marginal" / "RESCAN" — the shout is design) → domain/intake.captureChipLabel.
  Retires with the demo, alongside row 3.
- KEPT DELIBERATELY UNWORN (so an unrecorded copy never reads as drift): the copied sheet
  retains rule groups no product surface wears YET; each is held for the surface named or
  else retired with the demo. rotation-dial + rotation-verdict cumulative/source +
  verify-panel__hud--rotate (the adjust/rotate HUD — slice 6); chip--confidence-* (the
  assurance confidence chip when Deliver surfaces pose confidence); relief-clamp NOTICE
  block beyond the worn chip (title/why/reason/sites/numbers/--compact — run-clamp notices
  when runs surface clamps); verification-panel's acceptance-numbers table half (table/
  table-scroll/value/ref/group/header/context/note/note-input/confirm — the product carries
  references inline as results-table__candidates; the table returns if a QC numbers grid
  lands); decode-offset achieved/ceiling/warning family (the achieved-vs-asked readout
  after runs; Intake wears its own relief-ceilings block); toast family (transient errors);
  decode-ack sites-block/title/disclaimer/sites/actions/complete (the demo dialog's fuller
  ack bar; the product's ack is one strip); run-refusal head/next-label/status;
  decode-stepper control/state/item--reviewed (the demo's glyph ladder — replaced by the
  product's chip--status chips); decode-section scope/hint; decode-variant__badges +
  library-badge--superseded/--legacy (the archived fold replaces per-card badges);
  panel__hint--recompute; busy-state__elapsed; results-table__cap-surface; agreement--ok/
  --warn (superseded by Deliver's chip agreement language). Measured by scratch
  dead_css.py: 64 class names as of the parity fix.

Row 9 UPDATE (the client-corrections slice, 2026-07-28) — one re-copy, one deletion,
and the counts re-measured:
- RE-COPIED, VERBATIM, from the frozen sheet (apps/web/src/styles.css 2042-2123): the
  dialog chrome the parity slice had deleted as "demo-only" — `.decode-dialog-backdrop`,
  `.decode-dialog`, `.decode-dialog__header/__title/__subject/__body/__body--column-
  collapsed`. It came back because the client asked for the assurance report IN A MODAL
  (2026-07-27 #5: "The reports can be shown in a modal"), which is exactly the surface
  those rules dress. What stayed deleted, because the product's report has no selection
  column: `__identity`, `__header-right`, `__progress`, `__column`, `__main`, `__top`.
  ONE DIVERGENCE, recorded: `.decode-dialog__body .results-table-scroll` (product-own,
  4 lines) makes the body's table scroll INSIDE the dialog — the demo's body held panes,
  which size themselves; a table does not.
- DELETED (product-own, so no frozen counterpart): `.operator-field`,
  `.operator-field__input`, `.operator-field__input:focus` — the panel they dressed is
  gone with the operator name (client 2026-07-27 #1), and dead product-own CSS is drift,
  not a spare part.
- NEW product-own chrome below the marker, for the corrected Deliver and Declare
  surfaces (not copies — no demo counterpart exists): `.attestation-summary(+__line,
  --owed)`, `.declare-fork`, `.evidence-summary(+__line, --flagged, __site, __words)`,
  `.release-steps`, `.release-step(+--done/--current/--waiting, __marker, __body,
  __title, __detail, __actions)`, `.disclosure-note(+__line)`, `.artifact-group(+__title,
  __meta, __size)`, `.disposition-default`.
- COUNTS re-measured this slice (the parity fix's 1,873/561/2,448 had drifted with the
  panes/arch work as well as this one): 1,950 copied lines above the PRODUCT ADDITIONS
  marker, 814 product-own from the marker to EOF, file total 2,773.

Row 5 record (slice 6, 2026-07-28) — divergences, per the rules above:
- THE PACKAGE IS THE CALLER'S RUN DIRECTORY. The demo worked under `OUT/<case>/package`
  (`_load_rotation_site`); `application/adjust.py` takes `run_dir` as a parameter, like
  `run.run_case`'s `out_dir` — application code names no reports path (AM-1).
- NO `run-history.jsonl`. The four `_append_*_history` writers (server.py:1290-1312,
  1639-1667, 1805-1832, 2054-2082) are serve-time provenance into the demo's data plane
  and are deliberately NOT copied. The product's replayable audit is the site record's
  own append-only `adjustments` list, which now carries an `evidence` block (the
  operator's points and the derived observations) — so the geometry replays from the
  SHIPPED record rather than from a side file.
- NO `_update_run_row` (1337-1375). The demo folded the post-adjustment reading into its
  cached `run.json` + `_cache`; the product's run summary lives in the case session, so
  the reading RETURNS on `AdjustOutcome.clocking`/`.best_fit` and the BFF folds it in
  inside its own CAS mutation.
- NO persisted part ANNOTATION. `_seeded_annotation` (590-598) reads the demo's stored
  operator marks; the product has no annotator yet, so features are the machine's own
  `auto_features` reading — the demo's own auto-seed half, with the override half
  arriving when the annotator does.
- Refusals RAISE in two classes matching the demo's own status split: `AdjustInvalid`
  (the demo's 422 — mark distance, ≤8 pairs, the lever arm, the ±45° step, the diameter
  band) and `AdjustRefused` (the demo's 409 — every gate sentence, verbatim), with
  `AlreadyOptimal` carrying the machine-readable widen fields the demo added at 2183-2185.
- The tools also return the SEATED PANE PAYLOAD (`preview.deviation_payload` over the new
  pose): the product's Adjust stage re-renders the three panes from the pose that just
  passed the gates, where the demo reloaded the shipped STL. One payload builder, so a
  pose read before and after an adjustment is the same instrument on the same scale.
- NOT a copy — NEW physics beside it (plan §5, client ask 2026-07-26): the TWO-POINT
  SPAN (`span_readings`, `direction_delta`, `validate_span`, `MIN_SPAN_MM`,
  `SPAN_RADIAL_TOLERANCE_DEG`, the `midpoint`/`direction` observation kinds and the
  per-observation residual rows). The demo has no counterpart; recorded here so nobody
  hunts server.py for its origin. The existing circular mean is UNCHANGED — a span's
  midpoint observation is the demo's single-point observation computed at the averaged
  click (pinned by test_adjust's agreement test).
- `confirm-alignment` (2247-2324) is deliberately NOT lifted: the product's confirmation
  is the sealed evidence bundle at Deliver (slice 8), not a per-site doctor note.

Row 9 UPDATE (slice 6, 2026-07-28) — one MOVE, no new copying, and the counts
re-measured with the rule stated so they stop drifting:
- MOVED, not copied: the VerifyPanels chrome this row already records (PaneShell,
  the layer HUD, the colorbar + its two scales and folded legend, per-pane maximize,
  the link-orbits toggle) left `components/DeclarePanes.tsx` for the new
  `components/SitePanes.tsx`. Adjust shows the SAME three panes as Declare (plan §4
  Adjust says so in as many words), and a second copy would have been a second
  geometry waiting to disagree. The copied bytes are unchanged; only their home is.
  `DeclarePanes` keeps its exported names and its own half — the preview firing, the
  preview caption, the attestation bar — so this row's subject did not move, just
  its file. Retires with the demo, as before.
- NEW, product-own, NOT a copy: Adjust's chrome (`.adjust-tools(+__tab, --active)`,
  `.adjust-tool(+__row, __readout, __field)`, `.adjust-queue__reasons/__reason/
  __optional`, `.adjust-pairs(+__row, __words)`, `.adjust-pass(+__title, __detail)`,
  `.adjust-outcome(+__detail, __pairs, __pair, __note)`) plus one modifier on a
  copied class, `.decode-stepper__item--optional` — the demo's stepper had no
  "listed but optional" state because it had no stage where reworking a passing site
  was offered. The demo's own adjust chrome (align-actions, fit-points,
  rotation-dial, best-fit) was DELETED by the parity slice as demo-only and was NOT
  brought back: it dressed a dialog's tool strip, and this is a stage.
- COUNTS re-measured, with the RULE named so the next reader gets the same number:
  copied = every line before the PRODUCT ADDITIONS marker block = lines 1-1958
  (1,958); product-own = every line after it = lines 1966-3091 (1,126); file total
  3,091. The earlier "1,950 / 814 / 2,773" counted the copied region WITHOUT the
  file's own 8-line header and predated two later product-own additions; the copied
  region itself has NOT drifted — verified byte-identical against `2e71b7a`.

Carried-forward minors (grill of slices 0b/1, 2026-07-26):
- Tie `bff/session.py` RunSession.state to `ports/worker.py` JobState (one test or derive the
  Literal) — due slice 5c. DONE (slice 5c, 2026-07-27): test_worker_port.TestStateTie
  asserts the Literal's args equal the enum's values, both directions.
- This ledger existing satisfies the second minor.
