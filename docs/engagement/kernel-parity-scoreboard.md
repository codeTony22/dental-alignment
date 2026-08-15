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

**All three are now DONE** (§4, 2026-08-15, same-day follow-up): (1) is built, as the
`engine_expects` fixture below, not the `tracked_ops_supported(engine)` free function this
section sketched — a capability method on the kernel itself, so the corpus asks the ENGINE,
not a lookup table that could drift out of sync with it; (2) is DECIDED, not merely
theorised — ACCEPT THE FALLBACK, never pre-nudge, recorded in `meshlib_kernel.py`'s own
docstring and applied to every native MeshLib boolean refusal this corpus's own fixtures
turned out to trigger, not only the one this section named; (3) is loosened, exactly the
two named tests, nothing else. §4 is the full accounting.

---

## 4 · The rework, landed (same-day follow-up, 2026-08-15)

### 4.1 · The capability read

`BooleanKernel` (the `Protocol` in `pipeline/kernel.py`) gained one new member:

```python
def supports_tracked(self) -> bool: ...
```

`ManifoldKernel.supports_tracked()` returns `True`; `MeshLibKernel.supports_tracked()`
returns `False`. Its own docstring on the `Protocol` is explicit about scope: it is a
query about `difference_tracked`/`union_tracked` specifically, named for exactly what it
answers — not a general "how capable is this kernel" score. It is REUSED, deliberately, as
the referee corpus's one engine-aware signal for two OTHER axes this run's own exploration
surfaced (§4.4) — the `minkowski` offset engine, and native-refusal robustness on
self-intersecting/coplanar operands — because in today's two-kernel world `MeshLibKernel`
happens to be uniformly the reduced adapter across all three, and a second, narrower
capability read would be pure redundancy while that stays true. The flag's own docstring
says so, in the same words, so a future third kernel with a genuinely split capability
profile is a documented decision point, not a silent trap.

### 4.2 · The engine-aware pattern

One fixture, `engine_expects` (`tests/conftest.py`, shared by all five referee files — the
only file outside the three the task named that this slice touches, and only to hold the
one shared fixture the task itself asked for):

```python
@dataclass(frozen=True)
class EngineExpectations:
    tracked: bool

    def assert_fallback_notes(self, notes, *substrings) -> None:
        ...  # non-tracked branch only: notes must carry exactly len(substrings)
             # entries, each containing its own substring, IN ORDER


@pytest.fixture
def engine_expects() -> EngineExpectations:
    from case_prep.pipeline.kernel import default_kernel
    return EngineExpectations(tracked=default_kernel().supports_tracked())
```

Every reworked test reads `engine_expects.tracked` once and branches: the `tracked=True`
branch is the ORIGINAL assertion, byte-for-byte, wherever the geometry itself does not
depend on the engine (verified directly per test, not assumed — §4.3); the `tracked=False`
branch takes one of two shapes, depending on whether the call site under test has a
consumer-level fallback ladder to observe:

* **A fallback wrapper exists** (all 23 of `test_deliverables.py`'s own failures, plus the
  two `TestOffsetEngineComparison` pins §4.4 covers — `_csg_carve`/`arch_with_parts_fused`/
  `cap_imprint_parts`'s own `except Exception` clauses, or `exact_cap_punch`'s own
  self-heal catch): `assert_fallback_notes(notes, *substrings)` verifies the note(s) that
  landed, in order, by content — "the note IS the contract" — or, for the self-heal pins,
  the equivalent direct check (`heal_fired is False` and the punch stays watertight).
* **No fallback wrapper exists at this call site** (`TestStripTracked`,
  `TestTrackedLocalityAndConservativity`'s 3 pins, the `TestExactCapPunch`/
  `TestOffsetEngineDidNotFlipTheDefault` minkowski pins, one `TestPunchTangentToTheSkirt`
  pin, `TestFloorClipAtExactlyTheCapsBasePlane`, and the two outer-ladder
  `TestCapImprintHoles` pins §4.4 covers, where the WHOLE carve — not one strip step —
  falls back): `pytest.raises(NotImplementedError, match=...)` or `pytest.raises(ValueError)`
  against the exact same inputs the tracked branch would have used, verifying the refusal
  itself is loud and names what refused.

