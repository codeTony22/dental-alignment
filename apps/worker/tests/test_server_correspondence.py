"""MANUAL CORRESPONDENCE — mark the feature on the LIBRARY PART and the same feature on
the SCAN (client ask 2026-07-24, with screenshots).

Two contracts live here. The part-annotation endpoints
(GET/PUT/DELETE /api/library/{model}/{variant}/features) let a part be marked ONCE and
reused by every case that ships it — auto-seeded from the machine's own reading, never a
blank page. Then POST .../sites/{tooth}/align-to-correspondence rotates the seated cap so
the NAMED pairs meet: explicit, so it cannot bind the operator's click to the wrong code
feature the way nearest-match can, and usable where the automatic clock reader has no
evidence at all — cap7030, the acceptance case, whose half-occluded ring reads
``evidence: none`` to this day.

The rotation is still a PROPOSAL: refusals are 409s that leave every shipped artifact
byte-identical, adoptions re-emit the site's record and land in run-history.jsonl.
Handlers are called directly against the real live-demo artifacts — the pattern of
tests/test_server_align_mark.py.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import case_prep.server as srv
from case_prep.domain.clock_signature import (scan_rim_centre, template_signature,
                                              wrap_deg)
from case_prep.domain.part_features import auto_features, template_rim_centre
from case_prep.pipeline.auto_flow import _crowns_frame
from case_prep.server import AlignToCorrespondenceIn, PartFeaturesIn

CASE_ID = "cap7030-zimmer-4.5"
MODEL, VARIANT, TOOTH = "zimmer-4.5", "7030", 29
REAL_OUT = srv.OUT    # captured at import, before any monkeypatching
REAL_DATA = srv.DATA


@pytest.fixture()
def demo_out(tmp_path, monkeypatch):
    """A disposable copy of the case's live-demo artifacts, so a correspondence never
    mutates the real demo package."""
    src = REAL_OUT / CASE_ID
    if CASE_ID not in srv.CASES or not (src / "package").exists():
        pytest.skip("cap7030 live-demo artifacts not present on this machine")
    shutil.copytree(src, tmp_path / CASE_ID)
    monkeypatch.setattr(srv, "OUT", tmp_path)
    return tmp_path


@pytest.fixture()
def demo_out_for(tmp_path, monkeypatch):
    """The same disposable copy, for any case — the no-evidence acceptance sites live in
    two different demo cases."""
    def _prepare(case_id: str):
        src = REAL_OUT / case_id
        if case_id not in srv.CASES or not (src / "package").exists():
            pytest.skip(f"{case_id} live-demo artifacts not present on this machine")
        shutil.copytree(src, tmp_path / case_id)
        monkeypatch.setattr(srv, "OUT", tmp_path)
        return tmp_path
    return _prepare


@pytest.fixture()
def library_root(tmp_path, monkeypatch):
    """A disposable data root whose catalog is the REAL parts (symlinked, so the
    features read are the real ones) but whose annotations directory is throwaway —
    persisting a mark must never write into the doctor's data root during a test run."""
    caps = REAL_DATA / "library/caps" / MODEL
    if not caps.is_dir():
        pytest.skip("the real cap library is not present on this machine")
    root = tmp_path / "data"
    mirror = root / "library/caps" / MODEL
    mirror.mkdir(parents=True)
    for stl in sorted(caps.glob("*.stl")):
        (mirror / stl.name).symlink_to(stl.resolve())
    monkeypatch.setattr(srv, "DATA", root)
    return root


def _implant(out: Path) -> dict:
    return json.loads(
        (out / CASE_ID / "package" / f"{CASE_ID}-{TOOTH}-implant.json").read_text())


def _events(out: Path):
    hist = out / "run-history.jsonl"
    if not hist.exists():
        return []
    return [json.loads(ln) for ln in hist.read_text().strip().splitlines()
            if json.loads(ln).get("event") == "align-to-correspondence"]


def _site_geometry(case_id: str = CASE_ID, tooth: int = TOOTH):
    """The shipped pose in the site-local frame plus the clock signature and the measured
    scan rim centre — recomputed here the same deterministic way the server does, so the
    test can CONSTRUCT a scan click at an exactly-known azimuth."""
    cfg = srv.CASES[case_id]
    scan = srv._scan_mesh(cfg)
    rec = json.loads((REAL_OUT / case_id / "package"
                      / f"{case_id}-{tooth}-implant.json").read_text())
    # the library is resolved from the SHIPPED record's own model (the run's explicit
    # selection), the same way the server's re-pose path does it since 2026-07-25
    library = srv._library_for(cfg, rec["implant_model"], [rec["variant_code"]])
    spec = next(sp for sp in library.specs if sp.variant == rec["variant_code"])
    template = library.template(spec)
    sig = template_signature(template)
    pts = np.asarray(scan.vertices, float)
    frame, origin, _axis = _crowns_frame(pts, np.asarray(scan.vertex_normals, float))
    L = (pts - origin) @ frame
    W = np.asarray(rec["pose_matrix"], float)
    t_now = np.eye(4)
    t_now[:3, :3] = frame.T @ W[:3, :3]
    t_now[:3, 3] = frame.T @ (W[:3, 3] - origin)
    crop = L[np.linalg.norm(L[:, :2] - t_now[:2, 3], axis=1) < 8.0]
    canon = (crop - t_now[:3, 3]) @ t_now[:3, :3]
    c0 = scan_rim_centre(canon, sig.ztop, sig.rmax)
    return template, sig, frame, origin, t_now, c0


