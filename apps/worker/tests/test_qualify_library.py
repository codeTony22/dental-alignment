"""Tests for tools/qualify_library.py — the per-vendor-drop acceptance gate.

The named acceptance test is ``test_qualify_flags_known_duplicates``: running the
tool over TODAY'S real library must surface the zimmer-4.5-6020/6030 files being
byte-identical (sha256) to their neodent-gm counterparts (autopsy L3 — two "systems"
silently sharing CAD files, and nothing noticed until 2026-07-23).

`tools/` isn't on pythonpath (only `src` is, per pyproject.toml), so this file inserts
`tools/` onto sys.path itself rather than touching shared config (fle_study precedent).
"""
import sys
from pathlib import Path

import numpy as np
import pytest
import trimesh

_TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from qualify_library import (  # noqa: E402
    DEFAULT_LIBRARY,
    main,
    qualify_library,
    render_markdown,
)

REAL_LIBRARY = DEFAULT_LIBRARY


def _write_stl(path: Path, mesh: trimesh.Trimesh) -> bytes:
    data = mesh.export(file_type="stl")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


@pytest.fixture()
def synthetic_drop(tmp_path) -> Path:
    """A minimal vendor drop with a KNOWN duplicate pair across two 'systems':
    acme-5020 and bimex-5020 share bytes; acme-6020 is distinct; nonrev-7020 is a
    box (no rotational symmetry — the axis check's target)."""
    root = tmp_path / "library"
    cyl = trimesh.creation.cylinder(radius=3.0, height=4.0, sections=48)
    data = cyl.export(file_type="stl")
    for rel in ("caps/acme/acme-5020.stl", "caps/bimex/bimex-5020.stl"):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    _write_stl(root / "caps/acme/acme-6020.stl",
               trimesh.creation.cylinder(radius=2.5, height=5.0, sections=48))
    _write_stl(root / "caps/acme/nonrev-7020.stl",
               trimesh.creation.box(extents=[4.0, 6.0, 10.0]).subdivide().subdivide())
    return root


@pytest.mark.skipif(not REAL_LIBRARY.is_dir(), reason="real library not present")
class TestRealLibrary:
    @pytest.fixture(scope="class")
    def qualification(self):
        return qualify_library(REAL_LIBRARY)

    @pytest.mark.slow
    def test_qualify_flags_known_duplicates(self, qualification):
        # THE acceptance case: zimmer-4.5-6020/6030 == neodent-gm-6020/6030
        # byte-identity must surface as a finding, per variant
        for variant in ("6020", "6030"):
            matching = [
                f for f in qualification.findings
                if f"zimmer-4.5/zimmer-4.5-{variant}.stl" in f
                and f"neodent-gm/neodent-gm-{variant}.stl" in f
                and "byte-identical" in f
            ]
            assert matching, (
                f"the known zimmer==neodent {variant} byte-identity did not surface; "
                f"findings were: {qualification.findings}")
        # and the involved files themselves are flagged, not quietly listed as OK
        for rel in ("caps/zimmer-4.5/zimmer-4.5-6020.stl",
                    "caps/neodent-gm/neodent-gm-6020.stl"):
            rec = next(r for r in qualification.records if r.rel_path == rel)
            assert not rec.qualified

    def test_current_drop_inventory(self, qualification):
        caps = [r for r in qualification.records if r.kind == "cap"]
        construction = [r for r in qualification.records if r.kind == "construction"]
        assert len(caps) == 12, [r.rel_path for r in caps]
        assert len(construction) == 2, [r.rel_path for r in construction]
        # superseded drops are excluded from acceptance but listed
        assert all("superseded" not in r.rel_path for r in qualification.records)
        assert len(qualification.skipped) == 12
        assert all("superseded" in s for s in qualification.skipped)

    def test_every_cap_reads_channel_ring_and_axis(self, qualification):
        for r in qualification.records:
            if r.kind != "cap":
                continue
            # loop-truth channel mouth (catalog measures 1.077-1.152) + Kasa ring +
            # verified canonical axis (catalog 0.048-0.109) on every current cap
            assert r.channel_mouth_r_mm == pytest.approx(1.1, abs=0.08), r.rel_path
            assert r.ring_xy is not None, r.rel_path
            assert r.revolution_error_mm is not None and r.revolution_error_mm <= 0.25, \
                (r.rel_path, r.revolution_error_mm)

    def test_dess_designed_lumen_recorded(self, qualification):
        dess = next(r for r in qualification.records
                    if r.rel_path == "construction/dess/neodent-gm-scanbody.stl")
        assert dess.channel_mouth_r_mm == pytest.approx(2.0, abs=0.02)


class TestSyntheticDrop:
    def test_duplicates_detected_across_models(self, synthetic_drop):
        q = qualify_library(synthetic_drop)
        dupes = [f for f in q.findings if "byte-identical" in f]
        assert len(dupes) == 1, q.findings
        assert "acme/acme-5020.stl" in dupes[0] and "bimex/bimex-5020.stl" in dupes[0]
        assert "acme-6020" not in dupes[0]

    def test_non_revolute_part_fails_axis_verification(self, synthetic_drop):
        q = qualify_library(synthetic_drop)
        box_rec = next(r for r in q.records if "nonrev-7020" in r.rel_path)
        assert any("does NOT verify" in issue for issue in box_rec.issues), box_rec.issues

    def test_report_is_deterministic_and_written(self, synthetic_drop, tmp_path, capsys):
        q = qualify_library(synthetic_drop)
        assert render_markdown(q) == render_markdown(qualify_library(synthetic_drop)), \
            "re-running on an unchanged drop must produce identical bytes"
        out = tmp_path / "report.md"
        code = main(["--library", str(synthetic_drop), "--write", str(out)])
        assert code == 1  # flags present (duplicates + non-revolute part)
        text = out.read_text()
        assert text == render_markdown(q)
        assert "byte-identical" in text
        assert capsys.readouterr().out.strip().startswith("# Library qualification report")

    def test_missing_root_exits_2(self, tmp_path):
        assert main(["--library", str(tmp_path / "nope")]) == 2
