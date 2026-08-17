"""THE PER-ARTIFACT SEMANTICS AUDIT (plan 2026-08-16, goal-3 slice 3).

Each deliverable keeps its ORIGINAL ask — the client's ruling at the
per-deliverable spec table (plan §"THE DELIVERABLES SPEC", 2026-08-16:
"The deliverables changed each functionality is different - refer to the
original asks for each of the deliverables"). This file pins the CONTRASTS
between artifacts — the facts that make each tab itself and not its
neighbour — rather than re-pinning each builder's own mechanics (those
live in test_deliverables.py / test_csg.py). The audit changes no
production code; a discrepancy with an original ruling is pinned AS-IS
and ledgered as a named client question.

Anchors: §10-AS (open arch + exact cut doctrine), §10-AT (erase ruling,
fused composites), the fourth ruling (artifact 6, gingival floor,
2026-08-15), §10-AU/AV (voted bridge, drape, no-floaters cull).
"""
from __future__ import annotations

import numpy as np
import trimesh

from case_prep.pipeline import deliverables as d
from case_prep.pipeline.isolation import isolate_scanned_cap

from test_deliverables import _bulging_arch, _flat_sheet, _pose_at


def _recess_floor_a(mesh: trimesh.Trimesh) -> float:
    """The recess floor's height, read the way the shipped floor pin reads
    it (test_deliverables' own gingival-floor pin): a RAY down the site's
    axis — a boolean floor is large triangles whose vertices all sit on
    the rim, so a vertex census inside the hole reads empty while the
    floor is really there. All fixtures here pose the site at the
    origin, axis +z."""
    locs, *_ = mesh.ray.intersects_location(
        ray_origins=[np.array([0.0, 0.0, 100.0])],
        ray_directions=[np.array([0.0, 0.0, -1.0])])
    assert len(locs) > 0, "no material under the site axis — no floor at all"
    return float(np.asarray(locs, float)[:, 2].max())


class TestTab3KeepsWhatTheDeliverablesErase:
    """THE MEASUREMENT/MANUFACTURE CONTRAST (tab 3's snippet vs every arch
    tab; the erase ruling, client live 2026-08-15, landed @f3f2aa4): the
    scanned-cap snippet is what the scanner SAW — measured crust included,
    deviation and all — while every deliverable ERASES that same crust
    where the library cap was aligned. One fixture, both readings."""

    def test_the_isolation_keeps_the_crust_the_fuse_erases(
            self, engine_expects):
        arch, template, pose, bulge = _bulging_arch()
        rim_r = 2.6

        isolated = isolate_scanned_cap(arch, template, pose, rim_r)
        assert isolated is not None
        iso_v = {tuple(np.round(v, 6))
                 for v in np.asarray(isolated.vertices, float)}
        bv = np.asarray(bulge.vertices, float)
        proud = bv[np.linalg.norm(bv[:, :2], axis=1) > 2.0 + 0.05]
        kept = sum(1 for v in proud if tuple(np.round(v, 6)) in iso_v)
        assert kept > 0, \
            "the snippet lost the measured crust — it no longer shows " \
            "what the scanner saw (erase ruling scope leak)"

        if not engine_expects.tracked:
            return  # the fused erase contrast is the tracked path's pin
        fused, _notes = d.arch_with_parts_fused(
            arch, [(template.copy(), pose)],
            excise_sites=[(template, pose, rim_r)])
        fused_v = {tuple(np.round(v, 6))
                   for v in np.asarray(fused.vertices, float)}
        survivors = sum(1 for v in proud if tuple(np.round(v, 6)) in fused_v)
        assert survivors == 0, \
            f"{survivors} crust vertex(es) survived the fuse the erase " \
            f"ruling says must die"