37 failures reworked in total (matching every one §2 classified), plus the 2 preconditions
loosened to a contract instead of an accident (§4.5) and 2 new capability pins (§4.1).

### 4.3 · The flush-operand decision, implemented

`TestFloorClipAtExactlyTheCapsBasePlane::test_watertight_punch_and_the_floor_lands_at_floor_a`
(§2.1's own subject) now reads, under `engine_expects.tracked is False`:

```python
with pytest.raises(ValueError) as excinfo:
    exact_cap_punch(cap, 0.0, pose, floor_a=floor_a)
message = str(excinfo.value)
assert "guard" in message.lower()
assert "MeshLib" in message
```

— verifying the refusal is LOUD (names itself, names the engine) rather than asserting the
manifold-only outcome (a clipped, watertight punch) that this engine cannot produce on a
legitimately-flush operand. The decision — ACCEPT THE FALLBACK, never pre-nudge the operand
by epsilon to appease one engine — is recorded in `meshlib_kernel.py`'s own module
docstring (a new "THE FLUSH-OPERAND DECISION" paragraph) and in `guard_boolean_output`'s own
docstring, both citing this doc. Every OTHER test in §2 whose note names `"the exact cap
could not be cut"` (the guard firing inside `_csg_carve`'s own caught call, 8 tests — the
scoreboard's original count of 4 undercounted this; the correct count, reconfirmed while
reworking every one of them directly, is 8: `TestCapImprintHoles::
test_the_floor_follows_the_gum_at_the_countersink_depth`,
`test_the_collar_drapes_onto_curved_gum_no_floating_crescents`,
`test_a_proud_platform_floor_is_a_saucer_on_the_gum`,
`test_a_tall_cap_socket_stops_just_below_the_gum`, plus the four `TestSocketIsFaceProvenance`
/`TestMaskNeverSplitsAUniformProvenanceFan`/`TestNoScanFaceShipsInTheSocketLayer`/
`TestTheMergedCaplessArtifactDoesNotMove` rows §2 already named) applies the identical
acceptance via `assert_fallback_notes`, verifying the guard note's own content rather than
merely its presence.

### 4.4 · Beyond the three — the same decision, generalised (not a fourth item, the same one)

Reworking the corpus test-by-test surfaced two MORE shapes of native MeshLib boolean
refusal §2 did not classify separately (§2.4 predicted the FIRST of these existed but
could not find it among the 37; it turns out one test already exercises it):

* **The self-heal, on a genuinely self-intersecting punch, for real.**
  `TestOffsetEngineComparison::test_the_concave_fixture_forces_a_real_self_intersection`
  and its sibling `test_vertex_normal_path_needs_the_heal_minkowski_path_does_not` run
  `exact_cap_punch`'s vertex-normal path on `_notched_cylinder_cap()` — genuinely
  self-intersecting, no synthetic monkeypatch — and MeshLib's own `union([punch, punch])`
  raises NATIVELY (`"Bad contour on 28 mesh A faces, probably mesh B has self-intersections
  ..."`), caught by `csg.py`'s own pre-existing `except Exception: pass` around the heal
  call (the same catch §2.4 already named for a DIFFERENT, hand-built fixture).
  `heal_fired` reads `False` and the un-healed-but-still-watertight punch survives — §2.4's
  own predicted contract, holding on a test that turns out to already exercise it directly,
  not only by the isolated exploration §2.4 reported. Reworked to assert exactly that
  contract under `engine_expects.tracked is False`, instead of the manifold-only
  `heal_fired is True`.
* **The untracked `difference`, on a self-intersecting or deviated operand, for real.**
  `TestCapImprintHoles::test_the_recess_is_the_caps_exact_surface` (a cap with a
  protruding fin) and `test_a_deviated_scanned_cap_leaves_no_flaps` (a cap seated 0.35mm
  off pose) make their own operand self-intersecting under MeshLib's contour test at the
  `difference` step itself — not the self-heal, the actual carve — so BOTH `_csg_carve`
  routes fail (tracked AND untracked) and `cap_imprint_parts`'s own outer ladder falls the
  WHOLE carve back to the one-shell PRESS CARVE (`§10-AS.10`), a different algorithm with
  no claim to either pin's own CSG-exact geometric claims (the fin's own azimuthal
  footprint; the torn-flap cull margin). Reworked to verify the refusal is loud (names
  MeshLib, names itself) and the press-carve fallback's own note landed, and to SKIP the
  CSG-path-specific geometric assertions under this engine — they test a claim about a
  different algorithm now running.

