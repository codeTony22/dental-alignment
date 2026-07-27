"""Count-reconciliation safety: a mismatch between the declared site count and the
scan-bodies actually detected must FLAG (never silently drop a site or reconcile a
spurious one as confident). Guards the two false-confidence paths from review."""
import json
import pytest

from case_prep.adapters.synthetic import SyntheticParams, generate_case
from case_prep.domain.poses import Retention
from case_prep.manifest import CaseManifest, SiteSpec
from case_prep.pipeline.orchestrator import run_case


def _rewrite_sites(case_dir, sites):
    m = CaseManifest.model_validate_json((case_dir / "case.json").read_text())
    # preserve the mode: dropping it would fall back to the advisory default, where EVERYTHING
    # flags and these tests stop discriminating the count-mismatch flag from the mode (review)
    m = CaseManifest(case_ref=m.case_ref, scan_file=m.scan_file, implant_sites=sites, mode=m.mode)
    (case_dir / "case.json").write_text(m.model_dump_json(indent=2))


@pytest.mark.slow
def test_under_detection_flags_case_and_records_missing_site(tmp_path):
    # generate 2 scan bodies but declare 3 -> one site cannot be detected
    generate_case(tmp_path, SyntheticParams(seed=5, n_implants=2, retention=Retention.CEMENT))
    _rewrite_sites(tmp_path, [
        SiteSpec(tooth=19, scan_body_type="synthetic_sb", retention=Retention.CEMENT),
        SiteSpec(tooth=30, scan_body_type="synthetic_sb", retention=Retention.CEMENT),
        SiteSpec(tooth=31, scan_body_type="synthetic_sb", retention=Retention.CEMENT),
    ])
    result = run_case(tmp_path)

    assert result.declared_count == 3
    assert result.detected_count == 2
    assert not result.count_match
    # the missing declared site is surfaced, not dropped
    assert len(result.unresolved_sites) == 1
    # nothing auto-passes a count-mismatched case
    assert all(not d.passed for _, d in result.gated)


@pytest.mark.slow
def test_over_detection_breaks_count_match(tmp_path):
    # generate 3 scan bodies but declare only 2 -> a spurious extra must not reconcile
    generate_case(tmp_path, SyntheticParams(seed=7, n_implants=3, retention=Retention.CEMENT))
    _rewrite_sites(tmp_path, [
        SiteSpec(tooth=18, scan_body_type="synthetic_sb", retention=Retention.CEMENT),
        SiteSpec(tooth=19, scan_body_type="synthetic_sb", retention=Retention.CEMENT),
    ])
    result = run_case(tmp_path)

    assert result.declared_count == 2
    assert result.detected_count >= 3
    assert not result.count_match
    assert all(not d.passed for _, d in result.gated)
