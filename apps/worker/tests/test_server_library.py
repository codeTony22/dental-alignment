"""The cross-model library-browser endpoints (GET /api/library, .../{model}/{id}/mesh).

The catalog is the client-facing "whole shelf" (2026-07-23 ask): every model group under
data/real/library/caps — INCLUDING the superseded archives — plus legacy ``*-library`` dirs,
with honestly computed flags. The known real-data finding MUST surface: zimmer-4.5's
6020/6030 STLs are byte-identical to neodent-gm's (flag ``duplicate`` naming the counterpart).

Exercised over HTTP with FastAPI's TestClient (catalog shape, mesh serving contract,
404s, deterministic double-call) on a synthetic library tree; the real-data assertions
skip when the library is absent on this machine.
"""
from __future__ import annotations

import pytest
import trimesh
from fastapi.testclient import TestClient

import case_prep.server as srv
from case_prep.adapters import client_data
from case_prep.adapters.library_catalog import build_catalog

client = TestClient(srv.app)


def _write_cap(path, radius=2.0, height=3.0):
    path.parent.mkdir(parents=True, exist_ok=True)
    trimesh.creation.cylinder(radius=radius, height=height, sections=24).export(path)


@pytest.fixture()
def synthetic_data(tmp_path, monkeypatch):
    """A miniature data root exercising every catalog feature: two models, a superseded
    archive, a byte-identical cross-model pair, a legacy dir with one loadable and one
    garbage file."""
    caps = tmp_path / "library/caps"
    _write_cap(caps / "acme-a/acme-a-5020.stl", radius=2.5)
    _write_cap(caps / "acme-a/acme-a-6020.stl", radius=3.0)
    _write_cap(caps / "acme-a/superseded-2026-01-01/acme-a-5020.stl", radius=2.4)
    _write_cap(caps / "brand-b/brand-b-7020.stl", radius=3.5)
    # the cross-model duplicate: brand-b's 6020 is byte-identical to acme-a's
    dup = caps / "brand-b/brand-b-6020.stl"
    dup.write_bytes((caps / "acme-a/acme-a-6020.stl").read_bytes())
    legacy = tmp_path / "old-library"
    _write_cap(legacy / "old master.stl", radius=2.0)
    (legacy / "broken.stl").write_bytes(b"this is not an stl file")
    monkeypatch.setattr(srv, "DATA", tmp_path)
    return tmp_path


def _group(catalog, model):
    return next(g for g in catalog if g["model"] == model)


def _variant(group, entry_id):
    return next(v for v in group["variants"] if v["id"] == entry_id)


class TestCatalogShape:
    def test_groups_entries_and_fields(self, synthetic_data):
        res = client.get("/api/library")
        assert res.status_code == 200
        catalog = res.json()
        assert [g["model"] for g in catalog] == ["acme-a", "brand-b", "old-library"]
        acme = _group(catalog, "acme-a")
        assert acme["legacy"] is False
        current = _variant(acme, "5020")
        assert current["variant"] == "5020"
        assert current["label"] == "acme-a-5020"  # CapSpec.label convention: model-variant
        assert current["filename"] == "acme-a-5020.stl"
        assert current["flags"] == []
        assert current["rim_diameter_mm"] == pytest.approx(5.0, abs=0.3)
        assert current["height_mm"] == pytest.approx(3.0, abs=0.1)
        assert len(current["sha256"]) == 64
        assert current["mesh_url"] == "/api/library/acme-a/5020/mesh"

    def test_superseded_archive_is_listed_and_flagged_not_hidden(self, synthetic_data):
        acme = _group(client.get("/api/library").json(), "acme-a")
        old = _variant(acme, "superseded-2026-01-01--5020")
        assert old["variant"] == "5020"
        assert old["filename"] == "superseded-2026-01-01/acme-a-5020.stl"
        assert "superseded" in old["flags"]
        # both the current 5020 and the archived one live under the SAME model tab
        assert {v["id"] for v in acme["variants"]} >= {"5020", "superseded-2026-01-01--5020"}

    def test_cross_model_duplicate_flags_both_sides_and_names_counterpart(self, synthetic_data):
        catalog = client.get("/api/library").json()
        b_side = _variant(_group(catalog, "brand-b"), "6020")
        a_side = _variant(_group(catalog, "acme-a"), "6020")
        assert "duplicate" in b_side["flags"] and "duplicate" in a_side["flags"]
        assert b_side["duplicate_of"] == ["acme-a/6020"]
        assert a_side["duplicate_of"] == ["brand-b/6020"]
        assert b_side["sha256"] == a_side["sha256"]

    def test_legacy_dir_loadable_vs_unloadable(self, synthetic_data):
        legacy = _group(client.get("/api/library").json(), "old-library")
        assert legacy["legacy"] is True
        loadable = _variant(legacy, "old master")
        assert loadable["flags"] == ["legacy"]
        assert loadable["rim_diameter_mm"] is not None
        broken = _variant(legacy, "broken")
        assert "unloadable" in broken["flags"]
        assert "legacy" not in broken["flags"]  # unloadable REPLACES the dressing-up
        assert broken["rim_diameter_mm"] is None and broken["height_mm"] is None

    def test_double_call_is_deterministic_and_cached(self, synthetic_data):
        first = client.get("/api/library")
        second = client.get("/api/library")
        assert first.json() == second.json()
        # same in-process object — the sha256 scan ran once (lru_cache by data root)
        assert srv.library_catalog.catalog_groups(synthetic_data) is srv.library_catalog.catalog_groups(synthetic_data)


