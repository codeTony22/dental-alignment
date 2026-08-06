# Next-phase engineering plan — 2026-08-06

Written the night the fleet check, the three pair-math fixes and the live-testing
batch landed. Everything here is grounded in measured numbers (the fleet table,
the dipole analysis) and the client's own words from tonight's session. §10 in
`product-app-plan.md` remains the decision ledger; this is the map of what to do
next and why.

## 1. The problem, restated from first principles

The lab's business loop is: **scan in → caps identified → parts aligned →
operator attests → package released and billed.** The product is good exactly in
proportion to:

1. how often a case needs ZERO operator geometry work (automation quality);
2. when work is needed, how fast ONE obvious tool fixes it (tooling);
3. whether the operator always knows the state and the next act (clarity);
4. whether the shipped numbers survive scrutiny (trust — the non-negotiable).

Everything below is justified against those four, or cut.

## 2. What the measurements say tonight

- **Fleet of 8 landed sites**: 2 healthy (0.17–0.18mm RMS), 4 middling
  (0.25–0.34), 1 poor (cap7030, 0.43). The centre-seed lever is EXHAUSTED —
  verify-fleet finds exactly one improvement left (cap6030, one click at the
  adopt door).
- **The remaining misfit is not algorithmic.** The dipole analysis on 276794487
  shows a world-locked tilt (first harmonic direction fixed at every clock
  angle) on a seat with 29.9% coverage and an 8.8° axis spread; cap7030's rim
  reads 0.80mm — the rim itself is ambiguous on that capture. **Capture quality
  is the binding constraint**, not the optimizer.
- **The pair-math defect family is closed**: re-mark splice (§10-AH), pivot
  parallax (§10-AJ), the diameter span's ±180° branch (§10-AK) — each fixed,
  pinned, and now REFUSED at the source with actionable words.
- **The client's friction concentrates on information architecture**: three
  independent "so much text" complaints in one evening, plus camera behaviour,
  identity friction, and colour semantics — all fixed reactively tonight. The
  pattern deserves one deliberate pass, not more whack-a-mole.
- **The upload flow is the weakest path and the growth path at once**: on the
  arch upload the detector found 1 cap, there are no curated anchors, and the
  operator does everything by hand.

## 3. Ubiquitous language (standing) and the invariants that bind this plan

Case · Site (tooth-keyed identity) · Capture (assessment + verdict) ·
Declaration (variant) · Preview seat · Run (immutable, AM-1) · Evidence
(marks/pairs, re-applied across runs) · Refusal (server sentence, verbatim).

Invariants no step below may bend:
- statuses/verdicts derive server-side (AM-4); the client renders, never claims;
- the published DEV metric (`site_deviation_stats`) is the only acceptance
  instrument; candidates promote only by beating it past the noise floor
  (monotonic-accept);
- a human's mark is fixed at the UI or refused — never corrected downstream;
- an observation may only arbitrate a branch it carries the weight to be judged
  by (the §10-AK rule);
- server sentences render verbatim; provenance is named on every number.

## 4. The plan — dependency-ordered, each step with its proving test

### Phase 0 — close the open edges (days)

**0.1 Chase the client-supplied texts** — T&C + Clinical Responsibility
Statement (Deliver ships a labelled placeholder), §10-L's measurement, §10-J's
tool-2 words. Blocked externally; costs a message, unblocks a legal edge.
*Test: Deliver renders the served text verbatim; the placeholder pin flips.*

**0.2 Kill the `test_stages` parallel flake** (task chip already spawned).
A gate that cries wolf trains people to ignore gates.
*Test: three consecutive full batteries green; the shared state named and pinned.*

**0.3 Accessibility sweep of tonight's tooltip moves** — the condensations
deliberately traded always-visible text for `title`; swap to visually-hidden
`aria-describedby` nodes so screen readers keep the words.
*Test: render pins assert the described-by text exists for each moved sentence.*

### Phase 1 — capture-first alignment quality (the real lever)

**1.1 The border-points tool at Intake** (client ask, demo parity). Click points
around a cap's rim → the worker's existing `rim_points` read fits centre +
diameter → serve a RANKED variant shortlist (adjacent variants sit ~0.1mm apart;
one answer would over-claim). Scoped as a CAPTURE AID: §10-AH measured that
pair-shaped seeding LOSES to the bare click on DEV, so this feeds
identification, never the seat.
*Test: N synthetic border clicks on a known case serve the true variant first in
the shortlist; the DEV metric of a subsequent run is unchanged.*

