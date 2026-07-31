"""PROVENANCE (gap group ``provenance``, 2026-07-31): what happened to this case, and
what the numbers on it now say.

Three server-side surfaces, all READS except one body-less compute trigger:

  - ``GET /api/case-sessions/{id}/activity`` — THE ACTIVITY LOG. A bounded,
    append-only narrative written SERVER-SIDE at the point each act lands, plus the
    per-site rework provenance the worker already keeps on disk (the run directory's
    ``<case>-<tooth>-implant.json`` ``adjustments`` list). No route anywhere accepts
    an entry: a client-writable log is a channel for writing claims into the record,
    and a browser-local list would be a lie wearing an audit trail's clothes.
  - ``POST .../sites/{tooth}/re-preview`` — RE-READ A SITE WITHOUT APPLYING A TOOL.
    Body-less. It re-derives the row's measurements over the pose that is actually on
    disk, says whether anything moved, and NAMES what a shipped record cannot re-judge.
  - ``GET .../sites/{tooth}/acceptance`` — the acceptance catalog's own evaluation of
    THIS site, for the workspace: each measured value beside the band it falls in and
    the band's own thresholds. The design's three-lever client-side budget is
    deliberately NOT ported (see the class docstring).
"""
from __future__ import annotations

import json

import pytest

from bff.config import Settings
from bff.resources import adjust as adjust_resource
from bff.session import ACTIVITY_WINDOW, SessionStore, SiteStatus

from conftest import make_data_tree
from test_assurance import PACKAGE_FILES, landed_client
from test_adjust_tools import materialize_proof, outcome, stub_tools
from test_run_resource import FakeWorker, client_with, row, seed_ready


CASE = "neodent-gm"
BASE = f"/api/case-sessions/{CASE}"


@pytest.fixture
def product_root(tmp_path):
    return tmp_path / "product"


@pytest.fixture
def data_root(tmp_path):
    return make_data_tree(tmp_path / "data")


@pytest.fixture
def settings(data_root, product_root) -> Settings:
    return Settings(data_root=data_root, product_root=product_root)


def events(client) -> list:
    """The activity log's event words, newest first — what the log SAYS happened."""
    body = client.get(f"{BASE}/activity").json()
    return [entry["event"] for entry in body["entries"]]


def seated_stub(monkeypatch, payload=None, calls=None):
    """Replace the panes' read with a double. The physics is the worker suite's; what
    these tests own is what the BFF does with the reading."""
    payload = payload if payload is not None else {
        "tooth": 4, "preview": False, "stats": {"rms_mm": 0.43, "p90_mm": 0.71}}

    def stub(case, run_dir, tooth):
        if calls is not None:
            calls.append({"case": case.id, "run_dir": run_dir, "tooth": tooth})
        return payload

    monkeypatch.setattr(adjust_resource, "seated_payload", stub)
    return payload


# --- the activity log ---------------------------------------------------------------------

