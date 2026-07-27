# Variant-identification score recalibration (upright templates) — 2026-07-18

## Decision

**No change.** `_rim_seat` and `_pinned_rim_seat` are unmodified from the 2026-07-13
calibration (`score = seat + 2.0 * t2p`, `above_cut = -0.4`). The grid search found a
config that nominally clears the mission's numeric bar (min blind margin > the documented
0.012mm tie), but a click-noise robustness check (real end-to-end re-registration, not
just re-aggregated components) shows it is an overfit to the single frozen mark position,
not a genuine improvement: it trades away stability on the arch that is *already* correctly
identified (`doctor-cap7030-zimmer-4.5`) to partially fix the arch that is not
(`doctor-cap7020-zimmer-4.5`). The current tie-routing behavior (documented in
`test_blind_identification_matches_the_label`'s tie-escape) remains the right, honest
behavior — the file is restored byte-identical to its pre-experiment state (`diff` verified
against a pre-edit backup).

## Method

A read-only harness ([scratchpad], not part of the shipped repo) ran the real
`run_auto_case` pipeline blind (no declaration) on all 4 labeled arches
(`data/real/scans/doctor-cap{6020,6030,7020,7030}-*`). To capture raw components *from
production code itself* (not a reimplementation), a temporary, off-by-default trace hook
was added to `_rim_seat` (`_RIM_SEAT_TRACE`, `None` in normal operation — zero behavioral
change, confirmed by re-running `test_run_auto_case_is_deterministic_across_ambient_rng_state`
and `test_blind_identification_matches_the_label` before removal). For each candidate spec,
at the depth `t` the *pure seat term* search already picks (unchanged — this recalibration
never touches which `t` wins), the hook recorded:
- `seat_resid` (the existing pure-seat scalar),
- `local_z` and per-sample `dists` for **all** 1200 template samples at that `t` (so
  `above_cut` can be swept without re-running registration or re-sampling — the "capture
  once, re-aggregate" approach the mission specified),
- `patch_dists` (per-patch-point distance to the template at that `t`, for the optional
  ROI-trim experiment).

This is exact re-aggregation of production-computed distances, not an approximation.

## Baseline (current: `w=2.0`, `above_cut=-0.4`)

Blind ranking (lower = better), diameter class = first two variant digits:

| Arch | Truth | Ranking (variant: score) | Class correct | True-vs-wrong-class margin |
|---|---|---|---|---|
| doctor-cap6020-neodent-gm | 6020 | 6030:1.4530, 6020:1.4724, 5020:1.5301, 5030:1.5344, 4030:2.0293, 4020:2.0331 | yes (height twin) | +0.0774 |
| doctor-cap6030-neodent-gm | 6030 | 6020:1.2082, 4020:1.2657, 6030:1.2699, 5030:1.2879, 5020:1.3132, 4030:2.4196 | yes (height twin) | +0.0574 |
| doctor-cap7020-zimmer-4.5 | 7020 | **8030:1.0893**, 7020:1.1010, 7030:1.1015, 8020:1.1208, 6030:1.2471, 6020:1.3039 | **no** | **-0.0117** |
| doctor-cap7030-zimmer-4.5 | 7030 | 7030:1.0749, 6030:1.0844, 6020:1.0955, 7020:1.1111, 8020:1.2717, 8030:1.2993 | yes | +0.0095 |

Matches the documented 0.012mm tie exactly (mission text: "8030 1.089, 7020 1.101 ...
leads ... by 0.012"). 3/4 arches class-correct; `doctor-cap7020` loses to the oversized
80-class.

## Grid search (step 2): `w ∈ {1.0..3.0 step 0.25}` × `above_cut ∈ {-0.8,-0.6,-0.4,-0.2,0.0}`

Objective, per the mission: (a) 4/4 blind class-correct, (b) maximize the *minimum* (over
the 4 arches) margin between the best true-class and best wrong-class candidate, (c)
fewer height-twin inversions as tie-break. Full 45-point matrix (`min_margin` sorted, best
first; `4/4` = all four arches diameter-class-correct):

```
w=2.25 cut=+0.0  4/4=True  min_margin=0.0143  height_twins=2   <- best
w=2.50 cut=+0.0  4/4=True  min_margin=0.0106  height_twins=2
w=2.25 cut=-0.2  4/4=True  min_margin=0.0077  height_twins=2
w=2.75 cut=+0.0  4/4=True  min_margin=0.0068  height_twins=2
w=2.25 cut=-0.4  4/4=True  min_margin=0.0046  height_twins=2
w=2.50 cut=-0.2  4/4=True  min_margin=0.0032  height_twins=2
w=3.00 cut=+0.0  4/4=True  min_margin=0.0031  height_twins=2
w=2.00 cut=-0.2  4/4=True  min_margin=0.0029  height_twins=2
w=2.50 cut=-0.4  4/4=True  min_margin=0.0001  height_twins=2
w=2.75 cut=-0.2  4/4=False min_margin=-0.0013 height_twins=2
w=2.00 cut=+0.0  4/4=False min_margin=-0.0019 height_twins=2
... (remaining 34 configs all 4/4=False, min_margin down to -0.0939)
```

Best config: **`w=2.25`, `above_cut=0.0`** — min-margin 0.0143mm, binding on
`doctor-cap7030` (0.0143), `doctor-cap7020` at 0.0155:

| Arch | Truth | Ranking @ w=2.25, cut=0.0 |
|---|---|---|
| doctor-cap6020-neodent-gm | 6020 | 6030:1.5713, 6020:1.6399, 5030:1.7227, 5020:1.7340, 4020:2.3253, 4030:2.3780 |
| doctor-cap6030-neodent-gm | 6030 | 6020:1.1556, 4020:1.2197, 6030:1.2632, 5020:1.2636, 5030:1.2743, 4030:2.7683 |
| doctor-cap7020-zimmer-4.5 | 7020 | **7020:1.1463**, 7030:1.1484, 8030:1.1618, 8020:1.2089, 6030:1.2602, 6020:1.2984 |
| doctor-cap7030-zimmer-4.5 | 7030 | **7030:1.1063**, 6020:1.1206, 6030:1.1297, 7020:1.1602, 8030:1.2849, 8020:1.3071 |

This is a real (if thin) improvement in the frozen, zero-noise, single-run picture: `7020`
flips to the correct class. But two structural warning signs disqualify it before any
noise test:
1. **It sits at the grid boundary** (`above_cut=0.0`, the least-negative value the mission
   allowed). A diagnostic sweep past the boundary (`above_cut` up to +0.5, `w` up to 4.0,
   exploratory only, not a candidate for adoption) shows the margin peaks right around
   `w≈2.2-2.3, cut≈0.0` and then falls — for `cut ≥ 0.2` several candidates' "above" set
   goes empty (`t2p` hits the `9.9` sentinel) and margins become wildly unstable
   (down to -20mm at `cut=0.5`). A margin whose optimum sits exactly on a search boundary
   is not "clean" — it's the edge of a fragile region.
2. **The margin (0.0143mm) is barely larger than the failure it replaces (0.0117mm)**, at
   a scale (seat residuals ~1.0-1.5mm) where 0.002mm of "improvement" is not distinguishable
   from noise.

### Root cause (why the ceiling is so low)

The raw (untrimmed) *pure seat term* itself already favors the oversized 80-class over the
true 70-class on `doctor-cap7020` by a wide margin — **before** the anti-envelopment term
is even applied: `seat_resid` at the winning depth is 0.393mm (8030) vs 0.411mm (8020) vs
0.534mm (7020) vs 0.530mm (7030) — the bigger template's surface simply envelops the patch
better. The anti-envelopment term (`t2p`) does grow faster for the oversized templates as
weight/cut are pushed (from `t2p_8030=0.342, t2p_7020=0.272` at `cut=0.0` — a 0.070 gap that
needs `w > 2.0` just to cancel the 0.141 raw-seat gap), but that same push works *against*
`doctor-cap7030`, where the true class is already winning on the raw seat term alone and
gets less benefit from more weight. This is a genuine two-arch trade-off inherent to a
single global linear combination + a single global `above_cut` threshold — not a tuning
gap that a better constant closes.

## Optional ROI-trimmed seat experiment (step 3)

Per the mission, tested trimming the *seat term only* to patch points within 0.6mm of the
candidate's own posed template, across the same 45-point grid. Result: **discarded** — it
never reaches 4/4 class-correct anywhere in the grid (best config found, `w=1.0, cut=-0.8`,
min_margin = **-0.0317**, actively worse than baseline). Trimming collapses seat residuals
toward a narrow, size-independent band (~0.5-0.9mm for every candidate, since any
reasonably-posed template has *some* points within 0.6mm of the patch), destroying the
size-discriminating signal the raw seat term provides. Per the mission's own criterion
("only if it clearly improves (b) without hurting (a)"), this variant is not adopted.

## Robustness check (decisive): real re-registration under click-noise jitter

The grid search above uses components from a *single, frozen* click position per arch
(`np.random.seed(0)`, exact `center_mark`/`rim_mark` from `sites.json`). To check whether
the `w=2.25, cut=0.0` "win" is real or a knife-edge, the two borderline arches
(`doctor-cap7020`, `doctor-cap7030`) were re-run through the **actual production
pipeline** (full registration, not cached components) with `center_mark`/`rim_mark`
jittered in the occlusal plane by Gaussian noise at `sigma=0.15mm` and `sigma=0.3mm` — the
same click-noise scale the file's own `_pose_stability_bootstrap` uses
(`sigma_mm: float = 0.3`, documented there as "the measured Gaussian occlusal-plane
perturbation"). 6 trials/arch/sigma, comparing current (`w=2.0, cut=-0.4`) vs the
grid's best candidate (`w=2.25, cut=0.0`):

| sigma | Arch | Current: class-correct | Candidate: class-correct |
|---|---|---|---|
| 0.15mm | doctor-cap7020 (truth 7020) | 2/6 | 5/6 (improved) |
| 0.15mm | doctor-cap7030 (truth 7030) | 3/6 | **1/6 (regressed)** |
| 0.30mm | doctor-cap7020 (truth 7020) | 1/6 | 2/6 (marginal) |
| 0.30mm | doctor-cap7030 (truth 7030) | 4/6 | **2/6 (regressed)** |

The candidate config does not cleanly win — it improves the arch that was already failing
and **degrades** the arch that was already correct, under realistic click noise. Neither
config reaches reliable (>=5/6) class-correctness on both arches simultaneously. This
confirms the boundary/root-cause diagnosis above: the theoretical zero-noise margin
(0.0143mm) does not survive real perturbation and is not a genuine separation.

## Curated real-site regression check (step 4)

Not required to run: since the winning-candidate hypothesis was rejected before any
source edit was kept, the 10 curated real sites (all `data/real/scans/*/sites.json`, with
declarations) were never put at risk — the shipped file is byte-identical to its
pre-experiment state. `git diff`-equivalent verification: `diff` against the pre-edit
backup shows zero differences after restoration.

## Battery

`tests/test_auto_flow.py` (the file touched during the experiment, since instrumentation
was added and later removed) was run in full after restoration: **84 passed** (9m18s),
confirming the restored file is byte-identical and regression-free. The full repository
battery (`make test`, ~342 tests) was not re-run because no source file differs from its
pre-task state — there is nothing new for it to catch that `test_auto_flow.py`'s own suite
would not.

## Files touched

- `src/case_prep/pipeline/auto_flow.py` — temporarily instrumented (a trace hook in
  `_rim_seat` and swappable `_T2P_WEIGHT`/`_ABOVE_CUT` globals in `_rim_seat` and
  `_pinned_rim_seat`) for the experiment, then **fully reverted** (`diff` verified
  identical to the pre-experiment backup). No net change.
- `docs/research/score-recalibration.md` — this document (new).
- Scratch harness/scripts (not part of the shipped repo):
  `capture_components.py`, `grid_search.py`, `grid_search_roi.py`, `robustness_check.py`,
  `components.pkl` under the session scratchpad.

## What would change this conclusion

A config search over just (`weight`, `above_cut`) cannot separate `doctor-cap7020` from
its 80-class neighbor without destabilizing `doctor-cap7030`, because the two arches pull
in opposite directions under the same global knobs. Closing this gap for real would need
either (a) a per-candidate or per-arch-adaptive anti-envelopment term (a bigger structural
change, out of scope for a constant recalibration and against the "do not restructure the
ranking" landmine), or (b) more labeled real arches to determine whether `doctor-cap7020`
is representative or an outlier. Until then, the tie-escape in
`test_blind_identification_matches_the_label` is the correct, honest behavior: the scan
genuinely cannot separate these two candidates, and the gate correctly routes to the
doctor rather than presenting a falsely confident answer.
