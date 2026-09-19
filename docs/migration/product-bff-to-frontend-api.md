# Migrating product + BFF → frontend + REST API

Practical guide for moving a feature off the **live operator stack**
(`apps/product` + `apps/bff`) into the **new frontend and REST API**
projects (`apps/frontend` + `apps/api`).

This document is based on the tree as of the commit that added it. It does
**not** invent endpoints, env vars, or migration status. Where the code and
the older Phase 1 design disagree, that disagreement is named.

**Related docs (do not treat this page as a replacement):**

- [`../../CLAUDE.md`](../../CLAUDE.md) — repo map, gates, freeze line, stage keys
- [`../ARCHITECTURE.md`](../ARCHITECTURE.md) — how the *built* system is layered
- [`../engagement/product-app-plan.md`](../engagement/product-app-plan.md) — operator product plan + §10 client ledger
- [`../engagement/product-runbook.md`](../engagement/product-runbook.md) — how to run the operator app
- [`../HOWTO.md`](../HOWTO.md) — setup, run, test
- Historical Phase 1 portal design (unedited records, not operational truth):
  [`../technical-design-build-guide.md`](../technical-design-build-guide.md),
  [`../software-design-document.md`](../software-design-document.md),
  [`../implant-cad-design-document.md`](../implant-cad-design-document.md)

---

## 1. Read this first — what exists today

The four names in this migration are **not** four running apps.

| Path | What it is in the tree | Stack / ports | Status |
|---|---|---|---|
| [`apps/product`](../../apps/product) | Operator case-prep UI (worklist + five stages) | React 18 + Vite + TS, **:5174** | **ACTIVE** — all operator UI work lands here |
| [`apps/bff`](../../apps/bff) | Presentation-shaped API: sessions, gates, evidence, disclosure | FastAPI, **:8001** | **ACTIVE** — the product's only backend |
| [`apps/frontend`](../../apps/frontend) | — | — | **Does not exist.** No directory, no package, no references in the repo |
| [`apps/api`](../../apps/api) | Phase 1 portal backend placeholder | Planned NestJS | **README only** — no `package.json`, no source, no routes |

Two other apps sit next to those and must not be confused with them:

| Path | What it is | Ports | Status |
|---|---|---|---|
| [`apps/web`](../../apps/web) | Client demo UI | :5173 | **FROZEN** at `8125cbf` — never edit |
| [`apps/worker`](../../apps/worker) + [`case_prep.server`](../../apps/worker/src/case_prep/server.py) | Geometry pipeline + the demo's HTTP layer | pipeline API :8000 | Pipeline is live; `server.py` is frozen with the demo |

`packages/shared` is also a **README-only** placeholder (planned Zod/DTO package
for the portal). `packages/viewer` is a real three.js package consumed by
`apps/product`.

**Nothing has been migrated from product/BFF into frontend/API.** There is no
frontend to receive UI, and no REST API implementation to receive endpoints.
The inventory in §5 is therefore almost entirely "still on legacy" or "never
built". That is a finding, not a stall.

### Naming collision (the most expensive confusion)

Historical Phase 1 docs call the portal SPA **`apps/web`** and the privileged
backend **`apps/api`** (NestJS). After the demo shipped, `apps/web` was frozen
and the operator product was built as **`apps/product` + `apps/bff`**.

So:

- **`apps/web` is not the new frontend.** It is the frozen demo.
- **`apps/frontend` is the name this migration uses for a UI that has not been
  created.** The repo never chose that name; older docs still say `apps/web`.
- **`apps/api` is not a second BFF.** The Phase 1 design reserved NestJS for
  *privileged portal operations* (presigned S3, Stripe webhooks, operator
  cross-tenant actions). The BFF is a *presentation-shaped case-session API*
  over `case_prep.application`. Those are different jobs.

Until someone creates `apps/frontend` and implements `apps/api`, treat
product + BFF as the system of record for operator case-prep.

---

## 2. High-level architecture: old vs new

### 2.1 What is running (operator product)

```
apps/product   React + Vite + TS, :5174
      │  HTTP JSON to same-origin /api  (Vite proxies → :8001)
      │  mesh/image URLs handed to packages/viewer or <img>, not parsed in the JSON client
      ▼
apps/bff       FastAPI, :8001
      │  session store  (reports/product/<case>/session.json)
      │  status machine, evidence, pricing, disclosure gates
      │  WorkerPort.submit / status / result
      ▼
case_prep.application     framework-free callables  (cases, catalog, detection,
      │                    preview, run, emit, adjust, verify)
      ▼
case_prep.pipeline / domain / adapters     millimetres, degrees, meshes
```

The frozen demo is a parallel pair that must stay byte-identical on the freeze
line:

```
apps/web  (FROZEN)  ──▶  case_prep.server  (FROZEN FastAPI, :8000)
```

`case_prep.server` **must never be imported** outside the demo stack. An AST
test enforces this. Anything the product needs from the demo's HTTP layer was
lifted into `case_prep.application/`, not reached back into.

### 2.2 What the Phase 1 design specified (not built)

The portal design in the historical docs (SDD / TDBG / implant-cad design) is a
**different product**: multi-tenant shop intake, fulfillment queue, billing.

