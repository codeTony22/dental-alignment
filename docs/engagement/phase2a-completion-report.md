# Phase 2A Completion Report — Automated Healing-Cap Alignment

**Date:** 2026-07-18
**Audience:** lab ownership and technical lead
**Scope:** end-of-phase record of what was found, fixed, and measured on the alignment pipeline this phase, what remains physically out of reach of any software, and what the next phase should buy.

Every number in this report was measured on the 10 real client sites (including the 4 doctor-labeled ground-truth arches), on the current code, with the full automated test batteries green (worker: 342 tests, web: 151). Where a capability is advisory rather than validated, it is labeled as such.

---

## 1. Executive summary

Alignment is now in the strongest, most honestly-characterized state it has been in. This week we traced the two reported field symptoms — "sideways caps" and seats that always landed slightly off the rim — to two defects in **our own loading and centering code**, not in the manufacturer's library files and not in the doctors' scans. Both are fixed and guarded by tests. After the fixes, **every one of the 10 real sites rim-seats correctly**, all full-rim sites measure **0.00 mm off-centre**, and top-face seating reads **0.13–0.60 mm across the entire fleet**. Variant identification with the doctor's declared variant (now a required intake field) is **4 of 4 exact** on the labeled arches — including both height twins, which the scan alone physically cannot separate. Every run now also carries a graded confidence (high / medium / low) from a pose-stability probe; it grades how much review a case deserves, and it never auto-manufactures. The recommended next phase converts those grades into calibrated millimetres and establishes independent physical ground truth — the two things standing between "graded review effort" and a validated auto-pass line.

---

## 2. What we found and fixed

### 2.1 Library canonicalization — the "sideways cap" root cause

The manufacturer's cap files were saved correctly all along. The defect was in **our loader**: its PCA-based axis detection re-derived each template's axis from its shape and tilted every template off its true saved axis — the 6030 caps fully sideways at **88°**, 5030 at **43°**, 7030 at **27°**, and the rest **4–15°** off. This single defect was behind both the "sideways cap" reports from operators and a phantom "sloped-cap outlier" site that had been absorbing investigation time.

**Fixed:** the loader now trusts the verified saved axis in the file. A guard test audits every current — and any future — library file, so a tilted template can never silently enter the catalog again.

### 2.2 Systematic off-centre seating

Templates were being centred on their **mesh centroid**, which for these parts sits 0.2–0.58 mm off the true rotational axis. The consequence was systematic: every seat landed **0.29–0.51 mm off the scanned rim**, on every site, regardless of operator skill.

**Fixed** with a winner-only re-centering step (applied to the selected variant only, so the calibrated candidate-ranking contract is untouched). All full-rim sites now measure **0.00 mm off-centre**.

### 2.3 Depth on tall caps

Tall 30-collar caps rode up to **~2 mm high**: the depth objective is blind on straight vertical walls, so nothing pulled the template down its own axis. **Fixed** with a gated, winner-only depth polish, plus a new top-face depth bound added to the test guards so a floating seat now fails the battery rather than shipping.

### 2.4 Fleet state after the fixes

Measured on all 10 real sites with the curated marks:

- **Every site rim-seated.**
- **All 6 declared/labeled variants matched** — including both height twins on the ground-truth arches.
- **Top-face seating 0.13–0.60 mm everywhere.**

### 2.5 Identification vs. declaration — why the declared variant is now required

Measured on the 4 client-labeled arches:

| Input | Exact variant ID | Notes |
|---|---|---|
| Scan alone (auto-ID, no declaration) | **1 / 4** | Can flip between diameter classes |
| Scan + doctor's declared variant | **4 / 4** | Pose fully recoverable on every arch |

The product therefore now **requires the doctor's declared variant at intake**. The rim measurement is retained as an independent cross-check on the declaration — the software still guards against a gross mis-declaration; it just no longer guesses what the scan cannot tell it (see §3).

### 2.6 Confidence grading (new — advisory)

Every site now carries a graded confidence — **high / medium / low** — from a pose-stability probe: the seat is re-computed 8× under simulated click error, and the spread of the resulting poses is graded together with the fit residuals. A seat that lands in the same place no matter how the clicks wobble earns high confidence; one that scatters is flagged for closer review.

