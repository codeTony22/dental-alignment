"""THE PRODUCT'S OWN CASE DISCOVERY AND CATALOG READS — case_prep.application.

The product app plan (docs/engagement/product-app-plan.md §3, grill AM-2) forbids the BFF
from importing ``case_prep.server``: the clean seam is one layer down, and the orchestration
the product needs moves into ``case_prep/application/`` as NEW files. These tests pin the
first tranche of that lift:

  - ``application.cases.discover_cases`` — the demo's case-table rules, re-stated: a scan
    folder with an STL is a case, full stop; every model/construction/jaw reading is a
    NON-BINDING suggestion (client directive 2026-07-25: the lab chooses, the software
    never guesses); the patient-4471 regression (a folder matching no model was silently
    dropped) stays fixed in the product path too.
  - ``application.catalog`` — library groups / construction parts / the relief ceiling as
    plain functions over adapters+domain, refusing unknown selections with
    ``UnknownSelection`` instead of HTTP exceptions.

Synthetic-tree tests pin the RULES (empty STL files: discovery must not parse meshes);
real-tree tests pin the facts of the shipped data tree and skip when it is absent.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from case_prep.application.cases import CaseRecord, discover_cases
from case_prep.application.catalog import (UnknownSelection, construction_parts,
                                           library_groups, relief_ceiling)

REAL = Path(__file__).resolve().parents[1] / "data" / "real"
real_only = pytest.mark.skipif(not (REAL / "library").is_dir(),
                               reason="real data tree not present")


# --- synthetic tree: the discovery RULES, no meshes parsed ------------------------------

def _tree(root: Path, models=("neodent-gm", "neodent")) -> Path:
    """A minimal data tree. STLs are EMPTY files on purpose: discovery reads names and
    directory shape only — a rule change that starts parsing meshes will fail loudly here."""
    for m in models:
        (root / "library/caps" / m).mkdir(parents=True)
    dess = root / "library/construction/dess"
    dess.mkdir(parents=True)
    (dess / "neodent-gm-scanbody.stl").touch()
    (root / "scans").mkdir()
    return root


def _scan_folder(root: Path, folder: str, stl_name: str = "upper_jaw.stl") -> Path:
    d = root / "scans" / folder
    d.mkdir()
    (d / stl_name).touch()
    return d


class TestDiscoverCases:
    def test_a_scan_folder_with_an_stl_is_a_case_and_nothing_else_is(self, tmp_path):
        root = _tree(tmp_path)
        _scan_folder(root, "doctor-neodent-gm")
        (root / "scans" / "empty-folder").mkdir()          # no STL -> not a case
        (root / "scans" / "loose-file.txt").write_text("") # not a folder -> not a case
        cases = discover_cases(root)
        assert [c.id for c in cases] == ["neodent-gm"]

    def test_case_id_strips_the_doctor_prefix_and_doctor_label_reads_well(self, tmp_path):
        root = _tree(tmp_path)
        _scan_folder(root, "doctor-neodent-gm")
        (case,) = discover_cases(root)
        assert case.id == "neodent-gm"
        assert case.doctor == "Doctor Neodent GM"

    def test_longest_model_name_wins_the_suggestion(self, tmp_path):
        # "neodent-gm" and "neodent" both substring-match the folder; the longer, more
        # specific system must win (the demo's own rule, kept)
        root = _tree(tmp_path, models=("neodent", "neodent-gm"))
        _scan_folder(root, "doctor-neodent-gm")
        (case,) = discover_cases(root)
        assert case.suggested_model == "neodent-gm"
        assert case.suggested_construction == "dess/neodent-gm-scanbody.stl"

    def test_a_folder_matching_no_model_is_still_a_case_with_no_suggestions(self, tmp_path):
        # THE PATIENT-4471 REGRESSION: a real upload matching no library name used to be
        # silently dropped. A case is discoverable from its scan alone.
        root = _tree(tmp_path)
        _scan_folder(root, "patient-4471")
        (case,) = discover_cases(root)
        assert case.id == "patient-4471"
        assert case.suggested_model is None
        assert case.suggested_construction is None

    def test_jaw_is_a_suggestion_read_off_the_scan_filename(self, tmp_path):
        root = _tree(tmp_path)
        _scan_folder(root, "doctor-a-neodent-gm", "lower_jaw.stl")
        _scan_folder(root, "doctor-b-neodent-gm", "some_scan.stl")
        lower, upper = discover_cases(root)
        assert lower.jaw == "lower"
        assert upper.jaw == "upper"  # anything not saying "lower" defaults to upper

    def test_sites_json_supplies_curated_suggested_sites(self, tmp_path):
        root = _tree(tmp_path)
        folder = _scan_folder(root, "doctor-neodent-gm")
        (folder / "sites.json").write_text(json.dumps({"suggested_sites": [
            {"tooth": 13, "center": [1.0, 2.0, 3.0], "declared_variant": "5020"}]}))
        (case,) = discover_cases(root)
        assert case.suggested_sites[0]["tooth"] == 13
        assert case.suggested_sites[0]["declared_variant"] == "5020"

    def test_records_are_immutable_facts(self, tmp_path):
        root = _tree(tmp_path)
        _scan_folder(root, "doctor-neodent-gm")
        (case,) = discover_cases(root)
        assert isinstance(case, CaseRecord)
        with pytest.raises(AttributeError):
            case.jaw = "lower"  # a read model hands out facts, not a mutable cache


@real_only
class TestDiscoverCasesOnTheRealTree:
    def test_the_shipped_tree_discovers_the_known_cases(self):
        cases = {c.id: c for c in discover_cases(REAL)}
        assert "neodent-gm" in cases and "zimmer-4.5" in cases
        base = cases["neodent-gm"]
        assert base.jaw == "upper"
        assert base.suggested_model == "neodent-gm"
        assert base.suggested_construction == "dess/neodent-gm-scanbody.stl"
        assert [s["tooth"] for s in base.suggested_sites] == [4, 13]
        assert base.scan.is_file()


# --- catalog reads ----------------------------------------------------------------------

@real_only
class TestCatalogReads:
    def test_library_groups_lists_the_real_models(self):
        models = {g["model"] for g in library_groups(REAL)}
        assert {"neodent-gm", "zimmer-4.5"} <= models

    def test_construction_parts_lists_the_real_vendor_parts(self):
        ids = {row["path_id"] for row in construction_parts(REAL)}
        assert {"dess/neodent-gm-scanbody.stl", "atlantis/zimmer-4.5-scanbody.stl"} <= ids

    def test_relief_ceiling_refuses_an_unknown_construction(self):
        with pytest.raises(UnknownSelection):
            relief_ceiling(REAL, "nowhere/nothing.stl", "neodent-gm", "5020")

    def test_relief_ceiling_refuses_an_unknown_model_before_probing(self):
        with pytest.raises(UnknownSelection):
            relief_ceiling(REAL, "dess/neodent-gm-scanbody.stl", "no-such-system", "5020")

    def test_relief_ceiling_refuses_an_unknown_variant(self):
        with pytest.raises(UnknownSelection):
            relief_ceiling(REAL, "dess/neodent-gm-scanbody.stl", "neodent-gm", "0000")

    @pytest.mark.slow  # real SDF probing, measured 0.5-1.3s cold per pair
    def test_relief_ceiling_reads_a_real_pair(self):
        reading = relief_ceiling(REAL, "dess/neodent-gm-scanbody.stl", "neodent-gm", "5020")
        # the known receipt (memory 2026-07-25): 5020 ceilings WELL below the 0.20mm default
        assert reading["max_safe_mm"] < reading["requested_default_mm"]
        assert reading["default_is_safe"] is False
        assert reading["limited_by"] in ("wall", "channel", "seal", "none")
        assert reading["shippable_at_zero"] is True
        assert reading["note"]  # the operator-facing sentence rides along
