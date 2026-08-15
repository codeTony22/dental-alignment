# The kernel decision — Stage 3 memo

2026-08-14 · the decision the boolean-engine plan reserved for evidence, now taken. Body
for the decision-maker; appendix for anyone checking the arithmetic. Every number traces
to [`boolean-engine-plan.md`](boolean-engine-plan.md) or
[`meshlib-scoreboard-2026-08.md`](meshlib-scoreboard-2026-08.md).

---

## 1 · The question

Every artifact this product ships is cut by a *boolean engine* — the software that takes
the arch scan and the exact healing cap and computes "the arch, minus that cap, plus its
gingival offset". Ours is **manifold**: free, Apache-2.0, embeddable in a commercial
product forever with no fee and no royalty. In August we asked three questions in order —
is there a licensed engine that beats it, should we build our own, and, the only one that
costs money, should any money change hands. The plan answered the first two on paper and
then deliberately withheld judgement until there were numbers. There now are: a full
head-to-head against the strongest paid contender (MeshLib) on our own adversarial
corpus, on real vendor CAD, on a real arch scan, and finally across every boolean call
the production pipeline makes on the nine-case fleet. This memo is the decision.

## 2 · The recommendation, plainly

**(a) manifold stays the kernel. No money changes hands today.** Free, Apache-2.0,
commercially safe unconditionally — and it failed nothing we measured: 4 of 4 on the
degeneracy battery, 200 of 200 on the hardest case's randomised ensemble, 20 of 20 on the
fleet's own self-heal operands. There is no licensing emergency and no robustness gap to
buy our way out of.

**(b) A MeshLib license is worth CONSIDERING for exactly two capabilities — never as the
kernel.**

1. **Offset** (the gingival relief around each cap): `sharpOffsetMesh` runs about **60×
   faster than our own correct-by-construction reference** — 0.281 s against 18.6 s at a
   0.5 mm offset (50–66× across the offsets tested, ~40× end-to-end) — at **equal or
   better accuracy**: 0.00136 mm worst error against the reference's 0.00226 mm. At the
   smallest offset tested (0.1 mm) the comparison is mixed and the reference wins the
   worst case (0.00045 vs 0.00213 mm).
2. **Open-shell cutting** (cutting the raw scan without first wrapping it in a temporary
   solid): it matches our whole solidify → cut → strip choreography to **1.8 nanometres**
   while skipping that choreography's measured **16.8 s**, and leaves the scan's open
   boundary untouched (499 boundary edges in, 499 out).

Both are worth considering **if and only if** emit latency or offset quality becomes a
business constraint. **Neither is one today**: emits are seconds, not minutes, and the
shipping vertex-normal offset holds the fleet green. So the honest status is a priced
option, understood and costed — not taken.

**(c) Building our own kernel remains rejected.** Honestly sized at **12–24
person-months** for a senior geometry team plus a defect tail measured in years, at the
end of which we would own a commodity functionally indistinguishable from the free
library we already use. The industry does not do this either: commercial CAD licenses a
kernel or spends a decade building one.

The ownable intellectual property was never the kernel. It is the clinical layer this
repo already wrote — open-shell choreography, exact-part punches, the fabrication strip —
and that layer is untouched by all three answers.

## 3 · The evidence

### 3.1 manifold failed nothing we measured

Four adversarial cases drawn from our own everyday geometry (coplanar bore lid on a
machined floor; floor clip flush on the cap's base; a cut with that clipped tool; two
touching punches in one batched call): **manifold passes all four**, volume errors of
2e-6 mm³ against analytically-computed expectations, in 0.4–3.4 ms. Re-running the
hardest at 200 random clockings of the cap about its own axis: **200 / 200 correct** — a
0 % failure rate, 95 % upper bound 1.9 %. On the fleet's real self-heal operands it
produced a usable result **20 / 20**.

### 3.2 Why MeshLib cannot be the kernel

**The silent no-op.** On the coplanar bore lid — not an edge case for us but *every cut*
— MeshLib's mesh boolean returns the input unchanged: nothing removed, yet a watertight
output, `valid() = True`, an empty error string, both of its own bad-contour flags clear.
Across 200 seeded clockings this happens **101 times — 50.5 %, 95 % CI 43.6–57.4 %**. The
trigger is a knife-edge: moving the tool 3e-7 mm cures it; anything inside roughly
±1e-7 mm of exact coplanarity fails. Its own defect detectors call the input clean. The
severity is the silence — a wrong package that reports success is the one failure mode
this product cannot tolerate.

