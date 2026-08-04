"""ALIGNMENT EVIDENCE PERSISTS (§10-AD, client 2026-08-02: "when adjustment and
rerunning the alignment it does not take effect").

What the BFF decides, pinned here: an APPLIED evidence-bearing tool appends its
wire-shaped payload to the site's ``alignment_evidence`` (apply order); the rotation
NUDGE never does (its provenance is eyeball — auto-re-applying it would promote the
weakest evidence class); re-marking a centre retires the site's evidence with the
preview it invalidates (the pair-integrity rule); and the authorized run selection
SHIPS the evidence so the worker re-applies it after automation. The re-apply's
physics is worker-side (apps/worker/tests/test_evidence_reapply.py).
"""
from __future__ import annotations

import pytest

from bff.config import Settings
from bff.session import SessionStore

from conftest import make_data_tree
from test_adjust_tools import BASE, CASE, tooled
from test_assurance import landed_client
from test_run_resource import row


@pytest.fixture
def product_root(tmp_path):
    return tmp_path / "product"


@pytest.fixture
def data_root(tmp_path):
    return make_data_tree(tmp_path / "data")


@pytest.fixture
def settings(data_root, product_root) -> Settings:
    return Settings(data_root=data_root, product_root=product_root)


def evidence_of(product_root, tooth: int):
    return SessionStore(product_root).load(CASE).sites[str(tooth)].alignment_evidence


class TestTheEvidencePersists:
    def test_fit_by_points_persists_its_pairs_as_received(
            self, settings, product_root, monkeypatch):
        client, _ = tooled(settings, product_root, monkeypatch)
        pairs = [{"feature_id": "trench-01", "scan_point": [1.0, 2.0, 3.0]}]
        assert client.post(f"{BASE}/4/fit-by-points",
                           json={"pairs": pairs}).status_code == 200
        (entry,) = evidence_of(product_root, 4)
        assert entry.kind == "pairs"
        assert entry.pairs[0]["feature_id"] == "trench-01"
        assert entry.pairs[0]["scan_point"] == [1.0, 2.0, 3.0]
        assert entry.applied_at  # the act carries its own timestamp

    def test_mark_trench_persists_its_point(self, settings, product_root,
                                            monkeypatch):
        client, _ = tooled(settings, product_root, monkeypatch)
        assert client.post(f"{BASE}/4/mark-trench",
                           json={"scan_point": [4.0, 5.0, 6.0]}).status_code == 200
        (entry,) = evidence_of(product_root, 4)
        assert entry.kind == "mark"
        assert entry.point == [4.0, 5.0, 6.0]

    def test_best_fit_persists_its_diameter(self, settings, product_root,
                                            monkeypatch):
        client, _ = tooled(settings, product_root, monkeypatch)
        assert client.post(f"{BASE}/4/best-fit",
                           json={"matching_diameter_mm": 0.4}).status_code == 200
        (entry,) = evidence_of(product_root, 4)
        assert entry.kind == "best_fit"
        assert entry.matching_diameter_mm == 0.4

    def test_the_nudge_deliberately_leaves_no_evidence(self, settings, product_root,
                                                       monkeypatch):
        # eyeball with no marks: re-applying it silently on a future run would
        # promote the weakest evidence class — §10-AD's stated exception
        client, _ = tooled(settings, product_root, monkeypatch)
        assert client.post(f"{BASE}/4/rotation",
                           json={"step_deg": 1.0}).status_code == 200
        assert evidence_of(product_root, 4) == []

    def test_acts_accumulate_in_apply_order(self, settings, product_root,
                                            monkeypatch):
        client, _ = tooled(settings, product_root, monkeypatch)
        client.post(f"{BASE}/4/mark-trench", json={"scan_point": [1.0, 1.0, 1.0]})
        client.post(f"{BASE}/4/best-fit", json={"matching_diameter_mm": 0.3})
        kinds = [e.kind for e in evidence_of(product_root, 4)]
        assert kinds == ["mark", "best_fit"]

    def test_a_refused_tool_persists_nothing(self, settings, product_root,
                                             monkeypatch):
        client, calls = tooled(settings, product_root, monkeypatch)
        # nine pairs refuse at the wire — before any physics, before any persistence
        pairs = [{"feature_id": f"t-{i}", "scan_point": [0.0, 0.0, 0.0]}
                 for i in range(9)]
        assert client.post(f"{BASE}/4/fit-by-points",
                           json={"pairs": pairs}).status_code == 422
        assert evidence_of(product_root, 4) == []


