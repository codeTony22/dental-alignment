"""THE DEGENERACY BATTERY (boolean-engine plan W3, 2026-08-13): "the corpus
gains the cases that break naive engines, because they are OUR everyday
geometry" — exactly-coplanar bore lids on machined floors, a floor clip
mated plane-against-plane with a cap's own base, duplicate/zero-area scan
triangles, two adjacent sites whose punches touch, a punch tangent to the
solidified skirt. Each is asserted against the CURRENT kernel
(``case_prep.pipeline.kernel.default_kernel()``, manifold via the seam).

STAGE-2 ACCEPTANCE HOOK (plan §6): this file is part of the Stage-0
conformance corpus. Per the plan's own W3 acceptance criterion — "all pass
on the current kernel; any future kernel candidate must pass the same
battery to enter Stage 2" — a from-scratch or licensed kernel proposed as a
Stage-2 candidate must pass this file UNCHANGED before it is eligible for
that evaluation. Nothing here may be loosened to make a candidate pass;
a candidate that cannot clear it does not enter Stage 2.

Fixtures are built LOCALLY in this file, per this suite's own no-test-to-
test-import convention (``test_csg.py``'s ``_annulus_topped_cylinder``,
``test_csg_corpus.py``'s ``_curved_sheet`` — each file owns its own copies
of the same shapes). Every expected number is derived from the
construction's own arithmetic, commented at the point of use. Where two
things must be EXACTLY coplanar or exactly tangent, the shared value is
ASSIGNED once and reused — never computed twice by two different paths
that could round to neighbouring ulps — and the degenerate contact itself
is verified INSIDE the test, on the actual built geometry, before the
boolean under test ever runs.
"""
from __future__ import annotations

import numpy as np
import pytest
import trimesh

from case_prep.pipeline.csg import (exact_cap_punch, fabricated_face_mask,
                                    solidify_shell, solidified_shell_cached,
                                    strip_tracked)
from case_prep.pipeline.kernel import default_kernel


def _pose_at(x: float, y: float, z: float) -> np.ndarray:
    m = np.eye(4)
    m[:3, 3] = [x, y, z]
    return m


