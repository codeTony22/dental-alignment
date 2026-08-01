"""THE PREVIEW-MESH ENDPOINT (client 2026-08-01: "we also have the previews of the
artifacts" — the demo's three named 3D views). Evidence class, ungated like the QC
images (see deliver.case_preview_mesh's own docstring for the disclosure decision):
the operator must see what a run produced before they sign and pay for it. Distinct
from the release-gated artifact download endpoint, which is unchanged by this file.

Reuses test_deliver's ``deliverable_client`` (a done run with REAL bytes on disk for
every non-QC package file) rather than re-building that fixture a second way."""
from __future__ import annotations

import pytest

from bff.config import Settings

from conftest import make_data_tree
from test_deliver import deliverable_client
from test_run_resource import FakeWorker, client_with


@pytest.fixture
def product_root(tmp_path):
    return tmp_path / "product"


@pytest.fixture
def data_root(tmp_path):
    return make_data_tree(tmp_path / "data")


@pytest.fixture
def settings(data_root, product_root) -> Settings:
    return Settings(data_root=data_root, product_root=product_root)


class TestPreviewMesh:
    def test_serves_a_packaged_stls_bytes_with_the_model_stl_content_type(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        res = client.get("/api/case-sessions/neodent-gm/runs/current/preview-mesh/"
                         "neodent-gm-4-healingcap-aligned.stl")
        assert res.status_code == 200
        assert res.headers["content-type"] == "model/stl"
        assert res.content == b"STL:neodent-gm-4-healingcap-aligned.stl"

    def test_a_non_stl_package_file_serves_as_octet_stream(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        res = client.get("/api/case-sessions/neodent-gm/runs/current/preview-mesh/"
                         "neodent-gm-manifest.json")
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/octet-stream"
        assert res.content == b"STL:neodent-gm-manifest.json"

    def test_an_unknown_case_is_a_404(self, settings):
        client = client_with(settings, FakeWorker())
        res = client.get(
            "/api/case-sessions/nope/runs/current/preview-mesh/x.stl")
        assert res.status_code == 404

    def test_without_a_done_current_run_it_conflicts_the_act_flavor(self, settings):
        # deliberately 409, unlike the QC endpoint's 404: this feeds a live in-app
        # render the operator is mid-decision over — the same conflict class as
        # confirm/release, not a plain missing resource
        client = client_with(settings, FakeWorker())
        res = client.get(
            "/api/case-sessions/neodent-gm/runs/current/preview-mesh/x.stl")
        assert res.status_code == 409
        assert "no completed current run" in res.json()["detail"]

    def test_a_name_outside_the_package_files_refuses_even_though_the_file_exists_on_disk(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        run_id = client.get("/api/case-sessions/neodent-gm/run").json()["run_id"]
        run_dir = product_root / "neodent-gm" / "runs" / run_id
        (run_dir / "not-in-the-package.stl").write_bytes(b"STL:not-in-the-package.stl")
        res = client.get("/api/case-sessions/neodent-gm/runs/current/preview-mesh/"
                         "not-in-the-package.stl")
        assert res.status_code == 404
        assert "not among" in res.json()["detail"]

    def test_traversal_shaped_names_are_refused(self, settings, product_root):
        client = deliverable_client(settings, product_root)
        # an encoded slash survives the route match into the path param — the
        # validation, not the router, is the guard (mirrors the qc endpoint)
        for name in ("..%2Fsession.json", "%2e%2e%2fsession.json"):
            res = client.get(
                f"/api/case-sessions/neodent-gm/runs/current/preview-mesh/{name}")
            assert res.status_code == 404, name

    def test_a_listed_file_missing_on_disk_is_an_honest_404(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        run_id = client.get("/api/case-sessions/neodent-gm/run").json()["run_id"]
        run_dir = product_root / "neodent-gm" / "runs" / run_id
        (run_dir / "neodent-gm-4-healingcap-aligned.stl").unlink()
        res = client.get("/api/case-sessions/neodent-gm/runs/current/preview-mesh/"
                         "neodent-gm-4-healingcap-aligned.stl")
        assert res.status_code == 404
        assert "missing from the run directory" in res.json()["detail"]

    def test_no_confirmation_and_no_payment_are_needed_evidence_class(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        res = client.get("/api/case-sessions/neodent-gm/runs/current/preview-mesh/"
                         "neodent-gm-4-healingcap-aligned.stl")
        assert res.status_code == 200

    def test_a_qc_image_is_still_servable_here_too_it_is_a_package_file_like_any_other(
            self, settings, product_root):
        # THIS endpoint's membership rule is the run's own package list, full stop —
        # unlike the QC endpoint it draws no PNG/STL class line, because it serves
        # RENDERING geometry, not a curated evidence subset
        client = deliverable_client(settings, product_root)
        res = client.get("/api/case-sessions/neodent-gm/runs/current/preview-mesh/"
                         "neodent-gm-4-clockview.png")
        assert res.status_code == 200
