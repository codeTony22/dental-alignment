"""THE KERNEL SEAM (boolean-engine plan §6 Stage 0, 2026-08-13): the one port
``case_prep.pipeline.csg`` may call for a boolean operation. Every mesh
boolean ``csg.py`` performs — the self-healing punch's union-with-itself and
the visible-depth floor's box intersection — now goes through this narrow
surface instead of reaching for ``trimesh.boolean`` directly.

Why a seam at all, when nothing behind it changes today: the plan
(``docs/engagement/boolean-engine-plan.md``) prices a from-scratch kernel at
12-24 person-months and finds no licensing emergency in the incumbent
(manifold, Apache-2.0 — already safe to embed, forever). The honest Stage-0
move is not a new engine, it is a PLACE a new engine could go later without
every call site changing. ``ManifoldKernel`` below wraps the EXACT calls
``csg.py`` (and ``deliverables.py``'s own direct booleans) made before this
module existed — same engine string (``engine="manifold"``), same call
shapes — so this refactor changes nothing about what ships; it only names
the boundary a future kernel swap (Stage 2/3) would cross.

The protocol is deliberately narrow: the three operations the choreography
actually performs (union, difference, intersection) plus the validity check
that decides whether a mesh may be handed to any of them. It says nothing
about offsetting, lidding or stripping — those stay exactly where they are,
as clinical choreography in ``csg.py``, because they are the proprietary
layer the plan identifies as ours to keep (§5), not mechanism to swap out
from under.
"""
from __future__ import annotations

from typing import Optional, Protocol, Sequence, runtime_checkable

import trimesh
import trimesh.boolean


@runtime_checkable
class BooleanKernel(Protocol):
    """The only surface a boolean operation may be reached through. Every
    method's shape matches a call the codebase already made: ``union`` over
    a plain list (the fused composite, the self-heal), ``difference`` of one
    base against its tools (the arch cut, the closed model), ``intersection``
    of exactly two operands (the floor clip) — and ``is_valid_solid``, the
    watertightness question every one of those calls implicitly depends on
    its operands answering truthfully."""

    def union(self, meshes: Sequence[trimesh.Trimesh]) -> trimesh.Trimesh:
        ...

    def difference(self, a: trimesh.Trimesh,
                   tools: Sequence[trimesh.Trimesh]) -> trimesh.Trimesh:
        ...

    def intersection(self, a: trimesh.Trimesh,
                     b: trimesh.Trimesh) -> trimesh.Trimesh:
        ...

    def is_valid_solid(self, mesh: trimesh.Trimesh) -> bool:
        ...


class ManifoldKernel:
    """The default, and today's ONLY, ``BooleanKernel`` — trimesh's manifold
    engine, called exactly as the codebase called it before this seam
    existed. A future kernel (a licensed SDK, a from-scratch spike, per the
    plan's Stage 2 evaluation) is a new class here that the Stage-0
    conformance corpus judges against this one's numbers; it is never a
    rewrite of a call site."""

    def union(self, meshes: Sequence[trimesh.Trimesh]) -> trimesh.Trimesh:
        return trimesh.boolean.union(list(meshes), engine="manifold")

    def difference(self, a: trimesh.Trimesh,
                   tools: Sequence[trimesh.Trimesh]) -> trimesh.Trimesh:
        return trimesh.boolean.difference([a, *tools], engine="manifold")

    def intersection(self, a: trimesh.Trimesh,
                     b: trimesh.Trimesh) -> trimesh.Trimesh:
        return trimesh.boolean.intersection([a, b], engine="manifold")

    def is_valid_solid(self, mesh: trimesh.Trimesh) -> bool:
        return bool(mesh.is_watertight)


_default: Optional[BooleanKernel] = None


def default_kernel() -> BooleanKernel:
    """The kernel every caller gets unless a test injects its own — one
    ``ManifoldKernel`` instance for the process. The kernel is stateless, so
    the caching buys nothing behaviourally; it exists so ``default_kernel()
    is default_kernel()`` holds, which is the only property a Stage-1 caller
    could ever come to depend on."""
    global _default
    if _default is None:
        _default = ManifoldKernel()
    return _default
