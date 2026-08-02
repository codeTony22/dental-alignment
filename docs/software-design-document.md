# Software Design Document — Implant CAD Portal & Automation

> ## 📜 HISTORICAL RECORD — not the operational truth
>
> This document predates the operator product app (`apps/product` + `apps/bff`) and the
> client's five-stage flow. It is kept **unedited** as a record of what was designed and
> why; do not treat any command, path, count or flow description in it as current.
>
> For what is true today:
> - **[`../CLAUDE.md`](../CLAUDE.md)** — the repo map: the five gates, the freeze line, the
>   stage model, and the traps.
> - **[`ARCHITECTURE.md`](ARCHITECTURE.md)** — how the system fits together as built.
> - **[`engagement/product-app-plan.md`](engagement/product-app-plan.md)** — the product
>   plan, and §10 for the record of client direction as it arrived.
> - **[`engagement/product-runbook.md`](engagement/product-runbook.md)** — how to run and
>   demo the product app.
> **Specifically superseded:** the scope and phasing here were the engagement's
> opening position. The built system's shape is in `ARCHITECTURE.md`.

**Prepared by:** [Engineer]  **For:** [Client]
**Engagement:** Build a doctor-facing portal and/or an automation pipeline for a client who owns RealGUIDE, produces implant CAD design files, and already serves dental-shop customers.

> **Framing note.** This is a software engineering scope document, not a business plan. The client already owns the operation, the RealGUIDE license, the customer relationships, and the clinical/regulatory responsibility. Market demand, customer acquisition, and clinical sign-off are **the client's domain and out of scope for this engagement.** The software's job is to (1) make the client's intake/delivery/billing efficient and scalable and (2) reduce the manual time per case. Where the software touches regulated territory, it *supports* the client's compliance (audit trail, QC step) but does not assume the client's regulatory responsibility.

---

## 1. What is being built

Two separable products. They can be delivered independently and billed separately.

- **Product A — Portal.** Wraps the client's *existing manual workflow*. Dental shops submit cases and scans through a web app instead of email/file-transfer; the client tracks and fulfills them (still using RealGUIDE); deliverables and payment flow back through the portal. Low technical risk, immediate operational value.
- **Product B — Automation.** Reduces the client's per-case manual time by automating the mechanical/geometric steps around the design. Higher risk, scale-dependent payoff, and constrained by RealGUIDE being a closed application (§3).

**Recommended order: Product A first.** It delivers standalone value, is low-risk, funds and justifies Product B, and produces the case history that later informs automation priorities.

---

## 2. The single most important technical constraint: RealGUIDE is closed

RealGUIDE exposes **macros and a GUI — no public API or SDK.** You cannot reliably drive it headlessly or script it at scale; UI automation is brittle, breaks on updates, and likely violates the license. This has hard consequences for the automation design:

**You cannot automate *through* RealGUIDE. You can only automate *around* it.** Two viable patterns:

- **Pattern 1 — Augment (recommended first).** Build automated pre-processing in open tools that produces cleaned, aligned, validated inputs which the client then **imports into RealGUIDE** (RealGUIDE imports STL/DICOM). The client's manual time drops because the fiddly preparation is already done. RealGUIDE stays in the loop; nothing brittle.
- **Pattern 2 — Replace (selective, later).** For simple, high-volume case types, build a full open-tool pipeline (Blender + CloudCompare + custom code) that produces the design **without RealGUIDE at all**. This only works for the geometric parts — crown morphology remains a human/licensed-engine step (§5, hard wall).

**Do not design any automation that assumes programmatic control of RealGUIDE.** That is the most common way a project like this fails. Set this expectation with the client explicitly and in writing.

---

## 3. Product A — Portal: software design

### 3.1 Stack
| Layer | Choice | Why |
|------|--------|-----|
| Frontend | React (Vite SPA) | Standard; client decision |
| Auth + DB | Supabase (Auth + Postgres + Row-Level Security) | Collapses auth, database, and per-tenant isolation into one platform; RLS is most of the security model as a few policies |
| File storage | **S3** (private bucket) | Scan files are large (20–100 MB STL); keep them co-located with any future processing compute to avoid cross-cloud egress |
| Backend | NestJS (serverless) | Privileged operations only: presigned upload/download URLs, job-state writes, Stripe webhooks |
| Payments | Stripe | Per-case gated download or account billing |

