"""THE FULL RUN FOR THE PRODUCT — case_prep.application.run (plan §7 slice 5c).

The demo's run endpoint lifted as a refusal-raising call (copy-debt ledger row 8;
server.py:893-916 + 933-1011): validated selection → ``run_auto_case`` with everything
on, into THE CALLER'S run directory (a parameter — AM-1's immutable run dirs are the
caller's contract, so this layer names no reports path).

Synthetic tests pin the REFUSALS (they fire before any mesh is parsed — milliseconds),
including the explicit-selection gate's sentence VERBATIM: the BFF serves those words,
and the client reads them. The full run needs the real tree and is slow-marked; its
FIDELITY check compares against the DEMO'S EXISTING warmed ``run.json`` for the same
case — a read-only key-set comparison (running the demo's endpoint fresh would EMIT
into the frozen data plane, which the freeze forbids this suite to risk).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from case_prep.application.cases import CaseRecord, discover_cases
from case_prep.application.catalog import UnknownSelection
from case_prep.application.run import RunRefused, RunSelection, run_case

REAL = Path(__file__).resolve().parents[1] / "data" / "real"
real_only = pytest.mark.skipif(not (REAL / "library").is_dir(),
                               reason="real data tree not present")
DEMO_RUN = (Path(__file__).resolve().parents[1] / "reports" / "live-demo"
            / "neodent-gm" / "run.json")
demo_warmed = pytest.mark.skipif(not DEMO_RUN.is_file(),
                                 reason="demo's warmed run.json not present")


def _case(tmp_path: Path, sites=(), suggested=(None, None)) -> CaseRecord:
    return CaseRecord(
        id="case-x", doctor="Doctor X", jaw="upper",
        scan=tmp_path / "scan.stl", data_root=tmp_path,
        suggested_model=suggested[0], suggested_construction=suggested[1],
        suggested_sites=tuple(sites))


def _selection(**overrides) -> RunSelection:
    values = dict(model="neodent-gm",
                  construction_path="dess/neodent-gm-scanbody.stl",
                  variants={13: "5020"}, jaw=None, gingival_offset_mm=0.2)
    values.update(overrides)
    return RunSelection(**values)


class TestTheExplicitSelectionGate:
    """server.py:893-916 verbatim (ledger row 8): the run never falls back to the
    case's suggestion — the sentence, the field naming and the suggestion hint are
    the demo's own words, because the product client renders them."""

    def test_a_missing_model_refuses_in_the_demos_sentence(self, tmp_path):
        case = _case(tmp_path, sites=[{"tooth": 13, "center": [0.0, 0.0, 0.0]}])
        with pytest.raises(RunRefused) as exc:
            run_case(case, _selection(model=None), tmp_path / "run")
        message = str(exc.value)
        assert message.startswith("the library selection is incomplete: choose "
                                  "the implant system")
        assert "The software will not pick one for you." in message

    def test_a_missing_construction_names_that_piece(self, tmp_path):
        case = _case(tmp_path, sites=[{"tooth": 13, "center": [0.0, 0.0, 0.0]}])
        with pytest.raises(RunRefused) as exc:
            run_case(case, _selection(construction_path=None), tmp_path / "run")
        assert "the construction part" in str(exc.value)

    def test_both_missing_joins_with_and_and_carries_the_suggestion_hint(self, tmp_path):
        case = _case(tmp_path, sites=[{"tooth": 13, "center": [0.0, 0.0, 0.0]}],
                     suggested=("neodent-gm", "dess/neodent-gm-scanbody.stl"))
        with pytest.raises(RunRefused) as exc:
            run_case(case, _selection(model=None, construction_path=None),
                     tmp_path / "run")
        message = str(exc.value)
        assert " and " in message
        # the demo's hint, verbatim in shape: names both suggestions and says they
        # are suggestions only — the operator must send them back explicitly
        assert "this case suggests model='neodent-gm'" in message
        assert "a suggestion only; send it back explicitly to use it" in message

    def test_no_hint_when_the_case_suggests_nothing(self, tmp_path):
        case = _case(tmp_path, sites=[{"tooth": 13, "center": [0.0, 0.0, 0.0]}])
        with pytest.raises(RunRefused) as exc:
            run_case(case, _selection(model=None), tmp_path / "run")
        assert "suggests" not in str(exc.value)


