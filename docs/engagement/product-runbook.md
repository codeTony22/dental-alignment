# Product app — how to run and demo

**State (2026-08-02, HEAD `d84a0f9`):** the client's FIVE-STAGE flow is complete — a case
walks Intake → Alignment → run → Adjustment → Construction library → Delivery, finishing with
a confirmation sealed over an evidence bundle and a gated, paid (stub), per-site release.
Adjustment carries five correction tools. Remaining: slice 9 (predictability gate v2), plus
the items plan §10-M/N record as open.

THE STAGE KEYS ARE NOT THE TITLES, and the URL shows the key. Narrate from the right column:

| URL / key | what the rail says |
|---|---|
| `intake` | Intake |
| `declare` | **Alignment** |
| `adjust` | **Adjustment** |
| `library` | **Construction library** |
| `deliver` | **Delivery** |

The ORIGINAL demo is frozen and untouched (its own runbook: demo-runbook.md; freeze proven by
`git diff --stat 8125cbf -- apps/web apps/worker/src/case_prep/server.py apps/worker/tools`
= empty).

## 1. Run it

Two servers. The worker venv is the one Python environment; the BFF is installed into it.

```bash
# terminal 1 — the BFF (presentation API + physics via the application layer), :8001
cd apps/bff && ../worker/.venv/bin/uvicorn bff.main:app --port 8001 --app-dir src \
  --reload --reload-dir src --reload-dir ../worker/src/case_prep/application
```

`--reload` is not optional comfort. A BFF older than the tree answers **422 "Extra inputs
are not permitted"** to a field the code already has, and that is indistinguishable from a
real refusal — it cost a session on 2026-08-01. Starting the `bff` entry from
`.claude/launch.json` gets these flags for free.

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
5. **Construction library** — pick the part Delivery cuts. The rows are the real catalog
   (grouped by vendor, the effective one chipped "suggested" or "selected"), and the pane
   beside them renders the RUN'S OWN unified mesh — the arch with every site's construction
   posed into it. Say: "this is the construction against the patient's scan, and the caption
   tells you it is the part the run used — choosing a different one cannot change the picture
   until the case re-runs." That honesty is the point; do not promise a live preview of an
   unrun part, which is not built (plan §10-M).
   Reachable only over a DONE run with every site resolved, and **Delivery will not open
   until a part is chosen here** — if Delivery looks blocked, this is why.
6. **Delivery** — the assurance table, worst-first, flags pinned; expand a row for the two QC
   images; per-site disposition (release / withhold); every flagged-released row needs its own
   acknowledgment tick. Type the operator name → **Confirm** (the evidence bundle is sealed —
   the hash is shown) → **Authorize payment (stub)** (labelled as a stub, recorded as one) →
   **Release** → the artifact list with downloads.
7. The kill shot, if asked "is this secure?": change ANYTHING after confirming (a declaration,
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

Counts move every time a test is added, so read them as a floor rather than a target — the
number's job is telling "my change broke collection" apart from "the suite grew". The five
gates and their commands are listed in CLAUDE.md; run them and read each summary line.
`rehearse` must print "REHEARSAL CLEAN" (the frozen demo's gate — still binding). The full
worker battery (~13 min) before anything client-facing that touched the pipeline.

## 4. What to say about what's missing (honesty beats surprise)

- **Adjustment** is built and skippable BY DESIGN (the client's own ruling); flagged sites
  can also be handled at Delivery via withhold. Five tools: fit by points (a pair may span
  two points on the scan, two on the LIBRARY part, or both), best fit, rotation dial, mark
  trench, auto-mark. A fit whose marks disagree with each other is now REFUSED rather than
  applied, and a mark on the screw access is refused locally before the round trip.
- **Previewing a construction part the case has NOT run** is not built — the library page
  shows the run's own unified mesh and says so on the caption.
- **Where confirmation lives is an open client decision.** It is on Delivery today; their
  five-page prose puts it on Adjustment; their own design comp puts the control inside the
  payment dialog. Plan §10-N has the evidence. Do not improvise an answer on a call.
- **Payment** is a stub and says so on the button and in the record (`provider: "stub"`).
- **Import/upload** is not built; cases come from the data root (the select flow).
- **Visual polish** is thinner than the frozen demo's — structure and the audit chain were
  built first, deliberately. The frozen demo remains the pretty one; the product app is the
  correct-shaped one. Both run side by side.