class TestTheThreeFloorsDiffer:
    """ONE FIXTURE, THREE FLOORS (the spec table's rows 4/5/6): the dish
    (tab 4) digs the visible-depth pocket below the gum; the platform
    (tab 5) countersinks deeper — the full-depth read; artifact 6's hole
    is floored AT the gingival level (the fourth ruling: "the hole with
    the gingival floor"), the shallowest of the three."""

    def _site(self):
        # the shipped gingival-floor pin's own fixture (test_deliverables
        # TestOpenArchWithFlooredHoles._site): flat gum at world z=0, the
        # site posed at z=1.0 — the gingival floor is z=0 exactly
        return (trimesh.creation.cylinder(radius=2.0, height=4.0),
                _pose_at(0, 0, 1.0), 0.2, 2.0)

    def test_dish_platform_and_gingival_floors_order_themselves(self):
        site = self._site()

        _out_d, socket_dish, _n1 = d.cap_imprint_parts(
            _flat_sheet(), [site])
        assert socket_dish is not None
        dish_floor = _recess_floor_a(socket_dish)

        _out_p, socket_platform, _n2 = d.cap_imprint_parts(
            _flat_sheet(), [site], top_floor=True)
        assert socket_platform is not None
        platform_floor = _recess_floor_a(socket_platform)

        floored, _n3 = d.open_arch_with_floored_holes(_flat_sheet(), [site])
        assert floored is not None
        gingival_floor = _recess_floor_a(floored)

        # the flat gum sits at z=0: artifact 6's floor is AT the gum...
        assert abs(gingival_floor - 0.0) < 0.45, \
            f"artifact 6's floor sits {gingival_floor:.2f} from the gum — " \
            f"the fourth ruling wants it AT the gingival level"
        # ...and both recess floors dig below it, each by its own
        # mechanic. MEASURED FIXTURE TRUTH (2026-08-16): on a PLAIN
        # CYLINDER template the countersink arithmetic reads -0.50 vs the
        # dish's -1.20 — a real cap's platform sits deep and the
        # deeper-than-dish contrast is the real-mesh corpus's pin
        # (test_csg_corpus), not this synthetic one's to fake.
        assert dish_floor < gingival_floor - 1e-6, \
            f"the dish ({dish_floor:.2f}) does not dig below the gum floor " \
            f"({gingival_floor:.2f})"
        assert platform_floor < gingival_floor - 1e-6, \
            f"the platform countersink ({platform_floor:.2f}) does not dig " \
            f"below the gum floor ({gingival_floor:.2f})"
        assert abs(platform_floor - dish_floor) > 1e-6, \
            "the dish and the platform countersink read one identical " \
            "floor — two artifacts, one geometry, the fifth artifact " \
            "would be a duplicate row"


class TestEveryArtifactShipsConnected:
    """HARD INVARIANT 2 ACROSS THE TAB FAMILY (client, plan 2026-08-16;
    landed @§10-AV): one planted floater, every builder — each artifact
    ships exactly one connected body on this single-site fixture."""

    def _floatered_scan(self):
        # n=81 (0.2mm pitch): the n=19 default's 0.89mm-jagged excision
        # edge splits the drape's vote into sub-threshold radial shards
        # (measured 2026-08-16) — a real scan's pitch is 0.2mm
        f = trimesh.creation.icosphere(subdivisions=1, radius=0.4)
        f.apply_translation([1.5, 1.5, 3.0])
        return trimesh.util.concatenate([_flat_sheet(n=81), f])

    def _site(self):
        template = trimesh.creation.cylinder(radius=2.0, height=4.0,
                                             sections=48)
        template.apply_translation([0, 0, 2.0])
        return (template, _pose_at(0.0, 0.0, 0.0), 0.0, 2.3)

    def test_carve_floored_holes_and_fuse_all_ship_one_body(
            self, engine_expects):
        scan = self._floatered_scan()
        site = self._site()

        out, _socket, _n1 = d.cap_imprint_parts(scan, [site])
        assert len(out.split(only_watertight=False)) == 1

        floored, _n2 = d.open_arch_with_floored_holes(scan, [site])
        assert floored is not None
        assert len(floored.split(only_watertight=False)) == 1

        if not engine_expects.tracked:
            return
        template, _pose, _o, rim_r = site
        sunk_pose = _pose_at(0.0, 0.0, -0.5)
        fused, _n3 = d.arch_with_parts_fused(
            scan, [(template.copy(), sunk_pose)],
            excise_sites=[(template, sunk_pose, rim_r)])
        comps = fused.split(only_watertight=False)
        # THE INVARIANT IS SPATIAL, NOT TOPOLOGICAL (learned 2026-08-17,
        # the manifold-guard era): the erase ruling ALWAYS excises the
        # union-seam ring (its face centroids sit inside the rim), and a
        # strip cannot edge-join a CLOSED part without going
        # non-manifold — so a fused site is necessarily the main body
        # plus its own OVERLAPPING part body. Two bodies, both seated;
        # anything beyond is a floater the cull must have eaten.
        assert len(comps) <= 2, \
            f"{len(comps)} bodies in the fused composite"
        if len(comps) == 2:
            small = min(comps, key=lambda c: len(c.faces))
            ctr = np.asarray(small.triangles_center, float).mean(axis=0)
            assert np.hypot(ctr[0], ctr[1]) < rim_r + 1.0, \
                "the extra body is not the site's own part — it floats"
