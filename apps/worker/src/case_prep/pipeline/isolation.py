"""THE SCANNED-CAP ISOLATION — clinical pipeline plan Stage 2 slice 2a (boolean plan
4d): "the isolation becomes an artifact." Pane 2 of the product's two-pane workspace
already isolates the healing cap client-side, by an honest ladder — the caption naming
the rung in use (``apps/product/src/domain/declare.ts``'s ``scanPaneCapCylinder``,
``packages/viewer/src/viewer/meshDistance.ts``'s ``cropCapIsolation``). This module is
that same MATCHED rung, run server-side once per resolved site, so the lab can download
exactly what the scanner saw of the cap — ``{case}-{tooth}-scanned-cap.stl`` — and
inspect it outside our viewer.

THE KEEP RULE, mirrored from the client's exact contract (three rungs, each strictly
weaker than the last):

1. **Cylinder pre-cut**: a whole scan triangle survives when ANY of its three vertices
   sits within ``rim_r`` (the catalog rim radius) of the site's pose axis, radially —
   the same "ANY vertex" whole-triangle rule as ``cropTrianglesInCylinder``. Unlike the
   client's display cylinder, this pre-cut carries no axial (above/below) bound: it is
   the same infinite-line cylinder the core-keep rule below already commits to, and a
   single-arch scan never puts unrelated surface on that line.
2. **Template-matched band**: outside the core (below), a triangle survives only when a
   vertex sits within ``CAP_MATCH_BAND_MM`` of the POSED library cap's own surface —
   sampled densely (``trimesh.sample.sample_surface`` + every template vertex, queried
   through a ``scipy.spatial.cKDTree`` — the same idiom ``pipeline.csg.strip_fabricated``
   uses to judge a face against the original scan surface).
3. **CORE-KEEP** (the client-ruled correction, §10-AT front 1 corrected, 2026-08-11):
   inside a core radius of ``max(rim_r - 1.0, 1.2)``mm about the axis, a triangle
   survives UNCONDITIONALLY — the scanned screw-recess interior has no template
   counterpart (the template is a solid CAD cap; the scan's recess is a void), and a
   pure template-distance band would carve a hole in the cap itself. This rule is
   axis-radial only, exactly like ``cropCapIsolation``'s own core test — it does not
   re-check the axial bound the pre-cut already applied.

Nothing is moved and nothing is resliced: every surviving triangle keeps the scan's own
vertex coordinates exactly (``update_faces`` + ``remove_unreferenced_vertices``, never a
weld or a re-normal). A pathological pose that catches nothing returns ``None`` — the
caller's job, not this module's, to turn that into an honest per-site note.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import trimesh
from scipy.spatial import cKDTree

# THE TEMPLATE-MATCH BAND (§10-AT front 1): identical to the client's
# ``CAP_MATCH_BAND_MM`` (``apps/product/src/domain/declare.ts``) — the site's relief
# (0.2) + the fleet's seat deviation p90 (~0.36) + tessellation sampling slack. The two
# must never drift apart: the served artifact is the SAME rung the pane's caption names.
CAP_MATCH_BAND_MM = 0.6

# THE CORE-KEEP GEOMETRY (§10-AT front 1 corrected): a 1.0mm wall inset from the catalog
# rim, floored at 1.2mm so a narrow cap's core never collapses to nothing.
_CORE_INSET_MM = 1.0
_CORE_FLOOR_MM = 1.2

# Dense enough that a CAD cap's own tessellation (~0.2-0.5mm) is not the limiting
# factor in the 0.6mm band test — the cap is small (a few hundred mm² at most), so this
# is generous rather than merely adequate.
_TEMPLATE_SAMPLE_POINTS = 20_000


def _axis_and_origin(pose: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The site's pose axis (local +z carried into the jaw frame) and its origin —
    the same convention every pipeline cylinder test uses (``deliverables.py``'s
    ``remove_cap_region``/``_csg_carve``: ``pose[:3, 3]``, ``pose[:3, :3] @ +z``)."""
    pose = np.asarray(pose, dtype=float)
    origin = pose[:3, 3]
    axis = pose[:3, :3] @ np.array([0.0, 0.0, 1.0])
    norm = float(np.linalg.norm(axis))
    if norm > 0:
        axis = axis / norm
    return origin, axis


