"""THE CASE-SESSION RESOURCE (plan §3/§7 slices 1+4): the worklist, the flow-shaped
case resource, and the first ACTIONS — detect (a compute trigger) and choices (operator
acts) — derived from worker facts + the session store, never from a client's claims.

The one structural promise these tests must keep enforceable (grill AM-4): site-queue
statuses, verdicts and gate outcomes are DERIVED. Slice 4 deliberately ends GET-only —
the new invariant is stronger than the old one, not weaker: every non-GET route sits on
an explicit allowlist, and NO allowlisted request model carries a status-shaped field —
asserted on the route table AND the Pydantic models, so a future PATCH (or a "status"
field slipped into a legitimate write) cannot arrive unnoticed.
"""
from __future__ import annotations

import dataclasses
import threading

import pytest
from fastapi.testclient import TestClient

from bff.main import create_app
from bff.resources import case_sessions
from bff.session import (ConfirmationRecord, RunSession, SeatedSelection,
                         SessionStore, SiteSession, SiteStatus)


class InterferingStore(SessionStore):
    """A store whose ``load`` is immediately followed by a rival's write — the smallest
    deterministic interleaving that forces a CAS conflict on the caller's save. With
    ``interferences=1`` the handler's retry lands on a quiet second attempt; with more,
    every attempt loses and the handler must 409."""

    def __init__(self, root, interferences: int):
        super().__init__(root)
        self.interferences = interferences

    def load(self, case_id):
        session = super().load(case_id)
        if self.interferences > 0:
            self.interferences -= 1
            rival = SessionStore(self.root).load(case_id)
            rival.adjust_visited = True  # a server-side fact, same door the flow uses
            SessionStore(self.root).save(rival)
        return session


class SystemSwitchingStore(SessionStore):
    """A store whose FIRST ``load`` is immediately followed by a rival system SWITCH —
    the dangling-variant race from the 5a verification: a declaration judged against
    the pre-switch system must be re-judged against the switched document, never
    landed on it with a 200."""

    def __init__(self, root, model: str):
        super().__init__(root)
        self.model = model
        self.fired = False

    def load(self, case_id):
        session = super().load(case_id)
        if not self.fired:
            self.fired = True
            rival = SessionStore(self.root).load(case_id)
            rival.system = self.model   # what PUT /system persists (no sites declared yet)
            SessionStore(self.root).save(rival)
        return session
from case_prep.application.catalog import UnknownSelection
from case_prep.application.detection import (DetectedSite, DetectionResult,
                                             ScanUnreadable, SuggestedSiteCapture)
from case_prep.application.preview import PreviewRefused

CAP_PASS = {"verdict": "pass", "rim_z_mm": 1.2, "checks": []}
CAP_RESCAN = {"verdict": "rescan", "rim_z_mm": None,
              "checks": [{"name": "rim_arc", "value": 0.31, "bound_pass": 0.75,
                          "bound_rescan": 0.5, "verdict": "rescan",
                          "message": "Only 31% of the rim arc is captured."}]}


def stub_detection(jaw_reading: str | None = None) -> DetectionResult:
    """A detection result shaped exactly like the application layer's — teeth 4 and 13
    match the conftest tree's curated sites; one extra proposal has no tooth to inherit.
    ``jaw_reading`` defaults to None (a case not yet asserting a geometric reading, the
    pre-§10-AM shape every existing test here still exercises) — the resource never
    reads ``crown_axis`` (that physics is pinned worker-side, test_detection.py), so a
    placeholder is honest here."""
    return DetectionResult(
        proposals=(
            DetectedSite(center=(1.0, 2.0, 3.0), void_ratio=0.10,
                         rim_below_cusps_mm=0.5, tooth_guess=4, capture=CAP_PASS),
            DetectedSite(center=(40.0, 2.0, 3.0), void_ratio=0.35,
                         rim_below_cusps_mm=1.1, tooth_guess=None, capture=CAP_RESCAN),
        ),
        suggested=(
            SuggestedSiteCapture(tooth=4, center=(1.0, 2.0, 3.0), capture=CAP_PASS),
            SuggestedSiteCapture(tooth=13, center=(4.0, 5.0, 6.0), capture=CAP_RESCAN),
        ),
        crown_axis=(0.0, 0.0, 0.0),
        jaw_reading=jaw_reading,
    )


class TestWorklist:
    def test_one_row_per_case_with_the_site_rollup(self, client):
        rows = client.get("/api/case-sessions").json()
        assert len(rows) == 1
        (row,) = rows
        assert row["id"] == "neodent-gm"
        assert row["doctor"] == "Doctor Neodent GM"
        assert row["jaw"] == "upper"
        assert row["suggested_model"] == "neodent-gm"
        assert row["sites"] == {"total": 2, "declared": 0, "ready": 0, "flagged": 0}
        assert row["run_state"] == "none"
        assert row["confirmed"] is False
        # choices_complete is the EFFECTIVE fact (client 2026-07-27): this case's
        # suggestions + the standing relief default cover all three, so a fresh
        # session is already complete on the worklist
        assert row["choices_complete"] is True

    def test_persisted_session_state_reaches_the_rollup(self, settings):
        # state changes arrive ONLY via the server-side store — this is the same door
        # later slices use, and the worklist must reflect it on the next read
        store = SessionStore(settings.product_root)
        s = store.load("neodent-gm")
        s.sites["13"] = SiteSession(status=SiteStatus.FLAGGED, declared_variant="5020")
        s.run = RunSession(job_id="job-1", state="done")
        store.save(s)
        client = TestClient(create_app(settings))
        (row,) = client.get("/api/case-sessions").json()
        assert row["sites"] == {"total": 2, "declared": 1, "ready": 0, "flagged": 1}
        assert row["run_state"] == "done"

    def test_the_row_carries_the_scan_cards_discovery_facts(self, client):
        """The design's scan card states teeth, system and file size beside the
        practice (gap ``practice-and-batch-on-a-case``, 2026-07-31). PRACTICE was
        already built under the name ``doctor``, and SYSTEM under
        ``suggested_model``; these two are the rest."""
        (row,) = client.get("/api/case-sessions").json()
        assert row["teeth"] == [4, 13]
        assert row["scan_bytes"] == 0        # the fixture's STL is an empty touch()
        assert row["doctor"] == "Doctor Neodent GM"      # the design's "practice"
        assert row["suggested_model"] == "neodent-gm"    # the design's "system"


class TestCaseSessionDetail:
    def test_an_unknown_case_is_a_404(self, client):
        assert client.get("/api/case-sessions/no-such-case").status_code == 404

    def test_the_flow_shape(self, client):
        body = client.get("/api/case-sessions/neodent-gm").json()
        assert body["case"] == {
            "id": "neodent-gm",
            "doctor": "Doctor Neodent GM",
            "jaw": "upper",
            "scan_filename": "upper_jaw.stl",
            "suggested_model": "neodent-gm",
            "suggested_construction": "dess/neodent-gm-scanbody.stl",
            # the scan card's discovery facts (2026-07-31): the curated teeth and the
            # file's size on disk — the fixture's STL is an empty touch(), so 0 bytes
            "teeth": [4, 13],
            "scan_bytes": 0,
        }
        assert [s["tooth"] for s in body["sites"]] == [4, 13]
        assert all(s["status"] == "detected" for s in body["sites"])
        assert body["sites"][0]["center"] == [1.0, 2.0, 3.0]
        # the catalog rides along so Declare can render without a second round of calls
        assert {g["model"] for g in body["catalog"]["groups"]} == {"neodent-gm"}
        assert [c["path_id"] for c in body["catalog"]["constructions"]] == [
            "dess/neodent-gm-scanbody.stl"]
        # nothing declared -> no ceilings to read
        assert body["relief_ceilings"] == []
        # the effective system: the suggestion, and the payload SAYS so (AM-8)
        assert body["system"] == {"effective_model": "neodent-gm",
                                  "source": "suggested"}
        # detection has not run; choices not yet made — the RAW acts stay honestly
        # None, while the EFFECTIVE values (client 2026-07-27: the automation uses
        # the suggestions) fall back with their attribution, the SystemView pattern
        # mirrored: suggestion for construction and jaw, the standing 0.20mm default
        # for relief — and ``complete`` is the EFFECTIVE completeness
        assert body["detection"] is None
        assert body["choices"] == {
            "construction_path": None,
            "jaw": None,
            "gingival_offset_mm": None,
            "turnaround": None,
            "gingival_offset_default_mm": 0.2,
            "effective_construction": {"value": "dess/neodent-gm-scanbody.stl",
                                       "source": "suggested"},
            "effective_jaw": {"value": "upper", "source": "suggested"},
            "effective_relief": {"value": 0.2, "source": "default"},
            # a case nobody expedited is a standard case — the standing default,
            # attributed like the others (2026-07-31)
            "effective_turnaround": {"value": "standard", "source": "default"},
            # the card's own per-site units ride with the choices so the Intake
            # chooser prints the server's money, never its own (§10-AB.4)
            "turnaround_options": [
                {"value": "standard", "unit_amount_cents": 3200, "currency": "USD"},
                {"value": "rush", "unit_amount_cents": 4800, "currency": "USD"},
            ],
            "complete": True,
            # no detection has run yet -- nothing to cross-check against, so honestly
            # absent rather than a warning about a reading that does not exist
            "jaw_advisory": None,
        }
        assert body["session"] == {
            "tenant_id": "local",
            "adjust_visited": False,
            # the Delivery-vs-Skip fork (client 2026-07-27) — None until it is
            # faced, and None again once the run boundary clears its verdicts
            "adjust_decision": None,
            "run_state": "none",
            "run_refusal": None,   # 5c: a refused run's words ride here, verbatim
            "confirmed": False,
            "payment_authorized": False,
            # the disclosure chain (slice 8): records verbatim once they exist,
            # and "released" as a CURRENT-run verdict — all honestly empty here
            "confirmation": None,
            "payment": None,
            "release": None,
            # what a release WOULD disclose (client 2026-07-27 #6) — absent until a
            # confirmation covers the current done run: there is no honest promise
            # to make about a case nobody has confirmed
            "release_preview": None,
            "released": False,
        }

    def test_a_site_carries_its_preview_seat_facts_on_the_wire(self, settings):
        """Client 2026-07-27 #2: the attestation must be faced again "at the time to
        move forward", so Declare's footer summarizes what each tick attested — which
        needs the seat facts the preview persisted. Read-only worker facts, served
        beside the rung that justified them and cleared with it."""
        store = SessionStore(settings.product_root)
        s = store.load("neodent-gm")
        s.sites["4"] = SiteSession(status=SiteStatus.READY, declared_variant="5020",
                                   seat_method="rim-seat", rim_agreement_mm=0.07)
        store.save(s)
        client = TestClient(create_app(settings))
        sites = {s["tooth"]: s
                 for s in client.get("/api/case-sessions/neodent-gm").json()["sites"]}
        assert sites[4]["seat_method"] == "rim-seat"
        assert sites[4]["rim_agreement_mm"] == 0.07
        # a site with no preview says so honestly rather than inventing a seat
        assert sites[13]["seat_method"] is None
        assert sites[13]["rim_agreement_mm"] is None

    def test_session_statuses_overlay_the_detected_sites(self, settings):
        store = SessionStore(settings.product_root)
        s = store.load("neodent-gm")
        s.sites["13"] = SiteSession(status=SiteStatus.READY, declared_variant="5020")
        store.save(s)
        client = TestClient(create_app(settings))
        sites = {v["tooth"]: v for v in
                 client.get("/api/case-sessions/neodent-gm").json()["sites"]}
        assert sites[13]["status"] == "ready"
        assert sites[13]["declared_variant"] == "5020"
        assert sites[4]["status"] == "detected"

    def test_a_declared_variant_the_catalog_does_not_carry_is_an_error_row(
            self, tmp_path, product_root):
        # the ceiling column must not take the whole resource down: the refusal is a row
        from conftest import make_data_tree
        from bff.config import Settings
        data = make_data_tree(tmp_path / "data2", declared=(None, "9999"))
        client = TestClient(create_app(Settings(data_root=data, product_root=product_root)))
        (ceiling,) = client.get("/api/case-sessions/neodent-gm").json()["relief_ceilings"]
        assert ceiling["variant"] == "9999"
        assert ceiling["max_safe_mm"] is None
        assert "9999" in ceiling["error"]


