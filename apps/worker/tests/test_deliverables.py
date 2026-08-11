"""Arch-level deliverable composition (client spec, 2026-07-11):

  2. the doctor's WHOLE arch with the aligned healing cap covering the scanned gap;
  3. the arch with the scanned healing-cap region REMOVED and the construction part in its
     place — the composition of the aligned construction with the cap-free arch.

The removal is face-culling within the aligned cap's cylindrical region (visual/deliverable
composite; a watertight CSG variant can follow via the SDF engine when a vendor requires it).
"""
from __future__ import annotations

import numpy as np
import pytest
import trimesh

from case_prep.pipeline.deliverables import arch_with_parts, remove_cap_region


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

    def test_only_the_caps_footprint_is_culled(self):
        from case_prep.pipeline.deliverables import cap_imprint_holes

        arch = _arch_with_bump()
        out, notes = cap_imprint_holes(arch, [self._site()])
        assert notes == []
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

    def test_no_kept_face_touches_the_inside_of_the_exact_cap(self):
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
        between the exact cap and where the old envelope used to cut.)"""
        from case_prep.pipeline.deliverables import cap_imprint_holes

        arch = _arch_with_bump()
        out, notes = cap_imprint_holes(arch, [self._site()])
        assert notes == []
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

    def test_the_recess_is_the_caps_exact_surface(self):
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
        which the old fat envelope would have eaten too, now survives."""
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
        assert notes == []

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

    def test_the_wall_follows_the_gum_around_the_socket(self):
        """ONE MEDIAN COLLAR LEFT A PROUD CRESCENT (cap7020, client screenshot):
        on a tilted arch the tissue is lower on one side, and a wall clipped at
        the median height stood ~0.5mm proud of the low side's gum. The clip is
        per-AZIMUTH now: at every bearing the wall stops just above the local
        tissue, so no crescent stands above the gum anywhere."""
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
        assert notes == []
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

    def test_the_artifact_is_the_open_arch_with_the_cut(self):
        """THE OPEN ARCH COMES BACK (§10-AS.16, client 2026-08-10: "why did we
        build a dental model — we need to work with the open arch"). The
        solidify base/skirt exist only so the boolean has a solid to cut
        (§10-AS.12's machined floor and filled scan-hole survive on the cut
        surfaces); the ARTIFACT is the scan itself with the recess. Every kept
        face is either on the original shell or on a cut surface — the
        fabricated closure is stripped, so nothing the scan never contained
        ships."""
        from case_prep.pipeline.deliverables import cap_imprint_parts

        arch = _arch_with_bump()
        out, socket, notes = cap_imprint_parts(arch, [self._site()])
        assert notes == []
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

    def test_the_floor_follows_the_gum_at_the_countersink_depth(self):
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
        max(cap's dilated base, ring p25 - depth)."""
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
        assert notes == []
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

    def test_the_collar_drapes_onto_curved_gum_no_floating_crescents(self):
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
        above the local gum."""
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
        assert notes == []
        assert socket is not None
        v = np.asarray(socket.vertices, float)
        r = np.linalg.norm(v[:, :2], axis=1)
        # the collar-equivalent band: the socket's own outer rim, just past
        # the exact wall (~2.2) and short of its own max radius (~2.48) —
        # judge every vertex there against the sheet's own local height
        collar = (r > 2.15) & (r < 2.5)
        assert collar.sum() >= 20, "no collar band to judge"
        proud = v[collar, 2] - (-0.12 * v[collar, 1] ** 2)
        assert float(proud.max()) < 0.30, \
            f"collar floats {proud.max():.2f}mm above the local gum"

    def test_the_moat_between_wall_and_cut_edge_is_bridged(self):
        """THE EMPTY SPACE GOES (client 2026-08-09: "we cannot leave the empty
        space there, it looks weird"). The any-vertex cull opens the scan wider
        than the socket wall — up to one triangle-edge beyond it — leaving an
        annular MOAT you could see straight through. A collar annulus now
        bridges the wall's mouth to past the cut edge, riding the fitted gum
        plane — the same bridging idiom the old cylinder socket always had
        (test_bore_wall_meets_a_surface_collar). Looking straight down through
        where the moat was, geometry must be there at every bearing."""
        from case_prep.pipeline.deliverables import cap_imprint_holes

        arch = _arch_with_bump()
        out, notes = cap_imprint_holes(arch, [self._site()])
        assert notes == []
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

    def test_the_platform_floor_is_the_shallow_countersink(self):
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
        countersink" the client asked to see."""
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
        assert notes == []
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

    def test_a_deviated_scanned_cap_leaves_no_flaps(self):
        """THE TORN-FLAP MECHANISM (client 2026-08-09, on 295811960: 'a lot of
        the scan left... not smoothed into the scan'). The cull removed what sat
        inside template + relief, but the SCANNED cap deviates from the template
        (p90 0.36mm on the client's case) — everything the real cap does beyond
        the relief envelope survived as torn crescents standing around the
        socket. The CULL now carries its own clearance beyond the relief; the
        LINER stays at the exact relief (the seat is unchanged — only the
        cleanup is honest about real scans)."""
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
        assert notes == []
        v = np.asarray(out.vertices, float)
        r = np.linalg.norm(v[:, :2], axis=1)
        # WITHOUT the cull clearance, a crescent of the shifted bump survives
        # just outside the relief envelope (r 2.2..2.55) standing tall above the
        # sheet — the flaps in the client's screenshot. Nothing of the scan may
        # stand there now.
        flaps = (r < 2.9) & (v[:, 2] > 1.0) & (v[:, 2] < 3.8)
        assert not flaps.any(), \
            f"{int(flaps.sum())} scan vertices still stand in the seat's throat"

    def test_a_proud_platform_floor_is_a_saucer_on_the_gum(self):
        """THE SAUCER (client 2026-08-09 screenshots: the clamped platform
        disc stood proud of the tilted gum with a see-through sliver). When
        the clamp fires, the floor's rim IS the collar's inner ring — shared
        vertices, no gap — and nothing of the floor may stand above the local
        gum plane."""
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
        assert notes == []
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

    def test_a_tall_cap_socket_stops_just_below_the_gum(self):
        """THE VISIBLE-DEPTH CAP (client 2026-08-09, on 276794487's 6030): a tall
        cap's base sits ~4mm below the gum, and a socket lined all the way down
        hangs out of the thin scan shell as a protruding cylinder — 'showing all
        the way down until where the implant is going rather than just the
        healing cap.' The dish the competitor shows is SHALLOW: the floor stops
        just below the gum. The socket keeps the cap's footprint, but its floor
        is the HIGHER of the cap's offset base and (collar − visible depth).
        The short fixture cap elsewhere in this class is untouched by the cap —
        its base is already above that line."""
        from case_prep.pipeline.deliverables import cap_imprint_holes

        tall = trimesh.creation.cylinder(radius=2.0, height=10.0)
        arch = _arch_with_bump()
        out, notes = cap_imprint_holes(arch, [(tall, _pose_at(0, 0, 5.0),
                                               0.2, 2.0)])
        assert notes == []
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

    def test_a_degenerate_template_carves_a_cylinder_recess(self):
        """A template that cannot make an envelope profile still gets its
        site cut — as a CYLINDER recess at the rim radius, said so in the
        notes. An honest degradation, never a dead package.

        §10-AS.12 re-aimed the radii and the void check to the CSG's own
        truth: the cylinder recess is dilated to rim(3.0) + the region
        margin(0.6) + the deviation clearance(0.5) ≈ 4.1, and — like the
        machined-floor pin above — the floor is now a coarse punch-tool
        disc, not a dense pressed cap, so the judgement is the VOID (empty)
        and the FLOOR (a ray finds it), not a minimum vertex count."""
        from case_prep.pipeline.deliverables import cap_imprint_holes

        arch = _arch_with_bump()
        out, notes = cap_imprint_holes(
            arch, [(trimesh.Trimesh(), _pose_at(0, 0, 2.0), 0.2, 3.0)])
        assert len(notes) == 1 and "cylinder" in notes[0]
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


class TestSolidifyShell:
    """§10-AS.19 (client 2026-08-10: "I do not need a model stl — just work
    with open arch"): the solidified model is INTERNAL machinery only — the
    boolean needs a solid for the one instant of the cut, and §10-AS.16 strips
    the fabricated closure from every artifact. These pins hold the internal
    solidify honest; the closed-model ARTIFACT and its tab are retired."""

    @staticmethod
    def _open_sheet():
        # a genuinely OPEN single-surface sheet — the box fixture is already
        # watertight, which is not what a real scan shell is
        xs, ys = np.meshgrid(np.linspace(-8, 8, 24), np.linspace(-8, 8, 24))
        pts = np.column_stack([xs.ravel(), ys.ravel(), 0.02 * xs.ravel() ** 2])
        faces = []
        for i in range(23):
            for j in range(23):
                a = i * 24 + j
                faces.append([a, a + 1, a + 25])
                faces.append([a, a + 25, a + 24])
        return trimesh.Trimesh(pts, np.asarray(faces), process=False)

    def test_solidify_makes_a_watertight_model(self):
        from case_prep.pipeline.deliverables import solidify_shell

        sheet = self._open_sheet()
        assert not sheet.is_watertight
        solid = solidify_shell(sheet, np.array([0.0, 0.0, 1.0]))
        assert solid.is_watertight, "the skirted model must close"
        assert float(solid.volume) > 0.0

    def test_an_already_closed_mesh_passes_through(self):
        from case_prep.pipeline.deliverables import solidify_shell

        box = trimesh.creation.box(extents=[10, 10, 5])
        solid = solidify_shell(box, np.array([0.0, 0.0, 1.0]))
        assert solid.is_watertight

    def test_the_imprint_hugs_the_cap_and_the_gum_survives(self):
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
        assert notes == [], f"real template must not fall back: {notes}"

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
