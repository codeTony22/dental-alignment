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

import pytest

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
    def test_a_part_change_re_emits_without_re_aligning(self, tmp_path):
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

        # a DIFFERENT part from a DIFFERENT vendor, and a different relief ask
        reemit_selection = RunSelection(
            model="neodent-gm",
            construction_path="atlantis/zimmer-4.5-scanbody.stl",
            variants={t: "5020" for t in teeth}, jaw=None,
            gingival_offset_mm=0.1)
        out_dir = tmp_path / "runs" / "reemitted"
        out_dir.mkdir(parents=True)
        summary_b = emit_from_poses(case, reemit_selection, source_dir, out_dir)

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

        # 4. the receipt names its source and refreshes the product facts
        assert summary_b["emitted_from"] == "source"
        assert summary_b["mode"] == "reemit-from-poses"
        row_b = next(r for r in summary_b["sites"] if r["tooth"] == tooth)
        row_a = next(r for r in summary_a["sites"] if r["tooth"] == tooth)
        # pose/seat/clock facts verbatim; the product facts are the NEW part's
        assert row_b["fit"] == row_a["fit"]
        assert row_b["seat_method"] == row_a["seat_method"]
        assert row_b["guidance"]["level"] == row_a["guidance"]["level"]
        assert row_b["production"]["gingival_offset_mm"] <= 0.1 + 1e-9
        # the arch trio and the report are in the new package
        for name in (f"{case.id}-arch-with-constructions.stl",
                     f"{case.id}-auto-report.json"):
            assert (out_dir / name).exists()