class TestCoplanarBoreLidOnAMachinedFloor:
    """PLAN W3 #1 — clinical source: ``exact_cap_punch``'s own fan-lidded
    bore (``_lid_boundary_loops``, csg.py — most vendor healing-cap STLs
    export the implant-interface bore open) meeting a machined floor: a
    dish/platform artifact's own flat cut floor, or a scan region that
    happens to sit flush with the punch's own top. The naive failure
    mode: two faces that are the SAME plane, to the last ulp, on either
    side of a boolean cut — a coincident-plane classification a naive
    engine gets wrong by a single ulp and shreds into a non-manifold mess.

    ``offset_mm=0`` throughout: any positive offset routes through
    ``exact_cap_punch``'s self-heal union, and manifold3d's own MeshGL
    round-trip forces FLOAT32 precision on every vertex it touches —
    moving a coordinate by up to ~2.4e-7mm even where nothing
    geometrically changed (measured in ``test_csg_corpus.py``'s own
    ``_canonical_float32_triangles`` docstring). That would make a
    bit-exact coplanarity claim impossible to construct honestly. With
    offset 0, ``exact_cap_punch`` only copies, lids and poses the
    template — no boolean runs before the ONE boolean under test — so the
    punch's own lid plane is bit-identical to the fixture's own literal.
    """

    TOP_Z = 3.0  # the one number: the machined floor's plane. Never
    # recomputed below — every plane compared against it is built by
    # ASSIGNING this exact float, not deriving it a second way.

    @staticmethod
    def _open_bore_cap(radius: float = 2.0, bore_radius: float = 0.6,
                       height: float = 4.0, seg: int = 32) -> trimesh.Trimesh:
        """A closed side wall and bottom disc, OPEN annulus top — the same
        shape ``test_csg.py``'s own ``_annulus_topped_cylinder`` builds
        (rebuilt here per this suite's no-test-to-test-import convention)
        but flipped in z so the open bore sits at LOCAL z=0 and the body
        hangs below it (down to z=-height): a mean of literal zeros
        (every top-rim vertex, and ``_lid_boundary_loops``'s own centroid
        fan vertex) is exactly 0.0, so a pure z-translation by ``TOP_Z``
        lands the fan-lidded bore disc on the machined floor's plane with
        no other arithmetic in the way."""
        ang = np.linspace(0.0, 2.0 * np.pi, seg, endpoint=False)
        ca, sa = np.cos(ang), np.sin(ang)
        bot = np.column_stack([radius * ca, radius * sa, np.full(seg, -height)])
        top_outer = np.column_stack([radius * ca, radius * sa, np.zeros(seg)])
        top_inner = np.column_stack([bore_radius * ca, bore_radius * sa,
                                     np.zeros(seg)])
        centre = np.array([[0.0, 0.0, -height]])
        verts = np.vstack([bot, top_outer, top_inner, centre])
        n = seg
        ci = 3 * n
        faces = []
        for i in range(n):
            j = (i + 1) % n
            faces.append([i, j, n + j])                  # outer wall
            faces.append([i, n + j, n + i])
            faces.append([n + i, 2 * n + i, 2 * n + j])   # top annulus (open)
            faces.append([n + i, 2 * n + j, n + j])
            faces.append([j, i, ci])                      # bottom disc fan
        return trimesh.Trimesh(verts, np.asarray(faces, int), process=False)

    @classmethod
    def _flat_topped_block(cls, half: float = 10.0, depth: float = 12.0
                           ) -> trimesh.Trimesh:
        """A closed rectangular solid whose TOP face's z-coordinate is
        ``cls.TOP_Z`` — the literal appears directly in the vertex array,
        never computed from an ``extents / 2`` or a translate-then-shift
        that could round to a neighbouring ulp."""
        top_z = cls.TOP_Z
        bot_z = top_z - depth
        top = np.array([[-half, -half, top_z], [half, -half, top_z],
                        [half, half, top_z], [-half, half, top_z]])
        bot = np.array([[-half, -half, bot_z], [half, -half, bot_z],
                        [half, half, bot_z], [-half, half, bot_z]])
        verts = np.vstack([top, bot])
        faces = np.array([
            [0, 1, 2], [0, 2, 3],          # top
            [4, 6, 5], [4, 7, 6],          # bottom
            [0, 4, 1], [1, 4, 5],          # sides
            [1, 5, 2], [2, 5, 6],
            [2, 6, 3], [3, 6, 7],
            [3, 7, 0], [0, 7, 4],
        ])
        block = trimesh.Trimesh(verts, faces, process=False)
        trimesh.repair.fix_normals(block)
        return block

    def _punch(self) -> trimesh.Trimesh:
        cap = self._open_bore_cap()
        assert not cap.is_watertight, \
            "the fixture must start bore-open, or the fan lid under test " \
            "is never built at all"
        pose = _pose_at(0.0, 0.0, self.TOP_Z)
        return exact_cap_punch(cap, 0.0, pose)

    def test_the_punchs_fan_lid_and_the_blocks_top_face_are_bit_identical(self):
        """The degenerate contact itself, verified BEFORE the cut runs.

        LOOSENED (kernel-parity-scoreboard.md §2.2, 2026-08-15 — cited per
        the kernel-parity task's own instruction): the punch side of this
        bit-exact ``==`` is a MANIFOLD-SPECIFIC numerical accident, not a
        geometric requirement — manifold3d's own float32 MeshGL round-trip
        happens to preserve a round literal like ``TOP_Z = 3.0``
        losslessly, but ``exact_cap_punch``'s own unconditional self-heal
        (``union([punch, punch])``, csg.py, W5 rider (a)) genuinely
        RETRIANGULATES under MeshLib and moves the lid plane by
        ~5e-10mm — geometrically and clinically meaningless (three orders
        of magnitude below ``csg.py``'s own 1e-3mm^3 ``heal_fired``
        threshold — this is a coordinate drift, not a volume change, and
        it does not set ``heal_fired``), but enough to break bit-exact
        ``==``. The CONTRACT this precondition exists to protect is
        coplanarity within the margin the cut test below actually needs,
        not bit-exactness: 1e-6mm is five orders of magnitude tighter than
        the measured drift and nine orders looser than anything clinically
        significant. The block's own literal is untouched by any kernel
        and stays bit-exact."""
        punch = self._punch()
        block = self._flat_topped_block()
        assert float(punch.vertices[:, 2].max()) == pytest.approx(
            self.TOP_Z, abs=1e-6)
        assert float(block.vertices[:, 2].max()) == self.TOP_Z

    def test_the_cut_stays_watertight_at_the_exact_coplanar_seam(self):
        block = self._flat_topped_block()
        # already closed -> solidify_shell's passthrough branch, unchanged
        # (it only repairs winding, never moves a vertex) -- a weaker
        # kernel that cannot resolve two literally-identical face planes
        # would shred at the difference below, not here
        solid = solidified_shell_cached(block)
        punch = self._punch()

        cut = default_kernel().difference(solid, [punch])

        assert cut.is_watertight, \
            "a coincident-to-the-ulp bore lid / machined floor plane " \
            "shredded the cut instead of resolving cleanly"
        assert float(cut.volume) > 0.0
        assert float(cut.volume) < float(solid.volume), \
            "the cut must actually remove material, or this pin is vacuous"


