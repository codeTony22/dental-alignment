"""Runs the demo scenarios + the test suite and collects an inspectable report.

This is the 'workflow' a reviewer runs to learn and check the pipeline: every scenario
is executed against ground truth, rendered, and asserted against its stated expectation.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import numpy as np

from case_prep.adapters.loader import load_case
from case_prep.adapters.render import ImplantViz, render_scenario
from case_prep.adapters.synthetic import generate_case
from case_prep.manifest import CaseManifest, SiteSpec
from case_prep.pipeline.evaluation import evaluate_case, load_ground_truth
from case_prep.pipeline.orchestrator import run_case
from case_prep.demo.scenarios import SCENARIOS, Scenario


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


@dataclass
class ImplantRow:
    tooth: int
    retention: str
    position_error_mm: float
    axis_error_deg: float
    clocking_error_deg: Optional[float]
    within_tolerance: bool
    gate_passed: bool
    gate_reasons: List[str]


@dataclass
class ScenarioOutcome:
    name: str
    description: str
    clear_rate: float
    false_confidence_rate: float
    count_match: bool
    declared_count: int
    detected_count: int
    implants: List[ImplantRow]
    unresolved: List[dict]
    render_path: Optional[Path]
    meets_expectation: bool
    expectation: str


@dataclass
class SuiteSummary:
    total: int = 0
    passed: int = 0
    failed: int = 0
    duration_s: float = 0.0
    ran: bool = False
    tests: List[dict] = field(default_factory=list)


@dataclass
class DemoReport:
    scenarios: List[ScenarioOutcome]
    test_summary: SuiteSummary

    @property
    def all_expectations_met(self) -> bool:
        return all(s.meets_expectation for s in self.scenarios)


def _append_phantom_sites(case_dir: Path, extra_teeth) -> None:
    """Over-declare one site (a tooth not already present) to force a count mismatch."""
    m = CaseManifest.model_validate_json((case_dir / "case.json").read_text())
    declared = {s.tooth for s in m.implant_sites}
    sb = m.implant_sites[0].scan_body_type
    for t in extra_teeth:
        if t not in declared:
            sites = list(m.implant_sites) + [
                SiteSpec(tooth=t, scan_body_type=sb, retention=m.implant_sites[0].retention)
            ]
            (case_dir / "case.json").write_text(
                CaseManifest(case_ref=m.case_ref, scan_file=m.scan_file,
                             implant_sites=sites, mode=m.mode).model_dump_json(indent=2)
            )
            return


def run_scenario(scenario: Scenario, work_dir) -> ScenarioOutcome:
    work_dir = Path(work_dir)
    case_dir = work_dir / "cases" / _slug(scenario.name)
    generate_case(case_dir, scenario.params)
    if scenario.extra_declared_teeth:
        _append_phantom_sites(case_dir, scenario.extra_declared_teeth)

    result = run_case(case_dir)
    gt = load_ground_truth(case_dir)
    ev = evaluate_case(result, gt, scenario.tol)

    gt_positions = np.array([p.position for p in gt.poses])
    vizs: List[ImplantViz] = []
    rows: List[ImplantRow] = []
    for (reg, _decision), ie in zip(result.gated, ev.implants):
        j = int(np.linalg.norm(gt_positions - np.asarray(reg.pose.position), axis=1).argmin())
        truth = gt.poses[j]
        vizs.append(ImplantViz(
            tooth=reg.tooth, retention=reg.retention.value,
            position=reg.pose.position, axis=reg.pose.axis.direction,
            gate_passed=ie.gate_passed,
            position_error_mm=ie.position_error_mm, axis_error_deg=ie.axis_error_deg,
            gt_position=truth.position, gt_axis=truth.axis,
        ))
        rows.append(ImplantRow(
            tooth=ie.tooth, retention=ie.retention,
            position_error_mm=ie.position_error_mm, axis_error_deg=ie.axis_error_deg,
            clocking_error_deg=ie.clocking_error_deg, within_tolerance=ie.within_tolerance,
            gate_passed=ie.gate_passed, gate_reasons=ie.gate_reasons,
        ))

    scan_points = np.asarray(load_case(case_dir).scan.vertices, float)
    title = f"{scenario.name}  —  clear {ev.clear_rate*100:.0f}% / false-confidence {ev.false_confidence_rate*100:.0f}%"
    render_path = render_scenario(scan_points, vizs, title, work_dir / "renders" / f"{_slug(scenario.name)}.png")

    meets = (
        scenario.expect_min_clear <= ev.clear_rate <= scenario.expect_max_clear
        and ev.false_confidence_rate <= scenario.expect_max_false_confidence
        and result.count_match == scenario.expect_count_match
    )
    expectation = (f"clear in [{scenario.expect_min_clear:.0%},{scenario.expect_max_clear:.0%}], "
                   f"false-confidence ≤ {scenario.expect_max_false_confidence:.0%}, "
                   f"count_match = {scenario.expect_count_match}")

    return ScenarioOutcome(
        name=scenario.name, description=scenario.description,
        clear_rate=ev.clear_rate, false_confidence_rate=ev.false_confidence_rate,
        count_match=result.count_match,
        declared_count=result.declared_count, detected_count=result.detected_count,
        implants=rows,
        unresolved=[{"tooth": u.tooth, "retention": u.retention.value, "reason": u.reason}
                    for u in result.unresolved_sites],
        render_path=render_path, meets_expectation=meets, expectation=expectation,
    )


def run_test_suite(worker_root) -> SuiteSummary:
    """Run the pytest suite and parse the JSON report (best-effort)."""
    worker_root = Path(worker_root)
    report_file = worker_root / "reports" / "_pytest-report.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONWARNINGS="ignore:::urllib3")
    try:
        subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--json-report",
             f"--json-report-file={report_file}", "-p", "no:cacheprovider"],
            cwd=str(worker_root), env=env, capture_output=True, timeout=600,
        )
    except Exception:
        return SuiteSummary(ran=False)
    if not report_file.exists():
        return SuiteSummary(ran=False)

    data = json.loads(report_file.read_text())
    summary = data.get("summary", {})
    tests = [{"name": t.get("nodeid", ""), "outcome": t.get("outcome", "")}
             for t in data.get("tests", [])]
    return SuiteSummary(
        total=summary.get("total", 0),
        passed=summary.get("passed", 0),
        failed=summary.get("failed", 0),
        duration_s=float(data.get("duration", 0.0)),
        ran=True, tests=tests,
    )


def run_demo(work_dir, worker_root, run_tests: bool = True) -> DemoReport:
    outcomes = [run_scenario(s, work_dir) for s in SCENARIOS]
    tests = run_test_suite(worker_root) if run_tests else SuiteSummary(ran=False)
    return DemoReport(scenarios=outcomes, test_summary=tests)
