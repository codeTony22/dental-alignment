"""The staged workflow: stage 1 (ingest+localize → awaiting_seed) → operator seed →
stage 2 (register+gate → ready), each emitting real file artifacts."""
import json

import trimesh
import pytest

from case_prep.adapters.synthetic import SyntheticParams, generate_case
from case_prep.pipeline.stages import (
    Status,
    auto_seed,
    run_stage1,
    run_stage2,
    run_workflow,
)


def test_stage1_parks_at_awaiting_seed_with_artifacts(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    generate_case(case_dir, SyntheticParams(seed=7, n_implants=3))
    work = tmp_path / "work"

    s1 = run_stage1(case_dir, work)

    assert s1.status is Status.AWAITING_SEED
    assert s1.detected_count == s1.declared_count == 3
    assert len(s1.seeds) == 3
    assert s1.artifacts["normalized_scan"].exists()
    assert (work / "stage1" / "localization.json").exists()
    # state machine recorded
    assert json.loads((work / "case_state.json").read_text())["status"] == "awaiting_seed"


@pytest.mark.slow
def test_stage2_registers_from_seeds_and_packages(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    generate_case(case_dir, SyntheticParams(seed=7, n_implants=2, retention=__import__(
        "case_prep.domain.poses", fromlist=["Retention"]).Retention.CEMENT))
    work = tmp_path / "work"

    run_stage1(case_dir, work)
    auto_seed(work)
    s2 = run_stage2(case_dir, work)

    assert s2.status is Status.READY
    assert s2.clear_rate == 1.0
    gen = trimesh.load(s2.artifacts["generated"], force="mesh")
    assert len(gen.vertices) > 0          # bodies baked into geometry
    assert (work / "stage2" / "result.json").exists()


@pytest.mark.slow
def test_full_workflow_end_to_end(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    generate_case(case_dir, SyntheticParams(seed=4, n_implants=2))
    work = tmp_path / "work"

    s1, s2 = run_workflow(case_dir, work)

    assert s1.status is Status.AWAITING_SEED
    assert s2.status is Status.READY
    # every stage left an inspectable artifact behind
    assert s1.artifacts["normalized_scan"].exists()
    assert s2.artifacts["generated"].exists()
