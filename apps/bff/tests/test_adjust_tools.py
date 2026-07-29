"""THE FOUR ADJUST TOOLS' ENDPOINTS (plan §4 Adjust, §5; slice 6) — the rework surface.

``POST .../sites/{tooth}/{rotation|mark-trench|fit-by-points|best-fit}`` plus the read
the panes open on, ``GET .../sites/{tooth}/seated``.

The PHYSICS is pinned worker-side (apps/worker/tests/test_adjust.py — the gates, the
span maths, the refusal sentences, against a real shipped run). What these tests own is
everything the BFF actually decides:

  - THE PRECONDITION — a tool needs a verdict to rework, and the refusal names which of
    the three things is missing;
  - THE INPUT CORPUS — ``extra="forbid"``, the ±45° step, the ≤8 pairs cap, length-3 +
    finiteness on every coordinate, copied verbatim from the frozen models;
  - THE LANDING — the ladder move (``status.adjust``, its first legitimate writer), the
    summary row's folded reading, the newly emitted files joining the package list, the
    stage marked visited, and THE EVIDENCE BOUNDARY: a confirmed case whose fits moved
    is not confirmed any more;
  - THE REFUSAL SPLIT — 422 for a malformed ask, 409 for a gate, and the already-optimal
    PASS carrying its widen numbers; a refusal writes nothing at all.

The application layer is a seam here, stubbed like ``detect`` and ``preview_site`` are
in test_case_sessions: the fixture tree's STLs are empty on purpose (these tests stay
milliseconds) and no mesh may be parsed to prove a status transition.
"""
from __future__ import annotations

import pytest

from bff.config import Settings
from bff.resources import adjust as adjust_resource
from bff.session import SessionStore, SiteStatus
from case_prep.application.adjust import (AdjustInvalid, AdjustOutcome, AdjustRefused,
                                          AlreadyOptimal)

from conftest import make_data_tree
from test_assurance import PACKAGE_FILES, landed_client
from test_run_resource import row


CASE = "neodent-gm"
BASE = f"/api/case-sessions/{CASE}/sites"


@pytest.fixture
def product_root(tmp_path):
    return tmp_path / "product"


@pytest.fixture
def data_root(tmp_path):
    return make_data_tree(tmp_path / "data")


@pytest.fixture
def settings(data_root, product_root) -> Settings:
    return Settings(data_root=data_root, product_root=product_root)


def outcome(tooth: int = 4, operation: str = "rotation", applied: bool = True,
            **overrides) -> AdjustOutcome:
    """An application outcome in the shape the real tools return."""
    values = dict(
        tooth=tooth, operation=operation, detail="rotated +1.0° about the part axis",
        applied=applied,
        files=[f"{CASE}-{tooth}-healingcap-aligned.stl",
               f"{CASE}-{tooth}-implant.json",
               f"{CASE}-{tooth}-alignment-proof.png"],
        clocking={"notch_shift_deg": -1.0, "notch_corr": 0.51,
                  "notch_prominence": 0.16},
        nudge={"operator_delta_deg": 1.0, "cumulative_deg": 1.0},
        applied_delta_deg=1.0, cumulative_deg=1.0, stability_excess_mm=0.002,
        pane_payload={"tooth": tooth, "preview": False})
    values.update(overrides)
    return AdjustOutcome(**values)


def stub_tools(monkeypatch, result=None, raises=None):
    """Replace all four application tools with one recorded double."""
    calls = []

    def stub(case, run_dir, tooth, *args, **kwargs):
        calls.append({"case": case.id, "run_dir": run_dir, "tooth": tooth,
                      "args": args, "kwargs": kwargs})
        if raises is not None:
            raise raises
        return result if result is not None else outcome(tooth)

    for name in ("rotate_site", "align_to_mark", "align_to_correspondence",
                 "best_fit_site"):
        monkeypatch.setattr(adjust_resource, name, stub)
    return calls


