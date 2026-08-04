"""THE RUN RESOURCE (plan §7 slice 5c; §1.2/AM-1, §3/AM-3, §4 Declare/AM-8):
POST /api/case-sessions/{id}/run — the AUTHORIZED gate, server-minted — and
GET /api/case-sessions/{id}/run — the persisted run facts, Adjust's and Deliver's
read surface.

The POST is body-less (a compute trigger like detect/preview — the selection it runs
is the SESSION's, so there is nothing a client could claim with): the gate refuses 422
unless the choices are complete AND every site is READY, naming each missing piece;
authorized, it mints the immutable run_id, persists the job receipt INSIDE the
mutation (25604e7's rule), calls the worker port, and LANDS the results — per-site
verdicts through the status machine (guidance "ready" holds the rung; anything else is
the flag event's first legitimate writer), the summary + package file list as run
facts, done|refused mirrored to the worklist row.

RESET BOUNDARIES extend here: any post-run system/declaration/choices CHANGE clears
the session's current-run pointer (the run directory survives on disk — immutable
history — but a stale run can never masquerade as current), and the statuses regress
per the boundaries 5a/5b already stated.

The port is faked per test (the adapter's own contract is test_worker_port's; the
physics is the worker suite's) — these tests pin the RESOURCE: gate words, landing,
persistence, boundaries.
"""
from __future__ import annotations

import copy
import json
from typing import Optional

import pytest
from fastapi.testclient import TestClient

from bff.config import Settings
from bff.main import create_app
from bff.ports.worker import JobState, JobStatus
from bff.session import (CaseChoices, SeatedSelection, SessionStore, SiteSession,
                         SiteStatus)

from conftest import make_data_tree


# --- the fake port -----------------------------------------------------------------

class FakeWorker:
    """A port double: records the submit, answers with a configured outcome. The
    in-process adapter's real behavior (immutability, refusal.json, timestamps) is
    test_worker_port's business — here the port is a seam."""

    def __init__(self, summary: Optional[dict] = None, refusal: Optional[str] = None,
                 error: Optional[str] = None, on_submit=None):
        self.summary = summary
        self.refusal = refusal
        self.error = error
        self.on_submit = on_submit
        self.submitted = []

    def submit(self, case_id: str, request: dict) -> str:
        self.submitted.append((case_id, copy.deepcopy(request)))
        if self.on_submit is not None:
            self.on_submit(case_id, request)
        return request["run_id"]

    def status(self, job_id: str) -> JobStatus:
        if self.error is not None:
            return JobStatus(job_id=job_id, state=JobState.FAILED, error=self.error)
        if self.refusal is not None:
            return JobStatus(job_id=job_id, state=JobState.REFUSED,
                             refusal=self.refusal)
        return JobStatus(job_id=job_id, state=JobState.DONE)

    def result(self, job_id: str) -> dict:
        if self.summary is None:
            raise KeyError(job_id)
        return self.summary


# --- fixtures + seeding ------------------------------------------------------------

@pytest.fixture
def product_root(tmp_path):
    return tmp_path / "product"


@pytest.fixture
def data_root(tmp_path):
    return make_data_tree(tmp_path / "data")


@pytest.fixture
def settings(data_root, product_root) -> Settings:
    return Settings(data_root=data_root, product_root=product_root)


def client_with(settings: Settings, worker: FakeWorker) -> TestClient:
    client = TestClient(create_app(settings))
    client.app.state.worker = worker
    return client


