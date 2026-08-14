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

W1 (§ boolean-engine plan, "provenance replaces proximity in the strip",
2026-08-13) adds a SECOND, narrower surface alongside the first:
``difference_tracked``/``union_tracked``, returning a ``TrackedResult`` whose
per-face ``source`` array says WHICH input solid a face's material came from
— read from manifold3d's own originalID mesh relation, not measured by
distance to anything. Every operand is reserved a fresh id
(``Manifold.reserve_ids``) and built via manifold3d's multi-material ``Mesh``
constructor (``run_index``/``run_original_id``, its own documented route "for
multi-material input... sort the materials into triangle runs") rather than
``Manifold.as_original()`` — that call RESETS a manifold to a single fresh
id, which is right for a plain tool but wrong for the one operand that needs
MULTIPLE distinguishable ids on one physical solid (a solidified shell's own
scan faces vs the closure it fabricated); ``reserve_ids`` handles both
uniformly, so every operand — split or not — goes through the same
construction path. Reading the result is symmetric: the output ``Mesh``'s
``run_original_id``/``run_index`` runs are mapped back to a small
``0..source_count-1`` index per face. This is still mechanism, not
choreography: the tracked ops know nothing of "scan" or "closure" — that
vocabulary is ``csg.py``'s (``fabricated_face_mask``, ``strip_tracked``) —
they only know "operand 0" and "operand 1..n", the same algebraic vocabulary
``difference(a, tools)`` already uses. The untracked union/difference/
intersection methods stay exactly as they are — every existing call site is
untouched by default; the tracked ops are net-new surface, reached for only
by the three strip consumers this plan names.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import (Dict, List, Optional, Protocol, Sequence,
                    runtime_checkable)

import manifold3d
import numpy as np
import trimesh
import trimesh.boolean


@dataclass(frozen=True)
class TrackedResult:
    """A boolean result plus, for every output face, an exact per-face
    SOURCE index read from manifold3d's own face provenance — never a
    distance query. ``mesh`` is the boolean's output; ``source`` is a
    ``len(mesh.faces)`` int array; ``base_groups`` says how many of the
    smallest source values (``0 .. base_groups - 1``) belong to the
    operation's BASE operand (``a`` for ``difference_tracked``,
    ``meshes[0]`` for ``union_tracked``) rather than to a tool/other
    operand.

    Ordinarily ``base_groups`` is 1 (source 0 is the whole base, sources
    1..n are the remaining operands in argument order) — that is what you
    get when the base is handed in with no ``a_groups``/``base_groups``
    split. When the base WAS split (``csg.py``'s scan-vs-fabricated mask is
    the one caller that does this), ``base_groups`` is the number of
    distinct groups given, and every source below it is one of the base's
    own sub-groups (0, 1, ... in the order the group-index array named
    them) — the remaining operands still follow immediately after, at
    source ``base_groups``, ``base_groups + 1``, and so on. A face can
    never carry two sources: the boolean splits every face along every
    intersection curve before a source is ever read off it."""
    mesh: trimesh.Trimesh
    source: np.ndarray
    base_groups: int = 1


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

    def difference_tracked(self, a: trimesh.Trimesh,
                           tools: Sequence[trimesh.Trimesh],
                           a_groups: Optional[np.ndarray] = None
                           ) -> TrackedResult:
        ...

    def union_tracked(self, meshes: Sequence[trimesh.Trimesh],
                      base_groups: Optional[np.ndarray] = None
                      ) -> TrackedResult:
        ...


def _reserved_ids(n: int) -> List[int]:
    """``n`` fresh, distinct manifold3d original ids, as a plain list — the
    single-int-return-of-the-first-id shape of ``Manifold.reserve_ids``
    turned into something a caller can zip against ``0..n-1`` without
    re-deriving the offset at every call site."""
    first = manifold3d.Manifold.reserve_ids(n)
    return list(range(first, first + n))


def _grouped_manifold(mesh: trimesh.Trimesh, groups: np.ndarray
                      ) -> "tuple[manifold3d.Manifold, List[int]]":
    """``mesh`` as a manifold3d ``Manifold`` carrying one originalID PER
    DISTINCT VALUE in ``groups`` — a per-face int array, ``0 .. k-1``, one
    entry per ``mesh.faces`` row. A single physical solid can carry several
    provenance runs this way (manifold3d's own multi-material ``Mesh``
    constructor: ``run_index``/``run_original_id``, "sort the materials into
    triangle runs"), which is exactly what lets ``csg.py`` tag a solidified
    shell's SCAN faces and its FABRICATED closure faces as two distinct,
    trackable origins without ever measuring a distance. Faces are
    reordered by a stable sort on ``groups`` first — manifold3d requires
    each run to be contiguous — which changes nothing about the solid's
    shape, only which row of ``tri_verts`` each triangle sits in.

    Returns the tagged manifold plus the reserved ids, index-aligned with
    group values ``0..k-1`` (``ids[g]`` is the originalID for group ``g``).
    Raises if manifold3d refuses the input outright (NaN vertices, a
    non-manifold solid, …) — the fail-open ladder belongs to the caller,
    not to this helper."""
    faces = np.asarray(mesh.faces)
    groups = np.asarray(groups, dtype=np.int64)
    if len(groups) != len(faces):
        raise ValueError(
            f"groups has {len(groups)} entries for {len(faces)} faces")
    k = int(groups.max()) + 1 if len(groups) else 1
    ids = _reserved_ids(k)
    order = np.argsort(groups, kind="stable")
    counts = np.bincount(groups, minlength=k) if len(groups) else np.zeros(k, int)
    run_index = np.zeros(k + 1, np.uint32)
    run_index[1:] = np.cumsum(counts) * 3
    gl_mesh = manifold3d.Mesh(
        vert_properties=np.asarray(mesh.vertices, dtype=np.float32),
        tri_verts=faces[order].astype(np.uint32),
        run_index=run_index,
        run_original_id=np.asarray(ids, dtype=np.uint32))
    man = manifold3d.Manifold(gl_mesh)
    if man.status() != manifold3d.Error.NoError:
        raise ValueError(f"manifold3d rejected an input solid ({man.status()})")
    return man, ids


def _source_from_runs(out_mesh: "manifold3d.Mesh", id_to_source: Dict[int, int]
                      ) -> np.ndarray:
    """The per-face ``source`` array a ``TrackedResult`` carries, read off a
    boolean's own output ``Mesh``: ``run_original_id``/``run_index`` name
    which originalID owns which contiguous slice of ``tri_verts`` — in
    HALFEDGE units (3x the triangle index; verified against the installed
    manifold3d 3.5.2 binding, undocumented in the docstring itself), so the
    slice bounds are divided by 3 before indexing. Every triangle must
    resolve to a tagged id or this raises — a silent ``-1`` surviving into a
    strip decision is exactly the failure mode provenance exists to rule
    out."""
    n_tri = int(np.asarray(out_mesh.tri_verts).shape[0])
    source = np.full(n_tri, -1, dtype=np.int64)
    run_ids = out_mesh.run_original_id
    run_index = out_mesh.run_index
    for i, oid in enumerate(run_ids):
        lo, hi = run_index[i] // 3, run_index[i + 1] // 3
        src = id_to_source.get(int(oid))
        if src is None:
            raise ValueError(
                f"a boolean output run (original id {oid}) traces to no "
                "tagged input — provenance is broken")
        source[lo:hi] = src
    if (source < 0).any():
        raise ValueError(
            "a boolean output face carries no source provenance at all")
    return source


def _mesh_from_gl(out_mesh: "manifold3d.Mesh") -> trimesh.Trimesh:
    return trimesh.Trimesh(np.asarray(out_mesh.vert_properties, dtype=np.float64),
                           np.asarray(out_mesh.tri_verts, dtype=np.int64),
                           process=False)


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

    def difference_tracked(self, a: trimesh.Trimesh,
                           tools: Sequence[trimesh.Trimesh],
                           a_groups: Optional[np.ndarray] = None
                           ) -> TrackedResult:
        """``a - tools[0] - tools[1] - ...`` (manifold3d's own
        ``batch_boolean(Subtract)`` cascade, not trimesh's union-the-tools-
        first shortcut — set-theoretically identical, verified equal in
        volume on an overlapping two-tool fixture at kernel-pin time), with
        every output face labelled by which operand contributed its
        material. ``a_groups``, when given, is a ``len(a.faces)`` int array
        (``0..k-1``) splitting ``a`` itself into ``k`` distinguishable
        sources before the boolean runs (``csg.py``'s scan/fabricated
        split); the tools always get one source each, immediately after
        ``a``'s own ``k`` (or 1, with no split)."""
        if not tools:
            raise ValueError("difference_tracked needs at least one tool")
        a_groups = (np.zeros(len(a.faces), dtype=np.int64) if a_groups is None
                    else np.asarray(a_groups, dtype=np.int64))
        a_man, a_ids = _grouped_manifold(a, a_groups)
        id_to_source: Dict[int, int] = {aid: g for g, aid in enumerate(a_ids)}
        operands = [a_man]
        next_source = len(a_ids)
        for tool in tools:
            t_man, t_ids = _grouped_manifold(
                tool, np.zeros(len(tool.faces), dtype=np.int64))
            id_to_source[t_ids[0]] = next_source
            next_source += 1
            operands.append(t_man)
        result = manifold3d.Manifold.batch_boolean(operands,
                                                    manifold3d.OpType.Subtract)
        if result.status() != manifold3d.Error.NoError:
            raise ValueError(f"manifold3d difference failed ({result.status()})")
        out = result.to_mesh()
        return TrackedResult(mesh=_mesh_from_gl(out),
                             source=_source_from_runs(out, id_to_source),
                             base_groups=len(a_ids))

    def union_tracked(self, meshes: Sequence[trimesh.Trimesh],
                      base_groups: Optional[np.ndarray] = None
                      ) -> TrackedResult:
        """The union of every mesh in ``meshes``, labelled the same way
        ``difference_tracked`` is: ``base_groups``, when given, is a
        ``len(meshes[0].faces)`` int array splitting the FIRST mesh (the
        arch's own solidified shell, at every call site this plan adds) into
        distinguishable sources before the union runs; every other mesh in
        ``meshes`` gets one source each, immediately after."""
        if not meshes:
            raise ValueError("union_tracked needs at least one mesh")
        base = meshes[0]
        base_groups = (np.zeros(len(base.faces), dtype=np.int64)
                       if base_groups is None
                       else np.asarray(base_groups, dtype=np.int64))
        base_man, base_ids = _grouped_manifold(base, base_groups)
        id_to_source: Dict[int, int] = {bid: g for g, bid in enumerate(base_ids)}
        operands = [base_man]
        next_source = len(base_ids)
        for mesh in meshes[1:]:
            m_man, m_ids = _grouped_manifold(
                mesh, np.zeros(len(mesh.faces), dtype=np.int64))
            id_to_source[m_ids[0]] = next_source
            next_source += 1
            operands.append(m_man)
        result = manifold3d.Manifold.batch_boolean(operands,
                                                    manifold3d.OpType.Add)
        if result.status() != manifold3d.Error.NoError:
            raise ValueError(f"manifold3d union failed ({result.status()})")
        out = result.to_mesh()
        return TrackedResult(mesh=_mesh_from_gl(out),
                             source=_source_from_runs(out, id_to_source),
                             base_groups=len(base_ids))


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
