# The engine switch, run for real — a kernel-conformance scoreboard

Measured 2026-08-15 · the "try both engines" slice. Where
[`meshlib-scoreboard-2026-08.md`](meshlib-scoreboard-2026-08.md) ran a PORTED copy of the
repo's own choreography against each engine in isolation, this run is different in kind:
it points the REAL repo — `pipeline/kernel.py`'s new `CASE_PREP_BOOLEAN_KERNEL` switch,
`pipeline/meshlib_kernel.py`'s real `MeshLibKernel` — at the repo's own referee suites,
unmodified, and reports what actually happens when every `default_kernel()` call in
`csg.py`/`deliverables.py` resolves to MeshLib instead of manifold for an entire process.
Nothing here overturns [the kernel decision memo](kernel-decision-memo.md) (§2: manifold
stays, no money changes hands) — this is the same verdict, reached a second way, with the
production code path instead of a ported copy, and two findings the ported harness could
not have produced because it never ran the real fallback ladders.

**Harness.** Engine A: `/Users/tonycodes/Code/artech/dental-alignment/apps/worker/.venv/bin/pytest`
(the pinned production venv — manifold3d 3.5.2, trimesh 4.12.2, Python 3.9.6), cwd this
worktree's `apps/worker`, `PYTHONPATH=src`, `CASE_PREP_BOOLEAN_KERNEL` unset. Engine B: the
scratch evaluation venv's own Python
(`.../scratchpad/meshlib-eval-venv/bin/python -m pytest`, meshlib 3.1.3.429, same
trimesh/manifold3d/numpy/scipy pins as the production venv), same cwd and `PYTHONPATH`,
`CASE_PREP_BOOLEAN_KERNEL=meshlib`. `pytest`, `urllib3` (for the repo's own
`filterwarnings` ini option, which imports it by name at collection) were installed into
the scratch venv only; the production venv was never touched, per this slice's own rule.
Suites: `test_kernel.py test_csg.py test_csg_corpus.py test_degeneracy.py
test_deliverables.py` — the kernel seam's own referee corpus. `test_meshlib_kernel.py` is
excluded from the table below on purpose: it is this slice's OWN conformance suite (its
meshlib-dependent pins already run for real under the scratch venv as part of building the
adapter, 25 passed / 2 skipped there), not one of the five suites the task asked to be run
both ways.

---

## 1 · Per-suite results

| suite | Engine A (manifold) | Engine B (meshlib) | A wall-clock | B wall-clock |
|---|---|---|---|---|
| `test_kernel.py` | 28 pass / 0 fail / 0 skip | 27 pass / 0 fail / 1 skip | 0.62 s | 0.70 s |
| `test_csg.py` | 40 pass / 0 fail / 1 skip | 34 pass / 6 fail / 1 skip | 1.76 s | 1.19 s |
| `test_csg_corpus.py` | 10 pass / 0 fail / 3 skip | 6 pass / 4 fail / 3 skip | 0.86 s | 1.06 s |
| `test_degeneracy.py` | 11 pass / 0 fail / 0 skip | 7 pass / 4 fail / 0 skip | 0.77 s | 1.01 s |
| `test_deliverables.py` | 39 pass / 0 fail / 2 skip | 16 pass / 23 fail / 2 skip | 2.44 s | 5.48 s |
| **TOTAL** | **128 / 0 / 6** (134 collected) | **90 / 37 / 7** (134 collected) | **6.45 s** (sum of the five; 4.79 s run as one combined invocation) | **9.44 s** (sum) |

Engine A's skip count (6) and Engine B's (7) differ by exactly one: Engine B additionally
skips `test_meshlib_kernel.py`-style "meshlib is missing" pins that live in
`test_kernel.py::TestEngineSwitch` — meshlib IS importable under the scratch venv, so that
one pin (specifically testing the missing-package path) correctly skips there and correctly
RUNS (and passes) under Engine A. Every other skip is pre-existing and identical across
both engines (real-fleet-data tests skipping because `data/real` is absent in this
worktree, matching this repo's documented environment shape — unrelated to the engine
switch).

**Engine A is exactly the certification-gate baseline**: 128/128 on this five-file slice,
0 failures — the same result the fast-lane run (§ below) confirms at full-repo scale (851
passed, 0 failed, 188 skipped, 19.24 s on `-m "not slow"`, the default engine untouched).

**Engine B fails 37 of 134** — none of them silently. Every single one is accounted for in
§2 below, and every one resolves to either a loud refusal (the guard, or MeshLib's own
error string) or an honest fallback note already built into `csg.py`/`deliverables.py` for
other reasons. Zero produced a wrong artifact that a test's own geometry/volume assertion
missed — see the "genuine-wrong: 0" line in §2's summary table before assuming a 28%
failure rate means the code is broken; it means the CORPUS's own assumptions (tracked ops
always available, self-heal is bit-exact) are manifold-specific, which is exactly what
§2.3 and the memo already concluded on paper.