```
shop / operator SPA     (designed as apps/web; this migration calls the
      │                  not-yet-created home apps/frontend)
      │  most CRUD ──▶  Supabase (Auth + Postgres + RLS)
      │  privileged ──▶ apps/api  NestJS
      ▼
apps/api
      │  verify Supabase JWT against JWKS
      │  presign S3 multipart; Stripe webhooks; operator service-role
      ▼
S3 (scans) · Stripe · SQS → apps/worker  (phase-2 infra, designed not wired)
```

Designed NestJS surface (from
[`../implant-cad-system-design (1).md`](../implant-cad-system-design%20(1).md)
§10.2 — **specified, not implemented**):

```
POST /uploads/init
POST /uploads/:id/part-url
POST /uploads/:id/complete
POST /cases/:id/submit
POST /cases/:id/approve
POST /webhooks/stripe
GET  /cases/:id/download
GET  /operator/queue
POST /operator/cases/:id/{claim,qc-signoff,deliverable,price-override}
```

`docs/schema.sql` is the draft Postgres model for that portal (`cases`,
`implant_sites`, `restorations`, `case_files`, `processing_jobs`, `orders`).
It is **not** what the BFF persists. The BFF stores one JSON session per case
under `apps/worker/reports/product/<case>/session.json` and discovers scans
from `apps/worker/data/real/scans/`.

### 2.3 How the two designs meet

They share a worker and a business loop (scan in → align → attest → release /
bill). They do **not** share an HTTP contract, a data store, or an auth model.

```
                    ┌─ shop portal (designed, not built) ─┐
                    │  apps/frontend  →  apps/api (NestJS) │
                    │  + Supabase RLS + S3 + Stripe         │
                    └──────────────┬────────────────────────┘
                                   │  enqueue / status  (designed)
                                   ▼
                            apps/worker
                                   ▲
                                   │  InProcessWorker today
                    ┌──────────────┴────────────────────────┐
                    │  apps/product  →  apps/bff (FastAPI)  │
                    │  operator case-prep (BUILT, active)   │
                    └───────────────────────────────────────┘
```

A feature move has to say which of those two HTTP worlds it belongs in. Copying
a BFF route into NestJS "because both are APIs" drops the session store, the
status ladder, and the disclosure gates.

---

## 3. Responsibility map

| Concern | Today (source of truth) | Intended new home | Leave where it is |
|---|---|---|---|
| Operator worklist + five-stage UI | `apps/product` | `apps/frontend` (not created) | Frozen `apps/web` |
| Case-session HTTP, site ladder, CAS session writes | `apps/bff` | **Undecided** — see §6 | Do not reimplement inside React |
| Shop / multi-tenant portal UI | not built | `apps/frontend` | — |
| Privileged portal ops (S3 presign, Stripe, operator cross-tenant) | not built (payment is a BFF stub) | `apps/api` NestJS | — |
| Auth / identity | **none** (X-Operator removed on purpose) | Designed: Supabase Auth + NestJS JWKS | Do not restore a self-typed name header |
| Geometry, seats, channels, QC renders | `apps/worker` via `case_prep.application` | stays in the worker | Never in React or NestJS |
| 3D viewer | `packages/viewer` (product); frozen copy in `apps/web` | reuse `packages/viewer` | Do not edit `apps/web/src/viewer` |
| Shared TS contracts | hand-mirrored in `apps/product/src/api/client.ts` | `packages/shared` (placeholder) | — |
| Immutable run dirs | `apps/worker/reports/product/<case>/runs/<run_id>/` | same data plane until a store is chosen | Never mutate a landed run |
| Demo pipeline HTTP | `case_prep.server` | nowhere — frozen | — |

### What each live app owns

**`apps/product`** — presentational only. Routes, stage chrome, viewer
hosting, and *display* rules (reachability, copy, chip labels). It never
computes a millimetre, a verdict, a price, or a status. Network I/O is
centralized in `src/api/client.ts`.

**`apps/bff`** — aggregation, session persistence, the status machine,
evidence hashing, the rate card, and the disclosure edge (evidence ungated;
deliverable bytes gated on confirmation + payment). It owns **no physics**.
Its only doorway to the worker is `bff/ports/worker.py` (`WorkerPort`).

**`apps/worker` / `case_prep.application`** — detect, preview, run, emit,
adjust, catalog, case discovery. Framework-free functions. This is the seam
any new API must keep calling.

**`apps/api` (as designed)** — privileged operations RLS must not do. Not a
replacement for the BFF's case-session resource, unless a later decision
explicitly says so.

**`apps/frontend` (as this migration names it)** — the new UI host. Until the
directory exists, new operator screens still land in `apps/product`.

---

## 4. What each live app is responsible for (entrypoints and modules)

### 4.1 `apps/product` — operator UI

| | |
|---|---|
| Entrypoint | [`apps/product/src/main.tsx`](../../apps/product/src/main.tsx) |
| Dev server | `cd apps/product && pnpm dev` → http://localhost:5174 |
| Proxy | [`vite.config.ts`](../../apps/product/vite.config.ts): `/api` and `/health` → `http://localhost:8001` |
| Env | **none.** No `VITE_*` / `import.meta.env` usage. The UI talks to its own origin. |
| Auth | **none.** |

Routes:

