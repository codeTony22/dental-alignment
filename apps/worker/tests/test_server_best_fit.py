"""The MANUAL BEST-FIT pass at the review gate, and the ALIGNMENT PROOF artifact.

The best-fit is a PROPOSAL, exactly like the nudge: it runs the pipeline's own
refinement (auto_flow._refine_best_fit — trust region + monotonic improvement) on the
SHIPPED pose and the candidate is judged by the same certification bounds
(_certification_gates) the nudge/align/correspondence paths clear. A refusal is a 409
with the reason and NOTHING on disk changes; an adoption re-emits the site record,
re-reads the codes, writes the alignment proof, and lands in run-history.jsonl.

Exercised against the real live-demo artifacts — cap6030 (where the default matching
diameter finds a real improvement) and cap7030 (where the certified pose already is the
best fit in that band, so the endpoint refuses). Handlers are called directly, the
pattern of tests/test_server_nudge.py.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest
import trimesh
from fastapi import HTTPException
from pydantic import ValidationError

import case_prep.server as srv
from case_prep.server import BestFitIn, NudgeIn

APPLIES_CASE = "cap6030-neodent-gm"   # default diameter finds a real improvement here
REFUSES_CASE = "cap7030-zimmer-4.5"   # ...and none here: the certified pose stands
TOOTH = 29
REAL_OUT = srv.OUT  # captured at import, before any monkeypatching


def _demo_copy(case_id, tmp_path, monkeypatch) -> Path:
    """A disposable copy of a case's live-demo artifacts, so a best-fit never mutates
    the real demo package."""
    src = REAL_OUT / case_id
    if case_id not in srv.CASES or not (src / "package").exists():
        pytest.skip(f"{case_id} live-demo artifacts not present on this machine")
    shutil.copytree(src, tmp_path / case_id)
    monkeypatch.setattr(srv, "OUT", tmp_path)
    return tmp_path


@pytest.fixture()
def applies_out(tmp_path, monkeypatch) -> Path:
    return _demo_copy(APPLIES_CASE, tmp_path, monkeypatch)


@pytest.fixture()
def refuses_out(tmp_path, monkeypatch) -> Path:
    return _demo_copy(REFUSES_CASE, tmp_path, monkeypatch)


def _pkg(out: Path, case_id: str) -> Path:
    return out / case_id / "package"


def _implant(out: Path, case_id: str) -> dict:
    return json.loads((_pkg(out, case_id)
                       / f"{case_id}-{TOOTH}-implant.json").read_text())


def _events(out: Path, event: str = "best-fit"):
    hist = out / "run-history.jsonl"
    if not hist.exists():
        return []
    return [json.loads(ln) for ln in hist.read_text().strip().splitlines()
            if json.loads(ln).get("event") == event]


class TestBestFitContract:
    def test_unknown_tooth_404s(self, applies_out):
        with pytest.raises(HTTPException) as exc:
            srv.best_fit(APPLIES_CASE, 99, BestFitIn())
        assert exc.value.status_code == 404
        assert "run the automation first" in exc.value.detail

    def test_the_matching_diameter_is_bounded(self):
        # a dial, not a re-seat: the ceiling is the winner pass's own correspondence
        # cutoff doubled (a DIAMETER of 2 * 1.0mm)
        assert BestFitIn().matching_diameter_mm == 0.3
        assert srv._BEST_FIT_MAX_DIAMETER_MM == 2.0 * srv._BEST_FIT_CORR_DIST_MM
        with pytest.raises(ValidationError):
            BestFitIn(matching_diameter_mm=5.0)
        with pytest.raises(ValidationError):
            BestFitIn(matching_diameter_mm=0.0)
        with pytest.raises(ValidationError):
            BestFitIn(matching_diameter_mm=float("nan"))

    @pytest.mark.slow
    def test_the_diameter_maps_to_half_itself_as_the_icp_cutoff(self, applies_out):
        # THE MAPPING, pinned: matching_diameter_mm is a search DIAMETER; trimmed_icp's
        # max_corr_dist is a RADIUS about each source point, so cutoff = diameter / 2.
        seen = {}
        real = srv._refine_best_fit

        def spy(patch, template, m_init, accept=None, max_corr_dist=1.0,
                on_reject=None):
            seen["cutoff"] = max_corr_dist
            return real(patch, template, m_init, accept=accept,
                        max_corr_dist=max_corr_dist, on_reject=on_reject)

        srv._refine_best_fit = spy
        try:
            out = srv.best_fit(APPLIES_CASE, TOOTH,
                               BestFitIn(matching_diameter_mm=0.5))
        finally:
            srv._refine_best_fit = real
        assert seen["cutoff"] == pytest.approx(0.25)
        assert out["best_fit"]["correspondence_cutoff_mm"] == pytest.approx(0.25)
        assert out["best_fit"]["matching_diameter_mm"] == pytest.approx(0.5)


    def test_the_read_outs_ride_flat_for_the_ui(self, applies_out):
        # the numbers a dial UI shows sit at the top level as well as in ``best_fit``,
        # so a client never has to reach into a nested block to render the result
        out = srv.best_fit(APPLIES_CASE, TOOTH, BestFitIn())
        for key in ("matching_diameter_mm", "translation_mm", "rotation_deg",
                    "n_matched", "rms_mm", "max_mm", "rim_agreement_mm"):
            assert out[key] == out["best_fit"][key], key
        assert out["applied"] is True
        assert out["n_matched"] > 0                      # the fit's own support
        assert 0.0 < out["rms_mm"] <= out["max_mm"] <= out["best_fit"][
            "correspondence_cutoff_mm"], "residuals must be inside the matching band"


class TestBestFitMeasureOnly:
    """``apply=False`` is a PREVIEW: judged by the same gates, written nowhere."""

    def test_it_reports_the_move_without_touching_anything(self, applies_out):
        pkg = _pkg(applies_out, APPLIES_CASE)
        before = {p.name: p.read_bytes() for p in pkg.iterdir() if p.is_file()}
        run_before = (applies_out / APPLIES_CASE / "run.json").read_bytes()

        out = srv.best_fit(APPLIES_CASE, TOOTH, BestFitIn(apply=False))
        assert out["applied"] is False
        assert out["files"] == []
        assert out["translation_mm"] > 0.0                # a real candidate, measured
        assert out["clocking"] is None, "nothing was adopted, so nothing was re-read"

        assert {p.name: p.read_bytes() for p in pkg.iterdir() if p.is_file()} == before
        assert (applies_out / APPLIES_CASE / "run.json").read_bytes() == run_before
        assert not (pkg / f"{APPLIES_CASE}-{TOOTH}-alignment-proof.png").exists()
        (event,) = _events(applies_out)
        assert event["outcome"] == "measured" and event["applied"] is False

    @pytest.mark.slow
    def test_the_preview_and_the_applied_move_agree(self, applies_out):
        preview = srv.best_fit(APPLIES_CASE, TOOTH, BestFitIn(apply=False))
        applied = srv.best_fit(APPLIES_CASE, TOOTH, BestFitIn(apply=True))
        assert applied["best_fit"]["translation_mm"] == preview["translation_mm"]
        assert applied["best_fit"]["rotation_deg"] == preview["rotation_deg"]

    def test_a_gate_refusal_still_refuses_in_preview(self, applies_out, monkeypatch):
        # a candidate that cannot be adopted must not be previewed as adoptable
        monkeypatch.setattr(srv, "_NUDGE_FACE_MEAN_BOUND_MM", -1.0)
        with pytest.raises(HTTPException) as exc:
            srv.best_fit(APPLIES_CASE, TOOTH, BestFitIn(apply=False))
        assert exc.value.status_code == 409
        (event,) = _events(applies_out)
        assert event["outcome"] == "refused" and event["applied"] is False


class TestBestFitApplies:
    def test_it_moves_the_pose_reemits_and_audits(self, applies_out):
        before = _implant(applies_out, APPLIES_CASE)
        cap = _pkg(applies_out, APPLIES_CASE) / f"{APPLIES_CASE}-{TOOTH}-healingcap-aligned.stl"
        cap_before = cap.read_bytes()

        out = srv.best_fit(APPLIES_CASE, TOOTH, BestFitIn())
        fit = out["best_fit"]
        # a real 6-DoF move, inside _refine_best_fit's own trust region (<=1.2mm, <=8deg)
        assert 0.0 < fit["translation_mm"] <= 1.2
        assert 0.0 < fit["rotation_deg"] <= 8.0
        # ...that strictly improved the ROI agreement (the whole point of a best-fit)
        assert fit["roi_mean_after_mm"] < fit["roi_mean_before_mm"]
        # the codes were re-read at the adopted pose for the operator to judge
        assert set(out["clocking"]) >= {"notch_shift_deg", "notch_corr",
                                        "notch_prominence"}

        after = _implant(applies_out, APPLIES_CASE)
        W0 = np.asarray(before["pose_matrix"], float)
        W1 = np.asarray(after["pose_matrix"], float)
        assert not np.allclose(W0, W1)
        assert float(np.linalg.norm(W1[:3, 3] - W0[:3, 3])) == \
            pytest.approx(fit["translation_mm"], abs=1e-3)
        assert after["best_fit"] == fit
        assert cap.read_bytes() != cap_before, "the viewer's STL must be re-emitted"

        # the cached run row carries the adjusted state so a page reload is honest
        run = json.loads((applies_out / APPLIES_CASE / "run.json").read_text())
        row = next(r for r in run["summary"]["sites"] if r["tooth"] == TOOTH)
        assert row["best_fit"] == fit
        assert "notch_shift_deg" in row["clocking"]

        (event,) = _events(applies_out)
        assert event["outcome"] == "applied"
        assert event["matching_diameter_mm"] == 0.3
        assert event["correspondence_cutoff_mm"] == 0.15
        assert event["move"]["translation_mm"] == fit["translation_mm"]

    @pytest.mark.slow
    def test_it_is_not_a_clock_nudge_and_reset_still_undoes_it(self, applies_out):
        """A 6-DoF move must not be booked as a rotation: the site's cumulative nudge
        angle is untouched, and ``reset`` — which restores the pipeline's own certified
        pose — still puts the site back, best-fit included."""
        certified = np.asarray(_implant(applies_out, APPLIES_CASE)["pose_matrix"], float)
        srv.nudge_rotation(APPLIES_CASE, TOOTH, NudgeIn(delta_deg=3.0))
        assert _implant(applies_out, APPLIES_CASE)["nudge"]["cumulative_deg"] == 3.0

        srv.best_fit(APPLIES_CASE, TOOTH, BestFitIn())
        rec = _implant(applies_out, APPLIES_CASE)
        assert rec["nudge"]["cumulative_deg"] == 3.0, \
            "the best-fit rewrote the operator's cumulative ROTATION"
        assert np.allclose(np.asarray(rec["nudge"]["base_pose_matrix"], float), certified)

        srv.nudge_rotation(APPLIES_CASE, TOOTH, NudgeIn(reset=True))
        assert np.allclose(
            np.asarray(_implant(applies_out, APPLIES_CASE)["pose_matrix"], float),
            certified, atol=1e-9)

    def test_reset_undoes_a_best_fit_that_was_the_first_adjustment(self, applies_out):
        """REGRESSION: a best-fit with no prior nudge must still anchor the base pose.
        Without that, the site's base pose is read from the CURRENT record — so ``reset``
        would 'restore' the best-fitted pose it was supposed to undo."""
        certified = np.asarray(_implant(applies_out, APPLIES_CASE)["pose_matrix"], float)
        srv.best_fit(APPLIES_CASE, TOOTH, BestFitIn())
        moved = np.asarray(_implant(applies_out, APPLIES_CASE)["pose_matrix"], float)
        assert not np.allclose(moved, certified)

        srv.nudge_rotation(APPLIES_CASE, TOOTH, NudgeIn(reset=True))
        assert np.allclose(
            np.asarray(_implant(applies_out, APPLIES_CASE)["pose_matrix"], float),
            certified, atol=1e-9)

    @pytest.mark.slow
    def test_two_identical_requests_read_the_same_pose(self, applies_out):
        """DETERMINISM: the refinement samples the template surface, so the endpoint
        seeds it (and restores the global stream). One operator clicking twice on the
        same state must not get two different answers."""
        np.random.seed(0)
        stream = np.random.rand(3).tolist()

        first = srv.best_fit(APPLIES_CASE, TOOTH, BestFitIn())["best_fit"]
        np.random.seed(0)
        assert np.random.rand(3).tolist() == stream, "the endpoint ate the RNG stream"

        # re-run from the same starting pose, not from the adopted one
        srv.nudge_rotation(APPLIES_CASE, TOOTH, NudgeIn(reset=True))
        second = srv.best_fit(APPLIES_CASE, TOOTH, BestFitIn())["best_fit"]
        assert second["translation_mm"] == first["translation_mm"]
        assert second["rotation_deg"] == first["rotation_deg"]


class TestBestFitRefuses:
    def test_no_improvement_confirms_side_effect_free(self, refuses_out):
        """The certified pose already IS the best fit inside a 0.30mm matching diameter
        on cap7030 — the honest answer is 409 and an untouched package, never a move
        adopted because the operator asked for one. THIS branch alone is a PASS phrased
        as one (client ask 2026-07-26): the detail is machine-readable, worded as a
        confirmation, and carries the one-click wider search (2x the dial, capped at
        the ceiling); every other 409 in the file stays a plain sentence."""
        pkg = _pkg(refuses_out, REFUSES_CASE)
        before = {p.name: p.read_bytes() for p in pkg.iterdir() if p.is_file()}
        run_before = (refuses_out / REFUSES_CASE / "run.json").read_bytes()

        with pytest.raises(HTTPException) as exc:
            srv.best_fit(REFUSES_CASE, TOOTH, BestFitIn())
        assert exc.value.status_code == 409
        detail = exc.value.detail
        assert isinstance(detail, dict), "this one outcome is machine-readable"
        assert detail["kind"] == "already_optimal"
        assert "already the best fit" in detail["message"]
        assert "Ø0.30mm" in detail["message"]
        assert "refused" not in detail["message"], "a pass must not read as a failure"
        assert "widen to search further" in detail["message"], \
            "below the ceiling the confirmation invites the wider search"
        assert detail["matching_diameter_mm"] == pytest.approx(0.3)
        assert detail["suggested_diameter_mm"] == pytest.approx(0.6)

        assert {p.name: p.read_bytes() for p in pkg.iterdir() if p.is_file()} == before
        assert (refuses_out / REFUSES_CASE / "run.json").read_bytes() == run_before
        assert not (pkg / f"{REFUSES_CASE}-{TOOTH}-alignment-proof.png").exists()
        # a confirmation is still AUDITED — every attempt lands on the provenance
        # stream, outcome "refused" (the pose was not touched) plus the kind
        (event,) = _events(refuses_out)
        assert event["outcome"] == "refused"
        assert event["kind"] == "already_optimal"
        assert event["matching_diameter_mm"] == 0.3

    def test_the_wider_suggestion_never_exceeds_the_ceiling(self, applies_out,
                                                            monkeypatch):
        """2x the dial, capped at the operator ceiling (2.0mm) — the one-click widen
        must never offer a diameter the endpoint itself would 422."""
        monkeypatch.setattr(srv, "_refine_best_fit", lambda *a, **k: None)
        with pytest.raises(HTTPException) as exc:
            srv.best_fit(APPLIES_CASE, TOOTH, BestFitIn(matching_diameter_mm=1.5))
        assert exc.value.status_code == 409
        assert exc.value.detail["suggested_diameter_mm"] == pytest.approx(
            srv._BEST_FIT_MAX_DIAMETER_MM)

    def test_at_the_ceiling_the_confirmation_stops_inviting_a_wider_search(
            self, applies_out, monkeypatch):
        """At Ø2.00mm the doubled suggestion caps to the dial itself, so "widen to
        search further" was a lie and the UI's one-click widen re-ran the identical
        search forever (review 2026-07-26). The confirmation stands — it IS still a
        pass — but the message must say the band is the widest, and the suggestion
        equals the dial so the UI can suppress the button."""
        monkeypatch.setattr(srv, "_refine_best_fit", lambda *a, **k: None)
        with pytest.raises(HTTPException) as exc:
            srv.best_fit(APPLIES_CASE, TOOTH, BestFitIn(
                matching_diameter_mm=srv._BEST_FIT_MAX_DIAMETER_MM))
        assert exc.value.status_code == 409
        detail = exc.value.detail
        assert detail["kind"] == "already_optimal"
        assert detail["suggested_diameter_mm"] == pytest.approx(
            srv._BEST_FIT_MAX_DIAMETER_MM)
        assert "widest" in detail["message"]
        assert "widen to search further" not in detail["message"]

    def test_a_trust_region_exit_refuses_plainly_not_as_a_confirmation(
            self, refuses_out):
        """REAL-DATA pin of the split (review 2026-07-26): at Ø2.00mm on cap7030 the
        seeded ICP walks ~13.6° — outside _refine_best_fit's trust region. That None
        proved NOTHING about the certified pose being the in-band optimum, so it must
        be the plain-sentence refusal every real refusal is — never the green
        "already optimal" confirmation, whose one-click widen would push the search
        even further into basin-escape territory."""
        with pytest.raises(HTTPException) as exc:
            srv.best_fit(REFUSES_CASE, TOOTH, BestFitIn(matching_diameter_mm=2.0))
        assert exc.value.status_code == 409
        assert isinstance(exc.value.detail, str), \
            "only the confirmation is machine-readable; this is a real refusal"
        assert "trust region" in exc.value.detail
        assert "already the best fit" not in exc.value.detail
        (event,) = _events(refuses_out)
        assert event["outcome"] == "refused"
        assert "kind" not in event

    def test_the_certification_gates_judge_the_candidate(self, applies_out, monkeypatch):
        """The gates are never bypassed: with the bounds impossible to clear, the same
        move that applied above is refused with the gate's own words and nothing on disk
        changes."""
        pkg = _pkg(applies_out, APPLIES_CASE)
        before = {p.name: p.read_bytes() for p in pkg.iterdir() if p.is_file()}
        monkeypatch.setattr(srv, "_NUDGE_FACE_MEAN_BOUND_MM", -1.0)

        with pytest.raises(HTTPException) as exc:
            srv.best_fit(APPLIES_CASE, TOOTH, BestFitIn())
        assert exc.value.status_code == 409
        assert "top face would pull off the scan" in exc.value.detail
        assert {p.name: p.read_bytes() for p in pkg.iterdir() if p.is_file()} == before
        # the refused MOVE is on the audit line, so the geometry can be replayed
        (event,) = _events(applies_out)
        assert event["outcome"] == "refused" and event["move"]["translation_mm"] > 0.0

    def test_a_site_with_no_scan_surface_refuses(self, applies_out):
        implant = _pkg(applies_out, APPLIES_CASE) / f"{APPLIES_CASE}-{TOOTH}-implant.json"
        rec = json.loads(implant.read_text())
        W = np.asarray(rec["pose_matrix"], float)
        W[:3, 3] += 200.0  # the pose is nowhere near the scan
        implant.write_text(json.dumps({**rec, "pose_matrix": W.tolist()}))

        with pytest.raises(HTTPException) as exc:
            srv.best_fit(APPLIES_CASE, TOOTH, BestFitIn())
        assert exc.value.status_code == 409
        assert "too little scan surface" in exc.value.detail


class TestAlignmentProofArtifact:
    """The proof exists for sites a human moved, and only for those."""

    def _proof(self, out: Path, case_id: str) -> Path:
        return _pkg(out, case_id) / f"{case_id}-{TOOTH}-alignment-proof.png"

    def test_a_clean_shipped_package_carries_no_proof(self, applies_out):
        # the fixture is the package the automatic run emitted — nothing here was
        # adjusted, so there is nothing to prove
        assert not self._proof(applies_out, APPLIES_CASE).exists()
        manifest = json.loads((_pkg(applies_out, APPLIES_CASE)
                               / f"{APPLIES_CASE}-manifest.json").read_text())
        assert not [f for f in manifest["files"] if "alignment-proof" in f["name"]]

    @pytest.mark.parametrize("adjust", [
        pytest.param(lambda: srv.best_fit(APPLIES_CASE, TOOTH, BestFitIn()),
                     id="best-fit"),
        pytest.param(lambda: srv.nudge_rotation(APPLIES_CASE, TOOTH,
                                                NudgeIn(delta_deg=3.0)),
                     id="nudge"),
    ])
    def test_every_adjustment_emits_the_proof_into_package_and_manifest(
        self, applies_out, adjust
    ):
        import hashlib

        out = adjust()
        proof = self._proof(applies_out, APPLIES_CASE)
        assert proof.name in out["files"]
        assert proof.is_file() and proof.stat().st_size > 0

        manifest_path = (_pkg(applies_out, APPLIES_CASE)
                         / f"{APPLIES_CASE}-manifest.json")
        files = {f["name"]: f for f in json.loads(manifest_path.read_text())["files"]}
        assert proof.name in files, "the proof is not in the hashed manifest"
        assert files[proof.name]["sha256"] == \
            hashlib.sha256(proof.read_bytes()).hexdigest()
        # the re-emitted deliverables were re-hashed too — an adjustment used to leave
        # the manifest claiming the pre-adjustment bytes
        for name in (f"{APPLIES_CASE}-{TOOTH}-healingcap-aligned.stl",
                     f"{APPLIES_CASE}-{TOOTH}-implant.json"):
            p = _pkg(applies_out, APPLIES_CASE) / name
            assert files[name]["sha256"] == hashlib.sha256(p.read_bytes()).hexdigest()

    def test_the_provenance_record_is_append_only(self, applies_out):
        srv.nudge_rotation(APPLIES_CASE, TOOTH, NudgeIn(delta_deg=3.0))
        srv.best_fit(APPLIES_CASE, TOOTH, BestFitIn())
        adjustments = _implant(applies_out, APPLIES_CASE)["adjustments"]
        assert [a["operation"] for a in adjustments] == ["nudge-rotation", "best-fit"]
        assert all("this API captures no identity" in a["who"] for a in adjustments)
        assert "rotated +3.0" in adjustments[0]["detail"]
        assert "matching diameter" in adjustments[1]["detail"]
        assert all(a["ts"] for a in adjustments)

    def test_a_refused_adjustment_writes_no_proof(self, refuses_out):
        with pytest.raises(HTTPException):
            srv.best_fit(REFUSES_CASE, TOOTH, BestFitIn())
        assert not self._proof(refuses_out, REFUSES_CASE).exists()
        assert "adjustments" not in _implant(refuses_out, REFUSES_CASE)

    def test_the_proof_survives_a_package_with_no_manifest(self, applies_out):
        # packages emitted before the manifest existed must still accept an adjustment
        (_pkg(applies_out, APPLIES_CASE) / f"{APPLIES_CASE}-manifest.json").unlink()
        out = srv.best_fit(APPLIES_CASE, TOOTH, BestFitIn())
        assert self._proof(applies_out, APPLIES_CASE).is_file()
        assert out["files"][-1].endswith("-alignment-proof.png")


@pytest.mark.slow
def test_the_proof_draws_the_adjusted_pose_not_the_shipped_one(applies_out):
    """The picture must show what was ADOPTED. Rendering is compared through the
    renderer's own crop: the proof is drawn at the candidate pose, so a proof rendered
    at the pre-adjustment pose must differ byte-wise from the emitted one."""
    from case_prep.adapters.qc_render import render_alignment_proof

    _pkgdir, _ip, rec, template, frame, origin, L, t_before = \
        srv._load_rotation_site(APPLIES_CASE, TOOTH)
    srv.best_fit(APPLIES_CASE, TOOTH, BestFitIn())
    _p, _i, rec_after, _t, _f, _o, _L, t_after = \
        srv._load_rotation_site(APPLIES_CASE, TOOTH)
    assert not np.allclose(t_before, t_after)

    stale = render_alignment_proof("stale", TOOTH, L, t_before, template,
                                   rec_after["adjustments"], applies_out)
    fresh = render_alignment_proof("fresh", TOOTH, L, t_after, template,
                                   rec_after["adjustments"], applies_out)
    assert stale.read_bytes() != fresh.read_bytes()
    assert isinstance(trimesh.load(
        _pkg(applies_out, APPLIES_CASE)
        / f"{APPLIES_CASE}-{TOOTH}-healingcap-aligned.stl", force="mesh"),
        trimesh.Trimesh)
