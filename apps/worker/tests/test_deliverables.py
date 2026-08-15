"""Arch-level deliverable composition (client spec, 2026-07-11):

  2. the doctor's WHOLE arch with the aligned healing cap covering the scanned gap;
  3. the arch with the scanned healing-cap region REMOVED and the construction part in its
     place — the composition of the aligned construction with the cap-free arch.

The removal is face-culling within the aligned cap's cylindrical region (visual/deliverable
composite; a watertight CSG variant can follow via the SDF engine when a vendor requires it).
"""
from __future__ import annotations

import collections

import numpy as np
import pytest
import trimesh

from case_prep.pipeline.deliverables import (arch_with_parts,
                                              arch_with_parts_fused,
                                              remove_cap_region)


def _arch_with_bump(bump_center=(0.0, 0.0, 2.0)):
    # subdivided: a raw box has 8 corner vertices — nothing like a scan's dense surface,
    # and the collar-height sampling (like any scan-driven logic) needs real point density
    sheet = trimesh.creation.box(extents=[40, 20, 1])
    for _ in range(4):
        sheet = sheet.subdivide()
    bump = trimesh.creation.cylinder(radius=2.0, height=4.0)
    bump.apply_translation(bump_center)
    return trimesh.util.concatenate([sheet, bump])


def _pose_at(x, y, z):
    m = np.eye(4)
    m[:3, 3] = [x, y, z]
    return m


class _RecordingKernel:
    """Wraps the process's real kernel (``case_prep.pipeline.kernel.
    default_kernel()``), recording every ``TrackedResult`` a
    ``difference_tracked`` call produces. This is the seam the provenance
    pins below use to get at GROUND-TRUTH per-face ``source``/``base_groups``
    — the same ``TrackedResult`` ``_csg_carve`` itself reads to decide
    ``inside`` — without re-deriving any of ``_csg_carve``'s own internal
    geometry (the gum ring, the floor depth, the punch) a second time."""

    def __init__(self):
        from case_prep.pipeline.kernel import default_kernel as _dk

        self._inner = _dk()
        self.tracked_results = []

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def difference_tracked(self, *args, **kwargs):
        result = self._inner.difference_tracked(*args, **kwargs)
        self.tracked_results.append(result)
        return result


def _true_tool_mask_for(piece, cut, true_tool):
    """Maps every face of ``piece`` (a subset of ``cut``'s own faces, built
    via ``cut.faces[mask]`` + ``remove_unreferenced_vertices()`` — exactly
    ``_csg_carve``'s own ``out``/``socket`` idiom) back to its origin face in
    ``cut`` by exact vertex-coordinate identity (``remove_unreferenced_
    vertices`` only filters and re-indexes; it never moves a surviving
    vertex), and returns the corresponding ``true_tool`` ground-truth value
    per ``piece`` face — a ``len(piece.faces)`` bool array."""
    Vc = np.asarray(cut.vertices, float)
    Fc = np.asarray(cut.faces)
    sig_to_idx = {}
    for fi, f in enumerate(Fc):
        sig = tuple(sorted(tuple(np.round(Vc[v], 6)) for v in f))
        sig_to_idx[sig] = fi
    Vp = np.asarray(piece.vertices, float)
    Fp = np.asarray(piece.faces)
    out = np.zeros(len(Fp), bool)
    for i, f in enumerate(Fp):
        sig = tuple(sorted(tuple(np.round(Vp[v], 6)) for v in f))
        out[i] = true_tool[sig_to_idx[sig]]
    return out


def _ridge_sheet(n=40, extent=8.0):
    """A ridge-curved open sheet (z = -0.12*y^2) — the same fixture several
    ``TestCapImprintHoles`` pins already use for a real, non-flat gum
    surface."""
    xs, ys = np.meshgrid(np.linspace(-extent, extent, n),
                         np.linspace(-extent, extent, n))
    zs = -0.12 * ys ** 2
    pts = np.column_stack([xs.ravel(), ys.ravel(), zs.ravel()])
    faces = []
    for i in range(n - 1):
        for j in range(n - 1):
            a = i * n + j
            faces.append([a, a + 1, a + n + 1])
            faces.append([a, a + n + 1, a + n])
    return trimesh.Trimesh(pts, np.asarray(faces), process=False)


def _flat_sheet(n=19, extent=8.0):
    xs, ys = np.meshgrid(np.linspace(-extent, extent, n),
                         np.linspace(-extent, extent, n))
    pts = np.column_stack([xs.ravel(), ys.ravel(), np.zeros(xs.size)])
    faces = []
    for i in range(n - 1):
        for j in range(n - 1):
            a = i * n + j
            faces.append([a, a + 1, a + n + 1])
            faces.append([a, a + n + 1, a + n])
    return trimesh.Trimesh(pts, np.asarray(faces), process=False)


def _bulging_arch(template_r=2.0, bulge_r=2.4, height=4.0,
                  bump_center=(0.0, 0.0, 2.0)):
    """DEFECT 1's own scene (client-ruled, live verification 2026-08-15): a
    gum sheet plus a cap-SHAPED bump that stands ``bulge_r - template_r``
    (0.4mm) PROUD of the posed template — the scanned cap deviating from its
    CAD, exactly the fleet's own measured class (RMS 0.25/p90 0.35mm). The
    catalog rim radius a real site carries describes the PHYSICAL part (what
    the scan actually measures), so a caller's ``rim_r`` here must clear the
    bulge — a rim sized to the template's own (smaller, deviated) radius
    would refuse the bulge at the cylinder pre-cut before the classifier's
    band/core rungs ever ran, which is not the defect this fixture is FOR.
    Returns ``(arch, template, pose, bulge)`` — ``bulge`` on its own, for a
    caller that wants to name specific proud vertices by coordinate."""
    sheet = trimesh.creation.box(extents=[40, 20, 1])
    for _ in range(4):
        sheet = sheet.subdivide()
    bulge = trimesh.creation.cylinder(radius=bulge_r, height=height,
                                      sections=64)
    bulge.apply_translation(bump_center)
    arch = trimesh.util.concatenate([sheet, bulge])
    template = trimesh.creation.cylinder(radius=template_r, height=height,
                                         sections=64)
    pose = _pose_at(*bump_center)
    return arch, template, pose, bulge


class TestRemoveCapRegion:
    def test_removes_faces_inside_the_cap_cylinder(self):
        arch = _arch_with_bump()
        n_before = len(arch.faces)
        out = remove_cap_region(arch, pose_matrix=_pose_at(0, 0, 2.0),
                                radius_mm=3.0, half_height_mm=4.0)
        assert len(out.faces) < n_before
        # nothing left within the removal cylinder around the site
        v = np.asarray(out.vertices, float)
        d = np.linalg.norm(v[:, :2], axis=1)
        assert not ((d < 2.0) & (v[:, 2] > 1.0)).any()

    def test_leaves_distant_geometry_untouched(self):
        arch = _arch_with_bump()
        out = remove_cap_region(arch, pose_matrix=_pose_at(0, 0, 2.0),
                                radius_mm=3.0, half_height_mm=4.0)
        v = np.asarray(out.vertices, float)
        assert (np.abs(v[:, 0]) > 15).any()  # the sheet's far ends survive

    def test_input_not_mutated(self):
        arch = _arch_with_bump()
        before = len(arch.faces)
        remove_cap_region(arch, _pose_at(0, 0, 2.0), 3.0, 4.0)
        assert len(arch.faces) == before


class TestArchWithParts:
    def test_concatenates_posed_parts_onto_the_arch(self):
        arch = _arch_with_bump()
        part = trimesh.creation.cylinder(radius=1.0, height=3.0)
        out = arch_with_parts(arch, [(part, _pose_at(5.0, 0.0, 3.0))])
        assert len(out.vertices) > len(arch.vertices)
        v = np.asarray(out.vertices, float)
        near = v[np.linalg.norm(v - [5.0, 0.0, 3.0], axis=1) < 2.5]
        assert len(near) > 0  # the part is present at its pose


class TestArchWithPartsFused:
    """§10-AT 3b: the downloadable composites become TRUE BOOLEAN UNIONS. Where a
    part's pose buries part of its own volume inside the arch, ``arch_with_parts``'s
    concatenation leaves that buried half standing in the file as an internal wall
    the arch's own shell still surrounds; the true union merges the overlap so the
    buried half is ordinary interior material, indistinguishable from the shell
    around it — exactly what ``_csg_carve``'s own recess cut already proves for a
    subtraction, now proven here for a union."""

    def _sunk_part(self):
        # a healing-cap-shaped part sunk HALF into the bump-slab fixture's own bump
        # (radius 2.0, world z 0..4): a part radius of 1.0 stays fully inside the
        # bump's footprint everywhere it is embedded, so the buried half is
        # genuinely interior, not poking out the bump's own side wall. Posed so it
        # spans z 2.5..5.5: 1.5mm buried inside the bump, 1.5mm standing proud of
        # it — a real half-sink, not a token overlap.
        arch = _arch_with_bump()
        part = trimesh.creation.cylinder(radius=1.0, height=3.0)
        pose = _pose_at(0.0, 0.0, 4.0)
        return arch, part, pose

    def test_the_true_union_leaves_no_interior_wall_standing(self, engine_expects):
        """ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, 2026-08-15):
        under a kernel without ``union_tracked`` the fallback ladder
        (``default_kernel().union`` — still a REAL boolean union, only its
        strip is distance-based instead of provenance-exact) produces the
        SAME underlying geometry — verified directly, this slice's own
        exploration: 0.0 interior fraction either way — so every assertion
        below is unweakened; only the notes check branches."""
        from case_prep.pipeline.csg import solidified_shell_cached

        arch, part, pose = self._sunk_part()
        solid = solidified_shell_cached(arch)

        # the fixture check: the part really is half-buried, or this pin proves
        # nothing about what the union did
        posed_part = part.copy()
        posed_part.apply_transform(pose)
        part_centroids = np.asarray(posed_part.triangles_center, float)
        buried = solid.contains(part_centroids)
        assert buried.sum() > 0.2 * len(part_centroids), \
            "the fixture must genuinely bury part of the part"

        fused, notes = arch_with_parts_fused(arch, [(part, pose)])
        if engine_expects.tracked:
            assert notes == []
        else:
            engine_expects.assert_fallback_notes(
                notes, "the provenance-tracked strip could not run")
        inside = solid.contains(np.asarray(fused.triangles_center, float))
        # numerical skin only: a boundary face's centroid can read either side of
        # contains() by floating-point noise — the true union leaves NO deliberate
        # interior wall the way the raw concatenation below does
        assert inside.sum() <= 0.02 * len(fused.faces), \
            "the true union must not leave an internal wall standing inside the slab"

    def test_the_plain_concatenation_leaves_that_same_wall_standing(self):
        """The comparison the pin above is FOR: on the identical fixture, the
        concatenation (the thing this function replaces at the call sites) really
        does ship the buried half untouched — proving the fused pin measures a real
        difference, not an artifact of a fixture that was never buried at all."""
        arch, part, pose = self._sunk_part()
        from case_prep.pipeline.csg import solidified_shell_cached

        solid = solidified_shell_cached(arch)
        concatenated = arch_with_parts(arch, [(part, pose)])
        posed_part = part.copy()
        posed_part.apply_transform(pose)
        part_centroids = np.asarray(posed_part.triangles_center, float)
        buried = solid.contains(part_centroids)
        assert buried.sum() > 0.2 * len(part_centroids)
        # every one of those buried faces is still present, untouched, in the
        # concatenated output — that is the wall the fused builder exists to erase
        assert len(concatenated.faces) >= len(part.faces)

    def test_the_scans_own_far_reaches_survive_and_the_base_stays_stripped(
            self, engine_expects):
        """ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, 2026-08-15):
        see ``test_the_true_union_leaves_no_interior_wall_standing`` — the
        distance-based fallback strip produces the same underlying shape,
        verified directly; only the notes check branches."""
        arch, part, pose = self._sunk_part()
        fused, notes = arch_with_parts_fused(arch, [(part, pose)])
        if engine_expects.tracked:
            assert notes == []
        else:
            engine_expects.assert_fallback_notes(
                notes, "the provenance-tracked strip could not run")
        v = np.asarray(fused.vertices, float)
        assert (np.abs(v[:, 0]) > 15).any(), \
            "the sheet's far ends must survive the strip"
        scan_floor = float(np.asarray(arch.vertices, float)[:, 2].min())
        assert not (v[:, 2] < scan_floor - 0.2).any(), \
            "nothing may ship below the scan's own deepest point — a fabricated " \
            "base survived the strip"

    def test_a_degenerate_part_falls_back_alone_while_the_rest_fuse(
            self, engine_expects):
        """ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, 2026-08-15):
        under a kernel without ``union_tracked`` the good part's own union
        ALSO falls back to the distance strip, on top of the per-part
        note this pin already names — two notes, not one, the second
        appended strictly after (``arch_with_parts_fused``'s own order)."""
        arch, good_part, good_pose = self._sunk_part()
        degenerate = trimesh.Trimesh()
        fused, notes = arch_with_parts_fused(
            arch, [(degenerate, _pose_at(0.0, 0.0, 0.0)), (good_part, good_pose)])
        if engine_expects.tracked:
            assert len(notes) == 1
        else:
            assert len(notes) == 2
            assert "the provenance-tracked strip could not run" in notes[1]
        assert notes[0].startswith("part 1")
        assert "concatenated instead" in notes[0]
        # the good part (index 2) still fused in — its exposed top survives
        v = np.asarray(fused.vertices, float)
        near = v[np.linalg.norm(v - [0.0, 0.0, 5.5], axis=1) < 1.5]
        assert len(near) > 0, "the good part must still be present, fused"

    def test_a_totally_unbuildable_arch_falls_open_to_the_whole_concatenation(self):
        """The OTHER honest degradation: not a per-part failure but a whole-
        composite one — nothing here can even solidify. Never a dead package."""
        empty_arch = trimesh.Trimesh()
        part = trimesh.creation.cylinder(radius=1.0, height=3.0)
        pose = _pose_at(0.0, 0.0, 0.0)
        fused, notes = arch_with_parts_fused(empty_arch, [(part, pose)])
        assert len(notes) == 1
        assert "concatenated instead" in notes[0]
        assert not notes[0].startswith("part ")
        # the fallback IS arch_with_parts — the part's own geometry still ships
        assert len(fused.faces) >= len(part.faces)

    def test_input_not_mutated(self):
        arch, part, pose = self._sunk_part()
        arch_faces_before = len(arch.faces)
        part_faces_before = len(part.faces)
        arch_with_parts_fused(arch, [(part, pose)])
        assert len(arch.faces) == arch_faces_before
        assert len(part.faces) == part_faces_before


class TestArchWithCleanHoles:
    """Client spec v2 (2026-07-12) + socket fix (2026-07-14): each cap region becomes a
    floored SOCKET (closed at the bottom — reads solid, not a black void) whose wall is
    bridged to the surrounding scan surface by a collar annulus at the local gingiva
    height, so the socket reads as part of the model instead of a tube in a crater."""

    def test_bore_wall_meets_a_surface_collar(self):
        from case_prep.pipeline.deliverables import arch_with_clean_holes

        arch = _arch_with_bump()
        out = arch_with_clean_holes(arch, [(_pose_at(0, 0, 2.0), 3.0)])
        v = np.asarray(out.vertices, float)
        r = np.linalg.norm(v[:, :2], axis=1)
        # the bore wall sits at requested radius + the cull margin
        wall = v[(np.abs(r - 3.6) < 0.2) & (v[:, 2] > -9.0)]
        assert len(wall) >= 40, "no bore wall"
        # the collar annulus covers the crater edge OUTWARD of the wall, near surface z
        collar = v[(r > 3.7) & (r < 6.0) & (np.abs(v[:, 2] - 0.5) < 1.5)]
        assert len(collar) >= 40, "no covering collar at the surface"
        # SOCKET (client fix 2026-07-14, replaces the earlier open-through spec): the
        # bore has a FLOOR so the model reads solid, not a black void
        floor = v[(r < 2.4) & (v[:, 2] > -8.5) & (v[:, 2] < -4.0)]
        assert len(floor) >= 20, "the socket needs a floor"
        # and the scanned cap is still gone from the opening
        assert not ((r < 2.4) & (v[:, 2] > 1.5)).any()

    def test_input_not_mutated(self):
        from case_prep.pipeline.deliverables import arch_with_clean_holes

        arch = _arch_with_bump()
        before = len(arch.faces)
        arch_with_clean_holes(arch, [(_pose_at(0, 0, 2.0), 3.0)])
        assert len(arch.faces) == before

    def test_bore_faces_point_at_the_viewer(self):
        """Review 2026-07-14 (verified in MeshLab semantics): our own viewers render
        DoubleSide so an inside-out bore LOOKS fine locally, but the STL goes to labs
        whose tools shade/cull by the normals — the socket read as a black void again.
        Looking INTO the socket from above: floor and collar face +z, the wall faces
        the axis (inward)."""
        from case_prep.pipeline.deliverables import _hole_bore

        bore = _hole_bore(np.eye(4), radius_mm=3.6, collar_z_local=0.0, depth_mm=8.0)
        n = np.asarray(bore.face_normals, float)
        c = np.asarray(bore.triangles_center, float)
        floor = c[:, 2] < -7.9
        assert n[floor, 2].mean() > 0.9, "socket floor must face up (+z)"
        collar = (c[:, 2] > -0.1) & (np.linalg.norm(c[:, :2], axis=1) > 3.6)
        assert n[collar, 2].mean() > 0.9, "collar annulus must face up (+z)"
        wall = (c[:, 2] < -0.5) & (c[:, 2] > -7.5)
        radial = c[wall, :2] / np.linalg.norm(c[wall, :2], axis=1, keepdims=True)
        assert (n[wall, :2] * radial).sum(axis=1).mean() < -0.9, \
            "bore wall must face inward (toward the axis)"


