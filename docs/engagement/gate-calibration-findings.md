# Gate Calibration on Embedded-Real Ground Truth — Findings

*July 2026. Companion to the advisory-mode implementation (task #3) and the plan review.
Protocol and raw sweep: `scratchpad gate_calibration.py`, reproduced by
`tests/test_embedded_case.py::test_confidence_signals_separate_wrong_poses_after_isolation`.*

## Question

The grilling (must-fix #3/#4) documented the gate's worst failure: a **1.75 mm-wrong pose
PASSED** the synthetic-calibrated thresholds on real geometry. Can the confidence signals
(ICP fitness, inlier RMSE) be trusted on the embedded-real data class at all — and if so,
at what thresholds?

## Protocol

Three embedded-real cases (real Teeth3DS arch + real Certain CAD, degraded with sensor noise +
30% occlusion), each site registered twice: from a **good seed** (the truth) and from a
**poisoned seed** (2.5–4 mm off — the realistic operator-miss / detection-drift failure).
12 registrations: 7 position-correct, 5 wrong (>0.5 mm). Sweep `(min_fitness, max_rmse)`.

## Results

| Population | fitness | inlier RMSE | position error |
|---|---|---|---|
| Good poses (n=7) | **0.59 – 0.65** | 0.227 – 0.247 mm | 0.11 – 0.30 mm |
| Wrong poses (n=5) | **0.17 – 0.35** | 0.264 – 0.306 mm | 1.7 – 3.7 mm |

- **Clean separation**: every threshold pair down to the existing defaults (0.30 / 0.30 mm)
  achieves **0% wrong-pass at 100% good-pass** on this sample.
- One poisoned seed *recovered* to 0.13 mm (isolation + re-centering pulled it back) — a
  correct pose at fitness 0.46, i.e. the safe failure direction (would flag, not mis-pass).

## The finding that matters

**Body isolation fixed the false-confidence *mechanism*, not just accuracy.** The documented
1.75 mm PASS happened because a tissue-contaminated ROI let a wrong pose fit the surrounding
teeth well — surface fit was decoupled from pose correctness. With a body-only ROI, a wrong
pose has nothing to fit: fitness collapses (≤0.35). Surface confidence again *means* pose
confidence.

## Honest limits & decision

- **n = 12, one arch, one part, one poisoning mode.** This evidences the mechanism; it does
  not clinically validate the class.
- **Decision: ADVISORY MODE STANDS** for real/semi-real/embedded cases (fail-closed default in
  the manifest, wired through both gate sites). The gate's shadow verdicts (`would_pass`) are
  now evidenced-trustworthy, so the advisory log is a meaningful calibration instrument rather
  than noise.
- **Promotion path** (to a validated embedded/real gate): accumulate shadow-mode samples across
  arches/parts/failure modes; a future gate threads the separation band at ~`min_fitness 0.45`
  (margin to both populations). The regression test guards the band so a pipeline change that
  silently re-couples surface fit from pose correctness fails CI.
