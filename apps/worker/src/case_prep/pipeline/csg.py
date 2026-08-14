"""THE CSG MACHINERY, ON ITS OWN (§10-AT front 3a/3c, split out of
``deliverables.py`` once that module passed ~900 lines carrying both the
mechanism and the product's own policy constants tangled together).

Everything here is MECHANISM ONLY: solidifying an open scan shell into a
closed lab model, lathing a cut tool from a profile, dilating a cap's own
exact solid into a punch, and stripping a boolean's fabricated closure back
off the result. None of it knows the product's own numbers — visible depth,
countersink minimums, cull margins — those stay in ``deliverables.py`` and
are passed in as plain arguments. A reader auditing "what does the product
DECIDE" versus "what does the boolean DO" now has two files instead of one
undifferentiated 900-line one.

The functions below carry their original client-history docstrings verbatim
from ``deliverables.py`` (§10-AS.11/12/14/16) — they document WHY the shape
of the geometry is what it is, and that history does not change by moving
the code.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import trimesh

from case_prep.pipeline.kernel import default_kernel


def solidify_shell(shell: trimesh.Trimesh, crowns_up: np.ndarray,
                   base_margin_mm: float = 1.5) -> trimesh.Trimesh:
    """The open scan shell as a closed lab model. The LONGEST boundary loop is
    the shell's outer edge: it gets a skirt extruded away from the crowns to a
    flat base plane ``base_margin_mm`` past the deepest point, and the base is
    fanned closed. Every other loop is a small scan hole and gets a planar
    lid. A mesh with no boundary is already a solid and passes through."""
    import collections

    V = np.asarray(shell.vertices, float)
    F = np.asarray(shell.faces)
    up = np.asarray(crowns_up, float)
    up = up / np.linalg.norm(up)
    cnt = collections.Counter(map(tuple, shell.edges_sorted))
    boundary = [e for e, n in cnt.items() if n == 1]
    if not boundary:
        out = shell.copy()
        trimesh.repair.fix_normals(out)
        return out
    adj = collections.defaultdict(list)
    for a, b in boundary:
        adj[a].append(b)
        adj[b].append(a)
    seen: set = set()
    loops = []
    for start in adj:
        if start in seen:
            continue
        loop = [start]
        seen.add(start)
        prev, cur = None, start
        while True:
            nxts = [n for n in adj[cur] if n != prev and n not in seen]
            if not nxts:
                break
            prev, cur = cur, nxts[0]
            seen.add(cur)
            loop.append(cur)
        if len(loop) >= 3:
            loops.append(loop)
    if not loops:
        raise ValueError("boundary edges form no loop")
    loops.sort(key=len, reverse=True)
    base_h = float((V @ up).min()) - float(base_margin_mm)
    new_verts = [V]
    new_faces = [F]
    nv = len(V)
    outer = loops[0]
    ring = V[outer]
    proj = ring - np.outer((ring @ up) - base_h, up)
    base_idx = np.arange(nv, nv + len(outer))
    new_verts.append(proj)
    nv += len(outer)
    m = len(outer)
    skirt = []
    for i in range(m):
        j = (i + 1) % m
        skirt.append([outer[i], outer[j], base_idx[j]])
        skirt.append([outer[i], base_idx[j], base_idx[i]])
    new_faces.append(np.asarray(skirt, int))
    centre = proj.mean(axis=0)
    new_verts.append(centre[None, :])
    ci = nv
    nv += 1
    new_faces.append(np.asarray(
        [[ci, base_idx[(i + 1) % m], base_idx[i]] for i in range(m)], int))
    for loop in loops[1:]:
        lid_centre = V[loop].mean(axis=0)
        new_verts.append(lid_centre[None, :])
        li = nv
        nv += 1
        new_faces.append(np.asarray(
            [[li, loop[i], loop[(i + 1) % len(loop)]]
             for i in range(len(loop))], int))
    solid = trimesh.Trimesh(np.vstack(new_verts), np.vstack(new_faces),
                            process=False)
    trimesh.repair.fix_normals(solid)
    return solid


# one emit solidifies the same scan for the dish, the platform and the closed
# model — cache it for the life of the mesh object (key carries a content
# checksum so a recycled id can never serve another mesh's solid)
_SOLID_CACHE: dict = {}


def solidified_shell_cached(arch: trimesh.Trimesh) -> trimesh.Trimesh:
    from case_prep.adapters.cap_detection import crown_up_axis

    v = np.asarray(arch.vertices, float)
    key = (id(arch), len(v), float(v[:: max(1, len(v) // 97)].sum()))
    hit = _SOLID_CACHE.get(key)
    if hit is not None:
        return hit
    up = crown_up_axis(v, np.asarray(arch.face_normals, float))
    solid = solidify_shell(arch, up)
    if not solid.is_watertight:
        raise ValueError("the solidified shell is not watertight")
    _SOLID_CACHE.clear()
    _SOLID_CACHE[key] = solid
    return solid


def punch_solid(zs_p: np.ndarray, prof_p: np.ndarray, floor_a: float,
                pose: np.ndarray) -> trimesh.Trimesh:
    """The CUT TOOL (§10-AS.12): the envelope profile lathed from ``floor_a``
    up, with a flat bottom disc AT the floor — so a boolean difference leaves
    a smooth wall and a machined flat floor — and the top row extended 2mm
    past the profile's end (the scanned cap's apex can stand a deviation
    proud of the template's own top; without the extension a sliver of dome
    survived the cut as a floating crown)."""
    zs = np.asarray(zs_p, float)
    prof = np.asarray(prof_p, float)
    keep = zs > floor_a
    r_floor = float(np.interp(floor_a, zs, prof))
    z_rows = np.concatenate([[floor_a], zs[keep],
                             [float(zs[keep][-1]) + 2.0] if keep.any()
                             else [floor_a + 2.0]])
    r_rows = np.concatenate([[r_floor], prof[keep],
                             [float(prof[keep][-1])] if keep.any()
                             else [r_floor]])
    seg = 64
    ang = np.linspace(0.0, 2.0 * np.pi, seg, endpoint=False)
    ca, sa = np.cos(ang), np.sin(ang)
    rings = np.concatenate([
        np.column_stack([rr * ca, rr * sa, np.full(seg, zz)])
        for rr, zz in zip(r_rows, z_rows)])
    verts = np.vstack([rings, [[0.0, 0.0, z_rows[0]]],
                       [[0.0, 0.0, z_rows[-1]]]])
    faces = []
    bins = len(z_rows)
    for i in range(bins - 1):
        a0, b0 = i * seg, (i + 1) * seg
        for j in range(seg):
            k = (j + 1) % seg
            faces.append([a0 + j, a0 + k, b0 + k])
            faces.append([a0 + j, b0 + k, b0 + j])
    bot, top = len(verts) - 2, len(verts) - 1
    last = (bins - 1) * seg
    for j in range(seg):
        k = (j + 1) % seg
        faces.append([bot, k, j])
        faces.append([top, last + j, last + k])
    punch = trimesh.Trimesh(verts, np.asarray(faces, int), process=False)
    punch.apply_transform(np.asarray(pose, float))
    return punch


def _lid_boundary_loops(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Fan-close every boundary loop of ``mesh`` with a flat centroid lid —
    the same idiom ``solidify_shell`` uses for a scan's small holes, applied
    here to a vendor CAD cap. Most healing-cap STLs export the
    implant-interface bore OPEN (the physical part is genuinely hollow
    there) — an honest closure of a KNOWN loop, not an inferred shape, so
    it does not violate §10-AS.14's "we should not be inferring anything
    here": without it the exact-cut route would never run on real vendor
    files at all. A mesh with no boundary passes through unchanged."""
    import collections

    V = np.asarray(mesh.vertices, float)
    F = np.asarray(mesh.faces)
    cnt = collections.Counter(map(tuple, mesh.edges_sorted))
    boundary = [e for e, n in cnt.items() if n == 1]
    if not boundary:
        return mesh.copy()
    adj = collections.defaultdict(list)
    for a, b in boundary:
        adj[a].append(b)
        adj[b].append(a)
    seen: set = set()
    loops = []
    for start in adj:
        if start in seen:
            continue
        loop = [start]
        seen.add(start)
        prev, cur = None, start
        while True:
            nxts = [n for n in adj[cur] if n != prev and n not in seen]
            if not nxts:
                break
            prev, cur = cur, nxts[0]
            seen.add(cur)
            loop.append(cur)
        if len(loop) >= 3:
            loops.append(loop)
    new_verts = [V]
    new_faces = [F]
    nv = len(V)
    for loop in loops:
        centre = V[loop].mean(axis=0)
        new_verts.append(centre[None, :])
        ci = nv
        nv += 1
        new_faces.append(np.asarray(
            [[ci, loop[i], loop[(i + 1) % len(loop)]] for i in range(len(loop))],
            int))
    out = trimesh.Trimesh(np.vstack(new_verts), np.vstack(new_faces), process=False)
    trimesh.repair.fix_normals(out)
    return out