def seed_ready(product_root, teeth=("4", "13"), variant="5020",
               choices_complete=True) -> None:
    """Drive the session to Declare-complete THROUGH THE STORE — the same server-side
    door the resource itself uses; there is no client path to a status by design.
    The ``seated_selection`` mirrors what the preview route itself persists (the
    2026-07-28 drift guard): a READY whose recorded seat is absent or no longer
    matches the case's current selection is refused by the authorized gate."""
    store = SessionStore(product_root)
    s = store.load("neodent-gm")
    for tooth in teeth:
        s.sites[tooth] = SiteSession(
            status=SiteStatus.READY, declared_variant=variant,
            seat_method="rim-seat", rim_agreement_mm=0.07,
            seated_selection=SeatedSelection(
                model="neodent-gm",
                construction_path="dess/neodent-gm-scanbody.stl",
                variant=variant, jaw="upper", gingival_offset_mm=0.2))
    if choices_complete:
        s.choices = CaseChoices(construction_path="dess/neodent-gm-scanbody.stl",
                                jaw="upper", gingival_offset_mm=0.2)
    store.save(s)


def row(tooth: int, level: str = "ready") -> dict:
    """One summary site row in the demo's row shape (the keys the landing and the
    later Deliver read; the full key-set fidelity is worker test_run.py's pin)."""
    return {
        "tooth": tooth, "spec": "neodent-gm 5020", "vendor": "dess",
        "seat_method": "rim-seat", "seed_source": "site-center",
        "auto_delta_mm": None, "coverage": 0.91, "icp_fitness": 0.83,
        "fit": {"avg_mm": 0.21, "max_mm": 0.62, "n": 4200},
        "rim_agreement_mm": 0.07, "rim_arc_bins": 12, "rim_off_centre": 0.11,
        "border_click_disagreement_mm": None, "confidence": {"grade": "high"},
        "top_face_agreement_mm": 0.05, "cap_surface_explained_pct": 96.2,
        "clocking": {"evidence": "codes", "rotation_unverified": level != "ready"},
        "guidance": {"level": level, "actions": [] if level == "ready" else [
            "The cap's ROTATION could not be verified — visually check the coded "
            "features in view 1 (top-down) before accepting."]},
        "alignment_error_mm": 1.4,
        "variant": {"identified": "5020", "declared": "5020",
                    "measured_rim_diameter_mm": 4.73, "flags": [],
                    "candidates_too_close": False},
        "advisory": True,
        "production": {"screw_channel_radius_mm": 1.0, "gingival_offset_mm": 0.2,
                       "clamped": False},
        "deviation_rms_mm": 0.43, "deviation_p90_mm": 0.71,
        "site_measurement": {"md_span_mm": 8.1, "classification": "molar"},
    }


def summary_for(rows, files=("cap-4-aligned.stl", "cap-13-aligned.stl",
                             "view.html")) -> dict:
    return {"case_id": "neodent-gm", "jaw": "upper", "mode": "propose+confirm",
            "confirmed_sites": [{"tooth": r["tooth"], "center": [0, 0, 0]}
                                for r in rows],
            "gingival_relief": {"gingival_offset_requested_mm": 0.2,
                                "gingival_offset_applied_mm": 0.2, "clamped": False},
            "package_files": list(files),
            "sites": rows}


# --- the gate ----------------------------------------------------------------------

