"""Unit pins for ``case_prep.pipeline.csg`` (§10-AT front 3, 2026-08-11): the
CSG mechanism split out of ``deliverables.py`` once that module carried both
the mechanism and the product's own policy numbers tangled together in one
~900-line file. These pins hold the MECHANISM honest in isolation — no
product-policy constant (visible depth, countersink minimum, cull margin)
is exercised here; ``deliverables.py``'s own tests keep pinning those
against ``cap_imprint_holes``/``cap_imprint_parts``.
"""
from __future__ import annotations

import numpy as np
import pytest
import trimesh
import trimesh.boolean


def _annulus_topped_cylinder(radius: float = 2.0, bore_radius: float = 0.6,
                             height: float = 4.0, seg: int = 32
                             ) -> trimesh.Trimesh:
    """A closed outer wall and a closed bottom disc, but the TOP is an
    ANNULUS — a ring with an open bore straight through its centre, never
    lidded. This is the real shape of most vendor healing-cap STLs: solid
    everywhere except the implant-interface bore, which the physical part
    is genuinely hollow at (``_lid_boundary_loops``'s own docstring). Has
    exactly one boundary loop — the bore's own inner rim."""
    ang = np.linspace(0.0, 2.0 * np.pi, seg, endpoint=False)
    ca, sa = np.cos(ang), np.sin(ang)
    bot = np.column_stack([radius * ca, radius * sa, np.zeros(seg)])
    top_outer = np.column_stack([radius * ca, radius * sa, np.full(seg, height)])
    top_inner = np.column_stack([bore_radius * ca, bore_radius * sa,
                                 np.full(seg, height)])
    centre = np.array([[0.0, 0.0, 0.0]])
    verts = np.vstack([bot, top_outer, top_inner, centre])
    n = seg
    ci = 3 * n
    faces = []
    for i in range(n):
        j = (i + 1) % n
        faces.append([i, j, n + j])              # outer wall
        faces.append([i, n + j, n + i])
        faces.append([n + i, 2 * n + i, 2 * n + j])  # top annulus (inner rim open)
        faces.append([n + i, 2 * n + j, n + j])
        faces.append([j, i, ci])                  # bottom disc fan
    return trimesh.Trimesh(verts, np.asarray(faces, int), process=False)


def _notched_prism() -> trimesh.Trimesh:
    """A block with a thin slot cut through it — narrower than twice the
    0.2mm relief offset the self-heal pin dilates by, so each wall of the
    slot gets pushed toward the other, PAST it, by a plain vertex-normal
    offset: the concave-crease self-intersection §10-AT front 3a's
    self-heal exists for (a screw slot, a coded cutout, on a real cap)."""
    block = trimesh.creation.box(extents=[4.0, 4.0, 4.0])
    notch = trimesh.creation.box(extents=[0.2, 4.4, 2.4])
    notch.apply_translation([0.0, 0.0, 1.0])
    return trimesh.boolean.difference([block, notch], engine="manifold")


class TestSolidifyShell:
    """§10-AS.19 (client 2026-08-10: "I do not need a model stl — just work
    with open arch"): the solidified model is INTERNAL machinery only — the
    boolean needs a solid for the one instant of the cut, and §10-AS.16
    strips the fabricated closure from every artifact. These pins hold the
    internal solidify honest; the closed-model ARTIFACT and its tab are
    retired. (Moved out of ``test_deliverables.py`` — §10-AT front 3 — the
    real-fleet ``cap_imprint_holes`` pin that used to share this class
    tests product policy, not this mechanism, and moved to
    ``test_deliverables.py::TestCapImprintHoles`` instead.)"""

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
        from case_prep.pipeline.csg import solidify_shell

        sheet = self._open_sheet()
        assert not sheet.is_watertight
        solid = solidify_shell(sheet, np.array([0.0, 0.0, 1.0]))
        assert solid.is_watertight, "the skirted model must close"
        assert float(solid.volume) > 0.0

    def test_an_already_closed_mesh_passes_through(self):
        from case_prep.pipeline.csg import solidify_shell

        box = trimesh.creation.box(extents=[10, 10, 5])
        solid = solidify_shell(box, np.array([0.0, 0.0, 1.0]))
        assert solid.is_watertight


