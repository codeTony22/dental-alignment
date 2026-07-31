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

    def test_a_clean_row_claims_nothing_predates_it(self, settings, product_root):
        client = landed_client(settings, product_root, [row(4), row(13)])
        body = client.get("/api/case-sessions/neodent-gm/assurance").json()
        assert all(s["stale_metrics"] == [] for s in body["sites"])

    def test_a_reworked_rows_stale_numbers_are_named_on_the_document_itself(
            self, settings, product_root):
        """FINDING E (review 2026-07-28). Adjust re-derives the deviation scalars over
        the new pose but CANNOT re-derive the rim agreement (anchored on the scan's own
        fitted rim circle) or the guidance (a dozen run-time inputs the row does not
        carry). The confirmation seals this document, so it has to say which of its
        numbers predate the rework rather than let a fresh hash imply they are all
        current."""
        reworked = row(4, level="attention")
        reworked["rework"] = {"stale_metrics": ["rim_agreement_mm", "guidance"]}
        client = landed_client(settings, product_root, [reworked, row(13)])
        body = client.get("/api/case-sessions/neodent-gm/assurance").json()
        site = next(s for s in body["sites"] if s["tooth"] == 4)
        assert site["stale_metrics"] == ["rim_agreement_mm", "guidance"]
        # and the numbers themselves stay visible — naming them is disclosure, not
        # deletion: hiding a stale number would leave the doctor with nothing to weigh
        assert site["rim_agreement_mm"] == 0.07
        assert site["gate"]["level"] == "attention"

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


# --- the disclosure gap: production.note (plan §10-E, finding 2026-07-28) ---------------

SHARED_PART_NOTE = ("single construction part shared across sites identifying 2 "
                    "distinct variants — per-variant construction parts needed")


def with_note(r):
    r["production"]["note"] = SHARED_PART_NOTE
    return r


class TestTheProductionNoteSurfaces:
    """auto_flow.py already computes ``"single construction part shared across
    sites identifying N distinct variants — per-variant construction parts
    needed"`` into ``row["production"]["note"]`` on a multi-variant case. Before
    this fix the assurance read picked the clamp fields out of that same block
    and DROPPED the note — a two-variant case showed per-site GREEN verdicts
    with nothing said. This surfaces it, verbatim, beside the clamp story."""

    def test_the_note_rides_beside_the_clamp_fields(
            self, settings, product_root):
        client = landed_client(settings, product_root,
                               [with_note(row(4)), with_note(row(13))])
        body = client.get("/api/case-sessions/neodent-gm/assurance").json()
        for site in body["sites"]:
            assert site["production_note"] == SHARED_PART_NOTE
            # the CLAMP fields the row already carried are untouched — the note
            # sits BESIDE them, not instead of them
            assert "clamp" in site

    def test_a_single_variant_case_carries_no_note_at_all(
            self, settings, product_root):
        client = landed_client(settings, product_root, [row(4), row(13)])
        body = client.get("/api/case-sessions/neodent-gm/assurance").json()
        assert all(s["production_note"] is None for s in body["sites"])

    def test_the_gate_word_stays_the_workers_own_verbatim(
            self, settings, product_root):
        """The escalation this finding demands lives in SORTING and in the
        confirmation's acknowledgment gate (test_deliver.py) — never by
        rewriting what the worker itself said the guidance was. ``AssuranceGate``
        keeps its own documented promise: "the run's guidance verdict verbatim"."""
        client = landed_client(settings, product_root,
                               [with_note(row(4, level="ready")), row(13)])
        body = client.get("/api/case-sessions/neodent-gm/assurance").json()
        site = next(s for s in body["sites"] if s["tooth"] == 4)
        assert site["gate"]["level"] == "ready"
        assert site["gate"]["actions"] == []

    def test_a_production_noted_row_sorts_pinned_first_even_though_ready(
            self, settings, product_root):
        """THE FLAG DECISION, made visible in ordering: a production-noted site
        is at least as urgent as "action-needed" and pins ABOVE a clean ready
        row — even though the run itself called it ready. The note's own words
        are "cannot match", not "differs slightly"."""
        client = landed_client(settings, product_root,
                               [row(4, level="ready"),
                                with_note(row(13, level="ready"))])
        body = client.get("/api/case-sessions/neodent-gm/assurance").json()
        assert [s["tooth"] for s in body["sites"]] == [13, 4]

    def test_a_production_noted_row_still_outranks_a_merely_attention_row(
            self, settings, product_root):
        client = landed_client(settings, product_root,
                               [row(4, level="attention"),
                                with_note(row(13, level="ready"))])
        body = client.get("/api/case-sessions/neodent-gm/assurance").json()
        assert [s["tooth"] for s in body["sites"]] == [13, 4]


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