**The fleet confirms it on real data.** We reconstructed all **115 boolean calls** the
emit lanes make across **9 real cases**. Fifty are the punch self-heal — a union of a
solid with *itself*, 100 % coplanar by construction. Against MeshLib on the fleet's own
operands it returns an **empty result on 16 of 20** — this time with an error string, a
louder failure than the silent no-op, but a failure. The disqualification is not a
synthetic-fixture artifact.

**The risk is bounded, which is why the other two lanes survive.** The same census found
**zero incidence** of exact-coplanar contact between *distinct* solids: 0 of 75 calls,
zero face pairs in every band down to 1e-3 mm, stable across a 10⁵ sweep of the
measurement tolerance. The closest production geometry ever comes to the trigger is
**1.56e-4 mm** — three orders of magnitude clear. Neither the offset lane nor the
open-shell lane ever makes a coplanar-operand boolean, so neither is touched. The one
near miss is by design: 4–5 of 20 site × lane configurations put the clip plane on the
cap's own base, and at the accepted production relief of 0.00 the margin narrows to
**2.1e-7 mm** — roughly twice the trigger window, held open only by the vendor's float32
export scatter (7e-7 – 1e-6 mm across all 12 catalog variants). Two vendors' export
habits are not a guarantee.

**Therefore the guard is mandatory, not optional.** Any future MeshLib boolean ships a
post-condition — **output ≠ input AND output ≠ empty** — with a manifold fallback. It
costs one comparison and is exactly the shape of both observed failures. Without it, the
headline number of any adoption is a 50 % silent-wrong-answer rate on geometry we know we
generate.

### 3.3 The offset is where money would actually buy something

Our shipping offset (vertex-normal dilation) is instant (0.003 s) but is **not a
small-error method — it is a wrong-shape method at concave creases**: at a 0.5 mm offset
it is 0.49 mm wrong at worst and stands 0.327 mm short of the crease, with 9 892
self-intersecting triangle pairs in the tool. Our correct alternative, the Minkowski
path, is accurate (0.00226 mm) but costs 16.9–18.6 s per offset in the evaluation harness
and **56–68 s per catalog-sized punch in our own production path** (W2, 2026-08-14) — 10×
the ≤ 5 s per-emit budget the plan sets, which is exactly why the default stayed
vertex-normal by measurement rather than flipping. `sharpOffsetMesh` is the first thing
measured that is both: 0.00106–0.00136 mm at 0.28–0.36 s. Two caveats stay attached: its
accuracy is a statement about its voxel pitch (halving the pitch halves the error), and
its output carries 340 k faces where Minkowski carries 13 k — decimation would be
required before anything reaches an STL or the viewer.

### 3.4 Open-shell cutting is the largest single capability gap

manifold refuses the raw open scan outright (`Not all meshes are volumes!`) — which is
why we invented solidify → cut → strip, and that invention is ours and stays valuable.
MeshLib cuts the raw 262 505-face scan directly in **0.05–0.09 s**, geometrically
identical to our own route at **1.8e-6 mm symmetric Hausdorff** on three of four tool
depths, skipping the 16.8 s solidify. One qualification the measurement does not remove:
the closed model (artifact 6) and the fused composites are *built* from the solid, and
the solidifier is cached per arch — so the 16.8 s leaves the carve, not necessarily the
emit.

### 3.5 What we owe ourselves regardless of any licensing decision

The incidence work found a latent hole in **our** code, unrelated to any vendor: the
self-heal's `except Exception` would swallow an *empty* kernel result (an empty mesh
raises nothing), the punch would silently become empty, the clip would keep it, and the
package would ship with **no recess**. manifold has never produced empty there — 20 / 20
— so it cannot fire today. It is precisely the hole a kernel swap would fall through, and
the empty check belongs in that catch whether or not we ever pay anyone. Queued with it:
`solidified_shell_cached` still keys on `id(arch)`, the address-reuse hazard class we
retired elsewhere.

## 4 · What a license would cost, and what it would buy

