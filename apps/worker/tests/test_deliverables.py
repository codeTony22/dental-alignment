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

    def test_the_liner_walls_are_the_offset_cap_below_the_gum_line(self):
        from case_prep.pipeline.deliverables import cap_imprint_holes

        arch = _arch_with_bump()
        out, _ = cap_imprint_holes(arch, [self._site()])
        v = np.asarray(out.vertices, float)
        r = np.linalg.norm(v[:, :2], axis=1)
        # imprint wall at the dilated radius, below the collar (sheet top ~0.5)
        wall = (np.abs(r - 2.2) < 0.15) & (v[:, 2] < 0.7) & (v[:, 2] > -0.5)
        assert wall.sum() >= 20, "no imprint wall at the offset surface"
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

    def test_liner_faces_the_void(self):
        from case_prep.pipeline.deliverables import cap_imprint_holes

        arch = _arch_with_bump()
        out, _ = cap_imprint_holes(arch, [self._site()])
        n = np.asarray(out.face_normals, float)
        c = np.asarray(out.triangles_center, float)
        r = np.linalg.norm(c[:, :2], axis=1)
        floor = (r < 1.6) & (np.abs(c[:, 2] + 0.2) < 0.15)
        assert floor.sum() >= 10, "no floor faces found"
        assert n[floor, 2].mean() > 0.9, "the floor must face UP into the seat"
        wall = (np.abs(r - 2.2) < 0.15) & (c[:, 2] < 0.4) & (c[:, 2] > -0.1)
        if wall.sum() >= 5:  # a shallow collar may leave few wall faces
            radial = c[wall, :2] / np.linalg.norm(c[wall, :2], axis=1,
                                                  keepdims=True)
            assert (n[wall, :2] * radial).sum(axis=1).mean() < -0.5, \
                "imprint walls must face inward"

    def test_no_kept_face_touches_the_inside_of_the_envelope(self):
        """THE FRINGE KILL (client 2026-08-09, screenshot): the centroid cull kept
        triangles that STRADDLE the socket wall — 6,272 of them on cap7020 — and
        their needle tips overhung the hole as a comb of spikes. The cull is now
        by ANY vertex: a kept face may not have a single vertex inside the
        dilated envelope. Re-derived here independently of the builder."""
        from case_prep.pipeline.deliverables import _envelope_solid, cap_imprint_holes

        arch = _arch_with_bump()
        out, notes = cap_imprint_holes(arch, [self._site()])
        assert notes == []
        posed = _envelope_solid(self._cap(), 0.2)
        posed.apply_transform(_pose_at(0, 0, 2.0))
        tri = np.asarray(out.triangles, float).reshape(-1, 3)
        # liner vertices sit ON the envelope surface — contains() may call surface
        # points either way, so probe a hair OUTSIDE the wall's own skin
        shrunk = posed.copy()
        shrunk.vertices -= np.asarray(shrunk.vertex_normals, float) * 0.02
        assert not shrunk.contains(tri).any(), \
            "a kept face still reaches inside the socket"

    def test_the_socket_is_the_envelope_not_the_exact_surface(self):
        """A cap with a protruding FIN (or, on real caps, a recessed slot): the
        socket must be the smooth per-height envelope, so the liner carries NO
        azimuthal detail — the fin widens the whole ring at its height instead of
        printing its own shape into the wall."""
        from case_prep.pipeline.deliverables import cap_imprint_holes

        # the fin sits LOW on the cap (world z 0..1) so its band overlaps the part
        # of the liner the gum-line clip keeps — a fin above the collar would test
        # nothing, since no liner survives up there from either implementation
        fin = trimesh.creation.box(extents=[1.4, 0.6, 1.0])
        fin.apply_translation([2.0, 0.0, -1.5])  # sticks out to r=2.7, z -2..-1
        capped = trimesh.util.concatenate([self._cap(), fin])
        arch = _arch_with_bump()
        out, notes = cap_imprint_holes(arch, [(capped, _pose_at(0, 0, 2.0),
                                               0.2, 2.0)])
        assert notes == []
        v = np.asarray(out.vertices, float)
        r = np.linalg.norm(v[:, :2], axis=1)
        # in the fin's band the envelope ring is fin-radius + offset (2.9) ALL the
        # way round: neither liner wall NOR surviving arch may sit at the bare
        # cylinder's wall (2.2) — the exact-surface liner would put both there
        band = (v[:, 2] > 0.05) & (v[:, 2] < 0.45) & (r > 0.3) & (r < 2.55)
        assert not band.any(), \
            "the liner carries azimuthal detail — that is the exact surface, " \
            "not the envelope"

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
        # judged ABOVE the floor ring only (floor at cap base - offset = -0.2):
        # the flat floor legitimately emerges from the downhill tissue on a
        # steep slope — the physical cap protruded there too. What must never
        # stand proud is the WALL above it, which is what the client's
        # screenshot showed as a crescent out of the gum.
        wall = (np.abs(r - 2.2) < 0.12) & (v[:, 2] > 0.0)
        assert wall.sum() >= 10, "no wall to judge"
        w = v[wall]
        # every wall vertex stays near the LOCAL tissue height at its own
        # bearing (0.25*x here) — the median-collar bug put the low side's
        # wall ~0.6mm proud; the fitted plane + face-top clip bounds it by
        # the 0.15 tuck plus across-face slope slop
        proud = w[:, 2] - 0.25 * w[:, 0]
        assert float(proud.max()) < 0.25, \
            f"wall stands {proud.max():.2f}mm proud of the local gum"

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
        slack."""
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
        # the collar band: outside the wall's mouth (~2.2), out to the cut edge
        # bridge (~4.3). Judge every vertex there against the sheet's own local
        # height — the old plane-riding ring floated ~1.1mm at the ±y bearings.
        collar = (r > 2.6) & (r < 4.4)
        assert collar.sum() >= 30, "no collar band to judge"
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

    def test_the_platform_floor_sits_at_the_channel_mouth_plane(self):
        """THE FIFTH ARTIFACT, THIRD PASS (client 2026-08-09: 'still too deep —
        just the gingival offset platform, the top of the library... like the
        channel mouth'). ``top_floor=True`` puts the floor at the CAP'S TOP —
        the channel-mouth plane — plus the relief, clamped just below the gum
        when the cap stands proud so the footprint dish always shows. Never
        the base, never the 8mm bore."""
        from case_prep.pipeline.deliverables import cap_imprint_holes

        # a single-surface gum sheet at z=0 (the box slab's two faces make the
        # fitted plane ambiguous) and a SUBMERGED tall cap: top at world -0.8,
        # base at -10.8. The floor must land at TOP + relief (-0.6) — not the
        # base (-11.0), not the 1.8mm dish (-1.85).
        xs, ys = np.meshgrid(np.linspace(-8, 8, 40), np.linspace(-8, 8, 40))
        pts = np.column_stack([xs.ravel(), ys.ravel(), np.zeros(xs.size)])
        faces = []
        for i in range(39):
            for j in range(39):
                a = i * 40 + j
                faces.append([a, a + 1, a + 41])
                faces.append([a, a + 41, a + 40])
        sheet = trimesh.Trimesh(pts, np.asarray(faces), process=False)
        tall = trimesh.creation.cylinder(radius=2.0, height=10.0)
        out, notes = cap_imprint_holes(sheet, [(tall, _pose_at(0, 0, -5.8),
                                                0.2, 2.0)],
                                       top_floor=True)
        assert notes == []
        v = np.asarray(out.vertices, float)
        r = np.linalg.norm(v[:, :2], axis=1)
        sock = (r < 2.5) & (v[:, 2] < 0.4)
        deepest = float(v[sock][:, 2].min())
        assert -0.75 < deepest < -0.45, \
            f"platform floor at {deepest} — not the channel-mouth plane + relief"
        down = out.ray.intersects_any(ray_origins=[[0.0, 0.0, 0.3]],
                                      ray_directions=[[0.0, 0.0, -1.0]])
        assert bool(down[0]), "the platform dish still needs its floor"

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

    def test_a_degenerate_template_falls_back_to_the_cylinder_socket(self):
        from case_prep.pipeline.deliverables import cap_imprint_holes

        arch = _arch_with_bump()
        out, notes = cap_imprint_holes(
            arch, [(trimesh.Trimesh(), _pose_at(0, 0, 2.0), 0.2, 3.0)])
        assert len(notes) == 1 and "cylinder" in notes[0]
        v = np.asarray(out.vertices, float)
        r = np.linalg.norm(v[:, :2], axis=1)
        wall = v[(np.abs(r - 3.6) < 0.2) & (v[:, 2] > -9.0)]
        assert len(wall) >= 40, "the fallback must be the old floored socket"

    def test_input_not_mutated(self):
        from case_prep.pipeline.deliverables import cap_imprint_holes

        arch = _arch_with_bump()
        before = len(arch.faces)
        cap_imprint_holes(arch, [self._site()])
        assert len(arch.faces) == before


@pytest.mark.slow  # a real scan + a real landed pose — the client-visible win, measured
class TestCapImprintOnARealCase:
    """The §10-AO acceptance on real data (cap6030's landed run): the imprint's
    walls hug the cap within the offset, and the gum the old cylinder used to eat
    (between the cap's true surface and rim+0.6) SURVIVES."""

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

        posed = template.copy()
        posed.apply_transform(pose)
        v = np.asarray(out.vertices, float)
        origin, axis = pose[:3, 3], pose[:3, :3] @ np.array([0.0, 0.0, 1.0])
        rel = v - origin
        axial = rel @ axis
        radial = np.linalg.norm(rel - np.outer(axial, axis), axis=1)
        # (a) THE GUM SURVIVES where the cylinder used to eat it: output vertices
        # exist between the cap's rim and the old cull cylinder (rim+0.6),
        # near the gum line
        ring = (radial > rim_r + offset + 0.15) & (radial < rim_r + 0.6) \
            & (np.abs(axial) < 2.0)
        assert ring.sum() >= 25, "the gum the cylinder used to eat must survive"
        # (b) the imprint's wall hugs the cap: output vertices whose distance to
        # the cap surface is ~the offset (within +0.3mm tolerance for mesh
        # resolution), inside the footprint band
        near_seat = v[(radial < rim_r + offset + 0.1) & (np.abs(axial) < 4.0)]
        if len(near_seat) > 400:
            near_seat = near_seat[:: len(near_seat) // 400]
        d = np.abs(tm.proximity.signed_distance(posed, near_seat))
        assert float(np.median(d)) <= offset + 0.3, \
            f"the seat must hug the cap: median {float(np.median(d)):.3f}mm"
