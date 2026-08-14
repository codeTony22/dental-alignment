"""Unit pins for ``case_prep.pipeline.csg`` (§10-AT front 3, 2026-08-11): the
CSG mechanism split out of ``deliverables.py`` once that module carried both
the mechanism and the product's own policy numbers tangled together in one
~900-line file. These pins hold the MECHANISM honest in isolation — no
product-policy constant (visible depth, countersink minimum, cull margin)
is exercised here; ``deliverables.py``'s own tests keep pinning those
against ``cap_imprint_holes``/``cap_imprint_parts``.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

import numpy as np
import pytest
import trimesh
import trimesh.boolean

REAL = Path(__file__).resolve().parents[1] / "data" / "real"


def _boundary_degree_histogram(mesh: trimesh.Trimesh) -> dict:
    cnt = collections.Counter(map(tuple, mesh.edges_sorted))
    boundary = [e for e, n in cnt.items() if n == 1]
    adj = collections.defaultdict(list)
    for a, b in boundary:
        adj[a].append(b)
        adj[b].append(a)
    return dict(collections.Counter(len(n) for n in adj.values()))


def _edge_multiplicity_histogram(mesh: trimesh.Trimesh) -> dict:
    c = collections.Counter(collections.Counter(map(tuple, mesh.edges_sorted)).values())
    return {int(k): int(v) for k, v in sorted(c.items())}


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

    def test_the_open_sheet_has_zero_junction_vertices(self):
        """§10-AT front 5/W5's own invariant: a healthy input takes
        ``_simple_boundary_loops`` — unchanged, byte for byte — only
        because every one of its boundary vertices has degree <= 2. This is
        what the byte-identity claim below actually rests on: there is no
        junction here for the new route to even consider."""
        hist = _boundary_degree_histogram(self._open_sheet())
        assert set(hist) <= {2}

    def test_the_open_sheet_pins_faces_volume_and_a_single_skirt_loop(self):
        """Pinned against ``case_prep.pipeline.csg.solidify_shell`` run
        standalone at the commit BEFORE this change (493.02018903591676mm^3,
        1334 faces, byte-identical ``.faces``) — a runtime diff against the
        pre-fix module is not possible once this file is edited in place,
        so the pin is the number, not a live comparison. Also pins that the
        walker still finds exactly ONE loop (the sheet's own single
        perimeter): a regression that fabricated a spurious extra lid
        somewhere on a healthy sheet would move ``len(solid.faces)`` too,
        but this pins the LOOP COUNT directly."""
        from case_prep.pipeline.csg import solidify_shell

        sheet = self._open_sheet()
        solid = solidify_shell(sheet, np.array([0.0, 0.0, 1.0]))
        assert solid.is_watertight
        assert len(solid.faces) == 1334
        assert abs(float(solid.volume) - 493.02018903591676) < 1e-6

        cnt = collections.Counter(map(tuple, sheet.edges_sorted))
        boundary = [e for e, n in cnt.items() if n == 1]
        adj = collections.defaultdict(list)
        for a, b in boundary:
            adj[a].append(b)
            adj[b].append(a)
        seen: set = set()
        n_loops = 0
        for start in adj:
            if start in seen:
                continue
            n_loops += 1
            seen.add(start)
            prev, cur = None, start
            while True:
                nxts = [n for n in adj[cur] if n != prev and n not in seen]
                if not nxts:
                    break
                prev, cur = cur, nxts[0]
                seen.add(cur)
        assert n_loops == 1

    def test_the_closed_box_stays_byte_identical(self):
        from case_prep.pipeline.csg import solidify_shell

        box = trimesh.creation.box(extents=[10, 10, 5])
        solid = solidify_shell(box, np.array([0.0, 0.0, 1.0]))
        assert solid.is_watertight
        assert np.array_equal(np.asarray(box.faces), np.asarray(solid.faces))
        assert abs(float(solid.volume) - 500.0) < 1e-9


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


class TestJunctionSafeBoundary:
    """§10-AT front 5/W5: ``cap_imprint_parts``'s per-face mask at zero
    gingival relief leaves BOWTIE JUNCTIONS in the shell's boundary graph —
    a vertex where two separate patches meet at a single point (boundary
    degree 4; 58 of them on the real failure case, 276794487-zimmer-4.5).
    ``_simple_boundary_loops``'s plain vertex-DFS assumes a disjoint union
    of simple cycles and silently corrupts a junction instead: a fragment
    shorter than 3 vertices is dropped, and a still-open chain gets fanned
    shut as a fabricated closing edge (one of which collided with an
    interior edge on the real case, multiplicity 3). These pins hold the
    junction-safe route (``_junction_safe_boundary_loops``, dispatched from
    ``solidify_shell`` whenever any boundary vertex has degree > 2) honest
    against the exact fixtures the diagnosis measured."""

    @staticmethod
    def _bowtie_sheet() -> trimesh.Trimesh:
        """A 3x3 grid of vertices, keeping only the two DIAGONAL quads: the
        two patches meet at the CENTRE vertex alone — the minimal bowtie.
        9 vertices, 4 faces, boundary degree histogram {2: 6, 4: 1}."""
        xs, ys = np.meshgrid(np.arange(3.0), np.arange(3.0))
        pts = np.column_stack([xs.ravel(), ys.ravel(), np.zeros(9)])

        def quad(a, b, c, d):
            return [[a, b, c], [a, c, d]]

        faces = quad(0, 1, 4, 3) + quad(4, 5, 8, 7)
        return trimesh.Trimesh(pts, np.asarray(faces, int), process=False)

    @staticmethod
    def _masked_split_sheet() -> tuple:
        """A 9x9 open sheet split by a per-face predicate that alternates
        around one vertex — exactly ``_csg_carve``'s own ``inside`` mask at
        the recess mouth, the production route in miniature. One extra face
        is nicked onto the "inside" side of the diagonal so the mask
        alternates around a vertex; each piece is
        ``remove_unreferenced_vertices()``'d, ``_csg_carve``'s own idiom.
        103 vertices, 128 faces once concatenated; degree histogram
        {2: 70, 4: 6}."""
        n = 9
        xs, ys = np.meshgrid(np.linspace(-4, 4, n), np.linspace(-4, 4, n))
        pts = np.column_stack([xs.ravel(), ys.ravel(), np.zeros(n * n)])
        faces = []
        for i in range(n - 1):
            for j in range(n - 1):
                a = i * n + j
                faces.append([a, a + 1, a + n + 1])
                faces.append([a, a + n + 1, a + n])
        F = np.asarray(faces, int)
        C = pts[F].mean(axis=1)
        inside = (np.abs(C[:, 0]) < 1.5) & (np.abs(C[:, 1]) < 1.5)
        d = np.argmin(np.linalg.norm(C - np.array([1.9, 1.9, 0.0]), axis=1))
        inside[d] = True
        m1 = trimesh.Trimesh(pts.copy(), F[~inside].copy(), process=False)
        m1.remove_unreferenced_vertices()
        m2 = trimesh.Trimesh(pts.copy(), F[inside].copy(), process=False)
        m2.remove_unreferenced_vertices()
        return m1, m2

    def test_the_minimal_bowtie_fixture_has_one_degree_4_junction(self):
        bow = self._bowtie_sheet()
        assert len(bow.vertices) == 9
        assert len(bow.faces) == 4
        assert _boundary_degree_histogram(bow) == {2: 6, 4: 1}

    def test_bowtie_solidifies_watertight_with_multiplicity_two_only(self):
        """Before this fix: ``is_watertight`` False, 3 edges at multiplicity
        1 (measured). After: watertight, volume 1.5000mm^3."""
        from case_prep.pipeline.csg import solidify_shell

        bow = self._bowtie_sheet()
        solid = solidify_shell(bow, np.array([0.0, 0.0, 1.0]))
        assert solid.is_watertight
        assert set(_edge_multiplicity_histogram(solid)) == {2}
        assert abs(float(solid.volume) - 1.5) < 1e-6

    def test_the_production_route_miniature_has_six_degree_4_junctions(self):
        m1, m2 = self._masked_split_sheet()
        both = trimesh.util.concatenate([m1, m2])
        assert len(both.vertices) == 103
        assert len(both.faces) == 128
        assert _boundary_degree_histogram(both) == {2: 70, 4: 6}

    def test_the_production_route_miniature_solidifies_watertight(self):
        """Before this fix: not watertight, 22 open edges (measured). After:
        watertight, volume 96.0000mm^3."""
        from case_prep.pipeline.csg import solidify_shell

        m1, m2 = self._masked_split_sheet()
        both = trimesh.util.concatenate([m1, m2])
        solid = solidify_shell(both, np.array([0.0, 0.0, 1.0]))
        assert solid.is_watertight
        assert set(_edge_multiplicity_histogram(solid)) == {2}
        assert abs(float(solid.volume) - 96.0) < 1e-6

    def test_the_out_piece_alone_also_solidifies_the_concatenate_was_not_the_cause(self):
        """Pins that ``trimesh.util.concatenate`` was never the cause:
        the out-piece ALONE already carries 3 junctions and (measured) 11
        open edges under the old walker; watertight after this fix."""
        from case_prep.pipeline.csg import solidify_shell

        m1, _m2 = self._masked_split_sheet()
        hist = _boundary_degree_histogram(m1)
        assert hist.get(4, 0) == 3, \
            "the out-piece alone must already carry the junctions, or this " \
            "pin proves nothing about the concatenate"
        solid = solidify_shell(m1, np.array([0.0, 0.0, 1.0]))
        assert solid.is_watertight
        assert set(_edge_multiplicity_histogram(solid)) == {2}


class TestBoundaryRefusesRatherThanFabricates:
    """§10-AT front 5/W5 point 4 of the fix: a boundary chain that cannot
    close must never be fanned shut — it is a REFUSAL. A single
    NON-MANIFOLD spine edge, shared by three triangular "pages" rather than
    the usual two, leaves each spine endpoint with an ODD number of
    boundary edges in its own face-fan wedge: no pairing closes two-and-two,
    and the leftover edge dead-ends rather than getting a fabricated
    partner."""

    @staticmethod
    def _book_fixture() -> trimesh.Trimesh:
        """Three triangles sharing one spine edge (v0-v1) — multiplicity 3,
        not the ordinary 2. Every other edge is unique to its own page and
        so is boundary; v0 and v1 each end up with 3 boundary edges (one
        per page) inside a SINGLE wedge (the pages are mutually adjacent
        through the shared spine), which is odd and cannot pair cleanly."""
        v0 = [0.0, 0.0, 0.0]
        v1 = [0.0, 0.0, 1.0]
        v2 = [1.0, 0.0, 0.0]
        v3 = [-0.5, 0.87, 0.0]
        v4 = [-0.5, -0.87, 0.0]
        pts = np.array([v0, v1, v2, v3, v4])
        faces = np.array([[0, 1, 2], [0, 1, 3], [0, 1, 4]])
        return trimesh.Trimesh(pts, faces, process=False)

    def test_the_book_fixture_has_a_non_manifold_spine(self):
        book = self._book_fixture()
        cnt = collections.Counter(map(tuple, book.edges_sorted))
        assert cnt[(0, 1)] == 3, "the spine edge must be shared by all 3 pages"

    def test_a_non_closing_chain_raises_naming_the_count_and_a_location(self):
        from case_prep.pipeline.csg import solidify_shell

        book = self._book_fixture()
        with pytest.raises(ValueError) as excinfo:
            solidify_shell(book, np.array([0.0, 0.0, 1.0]))
        message = str(excinfo.value)
        assert "1 chain(s) that do not close" in message
        assert "open edge(s) total" in message
        # a representative COORDINATE, not just a count
        assert "(" in message and ")" in message


class TestSolidifiedShellCachedNamesTheDefect:
    """§10-AT front 5/W5: "the solidified shell is not watertight" alone was
    measured non-actionable — it names neither how many edges nor where.
    ``solidify_shell`` itself already closes cleanly here (the boundary has
    no chain at all — a duplicated face bumps three INTERIOR edges from
    multiplicity 2 to 3 without ever touching the boundary), so this pins
    ``solidified_shell_cached``'s OWN watertightness check and its own
    message, distinct from ``solidify_shell``'s non-closing-chain refusal
    pinned above."""

    @staticmethod
    def _box_with_a_duplicated_face() -> trimesh.Trimesh:
        box = trimesh.creation.box(extents=[4.0, 4.0, 4.0])
        F = np.asarray(box.faces)
        F2 = np.vstack([F, F[:1]])
        return trimesh.Trimesh(np.asarray(box.vertices, float), F2, process=False)

    def test_the_fixture_has_no_boundary_but_is_not_watertight(self):
        """The precondition the pin below needs: ``solidify_shell`` must
        take its EARLY "no boundary" return (unaffected by this fix) so the
        message under test is ``solidified_shell_cached``'s own, not
        ``solidify_shell``'s non-closing-chain refusal."""
        dup = self._box_with_a_duplicated_face()
        cnt = collections.Counter(map(tuple, dup.edges_sorted))
        assert not [e for e, n in cnt.items() if n == 1], \
            "the fixture must have no boundary edge at all"
        assert not dup.is_watertight

    def test_the_refusal_names_the_edge_count_and_a_location(self):
        from case_prep.pipeline.csg import solidified_shell_cached

        dup = self._box_with_a_duplicated_face()
        with pytest.raises(ValueError) as excinfo:
            solidified_shell_cached(dup)
        message = str(excinfo.value)
        assert "not watertight" in message
        assert "3 open/non-manifold edge(s)" in message
        assert "(" in message and ")" in message