class TestCaseScan:
    """GET /{id}/scan (plan §7 slice 3): the product's main stage streams the doctor's
    scan through the BFF — the application layer's CaseRecord.scan path, never a
    client-supplied one (no path parameter reaches the filesystem)."""

    @staticmethod
    def _tiny_stl() -> bytes:
        # A REAL (if minimal) binary STL: 80-byte header, uint32 triangle count = 1,
        # one 50-byte triangle record — enough for a parser to accept, small enough
        # to compare byte-for-byte.
        import struct
        header = b"tiny fixture stl".ljust(80, b"\0")
        triangle = struct.pack(
            "<12fH",
            0.0, 0.0, 1.0,        # normal
            0.0, 0.0, 0.0,        # v0
            1.0, 0.0, 0.0,        # v1
            0.0, 1.0, 0.0,        # v2
            0,                    # attribute byte count
        )
        return header + struct.pack("<I", 1) + triangle

    def test_streams_the_case_scan_bytes(self, settings):
        stl = self._tiny_stl()
        (settings.data_root / "scans/doctor-neodent-gm/upper_jaw.stl").write_bytes(stl)
        client = TestClient(create_app(settings))
        res = client.get("/api/case-sessions/neodent-gm/scan")
        assert res.status_code == 200
        assert res.content == stl
        assert res.headers["content-type"] == "model/stl"

    def test_an_unknown_case_scan_is_the_same_404_refusal(self, client):
        res = client.get("/api/case-sessions/no-such-case/scan")
        assert res.status_code == 404
        assert "unknown case" in res.json()["detail"]


class TestDetect:
    """POST /{id}/detect (plan §4): detection fires automatically on Intake; the route
    is a compute TRIGGER that persists what the application layer derived. The physics
    is the worker's (test_detection.py pins it on the real tree); what belongs here is
    orchestration — run-once, persist, refuse, re-derive on explicit ask — so the
    application function is stubbed at the resource seam."""

    def _client_with_stub(self, settings, monkeypatch, result=None):
        calls = []

        def stub(case):
            calls.append(case.id)
            if isinstance(result, Exception):
                raise result
            return result or stub_detection()

        monkeypatch.setattr(case_sessions, "detect", stub)
        return TestClient(create_app(settings)), calls

    def test_an_unknown_case_is_a_404(self, client):
        assert client.post("/api/case-sessions/no-such-case/detect").status_code == 404

    def test_detect_runs_persists_and_returns_the_updated_detail(
            self, settings, monkeypatch):
        client, calls = self._client_with_stub(settings, monkeypatch)
        body = client.post("/api/case-sessions/neodent-gm/detect").json()
        assert calls == ["neodent-gm"]
        # the proposals ride along, tooth guesses honest (None where nothing matched)
        assert [p["tooth_guess"] for p in body["detection"]["proposals"]] == [4, None]
        # every curated site now carries its capture verdict — the chair-side fact
        sites = {s["tooth"]: s for s in body["sites"]}
        assert sites[4]["capture"]["verdict"] == "pass"
        assert sites[13]["capture"]["verdict"] == "rescan"
        # and the store has it: a fresh app (a restart) serves the same facts
        rows = TestClient(create_app(settings)).get("/api/case-sessions").json()
        assert rows[0]["detected"] is True

    def test_re_post_returns_current_state_without_rederiving(
            self, settings, monkeypatch):
        client, calls = self._client_with_stub(settings, monkeypatch)
        client.post("/api/case-sessions/neodent-gm/detect")
        body = client.post("/api/case-sessions/neodent-gm/detect").json()
        assert calls == ["neodent-gm"]  # ONCE — idempotent, not a re-run per click
        assert body["detection"] is not None

    def test_fresh_is_the_explicit_re_ask(self, settings, monkeypatch):
        client, calls = self._client_with_stub(settings, monkeypatch)
        client.post("/api/case-sessions/neodent-gm/detect")
        client.post("/api/case-sessions/neodent-gm/detect?fresh=1")
        assert calls == ["neodent-gm", "neodent-gm"]

    def test_an_unreadable_scan_is_a_422_in_the_workers_words(
            self, settings, monkeypatch):
        client, _ = self._client_with_stub(
            settings, monkeypatch,
            result=ScanUnreadable("the scan upper_jaw.stl holds no surface to detect on"))
        res = client.post("/api/case-sessions/neodent-gm/detect")
        assert res.status_code == 422
        assert "holds no surface" in res.json()["detail"]
        # a refusal persists nothing — the next POST may try again
        assert TestClient(create_app(settings)).get(
            "/api/case-sessions").json()[0]["detected"] is False

    def test_a_choices_put_landing_mid_detect_is_not_clobbered(
            self, settings, monkeypatch):
        """The lost-update race the slice-4 adversarial review demonstrated: detection
        runs for many seconds (7-30s on real cases), Intake auto-fires it on open, and
        the choices panel stays live — so an operator's PUT can land WHILE detect runs.
        The old handler loaded the session BEFORE detect() and saved that stale object
        after, silently wiping the operator's persisted choices: an operator act
        discarded by a write-write race, the exact class AM-4 exists to prevent (only
        via clobber instead of client claim). The route must re-load AFTER detect()
        returns and write ONLY the detection facts onto the fresh document."""
        def detect_with_concurrent_put(case):
            # while detection "runs", the operator's PUT lands over HTTP and persists
            res = TestClient(create_app(settings)).put(
                f"/api/case-sessions/{case.id}/choices", json={
                    "construction_path": "dess/neodent-gm-scanbody.stl",
                    "jaw": "upper",
                    "gingival_offset_mm": 0.2,
                })
            assert res.json()["choices"]["complete"] is True
            return stub_detection()

        monkeypatch.setattr(case_sessions, "detect", detect_with_concurrent_put)
        body = TestClient(create_app(settings)).post(
            "/api/case-sessions/neodent-gm/detect").json()
        # the detail the UI renders carries BOTH facts — detect's save must not have
        # undone the operator's act (nor may the response re-render it as undone)
        assert body["detection"] is not None
        assert body["choices"]["complete"] is True
        # and the store agrees after the dust settles
        persisted = SessionStore(settings.product_root).load("neodent-gm")
        assert persisted.detection is not None
        assert persisted.choices.complete is True


class TestMeasuredVariantSuggestion:
    """Client escalation 2026-08-09 (cap 297589851-neodent-gm tooth 20): detection
    measured the rim DIAMETER per site and nothing about HEIGHT, so a site with no
    CURATED suggestion served ``suggested_variant: None`` with no cross-check at
    all — an operator declared a TALL variant over a visibly SHORT cap and the
    preview seated a 5.4mm barrel onto a ~3.4mm cap. This resource's job is
    precedence (curated beats measured, same door as the jaw reading above) and
    honest attribution — the worker's own proposal (test_detection.py pins the
    physics), never a comparison this layer invents."""

    def _client_detected_with(self, settings, monkeypatch, result):
        def stub(case):
            return result

        monkeypatch.setattr(case_sessions, "detect", stub)
        client = TestClient(create_app(settings))
        client.post("/api/case-sessions/neodent-gm/detect")
        return client

    def test_a_measured_proposal_serves_when_no_curated_value_exists(
            self, settings, monkeypatch):
        result = dataclasses.replace(stub_detection(), suggested=(
            SuggestedSiteCapture(tooth=4, center=(1.0, 2.0, 3.0), capture=CAP_PASS,
                                 measured_cap_height_mm=None, proposed_variant=None),
            SuggestedSiteCapture(tooth=13, center=(4.0, 5.0, 6.0), capture=CAP_RESCAN,
                                 measured_cap_height_mm=3.6, proposed_variant="5020"),
        ))
        client = self._client_detected_with(settings, monkeypatch, result)
        sites = {s["tooth"]: s
                for s in client.get("/api/case-sessions/neodent-gm").json()["sites"]}
        assert sites[13]["suggested_variant"] == "5020"
        assert sites[13]["suggested_variant_source"] == "measured"
        # nothing measured for tooth 4 -> honestly absent, not a stale carry-over
        assert sites[4]["suggested_variant"] is None
        assert sites[4]["suggested_variant_source"] is None

    def test_the_curated_value_wins_over_a_conflicting_measured_proposal(
            self, tmp_path, product_root, monkeypatch):
        from conftest import make_data_tree
        from bff.config import Settings
        data = make_data_tree(tmp_path / "data3", declared=("6020", None))
        settings = Settings(data_root=data, product_root=product_root)
        result = dataclasses.replace(stub_detection(), suggested=(
            SuggestedSiteCapture(tooth=4, center=(1.0, 2.0, 3.0), capture=CAP_PASS,
                                 measured_cap_height_mm=5.1, proposed_variant="9999"),
            SuggestedSiteCapture(tooth=13, center=(4.0, 5.0, 6.0), capture=CAP_RESCAN),
        ))
        client = self._client_detected_with(settings, monkeypatch, result)
        sites = {s["tooth"]: s
                for s in client.get("/api/case-sessions/neodent-gm").json()["sites"]}
        # the case's own curation stands even though detection measured something else
        assert sites[4]["suggested_variant"] == "6020"
        assert sites[4]["suggested_variant_source"] == "curated"

    def test_neither_curated_nor_measured_is_honestly_absent(
            self, settings, monkeypatch):
        client = self._client_detected_with(settings, monkeypatch, stub_detection())
        sites = {s["tooth"]: s
                for s in client.get("/api/case-sessions/neodent-gm").json()["sites"]}
        assert sites[4]["suggested_variant"] is None
        assert sites[4]["suggested_variant_source"] is None
        assert sites[13]["suggested_variant"] is None
        assert sites[13]["suggested_variant_source"] is None

    def test_the_raw_height_and_proposal_ride_the_detection_view(
            self, settings, monkeypatch):
        result = dataclasses.replace(stub_detection(), suggested=(
            SuggestedSiteCapture(tooth=4, center=(1.0, 2.0, 3.0), capture=CAP_PASS,
                                 measured_cap_height_mm=None, proposed_variant=None),
            SuggestedSiteCapture(tooth=13, center=(4.0, 5.0, 6.0), capture=CAP_RESCAN,
                                 measured_cap_height_mm=3.6, proposed_variant="5020",
                                 measured_rim_diameter_mm=4.9),
        ))
        client = self._client_detected_with(settings, monkeypatch, result)
        body = client.get("/api/case-sessions/neodent-gm").json()
        assert body["detection"]["site_measured_height_mm"] == {"4": None, "13": 3.6}
        assert body["detection"]["site_proposed_variant"] == {"4": None, "13": "5020"}
        # §10-AS.18: the visible rim rides too — the panes' soft-tissue separator
        assert body["detection"]["site_measured_diameter_mm"] == {"4": None, "13": 4.9}


class TestJawReadingCrossCheck:
    """§10-AM built: the jaw reads itself off the scan. ``application.detection``
    measures a SUGGESTION off the crowns' own axis (test_detection.py pins the
    physics); this resource's job is precedence (chosen beats the scan reading
    beats the filename) and the advisory sentence — never a transform, never a
    silent correction (§10-AM: cross-check, not a rewrite)."""

    def _detected_client(self, settings, monkeypatch, jaw_reading):
        def stub(case):
            return stub_detection(jaw_reading=jaw_reading)

        monkeypatch.setattr(case_sessions, "detect", stub)
        client = TestClient(create_app(settings))
        client.post("/api/case-sessions/neodent-gm/detect")
        return client

    def test_the_record_write_persists_the_reading(self, settings, monkeypatch):
        client = self._detected_client(settings, monkeypatch, "lower")
        persisted = SessionStore(settings.product_root).load("neodent-gm")
        assert persisted.detection.jaw_reading == "lower"

    def test_the_detection_view_carries_the_raw_reading(self, settings, monkeypatch):
        # the RAW reading survives on the wire even once a chosen jaw contradicts it
        # (effective_jaw only carries it while nothing is chosen) -- the UI's one-click
        # fix highlights the geometry's own answer on the jaw buttons from THIS field
        client = self._detected_client(settings, monkeypatch, "lower")
        client.put("/api/case-sessions/neodent-gm/choices", json={"jaw": "upper"})
        body = client.get("/api/case-sessions/neodent-gm").json()
        assert body["detection"]["jaw_reading"] == "lower"

    def test_a_scan_reading_beats_the_filename_suggestion(self, settings, monkeypatch):
        # the fixture's scan file is "upper_jaw.stl" -- the filename suggestion is
        # "upper" -- but the scan itself, once detected, reads "lower"
        client = self._detected_client(settings, monkeypatch, "lower")
        body = client.get("/api/case-sessions/neodent-gm").json()
        assert body["choices"]["effective_jaw"] == {"value": "lower", "source": "scan"}
        # effective now EQUALS the reading -- nothing to warn about
        assert body["choices"]["jaw_advisory"] is None

    def test_a_chosen_jaw_beats_the_scan_reading(self, settings, monkeypatch):
        client = self._detected_client(settings, monkeypatch, "lower")
        body = client.put("/api/case-sessions/neodent-gm/choices",
                          json={"jaw": "upper"}).json()
        assert body["choices"]["effective_jaw"] == {"value": "upper", "source": "chosen"}

    def test_the_advisory_names_the_contradiction_between_chosen_and_scan(
            self, settings, monkeypatch):
        client = self._detected_client(settings, monkeypatch, "lower")
        body = client.put("/api/case-sessions/neodent-gm/choices",
                          json={"jaw": "upper"}).json()
        assert body["choices"]["jaw_advisory"] == (
            "This scan reads as a lower jaw — the crowns point up along the "
            "scan's own axis — but the case says upper. Check the jaw choice; "
            "the package and its labels are named by it.")

    def test_the_advisory_is_absent_when_the_chosen_jaw_matches_the_reading(
            self, settings, monkeypatch):
        client = self._detected_client(settings, monkeypatch, "lower")
        body = client.put("/api/case-sessions/neodent-gm/choices",
                          json={"jaw": "lower"}).json()
        assert body["choices"]["jaw_advisory"] is None

    def test_the_advisory_is_absent_before_detection_has_run(self, client):
        # no reading exists yet -- nothing to cross-check the declared jaw against
        body = client.put("/api/case-sessions/neodent-gm/choices",
                          json={"jaw": "lower"}).json()
        assert body["choices"]["jaw_advisory"] is None

    def test_an_ambiguous_reading_makes_no_claim_and_no_advisory(
            self, settings, monkeypatch):
        # jaw_from_crown_axis returned None (a sideways export) -- honest absence,
        # never a coin-flip: the filename suggestion still stands
        client = self._detected_client(settings, monkeypatch, None)
        body = client.get("/api/case-sessions/neodent-gm").json()
        assert body["choices"]["effective_jaw"] == {"value": "upper", "source": "suggested"}
        assert body["choices"]["jaw_advisory"] is None


