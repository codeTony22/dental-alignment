"""THE ASSURANCE READ SURFACE (plan §4 Deliver, §2; grill AM-1/AM-12): what the
operator confirms OVER — visible BEFORE any confirmation, because signing over visible
evidence is the whole design (AM-1's two disclosure classes: EVIDENCE is ungated;
DELIVERABLE ARTIFACTS gate on confirmation + payment + release — test_deliver's side).

  - ``GET /api/case-sessions/{id}/assurance`` — the per-site verdict TABLE data: a pure
    PROJECTION of the persisted run summary (the worker's words verbatim, no new
    physics), each numeric beside the backend's own industry reference
    (case_prep.domain.acceptance — the catalog that pairs every measured number with
    the reference the doctor already knows), sorted worst-first SERVER-side (AM-12:
    exception-first — flagged rows pinned above the fold, then by gate severity).
  - ``GET /api/case-sessions/{id}/runs/current/qc/{filename}`` — the QC images,
    EVIDENCE class: ungated, filename validated against the run's own package files
    (no traversal), and everything that is NOT a QC image refused here — the
    release-gated artifact endpoint owns the rest.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bff.config import Settings
from bff.session import SessionStore

from conftest import make_data_tree
from test_run_resource import FakeWorker, client_with, row, seed_ready, summary_for


QC_FILES = ("neodent-gm-4-clockview.png", "neodent-gm-4-deviation.png",
            "neodent-gm-13-clockview.png", "neodent-gm-13-deviation.png")
# WORKER-REAL names (adapters/output_package.py): every per-tooth file is built as
# f"{case_id}-{tooth}-…", and the overlay / manifest / jaw scan are case-wide.
# The fixture speaks the pipeline's own naming because the artifact gate's
# file→site attribution anchors on exactly that construction — fixture names the
# worker would never emit ("cap-4-aligned.stl") once let a leak pass unseen.
PACKAGE_FILES = QC_FILES + (
    "neodent-gm-4-healingcap-aligned.stl",
    "neodent-gm-13-healingcap-aligned.stl",
    "neodent-gm-upper-overlay.stl",
    "neodent-gm-manifest.json",
    "neodent-gm-upper.stl",
    "view.html",
)


@pytest.fixture
def product_root(tmp_path):
    return tmp_path / "product"


@pytest.fixture
def data_root(tmp_path):
    return make_data_tree(tmp_path / "data")


@pytest.fixture
def settings(data_root, product_root) -> Settings:
    return Settings(data_root=data_root, product_root=product_root)


def landed_client(settings: Settings, product_root, rows,
                  files=PACKAGE_FILES, qc_bytes=True) -> TestClient:
    """A client whose case has a DONE current run: seed Declare-complete, fire the
    run through the fake port, and materialize the run directory's QC images (the
    fake port runs no physics, so the files the qc endpoint serves are laid down
    here — distinct bytes per file, so a hash test can tell them apart)."""
    seed_ready(product_root)
    client = client_with(settings, FakeWorker(summary=summary_for(rows, files=files)))
    res = client.post("/api/case-sessions/neodent-gm/run")
    assert res.status_code == 200
    if qc_bytes:
        run_id = client.get("/api/case-sessions/neodent-gm/run").json()["run_id"]
        run_dir = product_root / "neodent-gm" / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        for name in files:
            if name.endswith(".png"):
                (run_dir / name).write_bytes(b"\x89PNG:" + name.encode())
    return client


# --- the assurance projection ----------------------------------------------------------

class TestAssuranceRefusals:
    def test_an_unknown_case_is_a_404(self, settings):
        client = client_with(settings, FakeWorker())
        assert client.get("/api/case-sessions/nope/assurance").status_code == 404

    def test_no_run_at_all_is_a_404_with_words(self, settings):
        client = client_with(settings, FakeWorker())
        res = client.get("/api/case-sessions/neodent-gm/assurance")
        assert res.status_code == 404
        assert "no completed current run" in res.json()["detail"]

    def test_a_refused_run_is_a_404_not_an_empty_table(self, settings, product_root):
        seed_ready(product_root)
        client = client_with(settings, FakeWorker(refusal="no confirmed site"))
        client.post("/api/case-sessions/neodent-gm/run")
        res = client.get("/api/case-sessions/neodent-gm/assurance")
        assert res.status_code == 404
        # a refused run has no evidence to confirm — an empty 200 would invite a
        # confirmation over nothing
        assert "no completed current run" in res.json()["detail"]


class TestAssuranceProjection:
    def test_the_row_facts_are_the_summarys_own(self, settings, product_root):
        client = landed_client(settings, product_root,
                               [row(4, level="attention"), row(13)])
        body = client.get("/api/case-sessions/neodent-gm/assurance").json()
        assert body["case_id"] == "neodent-gm"
        assert body["run_id"]
        # the case-level relief outcome rides along verbatim (the clamp truth the
        # bundle must cover)
        assert body["relief"]["gingival_offset_requested_mm"] == 0.2
        site = next(s for s in body["sites"] if s["tooth"] == 4)
        assert site["status"] == "flagged"          # the ladder's rung, session truth
        assert site["declared_variant"] == "5020"   # the run row's variant facts
        assert site["identified_variant"] == "5020"
        assert site["variant_agreement"] == "match"  # the backend's own word
        assert site["seat_method"] == "rim-seat"
        assert site["rim_agreement_mm"] == 0.07
        assert site["deviation_rms_mm"] == 0.43
        assert site["deviation_p90_mm"] == 0.71
        # rotation: deg + evidence + unverified, from the clocking block verbatim
        assert site["rotation"]["evidence"] == "codes"
        assert site["rotation"]["unverified"] is True
        # gate level + the guidance words verbatim (the operator confirms over THESE)
        assert site["gate"]["level"] == "attention"
        assert any("ROTATION" in a for a in site["gate"]["actions"])
        # clamp: requested/applied/reason from the production block
        assert site["clamp"]["clamped"] is False
        ready = next(s for s in body["sites"] if s["tooth"] == 13)
        assert ready["status"] == "ready"
        assert ready["gate"]["level"] == "ready"

    def test_each_numeric_stands_beside_its_industry_reference(
            self, settings, product_root):
        """AM-12 + the acceptance catalog: the references are the BACKEND'S own
        pairings (case_prep.domain.acceptance) — value, display, band and the cited
        industry number, verbatim — never a UI's editorial."""
        client = landed_client(settings, product_root, [row(4), row(13)])
        body = client.get("/api/case-sessions/neodent-gm/assurance").json()
        site = body["sites"][0]
        refs = site["references"]
        # the four numerics the table serves each carry their catalog row
        assert refs["rim_agreement_mm"]["value"] == 0.07
        assert refs["rim_agreement_mm"]["band"] == "pass"
        assert "scan-body agreement literature" in \
            refs["rim_agreement_mm"]["industry_ref"]["value"]
        assert "±0.5 mm map convention" in \
            refs["deviation_rms_mm"]["industry_ref"]["value"]
        assert "Binon 1996" in refs["rotation_deg"]["industry_ref"]["source"]
        assert refs["cap_identity"]["value"] == "match"
        assert "declared 5020 / measured 5020" in refs["cap_identity"]["display"]

    def test_sites_sort_worst_first_flagged_pinned_then_by_gate(
            self, settings, product_root):
        """AM-12: exception-first. Flagged sites above the fold; within a status,
        the worse gate first (action-needed > attention > ready); ties by tooth so
        the order is stable across reloads."""
        rows = [row(4, level="attention"), row(13, level="action-needed")]
        # tooth 13's guidance says action-needed -> both 4 and 13 land flagged;
        # 13's gate is worse, so 13 leads despite the higher tooth number
        client = landed_client(settings, product_root, rows)
        body = client.get("/api/case-sessions/neodent-gm/assurance").json()
        assert [s["tooth"] for s in body["sites"]] == [13, 4]
        assert [s["status"] for s in body["sites"]] == ["flagged", "flagged"]

    def test_ready_rows_follow_flagged_rows(self, settings, product_root):
        client = landed_client(settings, product_root,
                               [row(4), row(13, level="attention")])
        body = client.get("/api/case-sessions/neodent-gm/assurance").json()
        assert [s["tooth"] for s in body["sites"]] == [13, 4]

    def test_each_site_names_its_own_qc_images(self, settings, product_root):
        client = landed_client(settings, product_root, [row(4), row(13)])
        body = client.get("/api/case-sessions/neodent-gm/assurance").json()
        by_tooth = {s["tooth"]: s for s in body["sites"]}
        assert by_tooth[4]["qc_images"] == ["neodent-gm-4-clockview.png",
                                            "neodent-gm-4-deviation.png"]
        assert by_tooth[13]["qc_images"] == ["neodent-gm-13-clockview.png",
                                             "neodent-gm-13-deviation.png"]

    def test_the_projection_is_ungated_no_operator_no_confirmation_needed(
            self, settings, product_root):
        """AM-1's first class: EVIDENCE is visible before any confirmation — the
        assurance endpoint carries no operator requirement and no payment gate."""
        client = landed_client(settings, product_root, [row(4), row(13)])
        res = client.get("/api/case-sessions/neodent-gm/assurance")
        assert res.status_code == 200
        # and reading it writes nothing: a projection, not an act
        store = SessionStore(settings.product_root)
        version_before = store.load("neodent-gm").version
        client.get("/api/case-sessions/neodent-gm/assurance")
        assert store.load("neodent-gm").version == version_before


