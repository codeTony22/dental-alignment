# Product app plan — the operator flow on a BFF, beside the frozen demo

> **The title said "four-stage" until 2026-08-02.** The flow is FIVE stages since the
> client's 2026-08-01 direction — Intake · Alignment · Adjustment · Construction
> library · Delivery — with the stage KEYS unchanged. §10-M is the record. Sections 4
> and 7 below describe the four-stage build as it happened and are left as written;
> where they disagree with §10, §10 wins.

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

## 4. The four stages (as built; the fifth arrived 2026-08-01 — see §10-M)

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

**F. The span caution should become a true pre-refusal (2026-07-29, item 2 of three).**

The client asked that fit-by-points "refuse before you place the span, not after". What
shipped is a CAUTION, not a refusal, and the difference is deliberate rather than a
shortcut.

The server's scan-side lever guard measures a mark's distance from the scan's MEASURED
RIM CENTRE — `scan_rim_centre(canon, sig.ztop, sig.rmax)`, derived from that site's clock
signature in canonical xy. The client has no such quantity. What it has is the seated
pose's origin, which sits close to that rim centre but is not it. Blocking on the client's
number could therefore refuse a span the server would have ACCEPTED, silently costing the
operator a legitimate correction — a worse failure than the 422, because it is invisible.

So the warning fires on the client's approximation, the server stays the authority, and a
refusal now says the marks are still placed (they are — `setDrafts([])` runs only on
success) so one mark can be undone rather than the pair restarted.

TO MAKE IT A REAL PRE-REFUSAL: expose the measured rim centre in WORLD coordinates on the
seated/preview payload — `clock_reference: {rim_centre: [x,y,z], min_lever_mm}` — beside
the existing `pose` block. The client then measures the same quantity the guard does and
can refuse locally with the gate's own bound, with no risk of disagreeing. That is worker
+ BFF + product and wants the worker battery, which is why it is written down rather than
squeezed in beside a UI change.

Item 3 (the auto-mark tool) reduces how much this matters: points proposed from
`PartFeature.defines_rotation` carry a valid lever arm BY CONSTRUCTION, so the operator
never places the bad span in the first place. The guard still belongs on the manual path.

**G. Two battery fragilities the 2026-07-29 slow lane exposed (5 failed, 212 passed).**

Neither was a code regression. Both will recur, so they are written down rather than
re-diagnosed next time.

**G1 — the warmed fixture lives in a directory the running product writes to.**
`test_adjust.py` pins `WARMED_RUN = reports/product/295811960-neodent-gm/runs/
20260728-224101-47bb54` and copies it per test, which correctly stops tests mutating
it. What it does NOT stop is the APP mutating it: demoing Adjust on that case rewrites
the site record, the cap STL and the manifest in place — that is what rework IS. A
session spent driving fit-by-points through the UI left `rotated -5.3°` in the record,
so four tests asserting "reset restores the PIPELINE's own certified pose" compared the
restored pose against a base that already carried an operator rotation, and failed.

Restoring it needed the product's own reset (`rotate_site(..., reset=True)`) because
the directory is UNTRACKED — git could not put it back. After that, 7/7 pass.

The repo's own rule says landed run dirs are immutable; the adjust tools are the
sanctioned exception, which is exactly why a battery must not point at one that is
also demo-able. Fix: give the slow lane its OWN warmed run — copied once into
`tests/data/` and tracked, or minted by a fixture — so no amount of demoing can move
the battery's floor. Until then, anyone who demos Adjust on 295811960 tooth 29 must
expect four red tests and reset the site before believing them.

**G2 — a wall-clock assertion under an 8-way parallel lane.**
`test_a_cold_search_is_cheap_enough_to_answer_at_selection_time` asserts the ceiling
search finishes in under 3.0s ("~1.2s worst case measured"). It passes alone in 1.97s
and failed inside the parallel lane while the BFF suite, the product suite and a
browser shared the box. The intent is right — the number is asked while an operator
waits on a dropdown — but a wall-clock bound measures the MACHINE, not the code, and
`-n auto` guarantees the machine is busy. Fix: measure work rather than seconds (cache
hits, catalog reads), or mark it serial, or widen the bound and say it is a smoke test.