class TestFloorClipAtExactlyTheCapsBasePlane:
    """PLAN W3 #2 — clinical source: ``exact_cap_punch``'s own visible-depth
    clip (csg.py, §10-AS.14: "the clip only limits depth, never extends
    it"). The clip's own box intersects the punch against a plane at
    ``floor_a``; when a caller passes ``floor_a`` at EXACTLY the cap
    template's own minimum z, the clip plane mates flush against the
    punch's own base — box face against solid face, zero gap, nothing
    below the plane left for the intersection to remove."""

    def test_the_clip_plane_exactly_mates_the_punchs_own_base(self):
        """The degenerate contact, MEASURED before the clipped call runs:
        build the same punch unclipped first, read its own minimum z off
        the actual mesh, and only THEN feed that exact value back in as
        ``floor_a`` — never an independently-computed constant that could
        round to a neighbouring ulp."""
        cap = trimesh.creation.cylinder(radius=2.0, height=4.0)
        template_min_z = float(np.asarray(cap.vertices, float)[:, 2].min())

        pose = np.eye(4)
        unclipped = exact_cap_punch(cap, 0.0, pose)
        pre_min_z = float(np.asarray(unclipped.vertices, float)[:, 2].min())

        gap = template_min_z - pre_min_z
        assert gap == 0.0, \
            "the punch's own base must sit exactly at the template's own " \
            "min z with offset_mm=0, or this pin proves nothing about a " \
            "flush-mated clip plane"

    def test_watertight_punch_and_the_floor_lands_at_floor_a(self, engine_expects):
        """ENGINE-AWARE (kernel-parity-scoreboard.md §2.1/§3, item 2's
        FLUSH-OPERAND DECISION, 2026-08-15): a floor clip flush with the
        punch's own base is EXACTLY the coplanar contact MeshLib's own
        guard exists to catch (an EMPTY or UNCHANGED result, depending on
        which side of MeshLib's ±1e-7mm contact tolerance this fixture's
        own retriangulation noise lands on) — DECIDED: accept the
        refusal, never pre-nudge a measured coordinate to appease one
        engine (``meshlib_kernel.py``'s own docstring). There is no
        fallback wrapper at THIS call site (``exact_cap_punch`` has no
        ``try`` around its own floor-clip intersection) — this test
        exercises the clip directly, so the honest non-tracked assertion
        is the guard's own loud, named refusal."""
        cap = trimesh.creation.cylinder(radius=2.0, height=4.0)
        floor_a = float(np.asarray(cap.vertices, float)[:, 2].min())  # -2.0,
        # the SAME value the previous test measures and calls the
        # degenerate contact -- passed straight through, not recomputed
        pose = np.eye(4)

        if not engine_expects.tracked:
            with pytest.raises(ValueError) as excinfo:
                exact_cap_punch(cap, 0.0, pose, floor_a=floor_a)
            message = str(excinfo.value)
            assert "guard" in message.lower()
            assert "MeshLib" in message
            return

        clipped = exact_cap_punch(cap, 0.0, pose, floor_a=floor_a)
        assert clipped.is_watertight, \
            "a clip plane flush with the tool's own base shredded the punch"

        block = trimesh.creation.box(extents=[20.0, 20.0, 12.0])
        cut = default_kernel().difference(block, [clipped])
        assert cut.is_watertight

        # probed like test_csg_corpus.py's TestCarveGoldenMetrics does: a
        # ray straight down the site's own axis crosses the block's top,
        # the empty recess, and the machined floor -- floor_a IS the
        # golden value here (pose is identity, so world z == floor_a)
        hits, *_ = cut.ray.intersects_location(
            ray_origins=[[0.0, 0.0, 10.0]], ray_directions=[[0.0, 0.0, -1.0]])
        assert len(hits) > 0, "the ray found no crossings at all"
        nearest = float(min(hits[:, 2], key=lambda z: abs(z - floor_a)))
        assert abs(nearest - floor_a) < 0.02, \
            f"floor at {nearest:.3f}, requested floor_a is {floor_a:.3f}"