class TestTheSelectionShipsIt:
    def test_the_authorized_run_carries_each_sites_evidence(
            self, settings, product_root, monkeypatch):
        # apply an evidence-bearing tool on a landed run, drive the site back to
        # READY through the store (no client path to a rung by design — the pricing
        # tests' precedent), clear the run pointer, and authorize a fresh run: its
        # selection must carry what the rework measured. The mutation is IN PLACE,
        # exactly as re-preview/re-review leave the evidence standing.
        client, _ = tooled(settings, product_root, monkeypatch)
        assert client.post(f"{BASE}/13/mark-trench",
                           json={"scan_point": [7.0, 8.0, 9.0]}).status_code == 200
        from bff.session import SeatedSelection, SiteStatus
        store = SessionStore(product_root)
        session = store.load(CASE)
        session.run = None
        for tooth in ("4", "13"):
            site = session.sites[tooth]
            site.status = SiteStatus.READY
            site.declared_variant = "5020"
            site.seat_method = "rim-seat"
            site.rim_agreement_mm = 0.07
            site.seated_selection = SeatedSelection(
                model="neodent-gm",
                construction_path="dess/neodent-gm-scanbody.stl",
                variant="5020", jaw="upper", gingival_offset_mm=0.2)
        store.save(session)
        from test_run_resource import (FakeWorker, client_with, row as run_row,
                                       summary_for)
        worker = FakeWorker(summary=summary_for([run_row(4), run_row(13)]))
        client2 = client_with(settings, worker)
        res = client2.post(f"/api/case-sessions/{CASE}/run")
        assert res.status_code == 200, res.text
        ((_case_id, submitted),) = worker.submitted
        evidence = submitted["selection"]["alignment_evidence"]
        assert list(evidence) == ["13"]
        assert evidence["13"][0]["kind"] == "mark"
        assert evidence["13"][0]["point"] == [7.0, 8.0, 9.0]

    def test_a_case_with_no_evidence_ships_an_empty_map(self, settings,
                                                        product_root):
        from test_run_resource import (FakeWorker, client_with, row as run_row,
                                       seed_ready, summary_for)
        worker = FakeWorker(summary=summary_for([run_row(4), run_row(13)]))
        client = client_with(settings, worker)
        seed_ready(product_root)
        assert client.post(f"/api/case-sessions/{CASE}/run").status_code == 200
        ((_case_id, submitted),) = worker.submitted
        assert submitted["selection"]["alignment_evidence"] == {}


class TestTheReMarkRetiresIt:
    def test_re_marking_a_centre_clears_that_sites_evidence(
            self, settings, product_root, monkeypatch):
        client, _ = tooled(settings, product_root, monkeypatch)
        client.post(f"{BASE}/4/mark-trench", json={"scan_point": [1.0, 1.0, 1.0]})
        assert len(evidence_of(product_root, 4)) == 1
        res = client.put(f"/api/case-sessions/{CASE}/sites/4/mark",
                         json={"center": [9.0, 9.0, 9.0]})
        assert res.status_code == 200, res.text
        assert evidence_of(product_root, 4) == []


