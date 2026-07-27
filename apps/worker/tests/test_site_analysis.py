"""Healing-cap site analysis: cap centre + interproximal (mesio-distal) gap to adjacent teeth.

A self-contained SYNTHETIC scene (two teeth flanking a cap) guards the measurement logic in CI;
the real DG Code / Certain 3i case (gitignored) validates it on a clinical scan when present.
"""
from __future__ import annotations

import numpy as np
import pytest
import trimesh

from case_prep.adapters import client_data
from case_prep.adapters.site_analysis import measure_site, occlusal_axis


def _synthetic_site(rng):
    """Occlusal plane = xy, up = +z, mesio-distal = y. Two tooth crowns at y=+6 / y=-6, a cap at
    the origin, and a low gingiva sheet. Proximal edges at y=+-3.5 -> md_span ~7 mm."""
    pts = []
    for cy in (+6.0, -6.0):  # two tooth crowns (tall, dense)
        p = rng.uniform([-3, cy - 2.5, 3.0], [3, cy + 2.5, 6.0], size=(2500, 3))
        pts.append(p)
    cap = rng.uniform([-2, -2, 0.0], [2, 2, 5.0], size=(600, 3))  # cap column
    cap = cap[np.linalg.norm(cap[:, :2], axis=1) < 2.0]
    pts.append(cap)
    ging = rng.uniform([-9, -15, -2.0], [9, 15, 0.0], size=(4000, 3))  # low gingiva sheet
    pts.append(ging)
    return np.vstack(pts)


def test_occlusal_axis_is_unit_and_thin_direction():
    rng = np.random.default_rng(0)
    V = _synthetic_site(rng)
    a = occlusal_axis(V)
    assert abs(np.linalg.norm(a) - 1.0) < 1e-6
    assert abs(abs(a[2]) - 1.0) < 0.2  # thinnest spread is z here -> occlusal axis ~ z


def test_interproximal_gap_on_synthetic_site():
    rng = np.random.default_rng(0)
    V = _synthetic_site(rng)
    r = measure_site(V, cap_center_mm=[0, 0, 2.5], cap_radius=2.0, occ_axis=[0, 0, 1.0])
    assert not r.terminal_site
    assert len(r.adjacent_teeth) == 2
    assert r.md_span_mm is not None and 5.0 < r.md_span_mm < 9.0  # ~7 mm by construction
    assert "ample" in r.classification
    assert r.md_span_points is not None and len(r.md_span_points) == 2


@pytest.mark.skipif(not client_data.DG_SCANBODY.exists(),
                    reason="real DG Code / Certain 3i data not present (gitignored)")
def test_interproximal_gap_on_real_dg_case():
    arch = trimesh.load(client_data.DG_ARCH, force="mesh")
    body = trimesh.load(client_data.DG_SCANBODY, force="mesh")
    V = np.asarray(arch.vertices, float)
    Bc = np.asarray(body.vertices, float).mean(0)
    occ = occlusal_axis(V)
    r = measure_site(V, cap_center_mm=Bc, cap_radius=4.0, occ_axis=occ)
    # premolar-range site: ~8-9 mm mesio-distal, classified ample, two neighbours, tight cap gaps
    assert r.md_span_mm is not None and 7.0 <= r.md_span_mm <= 11.0, f"md_span={r.md_span_mm}"
    assert "ample" in r.classification
    assert len(r.adjacent_teeth) == 2 and not r.terminal_site
    assert r.gap_mesial_mm < 3.0 and r.gap_distal_mm < 3.0
    assert np.linalg.norm(np.asarray(r.cap_center) - Bc) < 1.0  # centre echoes the input


class TestFailureSemantics:
    """A FAILED measurement must say so — not read as a confident clinical verdict — and
    NaN must never reach the JSON report (sweep finding, 2026-07-12)."""

    def test_unmeasurable_span_is_not_reported_as_insufficient(self):
        import numpy as np

        from case_prep.adapters.site_analysis import measure_site

        # two neighbours exist but no clean contact band -> md_span may fail: fabricate
        # by measuring in an empty scene region far from any teeth
        rng = np.random.default_rng(2)
        sheet = np.c_[rng.uniform(-20, 20, 4000), rng.uniform(-20, 20, 4000),
                      rng.normal(0, 0.05, 4000)]
        site = measure_site(sheet, np.array([0.0, 0.0, 0.0]), 2.5,
                            np.array([0.0, 0.0, 1.0]))
        assert "insufficient" not in site.classification
        assert site.md_span_mm is None

    def test_gaps_are_json_safe(self):
        import json

        import numpy as np

        from case_prep.adapters.site_analysis import measure_site

        rng = np.random.default_rng(3)
        sheet = np.c_[rng.uniform(-20, 20, 4000), rng.uniform(-20, 20, 4000),
                      rng.normal(0, 0.05, 4000)]
        site = measure_site(sheet, np.array([0.0, 0.0, 0.0]), 2.5,
                            np.array([0.0, 0.0, 1.0]))
        payload = json.dumps({"m": site.gap_mesial_mm, "d": site.gap_distal_mm,
                              "s": site.md_span_mm}, allow_nan=False)
        assert payload  # dumps with allow_nan=False raises on NaN
