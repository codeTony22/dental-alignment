"""Keystone: the full count -> localize -> align -> 6-DoF pose -> gate chain on
synthetic cases with held-out ground truth. This is the de-risk proof for Phase 2.

Recovered implants are matched to ground truth by nearest platform position, so the
accuracy assertion tests the *geometry* independent of the tooth-labeling heuristic.
"""
import numpy as np
import pytest

from case_prep.adapters.synthetic import SyntheticParams, generate_case
from case_prep.domain.geometry import Axis
from case_prep.domain.ground_truth import GroundTruth
from case_prep.domain.metrics import axis_error_deg, position_error_mm
from case_prep.domain.poses import Retention
from case_prep.pipeline.orchestrator import run_case


def _match_to_truth(impl, gt: GroundTruth):
    positions = np.array([p.position for p in gt.poses])
    j = int(np.linalg.norm(positions - np.asarray(impl.pose.position), axis=1).argmin())
    return gt.poses[j]


@pytest.mark.slow
def test_count_reconciles_with_declaration(tmp_path):
    generate_case(tmp_path, SyntheticParams(seed=5, n_implants=2))
    result = run_case(tmp_path)
    assert result.detected_count == result.declared_count == 2
    assert result.count_match


@pytest.mark.slow
def test_recovers_cement_position_and_axis_within_bounds(tmp_path):
    gt = generate_case(tmp_path, SyntheticParams(seed=5, n_implants=2, retention=Retention.CEMENT))
    result = run_case(tmp_path)
    assert len(result.implants) == 2
    for reg in result.implants:
        truth = _match_to_truth(reg, gt)
        # CI regression bounds (deterministic, seeded) — looser than clinical targets
        assert position_error_mm(reg.pose.position, truth.position) < 0.5
        assert axis_error_deg(reg.pose.axis, Axis.from_vector(truth.axis)) < 3.0


@pytest.mark.slow
def test_cement_carries_no_clocking(tmp_path):
    generate_case(tmp_path, SyntheticParams(seed=2, n_implants=1, retention=Retention.CEMENT))
    result = run_case(tmp_path)
    assert result.implants[0].pose.clocking_degrees is None


@pytest.mark.slow
def test_screw_recovers_clocking_within_bounds(tmp_path):
    from case_prep.domain.metrics import clocking_error_deg

    gt = generate_case(tmp_path, SyntheticParams(seed=4, n_implants=1, retention=Retention.SCREW))
    result = run_case(tmp_path)
    reg = result.implants[0]
    truth = _match_to_truth(reg, gt)
    err = clocking_error_deg(reg.pose.clocking_degrees, truth.clocking_degrees)
    assert err is not None
    assert err < 10.0  # clean-scan clocking recovery; the gate guards the ambiguous cases


@pytest.mark.slow
def test_every_implant_gets_a_gate_decision(tmp_path):
    generate_case(tmp_path, SyntheticParams(seed=7, n_implants=3, retention=Retention.CEMENT))
    result = run_case(tmp_path)
    assert len(result.gated) == 3
    for reg, decision in result.gated:
        assert decision.retention is reg.retention
        assert isinstance(decision.passed, bool)
