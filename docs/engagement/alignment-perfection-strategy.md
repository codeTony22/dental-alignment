# Alignment Perfection Strategy — inputs, algorithms, and the path to high confidence

**Date:** 2026-07-23
**Audience:** lab ownership and technical lead
**Question answered:** *"Do we need better inputs from the doctor? What algorithms does the
industry use — and what are we using? Give us a cohesive plan for near-perfect alignment
with high confidence."*

Everything in this document is measured (the instrument is named each time) or cited
(industry sources in the two research appendices). Companion documents:
[`docs/research/marks-as-locators-plan.md`](../research/marks-as-locators-plan.md) (the
full staged plan + adversarial verification) and
[`docs/research/doctor-inputs-research.md`](../research/doctor-inputs-research.md) (the
industry intake research, fully cited).

---

## 1. How our alignment actually works (plain language)

You asked whether we align by "optimization search over what covers the most surface."
We deliberately do **not** — and it is worth explaining why, because we tried it.

**Surface coverage is a misleading objective.** Early on, a perfect seat measured "41%
coverage" and was mistaken for a failure: raw coverage counts the surrounding gum and
teeth that no healing cap can ever explain, and a partially visible cap can never reach
100%. Coverage survives only as a *read-out*, never as the thing we optimize.

What runs instead, in order:

1. **Find the cap (proposals, confirmed by the doctor).** The proposal stage detects
   healing caps from the scan alone — it looks for the cap's signature: a closed, level
   ring (the rim) with an empty core. Measured fleet-wide (2026-07-24, `detect_hit` /
   `detect_off_mm` on the scoreboard): a candidate lands within 2mm of the confirmed
   site on **8 of 10 sites** — 0.002–0.06mm on six of them, 0.22 and 0.51mm on two more
   — but **misses 2 of 10** (cap7020 and the zimmer t7 scan: candidates appear elsewhere
   on those arches, none within 5.4mm of the real cap). Detection is strong, not solved;
   the doctor's one-click confirm remains a required step, not a formality.
2. **Measure the rim, closed-form.** The visible rim band is fit as a 3D circle (a
   least-squares circle fit). A circle in space gives us the cap's **axis and centre
   directly — measured, not searched**. Depth is then a simple one-dimensional search
   along that axis. This is the biggest difference from generic "optimization search"
   approaches: where the geometry can be *measured*, we measure it.
3. **Identify the variant (this IS an optimization search — a calibrated one).** Each
   catalog size is seated and scored with a calibrated two-way distance score (how well
   the scan explains the part AND the part explains the scan — one-way scores let a big
   cap "swallow" a small scan patch). Ranking is decided before any refinement polish, a
   structural rule that prevents subtle self-deception. Two sizes that score too close
   are declared "inseparable" and the doctor's declaration decides — never a silent guess.
4. **Refine, winner-only, behind safety gates.** Depth polish, a bounded best-fit pass
   (our own trimmed ICP — the industry's standard fine-alignment step, kept on a tight
   leash because unleashed ICP wanders to plausible-but-wrong basins), and re-centering.
   Every pass may only move the pose if it does not break certification bounds.
5. **Rotation from the coded cutouts.** The cap's top face carries coded features (the
   same idea as ZimVie's coded-abutment system). We unwrap the top face into a depth image and
   correlate it against the template's pattern — the rotation is *read*, not guessed.
   This shipped this week and is code-verified to **≤3.1° on 8 of 10 sites** (the
   commercial gold standard itself achieves ~2–3°); the other two sites are honestly
   flagged (one half-occluded ring, one bad scan).
6. **Confidence + QC artifacts.** Every site gets a graded confidence, an operator
   rotation nudge behind the same safety gates, and two acceptance images in the package
   (the clock view and the signed deviation map — the picture a QC tech signs off on).

**The industry's algorithm landscape, for comparison** (full survey in
`docs/research/alignment-algorithm-survey.md` and the §7 record):

