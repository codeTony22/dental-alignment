"""Accuracy metrics: per-implant pose error vs ground truth, and the aggregate
go/no-go numbers (clear-rate, false-confidence-rate) that gate Phase 2."""
import pytest

from case_prep.domain.geometry import Axis
from case_prep.domain.metrics import (
    ClinicalTolerance,
    ImplantOutcome,
    axis_error_deg,
    clear_rate,
    clocking_error_deg,
    false_confidence_rate,
    position_error_mm,
    within_tolerance,
)


def test_position_error_is_euclidean_distance_mm():
    assert position_error_mm([0, 0, 0], [0, 3, 4]) == pytest.approx(5.0)


def test_axis_error_is_angle_in_degrees():
    a = Axis.from_vector([0, 0, 1])
    b = Axis.from_vector([0, 1, 1])
    assert axis_error_deg(a, b) == pytest.approx(45.0)


def test_clocking_error_wraps_circularly():
    # 350 deg vs 10 deg are 20 deg apart, not 340
    assert clocking_error_deg(350.0, 10.0) == pytest.approx(20.0)
    assert clocking_error_deg(10.0, 350.0) == pytest.approx(20.0)


def test_clocking_error_none_when_no_clocking():
    # cement-retained: clocking is irrelevant, comparison yields None
    assert clocking_error_deg(None, None) is None


TOL = ClinicalTolerance(position_mm=0.1, axis_deg=1.0, clocking_deg=2.0)


def test_within_tolerance_true_when_all_under_limits():
    assert within_tolerance(pos_mm=0.05, axis_deg=0.3, clocking_deg=0.8, tol=TOL)


def test_within_tolerance_false_when_position_exceeds():
    assert not within_tolerance(pos_mm=0.5, axis_deg=0.3, clocking_deg=0.8, tol=TOL)


def test_within_tolerance_ignores_clocking_when_absent():
    # cement case (clocking None) is in-tolerance on position+axis alone
    assert within_tolerance(pos_mm=0.05, axis_deg=0.3, clocking_deg=None, tol=TOL)


def test_clear_rate_is_fraction_of_passed():
    outcomes = [
        ImplantOutcome(passed=True, within_tolerance=True),
        ImplantOutcome(passed=True, within_tolerance=True),
        ImplantOutcome(passed=False, within_tolerance=False),
        ImplantOutcome(passed=False, within_tolerance=True),
    ]
    assert clear_rate(outcomes) == pytest.approx(0.5)


def test_false_confidence_rate_is_passed_but_wrong_over_passed():
    # 3 passed, 1 of them actually out of tolerance -> 1/3
    outcomes = [
        ImplantOutcome(passed=True, within_tolerance=True),
        ImplantOutcome(passed=True, within_tolerance=True),
        ImplantOutcome(passed=True, within_tolerance=False),  # confident but wrong
        ImplantOutcome(passed=False, within_tolerance=False),
    ]
    assert false_confidence_rate(outcomes) == pytest.approx(1 / 3)


def test_false_confidence_rate_zero_when_nothing_passed():
    outcomes = [ImplantOutcome(passed=False, within_tolerance=False)]
    assert false_confidence_rate(outcomes) == 0.0


def test_rates_handle_empty_gracefully():
    assert clear_rate([]) == 0.0
    assert false_confidence_rate([]) == 0.0
