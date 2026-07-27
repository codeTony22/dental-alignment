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
| 4 | Server-side validation corpus (catalog membership, explicit-selection 422, relief bounds, point caps, ±45°, 15mm, ≤8 pairs, lever arm, diameter bounds) — copied VERBATIM then EXTENDED with coordinate finiteness | server.py request models | bff request models (slices 5a-8) | 300 | planned (AM-9) | demo retirement |
| 5 | Remaining application lift (explicit-selection gate, adjust-tool judging) | server.py:893-916, 1179-2324 | case_prep/application/* | 700 | slices 5c-6 (planned) | demo retirement |
| 6 | Detection + capture assembly (propose orchestration; crowns-frame capture context; centre+radius precedence; per-proposal + curated-site capture blocks) | server.py:733-857 (`_capture_context`, `_capture_block`, `_site_capture_inputs`, `_with_capture`, `_run_sites_capture`, `POST /propose`) | case_prep/application/detection.py | 120 | slice 4 | demo retirement |

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
- Row 5's range shrank accordingly (capture assembly 741-830 + propose 832-857 moved
  here); the explicit-selection gate stays row 5 at its true lines (893-916).

Carried-forward minors (grill of slices 0b/1, 2026-07-26):
- Tie `bff/session.py` RunSession.state to `ports/worker.py` JobState (one test or derive the
  Literal) — due slice 5c.
- This ledger existing satisfies the second minor.
