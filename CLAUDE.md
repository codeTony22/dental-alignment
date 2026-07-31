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
cd apps/worker && make test          # 977 tests, both lanes — the certification gate
cd apps/bff    && ../worker/.venv/bin/pytest -q     # 358 — SHARES THE WORKER VENV, it has no own .venv
npm test --prefix apps/product       # 383
npm test --prefix packages/viewer    # 73
npm test --prefix apps/web           # 789 — the FROZEN demo; must stay green and untouched
```

Worker lanes: `make test-fast` (760, not-slow) · `make test-slow` (217, real meshes) ·
`make test` (both). Nothing ships on `test-fast` alone.

Also `cd apps/worker && make rehearse` — the demo-readiness gate: every case down the UI's
own path against a known baseline.

## The freeze line

The demo app is **frozen at commit `8125cbf`** and is never edited again. This must print
nothing:

```bash
git diff --stat 8125cbf -- apps/web apps/worker/src/case_prep/server.py apps/worker/tools
```

Deliberate demo→product copies get a row in `docs/engagement/copy-debt-ledger.md` **in the
same commit**. An unrecorded copy is drift.

## Architecture

`apps/product` (React, :5174) → `apps/bff` (FastAPI, :8001) → `case_prep.application` →
`case_prep.pipeline` / `domain` / `adapters`.

**`case_prep.server` may never be imported outside the frozen demo** — an AST test enforces
it. `application/` is the seam: BFF-facing logic is lifted there, not reached for in
`server.py`.

Statuses, verdicts and gates are **derived server-side, never accepted from a client**; the
session store's allowlist test enforces that no request body carries a status-shaped field.

## Where things are

- `docs/engagement/product-app-plan.md` — the plan, its adversarial grill, and §10, the
  queued client direction. Read §10 before picking up new UI work.
- `docs/engagement/copy-debt-ledger.md` — every demo→product copy.
- `docs/engagement/product-runbook.md` — how to run and demo the product app.
- `reports/product/<case>/runs/<run_id>/` — immutable run dirs. Never mutate a landed run.

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
