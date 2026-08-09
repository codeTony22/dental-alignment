"""GET /api/library/{model}/{variant}/mesh (plan §7 slice 5b): the part STL for the
Declare panes' pane 1 — the catalog's own file, streamed through the BFF.

Same serving contract as the case scan (model/stl FileResponse) so the viewer package
treats both identically. Resolution is CATALOG MEMBERSHIP through
``application.catalog.require_variant`` — the id is judged against the catalog's own
entries, never joined onto a path — and a miss is a 404 in the catalog's wording (the
path names a resource that is not there; nothing about the request was malformed).
The catalog rows the detail already serves carry ``mesh_url`` pointing exactly here,
so the UI never assembles this URL itself.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from bff.main import create_app

MESH_BYTES = b"solid fixture bytes standing in for a cap STL"


def test_serves_the_catalog_entrys_bytes_as_model_stl(settings):
    (settings.data_root
     / "library/caps/neodent-gm/neodent-gm-5020.stl").write_bytes(MESH_BYTES)
    client = TestClient(create_app(settings))
    res = client.get("/api/library/neodent-gm/5020/mesh")
    assert res.status_code == 200
    assert res.content == MESH_BYTES
    assert res.headers["content-type"] == "model/stl"


def test_a_superseded_part_serves_by_its_explicit_catalog_id(settings):
    archive = settings.data_root / "library/caps/neodent-gm/superseded-2025-01-01"
    archive.mkdir()
    (archive / "neodent-gm-4010.stl").write_bytes(MESH_BYTES)
    client = TestClient(create_app(settings))
    res = client.get("/api/library/neodent-gm/superseded-2025-01-01--4010/mesh")
    assert res.status_code == 200
    assert res.content == MESH_BYTES


def test_an_unknown_model_is_a_404_in_catalog_words(client):
    res = client.get("/api/library/no-such-system/5020/mesh")
    assert res.status_code == 404
    assert "unknown implant system" in res.json()["detail"]


def test_an_unknown_variant_is_a_404_in_catalog_words(client):
    res = client.get("/api/library/neodent-gm/9999/mesh")
    assert res.status_code == 404
    assert "not a part of the 'neodent-gm' library" in res.json()["detail"]


def test_the_detail_payloads_mesh_urls_point_at_this_route(client):
    # the seam the UI actually uses: catalog rows arrive with mesh_url set by the
    # worker's catalog — pane 1 follows it verbatim, so the two must agree
    body = client.get("/api/case-sessions/neodent-gm").json()
    group = next(g for g in body["catalog"]["groups"] if g["model"] == "neodent-gm")
    entry = next(v for v in group["variants"] if v["id"] == "5020")
    assert entry["mesh_url"] == "/api/library/neodent-gm/5020/mesh"
    assert client.get(entry["mesh_url"]).status_code == 200


def test_serves_a_top_view_png_for_a_catalog_variant(settings):
    """The variant thumbnail (client 2026-08-09): same membership door as the mesh
    route, rendered from the catalog's own file — a real PNG, not a placeholder."""
    import trimesh

    stl = trimesh.creation.cylinder(radius=2.0, height=3.0).export(
        file_type="stl")
    (settings.data_root
     / "library/caps/neodent-gm/neodent-gm-5020.stl").write_bytes(stl)
    client = TestClient(create_app(settings))
    res = client.get("/api/library/neodent-gm/5020/top.png")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert res.content.startswith(b"\x89PNG")
    assert len(res.content) > 1500, "an empty render is not a thumbnail"


def test_an_unknown_variant_top_png_is_a_404_in_catalog_words(settings):
    (settings.data_root
     / "library/caps/neodent-gm/neodent-gm-5020.stl").write_bytes(MESH_BYTES)
    client = TestClient(create_app(settings))
    res = client.get("/api/library/neodent-gm/nope/top.png")
    assert res.status_code == 404
    assert "not a part of" in res.json()["detail"]


def test_the_detail_payloads_catalog_rows_carry_the_top_url(client):
    """The UI never assembles this URL: the catalog row serves it, exactly like
    mesh_url (same seam as the mesh_url test above)."""
    body = client.get("/api/case-sessions/neodent-gm").json()
    group = next(g for g in body["catalog"]["groups"] if g["model"] == "neodent-gm")
    entry = next(v for v in group["variants"] if v["id"] == "5020")
    assert entry["top_url"] == "/api/library/neodent-gm/5020/top.png"
