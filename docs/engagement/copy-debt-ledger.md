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
| 3 | Viewer stack (verifyScene, VerifyViewer, sceneController, partFrame, meshCrop, deviationColormap, siteRouting, anatomyOrientation, palette, domain/types subset, librarySelection, meshCache, Viewer3D) + tests | apps/web/src/viewer + domain | packages/viewer | 11,700 / ~35 files | slice 3 (planned) | demo retirement |
| 4 | Server-side validation corpus (catalog membership, explicit-selection 422, relief bounds, point caps, ±45°, 15mm, ≤8 pairs, lever arm, diameter bounds) — copied VERBATIM then EXTENDED with coordinate finiteness | server.py request models | bff request models (slices 5a-8) | 300 | planned (AM-9) | demo retirement |
| 5 | Remaining application lift (explicit-selection gate, capture assembly, adjust-tool judging) | server.py:741-830, 1179-2324 | case_prep/application/* | 850 | slices 5c-6 (planned) | demo retirement |

Rules:
- A new copy lands ONLY with a row here, in the same commit.
- Divergence inside a copied region is forbidden in the frozen direction (the demo never
  changes) and recorded in the product direction (note in the row when the product's version
  intentionally departs — e.g. slice 1's frozen dataclass vs the demo's mutable cfg-dict).
- The conformance check for a slice includes: does the diff touch a copied region without a
  ledger update?

Carried-forward minors (grill of slices 0b/1, 2026-07-26):
- Tie `bff/session.py` RunSession.state to `ports/worker.py` JobState (one test or derive the
  Literal) — due slice 5c.
- This ledger existing satisfies the second minor.
