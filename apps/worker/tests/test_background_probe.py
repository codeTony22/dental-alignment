"""Pins for the background probe + gate census (goal-3 slice 0, plan
2026-08-16): the acceptance INSTRUMENT everything downstream is judged by.

``background_fraction`` answers "does this artifact show background (white)
through itself inside a site's own neighbourhood disc?" — the formalized
version of the ad-hoc painter-sorted probes that diagnosed the moat, the
ghost and the floor breach on the real fleet. ``bridge_gate_census``
replays ``_bridge_recess_collar``'s exact outer-candidate gates per
boundary loop, so a silent bridge is diagnosed by measurement instead of
re-derivation.
"""
from __future__ import annotations

import numpy as np
import trimesh

from case_prep.research.background_probe import (background_fraction,
                                                 bridge_gate_census)


def _plate_with_annulus_gap(gap: bool, n: int = 121, extent: float = 8.0,
                            r_in: float = 2.4, r_out: float = 3.0
                            ) -> trimesh.Trimesh:
    """A flat plate; when ``gap`` the annulus r_in..r_out is genuinely
    absent — the moat scene, minimal."""
    xs, ys = np.meshgrid(np.linspace(-extent, extent, n),
                         np.linspace(-extent, extent, n))
    pts = np.column_stack([xs.ravel(), ys.ravel(), np.zeros(xs.size)])
    faces = []
    for i in range(n - 1):
        for j in range(n - 1):
            a = i * n + j
            cx = (xs[i, j] + xs[i, j + 1] + xs[i + 1, j + 1]) / 3.0
            cy = (ys[i, j] + ys[i, j + 1] + ys[i + 1, j + 1]) / 3.0
            if gap and r_in < np.hypot(cx, cy) < r_out:
                continue
            faces.extend([[a, a + 1, a + n + 1], [a, a + n + 1, a + n]])
    return trimesh.Trimesh(pts, np.asarray(faces), process=False)


POSE = np.eye(4)


class TestBackgroundProbe:
    def test_a_moated_plate_shows_background_and_a_bridged_one_shows_none(
            self):
        moated = _plate_with_annulus_gap(gap=True)
        solid = _plate_with_annulus_gap(gap=False)
        f_moat = background_fraction(moated, POSE, rim_r=2.2)
        f_solid = background_fraction(solid, POSE, rim_r=2.2)
        assert f_moat > 0.0, "the annulus gap must read as background"
        assert f_solid == 0.0, "a solid plate shows no background at all"

    def test_the_count_is_confined_to_the_site_disc(self):
        # the same gap moved far outside the disc: nothing counts
        plate = _plate_with_annulus_gap(gap=False, extent=12.0)
        # cut a hole far from the site (at x=+9, outside rim_r + search)
        F = np.asarray(plate.faces)
        C = np.asarray(plate.triangles_center, float)
        keep = ~(np.hypot(C[:, 0] - 9.0, C[:, 1]) < 1.0)
        holed = trimesh.Trimesh(np.asarray(plate.vertices, float),
                                F[keep], process=False)
        assert background_fraction(holed, POSE, rim_r=2.2) == 0.0

    def test_two_probes_are_identical(self):
        moated = _plate_with_annulus_gap(gap=True)
        a = background_fraction(moated, POSE, rim_r=2.2)
        b = background_fraction(moated, POSE, rim_r=2.2)
        assert a == b, "the probe must be deterministic to the float"


class TestGateCensus:
    def test_each_loop_reports_its_per_gate_verdict(self):
        """A ring BELOW the mouth's own max radius (the 295811960 shape)
        must report radius_window=False while roundness/z-band read True —
        the diagnosis the census exists to make."""
        # mouth: a cup wall at r=3.1 (its own boundary at the top ring)
        theta = np.linspace(-np.pi, np.pi, 48, endpoint=False)
        mouth = np.column_stack([3.1 * np.cos(theta), 3.1 * np.sin(theta),
                                 np.zeros(48)])
        # candidate bank: round, near the mouth height, but at r=2.84 —
        # below the mouth's max radius
        bank = np.column_stack([2.84 * np.cos(theta), 2.84 * np.sin(theta),
                                np.full(48, 0.2)])
        rows = bridge_gate_census([bank], mouth, POSE)
        assert len(rows) == 1
        row = rows[0]
        assert row["n"] == 48
        assert row["radius_window"] is False
        assert row["roundness"] is True
        assert row["z_band"] is True

    def test_a_qualifying_ring_passes_every_gate(self):
        theta = np.linspace(-np.pi, np.pi, 40, endpoint=False)
        mouth = np.column_stack([2.2 * np.cos(theta), 2.2 * np.sin(theta),
                                 np.zeros(40)])
        ring = np.column_stack([2.6 * np.cos(theta), 2.6 * np.sin(theta),
                                np.full(40, 0.1)])
        rows = bridge_gate_census([ring], mouth, POSE)
        assert rows[0]["radius_window"] is True
        assert rows[0]["roundness"] is True
        assert rows[0]["z_band"] is True
