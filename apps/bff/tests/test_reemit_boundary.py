"""THE RE-EMIT BOUNDARY (§10-AC, retiring §10-M's deadlock): a construction-part or
relief-only change over a DONE run re-emits the package from the run's own poses —
site rungs survive (the pose the review attested is untouched, the measured fact),
the confirmation and every draft fall explicitly, and the request that leaves the
BFF names its mode and its source run. A JAW change keeps the full retirement: it
moves the alignment's own input.
"""
from __future__ import annotations

import pytest

from bff.config import Settings
from bff.session import SessionStore, SiteStatus

from conftest import make_data_tree
from test_run_resource import FakeWorker, client_with, row, seed_ready, summary_for

CASE = "neodent-gm"


@pytest.fixture
def product_root(tmp_path):
    return tmp_path / "product"


@pytest.fixture
def data_root(tmp_path):
    return make_data_tree(tmp_path / "data")


@pytest.fixture
def settings(data_root, product_root) -> Settings:
    return Settings(data_root=data_root, product_root=product_root)


CHOICES = {"construction_path": "dess/neodent-gm-scanbody.stl", "jaw": "upper",
           "gingival_offset_mm": 0.2}


def second_part(data_root) -> str:
    """A second construction part in the synthetic tree, from another vendor —
    the catalog reads the filesystem, so the part exists by existing."""
    vendor_dir = data_root / "library" / "construction" / "atlantis"
    vendor_dir.mkdir(parents=True, exist_ok=True)
    (vendor_dir / "zimmer-4.5-scanbody.stl").touch()
    return "atlantis/zimmer-4.5-scanbody.stl"


def landed(settings, product_root, worker=None):
    """A client over a DONE run, with the fake worker exposed for capture."""
    worker = worker or FakeWorker(summary=summary_for([row(4), row(13)]))
    client = client_with(settings, worker)
    seed_ready(product_root)
    assert client.post(f"/api/case-sessions/{CASE}/run").status_code == 200
    return client, worker


def put_choices(client, **overrides):
    return client.put(f"/api/case-sessions/{CASE}/choices",
                      json={**CHOICES, **overrides})


def session_of(product_root):
    return SessionStore(product_root).load(CASE)


class TestThePartChangeReEmits:
    def test_the_request_names_its_mode_and_its_source_run(
            self, settings, product_root):
        client, worker = landed(settings, product_root)
        other = second_part(settings.data_root)
        source_run_id = session_of(product_root).run.run_id
        res = put_choices(client, construction_path=other)
        assert res.status_code == 200, res.text
        # two submits: the run, then the re-emit
        (_run_case_id, _run_req), (case_id, reemit_req) = worker.submitted
        assert case_id == CASE
        assert reemit_req["mode"] == "reemit"
        assert reemit_req["source_run_id"] == source_run_id
        assert reemit_req["run_id"] != source_run_id
        assert reemit_req["selection"]["construction_path"] == other

    def test_the_new_run_lands_done_and_the_rungs_survive(
            self, settings, product_root):
        client, _ = landed(settings, product_root)
        old_run_id = session_of(product_root).run.run_id
        assert put_choices(client, gingival_offset_mm=0.1).status_code == 200
        session = session_of(product_root)
        assert session.run is not None and session.run.state == "done"
        assert session.run.run_id != old_run_id
        # THE POINT: the reviews stand — the pose they attested is untouched
        assert session.sites["4"].status is SiteStatus.READY
        assert session.sites["13"].status is SiteStatus.READY

    def test_the_confirmation_and_every_draft_fall_explicitly(
            self, settings, product_root):
        from bff.session import (AlignmentEvidence, ConfirmationRecord)
        client, _ = landed(settings, product_root)
        store = SessionStore(product_root)
        session = store.load(CASE)
        run_id = session.run.run_id
        session.confirmation = ConfirmationRecord(
            at="2026-08-03T00:00:00+00:00", run_id=run_id,
            evidence_sha256="c0ffee".ljust(64, "0"),
            dispositions={"4": "release", "13": "release"},
            acknowledged_flags=[], terms_accepted=True,
            terms_version="placeholder-v1")
        session.sites["4"].exception_intent = "2026-08-03T00:00:00+00:00"
        session.adjust_decision = None
        store.save(session)
        assert put_choices(client, gingival_offset_mm=0.1).status_code == 200
        session = session_of(product_root)
        # hazard 4: the QC evidence is cap+pose and would verify unchanged while
        # the product changed underneath — the confirmation falls, stated
        assert session.confirmation is None
        assert session.sites["4"].exception_intent is None

    def test_a_refused_reemit_lands_as_a_refused_run_with_rungs_intact(
            self, settings, product_root):
        worker = FakeWorker(summary=summary_for([row(4), row(13)]))
        client, _ = landed(settings, product_root, worker=worker)
        # the second submit refuses — the design gate's own words
        worker.refusal = "catastrophic design-rule failure — package NOT emitted"
        res = put_choices(client, gingival_offset_mm=0.1)
        assert res.status_code == 200, res.text
        session = session_of(product_root)
        assert session.run is not None and session.run.state == "refused"
        assert "NOT emitted" in session.run.refusal
        assert session.sites["4"].status is SiteStatus.READY

    def test_the_activity_names_the_act_and_its_source(self, settings,
                                                       product_root):
        client, _ = landed(settings, product_root)
        source_run_id = session_of(product_root).run.run_id
        assert put_choices(client, gingival_offset_mm=0.1).status_code == 200
        words = " ".join(e.detail for e in session_of(product_root).activity)
        assert f"re-emitting run {source_run_id}'s poses" in words


class TestWhatStillRetires:
    def test_a_jaw_change_keeps_the_full_retirement(self, settings, product_root):
        client, worker = landed(settings, product_root)
        submits_before = len(worker.submitted)
        assert put_choices(client, jaw="lower").status_code == 200
        session = session_of(product_root)
        assert session.run is None, "a jaw change moves the alignment's own input"
        assert session.sites["4"].status is not SiteStatus.READY
        assert len(worker.submitted) == submits_before  # nothing was re-emitted

    def test_without_a_done_run_the_old_boundary_stands(self, settings,
                                                        product_root):
        worker = FakeWorker(summary=summary_for([row(4), row(13)]))
        client = client_with(settings, worker)
        seed_ready(product_root)
        other = second_part(settings.data_root)
        # no run yet: a part change simply retires previews, submits nothing
        assert put_choices(client, construction_path=other).status_code == 200
        assert worker.submitted == []
        assert session_of(product_root).run is None

    def test_a_turnaround_only_change_still_retires_nothing(
            self, settings, product_root):
        client, worker = landed(settings, product_root)
        run_id = session_of(product_root).run.run_id
        submits_before = len(worker.submitted)
        assert put_choices(client, turnaround="rush").status_code == 200
        session = session_of(product_root)
        assert session.run.run_id == run_id
        assert session.run.state == "done"
        assert len(worker.submitted) == submits_before
