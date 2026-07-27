"""The case manifest — the structured-intake contract that mirrors schema.sql's
implant_sites and bridges a portal case straight into the pipeline."""
import json

import pytest

from case_prep.domain.poses import Retention
from case_prep.manifest import CaseManifest, SiteSpec


def test_manifest_round_trips_through_json():
    manifest = CaseManifest(
        case_ref="abc-123",
        tooth_notation="universal",
        scan_file="scan.stl",
        implant_sites=[
            SiteSpec(tooth=19, scan_body_type="atlantis_x", retention=Retention.CEMENT),
            SiteSpec(tooth=30, scan_body_type="atlantis_x", retention=Retention.SCREW),
        ],
    )
    restored = CaseManifest.model_validate_json(manifest.model_dump_json())
    assert restored == manifest


def test_retention_parses_from_string():
    manifest = CaseManifest.model_validate(
        {
            "case_ref": "c1",
            "scan_file": "scan.stl",
            "implant_sites": [
                {"tooth": 14, "scan_body_type": "atlantis_x", "retention": "screw"}
            ],
        }
    )
    assert manifest.implant_sites[0].retention is Retention.SCREW


def test_declared_count_matches_site_rows():
    manifest = CaseManifest(
        case_ref="c2",
        scan_file="scan.stl",
        implant_sites=[
            SiteSpec(tooth=3, scan_body_type="t", retention=Retention.CEMENT),
            SiteSpec(tooth=5, scan_body_type="t", retention=Retention.CEMENT),
            SiteSpec(tooth=12, scan_body_type="t", retention=Retention.CEMENT),
        ],
    )
    assert manifest.declared_count == 3


def test_rejects_empty_sites():
    with pytest.raises(ValueError):
        CaseManifest(case_ref="c3", scan_file="scan.stl", implant_sites=[])


def test_rejects_duplicate_tooth_numbers():
    with pytest.raises(ValueError):
        CaseManifest(
            case_ref="c4",
            scan_file="scan.stl",
            implant_sites=[
                SiteSpec(tooth=8, scan_body_type="t", retention=Retention.CEMENT),
                SiteSpec(tooth=8, scan_body_type="t", retention=Retention.SCREW),
            ],
        )
