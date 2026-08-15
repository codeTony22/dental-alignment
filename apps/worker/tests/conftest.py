"""Test bootstrap. Suppress third-party import-time env noise before any heavy
import (trimesh -> urllib3 warns about LibreSSL on macOS system python). This is
environmental, not a signal about our code.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Sequence

import pytest

warnings.filterwarnings("ignore", message=".*OpenSSL.*")
warnings.filterwarnings("ignore", message=".*LibreSSL.*")


@dataclass(frozen=True)
class EngineExpectations:
    """THE ENGINE-AWARE SHARED FIXTURE (kernel-parity-scoreboard.md, item 1,
    2026-08-15): ONE capability read — ``default_kernel().supports_tracked()``
    — plus the ONE assertion helper every engine-aware pin in the referee
    corpus (``test_kernel.py test_csg.py test_csg_corpus.py
    test_degeneracy.py test_deliverables.py``) shares, so a test branches
    honestly on what THIS process's kernel can do instead of
    try/except-probing the tracked ops itself. See ``BooleanKernel.
    supports_tracked``'s own docstring (``pipeline/kernel.py``) for the
    precise scope of what this one flag stands in for across this corpus's
    three capability axes (tracked provenance, the ``minkowski`` offset
    engine, and native-refusal robustness on self-intersecting/coplanar
    operands) in today's two-kernel world.

    ``tracked`` is read once per test via the ``engine_expects`` fixture
    below. The manifold-path (``tracked=True``) branch of every pin this
    slice touches is the ORIGINAL, unweakened assertion, verbatim — this
    dataclass only ever adds the non-tracked branch's own verification, it
    never dilutes the tracked one."""
    tracked: bool

    def assert_fallback_notes(self, notes: Sequence[str],
                              *substrings: str) -> None:
        """For the non-tracked-kernel branch only: ``notes`` must carry
        EXACTLY ``len(substrings)`` entries, each containing its own
        corresponding substring, IN ORDER (every production fallback
        ladder this corpus exercises appends its own note strictly after
        any earlier site/part note, so order is a checkable part of the
        contract). Content, not just presence, is checked — "the note IS
        the contract" (kernel-parity task, item 1): a wrong-shaped or
        wrong-count note list is exactly as much a failure here as a
        missing one."""
        assert not self.tracked, (
            "assert_fallback_notes verifies the FALLBACK shape — call it "
            "only when engine_expects.tracked is False")
        notes = list(notes)
        assert len(notes) == len(substrings), (
            f"expected {len(substrings)} fallback note(s) under the "
            f"non-tracked kernel, got {len(notes)}: {notes}")
        for note, substring in zip(notes, substrings):
            assert substring in note, (
                f"fallback note missing expected content {substring!r}: "
                f"{note!r}")


@pytest.fixture
def engine_expects() -> EngineExpectations:
    """The one place every engine-aware referee pin reads the process's
    boolean-kernel capability (kernel-parity-scoreboard.md, item 1)."""
    from case_prep.pipeline.kernel import default_kernel

    return EngineExpectations(tracked=default_kernel().supports_tracked())
