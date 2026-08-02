# dental-alignment — repo map

Read this before running anything. Every command below is copy-pasteable and correct;
guessing at paths here costs minutes, and guessing at lanes costs half an hour.

## Speed rules (2026-07-28 — written after an hour was burned on one gate)

1. **Run the narrowest thing that can fail.** A fix confined to span physics is answered
   by `tests/test_adjust.py tests/test_server_best_fit.py`, not by 217 real-mesh tests.
   The full battery is a SHIPPING gate, not an inner-loop one — run it once, at the end,
   after the last edit.
2. **Never start a gate while files are still being written.** pytest imports the tree at
   collection: a run started at 21:27 and an edit at 21:33 produce a 24-minute answer to
   a question about code that no longer exists. Finish editing, then gate.
3. **Never start a second copy of a run already in flight.** Check `ps` first. Two copies
   of the same suite on one box are slower than one, not faster.
4. **Parallelism is already in the Makefile** (`-n auto --dist loadfile`). Do not add it
   by hand and do not take it out. If a parallel run fails and you suspect the
   parallelism, `make test-serial` is the tiebreaker — but a test that only passes serially
   has a shared-state bug, and that is the finding, not an excuse to go serial.

## The five gates

```bash
cd apps/worker && make test          # both lanes — the certification gate, ~13 min
cd apps/bff    && ../worker/.venv/bin/pytest -q     # SHARES THE WORKER VENV, it has no own .venv
npm test --prefix apps/product
npm test --prefix packages/viewer
npm test --prefix apps/web           # the FROZEN demo; must stay green and untouched
```

Worker lanes: `make test-fast` (not-slow, ~19 s) · `make test-slow` (real meshes, ~12 min) ·
`make test` (both). Nothing ships on `test-fast` alone.

**Counts, all measured 2026-08-02 at `d84a0f9`** — a floor to compare against, not a target.
They move whenever a test is added; what the number is FOR is telling "my change broke
collection" apart from "the suite grew", so read the summary line rather than trusting this
table. If yours is higher and green, the table is stale — not your branch.

| gate | passing |
|---|---|
| worker `make test` | **1028** |
| worker `make test-fast` / `make test-slow` | 797 / 231 (they partition it exactly) |
| bff | **560** |
| apps/product | **977** |
| packages/viewer | **108** |
| apps/web (frozen) | **789** |

Also `cd apps/worker && make rehearse` — the demo-readiness gate: every case down the UI's
own path against a known baseline.

## The freeze line

The demo app is **frozen at commit `8125cbf`** and is never edited again. This must print
nothing:

```bash
git diff --stat 8125cbf -- apps/web apps/worker/src/case_prep/server.py apps/worker/tools
```

Deliberate demo→product copies get a row in `docs/engagement/copy-debt-ledger.md` **in the
same commit**. An unrecorded copy is drift. A copied region that later DIVERGES gets a note
on its row in the product direction — the stylesheet's is the worked example (row 9).

**Two constants that differ on purpose, and must:** the verify panes' display band is
**11 mm** in `packages/viewer/src/viewer/meshCrop.ts` (the product's viewer) and **9 mm**
in `apps/web/src/viewer/meshCrop.ts` (the demo's frozen copy). Both are correct.
Reconciling them would break the freeze. Note the freeze line covers `apps/web` and says
nothing about `packages/viewer`, which is the product's and is edited freely.

## Architecture

`apps/product` (React, :5174) → `apps/bff` (FastAPI, :8001) → `case_prep.application` →
`case_prep.pipeline` / `domain` / `adapters`.

**The flow is FIVE stages (client direction, 2026-08-01).** The KEYS never changed, so
routes, session fields and every `stage ===` comparison still read the old names; only the
TITLES are the client's:

| key | title | reachable when |
|---|---|---|
| `intake` | Intake | always |
| `declare` | **Alignment** | the case has sites |
| `adjust` | **Adjustment** | a run exists |
| `library` | **Construction library** | run DONE **and** every site resolved |
| `deliver` | **Delivery** | those, **plus** a construction part chosen |

`apps/product/src/domain/flow.ts` is the single home for stage identity, order,
reachability, titles and blocked reasons. The route is the existing `/case/:id/:stage`
(`main.tsx`) — the library stage added no route line.

The plan's §4 and §7 describe the FOUR-stage build as it happened and are left as written;
§10-M is the correction, and where they disagree §10 wins.

**`case_prep.server` may never be imported outside the frozen demo** — an AST test enforces
it. `application/` is the seam: BFF-facing logic is lifted there, not reached for in
`server.py`.

Statuses, verdicts and gates are **derived server-side, never accepted from a client**. The
enforcing test is `apps/bff/tests/test_case_sessions.py::TestStatusesAreNeverClientWritable`
— it walks every non-GET route against an explicit allowlist and refuses a request model
that carries a status-shaped field. (It is NOT in `test_session_store.py`; that file tests
round-trips, path-traversal and version conflicts.)

## Where things are

- `docs/engagement/product-app-plan.md` — the plan, its adversarial grill, and §10, the
  queued client direction. Read §10 before picking up new UI work.
- `docs/engagement/copy-debt-ledger.md` — every demo→product copy.
- `docs/engagement/product-runbook.md` — how to run and demo the product app.
- `apps/worker/reports/product/<case>/runs/<run_id>/` — immutable run dirs. Never mutate a
  landed run. (The BFF's `product_root`, `apps/bff/src/bff/config.py:27`. There is NO
  `reports/` at the repo root — a `cd reports/product` fails, which is exactly the guess
  this file exists to prevent.)

## The stale-server trap

A dev server started before your change answers from the schema it booted with, and a
pydantic `extra=forbid` model that predates a field returns **422 "Extra inputs are not
permitted"** — indistinguishable, at the surface, from a real refusal. This cost a
debugging session on 2026-08-01. `.claude/launch.json`'s `bff` entry now carries
`--reload` over both `src` and `../worker/src/case_prep/application`, so start it from
there rather than by hand. When a 422 makes no sense, check the process is younger than
the code:

```bash
ps -eo pid,lstart,command | grep "uvicorn bff.main" | grep -v grep
```

## The typecheck trap

`apps/product/tsconfig.json` is a REFERENCES SHELL (`"files": []`). Running
`tsc --noEmit -p apps/product/tsconfig.json` exits 0 having checked NOTHING — it did so
for a whole session while two wrong-shaped API handlers sat in the tree. The real check:

```bash
cd apps/product && ./node_modules/.bin/tsc --noEmit -p tsconfig.app.json
```

## Conventions

- React tests use `renderToStaticMarkup` in the **node** environment — there is no jsdom.
  `StaticRouter` imports from `react-router-dom`, not `react-router-dom/server`.
- Python is typed and `from __future__ import annotations`; pydantic models are
  `extra=forbid`.
- A change is not done without tests, and tests are written first.