class TestCapImprintHoles:
    """THE SEAT IS THE CAP'S ENVELOPE SOCKET (client 2026-08-06 §10-AO, reshaped
    2026-08-09 on the competitor comp): the socket is the cap's REVOLUTE ENVELOPE —
    per-height maximum radius plus the relief, lathed closed — not the cap's exact
    tessellated surface. The exact surface faithfully reproduced the screw slot
    into the floor and left 6,272 straddling fringe triangles on a real case; the
    competitor's pocket the client pointed at is the clean envelope. Walls wound
    inward, a FLAT floor at the cap's offset base, mouth OPEN at the gum line.
    sites are (template, pose_matrix, offset_mm, rim_radius_mm) — the radius only
    feeds the per-site cylinder fallback."""

    def _cap(self):
        return trimesh.creation.cylinder(radius=2.0, height=4.0)

    def _site(self, offset=0.2):
        return (self._cap(), _pose_at(0, 0, 2.0), offset, 2.0)

    def test_only_the_caps_footprint_is_culled(self, engine_expects):
        """ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, 2026-08-15):
        the geometry itself is unaffected by which strip mechanism selects
        it — verified directly, this slice's own exploration — only the
        notes check branches."""
        from case_prep.pipeline.deliverables import cap_imprint_holes

        arch = _arch_with_bump()
        out, notes = cap_imprint_holes(arch, [self._site()])
        if engine_expects.tracked:
            assert notes == []
        else:
            engine_expects.assert_fallback_notes(
                notes, "the provenance-tracked strip could not run")
        v = np.asarray(out.vertices, float)
        r = np.linalg.norm(v[:, :2], axis=1)
        # nothing of the ARCH survives inside the dilated footprint (2.0 + 0.2);
        # the liner itself sits ON that surface, so probe strictly inside it
        assert not ((r < 1.8) & (v[:, 2] > 0.8) & (v[:, 2] < 3.8)).any()
        # THE OVERCUT ENDS: the old cylinder ate everything out to rim+0.6 (3.6mm
        # here) — this ring held ZERO vertices under it. The fixture sheet's
        # ~1.3mm vertex spacing puts only a handful in the ring; any is the proof.
        sheet_near = (r > 2.5) & (r < 3.4) & (np.abs(v[:, 2]) < 0.6)
        assert sheet_near.sum() >= 5, "the gum beside the cap must survive"

    def test_the_recess_is_pressed_to_the_floor_never_a_bore(self):
        """The carve (§10-AS.10): everything inside the rim lies AT the floor —
        the scanned cap is pressed flat, nothing stands in the recess, and
        there is no synthetic 8mm bore underneath.

        §10-AS.12 re-aimed this pin: the CSG floor is a MACHINED DISC cut by
        the punch tool, not the cap's own dense mesh pressed flat, so the
        vertex count near the axis collapsed to the punch's own coarse fan
        (a handful of vertices, not the cap's hundreds) — the truth that
        survives is the VOID (nothing stands in it) and the FLOOR (a ray
        finds it), not a minimum vertex count."""
        from case_prep.pipeline.deliverables import cap_imprint_holes

        arch = _arch_with_bump()
        out, _ = cap_imprint_holes(arch, [self._site()])
        v = np.asarray(out.vertices, float)
        r = np.linalg.norm(v[:, :2], axis=1)
        # THE VOID IS EMPTY: nothing stands between the machined floor
        # (world z ~ -0.2mm — the interior clamp 0.3mm above the fixture's
        # own -0.5mm underside) and the mouth
        void = (r < 1.7) & (v[:, 2] > 0.1) & (v[:, 2] < 3.8)
        assert not void.any(), "something still stands in the recess's void"
        # THE FLOOR EXISTS: looking down into the seat, geometry is there
        down = out.ray.intersects_any(ray_origins=[[0.0, 0.0, 0.3]],
                                      ray_directions=[[0.0, 0.0, -1.0]])
        assert bool(down[0]), "the seat needs its floor"
        # and NOT the old 8mm synthetic bore: nothing deep under the seat
        assert not ((r < 2.5) & (v[:, 2] < -2.0)).any(), \
            "the seat must be the cap's own depth, not a synthetic bore"

    def test_the_seat_has_the_caps_floor_and_an_open_mouth(self):
        from case_prep.pipeline.deliverables import cap_imprint_holes

        arch = _arch_with_bump()
        out, _ = cap_imprint_holes(arch, [self._site()])
        # THE FLOOR PIN: looking DOWN into the seat from inside its mouth, the
        # cap's offset base must be there — the seat is closed underneath
        down = out.ray.intersects_any(ray_origins=[[0.0, 0.0, 0.3]],
                                      ray_directions=[[0.0, 0.0, -1.0]])
        assert bool(down[0]), "the seat needs the cap's floor"
        # THE OPEN MOUTH: looking UP out of the seat, nothing may cap it — the
        # full-closed-liner mistake would leave the cap's top as a floating lid
        up = out.ray.intersects_any(ray_origins=[[0.0, 0.0, 0.9]],
                                    ray_directions=[[0.0, 0.0, 1.0]])
        assert not bool(up[0]), "the seat's mouth must be open at the gum line"

    def test_the_floor_faces_up_into_the_seat(self):
        """The carve preserves the shell's own orientation: pressed floor faces
        keep facing UP into the recess. Judged on real-area faces only — a cap
        side wall squashed onto the floor is a zero-area sliver whose normal is
        numerical noise and whose render is no pixels at all.

        §10-AS.12 re-aimed the numbers: the floor is now the punch tool's own
        flat bottom disc, cut in at the interior clamp — 0.3mm above the
        fixture box's own -0.5mm underside, i.e. world z ~ -0.2mm — and its
        triangle fan's centroids sit at ~2/3 of the wall radius (~1.8mm), not
        near the axis where the old pressed-cap-vertex floor was densest."""
        from case_prep.pipeline.deliverables import cap_imprint_holes

        arch = _arch_with_bump()
        out, _ = cap_imprint_holes(arch, [self._site()])
        n = np.asarray(out.face_normals, float)
        c = np.asarray(out.triangles_center, float)
        area = np.asarray(out.area_faces, float)
        r = np.linalg.norm(c[:, :2], axis=1)
        # the fixture's cap is a CLOSED cylinder, so its bottom disc presses
        # onto the floor too (coplanar, down-facing) — a real scan's cap
        # region is one open sheet with no second layer. The guarantee to
        # hold: an up-facing floor EXISTS (a fold-over would erase it).
        floor = (r < 2.0) & (np.abs(c[:, 2] + 0.2) < 0.15) & (area > 0.05) \
            & (n[:, 2] > 0.9)
        assert floor.sum() >= 10, "no up-facing floor faces found"

    def test_no_kept_face_touches_the_inside_of_the_exact_cap(self, engine_expects):
        """THE FRINGE KILL (client 2026-08-09, screenshot): the centroid cull kept
        triangles that STRADDLE the socket wall — 6,272 of them on cap7020 — and
        their needle tips overhung the hole as a comb of spikes. The cull is now
        by ANY vertex: a kept face may not have a single vertex inside the cut
        tool. Re-derived here independently of the builder.

        §10-AS.14 (client 2026-08-10: "why is the hole bigger than the healing
        cap") retired the revolute envelope as the CUT tool — the tool is now
        the cap's own solid dilated by the gingival offset ONLY, so this pin
        is judged against THAT exact-dilated cap, not the wider envelope.
        (The envelope's own gum-survives promise moved to the fringe-margin
        pin below — the whole point is that gum now legitimately sits
        between the exact cap and where the old envelope used to cut.)

        ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, 2026-08-15): the
        cull geometry itself is unaffected by which strip mechanism
        selects it — verified directly; only the notes check branches."""
        from case_prep.pipeline.deliverables import cap_imprint_holes

        arch = _arch_with_bump()
        out, notes = cap_imprint_holes(arch, [self._site()])
        if engine_expects.tracked:
            assert notes == []
        else:
            engine_expects.assert_fallback_notes(
                notes, "the provenance-tracked strip could not run")
        posed = self._cap()
        n = np.asarray(posed.vertex_normals, float)
        posed.vertices = np.asarray(posed.vertices, float) + n * 0.2
        posed.apply_transform(_pose_at(0, 0, 2.0))
        tri = np.asarray(out.triangles, float).reshape(-1, 3)
        # liner vertices sit ON the exact cap's own surface — contains() may
        # call surface points either way, so probe a hair OUTSIDE its skin
        shrunk = posed.copy()
        shrunk.vertices -= np.asarray(shrunk.vertex_normals, float) * 0.02
        assert not shrunk.contains(tri).any(), \
            "a kept face still reaches inside the socket"

    def test_the_recess_is_the_caps_exact_surface(self, engine_expects):
        """A cap with a protruding FIN (or, on real caps, a recessed slot).

        §10-AO (2026-08-09) chose the smooth per-height ENVELOPE for the cut
        tool — the fin was meant to widen the whole ring at its height, so
        the liner would carry no azimuthal detail. §10-AS.14 (2026-08-10,
        client on the competitor comp: "why is the hole bigger than the
        healing cap... subtraction is the exact, we should not be inferring
        anything here") OVERRULED that: the cut tool is the cap's own exact
        solid, dilated only by the gingival offset. Both directions are
        recorded here — this pin now proves the INVERSE of what it proved
        on 2026-08-09: the recess follows the fin's own footprint (a probe
        just past the fin is cut away) while the gum on the OPPOSITE side,
        which the old fat envelope would have eaten too, now survives.

        ENGINE-AWARE (kernel-parity-scoreboard.md §2.1, item 1 generalised,
        2026-08-15): the fin makes this operand genuinely self-intersecting
        under a boolean's own contour test the same way a vertex-normal-
        dilated screw slot does (§2.4) — MeshLib's own boolean natively
        refuses ("Bad contour ... self-intersections") where manifold3d
        succeeds. There is no per-boolean fallback wrapper HERE (unlike
        ``_csg_carve``'s own tracked-vs-distance ladder): the WHOLE tracked
        CSG carve fails and ``cap_imprint_parts``'s own outer ladder takes
        over — the one-shell PRESS CARVE, a genuinely different algorithm
        (a smooth per-height envelope, §10-AS.10) that does not claim to
        follow the fin's own azimuthal detail at all. So the fin-following
        assertions below are CSG-path-specific; under the non-tracked
        engine only the refusal and the fallback landing are verified."""
        from case_prep.pipeline.deliverables import (
            _envelope_solid, cap_imprint_holes)

        # the fin sits LOW on the cap (world z 0..1) so its band overlaps the
        # part of the cut the gum-line clip keeps — a fin above the collar
        # would test nothing, since neither implementation cuts up there
        fin = trimesh.creation.box(extents=[1.4, 0.6, 1.0])
        fin.apply_translation([2.0, 0.0, -1.5])  # sticks out to r=2.7, z -2..-1
        capped = trimesh.util.concatenate([self._cap(), fin])
        pose = _pose_at(0, 0, 2.0)
        arch = _arch_with_bump()
        out, notes = cap_imprint_holes(arch, [(capped, pose, 0.2, 2.0)])
        if not engine_expects.tracked:
            engine_expects.assert_fallback_notes(
                notes, "the true-boolean recess could not be cut")
            assert "MeshLib" in notes[0]
            assert "the pressed carve was used instead" in notes[0]
            assert len(out.faces) > 0, \
                "the pressed-carve fallback must still ship a recess"
            return
        # DEFECT B (client-ruled, live verification 2026-08-15): the fin
        # makes the socket's own boundary genuinely non-simple (3 loops,
        # verified directly) — the collar bridge fails OPEN here, honestly,
        # rather than guess at a mangled ring; the fin's own recess claims
        # below are unaffected.
        assert notes == [
            "site 1: the machined mouth could not be read as one clean "
            "loop (3 found) — the collar bridge was skipped"]

        # the reference shapes: the EXACT cut tool (cap+fin, dilated by the
        # offset only — mirrors ``_exact_cap_punch``) and the OLD fat
        # envelope (§10-AO) that would have widened uniformly for the fin
        exact = capped.copy()
        n = np.asarray(exact.vertex_normals, float)
        exact.vertices = np.asarray(exact.vertices, float) + n * 0.2
        exact.apply_transform(pose)
        envelope = _envelope_solid(capped, 0.2)
        envelope.apply_transform(pose)

        # ON THE FIN'S BEARING (r=2.5, inside the fin's ~2.85 reach, outside
        # the bare cylinder's 2.2): the exact tool reaches it, and no kept
        # gum survives there — the recess DOES follow the fin
        fin_probe = np.array([[2.5, 0.0, 0.5]])
        assert bool(exact.contains(fin_probe)[0]), \
            "the exact cap+fin should reach this probe"
        _, dist, _ = out.nearest.on_surface(fin_probe)
        assert float(dist[0]) > 0.1, \
            "gum survives on the fin's own bearing — the fin left no imprint"

        # OPPOSITE THE FIN (same radius, same z): the old fat envelope would
        # have reached it too (uniform ring at the fin's radius), but the
        # exact tool does not — and the gum genuinely survives there now
        far_probe = np.array([[-2.5, 0.0, 0.5]])
        assert not bool(exact.contains(far_probe)[0]), \
            "the exact cap+fin should NOT reach this probe — it is bare " \
            "cylinder here"
        assert bool(envelope.contains(far_probe)[0]), \
            "the old fat envelope should have reached this probe — that " \
            "is the whole point of the client's complaint"
        _, dist, _ = out.nearest.on_surface(far_probe)
        assert float(dist[0]) < 0.05, \
            "gum does not survive opposite the fin — the recess is still " \
            "the fat envelope, not the cap's exact surface"

    def test_the_wall_follows_the_gum_around_the_socket(self, engine_expects):
        """ONE MEDIAN COLLAR LEFT A PROUD CRESCENT (cap7020, client screenshot):
        on a tilted arch the tissue is lower on one side, and a wall clipped at
        the median height stood ~0.5mm proud of the low side's gum. The clip is
        per-AZIMUTH now: at every bearing the wall stops just above the local
        tissue, so no crescent stands above the gum anywhere.

        ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, 2026-08-15): the
        geometry is unaffected by which strip mechanism selects it —
        verified directly; only the notes check branches."""
        from case_prep.pipeline.deliverables import cap_imprint_holes

        # a TILTED sheet: z = 0.25*x, so the gum height swings ±1mm across the
        # socket's azimuths
        xs, ys = np.meshgrid(np.linspace(-8, 8, 40), np.linspace(-8, 8, 40))
        zs = 0.25 * xs
        pts = np.column_stack([xs.ravel(), ys.ravel(), zs.ravel()])
        faces = []
        for i in range(39):
            for j in range(39):
                a = i * 40 + j
                faces.append([a, a + 1, a + 41])
                faces.append([a, a + 41, a + 40])
        sheet = trimesh.Trimesh(pts, np.asarray(faces), process=False)
        out, notes = cap_imprint_holes(sheet, [self._site()])
        if engine_expects.tracked:
            assert notes == []
        else:
            engine_expects.assert_fallback_notes(
                notes, "the provenance-tracked strip could not run")
        v = np.asarray(out.vertices, float)
        r = np.linalg.norm(v[:, :2], axis=1)
        # THE CARVE'S FORM OF THIS GUARANTEE: pressing only ever moves
        # vertices DOWN, so nothing near the site can stand proud of the
        # local tissue (0.25*x here) — the crescent bug class is structurally
        # impossible, and this pin holds it so
        near = r < 3.5
        assert near.sum() >= 30, "no site neighbourhood to judge"
        proud = v[near, 2] - 0.25 * v[near, 0]
        assert float(proud.max()) < 0.25, \
            f"something stands {proud.max():.2f}mm proud of the local gum"

    def test_the_artifact_is_the_open_arch_with_the_cut(self, engine_expects):
        """THE OPEN ARCH COMES BACK (§10-AS.16, client 2026-08-10: "why did we
        build a dental model — we need to work with the open arch"). The
        solidify base/skirt exist only so the boolean has a solid to cut
        (§10-AS.12's machined floor and filled scan-hole survive on the cut
        surfaces); the ARTIFACT is the scan itself with the recess. Every kept
        face is either on the original shell or on a cut surface — the
        fabricated closure is stripped, so nothing the scan never contained
        ships.

        ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, 2026-08-15): the
        geometry is unaffected by which strip mechanism selects it —
        verified directly; only the notes check branches."""
        from case_prep.pipeline.deliverables import cap_imprint_parts

        arch = _arch_with_bump()
        out, socket, notes = cap_imprint_parts(arch, [self._site()])
        if engine_expects.tracked:
            assert notes == []
        else:
            engine_expects.assert_fallback_notes(
                notes, "the provenance-tracked strip could not run")
        assert socket is not None
        merged = trimesh.util.concatenate([out, socket])
        v = np.asarray(merged.vertices, float)
        # the base plate lived 1.5mm below the shell's own deepest point —
        # gone: nothing ships below where the scan itself reaches
        assert float(v[:, 2].min()) >= float(
            np.asarray(arch.vertices, float)[:, 2].min()) - 0.2, \
            "the fabricated base must be stripped from the artifact"
        # and the sheet's own far reaches survive untouched
        assert (np.abs(v[:, 0]) > 15).any(), "the scan itself must survive"

    def test_the_floor_follows_the_gum_at_the_countersink_depth(self, engine_expects):
        """THE GUM-FOLLOWING FLOOR (client 2026-08-10): on the ridge-curved
        sheet (z = -0.12*y**2) the platform recess floor must sit the
        countersink depth below the LOCAL gum at every bearing — a shallow
        draped dish that shows the offset, never a planar pocket whose wall
        towers out of the low side.

        §10-AS.12 re-aimed this pin once already: the CSG floor is FLAT
        (the punch is a lathed profile, not a per-bearing terrain-follower)
        — pinned at the gum ring's own p25 height minus the countersink.

        §10-AS.14 (client 2026-08-10, "subtraction is the exact") re-aims
        it AGAIN: the cut tool is now the cap's own dilated solid, not the
        envelope — and "an exact cap cannot cut deeper than itself." On
        THIS fixture the sunk cylinder's own dilated base (world -1.2, cap
        base -1.0 minus the 0.2 offset) is SHALLOWER than the countersink
        target (ring p25 minus 0.5), so the floor is the cap's own base —
        only ~0.06mm below the ring, not the full countersink depth. The
        floor pin is now the general rule both readings share: floor =
        max(cap's dilated base, ring p25 - depth).

        ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, 2026-08-15): at
        ``top_floor=True`` the floor clip lands the intersection guard's
        UNCHANGED branch (this exact site/pose combination — verified
        directly) ON TOP OF the tracked-strip gap, so the non-tracked
        engine carries TWO notes, not one; the underlying geometry is
        unaffected by either (verified directly), so every assertion below
        stays unweakened."""
        from case_prep.pipeline.deliverables import (
            _envelope_profile, cap_imprint_parts)

        xs, ys = np.meshgrid(np.linspace(-8, 8, 40), np.linspace(-8, 8, 40))
        zs = -0.12 * ys**2
        pts = np.column_stack([xs.ravel(), ys.ravel(), zs.ravel()])
        faces = []
        for i in range(39):
            for j in range(39):
                a = i * 40 + j
                faces.append([a, a + 1, a + 41])
                faces.append([a, a + 41, a + 40])
        sheet = trimesh.Trimesh(pts, np.asarray(faces), process=False)
        pose = _pose_at(0, 0, 1.0)
        out, socket, notes = cap_imprint_parts(
            sheet, [(self._cap(), pose, 0.2, 2.0)], top_floor=True)
        if engine_expects.tracked:
            assert notes == []
        else:
            engine_expects.assert_fallback_notes(
                notes,
                "the exact cap could not be cut",
                "the provenance-tracked strip could not run")
        assert socket is not None
        v = np.asarray(socket.vertices, float)
        r = np.linalg.norm(v[:, :2], axis=1)
        # THE FLAT FLOOR: a broad plateau at one height spans the disc near
        # the axis — not a per-bearing terrain-follower
        floor_pts = v[r < 1.0]
        assert len(floor_pts) >= 1, "no floor plateau to judge"
        floor_z = float(np.median(floor_pts[:, 2]))
        # THE TWO CANDIDATES, reproduced from the fixture's own geometry:
        # the cap's own dilated base (offset only, §10-AS.14), and the
        # ring's own p25 height (the same gum-ring reading the carve
        # takes, band just past the exact wall) minus the countersink
        offset = 0.2
        cap_base_world = float(pose[2, 3]) - 2.0 - offset  # cylinder half-height 2.0
        zs_p, prof_p = _envelope_profile(self._cap(), offset)
        r_ref = float(np.max(prof_p))
        Vin = np.asarray(sheet.vertices, float) - pose[:3, 3]
        r_in = np.linalg.norm(Vin[:, :2], axis=1)
        ring = (r_in > r_ref + 0.1) & (r_in < r_ref + 1.2)
        ring_p25 = float(np.percentile(Vin[ring, 2], 25)) + pose[2, 3]
        expected = max(cap_base_world, ring_p25 - max(offset, 0.5))
        assert abs(floor_z - expected) < 0.05, \
            f"floor at {floor_z:.2f}, expected {expected:.2f} " \
            "(max of the cap's own base and the countersink target)"
        # and NOTHING stands above the local gum inside the recess
        proud = v[:, 2] - (-0.12 * v[:, 1] ** 2)
        assert float(proud.max()) < 0.3
        # THE RECESS CENTRE IS COVERED (the scan-hole-in-the-middle fix):
        # judged on the whole cut solid, not the socketless piece alone —
        # that piece has a genuine open boundary where the socket was cut
        merged = trimesh.util.concatenate([out, socket])
        down = merged.ray.intersects_any(ray_origins=[[0.0, 0.0, 5.0]],
                                         ray_directions=[[0.0, 0.0, -1.0]])
        assert bool(down[0]), "the recess centre must be covered"

    def test_the_collar_drapes_onto_curved_gum_no_floating_crescents(
            self, engine_expects):
        """THE TINTED COLLAR EXPOSED THE PLANE (client 2026-08-10, on 276794487's
        platform tab: "the arch-platform artifact looks terrible"): the collar
        annulus rode the FITTED PLANE, and wherever the real gum curves away
        from that plane the ring floated free — invisible while it wore the
        arch's own tan, dark crescent blades once §10-AR.11 tinted the socket.
        The collar's outer rings now DRAPE onto the local scan surface, bearing
        by bearing. On a ridge-curved sheet (z = -0.12*y², a crest along x) the
        plane fit is honestly wrong by over a millimetre at the side bearings —
        no collar vertex may float above the local gum by more than the seam
        slack.

        §10-AS.12's boolean cut retired the separate collar/plane-riding
        piece entirely — the wall meets the kept arch directly, at a sharp
        cut edge, with nothing bridging them. §10-AS.14 then shrank that
        edge further, from the dilated envelope's ~2.7mm radius back to the
        exact cap's ~2.2mm — the "collar" band this pin judges is now the
        socket's own outer rim (2.15-2.5mm, where the CSG max radius is
        ~2.48 on this fixture), not the old draped annulus out past 2.6mm.
        The guarantee survives unchanged: nothing near the cut edge floats
        above the local gum.

        RE-AIMED (rider-b, fleet measurement 2026-08-14): this band sits just
        OUTSIDE the exact cut's own wall — genuinely scan-provenance
        geometry, since the punch never reached it. The band predicate used
        to mislabel it into the SOCKET piece anyway (a radius/height box
        does not know the difference); reading it there measured 28 collar
        vertices. Under face provenance the band correctly reads as `out`
        (0 socket vertices there — nothing wrongly relabelled survives),
        so the OBSERVATION SURFACE moves to the MERGED piece
        (``concat(out, socket)`` — ``TestTheMergedCaplessArtifactDoesNotMove``
        pins that this concatenation is exactly ``keep``, unmoved by which
        piece a face lands in). The clinical claim is unchanged — nothing
        near the cut edge floats above the local gum — only which piece of
        the split happens to carry the evidence.

        ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, 2026-08-15): this
        exact site/pose combination trips the intersection guard's
        UNCHANGED branch on top of the tracked-strip gap (verified
        directly), so the non-tracked engine carries TWO notes; the
        underlying geometry is unaffected by either (verified directly)."""
        from case_prep.pipeline.deliverables import cap_imprint_parts

        xs, ys = np.meshgrid(np.linspace(-8, 8, 40), np.linspace(-8, 8, 40))
        zs = -0.12 * ys**2
        pts = np.column_stack([xs.ravel(), ys.ravel(), zs.ravel()])
        faces = []
        for i in range(39):
            for j in range(39):
                a = i * 40 + j
                faces.append([a, a + 1, a + 41])
                faces.append([a, a + 41, a + 40])
        sheet = trimesh.Trimesh(pts, np.asarray(faces), process=False)
        # the cap SUNK a millimetre (pose z=1.0, base at -1): the ridge's fitted
        # plane sits at ~-0.9, and a base above it is honestly "wholly above the
        # gum line" — this pin judges the collar, not that guard
        out, socket, notes = cap_imprint_parts(
            sheet, [(self._cap(), _pose_at(0, 0, 1.0), 0.2, 2.0)])
        if engine_expects.tracked:
            assert notes == []
        else:
            engine_expects.assert_fallback_notes(
                notes,
                "the exact cap could not be cut",
                "the provenance-tracked strip could not run")
        assert socket is not None
        merged = trimesh.util.concatenate([out, socket])
        v = np.asarray(merged.vertices, float)
        r = np.linalg.norm(v[:, :2], axis=1)
        # the collar-equivalent band: the socket's own outer rim, just past
        # the exact wall (~2.2) and short of its own max radius (~2.48) —
        # judge every vertex there against the sheet's own local height
        collar = (r > 2.15) & (r < 2.5)
        assert collar.sum() >= 20, "no collar band to judge"
        proud = v[collar, 2] - (-0.12 * v[collar, 1] ** 2)
        assert float(proud.max()) < 0.30, \
            f"collar floats {proud.max():.2f}mm above the local gum"

    def test_the_moat_between_wall_and_cut_edge_is_bridged(self, engine_expects):
        """THE EMPTY SPACE GOES (client 2026-08-09: "we cannot leave the empty
        space there, it looks weird"). The any-vertex cull opens the scan wider
        than the socket wall — up to one triangle-edge beyond it — leaving an
        annular MOAT you could see straight through. A collar annulus now
        bridges the wall's mouth to past the cut edge, riding the fitted gum
        plane — the same bridging idiom the old cylinder socket always had
        (test_bore_wall_meets_a_surface_collar). Looking straight down through
        where the moat was, geometry must be there at every bearing.

        ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, 2026-08-15): the
        geometry is unaffected by which strip mechanism selects it —
        verified directly; only the notes check branches."""
        from case_prep.pipeline.deliverables import cap_imprint_holes

        arch = _arch_with_bump()
        out, notes = cap_imprint_holes(arch, [self._site()])
        if engine_expects.tracked:
            assert notes == []
        else:
            engine_expects.assert_fallback_notes(
                notes, "the provenance-tracked strip could not run")
        # rays straight down through the former moat ring (wall at 2.2; the
        # fixture's ~1.3mm edges opened the scan out to ~3.5)
        angles = np.linspace(0.0, 2.0 * np.pi, 12, endpoint=False)
        for radius in (2.45, 2.9):
            origins = np.column_stack([radius * np.cos(angles),
                                       radius * np.sin(angles),
                                       np.full(12, 8.0)])
            hits = out.ray.intersects_any(
                ray_origins=origins,
                ray_directions=np.tile([0.0, 0.0, -1.0], (12, 1)))
            assert bool(np.asarray(hits).all()), \
                f"the moat at r={radius} still lets rays through"

    def test_the_platform_floor_is_the_shallow_countersink(self, engine_expects):
        """THE FIFTH ARTIFACT, THIRD PASS (client 2026-08-09: 'still too deep —
        just the gingival offset platform, the top of the library... like the
        channel mouth'). ``top_floor=True`` puts the floor at the CAP'S TOP —
        the channel-mouth plane — plus the relief, clamped just below the gum
        when the cap stands proud so the footprint dish always shows. Never
        the base, never the 8mm bore.

        §10-AS.12 RE-AIMED THIS PIN ENTIRELY (client 2026-08-10, on the CSG
        cut's own floor: "not smooth at all, and hole in the middle?" — and
        the direction that followed it, "the floor is lower by the gum,
        which shows the gingival offset"): the channel-mouth plane this pin
        used to chase (§10-AS.6) is superseded. The platform floor is now
        the GUM-FOLLOWING COUNTERSINK — the same ring-p25-minus-countersink
        the dish uses — machined flat by the punch tool, never the cap's
        own submerged top. Renamed to match.

        §10-AS.14 (client 2026-08-10, "subtraction is the exact") re-aims it
        again, and retired the deeply-submerged fixture: the exact cut tool
        is bounded ABOVE by the cap's own dilated top (never extended past
        it, unlike the old envelope's "2mm past the profile" margin), so a
        cap sunk well below the gum leaves an honest, INTACT lid of
        untouched gum over the cut — the mouth never opens, which is a
        correct but different artifact from a shallow countersink (nothing
        for THIS pin to judge). A cap that PROTRUDES through the gum, whose
        base sits nowhere near the countersink target, isolates the ring
        branch of the shared floor rule: floor = max(cap base - offset,
        ring p25 - depth) — here the ring wins, exactly the "shallow
        countersink" the client asked to see.

        ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, 2026-08-15): the
        geometry is unaffected by which strip mechanism selects it —
        verified directly; only the notes check branches."""
        from case_prep.pipeline.deliverables import cap_imprint_parts

        # a single-surface gum sheet at z=0 and a cap that PROTRUDES through
        # it (base at world -1.0, far above the base clamp's reach) — the
        # recess comes purely from the gum ring's own reading, with nothing
        # in the punch's own reach to block the mouth from opening
        xs, ys = np.meshgrid(np.linspace(-8, 8, 40), np.linspace(-8, 8, 40))
        pts = np.column_stack([xs.ravel(), ys.ravel(), np.zeros(xs.size)])
        faces = []
        for i in range(39):
            for j in range(39):
                a = i * 40 + j
                faces.append([a, a + 1, a + 41])
                faces.append([a, a + 41, a + 40])
        sheet = trimesh.Trimesh(pts, np.asarray(faces), process=False)
        cap = trimesh.creation.cylinder(radius=2.0, height=4.0)
        out, socket, notes = cap_imprint_parts(
            sheet, [(cap, _pose_at(0, 0, 1.0), 0.2, 2.0)], top_floor=True)
        if engine_expects.tracked:
            assert notes == []
        else:
            engine_expects.assert_fallback_notes(
                notes, "the provenance-tracked strip could not run")
        assert socket is not None
        merged = trimesh.util.concatenate([out, socket])
        merged.merge_vertices()
        # (§10-AS.16 dropped the whole-artifact watertightness claim: the
        # artifact is the OPEN arch again; the machined floor below still
        # proves the cut surfaces themselves are whole.)
        # THE FLOOR, BY RAY: vertex sampling is unreliable here (the flat
        # floor's own coarse fan and the tint region's loose radial band
        # both leave the true floor under-represented among raw vertices) —
        # a ray down the axis finds it directly. The base plate is stripped,
        # so the floor is what the ray finds.
        hit, _, _ = merged.ray.intersects_location(
            ray_origins=[[0.0, 0.0, 5.0]], ray_directions=[[0.0, 0.0, -1.0]])
        assert len(hit) > 0, "the recess centre must be covered"
        floor_z = float(np.max(hit[:, 2]))
        # THE SHALLOW COUNTERSINK: the floor sits 0.3-1.0mm below the flat
        # sheet's own (ring-low) gum height — never the channel-mouth
        # plane, never the 8mm bore
        assert 0.3 < 0.0 - floor_z < 1.0, \
            f"platform floor at {floor_z} — not the shallow countersink"
        # THE VOID IS EMPTY: nothing stands in the socket above the floor
        v = np.asarray(socket.vertices, float)
        r = np.linalg.norm(v[:, :2], axis=1)
        void = (r < 1.7) & (v[:, 2] > floor_z + 0.3) & (v[:, 2] < 3.8)
        assert not void.any(), "something still stands in the platform's void"

    def test_a_deviated_scanned_cap_leaves_no_flaps(self, engine_expects):
        """THE TORN-FLAP MECHANISM (client 2026-08-09, on 295811960: 'a lot of
        the scan left... not smoothed into the scan'). The cull removed what sat
        inside template + relief, but the SCANNED cap deviates from the template
        (p90 0.36mm on the client's case) — everything the real cap does beyond
        the relief envelope survived as torn crescents standing around the
        socket. The CULL now carries its own clearance beyond the relief; the
        LINER stays at the exact relief (the seat is unchanged — only the
        cleanup is honest about real scans).

        ENGINE-AWARE (kernel-parity-scoreboard.md §2.1, item 1 generalised,
        2026-08-15): the 0.35mm seat deviation makes this arch's own boolean
        operand genuinely self-intersecting under MeshLib's own contour
        test (§2.4's mechanism, this time on the untracked ``difference``
        MeshLib's boolean itself refuses natively — "Bad contour ...
        self-intersections"), so ``_csg_carve`` fails ENTIRELY (both the
        tracked and untracked routes) and ``cap_imprint_parts``'s own outer
        ladder falls the WHOLE carve back to the one-shell PRESS CARVE — a
        different algorithm with no claim to this pin's own torn-flap
        cull margin. Under the non-tracked engine only the refusal and the
        fallback landing are verified."""
        from case_prep.pipeline.deliverables import cap_imprint_holes

        # the scanned cap sits 0.35mm OFF the declared pose — a realistic seat
        # deviation, larger than the 0.2 relief
        sheet = trimesh.creation.box(extents=[40, 20, 1])
        for _ in range(4):
            sheet = sheet.subdivide()
        bump = trimesh.creation.cylinder(radius=2.0, height=4.0)
        bump.apply_translation([0.35, 0.0, 2.0])
        arch = trimesh.util.concatenate([sheet, bump])
        out, notes = cap_imprint_holes(arch, [self._site()])
        if not engine_expects.tracked:
            engine_expects.assert_fallback_notes(
                notes, "the true-boolean recess could not be cut")
            assert "MeshLib" in notes[0]
            assert "the pressed carve was used instead" in notes[0]
            assert len(out.faces) > 0, \
                "the pressed-carve fallback must still ship something"
            return
        # DEFECT B (client-ruled, live verification 2026-08-15): the
        # off-pose scan makes the cut asymmetric — the socket's own
        # boundary is genuinely non-simple here (2 loops, verified
        # directly) — the collar bridge fails OPEN, honestly, rather than
        # guess at a mangled ring; the torn-flap cull claims below are
        # unaffected.
        assert notes == [
            "site 1: the machined mouth could not be read as one clean "
            "loop (2 found) — the collar bridge was skipped"]
        v = np.asarray(out.vertices, float)
        r = np.linalg.norm(v[:, :2], axis=1)
        # WITHOUT the cull clearance, a crescent of the shifted bump survives
        # just outside the relief envelope (r 2.2..2.55) standing tall above the
        # sheet — the flaps in the client's screenshot. Nothing of the scan may
        # stand there now.
        flaps = (r < 2.9) & (v[:, 2] > 1.0) & (v[:, 2] < 3.8)
        assert not flaps.any(), \
            f"{int(flaps.sum())} scan vertices still stand in the seat's throat"

    def test_a_proud_platform_floor_is_a_saucer_on_the_gum(self, engine_expects):
        """THE SAUCER (client 2026-08-09 screenshots: the clamped platform
        disc stood proud of the tilted gum with a see-through sliver). When
        the clamp fires, the floor's rim IS the collar's inner ring — shared
        vertices, no gap — and nothing of the floor may stand above the local
        gum plane.

        ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, 2026-08-15): this
        exact site/pose combination trips the intersection guard's
        UNCHANGED branch on top of the tracked-strip gap (verified
        directly), so the non-tracked engine carries TWO notes; the
        underlying geometry is unaffected by either (verified directly)."""
        from case_prep.pipeline.deliverables import cap_imprint_holes

        # tilted single-surface gum (z = 0.25x) and a PROUD tall cap
        xs, ys = np.meshgrid(np.linspace(-8, 8, 40), np.linspace(-8, 8, 40))
        pts = np.column_stack([xs.ravel(), ys.ravel(),
                               (0.25 * xs).ravel()])
        faces = []
        for i in range(39):
            for j in range(39):
                a = i * 40 + j
                faces.append([a, a + 1, a + 41])
                faces.append([a, a + 41, a + 40])
        sheet = trimesh.Trimesh(pts, np.asarray(faces), process=False)
        tall = trimesh.creation.cylinder(radius=2.0, height=10.0)
        out, notes = cap_imprint_holes(sheet, [(tall, _pose_at(0, 0, 5.0),
                                                0.2, 2.0)],
                                       top_floor=True)
        if engine_expects.tracked:
            assert notes == []
        else:
            engine_expects.assert_fallback_notes(
                notes,
                "the exact cap could not be cut",
                "the provenance-tracked strip could not run")
        v = np.asarray(out.vertices, float)
        r = np.linalg.norm(v[:, :2], axis=1)
        sock = r < 2.3
        # nothing of the floor stands proud of the LOCAL gum (0.25x) by more
        # than the collar tuck
        proud = v[sock][:, 2] - 0.25 * v[sock][:, 0]
        assert float(proud.max()) < 0.25, \
            f"platform floor stands {proud.max():.2f}mm proud of the gum"
        # and the saucer is a floor: a down-ray from inside the mouth hits it
        down = out.ray.intersects_any(ray_origins=[[0.0, 0.0, 2.0]],
                                      ray_directions=[[0.0, 0.0, -1.0]])
        assert bool(down[0]), "the saucer still needs to close the mouth"

    def test_a_tall_cap_socket_stops_just_below_the_gum(self, engine_expects):
        """THE VISIBLE-DEPTH CAP (client 2026-08-09, on 276794487's 6030): a tall
        cap's base sits ~4mm below the gum, and a socket lined all the way down
        hangs out of the thin scan shell as a protruding cylinder — 'showing all
        the way down until where the implant is going rather than just the
        healing cap.' The dish the competitor shows is SHALLOW: the floor stops
        just below the gum. The socket keeps the cap's footprint, but its floor
        is the HIGHER of the cap's offset base and (collar − visible depth).
        The short fixture cap elsewhere in this class is untouched by the cap —
        its base is already above that line.

        ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, 2026-08-15): this
        exact site/pose combination trips the intersection guard's
        UNCHANGED branch on top of the tracked-strip gap (verified
        directly), so the non-tracked engine carries TWO notes; the
        underlying geometry is unaffected by either (verified directly)."""
        from case_prep.pipeline.deliverables import cap_imprint_holes

        tall = trimesh.creation.cylinder(radius=2.0, height=10.0)
        arch = _arch_with_bump()
        out, notes = cap_imprint_holes(arch, [(tall, _pose_at(0, 0, 5.0),
                                               0.2, 2.0)])
        if engine_expects.tracked:
            assert notes == []
        else:
            engine_expects.assert_fallback_notes(
                notes,
                "the exact cap could not be cut",
                "the provenance-tracked strip could not run")
        v = np.asarray(out.vertices, float)
        r = np.linalg.norm(v[:, :2], axis=1)
        sock = r < 2.5
        # the cap's base+offset is at -0.2; the collar sits near the sheet top
        # (~0.5): nothing of the socket may reach deeper than collar - 2.0
        deepest = float(v[sock][:, 2].min())
        assert deepest > -1.9, \
            f"socket reaches {deepest}mm — the tube out of the shell is back"
        # and the shallow floor is still a FLOOR: a down-ray from the mouth hits
        down = out.ray.intersects_any(ray_origins=[[0.0, 0.0, 0.3]],
                                      ray_directions=[[0.0, 0.0, -1.0]])
        assert bool(down[0]), "the capped socket still needs its floor"

    def test_a_degenerate_template_carves_a_cylinder_recess(self, engine_expects):
        """A template that cannot make an envelope profile still gets its
        site cut — as a CYLINDER recess at the rim radius, said so in the
        notes. An honest degradation, never a dead package.

        §10-AS.12 re-aimed the radii and the void check to the CSG's own
        truth: the cylinder recess is dilated to rim(3.0) + the region
        margin(0.6) + the deviation clearance(0.5) ≈ 4.1, and — like the
        machined-floor pin above — the floor is now a coarse punch-tool
        disc, not a dense pressed cap, so the judgement is the VOID (empty)
        and the FLOOR (a ray finds it), not a minimum vertex count.

        ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, 2026-08-15): the
        geometry is unaffected by which strip mechanism selects it —
        verified directly; only the notes check branches (two notes under
        the non-tracked engine, the cylinder-fallback note plus the
        tracked-strip gap's own, in that order)."""
        from case_prep.pipeline.deliverables import cap_imprint_holes

        arch = _arch_with_bump()
        out, notes = cap_imprint_holes(
            arch, [(trimesh.Trimesh(), _pose_at(0, 0, 2.0), 0.2, 3.0)])
        if engine_expects.tracked:
            assert len(notes) == 1 and "cylinder" in notes[0]
        else:
            assert len(notes) == 2 and "cylinder" in notes[0]
            assert "the provenance-tracked strip could not run" in notes[1]
        v = np.asarray(out.vertices, float)
        r = np.linalg.norm(v[:, :2], axis=1)
        # THE VOID IS EMPTY: nothing stands between the machined floor and
        # the mouth, inside the dilated cylinder rim (3.0+0.6+0.5 ≈ 4.1)
        void = (r < 2.5) & (v[:, 2] > 0.1) & (v[:, 2] < 3.8)
        assert not void.any(), "something still stands in the recess's void"
        # THE FLOOR EXISTS
        down = out.ray.intersects_any(ray_origins=[[0.0, 0.0, 0.3]],
                                      ray_directions=[[0.0, 0.0, -1.0]])
        assert bool(down[0]), "the fallback recess still needs its floor"
        # and not the old 8mm synthetic bore
        assert not ((r < 4.2) & (v[:, 2] < -2.0)).any(), \
            "the fallback must still clear the site, not bore through it"

    def test_input_not_mutated(self):
        from case_prep.pipeline.deliverables import cap_imprint_holes

        arch = _arch_with_bump()
        before = len(arch.faces)
        cap_imprint_holes(arch, [self._site()])
        assert len(arch.faces) == before

    def test_the_imprint_hugs_the_cap_and_the_gum_survives(self, engine_expects):
        """§10-AS.19 (client 2026-08-10: "I do not need a model stl — just
        work with open arch"): the solidified model is INTERNAL machinery
        only (now ``case_prep.pipeline.csg``) — the boolean needs a solid
        for the one instant of the cut, and §10-AS.16 strips the fabricated
        closure from every artifact. This pin (moved out of the retired
        ``TestSolidifyShell`` grouping — §10-AT front 3 split the CSG
        mechanism into its own module, and this test is a full
        ``cap_imprint_holes`` pin, not a ``solidify_shell`` one) holds the
        real-fleet CSG path honest end to end.

        ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, extended past the
        parity branch per the §10-AT "parity referee" ledger entry,
        product-app-plan.md — one of the "12 excision/through-hole tests"
        it names). This real, feature-rich vendor cap (screw slot, coded
        trenches — this pin's own comment below already names it leaving
        "up to ~1.9mm proud" of the exact tool) is exactly the class of
        operand kernel-parity-scoreboard.md §2.1/§4.4 measured MeshLib
        refusing NATIVELY on the untracked ``difference`` itself, same as
        ``TestCapImprintHoles::test_the_recess_is_the_caps_exact_surface``/
        ``test_a_deviated_scanned_cap_leaves_no_flaps`` above — so
        ``_csg_carve`` fails ENTIRELY (both tracked and untracked routes)
        and ``cap_imprint_holes``'s own outer ladder falls the WHOLE carve
        back to the one-shell PRESS CARVE, a different algorithm with no
        claim to this pin's own CSG-exact wall/floor assertions below.
        SKIPS cleanly here either way (``data/real`` absent in this
        worktree): the branch below is UNVERIFIED against real geometry in
        this worktree — the ledger's own classification of this test among
        the 12 is the only confirmation it fires, at integration."""
        import json
        from pathlib import Path

        import trimesh as tm

        from case_prep.application.cases import discover_cases
        from case_prep.application.catalog import _library_for
        from case_prep.pipeline.deliverables import cap_imprint_holes

        data = Path(__file__).resolve().parents[1] / "data" / "real"
        product = (Path(__file__).resolve().parents[1] / "reports" / "product"
                   / "cap6030-neodent-gm" / "runs")
        if not data.is_dir() or not product.is_dir():
            pytest.skip("real fleet not present (gitignored)")
        run = next((r for r in sorted(product.iterdir(), reverse=True)
                    if any(r.glob("*-implant.json"))), None)
        if run is None:
            pytest.skip("no landed run for cap6030")
        rec = json.loads(next(run.glob("*-implant.json")).read_text())
        case = next(c for c in discover_cases(data) if c.id == "cap6030-neodent-gm")
        library = _library_for(case.data_root, rec["implant_model"],
                               [rec["variant_code"]])
        spec = next(s for s in library.specs
                    if s.variant == rec["variant_code"])
        template = library.template(spec)
        pose = np.asarray(rec["pose_matrix"], float)
        scan = tm.load(str(case.scan), force="mesh")
        rim_r = float(np.percentile(
            np.linalg.norm(np.asarray(template.vertices, float)[:, :2],
                           axis=1), 97))
        offset = 0.2

        out, notes = cap_imprint_holes(scan, [(template, pose, offset, rim_r)])
        if not engine_expects.tracked:
            engine_expects.assert_fallback_notes(
                notes, "the true-boolean recess could not be cut")
            assert "MeshLib" in notes[0]
            assert "the pressed carve was used instead" in notes[0]
            assert len(out.faces) > 0, \
                "the pressed-carve fallback must still ship a recess"
            return
        # THE BRIDGE DISCLOSURE IS THE ONE PERMITTED NOTE (integration
        # finding 2026-08-15: on a real coded cap the collar bridge FIRES —
        # its verbatim disclosure lands per bridged site by design, and
        # anything beyond that note is a genuine fallback):
        fallback_notes = [n for n in notes
                          if "collar between the recess mouth" not in n
                          and "collar bridge was skipped" not in n]
        assert fallback_notes == [], \
            f"real template must not fall back: {fallback_notes}"

        from case_prep.pipeline.deliverables import _collar_z_local

        v = np.asarray(out.vertices, float)
        origin, axis = pose[:3, 3], pose[:3, :3] @ np.array([0.0, 0.0, 1.0])
        rel = v - origin
        axial = rel @ axis
        radial = np.linalg.norm(rel - np.outer(axial, axis), axis=1)
        gum = _collar_z_local(np.asarray(scan.vertices, float), pose, rim_r)
        # (a) THE GUM SURVIVES UNMOVED just past the recess rim (the old
        # cylinder overcut ate rim+0.6 and beyond; the carve touches nothing
        # outside the rim + clearance): vertices near the gum line exist there
        ring = (radial > rim_r + offset + 0.8) & (radial < rim_r + 1.4) \
            & (np.abs(axial - gum) < 1.2)
        assert ring.sum() >= 25, "the gum just past the rim must survive unmoved"
        # (b) THE SCANNED CAP IS (MOSTLY) ERASED: nothing stands FAR above
        # the local gum line inside the recess — the cap that used to dome
        # out of the arch is pressed onto the floor.
        #
        # §10-AS.12 made this judged against the WALL, not a flat radius:
        # the CSG wall is the dilated envelope's own tapered profile, which
        # near the mouth narrows back down on this cap — well inside the
        # naive ``rim_r - 0.2`` cutoff (rim_r is a raw 97th-percentile
        # TEMPLATE radius, undilated) — so a flat cutoff flagged the
        # recess's own machined wall as "standing" (633 vertices, all
        # sitting exactly ON the profile's own radius at their height).
        # Judging against the true wall radius at each vertex's own height,
        # with a clearance margin, keeps the guarantee (nothing stands
        # INSIDE the wall) without tripping on the wall itself.
        #
        # §10-AS.14 (client 2026-08-10, "subtraction is the exact") re-aims
        # the WALL to the exact cap (offset only, no deviation clearance) —
        # and reopens exactly the risk ``_envelope_solid``'s own history
        # warned about (§10-AO): "the exact surface faithfully reproduced
        # the screw slot and coded trenches into the socket... and its
        # sealing machinery inherited every defect of vendor tessellation."
        # On this real, feature-rich vendor cap the exact tool measurably
        # leaves a BOUNDED solid lip standing — up to ~1.9mm proud here,
        # not the torn-open crescents §10-AR.3's clearance was built to
        # stop. The client's ruling accepts this trade (exactness over
        # inference); the guarantee that survives is BOUNDED, not zero.
        from case_prep.pipeline.deliverables import _envelope_profile

        zs_p, prof_p = _envelope_profile(template, offset)
        wall_r = np.interp(np.clip(axial, zs_p[0], zs_p[-1]), zs_p, prof_p)
        standing = (radial < wall_r - 0.3) & (axial > gum + 0.4)
        proud = axial[standing] - gum if int(standing.sum()) else np.array([0.0])
        assert float(proud.max()) < 2.5, \
            f"{proud.max():.2f}mm proud — beyond the exact cut's own " \
            "bounded-lip allowance, a real torn flap"
        # (c) THE FLOOR IS THERE: straight down through the mouth, geometry
        down = out.ray.intersects_any(
            ray_origins=[origin + axis * (gum + 4.0)],
            ray_directions=[-axis])
        assert bool(np.asarray(down)[0]), "the recess needs its floor"