RESOLVED 2026-07-29, the third option, and the reasoning is worth keeping: the bound is
now 30s and the test is renamed to what it actually is — a floor against ORDER-OF-
MAGNITUDE regression, not a budget. The failure mode it exists to catch (a change that
re-reads the catalog per query) is orders of magnitude, so a wide bound loses nothing
real while surviving a loaded box. The genuine budget belongs in a benchmark that owns
the machine and compares against a baseline rather than a constant; it is not a
correctness fact and does not belong in this lane.

**F — CORRECTED 2026-08-01, and the correction is the point.** The paragraph above says
the pre-refusal "is worker + BFF + product and wants the worker battery". That was true
when written and false by the time anyone read it: commit `08edf02` landed
`clock_reference {rim_centre (world xyz), min_lever_mm}` on the seated payload
(`application/adjust.clock_reference`), on every tool result's `pane_payload`, on
re-preview and on Declare's preview (`application/preview.measured_rim_centre_world`).
The BFF forwarded it — but ACCIDENTALLY: `pane_payload` is a bare `dict` on
`AdjustResultView` and the seated handler returns an untyped dict, and no test named the
field, so a tidy-up that added a `response_model` would have deleted it in silence.

LANDED 2026-08-01, product-only plus the passthrough pins:

- `markLeverGuard` (`product/src/domain/adjust.ts`) returns `refusal` when the SERVER's
  own centre and bound are in hand, and `caution` when they are not — the split rides on
  the result rather than being inferred, because "the server will refuse this" and "this
  looks wrong from here" are different claims and only one may block a control. Without
  `clock_reference` the old `spanLeverCaution` approximation is all there is, and it
  still only warns. §10-F's original reasoning is preserved exactly, not overridden.
- It covers a SINGLE mark as well as a span. The server has guarded both since
  2026-07-28 (`require_clock_lever(..., span=False)`); the client warned about neither
  until the span case, so a lone click on the screw access earned a 422 with no warning
  of any kind.
- `applyBlockedReason` consults it, so Apply is inert with the reason on it rather than
  live into a round trip that 422s.
- Two BFF tests now pin the passthrough (`test_adjust_tools.TestSeatedRead`) — the
  seated read and a tool result's `pane_payload`. The second one failed first.

**H. THE FIT-BY-POINTS EVIDENCE GATE (defect, cap7030-zimmer-4.5 2026-08-01; landed).**

The measured half of the client's "this case is not well aligned". On 2026-08-01 at
18:16:36, on that case's tooth 29:

```
site-adjusted | fit-by-points — fit by 3 point pair(s) → 3 observation(s):
                rotated -85.3° (cumulative -85.3°), marks agree to 2.349mm RMS
site-reviewed | reviewed over the live panes                    (nine seconds later)
confirmed     | confirmation sealed over run 20260801-181556-40f164
```

Three pairs missing the adopted rotation by 15°, 38° and 108° — they named three
different rotations, their weighted mean was an average of answers, and NOTHING refused
it. The fleet's measured click scatter is 0.61mm at p90; 2.349mm is not click noise.

WHY NO EXISTING GATE SAW IT, which is the part worth keeping: `judge_rotation` judges the
POSE, never the evidence. A ring-fixed candidate turns the part about its own axis, which
moves the rim by almost nothing at ANY angle, so the 0.35mm stability bound passes −85.3°
as readily as −0.3°; the certification gates read the same pose. And the disclosure that
landed the day before for the neighbouring defect reads `cross_checked === false` — the
fit with NO number — so the fit with a BAD number said nothing anywhere. The surface
treated three mutually inconsistent marks as better evidenced than one honest mark.

`require_pair_agreement` (`application/adjust.py`) refuses a CROSS-CHECKED fit past
`MAX_PAIR_DISAGREEMENT_MM = 1.0`, before any candidate pose is formed, naming the
worst-missing pair so the repair is one undo — the affordance the screw-access refusal
already offers and the product's error footer already promises. Silent below the
cross-check floor: with one observation the residual is zero by construction, there is no
disagreement to judge, and refusing there would delete the documented one-correspondence
capability instead of reading a measurement. The bound is derived, not invented: it is
`MIN_SPAN_MM`'s own line for the same measured reason, and it sits in an empty gap —
healthy fits on this fleet measure 0.02–0.08mm RMS, the defect measured 2.349mm.

STILL OPEN on this case: with the −85.3° refused, cap7030's automatic pose is
position-good and clock-UNVERIFIED (notch corr 0.502 PASSES, prominence 0.079 FAILS the
0.10 gate). §10 does not yet say what the product should offer an operator there.

