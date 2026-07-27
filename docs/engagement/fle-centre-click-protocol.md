# Centre-Click FLE Study — Operator One-Pager

**What this is:** a ~10-minute clicking exercise, done once (or occasionally, to re-check
yourself), that turns "we assume centre clicks are about as precise as border clicks" into a
measured number. It costs 10 minutes of normal clicking and produces a calibrated confidence
input instead of an assumption.

## Why 10 minutes of clicking buys a calibrated number

The alignment pipeline's confidence grade is driven by a bootstrap that perturbs your marks by a
small random amount and checks how much the resulting pose wobbles (`sigma_mm=0.3` in
`auto_flow.py`). That `0.3mm` figure was measured from real repeat clicks — but only from the
**border-click** channel (tracing several points around a cap's rim). Every recorded
**centre-click** (⊕) submission in the system's history turned out to be a byte-identical replay
of a stored value, never an independent click — so the centre channel has *never actually been
measured* (see `docs/research/fle-calibration.md`, section 1).

That matters because a centre click is a different physical action from a border trace: it
resolves through a hit-anchored ball percentile aimed at the cap's screw-recess hole, not a
traced ring. It plausibly has its own precision — maybe tighter (a single well-defined hole to
aim at), maybe looser (no averaging across multiple points). Nobody knows until it's measured.
This study measures it, on real cases, with your real clicking behaviour — not a guess.

## The exact protocol

1. Run `tools/fle_study.py instructions` — it prints the current `run-history.jsonl` line count
   (your starting point) and the full protocol below, so you always have the exact numbers to
   hand.
2. For each of the study's 3-4 real demo cases:
   - Open the case in the live-demo UI and step through to **step 3 (Confirm)**.
   - Click **⊕ centre** FRESH, aiming genuinely at the cap's top centre.
   - Press **"Recompute alignment"** — every Recompute logs the exact gesture to
     `run-history.jsonl`, which is what the analysis reads.
   - Repeat click-and-recompute **6-8 times** for that case.
   - *Optional, bonus data:* also re-click the rim mark each round before Recompute — this
     feeds the same analysis for the rim (pair) channel too.
3. **Aim genuinely each time.** Don't try to hit the same pixel twice, don't slow down or speed
   up from your normal pace, and use whatever camera angle you'd naturally use (rotate between
   clicks if that's normal for you). The study is only honest if it measures your real operating
   precision — forced precision or forced repetition would measure something else entirely and
   mis-calibrate the number that comes out.
4. When done (24-32+ fresh centre clicks across the cases), run the analysis (below).

Total operator time: about 10 minutes for 4 cases x 6-8 clicks, at a normal working pace.

## The two commands

```bash
cd apps/worker

# 1. Print the protocol + your starting run-history line count
.venv/bin/python tools/fle_study.py instructions

# ... go click, per the printed protocol ...

# 2. Analyze everything logged since your starting point (dry-run: prints only)
.venv/bin/python tools/fle_study.py analyze --after-line <N>

# Once you're happy with the result, append it to the calibration doc
.venv/bin/python tools/fle_study.py analyze --after-line <N> --write
```

`analyze` also accepts `--since <ISO timestamp>` instead of `--after-line`. With neither flag it
scans the entire history file (useful as a sanity check — it should report mostly-or-entirely
excluded curated replays until a real study has been run).

`--write` is required to touch anything on disk. Without it, `analyze` only prints — it never
appends to `docs/research/fle-calibration.md`, which is owned by the original border-click study.
The convention is to append a clearly dated `## Centre-click channel (study of <date>)` section;
existing content in that file is never modified.

## What the output means

- **Exclusions are the whole point.** `analyze` throws away three kinds of non-clicks before
  counting anything as real data:
  - **Curated replays** — a mark exactly matching the site's stored `sites.json` value (i.e. no
    click happened at all, just a cached/default submission).
  - **Duplicate runs** — the same mark resubmitted on a consecutive Recompute (pressing the
    button again without touching the mark).
  - **Border-derived artifacts** — when a submission includes border-click points
    (`rim_points`), its accompanying centre value is a leftover derived number from a different
    code path, not a centre-click aim, and is excluded from the centre channel for that reason
    (this is the trap the original border-click study documented and this tool guards against
    automatically).
- **Per-site table**: for each case/tooth, how many fresh clicks survived, how many were
  excluded (and why), and the resulting p50/p68/p90/max scatter (in mm, in the occlusal xy
  plane) about that site's own click cluster. Sites with fewer than 4 core clicks are marked
  **insufficient** — reported for transparency, not used to anchor a conclusion.
- **Slips**: any click landing more than 2mm from its site's cluster is flagged as a slip,
  reported separately, and excluded from the core scatter (a gross mis-click, not typical
  precision) — same rule the border study used.
- **Pooled numbers + implied sigma**: all sites' core deviations pooled into one distribution,
  then inverted through the Rayleigh relationship (`sigma = r / sqrt(-2 * ln(1 - pct))`, the same
  method the border-click study used) to get a per-axis Gaussian sigma comparable to the
  bootstrap's `sigma_mm` parameter.
- **Verdict**: whether the measured centre-click sigma sits within about 15% of the current
  `0.3mm` default ("holds") or implies a different value ("recommendation only — no production
  default is changed by this tool"). Turning a recommendation into an actual code change is a
  separate, deliberate step outside this tool's scope.
- **Rim-click bonus section**: the same analysis applied to `rim_mark`, since re-clicking the
  rim each round is optional but free extra data for the pair channel.
- **Border (`rim_points`) gestures**: counted and listed for awareness, but not re-analyzed here
  — that channel already has a dedicated, larger calibration in
  `docs/research/fle-calibration.md`.
- **"no new study data — run `instructions` and click first"**: printed when zero fresh clicks
  of any kind are found in range. This is the expected, honest result before anyone has actually
  run the protocol — it proves the exclusion logic is doing its job, not that something is
  broken.
