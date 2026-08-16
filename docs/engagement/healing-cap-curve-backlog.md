# Healing-cap curve alignment — backlog and Loop playbook

2026-08-15 · executable queue for
[`healing-cap-curve-alignment-design.md`](healing-cap-curve-alignment-design.md).
Do not start P1 until `git status` is clean and the design has been read. Do
not duplicate marks-as-locators, island promotion already in the perfection
strategy, or §10-AT boolean/isolation work.

Owners: **alignment** (geometry), **backend** (detection record / BFF),
**frontend** (honest absence), **data-science** (any millimetre claim).

---

## P0 — stop the bleeding (human, not Loop)

| id | task | status | acceptance |
|---|---|---|---|
| P0.1 | Land the in-flight §10-AT working tree (crust excision, open-arch through-holes, apply-fires-run) | **done** 2026-08-15 `d015f7b` | working tree was the AT slice; freeze line still clean |
| P0.2 | Measurement probe + design spec | **done** 2026-08-15 `375178f` | `tests/test_probe_cap_curves.py` green; probe lives in `eval/` (not frozen `tools/`) |

Loop does not start until P0 is closed.

---

## P1 — cheapest geometry win

**P1.1 Pratt/Taubin replacing Kasa** (alignment)

Replace algebraic Kasa in `auto_flow._fit_circle_xy/_plane/_3d`,
`island._kasa`, `clock_signature._kasa`, `channel._circle_read` with Pratt or
Taubin. Same `O(n)` cost, no new dependency. Shadow-compare against the
doctor's measured rim radii (from `sites.json` `rim_mark`).

Acceptance:

- Partial-arc sites (Appendix A closure < 20/24) improve or hold radius vs the
  marked rim; full-circle sites (cap6030 24/24) do not regress.
- Pose on the 8 already-found sites moves by less than click-FLE noise
  (σ ≈ 0.3 mm) *before* promotion. First ship is shadow-only if the delta is
  even close.
- Narrow tests: the circle-fit unit tests in whatever module owns the new fit,
  plus `tests/test_island.py`. Not the 13-minute battery until the last edit.

---

## P2 — the actual curve extractor

**P2.1 Periodic-DP ring replacing `_ring_fit`** (alignment)

DP on the `(θ, r)` cylinder with `r_0 = r_{N_θ}`. Retire the 25-refit median
(`RADIUS_GRID_PHASES` × `RADIUS_CENTRE_JITTERS`) if the DP cost gap is the
reportable ambiguity instead of a silent coin flip. Keep the `IslandReading`
contract: unconverged readings carry no trusted centre.

Acceptance: cap6030 radius no longer flips 1.81 ↔ 2.64 mm from a 0.8 mm-degraded
seed; same closure metric as the probe; `SHADOW_ISLAND` consumes the new ring
and still does not move shipped poses (`test_island.py` zero-pose-movement
contract).

**P2.2 Per-bearing confidence** (alignment, then backend) — **done** 2026-08-15

Emit the DP cost margin per 15° bin. Dual-report next to
`capture_gate._rim_arc_check` until they agree on the fleet. One instrument
instead of two is the end state, not the first ship.

Acceptance: additive fields; pre-field records serve empty; statuses-walk test
stays green.

Delivered: `auto_flow.py` island row now includes `dp_gap_fraction` (0–1 float)
and `bearing_margin` (list of per-bin floats). Pre-field records already carried
`None` for both. Slow integration test assertion updated additively — the exact
key-set assertion is replaced with a superset check plus value-range guards.
SHADOW_ISLAND stays True; capture_gate NOT retired (dual-report phase).

---

## P3 — density as prior

**P3.1 Informativeness gate + additive prior on `find_cap_sites`** (alignment) — **done** 2026-08-15

Percentile-normalise local tessellation per file. If the field is flat, disable
the prior and say so. **Pin the t4 inversion as a test that the prior must
disable, not a test that it must find t4.**

Acceptance:

- `neodent-gm` t4: prior off (or weight ≈ 0), site still proposed by the
  existing rim-slab stack.
- Detection recall does not drop below 8/10 on this fleet.
- Recall gain, if any, is a bonus — not sold as 8/10 → 10/10.

Delivered: `CapSiteCandidate.density_prior_used: bool = False` (additive field,
defaults False for all existing callers). `find_cap_sites` accepts `faces:
Optional[np.ndarray]`. Gate: `_density_field_is_informative` (p90/p10 ≥ 1.5 of
density ratios across FPS candidates). Per-site label: ratio ≥ 1.0 at the
refined candidate xy AND field informative → `density_prior_used=True`. Inverted
density (ratio < 1.0, t4 case) → False. Extra FPS seeds from finest 5% face
centroids in the band when informative (additive only — no candidate removed).
`propose_sites` now accepts `faces`; `application/detection.py` passes
`scan.faces`. Tests: `test_density_prior_used_field_exists_and_defaults_false`,
`test_density_prior_false_on_uniform_mesh`, `test_inverted_density_disables_prior`
(@slow). Fast tests: 2 passed. No millimetre claim made — needs data-science.

---

## P4 — product honesty