| Path | Page | Role |
|---|---|---|
| `/` | `pages/Worklist.tsx` | Case cards; upload drop zone; demo reset |
| `/case/:id` | `pages/CaseShell.tsx` | Resume at `furthestStage` |
| `/case/:id/:stage` | `pages/CaseShell.tsx` | Stage body; URL cannot outrun reachability |
| `/terms`, `/terms/:version` | `pages/TermsPage.tsx` | Case-independent terms document |
| (in-flow dialog) | `pages/CheckoutPage.tsx` | **Mock** hosted checkout — read-only fake cards |

Stage keys vs rail titles (keys are load-bearing; do not rename them to match
the titles):

| URL / `StageId` | Rail title | Component |
|---|---|---|
| `intake` | Intake | `components/IntakeStage.tsx` |
| `declare` | Alignment | `components/DeclareStage.tsx` |
| `adjust` | Adjustment | `components/AdjustStage.tsx` |
| `library` | Construction library | `components/LibraryStage.tsx` |
| `deliver` | Delivery | `components/DeliverStage.tsx` |

Display-only domain modules (framework-free; they project BFF payloads, they
do not invent facts):

`domain/flow.ts` · `intake.ts` · `declare.ts` · `adjust.ts` · `deliver.ts` ·
`worklist.ts` · `workspace.ts` · `provenance.ts` · `dialog.ts`

Single network module: [`src/api/client.ts`](../../apps/product/src/api/client.ts).
Types are **hand-mirrored** from BFF pydantic models (snake_case on the wire).
Every call returns `ApiResult<T>` — never a thrown fetch.

### 4.2 `apps/bff` — operator API

| | |
|---|---|
| Entrypoint | [`apps/bff/src/bff/main.py`](../../apps/bff/src/bff/main.py) (`create_app` / `app`) |
| Dev server | `cd apps/bff && ../worker/.venv/bin/uvicorn bff.main:app --port 8001 --app-dir src --reload --reload-dir src --reload-dir ../worker/src/case_prep/application` |
| Env | **none locally.** [`config.py`](../../apps/bff/src/bff/config.py) derives `data_root` and `product_root` from the file's position in the repo. Tests inject `Settings`. |
| Auth | **none.** `X-Operator` is ignored if sent. |
| Install | Into the **worker venv** (`pip install -e apps/bff`). There is no `apps/bff/.venv`. |

Mounted routers (all under `/api` except `/health`):

| Module | Prefix | Owns |
|---|---|---|
| `resources/case_sessions.py` | `/api/case-sessions` | Worklist, detail, scan stream, detect, choices, system, sites, preview, review, withhold, acknowledge, run, adjust-decision |
| `resources/adjust.py` | `/api/case-sessions` | seated, landmarks, re-preview, rotation, mark-trench, fit-by-points, best-fit |
| `resources/deliver.py` | `/api/case-sessions` | assurance, invoice, confirm, payment, release, artifacts, QC, preview-mesh, resets |
| `resources/deliver.py` | `/api/terms` | Versioned terms documents |
| `resources/activity.py` | `/api/case-sessions` | GET-only activity window |
| `resources/library.py` | `/api/library`, `/api/constructions` | Canonical cap mesh/PNG, construction STL |
| `resources/uploads.py` | `/api/uploads` | Raw STL write into `data_root/scans/<folder>/<file>.stl` |

Supporting modules: `session.py` (CAS JSON store), `status.py` (pure ladder),
`evidence.py` (content-addressed bundle), `pricing.py` (integer-cent rate card),
`ports/worker.py` (`InProcessWorker` today; job-shaped for a future SQS adapter).

Health: `GET /health` → `{"ok": true, "service": "bff"}`.

### 4.3 `apps/api` — planned NestJS REST API

[`apps/api/README.md`](../../apps/api/README.md) is the entire implementation:

> Privileged operations only: presigned S3 multipart URLs, job-state writes,
> Stripe webhooks, operator cross-tenant actions (service role). **Staged
> placeholder.**

There is no OpenAPI spec in-repo for this app. The designed routes are listed
in §2.2. Do not document additional NestJS routes as if they existed.

### 4.4 `apps/frontend` — planned new UI

Absent. When created, the closest in-repo patterns to copy (and record on the
copy-debt ledger if the copy is from the demo or the product) are:

- Operator chrome, stages, and BFF client: `apps/product`
- Viewer: `packages/viewer`
- Portal stack *as designed* (not present): Vite SPA, `@supabase/supabase-js`,
  TanStack Query, `react-hook-form`, `zod` — see TDBG D1–D4

---

## 5. Feature inventory and migration status

Statuses used below:

| Status | Meaning |
|---|---|
| **still on legacy** | Implemented on product + BFF; no frontend/API counterpart |
| **not started** | Designed in historical portal docs; no implementation in any app |
| **partial / stub** | A stand-in exists on the legacy stack; the designed replacement is unbuilt |
| **stays in worker** | Must not move into a UI or NestJS process |
| **unknown** | Code and design do not decide the destination |