class TestChoices:
    """PUT /{id}/choices (plan §4/§6): the case-level operator choices, re-validated by
    the BFF in the demo's own words — the UI is untrusted (AM-9, ledger row 4)."""

    def test_valid_choices_persist_and_the_detail_echoes_them(self, settings):
        client = TestClient(create_app(settings))
        body = client.put("/api/case-sessions/neodent-gm/choices", json={
            "construction_path": "dess/neodent-gm-scanbody.stl",
            "jaw": "upper",
            "gingival_offset_mm": 0.15,
        }).json()
        assert body["choices"] == {
            "construction_path": "dess/neodent-gm-scanbody.stl",
            "jaw": "upper",
            "gingival_offset_mm": 0.15,
            "turnaround": None,
            "gingival_offset_default_mm": 0.2,
            # explicit acts flip every attribution to "chosen" (the system bar's
            # declared/suggested pattern, mirrored per choice)
            "effective_construction": {"value": "dess/neodent-gm-scanbody.stl",
                                       "source": "chosen"},
            "effective_jaw": {"value": "upper", "source": "chosen"},
            "effective_relief": {"value": 0.15, "source": "chosen"},
            "effective_turnaround": {"value": "standard", "source": "default"},
            "turnaround_options": [
                {"value": "standard", "unit_amount_cents": 3200, "currency": "USD"},
                {"value": "rush", "unit_amount_cents": 4800, "currency": "USD"},
            ],
            "complete": True,
            "jaw_advisory": None,   # no detection has run -- nothing to cross-check
        }
        # persisted: a fresh app serves the same choices and the worklist's fact
        row, = TestClient(create_app(settings)).get("/api/case-sessions").json()
        assert row["choices_complete"] is True

    def test_partial_choices_keep_honest_attribution(self, client):
        # one explicit act beside two fallbacks: the RAW fields stay None, the
        # EFFECTIVE views say who supplied each value (client 2026-07-27)
        body = client.put("/api/case-sessions/neodent-gm/choices",
                          json={"jaw": "lower"}).json()
        assert body["choices"]["jaw"] == "lower"
        assert body["choices"]["construction_path"] is None
        assert body["choices"]["effective_jaw"] == {"value": "lower",
                                                    "source": "chosen"}
        assert body["choices"]["effective_construction"]["source"] == "suggested"
        assert body["choices"]["effective_relief"] == {"value": 0.2,
                                                       "source": "default"}
        assert body["choices"]["complete"] is True

    def test_a_case_without_a_construction_suggestion_is_honestly_incomplete(
            self, settings):
        # the effective fallback is a suggestion, never a guess: a scan folder
        # matching no library name has no suggested construction, so the effective
        # construction is absent (source "none") and completeness fails with it
        scans = settings.data_root / "scans/doctor-nobody"
        scans.mkdir(parents=True)
        (scans / "upper_jaw.stl").touch()
        client = TestClient(create_app(settings))
        body = client.get("/api/case-sessions/nobody").json()
        assert body["choices"]["effective_construction"] == {"value": None,
                                                             "source": "none"}
        # jaw still falls back (read off the scan filename), relief to the default
        assert body["choices"]["effective_jaw"] == {"value": "upper",
                                                    "source": "suggested"}
        assert body["choices"]["complete"] is False
        rows = {r["id"]: r for r in client.get("/api/case-sessions").json()}
        assert rows["nobody"]["choices_complete"] is False

    def test_pinning_the_effective_document_resets_nothing(self, settings):
        # the system route's withModel equality guard, mirrored (client 2026-07-27:
        # "the effective-default path is not a change"): a PUT that lands exactly
        # the values already in effect — the suggestion + the standing default —
        # changes no effective value, so no preview or review falls to it
        store = SessionStore(settings.product_root)
        s = store.load("neodent-gm")
        s.sites["4"] = SiteSession(status=SiteStatus.READY, declared_variant="5020",
                                   seat_method="rim-seat", rim_agreement_mm=0.07)
        store.save(s)
        client = TestClient(create_app(settings))
        complete_choices(client)   # exactly the suggested/default values
        persisted = SessionStore(settings.product_root).load("neodent-gm")
        assert persisted.sites["4"].status is SiteStatus.READY
        assert persisted.sites["4"].seat_method == "rim-seat"
        # the acts themselves DID persist — only the reset was judged a non-change
        assert persisted.choices.construction_path == "dess/neodent-gm-scanbody.stl"

    def test_a_choices_change_clears_previews_and_reviews_but_keeps_declarations(
            self, settings):
        # the demo's review-reset rule, LANDED (librarySelection.ts:10-16, 5a's stated
        # boundary made real in 5b): construction, jaw and relief describe the same
        # shipped part, so changing any clears every site's later-ladder facts — a
        # previewed site's seat AND a ready site's review — but never its declared
        # variant (withConstruction/withJaw/withOffsetInput touch `reviewed` only).
        store = SessionStore(settings.product_root)
        s = store.load("neodent-gm")
        s.sites["4"] = SiteSession(status=SiteStatus.PREVIEWED,
                                   declared_variant="5020",
                                   seat_method="rim-seat", rim_agreement_mm=0.07)
        s.sites["13"] = SiteSession(status=SiteStatus.READY,
                                    declared_variant="5020",
                                    seat_method="best-fit", rim_agreement_mm=0.11)
        store.save(s)
        client = TestClient(create_app(settings))
        body = client.put("/api/case-sessions/neodent-gm/choices",
                          json={"jaw": "lower"}).json()
        sites = {v["tooth"]: v for v in body["sites"]}
        assert sites[4]["status"] == "declared"
        assert sites[13]["status"] == "declared"
        assert sites[4]["declared_variant"] == "5020"
        assert sites[13]["declared_variant"] == "5020"
        persisted = SessionStore(settings.product_root).load("neodent-gm")
        for tooth in ("4", "13"):
            assert persisted.sites[tooth].seat_method is None
            assert persisted.sites[tooth].rim_agreement_mm is None

    def test_an_identical_choices_re_put_resets_nothing(self, settings):
        # the demo's equality guards (withConstruction/withJaw/withOffsetInput each
        # return the state unchanged on an equal value): re-submitting the same panel
        # is not a change, so no preview or review is destroyed by an idempotent PUT
        client = TestClient(create_app(settings))
        complete_choices(client)
        store = SessionStore(settings.product_root)
        s = store.load("neodent-gm")
        s.sites["4"] = SiteSession(status=SiteStatus.READY, declared_variant="5020",
                                   seat_method="rim-seat", rim_agreement_mm=0.07)
        store.save(s)
        complete_choices(client)   # the identical document, again
        persisted = SessionStore(settings.product_root).load("neodent-gm")
        assert persisted.sites["4"].status is SiteStatus.READY
        assert persisted.sites["4"].seat_method == "rim-seat"

    def test_turnaround_persists_with_its_attribution(self, client):
        body = client.put("/api/case-sessions/neodent-gm/choices",
                          json={"turnaround": "rush"}).json()
        assert body["choices"]["turnaround"] == "rush"
        assert body["choices"]["effective_turnaround"] == {"value": "rush",
                                                           "source": "chosen"}

    def test_the_turnaround_options_price_from_the_one_rate_card(self, client):
        # §10-AB.4: the chooser's money is the card's — the SAME module the invoice
        # charges from, so the pill and the bill can never disagree
        from bff.pricing import CURRENCY, TURNAROUNDS, unit_amount_cents
        body = client.get("/api/case-sessions/neodent-gm").json()
        assert body["choices"]["turnaround_options"] == [
            {"value": word, "unit_amount_cents": unit_amount_cents(word),
             "currency": CURRENCY}
            for word in TURNAROUNDS
        ]

    def test_an_unknown_turnaround_word_is_refused_at_the_wire(self, client):
        # a Literal, not a validated str: bff.pricing must never be handed a word it
        # has no rate for
        res = client.put("/api/case-sessions/neodent-gm/choices",
                         json={"turnaround": "overnight"})
        assert res.status_code == 422

    def test_turnaround_does_not_gate_completeness(self, client):
        # the standing default always answers it, so a case is never incomplete for
        # want of a commercial choice nobody has to make
        body = client.get("/api/case-sessions/neodent-gm").json()
        assert body["choices"]["turnaround"] is None
        assert body["choices"]["complete"] is True

    def test_changing_the_turnaround_RESETS_NOTHING(self, settings):
        """THE RULE THIS FIELD EXISTS UNDER (gap ``turnaround-as-a-case-choice``,
        2026-07-31). Construction, jaw and relief reset every preview and the run
        because they "all describe the same shipped part". A turnaround is a promise
        about WHEN and touches no geometry — dropping an operator's reviews because
        the lab upgraded a case to rush would be a fabricated invalidation, which is
        the same class of untruth as claiming one."""
        store = SessionStore(settings.product_root)
        s = store.load("neodent-gm")
        s.sites["4"] = SiteSession(status=SiteStatus.READY, declared_variant="5020",
                                   seat_method="rim-seat", rim_agreement_mm=0.07)
        s.run = RunSession(job_id="job-1", run_id="job-1", state="done", summary={})
        store.save(s)
        client = TestClient(create_app(settings))
        res = client.put("/api/case-sessions/neodent-gm/choices",
                         json={"turnaround": "rush"})
        assert res.status_code == 200, res.text
        persisted = SessionStore(settings.product_root).load("neodent-gm")
        assert persisted.sites["4"].status is SiteStatus.READY
        assert persisted.sites["4"].seat_method == "rim-seat"
        assert persisted.run is not None      # the run pointer survives
        assert persisted.choices.turnaround == "rush"

    def test_an_unknown_construction_part_is_refused_by_catalog_membership(self, client):
        res = client.put("/api/case-sessions/neodent-gm/choices",
                         json={"construction_path": "dess/../../../etc/passwd"})
        assert res.status_code == 422
        assert "unknown construction part" in res.json()["detail"]

    def test_a_bad_jaw_is_refused_in_the_demos_words(self, client):
        res = client.put("/api/case-sessions/neodent-gm/choices",
                         json={"jaw": "sideways"})
        assert res.status_code == 422
        assert "jaw must be one of upper, lower" in res.text

    def test_relief_out_of_bounds_is_refused_in_the_demos_words(self, client):
        for bad in (-0.1, 1.5):
            res = client.put("/api/case-sessions/neodent-gm/choices",
                             json={"gingival_offset_mm": bad})
            assert res.status_code == 422
            assert "clearance between 0 and 1.0mm" in res.text

    def test_a_non_finite_relief_is_refused(self, client):
        # the corpus' finiteness rule (server.py:260-266): NaN is a typo, not a choice.
        # The refusal itself must SERIALIZE — FastAPI's default 422 handler echoes the
        # offending input and json.dumps(allow_nan=False) turned the refusal into a 500
        # (bff.main's validation_refusal handler exists for exactly this).
        res = client.put("/api/case-sessions/neodent-gm/choices",
                         content='{"gingival_offset_mm": NaN}',
                         headers={"content-type": "application/json"})
        assert res.status_code == 422
        assert "clearance between 0 and 1.0mm" in res.text

    def test_an_unknown_case_is_a_404(self, client):
        assert client.put("/api/case-sessions/no-such-case/choices",
                          json={"jaw": "upper"}).status_code == 404

    def test_the_ceiling_follows_the_chosen_construction(
            self, tmp_path, product_root, monkeypatch):
        """Plan §4: the relief input lives beside ITS ceiling — the one for the part the
        operator picked, not the name-matched suggestion. The ceiling read is stubbed
        (its physics is the worker's own real-tree test); what is pinned here is which
        construction the resource asks about."""
        from conftest import make_data_tree
        from bff.config import Settings
        data = make_data_tree(tmp_path / "data2", declared=("5020", None))
        atlantis = data / "library/construction/atlantis"
        atlantis.mkdir(parents=True)
        (atlantis / "zimmer-4.5-scanbody.stl").touch()
        asked = []

        def stub_ceiling(data_root, construction_path, model, variant):
            asked.append(construction_path)
            return {"variant": variant, "construction_path": construction_path,
                    "model": model, "max_safe_mm": 0.5}

        monkeypatch.setattr(case_sessions, "relief_ceiling", stub_ceiling)
        client = TestClient(create_app(Settings(data_root=data,
                                                product_root=product_root)))
        client.get("/api/case-sessions/neodent-gm")
        assert asked == ["dess/neodent-gm-scanbody.stl"]  # the suggestion, pre-choice
        body = client.put("/api/case-sessions/neodent-gm/choices", json={
            "construction_path": "atlantis/zimmer-4.5-scanbody.stl"}).json()
        assert asked[-1] == "atlantis/zimmer-4.5-scanbody.stl"
        assert body["relief_ceilings"][0]["construction_path"] == \
            "atlantis/zimmer-4.5-scanbody.stl"


