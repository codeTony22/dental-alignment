# ArTech Case-Prep — Current Architecture (as built)

> ## 📜 HISTORICAL RECORD — not the operational truth
>
> This document predates the operator product app (`apps/product` + `apps/bff`) and the
> client's five-stage flow. It is kept **unedited** as a record of what was designed and
> why; do not treat any command, path, count or flow description in it as current.
>
> For what is true today:
> - **[`../CLAUDE.md`](../CLAUDE.md)** — the repo map: the five gates, the freeze line, the
>   stage model, and the traps.
> - **[`ARCHITECTURE.md`](ARCHITECTURE.md)** — how the system fits together as built.
> - **[`engagement/product-app-plan.md`](engagement/product-app-plan.md)** — the product
>   plan, and §10 for the record of client direction as it arrived.
> - **[`engagement/product-runbook.md`](engagement/product-runbook.md)** — how to run and
>   demo the product app.
> **Specifically superseded by [`ARCHITECTURE.md`](ARCHITECTURE.md)**, which covers the
> same ground for the system as it now stands. This file's own header claims to be a
> living document reflecting 788 tests as of 2026-07-19 — it is neither living nor
> current: the worker alone is past 1,000, and the product app did not exist.

*Living document. Reflects what exists and is tested (788 tests) as of 2026-07-19 — not the
original plan. The plan review lives in
`engagement/phase2-plan-review-2026-07.md`; per-decision history in the project memory.*

## The product flow (client's words → system)