**I. THE FIVE-PAGE DIRECTION (client, 2026-08-01) — three rulings needed before code.**

Asked: 1 Intake (import scan, mark the cap + its centre, declare the implant SYSTEM) ·
2 Alignment (declare the VARIANT, align over the three panes) · 3 Adjustment (the
tooling, CONFIRMATION, terms and conditions, the alignment reports) · 4 Construction
(pick the construction library, preview the BOOLEAN of construction + scan unified) ·
5 Delivery (payment, then artifacts with previews and downloads).

1. **T&C placement contradicts §10-A.** §10-A deliberately moved the agreement to the
   commercial moment, once, and what shipped binds terms to the CONFIRM act
   (`deliver.py` refuses a confirmation without `terms_accepted`); the client's own
   2026-07-30 words quoted in `deliver.py` say Delivery. Page 3 moves the signature two
   pages upstream, before the construction library is chosen and before a price is seen.
   RECOMMENDED: split the act — alignment reports and an explicit "I accept this
   alignment" review on Adjustment, terms + authorization still gating payment on
   Delivery. If the client insists, record §10-A as SUPERSEDED in the same commit.
2. **The literal page order is self-defeating.** Changing `construction_path` calls
   `clear_current_run`, so Construction on page 4 retires the run the page-3 confirmation
   was measured over — on the happy path, not as an edge case. Either order it
   Intake / Alignment / Construction / Adjustment(confirm) / Delivery, or keep
   confirmation on Delivery.
3. **"Two meshes in the scan" does not hold on the data we have.** Measured over all 9
   fleet scans: 6 are a SINGLE connected component, including the arch whose `sites.json`
   records a true healing cap. On the 3 with a second body (cap6020/6030/7030) that body
   is the sealed screw recess — watertight, NEGATIVE volume, max radius 1.52mm; on
   cap6030 it supplies 1219 of the 1262 points in the detector's own core disc. A
   connected-component split returns nothing on two thirds of the fleet and the recess
   mislabelled as the cap on the rest. Ask whether they mean two FILES instead:
   `application/cases.py` takes `stls[0]` and DISCARDS every other STL in a case folder,
   so a cap-only companion mesh is already being thrown away, and that is plumbing rather
   than segmentation.

Also queued from the same direction, not blocked on a ruling:

- **The cap-only cut.** The display crop is a 9mm sphere (`CAP_REGION_RADIUS_MM`); the
  ALIGNMENT already fits a ≤5.4mm ball at rim height (`_cap_patch_roi`), TIGHTER than the
  display, so "make the alignment based on this mesh" is already true in the strong sense
  and inadmissible in the literal one (a client-chosen bound reaching the aligner is the
  trust inversion the status allowlist exists to prevent). The real defect is that four
  crops exist for four jobs and nothing on screen discloses it. Note the 9mm was the
  CLIENT's own choice over a cap-tight view (`viewer/siteRouting.ts`), for reasons worth
  putting back to them; and `CAP_REGION_RADIUS_MM` is aliased as `SITE_FRAME_RADIUS_MM`,
  so retuning it in place silently re-frames the main stage. A second constant, with crop
  + camera radius + caption moved together.
- **Two library points** (client 2026-08-01). The library half takes exactly one point at
  every layer (`PairIn` is `extra="forbid"` with no `part_point_end`). A library span adds
  no degree of freedom — the unknown is one scalar — but it replaces an ASSUMPTION with a
  MEASUREMENT: the part-side span direction is the radial model today, and the whole
  30° chordal-drop branch exists to catch that assumption failing. Expressible only on the
  free `part_point` path; `PartFeature` carries no direction or extent, so a `feature_id`
  pair and the auto-mark proposer have no second point to offer.

**H, amended after adversarial review (2026-08-01) — the gate's first bound was wrong,
and how it was wrong is the part worth keeping.**

`MAX_PAIR_DISAGREEMENT_MM` is derived from operator CLICK SCATTER, which is the right
derivation for a `point` or a `midpoint` row. It is the wrong one for a `direction` row,
and the mismatch made the gate refuse legitimate corrections.

A span's direction rides its IN-PLANE BASELINE, so `observation_weight` gives it `L²/2`
while a midpoint at the same feature carries `2R²` — on a real trench that is 1.1 against
24.5, and the estimator is right to nearly ignore it. But `residual_rows` measures EVERY
row's residual at the PART's arm, and the RMS over those rows was UNWEIGHTED. So the
reading the estimator had discounted voted at full strength in the statistic that vetoed
the whole fit. Reproduced with the module's own functions:

