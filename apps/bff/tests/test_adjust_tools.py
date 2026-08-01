"""THE FOUR ADJUST TOOLS' ENDPOINTS (plan §4 Adjust, §5; slice 6) — the rework surface.

``POST .../sites/{tooth}/{rotation|mark-trench|fit-by-points|best-fit}`` plus the reads
the panes open on, ``GET .../sites/{tooth}/seated`` and ``GET .../sites/{tooth}/landmarks``
(client 2026-07-29, item 3 — AUTO-MARK: "another tool where we automatically mark the
points in the library and the client has to match the same points on the scan").

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

from types import SimpleNamespace

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
        deviation={"deviation_rms_mm": 0.52, "deviation_p90_mm": 0.88},
        stale_metrics=["rim_agreement_mm", "guidance"],
        nudge={"operator_delta_deg": 1.0, "cumulative_deg": 1.0},
        applied_delta_deg=1.0, cumulative_deg=1.0, stability_excess_mm=0.002,
        pane_payload={"tooth": tooth, "preview": False,
                      "stats": {"rms_mm": 0.52, "p90_mm": 0.88}})
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


def materialize_proof(client, product_root, tooth: int) -> None:
    """Lay down the alignment proof the stubbed tool claims. The confirmation seals QC
    BYTES, so a proof the package names and disk does not hold refuses the whole
    confirmation (AM-10) — the real tools write it, the stub cannot."""
    run_id = client.get(f"/api/case-sessions/{CASE}/run").json()["run_id"]
    path = (product_root / CASE / "runs" / run_id
            / f"{CASE}-{tooth}-alignment-proof.png")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG:proof")


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

    def test_a_library_span_reaches_the_application_with_both_part_ends(
            self, settings, product_root, monkeypatch):
        """TOOL 1'S WIRE FORM (client 2026-08-01): a second PART point on the same
        pair. The BFF adds no geometry here either — whether the bearing it names is
        usable is the application's read, not this layer's."""
        client, calls = tooled(settings, product_root, monkeypatch)
        res = client.post(f"{BASE}/4/fit-by-points", json={"pairs": [{
            "part_point": [1.5, 0.0, 1.0],
            "part_point_end": [1.5, 1.0, 1.0],
            "scan_point": [1.0, 0.0, 0.0],
            "scan_point_end": [2.0, 0.0, 0.0]}]})
        assert res.status_code == 200
        (pair,) = calls[0]["args"][0]
        assert pair.part_point_end == [1.5, 1.0, 1.0]
        assert pair.is_part_span is True

    def test_a_second_part_point_beside_a_named_feature_is_refused_at_the_wire(
            self, settings, product_root, monkeypatch):
        """A marked feature carries an azimuth and a radius, never a direction — so
        this shape can never produce a bearing and is decidable from the ask alone.
        The application refuses it too; refusing at the corpus keeps the round trip
        off the physics entirely."""
        client, calls = tooled(settings, product_root, monkeypatch)
        res = client.post(f"{BASE}/4/fit-by-points", json={"pairs": [{
            "feature_id": "trench-01",
            "part_point_end": [1.5, 1.0, 1.0],
            "scan_point": [1.0, 0.0, 0.0],
            "scan_point_end": [2.0, 0.0, 0.0]}]})
        assert res.status_code == 422
        assert calls == []

    def test_a_non_finite_part_span_end_is_refused_like_every_other_coordinate(
            self, settings, product_root, monkeypatch):
        client, _ = tooled(settings, product_root, monkeypatch)
        res = client.post(f"{BASE}/4/fit-by-points", json={"pairs": [{
            "part_point": [1.5, 0.0, 1.0], "part_point_end": [1.5, 1.0],
            "scan_point": [1.0, 0.0, 0.0], "scan_point_end": [2.0, 0.0, 0.0]}]})
        assert res.status_code == 422


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

    def test_a_correspondence_persists_the_pairs_the_operator_named(
            self, settings, product_root, monkeypatch):
        """GAP ``per-site-pairs-rotation-diameter`` (2026-07-31): the pair count
        lived only in a client-side draft — reload the page and it was gone, and no
        Deliver row could say what a fit was built from.

        PAIRS come from the REQUEST, observations from the outcome: a two-point span
        contributes two residual rows to one pair, so counting the outcome would
        over-report what the operator actually placed. SPANS and DIRECTIONS_USED come
        off the observations' own kinds (audit finding 6, 2026-07-31) — one radial
        span here, so its direction counted."""
        client, _ = tooled(settings, product_root, monkeypatch, result=outcome(
            4, operation="fit-by-points",
            pairs=[{"observation": "midpoint", "residual_mm": 0.05},
                   {"observation": "direction", "residual_mm": 0.07},
                   {"observation": "point", "residual_mm": 0.06}],
            residual_rms_mm=0.06))
        assert client.post(f"{BASE}/4/fit-by-points", json={"pairs": [
            {"feature_id": "code-1", "scan_point": [0.0, 0.0, 0.0],
             "scan_point_end": [1.0, 0.0, 0.0]},
            {"feature_id": "code-2", "scan_point": [2.0, 0.0, 0.0]},
        ]}).status_code == 200
        row4 = next(r for r in client.get(f"/api/case-sessions/{CASE}/run").json()[
            "sites"] if r["tooth"] == 4)
        assert row4["correspondence"] == {"pairs": 2, "observations": 3,
                                          "spans": 1, "directions_used": 1,
                                          "max_pairs": 8, "residual_rms_mm": 0.06,
                                          "cross_checked": True}

    def test_a_one_observation_fit_is_folded_as_not_cross_checked(
            self, settings, product_root, monkeypatch):
        """THE VACUOUS-RMS DEFECT (cap6020-neodent-gm, 2026-08-01), on the row the
        confirmation seals. One pair produces one observation, its residual is zero by
        construction, and the RMS over it is arithmetic — so the block carries no
        figure AND says why, rather than leaving a reader to infer the difference
        between "no number" and "a number that means nothing".

        Derived from the OBSERVATION COUNT this same block states, by the worker's own
        predicate, so ``observations`` and ``cross_checked`` cannot disagree here."""
        client, _ = tooled(settings, product_root, monkeypatch, result=outcome(
            4, operation="fit-by-points",
            pairs=[{"observation": "point", "residual_mm": 0.0}],
            residual_rms_mm=None, cross_checked=False))
        assert client.post(f"{BASE}/4/fit-by-points", json={"pairs": [
            {"feature_id": "code-1", "scan_point": [0.0, 0.0, 0.0]}]},
        ).status_code == 200
        row4 = next(r for r in client.get(f"/api/case-sessions/{CASE}/run").json()[
            "sites"] if r["tooth"] == 4)
        assert row4["correspondence"]["observations"] == 1
        assert row4["correspondence"]["cross_checked"] is False
        assert row4["correspondence"]["residual_rms_mm"] is None

    def test_the_outcome_view_carries_the_cross_check_fact_to_the_surface(
            self, settings, product_root, monkeypatch):
        """The tool panel must be able to say it at the moment it happens, not two
        stages later — so the fact rides on the response the Apply click reads."""
        client, _ = tooled(settings, product_root, monkeypatch, result=outcome(
            4, operation="fit-by-points",
            detail=("fit by 1 point pair(s) → 1 observation(s): rotated -50.9° "
                    "(cumulative -50.9°), a single observation fixes the rotation "
                    "exactly — there is no second mark for it to disagree with, so "
                    "this fit has no agreement number"),
            pairs=[{"observation": "point", "residual_mm": 0.0}],
            residual_rms_mm=None, cross_checked=False))
        body = client.post(f"{BASE}/4/fit-by-points", json={"pairs": [
            {"feature_id": "code-1", "scan_point": [0.0, 0.0, 0.0]}]}).json()
        assert body["outcome"]["cross_checked"] is False
        assert body["outcome"]["residual_rms_mm"] is None
        assert "0.000mm RMS" not in body["outcome"]["detail"]

    def test_a_rotation_reset_drops_the_correspondence_with_the_best_fit_block(
            self, settings, product_root, monkeypatch):
        """A site back on the pipeline's certified pose stands on no correspondence
        at all — leaving the block would have the sealed row credit a fit that has
        been undone."""
        client, _ = tooled(settings, product_root, monkeypatch, result=outcome(
            4, operation="fit-by-points", pairs=[{"residual_mm": 0.05}],
            residual_rms_mm=0.05))
        assert client.post(f"{BASE}/4/fit-by-points", json={"pairs": [
            {"feature_id": "code-1", "scan_point": [0.0, 0.0, 0.0]}]},
        ).status_code == 200
        stub_tools(monkeypatch, result=outcome(4, operation="rotation-reset"))
        assert client.post(f"{BASE}/4/rotation",
                           json={"reset": True}).status_code == 200
        row4 = next(r for r in client.get(f"/api/case-sessions/{CASE}/run").json()[
            "sites"] if r["tooth"] == 4)
        assert "correspondence" not in row4

    def test_a_rotation_drops_the_correspondence_it_moved_off(
            self, settings, product_root, monkeypatch):
        """AUDIT FINDING 5 (2026-07-31), and the test it replaces was the finding.

        The old rule cleared the block only on ``rotation-reset`` and sanctioned
        everything else with "a further nudge still stands on the pose the
        correspondence produced". A nudge is BY DEFINITION a move off that pose:
        fit three pairs to 0.021mm RMS, then step 15°, and the marks now disagree by
        fifteen degrees while the sealed row goes on claiming 0.021mm. That violates
        the invariant ``_fold_outcome``'s own docstring was rewritten for (finding E,
        2026-07-28: THE ROW MUST DESCRIBE THE POSE THAT SHIPPED), and unlike the
        row's other numbers it was not even named in ``rework.stale_metrics``.

        So the guard is INVERTED: the block belongs to the act that produced it, and
        any later applied act drops it — the same rule ``best_fit`` already got on
        reset."""
        client, _ = tooled(settings, product_root, monkeypatch, result=outcome(
            4, operation="fit-by-points", pairs=[{"residual_mm": 0.05}],
            residual_rms_mm=0.05))
        assert client.post(f"{BASE}/4/fit-by-points", json={"pairs": [
            {"feature_id": "code-1", "scan_point": [0.0, 0.0, 0.0]}]},
        ).status_code == 200
        stub_tools(monkeypatch, result=outcome(4, operation="rotation"))
        assert client.post(f"{BASE}/4/rotation",
                           json={"step_deg": 15.0}).status_code == 200
        row4 = next(r for r in client.get(f"/api/case-sessions/{CASE}/run").json()[
            "sites"] if r["tooth"] == 4)
        assert "correspondence" not in row4

    def test_a_best_fit_drops_the_correspondence_the_new_pose_does_not_stand_on(
            self, settings, product_root, monkeypatch):
        """The sharper half of the same finding: ``best-fit`` is a full 6-DoF
        re-pose that REPLACES ``row["best_fit"]`` in the line immediately above, and
        left the residual of a superseded pose standing beside it — sealed into the
        confirmed bundle and rendered on the Deliver row as "the correspondence the
        shipped pose stands on"."""
        client, _ = tooled(settings, product_root, monkeypatch, result=outcome(
            4, operation="fit-by-points", pairs=[{"residual_mm": 0.05}],
            residual_rms_mm=0.021))
        assert client.post(f"{BASE}/4/fit-by-points", json={"pairs": [
            {"feature_id": "code-1", "scan_point": [0.0, 0.0, 0.0]}]},
        ).status_code == 200
        stub_tools(monkeypatch, result=outcome(
            4, operation="best-fit", nudge=None,
            best_fit={"matching_diameter_mm": 0.45, "rms_mm": 0.031}))
        assert client.post(f"{BASE}/4/best-fit", json={
            "matching_diameter_mm": 0.45, "apply": True}).status_code == 200
        row4 = next(r for r in client.get(f"/api/case-sessions/{CASE}/run").json()[
            "sites"] if r["tooth"] == 4)
        assert row4["best_fit"]["matching_diameter_mm"] == 0.45
        assert "correspondence" not in row4

    def test_the_block_states_how_many_spans_counted_their_directions(
            self, settings, product_root, monkeypatch):
        """AUDIT FINDING 6 (2026-07-31). The block's stated contract was that pairs
        and observations "differ exactly when spans were used" — false. A span emits
        its direction only when it reads as RADIAL (``observations_for``:
        ``abs(radial_offset_deg) <= SPAN_RADIAL_TOLERANCE_DEG``); a chord across the
        feature contributes its midpoint alone.

        So three chord spans produced {pairs: 3, observations: 3} — byte-identical to
        three clean single clicks, and the reader of the confirmed document could not
        tell that three spans were placed and all three directions discarded. That is
        exactly the fact the 2026-07-28 dropped-direction fix exists to state.

        The accounting the physics actually produces is carried instead: each span
        emits one ``midpoint`` observation and, only if its direction counted, one
        ``direction`` observation."""
        client, _ = tooled(settings, product_root, monkeypatch, result=outcome(
            4, operation="fit-by-points",
            # three chord spans: three midpoints, no direction survived
            pairs=[{"observation": "midpoint", "residual_mm": 0.05},
                   {"observation": "midpoint", "residual_mm": 0.07},
                   {"observation": "midpoint", "residual_mm": 0.06}],
            residual_rms_mm=0.06))
        span = {"scan_point": [0.0, 0.0, 0.0], "scan_point_end": [1.0, 0.0, 0.0]}
        assert client.post(f"{BASE}/4/fit-by-points", json={"pairs": [
            {"feature_id": f"code-{i}", **span} for i in (1, 2, 3)]},
        ).status_code == 200
        row4 = next(r for r in client.get(f"/api/case-sessions/{CASE}/run").json()[
            "sites"] if r["tooth"] == 4)
        assert row4["correspondence"]["pairs"] == 3
        assert row4["correspondence"]["observations"] == 3
        assert row4["correspondence"]["spans"] == 3
        assert row4["correspondence"]["directions_used"] == 0

    def test_the_rows_deviation_is_re_derived_over_the_pose_that_just_landed(
            self, settings, product_root, monkeypatch):
        """FINDING E (review 2026-07-28): the row's numbers describe A POSE, and the
        confirmation SEALS the row. Left alone they went on reporting the pre-rework
        fit under a freshly derived hash — a stale document wearing a fresh signature.
        """
        client, _ = tooled(settings, product_root, monkeypatch)
        run = client.get(f"/api/case-sessions/{CASE}/run").json()
        assert next(r for r in run["sites"] if r["tooth"] == 4)["deviation_rms_mm"] \
            == 0.43
        client.post(f"{BASE}/4/rotation", json={"step_deg": 1.0})
        row4 = next(r for r in client.get(f"/api/case-sessions/{CASE}/run").json()[
            "sites"] if r["tooth"] == 4)
        assert row4["deviation_rms_mm"] == 0.52
        assert row4["deviation_p90_mm"] == 0.88

    def test_what_could_not_be_re_derived_is_named_on_the_row_not_left_unsaid(
            self, settings, product_root, monkeypatch):
        client, _ = tooled(settings, product_root, monkeypatch)
        client.post(f"{BASE}/4/rotation", json={"step_deg": 1.0})
        row4 = next(r for r in client.get(f"/api/case-sessions/{CASE}/run").json()[
            "sites"] if r["tooth"] == 4)
        assert row4["rework"]["stale_metrics"] == ["rim_agreement_mm", "guidance"]

    def test_a_reset_clears_the_stale_marker_because_nothing_predates_it(
            self, settings, product_root, monkeypatch):
        """A reset puts the site back on the pipeline's own certified pose, so the
        run's rim agreement and guidance describe it correctly again."""
        client, _ = tooled(settings, product_root, monkeypatch)
        client.post(f"{BASE}/4/rotation", json={"step_deg": 1.0})
        stub_tools(monkeypatch, result=outcome(
            4, operation="rotation-reset", stale_metrics=[],
            best_fit=None, detail="restored the pipeline's certified pose"))
        client.post(f"{BASE}/4/rotation", json={"reset": True})
        row4 = next(r for r in client.get(f"/api/case-sessions/{CASE}/run").json()[
            "sites"] if r["tooth"] == 4)
        assert "rework" not in row4

    def test_a_reset_retires_the_rows_best_fit_block_with_the_pose_it_described(
            self, settings, product_root, monkeypatch):
        client, _ = tooled(settings, product_root, monkeypatch)
        stub_tools(monkeypatch, result=outcome(
            4, operation="best-fit", best_fit={"roi_mean_after_mm": 0.19}))
        client.post(f"{BASE}/4/best-fit", json={"matching_diameter_mm": 0.3})
        stub_tools(monkeypatch, result=outcome(4, operation="rotation-reset",
                                               stale_metrics=[]))
        client.post(f"{BASE}/4/rotation", json={"reset": True})
        row4 = next(r for r in client.get(f"/api/case-sessions/{CASE}/run").json()[
            "sites"] if r["tooth"] == 4)
        assert "best_fit" not in row4

    def test_an_adjusted_site_cannot_be_confirmed_until_it_is_reviewed_again(
            self, settings, product_root, monkeypatch):
        """FINDING F (review 2026-07-28): "every site resolved" lived ONLY in flow.ts.
        Before this slice ADJUSTED had no writer, so the divergence was unreachable;
        the tools made it reachable, and an adjusted site whose own acceptance row read
        FAIL confirmed and released straight through the API. Screen order in a
        presentational app is not a control — the precondition belongs on the act."""
        client, _ = tooled(settings, product_root, monkeypatch)
        client.post(f"{BASE}/13/rotation", json={"step_deg": 1.0})
        res = client.post(f"/api/case-sessions/{CASE}/confirm",
                          json={"acknowledged_flags": [4], "terms_accepted": True})
        assert res.status_code == 422
        assert "tooth 13" in res.json()["detail"]
        assert "adjusted" in res.json()["detail"]

    def test_the_review_tick_over_the_new_panes_opens_the_confirmation_again(
            self, settings, product_root, monkeypatch):
        """The rung the ladder already drew (adjusted → review_ready): the operator
        attests the NEW pose, and Deliver opens on that attestation, not on time."""
        client, _ = tooled(settings, product_root, monkeypatch)
        client.post(f"{BASE}/13/rotation", json={"step_deg": 1.0})
        materialize_proof(client, product_root, 13)
        assert client.post(f"/api/case-sessions/{CASE}/sites/13/review"
                           ).status_code == 200
        assert site_status(product_root, 13) == "ready"
        assert client.post(f"/api/case-sessions/{CASE}/confirm",
                           json={"acknowledged_flags": [4],
                                "terms_accepted": True}).status_code == 200

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
            "acknowledged_flags": [4], "terms_accepted": True}).status_code == 200
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
                           json={"acknowledged_flags": [4],
                                "terms_accepted": True}).status_code == 200
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
                           json={"acknowledged_flags": [4],
                                "terms_accepted": True}).status_code == 200
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

    def test_the_measured_rim_centre_survives_the_passthrough(self, settings,
                                                              product_root, monkeypatch):
        """THE PRE-REFUSAL'S ONE DEPENDENCY (plan §10-F). ``clock_reference`` is the
        SERVER'S own rim centre and bound, and the product refuses a screw-access mark
        locally against it — but only while it actually arrives. Nothing else in this
        suite names the field, so a tidy-up that gave these handlers a response_model
        would drop it and the pre-refusal would go quiet with no test failing. This is
        that test."""
        payload = {"tooth": 4, "preview": False, "points": [], "faces": [],
                   "clock_reference": {"rim_centre": [1.0, 2.0, 3.0],
                                       "min_lever_mm": 0.5}}
        monkeypatch.setattr(adjust_resource, "seated_payload",
                            lambda case, run_dir, tooth: payload)
        client, _ = tooled(settings, product_root, monkeypatch)
        body = client.get(f"{BASE}/4/seated").json()
        assert body["clock_reference"] == {"rim_centre": [1.0, 2.0, 3.0],
                                           "min_lever_mm": 0.5}

    def test_a_tool_result_carries_the_rim_centre_onto_its_pane_payload(
            self, settings, product_root, monkeypatch):
        """The same field on the OTHER path: after an adjustment the panes re-read from
        the tool's own ``pane_payload``, and the next mark is guarded against the rim
        centre THAT pose measured — not the one the stage opened on."""
        client, _ = tooled(settings, product_root, monkeypatch, result=outcome(
            pane_payload={"tooth": 4, "preview": False,
                          "clock_reference": {"rim_centre": [0.0, 0.0, 1.0],
                                              "min_lever_mm": 0.5}}))
        res = client.post(f"{BASE}/4/rotation", json={"step_deg": 1.0})
        assert res.status_code == 200
        assert res.json()["pane_payload"]["clock_reference"]["min_lever_mm"] == 0.5

    def test_reading_the_seat_writes_nothing(self, settings, product_root, monkeypatch):
        monkeypatch.setattr(adjust_resource, "seated_payload",
                            lambda case, run_dir, tooth: {"tooth": tooth})
        client, _ = tooled(settings, product_root, monkeypatch)
        before = (SessionStore(product_root).load(CASE)).version
        client.get(f"{BASE}/4/seated")
        assert (SessionStore(product_root).load(CASE)).version == before