| Feature area | Legacy home | New home (if any) | Status |
|---|---|---|---|
| Worklist | `pages/Worklist.tsx` · `GET /api/case-sessions` | frontend, same contract or a portal queue | still on legacy |
| Case shell / stage rail | `pages/CaseShell.tsx` · `domain/flow.ts` | frontend | still on legacy |
| Intake: auto-detect, choices, capture banners | `IntakeStage` · `POST …/detect` · `PUT …/choices` | frontend + whoever owns case-session HTTP | still on legacy |
| Browser STL upload | `uploadScan` · `POST /api/uploads/scans/{folder}/{file}.stl` | designed: NestJS multipart + S3 | **partial / stub** — local FS write, 256 MB cap, no auth |
| Manual mark / re-mark / rim points | `POST …/sites`, `PUT …/mark`, `PUT/DELETE …/rim-points` | frontend + case-session API | still on legacy |
| Alignment (declare system/variant, preview, review tick) | `DeclareStage` · `PUT …/system` · `PUT …/declaration` · `POST …/preview` · `POST/DELETE …/review` | frontend + case-session API | still on legacy |
| Adjustment tools (rotation, mark-trench, fit-by-points, best-fit, landmarks, re-preview) | `AdjustStage` · `resources/adjust.py` | frontend + case-session API | still on legacy |
| Per-site relief + re-emit | `PUT …/sites/{tooth}/relief` · `application/emit.py` | frontend + case-session API | still on legacy |
| Construction library + part preview | `LibraryStage` · `GET /api/library/…` · `GET /api/constructions/…` | frontend + catalog mesh routes | still on legacy |
| Delivery: assurance, confirm, release, artifacts | `DeliverStage` · `resources/deliver.py` | frontend + disclosure API | still on legacy |
| Invoice / rate card | `GET …/invoice` · `bff/pricing.py` | unknown vs Stripe | still on legacy (card is client-confirmed; provider is stub) |
| Payment | `CheckoutPage` (mock cards) · `POST …/payment` `{authorize: true}` | designed: Stripe via NestJS | **partial / stub** — `provider: "stub"` on purpose |
| Terms | `GET /api/terms` · placeholder text `placeholder-v2` | frontend + versioned document | still on legacy; real client text not in repo |
| Activity log | `GET …/activity` (server-appended only) | frontend read | still on legacy |
| 3D viewer / mesh crop | `packages/viewer` | reuse from frontend | still on legacy (product consumer); **not** a BFF move |
| Detection / seat / run / emit physics | `case_prep.application` + pipeline | stays in worker | stays in worker |
| Session store + status ladder + evidence hash | `bff/session.py`, `status.py`, `evidence.py` | **unknown** — see §6 | still on legacy |
| Operator authentication | removed (`X-Operator` retired) | designed Supabase + JWKS | **not started** |
| Shop tenancy / RLS | `session.tenant_id = "local"` | designed `docs/schema.sql` + RLS | **not started** |
| Shop case submission portal | — | frontend + api + schema.sql | **not started** |
| Presigned S3 multipart | — | `apps/api` as designed | **not started** |
| Stripe webhooks / paid download | — | `apps/api` as designed | **not started** |
| SQS / Fargate worker adapter | `InProcessWorker` only | `bff/ports/worker.py` *or* NestJS enqueue | **not started** (IaC exists under `infrastructure/`, not wired to BFF) |
| Shared Zod/DTO package | product `api/client.ts` mirrors | `packages/shared` | **not started** |
| Frozen demo (select case → detect → run → export) | `apps/web` + `case_prep.server` | nowhere | **do not migrate** — freeze line |

---

## 6. Contracts that must survive a move

These are load-bearing. A new frontend or API that drops them is a rewrite, not
a migration.

### 6.1 Trust: facts are derived server-side

Statuses, verdicts, gates, invoice totals, and "released" are computed on the
server. The product never PATCHes a site to `ready`. The enforcing test is
[`apps/bff/tests/test_case_sessions.py::TestStatusesAreNeverClientWritable`](../../apps/bff/tests/test_case_sessions.py).
Any new write API needs the same allowlist: **no request model may carry a
status-shaped field.**

The site ladder lives in [`bff/status.py`](../../apps/bff/src/bff/status.py):

```
detected → declared → previewed → ready | flagged → adjusted → ready
```

Illegal jumps raise `IllegalTransition`. Reset boundaries (`declare`,
`invalidate_preview`, `regress_to_detected`) are named events, not field wipes
in the browser.

### 6.2 Session writes are compare-and-swap

Every session document has `version`. `save` raises `SessionConflict` → HTTP
409. Handlers retry once. Cross-process CAS is called out as a later
SQLite/phase-2 concern — it is **not** implemented.

### 6.3 Evidence and disclosure

- **Evidence** (assurance table, QC images, in-app preview meshes, invoice) is
  **ungated** — the operator must see it before signing.
- **Deliverable bytes** (package STLs) disclose only behind a still-valid
  confirmation **and** `payment_authorized`.
- Release **re-derives** the evidence bundle and **409s on hash drift**.

Do not put download links in the SPA that bypass that gate.

### 6.4 Amounts are never client-writable

`POST …/payment` accepts `{authorize: true, invoice_fingerprint?}`. It does not
accept an amount. The server re-prices at authorization time; a fingerprint
mismatch is 409 ("the price moved since you read it").

### 6.5 Auth (as built vs as designed)

**As built:** no login. The client explicitly removed `X-Operator` — a
self-typed name was not identity. Records stand on the *act* (`at`, run id,
evidence hash). Product comment: real identity arrives with real auth
(plan §8 / phase-2).

**As designed (portal):** Supabase Auth; NestJS verifies the JWT against JWKS;
shop clients use RLS; the operator never gets a client-side cross-tenant
bypass — operator actions go through NestJS with the service role and an audit
row.