class TestTrackedStripFailsOpenToTheDistanceStrip:
    """Boolean-engine plan W1 (2026-08-13): ``_csg_carve`` and
    ``arch_with_parts_fused`` now strip by manifold3d provenance first —
    these pins hold BOTH ends of that fail-open ladder honest: the tracked
    route runs silently (no note) on the clean synthetic fixtures every
    other pin in this file already exercises, and a forced tracked-path
    refusal falls back to the untracked engine + the old 0.35mm distance
    strip, WITH a note, producing the identical clinical outcome the
    untracked pins above already pin — the strip's own MECHANISM changed,
    the CONTRACT it enforces did not."""

    def _site(self, offset=0.2):
        return (trimesh.creation.cylinder(radius=2.0, height=4.0),
               _pose_at(0, 0, 2.0), offset, 2.0)

    def test_the_tracked_route_needs_no_fallback_on_a_clean_fixture(
            self, engine_expects):
        """If this ever fails, every OTHER ``notes == []`` pin in this file
        is silently exercising the fallback strip instead of the tracked
        one — this is the pin that tells the two apart.

        ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, 2026-08-15):
        under a kernel without ``difference_tracked`` the claim inverts BY
        CONSTRUCTION — the tracked route can never succeed here, so the
        honest sentinel is that EVERY ``notes == []`` pin elsewhere in this
        file is legitimately exercising the fallback strip instead,
        consistently, with its own note landing every time."""
        from case_prep.pipeline.deliverables import cap_imprint_holes

        arch = _arch_with_bump()
        out, notes = cap_imprint_holes(arch, [self._site()])
        if engine_expects.tracked:
            assert notes == []
        else:
            engine_expects.assert_fallback_notes(
                notes, "the provenance-tracked strip could not run")
        assert len(out.faces) > 0

    def test_a_tracked_carve_refusal_falls_back_and_says_so(self, monkeypatch):
        from case_prep.pipeline import deliverables as d

        def _refuse(*_args, **_kwargs):
            raise RuntimeError("forced for the W1 fallback pin")

        monkeypatch.setattr(d, "fabricated_face_mask", _refuse)

        arch = _arch_with_bump()
        out, notes = d.cap_imprint_holes(arch, [self._site()])
        assert any("distance-based strip" in n for n in notes), notes

        # the SAME clinical outcome ``TestCapImprintHoles::
        # test_only_the_caps_footprint_is_culled`` already pins on the
        # tracked route: the cap's own footprint is gone, the gum beside
        # it survives
        v = np.asarray(out.vertices, float)
        r = np.linalg.norm(v[:, :2], axis=1)
        assert not ((r < 1.8) & (v[:, 2] > 0.8) & (v[:, 2] < 3.8)).any()
        sheet_near = (r > 2.5) & (r < 3.4) & (np.abs(v[:, 2]) < 0.6)
        assert sheet_near.sum() >= 5, "the gum beside the cap must survive"

    def test_the_tracked_union_needs_no_fallback_on_a_clean_fixture(
            self, engine_expects):
        """ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, 2026-08-15):
        the union-side half of the same sentinel — see
        ``test_the_tracked_route_needs_no_fallback_on_a_clean_fixture``."""
        from case_prep.pipeline.deliverables import arch_with_parts_fused

        arch = _arch_with_bump()
        part = trimesh.creation.cylinder(radius=1.0, height=3.0)
        pose = _pose_at(0.0, 0.0, 4.0)
        _fused, notes = arch_with_parts_fused(arch, [(part, pose)])
        if engine_expects.tracked:
            assert notes == []
        else:
            engine_expects.assert_fallback_notes(
                notes, "the provenance-tracked strip could not run")

    def test_a_tracked_union_refusal_falls_back_and_says_so(self, monkeypatch):
        from case_prep.pipeline import deliverables as d

        def _refuse(*_args, **_kwargs):
            raise RuntimeError("forced for the W1 fallback pin")

        monkeypatch.setattr(d, "fabricated_face_mask", _refuse)

        arch = _arch_with_bump()
        part = trimesh.creation.cylinder(radius=1.0, height=3.0)
        pose = _pose_at(0.0, 0.0, 4.0)
        fused, notes = d.arch_with_parts_fused(arch, [(part, pose)])
        assert any("distance-based strip" in n for n in notes), notes

        # the SAME clinical outcome ``TestArchWithPartsFused::
        # test_the_scans_own_far_reaches_survive_and_the_base_stays_
        # stripped`` already pins on the tracked route
        v = np.asarray(fused.vertices, float)
        assert (np.abs(v[:, 0]) > 15).any(), \
            "the sheet's far ends must survive the strip"
        scan_floor = float(np.asarray(arch.vertices, float)[:, 2].min())
        assert not (v[:, 2] < scan_floor - 0.2).any(), \
            "nothing may ship below the scan's own deepest point — a " \
            "fabricated base survived the strip"