# --- the fork, on the document the operator reads ---------------------------------------

class TestTheAssuranceShowsTheFork:
    """THE STANDING DIRECTIVE, kept where it was promised: when Adjust is not
    surfaced the ASSURANCE must still show what was done (bff/evidence.py cites it
    as the reason the decision joined the seal). Sealing the word is not showing it
    — a hash is unreadable — so the projection the operator reads before confirming
    carries the decision too. Same document both ways: what the operator saw is
    what the seal covers, and Deliver's report can state it without a second fetch.
    """

    def test_before_the_fork_is_faced_the_assurance_says_nothing_happened(
            self, settings, product_root):
        client = landed_client(settings, product_root, [row(4), row(13)])
        body = client.get("/api/case-sessions/neodent-gm/assurance").json()
        assert body["adjustments"] is None

    def test_the_recorded_decision_shows_on_the_assurance(
            self, settings, product_root):
        client = landed_client(settings, product_root, [row(4), row(13)])
        assert client.post("/api/case-sessions/neodent-gm/adjust-decision",
                           json={"decision": "skip"}).status_code == 200
        assert client.get("/api/case-sessions/neodent-gm/assurance").json()[
            "adjustments"] == "skip"
        # newest act wins here too — the projection is derived, never cached
        assert client.post("/api/case-sessions/neodent-gm/adjust-decision",
                           json={"decision": "adjust"}).status_code == 200
        assert client.get("/api/case-sessions/neodent-gm/assurance").json()[
            "adjustments"] == "adjust"