def _scan_click_at(azimuth_deg: float, case_id: str = CASE_ID, tooth: int = TOOTH):
    """A world-coordinate click on the scanned cap's coded band at an exactly-known
    azimuth about the measured rim centre — the inverse of the server's click mapping."""
    _template, sig, frame, origin, t_now, c0 = _site_geometry(case_id, tooth)
    a = np.radians(azimuth_deg)
    r = 0.6 * sig.rmax  # mid coded band
    p_canon = np.array([c0[0] + r * np.cos(a), c0[1] + r * np.sin(a), sig.ztop - 0.3])
    p_local = t_now[:3, :3] @ p_canon + t_now[:3, 3]
    return (origin + frame @ p_local).tolist()


def _site_features(case_id: str = CASE_ID, tooth: int = TOOTH):
    template, *_ = _site_geometry(case_id, tooth)
    return {f.id: f for f in auto_features(template)}


def _pair(feature_id: str, azimuth_deg: float, case_id: str = CASE_ID,
          tooth: int = TOOTH) -> dict:
    return {"feature_id": feature_id,
            "scan_point": _scan_click_at(azimuth_deg, case_id, tooth)}


def _part_point_at(azimuth_deg: float, radius_mm=None):
    """A canonical-frame click on the LIBRARY PART at an exactly-known azimuth about the
    part's own rim centre — the free-point half of a pair (client ask 2026-07-26), built
    the same way the server measures it (template_rim_centre + atan2)."""
    template, sig, *_rest = _site_geometry()
    centre = template_rim_centre(template)
    r = 0.6 * sig.rmax if radius_mm is None else radius_mm
    a = np.radians(azimuth_deg)
    return [float(centre[0] + r * np.cos(a)), float(centre[1] + r * np.sin(a)),
            float(sig.ztop)]


def _free_pair(part_azimuth_deg: float, scan_azimuth_deg: float,
               radius_mm=None) -> dict:
    return {"part_point": _part_point_at(part_azimuth_deg, radius_mm),
            "scan_point": _scan_click_at(scan_azimuth_deg)}


# --- the part-annotation endpoints ----------------------------------------------------

