"""THE WORKER PORT'S IN-PROCESS ADAPTER (plan §3/AM-3, §1.2/AM-1; slice 5c).

``InProcessWorker`` completes synchronously but records the job-shaped truth —
queued→running→done|refused with timestamps — so the product renders phase-2's states
from day one and the SQS adapter later replaces one file, not the resource contracts.

The adapter owns AM-1's immutability at the filesystem edge: a run directory is
created exactly once, a second submit against the same run_id REFUSES rather than
write into history, and a refused run leaves ``refusal.json`` — never half-artifacts
pretending to be a package. The physics is injectable (``runner``) so these tests pin
the ADAPTER's contract in milliseconds; the real ``application.run.run_case`` path is
exercised by the worker's own suite (test_run.py) and the wired default is asserted
here by identity.

Also here: the carried 5a-era minor — RunSession.state (bff/session.py) is TIED to
JobState by test, so the session's run receipt and the port's states can never drift.
"""
from __future__ import annotations

import json
import typing
from pathlib import Path

import pytest

from case_prep.application.run import RunRefused, RunSelection, run_case

from bff.ports.worker import InProcessWorker, JobState
from bff.session import RunSession

from conftest import make_data_tree


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    return make_data_tree(tmp_path / "data")


@pytest.fixture
def product_root(tmp_path: Path) -> Path:
    return tmp_path / "product"


def _request(run_id: str = "run-1", **selection_overrides) -> dict:
    selection = {"model": "neodent-gm",
                 "construction_path": "dess/neodent-gm-scanbody.stl",
                 "variants": {"4": "5020", "13": "5020"},
                 "jaw": "upper", "gingival_offset_mm": 0.2}
    selection.update(selection_overrides)
    return {"run_id": run_id, "selection": selection}


def _ok_runner(summary: dict):
    def runner(case, selection: RunSelection, out_dir: Path) -> dict:
        # a real run fills the dir it was handed; the fake leaves a marker so the
        # immutability tests can see which submit wrote where
        (Path(out_dir) / "marker.json").write_text(json.dumps({"case": case.id}))
        return summary
    return runner


SUMMARY = {"case_id": "neodent-gm", "sites": [{"tooth": 4}, {"tooth": 13}],
           "package_files": ["a.stl", "view.html"]}


class TestStateTie:
    def test_run_session_state_literal_is_exactly_the_job_states(self):
        """The carried minor (grill of 0b/1, due 5c): the session's run receipt and
        the port's enum are one vocabulary — a state the port can report must be a
        state the session can hold, and vice versa."""
        literal = RunSession.model_fields["state"].annotation
        assert set(typing.get_args(literal)) == {s.value for s in JobState}


class TestSubmitRunsTheJob:
    def test_a_completed_job_reports_done_with_ordered_timestamps(
            self, data_root, product_root):
        worker = InProcessWorker(data_root, product_root, runner=_ok_runner(SUMMARY))
        job_id = worker.submit("neodent-gm", _request())
        status = worker.status(job_id)
        assert status.state is JobState.DONE
        assert status.refusal is None
        # queued→running→done really happened, in order (AM-3's writeback shape)
        assert status.queued_at is not None
        assert status.queued_at <= status.started_at <= status.finished_at

    def test_result_serves_the_summary_verbatim(self, data_root, product_root):
        worker = InProcessWorker(data_root, product_root, runner=_ok_runner(SUMMARY))
        job_id = worker.submit("neodent-gm", _request())
        assert worker.result(job_id) == SUMMARY

    def test_the_run_lands_in_the_named_immutable_run_dir(
            self, data_root, product_root):
        worker = InProcessWorker(data_root, product_root, runner=_ok_runner(SUMMARY))
        worker.submit("neodent-gm", _request(run_id="run-9"))
        assert (product_root / "neodent-gm" / "runs" / "run-9" / "marker.json").is_file()

    def test_the_request_is_snapshotted_at_submit(self, data_root, product_root):
        """A caller mutating its dict after submit must not rewrite the job's record
        — the queue adapter will serialize at this boundary, so the in-process one
        must behave as if it already had."""
        seen = {}

        def runner(case, selection: RunSelection, out_dir: Path) -> dict:
            seen["variants"] = dict(selection.variants)
            return SUMMARY

        worker = InProcessWorker(data_root, product_root, runner=runner)
        request = _request()
        request["selection"]["variants"]["4"] = "5020"
        job_id = worker.submit("neodent-gm", request)
        request["selection"]["variants"]["4"] = "9999"  # too late — snapshotted
        assert seen["variants"] == {4: "5020", 13: "5020"}
        assert worker.status(job_id).state is JobState.DONE

    def test_unknown_jobs_raise_key_error(self, data_root, product_root):
        worker = InProcessWorker(data_root, product_root, runner=_ok_runner(SUMMARY))
        with pytest.raises(KeyError):
            worker.status("no-such-job")
        with pytest.raises(KeyError):
            worker.result("no-such-job")

    def test_the_default_runner_is_the_application_lift(self, data_root, product_root):
        # wiring, not behavior: the real physics path is the worker suite's to prove
        assert InProcessWorker(data_root, product_root)._runner is run_case


