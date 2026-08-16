# Blind-detection scoreboard — the client's RANSAC idea, measured (2026-08-16)

The client relayed their partner's RANSAC/Open3D script thread and asked to
incorporate the approach "to tackle that use case" — the BLIND lane: a scan
with no declared sites, or the missed-cap search. This document is the
measurement that decision rests on. The instrument itself is
`case_prep/adapters/blind_candidates.py` (pinned by
`tests/test_blind_candidates.py`); nothing is wired into `detect()` yet —
the wiring is queued behind the complementarity measurement below.

## Method

Nine real scans (`data/real/scans/doctor-*`), ten truth sites read from each
case's LATEST landed run's `implant.json` (position + axis). A candidate
"finds" a site when the truth position sits within **3.0mm** of the
candidate's axis line — the production detector's own ±3mm refinement basin
— with axis within 30°: the gate for a SEED, not a verdict. Harness scripts
live in the session scratchpad; the numbers below are from the final
configurations.

## The instrument, round by round (what was measured, not guessed)

1. **Two-point cross-product axes** (the script thread's own shape): found
   the cap7030 wall at 1.10mm but with a 47° axis — two noisy normals give
   a noisy axis. 148s/scan.
2. **Patch-seeded normal-covariance axes** (a cylinder wall's normals lie ⊥
   its axis): 8s/scan, axis errors collapsed — but caps LOST to natural
   tooth walls (molars carry short near-cylindrical bands too).
3. **The recess-void discriminator** (a cap's core dips at/below its own
   wall top; a tooth's cusp rises): killed 5 of 8 false positives on
   cap7030 — and, measured next, EXECUTED the domed neodent caps, whose own
   revolute dome rises exactly like a cusp. 4/10 fleet.
4. **The dome allowance** (a cap's dome is revolute about the fitted axis —
   8 azimuth sectors of core heights agree; a cusp field is lopsided):
   no fleet change alone — the neodent misses were dying EARLIER.
5. **Catalog-radius centre-only fits**: the real neodent killer was
   partial-arc ballooning — cap6020's 1,895-point machined ring at r≈2.6
   fit free at r=3.33 with the centre 4.3mm off (draped tissue leaves a
   partial arc; a free circle fit balloons). Fitting ONLY the centre at
   discrete catalog radii cannot balloon. 4/10 again — but a DIFFERENT
   4: gained 297589851-20 (the isolation stress case) and cap6030, lost
   295811960 and cap7020.

## The numbers (final round; union across rounds in brackets)

| case | truth | found @3mm | best dist/angle | spurious |
|---|---|---|---|---|
| 276794487-zimmer-4.5 | 3 | yes | 0.39mm / 6.6° | 4–7 |
| 295811960-neodent-gm | 29 | round-3 yes, round-5 no | 1.20mm / 18.7° | 6–8 |
| 297589851-neodent-gm | 20 | round-5 yes | — | 7–8 |
| cap6020-neodent-gm | 29 | no (signal present: 1,895-pt ring @r2.6) | — | 7–8 |
| cap6030-neodent-gm | 29 | round-5 yes | — | 6–7 |
| cap7020-zimmer-4.5 | 3 | round-3 yes (0.19mm / 2.3°), round-5 no | — | 7–8 |
| cap7030-zimmer-4.5 | 29 | yes | 2.37mm / 19.9° | 3–7 |
| neodent-gm | 4, 13 | no | — | 8 |
| zimmer-4.5 | 7 | no | — | 8 |

**Single configuration: 4/10. Union across configurations: 6/10 distinct
sites. ~7 spurious candidates per case. ~10s per scan.** The wall-signal
autopsy says five of the six single-round misses carry substantial machined
ring signal — they are lost to configuration trade-offs, not absent.

## Verdict

- **As a detector: no.** The production density/rim-slab detector's own
  fleet record (misses 2 of 10, per `RunSelection`'s marked_centers note)
  outranks any single configuration of this instrument.
- **As a SEED PROPOSER: promising, and that is the honest shape of the
  client's idea here.** Seeds are cheap (~10s), multiple configurations can
  all contribute, and the production rim-slab refinement — which already
  judges every candidate the current proposer emits — would keep the true
  positives of EVERY round and kill the spurious. Two of tonight's hits are
  sub-0.4mm, far better than a seed needs.
- **Template-matched work is untouched**: everywhere a variant is declared
  or identified, the §10-AT front-1 doctrine stands — this lane exists only
  where there is no template to match.

## Queued (measurement-gated, in order)

1. **Complementarity**: per-tooth found/missed of the PRODUCTION detector
   across this same fleet (its two documented misses by tooth), so the
   blind seeds' added value is a number, not an argument. Blocked tonight:
   re-running `propose_sites` in-harness proved pathologically slow
   (30+ CPU-min on one case that production detects in seconds — an
   unexplained discrepancy worth its own measurement), and today's reset
   sessions carry no stored proposals to score.
2. **The wiring slice**, if complementarity earns it: blind seeds feed the
   same evidence loop in `detect()` (the scout-mapped plug point at
   detection.py's proposal loop), deduped at the 8mm separation rule,
   carrying an additive `proposer` provenance field (worker DetectedSite →
   BFF DetectedProposal/View, all additive-optional). `find_cap_sites` and
   `propose_sites` stay untouched — both are shared with the frozen demo.
3. **A calibration harness**, replacing tonight's hand-tuning: grid-search
   the gate space scored on the fleet, per cap family — the round-3/round-5
   oscillation is exactly what a scored search resolves.

## Scan-body footnote

For TALL, fully-exposed scan bodies (the client's partner's actual target),
this technique is on much firmer ground than for tissue-covered healing
caps — if their lab workflow ever feeds us scan-body scans, the same
instrument should be re-scored on that input before any further tuning.