class TestDuplicateAndZeroAreaScanTriangles:
    """PLAN W3 #3 — clinical source: "triangles a scanner emitted with
    near-zero area" (plan §0) — an intraoral scanner's own raw output
    regularly repeats a triangle exactly at a stitched seam and degenerates
    one to a sliver where two scan patches meet at a single vertex. This
    case is defined by MEASUREMENT, per the mission brief: run the current
    stack, observe what it actually does, and pin that.

    MEASURED (this file, 2026-08-14): ``solidified_shell_cached`` — the
    ONE entry point ``deliverables.py`` ever calls (``grep`` over
    ``pipeline/deliverables.py`` confirms all three call sites use the
    cached, checked wrapper; the raw ``solidify_shell`` is never called
    unguarded in production) — REFUSES with a named, actionable
    ``ValueError`` naming an edge count and a location, rather than
    producing a leaking non-manifold solid silently. This is NOT the
    silent-leak finding the mission brief warns about: the refusal is
    loud, and it happens BEFORE any tracked difference is ever attempted
    — the corrupted geometry never reaches a boolean at all. Pinned as
    the measured, deliberate, current contract; loosening it later is
    then a decision, not a regression nobody noticed."""

    @staticmethod
    def _sheet_with_defects() -> trimesh.Trimesh:
        """A curved open sheet (the same ``z = -0.12*y**2`` ridge every
        gum-following pin in this suite's neighbours uses, rebuilt here
        per the no-test-to-test-import convention) with two extra faces
        appended onto an otherwise healthy triangulation: (a) an EXACT
        duplicate of an existing interior face (the same three vertex
        INDICES, so the same three vertex positions, verbatim — no new
        geometry, just a repeat), and (b) a ZERO-AREA face built by
        reusing one of that face's own vertex indices twice, so two of
        its three corners are literally the same vertex — coincident by
        construction, not by a coordinate that merely rounds together."""
        n = 16
        xs, ys = np.meshgrid(np.linspace(-8, 8, n), np.linspace(-8, 8, n))
        zs = -0.12 * ys ** 2
        pts = np.column_stack([xs.ravel(), ys.ravel(), zs.ravel()])
        faces = []
        for i in range(n - 1):
            for j in range(n - 1):
                a = i * n + j
                faces.append([a, a + 1, a + n + 1])
                faces.append([a, a + n + 1, a + n])
        F = np.asarray(faces, int)
        k = len(F) // 2  # an interior face, well away from the sheet's own edge
        dup_face = F[k].copy()
        i0, i1, _i2 = F[k]
        zero_face = np.array([i0, i0, i1])  # two corners are literally vertex i0
        F2 = np.vstack([F, dup_face[None, :], zero_face[None, :]])
        return trimesh.Trimesh(pts, F2, process=False)

    def test_the_fixture_actually_carries_a_duplicate_and_a_zero_area_face(self):
        """Verify the degeneracy exists before trusting anything measured
        against it: the duplicate face's own vertex positions equal an
        earlier face's exactly, and the zero-area face's own triangle
        area is exactly 0.0 — never a tolerance."""
        sheet = self._sheet_with_defects()
        assert not sheet.is_watertight
        F = np.asarray(sheet.faces)
        V = np.asarray(sheet.vertices, float)

        dup_face, zero_face = F[-2], F[-1]
        earlier = next(f for f in F[:-2] if tuple(f) == tuple(dup_face))
        assert np.array_equal(V[earlier], V[dup_face]), \
            "the duplicated face's own vertex positions must be exact " \
            "repeats, or this pin proves nothing"
        assert zero_face[0] == zero_face[1], \
            "two of the zero-area face's corners must be the SAME vertex " \
            "index, not merely coincident coordinates"
        area = float(trimesh.triangles.area(V[zero_face][None, :])[0])
        assert area == 0.0

    def test_solidified_shell_cached_refuses_rather_than_leaks(self):
        sheet = self._sheet_with_defects()
        with pytest.raises(ValueError) as excinfo:
            solidified_shell_cached(sheet)
        message = str(excinfo.value)
        assert "not watertight" in message
        assert "open/non-manifold edge(s)" in message
        assert "(" in message and ")" in message  # names a location, not just a count

    def test_the_raw_mechanism_does_not_itself_guard_this_gap(self):
        """A secondary, explicit measurement (informational, NOT a
        finding on its own): ``solidify_shell`` alone — the plain
        mechanism, never called unguarded in production — returns a mesh
        WITHOUT raising, and that mesh is not watertight. This is exactly
        why the cached wrapper's own check exists; it is not the
        silent-leak finding the mission brief warns about, because
        nothing in this codebase ever calls the raw function without
        that guard (see the class docstring's own ``grep`` claim)."""
        sheet = self._sheet_with_defects()
        solid = solidify_shell(sheet, np.array([0.0, 0.0, 1.0]))
        assert not solid.is_watertight


