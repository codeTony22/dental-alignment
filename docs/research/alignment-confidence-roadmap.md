# Alignment Confidence Roadmap

**Audience:** dental-lab decision-maker. **Question answered:** *"What else can we do to
improve alignment? Do we need to improve the search optimization? Do we need to mark the
holes in the healing cap that align to the library?"*

This document is a decision tool, not a research paper. It is built on five grounded
deep-dives that measured the current pipeline on the 10 real sites and 4 labeled
ground-truth arches, plus a skeptical cross-check. Every claim below cites a measured
number.

---

## 1. The three questions, answered head-on

### (a) What else can we do to improve alignment?

**The biggest win is not a better algorithm — it is a better input.** Make the doctor's
**declared variant a required intake field**. Measured on the 4 labeled arches: with no
declaration the pipeline picks the exact variant only **1 of 4** times (it flips
6020↔6030, and even mis-calls 7020→8030 across a *diameter* class); with the declaration
passed in it is **4 of 4** correct and guidance rises from "attention" to "ready" on every
arch, with the pose fully recoverable (rim agreement 0.31–0.80 mm, top-face 0.16–0.28 mm).
This path is **already wired** (`auto_flow.py`, `candidate_specs=[declared_spec]`) — the
change is workflow enforcement, not code.

After the declaration, the ranked levers are:

1. **Quantify per-site confidence** with a Monte-Carlo click-noise re-seat (an actual
   mm/deg error bar — see question (b) and the roadmap). This is what lets the machine
   ever *earn* an auto-pass.
2. **Wire the signals we already compute but ignore** into the gate (top-face p90,
   seat-residual magnitude, rim-arc fraction), so the fleet-worst seat stops reading
   "ready."
3. **Fix the systematic axial (depth) under-seat on tall caps** — the single largest
   *measured* pose error in the whole set (below), and invisible to every rim-based
   confidence signal.
4. **Clean the ROI** (cut tooth/gingiva out of the patch the optimizer sees) — the only
   real *precision* lever, and it is upstream of the solver.

Marking the screw holes is **not** on this list. See (c).

### (b) Do we need to improve the search optimization?

**Partially — and only for confidence, not for precision.** Measured directly: the inner
solver recovers a planted pose to **~5 µm / 0.13°** on clean input and **~19 µm / 0.64°**
at realistic 40 µm scanner noise, and on all 9 real sites the seat already sits **at the
score minimum** (height arg-min ≈ 0). The optimizer is not failing to find a basin. It
degrades 25–90× *only when the input degrades*: submergence drives centre error to
~480 µm, and gingiva contamination drives axis error to 4–5°. On real arches the patch fed
to the seat is a **median 54% tooth/gingiva contamination** — more than half the points are
not the cap. **So the bottleneck is the input, not the optimizer.** "Better search" of the
global/feature kind (TEASER, FGR, 4PCS) is structurally inapplicable to smooth revolute
caps and buys nothing. The two search-family items worth building — a dense score-landscape
readout and an X-ICP localizability spectrum — are worth it because they **make the
uncertainty observable** (confidence), not because they sharpen the pose. Do **not** rebuild
the solver for accuracy.

### (c) Do we need to mark the holes that align to the library?

**No — for the problem you are worried about, it is redundant and partly impossible.**
Three measured reasons:

- **The scan does not contain the hole.** The 3.3–5.4 mm-deep screw channel appears in the
  intraoral scan as a **smooth convex dome** — on cap6030 the scanned centre sits **+0.13 mm
  *above* the rim**, while the CAD has it 5.3 mm *below*. There is no hole in the scan to
  click, and it is least visible on exactly the submerged caps where confidence is lowest.
- **Position and axis are already pinned by the visible rim.** The fitted rim normal agrees
  with the shipped pose axis to **1.0–3.7°** (circularity residual 0.23–0.36 mm). A hole
  click would only re-supply the axis the rim already gives, less accurately.
- **The only DoF a mark could touch is clocking — and clocking is inert.** The screw channel
  is bored **coaxial** to the implant axis, so rotating the cap changes **no delivered
  geometry**; and the top-face→scan clocking signal is flat to **0.04–0.07 mm** (at/below
  scanner noise), so an operator would read the same weak signal the existing 24×15° sweep
  already reads.

**Crucially, hole-marking cannot resolve the height-twin** (the real confidence problem):
the twins' top faces differ by only **0.02–0.07 mm** in radius — the distinguishing ~2 mm of
collar lives entirely below the gingiva. The honest scope for any feature mark is a *visual
QA tie-breaker for the overlay*, not geometric accuracy or variant identity. Do not build it
expecting a precision or ID gain.

---

