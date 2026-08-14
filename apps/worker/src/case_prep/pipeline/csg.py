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

from case_prep.pipeline.kernel import TrackedResult, default_kernel


def _simple_boundary_loops(adj: dict) -> list:
    """The ORIGINAL walker (§10-AT front 3a/3c), unchanged: a plain vertex-DFS
    that is correct exactly when every boundary vertex has degree <= 2 — a
    disjoint union of simple cycles, which is what a healthy scan shell's
    boundary always is. Kept byte-for-byte so every healthy input (raw scans,
    carved arches, closed inputs) takes this SAME route and produces the SAME
    solid it always has — the junction-safe walker below is a new branch, not
    a replacement of this one."""
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
    return loops


def _junction_safe_boundary_loops(V: np.ndarray, F: np.ndarray, boundary: list
                                  ) -> list:
    """The boundary decomposition for a shell with at least one JUNCTION — a
    boundary vertex where more than one patch of the shell meets at a single
    point (the seam ``cap_imprint_parts``'s per-face mask leaves at zero
    gingival relief, §10-AT front 5/W5: 58 of them on the real failure case).
    The plain vertex-DFS above assumes a disjoint union of simple cycles and
    silently mangles a junction instead: fragments shorter than 3 vertices
    get dropped, and a still-open chain gets fanned shut as if it had
    closed — fabricating an edge that either stays open (not watertight) or
    collides with an interior one (multiplicity 3).

    Here the walk is EDGE-wise — a ``used`` set of edge INDICES, never a
    global vertex ``seen`` set, so two patches meeting at one point are never
    folded into one messier walk. At a junction, the incident triangles split
    into WEDGES — connected components of "shares a non-boundary edge through
    this vertex" — and each wedge's own two boundary edges continue each
    other: the FACE FAN decides the pairing, not iteration order (measured to
    mis-pair a wedge and move the resulting volume by over a cubic
    millimetre). A path-stack + position map decomposes the walk into simple
    cycles: a walk that revisits a vertex still on its own path closes the
    sub-cycle there rather than growing a self-crossing loop (the thing that
    would otherwise double a lid spoke to multiplicity 4). A chain that runs
    out of pairing before it closes is NEVER fanned shut — it is left for the
    caller to refuse on, loudly, rather than leaking an unclosed "solid"."""
    import collections

    edge_faces: dict = collections.defaultdict(list)
    for fi, f in enumerate(F):
        for k in range(3):
            e = tuple(sorted((int(f[k]), int(f[(k + 1) % 3]))))
            edge_faces[e].append(fi)
    vertex_faces: dict = collections.defaultdict(list)
    for fi, f in enumerate(F):
        for v in f:
            vertex_faces[int(v)].append(fi)
    vertex_edges: dict = collections.defaultdict(list)
    for idx, (a, b) in enumerate(boundary):
        vertex_edges[a].append(idx)
        vertex_edges[b].append(idx)

    # pair[(edge_idx, vertex)] -> the boundary edge that CONTINUES edge_idx
    # when the walk arrives at ``vertex`` along it
    pair: dict = {}
    for v, eidxs in vertex_edges.items():
        if len(eidxs) == 2:
            i0, i1 = eidxs
            pair[(i0, v)] = i1
            pair[(i1, v)] = i0
            continue
        # a junction: split the faces incident to v into wedges by face
        # adjacency THROUGH v. A well-formed mesh edge is shared by at most
        # two faces, so each face has at most two neighbours here — a wedge
        # is always an open FAN (a path, never a branching tree) with
        # exactly two free (boundary) ends, which is why this pairs cleanly
        # two-and-two; a non-manifold EDGE (multiplicity >= 3) can leave a
        # wedge with an ODD boundary-edge count, and the leftover edge is
        # deliberately left unpaired below — it becomes the dead end a
        # non-closing chain is refused on.
        fan_adj: dict = collections.defaultdict(list)
        for fi in vertex_faces[v]:
            f = F[fi]
            for k in range(3):
                a, b = int(f[k]), int(f[(k + 1) % 3])
                if v not in (a, b):
                    continue
                for fj in edge_faces[tuple(sorted((a, b)))]:
                    if fj != fi:
                        fan_adj[fi].append(fj)
        wedge_of: dict = {}
        seen_f: set = set()
        n_wedges = 0
        for fi in vertex_faces[v]:
            if fi in seen_f:
                continue
            stack = [fi]
            seen_f.add(fi)
            while stack:
                c = stack.pop()
                wedge_of[c] = n_wedges
                for d in fan_adj[c]:
                    if d not in seen_f:
                        seen_f.add(d)
                        stack.append(d)
            n_wedges += 1
        by_wedge: dict = collections.defaultdict(list)
        for eidx in eidxs:
            face = edge_faces[boundary[eidx]][0]
            by_wedge[wedge_of[face]].append(eidx)
        for wedge_eidxs in by_wedge.values():
            for k in range(0, len(wedge_eidxs) - 1, 2):
                i0, i1 = wedge_eidxs[k], wedge_eidxs[k + 1]
                pair[(i0, v)] = i1
                pair[(i1, v)] = i0

    used: set = set()
    loops: list = []
    open_chains: list = []
    for start in range(len(boundary)):
        if start in used:
            continue
        a0, b0 = boundary[start]
        used.add(start)
        path = [a0, b0]
        pos = {a0: 0, b0: 1}
        cur_edge, cur_v = start, b0
        while True:
            nxt = pair.get((cur_edge, cur_v))
            if nxt is None or nxt in used:
                break
            used.add(nxt)
            ea, eb = boundary[nxt]
            nxt_v = eb if ea == cur_v else ea
            if nxt_v in pos:
                start_i = pos[nxt_v]
                cycle = path[start_i:]
                if len(cycle) >= 3:
                    loops.append(cycle)
                del path[start_i + 1:]
                for stale in [x for x, p in pos.items() if p > start_i]:
                    del pos[stale]
                cur_edge, cur_v = nxt, nxt_v
                continue
            pos[nxt_v] = len(path)
            path.append(nxt_v)
            cur_edge, cur_v = nxt, nxt_v
        if len(path) > 1:
            open_chains.append(path)

    if open_chains:
        rep = open_chains[0]
        coord = V[rep[len(rep) // 2]]
        n_open_edges = sum(len(c) - 1 for c in open_chains)
        raise ValueError(
            f"the shell's boundary has {len(open_chains)} chain(s) that do "
            f"not close ({n_open_edges} open edge(s) total; one runs "
            f"through {tuple(round(float(x), 3) for x in coord)}) — it "
            f"cannot be lidded without fabricating a closing edge")
    return loops


def solidify_shell(shell: trimesh.Trimesh, crowns_up: np.ndarray,
                   base_margin_mm: float = 1.5) -> trimesh.Trimesh:
    """The open scan shell as a closed lab model. The LONGEST boundary loop is
    the shell's outer edge: it gets a skirt extruded away from the crowns to a
    flat base plane ``base_margin_mm`` past the deepest point, and the base is
    fanned closed. Every other loop is a small scan hole and gets a planar
    lid. A mesh with no boundary is already a solid and passes through.

    The boundary walk itself has two routes (§10-AT front 5/W5): a shell
    whose boundary vertices are all degree <= 2 — every healthy input this
    has ever seen — takes ``_simple_boundary_loops``, unchanged, byte for
    byte. A shell with at least one JUNCTION vertex (boundary degree > 2 —
    the seam ``cap_imprint_parts``'s per-face mask leaves at zero gingival
    relief) takes ``_junction_safe_boundary_loops`` instead, which pairs a
    junction's incident boundary edges by the face fan rather than assuming
    a simple cycle, and refuses outright rather than fanning a chain shut
    that never actually closed."""
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
    if all(len(ns) <= 2 for ns in adj.values()):
        loops = _simple_boundary_loops(adj)
    else:
        loops = _junction_safe_boundary_loops(V, F, boundary)
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


def fabricated_face_mask(original_shell: trimesh.Trimesh,
                         solid: trimesh.Trimesh) -> np.ndarray:
    """THE CLOSURE, NAMED AT THE SOURCE (boolean-engine plan W1, 2026-08-13):
    true for every face of ``solid`` that ``solidify_shell`` fabricated — the
    skirt, the base fan, any hole lid — false for the shell's own scan
    faces. Exact, by construction, never by distance: ``solidify_shell``
    always builds its output as ``[the input's own F, skirt, base fan, lid
    fans...]`` (its own ``new_faces`` list, in that order), so every
    fabricated face comes AFTER every scan face and the boundary is one
    integer — ``len(original_shell.faces)``.

    Trusted, not merely assumed: the leading block of ``solid.faces`` must
    reference the SAME vertex triples as ``original_shell.faces`` (compared
    as unordered sets per face — ``trimesh.repair.fix_normals`` may flip a
    triangle's own winding without moving it, and the "already closed"
    branch of ``solidify_shell`` runs exactly that repair). A solid whose
    leading block has drifted from this invariant raises here rather than
    silently mislabelling every downstream provenance tag."""
    n_scan = len(original_shell.faces)
    if len(solid.faces) < n_scan:
        raise ValueError(
            "the solidified shell has fewer faces than its own input "
            f"({len(solid.faces)} < {n_scan}) — solidify_shell's "
            "append-only ordering invariant is broken")
    head = np.sort(np.asarray(solid.faces[:n_scan]), axis=1)
    orig = np.sort(np.asarray(original_shell.faces), axis=1)
    if not np.array_equal(head, orig):
        raise ValueError(
            "the solidified shell's leading faces no longer match its own "
            "input's faces — solidify_shell's append-only ordering "
            "invariant is broken, and the fabricated-face mask cannot be "
            "trusted without it")
    mask = np.zeros(len(solid.faces), bool)
    mask[n_scan:] = True
    return mask


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
        # §10-AT front 5/W5: name what and where, not just that — "not
        # watertight" alone sent a debugging session hunting for the wrong
        # thing (measured non-actionable). Multiplicity != 2 catches both a
        # boundary edge left open (1) and one fabricated onto an interior
        # edge by mistake (3+); a representative vertex locates it.
        import collections

        vcnt = collections.Counter(map(tuple, solid.edges_sorted))
        bad_edges = [e for e, n in vcnt.items() if n != 2]
        sv = np.asarray(solid.vertices, float)
        near = tuple(round(float(x), 3) for x in sv[bad_edges[0][0]]) \
            if bad_edges else None
        raise ValueError(
            f"the solidified shell is not watertight ({len(bad_edges)} "
            f"open/non-manifold edge(s), one near {near})")
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
                    floor_a: Optional[float] = None,
                    offset_engine: str = "vertex-normal",
                    diagnostics: Optional[dict] = None) -> trimesh.Trimesh:
    """THE EXACT CUT TOOL (§10-AS.14, client 2026-08-10: "this needs to be
    exact of the healing cap... the gum is gonna heal around the healing cap
    ... subtraction is the exact, we should not be inferring anything here").
    The cap's OWN CAD solid at its aligned pose, grown only by the site's
    gingival offset — the offset is the operator's chosen parameter, the
    one dilation that is not inference. The revolute envelope and the
    deviation clearance are gone from the cut; the envelope survives only
    as this tool's per-site fallback. When a visible depth applies, the
    tool is clipped below ``floor_a`` by a box intersection so the
    dish/platform artifacts keep their shallow reads.

    Most vendor healing-cap STLs are not watertight as exported — the
    implant-interface bore is open, since the physical part is hollow
    there — so a not-yet-closed template gets ONE honest closure attempt
    (``_lid_boundary_loops``) before this tool gives up on it. THIS LIDDING
    ALWAYS RUNS FIRST, before either offset path below, and never after:
    manifold3d's ``minkowski_sum`` needs a SOLID operand (verified —
    ``kernel.minkowski_sphere``'s own docstring — an open shell reads back
    ``Error.NotManifold`` and the sum on it silently returns an EMPTY mesh,
    not an exception), so an unlidded bore handed to the minkowski path
    would vanish rather than raise. Lidding before dilating, always, is
    what keeps that failure mode unreachable from here.

    THE OFFSET PATH (``offset_engine``, boolean-engine plan W2, 2026-08-14):
    two ways to grow the lidded solid by ``offset_mm``, chosen by the
    caller, same everything else after —

    * ``"vertex-normal"`` (THE DEFAULT — unchanged by this slice; the fleet
      measurement at integration decides whether that changes, per the
      plan's own W2 acceptance criterion, not a guess made here): every
      vertex walks along its OWN normal, independently. At a concave crease
      — a screw slot, a coded cutout — the two walls meeting there converge
      toward each other rather than opening a smooth notch, so the dilated
      shell can self-intersect exactly at the features that make a real
      vendor cap a real vendor cap.
    * ``"minkowski"``: the lidded solid Minkowski-summed with a sphere of
      radius ``offset_mm`` (``default_kernel().minkowski_sphere`` — see its
      own docstring for the sphere's subdivision and the chord-error
      arithmetic behind it). A true morphological dilation cannot
      self-intersect by construction — nothing in the sweep ever asks two
      points of the input to separate — so this path does not need the
      heal below to produce a valid solid, though the heal still runs over
      it (belt-and-braces, not a load-bearing step on this path). MEASURED
      (2026-08-14, this slice's own timing run) far too slow for the W6
      ~5s emit budget on a catalog-sized (~30k-face) cap — 56-68s at the
      chosen subdivision, 9.8s even at the coarsest possible sphere,
      because the cost floor is set by the CAP's own face count, not the
      sphere's. This is why the default has not moved.

    THE HEAL RUNS UNCONDITIONALLY (§ boolean-engine plan W5 rider (a),
    2026-08-14 — previously gated on ``offset_mm > 0``, so a raw, zero-
    offset CAD punch was never healed at all; the real case 276794487's
    carve mask showed bowtie junctions from exactly an un-healed punch,
    offset 0.0). A manifold union of the punch WITH ITSELF resolves any
    self-intersection the shape carries — whether from the vertex-normal
    dilation above, or baked into the vendor CAD/lidding itself — and it
    changes nothing on a shape that was already clean (measured: a clean
    solid's own self-union differs from the input by ~1e-6mm^3, float32
    round-trip noise, not a real change).

    A SUBTLE BUG THIS SLICE ALSO FIXES: the OLD self-heal call was
    ``default_kernel().union([punch])`` — a ONE-ELEMENT list. Trimesh's own
    ``reduce_cascade`` (the fan-in ``boolean_manifold`` uses for a union of
    N meshes) returns ``items[0]`` UNCHANGED for a single-item input,
    skipping the boolean call entirely — measured directly at this slice's
    own pin time: unioning a genuinely self-intersecting fixture with
    ``[punch]`` left it byte-for-byte the same self-intersecting shape,
    while ``[punch, punch]`` (two independent conversions of the SAME
    mesh, forcing the real pairwise manifold boolean) actually resolved
    it. The self-heal has therefore never healed anything since it
    shipped; this is the fix, not a refactor of working code.

    DIAGNOSTICS (optional ``dict`` out-param, boolean-engine plan W2): when
    given, filled with ``{"heal_fired": bool, "heal_changed_faces": bool,
    "offset_engine": str}``. ``heal_changed_faces`` is the raw fact — did
    the heal's own output carry a different face count — which fires even
    on a CLEAN minkowski punch (the sum's own retriangulation merges
    coincident/coplanar geometry the self-union then simplifies further,
    measured moving face count by tens of percent with the volume steady
    to ~1e-7mm^3): a fact, not a verdict. ``heal_fired`` is the verdict a
    corpus can assert "no heal fired" against — true only when the punch's
    own VOLUME measurably changed (a self-intersecting shape shrinks when
    the overlap collapses to material counted once, not twice — measured
    2.47mm^3 on this slice's own concave fixture, orders of magnitude
    above the ~1e-6mm^3 noise floor), or when watertightness itself
    flipped. A face-count-only change is retriangulation, not a defect
    fix, and does not set ``heal_fired``."""
    if len(template.faces) == 0:
        raise ValueError("the cap template is not a watertight solid")
    src = template if template.is_watertight else _lid_boundary_loops(template)
    if not src.is_watertight:
        raise ValueError("the cap template is not a watertight solid")
    punch = src.copy()
    if float(offset_mm) > 0:
        if offset_engine == "vertex-normal":
            n = np.asarray(punch.vertex_normals, float)
            punch.vertices = (np.asarray(punch.vertices, float)
                              + n * float(offset_mm))
        elif offset_engine == "minkowski":
            punch = default_kernel().minkowski_sphere(punch, float(offset_mm))
        else:
            raise ValueError(
                f"exact_cap_punch: unknown offset_engine {offset_engine!r} "
                "(expected 'vertex-normal' or 'minkowski')")
    before_watertight = bool(punch.is_watertight)
    before_faces = len(punch.faces)
    before_volume = float(punch.volume) if before_watertight else None
    heal_fired = False
    heal_changed_faces = False
    try:
        healed = default_kernel().union([punch, punch])
        heal_changed_faces = len(healed.faces) != before_faces
        after_watertight = bool(healed.is_watertight)
        if before_watertight and after_watertight:
            heal_fired = abs(float(healed.volume) - before_volume) > 1e-3
        else:
            heal_fired = after_watertight != before_watertight
        punch = healed
    except Exception:  # noqa: BLE001 — keep the un-healed punch; the
        # cut's own per-site failure handling is the containment here,
        # not this function refusing to return a shape at all
        pass
    if diagnostics is not None:
        diagnostics["heal_fired"] = heal_fired
        diagnostics["heal_changed_faces"] = heal_changed_faces
        diagnostics["offset_engine"] = offset_engine
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


def strip_tracked(result: TrackedResult) -> np.ndarray:
    """``strip_fabricated``'s claim made EXACT (boolean-engine plan W1,
    2026-08-13): given a ``TrackedResult`` whose base operand was tagged
    with ``fabricated_face_mask`` (source 0 = the shell's own scan faces,
    source 1 = the closure it fabricated — ``base_groups == 2``), the keep
    decision is pure identity — every face is either tool material or the
    shell's own scan material, and the ONLY thing ever dropped is the
    closure, by its own tag, never by how close it happens to sit to
    anything. When the base carried no split at all (``base_groups == 1`` —
    an already-closed shell that ``solidify_shell`` passed through
    unchanged, so there is no closure to drop) every face is scan-or-tool
    by definition and nothing is stripped.

    This is the function ``strip_fabricated``'s own docstring describes as
    the goal: "the fabricated closure ... is stripped" — here that sentence
    is true by construction, not by a 0.35mm sample-distance admission."""
    source = np.asarray(result.source)
    if result.base_groups >= 2:
        # source 1 is the closure ONLY when the base was actually split;
        # every source at or above 2 is a tool's own, kept unconditionally
        return source != 1
    return np.ones(len(source), bool)
