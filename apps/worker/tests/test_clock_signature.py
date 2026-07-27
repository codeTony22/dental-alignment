"""Coded-cutout clock signature (domain/clock_signature.py) — the validated "e8"
extractor (2026-07-20 two-pose consistency study: the only design that reproduced
known applied rotations on the real fleet, 6/7 sites <= 10 deg).

The load-bearing properties under test:
- IDENTITY: the reading grows one-for-one with an applied rotation about the part's
  own axis (m_after - m_before = applied) — this is what the two-pose validation
  proved and what production's nulling rotation (-reading) relies on.
- Recovery holds under a TILTED seat (zero-tilt fixtures are provably blind to a
  class of compensation regressions — battery lesson 2026-07-19).
- A template with no coded relief must refuse (w_notch = 0 downstream).
- Deep geometry OUTSIDE the coded band (gingival sulcus) must not move the peak.
- Calling template_signature mid-pipeline must not perturb the global RNG stream
  (the pinned stream feeds later stages — measured hazard, review 2026-07-20).
"""
from pathlib import Path

import numpy as np
import pytest
import trimesh

from case_prep.adapters.cap_library import CapLibrary
from case_prep.domain.clock_signature import (NotchReading, notch_reading,
                                              scan_rim_centre,
                                              template_signature, wrap_deg)

ROOT = Path(__file__).parents[1] / "data/real/library/caps/zimmer-4.5"


def _template():
    if not ROOT.exists():
        pytest.skip("library not present")
    lib = CapLibrary.load(ROOT)
    return lib.template(next(s for s in lib.specs if s.variant == "6020"))


def _scan_cloud(tmpl, n=30000):
    np.random.seed(0)
    samp, _ = trimesh.sample.sample_surface(tmpl, n)
    return np.asarray(samp, float)


def _rotate_about(pts, centre_xy, phi_deg):
    c, s = np.cos(np.radians(phi_deg)), np.sin(np.radians(phi_deg))
    rz = np.array([[c, -s], [s, c]])
    out = pts.copy()
    out[:, :2] = (pts[:, :2] - centre_xy) @ rz.T + centre_xy
    return out


class TestClockSignature:
    def test_reading_tracks_an_applied_rotation(self):
        """The two-pose identity, on a synthetic clone of the validation protocol:
        rotating the scan content by phi about the rim centre moves the reading by
        -phi (equivalently: rotating the POSE by phi moves it by +phi)."""
        tmpl = _template()
        sig = template_signature(tmpl)
        assert sig.has_coded_relief, "the real 6020 carries coded relief"
        cloud = _scan_cloud(tmpl)
        c = scan_rim_centre(cloud, sig.ztop, sig.rmax)
        r0 = notch_reading(cloud, sig, c)
        assert r0.has_evidence and abs(r0.shift_deg) < 4.0, \
            "an unrotated clone must read ~aligned with strong evidence"
        for phi in (35.0, -70.0, 117.0):
            rp = notch_reading(_rotate_about(cloud, c, phi), sig, c)
            assert rp.has_evidence
            moved = wrap_deg(rp.shift_deg - r0.shift_deg)
            assert abs(wrap_deg(moved + phi)) < 4.0, \
                (f"applied {phi} deg to the scan content, reading moved {moved} — "
                 f"the identity the nulling rotation relies on is broken")

    def test_recovery_under_a_tilted_seat(self):
        """8-deg tilted pose frame: the reading must still track (zero-tilt fixtures
        are blind to compensation-class regressions)."""
        tmpl = _template()
        sig = template_signature(tmpl)
        cloud = _scan_cloud(tmpl)
        c = scan_rim_centre(cloud, sig.ztop, sig.rmax)
        t = np.radians(8.0)
        Rx = np.array([[1, 0, 0],
                       [0, np.cos(t), -np.sin(t)],
                       [0, np.sin(t), np.cos(t)]])
        # world scan = tilted pose of content rotated by phi about the rim axis;
        # reading in the canonical frame of the un-rotated tilted pose must be ~phi
        phi = 55.0
        rot = _rotate_about(cloud, c, phi)
        world = rot @ Rx.T
        canon = world @ Rx  # back into the pose's canonical frame
        rp = notch_reading(canon, sig, c)
        assert rp.has_evidence
        assert abs(wrap_deg(rp.shift_deg + phi)) < 6.0, \
            f"tilted-seat reading {rp.shift_deg} for applied {phi}"

    def test_no_relief_template_refuses(self):
        cyl = trimesh.creation.cylinder(radius=3.0, height=5.0, sections=96)
        sig = template_signature(cyl)
        assert not sig.has_coded_relief, \
            "a plain cylinder has no coded relief — the notch term must disarm"
        cloud = _scan_cloud(cyl)
        r = notch_reading(cloud, sig, np.zeros(2))
        assert not r.has_evidence

    def test_sulcus_outside_the_band_does_not_move_the_peak(self):
        """Deep annular dips at the gingival-sulcus radius (outside the coded band)
        were what broke the diagnostic-era extractors — the band/z windows must
        exclude them."""
        tmpl = _template()
        sig = template_signature(tmpl)
        cloud = _scan_cloud(tmpl)
        c = scan_rim_centre(cloud, sig.ztop, sig.rmax)
        r0 = notch_reading(cloud, sig, c)
        rng = np.random.default_rng(1)
        ang = rng.uniform(0, 2 * np.pi, 3000)
        rad = sig.rmax * rng.uniform(0.95, 1.30, 3000)
        depth = rng.uniform(1.5, 2.7, 3000)
        sulcus = np.c_[c[0] + rad * np.cos(ang), c[1] + rad * np.sin(ang),
                       sig.ztop - depth]
        r1 = notch_reading(np.vstack([cloud, sulcus]), sig, c)
        assert r1.has_evidence
        assert abs(wrap_deg(r1.shift_deg - r0.shift_deg)) < 4.0, \
            "sulcus points outside the coded band moved the peak"

    def test_template_signature_preserves_the_rng_stream(self):
        tmpl = _template()
        # evict any cached signature so the sampling path actually runs
        from case_prep.domain import clock_signature as cs
        cs._SIG_CACHE.pop(id(tmpl), None)
        np.random.seed(123)
        expected = np.random.rand(3)
        np.random.seed(123)
        template_signature(tmpl)
        got = np.random.rand(3)
        assert np.allclose(expected, got), \
            "template_signature must save/restore the global RNG state"

    def test_noise_scan_has_no_evidence(self):
        tmpl = _template()
        sig = template_signature(tmpl)
        rng = np.random.default_rng(2)
        junk = np.c_[rng.uniform(-3, 3, 4000), rng.uniform(-3, 3, 4000),
                     rng.uniform(sig.ztop - 1.2, sig.ztop + 0.2, 4000)]
        r = notch_reading(junk, sig, np.zeros(2))
        assert isinstance(r, NotchReading)
        assert not r.has_evidence, "uniform noise must not clear the evidence gates"