**P4.1 Serve discriminator evidence** (backend, frontend) — **done** 2026-08-15

`rim_below_cusps_mm`, `void_ratio` (already on some records), plus
`density_prior_used`, DP gap fraction, per-bearing margin. Intake digest and
detection record. Honest absence renders nothing, never zeros.

Delivered: `CandidateEvidence` borrows density/DP from the matching proposal
(`None` when unmatched — never `False`/`0.0`). `DetectionRecord` /
`DetectionView` add `site_density_prior_used`, `site_dp_gap_fraction`,
`site_bearing_margin` (empty on pre-field documents). Intake
`curveHonestySentence` renders "density prior off" only when the served bool
is `false`; a null DP gap is no clause; a real `0` gap is "inferred across 0%".
Statuses-walk test stays green. Island still does not run at detect — DP
fields are `None` until a later island reading exists.

**P4.2 Hard capture-gate refusal at Intake** (backend, frontend) — **done** 2026-08-15

t7-class scans (rim occupancy ~0.54, collar at or below tissue, Appendix A
closure 9/24) refuse with chairside recapture copy while the patient can still
be scanned. The instruments already exist in `capture_gate.py`.

Acceptance: a synthetic starved rim is refused by name; a healthy cap6030-class
site is not.

Delivered: `_authorized_selection` 422s when
`session.detection.site_capture[tooth].verdict == "rescan"`, quoting the
gate's own recapture sentence (same copy Intake's banner already shows).
Missing detection is not a refusal. pass/marginal do not block. Declare
already surfaces the 422 as `runRefusal`.

---

## P5 — blocked on other people

| id | task | blocked on |
|---|---|---|
| P5.1 | Phantom plate back from the lab → true millimetre claims + doctor-vs-model calibration | lab turnaround ([`phantom-protocol.md`](phantom-protocol.md)) |
| P5.2 | One coloured PLY from a doctor's scanner → additive chroma term in `w` | a real coloured scan in `data/real/scans/` (BFF today refuses non-STL) |
| P5.3 | Client T&C / CRS text; payment provider; RealGUIDE import spike; N>2-site measurement | client / commercial |

Loop may *prepare* P5.3 scaffolding. It may not invent legal text or declare a
RealGUIDE seam green.

---

## Cursor Loop playbook

Cursor Loop (`/loop`) wakes the agent on a schedule or an event. It is a good
fit for **some** of this repo and a landmine for the rest. Two standing rules
in [`CLAUDE.md`](../../CLAUDE.md) will be violated by a naive
`/loop 5m run the tests` on the first tick:

- Never start a gate while files are still being written (pytest imports at
  collection; a mid-edit run is a 13-minute answer about code that no longer
  exists).
- Never start a second copy of a run already in flight.

**Do not use fixed-interval test loops.**

### Pattern that works — one dynamic loop, commit-per-tick

1. Human closes P0. Loop does not arm until `git status` is clean.
2. Arm **one** Loop whose prompt is:

   > Read `docs/engagement/healing-cap-curve-backlog.md`. Pick the top item
   > whose dependencies are met and which is not blocked on other people.
   > First actions: `ps` for an in-flight pytest/make, and `git status` for a
   > quiet tree. If either fails, exit doing nothing. Otherwise implement the
   > item test-first, run only that slice's tests (narrowest files), commit if
   > green, then re-arm.

   Unique sentinel (e.g. `AGENT_LOOP_WAKE_cap_curve`), tracked PID, stoppable.
3. Long gates (`cd apps/worker && make test`, `make rehearse`,
   `make verify-fleet`) are **event-woken**: the tick fires when the process
   exits, not every five minutes. The tick prompt still starts with `ps` and
   "is the tree quiet".
4. Inner red/green after a slice is coded: the **loop-runner** subagent
   (test/fix until green or stuck), not a second Loop. One Loop, one in-flight
   gate.
5. Promotion ticks (P1/P2/P3 going from shadow to shipped) require a human:
   `make verify-fleet` delta + data-science sign-off. Loop may *prepare* the
   scoreboard; it may not declare a millimetre win.

Each tick is independently recoverable because it commits. Keep ticks smaller
than the 19-file, 1,500-line slice that cost an hour just in the fix loop.

### Suggested Loop prompt (copy-paste)

```
/loop Read docs/engagement/healing-cap-curve-backlog.md. Pick the top unblocked
item. First: ps for in-flight pytest/make, git status for a quiet tree — exit
if either is dirty. Implement test-first, run only the slice's tests, commit
if green. Do not run make test or make rehearse unless this tick's item names
that gate, and then wait on the process instead of polling. Do not promote
shadow geometry to shipped poses. Do not edit apps/web or case_prep.server.
```

Use dynamic mode (no `5m`). After each commit, pick the next delay from
"is there an unblocked item?" — if yes, a short heartbeat; if the next item is
a long gate, arm a watcher on that process.

### What Loop must never do

- Start `make test` while files are being written.
- Start a second copy of a gate already in flight.
- Claim a millimetre improvement without data-science.
- Use the curve to crop/isolate (clinical-pipeline Stage 2 rejection).
- Add colour code before a coloured doctor scan exists in the fleet.
- Touch the freeze line.