class TestTheActivityLogIsWrittenServerSide:
    """THE HONESTY QUESTION, decided first (the gap's own instruction). The log is
    appended by the SAME mutation that lands each act, inside the same CAS write —
    so an entry exists exactly when the act it names actually landed. Nothing a
    client sends can add, edit or remove one."""

    def test_a_case_nobody_has_touched_has_an_honestly_empty_log(self, settings):
        client = client_with(settings, FakeWorker())
        body = client.get(f"{BASE}/activity").json()
        assert body["case_id"] == CASE
        assert body["entries"] == []
        assert body["recorded"] == 0
        assert body["window"] == ACTIVITY_WINDOW
        assert body["site_adjustments"] == []

    def test_an_unknown_case_is_a_404(self, settings):
        client = client_with(settings, FakeWorker())
        assert client.get("/api/case-sessions/nope/activity").status_code == 404

    def test_the_run_records_both_its_authorization_and_its_landing(
            self, settings, product_root):
        client = landed_client(settings, product_root, [row(4), row(13)])
        assert events(client)[:2] == ["run-landed", "run-authorized"]
        entries = client.get(f"{BASE}/activity").json()["entries"]
        # WHEN, which no record on this session could answer before: the run receipt
        # carries a state and a run id, never a timestamp
        assert all(entry["at"] for entry in entries)

    def test_a_refused_run_is_recorded_as_refused_not_as_a_landing(
            self, settings, product_root):
        seed_ready(product_root)
        client = client_with(settings, FakeWorker(refusal="no confirmed site"))
        client.post(f"{BASE}/run")
        assert events(client)[0] == "run-refused"

    def test_per_site_acts_carry_their_tooth(self, settings, product_root):
        client = landed_client(settings, product_root, [row(4), row(13)])
        entries = client.get(f"{BASE}/activity").json()["entries"]
        client.delete(f"{BASE}/sites/4/review")
        withdrawn = client.get(f"{BASE}/activity").json()["entries"][0]
        assert withdrawn["event"] == "site-review-withdrawn"
        assert withdrawn["tooth"] == 4
        # and a case-level act names no tooth rather than inventing one
        assert all(e["tooth"] is None for e in entries if e["event"].startswith("run-"))

    def test_the_signing_acts_are_recorded(self, settings, product_root):
        client = landed_client(settings, product_root, [row(4), row(13)])
        assert client.post(f"{BASE}/confirm",
                           json={"terms_accepted": True}).status_code == 200
        assert client.post(f"{BASE}/payment", json={"authorize": True}).status_code == 200
        assert client.post(f"{BASE}/release").status_code == 200
        assert events(client)[:3] == ["released", "payment-authorized", "confirmed"]

    def test_the_delivery_door_back_is_recorded_too(self, settings, product_root):
        client = landed_client(settings, product_root, [row(4), row(13)])
        client.post(f"{BASE}/confirm", json={"terms_accepted": True})
        client.post(f"{BASE}/delivery/reset")
        assert events(client)[0] == "delivery-reset"

    def test_the_log_is_bounded_and_says_how_many_acts_it_did_not_keep(
            self, settings, product_root):
        """WATCH session.json SIZE: the store re-reads the document per request and a
        size test pins it, so the log is a WINDOW on the newest acts, never a complete
        audit trail. ``recorded`` is the total, so the surface can say so instead of
        implying the window is everything."""
        client = landed_client(settings, product_root, [row(4), row(13)])
        for _ in range(ACTIVITY_WINDOW + 5):
            client.delete(f"{BASE}/sites/4/review")
            client.post(f"{BASE}/sites/4/review")
        body = client.get(f"{BASE}/activity").json()
        assert len(body["entries"]) == ACTIVITY_WINDOW
        assert body["recorded"] > ACTIVITY_WINDOW
        # the WINDOW keeps the newest: the oldest surviving entry is not the run's
        assert "run-authorized" not in [e["event"] for e in body["entries"]]

    def test_session_json_stays_small_with_a_full_log(self, settings, product_root):
        client = landed_client(settings, product_root, [row(4), row(13)])
        for _ in range(ACTIVITY_WINDOW + 5):
            client.delete(f"{BASE}/sites/4/review")
            client.post(f"{BASE}/sites/4/review")
        session_file = product_root / CASE / "session.json"
        assert session_file.stat().st_size < 32_768

    def test_the_case_reset_is_recorded_and_the_log_survives_it(
            self, settings, product_root):
        """THE ONE FIELD THAT SURVIVES ``POST /reset``, deliberately: a log that
        erased the record of its own erasure would hide the one act nobody could
        otherwise see."""
        client = landed_client(settings, product_root, [row(4), row(13)])
        before = client.get(f"{BASE}/activity").json()["recorded"]
        assert client.post(f"{BASE}/reset").status_code == 200
        body = client.get(f"{BASE}/activity").json()
        assert body["entries"][0]["event"] == "case-reset"
        assert body["recorded"] == before + 1
        # and the reset really did reset everything else
        assert client.get(BASE).json()["session"]["run_state"] == "none"


class TestNoClientCanWriteTheLog:
    """AM-4, applied to the record itself. An activity list a browser could POST to
    would be a channel for writing claims into the case's history — the exact thing
    the status allowlist exists to prevent, one layer up."""

    def test_there_is_no_route_that_writes_an_activity_entry(self, settings):
        client = client_with(settings, FakeWorker())
        res = client.post(f"{BASE}/activity",
                          json={"event": "released", "detail": "trust me"})
        assert res.status_code in (404, 405)

    def test_a_smuggled_activity_field_is_refused_on_a_legitimate_write(self, settings):
        client = client_with(settings, FakeWorker())
        res = client.put(f"{BASE}/choices",
                         json={"jaw": "upper", "activity": [{"event": "released"}]})
        assert res.status_code == 422

    def test_reading_the_log_writes_nothing(self, settings, product_root):
        client = client_with(settings, FakeWorker())
        client.get(f"{BASE}/activity")
        assert not product_root.exists()


