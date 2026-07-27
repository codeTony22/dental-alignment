"""Advisory (shadow) mode — the clinical-safety policy for unvalidated data classes.

The measured problem (docs/engagement/real-data-first-run.md): the synthetic-calibrated gate
PASSED a 1.75 mm-wrong pose on real geometry. Until thresholds are validated per data class,
a case runs in ADVISORY mode: the gate still computes its decision, but auto-approval is
disabled — every implant routes to a human, and what WOULD have passed is logged (the shadow
measurement that later calibrates the gate). Fail-closed: a case that does not declare a mode
is advisory.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

from case_prep.domain.confidence import (
    ADVISORY_REASON,
    CaseMode,
    ConfidenceScore,
    GateDecision,
    GateThresholds,
    apply_case_mode,
    evaluate_gate,
)
from case_prep.domain.poses import Retention
from case_prep.manifest import CaseManifest, SiteSpec

THRESHOLDS = GateThresholds(min_fitness=0.3, max_rmse_mm=0.3,
                            min_clocking_gap=1.5, max_anti_rotation_residual=0.6)


def _passing_score() -> ConfidenceScore:
    return ConfidenceScore(icp_fitness=0.9, inlier_rmse_mm=0.05, multi_implant_consistent=True)


class TestApplyCaseMode:
    def test_validated_mode_leaves_the_decision_untouched(self):
        decision = evaluate_gate(_passing_score(), Retention.CEMENT, THRESHOLDS)
        assert decision.passed
        assert apply_case_mode(decision, CaseMode.VALIDATED) is decision

    def test_advisory_mode_never_auto_passes_and_logs_the_shadow_result(self):
        decision = evaluate_gate(_passing_score(), Retention.CEMENT, THRESHOLDS)
        routed = apply_case_mode(decision, CaseMode.ADVISORY)
        assert not routed.passed                 # auto-approval disabled
        assert routed.advisory
        assert routed.would_pass is True         # the shadow log: gate WOULD have passed
        assert ADVISORY_REASON in routed.reasons

    def test_advisory_mode_keeps_real_flags_and_their_reasons(self):
        bad = ConfidenceScore(icp_fitness=0.1, inlier_rmse_mm=0.9, multi_implant_consistent=True)
        decision = evaluate_gate(bad, Retention.CEMENT, THRESHOLDS)
        routed = apply_case_mode(decision, CaseMode.ADVISORY)
        assert not routed.passed
        assert routed.would_pass is False        # it would have flagged anyway
        assert any("fitness" in r for r in routed.reasons)  # original reasons preserved

    def test_plain_gate_decision_is_not_advisory(self):
        decision = GateDecision(passed=True, retention=Retention.CEMENT)
        assert decision.advisory is False and decision.would_pass is None


class TestManifestMode:
    def _manifest(self, **kw) -> CaseManifest:
        return CaseManifest(case_ref="c", scan_file="scan.stl",
                            implant_sites=[SiteSpec(tooth=8, scan_body_type="sb",
                                                    retention=Retention.CEMENT)], **kw)

    def test_mode_defaults_to_advisory_fail_closed(self):
        assert self._manifest().mode is CaseMode.ADVISORY

    def test_explicit_validated_mode_round_trips_through_json(self):
        m = self._manifest(mode=CaseMode.VALIDATED)
        again = CaseManifest.model_validate_json(m.model_dump_json())
        assert again.mode is CaseMode.VALIDATED

    def test_legacy_case_json_without_mode_is_advisory(self):
        raw = json.loads(self._manifest().model_dump_json())
        raw.pop("mode")
        assert CaseManifest.model_validate(raw).mode is CaseMode.ADVISORY


def test_synthetic_generator_declares_validated_mode(tmp_path):
    """Synthetic cases are the class the thresholds WERE calibrated on — they stay validated
    (otherwise every demo clear-rate silently becomes 0 and the dashboards lie)."""
    from case_prep.adapters.synthetic import SyntheticParams, generate_case

    generate_case(tmp_path, SyntheticParams(seed=1, n_implants=1))
    m = CaseManifest.model_validate_json((tmp_path / "case.json").read_text())
    assert m.mode is CaseMode.VALIDATED


class TestShadowFalseConfidence:
    """Review finding (HIGH): in advisory mode nothing auto-passes, so the classic
    false_confidence_rate structurally reads a reassuring 0% while measuring nothing. The
    evaluation must expose the SHADOW rate — computed from what the gate WOULD have passed —
    or the one safety-critical number lies on exactly the data classes advisory mode watches."""

    def _case(self, decision) -> "tuple":
        from case_prep.domain.geometry import RigidTransform
        from case_prep.domain.ground_truth import GroundTruth, ImplantTruth
        from case_prep.domain.poses import Pose6DoF
        from case_prep.domain.geometry import Axis as GAxis
        from case_prep.pipeline.orchestrator import CaseResult, RegisteredImplant

        pose = Pose6DoF(position=[1.5, 0.0, 0.0], axis=GAxis.from_vector([0, 0, 1.0]),
                        clocking_degrees=None)  # 1.5 mm OFF the truth -> out of tolerance
        reg = RegisteredImplant(8, Retention.CEMENT, "sb", pose, _passing_score(),
                                RigidTransform.identity())
        result = CaseResult(case_ref="c", declared_count=1, detected_count=1, count_match=True,
                            implants=[reg], gated=[(reg, decision)], unresolved_sites=[])
        gt = GroundTruth(poses=[ImplantTruth(tooth=8, scan_body_type="sb",
                                             retention=Retention.CEMENT,
                                             position=[0.0, 0.0, 0.0], axis=[0.0, 0.0, 1.0],
                                             clocking_degrees=None)])
        return result, gt

    def test_advisory_would_pass_on_wrong_pose_surfaces_as_shadow_false_confidence(self):
        from case_prep.domain.metrics import ClinicalTolerance
        from case_prep.pipeline.evaluation import evaluate_case

        confident = evaluate_gate(_passing_score(), Retention.CEMENT, THRESHOLDS)
        result, gt = self._case(apply_case_mode(confident, CaseMode.ADVISORY))
        ev = evaluate_case(result, gt, ClinicalTolerance(0.2, 2.0, 5.0))
        assert ev.false_confidence_rate == 0.0            # nothing auto-passed (advisory)
        assert ev.shadow_false_confidence_rate == 1.0     # but the gate WOULD have passed a wrong pose

    def test_validated_case_has_no_shadow_rate(self):
        from case_prep.domain.metrics import ClinicalTolerance
        from case_prep.pipeline.evaluation import evaluate_case

        confident = evaluate_gate(_passing_score(), Retention.CEMENT, THRESHOLDS)
        result, gt = self._case(confident)  # validated: decision used as-is
        ev = evaluate_case(result, gt, ClinicalTolerance(0.2, 2.0, 5.0))
        assert ev.shadow_false_confidence_rate is None    # not applicable
        assert ev.false_confidence_rate == 1.0            # the REAL metric catches it


@pytest.mark.slow
def test_semireal_workflow_runs_advisory_and_logs_would_pass(tmp_path):
    """End-to-end shadow mode: a semi-real case (real-arch data class — where the 1.75 mm
    false-confidence was measured) must route EVERY implant to review, carrying the shadow
    would_pass measurement, and the case state must say advisory."""
    from case_prep.adapters.real_case import build_semireal_case
    from case_prep.adapters.synthetic import make_gingiva_arch
    from case_prep.pipeline.stages import Status, run_workflow

    arch_path = tmp_path / "arch.stl"
    make_gingiva_arch(np.random.default_rng(0)).export(arch_path)
    case_dir = tmp_path / "case"
    build_semireal_case(arch_path, case_dir, n_implants=2, seed=1)

    s1, s2 = run_workflow(case_dir, tmp_path / "work", operator_seeds=True)

    assert s2 is not None and s2.status is Status.NEEDS_REVIEW
    assert s2.clear_rate == 0.0                       # advisory: nothing auto-passes
    for row in s2.implants:
        assert row["pose_origin"] == "implant-platform"  # semireal writes a real transform
        assert row["gate"] == "FLAG"
        assert row["advisory"] is True
        assert row["would_pass"] in (True, False)     # the shadow log is populated
        assert ADVISORY_REASON in row["reasons"]