class TestSiteRefusals:
    """Cheapest-first, like the preview: an impossible ask never costs a mesh parse."""

    def test_an_empty_selection_refuses(self, tmp_path):
        case = _case(tmp_path, sites=[{"tooth": 13, "center": [0.0, 0.0, 0.0]}])
        with pytest.raises(RunRefused) as exc:
            run_case(case, _selection(variants={}), tmp_path / "run")
        assert "no sites selected" in str(exc.value)

    def test_a_tooth_the_case_has_no_site_for_refuses(self, tmp_path):
        case = _case(tmp_path, sites=[{"tooth": 13, "center": [0.0, 0.0, 0.0]}])
        with pytest.raises(RunRefused) as exc:
            run_case(case, _selection(variants={31: "5020"}), tmp_path / "run")
        assert "tooth 31" in str(exc.value)

    def test_a_site_without_a_centre_refuses(self, tmp_path):
        case = _case(tmp_path, sites=[{"tooth": 13, "center": None}])
        with pytest.raises(RunRefused) as exc:
            run_case(case, _selection(), tmp_path / "run")
        assert "tooth 13" in str(exc.value)

    def test_an_unknown_model_refuses_in_catalog_words(self, tmp_path):
        (tmp_path / "library/caps").mkdir(parents=True)
        case = _case(tmp_path, sites=[{"tooth": 13, "center": [0.0, 0.0, 0.0]}])
        with pytest.raises(UnknownSelection) as exc:
            run_case(case, _selection(model="no-such-system"), tmp_path / "run")
        assert "unknown implant system" in str(exc.value)


@real_only
@demo_warmed
@pytest.mark.slow  # a FULL run: product + QC renders + confidence + package emission
class TestRunOnTheRealTree:
    def test_the_summary_is_the_demos_shape_exactly(self, tmp_path):
        """Key-set fidelity against the demo's EXISTING warmed run for the SAME case
        and the SAME selection (reports/live-demo/neodent-gm/run.json — read-only:
        re-running the demo endpoint would emit into the frozen data plane). The
        product's results table and Deliver's assurance rows are written against
        these keys; a silently divergent key is a blank column, not a type error."""
        demo = json.loads(DEMO_RUN.read_text())
        demo_summary = demo["summary"]
        sel = demo["selection"]  # the demo's own authorized selection, mirrored
        case = next(c for c in discover_cases(REAL) if c.id == "neodent-gm")
        out_dir = tmp_path / "runs" / "fidelity"
        out_dir.mkdir(parents=True)
        summary = run_case(case, RunSelection(
            model=sel["model"], construction_path=sel["construction_path"],
            variants={int(t): v for t, v in sel["variants"].items()},
            jaw=sel["jaw"], gingival_offset_mm=sel["gingival_offset_mm"]), out_dir)

        assert set(summary) == set(demo_summary)
        ours = {r["tooth"]: r for r in summary["sites"]}
        theirs = {r["tooth"]: r for r in demo_summary["sites"]}
        assert set(ours) == set(theirs)
        for tooth in ours:
            assert set(ours[tooth]) == set(theirs[tooth]), f"tooth {tooth} row keys"
            # the row's verdict blocks keep their inner shape too — the flag landing
            # (5c-ii) reads guidance.level, Deliver reads variant/production
            assert set(ours[tooth]["guidance"]) == set(theirs[tooth]["guidance"])
            assert set(ours[tooth]["variant"]) == set(theirs[tooth]["variant"])
        assert ours[13]["guidance"]["level"] in ("ready", "attention", "action-needed")

        # the emission landed in THE CALLER'S directory, file-for-file what the
        # summary claims (names relative to the run dir). The demo's set is a
        # FLOOR, not the whole truth: the product deliberately grew artifacts the
        # frozen demo can never emit (§10-AR.4 the platform arch, §10-AR.11 the
        # socket layer files) — those additions are named EXACTLY, so an
        # unrecorded new artifact still fails here rather than drifting in.
        ours_files = set(summary["package_files"])
        demo_files = set(demo_summary["package_files"])
        assert demo_files <= ours_files, demo_files - ours_files
        assert ours_files - demo_files == {
            "neodent-gm-arch-platform.stl",
            "neodent-gm-arch-socketless.stl",
            "neodent-gm-socket-dish.stl",
            "neodent-gm-socket-platform.stl",
            "neodent-gm-model-closed.stl",
            # pipeline 2a: the per-site scanned-cap isolation, one per selected
            # tooth — the demo can never emit these
            "neodent-gm-4-scanned-cap.stl",
            "neodent-gm-13-scanned-cap.stl",
        }
        for name in summary["package_files"]:
            assert (out_dir / name).is_file(), name

    def test_nothing_is_written_outside_the_callers_run_dir(self, tmp_path):
        """AM-1's contract from this layer's side: the run fills the directory it was
        handed and touches nothing else — no reports path, no demo data plane."""
        case = next(c for c in discover_cases(REAL) if c.id == "neodent-gm")
        scan_tree_before = sorted(case.scan.parent.rglob("*"))
        demo_run_bytes = DEMO_RUN.read_bytes()
        out_dir = tmp_path / "runs" / "isolation"
        out_dir.mkdir(parents=True)
        run_case(case, RunSelection(
            model="neodent-gm", construction_path="dess/neodent-gm-scanbody.stl",
            variants={13: "5020"}), out_dir)
        assert sorted(case.scan.parent.rglob("*")) == scan_tree_before
        assert DEMO_RUN.read_bytes() == demo_run_bytes
        assert any(out_dir.iterdir())


