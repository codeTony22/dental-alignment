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

from typing import Optional, Sequence, Tuple

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


def scanned_cap_face_mask(mesh: trimesh.Trimesh, template: trimesh.Trimesh,
                         pose: np.ndarray, rim_r: float) -> np.ndarray:
    """THE SHARED CLASSIFIER (client-ruled defect 1, 2026-08-15 live verification):
    ``isolate_scanned_cap``'s own three-rung test, factored out as a per-face
    boolean array parallel to ``mesh.faces`` — cylinder pre-cut (whole triangles,
    axially unbounded), core-keep (unconditional inside ``max(rim_r-1.0, 1.2)``mm),
    template band (``CAP_MATCH_BAND_MM`` of the posed template's own surface). This
    IS ``isolate_scanned_cap``'s mechanism, not a second copy of it — that function
    is now a thin wrapper that keeps the faces this one marks True. Returns an
    all-False array (never raises) when ``mesh`` carries no faces at all.

    ``mesh`` NEED NOT BE THE RAW SCAN. The excision doctrine (DEFECT 1: "the real
    cap physically leaves the mouth; removing its MEASURED surface is measurement")
    applies this exact geometric test to a BOOLEAN RESULT's own scan-provenance
    faces too — their vertex coordinates are inherited, unmoved, from the scan the
    boolean cut (``solidify_shell``'s append-only ordering, and a boolean split
    only subdivides a face along an intersection curve, it never relocates the
    material outside that curve), so the same axis-radial / template-distance test
    reads a cut result's leftover crust exactly as it reads the raw scan. One
    geometric rule, shared by every consumer that needs to answer "is this triangle
    the physical healing cap the scanner saw" — the per-site isolation artifact,
    the fused composite's excision, the carved recess's excision, and the
    through-hole artifact's excision all read it, and can never drift apart."""
    origin, axis = _axis_and_origin(pose)
    V = np.asarray(mesh.vertices, dtype=float)
    F = np.asarray(mesh.faces)
    if len(F) == 0:
        return np.zeros(0, dtype=bool)

    # 1. CYLINDER PRE-CUT — the catalog rim radius, whole triangles, axially
    # unbounded (see module docstring).
    radial = _radial_distances(V, origin, axis)
    step1 = (radial <= float(rim_r))[F].any(axis=1)
    if not step1.any():
        return np.zeros(len(F), dtype=bool)

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

    # 3. CORE-KEEP (unconditional) OR template-band (everywhere else) — the
    # distance query is restricted to vertices step 1 actually touched (the
    # same cost profile the two-stage implementation this replaces had: a
    # KD-tree query over the pre-cut's own vertices, not the whole mesh).
    core_r = max(float(rim_r) - _CORE_INSET_MM, _CORE_FLOOR_MM)
    in_core = radial <= core_r
    used = np.zeros(len(V), dtype=bool)
    used[F[step1].ravel()] = True
    distance_to_template = np.full(len(V), np.inf)
    distance_to_template[used] = tree.query(V[used])[0]
    in_band = distance_to_template <= CAP_MATCH_BAND_MM
    step2 = (in_core | in_band)[F].any(axis=1)

    return step1 & step2


def isolate_scanned_cap(scan: trimesh.Trimesh, template: trimesh.Trimesh,
                        pose: np.ndarray, rim_r: float) -> Optional[trimesh.Trimesh]:
    """Exactly what the scanner saw of the healing cap at ``pose`` — the matched rung
    of the client's own isolation ladder, run over the doctor's scan bytes.

    ``template`` is the library cap CAD in its own canonical local frame (the same
    mesh the alignment fit); ``pose`` carries it into the jaw-scan world frame, and
    ``rim_r`` is the catalog rim radius (mm) the site's imprint tuple already carries.

    A thin wrapper over ``scanned_cap_face_mask`` (the shared classifier, boolean-
    engine defect-1 slice, 2026-08-15): keeps the faces the mask marks True, moving
    nothing (``update_faces`` + ``remove_unreferenced_vertices``, exactly as before).
    Returns ``None`` when the pose is pathological enough that nothing survives the
    cylinder pre-cut, or nothing in it lies within the core or the template band — the
    caller's signal to skip emission and land an honest note instead of an empty file.
    """
    mask = scanned_cap_face_mask(scan, template, pose, rim_r)
    if not mask.any():
        return None
    out = scan.copy()
    out.update_faces(mask)
    out.remove_unreferenced_vertices()
    if len(out.faces) == 0:
        return None
    return out