def tooled(settings, product_root, monkeypatch, rows=None, result=None, raises=None):
    """A client whose case has a DONE current run, with the tools stubbed."""
    rows = rows if rows is not None else [row(4, level="attention"), row(13)]
    client = landed_client(settings, product_root, rows, files=PACKAGE_FILES)
    return client, stub_tools(monkeypatch, result=result, raises=raises)


def site_status(product_root, tooth: int) -> str:
    return SessionStore(product_root).load(CASE).sites[str(tooth)].status.value


# --- the precondition ---------------------------------------------------------------------

class TestATOOLNeedsAVerdictToRework:
    def test_an_unknown_case_is_a_404(self, settings, monkeypatch):
        client, _ = tooled(settings, settings.product_root, monkeypatch)
        res = client.post("/api/case-sessions/nope/sites/4/rotation",
                          json={"step_deg": 1.0})
        assert res.status_code == 404

    def test_a_tooth_the_case_does_not_have_is_a_404(self, settings, product_root,
                                                     monkeypatch):
        client, calls = tooled(settings, product_root, monkeypatch)
        res = client.post(f"{BASE}/99/rotation", json={"step_deg": 1.0})
        assert res.status_code == 404
        assert calls == [], "no physics may run for a site that does not exist"

    def test_no_completed_run_refuses_naming_that(self, settings, product_root,
                                                  monkeypatch):
        from test_run_resource import FakeWorker, client_with
        stub_tools(monkeypatch)
        client = client_with(settings, FakeWorker())
        res = client.post(f"{BASE}/4/rotation", json={"step_deg": 1.0})
        assert res.status_code == 422
        assert "no completed current run" in res.json()["detail"]

    def test_a_tooth_the_run_never_aligned_refuses_naming_that(
            self, settings, product_root, monkeypatch):
        # the run's summary carries tooth 13 only; tooth 4 is a site of the case
        client, calls = tooled(settings, product_root, monkeypatch, rows=[row(13)])
        res = client.post(f"{BASE}/4/rotation", json={"step_deg": 1.0})
        assert res.status_code == 422
        assert "carries no verdict from the current run" in res.json()["detail"]
        assert "meaningless" in res.json()["detail"]
        assert calls == []

    def test_a_site_still_climbing_has_no_fit_to_rework(self, settings, product_root,
                                                        monkeypatch):
        client, calls = tooled(settings, product_root, monkeypatch)
        store = SessionStore(product_root)
        session = store.load(CASE)
        session.sites["4"].status = SiteStatus.DECLARED
        store.save(session)
        res = client.post(f"{BASE}/4/rotation", json={"step_deg": 1.0})
        assert res.status_code == 422
        assert "still climbing to a verdict" in res.json()["detail"]
        assert calls == []


# --- the input corpus ----------------------------------------------------------------------