**As designed then changed (operator product plan §3 Deliver):** the grilled
plan said the BFF authenticates the operator before Deliver and stamps an
actor on confirmation/release. The later client direction removed the name
field. A new auth system should stamp a *verified* identity; it should not
bring back an unauthenticated header.

### 6.6 Routing and data fetching (product conventions)

- Route: `/case/:id/:stage` with `StageId` keys. `resolveStagePath` in
  `domain/flow.ts` is the one guard.
- Fetch: `fetchJson` → `ApiResult<T>`. Components hold `FetchState<T>`
  (`loading` \| `ok` \| `error`). A down BFF is a banner, not a blank screen.
- Meshes and QC images are **URLs**, not JSON. The viewer / `<img>` loads them.
- Action responses return the **whole** `CaseSessionDetail`. The shell replaces
  the payload verbatim (no client-side patch of statuses).
- Wire field names are snake_case, mirrored in TypeScript. New fields on
  response types are often optional (`?:`) so older fixtures compile; a field
  the server may omit for real is `| null`.

### 6.7 Domain models (do not fork casually)

| Model | Home | Notes |
|---|---|---|
| `StageId` / reachability | `product/src/domain/flow.ts` | Display only; never sent to the server |
| `CaseSession` / `SiteSession` | `bff/session.py` | Persisted JSON; source of site rungs, choices, confirmation, payment, release |
| `CaseSessionDetail` / `WorklistRow` | `bff/resources/case_sessions.py` + `product/src/api/client.ts` | The wire contract the UI is written against |
| `JobState` | `bff/ports/worker.py` | `queued \| running \| done \| refused \| failed` — job-shaped for SQS later |
| `CaseRecord` | `case_prep.application.cases` | Discovery from the scan tree |
| Portal `cases` / `orders` | `docs/schema.sql` | Designed, unused by BFF |

Effective choices are `chosen ?? scan ?? suggested ?? default`, composed
**server-side**, with a `source` tag the UI renders. The browser does not
decide completeness.

### 6.8 Open architectural decision (do not paper over)

The repo does **not** say whether `apps/api` replaces `apps/bff` or sits beside
it.

Facts that constrain the choice:

1. NestJS cannot import `case_prep.application` (Python). A NestJS
   reimplementation of detect/preview/run/adjust would have to shell out,
   HTTP-call the BFF, or enqueue the worker.
2. `WorkerPort` is already the intended swap point for SQS
   ([`ports/worker.py`](../../apps/bff/src/bff/ports/worker.py)).
3. Phase 1 NestJS was specified as *privileged ops only*, with CRUD on
   Supabase — not as a case-session BFF.
4. `tenant_id` is already a field on the BFF session (`"local"`).

Until that decision is written down, the safe migration is:

- **Portal / commercial / tenancy / Stripe / S3** → new `apps/api` + `apps/frontend`
- **Operator case-prep HTTP** → keep `apps/bff` (frontend may call it) **or**
  proxy it
- **Physics** → `case_prep.application` only

---

## 7. Migration guide — moving one feature end-to-end

Work **one feature** at a time. Do not start a second copy of a test gate
already running. Tests first, same as the rest of this repo.

### Step 0 — Classify the feature

Ask which world it belongs to:

| If the feature… | It belongs in… |
|---|---|
| Computes mm / degrees / a mesh / a gate | `case_prep.application` (or below). Not frontend, not NestJS. |
| Is a shop submitting a case, paying, or downloading a paid zip | `apps/frontend` + `apps/api` (as designed) |
| Is an operator walking Intake → Delivery on a scan | `apps/product` today; `apps/frontend` later; HTTP stays BFF-shaped unless §6.8 is decided |
| Is identity, tenancy, or audit of *who* | Designed for Supabase + NestJS; nothing to copy from product except the lesson that a typed name is not auth |

If you cannot classify it, stop and write the decision. Do not "just add a
route to both."

### Step 1 — Inventory the legacy seam (before writing files)

For an operator feature, collect:

1. **UI** — page/component under `apps/product/src/` and the domain helpers it
   imports.
2. **Client** — the function(s) in `api/client.ts` (path, method, body, return
   type).
3. **BFF route** — handler in `resources/*.py`, request model, status codes
   (422 sentence, 409 conflict/drift, 404).
4. **Session mutations** — which `ACT_*` and which `status.py` event fire.
5. **Worker call** — `application.*` function, if any. Preview/run/adjust
   never live in the HTTP layer.
6. **Tests** — product `*.test.tsx` / `domain/*.test.ts` and the matching
   `apps/bff/tests/test_*.py`. Those tests *are* the contract.

For a portal feature, the seam is the historical design + `docs/schema.sql` +
`apps/api/README.md`. There is no legacy implementation to port — you are
building it for the first time. The BFF upload and payment stub are the
behaviors you will **retire**, not copy.

### Step 2 — Land the new API contract (if the feature needs one)

**If the HTTP stays on the BFF** (likely for case-prep until §6.8 is decided):

- Add or extend the FastAPI resource. Keep `extra=forbid` pydantic models.
- Derive facts in the handler / session store. Do not accept them from the
  client.
- Return the whole detail document after a write, same as existing actions.
- Add the allowlist row if you introduce a new non-GET route
  (`TestStatusesAreNeverClientWritable`).
