# Per-site alignment confidence metric — design (Spec A)

**Date:** 2026-07-15
**Status:** approved (user: "build your recommendation")
**Author:** case-prep automation

## Problem

The advisory gate routes almost every real site to the doctor. Not because the pose
is bad — this week's measurements show the seat already extracts pose to the
rim-geometry limit (rim-seat 0.3–1.0mm, top-face <0.6mm on clean sites) — but because
we have **no validated confidence number** to justify anything stronger than "advisory,
visually confirm." "High confidence" is therefore a *quantification* problem, not an
*alignment* problem.

Measured facts grounding this spec:
- A template-guided clean ROI + re-fit does **not** improve the pose (rim-seat neutral-
  to-worse, pose drifts 0.3–1.2mm) — the pose is not ROI-limited. So confidence must be
  *measured*, not squeezed out by better fitting.
- Good operator gestures agree to ~0.3mm (leave-one-out plane distance on real border
  clicks measured 0.33mm); a bad gesture measured 0.89mm. Click noise is real and
  quantifiable.
- The height-twin ambiguity is a physics ceiling (a submerged 30-collar cap shows a
  20-collar cap's shell) — no confidence metric beats it; it is reported as a hard limit.

## Goal

A per-site **confidence** number that **predicts pose error**, so the gate can *grade*
a site (high / medium / low) instead of a blanket advisory. This reduces the operator's
review burden — high-confidence sites need a glance, low-confidence sites get attention —
**without removing the human** (the real-data policy: never auto-manufacture blind).

Success criterion (non-negotiable): the confidence grade must **correlate with actual
error** on ground truth. A confidence number that does not separate good seats from bad
is worse than none.

## Approach

Core = **bootstrap pose-stability**. Complementary = **Fitzpatrick TRE prior**. Both fold
into a **grade** together with the existing signals. Read-only: the confidence pass never
changes the shipped pose or the identified variant — pure addition, no calibration risk.

### 1. Bootstrap pose-stability (core)

For a seated site, probe how much the pose would move under plausible click error:

1. Take the doctor's marks (centre + rim mark, or ≥3 rim/border points, or brush patch).
2. `K` times (K = 8), perturb every mark by Gaussian click-noise (σ = 0.3mm, occlusal
   plane; the measured good-gesture agreement), using a **local RNG seeded per tooth**
   (deterministic; must not disturb the global `np.random.seed(0)` the pipeline pins).
3. Re-seat the **winning variant only** (identification is fixed — we are measuring pose
   stability, not re-identifying), through the same rim-first seat + centre pass. Skip the
   slow best-fit ICP; keep the closed-form rim seat + depth + clocking + centre (fast, so
   K=8 is a few seconds).
4. Measure the spread of the K poses:
   - `pos_spread_mm` — p90 of position deviation from the shipped pose
   - `axis_spread_deg` — p90 of axis-angle deviation
   - `clock_spread_deg` — p90 of clocking deviation (coded caps)

Tight spread ⇒ the seat is robust to how precisely the doctor clicked ⇒ high confidence.
This is the intuitive "would a slightly different click give the same answer" question,
and it works for every input mode.

### 2. Fitzpatrick TRE prior (complementary, ≥3 marks)

Closed-form registration-error prediction at the implant platform from the mark geometry,
no re-seating:

`TRE²(target) ≈ (FLE²/N) · (1 + (1/3) Σ_k d_k² / f_k²)`

where N = mark count, d_k = target distance from principal axis k of the mark
configuration, f_k = RMS mark distance from that axis, FLE = fiducial localization error
(calibrate from re-click spread; start at 0.3mm). Target = implant platform centre (a
collar-height below the rim along the axis). Degenerate for a 2-mark centre+rim pair
(reported only when ≥3 marks exist); bootstrap is the primary signal there.

### 3. Confidence grade (combine)

Inputs: bootstrap spreads, `rim_agreement_mm`, `top_face_p90`, candidate margin
(`candidates_too_close`), `border_click_disagreement_mm`, TRE. Output grade:

- **high** — pose spread tight (pos < ~0.25mm, axis < ~3°, clock < ~8°) AND rim-seat
  tight AND top-face seated AND variant margin clear AND no disagreeing clicks.
- **medium** — one soft signal off.
- **low** — any hard signal off (unstable pose, high seat residual, riding top face,
  ambiguous variant).

Thresholds are **calibrated against ground truth** (see Validation), not guessed.

### 4. Gate integration

`domain/guidance.py` consumes the grade. A `ready`-level site additionally carries its
grade: "READY — high confidence (pose stable to X mm under click noise)". The gate policy
is unchanged (never blind auto-manufacture on real data); the grade lets the lab triage.

### 5. Reporting

- New row field `confidence`: `{grade, pos_spread_mm, axis_spread_deg, clock_spread_deg,
  tre_mm}`.
- Report line + a results-table chip (frontend — small, separate follow-up).

## Validation protocol (the load-bearing part)

1. **Correlation on known pose** — place-and-recover synthetic (pose known): confirm
   `pos_spread`/`axis_spread` correlate with the *actual* recovered-pose error
   (monotonic; report the rank correlation). If bootstrap spread does not track true
   error, the metric is rejected.
2. **Correlation on known variant** — the 4 labeled arches: high-confidence sites carry
   the correct variant; a genuinely ambiguous site (height twin) must NOT read high.
3. **Discrimination guard** — a deliberately imprecise gesture (marks jittered beyond
   click noise) must read a *lower* grade than a clean gesture on the same real site.
4. **Determinism** — per-tooth local RNG ⇒ byte-identical confidence across runs
   (guard: perturb ambient global seed, demand identical output).

## Components / files

- **New** `domain/confidence.py` — pure: pose-spread statistics, TRE closed form, grade
  thresholds. No IO, unit-tested.
- `pipeline/auto_flow.py` — the bootstrap loop, spread computation, grade call,
  `confidence` row field. The seat is **already decomposed** into reusable callables
  (`_cap_patch_roi`, `_rim_seat`, `_fit_circle_3d`, `_pinned_rim_seat`), so the bootstrap
  re-seats the winning variant by perturbing the marks and calling those directly — no
  refactor of the large `run_auto_case` body, and identification is never re-run.
- `domain/guidance.py` — consume the grade.
- **Tests** `tests/test_confidence.py` (grade logic, TRE, determinism) + additions to
  `tests/test_auto_flow.py` (bootstrap-correlates-with-error on synthetic; degraded
  gesture reads lower; determinism).

## Scope / non-goals

- Read-only: never changes the shipped pose or identified variant. No recalibration.
- Frontend chip is a small separate follow-up, not in this spec's worker scope.
- Does NOT attempt to beat the height-twin physics ceiling — it *reports* it as low
  confidence / declaration-required.
- Cost: K=8 lightweight re-seats of the winning variant only (~2–5s/site). If the live
  demo needs it faster, the full-confidence pass can be made opt-in/background — noted,
  not built here.

## Risks

- **Compute cost** on the live demo (K re-seats). Mitigation: winning-variant-only,
  skip best-fit ICP, K=8; opt-in escape hatch if needed.
- **Miscalibrated thresholds** presenting false "high confidence". Mitigation: thresholds
  are set from the ground-truth correlation, and the discrimination guard fails the build
  if a degraded gesture reads high.
- **Determinism** regressions from the bootstrap RNG. Mitigation: local per-tooth
  Generator, determinism guard test.

## Sequencing

This is Spec A. Spec B (ROI isolation + identification score recalibration on the upright
templates, optimized on the labeled arches) is a separate, calibration-bearing follow-up
with its own spec → plan cycle, and subsumes the pending recalibration backlog item.
