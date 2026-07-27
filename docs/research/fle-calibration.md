# Operator Click-Error (FLE) Calibration — 2026-07-18

Empirical fiducial localization error (FLE) study, mined from `reports/live-demo/run-history.jsonl`
(50 pipeline runs, single operator, 2026-07-14 22:20 → 2026-07-15 15:21, 9 case IDs). Answers
roadmap item #2 (`docs/research/alignment-confidence-roadmap.md`): replace the single-anecdote
click-noise anchor ("good border-click gestures agree ~0.33mm leave-one-out; one bad redo click
measured 0.89mm off") behind `_pose_stability_bootstrap`'s `sigma_mm=0.3` default
(`src/case_prep/pipeline/auto_flow.py`) with a measured distribution, and check the confidence
grade thresholds in `src/case_prep/domain/pose_confidence.py` for consistency with it.

## 1. Data inventory

`sites_in` on every logged run carries `center_mark`/`rim_mark` (a centre+rim pair) or
`rim_points` (a 3-6 point border-click gesture) — the exact marks sent to the pipeline for that
run. Grouped by `(case_id, tooth)`:

| Site | Raw `sites_in` entries | Distinct pair values | Distinct border (`rim_points`) gestures |
|---|---:|---:|---:|
| 276794487-zimmer-4.5 / t3 | 23 | 1 (all byte-identical) | 7 |
| 295811960-neodent-gm / t29 | 3 | 1 (all byte-identical) | 0 |
| 297589851-neodent-gm / t20 | 2 | 1 (all byte-identical) | 0 |
| cap6020-neodent-gm / t29 | 1 | 1 | 0 |
| cap6030-neodent-gm / t29 | 13 | 1 (all byte-identical) | 0 |
| cap7020-zimmer-4.5 / t3 | 3 | 1 (2 identical) | 1 |
| cap7030-zimmer-4.5 / t29 | 1 | 1 | 0 |
| neodent-gm / t4 | 3 | 1 | 1 (2 identical) |
| neodent-gm / t13 | 3 | 1 | 1 (2 identical) |
| zimmer-4.5 / t7 | 1 | 1 | 0 |

**Finding that reshapes the method: every pair-type (`center_mark`+`rim_mark`) submission in this
dataset is a byte-identical duplicate of the site's static `sites.json` curation, replayed on
every rerun — not a fresh operator click.** Cross-checked against
`docs/research/alignment-benchmark-results.md`'s data caveat ("every real site under
`data/real/scans/*/sites.json` carries a `(center_mark, rim_mark)` PAIR... never a `rim_points`
array") and the user's own re-click-pair-integrity note (a centre+rim pair is stored/replayed as
ONE measurement). Consequently **the pair channel supplies zero usable centre-click scatter** —
step 1's "distinct center_mark values" instruction returns n=1 per site everywhere, by
construction, not by chance. Two entries even carry non-identical `center_mark` under a
duplicated `rim_points` set (322-2 sessions) — that field turned out on inspection to be an
unrelated derived value (differs from both the pair's static centre AND the border centroid by up
to 1.3mm in z), not a raw click; it is excluded from the FLE calculation for the same reason.

**All usable repeat-click evidence comes from the border (`rim_points`) channel**: 10 independent
4-point gestures survive exact-duplicate dedup (rounding-level duplicates included, e.g.
`23:20:57`'s 3-decimal points match `22:34:09`'s to <0.001mm) — 7 repeats of the *same* physical
site (276794487-zimmer-4.5 t3, spanning both days) plus 3 singleton gestures on 3 other sites,
40 individual clicks total.

## 2. Method

1. **Per-position repeat-click scatter (primary).** For the 7 repeated gestures on the same
   site, each click was matched across gestures to one of 4 canonical clock positions by nearest
   angle about the site's fixed nominal centre. Per position, deviation = distance from that
   position's own (robust, median) centre across its 7 repeats — this is a direct, unamplified
   read of "how far does a re-aimed click at the same physical feature land from the last one."