```
Doctor's arch scan (STL, upper/lower)
   │
   ▼
PROPOSE      cap_detection.find_cap_sites — rim-slab stack finds healing-cap candidates
   │            (crowns-up via mesh normals · interior mask kills border flare ·
   │             arch-band kills palate · height window kills teeth · closed level ring
   │             + empty core = cap evidence)
   ▼
CONFIRM      human, per site: centre + rim-border marks (ONE measurement pair — pair
   │            integrity is a hard product rule) or a painted patch (brush), PLUS the
   │            REQUIRED declared variant (the intake picker is enforced; with the
   │            declaration, fleet identification went 1/4 → 4/4 on the ambiguous
   │            single-cap scans)
   ▼
ALIGN        rim-first closed-form seat: the visible rim band is fit as a 3D circle
   │            (Kasa least-squares) → axis + centre; depth resolved by a 1-D search.
   │            Doctor-supplied border clicks PIN the seat to their clicked circle
   │            (_pinned_rim_seat); border_click_disagreement_mm (>0.6 mm → attention)
   │            flags a suspect gesture — the seat still honors the doctor's circle
   ▼
IDENTIFY     calibrated contract: score = seat + 2.0×t2p (patch→template plus
   │            2× template-above-gingiva→patch; above-cut −0.4). Candidates are ranked
   │            BEFORE any per-candidate refinement — post-hoc polish must never leak
   │            into ranking (a burned-in structural rule). Two variants within
   │            max(0.05 mm, 10%) in seat residual → "inseparable": the doctor decides,
   │            never a silent guess; declared ≠ identified → explainable mismatch flag
   ▼
REFINE       winner-only chain (runs after ranking — the same structural safety):
   │            _refine_depth (axial slide, symmetric-score + top-face gates) →
   │            _best_clocking (coded-face rotation sweep) →
   │            _refine_best_fit (trust-region trimmed ICP ≤1.2mm/≤8°, monotonic accept) →
   │            _center_on_rim (slides the pose so the posed rim ring — its centre sits
   │            0.2–0.58 mm off the canonical axis — lands on the scanned rim circle;
   │            ≤0.8 mm, monotonic band + top-face gates) →
   │            CODED-FEATURE CLOCKING (the FINAL pass, 2026-07-20): the coded cutouts
   │            on the cap's top face are the PRIMARY rotational instrument — a lab
   │            tech judges rotation there, and the validated "e8" extractor
   │            (domain/clock_signature.py: (θ,r) depth-image unwrapping about the
   │            scan's own cap-rim centre, informative-row filtering, masked circular
   │            correlation; the only design that reproduced known applied rotations
   │            in the two-pose consistency study, 6/7 sites ≤10°) reads the
   │            misalignment and the pass rotates to null it (ring-fixed kinematics:
   │            rotation + exact compensating slide, the rim cannot move; adoption
   │            gated by stability ≤0.35 mm, face-mean +0.4, top-p90 1.5 ride-off,
   │            band ≥1.6-and-worsening, and a CONFIRM RE-READ ≤12° at the candidate).
   │            No code evidence → the recess clock (_void_clocking, bore-on-void)
   │            keeps its prior behavior; neither instrument → ships flagged
   │            rotation_unverified. The recess AZIMUTH was measured systematically
   │            biased (partially-visible dip skews its centroid; it had rotated away
   │            from the codes on 5 of 7 sites), so where both instruments read, their
   │            disagreement ships as clock_consistency_deg (>20° → attention); the
   │            printed phantom (designed clock angles) is the physical arbiter
   ▼
CONFIDENCE   _pose_stability_bootstrap — K=8 re-seats of the WINNING variant under
   │            σ=0.3 mm click noise (σ is MEASURED, see FLE below);
   │            domain.pose_confidence → PoseSpread (p90 position / axis / clock),
   │            Fitzpatrick TRE estimate, grade high / medium / low. A read-out: never
   │            changes the shipped pose or the identified variant. Opt-in kwarg
   │            compute_confidence (the demo server enables it); shown as a chip in the
   │            results-table gate cell
   ▼
MEASURE      site_analysis.measure_site — interproximal (mesio-distal) span + clearances,
   │            clinical classification (≥7mm ample / 6–7 narrow / <6 insufficient / ≥12 two)
   ▼
GATE         domain.confidence — retention-aware thresholds; CaseMode ADVISORY fail-closed
   │            for real data (never auto-approves; would_pass = shadow calibration log);
   │            domain.consistency — cross-implant spacing ≥4mm, divergence ≤60°;
   │            GUIDANCE: domain.guidance.advisory_guidance routes operator attention —
   │            border clicks disagree >0.6 mm, or top-face p90 >1.5 mm → "attention"
   │            with a concrete action (re-check the ◐ border clicks, paint the cap, …)
   ▼
CONSTRUCT    pipeline/final_product.build_final_product — OUR OWN EXPORT (client pivot
   │            2026-07-04, replaces the RealGUIDE handoff): the vendor construction part,
   │            screw-access channel bored along the implant axis (SDF-CSG; watertight
   │            output even from non-watertight vendor meshes)
   ▼
PACKAGE      output_package.emit_case_package — the paid deliverable:
                raw jaw STL (unmodified) · per-site aligned healing-cap STL ·
                vendor construction scan-body STL at pose (in-mesh = pose carrier) ·
                implant.json (pose 4x4 + position/axis, fitness = scan-coverage,
                variant record, advisory, per-run audit block, nudge audit when the
                operator rotated) ·
                production set (*-prosthesis_cad.stl + construction.json — generated by US) ·
                per-site QC ACCEPTANCE ARTIFACTS (adapters/qc_render.py, 2026-07-20):
                <case>-<tooth>-clockview.png (occlusal clock view: scan depth field,
                coded-cutout overlay, bore★/void✕, rotation residual + evidence) and
                <case>-<tooth>-deviation.png (signed deviation map ±0.5 mm, RMS + p90
                — the industry lab-tech acceptance convention) ·
                manifest.json (SHA-256, QC renders included) · QC overlay
```

Surfaces: `case-prep auto` CLI (PROPOSE mode → prints ready-to-paste `--site TOOTH:X,Y,Z`
lines; the flag accepts `TOOTH:X,Y,Z[:VARIANT]`;
confirmed mode → full run), `make auto`, and the demo pair — FastAPI server
(`src/case_prep/server.py`, `make serve`, port 8000, runs this same pipeline with
`compute_confidence=True`) behind the React demo UI (`apps/web`, port 5173).
The server also exposes the OPERATOR ROTATION NUDGE (2026-07-20): POST
`/api/cases/{case}/sites/{tooth}/nudge-rotation` `{delta_deg}` — re-applies the
rotation via the same ring-fixed kinematics and REFUSES (409, human-readable reason)
through the same certification gates the pipeline uses; success re-emits the aligned
STL + implant.json with a nudge audit record, re-reads the coded-cutout residual, and
appends provenance to run-history.jsonl. A proposal the gates still judge — the human
backstop for `rotation_unverified` sites, never a bypass. UI: the Rotation column in
the results table (−15/−3/+3/+15/Reset, auto-expanded on weak-evidence rows).
Orchestrating module: `pipeline/auto_flow.py`.