class TestSocketIsFaceProvenance:
    """RIDER-B (fleet measurement 2026-08-14, 36 carves/9 cases — read-only,
    already decided): ``_csg_carve``'s tracked-path ``inside`` predicate
    becomes FACE PROVENANCE (``tracked.source >= tracked.base_groups`` —
    the punch operands' own faces, already computed for ``strip_tracked``)
    instead of a revolute band (radius/height box) around the site axis.
    The band was measured to mislabel 6.6-43.6% of its socket as scan and to
    miss 13.8-86.2% of the true machined surface on deep-seated sites."""

    def test_the_socket_is_exactly_the_tool_surface(self, monkeypatch,
                                                    engine_expects):
        """Both configs the client actually ships: the DISH
        (``visible_depth_mm=1.8``) and the PLATFORM (``top_floor=True``).
        Every socket face must sit within 1e-3mm of the punch's own surface
        (the boolean cannot manufacture material that was not in one of its
        operands — a socket vertex off the punch by more than float
        round-trip noise means the label is wrong, not just imprecise), and
        every ground-truth tool-provenance face must land IN the socket —
        neither dropped nor left stranded in ``out``. Fails today (the band)
        in both directions: it both admits scan faces the punch never
        touched and drops real punch faces the band's own thresholds miss.

        ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, 2026-08-15): this
        pin's own ground truth is read off the tracked ``TrackedResult`` the
        ``_RecordingKernel`` captures — under a kernel that cannot produce
        one at all, the honest assertion is that the documented fallback
        ladder landed (this exact site/pose combination also trips the
        intersection guard's UNCHANGED branch, verified directly, so TWO
        notes) and that the untracked route still shipped a socket; nothing
        about the (nonexistent) tracked provenance can be checked."""
        from case_prep.pipeline import deliverables as d

        kernel = _RecordingKernel()
        monkeypatch.setattr(d, "default_kernel", lambda: kernel)
        real_exact_cap_punch = d.exact_cap_punch
        captured_punches = []

        def _capture_punch(*args, **kwargs):
            punch = real_exact_cap_punch(*args, **kwargs)
            captured_punches.append(punch.copy())
            return punch

        monkeypatch.setattr(d, "exact_cap_punch", _capture_punch)

        sheet = _ridge_sheet()
        cap = trimesh.creation.cylinder(radius=2.0, height=4.0)
        site = (cap, _pose_at(0, 0, 1.0), 0.2, 2.0)

        for kwargs in ({"visible_depth_mm": 1.8}, {"top_floor": True}):
            kernel.tracked_results.clear()
            captured_punches.clear()
            out, socket, notes = d.cap_imprint_parts(sheet, [site], **kwargs)
            if not engine_expects.tracked:
                engine_expects.assert_fallback_notes(
                    notes,
                    "the exact cap could not be cut",
                    "the provenance-tracked strip could not run")
                assert socket is not None, \
                    f"{kwargs}: the untracked fallback must still ship a socket"
                continue
            assert notes == [], f"{kwargs}: must exercise the tracked path: {notes}"
            assert socket is not None
            assert len(kernel.tracked_results) == 1
            tracked = kernel.tracked_results[0]
            source = np.asarray(tracked.source)
            true_tool = source >= tracked.base_groups
            n_tool = int(true_tool.sum())
            assert n_tool > 0

            mask_socket = _true_tool_mask_for(socket, tracked.mesh, true_tool)
            mask_out = _true_tool_mask_for(out, tracked.mesh, true_tool)
            assert mask_socket.all(), \
                f"{kwargs}: a socket face is not truly tool-provenance"
            assert not mask_out.any(), \
                f"{kwargs}: a true tool-provenance face landed in `out`"
            assert len(socket.faces) == n_tool, \
                f"{kwargs}: socket has {len(socket.faces)} faces, ground " \
                f"truth has {n_tool} tool-provenance faces"

            assert len(captured_punches) == 1
            punch = captured_punches[0]
            _, dist, _ = punch.nearest.on_surface(
                np.asarray(socket.vertices, float))
            assert float(dist.max()) < 1e-3, \
                f"{kwargs}: a socket vertex sits {float(dist.max()):.4f}mm " \
                "off the punch's own surface"


