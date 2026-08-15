"""RE-EMIT FROM PROVEN POSES — case_prep.application.emit (§10-AC, 2026-08-02).

The synthetic tests pin the REFUSALS (they fire before any mesh is parsed): the
explicit-selection gate keeps its verbatim sentence, and a re-emit without a readable
source package says so in stated words rather than guessing.

The slow test is the feature: a REAL source run's poses re-emitted with a DIFFERENT
construction part into a new directory. It pins the four §10-M hazard answers —
poses identical (nothing re-aligned), operator provenance copied forward and
re-hashed, the old vendor's scanbody name absent from the new package, and the
report naming its source run.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import trimesh

from case_prep.application.cases import CaseRecord, discover_cases
from case_prep.application.emit import emit_from_poses
from case_prep.application.run import RunRefused, RunSelection, run_case

REAL = Path(__file__).resolve().parents[1] / "data" / "real"
real_only = pytest.mark.skipif(not (REAL / "library").is_dir(),
                               reason="real data tree not present")


def _case(tmp_path: Path, sites=()) -> CaseRecord:
    return CaseRecord(
        id="case-x", doctor="Doctor X", jaw="upper",
        scan=tmp_path / "scan.stl", data_root=tmp_path,
        suggested_model=None, suggested_construction=None,
        suggested_sites=tuple(sites))


def _selection(**overrides) -> RunSelection:
    values = dict(model="neodent-gm",
                  construction_path="dess/neodent-gm-scanbody.stl",
                  variants={13: "5020"}, jaw=None, gingival_offset_mm=0.2)
    values.update(overrides)
    return RunSelection(**values)


class TestTheRefusalsFireBeforeAnyMesh:
    def test_the_explicit_selection_gate_keeps_its_sentence(self, tmp_path):
        with pytest.raises(RunRefused) as exc:
            emit_from_poses(_case(tmp_path), _selection(model=None),
                            tmp_path / "a", tmp_path / "b")
        assert "The software will not pick one for you" in str(exc.value)

    def test_a_missing_source_report_is_a_stated_refusal(self, tmp_path):
        (tmp_path / "a").mkdir()
        with pytest.raises(RunRefused) as exc:
            emit_from_poses(_case(tmp_path), _selection(),
                            tmp_path / "a", tmp_path / "b")
        assert "carries no report" in str(exc.value)

    def test_a_report_with_no_aligned_sites_is_a_stated_refusal(self, tmp_path):
        source = tmp_path / "a"
        source.mkdir()
        (source / "case-x-auto-report.json").write_text(json.dumps(
            {"sites": [{"tooth": 13, "error": "no seat"}]}))
        with pytest.raises(RunRefused) as exc:
            emit_from_poses(_case(tmp_path), _selection(),
                            source, tmp_path / "b")
        assert "nothing to re-emit" in str(exc.value)

    def test_a_row_without_its_implant_record_is_a_stated_refusal(self, tmp_path):
        source = tmp_path / "a"
        source.mkdir()
        (source / "case-x-auto-report.json").write_text(json.dumps(
            {"sites": [{"tooth": 13, "fit": {},
                        "variant": {"identified": "5020"}}]}))
        with pytest.raises(RunRefused) as exc:
            emit_from_poses(_case(tmp_path), _selection(),
                            source, tmp_path / "b")
        assert "implant record for tooth 13" in str(exc.value)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@real_only
@pytest.mark.slow  # one FULL source run + one re-emit (emission only) on real meshes
class TestReEmitOnTheRealTree:
    def test_a_part_change_re_emits_without_re_aligning(self, tmp_path, monkeypatch):
        cases = {c.id: c for c in discover_cases(REAL)}
        case = cases.get("neodent-gm") or cases.get("doctor-neodent-gm")
        assert case is not None, sorted(cases)
        teeth = [int(s["tooth"]) for s in case.suggested_sites][:1]
        assert teeth, "the real case carries no suggested sites"
        selection = RunSelection(
            model="neodent-gm",
            construction_path="dess/neodent-gm-scanbody.stl",
            variants={t: "5020" for t in teeth}, jaw=None,
            gingival_offset_mm=0.2)

        source_dir = tmp_path / "runs" / "source"
        source_dir.mkdir(parents=True)
        summary_a = run_case(case, selection, source_dir)
        tooth = teeth[0]

        # seed operator provenance onto the landed record — the thing a naive
        # re-emit would erase (§10-M hazard 1)
        record_path = source_dir / f"{case.id}-{tooth}-implant.json"
        record = json.loads(record_path.read_text())
        record["adjustments"] = [{"ts": "2026-08-02T00:00:00",
                                  "operation": "test-seeded",
                                  "who": "operator (no identity is captured)",
                                  "detail": "seeded by test_emit"}]
        record_path.write_text(json.dumps(record, indent=2))

        # seed re-apply receipts onto the source report — §10-AD's receipts must
        # ride a §10-AC re-emit, because the copied poses still stand on those acts
        source_report_path = source_dir / f"{case.id}-auto-report.json"
        source_report = json.loads(source_report_path.read_text())
        source_report["evidence_reapplied"] = [
            {"tooth": tooth, "kind": "mark", "applied_at": "2026-08-02T00:00:00",
             "outcome": "applied", "operation": "align-to-mark",
             "detail": "seeded by test_emit"}]
        source_report_path.write_text(json.dumps(source_report, indent=2))

        # a DIFFERENT part from a DIFFERENT vendor, and a different relief ask
        reemit_selection = RunSelection(
            model="neodent-gm",
            construction_path="atlantis/zimmer-4.5-scanbody.stl",
            variants={t: "5020" for t in teeth}, jaw=None,
            gingival_offset_mm=0.1)
        out_dir = tmp_path / "runs" / "reemitted"
        out_dir.mkdir(parents=True)

        # THE CALLER-PROVIDES ROUTE, PINNED DIRECTLY (boolean-engine plan 4c): the
        # re-emit lane holds every composite mesh in memory the instant it writes
        # it, so the load fallback (``output_package._facts_from_disk``) must never
        # fire — a call would mean facts were re-derived by re-parsing a file this
        # same call just wrote.
        import case_prep.adapters.output_package as _op
        fallback_calls: list = []
        original_fallback = _op._facts_from_disk
        monkeypatch.setattr(
            _op, "_facts_from_disk",
            lambda p: (fallback_calls.append(p), original_fallback(p))[1])

        summary_b = emit_from_poses(case, reemit_selection, source_dir, out_dir)

        assert fallback_calls == [], (
            "the re-emit lane must hand every artifact's facts straight from the "
            f"mesh it already holds — the load fallback fired for {fallback_calls}")

        # 1. NOTHING re-aligned: the pose travels bit-identically
        new_record = json.loads(
            (out_dir / f"{case.id}-{tooth}-implant.json").read_text())
        assert new_record["pose_matrix"] == record["pose_matrix"]

        # 2. provenance copied forward, and the manifest hash covers the rewrite
        assert new_record["adjustments"][0]["operation"] == "test-seeded"
        manifest = json.loads((out_dir / f"{case.id}-manifest.json").read_text())
        row = next(r for r in manifest["files"]
                   if r["name"] == f"{case.id}-{tooth}-implant.json")
        assert row["sha256"] == _sha256(
            out_dir / f"{case.id}-{tooth}-implant.json")

        # 3. the vendor rename leaves no stale scanbody behind
        names = {r["name"] for r in manifest["files"]}
        assert f"{case.id}-{tooth}-scanbody-atlantis.stl" in names
        assert f"{case.id}-{tooth}-scanbody-dess.stl" not in names
        assert not (out_dir / f"{case.id}-{tooth}-scanbody-dess.stl").exists()

        # 4b. PER-SITE RELIEF (§10-B/C): a site override rides the selection and
        # lands on that site's production row (single-site case: the one row)
        reemit_persite = RunSelection(
            model="neodent-gm",
            construction_path="dess/neodent-gm-scanbody.stl",
            variants={t: "5020" for t in teeth}, jaw=None,
            gingival_offset_mm=0.2,
            site_reliefs={tooth: 0.05})
        persite_dir = tmp_path / "runs" / "persite"
        persite_dir.mkdir(parents=True)
        summary_c = emit_from_poses(case, reemit_persite, source_dir, persite_dir)
        row_c = next(r for r in summary_c["sites"] if r["tooth"] == tooth)
        assert row_c["production"]["gingival_offset_requested_mm"] == 0.05
        assert fallback_calls == [], (
            "the per-site-relief re-emit must also hand its facts straight from "
            f"memory — the load fallback fired for {fallback_calls}")

        # 4. the receipt names its source and refreshes the product facts
        assert summary_b["emitted_from"] == "source"
        assert summary_b["mode"] == "reemit-from-poses"
        # 4c. and the source run's re-apply receipts RIDE it — a summary that
        # dropped them would deny evidence the copied poses embody (§10-AD×AC)
        assert summary_b["evidence_reapplied"][0]["detail"] == "seeded by test_emit"
        row_b = next(r for r in summary_b["sites"] if r["tooth"] == tooth)
        row_a = next(r for r in summary_a["sites"] if r["tooth"] == tooth)
        # pose/seat/clock facts verbatim; the product facts are the NEW part's
        assert row_b["fit"] == row_a["fit"]
        assert row_b["seat_method"] == row_a["seat_method"]
        assert row_b["guidance"]["level"] == row_a["guidance"]["level"]
        assert row_b["production"]["gingival_offset_mm"] <= 0.1 + 1e-9
        # the arch trio and the report are in the new package — the composite
        # files land under the SAME names now that they are true boolean unions
        # (§10-AT 3b), not the concatenations they used to be
        for name in (f"{case.id}-arch-with-healingcaps.stl",
                     f"{case.id}-arch-with-constructions.stl",
                     f"{case.id}-auto-report.json"):
            assert (out_dir / name).exists()

        # 5. THE SCANNED-CAP ARTIFACT (plan Stage 2 slice 2a) rides the re-emit too —
        # a part change owes the lab the same "what the scanner saw" file, even
        # though nothing realigned
        scanned_cap_name = f"{case.id}-{tooth}-scanned-cap.stl"
        assert scanned_cap_name in summary_b["package_files"]
        assert (out_dir / scanned_cap_name).is_file()

        # 6. THE MANIFEST SEALS THE COMPOSITES (W4, 2026-08-14) — the re-emit lane
        # mirrors the run lane exactly: every boolean composite this re-emit wrote
        # is in the manifest's ``files`` with a hash that verifies against the
        # on-disk bytes, and any of the eight names it did NOT write is absent from
        # the seal too (never hallucinated in).
        reemit_manifest = json.loads((out_dir / f"{case.id}-manifest.json").read_text())
        sealed = {f["name"]: f for f in reemit_manifest["files"]}
        composite_suffixes = ("arch-with-healingcaps", "arch-with-constructions",
                              "arch-capless", "arch-platform", "arch-socketless",
                              "socket-dish", "socket-platform", "arch-open-holes")
        composite_names = [f"{case.id}-{suffix}.stl" for suffix in composite_suffixes]
        on_disk = {p.name for p in out_dir.iterdir()}
        emitted = [name for name in composite_names if name in on_disk]
        assert emitted, "this re-emit must exercise at least one boolean composite"
        for name in emitted:
            assert name in sealed, f"{name} is on disk but the manifest never sealed it"
            assert sealed[name]["sha256"] == _sha256(out_dir / name)
            assert sealed[name]["bytes"] == (out_dir / name).stat().st_size
        for name in composite_names:
            if name not in on_disk:
                assert name not in sealed, \
                    f"{name} was never emitted — it must not ride the seal"

        # 7. ARTIFACT FACTS (boolean-engine plan 4c / clinical-pipeline-plan Stage 5)
        # — every STL this re-emit wrote (per-site AND the composites) carries a
        # manifest ``facts`` block; ``triangle_count`` matches an on-disk reload
        # exactly (STL preserves the triangle list losslessly). ``watertight`` is
        # checked only where the answer is structurally unambiguous — the raw scan
        # is open, and so is the open arch with the gingival-floor holes (artifact
        # 6's fourth ruling, client-ruled, 2026-08-15 night: the recess floor
        # never closes the model, the same open-by-design read the retired
        # through-hole shape carried) — a naive reload's watertight reading can
        # otherwise disagree with the in-memory mesh's own answer purely from
        # STL's float32 quantization (measured on the synthetic fixture,
        # test_auto_flow.py's twin pin), which is exactly why the design calls
        # for the caller's own reading.
        for name in on_disk:
            if not name.endswith(".stl"):
                continue
            entry = sealed.get(name)
            assert entry is not None, f"{name} is on disk but never entered the seal"
            assert "facts" in entry, f"{name} carries no facts block"
            reloaded = trimesh.load(out_dir / name, force="mesh")
            assert entry["facts"]["triangle_count"] == len(reloaded.faces), name
        raw_scan_name = f"{case.id}-upper.stl"
        if raw_scan_name in sealed:
            assert sealed[raw_scan_name]["facts"]["watertight"] is False
        if f"{case.id}-arch-open-holes.stl" in sealed:
            assert sealed[f"{case.id}-arch-open-holes.stl"]["facts"]["watertight"] is False
            # ARTIFACT 6, THE FOURTH RULING: the hole has a FLOOR now, not a
            # shaft through the model — a downward ray at the site's own pose
            # must find one inside the recess, never pass through empty (the
            # through-shaft's own retirement, "why is that cylinder so big",
            # read directly against the real package this re-emit just wrote).
            holes_mesh = trimesh.load(
                out_dir / f"{case.id}-arch-open-holes.stl", force="mesh")
            hole_pose = np.asarray(new_record["pose_matrix"], float)
            hole_origin = hole_pose[:3, 3]
            hole_axis = hole_pose[:3, :3] @ np.array([0.0, 0.0, 1.0])
            hole_locs, *_ = holes_mesh.ray.intersects_location(
                ray_origins=[hole_origin + hole_axis * 100.0],
                ray_directions=[-hole_axis])
            assert len(hole_locs) > 0, \
                "the floored hole must have a floor — no ray hit at all"
        for name, entry in sealed.items():
            if not name.endswith(".stl"):
                assert "facts" not in entry, f"{name} is not a mesh — no facts expected"