def exact_cap_punch(template: trimesh.Trimesh, offset_mm: float,
                    pose: np.ndarray,
                    floor_a: Optional[float] = None) -> trimesh.Trimesh:
    """THE EXACT CUT TOOL (§10-AS.14, client 2026-08-10: "this needs to be
    exact of the healing cap... the gum is gonna heal around the healing cap
    ... subtraction is the exact, we should not be inferring anything here").
    The cap's OWN CAD solid at its aligned pose, grown only by the site's
    gingival offset along its vertex normals — the offset is the operator's
    chosen parameter, the one dilation that is not inference. The revolute
    envelope and the deviation clearance are gone from the cut; the envelope
    survives only as this tool's per-site fallback. When a visible depth
    applies, the tool is clipped below ``floor_a`` by a box intersection so
    the dish/platform artifacts keep their shallow reads.

    Most vendor healing-cap STLs are not watertight as exported — the
    implant-interface bore is open, since the physical part is hollow
    there — so a not-yet-closed template gets ONE honest closure attempt
    (``_lid_boundary_loops``) before this tool gives up on it."""
    if len(template.faces) == 0:
        raise ValueError("the cap template is not a watertight solid")
    src = template if template.is_watertight else _lid_boundary_loops(template)
    if not src.is_watertight:
        raise ValueError("the cap template is not a watertight solid")
    punch = src.copy()
    if float(offset_mm) > 0:
        n = np.asarray(punch.vertex_normals, float)
        punch.vertices = (np.asarray(punch.vertices, float)
                          + n * float(offset_mm))
        # SELF-HEALING PUNCH (§10-AT front 3a): vertex-normal dilation moves
        # every vertex out along its OWN normal independently, and at a
        # concave crease — the screw slot, a coded cutout — the two walls
        # meeting there converge rather than opening a smooth notch, so the
        # dilated shell can self-intersect exactly at the features that make
        # a real vendor cap a real vendor cap. A manifold union of the punch
        # WITH ITSELF resolves that: it is the same boolean machinery the
        # later cut already trusts, run once more against itself, and it
        # costs nothing when the shape was already clean. Without this a
        # creased cap's punch carries the self-intersection into the site's
        # own cut, that cut fails, and the site falls back to the envelope
        # tool (``punch_solid``) — losing the exact cut this function exists
        # to do. On failure here the UN-HEALED punch is kept — the site's
        # own failure handling downstream still stands as the containment.
        #
        # (manifold3d 3.5.2, as installed: ``dir(manifold3d.Manifold)`` has
        # no ``offset`` method. It does have ``minkowski_sum``, which is a
        # true morphological offset if summed with a small sphere — a
        # cleaner dilation than walking vertices along their own normals,
        # since a Minkowski sum cannot self-intersect by construction. That
        # is the candidate for a future slice; this one keeps the existing
        # vertex-normal dilation and only adds the self-heal after it.)
        try:
            punch = default_kernel().union([punch])
        except Exception:  # noqa: BLE001 — keep the un-healed punch; the
            # cut's own per-site failure handling is the containment here,
            # not this function refusing to return a shape at all
            pass
    punch.apply_transform(np.asarray(pose, float))
    if floor_a is not None:
        box = trimesh.creation.box(extents=[60.0, 60.0, 60.0])
        box.apply_translation([0.0, 0.0, 30.0 + float(floor_a)])
        box.apply_transform(np.asarray(pose, float))
        clipped = default_kernel().intersection(punch, box)
        if len(clipped.faces) > 0:
            punch = clipped
        # "the clip only limits depth, never extends it": a submerged cap
        # whose own dilated top sits BELOW the visible-floor target (the
        # countersink wants to open at the gum, but the cap's own material
        # never reaches that high) has nothing for the clip to keep — the
        # clip is then a no-op, and the WHOLE cap is the cut, exactly as
        # ``depth=None`` would give it. Never an empty tool, never a
        # manufactured extension past the cap's own true shape.
    return punch