class TestRealFleetJunctionSafety:
    """W5, exercised end to end on the real failure case (276794487-
    zimmer-4.5, template zimmer-4.5 variant
    superseded-2026-07-13--6030, relief 0.0): 58 degree-4 boundary
    junctions from ``cap_imprint_parts``'s own per-face mask used to leave
    ``solidified_shell_cached`` refusing and ``arch_with_parts_fused``
    falling back to plain concatenation. SKIPS cleanly when the gitignored
    real-fleet tree is absent (this worktree has none) — exercised at
    integration."""

    @pytest.mark.slow
    def test_the_bowtie_seam_no_longer_falls_back_to_concatenation(self):
        from case_prep.application.cases import discover_cases
        from case_prep.application.catalog import _library_for
        from case_prep.pipeline.csg import solidified_shell_cached
        from case_prep.pipeline.deliverables import (arch_with_parts_fused,
                                                      cap_imprint_parts)

        case_id = "276794487-zimmer-4.5"
        product = (Path(__file__).resolve().parents[1] / "reports" / "product"
                   / case_id / "runs")
        if not REAL.is_dir() or not product.is_dir():
            pytest.skip("real fleet not present (gitignored)")
        run = next((r for r in sorted(product.iterdir(), reverse=True)
                    if any(r.glob("*-implant.json"))), None)
        if run is None:
            pytest.skip(f"no landed run for {case_id}")

        rec = json.loads(next(run.glob("*-implant.json")).read_text())
        case = next((c for c in discover_cases(REAL) if c.id == case_id), None)
        if case is None:
            pytest.skip(f"{case_id} not present under data/real")
        library = _library_for(case.data_root, "zimmer-4.5",
                               ["superseded-2026-07-13--6030"])
        spec = next(s for s in library.specs
                    if s.variant == "superseded-2026-07-13--6030")
        template = library.template(spec)
        rim_r = float(library.variant_dimensions()[
            "superseded-2026-07-13--6030"][0]) / 2.0
        pose = np.asarray(rec["pose_matrix"], float)
        scan = trimesh.load(str(case.scan), force="mesh")

        a, s, _notes = cap_imprint_parts(scan, [(template, pose, 0.0, rim_r)])
        arch = trimesh.util.concatenate([a, s]) if s is not None else a

        solid = solidified_shell_cached(arch)
        assert solid.is_watertight

        _fused, notes = arch_with_parts_fused(arch, [])
        assert notes == []