## Module map (hexagonal)

| Layer | Module | Responsibility |
|---|---|---|
| domain | `icp.py` | trimmed point-to-point ICP (Open3D ICP segfaults on arm64) |
| domain | `confidence.py` | gate + `CaseMode` (validated/advisory, fail-closed) |
| domain | `pose_confidence.py` | bootstrap read-out: `PoseSpread` (p90 pos/axis/clock) + Fitzpatrick TRE + grade — never changes the pose |
| domain | `guidance.py` | advisory gate as GUIDANCE: every computed signal maps to a concrete operator action |
| domain | `consistency.py` | cross-implant geometric sanity (conservative, explainable) |
| domain | `cap_catalog.py` | open catalog: `CapSpec(model, variant)`; `resolve_sites` NMS |
| domain | `sdf.py` | SDF-CSG booleans (screw channel etc., non-watertight-safe) |
| adapters | `cap_detection.py` | the rim-slab candidate generator + crowns-up orientation |
| adapters | `cap_library.py` | filesystem template catalog (`rim_seatable` by construction); clinical detection composition |
| adapters | `site_analysis.py` | occlusal axis, interproximal measurement |
| adapters | `open3d_engine.py` | localize/isolate/register engine (body isolation is load-bearing) |
| adapters | `output_package.py` | the industry-grounded deliverable emitter |
| adapters | `ingest.py` | normalization; `canonicalize_library` + `canonicalize_revolute` (file-z trust-then-verify for rotational parts) |
| adapters | `qc_render.py` | per-site acceptance artifacts: occlusal clock view + signed deviation map (reporting only — never touches a pose) |
| domain | `clock_signature.py` | the validated "e8" coded-cutout clock extractor ((θ,r) depth-image correlation; two-pose-consistency proven) |
| pipeline | `auto_flow.py` | propose → confirm → align/identify/refine/confidence → measure/gate/package |
| pipeline | `stages.py` / `orchestrator.py` | staged worker (stage1→seed→stage2) / single-shot |
| pipeline | `evaluation.py` | held-out ground-truth eval incl. shadow false-confidence |
| tools | `fleet_scoreboard.py` | EVERY real case through the production pipeline; `--save NAME` snapshots to `reports/scoreboard/`, `--baseline NAME` per-site improved/regressed/unchanged diff — the regression harness the client asked for |
| tools | `make_phantom.py` / `evaluate_phantom.py` | printable calibration phantom (watertight plate + ground-truth JSON) and its evaluator — the physically-validated auto-pass line (`docs/engagement/phantom-protocol.md`) |
| tools | `fle_study.py` | deliberate centre-click re-click study: `instructions` prints the protocol, `analyze --write` fits the FLE distribution (`docs/engagement/fle-centre-click-protocol.md`) |
| tools | `benchmark_alignment.py` | offline seating-strategy benchmark — research only, never called by production (`docs/research/alignment-algorithm-survey.md`, `-benchmark-results.md`) |
| tools | `warm_demo.py` | pre-warm the live-demo caches (same live pipeline, computed ahead of time) |

## Data layout (`apps/worker/data/real/`, gitignored)

```
library/caps/<model>/<model>-<code>.stl     # 6 size variants per model (code = Ø×H, e.g. 5020)
library/caps/<model>/superseded-<date>/     # archived parts — listed, flagged, selectable
library/construction/<vendor>/<any>.stl     # per-vendor construction parts (name meaningless)
scans/<anything>/<any>.stl                  # raw scans — a folder with an STL is a case
```

Models on hand: `neodent-gm`, `zimmer-4.5`, plus the legacy Certain 3i shelf (a client-named
directory under `data/real/` — spelled only in `adapters/client_data.py`, displayed as
"Legacy shelf").
Vendors wired: `dess`, `atlantis` (third vendor pending client).

