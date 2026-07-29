# Product app plan — the four-stage flow on a BFF, beside the frozen demo

**Date:** 2026-07-26 · **Status:** v2 — GRILLED (4 adversarial lenses, 1 FATAL + 11 must-amend
folded in; grill record in §9) · ready to execute on client go
**Client directives this answers (2026-07-26, voice):** presentation and processing must be
layered ("BFF layer… the backend and the workers actually doing the processing… the front end
layer is just presentational"); **do not touch the current demo** — build a NEW React app with
the new flow; keep the 3D panels, the point-matching and the rotation tools; support going BACK
through steps; support **multiple caps in one intake** for volume; Adjust is **skippable**, but
when skipped the client must still SEE the assurance of what was done and **confirm** before
payment and artifacts.

---

## 1. First principles

1. **A case is a session, not a wizard.** Forward and BACK, leave and return, several sites in
   one visit. State survives navigation — which rules out "the modal owns the state".
2. **Compute early, gate ACCESS late.** Alignment is cheap and reversible; what the client can
   TAKE is not. The worker emits at run time — that is how the frozen pipeline works and how
   the adjust tools find their site records — so the product does not pretend otherwise. What
   moves to the end of the flow is DISCLOSURE: no downloads, no payment transition, until a
   still-valid confirmation exists. (Grill AM-1: the draft said "the export gate moves to
   Release"; the worker contradicts that story, and pretending otherwise was the plan's one
   FATAL. §4 Deliver and §6 carry the corrected mechanism.)
3. **Presentation may not do the physics.** The React app renders payloads and collects
   choices. Every millimetre, verdict and clamp comes from the worker.
4. **Confirmation is on EVIDENCE, not on faith.** Whether or not Adjust was visited, Deliver
   shows what was measured and the client confirms THAT — a sealed evidence bundle, not a
   checkbox (§6).

## 2. Ubiquitous language

| Term | Meaning |
|---|---|
| **Case session** | One scan's journey Intake → Deliver; multi-site; resumable; back-navigable; persisted (§3) |
| **Worklist** | The `/` screen: one row per case with its site-queue rollup; the 20-scan morning's home |
| **Site queue** | Per-site status, DERIVED by the BFF from worker facts, never client-writable: `detected → declared → previewed → ready \| flagged → adjusted → ready` |
| **Assurance summary** | Deliver's per-site verdict TABLE (worst-first, flags above the fold): numbers vs industry refs, gate/clamp words, QC images behind row-expand |
| **Evidence bundle** | The canonical, content-addressed record the confirmation seals (§6) |
| **Release** | Post-confirmation DISCLOSURE of artifacts; the payment hook lives here |
| **Run directory** | Immutable `reports/product/<case>/<run_id>/`; a re-run mints a new id, never overwrites |
| **BFF** | The presentation-shaped API. Owns flow/session shape and the disclosure edge; owns NO physics |

## 3. Architecture

```
apps/product (NEW React app, :5174)      — presentational only
        │  case-session API (flow-shaped, job-shaped runs)
apps/bff (NEW FastAPI, :8001)            — aggregation, session store, validation, disclosure edge
        │  case_prep.application (NEW package, new files only)
apps/worker case_prep pipeline/domain/adapters — the physics (extended only where priced: §5, emit_from_poses)
apps/web + server.py (:5173/:8000)       — the FROZEN demo; no edits, runbook stays valid
```

**The seam, corrected (AM-2).** The clean seam is one layer DOWN from the draft's claim:
`run_auto_case`/`propose_sites` are clean callables with `emit_package/render_qc/
compute_confidence` flags (proven by the preview endpoint). The BFF imports ONLY
`case_prep.pipeline`/`domain`/`adapters`; **importing `case_prep.server` is forbidden** — it
boots the demo's module state (CASES, app, CORS, caches) and its handlers are HTTP-typed and
always-emit into the demo's data plane. A new `case_prep/application/` package (new files only;
server.py untouched) hosts the orchestration the product needs — request models, the
explicit-selection gate, capture assembly, and the certification-gate judging behind the four
adjust tools. Recorded Python debt: ~1,200 lines lifted from server.py. The BFF writes
exclusively under `reports/product/`; `reports/live-demo` is part of the freeze. **Slice-1 exit
criterion: run the BFF's propose+run+adjust flows and assert `reports/live-demo` is
byte-identical before and after.**