class TestPunchSolid:
    def test_watertight(self):
        from case_prep.pipeline.csg import punch_solid

        zs = np.array([-2.0, -1.0, 0.0, 1.0, 2.0])
        prof = np.array([2.0, 2.2, 2.4, 2.2, 2.0])
        punch = punch_solid(zs, prof, floor_a=-1.5, pose=np.eye(4))
        assert punch.is_watertight
        assert float(punch.volume) > 0.0

    def test_apex_is_extended_2mm_past_the_profiles_end(self):
        # §10-AS.12's own reasoning: without the extension a sliver of dome
        # survives the cut as a floating crown
        from case_prep.pipeline.csg import punch_solid

        zs = np.array([0.0, 1.0, 2.0])
        prof = np.array([1.0, 1.5, 1.0])
        punch = punch_solid(zs, prof, floor_a=0.0, pose=np.eye(4))
        v = np.asarray(punch.vertices, float)
        assert float(v[:, 2].max()) >= 2.0 + 2.0 - 1e-6


class TestExactCapPunch:
    def test_watertight_on_a_closed_cylinder_cap(self):
        from case_prep.pipeline.csg import exact_cap_punch

        cap = trimesh.creation.cylinder(radius=2.0, height=4.0)
        punch = exact_cap_punch(cap, 0.2, np.eye(4))
        assert punch.is_watertight
        assert float(punch.volume) > float(cap.volume), \
            "the dilation must grow the cap, not shrink it"

    def test_watertight_on_a_cap_with_an_open_bore(self):
        """THE LID PIN: most vendor healing-cap STLs export the implant-
        interface bore OPEN (the physical part is genuinely hollow there).
        ``exact_cap_punch`` must fan-close that one honest loop
        (``_lid_boundary_loops``) before it can dilate and cut with it."""
        from case_prep.pipeline.csg import exact_cap_punch

        cap = _annulus_topped_cylinder()
        assert not cap.is_watertight, \
            "the fixture must start open, or this pin proves nothing"
        punch = exact_cap_punch(cap, 0.2, np.eye(4))
        assert punch.is_watertight

    def test_empty_template_refuses_rather_than_guesses(self):
        from case_prep.pipeline.csg import exact_cap_punch

        with pytest.raises(ValueError):
            exact_cap_punch(trimesh.Trimesh(), 0.2, np.eye(4))


class TestSelfHealingPunch:
    """§10-AT front 3a: vertex-normal dilation self-intersects at a concave
    crease (a screw slot, a coded cutout) — the two walls converge instead
    of opening a smooth notch. ``exact_cap_punch`` now unions the dilated
    punch with itself (manifold engine) to resolve that before returning."""

    def test_a_creased_dilation_still_yields_a_boolean_usable_punch(self):
        from case_prep.pipeline.csg import exact_cap_punch

        fixture = _notched_prism()
        assert fixture.is_watertight, "the fixture itself must be a solid"

        punch = exact_cap_punch(fixture, 0.2, np.eye(4))

        # the contract under test: whatever the dilation did to the
        # geometry, the RESULT must still be usable as a boolean operand —
        # a self-intersecting, un-healed punch is exactly what used to make
        # this raise and fall the site back to the envelope tool
        box = trimesh.creation.box(extents=[20.0, 20.0, 20.0])
        out = trimesh.boolean.difference([box, punch], engine="manifold")
        assert len(out.faces) > 0


class TestStripFabricated:
    """§10-AS.16's strip, extracted to its own reusable function: a face
    survives if it is already marked as a punch/cut-surface face, or if it
    sits close to the original scan's own surface; anything else — the
    fabricated base plate the solidify step built purely so the boolean had
    something to cut — is dropped."""

    def test_drops_a_fabricated_base_plate_but_keeps_surface_and_cut_faces(self):
        from case_prep.pipeline.csg import strip_fabricated

        # a flat sheet standing in for the original scanned arch
        arch = trimesh.creation.box(extents=[10, 10, 0.1])

        def _tri(x, y, z):
            return np.array([[x, y, z], [x + 0.2, y, z], [x, y + 0.2, z]])

        on_surface = _tri(0.0, 0.0, 0.05)     # sits ON the arch's own top face
        fabricated = _tri(-20.0, 0.0, -50.0)  # nowhere near the scan — a base plate
        cut_face = _tri(20.0, 0.0, -50.0)     # far away too, but a marked punch face

        verts = np.vstack([on_surface, fabricated, cut_face])
        faces = np.array([[0, 1, 2], [3, 4, 5], [6, 7, 8]])
        cut = trimesh.Trimesh(verts, faces, process=False)
        inside = np.array([False, False, True])

        keep = strip_fabricated(cut, arch, inside)

        assert list(keep) == [True, False, True]