class TestTheAuthorizedGate:
    """AM-8: the full run fires only over a server-minted authorization — choices
    complete AND every site reviewed READY. The 422 names EACH missing piece: the
    operator fixes what is named, never guesses."""

    def test_a_fresh_session_is_refused_naming_only_what_is_actually_missing(
            self, settings):
        # the gate reads the EFFECTIVE choices (client 2026-07-27): this case's
        # suggestions + the standing relief default cover construction/jaw/relief,
        # so a fresh session is short ONLY of its reviews — the refusal names the
        # unreviewed teeth and nothing the fallbacks already supply
        worker = FakeWorker()
        client = client_with(settings, worker)
        res = client.post("/api/case-sessions/neodent-gm/run")
        assert res.status_code == 422
        detail = res.json()["detail"]
        assert "not authorized" in detail
        for piece in ("tooth 4", "tooth 13"):
            assert piece in detail, piece
        for covered in ("the construction part", "the jaw", "the gingival relief"):
            assert covered not in detail, covered
        # asking created nothing: no job submitted, no receipt persisted
        assert worker.submitted == []
        res = client.get("/api/case-sessions/neodent-gm/run")
        assert res.status_code == 404

    def test_one_unreviewed_site_is_named_with_its_actual_rung(
            self, settings, product_root):
        seed_ready(product_root, teeth=("4",))
        store = SessionStore(product_root)
        s = store.load("neodent-gm")
        s.sites["13"] = SiteSession(status=SiteStatus.PREVIEWED,
                                    declared_variant="5020")
        store.save(s)
        client = client_with(settings, FakeWorker())
        res = client.post("/api/case-sessions/neodent-gm/run")
        assert res.status_code == 422
        detail = res.json()["detail"]
        assert "tooth 13 reviewed over the panes (now 'previewed')" in detail
        assert "tooth 4" not in detail  # ready sites are not named as missing

    def test_a_drifted_effective_value_after_review_refuses_the_run(
            self, settings, product_root):
        """THE 2026-07-28 RULE, SHARPENED BY §10-AC/C (2026-08-04): the gate
        refuses drift in the POSE INPUTS — model, variant, jaw — because those are
        what the review's seat attested. Relief and the construction part are
        provably pose-independent (§10-M measured construction entering no
        alignment stage; §10-C: relief shapes only the EMITTED part), so their
        drift no longer refuses: the attested seat is bit-identical under them,
        and their changes have their own honest path (the §10-AC re-emit). Without
        this sharpening, #8's rung-preserving boundary wedged the next full run.

        Here: tooth 4's seat records a 0.15 relief against today's 0.20 —
        AUTHORIZES; tooth 13's seat records the wrong JAW — REFUSES, named."""
        seed_ready(product_root, choices_complete=False)
        store = SessionStore(product_root)
        s = store.load("neodent-gm")
        s.sites["4"].seated_selection = s.sites["4"].seated_selection.model_copy(
            update={"gingival_offset_mm": 0.15})
        store.save(s)
        worker = FakeWorker(summary=summary_for([row(4), row(13)]))
        client = client_with(settings, worker)
        res = client.post("/api/case-sessions/neodent-gm/run")
        assert res.status_code == 200, res.text   # relief drift seats identically

        # …but a POSE input drifting still refuses, naming the tooth
        s = store.load("neodent-gm")
        s.run = None
        s.sites["13"].seated_selection = s.sites["13"].seated_selection.model_copy(
            update={"jaw": "lower"})
        store.save(s)
        res = client.post("/api/case-sessions/neodent-gm/run")
        assert res.status_code == 422
        detail = res.json()["detail"]
        assert "tooth 13 re-previewed and re-reviewed" in detail
        assert "tooth 4" not in detail   # its pose inputs still match

    def test_a_ready_site_with_no_recorded_seat_is_refused(
            self, settings, product_root):
        # a document persisted before the seat record existed: READY with no
        # record cannot prove what its review attested — fail-closed, the gate
        # asks for one re-preview + re-review instead of trusting the rung
        store = SessionStore(product_root)
        s = store.load("neodent-gm")
        for tooth in ("4", "13"):
            s.sites[tooth] = SiteSession(status=SiteStatus.READY,
                                         declared_variant="5020",
                                         seat_method="rim-seat",
                                         rim_agreement_mm=0.07)
        store.save(s)
        worker = FakeWorker(summary=summary_for([row(4), row(13)]))
        client = client_with(settings, worker)
        res = client.post("/api/case-sessions/neodent-gm/run")
        assert res.status_code == 422
        detail = res.json()["detail"]
        for piece in ("tooth 4 re-previewed and re-reviewed",
                      "tooth 13 re-previewed and re-reviewed"):
            assert piece in detail, piece
        assert worker.submitted == []

    def test_a_case_with_no_sites_and_no_system_names_both(self, settings, data_root):
        # a scan folder matching no library name: a real case (the patient-4471
        # lesson) with no suggestion and nothing detected yet
        mystery = data_root / "scans/doctor-mystery"
        mystery.mkdir()
        (mystery / "upper_jaw.stl").touch()
        client = client_with(settings, FakeWorker())
        res = client.post("/api/case-sessions/mystery/run")
        assert res.status_code == 422
        detail = res.json()["detail"]
        assert "the implant system" in detail
        assert "at least one site" in detail
        # no suggestion exists here, so the effective construction is honestly
        # absent and the refusal still names it — fallbacks are facts, not guesses
        assert "the construction part" in detail