**Job-shaped from day one (AM-3).** `bff/ports/worker.py` exposes `submit(case, selection) →
job_id`, `status(job_id)`, `result(job_id)` — mirroring phase-2's SQS/status-writeback
semantics. The in-process adapter completes synchronously, but the app renders
`queued|running|done|refused` from day one, so the SQS adapter later replaces one file without
breaking any resource. Product state names carry an explicit mapping to phase-2's `case_status`
enum and `processing_jobs` columns; `tenant_id` is recorded on the case from day one.

**Session store, named and persisted (AM-4).** Site-queue statuses, adjust-visited, the
confirmation record + evidence hash, `payment_authorized` — persisted per case
(`reports/product/<case>/session.json` or SQLite), rehydrated on BFF start; a restart
mid-morning loses nothing, least of all at the money-adjacent step. No endpoint accepts a
status, verdict or gate outcome from the client — a presentational app PATCHing a flagged site
to `ready` is structurally impossible, not merely unstyled.

**Reuse: copies land in `packages/viewer` immediately (AM-5).** Consumed ONLY by
`apps/product` — zero demo import rewrites, and the draft's "extract later" slice retires.
Measured copy closure: **~11,700 lines / ~35 files** (the viewer stack plus its hard transitive
closure — palette, domain/types, librarySelection, meshCache, Viewer3D — and the deviation/
pane-framing payload types; `VerifyStage`/`VerifyPanels`/App wiring is REBUILT against BFF
shapes, not copied). `sceneController.ts` (1,839 lines) has NO test today — a characterization
test is part of the viewer slice, or "copied with their tests" is false where it matters most.
The ~1,200-line Python lift (above) is entered in the same debt ledger.

## 4. The four stages

**Worklist first (AM-7).** `/` is the case worklist: one row per case with the site-queue
rollup (n declared / n ready / n flagged / run state / confirmed), sorted blocked-first;
opening a row resumes its session at its furthest stage; "next case" returns here from any
stage. With job-shaped runs, the tech kicks off case A's run and declares case B — the 20-scan
morning has a surface.

**Intake** — case routes into its session (`/case/:id/intake` … `/deliver`; Back is a browser
affordance). Detection fires AUTOMATICALLY on load; capture-gate verdicts surface before work
is invested. Case-level choices live here: construction part, jaw, relief (+ceiling).
Import/upload is a later slice on this stage.

**Declare (AM-8)** — a case-level SYSTEM bar declared once (pre-filled from the suggestion;
switching is an explicit case-level act that visibly resets all variants — librarySelection
semantics, copied). Variant cards per ACTIVE site; the site queue on the left; the THREE PANES
live beside them, previews per-site and non-blocking. Mixed-system cases are out of scope for
v1 (the worker accepts one model per run) — named, not silent. The act that sets a site
`ready` is the operator's review tick over the live panes — the branded run gate's
"reviewed over panels, not a checkbox" doctrine kept — and the full run fires only over an
`AuthorizedRunSelection` minted when every site is reviewed.

**Adjust — skippable, evidence-preserving.** Rail shows "N of M ready · nothing to adjust";
Deliver directly reachable when clean. Flagged sites open with the toolset in order: fit by
points (incl. two-point spans, §5), best fit, rotation dial, mark trench. Re-verify updates
the site in place. **Adjusted cases change what Release consumes:** adjustments patch the cap
record only, so Release for an adjusted case uses a NEW worker entry point `emit_from_poses`
(emits deliverables from the implant records as adjusted) — priced with this slice; the worker
core is extended, not frozen.