| Approach | Who uses it | Our verdict |
|---|---|---|
| 3-point coarse click + best-fit ICP | 3Shape, exocad, Medit scan-body flows | We have the equivalent, with the coarse step *measured* (rim circle) instead of clicked |
| Coded-feature reading (occlusal codes) | ZimVie's coded-abutment workflow (the closest product) | Adopted — our e8 depth-image correlation, validated on ground truth |
| Difference-map acceptance QC | ZimVie, Control-X convention | Adopted — shipped in every package |
| Global feature solvers (TEASER/FGR/4PCS) | research literature | Structurally inapplicable to smooth revolute caps (measured twice) |
| Deep-learning pose estimation | research/emerging | No training data at our scale; nothing it solves that measurement doesn't |

---

## 2. Why alignment is not perfect yet — the measured answer

An 18-run decomposition across the whole fleet (every site run at its curated marks AND
at idealized anchors) split the remaining imperfection into named causes:

**Cause 1 — the "island" problem (dominant, fixable).** The region we feed the seat is
anchored at the doctor's click and is median **54–60% tooth/gum** — points the cap can
never explain. With a clean anchor, measured payoffs include: t20's rim 1.00→0.51mm and
its screw hole landing 1.07→0.08mm; **t7's rotation going from −150.5° unverified to
−3.6° code-verified** — the coded evidence was there all along, buried in contamination.

**Cause 2 — clicks are structurally load-bearing (fixable — this is your product
decision).** Today a 0.6mm click error moves the shipped pose by up to **1.09mm and
16.6° of axis** — the pose can move *more than the click*. Under the measured click
noise (p90 = 0.61mm), this manufactured error is the main reason no site grades "high"
confidence today: the confidence probe honestly reports the click-sensitivity we built in.
In a simulation where marks only *locate* (the pose anchored to machine measurement),
the confidence spread collapses **7–13×** and clean sites pass every "high" bar.

**Cause 3 — two dishonest instruments (fixable, zero millimetres).** Our rim-agreement
QA is anchored to the clicked centre, so it is blind to click-induced error (measured: a
1.09mm-off pose *improved* the metric). And the recess-azimuth alarm over-warns on five
sites whose rotation is already code-verified — that disagreement is the known bias of
the recess instrument, which the printed phantom will calibrate.

**Physics floors — flagged, not "fixed."** Submerged caps: the visible ring meets the
cap's flank, so a correct seat on t13 honestly reads ~1.5mm rim residual; no software
crosses that — declaration + honest flags do. t7's scan has a hole across 46% of the
seat band: that is a **rescan**, not an algorithm. Height twins under gum remain
separable only by the doctor's declaration.

---

## 3. Do we need better inputs from the doctor?

Short answer, from the industry research: **not more landmarks — better capture and
richer identity.** No commercial system asks doctors for precision clicks; every one of
them (ZimVie, Atlantis, 3Shape, Medit) uses coarse locators plus **hard intake gates**.
Your instinct — "the mark just finds the healing cap" — is exactly the industry pattern.

Ranked recommendations (full cited tables in the research appendix):