class TestPartFeatureEndpoints:
    def test_get_auto_seeds_an_unmarked_part_without_writing_anything(self, library_root):
        out = srv.library_features(MODEL, VARIANT)
        assert out["model"] == MODEL and out["variant"] == VARIANT
        assert out["auto_seeded"] is True
        assert out["revised_at"] is None
        kinds = [f["kind"] for f in out["features"]]
        assert kinds.count("channel") == 1 and kinds.count("trench") == 3
        assert all(f["source"] == "auto" for f in out["features"])
        assert not (library_root / "library/annotations").exists(), \
            "a read must not create an annotation — the seed is derived, not stored"

    def test_unknown_part_404s(self, library_root):
        with pytest.raises(HTTPException) as exc:
            srv.library_features(MODEL, "9999")
        assert exc.value.status_code == 404

    def test_put_persists_the_operators_marks_and_get_returns_them(self, library_root):
        auto = {f["id"]: f for f in srv.library_features(MODEL, VARIANT)["features"]}
        put = srv.put_library_features(MODEL, VARIANT, PartFeaturesIn(features=[
            {"kind": "trench", "azimuth_deg": auto["trench-02"]["azimuth_deg"]},
            {"kind": "notch", "azimuth_deg": 45.0}]))
        assert put["auto_seeded"] is False and put["revised_at"] is not None
        assert [f["source"] for f in put["features"]] == ["operator", "operator"]

        path = library_root / "library/annotations" / MODEL / f"{VARIANT}.json"
        assert path.exists(), "the mark must survive the process — that IS the flow"
        stored = json.loads(path.read_text())
        assert stored["model"] == MODEL and stored["variant"] == VARIANT
        assert [f["kind"] for f in stored["features"]] == ["trench", "notch"]

        again = srv.library_features(MODEL, VARIANT)
        assert again["auto_seeded"] is False
        assert again["features"] == put["features"]
        assert again["revised_at"] == put["revised_at"]

    def test_a_clicked_mark_snaps_to_the_machines_own_feature(self, library_root):
        """The reconciliation that keeps a human mark and the clock instrument talking
        about the same cutout: a click 4° off trench-02 is stored AS trench-02."""
        template = srv._catalog_template(MODEL, VARIANT)
        target = next(f for f in auto_features(template) if f.id == "trench-02")
        c = template_rim_centre(template)
        a = np.radians(target.azimuth_deg + 4.0)
        click = [float(c[0] + target.radius_mm * np.cos(a)),
                 float(c[1] + target.radius_mm * np.sin(a)), target.z_mm]
        out = srv.put_library_features(MODEL, VARIANT,
                                       PartFeaturesIn(features=[{"point": click}]))
        assert [f["id"] for f in out["features"]] == ["trench-02"]
        assert out["features"][0]["azimuth_deg"] == pytest.approx(
            round(target.azimuth_deg, 2))
        assert out["features"][0]["source"] == "operator"

    def test_azimuth_only_marks_land_on_the_coded_band(self, library_root):
        """A typed azimuth still needs a lever arm — it is placed at the mid-radius of
        the band the codes actually occupy, not at the axis."""
        sig = template_signature(srv._catalog_template(MODEL, VARIANT))
        out = srv.put_library_features(MODEL, VARIANT, PartFeaturesIn(
            features=[{"azimuth_deg": 12.0}]))
        f = out["features"][0]
        assert f["defines_rotation"] is True
        assert f["radius_mm"] == pytest.approx(0.61 * sig.rmax, abs=0.01)

    def test_delete_reverts_to_the_automatic_reading(self, library_root):
        srv.put_library_features(MODEL, VARIANT,
                                 PartFeaturesIn(features=[{"azimuth_deg": 12.0}]))
        dropped = srv.delete_library_features(MODEL, VARIANT)
        assert dropped["reverted"] is True
        assert dropped["auto_seeded"] is True
        assert [f["id"] for f in dropped["features"]] == \
            ["trench-01", "trench-02", "trench-03", "channel"]
        assert not (library_root / "library/annotations" / MODEL
                    / f"{VARIANT}.json").exists()
        # deleting an unmarked part is honest about having found nothing
        assert srv.delete_library_features(MODEL, VARIANT)["reverted"] is False

    def test_a_corrupt_annotation_is_loud_not_silently_re_seeded(self, library_root):
        path = library_root / "library/annotations" / MODEL / f"{VARIANT}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json")
        with pytest.raises(HTTPException) as exc:
            srv.library_features(MODEL, VARIANT)
        assert exc.value.status_code == 500
        assert "unreadable" in exc.value.detail

    def test_malformed_annotations_are_rejected(self, library_root):
        with pytest.raises(ValidationError, match="at least one feature"):
            PartFeaturesIn(features=[])
        with pytest.raises(ValidationError, match="exactly one of point or azimuth_deg"):
            PartFeaturesIn(features=[{"azimuth_deg": 10.0, "point": [1.0, 1.0, 1.0]}])
        with pytest.raises(ValidationError, match="exactly one of point or azimuth_deg"):
            PartFeaturesIn(features=[{"kind": "trench"}])
        with pytest.raises(ValidationError, match="unknown feature kind"):
            PartFeaturesIn(features=[{"kind": "sprocket", "azimuth_deg": 10.0}])
        with pytest.raises(ValidationError, match="capped at"):
            PartFeaturesIn(features=[{"azimuth_deg": float(i * 7)} for i in range(13)])
        with pytest.raises(ValidationError, match="triple"):
            PartFeaturesIn(features=[{"point": [1.0, 2.0]}])

    def test_two_marks_at_the_same_azimuth_are_a_contradiction(self, library_root):
        with pytest.raises(HTTPException) as exc:
            srv.put_library_features(MODEL, VARIANT, PartFeaturesIn(
                features=[{"azimuth_deg": 30.0}, {"azimuth_deg": 30.2}]))
        assert exc.value.status_code == 422
        assert "duplicate feature id" in exc.value.detail

    def test_a_plain_save_of_the_seed_changes_nothing_but_who_placed_it(self,
                                                                        library_root):
        """The annotator re-sends every mark it did not touch AS AN AZIMUTH, so saving an
        unedited seed must hand the part back unchanged. It did not: each mark was
        re-placed on the coded band's mid-radius, which renamed every stable id AND gave
        the CONCENTRIC screw bore a fabricated ~2.2mm lever arm — defines_rotation flipped
        False -> True and the axis became a nameable rotation anchor."""
        seed = srv.library_features(MODEL, VARIANT)["features"]
        saved = srv.put_library_features(MODEL, VARIANT, PartFeaturesIn(
            features=[{"kind": f["kind"], "azimuth_deg": f["azimuth_deg"]}
                      for f in seed]))["features"]
        assert [{**f, "source": "operator"} for f in seed] == saved
        bore = next(f for f in saved if f["kind"] == "channel")
        assert bore["id"] == "channel" and bore["defines_rotation"] is False

    def test_the_bore_cannot_be_laundered_into_an_anchor_by_saving(self, demo_out,
                                                                   library_root):
        """End to end, the harm the lever-arm rule exists to stop: after a plain save the
        bore must STILL be refused as one half of a correspondence. (It was not — it
        anchored a 33° rotation of the shipped part, gates and all, because the geometric
        gates judge whether the cap still sits on the scan, not whether the clock angle
        means anything.)"""
        seed = srv.library_features(MODEL, VARIANT)["features"]
        srv.put_library_features(MODEL, VARIANT, PartFeaturesIn(
            features=[{"kind": f["kind"], "azimuth_deg": f["azimuth_deg"]}
                      for f in seed]))
        with pytest.raises(HTTPException) as exc:
            srv.align_to_correspondence(CASE_ID, TOOTH, AlignToCorrespondenceIn(
                pairs=[_pair("channel", -140.0)]))
        assert exc.value.status_code == 422
        assert "names the axis, not a clock angle" in exc.value.detail
        assert _events(demo_out) == []

    def test_a_saved_mark_still_names_the_machines_own_cutout(self, demo_out,
                                                              library_root):
        """A persisted mark must keep naming the same cutout — the operator marks the
        catalog once and every later case aligns to it BY ID."""
        seed = srv.library_features(MODEL, VARIANT)["features"]
        srv.put_library_features(MODEL, VARIANT, PartFeaturesIn(
            features=[{"kind": f["kind"], "azimuth_deg": f["azimuth_deg"]}
                      for f in seed]))
        target = _site_features()["trench-02"]
        out = srv.align_to_correspondence(CASE_ID, TOOTH, AlignToCorrespondenceIn(
            pairs=[_pair("trench-02", wrap_deg(target.azimuth_deg + 7.0))]))
        assert out["applied_delta_deg"] == pytest.approx(7.0, abs=0.3)
        # ...and the residual is measured at the trench's OWN lever arm, not a band default
        assert out["pairs"][0]["residual_mm"] == 0.0

    def test_a_click_off_the_part_is_422_not_a_stored_guess(self, library_root):
        with pytest.raises(HTTPException) as exc:
            srv.put_library_features(MODEL, VARIANT, PartFeaturesIn(
                features=[{"point": [40.0, 40.0, 0.0]}]))
        assert exc.value.status_code == 422
        assert "not on this part" in exc.value.detail
        assert not (library_root / "library/annotations").exists()


