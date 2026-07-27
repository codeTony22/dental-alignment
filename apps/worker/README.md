# apps/worker — Phase 2A Automated Case-Prep

Python pipeline that started as the spike proving the **count → localize → align → 6-DoF pose →
gate** chain, and now also carries the production **propose → confirm → align → package** flow
(`pipeline/auto_flow.py`) plus the FastAPI demo server (`src/case_prep/server.py`, port 8000)
that backs the React demo in `apps/web`.

Design spec: [`docs/superpowers/specs/2026-06-28-phase2a-case-prep-spike-design.md`](../../docs/superpowers/specs/2026-06-28-phase2a-case-prep-spike-design.md).

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
make test                                     # run the test suite (788 tests, ~17 min)
make serve                                    # demo API -> http://localhost:8000

# THE DEMO — run every scenario + the test suite, build one HTML dashboard you can open:
make demo                                      # -> reports/demo/dashboard.html
#   self-checks 4 scenarios (cement clean, screw clean, screw degraded, count mismatch)
#   against stated expectations, renders each in 3D, and embeds the test-suite report.

# Single case:
.venv/bin/python -m case_prep.cli run --synthetic --seed 7 --implants 3 --retention screw
# -> writes reports/<timestamp>-<case_ref>/  (accuracy-report.html/.json, manifest, memo)
```

### The demo dashboard
`make demo` (or `case-prep demo`) is the **learn-and-check workflow**: it runs the pipeline
across curated scenarios, asserts each against an expectation (so it's a *check*, green/red, not
just a picture), renders the recovered vs ground-truth poses in 3D, runs the full test suite, and
assembles a single self-contained `reports/demo/dashboard.html`. Open it in a browser. Exit code is
non-zero if any scenario misses its expectation — so it doubles as a CI regression gate.

## Layout (hexagonal)

| Dir | Role |
|---|---|
| `src/case_prep/domain/` | pure: poses, transforms, confidence + pose-stability grading (`pose_confidence.py`), retention-aware gate, guidance, metrics, our own trimmed ICP (`icp.py`) — no IO, no Open3D |
| `src/case_prep/ports/` | Protocols: scan/library/ground-truth sources, report sink |
| `src/case_prep/pipeline/` | spike stages (ingest → detect_count → localize → register → derive_pose → clocking → gate) and **`auto_flow.py`** — the production propose → confirm → align flow (next section) |
| `src/case_prep/adapters/` | fs loader, **adversarial synthetic generator**, Open3D engine, report writer, **SDF-CSG booleans** (`mesh_sdf`/`booleans`; the pure field math is `domain/sdf.py`), **messy-mesh generator**, **real-file ingest** |

## Alignment (`pipeline/auto_flow.py` — the production flow)

Per confirmed site. The **declared variant is required at intake** (the web UI enforces the
picker); centre + rim marks are ONE measurement pair — pair integrity is a hard product rule.

1. **Rim-first closed-form seat** — the visible rim band is fit as a 3D circle (least
   squares), giving axis + centre; depth by 1-D search. Doctor border clicks pin the seat
   (`_pinned_rim_seat`); a `border_click_disagreement_mm` advisory (>0.6 mm → attention)
   flags clicks that disagree with the scanned rim.
2. **Variant identification (calibrated)** — score = seat residual + 2× mean
   template→patch distance over the template's above-gingiva part (cut at −0.4 mm).
   Candidates are ranked **before** any refinement — post-hoc improvements never leak into
   ranking. Two variants within max(0.05 mm, 10%) in seat residual are "inseparable": the
   doctor decides, never a silent guess. Declared ≠ identified → amber mismatch flag.
3. **Winner-only refinement chain** — `_refine_depth` (axial slide, symmetry + top-face
   gates), `_best_clocking` (coded-face rotation sweep), `_refine_best_fit` (trust-region
   trimmed ICP, ≤1.2 mm / ≤8°, monotonic acceptance), `_center_on_rim` (slides the pose so
   the rim ring — 0.2–0.58 mm off the canonical axis — lands on the scanned rim circle;
   ≤0.8 mm, monotonic gates), then **ring-fixed recess clocking** (`_void_clocking`, the
   final pass): rotates the part about the vertical axis through the posed rim-ring centre
   (rotation + exact compensating slide) so the off-axis screw bore lands on the scanned
   screw-recess void. About the ring centre the rim is invariant by construction — the
   pass cannot undo the centering — and the swing radius |bore−ring| (0.77–1.12 mm)
   exceeds the axis-relative bore offset: more reach. Both passes refuse moves that push
   top-face p90 past the 1.5 mm ride-off bound unless improving.
4. **Confidence** — `_pose_stability_bootstrap` (K=8 re-seats of the winner under
   σ=0.3 mm click noise; σ is measured, see `docs/research/fle-calibration.md`) feeds
   `domain/pose_confidence.py`: pose spread + a Fitzpatrick TRE estimate → grade
   **high / medium / low**. Opt-in via `run_auto_case(compute_confidence=True)` — the demo
   server enables it; the battery leaves it off.

Then measure → gate → construct → package as before (interproximal measurement, advisory
fail-closed gate, own-export construction with SDF-CSG screw channel, SHA-256 manifest).

## Boolean operations (SDF-CSG)

`make booleans-demo` bores a screw-access channel into a restoration via signed-distance-field
CSG and exports STLs + a field-slice render. SDF-CSG is robust on the non-watertight meshes real
scans produce (it closes holes and bores the channel in one pass), where naive mesh booleans crack.
Ops: screw channel (subtract), abutment post (union), cement gap (offset) — see `adapters/booleans.py`.
Real STLs ingest via `adapters/ingest.py`. Library CAD is canonicalized by
`canonicalize_revolute`: manufacturer file-z is **trusted then verified** as the revolution
axis (multi-angle self-similarity on area-uniform samples); PCA candidates only as fallback;
rim-down flip preserved. Every library cap is rim-seatable by construction
(`CapLibrary.rim_seatable`).

Open3D is imported only inside `adapters/open3d_engine.py` (spike-era); its `registration_icp`
segfaults on this host, so the production pipeline runs on numpy/scipy/trimesh only —
`domain/icp.py` is our own trimmed ICP.

## Data

- `data/real/` — real client data; **gitignored**. Layout per `data/real/README.md`:
  `library/caps/<model>/` (cap size variants), `library/construction/<vendor>/` (vendor
  construction parts), `scans/<doctor>/<jaw>.stl` + optional `sites.json` — drop a new
  doctor folder there and the live demo discovers it.
- `reports/` — generated billable artifacts; **gitignored**. Synthetic cases (held-out
  ground truth, no clinical data) are generated under `reports/cases/`.

## Tools (`tools/`)

- `warm_demo.py` — pre-warm the live-demo caches (propose + full run for both demo cases) so the React demo answers instantly.
- `fleet_scoreboard.py` — the regression harness: runs every real case through the production pipeline and scores rim_agreement / top_face_p90 / rim_off_centre / bore_void_off / id_match / confidence / gate per site; `--save NAME` snapshots to `reports/scoreboard/`, `--baseline NAME` prints a per-site improved/regressed/unchanged diff.
- `make_phantom.py` — printable calibration phantom with ground-truth-by-construction poses (`reports/phantom/phantom-plate.stl` + truth JSON); protocol: `docs/engagement/phantom-protocol.md`.
- `evaluate_phantom.py` — registers a scanned phantom into the design frame via its fiducials, runs the real pipeline, and compares shipped poses to designed truth (confidence-validation table).
- `fle_study.py` — operator centre-click FLE study: `instructions` prints the ~10-minute protocol, `analyze --write` fits the click-error distribution; protocol: `docs/engagement/fle-centre-click-protocol.md`.
- `benchmark_alignment.py` — offline seating-strategy benchmark (research only, never called by production); survey: `docs/research/alignment-algorithm-survey.md`, results: `docs/research/alignment-benchmark-results.md`.
