"""Behavioral tests for the G5 pre-export design-rule gate (domain/design_rules.py).

The centrepiece is ``test_export_gate_flags_lumen_mismatch`` (master plan §7.4 G5's
named failing test): a DESS-shaped construction tube with a designed 2.00mm lumen is
run through the REAL production path (``build_final_product``), which seals the lumen
mouth, floods the lumen with invented material, and re-bores at r=1.0 — today's
measured halved-lumen defect (autopsy L8; delivered parts carry a wall band
[0.97-1.05] that exists in no vendor CAD). The gate must flag it.
"""
from pathlib import Path

import numpy as np
import pytest
import trimesh

from case_prep.adapters.ingest import canonicalize_library
from case_prep.domain.design_rules import (
    MAX_CHANNEL_ANGLE_DEG,
    MIN_WALL_MM,
    VERDICT_FAIL,
    VERDICT_FLAG,
    VERDICT_PASS,
    VERDICT_UNKNOWN,
    designed_lumen_radius,
    evaluate_site_rules,
    has_catastrophic,
    measure_product_channel,
    worst_verdict,
)
from case_prep.pipeline.final_product import build_final_product

REAL_LIBRARY = Path(__file__).resolve().parents[1] / "data" / "real" / "library"


def sealed_lumen_tube(lumen_r: float = 2.0, outer_r: float = 3.0,
                      height: float = 12.0) -> trimesh.Trimesh:
    """DESS-shaped construction fixture: a closed outer shell plus an interior lumen
    tube whose mouth opens at ONE end only (a single open boundary loop, like the
    real part's 65-edge rim). ``_cap_open_boundaries`` fans that mouth shut, the
    occupancy SDF floods the enclosed lumen, and the pipeline re-bores at r=1.0 —
    the exact mechanism of the measured defect."""
    outer = trimesh.creation.revolve(
        np.array([[0.0, height], [outer_r, height], [outer_r, 0.0], [0.0, 0.0]]),
        sections=64)
    inner = trimesh.creation.revolve(
        np.array([[0.0, height - 3.0], [lumen_r, height - 3.0], [lumen_r, 0.0]]),
        sections=64)
    return trimesh.util.concatenate([outer, inner])


@pytest.fixture(scope="module")
def construction_tube() -> trimesh.Trimesh:
    return sealed_lumen_tube()


@pytest.fixture(scope="module")
def defective_product(construction_tube) -> trimesh.Trimesh:
    """Today's ACTUAL production output on the tube — not a hand-mock of the defect."""
    return build_final_product(construction_tube)


def _check(checks, rule):
    return next(c for c in checks if c.rule == rule)


class TestLumenMatch:
    @pytest.mark.slow
    def test_export_gate_flags_lumen_mismatch(self, defective_product, construction_tube):
        # G5's named failing test: the vendor designed a 2.00mm-radius lumen; the
        # emitted part carries a 1.0mm bore (HALF the designed diameter). value =
        # emitted radius, bound = designed lumen radius, verdict = flag.
        canonical_body, _ = canonicalize_library(construction_tube)
        checks = evaluate_site_rules(defective_product, canonical_body)
        lumen = _check(checks, "channel_lumen_match")
        assert lumen.verdict == VERDICT_FLAG, (
            "the halved-lumen defect (emitted r~1.0 vs designed r=2.0) must flag, "
            f"got {lumen.verdict!r}: {lumen.message}")
        assert lumen.value == pytest.approx(1.0, abs=0.1), \
            f"emitted channel radius misread: {lumen.value}"
        assert lumen.bound == pytest.approx(2.0, abs=0.05), \
            f"designed lumen misread: {lumen.bound}"
        assert "designed lumen" in lumen.message

    def test_lumen_true_bore_passes(self, construction_tube):
        # a product whose channel matches the designed lumen (r=2.0) must pass —
        # the rule flags the defect, not the fix
        good = trimesh.creation.annulus(r_min=2.0, r_max=3.0, height=12.0, sections=64)
        canonical_body, _ = canonicalize_library(construction_tube)
        lumen = _check(evaluate_site_rules(good, canonical_body), "channel_lumen_match")
        assert lumen.verdict == VERDICT_PASS, lumen.message
        assert lumen.value == pytest.approx(2.0, abs=0.05)

    def test_unknown_when_vendor_cad_has_no_lumen_record(self):
        # a watertight construction CAD carries no boundary-loop lumen record: the
        # gate says UNKNOWN (C7 vendor-spec debt), it never guesses a reference
        product = trimesh.creation.annulus(r_min=1.0, r_max=3.0, height=10.0, sections=64)
        sealed_body = trimesh.creation.cylinder(radius=3.0, height=10.0, sections=32)
        assert designed_lumen_radius(sealed_body) is None
        lumen = _check(evaluate_site_rules(product, sealed_body), "channel_lumen_match")
        assert lumen.verdict == VERDICT_UNKNOWN
        assert lumen.value == pytest.approx(1.0, abs=0.05)
        assert lumen.bound is None

    def test_channel_absent_is_flag_not_fail(self):
        # Retention.CEMENT exists: a channel-less product is legitimate design intent,
        # so absence is surfaced for a human (flag), never a hard block (fail)
        box = trimesh.creation.box(extents=[6.0, 6.0, 8.0])
        checks = evaluate_site_rules(box, None)
        assert _check(checks, "channel_lumen_match").verdict == VERDICT_FLAG
        assert _check(checks, "min_wall_thickness").verdict == VERDICT_UNKNOWN
        assert _check(checks, "channel_angulation").verdict == VERDICT_UNKNOWN
        assert not has_catastrophic(checks)