class TestTwoAdjacentSitesWhosePunchesTouch:
    """PLAN W3 #4 — clinical source: two implant sites close enough
    together (a bridge span, adjacent healing caps) that their dilated
    recess tools reach each other — the BATCHED cut ``deliverables.py``
    runs (one ``difference(arch, tools)`` call carrying every site's own
    punch, never a difference per site) is exactly this shape. The naive
    failure mode: a wall FRAGMENT left standing between two recesses that
    should have merged into one open corridor, because the boolean
    misclassified the sliver where the two tools' dilated surfaces meet."""

    RADIUS_MM = 2.0
    OFFSET_MM = 0.2

    @classmethod
    def _reference_punch_radius(cls, cap: trimesh.Trimesh) -> float:
        """The dilated punch's OWN measured half-width at mid-height, off
        a single reference site posed at the origin — not assumed from
        ``RADIUS_MM + OFFSET_MM``, because vertex-normal dilation on this
        two-ring cylinder blends toward axial at the rim (measured:
        the wall reaches ~2.1456mm here, short of the naive 2.2mm sum) —
        a formula that ignored that would build a "tangent" pose that is
        not actually tangent to the geometry under test."""
        reference = exact_cap_punch(cap, cls.OFFSET_MM, np.eye(4))
        hits, *_ = reference.ray.intersects_location(
            ray_origins=[[0.0, 0.0, 0.0]], ray_directions=[[1.0, 0.0, 0.0]])
        assert len(hits) == 1, \
            "the reference punch must present exactly one crossing along " \
            "its own +x mid-height ray, or the measured radius is bogus"
        return float(hits[0, 0])

    def _cap(self) -> trimesh.Trimesh:
        return trimesh.creation.cylinder(radius=self.RADIUS_MM, height=4.0)

    def _poses(self, cap: trimesh.Trimesh):
        r = self._reference_punch_radius(cap)
        tangent_distance = 2.0 * r  # dilated surfaces exactly touch here
        overlap = 0.05              # nudged past tangency by this much
        d = tangent_distance - overlap
        assert d < tangent_distance
        return _pose_at(-d / 2.0, 0.0, 0.0), _pose_at(d / 2.0, 0.0, 0.0), d

    def test_the_dilated_punches_measurably_overlap_at_the_midpoint(self):
        """The degenerate contact, verified on the ACTUAL built punch
        meshes (``.contains``) before the shared cut runs — not inferred
        from the pose arithmetic alone, since a self-heal union sits
        between the pose and the final punch geometry."""
        cap = self._cap()
        pose1, pose2, _d = self._poses(cap)
        punch1 = exact_cap_punch(cap, self.OFFSET_MM, pose1)
        punch2 = exact_cap_punch(cap, self.OFFSET_MM, pose2)

        midpoint = np.array([[0.0, 0.0, 0.0]])
        assert bool(punch1.contains(midpoint)[0]), \
            "the midpoint between the two sites must sit inside punch 1"
        assert bool(punch2.contains(midpoint)[0]), \
            "the midpoint between the two sites must sit inside punch 2, " \
            "or this pin never built a genuine overlap at all"

    def test_the_batched_cut_is_watertight_with_no_wall_between_the_sites(self):
        cap = self._cap()
        pose1, pose2, d = self._poses(cap)
        punch1 = exact_cap_punch(cap, self.OFFSET_MM, pose1)
        punch2 = exact_cap_punch(cap, self.OFFSET_MM, pose2)

        block = trimesh.creation.box(extents=[20.0, 20.0, 12.0])
        # the batched form: every site's tool in ONE difference call, the
        # shape deliverables.py's own carve uses -- not two sequential cuts
        cut = default_kernel().difference(block, [punch1, punch2])

        assert cut.is_watertight, \
            "the overlapping-tool cut shredded instead of merging cleanly"

        midpoint = np.array([[0.0, 0.0, 0.0]])
        assert not bool(cut.contains(midpoint)[0]), \
            "a wall fragment survived at the overlap depth between the " \
            "two sites"

        site_centres = np.array([[-d / 2.0, 0.0, 0.0], [d / 2.0, 0.0, 0.0]])
        contains_centres = cut.contains(site_centres)
        assert not bool(contains_centres[0]), "site 1's recess is not open"
        assert not bool(contains_centres[1]), "site 2's recess is not open"