**Deliver (AM-1, AM-11, AM-12)** — the assurance summary ALWAYS renders: a per-site verdict
table, worst-first, flags pinned above the fold, QC images behind row-expand (six sites = 12
images; a scroll of images must not bury the signature). Each row carries a disposition —
release / withhold-this-site (a withheld site drops from the released set and stays open) — and
the confirmation control is inert until every flagged row carries its own acknowledgment tick.
The BFF authenticates the operator before Deliver (minimum: a named operator session);
confirmation and release records carry the actor. Then **release = disclosure**: the BFF serves
no files_base, no downloads, no payment transition until a still-valid confirmation exists, and
it RE-DERIVES the case's evidence at release time, refusing (409 "the case changed —
re-confirm") unless it hashes to the confirmed bundle. Confirm → Back → adjust → Release is a
supported path that invalidates the confirmation by construction. The payment stub is
fail-closed, records `provider: "stub"` so stub-authorized sessions stay permanently
distinguishable from paid ones, and the artifact endpoint ITSELF enforces confirmation +
`payment_authorized` — screen order in a presentational app is not a control.

## 5. Two-point spans (worker extension)

Both ends of a trench, or across a hole: midpoint averages click noise (~0.21mm from two
±0.3mm clicks); the span DIRECTION is a second rotational constraint no single click gives;
ends are visually unambiguous where "the centre" is a judgement. Spans resolve to
(midpoint-azimuth + orientation) constraints feeding the existing gated circular-mean;
audit records both points. Validation (AM-9): finite ends, both within 15mm of the site,
MINIMUM span length (coincident clicks give an undefined direction), maximum span length.

## 6. Security of the alignment chain (grilled: AM-9, AM-10, AM-11)

- **The UI is untrusted; the BFF re-validates everything.** The validation corpus is copied
  VERBATIM from frozen server.py into the BFF request models (catalog membership + traversal
  refusal, explicit-selection 422, relief bounds, unique teeth, point-count caps, ±45° nudge,
  15mm mark distance, ≤8 pairs + lever-arm minimum, best-fit diameter bounds) and EXTENDED
  with what the demo lacks: length-3 + finiteness on every client coordinate including
  `SiteIn.center`. Five untrusted input classes, each with named checks: selections, site
  coords/marks, adjustment proposals, span points, session state. The compile-time branded
  type is honest UX, forgeable by any HTTP client; the BFF re-validation beside it is the
  control.
- **One gate, one home.** The design-rule gate keeps its single implementation inside
  `output_package`, fail-closed on catastrophic at RUN time — a refusal fires before the
  client is ever shown a confirmation, and the manifest's design-rules verdict is part of what
  they sign.
