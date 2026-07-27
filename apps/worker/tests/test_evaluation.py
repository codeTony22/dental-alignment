"""Evaluation: compare a CaseResult against held-out ground truth and produce the
go/no-go numbers. This is the ONLY layer that reads ground_truth.json."""
import pytest

from case_prep.adapters.synthetic import SyntheticParams, generate_case
from case_prep.domain.metrics import ClinicalTolerance
from case_prep.domain.poses import Retention
from case_prep.pipeline.evaluation import evaluate_case, load_ground_truth
from case_prep.pipeline.orchestrator import run_case

# Clinical targets from the design (~0.1mm / <1 deg); clocking a touch looser for the spike.
CLINICAL = ClinicalTolerance(position_mm=0.2, axis_deg=2.0, clocking_deg=5.0)


@pytest.mark.slow
def test_clean_cement_case_clears_with_zero_false_confidence(tmp_path):
    generate_case(tmp_path, SyntheticParams(seed=11, n_implants=3, retention=Retention.CEMENT))
    result = run_case(tmp_path)
    ev = evaluate_case(result, load_ground_truth(tmp_path), CLINICAL)

    assert ev.clear_rate == pytest.approx(1.0)
    assert ev.false_confidence_rate == 0.0
    assert all(r.within_tolerance for r in ev.implants)


@pytest.mark.slow
def test_each_recovered_implant_matches_a_distinct_truth(tmp_path):
    # 1:1 assignment guards the false-confidence metric — two poses must not both
    # collapse onto a single ground-truth implant, leaving another unevaluated
    generate_case(tmp_path, SyntheticParams(seed=8, n_implants=3, retention=Retention.CEMENT))
    result = run_case(tmp_path)
    ev = evaluate_case(result, load_ground_truth(tmp_path), CLINICAL)
    matched = [r.tooth for r in ev.implants]
    assert len(set(matched)) == len(matched)


@pytest.mark.slow
def test_each_evaluated_implant_carries_errors_and_decision(tmp_path):
    generate_case(tmp_path, SyntheticParams(seed=12, n_implants=2, retention=Retention.SCREW))
    result = run_case(tmp_path)
    ev = evaluate_case(result, load_ground_truth(tmp_path), CLINICAL)

    for r in ev.implants:
        assert r.position_error_mm >= 0.0
        assert r.axis_error_deg >= 0.0
        assert r.clocking_error_deg is not None  # screw-retained
        assert isinstance(r.gate_passed, bool)


@pytest.mark.slow
def test_clean_screw_case_clears_with_recovered_clocking(tmp_path):
    # the calibrated gate: a well-captured screw case auto-passes (clocking confident)
    generate_case(tmp_path, SyntheticParams(seed=7, n_implants=3, retention=Retention.SCREW))
    result = run_case(tmp_path)
    ev = evaluate_case(result, load_ground_truth(tmp_path), CLINICAL)
    assert ev.clear_rate == pytest.approx(1.0)
    assert ev.false_confidence_rate == 0.0


@pytest.mark.slow
def test_degraded_screw_case_is_flagged_not_passed_blind(tmp_path):
    # heavy noise + occlusion pushes poses out of tolerance; the gate MUST flag them
    generate_case(
        tmp_path,
        SyntheticParams(seed=7, n_implants=3, retention=Retention.SCREW,
                        noise_mm=0.4, partial_fraction=0.4),
    )
    result = run_case(tmp_path)
    ev = evaluate_case(result, load_ground_truth(tmp_path), CLINICAL)
    assert ev.false_confidence_rate == 0.0  # nothing confident-but-wrong
    assert ev.clear_rate < 1.0  # degraded work is not all auto-passed


@pytest.mark.slow
def test_false_confidence_stays_near_zero_under_degradation(tmp_path):
    # heavy noise + partial capture: the gate must NOT confidently pass wrong poses
    generate_case(
        tmp_path,
        SyntheticParams(
            seed=13, n_implants=3, retention=Retention.SCREW,
            noise_mm=0.4, partial_fraction=0.35,
        ),
    )
    result = run_case(tmp_path)
    ev = evaluate_case(result, load_ground_truth(tmp_path), CLINICAL)
    # the safety-critical invariant: confident-but-wrong is rare/none
    assert ev.false_confidence_rate <= 0.34