class TestThePerSiteReworkProvenanceOnDiskIsReadBack:
    """The worker has kept this all along and no endpoint read it: every adopted
    adjustment appends ``{ts, operation, who, detail}`` to an append-only
    ``adjustments`` list on the run directory's ``<case>-<tooth>-implant.json``
    (case_prep/application/adjust.py ``_finish_adjustment``)."""

    def write_record(self, client, product_root, tooth: int, entries) -> None:
        run_id = client.get(f"{BASE}/run").json()["run_id"]
        path = (product_root / CASE / "runs" / run_id
                / f"{CASE}-{tooth}-implant.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"tooth": tooth, "adjustments": entries}))

    def test_the_shipped_records_adjustments_reach_the_wire(
            self, settings, product_root):
        client = landed_client(settings, product_root, [row(4), row(13)])
        self.write_record(client, product_root, 4, [
            {"ts": "2026-07-30T09:15:00", "operation": "rotation",
             "who": "operator (no identity is captured)",
             "detail": "rotated +5.0° about the part axis"}])
        body = client.get(f"{BASE}/activity").json()
        assert body["site_adjustments"] == [{
            "tooth": 4, "at": "2026-07-30T09:15:00", "operation": "rotation",
            "who": "operator (no identity is captured)",
            "detail": "rotated +5.0° about the part axis"}]

    def test_a_site_with_no_record_on_disk_contributes_nothing(
            self, settings, product_root):
        client = landed_client(settings, product_root, [row(4), row(13)])
        assert client.get(f"{BASE}/activity").json()["site_adjustments"] == []

    def test_a_corrupt_record_is_skipped_not_a_500(self, settings, product_root):
        """The worklist's per-row error contract, applied here: one unreadable file
        must not take down the case's whole narrative."""
        client = landed_client(settings, product_root, [row(4), row(13)])
        run_id = client.get(f"{BASE}/run").json()["run_id"]
        path = product_root / CASE / "runs" / run_id / f"{CASE}-4-implant.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json")
        self.write_record(client, product_root, 13, [
            {"ts": "2026-07-30T10:00:00", "operation": "best-fit", "who": "operator",
             "detail": "refined at 0.30mm"}])
        body = client.get(f"{BASE}/activity").json()
        assert [a["tooth"] for a in body["site_adjustments"]] == [13]


# --- re-read a site without applying a tool -------------------------------------------------