class TestSystem:
    """PUT /{id}/system (plan §4 Declare / AM-8): the case-scoped implant system,
    declared ONCE per case. Switching is the explicit case-level act that visibly
    resets every site — the demo's librarySelection.withModel semantics REIMPLEMENTED
    server-side (the state lives in the session now; ledger NOTE row). Validation is
    catalog membership in the catalog's own words; the detail always says WHICH system
    is effective and whether it is the session's act or the case's suggestion."""

    @staticmethod
    def _second_model(settings, model="astra-ev"):
        caps = settings.data_root / "library/caps" / model
        caps.mkdir(parents=True)
        (caps / f"{model}-3010.stl").touch()

    def test_an_unknown_case_is_a_404(self, client):
        assert client.put("/api/case-sessions/no-such-case/system",
                          json={"model": "neodent-gm"}).status_code == 404

    def test_an_unknown_system_is_refused_in_catalog_words(self, client):
        res = client.put("/api/case-sessions/neodent-gm/system",
                         json={"model": "no-such-system"})
        assert res.status_code == 422
        assert "unknown implant system" in res.json()["detail"]

    def test_a_legacy_shelf_is_not_a_declarable_system(self, tmp_path, product_root):
        # legacy *-library directories are honestly LISTED by the catalog but carry
        # no current parts — a case-level system must be a real caps model
        from conftest import make_data_tree
        from bff.config import Settings
        data = make_data_tree(tmp_path / "data2")
        legacy = data / "old-parts-library"
        legacy.mkdir()
        (legacy / "old-parts-library-4040.stl").touch()
        client = TestClient(create_app(Settings(data_root=data,
                                                product_root=product_root)))
        res = client.put("/api/case-sessions/neodent-gm/system",
                         json={"model": "old-parts-library"})
        assert res.status_code == 422
        assert "unknown implant system" in res.json()["detail"]

    def test_before_any_declaration_the_detail_says_suggested(self, client):
        body = client.get("/api/case-sessions/neodent-gm").json()
        assert body["system"] == {"effective_model": "neodent-gm",
                                  "source": "suggested"}

    def test_declaring_a_system_is_an_act_the_detail_attributes(self, settings):
        client = TestClient(create_app(settings))
        body = client.put("/api/case-sessions/neodent-gm/system",
                          json={"model": "neodent-gm"}).json()
        assert body["system"] == {"effective_model": "neodent-gm",
                                  "source": "declared"}
        # persisted: a fresh app serves the act, not the suggestion
        again = TestClient(create_app(settings)).get(
            "/api/case-sessions/neodent-gm").json()
        assert again["system"]["source"] == "declared"

    def test_switching_the_system_resets_every_site_server_side(self, settings):
        # the withModel rule (librarySelection.ts:96-103), now a server derivation:
        # a variant id belongs to one system's catalog, so switching drops every
        # declared variant AND regresses every site to detected
        self._second_model(settings)
        store = SessionStore(settings.product_root)
        s = store.load("neodent-gm")
        s.sites["4"] = SiteSession(status=SiteStatus.DECLARED,
                                   declared_variant="5020")
        s.sites["13"] = SiteSession(status=SiteStatus.READY,
                                    declared_variant="5020",
                                    seat_method="rim-seat", rim_agreement_mm=0.07,
                                    seated_selection=seated())
        store.save(s)
        client = TestClient(create_app(settings))
        body = client.put("/api/case-sessions/neodent-gm/system",
                          json={"model": "astra-ev"}).json()
        sites = {v["tooth"]: v for v in body["sites"]}
        assert all(sites[t]["status"] == "detected" for t in (4, 13))
        assert all(sites[t]["declared_variant"] is None for t in (4, 13))
        assert body["system"] == {"effective_model": "astra-ev",
                                  "source": "declared"}
        # and the store agrees — the 5b preview facts fell with the declarations
        persisted = SessionStore(settings.product_root).load("neodent-gm")
        assert persisted.sites["4"].status is SiteStatus.DETECTED
        assert persisted.sites["4"].declared_variant is None
        assert persisted.sites["13"].seat_method is None
        assert persisted.sites["13"].rim_agreement_mm is None
        assert persisted.sites["13"].seated_selection is None

    def test_re_declaring_the_effective_system_resets_nothing(self, settings):
        # withModel's own guard (state.model === model → no change): PUTting the
        # system already in effect — including pinning the suggestion — is not a
        # switch, so no site loses its declaration to an idempotent click
        store = SessionStore(settings.product_root)
        s = store.load("neodent-gm")
        s.sites["4"] = SiteSession(status=SiteStatus.DECLARED,
                                   declared_variant="5020")
        store.save(s)
        client = TestClient(create_app(settings))
        body = client.put("/api/case-sessions/neodent-gm/system",
                          json={"model": "neodent-gm"}).json()
        sites = {v["tooth"]: v for v in body["sites"]}
        assert sites[4]["status"] == "declared"
        assert sites[4]["declared_variant"] == "5020"


class TestDeclaration:
    """PUT /{id}/sites/{tooth}/declaration (plan §4 Declare / AM-8): the per-site
    variant declaration. The variant must be a part of the EFFECTIVE system's library
    (422 in the catalog's words); the tooth must be a site the case actually has
    (404 — the path names a subresource that does not exist). The status transition
    is the machine's (detected → declared), never a handler's string."""

    def test_an_unknown_case_is_a_404(self, client):
        assert client.put("/api/case-sessions/no-such-case/sites/4/declaration",
                          json={"variant": "5020"}).status_code == 404

    def test_a_tooth_the_case_does_not_have_is_a_404(self, client):
        res = client.put("/api/case-sessions/neodent-gm/sites/31/declaration",
                         json={"variant": "5020"})
        assert res.status_code == 404
        assert "not a site" in res.json()["detail"]

    def test_an_unknown_variant_is_refused_in_catalog_words(self, client):
        res = client.put("/api/case-sessions/neodent-gm/sites/4/declaration",
                         json={"variant": "9999"})
        assert res.status_code == 422
        assert "not a part of the 'neodent-gm' library" in res.json()["detail"]

    def test_a_case_with_no_effective_system_asks_for_one_first(
            self, settings):
        # a case whose folder matched no model has no suggestion; until the operator
        # declares a system there is no catalog to validate variants against
        scans = settings.data_root / "scans/doctor-nobody"
        scans.mkdir(parents=True)
        (scans / "upper_jaw.stl").touch()
        import json as _json
        (scans / "sites.json").write_text(_json.dumps({"suggested_sites": [
            {"tooth": 8, "center": [0.0, 0.0, 0.0], "declared_variant": None}]}))
        client = TestClient(create_app(settings))
        res = client.put("/api/case-sessions/nobody/sites/8/declaration",
                         json={"variant": "5020"})
        assert res.status_code == 422
        assert "declare the implant system" in res.json()["detail"]

    def test_declaring_moves_the_site_detected_to_declared(self, settings):
        client = TestClient(create_app(settings))
        body = client.put("/api/case-sessions/neodent-gm/sites/4/declaration",
                          json={"variant": "5020"}).json()
        sites = {v["tooth"]: v for v in body["sites"]}
        assert sites[4]["status"] == "declared"
        assert sites[4]["declared_variant"] == "5020"
        assert sites[13]["status"] == "detected"   # only the named site moved
        # persisted, and the worklist rollup counts the act
        row, = TestClient(create_app(settings)).get("/api/case-sessions").json()
        assert row["sites"]["declared"] == 1

    def test_re_declaring_a_different_variant_keeps_declared(self, settings):
        (settings.data_root / "library/caps/neodent-gm/neodent-gm-6030.stl").touch()
        client = TestClient(create_app(settings))
        client.put("/api/case-sessions/neodent-gm/sites/4/declaration",
                   json={"variant": "5020"})
        body = client.put("/api/case-sessions/neodent-gm/sites/4/declaration",
                          json={"variant": "6030"}).json()
        sites = {v["tooth"]: v for v in body["sites"]}
        assert sites[4]["status"] == "declared"
        assert sites[4]["declared_variant"] == "6030"

    def test_re_declaring_a_different_variant_clears_the_preview_facts(
            self, settings):
        # the declaration is the reset boundary (5a's stated rule, real since 5b): a
        # previewed/reviewed site re-described drops its seat facts WITH its rung —
        # the old preview coloured a part no longer declared
        (settings.data_root / "library/caps/neodent-gm/neodent-gm-6030.stl").touch()
        store = SessionStore(settings.product_root)
        s = store.load("neodent-gm")
        s.sites["4"] = SiteSession(status=SiteStatus.READY, declared_variant="5020",
                                   seat_method="rim-seat", rim_agreement_mm=0.07,
                                   seated_selection=seated())
        store.save(s)
        client = TestClient(create_app(settings))
        body = client.put("/api/case-sessions/neodent-gm/sites/4/declaration",
                          json={"variant": "6030"}).json()
        sites = {v["tooth"]: v for v in body["sites"]}
        assert sites[4]["status"] == "declared"
        persisted = SessionStore(settings.product_root).load("neodent-gm")
        assert persisted.sites["4"].seat_method is None
        assert persisted.sites["4"].rim_agreement_mm is None
        # the seat record is a preview fact: it falls at the same boundary
        assert persisted.sites["4"].seated_selection is None

    def test_re_declaring_the_same_variant_changes_nothing_at_all(self, settings):
        # the same idempotence the system route has: re-clicking the declared card
        # must not throw away a preview of exactly that part
        store = SessionStore(settings.product_root)
        s = store.load("neodent-gm")
        s.sites["4"] = SiteSession(status=SiteStatus.PREVIEWED,
                                   declared_variant="5020",
                                   seat_method="rim-seat", rim_agreement_mm=0.07)
        store.save(s)
        client = TestClient(create_app(settings))
        body = client.put("/api/case-sessions/neodent-gm/sites/4/declaration",
                          json={"variant": "5020"}).json()
        sites = {v["tooth"]: v for v in body["sites"]}
        assert sites[4]["status"] == "previewed"
        persisted = SessionStore(settings.product_root).load("neodent-gm")
        assert persisted.sites["4"].seat_method == "rim-seat"

    def test_a_superseded_part_is_declarable_by_its_explicit_catalog_id(
            self, settings):
        # the shelf is honest, never hidden (library_catalog): an archived part
        # enters only because a human NAMED it — by the catalog's own id
        archive = settings.data_root / "library/caps/neodent-gm/superseded-2025-01-01"
        archive.mkdir()
        (archive / "neodent-gm-4010.stl").touch()
        client = TestClient(create_app(settings))
        body = client.put("/api/case-sessions/neodent-gm/sites/4/declaration",
                          json={"variant": "superseded-2025-01-01--4010"}).json()
        sites = {v["tooth"]: v for v in body["sites"]}
        assert sites[4]["declared_variant"] == "superseded-2025-01-01--4010"

    def test_the_variant_is_validated_against_the_effective_system(self, settings):
        # after a system switch the OLD system's variants are strangers: the
        # validation corpus follows the session's declared system, not the suggestion
        caps = settings.data_root / "library/caps/astra-ev"
        caps.mkdir(parents=True)
        (caps / "astra-ev-3010.stl").touch()
        client = TestClient(create_app(settings))
        client.put("/api/case-sessions/neodent-gm/system",
                   json={"model": "astra-ev"})
        res = client.put("/api/case-sessions/neodent-gm/sites/4/declaration",
                         json={"variant": "5020"})   # a neodent-gm part
        assert res.status_code == 422
        assert "not a part of the 'astra-ev' library" in res.json()["detail"]
        ok = client.put("/api/case-sessions/neodent-gm/sites/4/declaration",
                        json={"variant": "3010"})
        assert ok.status_code == 200