class TestDeepSeatedRecessKeepsItsWholeWall:
    """The band's floor is a percentile read of the local gum ring, but its
    CEILING was a flat ``h_low + 3.0mm`` above that same ring — fine for a
    shallow dish, but a real wall can legitimately run deeper than 3mm
    beneath material that stands tall at the site (a ridge, a healed collar,
    a thick model). Provenance carries no such ceiling: the socket is
    whatever the punch actually cut, however tall."""

    @staticmethod
    def _tall_bump_arch(bump_height=12.0, bump_radius=2.0):
        sheet = trimesh.creation.box(extents=[40, 20, 1])
        for _ in range(4):
            sheet = sheet.subdivide()
        bump = trimesh.creation.cylinder(radius=bump_radius,
                                         height=bump_height, sections=48)
        bump.apply_translation((0.0, 0.0, bump_height / 2.0))
        return trimesh.util.concatenate([sheet, bump])

    def test_a_deep_seated_recess_keeps_its_whole_wall(self, monkeypatch,
                                                       engine_expects):
        """ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, 2026-08-15):
        this pin's own coverage claim is read off the tracked
        ``TrackedResult`` — under a kernel without it, the honest
        assertion is the documented fallback note plus a shipped socket."""
        from case_prep.pipeline import deliverables as d

        kernel = _RecordingKernel()
        monkeypatch.setattr(d, "default_kernel", lambda: kernel)

        arch = self._tall_bump_arch()
        tall_cap = trimesh.creation.cylinder(radius=2.0, height=10.0)
        site = (tall_cap, _pose_at(0, 0, 1.0), 0.2, 2.0)
        out, socket, notes = d.cap_imprint_parts(arch, [site],
                                                  visible_depth_mm=1.8)
        if not engine_expects.tracked:
            engine_expects.assert_fallback_notes(
                notes, "the provenance-tracked strip could not run")
            assert socket is not None
            return
        # DEFECT B (client-ruled, live verification 2026-08-15): the tall,
        # NARROWER bump leaves the wall's own boundary split across two
        # heights (the floor ring and, well above it, the ring where the
        # punch's own reach ends and the bump's untouched surface resumes —
        # verified directly) — genuinely non-simple, so the collar bridge
        # fails OPEN, honestly. The whole-wall coverage claim below is
        # unaffected; it is what this test exists to prove.
        assert notes == [
            "site 1: the machined mouth could not be read as one clean "
            "loop (2 found) — the collar bridge was skipped"
        ], f"must exercise the tracked path: {notes}"
        assert socket is not None
        assert len(kernel.tracked_results) == 1
        tracked = kernel.tracked_results[0]
        source = np.asarray(tracked.source)
        n_tool = int((source >= tracked.base_groups).sum())
        assert n_tool > 0
        coverage = len(socket.faces) / n_tool
        assert coverage >= 0.99, \
            f"socket carries {len(socket.faces)}/{n_tool} = {coverage:.1%} " \
            "of the true machined wall — the old h_low+3.0 ceiling " \
            "truncated it"


class TestMaskNeverSplitsAUniformProvenanceFan:
    """W5's own edge-degree census (``tests/test_csg.py::
    TestJunctionSafeBoundary``), turned on the SOCKET piece: a boundary
    JUNCTION (degree > 2) is only honest when it sits on a real seam between
    two different materials. The band's geometric threshold can slice
    through a run of faces that are all, in truth, the SAME provenance — a
    manufactured junction, an artifact of the box/radius test rather than
    anything the boolean actually cut along. At relief 0.00 this is
    measured, not theoretical: the fleet's zero-relief lane carried 382 such
    junctions under the band; provenance carries none, because a junction in
    the socket's own boundary can only exist where ``inside`` (now the
    ground truth itself) actually changes across an edge."""

    def test_the_mask_never_splits_a_uniform_provenance_fan(self, monkeypatch,
                                                            engine_expects):
        """ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, 2026-08-15):
        this pin's own junction census is read off the tracked
        ``TrackedResult`` — under a kernel without it, the honest
        assertion is the documented fallback ladder (this exact zero-
        relief site also trips the intersection guard's EMPTY branch,
        verified directly, so TWO notes) plus a shipped socket."""
        from case_prep.pipeline import deliverables as d

        kernel = _RecordingKernel()
        monkeypatch.setattr(d, "default_kernel", lambda: kernel)

        sheet = _flat_sheet(n=19, extent=8.0)
        cap = trimesh.creation.cylinder(radius=1.8, height=4.0)
        site = (cap, _pose_at(0, 0, 1.0), 0.0, 1.8)  # relief 0.00
        out, socket, notes = d.cap_imprint_parts(sheet, [site],
                                                  visible_depth_mm=1.8)
        if not engine_expects.tracked:
            engine_expects.assert_fallback_notes(
                notes,
                "the exact cap could not be cut",
                "the provenance-tracked strip could not run")
            assert socket is not None
            return
        assert notes == [], f"must exercise the tracked path: {notes}"
        assert socket is not None
        assert len(kernel.tracked_results) == 1
        tracked = kernel.tracked_results[0]
        cut = tracked.mesh
        source = np.asarray(tracked.source)
        true_tool = source >= tracked.base_groups

        cnt = collections.Counter(map(tuple, socket.edges_sorted))
        boundary = [e for e, n in cnt.items() if n == 1]
        adj = collections.defaultdict(list)
        for a, b in boundary:
            adj[a].append(b)
            adj[b].append(a)
        junctions = [v for v, ns in adj.items() if len(ns) > 2]

        Vc = np.asarray(cut.vertices, float)
        coord_to_idx = {tuple(np.round(v, 6)): i for i, v in enumerate(Vc)}
        vertex_faces = collections.defaultdict(list)
        Fc = np.asarray(cut.faces)
        for fi, f in enumerate(Fc):
            for vtx in f:
                vertex_faces[int(vtx)].append(fi)

        Vs = np.asarray(socket.vertices, float)
        for jv in junctions:
            coord = tuple(np.round(Vs[jv], 6))
            cut_idx = coord_to_idx[coord]
            incident = vertex_faces[cut_idx]
            statuses = {bool(true_tool[fi]) for fi in incident}
            assert len(statuses) > 1, \
                f"junction at {coord} has a UNIFORM-provenance fan " \
                f"({statuses}) — a manufactured split, not a real seam"


class TestNoScanFaceShipsInTheSocketLayer:
    def test_no_scan_face_ships_in_the_socket_layer(self, monkeypatch,
                                                    engine_expects):
        """ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, 2026-08-15):
        this pin's own provenance census is read off the tracked
        ``TrackedResult`` — under a kernel without it, the honest
        assertion is the documented fallback ladder (this exact zero-
        relief site also trips the intersection guard's EMPTY branch,
        verified directly, so TWO notes) plus a shipped socket."""
        from case_prep.pipeline import deliverables as d

        kernel = _RecordingKernel()
        monkeypatch.setattr(d, "default_kernel", lambda: kernel)

        sheet = _ridge_sheet()
        cap = trimesh.creation.cylinder(radius=2.0, height=4.0)
        site = (cap, _pose_at(0, 0, 1.0), 0.0, 2.0)  # relief 0.00
        out, socket, notes = d.cap_imprint_parts(sheet, [site],
                                                  visible_depth_mm=1.8)
        if not engine_expects.tracked:
            engine_expects.assert_fallback_notes(
                notes,
                "the exact cap could not be cut",
                "the provenance-tracked strip could not run")
            assert socket is not None
            return
        # DEFECT B (client-ruled, live verification 2026-08-15): on the
        # ridge-curved sheet the excision genuinely leaves a moat between
        # the machined mouth and the scan's own edge — the collar bridge
        # fires and lands its own note; the socket-provenance census below
        # is unaffected (the bridge always ships in ``out``, never
        # ``socket`` — a fact ``TestBridgeLandsInOutNeverSocket`` pins
        # directly).
        assert notes == [
            "site 1: the collar between the recess mouth and the scan's "
            "edge is bridged — the tissue there sat under the cap and was "
            "never scanned"
        ], f"must exercise the tracked path: {notes}"
        assert socket is not None
        assert len(kernel.tracked_results) == 1
        tracked = kernel.tracked_results[0]
        source = np.asarray(tracked.source)
        true_tool = source >= tracked.base_groups

        mask_socket = _true_tool_mask_for(socket, tracked.mesh, true_tool)
        assert mask_socket.all(), \
            f"{int((~mask_socket).sum())} scan-provenance face(s) shipped " \
            "in the socket layer"