Two honesty notes: this grade **directs review effort — it never auto-manufactures**; and the thresholds are **preliminary** until a short operator repeat-click calibration study pins the real click-error scale (§4).

### 2.7 Operator-experience fixes shipped

- Anatomical **Front / Left / Right / Top** camera presets — scans open facing the front of the mouth.
- Clean input-scan restore whenever marks are redone.
- Run-results fresh-start on re-marking (no stale results lingering next to new marks).
- Results-table layout fix.
- Run-report additions: border-click disagreement, top-face seat, and the confidence grade now appear on every report.

---

## 3. Physics limits, stated plainly

Two limits are properties of the physical capture, not of our software. No algorithm, marking protocol, or re-scan crosses them, and the product is designed around them rather than pretending otherwise.

**(a) A submerged cap's collar height is not recoverable from a surface scan.** A submerged 30-collar cap presents the same visible shell as its 20-collar twin — the distinguishing ~2 mm of collar sits under the gingiva, occluded by tissue. This is exactly why the doctor's declared variant is now a required field: it supplies the one piece of information the scan physically cannot, and it is why 4/4 identification is achievable *with* the declaration and not without it.

**(b) The scan does not resolve the screw channel.** Measured directly: the bore reads in the intraoral scan as a smooth convex dome — there is no hole in the scan to mark. Asking operators to mark the screw hole therefore adds nothing; the visible rim plus the coded top face already carry all the pose information the scan contains.

---

## 4. What phase completion means, and the recommended next phase

Phase completion means: the known systematic errors in the alignment chain are found, fixed, and fenced with tests; the fleet numbers above are the measured, reproducible state of the product on real client data; and the remaining uncertainty is *quantified and displayed* per site rather than hidden. What it does not yet mean is a validated auto-pass: the confidence grades are advisory until they are calibrated against real operator behaviour and independent ground truth.

The recommended next phase, in order:

1. **Operator FLE calibration study** — about 30 minutes of structured repeat-clicking by the lab's own operators on existing arches. This converts the confidence grades from relative bands into calibrated millimetres.
2. **Independent physical ground truth** — a printed phantom with a cap at a known, measured pose. This is what unlocks a *validated* auto-pass line ("accurate to X mm with probability Y"), decoupled from the pipeline's own residuals.
3. **Production hardening** — the AWS infrastructure plan already exists (`docs/engagement/phase2-aws-infrastructure-plan.md`); once 1–2 set the pass line, the pipeline is ready to be operationalized behind it.

---

## 5. Appendix — supporting documents

- **Benchmark results (regenerated this phase, on the corrected upright templates):** `docs/research/alignment-benchmark-results.md` — supersedes the pre-fix run, whose baseline measured tilted templates.
- **Algorithm survey (why the seating approach is what it is):** `docs/research/alignment-algorithm-survey.md`
- **Confidence roadmap (the ranked path to a validated auto-pass):** `docs/research/alignment-confidence-roadmap.md`
- **Infrastructure plan for production hardening:** `docs/engagement/phase2-aws-infrastructure-plan.md`

---

## 6. Addendum (2026-07-19) — Screw-channel clocking + fleet scoreboard

*Appended after the 2026-07-18 report above; the sections above are left as the record of that date.*

### 6.1 The client's report

On the day of the report above (client report, 2026-07-18), the client reported two symptoms on the delivered overlays: **the screw channels are not rotated to the scanned screw recess**, and **the centres are never quite centred**. Both are real, both were measured, and both trace to the same geometric fact.

### 6.2 Root cause — two off-axis features that couple

Measured across the whole template catalog:

- the **screw bore centre sits 0.43–0.76 mm off the canonical axis**, and
- the **rim-ring centre sits 0.2–0.58 mm off the canonical axis**.

Because *both* features are off-axis, clocking and centering are coupled **under axis-rotation kinematics**: rotating the cap about its canonical axis to put the bore on the scanned recess **swings the rim centre off the scanned rim**, and translating the cap back onto the rim **moves the bore off the recess**. Neither fix applied in a strict order converges (measured: an interleave prototype bought bore improvements at up to +0.51 mm rim off-centre). On the shipped fleet the posed bore sat **0.31–1.78 mm** from the scanned recess void, with the true clocking optimum up to ~150° away from what the coded-face sweep chose (that sweep is nearly flat on these caps, 0.04–0.07 mm of variation — no discrimination).