2. **Within-gesture leave-one-out circle fit (xy-only cross-check).** For every one of the 10
   gestures (n=4 points each), fit a circumcircle (Kasa least-squares, the same method
   `test_auto_flow.py`'s rim-centre helper uses) through 3 of the 4 points and measure the 4th's
   radial residual. Works even for the 3 singleton gestures with no repeats.
3. **Within-gesture leave-one-out plane fit (3D cross-check).** Same leave-one-out idea, fitting
   a 3D plane instead of a circle — mixes xy and z, so treated as a corroborating signal, not the
   headline number.
4. **Slip flag.** Per step 1's instruction, any point >2mm (3D) from its position's robust centre
   is excluded from the core distribution and reported separately.

z is reported for completeness only; per the task brief, z is re-read from the scan surface by
the pipeline, so xy governs the bootstrap noise model.

## 3. Results

### Slips found

| Gesture (site, ts) | Position | xy dev | z dev | 3D dev | Disposition |
|---|---|---:|---:|---:|---|
| 276794487-zimmer-4.5 t3, `2026-07-14T22:28:02` | bin 0 | 1.64mm | 1.78mm | **2.42mm** | Excluded from core. This is the site's *first-ever* border-click submission in the log (22:28, before any repeat existed); z is ~1.8mm high (23.04 vs. siblings' 21.2-21.6mm) — consistent with a warm-up click landing on the cap's wall slope rather than its rim edge. |
| 276794487-zimmer-4.5 t3, `2026-07-15T10:49:17` | bin 3 | 0.52mm | 1.83mm | 1.91mm | **Kept in core** (<2mm). xy deviation is unremarkable (0.52mm, inside the normal spread); the deviation is almost entirely in z (23.51 vs. siblings' 21.25-21.68mm) — a mis-projected depth read from one viewing angle, not an xy aiming error. Since the pipeline re-reads z from the scan, this click cost nothing to alignment quality; flagged for completeness only. |

n=1 true slip (of 28 clock-position-matched clicks, 3.6%).

### Primary: per-position repeat-click xy scatter (occlusal plane), n=27 core / 28 all

| | n | p50 | p68 | p90 | max |
|---|---:|---:|---:|---:|---:|
| **Core (slip excluded)** | 27 | **0.317mm** | **0.459mm** | **0.605mm** | 1.677mm |
| All (slip included) | 28 | 0.341mm | 0.489mm | 0.769mm | 1.677mm* |

*max unaffected by slip removal — the largest single xy deviation (1.677mm, at
`2026-07-15T10:30:05`) was itself under the 2mm 3D slip bar (z deviation ≈0), so it stays in
core: a legitimate tail click, not a slip.

z scatter, core (n=27, for completeness): p50=0.038mm, p68=0.064mm, p90=0.380mm, max=1.833mm
(the max is the near-slip's z-only deviation above).

### Cross-checks (n=40, all 10 gestures pooled, unfiltered)

| Method | p50 | p68 | p90 | max |
|---|---:|---:|---:|---:|
| Leave-one-out circumcircle (xy only) | 0.225mm | 0.409mm | 0.768mm | 1.047mm |
| Leave-one-out plane fit (3D) | 0.314mm | 0.499mm | 0.909mm | 1.844mm |

Both cross-checks land in the same 0.2-0.9mm band as the primary measurement, despite measuring a
different thing (within-gesture self-consistency rather than cross-session repeat-click scatter)
— convergent evidence, not a repeat of the same number.

## 4. Sigma recommendation

`_pose_stability_bootstrap` applies the noise as an i.i.d. per-axis Gaussian
(`rng.normal(0.0, sigma_mm, size=(n_marks, 2))`), so the *radial* xy deviations measured above
follow a Rayleigh distribution with scale `sigma`. Inverting each percentile
(`sigma = r / sqrt(-2 * ln(1 - pct))`) against the three channels above:

| Channel | sigma @p50 | sigma @p68 | sigma @p90 | mean |
|---|---:|---:|---:|---:|
| Core repeat-click scatter (primary) | 0.269mm | 0.304mm | 0.282mm | **0.285mm** |
| All incl. the one slip | 0.290mm | 0.324mm | 0.358mm | 0.324mm |
| LOO circumcircle cross-check | 0.191mm | 0.271mm | 0.358mm | 0.273mm |

**Recommendation: keep `sigma_mm = 0.3`.** Three independent measurement channels, with and
without the one flagged slip, converge on a per-axis sigma of 0.27-0.32mm — the current default
sits almost exactly in the middle of that band. The prior anecdotal anchor (0.33mm / 0.89mm from
a single pair of observations) happened to land close to the truth, but that was luck, not
calibration; this is now n=27-40 clicks across 10 independent gestures on 4 real sites (2
implant systems, zimmer and neodent). A downward nudge to e.g. 0.28mm is not justified: the
sample is small enough (n=27 for the primary channel) that its own p90 has wide sampling
uncertainty, and 0.28 vs 0.30 is inside that noise — changing the constant would be false
precision, not a real correction. `auto_flow.py` was not edited (out of file scope for this
task); this is a recommendation for whoever owns that default.

## 5. Threshold decision (`pose_confidence.py`)

The existing `_POS_*` / `_AXIS_*` grade thresholds were calibrated against the *bootstrap's
output* p90 spread on real cases under this same `sigma_mm=0.3` (good pairs ~0.7-1.3mm/7-18deg,
sloppy ~1.6-2.5mm/16-48deg, per the file's own comment). Because this study **confirms** rather
than moves the input sigma that produced those output ranges, **the numeric threshold constants
are unchanged** — moving them now, without also re-running the bootstrap-output measurement they
were fit to, would decalibrate them relative to their own evidence.

What changed: `src/case_prep/domain/pose_confidence.py`'s threshold comment was rewritten to cite
this study's measured numbers and drop the "PRELIMINARY" / "not yet truth-calibrated [FLE]"
language for the FLE piece specifically — roadmap #2 (FLE input calibration) is now done.
Roadmap #7 (an independent ground-truth pass/fail line) remains open and is called out explicitly
in the updated comment; it is a different, larger validation effort (synthetic place-and-recover
plus a physical phantom) than this click-noise study, and out of this task's scope.
`tests/test_pose_confidence.py` needed no changes — no numeric constant moved.

## 6. Fitzpatrick TRE at the platform

Using the calibrated FLE (0.3mm) and a representative real 4-point border-click gesture
(`276794487-zimmer-4.5` t3, `2026-07-14T22:30:12`, an unflagged mid-tightness gesture, radius
≈2.0-2.6mm about the site centre) through `fitzpatrick_tre` in `pose_confidence.py`:

- At the fiducial centroid (the platform sits directly under the click ring, the common case for
  a healing-cap border gesture): **TRE ≈ 0.15mm** — matches the closed form's `FLE/sqrt(N)`
  exactly at `d_k=0` (N=4, FLE=0.3mm → 0.3/2 = 0.15mm).
- 1mm off-centroid (an angled or asymmetric prep): **TRE ≈ 0.158mm** — barely moves, because the
  gesture's own spread (≈2-3mm radius) is wide relative to a 1mm offset, which is exactly the
  geometry Fitzpatrick predicts (a wide fiducial ring stiffens the pose against off-centre error).
- A 2-click pair (centre+rim) cannot be scored by this formula at all (`N<3`); its expected error
  cannot be bounded the same way, which is itself the case for encouraging border clicks.

**The sentence for a lab:** *with 4 border clicks at this operator's measured precision
(FLE ≈ 0.3mm per axis), expect target registration error ≈ ±0.15-0.16mm at the implant platform —
under a single pair click, that bound is not measurable at all.*

## 7. Caveats (read before treating this as final)

- **Single operator, one day and a bit** (2026-07-14/15), 9 case IDs, one live-demo session —
  not a multi-operator, multi-day reproducibility study. The measured sigma is this operator's
  precision on this UI, not a population estimate.
- **Demo conditions**: these are pipeline-development runs, not supervised clinical clicks; some
  gestures are plausibly deliberate stress-tests (the task brief flags a "documented sloppy
  redo" as an example) rather than best-effort aims. The one flagged slip (§3) is consistent with
  a first-attempt warm-up click, not necessarily representative of steady-state clinical use.
- **n=27 core clicks is small** for pinning down a p90 to more than one significant figure — the
  sigma recommendation leans on convergence across 3 independent channels precisely because any
  one of them alone would be under-powered.
- **The centre-click (pair) channel supplied zero data** — every pair submission in this history
  is a cached replay of the static site curation, not an independent click (§1). This FLE
  calibration is therefore purely a **border-click** calibration; if the product ships a
  pair-only (no border-click) intake path in practice, its click-noise distribution is not
  measured here and may differ (a single point + a single radius point is a different motor task
  than tracing a ring).
- **Slips excluded from core, not from awareness**: 1 of 28 matched clicks (3.6%) exceeded the
  2mm 3D bar. That base rate is not itself calibrated (n too small) but says gross mis-clicks are
  not rare enough to ignore when reasoning about worst-case, only about the *typical* click this
  sigma models.
