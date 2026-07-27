# HowTo — the operational handbook

One page: set up, run the demo, run the tests, measure whether a change helped,
validate physically, find things. Every command below is copy-pasteable from the repo root
unless a `cd` says otherwise.

## 1. Setup (one-time)

```bash
# Python worker — pinned to Python 3.9 (the Open3D-0.18-era interpreter on the build
# host; note the pipeline itself is pure numpy/scipy/trimesh — Open3D's registration_icp
# segfaults here, so domain/icp.py is our own trimmed ICP)
cd apps/worker
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"   # or: make install

# Web demo UI
cd ../web && pnpm install
```

## 2. Run the demo

```bash
(cd apps/worker && .venv/bin/python tools/warm_demo.py)  # pre-warm caches once (~10 min)
./scripts/run-demo.sh                                    # from repo root; or: pnpm demo
```

That one script starts the pipeline API (FastAPI, `apps/worker/src/case_prep/server.py`,
port **8000**) and the web UI (port **5173**) together. Two-terminal equivalent:

```bash
cd apps/worker && make serve      # terminal 1 — API  → http://localhost:8000 (/docs for OpenAPI)
cd apps/web    && pnpm dev        # terminal 2 — UI   → http://localhost:5173  ← the demo
```

Presenter script with click-by-click talking points: [`RUN-DEMO.md`](RUN-DEMO.md).

**Re-warm after an algorithm change — without losing run history.** Cached results live
per-case under `apps/worker/reports/live-demo/<case_id>/`; the append-only attempt log the
client asked us to keep is `reports/live-demo/run-history.jsonl` (sibling file, not inside
the case dirs). So:

```bash
cd apps/worker
find reports/live-demo -mindepth 1 -maxdepth 1 -type d -exec rm -r {} +   # keeps run-history.jsonl
.venv/bin/python tools/warm_demo.py
# restart the API if it was running — it also caches in memory
```

## 3. Run the tests

```bash
cd apps/worker
make test                                  # full battery: 788 tests, ~30 min
.venv/bin/pytest -m "not slow" -q          # FAST LANE: 619 tests, ~55s — the inner loop
.venv/bin/pytest -q -k rim_seat            # one area, seconds
.venv/bin/pytest --collect-only -q         # fast sanity: lists all 788 without running
```

Web side: `cd apps/web && pnpm test` (vitest) and `pnpm typecheck`.

## 4. Measure whether a change improved the model

`tools/fleet_scoreboard.py` runs **every real case's curated gesture through the
production pipeline** and scores each site on the clinical metrics (rim_agreement,
top_face_p90, rim_off_centre, bore_void_off, id_match, confidence, gate). This is the
regression harness: before/after any algorithm change,

```bash
cd apps/worker
.venv/bin/python tools/fleet_scoreboard.py                      # score + print
.venv/bin/python tools/fleet_scoreboard.py --save baseline      # store a named snapshot
# ...make your change...
.venv/bin/python tools/fleet_scoreboard.py --baseline baseline  # per-site improved/regressed/unchanged
```

Snapshots live in `apps/worker/reports/scoreboard/<name>.json`. Deterministic: same code +
data = same numbers, so any diff is your change, not noise (sub-epsilon deltas are
reported as unchanged).

## 5. Physical validation (the two lab-side loops)

**Printed phantom** — ground truth by construction. Generate the plate, print it, scan
the print, evaluate the shipping pipeline against the designed poses:

```bash
cd apps/worker
PYTHONWARNINGS=ignore .venv/bin/python tools/make_phantom.py            # → reports/phantom/phantom-plate.stl + phantom-ground-truth.json
# print the STL, scan the print, then:
PYTHONWARNINGS=ignore .venv/bin/python tools/evaluate_phantom.py \
    --scan <scanned-phantom.stl> --truth reports/phantom/phantom-ground-truth.json
```

Full print/scan protocol and acceptance criteria: [`engagement/phantom-protocol.md`](engagement/phantom-protocol.md).

**Centre-click FLE study** — a ~10-minute operator session that measures real
centre-click scatter (the σ feeding the confidence bootstrap; currently 0.3 mm, from
border-click evidence — centre-click data is what this study adds):

```bash
cd apps/worker
.venv/bin/python tools/fle_study.py instructions          # prints the click protocol
.venv/bin/python tools/fle_study.py analyze               # fits the distribution (dry-run, print only)
.venv/bin/python tools/fle_study.py analyze --write       # …and appends the dated section to docs/research/fle-calibration.md
```

Protocol: [`engagement/fle-centre-click-protocol.md`](engagement/fle-centre-click-protocol.md).

## 6. Where things live

| What | Where |
|---|---|
| Alignment pipeline (seat → identify → refine → confidence) | `apps/worker/src/case_prep/pipeline/auto_flow.py` |
| Demo API (cases, propose, run, package download) | `apps/worker/src/case_prep/server.py` |
| Web demo UI entry | `apps/web/src/App.tsx` |
| Cap library CAD (canonicalized on ingest) | `apps/worker/data/real/library/caps/<system>/` |
| Doctor scans + curated sites | `apps/worker/data/real/scans/doctor-<case>/` |
| Run artifacts, scoreboard snapshots, phantom outputs | `apps/worker/reports/` |
| Research notes (FLE calibration, algorithm survey/benchmarks, score recalibration) | `docs/research/` |
| Engagement records (findings, protocols, client asks, completion report) | `docs/engagement/` |
