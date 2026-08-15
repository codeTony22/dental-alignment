# The boolean engine: first principles, the industry, and the implementation plan

2026-08-11 · research + engineering plan, requested by the client alongside §10-AT
front 3 ("booleans").

> **Era note (2026-08-14):** Parts I–II describe the system AS IT STOOD when this
> plan was written; Stage 0–1 have since executed and changed it (the env is now
> pinned; the strip is provenance-based, not distance-based; the self-heal —
> which Part I describes as load-bearing — was found to have NEVER fired until
> fixed on 2026-08-14). Per this repo's convention the original text stands as
> written; the Stage 2 results below, the Stage 2 addendum, and the §10-AT
> ledger are the current truth, and `kernel-decision-memo.md` is the decision. Two questions answered in order: **(a)** what exists in the
open-source mesh-boolean world and what each piece may legally do inside a
commercial product, and **(b)** an honest, staged path to a PROPRIETARY,
COMMERCIAL boolean operator for ArTech.

Doctrine this plan is bound by (§10-AS.14/16/19, client 2026-08-10/11): the
artifact is the **open arch**; the cut is the **exact healing cap + the chosen
gingival offset, nothing inferred**; `solidify_shell` is **internal-only** — a
solid exists for the one instant of the cut and is stripped before anything
ships. Any engine that cannot express that choreography is disqualified no
matter its license.

---

## 0 · First principles — what the operation is, and where the hardness lives

**A boolean is a statement about volumes, not meshes.** Solid A minus solid B is
defined pointwise: a point is in the result iff it is in A and not in B. A mesh
is only the BOUNDARY of a volume. So every mesh boolean, in every engine ever
shipped, is the same five moves:

1. find the intersection curves where ∂A crosses ∂B;
2. split the faces of both meshes along those curves;
3. classify every resulting patch — inside, outside, or on the other solid;
4. keep patches per the operation's truth table (difference keeps A-outside-B
   and B-inside-A flipped; union keeps both outsides; intersection both insides);
5. stitch the kept patches into a closed, manifold boundary again.

