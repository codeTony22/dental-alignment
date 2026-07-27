# Phase 2A Spike — Findings & Engagement Record

**Deliverable:** the 2A de-risk spike (per [`technical-design-build-guide.md`](../technical-design-build-guide.md) M2 and [`phase2a-automated-case-prep-plan.md`](../phase2a-automated-case-prep-plan.md) §11).
**Question answered:** *Is Phase 2 automation technically possible for this client, and on what slice of the caseload?*
**Status:** spike complete on synthetic ground truth; ready to re-run on the client's real scans.

This is the chargeable record of the research, experimentation, and artifacts produced. It maps engineering effort to evidence so the work is auditable and the go/no-go is defensible.

---

## 1. Verdict

**Phase 2 case-prep automation is feasible.** The full chain — count → localize → align → recover 6-DoF implant pose (position, axis, and clocking) → confidence-gate — runs end-to-end, deterministically, and recovers poses to **well inside clinical tolerance on clean captures**, while **safely flagging degraded captures rather than passing them blind**.

| Scenario | Clear-rate | False-confidence | Recovered error (worst) |
|---|---|---|---|
| Cement-retained, clean | **100%** | **0%** | 0.074 mm / 0.28° |
| Screw-retained, clean (incl. clocking) | **100%** | **0%** | 0.067 mm / 0.66° |
| Screw-retained, heavy noise + 40% occlusion | 0% (all flagged) | **0%** | flagged to manual |

The decisive safety number — **false-confidence-rate (auto-passed yet out of tolerance) — is 0% in every scenario.** That is the property a clinical-safety gate must have, and it holds under deliberate degradation.

These figures are measured against **ground truth** on an adversarial synthetic dataset (noise, partial capture, a gingiva surface, near-rotational symmetry). The same pipeline and report run unchanged on real client cases once scans + scan-body libraries + ground truth are supplied — that run produces the **clear-rate on the real caseload**, which is the number that gates funding 2B.

## 2. What was researched & experimented (the chargeable core)

1. **Environment & toolchain feasibility.** Confirmed the open geometry stack (Open3D + trimesh + numpy/scipy) installs and runs on the target platform. **Finding:** Open3D 0.18's `registration_icp` **segfaults** on this macOS-arm64 wheel (reproduced in isolation, exit 139, both point-to-point and point-to-plane). **Resolution:** implemented an in-house, dependency-light **trimmed point-to-point ICP** (numpy + scipy KD-tree) — deterministic, fully unit-tested, and portable. This removed a hard external dependency from the critical path and is itself a de-risking result.
2. **Localization without ML.** Height-above-gingiva clustering + PCA axis seeding locates each scan body using only the declared count as a prior (Track A geometric). Calibrated the above-gingiva threshold and ROI extraction after finding that a naïve threshold captured only the body tops (wrong axis) and that omitting the base cap left the pose axially under-constrained.
3. **Registration accuracy.** Multi-start ICP about the recovered axis aligns the known library scan-body mesh; position+axis recovered to ~0.03–0.07 mm / 0.2–0.7° on clean captures — at the level the literature reports for careful best-fit overlay.
4. **Clocking — the irreducibly hard part.** Whole-surface RMSE was shown to be a **weak** clocking discriminator (the flat is a small fraction of the surface). Implemented an **explicit anti-rotation-feature residual** (geometry-agnostic: the indented feature inside the round envelope), compared at the best clock vs a rigid 180° flip. This produced real separation (clean ≈ 1.7–1.8× vs degraded ≈ 1.3×) and a calibrated threshold that passes confident clocking and flags ambiguity.
5. **Safety-gate calibration.** Thresholds (fitness, RMSE, clocking ratio, multi-implant consistency, count reconciliation) were tuned against ground truth so that confident-but-wrong never passes. Count mismatch (over- or under-detection) reconciles against the declaration and flags the case rather than silently dropping or inventing a site.

## 3. Artifacts produced (per run)

Each pipeline run writes a timestamped folder under `apps/worker/reports/`:
- **`accuracy-report.json` / `.html`** — per-implant recovered pose, error vs ground truth, gate decision, and the headline clear-rate / false-confidence-rate.
- **`feasibility-memo.md`** — the auto-summarized go/no-go read for the client.
- **`run-manifest.json`** — pipeline version, dependency versions, platform (traceability per system-design §6.7).

Plus the durable engineering assets: the `apps/worker` pipeline (hexagonal, 63 passing tests, TDD throughout), the adversarial synthetic generator (ground-truth-by-construction), and the monorepo scaffold staging Phase 1.

## 4. Named prerequisites to repeat this on real cases

1. **Scan-body library meshes** for the client's systems (sourced from their RealGUIDE libraries) + each part's fixed scan-body→platform transform.
2. **Real scans** with scan bodies in place, exported as STL.
3. **Ground truth** — the spike's first real-data deliverable: derive the positioned-implant transform from RealGUIDE export, or fall back to a machined/measured phantom (the named Plan B, system-design §6.4).
4. **Orientation normalization** for real scans (the spike assumes a z-up frame; real intraoral scans need an ingest step to establish "up" before localization).

## 5. Honest limitations (scope of this spike)

- Validated on **synthetic** geometry; real-scan clear-rate is the next measurement, not yet taken.
- One synthetic scan-body type; the auto-clock allow-list is per-geometry and grows with evidence.
- Stops at **case prep** — no crown morphology, abutment generation, manufacturability, or RealGUIDE export (later phases).
- Thresholds are calibrated to the synthetic mesh resolution; real dense scans will re-calibrate (expected tighter).

## 6. Recommendation

Proceed to **run this spike on a batch of the client's real cases** to measure the real clear-rate by retention type and scan-body type. Cement-retained single crowns are the first auto-target (no clocking; cleared at 100% / 0% false-confidence here). That measured clear-rate is the input to the 2B go/no-go and the number to put in front of the client before quoting the augment pipeline.
