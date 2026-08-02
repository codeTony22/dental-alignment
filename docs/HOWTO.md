# HowTo — the operational handbook

One page: set up, run the apps, run the tests, measure whether a change helped, validate
physically, find things. Every command below is copy-pasteable from the repo root unless a
`cd` says otherwise.

**Two front ends, one of them frozen.** `apps/product` (:5174) + `apps/bff` (:8001) is the
operator product and is where all work lands. `apps/web` (:5173) + `case_prep.server`
(:8000) is the client demo, **frozen at `8125cbf`** and never edited. If you are here to
change something, you want §2. If you are here to present, you want §2b.

The repo map — the five gates, the freeze line, the stage model, the two traps that have
each cost a session — is [`../CLAUDE.md`](../CLAUDE.md). Read it first.

## 1. Setup (one-time)

```bash
# Python worker — pinned to Python 3.9 (the Open3D-0.18-era interpreter on the build
# host; note the pipeline itself is pure numpy/scipy/trimesh — Open3D's registration_icp
# segfaults here, so domain/icp.py is our own trimmed ICP)
cd apps/worker
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"   # or: make install

# All the TypeScript, in one go: apps/web, apps/product, packages/viewer, packages/shared
cd .. && pnpm install

# The BFF installs INTO the worker venv — there is no second Python environment
apps/worker/.venv/bin/pip install -e apps/bff
```

## 2. Run the product app (this is the one you change)

Two servers. Start them from `.claude/launch.json` (`bff`, `product-web`) so the BFF gets
its `--reload` flags, or by hand:

```bash
cd apps/bff && ../worker/.venv/bin/uvicorn bff.main:app --port 8001 --app-dir src \
  --reload --reload-dir src --reload-dir ../worker/src/case_prep/application
```

```bash
cd apps/product && pnpm dev      # → http://localhost:5174
```

Health checks, in order of how much they tell you:

```bash
curl -s localhost:8001/health && curl -s localhost:8001/api/case-sessions | head -c 300
```

**If a request 422s with "Extra inputs are not permitted", suspect the process, not the
code.** A BFF older than the tree answers from the schema it booted with, and that is
indistinguishable from a real refusal. `ps -eo pid,lstart,command | grep "[u]vicorn bff"`
tells you how old it is.

THE FLOW IS FIVE STAGES. The URL carries the stage KEY; the rail shows the client's TITLE,
and they are not the same words:

| URL / key | rail title | opens when |
|---|---|---|
| `intake` | Intake | always |
| `declare` | **Alignment** | the case has sites |
| `adjust` | **Adjustment** | a run exists |
| `library` | **Construction library** | run DONE + every site resolved |
| `deliver` | **Delivery** | those, plus a construction part chosen |

`apps/product/src/domain/flow.ts` is the single home for stage identity, order,
reachability and titles. Demo script: [`engagement/product-runbook.md`](engagement/product-runbook.md).

## 2b. Run the frozen demo (presentations only — never edit it)

```bash
(cd apps/worker && .venv/bin/python tools/warm_demo.py)  # pre-warm caches once (~10 min)
./scripts/run-demo.sh                                    # from repo root; or: pnpm demo
```

That one script starts the pipeline API (FastAPI, `apps/worker/src/case_prep/server.py`,
port **8000**) and the web UI (port **5173**) together. `case_prep.server` may never be
imported outside this demo — an AST test enforces it; the product's API is `apps/bff`.
Two-terminal equivalent:

```bash
cd apps/worker && make serve      # terminal 1 — API  → http://localhost:8000 (/docs for OpenAPI)
cd apps/web    && pnpm dev        # terminal 2 — UI   → http://localhost:5173  ← the demo
```

Presenter script with click-by-click talking points: [`RUN-DEMO.md`](RUN-DEMO.md).

The freeze is enforced, not merely intended — this must print nothing:

```bash
git diff --stat 8125cbf -- apps/web apps/worker/src/case_prep/server.py apps/worker/tools
```

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

FIVE gates, listed with their commands in [`../CLAUDE.md`](../CLAUDE.md). Counts are
deliberately not repeated here: they move every time a test is added, and a number that
disagrees with reality is worse than no number. What the count is FOR is telling "my change
broke collection" apart from "the suite grew" — so read the summary line, do not memorise it.

The worker's inner loop and its lanes:

```bash
cd apps/worker
make test-fast                             # the inner loop: not-slow, parallel
make test-slow                             # the real-mesh lane
make test                                  # BOTH — the certification gate, ~13 min
.venv/bin/pytest -q -k rim_seat            # one area, seconds
```

Nothing ships on `test-fast` alone. Parallelism (`-n auto --dist loadfile`) is already in
the Makefile — do not add it by hand and do not remove it.

Front end:

```bash
npm test --prefix apps/product && npm test --prefix packages/viewer
```

```bash
cd apps/product && ./node_modules/.bin/tsc --noEmit -p tsconfig.app.json
```

**That tsconfig path is not optional.** `apps/product/tsconfig.json` is a references shell
(`"files": []`) and checking it exits 0 having checked nothing — it did exactly that for a
whole session while two wrong-shaped API handlers sat in the tree.

`npm test --prefix apps/web` is the frozen demo's suite: it must stay green and its source
must stay untouched.

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