def _radial_distances(points: np.ndarray, origin: np.ndarray,
                      axis: np.ndarray) -> np.ndarray:
    """Perpendicular distance of each point to the axis LINE through ``origin`` —
    axial extent is unbounded on purpose (see module docstring, rule 1 and 3)."""
    rel = points - origin
    axial = rel @ axis
    radial_vec = rel - np.outer(axial, axis)
    return np.linalg.norm(radial_vec, axis=1)


def _keep_faces_by_vertex_mask(mesh: trimesh.Trimesh,
                               vertex_keep: np.ndarray) -> Optional[trimesh.Trimesh]:
    """The whole-triangle rule: a face survives when ANY of its three vertices is
    marked keep. Vertex coordinates never move — ``update_faces`` culls faces,
    ``remove_unreferenced_vertices`` drops the now-orphaned rows, and nothing else
    touches the array. Returns ``None`` when nothing survives."""
    if len(mesh.faces) == 0:
        return None
    face_keep = vertex_keep[mesh.faces].any(axis=1)
    if not face_keep.any():
        return None
    out = mesh.copy()
    out.update_faces(face_keep)
    out.remove_unreferenced_vertices()
    if len(out.faces) == 0:
        return None
    return out


def isolate_scanned_cap(scan: trimesh.Trimesh, template: trimesh.Trimesh,
                        pose: np.ndarray, rim_r: float) -> Optional[trimesh.Trimesh]:
    """Exactly what the scanner saw of the healing cap at ``pose`` — the matched rung
    of the client's own isolation ladder, run over the doctor's scan bytes.

    ``template`` is the library cap CAD in its own canonical local frame (the same
    mesh the alignment fit); ``pose`` carries it into the jaw-scan world frame, and
    ``rim_r`` is the catalog rim radius (mm) the site's imprint tuple already carries.

    Returns ``None`` when the pose is pathological enough that nothing survives the
    cylinder pre-cut, or nothing in it lies within the core or the template band — the
    caller's signal to skip emission and land an honest note instead of an empty file.
    """
    origin, axis = _axis_and_origin(pose)

    # 1. CYLINDER PRE-CUT — the catalog rim radius, whole triangles, axially
    # unbounded (see module docstring).
    scan_vertices = np.asarray(scan.vertices, dtype=float)
    pre_cut = _keep_faces_by_vertex_mask(
        scan, _radial_distances(scan_vertices, origin, axis) <= float(rim_r))
    if pre_cut is None:
        return None

    # 2. THE POSED TEMPLATE SURFACE, densely sampled (own vertices + a surface
    # sample) — the same idiom ``csg.strip_fabricated`` uses to judge a face
    # against a reference surface.
    posed_template = template.copy()
    posed_template.apply_transform(np.asarray(pose, dtype=float))
    template_vertices = np.asarray(posed_template.vertices, dtype=float)
    # SEEDED (W4, measured 2026-08-14): unseeded, this draw made the artifact
    # re-roll — ~5,300 of the pre-cut's vertices are decided by the 0.6mm band,
    # the draw's per-vertex jitter is median 0.013mm, and a handful of vertices
    # sit closer to the threshold than that, so face MEMBERSHIP flipped on 22%
    # of re-emits (50% on the worst site) and the sealed manifest moved with
    # it. The explicit seed= parameter (NOT np.random.seed — a different
    # stream) makes the whole 21-file package byte-stable across processes.
    surface_sample, _ = trimesh.sample.sample_surface(
        posed_template, _TEMPLATE_SAMPLE_POINTS, seed=0)
    tree = cKDTree(np.vstack([template_vertices, surface_sample]))

    # 3. CORE-KEEP (unconditional) OR template-band (everywhere else).
    pre_cut_vertices = np.asarray(pre_cut.vertices, dtype=float)
    core_r = max(float(rim_r) - _CORE_INSET_MM, _CORE_FLOOR_MM)
    in_core = _radial_distances(pre_cut_vertices, origin, axis) <= core_r
    distance_to_template, _ = tree.query(pre_cut_vertices)
    in_band = distance_to_template <= CAP_MATCH_BAND_MM

    return _keep_faces_by_vertex_mask(pre_cut, in_core | in_band)
