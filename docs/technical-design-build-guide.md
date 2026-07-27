# Implant CAD Portal & Automation — Technical Design & Build Guide

**Audience:** the engineer(s) building this, and the stakeholder approving the budget.
**Goal:** a rigorous, decision-complete design. Every implementation fork is written as a numbered **Decision (D#)** with options, tradeoffs, and a recommendation, so the build team can navigate the project and a reviewer can see the depth the cost reflects.

> **How to read this.** Each step states its *purpose* and *implementation*, then breaks out any **Decision** the engineer must make. Decisions are numbered D1–D42 for reference in discussion. Domain terms (scan body, clocking, emergence…) are defined in the Glossary (Appendix B) — read that first if dental CAD is unfamiliar; it is essential to the mental model.

**Contents:** Part 0 Principles · Part 1 Portal (P1–P12, D1–D25) · Part 2 Automation (A1–A11, D26–D42) · Part 3 Cross-cutting · Part 4 Why it costs what it does · Part 5 Milestones & gates · Appendix A Tech inventory · Appendix B Glossary

---

## Part 0 — Principles & scope

**Scope.** We build software for a client who already owns the operation, the RealGUIDE license, the dental-shop customers, and the clinical/regulatory responsibility. We do *not* own demand, clinical judgment, or device regulation.

**The principle that constrains every automation choice:** RealGUIDE is closed (macros + GUI, no API). **We augment it (pre-process inputs it imports) or replace specific steps with open tools — we never script it.** Restated here because half the automation decisions below are downstream of it.

**No PII.** Cases carry an opaque shop-supplied label only. Note the scan mesh is itself arguably biometric (Appendix B); enforcement means no identifiers in filenames or metadata, encryption at rest, and access logging — not merely the absence of patient names.

---

# Part 1 — The Portal

## P1. Project setup & stack

**Purpose.** Establish the repo, build, and deploy substrate.

**D1 — Frontend build.**
- **Vite SPA** — fast, simple, clean separation from the NestJS API. No SSR/SEO (irrelevant for an authenticated portal).
- **Next.js (App Router)** — SSR + built-in API routes (could absorb some backend), but heavier and redundant given a dedicated NestJS backend.
- **Recommendation: Vite SPA.** The portal is behind auth; SEO is moot, and a separate API is already chosen. Avoid carrying Next's weight for features we won't use.

**D2 — Repo layout.**
- **Monorepo** (pnpm/turborepo: `web`, `api`, `worker`, `shared` types) — shared TypeScript types between front/back/worker, atomic cross-cutting changes. Recommended; the shared case/implant types are used in all three.
- **Polyrepo** — independent deploys, more overhead syncing types. Only if separate teams own each.
- **Recommendation: monorepo** with a `shared` package for DTOs/zod schemas reused by web, api, and worker.

## P2. Auth & identity

**Purpose.** Authenticate shops and the operator; let the API trust requests.

**D3 — Auth methods (Supabase Auth).**
- Email + password, magic link, Google OAuth, SSO/SAML.
- **Recommendation:** email/password **+ magic link** for shops at MVP; defer SSO/SAML (enterprise-only; the client's customers are small labs). Enforce email verification.

**D4 — How NestJS trusts a request.**
- **Verify the Supabase JWT against its JWKS** in middleware (stateless, no per-request network call) — recommended.
- Call Supabase admin `getUser()` per request — a network hop and rate-limit exposure on every call. Avoid.
- **Recommendation:** cache the JWKS, verify the JWT signature + claims (aud, exp, role) locally; reject otherwise. This is ~30 lines and is the API's trust boundary.

## P3. Tenancy & authorization — the core security design

**Purpose.** Guarantee a shop sees only its own data; give the operator controlled cross-tenant access **without** a dangerous client-side super-grant.

**D5 — The authorization model (HIGH stakes).**
- **Option A — Pure RLS, operator super-policy.** Shops scoped by RLS; operator gets an RLS policy reading all rows. *Rejected:* one misconfig or a stolen operator session exposes every tenant; the elevated grant lives on the client.
- **Option B — Split: RLS for shops, backend for operator.** Shop clients hit Supabase directly under strict tenant-scoped RLS. The **operator console never gets a cross-tenant RLS bypass**; its cross-tenant reads/writes go through NestJS using the **service role**, with the API enforcing operator authz and logging every access. *Recommended.*
- **Option C — Fully backend-mediated.** No direct Supabase from any client; everything via NestJS. Maximum control, but you rewrite all CRUD and lose RLS's defense-in-depth and Supabase's DX. Overkill at this scale.
- **Recommendation: Option B.** It keeps Supabase's RLS as a hard tenant boundary for the many (shops) while routing the few, powerful operator actions through an auditable backend.

**D6 — Making RLS performant.**
Child-table policies that check ownership via `exists (select … from cases)` run a **subquery per row** — fine at 100 rows, painful at 100k.
- **Denormalize `tenant_id` onto every child table** (`implant_sites`, `case_files`, …) so policies are indexed equality checks (`tenant_id = auth.jwt() ->> 'tenant_id'`). *Recommended.* Maintain it with a trigger or set it on insert from the parent.

## P4. Data model & migrations

**Purpose.** The schema everything hangs off.

Base: the delivered `schema.sql` (`cases`, `implant_sites`, `restorations`, `case_files`, `processing_jobs`, `orders`), plus `role` on `profiles` and `tenant_id` denormalized per D6.

**D7 — Migration tooling.**
- **Raw SQL migrations** (Supabase CLI) — idiomatic for Supabase, full control over RLS/policies/triggers which ORMs model poorly. *Recommended.*
- **Prisma/Drizzle migrations** — nicer DX for the NestJS side, but RLS/policy DDL fights the ORM. If used, keep policies/triggers in raw SQL migrations alongside.
- **Recommendation:** raw SQL as the source of truth for schema + RLS; optionally generate TypeScript types from the DB for the app.

## P5. Case submission & the upload subsystem (the portal's hardest engineering)

**Purpose.** Capture the case spec and move 20–100 MB scan files reliably from a clinic to S3.

**Submission form.** Dynamic, per-implant rows mirroring RealGUIDE inputs (tooth number, implant system, implant code, scan-body type), restoration definitions (single crown vs bridge spans), and the scan-file set (lower/upper/scan-bodies/bite). Validate with shared zod schemas (front + back).

**D8 — Upload path.**
- **Through the backend (proxy).** Backend validates the file directly — but **API Gateway/Lambda caps payloads at 6 MB**, so 100 MB files are impossible this way, and proxying doubles bandwidth/cost regardless. *Rejected for large files.*
- **Direct browser→S3, presigned single PUT.** Simple, but a single 100 MB PUT over clinic Wi-Fi will time out / fail with no resume. *Insufficient.*
- **Direct browser→S3, presigned multipart.** Reliable, resumable, parallel parts. More client logic. *Recommended.*
- **Recommendation: presigned multipart**, direct to S3.

**D9 — Multipart orchestration.** Backend signs `CreateMultipartUpload`, then a presigned URL per `UploadPart` (5 MB min part, ≤10k parts), then `CompleteMultipartUpload`. Client uploads parts in parallel (3–5 concurrent) with per-part retry/backoff.
- Decision: **who tracks completed parts** — client memory only (lost on refresh) vs persisted. **Recommendation:** persist `uploadId` + completed ETags in a `uploads` table so an interrupted upload **resumes** after a reload; reconcile against S3 `ListParts`.

**D10 — Integrity.** Client computes a SHA-256 while chunking; store it on `case_files`; verify on completion. Guards against silent corruption of clinical geometry.

**D11 — File validation (since the backend never sees the bytes).**
- **S3 event → validation Lambda/worker** that downloads the object and runs a cheap check (valid STL/PLY header, vertex/face counts in range, basic manifold sanity) before the case can be queued. Flag failures back to the shop. *Recommended.*
- Validate inside the automation worker only — too late; garbage already entered the queue. Avoid as the sole gate.

## P6. Storage, encryption, lifecycle

**D12 — Encryption at rest.**
- **SSE-S3** (AES-256, managed) — free, simple.
- **SSE-KMS** — per-key control, audit trail, defensible for biometric-adjacent data; small per-request cost.
- **Recommendation: SSE-KMS** given the data's nature; the audit and key-rotation story is worth the marginal cost.

**D13 — Lifecycle (cost control).** Storage grows unbounded otherwise. **Recommendation:** policy to transition delivered cases' inputs to infrequent-access/Glacier after a grace period and delete after a retention window — **confirm the legal/clinical retention requirement with the client first** (this is a client decision, D-client).

**D14 — Key layout.** `tenant/{tenant_id}/case/{case_id}/{kind}/{uuid}.stl` — no PII in keys; enables per-tenant lifecycle and prefix-scoped IAM.

## P7. Case state machine & concurrency

**Purpose.** A correct, race-free lifecycle the operator and shops share.

**D15 — States & transitions.** Model explicitly:
`draft → submitted → queued → assigned → in_design → qc_pending → ready → paid → delivered`, plus `rejected` and `failed`. Record legal transitions in one place (DB enum + service-layer guard); reject illegal jumps. This prevents the "status drifts from reality" failure.

**D16 — Concurrency / locking (multiple technicians).**
- **Optimistic** (version column; reject stale writes) — light, but two techs can still both *start* the same case before either saves.
- **Pessimistic / claim-based** (`assigned_to` set on claim; others see it locked; heartbeat + timeout auto-releases an abandoned claim). *Recommended* for an operator queue — it prevents duplicate work, which is the real failure here.
- **Recommendation: claim-based assignment with a TTL heartbeat.**

## P8. Operator console & the fulfillment seam

**Purpose.** Where the operator works the queue. Note the **hard truth (design it honestly):** fulfillment happens in RealGUIDE, *out-of-band*. The portal has **zero visibility** into the actual design work; status is operator-asserted.

**D17 — Reducing the handoff friction.** Operator downloads inputs (signed URLs), works in RealGUIDE, uploads the deliverable + sets QC sign-off. To minimize context-switching, provide a per-case "work packet" (all inputs zipped + the case spec sheet) one click away, and an explicit QC-gate action that is the *only* path to `ready`. There is no deeper integration available — say so to the client.

## P9. Payment & preview

**D18 — Payment model.**
- **Per-case prepay** — Stripe Checkout Session (hosted, simplest) or PaymentIntent (custom UI). Clean for ad-hoc shops.
- **Account / postpaid monthly** — Stripe Invoicing or metered billing; shop accrues cases, billed monthly. Common in B2B labs; better for high-volume regulars.
- **Recommendation:** support **per-case prepay at MVP** (Checkout Session, least code), architect `orders` so **monthly account billing** can be added without schema change. Final choice is the client's (D-client).

**D19 — Preview-before-pay (product-critical; a delivered file can't be clawed back).**
- **Server-rendered watermarked images / turntable** of the deliverable mesh (headless Blender or three.js offscreen render) — shows quality, exposes **no usable geometry**. *Recommended.*
- Decimated/low-poly in-browser viewer — still ships geometry the shop could mill. *Reject* (defeats the gate).
- Operator-uploaded screenshots — manual, inconsistent. Fallback only.
- **Recommendation:** automated server-side watermarked renders as the approval artifact; payment unlocks the real file.

**D20 — Webhook handling.** Verify Stripe signatures; make handlers **idempotent** (store processed event IDs — Stripe retries); the `paid` transition is driven only by the verified webhook, never the client. Handle refunds/disputes as explicit states with a defined policy for already-delivered files.

## P10. Delivery

**D21 — Download policy.** Backend issues a **short-TTL signed URL** only after confirming `orders.paid`; log every issuance (audit). Bucket stays private, so a leaked key is inert. Decide single-use vs short-window reusable — **recommend short-window** (e.g., 15 min) to tolerate flaky downloads without long-lived exposure.

## P11. Notifications

**D22 — Provider & events.** Resend/Postmark/SES; events: case received, ready-for-approval, delivered, failed/needs-attention. Recommend a thin notifications service so channels (email now, SMS later) are pluggable.

## P12. Observability & deployment

**D23 — Hosting.** Web on Vercel/Cloudflare/S3+CloudFront; NestJS on Lambda (cold-start aware — keep the bundle lean) **or** a container (Fargate/Cloud Run) to avoid cold starts. **Recommendation:** container for the API if budget allows (steadier latency); Lambda acceptable at low volume.
**D24 — Error tracking & logging.** Sentry + structured logs from day one; correlate by `case_id`.
**D25 — CI/CD.** GitHub Actions: typecheck, test (incl. **RLS policy tests** and state-machine tests), migrate, deploy to staging then prod.

---

# Part 2 — The Automation

## A1. Orchestration & compute

**D26 — Queue / orchestration.**
- **Supabase table + polling worker** — trivial, fine for the first pipeline; weak retry/backoff semantics.
- **Managed queue (SQS) / BullMQ (Redis)** — durable, retries, dead-letter. *Recommended baseline.*
- **Temporal (workflow engine)** — best for a multi-step pipeline with retries, timeouts, and compensation per step; more infra. *Adopt if/when the pipeline grows to many fallible stages.*
- **Recommendation:** start **SQS or BullMQ**; graduate to **Temporal** when steps multiply and per-step retry/observability matters.

**D27 — Worker compute.**
- **Lambda** — 15-min cap, ≤10 GB mem, no GPU; OK for light mesh ops, **too constrained for heavy CAD/ML**.
- **ECS Fargate** — containers, right-sized CPU/mem, no GPU. *Recommended for the geometric pipeline.*
- **AWS Batch / EC2 (GPU)** — for ML morphology or heavy jobs. Adopt in 2C.
- **Recommendation:** containerized worker on **Fargate** for 2A/2B; **GPU EC2/Batch** only if 2C trains/serves a model.

**D28 — OS.** **Linux** for Blender / CloudCompare / Open3D. A **Windows** worker only if a step is forced to touch RealGUIDE — which the design avoids (Part 0).

## A2. Mesh libraries — the toolbox

**D29 — Which library for what.** No single library wins; assemble:
- **trimesh** — Pythonic I/O, basic geometry, ray casting (used in thickness checks).
- **Open3D** — point clouds, **FPFH features, RANSAC/Fast Global Registration, ICP variants** (the registration core).
- **PyMeshLab** — robust cleaning/repair filters.
- **Blender (bpy, headless)** — booleans, blockout, complex modeling, offscreen renders (also reused for the P9 preview).
- **Recommendation:** trimesh + Open3D for geometry/registration, PyMeshLab for cleaning, Blender for booleans/rendering. Pin versions; containerize.

## A3. Ingest & validation
Pull the case's files from S3, re-validate (parity with P11), normalize units/orientation. Reject early on malformed meshes with a clear reason; never silently proceed.

## A4. Mesh hygiene

**D30 — Repair vs reject.** Auto-repair (fill holes, remove non-manifold, isolate the relevant shell, light smoothing) **up to a quality threshold**; beyond it (excessive holes/non-manifold), **reject to manual** rather than "fix" and risk corrupting clinical geometry. Define the thresholds with the client.
**D31 — Cleaning tool.** PyMeshLab filter chain (recommended for breadth) vs Open3D vs MeshFix. Recommendation: PyMeshLab, with the chain parameterized and logged per case.

## A5. Scan-body localization (coarse find) — the make-or-break input to registration

**Purpose.** Find each scan body in the arch and get a rough pose to seed fine registration. The form gives *which tooth* and *which scan-body type* (so the target STL is known) — but **not the 6-DOF pose**.

**D32 — Localization strategy (HIGH stakes; the central automation fork).**
- **Operator-seeded** — the operator clicks each scan body once in a viewer to seed position. Cheap, robust, but **not lights-out** (a ~2-second human action per implant). *Best MVP; degrades gracefully.*
- **Position-prior cropping + template fit** — use tooth position + arch landmarks to crop the region, then fit the known scan-body STL.
- **Feature-based global registration** — FPFH descriptors + RANSAC/Fast Global Registration (Open3D) to locate the known scan-body geometry automatically. The "automated" path; **brittle on noisy/partial scans**.
- **ML detection/segmentation** — train a 3D segmenter (PointNet++ / sparse-conv) on the client's accumulating cases to detect scan bodies. Most robust long-term; **needs labeled data** (the human-in-the-loop service generates it — the data flywheel).
- **Recommendation:** ship with **operator-seeded** (reliable, immediate) *or* **FPFH+RANSAC** if going for automation early; instrument every case to build the dataset, then move to **ML** once data justifies it. This decision defines whether "full automation" is reachable and on what timeline — discuss explicitly.

## A6. Fine registration & clocking — the highest-risk component

**Purpose.** Recover precise implant **axis, depth, and rotational clocking** from the seeded pose. Clocking errors of a few degrees ruin the screw channel.

**D33 — ICP variant.** Point-to-point vs **point-to-plane** vs Generalized-ICP. **Recommendation: point-to-plane** (faster, better convergence on surfaces); GICP if noise warrants.
**D34 — Seeding.** Run **global registration first** (D32 feature path) to seed, then ICP refine — solves the "ICP only polishes" problem.
**D35 — Clocking validation (the trap).** Scan bodies are near-rotationally-symmetric, so ICP can converge to the **wrong clock**.
- **Multi-start ICP** from several rotations about the axis; pick lowest residual **and check the gap to second-best** — if too close, flag symmetry ambiguity.
- **Explicit anti-rotation-feature detection** — find the flat/notch geometrically and align to it.
- **Recommendation:** both — multi-start to get the candidate, feature-check to confirm; on low confidence, **flag to manual**.
**D36 — Acceptance & confidence.** Define a tolerance (position µm, angle °, clocking °) **with the client, against ground truth = the client's manual RealGUIDE result**, *before* the 2A spike. Emit a per-case confidence; below threshold → route to manual, never ship blind.

## A7. Abutment interface & emergence

**D37 — Generation approach.** The implant connection geometry is library-known → **parametric, library-driven generation** of the interface (recommended). The **emergence profile** has a clinical/soft-tissue component → in the **augment** path, leave it to RealGUIDE; only attempt it in 2C with explicit rules and QC.

## A8. Manufacturability checks

**D38 — Implementation.** Geometric checks: minimum wall thickness (ray-cast / signed-distance), cement gap, undercuts relative to the insertion axis, milling-tool-radius feasibility. trimesh/Open3D + custom. Output a pass/fail report per case; failures flag, don't auto-edit.

## A9. Output packaging for RealGUIDE (the augment seam)

**Purpose.** Hand RealGUIDE inputs that cut the operator's time. **Seam to design carefully:** STL is geometry-only and we **cannot inject the recovered transform into RealGUIDE programmatically** (it's closed).

**D39 — Conveying the implant pose.**
- **Bake pose into geometry** — pre-position/orient the exported meshes in the coordinate frame RealGUIDE's import expects, so the operator's import lands correctly with minimal setup. *Preferred where feasible.*
- **Sidecar spec sheet** — a generated summary (positions, axes, codes) the operator uses to set up the implant quickly in RealGUIDE.
- **Recommendation:** do **both** — bake what import will honor, and provide the sheet for what it won't. Validate against a real RealGUIDE import early (this seam is a known integration risk).

## A10. Morphology (Replace path, 2C — optional)

**Purpose.** Crown morphology — the clinical wall open tools don't give free.

**D40 — Source of morphology.**
- **Rent** — 3Shape Automate (~$2/unit, ~90 s, ~93% accept), Dentbird, UP3D. Fast/proven, **but they don't cover implant abutments**, and they're consumed via file workflows, not a dev SDK.
- **Open models** — VBCD, CrownGen (code available). They output a **proposal needing margin-line/interface adaptation** in a CAD engine.
- **Build** — train on the client's data (PointNet++/diffusion). Moonshot; only with the flywheel; competes with million-case incumbents.
- **Recommendation:** for implant work specifically, **own segmentation + registration (open)**; for morphology, **integrate an open proposal model and finalize margins in CAD**, or keep the operator. Treat full self-trained morphology as a later, narrow, data-funded bet.

**D41 — Integration seam.** Whichever source, 2C is a **multi-tool chain** (your geometry → morphology engine → margin/interface adaptation → export) with format conversions; each seam is a failure point and a maintenance burden. Scope it as integration, not a monolith.

## A11. QC tooling & fallback

**D42 — Fallback & QC.** Every automated output passes a **human QC gate** (automation removes design labor, never the checker). Failed/low-confidence jobs **dead-letter and fall back to manual** so a case is never stuck. Provide the operator a viewer to inspect/approve/reject automated results, feeding rejections back as training signal.

---

## Part 3 — Cross-cutting concerns

- **Worker identity/secrets.** Worker authenticates to S3/Supabase via IAM role / service role; secrets in a manager (not env files); least-privilege, prefix-scoped S3 access.
- **Observability.** Per-step logs/metrics, job duration, failure reasons, registration confidence distribution; alert on failure-rate spikes.
- **Backup/DR.** Case DB + scan files *are* the business — automated backups, tested restore, defined RPO/RTO.
- **Retention/PII.** Lifecycle per D13; no identifiers in keys/metadata; KMS encryption; access audited.
- **Cost model.** Track per-case S3 storage + egress + worker compute; the lifecycle policy (D13) is the main lever as volume grows.

---

## Part 4 — Why this costs what it does

The price reflects resolved hard problems, not a CRUD app. Concretely, the non-trivial engineering a reviewer is paying for:

- **A real authorization architecture** (D5/D6) — tenant isolation with audited operator escalation, not a naive admin flag that leaks every shop.
- **Production-grade large-file ingestion** (D8–D11) — resumable multipart with integrity and out-of-band validation, because single PUTs fail in clinics.
- **A correct, race-free case lifecycle** (D15/D16) — claim-based locking so technicians don't duplicate work.
- **A payment design that survives reality** (D18–D20) — preview-before-pay and idempotent, signature-verified webhooks, because a delivered design can't be clawed back.
- **The registration problem** (D32–D36) — coarse localization + seeded point-to-plane ICP + **clocking validation against ground truth**: the genuinely hard, de-risk-first component on which all automation value rests.
- **The closed-RealGUIDE seam** (D39) — conveying recovered pose into a tool we cannot script.

| Deliverable | Effort | Price |
|---|---|---|
| Portal MVP (P1–P12) | 6–10 wks (250–400 hrs) | **$30k–$55k** fixed |
| 2A Registration spike (A5–A6) | 2–4 wks (80–160 hrs) | **$10k–$20k** fixed |
| 2B Augment pipeline (A1–A9) | 3–5 mo | **$50k–$120k** milestone |
| 2C Replace + ML (A10) | 6+ mo | **$120k–$250k+** T&M |

Rate basis: ~$100–150/hr solo senior direct; agencies higher, offshore lower; retainer ~$15k–25k/mo. Portal and spike are fixed-price; the rest is milestone/T&M and **gated** (Part 5).

---

## Part 5 — Milestones & gates

1. **Discovery** (Appendix-client questions) → caseload mix, volume, per-case time, tolerances.
2. **M1 Portal MVP** *(fixed)*. Gate: real case submitted → fulfilled → paid → delivered.
3. **M2 Registration spike** *(fixed)*. Gate: clocking/position within agreed tolerance on sample scans → **go/no-go on automation**.
4. **M3 Augment pipeline** *(milestone)*. Gate: **measured per-case time reduction on live cases** → go/no-go on scaling.
5. **M4 Replace/ML** *(T&M, conditional)*. Only if volume + case mix + M2/M3 justify.

Each milestone is standalone and independently billable; no open-ended research is ever carried at a fixed price.

---

## Appendix A — Technology inventory

| Concern | Choice | Decision |
|---|---|---|
| Frontend | React + Vite SPA | D1 |
| Repo | pnpm/turbo monorepo + shared types | D2 |
| Auth/DB | Supabase (Auth + Postgres + RLS) | D3/D5 |
| API | NestJS (container or Lambda) | D4/D23 |
| Authz | RLS (shops) + service-role backend (operator) | D5/D6 |
| Storage | S3 private, SSE-KMS, lifecycle, multipart | D8/D12/D13 |
| Payments | Stripe (Checkout MVP → account billing) | D18 |
| Preview | Headless Blender/three.js watermarked render | D19 |
| Queue | SQS/BullMQ → Temporal | D26 |
| Worker | Fargate (Linux) → GPU Batch for ML | D27/D28 |
| Mesh | trimesh + Open3D + PyMeshLab + Blender | D29 |
| Registration | FPFH/RANSAC seed → point-to-plane ICP + clocking check | D32–D35 |
| Morphology (2C) | Open proposal model + CAD finalize, or rent | D40 |
| Observability | Sentry + structured logs/metrics | D24 |

## Appendix B — Glossary (build your mental model first)

- **Implant** — titanium fixture in the jaw replacing a tooth root.
- **Abutment** — connector between the implant and the crown.
- **Scan body / scan abutment** — a precision marker temporarily screwed onto the implant so an intraoral scan captures the implant's exact position and orientation. The library STL of each scan-body type is known.
- **Clocking / timing / indexing** — the **rotational** orientation of the implant connection (hex/anti-rotation feature). Critical for screw-retained crowns; small errors misplace the screw channel.
- **Emergence profile** — the contour where the restoration emerges through the gum; partly a clinical/soft-tissue judgment.
- **Margin line** — the boundary where the crown meets the prepared tooth/abutment.
- **Antagonist / occlusion** — the opposing arch and how the teeth meet; drives contact design.
- **Screw-retained vs cement-retained** — how the crown attaches; screw-retained needs an accurate access channel along the implant axis (hence clocking).
- **Waxup / blockout** — a proposed restoration shape; filling undercuts before design.
- **FDI vs Universal numbering** — two tooth-numbering systems (the screenshots use Universal 1–32; store the notation to avoid ambiguity).
- **STL / PLY** — common 3D mesh file formats for scans/designs (geometry only; no implant transform).
- **ICP (Iterative Closest Point)** — aligns one mesh/point-cloud to another by minimizing surface distance; **refines** an existing rough alignment.
- **FPFH / RANSAC global registration** — feature-based method to find an initial alignment from scratch (seeds ICP).

---

*This document specifies the build to the level a senior engineer can execute against and a reviewer can fund. Architecture and lifecycle diagrams are in the companion brief; this one carries the implementation depth and decision rationale.*