def stub_preview_payload(tooth: int = 4, variant: str = "5020") -> dict:
    """A payload shaped like application.preview's (the demo's wire shape — pinned for
    real in worker test_preview.py; here only the fields the resource TOUCHES matter:
    the seat block it persists and the mesh it must pass through untouched)."""
    return {
        "case_id": "neodent-gm", "tooth": tooth, "implant_model": "neodent-gm",
        "variant": variant, "frame": "jaw-scan world frame", "units": "mm",
        "pose": {"axis": [0.0, 0.0, 1.0], "x_axis": [1.0, 0.0, 0.0],
                 "origin": [0.0, 0.0, 0.0]},
        "n_points": 1, "points": [[0.0, 0.0, 0.0]], "faces": [[0, 0, 0]],
        "deviation_mm": [0.1],
        "scale": {"clamp_mm": 0.5}, "stats": {"rms_mm": 0.43, "p90_mm": 0.7},
        "vertex_footprint_points": 1, "reporting_only": True, "preview": True,
        "seat": {"seat_method": "rim-seat", "rim_agreement_mm": 0.07, "fit": "ok"},
    }


def seated(variant: str = "5020", **overrides) -> SeatedSelection:
    """The seat record the preview route persists for the conftest case's effective
    document — overrides express a HISTORIC seat (what a review once attested)
    diverging from the current one, the 2026-07-28 drift finding's raw material."""
    fields = dict(model="neodent-gm",
                  construction_path="dess/neodent-gm-scanbody.stl",
                  variant=variant, jaw="upper", gingival_offset_mm=0.2)
    fields.update(overrides)
    return SeatedSelection(**fields)


def complete_choices(client: TestClient, case_id: str = "neodent-gm"):
    res = client.put(f"/api/case-sessions/{case_id}/choices", json={
        "construction_path": "dess/neodent-gm-scanbody.stl",
        "jaw": "upper",
        "gingival_offset_mm": 0.2,
    })
    assert res.status_code == 200, res.text


def declare_site(client: TestClient, tooth: int = 4, variant: str = "5020",
                 case_id: str = "neodent-gm"):
    res = client.put(f"/api/case-sessions/{case_id}/sites/{tooth}/declaration",
                     json={"variant": variant})
    assert res.status_code == 200, res.text


class TestPreview:
    """POST /{id}/sites/{tooth}/preview (plan §4 Declare / §7 slice 5b): seat the
    declared cap and return its deviation colouring. A compute TRIGGER like detect —
    no body at all; everything derives from the session (the declaration, the
    choices) plus the case. The physics is the worker's (test_preview.py pins it on
    the real tree); what belongs here is orchestration — refuse incomplete sessions,
    persist the seat FACTS through the status machine, keep the mesh response-only —
    so the application function is stubbed at the resource seam."""

    def _client_with_stub(self, settings, monkeypatch, result=None):
        calls = []

        def stub(case, selection, tooth):
            calls.append((case.id, selection, tooth))
            if isinstance(result, Exception):
                raise result
            return result or stub_preview_payload(tooth=tooth)

        monkeypatch.setattr(case_sessions, "preview_site", stub)
        return TestClient(create_app(settings)), calls

    def test_an_unknown_case_is_a_404(self, client):
        assert client.post(
            "/api/case-sessions/no-such-case/sites/4/preview").status_code == 404

    def test_a_tooth_the_case_does_not_have_is_a_404(self, settings, monkeypatch):
        client, _ = self._client_with_stub(settings, monkeypatch)
        res = client.post("/api/case-sessions/neodent-gm/sites/31/preview")
        assert res.status_code == 404
        assert "not a site" in res.json()["detail"]

    def test_an_undeclared_site_is_a_422_naming_the_gap(self, settings, monkeypatch):
        client, calls = self._client_with_stub(settings, monkeypatch)
        complete_choices(client)
        res = client.post("/api/case-sessions/neodent-gm/sites/4/preview")
        assert res.status_code == 422
        assert "declared cap variant" in res.json()["detail"]
        assert calls == []   # the refusal costs no physics

    def test_a_fresh_session_with_only_a_declaration_previews_on_the_suggestions(
            self, settings, monkeypatch):
        """THE CLIENT'S COMPLAINT (2026-07-27), pinned: 'once implant system and
        variant for tooth are selected the union needs to show up'. No choices PUT
        was ever made — the preview seats with the EFFECTIVE values: the case's
        suggested construction, the filename-read jaw, the standing 0.20mm relief
        default. A 422 here is the bug this test exists to keep dead."""
        client, calls = self._client_with_stub(settings, monkeypatch)
        declare_site(client)   # the ONLY act on this session
        res = client.post("/api/case-sessions/neodent-gm/sites/4/preview")
        assert res.status_code == 200
        (_case_id, selection, _tooth), = calls
        assert selection.construction_path == "dess/neodent-gm-scanbody.stl"
        assert selection.jaw == "upper"
        assert selection.gingival_offset_mm == 0.2

    def test_a_re_marked_sites_preview_carries_the_operators_centre(
            self, settings, monkeypatch):
        """THE 12° DEFECT's preview half (measured 2026-08-04, cap6020): the
        preview always seated from the curated record, so a re-marked centre moved
        the panes' framing and never the previewed pose — the operator corrected a
        centre and watched the same tilt come back. The selection now ships the
        re-mark; the worker seeds it ALONE (pair integrity, pinned worker-side)."""
        client, calls = self._client_with_stub(settings, monkeypatch)
        declare_site(client)
        assert client.put("/api/case-sessions/neodent-gm/sites/4/mark",
                          json={"center": [9.0, 9.0, 9.0]}).status_code == 200
        res = client.post("/api/case-sessions/neodent-gm/sites/4/preview")
        assert res.status_code == 200, res.text
        (_case_id, selection, _tooth), = calls
        assert selection.marked_center == [9.0, 9.0, 9.0]

    def test_an_unmarked_sites_preview_ships_no_marked_centre(
            self, settings, monkeypatch):
        client, calls = self._client_with_stub(settings, monkeypatch)
        declare_site(client)
        assert client.post(
            "/api/case-sessions/neodent-gm/sites/4/preview").status_code == 200
        (_case_id, selection, _tooth), = calls
        assert selection.marked_center is None

    def test_a_case_without_a_construction_suggestion_still_refuses_naming_it(
            self, settings, monkeypatch):
        # the effective fallback is a suggestion, never a guess: a case whose
        # folder matched no library name has none, and the preview refusal names
        # exactly the piece no fallback covers (jaw and relief have fallbacks)
        scans = settings.data_root / "scans/doctor-nobody"
        scans.mkdir(parents=True)
        (scans / "upper_jaw.stl").touch()
        import json as _json
        (scans / "sites.json").write_text(_json.dumps({"suggested_sites": [
            {"tooth": 8, "center": [0.0, 0.0, 0.0], "declared_variant": None}]}))
        client, calls = self._client_with_stub(settings, monkeypatch)
        client.put("/api/case-sessions/nobody/system", json={"model": "neodent-gm"})
        declare_site(client, tooth=8, case_id="nobody")
        res = client.post("/api/case-sessions/nobody/sites/8/preview")
        assert res.status_code == 422
        detail = res.json()["detail"]
        assert "construction part" in detail
        assert "jaw" not in detail
        assert "gingival relief" not in detail
        assert calls == []   # the refusal costs no physics

    def test_preview_runs_persists_the_seat_facts_and_returns_the_payload(
            self, settings, monkeypatch):
        client, calls = self._client_with_stub(settings, monkeypatch)
        complete_choices(client)
        declare_site(client)
        res = client.post("/api/case-sessions/neodent-gm/sites/4/preview")
        assert res.status_code == 200
        # the response IS the payload — the panes render it directly
        assert res.json() == stub_preview_payload(tooth=4)
        # the application was asked with the SESSION's own acts, never a suggestion
        (case_id, selection, tooth), = calls
        assert (case_id, tooth) == ("neodent-gm", 4)
        assert selection.model == "neodent-gm"
        assert selection.construction_path == "dess/neodent-gm-scanbody.stl"
        assert selection.variant == "5020"
        assert selection.jaw == "upper"
        assert selection.gingival_offset_mm == 0.2
        # the FACTS persisted; the mesh did not (the session stays session-sized)
        persisted = SessionStore(settings.product_root).load("neodent-gm")
        site = persisted.sites["4"]
        assert site.status is SiteStatus.PREVIEWED
        assert site.seat_method == "rim-seat"
        assert site.rim_agreement_mm == 0.07
        # the SEAT RECORD rides with the facts (the 2026-07-28 drift guard): the
        # full selection this preview actually seated, so a later gate can judge
        # whether READY still describes the case instead of assuming it
        assert site.seated_selection == seated()
        assert "points" not in site.model_dump()
        # …and the detail the UI re-reads says previewed
        detail = client.get("/api/case-sessions/neodent-gm").json()
        sites = {v["tooth"]: v for v in detail["sites"]}
        assert sites[4]["status"] == "previewed"

    def test_a_re_preview_re_derives_and_stays_previewed(self, settings, monkeypatch):
        # no server-side cache (ledger row 7): the payload is response-only, so the
        # UI's reload re-ask runs the derivation again — and the rung holds
        client, calls = self._client_with_stub(settings, monkeypatch)
        complete_choices(client)
        declare_site(client)
        client.post("/api/case-sessions/neodent-gm/sites/4/preview")
        res = client.post("/api/case-sessions/neodent-gm/sites/4/preview")
        assert res.status_code == 200
        assert len(calls) == 2
        persisted = SessionStore(settings.product_root).load("neodent-gm")
        assert persisted.sites["4"].status is SiteStatus.PREVIEWED

    def test_a_re_preview_over_a_reviewed_site_keeps_the_review(
            self, settings, monkeypatch):
        # a page reload re-renders a READY site's panes; the attestation stands
        # because the seat is judged the SAME — the seeded record mirrors what the
        # preview route itself persists (since 2026-07-28, READY holding is an
        # equality over the recorded seat, no longer an assumption)
        client, _ = self._client_with_stub(settings, monkeypatch)
        complete_choices(client)
        store = SessionStore(settings.product_root)
        s = store.load("neodent-gm")
        s.sites["4"] = SiteSession(status=SiteStatus.READY, declared_variant="5020",
                                   seat_method="rim-seat", rim_agreement_mm=0.07,
                                   seated_selection=seated())
        store.save(s)
        res = client.post("/api/case-sessions/neodent-gm/sites/4/preview")
        assert res.status_code == 200
        assert SessionStore(settings.product_root).load(
            "neodent-gm").sites["4"].status is SiteStatus.READY

    def test_a_re_preview_whose_seat_drifted_unticks_the_review(
            self, settings, monkeypatch):
        """THE EFFECTIVE-DEFAULT DRIFT BOUNDARY (the 2026-07-28 review's refuted
        finding): the effective fallbacks — the case's suggestions, the standing
        relief default — live OUTSIDE the session, so they can change while READY
        stands and no reset boundary fires. The UI auto-refires the preview when
        its key changes; before this boundary, that repainted the panes with the
        NEW physics while the tick stayed ticked — invisible drift. Now the
        landing judges seat equality: a differing seat drops READY to PREVIEWED
        (the machine's reseat_preview) — the drift COSTS the tick, visibly."""
        client, _ = self._client_with_stub(settings, monkeypatch)
        # no choices PUT: the preview seats on the suggestions + the 0.20 standing
        # default. The RECORD says the review attested a 0.15 relief — a former
        # standing default, seeded as the historic fact a deploy left behind.
        store = SessionStore(settings.product_root)
        s = store.load("neodent-gm")
        s.sites["4"] = SiteSession(status=SiteStatus.READY, declared_variant="5020",
                                   seat_method="rim-seat", rim_agreement_mm=0.07,
                                   seated_selection=seated(gingival_offset_mm=0.15))
        store.save(s)
        res = client.post("/api/case-sessions/neodent-gm/sites/4/preview")
        assert res.status_code == 200
        site = SessionStore(settings.product_root).load("neodent-gm").sites["4"]
        assert site.status is SiteStatus.PREVIEWED   # the tick fell with the drift
        assert site.seated_selection == seated()     # the record now names THIS seat

    def test_a_ready_site_with_no_recorded_seat_falls_on_re_preview(
            self, settings, monkeypatch):
        # a document persisted before the seat record existed: READY with no record
        # cannot prove WHAT its review attested, so the judgment fails closed — the
        # re-preview lands PREVIEWED and writes the record; one re-review restores
        # READY over a seat that can be verified from then on
        client, _ = self._client_with_stub(settings, monkeypatch)
        complete_choices(client)
        store = SessionStore(settings.product_root)
        s = store.load("neodent-gm")
        s.sites["4"] = SiteSession(status=SiteStatus.READY, declared_variant="5020",
                                   seat_method="rim-seat", rim_agreement_mm=0.07)
        store.save(s)
        res = client.post("/api/case-sessions/neodent-gm/sites/4/preview")
        assert res.status_code == 200
        site = SessionStore(settings.product_root).load("neodent-gm").sites["4"]
        assert site.status is SiteStatus.PREVIEWED
        assert site.seated_selection == seated()

    def test_the_pipelines_refusal_is_a_409_in_its_own_words(
            self, settings, monkeypatch):
        client, _ = self._client_with_stub(
            settings, monkeypatch,
            result=PreviewRefused("no confirmed site could be aligned"))
        complete_choices(client)
        declare_site(client)
        res = client.post("/api/case-sessions/neodent-gm/sites/4/preview")
        assert res.status_code == 409
        assert "no confirmed site could be aligned" in res.json()["detail"]
        # a refusal persists nothing — the site still awaits its first preview
        site = SessionStore(settings.product_root).load("neodent-gm").sites["4"]
        assert site.status is SiteStatus.DECLARED
        assert site.seat_method is None

    def test_an_unreadable_scan_is_a_422_in_the_workers_words(
            self, settings, monkeypatch):
        client, _ = self._client_with_stub(
            settings, monkeypatch,
            result=ScanUnreadable("the scan upper_jaw.stl could not be read as a mesh"))
        complete_choices(client)
        declare_site(client)
        res = client.post("/api/case-sessions/neodent-gm/sites/4/preview")
        assert res.status_code == 422
        assert "could not be read" in res.json()["detail"]

    def test_a_catalog_refusal_is_a_422_in_catalog_words(self, settings, monkeypatch):
        client, _ = self._client_with_stub(
            settings, monkeypatch,
            result=UnknownSelection("'5020' is not a part of the 'x' library"))
        complete_choices(client)
        declare_site(client)
        res = client.post("/api/case-sessions/neodent-gm/sites/4/preview")
        assert res.status_code == 422
        assert "not a part of" in res.json()["detail"]

    def test_a_rival_change_mid_derivation_is_a_409_not_stale_facts(
            self, settings, monkeypatch):
        """The preview derivation runs for SECONDS; a rival re-declaration landing
        mid-derivation makes the derived facts describe a part no longer declared.
        The mutation re-judges against the fresh document (commit 25604e7's rule) and
        refuses — stale seat facts must never land on the switched declaration."""
        (settings.data_root / "library/caps/neodent-gm/neodent-gm-6030.stl").touch()

        def preview_with_concurrent_redeclare(case, selection, tooth):
            rival = TestClient(create_app(settings))
            res = rival.put(f"/api/case-sessions/{case.id}/sites/4/declaration",
                            json={"variant": "6030"})
            assert res.status_code == 200
            return stub_preview_payload(tooth=tooth)

        monkeypatch.setattr(case_sessions, "preview_site",
                            preview_with_concurrent_redeclare)
        client = TestClient(create_app(settings))
        complete_choices(client)
        declare_site(client)   # 5020 — the rival will switch it to 6030 mid-flight
        res = client.post("/api/case-sessions/neodent-gm/sites/4/preview")
        assert res.status_code == 409
        assert "changed while the preview" in res.json()["detail"]
        # the rival's act survived; no stale facts landed on it
        site = SessionStore(settings.product_root).load("neodent-gm").sites["4"]
        assert site.declared_variant == "6030"
        assert site.status is SiteStatus.DECLARED
        assert site.seat_method is None