Both are the SAME decision as §4.3 (accept the native refusal, trust the existing
fail-open ladder, never pre-nudge), applied to two MORE call sites the exploration found by
actually reworking the tests rather than by prediction. Nothing here is a fourth category:
every one of the 37 is still exactly one of parity-gap-fallback (34), guard-refusal, or
precondition drift (2) — the total stays 37, reclassified more precisely than §2's own
first pass (which counted only 1 guard-refusal test and folded these other 4 into the
parity-gap-fallback bucket by their `NotImplementedError`-shaped description, imprecisely —
`test_vertex_normal_path_needs_the_heal_minkowski_path_does_not` genuinely carries BOTH: its
vertex-normal half is guard-refusal, its minkowski half is parity-gap-fallback), not
enlarged. Guard-refusal now names 3 distinct call sites (the coplanar floor-clip
intersection, §2.1's own subject; the self-heal's own union call, §2.4; the untracked
carve's own difference call, new here) across 5 tests
(`test_watertight_punch_and_the_floor_lands_at_floor_a`;
`test_the_concave_fixture_forces_a_real_self_intersection` and
`test_vertex_normal_path_needs_the_heal_minkowski_path_does_not`;
`test_the_recess_is_the_caps_exact_surface` and
`test_a_deviated_scanned_cap_leaves_no_flaps`) — not 1 test at 1 site, as §2's first pass
undercounted before every failure was reworked and re-examined directly.

### 4.5 · The two loosened preconditions, before/after

**`TestCoplanarBoreLidOnAMachinedFloor::test_the_punchs_fan_lid_and_the_blocks_top_face_are_bit_identical`**

```python
# before
assert float(punch.vertices[:, 2].max()) == self.TOP_Z

# after
assert float(punch.vertices[:, 2].max()) == pytest.approx(self.TOP_Z, abs=1e-6)
```

1e-6mm is five orders of magnitude looser than the measured manifold-vs-MeshLib drift
(≈5e-10mm, §2.2) and nine orders tighter than anything clinically significant — the
CONTRACT (coplanar enough for the cut test below to be meaningful), not the accident
(bit-exact because manifold's float32 round-trip happens to preserve `3.0` losslessly).
The block's own literal (never touched by any kernel) stays bit-exact `==`, unchanged.

**`TestPunchTangentToTheSkirt::test_the_punchs_side_and_the_skirt_share_the_same_x_plane`**

```python
# before
at_plane = Vp[:, 0] == skirt_x
assert int(at_plane.sum()) == 2
assert sorted(Vp[at_plane, 2].tolist()) == [-2.0, 2.0]

# after
at_plane = Vp[:, 0] == skirt_x
assert int(at_plane.sum()) >= 2
plane_zs = Vp[at_plane, 2]
assert float(plane_zs.min()) == -2.0 and float(plane_zs.max()) == 2.0
```

The manifold-authored fixture (2 vertices, top+bottom rim only) still satisfies `>= 2` and
still spans `[-2.0, 2.0]` exactly, so this loosening changes nothing on the manifold path
(reconfirmed: 130/130 on this slice's own five-file run) — it accepts MeshLib's own
retriangulation near the tangent contact (10 vertices, same span) without accepting a
weaker CONTRACT: the whole edge (top rim to bottom rim) must still be tangent to the
plane, whatever triangulation lands on it.

### 4.6 · The after-table

Both venvs, same harness as §1 (Engine A: production venv, `CASE_PREP_BOOLEAN_KERNEL`
unset; Engine B: scratch venv, `CASE_PREP_BOOLEAN_KERNEL=meshlib`), same five suites, run
individually (not combined) so each suite's own wall-clock is exact rather than apportioned:

| suite | Engine A (manifold) | Engine B (meshlib) | A wall-clock | B wall-clock |
|---|---|---|---|---|
| `test_kernel.py` | 30 pass / 0 fail / 0 skip | 29 pass / 0 fail / 1 skip | 0.49 s | 0.63 s |
| `test_csg.py` | 40 pass / 0 fail / 1 skip | 40 pass / 0 fail / 1 skip | 1.69 s | 1.07 s |
| `test_csg_corpus.py` | 10 pass / 0 fail / 3 skip | 10 pass / 0 fail / 3 skip | 0.85 s | 1.25 s |
| `test_degeneracy.py` | 11 pass / 0 fail / 0 skip | 11 pass / 0 fail / 0 skip | 0.59 s | 0.85 s |
| `test_deliverables.py` | 39 pass / 0 fail / 2 skip | 39 pass / 0 fail / 2 skip | 2.48 s | 5.13 s |
| **TOTAL** | **130 / 0 / 6** (136 collected) | **129 / 0 / 7** (136 collected) | **6.10 s** (sum; 5.13 s combined) | **8.93 s** (sum; 6.12 s combined) |

**Engine A: 130/130, 0 failures — 2 pins ABOVE the §1 baseline (128), never fewer**: the
new `TestSupportsTracked` class (`test_kernel.py`, 2 pins for the capability read itself)
is the only net-new test surface; every pre-existing manifold-path assertion this slice
touched is reconfirmed passing, unweakened, exactly as §4.5's own reconfirmation states for
the two loosened preconditions specifically. The fast-lane equivalent (`-m "not slow"` on
these five files, production venv) is likewise green: 130 passed, 2 skipped, 4 deselected.

**Engine B: 129/136, 0 failures, 0 unclassified — down from 90/37/7 (§1) to 129/0/7.**
Every one of the 37 failures §2 classified now passes, engine-aware, without weakening a
single manifold-path assertion (§4.2's own branch structure keeps the `tracked=True` arm
literal or, where geometry was reconfirmed unaffected by the strip mechanism, byte-for-byte
the original code). The skip-count asymmetry (6 vs 7) is unchanged from §1 and remains the
same one pin (`test_kernel.py::TestEngineSwitch`'s missing-package path, which correctly
skips only where meshlib IS importable). The fast-lane equivalent under Engine B is
likewise green: 129 passed, 3 skipped, 4 deselected. `test_meshlib_kernel.py` — outside
this slice's own scope, untouched — still reads 25 passed / 2 skipped under Engine B and
11 passed / 16 skipped under Engine A, unchanged from before this rework, confirming the
`supports_tracked()` docstring additions to `meshlib_kernel.py` broke nothing there either.

**Nothing resisted classification.** The task's own target — 0 unclassified failures under
Engine B — is reached exactly: every failure in §2's table is now a passing, engine-aware
assertion, and the two "beyond the three" shapes §4.4 found were classified (as the same
guard-refusal decision, at two more call sites) rather than left as a residue.

---

## 5 · The extension past the parity branch — 13 more, same pattern (2026-08-15)

§4's rework landed on a branch; by the time it reached `main`, `product-app-plan.md`'s
§10-AT "excision + artifact 6's third ruling" entry (2026-08-15, same day) had added the
DEFECT-1 excision (`scanned_cap_face_mask`, both `_csg_carve` branches, the healingcaps
fuse, the press fallback) and retired `closed_model_with_recesses` in favour of
`open_arch_with_through_holes` — 13 tests the parity branch never saw. The plan's own
"AT parity referee" entry records the consequence measured AT INTEGRATION, on `main`, where
`data/real` is present: **manifold 130/0, MeshLib 130/13** — 12 of the 13 read tracked
provenance directly (`_RecordingKernel`/`tracked.source`) or a real-fleet fixture, and the
13th is the one true-boolean-recess pin naming a real vendor cap by name. This section is
that extension, reworked the same way as §4 — one test/class at a time, `engine_expects`,
never a diluted tracked-path assertion — against the SAME five-file corpus.

### 5.1 · The 13, and the branch chosen for each (verified by running both engines directly
against the fixture each pin actually uses, this slice's own exploration — not inferred)

| test | non-tracked outcome | why |
|---|---|---|
| `test_csg_corpus.py::TestRealFleetGoldenMetrics::test_golden_metrics_on_a_real_cap6030_site` | `pytest.raises(ValueError, match="MeshLib")` on the bare `default_kernel().difference()` call (no fallback wrapper at this call site) | real, feature-rich cap6030 geometry is the §2.1/§4.4 self-intersection/coplanar class; **UNVERIFIED in this worktree** (`data/real` absent — skips before reaching the branch either way; the ledger's own "1 of 13" is the only confirmation it fires, at integration) |
| `test_deliverables.py::TestCapImprintHoles::test_the_imprint_hugs_the_cap_and_the_gum_survives` | whole-cut falls back to the press carve (`"the true-boolean recess could not be cut" … "MeshLib" … "the pressed carve was used instead"`), CSG-exact wall/floor assertions skipped | same cap6030 fixture as the row above, through the full `cap_imprint_holes` ladder; **UNVERIFIED in this worktree** for the same reason — inferred from the row above plus the established fin/deviated-cap precedent (§4.4), not measured directly here |
| `TestTheMergedCaplessArtifactDoesNotMove::test_the_excised_set_is_exactly_scan_provenance_intersect_mask` | `assert_fallback_notes(notes, "the exact cap could not be cut", "the provenance-tracked strip could not run")`; the tracked-ground-truth claim is skipped | VERIFIED directly: this exact site/pose trips the SAME coplanar intersection-guard branch its sibling pin already documents (2 notes) — no tracked result exists to re-derive the companion claim from, so the honest assertion is the sibling's own already-established fallback outcome, not a diluted re-proof |
| `TestDefect1MeasuredCapResidueIsExcised::test_the_bulge_does_not_survive_the_carve` | whole-cut falls back to the press carve; **the bulge-survivor assertion is kept, unweakened** | VERIFIED directly: the untracked `difference` ALSO refuses natively here ("Cannot separate mesh B…self-intersections") — but `_press_carve`'s own DEFECT-1 excision (`excise &= ~face_moved`, over the pristine arch) drops the bulge exactly as the tracked path does (0/128 survivors either way) |
| `…::test_the_gum_outside_the_mask_survives_untouched` | same whole-cut fallback; gum-survives assertion kept unweakened | VERIFIED directly: same site, same fallback, same result |
| `…::test_tool_provenance_faces_are_never_excised` | same whole-cut fallback; socket-shipped assertion kept unweakened | VERIFIED directly: the press carve still ships a non-empty recess piece (284 faces) |
| `…::test_the_bulge_does_not_survive_the_fused_composite` | tracked-strip-fallback note only (the union itself succeeds); **the bulge assertion is the OPPOSITE of the tracked claim — all 128 vertices survive** | VERIFIED directly, a genuine finding, not diluted: `arch_with_parts_fused`'s untracked branch substitutes a 0.45mm proximity-to-the-part-solid test for the tracked path's exact `source == 0`, and this fixture's own bulge sits a measured 0.400–0.403mm from the part surface — inside that radius almost everywhere — so the excision is defeated. Out of scope to fix (tests only, this slice) |
| `…::test_without_excise_sites_the_fuse_behaves_exactly_as_before` | tracked-strip-fallback note only | VERIFIED directly: the plain union succeeds; same shape as `TestArchWithPartsFused`'s own already-reworked siblings |
| `TestOpenArchWithThroughHoles::test_the_result_is_not_watertight_open_by_design` | tracked-strip-fallback note only; geometry claim kept unweakened | VERIFIED directly: the untracked `difference` succeeds on this clean-cylinder site |
| `…::test_zero_closure_provenance_faces_survive` | `assert_fallback_notes` + non-empty result; the tracked-source closure census is skipped (no ground truth) | VERIFIED directly: same clean site, same one-note fallback |
| `…::test_the_bore_pierces_no_floor_hit_inside_the_punch_footprint` | fallback note branches; the ray-hit assertion kept unweakened | VERIFIED directly: geometry unaffected by which strip mechanism selects it |
| `…::test_the_excision_holds_here_too` | **the whole artifact is ABSENT** — `out is None`, one note ("could not be built" … "ships without it" … names MeshLib) | VERIFIED directly: unlike `cap_imprint_parts`, this function has no intermediate press-carve rung — its outer `try/except` wraps the untracked fallback too, so the SAME native refusal that hits the bulging-cap carve above fails the whole artifact open to absence, exactly `test_a_totally_unbuildable_scan_fails_open_to_absence`'s own shape |
| `…::test_a_degenerate_template_falls_back_to_its_envelope_per_site` | 2 notes (the per-site envelope note, unchanged, then the tracked-strip note) | VERIFIED directly: the good site's own untracked difference succeeds |

`TestOpenArchWithThroughHoles::test_a_totally_unbuildable_scan_fails_open_to_absence` — the
class's 6th test — is untouched: verified byte-identical under both engines (it fails
before ever reaching the kernel, on an empty scan's own gum-ring band), which is exactly why
the task's own list names 5 of this class's 6 tests, not 6.

### 5.2 · The after-numbers, this worktree (`data/real` absent — the 2 rows above marked
UNVERIFIED still skip here; both engines, `-m "not slow"`, individual per-suite runs)

| suite | Engine A (manifold) | Engine B (meshlib) |
|---|---|---|
| `test_kernel.py` | 30 pass / 0 fail / 0 skip | 29 pass / 0 fail / 1 skip |
| `test_csg.py` | 40 pass / 0 fail (1 deselected) | 40 pass / 0 fail (1 deselected) |
| `test_csg_corpus.py` | 10 pass / 0 fail / 1 skip (2 deselected) | 10 pass / 0 fail / 1 skip (2 deselected) |
| `test_degeneracy.py` | 11 pass / 0 fail | 11 pass / 0 fail |
| `test_deliverables.py` | 51 pass / 0 fail / 1 skip (1 deselected) | 51 pass / 0 fail / 1 skip (1 deselected) |
| **TOTAL** | **142 / 0 / 2** (4 deselected) | **141 / 0 / 3** (4 deselected) |

Combined single-invocation (the same five files, one `pytest` call): manifold 142 passed, 2
skipped, 4 deselected in 12.60s; MeshLib 141 passed, 3 skipped, 4 deselected in 19.84s. The
skip-count asymmetry (2 vs 3) is unchanged from §4.6 and remains the same one pin
(`test_kernel.py::TestEngineSwitch`'s missing-package path).

**Zero failures on both engines — the task's own target for this extension, reached
exactly**, with two honest qualifications carried over from §5.1 rather than hidden: (1) the
two real-fleet-gated rows (`TestRealFleetGoldenMetrics`'s pin, `TestCapImprintHoles`'s
cap6030 pin) skip in every venv available to this worktree — their non-tracked branches are
STRUCTURALLY correct (they collect, they would run if `data/real` existed) but the actual
refusal they assert is confirmed only by the plan's own "AT INTEGRATION … MeshLib 130/13"
reading, not re-verified here; (2) `test_the_bulge_does_not_survive_the_fused_composite`'s
non-tracked branch asserts a genuine REGRESSION relative to the tracked claim (the bulge
survives, not "dies more slowly") — recorded as a finding in §5.1's own table, not smoothed
over, and out of scope to fix under this slice's own tests-only charter.
