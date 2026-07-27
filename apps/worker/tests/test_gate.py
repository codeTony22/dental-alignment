"""Retention-aware confidence gate: auto-PASS confident implants, FLAG ambiguous ones.

The gate is deterministic and explainable (per system-design 6.7) — not a model.
Cement-retained sites are evaluated on position+axis only; screw-retained sites
additionally face the hard clocking gates.
"""
import pytest

from case_prep.domain.confidence import ConfidenceScore, GateThresholds, evaluate_gate
from case_prep.domain.poses import Retention

THRESH = GateThresholds(
    min_fitness=0.8,
    max_rmse_mm=0.1,
    min_clocking_gap=1.5,  # clocking_gap is a best-vs-antipodal RMSE ratio
    max_anti_rotation_residual=0.08,
)


def _good_position_axis(**overrides):
    base = dict(
        icp_fitness=0.95,
        inlier_rmse_mm=0.04,
        multi_implant_consistent=True,
        clocking_gap=None,
        anti_rotation_residual=None,
    )
    base.update(overrides)
    return ConfidenceScore(**base)


def test_cement_passes_on_good_position_and_axis_without_clocking():
    score = _good_position_axis()
    decision = evaluate_gate(score, Retention.CEMENT, THRESH)
    assert decision.passed
    assert decision.retention is Retention.CEMENT


def test_cement_ignores_missing_clocking_signals():
    # cement has no clocking fields at all; that must not flag it
    score = _good_position_axis(clocking_gap=None, anti_rotation_residual=None)
    assert evaluate_gate(score, Retention.CEMENT, THRESH).passed


def test_low_fitness_flags_any_retention():
    score = _good_position_axis(icp_fitness=0.5)
    decision = evaluate_gate(score, Retention.CEMENT, THRESH)
    assert not decision.passed
    assert any("fitness" in r for r in decision.reasons)


def test_high_rmse_flags():
    score = _good_position_axis(inlier_rmse_mm=0.5)
    assert not evaluate_gate(score, Retention.CEMENT, THRESH).passed


def test_multi_implant_inconsistency_flags():
    score = _good_position_axis(multi_implant_consistent=False)
    decision = evaluate_gate(score, Retention.CEMENT, THRESH)
    assert not decision.passed
    assert any("consisten" in r for r in decision.reasons)


def test_screw_passes_only_with_confident_clocking():
    score = _good_position_axis(clocking_gap=2.5, anti_rotation_residual=0.02)
    assert evaluate_gate(score, Retention.SCREW, THRESH).passed


def test_screw_flags_on_ambiguous_clocking_gap():
    # good position/axis but best vs antipodal rotation fit nearly equally -> symmetry ambiguity
    score = _good_position_axis(clocking_gap=1.05, anti_rotation_residual=0.02)
    decision = evaluate_gate(score, Retention.SCREW, THRESH)
    assert not decision.passed
    assert any("clocking" in r for r in decision.reasons)


def test_screw_flags_when_clocking_signals_absent():
    # a screw case MUST have clocking evidence; absence is a flag, never a silent pass
    score = _good_position_axis(clocking_gap=None, anti_rotation_residual=None)
    assert not evaluate_gate(score, Retention.SCREW, THRESH).passed


def test_non_finite_signal_fails_closed():
    # a NaN/inf confidence signal must FLAG, never satisfy a threshold by accident
    score = _good_position_axis(icp_fitness=float("nan"))
    decision = evaluate_gate(score, Retention.CEMENT, THRESH)
    assert not decision.passed
    assert any("finite" in r for r in decision.reasons)


def test_decision_always_carries_a_reason_when_flagged():
    score = _good_position_axis(icp_fitness=0.1)
    decision = evaluate_gate(score, Retention.CEMENT, THRESH)
    assert decision.reasons  # non-empty