class TestTheValidationCorpus:
    def test_a_step_past_forty_five_degrees_is_refused_in_the_demos_words(
            self, settings, product_root, monkeypatch):
        client, calls = tooled(settings, product_root, monkeypatch)
        res = client.post(f"{BASE}/4/rotation", json={"step_deg": 46.0})
        assert res.status_code == 422
        assert "±45°" in res.text
        assert calls == []

    def test_an_unknown_field_is_refused_not_dropped(self, settings, product_root,
                                                     monkeypatch):
        client, _ = tooled(settings, product_root, monkeypatch)
        res = client.post(f"{BASE}/4/rotation",
                          json={"step_deg": 1.0, "status": "ready"})
        assert res.status_code == 422

    def test_a_two_coordinate_mark_is_refused(self, settings, product_root,
                                             monkeypatch):
        client, _ = tooled(settings, product_root, monkeypatch)
        res = client.post(f"{BASE}/4/mark-trench", json={"scan_point": [1.0, 2.0]})
        assert res.status_code == 422
        assert "[x, y, z] triple" in res.text

    def test_a_non_finite_coordinate_is_refused_and_the_refusal_serializes(
            self, settings, product_root, monkeypatch):
        """The corpus' promised EXTENSION plus main.py's non-finite-safe handler: a
        refusal about NaN must never crash into a 500 while echoing NaN back."""
        client, _ = tooled(settings, product_root, monkeypatch)
        # raw content: a JSON encoder that refuses NaN cannot even build this request,
        # which is the point — a hostile client is not using our encoder
        res = client.post(f"{BASE}/4/mark-trench",
                          content='{"scan_point": [1.0, 2.0, NaN]}',
                          headers={"content-type": "application/json"})
        assert res.status_code == 422
        assert "finite numbers" in res.text

    def test_nine_pairs_are_refused_in_the_demos_words(self, settings, product_root,
                                                       monkeypatch):
        client, calls = tooled(settings, product_root, monkeypatch)
        pairs = [{"feature_id": f"t-{i}", "scan_point": [0.0, 0.0, 0.0]}
                 for i in range(9)]
        res = client.post(f"{BASE}/4/fit-by-points", json={"pairs": pairs})
        assert res.status_code == 422
        assert "capped at 8 pairs" in res.text
        assert calls == []

    def test_a_pair_needs_exactly_one_part_half(self, settings, product_root,
                                                monkeypatch):
        client, _ = tooled(settings, product_root, monkeypatch)
        both = {"feature_id": "trench-01", "part_point": [1.0, 0.0, 1.0],
                "scan_point": [0.0, 0.0, 0.0]}
        assert client.post(f"{BASE}/4/fit-by-points",
                           json={"pairs": [both]}).status_code == 422
        neither = {"scan_point": [0.0, 0.0, 0.0]}
        assert client.post(f"{BASE}/4/fit-by-points",
                           json={"pairs": [neither]}).status_code == 422

    def test_a_diameter_outside_the_operator_band_is_refused(self, settings,
                                                             product_root, monkeypatch):
        client, calls = tooled(settings, product_root, monkeypatch)
        res = client.post(f"{BASE}/4/best-fit", json={"matching_diameter_mm": 2.5})
        assert res.status_code == 422
        assert "between 0.05 and 2.0mm" in res.text
        assert calls == []

    def test_a_span_reaches_the_application_with_both_ends(self, settings, product_root,
                                                           monkeypatch):
        """THE SPAN'S WIRE FORM (plan §5): a second scan point on the same pair, passed
        through as the application's own Correspondence — the BFF adds no geometry."""
        client, calls = tooled(settings, product_root, monkeypatch)
        res = client.post(f"{BASE}/4/fit-by-points", json={"pairs": [{
            "part_point": [1.5, 0.0, 1.0],
            "scan_point": [1.0, 0.0, 0.0],
            "scan_point_end": [2.0, 0.0, 0.0]}]})
        assert res.status_code == 200
        (pair,) = calls[0]["args"][0]
        assert pair.scan_point == [1.0, 0.0, 0.0]
        assert pair.scan_point_end == [2.0, 0.0, 0.0]
        assert pair.is_span is True


# --- the landing -----------------------------------------------------------------------------