class TestLandmarksRead:
    """AUTO-MARK'S PROPOSAL (client 2026-07-29, item 3): the part half of every
    correspondence pair, read off the site's declared template instead of hunted for
    by eye. ``clock_landmarks`` and ``load_site`` are the worker's own, pinned in
    ``apps/worker/tests/test_adjust.py`` — best clock evidence first, filtered to
    features that pass ``PartFeature.defines_rotation``. What this resource owns is
    the same thing ``seated`` owns: the precondition, the load, and the refusal split,
    nothing more — so the double here is a stub of ``load_site`` + ``clock_landmarks``,
    exactly like ``seated_payload`` is stubbed above."""

    @staticmethod
    def _stub_template(monkeypatch, landmarks, *, template=None):
        template = template if template is not None else object()
        recorded: dict = {}

        def fake_load_site(case, run_dir, tooth):
            recorded["case"] = case.id
            recorded["run_dir"] = run_dir
            recorded["tooth"] = tooth
            return SimpleNamespace(template=template)

        def fake_clock_landmarks(t):
            recorded["template"] = t
            return landmarks

        monkeypatch.setattr(adjust_resource, "load_site", fake_load_site)
        monkeypatch.setattr(adjust_resource, "clock_landmarks", fake_clock_landmarks)
        return recorded, template

    def test_it_serves_the_proposed_landmarks_best_lever_first(
            self, settings, product_root, monkeypatch):
        landmarks = [
            {"id": "notch-a", "kind": "notch", "point": [1.5, 0.0, 2.0],
             "lever_arm_mm": 1.5, "azimuth_deg": 0.0},
            {"id": "notch-b", "kind": "notch", "point": [0.0, 0.9, 2.0],
             "lever_arm_mm": 0.9, "azimuth_deg": 90.0},
        ]
        recorded, template = self._stub_template(monkeypatch, landmarks)
        client, _ = tooled(settings, product_root, monkeypatch)
        res = client.get(f"{BASE}/4/landmarks")
        assert res.status_code == 200
        assert res.json() == landmarks
        # the template that reached clock_landmarks is the SITE's own — load_site's
        # read, not a mesh this resource conjured itself
        assert recorded["template"] is template
        assert recorded["case"] == CASE
        assert recorded["tooth"] == 4

    def test_it_stands_on_the_same_precondition_as_the_tools(
            self, settings, product_root, monkeypatch):
        self._stub_template(monkeypatch, [])
        client, _ = tooled(settings, product_root, monkeypatch, rows=[row(13)])
        assert client.get(f"{BASE}/4/landmarks").status_code == 422

    def test_reading_landmarks_writes_nothing(self, settings, product_root, monkeypatch):
        self._stub_template(monkeypatch, [])
        client, _ = tooled(settings, product_root, monkeypatch)
        before = (SessionStore(product_root).load(CASE)).version
        client.get(f"{BASE}/4/landmarks")
        assert (SessionStore(product_root).load(CASE)).version == before

    def test_a_shipped_variant_that_left_the_library_refuses_in_the_applications_words(
            self, settings, product_root, monkeypatch):
        def boom(case, run_dir, tooth):
            raise AdjustRefused(
                "shipped variant 'gone' is not in the current neodent-gm library — "
                "cannot re-pose")
        monkeypatch.setattr(adjust_resource, "load_site", boom)
        client, _ = tooled(settings, product_root, monkeypatch)
        res = client.get(f"{BASE}/4/landmarks")
        assert res.status_code == 409
        assert "cannot re-pose" in res.text

    def test_a_run_with_no_shipped_pose_is_a_422_in_the_applications_words(
            self, settings, product_root, monkeypatch):
        def boom(case, run_dir, tooth):
            raise AdjustInvalid("tooth 4 has no shipped pose in this run — nothing to "
                                "adjust")
        monkeypatch.setattr(adjust_resource, "load_site", boom)
        client, _ = tooled(settings, product_root, monkeypatch)
        res = client.get(f"{BASE}/4/landmarks")
        assert res.status_code == 422
        assert "nothing to adjust" in res.text