# --- the qc image endpoint -------------------------------------------------------------

class TestQcImages:
    def test_a_qc_image_serves_its_bytes_as_png(self, settings, product_root):
        client = landed_client(settings, product_root, [row(4), row(13)])
        res = client.get("/api/case-sessions/neodent-gm/runs/current/qc/"
                         "neodent-gm-4-clockview.png")
        assert res.status_code == 200
        assert res.headers["content-type"] == "image/png"
        assert res.content == b"\x89PNG:neodent-gm-4-clockview.png"

    def test_without_a_done_current_run_the_qc_endpoint_404s(self, settings):
        client = client_with(settings, FakeWorker())
        res = client.get("/api/case-sessions/neodent-gm/runs/current/qc/x.png")
        assert res.status_code == 404
        assert "no completed current run" in res.json()["detail"]

    def test_a_name_outside_the_package_files_is_refused(
            self, settings, product_root):
        client = landed_client(settings, product_root, [row(4), row(13)])
        res = client.get("/api/case-sessions/neodent-gm/runs/current/qc/"
                         "session.json")
        assert res.status_code == 404
        assert "not among" in res.json()["detail"]

    def test_traversal_shaped_names_are_refused(self, settings, product_root):
        client = landed_client(settings, product_root, [row(4), row(13)])
        # an encoded slash survives the route match into the path param — the
        # validation, not the router, is the guard
        for name in ("..%2Fsession.json", "%2e%2e%2fsession.json"):
            res = client.get(
                f"/api/case-sessions/neodent-gm/runs/current/qc/{name}")
            assert res.status_code == 404, name

    def test_a_package_file_that_is_not_a_qc_image_is_refused_here(
            self, settings, product_root):
        """AM-1's boundary IN CODE: this endpoint serves the EVIDENCE class only.
        An STL is a deliverable — it discloses through the release-gated artifact
        endpoint or not at all, and the refusal says so."""
        client = landed_client(settings, product_root, [row(4), row(13)])
        res = client.get("/api/case-sessions/neodent-gm/runs/current/qc/"
                         "neodent-gm-4-healingcap-aligned.stl")
        assert res.status_code == 403
        detail = res.json()["detail"]
        assert "not a QC image" in detail
        assert "artifact" in detail

    def test_a_listed_image_missing_on_disk_is_an_honest_404(
            self, settings, product_root):
        client = landed_client(settings, product_root, [row(4), row(13)],
                               qc_bytes=False)
        res = client.get("/api/case-sessions/neodent-gm/runs/current/qc/"
                         "neodent-gm-4-clockview.png")
        assert res.status_code == 404
        assert "missing from the run directory" in res.json()["detail"]
