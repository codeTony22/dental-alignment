"""Report writer — emits the billable artifacts: JSON + HTML accuracy report,
run manifest (traceability), and a feasibility memo."""
import json
import pytest

from case_prep.adapters.report_writer import write_report
from case_prep.adapters.synthetic import SyntheticParams, generate_case
from case_prep.domain.metrics import ClinicalTolerance
from case_prep.domain.poses import Retention
from case_prep.pipeline.evaluation import evaluate_case, load_ground_truth
from case_prep.pipeline.orchestrator import run_case

CLINICAL = ClinicalTolerance(position_mm=0.2, axis_deg=2.0, clocking_deg=5.0)


def _run(case_dir):
    generate_case(case_dir, SyntheticParams(seed=21, n_implants=2, retention=Retention.SCREW))
    result = run_case(case_dir)
    ev = evaluate_case(result, load_ground_truth(case_dir), CLINICAL)
    return result, ev


@pytest.mark.slow
def test_writes_all_artifacts(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    result, ev = _run(case_dir)
    out = tmp_path / "report"

    paths = write_report(out, result, ev)

    for name in ("accuracy-report.json", "accuracy-report.html",
                 "run-manifest.json", "feasibility-memo.md"):
        assert (out / name).exists(), name
    assert paths["json"].name == "accuracy-report.json"


@pytest.mark.slow
def test_json_report_has_headline_numbers(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    result, ev = _run(case_dir)
    out = tmp_path / "report"
    write_report(out, result, ev)

    data = json.loads((out / "accuracy-report.json").read_text())
    assert "clear_rate" in data and "false_confidence_rate" in data
    assert data["count_match"] is True
    assert len(data["implants"]) == 2
    assert "position_error_mm" in data["implants"][0]


@pytest.mark.slow
def test_manifest_records_versions_and_pipeline(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    result, ev = _run(case_dir)
    out = tmp_path / "report"
    write_report(out, result, ev)

    manifest = json.loads((out / "run-manifest.json").read_text())
    assert "pipeline_version" in manifest
    assert "dependencies" in manifest and "open3d" in manifest["dependencies"]


@pytest.mark.slow
def test_html_is_nonempty_and_mentions_case(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    result, ev = _run(case_dir)
    out = tmp_path / "report"
    write_report(out, result, ev)

    html = (out / "accuracy-report.html").read_text()
    assert result.case_ref in html
    assert "clear" in html.lower()
