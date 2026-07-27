# Alignment Master Plan — find the cap, align it perfectly, build the prosthesis, say honestly how sure we are

**Date:** 2026-07-23
**Status:** This document SUPERSEDES `docs/research/marks-as-locators-plan.md` as the executable plan.
That document remains the measurement record — every number cited here traces to it, to
`docs/engagement/phase2a-completion-report.md` §6–7, or to an instrument named inline.
**Baseline:** scoreboard snapshot `notchclock-v1`; 423-test battery green; 10 real sites, 2 implant systems, one lab.
**Status 2026-07-23:** inline `[DONE]` / `[PARTIAL]` / `[DEFERRED]` markers on the slices below; unmarked slices are
queued — the ranked queue is §8. Client direction (2026-07-23): **local code only, demo first** — git/remote,
sign-off meetings, the phantom print, the client-ask emails, and the FLE study are DEFERRED (not cancelled).
§7 (new) answers the client's screw-channel question and defines the guarantee instruments.
**How this plan was built:** the prior plan was put through four independent adversarial reviews —
domain model, execution shape (XP), goal-chain coverage, and pre-mortem — and rebuilt as one document.
Nothing measured was discarded; several things the prior plan could not see were added.

---

## 1. THE GOAL, FROM FIRST PRINCIPLES

The client's sentence: *"find a healing cap and align it PERFECTLY using the libraries that we
have, for the prostheses."* Reduced to its irreducible chain, that is five links, and the product
is only as good as the weakest one:

**SCAN → FIND → ALIGN → CONSTRUCT → DELIVER**

The prior plan was depth-first on the middle link. This plan covers the chain. "Perfect" is not a
feeling; here is what it measurably means at each link, with the instrument that proves it:

| Link | What it is | What "perfect" measurably means | Where we are today (measured) |
|---|---|---|---|
| **SCAN** | The intraoral scan arrives good enough for physics to work | Every upload passes an automatic capture gate: rim-arc coverage above threshold, code-band visible, collar exposure ≥1 mm (the rule the industry's coded-cap gold standard hard-requires). Failing scans are refused **while the patient is in the chair**, with a concrete message ("rescan the cheek-side rim") | No gate exists. t7 shipped with 46% of its seat-band arc empty and exposure 0.20 — a scan no algorithm can rescue, discovered at the end of the pipeline instead of the start |
| **FIND** | Locate the cap with no precision burden on the doctor | A machine candidate within the click-noise envelope (p90 = 0.61 mm) on every capture-gated scan, **with the recall number on the scoreboard** — not asserted from memory | Candidates land 0.002–0.062 mm from the curated click on 6/10 scans (0.22 on t20, 0.51 on t3-276) — genuinely strong — but **0 candidates on 2/10** (cap7020, t7), and zero fleet instrumentation. "Detection already works" was an overclaim; this plan instruments it and corrects the client-facing strategy text |
| **ALIGN — centre, depth, axis** | Seat the catalog cap on the scan | Pose anchored to a **machine-measured island** (the cap's own segmented region), never to the doctor's gesture; stability spread under bars whose millimetre meaning is **phantom-pinned** ("high means ≤X mm with probability Y", X measured by print-and-scan, not asserted). Industry frame: the coded-cap gold standard's measured centre trueness is 35–47 µm in study conditions; 200 µm is the literature's misfit-acceptability line; our fleet reads top-face 0.13–0.60 mm today | A 0.6 mm click error moves the shipped pose up to **1.09 mm / 16.6° of axis** — the pose can move more than the click. The region fed to the seat is median **54–60% tooth/gum**. In a simulation where marks only locate, confidence spread collapses **7–13×** (cap6030 1.237→0.099 mm; axis 18.4°→0.20°) |
| **ALIGN — rotation** | Read the cap's clocking from its coded cutouts | **Solved — do not re-plan.** Code-verified ≤3.1° on 8/10 sites (the commercial gold standard itself measures ~2.9°). Perfect = every capture-gated site code-verified or honestly flagged; the two exceptions are evidence occlusion (cap7030 half-occluded ring — honest refusal; t7 — subsumed by the SCAN and ALIGN fixes) | Done and guarded. This plan's only rotation work is *protecting* it: a promotion gate that refuses any change which downgrades a site from code evidence to recess-only (t20's oracle run measurably lost codes: −2.1°→−23.6°) |
| **IDENTIFY → library** | Pick the right catalog variant | Declared-ID 4/4 on the labeled arches, held through every recalibration; inseparable scores → the doctor's declaration decides, never a silent guess; plus, for the first time, **variant ground truth** (placed-cap records, engraved-code photos — a 5-minute client ask) | 4/4 today. At risk from recalibration (the record warns the score *family* may reopen); protected by decision rule DR2 below. The catalog itself has no acceptance contract for future vendor drops — fixed by the library qualification gate (§4.2) |
| **CONSTRUCT** | Build the prosthesis part with the screw channel | The delivered channel's position vs the scanned recess is **measured on every site** (a scoreboard column that does not exist today) and bounded per the vendor's interface spec. A 0.3 mm seat improvement must provably arrive at the deliverable | **Zero coverage in the prior plan — the sharpest gap found.** The delivered channel is bored at the canonical axis (final_product.py:65–69), so the entire rotation program never moves it — while our own §6.2 measurement puts the physical bore 0.43–0.76 mm off that axis. Two records contradict at the deliverable; nothing today can see it. Seating vertical offset and z-sign convention await each vendor's interface spec (an open architecture debt at the same 0.4 mm–mm scale as everything the alignment work buys) |
| **DELIVER — confidence** | Say how sure we are, honestly | A grade whose millimetre meaning is phantom-pinned; package keys that say what they carry (`pose_origin` written; the key currently named `fitness` renamed to the coverage it actually holds); QA metrics that cannot be fooled by the input they judge | 0/10 high, 8 medium, 1 low, 1 ungraded — and honest: click noise really does move today's poses. But QA is anchored to the clicks (a 1.09 mm-off pose *improved* rim-agreement, 0.62→0.88), and five code-verified sites over-warn off a phantom-convicted biased instrument |

**The first-principles verdict on the prior plan:** its ALIGN work survives adversarial review
and stays. What gets added: the chain's front (SCAN gate, FIND instrumentation) and its end
(CONSTRUCT measurement, library qualification) — because a perfectly aligned pose feeding an
unmeasured construction step is perfection nobody receives.

---

## 2. THE DOMAIN MODEL

The domain review found the plan's central concept — the island — has **no name anywhere in the
production code**, and that a dozen core terms mean different things in different files. Language
drift is how the last five backend "fixes" of the click-pair contract broke calibrated behavior.
So the model comes before the code.

### 2.1 Ubiquitous language — final names

These names are canonical from now on, in code, reports, and conversation. Where today's code
diverges, the rename is scheduled in the execution plan (§3).

| Final term | Definition | What changes in code |
|---|---|---|
| **Mark** | A doctor's recorded intake gesture (centre mark, rim mark, border points, brush). Data — its authority is decided by consumers, not by the mark | Marks v2 schema at the UI source (slice 23); the four field styles in `ConfirmedSite` consolidate; click/marks/brush/gesture wording unifies |
| **Locator** | The role Marks play after this plan: select which island, seed the search, provide a prior, cross-check as advisory — **never load-bearing on the pose** | Today the word appears once, in a comment. It becomes the `SeatAnchor` value object's contract (slice 17) |
| **Seed** | Derived local-frame start location for segmentation | The inverted vocabulary (`seed_source="click"` currently means *no* click) is corrected when `SeatAnchor` lands |
| **Island** | The machine-segmented cap-only region: centre, radius, boundary, convergence evidence, contamination stats. **CONVERGED-or-absent — no partially-trusted islands** | New `domain/island.py` aggregate (slice 6; the probe source it ports lands in slice 5). Today: zero production identifiers — the plan's core concept is code-homeless |
| **Patch** | The point set fed to a seat, **carrying its provenance** (machine crop / brush / seed-localized) | Provenance-carrying type; today one variable with three unlabeled origins |
| **Seat** | Rim-first placement result: variant + pose + method + residuals + **anchor provenance** (which anchor bore load — the question this whole plan is about, currently recorded nowhere) | `SeatAnchor ∈ {clicked, machine, fallback}` field (slice 17) |
| **Rim / RimBand / RimCircle / PosedRing** | Physical edge / scan-evidence annulus / fitted 3D circle / template's rim at pose | Four concepts, four names — today five words used interchangeably across 300+ occurrences |
| **CodeReading** | The e8 coded-cutout instrument's output (primary rotation evidence) | Rename from "notch" (`notch_reading` etc.) in slice 16b; docs and code finally speak the same word |
| **RecessClock** | The fallback rotation instrument on the scanned depression; phantom-convicted azimuth-biased | Rename "void" → "recess" in the clocking context (slice 16b; the word "void" stays only in Detection's unrelated `void_ratio`) |
| **Bore vs Channel** | Bore = the template CAD's hole. Channel = the constructed prosthesis's screw channel. **They differ by the measured 0.43–0.76 mm eccentricity — conflating them hid finding C2** | Two names, and the new `delivered_channel_vs_recess` metric (slice 12) measures the one that reaches the patient |
| **Grade vs Gate** | Grade = QA read-out (high/medium/low). Gate = a routing decision | Today two modules are both named "confidence". Renamed in slice 16b, before the confidence re-grade makes the word mean a third thing |
| **Advisory** | Non-binding operator signal — one channel | Five current uses consolidate; machine-vs-click disagreement and border disagreement become ONE advisory |
| **Coverage** | Fraction of ROI within tolerance — a read-out, never an objective, never called "fitness" | The package key `fitness` (auto_flow.py:1705) renamed (slice 11) |
| **Declaration** | The doctor's authoritative variant statement — the one input that collapses height twins | Already consistent everywhere. The one term the system got right; unchanged |

### 2.2 Bounded contexts, aggregates, invariants

Nine contexts: **Detection → Intake/Marking → Segmentation (new) → Seating ⇄ Identification →
Clocking → QA/Confidence → Construction → Delivery.** Each invariant below is a rule with the
test that guards it (tests are named in §3; new ones marked •new).

- **Detection** — aggregate `CandidateSite`. **D1:** Detection consumes only the scan, never
  human input. (Guard: existing propose-stage tests + •new detection recall columns, slice 10.)
- **Intake** — aggregate `CaseIntake`. **I1:** the declaration is authoritative.
  **I2:** corrections happen at the UI source, never by backend self-correction (five failed
  attempts prove why). **I3:** the centre+rim pair-integrity contract is superseded **by the
  client's 2026-07-21 product decision** — implemented as an explicit Marks-v2 schema change at
  intake, versioned; the old pair type dies at the boundary, never mid-pipeline (slice 23 —
  otherwise it is backend self-correction attempt #6).
- **Segmentation** (new) — aggregate `Island`. **S1:** union-safe — never remove points the
  posed template explains (•new `test_union_safe_mask_preserves_submerged_cap`; today's probe
  loses 53–83% of cap points on submerged caps). **S2:** CONVERGED-or-absent. **S3:** a seed
  only selects which island; it never shapes the island.
- **Seating** — aggregate `Seat`. **T1:** ranking never sees winner-only refinement (existing
  structural tests). **T2:** monotonic gated passes; ride-off p90 ≤ 1.5 (existing).
  **T3:** ring-fixed — the rim cannot move (existing). **T4:** stability refusal ≤ 0.35
  (existing). **T5 (new, previously unnamed and therefore unprotected):** *no Mark bears load —
  Marks seed, Islands anchor; and the fallback path is behavior-identical to today* (•new
  `test_fallback_path_byte_identical`, slice 17).
- **Identification** — aggregates `VariantId`, `Calibration`. **ID1:** inseparable → the doctor
  decides; declared ≠ identified → an explainable flag, never silence (existing contract
  tests). **ID2 (new name for an old practice):** a score is only
  comparable under the Calibration it was measured with — Calibration = score family + cut +
  fleet snapshot + seat-path version, an aggregate, not a constant (guard: recalibration harness
  + •new `test_declared_id_4_of_4_post_recal`, slice 26).
- **Clocking** — aggregate `ClockReading`. **C1:** codes primary, recess fallback, neither →
  `rotation_unverified`. **C2:** confirm re-read ≤ 12°. **C3:** instrument disagreement ships;
  the phantom arbitrates. **C4:** operator nudge passes the same gates. All existing and green —
  plus •new **C5:** no change may downgrade a site from code evidence to recess
  (`test_promotion_refused_on_codes_loss`, slice 25 — the t20 lesson).
- **QA/Confidence** — aggregate `SiteAssessment`. **Q1:** read-only. **Q2 (new, the rule behind
  Cause 3):** *an instrument may never be anchored to an input under its own judgment* — the
  rule that makes click-anchored rim-agreement wrong, and that equally forbids a future stability
  probe from certifying the segmentation through the segmentation (•new blindness-closure and
  discrimination tests, slices 15/27). **Q3:** advisory fail-closed. **Q4:** a probe must
  discriminate known-sick sites or it does not ship. **Q5:** no warnings off a convicted-biased
  instrument when the primary is verified (slice 16).
- **Construction** — sealed `_cap_sdf` voxelization path (the fine-pitch seal hazard is a
  recorded gotcha). •new **CN1:** the delivered channel's relation to the scanned recess is
  measured, not assumed (slice 12).
- **Delivery** — **P1:** flags travel with the package. **P2:** keys say what they carry —
  violated twice today (`fitness` carries coverage; `alignment_error_mm` is a seed-delta with a
  known collar-height bias the code itself warns about). Fixed in slice 11 (keys) + the
  slice-16b rename batch (`alignment_error_mm`).

### 2.3 Refactorings the model demands (domain free of framework/IO, applied concretely)

`run_auto_case` in `auto_flow.py` is a ~850-line loop where all nine contexts meet: e8 clocking
gates hard-coded inline (~lines 1560–95), identification's inseparability rule inline
(1598–1603), QA computed against the clicked circle (1646–56), and the de-facto site assessment
is an untyped dict. The stability bootstrap (`pipeline.py` ~989–1073) hand-copies the seating
closures — which is exactly why today's spread certifies the *base* seat, not the *shipped* pose.
The model demands, in dependency order:

1. **`domain/island.py`** — the segmentation mathematics (evidence-centre refine, closed-ring
   edge scan, 48-bin radial march, strict/plane dual-run) is pure geometry and belongs in the
   domain layer; only the mesh/IO wrapper is an adapter. (The prior plan's "port into an
   adapter" misfiled it.)
2. **`domain/rim_evidence`** — Detection and Segmentation share the rim-slab ring-evidence
   kernel; naming it prevents a second copy growing (the probe already grew one). The cap7020
   chooser-defect regression test lives here.
3. **`seat_site(intake, island, catalog) → Seat`** — extract the winner-pass chain (~250 inline
   lines) as a domain service called by BOTH the pipeline and the stability probe. Without this,
   the confidence re-grade would re-implement seating a third time — structurally reproducing
   the defect it fixes. Extraction is zero-diff, provable with the existing battery + scoreboard.
4. **`SeatAnchor` value object** (clicked | machine | fallback) — turns the audit's 13 click
   consumption points into one anchor-construction site, and gives invariant T5 a type to live in.
5. **`qa_metrics` module** — rim-agreement out of its private home (auto_flow:460); the
   scoreboard stops computing its own copy.
6. **Renames with teeth:** Grade/Gate module split; `notch→code_reading`; `void→recess` (clocking
   only); `fitness→coverage`; `alignment_error_mm` recomputed correctly or renamed
   `seed_delta_mm`; delete the dead legacy `domain/clocking.py` (scan-body flat-feature logic —
   nothing on a revolute cap has a flat).
7. **Marks v2** at the UI source (intake-versioned pair split).

---

## 3. THE EXECUTION PLAN — XP-shaped

### 3.0 Rules of play

- **Version control is slice zero, not a nicety.** There is no `.git` today. 423 tests,
  calibrated thresholds, and every scoreboard snapshot are unversioned files on one machine; the
  client's own conventions ("small reversible commits") are currently unimplementable, and
  nothing records which code produced `notchclock-v1`. Every slice below = one commit, trunk-based.
- **Failing test first, named below.** A slice without its red test does not start.
- **Every pose-affecting slice lands against a scoreboard diff** (`--save/--baseline`) and the
  full battery; calibration re-pins are their own commits with pre/post snapshot pairs.
- **Decision rules DR1–DR5 (§3.8) are agreed with the client in writing before Phase E code.**
  Rules agreed in advance are cheap; negotiated after three failed iterations they are politics.
- Effort figures are single-engineer estimates; ⏎ = trivially reversible (single-commit revert);
  ⏎flag = reversible by feature flag without revert.

### 3.1 Phase A — Substrate (week 1)

**1. Version-control substrate** — *1 hour + remote setup.* `[PARTIAL 2026-07-23: the `locators-pre`
scoreboard snapshot is saved and verified; git init / remote / tagging DEFERRED by client — local code only.]`
`git init`; fix `.gitignore` (it
exists, prepared for a repo never initialized, and it would currently ignore
`apps/worker/reports/scoreboard/` — the evidence baseline; carve that out, keep `data/real/`
clinical scans ignored); add a private remote; tag `locators-pre` paired with a fresh
`fleet_scoreboard.py --save locators-pre` verified identical to `notchclock-v1`. No test — process.
⏎ n/a. *Tripwire:* any future delivery not revertible to a named tag = process incident.

**2. RNG determinism** — *1 day.* Failing test first: `test_probe_spread_deterministic`
(identical input → identical spread; fails today, measured 1.237 vs 1.303 mm on re-runs —
`sample_surface`'s draw is unpinned). Change: replace ambient `np.random.seed(0)` with an
injected `Generator`. Outcome: every measurement in this plan becomes reproducible. ⏎.
*Tripwire:* none — this blocks all measurement work until green.

**3. Battery split** — *1 day.* No pytest markers exist today; the full battery is 18 minutes,
which makes test-first performative. Change: markers — default suite = synthetic-fixture unit
tests (target < 2 min); real-scan/integration/server/benchmark behind `-m battery`. Outcome: an
inner loop compatible with red-green-refactor; full battery stays the pre-delivery/nightly gate.
⏎. *Tripwire:* battery-run frequency dropping = process incident.

**4. Surface `candidates_too_close`** — *half day.* Failing test:
`test_report_surfaces_candidates_too_close` on a known-tie fixture (computed at auto_flow ~1563,
never reported — today an invisible high-blocker). ⏎.

**5. Land the island probe under version control** — *half day.* `[PARTIAL 2026-07-23: the probe
mathematics is ported into production `domain/island.py` (slice 6); the version-control landing
rides the deferred git substrate.]` `island_probe.py` is not in the
tree (verified); "port" has no reviewable base until it is. Commit it + one characterization
fixture (`test_island_probe_characterization_cap6030` pinning the measured 0.027 mm). ⏎.

**Also fired in week 1, zero code (lead-time items — see §5):** `[DEFERRED by client 2026-07-23 —
none of these fired; they remain open asks, not cancelled.]` the client asks batch (vendor
interface spec, placed-cap ground truth, engraved-code photos), the phantom print order on the
client's production scanner, the FLE-study scheduling, and the decision-rules sign-off meeting.

### 3.2 Phase B — Walking skeleton + shadow measurement (weeks 2–3) *(folds prior Stage 1 + pre-work a/b)*

**6. WALKING SKELETON** — *2–3 days.* `[DONE 2026-07-23: `domain/island.py` + scoreboard shadow
columns live; zero pose movement proven on the scoreboard diff; battery green.]` One site (cap6030, the best machine-island performer at
0.027 mm), `segment_island` running in production as `domain/island.py` + mesh adapter, behind a
flag, writing three shadow columns (`machine_centre_dist`, `contamination`, `cap_coverage`) to
the fleet scoreboard. Failing test: `test_shadow_columns_populated_cap6030`. **Zero pose
movement** — scoreboard diff must read all-unchanged on pose metrics; battery green. Proves
end-to-end: probe→production port, determinism under injected RNG, scoreboard plumbing, the
converged/unconverged flag mechanism every later promotion rides, and snapshot-diff discipline.
Everything after this is widening or promoting. ⏎flag.

**7. Union-safe mask guard** — *1–2 days.* Failing test:
`test_union_safe_mask_preserves_submerged_cap` (a submerged-cap fixture where today's mask loses
53–83% of cap points — the roadmap-#9 warned failure). Change: never drop template-explained
points; cap-coverage becomes a hard gate input. ⏎.

**8. Strict/plane chooser fix** — *1–2 days.* Failing test: `test_chooser_cap7020_inversion`
(the 1.54 mm wrong-chooser fixture). Lives in `domain/rim_evidence` with the regression test. ⏎.

**9. Fleet-wide shadow + gate telemetry** — *1 day.* Failing test:
`test_shadow_columns_10_of_10_or_unconverged` (t7 re-run included — its probe run produced no
result file). Also lands the pre-mortem's telemetry: `island_converged`, `promoted_path`,
per-gate fire counts, and **would-promote computed in shadow** (the promotion gates are pure
functions of shadow data — so Phase E's real reach is known months early). ⏎flag.
*Leading indicator:* would-promote < 7/10 here forecasts trouble before any promotion code exists.

**10. Detection instrumentation** — *half day.* Failing test:
`test_detection_columns_present` (recall + candidate-proximity columns per site). Also: correct
the client-facing strategy's "no clicks needed on most sites" to the measured 8/10-with-candidate
/ 2-with-none. Honesty is a deliverable. ⏎.

**11. Package-key honesty** — *half day.* Failing tests: `test_pose_origin_written`
(implant.json gains the honesty field) and `test_package_key_coverage` (`fitness` renamed to the
coverage it carries; dual-key during transition with slice 29 as the named end date). ⏎.

**12. `delivered_channel_vs_recess` scoreboard column** — *1 day.* Failing test:
`test_delivered_channel_column_present`. The deliverable-level analog of `bore_void_off`: the
emitted prosthesis channel vs the scanned recess, per site. **This is the instrument that makes
finding C2 (§4.1) visible on the fleet — it must exist before any promotion lands, so we can see
whether seat improvements arrive at the prosthesis.** ⏎.

**13. Machine-marks autopsy** — *timeboxed 2–3 days (spike).* `[DONE 2026-07-23: DR1 NOT cleared
on this evidence; iteration targets named — radius under-read from grid-phase-unstable Kasa
(`island_r` identified as the stable alternative), coverage tissue bias, cap6020 march start.
These targets are segmentation iteration 1 in §8.]` Re-run the 18-run autopsy harness
with the pair overridden to the machine island circle **where converged** — the direct
measurement of promotion's real impact (the prior plan's headline payoffs — t20 rim 1.00→0.51,
bore 1.07→0.08; t7 rotation −150.5°→−3.6° — were ORACLE-anchored; the machine as probed loses to
clicks on 5/9 sites). The committed distribution sets Phase E's gates and feeds decision rule
DR1. Also shadow-compute the machine-band identification scores here (free) — answering the
score-family question (DR2) before Phase E is built, not after.

### 3.3 Phase C — Honesty at zero millimetres (week 4) *(folds prior Stage 2)*

**14. Extract `qa_metrics`** — *1 day.* Characterization tests pin today's numbers
(`test_qa_metrics_characterization`); rim-agreement leaves its private home; the scoreboard stops
computing its own copy. Refactor slice — zero behavior change. ⏎.

**15. Machine-anchored QA, dual-reported** — *1–2 days.* Failing test — the blindness-closure
contract, one of the three strongest red/greens in the program:
`test_machine_rim_agreement_worsens_on_shifted_pose` — on the +0.6x shifted-pose fixture the
machine-anchored metric must WORSEN while the click-anchored one improves (today's metric
improved 0.62→0.88 while the pose was 1.09 mm off). Both anchorings reported during transition
(scoreboard only — not report + run-history too; YAGNI), with slice 29 as the sunset. ⏎flag.

**16. Clock-bias relabel** — *1 day.* `[DONE 2026-07-23: consistency no longer routes attention
on code-verified sites; zero millimetres moved.]` Failing tests both directions:
`test_relabel_when_codes_verified` (codes + confirm re-read ≤12° → "instrument disagreement
(recess-azimuth bias, phantom will arbitrate)" instead of "attention") and
`test_recess_only_keeps_attention`. Stops five code-verified sites over-warning off the
phantom-convicted biased instrument (`bore_void_off` 0.58–1.35 mm, consistency 39–107° — bias,
not pose error). Zero millimetres moved. ⏎.

**16b. The §2.3(6) rename batch** — *1 day, each rename its own commit.* Grade/Gate module
split (before Phase F makes "confidence" mean a third thing); `notch→code_reading`;
`void→recess` (clocking context only — Detection's `void_ratio` keeps its name);
`alignment_error_mm` recomputed at the correct origin or renamed `seed_delta_mm`; dead legacy
`domain/clocking.py` deleted. Refactor slices — acceptance is battery green after each commit +
a grep showing the old vocabulary gone from the renamed context; zero millimetres moved.
Language honesty rides the zero-mm phase (grill A6). ⏎.

### 3.4 Phase D — Structural refactor + demotion (weeks 5–6) *(folds prior Stage 3, re-scoped per the adversarial amendment)*

**17. Extract the winner-pass chain + `SeatAnchor`** — *2–3 days.* The prerequisite refactor for
everything after it: `seat_site(intake, island, catalog) → Seat` extracted from the ~850-line
`run_auto_case`; the stability bootstrap's hand-copied closures deleted in favor of calling the
same service; `SeatAnchor` (clicked|machine|fallback) recorded on every Seat; the
provenance-carrying `Patch` type (§2.1) lands with it. Failing tests:
`test_seat_site_extraction_zero_diff` (characterization — scoreboard byte-identical) and
`test_fallback_path_byte_identical` (invariant T5's guard). Without this slice, the confidence
probe of the shipped-pose chain is unimplementable. ⏎.

**18. Free-path synthetic-border spike** — *1 day.* Pre-work (b): grounds slice 19's prediction
with a measured baseline on 276794487/t3 (today: +0.6y → 0.78 mm/7.6°, a 1:1 sensitivity).

**19. Border-circle demotion** — *1–2 days.* The prior Stage 3, correctly re-scoped: ONLY the
clicked border circle demotes (initializer + advisory cross-check; free seat + depth polish
always run; the fitness=1.0 fiction dies). The always-snap pair split does NOT happen here — it
moves behind Phase E's gate (the amendment: it is a fleet-wide seed change and must not land two
phases before recalibration). Failing tests: `test_depth_polish_runs_on_pinned_seats`,
`test_no_fitness_fiction`, `test_border_sensitivity_collapse` (vs slice 18's baseline). The
existing pinned-path contract tests assert TODAY's pinning behavior — they are rewritten
deliberately in their own commit, never silently edited.
Pose changes on border-gesture sites only. ⏎flag. *Tripwire:* scoreboard regression on any
non-border site = revert.

### 3.5 Phase E — Promotion behind gates (weeks 7–10, hard-timeboxed) *(folds prior Stage 4, unbundled into four independently revertible slices)*

The prior plan shipped this as one L-sized stage across three bounded contexts — a rollback unit
three contexts wide whose scoreboard diff could not attribute regressions. Unbundled. Every slice
here promotes ONLY where the island CONVERGED (bins-hit, cap-coverage, machine-vs-click sanity
bound from slice 13's distribution); otherwise the site keeps today's behavior + flag
`island_unconverged`. **A failed segmentation can never ship a worse seat than today.**

**20. E-a: ROI crop at machine centre + island mask** — *2–4 days.* The dominant cause first
(the record's own ranking: contamination is the medium→high lever). Failing test:
`test_roi_contamination_bound` on fixture. Outcome target: in-band contamination < 25% on
converged sites (today median 54–60%, bands 2–94% tissue). ⏎flag per site-class.

**21. E-b: seat band + arc bins from the machine ring** — *3–5 days.* Failing test — the
strongest red/green in the program, absent from the prior plan:
`test_pose_stable_under_0p6mm_gesture_offset` — the 16.6°-cliff contract: under a +0.6 mm rigid
gesture offset the shipped pose must stay under the bar (fails today by construction; passes by
construction when the band anchors to the machine ring). ⏎flag.

**22. E-c: guard anchors + centering target re-anchor** — *2–3 days.* Failing test:
`test_guards_anchor_to_machine_ring_on_shifted_gesture` (depth/best-fit/centering/clock accept
gates + `_center_on_rim` target measured against the machine ring, not the clicks). ⏎flag.

**23. E-d: always-snap / pair split** — *1–2 days.* Behind the same gate. The commit message
cites the 2026-07-21 client product decision superseding the pair-integrity contract — recorded,
not snuck in. Implemented as Marks v2 at the UI source (invariant I3): the old pair type dies at
intake. Failing test: `test_pair_split_at_intake_versioned`. ⏎flag.

**24. Honesty notes carried (unchanged from the adversarial record):** the oracle-vs-machine gap
is the whole reason Phase E is gated; t7's islanding currently fails outright (2.04 mm off,
detector None, cap coverage 0.15 — the coverage gate fires its fallback; t7 keeps today's
behavior until fixed, and its real fix is the SCAN link); t20/cap7020's predicted improvements
are conditional, not promised.

**25. Code-evidence survival gate** — *1 day.* Failing test:
`test_promotion_refused_on_codes_loss` with t20's measured counterexample as the fixture (oracle
anchor shift lost codes: −2.1°→−23.6°, codes→recess). No promotion may downgrade clock evidence.
Invariant C5. ⏎.

### 3.6 Phase F — Recalibration + confidence (weeks 11–12) *(folds prior Stages 5–6)*

**26. Recalibration** — *2–4 days + a budgeted reopen.* Mandatory once Phase E lands; never ship
one without the other — **in both directions** (DR2: declared-ID < 4/4 on the labeled arches
BLOCKS Phase E; it does not get iterated into agreement). Re-measure the identification score
distribution on the new seat paths; re-pin the cut (today −0.4); every per-site battery ceiling
re-pin is its own commit with a pre/post snapshot pair. Budget note carried: the record says no
clean LINEAR-family win exists under click noise — the machine band may reopen the score
*family*; slice 13's shadow scores tell us early; if it reopens, that is its own planned week,
not a surprise. n=4 labeled arches is thin — the placed-cap ground-truth ask (§5) grows it.

**27. Machine-side stability probe — ONE perturbation family** — *2–3 days.* The click-noise
bootstrap becomes vacuous by construction once marks are locators (locator-only simulation:
spread collapses 7–13×) — it must be REPLACED, not kept. Start with one family (YAGNI; the prior
plan's three). Failing tests: the discrimination contract
`test_probe_discriminates_known_sick_sites` (t7 grades low, cap7030 not high, cap6030 under the
bar) and `test_probe_not_vacuous`. Invariant Q2 applies: the probe perturbs INPUTS, never
certifies the segmentation through the segmentation. Probes the **shipped-pose chain** via the
slice-17 service (today's spread certifies only the base seat). Add families only if the
discrimination test fails. ⏎.

**28. Rotation enters the grade + coverage 10/10** — *1–2 days.* Failing tests:
`test_recess_only_caps_at_medium` (high REQUIRES code-verified rotation with confirm re-read
≤12°), `test_t4_graded` (grade computed on 10/10 — t4's bootstrap currently returns None);
visible-band rim scoring so t13's flank floor (a correct seat honestly reading 1.47 mm against a
25%-visible ring) is a flag, not a residual. ⏎.

**29. Deletion slice** — *1 day.* The click-noise bootstrap, the click-anchored QA columns, and
every transition dual-report are **deleted, not flagged off**. Failing test: battery green with
them gone; scoreboard diff shows only column removals. This is the named end date promised in
slices 11 and 15. ⏎.

### 3.7 Phase G — Chain completion + physical truth (parallel track + external lead time)

**30. Capture gate at upload** — *2–3 days, can start ANY time after Phase A (independent of
everything).* Failing test: `test_capture_gate_rejects_t7_class_scan` (rim-arc coverage,
code-band visibility, exposure ≥1 mm; concrete refusal message). The industry's actual accuracy
mechanism, the only fix for t7-class scans, and the fastest client-visible win. ⏎.

**31. Library qualification gate** — *1–2 days.* Failing test:
`test_library_drop_qualification` — per vendor drop: watertight, axis win-margin, ring + bore
offsets vs spec, estimator stability, open-loop census. The catalog burned this project once
(the "sideways caps" week traced to loading defects); "the libraries we have" is a goal input
and now has an acceptance contract. ⏎.

**32. Phantom print + scan, WITH the construction leg** — *external lead time; order the print
in week 1.* `[DEFERRED by client 2026-07-23 — no print order; the phantom remains the named
physical arbiter for §7's flagged conventions and for codes-vs-recess.]` Everything the prior Stage 7 promised: truth-pins grade→platform error ("high means
≤X mm with probability Y"), arbitrates codes-vs-recess and calibrates the recess-azimuth bias,
checks the bore-mouth estimator's cut-sensitivity, confirms "p90 ≈ 2× actual". PLUS the missing
end-to-end leg: run CONSTRUCT+PACKAGE on the phantom and measure the **emitted channel vs the
designed bore** (`test_phantom_channel_error` — the first ground-truth number the deliverable
has ever had). Carried caveats: regenerate through the sealed `_cap_sdf` path (fine-pitch seal
hazard erased half the crowns once); the recess column inherits the recess-shallower-than-channel
caveat. Re-print per new scanner. The centre-click FLE study runs in parallel at the lab —
re-justified honestly: it bounds the island *seed* tolerance (the 0.8 mm degraded-seed margin was
calibrated off border-click noise; centre-click noise is unmeasured).

**33. Vendor-interface seating resolution** — *product decision + 1–2 days code once the spec
arrives (ask fired in week 1).* `[DEFERRED by client 2026-07-23 — the ask email is not sent; the
spec remains the missing leg named in §7.1.]` Resolves C2/C3 (§4.1): is the channel bored at the canonical
axis correct, or must it follow the measured 0.43–0.76 mm bore eccentricity? Blocks
*interpretation* of slices 12/32's numbers, not their landing. Until resolved, the honest
position is: **we cannot yet say what perfect alignment is worth at the prosthesis** — which is
exactly why the instrument lands first.

### 3.8 Decision rules — agreed in writing before Phase E code (the pre-mortem's output)

`[Sign-off meeting DEFERRED by client 2026-07-23. The rules below still bind the engineering —
Phase E code does not start until they are countersigned.]`

- **DR1 — Segmentation go/no-go.** Pass bar (from slice 13's autopsy): machine beats-or-ties
  clicks on ≥7/10 sites; code evidence survives on every codes site; in-band contamination <25%.
  Timebox: two segmentation iterations (~2–3 weeks each). Two consecutive failures → Phase E is
  **abandoned for this engagement**, the fallback tier ships (§3.9), and islanding moves to a
  color-scan-gated research track. The engineer runs the harness; the CLIENT accepts the tier
  decision. *Leading indicator:* slice-9 shadow shows machine-closer <5/10 or contamination
  plateauing >30%.
- **DR2 — Identification is not traded away.** Declared-ID 4/4 on the labeled arches blocks
  promotion in BOTH directions (the prior plan had only one). Fleet inseparable-rate rising vs
  `locators-pre` is a tripwire.
- **DR3 — "Gates fired everywhere" is a defined FAILURE, never reportable as success.** The
  known-today fallback population is already 5–6/10. Promotion coverage (machine-path sites/10)
  is reported as prominently as rim numbers. Coverage <70% after iteration 2 = Phase E failure
  state → DR1. Secondary: projected high-count <3 at slice 27.
- **DR4 — Overfit guard.** Every threshold in the system is tuned on 10 sites / 2 systems /
  one lab, and the record already contains one synthetic-calibrated gate passing a 1.75 mm-wrong
  pose. The 10 sites are hereby the **named calibration set**; all future data lands as holdout
  first; a calibration-envelope check at intake (mesh density, rim point count, exposure,
  band-tissue fraction, code correlation — outside fleet p95 → auto-attention + grade capped
  medium); N-case shadow onboarding per new scanner/doctor/vendor; phantom re-printed per scanner.
- **DR5 — Delivery discipline.** No client delivery without battery green + fresh scoreboard
  diff; any change not revertible to a named tag is a process incident.

### 3.9 The fallback tier — named and priced, so the engagement cannot fail by segmentation alone

If DR1 fires, what ships is Phases A–D + capture gate + QC artifacts + operator nudge:
rotation code-verified ≤3.1° on 8/10, honest QA (blindness closed), border-sensitivity killed,
t7-class scans caught in-chair, acceptance images in every package. It honestly cannot claim
"high" (click noise really moves poses up to 1.09 mm/16.6°) — so it ships as
**"medium-confidence automation + operator review + acceptance artifacts"**, its own milestone
with its own price. The engagement succeeds either way; only the ceiling differs.

---

## 4. GOAL-CHAIN COMPLETIONS THE PRIOR PLAN MISSED

### 4.1 The construction link (the sharpest audit finding)

The prior plan had ZERO stages past the pose, while the record shows the construction link
carries unresolved systematics of the **same order as everything the alignment work buys**:

- **C1** — a 0.3 mm seat improvement DOES move the deliverable 0.3 mm rigidly (one
  `pose_matrix` poses cap, scan body, and prosthesis) — but it lands on unvalidated
  construction-frame conventions of the same magnitude, so today the gain is unverifiable at the
  deliverable.
- **C2** — the delivered screw channel is bored at the canonical axis, so the entire rotation
  program never moves it — while our own measurement puts the physical bore 0.43–0.76 mm off
  that axis, and the "coaxial → clocking inert" premise was already convicted wrong once. Two
  records contradict at the deliverable. → slices 12 (measure), 33 (resolve), 32 (ground truth).
  `[2026-07-23 UPDATE — C2 is now CONFIRMED at the deliverable on all 3 real packages (delivered
  channel exactly at the canonical axis; misses the cap's true channel by 0.36–0.42 mm and the
  scanned recess by 0.60–0.84 mm — §7.1). Also: the 0.43–0.76 mm figure cited here and elsewhere
  in this document is the ESTIMATOR's number; the zero-noise loop truth is 0.20–0.59 mm on the
  ~opposite azimuth (§7.1 finding 1).]`
- **C3** — seating vertical offset + z-sign vs the implant platform needs each vendor's
  interface spec (recorded architecture debt; the z-sign of a near-symmetric part is not
  data-derivable). → slice 33's ask, fired week 1.
- **C4** — one construction part serves every site and variant: IDENTIFY precision reaches the
  deliverable only through the pose. Recorded honestly; acceptable for now, revisited only if
  slice 32's numbers demand it.
- **C5/C6** — the coaxial `_derive_pose` assumption is asserted per-catalog, never measured
  per-part; no test anywhere measures the emitted channel vs anything real. → slices 31, 32.
- **C7** — `pose_origin` unwritten, `fitness` mislabeled, fixed 1.0 mm channel radius across
  systems. → slice 11 now; radius joins slice 33's spec work.

**The cheapest correction in the whole plan:** land slice 12 (the `delivered_channel_vs_recess`
column) and fire slice 33's ask BEFORE Phase E, so "perfect alignment" is provably worth
something at the prosthesis, not just at the seat.

### 4.2 Library qualification (slice 31)

"Using the libraries that we have" is a goal input with no acceptance contract, and the catalog
has already burned the project once. Every vendor drop henceforth passes the qualification gate
before any case uses it.

### 4.3 Detection honesty (slice 10)

Detection is good (6/10 within 0.062 mm) but was overclaimed ("no clicks needed on most sites")
and is uninstrumented, with 0 candidates on 2/10 scans. Non-fatal — clicks remain locators, and
island selection presumes candidates exist — so the fix is instrumentation + the capture gate,
not a new algorithm. The strategy document's claim gets corrected.

---

## 5. RECOMMENDATIONS (ranked; ⚡ = we can implement immediately)

`[Status 2026-07-23: items 1–5 DEFERRED by client (git/remote, sign-off meeting, phantom print,
client-ask emails, FLE scheduling) — local code only, demo first. Item 8's first artifact
(`locators-pre` snapshot) exists. The rest are queued in §8.]`

1. ⚡ **Version control + private remote + tagged snapshots** (slice 1, ~1 hour). The
   precondition for the client's own stated conventions and the cheapest insurance in the
   engagement. Five layered irreversible edits already cost us the reclick-pair saga.
   *First step: `git init` today.*
2. ⚡ **Pre-commit decision rules DR1–DR3 with the client** before any promotion code. *First
   step: a 30-minute sign-off meeting on §3.8 this week.*
3. ⚡ **Order the phantom print NOW, on the client's production scanner.** Three phases lean on
   an arbiter that is physical lead time, not code time. *First step: send the regenerated
   `phantom-plate.stl` + `docs/engagement/phantom-protocol.md` to the print vendor.*
4. ⚡ **Fire the client-asks batch** (`docs/engagement/client-asks.md`): the vendor interface
   spec (unblocks §4.1), placed-cap ground truth + engraved-code photos (converts the fleet into
   a labeled holdout and grows the n=4 calibration set), implant system on the Rx. *First step:
   one email, drafted today.*
5. ⚡ **Schedule the centre-click FLE study with the lab** (protocol already written:
   `docs/engagement/fle-centre-click-protocol.md`) — human-protocol lead time.
6. **CI on linux/3.11 with pinned golden values** — closes the recorded 3.9/arm64 vs 3.11/linux
   divergence debt before productization (the environment is a snowflake: Open3D segfaults,
   Accelerate filters). *First step: one GitHub Actions workflow running the fast suite.*
7. **Battery tiering + determinism** (slices 2–3) — makes test-first real instead of performative.
8. ⚡ **Weekly scoreboard-diff cadence to the client** — the instrument they explicitly asked
   for ("so we know what changes improve or don't improve the model") becomes the status report.
   *First step: send the `locators-pre` snapshot with this plan.*
9. **Ship the upload capture gate early** (slice 30) — independent of everything, catches
   t7-class scans in-chair, the industry's actual accuracy mechanism, fastest visible win.
10. **Pilot color-scan (PLY/OBJ) intake in parallel** — scanners capture color natively;
    titanium-vs-tissue separation is segmentation insurance if DR1 fires. Intake recommendation
    only; no color-segmentation code in this plan (YAGNI).
11. **Holdout discipline + calibration-envelope intake check + new-source onboarding** (DR4) —
    generalization currently rests on gates tuned on the same 10 sites they guard.
12. **Move gate/threshold rationale from private memory into repo docs** — bus-factor-1
    mitigation for judgment, not just code. *First step: one `docs/gates.md` page, one gate per
    heading, the "why" and the measurement behind each of the ~30 thresholds.*
13. **Parallel-session hygiene** — dedicated demo ports (5173/8000 were already taken over
    once), pipeline-version salt in the `/run` cache key (the unsalted key "bit twice"),
    restart-after-rewarm script, environment runbook in the repo.

---

## 6. WHAT WE EXPLICITLY DO NOT DO

**Failed routes — measured dead ends, never to be re-proposed:** recess-authoritative clocking
(rotated away from codes on 5/7); 1-D azimuthal profile extractors (≤3/7); fixed-3D-ring-point
clocking (0.20 mm leak); interleaved centre/clock iteration (+0.51 mm rim cost); global feature
solvers (TEASER/FGR/4PCS — structurally inapplicable to smooth revolute caps, measured twice);
rebuilding the inner solver (already ~5 µm on clean input); backend self-correction of corrupted
click pairs (five failed attempts — corrections at the UI source, always); a separate
platform-depth intake (redundant with the declaration); Fitzpatrick TRE as a grade driver
(deleted from grade code in slice 29, not just demoted in prose); surface-coverage as an
optimization objective (a perfect seat once read "41%").

**Physics floors — flagged honestly, never "fixed" in software:** height twins under submergence
(the declaration is the collapse; 95–98% shell coincidence within 0.2 mm); t13-class flank
floors (visible-band scoring + flag — a correct seat honestly reads ~1.5 mm there); t7's scan
hole (a rescan workflow, caught by the capture gate, not an algorithm); the recess-azimuth bias
and the bore-mouth estimator are calibrated by the phantom only — never retuned blind.

**Rotation is not re-planned.** e8 coded-feature clocking is shipped, code-verified ≤3.1° on
8/10, at the commercial gold standard's own accuracy class. This plan only protects it (slice 25).

**No operator hole-marking or code-clicking.** The bore interior is not in the scan; the machine
reads the recess and the coded band better than a click would. Patent landscape noted in the
record (Nobel's boundary matching; ZimVie's coded-abutment workflow operator-clicked codes) — we stay on our own
shipped depth-image correlation.

**The doctor's marks are never deleted.** They remain the locator, the island selector on
multi-implant arches, and the human cross-check advisory. "Approximate locators only" demotes
authority; it does not remove the gesture. The declaration stays required.

**YAGNI cuts (from the XP review):** one probe perturbation family until the discrimination test
fails, not three; dual-anchored QA in the scoreboard only, with slice 29 the named end date; the
research-only benchmark tests out of the default battery; the four demo scripts frozen; the
second orchestration path (`stages.py`/`orchestrator.py`) frozen; the `_best_clocking` face
sweep (measured flat, 0.04–0.07 mm, no discrimination) cut to a catastrophe guard after one
cheap scoreboard-diff measurement; border-disagreement and machine-vs-click merged into ONE
advisory channel; no color-segmentation code.

**And one standing rule:** the predicted "~5–7 sites grading high" may NEVER appear in any
acceptance criterion. It is a forecast, not a quota — t20 and cap7020's memberships are
explicitly conditional, and the claim of this entire plan is honesty, not a number. If the
phantom moves the bars, the distribution follows the truth.

---

## 7. Screw-channel guarantee (2026-07-23)

The client asked: *"Do the screw channels need to be aligned perfectly? How can we GUARANTEE the
screw lines are correct? Is this information in the scan, in the healing cap, or in the library?
Where else do we need to align on this project?"* Answered here from the settled record (§1 goal
chain, §4.1, `docs/architecture-current.md`, `phase2a-completion-report.md` §6–7), a read-only
code autopsy of the full channel chain run 2026-07-23 (probes over the library cap CADs, the DESS
construction part, and the 3 real delivered packages — no pipeline runs), and industry research
(sources cited inline; full citation list in the session research record).

### 7.1 Where the truth lives

The industry's answer has three legs, and ours maps onto them exactly:

| Leg | Industry | This project (measured) |
|---|---|---|
| **LIBRARY part owns the channel** | The manufacturer CAD library part carries the channel geometry, seat, and allowed angulation; the milled channel's axis is *derived in CAD from the library part at the measured pose — never measured from the patient* | Our cap CADs hold the channel **exactly**: the open-boundary loops are perfect circles (radius/z std 0.002 mm); bore mouth r = 1.102 mm and base opening r = 2.248 mm share the SAME xy → a straight channel parallel to the canonical axis, **0.20–0.59 mm off it** (direct zero-noise read). The DESS construction part even carries its own designed lumen: r = 2.00 mm, coaxial ≤ 0.026 mm |
| **DECLARED system owns the platform** | The prescription (implant system + platform) is declared, never inferred; wrong/mixed library = cannot seat "regardless of how accurately the scanning was performed" | Our `scan_body_to_platform` is the identity placeholder (real_case.py:47,130); z-sign not data-derivable (final_product.py:12–18). **This leg is missing** — it is C3, the vendor-spec ask (slice 33, deferred) |
| **SCAN owns only the transfer part's POSE** | Scan bodies transfer implant pose at ~105–127 µm / 0.22–1.25° (PMC10568787); acquisition is the dominant, irreversible error stage | Our scan never sees the bore interior (auto_flow.py:563). It holds the recess mouth (a doubly-biased instrument — scan-side centroid per §7.1 of the phase2a report, plus the CAD-side estimator bias below) and the **coded cutouts — the rotation key**, rigidly related to the bore in CAD (phase2a §6–7) |

**Compressed answer to the client's "where is it?":** the LIBRARY holds the channel exactly. The
SCAN holds only pose evidence — the coded cutouts (rotation; solved, ≤3.1°) and the recess mouth
(position; biased). The HEALING CAP is the physical courier between them. And the missing piece
is in **none of the three: the VENDOR interface spec** (seating offset, z-sign, channel
radius/convention).

**Autopsy findings that move the record (2026-07-23):**

1. **Estimator bias (NEW).** The production bore estimator `_template_bore_centre`
   (auto_flow.py:534–556) reads the bore on the ~OPPOSITE azimuth from the truth: it is a surface
   centroid, and a hole has no vertices, so the centroid is *repelled* from the hole. cap6030:
   estimator (+0.589, +0.133) vs loop truth (−0.354, −0.044) = **0.96 mm apart (~174°)**; cap7030:
   0.87 mm. The settled 0.43–0.76 mm eccentricity figure is the estimator's; the truth is
   0.20–0.59 mm on the other side. Consumers inheriting the bias: `_void_clocking`
   (auto_flow.py:678,687,709,735), scoreboard `bore_void_off` (fleet_scoreboard.py:16,66), QC
   bore★ (qc_render.py:51,201–204). The docstring's "no cheap ground truth exists"
   (auto_flow.py:543) is false — the outline loop is zero-noise.
2. **C2 confirmed at the deliverable.** Three real delivered packages, un-posed by
   inv(pose_matrix):

   | case/tooth (variant) | delivered channel local xy (r) | vs cap bore (estimator) | vs cap channel (loop truth) | vs scanned recess |
   |---|---|---|---|---|
   | cap6030 t29 (6030) | (0.000, −0.000) r 0.998 | 0.604 mm | **0.357 mm** | **0.596 mm** |
   | 276794487 t3 (6020) | (−0.050, −0.003) r 1.026 | 0.674 mm | **~0.38 mm** | **0.838 mm** |
   | 295811960 t29 (6020) | (−0.000, 0.000) r 0.998 | 0.623 mm | **0.375 mm** | **0.821 mm** |

   The delivered channel sits EXACTLY on the canonical axis (final_product.py:65–69: position
   [0,0,mid], axis [0,0,1], r = 1.0 fixed). It misses the cap's true channel by 0.36–0.42 mm and
   the scanned recess by 0.60–0.84 mm on every measured case — and the entire rotation program
   changes none of it, because a coaxial cylinder is rotation-invariant. These rows seed the
   slice-12 column.
3. **Lumen erasure (C7's first measured victim).** `_cap_open_boundaries` seals the DESS tube
   before voxelization, so the SDF fills the vendor's designed 2.00 mm-radius lumen with invented
   material, and the pipeline re-bores at fixed r = 1.0: the delivered part carries a wall band
   [0.97–1.05] that does not exist in the vendor CAD at any height, and the delivered channel is
   **half the vendor's designed diameter**.
4. **Platform hint in the CAD itself.** The cap's base opening — the platform interface — is
   concentric with the CHANNEL, not with the outer revolute axis. The CAD is suggesting the
   implant axis sits 0.36–0.59 mm off where `_derive_pose` reports it. Only the vendor spec or
   the phantom can arbitrate this; until then it ships as a flagged open convention, never a
   silent assumption.
5. **Library duplication hazard (NEW).** `zimmer-4.5-6020/6030` CADs are byte-identical (sha256)
   to their `neodent-gm` counterparts. No vendor-drop qualification gate exists (slice 31's case,
   now with a concrete exhibit).

### 7.2 Does the channel need to be perfectly aligned?

**Yes for undesigned error — at the 0.2 mm / 2° scale. No for designed angulation — which is a
specified allowance, not slop, and is asymmetric:**

- **Designed axis allowance:** angulated-screw-channel (ASC) systems permit the channel 0–25°
  off the implant axis in any azimuth (Nobel ASC spec), some systems 25–30° (ITI review); exocad
  caps ASC at 20° unless the implant library says otherwise; 3Shape validates against the implant
  provider's maximum and BLOCKS export on violation. Angulation is not free: preload and
  reverse-torque fall significantly at 25–28° (no significant difference 0° vs 15°), and
  driver/screw wear peaks at 25° (PMC10051685, PMC11289999, PubMed 31307810).
- **Undesigned error budget:** pose transfer through a scan body is ~105–127 µm / 0.22–1.25°
  (PMC10568787); misfit-acceptability thresholds are ~120 µm marginal, ~150 µm internal, ~230 µm
  full-arch misfit linked to screw loosening (PMC11391652, PMC12937834). Emergence is judged
  anatomically — cingulum (anterior) / central fossa (posterior); an exit displaced ~1–2 mm into
  the buccal facet is a recognized clinical failure with published rescue decision-trees.
- **Verdict on our numbers:** the measured 0.36–0.84 mm delivered miss (§7.1) is **3–6× the
  industry's entire transfer-error budget** and is NOT covered by ASC tolerance — that tolerance
  covers *designed* angulation of the library part, not coaxiality error between the cut channel
  and the physical bore.
- **Rotation and angulation still decide where the hole lands:** the cap channel genuinely sits
  0.20–0.59 mm off-axis, so clocking rotates the channel's landing point around that circle —
  position and rotation are coupled at exactly the scale we measure. And the unguarded coaxial
  assumption (C5) has a grill: 1° of interface angulation = 0.14 mm/° lateral over the 8 mm part
  (0.17–0.26 mm/° at prosthesis height); a 17–30° angulated abutment would be 2.4–4.6 mm off,
  silently.

### 7.3 How the industry guarantees it — and what that convicts here

The industry guarantees the channel **by construction, not by measurement**: the screw-critical
geometry is premanufactured (Ti-bases, premilled blanks — the connection is never touched by the
mill), and where the channel IS custom-cut, its axis is derived in CAD from the library part
placed at the measured pose. The residual is pose-transfer error (~0.1 mm class). Then a
**physical verification leg** — verification jigs, try-in, screw-resistance/Sheffield tests —
because the industry does not trust the digital chain end-to-end (a 2026 review reports 60–80% of
frameworks flagged non-passive clinically, only ~30% truly acceptable by micro-CT; single-review
evidence, flagged). Critically: **no commercial product digitally verifies the as-built channel
against the as-designed channel** — the guarantee is construct-from-library + pre-export rule
gates (3Shape: channel-vs-provider-max-angle, minimum wall thickness — violations render red and
block export) + physical seating checks.

Three consequences for us:

1. Our §4.1 gap can ONLY be closed at construction time — bore FROM the library part AT the
   measured pose. Industry practice directly convicts `final_product.py:65–69`.
2. Today we have the opposite of a guarantee: `tests/test_final_product.py:22–31,42–57` assert
   the channel IS at the canonical axis — **the test suite enforces the defect**. No instrument
   anywhere renders or measures the delivered channel (`delivered_channel` appears nowhere in
   src/tests/tools; QC clockview draws the biased estimator bore★ instead).
3. We have no physical-verification leg. The phantom (slice 32, deferred) is our jig analog and
   the named arbiter for every flagged convention below.

### 7.4 The guarantee design — instruments that close the chain

All local-only except the two marked arbiters. Order matters: G2 → G3 → G1 → G4 so the fleet
column shows the before/after of the boring fix.

| # | Instrument | Failing test (first) | Effort | Demo visibility |
|---|---|---|---|---|
| **G2** | **Bore-centre estimator truth.** Replace `_template_bore_centre`'s surface centroid with the open-boundary-loop read (zero-noise, already probed). Heals every consumer of the bias: `_void_clocking` geometry, scoreboard `bore_void_off`, QC bore★ | `test_template_bore_centre_matches_loop` — cap6030 estimate within 0.05 mm of (−0.354, −0.044); today 0.96 mm off at ~174° | 0.5–1 d | QC stars and scoreboard flip to truth immediately. ⏎ |
| **G3** | **= slice 12**, `delivered_channel_vs_recess` scoreboard column (plus `delivered_channel_vs_cap_channel`), seeded with the three §7.1 rows | `test_delivered_channel_column_present` (as planned) | 1 d | The before/after instrument for G1. ⏎ |
| **G1** | **Boring-axis fix (closes C2 locally).** Bore the delivered channel at the cap CAD's channel xy (loop truth) carried by the measured pose — not the canonical axis; the fixed r = 1.0 becomes the library channel radius (bounded by G5 until the spec lands). The defect-enforcing assertions in `tests/test_final_product.py:22–31,42–57` are rewritten deliberately in their own commit, per §3.4 slice-19 precedent | `test_channel_follows_library_channel_axis` — un-posed delivered channel within 0.05 mm of the cap loop centre; today 0.36–0.42 mm off on all 3 packages | 1–2 d | The money shot: the delivered channel lands on the physical bore. ⏎flag — the vendor spec (C3) stays the final arbiter of the convention; both modes emittable until it lands |
| **G4** | **QC renders the DELIVERED channel.** Clockview draws the emitted channel and the loop-truth bore; the biased estimator star dies with G2 | `test_clockview_draws_delivered_channel` | 0.5–1 d | The demo artifact itself. ⏎ |
| **G5** | **Pre-export design-rule gate (industry parity).** Block/flag on: channel radius vs library lumen (today the vendor's 4.0 mm-dia lumen is silently erased and re-bored at half diameter), minimum wall thickness around the channel, channel angle vs the library's allowed maximum, post-`_cap_sdf` seal/lumen census (the fine-pitch seal hazard is a recorded gotcha) | `test_export_gate_flags_lumen_mismatch` | 1–2 d | Red flags in the report, 3Shape-style. ⏎ |
| — | **Arbiters (non-local, DEFERRED by client 2026-07-23):** slice 33 vendor-spec ask (seating offset, z-sign, radius, platform convention — resolves §7.1 finding 4) and slice 32 phantom print (`test_phantom_channel_error` — the first ground-truth number the deliverable has ever had) | — | external | — |

**The guarantee, stated:** after G1–G5, the chain is closed locally — library loop truth →
measured pose → bored channel → fleet-measured column → rendered QC — with exactly two open
conventions (vendor platform spec, physical arbitration), both FLAGGED on every package, neither
silent. That is the same guarantee structure the industry itself uses, minus the physical leg we
have deliberately deferred.

---

## 8. Execution queue (2026-07-23) — every unimplemented item, ranked by demo-first ROI

Ranking rule: the client's goal is **demo first — show the existing cases aligned properly, then
expand**. Local-only items rank; anything needing non-local action is marked **[NON-LOCAL]** and
sits at the bottom regardless of importance. Effort = single engineer.

| # | Item (slice) | What it is | Why it matters (measured) | Effort | Non-local? |
|---|---|---|---|---|---|
| 1 | **Bore-centre estimator truth (G2, §7.4)** | Read the cap's bore from its perfect-circle boundary loop instead of a surface centroid | The production estimator points ~174° the wrong way — 0.87–0.96 mm from zero-noise truth — and poisons `_void_clocking`, `bore_void_off`, and the QC bore★ the demo shows | 0.5–1 d | No |
| 2 | **`delivered_channel_vs_recess` column (slice 12 / G3)** | A scoreboard column measuring the emitted prosthesis channel against the scanned recess and the cap channel, per site | The instrument that makes C2 visible fleet-wide; seeded today with 0.60–0.84 mm (vs recess) / 0.36–0.42 mm (vs cap channel) on all 3 real packages; must exist before the fix so the demo shows before/after | 1 d | No |
| 3 | **Boring-axis fix (G1, §7.4)** | Bore the delivered channel where the library says the channel is, carried by the measured pose — behind a flag | Every delivered case misses the cap's channel by 0.36–0.42 mm; without this the entire alignment program never reaches the deliverable (a coaxial cylinder is rotation-invariant) | 1–2 d | No (vendor spec arbitrates the convention later — flagged, not blocked) |
| 4 | **QC delivered-channel render (G4, §7.4)** | Clockview draws the channel the patient actually receives, not an estimator star | The demo's visual proof; today QC renders an instrument that is 0.87–0.96 mm biased and never the deliverable | 0.5–1 d | No |
| 5 | **RNG determinism (slice 2)** | Inject a seeded `Generator` so identical input gives identical spread | Demo numbers currently non-reproducible: 1.237 vs 1.303 mm on re-runs of the same site; blocks trustworthy before/after claims | 1 d | No |
| 6 | **Machine-anchored QA, dual-reported (slices 14–15)** | Extract `qa_metrics`; add rim-agreement anchored to the machine ring alongside the click-anchored copy | Blindness closure: a 1.09 mm-off pose IMPROVED today's click-anchored rim-agreement 0.62→0.88 — the demo's "how good is it" number is currently foolable by its own input | 2–3 d | No |
| 7 | **Segmentation iteration 1 (DR1 targets from slice 13 + slices 7–9)** | Fix the three named autopsy defects — Kasa radius under-read (switch to the stable `island_r`), coverage tissue bias (union-safe mask, slice 7), cap6020 march start — plus the cap7020 chooser fix (slice 8) and fleet shadow telemetry with would-promote (slice 9) | DR1 is NOT cleared: machine loses to clicks on 5/9 sites as probed; pass bar is beats-or-ties ≥7/10; this is timeboxed iteration 1 of the 2 DR1 allows — "cases aligned properly" ultimately rides on it | 1–2 wk (timeboxed) | No |
| 8 | **`seat_site` extraction + `SeatAnchor` (slice 17)** | Extract the ~250-line winner-pass chain into one domain service both pipeline and stability probe call; record anchor provenance | Zero-diff refactor that unblocks the shipped-pose confidence probe (slice 27) and invariant T5; today's spread certifies the base seat, not the shipped pose | 2–3 d | No |
| 9 | **Pre-export design-rule gate (G5, §7.4)** | Block/flag on channel-radius-vs-lumen, wall thickness, angle-vs-library-max, seal census | The delivered channel is HALF the vendor's designed diameter today (vendor 2.00 mm-radius lumen erased, re-bored at 1.0) and nothing flags it; industry products hard-block on exactly these checks | 1–2 d | No |
| 10 | **Library qualification gate (slice 31)** | Per-vendor-drop acceptance: watertight, axis margin, ring/bore offsets, open-loop census, duplicate detection | New exhibit: zimmer-4.5-6020/6030 byte-identical (sha256) to neodent-gm counterparts and nothing noticed; the catalog already burned the project once | 1–2 d | No |
| 11 | **Capture gate at upload (slice 30)** | Refuse inadequate scans in-chair with a concrete rescan message | The only fix for t7-class scans (46% seat-band arc empty, exposure 0.20); independent of everything; fastest client-visible win outside the demo cases | 2–3 d | No |
| 12 | **Small honesty batch (slices 4, 10, 11)** | Surface `candidates_too_close`; detection recall columns + strategy-text correction; `pose_origin` written + `fitness`→coverage rename | Three half-day honesty debts: an invisible high-blocker, an overclaimed detection story (0 candidates on 2/10), and a package key that lies | 1.5 d | No |
| 13 | **Battery split (slice 3)** | Pytest markers: <2 min inner loop, full battery nightly/pre-delivery | 18-minute battery makes test-first performative for every item above | 1 d | No |
| 14 | **Rename batch (slice 16b)** | Grade/Gate split, notch→code_reading, void→recess, `alignment_error_mm` honesty, delete dead `domain/clocking.py` | Language drift broke calibrated behavior five times (reclick saga); zero millimetres moved | 1 d | No |
| 15 | **Phases D–F (slices 18–29)** | Border demotion, gated promotion, recalibration, confidence re-grade, deletion slice | Gated: DR1 evidence (item 7) and the deferred sign-off must land first; promotion without them is the pre-mortem's named failure | weeks | Sign-off is non-local |
| — | **[NON-LOCAL — DEFERRED by client 2026-07-23]** git init + remote + tags (slice 1); DR1–DR5 sign-off meeting (§3.8); phantom print order (slice 32) — the only physical arbiter for §7's flagged conventions; vendor-spec + ground-truth client asks (slice 33, §5.4); FLE study scheduling (§5.5); CI on linux/3.11 (§5.6) | Deferred, not cancelled. The phantom and the vendor spec are the two arbiters §7.4's guarantee explicitly leaves open; every week of deferral extends the flagged-convention window | — | — | Yes |

Reading of the queue: **items 1–4 are one engineer-week and constitute the §7 guarantee's local
core plus the demo's money shot** (delivered channel visibly landing on the physical bore, with a
fleet column proving it on every case). Items 5–6 make the demo's numbers reproducible and
unfoolable. Item 7 is the big rock for "aligned properly" and carries its own DR1 timebox. Items
8–14 widen honestly. Item 15 stays gated exactly as §3 planned it.

---

## Appendix — mapping from the superseded plan

| Prior stage | Where it lives now |
|---|---|
| Stage 0 (snapshot + surfacing) | Slices 1, 4 |
| Pre-work a/b/c (autopsy, border spike, RNG) | Slices 13, 18, 2 |
| Stage 1 (island shadow) | Slices 5–9 (walking skeleton + widening) |
| Stage 2 (metric honesty) | Slices 14–16b + 11 |
| Stage 3 (demotion, re-scoped) | Slices 18–19 (always-snap moved to 23) |
| Stage 4 (machine anchoring, one L stage) | Slices 20–25, unbundled per bounded context, each independently revertible |
| Stage 5 (recalibration) | Slice 26 + DR2 |
| Stage 6 (confidence re-grade) | Slices 27–29 (probe cut to one family; requires slice 17) |
| Stage 7 (phantom + FLE) | Slice 32, extended with the construction leg |
| *(no prior coverage)* | Slices 10, 12, 30, 31, 33 — the FIND and CONSTRUCT links, capture gate, library gate |
