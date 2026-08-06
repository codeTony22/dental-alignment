# Architecture review — 2026-08-06

**What this is.** A structural review of the system itself — not the feature
queue (that is `next-phase-plan.md`, which stands). Produced from five
evidence-cited deep-dives over the codebase (execution, state, frontend,
quality infrastructure, detection/measurement data), three external research
tracks (interop standards, execution architecture, measurement storage), and
one adversarial verification pass that re-read every load-bearing citation,
refuted one claim (the `--reload` wedge trigger — uvicorn waits for in-flight
requests), re-ordered the roadmap once (the golden DEV pin now precedes the
interpreter move it exists to police), and contributed four findings this
document had missed (logging, auth posture, the product path's missing
end-to-end gate, the undeclared HTTP stack). Where this document says
"measured", a number was read, not recalled.

**The one-paragraph verdict.** The architecture is a deliberate, well-documented
monolith whose *seams are already in the right places* — the job-shaped worker
port, the SessionStore interface, the domain/application/adapter layering, the
pure-rule frontend domain layer — and whose file-first philosophy is a strength
to double down on, not a debt to migrate away from. The real exposure is not
architectural; it is **operational**: a single unbacked-up copy of every
operator act and payment record, a receipt wedge that can lock a case with no
recovery door, an EOL interpreter serving HTTP with zero logging and zero
authentication, no CI, an environment a clean checkout cannot even reconstruct,
and a measurement system whose numbers evaporate with the terminal scrollback.
Almost everything urgent is small precisely *because* the seams are good.

---

## 1. The system as it is

One uvicorn process (Python 3.9.6, Apple CLT) contains the HTTP layer and all
geometry physics: the BFF declares `case-prep` as a dependency and runs from
the worker's venv (`apps/bff/pyproject.toml`; `.claude/launch.json`). A run
executes **synchronously inside the HTTP request thread** —
`InProcessWorker.submit()` calls `_execute()` before returning
(`apps/bff/src/bff/ports/worker.py:144-160`) — deliberately job-shaped
(queued/running/done/refused/failed) so a future queue adapter replaces one
class. State is three file planes with clean source-of-truth boundaries:
`data_root` case trees (inputs; identity = folder name), per-case
`session.json` documents (operator acts; in-document CAS version + one
process-wide lock + atomic tmp/`os.replace` writes), and immutable run dirs
(physics facts; sha256 manifests; refusal/failure files as the honest terminal
states). The frontend is five stage containers (the components tree totals
17.7k lines) over a pure-rule domain layer (13.4k lines, ~1:1
test-to-source) tested with static markup in node — no effect ever runs in a
test. The gates — five test suites, the real typecheck, the freeze-line diff,
plus `rehearse` and `verify-fleet` — run by hand on one machine; there is no
CI, no lockfile, no backup, no log output from the BFF, and no authentication
on any route.

That design is *right for one lab at tens of cases/day* — the review confirms
throughput is nowhere near the ceiling, and FastAPI's threadpool keeps other
requests flowing during a ~10s run. What follows are the places it bends.

---

## 2. Software-engineering assessment

### 2.1 The execution model — keep it, fix its four sharp edges

**S1 · The stuck-receipt wedge.** A `run.state == "queued"` receipt is
persisted *before* the physics, and its withdrawal runs only inside the
request's `except` (`case_sessions.py:2296-2302`) — and is itself best-effort
(`except Exception: pass` after a contended CAS, `:2176-2177`). So the receipt
can outlive its run two ways: **process death mid-run** (a hard kill, power
loss, or a native open3d segfault — *not* a routine `--reload`, which the
installed uvicorn drains gracefully; the adversarial pass verified this), or
**a contended withdraw on a live box**. Either way every later run attempt
409s "already in flight" with no recovery door short of a review-destroying
reset. Two complementary fixes, both small: (a) treat a sufficiently old
`queued` receipt as releasable **on read** (works on a box with 200 days of
uptime — no boot required), and (b) a startup sweep in the FastAPI
**lifespan** — emphatically not in `create_app`, which tests import at module
scope against the real product root and which must never gain writes. The
sweep must also stamp `failure.json` into any run dir its withdrawn receipt
names: a mid-run death currently leaves a partial dir with *no terminal file*,
violating the honesty invariant the worker enforces everywhere else — and
`verify.py::latest_run_dir` selects baselines by implant-record presence, so a
half-written dir can become the standing baseline. Require the manifest there.
Order matters: the flock below lands **first**, because the sweep's safety
argument ("no in-flight work after restart") is only true once single-process
is enforced.