class TestASiteTheOperatorMarked:
    """Client 2026-07-28: detection MISSES 2 of the 10 sites on this fleet, and until
    now a missed cap could not be worked at all — the case record was the only place a
    centre lived, and an operator cannot write to the case record. A marked centre
    rides in the SELECTION with every other operator act."""

    def test_a_marked_centre_lets_a_site_the_case_never_suggested_be_run(self, tmp_path):
        # no suggested_sites at all: without the mark this refuses outright
        case = _case(tmp_path)
        with pytest.raises(RunRefused) as exc:
            run_case(case, _selection(), tmp_path / "run")
        assert "has no site centre" in str(exc.value)

        # with the mark it gets PAST the centre gate — it fails later, on the meshes
        # this synthetic case does not have, which is the point: the centre resolved.
        with pytest.raises(Exception) as exc2:
            run_case(case, _selection(marked_centers={13: [1.0, 2.0, 3.0]}),
                     tmp_path / "run")
        assert "has no site centre" not in str(exc2.value)

    def test_the_operators_mark_WINS_over_the_cases_own_suggestion(self, tmp_path):
        """A human who marked a centre has looked at this scan more recently than the
        ingest did. Preferring the ingest would make the mark decorative."""
        case = _case(tmp_path, sites=[{"tooth": 13, "center": [9.0, 9.0, 9.0]}])
        seen = {}
        import case_prep.application.run as run_module
        original = run_module.ConfirmedSite

        def spy(tooth, center, *args, **kwargs):
            seen[tooth] = center
            return original(tooth, center, *args, **kwargs)

        run_module.ConfirmedSite = spy
        try:
            with pytest.raises(Exception):
                run_case(case, _selection(marked_centers={13: [1.0, 2.0, 3.0]}),
                         tmp_path / "run")
        finally:
            run_module.ConfirmedSite = original
        assert seen[13] == (1.0, 2.0, 3.0), "the mark must win over the suggestion"

    def test_a_site_with_NEITHER_still_refuses_in_the_same_words(self, tmp_path):
        # the refusal was never about where the centre came from
        case = _case(tmp_path, sites=[{"tooth": 99, "center": [0.0, 0.0, 0.0]}])
        with pytest.raises(RunRefused) as exc:
            run_case(case, _selection(marked_centers={99: [1.0, 2.0, 3.0]}),
                     tmp_path / "run")
        assert "tooth 13 has no site centre" in str(exc.value)

    def test_a_re_mark_drops_the_case_records_pair_with_the_centre_it_measured(
            self, tmp_path):
        """THE 12° DEFECT (measured 2026-08-04, cap6020): the mark won the CENTRE
        while the record's center_mark/rim_mark still shipped — and the aligner
        prefers the marks, so the re-mark was decorative for the physics and the
        seat spliced two measurements 2.24mm apart. A centre mark and its rim mark
        are ONE measurement (the re-click pair-integrity record): the record's pair
        belongs to the record's centre, and an operator's re-mark ships ALONE.
        Measured on the production pipeline: seeding from the operator's bare
        centre took DEV RMS 0.4157 -> 0.3053 and moved the axis 12.2°."""
        case = _case(tmp_path, sites=[{
            "tooth": 13, "center": [9.0, 9.0, 9.0],
            "center_mark": [9.1, 9.0, 9.0], "rim_mark": [11.0, 9.0, 9.0],
            "marked_points": [[9.1, 9.0, 9.0]], "rim_points": [[11.0, 9.0, 9.0]],
        }])
        seen = {}
        import case_prep.application.run as run_module
        original = run_module.ConfirmedSite

        def spy(tooth, center, variant, marked_points=None, center_mark=None,
                rim_mark=None, rim_points=None, **kwargs):
            seen[tooth] = dict(center=center, marked_points=marked_points,
                               center_mark=center_mark, rim_mark=rim_mark,
                               rim_points=rim_points)
            return original(tooth, center, variant, marked_points, center_mark,
                            rim_mark, rim_points=rim_points, **kwargs)

        run_module.ConfirmedSite = spy
        try:
            with pytest.raises(Exception):
                run_case(case, _selection(marked_centers={13: [1.0, 2.0, 3.0]}),
                         tmp_path / "run")
        finally:
            run_module.ConfirmedSite = original
        assert seen[13]["center"] == (1.0, 2.0, 3.0)
        assert seen[13]["center_mark"] is None
        assert seen[13]["rim_mark"] is None
        assert seen[13]["marked_points"] is None
        assert seen[13]["rim_points"] is None

    def test_without_a_re_mark_the_records_pair_still_ships_whole(self, tmp_path):
        # the pair path BEATS the bare click when the centre is good (measured:
        # 0.4157 vs 0.4894 on cap6020's curated seed) — dropping it
        # unconditionally would regress every well-seeded site
        case = _case(tmp_path, sites=[{
            "tooth": 13, "center": [9.0, 9.0, 9.0],
            "center_mark": [9.1, 9.0, 9.0], "rim_mark": [11.0, 9.0, 9.0],
        }])
        seen = {}
        import case_prep.application.run as run_module
        original = run_module.ConfirmedSite

        def spy(tooth, center, variant, marked_points=None, center_mark=None,
                rim_mark=None, rim_points=None, **kwargs):
            seen[tooth] = dict(center=center, center_mark=center_mark,
                               rim_mark=rim_mark)
            return original(tooth, center, variant, marked_points, center_mark,
                            rim_mark, rim_points=rim_points, **kwargs)

        run_module.ConfirmedSite = spy
        try:
            with pytest.raises(Exception):
                run_case(case, _selection(), tmp_path / "run")
        finally:
            run_module.ConfirmedSite = original
        assert seen[13]["center"] == (9.0, 9.0, 9.0)
        assert seen[13]["center_mark"] == [9.1, 9.0, 9.0]
        assert seen[13]["rim_mark"] == [11.0, 9.0, 9.0]