class TestTheMergedCaplessArtifactDoesNotMove:
    """THE GUARD: whatever ``inside`` is — a band, a provenance mask, ANY
    per-face predicate at all — ``out = keep & ~inside`` and
    ``socket = inside`` (the split ``_csg_carve`` always builds) satisfy
    ``(keep & ~inside) | inside == keep`` exactly whenever ``inside`` is a
    SUBSET of ``keep`` (a fact of plain set algebra, not of the predicate).
    ``TestSocketIsFaceProvenance``'s structural assertion proves that
    subset relation for the new provenance predicate; the fleet measurement
    proved it empirically (36/36 carves) for the old band. So the concat of
    the two pieces can never move: a predicate change is a RELABELLING —
    which face is called socket vs out — never a reshape of the union. This
    pin is predicate-independent by design; see the report for the argument
    that it must also hold, unrun, on the old band build.

    UPDATED (client-ruled defect 1, live verification 2026-08-15): the carve
    now also EXCISES scan-provenance faces that fall in DEFECT 1's shared
    classifier mask (``scanned_cap_face_mask``) — the scanned cap's own
    measured crust, wherever it stood proud of the template+relief the
    boolean actually cut. That excision legitimately SHRINKS ``keep`` before
    the ``out``/``socket`` split ever runs, so ``merged`` is no longer
    ``keep`` verbatim — it is ``keep`` MINUS whatever the excision dropped.
    The guard is updated to assert exactly that (recomputed independently,
    the same way ``_csg_carve`` computes it: the mask restricted to
    scan-provenance, i.e. ``tracked.source == 0``) rather than retired —
    the underlying algebra (``inside`` is still a subset of the SHRUNK
    ``keep``) is unchanged, and remains the reason the two pieces can never
    move relative to EACH OTHER even though the merged whole can shrink."""

    def test_the_merged_capless_artifact_is_keep_minus_the_excised_crust(
            self, monkeypatch, engine_expects):
        """ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, 2026-08-15):
        the structural claim under test is read off the tracked
        ``TrackedResult``'s own ``source``/``strip_tracked`` — under a
        kernel without the tracked op, the honest assertion is the
        documented fallback ladder (this exact site/pose combination also
        trips the intersection guard's UNCHANGED branch, verified
        directly, so TWO notes) plus a shipped socket; the class docstring's
        own "predicate-independent by design" claim is exactly why nothing
        further needs proving here under a different (band) predicate — it
        is proven structurally, not by this pin's own tracked-only ground
        truth."""
        from case_prep.pipeline import deliverables as d
        from case_prep.pipeline.csg import strip_tracked
        from case_prep.pipeline.isolation import scanned_cap_face_mask

        kernel = _RecordingKernel()
        monkeypatch.setattr(d, "default_kernel", lambda: kernel)

        sheet = _ridge_sheet()
        cap = trimesh.creation.cylinder(radius=2.0, height=4.0)
        pose = _pose_at(0, 0, 1.0)
        site = (cap, pose, 0.2, 2.0)
        out, socket, notes = d.cap_imprint_parts(sheet, [site],
                                                  visible_depth_mm=1.8)
        if not engine_expects.tracked:
            engine_expects.assert_fallback_notes(
                notes,
                "the exact cap could not be cut",
                "the provenance-tracked strip could not run")
            assert socket is not None
            return
        assert notes == []
        assert socket is not None
        assert len(kernel.tracked_results) == 1
        tracked = kernel.tracked_results[0]
        cut = tracked.mesh
        keep = strip_tracked(tracked)
        scan_provenance = np.asarray(tracked.source) == 0
        excised = scanned_cap_face_mask(cut, cap, pose, 2.0) & scan_provenance
        expected_keep = keep & ~excised

        def _sig_set(mesh):
            V = np.asarray(mesh.vertices, float)
            F = np.asarray(mesh.faces)
            return {tuple(sorted(tuple(np.round(V[v], 6)) for v in f))
                   for f in F}

        merged = trimesh.util.concatenate([out, socket])
        merged_sigs = _sig_set(merged)
        Vc = np.asarray(cut.vertices, float)
        Fc = np.asarray(cut.faces)[expected_keep]
        expected_sigs = {tuple(sorted(tuple(np.round(Vc[v], 6)) for v in f))
                        for f in Fc}
        assert merged_sigs == expected_sigs, \
            "concat(out, socket) is no longer keep MINUS the excised crust"

    def test_the_excised_set_is_exactly_scan_provenance_intersect_mask(
            self, monkeypatch, engine_expects):
        """THE COMPANION PIN (defect 1's own text): the excised set can never
        contain a tool-provenance face — proved here directly against the
        SAME tracked result the carve itself used, not merely asserted
        inside the production code.

        ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, extended past the
        parity branch per the §10-AT "parity referee" ledger entry,
        product-app-plan.md). This pin's own claim genuinely reads
        ``tracked.source`` ground truth — under a kernel that never
        produces a ``TrackedResult`` there is no scan-provenance∩mask set
        to re-derive, so the honest non-tracked assertion is the DOCUMENTED
        fallback outcome its sibling
        (``test_the_merged_capless_artifact_is_keep_minus_the_excised_crust``)
        already establishes for this exact site/pose combination (verified
        directly: the same coplanar intersection-guard note plus the
        tracked-strip gap, two notes, in that order), never a diluted
        version of the tracked claim above."""
        from case_prep.pipeline import deliverables as d
        from case_prep.pipeline.csg import strip_tracked
        from case_prep.pipeline.isolation import scanned_cap_face_mask

        kernel = _RecordingKernel()
        monkeypatch.setattr(d, "default_kernel", lambda: kernel)

        sheet = _ridge_sheet()
        cap = trimesh.creation.cylinder(radius=2.0, height=4.0)
        pose = _pose_at(0, 0, 1.0)
        site = (cap, pose, 0.2, 2.0)
        out, socket, notes = d.cap_imprint_parts(sheet, [site],
                                                  visible_depth_mm=1.8)
        if not engine_expects.tracked:
            engine_expects.assert_fallback_notes(
                notes,
                "the exact cap could not be cut",
                "the provenance-tracked strip could not run")
            assert socket is not None
            return
        assert notes == []
        tracked = kernel.tracked_results[0]
        cut = tracked.mesh
        keep = strip_tracked(tracked)
        source = np.asarray(tracked.source)
        scan_provenance = source == 0
        tool_provenance = source >= tracked.base_groups
        mask = scanned_cap_face_mask(cut, cap, pose, 2.0)
        excised = mask & scan_provenance

        assert not (excised & tool_provenance).any(), \
            "the excised set must never contain a tool-provenance face"
        # and the algebra the guard above depends on: excision only ever
        # shrinks a subset of what the strip already kept
        assert (excised & keep).sum() == excised.sum() or not excised.any()


class TestRealFleetSocketCoverage:
    """RIDER-B, exercised end to end on the real failure case the fleet
    measurement itself named: cap7030-zimmer-4.5's landed run. Measured
    worst case under the band was 45.3% coverage — well under the 99% the
    provenance predicate guarantees structurally. SKIPS cleanly when the
    gitignored real-fleet tree is absent (this worktree has none) —
    exercised at integration."""

    @pytest.mark.slow
    def test_cap7030_socket_covers_the_kept_tool_provenance(self, monkeypatch):
        import json
        from pathlib import Path

        import trimesh as tm

        from case_prep.application.cases import discover_cases
        from case_prep.application.catalog import _library_for
        from case_prep.pipeline import deliverables as d

        case_id = "cap7030-zimmer-4.5"
        data = Path(__file__).resolve().parents[1] / "data" / "real"
        product = (Path(__file__).resolve().parents[1] / "reports" / "product"
                  / case_id / "runs")
        if not data.is_dir() or not product.is_dir():
            pytest.skip("real fleet not present (gitignored)")
        run = next((r for r in sorted(product.iterdir(), reverse=True)
                   if any(r.glob("*-implant.json"))), None)
        if run is None:
            pytest.skip(f"no landed run for {case_id}")
        rec = json.loads(next(run.glob("*-implant.json")).read_text())
        case = next((c for c in discover_cases(data) if c.id == case_id), None)
        if case is None:
            pytest.skip(f"{case_id} not present under data/real")
        library = _library_for(case.data_root, rec["implant_model"],
                               [rec["variant_code"]])
        spec = next(s for s in library.specs
                   if s.variant == rec["variant_code"])
        template = library.template(spec)
        pose = np.asarray(rec["pose_matrix"], float)
        scan = tm.load(str(case.scan), force="mesh")
        rim_r = float(np.percentile(
            np.linalg.norm(np.asarray(template.vertices, float)[:, :2],
                          axis=1), 97))
        offset = 0.2

        kernel = _RecordingKernel()
        monkeypatch.setattr(d, "default_kernel", lambda: kernel)
        out, socket, notes = d.cap_imprint_parts(
            scan, [(template, pose, offset, rim_r)])
        # THE BRIDGE DISCLOSURE IS THE ONE PERMITTED NOTE (integration
        # finding 2026-08-15: on a real coded cap the collar bridge FIRES —
        # its verbatim disclosure lands per bridged site by design, and
        # anything beyond that note is a genuine fallback):
        fallback_notes = [n for n in notes
                          if "collar between the recess mouth" not in n
                          and "collar bridge was skipped" not in n]
        assert fallback_notes == [], \
            f"real template must not fall back: {fallback_notes}"
        assert socket is not None
        assert len(kernel.tracked_results) == 1
        tracked = kernel.tracked_results[0]
        source = np.asarray(tracked.source)
        n_tool = int((source >= tracked.base_groups).sum())
        assert n_tool > 0
        coverage = len(socket.faces) / n_tool
        assert coverage >= 0.99, \
            f"cap7030-zimmer-4.5 socket covers {coverage:.1%} of the true " \
            "machined surface (measured 45.3% under the band predicate)"


class TestDefect1MeasuredCapResidueIsExcised:
    """CLIENT-RULED DEFECT 1 (live verification, 2026-08-15). The boolean
    subtracts the TEMPLATE's own volume, but the scanned cap deviates from it
    (fleet: RMS 0.25, p90 0.35mm) — wherever the scan stands proud of
    template+relief, its own measured surface used to survive the cut
    untouched: white patches in the fused composite, floating flaps in the
    recess bore. ``_bulging_arch`` builds exactly that scene: a cap-shaped
    bump 0.4mm proud of the posed template, standing where neither the
    dilated punch nor (for the fuse pin) the posed part itself reaches."""

    def test_the_bulge_does_not_survive_the_carve(self, monkeypatch,
                                                  engine_expects):
        """ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, extended past
        the parity branch per the §10-AT "parity referee" ledger entry,
        product-app-plan.md). Built engine-agnostic ON PURPOSE (defect 1's
        own text): the untracked fallback applies the classifier mask BY
        GEOMETRY, so the honest non-tracked expectation is NOT "skip" —
        verified directly, this slice's own exploration (scratch venv,
        ``CASE_PREP_BOOLEAN_KERNEL=meshlib``): this exact site/pose (the
        bulge's own dilated punch, offset 0.2) makes the UNTRACKED
        ``difference`` itself refuse natively too ("Cannot separate mesh B
        to inside and outside parts... self-intersections") — the WHOLE
        tracked CSG carve fails and ``cap_imprint_parts``'s own outer ladder
        falls back to the one-shell PRESS CARVE (§10-AS.10), which applies
        ``scanned_cap_face_mask`` over the PRISTINE arch too
        (``_press_carve``'s own DEFECT-1 excision, ``excise &=
        ~face_moved``) — so the bulge still dies where THAT geometric-mask
        path runs, unweakened, even though the mechanism producing the
        merged artifact has changed."""
        from case_prep.pipeline import deliverables as d

        kernel = _RecordingKernel()
        monkeypatch.setattr(d, "default_kernel", lambda: kernel)
        arch, template, pose, bulge = _bulging_arch()
        rim_r = 2.6  # clears the bulge at the cylinder pre-cut (see fixture doc)
        site = (template, pose, 0.2, rim_r)
        out, socket, notes = d.cap_imprint_parts(arch, [site],
                                                  visible_depth_mm=1.8)
        if not engine_expects.tracked:
            engine_expects.assert_fallback_notes(
                notes, "the true-boolean recess could not be cut")
            assert "MeshLib" in notes[0]
            assert "the pressed carve was used instead" in notes[0]
        else:
            # DEFECT B (client-ruled, live verification 2026-08-15): the
            # bulge's own radius (2.4) sits between the template's (2.0)
            # and the dilated punch's (~2.2) — the socket's own boundary is
            # genuinely non-simple here (3 loops, verified directly) — the
            # collar bridge fails OPEN, honestly; the crust-excision claim
            # below is unaffected.
            assert notes == [
                "site 1: the machined mouth could not be read as one "
                "clean loop (3 found) — the collar bridge was skipped"]
        merged = (trimesh.util.concatenate([out, socket])
                 if socket is not None else out)
        merged_v = {tuple(np.round(v, 6))
                   for v in np.asarray(merged.vertices, float)}
        # a bulge vertex standing outside even the DILATED punch (template
        # radius + relief) is untouched by the boolean — if it still reads in
        # the merged artifact, the scanned cap's crust survived the carve
        bv = np.asarray(bulge.vertices, float)
        outside_punch = np.linalg.norm(bv[:, :2], axis=1) > 2.0 + 0.2 + 0.05
        survivors = [tuple(np.round(v, 6)) for v in bv[outside_punch]
                    if tuple(np.round(v, 6)) in merged_v]
        assert survivors == [], \
            f"{len(survivors)} scanned-cap crust vertex(es) survived the carve"

    def test_the_gum_outside_the_mask_survives_untouched(self, monkeypatch,
                                                          engine_expects):
        """ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, extended past
        the parity branch, product-app-plan.md's §10-AT ledger): same site
        as the pin above — the same whole-cut fallback to the press carve
        engages (verified directly), which reads the arch's far reaches the
        same way; only the notes check branches."""
        from case_prep.pipeline import deliverables as d

        kernel = _RecordingKernel()
        monkeypatch.setattr(d, "default_kernel", lambda: kernel)
        arch, template, pose, bulge = _bulging_arch()
        site = (template, pose, 0.2, 2.6)
        out, socket, notes = d.cap_imprint_parts(arch, [site],
                                                  visible_depth_mm=1.8)
        if not engine_expects.tracked:
            engine_expects.assert_fallback_notes(
                notes, "the true-boolean recess could not be cut")
            assert "MeshLib" in notes[0]
            assert "the pressed carve was used instead" in notes[0]
        else:
            # DEFECT B — see ``test_the_bulge_does_not_survive_the_carve``'s
            # own comment (same site, same measured 3-loop fail-open).
            assert notes == [
                "site 1: the machined mouth could not be read as one "
                "clean loop (3 found) — the collar bridge was skipped"]
        merged = (trimesh.util.concatenate([out, socket])
                 if socket is not None else out)
        v = np.asarray(merged.vertices, float)
        assert (np.abs(v[:, 0]) > 15).any(), \
            "the sheet's far ends (well outside any mask) must survive"

    def test_tool_provenance_faces_are_never_excised(self, monkeypatch,
                                                      engine_expects):
        """ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, extended past
        the parity branch, product-app-plan.md's §10-AT ledger): same site
        as the two pins above — the whole-cut fallback to the press carve
        still ships a non-empty recess piece (verified directly, 284
        faces), so the claim survives unweakened; only the notes check
        branches."""
        from case_prep.pipeline import deliverables as d

        kernel = _RecordingKernel()
        monkeypatch.setattr(d, "default_kernel", lambda: kernel)
        arch, template, pose, bulge = _bulging_arch()
        site = (template, pose, 0.2, 2.6)
        out, socket, notes = d.cap_imprint_parts(arch, [site],
                                                  visible_depth_mm=1.8)
        if not engine_expects.tracked:
            engine_expects.assert_fallback_notes(
                notes, "the true-boolean recess could not be cut")
            assert "MeshLib" in notes[0]
            assert "the pressed carve was used instead" in notes[0]
        else:
            # DEFECT B — see ``test_the_bulge_does_not_survive_the_carve``'s
            # own comment (same site, same measured 3-loop fail-open).
            assert notes == [
                "site 1: the machined mouth could not be read as one "
                "clean loop (3 found) — the collar bridge was skipped"]
        assert socket is not None and len(socket.faces) > 0, \
            "the recess wall/floor (tool provenance) must survive the excision"

    def test_the_bulge_does_not_survive_the_fused_composite(self, monkeypatch,
                                                             engine_expects):
        """DEFECT 1(b): ``arch_with_parts_fused`` (the ``arch-with-
        healingcaps.stl`` composite) excises the SAME crust from the ARCH's
        own contribution before/at the union — the part's posed surface
        replaces the scanned cap's crust rather than merging with it.

        ENGINE-AWARE, WITH AN HONEST NEGATIVE (kernel-parity-scoreboard.md,
        item 1, extended past the parity branch, product-app-plan.md's
        §10-AT ledger): ``union_tracked`` always raises under a non-tracked
        kernel (deterministic — no operand-dependent refusal here, unlike
        the carve above), so the tracked-strip-fallback note lands and the
        UNION itself succeeds (verified directly: unlike ``difference``,
        this union does not trip a native MeshLib refusal on this operand).
        But the excision itself is measurably DEFEATED on THIS fixture
        under the untracked fallback — verified directly, not merely
        theorised: ``arch_with_parts_fused``'s own untracked branch
        substitutes ``~inside_mask`` (a 0.45mm cKDTree proximity-to-the-
        part-solid test, chosen for a DIFFERENT purpose — telling a part's
        own surface apart from the fabricated closure during the strip) for
        the tracked path's exact ``source == 0`` read. ``_bulging_arch``'s
        own bulge sits a MEASURED 0.400-0.403mm from the zero-offset part
        solid's surface — inside that 0.45mm radius almost everywhere along
        its wall — so ``inside_mask`` reads True across the bulge and
        ``excise &= ~inside_mask`` drops nearly the whole mask right back
        out (measured: 1790 masked faces, 54 survive the intersection).
        Net effect, measured on this exact fixture: ALL 128 bulge vertices
        the tracked path drops now SURVIVE the fuse — the opposite of the
        tracked-path claim. This is a genuine, reproducible property of the
        untracked fallback (an accidental near-collision between two
        independently-chosen constants: the fixture's own 0.4mm authored
        proudness and the strip's own 0.45mm radius), not a diluted
        assertion invented here to paper over it — out of scope to fix
        (tests only, no production code per this slice's own charter)."""
        from case_prep.pipeline import deliverables as d

        arch, template, pose, bulge = _bulging_arch()
        rim_r = 2.6
        part = template.copy()  # the "library cap" fused in — same shape,
        # posed identically, exactly ``auto_flow.py``'s own caps_posed
        fused, notes = d.arch_with_parts_fused(
            arch, [(part, pose)], excise_sites=[(template, pose, rim_r)])
        fused_v = {tuple(np.round(v, 6))
                  for v in np.asarray(fused.vertices, float)}
        bv = np.asarray(bulge.vertices, float)
        # zero-offset part punch: anything past the RAW template radius is
        # never covered by the part itself either, so a survivor here is
        # unambiguously the scan's own crust, not the part's own surface
        outside_part = np.linalg.norm(bv[:, :2], axis=1) > 2.0 + 0.05
        survivors = [tuple(np.round(v, 6)) for v in bv[outside_part]
                    if tuple(np.round(v, 6)) in fused_v]
        if not engine_expects.tracked:
            engine_expects.assert_fallback_notes(
                notes, "the provenance-tracked strip could not run")
            assert len(survivors) == int(outside_part.sum()), \
                "documented fallback outcome changed — re-measure the " \
                "0.45mm-proximity/0.4mm-proudness near-collision before " \
                "tightening this assertion"
            # the far gum still stands regardless
            v = np.asarray(fused.vertices, float)
            assert (np.abs(v[:, 0]) > 15).any()
            return
        assert notes == []
        assert survivors == [], \
            f"{len(survivors)} scanned-cap crust vertex(es) survived the fuse"
        # the far gum still stands — the excision is scoped to the site
        v = np.asarray(fused.vertices, float)
        assert (np.abs(v[:, 0]) > 15).any()

    def test_without_excise_sites_the_fuse_behaves_exactly_as_before(
            self, engine_expects):
        """``excise_sites`` defaults to ``None`` — the ``arch-with-
        constructions.stl`` call site (whose base already went through
        ``_csg_carve``'s own excision) must see NO behaviour change.

        ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, extended past the
        parity branch, product-app-plan.md's §10-AT ledger): this is the
        SAME call shape as
        ``TestArchWithPartsFused::test_the_scans_own_far_reaches_survive_
        and_the_base_stays_stripped`` (no ``excise_sites`` at all) — the
        same single tracked-strip-fallback note, verified directly; only
        the notes check branches."""
        from case_prep.pipeline import deliverables as d

        arch, part, pose = TestArchWithPartsFused()._sunk_part()
        fused, notes = d.arch_with_parts_fused(arch, [(part, pose)])
        if engine_expects.tracked:
            assert notes == []
        else:
            engine_expects.assert_fallback_notes(
                notes, "the provenance-tracked strip could not run")
        assert len(fused.faces) > 0