**S2 · The single-process assumption is unenforced.** Cross-process CAS
deliberately doesn't exist (`session.py:876-879`); a stray second uvicorn (or
`--workers 2`) silently loses operator acts — last `os.replace` wins. Cheapest
honest fix: an exclusive `flock` on a lockfile under `product_root` at boot, so
a second process **fails loudly**. The SQLite session store remains the phase-2
answer; the flock makes waiting for it safe — and makes S1's sweep sound.

**S3 · Crash isolation, not a queue.** The research verdict is unambiguous for
this scale: no broker, no Celery, no arq (maintenance-mode). The converged
pattern is a `ProcessPoolExecutor(1-2)` created in the FastAPI lifespan +
202-and-poll, with the run dirs *already serving as the job table*. What the
pool buys here is not throughput but **fault isolation**: open3d's native code
has a documented segfault history on this host, a segfault today takes down
the whole HTTP surface — and it is precisely the S1 trigger. The port makes
this a one-file change. A queue (Huey-on-SQLite, the only zero-new-service
option) is the named escape hatch with a concrete trigger — multi-box, or
scheduled/retried work — not a plan.

**S4 · The one sanctioned run-dir mutation is unlocked.** Adjust tools rewrite
STL/record/manifest inside a landed run dir with the physics *outside* the CAS
mutation (`resources/adjust.py:44-49, 498-508`). Two operators on the same site
can interleave writes; the disclosure gate catches a torn manifest but surfaces
it as a baffling 409. A per-case lock around `run_tool + _land` is trivially
cheap in the single-process world. (Also record: this mutation lane means a run
dir is *current state, not history* — the pre-adjustment pose is unrecoverable;
the append-only adjustments list is the deliberate audit answer.)

### 2.2 The platform — the interpreter is the deadline, and the environment is broken in shape

**S5 · Python 3.9.6 is past EOL and serving HTTP — and a clean checkout cannot
even reconstruct today's process.** The interpreter is pinned by the Open3D
0.18 arm64 wheel — whose most crash-prone API the codebase *already replaced*
with home-grown numpy/scipy ICP confined to one lazy adapter — so the 3.11
move the pyproject itself promises is mostly a re-wheel + gate exercise
(see §4 for what the court must include). Worse than the version drift: the
adversarial pass found **`uvicorn` and `httpx` are declared in neither
pyproject, `fastapi` only in the BFF's — and no make target ever installs
`apps/bff`**. The one installer (`apps/worker/Makefile: pip install -e
".[dev]"`) produces a venv in which the launch entry points at a uvicorn
binary that does not exist and the BFF gate cannot import TestClient. Today's
process exists only because someone hand-installed the HTTP stack. Fix order:
declare the real dependencies and add the BFF install step, *then* the
lockfile (uv/pip-compile) + `.python-version`, *then* the 3.11 re-wheel.
Add `make doctor` (interpreter version, open3d importability, data presence,
uvicorn present) — it converts the next machine's lost hour into five seconds.
Node is half-pinned (pnpm + lockfile; add engines/.nvmrc).

### 2.3 Quality infrastructure — the gates are good; nothing runs them, and one lane has no gate at all

**S6 · No CI, and the honest split already exists.** Push lane: worker
`test-fast` (~19s) + BFF (~37s) + three npm suites + the *real* typecheck +
the freeze-line diff — under 3 minutes total. Nightly: full battery + the
end-to-end lane + verify-fleet **with output archived**. The hard blocker is
data, not compute: 211MB of clinical meshes are (correctly) gitignored and 24
test files `skipif` on their presence — a clean checkout runs the slow lane
*hollow*, green-but-weaker, which is exactly the dishonesty this repo's
culture forbids. Options in order: self-hosted runner on the dev box (honest
about where clinical data lives — but see §2.5: that machine holds the only
copy of everything, so pushed-code execution on it is a coupling to state, not
to hide), or a private bucket + `make fetch-data` + a `--strict-data` flag
that turns silent skips into failures. Two more facts CI must respect:
`bff/main.py` builds the app at module scope over `default_settings()`, so
**the BFF test gate currently reads the production data plane** (decouple with
a test-settings fixture before putting it on a runner); and graduate the
freeze-line check + counts floor from CLAUDE.md prose into `make` targets both
humans and CI share.

