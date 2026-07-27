"""Screw-channel loop truth (G2, master plan §7.4 / autopsy 2026-07-23): the cap CADs
carry the channel EXACTLY — their open boundary loops are perfect circles (radius/z std
0.002-0.05mm measured across all 12 variants) — so the channel mouth must be read from
the loops, never estimated from a surface centroid (a hole feeds no vertices to a
centroid, which is REPELLED from the bore: measured 0.87-0.96mm wrong at ~174deg on
cap6030/7030)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import trimesh

from case_prep.adapters.cap_library import CapLibrary
from case_prep.domain.channel import channel_from_boundary_loops

LIB_ROOT = Path(__file__).parents[1] / "data/real/library/caps"


def _open_tube(centre_top, centre_bot, r_top, r_bot, n=96, wave=0.0):
    """Uncapped tube: two n-gon rings joined by wall quads — two open boundary loops.
    ``wave`` adds a radial 3-lobe ripple (a deliberately NON-circular boundary)."""
    th = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
    rt = r_top + wave * np.sin(3.0 * th)
    rb = r_bot + wave * np.sin(3.0 * th)
    top = np.c_[centre_top[0] + rt * np.cos(th), centre_top[1] + rt * np.sin(th),
                np.full(n, float(centre_top[2]))]
    bot = np.c_[centre_bot[0] + rb * np.cos(th), centre_bot[1] + rb * np.sin(th),
                np.full(n, float(centre_bot[2]))]
    faces = []
    for i in range(n):
        j = (i + 1) % n
        faces.append([i, n + i, n + j])
        faces.append([i, n + j, j])
    return trimesh.Trimesh(np.vstack([top, bot]), np.array(faces), process=False)


class TestChannelFromBoundaryLoops:
    def test_reads_mouth_base_and_axis_from_a_straight_channel(self):
        """Cap-channel shape: narrow mouth on top, wide base opening at the bottom,
        both centred at the same xy — mouth/base must be told apart by TOP PROXIMITY,
        never by size (the mouth is the SMALLER circle)."""
        ch = channel_from_boundary_loops(
            _open_tube((0.4, -0.1, 4.0), (0.4, -0.1, -4.0), r_top=1.1, r_bot=2.25))
        assert ch is not None, "two clean circular loops must qualify as a channel"
        assert np.allclose(ch.mouth_centre, [0.4, -0.1, 4.0], atol=1e-9), \
            f"mouth centre {ch.mouth_centre} is not the TOP loop centre"
        assert abs(ch.mouth_radius - 1.1) < 1e-6, \
            f"mouth radius {ch.mouth_radius:.3f} != 1.1 — picked the base loop?"
        assert ch.base_centre is not None and np.allclose(
            ch.base_centre, [0.4, -0.1, -4.0], atol=1e-9)
        assert abs(ch.base_radius - 2.25) < 1e-6
        assert ch.axis is not None and ch.axis[2] > 0
        assert float(ch.axis @ [0.0, 0.0, 1.0]) > 0.99999, \
            f"axis {ch.axis} should be +z for concentric horizontal loops"

    def test_deterministic_and_rng_state_safe(self):
        tube = _open_tube((0.4, -0.1, 4.0), (0.4, -0.1, -4.0), 1.1, 2.25)
        np.random.seed(11)
        before = np.random.get_state()
        a = channel_from_boundary_loops(tube)
        b = channel_from_boundary_loops(tube)
        after = np.random.get_state()
        assert np.array_equal(a.mouth_centre, b.mouth_centre)
        assert a.mouth_radius == b.mouth_radius
        for e, g in zip(before, after):
            assert np.array_equal(e, g), \
                "channel read perturbed the global RNG stream (house determinism rule)"

    def test_watertight_mesh_has_no_channel(self):
        assert channel_from_boundary_loops(trimesh.creation.box()) is None, \
            "a watertight mesh has no open loops — no channel to read"

    def test_non_circular_boundary_is_refused(self):
        tube = _open_tube((0, 0, 4.0), (0, 0, -4.0), 1.1, 1.1, wave=0.3)
        assert channel_from_boundary_loops(tube) is None, \
            "a 3-lobe rippled boundary (radial std ~0.2mm) is not a channel circle"

    def test_sparse_loops_are_refused(self):
        tube = _open_tube((0, 0, 4.0), (0, 0, -4.0), 1.1, 1.1, n=8)
        assert channel_from_boundary_loops(tube) is None, \
            "8-point loops carry too little evidence (real loops discretize to 221-328)"

    def test_a_circle_far_from_the_top_is_not_a_mouth(self):
        """Wavy (disqualified) mouth + clean base: the only qualifying circle sits at
        the BOTTOM — it must not be promoted to a channel mouth (measured mouths sit
        within 0.03mm of the template top)."""
        n = 96
        th = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
        rt = 1.1 + 0.3 * np.sin(3.0 * th)
        top = np.c_[rt * np.cos(th), rt * np.sin(th), np.full(n, 4.0)]
        bot = np.c_[1.1 * np.cos(th), 1.1 * np.sin(th), np.full(n, -4.0)]
        faces = []
        for i in range(n):
            j = (i + 1) % n
            faces.extend([[i, n + i, n + j], [i, n + j, j]])
        tube = trimesh.Trimesh(np.vstack([top, bot]), np.array(faces), process=False)
        assert channel_from_boundary_loops(tube) is None

    def test_off_concentric_base_yields_mouth_but_no_axis(self):
        """A base opening 0.5mm off the mouth xy is OUTSIDE the measured straight-
        channel envelope (catalog max mouth-base xy disagreement 0.083mm): keep the
        zero-noise mouth read, refuse to invent a base pairing or an axis."""
        ch = channel_from_boundary_loops(
            _open_tube((0.5, 0.0, 4.0), (0.0, 0.0, -4.0), 1.1, 1.1))
        assert ch is not None
        assert np.allclose(ch.mouth_centre, [0.5, 0.0, 4.0], atol=1e-9)
        assert ch.base_centre is None and ch.base_radius is None
        assert ch.axis is None, \
            "an axis claimed across a non-concentric loop pair is a silent guess"


@pytest.mark.skipif(not LIB_ROOT.exists(), reason="real cap library not on this host")
class TestCatalogLoopTruth:
    """Every catalog variant, both systems — the G2 acceptance contract."""

    @staticmethod
    def _variants():
        out = []
        for system in ("neodent-gm", "zimmer-4.5"):
            lib = CapLibrary.load(LIB_ROOT / system)
            for spec in sorted(lib.specs, key=lambda s: s.variant):
                out.append((f"{system}-{spec.variant}", lib.template(spec)))
        return out

    @pytest.mark.slow
    def test_template_bore_centre_matches_loop(self):
        """The production estimator must sit on the loop truth (<= 0.05mm) for EVERY
        variant. Pre-G2 the surface-centroid estimator read 0.87-1.06mm away at ~174deg
        the wrong azimuth (autopsy 2026-07-23) and poisoned _recess_clocking levers,
        scoreboard bore_void_off and the QC bore star."""
        from case_prep.pipeline.auto_flow import _template_bore_centre

        for name, tmpl in self._variants():
            ch = channel_from_boundary_loops(tmpl)
            assert ch is not None, f"{name}: no loop read on a catalog cap CAD"
            est = _template_bore_centre(tmpl)
            assert est is not None, f"{name}: estimator returned None"
            gap = float(np.linalg.norm(np.asarray(est) - ch.mouth_centre))
            assert gap <= 0.05, \
                (f"{name}: _template_bore_centre sits {gap:.3f}mm from the zero-noise "
                 f"loop truth {np.round(ch.mouth_centre, 3)} — estimator poisoned again?")

    @pytest.mark.slow
    def test_loop_read_is_self_consistent_across_the_two_loops(self):
        """Mouth and base loops of one straight channel must agree in xy (measured
        max disagreement 0.083mm, zimmer-7030) and pair into a near +z axis; radii
        must sit in the measured catalog envelope (mouth 1.078-1.152, base
        1.753-2.261)."""
        for name, tmpl in self._variants():
            ch = channel_from_boundary_loops(tmpl)
            assert ch is not None, f"{name}: no loop read"
            assert ch.base_centre is not None, \
                f"{name}: base opening loop not paired — concentricity gate too tight?"
            xy_gap = float(np.linalg.norm((ch.mouth_centre - ch.base_centre)[:2]))
            assert xy_gap <= 0.12, \
                f"{name}: mouth/base xy disagree by {xy_gap:.3f}mm (catalog max 0.083)"
            assert ch.axis is not None and float(ch.axis[2]) > 0.999, \
                f"{name}: channel axis {ch.axis} is not near +z"
            assert 1.0 <= ch.mouth_radius <= 1.2, \
                f"{name}: mouth radius {ch.mouth_radius:.3f} outside measured envelope"
            assert 1.7 <= ch.base_radius <= 2.3, \
                f"{name}: base radius {ch.base_radius:.3f} outside measured envelope"


class TestEstimatorFallback:
    """_template_bore_centre keeps the (biased) top-core centroid ONLY when no loop
    exists — the contract (3-vector or None) is unchanged."""

    def test_loopless_mesh_falls_back_to_the_top_core_centroid(self):
        from case_prep.pipeline.auto_flow import _template_bore_centre

        blob = trimesh.creation.icosphere(subdivisions=3, radius=5.0)  # watertight
        assert channel_from_boundary_loops(blob) is None
        est = _template_bore_centre(blob)
        assert est is not None, "fallback centroid path must still answer"
        assert float(np.linalg.norm(est[:2])) < 0.1, \
            "sphere pole-cap centroid should sit on the axis"

    def test_degenerate_mesh_returns_none(self):
        from case_prep.pipeline.auto_flow import _template_bore_centre

        tri = trimesh.Trimesh(np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0]]),
                              np.array([[0, 1, 2]]), process=False)
        assert _template_bore_centre(tri) is None