NO NAME INFERENCE (client directive 2026-07-25, "the lab chooses, the software never
guesses"): neither the implant system nor the construction part is derived from a folder
or file name. A folder-name match survives only as `suggested_model` /
`suggested_construction` on the case payload; `POST /api/cases/{id}/run` requires an
explicit `model` + `construction_path` and 422s without them.

## Measured truths the architecture rests on

- Clean library CAD closes the real-data gap: 2.6 mm → ~20 µm.
- Body isolation is THE real-arch unlock: naïve ROI 1.53 mm → 0.13 mm.
- Low-profile caps ≠ scan bodies: no local geometric feature fully separates caps from
  tissue artifacts at n=2 arches → propose+confirm; full-auto is data-gated.
- Whole-CAD ICP fitness is structurally low (~0.3–0.45) on partially-visible caps —
  scan-coverage is the confirmation signal; named honestly in the deliverable.
- Advisory mode is non-negotiable until per-class threshold validation (a synthetic-calibrated
  gate passed a 1.75 mm-wrong pose on real geometry).
- FLE is measured, not assumed: border repeat-click xy p50/p68/p90 = 0.32/0.46/0.61 mm from
  run history — the bootstrap's σ=0.3 mm is evidence-based; 4 border clicks propagate to
  ≈±0.15 mm TRE at the platform. The centre-click (pair) channel supplied zero usable
  scatter (every logged pair is a byte-identical replay of the curated marks) — the
  deliberate centre-click study (`tools/fle_study.py`) is what adds it
  (`docs/research/fle-calibration.md`).
- The catalog's own geometry couples clocking and centering: the screw-bore centre sits
  0.43–0.76 mm off the canonical axis and the rim-ring centre 0.2–0.58 mm (whole catalog)
  — a rotation about the canonical axis swings the rim centre, a centering slide moves
  the bore. The resolution is kinematic, not iterative: compose the clock rotation with
  the exact compensating slide that holds the MEASURED rim centre (the Kasa fit of the
  posed rim band, re-measured per candidate angle — a fixed 3D stand-in still leaks
  0.2 mm under a tilted seat) — the rim cannot move by construction, while the bore's
  swing radius |bore−ring| (0.77–1.12 mm) exceeds |bore| — strictly more reach.
- File-z trust-then-verify canonicalization (`canonicalize_revolute`): manufacturer cap
  CADs are saved axis-aligned in file-z, and the old PCA-only axis pick — fooled by the
  coded cutouts — shipped templates tilted up to 88°. File-z now joins the candidate set,
  verified by trimmed multi-angle self-similarity on area-uniform samples, and wins within
  a 10% margin (PCA remains the fallback for genuinely rotated files). This one fix
  dissolved the "zimmer-t7 outlier" (it was the 27°-tilted template, not the site) and
  made every library cap rim-seatable by construction (`CapLibrary.rim_seatable`).
- Clocking is recess-authoritative: the coded-face sweep is nearly flat on these caps
  (0.04–0.07 mm variation — no discrimination) while the off-axis bore decides where the
  screw hole lands (measured 0.3–1.3 mm off the scanned recess, true optimum up to ~150°
  away; a +0.17 face preference was measured overriding a 1.3 mm screw-hole error). The
  face metric survives only as a catastrophe guard (+0.4 mm mean).

## Known contracts & debts (honest list)

- `_derive_pose`: platform translation honored; axis assumes body∥platform (coaxial) —
  extension point marked for angulated interfaces.
- `SitePackageSpec.fitness` carries scan-coverage — and the emitted `implant.json` key is
  still named `fitness`, so a consumer must read it as coverage, not ICP fitness (the run
  report keeps `coverage` and `icp_fitness` as separate fields; the spec's `pose_origin`
  honesty field is not yet written into the JSON sidecar).
- Pinned-seat depth sensitivity on tilted half-submerged profiles (surfaced by phantom
  simulation): when the doctor's clicked circle pins a seat on a steeply tilted,
  half-buried cap, the 1-D depth resolution has less signal to push against.
- zimmer-t7 stays confidence grade "low", honestly: tilted, half-submerged,
  position-dominated residual — the system flags it rather than pretending.
- Tooth numbers in packages are operator-entered; vendor #3 unknown (vendor layer delayed
  by client decision until more vendor formats arrive).
- OWN-EXPORT pivot (2026-07-04) replaced the RealGUIDE handoff: the seam risk is dissolved,
  not tested. Open contract: the construction part's SEATING (vertical offset + axis
  convention vs the implant platform) needs each vendor's interface spec — currently the
  part is origin-centred and bored along its native tallest axis (verified plausible for
  DESS + Atlantis parts), documented in final_product.py.
- Variant ground truth unverified: the client confirming which caps were actually placed
  converts the variant identifications into measured accuracy.