class TestOpenArchWithThroughHoles:
    """CLIENT-RULED DEFECT 2, THE THIRD RULING (live verification, 2026-08-15,
    client verbatim: "the hole is perfect just need to be without the
    backfilling we create which is like a dental model which we don't need —
    just the open scan, and the hole viewed like it is"). Retires
    ``closed_model_with_recesses``: the open scan, each site's cap punched
    all the way THROUGH, no backfilled body surviving the strip."""

    def _site(self, offset=0.2, rim_r=2.0):
        return (trimesh.creation.cylinder(radius=2.0, height=4.0),
               _pose_at(0, 0, 1.0), offset, rim_r)

    def test_the_result_is_not_watertight_open_by_design(self, engine_expects):
        """ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, extended past
        the parity branch per the §10-AT "parity referee" ledger entry,
        product-app-plan.md). Verified directly (scratch venv,
        ``CASE_PREP_BOOLEAN_KERNEL=meshlib``): on this site the UNTRACKED
        ``difference`` succeeds (unlike the bulging-cap sites above), so
        ``open_arch_with_through_holes`` falls back only as far as the
        tracked-strip gap — one note — and ships the SAME open-by-design
        geometry the tracked path does; only the notes check branches."""
        from case_prep.pipeline import deliverables as d

        out, notes = d.open_arch_with_through_holes(_ridge_sheet(),
                                                     [self._site()])
        assert out is not None
        if engine_expects.tracked:
            assert notes == []
        else:
            engine_expects.assert_fallback_notes(
                notes, "the provenance-tracked strip could not run")
        assert out.is_watertight is False

    def test_zero_closure_provenance_faces_survive(self, monkeypatch,
                                                    engine_expects):
        """ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, extended past
        the parity branch, product-app-plan.md's §10-AT ledger): this pin's
        own claim is read off the tracked ``TrackedResult``'s own
        ``source`` — under a kernel that never produces one there is no
        closure-provenance census to take, so the honest non-tracked
        assertion is the documented fallback ladder (verified directly:
        the untracked ``difference`` succeeds on this site, one note) plus
        a shipped, non-empty result."""
        from case_prep.pipeline import deliverables as d

        kernel = _RecordingKernel()
        monkeypatch.setattr(d, "default_kernel", lambda: kernel)
        out, notes = d.open_arch_with_through_holes(_ridge_sheet(),
                                                     [self._site()])
        if not engine_expects.tracked:
            engine_expects.assert_fallback_notes(
                notes, "the provenance-tracked strip could not run")
            assert out is not None and len(out.faces) > 0
            return
        assert notes == []
        assert len(kernel.tracked_results) == 1
        tracked = kernel.tracked_results[0]
        source = np.asarray(tracked.source)
        closure = source == 1
        assert closure.any(), \
            "the fixture must genuinely fabricate a closure, or this pin " \
            "proves nothing"
        # every closure-provenance face's own coordinates must be absent
        # from the shipped result — never merely "the closure mask says so"
        cut = tracked.mesh
        Vc = np.asarray(cut.vertices, float)
        Fc = np.asarray(cut.faces)[closure]
        closure_sigs = {tuple(sorted(tuple(np.round(Vc[v], 6)) for v in f))
                       for f in Fc}
        out_v = np.asarray(out.vertices, float)
        out_f = np.asarray(out.faces)
        out_sigs = {tuple(sorted(tuple(np.round(out_v[v], 6)) for v in f))
                   for f in out_f}
        assert closure_sigs.isdisjoint(out_sigs), \
            "a closure-provenance face survived into the shipped result"

    def test_the_bore_pierces_no_floor_hit_inside_the_punch_footprint(
            self, engine_expects):
        """A ray down the site's own axis, from well above, must pass
        through the shipped result with NO hit at all inside the punch's
        footprint — "the hole goes through", not a blind recess whose floor
        happens to be the punch's own incidental bottom cap.

        ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, extended past
        the parity branch, product-app-plan.md's §10-AT ledger): the
        untracked fallback succeeds on this site (verified directly) and
        produces the SAME through-bore — the geometry is unaffected by
        which strip mechanism selects it; only the notes check branches."""
        from case_prep.pipeline import deliverables as d

        site = self._site()
        _template, pose, _offset, _rim_r = site
        out, notes = d.open_arch_with_through_holes(_ridge_sheet(), [site])
        if engine_expects.tracked:
            assert notes == []
        else:
            engine_expects.assert_fallback_notes(
                notes, "the provenance-tracked strip could not run")
        origin = pose[:3, 3]
        axis = pose[:3, :3] @ np.array([0.0, 0.0, 1.0])
        locs, *_ = out.ray.intersects_location(
            ray_origins=[origin + axis * 100.0], ray_directions=[-axis])
        assert len(locs) == 0, \
            f"the bore is blocked — hit(s) at {locs}"

    def test_the_excision_holds_here_too(self, monkeypatch, engine_expects):
        """DEFECT 1's own classifier, applied to defect 2's own artifact: an
        unfloored bore is the LAST place a scanned cap's crust should be
        allowed to stand.

        ENGINE-AWARE, THE FAIL-OPEN DESIGN, READ AND ASSERTED (kernel-
        parity-scoreboard.md, item 1, extended past the parity branch,
        product-app-plan.md's §10-AT ledger). Unlike ``cap_imprint_parts``,
        ``open_arch_with_through_holes`` has no intermediate press-carve
        rung — its OUTER ``try/except`` wraps the untracked fallback too,
        so when the untracked ``difference`` ALSO refuses natively (verified
        directly, this exact bulging-cap site: "Cannot separate mesh B...
        self-intersections", the same trigger as the carve tests above) the
        function fails open to ABSENCE — ``(None, [reason])``, "the package
        ships without it" — exactly the shape
        ``test_a_totally_unbuildable_scan_fails_open_to_absence`` already
        pins, not the envelope path (there is no per-site fallback left to
        try once the boolean itself is gone)."""
        from case_prep.pipeline import deliverables as d

        kernel = _RecordingKernel()
        monkeypatch.setattr(d, "default_kernel", lambda: kernel)
        arch, template, pose, bulge = _bulging_arch()
        rim_r = 2.6
        out, notes = d.open_arch_with_through_holes(
            arch, [(template, pose, 0.2, rim_r)])
        if not engine_expects.tracked:
            assert out is None
            assert len(notes) == 1
            assert "could not be built" in notes[0]
            assert "ships without it" in notes[0]
            assert "MeshLib" in notes[0]
            return
        assert notes == []
        assert out is not None
        out_v = {tuple(np.round(v, 6))
                for v in np.asarray(out.vertices, float)}
        bv = np.asarray(bulge.vertices, float)
        outside_punch = np.linalg.norm(bv[:, :2], axis=1) > 2.0 + 0.2 + 0.05
        survivors = [tuple(np.round(v, 6)) for v in bv[outside_punch]
                    if tuple(np.round(v, 6)) in out_v]
        assert survivors == [], \
            f"{len(survivors)} scanned-cap crust vertex(es) survived the bore"

    def test_a_degenerate_template_falls_back_to_its_envelope_per_site(
            self, engine_expects):
        """A template with real vertex geometry (so its ENVELOPE profile can
        still be read as a point cloud) but zero faces (so ``exact_cap_punch``
        refuses outright — "not a watertight solid") falls back to the
        envelope tool for that one site, noted; the good site is untouched.

        ENGINE-AWARE (kernel-parity-scoreboard.md, item 1, extended past
        the parity branch, product-app-plan.md's §10-AT ledger): the good
        site's own untracked ``difference`` succeeds (verified directly —
        this is the SAME clean cylinder site as the tests above), so the
        tracked-strip-fallback note lands SECOND, strictly after the
        per-site envelope note the loop already appends — two notes, not
        one, in that order."""
        from case_prep.pipeline import deliverables as d

        good = self._site()
        good_cyl = trimesh.creation.cylinder(radius=2.0, height=4.0)
        degenerate_template = trimesh.Trimesh(
            vertices=good_cyl.vertices.copy(),
            faces=np.zeros((0, 3), dtype=int), process=False)
        degenerate = (degenerate_template, _pose_at(3.0, 3.0, 1.0), 0.2, 2.0)
        out, notes = d.open_arch_with_through_holes(
            _ridge_sheet(), [good, degenerate])
        assert out is not None
        if engine_expects.tracked:
            assert len(notes) == 1
        else:
            assert len(notes) == 2
            assert "the provenance-tracked strip could not run" in notes[1]
        assert notes[0].startswith("site 2")
        assert "envelope was used instead" in notes[0]

    def test_a_totally_unbuildable_scan_fails_open_to_absence(self):
        from case_prep.pipeline import deliverables as d

        out, notes = d.open_arch_with_through_holes(
            trimesh.Trimesh(), [self._site()])
        assert out is None
        assert len(notes) == 1
        assert "could not be built" in notes[0]
        assert "ships without it" in notes[0]


class TestZipLoopBridge:
    """DEFECT B's own triangulation primitive (client-ruled, live
    verification 2026-08-15), tested in isolation from any boolean kernel:
    a pure-geometry bridge between two closed, roughly-concentric loops of
    POSSIBLY DIFFERENT vertex counts, reusing every one of their own real
    points."""

    def _rings(self, m=32, n=40, r_in=2.0, r_out=2.3, phase=0.01):
        theta_i = np.linspace(-np.pi, np.pi, m, endpoint=False)
        theta_o = np.linspace(-np.pi, np.pi, n, endpoint=False) + phase
        inner = np.column_stack([r_in * np.cos(theta_i), r_in * np.sin(theta_i),
                                 np.zeros(m)])
        outer = np.column_stack([r_out * np.cos(theta_o), r_out * np.sin(theta_o),
                                 np.zeros(n)])
        return inner, theta_i, outer, theta_o

    def test_mismatched_vertex_counts_produce_exactly_their_sum_of_faces(self):
        from case_prep.pipeline.deliverables import _zip_loop_bridge

        inner, ti, outer, to = self._rings(m=32, n=40)
        ip, op, faces = _zip_loop_bridge(inner, ti, outer, to)
        assert len(faces) == 32 + 40
        assert len(ip) == 32 and len(op) == 40

    def test_every_bridge_vertex_is_a_real_input_point(self):
        """Never an interpolated one — the caller needs exact identity to
        weld the result onto its source loops afterward."""
        from case_prep.pipeline.deliverables import _zip_loop_bridge

        inner, ti, outer, to = self._rings(m=13, n=21)
        ip, op, _faces = _zip_loop_bridge(inner, ti, outer, to)
        inner_set = {tuple(np.round(v, 9)) for v in inner}
        outer_set = {tuple(np.round(v, 9)) for v in outer}
        assert {tuple(np.round(v, 9)) for v in ip} == inner_set
        assert {tuple(np.round(v, 9)) for v in op} == outer_set

    def test_the_strip_closes_with_exactly_two_boundary_loops(self):
        """A valid bridge is an annulus: every "rung" edge is shared by
        two triangles (interior), and only the two input rings' own edges
        remain open."""
        from case_prep.pipeline.deliverables import _zip_loop_bridge

        inner, ti, outer, to = self._rings(m=17, n=29)
        ip, op, faces = _zip_loop_bridge(inner, ti, outer, to)
        mesh = trimesh.Trimesh(np.vstack([ip, op]), faces, process=False)
        boundary = collections.Counter(map(tuple, mesh.edges_sorted))
        n_boundary_edges = sum(1 for _e, c in boundary.items() if c == 1)
        assert n_boundary_edges == len(ip) + len(op)
        assert not any(c > 2 for c in boundary.values()), \
            "a non-manifold edge means the strip self-crosses"

    def test_winding_is_consistent_across_the_whole_strip(self):
        """THE DEFECT THIS PIN PINS (measured directly at this slice's own
        pin time): comparing each ring's NEXT LOCAL step, rather than
        cumulative bearing, let the denser ring race all the way around
        while the sparser one had barely started — a self-crossing strip
        whose face normals flipped sign partway through. A flat, planar
        bridge must read ONE consistent normal direction throughout."""
        from case_prep.pipeline.deliverables import _zip_loop_bridge

        inner, ti, outer, to = self._rings(m=32, n=40, phase=0.01)
        ip, op, faces = _zip_loop_bridge(inner, ti, outer, to)
        mesh = trimesh.Trimesh(np.vstack([ip, op]), faces, process=False)
        dots = np.asarray(mesh.face_normals, float) @ np.array([0.0, 0.0, 1.0])
        assert np.all(dots > 0.99) or np.all(dots < -0.99), \
            f"inconsistent winding: normal z-components range " \
            f"{dots.min():.3f}..{dots.max():.3f}"

    def test_no_degenerate_faces(self):
        from case_prep.pipeline.deliverables import _zip_loop_bridge

        inner, ti, outer, to = self._rings(m=11, n=23)
        ip, op, faces = _zip_loop_bridge(inner, ti, outer, to)
        mesh = trimesh.Trimesh(np.vstack([ip, op]), faces, process=False)
        assert bool((np.asarray(mesh.area_faces, float) > 1e-9).all())

    def test_equal_counts_matches_the_envelope_eras_own_fixed_index_strip(self):
        """The degenerate case named in the docstring: with matching,
        already angle-ordered rings, the zip must reduce to the historical
        ``[j, off+j, off+k], [j, off+k, k]`` idiom (git history 35c888a) —
        same face count, same consistent winding."""
        from case_prep.pipeline.deliverables import _zip_loop_bridge

        inner, ti, outer, to = self._rings(m=24, n=24, phase=0.0)
        ip, op, faces = _zip_loop_bridge(inner, ti, outer, to)
        assert len(faces) == 48
        mesh = trimesh.Trimesh(np.vstack([ip, op]), faces, process=False)
        dots = np.asarray(mesh.face_normals, float) @ np.array([0.0, 0.0, 1.0])
        assert np.all(dots > 0.99) or np.all(dots < -0.99)