# --- align-to-correspondence ----------------------------------------------------------

class TestCorrespondenceValidation:
    def test_empty_pairs_422s(self, demo_out):
        with pytest.raises(HTTPException) as exc:
            srv.align_to_correspondence(CASE_ID, TOOTH,
                                        AlignToCorrespondenceIn(pairs=[]))
        assert exc.value.status_code == 422
        assert "at least one correspondence" in exc.value.detail
        assert _events(demo_out) == []

    def test_unknown_feature_id_422s_and_names_the_known_ones(self, demo_out):
        with pytest.raises(HTTPException) as exc:
            srv.align_to_correspondence(CASE_ID, TOOTH, AlignToCorrespondenceIn(
                pairs=[_pair("trench-09", -130.0)]))
        assert exc.value.status_code == 422
        assert "'trench-09' is not a marked feature" in exc.value.detail
        assert "trench-01" in exc.value.detail  # the operator is told what IS available

    def test_far_scan_point_422s_and_is_side_effect_free(self, demo_out):
        implant = demo_out / CASE_ID / "package" / f"{CASE_ID}-{TOOTH}-implant.json"
        before = implant.read_bytes()
        pos = np.asarray(_implant(demo_out)["pose_matrix"], float)[:3, 3]
        far = (pos + np.array([0.0, 0.0, 50.0])).tolist()
        with pytest.raises(HTTPException) as exc:
            srv.align_to_correspondence(CASE_ID, TOOTH, AlignToCorrespondenceIn(
                pairs=[{"feature_id": "trench-02", "scan_point": far}]))
        assert exc.value.status_code == 422
        assert "within 15mm" in exc.value.detail
        assert implant.read_bytes() == before
        assert _events(demo_out) == []

    def test_one_feature_cannot_sit_at_two_places(self, demo_out):
        with pytest.raises(HTTPException) as exc:
            srv.align_to_correspondence(CASE_ID, TOOTH, AlignToCorrespondenceIn(
                pairs=[_pair("trench-02", -130.0), _pair("trench-02", -100.0)]))
        assert exc.value.status_code == 422
        assert "named twice" in exc.value.detail

    def test_the_concentric_channel_cannot_anchor_a_rotation(self, demo_out):
        """The bore is seeded and listed because the operator sees it — but its mouth is
        concentric with the rim (0.03mm on this part), so it names the AXIS, not a clock
        angle. Refusing is the honest answer; rotating to it would be noise."""
        with pytest.raises(HTTPException) as exc:
            srv.align_to_correspondence(CASE_ID, TOOTH, AlignToCorrespondenceIn(
                pairs=[_pair("channel", -130.0)]))
        assert exc.value.status_code == 422
        assert "names the axis, not a clock angle" in exc.value.detail
        assert _events(demo_out) == []

    def test_unknown_tooth_404s(self, demo_out):
        with pytest.raises(HTTPException) as exc:
            srv.align_to_correspondence(CASE_ID, 99, AlignToCorrespondenceIn(
                pairs=[{"feature_id": "trench-02", "scan_point": [0.0, 0.0, 0.0]}]))
        assert exc.value.status_code == 404

    def test_malformed_scan_point_is_rejected(self):
        with pytest.raises(ValidationError, match="triple"):
            AlignToCorrespondenceIn(pairs=[{"feature_id": "a", "scan_point": [1.0, 2.0]}])
        with pytest.raises(ValidationError, match="finite"):
            AlignToCorrespondenceIn(pairs=[{"feature_id": "a",
                                            "scan_point": [float("inf"), 0.0, 0.0]}])