**S6b · The product path has no end-to-end gate.** `rehearse` — counted for
weeks as the demo-readiness court — drives **the frozen demo's server**
(`rehearse_demo.py: from case_prep.server import app`), the one lane that
never changes. The lane that ships every day (product UI → BFF →
`application`) has no whole-fleet end-to-end check at all. A product-lane
rehearse (same script shape, `bff.main:app` via TestClient, same baseline
discipline) is cheaper than the jsdom layer and covers the path that actually
ships. This was the adversarial pass's sharpest omission catch.

**S7 · The flake has a named suspect with a mechanism.** `test_stages.py::
test_full_workflow_end_to_end`: the stages lane's `engine.register` passes no
rng, falling through the `rng.py` migration shim to the **process-global numpy
stream** — and ~20 test files seed or churn `np.random`, so under
`-n auto --dist loadfile` the gate verdict depends on which files that xdist
worker ran first. The fix is the migration the shim itself prescribes (thread
a `PipelineRng` through the stages lane); the cheap falsifier first is an
autouse constant-seed fixture in that file.

**S8 · The BFF emits no logs at all.** Not one `import logging` in the entire
BFF; three `except Exception` swallow-sites on compensation paths. When the S1
wedge fires — or anything else — no artifact anywhere says so. Five lines
(`logging.exception` in the three handlers + basicConfig in the lifespan) is
worth more than several Tier B items, and it is a precondition for ever
diagnosing a field incident by evidence instead of memory.

### 2.4 Frontend — the convention hit its categorical limit

