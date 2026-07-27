# Phase 2A Spike — Automated Case-Prep Design Spec

**Date:** 2026-06-28
**Status:** Implemented (synthetic ground truth). 63 tests green; see [`../../engagement/phase2a-spike-findings.md`](../../engagement/phase2a-spike-findings.md) for results. Notable deviation: Open3D `registration_icp` segfaults on the arm64 wheel, so registration uses an in-house numpy/scipy trimmed ICP; clocking confidence uses an explicit anti-rotation-feature residual rather than whole-surface RMSE.
**Engagement deliverable:** the 2A de-risk spike — *prove the count → localize → align → 6-DoF pose → gate chain and measure clear-rate*, producing the go/no-go evidence the client is billed for.

Source docs: [`phase2a-automated-case-prep-plan.md`](../../phase2a-automated-case-prep-plan.md), [`implant-cad-system-design (1).md`](../../implant-cad-system-design%20(1).md) §6, [`technical-design-build-guide.md`](../../technical-design-build-guide.md) Part 2, [`schema.sql`](../../schema.sql).

---

## 1. Purpose & success criteria

This spike answers one question: **is Phase 2 (automation) technically possible for this client, and on what fraction of their caseload?** It de-risks the geometric core (registration + clocking) — the component the design docs identify as the genuine R&D risk on which all automation ROI rests — *before* the client commits to the larger 2B build.

It deliberately stops at **case preparation** (count, locate, align, recover pose, gate, hand off). It does **not** generate crown morphology, build abutments, or replace QC — those stay with the operator / later phases.

**Success = a runnable pipeline + an accuracy report** that, on the spike dataset, demonstrates:
- the count → localize → align → pose chain runs end-to-end and is **deterministic**;
- recovered pose error is measured against ground truth (position mm, axis °, clocking °);
- a **retention-aware confidence gate** auto-passes confident implants and **flags** ambiguous ones;
- the headline numbers — **clear-rate** and **false-confidence-rate** — are produced per retention type and scan-body type (the go/no-go metric from system-design §6.8).

## 2. Scope

**In:** ingest + scale-gate; detect & count vs declared N; localize (seed + axis); coarse global registration (FPFH+RANSAC/FGR) → fine trimmed point-to-plane ICP; derive implant pose via the library scan-body→platform transform; **clocking** (multi-start ICP + anti-rotation-feature check) for screw-retained; retention-aware confidence gate; report artifacts.

**Out (this slice):** crown/bridge morphology, abutment interface generation, manufacturability checks, RealGUIDE export baking, ML detector (Track B), the portal itself (Phase 1).

**Retention routing (decisive simplification):** cement-retained cases need only position + axis → they skip the clocking gate and are the easy, high-clear-rate wedge. Screw-retained cases get the full clocking treatment and the hard gate.

## 3. Architecture — hexagonal / DDD

Pure domain core, IO and geometry-engine at the edges, so the registration engine is swappable (Open3D now → MeshLib later) without touching domain logic.

```
apps/worker/src/case_prep/
  domain/    pure, no IO, no Open3D:
             Pose6DoF, RigidTransform, Axis, ScanBodyType, Retention,
             ConfidenceScore, GateDecision + retention-aware gating rules,
             accuracy metrics (position/axis/clocking error, C2M deviation)
  ports/     Protocols: ScanSource, LibrarySource, GroundTruthSource, ReportSink
  pipeline/  stages: ingest -> detect_count -> localize -> register -> derive_pose
             -> clocking -> gate ; an orchestrator threads a CaseContext through them
  adapters/  fs_loader (real data via input contract),
             synthetic_fixtures (adversarial generator, ground-truth-by-construction),
             open3d_engine (FPFH+RANSAC -> trimmed point-to-plane ICP, multi-start clocking),
             report_writer (JSON + HTML + best-effort renders)
  cli.py     `case-prep run --case <dir>` | `--synthetic [--seed N --implants K ...]`
```

**Dependency rule:** `domain` imports nothing from `adapters`/`pipeline`. `pipeline` depends on `domain` + `ports`. Open3D is imported **only inside** `open3d_engine` (lazily), so the whole core is testable with numpy/trimesh alone.

## 4. Domain model (ubiquitous language)

- **Scan** — an intraoral STL with scan bodies in place (unitless geometry).
- **ScanBodyType** — a manufacturer part; its **library mesh** and its fixed **scan-body→platform transform** are known. (`implant_sites.scan_body_type` in the schema.)
- **ImplantSite (declared)** — tooth number, implant system/code, scan-body type, **retention** (cement/screw). Comes from the case manifest (mirrors `implant_sites`).
- **Pose6DoF** — implant platform position + axis (+ clocking estimate for screw-retained). "Where the healing cap / restoration seats."
- **RigidTransform** — a 4×4 SE(3) transform; composition and inversion live in the domain.
- **ConfidenceScore** — per-implant metrics: ICP fitness, inlier RMSE, clocking best-vs-next-best gap, anti-rotation residual, multi-implant consistency.
- **GateDecision** — `PASS` (auto-seed) | `FLAG` (route to manual), with reason. Retention-aware.
- **ClearRate / FalseConfidenceRate** — aggregate go/no-go metrics.

Invariants expressed in types: an axis is a unit vector; a `Pose6DoF` for a cement-retained site carries **no** clocking; a `GateDecision` always carries a reason; ground-truth is a separate type the pipeline cannot consume.

## 5. The case manifest (input contract — Phase-1 bridge)