# --- the authorized run + landing --------------------------------------------------

class TestTheRunLands:
    def test_the_submit_is_job_shaped_with_the_sessions_own_selection(
            self, settings, product_root):
        seed_ready(product_root)
        worker = FakeWorker(summary=summary_for([row(4), row(13)]))
        client = client_with(settings, worker)
        res = client.post("/api/case-sessions/neodent-gm/run")
        assert res.status_code == 200
        ((case_id, request),) = worker.submitted
        assert case_id == "neodent-gm"
        assert request["run_id"]  # BFF-minted, non-empty — the immutable dir's name
        assert request["selection"] == {
            "model": "neodent-gm",
            "construction_path": "dess/neodent-gm-scanbody.stl",
            "jaw": "upper", "gingival_offset_mm": 0.2,
            "variants": {"4": "5020", "13": "5020"},
            # 2026-07-28: sites that exist because a HUMAN marked them. EMPTY
            # here on purpose — a detected site's centre still comes from the
            # case, and shipping a redundant copy would invite the two drifting
            # apart. The map carries the marked ones and nothing else.
            "marked_centers": {},
            # §10-B/C: per-site relief overrides ride beside the case value —
            # empty here: nobody overrode a site
            "site_reliefs": {},
            # §10-AD: the operator's persisted marks/pairs/best-fits ride the
            # selection so a re-run re-applies them — empty here: nobody adjusted
            "alignment_evidence": {},
        }

    def test_an_authorized_run_consumes_the_effective_choices(
            self, settings, product_root):
        # the client's 2026-07-27 automation ask, at the RUN: every site reviewed
        # but no choices PUT ever made — the run fires with the case's suggestions
        # and the standing 0.20mm relief default, the same values the detail's
        # effective views attribute
        seed_ready(product_root, choices_complete=False)
        worker = FakeWorker(summary=summary_for([row(4), row(13)]))
        client = client_with(settings, worker)
        res = client.post("/api/case-sessions/neodent-gm/run")
        assert res.status_code == 200
        ((_case_id, request),) = worker.submitted
        assert request["selection"] == {
            "model": "neodent-gm",
            "construction_path": "dess/neodent-gm-scanbody.stl",
            "jaw": "upper", "gingival_offset_mm": 0.2,
            "variants": {"4": "5020", "13": "5020"},
            # 2026-07-28: sites that exist because a HUMAN marked them. EMPTY
            # here on purpose — a detected site's centre still comes from the
            # case, and shipping a redundant copy would invite the two drifting
            # apart. The map carries the marked ones and nothing else.
            "marked_centers": {},
            # §10-B/C: per-site relief overrides ride beside the case value —
            # empty here: nobody overrode a site
            "site_reliefs": {},
            # §10-AD: the operator's persisted marks/pairs/best-fits ride the
            # selection so a re-run re-applies them — empty here: nobody adjusted
            "alignment_evidence": {},
        }

    def test_verdicts_land_on_the_ladder_ready_holds_attention_flags(
            self, settings, product_root):
        seed_ready(product_root)
        worker = FakeWorker(summary=summary_for([row(4, level="attention"),
                                                 row(13, level="ready")]))
        client = client_with(settings, worker)
        detail = client.post("/api/case-sessions/neodent-gm/run").json()
        by_tooth = {s["tooth"]: s["status"] for s in detail["sites"]}
        assert by_tooth[4] == "flagged"   # the flag event's first legitimate writer
        assert by_tooth[13] == "ready"    # a ready verdict never moves the rung
        assert detail["session"]["run_state"] == "done"
        # and the persisted truth agrees (a restart serves the same facts)
        persisted = SessionStore(product_root).load("neodent-gm")
        assert persisted.sites["4"].status is SiteStatus.FLAGGED
        assert persisted.sites["13"].status is SiteStatus.READY
        assert persisted.run is not None and persisted.run.state == "done"

    def test_the_run_facts_serve_from_get_run(self, settings, product_root):
        seed_ready(product_root)
        rows = [row(4, level="attention"), row(13)]
        worker = FakeWorker(summary=summary_for(rows))
        client = client_with(settings, worker)
        client.post("/api/case-sessions/neodent-gm/run")
        res = client.get("/api/case-sessions/neodent-gm/run")
        assert res.status_code == 200
        facts = res.json()
        assert facts["state"] == "done"
        assert facts["refusal"] is None
        assert facts["run_id"]
        # per-site rows verbatim — Adjust's and Deliver's read surface
        assert [r["tooth"] for r in facts["sites"]] == [4, 13]
        assert facts["sites"][0]["guidance"]["level"] == "attention"
        # package files as names RELATIVE to the run dir — the payloads stay on disk
        assert facts["package_files"] == ["cap-4-aligned.stl", "cap-13-aligned.stl",
                                          "view.html"]
        assert all("/" not in name for name in facts["package_files"])

    def test_the_worklist_row_mirrors_done(self, settings, product_root):
        seed_ready(product_root)
        client = client_with(settings, FakeWorker(summary=summary_for([row(4)])))
        client.post("/api/case-sessions/neodent-gm/run")
        (row_,) = client.get("/api/case-sessions").json()
        assert row_["run_state"] == "done"

    def test_session_json_stays_small_with_a_six_site_summary(
            self, settings, product_root):
        """The mesh-heavy payloads stay on disk in the run dir; the session holds
        FACTS. Six sites (a full-arch morning's worst case) must keep session.json
        well under 32KB — the size a rehydrating BFF re-reads per request."""
        seed_ready(product_root, teeth=tuple(str(t) for t in (4, 8, 13, 19, 25, 30)))
        rows = [row(t) for t in (4, 8, 13, 19, 25, 30)]
        client = client_with(settings, FakeWorker(summary=summary_for(rows)))
        assert client.post("/api/case-sessions/neodent-gm/run").status_code == 200
        session_file = product_root / "neodent-gm" / "session.json"
        assert session_file.stat().st_size < 32_768

    def test_a_second_authorized_run_mints_a_new_run_id(self, settings, product_root):
        seed_ready(product_root)
        worker = FakeWorker(summary=summary_for([row(4), row(13)]))
        client = client_with(settings, worker)
        client.post("/api/case-sessions/neodent-gm/run")
        client.post("/api/case-sessions/neodent-gm/run")
        (_, first), (_, second) = worker.submitted
        assert first["run_id"] != second["run_id"]  # AM-1: a re-run is a NEW directory