class TestThePartBoundaryRetiresPairs:
    """AUDIT 2026-08-04: a "pairs" entry's PART half (feature_id / part_point) was
    measured against the DECLARED part. Re-declaring a different variant or switching
    the implant system replaces that geometry, and re-applying the old part half
    against the new part would land an 'applied' receipt over physics the operator
    never measured on this part. The scan-frame kinds survive — the mark is a real
    trench on a scan that did not change, and best_fit's diameter is an ask, not a
    part coordinate. A JAW change retires nothing: it moves the alignment's own
    input, not the scan or the part, and the re-apply's own gates judge the result."""

    def pairs_and_mark_on(self, client, tooth: int) -> None:
        client.post(f"{BASE}/{tooth}/mark-trench",
                    json={"scan_point": [1.0, 1.0, 1.0]})
        client.post(f"{BASE}/{tooth}/fit-by-points",
                    json={"pairs": [{"feature_id": "trench-01",
                                     "scan_point": [1.0, 2.0, 3.0]}]})

    def test_a_variant_redeclaration_retires_that_sites_pairs_evidence(
            self, settings, product_root, monkeypatch):
        # the catalog reads the filesystem — the second variant exists by existing
        (settings.data_root / "library/caps/neodent-gm"
         / "neodent-gm-6020.stl").touch()
        client, _ = tooled(settings, product_root, monkeypatch)
        self.pairs_and_mark_on(client, 4)
        assert [e.kind for e in evidence_of(product_root, 4)] == ["mark", "pairs"]
        res = client.put(f"/api/case-sessions/{CASE}/sites/4/declaration",
                         json={"variant": "6020"})
        assert res.status_code == 200, res.text
        assert [e.kind for e in evidence_of(product_root, 4)] == ["mark"]

    def test_a_same_variant_redeclaration_retires_nothing(
            self, settings, product_root, monkeypatch):
        client, _ = tooled(settings, product_root, monkeypatch)
        self.pairs_and_mark_on(client, 4)
        res = client.put(f"/api/case-sessions/{CASE}/sites/4/declaration",
                         json={"variant": "5020"})
        assert res.status_code == 200, res.text
        assert [e.kind for e in evidence_of(product_root, 4)] == ["mark", "pairs"]

    def test_a_system_switch_retires_pairs_on_every_site(
            self, settings, product_root, monkeypatch):
        caps = settings.data_root / "library/caps/zimmer-4.5"
        caps.mkdir(parents=True, exist_ok=True)
        (caps / "zimmer-4.5-5020.stl").touch()
        client, _ = tooled(settings, product_root, monkeypatch)
        self.pairs_and_mark_on(client, 4)
        self.pairs_and_mark_on(client, 13)
        res = client.put(f"/api/case-sessions/{CASE}/system",
                         json={"model": "zimmer-4.5"})
        assert res.status_code == 200, res.text
        assert [e.kind for e in evidence_of(product_root, 4)] == ["mark"]
        assert [e.kind for e in evidence_of(product_root, 13)] == ["mark"]

    def test_a_jaw_change_leaves_evidence_standing(
            self, settings, product_root, monkeypatch):
        client, _ = tooled(settings, product_root, monkeypatch)
        self.pairs_and_mark_on(client, 4)
        res = client.put(f"/api/case-sessions/{CASE}/choices",
                         json={"construction_path": "dess/neodent-gm-scanbody.stl",
                               "jaw": "lower", "gingival_offset_mm": 0.2})
        assert res.status_code == 200, res.text
        assert [e.kind for e in evidence_of(product_root, 4)] == ["mark", "pairs"]


class TestTheCountRidesTheDetail:
    def test_the_site_view_says_how_many_measurements_stand(
            self, settings, product_root, monkeypatch):
        client, _ = tooled(settings, product_root, monkeypatch)
        client.post(f"{BASE}/4/mark-trench", json={"scan_point": [1.0, 1.0, 1.0]})
        client.post(f"{BASE}/4/best-fit", json={"matching_diameter_mm": 0.3})
        body = client.get(f"/api/case-sessions/{CASE}").json()
        by_tooth = {s["tooth"]: s for s in body["sites"]}
        assert by_tooth[4]["alignment_evidence_count"] == 2
        assert by_tooth[13]["alignment_evidence_count"] == 0
