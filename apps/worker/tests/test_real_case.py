"""Semi-real case path: place scan bodies on an arbitrary arch mesh and run the staged
workflow with operator seeds. Uses a synthetic arch as the stand-in so the test is
self-contained (the real Teeth3DS arch lives in gitignored data/real/)."""
import numpy as np
import pytest

from case_prep.adapters.real_case import build_semireal_case
from case_prep.adapters.synthetic import make_gingiva_arch
from case_prep.pipeline.stages import Status, run_workflow


@pytest.mark.slow
def test_semireal_workflow_emits_staged_artifacts(tmp_path):
    arch_path = tmp_path / "arch.stl"
    make_gingiva_arch(np.random.default_rng(0)).export(arch_path)

    case_dir = tmp_path / "case"
    gt = build_semireal_case(arch_path, case_dir, n_implants=2, seed=1)
    assert len(gt.poses) == 2  # bodies placed on the arch with ground truth

    work = tmp_path / "work"
    s1, s2 = run_workflow(case_dir, work, operator_seeds=True)

    assert s2 is not None
    assert len(s2.implants) == 2
    # per-stage artifacts exist (the real input/output files)
    assert s1.artifacts["normalized_scan"].exists()
    assert (work / "stage2" / "01_input.stl").exists()
    assert (work / "stage2" / "02_generated.stl").exists()
    # operator reconciled the count, so stage 2 judged registration (not a count flag)
    import json
    assert json.loads((work / "case_state.json").read_text())["count_match"] is True
