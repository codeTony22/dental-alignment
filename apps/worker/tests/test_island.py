"""The ISLAND (master plan slice 6): machine segmentation of the cap-only region.

Unit tests run on a deterministic synthetic cap+gingiva cloud (no real data, no RNG in
the geometry). The integration test at the bottom runs one real site and proves the
walking skeleton's core contract: the shadow row exists AND the shipped pose is
byte-identical with the shadow on or off — the island measures, it never moves.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from case_prep.domain.island import (IslandReading, coverage_band, segment_island,
                                     union_safe_mask)

TRUE_CENTRE = np.array([1.3, -0.7])
TRUE_RIM_R = 2.5
TRUE_RIM_Z = 3.0


def _ring(r: float, z: float, step: float = 0.12) -> np.ndarray:
    n = max(int(round(2 * np.pi * r / step)), 8)
    th = np.arange(n) * 2 * np.pi / n
    return np.c_[TRUE_CENTRE[0] + r * np.cos(th), TRUE_CENTRE[1] + r * np.sin(th),
                 np.full(n, z)]


def cap_and_gingiva_cloud(centre=TRUE_CENTRE, rim_r=TRUE_RIM_R,
                          rim_z=TRUE_RIM_Z) -> np.ndarray:
    """Deterministic polar/grid sampling of the anatomy the segmentation reads: a flat
    cap top with an empty screw recess (the closed level ring + void core that locks
    the centre), a short wall, an unscanned sulcus gap, and flat gingiva beyond it."""
    cx, cy = centre
    pts = []
    for r in np.arange(0.75, rim_r + 1e-9, 0.1):  # cap top annulus (recess r<0.7 empty)
        n = max(int(round(2 * np.pi * r / 0.12)), 8)
        th = np.arange(n) * 2 * np.pi / n
        pts.append(np.c_[cx + r * np.cos(th), cy + r * np.sin(th), np.full(n, rim_z)])
    for r in np.arange(0.1, 0.65, 0.15):  # recess floor, below the evidence slab
        n = max(int(round(2 * np.pi * r / 0.2)), 6)
        th = np.arange(n) * 2 * np.pi / n
        pts.append(np.c_[cx + r * np.cos(th), cy + r * np.sin(th),
                         np.full(n, rim_z - 2.0)])
    for z in np.arange(rim_z - 1.0, rim_z - 0.05, 0.25):  # wall below the rim edge
        n = int(round(2 * np.pi * rim_r / 0.25))
        th = np.arange(n) * 2 * np.pi / n
        pts.append(np.c_[cx + rim_r * np.cos(th), cy + rim_r * np.sin(th),
                         np.full(n, z)])
    g = np.arange(-8.0, 8.01, 0.2)  # gingiva beyond the sulcus data gap
    gx, gy = np.meshgrid(g, g)
    gx, gy = gx.ravel() + cx, gy.ravel() + cy
    keep = np.hypot(gx - cx, gy - cy) > rim_r + 0.7
    pts.append(np.c_[gx[keep], gy[keep], np.zeros(int(keep.sum()))])
    return np.vstack(pts)


def test_recovers_planted_centre_from_a_degraded_seed():
    """The design margin the whole plan rides on: a seed 0.8mm off (the measured click
    tolerance) must still converge onto the planted centre with sub-0.1mm error."""
    cloud = cap_and_gingiva_cloud()
    seed = TRUE_CENTRE + 0.8 * np.array([np.cos(0.65), np.sin(0.65)])
    reading = segment_island(cloud, seed, radius_hint=TRUE_RIM_R)

    assert reading.converged, f"refused a clean cap: {reading.reason}"
    err = float(np.linalg.norm(np.asarray(reading.centre_xy) - TRUE_CENTRE))
    assert err < 0.1, f"machine centre {err:.3f}mm from the planted centre"
    assert abs(reading.radius - TRUE_RIM_R) < 0.35, (
        f"machine rim radius {reading.radius:.2f} vs planted {TRUE_RIM_R}")
    assert reading.bins_hit >= 40  # boundary closed nearly the whole compass


def test_union_safe_mask_never_removes_template_explained_points():
    """The measured over-crop defect (probe fleet: 53-83% of cap points lost on the
    submerged caps cap6020/7020/7030): the geometric boundary excludes cap surface the
    posed template explains. The production mask is UNION-SAFE — a template-explained
    point is NEVER classified non-island, however far outside the geometric boundary."""
    cloud = cap_and_gingiva_cloud()
    seed = TRUE_CENTRE + 0.8 * np.array([np.cos(0.65), np.sin(0.65)])
    reading = segment_island(cloud, seed, radius_hint=TRUE_RIM_R)
    assert reading.converged

    # a submerged flank: points OUTSIDE the geometric island (beyond the boundary
    # radius AND deep below the rim plane) that the posed template would explain
    th = np.arange(24) * 2 * np.pi / 24
    flank_r = reading.island_r + 1.0
    flank = np.c_[TRUE_CENTRE[0] + flank_r * np.cos(th),
                  TRUE_CENTRE[1] + flank_r * np.sin(th),
                  np.full(24, TRUE_RIM_Z - 2.5)]
    pts = np.vstack([cloud, flank])
    flank_idx = np.arange(len(cloud), len(pts))

    nothing = np.zeros(len(pts), bool)
    geo_only = union_safe_mask(pts, reading, explained=nothing)
    assert not geo_only[flank_idx].any(), (
        "fixture broken: the flank must sit outside the geometric island")

    explained = nothing.copy()
    explained[flank_idx] = True  # the template explains the submerged flank
    mask = union_safe_mask(pts, reading, explained=explained)
    assert mask[flank_idx].all(), (
        "union-safety violated: template-explained points were classified non-island")
    # and the union did not stop the geometric part doing its job elsewhere
    assert (mask & ~explained).sum() == geo_only.sum()


def test_union_safe_mask_refuses_unconverged_readings():
    """No partially-trusted islands: an unconverged reading has no mask to give."""
    unconv = IslandReading(converged=False, reason="weak_recess_evidence")
    with pytest.raises(ValueError):
        union_safe_mask(np.zeros((5, 3)), unconv, explained=np.zeros(5, bool))


def test_starved_cloud_is_reported_unconverged():
    """The t7 failure class (machine 2.04mm off on a badly-scanned cap) must be REFUSED,
    never silently wrong. A cloud too sparse to close any level ring has no recess
    evidence anywhere — the reading says so."""
    rr = np.linspace(0.3, 5.0, 30)
    th = np.linspace(0.0, 4 * np.pi, 30)
    sparse = np.c_[rr * np.cos(th), rr * np.sin(th), np.linspace(0, 2, 30)]
    reading = segment_island(sparse, np.zeros(2), radius_hint=2.5)
    assert not reading.converged
    assert reading.reason == "no_recess_evidence"
    assert reading.centre_xy is None  # no trusted centre leaves an unconverged reading


def test_featureless_plane_is_refused_for_weak_evidence():
    """A flat plane closes level rings everywhere but has no empty recess (core density
    == ring density, ratio ~1) — refused by the evidence-quality gate, with the honest
    reason, not a misleading geometric one."""
    g = np.arange(-6.0, 6.01, 0.25)
    gx, gy = np.meshgrid(g, g)
    flat = np.c_[gx.ravel(), gy.ravel(), np.zeros(gx.size)]
    reading = segment_island(flat, np.zeros(2), radius_hint=2.5)
    assert not reading.converged
    assert reading.reason == "weak_recess_evidence"


def test_far_locked_centre_is_refused_by_the_seed_gate():
    """The cap7020 defect class: the recess-evidence landscape can lock onto a structure
    over 1.2mm from the locator seed (measured: 1.35-1.57mm lock, 1.54mm shipped-centre
    error; BOTH strict and plane fits were wrong, so no chooser fixes it). A machine
    centre that contradicts the locator is refused, never trusted."""
    cloud = cap_and_gingiva_cloud()
    seed = TRUE_CENTRE + np.array([1.4, -0.9])  # a seed 1.66mm off the only cap around
    reading = segment_island(cloud, seed, radius_hint=TRUE_RIM_R)
    assert not reading.converged
    assert reading.reason == "centre_seed_disagreement"
    assert reading.centre_from_seed_mm > 1.2


def test_radius_falling_short_of_the_hint_is_refused():
    """The t7 signature (machine extents 1.51/2.40mm against a 3.62mm human hint,
    alongside a 2.04mm centre error): when BOTH extent instruments (rim Kasa and
    boundary march) fall >0.8mm short of the independent radius hint, the machine
    locked onto the wrong, smaller structure. (One instrument under-reading alone is
    a measured cap behaviour — code steps, submergence — and must not refuse.)"""
    cloud = cap_and_gingiva_cloud()
    seed = TRUE_CENTRE + 0.8 * np.array([np.cos(0.65), np.sin(0.65)])
    reading = segment_island(cloud, seed, radius_hint=3.9)  # cap is really r=2.5
    assert not reading.converged
    assert reading.reason == "radius_hint_disagreement"
    assert max(reading.radius, reading.island_r) < 3.9 - 0.8


def test_segment_island_preserves_global_rng_state_and_is_deterministic():
    """House rule: no ambient RNG draws mid-pipeline. The segmentation must neither
    consume nor perturb numpy's global stream (the pinned stream feeds every stage
    after it in run_auto_case), and identical inputs must give identical readings."""
    cloud = cap_and_gingiva_cloud()
    seed = TRUE_CENTRE + 0.8 * np.array([np.cos(0.65), np.sin(0.65)])

    np.random.seed(1234)
    before = np.random.get_state()
    a = segment_island(cloud, seed, radius_hint=TRUE_RIM_R)
    after = np.random.get_state()
    assert all(np.array_equal(x, y) for x, y in zip(before, after)), (
        "segment_island moved the global RNG state")

    np.random.seed(999)  # different ambient state must not change the reading
    b = segment_island(cloud, seed, radius_hint=TRUE_RIM_R)
    assert a == b, "identical inputs gave different readings"


# ---------------------------------------------------------------------------------
# Iteration 1 of the DR1 timebox (2026-07-24): the three named segmentation defects
# ---------------------------------------------------------------------------------


def code_step_cap_cloud(step0=1.7, step1=2.1, step_drop=0.6) -> np.ndarray:
    """The cap6030 anatomy: a cap top with an inner CODE-STEP ring (a dropped band
    that breaks level-ring closure between the inner plateau and the true rim), wall,
    sulcus gap, gingiva. The single-phase edge scan is grid-phase-bistable here —
    the closed-run selection flips between the inner plateau and the true rim."""
    pts = [_ring(r, TRUE_RIM_Z - (step_drop if step0 <= r < step1 else 0.0))
           for r in np.arange(0.75, TRUE_RIM_R + 1e-9, 0.1)]
    for r in np.arange(0.1, 0.65, 0.15):
        pts.append(_ring(r, TRUE_RIM_Z - 2.0, step=0.2))
    for z in np.arange(TRUE_RIM_Z - 1.0, TRUE_RIM_Z - 0.05, 0.25):
        pts.append(_ring(TRUE_RIM_R, z, step=0.25))
    g = np.arange(-8.0, 8.01, 0.2)
    gx, gy = np.meshgrid(g, g)
    gx, gy = gx.ravel() + TRUE_CENTRE[0], gy.ravel() + TRUE_CENTRE[1]
    keep = np.hypot(gx - TRUE_CENTRE[0], gy - TRUE_CENTRE[1]) > TRUE_RIM_R + 0.7
    pts.append(np.c_[gx[keep], gy[keep], np.zeros(int(keep.sum()))])
    return np.vstack(pts)


def test_code_step_ring_no_longer_under_reads_the_radius():
    """DEFECT 1 (cap6030, the catastrophe): the single-phase Kasa read this anatomy at
    1.54 on a true 2.5 rim (the shipped 1.81-on-2.68 under-read that flipped the seat
    to ICP and lost the codes). The multi-phase median radius must read the true rim,
    and the march must not stop at the code step either (old island_r 1.8)."""
    cloud = code_step_cap_cloud()
    seed = TRUE_CENTRE + 0.8 * np.array([np.cos(0.65), np.sin(0.65)])
    reading = segment_island(cloud, seed, radius_hint=TRUE_RIM_R)

    assert reading.converged, f"refused the code-step cap: {reading.reason}"
    assert abs(reading.radius - TRUE_RIM_R) < 0.35, (
        f"radius {reading.radius:.2f} vs true {TRUE_RIM_R} — inner-ring lock")
    assert reading.island_r > 2.2, (
        f"island_r {reading.island_r:.2f} — the march stopped at the code step")
    # the bistability is REPORTED, not hidden: the phase pool disagrees with itself
    assert reading.radius_spread_mm is not None and reading.radius_spread_mm > 0.3


def test_interior_engraving_dip_no_longer_over_crops():
    """DEFECT 3 (cap6020): a shallow engraving dip on the cap top (here 0.3mm deep at
    1.7-1.9mm) used to terminate the march inside the rim (island_r 1.8 on a 2.5 rim —
    75% of the cap's own points cropped). The march now starts just inside the
    measured rim, so the interior dip is never a candidate boundary."""
    cloud = cap_and_gingiva_cloud()
    # carve the engraving dip into the cap top (replace the affected annulus rings)
    rr = np.hypot(cloud[:, 0] - TRUE_CENTRE[0], cloud[:, 1] - TRUE_CENTRE[1])
    on_top = (cloud[:, 2] > TRUE_RIM_Z - 0.01) & (rr >= 1.7) & (rr < 1.9)
    cloud = cloud.copy()
    cloud[on_top, 2] -= 0.3
    seed = TRUE_CENTRE + 0.8 * np.array([np.cos(0.65), np.sin(0.65)])
    reading = segment_island(cloud, seed, radius_hint=TRUE_RIM_R)

    assert reading.converged, f"refused the engraved cap: {reading.reason}"
    assert reading.island_r > 2.2, (
        f"island_r {reading.island_r:.2f} — the march still over-crops at the dip")
    assert abs(reading.radius - TRUE_RIM_R) < 0.35


def test_submerged_cap_without_crevice_is_refused_not_over_cropped():
    """DEFECT 3, the truly-submerged variant (cap6020's measured state): tissue laps
    flush below the rim with NO crevice signature — after the start fix the march
    loses the trail in every bin (the real site: 28/48 bins ran to 4.05 on a 2.49
    rim). The reading must REFUSE as open_boundary, never converge on a fabricated
    extent (the old code converged with island_r 1.8 and silently cropped the cap)."""
    pts = [_ring(r, TRUE_RIM_Z - (0.3 if 1.7 <= r < 1.9 else 0.0))
           for r in np.arange(0.75, TRUE_RIM_R + 1e-9, 0.1)]
    for r in np.arange(0.1, 0.65, 0.15):
        pts.append(_ring(r, TRUE_RIM_Z - 2.0, step=0.2))
    for r in np.arange(TRUE_RIM_R + 0.1, 7.5, 0.12):  # flush tissue, no crevice
        pts.append(_ring(r, TRUE_RIM_Z - 0.5, step=0.15))
    cloud = np.vstack(pts)
    seed = TRUE_CENTRE + 0.8 * np.array([np.cos(0.65), np.sin(0.65)])
    reading = segment_island(cloud, seed, radius_hint=2.78)

    assert not reading.converged
    assert reading.reason == "open_boundary"


def test_coverage_band_clips_the_sulcus_wall():
    """DEFECT 2: the coverage gate's band used the full 2mm membership depth and
    counted sulcus wall against the cap (healthy fleet sites read 0.62-0.72, a
    whisker over the 0.60 gate). The band stops at the march's own below-the-island
    threshold: points 1.2mm under the rim plane are OUT of the band (they are still
    island MEMBERS — the permissive mask is a different, union-safe instrument)."""
    cloud = cap_and_gingiva_cloud()
    seed = TRUE_CENTRE + 0.8 * np.array([np.cos(0.65), np.sin(0.65)])
    reading = segment_island(cloud, seed, radius_hint=TRUE_RIM_R)
    assert reading.converged

    a, b, c = reading.plane
    xy = TRUE_CENTRE + np.array([1.0, 0.0])
    z0 = xy[0] * a + xy[1] * b + c  # rim-plane height at that xy

    def probe(dz, dxy=np.zeros(2)):
        p = np.array([[xy[0] + dxy[0], xy[1] + dxy[1], z0 + dz]])
        return bool(coverage_band(p, reading)[0])

    assert probe(-0.3), "cap top just under the plane must be IN the band"
    assert not probe(-1.2), "sulcus wall (1.2mm below the plane) must be OUT"
    far = np.array([reading.island_r + 1.0, 0.0])
    assert not probe(0.0, dxy=far), "outside the island extent must be OUT"

    with pytest.raises(ValueError):
        coverage_band(np.zeros((2, 3)),
                      IslandReading(converged=False, reason="open_boundary"))


# ---------------------------------------------------------------------------------
# Integration: one real site, the zero-pose-movement contract
# ---------------------------------------------------------------------------------

_SCANS = Path(__file__).resolve().parents[1] / "data/real/scans"
_CASE = "doctor-cap6030-neodent-gm"  # single-site case, best machine performer


@pytest.mark.skipif(not (_SCANS / _CASE / "sites.json").exists(),
                    reason="real clinical scans not present (gitignored)")
@pytest.mark.slow
def test_shadow_island_row_present_and_pose_byte_identical_without_it():
    """THE WALKING-SKELETON CONTRACT (master plan slice 6): the production run reports
    the island in the site row, and the shipped pose is byte-identical with the shadow
    disabled — the island measures next to the pose, it never moves it."""
    import trimesh

    from case_prep.adapters.cap_library import CapLibrary
    from case_prep.pipeline import auto_flow
    from case_prep.pipeline.auto_flow import ConfirmedSite, run_auto_case

    folder = _SCANS / _CASE
    scan = trimesh.load(next(folder.glob("*.stl")), force="mesh")
    lib = CapLibrary.load(_SCANS.parents[0] / "library/caps/neodent-gm")
    vendor_dir = next((_SCANS.parents[0] / "library/construction").glob(
        "*/neodent-gm-scanbody.stl"))
    sites = json.loads((folder / "sites.json").read_text())["suggested_sites"]
    confirmed = [ConfirmedSite(s["tooth"], tuple(s["center"]),
                               s.get("declared_variant"),
                               center_mark=s.get("center_mark"),
                               rim_mark=s.get("rim_mark"),
                               rim_points=s.get("rim_points")) for s in sites]

    def one_run(shadow_on, monkey=None):
        out = Path(tempfile.mkdtemp()) / "out"
        if monkey is not None:
            monkey.setattr(auto_flow, "SHADOW_ISLAND", shadow_on)
        summary = run_auto_case(
            case_id="isl", scan=scan, library=lib,
            construction_mesh=trimesh.load(vendor_dir, force="mesh"),
            vendor=vendor_dir.parent.name, confirmed=confirmed, jaw_label="x",
            out_dir=out, generate_product=False, render_qc=False)
        poses = {s["tooth"]: json.loads(
            (out / f"isl-{s['tooth']}-implant.json").read_text())["pose_matrix"]
            for s in sites}
        return summary, poses

    with pytest.MonkeyPatch.context() as mp:
        with_shadow, poses_on = one_run(True, mp)
    with pytest.MonkeyPatch.context() as mp:
        without, poses_off = one_run(False, mp)

    # the shadow row exists and carries the contract fields
    for row in with_shadow["sites"]:
        assert "island" in row, "shadow island field missing from the site row"
        isl = row["island"]
        assert isl["converged"] in (True, False)
        if isl["converged"]:
            assert set(isl) == {"machine_centre_offset_mm", "radius", "converged",
                                "bins_hit", "contamination_est"}
        else:
            assert "reason" in isl
    assert all("island" not in row for row in without["sites"]), (
        "shadow off must mean shadow absent — no half-disabled state")

    # ZERO POSE MOVEMENT: the shipped pose is byte-identical with the shadow on or off
    assert poses_on == poses_off, (
        "the shadow island moved a shipped pose — the walking-skeleton contract is broken")