One honest correction to §3(b) above: the scanner still cannot see the bore's *interior* (there is still no hole for an operator to mark, and the "don't ask operators to mark holes" conclusion stands), but the scan **does** record the recess as a deep, compact *depression* — measured fleet-wide at 547–8,356 points and 0.76–3.5 mm deep. That depression is rich enough signal to clock against automatically. And because the bore is off-axis, clocking is **not** inert for the deliverable: it decides where the screw channel lands.

### 6.3 The fix — recess-authoritative RING-FIXED clocking

Both passes are **winner-only** (ranking is long decided when they run — the calibrated identification contract is untouched by construction, the same structural safety as every other refinement stage):

- **`_center_on_rim`** slides the pose so the posed rim ring lands on the scanned rim circle — discretionary shift capped at 0.8 mm, monotonic band-agreement + top-face gates (a noisy partial-rim target cannot drag the seat).
- **`_void_clocking`** then rotates the part **about the vertical axis through the posed rim-ring centre** (a rotation about the part's own axis composed with the exact compensating slide) so the posed bore centre lands on the scanned recess void. The invariant is the **measured** rim centre — the Kasa fit of the posed rim band's occlusal projection, the very quantity the centering pass drives and every rim guard measures — re-measured **per candidate angle** with the exact compensating slide folded into the sweep objective, so the pass cannot undo the centering and §6.2's coupling dissolves without iteration. (Holding a fixed 3D ring point instead still leaked 0.20 mm, measured: the rim band is a radius-selected *strip* whose z-asymmetric cutouts drift its projected Kasa centre as the part clocks under a tilted seat.) The lever is the bore's offset *from the ring centre*, |bore−ring| = **0.77–1.12 mm** across the catalog — larger than the axis-relative 0.43–0.76 mm (the two offsets point roughly opposite ways): strictly more reach.
- Void detection is anchored at the deepest points, deepest-first, with a reachability gate: a candidate cluster is accepted only within ±0.8 mm of the circle the CAD says the bore can sweep ("the screw hole can only be where the screw hole can be" — this is what stops the coded cutout's D-flat from hijacking the search, as it did on the labeled 7030). The recess is authoritative when its signal is strong; the coded-face metric survives only as a catastrophe guard (the rotation may not worsen top-face agreement by more than 0.4 mm mean).
- **Ride-off bound:** both passes refuse any move that pushes top-face **p90 beyond 1.5 mm** unless it improves it — the same measure the certification guards enforce. (Measured why: on zimmer-t7 a rim-perfect slide pushed p90 1.4 → 1.72; gating on the *mean* had let a ride-off pose sneak under the bar.)
- **Stability refusal:** the measured compensation must agree with the swing the canonical ring geometry predicts for the chosen angle (excess ≤ 0.35 mm). On a tilted partial-band site the ring estimate can go unstable and "compensate" the part >1.4 mm sideways (measured on t13 re-click gestures, riding the rim band past its certification bar) — such a site cannot support ring-fixed clocking, and the pass refuses, keeping the face-sweep pose. A rim-band bound (≥1.6 mm and worsening → refuse) backs this up as defense in depth.
- **Honest limit:** clocking is a rotation — it cannot fix a void whose *radial* position is off the bore's swing circle. On 297589851-t20 the void sits ~0.4 mm from the ring centre against a ~0.99 mm swing radius (kinematic floor ~0.59 mm); the site ships flagged **attention** (undeclared variant, noisy rim). The contract everywhere is *no silent misplacement*: the bore lands on the recess, or the site is flagged.

### 6.4 New regression instrument — the fleet scoreboard

The client asked for exactly this: *"so we know what changes improve or don't improve the model."* `apps/worker/tools/fleet_scoreboard.py` runs **every real case through the production pipeline** and scores each site on rim_agreement, top_face_p90, rim_off_centre, **bore_void_off** (the metric §6.1's defect lives in), id_match, confidence grade, and gate level. `--save NAME` stores a deterministic snapshot in `reports/scoreboard/`; `--baseline NAME` prints a per-site **improved / regressed / unchanged** diff against a stored snapshot. Every future algorithm change gets judged by this diff, not by anecdote.

Per-site before/after (snapshots `baseline` → `postclock-final` in `reports/scoreboard/`), bore-void offset in mm:

| site | before | after | note |
|---|---|---|---|
| 276794487 t3 | 1.09 | **0.26** | clocked onto the recess |
| 295811960 t29 | 0.79 | **0.17** | clocked onto the recess |
| cap6020 t29 | 0.54 | **0.08** | clocked onto the recess |
| cap6030 t29 | 0.52 | **0.03** | clocked onto the recess |
| neodent t4 | n/a | **0.15** | void newly detectable under ring-relative reach |
| 297589851 t20 | 0.57 | 0.59 | kinematic floor (void nearly central); ships flagged *attention* |
| cap7030 t29 | 0.31* | 0.46 | *baseline measured a differently-detected void; the pass improves on its own incumbent |
| neodent t13 | 0.75* | 1.67* | pose unchanged (stability refusal); *estimator-convention shift only |
| zimmer t7 | 1.78* | 2.24* | pose unchanged; grade **low** (position-dominated residual) |

Rim centring cost of all of the above: **zero** — rim off-centre reads 0.000–0.006 mm on every full-rim site (the interleave prototype's +0.51 mm cost is gone), and rim-band / top-face stay within every certification bound. Battery: **534/534 green**.

### 6.5 Test battery

The automated battery now stands at **788 tests**, including guards for the ring-fixed clocking (synthetic recess recovery + ring-invariance at zero AND tilted seats, five real-site bore-on-void contracts with per-site ceilings so a regression can never hide behind an unrelated flag, direct units for the stability-refusal and incumbent gates, seven rim-centering guards) and the ride-off bound.

### 6.6a Superseded note (2026-07-20 evening)

§6.3's "recess is authoritative" rule was measured WRONG the same week it shipped — see §7: the recess-void *azimuth* is systematically biased by partial visibility, and the coded cutouts (which §3(b) correctly identified as carrying the scan's pose information) are now the primary rotational instrument. §6's record is kept as written; the mm-scale void *detection* machinery it describes remains in service as the fallback instrument.

### 6.6 Independent adversarial review (2026-07-20)

The round was closed with a three-lens adversarial review (geometry/numerics, calibrated-contract safety, test adequacy), every finding independently re-verified against the real catalog. All 13 confirmed findings were fixed the same day — highlights: the rim-band certification gate was silently skipped on the click/brush seed path (anchor added); the packaged `fitness`/coverage number was computed at a pre-refinement pose (now refreshed at the final pose); two test contracts had escapes that made them vacuous (closed with tilted-seat fixtures and per-site ceilings). One finding is deliberately **documented rather than tuned**: the bore-mouth estimator is cut-sensitive on the neodent 4230/4030 (~0.3 mm scale, 2 of 12 variants) and no software-only ground truth exists to tune it against — the **printed phantom** (caps designed into the solid at known poses) is the instrument that validates or corrects it; retuning blind would be guessing.

---

## 7. Addendum (2026-07-20) — The coded cutouts become the rotational authority

**Client report:** "still not 100% working, not properly aligned and rotated to match the healing cap and bore channels."

### 7.1 What the investigation found

A lab tech judges rotation at the **coded cutouts** on the cap's top face — and nothing in the pipeline optimized them. Worse, a two-pose consistency study (the same scan evaluated at two poses with an exactly-known rotation between them — ground truth that needs no phantom) proved two things:

- The **recess-void azimuth is systematically biased**: a partially-visible recess dip pulls its measured centroid sideways, so the §6 recess clock had rotated *away* from the coded features on **5 of the 7 sites** where it fired — on one site it rotated a correctly-aligned pose 71° wrong while its own bore metric *improved*.
- Simple 1-D azimuthal profiles are not trustworthy extractors (they reproduced known rotations on at most 3/7 sites). Only a **2-D unwrapped depth-image correlation** ("e8": (θ,r) grid over the coded band, informative-row filtering, azimuths about the scan's own cap-rim centre) passed — **6/7 sites to ≤10°**, the one failure being a half-occluded ring that its own evidence gate flags.

Every industry lens pointed the same way: ZimVie's coded-abutment workflow has the operator click dots **on the codes**; Nobel's patent matches the asymmetric top-face boundary; the classic literature solves exactly this problem with cylindrical unwrapping + circular correlation.

### 7.2 What shipped

`domain/clock_signature.py` (the validated e8 extractor, deterministic, RNG-stream-neutral) plus a codes-primary final clocking pass: read the coded misalignment → rotate to null it (ring-fixed kinematics, all §6 certification gates, **plus a confirm re-read at the candidate pose, ≤12°**). No code evidence → the §6 recess clock unchanged. Neither instrument → the site ships flagged `rotation_unverified`. Where both instruments read, their disagreement ships as `clock_consistency_deg` (>20° routes attention) — on a rigid part they cannot both be right, and the **printed phantom (designed clock angles) is the physical arbiter**.

### 7.3 Fleet after (snapshot `notchclock-v1`, battery 534/534 green)

| site | coded-rotation residual | evidence | note |
|---|---|---|---|
| 276794487 t3 | **1.1°** | codes+recess | rim 0.51→0.38, top-face 0.32→0.26 |
| 295811960 t29 | **−1.9°** | codes+recess | the smoking-gun site, now aligned; rim 0.50→0.35 |
| 297589851 t20 | **−2.1°** | codes+recess | top-face 0.30 |
| cap6020 t29 | **0.1°** | codes+recess | top-face 0.74→0.62 |
| cap6030 t29 | **−2.2°** | codes+recess | rim 0.45→0.22, top-face 0.30→0.21 |
| cap7020 t3 | **0.8°** | codes | first-ever rotational anchor on this site |
| neodent t4 | **0.7°** | codes+recess | top-face 0.50→0.43 |
| neodent t13 | **−3.1°** | codes | previously stuck at the face-sweep fallback |
| cap7030 t29 | 23.8° (unconfirmed) | recess | half-occluded ring — evidence gate refuses honestly; recess behavior kept |
| zimmer t7 | — | none | `rotation_unverified` + attention (mis-seated site, §6 record) |

**8 of 10 sites now ship code-verified rotation ≤3.1°** — and the physical fit metrics *improved* almost everywhere the codes won (they were never told to improve): independent corroboration that the coded features are the true rotation. The `bore_void_off` column now largely measures the void detector's own azimuth bias (0.3–1.3 mm at 24–107° instrument disagreement, shipped per site); it remains the fallback instrument and the phantom will arbitrate the conflict physically.

### 7.4 What this means for productization

The rotation the client sees is now (a) actively optimized, (b) evidence-gated with an honest refusal state, (c) cross-checked by a second instrument with the disagreement surfaced, and (d) reported in degrees — the unit of the field's own spec (screw-joint literature: ≤2° goal; the commercial coded-abutment gold standard itself achieves ~2–3°).

### 7.5 Productization trio (shipped 2026-07-20, battery 534 worker + 222 web green)

1. **Acceptance artifacts in every package** (`adapters/qc_render.py`): per site, an occlusal **clock view** (scan depth field, coded-cutout overlay, bore★/void✕ markers, rotation residual + evidence text) and a **signed deviation map** (±0.5 mm industry colormap, RMS + p90) — both SHA-256-listed in the manifest. The lab tech's eye test is now a deliverable, not a conversation.
2. **Operator rotation nudge at the review gate**: a Rotation column in the results table (−15/−3/+3/+15/Reset, auto-expanded on weak-evidence rows) backed by a server endpoint that re-applies the rotation through the *same* ring-fixed kinematics and *same* certification gates as the pipeline (409 with a human-readable reason on refusal), re-reads the coded residual ("−1.8° — aligned"), re-emits the deliverables with a nudge audit record, and logs provenance to run-history. A proposal the gates still judge — never a bypass.
3. **Phantom clock ground truth**: each cap on the printable plate now carries a designed clock angle in the ground-truth JSON, and the evaluator reports **both instruments' clock error per site** (coded-feature vs recess-azimuth) — one print+scan physically arbitrates the §7.1 instrument conflict and sets the validated rotation auto-pass line. En route, a pre-existing generator defect was found and fixed: at print pitch, the SDF hole-seal leaked through the cap CADs' open bore mouths and had **erased half the zimmer cap crowns from the printable solid** — the regenerated `phantom-plate.stl` is the one to print.