Every case (real or synthetic) is a directory with a `case.json` declaring the structured intake the portal already captures, plus file pointers:

```json
{
  "case_ref": "opaque-label",
  "tooth_notation": "universal",
  "implant_sites": [
    {"tooth": 19, "scan_body_type": "atlantis_x", "retention": "cement"},
    {"tooth": 30, "scan_body_type": "atlantis_x", "retention": "screw"}
  ],
  "scan_file": "scan.stl"
}
```

`library/<scan_body_type>/mesh.stl` + `transform.json` (scan-body→platform) supply the known targets. `ground_truth.json` (held out from the pipeline) supplies true poses for the metrics layer. This mirrors `schema.sql` so a real portal case serializes straight into it.

## 6. The synthetic generator (validation engine — runs today, no external data)

Places known scan-body meshes at **known 6-DoF poses** on a procedural arch, writing a complete case directory + held-out `ground_truth.json`. **Adversarial by design** so "success" is not tautological:
- procedural **gingiva/arch surface** (so height-above-surface detection is tested, not gamed);
- a procedural scan-body mesh with a small **anti-rotation flat** and otherwise **near-cylindrical symmetry** (the thing that makes clocking hard);
- tunable **Gaussian vertex noise**, **partial capture** (face dropout / occlusion), **decimation**;
- tunable implant **count**, **retention mix**, **spacing**.

The generator and the registration engine share **no** pose information — the engine receives only geometry; the known pose is revealed only to the metrics layer. When real client STLs + library meshes + ground-truth arrive, the *same* pipeline and report run against them via `fs_loader`.

## 7. Pipeline stages

1. **Ingest & normalize** — load scan; **scale-gate** arch bbox to 45–70 mm; downsample to ~10–16k for processing.
2. **Detect & count** — find scan-body instances (height-above-gingiva + cylinder-like shape signature, narrowed by declared N); **reconcile vs declared count** → mismatch flags whole case (also a billing check).
3. **Localize** — per instance: centroid = position seed, PCA = axis seed → ROI crop.
4. **Register** — coarse FPFH+RANSAC/FGR seeded by the ROI → fine **trimmed point-to-plane ICP** at full res with an **explicit overlap parameter**.
5. **Derive implant pose** — apply the library's fixed scan-body→platform transform → platform position + axis.
6. **Clocking** (screw-retained only) — **multi-start ICP** about the axis; pick lowest residual **and** measure best-vs-next gap; **anti-rotation-feature** alignment cross-check.
7. **Gate** — retention-aware thresholds on fitness/RMSE, clocking gap, multi-implant consistency, count match → `PASS` / `FLAG`. Per-implant: one low-confidence implant flags only itself.

## 8. Artifacts (the billable deliverable)

Each run writes `reports/<timestamp>-<case_ref>/`:
1. **`accuracy-report.json` + `accuracy-report.html`** — per-implant recovered pose, error vs ground truth, confidence metrics, PASS/FLAG; aggregate **clear-rate** + **false-confidence-rate** by retention type & scan-body type.
2. **Overlay renders** (best-effort) — library mesh superimposed on the scan per implant.
3. **`run-manifest.json`** — pipeline version, library/dependency versions, parameters, RNG seeds (traceability per §6.7).
4. **`feasibility-memo.md`** — auto-summarized go/no-go evidence for the client.

## 9. Testing strategy (test-first, per global XP conventions)

- **Domain unit tests** — transform composition/inversion, axis normalization, gate thresholds (retention-aware), metric math — pure, fast, no Open3D.
- **Pipeline integration tests** — full chain on **seeded** synthetic fixtures, asserting **deterministic regression bounds** (e.g. position < 0.1 mm, axis < 1° on clean fixtures; documented separately from aspirational clinical targets).
- **Gate behaviour tests** — degraded fixtures (high noise / broken anti-rotation feature) must **FLAG**, not falsely PASS (guards false-confidence).
- **Golden-run smoke test** — a known seed produces a report with stable structure.
- A change is not done without green tests and a `code-reviewer` pass (no open High/Critical).

## 10. Tech & environment decisions

- **Python 3.9** for the spike (the installed, Open3D-0.18-compatible interpreter on this arm64 host; Python 3.14 present is too new for Open3D). Production CI/container pins **3.11** per the docs.
- **Open3D + trimesh + numpy** for geometry/registration; **pydantic** for typed domain/DTOs; **jinja2** for the HTML report; **matplotlib/trimesh** for best-effort renders. **MeshLib** documented as the licensed production swap-in (evaluated free under non-commercial during the spike).
- **Monorepo** (pnpm/turbo): `apps/worker` built now; `apps/web`, `apps/api`, `packages/shared` are documented placeholders staging Phase 1.

## 11. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Synthetic success is tautological | Adversarial generator + held-out ground truth + no answer leakage (§6) |
| Clocking unreliable on real captures | Success = recover-or-flag with measured false-confidence; hard gate; cement-retained wedge first |
| Open3D install/headless fragility | Engine isolated behind a lazily-imported adapter; core testable without it; renders best-effort |
| Scope creep | Thin vertical slice first, then thicken (XP increments) |
| Real ground-truth from closed RealGUIDE | Synthetic gives exact GT now; real GT is the spike's named first deliverable / phantom Plan B (§6.4) |

## 12. Out-of-scope but staged-for

Phase-1 portal (web/api/shared placeholders + the `case.json` contract that mirrors `schema.sql`); Track-B ML detector; 2B abutment/manufacturability/RealGUIDE-export; 2C morphology. None require restructuring to add.
