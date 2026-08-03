"""THE BROWSER UPLOAD (§10-AB.3, retiring §10-O.6's refusal-to-pretend).

The storage policy, pinned here because it IS the feature: the endpoint writes
exactly one thing — ``data_root/scans/<folder>/<filename>`` — the same tree
discovery reads, so an uploaded case appears on the next worklist read through the
same folder-name rules as a lab-copied one. One folder per case, never overwritten;
the body is the raw STL bytes (no multipart, nothing else travels); a size cap
refuses runaways while streaming; and the response is the DISCOVERED case row read
back through ``discover_cases`` — what the worklist will say, never an invention.

Deliberately under ``/api/uploads``, not ``/api/case-sessions``: an upload creates a
CASE in the scan tree; it is not an action on a session, touches no session store,
and carries no status-shaped field (the body is bytes). The case-sessions action
allowlist keeps its own scope.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bff.config import Settings
from bff.main import create_app
from bff.resources.uploads import MAX_UPLOAD_BYTES

from conftest import make_data_tree


@pytest.fixture
def product_root(tmp_path):
    return tmp_path / "product"


@pytest.fixture
def data_root(tmp_path):
    return make_data_tree(tmp_path / "data")


@pytest.fixture
def client(data_root, product_root) -> TestClient:
    return TestClient(create_app(Settings(data_root=data_root,
                                          product_root=product_root)))


STL = b"solid smoke\nendsolid smoke\n"


def upload(client, folder="doctor-costa-4471", filename="lower_jaw.stl",
           body: bytes = STL):
    return client.post(f"/api/uploads/scans/{folder}/{filename}", content=body)


class TestTheHappyPath:
    def test_the_bytes_land_where_discovery_reads(self, client, data_root):
        res = upload(client)
        assert res.status_code == 201, res.text
        written = data_root / "scans/doctor-costa-4471/lower_jaw.stl"
        assert written.read_bytes() == STL

    def test_the_response_is_the_discovered_case_not_an_echo(self, client):
        body = upload(client).json()
        # every field below is discover_cases' own derivation: the doctor- prefix
        # stripped for the id, the label rules, the jaw read off the filename
        assert body["case_id"] == "costa-4471"
        assert body["folder"] == "doctor-costa-4471"
        assert body["scan_filename"] == "lower_jaw.stl"
        assert body["doctor"] == "Doctor Costa 4471"
        assert body["jaw"] == "lower"
        assert body["scan_bytes"] == len(STL)

    def test_the_new_case_reaches_the_worklist(self, client):
        upload(client)
        rows = client.get("/api/case-sessions").json()
        assert any(row.get("id") == "costa-4471" for row in rows)

    def test_uploading_writes_nothing_to_the_product_data_plane(
            self, client, product_root):
        # creating a case mints no session — the session appears when the case is
        # first WORKED, exactly as it does for a lab-copied folder
        upload(client)
        assert not product_root.exists()


class TestTheRefusals:
    def test_an_existing_folder_is_refused_never_overwritten(self, client):
        assert upload(client).status_code == 201
        res = upload(client, body=b"other bytes")
        assert res.status_code == 409
        assert "already" in res.json()["detail"]
        # and the refusal names the one-folder-per-case rule's consequence
        assert "folder" in res.json()["detail"]

    def test_the_existing_lab_copied_case_is_equally_protected(self, client):
        res = upload(client, folder="doctor-neodent-gm")
        assert res.status_code == 409

    def test_a_non_stl_filename_is_refused(self, client):
        res = upload(client, filename="lower_jaw.ply")
        assert res.status_code == 422
        assert "STL" in res.json()["detail"]

    def test_unsafe_names_are_refused(self, client, data_root):
        # ".." collapses at the router (404 before the handler — refused by the
        # path shape itself); everything else reaches the name rule and gets the
        # stated 422. Either way: refused, and NOTHING lands on disk.
        before = sorted(p.name for p in (data_root / "scans").iterdir())
        assert upload(client, folder="..").status_code in (404, 422)
        assert upload(client, folder=".hidden").status_code == 422
        assert upload(client, filename="..stl").status_code == 422
        assert upload(client, folder="a b").status_code == 422
        assert sorted(p.name for p in (data_root / "scans").iterdir()) == before

    def test_an_empty_body_is_refused(self, client):
        res = upload(client, body=b"")
        assert res.status_code == 422
        assert "empty" in res.json()["detail"]

    def test_a_refused_upload_leaves_no_folder_behind(self, client, data_root):
        upload(client, body=b"")
        assert not (data_root / "scans/doctor-costa-4471").exists()

    def test_the_size_cap_refuses_while_streaming(self, client, data_root):
        res = upload(client, body=b"x" * (MAX_UPLOAD_BYTES + 1))
        assert res.status_code == 413
        assert not (data_root / "scans/doctor-costa-4471").exists()

    def test_uppercase_stl_extension_is_accepted_like_discovery_does(
            self, client, data_root):
        # discovery matches the suffix case-insensitively (cases.py); the door in
        # must accept what the reader accepts
        res = upload(client, filename="SCAN.STL")
        assert res.status_code == 201
        assert (data_root / "scans/doctor-costa-4471/SCAN.STL").exists()
