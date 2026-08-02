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
                                           library_groups, relief_ceiling,
                                           require_construction,
                                           require_library_model, require_variant)

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

    def test_a_folder_holding_only_a_ply_is_not_a_case(self, tmp_path):
        # THE PRODUCT'S SCAN-ARRIVAL COPY DEPENDS ON THIS (2026-07-31). The design
        # prototype's drop zone advertises "STL or PLY"; discovery globs ``*.stl`` and
        # nothing else, so a PLY-only folder is silently invisible — the worst failure
        # mode there is for a lab that just copied a case in. apps/product's Worklist
        # panel (domain/worklist.SCAN_ARRIVAL) therefore tells operators to convert
        # first. If discovery ever learns PLY, this test fails and names the copy to fix.
        root = _tree(tmp_path)
        d = root / "scans" / "doctor-ply-only"
        d.mkdir()
        (d / "upper_jaw.ply").touch()
        assert discover_cases(root) == []

    def test_an_uppercase_stl_extension_is_still_a_case(self, tmp_path):
        # 2026-07-31 discovery bug, reproduced against a TestClient before it was fixed:
        # ``Path.glob("*.stl")`` is case-sensitive on POSIX, so a folder whose scanner
        # exported ``UPPER_JAW.STL`` yielded NO case at all. The lab copies the folder in,
        # reloads as the worklist's scan-arrival panel instructs, and sees nothing — while
        # the panel says the only disqualifier is having no STL. Extension case is a
        # scanner-export accident, never a statement about the file.
        root = _tree(tmp_path)
        _scan_folder(root, "doctor-shouty-neodent-gm", "UPPER_JAW.STL")
        (case,) = discover_cases(root)
        assert case.id == "shouty-neodent-gm"
        assert case.scan.name == "UPPER_JAW.STL"

    def test_several_stls_take_the_first_by_name_and_the_rest_are_ignored(self, tmp_path):
        # A complete case folder (both arches) is the normal scanner export, and it becomes
        # ONE case: the first STL by name is the scan and the others are dropped with no
        # row and no diagnostic. That is the shipped behaviour and the product states it
        # (apps/product domain/worklist.SCAN_ARRIVAL step "stl"); this test is what makes
        # the statement true. Sorting is case-insensitive so "first by name" means what an
        # operator reading the folder means by it.
        root = _tree(tmp_path)
        folder = _scan_folder(root, "doctor-both-neodent-gm", "UPPER_JAW.STL")
        (folder / "lower_jaw.stl").touch()
        (case,) = discover_cases(root)
        assert case.scan.name == "lower_jaw.stl"
        assert case.jaw == "lower"

    def test_doctor_is_stripped_only_as_a_leading_prefix(self, tmp_path):
        # 2026-07-31, reproduced: ``replace("doctor-", "", 1)`` strips the first occurrence
        # ANYWHERE, so ``patient-doctor-4471`` became case id ``patient-4471``. The id keys
        # reports/product/<case>/runs/…, so the immutable run dir stopped carrying the
        # folder's name, and the scan-arrival panel's rule ("a leading doctor- is stripped")
        # predicted the wrong id. The prefix form is what the rest of this code assumes.
        root = _tree(tmp_path)
        _scan_folder(root, "patient-doctor-4471")
        (case,) = discover_cases(root)
        assert case.id == "patient-doctor-4471"

    def test_a_folder_named_only_doctor_keeps_its_own_name_as_the_id(self, tmp_path):
        # Stripping the prefix must never mint an empty id.
        root = _tree(tmp_path)
        _scan_folder(root, "doctor-")
        (case,) = discover_cases(root)
        assert case.id == "doctor-"

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

class TestRequireConstruction:
    """Slice 4's choices validation reads through this one door (plan §6/AM-9: catalog
    membership, never a path join on caller input) — synthetic tree, no meshes parsed."""

    def test_a_listed_part_resolves_to_its_file(self, tmp_path):
        root = _tree(tmp_path)
        path = require_construction(root, "dess/neodent-gm-scanbody.stl")
        assert path == root / "library/construction/dess/neodent-gm-scanbody.stl"

    def test_an_unlisted_part_is_refused_in_one_sentence(self, tmp_path):
        root = _tree(tmp_path)
        with pytest.raises(UnknownSelection, match="unknown construction part"):
            require_construction(root, "dess/no-such-part.stl")

    def test_a_traversal_string_is_just_another_unknown(self, tmp_path):
        # membership refuses the escape the measured 2026-07-25 path join allowed
        root = _tree(tmp_path)
        with pytest.raises(UnknownSelection):
            require_construction(root, "../caps/neodent-gm/neodent-gm-5020.stl")


