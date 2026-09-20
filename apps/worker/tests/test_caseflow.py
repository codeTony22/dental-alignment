"""caseflow resolves a site from session.json without importing the BFF."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from case_prep.application.caseflow import (CaseNotFound, SiteUnresolved,
                                            resolve_site)
from case_prep.application.cases import CaseRecord


def _tree(tmp_path: Path):
    data = tmp_path / "data"
    (data / "library/caps/neodent-gm").mkdir(parents=True)
    (data / "library/caps/neodent-gm/part.stl").touch()
    scans = data / "scans/doctor-neodent-gm"
    scans.mkdir(parents=True)
    (scans / "upper_jaw.stl").touch()
    product = tmp_path / "product"
    run = product / "neodent-gm" / "runs" / "run-1"
    run.mkdir(parents=True)
    (product / "neodent-gm" / "session.json").write_text(json.dumps({
        "run": {"state": "done", "run_id": "run-1",
                "summary": {"sites": [{"tooth": 4, "seat_method": "rim-seat"}]}},
    }))
    return data, product


def test_resolve_site_reads_the_session_pointer(tmp_path):
    data, product = _tree(tmp_path)
    handle = resolve_site(data, product, "neodent-gm", 4)
    assert handle.run_id == "run-1"
    assert handle.row["seat_method"] == "rim-seat"
    assert handle.case.id == "neodent-gm"


def test_unknown_case_and_unaligned_tooth(tmp_path):
    data, product = _tree(tmp_path)
    with pytest.raises(CaseNotFound):
        resolve_site(data, product, "nope", 4)
    with pytest.raises(SiteUnresolved):
        resolve_site(data, product, "neodent-gm", 99)


def test_case_record_is_the_application_type(tmp_path):
    data, product = _tree(tmp_path)
    handle = resolve_site(data, product, "neodent-gm", 4)
    assert isinstance(handle.case, CaseRecord)