With RLS doing authorization, the React client talks to Supabase directly for most reads/writes; NestJS is reserved for the privileged moves. Less backend than it first appears.

### 3.2 Tenancy model (important change from a single-doctor portal)
There are **two roles**, not one:
- **Shop users** — the client's dental-shop customers, each an isolated tenant. They see only their own cases.
- **Operator (the client)** — the business owner/admin. Sees and manages **all** cases across all shops; runs the fulfillment queue; uploads deliverables; controls pricing.

Concretely: add a `role` to the `profiles` table (`'shop' | 'operator'`) and a tenant/organization key on `cases`. RLS gives shop users owner-scoped access; an additional policy grants the operator role read/write across all cases. (This is the one substantive change to the previously drafted `schema.sql` — everything else in that schema carries over.)

### 3.3 Data model
Use the previously delivered `schema.sql` as the base. It models, PII-free:
- `cases` — one per restoration job, referenced by the shop's own opaque label (no patient identity).
- `implant_sites` — one row per implant (e.g. 23, 24, 26, 28) capturing the exact fields the client specifies in RealGUIDE: implant system (e.g. "DG code lite for zimmer and Bio"), implant code (e.g. "zimmer 3.5 dg code 5020"), scan-body type (e.g. "atlantic scan body"), tooth position.
- `restorations` — single crowns vs bridges with their tooth spans (e.g. single crowns at 26/28, a 23-24 bridge).
- `case_files` — uploaded scans (lower arch, upper/antagonist, scan-bodies, bite) as private S3 objects.
- `processing_jobs` — fulfillment/automation status.
- `orders` — payment gate.

Add: the `role` field and operator-wide RLS policies described in §3.2.

### 3.4 Core flows
1. **Submission.** Shop creates a case, adds implant sites (tooth → system/code/scan-body), selects restoration types, uploads scans via presigned S3 URLs.
2. **Fulfillment.** Operator sees a queue/dashboard, downloads inputs, does the RealGUIDE work, uploads the deliverable.
3. **Delivery + payment.** Download is gated until `orders.paid` is true. The bucket is private; NestJS signs a download URL only after confirming payment (so exposing an object key leaks nothing).

