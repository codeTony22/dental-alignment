"""GET /api/constructions/{vendor}/{filename}/mesh: the vendor construction part's STL,
streamed for the Construction library page's part preview (plan §10-M2 — "the natural
next slice": a part the operator picked is no longer blind before any run has baked it
into a package).

Same serving contract as the caps route (``library.py``'s ``/api/library/{model}/
{variant}/mesh``): resolution is CATALOG MEMBERSHIP through ``application.catalog.
require_construction`` — the ``{vendor}/{filename}`` segments are reassembled into a
``path_id`` STRING and looked up in the catalog's dict, never joined onto a path — so a
miss (unknown OR a traversal shape) is the same 404 in the catalog's own words. The
detail payload's ``catalog.constructions`` rows already carry ``mesh_url`` pointing
here (the worker's catalog writes it), so the UI follows a served URL instead of
assembling one — the same seam ``test_library_mesh.py`` pins for caps.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from bff.main import create_app

MESH_BYTES = b"solid fixture bytes standing in for a construction STL"


def test_serves_the_catalog_entrys_bytes_as_model_stl(settings):
    (settings.data_root
     / "library/construction/dess/neodent-gm-scanbody.stl").write_bytes(MESH_BYTES)
    client = TestClient(create_app(settings))
    res = client.get("/api/constructions/dess/neodent-gm-scanbody.stl/mesh")
    assert res.status_code == 200
    assert res.content == MESH_BYTES
    assert res.headers["content-type"] == "model/stl"


def test_an_unknown_part_is_a_404_in_catalog_words(client):
    res = client.get("/api/constructions/dess/no-such-part.stl/mesh")
    assert res.status_code == 404
    assert "unknown construction part" in res.json()["detail"]


def test_an_unknown_vendor_is_a_404_in_catalog_words(client):
    res = client.get("/api/constructions/no-such-vendor/neodent-gm-scanbody.stl/mesh")
    assert res.status_code == 404
    assert "unknown construction part" in res.json()["detail"]


def test_a_traversal_shaped_vendor_is_refused_by_catalog_membership(client):
    # nothing is ever path-joined — the decoded ".." is just another string that
    # misses the membership dict, the same posture require_construction already
    # gives choices validation (test_case_sessions.py::
    # test_an_unknown_construction_part_is_refused_by_catalog_membership). A
    # LITERAL ".." segment never even reaches the app: the http client resolves
    # it away as ordinary relative-URL dot-segment removal before the request is
    # sent (RFC 3986 §5.2, done client-side, not a server refusal), so the
    # characterisation needs the percent-encoded form to actually exercise the
    # route.
    res = client.get("/api/constructions/%2e%2e/neodent-gm-scanbody.stl/mesh")
    assert res.status_code == 404
    assert "unknown construction part" in res.json()["detail"]


def test_a_slash_smuggled_into_one_segment_never_reaches_the_handler(client):
    # An encoded slash (%2F) inside what is meant to be a single {filename}
    # segment does not reach require_construction at all: FastAPI's default str
    # path converter refuses to match a decoded value containing "/", so the
    # request never resolves to THIS route and Starlette answers its own generic
    # 404 before our handler — and therefore before the catalog membership
    # check — ever runs. Still refused, still never serves a file; the reason is
    # routing, not membership, and the two must not be conflated (deliver.py's
    # shape pre-checks guard a real path join — this route joins nothing).
    for shape in ("dess/..%2Fsession.json", "dess/%2e%2e%2fsession.json"):
        res = client.get(f"/api/constructions/{shape}/mesh")
        assert res.status_code == 404
        assert res.json()["detail"] == "Not Found"


def test_the_detail_payloads_constructions_rows_carry_mesh_url(client):
    # the seam the UI actually uses: catalog rows arrive with mesh_url set by the
    # worker's catalog — the library page follows it verbatim, so the two must agree
    body = client.get("/api/case-sessions/neodent-gm").json()
    row = next(c for c in body["catalog"]["constructions"]
               if c["path_id"] == "dess/neodent-gm-scanbody.stl")
    assert row["mesh_url"] == "/api/constructions/dess/neodent-gm-scanbody.stl/mesh"
    assert client.get(row["mesh_url"]).status_code == 200
