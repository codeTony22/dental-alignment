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
GAP (found 2026-07-28 answering the client's multi-cap question). LANDED SINCE (verified
2026-08-02, §10-AB sweep): the fix shape below shipped end-to-end — `production.note`
rides `AssuranceSite.production_note` (resources/deliver.py), a noted-but-ready row NEEDS
ACKNOWLEDGMENT exactly like a flagged one (domain/deliver.ts, `needs_acknowledgment` in
session.py — the "should probably flag" call, taken), and the note renders on the row,
the checkout metric strip and the report expand, pinned by tests in both apps.**

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

LANDED SINCE (verified against the tree 2026-08-02, §10-AB sweep): all three. The
advisory band arrived as §10-Q; `span-caution` is gone from the tree (`mark-guard` at
AdjustStage.tsx, with the alert/status role split); `ClockReference.rim_centre` is the
readonly tuple in api/client.ts — `domain/adjust.ts`'s `ClockReferenceLike` deliberately
stays wire-tolerant (`readonly number[]`) because its fail-open guard is the tested
behaviour for a short vector.

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
   hand-verified and says so. *(Landed later that day: jsdom as a product-only devDep with
   per-file pragmas, `useDialogFocus` on all four dialogs — autofocus/trap/restore — the
   checkout's Escape aligned to its own Cancel rule, and DeliverStage's dead pre-hook
   Escape listener deleted. The node default stands; only the hook fixtures opt in.)*

**P. THE ZOOM, AND TWO DEFECTS THAT ONLY THE BROWSER FOUND (2026-08-02).**