```
R=3.0mm L=1.5mm 29° off radial   applied +1.65°   rms 1.014  REFUSED   (weighted 0.357)
R=3.5mm L=1.5mm 25° off radial   applied +1.07°   rms 1.035  REFUSED   (weighted 0.313)
R=2.5mm L=1.5mm 25° off radial   applied +2.01°   rms 0.712  passed    (weighted 0.300)
```

Every refused row there is a span the module's OWN `SPAN_RADIAL_TOLERANCE_DEG = 30°`
calls radial — "what two ±0.3mm clicks on a short trench produce on their own" — adopting
a rotation of one to two degrees, i.e. the midpoint's own answer. Crossover is R ≈ 2.7mm
and landed fits carry part arms of 1.2–2.63mm with `rmax` ~3.5mm on a 7mm cap, so the
band is inside the domain, not a corner. And the refusal's words would have been false
besides: with one pair there is no other mark to "re-place it to match".

FIXED by combining the RMS THE WAY THE ROTATION WAS — inverse-variance weighted, the same
weights `circular_mean_deg` used. This changes a PUBLISHED number (`residual_rms_mm` on
the wire and in "marks agree to Xmm RMS"), deliberately: the number reported and the
number judged must be the same number, or an operator reads an agreement figure that
passed a bound it appears to exceed. The motivating defect is unmoved — three free points
at near-equal arms carry near-equal weights (2.355mm plain, 2.360mm weighted).

Also from the same review, fixed here:

- `require_pair_agreement(rows, rms)` derives the observation count from the rows rather
  than taking it alongside them. As three independent arguments they could disagree, and
  a count that outran the rows reached `max()` on an empty sequence — `ValueError` where
  the contract is `AdjustInvalid`.
- `markLeverGuard` FAILS OPEN on a reference it cannot measure. The API layer casts
  rather than validates, so a short `rim_centre` or an absent `min_lever_mm` is
  reachable; `NaN >= x` and `x >= undefined` are both false, so both landed in the
  REFUSAL branch — one produced a permanently inert Apply reading "NaNmm", the other
  threw inside render. A guard justified by "never block a correction the server would
  take" must not fail closed on its own inputs.
- `applyBlockedReason`'s `pose`/`clock` are REQUIRED (still nullable). As optional
  trailing params, an omitted call type-checked and silently returned a live Apply into a
  guaranteed 422; the typechecker found five such call sites the moment they were made
  required. Null is a claim, absence was an oversight.
- The blocked reason names WHICH pair ("Pair 2: …"), matching the worker refusal's own
  one-undo affordance.
- Two tests that were previously unprovable: the axis PROJECTION in `inPlaneRadius` (every
  earlier test used `axis: [0,0,1]` with `z = 0`, where projecting and not projecting are
  numerically identical — a client that skipped it would silently stop refusing the very
  mark this slice exists to catch), and the component wiring (severing `clock={clock}` is
  now a failing test; before, it left the whole product suite green).

DEFERRED, recorded rather than done: an advisory band below the bound (a 0.99mm fit still
renders identically to a 0.02mm one, which is a narrower version of the same complaint
this item is written against); `data-role="span-caution"` now also carries single-mark
refusals and should be renamed `mark-guard`; `ClockReference.rim_centre` should be a
`readonly [number, number, number]` tuple rather than `number[]`.

**J. THE LIBRARY SPAN — tool 1 of the client's two (2026-08-01; landed).**

"Fit by points needs to have TWO points in the library." The client asked for both
readings of that to exist as SEPARATE tools; this is the first.

WHAT IT BUYS, stated precisely because the surface's wording invites the wrong answer:
it adds NO degree of freedom. The unknown is one scalar rotation and always was, and two
library points cannot constrain more than one library point plus a direction can. What it
adds is that the part's span bearing stops being ASSUMED and becomes MEASURED. Today
`observations_for` compares a scan span's bearing against the part half's AZIMUTH under
the radial model — "both ends of a trench lie along the radius through its azimuth" — and
`SPAN_RADIAL_TOLERANCE_DEG` plus the whole chordal-drop branch exist for one reason: to
catch that assumption failing. Span the same feature on the library and the two bearings
are the same kind of quantity, so a CHORD MATCHED BY A CHORD is a valid direction reading
instead of a discarded one. Pinned on the same scan chord, 60° off its own radius: without
a library span it yields one observation and a dropped direction; with one it yields two,
and the direction asks for 0° rather than the 90° the radial model would have inferred.