class TestOnePairCorrespondence:
    def test_the_named_feature_comes_to_the_mark_in_the_right_direction(self, demo_out):
        """A click 9° CCW of the NAMED feature must rotate the pose by ~+9° about the
        part's own axis, with the full nudge-grade re-emit + audit trail. The expected
        delta is constructed here from the feature's own azimuth — not read back out of
        the server's answer."""
        target = _site_features()["trench-02"]
        offset = 9.0
        click_az = wrap_deg(target.azimuth_deg + offset)
        before = _implant(demo_out)
        cap = demo_out / CASE_ID / "package" / f"{CASE_ID}-{TOOTH}-healingcap-aligned.stl"
        cap_before = cap.read_bytes()

        out = srv.align_to_correspondence(CASE_ID, TOOTH, AlignToCorrespondenceIn(
            pairs=[_pair("trench-02", click_az)]))

        assert out["tooth"] == TOOTH
        assert out["applied_delta_deg"] == pytest.approx(offset, abs=0.3)
        assert out["residual_rms_mm"] == 0.0, "a single pair is satisfied exactly"
        assert len(out["pairs"]) == 1
        row = out["pairs"][0]
        assert row["feature_id"] == "trench-02"
        assert row["feature_azimuth_deg"] == pytest.approx(target.azimuth_deg, abs=0.1)
        assert row["click_azimuth_deg"] == pytest.approx(click_az, abs=0.3)
        assert row["delta_deg"] == pytest.approx(offset, abs=0.3)
        assert row["residual_deg"] == 0.0
        assert out["stability_excess_mm"] <= srv._NUDGE_STABILITY_BOUND_MM
        assert "notch_shift_deg" in out["clocking"]

        after = _implant(demo_out)
        R0 = np.asarray(before["pose_matrix"], float)[:3, :3]
        R1 = np.asarray(after["pose_matrix"], float)[:3, :3]
        assert float(R0[:, 2] @ R1[:, 2]) > 0.999, "the part's own axis must not move"
        rel = R0.T @ R1
        angle = float(np.degrees(np.arctan2(rel[1, 0], rel[0, 0])))
        assert angle == pytest.approx(offset, abs=0.4)
        assert after["nudge"]["cumulative_deg"] == out["cumulative_deg"]
        assert cap.read_bytes() != cap_before, "the viewer's STL must be re-emitted"

        run = json.loads((demo_out / CASE_ID / "run.json").read_text())
        run_row = next(r for r in run["summary"]["sites"] if r["tooth"] == TOOTH)
        assert run_row["nudge"]["cumulative_deg"] == out["cumulative_deg"]

        events = _events(demo_out)
        assert [e["outcome"] for e in events] == ["applied"]
        assert events[0]["pairs"] == [{"feature_id": "trench-02",
                                       "scan_point": pytest.approx(
                                           [round(c, 3) for c in
                                            _scan_click_at(click_az)], abs=0.01)}]
        assert events[0]["applied_delta_deg"] == out["applied_delta_deg"]
        assert events[0]["residuals"] == out["pairs"]
        assert events[0]["residual_rms_mm"] == out["residual_rms_mm"]

    def test_naming_the_feature_overrides_what_nearest_match_would_pick(self, demo_out):
        """THE limitation this flow exists to fix. A click at -160° sits nearer
        trench-01 (-177.0) than trench-02 (-136.0), so align-to-mark would rotate by
        +17°; naming trench-02 rotates by -24° instead — the operator's correspondence,
        not the machine's guess."""
        feats = _site_features()
        click_az = -160.0
        nearest = min((abs(wrap_deg(click_az - f.azimuth_deg)), f.id)
                      for f in feats.values() if f.kind == "trench")[1]
        assert nearest == "trench-01", "the geometry this test relies on has moved"
        named_delta = wrap_deg(click_az - feats["trench-02"].azimuth_deg)
        nearest_delta = wrap_deg(click_az - feats["trench-01"].azimuth_deg)

        out = srv.align_to_correspondence(CASE_ID, TOOTH, AlignToCorrespondenceIn(
            pairs=[_pair("trench-02", click_az)]))
        assert out["applied_delta_deg"] == pytest.approx(named_delta, abs=0.3)
        assert abs(out["applied_delta_deg"] - nearest_delta) > 10.0, \
            "the endpoint fell back to the nearest feature — the ambiguity is back"

    def test_the_acceptance_case_works_where_the_clock_reader_has_none(self, demo_out):
        """cap7030: the half-occluded ring gives the automatic coded-cutout reader NO
        evidence, so the site ships rotation_unverified. A single named correspondence
        still produces a gated, audited, re-emitted rotation — that is the whole point
        of the manual fallback."""
        pkg, _ip, _rec, template, _frame, _origin, L, t0 = \
            srv._load_rotation_site(CASE_ID, TOOTH)
        assert srv._read_clock_at(L, template, t0, t0).has_evidence is False, \
            "cap7030 is the acceptance case BECAUSE its clock reading has no evidence"

        target = _site_features()["trench-03"]
        out = srv.align_to_correspondence(CASE_ID, TOOTH, AlignToCorrespondenceIn(
            pairs=[_pair("trench-03", wrap_deg(target.azimuth_deg - 6.0))]))
        assert out["applied_delta_deg"] == pytest.approx(-6.0, abs=0.3)
        # GATED: the certification bound was measured, not skipped
        assert out["stability_excess_mm"] is not None
        assert out["stability_excess_mm"] <= srv._NUDGE_STABILITY_BOUND_MM
        # VERIFIED: the codes were re-read at the adopted pose for the operator to judge
        assert set(out["clocking"]) >= {"notch_shift_deg", "notch_corr",
                                        "notch_prominence"}
        # AUDITED: the correspondence is on the provenance stream
        assert [e["outcome"] for e in _events(demo_out)] == ["applied"]
        # SHIPPED: the deliverables the viewer loads were re-emitted
        assert (pkg / f"{CASE_ID}-{TOOTH}-healingcap-aligned.stl").exists()
        # ...and the ALIGNMENT PROOF (2026-07-25): an operator-adjusted pose now ships
        # its own picture with the provenance printed on it
        assert out["files"] == [f"{CASE_ID}-{TOOTH}-healingcap-aligned.stl",
                                f"{CASE_ID}-{TOOTH}-implant.json",
                                f"{CASE_ID}-{TOOTH}-alignment-proof.png"]