class TestRefusedRuns:
    def test_the_pipelines_words_land_verbatim_and_sites_stand(
            self, settings, product_root):
        seed_ready(product_root)
        words = ("package NOT emitted: the 0.20mm gingival relief the lab asked for "
                 "is NOT safe on this pair — re-run with a smaller gingival offset")
        client = client_with(settings, FakeWorker(refusal=words))
        detail = client.post("/api/case-sessions/neodent-gm/run").json()
        assert detail["session"]["run_state"] == "refused"
        assert detail["session"]["run_refusal"] == words
        # a refusal is evidence about the RUN, not about any single site's review
        assert all(s["status"] == "ready" for s in detail["sites"])
        facts = client.get("/api/case-sessions/neodent-gm/run").json()
        assert facts["state"] == "refused"
        assert facts["refusal"] == words
        assert facts["sites"] == [] and facts["package_files"] == []
        (row_,) = client.get("/api/case-sessions").json()
        assert row_["run_state"] == "refused"

    def test_a_refused_run_can_be_retried_explicitly(self, settings, product_root):
        seed_ready(product_root)
        worker = FakeWorker(refusal="no confirmed site could be aligned")
        client = client_with(settings, worker)
        client.post("/api/case-sessions/neodent-gm/run")
        worker.refusal, worker.summary = None, summary_for([row(4), row(13)])
        detail = client.post("/api/case-sessions/neodent-gm/run").json()
        assert detail["session"]["run_state"] == "done"
        assert detail["session"]["run_refusal"] is None