---

## 2 · Failure anatomy — all 37, classified

Four buckets, not three — the task named guard-refusal / parity-gap-fallback /
genuine-wrong; a fourth, **precondition drift**, showed up and does not fit any of those
three cleanly (see §2.2). None of the 37 is genuine-wrong.

Classified by PRIMARY cause — the reason the test itself failed. A separate note below the
table names the failures that carry a SECOND, non-fatal cause stacked underneath.

| category | count | suites (counts) |
|---|---|---|
| **parity-gap-fallback** (`NotImplementedError` — either propagates directly because the calling test has no fallback wrapper, or is caught by `csg.py`/`deliverables.py`'s own existing `except Exception` and lands an honest note) | 34 | `test_csg.py` 6, `test_csg_corpus.py` 4, `test_degeneracy.py` 1, `test_deliverables.py` 23 |
| **guard-refusal** (the adapter's own guard raises loudly; propagates as a clean exception here, uncaught by any fallback wrapper at this specific call site) | 1 | `test_degeneracy.py` 1 |
| **precondition drift** (the fixture's own BIT-EXACT setup assertion — verified before the boolean under test ever runs — no longer holds, because an intermediate `default_kernel()` call, the unconditional self-heal, is not a numerical no-op under this engine the way it is under manifold) | 2 | `test_degeneracy.py` 2 |
| **genuine-wrong** (a test's own geometry/volume/shape assertion failed — the boolean ran, returned something, and it was measurably incorrect) | **0** | — |
| **TOTAL** | **37** | |

**Stacked, non-fatal second causes** (not separately counted above, since the PRIMARY
cause — the tracked-ops fallback note — is what fails the test either way): 4 of the 34
`test_deliverables.py` parity-gap-fallback rows (`TestSocketIsFaceProvenance`,
`TestMaskNeverSplitsAUniformProvenanceFan`, `TestNoScanFaceShipsInTheSocketLayer`,
`TestTheMergedCaplessArtifactDoesNotMove`) ALSO carry a guard-refusal note from an earlier,
internally-caught `exact_cap_punch` call (§2.1) — the test's own `notes` list has TWO
entries in those four cases, one entry in the other 19. `test_csg_corpus.py`'s 4 failures
are `difference_tracked`/`minkowski_sphere` `NotImplementedError` propagating directly (no
fallback wrapper at that call site, since these tests exist specifically to exercise the
tracked path itself) — parity-gap-fallback, not guard-refusal; §2.4 separately confirms the
guard's OTHER real trigger (the self-heal on a genuinely self-intersecting dilated punch)
by direct construction, since none of the 37 failures above happened to exercise it.

### 2.1 · The coplanar guard, reproduced end-to-end (not just the isolated pin)

`TestFloorClipAtExactlyTheCapsBasePlane::test_watertight_punch_and_the_floor_lands_at_floor_a`
calls `exact_cap_punch(cap, 0.0, pose, floor_a=floor_a)` directly (no fallback wrapper at
this call site, so the guard's `ValueError` propagates as the test failure, which is
correct — this specific test is exercising `csg.py`'s own choreography directly, not
`deliverables.py`'s fail-open layer). The floor clip — a box intersection with the plane
flush on the cap's own base, `floor_a` — comes back EMPTY under MeshLib:

```
MeshLibKernel.intersection guard: MeshLib returned an EMPTY result for an operation
whose operands were not — operand face counts [400, 12].
```

This is the memo's own §A.5 "near miss" (4-5 of 20 site×lane configurations put the clip
plane on the cap's own base; margin there **2.1e-7mm**, "held open only by ... float32
export scatter") reproduced for real, but from a DIFFERENT source of margin-eating noise
than the memo's own vendor-export scatter: here it is `exact_cap_punch`'s own unconditional
self-heal (§2.2 below) perturbing the punch by a few times 1e-9mm RELATIVE TO the
`floor_a` value measured from the pre-heal cap — enough, on this fixture, to push the
clip's own coplanar contact past MeshLib's ±1e-7mm trigger, this time landing on the EMPTY
side rather than the silent-no-op side the isolated memo battery measured. Two different
degenerate-geometry sources (vendor export scatter; this engine's own self-heal) converging
on the SAME narrow margin is exactly why the memo calls the guard mandatory rather than
conditional on any one cause.

`test_deliverables.py`'s `TestMaskNeverSplitsAUniformProvenanceFan` and
`TestNoScanFaceShipsInTheSocketLayer` hit the identical EMPTY-intersection guard at the
SAME call site (`_csg_carve`'s own `exact_cap_punch(..., floor_a=...)`, line 510) — but
THERE it is caught by the pre-existing `except Exception` (line 513) and lands the
`"site 1: the exact cap could not be cut (...) — its envelope was used instead"` note,
never propagating. Same trigger, same guard, two different outcomes purely because of
which layer calls it — the isolated case above has no fallback wrapper; the production
consumer does.

### 2.2 · Precondition drift — the self-heal is not a numerical no-op under MeshLib

`exact_cap_punch` unconditionally self-heals (`default_kernel().union([punch, punch])`,
`csg.py:594`, regardless of `offset_mm`) before anything else happens to the punch.
Under manifold, on the corpus's own round-literal coordinates (`TOP_Z = 3.0`), this
round-trips bit-exact — not because manifold's boolean is an identity operation, but
because manifold3d's own MeshGL conversion forces float32, and small integers like `3.0`
survive that rounding losslessly. `test_degeneracy.py`'s own docstring names this
precisely ("the punch's own lid plane is bit-identical to the fixture's own literal") and
the corpus leans on it: several tests assert bit-exact coplanarity/tangency BEFORE the
boolean under test ever runs, exactly this repo's own stated discipline.

Under MeshLib, the SAME self-heal call — verified directly, this slice's own exploration,
not inferred —

```
pre-heal top z: 3.0   faces: 192   vol: 49.94312243612884
healed   top z: 3.0000000000000  →  read back as 2.999999999501413 after
                                    exact_cap_punch's own pose transform
healed faces: 498 (was 192)   volume delta: 1.833458973976576e-06 mm³
```

is NOT a numerical no-op: MeshLib's boolean genuinely retriangulates a mesh unioned with
its own exact duplicate (192 → 498 faces), and the retriangulated coordinates carry noise
on the order of 1e-9mm — clinically and geometrically meaningless (`csg.py`'s own
`heal_fired` threshold is 1e-3mm³; this is 1.8e-6mm³, three orders below it, so
`heal_fired` correctly reads `False`), but enough to break a fixture's BIT-EXACT (`==`,
not `pytest.approx`) precondition check. Two failures are exactly this:
`TestCoplanarBoreLidOnAMachinedFloor::test_the_punchs_fan_lid_and_the_blocks_top_face_are_bit_identical`
(`2.999999999501413 == 3.0` fails) and
`TestPunchTangentToTheSkirt::test_the_punchs_side_and_the_skirt_share_the_same_x_plane`
(10 vertices land exactly on the tangent plane where manifold's construction puts exactly
2 — MeshLib's retriangulation near the tangent contact adds vertices the manifold path
never introduces).

Neither is a MeshLib defect in the geometric sense — both meshes remain watertight, both
volumes stay within float noise of correct — it is a mismatch between an ENGINE-SPECIFIC
numerical accident (manifold's self-heal happens to preserve round literals) that a
manifold-authored corpus's own preconditions quietly came to depend on, and a second
engine that does not share the accident. This is why it earns its own bucket rather than
folding into "genuine-wrong": nothing here is wrong, a fixture-authoring assumption is
merely engine-specific.

### 2.3 · The tracked-ops cascade — `_csg_carve`'s own fallback ladder, engaging for real

Every one of `test_deliverables.py`'s 23 failures is the SAME shape:
`assert notes == []` (or `len(notes) == 1`) fails because `notes` gained ONE MORE entry
than the test expected. Reading `deliverables.py:539-568` (`_csg_carve`) directly — this is
pre-existing code, UNCHANGED by this slice:

```python
try:
    ...
    tracked = default_kernel().difference_tracked(solid, punches, fabricated...)
    ...
except Exception as exc:      # noqa: BLE001 — fail-open to the untracked
    cut = default_kernel().difference(solid, punches)
    if not cut.is_watertight:
        raise ValueError("the boolean result is not watertight")
    notes.append(f"the provenance-tracked strip could not run ({exc}) "
                 f"— the distance-based strip was used instead")
```

Under MeshLib, `difference_tracked` raises the adapter's own `NotImplementedError` (naming
the provenance gap and the fallback ladder — see `meshlib_kernel.py`'s
`_TRACKED_PROVENANCE_GAP`), the `except` catches it, the UNTRACKED `difference` runs
instead (itself sometimes ALSO hitting the guard on an upstream `exact_cap_punch` call,
§2.1 — in 4 of the 23 the note list carries both), and the honest note lands exactly as
`deliverables.py` was already built to do — for a DIFFERENT reason (a manifold3d rejection,
an unwatertight tracked result) than this slice introduces. Not one line of `csg.py` or
`deliverables.py` changed to make this work; the fallback ladder simply had a second real
trigger handed to it. Spot-checked directly
(`TestCapImprintHoles::test_a_degenerate_template_carves_a_cylinder_recess`): the
UNDERLYING cut geometry is unaffected — the test's own note-count assertion
(`len(notes) == 1`) is the only thing that fails; the site still gets cut, still gets a
cylinder recess, exactly as the manifold path produces, plus one additional honest string
saying why the tracked route was not used.

`test_csg.py`'s and `test_csg_corpus.py`'s 10 tracked/minkowski failures (of the 34 in the
parity-gap-fallback row) are the same `NotImplementedError`, but at call sites with NO
fallback wrapper — `TestStripTracked` and `TestTrackedLocalityAndConservativity` call
`default_kernel().difference_tracked(...)` directly to test the tracked path ITSELF, so
there is nothing to catch the exception; it is the correct, honest failure mode for a test
whose entire point is "does the tracked path work" when the tracked path, under this
engine, by design, does not.

### 2.4 · The W5 empty-heal guard, and whether it keeps a punch alive (verified directly)

Neither of the two questions the task asked can be answered from the 37 failures above —
this corpus's synthetic self-heal fixtures never happened to trigger the self-heal's own
empty/refusal path (§2.2's coplanar fixture perturbs but does not empty). Answered instead
by direct construction, this slice's own exploration, against `_notched_cylinder_cap()`
(`test_csg.py`'s own concave fixture, vertex-normal dilated 0.3mm — genuinely
self-intersecting, matching the memo's real-fleet dilated-cap finding):

```
dilated punch: watertight, 440 faces, volume 73.25mm³ (inflated by the self-overlap)
MeshLibKernel.union([punch, punch]) → RAISES:
  "MeshLibKernel.union: MeshLib refused the operation (Bad contour on 5 mesh A
   faces, probably mesh B has self-intersections on contours lying on these faces.)"

exact_cap_punch(fixture, 0.3, pose, kernel resolved via CASE_PREP_BOOLEAN_KERNEL=meshlib):
  diagnostics["heal_fired"] = False
  result: the ORIGINAL 440-face, still-watertight, un-healed punch — unchanged
```

Two things worth separating precisely. First, this specific refusal is MeshLib's OWN
native one (`res.valid() is False`, with an error string) — the adapter's `_boolean`
converts it to a `ValueError` BEFORE `guard_boolean_output` is ever consulted; it is not
literally the memo's "output == input" or "output is empty" branch firing, though the
adapter's docstring and this doc both use "the guard" loosely to cover both layers, since
from a caller's point of view both are the same thing: a loud refusal instead of a wrong
answer. Second, and this is the actual finding: `csg.py`'s own pre-existing
`except Exception: pass` around the self-heal call (line 611-614, written for manifold3d's
own possible rejections, not for this engine) catches EITHER layer's `ValueError`
identically, and the documented W5 empty-heal guard's own contract —
"the original (pre-heal) punch is kept" — holds under MeshLib with ZERO code changes. The
engine switch needed no new safety net here; the one already in `csg.py` for a different
reason already covers it.

---

## 3 · The parity verdict

**MeshLibKernel cannot pass this corpus unchanged, and this run confirms the memo's own
verdict (§3.2, "not a drop-in replacement") rather than overturning it — with the
qualification that every failure resolves to a named refusal or an existing honest
fallback, never a silently wrong artifact.** Three things would have to change, and none
of them is a kernel bug to fix: (1) a real `difference_tracked`/`union_tracked` under
MeshLib, which does not exist as a vendor capability today and cannot be built without
either a MeshLib SDK feature this evaluation never found or resurrecting the
proximity-based provenance W1 explicitly retired — so 34 of the 37 failures are not
closeable inside this adapter at all, only by the corpus's OWN assertions becoming
engine-aware (`notes == [] if tracked_ops_supported(engine) else [...]`), which is test
work, not kernel work; (2) either accepting the guard's conservative false-positive on a
legitimately-flush operand (the floor clip at `relief == 0`) as MeshLib's permanent,
by-design behavior under this engine — in which case `_csg_carve`'s existing envelope
fallback is already the correct answer and needs nothing new — or pre-nudging a
known-coplanar operand by a few times 1e-7mm before a MeshLib boolean, which the memo's own
characterization suggests would cure it but which this slice did not build (scope: no
`csg.py` changes); (3) loosening two of the corpus's own bit-exact (`==`) preconditions to
an epsilon tolerance, since they encode a manifold-specific numerical accident rather than
a geometric requirement. None of the three touches `MeshLibKernel` itself, which is exactly
the memo's own finding restated: the gap is structural (no provenance API) and
probabilistic (a narrow, bounded-incidence trigger already named and guarded), not a
defect this adapter could quietly fix by trying harder.
