"""CLI smoke test — the synthetic run produces report artifacts end to end.

Plus the ``auto`` command's half of the GINGIVAL-RELIEF contract (2026-07-25): the relief
is a proposal the export gate judges, and the gate now fails CLOSED (a relief that eats or
undercuts the as-built screw channel raises ValueError and emits nothing — measured on the
whole atlantis/zimmer-4.5 fleet and dess/neodent-gm 5020 at the 0.20 default). The server
turns that into a 409 carrying the gate's words; the CLI must be equally readable — the
sentence printed, a non-zero exit — and must be able to ASK for a different offset at all.
The refusal is injected here rather than driven from real fleet geometry: this is about the
entrypoint's contract with the pipeline, and the measured gate itself is pinned on the real
parts in ``test_output_package.py::TestGingivalReliefBlock``.
"""
import trimesh
import pytest

import case_prep.pipeline.auto_flow as auto_flow
from case_prep.cli import main
from case_prep.pipeline.final_product import DEFAULT_GINGIVAL_OFFSET_MM


@pytest.mark.slow
def test_synthetic_run_writes_report(tmp_path, capsys):
    code = main([
        "run", "--synthetic", "--seed", "5", "--implants", "2",
        "--retention", "cement", "--out", str(tmp_path),
    ])
    assert code == 0
    reports = [d for d in tmp_path.iterdir() if d.is_dir() and d.name != "cases"]
    assert len(reports) == 1
    assert (reports[0] / "accuracy-report.json").exists()
    assert (reports[0] / "feasibility-memo.md").exists()
    assert "clear-rate" in capsys.readouterr().out


def _auto_inputs(tmp_path):
    """The three files an ``auto`` confirmed run needs, as the smallest valid stand-ins:
    an arch scan, a one-variant cap library and a vendor construction part."""
    scan = tmp_path / "arch.stl"
    scan.write_bytes(trimesh.creation.box(extents=[30, 20, 6]).export(file_type="stl"))
    caps = tmp_path / "caps"
    caps.mkdir(exist_ok=True)  # the argv helper may be called twice in one test
    (caps / "neodent-gm-6030.stl").write_bytes(
        trimesh.creation.cylinder(radius=2.2, height=5.0, sections=48)
        .export(file_type="stl"))
    construction = tmp_path / "scanbody.stl"
    construction.write_bytes(
        trimesh.creation.cylinder(radius=3.0, height=8.0, sections=48)
        .export(file_type="stl"))
    return scan, caps, construction


def _auto_argv(tmp_path, *extra):
    scan, caps, construction = _auto_inputs(tmp_path)
    return ["auto", "--scan", str(scan), "--caps", str(caps),
            "--construction", str(construction), "--vendor", "dess",
            "--jaw", "lower", "--site", "29:0,0,3",
            "--out", str(tmp_path / "pkg"), *extra]


def test_the_export_gates_refusal_is_printed_not_raised(tmp_path, capsys, monkeypatch):
    """A gate refusal is an ANSWER to the operator: the words the gate wrote, on stdout,
    with a non-zero exit — not a traceback with the sentence buried in it."""
    refusal = ("gingival-relief gate: the 0.20mm gingival relief ate the screw channel "
               "of tooth 29 (atlantis/zimmer-4.5 7030) — re-run with a smaller gingival "
               "offset — package NOT emitted")

    def _refuse(**kwargs):
        raise ValueError(refusal)

    monkeypatch.setattr(auto_flow, "run_auto_case", _refuse)
    code = main(_auto_argv(tmp_path))
    assert code == 2
    out = capsys.readouterr().out
    assert "re-run with a smaller gingival offset" in out
    assert "tooth 29 (atlantis/zimmer-4.5 7030)" in out, \
        "the refusal must still name the part a human has to act on"


def test_the_gingival_offset_is_askable_and_defaults_to_the_client_value(
    tmp_path, monkeypatch
):
    """The flag exists BECAUSE the default is refused on part of the catalog — a CLI that
    can only ask for 0.20 cannot emit those parts at all."""
    seen = {}

    def _capture(**kwargs):
        seen.update(kwargs)
        return {"sites": [], "package_files": []}

    monkeypatch.setattr(auto_flow, "run_auto_case", _capture)

    assert main(_auto_argv(tmp_path)) == 0
    assert seen["gingival_offset_mm"] == DEFAULT_GINGIVAL_OFFSET_MM

    seen.clear()
    assert main(_auto_argv(tmp_path, "--gingival-offset", "0.0")) == 0
    assert seen["gingival_offset_mm"] == 0.0, "the operator's value must reach the pipeline"