class TestTheLanding:
    def test_an_applied_tool_moves_the_site_through_the_ladder(
            self, settings, product_root, monkeypatch):
        client, _ = tooled(settings, product_root, monkeypatch)
        assert site_status(product_root, 4) == "flagged"
        res = client.post(f"{BASE}/4/rotation", json={"step_deg": 1.0})
        assert res.status_code == 200
        assert site_status(product_root, 4) == "adjusted"
        assert res.json()["case"]["sites"][0]["status"] == "adjusted"

    def test_a_clean_site_may_be_reworked_and_its_review_falls_with_the_pose(
            self, settings, product_root, monkeypatch):
        """The queue lists clean sites too, visibly optional — and a tool that lands on
        one drops READY: the attestation stood on a pose that has moved."""
        client, _ = tooled(settings, product_root, monkeypatch)
        assert site_status(product_root, 13) == "ready"
        assert client.post(f"{BASE}/13/rotation",
                           json={"step_deg": 1.0}).status_code == 200
        assert site_status(product_root, 13) == "adjusted"

    def test_a_second_tool_on_an_adjusted_site_is_legal(self, settings, product_root,
                                                        monkeypatch):
        client, _ = tooled(settings, product_root, monkeypatch)
        client.post(f"{BASE}/4/rotation", json={"step_deg": 1.0})
        assert client.post(f"{BASE}/4/best-fit",
                           json={"matching_diameter_mm": 0.3}).status_code == 200
        assert site_status(product_root, 4) == "adjusted"

    def test_the_new_reading_is_folded_into_the_runs_summary_row(
            self, settings, product_root, monkeypatch):
        client, _ = tooled(settings, product_root, monkeypatch)
        client.post(f"{BASE}/4/rotation", json={"step_deg": 1.0})
        run = client.get(f"/api/case-sessions/{CASE}/run").json()
        row4 = next(r for r in run["sites"] if r["tooth"] == 4)
        assert row4["clocking"]["notch_shift_deg"] == -1.0
        # the run's own words survive the fold — only the instrument fields change
        assert row4["clocking"]["evidence"] == "codes"
        assert row4["nudge"] == {"operator_delta_deg": 1.0, "cumulative_deg": 1.0}

    def test_the_alignment_proof_joins_the_runs_package_files(
            self, settings, product_root, monkeypatch):
        """The proof exists only for sites a human moved — and it is EVIDENCE, so it
        must be in what the run claims or the operator can never see it."""
        client, _ = tooled(settings, product_root, monkeypatch)
        client.post(f"{BASE}/4/rotation", json={"step_deg": 1.0})
        files = client.get(f"/api/case-sessions/{CASE}/run").json()["package_files"]
        assert f"{CASE}-4-alignment-proof.png" in files
        # already-listed files are not duplicated by the rewrite
        assert files.count(f"{CASE}-4-healingcap-aligned.stl") == 1

    def test_a_best_fit_never_overwrites_the_sites_rotation_bookkeeping(
            self, settings, product_root, monkeypatch):
        """server.py's 2026-07-25 rule, kept: a 6-DoF move is not a clock nudge and
        must not claim a cumulative rotation it did not apply."""
        client, calls = tooled(settings, product_root, monkeypatch)
        client.post(f"{BASE}/4/rotation", json={"step_deg": 1.0})
        stub_tools(monkeypatch, result=outcome(
            4, operation="best-fit", nudge={"operator_delta_deg": 1.0,
                                            "cumulative_deg": 1.0},
            best_fit={"roi_mean_before_mm": 0.21, "roi_mean_after_mm": 0.19},
            applied_delta_deg=None, cumulative_deg=None))
        client.post(f"{BASE}/4/best-fit", json={"matching_diameter_mm": 0.3})
        row4 = next(r for r in client.get(f"/api/case-sessions/{CASE}/run").json()["sites"]
                    if r["tooth"] == 4)
        assert row4["nudge"] == {"operator_delta_deg": 1.0, "cumulative_deg": 1.0}
        assert row4["best_fit"]["roi_mean_after_mm"] == 0.19

    def test_the_stage_is_marked_visited_by_the_act_not_by_a_client(
            self, settings, product_root, monkeypatch):
        client, _ = tooled(settings, product_root, monkeypatch)
        assert client.get(f"/api/case-sessions/{CASE}").json(
        )["session"]["adjust_visited"] is False
        client.post(f"{BASE}/4/rotation", json={"step_deg": 1.0})
        assert client.get(f"/api/case-sessions/{CASE}").json(
        )["session"]["adjust_visited"] is True

    def test_the_tool_gets_the_runs_own_directory(self, settings, product_root,
                                                  monkeypatch):
        client, calls = tooled(settings, product_root, monkeypatch)
        client.post(f"{BASE}/4/rotation", json={"step_deg": 1.0})
        run_id = client.get(f"/api/case-sessions/{CASE}/run").json()["run_id"]
        assert calls[0]["run_dir"] == product_root / CASE / "runs" / run_id


# --- the evidence boundary ---------------------------------------------------------------

