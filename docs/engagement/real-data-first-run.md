# First Real-Data Run — Staged Workflow on a Real Intraoral Arch

**What ran:** the staged worker (stage 1 ingest → awaiting_seed → operator seed → stage 2 register/gate/package) on a **real Teeth3DS lower-arch scan** (82k vertices, non-watertight, arbitrary scanner frame ~100 mm off-origin), with scan bodies placed on it at **known** poses (a "semi-real" case — real mesh topology + exact ground truth; no public dataset has scan bodies in place).

This is the first time the pipeline touched real geometry, and it produced the signal the engagement was waiting for.

## Result

| Tooth | Position err | Axis err | Clocking err | ICP fitness | Gate |
|---|---|---|---|---|---|
| 20 | 1.14 mm | 0.69° | 0.7° | 0.49 | FLAG (clocking) |
| 21 | **1.75 mm** | 1.21° | 0.8° | 0.51 | **PASS** ⚠ |
| 30 | 1.78 mm | 0.93° | 0.1° | 0.49 | FLAG (clocking) |

## Findings (honest)

1. **The staged workflow runs end-to-end on real topology** and emits real per-stage artifacts: `stage1/normalized_scan.stl`, `stage2/{01_input,02_generated,03_intersection_AND,04_difference}.stl`, `result.json`. Real input in, real output out, inspectable at every stage.

2. **Axis and clocking recover well on real scans (~1° / <1°)** — encouraging for the hard rotational parts.

3. **Position drifts ~1–1.8 mm** (vs ~0.05 mm on synthetic). Cause: a scan body sitting on irregular real surface gives a weak axial constraint, and ICP fitness halves (~0.5) because the ROI mixes body + surrounding tissue. (Partly a harder-than-real artifact of placing bodies on tooth surface rather than a clean implant emergence.)

4. **The synthetic-calibrated gate produced a FALSE CONFIDENCE.** Tooth 21 **PASSED** the gate at **1.75 mm** position error — 9× the 0.2 mm clinical tolerance. The gate caught the other two only incidentally (clocking ambiguity), not the position error. **This concretely confirms the plan-grilling finding #3: thresholds tuned on one synthetic geometry do not transfer to real data.**

5. **Automatic localization is brittle on a dense real arch** (stage 1 detected 0/3 — the teeth themselves are protrusions). This is the documented Track-A weakness and exactly why operator-seeding is the design's reliable default; the operator seed rescued the case.

## What this means

The infrastructure, booleans, and registration math are sound — but **auto-seed must not be trusted on real cases until the gate is re-calibrated against real ground truth**, and the screw-channel position needs a tighter real-scan ROI. This is the "run real cases" gate doing its job: it turned an abstract risk into a measured number before any of it reached a patient.

**Next gated milestone (unchanged by this, reinforced):** real-scan clear-rate measurement + threshold re-calibration on real ground truth, and the RealGUIDE-import seam spike. Run auto-seed in **shadow/advisory mode** (compute, always route to human, log what it *would* have passed) until the real false-confidence-rate is measured near zero.

## Reproduce

```bash
cd apps/worker
# with a real arch (OBJ/STL) you provide or download (e.g. Teeth3DS):
.venv/bin/python -m case_prep.cli workflow --real-arch <arch.obj> --implants 3 --retention screw
# -> reports/workflow/work/stage1/ and stage2/  (per-stage real artifacts)
```