- **Confirmation seals a persisted bundle, not a hash of thin air.** The demo derives its
  acceptance numbers per response and mutates QC PNGs in place — a bare digest could never be
  re-verified in a dispute. Confirmation writes the evidence BUNDLE (canonical JSON, sorted
  keys, stated rounding, plus SHA-256 of each QC image's bytes) to an immutable
  content-addressed store under the run directory, transactionally — a failed write REFUSES
  the confirmation. Release verifies against this bundle. run-history stays what it is:
  best-effort telemetry.
- Nothing self-corrects: every operator action remains a gated proposal, refusable with reasons.

## 7. Slices, dependency-ordered (AM-6; each leaves everything working; demo untouched)

| # | Slice | Contents | Est. |
|---|---|---|---|
| 0 | **git init** + scaffold | version control FIRST (the master plan's own slice zero); `apps/bff` + `apps/product` + `packages/viewer` skeletons; ports 8001/5174; launch.json; local test lanes | 1d |
| 1 | BFF case-session read model | `case_prep/application` package; flow-shaped resource; freeze-guard test (live-demo byte-identical); session store | 1.5d |
| 2 | Product shell + routes | 4-stage rail, `/case/:id/:stage`, back/forward, resume | 1d |
| 2b | **Worklist** | the `/` screen; rollups; next-case loop | 1d |
| 3 | Viewer foundation | copies → `packages/viewer` + tests + sceneController characterization test; main stage with routing | 1.5d |
| 4 | Intake | auto-detect on load, capture verdicts, case-level choices | 1d |
| 5a | Declare: queue + status machine | site queue, system bar, variant cards, review ticks → AuthorizedRunSelection | 1.5d |
| 5b | Declare: live panes | three panes over the copied core; per-site non-blocking preview | 1d |
| 5c | Run orchestration | job-shaped full run (QC+confidence on) into a versioned run dir; progress surface; session-cached result | 1d |
| 8 | **Deliver** (pulled forward) | assurance table, evidence bundle + confirmation, operator identity, release-as-disclosure, payment stub, artifacts | 2d |
| 6 | Adjust | skippable policy, flagged queue, four tools via application layer, **emit_from_poses** | 2d |
| 7 | Two-point spans | worker + BFF + UI; battery extension | 1d |
| 9 | Predictability | rehearse-gate v2 driving BOTH paths (BFF and the frozen demo — slice 7 touches constraint code the demo executes); runbook addendum; fleet dry-run | 1d |
| 10 | Later | import/upload; SQS adapter per phase-2 plan | — |

**Honest totals (AM-6):** full table **~14–16 working days**. **Minimum demoable cut ~9–11
days = slices 0–5c + 2b + 8**: a clean case walks Intake → Declare → Deliver end-to-end with
the assurance table, sealed confirmation, gated release and payment stub. Adjust, spans and
predictability extend the product but — by the client's own skippable-Adjust directive — never
gate the first showing. Deliver lands BEFORE Adjust so the client's headline requirement
arrives 2.5–3 days earlier and the one worker change (`emit_from_poses`) leaves the critical
path.

## 8. Decisions taken vs open

**Taken (client, 2026-07-26):** Adjust skippable; assurance + confirmation ALWAYS before
release; new app rather than editing the demo; layering as above; multi-cap in one intake.
**Assumed (flagged):** app name `apps/product`; FastAPI BFF with the seam as in §3; payment
stubbed until a provider is named; mixed-system cases out of v1.
**Open (needs client):** the confirmation's attestation wording for THEIR client; whether
release requires a second actor — note this is NOT a one-line change (it rides on the operator
identity in AM-11, which is why identity capture is in the Deliver slice from the start).

## 9. Grill record (2026-07-26)

Four independent adversarial lenses (architecture/DDD, delivery, product/volume, security/
audit) + synthesis; all pillar decisions WITHSTOOD (new app over BFF over worker, copy-not-
share, four stages, preview-at-Declare, FastAPI-over-Node, multi-cap). Amendments folded in:
AM-1 emission/disclosure (FATAL), AM-2 seam correction, AM-3 job-shaped port, AM-4 session
store, AM-5 copy ledger, AM-6 slice repair, AM-7 worklist, AM-8 case-scoped system + review
ticks, AM-9 validation corpus, AM-10 evidence bundle, AM-11 actor identity + stub honesty,
AM-12 exception-first assurance. **Rejected by the synthesis** (recorded so they are not
re-proposed): repointing `server.OUT`/`CASES` at BFF startup (executes frozen module state);
deferred emission with a design-rules dry-run (contradicts how Adjust and the QC evidence
actually work — more new worker surface than `emit_from_poses`).

---

## 10. Queued after slice 6 (client direction, 2026-07-28)

**A. The agreement moves to payment (client: "This can be at the time of payment … as a Terms
and Conditions or more explicit saying someone reviewed the alignment changes and they agree to
proceed").** The formal language was scattered across per-site ticks mid-workflow; legal weight
belongs at the commercial moment, once.

- Declare's per-site control becomes lightweight: "Reviewed" — a workflow state meaning the
  operator looked at that site's panes. It still gates the run (the run-authorization doctrine
  is unchanged); it simply stops wearing agreement clothes.
- The PAYMENT step gains the agreement: the terms, an explicit acceptance, recorded with its
  timestamp and the evidence hash it was given over. Payment (and therefore release) is gated
  on it. The acceptance rides into the evidence bundle like the fork decision does, so
  re-derivation at release catches a case that changed after it was agreed.
- THE TERMS TEXT IS THE CLIENT'S. Placeholder until they supply it, marked as such in the UI
  and in the record: "I have reviewed the alignment for all N sites in this case, including the
  assurance report and its QC images. I accept the alignment as shown and authorize release of
  the deliverables." One string to swap.
- Open, still theirs (plan §8): whether release requires a second actor. Unchanged by this.

**B. Manual cap marking at Intake (client, 2026-07-28).** The product has no marking flow: a cap
the detector misses cannot be added, and detection MISSES 2 of 10 sites on this fleet
(cap7020-zimmer-4.5, zimmer-4.5 t7) — those cases are unworkable in the product today. Also the
marker on screen is the demo's PROPOSAL vocabulary (orange, guess-radius), not the operator
CENTRE MARK the client remembers (red, 0.6mm, with blue for the rim). Brings across: confirm or
dismiss a proposal, add a site by clicking its centre, the centre+rim pair (carrying the
re-click pair-integrity rule — moving the centre clears a standing rim mark), per-site removal.

**C. Gingival relief moves out of Intake (client, 2026-07-28: "Gingival relief should be in the
adjustment section not in the intake").** They are right, and the reason is stronger than
placement: relief does not touch the ALIGNMENT at all — it shapes the EMITTED part — and its
ceiling is a property of (construction part × declared variant). At Intake no variant is
declared yet, so the ceiling shown there is derived from the SUGGESTION and can be wrong for
what the operator actually declares. The screenshot shows it: "6020: ceiling 0.43mm" quoted
before 6020 was declared.

Design consequence to face, not paper over: relief feeds the run. Moving it to Adjust makes the
loop honest — the first run uses the standing default (clamped as the wall rule requires), the
operator sees the produced result, and changing relief there RE-EMITS (it never re-aligns; the
pose is untouched). That is precisely what an adjustment is.

Open, and worth deciding when it is built: relief is case-level today while its ceiling is
per-site. On a two-variant case (neodent-gm: 6020 and 5020) one number carries two different
ceilings — which is why the run clamps per site. In Adjust it should become PER SITE, with the
per-site ceiling beside it. That is more correct than what the demo did, not merely relocated.

**D. Intake badge collision (client, 2026-07-28).** The SUGGESTED / DEFAULT badges sit flush
against their labels with no gap and no wrap allowance. Cosmetic, product-only; the label row
needs to be a flex line with a gap and wrapping.

**E. N caps in one scan — the shape holds, but the shared construction part is a DISCLOSURE
GAP (found 2026-07-28 answering the client's multi-cap question).**

The plumbing is genuinely N-wide: no site-count cap exists anywhere, `sites` is a dict keyed by
tooth, the run loops per site (auto_flow.py:1714), the queue and the assurance table are
per-site rows. Jaw being case-level is CORRECT for the client's own framing — one arch, one jaw.

The per-site / case-level split is the thing to state as a rule rather than leave as an
accident. PER SITE: the variant only. CASE-LEVEL: implant system, construction part, jaw,
relief. So N caps in one intake must share one implant SYSTEM (variants may differ) — defensible
for one patient, but it should be a declared constraint the UI enforces, not a shape nobody
wrote down.

THE GAP: the construction part is case-level while the variant is per-site, and the worker
already knows this breaks. auto_flow.py:2280-2283 computes
`"single construction part shared across sites identifying N distinct variants — per-variant
construction parts needed"` and writes it to `row["production"]["note"]`. The BFF's assurance
read (resources/deliver.py:176-205) picks up the relief-clamp fields out of that same block and
DROPS the note. Consequence on a two-variant case (neodent-gm: 6020 + 5020): the worker records
that the emitted geometry cannot match both sites, and the client sees per-site green verdicts
with nothing said — then confirms and pays against that surface. Same class as the four slice-8
disclosure leaks: a fact the system holds and the paying surface does not show.

Fix shape: surface `production.note` on the assurance row (per-site, beside the clamp story),
and decide whether a multi-variant case should FLAG rather than merely annotate. It should
probably flag — the note's own words are "cannot match", not "differs slightly".

Untested above N=2: the whole fleet is single-site except neodent-gm. Preview is 3-6s/site
serial, so a full arch is minutes of previews nobody has measured; the run's N-scaling, the
memory of N scan crops, and the queue/table at 14 rows are all unmeasured. Not known-broken —
unmeasured, which is a different claim and should stay one until someone runs it.
