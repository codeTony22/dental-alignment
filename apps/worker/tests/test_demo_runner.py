"""The demo runner aggregates scenario outcomes and self-checks each against its
stated expectation. Renders are best-effort; we assert on the data, not the pixels."""
import pytest

from case_prep.demo.runner import run_scenario
from case_prep.demo.scenarios import SCENARIOS


def _by_name(fragment):
    return next(s for s in SCENARIOS if fragment in s.name)


@pytest.mark.slow
def test_cement_scenario_meets_its_expectation(tmp_path):
    outcome = run_scenario(_by_name("Cement"), tmp_path)
    assert outcome.clear_rate == 1.0
    assert outcome.false_confidence_rate == 0.0
    assert outcome.meets_expectation
    assert len(outcome.implants) == 2


@pytest.mark.slow
def test_degraded_screw_scenario_flags_and_meets_expectation(tmp_path):
    outcome = run_scenario(_by_name("degraded"), tmp_path)
    assert outcome.clear_rate <= 0.5
    assert outcome.false_confidence_rate == 0.0
    assert outcome.meets_expectation


@pytest.mark.slow
def test_count_mismatch_scenario_is_caught(tmp_path):
    outcome = run_scenario(_by_name("Count mismatch"), tmp_path)
    assert not outcome.count_match
    assert outcome.declared_count == 3
    assert outcome.detected_count == 2
    assert len(outcome.unresolved) == 1
    assert outcome.meets_expectation