## 2. The physics ceiling — where confidence is bounded by nature, not software

State this to the lab plainly, because no amount of engineering crosses it:

- **Diameter class: the scan CAN resolve it.** The visible rim/shell fixes the diameter, and
  the declared-variant cross-check guards a gross mis-declaration.
- **Collar height (the 20-vs-30 twins): the scan CANNOT resolve it when the cap is
  submerged.** The twins differ by ~2.0 mm of collar that sits under the gingiva. With only
  the top 1.0–1.5 mm exposed, **95–98% of a 30-cap's visible surface coincides within 0.2 mm
  with its 20-twin**; the twin becomes observable only above ~2.5 mm exposure (shell sharing
  falls to 64–78%). On the labeled arches the caps are 33–65% exposed — the collar is
  sub-tissue. In seat-residual terms the twin gap is **0.01–0.06 mm**, below any achievable
  calibration precision.

**Consequence:** collar height is collapsed only by an *external* input — the doctor's
declaration (or a longer supragingival scan body at the chair). No optimizer, no
hole-marking, and no re-scan from a different angle changes this, because the missing
geometry is occluded by tissue, not by viewing angle. Picking the wrong twin is not just a
billing label: it shifts the delivered implant-platform position **0.49 mm** (same-diameter
twin) to **0.93 mm** (cross-diameter mis-ID).

---

## 3. The three honest buckets — and which one moves "high confidence"

| Bucket | What it changes | Does it raise trustworthy confidence? |
|---|---|---|
| **(i) Improve precision (algorithmic)** | Tighter pose on well-posed sites | **Little.** The solver is already at 5 µm on clean input; the real precision headroom is ROI cleaning + the tall-cap depth fix, and both are input/gate problems more than solver problems. |
| **(ii) Quantify confidence** | Turns "passed all gates" into a per-site mm/deg error bar with a validated threshold | **Most of it.** This is the bucket that lets the machine earn an auto-pass. |
| **(iii) Collapse observability limits (inputs)** | Declaration, known platform depth, taller scan body | **The largest single step** — the declaration alone moves 1/4→4/4 ID. But it is a workflow change, not something the software can force. |

**The verdict the lab needs:** *high confidence comes mostly from bucket (ii), unlocked by
one bucket (iii) input (the declaration).* Search optimization (bucket i) is not the lever.

---

## 4. Ranked roadmap (highest confidence-per-effort first)

Effort: S ≈ hours–1 day, M ≈ days, L ≈ week+ / external cost.