class TestMidRunRivals:
    """25604e7's rule at run scale: the receipt persists INSIDE a mutation, and the
    landing refuses when the case moved underneath the multi-second physics."""

    def test_a_run_already_in_flight_refuses_a_second_post(
            self, settings, product_root):
        seed_ready(product_root)
        store = SessionStore(product_root)
        s = store.load("neodent-gm")
        from bff.session import RunSession
        s.run = RunSession(job_id="job-1", run_id="job-1", state="running")
        store.save(s)
        worker = FakeWorker(summary=summary_for([row(4)]))
        client = client_with(settings, worker)
        res = client.post("/api/case-sessions/neodent-gm/run")
        assert res.status_code == 409
        assert "already in flight" in res.json()["detail"]
        assert worker.submitted == []

    def test_a_rival_declaration_mid_run_makes_the_landing_a_409(
            self, settings, product_root):
        seed_ready(product_root)

        def rival(case_id, request):
            # a re-declaration lands while the physics runs: the reset boundary
            # clears the current-run pointer, so these results describe a part no
            # longer declared and must never land
            rival_store = SessionStore(settings.product_root)
            s = rival_store.load(case_id)
            s.sites["4"].status = SiteStatus.DECLARED
            s.sites["4"].declared_variant = "5030"
            s.run = None
            rival_store.save(s)

        client = client_with(settings, FakeWorker(
            summary=summary_for([row(4), row(13)]), on_submit=rival))
        res = client.post("/api/case-sessions/neodent-gm/run")
        assert res.status_code == 409
        assert "changed while the run was computing" in res.json()["detail"]
        # the rival's acts stand; no run receipt claims to be current
        persisted = SessionStore(settings.product_root).load("neodent-gm")
        assert persisted.run is None
        assert persisted.sites["4"].declared_variant == "5030"