- Call `case_prep.application`, never `case_prep.server`.

**If the HTTP is a new NestJS privileged op:**

- Create the NestJS app (it does not exist yet): package, module layout, JWKS
  middleware as specified in TDBG D4.
- Implement only the privileged surface in §2.2 (or a documented increment).
- Put shared request/response types in `packages/shared` once that package
  exists. Do not start a third hand-rolled mirror if you can avoid it.
- Do not re-derive alignment numbers in TypeScript.

**If frontend should call the existing BFF** from a new app: keep the Vite
proxy pattern (`/api` → `:8001`) so the UI still has no hardcoded backend
host. Path prefix `/api/case-sessions` is the product contract; do not
silently rename it on one side.

### Step 3 — Land the UI in the new frontend

`apps/frontend` must exist first (workspace package, Vite, TS). Then:

1. Prefer **moving** product modules over rewriting them. The expensive rules
   are in `domain/*.ts` and `api/client.ts`, not in the JSX.
2. Keep display logic out of the fetch layer (`flow.ts` is the model).
3. Reuse `packages/viewer`. Do not copy `apps/web/src/viewer` (freeze + the
   9 mm vs 11 mm crop band is intentional).
4. If you copy from `apps/web` or from product into frontend, add a row to
   [`../engagement/copy-debt-ledger.md`](../engagement/copy-debt-ledger.md)
   **in the same commit**.
5. Tests: this repo's product tests use `renderToStaticMarkup` in **node**
   (no jsdom contract). Match that unless the new app deliberately adopts a
   different test stack — and say so.
6. Typecheck the **app** tsconfig, not a references shell. Product's trap:
   `tsconfig.json` has `"files": []`; the real check is
   `tsc --noEmit -p tsconfig.app.json`.

### Step 4 — Wire config

There is **no** env file for product or BFF today.

| Layer | How it finds things |
|---|---|
| Product | Vite proxy; relative `/api/…` |
| BFF | `Settings.data_root` = `apps/worker/data/real`, `product_root` = `apps/worker/reports/product` |
| Planned NestJS | Not present. Design implies Supabase URL/keys, S3, Stripe secrets — none are in this repo's app config |
| Planned frontend | Not present. Design implies `VITE_` Supabase publishable keys — none exist |

When you add env, put a sample in the new app and link it from this section.
Do not assume `apps/bff` will start reading `os.environ` — it currently does
not.

### Step 5 — Retire the legacy path

A path is retired only when:

1. The new UI is the only operator-facing entry (or the portal is the only
   shop-facing entry).
2. The new API is covered by tests that encode the same refusals (422/409)
   the BFF already pins, *or* the BFF route remains the implementation and
   the old UI is deleted.
3. No product route/component still calls the old helper.
4. The freeze line is still clean:

   ```bash
   git diff --stat 8125cbf -- apps/web apps/worker/src/case_prep/server.py apps/worker/tools
   ```

Do **not** delete BFF routes because a NestJS stub exists. Do **not** edit
`apps/web` as part of a migration.

Suggested retire order once frontend + api actually exist:

1. Auth / identity (nothing to retire in product except remaining "no actor"
   comments).
2. Real Stripe checkout → then delete `CheckoutPage` mock + stop treating
   `provider: "stub"` as a shipping payment.
3. S3 multipart upload → then stop writing STLs through
   `POST /api/uploads/scans/…` (or keep that route as a local-dev adapter).
4. Operator screens, one stage at a time, only after the BFF (or its
   successor) still serves that stage's contract.
5. Leave worker + `case_prep.application` in place throughout.

### Step 6 — Gates for the slice you touched

Narrowest failing tests first ([`../../CLAUDE.md`](../../CLAUDE.md)):

```bash
# BFF, shares the worker venv
cd apps/bff && ../worker/.venv/bin/pytest -q tests/test_<area>.py

# Product UI / domain
npm test --prefix apps/product

# If the slice touched physics
cd apps/worker && .venv/bin/pytest -q tests/test_<area>.py
```

Full `make test` / product+viewer+web batteries are the shipping gate, not
the inner loop. When `apps/frontend` and `apps/api` have tests, add them to
the README table — they are not gates today.

---

## 8. Conventions for the new apps (inferred; mark what is prescribed vs guessed)

Prescribed by existing code or design docs:

| Topic | Convention | Source |
|---|---|---|
| Monorepo | pnpm workspaces `apps/*`, `packages/*`; turbo task names `build` / `test` / `lint` / `typecheck` | root `package.json`, `pnpm-workspace.yaml`, `turbo.json` |
| Product folder layout | `src/pages`, `src/components`, `src/domain`, `src/api` | `apps/product` |
| BFF folder layout | `src/bff/resources`, `ports`, `session` / `status` / `evidence` / `pricing` | `apps/bff` |
| Wire names | snake_case JSON; TS interfaces match the wire | `api/client.ts` |
| Pydantic | `extra=forbid`, `from __future__ import annotations` | BFF + worker |
| Viewer crop band | **11 mm** in `packages/viewer`; **9 mm** in frozen `apps/web` | `CLAUDE.md` |
| Copy from demo | ledger row in the same commit | `docs/engagement/copy-debt-ledger.md` |
| NestJS role | privileged ops only, JWKS verify | `apps/api/README.md`, TDBG D4–D5 |
| Shared types | `packages/shared` Zod schemas (when built) | `packages/shared/README.md` |