class TestReReadingASiteWithoutApplyingATool:
    """THE GAP: ``_fold_outcome`` re-derives every measurement, but only a TOOL ever
    calls it — so an operator who wants the row re-checked has to pretend to adjust
    something. This route is that re-read, and it applies nothing.

    THE DESIGN'S ``repreviewLabel`` PRE-ANNOUNCES ITS OWN VERDICT ("this will pass").
    That is precisely the client-side verdict the product forbids: a button label may
    promise a re-READ, never an outcome. What comes back here is what the server
    measured."""

    def test_no_completed_run_refuses_naming_that(self, settings, monkeypatch):
        seated_stub(monkeypatch)
        client = client_with(settings, FakeWorker())
        res = client.post(f"{BASE}/sites/4/re-preview")
        assert res.status_code == 422
        assert "no completed current run" in res.json()["detail"]

    def test_a_tooth_the_case_does_not_have_is_a_404(self, settings, product_root,
                                                     monkeypatch):
        calls = []
        seated_stub(monkeypatch, calls=calls)
        client = landed_client(settings, product_root, [row(4), row(13)])
        assert client.post(f"{BASE}/sites/99/re-preview").status_code == 404
        assert calls == [], "no read may run for a site that does not exist"

    def test_an_unchanged_row_re_reads_as_unchanged(self, settings, product_root,
                                                    monkeypatch):
        # the stub reports exactly what row(4) already carries
        seated_stub(monkeypatch)
        client = landed_client(settings, product_root, [row(4), row(13)])
        body = client.post(f"{BASE}/sites/4/re-preview").json()
        assert body["tooth"] == 4
        assert body["changed"] is False
        assert body["rederived"] == {"deviation_rms_mm": 0.43,
                                     "deviation_p90_mm": 0.71}
        assert body["previous"] == body["rederived"]

    def test_a_moved_number_is_folded_into_the_row(self, settings, product_root,
                                                   monkeypatch):
        seated_stub(monkeypatch, payload={
            "tooth": 4, "preview": False, "stats": {"rms_mm": 0.91, "p90_mm": 1.4}})
        client = landed_client(settings, product_root, [row(4), row(13)])
        body = client.post(f"{BASE}/sites/4/re-preview").json()
        assert body["changed"] is True
        assert body["previous"]["deviation_rms_mm"] == 0.43
        assert body["rederived"]["deviation_rms_mm"] == 0.91
        # and the RUN ROW is what moved — the assurance projection reads it verbatim
        assurance = client.get(f"{BASE}/assurance").json()
        moved = next(s for s in assurance["sites"] if s["tooth"] == 4)
        assert moved["deviation_rms_mm"] == 0.91

    def test_it_moves_no_rung(self, settings, product_root, monkeypatch):
        """A re-read is not a rework: it applies nothing, so the ladder does not
        move. ``status.adjust`` is the TOOLS' writer, and only theirs."""
        seated_stub(monkeypatch, payload={
            "tooth": 4, "preview": False, "stats": {"rms_mm": 0.91, "p90_mm": 1.4}})
        client = landed_client(settings, product_root, [row(4), row(13)])
        client.post(f"{BASE}/sites/4/re-preview")
        store = SessionStore(product_root)
        assert store.load(CASE).sites["4"].status is SiteStatus.READY

    def test_it_names_what_a_shipped_record_cannot_re_judge(
            self, settings, product_root, monkeypatch):
        """``rim_agreement_mm`` was anchored on run-time data the shipped record does
        not carry, and ``guidance`` is a function of a dozen inputs it does not carry
        either (case_prep.application.adjust.STALE_AFTER_REWORK). A re-read that
        invented either would put a different number under the same name."""
        seated_stub(monkeypatch)
        client = landed_client(settings, product_root,
                               [row(4, level="attention"), row(13)])
        # a tool ran first, so the row already carries its stale markers
        stub_tools(monkeypatch, result=outcome(4))
        client.post(f"{BASE}/sites/4/rotation", json={"step_deg": 1.0})
        body = client.post(f"{BASE}/sites/4/re-preview").json()
        assert body["stale_metrics"] == ["rim_agreement_mm", "guidance"]

    def test_a_clean_row_stays_clean_through_a_re_read(self, settings, product_root,
                                                       monkeypatch):
        """Nothing MOVED, so nothing became stale: a re-read must not manufacture a
        staleness marker the case has not earned."""
        seated_stub(monkeypatch)
        client = landed_client(settings, product_root, [row(4), row(13)])
        body = client.post(f"{BASE}/sites/4/re-preview").json()
        assert body["stale_metrics"] == []

    def test_a_changed_re_read_retires_the_confirmation(self, settings, product_root,
                                                        monkeypatch):
        """THE EVIDENCE BOUNDARY (``session.clear_confirmation``): the sealed row's
        numbers moved, so nothing signed over the old ones stands."""
        client = landed_client(settings, product_root, [row(4), row(13)])
        assert client.post(f"{BASE}/confirm",
                           json={"terms_accepted": True}).status_code == 200
        seated_stub(monkeypatch, payload={
            "tooth": 4, "preview": False, "stats": {"rms_mm": 0.91, "p90_mm": 1.4}})
        client.post(f"{BASE}/sites/4/re-preview")
        assert client.get(BASE).json()["session"]["confirmed"] is False

    def test_an_unchanged_re_read_leaves_the_confirmation_standing(
            self, settings, product_root, monkeypatch):
        client = landed_client(settings, product_root, [row(4), row(13)])
        assert client.post(f"{BASE}/confirm",
                           json={"terms_accepted": True}).status_code == 200
        seated_stub(monkeypatch)
        client.post(f"{BASE}/sites/4/re-preview")
        assert client.get(BASE).json()["session"]["confirmed"] is True

    def test_the_re_read_is_recorded_in_the_activity_log(self, settings, product_root,
                                                         monkeypatch):
        seated_stub(monkeypatch)
        client = landed_client(settings, product_root, [row(4), row(13)])
        client.post(f"{BASE}/sites/4/re-preview")
        entry = client.get(f"{BASE}/activity").json()["entries"][0]
        assert entry["event"] == "site-re-read"
        assert entry["tooth"] == 4

    def test_it_returns_the_panes_payload_and_the_whole_case(
            self, settings, product_root, monkeypatch):
        payload = seated_stub(monkeypatch)
        client = landed_client(settings, product_root, [row(4), row(13)])
        body = client.post(f"{BASE}/sites/4/re-preview").json()
        assert body["pane_payload"] == payload
        assert body["case"]["case"]["id"] == CASE


