"""The five comparison artifacts are produced and are valid meshes."""
import trimesh
import pytest

from case_prep.adapters.synthetic import SyntheticParams, generate_case
from case_prep.demo.comparison import emit_comparison_artifacts


@pytest.mark.slow
def test_emits_the_five_comparison_files(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    generate_case(case_dir, SyntheticParams(seed=4, n_implants=2))

    paths = emit_comparison_artifacts(case_dir, tmp_path / "compare")

    for key in ("input", "generated", "intersection", "difference", "modifications"):
        assert paths[key].exists(), key
    # the AND of scan and generated is a real, non-empty solid smaller than the scan
    inter = trimesh.load(paths["intersection"], force="mesh")
    scan = trimesh.load(paths["input"], force="mesh")
    assert inter.is_watertight and 0 < inter.volume < scan.volume