class TestNoEvidenceAcceptanceSites:
    """The two sites the flow was commissioned for: their half-occluded rings give the
    automatic coded-cutout reader NO evidence, so nearest-match has nothing to steer by
    and the operator's named correspondence is the only route to a certified rotation."""

    @pytest.mark.parametrize("case_id,tooth,feature_id",
                             [("cap7030-zimmer-4.5", 29, "trench-02"),
                              ("zimmer-4.5", 7, "trench-01")])
    @pytest.mark.slow
    def test_a_named_pair_produces_a_gated_audited_rotation(self, demo_out_for,
                                                            case_id, tooth, feature_id):
        out_root = demo_out_for(case_id)
        _pkg, _ip, _rec, template, _frame, _origin, L, t0 = \
            srv._load_rotation_site(case_id, tooth)
        assert srv._read_clock_at(L, template, t0, t0).has_evidence is False, \
            f"{case_id}/{tooth} is an acceptance site BECAUSE its clock read is blind"

        target = _site_features(case_id, tooth)[feature_id]
        offset = 8.0
        out = srv.align_to_correspondence(case_id, tooth, AlignToCorrespondenceIn(
            pairs=[_pair(feature_id, wrap_deg(target.azimuth_deg + offset),
                         case_id, tooth)]))
        assert out["applied_delta_deg"] == pytest.approx(offset, abs=0.3)
        assert out["stability_excess_mm"] <= srv._NUDGE_STABILITY_BOUND_MM
        assert out["residual_rms_mm"] == 0.0

        after = json.loads((out_root / case_id / "package"
                            / f"{case_id}-{tooth}-implant.json").read_text())
        before = json.loads((REAL_OUT / case_id / "package"
                             / f"{case_id}-{tooth}-implant.json").read_text())
        rel = (np.asarray(before["pose_matrix"], float)[:3, :3].T
               @ np.asarray(after["pose_matrix"], float)[:3, :3])
        assert float(np.degrees(np.arctan2(rel[1, 0], rel[0, 0]))) == \
            pytest.approx(offset, abs=0.4)
        events = [json.loads(ln) for ln in
                  (out_root / "run-history.jsonl").read_text().strip().splitlines()]
        assert [e["event"] for e in events] == ["align-to-correspondence"]
        assert events[0]["outcome"] == "applied"