class TestRequireLibraryModel:
    """Slice 5a's system declaration reads through this door: an implant SYSTEM is a
    top-level directory NAME under library/caps — the demo's ``_library_for`` membership
    rule, without loading a single mesh (the check must stay cheap; declaring a system
    happens before any physics is wanted)."""

    def test_a_real_caps_model_passes(self, tmp_path):
        require_library_model(_tree(tmp_path), "neodent-gm")   # no raise, no return

    def test_an_unknown_system_is_refused_in_one_sentence(self, tmp_path):
        with pytest.raises(UnknownSelection, match="unknown implant system"):
            require_library_model(_tree(tmp_path), "no-such-system")

    def test_a_legacy_shelf_directory_is_not_a_system(self, tmp_path):
        # *-library legacy dirs are honestly LISTED by the catalog but are not
        # caps models — a run could never load them as a system
        root = _tree(tmp_path)
        legacy = root / "old-parts-library"
        legacy.mkdir()
        (legacy / "old-parts-library-4040.stl").touch()
        with pytest.raises(UnknownSelection, match="unknown implant system"):
            require_library_model(root, "old-parts-library")

    def test_a_traversal_string_is_just_another_unknown(self, tmp_path):
        with pytest.raises(UnknownSelection):
            require_library_model(_tree(tmp_path), "../construction")


class TestRequireVariant:
    """Slice 5a's per-site declaration validates the variant against the EFFECTIVE
    system's catalog — by the catalog's own entry id, so archived parts stay
    declarable exactly one explicit name at a time (never by widening a glob)."""

    def test_a_current_part_passes_and_returns_the_catalogs_own_file(self, tmp_path):
        # the returned path (5b: the BFF's part-mesh stream serves it) is the
        # CATALOG's resolution, never a join on the caller's strings
        root = _tree(tmp_path)
        stl = root / "library/caps/neodent-gm/neodent-gm-5020.stl"
        stl.touch()
        assert require_variant(root, "neodent-gm", "5020") == stl

    def test_a_superseded_part_passes_by_its_explicit_catalog_id(self, tmp_path):
        root = _tree(tmp_path)
        archive = root / "library/caps/neodent-gm/superseded-2025-01-01"
        archive.mkdir()
        (archive / "neodent-gm-4010.stl").touch()
        assert require_variant(root, "neodent-gm", "superseded-2025-01-01--4010") \
            == archive / "neodent-gm-4010.stl"

    def test_an_unknown_variant_is_refused_in_the_catalog_sentence(self, tmp_path):
        root = _tree(tmp_path)
        (root / "library/caps/neodent-gm/neodent-gm-5020.stl").touch()
        with pytest.raises(UnknownSelection,
                           match="not a part of the 'neodent-gm' library"):
            require_variant(root, "neodent-gm", "9999")

    def test_the_check_is_scoped_to_the_named_model(self, tmp_path):
        # another system's variant is a stranger here — ids belong to ONE catalog
        root = _tree(tmp_path)
        (root / "library/caps/neodent-gm/neodent-gm-5020.stl").touch()
        (root / "library/caps/neodent/neodent-3510.stl").touch()
        with pytest.raises(UnknownSelection):
            require_variant(root, "neodent-gm", "3510")


@real_only
class TestCatalogReads:
    def test_library_groups_lists_the_real_models(self):
        models = {g["model"] for g in library_groups(REAL)}
        assert {"neodent-gm", "zimmer-4.5"} <= models

    def test_construction_parts_lists_the_real_vendor_parts(self):
        ids = {row["path_id"] for row in construction_parts(REAL)}
        assert {"dess/neodent-gm-scanbody.stl", "atlantis/zimmer-4.5-scanbody.stl"} <= ids

    def test_construction_parts_rows_carry_a_mesh_url(self):
        # the product-only seam (server.py:394 serves the shared adapter's rows
        # VERBATIM and has no such route to honour): the wrapper here, not the
        # adapter, is where a part gains a URL the BFF actually serves
        rows = {row["path_id"]: row for row in construction_parts(REAL)}
        row = rows["dess/neodent-gm-scanbody.stl"]
        assert row["mesh_url"] == "/api/constructions/dess/neodent-gm-scanbody.stl/mesh"

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