### 3.5 Compliance-support features (supports the client; doesn't assume their liability)
- **Immutable audit trail** — who submitted/changed/delivered what, when.
- **Explicit QC sign-off step** before a deliverable can be released (the operator's human check; the software just enforces the gate).
- **Private storage**, no patient-identifying data, no identifiers in filenames.
- Per-case design-notes field (industry norm; aids the shop and documents decisions).

### 3.6 Effort
Well-understood, low-risk build. The complexity is in the multi-tenant case/implant-site data entry and the presigned-upload + payment-gate plumbing, not in anything novel.

---

## 4. Product B — Automation: software design

### 4.1 The pipeline, decomposed
| # | Step | Automatable? | Tooling | Note for scoping |
|---|------|--------------|---------|------------------|
| 1 | Ingest scans | ✅ Full | I/O lib | Trivial |
| 2 | Mesh hygiene (denoise, fill, fix) | 🟡 Mostly | Blender / MeshLab | Bad scans → flag for human, don't force |
| 3 | Locate scan bodies → tooth position | 🟡 Partial | Custom + shop-provided positions | Positions are supplied, which helps a lot |
| 4 | **Register implant (axis, depth, clocking)** | 🟡 Partial | CloudCompare ICP + coarse align | **Highest-risk component. Clocking errors of a few degrees ruin the screw channel. De-risk this first.** |
| 5 | Abutment interface / emergence | 🟡 Partial | Library geometry + code | Has a clinical component |
| 6 | **Crown/bridge morphology** | 🔴 **No (cheaply)** | — | **Hard wall — see §4.3** |
| 7 | Contacts / occlusion | 🟡 Partial | Antagonist + bite | Judgment call on tightness |
| 8 | Screw-access channel | ✅ Full* | Follows axis | *Only after step 4 succeeds |
| 9 | Manufacturability check | ✅ Full | Geometric rules | Easy, high value |
| 10 | Export milling-ready file | ✅ Full | I/O lib | Trivial |

### 4.2 Two delivery patterns (per §2)
- **Augment pipeline (build first):** steps 1, 2, 3, 4, 9 run automatically and emit a cleaned/aligned STL set + a structured case spec. The client imports these into RealGUIDE and finishes — saving the per-case prep time. **This is the safe, high-confidence automation deliverable.**
- **Replace pipeline (selective, later):** for simple case types, chain steps 1–5 + 8–10 in open tools to produce a design without RealGUIDE. Step 6 (morphology) still needs the client or a licensed engine, so "replace" is partial even where it applies.

### 4.3 The hard wall — set expectations now
**Crown/bridge morphology (step 6) cannot be automated cheaply with open tools.** It's the clinical core — anatomy, esthetics, occlusion — and it's exactly what commercial engines (3Shape, exocad) spent years and large datasets building. Realistic options: keep the client doing it (most likely), or later evaluate licensing a design engine. **Tell the client plainly: automation removes the mechanical labor and pre-stages the design; it does not eliminate the designer.** A realistic target is **40–70% reduction in manual minutes per case**, not lights-out.

### 4.4 Automation stack
- **Orchestration:** Python; a job queue (Redis/RQ or a cloud queue) fed by the portal.
- **Workers:** Linux for Blender (`blender --background --python step.py`) and CloudCompare CLI (`CloudCompare -SILENT -O ... -ICP ...`). A Windows worker is needed **only** if any step must touch RealGUIDE (which, per §2, the automation should avoid).
- **Registration:** CloudCompare CLI for ICP refine, plus a custom coarse-alignment stage (ICP only polishes an already-rough fit; the coarse step is where the engineering is).
- **Integration with the portal:** the portal enqueues a `processing_job`; the worker writes status back and uploads outputs to S3.

### 4.5 De-risking recommendation
Before quoting the full automation, run a **fixed-scope spike on step 4 (registration)** against a handful of the client's real sample scans. It's the component most likely to be hard and most likely to determine whether Pattern 2 is ever viable. Quote the spike separately; let its result gate the larger automation contract. This protects both you and the client.

---

## 5. Architecture (text view)

```
 Dental shop (tenant)                      Operator = your client
 ┌───────────────┐    submit case+scans    ┌────────────────────────┐
 │  React portal │ ───────────────────────▶│  Operator dashboard    │
 │  (shop user)  │ ◀─────────────────────── │  (queue, QC, pricing)  │
 └──────┬────────┘   gated download         └───────────┬────────────┘
        │ presigned S3                                   │
        ▼                                                ▼
 ┌──────────────┐   ┌─────────────┐   ┌──────────────────────────────┐
 │  S3 (private)│   │  Supabase   │   │  NestJS (serverless)         │
 │  scan files  │   │  Auth + DB  │   │  presign URLs / job state /  │
 └──────┬───────┘   │  + RLS      │   │  Stripe webhooks             │
        │           └─────────────┘   └──────────────┬───────────────┘
        │ (Product B only)                           │ enqueue
        ▼                                            ▼
 ┌─────────────────────────────────────────────────────────────────┐
 │  Automation worker  (Python orchestration; Product B)            │
 │   ingest → mesh hygiene → REGISTER (CloudCompare ICP) →          │
 │   manufacturability check → cleaned/aligned STL + case spec      │
 │                                                                  │
 │   ── Pattern 1 (Augment): hand outputs to client → RealGUIDE     │
 │   ── Pattern 2 (Replace, simple cases): + morphology (human/     │
 │      licensed engine) → milling-ready file                       │
 └─────────────────────────────────────────────────────────────────┘
```

---

## 6. Build decisions — pros / cons

| Decision | Option A | Option B | Recommendation |
|---|---|---|---|
| Sequencing | Portal first | Automation first | **Portal first** — value now, low risk, funds the rest |
| RealGUIDE | Augment (pre-process for it) | Replace (open-tool pipeline) | **Augment first**; replace only for proven simple, high-volume case types |
| Auth/DB | Supabase | Cognito + own DB | **Supabase** — RLS isolation + DB + auth in one; Cognito only if going fully AWS-native |
| File storage | S3 | Supabase Storage | **S3** — co-locate with workers; avoid egress on large STLs |
| Morphology | Keep client manual | License design engine | **Keep client manual** initially; revisit licensing only if volume justifies |
| Automation scope | Fixed-scope registration spike, then expand | Full pipeline up front | **Spike first** — de-risks the one hard component before a big commitment |

---

## 7. ROI / effort analysis (framed for the client's existing operation)

The relevant ROI here is **the client's**, not a startup's: does paying you to build each product pay back against the client's current case volume? Plug the client's real numbers into these.

### 7.1 Portal ROI (to the client)
The portal saves per-case **admin** time (intake, back-and-forth, invoicing, file wrangling) and lets the client add shops without adding admin headcount.

```
Monthly admin saving ≈ V × A × Radmin
  V      = cases / month
  A      = admin minutes saved per case (intake + invoicing + file handling)
  Radmin = value of admin time per minute
```
*Illustrative:* V=300, A=10 min, Radmin=$0.40 → **~$1,200/mo** in admin time, **before** the scaling/professionalism upside (the portal is also a sales asset that helps the client win and retain shops). Against a portal build in the low five figures, payback is roughly a year on admin savings alone — faster once the growth effect is counted.

### 7.2 Automation ROI (to the client) — the decisive number
Automation saves per-case **design/prep** minutes (the mechanical steps), against the cost of building it.

```
Monthly saving      ≈ V × T × Rdesign
Break-even (months) ≈ Build cost ÷ Monthly saving
  T       = manual minutes saved per case (target 40–70% of prep)
  Rdesign = value of designer time per minute
```
*Illustrative:* automation saves T=20 min/case, Rdesign=$0.50/min.
| Volume V | Monthly saving | Break-even on a ~$30k automation build |
|---|---|---|
| 50 cases/mo | ~$500 | ~60 months — **not worth it; portal only** |
| 300 cases/mo | ~$3,000 | ~10 months — worth it |
| 800 cases/mo | ~$8,000 | ~4 months — clearly worth it |

**Honest conclusion to give the client:** automation pays back only above a volume threshold (roughly a few hundred cases/month with these assumptions). **Below that, the portal is the win and automation is premature** — building it would be spending your fee on something the client's volume can't amortize. Get the client's actual V and per-case time before scoping Product B.

### 7.3 Your perspective as the engineer (de-risked engagement)
- **Phase the contract** so each milestone is standalone and independently billable (§8). The client gets value at every step; you're not betting the whole fee on the hardest part landing.
- **Quote the registration spike as a fixed-scope, fixed-fee item** and let its outcome gate the larger automation contract. This is the single most important risk control for both sides.
- **Bill the portal on milestones** (intake → fulfillment dashboard → payment/delivery), each demoable.

---

## 8. Recommended delivery plan (milestones)

| Milestone | Deliverable | Acceptance criteria |
|---|---|---|
| **M1 — Portal MVP** | Multi-tenant intake (case + implant sites + scan upload), operator dashboard, gated delivery, Stripe payment, audit trail + QC gate | A shop can submit a real case; the client can fulfill and deliver; payment gates the download |
| **M2 — Registration spike** *(fixed scope/fee)* | Automated implant-axis + clocking recovery on the client's sample scans, accuracy report | Recovered axis/clocking within an agreed tolerance on the sample set; go/no-go on Pattern 2 |
| **M3 — Augment pipeline** | Automated ingest + mesh hygiene + registration + manufacturability check → cleaned/aligned STL + case spec for RealGUIDE import | Measured reduction in the client's per-case prep time on live cases |
| **M4 — Replace pipeline** *(conditional)* | Full open-tool design for one or more simple, high-volume case types | Only if M2 + volume justify; morphology path (manual or licensed) defined |

---

## 9. Open questions to scope and quote

Get these from the client before fixing scope and price:

1. **Current case volume per month**, and **how many dental-shop customers**? (Drives automation ROI and portal tenancy scale.)
2. **Average manual time per case in RealGUIDE today**, and which steps eat the most time? (Targets the automation; validates §7.2.)
3. **Current intake method** (email, file transfer, phone)? (Defines what the portal replaces.)
4. **Which implant systems / scan bodies dominate** the caseload? (Each system added to the automation is engineering + validation; narrow is faster.)
5. **Self-serve or mediated** — should shops submit directly, or does the client gatekeep intake?
6. **Payment model** — per-case, or shop subscriptions/account billing?
7. **Output formats** the shops need (STL for milling, vendor-specific, printed-model files)?
8. **Does the client already use RealGUIDE macros** or any existing automation? (May reduce or redirect effort.)
9. **Budget and timeline**, and which product (A or B) is the priority?
10. **Regulatory posture** — confirm the client owns clinical QC and device responsibility; the software will provide the audit trail and QC gate to support it.

---

*This document supersedes the prior business-feasibility review in framing: it assumes the operation exists and the engagement is to build software for it.*
