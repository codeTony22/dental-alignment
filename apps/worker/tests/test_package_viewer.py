"""view.html — the self-contained 3D deliverable viewer (ROI loop it.2, business #1):
the doctor opens ONE file offline and sees the colored views. The web side ships a
standalone JS bundle; the emitter inlines it with base64 STLs + the audit meta.

MODULE NOTE — ``gingival_offset_mm=0.0`` on the run below (2026-07-25): the stand-in
construction part (``make_scan_body_mesh``) is too thin for the client's 0.20mm gingival
relief and the G5 export gate rightly fails it closed; the relief's own contract lives in
``test_final_product.py::TestGingivalProfileOffset``."""
from __future__ import annotations

import base64
from pathlib import Path

import pytest
import trimesh

BUNDLE = (Path(__file__).parents[2]
          / "web/viewer-standalone/dist/standalone-viewer.iife.js")


@pytest.mark.skipif(not BUNDLE.exists(), reason="standalone viewer bundle not built yet")
def test_view_html_embeds_bundle_parts_and_meta(tmp_path):
    from case_prep.pipeline.package_viewer import write_view_html

    stl = tmp_path / "part.stl"
    trimesh.creation.cylinder(radius=2.0, height=3.0).export(stl)
    out = write_view_html(
        case_id="c1", out_dir=tmp_path,
        parts=[{"name": "part.stl", "role": "cap", "path": stl}],
        meta={"sites": [{"tooth": 8, "variant": "5020"}]})
    html = out.read_text()
    assert out.name == "view.html"
    assert "__CASE__" in html and '"cap"' in html and '"c1"' in html
    b64 = base64.b64encode(stl.read_bytes()).decode()
    assert b64[:60] in html            # the STL is embedded
    assert "standalone-viewer" in html or "THREE" in html or len(html) > 100_000


@pytest.mark.slow
@pytest.mark.skipif(not BUNDLE.exists(), reason="standalone viewer bundle not built yet")
def test_run_emits_view_html_in_the_package(tmp_path):
    import json as _json

    import numpy as np

    from case_prep.adapters.cap_library import CapLibrary
    from case_prep.adapters.synthetic import make_gingiva_arch, make_scan_body_mesh
    from case_prep.domain.cap_catalog import CapSpec
    from case_prep.pipeline.auto_flow import ConfirmedSite, run_auto_case
    from case_prep.adapters.real_case import build_embedded_case

    np.random.seed(0)
    arch_path = tmp_path / "arch.stl"
    make_gingiva_arch(np.random.default_rng(0)).export(arch_path)
    cad_path = tmp_path / "cap.stl"
    make_scan_body_mesh().export(cad_path)
    gt = build_embedded_case(arch_path, cad_path, tmp_path / "case", n_implants=1, seed=1)
    scan = trimesh.load(tmp_path / "case" / "scan.stl", force="mesh")
    lib = CapLibrary.single(CapSpec("certain", "4.1"),
                            trimesh.load(tmp_path / "case/library/certain3i_4_1/mesh.stl",
                                         force="mesh"))
    out = run_auto_case(case_id="vh", scan=scan, library=lib,
                        construction_mesh=make_scan_body_mesh(), vendor="dess",
                        gingival_offset_mm=0.0,  # stand-in body — see module note
                        confirmed=[ConfirmedSite(8, tuple(map(float, gt.poses[0].position)))],
                        jaw_label="upper", out_dir=tmp_path / "out")
    assert "view.html" in out["package_files"]
    html = (tmp_path / "out" / "view.html").read_text()
    assert "__CASE__" in html and '"vh"' in html