class TestAnAdjustmentRetiresTheConfirmation:
    def _confirmed(self, client):
        assert client.post(f"/api/case-sessions/{CASE}/confirm", json={
            "acknowledged_flags": [4]}).status_code == 200
        assert client.post(f"/api/case-sessions/{CASE}/payment",
                           json={"authorize": True}).status_code == 200
        assert client.post(f"/api/case-sessions/{CASE}/release").status_code == 200

    def test_a_confirmed_case_whose_fits_moved_is_not_confirmed_any_more(
            self, settings, product_root, monkeypatch):
        client, _ = tooled(settings, product_root, monkeypatch)
        self._confirmed(client)
        before = client.get(f"/api/case-sessions/{CASE}").json()["session"]
        assert before["confirmed"] is True and before["released"] is True

        res = client.post(f"{BASE}/4/rotation", json={"step_deg": 1.0})
        assert res.status_code == 200
        after = res.json()["case"]["session"]
        assert after["confirmed"] is False
        assert after["released"] is False
        assert after["confirmation"] is None
        assert after["release"] is None

    def test_the_payment_survives_because_money_is_not_evidence(
            self, settings, product_root, monkeypatch):
        client, _ = tooled(settings, product_root, monkeypatch)
        self._confirmed(client)
        res = client.post(f"{BASE}/4/rotation", json={"step_deg": 1.0})
        assert res.json()["case"]["session"]["payment_authorized"] is True

    def test_artifacts_stop_disclosing_the_moment_a_fit_moves(
            self, settings, product_root, monkeypatch):
        client, _ = tooled(settings, product_root, monkeypatch)
        self._confirmed(client)
        assert client.get(
            f"/api/case-sessions/{CASE}/runs/current/artifacts").status_code == 200
        client.post(f"{BASE}/4/rotation", json={"step_deg": 1.0})
        res = client.get(f"/api/case-sessions/{CASE}/runs/current/artifacts")
        assert res.status_code == 409
        assert "no release record covers the current run" in res.json()["detail"]


# --- the refusal split -----------------------------------------------------------------------

class TestRefusalsChangeNothing:
    def test_a_gate_refusal_is_a_409_in_the_gates_own_words(
            self, settings, product_root, monkeypatch):
        client, _ = tooled(settings, product_root, monkeypatch, raises=AdjustRefused(
            "ring-fixed stability excess 0.51mm exceeds the 0.35mm certification "
            "bound — the rim cannot hold this rotation still"))
        res = client.post(f"{BASE}/4/rotation", json={"step_deg": 30.0})
        assert res.status_code == 409
        assert res.json()["detail"].startswith("ring-fixed stability excess 0.51mm")
        assert site_status(product_root, 4) == "flagged", "a refusal moves nothing"

    def test_a_validation_refusal_from_the_application_is_a_422(
            self, settings, product_root, monkeypatch):
        client, _ = tooled(settings, product_root, monkeypatch, raises=AdjustInvalid(
            "the mark is 41.2mm from tooth 4's seated cap — click the coded trench on "
            "the cap itself (within 15mm)"))
        res = client.post(f"{BASE}/4/mark-trench", json={"scan_point": [9.0, 9.0, 9.0]})
        assert res.status_code == 422
        assert "click the coded trench on the cap itself" in res.json()["detail"]

    def test_a_refused_tool_leaves_a_confirmation_standing(
            self, settings, product_root, monkeypatch):
        """A refusal changes NOTHING — including the evidence boundary. Retiring a
        confirmation over an adjustment that never happened would be a second bug
        wearing the first one's clothes."""
        client, _ = tooled(settings, product_root, monkeypatch)
        assert client.post(f"/api/case-sessions/{CASE}/confirm",
                           json={"acknowledged_flags": [4]}).status_code == 200
        stub_tools(monkeypatch, raises=AdjustRefused("the rim band would leave the scan"))
        assert client.post(f"{BASE}/4/rotation",
                           json={"step_deg": 30.0}).status_code == 409
        assert client.get(f"/api/case-sessions/{CASE}").json(
        )["session"]["confirmed"] is True

    def test_the_already_optimal_pass_arrives_with_its_widen(
            self, settings, product_root, monkeypatch):
        """The one refusal that is really a confirmation (client ask 2026-07-26): the
        surface renders it GREEN, so the wire must carry more than a sentence."""
        client, _ = tooled(settings, product_root, monkeypatch, raises=AlreadyOptimal(
            "the certified pose is already the best fit within this matching diameter "
            "— nothing to correct at Ø0.30mm; widen to search further",
            matching_diameter_mm=0.3, suggested_diameter_mm=0.6))
        res = client.post(f"{BASE}/4/best-fit", json={"matching_diameter_mm": 0.3})
        assert res.status_code == 409
        detail = res.json()["detail"]
        assert detail["kind"] == "already_optimal"
        assert detail["matching_diameter_mm"] == 0.3
        assert detail["suggested_diameter_mm"] == 0.6
        assert "already the best fit" in detail["message"]

    def test_at_the_ceiling_the_widen_caps_to_the_dial_itself(
            self, settings, product_root, monkeypatch):
        client, _ = tooled(settings, product_root, monkeypatch, raises=AlreadyOptimal(
            "…and this is the widest matching band the tool searches",
            matching_diameter_mm=2.0, suggested_diameter_mm=2.0))
        detail = client.post(f"{BASE}/4/best-fit",
                             json={"matching_diameter_mm": 2.0}).json()["detail"]
        assert detail["suggested_diameter_mm"] == detail["matching_diameter_mm"]