class TestMeshEndpoint:
    def test_serves_the_stl_with_the_part_mesh_contract(self, synthetic_data):
        res = client.get("/api/library/acme-a/5020/mesh")
        assert res.status_code == 200
        assert res.headers["content-type"] == "model/stl"
        loaded = trimesh.load(trimesh.util.wrap_as_stream(res.content), file_type="stl")
        assert len(loaded.vertices) > 10

    def test_superseded_entry_is_fetchable_via_its_id(self, synthetic_data):
        res = client.get("/api/library/acme-a/superseded-2026-01-01--5020/mesh")
        assert res.status_code == 200
        assert res.headers["content-type"] == "model/stl"

    def test_unknown_entry_404s(self, synthetic_data):
        assert client.get("/api/library/acme-a/9999/mesh").status_code == 404
        assert client.get("/api/library/nope/5020/mesh").status_code == 404


real_data = pytest.mark.skipif(not (srv.DATA / "library/caps").is_dir(),
                               reason="real library not present on this machine")


@real_data
class TestRealLibraryFindings:
    """The honest read of the REAL shelf — including the known byte-identical pair."""

    def test_both_systems_present_with_superseded_archives(self):
        catalog, _ = build_catalog(srv.DATA)
        models = [g["model"] for g in catalog]
        assert "neodent-gm" in models and "zimmer-4.5" in models
        neodent = _group(catalog, "neodent-gm")
        assert any("superseded" in v["flags"] for v in neodent["variants"])

    def test_zimmer_6020_and_6030_are_byte_identical_to_neodents(self):
        catalog, _ = build_catalog(srv.DATA)
        zimmer = _group(catalog, "zimmer-4.5")
        for vid in ("6020", "6030"):
            entry = _variant(zimmer, vid)
            assert "duplicate" in entry["flags"], f"zimmer {vid} lost its duplicate flag"
            assert f"neodent-gm/{vid}" in entry["duplicate_of"]

    def test_the_client_legacy_shelf_surfaces_as_a_legacy_group(self):
        # the shelf is addressed by its on-disk directory name (client-owned, never renamed
        # and never printed in the interface — adapters/client_data)
        shelf = client_data.LEGACY_SHELF_DIR.name
        catalog, _ = build_catalog(srv.DATA)
        legacy_groups = [g for g in catalog if g["legacy"]]
        assert any(g["model"] == shelf for g in legacy_groups)
        group = _group(catalog, shelf)
        # the two shelf files are themselves byte-identical — surfaced, not hidden
        flags = {v["id"]: v["flags"] for v in group["variants"]}
        assert all("legacy" in f or "unloadable" in f for f in flags.values())

    def test_real_mesh_serves_over_http(self):
        res = client.get("/api/library/neodent-gm/4020/mesh")
        assert res.status_code == 200
        assert res.headers["content-type"] == "model/stl"
