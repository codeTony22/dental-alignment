# Architecture

What this system is, how it is layered, and which rules are load-bearing. Read this before
changing anything structural. `CLAUDE.md` at the repo root is the short operational map;
this is the reasoning behind it.

---

## 1. What the product does

A dental lab receives an intraoral **scan** of a patient's arch with **healing caps** screwed
into the implant sites. The lab needs, for each site, a manufacturable part aligned to the
implant's true axis and rotational clock. Doing this by hand in CAD takes a trained
technician tens of minutes per site.

This system automates it: find the caps in the scan, identify which catalog cap each one is,
recover the seated **pose** (axis, origin, clock), bore the screw channel, apply gingival
relief, and emit a package the lab can manufacture — with evidence a human can audit before
paying for it.

The hard part is not the CAD. It is **knowing when the answer is wrong** and saying so.

---

## 2. Bounded contexts

| Context | Lives in | Owns |
|---|---|---|
| **Capture** | `domain/capture_gate.py`, `adapters/site_analysis.py` | Is this scan good enough to work from? |
| **Detection** | `adapters/cap_detection.py`, `application/detection.py` | Where are the caps? |
| **Catalog** | `domain/cap_catalog.py`, `adapters/*_catalog.py` | Which library part is this? |
| **Alignment** | `domain/poses.py`, `registration.py`, `icp.py`, `clocking.py` | Where exactly is it seated, and how is it clocked? |
| **Production** | `pipeline/final_product.py`, `domain/channel.py`, `design_rules.py` | Bore, relieve, and check the part is makeable |
| **Assurance** | `bff/evidence.py`, `pipeline/evaluation.py`, `adapters/qc_render.py` | What did we do, and can we prove it? |
| **Flow** | `bff/session.py`, `bff/status.py`, `product/src/domain/flow.ts` | Where is this case in the operator's process? |

Alignment and Production speak millimetres and degrees. Flow speaks statuses and acts.
Keeping those vocabularies apart is why the status ladder is a separate pure module from
everything that computes geometry.

---

## 3. Runtime topology

```
apps/product  (React + TS, Vite, :5174)     the operator's app
      │  HTTP, JSON only — no meshes except explicit mesh endpoints
      ▼
apps/bff      (FastAPI, :8001)              session state, gates, evidence, disclosure
      │  direct Python calls
      ▼
case_prep.application                        the BFF-facing seam
      │
      ▼
case_prep.pipeline / domain / adapters       the geometry and the physics
```

```
apps/web      (React, FROZEN)  ──▶  case_prep.server  (FastAPI, FROZEN)
```

`packages/viewer` holds the three.js scene controller, lifted from the demo and shared by
the product app. `apps/api` and `packages/shared` are placeholders (README only).

### The one-way rule

**`case_prep.server` may never be imported outside `apps/web`'s stack.** An AST test
enforces this. `server.py` is the frozen demo's HTTP layer; it accreted logic during the
spike, and the way that logic reaches the product is by being **lifted into
`case_prep.application/`** — a real function with a real signature and its own tests — not
by being reached back into.

`application/` is therefore the seam. Modules there (`cases`, `catalog`, `detection`,
`preview`, `run`, `adjust`) are plain callables over domain types. They know nothing about
FastAPI, sessions, or React.

---

## 4. The freeze line

The demo app is **frozen at `8125cbf`**. It is the working artifact the client has already
seen; it must keep behaving exactly as it did. This must always print nothing:

```bash
git diff --stat 8125cbf -- apps/web apps/worker/src/case_prep/server.py apps/worker/tools
```

Because the product legitimately needs the demo's hard-won UI and geometry code, deliberate
copies are allowed — but each one gets a row in `docs/engagement/copy-debt-ledger.md`, **in
the same commit**, recording what was copied, why, and every deliberate divergence. An
unrecorded copy is drift: two versions of the same idea silently disagreeing.

---

## 5. The trust architecture

This system asks a lab to pay for parts it did not verify by hand. Everything below exists
to make that defensible.

### Facts are derived, never claimed

Statuses, verdicts and gate outcomes are computed server-side from worker output. The
session store's allowlist test asserts that **no request body may carry a status-shaped
field** — a presentational app cannot PATCH a flagged site to `ready`; it is impossible, not
merely discouraged.

### The status ladder is pure

`bff/status.py` is a set of pure functions over `SiteStatus` with an exhaustiveness guard:

```
detected → declared → previewed → ready | flagged → adjusted → ready
```

Each transition is a named event (`declare`, `preview`, `review_ready`, `flag`, `adjust`,
`reseat_preview`, `withdraw_review`, `invalidate_preview`, `regress_to_detected`). Illegal
transitions raise `IllegalTransition` rather than silently landing somewhere plausible.

### The seat record defeats drift