class TestMeasureOnlyLandsNothing:
    def test_a_measured_best_fit_moves_no_rung_and_seals_nothing(
            self, settings, product_root, monkeypatch):
        client, _ = tooled(settings, product_root, monkeypatch, result=outcome(
            4, operation="best-fit", applied=False, files=[], clocking=None,
            nudge=None, applied_delta_deg=None, cumulative_deg=None,
            stability_excess_mm=None, pane_payload=None,
            best_fit={"roi_mean_before_mm": 0.21, "roi_mean_after_mm": 0.19}))
        assert client.post(f"/api/case-sessions/{CASE}/confirm",
                           json={"acknowledged_flags": [4]}).status_code == 200
        res = client.post(f"{BASE}/4/best-fit",
                          json={"matching_diameter_mm": 0.3, "apply": False})
        assert res.status_code == 200
        body = res.json()
        assert body["outcome"]["applied"] is False
        assert body["pane_payload"] is None
        assert body["outcome"]["best_fit"]["roi_mean_after_mm"] == 0.19
        assert site_status(product_root, 4) == "flagged"
        assert body["case"]["session"]["confirmed"] is True


# --- the read the panes open on --------------------------------------------------------------

class TestSeatedRead:
    def test_it_serves_the_shipped_poses_own_payload(self, settings, product_root,
                                                     monkeypatch):
        payload = {"tooth": 4, "preview": False, "points": [], "faces": []}
        monkeypatch.setattr(adjust_resource, "seated_payload",
                            lambda case, run_dir, tooth: payload)
        client, _ = tooled(settings, product_root, monkeypatch)
        res = client.get(f"{BASE}/4/seated")
        assert res.status_code == 200
        assert res.json() == payload

    def test_it_stands_on_the_same_precondition_as_the_tools(self, settings,
                                                             product_root, monkeypatch):
        client, _ = tooled(settings, product_root, monkeypatch, rows=[row(13)])
        assert client.get(f"{BASE}/4/seated").status_code == 422

    def test_reading_the_seat_writes_nothing(self, settings, product_root, monkeypatch):
        monkeypatch.setattr(adjust_resource, "seated_payload",
                            lambda case, run_dir, tooth: {"tooth": tooth})
        client, _ = tooled(settings, product_root, monkeypatch)
        before = (SessionStore(product_root).load(CASE)).version
        client.get(f"{BASE}/4/seated")
        assert (SessionStore(product_root).load(CASE)).version == before