**S9 · The client has been functioning as the effect-layer test suite.** The
pure-rule layer is genuinely excellent (near 1:1 test-to-source; words, gates
and folds all pinned). But the static-markup convention means *no effect ever
runs in a test*, and the containers' own comments log at least five async
wiring bugs caught only live (auto-mark cancelling its own fetch; the frozen
rows nonce; presets without a camera; linked reset; this week's held-pose).
The jsdom beachhead already exists in-repo (`jsdom` devDependency, per-file
`@vitest-environment jsdom` pragma on two hook tests, the §10-O.8 doctrine).
The move: one jsdom container mount per stage with the viewer package mocked
and fetch faked — configuration-free per file, zero risk to the 1,264 node
tests — plus extracting the AdjustStage settle-fold (~10 setters in one
callback, the file's riskiest and least-tested region) into a pure reducer in
domain/adjust. A thin Playwright smoke over the launch.json servers covers what
jsdom can't (WebGL panes), as a shipping gate, not an inner loop.

**S10 · Copy-debt bookkeeping rots; make the boundary mechanical.** The
ledger's discipline is excellent and its numbers are stale for the second time
(it says styles.css is 5,463 lines; it is 7,118). A small read-only script that
locates the PRODUCT-ADDITIONS marker and diffs the copied region against
`8125cbf`, run beside the freeze check at ship time, ends the rot. Also pin the
two deliberately-different constants (11mm/9mm crop bands) with one-line tests
in their own packages so a well-intentioned "cleanup" fails a gate instead of a
review.

### 2.5 Security posture — state the boundary out loud

The BFF has **no authentication of any kind** — no auth dependency, no API
key, no CORS policy; the `X-Operator` header is self-reported identity
"behind no authentication" (the session module says so itself). Unauthenticated
routes include payment authorization, release, and the one writer into
`data_root` (uploads — which, credit due, is the best-defended surface in the
repo: traversal-proof naming, streaming size cap, no half-writes; the gap is
authorization, not validation). The words PHI and encryption appear nowhere,
yet the data plane is clinical scans plus payment records. Today's posture —
localhost-bound, one trusted operator, one box — is *defensible*; what is
missing is this codebase's own signature move: **stating the boundary as a
deliberate, dated decision** so it cannot silently rot into a networked
deployment. Concretely: a §-note in the runbook; bind explicitly to
127.0.0.1; encrypt the backup target (D1); and when CI lands, remember the
self-hosted-runner coupling above. The moment a second workstation or a
network deployment is asked for, auth is the first slice, not an afterthought.

---

## 3. Data-engineering assessment

### 3.1 Durability — the single worst finding of the whole review

**D1 · There is no backup — and the two planes deserve different treatment.**
`reports/product` and `data/real` are gitignored, single-copy, on one
workstation. Measured: the irreplaceable plane — every operator act,
confirmation, **payment record** — is all of **152 KB** of `session.json`;
the bulk plane is **4.3 GB** of run dirs (~170 MB/run) plus 211 MB of scans.
Physics is only *approximately* re-derivable — new run ids orphan every sealed
confirmation — and operator acts are not re-derivable at all. So: **versioned,
frequent, off-box backup for the sessions** (they are tiny — every save could
ship), a nightly `restic` snapshot for runs + scans, and an **encrypted**
target (clinical data). Note the growth math the review surfaced: at the
stated design point (tens of cases/day × ~170 MB/run) the run plane grows
GB/day, which moves the retention/archive policy from "on trigger" to
near-term, and sizes the backup target honestly. This item goes **before
anything else in this document**.

**D2 · Rollback silently deletes newer fields.** Persisted session models use
pydantic's default `extra="ignore"` — an older build loading a newer document
drops unknown keys, and its next CAS save (whole-document rewrite) deletes
them permanently: rolling back past §10-AD would erase `alignment_evidence`
case by case, with no error anywhere. Fix: a `schema_version` on the document
with refuse-to-save when the disk document is newer than the build, or
`extra="allow"` round-tripping. Small, and it converts a silent data loss into
a loud refusal — this codebase's signature move. (Side-finding: CLAUDE.md's
"pydantic models are extra=forbid" is true of request models only; the
persisted models are the exception, and the docs should say so.)

### 3.2 Lineage — strong downstream, three upstream breaks

Downstream is unusually good: pose → audit block → append-only adjustments →
re-hashed manifest → content-addressed evidence bundle → confirmation pinning
`run_id + evidence_sha256`; re-emits name their source run. Upstream breaks:
**the library template is named, never hashed** (a silently replaced variant
STL is undetectable from any run record — one `sha256` call into
`implant.json`'s audit block closes the biggest provenance gap, and the
browser-lane catalog *already computes* these hashes; the two lanes just never
joined); the activity narrative is a 40-entry window (append every entry to a
per-case `activity.jsonl` beside the windowed copy); the submitted job request
lives only in process memory (persist `request.json` into the run dir — the
queue adapter will need it serialized anyway).

**D3 · Case identity is a folder-name convention with no registry.** A folder
rename orphans a session (with its confirmations and payments) *silently* —
session load of an unknown case mints a fresh document. Cheap: write an
identity stamp (`case.json`: id, created_at, scan sha256) into scan folders at
first-work time, and make the worklist flag orphaned product dirs instead of
ignoring them. Upload intake should hash the stream while writing (it is
already chunked) — integrity check and dedup advisory in one move.

### 3.3 Measurements as data — the largest data-engineering gap

**D4 · The fleet dataset is computed and thrown away.** `verify-fleet` builds
exactly the queryable rows (per-site shipped RMS/P90 + per-seed-provenance
comparisons) as dicts, prints them, and deletes every scratch dir. Meanwhile
each run dir already carries **~40 scalars per site** (fit, coverage,
icp_fitness, rim agreement, confidence spreads, clocking, variant margins,
gingival percentiles, DEV RMS/P90, re-apply receipts…) — a time series is one
harvest away, with *no new instrumentation*. The research verdict on shape
(and it mirrors the repo's own file-first invariants exactly):

- nightly batch writes `reports/fleet-verify/<date>/metrics.jsonl` (stdlib
  json; one line per case/site/seed) + `batch.json` (git SHA, timestamps) —
  a new immutable dated dir, greppable, diffable;
- **DuckDB reads the JSONL glob in place** (`read_json_auto`) — the `.duckdb`
  file is a disposable derived index (`make fleet-db`, rebuilt in seconds;
  Baked-Data pattern), never a second source of truth;
- consumption: checked-in `.sql` queries + one marimo notebook (a plain
  `.py`, git-diffable, same venv) for trends. Datasette is the named upgrade
  if a standing browsable UI is ever wanted; Evidence.dev rejected (a Node
  build pipeline for a two-person audience).

**D5 · The acceptance instrument has no golden reference — and the roadmap
must respect that before touching the platform.** Nothing anywhere pins a
*measured* DEV value: rehearse pins flags, the battery asserts shapes and
ranges, and the 0.01mm noise floor is asserted, not measured. The sampling is
deterministic *today* (the seed is applied and restored, verified down to the
installed trimesh routing `seed=None` to the legacy global stream) — the
exposure is that **any dependency or template shift moves every RMS silently**
(a trimesh default flip would make the seed a no-op with no tripwire), and
monotonic-accept would then be arbitrated by an uncalibrated constant on a
shifted scale. Three moves, and their order is the point: **pin one golden
(scan, pose, template) triple's `rms_mm` to 4 decimals in a fast test and
measure the floor FIRST** (repeat runs across perturbations on the 8 landed
sites — the receipt for or correction of 0.01), because the 3.11 re-wheel
(S5) re-resolves numpy/scipy/trimesh — the exact perturbation this instrument
cannot currently see. The full battery is not a court for this; the golden pin
is. The nightly dated fleet file then serves as the standing drift tripwire.
(A deterministic `vertex_deviation` already exists in the same adapter if the
RNG dependence ever needs to go entirely.)

### 3.4 Detection as a data problem

The detector is a fully heuristic discriminator stack — ~13 module constants
calibrated on **2–5 labelled arches** in July, recall-first with the human
click as the precision stage. That is a defensible design; what is missing is
the data discipline around it:

- **Ground truth**: 10 curated sites across 9 files; the upload arch — the
  growth path — has *zero labels*, so its recall is unmeasurable in principle.
  Convention fix: every upload that reaches a confirmed run back-fills an
  expected-sites manifest from the operator's own confirmations — labels
  accrete from production use for free.
- **Rejection telemetry**: the rim-slab test's five rejection paths all return
  an indistinguishable `None`; the height/arch-band/ratio/separation gates
  `continue` silently. "Measure why the arch found 1 of N" cannot be executed
  scientifically today. A trace mode returning per-candidate per-gate values
  is a pure addition.
- **Recall fixtures**: the strongest count assertion anywhere is "both known
  caps, ≤6 candidates" — a drop to 1-of-4 on a multi-cap case would pass every
  existing gate. The §1.3 fixture (arch + expected counts) closes it.
- The capture gate's bounds are calibrated to IOS-class mesh density —
  a different-vendor upload could read systematically low; log
  (value, verdict, eventual DEV) per site so the correlation argues.

### 3.5 Interop and the regulatory frame (research verdicts)

- **PLY intake is the one interop addition with real payoff**: TRIOS, Medit
  and iTero all export colour-bearing PLY; exocad ingests it natively. Accept
  and *store* PLY (strip to mesh initially) — colour is the obvious next
  detection feature if geometry ever plateaus, and it only exists if intake
  keeps it. 3MF is a printing-side story — watch, don't build. ISO 12836 is a
  scanner test-method standard (not data exchange); ISO 18618 is the XML
  case-transfer schema an enterprise checklist might one day cite.
- **Regulatory (honest reading of public records, not legal advice)**: dental
  labs stay inside the traditional 21 CFR 807.65 exemption doing
  prescription-driven work; the cleared-device line for dental CAD sits where
  software *designs patient-specific implant components* (exocad AbutmentCAD's
  own 510(k), K193352). An alignment/verification aid presenting fit evidence
  to a technician sits well short of that line. The watch-item is scope drift:
  the moment the product *generates or modifies delivered part geometry*
  beyond catalog parts, get advice. Position the product as a lab-efficiency
  aid supporting technician judgment; avoid diagnostic-sounding claims.

---

## 4. The structural roadmap — dependency-ordered

**Tier A — this week; small, and they close corruption/loss holes**
1. Backup: versioned frequent copies of `*/session.json` (152 KB — every save
   can ship) + nightly encrypted snapshot of runs and scans (D1).
2. Boot-time `flock` so a second process fails loudly (S2). *Before* item 3 —
   it is what makes item 3's safety argument true.
3. The wedge: age-based release of stale `queued` receipts on read, plus a
   lifespan (never `create_app`) startup sweep that also stamps `failure.json`
   into orphaned run dirs; `latest_run_dir` requires the manifest (S1).
4. `schema_version` + refuse-to-save-older (D2).
5. Logging in the BFF: basicConfig in the lifespan + `logging.exception` in
   the three swallowing handlers (S8).
6. The golden DEV pin + the measured noise floor (D5) — deliberately **before**
   any platform work.
7. `verify-fleet` writes its rows as a dated JSONL beside the print (D4 step 1
   — five lines; the store can follow later).
8. Template + scan sha256 into the run audit block (lineage).
9. The flake falsifier: constant-seed fixture in test_stages, then the
   PipelineRng migration (S7).

**Tier B — the structural upgrades (next 2–3 weeks, each independent)**
10. Environment shape: declare uvicorn/httpx/fastapi where they belong, add
    the BFF install step and `make doctor`; then the lockfile +
    `.python-version`; then the 3.11 re-wheel with the full battery **plus the
    golden pin** as the court (S5 + D5).
11. A product-lane rehearse: the demo's end-to-end script pointed at
    `bff.main:app` with its own baseline — the shipping path's first
    whole-fleet gate (S6b).
12. CI: push fast-lane + nightly full battery / product-rehearse /
    verify-fleet with archived output; decouple the BFF gate from the
    production data plane first; self-hosted runner with the §2.5 coupling
    stated; skips-made-loud flag (S6).
13. ProcessPool isolation + 202/poll formalization + lifespan teardown (S3).
14. The jsdom container-test layer + the settle-fold reducer extraction (S9).
15. `make fleet-db` (DuckDB over the JSONL glob) + checked-in queries + one
    marimo trend notebook (D4).
16. Detection telemetry + the arch recall fixture + the label-accretion
    convention (§3.4) — this *unblocks* next-phase-plan §1.3.
17. Per-case `activity.jsonl`; upload-stream hashing; case identity stamp;
    `request.json` into run dirs (§3.2, D3).
18. Copy-debt boundary script + the two constant pins (S10). Per-case run-dir
    lock around the adjust tools (S4).

**Tier C — on trigger, not on schedule**
- SQLite session store (trigger: second box or persistent multi-operator
  conflicts). The SessionStore seam is ready.
- Auth (trigger: any second workstation or non-localhost bind — then it is the
  *first* slice, per §2.5).
- Huey-on-SQLite queue (trigger: scheduled/retried work or a second box).
- PLY intake (trigger: first clinic that sends one — or proactively with the
  border-points work, same intake surface).
- Datasette over the metrics store (trigger: a third person wants the charts).
- Run-dir retention/archive policy — near-term at GB/day growth; write the
  stance down now, build at disk pressure.

**Sequencing note.** Tier A is deliberately *before* the feature work in
`next-phase-plan.md`: every item is hours-not-days and each closes a hole that
could cost real lab data or a real case. The two plans then interleave — the
misfit-family advisor (next-phase §2.1) rides on the metrics store (item 15),
and arch detection recall (§1.3) rides on telemetry (item 16).

---

## 5. Opinion — what to defend, what to change, what to refuse

**Defend the monolith.** One process, one venv, file-based state: at this
scale that is not technical debt, it is the correct engineering. Every
research track independently confirmed it. The seams for the day it changes
(worker port, SessionStore, run-dir job table) already exist and are the
cleanest parts of the design.

**Defend file-first — and complete it.** The immutable-run-dir discipline is
genuinely good data engineering. Its missing half is *measurements as data*:
the same discipline (immutable dated dirs, derived disposable indexes) applied
to the fleet's numbers. That, plus backup, turns the file-first philosophy
from a stance into a system.

**Change the testing convention at the effect boundary — on both sides.** The
static-markup rule served its purpose and hit its categorical limit (five
client-caught async bugs in one week); the jsdom beachhead exists — extend it.
And the server side has the mirror-image gap: the frozen demo has an
end-to-end gate, the shipping product does not. Close both.

**Refuse two tempting migrations.** No queue/broker infrastructure at this
volume (the research is unanimous, and the ops burden lands on a two-person
team), and no orchestrator (Prefect/Dagster) for the pipeline — the re-emit
lane proves the hand-rolled content-addressed pattern already works; generalize
it inside the run-dir scheme if stage caching is ever needed.

**The single most urgent item in this entire document is a backup cron** —
152 KB of operator acts and payment records that exist exactly once, on one
disk. It is also the least glamorous. That is usually how it goes.