A site marked `ready` records the **full selection its preview actually seated**
(`SeatedSelection`: system, construction, variant, jaw, relief). The effective-choice
fallbacks live outside that document and can change with no reset boundary firing — so the
rung alone cannot prove the operator's review still describes the case. The run gate refuses
any `ready` site whose record no longer matches the current selection.

### Evidence is content-addressed and re-derivable

`bff/evidence.py` builds a canonical JSON bundle (sorted keys, fixed rounding,
`allow_nan=False`) plus SHA-256 over the QC image bytes, written transactionally to
`runs/<run_id>/evidence/<sha256>.json`. **Release re-derives the bundle and 409s on drift** —
you cannot release artifacts that no longer match what was confirmed.

### Runs are immutable

`reports/product/<case>/runs/<run_id>/` is written once. The session holds a *pointer* to the
current run; reset boundaries clear the pointer, never the directory. Run history survives
every operator act.

### Writes are compare-and-swap

Every session document carries `version`. `save` raises `SessionConflict` when the disk has
moved on; handlers retry once, then surface a 409. The check-and-write pair is held under a
process lock because FastAPI runs sync handlers on a threadpool, so rival saves genuinely
overlap. Cross-process CAS is a phase-2 (SQLite) concern.

### Failure is loud

A corrupt session file refuses by name rather than starting fresh — a quiet reset would
forget a confirmation or a payment authorization. Worker crashes land as `JobState.FAILED`
and **withdraw** the queued receipt rather than leaving a case wedged in `running`.

---

## 6. The operator's flow

FIVE stages since the client's 2026-08-01 direction, in `apps/product/src/domain/flow.ts`.
The stage KEYS are unchanged, so routes, session fields and every `stage ===` comparison
still read the original names; the TITLES are the client's, and one stage is new:

1. **Intake** (`intake`) — case-level choices (construction part, jaw, relief), detection
   fires, capture verdicts surface *before* work is invested.
2. **Alignment** (`declare`) — per site: implant system and variant, then a preview seats
   the cap and the three panes show it. The operator confirms each site.
3. **Adjustment** (`adjust`) — optional. Fit-by-points (a pair may span two points on the
   scan, on the library part, or both), best fit, rotation, mark trench, auto-mark.
   Skippable, but skipping still requires seeing and confirming the assurance.
4. **Construction library** (`library`) — NEW. Pick the part Delivery cuts, and preview it
   against the scan. Reachable once the run is DONE and every site is resolved.
5. **Delivery** (`deliver`) — the assurance table, terms, payment, released artifacts.
   Additionally requires a chosen construction part.

Every stage but `library` has its own domain module; the library page deliberately owns no
model of its own, reading the catalog through `domain/intake.constructionOptions` and the
effective value through `domain/deliver.constructionStepWords` — the same two sources
Intake's dropdown and Deliver's picker read, so one choice cannot wear three descriptions.

WHERE CONFIRMATION LIVES IS AN OPEN CLIENT DECISION, not an accident: it is on Delivery
today, the client's five-page prose puts it on Adjustment, and their own design comp puts
its control inside the payment dialog. `docs/engagement/product-app-plan.md` §10-N records
the evidence and the recommendation. Do not move it without that ruling.

Choices are **effective**: `session.choices.X ?? case.suggested_X ?? standing default`, each
carrying `source: chosen | suggested | default` so the UI can say where a value came from.
Nothing is ever pre-filled server-side into the operator's own record — the lab chooses; the
software suggests.

---

## 7. Known limits — read before promising anything

- **One implant system per case.** Variants may differ per site; the system may not.
- **One construction part per case**, while variants are per site. When sites declare
  different variants the pipeline itself records *"single construction part shared across
  sites identifying N distinct variants — per-variant construction parts needed"*. See the
  disclosure gap in `product-app-plan.md` §10-E.
- **Relief is case-level, its ceiling is per site.** A two-variant case carries one number
  against two ceilings; the run clamps per site.
- **Sites enter only through detection**, which misses 2 of 10 sites on the current fleet.
  Manual marking is queued and is a prerequisite for real multi-cap work.
- **Nothing above N=2 sites has been measured.** Not known-broken — unmeasured.
- **`mesh_to_sdf` is pitch-dependent**: caps vanish at fine pitch. See the memory notes.
- **The occlusal proxy is not the cap axis** — measured 6.2°–42.0° off. Never substitute it.

---

## 8. Testing

Five gates; see `CLAUDE.md` for exact commands. The worker's 977 tests split by marker into
a fast lane (760) and a slow lane (217, real meshes). All lanes run parallel by default
(`-n auto --dist loadfile`); `make test-serial` is the tiebreaker when you suspect the
parallelism rather than the code.

React tests render with `renderToStaticMarkup` in the **node** environment — there is no
jsdom in this repo, by choice: these components are tested for the markup contract they
emit, and a DOM would invite testing the framework instead.