class TestCrashesAreNotWedges:
    """The 5c crash-path fix (the verification refuted claim 2 on exactly this):
    when NO verdict can land — the adapter reports FAILED (a crash inside the
    physics), ``submit`` itself raises (the run-dir collision), or the landing
    loses its CAS race twice — the queued receipt must be WITHDRAWN, not
    abandoned. An abandoned ``queued`` receipt wedges the case forever: every
    later POST 409s ("a run is already in flight") and no reset boundary is
    obliged to fire. A crash is a 500 (an error), NOT a refusal (a first-class
    outcome in the pipeline's own words) and NOT a landed run state."""

    def test_a_worker_crash_is_a_500_and_the_receipt_is_withdrawn(
            self, settings, product_root):
        seed_ready(product_root)
        worker = FakeWorker(error="IndexError: index 7 is out of bounds")
        client = client_with(settings, worker)
        res = client.post("/api/case-sessions/neodent-gm/run")
        assert res.status_code == 500
        detail = res.json()["detail"]
        assert "crashed" in detail
        assert "IndexError: index 7 is out of bounds" in detail
        # withdrawn: nothing claims to be current, nothing is wedged "queued"
        assert SessionStore(product_root).load("neodent-gm").run is None
        assert client.get("/api/case-sessions/neodent-gm/run").status_code == 404
        # a crash is evidence about the infrastructure, not about any site's review
        detail = client.get("/api/case-sessions/neodent-gm").json()
        assert all(s["status"] == "ready" for s in detail["sites"])
        assert detail["session"]["run_state"] == "none"

    def test_after_a_crash_a_retry_can_run_and_land(self, settings, product_root):
        seed_ready(product_root)
        worker = FakeWorker(error="RuntimeError: boom")
        client = client_with(settings, worker)
        assert client.post("/api/case-sessions/neodent-gm/run").status_code == 500
        worker.error, worker.summary = None, summary_for([row(4), row(13)])
        detail = client.post("/api/case-sessions/neodent-gm/run").json()
        assert detail["session"]["run_state"] == "done"
        assert detail["session"]["run_refusal"] is None

    def test_a_submit_that_raises_withdraws_the_receipt_too(
            self, settings, product_root):
        """The collision ``FileExistsError`` (or any adapter bug) raised from
        ``submit`` AFTER the receipt persisted: the 500 must not strand it."""
        seed_ready(product_root)

        def exploding(case_id, request):
            raise FileExistsError("run directory already exists — immutable (AM-1)")

        worker = FakeWorker(on_submit=exploding)
        client = TestClient(create_app(settings), raise_server_exceptions=False)
        client.app.state.worker = worker
        assert client.post("/api/case-sessions/neodent-gm/run").status_code == 500
        assert SessionStore(product_root).load("neodent-gm").run is None
        # unwedged: the same case can immediately authorize a fresh run
        worker.on_submit, worker.summary = None, summary_for([row(4), row(13)])
        detail = client.post("/api/case-sessions/neodent-gm/run").json()
        assert detail["session"]["run_state"] == "done"

    def test_a_landing_that_loses_the_cas_twice_withdraws_the_receipt(
            self, settings, product_root):
        """The verification's second wedge class: rival (non-boundary) version
        bumps land between the landing's load and save on BOTH attempts, so the
        landing 409s — without the withdrawal, the queued receipt would sit
        forever on a case whose physics actually finished."""
        seed_ready(product_root)
        worker = FakeWorker(summary=summary_for([row(4), row(13)]))
        client = client_with(settings, worker)
        store = client.app.state.sessions
        original_save = store.save
        rivals = {"left": 2}

        def contended_save(session):
            # interleave a rival bump under the LANDING's save only (it carries
            # state "done"); the claim ("queued") and the withdrawal (run=None)
            # pass through untouched
            if (rivals["left"] > 0 and session.run is not None
                    and session.run.state == "done"):
                rivals["left"] -= 1
                rival = SessionStore(product_root)
                rival.save(rival.load("neodent-gm"))
            return original_save(session)

        store.save = contended_save
        res = client.post("/api/case-sessions/neodent-gm/run")
        assert res.status_code == 409
        # withdrawn, not wedged: no current run, and a re-POST is authorized
        assert SessionStore(product_root).load("neodent-gm").run is None
        store.save = original_save
        detail = client.post("/api/case-sessions/neodent-gm/run").json()
        assert detail["session"]["run_state"] == "done"


# --- reset boundaries --------------------------------------------------------------

