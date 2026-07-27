"""THE WORKER PORT — the BFF's ONLY doorway to the physics (plan §3, grill AM-3).

Job-shaped from day one, deliberately: ``submit → job_id``, ``status``, ``result`` mirror the
phase-2 SQS/status-writeback semantics (`docs/engagement/phase2-aws-infrastructure-plan.md`),
so the product app renders ``queued|running|done|refused`` states from its first slice and the
eventual queue adapter replaces THIS FILE, not every resource contract built on top of it.

Two rules, both enforced by tests in ``tests/test_boundaries.py``:

1. The BFF imports ONLY ``case_prep.pipeline`` / ``case_prep.domain`` / ``case_prep.adapters``
   (and, once it exists, ``case_prep.application``). **``case_prep.server`` is forbidden** — it
   is the FROZEN demo's HTTP surface, and importing it boots the demo's module state (its case
   table, app, CORS, response caches) and its always-emit handlers aimed at the demo's own data
   plane. The grill rejected exactly that shortcut (plan §9).
2. Everything the BFF writes lives under ``reports/product/``; ``reports/live-demo`` belongs to
   the frozen demo, and slice 1's freeze-guard test asserts it stays byte-identical.
"""
from __future__ import annotations

import copy
import datetime
import enum
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Protocol

from case_prep.application.cases import CaseRecord, discover_cases
from case_prep.application.catalog import UnknownSelection
from case_prep.application.detection import ScanUnreadable
from case_prep.application.run import RunRefused, RunSelection, run_case


class JobState(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    # A refusal is a first-class outcome, not an error: the pipeline saying "no" with a reason
    # (a gate, a validation, an unshippable part) is the product working as designed.
    REFUSED = "refused"


@dataclass(frozen=True)
class JobStatus:
    job_id: str
    state: JobState
    # The refusal's reason in the worker's own words, verbatim — the BFF never paraphrases
    # physics. None unless state is REFUSED.
    refusal: Optional[str] = None
    # The writeback timestamps (ISO-8601), mirroring phase-2's processing_jobs columns
    # (queued_at/started_at/finished_at) so the SQS adapter later fills the SAME fields.
    queued_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class WorkerPort(Protocol):
    """What the BFF is allowed to ask of the processing tier. Nothing else exists."""

    def submit(self, case_id: str, request: dict[str, Any]) -> str:
        """Queue a full alignment run. Returns a job id immediately."""
        ...

    def status(self, job_id: str) -> JobStatus: ...

    def result(self, job_id: str) -> dict[str, Any]:
        """The completed job's summary payload. Raises KeyError for unknown/unfinished jobs."""
        ...


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


@dataclass
class _Job:
    """One job's whole record — private to the adapter; ``status()`` projects it."""

    job_id: str
    request: dict[str, Any]        # snapshotted at submit (the queue will serialize here)
    state: JobState
    refusal: Optional[str] = None
    summary: Optional[dict] = None
    queued_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class InProcessWorker:
    """The day-one adapter (plan §3/AM-3): ``submit`` runs ``application.run.run_case``
    SYNCHRONOUSLY but records the job-shaped truth — queued→running→done|refused with
    timestamps — so every resource built on the port already speaks the queue's
    language and the SQS adapter later replaces THIS CLASS, nothing above it.

    THE RUN DIRECTORY IS THE ADAPTER'S CONTRACT (plan §1.2/AM-1): the request names a
    BFF-minted ``run_id``; the run lands in ``<product_root>/<case>/runs/<run_id>/``,
    created here exactly once — an existing directory REFUSES before any physics runs,
    because nothing ever writes into an existing run dir (a re-run is a NEW id). A
    refused run leaves ``refusal.json`` as the directory's whole content: half-emitted
    artifacts are DELETED rather than left pretending to be a package the gate never
    let out.

    Refusals are first-class: the pipeline's own words land verbatim on the status
    (``RunRefused`` — the gates, "no confirmed site could be aligned" — and the
    catalog/scan refusals ``UnknownSelection``/``ScanUnreadable``, which the run gate
    normally pre-empts but which stay honest answers if reached). The ``runner`` is
    injectable for the port tests; the wired default is the application lift.
    """

    def __init__(self, data_root: Path, product_root: Path,
                 runner: Callable[[CaseRecord, RunSelection, Path], dict] = run_case):
        self._data_root = Path(data_root)
        self._product_root = Path(product_root)
        self._runner = runner
        self._jobs: Dict[str, _Job] = {}

    # --- the port -----------------------------------------------------------------

    def submit(self, case_id: str, request: dict[str, Any]) -> str:
        request = copy.deepcopy(request)   # the job's record, not the caller's object
        run_id = request.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("a run request must carry the BFF-minted run_id — the "
                             "run directory's immutable name (AM-1)")
        run_dir = self._product_root / case_id / "runs" / run_id
        if run_dir.exists():
            raise FileExistsError(
                f"run directory {run_dir} already exists — run directories are "
                f"immutable (AM-1): nothing ever writes into an existing run; a "
                f"re-run mints a new run_id")
        job = _Job(job_id=run_id, request=request, state=JobState.QUEUED,
                   queued_at=_now())
        self._jobs[job.job_id] = job
        self._execute(case_id, job, run_dir)
        return job.job_id

    def status(self, job_id: str) -> JobStatus:
        job = self._jobs[job_id]
        return JobStatus(job_id=job.job_id, state=job.state, refusal=job.refusal,
                         queued_at=job.queued_at, started_at=job.started_at,
                         finished_at=job.finished_at)

    def result(self, job_id: str) -> dict[str, Any]:
        job = self._jobs[job_id]
        if job.state is not JobState.DONE or job.summary is None:
            raise KeyError(f"job {job_id!r} has no result: it is {job.state.value}")
        return job.summary

    # --- internals ----------------------------------------------------------------

    def _execute(self, case_id: str, job: _Job, run_dir: Path) -> None:
        job.state = JobState.RUNNING
        job.started_at = _now()
        run_dir.mkdir(parents=True)
        try:
            case = next((c for c in discover_cases(self._data_root)
                         if c.id == case_id), None)
            if case is None:
                raise RunRefused(f"unknown case {case_id!r} — nothing to run")
            job.summary = self._runner(case, self._selection(job.request), run_dir)
            job.state = JobState.DONE
        except (RunRefused, UnknownSelection, ScanUnreadable) as exc:
            job.state = JobState.REFUSED
            job.refusal = str(exc)
            self._leave_refusal(run_dir, case_id, job)
        finally:
            job.finished_at = _now()

    @staticmethod
    def _selection(request: dict[str, Any]) -> RunSelection:
        sel = request.get("selection") or {}
        return RunSelection(
            model=sel.get("model"),
            construction_path=sel.get("construction_path"),
            variants={int(t): v for t, v in (sel.get("variants") or {}).items()},
            jaw=sel.get("jaw"),
            gingival_offset_mm=float(sel.get("gingival_offset_mm", 0.0)),
        )

    @staticmethod
    def _leave_refusal(run_dir: Path, case_id: str, job: _Job) -> None:
        """A refused run's directory holds the refusal and NOTHING else: whatever the
        pipeline emitted before its gate fired is deleted — half-artifacts must never
        sit where a later reader expects a package (AM-1's honesty half)."""
        for child in run_dir.iterdir():
            shutil.rmtree(child) if child.is_dir() else child.unlink()
        (run_dir / "refusal.json").write_text(json.dumps({
            "case_id": case_id, "run_id": job.job_id, "refusal": job.refusal,
            "refused_at": _now(),
        }, indent=2))