- `Correspondence.part_point_end` / `is_part_span`; `_part_half` measures the bearing and
  guards the library span's MIDPOINT against `MIN_LEVER_ARM_MM` — the scan half's own
  discriminator, for the same reason: a library span across the part's axis is a diameter
  through it, and names the axis rather than a clock angle. The part span is validated by
  `validate_span` against `_PART_SPAN_MAX_MM`, so one operator act is not judged two ways.
- The audit carries `direction_reference: "library-span" | "radial-model"`. The same
  clicks now produce different numbers under the two models, so the record says which one
  it read under — the chordal-drop note's precedent, applied to why a direction COUNTED.
- Only expressible beside a free `part_point`. A `PartFeature` carries azimuth, radius and
  z — no direction, no extent — so a named feature has no second point to give, and
  auto-mark cannot propose a library span without new part-annotation geometry. Refused in
  BOTH the wire corpus and the application prelude, deliberately: the wire is not the only
  caller, and the prelude runs before a mesh is parsed.
- A library span FORCES the scan span (`newPairDraft` normalizes it). A bearing and a
  single click have nothing to subtract; the worker refuses the shape, so the surface
  cannot let the operator build it. An act that can only 422 should not be constructible.
- `paneArming` arms pane 1 for BOTH library slots. It matched `slot === "part"` only, so
  a started library span left pane 1 dead, waiting on a click no pane would accept —
  found by writing the test first, not by using the app.

STILL OPEN: tool 2 (visual matching). Now that tool 1 exists its distinct job is narrower
than it looked, and the two readings need the client's own words before either is built:
two library marks where the fit consumes only the FIRST changes no number, so this
codebase's doctrine requires the surface to say so out loud; two library marks matched as
INDEPENDENT pairs already changes numbers honestly (two observations clears the
cross-check floor) and is a different build. Do not invent the product here.

**K. THE DISPLAY BAND WIDENS 9 -> 11mm (client, 2026-08-01; landed).**

The client's first ask was the opposite — "the panel cannot have a lot of extra of the
scan" — and reversed once the measurement was on the table: the ALIGNER never sees this
crop. It cuts its own ROI server-side, a ball at rim height of radius
min(rim_r + 1.2, 5.4)mm (`auto_flow._cap_patch_roi`), TIGHTER than the display and
derived from the seat rather than the operator's centre. So this bound trades context
against apparent cap size and trades nothing else; it cannot move a millimetre of any
fit. With that established the client chose MORE context, not less.

Changed IN PLACE rather than behind a second constant, which reverses the earlier
recommendation and should be read as deliberate: `CAP_REGION_RADIUS_MM` is aliased as
`SITE_FRAME_RADIUS_MM` precisely so the main stage and the verify panes cannot disagree
about what "this site" means, and `siteRouting.ts` says so in as many words. Widening the
crop SHOULD widen the main stage's framing — that is what sharing the constant is for. A
second constant would have been the change needing justification.

Measured consequence, stated so it can be dialled: at 45° FOV an 11mm radius puts the
camera ~40mm out and shows ~33mm of jaw; the 6.16mm cap reads ~19% of the view (~84px on
the 444px stage), down from 23% at 9mm and still far above the 3.1% / 14px of whole-arch
framing. Every millimetre here costs apparent cap size. One line to change.

Trap for the next person: the pane caption and `siteFrameFor`/`partCameraFrame` take the
radius as an ARGUMENT and echo it. Their tests must move the input WITH the expectation,
or they assert a transformation that does not happen. Only `siteRouting.test.ts` and the
sceneController characterization actually pin the constant — the latter now reads
`SITE_FRAME_RADIUS_MM` instead of a literal, so it cannot silently describe an old radius.

**L. THE SECOND BODY IS THE SEALED SCREW RECESS — measured 2026-08-01, and what it can
and cannot be used for.**

The client confirmed this is what "two meshes in the scan" meant: where a second
connected component exists it IS the sealed screw recess, and they asked whether it can
be used when available. Measured on all three fleet scans that carry one, against each
case's own shipped pose:

