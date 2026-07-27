"""Capture gate (master plan §1 SCAN / §8 item 11): the industry intake mechanism.

Synthetic clouds exercise the three cited checks (rim-arc coverage, code-band
visibility, collar exposure) and the message directions; the real-fleet tests pin the
calibration receipts — t7 (the measured failure exemplar: ~46% of the seat-band arc
empty scan) MUST gate rescan, a healthy site must not.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from case_prep.domain.capture_gate import (
    CODE_PASS_MIN, CODE_RESCAN_BELOW, EXPO_PASS_MIN_MM, EXPO_RESCAN_BELOW_MM,
    RIM_N_BINS, RIM_PASS_MIN, RIM_RESCAN_BELOW, assess_capture)

REAL = Path(__file__).parents[1] / "data/real"


# --- synthetic clouds ------------------------------------------------------------------
# IOS-class density (~0.15mm spacing — the fleet's scans measure 0.1-0.2mm): the
# occupancy constants are calibrated at this density (see RIM_BIN_MIN_PTS).

def _disc(r0, r1, z, step=0.15):
    xs = np.arange(-r1, r1 + step, step)
    X, Y = np.meshgrid(xs, xs)
    P = np.c_[X.ravel(), Y.ravel(), np.full(X.size, float(z))]
    rr = np.linalg.norm(P[:, :2], axis=1)
    return P[(rr >= r0) & (rr <= r1)]


def _cap_cloud(rim_r=3.0, rim_z=0.0, tissue_z=-1.5, keep=None):
    """A cap-like site: top face + rim ring at ``rim_z`` (screw recess r<0.8 empty),
    a short collar wall, surrounding tissue at ``tissue_z``. ``keep``: optional mask
    fn(points)->bool to carve capture defects out of the CAP surface only."""
    top = _disc(0.8, rim_r, rim_z)
    wall = np.concatenate([_disc(rim_r - 0.05, rim_r + 0.05, rim_z - dz)
                           for dz in (0.3, 0.6, 0.9)])
    cap = np.vstack([top, wall])
    if keep is not None:
        cap = cap[keep(cap)]
    tissue = _disc(rim_r + 0.4, rim_r + 4.0, tissue_z)
    return np.vstack([cap, tissue])


class TestFullRingPasses:
    def test_healthy_capture_passes_every_check(self):
        pts = _cap_cloud()
        a = assess_capture(pts, np.zeros(2), 3.0)
        assert a.verdict == "pass"
        assert a.rim_arc.verdict == "pass"
        assert a.rim_arc.value >= RIM_PASS_MIN
        assert a.code_band.verdict == "pass"
        assert a.code_band.value >= CODE_PASS_MIN
        assert a.collar.verdict == "pass"
        assert a.collar.value == pytest.approx(1.5, abs=0.2)

    def test_assessment_serializes_for_the_wire(self):
        a = assess_capture(_cap_cloud(), np.zeros(2), 3.0)
        d = a.to_dict()
        assert d["verdict"] == "pass"
        assert [c["name"] for c in d["checks"]] == [
            "rim_arc", "code_band", "collar_exposure"]
        for c in d["checks"]:
            assert set(c) == {"name", "value", "bound_pass", "bound_rescan",
                              "verdict", "message"}
            assert c["verdict"] == "pass"


class TestHalfRingRescans:
    """The standard refuses a scan without the ENTIRE cap circumference (ZVINST0206); a
    half-missing ring must gate rescan with a message naming the missing side."""

    def test_half_ring_gates_rescan(self):
        # carve every cap point on the +x side: the ring arc facing +x is gone
        pts = _cap_cloud(keep=lambda P: P[:, 0] < 0.3)
        a = assess_capture(pts, np.zeros(2), 3.0, arch_outward_xy=(1.0, 0.0))
        assert a.rim_arc.verdict == "rescan"
        assert a.rim_arc.value < RIM_RESCAN_BELOW
        assert a.verdict == "rescan"

    def test_message_names_the_missing_side_and_the_deficit(self):
        pts = _cap_cloud(keep=lambda P: P[:, 0] < 0.3)
        # +x declared as the cheek-facing (buccal) direction
        a = assess_capture(pts, np.zeros(2), 3.0, arch_outward_xy=(1.0, 0.0))
        assert "cheek-facing" in a.rim_arc.message
        assert "% of the ring is missing" in a.rim_arc.message

    def test_missing_lingual_side_is_named_too(self):
        pts = _cap_cloud(keep=lambda P: P[:, 0] < 0.3)
        # +x declared as INWARD (tongue-facing): same hole, opposite label
        a = assess_capture(pts, np.zeros(2), 3.0, arch_outward_xy=(-1.0, 0.0))
        assert "tongue-facing" in a.rim_arc.message


class TestCodeBandVisibility:
    def test_missing_code_band_gates_rescan(self):
        # top face carved out except the outer rim ring: codes unreadable, ring intact
        pts = _cap_cloud(keep=lambda P: np.linalg.norm(P[:, :2], axis=1) > 2.55)
        a = assess_capture(pts, np.zeros(2), 3.0)
        assert a.code_band.verdict == "rescan"
        assert a.code_band.value < CODE_RESCAN_BELOW
        assert "code" in a.code_band.message.lower()
        assert a.rim_arc.verdict == "pass"  # the defect is the codes, not the ring


class TestCollarExposure:
    """The standard hard-requires a 1-2mm supragingival collar (1mm minimum) around the
    whole circumference — below the floor the scan is refused (ZVINST0213)."""

    def test_submerged_collar_gates_rescan(self):
        pts = _cap_cloud(tissue_z=-0.2)  # collar pokes 0.2mm above tissue (t7-class)
        a = assess_capture(pts, np.zeros(2), 3.0)
        assert a.collar.verdict == "rescan"
        assert a.collar.value < EXPO_RESCAN_BELOW_MM
        assert a.verdict == "rescan"
        assert "supragingival" in a.collar.message

    def test_below_vendor_floor_is_marginal_not_pass(self):
        pts = _cap_cloud(tissue_z=-0.7)
        a = assess_capture(pts, np.zeros(2), 3.0)
        assert a.collar.verdict == "marginal"
        assert EXPO_RESCAN_BELOW_MM <= a.collar.value < EXPO_PASS_MIN_MM

    def test_unscanned_tissue_is_flagged_not_passed(self):
        # cap floating with no surrounding tissue captured at all — the standard requires
        # ALL soft-tissue contours; the gate must not silently pass
        pts = _cap_cloud()
        rr = np.linalg.norm(pts[:, :2], axis=1)
        a = assess_capture(pts[rr < 3.2], np.zeros(2), 3.0)
        assert a.collar.verdict == "marginal"
        assert a.collar.value is None
        assert "soft-tissue" in a.collar.message


class TestStarvedSite:
    def test_no_surface_at_the_mark_gates_rescan(self):
        rng_pts = _disc(6.0, 9.0, 0.0)  # nothing anywhere near the marked centre
        a = assess_capture(rng_pts, np.zeros(2), 3.0)
        assert a.verdict == "rescan"
        assert a.rim_arc.verdict == "rescan"


def _real_site(case_dir: str, idx: int = 0):
    import trimesh

    from case_prep.pipeline.auto_flow import _crowns_frame

    folder = REAL / "scans" / case_dir
    scan = trimesh.load(next(iter(sorted(folder.glob("*.stl")))), force="mesh")
    pts = np.asarray(scan.vertices, float)
    frame, origin, _ = _crowns_frame(pts, np.asarray(scan.vertex_normals, float))
    L = (pts - origin) @ frame
    s = json.loads((folder / "sites.json").read_text())["suggested_sites"][idx]
    seed = frame.T @ (np.asarray(s["center_mark"], float) - origin)
    rim = frame.T @ (np.asarray(s["rim_mark"], float) - origin)
    return L, seed[:2], float(np.linalg.norm((rim - seed)[:2]))


@pytest.mark.skipif(not (REAL / "scans/doctor-zimmer-4.5").exists(),
                    reason="real client scan not on this host")
class TestT7Exemplar:
    """The measured failure the gate exists for: t7 shipped with ~46% of its seat-band
    arc EMPTY scan and a submerged collar — discovered at the END of the pipeline.
    The gate must catch it at intake (master plan §1 SCAN row)."""

    def test_t7_gates_rescan_with_the_measured_deficit(self):
        L, seed_xy, rim_r = _real_site("doctor-zimmer-4.5")
        a = assess_capture(L, seed_xy, rim_r)
        assert a.verdict == "rescan"
        # the calibration receipt: ~0.54 of the seat-band arc occupied (46% empty)
        assert a.rim_arc.value == pytest.approx(0.54, abs=0.03)
        assert a.rim_arc.verdict == "rescan"
        assert a.collar.verdict == "rescan"  # measured submerged (worst on the fleet)
        assert "% of the ring is missing" in a.rim_arc.message


@pytest.mark.skipif(not (REAL / "scans/doctor-276794487-zimmer-4.5").exists(),
                    reason="real client scan not on this host")
class TestHealthySiteStaysOpen:
    @pytest.mark.slow
    def test_t3_passes_every_check(self):
        L, seed_xy, rim_r = _real_site("doctor-276794487-zimmer-4.5")
        a = assess_capture(L, seed_xy, rim_r)
        assert a.verdict == "pass"
