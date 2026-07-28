"""THE DISCLOSURE GATES (plan §4 Deliver, §6; grill AM-1/AM-10/AM-12): the
confirmation over sealed evidence, the payment stub, release-as-disclosure, and the
gated artifact endpoints — slice 8-ii.

The chain under test, end to end:

  POST /confirm (dispositions + per-flag acknowledgments; seals the evidence bundle
  TRANSACTIONALLY) → POST /payment (the honest stub) → POST /release (re-derives the
  evidence and refuses on ANY drift) → GET /runs/current/artifacts[/{filename}] (the
  deliverable class, disclosed at last; withheld sites excluded).

Confirm → change → release must 409 — pinned here both ways the case can change:
a reset boundary clearing the run pointer, and an evidence drift the pointer
survives (a withdrawn review tick, a mutated QC byte).

NO OPERATOR HEADER ANYWHERE (client 2026-07-27: "WE dont need operator name the
checkmark is sufficient"). AM-11's X-Operator requirement is GONE — deliberately,
not by oversight — and TestIdentityIsNoLongerClaimed below is where that decision
is pinned so nobody restores the 422 as a "regression fix".
"""
from __future__ import annotations

import json

import pytest

from bff.config import Settings
from bff.session import SessionStore

from conftest import make_data_tree
from test_assurance import PACKAGE_FILES, landed_client
from test_run_resource import FakeWorker, client_with, row, seed_ready, summary_for


@pytest.fixture
def product_root(tmp_path):
    return tmp_path / "product"


@pytest.fixture
def data_root(tmp_path):
    return make_data_tree(tmp_path / "data")


@pytest.fixture
def settings(data_root, product_root) -> Settings:
    return Settings(data_root=data_root, product_root=product_root)


def deliverable_client(settings, product_root, rows=None, files=PACKAGE_FILES):
    """A landed client whose run directory also holds the DELIVERABLE files, so the
    artifact endpoints have real bytes to (refuse to) serve."""
    rows = rows if rows is not None else [row(4), row(13)]
    client = landed_client(settings, product_root, rows, files=files)
    run_id = client.get("/api/case-sessions/neodent-gm/run").json()["run_id"]
    run_dir = product_root / "neodent-gm" / "runs" / run_id
    for name in files:
        if not name.endswith(".png"):
            (run_dir / name).write_bytes(b"STL:" + name.encode())
    return client


def confirm_body(dispositions=None, acknowledged=()):
    return {"dispositions": dispositions if dispositions is not None
            else {"4": "release", "13": "release"},
            "acknowledged_flags": list(acknowledged)}


def confirm(client, body=None):
    return client.post("/api/case-sessions/neodent-gm/confirm",
                       json=body if body is not None else confirm_body())


def pay(client):
    return client.post("/api/case-sessions/neodent-gm/payment",
                       json={"authorize": True})


def release(client):
    return client.post("/api/case-sessions/neodent-gm/release")


def confirmed_paid_client(settings, product_root, dispositions=None,
                          acknowledged=()):
    client = deliverable_client(settings, product_root)
    assert confirm(client, confirm_body(dispositions, acknowledged)).status_code == 200
    assert pay(client).status_code == 200
    return client


# --- identity, DELIBERATELY REMOVED (client 2026-07-27) --------------------------------

