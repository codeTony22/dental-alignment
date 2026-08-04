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
from case_prep.application.emit import emit_from_poses
from case_prep.application.run import RunRefused, RunSelection, run_case


class JobState(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    # A refusal is a first-class outcome, not an error: the pipeline saying "no" with a reason
    # (a gate, a validation, an unshippable part) is the product working as designed.
    REFUSED = "refused"
    # A crash is NEITHER a verdict nor a refusal: the physics never reached an answer (a
    # numpy error deep in alignment, disk-full mid-emission). It is a job STATE by
    # necessity, not taste — phase-2's queue adapter returns from ``submit`` before the
    # physics starts, so a crash can only ever surface as a status writeback, and an
    # in-process adapter that raised instead would hand the resources above it a second,
    # different contract (AM-3 forbids exactly that). Before this state existed, an
    # escaping crash wedged the session's queued receipt forever and abandoned
    # half-artifacts in the immutable run dir (the 5c verification's refuted claim).
    FAILED = "failed"


@dataclass(frozen=True)
class JobStatus:
    job_id: str
    state: JobState
    # The refusal's reason in the worker's own words, verbatim — the BFF never paraphrases
    # physics. None unless state is REFUSED.
    refusal: Optional[str] = None
    # The crash's words (exception type + message); None unless state is FAILED. Kept
    # DISTINCT from ``refusal``: a refusal is the product working as designed, a failure
    # is it breaking — conflating them would let a stack trace masquerade as a verdict.
    error: Optional[str] = None
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
    error: Optional[str] = None
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
    normally pre-empts but which stay honest answers if reached). Anything ELSE the
    physics raises is CONTAINED as a FAILED status with ``failure.json`` as the run
    dir's whole content — a crash may never escape ``submit``, because phase-2's
    queue adapter cannot raise a later crash from ``submit`` either, and the resource
    above must see one contract (AM-3). The ``runner`` is injectable for the port
    tests; the wired default is the application lift.
    """

    def __init__(self, data_root: Path, product_root: Path,
                 runner: Callable[[CaseRecord, RunSelection, Path], dict] = run_case,
                 reemitter: Callable[[CaseRecord, RunSelection, Path, Path],
                                     dict] = emit_from_poses):
        self._data_root = Path(data_root)
        self._product_root = Path(product_root)
        self._runner = runner
        # the §10-AC re-emit lane — injectable exactly like the runner, wired to
        # the application lift by default
        self._reemitter = reemitter
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
                         error=job.error, queued_at=job.queued_at,
                         started_at=job.started_at, finished_at=job.finished_at)

    def result(self, job_id: str) -> dict[str, Any]:
        job = self._jobs[job_id]
        if job.state is not JobState.DONE or job.summary is None:
            raise KeyError(f"job {job_id!r} has no result: it is {job.state.value}")
        return job.summary

    # --- internals ----------------------------------------------------------------

    def _execute(self, case_id: str, job: _Job, run_dir: Path) -> None:
        job.state = JobState.RUNNING
        job.started_at = _now()
        try:
            # mkdir INSIDE the containment: a filesystem failure here is a crashed
            # job too, not an escape through ``submit``
            run_dir.mkdir(parents=True)
            case = next((c for c in discover_cases(self._data_root)
                         if c.id == case_id), None)
            if case is None:
                raise RunRefused(f"unknown case {case_id!r} — nothing to run")
            if job.request.get("mode") == "reemit":
                # THE RE-EMIT (§10-AC): same containment, same job shape — a
                # refusal from the design/relief gates lands as a REFUSED run on
                # the surfaces that already render refusals. The source run is
                # read-only history; the poses come out of its implant.json.
                source_run_id = job.request.get("source_run_id")
                if not isinstance(source_run_id, str) or not source_run_id:
                    raise RunRefused("a re-emit request must name its source run "
                                     "— the poses come out of that run's package")
                source_dir = (self._product_root / case_id / "runs"
                              / source_run_id)
                job.summary = self._reemitter(case, self._selection(job.request),
                                              source_dir, run_dir)
            else:
                job.summary = self._runner(case, self._selection(job.request),
                                           run_dir)
            job.state = JobState.DONE
        except (RunRefused, UnknownSelection, ScanUnreadable) as exc:
            job.state = JobState.REFUSED
            job.refusal = str(exc)
            self._leave_refusal(run_dir, case_id, job)
        except Exception as exc:   # noqa: BLE001 — the containment IS the point
            # THE CRASH CONTAINMENT (the 5c verification's refuted claim): an
            # UNEXPECTED exception — numpy deep in the physics, disk-full
            # mid-emission — is a FAILED terminal state, never an escape. Escaping
            # here left the caller's queued receipt stranded (a wedged case with no
            # recovery route) and half-artifacts abandoned in the immutable run dir.
            job.state = JobState.FAILED
            job.error = f"{type(exc).__name__}: {exc}"
            self._leave_failure(run_dir, case_id, job)
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
            # the operator's own centres, for sites detection missed (2026-07-28) —
            # carried like every other act in this selection, so the run needs no
            # second source and the case record stays what the ingest produced
            marked_centers={int(t): [float(c) for c in centre]
                            for t, centre in (sel.get("marked_centers")
                                              or {}).items()},
            # the operator's persisted marks/pairs/best-fits (§10-AD) — carried
            # like the centres, re-applied by the run after automation
            alignment_evidence={int(t): list(entries)
                                for t, entries in (sel.get("alignment_evidence")
                                                   or {}).items()},
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

    @staticmethod
    def _leave_failure(run_dir: Path, case_id: str, job: _Job) -> None:
        """A crashed run's directory holds ``failure.json`` and NOTHING else — the
        same honesty ``_leave_refusal`` gives a refusal (AM-1's honesty half): a
        later reader must never mistake whatever landed before the crash for a
        package. Best-effort ON PURPOSE: when the crash IS the filesystem (disk
        full, permissions, the mkdir itself), cleanup can fail too — and the FAILED
        status carrying the ORIGINAL error must stand, so a cleanup error is
        swallowed rather than allowed to escape and mask the crash it records."""
        try:
            if not run_dir.is_dir():
                return   # the crash was the mkdir itself — nothing ever landed
            for child in run_dir.iterdir():
                shutil.rmtree(child) if child.is_dir() else child.unlink()
            (run_dir / "failure.json").write_text(json.dumps({
                "case_id": case_id, "run_id": job.job_id, "error": job.error,
                "failed_at": _now(),
            }, indent=2))
        except OSError:
            pass
