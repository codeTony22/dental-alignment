"""THE MESHLIB ADAPTER (this slice, 2026-08-15) — a SECOND concrete
``BooleanKernel`` (``pipeline/kernel.py``'s own port) behind the seam the
boolean-engine plan built for exactly this: a licensed contender a future
process could select without any call site changing. ``MeshLibKernel`` wraps
``meshlib.mrmeshpy``'s MESH boolean (never its voxel path — the evaluation
disqualified voxel outright: it loses a subtraction across a batched call
and produces the SAME silent-no-op failure mode with worse resolution on
top, per ``docs/engagement/meshlib-scoreboard-2026-08.md`` Battery 1). The
conversion bridge (``meshlib.mrmeshnumpy``) is float64-lossless in both
directions per that same evaluation — nothing here reflects a conversion
artifact.

Lazy import, by design: this module imports cleanly whether or not meshlib
is installed (only ``numpy``/``trimesh``/``kernel``'s own ``TrackedResult``
load at import time) — ``MeshLibKernel()`` is the ONE place meshlib itself
is ever imported, and only there. A worker process that never sets
``CASE_PREP_BOOLEAN_KERNEL=meshlib`` never touches the package at all, which
is exactly right for the production venv, which does not carry it and never
will (the free evaluation tier is non-commercial-only; see
``docs/engagement/kernel-decision-memo.md`` §4).

THE GUARD (memo §3.2, "the guard is mandatory, not optional") is
``guard_boolean_output`` below — a plain function over trimesh meshes, with
no meshlib dependency of its own, so it is testable without the package
installed. It is called after EVERY meshlib boolean this adapter performs,
converting MeshLib's two measured failure modes into a loud ``ValueError``
instead of a quiet wrong answer:

  1. an EMPTY result (the fleet's self-heal operands: 16 of 20 real
     ``union(punch, punch)`` calls came back empty under MeshLib, memo
     A.5) — the failure carries an error string on this path, but a
     caller that only checked ``valid()`` or watertightness would still
     ship a package with no recess;
  2. an operand returned UNCHANGED — same face count AND volume within
     1e-9 mm^3 — the coplanar silent-no-op (memo A.1): a watertight
     ``valid()=True`` result that removed nothing, with every one of
     MeshLib's own health signals reporting success.

Known, accepted trade-off (said out loud, matching this repo's own
convention of naming a guard's blind spots rather than hiding them): the
face-count-and-volume test cannot distinguish "MeshLib silently no-opped"
from "the tool genuinely never touched the base" — a difference against a
truly disjoint tool would ALSO trip this guard under this engine, where
``ManifoldKernel`` returns it as a legitimate unchanged result (pinned in
``test_kernel.py``). The memo's own census (§A.5: 0 of 75 distinct-solid
calls ever land on exact coplanarity, closest approach 1.56e-4mm) is why
this trade is acceptable in THIS domain — every real difference call is
expected to remove material — not because the ambiguity is resolved.

PROVENANCE AND OFFSET ARE OUT OF SCOPE FOR THIS ENGINE, ON PURPOSE.
``difference_tracked``/``union_tracked`` raise ``NotImplementedError``:
MeshLib exposes no manifold3d-``originalID`` equivalent, and building one
by measuring face proximity to the original operands would resurrect
exactly the "provenance replaces proximity" defect W1 retired — so this
adapter refuses rather than fakes it. ``minkowski_sphere`` raises
``NotImplementedError`` too: the memo's own offset recommendation is
``sharpOffsetMesh`` (§3.3/§4), a SEPARATE, still-unlicensed capability this
slice does not build.

THE FLUSH-OPERAND DECISION (kernel-parity scoreboard §3, amended 2026-08-15
— "try both engines for real" against the referee corpus itself surfaced
this for the first time, not on paper): a legitimately-flush operand — the
floor clip's plane landing EXACTLY on the cap's own base plane, ``relief ==
0`` — trips guard 2 above (the UNCHANGED coplanar no-op) or comes back
EMPTY, depending on which side of the ±1e-7mm contact this engine's own
retriangulation noise happens to land on (kernel-parity-scoreboard.md §2.1).
DECIDED: ACCEPT THE FALLBACK, never pre-nudge the operand. Moving a
measured, calibrated coordinate by a few times 1e-7mm purely to keep a
SPECIFIC ENGINE happy is exactly the inference the client's own doctrine
forbids ("we should not be inferring anything here" — §10-AS.14) applied to
geometry instead of an offset number; it would also silently make every
future flush contact engine-DEPENDENT (a value nudged to please MeshLib is
a value manifold never asked for). The already-existing consumer-side
fallback — ``_csg_carve``'s per-site ``except Exception`` around
``exact_cap_punch``, landing "its envelope was used instead" — is the
correct, sufficient answer under this engine; nothing in this adapter or
its callers changes to accommodate it. This same acceptance generalises,
by the same reasoning, to every other native MeshLib boolean refusal a
legitimately-shaped operand can trigger under this engine and manifold
cannot — measured directly, this slice's own referee run: a self-
intersecting vertex-normal-dilated punch's own self-heal union (a
genuinely self-intersecting but otherwise unremarkable operand — a screw-
slot cap, nothing degenerate about it) and a fin/deviated-cap's true-
boolean recess cut both trip MeshLib's native ``res.valid() is False``
refusal (kernel-parity-scoreboard.md §2.1/§2.4) where manifold3d succeeds;
in every case the existing fail-open ladder already coded for OTHER
reasons (a manifold3d rejection, an unwatertight tracked result) is what
actually ships, unmodified, under this engine too.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Sequence

import numpy as np
import trimesh

from case_prep.pipeline.kernel import TrackedResult

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    import meshlib.mrmeshpy as mm
    import meshlib.mrmeshnumpy as mn

GUARD_VOLUME_TOLERANCE_MM3 = 1e-9

_TRACKED_PROVENANCE_GAP = (
    "{method} has no MeshLib equivalent: MeshLib exposes no manifold3d-"
    "originalID/run_original_id per-face provenance mechanism (W1, "
    "kernel-decision-memo §3.2), so a tracked boolean cannot be built "
    "under this engine without measuring provenance by distance to the "
    "original operands — exactly the proximity method W1 replaced, and "
    "this adapter will not resurrect it. The documented fallback ladder "
    "for CASE_PREP_BOOLEAN_KERNEL=meshlib is the strip consumers' own "
    "(csg.py's fabricated_face_mask/strip_tracked callers): an untracked "
    "boolean, a distance-based strip, and an honest note on the result — "
    "never faked provenance.")


def guard_boolean_output(op_name: str, operands: Sequence[trimesh.Trimesh],
                         result: trimesh.Trimesh) -> None:
    """THE MANDATORY GUARD (kernel-decision-memo §3.2). Raises
    ``ValueError`` naming ITSELF ("guard" appears in every message) and
    the face count of every operand in ``operands`` if ``result`` is
    either of MeshLib's two measured failure signatures:

      * EMPTY — zero faces;
      * UNCHANGED — the same face count AND the same volume (within
        ``GUARD_VOLUME_TOLERANCE_MM3`` mm^3) as one of ``operands``.

    A pure function over trimesh meshes: no meshlib import, callable —
    and tested — with or without the package present.

    THE FLUSH-OPERAND DECISION (this module's own docstring, kernel-parity
    scoreboard §3, amended 2026-08-15): a legitimately-flush operand (a
    floor clip landing exactly on a coplanar plane, ``relief == 0``) is a
    real, expected trigger of this guard's EMPTY or UNCHANGED branch under
    this engine — never cured by nudging the operand's own coordinates by
    epsilon before the call. This function raises; the caller's own,
    already-documented fallback ladder is where the acceptance lives."""
    face_counts = [len(op.faces) for op in operands]
    if len(result.faces) == 0:
        raise ValueError(
            f"MeshLibKernel.{op_name} guard: MeshLib returned an EMPTY "
            f"result for an operation whose operands were not — operand "
            f"face counts {face_counts}. This is one of the two measured "
            "MeshLib failure modes (kernel-decision-memo §3.2/§A.5) and "
            "is never passed through silently under this engine.")
    out_faces = len(result.faces)
    out_volume = float(result.volume)
    for i, operand in enumerate(operands):
        if len(operand.faces) != out_faces:
            continue
        if abs(float(operand.volume) - out_volume) >= GUARD_VOLUME_TOLERANCE_MM3:
            continue
        raise ValueError(
            f"MeshLibKernel.{op_name} guard: MeshLib silently returned "
            f"operand {i} UNCHANGED (face count {out_faces}, volume "
            f"matches within {GUARD_VOLUME_TOLERANCE_MM3} mm^3) — the "
            "coplanar silent-no-op signature (kernel-decision-memo §3.2, "
            f"§A.1) — operand face counts {face_counts}.")


class MeshLibKernel:
    """MeshLib's MESH (never voxel) boolean behind ``BooleanKernel``.
    Multiple tools/meshes are cascaded as binary calls — ``((a-t0)-t1)``
    for ``difference``, left-fold for ``union`` — because
    ``mrmeshpy.boolean`` is strictly binary; this is set-theoretically
    identical to ``ManifoldKernel``'s batched call (verified on the
    degeneracy corpus's own two-tool case, memo A.1 case #4) and every
    binary step is independently guarded."""

    def __init__(self) -> None:
        try:
            import meshlib.mrmeshpy as mm
            import meshlib.mrmeshnumpy as mn
        except ImportError as exc:
            raise ImportError(
                "MeshLibKernel requires the meshlib package (mrmeshpy/"
                "mrmeshnumpy), which is not importable in this "
                "environment. It is an EVALUATION-tier adapter: the free "
                "tier this repo's own evaluation ran under is non-"
                "commercial only (docs/engagement/kernel-decision-memo.md "
                "§4) — production shipping requires AMV's paid commercial "
                "license. Select this engine only in a trial environment "
                "that has the package installed."
            ) from exc
        self._mm = mm
        self._mn = mn

    def _to_ml(self, tm: trimesh.Trimesh) -> "mm.Mesh":
        return self._mn.meshFromFacesVerts(np.asarray(tm.faces, np.int32),
                                           np.asarray(tm.vertices, np.float64))

    def _from_ml(self, mesh: "mm.Mesh") -> trimesh.Trimesh:
        try:
            mesh.pack()
        except Exception:
            pass
        V = np.asarray(self._mn.getNumpyVerts(mesh), np.float64)
        F = np.asarray(self._mn.getNumpyFaces(mesh.topology), np.int64)
        return trimesh.Trimesh(V, F, process=False)

    def _boolean(self, op_name: str, a: trimesh.Trimesh, b: trimesh.Trimesh,
                op) -> trimesh.Trimesh:
        res = self._mm.boolean(self._to_ml(a), self._to_ml(b), op)
        if not res.valid():
            raise ValueError(
                f"MeshLibKernel.{op_name}: MeshLib refused the operation "
                f"({res.errorString})")
        out = self._from_ml(res.mesh)
        guard_boolean_output(op_name, [a, b], out)
        return out

    def union(self, meshes: Sequence[trimesh.Trimesh]) -> trimesh.Trimesh:
        meshes = list(meshes)
        if not meshes:
            raise ValueError("union needs at least one mesh")
        out = meshes[0]
        for m in meshes[1:]:
            out = self._boolean("union", out, m, self._mm.BooleanOperation.Union)
        return out

    def difference(self, a: trimesh.Trimesh,
                   tools: Sequence[trimesh.Trimesh]) -> trimesh.Trimesh:
        tools = list(tools)
        if not tools:
            raise ValueError("difference needs at least one tool")
        out = a
        for t in tools:
            out = self._boolean("difference", out, t,
                                self._mm.BooleanOperation.DifferenceAB)
        return out

    def intersection(self, a: trimesh.Trimesh,
                     b: trimesh.Trimesh) -> trimesh.Trimesh:
        return self._boolean("intersection", a, b,
                             self._mm.BooleanOperation.Intersection)

    def is_valid_solid(self, mesh: trimesh.Trimesh) -> bool:
        """MeshLib-native (``MeshTopology.isClosed()``), not trimesh's own
        ``is_watertight`` on a round-tripped mesh: this asks the SAME
        representation the booleans themselves run in, rather than a
        second engine's opinion on a mesh that has already been converted
        away from it — one fewer moving part, and the exact check
        ``mlcommon.py``'s own evaluation harness used (``ml_closed``)."""
        return bool(self._to_ml(mesh).topology.isClosed())

    def difference_tracked(self, a: trimesh.Trimesh,
                           tools: Sequence[trimesh.Trimesh],
                           a_groups: Optional[np.ndarray] = None
                           ) -> TrackedResult:
        raise NotImplementedError(
            _TRACKED_PROVENANCE_GAP.format(method="difference_tracked"))

    def union_tracked(self, meshes: Sequence[trimesh.Trimesh],
                      base_groups: Optional[np.ndarray] = None
                      ) -> TrackedResult:
        raise NotImplementedError(
            _TRACKED_PROVENANCE_GAP.format(method="union_tracked"))

    def minkowski_sphere(self, mesh: trimesh.Trimesh, radius: float,
                        subdivisions: int = 3) -> trimesh.Trimesh:
        raise NotImplementedError(
            "minkowski_sphere is not implemented under MeshLibKernel in "
            "this slice. The memo's own recommended offset provider under "
            "this engine is sharpOffsetMesh (kernel-decision-memo §3.3, "
            "§4) — 50-66x faster than manifold's minkowski_sum at equal "
            "or better accuracy — but it is a SEPARATE, still-unlicensed "
            "capability this slice does not build; out of scope here.")

    def supports_tracked(self) -> bool:
        """False — ``difference_tracked``/``union_tracked`` above always
        raise ``NotImplementedError`` (no manifold3d-originalID equivalent
        exists in MeshLib, W1). See ``BooleanKernel.supports_tracked``'s own
        docstring for the scope of what this flag stands in for in the
        referee corpus's own ``engine_expects`` fixture."""
        return False
