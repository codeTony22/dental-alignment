# PLAN — Marks as Locators: the algorithm finds centre, borders, depth, rotation itself

*Synthesis of the 2026-07-23 session's four measured investigations (mark-dependence audit,
island-segmentation probe, residual autopsy, confidence-path analysis), built on the settled
record (`docs/architecture-current.md`, `docs/research/alignment-confidence-roadmap.md`,
`docs/engagement/phase2a-completion-report.md` §6–7). Client product decision (2026-07-21):
the doctor's marks are approximate locators only; the algorithm must find the true centre,
the cap's actual borders ("the island"), the depth, and the rotation itself, and deliver
near-perfect alignment with HIGH confidence. Every number below is measured, with the
instrument named. Fleet baseline: snapshot `notchclock-v1`, battery 423 green.*

---

## 1. WHY ALIGNMENTS ARE NOT PERFECT — the measured decomposition

The residual autopsy (18 production runs: every site at curated marks AND at "ideal marks"
moved onto the scan's own converged rim circle; `autopsy-residuals.md`) decomposes today's
imperfection into five causes. Three are fixable by this plan; two are physics floors that
need honest flags, not software.

### 1a. Fixable by this plan

**Cause 1 — ROI contamination ("the island" not found), the dominant fleet-wide cause.**
The click-anchored ball crop feeds the seat a patch that is median **54–60% tooth/gingiva**
(31–71% per site, island probe re-measure), points the cap can never explain. Seat bands are
**2–94% tissue**. Measured payoffs of a clean anchor (autopsy ideal-mark runs): t20 rim
1.00→0.51 mm and screw-hole landing (bore 1.07→0.08 mm); **t7 rotation −150.5°→−3.6°**
(coded evidence *appears* once the anchor is clean) and rim_off 1.24→0.59; cap7030 rim
−0.26 mm; t4 unlocks the 0.3–0.5 mm centring class *and* a computable confidence grade
(bootstrap currently returns None); t13 the ~1.5°/170 µm class. This is roadmap item #9 and
is exactly the client's product decision.

**Cause 2 — click positions are structurally load-bearing (measurements, not locators).**
The audit found 13 consumption points in `auto_flow.py` where the click *position* sets the
answer, not just the search region. Measured sensitivity (rigid whole-gesture offsets):
a 0.3 mm click error moves the shipped pose **0.16–0.71 mm**; 0.6 mm moves it up to
**1.09 mm / 16.6° axis** (cap6030 +0.6y: axis 16.6°, clock evidence LOST; t13 +0.6x: pose
1.09 mm with gain >1 — the pose moves MORE than the click). Mechanism: the rim-band annulus
|d−rim_r|<0.5 and the ROI crop are anchored at the clicked centre+radius, so a shifted
gesture swaps rim points for flank points (a 0.5 mm cliff). Under the measured centre-click
FLE (p50/p68/p90 = 0.32/0.46/0.61 mm), this manufactured noise is what the confidence
bootstrap measures — it is the dominant reason the fleet grades 0/10 high.

**Cause 3 — instrument dishonesty: QA anchored to the marks, and a convicted-biased metric.**
(a) `rim_agreement` (#14) and the scoreboard's `rim_off_centre` are computed in a band
anchored at the *clicked* centre/radius — on t13 at +0.6x the pose was 1.09 mm off while
rim_agreement *improved* (0.62→0.88 band): QA is structurally blind to click-induced error.
(b) `bore_void_off` 0.58–1.35 mm + clock consistency 39–107° on the 5 code-verified sites is
the phantom-convicted **recess-azimuth bias** (§7.1), not pose error — the gate over-warns
off a biased instrument on sites whose rotation is code-verified to ≤3.1°.

### 1b. Partially fixable (evidence reach)

**Cause 4 — clock-evidence occlusion.** Rotation is SOLVED where evidence exists (8/10 sites
code-verified ≤3.1°). The two failures are occlusion: cap7030 half-occluded ring (recess-only,
23.8° unconfirmed — the e8 gate refuses honestly), t7 no evidence (−150.5° unverified).
t7's failure is subsumed by Cause 1 (clean anchor → codes appear, −3.6°). cap7030's ring
stays half-occluded — the island cleanup may extend informative rows, but no promise.

### 1c. Physics floors — flag honestly, do not "fix"

- **Submergence.** Geometry-floor triple (exposure · ring-visibility · band-tissue) bounds
  rim residuals at ~0.8–1.5 on t4/t13/cap7030/t7. t13's *correct* seat reads rim 1.47
  because the 25%-visible ring meets the FLANK. On tissue-dominated sites (t4, t13) a
  "perfect click" does not exist — the scan-converged circle is itself contamination-biased.
  Height twins remain collapsed only by the doctor's declaration (settled, roadmap §2).
- **Scan holes.** t7: 46% of the seat-band arc is empty scan + worst exposure (0.20) — a
  genuinely sick seat that grades honestly low. Workflow (rescan), not software.
- **Recess-azimuth bias magnitude.** Only the printed phantom (designed clock angles,
  tooling shipped) can calibrate it; retuning blind would be guessing (§6.6 record).

**Fleet ranking if one cause is fixed perfectly (autopsy):** 1. island/ROI cleanup (the
medium→high lever, de-inflates every rim read, tightens every bootstrap spread); 2. clock
evidence reach (largest degree moves; t7's subsumed by #1); 3. metric honesty (zero mm, stops
5 verified sites reading "attention"); 4. perfect clicks — **subsumed by #1**; 5. submergence
— workflow; 6. scan holes — t7 only.

---

## 2. THE TARGET ARCHITECTURE — marks as locators

### 2a. The machine measurement that replaces the marks

The island probe (`island_probe.py`, 9/10 sites; the t7 case run produced no result file —
re-run in Stage 1) validated the core capability on real data:

- **Zero-click detection already works**: the existing PROPOSE stage
  (`adapters/cap_detection.find_cap_sites`: rim-slab core/ring evidence) lands
  0.002–0.062 mm from the curated click on 6/9 sites (0.22 t20, 0.51 t3-276).
- **Degraded-seed island segmentation** (seed = click + 0.8 mm ≈ 2.6× the p90 FLE):
  evidence-driven centre refine + closed-ring edge scan + 48-bin radial island march
  recovers the rim centre to **median 0.26 mm of the shipped pose** (≤0.13 on 4 sites,
  0.027 on cap6030). Failures to fix before promotion: cap7020 1.54 mm (strict/plane
  chooser picked wrong), t13 0.67 / t4 0.46 (the known tissue-biased-circle sites).
- **Prototype limits (promotion gates needed):** the crude island mask still leaves median
  48% in-island contamination, and **over-crops submerged caps** (cap points lost 53–83% on
  cap6020/7020/7030) — exactly the roadmap-#9 warned failure ("don't over-crop the
  constraining rim wall"). Production segmentation must be union-safe: never remove points
  the posed template explains; a cap-coverage guard is a hard promotion gate.
- Probe caveat, carried honestly: on the 8 well-behaved sites "d_ship" measures agreement
  with a scan-measured centre whose band the click selected — not independent truth. The
  phantom (Stage 7) is the independent arbiter.

### 2b. Exactly which consumption points change (audit numbering)

| Audit # | Today (measurement) | Target (locator) |
|---|---|---|
| **#9** `_rim_seat` band anchoring | annulus \|d−rim_r\|<0.5 + arc bins around *clicked* centre/radius → axis is a click measurement (the 16.6° cliff) | band = the **machine-detected ring** (island edge scan); click only selects which island |
| **#8** `_pinned_rim_seat` | clicked border circle PINS centre/axis/depth 1:1, fitness=1.0, depth polish skipped | clicked circle demoted to **initializer**; free machine-banded seat always runs; depth polish always eligible |
| **#7** `_cap_patch_roi` | ball crop at clicked centre + human_rim_r → 54% contamination | crop at machine centre; island mask (union-safe) removes below-ring tissue |
| **#10–13** depth/best-fit/centering/clock guard anchors + centering target | accept gates + `_center_on_rim` target anchored at clicks; border path drags pose TO the clicked centre | re-anchored to the **detected ring** |
| **#14** `rim_agreement` + scoreboard `rim_off_centre` | mark-anchored → blind to click error (t13 proof) | machine-ring-anchored (both reported during transition) |
| **#3** pair path "xy is ground truth" | centre click skips the snap when a rim pair exists | **always snap**; the pair contributes a radius prior only |
| **#4** `human_rim_r` | drives band radius, arc relaxation, crop, guards | detector-measured radius primary; human radius a prior/cross-check |

**Keep as-is** (already locator-classed): z re-read from scan, bare-click mean-shift, #5
(seed = site.center), #6 `measure_rim_diameter`, pure reporting (#15–18).

### 2c. What the doctor's clicks still do

1. **Locate**: seed the ROI and select the correct island on multi-implant arches
   (nearest-candidate disambiguation — the click means "this cap").
2. **Prior**: radius hint for band initialization; z-neighborhood.
3. **Cross-check advisory**: machine-found circle vs clicked circle disagreement shipped as
   a per-site advisory (like `border_disagreement` today) — a large gap flags either a bad
   gesture or a machine failure, routed to review, never load-bearing on the pose.
4. **Declaration stays required** (settled — the one input that collapses the height twin).

### 2d. Calibration consequence — stated explicitly

Changing seat anchoring (#8/#9) **re-opens two burned-in calibrations**:

- **The identification score** (seat + 2.0×t2p, cut −0.4) was calibrated WITH the current
  click-anchored seat paths. The machine band feeds all candidates symmetrically (ranking
  still never sees winner-only refinements — that structural contract is untouched), but
  score *ranges* shift → the cut must be re-measured (Stage 5) before the new anchoring
  ships. Instrument: the recalibration harness + labeled arches (declared-ID 4/4 must hold).
- **The confidence grade bars** are fleet-distribution-calibrated; the distribution changes
  → re-pin from the new fleet (Stage 6), then truth-validate with the phantom.
- **The click-noise bootstrap becomes vacuous by construction** once marks are locators
  (locator-only simulation: cap6030 pos spread 1.237→0.099 mm, axis 18.4°→0.20°) — it must
  be REPLACED by a machine-side probe, or "high" silently rests on rim_agr+topf alone.

**How re-pinning works:** every stage lands against `tools/fleet_scoreboard.py --save/
--baseline` diffs (pre-plan snapshot + `notchclock-v1`), the 423-test battery with per-site
contract ceilings updated *deliberately* (never silently), and the phantom/FLE instruments
for truth. Corrections stay at the UI source; determinism preserved (no ambient RNG).

---

## 3. STAGED IMPLEMENTATION PLAN — small, reversible, shadow-first

| Stage | What | Effort | Pose change? |
|---|---|---|---|
| 0 | Snapshot + surface hidden gate signals | S | no |
| 1 | Island segmentation as SHADOW measurement | M | no |
| 2 | Metric honesty (machine-anchored QA + clock-bias labeling) | S | no |
| 3 | Demote the pinned path + pair "ground truth" | M | yes (border-gesture sites) |
| 4 | Machine band + clean ROI behind gates | L | yes (fleet-wide) |
| 5 | Re-calibration of ID score + contract ceilings | M | no |
| 6 | Confidence re-grade (machine-side probe, rotation in grade) | M | no |
| 7 | Phantom + FLE validation (external) | L | no |

**Stage 0 — Baseline snapshot + surfacing (S).**
`fleet_scoreboard.py --save locators-pre` and verify it reproduces `notchclock-v1` exactly;
log `candidates_too_close` per site (today an invisible high-blocker, auto_flow.py:1600).
*Impact:* none (instrumentation). *Risk:* none. *Validation:* diff vs notchclock-v1 = all
unchanged; battery green.

**Stage 1 — Island segmentation as a SHADOW measurement (M).**
Port `segment_island` (evidence-centre refine, closed-ring edge scan, 48-bin radial march,
strict/plane dual-run) into an adapter; run per site; report machine centre/radius/boundary,
contamination stats, and machine-vs-click distance NEXT to the shipped numbers (report,
scoreboard columns, run history). Fix the two probe defects first: (a) union-safe masking —
never drop template-explained points (cap loss 53–83% on the three submerged caps is a
disqualifier); (b) the cap7020 1.54 mm chooser failure; (c) re-run t7. *Impact:* zero pose
movement; establishes the fleet distribution of machine-vs-click disagreement — the data
that sets Stage 4's gates. *Risk:* runtime, determinism — guard: RNG-stream-neutral like e8;
scoreboard diff must read all-unchanged on pose metrics. *Validation:* scoreboard diff +
battery + shadow columns populated 10/10.

**Stage 2 — Metric honesty (S).**
Compute `rim_agreement` and `rim_off_centre` against the machine ring (shadow: report both
anchorings during transition); stop routing "attention" off `bore_void_off`/consistency when
rotation is codes-verified with confirm re-read ≤12° — relabel as "instrument disagreement
(recess-azimuth bias, phantom will arbitrate)". *Impact:* zero mm; the 5 code-verified sites
stop over-warning; QA stops moving with the clicks (t13's blindness closes). *Risk:* masking
a genuine defect — guard: relabel ONLY when clock_evidence ∈ {codes, codes+recess} AND the
confirm re-read passed; recess-only/none sites keep the warning. *Validation:* scoreboard
gate-level diff reviewed site-by-site; battery contracts for the five bore-on-void sites
updated deliberately.

**Stage 3 — Demote the pinned path (M).**
#8: clicked border circle becomes initializer (free seat + depth polish always run; delete
the fitness=1.0 fiction); #3: always mean-shift-snap the centre click, pair = radius prior
only. *Impact prediction:* the synthetic-border 1:1 sensitivity on 276794487/t3
(+0.6y → 0.78 mm/7.6°) collapses toward the free-path numbers; no movement on sites without
border gestures. *Risk:* the pinned path was a doctor-trust feature — keep the clicked
circle as the advisory cross-check (2c.3) so the trust story survives; pair-channel FLE was
never measured (all replays) — demotion removes that caveat rather than inheriting it.
*Guard:* rim-band certification gates (anchored since the §6.6 review) + scoreboard diff;
targeted pytest on the pinned-path fixtures. *Validation:* single-case runs on the
border-gesture cases; battery green.

**Stage 4 — Machine band anchoring + clean ROI, behind gates (L).**
#9/#7/#10–13: seat band annulus and arc bins from the machine ring; ROI crop at machine
centre with union-safe island mask; guard anchors and `_center_on_rim` target re-anchored to
the detected ring. **Gated promotion:** machine anchor used only when the island converged
(bins-hit ≥ threshold, cap-coverage ≥ threshold, machine-vs-click distance ≤ sanity bound
from Stage 1's distribution); otherwise fall back to today's click-anchored path + flag
`island_unconverged`. *Impact prediction (measured basis):* t20 rim 1.00→~0.5 + bore →~0.1
(autopsy ideal-mark run); t7 codes evidence appears, rotation −150.5°→single digits, rim_off
−0.65 (ditto); cap7030 rim −0.26; t4 grades at last; t13 partial (flank floor remains);
clean sites move little in pose but their residual gates de-inflate (bands stop reading
2–94% tissue). Axis sensitivity to gesture error (the 16.6° cliff) disappears by
construction. *Risk:* over-crop starving the seat (probe measured it) — guard: cap-coverage
promotion gate + place-and-recover harness (roadmap #9's prescribed validator); t4/t13-class
sites where the machine circle is itself tissue-biased — guard: the fallback + flag, and the
stability-refusal/ride-off bounds stay untouched. *Validation:* scoreboard diff vs Stage-0
per site (improved/regressed/unchanged), full battery, single-case runs on all 10.

**Stage 5 — Re-calibration (M).** Mandatory once Stage 4 lands: re-measure the
identification score distribution on the new seat paths, re-pin the cut; declared-ID must
stay 4/4 on the labeled arches; update per-site battery ceilings deliberately. *Guard:* the
scoreboard snapshot pair (pre/post) is the reviewable evidence; no threshold moves without a
measured distribution. *Validation:* battery green at the new ceilings; ID contract tests.

**Stage 6 — Confidence re-grade (M).**
Replace the click-noise bootstrap with a **machine-side stability probe** (ROI jitter,
band-inlier resampling, surface-noise perturbation — the spread that remains once marks are
locators); include winner passes in the probed chain (today's spread certifies the base
seat, not the shipped pose); grade coverage 10/10 (t4); **rotation enters the grade**: high
REQUIRES clock_evidence ∈ {codes, codes+recess} (recess-only or none caps at medium);
submergence-aware rim scoring (visible-band, so t13's flank floor stops masquerading as seat
error); surface `candidates_too_close` per site. *Impact:* grades become meaningful under
the new architecture. *Risk:* a vacuous probe that grades everything high — guard: the probe
must discriminate the known-sick sites (t7 low, cap7030/t13 sub-high) or it does not ship.
*Validation:* fleet grade distribution reviewed against §1's floors.

**Stage 7 — Physical validation (external, L).**
Print + scan the regenerated `phantom-plate.stl` (designed poses AND designed clock angles);
run `tools/evaluate_phantom.py`: (a) truth-pins the grade→platform-error mapping ("high
means ≤X mm with probability Y"), (b) arbitrates the codes-vs-recess instrument conflict and
calibrates the recess-azimuth bias, (c) checks the bore-mouth estimator's documented
cut-sensitivity (neodent 4230/4030), (d) confirms "p90 ≈ 2× actual". The centre-click FLE
study (`tools/fle_study.py`, protocol handed to the lab) closes the last input-noise caveat.

---

## 4. WHAT "HIGH CONFIDENCE" WILL HONESTLY MEAN

**Today:** 0/10 high, 8 medium, 1 low (t7), 1 ungraded (t4). Every graded site fails the
position-spread bar; 7/9 fail axis — and the locator-only simulation proves this is mostly
*manufactured* click-noise propagating through the marks' structural role (cap6030
1.237→0.099 mm, 12.5×; t3 0.963→0.139 mm, 7×; both then pass every high bar).

**After the plan, "high" means all of:**
1. Seat anchored to a converged machine-detected island (not the gesture) — or the site is
   flagged `island_unconverged` and capped;
2. Machine-side stability spread (Stage 6 probe, shipped-pose chain) under bars whose
   mm-meaning is phantom-pinned (Stage 7), not fleet-relative;
3. Rotation code-verified (confirm re-read ≤12°), residual within the re-pinned bar —
   recess-only/none never grades high;
4. Visible-band rim agreement within bar, with submergence flagged separately (a physics
   floor is a flag, not a residual);
5. No `candidates_too_close` (submerged height-ties correctly stay sub-high; declaration
   present);
6. Grade computed on 10/10 sites.

**Instruments that re-pin the thresholds:** fleet scoreboard (relative regression truth,
every stage), FLE study (input-noise scale for the remaining advisory channel — border-click
σ≈0.3 mm already truth-calibrated, centre-click study with the lab), printed phantom (the
only independent pose + clock truth; sets the auto-pass line, roadmap #7).

**Expected fleet distribution (prediction, measured basis, to be verified not asserted):**
~5–7 high (t3-276, t29-295, cap6030, cap6020, cap7020 from the spread collapse + de-inflated
bands; t20 joins on the measured rim 1.00→0.5 cleanup), 2–4 medium with honest named floors
(t13 flank submergence; cap7030 half-occluded ring at medium via rule 3; t4 graded, likely
medium), t7 low until rescanned (real scan hole, genuinely sick seat). If the phantom moves
the bars, the distribution follows the truth — the claim is honesty, not a quota.

---

## 5. WHAT WE EXPLICITLY DO NOT DO

- **Do not re-plan rotation.** Coded-feature clocking (e8) is shipped and code-verified
  ≤3.1° on 8/10; the two exceptions are evidence-occlusion handled by Stage 4 (t7) and an
  honest refusal (cap7030). No new rotation algorithm.
- **Failed routes, not to be re-proposed:** recess-authoritative clocking (rotated away from
  codes on 5/7, superseded §6.6a); 1-D azimuthal profile extractors (≤3/7); fixed-3D-ring-
  point clocking (0.20 mm leak); interleaved centre/clock iteration (+0.51 mm rim cost);
  global feature solvers (TEASER/FGR/4PCS — structurally inapplicable to smooth revolute
  caps); rebuilding the inner solver (already ~5 µm on clean input); backend self-correction
  of corrupted click pairs (5 failed attempts — corrections at the UI source, always);
  a separate platform-depth intake (redundant with the declaration); Fitzpatrick TRE as the
  grade driver (reporting only).
- **No operator hole-marking or code-clicking.** The bore interior is not in the scan; the
  machine reads the recess and the coded band better than a click would. Note the patent
  landscape recorded in §7.1 (Nobel's asymmetric top-face boundary matching; ZimVie's coded-abutment workflow
  operator-clicked codes): we stay on our own shipped e8 depth-image correlation and do not
  build an operator code-marking workflow.
- **Do not "fix" physics floors in software:** height twins under submergence (declaration
  stays the required collapse); t13-class flank floors (visible-band scoring + flag);
  t7's scan hole (rescan workflow); do not retune the recess-azimuth bias or the bore-mouth
  estimator blind — the phantom is the instrument (§6.6 record).
- **Do not remove the doctor's marks from the product.** They remain the locator, the island
  selector on multi-implant arches, and the human cross-check advisory — "approximate
  locators only" is a demotion of authority, not a deletion of the gesture.
- **Do not ship Stage 4 without Stage 5**, and do not keep the click-noise bootstrap as the
  grade once marks are locators (it becomes vacuous by construction — the grade would be
  resting on rim_agr + top-face alone while claiming more).

---

## ADVERSARIAL VERIFICATION CORRECTIONS (2026-07-23, fold into execution)

The plan above was independently attacked; stages 0/1/2/5/6/7 CONFIRMED, two findings
require amendment before execution:

1. **Stage 3 re-scoped.** "Always mean-shift-snap the centre click" applies to centre+rim
   PAIR gestures = ALL 10 fleet sites, not just border-gesture sites — a fleet-wide seed
   change two stages before recalibration. AMENDMENT: the always-snap moves into Stage 4's
   gated promotion; Stage 3 keeps only the border-circle demotion (initializer + advisory).
   And EXPLICITLY: splitting the centre/rim pair supersedes the reclick-pair-integrity
   contract BY CLIENT DECISION (2026-07-21 "marks are approximate locators") — this is a
   product-level supersession, not backend self-correction attempt #6.
2. **Stage 4 impact honesty (oracle vs machine).** The cited per-site payoffs
   (t20 rim 1.00→0.51 + bore→0.08; t7 codes appear at −3.6°) were measured with an ORACLE
   anchor (scan-converged circle seeded from the curated click). The machine segmentation
   as probed today delivers: median 0.26mm from ship, click-closer on 5/9, cap7020 1.54mm
   chooser failure, and t7 islanding FAILS outright (machine 2.04mm off, detector None,
   cap coverage 0.15 → the cap-coverage gate fires the fallback; t7 keeps today's behavior
   until islanding is fixed for it). Measured counterexample to carry: t20's oracle run
   LOST coded clock evidence (−2.1°→−23.6°, codes→recess) — anchor shifts can lose codes,
   so Stage 4 must re-verify clock evidence survival per site, and t20/cap7020's predicted
   "high" memberships are conditional.
3. **Pre-work (cheap, before Stage 1 code):** (a) the MACHINE-MARKS AUTOPSY — re-run the
   18-run autopsy harness with the pair overridden to the machine island circle (where
   converged): the direct measurement of Stage 4's real impact; (b) free-path
   synthetic-border run to ground Stage 3's prediction; (c) pin the ambient-RNG draw in
   the seat helpers (sample_surface) — the Stage 6 probe is not stream-stable without it
   (measured: re-runs of the locator-only sim differ, 1.237 vs 1.303).
4. Stage 5 budget note: the settled record says no clean win exists in the LINEAR score
   family under click-noise — a machine-banded seat may reopen the score family, not just
   the cut.
5. Stage 7 carries: any phantom re-voxelization must use the sealed `_cap_sdf` path (the
   fine-pitch seal hazard), and the recess-arbitration column inherits the
   recess-shallower-than-channel caveat.