class TestReview:
    """POST/DELETE /{id}/sites/{tooth}/review (plan §4 Declare / AM-8): the operator's
    ATTESTATION over the live panes — an ACT, like choices (AM-4 allows acts, forbids
    claimed verdicts). No body at all, both ways: the act is the request itself, so
    there is no field a claimed outcome could ride in on. The previewed->ready move is
    the machine's ``review_ready``; a tick over nothing stays impossible because the
    machine refuses it, not because the UI hides a checkbox."""

    def _previewed(self, settings, tooth="4"):
        store = SessionStore(settings.product_root)
        s = store.load("neodent-gm")
        s.sites[tooth] = SiteSession(status=SiteStatus.PREVIEWED,
                                     declared_variant="5020",
                                     seat_method="rim-seat", rim_agreement_mm=0.07)
        store.save(s)

    def test_an_unknown_case_is_a_404(self, client):
        assert client.post(
            "/api/case-sessions/no-such-case/sites/4/review").status_code == 404

    def test_a_tooth_the_case_does_not_have_is_a_404(self, client):
        res = client.post("/api/case-sessions/neodent-gm/sites/31/review")
        assert res.status_code == 404
        assert "not a site" in res.json()["detail"]

    def test_a_tick_over_nothing_is_refused_in_the_ladders_words(self, settings):
        # detected AND declared sites refuse alike: no preview, nothing to attest to
        client = TestClient(create_app(settings))
        res = client.post("/api/case-sessions/neodent-gm/sites/4/review")
        assert res.status_code == 422
        assert "cannot review_ready" in res.json()["detail"]
        declare_site(client)
        res = client.post("/api/case-sessions/neodent-gm/sites/4/review")
        assert res.status_code == 422
        assert "'declared'" in res.json()["detail"]
        persisted = SessionStore(settings.product_root).load("neodent-gm")
        assert persisted.sites["4"].status is SiteStatus.DECLARED

    def test_the_tick_moves_previewed_to_ready_and_the_detail_says_so(self, settings):
        self._previewed(settings)
        client = TestClient(create_app(settings))
        body = client.post("/api/case-sessions/neodent-gm/sites/4/review").json()
        sites = {v["tooth"]: v for v in body["sites"]}
        assert sites[4]["status"] == "ready"
        # persisted, and the worklist rollup counts it — the queue chip's fact
        row, = TestClient(create_app(settings)).get("/api/case-sessions").json()
        assert row["sites"]["ready"] == 1

    def test_the_untick_withdraws_the_review(self, settings):
        self._previewed(settings)
        client = TestClient(create_app(settings))
        client.post("/api/case-sessions/neodent-gm/sites/4/review")
        body = client.delete("/api/case-sessions/neodent-gm/sites/4/review").json()
        sites = {v["tooth"]: v for v in body["sites"]}
        assert sites[4]["status"] == "previewed"
        # the preview's facts survive the untick — only the attestation is gone
        site = SessionStore(settings.product_root).load("neodent-gm").sites["4"]
        assert site.seat_method == "rim-seat"

    def test_withdrawing_a_review_that_was_never_given_is_refused(self, settings):
        self._previewed(settings)
        client = TestClient(create_app(settings))
        res = client.delete("/api/case-sessions/neodent-gm/sites/4/review")
        assert res.status_code == 422
        assert "cannot withdraw_review" in res.json()["detail"]


class TestWriteConflicts:
    """The store's CAS surfaced at the endpoints (slice 5a): every mutating route
    fresh-loads, mutates, saves — and on a conflict retries ONCE on a fresh document
    before refusing with 409. One retry is deliberate: a single interleaved writer is
    the normal case (detect finishing while a declaration lands); losing twice means
    the case is genuinely contended and the operator should see what changed rather
    than have the BFF silently win a race on their behalf."""

    def test_an_interleaved_write_is_absorbed_by_one_clean_retry(self, settings):
        client = TestClient(create_app(settings))
        client.app.state.sessions = InterferingStore(settings.product_root, 1)
        res = client.put("/api/case-sessions/neodent-gm/choices", json={
            "construction_path": "dess/neodent-gm-scanbody.stl",
            "jaw": "upper",
            "gingival_offset_mm": 0.2,
        })
        assert res.status_code == 200
        assert res.json()["choices"]["complete"] is True
        # BOTH writes survived: the rival's fact and the operator's choices
        persisted = SessionStore(settings.product_root).load("neodent-gm")
        assert persisted.adjust_visited is True
        assert persisted.choices.complete is True

    def test_a_genuinely_contended_case_is_a_409_that_says_so(self, settings):
        client = TestClient(create_app(settings))
        client.app.state.sessions = InterferingStore(settings.product_root, 99)
        res = client.put("/api/case-sessions/neodent-gm/choices", json={"jaw": "upper"})
        assert res.status_code == 409
        detail = res.json()["detail"]
        assert "changed underneath" in detail
        assert "neodent-gm" in detail
        # the refused write left nothing of itself behind
        assert SessionStore(settings.product_root).load("neodent-gm").choices.jaw is None

    def test_two_truly_concurrent_mutations_both_land(self, settings):
        # the 5a verification's failing interleave: two handler writes overlapping on
        # the threadpool. A barrier holds both writers on a fresh load until BOTH have
        # mutated, forcing the save-save overlap every round: one must land directly,
        # the other through the CAS retry — no silent loss, no escaped tmp-file error.
        store = SessionStore(settings.product_root)
        for round_no in range(5):
            case_id = f"case-{round_no}"
            barrier = threading.Barrier(2)

            def mutate_for(tooth: str):
                first_attempt = [True]

                def mutate(session):
                    session.sites[tooth] = SiteSession(status=SiteStatus.DECLARED,
                                                       declared_variant="5020")
                    if first_attempt[0]:       # the retry re-applies without waiting
                        first_attempt[0] = False
                        barrier.wait(timeout=5)
                return mutate

            errors: list = []

            def run(tooth: str):
                try:
                    case_sessions._mutate_session(store, case_id, mutate_for(tooth))
                except Exception as exc:   # noqa: BLE001 — any escape is the finding
                    errors.append(exc)

            threads = [threading.Thread(target=run, args=(t,)) for t in ("4", "13")]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            assert errors == [], f"round {round_no}: {errors}"
            persisted = SessionStore(settings.product_root).load(case_id)
            assert set(persisted.sites) == {"4", "13"}, (
                f"round {round_no}: a write was silently lost — {set(persisted.sites)}")
            assert persisted.version == 2   # two landings, one bump each

    def test_a_rival_system_switch_forces_the_declaration_to_revalidate(self, settings):
        # the dangling-variant race (5a adversarial review, item 3): the declaration's
        # validity depends on SESSION state (the effective system), so a rival switch
        # landing between its load and its save must force a re-judgment — the retry
        # re-validates against the fresh document instead of re-applying a verdict
        # reached against the old one. A neodent part must never land on an astra
        # case with a 200.
        caps = settings.data_root / "library/caps/astra-ev"
        caps.mkdir(parents=True)
        (caps / "astra-ev-3010.stl").touch()
        client = TestClient(create_app(settings))
        client.app.state.sessions = SystemSwitchingStore(settings.product_root,
                                                         "astra-ev")
        res = client.put("/api/case-sessions/neodent-gm/sites/4/declaration",
                         json={"variant": "5020"})   # a neodent-gm part
        assert res.status_code == 422
        assert "not a part of the 'astra-ev' library" in res.json()["detail"]
        persisted = SessionStore(settings.product_root).load("neodent-gm")
        assert persisted.system == "astra-ev"        # the rival's act survived
        assert not any(s.declared_variant for s in persisted.sites.values())


class TestWorklistRowErrors:
    """THE PER-ROW ERROR CONTRACT (slice 5a, carried from the slice-4 review): one
    corrupt session file must not 500 the whole worklist — the 20-scan morning's home
    screen would go dark over one case's trouble. The row itself carries the refusal
    (the store's own words) and every session-derived fact on it is honestly absent —
    the identity fields (id, doctor, jaw) come from case DISCOVERY, which still works.
    The case detail keeps refusing loudly: opening the corrupt case is where the
    trouble must be faced, the list is where the other 19 cases must stay workable."""

    @staticmethod
    def _second_case(settings):
        scans = settings.data_root / "scans/doctor-other"
        scans.mkdir(parents=True)
        (scans / "lower_jaw.stl").touch()

    def test_a_corrupt_session_becomes_an_error_row_not_a_500(self, settings):
        self._second_case(settings)
        client = TestClient(create_app(settings))
        bad = settings.product_root / "neodent-gm"
        bad.mkdir(parents=True)
        (bad / "session.json").write_text("{this is not json")
        res = client.get("/api/case-sessions")
        assert res.status_code == 200
        rows = {row["id"]: row for row in res.json()}
        assert set(rows) == {"neodent-gm", "other"}
        # the corrupt row: identity intact, refusal stated, no claimed session facts
        corrupt = rows["neodent-gm"]
        assert corrupt["error"] is not None and "session" in corrupt["error"]
        assert corrupt["sites"] is None
        assert corrupt["run_state"] is None
        assert corrupt["confirmed"] is None
        assert corrupt["detected"] is None
        assert corrupt["choices_complete"] is None
        # the DISCOVERY facts survive it (2026-07-31): a corrupt session says
        # nothing about the data tree, so the scan card's teeth and file size
        # still stand beside identity
        assert corrupt["teeth"] == [4, 13]
        assert corrupt["scan_bytes"] == 0
        # the healthy row is untouched by its neighbour's trouble
        healthy = rows["other"]
        assert healthy["error"] is None
        assert healthy["sites"] == {"total": 0, "declared": 0, "ready": 0,
                                    "flagged": 0}

    def test_a_healthy_worklist_carries_no_error_field_noise(self, client):
        (row,) = client.get("/api/case-sessions").json()
        assert row["error"] is None