```
                    verts   extent (mm)        watertight  volume   centroid vs pose AXIS
cap6030-neodent-gm   8377   2.77x2.67x3.74     yes         -12.98   0.171mm  (agrees)
cap6020-neodent-gm   3796   2.51x2.44x2.04     yes          -3.69   1.590mm
cap7030-zimmer-4.5   3099   2.37x2.25x2.20     yes          -2.92   2.069mm
```

WHAT IT IS GOOD FOR, and it is a real answer to the identification ask: when present it
is topologically isolated, watertight and negative-volume, so it can be labelled
"screw recess, not tissue" EXACTLY — no heuristic, no island, no contamination estimate.
Its centroid is also stable (vertex mean and area-weighted mean agree to ~0.015mm), so it
is a genuine independent witness of where the screw access sits.

WHAT IT CANNOT DO, all three measured rather than assumed:

1. NO CLOCK. The shell is BLOBBY — singular values 0.665/0.549/0.435 on cap7030,
   0.895/0.822/0.722 on cap6030 — so it has no reliable principal axis, and the
   "own axis vs pose axis" readings (66.5°, 30.3°, 82.9°) are noise, not measurements.
   It therefore cannot help the rotation, which is cap7030's actual defect.
2. NO COVERAGE. Present on 3 of 9 fleet scans. Anything that DEPENDS on it works a third
   of the time, so it can be an extra, never a step.
3. NOT TRUSTWORTHY AS TRUTH. Its centroid agrees with the shipped pose on cap6030
   (0.171mm) and disagrees by 1.59mm and 2.07mm on the other two — on cap7030, whose seat
   is the BEST on the fleet by fit.avg (0.395mm) and fit.max (1.183mm). Either the recess
   or the pose is wrong there and this measurement cannot say which. The recess
   instrument is separately convicted of bias in this repo's phantom-clock work, which is
   why the recess-anchored clock fallback was retired for the 7030 in 2026-07-23.

THE SHAPE TO BUILD, therefore: a REPORTED CROSS-CHECK, never an input. When the second
body exists, say so and say how far its centre sits from the axis the fit used. On
cap7030 that reads 2.07mm — a loud, independent signal on precisely the case the client
called badly aligned, arrived at without the island, the void detector, or any tunable.
Same doctrine as SHADOW_ISLAND: measured, reported, consumed by nothing.

Compare the pipeline's own `delivered_channel_vs_recess` on the same sites (1.254 /
0.912 / 0.953mm): it measures a related disagreement through the void detector, and
disagrees with this cleaner instrument. Which is right is unresolved and worth one
measurement before either number is put in front of a client.

**M. THE FIVE-PAGE FLOW (client design "ArTech End-to-End Flow", 2026-08-01; stage model
and the library page landed).**

The design keeps the ENGINEERING KEYS and changes only the titles, which is why this cost
a fraction of what §10-I feared: `declare` is titled **Alignment**, `adjust` is
**Adjustment**, `deliver` is **Delivery**, and a new `library` — **Construction library**
— sits fourth. Every route, guard, session field and BFF resource survives untouched.

Gating, verbatim from the design and now in `flow.ts`: `library` needs a DONE run and
every site resolved — the condition Deliver used to hold alone — and `deliver` adds a
chosen construction part, because Delivery is what prices and cuts it.

**THE DEADLOCK THE DESIGN WALKS INTO, and what was done about it.** `reach.library`
requires `runState === "done"`, and picking a part is what satisfies `reach.deliver` —
but changing the effective `construction_path` calls `clear_current_run`
(case_sessions.py:1124) and regresses every site. Taken literally the happy-path forward
walk retires the run the page depends on, and Delivery never opens.

Measured, the fix is real and cheap in principle: THE POSE IS CONSTRUCTION-INDEPENDENT.
`construction_mesh` enters `auto_flow` at exactly four places — two signatures, the
forward, and the product build — and every alignment, seat, clock and confidence
computation runs on the CAP template. So a part change owes a RE-EMIT, never a re-align,
which is what §4's `emit_from_poses` was priced for.

`emit_from_poses` DOES NOT EXIST — grep returns five hits, all of them prose in this
document. So the page ships telling the truth about today's cost (`constructionChangeWords`,
the same sentence Deliver's picker uses) rather than pretending a change is free. The
flow does not lock: a changed part retires the run, the rail honestly says the library
"opens once the run completes", and re-running returns the case. Picking the part that is
ALREADY effective is not an act at all — the reset boundary is keyed on the effective
value changing — so the ordinary walk costs nothing.