**1.2 Pre-run capture advisory per site** — surface the capture gate's verdict
AT INTAKE with its measured reason ("coverage 30% — the seat cannot beat ~0.3mm
here; rescan this die"), before anyone spends alignment effort. All the numbers
exist; this is a serving-and-words slice.
*Test: BFF pins the served advisory for a low-coverage fixture; UI renders it
verbatim; healthy fixtures serve none.*

**1.3 Detection recall on arches.** The arch upload found 1 cap. Measure why
(run the detector against the arch with counts as the fixture), then tune
`propose_sites` for multi-cap arch context — behind the two hard gates.
*Test: a new arch fixture asserts ≥K proposals; the fleet table and `rehearse`
are unchanged-or-better (any regression kills the tune).*

### Phase 2 — guidance over more tools

**2.1 The misfit-family advisor — the highest-leverage single feature.**
Tonight's diagnosis separated "tilt you cannot rotate away" from "clock error"
from "wrong centre" using the deviation field's first azimuthal harmonic swept
against clock angle — a two-hour expert instrument. Productize it server-side:
each DONE site gets a served `misfit_family` (tilt-locked / clock / centred /
mixed-uncertain) with its number, and Adjustment shows one sentence plus the
tool it points at ("this misfit is tilt — no rotation removes it; rescan or
accept" · "clock is 14° off — Auto-mark will fix it"). The five tools exist;
what the operator lacks is WHICH — the client proved it live by spanning a
diameter.
*Test: worker unit pins on synthetic fields (a pure rotation field reads
"clock"; a world-locked field reads "tilt"; noise reads "mixed-uncertain" —
the classifier must be allowed to say it does not know); BFF serves it; the UI
renders the sentence verbatim.*

**2.2 Algorithm A/Bs stay in the REPORT lane.** Fitzpatrick TRE advisory,
symmetric-ICP inner engine, SDF search — each lands first as a verify-fleet
VARIANT COLUMN, promoted into the product only on a ≥0.01mm median win with
zero per-case regressions. Opinion: the dipole evidence says these will not
move the fleet much — budget them as background experiments, never as
product-blocking work.
*Test: verify-fleet prints the variant column; the promotion PR must quote the
table.*

### Phase 3 — operational smoothness

**3.1 The cross-case "needs me" queue.** The worklist lists cases; a lab runs a
DAY. Order the worklist by blocked-on-operator states (all server-derived
already): confirm-owed, flagged, capture-rescan, payment-pending.
*Test: worklist domain pin — given mixed case states, the queue orders by the
operator-owed act, and a case owing nothing sinks.*

**3.2 Nightly verify-fleet + rehearse** on a schedule, table written to a dated
file — regressions surface the morning after they land, not the demo after.
*Test: the make target writes the dated report; two consecutive runs diff
cleanly on an unchanged tree.*

**3.3 The systematic UI pass — one session, with the client.** Walk the five
stages together against the three rules tonight proved out: one row of chrome
per surface; one status line, changing with state; sentences live behind doors,
claims stay on the glass. Output a single §10 batch and implement it in one
slice, instead of six reactive ones.
*Test: the batch's own pins; the client's word.*

**3.4 Run-dir lifecycle note.** Immutable run dirs accumulate forever; write
the retention policy down (archive after release + N days), do not build until
disk says so.

## 5. Opinion — the ranking, and what NOT to do

1. **2.1 Misfit-family advisor** — the single best quality-per-effort in the
   codebase: it converts the only remaining hard operator problem ("what is
   wrong with this fit?") into a served sentence, using an instrument already
   proven on real cases tonight.
2. **1.1 + 1.2 Capture-forward intake** (border points + pre-run advisory) —
   attacks the measured binding constraint (capture), gives the client their
   missing demo tool, and moves the rescan conversation to BEFORE effort is
   spent.
3. **1.3 Arch detection recall** — the upload flow is the growth path; today it
   is the weakest.
4. **3.1 + 3.2 Ops queue + nightly fleet report** — cheap, compounding.
5. **3.3 Systematic UI pass** — bounded, with the client in the room.
6. **2.2 Algorithm A/Bs** — LAST, and report-only. The measurements say the
   optimizer is not the constraint; chasing it would be motion, not progress.

**What not to do:** no free-ICP or global-correspondence revival (measured out);
no anatomical tooth-numbering guesser (mirror-ambiguous — the labelled free
label stands); no re-weighting of the pair fold (refusal-only, §10-AK's
invariant); no speculative multi-tenant/auth work until the client asks.

## 6. Risks, and the cheapest de-risking experiment

- **R1 Detection tuning regresses curated cases** → both hard gates (fleet
  table + rehearse) are regression courts; tune behind a flag.
- **R2 The misfit classifier over-claims** → it must have an "uncertain" answer
  and use it; calibrate thresholds on the 8 known sites; ship report-only first.
- **R3 Border-point diameter ambiguity between adjacent variants** → serve a
  ranked shortlist, never one answer.
- **R4 Client texts stall Phase 0** → placeholders are labelled; nothing else
  blocks on them.
- **R5 Rescan advisories annoy rather than help** → the words carry the measured
  number and the lab decides; track advisory-vs-final-DEV correlation and let
  the data argue.

**The cheapest experiment for the biggest bet (R2 / step 2.1):** before any
product code, run the dipole-direction sweep OFFLINE over all 8 landed sites
(the scratch scripts from tonight's 276794487 diagnosis already do it) and
check the classifier's verdicts against the known ground truth: 276794487 =
tilt-locked, cap7030 = rotation, cap6020 = was-centre (now fixed), the healthy
pair = centred. One evening, zero product code. If it cannot separate those
cleanly, the advisor dies cheaply and Phase 2 re-ranks.
