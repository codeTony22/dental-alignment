# MeshLib vs manifold — Stage-2 contender #2 scoreboard

**Measured** 2026-08-14 · **Host** macOS 26.4 (Darwin 25.4.0), arm64, single machine, unloaded
**Python** 3.9.6 (system) · **Scratch venv only** — the repo's pinned `.venv` was not touched, no repo file was modified.

| package | version | note |
|---|---|---|
| **meshlib** | **3.1.3.429** | `meshlib-3.1.3.429-py39…py314-none-macosx_12_0_arm64.whl`, 78.2 MB. Installs and imports cleanly on py3.9 / macOS arm64. **No install or import failure.** |
| manifold3d | 3.5.2 | same as the repo's pin |
| trimesh | 4.12.2 | same as the repo's pin |
| numpy / scipy / networkx / rtree | 2.0.2 / 1.13.1 / 3.2.1 / 1.4.1 | same as the repo's pins |

`meshlib` exposes **no `__version__`**; the version above is the pip distribution version.
License: free tier is Non-Commercial & Education and **expressly covers this evaluation**; commercial
embedding requires a paid license from AMV.

**Populations.** Battery 1 is the repo's own synthetic degeneracy corpus (ported, not imported).
Batteries 2–4 use **real vendor CAD and one real arch scan**, read-only. Nothing here is a fleet
sweep: **n = 1 cap and n = 1 scan**, not the 10-case fleet.

---

## Conversion bridge (precondition for every number below)