class TestMultiPairCorrespondence:
    def test_best_fit_rotation_and_per_pair_residuals(self, demo_out):
        """Two disagreeing pairs (+10° and +6°) resolve to their circular mean, +8°,
        and each pair reports the 2° it is off — in MILLIMETRES at its own radius, the
        number the operator can actually judge ("your marks agree to X mm")."""
        feats = _site_features()
        a, b = feats["trench-01"], feats["trench-03"]
        out = srv.align_to_correspondence(CASE_ID, TOOTH, AlignToCorrespondenceIn(
            pairs=[_pair("trench-01", wrap_deg(a.azimuth_deg + 10.0)),
                   _pair("trench-03", wrap_deg(b.azimuth_deg + 6.0))]))

        assert out["applied_delta_deg"] == pytest.approx(8.0, abs=0.3)
        by_id = {r["feature_id"]: r for r in out["pairs"]}
        assert by_id["trench-01"]["delta_deg"] == pytest.approx(10.0, abs=0.3)
        assert by_id["trench-03"]["delta_deg"] == pytest.approx(6.0, abs=0.3)
        assert by_id["trench-01"]["residual_deg"] == pytest.approx(2.0, abs=0.3)
        assert by_id["trench-03"]["residual_deg"] == pytest.approx(-2.0, abs=0.3)
        for feature, row in ((a, by_id["trench-01"]), (b, by_id["trench-03"])):
            assert row["residual_mm"] == pytest.approx(
                np.radians(2.0) * feature.radius_mm, abs=0.01)
        assert out["residual_rms_mm"] == pytest.approx(
            float(np.sqrt(np.mean([r["residual_mm"] ** 2 for r in out["pairs"]]))),
            abs=1e-3)
        assert out["residual_rms_mm"] > 0.0

        # the adopted pose really is the best fit, not the first pair's answer
        after = _implant(demo_out)
        before = json.loads((REAL_OUT / CASE_ID / "package"
                             / f"{CASE_ID}-{TOOTH}-implant.json").read_text())
        rel = (np.asarray(before["pose_matrix"], float)[:3, :3].T
               @ np.asarray(after["pose_matrix"], float)[:3, :3])
        assert float(np.degrees(np.arctan2(rel[1, 0], rel[0, 0]))) == \
            pytest.approx(8.0, abs=0.4)

    def test_agreeing_pairs_report_a_clean_qc_number(self, demo_out):
        feats = _site_features()
        out = srv.align_to_correspondence(CASE_ID, TOOTH, AlignToCorrespondenceIn(
            pairs=[_pair(fid, wrap_deg(feats[fid].azimuth_deg + 5.0))
                   for fid in ("trench-01", "trench-02", "trench-03")]))
        assert out["applied_delta_deg"] == pytest.approx(5.0, abs=0.3)
        assert out["residual_rms_mm"] < 0.02, \
            "marks placed at the same offset must agree to well under a tenth of a mm"

    def test_the_circular_mean_survives_the_180_degree_seam(self, demo_out):
        """Deltas of +179° and -179° average to 180°, not 0° — an arithmetic mean would
        silently ship the part a half-turn out."""
        feats = _site_features()
        a, b = feats["trench-01"], feats["trench-03"]
        pairs = [_pair("trench-01", wrap_deg(a.azimuth_deg + 179.0)),
                 _pair("trench-03", wrap_deg(b.azimuth_deg - 179.0))]
        try:
            out = srv.align_to_correspondence(CASE_ID, TOOTH,
                                              AlignToCorrespondenceIn(pairs=pairs))
        except HTTPException as exc:
            # a half-turn may well fail the certification gates on this site — what must
            # NOT happen is a ~0° "agreement" sailing through
            assert exc.status_code == 409
            applied = float(exc.detail.split("rotation")[1].split("°")[0])
        else:
            applied = out["applied_delta_deg"]
        assert abs(abs(applied) - 180.0) < 1.0, \
            f"circular mean collapsed to {applied:.1f}° across the seam"


class TestCorrespondenceRefusal:
    def test_refused_rotation_is_side_effect_free_with_reason(self, demo_out, monkeypatch):
        """The gates judge this proposal exactly as they judge a nudge — a stability
        excess over the bound 409s with the server's own sentence and leaves every
        artifact byte-identical."""
        target = _site_features()["trench-02"]
        before = _implant(demo_out)
        cap = demo_out / CASE_ID / "package" / f"{CASE_ID}-{TOOTH}-healingcap-aligned.stl"
        cap_before = cap.read_bytes()
        run_before = (demo_out / CASE_ID / "run.json").read_bytes()
        monkeypatch.setattr(srv, "_ring_fixed_candidate",
                            lambda *a, **k: (np.eye(4), 0.9))

        with pytest.raises(HTTPException) as exc:
            srv.align_to_correspondence(CASE_ID, TOOTH, AlignToCorrespondenceIn(
                pairs=[_pair("trench-02", wrap_deg(target.azimuth_deg + 9.0))]))
        assert exc.value.status_code == 409
        assert "align-to-correspondence rotation" in exc.value.detail
        assert "refused" in exc.value.detail and "0.90mm" in exc.value.detail

        assert _implant(demo_out) == before
        assert cap.read_bytes() == cap_before
        assert (demo_out / CASE_ID / "run.json").read_bytes() == run_before
        events = _events(demo_out)
        assert [e["outcome"] for e in events] == ["refused"]
        assert events[0]["pairs"][0]["feature_id"] == "trench-02"
        assert events[0]["residuals"][0]["residual_deg"] == 0.0
        assert events[0]["cumulative_deg"] is None  # nothing was adopted

    def test_an_unmeasurable_ring_is_refused_not_forced(self, demo_out, monkeypatch):
        target = _site_features()["trench-02"]
        monkeypatch.setattr(srv, "_ring_fixed_candidate", lambda *a, **k: None)
        with pytest.raises(HTTPException) as exc:
            srv.align_to_correspondence(CASE_ID, TOOTH, AlignToCorrespondenceIn(
                pairs=[_pair("trench-02", wrap_deg(target.azimuth_deg + 9.0))]))
        assert exc.value.status_code == 409
        assert "rim ring is unmeasurable" in exc.value.detail