class TestTheAlignmentMetricsAreTyped:
    """GAP ``per-site-pairs-rotation-diameter`` (2026-07-31). Three facts about work
    already done reached the surface only as untyped dicts inside ``RunView.sites``
    — or, for the pair count, not at all — so no Deliver row could state them. They
    are DERIVED (the tools' own readings, folded at landing), never client-supplied,
    and they are typed HERE, on the document the operator signs."""

    def rows_with(self, extra: dict):
        r = row(4)
        r.update(extra)
        return [r, row(13)]

    def site(self, client, tooth: int) -> dict:
        body = client.get("/api/case-sessions/neodent-gm/assurance").json()
        return next(s for s in body["sites"] if s["tooth"] == tooth)

    def test_a_clean_run_claims_none_of_them(self, settings, product_root):
        # None here means "nobody touched this site", never "we forgot"
        client = landed_client(settings, product_root, [row(4), row(13)])
        site = self.site(client, 4)
        assert site["rotation"]["operator_cumulative_deg"] is None
        assert site["matching_diameter_mm"] is None
        assert site["correspondence"] is None

    def test_the_operators_cumulative_rotation_is_distinct_from_the_measured_one(
            self, settings, product_root):
        # ``deg`` is what the instrument reads at the shipped pose; the nudge is how
        # far a human turned the cap off the certified one. Two questions, two fields.
        rows = self.rows_with({
            "clocking": {"evidence": "codes", "rotation_unverified": False,
                         "notch_shift_deg": 1.4},
            "nudge": {"operator_delta_deg": 5.0, "cumulative_deg": 12.5}})
        client = landed_client(settings, product_root, rows)
        rotation = self.site(client, 4)["rotation"]
        assert rotation["deg"] == 1.4
        assert rotation["operator_cumulative_deg"] == 12.5

    def test_the_best_fit_dial_reaches_the_row(self, settings, product_root):
        rows = self.rows_with({"best_fit": {"matching_diameter_mm": 0.45,
                                            "roi_mean_after_mm": 0.12}})
        client = landed_client(settings, product_root, rows)
        assert self.site(client, 4)["matching_diameter_mm"] == 0.45

    def test_the_correspondence_says_pairs_observations_and_the_servers_own_cap(
            self, settings, product_root):
        # a two-point SPAN contributes a midpoint observation, and a SECOND one only
        # when its direction counted — so the counts alone cannot say how many spans
        # were placed (audit finding 6, 2026-07-31). ``spans``/``directions_used``
        # carry that, and ``max_pairs`` rides along so a surface renders "3/8" from a
        # server fact rather than a hard-coded bound.
        rows = self.rows_with({"correspondence": {"pairs": 3, "observations": 5,
                                                  "spans": 2, "directions_used": 2,
                                                  "max_pairs": 8,
                                                  "residual_rms_mm": 0.08}})
        client = landed_client(settings, product_root, rows)
        assert self.site(client, 4)["correspondence"] == {
            "pairs": 3, "observations": 5, "spans": 2, "directions_used": 2,
            "max_pairs": 8, "residual_rms_mm": 0.08}

    def test_three_chord_spans_no_longer_read_like_three_single_clicks(
            self, settings, product_root):
        """AUDIT FINDING 6's own scenario, on the wire. All three spans read more
        than 30° off their own radius, so every direction was discarded and the
        counts collapsed to 3/3 — identical to three plain clicks. The reader of the
        sealed row is now told three spans were placed and none of their directions
        counted."""
        rows = self.rows_with({"correspondence": {
            "pairs": 3, "observations": 3, "spans": 3, "directions_used": 0,
            "max_pairs": 8, "residual_rms_mm": 0.08}})
        block = self.site(landed_client(settings, product_root, rows),
                          4)["correspondence"]
        assert block["spans"] == 3 and block["directions_used"] == 0

    def test_a_malformed_block_is_ignored_rather_than_crashing_the_projection(
            self, settings, product_root):
        # every worker-shaped block on this row is read defensively; a string where
        # a dict belongs must not take the whole Deliver surface down
        rows = self.rows_with({"best_fit": "nope", "nudge": "nope",
                               "correspondence": "nope"})
        client = landed_client(settings, product_root, rows)
        site = self.site(client, 4)
        assert site["matching_diameter_mm"] is None
        assert site["correspondence"] is None
        assert site["rotation"]["operator_cumulative_deg"] is None


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