Not prescribed (do not pretend the repo decided these):

- Whether `apps/frontend` is one SPA or shop + operator two apps
- Whether frontend uses TanStack Query (designed) or product's hand-rolled
  `FetchState`
- OpenAPI codegen vs continued hand mirrors
- NestJS port number
- How NestJS locates the worker / BFF

When you decide one of those, write it here in the same PR as the code.

### How the frontend should call the REST API (today vs later)

**Today (product → BFF):**

```ts
// relative URL; Vite proxies /api → localhost:8001
const result = await fetchJson<CaseSessionDetail>(
  `/api/case-sessions/${encodeURIComponent(caseId)}`,
);
```

**Later (frontend → BFF still):** same relative `/api` proxy. Do not hard-code
`localhost:8001`.

**Later (frontend → NestJS):** no client code exists. The design expects a
Supabase session JWT on privileged routes and *direct* Supabase access for
tenant-scoped CRUD. That is incompatible with "all traffic through `/api`"
until someone chooses one. Record the choice when the first frontend fetch
lands.

---

## 9. Key source paths

### Operator UI (`apps/product`)

| Path | Why jump here |
|---|---|
| [`apps/product/src/main.tsx`](../../apps/product/src/main.tsx) | Route table |
| [`apps/product/src/api/client.ts`](../../apps/product/src/api/client.ts) | Entire BFF TypeScript contract + fetch helpers |
| [`apps/product/src/domain/flow.ts`](../../apps/product/src/domain/flow.ts) | Stages, reachability, resume |
| [`apps/product/src/pages/CaseShell.tsx`](../../apps/product/src/pages/CaseShell.tsx) | Case load + stage switch |
| [`apps/product/src/pages/Worklist.tsx`](../../apps/product/src/pages/Worklist.tsx) | Home + upload |
| [`apps/product/src/pages/CheckoutPage.tsx`](../../apps/product/src/pages/CheckoutPage.tsx) | Mock checkout (Stripe stand-in) |
| [`apps/product/vite.config.ts`](../../apps/product/vite.config.ts) | Dev proxy |

### Operator API (`apps/bff`)

| Path | Why jump here |
|---|---|
| [`apps/bff/src/bff/main.py`](../../apps/bff/src/bff/main.py) | App factory, router mount order |
| [`apps/bff/src/bff/config.py`](../../apps/bff/src/bff/config.py) | `data_root` / `product_root` |
| [`apps/bff/src/bff/session.py`](../../apps/bff/src/bff/session.py) | Session document, CAS, activity |
| [`apps/bff/src/bff/status.py`](../../apps/bff/src/bff/status.py) | Site ladder |
| [`apps/bff/src/bff/evidence.py`](../../apps/bff/src/bff/evidence.py) | Canonical bundle + SHA-256 |
| [`apps/bff/src/bff/pricing.py`](../../apps/bff/src/bff/pricing.py) | Rate card (integer cents) |
| [`apps/bff/src/bff/ports/worker.py`](../../apps/bff/src/bff/ports/worker.py) | Job port + in-process adapter |
| [`apps/bff/src/bff/resources/case_sessions.py`](../../apps/bff/src/bff/resources/case_sessions.py) | Worklist + most operator acts |
| [`apps/bff/src/bff/resources/adjust.py`](../../apps/bff/src/bff/resources/adjust.py) | Rework tools |
| [`apps/bff/src/bff/resources/deliver.py`](../../apps/bff/src/bff/resources/deliver.py) | Disclosure + payment stub + terms |
| [`apps/bff/src/bff/resources/uploads.py`](../../apps/bff/src/bff/resources/uploads.py) | Local STL upload policy |
| [`apps/bff/src/bff/resources/library.py`](../../apps/bff/src/bff/resources/library.py) | Catalog meshes |
| [`apps/bff/src/bff/resources/activity.py`](../../apps/bff/src/bff/resources/activity.py) | Narrative read model |
| [`apps/bff/tests/test_case_sessions.py`](../../apps/bff/tests/test_case_sessions.py) | Status-not-writable + route corpus |

### Worker seam (keep calling this)

| Path | Why jump here |
|---|---|
| [`apps/worker/src/case_prep/application/`](../../apps/worker/src/case_prep/application/) | BFF-facing callables |
| [`application/cases.py`](../../apps/worker/src/case_prep/application/cases.py) | `discover_cases` |
| [`application/detection.py`](../../apps/worker/src/case_prep/application/detection.py) | Detect |
| [`application/preview.py`](../../apps/worker/src/case_prep/application/preview.py) | Preview seat + pane payload |
| [`application/run.py`](../../apps/worker/src/case_prep/application/run.py) | Authorized full run |
| [`application/emit.py`](../../apps/worker/src/case_prep/application/emit.py) | Re-emit from poses (`mode: "reemit"`) |
| [`application/adjust.py`](../../apps/worker/src/case_prep/application/adjust.py) | Tool physics |
| [`application/catalog.py`](../../apps/worker/src/case_prep/application/catalog.py) | Library / construction membership |

### New / placeholder / frozen