def orphan_flap_mask(mesh: trimesh.Trimesh,
                     site_poses: Sequence[Tuple[np.ndarray, float]],
                     candidate: Optional[np.ndarray] = None) -> np.ndarray:
    """DEFECT A — THE ORPHAN FLAPS (client-ruled, live verification
    2026-08-15): CONNECTIVITY, not a wider threshold. ``scanned_cap_face_
    mask``'s 0.6mm template-match band (``CAP_MATCH_BAND_MM``) misses
    cap-margin surface that deviates MORE than the band in the annulus
    between the core-keep radius and the catalog rim — those triangles
    dodge the excision and survive as loose slivers at the bore edge.
    Widening the band would eat real gum (the same classifier serves pane
    2's own crop, and every other DEFECT-1 excision consumer); the fix is
    topological instead, run AFTER that excision has already dropped what
    it could catch:

    A face is ORPHAN when BOTH hold —

    1. it lies ENTIRELY inside SOME site's cylinder — every one of its
       three vertices within that site's own catalog rim radius of the
       site's pose axis, radially (the same axis/radius convention every
       cylinder test in this module and ``deliverables.py`` shares; "any
       vertex" is the SURVIVAL rule the classifier's own pre-cut uses,
       but "entirely" is the right-sized test for CANDIDACY here — a face
       straddling the rim is still attached to whatever lies outside it,
       so it is connected tissue by definition, never an orphan);
    2. it belongs to a connected component (mesh face adjacency, shared
       edges only) that is DISCONNECTED from the mesh's own largest
       candidate component — real gum always runs into the surrounding
       arch, so a scrap of surface an implant-neighbourhood excision left
       behind, with no path back to the main body, is physically nothing
       but cap remnant.

    ``candidate`` restricts which of ``mesh``'s faces may even be
    considered eligible — every consumer already knows which of its own
    faces are scan-provenance (a fused composite also carries each
    construction part's own surface, which this test must never reach for;
    a pressed carve's own already-moved recess faces are equally out of
    scope). ``None`` means every face of ``mesh`` is eligible. THE GUARD:
    the single LARGEST candidate connected component, by face count, is
    the main scan body and can never itself be an orphan, however its own
    faces happen to read against the cylinder test — named explicitly
    because the doctrine depends on it, not left to fall out of the
    component-size arithmetic by accident. A component with any face
    OUTSIDE every site's cylinder is connected tissue reaching in from the
    arch — kept, unconditionally (the guard's other half: a gum tongue
    that dips into the annulus and back out is real anatomy, not a flap).

    Returns an all-False mask (never raises) when ``mesh`` carries no
    faces, ``site_poses`` is empty, ``candidate`` excludes everything, or
    nothing candidate falls inside any site's cylinder at all — dropping
    measured cap remnant is the excision's own contract (no note is ever
    warranted for it), but this function makes no claim it cannot back
    with a component that actually qualifies."""
    F = np.asarray(mesh.faces)
    n = len(F)
    if n == 0 or not site_poses:
        return np.zeros(n, dtype=bool)
    candidate_mask = (np.ones(n, dtype=bool) if candidate is None
                      else np.asarray(candidate, dtype=bool))
    if not candidate_mask.any():
        return np.zeros(n, dtype=bool)

    V = np.asarray(mesh.vertices, dtype=float)
    inside_any = np.zeros(n, dtype=bool)
    for pose, rim_r in site_poses:
        origin, axis = _axis_and_origin(pose)
        radial = _radial_distances(V, origin, axis)
        inside_any |= (radial[F] <= float(rim_r)).all(axis=1)
    if not inside_any.any():
        return np.zeros(n, dtype=bool)

    nodes = np.flatnonzero(candidate_mask)
    components = trimesh.graph.connected_components(
        mesh.face_adjacency, nodes=nodes, min_len=1)
    if not components:
        return np.zeros(n, dtype=bool)
    sizes = [len(comp) for comp in components]
    main_idx = int(np.argmax(sizes))

    orphan = np.zeros(n, dtype=bool)
    for i, comp in enumerate(components):
        if i == main_idx:
            continue
        comp_idx = np.asarray(comp, dtype=int)
        if inside_any[comp_idx].all():
            orphan[comp_idx] = True
    return orphan
