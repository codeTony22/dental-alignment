"""Dashboard builder smoke test — a DemoReport renders to self-contained HTML."""
from case_prep.demo.dashboard import build_dashboard
from case_prep.demo.runner import (
    DemoReport,
    ImplantRow,
    ScenarioOutcome,
    SuiteSummary,
)


def _report():
    scenario = ScenarioOutcome(
        name="Demo scenario", description="a description",
        clear_rate=1.0, false_confidence_rate=0.0, count_match=True,
        declared_count=2, detected_count=2,
        implants=[
            ImplantRow(tooth=19, retention="cement", position_error_mm=0.05,
                       axis_error_deg=0.3, clocking_error_deg=None, within_tolerance=True,
                       gate_passed=True, gate_reasons=[]),
        ],
        unresolved=[], render_path=None, meets_expectation=True,
        expectation="clear in [100%,100%]",
    )
    tests = SuiteSummary(total=2, passed=2, failed=0, duration_s=1.2, ran=True,
                        tests=[{"name": "tests/test_x.py::test_a", "outcome": "passed"},
                               {"name": "tests/test_x.py::test_b", "outcome": "passed"}])
    return DemoReport(scenarios=[scenario], test_summary=tests)


def test_dashboard_builds_self_contained_html(tmp_path):
    out = build_dashboard(_report(), tmp_path / "dashboard.html")
    html = out.read_text()
    assert html.startswith("<!doctype html>")
    assert "Demo scenario" in html
    assert "EXPECTED" in html
    assert "test_x.py" in html  # test breakdown present


def test_dashboard_flags_unmet_expectations(tmp_path):
    report = _report()
    report.scenarios[0].meets_expectation = False
    out = build_dashboard(report, tmp_path / "d.html")
    assert "UNEXPECTED" in out.read_text()