| # | Item | Question it answers | Bucket | Effort | Expected gain | Risk |
|---|---|---|---|---|---|---|
| 1 | **Make the doctor's declared variant a required (hard-to-skip) intake field.** Already consumed by the pipeline; only UI/workflow enforcement plus surfacing the rim cross-check as a second opinion. | (a) | Input (iii) | **S** | 1/4→4/4 exact ID; all labeled arches attention→ready; removes 0.49–0.93 mm mis-ID platform error. Single largest, cheapest win. | Trust shifts to the doctor; only *same-diameter height-twin* mis-declarations pass silently — and those are unresolvable by the scan anyway. |
| 2 | **Calibrate FLE from a small repeat-click study** (operator re-clicks centre+rim 5–10× on a few existing arches). | (b) | Input (iii) | **S** | Sets the mm x-axis for every confidence number below; also finally quantifies the memory-noted 0.64→1.08 mm re-click swing. Prerequisite, not optional. | A rim click on a slope is anisotropic — capture a 2-D covariance, not one scalar, or axis uncertainty is understated. |
| 3 | **Wire the already-computed-but-cosmetic signals into the gate:** persist and gate on top-face **p90** (only the reassuring mean is stored today), seat-residual magnitude, rim-arc-as-fraction, candidate top-2 gap; delete the dead `fit_max_mm` param. | (a),(b) | Confidence (ii) | **S** | Closes the measured "fleet-worst seat (zimmer t7) reads *ready*" hole with no new algorithm; makes *why* a site passed auditable. | Re-classifies some current "ready" sites to "attention" — must re-threshold against the 10 real sites so it doesn't over-warn on good partial-rim seats. **Do after the pending score-recalibration (see §5).** |
| 4 | **Make the height-twin limit an explicit signal and block silent acceptance:** compute exposed cap height above the gingiva plane; below the ~2.5 mm crossover assert `candidates_too_close`, and when no declaration is present, block shipping the noise-winner. Also score the twin *even under a declaration* (advisory) so the ceiling is visible on declared sites where it is currently hidden. | (a),(c) | Confidence (ii) | **S–M** | Guarantees no 0.01–0.06 mm-margin twin ever ships on a guess; makes the physics limit honest and explainable instead of silently reassuring. | Needs a reliable gingiva-plane estimate; keep the existing residual-tie rule as an OR fallback, never a replacement. Must be framed as advisory so it doesn't read as disputing the doctor's billing. |
| 5 | **Build the per-site Monte-Carlo click-noise re-seat.** Jitter centre+rim (and border clicks) by the calibrated FLE, re-run the real seat N times, report axis-SD (°), centre-SD and platform-SD (mm). **This is ONE build** (both confidence dives proposed it). | (a),(b) | Confidence (ii) | **M** | First per-site number in true pose units, and discriminative (cap6030 measured ~2× noisier than cap7020). Turns "passed all gates" into an error bar. | Absolute scale is meaningless until FLE (#2) and a truth-calibrated threshold (#7) land. Runtime is seconds — sub-sample N or run async. |
| 6 | **Fix / flag the systematic axial under-seat on tall (30-height) caps.** Shipped poses float **1.0–1.95 mm high** (top-face→scan mean 1.27 mm cap6030, 0.98 mm cap7030); an extra downward slide of −1.0 to −1.25 mm collapses top-face agreement to ~0.25–0.33 mm. Audit whether `_refine_depth`'s gates are refusing a legitimate slide on straight-walled tall caps; gate on top-face p90 **at the shipped depth**. | (a) | Precision (i) | **M** | 0.7–1.6 mm axial correction — the single largest measured pose error, and *invisible* to every rim-based confidence metric, so leaving it un-flagged gives false assurance. | Depth gates are calibrated to stay safe on submerged caps; any loosening must be re-validated on the labeled arches so it doesn't reintroduce the 2 mm-high failure. |
| 7 | **Establish independent ground truth for the auto-pass threshold:** place-and-recover synthetic (the `ground_truth.json` + `evaluate_case` machinery already exists) to set the cutoff, then one physical printed/CMM phantom across 2–3 exposure levels to validate the noise model. | (b) | Confidence (ii) | **M–L** | The mechanism that actually *unlocks* auto-pass: a validated pass/fail line at the clinical target, decoupled from the fit residual. | Only 4 labeled arches — indicative not certified until more cases arrive; synthetic scanner noise must match field roughening or the threshold is optimistic. Physical phantom carries external cost/turnaround. |
| 8 | **Add X-ICP localizability + dense score-landscape readouts** (search-family, confidence-only). Emit the 6×6 JtJ eigen-spectrum per site (measured condition 10.5–52.9; tilt/spin softest) and a dense tilt×height×clocking landscape (flat valley = reportable ambiguity). Report *alongside* the existing gates. | (b) | Confidence (ii) | **L** | Graded per-DoF confidence ("depth well-constrained, clock weak") instead of a binary pass — the principled basis for a defensible policy. | Larger build; sequence **after** #3–#7. Must **consume, not replace,** the rim-circle axis (the landscape is flatter in tilt than the rim estimate). Depends on the recalibrated score (§5). |
| 9 | **ROI contamination cleanup** (curvature/normal cap-vs-tissue segmentation or a tighter rim-anchored crop). | (a) | Input/precision (i) | **L** | Largest *precision* headroom: recovers ~1.5° axis / ~170 µm centre on contaminated sites and de-inflates the fit residual so the gate reads truer. | Segmentation on submerged caps is itself hard; validate on the place-and-recover harness so it doesn't over-crop the constraining rim wall. |

### Status (2026-07-19)

The analysis above is left as written (it is the record the decisions were made from). Where things stand now:

- **#1 declared variant — DONE (2026-07-18).** Required intake field, enforced by the web UI picker; measured 1/4 → 4/4 exact ID on the labeled arches. Declared ≠ identified raises an amber mismatch flag.
- **#2 FLE calibration — DONE (2026-07-19).** Measured from run history three independent ways (border repeat-click xy p50/p68/p90 = 0.32/0.46/0.61 mm; all invert to σ ≈ 0.3 mm/axis): `docs/research/fle-calibration.md`. The history's centre-click channel supplied zero usable scatter (every pair is a byte-identical replay of the curated marks), so the deliberate centre-click re-click study is tooled (`tools/fle_study.py` + `docs/engagement/fle-centre-click-protocol.md`) and handed to the lab.
- **#3 gate signals — PARTIAL (2026-07-19).** Top-face **p90** (not just the mean) is now persisted and drives guidance at the 1.5 mm ride-off bar; border-click disagreement >0.6 mm routes to "attention". The remaining signals (rim-arc fraction, top-2 gap) are still cosmetic.
- **#5 Monte-Carlo click-noise re-seat — DONE (2026-07-19).** `_pose_stability_bootstrap` (K=8 re-seats under the measured σ=0.3 mm) → `domain/pose_confidence.py` grades **high / medium / low**, shown per site in the demo. Grades discriminate the fleet correctly but are not yet validated against truth-known error (#7 still open).
- **#6 tall-cap depth — DONE (2026-07-18).** Winner-only gated depth polish (`_refine_depth`); floating seats now fail the battery (see completion report §2.3).
- **#7 independent ground truth — TOOLING READY (2026-07-19).** Printable phantom + evaluator shipped (`tools/make_phantom.py` / `tools/evaluate_phantom.py`, protocol `docs/engagement/phantom-protocol.md`); the physical print + scan is handed to the lab. The validated auto-pass line still waits on it.
- **New instrument (not an original lever): fleet scoreboard (2026-07-19).** `tools/fleet_scoreboard.py` runs every real case through the production pipeline and diffs per-site metrics (`--save` / `--baseline`, snapshots in `reports/scoreboard/`) — the regression harness that judges every lever above by measurement instead of anecdote.

### Explicitly do NOT build (folded in from the critique)

- **A separate surgical/prosthetic platform-depth input** — redundant with the declaration.
  The scan-body→platform transform is coaxial and its translation *is* the collar height, so
  "platform depth known at surgery" and "declared variant" are the **same information** for
  this direct-seat catalog. Building it is a second, noisier intake for the same DoF.
- **A Fitzpatrick closed-form TRE predictor on today's gestures** — every real site has
  exactly one centre+rim pair (2 *collinear* points); Fitzpatrick needs ≥3 non-collinear. It
  is uncomputable on the data you actually capture. Revisit *only if* doctors adopt
  multi-point border clicks.
  *Update (2026-07-19): the revisit condition arrived — the run history now contains
  multi-point (4-click) border gestures, so `domain/pose_confidence.py` computes a Fitzpatrick
  TRE where the marks support it. It is carried for reporting only; the confidence grade rests
  on the empirical bootstrap spread, exactly as this bullet demanded.*
- **An "independent TRE" measured against the shipped `implant.json` poses** — those poses
  *are* the pipeline's own output, so it is circular, not independent. Real independent truth
  needs the synthetic + phantom of #7.
- **A clocking-marking advisory / screw-hole correspondence landmark** — the deliverable is
  clocking-invariant (coaxial channel), the signal is flat at/below scanner noise, and the
  hole does not exist in the scan. It manufactures false precision.
  *Correction (2026-07-19): the coaxial premise was wrong — the bore measures 0.43–0.76 mm
  off-axis across the catalog, so clocking does move the delivered screw channel; and while the
  bore's interior is indeed absent from the scan, the recess dip is rich signal
  (547–8,356 points, 0.76–3.5 mm deep). The pipeline now clocks against it automatically
  (`_void_clocking`, recess-authoritative, ring-fixed — it rotates about the posed
  rim-ring centre so the centering cannot be undone; see completion report §6). The conclusion that stands: no operator hole-marking — the machine reads the
  recess better than a click would.*
- **Rebuilding the inner solver, or a global feature solver (TEASER/FGR/4PCS)** — the solver
  is already at the score minimum on real data; these are structurally inapplicable to smooth
  revolute caps.

---

## 5. Prerequisite: the pending score-recalibration

The axis-canonicalization fix left templates upright, but the **score has not yet been
re-calibrated on the corrected upright templates**. This blocks the confidence critical
path: items **#3, #4, #8** (and any landscape/localizability/too-close threshold) all consume
the same score, so their thresholds must be set *after* recalibration or they will be
calibrated against numbers that are about to change. The pre-axis-fix benchmark rankings are
indicative only for the same reason. **Land the recalibration first; then set thresholds.**
Scope the recalibration narrowly — it restores *diameter-class* reliability for the
no-declaration fallback and strengthens the mis-declaration guard, but it **cannot** separate
height twins (their 0.01–0.06 mm gap is below any calibration precision).

*Status (2026-07-19): DONE — the score was recalibrated on the corrected upright templates;
identification now runs the calibrated seat + 2.0×t2p contract (above-cut −0.4), with
candidates ranked strictly before any per-candidate refinement.*

---

## 6. One-line summary for the lab

You get "high confidence" by (1) **requiring the doctor's declaration** — the one input that
collapses the height twin the scan physically cannot see — and (2) **measuring per-site pose
uncertainty and validating a threshold against real ground truth**, so an auto-pass means
"accurate to X mm with probability Y," not merely "refused all gates." Better *search
optimization* and *hole-marking* are not the levers: the optimizer is already near-exact, and
the holes are neither visible in the scan nor able to cross the physics ceiling.