**Cost.** MeshLib publishes **no price**. What we hold is the vendor's own licensing
material — not a quote, and not something this evaluation verified: an **annual fee
stated as lower than a single engineer's salary**, covering **up to 5 developer seats**,
with **unlimited end-users and no royalties**, and a **startup track**. Contact:
`contact@meshlib.io`. The free tier we evaluated under is expressly non-commercial and
covers evaluation only; commercial embedding requires the paid license from AMV (Nevada
law, liability capped at $100, audit clause with 30 days' notice). One email settles the
real number, and it can be sent the day a trigger below fires.

**What it would buy, precisely.** Two lanes and no more, behind the kernel seam that
already exists (`pipeline/kernel.py`, Stage 0, 2026-08-13):

1. **the offset provider** — `sharpOffsetMesh` in place of vertex-normal dilation, with
   decimation before export;
2. **the open-shell carve** — the direct cut of the raw scan in place of
   solidify → cut → strip, for the carve lane only.

manifold remains the kernel for every boolean, including all composite artifacts and the
self-heal. Every MeshLib call ships the output ≠ input ∧ output ≠ empty guard with a
manifold fallback and an honest manifest note when it fires. None of this is a rewrite:
the seam makes it a bounded, testable swap, and the existing conformance corpus is the
acceptance gate.

## 5 · What would reopen this decision

1. **Emit latency becomes client-facing pain.** Today emits are seconds. If a case class
   or fleet growth pushes an emit into visible waiting, the 16.8 s solidify is the largest
   single identified item and the open-shell lane is the answer to it.
2. **An offset-quality complaint the Minkowski path cannot answer inside the budget.** If
   a clinical complaint traces to the vertex-normal crease shortfall (0.19–0.33 mm at the
   offsets we ship) while the correct alternative still costs 56–68 s per punch, we would
   be choosing between a wrong shape and an unshippable wait — the gap `sharpOffsetMesh`
   fills.
3. **A fleet case class our solidify choreography refuses.** The walker now names its
   refusals rather than mis-skirting; a refusal class that recurs on real cases is a
   capability gap direct open-shell cutting handles without a closure at all.

Any of the three reopens the decision — and reopening means re-measuring at fleet scale
first, because today's evaluation is n = 1 cap and n = 1 scan on a single host.

---

# Appendix — the measurements

Full evaluation: [`meshlib-scoreboard-2026-08.md`](meshlib-scoreboard-2026-08.md).
Requirements, build-from-scratch sizing, build-vs-buy and the staging:
[`boolean-engine-plan.md`](boolean-engine-plan.md) (Part I §0, §4, §5; Stage 2 results and
the Stage 2 addendum). Ledger: [`product-app-plan.md`](product-app-plan.md) §10-AT,
2026-08-13/14 (Stage 0, W1, W2, W4, W5, the scoreboard and incidence entries).

**Harness.** meshlib 3.1.3.429 (free evaluation tier, scratch venv — the pinned worker
env untouched, no repo file modified), manifold3d 3.5.2, trimesh 4.12.2, Python 3.9.6,
macOS arm64, single unloaded host.

## A.1 Battery 1 — the degeneracy corpus (synthetic, ported from `test_degeneracy.py`)

PASS = watertight **and** |V − V_expected| < 0.01 mm³ **and** the case's own geometric probe.

| case (plan W3 #) | manifold (incumbent) | MeshLib (mesh) | MeshLib (voxel 0.1 mm) |
|---|---|---|---|
| **#1 coplanar bore lid on a machined floor** | **PASS** — err 2e-6 mm³, 0.9 ms | **FAIL — SILENT NO-OP.** 0.000000 mm³ removed (err 49.94 mm³); base returned unchanged, watertight, `valid()=True`, `errorString=''`, bad-contour bitsets empty. 5.4 ms | FAIL — err 0.076 mm³, 369 620 faces, 60 ms |
| **#2a floor clip flush on the cap's own base** | **PASS** — err 2e-6 mm³, 3.4 ms | **PASS** — err 2e-6 mm³, 1.2 ms | FAIL — err 0.183 mm³, 270 ms |
| **#2b cut with the clipped tool** | **PASS** — err 2e-6 mm³, floor err 0.000 mm, 0.4 ms | **PASS** — err 2e-6 mm³, floor err 0.000 mm, 0.5 ms | FAIL vol — err 0.239 mm³ (floor probe passes), 57 ms |
| **#4 two touching punches, batched difference** | **PASS** — 4676.0107 mm³, 0.23 mm³ from the MC referee, 1.4 ms | **PASS** — 4676.0107 mm³ (identical), 0.8 ms | **FAIL — one subtraction lost.** 62.31 mm³ from the referee; site 1 never opened, 244 ms |

**Case #1 as a rate** — same fixture, N = 200 seeded random clockings of the cap about its
own axis, full production choreography:

| engine | correct | silent no-op | wrong volume | refused |
|---|---|---|---|---|
| manifold | 200 / 200 | **0** — 0.0 %, 95 % CI [0.0 %, 1.9 %] | 0 | 0 |
| MeshLib (mesh) | 99 / 200 | **101 — 50.5 %, 95 % CI [43.6 %, 57.4 %]** | 0 | 0 |

Characterisation: not a detectable mesh defect (0 self-colliding triangles, 0 degenerate
faces to MeshLib's own queries), not the fan lid, not float32 quantisation. Translating
the punch +3e-7 mm or −5e-7 mm cures it; ±1e-7 mm of exact coplanarity no-ops;
`BooleanParameters.forceCut = True` changes nothing. The voxel path's #4 failure is
separate: `voxelBooleanSubtract` does not compose across sequential subtractions
(confirmed at 0.05 / 0.1 / 0.2 mm, both tool orders).

## A.2 Battery 2 — a real vendor cap punch (`neodent-gm-5030`, 17 186-face dilated punch)

| metric | manifold | MeshLib (mesh) | MeshLib (voxel 0.1 mm) |
|---|---|---|---|
| watertight | yes | yes | yes |
| volume | 3124.30272 mm³ | **3124.30272 mm³ — identical** | 3124.34581 mm³ (+0.043) |
| removed vs MC referee (76.40 ± 0.47 mm³) | 0.71 mm³ | 0.71 mm³ | 0.75 mm³ |
| recess-mouth probe, max / median | 0.000399 / 0.000113 mm | **identical** | 0.001149 / 0.000726 mm |
| self-intersecting pairs out | 0 | 0 | 0 |
| wall-clock | 42.7 ms | **17.3 ms (2.5× faster)** | 1 381.6 ms |

On real geometry with no exact coplanarity, MeshLib's mesh boolean is exactly as accurate
as manifold and 2.5× faster. That is the case *for* the two lanes; it is not a case for
the kernel — A.1 is.

## A.3 Battery 3 — the offset head-to-head

Metric: sample the offset result's own surface (30 000 seeded samples), measure unsigned
distance to the original cap, error = |dist − d|; valid on convex, flat and concave
regions alike. Condensed from the scoreboard's full table, which also carries
`offsetMesh` @0.05/@0.025 and `generalOffset` Standard @0.025 rows.

| d (mm) | engine | wall-clock | faces out | self-int pairs | err p95 | **err max** | crease shortfall |
|---|---|---|---|---|---|---|---|
| 0.1 | vertex-normal *(shipping default)* | 0.003 s | 9 718 | 1 153 | 0.02576 | **0.05738** | +0.06960 |
| | manifold minkowski *(reference)* | 16.923 s | 43 614 | 64 | 0.00037 | **0.00045** | +0.00043 |
| | MeshLib sharpOffset @0.025 | 0.128 s | 460 550 | 1 | **0.00019** | 0.00213 | +0.00142 |
| 0.3 | vertex-normal *(shipping default)* | 0.003 s | 9 718 | 3 768 | 0.07526 | **0.28496** | +0.19390 |
| | manifold minkowski *(reference)* | 16.900 s | 37 792 | 29 | 0.00113 | 0.00136 | +0.00128 |
| | MeshLib sharpOffset @0.025 | 0.359 s | 520 404 | 3 | **0.00020** | **0.00106** | +0.00117 |
| 0.5 | vertex-normal *(shipping default)* | 0.003 s | 9 718 | 9 892 | 0.12470 | **0.49345** | +0.32745 |
| | manifold minkowski *(reference)* | 18.554 s | 32 606 | 2 | 0.00193 | 0.00226 | +0.00213 |
| | MeshLib sharpOffset @0.025 | 0.281 s | 594 320 | 3 | **0.00015** | **0.00136** | +0.00039 |

All MeshLib offset modes are voxel-based; it has no exact/Minkowski mesh offset. Its error
is **pitch-limited, not offset-limited** (0.05 → 0.025 mm roughly halves the max error),
so every MeshLib row is a statement about its voxel size. Minkowski's error is a pure
signed undershoot growing linearly with d, matching the documented icosphere sagitta
budget (0.0017 mm at r = 0.5, subdivision 3) — the instrument reproducing the repo's own
theory independently is a check on the instrument.

**End-to-end (the offset feeds a boolean, d = 0.3, 3 repeats, median):**

| offset engine | punch faces | offset s | + boolean s | **total** | removed mm³ | cut faces |
|---|---|---|---|---|---|---|
| vertex-normal | 9 718 | 0.004 | 0.014 | **0.018 s** | 83.1934 | 2 592 |
| manifold minkowski | 37 792 | 29.339 | 0.024 | **29.363 s** | 85.36436 | 13 088 |
| MeshLib sharpOffset @0.025 | 520 404 | 0.529 | 0.209 | **0.738 s** | 85.39873 | 340 546 |

sharpOffset agrees with minkowski to **0.034 mm³ (0.04 %)**; vertex-normal removes
**2.2 mm³ less — 2.6 % of the recess** — and that gap is the crease collapse in cubic
millimetres.

## A.4 Battery 4 — the open-shell probe

Subject: the raw `lower_jaw.stl` scan, 131 503 v / 262 505 f, open, 499 boundary edges,
never solidified; tool = the real cap punch at the case's own declared site.

| route | outcome | wall-clock |
|---|---|---|
| manifold on the raw open shell | **REFUSED** — `ValueError: Not all meshes are volumes!` | 0.0 s |
| MeshLib mesh boolean on the raw open shell | **CUT IT.** 261 885 f out, boundary 499 → 499, bad-contour flags 0/0 | **0.05 – 0.09 s** |
| MeshLib **voxel** on the raw open shell | **SILENT GARBAGE** — watertight=True, 5 808 faces, 7.7 mm² against the scan's 2 803.1 mm² (99.7 % destroyed), no error raised | 0.45 s |
| **incumbent route** (`solidify_shell` → manifold difference) | CUT, watertight | **16.8 s solidify** + 0.10 – 0.25 s |

Identity against the incumbent inside a 4 mm ball at the site: symmetric Hausdorff
**1.78e-6 / 1.83e-6 / 9.1e-7 mm** at tool sinks 0.0 / 1.5 / 3.0 mm; 0.0209 mm (median 0.0)
at 4.5 mm. MeshLib's mesh boolean tolerates a globally open shell provided it is closed in
the intersecting zone — which is our situation exactly: sites sit mid-arch, the open
boundary is the scan's periphery.

## A.5 The fleet incidence census (Stage 2 addendum, 2026-08-14)

| what was measured | result |
|---|---|
| boolean calls reconstructed on real cases | 115 calls · 9 cases · 10 sites · 125 operand pairs · 22 s |
| exact-coplanar contact between **distinct** solids | **0 of 75 calls**; 0 face pairs in every band down to < 1e-3 mm |
| closest approach production geometry ever makes | **1.56e-4 mm** — three orders of magnitude clear of the ±1e-7 mm trigger |
| stability of that result | unchanged across a 10⁵ sweep of the parallelism tolerance |
| self-heal calls (union of a solid with itself) | **50 of 50 — 100 % coplanar by construction** |
| MeshLib on those fleet self-heal operands | **EMPTY output on 16 / 20** (with `errorString`); 4 / 10 clean-cap failures attributable specifically to coplanarity; all 10 dilated caps fail regardless |
| clip plane on the cap's own base, by design | 4–5 of 20 site × lane configurations (floor_a = envelope base) |
| margin there at the accepted production relief 0.00 | **2.1e-7 mm**, held open only by the vendor STL's float32 base-disc scatter (7e-7 – 1e-6 mm across all 12 catalog variants) |
| latent hole found in **our** code | the self-heal's `except Exception` would swallow an EMPTY kernel result → a package with no recess (cannot fire on manifold: 20 / 20 non-empty) |

## A.6 Honest limitations

- **n = 1 cap and n = 1 scan** in batteries 2–4 (`neodent-gm-5030`, `doctor-295811960`).
  The other 11 caps and 9 scans were not run. This is not a fleet result; the fleet result
  is A.5, which measures incidence, not accuracy.
- **Single host, mostly single runs.** The same minkowski call at d = 0.3 measured 16.9 s
  and 29.3 s across two runs (1.7× spread) — treat every wall-clock as order-of-magnitude.
  Only the end-to-end table has repeats (n = 3, median).
- **Battery 1 is synthetic.** The 50.5 % rate is a rate within an adversarial fixture, not
  a fleet failure rate — which is exactly why A.5 was run before this memo.
- **The offset numbers are conditional on voxel size**, measured at two pitches only
  (0.05, 0.025 mm); the error is pitch-linear over that range.
- **Python 3.9.6 / macOS arm64 only.** No Linux or CI verification; MeshLib's advertised
  CUDA paths were unavailable and untested.
- **The choreography was ported, not imported** (read-only mandate): it mirrors `csg.py`
  and `kernel.py` as of the evaluation commit, but it is a copy and could drift.
- **The §4 pricing terms are the vendor's own material** — not a quote, not verified by
  this evaluation. No price is published; the first email settles it.
- **The W2 acceptance sweep (every catalog cap × offset ∈ {0.1..0.5}) is an
  integration-time run**, not part of the routine battery, and it skips when the
  gitignored fleet tree is absent. It is the measurement any offset-default flip needs,
  and it is still owed.