class TestIdentityIsNoLongerClaimed:
    """THE DELETED REQUIREMENT, pinned so it is never "restored" as a regression fix.

    Client, verbatim: "WE dont need operator name the checkmark is sufficient."

    The reasoning, because a reader deserves it: a self-typed name behind no
    authentication was never identity — it was a text field. Recording it made the
    records LOOK rigorous while proving nothing (anyone could type anyone), and a
    record that looks like proof and is not is worse than one that claims less.
    What the records now stand on is the ATTESTATION ACT itself — a run authorized
    only by per-site review ticks, a confirmation sealed over re-derivable evidence.
    Real identity arrives with real auth (plan §8 / phase-2), where a name will
    mean something. A deliberate reduction, not an oversight.

    Every test below used to assert a 422. They assert the act instead."""

    def test_confirming_with_no_header_at_all_seals_the_record(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        record = SessionStore(product_root).load("neodent-gm").confirmation
        assert record is not None
        assert record.at   # the timestamp stays: WHEN is a fact the act produced

    @pytest.mark.parametrize("method,path", [
        ("POST", "/api/case-sessions/neodent-gm/payment"),
        ("POST", "/api/case-sessions/neodent-gm/release"),
        ("GET", "/api/case-sessions/neodent-gm/runs/current/artifacts"),
        ("GET", "/api/case-sessions/neodent-gm/runs/current/artifacts/"
                "neodent-gm-4-healingcap-aligned.stl"),
    ])
    def test_no_gating_endpoint_asks_who_you_are(
            self, settings, product_root, method, path):
        """Whatever these refuse, it is never "who is acting?" — the 422 that used
        to greet an unnamed caller is gone from every one of them."""
        client = deliverable_client(settings, product_root)
        res = client.request(
            method, path, json={"authorize": True} if "payment" in path else None)
        assert res.status_code != 422
        assert "names its actor" not in res.text

    def test_a_sent_header_is_simply_ignored_never_recorded(
            self, settings, product_root):
        # a stale client (or a curl someone kept) may still send X-Operator: the
        # server neither refuses it nor keeps it — an unauthenticated name is not a
        # fact worth persisting, and a nullable column that never fills would be a
        # lie about intent
        client = deliverable_client(settings, product_root)
        assert confirm(client).status_code == 200
        assert client.post("/api/case-sessions/neodent-gm/payment",
                           json={"authorize": True},
                           headers={"X-Operator": "Ana Petrova"}).status_code == 200
        session = SessionStore(product_root).load("neodent-gm")
        assert "Ana Petrova" not in session.model_dump_json()

    @pytest.mark.parametrize("record", ["ConfirmationRecord", "PaymentRecord",
                                        "ReleaseRecord"])
    def test_the_three_records_carry_no_operator_field_at_all(self, record):
        """STRUCTURAL: the field is GONE, not nullable. A column that can only ever
        hold None documents an intention nobody has."""
        import bff.session as session_module
        model = getattr(session_module, record)
        assert "operator" not in model.model_fields
        assert "at" in model.model_fields   # the timestamp is what survives


# --- the confirmation (AM-10, AM-12) ---------------------------------------------------

class TestConfirmRefusals:
    def test_without_a_done_current_run_there_is_nothing_to_confirm(
            self, settings, product_root):
        seed_ready(product_root)
        client = client_with(settings, FakeWorker())
        res = confirm(client)
        assert res.status_code == 409
        assert "no completed current run" in res.json()["detail"]

    def test_every_site_needs_a_disposition_each_missing_one_named(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        res = confirm(client, confirm_body({"4": "release"}))
        assert res.status_code == 422
        detail = res.json()["detail"]
        assert "tooth 13" in detail and "disposition" in detail

    def test_a_disposition_for_a_tooth_the_run_does_not_carry_is_refused(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        res = confirm(client, confirm_body(
            {"4": "release", "13": "release", "30": "release"}))
        assert res.status_code == 422
        assert "tooth 30" in res.json()["detail"]

    def test_a_disposition_value_outside_the_two_acts_is_refused(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        res = confirm(client, confirm_body({"4": "ship-it", "13": "release"}))
        assert res.status_code == 422

    def test_a_smuggled_extra_field_is_refused(self, settings, product_root):
        client = deliverable_client(settings, product_root)
        res = client.post("/api/case-sessions/neodent-gm/confirm",
                          json={**confirm_body(), "status": "confirmed"})
        assert res.status_code == 422


class TestFlagsAcknowledgeRowByRow:
    """AM-12: a flag is confirmed row-by-row, never in bulk — releasing a flagged
    site demands ITS OWN acknowledgment, and the refusal names exactly the teeth
    still unacknowledged."""

    def _flagged_client(self, settings, product_root):
        # both sites flagged: tooth 4 attention, tooth 13 action-needed
        return deliverable_client(settings, product_root,
                                  rows=[row(4, level="attention"),
                                        row(13, level="action-needed")])

    def test_releasing_a_flagged_site_without_its_acknowledgment_is_refused(
            self, settings, product_root):
        client = self._flagged_client(settings, product_root)
        res = confirm(client, confirm_body(acknowledged=[4]))
        assert res.status_code == 422
        detail = res.json()["detail"]
        assert "tooth 13" in detail and "acknowledg" in detail
        assert "tooth 4" not in detail  # 4 IS acknowledged — only 13 is named

    def test_each_flagged_release_acknowledged_confirms(
            self, settings, product_root):
        client = self._flagged_client(settings, product_root)
        assert confirm(client, confirm_body(acknowledged=[4, 13])).status_code == 200

    def test_a_withheld_flagged_site_needs_no_acknowledgment(
            self, settings, product_root):
        # withholding is not releasing: the site drops from the released set and
        # stays open — there is no release to acknowledge
        client = self._flagged_client(settings, product_root)
        res = confirm(client, confirm_body({"4": "release", "13": "withhold"},
                                           acknowledged=[4]))
        assert res.status_code == 200

    def test_acknowledging_an_unflagged_site_is_refused(
            self, settings, product_root):
        # tooth 13 is READY here — an acknowledgment of a flag that does not exist
        # is a claim about nothing, refused rather than silently dropped
        client = deliverable_client(settings, product_root,
                                    rows=[row(4, level="attention"), row(13)])
        res = confirm(client, confirm_body(acknowledged=[4, 13]))
        assert res.status_code == 422
        assert "tooth 13" in res.json()["detail"]


class TestConfirmSealsTheEvidence:
    def test_the_record_and_the_bundle_land_together(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        res = confirm(client, confirm_body({"4": "release", "13": "withhold"}))
        assert res.status_code == 200
        session = SessionStore(product_root).load("neodent-gm")
        record = session.confirmation
        assert record is not None
        assert record.at   # ISO stamp — the record's own fact, no actor beside it
        assert record.run_id == session.run.run_id
        assert record.dispositions == {"4": "release", "13": "withhold"}
        assert record.acknowledged_flags == []
        # the bundle is ON DISK, content-addressed under the run dir (AM-10)
        bundle_path = (product_root / "neodent-gm" / "runs" / record.run_id /
                       "evidence" / f"{record.evidence_sha256}.json")
        payload = json.loads(bundle_path.read_bytes())
        assert payload["assurance"]["run_id"] == record.run_id
        assert set(payload["qc_sha256"]) == {
            n for n in PACKAGE_FILES if n.endswith(".png")}
        # and the response's session view says so, for the UI's sealed state
        view = res.json()["session"]
        assert view["confirmed"] is True
        assert "operator" not in view["confirmation"]   # the wire dropped it too
        assert view["confirmation"]["at"] == record.at
        assert view["confirmation"]["evidence_sha256"] == record.evidence_sha256

    def test_a_missing_qc_image_refuses_the_whole_confirmation(
            self, settings, product_root):
        """Transactional (AM-10): a bundle that cannot cover its images is never
        sealed — the confirmation refuses and NOTHING persists."""
        client = deliverable_client(settings, product_root)
        run_id = client.get("/api/case-sessions/neodent-gm/run").json()["run_id"]
        (product_root / "neodent-gm" / "runs" / run_id /
         "neodent-gm-13-deviation.png").unlink()
        res = confirm(client)
        assert res.status_code == 409
        assert "neodent-gm-13-deviation.png" in res.json()["detail"]
        assert SessionStore(product_root).load("neodent-gm").confirmation is None

    def test_re_confirming_replaces_the_record_over_the_same_evidence(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        confirm(client, confirm_body({"4": "release", "13": "withhold"}))
        res = confirm(client, confirm_body({"4": "release", "13": "release"}))
        assert res.status_code == 200
        record = SessionStore(product_root).load("neodent-gm").confirmation
        assert record.dispositions == {"4": "release", "13": "release"}


# --- the payment stub (AM-11) ----------------------------------------------------------

class TestPaymentStub:
    def test_fail_closed_by_default(self, settings, product_root):
        client = deliverable_client(settings, product_root)
        detail = client.get("/api/case-sessions/neodent-gm").json()
        assert detail["session"]["payment_authorized"] is False

    def test_the_stub_records_provider_and_time(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        res = pay(client)
        assert res.status_code == 200
        session = SessionStore(product_root).load("neodent-gm")
        assert session.payment is not None
        assert session.payment.provider == "stub"   # permanently distinguishable
        assert session.payment.at
        view = res.json()["session"]
        assert view["payment_authorized"] is True
        assert view["payment"]["provider"] == "stub"

    def test_authorize_false_authorizes_nothing(self, settings, product_root):
        client = deliverable_client(settings, product_root)
        res = client.post("/api/case-sessions/neodent-gm/payment",
                          json={"authorize": False})
        assert res.status_code == 422
        assert SessionStore(product_root).load("neodent-gm").payment is None

    def test_an_extra_field_is_refused(self, settings, product_root):
        client = deliverable_client(settings, product_root)
        res = client.post("/api/case-sessions/neodent-gm/payment",
                          json={"authorize": True, "amount": 0})
        assert res.status_code == 422


# --- release-as-disclosure (AM-1) ------------------------------------------------------

class TestReleaseGates:
    def test_release_without_a_confirmation_names_the_missing_piece(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        pay(client)
        res = release(client)
        assert res.status_code == 409
        assert "confirm" in res.json()["detail"]

    def test_release_without_payment_names_the_missing_piece(
            self, settings, product_root):
        client = deliverable_client(settings, product_root)
        confirm(client)
        res = release(client)
        assert res.status_code == 409
        assert "payment" in res.json()["detail"]

    def test_a_valid_chain_releases_and_records_the_act(
            self, settings, product_root):
        client = confirmed_paid_client(settings, product_root,
                                       {"4": "release", "13": "withhold"})
        res = release(client)
        assert res.status_code == 200
        session = SessionStore(product_root).load("neodent-gm")
        record = session.release
        assert record is not None
        assert record.at
        assert record.run_id == session.run.run_id
        assert record.evidence_sha256 == session.confirmation.evidence_sha256
        assert record.released_teeth == [4]   # the withheld site stays open
        view = res.json()["session"]
        assert view["released"] is True
        assert view["release"]["released_teeth"] == [4]


class TestConfirmThenChangeThenRelease:
    """THE PIN the slice demands: confirm → change → release must 409, whichever way
    the case changed. Validity is re-derivation, never trust in the record."""

    def test_a_reset_boundary_clearing_the_run_blocks_release(
            self, settings, product_root, data_root):
        (data_root / "library/caps/neodent-gm/neodent-gm-5030.stl").touch()
        client = confirmed_paid_client(settings, product_root)
        # the operator re-declares a variant: the boundary clears the run pointer
        assert client.put("/api/case-sessions/neodent-gm/sites/4/declaration",
                          json={"variant": "5030"}).status_code == 200
        res = release(client)
        assert res.status_code == 409
        assert "no completed current run" in res.json()["detail"]

    def test_an_evidence_drift_the_pointer_survives_blocks_release(
            self, settings, product_root):
        """A withdrawn review tick moves a site ready→previewed WITHOUT clearing
        the run pointer — the confirmed bundle no longer matches the re-derived
        evidence, and release refuses in the stated words."""
        client = confirmed_paid_client(settings, product_root)
        assert client.delete(
            "/api/case-sessions/neodent-gm/sites/13/review").status_code == 200
        res = release(client)
        assert res.status_code == 409
        assert "changed since it was confirmed" in res.json()["detail"]
        assert "re-confirm" in res.json()["detail"]

    def test_a_mutated_qc_image_blocks_release(self, settings, product_root):
        """The QC images are part of what was signed (AM-10): one changed bit in a
        render re-derives to a different bundle, and release refuses."""
        client = confirmed_paid_client(settings, product_root)
        run_id = SessionStore(product_root).load("neodent-gm").run.run_id
        qc = (product_root / "neodent-gm" / "runs" / run_id /
              "neodent-gm-4-clockview.png")
        qc.write_bytes(qc.read_bytes() + b"\x00")
        res = release(client)
        assert res.status_code == 409
        assert "changed since it was confirmed" in res.json()["detail"]

    def test_re_confirming_over_the_current_evidence_unblocks_release(
            self, settings, product_root):
        client = confirmed_paid_client(settings, product_root)
        client.delete("/api/case-sessions/neodent-gm/sites/13/review")
        assert release(client).status_code == 409
        # the operator re-reads the evidence as it now stands and re-confirms
        assert confirm(client).status_code == 200
        assert release(client).status_code == 200


# --- the artifact endpoints (the deliverable class) ------------------------------------

class TestArtifactsAreGated:
    @pytest.mark.parametrize("path", [
        "/api/case-sessions/neodent-gm/runs/current/artifacts",
        "/api/case-sessions/neodent-gm/runs/current/artifacts/"
        "neodent-gm-4-healingcap-aligned.stl",
    ])
    def test_no_release_no_disclosure_with_the_missing_pieces_named(
            self, settings, product_root, path):
        client = deliverable_client(settings, product_root)
        res = client.get(path)
        assert res.status_code == 409
        assert "release" in res.json()["detail"]

    def test_a_release_for_a_previous_run_does_not_disclose_the_current_one(
            self, settings, product_root, data_root):
        (data_root / "library/caps/neodent-gm/neodent-gm-5030.stl").touch()
        client = confirmed_paid_client(settings, product_root)
        assert release(client).status_code == 200
        # the case changes and a NEW run lands: the old release must not carry over
        client.put("/api/case-sessions/neodent-gm/sites/4/declaration",
                   json={"variant": "5030"})
        store = SessionStore(product_root)
        s = store.load("neodent-gm")
        from bff.session import SeatedSelection, SiteStatus
        s.sites["4"].status = SiteStatus.READY
        # the re-preview + re-review this seeding stands in for records its seat
        # (the 2026-07-28 drift guard would otherwise refuse the new run)
        s.sites["4"].seated_selection = SeatedSelection(
            model="neodent-gm", construction_path="dess/neodent-gm-scanbody.stl",
            variant="5030", jaw="upper", gingival_offset_mm=0.2)
        store.save(s)
        assert client.post("/api/case-sessions/neodent-gm/run").status_code == 200
        res = client.get("/api/case-sessions/neodent-gm/runs/current/artifacts")
        assert res.status_code == 409

    def test_evidence_drift_after_release_closes_the_door_again(
            self, settings, product_root):
        """The artifact gate re-derives too: released, then a review withdrawn —
        the evidence no longer hashes to what was sealed, so disclosure stops
        until the operator re-confirms and re-releases over what is actually
        there."""
        client = confirmed_paid_client(settings, product_root)
        assert release(client).status_code == 200
        client.delete("/api/case-sessions/neodent-gm/sites/13/review")
        res = client.get("/api/case-sessions/neodent-gm/runs/current/artifacts")
        assert res.status_code == 409


class TestArtifactsDisclose:
    def _released(self, settings, product_root,
                  dispositions=None) -> "TestClient":
        client = confirmed_paid_client(settings, product_root, dispositions)
        assert release(client).status_code == 200
        return client

    def test_the_list_is_the_deliverables_qc_images_are_evidence_not_artifacts(
            self, settings, product_root):
        client = self._released(settings, product_root)
        body = client.get("/api/case-sessions/neodent-gm/runs/current/artifacts").json()
        assert body["run_id"]
        assert body["files"] == ["neodent-gm-4-healingcap-aligned.stl",
                                 "neodent-gm-13-healingcap-aligned.stl",
                                 "neodent-gm-upper-overlay.stl",
                                 "neodent-gm-manifest.json",
                                 "neodent-gm-upper.stl",
                                 "view.html"]
        assert body["withheld_teeth"] == []
        # a full release ships the case-wide files: nothing withheld, nothing held
        assert body["withheld_case_files"] == []

    def test_withholding_a_site_withholds_every_case_wide_file_too(
            self, settings, product_root):
        """The overlay merges ALL aligned components (the worker's own note,
        output_package.py) and the manifest carries every site's row and hashes —
        so under a partial release NOTHING case-wide ships: only files attributed
        to a released tooth leave, and the list names what is held and why."""
        client = self._released(settings, product_root,
                                {"4": "release", "13": "withhold"})
        body = client.get("/api/case-sessions/neodent-gm/runs/current/artifacts").json()
        assert body["files"] == ["neodent-gm-4-healingcap-aligned.stl"]
        assert body["withheld_teeth"] == [13]
        assert body["withheld_case_files"] == ["neodent-gm-upper-overlay.stl",
                                               "neodent-gm-manifest.json",
                                               "neodent-gm-upper.stl",
                                               "view.html"]

    def test_a_case_wide_file_refuses_its_bytes_while_any_site_is_withheld(
            self, settings, product_root):
        client = self._released(settings, product_root,
                                {"4": "release", "13": "withhold"})
        for name in ("neodent-gm-upper-overlay.stl", "neodent-gm-manifest.json",
                     "view.html"):
            res = client.get("/api/case-sessions/neodent-gm/runs/current/"
                             f"artifacts/{name}")
            assert res.status_code == 403, name
            detail = res.json()["detail"]
            assert "case-wide" in detail
            assert "tooth 13" in detail   # the withheld site is NAMED

    def test_a_full_release_serves_the_case_wide_bytes(
            self, settings, product_root):
        client = self._released(settings, product_root)
        res = client.get("/api/case-sessions/neodent-gm/runs/current/artifacts/"
                         "neodent-gm-upper-overlay.stl")
        assert res.status_code == 200
        assert res.content == b"STL:neodent-gm-upper-overlay.stl"

    def test_a_released_file_serves_its_bytes(self, settings, product_root):
        client = self._released(settings, product_root)
        res = client.get("/api/case-sessions/neodent-gm/runs/current/artifacts/"
                         "neodent-gm-4-healingcap-aligned.stl")
        assert res.status_code == 200
        assert res.content == b"STL:neodent-gm-4-healingcap-aligned.stl"

    def test_a_withheld_sites_file_refuses_with_its_status(
            self, settings, product_root):
        client = self._released(settings, product_root,
                                {"4": "release", "13": "withhold"})
        res = client.get("/api/case-sessions/neodent-gm/runs/current/artifacts/"
                         "neodent-gm-13-healingcap-aligned.stl")
        assert res.status_code == 403
        assert "withheld" in res.json()["detail"]

    def test_a_qc_image_refuses_here_and_points_at_the_evidence_class(
            self, settings, product_root):
        client = self._released(settings, product_root)
        res = client.get("/api/case-sessions/neodent-gm/runs/current/artifacts/"
                         "neodent-gm-4-clockview.png")
        assert res.status_code == 403
        assert "QC image" in res.json()["detail"]

    def test_unknown_and_traversal_shaped_names_are_404(
            self, settings, product_root):
        client = self._released(settings, product_root)
        for name in ("nope.stl", "..%2Fsession.json"):
            res = client.get("/api/case-sessions/neodent-gm/runs/current/"
                             f"artifacts/{name}")
            assert res.status_code == 404, name


# --- file→site attribution is anchored, never a substring scan -------------------------

class TestToothAttribution:
    """The gate's attribution stands on the worker's OWN construction
    (output_package.py: every per-tooth file is ``f"{case_id}-{tooth}-…"``), so it
    anchors on ``{case_id}-{tooth}-`` — at most one tooth can match, whatever order
    the teeth arrive in. An anywhere-substring scan attributed by ascending-tooth
    luck: a case id ending in ``-4`` claimed every other tooth's file."""

    def test_anchoring_beats_the_ascending_order_substring_scan(self):
        from bff.resources.deliver import _tooth_of_file
        name = "smith-4-13-healingcap-aligned.stl"
        assert _tooth_of_file(name, "smith-4", [4, 13]) == 13
        assert _tooth_of_file(name, "smith-4", [13, 4]) == 13   # order-independent

    def test_a_case_id_ending_in_a_tooth_number_claims_no_case_wide_file(self):
        from bff.resources.deliver import _tooth_of_file
        assert _tooth_of_file("smith-4-upper.stl", "smith-4", [4, 13]) is None
        assert _tooth_of_file("smith-4-upper-overlay.stl", "smith-4",
                              [4, 13]) is None
        assert _tooth_of_file("smith-4-manifest.json", "smith-4", [4, 13]) is None

    def test_worker_shaped_names_attribute_exactly(self):
        from bff.resources.deliver import _tooth_of_file
        assert _tooth_of_file("neodent-gm-4-healingcap-aligned.stl",
                              "neodent-gm", [4, 13]) == 4
        assert _tooth_of_file("neodent-gm-13-clockview.png",
                              "neodent-gm", [4, 13]) == 13
        assert _tooth_of_file("neodent-gm-upper.stl",
                              "neodent-gm", [4, 13]) is None


# --- a re-confirm retires the release --------------------------------------------------

class TestAReconfirmRetiresTheRelease:
    """The release record is valid only while it still covers the CURRENT
    confirmation (plan §4: validity is re-derivation, never trust in a record).
    Dispositions are deliberately NOT in the evidence bundle — so a re-confirm
    that changes one moves no hash, and the gate must compare the records
    themselves: the operator's newest signed act wins, disclosure stops until an
    explicit re-release."""

    def test_a_re_confirm_that_withholds_a_site_closes_disclosure(
            self, settings, product_root):
        client = confirmed_paid_client(settings, product_root)
        assert release(client).status_code == 200
        res = confirm(client, confirm_body({"4": "release", "13": "withhold"}))
        assert res.status_code == 200
        # the display half flips with the record: the rail tick is rail truth
        assert res.json()["session"]["released"] is False
        listing = client.get(
            "/api/case-sessions/neodent-gm/runs/current/artifacts",)
        assert listing.status_code == 409
        assert "confirmation changed after release" in listing.json()["detail"]
        assert "re-release" in listing.json()["detail"]
        fetched = client.get(
            "/api/case-sessions/neodent-gm/runs/current/artifacts/"
            "neodent-gm-13-healingcap-aligned.stl")
        assert fetched.status_code == 409   # the gate closes before per-file logic

    def test_an_explicit_re_release_re_opens_over_the_new_dispositions(
            self, settings, product_root):
        client = confirmed_paid_client(settings, product_root)
        assert release(client).status_code == 200
        confirm(client, confirm_body({"4": "release", "13": "withhold"}))
        assert release(client).status_code == 200
        body = client.get(
            "/api/case-sessions/neodent-gm/runs/current/artifacts",).json()
        assert body["withheld_teeth"] == [13]
        assert "neodent-gm-13-healingcap-aligned.stl" not in body["files"]

    def test_an_identical_re_confirm_keeps_the_release_current(
            self, settings, product_root):
        # nothing material changed — same run, same evidence, same released set:
        # closing the door here would punish a re-read, not protect anyone
        client = confirmed_paid_client(settings, product_root)
        assert release(client).status_code == 200
        res = confirm(client)
        assert res.status_code == 200
        assert res.json()["session"]["released"] is True
        assert client.get(
            "/api/case-sessions/neodent-gm/runs/current/artifacts",).status_code == 200

    def test_the_worklist_released_chip_unticks_with_the_retired_release(
            self, settings, product_root):
        client = confirmed_paid_client(settings, product_root)
        release(client)
        confirm(client, confirm_body({"4": "release", "13": "withhold"}))
        (row_,) = client.get("/api/case-sessions").json()
        assert row_["released"] is False


# --- signing acts are one-winner -------------------------------------------------------

class TestSigningActsAreOneWinner:
    """A CAS loss on a SIGNING act never silently retries: re-applying a
    signature over a rival's write would erase the rival's record while both
    callers hold a 200 — two winners with contradictory receipts. The loser
    gets a 409 that says a rival act landed first AND WHEN; disk holds exactly
    the winner's record.

    WHEN, not WHO, since the identity removal (client 2026-07-27): the rival
    record no longer carries a name to print, and its timestamp is the fact the
    loser can actually check against what they are re-reading."""

    @staticmethod
    def _racing_save(monkeypatch, product_root, rival_write):
        """Arrange a rival write to land between the route's load and its save:
        the first save through the store performs ``rival_write`` first, so the
        route's own save loses the CAS — deterministically, no threads."""
        orig = SessionStore.save
        fired = {"done": False}

        def save(self, session):
            if not fired["done"]:
                fired["done"] = True
                rival_write(SessionStore(product_root), orig)
            return orig(self, session)

        monkeypatch.setattr(SessionStore, "save", save)

    def test_a_rival_confirmation_wins_and_the_loser_is_told_when(
            self, settings, product_root, monkeypatch):
        from bff.session import ConfirmationRecord
        client = deliverable_client(settings, product_root)
        run_id = client.get("/api/case-sessions/neodent-gm/run").json()["run_id"]

        def rival_write(store, orig_save):
            rival = store.load("neodent-gm")
            rival.confirmation = ConfirmationRecord(
                at="2026-07-27T00:00:00+00:00",
                run_id=run_id, evidence_sha256="0" * 64,
                dispositions={"4": "withhold", "13": "withhold"})
            orig_save(store, rival)

        self._racing_save(monkeypatch, product_root, rival_write)
        res = confirm(client)   # the release-everything confirmation
        assert res.status_code == 409
        detail = res.json()["detail"]
        assert "2026-07-27T00:00:00+00:00" in detail and "landed first" in detail
        # ONE winner on disk: the withhold-everything record stands untouched
        record = SessionStore(product_root).load("neodent-gm").confirmation
        assert record.at == "2026-07-27T00:00:00+00:00"
        assert record.dispositions == {"4": "withhold", "13": "withhold"}

    def test_a_rival_release_wins_and_the_loser_is_told_when(
            self, settings, product_root, monkeypatch):
        from bff.session import ReleaseRecord
        client = confirmed_paid_client(settings, product_root)
        session = SessionStore(product_root).load("neodent-gm")
        sha = session.confirmation.evidence_sha256

        def rival_write(store, orig_save):
            rival = store.load("neodent-gm")
            rival.release = ReleaseRecord(
                at="2026-07-27T00:00:00+00:00",
                run_id=session.run.run_id, evidence_sha256=sha,
                released_teeth=[4, 13])
            orig_save(store, rival)

        self._racing_save(monkeypatch, product_root, rival_write)
        res = release(client)
        assert res.status_code == 409
        assert "2026-07-27T00:00:00+00:00" in res.json()["detail"]
        assert SessionStore(product_root).load(
            "neodent-gm").release.at == "2026-07-27T00:00:00+00:00"

    def test_a_non_signing_rival_still_costs_the_act_one_honest_409(
            self, settings, product_root, monkeypatch):
        # ANY interleaved write means the signer did not sign over what is there
        # now — no rival to name, but the act still refuses instead of retrying
        def rival_write(store, orig_save):
            orig_save(store, store.load("neodent-gm"))   # a bare version bump

        client = deliverable_client(settings, product_root)
        self._racing_save(monkeypatch, product_root, rival_write)
        res = confirm(client)
        assert res.status_code == 409
        assert "repeat the act" in res.json()["detail"]
        assert SessionStore(product_root).load("neodent-gm").confirmation is None


# --- the read models tell the chain's truth --------------------------------------------

class TestTheViewsCarryTheChain:
    def test_the_worklist_confirmed_chip_is_real_and_released_rides_beside_it(
            self, settings, product_root):
        client = confirmed_paid_client(settings, product_root)
        (row_,) = client.get("/api/case-sessions").json()
        assert row_["confirmed"] is True
        assert row_["released"] is False
        assert release(client).status_code == 200
        (row_,) = client.get("/api/case-sessions").json()
        assert row_["released"] is True

    def test_released_reports_false_after_the_run_pointer_clears(
            self, settings, product_root, data_root):
        (data_root / "library/caps/neodent-gm/neodent-gm-5030.stl").touch()
        client = confirmed_paid_client(settings, product_root)
        release(client)
        client.put("/api/case-sessions/neodent-gm/sites/4/declaration",
                   json={"variant": "5030"})
        detail = client.get("/api/case-sessions/neodent-gm").json()
        # the record survives as history, but "released" is a CURRENT-run verdict
        assert detail["session"]["released"] is False