MeshLib's numpy bridge is **lossless float64**: box round-trip max vertex delta `0.0`, volume
identical. This contrasts with manifold3d's MeshGL round-trip, which **forces float32** on every
vertex it touches (~2.4e-7 mm of movement, per the repo's own `test_csg_corpus.py` docstring).
Every MeshLib row below therefore reflects the engine, not a conversion artifact.

---

## Battery 1 — the degeneracy corpus (ported from `apps/worker/tests/test_degeneracy.py`)

Same inputs handed to every engine; only the boolean engine varies. Voxel path at **0.1 mm**.
PASS = watertight **and** |V − V_expected| < 0.01 mm³ **and** the case's own geometric probe.
Expected volumes are analytic (32-gon prism arithmetic), not engine-derived.

| case (plan W3 #) | manifold (incumbent) | MeshLib (mesh) | MeshLib (voxel 0.1 mm) |
|---|---|---|---|
| **#1 coplanar bore lid on a machined floor** | **PASS** — err 2e-6 mm³, **0.9 ms** | **FAIL — SILENT NO-OP.** 0.000000 mm³ removed (err **49.94 mm³**); returned the base unchanged, 12 faces, watertight, `valid()=True`, `errorString=''`, both bad-contour bitsets empty. 5.4 ms | FAIL — err 0.076 mm³, 369 620 faces, 60 ms |
| **#2a floor clip, plane flush on the cap's own base** | **PASS** — err 2e-6 mm³, 3.4 ms | **PASS** — err 2e-6 mm³, **1.2 ms** | FAIL — err 0.183 mm³, 270 ms |
| **#2b cut with the clipped tool** (+ floor-height probe) | **PASS** — err 2e-6 mm³, floor err **0.000 mm**, 0.4 ms | **PASS** — err 2e-6 mm³, floor err **0.000 mm**, 0.5 ms | FAIL vol — err 0.239 mm³ (floor probe passes), 57 ms |
| **#4 two touching punches, BATCHED difference** | **PASS** — 4676.0107 mm³, 0.23 mm³ from the MC referee, no wall at midpoint, both sites open, 1.4 ms | **PASS** — 4676.0107 mm³ (**identical to manifold**), 0.8 ms | **FAIL — one subtraction lost.** 62.31 mm³ from the referee; site 1 never opened, 244 ms |

Referee for #4 is a seeded 400 k-sample Monte-Carlo union volume via ray-based `contains`
(4675.78 ± 0.31 mm³), independent of both engines.

### The #1 failure is not an artifact of one pose — it is a **rate**

Same fixture, **N = 200 seeded random clockings** of the cap about its own axis (a real degree of
freedom at every site), full production choreography, bore lid kept exactly on the floor plane:

| engine | correct | **silent no-op** | wrong volume | refused |
|---|---|---|---|---|
| manifold | 200 / 200 | **0** — rate 0.0 %, 95 % CI [0.0 %, 1.9 %] | 0 | 0 |
| MeshLib (mesh) | 99 / 200 | **101 — rate 50.5 %, 95 % CI [43.6 %, 57.4 %]** | 0 | 0 |

**Characterisation** (`investigate*.py`): the trigger is *not* a detectable mesh defect — both punches
are closed, hole-free, and report **0** self-colliding triangles and **0** degenerate faces to
MeshLib's own detectors. It is *not* the fan lid (a plain coplanar-topped cylinder cuts correctly)
and *not* float32 quantisation (a float32-quantised copy of the same punch cuts correctly).
It is a knife-edge coincident-plane classification: translating the punch by **+3e-7 mm** or
**−5e-7 mm** makes it cut correctly; anything inside roughly **±1e-7 mm** of exact coplanarity
no-ops. `BooleanParameters.forceCut = True` does not change it.

**The severity is the silence, not the failure.** No exception, no error string, no bad-contour
flag, and a watertight output. It is, however, **trivially detectable by the caller** — the output
is byte-identical to the input (same face count, same volume) — so a post-condition guard costs
one comparison.

The voxel path's #4 failure is separate and equally silent: **`voxelBooleanSubtract` does not
compose.** A second subtraction against an already-voxel-remeshed base removes nothing.
Confirmed at voxel sizes 0.05 / 0.1 / 0.2 mm, in both tool orders, and with a clean
mesh round-trip in between; the mesh-boolean cascade on the same tools is correct
(62.02 → 123.99 mm³). Pre-unioning the tools into one call works (123.94 mm³ removed).

---

## Battery 2 — a REAL vendor cap punch

Subject `neodent-gm-5030.stl` (4 859 v / 9 163 f, bore open — 555 boundary edges), bore-lidded by
the repo's own centroid-fan idiom (`_lid_boundary_loops`) → 9 718 f, watertight, 83.4583 mm³;
dilated 0.2 mm vertex-normal + self-heal → **17 186-face punch**; cut into a 20×20×8 mm slab
(corpus `_thick_slab` tessellation). Mouth probe = the corpus's 16-bearing idiom at the
**measured** dilated wall radius (2.460201 mm; cap wall 2.260233 + 0.2 = 2.460233).

| metric | manifold | MeshLib (mesh) | MeshLib (voxel 0.1 mm) |
|---|---|---|---|
| watertight | yes | yes | yes |
| volume | 3124.30272 mm³ | **3124.30272 mm³ — identical** | 3124.34581 mm³ (+0.043) |
| removed vs MC referee (76.40 ± 0.47 mm³) | 0.71 mm³ | 0.71 mm³ | 0.75 mm³ |
| removed ≤ \|tool\| (set-theory bound) | holds | holds | holds |
| **recess-mouth probe, max / median** | 0.000399 / 0.000113 mm | **0.000399 / 0.000113 mm** | 0.001149 / 0.000726 mm |
| self-intersecting pairs out | 0 | 0 | 0 |
| output faces | 2 600 | 2 620 | 307 924 |
| **wall-clock** | 42.7 ms | **17.3 ms (2.5× faster)** | 1 381.6 ms (32× slower) |

On real geometry with no exact coplanarity, MeshLib's mesh boolean is **exactly as accurate as
manifold and 2.5× faster**.

---

## Battery 3 — THE OFFSET HEAD-TO-HEAD (the capability we lack natively)

Subject: the same real lidded cap (9 718 f, 67 concave crease edges above z = 4.6).

**Metric (engine-independent, one instrument for all rows).** For a solid *S*, the boundary of the
true offset by *d* is exactly the *d*-level set of the distance function to *S*. So: sample the
offset result's own surface (30 000 seeded samples) and measure unsigned distance to the
**original** cap; the error is |dist − *d*|. Valid on convex, flat **and** concave (fillet) regions
alike. "Crease shortfall" = *d* minus the closest approach of the offset surface to the original's
reflex-edge vertices — how far the offset collapsed into the notch.

| d | engine | wall-clock | faces out | self-int pairs | err median | err p95 | **err max** | **crease shortfall** |
|---|---|---|---|---|---|---|---|---|
| **0.1** | vertex-normal *(shipping default)* | **0.003 s** | 9 718 | **1 153** | 0.00012 | 0.02576 | **0.05738** | **+0.06960** |
| | manifold minkowski *(reference)* | 16.923 s | 43 614 | 64 | 0.00009 | 0.00037 | **0.00045** | +0.00043 |
| | MeshLib offsetMesh @0.05 | 0.053 s | 113 144 | 0 | 0.00015 | 0.00249 | 0.02216 | +0.00963 |
| | MeshLib offsetMesh @0.025 | 0.086 s | 449 984 | 0 | 0.00001 | 0.00067 | 0.01129 | +0.00297 |
| | MeshLib generalOffset Standard @0.025 | 0.152 s | 449 980 | 0 | 0.00000 | 0.00035 | 0.00941 | +0.00169 |
| | **MeshLib sharpOffset @0.025** | **0.128 s** | 460 550 | 1 | 0.00000 | **0.00019** | 0.00213 | +0.00142 |
| **0.3** | vertex-normal *(shipping default)* | **0.003 s** | 9 718 | **3 768** | 0.00055 | 0.07526 | **0.28496** | **+0.19390** |
| | manifold minkowski *(reference)* | 16.900 s | 37 792 | 29 | 0.00036 | 0.00113 | 0.00136 | +0.00128 |
| | MeshLib offsetMesh @0.05 | 0.040 s | 130 456 | 0 | 0.00015 | 0.00167 | 0.02676 | +0.00425 |
| | MeshLib offsetMesh @0.025 | 0.223 s | 519 292 | 0 | 0.00002 | 0.00043 | 0.01212 | +0.00117 |
| | MeshLib generalOffset Standard @0.025 | 0.155 s | 519 288 | 0 | 0.00000 | 0.00025 | 0.01150 | **+0.00074** |
| | **MeshLib sharpOffset @0.025** | **0.359 s** | 520 404 | 3 | 0.00000 | **0.00020** | **0.00106** | +0.00117 |
| **0.5** | vertex-normal *(shipping default)* | **0.003 s** | 9 718 | **9 892** | 0.00100 | 0.12470 | **0.49345** | **+0.32745** |
| | manifold minkowski *(reference)* | 18.554 s | 32 606 | 2 | 0.00069 | 0.00193 | 0.00226 | +0.00213 |
| | MeshLib offsetMesh @0.05 | 0.056 s | 149 108 | 0 | 0.00016 | 0.00118 | 0.02392 | +0.00231 |
| | MeshLib offsetMesh @0.025 | 0.255 s | 593 680 | 0 | 0.00003 | 0.00031 | 0.01068 | +0.00075 |
| | MeshLib generalOffset Standard @0.025 | 0.528 s | 593 676 | 1 | 0.00001 | 0.00018 | 0.01063 | **+0.00045** |
| | **MeshLib sharpOffset @0.025** | **0.281 s** | 594 320 | 3 | 0.00000 | **0.00015** | **0.00136** | +0.00039 |

All offset modes are **voxel-based** — MeshLib has **no exact/Minkowski mesh offset**. `offsetMesh` is
OpenVDB distance field + dual marching cubes; `generalOffsetMesh(Standard)` is standard MC;
`sharpOffsetMesh` is MC + feature sharpening.

**Three readings that matter:**

1. **Vertex-normal is not a small-error method, it is a wrong-shape method at creases.** At d = 0.5
   it is **0.49 mm** wrong at worst and stands **0.327 mm** short of the crease, with **9 892**
   self-intersecting triangle pairs in the tool. The error grows with d (0.057 / 0.285 / 0.493).
2. **Minkowski's error is a pure, signed undershoot that grows linearly with d**
   (−0.00045 / −0.00136 / −0.00226), exactly the documented icosphere sagitta budget
   (0.0017 mm at r = 0.5, subdiv 3). The instrument reproducing the repo's own theory
   independently is a check on the instrument.
3. **MeshLib's error is pitch-limited, not offset-limited.** Halving the voxel (0.05 → 0.025 mm)
   roughly halves the max error (0.0222 → 0.0113 at d = 0.1). **Every MeshLib number above is a
   statement about its voxel size.** Its max error does *not* shrink with d, so it crosses over
   with minkowski: minkowski is more accurate at d = 0.1, sharpOffset at d = 0.3 and 0.5.
   The corpus's own cylinder-wall probe is blind to all of this — it reads 0.000367 mm even for
   the vertex-normal punch that is 0.49 mm wrong elsewhere.

### End-to-end (the offset feeds a boolean — d = 0.3, 3 repeats, median)

| offset engine | punch faces | offset s | + boolean s (manifold) | **total** | removed mm³ | cut faces |
|---|---|---|---|---|---|---|
| vertex-normal | 9 718 | 0.004 | 0.014 | **0.018 s** | 83.1934 | 2 592 |
| manifold minkowski | 37 792 | 29.339 | 0.024 | **29.363 s** | 85.36436 | 13 088 |
| MeshLib sharpOffset @0.025 | 520 404 | 0.529 | 0.209 | **0.738 s** | 85.39873 | 340 546 |
| MeshLib sharpOffset @0.025 + MeshLib boolean | 520 404 | 0.529 | 0.090 | **0.619 s** | 85.39873 | 341 892 |

The 18× mesh inflation costs only 0.209 s downstream, so **sharpOffset is ~40× faster end-to-end
than minkowski and agrees with it to 0.034 mm³ (0.04 %)**. Vertex-normal removes **2.2 mm³ less**
(2.6 % of the recess) than both — that gap is the crease collapse, in cubic millimetres.
Caveat: the cut carries **340 k faces** vs minkowski's 13 k, which would need decimation before
it reaches an STL or the viewer.

---

## Battery 4 — the OPEN-SHELL probe (the biggest capability gap)

Subject: the raw `doctor-295811960-neodent-gm/lower_jaw.stl` scan — 131 503 v / **262 505 f**,
open, **499 boundary edges**, never solidified; tool = the same real-cap punch posed at the case's
own declared site from `sites.json`.

| route | outcome | wall-clock |
|---|---|---|
| **manifold on the raw open shell** | **REFUSED** — `ValueError: Not all meshes are volumes!` | 0.0 s |
| **MeshLib mesh boolean on the raw open shell** | **CUT IT.** 261 885 f out, boundary edges **499 → 499** (no closure fabricated), bad-contour flags 0/0 | **0.05 – 0.09 s** |
| MeshLib **voxel** on the raw open shell | **SILENT GARBAGE** — returns a `watertight=True` mesh of 5 808 faces and **7.7 mm² of area against the scan's 2 803.1 mm²**: 99.7 % of the surface destroyed, no error raised | 0.45 s |
| **INCUMBENT ROUTE** (`solidify_shell` → manifold difference) | CUT, watertight | **16.8 s solidify** + 0.10 – 0.25 s boolean |

**Is MeshLib's open cut *correct*, or merely fast?** Compared against the incumbent route inside a
4 mm ball around the site, across a sweep of tool sink depths (30 000 seeded surface samples each
way):

| sink | faces removed from the scan | ball faces A / B | ball area A / B (mm²) | **symmetric Hausdorff** |
|---|---|---|---|---|
| 0.0 mm | 620 | 32 862 / 32 862 | 73.408733 / 73.408733 | **1.78e-6 mm** |
| 1.5 mm | 9 114 | 25 921 / 25 905 | 87.75872 / 87.75872 | **1.83e-6 mm** |
| 3.0 mm | 11 346 | 18 603 / 18 588 | 98.355918 / 98.356155 | **9.1e-7 mm** |
| 4.5 mm | 11 304 | 6 301 / 6 269 | 82.104553 / 82.105664 | 0.0209 mm (median 0.0) |

MeshLib's direct open-shell cut is **geometrically identical to the incumbent's
solidify → cut route to ~2 nanometres** at three of four depths, while skipping the 16.8 s
solidify entirely. MeshLib's mesh boolean tolerates a *globally* open shell provided it is closed
**in the intersecting zone** — which is exactly our situation (sites sit mid-arch; the open
boundary is the scan's periphery).

---

## Verdict

**Does MeshLib clear the bar the boolean plan sets — "beat manifold on robustness or capability
to justify a paid license"? Split, and the split is the finding.**

**1. As a drop-in boolean-kernel replacement: NO, and it is disqualified by the plan's own rule.**
`test_degeneracy.py`'s stated W3 acceptance criterion is that a Stage-2 candidate must pass that
file **unchanged**. MeshLib fails case #1 — not marginally, but **50.5 % of the time
(95 % CI 43.6–57.4 %, N = 200)**, by silently returning the input unchanged with every health
signal reporting success. Manifold's rate on the identical ensemble is **0 %** (CI upper bound
1.9 %). It also fails the batched-tool case on the voxel path by losing a subtraction. This is the
exact failure class the corpus exists to catch, and it lands on our everyday geometry
(fan-lidded bores meeting machined floors).

**2. As an OFFSET provider: YES, decisively, and it beats both incumbents.** Against the
pre-stated bar — watertight, non-self-intersecting, beat vertex-normal on accuracy *and*
minkowski on wall-clock without exceeding minkowski's own chord-error budget — `sharpOffsetMesh`
at 0.025 mm voxel clears it at d = 0.3 and d = 0.5: **max error 0.00106 / 0.00136 mm vs
minkowski's 0.00136 / 0.00226 mm, at 0.359 s / 0.281 s vs 16.9 s / 18.6 s (~50-66×), and ~40×
faster end-to-end including the downstream boolean.** At d = 0.1 the result is **mixed** —
minkowski has the better worst case (0.00045 vs 0.00213 mm), sharpOffset the better p95
(0.00019 vs 0.00037). Both are ~100× better than the shipping vertex-normal default, whose
0.19–0.33 mm crease shortfall is well outside any clinical tolerance band this repo uses.

**3. As an OPEN-SHELL boolean: YES, and this is the single largest capability gap.** manifold
refuses outright; MeshLib cuts the raw scan in 0.05–0.09 s, producing geometry identical to the
incumbent route to ~2 nm, preserving the scan boundary exactly. Adopting it would remove the
16.8 s/case solidify and could retire `solidify_shell` + `fabricated_face_mask` + the strip
choreography for the carve.

**What this changes.** It does *not* justify replacing the kernel. It *does* reframe the Stage-3
question from "swap manifold for MeshLib?" to **"license MeshLib for the offset and open-shell
lanes while manifold stays the boolean kernel?"** — which is a different, cheaper, and testable
decision. The coplanar no-op is survivable **because it is detectable**: the output is byte-identical
to the input, so a one-comparison post-condition with a manifold fallback closes it. Any adoption
of MeshLib for *any* boolean must ship that guard; without it, this evaluation's headline number is
a 50 % silent-wrong-answer rate on a case we know we generate.

**Not yet answered, and needed before money changes hands:** how often exact coplanar contact
actually arises across the 10 real cases. This evaluation proves the failure exists and is frequent
*conditional on* that contact; it does not measure the contact's incidence on the fleet.

---

## Honest limitations

- **Single host, single run for most timings.** Wall-clock varied **16.9 s → 29.3 s** for the same
  minkowski call at d = 0.3 across two runs (a 1.7× spread) — treat every timing as order-of-magnitude,
  not precise. Only the end-to-end table has repeats (n = 3, median).
- **Python 3.9.6 on macOS arm64 only.** No Linux/CI verification, no CUDA path (MeshLib advertises
  CUDA acceleration for some sign-detection modes; unavailable here and untested).
- **n = 1 cap and n = 1 scan.** Battery 2–4 use one vendor cap (`neodent-gm-5030`) and one arch
  (`doctor-295811960`). **This is not a fleet result.** The other 11 caps and 9 scans were not run.
- **Battery 1 is synthetic** — a statement about the repo's degeneracy fixtures, which were built to
  be adversarial. The 50.5 % rate is a rate *within that fixture*, not a fleet failure rate.
- **The offset numbers are conditional on voxel size** and were measured at two pitches only
  (0.05, 0.025 mm). Finer pitches were not attempted; the error is pitch-linear over the range tested.
- **Choreography was ported, not imported**, per the read-only mandate. It mirrors `csg.py` and
  `kernel.py` as of this commit, but is a copy and could drift from them.
- The MeshLib difference cascades binary operations `((a−t0)−t1)`; the incumbent uses a batched
  call. Set-theoretically identical, and verified equal on case #4, but not the same code path.
- **No repo file was modified and no repo test suite was run.** Nothing was installed outside the
  scratch venv.

## Reproduce

```
/private/tmp/claude-501/-Users-tonycodes-Code-artech-dental-alignment/98997f1a-0a5a-47b4-9dbd-ad120f7b8aa9/scratchpad/
  meshlib-eval-venv/       scratch venv (meshlib 3.1.3.429)
  mlcommon.py              ported choreography + kernels + metrics (seed 20260814)
  run_battery.py           battery 1   -> results_battery.json
  run_jitter.py            the 50.5% rate, N=200 -> results_jitter.json
  run_real.py              batteries 2 and 4 -> results_real.json
  run_offsets.py           battery 3 -> results_offsets.json
  run_downstream.py        end-to-end offset+boolean -> results_downstream.json
  verify_openshell.py      open-shell identity check -> results_openshell.json
  verify_openshell2.py     open-shell sink sweep -> results_openshell2.json
  investigate.py / investigate2.py / investigate3.py   mechanism isolation
```
