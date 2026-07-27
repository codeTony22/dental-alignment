"""Arch-level deliverable composition (client spec, 2026-07-11):

  2. the doctor's WHOLE arch with the aligned healing cap covering the scanned gap;
  3. the arch with the scanned healing-cap region REMOVED and the construction part in its
     place — the composition of the aligned construction with the cap-free arch.

The removal is face-culling within the aligned cap's cylindrical region (visual/deliverable
composite; a watertight CSG variant can follow via the SDF engine when a vendor requires it).
"""
from __future__ import annotations

import numpy as np
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