When `emit_from_poses` is built, these hazards were measured and must be answered:
`emit_case_package` rewrites `implant.json` wholesale and would ERASE `record["adjustments"]`
(the append-only operator provenance), so a re-emit must merge; the design-rule gate is
per (construction part × cap) and can REFUSE at emission, arriving at a point in the flow
that has never had to surface a refusal; the scanbody filename embeds the VENDOR, so a
vendor change must delete the old name and drop its manifest row (`register_package_files`
never removes); and the QC PNGs are cap+pose, so a naive evidence re-derivation would pass
while `prosthesis_cad.stl` changed underneath — `clear_confirmation` must fire explicitly.

**WHAT THE PAGE DELIBERATELY DOES NOT SHIP.**

- **The design's four parts.** `["ti-base", "Titanium base", "$18 / site", "3 days"]` and
  three siblings are invented: the real catalog carries `path_id`, `label` and `vendor`
  and no price or lead time anywhere. The page reads `constructionOptions` — the same
  source Intake's dropdown and Deliver's picker read — so there is no fourth copy of the
  list, and it quotes no money the server never said.
- **The design's preview.** It LOOKS like the client's "preview of the boolean with the
  construction and the scan unified in a view" and is not: lines 511-514 are a static CSS
  disc with zero data bindings, which reads neither the chosen part nor the scan nor any
  geometry, and it wears the SCAN CAP's own palette so it depicts the cap. Porting it
  would ship a control that looks like the answer — the silent no-op this codebase
  forbids. `libraryPreviewPending()` states the gap instead. The real thing needs a mesh
  the BFF does not serve: `library.py` serves a catalog part alone, and the only unified
  geometry that exists is the run's own `-arch-with-constructions.stl`, emitted AFTER
  this page.

One consequential fix found by the typechecker rather than by eye: DeclareStage gated its
whole move-forward block on `isReachable("deliver")`. That was exactly right until a page
appeared between them; with Deliver now needing a part picked two stages later, the fork
vanished from Alignment until work that happens after it. It reads `library` now — the
condition it always meant — and the skip fork lands on the library rather than Delivery.

STILL OPEN: the confirmation's placement. The design's rail sub-line puts it on
Adjustment ("tooling, reports, confirmation"), which is §10-I ruling 1 and remains
unanswered; confirmation is untouched by this slice and still lives on Delivery.

**M2. THE UNIFIED PREVIEW, ANSWERED WITH GEOMETRY THAT ALREADY EXISTED (2026-08-01).**

§10-M shipped the library page stating that the client's "preview of the boolean with the
construction and the scan unified in a view" was not built. That was true of the DESIGN's
preview and false of the system: the run already emits exactly that mesh.

`-arch-with-constructions.stl` (auto_flow.py:2471) is the arch with every site's
construction part posed into it — construction ∪ scan, in one file. The library page is
reachable ONLY over a done run (`flow.isReachable("library")`), so on this page that file
is on disk by construction, `previewTabs` already matches it by suffix, and
`GET /runs/current/preview-mesh/{filename}` already serves it behind the same done-run
precondition. No new worker code, no new BFF route, no new geometry — the answer was one
suffix match and a component that already existed.

ONE TAB, not Deliver's three. Deliver shows the cap arch, the construction arch and the
per-site prostheses because Deliver is reviewing everything that ships. This page asks one
question — what does the construction look like ON the scan — so the cap arch (the scan
WITHOUT constructions) and the prosthesis (the part WITHOUT the scan) are both off-topic
and deliberately absent.

WHAT THE CAPTION HAS TO SAY, and why it is not decoration: the mesh is the RUN's, built
with the part the run used — not the one the operator is hovering over. Picking a
different part cannot change the image until the case re-runs. Saying so is the whole
difference between a preview and a promise; a surface that let the operator believe the
picture tracked their selection would be claiming geometry nobody computed. That is the
same rule the fit's chordal-direction note and the cross-check caution already follow.

The gap words survive for the case they were written for: a run that emitted no such file
renders the stated gap rather than a dead viewer, the same discipline `previewTabs`
applies to every tab it cannot fill.