class TestFreePointPairs:
    """FREE POINTS (client ask 2026-07-26): a pair may name an ARBITRARY point on the
    part instead of a detected feature — RealGUIDE's numbered clicks. On catalogs whose
    detector reads a single rotation-defining feature the feature-only contract stranded
    the operator at one pair; a free point is measured about the same rim centre a
    feature azimuth is named about and rides the identical judged rotation path."""

    def test_a_free_pair_is_accepted_and_rotates_like_a_named_feature(self, demo_out):
        out = srv.align_to_correspondence(CASE_ID, TOOTH, AlignToCorrespondenceIn(
            pairs=[_free_pair(-150.0, -141.0)]))
        assert out["applied_delta_deg"] == pytest.approx(9.0, abs=0.3)
        assert out["residual_rms_mm"] == 0.0, "a single pair is satisfied exactly"
        row = out["pairs"][0]
        assert row["feature_id"] == "point-1"
        assert row["feature_azimuth_deg"] == pytest.approx(-150.0, abs=0.1)
        # the rotation went through the same gates as a feature pair, and shipped
        assert out["stability_excess_mm"] <= srv._NUDGE_STABILITY_BOUND_MM
        assert [e["outcome"] for e in _events(demo_out)] == ["applied"]

    def test_mixed_feature_and_free_pairs_take_the_circular_mean(self, demo_out):
        target = _site_features()["trench-02"]
        out = srv.align_to_correspondence(CASE_ID, TOOTH, AlignToCorrespondenceIn(
            pairs=[_pair("trench-02", wrap_deg(target.azimuth_deg + 10.0)),
                   _free_pair(40.0, 46.0)]))
        assert out["applied_delta_deg"] == pytest.approx(8.0, abs=0.3)
        by_id = {r["feature_id"]: r for r in out["pairs"]}
        assert set(by_id) == {"trench-02", "point-1"}
        assert by_id["trench-02"]["delta_deg"] == pytest.approx(10.0, abs=0.3)
        assert by_id["point-1"]["delta_deg"] == pytest.approx(6.0, abs=0.3)

    def test_a_free_point_inside_the_lever_arm_is_refused(self, demo_out):
        """The same honesty the concentric channel gets: inside 0.5mm a click names the
        AXIS, not a clock angle — free-hand placement must not launder a lever arm the
        geometry does not have."""
        with pytest.raises(HTTPException) as exc:
            srv.align_to_correspondence(CASE_ID, TOOTH, AlignToCorrespondenceIn(
                pairs=[_free_pair(-140.0, -140.0, radius_mm=0.3)]))
        assert exc.value.status_code == 422
        assert "names the axis, not a clock angle" in exc.value.detail
        assert _events(demo_out) == []

    def test_a_pair_needs_exactly_one_part_half(self):
        with pytest.raises(ValidationError,
                           match="exactly one of feature_id or part_point"):
            AlignToCorrespondenceIn(pairs=[{"scan_point": [0.0, 0.0, 0.0]}])
        with pytest.raises(ValidationError,
                           match="exactly one of feature_id or part_point"):
            AlignToCorrespondenceIn(pairs=[{"feature_id": "trench-01",
                                            "part_point": [1.0, 1.0, 1.0],
                                            "scan_point": [0.0, 0.0, 0.0]}])
        with pytest.raises(ValidationError, match="triple"):
            AlignToCorrespondenceIn(pairs=[{"part_point": [1.0],
                                            "scan_point": [0.0, 0.0, 0.0]}])
        with pytest.raises(ValidationError, match="finite"):
            AlignToCorrespondenceIn(pairs=[{"part_point": [float("nan"), 0.0, 0.0],
                                            "scan_point": [0.0, 0.0, 0.0]}])

    def test_the_audit_record_carries_the_positional_labels(self, demo_out):
        """Two free points are LEGAL (the duplicate check names features only) and land
        on the provenance stream as 'point-1'/'point-2' in click order, each with the
        part click itself — run-history.jsonl stays replayable without the annotation."""
        out = srv.align_to_correspondence(CASE_ID, TOOTH, AlignToCorrespondenceIn(
            pairs=[_free_pair(-150.0, -145.0), _free_pair(30.0, 35.0)]))
        assert [r["feature_id"] for r in out["pairs"]] == ["point-1", "point-2"]
        (event,) = _events(demo_out)
        assert event["outcome"] == "applied"
        assert [p.get("label") for p in event["pairs"]] == ["point-1", "point-2"]
        assert all("part_point" in p and "scan_point" in p for p in event["pairs"])
        assert [r["feature_id"] for r in event["residuals"]] == ["point-1", "point-2"]


class TestCorrespondenceUsesThePersistedAnnotation:
    def test_an_operator_marked_feature_anchors_the_rotation(self, demo_out,
                                                             library_root):
        """The productization point end to end: the part is marked ONCE (an operator
        feature the automatic reader never proposed), and a later case's site aligns to
        that mark by name."""
        srv.put_library_features(MODEL, VARIANT, PartFeaturesIn(
            features=[{"kind": "flat", "azimuth_deg": -60.0}]))
        [mark] = srv.library_features(MODEL, VARIANT)["features"]
        assert mark["id"] == "operator-300" and mark["source"] == "operator"

        out = srv.align_to_correspondence(CASE_ID, TOOTH, AlignToCorrespondenceIn(
            pairs=[_pair("operator-300", -53.0)]))
        assert out["applied_delta_deg"] == pytest.approx(7.0, abs=0.3)
        assert out["pairs"][0]["feature_id"] == "operator-300"

        # ...and the auto features it REPLACED are no longer nameable
        with pytest.raises(HTTPException) as exc:
            srv.align_to_correspondence(CASE_ID, TOOTH, AlignToCorrespondenceIn(
                pairs=[_pair("trench-02", -130.0)]))
        assert exc.value.status_code == 422
        assert "operator-300" in exc.value.detail