class TestRunResetBoundaries:
    """A stale run can never masquerade as current: any post-run system/declaration/
    choices CHANGE clears the session's current-run pointer (the run directory is
    immutable history on disk) and the statuses regress per the stated boundaries.
    IDENTICAL re-writes clear nothing — the 5a/5b equality guards hold here too."""

    def _landed_client(self, settings, product_root,
                       levels=("attention", "ready")) -> TestClient:
        seed_ready(product_root)
        client = client_with(settings, FakeWorker(summary=summary_for(
            [row(4, level=levels[0]), row(13, level=levels[1])])))
        assert client.post("/api/case-sessions/neodent-gm/run").status_code == 200
        return client

    def test_a_re_declaration_clears_the_run_and_regresses_its_site(
            self, settings, product_root, data_root):
        (data_root / "library/caps/neodent-gm/neodent-gm-5030.stl").touch()
        client = self._landed_client(settings, product_root)
        # 5020 -> 5020 is a re-declaration of the same variant: nothing changes,
        # the run stays current (the 5a equality guard)
        detail = client.put("/api/case-sessions/neodent-gm/sites/13/declaration",
                            json={"variant": "5020"}).json()
        assert detail["session"]["run_state"] == "done"
        # a DIFFERENT variant on the flagged site: the declaration boundary — the
        # current-run pointer clears, the site regresses, the OTHER site's review
        # stands (the boundary is per its stated scope, not a case-wide sweep)
        detail = client.put("/api/case-sessions/neodent-gm/sites/4/declaration",
                            json={"variant": "5030"}).json()
        assert detail["session"]["run_state"] == "none"
        by_tooth = {s["tooth"]: s for s in detail["sites"]}
        assert by_tooth[4]["status"] == "declared"
        assert by_tooth[4]["declared_variant"] == "5030"
        assert by_tooth[13]["status"] == "ready"
        assert client.get("/api/case-sessions/neodent-gm/run").status_code == 404

    def test_a_choices_change_clears_the_run_and_regresses_sites(
            self, settings, product_root):
        client = self._landed_client(settings, product_root)
        detail = client.put("/api/case-sessions/neodent-gm/choices",
                            json={"construction_path": "dess/neodent-gm-scanbody.stl",
                                  "jaw": "lower",
                                  "gingival_offset_mm": 0.2}).json()
        assert detail["session"]["run_state"] == "none"
        # later rungs (ready, flagged) regress to declared per invalidate_preview
        assert all(s["status"] == "declared" for s in detail["sites"])
        assert client.get("/api/case-sessions/neodent-gm/run").status_code == 404

    def test_an_identical_choices_re_put_clears_nothing(self, settings, product_root):
        client = self._landed_client(settings, product_root)
        detail = client.put("/api/case-sessions/neodent-gm/choices",
                            json={"construction_path": "dess/neodent-gm-scanbody.stl",
                                  "jaw": "upper",
                                  "gingival_offset_mm": 0.2}).json()
        assert detail["session"]["run_state"] == "done"
        assert {s["tooth"]: s["status"] for s in detail["sites"]} == {
            4: "flagged", 13: "ready"}

    def test_a_system_switch_clears_the_run_and_resets_every_site(
            self, settings, product_root, data_root):
        (data_root / "library/caps/straumann-bl").mkdir(parents=True)
        (data_root / "library/caps/straumann-bl/straumann-bl-4020.stl").touch()
        client = self._landed_client(settings, product_root)
        detail = client.put("/api/case-sessions/neodent-gm/system",
                            json={"model": "straumann-bl"}).json()
        assert detail["session"]["run_state"] == "none"
        assert all(s["status"] == "detected" for s in detail["sites"])
        assert client.get("/api/case-sessions/neodent-gm/run").status_code == 404

    def test_the_pinning_same_system_put_clears_nothing(self, settings, product_root):
        client = self._landed_client(settings, product_root)
        detail = client.put("/api/case-sessions/neodent-gm/system",
                            json={"model": "neodent-gm"}).json()
        assert detail["session"]["run_state"] == "done"


class TestGetRunRefusals:
    def test_no_run_yet_is_a_404_with_words(self, settings):
        client = client_with(settings, FakeWorker())
        res = client.get("/api/case-sessions/neodent-gm/run")
        assert res.status_code == 404
        assert "no current run" in res.json()["detail"]

    def test_an_unknown_case_is_a_404(self, settings):
        client = client_with(settings, FakeWorker())
        assert client.get("/api/case-sessions/nope/run").status_code == 404
