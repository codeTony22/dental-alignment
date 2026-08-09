"""GET /api/library/{model}/{variant}/mesh (plan §7 slice 5b; frame contract
2026-08-09): the part mesh for the Declare panes' pane 1 — CANONICALIZED, never the
vendor file verbatim.

THE FRAME DEFECT THIS FILE NOW PINS AGAINST: the route used to stream the catalog
file's bytes, but the pair fold, the posed ghosts, auto-mark's landmarks and the run
itself all speak the CANONICAL frame, and raw→canonical is a per-part translation
(0.2-0.6mm xy, 2.3-4.7mm z measured across the catalog) — so every pane-1 click was
recorded in the wrong frame, drawing ghosts 2.4-4.8mm off the features. Resolution is
CATALOG MEMBERSHIP (``require_variant`` wording for the 404s) and the canonicalization
is the application layer's one door (``variant_canonical_stl`` → the same
``_library_for``/``template`` the run loads through). The catalog rows the detail
serves carry ``mesh_url``/``top_url`` pointing here, so the UI never assembles these
URLs itself.

The shared conftest tree keeps its EMPTY placeholder files (a real cap there sends
the detector into the empty fixture scan across the whole suite) — every test that
actually loads geometry writes its own real little STL first.
"""
from __future__ import annotations

import io

from fastapi.testclient import TestClient

from bff.main import create_app


def _write_real_cap(settings, offset=(3.0, 2.0, 5.0)) -> None:
    """A real little cap standing OFF the origin — the shape of the frame defect:
    vendor files arrive translated; canonical puts the axis on z."""
    import trimesh

    cap = trimesh.creation.cylinder(radius=2.0, height=3.0)
    cap.apply_translation(list(offset))
    (settings.data_root
     / "library/caps/neodent-gm/neodent-gm-5020.stl").write_bytes(
        cap.export(file_type="stl"))


def _served_mesh(client: TestClient, url: str):
    import trimesh

    res = client.get(url)
    assert res.status_code == 200
    assert res.headers["content-type"] == "model/stl"
    return trimesh.load_mesh(io.BytesIO(res.content), file_type="stl")


def test_serves_the_CANONICALIZED_template_as_model_stl(settings):
    """The fixture cap stands at xy (3, 2); canonical puts the axis on z. A raw
    stream would come back where the vendor file stands — the defect's shape."""
    _write_real_cap(settings)
    client = TestClient(create_app(settings))
    served = _served_mesh(client, "/api/library/neodent-gm/5020/mesh")
    centre_xy = served.vertices[:, :2].mean(axis=0)
    assert abs(centre_xy[0]) < 0.3 and abs(centre_xy[1]) < 0.3, \
        f"served mesh is not canonical — centre at {centre_xy}"


def test_a_superseded_part_serves_by_its_explicit_catalog_id(settings):
    import trimesh

    archive = settings.data_root / "library/caps/neodent-gm/superseded-2025-01-01"
    archive.mkdir()
    old = trimesh.creation.cylinder(radius=2.0, height=2.0)
    old.apply_translation([-4.0, 1.5, 2.0])
    (archive / "neodent-gm-4010.stl").write_bytes(old.export(file_type="stl"))
    client = TestClient(create_app(settings))
    served = _served_mesh(
        client, "/api/library/neodent-gm/superseded-2025-01-01--4010/mesh")
    centre_xy = served.vertices[:, :2].mean(axis=0)
    assert abs(centre_xy[0]) < 0.3 and abs(centre_xy[1]) < 0.3


def test_an_unknown_model_is_a_404_in_catalog_words(client):
    res = client.get("/api/library/no-such-system/5020/mesh")
    assert res.status_code == 404
    assert "unknown implant system" in res.json()["detail"]


def test_an_unknown_variant_is_a_404_in_catalog_words(client):
    res = client.get("/api/library/neodent-gm/9999/mesh")
    assert res.status_code == 404
    assert "not a part of the 'neodent-gm' library" in res.json()["detail"]


def test_the_detail_payloads_mesh_urls_point_at_this_route(settings):
    # the seam the UI actually uses: catalog rows arrive with mesh_url set by the
    # worker's catalog — pane 1 follows it verbatim, so the two must agree
    _write_real_cap(settings)
    client = TestClient(create_app(settings))
    body = client.get("/api/case-sessions/neodent-gm").json()
    group = next(g for g in body["catalog"]["groups"] if g["model"] == "neodent-gm")
    entry = next(v for v in group["variants"] if v["id"] == "5020")
    assert entry["mesh_url"] == "/api/library/neodent-gm/5020/mesh"
    assert client.get(entry["mesh_url"]).status_code == 200


def test_serves_a_top_view_png_for_a_catalog_variant(settings):
    """The variant thumbnail (client 2026-08-09): same membership door as the mesh
    route, rendered from the catalog's own file — a real PNG, not a placeholder."""
    _write_real_cap(settings)
    client = TestClient(create_app(settings))
    res = client.get("/api/library/neodent-gm/5020/top.png")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert res.content.startswith(b"\x89PNG")
    assert len(res.content) > 1500, "an empty render is not a thumbnail"


def test_an_unknown_variant_top_png_is_a_404_in_catalog_words(client):
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
