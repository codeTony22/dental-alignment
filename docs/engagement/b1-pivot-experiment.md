# B1 — the controlled repeat: operator scatter vs pivot parallax

2026-08-13 · the first workstream-B experiment (§10-AH / clinical-pipeline-plan
Stage 3). Requires ~15–20 minutes of the client at the tool. Nothing ships from
this document; it produces the NUMBERS that decide whether the re-anchoring
lever proceeds.

## The question

Scan-side azimuths are measured about the TEMPLATE's rim centre. The scan's own
ring centre sits 0.25–0.38 mm away from it on the measured fleet (the ring
offset e). If clicks are read about the wrong pivot, a click at rim radius r
carries a geometric azimuth bias up to asin(e/r) — worst case ~14° at our rim
radii, which is the size of real observed rotation disagreements. But the same
disagreement could also be plain operator click scatter. One number separates
them: the SPREAD of repeated clicks on one feature. Scatter is random; parallax
is a consistent offset. We cannot tell them apart from single clicks — only
from repeats.

## Setup (operator: the client)

- One case, one site, one pose. Any case whose cap shows ONE clearly visible
  feature (a code notch, a rim landmark). Do not rotate, re-run, or adjust the
  case during the experiment — the pose must stand still.
- The Adjustment stage's point-pair tool (Fit by points).

## Procedure — 10 repetitions

For each repetition, 1 through 10:

1. Place ONE pair on the SAME feature: centre mark + the feature mark, exactly
   as in normal work. Do not apply the fit.
2. Open Numbers & log and press the copy button. Paste the digest into a
   message (or a running document) labeled with the repetition number.
3. Remove the pair (centre and rim marks are one measurement — always remove
   the pair as a whole, never one half).
4. Repeat.

Send us the 10 digests. That is the whole experiment. If a placement feels
misclicked, finish it anyway and note the number — a known-bad rep is data;
a silently redone one is not.

## Analysis (ours) and the decision rule

From the 10 digests: the per-rep measured azimuth of the same feature →
operator scatter σ and the mean. From the run's own record: the measured ring
offset e and the feature's radius r → the parallax prediction asin(e/r) with
its direction.

- If the mean offset is consistent with the parallax prediction in sign and
  size, and exceeds 2σ/√10 — parallax is CONFIRMED as a real bias, and the
  lever proceeds: scan azimuths re-anchor about the scan's own measured ring
  centre. That change lands at the measurement fold, gated by
  `make verify-fleet` before/after on the whole fleet — never tuned on this
  one case.
- If the spread swallows the offset — the disagreement is operator scatter;
  the honest lever is the A-track (more pairs per fit, the A1 caution), and
  re-anchoring is dropped without being built.

## What we will never do with this data

No retroactive rewriting of historical evidence (the re-click-pair doctrine:
corrupted or superseded pairs are fixed at the source, never self-corrected by
the backend). The experiment changes how FUTURE measurements are read, if it
changes anything at all.