class TestTheGateSaysWhenItsWordsPredateARework:
    """``_fold_outcome`` re-derives the measurements and never touches
    ``row['guidance']`` — it cannot, and says so. What was missing is the SERVER
    saying so on the document the operator reads: Deliver's assurance table renders
    ``gate.actions`` for every row, so pre-rework gate words read as current."""

    def test_a_clean_row_reports_a_gate_that_is_not_stale(self, settings, product_root):
        client = landed_client(settings, product_root, [row(4), row(13)])
        site = client.get(f"{BASE}/assurance").json()["sites"][0]
        assert site["gate"]["stale"] is False

    def test_a_reworked_row_reports_its_gate_as_stale(self, settings, product_root,
                                                      monkeypatch):
        client = landed_client(settings, product_root,
                               [row(4, level="attention"), row(13)])
        stub_tools(monkeypatch, result=outcome(4))
        assert client.post(f"{BASE}/sites/4/rotation",
                           json={"step_deg": 1.0}).status_code == 200
        materialize_proof(client, product_root, 4)
        site = next(s for s in client.get(f"{BASE}/assurance").json()["sites"]
                    if s["tooth"] == 4)
        assert "guidance" in site["stale_metrics"]
        assert site["gate"]["stale"] is True
        # the WORDS stay verbatim — the projection annotates, it never rewrites
        assert site["gate"]["level"] == "attention"


# --- the acceptance projection --------------------------------------------------------------

class TestTheAcceptanceProjectionReachesTheWorkspace:
    """WHAT IS DELIBERATELY NOT PORTED: the design's ``budget`` (flow.dc.html
    1363-1372) slices a synthetic tolerance three ways — rotation error, diameter
    error and residual scatter, each divided by a tolerance the BROWSER holds. None
    of those three quantities exists here, and the product's deviation is MEASURED
    over real mesh. What is served instead is what the pipeline actually computes and
    the acceptance catalog actually cites: the value, the band it falls in, and the
    band's own thresholds."""

    def test_no_run_yet_is_a_404_that_says_why(self, settings):
        client = client_with(settings, FakeWorker())
        res = client.get(f"{BASE}/sites/4/acceptance")
        assert res.status_code == 404
        assert "no completed current run" in res.json()["detail"]

    def test_a_tooth_the_run_never_aligned_is_a_404(self, settings, product_root):
        client = landed_client(settings, product_root, [row(13)])
        res = client.get(f"{BASE}/sites/4/acceptance")
        assert res.status_code == 404
        assert "carries no verdict" in res.json()["detail"]

    def test_every_metric_carries_its_value_band_and_the_bands_own_thresholds(
            self, settings, product_root):
        client = landed_client(settings, product_root, [row(4), row(13)])
        body = client.get(f"{BASE}/sites/4/acceptance").json()
        assert body["tooth"] == 4
        assert body["run_id"]
        by_key = {m["key"]: m for m in body["metrics"]}
        rms = by_key["deviation_rms_mm"]
        assert rms["value"] == 0.43
        assert rms["band"] == "review"
        # THE ROOM LEFT, from the catalog's own numbers — never a client's tolerance
        assert rms["bands"] == {"pass": 0.2, "review": 0.5}
        assert rms["industry_ref"]["source"]

    def test_the_overall_band_is_the_catalogs_own_worst(self, settings, product_root):
        client = landed_client(settings, product_root, [row(4), row(13)])
        body = client.get(f"{BASE}/sites/4/acceptance").json()
        bands = {m["band"] for m in body["metrics"]}
        assert body["overall_band"] in bands
        assert body["overall_band"] == "review"

    def test_metrics_the_row_could_not_measure_are_listed_missing(
            self, settings, product_root):
        thin = row(4)
        thin.pop("deviation_rms_mm")
        client = landed_client(settings, product_root, [thin, row(13)])
        body = client.get(f"{BASE}/sites/4/acceptance").json()
        assert "deviation_rms_mm" in body["missing"]
        by_key = {m["key"]: m for m in body["metrics"]}
        assert by_key["deviation_rms_mm"]["band"] == "missing"

    def test_it_carries_the_rows_own_staleness_markers(self, settings, product_root,
                                                       monkeypatch):
        client = landed_client(settings, product_root,
                               [row(4, level="attention"), row(13)])
        stub_tools(monkeypatch, result=outcome(4))
        client.post(f"{BASE}/sites/4/rotation", json={"step_deg": 1.0})
        body = client.get(f"{BASE}/sites/4/acceptance").json()
        assert body["stale_metrics"] == ["rim_agreement_mm", "guidance"]

    def test_reading_it_writes_nothing(self, settings, product_root):
        client = landed_client(settings, product_root, [row(4), row(13)])
        before = (product_root / CASE / "session.json").read_bytes()
        client.get(f"{BASE}/sites/4/acceptance")
        assert (product_root / CASE / "session.json").read_bytes() == before