class TestStatusesAreNeverClientWritable:
    """STRUCTURAL (AM-4), slice-4 form. The old invariant was "the route table is
    GET-only"; slice 4 updates it DELIBERATELY, not around: choices and compute triggers
    are legitimate writes — claimed OUTCOMES are not. So (1) every non-GET route must
    sit on the explicit allowlist below, and (2) no allowlisted route's request model
    may carry a status-shaped field, walked recursively so a nested model cannot smuggle
    one. A presentational app PATCHing a flagged site to ready stays impossible — there
    is no such route, and no legitimate route's body could express it."""

    ACTION_ALLOWLIST = {
        ("POST", "/api/case-sessions/{case_id}/detect"),   # compute trigger, no body
        # a cap the DETECTOR MISSED, marked by the operator (client 2026-07-28):
        # {"tooth", "center"} — WHICH tooth and WHERE, both acts in this allowlist's
        # sense. The site starts at DETECTED and climbs the same ladder, so marking
        # buys the operator work to do and never a rung
        ("POST", "/api/case-sessions/{case_id}/sites"),
        ("PUT", "/api/case-sessions/{case_id}/choices"),   # operator acts (plan §4)
        ("PUT", "/api/case-sessions/{case_id}/system"),    # case-scoped system (AM-8)
        # the per-site variant declaration (AM-8) — the status move it causes is the
        # machine's (bff/status.py), never a field in this body
        ("PUT", "/api/case-sessions/{case_id}/sites/{tooth}/declaration"),
        # the pre-run preview (5b): a compute trigger like detect — NO body; the
        # declaration and choices it seats with come from the session, so there is
        # nothing a client could claim with
        ("POST", "/api/case-sessions/{case_id}/sites/{tooth}/preview"),
        # the review tick (5b, AM-8): the operator's ATTESTATION — an act whose whole
        # content is the request itself, both ways; the previewed->ready move is the
        # machine's review_ready, the untick its withdraw_review
        ("POST", "/api/case-sessions/{case_id}/sites/{tooth}/review"),
        ("DELETE", "/api/case-sessions/{case_id}/sites/{tooth}/review"),
        # the authorized run (5c): a compute trigger like detect/preview — NO body;
        # the selection it runs is the session's own acts, the gate is server-minted
        # (AM-8), and the verdict landing goes through the status machine
        ("POST", "/api/case-sessions/{case_id}/run"),
        # the confirmation (slice 8, AM-10/AM-12): the DELIBERATE extension of this
        # allowlist's doctrine — dispositions (release|withhold per tooth) and
        # per-flag acknowledgments are operator ACTS, like choices: they say what
        # the operator DOES with a site, never what the site IS. Statuses, gates
        # and evidence stay server-derived, and the server refuses any disposition
        # set that does not match the evidence it derived itself.
        ("POST", "/api/case-sessions/{case_id}/confirm"),
        # the payment stub (slice 8, AM-11): {"authorize": true} — the explicit
        # act, fail-closed, provider recorded as "stub". Its ONE other field is
        # ``invoice_fingerprint`` (audit 2026-07-31), and it is admissible for
        # exactly the reason a disposition is: it is an opaque digest of the
        # document the SERVER served, echoed back as a precondition — "this is
        # what I was shown", never "this is what I owe". No amount rides on this
        # wire and none ever will; the server prices at authorization time and
        # refuses when the two documents differ.
        ("POST", "/api/case-sessions/{case_id}/payment"),
        # THE CHECKOUT RETURN LEG (plan §10-A: "a checkout screen and a return").
        # An operator ACT in this allowlist's structural sense even though it
        # mutates nothing: it is a non-GET route, so the doctrine still applies —
        # every non-GET sits on this list, named, with its body checked for a
        # status-shaped field like every other. {"reference": "..."} is an
        # opaque identifier, never a claimed outcome; there is no field this body
        # COULD carry a "payment succeeded" claim in, which is the whole point
        # (bff/resources/deliver.checkout_return's own docstring).
        ("POST", "/api/case-sessions/{case_id}/checkout/return"),
        # release = disclosure (slice 8, AM-1): body-less — everything it consumes
        # (confirmation, dispositions, payment) is already the session's; validity
        # is judged by RE-DERIVING the evidence, never by trusting the record
        ("POST", "/api/case-sessions/{case_id}/release"),
        # the demo's door back (client 2026-07-30): withdraw confirmation, payment
        # and release TOGETHER — body-less, an explicit operator act; the state it
        # clears stays server-side truth right up until this is called, which is
        # what keeps the forged-checkout-return test meaningful
        ("POST", "/api/case-sessions/{case_id}/delivery/reset"),
        # the whole case back to fresh intake (client 2026-07-30: "resetting the
        # cases persistance") — body-less; clears the session, never the immutable
        # run directories, which AM-1 keeps as history
        ("POST", "/api/case-sessions/{case_id}/reset"),
        # THE DELIVERY-vs-SKIP FORK (client 2026-07-27) — this allowlist's doctrine
        # extended once more, and the reason is worth stating: {"decision": "skip"}
        # says what the operator DID with the Adjust stage, never what any site IS.
        # It moves no rung, opens and closes no stage (flow reachability never reads
        # it — skip does not block navigating to Adjust), and the ladder stays
        # server-derived. The body carries no field a claimed fit-outcome could ride
        # in on, which is why "skip" is admissible where "ready" never will be.
        ("POST", "/api/case-sessions/{case_id}/adjust-decision"),
        # THE FOUR ADJUST TOOLS (slice 6). Each body carries the operator's own
        # PROPOSAL — a rotation step, a click, named correspondences, a matching
        # diameter — and nothing else. Not one of them can express an outcome: the
        # gates decide whether the proposal lands, the status machine decides where
        # the site stands afterwards, and a refusal writes nothing at all. That is
        # why a geometry a client chose is admissible where a verdict never will be.
        ("POST", "/api/case-sessions/{case_id}/sites/{tooth}/rotation"),
        ("POST", "/api/case-sessions/{case_id}/sites/{tooth}/mark-trench"),
        ("POST", "/api/case-sessions/{case_id}/sites/{tooth}/fit-by-points"),
        ("POST", "/api/case-sessions/{case_id}/sites/{tooth}/best-fit"),
        # THE RE-READ (gap ``re-preview-a-site-without-applying-a-tool``,
        # 2026-07-31) — body-less, like detect/preview/run, and for the same
        # reason: everything it reads is on disk in the run directory, so there
        # is nothing a client could claim with. It applies no tool, moves no
        # rung, and what it writes onto the row is what the SERVER measured over
        # the pose that shipped. A body here could only ever carry the outcome
        # the design's own re-preview label pre-announces, which is exactly the
        # client-side verdict this allowlist exists to make unexpressible.
        ("POST", "/api/case-sessions/{case_id}/sites/{tooth}/re-preview"),
        # DROPPING A CAP (design flow.dc.html dropSite 1345-1354; gap
        # ``drop-a-cap-from-adjust``, 2026-07-31): {"withhold": true|false} — the
        # DRAFT of the disposition ``ConfirmIn`` has carried since slice 8, made
        # reachable from Adjust instead of only from the signing screen. Admissible
        # for exactly the reason a disposition is: it says what the operator DOES
        # with a site (holds it back from the release and the bill), never what the
        # site IS. It moves no rung, the run still aligns the site, and the
        # confirmation is still the only place a disposition is sealed — an intent
        # is a draft, and the body of THIS route has no field a claimed fit-outcome
        # could ride in on.
        ("PUT", "/api/case-sessions/{case_id}/sites/{tooth}/withhold"),
        # RE-MARKING AN EXISTING SITE'S CENTRE (client 2026-08-01, the tooth-29 gap):
        # {"center": [x, y, z]} — post_marked_site's exact complement (WHERE, over a
        # tooth that must already BE a site rather than must not be). One field,
        # sent exactly as clicked and never re-centred here — the re-click
        # pair-integrity rule. It is a reset boundary like the choices/system/
        # declaration routes, both a compute-derivation trigger and an operator
        # act, but no field on this body could ever carry a claimed outcome: the
        # reset it causes is entirely the status machine's and session.py's
        # boundary helpers, never a value in this request.
        ("PUT", "/api/case-sessions/{case_id}/sites/{tooth}/mark"),
        # ONE site's relief override (§10-B/C): the ask in mm or null — WHAT the
        # operator wants cut, never what the site IS; over a done run it re-emits
        ("PUT", "/api/case-sessions/{case_id}/sites/{tooth}/relief"),
        # ACCEPT AS FLAGGED EXCEPTION, IN ADVANCE (client ruling 2026-08-02):
        # body-less both ways, ``withhold_intent``'s sibling — the act's whole
        # content is the request itself, both directions. It is a DRAFT that
        # PRE-FILLS Deliver's row-by-row checkbox (``SiteSession.
        # exception_intent``), never a signature: ``ConfirmIn.acknowledged_flags``
        # stays required and stays the only thing that seals a released flagged
        # row. No field here could ever carry a claimed verdict — there is no
        # field at all.
        ("POST", "/api/case-sessions/{case_id}/sites/{tooth}/acknowledge"),
        ("DELETE", "/api/case-sessions/{case_id}/sites/{tooth}/acknowledge"),
    }
    STATUS_SHAPED = {"status", "state", "verdict", "gate", "flagged", "ready",
                     "confirmed"}

    @staticmethod
    def _field_names(model, seen=None):
        """Every field name of a Pydantic model, recursing into nested models."""
        import typing

        from pydantic import BaseModel

        seen = seen if seen is not None else set()
        if model in seen:  # cycles cannot hide a field either
            return set()
        seen.add(model)
        names = set()
        for name, field in model.model_fields.items():
            names.add(name)
            stack = [field.annotation]
            while stack:
                t = stack.pop()
                if isinstance(t, type) and issubclass(t, BaseModel):
                    names |= TestStatusesAreNeverClientWritable._field_names(t, seen)
                else:
                    stack.extend(typing.get_args(t))
        return names

    def _case_session_routes(self, client):
        return [r for r in client.app.routes
                if getattr(r, "path", "").startswith("/api/case-sessions")]

    def test_every_non_get_route_is_on_the_allowlist(self, client):
        offenders = []
        for route in self._case_session_routes(client):
            for method in set(route.methods) - {"GET", "HEAD", "OPTIONS"}:
                if (method, route.path) not in self.ACTION_ALLOWLIST:
                    offenders.append((method, route.path))
        assert offenders == []
        # and both directions hold: the allowlist names real routes, not wishes
        present = {(m, r.path) for r in self._case_session_routes(client)
                   for m in r.methods}
        assert self.ACTION_ALLOWLIST <= present

    def test_no_action_request_model_carries_a_status_shaped_field(self, client):
        offenders = []
        for route in self._case_session_routes(client):
            if not ({(m, route.path) for m in route.methods} & self.ACTION_ALLOWLIST):
                continue
            body_field = getattr(route, "body_field", None)
            if body_field is None:
                continue  # the detect trigger: no body at all — nothing to claim with
            shaped = (self._field_names(body_field.field_info.annotation)
                      & self.STATUS_SHAPED)
            if shaped:
                offenders.append((route.path, sorted(shaped)))
        assert offenders == []

    def test_reading_writes_nothing_to_the_product_data_plane(self, client, product_root):
        client.get("/api/case-sessions")
        client.get("/api/case-sessions/neodent-gm")
        assert not product_root.exists()

    @staticmethod
    def _nested_models(model, seen=None):
        """Every Pydantic model reachable from a request model's annotations."""
        import typing

        from pydantic import BaseModel

        seen = seen if seen is not None else set()
        if model in seen:
            return set()
        seen.add(model)
        out = {model}
        for field in model.model_fields.values():
            stack = [field.annotation]
            while stack:
                t = stack.pop()
                if isinstance(t, type) and issubclass(t, BaseModel):
                    out |= TestStatusesAreNeverClientWritable._nested_models(t, seen)
                else:
                    stack.extend(typing.get_args(t))
        return out

    def test_every_request_model_forbids_unknown_fields(self, client):
        """extra="forbid" on EVERY request model, nested ones included (slice 5a,
        carried from the slice-4 review): pydantic's default silently DROPS unknown
        fields, so a client sending {"status": "ready"} beside a legitimate choice
        would get a 200 and believe its claim was accepted. Refusing loudly keeps the
        no-claimed-outcomes doctrine honest at the wire, not just in the field list."""
        offenders = []
        for route in self._case_session_routes(client):
            body_field = getattr(route, "body_field", None)
            if body_field is None:
                continue
            for model in self._nested_models(body_field.field_info.annotation):
                if model.model_config.get("extra") != "forbid":
                    offenders.append((route.path, model.__name__))
        assert offenders == []

    def test_an_unknown_field_beside_a_legitimate_choice_is_refused(self, client):
        # the behavioral face of the introspection above: a smuggled claim is a 422,
        # never a 200 that quietly ignored it
        res = client.put("/api/case-sessions/neodent-gm/choices",
                         json={"jaw": "upper", "status": "ready"})
        assert res.status_code == 422


