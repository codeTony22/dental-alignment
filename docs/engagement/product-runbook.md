# Product app — how to run and demo

**State (2026-07-27, HEAD `ea0b9a1`):** the minimum demoable cut is complete — a case walks
Intake → Declare → run → Deliver end to end, finishing with a confirmation sealed over an
evidence bundle and a gated, paid (stub), per-site release. Remaining slices: 6 Adjust
(skippable by design — never blocks this demo), 7 two-point spans, 9 predictability gate v2.
The ORIGINAL demo is frozen and untouched (its own runbook: demo-runbook.md; freeze proven by
`git diff 8125cbf -- apps/web apps/worker/src/case_prep/server.py` = empty).

## 1. Run it

Two servers. The worker venv is the one Python environment; the BFF is installed into it.

```bash
# terminal 1 — the BFF (presentation API + physics via the application layer), :8001
cd apps/bff && ../worker/.venv/bin/uvicorn bff.main:app --port 8001 --app-dir src
```

```bash
# terminal 2 — the product app, :5174
cd apps/product && pnpm dev
```

Open **http://localhost:5174**. (The frozen demo still runs beside it: `make serve` in
apps/worker for :8000, `pnpm dev` in apps/web for :5173 — nothing conflicts.)

First-time setup on a fresh machine only: `pnpm install` at the repo root, and
`apps/worker/.venv/bin/pip install -e apps/bff`.

Fast health checks:

```bash
curl -s localhost:8001/health
```

```bash
curl -s localhost:8001/api/case-sessions | head -c 400
```

To reset a case to untouched (sessions are the only mutable product state; run history under
`runs/` is immutable and safe to keep): delete
`apps/worker/reports/product/<case-id>/session.json`.

## 2. The demo script (one clean case, ~3 minutes of clicking)

Use **Doctor Cap6030 Neodent GM** (clean end-to-end; rim 0.22 mm, rotation code-verified).
`cap6020` is already walked-through/confirmed from verification — either demo material ("here
is a finished one") or delete its session.json to reuse it.

1. **Worklist** (`/`): nine cases, blocked-first, live rollup chips. Say: "one row per case —
   the tech's whole morning; opening a row resumes wherever it left off."
2. **Intake** — open the case. Detection fires ITSELF: "Detecting caps…", then the proposal
   lands as a marker on the 3D with a tooth guess and the capture verdict speaks first —
   rescan-grade problems are announced before any work is invested, in the pipeline's own
   sentences. Pick construction/jaw/relief (defaults pre-filled; the relief ceiling is stated
   beside the input). The rail ticks.
3. **Declare** — the site queue left, the system bar top (suggested system pre-selected;
   switching warns "resets N declared sites" before acting), variant cards with Ø × height.
   Click the variant → the PREVIEW fires itself and the three panes fill: library part
   (top-of-cap), scanned cap (down the seated pose's exact axis), union coloured by signed
   deviation with its RMS/p90. Say: "you are looking at the alignment BEFORE anything is
   processed." Tick the review — the tick is refused until the panes have something real.
4. **The run fires itself** the moment every site is reviewed — footer: "Aligning N sites —
   30–60 s". It lands in an immutable run directory; verdicts land on the site chips.
5. **Deliver** — the assurance table, worst-first, flags pinned; expand a row for the two QC
   images; per-site disposition (release / withhold); every flagged-released row needs its own
   acknowledgment tick. Type the operator name → **Confirm** (the evidence bundle is sealed —
   the hash is shown) → **Authorize payment (stub)** (labelled as a stub, recorded as one) →
   **Release** → the artifact list with downloads.
6. The kill shot, if asked "is this secure?": change ANYTHING after confirming (a declaration,
   a review) and hit Release — **409: "the case changed since it was confirmed — re-confirm
   over the current evidence."** Artifacts refuse without a valid confirmation AND payment at
   the ENDPOINT, not the screen. Every gating record names its operator.

Multi-cap volume story: open **Doctor Neodent GM** (two sites) — the queue, per-site
declarations/previews/ticks, one run over both, per-site dispositions at Deliver (withhold
one, release the other).

## 3. Gates before demoing

```bash
cd apps/bff && ../worker/.venv/bin/pytest -q
```

```bash
cd apps/product && pnpm typecheck && pnpm test
```

```bash
cd apps/worker && make test-fast && make rehearse
```

Expected (2026-07-27): bff 253+ · product 245+ · viewer 73 · worker fast 692+ · rehearse
"REHEARSAL CLEAN" (the frozen demo's gate — still binding). Full worker battery (`make test`,
~25 min) before anything client-facing that touched the pipeline.

## 4. What to say about what's missing (honesty beats surprise)

- **Adjust** is a placeholder stage — skippable BY DESIGN (the client's own ruling); flagged
  sites today are handled at Deliver via withhold. The correction tools (fit by points with
  two-point spans, best fit, rotation dial) are slices 6–7, next up.
- **Payment** is a stub and says so on the button and in the record (`provider: "stub"`).
- **Import/upload** is not built; cases come from the data root (the select flow).
- **Visual polish** is thinner than the frozen demo's — structure and the audit chain were
  built first, deliberately. The frozen demo remains the pretty one; the product app is the
  correct-shaped one. Both run side by side.