§10-O.2's global zoom shipped as a signed integer counter held by each stage's container
(`packages/viewer/src/viewer/zoom.ts`, `WorkspaceToolbar`'s −/+ pair). A counter and not an
absolute distance because the scroll wheel drives the same camera: an absolute zoom would
drag the view back to the button's opinion on every unrelated re-render, and the two
controls would fight. Each pane applies the delta it has not applied yet, so a pane that
MOUNTS into an already-zoomed workspace joins at the current level instead of replaying the
history onto a camera that was just framed.

Both of the following were caught by opening the page. Every markup test was green while
each was live, which is the standing lesson of §10's verification rule, now with two more
instances behind it.

1. **THE COUNTER OUTRAN THE CAMERA.** Clamping only the distance scale left the counter
   free: forty presses of + parked the camera at the floor — correctly — and left the
   level at 42, so the operator then pressed − about thirty-five times before anything on
   screen moved. A button that accepts every press and answers none is worse than a dead
   one. `clampZoomLevel` saturates the counter at the band's own edge, so a spent control
   reports itself spent and one press back moves the camera at once. The bounds are
   DERIVED from `MIN/MAX_ZOOM_SCALE` and the step, not chosen twice.

2. **THE PANE GRID RENDERED UNDERNEATH THE TOOL DRAWER.** `grid-auto-rows: minmax(220px,
   1fr)` is a MINIMUM, so at two rows the grid demands 452px however little it is given. At
   1280x720 the stage has 606px and the drawer takes 168: the grid box measured 183px, the
   second row spilled to 457–677, and the drawer occupied 416–584. 127px of the union pane
   — the verdict pane — rendered under the tool tabs, clipped by nothing and reachable by
   nothing. Fixed by scrolling the grid inside its own box, which is the shell's own
   doctrine (the page never scrolls; regions scroll inside themselves). Letting the rows
   collapse instead was rejected: at 183px for two rows a pane is 85px and shows no
   geometry at all.

   **STILL OPEN, and deliberately not tuned here.** At 1512x950 the grid gets 343px of the
   452px it wants, so the union pane needs a scroll to reach. The stage's own budget is
   toolbar 57 + panes 381 + drawer 238 + advance 128: the two chrome bands take 44% of it.
   Retuning that split is a slice-B question the client has not been asked, and it is not
   the same defect — every pane is present and reachable, which is what "see everything at
   once" (2026-08-01) was about. Their objection was to panes DISAPPEARING behind a
   switcher, and nothing disappears.

**Q. THE ADVISORY BAND UNDER THE EVIDENCE GATE (2026-08-02).** §10-H's own review noted
that a refusal alone leaves the band beneath it flat — a 0.99mm fit printed the identical
sentence to a 0.02mm one, a narrower version of the very "a fit with a BAD number said
nothing" complaint the gate was written against. `agreement_words` now words the near-miss.
0.50mm is read off the measured fleet, not picked: healthy fits scatter 0.02–0.331mm, the
two refusals were 1.546 and 2.349mm, and nothing was observed between. It DISCLOSES rather
than gates — the operator with a reason to accept a 0.7mm fit still can, the same division
of labour the one-observation clause uses.

**R. ONE NAV BAR ON A CASE ROUTE (client 2026-08-02).** "There are two nav bars, take off
the ArTech Software Labs, and All cases should be also navigable in the same nav bar."

This retires slice A's stated concession. That slice chose to *visually merge, structurally
keep* — `Shell` went on rendering the brand bar and `CaseShellView` stacked its `#0e1613`
band directly beneath it, on the reasoning that the pair would read as the comp's single
header and cost no data-flow change. It did not read that way. Two dark bands, each with
its own link out of the page, are two navigations however tightly they are stacked.

`Shell` now renders its header only where it is the ONLY bar — the worklist and `/terms` —
and the case band carries "← All cases" itself, first, before the stages. The way out comes
first on purpose: abandoning the case is a different kind of move from walking along it, and
the one control that leaves should not sit at the end of the row of controls that continue.

`rendersOwnNav(pathname)` matches on the path rather than taking a prop, because `Outlet`
gives a parent no way to ask its child what chrome it brought, and a context is a data-flow
change for a question the URL already answers — the same trade slice A declined, declined
again for the same reason and now with nothing left to pay for.

Cost and gain: the header assertions in `Shell.test.tsx` MOVED rather than being deleted —
half of them (the link exists on a case route) now live in `CaseShell.test.tsx`, and a new
one pins that no brand bar renders there, so the two halves cannot both quietly disappear.
The reclaimed ~56px went straight to the panes: at 1512x950 all three are visible on Adjust
where the union pane previously needed a scroll (§10-P.2), which is a real dent in that
still-open item without touching the drawer/advance split.

**S. THE ALIGNMENT PAGE'S SECOND SCROLL, AND THE CARD PICKERS (client 2026-08-02).**
Their words: "view needs also to see the 3 panels, there is a lot of real estate for the
buttons … The second scroll section is uncomfortable, hides the 3 vertical panels view
side by side. the implant variant selection needs to be drop down. The confirmation
button is in a weird spot. There is multiple scrolling sections here which is really
weird, we need to be more cohesive and organized about the information we show."

What changed, and the reasoning each change carries in-code:

1. **The two-across pane tier is dead.** `paneColumns` and the ≤1600px media block wrapped
   the panes two-up on the guess that three-across is slivers at 1440 — but two-up ALWAYS
   puts the union pane on a second row, and a second row is a scroll at every height this
   app runs at, so the tier hid the verdict pane to protect the width of its inputs.
   Three across down to 1180px, where the shell itself stacks. One row means the grid
   never scrolls and the chrome ladder stops engaging at ordinary window sizes — the
   1280x800 fixtures that pinned "compact" now honestly pin "full", and the ladder's
   fixtures hand it real height scarcity instead.
2. **Both pickers are selects on one slim row.** The system cards and the six variant
   cards were the second scroll. Every claim the cards made moved INTO the options — dims,
   the declared one selected (controlled by the server's fact), detection's proposal
   attributed and vanishing on declaration, the superseded shelf a labelled optgroup —
   and the switch-consent ceremony is untouched: the system select ASKS, springs back
   until consented.
3. **The advance is one band.** `.panel__actions--advance` stacks as a column for the
   work-column footers it was born in; inside `.workspace-advance` that made
   `flex: 1 1 260px` mean 260px of HEIGHT — a one-line attestation summary in 84px of
   grey, and the bar overflowing into its own scrollbar (230 > 195, the "weird" scroll).
   Across the stage's foot it reads left-to-right: the set faced, its consequence, the
   two doors — which are now natural-width `button--small`, ending the bar instead of
   dominating it.
4. **The confirmation stays under the panes it attests** — its weirdness was the scroll
   fragmentation around it, not its position; with one coherent stack it reads as the
   panes' own footer.
5. **Intake's choices card**: overrides only (the `.decode-*` bases are the demo's copy,
   below-marker overrides beat diverging it) — consistent 34px controls, an inlined-SVG
   chevron, the app's green focus ring instead of the UA blue, the jaw pair as one
   segmented control, the ceiling line styled as the readout it is.

Verified by opening it at 1512x950 and 1280x800: three panes side by side on BOTH
workspace stages, `stageScrollers: []`, document scroll 0.

**T. THE QUEUED FIVE, LANDED (2026-08-02, three agent waves, each gated and committed).**
The popover (§10-O's own gap list), dialog focus + jsdom (closes O.8), the unrun-part
preview (the §10-M2 slice), re-preview on Adjust, and the unverified-clock affordance —
which CLOSES §10-H's open question ("what the product should offer an operator there"):

- The ROTATION pill now reads "+21.7° · unverified" when the run itself refused to trust
  the instrument — the same honesty the PAIRS pill already had. A naked degree figure
  from evidence:"none" was the pill lying by omission.
- The notice on Adjust relays the server's fact, states plainly that NO tool re-reads a
  clearer signal off the same scan, and routes to auto-mark — promising exactly what a
  human act can land (a CROSS-CHECKED fit: two or more marks that agree) and explicitly
  NOT a flip of the flag. The forbidden promise is pinned absent by test. This is a
  CLASS, not a quirk: 3 of 8 fleet cases carry rotation_unverified on their newest run.
- Re-preview is a re-READ: the body-less POST existed with zero consumers; the control
  promises nothing but a fresh read, and renders the server's changed/unchanged words.

Follow-ups flagged, not built: the Library pane previews the ARMED candidate only — a
case whose effective construction has no run yet still shows the pending gap (separable
slice); Deliver's inert "unverified" em could route back to Adjust's tools (client call,
§10-N territory); the session log is reachable only from the two workspace toolbars.

**U. THE THREE ROWS OF CHROME (client 2026-08-02).** "There is three rows of buttons which
takes a lot of real estate in the screen for the panels. Also on the tooling part."

The third row existed to hold one button: the panes' own strip carried "link views" and
nothing else. The toggle rides the workspace toolbar now, beside the zoom it is kin to —
one act, all three cameras — with the link STATE lifted to the stage the same way the
zoom counter was (controlled `options.linked` on the scene hook; DeclarePanes threads it
down; the hook keeps only the OrbitLinkGroup plumbing). The panes' strip returns only
while a pane is maximized, when the 1/2/3 switcher genuinely needs it. One deliberate
behavior change: the toggle no longer disables while maximized — the toolbar cannot see
the maximize, and a standing preference that takes effect when three panes return is the
more honest control anyway.

The drawer's head merged: title + re-read on one row, tabs directly under; the clock
notice keeps its own full-width line because it is a paragraph of fact, not a control.
The stat pills quieted (they are a readout, not controls). Measured at 1280x800: toolbar
132→72px, drawer head −40px, panes 220→294px — the floor unstuck.

**V. THE DROPDOWN REVERSED, AND THE TOOLING STOPPED SCROLLING (client 2026-08-02).**
"The dropdown buttons need better styling - the implant variant should not be a dropdown
and we need the suggested. I am not a fan of the scrolling on the tooling, it is too much
scrolling up and down."

1. **The variant picker goes back to chips**, reversing §10-S.2 the same day it landed —
   and the reason is visible in the markup. The server has published `suggested_variant`
   per site since 5a precisely so the operator can SEE what detection proposed for the
   site they are declaring; inside a collapsed select that became a word in an option
   nobody reads until they open it. On a chip it is a badge on the face of the page. The
   real-estate complaint that drove the dropdown was real and is answered by the chips'
   SIZE — one dense wrapping row, not a grid of cards. The system picker stays a select:
   nothing is attributed on it that a closed control hides.
2. **The selects read as controls**: resting border, hover, shadow, and the amber
   "still owed" weight behind `--needs`, which had the class and no tone.
3. **The tooling's scroll was a flex-order bug, not a height budget.** The drawer was
   `flex: 0 1 auto` beside a pane region that GROWS, so the panes swallowed the free
   height and the drawer was shrunk into a scroll even on a tall window — measured at
   1512x950: panes 479px, drawer 239px showing 297px of content. The drawer takes its
   content first now (`flex: 0 0 auto`, capped) and the panes take the remainder,
   yielding first when the stage is genuinely short — safe, because the grid scrolls
   inside itself and each pane holds its 220px floor.
   Drop also moved into the head row beside the re-read: it is the same KIND of act
   (about the site, not about whichever tool is open) and it sat past the tool body, so
   reaching it always cost a scroll. Its note survives where it says something NEW —
   dropped, the hold is a DRAFT until Deliver's confirmation signs it; undropped, it
   only restated its own button label and rides in `title`.

Measured after, 1280x800 AND 1512x950: the tool panel does not scroll at either, and
all three panes stay up.

**STILL OPEN — needs the client.** "We need the adjustment and alignment to look more
like the claude designs": the comp is not reachable from this session. It is not in the
repo, `~/Downloads` has no HTML, and the claude.ai design-system project lists zero
files. Every comp fact this plan cites survives only as extracted notes in code comments.
Also unresolved: which surface is "green on the preview on construction" — both
construction previews (the library page's run mesh and Deliver's "Construction in arch")
render the palette's steel blue `#7d93b8`, and `PartPreview` passes `PALETTE.construction`
explicitly. The only green in a preview is the CAP view, which is the established
convention Deliver's own advisory text relies on ("visually confirm the green cap covers
the scanned cap in view 1").

**W. THE COMP, READ DIRECTLY AT LAST (2026-08-02).** The file finally reached a readable
path (macOS TCC blocks ~/Downloads for this process even unsandboxed; the client copied
it out). It is a bundler-packed standalone: base64+gzip assets in a `__bundler/manifest`
script with the real markup in `__bundler/template`. Unpacked, served on :8777 and
rendered side by side with ours at 1512x950 — so this section is measured against the
comp running, not against notes.

**Confirmed, and now first-hand rather than second:** the comp's `deviation()`,
`verdict()`, `tol()` and its budget bars' `f: value/tol` are all client-side arithmetic
(`comp-body.html`, the `Component` class). Its MAX DEV pill is `this.deviation(site)`.
Its `pushLog` is a browser array. None of it ports; all of it is already refused.

**Ported:**
- **The stat strip is inline** — micro-caps key, value, hairline separators, no per-pill
  box. That is the comp's own rhythm and it is what let its toolbar be ONE row.
- **The tool panel opens on its tabs.** The comp has no "Tools — tooth N" heading: the
  tabs name the tool and the toolbar's chip names the tooth.
- **The queue column is a list, not a card** — micro-caps label over a one-line note,
  no panel border. A card inside a 168px column reads as a box inside a box.
- **Abbreviated control labels** (`occ / A / B`, `⛓ link`, `Numbers & log`) — the comp's
  own instinct (`occ · buc · mes`). Ours keep "side A/B" rather than the comp's
  anatomical buccal/mesial: those need a measured roll, and naming a direction the app
  cannot compute is the lie §10 already refused. The meanings stay in `title`.

**Deliberately NOT matched, with the reason:**
- **Our toolbar still wraps to a second line at 1512.** Measured: the row needs 1356px of
  1308. The remaining excess is content the comp does not carry — it shows ONE invented
  MAX DEV where we show the run's own DEV RMS **and** DEV P90, each with a `(run)` /
  `(preview)` qualifier naming where the number came from. The comp needs no such
  qualifier because its number has no source. Dropping either would buy the row by
  spending provenance, so the row wraps.
- The comp's re-preview button reads "re-preview — this will pass" — a promise of an
  outcome, already recorded as forbidden. Ours reads "Re-read this site's numbers".
- The comp's variant chips + system dropdown on one row under the panes is exactly what
  §10-V restored, independently — the client's reversal and the comp agree.

**X. THE COMP'S SILHOUETTE, BOTH WORKSPACES (2026-08-02, "why are we not matching the
designs").** The honest answer to the client's question: the port went structure-first —
behaviour, trust rules, data flow — and left the tool panel's clothing and the nav
placement unmatched. Closed now, measured against the comp RUNNING (§10-W):

1. **Stage nav returned to the queue column's foot** on both workspaces — the comp's own
   sticky footer (template 465-469), which slice B had moved to a stage-wide bar. Forward
   above back, stacked, full-width in the column; the consequence sentence and the
   set-faced summary ride with the doors they inform (summary capped at 96px scroll so a
   full arch cannot push the doors off screen). The width under the panes now belongs
   entirely to the tools — which is the comp's whole silhouette.
2. **The tool panel opens on its tabs** — compact rounded pills, natural width, active =
   the READY chip's green-tinted outline (the comp's active tab is an outline, not our
   old filled slab). Site acts (re-read · drop) sit in ONE row at the panel's FOOT, the
   comp's arrangement — safe to do now because §10-V.3 made the drawer take its content
   before the panes grow, so the foot is as reachable as the head was.
3. **Queue titles are the comp's**: "Adjustment queue — flagged first" / "Sites in this
   case", rendered by the existing micro-caps rule.
4. One self-inflicted defect caught by screenshot: the acts-row extraction left a JSX
   comment in CHILD position, where a bare /* */ RENDERS — it printed itself onto the
   page. Braced. (The third such screenshot-only catch this week; the node suite is
   structurally blind to all of them.)

**"Alignment is not working properly" — could not reproduce.** On cap7030 itself: side A
re-frames all three panes together (feet all read "down the side A viewpoint", part
edge-on, union edge-on), occ returns, pressed states track, zoom and link live. What the
client's screenshot DOES show is the fleet's worst fit wearing all its honest labels —
DEV RMS 0.427/p90 0.728 (highest of the eight), ROTATION +21.7° · unverified, PAIRS 1/8 ·
unchecked, capture marginal — on the case whose clock no instrument can verify (§10-T).
If "not working" meant one of those numbers, the numbers are the finding, not a defect.
Awaiting specifics if it was neither.

**Y. ADJUSTMENT, REGION FOR REGION (2026-08-02, "revamp the whole page").** Three more
comp facts landed, each read off the running comp:
1. **The toolbar ends on the popover control** — the comp closes its strip with
   "▸ budget & log"; ours closes with "Numbers & log" via a new `endSlot` on the shared
   toolbar (children stay left, for Declare's arch opener). With the strip thinned, the
   toolbar is ONE row at 1512 — the wrap §10-W accepted is gone without spending the
   DEV RMS/P90 provenance that caused it.
2. **The resting colorbar is two lines** — the thin ramp and one summary line naming the
   scale ("▸ signed ±0.50 mm · legend & stats"). The chooser pills and tick numbers fold
   into the legend. The 2026-07-31 ramp-identity rule is satisfied HARDER than before:
   the scale's name is now on the always-visible summary at every chrome size, so the
   old tiny-only scalename test retargeted to pin exactly that.
3. **The re-read is the acts row's primary** — the comp fills its re-preview green; the
   TONE ports, the words do not (its label promises an outcome; ours promises a read).

CALLS THE CLIENT ASKED FOR, left open on purpose:
- **"Accept as flagged exception" on Adjustment** (comp) vs our acknowledgment gate on
  Deliver's assurance rows (server-derived disposition, §10-N). Duplicating the act on
  Adjust is a flow + BFF change, not a restyle.
- **The terms checkbox in Adjust's queue foot** (comp: "accept the terms to continue")
  vs their own 2026-07-30 ruling that terms gate PAYMENT on Delivery (§10-O.1). The comp
  contradicts the ruling; ours follows the ruling until they say otherwise.
- **MAX DEV as one pill** (comp) vs our DEV RMS + DEV P90 with (run)/(preview) source
  qualifiers — collapsing spends provenance.
- **The label "budget & log"** — the comp's words imply the client-side budget fractions
  this product refuses; ours says "Numbers & log". Rename is possible if the exact words
  matter more than the implication.

**Z. THE AMBER ACT LANDS ON ADJUSTMENT (client 2026-08-02: "Replace it to match the
designs and do what it is recommended").** Rulings, resolved: accept-as-flagged-exception
moves onto Adjustment (built); terms keep gating payment at Delivery (their own
2026-07-30 ruling stands over the comp); DEV RMS + DEV P90 keep their (run)/(preview)
provenance; the label stays "Numbers & log".

The design decision that makes the move honest: what Adjustment records is a DRAFT —
`SiteSession.exception_intent`, the sibling of the drop's `withhold_intent` — that
PRE-FILLS Deliver's acknowledgment checkboxes. AM-12 is untouched: `acknowledged_flags`
on the confirmation, row by row, remains the only signature, and every face of the new
control says so ("the confirmation there is what signs it" — the forbidden promise is
pinned absent by test).

Two divergences from the withhold precedent, both deliberate and BFF-tested:
- `exception_intent` CLEARS at run boundaries — including the re-authorize-over-done
  path that never routes through `clear_current_run` — where `withhold_intent`
  deliberately survives them. A drop is a standing preference about a cap; an
  acknowledgment is about ONE run's verdict, and must not outlive the verdict.
- The draft is excluded from `sealed_facts()` like the intent is, so withdrawing it
  after confirming can never read as evidence drift at release.

Wire: POST/DELETE `/api/case-sessions/{id}/sites/{tooth}/acknowledge` (body-less both
ways, the review pair's shape); `exception_acknowledged` on SiteView and AssuranceSite;
eligibility is the acknowledgment gate's OWN predicate, lifted to session.py so
Deliver's `_needs_acknowledgment` and the route share one derivation. Verified live on
cap6020: accept → pressed + amber queue line → Deliver's checkbox pre-ticked → withdraw
→ clean.

**AA. THE COMP, PAGE BY PAGE (2026-08-02, client: "Implement page by page — the product
does not look like the designs at all").** The workspaces already wear the comp (W-Z);
this pass dresses the remaining pages, one commit each, against the comp RUNNING plus its
template read directly. Standing refusals all hold: no invented prices/parts, no
confidence %, no browser upload, no client-side tolerance words, no outcome promises.

**AA.1 — header strip + worklist (this commit).**
- The dark band carries the comp's five-stage strip on non-case routes as a PREVIEW
  (`StageStrip`): every step a span — there is no case to navigate into — Intake current,
  the rest dimmed with "Open a case from the worklist first." as the tooltip; the comp's
  case-note slot reads `no case open`. The comp's `restart` button is NOT ported: it
  resets the mock's state, and this product has nothing case-global to reset from the
  worklist (the per-case demo reset lives in the case band).
- The worklist renders as the comp's card grid, per band — the blocked-first bands keep
  their captions and DOM order (they are real signal the comp's flat grid lacks). Cards
  carry the comp's rows from served facts only: name, site-count chip, discovery line
  (rollup total · suggested model · scan MB), teeth + jaw, the five status chips
  unchanged, and one segment bar per site drawn from the ready/flagged counts. The
  comp's batch codes, clinic names and per-card fake MB have no source and are not
  invented. The page keeps the honest title "Worklist"; the comp's lead ports minus its
  false clause ("or drop a new scan" — there is no browser upload, AA holds O.6).

**AA.2 — the construction library as the comp's page.** One centered `.stage-page`
spanning both workbench columns (grid-column 1/-1 — the lone-wrapper-in-the-356px-column
failure the old two-children markup dodged is retired at the grid instead); title + lead
in the comp's type; parts as the comp's CARDS in an auto-fit grid, vendor groups kept
(they are real attribution the comp lacks); a non-effective card wears the neutral
"select" invite, the effective one keeps its server-attributed suggested/selected chip.
The page's acts move to the preview column's foot, forward leading, the blocked forward
staying visible at 0.45 opacity. Still refused, per M/O.5: the comp's four invented
parts, prices and lead times; its dataless preview disc. The four preview branches and
their provenance captions are untouched.

**AA.3 — the case intake mirrored to the comp.** The comp's intake leads with the scan:
a panel whose head names the scan file and the centred count (both served — the count
is the flow model's own `siteCentred` over `siteTotal`), the real 3D viewer as its
stage (the comp's procedural 2D horseshoe stays refused — this product has the actual
mesh), and the site rows directly under it. The control cards keep the right column:
capture banner, missed-cap card, case-level choices, the advance at the foot. Layout
is one `:has()` rule flipping the workbench's columns for this stage alone; the site
rows travelled markup-whole (every role, verbatim sentence, source chip and the
no-invented-confidence rule untouched, their panel chrome flattened by CSS inside the
scan panel).

**AA.4 — Delivery as the comp's page.** Centered `.stage-page` with the comp's title
row: "Delivery" + the lead naming the served part and site count — the part clause
DROPS when nothing is effective (the comp's lead assumes one always exists), and the
comp's "then pay to release" causality is not repeated: the lead states the three acts
as separate, which is what they are (O.1). The door back rides the title row. The
progression and the evidence become two card columns with their DOM order untouched —
every within-region ordering pin (disclosure before release, lines before total, terms
above confirm, one blocker list per confirm site, open-report before previews) stands
unmoved. The steps panel's own "Delivery" h3 retired into the page title; the reset
button kept its role and words.

**AB. THE CLIENT'S DECISION BATCH (2026-08-02, in-chat, on AA's open list).** Rulings,
verbatim intent:
1. **Landing page stays the Worklist; per-case Intake stays separate** — the AA.1 split
   is ratified; the comp's one-page Intake is not adopted.
2. **The header restart button stays out** — "leave this as is."
3. **The rate card is CONFIRMED**: "$32/site standard, $48 rush, exceptions at half" —
   the client's own words adopting the placeholder figures as the price list. The
   invoice's placeholder status retires (AB.1 below); the not-a-quotation hedge goes
   with it. The rates stay server-side, one home.
4. **The three comp-vs-ruling conflicts are ratified in the product's favor** — terms
   keep gating payment at Delivery (their 2026-07-30 ruling), DEV RMS + DEV P90 keep
   their (run)/(preview) provenance, the label stays "Numbers & log."
5. **A tolerance number SHALL be displayed, as a served fact** ("Do this") — the band
   the verdicts actually use becomes part of the assurance payload and renders on
   Delivery only when served (AB.2 below). The no-client-side-tolerance rule is
   unchanged; what changes is that the server now states its band.
6. **Browser upload is greenlit** (retires O.6's refusal-to-pretend; AB.3 below) and
   **the turnaround chooser lands at Intake** now that the rate card is real (AB.4).
7. The standing engineering queue (O.7 emit_from_poses, B/C per-site relief, E, H's
   renames) proceeds. §10-L's recess measurement and §10-J's tool-2 words still wait
   on the client's physical measurement and wording respectively — restated, not
   resolved, by this batch.

Landings against this batch (same-day):
- **AB.1 LANDED** — `bff.pricing`: status "final", version `client-2026-08-02-v1`,
  note names the confirmation date; placeholder-v1 receipts stay readable as such.
  The product's badges dropped by construction (they key off the served word).
- **AB.2 LANDED** — `toleranceBandsWords` renders the served catalog bands
  (`references[*].bands`) on Delivery's assurance header, exactly once, with the
  guidance-decides disclaimer; the old blanket no-tolerance pin SHARPENED to
  "only as the served line" rather than falling.
- **AB.4 LANDED** — the Intake turnaround chooser: `turnaround_options` ride the
  choices view priced from the ONE `bff.pricing` card ($32/$48 per site), pills
  wear the jaw chooser's clothes with the served money via `turnaroundPillLabel`,
  the effective value presses, attribution chips as elsewhere, and no served
  options means NO chooser. The comp's "24 h"/"4 h" lead times have no source and
  stay absent.
**AC. EMIT_FROM_POSES — THE PLAN, MEASURED (2026-08-02, §10-O.7 taken up; the client's
"then the engineering items").** The seam was re-verified against the tree at `e80ad07`:
`construction_mesh` enters `_align_and_package` only at the two signatures, the
`package_sites` triple (auto_flow.py:2082) and the product-build block (2266-2275);
everything from auto_flow.py:2234 down is pure emission over
`(package_sites, final_products, audit_by_tooth, site_rows, frame/origin/L, scan)`, and
`frame/origin/L` are DETERMINISTIC scan derivatives (`pts = scan.vertices`,
`normals = scan.vertex_normals`, `_crowns_frame`, auto_flow.py:1699-1703 — no sampling,
no RNG). The four M-hazards, answered by construction:
1. **Provenance**: a re-emit mints a NEW run dir (AM-1 forbids writing into the old
   one); the old run's `<case>-<tooth>-implant.json` `adjustments`/`nudge`/`best_fit`
   keys are COPIED FORWARD into the new records — merge becomes copy-forward.
2. **The emission-time refusal**: the re-emit enters through the worker port's existing
   containment (`_leave_refusal`), so a design-rule or relief-block refusal lands as a
   REFUSED run on the surfaces that already render refusals — the flow point §10-M
   feared gets the run-refusal surface for free.
3. **Vendor rename**: the new dir gets a fresh manifest from `emit_case_package`; the
   old `-scanbody-<vendor>.stl` simply is not copied — "register_package_files never
   removes" only bites in-place rewrites, which AM-1 already forbids.
4. **Stale evidence**: `clear_confirmation` fires explicitly on the session transition;
   exception drafts fall via `clear_exception_intents`; `adjust_decision` falls.
Call sequence (worker, new `application/emit.py::emit_from_poses(case, selection,
source_run_dir, out_dir)`): read per-site implant.json (pose_matrix is the ADJUSTED
world pose — `_reemit_site` keeps it current) + the source report's site rows and
`clocking`; rebuild `SitePackageSpec`s; per distinct variant
`channel_from_boundary_loops` → `resolve_gingival_offset` → `build_final_product`;
`delivered_channel_offsets` per site; `render_site_qc`; `emit_case_package` (the gate);
arch trio + `view.html` + report. The report carries `emitted_from: <source_run_id>`
(provenance on the receipt) and site rows whose pose/seat/clock facts are the source's
VERBATIM while product facts (clamp trio, delivered channel, part label, design
advisories) are fresh.
BFF: the re-emit-eligible boundary is a construction-path or relief-only effective
change over a DONE current run — those keep site rungs (the pose the review attested is
untouched, the measured §10-M fact) and route through a new port submission
(`mode="reemit"`, source_run_id) with the existing claim/land/withdraw pattern; jaw or
model changes keep today's full retirement. Product UI: `constructionChangeWords` tells
the NEW truth (re-emits from the run's own poses; the confirmation falls; flags may
change) — the old "re-processes the case" promise retires with the behaviour.
FOLLOW-ON (§10-B/C rides this): relief per-site on Adjustment becomes a re-emit with a
per-site offset map once this lands.

**AC FULLY LANDED (2026-08-04): the whole wire.** The worker layer landed at
`03a1628` (application/emit.py, real-tree verified); now the port dispatches
`mode: "reemit"` to `emit_from_poses` under the same containment (a gate refusal is a
REFUSED run); `put_choices` recognises a part/relief-only effective change over a DONE
run and re-emits — site rungs SURVIVE (the pose the review attested is untouched),
the confirmation and every draft fall explicitly, the activity names the act and its
source run, and jaw/model changes keep the full retirement. The disclosure words
follow the truth on both surfaces (`constructionChangeWords` gains `runDone`; the old
full-reset words remain exactly where they are still true — no done run). Pins
amended to the new truth: test_pricing's boundary helper now drives the JAW (a relief
change no longer crosses a run boundary), test_reemit_boundary (8 new pins),
test_worker_port (+4), and the three constructionChangeWords sites. MEASURED LIVE on
cap6020: the full run took 10 s; the relief re-emit took **1.26 s**, landing
`mode: reemit-from-poses` with `emitted_from` on the receipt and the flagged rung
preserved end to end.

**§10-B/C LANDED (2026-08-04, on the §10-AC lane): PER-SITE RELIEF.** The pipeline
takes ``site_gingival_offsets`` (the shared-product cache keys on (variant, ask) —
two same-variant sites with different reliefs are two bored products);
``RunSelection.site_reliefs`` rides run and re-emit alike; ``SiteSession`` holds the
override (an act — no rung moves, no review falls: relief shapes the emitted part
only); ``PUT /sites/{tooth}/relief`` sets or clears it, re-emitting over a done run
with every standing override in the selection; the Adjust acts row carries the
control (site ask beside the standing case value, the served ceiling, the §10-AC
disclosure). THE DRIFT GATE SHARPENED with it: the authorized gate's seat equality
now covers the POSE INPUTS — model, variant, jaw — because relief and the
construction part are provably pose-independent (§10-M/C) and their changes ride the
re-emit lane; an absent seat record still fails closed. Without the sharpening, #8's
rung-preserving boundary wedged the next full run. Verified live on cap6020: the
override re-emitted with site 29 cut at its own 0.05 ask (requested AND applied on
the receipt), rung untouched; clearing re-emitted back. Case-level relief at Intake
stays the standing default, exactly as before.

**AB AMENDED (client, 2026-08-02, second batch):** the second-actor question (item in
A) is NOT NEEDED FOR NOW — closed until the client reopens it; the final Terms &
Conditions text STAYS OPEN (placeholder renders until it arrives; one string to swap).

**AD. ALIGNMENT TUNING + TOOL COHESIVENESS (client 2026-08-02: "when adjustment and
rerunning the alignment it does not take effect").** ROOT CAUSE, verified in code, not
guessed: `_authorized_selection` (case_sessions.py:1858-1878) sends the run exactly
`model / construction_path / jaw / gingival_offset_mm / variants / marked_centers`,
and `SiteSession` persists only `marked_center` — the adjust tools' evidence (fit
pairs, align-to-mark marks, best-fit pairs, nudge deltas) is applied to the CURRENT
run's implant.json in place (`_reemit_site`/`_finish_adjustment`) and stored nowhere
else. A re-run therefore re-aligns from scratch and silently discards every operator
adjustment; the flag that prompted the rework returns.
THE DESIGN (respecting the standing trust rules, incl. the re-click pair-integrity
record): operator alignment evidence is a MEASUREMENT in the scan's world frame —
valid across runs like `marked_center` already is — so it PERSISTS per site in the
session (a new `alignment_evidence` record: kind + points, appended by the adjust
routes at apply time, cleared only by an explicit operator act or a re-mark of that
site's centre) and RIDES the selection into every future run; `run_case` re-applies
it per site AFTER automation through the same application.adjust functions the tools
use, landing the same provenance entries in implant.json ("re-applied from session
evidence, run X"). The bare rotation NUDGE deliberately does NOT auto-re-apply (its
own provenance says eyeball, no marks — re-applying it silently would promote the
weakest evidence class); its cumulative degrees stay reported. The preview seat in
the screenshot (rim 0.80 mm on cap7030 t29) is the pre-run preview's own seat — the
same persistence gives the preview the evidence too. Wire: SiteSession +
`alignment_evidence`, the adjust routes append on apply, `_authorized_selection`
gains the field, `application/run.py` re-applies post-align, tests at every layer.

**AD LANDED (2026-08-02, the whole wire).** `SiteSession.alignment_evidence`
(mark/pairs/best_fit, wire-shaped, apply order); the three evidence-bearing routes
append through `_land` on APPLY only, the nudge never; a centre re-mark clears the
site's evidence (pair-integrity); `_authorized_selection` ships it, the port passes
it, and `run_case` re-applies AFTER automation via the same `application.adjust`
functions — outcomes land as receipts on `summary["evidence_reapplied"]`
(applied / already-optimal / refused with the gate's own words, never a failed run),
re-derived row numbers fold in, rewritten files join `package_files`, and the
on-disk report says what the summary says. Verified on the real tree
(test_evidence_reapply.py's slow test) and pinned at both layers (worker dispatch +
BFF persistence/selection/re-mark). FOLLOW-UPS, RESOLVED (2026-08-04):
the surfacing half LANDED (SiteView.alignment_evidence_count + the queue's
"N measurements ride the next run" line, 560d9fd); the PREVIEW re-apply is
DECLINED FOR NOW, deliberately — after AE.1 the flagged/adjusted sites (the ones
whose evidence matters) read the SEATED fallback, which shows the re-applied
shipped fit, so the only diverging surface is a fresh preview on a
declared/previewed/ready site that kept evidence through a re-run; that pane is
labelled "preview — nothing processed yet" by its own caption, and buying
coherence there would spend seconds of adjust-tool physics on every site-step.
Reopen if an operator reads a preview as the standing truth despite the caption. The correspondence QC block is not reconstructed on a re-applied row — it
under-claims (no agreement figure) rather than hand-rebuilding the block, stated
in `_reapply_evidence`'s doc.

**AE. PANE 2's CAMERA AND CROP (client 2026-08-02, with a screenshot: "We lost the
global view of the rotation of the camera. The second panel doesn't default to the top
of the healing cap … maybe [cutting to] just the healing cap and a little more in
panel 2 would have made the alignment more accurate?").** Two asks, and one boundary
to keep:
1. **Pane 2's DEFAULT camera must look down the seated pose axis** (top of the cap).
   The screenshot's own footer reads "45° off the seated pose axis" at rest — the
   readout is honest (paneReadout's live angle), the DEFAULT it reports drifted.
   Find where pane 2's initial camera frame is set (SitePanes/DeclarePanes + the
   viewer's frame helpers — the effective-choices slice's siteFrameFor/
   partCameraFrame) and default it to the pose axis; the readout should then say
   "down the seated pose axis" on open, as panes 1/3 do.
AE.1 LANDED (2026-08-03): the 45° was not a camera defect — REPRODUCED as the
auto-preview firing on a FLAGGED site and the ladder refusing it forever ("cannot
preview a site that is 'flagged'"), leaving the panes payload-less on the occlusal
proxy with a retry that could never succeed. Two-part fix, verified live on cap7020
t3: `previewKeyFor` mirrors the server's ladder (no known-refused POST is ever
auto-fired — not a client verdict, a refusal already known), and a flagged/adjusted
site over a DONE run reads the SHIPPED fit instead (`seatedReadWanted` +
GET .../seated — a read, no rung moves), so pane 2 rests down the cap's own axis and
the union wears the honest caption "the run's own fit — rework belongs to
Adjustment". Preview figures stay the preview lane's own (provenance).

AE.2 LANDED (2026-08-03): `scanPaneRadiusMm` — the largest SERVED rim diameter's
radius + 3 mm, one decimal, floored at 6 mm, capped at the standing 11 mm band, and
exactly that band when the catalog serves no dimensions. The crop, the frame and the
caption read the ONE number (pane 2 cannot claim a band it is not drawing); on
cap7020 the band derives to 7.1 mm and the crop halves (83k → 40k triangles — the
cap fills the pane). `CAP_REGION_RADIUS_MM` itself is untouched (§10-K's two-constants
rule stands); §10-I.3 stands (display-only, stated in the function's own doc). The
pane-3 "preview has not run" notice STANDS DOWN when the seated fallback's fit is on
the panes — it contradicted the colouring it overlaid.

2. **Pane 2's display band tightens to the cap + a little more.** Today it draws
   "within 11 mm of the site's centre" (~117k triangles of jaw around a ~7 mm cap).
   The band is DISPLAY-ONLY (meshCrop.ts, the §10-K constant; the demo's 9 mm copy
   is frozen — the two-constants rule stands): tightening it must be a pane-2-scoped
   display radius, NEVER a bound that reaches the aligner (§10-I.3's trust
   inversion). The honest accuracy claim, stated to the client: a tighter view
   improves alignments only through the operator's mark placement — the aligner's
   own input radius is the server's and unchanged. Pick the radius from the cap
   catalog's largest variant diameter + margin, not a new magic number; verify the
   fit-by-points click flow on the cropped mesh still lands world-frame points.
`application/emit.py::emit_from_poses(case, selection, source_run_dir, out_dir)` exists
and is verified on the real tree (tests/test_emit.py): pose bit-identity, provenance
copy-forward + re-hash, vendor-rename cleanliness, `emitted_from` on the receipt, the
gate refusal as `RunRefused` — and the re-emit runs in seconds. REMAINING, the BFF+UI
wiring, mapped precisely for the next session:
1. **Port**: `InProcessWorker._execute` dispatches on `request["mode"] == "reemit"`
   (+ `source_run_id`) to `emit_from_poses` with
   `source_run_dir = product_root/<case>/runs/<source_run_id>`; same containment.
2. **Boundary**: `put_choices` (case_sessions.py:1140-1175) — when the effective
   change is construction-path and/or relief ONLY and `session.run` is done: keep the
   site rungs (skip `invalidate_preview`/`clear_preview_facts` — the pose the review
   attested is untouched, the measured §10-M fact), snapshot the source run_id, mint a
   new one, set the queued receipt (+ `adjust_decision = None`,
   `clear_exception_intents`, **`clear_confirmation` explicitly** — hazard 4), submit
   the reemit, land through the same guidance→flag mapping (levels carried verbatim →
   flags land unchanged), withdraw the receipt on no-verdict. Jaw/model changes keep
   today's full retirement.
3. **Tests to amend to the new truth**: the BFF pins that a construction change
   retires the run (test_case_sessions choices-boundary tests, test_withhold_intent's
   boundary expectations), and the product's `constructionChangeWords` pins
   ("re-processes the case", "a new run re-bores and re-renders everything" in
   domain/deliver tests + LibraryStage/DeliverStage) — the words must tell the new
   truth: re-emits from the run's own poses, seconds not minutes, the confirmation
   falls, the design gate can refuse. The disclosure-before-act rule is unchanged;
   only the disclosed consequence shrinks.

- **AB.3 LANDED** — the browser upload, retiring O.6's refusal WITH its reason. The
  storage policy (bff/resources/uploads.py's module doc, pinned in test_uploads.py):
  `POST /api/uploads/scans/{folder}/{filename}` takes the raw STL bytes — no
  multipart, no request model — and writes the ONE thing the BFF may now write,
  `data_root/scans/<folder>/<file>.stl`, streaming under a 256 MB cap to a temp
  name, refusing an existing folder (one folder per case, never overwrite), non-STL
  names, unsafe names and empty bodies, and removing its folder on any failure. The
  response is the DISCOVERED case read back through `discover_cases` — an uploaded
  case is indistinguishable from a lab-copied one, deliberately. Own prefix, outside
  the case-sessions action allowlist: it creates a case, it is not a session act,
  and it mints no session (product data plane untouched). The worklist's drop zone
  is the comp's dashed band, honest at last — browse or drag one STL, name the
  folder (`suggestedUploadFolder` pre-fills off the filename; the BFF's name rule
  mirrored client-side as a pre-check), refusals verbatim, and the landing case
  named from the response. The scan-arrival note now describes BOTH routes in; the
  comp's lead ships whole ("or drop a new scan" became true). `config.Settings.
  data_root`'s read-only comment names its one exception.