class TestWallThickness:
    def test_thick_wall_passes(self, defective_product, construction_tube):
        canonical_body, _ = canonicalize_library(construction_tube)
        wall = _check(evaluate_site_rules(defective_product, canonical_body),
                      "min_wall_thickness")
        # outer r=3.0, bore r=1.0: the wall is ~2.0mm (SDF pitch 0.25 rounding allowed)
        assert wall.verdict == VERDICT_PASS, wall.message
        assert wall.value == pytest.approx(2.0, abs=0.2)
        assert wall.bound == MIN_WALL_MM

    def test_thin_wall_flags(self):
        # 2.0 -> 2.4mm annulus: a 0.4mm wall, under the 0.5mm 3Shape-parity minimum
        thin = trimesh.creation.annulus(r_min=2.0, r_max=2.4, height=10.0, sections=64)
        wall = _check(evaluate_site_rules(thin, None), "min_wall_thickness")
        assert wall.verdict == VERDICT_FLAG, wall.message
        assert wall.value == pytest.approx(0.4, abs=0.05)


class TestAngulation:
    def test_axial_channel_passes(self, defective_product, construction_tube):
        canonical_body, _ = canonicalize_library(construction_tube)
        ang = _check(evaluate_site_rules(defective_product, canonical_body),
                     "channel_angulation")
        assert ang.verdict == VERDICT_PASS, ang.message
        assert ang.value == pytest.approx(0.0, abs=2.0)
        assert ang.bound == MAX_CHANNEL_ANGLE_DEG

    def test_over_max_angulation_flags(self):
        # a 30 deg channel exceeds the 20 deg exocad-convention default maximum
        tilted = trimesh.creation.annulus(r_min=1.0, r_max=4.0, height=14.0, sections=64)
        tilted.apply_transform(
            trimesh.transformations.rotation_matrix(np.radians(30.0), [1.0, 0.0, 0.0]))
        ang = _check(evaluate_site_rules(tilted, None), "channel_angulation")
        assert ang.verdict == VERDICT_FLAG, ang.message
        assert ang.value == pytest.approx(30.0, abs=3.0)


class TestSealCensus:
    def test_watertight_single_body_passes(self, defective_product):
        seal = _check(evaluate_site_rules(defective_product, None), "seal_census")
        assert seal.verdict == VERDICT_PASS, seal.message

    def test_fragmented_part_is_catastrophic(self):
        two = trimesh.util.concatenate([
            trimesh.creation.box(extents=[4.0, 4.0, 8.0]),
            trimesh.creation.box(extents=[4.0, 4.0, 8.0]).apply_translation([10.0, 0.0, 0.0]),
        ])
        checks = evaluate_site_rules(two, None)
        seal = _check(checks, "seal_census")
        assert seal.verdict == VERDICT_FAIL
        assert seal.value == 2.0
        assert has_catastrophic(checks)
        assert worst_verdict(checks) == VERDICT_FAIL

    def test_unsealed_part_is_catastrophic(self):
        box = trimesh.creation.box(extents=[6.0, 6.0, 8.0])
        holey = trimesh.Trimesh(vertices=box.vertices.copy(),
                                faces=box.faces[:-2].copy(), process=False)
        checks = evaluate_site_rules(holey, None)
        assert _check(checks, "seal_census").verdict == VERDICT_FAIL
        assert has_catastrophic(checks)


class TestChannelMeasurement:
    def test_measures_todays_bore_where_it_is(self, defective_product):
        ch = measure_product_channel(defective_product)
        assert ch is not None
        # the SDF bore lands within pitch-rounding of the asked r=1.0 (measured
        # 0.995-0.998 in the rehearsal probes)
        assert ch.radius_mm == pytest.approx(1.0, abs=0.05)
        assert ch.n_sections == 5
        assert ch.axis is not None and ch.axis[2] > 0.99
        # deterministic: same mesh, same read, bit-for-bit
        again = measure_product_channel(defective_product)
        assert again.radius_mm == ch.radius_mm
        assert again.min_wall_mm == ch.min_wall_mm

    def test_no_channel_in_a_solid(self):
        assert measure_product_channel(trimesh.creation.box(extents=[6, 6, 8])) is None


@pytest.mark.skipif(not REAL_LIBRARY.is_dir(), reason="real library not present")
class TestRealVendorParts:
    def test_designed_lumen_reads_dess_2mm(self):
        # the DESS construction part carries its designed lumen EXACTLY: r=2.00mm,
        # coaxial <= 0.026 (autopsy L4) — the gate's reference must read it
        dess = trimesh.load(
            REAL_LIBRARY / "construction" / "dess" / "neodent-gm-scanbody.stl",
            force="mesh")
        canonical, _ = canonicalize_library(dess)
        assert designed_lumen_radius(canonical) == pytest.approx(2.0, abs=0.02)
