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

import enum
from dataclasses import dataclass
from typing import Any, Optional, Protocol


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


class WorkerPort(Protocol):
    """What the BFF is allowed to ask of the processing tier. Nothing else exists."""

    def submit(self, case_id: str, request: dict[str, Any]) -> str:
        """Queue a full alignment run. Returns a job id immediately."""
        ...

    def status(self, job_id: str) -> JobStatus: ...

    def result(self, job_id: str) -> dict[str, Any]:
        """The completed job's summary payload. Raises KeyError for unknown/unfinished jobs."""
        ...