class TestPunchTangentToTheSkirt:
    """PLAN W3 #5 — clinical source: a site near the scan's own posterior
    edge, close enough that its recess tool reaches the boundary
    ``solidify_shell`` fabricates a skirt from (csg.py, W1's own
    ``fabricated_face_mask``). Reuses the tracked-op API from kernel.py
    the way ``test_csg_corpus.py``'s own
    ``TestTrackedLocalityAndConservativity`` does: conservativity means
    ZERO closure-provenance faces survive the strip, checked by identity
    (``TrackedResult.source``), never by a distance sample."""

    RADIUS_MM = 2.0

    @staticmethod
    def _flat_sheet(n: int = 24, half: float = 8.0) -> trimesh.Trimesh:
        """A perfectly FLAT open sheet (z=0 everywhere) rather than the
        usual curved ridge, so ``solidify_shell``'s skirt is a clean set
        of vertical planes at exactly x=+-half / y=+-half
        (``np.linspace``'s own endpoints are exact — verified below,
        never an arithmetic derivation), giving the punch a literal
        plane to graze rather than a curved wall."""
        xs, ys = np.meshgrid(np.linspace(-half, half, n),
                             np.linspace(-half, half, n))
        pts = np.column_stack([xs.ravel(), ys.ravel(), np.zeros(xs.size)])
        faces = []
        for i in range(n - 1):
            for j in range(n - 1):
                a = i * n + j
                faces.append([a, a + 1, a + n + 1])
                faces.append([a, a + n + 1, a + n])
        return trimesh.Trimesh(pts, np.asarray(faces), process=False)

    def _punch_and_solid(self):
        sheet = self._flat_sheet()
        solid = solidified_shell_cached(sheet)
        sheet_half = float(sheet.vertices[:, 0].max())  # 8.0, an exact
        # np.linspace endpoint -- assigned once, reused below, never
        # recomputed by any other path
        cap = trimesh.creation.cylinder(radius=self.RADIUS_MM, height=4.0)
        punch_x = sheet_half - self.RADIUS_MM  # 6.0
        pose = _pose_at(punch_x, 0.0, 0.0)
        # offset_mm=0: no self-heal union, so the punch's own vertices
        # stay bit-identical to the plain cylinder's, and the ONLY
        # boolean below is the tracked difference under test
        punch = exact_cap_punch(cap, 0.0, pose)
        return sheet, solid, punch, sheet_half

    def test_the_punchs_side_and_the_skirt_share_the_same_x_plane(self):
        """The degenerate contact, measured before the tracked cut runs:
        the sheet's own boundary reaches exactly x=8.0, ``solidify_shell``'s
        skirt copies that SAME x,y for every fabricated vertex (only z
        moves — the projection subtracts along ``up=[0,0,1]`` alone, so
        x,y are untouched, not merely close), and the punch reaches
        the skirt plane along a whole EDGE (top+bottom rim, at the pose's
        own aligned angle), not a single accidental point.

        LOOSENED (kernel-parity-scoreboard.md §2.2, 2026-08-15 — cited per
        the kernel-parity task's own instruction): the bit-exact vertex
        COUNT (2) this test used to assert is a manifold-specific
        retriangulation accident, not the geometric contract — the
        unconditional self-heal (``union([punch, punch])``, csg.py, fires
        even at ``offset_mm=0``) genuinely retriangulates under MeshLib
        and adds vertices exactly ON the tangent plane that the manifold
        path's own construction never introduces (measured: 10, not 2).
        The CONTRACT is a whole edge tangent to the plane — at least 2
        vertices ON it, spanning the punch's full height (both the top
        AND bottom rim reach it) — not a specific triangulation of that
        edge."""
        sheet, solid, punch, sheet_half = self._punch_and_solid()
        assert not sheet.is_watertight
        assert sheet_half == 8.0

        skirt_x = float(np.asarray(solid.vertices, float)[:, 0].max())
        assert skirt_x == sheet_half

        Vp = np.asarray(punch.vertices, float)
        at_plane = Vp[:, 0] == skirt_x
        assert int(at_plane.sum()) >= 2, \
            "the punch must graze the skirt plane along a whole edge " \
            "(top+bottom rim), or the degenerate contact this case " \
            "needs is not actually there"
        plane_zs = Vp[at_plane, 2]
        assert float(plane_zs.min()) == -2.0 and float(plane_zs.max()) == 2.0, \
            "the tangent contact must span the punch's full height (both " \
            "the top and bottom rim), whatever triangulation lands on it"

    def test_the_tracked_cut_is_watertight_and_conservative(self, engine_expects):
        """ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, 2026-08-15):
        this pin's whole point is the tracked op at a degenerate tangent
        contact — under a kernel without it, the honest assertion is the
        named refusal, verified against the exact same tangent-contact
        inputs."""
        sheet, solid, punch, _sheet_half = self._punch_and_solid()
        fabricated = fabricated_face_mask(sheet, solid)
        assert solid.is_watertight

        if not engine_expects.tracked:
            with pytest.raises(NotImplementedError, match="difference_tracked"):
                default_kernel().difference_tracked(
                    solid, [punch], fabricated.astype(np.int64))
            return

        tracked = default_kernel().difference_tracked(
            solid, [punch], fabricated.astype(np.int64))
        assert tracked.mesh.is_watertight, \
            "the tangent-to-the-skirt cut shredded instead of resolving cleanly"
        assert tracked.base_groups == 2, \
            "the shell must have been split scan-vs-closure, or " \
            "conservativity below proves nothing"

        keep = strip_tracked(tracked)
        closure_provenance = (tracked.source == 1)
        assert int(closure_provenance.sum()) > 0, \
            "solidify fabricated no closure at all here -- vacuous pin"
        assert not (keep & closure_provenance).any(), \
            "a closure-provenance face survived the strip at the exact " \
            "tangent seam -- conservativity broke where it mattered most"