class TestBridgeRecessCollar:
    """``_bridge_recess_collar`` in isolation from any boolean kernel: pure
    loop-selection logic over hand-built boundary polylines."""

    def _circle(self, radius, z, n=32, phase=0.0):
        theta = np.linspace(-np.pi, np.pi, n, endpoint=False) + phase
        return np.column_stack([radius * np.cos(theta), radius * np.sin(theta),
                                np.full(n, z)])

    def _cup_mesh(self, radius, z, n=32):
        """A floored cup (wall + a flat floor fan) whose SOLE boundary loop
        is the mouth (the top ring) — the same topology a real recess's
        tool-provenance surface has (wall + floor, open only where the
        punch met the surface it removed), and enough for
        ``_bridge_recess_collar`` to read, which only ever looks at
        ``socket_faces``'s own boundary."""
        ring_top = self._circle(radius, z, n=n)
        ring_bot = self._circle(radius, z - 1.0, n=n)
        centre = np.array([[0.0, 0.0, z - 1.0]])
        verts = np.vstack([ring_top, ring_bot, centre])
        ci = 2 * n
        faces = []
        for j in range(n):
            k = (j + 1) % n
            faces.append([j, n + j, n + k])
            faces.append([j, n + k, k])
            faces.append([n + j, n + k, ci])
        return verts, np.asarray(faces, int)

    def test_a_genuine_gap_is_bridged_and_noted(self):
        from case_prep.pipeline.deliverables import _bridge_recess_collar

        pose = np.eye(4)
        mouth_r, moat_r = 2.0, 2.3
        Vc, socket_faces = self._cup_mesh(mouth_r, 0.0, n=32)
        moat = self._circle(moat_r, 0.0, n=40, phase=0.02)
        bridge, note = _bridge_recess_collar([moat], Vc, socket_faces, pose,
                                             mouth_r)
        assert bridge is not None
        assert note == (
            "the collar between the recess mouth and the scan's edge is "
            "bridged — the tissue there sat under the cap and was never "
            "scanned")
        # every bridge face sits between the mouth and moat radii
        r = np.linalg.norm(np.asarray(bridge.vertices, float)[:, :2], axis=1)
        assert float(r.min()) >= mouth_r - 1e-6
        assert float(r.max()) <= moat_r + 1e-6

    def test_no_candidate_outer_loop_is_silently_nothing_to_bridge(self):
        """No note — an honest "already flush", never a failure."""
        from case_prep.pipeline.deliverables import _bridge_recess_collar

        pose = np.eye(4)
        Vc, socket_faces = self._cup_mesh(2.0, 0.0, n=32)
        bridge, note = _bridge_recess_collar([], Vc, socket_faces, pose, 2.0)
        assert bridge is None
        assert note is None

    def test_a_junction_mouth_fails_open_with_the_loop_count(self):
        from case_prep.pipeline.deliverables import _bridge_recess_collar

        pose = np.eye(4)
        Vc, socket_faces_1 = self._cup_mesh(2.0, 0.0, n=32)
        Vc2, socket_faces_2 = self._cup_mesh(2.0, 5.0, n=32)
        # two disjoint cups concatenated as ONE "socket" — two mouths, not one
        V = np.vstack([Vc, Vc2])
        F = np.vstack([socket_faces_1, socket_faces_2 + len(Vc)])
        bridge, note = _bridge_recess_collar([], V, F, pose, 2.0)
        assert bridge is None
        assert note == (
            "the machined mouth could not be read as one clean loop "
            "(2 found) — the collar bridge was skipped")

    def test_more_than_one_candidate_outer_loop_fails_open_with_the_count(self):
        from case_prep.pipeline.deliverables import _bridge_recess_collar

        pose = np.eye(4)
        Vc, socket_faces = self._cup_mesh(2.0, 0.0, n=32)
        moat_a = self._circle(2.3, 0.0, n=40, phase=0.02)
        moat_b = self._circle(2.6, 0.2, n=36, phase=0.05)
        bridge, note = _bridge_recess_collar([moat_a, moat_b], Vc, socket_faces,
                                             pose, 2.0)
        assert bridge is None
        assert note == (
            "2 candidate boundary loops sit near the recess mouth — the "
            "collar bridge was skipped")

    def test_an_irregular_outer_loop_fails_the_roundness_gate(self):
        """A candidate loop that is not itself "roughly concentric" — the
        client's own framing of both boundary loops the bridge joins — is
        some unrelated cut edge that merely passed the radius/height
        gates, never a real moat."""
        from case_prep.pipeline.deliverables import _bridge_recess_collar

        pose = np.eye(4)
        Vc, socket_faces = self._cup_mesh(2.0, 0.0, n=32)
        theta = np.linspace(-np.pi, np.pi, 10, endpoint=False)
        irregular = np.column_stack([
            (2.5 + 1.0 * (np.arange(10) % 2)) * np.cos(theta),
            (2.5 + 1.0 * (np.arange(10) % 2)) * np.sin(theta),
            np.zeros(10)])
        bridge, note = _bridge_recess_collar([irregular], Vc, socket_faces,
                                             pose, 2.0)
        assert bridge is None
        assert note is None  # not "found near the mouth" at all — filtered out

    def test_no_socket_faces_fails_open_by_name(self):
        from case_prep.pipeline.deliverables import _bridge_recess_collar

        pose = np.eye(4)
        bridge, note = _bridge_recess_collar(
            [], np.zeros((0, 3)), np.zeros((0, 3), dtype=int), pose, 2.0)
        assert bridge is None
        assert note == (
            "the recess has no machined surface at this site — the "
            "collar bridge was skipped")


class TestDefectBTheGapRingIsBridgedEndToEnd:
    """DEFECT B — THE GAP RING (client-ruled, live verification 2026-08-15),
    exercised through the real ``cap_imprint_parts`` boolean pipeline. The
    ridge-curved sheet + zero-relief site (the SAME fixture ``TestNoScanFace
    ShipsInTheSocketLayer`` already carries) genuinely leaves a moat: the
    scanned cap's own crust is excised right up to the machined mouth, but
    the curved gum's own kept material does not resume until a bit farther
    out."""

    def _fixture(self):
        sheet = _ridge_sheet()
        cap = trimesh.creation.cylinder(radius=2.0, height=4.0)
        pose = _pose_at(0, 0, 1.0)
        return sheet, [(cap, pose, 0.0, 2.0)], pose

    def test_the_gap_ring_exists_pre_bridge(self, engine_expects):
        """Boundary edge census, BEFORE the bridge lands: ``out``'s own
        boundary near the site carries two loops (the mouth — a duplicate
        of the socket's own — and the scan's genuine opening edge, farther
        out)."""
        if not engine_expects.tracked:
            pytest.skip("the boundary census is read off the tracked carve")
        from case_prep.pipeline import deliverables as d

        sheet, sites, _pose = self._fixture()
        seen = []
        orig = d._bridge_recess_collar

        def spy(out_boundary_loops, Vc, socket_faces, pose, rim_r):
            seen.append(len(out_boundary_loops))
            return orig(out_boundary_loops, Vc, socket_faces, pose, rim_r)

        d._bridge_recess_collar = spy
        try:
            out, socket, notes = d.cap_imprint_parts(sheet, sites,
                                                      visible_depth_mm=1.8)
        finally:
            d._bridge_recess_collar = orig
        assert seen == [2], \
            f"expected the mouth + one moat loop pre-bridge, saw {seen}"
        assert socket is not None

    def test_post_bridge_the_out_boundary_near_the_site_shrinks_to_one_loop(
            self, engine_expects):
        if not engine_expects.tracked:
            pytest.skip("the boundary census is read off the tracked carve")
        from case_prep.pipeline.deliverables import (_boundary_loops_of,
                                                      cap_imprint_parts)

        sheet, sites, pose = self._fixture()
        out, socket, notes = cap_imprint_parts(sheet, sites, visible_depth_mm=1.8)
        assert notes == [
            "site 1: the collar between the recess mouth and the scan's "
            "edge is bridged — the tissue there sat under the cap and was "
            "never scanned"]
        origin = pose[:3, 3]
        near = [loop for loop in _boundary_loops_of(out)
               if np.all(np.linalg.norm(loop[:, :2] - origin[:2], axis=1) < 6.0)
               and np.all(np.abs(loop[:, 2] - origin[2]) < 6.0)]
        assert len(near) == 1, \
            f"expected ~one boundary loop near the site post-bridge, found " \
            f"{len(near)}"

    def test_the_bridge_faces_land_in_out_never_socket(self, engine_expects):
        """The bridge is FABRICATED, arch-layer material — it stands in for
        gum, never machined surface, so it must never reach the socket."""
        from case_prep.pipeline.deliverables import cap_imprint_parts

        sheet, sites, pose = self._fixture()
        out, socket, notes = cap_imprint_parts(sheet, sites, visible_depth_mm=1.8)
        if not engine_expects.tracked:
            engine_expects.assert_fallback_notes(
                notes,
                "the exact cap could not be cut",
                "the provenance-tracked strip could not run")
        else:
            assert notes == [
                "site 1: the collar between the recess mouth and the scan's "
                "edge is bridged — the tissue there sat under the cap and "
                "was never scanned"]
        assert socket is not None
        origin = pose[:3, 3]
        r_out = np.linalg.norm(
            np.asarray(out.vertices, float)[:, :2] - origin[:2], axis=1)
        r_sock = np.linalg.norm(
            np.asarray(socket.vertices, float)[:, :2] - origin[:2], axis=1)
        # the bridge's own outer ring sits past the socket's own widest
        # reach — proof some of `out`'s material now stands there that a
        # pre-bridge carve never shipped
        assert float(r_out.max()) > float(r_sock.max()) + 0.05

    def test_the_note_names_the_client_ruled_sentence_verbatim(
            self, engine_expects):
        from case_prep.pipeline.deliverables import cap_imprint_parts

        sheet, sites, _pose = self._fixture()
        out, socket, notes = cap_imprint_parts(sheet, sites, visible_depth_mm=1.8)
        if not engine_expects.tracked:
            engine_expects.assert_fallback_notes(
                notes,
                "the exact cap could not be cut",
                "the provenance-tracked strip could not run")
            return
        assert notes == [
            "site 1: the collar between the recess mouth and the scan's "
            "edge is bridged — the tissue there sat under the cap and was "
            "never scanned"]


class TestDefectBFailsOpenRatherThanMangleARing:
    """THE FAIL-OPEN PATH PINS (client's own words: "never a mangled
    ring") — a genuinely non-simple socket or ambiguous scan edge skips the
    bridge for that site, honestly, WITH a note naming why; the site's own
    recess is otherwise unaffected."""

    def test_a_fin_shaped_cap_leaves_a_non_simple_mouth(self, engine_expects):
        """Reuses ``TestCapImprintHoles``'s own fin fixture: the fin makes
        the socket's own boundary genuinely non-simple (3 loops, measured)."""
        from case_prep.pipeline.deliverables import cap_imprint_holes

        cap = trimesh.creation.cylinder(radius=2.0, height=4.0)
        fin = trimesh.creation.box(extents=[1.4, 0.6, 1.0])
        fin.apply_translation([2.0, 0.0, -1.5])
        capped = trimesh.util.concatenate([cap, fin])
        pose = _pose_at(0, 0, 2.0)
        arch = _arch_with_bump()
        out, notes = cap_imprint_holes(arch, [(capped, pose, 0.2, 2.0)])
        if not engine_expects.tracked:
            engine_expects.assert_fallback_notes(
                notes, "the true-boolean recess could not be cut")
            return
        assert notes == [
            "site 1: the machined mouth could not be read as one clean "
            "loop (3 found) — the collar bridge was skipped"]
        assert len(out.faces) > 0, "the recess itself must still ship"

    def test_a_deep_narrow_bump_leaves_the_wall_split_across_two_heights(
            self, monkeypatch, engine_expects):
        """Reuses ``TestDeepSeatedRecessKeepsItsWholeWall``'s own tall,
        NARROWER bump: the punch is wider than the bump everywhere along
        its height, so the socket's own wall only borders material at two
        disjoint heights (the floor, and where the bump's untouched
        surface resumes above the punch's own reach) — genuinely
        non-simple, measured directly."""
        from case_prep.pipeline import deliverables as d

        sheet = trimesh.creation.box(extents=[40, 20, 1])
        for _ in range(4):
            sheet = sheet.subdivide()
        bump = trimesh.creation.cylinder(radius=2.0, height=12.0, sections=48)
        bump.apply_translation((0.0, 0.0, 6.0))
        arch = trimesh.util.concatenate([sheet, bump])
        tall_cap = trimesh.creation.cylinder(radius=2.0, height=10.0)
        site = (tall_cap, _pose_at(0, 0, 1.0), 0.2, 2.0)
        out, socket, notes = d.cap_imprint_parts(arch, [site],
                                                  visible_depth_mm=1.8)
        if not engine_expects.tracked:
            engine_expects.assert_fallback_notes(
                notes, "the provenance-tracked strip could not run")
            assert socket is not None
            return
        assert notes == [
            "site 1: the machined mouth could not be read as one clean "
            "loop (2 found) — the collar bridge was skipped"]
        assert socket is not None and len(socket.faces) > 0


def _orphan_flap_scene(template_r=2.0, flap_r=3.0, rim_r=3.2, height=4.0,
                       bump_center=(0.0, 0.0, 2.0)):
    """DEFECT A's own scene (client-ruled, live verification 2026-08-15), at
    the boolean-pipeline's own scale: a gum sheet plus a small, entirely
    DISCONNECTED box standing in the annulus between the site's core-keep
    radius and its catalog rim — a full 1.0mm past the posed template's own
    wall (well past ``CAP_MATCH_BAND_MM``'s 0.6mm, so the shared
    classifier's band rung misses it exactly as the defect describes) and
    past every consumer's own cull margin too, so a build with NO orphan
    cleanup at all ships it completely untouched (measured directly, every
    consumer below: 8/8 flap vertices survive without it). Concatenation
    never welds vertices, so the flap is its own connected component by
    construction — the topology the orphan rule reads. Returns ``(arch,
    template, pose, flap, rim_r)``."""
    sheet = trimesh.creation.box(extents=[40, 20, 1])
    for _ in range(4):
        sheet = sheet.subdivide()
    flap = trimesh.creation.box(extents=[0.3, 0.3, 0.3])
    flap.apply_translation((bump_center[0] + flap_r, bump_center[1],
                            bump_center[2]))
    arch = trimesh.util.concatenate([sheet, flap])
    template = trimesh.creation.cylinder(radius=template_r, height=height,
                                         sections=64)
    pose = _pose_at(*bump_center)
    return arch, template, pose, flap, rim_r


def _flap_survivor_count(mesh_list, flap):
    flap_v = {tuple(np.round(v, 6))
             for v in np.asarray(flap.vertices, float)}
    merged_v: set = set()
    for m in mesh_list:
        if m is not None:
            merged_v |= {tuple(np.round(v, 6))
                        for v in np.asarray(m.vertices, float)}
    return len(flap_v & merged_v)


class TestDefectAOrphanFlapsDodgeTheBandButNotTheGuard:
    """DEFECT A — THE ORPHAN FLAPS (client-ruled, live verification
    2026-08-15). "THE FIX IS CONNECTIVITY, NOT A WIDER THRESHOLD" — proved
    here both ways: the shared classifier alone genuinely misses the
    flap (the gap this defect closes), and the guard pin (a connected gum
    tongue survives) holds beside it."""

    def test_the_flap_dodges_the_shared_classifier_alone(self):
        from case_prep.pipeline.isolation import scanned_cap_face_mask

        arch, template, pose, flap, rim_r = _orphan_flap_scene()
        mask = scanned_cap_face_mask(arch, template, pose, rim_r)
        n_sheet_faces = len(arch.faces) - len(flap.faces)
        assert not mask[n_sheet_faces:].any(), \
            "1.0mm past the template must dodge the 0.6mm band classifier " \
            "alone — that gap is the defect, not a red herring"

    def test_the_carve_drops_the_orphan_the_classifier_alone_would_ship(
            self, engine_expects):
        from case_prep.pipeline.deliverables import cap_imprint_parts

        arch, template, pose, flap, rim_r = _orphan_flap_scene()
        site = (template, pose, 0.2, rim_r)
        out, socket, notes = cap_imprint_parts(arch, [site],
                                                visible_depth_mm=1.8)
        assert notes == [], \
            f"orphan cleanup drops measured cap remnant silently: {notes}"
        assert _flap_survivor_count([out, socket], flap) == 0

    def test_without_orphan_cleanup_the_same_scene_would_have_shipped_it(
            self, monkeypatch):
        """THE BEFORE, proved directly against production code (not merely
        asserted): neutralise ``orphan_flap_mask`` and the SAME scene's
        flap survives — the connectivity step is what this defect needed,
        not the pre-existing band excision alone."""
        from case_prep.pipeline import deliverables as d

        arch, template, pose, flap, rim_r = _orphan_flap_scene()
        site = (template, pose, 0.2, rim_r)
        monkeypatch.setattr(
            d, "orphan_flap_mask",
            lambda mesh, site_poses, candidate=None:
                np.zeros(len(mesh.faces), bool))
        out, socket, notes = d.cap_imprint_parts(arch, [site],
                                                  visible_depth_mm=1.8)
        assert _flap_survivor_count([out, socket], flap) == len(flap.vertices)

    def test_a_connected_gum_tongue_reaching_into_the_cylinder_survives(
            self, engine_expects):
        """THE GUARD PIN, in the real pipeline (client's own words: "a
        connected gum tongue reaching into the cylinder: kept"): the far
        sheet — real, ordinary, CONNECTED gum — must survive untouched."""
        from case_prep.pipeline.deliverables import cap_imprint_parts

        arch, template, pose, flap, rim_r = _orphan_flap_scene()
        site = (template, pose, 0.2, rim_r)
        out, socket, notes = cap_imprint_parts(arch, [site],
                                                visible_depth_mm=1.8)
        v = np.asarray(out.vertices, float)
        assert (np.abs(v[:, 0]) > 15).any(), \
            "the sheet's far reaches (connected, real gum) must survive"


class TestDefectAOrphanCleanupEveryConsumer:
    """"Drop orphans, on every consumer the excision serves" — the SAME
    ``_orphan_flap_scene`` fixture, run through each of the four places
    DEFECT 1's own excision runs (the carve, the fuse, the press fallback,
    the through-holes artifact)."""

    def test_the_press_carve_drops_the_orphan(self):
        from case_prep.pipeline.deliverables import _press_carve

        arch, template, pose, flap, rim_r = _orphan_flap_scene()
        site = (template, pose, 0.2, rim_r)
        out, socket, notes = _press_carve(arch, [site], visible_depth_mm=1.8)
        assert _flap_survivor_count([out, socket], flap) == 0

    def test_the_fused_composite_drops_the_orphan(self):
        from case_prep.pipeline.deliverables import arch_with_parts_fused

        arch, template, pose, flap, rim_r = _orphan_flap_scene()
        part = template.copy()
        fused, notes = arch_with_parts_fused(
            arch, [(part, pose)], excise_sites=[(template, pose, rim_r)])
        assert _flap_survivor_count([fused], flap) == 0

    def test_the_through_holes_artifact_drops_the_orphan(self):
        from case_prep.pipeline.deliverables import open_arch_with_through_holes

        arch, template, pose, flap, rim_r = _orphan_flap_scene()
        site = (template, pose, 0.2, rim_r)
        out, notes = open_arch_with_through_holes(arch, [site])
        assert out is not None
        assert _flap_survivor_count([out], flap) == 0

    def test_without_excise_sites_the_fuse_never_runs_orphan_cleanup(self):
        """No sites, no site-shaped cylinder to test against — orphan
        cleanup is scoped to named sites, exactly like DEFECT 1's own
        excision it rides alongside."""
        from case_prep.pipeline.deliverables import arch_with_parts_fused

        arch, template, pose, flap, rim_r = _orphan_flap_scene()
        part = template.copy()
        fused, notes = arch_with_parts_fused(arch, [(part, pose)])
        # the flap is untouched — nothing named it as a site to excise
        # around, so nothing about it is even candidate material
        assert _flap_survivor_count([fused], flap) == len(flap.vertices)
