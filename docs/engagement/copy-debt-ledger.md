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
| 5 | Remaining application lift (adjust-tool judging) | server.py:1259-2324 | case_prep/application/* | 450 | slice 6 (planned) | demo retirement |
| 6 | Detection + capture assembly (propose orchestration; crowns-frame capture context; centre+radius precedence; per-proposal + curated-site capture blocks) | server.py:733-853 (`_capture_context`, `_capture_block`, `_site_capture_inputs`, `_with_capture`, `_run_sites_capture`, `POST /propose`; 856+ is `_append_run_history`, NOT lifted) | case_prep/application/detection.py | 120 | slice 4 | demo retirement |
| 7 | Pre-run preview: the deviation payload builder + the one-site preview seat | server.py:1038 (`_DEVIATION_ROUND`), 1068-1156 (`_deviation_payload`), 1176-1257 (`_PREVIEW_DIRNAME` + `preview_site_alignment`) | case_prep/application/preview.py | 170 | slice 5b | demo retirement |
| 8 | The full run: explicit-selection gate + run orchestration (everything on: product, QC, confidence, package emission) | server.py:893-916 (`_required_selection`), 933-1011 (`POST /run`) | case_prep/application/run.py | 150 | slice 5c | demo retirement |

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
- Still to record as they are copied (slices 5b-8): explicit-selection 422, unique
  teeth, point caps, ±45°, 15mm, ≤8 pairs + lever arm, diameter bounds, length-3 +
  finiteness on client coordinates.

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

Carried-forward minors (grill of slices 0b/1, 2026-07-26):
- Tie `bff/session.py` RunSession.state to `ports/worker.py` JobState (one test or derive the
  Literal) — due slice 5c. DONE (slice 5c, 2026-07-27): test_worker_port.TestStateTie
  asserts the Literal's args equal the enum's values, both directions.
- This ledger existing satisfies the second minor.