def strip_fabricated(cut: trimesh.Trimesh, original_arch: trimesh.Trimesh,
                     punch_regions_test: np.ndarray) -> np.ndarray:
    """THE OPEN ARCH COMES BACK (§10-AS.16, client 2026-08-10: "why did we
    build a dental model — we need to work with the open arch"): the
    solidify base and skirt exist ONLY so the boolean has a solid to cut.
    The artifact is the SCAN. A face survives if it lies on a cut surface
    (the recess) or on the original shell itself; the fabricated closure —
    base plate, skirt, anything the scan never contained — is stripped.
    Tab 6's closed model keeps its base; that is its whole point.

    Returns the per-face KEEP mask over ``cut`` (parallel to
    ``cut.faces``): true where ``punch_regions_test`` already marks the
    face as a punch/recess surface, OR the face sits within 0.35mm of
    ``original_arch``'s own surface; false for anything the scan never
    contained."""
    from scipy.spatial import cKDTree

    inside = np.asarray(punch_regions_test, bool)
    V = np.asarray(original_arch.vertices, float)
    C = np.asarray(cut.triangles_center, float)
    # judged against a dense SURFACE sample, not the vertices alone: a scan's
    # 0.3mm vertex spacing hides the difference, but a coarse mesh's mid-face
    # centroids sit a full edge from any vertex and were stripped as if
    # fabricated (measured on the 2.5mm-spaced fixtures)
    surf_pts, _ = trimesh.sample.sample_surface(original_arch, 150_000)
    d_scan, _ = cKDTree(np.vstack([V, surf_pts])).query(C)
    return inside | (d_scan < 0.35)
