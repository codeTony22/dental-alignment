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