1. **An automatic capture gate at upload (the industry's real accuracy mechanism).**
   The coded-abutment standard requires the entire cap circumference + code band visible and the collar 1–2mm
   above the gum; Atlantis formally rejects scans with saliva/artifacts ("RESCAN
   REQUESTED"). We can compute rim-arc coverage and code-band visibility at upload and
   refuse with a concrete message ("rescan the cheek-side rim") **while the patient is
   still in the chair.** Targets our measured partial-coverage and t7-class failures.
2. **Ask for color scans (PLY/OBJ instead of bare STL) — near-zero friction.** Scanners
   capture color natively. Titanium-vs-tissue color separation converts our #1 limiter
   (the 54% contamination) into a far easier segmentation problem.
3. **A periapical radiograph of the seated cap.** Standard of care for scan bodies; the
   only input that can catch a cap that is not fully seated — the one failure mode the
   scan cannot distinguish from a good cap in a strange place.
4. **Implant system + platform on the Rx, and a photo of the cap's engraved code or its
   package label.** Cheap cross-checks on the declared variant, and the variant ground
   truth this project has never had.
5. **Exposure rule for submerged cases:** the industry answer is procedural — the
   coded-abutment standard simply refuses caps without 1mm supragingival exposure; the alternative is a taller
   cap. We keep the declaration path plus honest flags.

**What we will NOT ask for** (measured or industry-abandoned): screw-hole marks (the
scan shows no hole — measured), extra precision clicks (0.3–0.6mm click noise makes them
counterproductive; nobody in the industry does it), bite scans *for alignment* (collect
for restoration design only), powder, model scans of coded caps.

---

## 4. The implementation plan (staged, reversible, measured at every step)

Full detail + adversarial verification in `docs/research/marks-as-locators-plan.md`.
The shape: **shadow first, promote behind gates, recalibrate, then re-grade.**

| Stage | What happens | Pose changes? |
|---|---|---|
| 0 | Baseline snapshot; surface hidden gate signals | no |
| pre-work | Machine-marks autopsy (measure the real Stage-4 impact before writing production code); pin one RNG source | no |
| 1 | **Island segmentation as a SHADOW measurement** — machine centre/border/contamination reported *next to* shipped numbers, changing nothing | no |
| 2 | **Metric honesty** — QA anchored to the machine ring (stops being blind to click error); stop over-warning off the biased recess instrument on code-verified sites | no |
| 3 | Demote the clicked border circle to initializer + advisory cross-check | border sites only |
| 4 | **Marks become locators** — seat band + region from the machine-detected island, *gated*: if the island doesn't converge on a site, that site keeps today's behavior and is flagged. A failed segmentation can never ship a worse seat than today | fleet-wide, gated |
| 5 | Recalibrate the identification score on the new seat paths (declared-ID must stay 4/4 on the labeled arches) | no |
| 6 | **Confidence re-grade** — the click-noise probe becomes vacuous by construction (good — that noise no longer matters); replaced by a machine-side stability probe; "high" additionally *requires* code-verified rotation | no |
| 7 | **Physical validation** — print + scan the phantom (designed poses AND clock angles): pins "high means ≤X mm with probability Y" to independent truth and arbitrates the recess-vs-codes instrument conflict | no |

Honesty notes carried from the adversarial verification: the big per-site payoffs were
measured with an idealized anchor — the production segmentation must first *prove* it
reaches them (that is what the shadow stage and the machine-marks autopsy are for); on
one site (t20) an anchor shift *lost* the coded rotation evidence, so code-evidence
survival is re-verified per site before promotion; t7's islanding currently fails and
keeps its fallback until fixed. Splitting the centre+rim pair supersedes the earlier
"pair is one measurement" contract **by this product decision** — recorded, not snuck in.

**What "high confidence" will mean when this lands:** seat anchored to a converged
machine-measured island; stability spread under bars whose millimetre meaning is
phantom-pinned; rotation code-verified; visible-band rim agreement in bounds with
submergence flagged separately; no unresolved size ambiguity. Expected distribution on
today's fleet (prediction to be verified, not asserted): roughly 5–7 high, the rest
medium with *named* floors, t7 low until rescanned.

---

## 5. The one-page executive answer

- **Inputs:** keep the marks as rough locators (your instinct matches the entire
  industry); add capture gating at upload, color scans, a radiograph, and richer
  identity on the Rx. Do not add landmark burden.
- **Algorithms:** we already use the industry's best pattern — measure what is
  measurable (rim circle, coded rotation), search only where searching is right
  (variant identification), refine behind safety gates, and prove it with acceptance
  artifacts. The remaining gap is not a missing algorithm: it is that the doctor's
  clicks still *steer* the measurement. The plan removes that, carefully.
- **Confidence:** grades are honest today (medium everywhere) because click noise really
  does move today's poses. Make marks locators and the same honest instrument will read
  "high" — and the printed phantom converts "high" into a validated millimetre claim.
