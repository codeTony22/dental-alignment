# HOWTO — run, test, and verify this project

Every command below is copy-pasteable from the **repo root** unless a `cd` says
otherwise. Deeper context lives in `docs/engagement/product-runbook.md` (the demo
script) and `CLAUDE.md` (the gates and their traps).

## 0. Prerequisites (already set up on this machine)

- Node + pnpm for the workspace: `pnpm install` at the root once.
- The Python worker venv at `apps/worker/.venv` (Python 3.9). The BFF has **no
  venv of its own** — it shares the worker's, always.

## 1. Run the PRODUCT app (the real five-stage flow)

Two servers. Start the BFF first:

```bash
cd apps/bff && ../worker/.venv/bin/uvicorn bff.main:app --port 8001 --app-dir src --reload --reload-dir src --reload-dir ../worker/src/case_prep/application
```

Then the web app:

```bash
cd apps/product && pnpm dev
```

Open **http://localhost:5174**. The flow: Worklist → open a case (or drop an STL
on the drop zone) → Intake → Alignment → Adjustment → Construction library →
Delivery. "Reset all cases (demo)" at the Worklist's foot restores every case to
fresh intake; per-case reset lives in the case header.

**"Address already in use"**: something (often an earlier session's server) still
holds the port. Find and stop it, then re-run:

```bash
lsof -nP -iTCP:8001 -sTCP:LISTEN
```

```bash
kill $(lsof -ti :8001 -sTCP:LISTEN)
```

(Same recipe for :5174/:5173/:8000 — change the port number.)

**The stale-server trap** (this has burned four sessions): a BFF started without
`--reload` keeps answering from the code it booted with — a nonsense 422 usually
means the process is older than the code. Check:

```bash
ps -eo pid,lstart,command | grep "uvicorn bff.main" | grep -v grep
```

## 2. Run the FROZEN demo (never edited, its own runbook)

```bash
cd apps/worker && .venv/bin/uvicorn case_prep.server:app --port 8000 --app-dir src
```

```bash
cd apps/web && pnpm dev
```

Open **http://localhost:5173**. Frozen at commit `8125cbf`; this must print
nothing:

```bash
git diff --stat 8125cbf -- apps/web apps/worker/src/case_prep/server.py apps/worker/tools
```

## 3. The five test gates (the shipping certification)

```bash
cd apps/worker && make test
```

```bash
cd apps/bff && ../worker/.venv/bin/pytest -q
```

```bash
npm test --prefix apps/product
```

```bash
npm test --prefix packages/viewer
```

```bash
npm test --prefix apps/web
```

Worker lanes when iterating: `make test-fast` (~30 s, no real meshes) ·
`make test-slow` (real meshes, ~12 min) · `make test` (both — the only lane that
certifies). During a loop, run the narrowest file that can fail
(`.venv/bin/pytest tests/test_adjust.py -q`), and gate once at the end.

**The typecheck trap**: `apps/product/tsconfig.json` is a references shell that
checks nothing. The real check:

```bash
cd apps/product && ./node_modules/.bin/tsc --noEmit -p tsconfig.app.json
```

## 4. Verification across all cases

The demo-readiness gate (every case down the UI's own path vs a known baseline):

```bash
make rehearse
```

The alignment check across all cases (§10-AH): re-runs every landed site from
each seed provenance it has — the record's pair, the operator's re-mark, the
detector's proposal — into scratch dirs, scored by the published DEV metric, and
names which sites have a better seat available. A report; rehearse stays the
gate:

```bash
make verify-fleet
```

Both also work from `apps/worker` directly (`make -C apps/worker ...` is what
the root passthrough calls).

## 5. Where things live

- Run artifacts (immutable, never edit): `apps/worker/reports/product/<case>/runs/<run_id>/`
- Case scans + library: `apps/worker/data/real/` — a browser upload writes exactly
  one thing there: `scans/<folder>/<file>.stl`.
- The plan and its decision record: `docs/engagement/product-app-plan.md` (§10 is
  the running client-decision ledger — read it before picking up UI work).
- The demo script for client calls: `docs/engagement/product-runbook.md`.