class TestImmutableRunDirs:
    """AM-1: a run directory is written ONCE. Nothing ever writes into an existing
    one — a re-run is a NEW run_id, and the adapter enforces it at the edge."""

    def test_a_second_submit_with_the_same_run_id_refuses_before_running(
            self, data_root, product_root):
        calls = []

        def runner(case, selection, out_dir):
            calls.append(out_dir)
            return SUMMARY

        worker = InProcessWorker(data_root, product_root, runner=runner)
        worker.submit("neodent-gm", _request(run_id="run-1"))
        with pytest.raises(FileExistsError) as exc:
            worker.submit("neodent-gm", _request(run_id="run-1"))
        assert "immutable" in str(exc.value)
        assert len(calls) == 1  # the physics never ran a second time

    def test_even_a_refused_runs_dir_is_never_rewritten(self, data_root, product_root):
        def refusing(case, selection, out_dir):
            raise RunRefused("the gate said no")

        worker = InProcessWorker(data_root, product_root, runner=refusing)
        worker.submit("neodent-gm", _request(run_id="run-1"))
        with pytest.raises(FileExistsError):
            worker.submit("neodent-gm", _request(run_id="run-1"))


class TestRefusals:
    def test_a_pipeline_refusal_reports_refused_with_the_words_verbatim(
            self, data_root, product_root):
        words = ("package NOT emitted: catastrophic design-rule violation — "
                 "the screw channel breaks out of the wall")

        def refusing(case, selection, out_dir):
            raise RunRefused(words)

        worker = InProcessWorker(data_root, product_root, runner=refusing)
        job_id = worker.submit("neodent-gm", _request())
        status = worker.status(job_id)
        assert status.state is JobState.REFUSED
        assert status.refusal == words  # verbatim — the BFF never paraphrases physics
        with pytest.raises(KeyError):
            worker.result(job_id)  # a refused job has no summary to serve

    def test_a_refused_run_leaves_refusal_json_not_half_artifacts(
            self, data_root, product_root):
        def refusing(case, selection, out_dir):
            # the pipeline got partway: a half-artifact lands before the gate fires
            (Path(out_dir) / "half-aligned.stl").write_text("partial")
            raise RunRefused("no confirmed site could be aligned")

        worker = InProcessWorker(data_root, product_root, runner=refusing)
        worker.submit("neodent-gm", _request(run_id="run-r"))
        run_dir = product_root / "neodent-gm" / "runs" / "run-r"
        assert [p.name for p in run_dir.iterdir()] == ["refusal.json"]
        record = json.loads((run_dir / "refusal.json").read_text())
        assert record["refusal"] == "no confirmed site could be aligned"
        assert record["case_id"] == "neodent-gm"
        assert record["run_id"] == "run-r"

    def test_an_unknown_case_is_a_refusal_too(self, data_root, product_root):
        worker = InProcessWorker(data_root, product_root, runner=_ok_runner(SUMMARY))
        job_id = worker.submit("no-such-case", _request())
        status = worker.status(job_id)
        assert status.state is JobState.REFUSED
        assert "no-such-case" in status.refusal

    def test_a_request_without_a_run_id_is_refused_loudly(
            self, data_root, product_root):
        worker = InProcessWorker(data_root, product_root, runner=_ok_runner(SUMMARY))
        with pytest.raises(ValueError):
            worker.submit("neodent-gm", {"selection": {}})