All the difficulty in fifty years of this field lives in moves 1 and 3, for one
reason: **floating-point geometry lies near degeneracy**. Two faces that are
exactly coplanar (our bore lids on machined floors), edges that graze
(a floor clip at exactly the cap's base), triangles a scanner emitted with
near-zero area — a naive implementation gets a predicate wrong by 1e-16 and the
classification flips, and the output is a non-manifold shred. The industry has
exactly four families of answer:

| family | idea | cost | exemplars |
|---|---|---|---|
| **Exact arithmetic / arrangements** | evaluate every predicate in rational or expansion arithmetic so it can never lie; degeneracy handled by symbolic perturbation | slow; enormous implementation burden; the gold standard for correctness | CGAL Nef & corefinement, Blender's exact solver (Zhou 2016), trueform |
| **ε-consistent floating point with topological guarantees** | track error intervals, weld within ε, and construct the output so manifoldness is guaranteed by the algorithm, not checked after | fast, parallel, robust in practice; ε is a modelling admission | **manifold (ours)**, Smith & Dodgson's method it descends from |
| **Plane-based / BSP** | represent geometry as plane arrangements; booleans become logic on half-spaces | exact for few planes; wrong tool for 400k-triangle curved scans | QuickCSG, classic CSG kernels |
| **Volumetric / SDF** | sample both solids into signed-distance grids; boolean = per-voxel min/max; re-extract a surface | unconditionally robust; RESOLUTION-LIMITED — the exact cap surface is resampled away | OpenVDB, Meshmixer-era tools, MeshLib's voxel path |

**How the dental industry itself does it:** the big CAD suites (3Shape, exocad)
embed licensed BREP/hybrid kernels or long-lived proprietary mesh kernels, and
lab-side mesh tools historically used the volumetric route for repair because it
cannot fail. Nobody publishes an open-shell clinical boolean; the closest
published primitive (MCUT's open-surface cuts) is LGPL/commercial-dual.

**Our requirements, derived from the product's goals rather than from any
library** (each traces to a shipped behaviour or a client ruling):

1. **Difference** — the recess: the exact cap + gingival offset out of the arch
   (§10-AS.14 "we should not be inferring anything here").
2. **Union** — fused composites and punch self-healing (§10-AT 3b).
3. **Intersection** — the visible-depth floor clip, only ever shallowing.
4. **Offset/dilation** — the gingival offset itself, today vertex-normal + heal,
   tomorrow Minkowski-sphere.
5. **On OPEN SHELLS against closed CAD parts** — the defining constraint. Scans
   are boundaries of nothing; caps are watertight but bore-open, coplanar-heavy,
   feature-dense.
6. **Never a dead package** — every operation carries a fallback ladder with a
   manifest note (the §10 doctrine of honest degradation).
7. **The claim must be exact where it is clinical** — the cut surface is the
   cap's own; ε lives in welding, never in the tool's shape.
8. **Deterministic and attestable** — same inputs, same artifact, hashable into
   the manifest the confirmation seals.
9. **Interactive re-emit** — seconds, not minutes, on a 400k-triangle arch
   (§10-AC's ~1s promise stretched, not broken).

**The open-shell reduction — our own first principle.** Set theory needs
volumes, and a scan has none. Our answer (invented here, now in
`pipeline/csg.py`) is a reduction we can state precisely, and it is the thing
worth owning:

> **The shell-boolean contract.** For an open shell S and solid tools T₁…Tₙ,
> choose a canonical closure S̄ (skirt + base + lids). Compute the solid result
> R = S̄ op T₁ … Tₙ. Ship ∂R **restricted to** (surfaces of S) ∪ (surfaces of
> the tools) — the closure is scaffolding and never ships.
>
> Properties the corpus must hold forever: **locality** (far from every tool,
> the shipped surface is bit-identical to the scan); **conservativity** (no
> shipped triangle originates from the closure); **clinical exactness** (every
> shipped cut triangle lies on a tool's true surface).

Everything in Part III is an improvement to how faithfully and robustly we
implement this contract; Part II is what the rest of the world offers us to
build it on.

---

# Part II — what exists, and what it may legally do


## 1 · What ArTech runs today

`apps/worker/src/case_prep/pipeline/csg.py` — mechanism only, split from
`deliverables.py` at §10-AT front 3a/3c. The stack under it:

| layer | what | license |
|---|---|---|
| orchestration | trimesh 4.12.2 (`trimesh.boolean`, `engine="manifold"`) | MIT |
| kernel | **manifold3d 3.5.2** (the `manifold` C++ library, nanobind wheel) | **Apache-2.0** |
| numerics | numpy / scipy (cKDTree in `strip_fabricated`) | BSD |

Runtime: Python 3.9.6, macOS dev, environment **unpinned** (a standing risk this
plan closes in Stage 0).

The choreography — and this is the part no surveyed library provides — is
in-house invention, four moves:

1. **Solidify** (`solidify_shell`): the open intraoral shell's longest boundary
   loop becomes a skirt extruded along the crown axis to a flat fanned base
   1.5 mm past the deepest point; every smaller loop gets a planar lid. Open
   scan → watertight lab solid, cached per mesh content
   (`solidified_shell_cached`).
2. **Punch** (`exact_cap_punch`): the vendor cap's OWN CAD solid at its aligned
   pose. The open implant-interface bore is fan-lidded (`_lid_boundary_loops` —
   an honest closure of a KNOWN loop, not inference); the gingival offset is a
   vertex-normal dilation whose concave-crease self-intersections are healed by
   a **manifold union of the punch with itself**; a visible-depth floor clip is
   a box intersection that only ever shallows the tool, degrading to a no-op
   rather than fabricating an extension. `punch_solid` (the lathed revolute
   envelope, apex extended 2 mm) survives as the per-site fallback only.
3. **Cut**: manifold difference of solid minus punches.
4. **Strip** (`strip_fabricated`): every face that is neither a punch/recess
   surface nor within 0.35 mm of a dense sample of the original scan is
   discarded — the base plate and skirt vanish, and the artifact is the scan
   itself wearing machined cap-width recesses.

The known gap, flagged in-code: manifold3d 3.5.2 has **no `offset` API**, but it
does expose `minkowski_sum` — a sum with a small sphere is a true morphological
dilation that cannot self-intersect by construction, and is the standing
candidate to replace vertex-normal dilation + self-heal.

The existing pins over this machinery (they become the Stage-0 conformance
corpus): `apps/worker/tests/test_csg.py` (9 tests: solidify watertightness,
punch watertightness with open bores, refusal on empty templates, the
self-healing punch, strip keeping cut+surface and dropping the base),
`apps/worker/tests/test_deliverables.py` (25), `apps/worker/tests/test_emit.py`
(5), plus the real-mesh slow lane and `make rehearse`.

---

## 2 · The three repos the client named

### 2.1 [MeshInspector/MeshLib](https://github.com/MeshInspector/MeshLib)

- **What**: a large C++ 3D-processing SDK (AMV Consulting / MeshInspector) —
  mesh AND voxel booleans ("up to 10× faster" claimed), **real offsetting with
  multiple modes** (the one capability our stack lacks natively), repair,
  hole-filling, decimation, ICP, segmentation. Half-edge structure with manifold
  compliance enforced.
- **Bindings**: C, C#, **Python (`pip install meshlib`)**; Windows/macOS/
  Linux/WASM.
- **Health**: strong — ~7,300 commits, active issues/PRs, ~805 stars, corporate
  backing.
- **License — read from [the LICENSE file itself](https://raw.githubusercontent.com/MeshInspector/MeshLib/master/LICENSE)**:
  the "Non-Commercial & Education License Agreement" grants use "solely for
  non-commercial, evaluation or educational purposes", terminable on notice,
  destruction within 5 days on termination, audit clause with 30 days' notice,
  liability capped at $100, Nevada law. **Commercial embedding requires a paid
  license from AMV.** The free tier DOES cover evaluation — which is exactly
  what Stage 2 uses it for.
- **Verdict**: the strongest *licensed contender*: closest capability match
  (offset + booleans + repair in one SDK, Python-native). Not free for the
  product; a price conversation, not a legal impossibility.

### 2.2 [miho/OCC-CSG](https://github.com/miho/OCC-CSG) + the OpenCascade kernel

- **What**: a small (~324 commits, 79 stars) **command-line** CSG convenience
  tool over OpenCascade 7.4 — union/difference/intersection on BREP/STEP/STL,
  primitives, transforms, mesh→BREP conversion. LGPL-3.0 itself; the real
  machinery is [OCCT](https://github.com/Open-Cascade-SAS/OCCT):
  **LGPL-2.1 with the OCCT exception** (`OCCT_LGPL_EXCEPTION.txt`), actively
  maintained (~7,100 commits, 2.7k stars), commercial support from Open Cascade
  SAS.
- **The technical mismatch**: OCCT is a **BREP** (analytic boundary
  representation) kernel. Our inputs are 100k–400k-triangle scan meshes; running
  them through OCCT means tessellated-BREP conversion, and booleans over
  triangulated BReps are the classic weak spot of BREP kernels — slow and
  fragile at exactly our mesh sizes. OCC-CSG being a CLI, not a library API,
  adds a process boundary per cut.
- **Verdict**: legally workable (LGPL + exception, dynamic linking), technically
  the wrong kernel class for scan-mesh CSG. Not a candidate.

### 2.3 [polydera/trueform](https://github.com/polydera/trueform)

- **What**: young (133 stars, 193 commits) header-only C++17 geometry library —
  "fast and exact" mesh booleans via **exact predicates and canonical
  topology**, AABB trees, curvature, ICP, decimation. oneTBB parallelism;
  Python (NumPy) and WASM bindings; VTK/Blender integrations.
- **License**: **dual** — PolyForm Noncommercial 1.0.0 for free use; commercial
  use requires a paid license ("Contact info@polydera.com").
- **Health**: active CI and docs, but small and young; no track record at the
  OpenSCAD/Blender scale of adoption manifold has.
- **Verdict**: technically interesting (exact predicates in a modern, small
  package) but commercially it sits in the same seat as MeshLib — a paid
  license — with far less production mileage. Watch; do not build on.

---

## 3 · The wider landscape — license matrix

"Commercial embedding" = shipping inside ArTech's closed product. Licenses read
from the repos themselves, 2026-08-11.

| library | license | commercial embedding | robustness approach | open-shell handling | health |
|---|---|---|---|---|---|
| [manifold](https://github.com/elalish/manifold) (in use) | **Apache-2.0** | **yes, unconditionally** | ε-valid approximate arithmetic with **guaranteed-manifold topology** (Smith-style; manifold-by-construction, not exact math) | none — inputs must be manifold solids (our solidify exists for this) | excellent: 2.2k stars, used by OpenSCAD, **Blender**, Godot + 30 more |
| [MeshLib](https://github.com/MeshInspector/MeshLib) | Non-Commercial & Education | **paid license** (free tier covers evaluation) | mesh- and voxel-based booleans; half-edge manifold enforcement; native **offset** | repair/hole-fill tooling adjacent | excellent, corporate |
| [trueform](https://github.com/polydera/trueform) | PolyForm-NC / commercial dual | **paid license** | exact predicates + canonical topology | not advertised | young, active |
| [OCC-CSG](https://github.com/miho/OCC-CSG) / [OCCT](https://github.com/Open-Cascade-SAS/OCCT) | LGPL-3.0 / **LGPL-2.1 + OCCT exception** | yes with dynamic-link care | BREP algebra, not mesh arrangements | poor fit for scan meshes entirely | wrapper dormant; OCCT strong |
| [CGAL](https://www.cgal.org/license.html) Nef & [PMP corefinement](https://doc.cgal.org/latest/Manual/packages.html) | kernel LGPL; **Nef GPL; PMP GPL** | **no** without a paid GeometryFactory license | exact arithmetic (gold standard for correctness; slowest) | corefinement can clip open meshes | excellent |
| [libigl](https://github.com/libigl/libigl) mesh boolean | core MPL-2.0; `igl/copyleft/cgal` **GPL-3** | **no** for the robust boolean (it lives in copyleft/ and calls CGAL exact) | CGAL exact arithmetic + winding numbers | some (winding-number machinery) | good |
| [Cork](https://github.com/gilbo/cork) | LGPL | technically yes | float with perturbation; "a number of known problems" (author) | none | **abandoned since ~2016** |
| [MCUT](https://github.com/cutdigital/mcut) | **LGPL-3 / commercial dual** (CutDigital, priced by company size) | LGPL with care, or paid | robust geometric predicates | **yes — explicit partial-cut / open-surface support** | active, 496 stars |
| [vtkbool](https://github.com/zippy84/vtkbool) | **Apache-2.0** | yes | float with tolerant intersection handling; copes with some non-watertight input | partial | maintained, small (187 stars); VTK dependency |
| Blender exact boolean ([Mesh Arrangements](https://developer.blender.org/docs/release_notes/2.91/modeling/), Zhou et al. 2016) | **GPL-2+** | **no** | exact GMP rational arithmetic + generalized winding numbers | winding numbers tolerate some openness | inside Blender only |
| [Interactive & Robust Mesh Booleans](https://github.com/gcherchi/InteractiveAndRobustMeshBooleans) (Cherchi et al. 2022) | **MIT** | yes | floating-point arrangements with indirect (lazy-exact) predicates | no | research code; authors state they **cannot support it** |
| [EMBER](https://dl.acm.org/doi/10.1145/3528223.3530181) (2022) | paper only | n/a | fixed-width multiprecision integer local arrangements | no | no embeddable release |
| QuickCSG-style plane-based ([Douze et al.](https://arxiv.org/abs/1706.01558)) | research code; license unverifiable today — treat as unusable | assume **no** | vertex-centric plane-based, extremely fast, **no** exact arithmetic — fragile on coplanar/degenerate input (our bore lids and flat floors are exactly that) | no | dormant |
| [OpenVDB](https://github.com/AcademySoftwareFoundation/openvdb) | **Apache-2.0** (relicensed from MPL-2.0) | yes | volumetric level-set CSG — unconditionally robust, but **resamples the surface at voxel resolution** | trivially (SDF doesn't care) | excellent (ASWF) |

Three cross-cutting reads:

1. **The permissive shortlist is short**: manifold (in use), vtkbool, the
   Cherchi MIT research code, OpenVDB, Geogram
   ([BSD-3, active, SGP software award 2023](https://github.com/BrunoLevy/geogram),
   exact-arithmetic mesh intersections — a credible second permissive kernel).
   Everything CGAL-derived is GPL-walled; everything else robust-and-modern is
   dual-licensed commercial.
2. **Volumetric (OpenVDB/SDF) booleans are doctrinally disqualified for the
   cut**: §10-AS.14 demands the exact cap surface; a level-set round-trip
   resamples every wall at voxel pitch — and the repo has already measured this
   class of hazard (the mesh_to_sdf pitch-dependent seal, caps vanishing at fine
   pitch). SDF remains legitimate as an *offset* fallback only if Minkowski
   proves inadequate, with the deviation measured and gated.
3. **Nobody ships our open-shell choreography.** MCUT is the only library even
   advertising open-surface cuts, and it is LGPL/commercial-dual. The
   solidify→punch→cut→strip cycle with bore lidding, self-healing dilation and
   fabrication stripping exists in exactly one place: this repo.

---

## 4 · What building a robust mesh boolean from scratch actually takes

The honest algorithm survey, because the plan's economics hang on it.

**The problem is not the easy 95%.** Intersecting two clean, generically-posed
meshes is a term project. The remaining 5% is the entire discipline:

- **Exact predicates.** Every orientation/incircle decision must be consistent
  or the arrangement's topology contradicts itself. The industry answers:
  exact rational arithmetic (CGAL, Blender/GMP — correct, slow), floating-point
  expansions with filters (Shewchuk predicates, Geogram), indirect/lazy-exact
  predicates (Cherchi 2020/2022), fixed-width integers (EMBER), or manifold's
  inversion of the problem — accept ε-error but **never ask the same geometric
  question two ways**, guaranteeing topological manifoldness rather than
  geometric exactness.
- **Coplanarity and degeneracy.** Our workload is adversarial here by
  construction: fan-lidded bores are perfectly planar disks; `punch_solid`
  floors are machined flats; the box clip in `exact_cap_punch` mates a plane
  against a plane. Coplanar-face handling is where floating-point booleans die,
  and it is not an edge case for us — it is every cut.
- **Self-intersection tolerance.** Vendor STLs and dilated punches arrive
  self-intersecting; a from-scratch kernel needs arrangement-based resolution
  (Zhou et al.) or a union-with-self idiom like ours.
- **Manifoldness guarantees out.** Downstream (slicers, viewers, the strip
  mask) needs watertight-where-claimed output; guaranteeing it under all inputs
  is the part Lalish calls the first of its kind in manifold.
- **Then the unglamorous 80%**: BVH broad phase at 400k triangles,
  re-triangulation quality, attribute propagation, exhaustive fuzzing, and
  years of issue-tab hardening. Manifold, with a world-class author and heavy
  adoption pressure, took years to earn Blender's and OpenSCAD's trust.

**Effort, honestly sized**: a production-robust general kernel is **12–24
person-months** for a senior geometry team, with a long defect tail measured in
years of field hardening — and at the end it does what Apache-2.0 manifold does
today. **What the industry does**: commercial CAD overwhelmingly licenses a
kernel ([Parasolid is the most-licensed](https://en.wikipedia.org/wiki/Parasolid);
ACIS/CGM fill the mid-tier) or spends a decade building in-house; dental CAD
vendors' mesh engines are the product of exactly such decade-scale in-house
programs. Nobody rebuilds exact mesh arithmetic as a side quest.

---

## 5 · Build vs buy — the licensing truth and where the IP actually is

**The licensing truth, stated plainly:**

- What ArTech ships today — trimesh (MIT) over manifold3d (**Apache-2.0**) — is
  **already commercially safe, royalty-free, forever**. There is no licensing
  emergency.
- LGPL (OCCT, MCUT, Cork) is linkable-with-care (dynamic linking, notices), but
  nothing in that column is technically compelling for us.
- MeshLib and trueform are **paid-license** for commercial use; their free tiers
  are evaluation-only.
- CGAL's exact booleans, libigl's robust path, and Blender's exact boolean are
  **GPL-walled** — not embeddable without GeometryFactory's paid dual license or
  open-sourcing the product.

**Where the proprietary value honestly is.** Re-implementing exact mesh
arithmetic is a multi-quarter, high-risk **commodity rebuild** — the output
would be functionally indistinguishable from a free Apache-2.0 library and
legally no more ours than manifold already is (Apache-2.0 code may be embedded,
modified, and kept closed). The differentiating, ownable IP is the layer this
repo already invented, none of which exists in any surveyed library:

- **Booleans on open intraoral shells**: the solidify→cut→strip cycle that lets
  a solid-only kernel serve an open-arch doctrine (§10-AS.16/19).
- **Exact-implant-part punches**: vendor-CAD-exact cut tools with honest bore
  lidding, offset dilation, the union-with-self self-heal, and the
  only-ever-shallower floor clip (§10-AS.14, §10-AT front 3a).
- **The clinical contracts around them**: gum-following floors, deviation-aware
  clearances and their retirement history, per-site fallback semantics, the
  fabrication-strip mask with its measured 0.35 mm surface-sample test.

**The proposal: package THAT as the proprietary engine — "ArTech CSG".** A
named module/library owning the clinical boolean layer, with a
**kernel-abstraction seam** underneath: a narrow port (union / difference /
intersection / validity) that manifold satisfies today and any licensed or
from-scratch kernel can satisfy later if IP strategy demands. The proprietary
claim then rests on the clinical choreography — which is genuinely novel —
rather than on a rebuilt commodity, and the kernel question converts from a
blocking bet into a swappable, measurable decision.

---

# Part III — the implementation plan: improving OUR boolean operations

Derived from the contract's properties and this week's measured pain, ordered by
leverage. Each workstream names its acceptance criterion; all of them run on the
Stage-0 conformance corpus below, and nothing ships without the fleet battery
and `make rehearse`.

### W1 · Provenance replaces proximity in the strip (highest leverage)

**Measured today:** `strip_fabricated` decides "fabricated vs real" by distance
to a 150k-point sample of the original scan (0.35 mm) — it mis-stripped coarse
fixtures until the sampling was densified, and its threshold is a modelling
admission. **Verified this session:** the manifold Python binding exposes
`Manifold.original_id` / `as_original` / `reserve_ids` — face PROVENANCE that
survives booleans. Tag the closure, the scan surface, and each tool with
reserved ids before the cut; after it, keep faces whose provenance is scan or
tool, drop closure faces **by identity, not by distance**. The contract's
conservativity property becomes exact rather than sampled.
*Acceptance:* the corpus's strip pins pass with the distance fallback deleted;
locality becomes bit-identity on untouched regions (hash-compared).

### W2 · Minkowski-sphere offset replaces vertex-normal dilation

The gingival offset is clinical; its implementation today can self-intersect at
concave creases and leans on the union-with-self heal. `minkowski_sum` with an
icosphere of radius = the offset is a true morphological dilation that cannot
self-intersect by construction. The heal remains as a belt-and-braces wrapper.
*Acceptance:* every catalog cap × offset ∈ {0.1..0.5} yields a watertight punch
with no heal fired (log the heal's firings; corpus asserts zero on catalog
parts); cap6030 stays the sentinel.

### W3 · The degeneracy battery

The corpus gains the cases that break naive engines, because they are OUR
everyday geometry: exactly-coplanar bore lid on a machined floor; the floor
clip at exactly the cap's base plane; duplicate/zero-area scan triangles
(pre-welded, with a logged count); two adjacent sites whose punches touch;
a punch tangent to the skirt. Each is a named corpus case with the expected
manifold-and-contract outcome.
*Acceptance:* all pass on the current kernel; any future kernel candidate must
pass the same battery to enter Stage 2.

### W4 · Determinism and attestation

Same inputs must yield the same artifact bytes (the confirmation seals hashes).
Pin the environment (worker deps frozen — closes the standing unpinned-env
risk); assert corpus outputs are hash-stable across two runs and across
`-n auto` workers; if the kernel introduces nondeterminism, canonicalize
(sorted faces, welded order) before export.
*Acceptance:* a corpus job runs the full artifact set twice and diffs hashes.

### W5 · Open-shell robustness

The solidify walker assumes clean boundary cycles; a figure-8 junction or a
non-manifold scan edge would confuse it. Harden: boundary extraction via edge
multiplicity with explicit junction handling, refusal notes naming the loop;
multi-loop scans covered by corpus cases built from real-fleet boundary shapes.
*Acceptance:* every fleet scan solidifies with loop counts logged; a synthetic
figure-8 refuses with its named note rather than mis-skirting.

### W6 · The performance budget

Emit currently pays one solidify (cached) + up to three cuts. Budget: ≤ 5 s
added per emit on the fleet's largest arch, measured in the corpus as a
regression bound; batched punches stay one difference call; preview meshes may
decimate, downloads never.
*Acceptance:* a timed corpus case fails if the budget is exceeded.

The strategic stages below stand as the frame around these workstreams: W1–W6
are Stage 1's concrete content; Stage 0 builds the corpus they run on; Stages
2–3 remain the measured kernel decision.

## 6 · The staged plan

### Stage 0 — the kernel seam and the conformance corpus (~1–2 weeks)

- Extract a `BooleanKernel` port (protocol in `case_prep.domain` or a new
  `case_prep/csg_engine/` package): `union(meshes)`, `difference(a, b)`,
  `intersection(a, b)`, `is_valid_solid(mesh)` — the only surface `csg.py` may
  call. The manifold adapter is the first and default implementation. Tests
  first; behaviour identical by construction.
- **The conformance corpus is the repo's own pins**: `test_csg.py` (9),
  `test_deliverables.py` (25), `test_emit.py` (5), the slow-lane real-mesh
  battery, and `make rehearse` baselines. Add golden **metric** assertions per
  fleet case (recess mouth diameter vs cap+offset, floor height vs floor_a,
  volume removed, watertightness of cut surfaces, strip mask face counts) so a
  kernel swap is judged on clinical numbers, not bit-identical meshes.
- Pin the environment (`manifold3d==3.5.2` et al.) — the unpinned env is a
  standing risk this stage retires.
- Freeze-line note: all of this is worker/product side; `apps/web` and the
  frozen `server.py` are untouched.

### Stage 1 — harden and name the proprietary clinical layer (~3–6 weeks)

- Promote the choreography into the **ArTech CSG** package with typed,
  documented contracts: `solidify (internal) → punch → cut → strip`, open-shell
  invariants expressed in types (an `OpenShell` is not a `Solid`; only the
  engine may convert, and only transiently).
- **Offset via Minkowski sum with a sphere** (manifold3d's `minkowski_sum`)
  replacing vertex-normal dilation as the primary gingival-offset path — a
  dilation that cannot self-intersect by construction. The union-with-self
  self-heal stays as the belt behind the suspenders; the envelope fallback and
  its per-site note are unchanged. Measure the recess-wall delta on the fleet
  before flipping the default (cap6030's creased rim is the sentinel case).
- Tolerant pre-weld (bounded, reported vertex merging for vendor STLs) as an
  explicit, logged step — never silent mutation, per re-click-pair doctrine.
- The corpus from Stage 0 is the acceptance gate for every change here.

### Stage 2 — the evaluation gate (~2–4 weeks, plus license conversations)

Run three contenders over the identical conformance corpus + fleet battery,
scored on: corpus pass rate, clinical-metric deltas, wall-clock per cut, failure
modes on the adversarial coplanar set (bore lids, floor clips), and open-shell
cycle survival.

1. **manifold** (incumbent, Apache-2.0) — the bar to beat.
2. **MeshLib trial** — its license expressly permits evaluation; also scores its
   native offset against our Minkowski path. If it wins on robustness or the
   offset, that becomes a priced option on the table, not a default.
3. **A scoped from-scratch spike** (2–3 weeks, timeboxed): a minimal
   arrangements-based difference on the corpus only — not to ship, but to price
   the real thing with evidence instead of §4's literature estimate.

Deliverable: a scoreboard and a written recommendation. No kernel changes ship
from this stage.

### Stage 3 — the kernel decision (only now)

Decide with evidence: **(a)** stay on manifold behind the seam (the default —
zero cost, zero legal exposure, proprietary layer intact); **(b)** license a
kernel (MeshLib/GeometryFactory/trueform) if Stage 2 shows a robustness or
capability gap worth the fee; or **(c)** fund a from-scratch kernel — honestly
sized at **12–24 person-months** with the §4 risk register (predicate
consistency, coplanar handling, the multi-year defect tail, key-person risk) —
only if the IP strategy demands owning the arithmetic itself and the spike's
numbers support the price. The seam makes any of the three a bounded swap, not
a rewrite.

### Stage 2 results — the MeshLib evaluation (2026-08-14, contender #2 run)

Full scoreboard: `meshlib-scoreboard-2026-08.md` (meshlib 3.1.3.429, free
evaluation tier, scratch venv — the pinned worker env untouched). Three
verdicts, which REFRAME Stage 3:

1. **As a kernel replacement: disqualified.** On the degeneracy battery's
   coplanar-bore-lid case — our everyday geometry — MeshLib's mesh boolean
   SILENTLY NO-OPS: 101/200 seeded clockings (CI 43.6–57.4%) return the
   input unchanged with `valid()=True`, empty error state, watertight
   output. manifold: 0/200. The failure is a ±1e-7 knife-edge around exact
   coplanarity and is not detectable by MeshLib's own defect queries — only
   by the caller comparing output to input. Its voxel path fails the
   battery outright and does not compose across sequential subtractions.
2. **As an offset provider: decisively better than everything we have.**
   sharpOffset at 0.025mm voxel pitch: 0.00136mm max error at 0.281s —
   vs our Minkowski reference 0.00226mm at 18.6s and vertex-normal's
   0.49mm worst-case crease shortfall at ~0s. End-to-end offset+cut:
   0.738s vs 29.4s, agreeing to 0.034mm³. (Voxel-pitch-conditional:
   halving pitch halves error.)
3. **As an open-shell boolean: the largest single win.** It cuts the raw
   262k-face open scan in 0.05–0.09s, boundary preserved, matching the
   incumbent solidify→cut→strip route to 1.8e-6mm symmetric Hausdorff —
   skipping the 16.8s solidify FOR THE CARVE LANE. (Qualifier that must
   travel with the claim: the closed model and the fused composites are
   BUILT from the solid, so an emit producing them still pays the
   solidify; the per-arch cache is what reconciles that cost with W6's
   ≤5s budget. And its voxel path on the same shell returns watertight
   garbage — mesh path only.)

**The reframed Stage 3 question** is no longer "swap manifold" but:
license MeshLib for the OFFSET and OPEN-SHELL lanes behind the seam, keep
manifold as the kernel, and wrap every MeshLib boolean in a mandatory
no-op guard (output-equals-input comparison — cheap, and the failure mode
is exactly detectable that way). Honest limitations: n=1 cap, n=1 scan,
single host, wall-clocks order-of-magnitude. **The one measurement owed
before any money conversation: the fleet incidence of exact-coplanar
contact in production geometry** — the no-op failure is frequent
conditional on that contact; its unconditional rate on real cases is
unmeasured.

### Stage 2 addendum — the incidence measurement (2026-08-14, fleet)

All 115 boolean calls the emit lanes make, reconstructed on the real
fleet (9 cases, 10 sites, 125 operand pairs; bucketed plane census,
22s):

- **Between DISTINCT solids: zero incidence** — 0/75 calls, 0 face pairs
  in every band down to <1e-3mm, stable across a 10⁵ sweep of the
  parallelism tolerance. The closest production geometry ever gets to
  the ±1e-7 trigger window is 1.56e-4mm.
- **The self-heal is the exception, structurally**: union([p, p]) passes
  the same solid twice — 100% coplanar by construction, 50/50 calls. Run
  against MeshLib on the fleet's own operands: EMPTY output on 16/20
  (with errorString — a different failure than Stage 2's silent no-op).
  The 16 decompose as: 6/10 clean (relief-0) caps failed, of which 4 are
  attributable specifically to the coplanarity (arm A 4/10 non-empty vs
  decoplanarized arm B 8/10); all 10 dilated caps failed regardless of
  coplanarity. The kernel disqualification is confirmed on real data;
  the offset/open-shell lanes are untouched by this result (neither
  makes a coplanar-operand boolean).
- **The near miss**: 4–5 of 20 site×lane configurations put the clip
  plane on the cap's own base BY DESIGN (floor_a = envelope-base), and
  at the accepted production relief 0.00 the margin narrows to 2.1e-7mm
  — held open only by the vendor STL's float32 base-disc scatter
  (7e-7–1e-6mm across all 12 catalog variants). Two vendors' export
  habits are not a guarantee; the guard stays mandatory.
- **A latent containment gap in OUR code, found in passing**: the
  self-heal's `except Exception` would swallow an EMPTY kernel result
  (empty raises nothing; is_watertight False, volume 0) — the punch
  silently becomes empty, the clip keeps it, and the package ships with
  NO recess. Manifold has never produced empty there (20/20), so it
  cannot fire today; it is exactly the hole a kernel swap would fall
  through. The mandated guard is therefore "output ≠ input AND output ≠
  empty", and the heal's catch needs the empty check regardless of any
  licensing decision. Also re-flagged: solidified_shell_cached keys on
  id(arch) — the same address-reuse hazard class W4 retired in
  clock_signature — plus one unexplained, non-reproducing face-count
  observation in its vicinity. Both queued as the hardening pair.

### Verification, per stage

| stage | proof |
|---|---|
| 0 | conformance corpus green under the seam, byte-identical artifacts on the fleet; `make test` (both lanes) + `make rehearse` unchanged; freeze-line diff empty |
| 1 | corpus + golden metrics green; Minkowski-vs-dilation fleet delta report; cap6030 sentinel within band |
| 2 | the scoreboard: same corpus, three kernels, numbers side by side |
| 3 | decision memo citing the scoreboard; if (b)/(c), the seam's adapter tests are the acceptance gate |

---

## 7 · Top-line summary

1. **No licensing emergency**: Apache-2.0 manifold is already safe to embed
   commercially, and it is the best-adopted permissive mesh-boolean kernel in
   existence (Blender itself now uses it).
2. **Of the client's three**: MeshLib is a real (paid) contender and the free
   evaluation tier fits Stage 2; OCC-CSG/OpenCascade is the wrong kernel class
   for scan meshes; trueform is promising but young and equally paid.
3. **The ownable IP is the clinical layer this repo already wrote** — open-shell
   choreography, exact-part punches, self-healing offsets, fabrication
   stripping. Package it as ArTech CSG over a kernel seam; measure before ever
   paying for or rebuilding the commodity underneath.

## Sources

- [MeshLib repo](https://github.com/MeshInspector/MeshLib) · [MeshLib LICENSE](https://raw.githubusercontent.com/MeshInspector/MeshLib/master/LICENSE)
- [OCC-CSG](https://github.com/miho/OCC-CSG) · [OCCT](https://github.com/Open-Cascade-SAS/OCCT)
- [trueform](https://github.com/polydera/trueform)
- [manifold](https://github.com/elalish/manifold) and its wiki (Smith-style ε-valid robustness)
- [CGAL license page](https://www.cgal.org/license.html) · [CGAL package licenses](https://doc.cgal.org/latest/Manual/packages.html)
- [libigl](https://github.com/libigl/libigl) · [Cork](https://github.com/gilbo/cork) · [MCUT](https://github.com/cutdigital/mcut) · [vtkbool](https://github.com/zippy84/vtkbool)
- [Blender 2.91 exact boolean notes](https://developer.blender.org/docs/release_notes/2.91/modeling/) (Zhou et al. 2016 Mesh Arrangements, GMP)
- [Interactive & Robust Mesh Booleans](https://github.com/gcherchi/InteractiveAndRobustMeshBooleans) · [EMBER](https://dl.acm.org/doi/10.1145/3528223.3530181) · [QuickCSG](https://arxiv.org/abs/1706.01558)
- [OpenVDB](https://github.com/AcademySoftwareFoundation/openvdb) · [Geogram](https://github.com/BrunoLevy/geogram)
- [Parasolid](https://en.wikipedia.org/wiki/Parasolid) (industry kernel-licensing pattern)