STILL NOT BUILT, and now the only part that isn't: previewing a part the case has NOT run.
That needs `emit_from_poses` (§10-M's hazard list) or a client-side compose of the catalog
part mesh against each site's shipped pose. The second is cheaper than it looks — the page
has the poses and `library.py` already serves a part mesh — and is the natural next slice.

**N. THE DESIGN COMP CONTRADICTS ITS OWN RAIL ON WHERE CONFIRMATION LIVES (measured
2026-08-01, before moving anything).**

The client ruled that confirmation and T&C move to Adjustment (page 3), citing the
five-page spec and — as corroboration — the comp's rail sub-line for that stage,
"tooling, reports, confirmation".

THE SUB-LINE IS THE ONLY PLACE IN THE COMP THAT SAYS SO. Its actual confirmation control
is `toggleClinical` at artech-flow.html:610, and an sc-if nesting walk puts that control
inside `<sc-if value="{{ payOpen }}">` (opened line 583) — the PAYMENT DIALOG. `payOpen`
is reset to false on every `goStage` and opened only from Delivery, and the pay button
itself reads `st.clinical ? "pay … & release" : "confirm the metrics to pay"` (line 1555):
the confirmation GATES PAYMENT and sits in the payment dialog.

So the comp implements §10-A's position exactly — "legal weight belongs at the commercial
moment, once" — and matches both what shipped and the client's own 2026-07-30 words
quoted in `bff/resources/deliver.py`. Three artifacts agree; one rail sub-line does not.

`st.clinical` and `st.terms` appear nowhere in the comp's Adjustment block. What the
Adjustment stage actually renders is the toolset and the site queue; the sub-line's third
noun has no control behind it.

RECOMMENDATION UNCHANGED, and now on firmer ground than when it was an argument about
legal placement: split the act. Adjustment gets the ALIGNMENT REPORTS and an explicit
"I accept this alignment" review — a workflow attestation, which is what a stage of
tooling can honestly carry — and the terms plus the authorization stay gating payment on
Delivery, where the comp, the plan and the client's own quoted words all put them.

IF THE CLIENT STILL WANTS THE FULL LEGAL ACT ON PAGE 3 after seeing this, the hazard to
state to them is mechanical, not aesthetic: a construction change on page 4 fires the
reset boundary, and `clear_confirmation` (session.py:525, called from case_sessions.py:
1493 and :1628) retires the signature. Signing on 3 and choosing on 4 means the signature
falls whenever the choice actually changes. Either pages 3 and 4 swap so the signature is
last, or the surface must say out loud that picking a different part re-collects it.

HELD, deliberately: the Deliver construction-picker removal (§10-M's three-homes finding).
It lives in the same release ladder any confirmation move would restructure, so doing it
now would mean rebuilding that ladder twice.

**O. DECISIONS TAKEN 2026-08-02, so the next reader stops re-deriving them.**

1. **Confirmation SPLITS.** Adjustment gets the alignment reports and an explicit
   "I accept this alignment" review — a workflow attestation. The terms and the
   authorization stay gating payment on Delivery, per §10-A, the client's own 2026-07-30
   words, and their comp's own control placement (§10-N). This satisfies the five-page
   spec's intent for page 3 without contradicting three artifacts to follow one rail
   sub-line.
2. **Zoom is GLOBAL**, not per-pane — one control moving all three cameras, as the comp
   has it. The client's words: "global is probably better on adjustment views".
3. **"Two meshes" means TWO SHELLS IN ONE FILE.** Recorded with the measurement that
   contradicts it, because both facts matter: on this fleet 6 of 9 scans are a SINGLE
   connected component, and on the other three the second shell is the sealed screw
   recess — watertight, negative volume, max radius 1.52mm — not the cap. So the reading
   is settled and the data still says a component split cannot separate cap from gum.
   §10-L's recommendation stands unchanged: use the second shell as a REPORTED
   cross-check (it is definitively not tissue), never as a pose input.
4. **Deliver's construction picker is CUT.** Three surfaces wrote one choice; Deliver's is
   the one where a change retires the confirmation just sealed. Intake's stays (it is what
   makes `choices.complete` true) and the library page is the flow's own home for it.
5. **Per-part price and lead time are NOT shown.** They do not exist in the catalog and
   pricing is server-derived; showing them is a catalog + BFF change, not a UI one.
6. **Drag-and-drop upload is NOT built.** No write path into `data_root`, no multipart
   endpoint, no mesh validation. The stated arrival procedure stands; upload is its own
   project.
7. **`emit_from_poses` is DEFERRED.** The flow works, and the hazards in §10-M are sharp —
   chiefly that a naive re-emit erases `implant.json`'s append-only operator provenance.
8. **jsdom arrives WITH focus management**, not before. Until then the dialog listener is
   hand-verified and says so.
