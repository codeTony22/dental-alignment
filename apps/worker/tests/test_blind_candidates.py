"""Pins for the blind cylinder seed proposer (adapters/blind_candidates.py).

An EXPERIMENTAL instrument with no production consumer yet (the wiring is
queued behind the complementarity measurement —
docs/engagement/blind-detection-scoreboard.md). These pins hold the
algorithm's contract so the calibration slice starts from known ground:
a proud machined cylinder is found; a DOMED cap is found (the dome
allowance — round 3's plain rise gate executed exactly these); a lopsided
cusp is not proposed; and the proposal is deterministic, because any
future consumer sits under detect()'s own determinism pin.
"""
from __future__ import annotations

import numpy as np
import trimesh

from case_prep.adapters.blind_candidates import (BlindCandidate,
                                                 propose_blind_candidates)


def _sheet_with_bump(bump, n=241, extent=12.0):
    """A flat gum sheet (z=0) with ``bump(r) -> z`` stamped at the origin —
    n=241 over ±12mm is ~0.1mm spacing, the real scans' own point density
    (a 0.2mm grid starves the proposer's patch gate exactly as a decimated
    scan would)."""
    xs, ys = np.meshgrid(np.linspace(-extent, extent, n),
                         np.linspace(-extent, extent, n))
    rr = np.hypot(xs, ys)
    zz = bump(rr, xs, ys)
    pts = np.column_stack([xs.ravel(), ys.ravel(), zz.ravel()])
    faces = []
    for i in range(n - 1):
        for j in range(n - 1):
            a = i * n + j
            faces.append([a, a + 1, a + n + 1])
            faces.append([a, a + n + 1, a + n])
    return trimesh.Trimesh(pts, np.asarray(faces), process=False)


def _cylinder_bump(radius=2.6, height=3.0, ramp=0.4):
    def bump(rr, xs, ys):
        z = np.zeros_like(rr)
        z[rr <= radius] = height
        edge = (rr > radius) & (rr < radius + ramp)
        z[edge] = height * (radius + ramp - rr[edge]) / ramp
        return z
    return bump


def _domed_cap_bump(radius=2.6, wall=1.6, dome=1.8, ramp=0.4):
    """A short machined wall with a revolute dome rising past the wall top —
    the neodent-family shape whose own dome round 3's rise gate executed."""
    def bump(rr, xs, ys):
        z = np.zeros_like(rr)
        inside = rr <= radius
        z[inside] = wall + dome * np.sqrt(
            np.clip(1.0 - (rr[inside] / radius) ** 2, 0.0, 1.0))
        edge = (rr > radius) & (rr < radius + ramp)
        z[edge] = wall * (radius + ramp - rr[edge]) / ramp
        return z
    return bump


def _lopsided_cusp_bump(radius=2.6, height=3.0):
    """Tooth-like: an off-centre pointed cusp with no machined ring."""
    def bump(rr, xs, ys):
        d = np.hypot(xs - 1.2, ys - 0.6)
        return height * np.exp(-(d / 1.6) ** 2)
    return bump


def _closest(cands, point):
    point = np.asarray(point, float)
    best = None
    for c in cands:
        centre = np.asarray(c.centre)
        axis = np.asarray(c.axis)
        w = point - centre
        dist = float(np.linalg.norm(w - (w @ axis) * axis))
        if best is None or dist < best[0]:
            best = (dist, c)
    return best


class TestBlindCandidates:
    def test_a_proud_machined_cylinder_is_found(self):
        mesh = _sheet_with_bump(_cylinder_bump())
        cands = propose_blind_candidates(mesh)
        assert cands, "a clean proud cylinder must produce a candidate"
        dist, c = _closest(cands, [0.0, 0.0, 3.0])
        assert dist < 0.5, f"axis {dist:.2f}mm off the bump's own centre"
        assert abs(np.asarray(c.axis) @ np.array([0.0, 0.0, 1.0])) > 0.98
        assert abs(c.radius_mm - 2.6) <= 0.4

    def test_a_domed_cap_is_found_the_dome_allowance(self):
        mesh = _sheet_with_bump(_domed_cap_bump())
        cands = propose_blind_candidates(mesh)
        assert cands, ("a revolute dome above a short wall is a CAP — the "
                       "plain rise gate that rejected it was the measured "
                       "round-3 defect")
        dist, _c = _closest(cands, [0.0, 0.0, 1.6])
        assert dist < 0.5

    def test_a_lopsided_cusp_is_not_proposed(self):
        mesh = _sheet_with_bump(_lopsided_cusp_bump())
        cands = propose_blind_candidates(mesh)
        near = [c for c in cands
                if _closest([c], [1.2, 0.6, 3.0])[0] < 1.5]
        assert near == [], "a tooth-shaped cusp must not become a seed"

    def test_deterministic_for_a_fixed_seed(self):
        mesh = _sheet_with_bump(_domed_cap_bump())
        a = propose_blind_candidates(mesh)
        b = propose_blind_candidates(mesh)
        assert [(c.centre, c.axis, c.radius_mm, c.inliers) for c in a] == \
               [(c.centre, c.axis, c.radius_mm, c.inliers) for c in b]

    def test_an_empty_or_flat_scan_returns_nothing(self):
        assert propose_blind_candidates(trimesh.Trimesh()) == []
        flat = _sheet_with_bump(lambda rr, xs, ys: np.zeros_like(rr))
        assert propose_blind_candidates(flat) == []

    def test_the_candidate_is_a_frozen_value(self):
        c = BlindCandidate(centre=(0, 0, 0), axis=(0, 0, 1), radius_mm=2.6,
                           inliers=100, wall_span_mm=2.0, score=1.0)
        try:
            c.radius_mm = 3.0  # type: ignore[misc]
            raise AssertionError("BlindCandidate must be frozen")
        except AttributeError:
            pass