class TestMarkingACapTheDetectorMissed:
    """Client 2026-07-28: detection finds 8 of the 10 sites on this fleet. Before this
    route the other two were unworkable — a centre lived only in the case record, which
    the ingest writes and an operator cannot."""

    def test_a_marked_cap_becomes_a_site_with_its_centre_on_the_surface(self, client):
        before = {s["tooth"] for s in client.get(
            "/api/case-sessions/neodent-gm").json()["sites"]}
        assert 7 not in before

        r = client.post("/api/case-sessions/neodent-gm/sites",
                        json={"tooth": 7, "center": [1.5, -2.0, 3.25]})
        assert r.status_code == 200, r.text
        site = next(s for s in r.json()["sites"] if s["tooth"] == 7)
        # the surface must not deny the centre the run is about to use
        assert site["center"] == [1.5, -2.0, 3.25]
        # marking buys WORK, never a rung
        assert site["status"] == "detected"

    def test_marking_a_site_that_already_exists_REFUSES(self, client):
        # re-marking would retire that site's preview and its review; a mis-typed
        # tooth number must not be able to do that silently
        r = client.post("/api/case-sessions/neodent-gm/sites",
                        json={"tooth": 13, "center": [0.0, 0.0, 0.0]})
        assert r.status_code == 409
        assert "already a site" in r.json()["detail"]

    def test_a_centre_that_is_not_three_numbers_refuses(self, client):
        r = client.post("/api/case-sessions/neodent-gm/sites",
                        json={"tooth": 7, "center": [0.0, 0.0]})
        assert r.status_code == 422, r.text

    def test_a_NON_FINITE_centre_refuses_even_though_json_cannot_normally_carry_one(
            self, client):
        """Python's json.dumps REFUSES NaN, so `json=` can never produce this — the
        first version of this test failed in the client, not the server, and would
        have left the guard untested while looking green. Sent as a raw body, which
        json.loads does accept, so the handler's own check is what answers."""
        r = client.post("/api/case-sessions/neodent-gm/sites",
                        content='{"tooth": 7, "center": [0.0, 0.0, NaN]}',
                        headers={"content-type": "application/json"})
        assert r.status_code == 422, r.text
        assert "finite" in r.json()["detail"]

    def test_a_tooth_outside_the_arch_refuses(self, client):
        r = client.post("/api/case-sessions/neodent-gm/sites",
                        json={"tooth": 99, "center": [0.0, 0.0, 0.0]})
        assert r.status_code == 422
        assert "not a tooth number" in r.json()["detail"]

    def test_the_body_cannot_carry_anything_else(self, client):
        # extra=forbid: no status, no verdict, no centre-adjacent smuggling
        r = client.post("/api/case-sessions/neodent-gm/sites",
                        json={"tooth": 7, "center": [0.0, 0.0, 0.0],
                              "status": "ready"})
        assert r.status_code == 422

    def test_marking_an_existing_site_now_points_at_the_re_mark_door(self, client):
        # THE OLD REFUSAL NAMED A REASON WITHOUT NAMING THE DOOR (gap
        # ``re-mark-a-sites-centre``, 2026-08-01): the two routes now point at each
        # other so an operator who hits the wrong one learns where the right one is.
        r = client.post("/api/case-sessions/neodent-gm/sites",
                        json={"tooth": 13, "center": [0.0, 0.0, 0.0]})
        assert r.status_code == 409
        assert "/sites/13/mark" in r.json()["detail"]


class TestReMarkingAnExistingSite:
    """Client 2026-08-01 (the tooth-29 gap on case cap6020-neodent-gm: the
    detector's proposed centre sat visibly off the cap, and the operator had no way
    to correct it). ``post_marked_site`` refuses an existing tooth and NAMES the
    reason without building the act — 're-marking an existing cap is a different
    act with different consequences (it would invalidate a preview and a review)'.
    This is that act: post_marked_site's EXACT COMPLEMENT, both in validation
    (finite [x, y, z], nothing else) and in which tooth it accepts."""

    def test_re_marking_a_curated_site_replaces_its_centre_on_the_surface(self, client):
        # tooth 4 is curated (conftest's suggested_sites, centre [1, 2, 3]) and was
        # never operator-marked — re-marking must still work on it
        r = client.put("/api/case-sessions/neodent-gm/sites/4/mark",
                       json={"center": [9.0, 8.0, 7.0]})
        assert r.status_code == 200, r.text
        site = next(s for s in r.json()["sites"] if s["tooth"] == 4)
        assert site["center"] == [9.0, 8.0, 7.0]
        # marking buys work, never a rung — re-marking must not either
        assert site["status"] == "detected"

    def test_re_marking_a_previously_hand_marked_site_replaces_it_again(self, client):
        marked = client.post("/api/case-sessions/neodent-gm/sites",
                             json={"tooth": 7, "center": [1.0, 1.0, 1.0]})
        assert marked.status_code == 200, marked.text
        r = client.put("/api/case-sessions/neodent-gm/sites/7/mark",
                       json={"center": [2.0, 2.0, 2.0]})
        assert r.status_code == 200, r.text
        site = next(s for s in r.json()["sites"] if s["tooth"] == 7)
        assert site["center"] == [2.0, 2.0, 2.0]

    def test_re_marking_a_tooth_that_is_not_a_site_yet_REFUSES(self, client):
        # the exact complement of post_marked_site's guard — 404, not 409: the path
        # names a subresource the case does not have yet
        r = client.put("/api/case-sessions/neodent-gm/sites/9/mark",
                       json={"center": [0.0, 0.0, 0.0]})
        assert r.status_code == 404
        assert "POST" in r.json()["detail"]
        assert "/sites" in r.json()["detail"]

    def test_a_centre_that_is_not_three_numbers_refuses(self, client):
        r = client.put("/api/case-sessions/neodent-gm/sites/4/mark",
                       json={"center": [0.0, 0.0]})
        assert r.status_code == 422, r.text

    def test_a_NON_FINITE_centre_refuses_even_though_json_cannot_normally_carry_one(
            self, client):
        r = client.put("/api/case-sessions/neodent-gm/sites/4/mark",
                       content='{"center": [0.0, 0.0, NaN]}',
                       headers={"content-type": "application/json"})
        assert r.status_code == 422, r.text
        assert "finite" in r.json()["detail"]

    def test_the_body_cannot_carry_a_tooth_or_anything_else(self, client):
        # extra=forbid: the tooth is the path segment, never a second source of truth
        assert client.put("/api/case-sessions/neodent-gm/sites/4/mark",
                          json={"center": [0.0, 0.0, 0.0], "tooth": 4}
                          ).status_code == 422
        assert client.put("/api/case-sessions/neodent-gm/sites/4/mark",
                          json={"center": [0.0, 0.0, 0.0], "status": "ready"}
                          ).status_code == 422

    def test_an_identical_re_mark_is_not_an_act(self, client, product_root):
        # tooth 4's suggested centre is [1.0, 2.0, 3.0] (conftest.make_data_tree) —
        # resending it EXACTLY changes nothing (the SeatedSelection precedent: an
        # identical re-assertion flips no equality and costs nobody a reset)
        before = SessionStore(product_root).load("neodent-gm")
        r = client.put("/api/case-sessions/neodent-gm/sites/4/mark",
                       json={"center": [1.0, 2.0, 3.0]})
        assert r.status_code == 200, r.text
        after = SessionStore(product_root).load("neodent-gm")
        assert after.activity_recorded == before.activity_recorded
        assert "4" not in after.sites   # nothing was ever written for it

    def test_re_marking_retires_the_sites_preview_review_and_the_run(
            self, client, product_root):
        store = SessionStore(product_root)
        session = store.load("neodent-gm")
        session.sites["4"] = SiteSession(
            status=SiteStatus.READY, declared_variant="5020",
            seat_method="rim-seat", rim_agreement_mm=0.07,
            seated_selection=seated())
        session.run = RunSession(job_id="run-1", run_id="run-1", state="done",
                                 summary={"sites": [{"tooth": 4}]})
        store.save(session)

        r = client.put("/api/case-sessions/neodent-gm/sites/4/mark",
                       json={"center": [9.0, 8.0, 7.0]})
        assert r.status_code == 200, r.text
        body = r.json()
        site = next(s for s in body["sites"] if s["tooth"] == 4)
        # the declared VARIANT survives — the cap did not change, only its centre —
        # but every fact derived from the OLD centre falls
        assert site["declared_variant"] == "5020"
        assert site["status"] == "declared"
        assert site["seat_method"] is None
        assert site["rim_agreement_mm"] is None
        # the run was cropped around the old centre; stale physics never
        # masquerades as current (5c's boundary, mirrored for a fourth trigger)
        assert body["session"]["run_state"] == "none"

    def test_re_marking_retires_a_standing_confirmation_too(self, client, product_root):
        """THE ONE PLACE THIS BOUNDARY GOES FURTHER than its three siblings
        (choices/system/declaration — session.clear_current_run's own docstring,
        pinned by test_pricing: they deliberately LEAVE a standing confirmation
        alone, protected only by the deliver-side gates re-checking the run id).
        A re-mark is different in kind: what stands confirmed there was sealed over
        evidence measured from the exact centre the operator has just said is
        WRONG, and the words this app must show before arming the pick (client
        2026-08-01) promise 'anything signed over it' retires. A promise made out
        loud before the act must come true, not merely become unreachable behind a
        gate three requests later."""
        store = SessionStore(product_root)
        session = store.load("neodent-gm")
        session.run = RunSession(job_id="run-1", run_id="run-1", state="done",
                                 summary={"sites": [{"tooth": 4}]})
        session.confirmation = ConfirmationRecord(
            at="2026-08-01T00:00:00+00:00", run_id="run-1",
            evidence_sha256="0" * 64, dispositions={"4": "release"})
        store.save(session)

        r = client.put("/api/case-sessions/neodent-gm/sites/4/mark",
                       json={"center": [9.0, 8.0, 7.0]})
        assert r.status_code == 200, r.text
        assert r.json()["session"]["confirmed"] is False
        assert SessionStore(product_root).load("neodent-gm").confirmation is None

    def test_a_neighbours_run_derived_rung_falls_with_the_run(
            self, client, product_root):
        """THE STALE-FLAGGED CONTRADICTION (client 2026-08-06): tooth 4's re-mark
        retired the case's run, and tooth 13 — untouched — kept the FLAGGED rung
        that only that run's verdict ever wrote. The queue then read 'Flagged by
        the run — no run has measured this fit yet' while Adjustment (which needs
        a run) refused to open: a verdict outliving its run, wedging the flow.
        FLAGGED and ADJUSTED are post-run rungs; when the run pointer falls, they
        fall to READY — the confirmation that admitted them to the run stands,
        and the ready sentence ('no run has measured this fit yet') is true."""
        store = SessionStore(product_root)
        session = store.load("neodent-gm")
        session.sites["4"] = SiteSession(
            status=SiteStatus.READY, declared_variant="5020")
        session.sites["13"] = SiteSession(
            status=SiteStatus.FLAGGED, declared_variant="5020")
        session.sites["29"] = SiteSession(
            status=SiteStatus.ADJUSTED, declared_variant="5020")
        session.run = RunSession(job_id="run-1", run_id="run-1", state="done",
                                 summary={"sites": [{"tooth": 4}]})
        store.save(session)

        r = client.put("/api/case-sessions/neodent-gm/sites/4/mark",
                       json={"center": [9.0, 8.0, 7.0]})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["session"]["run_state"] == "none"
        by_tooth = {s["tooth"]: s for s in body["sites"]}
        assert by_tooth[13]["status"] == "ready"
        assert by_tooth[29]["status"] == "ready"
        # the changed site itself keeps the deeper reset its own boundary owes
        assert by_tooth[4]["status"] == "declared"

    def test_a_standing_document_with_flagged_but_no_run_heals_on_load(
            self, client, product_root):
        """The same rule at the LOAD seam: documents persisted BEFORE
        clear_current_run learned the demotion already hold the contradiction —
        they must heal on their next read, not wait for a boundary to fire."""
        store = SessionStore(product_root)
        session = store.load("neodent-gm")
        session.sites["13"] = SiteSession(
            status=SiteStatus.FLAGGED, declared_variant="5020")
        session.run = None
        store.save(session)

        reloaded = SessionStore(product_root).load("neodent-gm")
        assert reloaded.sites["13"].status == SiteStatus.READY
        r = client.get("/api/case-sessions/neodent-gm")
        site = next(s for s in r.json()["sites"] if s["tooth"] == 13)
        assert site["status"] == "ready"

    def test_the_activity_log_names_a_re_mark_differently_from_a_first_mark(
            self, client, product_root):
        r = client.put("/api/case-sessions/neodent-gm/sites/4/mark",
                       json={"center": [9.0, 8.0, 7.0]})
        assert r.status_code == 200, r.text
        session = SessionStore(product_root).load("neodent-gm")
        assert session.activity[-1].event == "site-remarked"
        assert session.activity[-1].tooth == 4
