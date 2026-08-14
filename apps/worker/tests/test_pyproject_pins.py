"""Determinism pins in pyproject.toml (boolean-engine plan W4/Stage 0).

``numpy``/``scipy``/``trimesh``/``manifold3d`` are pinned EXACT already (2026-08-13):
the geometry stack a kernel swap or a boolean result could be sensitive to. matplotlib
joined them 2026-08-14 — it is imported at RUNTIME (``adapters/qc_render.py``, never
gated behind a dev-only code path) and stamps its OWN version string into every PNG it
writes (the ``Software`` metadata tag), and both PNGs ride in the hashed manifest — an
unpinned matplotlib bump changes sealed hashes with no geometry change behind it.

Text-matched against ``pyproject.toml`` rather than parsed with a TOML library: no TOML
parser is a declared project dependency (``tomllib`` is 3.11+, this venv runs 3.9), and a
plain read keeps this test from acquiring one for a single pin check.
"""
from __future__ import annotations

import re
from pathlib import Path

import matplotlib

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def _section(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def test_matplotlib_is_pinned_exact_as_a_runtime_dependency():
    text = PYPROJECT.read_text()
    deps = _section(text, "dependencies = [", "[project.optional-dependencies]")
    match = re.search(r'"matplotlib==([0-9][^"]*)"', deps)
    assert match is not None, (
        "matplotlib must be pinned EXACT in [project.dependencies] — it is a "
        "runtime import (adapters/qc_render.py) whose version rides inside "
        "manifest-sealed PNGs, the same hazard the numpy/scipy/trimesh/manifold3d "
        "pins above it exist to close")
    assert match.group(1) == matplotlib.__version__, (
        f"pyproject pins matplotlib=={match.group(1)} but this venv runs "
        f"{matplotlib.__version__} — re-pin to what `.venv/bin/python -c "
        f'"import matplotlib; print(matplotlib.__version__)"` reports, the same '
        "way the four pins beside it were read")


def test_matplotlib_does_not_also_ride_the_dev_extra():
    """The defect this slice retires: a RUNTIME dependency declared only as dev
    tooling. A ``matplotlib`` entry surviving in the ``dev`` LIST (as opposed to
    this file's own prose explaining why it doesn't) would be a second, unpinned
    place the version could arrive from — one pin, one place."""
    text = PYPROJECT.read_text()
    dev_list = _section(text, "dev = [", "]")
    assert "matplotlib" not in dev_list, \
        "matplotlib belongs to [project.dependencies] only, pinned exact"
