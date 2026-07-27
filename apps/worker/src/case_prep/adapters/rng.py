"""The pipeline's ONE source of randomness, owned instead of borrowed.

WHY THIS EXISTS
---------------
Surface sampling (``trimesh.sample.sample_surface``) is the only randomness the seating
pipeline consumes, and it draws from numpy's PROCESS-GLOBAL stream. That makes a run's
poses a function of whatever else touched ``np.random`` first — another case in the same
process, a test that seeded for its own fixture, an offline benchmark's ``np.random.seed(0)``.
``run_auto_case`` papered over it by re-seeding the global stream on entry, which works
only as long as every caller is single-threaded, one-case-at-a-time, and nothing in a
downstream stage reseeds. Callers OUTSIDE that discipline saw it: repeated re-runs of the
same input disagreed in the third significant figure.

THE SEAM
--------
``PipelineRng`` owns a stream and hands out draws. Nothing in the pipeline reads or writes
ambient global state; ``run_auto_case(rng=PipelineRng(seed=...))`` makes the run's
randomness an explicit, inspectable input like any other.

WHY IT BORROWS THE GLOBAL SLOT FOR THE DURATION OF ONE CALL
-----------------------------------------------------------
``trimesh.sample_surface`` accepts only an ``int`` seed, from which it builds a FRESH
generator per call — so every call with the same count would draw the SAME points, and
routing through it would change every calibrated number in the codebase. The alternative
(reimplementing trimesh's triangle-point-picking here) forks a third-party algorithm we
would then have to keep in sync.

So the adapter swaps its OWN state into the global slot, makes the call, saves the advanced
state back, and restores whatever was there before. Two consequences, both deliberate:

  * the draw sequence is byte-identical to the previously-shipped ``np.random.seed(0)``
    behaviour (same MT19937, same seed, same call order), so this is a ZERO-DIFF change to
    every pose, coverage and residual the pipeline has ever been calibrated against;
  * ambient global state is left exactly as found, so a caller that seeded for its own
    reasons is not trampled — and, the point of the exercise, cannot trample us.

This is the same save/restore discipline already used ad hoc in ``adapters/qc_render``,
``domain/clock_signature`` and ``pipeline/final_product``; those shims keep working
untouched until their callers migrate to an injected rng.

It lives in ``adapters`` because it wraps a third-party sampler: both the pipeline and
``adapters/open3d_engine`` (whose registration ICP samples the library mesh) draw from
it, and adapters must not have to import the pipeline to do so.

NOT THREAD-SAFE, and honestly so: two runs sharing a process must not share a
``PipelineRng`` (nor could they share the global stream before this existed).
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import trimesh

# The pipeline's shipped seed. Changing it re-rolls every sampled surface and therefore
# every coverage/residual number the acceptance bands were calibrated on — a deliberate
# bound change, not a tuning knob.
DEFAULT_SEED = 0


class PipelineRng:
    """An owned, seeded random stream for one pipeline run.

    ``sample_surface`` is the only channel the seating pipeline needs. ``generator`` is
    there for NEW code, which has no byte-compatibility debt and should use the modern
    ``np.random.Generator`` API.
    """

    __slots__ = ("_seed", "_state", "_generator")

    def __init__(self, seed: int = DEFAULT_SEED) -> None:
        self._seed = int(seed)
        # legacy MT19937, matching what np.random.seed(seed) installs — see the module
        # docstring for why the byte-compatible stream is the required one here
        self._state = np.random.RandomState(self._seed).get_state()
        self._generator: Optional[np.random.Generator] = None

    @property
    def seed(self) -> int:
        return self._seed

    def sample_surface(self, mesh: trimesh.Trimesh, count: int) -> np.ndarray:
        """``count`` points on ``mesh``'s surface, drawn from THIS stream.

        Returns the points only — every call site in the pipeline discards the face
        indices, and returning them invited the ``sampled, _ =`` unpacking that made the
        draws easy to miss while grepping for randomness.
        """
        outer = np.random.get_state()
        np.random.set_state(self._state)
        try:
            sampled, _ = trimesh.sample.sample_surface(mesh, count)
        finally:
            # advance OUR stream, then hand the global slot back exactly as found —
            # even if the sampling raised
            self._state = np.random.get_state()
            np.random.set_state(outer)
        return np.asarray(sampled, float)

    def generator(self) -> np.random.Generator:
        """A ``np.random.Generator`` for code with no legacy-stream obligation. Created
        once per instance and reused, so it advances like any other owned stream."""
        if self._generator is None:
            self._generator = np.random.default_rng(self._seed)
        return self._generator


def sample_surface(rng: Optional[PipelineRng], mesh: trimesh.Trimesh,
                   count: int) -> np.ndarray:
    """MIGRATION SHIM. Draw from the injected stream when the caller was given one;
    otherwise from the process-global stream exactly as before.

    Helpers like ``auto_flow._rim_seat`` are shared between the pipeline (which now
    injects) and callers that have not migrated yet (``server.best_fit``, the offline
    strategy benchmarks, unit tests that call them directly). Those callers keep their
    old behaviour — including their own local seed/restore shims — instead of being
    forced to thread an rng through in the same change. Delete this shim, and the
    ``Optional`` on every ``rng`` parameter, once nothing passes ``None``.
    """
    if rng is not None:
        return rng.sample_surface(mesh, count)
    sampled, _ = trimesh.sample.sample_surface(mesh, count)
    return np.asarray(sampled, float)