| Path | Why jump here |
|---|---|
| [`apps/api/README.md`](../../apps/api/README.md) | Entire NestJS app, as of this writing |
| [`packages/shared/README.md`](../../packages/shared/README.md) | Entire shared DTO package, as of this writing |
| [`docs/schema.sql`](../schema.sql) | Designed portal schema (unused by BFF) |
| [`packages/viewer/src/`](../../packages/viewer/src/) | Product 3D viewer |
| [`apps/web/src/App.tsx`](../../apps/web/src/App.tsx) | Frozen demo entry — do not migrate from here without a ledger row |

### BFF HTTP cheat sheet (implemented)

Full list of product-facing routes. Bodies and fields: see `api/client.ts`
and the resource modules. This is the contract a frontend can call **today**.

```
GET    /health
GET    /api/terms
GET    /api/terms/{version}
GET    /api/library/{model}/{variant}/mesh
GET    /api/library/{model}/{variant}/top.png
GET    /api/constructions/{vendor}/{filename}/mesh
POST   /api/uploads/scans/{folder}/{filename}

GET    /api/case-sessions
GET    /api/case-sessions/{id}
GET    /api/case-sessions/{id}/scan
GET    /api/case-sessions/{id}/run
GET    /api/case-sessions/{id}/activity
GET    /api/case-sessions/{id}/assurance
GET    /api/case-sessions/{id}/invoice
GET    /api/case-sessions/{id}/sites/{tooth}/seated
GET    /api/case-sessions/{id}/sites/{tooth}/landmarks
GET    /api/case-sessions/{id}/sites/{tooth}/acceptance
GET    /api/case-sessions/{id}/runs/current/qc/{filename}
GET    /api/case-sessions/{id}/runs/current/preview-mesh/{filename}
GET    /api/case-sessions/{id}/runs/current/artifacts
GET    /api/case-sessions/{id}/runs/current/artifacts/{filename}

POST   /api/case-sessions/{id}/detect
PUT    /api/case-sessions/{id}/choices
PUT    /api/case-sessions/{id}/system
POST   /api/case-sessions/{id}/sites
POST   /api/case-sessions/{id}/run
POST   /api/case-sessions/{id}/adjust-decision
POST   /api/case-sessions/{id}/confirm
POST   /api/case-sessions/{id}/payment
POST   /api/case-sessions/{id}/release
POST   /api/case-sessions/{id}/checkout/return
POST   /api/case-sessions/{id}/reset
POST   /api/case-sessions/{id}/delivery/reset

PUT    /api/case-sessions/{id}/sites/{tooth}/declaration
PUT    /api/case-sessions/{id}/sites/{tooth}/mark
PUT    /api/case-sessions/{id}/sites/{tooth}/rim-points
DELETE /api/case-sessions/{id}/sites/{tooth}/rim-points
PUT    /api/case-sessions/{id}/sites/{tooth}/relief
PUT    /api/case-sessions/{id}/sites/{tooth}/withhold
POST   /api/case-sessions/{id}/sites/{tooth}/preview
POST   /api/case-sessions/{id}/sites/{tooth}/review
DELETE /api/case-sessions/{id}/sites/{tooth}/review
POST   /api/case-sessions/{id}/sites/{tooth}/acknowledge
DELETE /api/case-sessions/{id}/sites/{tooth}/acknowledge
POST   /api/case-sessions/{id}/sites/{tooth}/re-preview
POST   /api/case-sessions/{id}/sites/{tooth}/rotation
POST   /api/case-sessions/{id}/sites/{tooth}/mark-trench
POST   /api/case-sessions/{id}/sites/{tooth}/fit-by-points
POST   /api/case-sessions/{id}/sites/{tooth}/best-fit
```

There is no implemented NestJS cheat sheet. Do not add one until routes exist
in `apps/api`.

---

## 10. Gaps this document cannot close from the code

These are honest unknowns. Do not fill them in with guesses in a later edit
unless the code or an explicit decision landed.

1. **`apps/frontend` was never created**, and no doc in this repo uses that
   path. This migration *assigns* the name so engineers have a destination;
   a later rename (or a decision to keep extending `apps/product`) is possible.
2. **Whether NestJS replaces the BFF** for operator case-prep is unset (§6.8).
3. **Auth provider is unimplemented.** Design says Supabase; product/BFF have
   zero auth code and no env keys.
4. **Portal schema vs session JSON.** `docs/schema.sql` and
   `reports/product/.../session.json` have not been mapped field-for-field.
   Phase-2 infra grilling already notes `tenant_id` / `processing_jobs.stage`
   are not in the shipped schema.
5. **Payment:** BFF stub + mock checkout vs designed Stripe Checkout /
   PaymentIntent. How an invoice fingerprint becomes a PaymentIntent amount
   is unspecified.
6. **Upload:** local scan-tree write vs designed S3 multipart. How
   `discover_cases` learns about an S3 object is unspecified.
7. **Actor on confirmation/release:** plan said stamp an operator; client
   removed the name. Verified auth will have to decide the record shape again.
8. **Confirmation placement** is still an open client decision (plan §10-N):
   Delivery today, Adjustment in one prose draft, payment dialog in a comp.
   Do not move it as part of a mechanical migration.
9. **IaC** under `infrastructure/` provisions worker/SQS/S3 pieces of the
   phase-2 plan; it does not provision NestJS, Supabase, or a frontend host,
   and the BFF does not call SQS.

When a decision lands, add a dated note under this section (or a row in
product-app-plan §10) and update the inventory table.
