"""Arch-level deliverable composition (client spec, 2026-07-11).

The demo/deliverable trio per case:
  1. the aligned CONSTRUCTION part alone            (already emitted per site)
  2. the doctor's WHOLE arch + the aligned HEALING CAP covering the scanned gap
  3. the arch with the scanned cap region REMOVED and the CONSTRUCTION in its place

Region removal is face-culling inside the aligned cap's cylinder — a visual/deliverable
composite that keeps the doctor's scan data untouched elsewhere. (A watertight CSG variant
via the SDF engine is the follow-up if a manufacturer requires a single fused solid.)
"""
from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np
import trimesh

from case_prep.pipeline.csg import (exact_cap_punch, fabricated_face_mask,
                                    punch_solid, solidified_shell_cached,
                                    strip_fabricated, strip_tracked)
from case_prep.pipeline.isolation import orphan_flap_mask, scanned_cap_face_mask
from case_prep.pipeline.kernel import default_kernel

_REGION_MARGIN_MM = 0.6  # cull slightly beyond the cap so no scanned cap sliver survives


def remove_cap_region(arch: trimesh.Trimesh, pose_matrix: np.ndarray,
                      radius_mm: float, half_height_mm: float) -> trimesh.Trimesh:
    """The arch with everything inside the aligned cap's cylinder removed. The cylinder is
    the pose's local +z axis through its origin; faces are culled when their CENTROID falls
    inside (radius + margin, ±(half height + margin))."""
    pose = np.asarray(pose_matrix, float)
    origin, axis = pose[:3, 3], pose[:3, :3] @ np.array([0.0, 0.0, 1.0])
    centroids = np.asarray(arch.triangles_center, float) - origin
    axial = centroids @ axis
    radial = np.linalg.norm(centroids - np.outer(axial, axis), axis=1)
    keep = ~((radial < radius_mm + _REGION_MARGIN_MM)
             & (np.abs(axial) < half_height_mm + _REGION_MARGIN_MM))
    out = trimesh.Trimesh(np.asarray(arch.vertices).copy(), arch.faces[keep], process=False)
    out.remove_unreferenced_vertices()
    return out


def arch_with_parts(arch: trimesh.Trimesh,
                    posed_parts: Sequence[Tuple[trimesh.Trimesh, np.ndarray]]) -> trimesh.Trimesh:
    """The arch plus each part transformed by its pose — one composite deliverable mesh.
    A CONCATENATION, not a boolean: where a part's pose buries part of its own volume
    inside the arch (§10-AS.11's dish, a construction shank seated past the gum), that
    buried half stands in the file as an internal wall the arch's own shell still
    surrounds. ``arch_with_parts_fused`` (§10-AT 3b) is the true-union deliverable now;
    every call site prefers it, and this function survives ONLY as its fail-open
    fallback — the honest degradation when a true union cannot be built at all."""
    placed = []
    for part, pose in posed_parts:
        p = part.copy()
        p.apply_transform(np.asarray(pose, float))
        placed.append(p)
    return trimesh.util.concatenate([arch.copy()] + placed)


def arch_with_parts_fused(arch: trimesh.Trimesh,
                          posed_parts: Sequence[Tuple[trimesh.Trimesh, np.ndarray]],
                          excise_sites: "Optional[Sequence[Tuple[trimesh.Trimesh, np.ndarray, float]]]" = None
                          ) -> Tuple[trimesh.Trimesh, List[str]]:
    """THE COMPOSITE BECOMES A TRUE UNION (§10-AT 3b, on §10-AS.16/19's own doctrine:
    the shipped artifact is the open arch, and ``arch_with_parts``'s concatenation left
    a part's buried half standing in the file as an internal wall the shell still
    surrounds — a real boolean seam for a lab's slicer to reason about, not a fact
    about the case). Every downloadable composite call site now prefers this function;
    ``arch_with_parts`` survives only as ITS fallback.

    The mechanism: ``solidified_shell_cached`` gives the arch a momentary closed solid
    to union against — the same call ``_csg_carve`` makes, and it needs the same
    crowns-up axis for the same reason. Each part is posed as its own exact watertight
    solid via ``exact_cap_punch(part, 0.0, pose)`` — a ZERO offset, which lids an open
    bore and self-heals a creased dilation's self-intersection WITHOUT ever dilating a
    millimetre: exactly "the part as a watertight solid at its pose", nothing grown. A
    true manifold union of the arch solid with every part solid merges any overlap —
    the buried half stops being a wall and becomes ordinary interior material,
    indistinguishable from the shell around it. ``strip_fabricated`` then does its
    usual job (the union needed the arch's fabricated base/skirt to have something to
    close against, and that base is not the artifact) — except its keep test must ALSO
    keep each part's own surface, which lies nowhere near the original scan and would
    otherwise read as fabricated too: a dense surface sample of the part solids (the
    same ``cKDTree`` + ``trimesh.sample.sample_surface`` idiom ``strip_fabricated``
    already uses to keep a cut's own recess) feeds it as ``punch_regions_test``.

    Two honest degradations, never a dead package: a single part that cannot be built
    into a watertight solid (a degenerate template) falls back to CONCATENATING just
    that part, with a note — the rest still fuse. Any other failure — the union itself
    refusing, the arch failing to solidify — falls the WHOLE composite back to
    ``arch_with_parts`` for every part, with its own note; the notes from any per-part
    fallback that already happened are lost in that case, because the whole composite
    it would have landed on no longer exists.

    THE TRACKED UNION (boolean-engine plan W1, 2026-08-13): the arch solid is tagged
    scan-vs-fabricated at the source (``fabricated_face_mask``) and the union runs
    through manifold3d's own provenance (``union_tracked``) — the strip that follows
    reads WHICH solid a face's material came from, part or shell-scan or
    shell-closure, rather than sampling a dense point cloud off every part solid and
    measuring distance. A refusal here (a manifold3d rejection the plain trimesh
    engine tolerated, or the tracked union itself coming back empty) falls back to
    the untracked engine plus the old distance-based strip, with a note — the
    geometry degrades silently, the manifest never does.

    DEFECT 1 EXCISION (client-ruled, live verification 2026-08-15): ``excise_sites``
    — optional ``(template, pose, rim_r)`` triples, independent of ``posed_parts`` —
    names the sites whose SCANNED cap must never survive this fuse: "white patches
    poking through the library cap" was this composite's own symptom of the boolean
    cutting the template's volume while the scan stands proud of it. The caller for
    ``arch-with-healingcaps.stl`` passes the SAME templates/poses already carried in
    ``posed_parts``, plus each site's catalog rim radius — the part's own posed
    surface REPLACES the scanned cap, never merges with its crust. The caller for
    ``arch-with-constructions.stl`` passes none: its base (``arch_removed``) already
    went through ``_csg_carve``'s own excision, so nothing new can have grown proud
    of it by this second fuse. The shared classifier
    (``case_prep.pipeline.isolation.scanned_cap_face_mask``) is applied to the FUSED
    result and restricted to scan-provenance faces ONLY — tool/part-provenance is
    read straight off the tracked union's own ``source`` array (never approximated),
    so a part's own material can structurally never be excised by this step."""
    from scipy.spatial import cKDTree

    try:
        solid = solidified_shell_cached(arch)
        part_solids: List[trimesh.Trimesh] = []
        fallback_parts: List[Tuple[trimesh.Trimesh, np.ndarray]] = []
        notes: List[str] = []
        solid_pos: dict = {}
        for index, (part, pose) in enumerate(posed_parts, 1):
            try:
                part_solids.append(exact_cap_punch(part, 0.0, np.asarray(pose, float)))
                solid_pos[index - 1] = len(part_solids) - 1
            except Exception as exc:  # noqa: BLE001 — per-part honest fallback;
                # the rest of the parts still get the true union below
                notes.append(f"part {index} could not be fused ({exc}) — "
                            f"concatenated instead")
                fallback_parts.append((part, pose))

        tracked_keep: Optional[np.ndarray] = None
        try:
            fabricated = fabricated_face_mask(arch, solid)
            tracked = default_kernel().union_tracked(
                [solid] + part_solids, fabricated.astype(np.int64))
            fused = tracked.mesh
            if len(fused.faces) == 0:
                raise ValueError("the fused composite came back empty")
            tracked_keep = strip_tracked(tracked)
        except Exception as exc:  # noqa: BLE001 — fail-open to the
            # untracked engine and the distance strip
            fused = default_kernel().union([solid] + part_solids)
            if len(fused.faces) == 0:
                raise ValueError("the fused composite came back empty")
            notes.append(f"the provenance-tracked strip could not run "
                        f"({exc}) — the distance-based strip was used "
                        f"instead")

        if tracked_keep is not None:
            keep = tracked_keep
        else:
            if part_solids:
                # the dense sample lives on the PART solids, not the arch — these are
                # the surfaces the strip below must keep even though they sit nowhere
                # near the original scan (one tree over every part, same idiom as
                # strip_fabricated's own arch sample)
                surf_pts = np.vstack([
                    trimesh.sample.sample_surface(ps, 150_000)[0]
                    for ps in part_solids])
                d_part, _ = cKDTree(surf_pts).query(
                    np.asarray(fused.triangles_center, float))
                inside_mask = d_part < 0.45
            else:
                inside_mask = np.zeros(len(fused.faces), bool)
            keep = strip_fabricated(fused, arch, inside_mask)

        # DEFECT 1 EXCISION — see this function's own docstring. Applied AFTER the
        # strip decides `keep` (closure is already gone either way), restricted to
        # SCAN-provenance faces only: on the tracked path that is exact (`source ==
        # 0`, structurally disjoint from every part's own `source >= base_groups`
        # — the assertion below is the permanent, cheap version of that fact, the
        # same idiom rider-b's own guard uses); on the untracked fallback there is
        # no per-face provenance to read, so the geometric mask is restricted to
        # `~inside_mask` (the same distance-based "is this a part's own surface"
        # test the strip itself just used) instead.
        excise = np.zeros(len(fused.faces), bool)
        if excise_sites:
            for e_template, e_pose, e_rim_r in excise_sites:
                try:
                    excise |= scanned_cap_face_mask(
                        fused, e_template, np.asarray(e_pose, float),
                        float(e_rim_r),
                    full_footprint=True)
                except Exception:  # noqa: BLE001 — the excision refines an
                    # already-successful fuse; a site it cannot read never fails
                    # the whole composite
                    continue
            if tracked_keep is not None:
                scan_provenance = np.asarray(tracked.source) == 0
                excise &= scan_provenance
                assert not (excise & (np.asarray(tracked.source)
                                      >= tracked.base_groups)).any(), (
                    "DEFECT-1 excision must be scan-provenance only — a "
                    "part's own face was about to be dropped from the fuse")
            else:
                excise &= ~inside_mask
            keep = keep & ~excise

            # DEFECT A — THE ORPHAN FLAPS (client-ruled, live verification
            # 2026-08-15): see ``isolation.orphan_flap_mask``'s own docstring.
            # Candidate faces are exactly the scan-provenance set the excision
            # above just used (``scan_provenance``/``~inside_mask``, whichever
            # path built it) restricted to what the strip actually kept —
            # never a part's own surface, which this test must not touch.
            scan_candidate = (scan_provenance if tracked_keep is not None
                              else ~inside_mask)
            site_poses = [(np.asarray(e_pose, float), float(e_rim_r))
                         for _, e_pose, e_rim_r in excise_sites]
            orphan = orphan_flap_mask(fused, site_poses,
                                      candidate=keep & scan_candidate)
            keep = keep & ~orphan

        F = np.asarray(fused.faces)
        V = np.asarray(fused.vertices, float)
        out = trimesh.Trimesh(V.copy(), F[keep].copy(), process=False)
        out.remove_unreferenced_vertices()
        # THE DRAPE (goal-3 S2, plan 2026-08-16): the full-footprint
        # excision rings the aligned cap with a white annulus where the
        # scanned crust died — the scan's edge drapes onto the cap's own
        # wall (see ``_drape_scan_edge_to_cap_wall``). Tracked path only
        # (the inner ring is provenance-read); the untracked fallback's
        # note already discloses the degraded build. ``excise_sites`` and
        # ``posed_parts`` share one order (the emit caller's own zip), so
        # a site's part faces are its solid's own source group. Every
        # site's drape reads the SAME pre-drape boundary, whatever the
        # build order — the carve's own bridge idiom.
        drape_strips: list = []
        if excise_sites and tracked_keep is not None:
            src_kept = np.asarray(tracked.source)[keep]
            for e_index, (_e_t, e_pose, e_rim_r) in enumerate(excise_sites):
                pos = solid_pos.get(e_index)
                if pos is None:
                    continue
                part_faces = src_kept == (tracked.base_groups + pos)
                if not bool(part_faces.any()):
                    continue
                strip, undraped = _drape_scan_edge_to_cap_wall(
                    out, part_faces, np.asarray(e_pose, float),
                    float(e_rim_r))
                if strip is not None:
                    drape_strips.append(strip)
                    notes.append(
                        f"part {e_index + 1} wears the scan's edge draped "
                        f"onto its wall — the tissue there sat under the "
                        f"cap and was never scanned")
                elif undraped:
                    # the same honesty the collar bridge's fragmentary
                    # note carries — the fleet gate found the fused
                    # composites failing MUTE on edges their capless
                    # twins disclosed (zimmer-4.5/cap6020, 2026-08-17)
                    notes.append(
                        f"part {e_index + 1} keeps an open gap at its "
                        f"base ({undraped} scan-edge points in scattered "
                        f"arcs) — the drape was skipped")

        # HARD INVARIANT 2, BEFORE the per-part fallback concatenation: a
        # part that could not fuse is a DOCUMENTED extra body, never a
        # floater — the cull must not see it. Each part's OWN BODY is
        # PROTECTED: an excision moat can ring the aligned cap completely,
        # and a relief-hovering construction never touches its socket —
        # disjoint, but the artifact's point. PER PART, ONE BODY (measured
        # on 295811960's own rebuild: blanket part-provenance protection
        # rescued 24 one-to-two-face union slivers and a 236-face crust
        # shard at the cap wall — all debris): a part is a single solid,
        # so per part group the component carrying MOST of its faces is
        # the part; every other part-tagged fragment is a shard the cull
        # may eat.
        src_full = (np.asarray(tracked.source)[keep]
                    if tracked_keep is not None else None)
        if drape_strips:
            n_before = len(out.faces)
            out = trimesh.util.concatenate([out] + drape_strips)
            out.merge_vertices()
            out = _shed_nonmanifold_strip_faces(out, n_before)
            if src_full is not None:
                src_full = np.concatenate(
                    [src_full, np.full(len(out.faces) - n_before, -1,
                                       dtype=src_full.dtype)])
        if src_full is not None:
            comps = trimesh.graph.connected_components(
                out.face_adjacency, min_len=0,
                nodes=np.arange(len(out.faces)))
            protect = np.zeros(len(out.faces), bool)
            for pos in sorted(set(solid_pos.values())):
                g = tracked.base_groups + pos
                counts = [int((src_full[comp] == g).sum())
                          for comp in comps]
                best = int(np.argmax(counts))
                if counts[best]:
                    protect[comps[best]] = True
        elif part_solids:
            # the untracked fallback has no per-face provenance to count —
            # any part-material face protects its component; the fallback
            # note already discloses the degraded build
            protect = inside_mask[keep]
        else:
            protect = np.zeros(len(out.faces), bool)
        cull_sites = ([(np.asarray(p, float), float(r))
                       for _t, p, r in excise_sites] if excise_sites
                      else [(np.asarray(p, float), 3.0)
                            for _part, p in posed_parts])
        out, cull_notes = cull_floating_fragments(out, cull_sites,
                                                  protect=protect,
                                                  style="part")
        notes.extend(cull_notes)
        if fallback_parts:
            placed = []
            for part, pose in fallback_parts:
                p = part.copy()
                p.apply_transform(np.asarray(pose, float))
                placed.append(p)
            out = trimesh.util.concatenate([out] + placed)
        return out, notes
    except Exception as exc:  # noqa: BLE001 — the fallback IS the containment; this
        # function can never return nothing
        return arch_with_parts(arch, posed_parts), [
            f"the fused composite could not be built ({exc}) — the parts are "
            f"concatenated instead"]


def _hole_bore(pose_matrix: np.ndarray, radius_mm: float, collar_z_local: float,
               depth_mm: float = 8.0, collar_width_mm: float = 2.2,
               sections: int = 64) -> trimesh.Trimesh:
    """A SOCKET in the pose frame (client fix 2026-07-14): a cylinder wall from the
    collar plane down to a FLOOR disc — closed at the bottom so the model reads solid —
    plus a COLLAR annulus at the local surface height that bridges the wall to the
    surrounding scan, covering the culled crater edge. Faces are wound for a viewer
    looking INTO the socket (floor/collar up, wall inward): lab tools shade by normals
    and an inside-out socket reads as a black void there, even though our own
    DoubleSide viewers hide it."""
    ang = np.linspace(0.0, 2.0 * np.pi, sections, endpoint=False)
    cx, sx = np.cos(ang), np.sin(ang)
    top = np.c_[radius_mm * cx, radius_mm * sx, np.full(sections, collar_z_local)]
    bot = np.c_[radius_mm * cx, radius_mm * sx, np.full(sections, collar_z_local - depth_mm)]
    rim = np.c_[(radius_mm + collar_width_mm) * cx, (radius_mm + collar_width_mm) * sx,
                np.full(sections, collar_z_local)]
    # floor disc = outer ring (shared with the wall base) + mid ring + centre vertex
    mid = np.c_[(radius_mm * 0.5) * cx, (radius_mm * 0.5) * sx,
                np.full(sections, collar_z_local - depth_mm)]
    centre = np.array([[0.0, 0.0, collar_z_local - depth_mm]])
    verts = np.vstack([top, bot, rim, mid, centre])
    n_c = 4 * sections  # centre vertex index
    faces = []
    for i in range(sections):
        j = (i + 1) % sections
        faces += [[i, sections + i, sections + j], [i, sections + j, j]]        # wall
        faces += [[i, j, 2 * sections + j], [i, 2 * sections + j, 2 * sections + i]]  # collar
        faces += [[sections + i, 3 * sections + i, 3 * sections + j],
                  [sections + i, 3 * sections + j, sections + j]]               # floor outer
        faces += [[3 * sections + i, n_c, 3 * sections + j]]                    # floor fan
    # wind every face toward the socket interior (review 2026-07-14: the loop above is
    # historical outward winding — flipping once here keeps the index math untouched)
    bore = trimesh.Trimesh(verts, np.asarray(faces)[:, [0, 2, 1]], process=False)
    bore.apply_transform(np.asarray(pose_matrix, float))
    return bore


def arch_with_clean_holes(arch: trimesh.Trimesh,
                          sites: Sequence[Tuple[np.ndarray, float]]) -> trimesh.Trimesh:
    """The 3shape-style capless model (client spec v2 2026-07-12, socket fix
    2026-07-14): each cap region is removed and replaced by a floored SOCKET — closed
    at the bottom so it reads solid, its wall bridged to the scan surface by a collar
    annulus at the LOCAL gingiva height (sampled from the arch, not assumed).
    ``sites`` is (pose_matrix, radius_mm) per cap. Visual/deliverable composite;
    watertight CSG remains the follow-up if a manufacturer needs a fused solid."""
    out = arch
    bores = []
    V = np.asarray(arch.vertices, float)
    for pose, radius in sites:
        pose = np.asarray(pose, float)
        origin, axis = pose[:3, 3], pose[:3, :3] @ np.array([0.0, 0.0, 1.0])
        rel = V - origin
        axial = rel @ axis
        radial = np.linalg.norm(rel - np.outer(axial, axis), axis=1)
        ring = axial[(radial > radius + 0.5) & (radial < radius + 2.5)
                     & (np.abs(axial) < 6.0)]
        collar_z = float(np.median(ring)) if len(ring) else 0.0
        # cull the FULL bore column: depth below the collar AND the whole scanned cap
        # above it (a cap top left floating over the opening reads absurd)
        span_up = 8.0
        shifted = pose.copy()
        shifted[:3, 3] = origin + axis * (collar_z + (span_up - _HOLE_DEPTH_MM) / 2.0)
        out = remove_cap_region(out, shifted, radius_mm=radius,
                                half_height_mm=(_HOLE_DEPTH_MM + span_up) / 2.0)
        bores.append(_hole_bore(pose, radius + _REGION_MARGIN_MM, collar_z,
                                _HOLE_DEPTH_MM))
    return trimesh.util.concatenate([out] + bores)


_HOLE_DEPTH_MM = 8.0  # socket depth below the collar (floored — reads solid)

# THE SOCKET'S VISIBLE DEPTH (client 2026-08-09, on 276794487's tall 6030 cap):
# a cap whose base sits ~4mm subgingival lined a socket that hung out of the
# thin scan shell as a protruding cylinder — "showing all the way down until
# where the implant is going rather than just the healing cap". The dish the
# competitor renders is SHALLOW. The socket keeps the cap's exact footprint,
# but its floor stops at (collar − this) when the cap's offset base is deeper.
_SOCKET_VISIBLE_DEPTH_MM = 1.8
# the platform countersink never reads shallower than this (client
# 2026-08-10: the floor shows the gingival offset — but a 0.2mm step is
# one scan-triangle row, invisible; 0.5mm is the legibility floor)
_PLATFORM_COUNTERSINK_MIN_MM = 0.5

# THE CULL'S OWN CLEARANCE (client 2026-08-09, on 295811960's torn flaps): the
# liner is the template + the applied relief — the SEAT truth — but the SCANNED
# cap deviates from the template (p90 0.36mm measured on the client's case), and
# a cull sized exactly to the relief left every real-cap excursion standing as a
# torn crescent around the socket. The cull sweeps this much beyond the relief;
# the liner does not move. Far tighter than the old cylinder's rim+0.6-on-a-
# bounding-can, and sized to cover seat p90 + scan noise.
_CULL_MARGIN_MM = 0.5


def _envelope_profile(template: trimesh.Trimesh,
                      offset_mm: float) -> Tuple[np.ndarray, np.ndarray]:
    """The cap's per-height maximum-radius profile + the relief, as ``(zs, prof)``
    arrays in the template's own canonical frame — the one source both the lathe
    and the collar annulus read. Smoothed OUTWARD-ONLY (a ring keeps the larger of
    itself and its neighbours' blend), so vendor tessellation steps round off
    while the envelope still covers every point of the cap."""
    pts = np.asarray(template.vertices, float)
    if len(pts) < 3 or not np.isfinite(pts).all():
        raise ValueError("imprint template is empty or degenerate")
    radii = np.hypot(pts[:, 0], pts[:, 1])
    z = pts[:, 2]
    z_lo, z_hi = float(z.min()), float(z.max())
    if z_hi - z_lo < 0.2:
        raise ValueError("imprint template has no height")
    bins = 40
    idx = np.clip(((z - z_lo) / (z_hi - z_lo) * bins).astype(int), 0, bins - 1)
    prof = np.full(bins, np.nan)
    for b in range(bins):
        sel = radii[idx == b]
        if len(sel):
            prof[b] = float(sel.max())
    good = np.flatnonzero(~np.isnan(prof))
    if len(good) == 0:
        raise ValueError("imprint template has no radial extent")
    # sparse vendor tessellation can leave empty height bins — inherit neighbours
    prof = np.interp(np.arange(bins), good, prof[good])
    # smooth it out (client 2026-08-09), without ever dipping below the true
    # envelope: the blend only wins where it is LARGER
    blend = np.convolve(np.pad(prof, 1, mode="edge"),
                        [0.25, 0.5, 0.25], mode="valid")
    prof = np.maximum(prof, blend)
    prof = np.maximum(prof + float(offset_mm), 0.05)
    zs = z_lo + (np.arange(bins) + 0.5) * (z_hi - z_lo) / bins
    # the end rings move to the offset extremes, so the solid clears the cap's
    # own top and base by the relief exactly as the walls clear its sides
    zs[0], zs[-1] = z_lo - float(offset_mm), z_hi + float(offset_mm)
    return zs, prof


def _envelope_solid(template: trimesh.Trimesh, offset_mm: float) -> trimesh.Trimesh:
    """The cap's REVOLUTE ENVELOPE grown by ``offset_mm`` — per-height maximum
    radius, lathed into a closed solid (client 2026-08-09, competitor comp).

    This replaced an exact-surface dilation (vertex normals on the sealed vendor
    CAD) after live testing: the exact surface faithfully reproduced the screw
    slot and coded trenches into the socket — noise, not information, in a seat —
    and its sealing machinery inherited every defect of vendor tessellation. The
    envelope reads the template as a POINT CLOUD (no watertightness demanded of
    the input), and the lathe is watertight by construction: smooth wall, a flat
    disc at each end, reliable ``contains``. The bottom disc, offset downward,
    becomes the socket's floor."""
    zs, prof = _envelope_profile(template, offset_mm)
    bins = len(zs)
    seg = 64
    ang = np.linspace(0.0, 2.0 * np.pi, seg, endpoint=False)
    ca, sa = np.cos(ang), np.sin(ang)
    rings = np.concatenate([
        np.column_stack([rr * ca, rr * sa, np.full(seg, zz)])
        for rr, zz in zip(prof, zs)])
    verts = np.vstack([rings, [[0.0, 0.0, zs[0]]], [[0.0, 0.0, zs[-1]]]])
    faces = []
    for i in range(bins - 1):
        a0, b0 = i * seg, (i + 1) * seg
        for j in range(seg):
            k = (j + 1) % seg
            # outward winding: phi-hat x z-hat = r-hat
            faces.append([a0 + j, a0 + k, b0 + k])
            faces.append([a0 + j, b0 + k, b0 + j])
    bot, top = len(verts) - 2, len(verts) - 1
    last = (bins - 1) * seg
    for j in range(seg):
        k = (j + 1) % seg
        faces.append([bot, k, j])                  # bottom cap faces -z
        faces.append([top, last + j, last + k])    # top cap faces +z
    out = trimesh.Trimesh(verts, np.asarray(faces, int), process=False)
    out.merge_vertices()
    if not out.is_watertight:  # unreachable by construction; refuse over guessing
        raise ValueError("imprint envelope failed to close")
    return out


def _collar_z_local(arch_vertices: np.ndarray, pose: np.ndarray,
                    rim_radius_mm: float) -> float:
    """The local gingiva height about the pose axis — the same ring-sampling rule
    ``arch_with_clean_holes`` uses, factored so both socket shapes share it."""
    origin, axis = pose[:3, 3], pose[:3, :3] @ np.array([0.0, 0.0, 1.0])
    rel = arch_vertices - origin
    axial = rel @ axis
    radial = np.linalg.norm(rel - np.outer(axial, axis), axis=1)
    ring = axial[(radial > rim_radius_mm + 0.5) & (radial < rim_radius_mm + 2.5)
                 & (np.abs(axial) < 6.0)]
    return float(np.median(ring)) if len(ring) else 0.0


def _collar_plane(arch_vertices: np.ndarray, pose: np.ndarray,
                  rim_radius_mm: float) -> np.ndarray:
    """The gingiva as a PLANE about the pose axis (client 2026-08-09): one median
    collar height left the socket wall standing in a ~0.5mm proud crescent out of
    the LOW side of a tilted arch, and azimuth bins inherit the same defect in a
    smaller coat — the ring band samples tissue 0.5-2.5mm OUTWARD of the wall, so
    any per-bearing height still over-reads a slope at the wall itself. A fitted
    plane extrapolates the tilt back to the wall exactly. Least squares of
    ``axial = a + b*x + c*y`` over the same ring band ``_collar_z_local`` uses
    (local in-plane x/y about the pose origin); returns ``[a, b, c]``. Falls back
    to the flat median plane when the band is empty or degenerate."""
    origin = pose[:3, 3]
    R = pose[:3, :3]
    axis = R @ np.array([0.0, 0.0, 1.0])
    rel = arch_vertices - origin
    axial = rel @ axis
    in_plane = rel - np.outer(axial, axis)
    radial = np.linalg.norm(in_plane, axis=1)
    band = ((radial > rim_radius_mm + 0.5) & (radial < rim_radius_mm + 2.5)
            & (np.abs(axial) < 6.0))
    if band.sum() < 8:
        level = float(np.median(axial[band])) if band.any() else 0.0
        return np.array([level, 0.0, 0.0])
    x = in_plane[band] @ (R @ np.array([1.0, 0.0, 0.0]))
    y = in_plane[band] @ (R @ np.array([0.0, 1.0, 0.0]))
    A = np.column_stack([np.ones(len(x)), x, y])
    sol, *_ = np.linalg.lstsq(A, axial[band], rcond=None)
    if not np.isfinite(sol).all():
        return np.array([float(np.median(axial[band])), 0.0, 0.0])
    return sol


def cap_imprint_holes(arch: trimesh.Trimesh,
                      sites: Sequence[Tuple[trimesh.Trimesh, np.ndarray,
                                            float, float]],
                      visible_depth_mm: Optional[float] =
                      _SOCKET_VISIBLE_DEPTH_MM,
                      top_floor: bool = False
                      ) -> Tuple[trimesh.Trimesh, list]:
    """THE SEAT IS THE CAP'S ENVELOPE SOCKET (client 2026-08-06 §10-AO; reshaped
    2026-08-09 on the client's competitor screenshot): the arch with each scanned
    cap replaced by a CLEAN RECESS — the cap's revolute envelope grown by the
    relief, with a flat floor — the industry ditch as the competitor's tooling
    renders it, not the cap's exact tessellated surface (which printed the screw
    slot into the floor: noise in a seat).

    Per site ``(template, pose_matrix, offset_mm, rim_radius_mm)``:
      * faces with ANY vertex inside the posed envelope are culled — a centroid
        cull kept straddling triangles whose needle tips overhung the hole as a
        fringe of spikes (6,272 on cap7020, the client's screenshot); only the
        cap's footprint + offset is removed and the gum beside it survives;
      * the hole is lined with the envelope's own surface below the local gum
        line, wound to face the void — smooth walls, and THE FLOOR IS THE FLAT
        DISC AT THE CAP'S OFFSET BASE ("there needs to be a floor"); the mouth
        stays open where the cap emerged from the gum;
      * a site whose template cannot make an envelope FALLS BACK to the old
        cylinder socket for that site, and says so — the second element of the
        returned tuple is the list of those sentences (the caller surfaces them
        on the site's own row). ``rim_radius_mm`` exists for exactly that
        fallback.

    True CSG is deliberately NOT used: no boolean backend ships in this
    environment, and scan shells are open meshes where booleans are fragile —
    face-culling against the watertight envelope plus the envelope's own surface
    achieves the subtraction, robustly."""
    kept_arch, socket, notes = cap_imprint_parts(
        arch, sites, visible_depth_mm=visible_depth_mm, top_floor=top_floor)
    if socket is None:
        return kept_arch, notes
    return trimesh.util.concatenate([kept_arch, socket]), notes


def _gingival_floor_a(V: np.ndarray, solid: trimesh.Trimesh, index: int,
                      origin: np.ndarray, axis: np.ndarray, xl: np.ndarray,
                      yl: np.ndarray, zs_p: np.ndarray, prof_p: np.ndarray,
                      depth_mm: Optional[float]) -> Tuple[float, float]:
    """THE GUM-FOLLOWING FLOOR (§10-AS.10's own ring-read heuristic, factored
    here so every recess this module cuts — the dish, the platform
    countersink, and the fourth artifact-6 ruling's gingival floor — shares
    ONE measurement rather than three copies of it): the local gingival
    height about one site's pose axis, read off the SOLIDIFIED shell's own
    vertices (``V``, never the punch template's), and the floor's axial
    coordinate ``depth_mm`` below it.

    THE RING: the shell's own vertices just outside the cap's own footprint
    (``r_ref = max(prof_p)``, the widest the relief envelope ever reaches) —
    ``r_ref+0.1`` to ``r_ref+1.2`` radially, within 6mm of the site's own
    mid-height axially. The LOW quartile of that band's axial height is the
    read (``h_low``), not the median: a band that grazes a neighbouring
    crown reads mostly tooth, and the lowest surface in it is the gingiva
    (measured, cap6030: a median once read +3.2mm of "gum"). Fewer than 8
    vertices in the band is an honest refusal (``ValueError``, naming the
    site), never a floor guessed from nothing.

    THE CLAMP, when ``depth_mm`` is given: ``h_low - depth_mm`` is floored
    never below the envelope's own base (``zs_p[0]`` — a floor cannot sink
    past the cap's own exact bottom plus its relief), then probed against
    the SOLID itself — a downward ray at the footprint's centre plus four
    off-axis points at ``0.6 * r_ref`` finds the model's true material limit
    directly beneath this site (the same idiom the box fixture's own
    -0.5mm underside is measured through); a floor that would land past
    that limit is pulled up to 0.3mm above it, so a thin model never opens
    a hole where a floor was asked for. ``depth_mm is None`` means "no
    floor at all" — ``floor_a`` is the envelope's own base, unclamped.

    Returns ``(floor_a, h_low)`` — ``h_low`` is also the tint-region
    reference ``_csg_carve`` threads onward through ``regions``."""
    rel = V - origin
    a = rel @ axis
    r = np.hypot(rel @ xl, rel @ yl)
    r_ref = float(np.max(prof_p))
    band = (r > r_ref + 0.1) & (r < r_ref + 1.2) & (np.abs(a) < 6.0)
    if int(band.sum()) < 8:
        raise ValueError(f"no gum ring around site {index}")
    # the LOW quartile: a median once read a neighbouring crown as
    # +3.2mm of gum; the lowest surface in the ring is the gingiva
    h_low = float(np.percentile(a[band], 25))
    if depth_mm is None:
        return float(zs_p[0]), h_low
    floor_a = max(h_low - float(depth_mm), float(zs_p[0]))
    # the floor stays INSIDE the solid: on a thin model a punch that
    # reaches past the underside cuts a through-hole, not a seat.
    # A raw OPEN scan carries no "underside" of its own (it is one
    # surface, not a slab) — reading the footprint's raw vertices
    # for a "thin material" signal found only the SAME top surface
    # again and pushed the floor above the gum entirely on a real
    # single-sheet scan. The SOLIDIFIED shell (skirt + base) is the
    # honest source: a ray straight down the pose axis, probed at
    # the footprint's centre and a few off-axis points, finds the
    # model's true material limit directly beneath this site —
    # exactly the box fixture's own -0.5mm underside where one
    # genuinely exists, and the base plate far below on an open
    # single-sheet scan where none does.
    probes = [origin + axis * 100.0]
    if r_ref > 0:
        for ang in (0.0, np.pi / 2, np.pi, 3 * np.pi / 2):
            probes.append(origin + axis * 100.0
                          + (xl * np.cos(ang) + yl * np.sin(ang))
                          * (r_ref * 0.6))
    hits, *_ = solid.ray.intersects_location(
        ray_origins=probes, ray_directions=[-axis] * len(probes))
    if len(hits):
        base_a = float(((np.asarray(hits, float) - origin) @ axis).min())
        floor_a = max(floor_a, base_a + 0.3)
    return floor_a, h_low
_BRIDGE_Z_BAND_MM = 3.0     # a real moat sits close to the mouth's own height —
#                             tighter than the file's other (radial) gum-ring bands
#                             on purpose: an axial hole clean through a THIN model
#                             (a boundary loop on the model's own FAR side, e.g. a
#                             box fixture's underside) must never read as the near
#                             side's own moat
# THE MOUTH RULE'S OWN NUMBERS (2026-08-16, the loop census on 276794487's
# run 20260816-155459: a real coded cap's tool surface carries dozens of
# boundary loops — trench edges, floor cuts, deviation windows — but the
# machined mouth is BY CONSTRUCTION the outermost: the punch is a revolute
# whose widest cut rings the mouth. Measured: mouth r 2.9-3.1 with radial
# std 0.18-0.28; every internal edge r <= 2.2).
_FLOOR_LID_BAND_MM = 0.3    # a floor-height loop sits AT the floor plane
_FLOOR_LID_MIN_VERTICES = 12  # a real pocket breach is a ring (measured: 395
                              # vertices on 276794487) — a flush cut's own
                              # degenerate slivers are not floor gaps
_MOUTH_MIN_VERTICES = 24    # a mouth is a ring, not a sliver
# THE BANK VOTE's numbers (goal-3 S1; slice-0 census on 295811960):
_BANK_GAP_MM = 0.25         # radial gap that separates two banks (the
                            # chained fixture's 2.3/2.6 rings must split;
                            # within-bank scan noise gaps measure ≪0.1)
_BANK_SEARCH_MM = 2.0       # the vote's outer reach past the mouth — the
                            # MOAT's own scale (measured banks sit within
                            # ~1mm of the mouth), never the loop test's
                            # generous 8mm, which let a flat fixture's own
                            # outer edge vote as a "bank"
_BANK_THETA_BINS = 48       # bearing bins for the bank's occupancy read
# FULL RING vs CRESCENT vs FRAGMENTS (probe on 295811960's live carve,
# 2026-08-16: the real moat is ONE contiguous 82° crescent — 272 points,
# radial MAD 0.094, every occupied bin in a single run — and the client's
# screenshots always showed the white on one side; a full-ring coverage
# gate refused exactly this shape):
_BANK_FULL_GAP_BINS = 2     # ≤15° of empty bearings is sampling scale — a
                            # FULL ring (fixture rings of 36-44 points over
                            # 48 bins leave isolated 1-bin gaps)
_BANK_ARC_BINS_MIN = 6      # a crescent must span ≥45° — between the
                            # sparse-arc refusal (29°) and the narrowest
                            # measured real crescent (82°, 295811960)
_BANK_WINDOW_FILL_MIN = 0.8  # and be SOLID inside its own window (measured
                             # 1.0 live) — two opposite arcs are not one
                             # crescent, and zipping across their mutual
                             # gap would fabricate a chord wall
_BANK_DUP_TOL_MM = 0.25     # a loop whose MEDIAN distance to the mouth is
                            # under this is the mouth's own flush
                            # counterpart, not a bank. Measured populations
                            # (2026-08-16): flush-cut crack rings 0.03-0.2;
                            # the narrowest real moat 0.35; real banks
                            # >=1.0. A sub-quarter-millimetre gap is
                            # contact at this pipeline's own weld scale.
_MOUTH_ROUNDNESS_MM = 0.45  # measured mouth std 0.28 max, with headroom
_MOUTH_TIE_MM = 0.3         # two round loops this close in radius = a junction
_BRIDGE_ROUNDNESS_MM = 0.3  # "roughly concentric" made a number: a loop's own
#                             radial std about the axis past this is not a ring at
#                             all — it is some other cut edge that merely passed
#                             the radius/height gates (measured: a thin fixture's
#                             own far-side exit hole reads 0.38mm here; the true
#                             moat loop, cut by a lathe about one axis, reads ~0)


def _boundary_loops_of(mesh: trimesh.Trimesh) -> "List[np.ndarray]":
    """Every boundary loop of ``mesh``, as ordered ``(n, 3)`` point arrays
    (``trimesh``'s own ``outline()``/``discrete`` — the same idiom
    ``domain.channel.channel_from_boundary_loops`` reads catalog channel
    loops through), first point never repeated. ``[]`` when ``mesh`` is
    empty, watertight (no boundary at all), or its own boundary cannot be
    walked at all (a junction ``outline()`` itself refuses) — the caller's
    signal to fail open, never this function's to raise on."""
    if len(mesh.faces) == 0:
        return []
    try:
        outline = mesh.outline()
    except Exception:  # noqa: BLE001 — an unreadable boundary is "no loops",
        # for the caller's own fail-open ladder, never a raise from here
        return []
    loops = []
    for loop in outline.discrete:
        pts = np.asarray(loop, float)
        if len(pts) >= 2 and np.allclose(pts[0], pts[-1]):
            pts = pts[:-1]  # a closed polyline repeats its first vertex
        if len(pts) >= 3:
            loops.append(pts)
    return loops


def _zip_loop_bridge(inner_pts: np.ndarray, inner_theta: np.ndarray,
                     outer_pts: np.ndarray, outer_theta: np.ndarray
                     ) -> "Tuple[np.ndarray, np.ndarray, np.ndarray]":
    """Triangulates a strip bridging two closed, "roughly concentric"
    polylines of POSSIBLY DIFFERENT vertex counts, using every one of
    their own REAL points — never an interpolated one — so the result can
    be WELDED onto its source loops by an exact-coordinate vertex merge
    afterward (``trimesh.Trimesh.merge_vertices``, run by the caller once
    the bridge lands: real dental recesses and their scan edges are two
    independently-tessellated loops, so a fixed common vertex count the
    envelope-era collar's own synthesized rings could assume (git history,
    ``35c888a``) does not hold here).

    Both loops are sorted by bearing (``inner_theta``/``outer_theta``)
    first, then walked TOGETHER on a common UNWRAPPED angle: at each step
    the ring whose NEXT point sits at the smaller cumulative bearing
    advances, and one triangle closes using the ring that just advanced
    plus the other ring's current point. Comparing CUMULATIVE bearing
    (each ring's own angles extended by one wrap-around entry at
    ``theta[0] + 2*pi``) rather than the next LOCAL step's size is the
    load-bearing choice: a local-step comparison let the denser ring run
    all the way around while the sparser one had barely started (measured
    directly at this slice's own pin time — a 32-vs-40-point fixture left
    one ring's index wrapped back to its own start after only 2 of the
    other ring's 32 steps, producing a self-crossing, inconsistently-
    wound strip). Exactly ``len(inner_pts) + len(outer_pts)`` triangles; a
    closed strip with exactly two boundary loops (the two inputs) and no
    gaps; degenerates to the historical fixed-index strip when both loops
    share a vertex count and are already angle-ordered.

    Returns ``(sorted_inner_pts, sorted_outer_pts, faces)`` — ``faces``
    indexes into ``np.vstack([sorted_inner_pts, sorted_outer_pts])``."""
    io = np.argsort(inner_theta)
    oo = np.argsort(outer_theta)
    it = inner_theta[io]
    ot = outer_theta[oo]
    ip = inner_pts[io]
    op = outer_pts[oo]
    m, n = len(it), len(ot)
    off = m
    it_ext = np.concatenate([it, [it[0] + 2.0 * np.pi]])
    ot_ext = np.concatenate([ot, [ot[0] + 2.0 * np.pi]])
    faces = []
    ai = bi = 0
    ca = cb = 0
    while ca < m or cb < n:
        a_next, b_next = ai + 1, bi + 1
        if ca >= m:
            step_outer = True
        elif cb >= n:
            step_outer = False
        else:
            step_outer = ot_ext[b_next] < it_ext[a_next]
        if step_outer:
            faces.append([ai % m, off + (bi % n), off + (b_next % n)])
            bi, cb = b_next, cb + 1
        else:
            faces.append([ai % m, off + (bi % n), a_next % m])
            ai, ca = a_next, ca + 1
    return ip, op, np.asarray(faces, int)


def _zip_open_strip(inner_pts: np.ndarray, inner_phi: np.ndarray,
                    outer_pts: np.ndarray, outer_phi: np.ndarray
                    ) -> "Tuple[np.ndarray, np.ndarray, np.ndarray]":
    """``_zip_loop_bridge``'s OPEN-ARC sibling (goal-3 S1, the crescent):
    triangulates a strip between two arcs sorted on a common REBASED
    bearing (``phi`` — the caller measures both from the crescent window's
    own start, so neither side wraps), using only their own real points.
    The same cumulative walk, minus the wrap machinery: no extension
    entry, no modulo, and the walk stops at both sequences' last points —
    the strip is OPEN at both ends, which is the point: a crescent's ends
    are where the moat tapers shut and the scan already meets the mouth;
    a closed zip would sweep a chord wall across that flush side.
    Exactly ``(m - 1) + (n - 1)`` triangles."""
    io = np.argsort(inner_phi)
    oo = np.argsort(outer_phi)
    ip = inner_pts[io]
    op = outer_pts[oo]
    it = inner_phi[io]
    ot = outer_phi[oo]
    m, n = len(it), len(ot)
    off = m
    faces = []
    ai = bi = 0
    while ai < m - 1 or bi < n - 1:
        if ai >= m - 1:
            step_outer = True
        elif bi >= n - 1:
            step_outer = False
        else:
            step_outer = ot[bi + 1] < it[ai + 1]
        if step_outer:
            faces.append([ai, off + bi, off + bi + 1])
            bi += 1
        else:
            faces.append([ai, off + bi, ai + 1])
            ai += 1
    return ip, op, np.asarray(faces, int)


def cull_floating_fragments(mesh: trimesh.Trimesh,
                            site_poses: "Sequence[Tuple[np.ndarray, float]]",
                            protect: "Optional[np.ndarray]" = None,
                            style: str = "site"
                            ) -> "Tuple[trimesh.Trimesh, List[str]]":
    """HARD INVARIANT 2 (client, plan 2026-08-16: "cannot things floating
    in the air"): no deliverable ships a disconnected fragment. Keeps the
    arch-connected body — the LARGEST face-connected component — and culls
    every island, with a counted note per site (an island whose centroid
    sits inside a site's disc — the site's own radial reach plus the
    probe's 3mm moat margin — is that site's debris; anything else is
    "away from any site"). Generalizes ``isolation.orphan_flap_mask`` from
    its site-cylinder scope to the WHOLE artifact, as the builders' last
    step: the flap guard needs a site to name, this rule needs none.

    ``site_poses`` is ``[(pose_matrix, rim_r), ...]`` — the same pairs the
    builders already carry. Attribution only; the cull itself is global.

    ``protect`` (optional bool face mask): a component carrying ANY
    protected face survives — the fused composites protect their parts'
    own material, because an excision moat can ring the aligned cap
    COMPLETELY (the cap is then a disjoint body, and the whole point of
    the artifact) and a relief-hovering construction never touches its
    socket at all. ``style`` picks the note's prefix idiom: ``"site"``
    emits ``"site N: …"`` (the carve/floored-holes routing), ``"part"``
    emits ``"part N sheds …"`` (the fused-composite routing, whose parser
    reads the bare index word)."""
    if len(mesh.faces) == 0:
        return mesh, []
    comps = trimesh.graph.connected_components(
        mesh.face_adjacency, min_len=0, nodes=np.arange(len(mesh.faces)))
    if len(comps) <= 1:
        return mesh, []
    comps = sorted(comps, key=len, reverse=True)
    centers = np.asarray(mesh.triangles_center, float)
    per_site: "dict" = {}
    away = 0
    protected: list = [comps[0]]
    culled: list = []
    for comp in comps[1:]:
        if protect is not None and bool(np.asarray(protect)[comp].any()):
            protected.append(comp)
            continue
        culled.append(comp)
    if not culled:
        return mesh, []
    for comp in culled:
        c = centers[comp].mean(axis=0)
        landed = None
        for index, (pose, rim_r) in enumerate(site_poses, 1):
            pose = np.asarray(pose, float)
            origin = pose[:3, 3]
            axis = pose[:3, :3] @ np.array([0.0, 0.0, 1.0])
            rel = c - origin
            radial = float(np.linalg.norm(rel - (rel @ axis) * axis))
            if radial < float(rim_r) + 3.0:
                landed = index
                break
        if landed is None:
            away += 1
        else:
            per_site[landed] = per_site.get(landed, 0) + 1
    keep = np.zeros(len(mesh.faces), bool)
    for comp in protected:
        keep[comp] = True
    out = trimesh.Trimesh(np.asarray(mesh.vertices, float).copy(),
                          np.asarray(mesh.faces)[keep].copy(),
                          process=False)
    out.remove_unreferenced_vertices()
    if style == "part":
        notes = [
            f"part {index} sheds {count} floating fragment"
            f"{'s' if count > 1 else ''} — nothing ships in the air"
            for index, count in sorted(per_site.items())]
    else:
        notes = [
            f"site {index}: {count} floating fragment"
            f"{'s' if count > 1 else ''} removed — nothing ships in the air"
            for index, count in sorted(per_site.items())]
    if away:
        notes.append(
            f"{away} floating fragment{'s' if away > 1 else ''} away from "
            f"any site removed — nothing ships in the air")
    return out, notes


def _shed_nonmanifold_strip_faces(mesh: trimesh.Trimesh,
                                  n_base_faces: int) -> trimesh.Trimesh:
    """THE WELD'S MANIFOLD GUARD (the bowtie regression, 2026-08-17): the
    vote's strip zips a MIXED population — round banks plus shard-fragment
    boundary points — and wherever two theta-consecutive strip vertices
    are not adjacent on their source loop, the weld can mint an edge that
    ALREADY has two faces: a non-manifold (3+ face) edge the solidify
    walker downstream cannot wrap (measured on 276794487's carve: 9
    non-manifold input edges left the solidified shell with 4 bad edges
    and the fused composite falling back). The strip's job is covering
    the moat, never corrupting the manifold: per pass, ``fix_winding``
    first propagates the base's own orientation into the strips (the
    whole-strip mean-normal flip cannot guarantee per-edge agreement),
    then any face AT OR PAST ``n_base_faces`` (the strips — concatenated
    after the base) standing on a ≥3-face edge OR on a SAME-DIRECTION
    duplicated edge (an orientation frustration the propagation could not
    resolve — flipping the face fixes one edge and breaks another;
    measured: 3 such pairs left the solidified shell watertight, volume
    11249, yet ``is_volume`` False, and the union refused it as "not a
    volume") is shed, iterating until clean. Open (1-face) edges are left
    alone — the walker handles those by design, exactly as it handles the
    arch's own rim."""
    for _ in range(4):
        trimesh.repair.fix_winding(mesh)
        edges = mesh.edges_sorted
        unique, inverse = trimesh.grouping.unique_rows(edges)
        counts = np.bincount(inverse)
        bad_edge = np.zeros(len(unique), bool)
        bad_edge[counts >= 3] = True
        face_bad = bad_edge[inverse].reshape(-1, 3).any(axis=1)
        directed = mesh.edges
        key = (directed[:, 0].astype(np.int64) * len(mesh.vertices)
               + directed[:, 1])
        order = np.argsort(key, kind="stable")
        sk = key[order]
        dup = np.zeros(len(key), bool)
        same_prev = np.concatenate([[False], sk[1:] == sk[:-1]])
        same_next = np.concatenate([sk[:-1] == sk[1:], [False]])
        dup[order] = same_prev | same_next
        face_bad |= dup.reshape(-1, 3).any(axis=1)
        face_bad[:n_base_faces] = False
        if not face_bad.any():
            break
        keep = ~face_bad
        mesh = trimesh.Trimesh(
            np.asarray(mesh.vertices, float).copy(),
            np.asarray(mesh.faces)[keep].copy(), process=False)
        n_base_faces = min(n_base_faces, len(mesh.faces))
    return mesh


def _longest_circular_run(mask: np.ndarray) -> "Tuple[int, int]":
    """``(length, start)`` of the longest circular run of True bins."""
    n = len(mask)
    if not mask.any():
        return 0, 0
    if mask.all():
        return n, 0
    ext = np.concatenate([mask, mask])
    best_len = best_start = cur = 0
    for i, v in enumerate(ext):
        if v:
            cur += 1
            if cur > best_len:
                best_len, best_start = cur, i - cur + 1
        else:
            cur = 0
    return min(best_len, n), best_start % n


def _loop_overlap_fraction(a: np.ndarray, b: np.ndarray,
                           tol_mm: float = 1e-4) -> float:
    """The fraction of ``a``'s own points that land within ``tol_mm`` of
    SOME point of ``b`` — used to tell ``out``'s own duplicate of the
    machined mouth (the shared cut edge every DEFECT-1 consumer's out/
    socket split leaves standing on BOTH sides, bit-identical, because both
    pieces are built from the very same source vertex array and neither
    ever moves a surviving coordinate) apart from a genuine second ring.
    ``1.0`` when every point of ``a`` matches; ``0.0`` when none do."""
    from scipy.spatial import cKDTree

    if len(a) == 0:
        return 0.0
    dist, _ = cKDTree(b).query(a)
    return float(np.mean(np.asarray(dist) < tol_mm))


def _vote_banks(out_boundary_loops: "Sequence[np.ndarray]",
                origin: np.ndarray, axis: np.ndarray, xl: np.ndarray,
                yl: np.ndarray, r_lo: float, r_hi: float, a_mid: float,
                exclude_pts: "Optional[np.ndarray]" = None
                ) -> "Tuple[list, int]":
    """THE CLOUD VOTE's bank formation (goal-3 S1, factored for S2's drape:
    the collar bridge and the fused-composite drape read the SAME scan-edge
    physics, so they share one vote). Pools every out-boundary vertex in
    the radial window and z-band, splits the pool into radial BANKS at
    gaps, and gates each bank by votes, radial MAD and bearing structure —
    the "RANSAC ring" made deterministic (the axis is known; no sampling,
    nothing to seed).

    NEAR-duplicate exclusion (``exclude_pts`` — the bridge passes its
    mouth), judged PER LOOP, not per point — measured: a narrow moat's
    out-boundary is ONE mixed ring whose flush stretch grazes the mouth at
    0.03mm while its median sits 0.35mm away; excluding its near points
    tore the weld into 7 crack fragments. A loop is the reference ring's
    own flush counterpart only when it hugs it WHOLESALE (median distance
    < ``_BANK_DUP_TOL_MM``); a mixed loop votes in full.

    FULL RING or CRESCENT (probe on 295811960's live carve: the real moat
    is one contiguous 82° crescent — the client's screenshots always
    showed the white on ONE side; a full-ring coverage gate refused it):
    the longest run of EMPTY bearings decides — sampling-scale gaps mean a
    full ring; one large gap leaves a WINDOW that must be wide enough
    (``_BANK_ARC_BINS_MIN``) and solidly filled
    (``_BANK_WINDOW_FILL_MIN``) to be one real crescent; anything else is
    fragmentary. Each bank keeps ALL its real points, ordered by bearing
    from its window's own start — thinning was tried and broke the weld
    (a strip through selected points leaves every unselected boundary
    vertex on a crack: measured 7 residual loops on the end-to-end pin).

    Returns ``(banks, fragmentary)`` — banks as ``(median_r, points,
    window)`` with ``window`` ``None`` for a full ring or ``(theta_start,
    theta_end)`` for a crescent; ``fragmentary`` counts refused points."""
    from scipy.spatial import cKDTree as _KD
    exclude_tree = (_KD(np.asarray(exclude_pts, float))
                    if exclude_pts is not None and len(exclude_pts)
                    else None)
    pool: list = []
    for loop in out_boundary_loops:
        pts = np.asarray(loop, float)
        if len(pts) == 0:
            continue
        if exclude_tree is not None:
            d_ref, _ = exclude_tree.query(pts)
            if float(np.median(d_ref)) < _BANK_DUP_TOL_MM:
                continue
        pool.extend(pts)
    banks: list = []
    fragmentary = 0
    if not pool:
        return banks, fragmentary
    P = np.asarray(pool, float)
    rel = P - origin
    r = np.hypot(rel @ xl, rel @ yl)
    a = rel @ axis
    keep_pts = ((r > r_lo) & (r < r_hi)
                & (np.abs(a - a_mid) < _BRIDGE_Z_BAND_MM))
    P, r = P[keep_pts], r[keep_pts]
    if not len(P):
        return banks, fragmentary
    order = np.argsort(r)
    P, r = P[order], r[order]
    splits = np.flatnonzero(np.diff(r) > _BANK_GAP_MM) + 1
    for cluster in np.split(np.arange(len(P)), splits):
        if len(cluster) < _MOUTH_MIN_VERTICES:
            continue
        cp = P[cluster]
        cr = r[cluster]
        med = float(np.median(cr))
        if float(np.median(np.abs(cr - med))) > _BRIDGE_ROUNDNESS_MM:
            continue
        theta = np.arctan2((cp - origin) @ yl, (cp - origin) @ xl)
        bins = ((theta + np.pi) / (2 * np.pi)
                * _BANK_THETA_BINS).astype(int) % _BANK_THETA_BINS
        occ = np.zeros(_BANK_THETA_BINS, dtype=bool)
        occ[bins] = True
        gap_len, gap_start = _longest_circular_run(~occ)
        if gap_len <= _BANK_FULL_GAP_BINS:
            window = None
            keep = np.arange(len(cp))
        else:
            w_start = (gap_start + gap_len) % _BANK_THETA_BINS
            w_len = _BANK_THETA_BINS - gap_len
            if w_len < _BANK_ARC_BINS_MIN:
                fragmentary += len(cluster)
                continue
            in_window = (bins - w_start) % _BANK_THETA_BINS < w_len
            fill = len(np.unique(bins[in_window])) / w_len
            if fill < _BANK_WINDOW_FILL_MIN:
                fragmentary += len(cluster)
                continue
            step = 2.0 * np.pi / _BANK_THETA_BINS
            t0 = -np.pi + w_start * step
            window = (t0, t0 + w_len * step)
            keep = np.flatnonzero(in_window)
        base = window[0] if window is not None else -np.pi
        phi = (theta[keep] - base) % (2.0 * np.pi)
        banks.append((med, cp[keep][np.argsort(phi)], window))
    if not banks and len(P) >= _MOUTH_MIN_VERTICES:
        # NOTHING bridged while a SUBSTANTIAL scan edge stands in the
        # window: every windowed point joins the disclosure's count.
        # Sub-minimum radial shards were previously dropped in silence,
        # and a silent degradation ships as a mystery — the fleet gate's
        # own finding (zimmer-4.5 / cap6020 fused, 2026-08-17): their
        # capless twins disclosed "too fragmentary" and were exempt
        # while the fused composites failed mute on the same edge. A
        # sub-substantial pool (an irregular cut edge's handful of
        # points) stays silent — it is not a scan edge at all.
        fragmentary = len(P)
    return banks, fragmentary


def _zip_chain(chain: "Sequence[Tuple[np.ndarray, Optional[Tuple[float, float]]]]",
               origin: np.ndarray, axis: np.ndarray, xl: np.ndarray,
               yl: np.ndarray) -> list:
    """THE TRIANGULATION reuses the envelope-era collar's own idiom (see
    ``_zip_loop_bridge``'s docstring) — an inner-to-outer strip per
    consecutive pair of the chain — joining each pair's OWN REAL points
    (never an interpolated one), which is what lets the caller WELD the
    strips onto its own pre-existing loops by an exact-coordinate vertex
    merge. A CRESCENT element (a ``(theta_start, theta_end)`` window) zips
    an OPEN strip instead, over its own bearing window only — the other
    side of the pair is clipped to that window (the flush side, where the
    scan already meets the ring, is never touched)."""
    strips: list = []
    for (inner_lp, inner_w), (outer_lp, outer_w) in zip(chain[:-1],
                                                        chain[1:]):
        inner_theta = np.arctan2((inner_lp - origin) @ yl,
                                 (inner_lp - origin) @ xl)
        outer_theta = np.arctan2((outer_lp - origin) @ yl,
                                 (outer_lp - origin) @ xl)
        if inner_w is None and outer_w is None:
            inner_sorted, outer_sorted, faces = _zip_loop_bridge(
                inner_lp, inner_theta, outer_lp, outer_theta)
        else:
            w = inner_w if outer_w is None else outer_w
            span = w[1] - w[0]
            inner_phi = (inner_theta - w[0]) % (2.0 * np.pi)
            outer_phi = (outer_theta - w[0]) % (2.0 * np.pi)
            ki = inner_phi <= span + 1e-9
            ko = outer_phi <= span + 1e-9
            if int(ki.sum()) < 2 or int(ko.sum()) < 2:
                continue
            inner_sorted, outer_sorted, faces = _zip_open_strip(
                inner_lp[ki], inner_phi[ki], outer_lp[ko], outer_phi[ko])
        verts = np.vstack([inner_sorted, outer_sorted])
        strip = trimesh.Trimesh(verts, faces, process=False)
        if float(np.asarray(strip.face_normals, float).mean(axis=0)
                 @ axis) < 0:
            strip = trimesh.Trimesh(verts, faces[:, ::-1], process=False)
        strips.append(strip)
    return strips


def _drape_scan_edge_to_cap_wall(out: trimesh.Trimesh,
                                 part_faces: np.ndarray,
                                 pose: np.ndarray,
                                 rim_r: float
                                 ) -> "Optional[trimesh.Trimesh]":
    """THE FUSED-COMPOSITE DRAPE (goal-3 S2, plan 2026-08-16): tab 1's
    white annulus. The full-footprint excision rings the aligned cap with
    a gap where the scanned crust died — the scan's edge must drape onto
    the cap's own wall. The OUTER side is slice 1's vote over ``out``'s
    boundary loops (the scan's edge, fragments and crescents included);
    the INNER side is built from the composite's own PART-provenance
    vertices — one real vertex per occupied bearing bin, HEIGHT-MATCHED to
    the bank's own height at that bearing (never planar: the gum line
    climbs and falls around a cap). Both sides being ``out``'s own real
    points, the caller's ``merge_vertices()`` welds the strip on for real.

    ``part_faces`` is a boolean mask over ``out.faces`` naming this site's
    own part-provenance faces (the tracked union's ``source`` read,
    carried through the strip's ``keep``). Returns ``(strip,
    undraped_count)``: the strip (or ``None``), plus the number of
    windowed scan-edge points the drape could NOT close — the caller's
    disclosure count, mirroring the collar bridge's own fragmentary note
    (the fleet gate's finding, 2026-08-17: the fused composites failed
    MUTE on the same shattered edges their capless twins disclosed).
    ``(None, 0)`` is genuine flush — nothing to drape, nothing to say."""
    pose = np.asarray(pose, float)
    origin = pose[:3, 3]
    R = pose[:3, :3]
    axis = R @ np.array([0.0, 0.0, 1.0])
    xl = R @ np.array([1.0, 0.0, 0.0])
    yl = R @ np.array([0.0, 1.0, 0.0])

    V = np.asarray(out.vertices, float)
    pv_idx = np.unique(np.asarray(out.faces)[part_faces].ravel())
    if len(pv_idx) == 0:
        return None, 0
    banks, fragmentary = _vote_banks(
        _boundary_loops_of(out), origin, axis, xl, yl,
        # the scan's edge starts AT the excision cylinder (whole faces die,
        # so surviving edge vertices sit up to a face's span inside the
        # rim) and the vote reaches the moat's own scale past it
        r_lo=float(rim_r) - 0.75, r_hi=float(rim_r) + _BANK_SEARCH_MM,
        a_mid=0.0,
        # the part's OWN boundary never votes (the bridge's mouth-dup rule,
        # re-learned here 2026-08-17: the solidified scan's closure makes
        # the union cut an intersection ring ON the part — a boundary loop
        # of part-owned vertices the vote read as a "bank", and zipping
        # onto part-adjacent vertex pairs minted the frustration edges the
        # manifold guard then had to amputate)
        exclude_pts=V[pv_idx])
    if not banks:
        return None, fragmentary
    # PER-POINT part hygiene, drape-only (the carve's weld NEEDS every
    # mixed-loop point; the drape does not): a mixed loop votes in full,
    # so a few union-seam vertices — ON the part — can still reach a
    # bank, and zipping onto part-adjacent pairs mints frustration edges
    # (measured: 4 non-manifold + 8 misdirected on the annulus fixture).
    # Where the scan touches the part it is already flush; those points
    # simply drop.
    from scipy.spatial import cKDTree as _KD
    part_tree = _KD(V[pv_idx])
    cleaned = []
    for med, ring, window in banks:
        d_part, _ = part_tree.query(ring)
        keep_ring = ring[d_part >= _BANK_DUP_TOL_MM]
        if len(keep_ring) >= 2:
            cleaned.append((med, keep_ring, window))
    banks = cleaned
    if not banks:
        return None, fragmentary
    banks.sort(key=lambda t: t[0])
    med0, bank_pts, window0 = banks[0]
    bank_total = sum(len(ring) for _m, ring, _w in banks)

    pv = V[pv_idx]
    rel = pv - origin
    pa = rel @ axis
    pr = np.hypot(rel @ xl, rel @ yl)
    zone = ((pr > float(rim_r) - 1.5) & (pr < med0 + 0.1)
            & (np.abs(pa) < _BRIDGE_Z_BAND_MM + 1.5))
    if not zone.any():
        return None, bank_total
    pv, pa = pv[zone], pa[zone]
    p_theta = np.arctan2((pv - origin) @ yl, (pv - origin) @ xl)
    p_bins = ((p_theta + np.pi) / (2 * np.pi)
              * _BANK_THETA_BINS).astype(int) % _BANK_THETA_BINS

    b_rel = bank_pts - origin
    b_a = b_rel @ axis
    b_theta = np.arctan2(b_rel @ yl, b_rel @ xl)
    b_bins = ((b_theta + np.pi) / (2 * np.pi)
              * _BANK_THETA_BINS).astype(int) % _BANK_THETA_BINS

    base = window0[0] if window0 is not None else -np.pi
    inner: list = []
    for bin_id in np.unique(b_bins):
        cand = np.flatnonzero(p_bins == bin_id)
        if len(cand) == 0:
            continue
        h_bin = float(np.median(b_a[b_bins == bin_id]))
        inner.append(pv[cand[np.argmin(np.abs(pa[cand] - h_bin))]])
    if len(inner) < 2:
        return None, bank_total
    inner_pts = np.asarray(inner, float)
    # THE PART SIDE OVERLAPS, NEVER WELDS (the bowtie regression's
    # deepest lesson, 2026-08-17): the part is a CLOSED solid, so its
    # surface edges already carry two faces — a strip edge welded onto
    # one is born non-manifold, and the manifold guard then amputates the
    # strip's whole inner side (measured on the annulus fixture: the
    # crack ring it left alternated wall and sheet radii). A hair of
    # radial inset keeps every inner vertex coordinate-distinct: the seam
    # is visually sealed, topologically its own open edge — exactly what
    # the solidify walker handles by design.
    i_rel = inner_pts - origin
    i_ax = i_rel @ axis
    i_rad = i_rel - np.outer(i_ax, axis)
    i_len = np.linalg.norm(i_rad, axis=1)
    safe = i_len > 1e-9
    inner_pts = inner_pts.copy()
    inner_pts[safe] -= (i_rad[safe] / i_len[safe, None]) * 0.02
    i_theta = np.arctan2((inner_pts - origin) @ yl,
                         (inner_pts - origin) @ xl)
    i_phi = (i_theta - base) % (2.0 * np.pi)
    inner_pts = inner_pts[np.argsort(i_phi)]

    chain = [(inner_pts, window0)] + [
        (ring, w) for _med, ring, w in banks]
    strips = _zip_chain(chain, origin, axis, xl, yl)
    if not strips:
        return None, bank_total
    return (strips[0] if len(strips) == 1
            else trimesh.util.concatenate(strips)), 0


def _bridge_recess_collar(out_boundary_loops: "Sequence[np.ndarray]",
                          Vc: np.ndarray, socket_faces: np.ndarray,
                          pose: np.ndarray, rim_r: float
                          ) -> "Tuple[Optional[trimesh.Trimesh], Optional[str]]":
    """DEFECT B — THE GAP RING (client-ruled, live verification 2026-08-15,
    on the STANDING PRECEDENT of the envelope-era moat bridge: the collar
    annulus ``cap_imprint_parts`` carried from §10-AO's original build
    through §10-AS.7 "the collar drapes onto the gum" — git history
    ``35c888a``, retired only when §10-AS.10's press carve replaced the
    whole liner architecture with one seamless pressed shell, and the true
    CSG carve after it cuts a real machined wall with nothing bridging its
    mouth back to the scan). A healing cap's flange overhangs the gum
    beneath it, and a scanner can never see what its own shadow hides —
    the excision (dropping the scanned cap's own crust up to the machined
    mouth) exposes that blind ring for what it always was: tissue that was
    never captured, not tissue the cut failed to reach. TONIGHT'S RULING:
    bridge it, fabricated-and-noted, never left standing open as a moat on
    a print — the same precedent, applied to the carve that replaced the
    liner which used to bridge it.

    ``out_boundary_loops`` is the ARCH layer's own boundary loops, computed
    ONCE by the caller over the whole carved arch before any site's bridge
    has landed (every site reads the identical pre-bridge boundary — nether
    an earlier site's own new bridge faces nor a later site's absence can
    move what an earlier one sees). ``socket_faces`` is THIS site's own
    tool-provenance faces alone (never another site's, never the untouched
    scan) — a boolean-cut recess is a simple cup, open only where the punch
    met the surface it removed, so its own boundary is the MACHINED MOUTH
    exactly, with no radial search needed to find it.

    Extraction is two loops, each required to stand alone. The MOUTH is the
    socket submesh's OUTERMOST substantial round boundary loop (the
    2026-08-16 measured rule — a real coded cap's tool surface carries
    dozens of boundary loops, but the punch is a revolute whose widest cut
    rings the mouth; a radius near-tie between two round loops is a genuine
    junction and skips with the count). The SCAN'S OPENING BOUNDARY is,
    among ``out_boundary_loops``,
    the one loop whose every point sits radially beyond the mouth's own
    farthest point (excluding the mouth's own duplicate — ``out`` always
    carries one too, at the shared cut edge, and it fails this test because
    most of ITS points sit at or under the mouth's own max radius), within
    ``_BRIDGE_Z_BAND_MM`` of the mouth's own height, AND itself "roughly
    concentric" about the SAME axis (``_BRIDGE_ROUNDNESS_MM`` — radial std
    past this is not a ring, it is some unrelated cut edge that merely
    passed the other two gates; see the constant's own comment for the
    measured case this rules out: a thin fixture's FAR side, punched clean
    through, sits close enough in height and radius to read as a second
    candidate without this test). Zero qualifying loops means the excision
    left nothing proud of the mouth at all — no gap, nothing to bridge, no
    note (an honest "already flush", never a failure). More than one is
    ambiguous, and skipped with a note naming the count — "never a mangled
    ring" is the client's own words for the alternative.

    THE TRIANGULATION reuses the envelope-era collar's own idiom (see
    ``_zip_loop_bridge``'s docstring) — an inner-to-outer strip — over the
    two loops' own REAL points, never an interpolated one: both the mouth
    (read off ``socket_faces``) and the scan's own opening boundary (read
    off ``out_boundary_loops``) contribute their actual vertex values, so
    the caller's ``merge_vertices()`` after concatenation welds the bridge
    onto BOTH — the moat closes for real, and the mouth vertices the
    bridge and ``out``'s own kept scan share become one shared loop rather
    than two coincident ones standing apart.

    Returns ``(bridge_mesh, note)``. A built bridge always carries its own
    note (the client's required sentence, verbatim); ``(None, None)`` means
    genuinely nothing to bridge; ``(None, "why")`` is the fail-open path."""
    if len(socket_faces) == 0:
        return None, ("the recess has no machined surface at this site — "
                      "the collar bridge was skipped")
    socket_mesh = trimesh.Trimesh(Vc, socket_faces, process=False)
    mouth_loops = _boundary_loops_of(socket_mesh)
    if len(mouth_loops) == 0:
        return None, ("the machined mouth has no boundary at this site — "
                      "the collar bridge was skipped")

    pose = np.asarray(pose, float)
    origin = pose[:3, 3]
    R = pose[:3, :3]
    axis = R @ np.array([0.0, 0.0, 1.0])
    xl = R @ np.array([1.0, 0.0, 0.0])
    yl = R @ np.array([0.0, 1.0, 0.0])

    def _radial_axial(pts: np.ndarray) -> "Tuple[np.ndarray, np.ndarray]":
        rel = pts - origin
        return np.hypot(rel @ xl, rel @ yl), rel @ axis

    # THE OUTERMOST-ROUND MOUTH RULE (the exactly-one rule's measured
    # replacement, 2026-08-16 — the loop census that the delivered rule's
    # own KNOWN LIMITATION comment queued as probe-first follow-up): a real
    # coded cap's tool surface carries dozens of boundary loops (26-37 was
    # the integration measurement; 276794487's own run showed the same),
    # but the machined MOUTH is BY CONSTRUCTION the outermost of them — the
    # punch is a revolute whose widest cut rings the mouth (measured: mouth
    # r 2.9-3.1 vs <= 2.2 for every trench/floor edge). The mouth is the
    # SUBSTANTIAL, ROUND loop with the largest mean radius; two round loops
    # in a radius near-tie is a genuine junction, skipped with the count —
    # "never a mangled ring" stands.
    candidates = []
    for lp in mouth_loops:
        if len(lp) < _MOUTH_MIN_VERTICES:
            continue
        r, a = _radial_axial(lp)
        if float(r.std()) > _MOUTH_ROUNDNESS_MM:
            continue
        candidates.append((float(r.mean()), float(a.mean()), lp))
    if not candidates:
        return None, (
            f"no round machined mouth stands among the {len(mouth_loops)} "
            f"boundary loops at this site — the collar bridge was skipped")
    candidates.sort(key=lambda t: -t[0])
    top_r = candidates[0][0]
    rivals = [c for c in candidates if top_r - c[0] < _MOUTH_TIE_MM]
    if len(rivals) > 1:
        # STACKED WALL EDGES AT ONE RADIUS: a deep or interrupted socket's
        # wall leaves several round rings at the same radius (floor edge,
        # wall top, disjoint wall fragments). The MOUTH is where the
        # machined surface meets the outside world — the most OCCLUSAL of
        # them, whatever the fragments' connectivity. The only genuine
        # ambiguity left is two round rings at one radius AND one height —
        # nothing physical to choose between — and that skips, "never a
        # mangled ring".
        rivals.sort(key=lambda t: -t[1])
        # 0.15mm: a real wall always has height (the shallowest measured
        # fixture wall is 0.38mm); only a degenerate sliver has none
        if rivals[0][1] - rivals[1][1] < 0.15:
            return None, (
                f"{len(rivals)} rival round mouths sit within "
                f"{_MOUTH_TIE_MM:.1f}mm of one radius at one height — the "
                f"collar bridge was skipped")
        mouth = rivals[0][2]
    else:
        mouth = candidates[0][2]

    mouth_r, mouth_a = _radial_axial(mouth)
    mouth_r_mean = float(mouth_r.mean())
    mouth_r_max = float(mouth_r.max())
    mouth_a_mid = float(mouth_a.mean())

    # THE CLOUD VOTE (plan goal-3 S1; the slice-0 census on 295811960's own
    # carve, 2026-08-16): the erase ruling leaves the scan's edge as
    # FRAGMENTS, and a per-loop test starves — while the fragments' own
    # vertices still agree on one radius. Worse, the delivered radius
    # window compared every point against the mouth's own MAX radius, and a
    # WAVY mouth (measured: mean 2.94, max 3.35) put its max above the real
    # bank's points (r 2.98±0.24 — z-band and roundness both passed) — the
    # sole measured killer of the silent bridge. So: pool EVERY out-boundary
    # vertex in the z-band beyond the mouth's MEAN radius (minus the
    # mouth's own duplicate, by exact point identity), split the pool into
    # radial BANKS at gaps, and gate each bank by votes, angular coverage
    # and radial MAD — the "RANSAC ring" made deterministic (the axis is
    # known; no sampling, nothing to seed).
    banks, fragmentary = _vote_banks(
        out_boundary_loops, origin, axis, xl, yl,
        r_lo=mouth_r_mean - 0.1, r_hi=mouth_r_max + _BANK_SEARCH_MM,
        a_mid=mouth_a_mid, exclude_pts=np.asarray(mouth, float))
    if not banks:
        if fragmentary:
            return None, (
                f"the scan's edge near the mouth is too fragmentary to "
                f"bridge ({fragmentary} boundary points in scattered arcs) "
                f"— the collar bridge was skipped")
        return None, None
    banks.sort(key=lambda t: t[0])
    chain = [(np.asarray(mouth, float), None)] + [
        (ring, window) for _med, ring, window in banks]

    strips = _zip_chain(chain, origin, axis, xl, yl)
    if not strips:
        return None, None
    bridge = (strips[0] if len(strips) == 1
              else trimesh.util.concatenate(strips))
    note = ("the collar between the recess mouth and the scan's edge is "
           "bridged — the tissue there sat under the cap and was never "
           "scanned")
    return bridge, note


def _lid_planar_holes(mesh: trimesh.Trimesh, origin: np.ndarray,
                      axis: np.ndarray, floor_a: float, r_ref: float
                      ) -> "Tuple[list, int]":
    """FAN LIDS FOR FLOOR-HEIGHT OPENINGS (client live, 2026-08-16): every
    boundary loop of ``mesh`` that sits AT the site's floor plane
    (``_FLOOR_LID_BAND_MM``) and INSIDE the hole's own footprint
    (mean radius under ``0.8 * r_ref`` — the mouth ring itself lives at the
    silhouette radius and must never be sealed, flush cap or not) is closed
    with a centroid fan wound to face occlusally. The lids reuse the loop's
    own real vertex values, so the caller's ``merge_vertices()`` welds them
    on for real. Returns ``(lid_meshes, count)``."""
    lids: list = []
    for lp in _boundary_loops_of(mesh):
        if len(lp) < _FLOOR_LID_MIN_VERTICES:
            continue
        rel = np.asarray(lp, float) - origin
        a = rel @ axis
        r = np.linalg.norm(rel - np.outer(a, axis), axis=1)
        if float(np.abs(a - floor_a).max()) > _FLOOR_LID_BAND_MM:
            continue
        if float(r.mean()) > 0.8 * r_ref:
            continue
        if float(r.std()) > 0.5:
            # a real pocket breach is roughly round (measured 0.30 on
            # 276794487's own loop); a flush-coplanar cut's stitching junk
            # is star-shaped (measured 0.73) and is not a floor gap
            continue
        pts = np.asarray(lp, float)
        centroid = pts.mean(axis=0)
        verts = np.vstack([pts, centroid[None, :]])
        n = len(pts)
        faces = np.asarray([[i, (i + 1) % n, n] for i in range(n)], int)
        lid = trimesh.Trimesh(verts, faces, process=False)
        if float(np.asarray(lid.face_normals, float).mean(axis=0) @ axis) < 0:
            lid = trimesh.Trimesh(verts, faces[:, ::-1], process=False)
        lids.append(lid)
    return lids, len(lids)


def _gingival_floor_a(V: np.ndarray, solid: trimesh.Trimesh, index: int,
                      origin: np.ndarray, axis: np.ndarray, xl: np.ndarray,
                      yl: np.ndarray, zs_p: np.ndarray, prof_p: np.ndarray,
                      depth_mm: Optional[float]) -> Tuple[float, float]:
    """THE GUM-FOLLOWING FLOOR (§10-AS.10's own ring-read heuristic, factored
    here so every recess this module cuts — the dish, the platform
    countersink, and the fourth artifact-6 ruling's gingival floor — shares
    ONE measurement rather than three copies of it): the local gingival
    height about one site's pose axis, read off the SOLIDIFIED shell's own
    vertices (``V``, never the punch template's), and the floor's axial
    coordinate ``depth_mm`` below it.

    THE RING: the shell's own vertices just outside the cap's own footprint
    (``r_ref = max(prof_p)``, the widest the relief envelope ever reaches) —
    ``r_ref+0.1`` to ``r_ref+1.2`` radially, within 6mm of the site's own
    mid-height axially. The LOW quartile of that band's axial height is the
    read (``h_low``), not the median: a band that grazes a neighbouring
    crown reads mostly tooth, and the lowest surface in it is the gingiva
    (measured, cap6030: a median once read +3.2mm of "gum"). Fewer than 8
    vertices in the band is an honest refusal (``ValueError``, naming the
    site), never a floor guessed from nothing.

    THE CLAMP, when ``depth_mm`` is given: ``h_low - depth_mm`` is floored
    never below the envelope's own base (``zs_p[0]`` — a floor cannot sink
    past the cap's own exact bottom plus its relief), then probed against
    the SOLID itself — a downward ray at the footprint's centre plus four
    off-axis points at ``0.6 * r_ref`` finds the model's true material limit
    directly beneath this site (the same idiom the box fixture's own
    -0.5mm underside is measured through); a floor that would land past
    that limit is pulled up to 0.3mm above it, so a thin model never opens
    a hole where a floor was asked for. ``depth_mm is None`` means "no
    floor at all" — ``floor_a`` is the envelope's own base, unclamped.

    Returns ``(floor_a, h_low)`` — ``h_low`` is also the tint-region
    reference ``_csg_carve`` threads onward through ``regions``."""
    rel = V - origin
    a = rel @ axis
    r = np.hypot(rel @ xl, rel @ yl)
    r_ref = float(np.max(prof_p))
    band = (r > r_ref + 0.1) & (r < r_ref + 1.2) & (np.abs(a) < 6.0)
    if int(band.sum()) < 8:
        raise ValueError(f"no gum ring around site {index}")
    # the LOW quartile: a median once read a neighbouring crown as
    # +3.2mm of gum; the lowest surface in the ring is the gingiva
    h_low = float(np.percentile(a[band], 25))
    if depth_mm is None:
        return float(zs_p[0]), h_low
    floor_a = max(h_low - float(depth_mm), float(zs_p[0]))
    # the floor stays INSIDE the solid: on a thin model a punch that
    # reaches past the underside cuts a through-hole, not a seat.
    # A raw OPEN scan carries no "underside" of its own (it is one
    # surface, not a slab) — reading the footprint's raw vertices
    # for a "thin material" signal found only the SAME top surface
    # again and pushed the floor above the gum entirely on a real
    # single-sheet scan. The SOLIDIFIED shell (skirt + base) is the
    # honest source: a ray straight down the pose axis, probed at
    # the footprint's centre and a few off-axis points, finds the
    # model's true material limit directly beneath this site —
    # exactly the box fixture's own -0.5mm underside where one
    # genuinely exists, and the base plate far below on an open
    # single-sheet scan where none does.
    probes = [origin + axis * 100.0]
    if r_ref > 0:
        for ang in (0.0, np.pi / 2, np.pi, 3 * np.pi / 2):
            probes.append(origin + axis * 100.0
                          + (xl * np.cos(ang) + yl * np.sin(ang))
                          * (r_ref * 0.6))
    hits, *_ = solid.ray.intersects_location(
        ray_origins=probes, ray_directions=[-axis] * len(probes))
    if len(hits):
        base_a = float(((np.asarray(hits, float) - origin) @ axis).min())
        floor_a = max(floor_a, base_a + 0.3)
    return floor_a, h_low


def _csg_carve(arch: trimesh.Trimesh,
               sites: "Sequence[Tuple[trimesh.Trimesh, np.ndarray, float, float]]",
               visible_depth_mm: Optional[float],
               top_floor: bool
               ) -> Tuple[trimesh.Trimesh, Optional[trimesh.Trimesh], list]:
    solid = solidified_shell_cached(arch)
    V = np.asarray(arch.vertices, float)
    punches = []
    regions = []
    notes: list = []
    for index, (template, pose, offset_mm, rim_radius_mm) in enumerate(sites, 1):
        pose = np.asarray(pose, float)
        origin = pose[:3, 3]
        R = pose[:3, :3]
        axis = R @ np.array([0.0, 0.0, 1.0])
        xl = R @ np.array([1.0, 0.0, 0.0])
        yl = R @ np.array([0.0, 1.0, 0.0])
        try:
            # relief-only: the profile bounds the exact cap (max radius per
            # height) — it feeds the tint region test, the ring band and the
            # per-site FALLBACK tool. The deviation clearance is gone from
            # the cut (§10-AS.14: "we should not be inferring anything here")
            zs_p, prof_p = _envelope_profile(template, float(offset_mm))
            profile_ok = True
        except Exception as exc:  # noqa: BLE001 — cut on, honestly
            zs_p = np.array([-_HOLE_DEPTH_MM, _HOLE_DEPTH_MM])
            prof_p = np.full(2, rim_radius_mm + _REGION_MARGIN_MM)
            profile_ok = False
            notes.append(f"site {index}: the cap envelope could not be built "
                         f"({exc}) — a cylinder recess was cut at the rim "
                         f"radius instead")
        if top_floor:
            depth = max(float(offset_mm), _PLATFORM_COUNTERSINK_MIN_MM)
        elif visible_depth_mm is not None:
            depth = float(visible_depth_mm)
        else:
            depth = None
        floor_a, h_low = _gingival_floor_a(V, solid, index, origin, axis, xl,
                                           yl, zs_p, prof_p, depth)
        try:
            punches.append(exact_cap_punch(
                template, float(offset_mm), pose,
                floor_a if depth is not None else None))
        except Exception as exc:  # noqa: BLE001 — per-site honest fallback
            if profile_ok:  # a degenerate template already told its story
                notes.append(f"site {index}: the exact cap could not be cut "
                             f"({exc}) — its envelope was used instead")
            punches.append(punch_solid(zs_p, prof_p, floor_a, pose))
        # the tint's own floor: when the visible-floor clip on the exact cap
        # was a no-op (the cap's own top never reached the nominal target),
        # the punch actually reaches all the way to the cap's own base —
        # the SOCKET/OUT split must follow the punch it was actually given,
        # not the unmet nominal target, or the split misplaces the whole cut
        punch_a = (np.asarray(punches[-1].vertices, float) - origin) @ axis
        actual_floor_a = float(punch_a.min()) if len(punch_a) else floor_a
        regions.append((origin, axis, xl, yl, zs_p, prof_p, actual_floor_a,
                        h_low))
    # THE TRACKED CUT (boolean-engine plan W1, 2026-08-13): the shell is
    # tagged scan-vs-fabricated at the source (``fabricated_face_mask``,
    # exact by construction — solidify_shell's own append-only ordering)
    # and the difference runs through manifold3d's own provenance instead
    # of ``trimesh.boolean`` — so the strip below reads WHICH solid a face
    # came from rather than measuring how close it sits to anything.
    # Fail-open, never a dead package: any refusal here (a manifold3d
    # rejection the plain trimesh engine tolerated, an unwatertight tracked
    # result) falls back to the untracked engine + the distance strip, with
    # a note — the geometry falls back silently, the manifest never does.
    tracked_keep: Optional[np.ndarray] = None
    tool_provenance: Optional[np.ndarray] = None
    try:
        fabricated = fabricated_face_mask(arch, solid)
        tracked = default_kernel().difference_tracked(
            solid, punches, fabricated.astype(np.int64))
        cut = tracked.mesh
        if not cut.is_watertight:
            raise ValueError("the tracked boolean result is not watertight")
        tracked_keep = strip_tracked(tracked)
        # THE SOCKET IS FACE PROVENANCE (rider-b, fleet measurement 2026-08-14,
        # 36 carves/9 cases): every face whose material came from a PUNCH
        # operand (``source >= base_groups`` — a tool's own source is never
        # below the base's own group count, by ``difference_tracked``'s own
        # argument order) IS the socket, exactly, by construction — not a
        # revolute band (radius/height box) approximating where a punch
        # probably reached. The band was measured to mislabel 6.6-43.6% of
        # its socket as scan (a face near the recess that never came from any
        # punch) and to MISS 13.8-86.2% of the true machined surface on
        # deep-seated sites (the band's ``h_low + 3.0`` ceiling truncating a
        # wall that legitimately runs deeper); provenance carries neither
        # failure, because it reads what the boolean actually built rather
        # than re-deriving a guess about it from the site's own axis.
        tool_provenance = (np.asarray(tracked.source)
                           >= tracked.base_groups)
    except Exception as exc:  # noqa: BLE001 — fail-open to the untracked
        # engine and the distance strip
        cut = default_kernel().difference(solid, punches)
        if not cut.is_watertight:
            raise ValueError("the boolean result is not watertight")
        notes.append(f"the provenance-tracked strip could not run ({exc}) "
                     f"— the distance-based strip was used instead")
    if tool_provenance is not None:
        assert tracked_keep is not None  # set together, above, in the same try
        inside = tool_provenance
        keep = tracked_keep
        # THE STRUCTURAL GUARANTEE (rider-b): a tool's own source can never
        # equal the closure's (source 1, dropped by ``strip_tracked`` only
        # when the base was actually split) nor fall below ``base_groups``,
        # so ``inside`` is a subset of ``keep`` by the two functions' own
        # definitions, not by measurement — the fleet found it true 36/36
        # under the OLD band predicate too (empirically, not structurally);
        # this assertion is the cheap, permanent version of that finding for
        # the predicate that now REPLACES the band.
        assert not (inside & ~keep).any(), (
            "a tool-provenance face was dropped by the tracked strip — "
            "the socket must be a subset of keep by construction")
        # PER-SITE PROVENANCE (DEFECT B, the collar bridge below): each
        # punch was appended to ``punches`` in ``sites`` order, so
        # ``difference_tracked`` assigned it source ``base_groups + i`` —
        # exact, by the same argument-order fact ``tool_provenance`` itself
        # already rests on, never a re-derived guess.
        site_inside_masks = [
            np.asarray(tracked.source) == (tracked.base_groups + i)
            for i in range(len(sites))]
    else:
        # THE UNTRACKED FALLBACK, VERBATIM (rider-b deliberately leaves this
        # branch untouched): when ``difference_tracked`` itself refused, no
        # per-face provenance exists to read, so ``inside`` falls back to the
        # revolute band this whole slice replaces on the tracked path — the
        # fleet measurement's own recommendation was to leave keep-adjacent
        # behaviour on this path alone (its own provenance-offset variant,
        # v2@0.06, moves ``keep`` by up to 1,705 faces and needs its own
        # pin); this asymmetry is deliberate, not an oversight.
        C = np.asarray(cut.triangles_center, float)
        # PER-SITE (DEFECT B, the collar bridge below): the band test run
        # separately per site before it is OR'd into the combined ``inside``
        # every other branch of this function has always used — the
        # combined array is unchanged, byte for byte, from before this
        # slice.
        site_inside_masks = []
        for origin, axis, xl, yl, zs_p, prof_p, floor_a, h_low in regions:
            rel = C - origin
            a = rel @ axis
            r = np.hypot(rel @ xl, rel @ yl)
            rmax = np.interp(np.clip(a, float(zs_p[0]), float(zs_p[-1])),
                             zs_p, prof_p)
            site_inside_masks.append(
                (r < rmax + 0.05) & (a > floor_a - 0.05) & (a < h_low + 3.0))
        inside = np.zeros(len(C), bool)
        for site_mask in site_inside_masks:
            inside |= site_mask
        # THE OPEN ARCH COMES BACK (§10-AS.16, client 2026-08-10: "why did we
        # build a dental model — we need to work with the open arch"): the
        # solidify base and skirt exist ONLY so the boolean has a solid to
        # cut. The artifact is the SCAN. A face survives if it lies on a cut
        # surface (the recess) or on the original shell itself; the
        # fabricated closure — base plate, skirt, anything the scan never
        # contained — is stripped by the 0.35mm distance fallback.
        keep = strip_fabricated(cut, arch, inside)

    # DEFECT 1 EXCISION (client-ruled, live verification 2026-08-15): the boolean
    # subtracts the TEMPLATE's own volume, but the scanned cap deviates from it
    # (fleet RMS 0.25/p90 0.35mm) — wherever it stands proud of template+relief its
    # own MEASURED surface survives the cut untouched: floating flaps standing in
    # the recess bore. The real cap physically leaves the mouth; dropping its
    # measured surface is measurement, using the shared classifier
    # (``case_prep.pipeline.isolation.scanned_cap_face_mask``) — the SAME rung
    # ``isolate_scanned_cap``'s own per-site artifact already isolates.
    #
    # Dropped from ``keep`` BEFORE the ``out``/``socket`` split, so it can never
    # land in either: on the tracked path the excision is restricted to ``source
    # == 0`` (scan-provenance, structurally disjoint from ``inside``'s own
    # ``source >= base_groups`` — the assertion below is the permanent, cheap
    # version of that fact, rider-b's own idiom); on the untracked fallback there
    # is no per-face provenance, so the mask is restricted to ``~inside`` (the
    # same revolute-band "is this a punch surface" test the strip itself just
    # used) instead — never a tool/recess face excised, on either path.
    excise = np.zeros(len(cut.faces), bool)
    for e_template, e_pose, _e_offset, e_rim_r in sites:
        try:
            excise |= scanned_cap_face_mask(
                cut, e_template, np.asarray(e_pose, float), float(e_rim_r),
                    full_footprint=True)
        except Exception:  # noqa: BLE001 — the excision refines an already-
            # successful cut; a site it cannot read never fails the whole carve
            continue
    if tool_provenance is not None:
        scan_provenance = np.asarray(tracked.source) == 0
        excise &= scan_provenance
        assert not (excise & tool_provenance).any(), (
            "DEFECT-1 excision must be scan-provenance only — a tool face "
            "was about to be dropped from the cut")
    else:
        excise &= ~inside
    keep = keep & ~excise

    # DEFECT A — THE ORPHAN FLAPS (client-ruled, live verification
    # 2026-08-15): see ``isolation.orphan_flap_mask``'s own docstring. Runs
    # AFTER the excision above, on both branches (the candidate mask is
    # exactly the scan-provenance set that excision itself just used) — no
    # note, by the excision's own contract: dropping measured cap remnant
    # is measurement, not a degradation.
    scan_candidate = ((np.asarray(tracked.source) == 0)
                      if tool_provenance is not None else ~inside)
    site_poses = [(np.asarray(pose, float), float(rim_r))
                 for _, pose, _offset, rim_r in sites]
    orphan = orphan_flap_mask(cut, site_poses, candidate=keep & scan_candidate)
    keep = keep & ~orphan

    F = np.asarray(cut.faces)
    Vc = np.asarray(cut.vertices, float)
    out = trimesh.Trimesh(Vc.copy(), F[keep & ~inside].copy(), process=False)
    out.remove_unreferenced_vertices()
    socket: Optional[trimesh.Trimesh] = None
    if bool(inside.any()):
        socket = trimesh.Trimesh(Vc.copy(), F[inside].copy(), process=False)
        socket.remove_unreferenced_vertices()

    # DEFECT B — THE GAP RING: see ``_bridge_recess_collar``'s own docstring
    # for the full argument. The arch layer's own boundary loops are read
    # ONCE, before any site's bridge lands, so every site's own search sees
    # the same pre-bridge boundary regardless of build order.
    out_boundary_loops = _boundary_loops_of(out)
    bridges: list = []
    for index, ((_, site_pose, _offset, site_rim_r), site_inside) in enumerate(
            zip(sites, site_inside_masks), 1):
        if not bool(site_inside.any()):
            continue
        bridge, note = _bridge_recess_collar(
            out_boundary_loops, Vc, F[site_inside], site_pose, site_rim_r)
        if note is not None:
            notes.append(f"site {index}: {note}")
        if bridge is not None:
            bridges.append(bridge)
    if bridges:
        n_base_faces = len(out.faces)
        out = trimesh.util.concatenate([out] + bridges)
        # THE WELD: every bridge's own inner/outer rings carry the EXACT
        # coordinate values of the loops they bridge (``_zip_loop_bridge``'s
        # own docstring) — merging now, once, over the whole result, closes
        # those seams for real rather than leaving two coincident copies
        # standing apart.
        out.merge_vertices()
        out = _shed_nonmanifold_strip_faces(out, n_base_faces)

    out, cull_notes = cull_floating_fragments(out, site_poses)
    notes.extend(cull_notes)
    return out, socket, notes


def cap_imprint_parts(arch: trimesh.Trimesh,
                      sites: "Sequence[Tuple[trimesh.Trimesh, np.ndarray, float, float]]",
                      visible_depth_mm: Optional[float] =
                      _SOCKET_VISIBLE_DEPTH_MM,
                      top_floor: bool = False
                      ) -> Tuple[trimesh.Trimesh, Optional[trimesh.Trimesh],
                                 list]:
    """THE RECESS, CUT FOR REAL (§10-AS.12, client 2026-08-10 on the pressed
    carve's floor: "not smooth at all, and hole in the middle?"). The scan is
    SOLIDIFIED (skirt + base + hole lids — which is what fills the scan's own
    hole inside the cap's recess) and every site's punch — the relief envelope
    plus the deviation clearance, flat-bottomed at the local gum's low
    quartile minus the countersink — is subtracted in ONE manifold boolean.
    The result is watertight: machined wall, machined floor, no backface
    possible from any angle. Faces on the cut surface split into the SOCKET
    piece for the preview tint; concatenating the two pieces rebuilds the cut
    solid exactly. Inside ``_csg_carve``, the fabricated closure (base plate,
    skirt) is stripped by manifold3d's own face PROVENANCE now — exact by
    construction (boolean-engine plan W1, 2026-08-13) — with the old 0.35mm
    distance test as ITS OWN fallback, noted, never silent. When the CSG
    route cannot run at all (an unclosable shell, a boolean refusal) the
    one-shell PRESS carve (§10-AS.10) takes over with a note — an honest
    degradation, never a dead package."""
    try:
        return _csg_carve(arch, sites, visible_depth_mm, top_floor)
    except Exception as exc:  # noqa: BLE001 — the fallback IS the containment
        out, socket, notes = _press_carve(arch, sites,
                                          visible_depth_mm=visible_depth_mm,
                                          top_floor=top_floor)
        return out, socket, [f"the true-boolean recess could not be cut "
                             f"({exc}) — the pressed carve was used instead"
                             ] + notes



def _press_carve(arch: trimesh.Trimesh,
                      sites: Sequence[Tuple[trimesh.Trimesh, np.ndarray,
                                            float, float]],
                      visible_depth_mm: Optional[float] =
                      _SOCKET_VISIBLE_DEPTH_MM,
                      top_floor: bool = False
                      ) -> Tuple[trimesh.Trimesh, Optional[trimesh.Trimesh],
                                 list]:
    """THE PRESS FALLBACK (§10-AS.12 demoted it from the front line): the
    one-shell carve that presses scan vertices onto the floor. Kept whole as
    the honest degradation when the CSG route cannot run — it can never die,
    but its floor is pressed scan debris and a scan hole in the cap's own
    recess survives as a hole in the floor (the client's screenshot).
    Original charter (client 2026-08-10, §10-AS.10, over the competitor's screenshot:
    "look like the second picture — there is a floor and the floor is lower by
    the gum, which shows the gingival offset"). The recess is pressed into the
    scan's OWN vertices: every vertex standing inside the cap's relief envelope
    (plus the deviation clearance) above the recess floor is moved straight down
    the pose axis onto that floor. No liner, no collar, no seams — and no
    backface can EVER show, because the shell stays one continuous surface. The
    liner architecture this replaces (envelope solid + fitted-plane clip +
    draped collar + saucer, §10-AO..AS.7) fixed one viewing angle per pass
    because it decorated an open hole with floating geometry; the carve retires
    the whole class.

    THE FLOOR FOLLOWS THE GUM: per bearing, the local gum height is the median
    of the scan's own ring vertices just outside the recess, gap-filled
    circularly and smoothed; the floor sits a constant countersink below it —
    ``top_floor`` (the platform artifact): max(the site's relief, 0.5mm
    legibility); else ``visible_depth_mm`` (the 1.8mm dish); ``None``: down to
    the envelope's base. A planar floor dug a pocket into sloped ridges whose
    tall wall read as a dark blade from the low side (the client's screenshot).

    Returns (arch-without-recess-faces, recess-faces, notes) — the two piece
    meshes share the carved coordinates, so concatenating them rebuilds the
    carved arch exactly; the split exists so the preview can tint the recess.
    A site that cannot make an envelope profile is carved as a CYLINDER recess
    at its rim radius, and says so in the notes; a site with no gum ring around
    it is left uncut, and says so."""
    notes: list = []
    V = np.asarray(arch.vertices, float).copy()
    moved_any = np.zeros(len(V), bool)
    for index, (template, pose, offset_mm, rim_radius_mm) in enumerate(sites, 1):
        pose = np.asarray(pose, float)
        try:
            origin = pose[:3, 3]
            R = pose[:3, :3]
            axis = R @ np.array([0.0, 0.0, 1.0])
            xl = R @ np.array([1.0, 0.0, 0.0])
            yl = R @ np.array([0.0, 1.0, 0.0])
            try:
                zs_p, prof_p = _envelope_profile(template, offset_mm)
            except Exception as exc:  # noqa: BLE001 — carve on, honestly
                # span far past any gum height BOTH ways: the floor depth is
                # the gum-following countersink's job, and a short profile
                # base once left the fallback floor standing ABOVE the sheet
                zs_p = np.array([-_HOLE_DEPTH_MM, _HOLE_DEPTH_MM])
                prof_p = np.full(2, rim_radius_mm + _REGION_MARGIN_MM)
                notes.append(f"site {index}: the cap envelope could not be "
                             f"built ({exc}) — a cylinder recess was carved "
                             f"at the rim radius instead")
            rel = V - origin
            a = rel @ axis
            r = np.hypot(rel @ xl, rel @ yl)
            th = np.arctan2(rel @ yl, rel @ xl)
            # the local gum ring, per bearing: the scan's own vertices just
            # outside the widest envelope radius. Median per 64 bins, gaps
            # filled circularly, 3-tap smoothed — the same drape idea AS.7
            # proved, now driving the floor instead of a collar.
            r_ref = float(np.max(prof_p)) + _CULL_MARGIN_MM
            band = (r > r_ref + 0.1) & (r < r_ref + 1.2) & (np.abs(a) < 6.0)
            if int(band.sum()) < 8:
                raise ValueError("no gum ring around the site")
            nb = 64
            bins = ((th + np.pi) / (2.0 * np.pi) * nb).astype(int) % nb
            h = np.full(nb, np.nan)
            for b in range(nb):
                sel = band & (bins == b)
                # one vertex is a legitimate (if noisy) read — sparse shells
                # exist, and the circular smoothing below steadies it. The
                # LOW quartile, not the median: at a bearing where the ring
                # band grazes a NEIGHBOURING CROWN the band is mostly tooth —
                # measured +3.2mm "gum" on cap6030 — and the lowest surface
                # in the band is the gingiva the floor must follow.
                if sel.sum() >= 1:
                    h[b] = float(np.percentile(a[sel], 25))
            good = ~np.isnan(h)
            # the crown clamp, one-sided: no bearing's gum read may stand
            # more than 1.5mm above the ring's own median — that is a crown,
            # not gingiva. Low outliers stay: a real gum valley is real.
            if good.any():
                h_med = float(np.median(h[good]))
                h[good] = np.minimum(h[good], h_med + 1.5)
            idx = np.arange(nb, dtype=float)
            h = np.interp(idx, idx[good], h[good], period=float(nb))
            h = (np.roll(h, 1) + h + np.roll(h, -1)) / 3.0
            if top_floor:
                depth = max(float(offset_mm), _PLATFORM_COUNTERSINK_MIN_MM)
            elif visible_depth_mm is not None:
                depth = float(visible_depth_mm)
            else:
                depth = None
            h_v = h[bins]
            # the rim: the envelope's radius AT the local gum height, plus the
            # deviation clearance (§10-AR.3's lesson: the scanned cap strays
            # beyond the relief envelope; without the margin its excursions
            # survive as torn flaps standing in the recess). A HIGH gum read
            # never narrows the rim: where the ring grazes a crown, prof(h)
            # picks the envelope's slim top and the cap's flank survived
            # standing (113 vertices on cap6030) — the rim reads the envelope
            # no higher than just above the ring's own median.
            h_med2 = float(np.median(h))
            rim_v = (np.interp(np.minimum(h_v, h_med2 + 0.5), zs_p, prof_p)
                     + _CULL_MARGIN_MM)
            # the floor's reference height: the ring's own bearing read at the
            # rim, blended to the ring's circular mean at the centre — a
            # centre vertex's bearing is numerical noise, and an unblended
            # per-bearing floor came out jagged in the middle of the recess
            w = np.clip(r / np.maximum(rim_v, 1e-6), 0.0, 1.0)
            h_eff = (1.0 - w) * float(h.mean()) + w * h_v
            if depth is None:
                floor_v = np.full(len(V), float(zs_p[0]))
            else:
                # never below the envelope's own base — the recess is the
                # cap's, not a well past it
                floor_v = np.maximum(h_eff - depth, float(zs_p[0]))
            press = (r < rim_v) & (a > floor_v)
            if not press.any():
                raise ValueError("the recess would touch no scan vertex")
            V[press] -= np.outer(a[press] - floor_v[press], axis)
            moved_any |= press
        except Exception as exc:  # noqa: BLE001 — an uncut site over a dead one
            notes.append(f"site {index}: the cap imprint could not be carved "
                         f"({exc}) — the site was left uncut")
    faces = np.asarray(arch.faces)
    face_moved = moved_any[faces].any(axis=1)

    # DEFECT 1 EXCISION (client-ruled, live verification 2026-08-15): the press
    # only relocates vertices INSIDE its own culled rim/floor — a scanned cap
    # that bulges past that cull (or a site the loop above left uncut, "no gum
    # ring") can still stand in ``out`` as measured crust. Applied over the
    # PRISTINE ``arch`` (the loop above moves ``V`` in place, but the classifier
    # reads geometry, and ``arch``'s own untouched coordinates are exactly what
    # a genuinely un-pressed face still carries) — the same shared classifier
    # (``case_prep.pipeline.isolation.scanned_cap_face_mask``) every other
    # DEFECT-1 consumer uses. NO PER-FACE PROVENANCE EXISTS HERE AT ALL (there
    # is no boolean, only a vertex press), so the mask is restricted to
    # ``~face_moved``: a face already pressed onto the floor IS the recess's
    # own material and is never touched twice.
    excise = np.zeros(len(faces), bool)
    for e_template, e_pose, _e_offset, e_rim_r in sites:
        try:
            excise |= scanned_cap_face_mask(
                arch, e_template, np.asarray(e_pose, float), float(e_rim_r),
                    full_footprint=True)
        except Exception:  # noqa: BLE001 — the excision refines an already-
            # successful carve; a site it cannot read never fails the whole
            # carve
            continue
    excise &= ~face_moved

    # DEFECT A — THE ORPHAN FLAPS (client-ruled, live verification
    # 2026-08-15): see ``isolation.orphan_flap_mask``'s own docstring. Same
    # PRISTINE-``arch`` reasoning as the excision just above (candidacy is
    # everything not already pressed or excised); no note, by the
    # excision's own contract.
    site_poses = [(np.asarray(pose, float), float(rim_radius_mm))
                 for _, pose, _offset, rim_radius_mm in sites]
    orphan = orphan_flap_mask(arch, site_poses,
                              candidate=~(face_moved | excise))
    excise = excise | orphan

    out = trimesh.Trimesh(V.copy(), faces[~(face_moved | excise)].copy(),
                          process=False)
    out.remove_unreferenced_vertices()
    socket: Optional[trimesh.Trimesh] = None
    if bool(face_moved.any()):
        socket = trimesh.Trimesh(V.copy(), faces[face_moved].copy(),
                                 process=False)
        socket.remove_unreferenced_vertices()
    out, cull_notes = cull_floating_fragments(out, site_poses)
    notes.extend(cull_notes)
    return out, socket, notes


def open_arch_with_floored_holes(scan: trimesh.Trimesh,
                                 sites: Sequence[Tuple[trimesh.Trimesh,
                                                       np.ndarray, float,
                                                       float]]
                                 ) -> Tuple[Optional[trimesh.Trimesh], list]:
    """ARTIFACT 6, THE FOURTH RULING (client-ruled, live call with the lab over
    a reference image, 2026-08-15 night; verbatim: "why is that cylinder so
    big" — on the through-shaft this function's predecessor extended past the
    model's own base; "[it] should have the hole with the gingival floor").
    RETIRES ``open_arch_with_through_holes`` (the third ruling, same day, same
    authority, same artifact slot): the doctor's OPEN scan, each site's cap
    punched to a CLEAN SHALLOW RECESS whose floor sits at gum level — no pipe
    descending into the solidified interior, no cap, exactly the reference
    tool's own look.

    THE FLOOR IS THE SAME GUM-FOLLOWING MEASUREMENT ``_csg_carve`` has always
    cut a socket to (``_gingival_floor_a`` — the ring-read low quartile,
    clamped against the solidified shell's own true material limit),
    requested at ``depth_mm=0.0``: the gingival level itself, the site's own
    relief and nothing more. This is deliberately NOT the 1.8mm inspection
    dish (``_SOCKET_VISIBLE_DEPTH_MM``, ``cap_imprint_holes``'s own default)
    — that is a visible pocket for a different artifact; this floor sits AT
    the gum, invisible as a "dish" because it is the surface the cap actually
    sat on.

    NO SHAFT EXTENSION: the through-hole ruling's own barrel — bridging an
    unfloored punch's natural bottom down to the solidified shell's base
    plate, so the bore opened all the way through — is gone entirely; the
    client's own words on it named the extended shaft itself as the defect.
    A floored envelope punch never needs one: ``punch_solid`` is called
    WITH ``floor_a`` (the envelope-is-the-cut refinement below).

    THE ENVELOPE IS THE CUT (the same ruling, refined the same night on its
    own first emit — cap7030 tooth 29, run 20260815-224356-8056c2): the
    EXACT cap as the punch prints the cap's interior anatomy into the hole.
    The screw slot and the code windows are VOIDS in the cap's solid, so the
    scanned bump's material there survives the difference as standing
    columns; the sub-platform connection lobes print as trenches (measured:
    punch-signature surfaces at exactly the site's 0.08mm offset, spanning
    the gum floor −3.08 up to the dome imprint's +1.89 — the client's
    verbatim reading of that geometry: "no i see the healing cap"). This
    artifact therefore cuts with the cap's REVOLUTE ENVELOPE
    (``punch_solid`` — max radius per height, floored), the semantics the
    client already confirmed for the capless seat (2026-08-09, the
    envelope-socket ruling: the seat is "never the exact surface"): a clean
    revolute recess to the gum floor, no anatomy, the reference look. The
    exact-cut doctrine (§10-AS.14) is untouched where it lives — the
    carve/socket artifacts, where the gum genuinely healed around the cap's
    exact shape.

    Per site ``(template, pose_matrix, offset_mm, rim_radius_mm)``: a
    template whose envelope profile cannot be read cuts a cylinder recess at
    the catalog rim radius, noted; a site with no measurable gum ring is an
    honest refusal (there is no floor to fall back to that is not a guess)
    that fails the WHOLE artifact open, never smuggled past as a silent
    zero.

    Everything else is unchanged from the through-hole shape it replaces: the
    tracked difference against the solidified shell, ``strip_tracked``/
    ``strip_fabricated`` dropping the fabricated closure, and DEFECT 1's
    excision (``case_prep.pipeline.isolation.scanned_cap_face_mask``,
    restricted to scan-provenance faces) all run exactly as before. FAIL-OPEN
    AS A WHOLE: any refusal — the shell will not solidify, no gum ring at
    some site, the boolean itself refuses, nothing survives the strip —
    returns ``(None, [why])`` and the package ships without it."""
    try:
        solid = solidified_shell_cached(scan)
        V = np.asarray(scan.vertices, float)
        punches = []
        notes: list = []
        site_geoms: list = []   # (pose, floor_a, r_ref) — the lids/bridge below
        for index, (template, pose, offset_mm, rim_radius_mm) in enumerate(
                sites, 1):
            pose = np.asarray(pose, float)
            origin = pose[:3, 3]
            R = pose[:3, :3]
            axis = R @ np.array([0.0, 0.0, 1.0])
            xl = R @ np.array([1.0, 0.0, 0.0])
            yl = R @ np.array([0.0, 1.0, 0.0])
            try:
                zs_p, prof_p = _envelope_profile(template, float(offset_mm))
            except Exception as exc:  # noqa: BLE001 — cut on, honestly
                zs_p = np.array([-_HOLE_DEPTH_MM, _HOLE_DEPTH_MM])
                prof_p = np.full(2, rim_radius_mm + _REGION_MARGIN_MM)
                notes.append(f"site {index}: the cap envelope could not be "
                             f"built ({exc}) — a cylinder recess was cut at "
                             f"the rim radius instead")
            # THE FLOOR: the gingival level itself (depth_mm=0.0) — no dish,
            # no countersink, the site's own relief and nothing more. A site
            # with no measurable gum ring raises here and fails the WHOLE
            # artifact open (see this function's own docstring) — there is
            # no honest floor to fall back to.
            floor_a, _h_low = _gingival_floor_a(
                V, solid, index, origin, axis, xl, yl, zs_p, prof_p, 0.0)
            # THE ENVELOPE IS THE CUT — never ``exact_cap_punch`` here (see
            # this function's own docstring: the exact cap prints its slot,
            # code windows and connection lobes into the hole as the cap's
            # ghost). A failed profile already noted its cylinder shape.
            punches.append(punch_solid(zs_p, prof_p, floor_a, pose))
            site_geoms.append((pose, float(floor_a), float(np.max(prof_p))))

        tracked_keep: Optional[np.ndarray] = None
        scan_provenance: Optional[np.ndarray] = None
        try:
            fabricated = fabricated_face_mask(scan, solid)
            tracked = default_kernel().difference_tracked(
                solid, punches, fabricated.astype(np.int64))
            cut = tracked.mesh
            if not cut.is_watertight:
                raise ValueError("the tracked boolean result is not watertight")
            tracked_keep = strip_tracked(tracked)
            scan_provenance = np.asarray(tracked.source) == 0
        except Exception as exc:  # noqa: BLE001 — fail-open to the untracked
            # engine and the distance strip
            cut = default_kernel().difference(solid, punches)
            if not cut.is_watertight:
                raise ValueError("the boolean result is not watertight")
            notes.append(f"the provenance-tracked strip could not run ({exc}) "
                         f"— the distance-based strip was used instead")

        if tracked_keep is not None:
            keep = tracked_keep
        else:
            # no punch region to keep separately here (this artifact has no
            # socket layer of its own) — the strip's "keep the recess too"
            # argument is an honest all-False; the recess's own wall/floor
            # survives as ordinary cut surface, exactly like every
            # scan-adjacent face
            keep = strip_fabricated(cut, scan, np.zeros(len(cut.faces), bool))

        # DEFECT 1 EXCISION (client-ruled, live verification 2026-08-15) — see
        # ``_csg_carve``'s own comment for the full argument. Applied here too:
        # a scanned cap's own crust can still stand proud of the floored recess.
        excise = np.zeros(len(cut.faces), bool)
        for e_template, e_pose, _e_offset, e_rim_r in sites:
            try:
                excise |= scanned_cap_face_mask(
                    cut, e_template, np.asarray(e_pose, float),
                    float(e_rim_r),
                    full_footprint=True)
            except Exception:  # noqa: BLE001 — the excision refines an
                # already-successful cut; a site it cannot read never fails
                # the whole artifact
                continue
        if scan_provenance is not None:
            excise &= scan_provenance
        keep = keep & ~excise

        # DEFECT A — THE ORPHAN FLAPS (client-ruled, live verification
        # 2026-08-15): see ``isolation.orphan_flap_mask``'s own docstring —
        # applied here too. No note, by the excision's own contract.
        site_poses = [(np.asarray(pose, float), float(rim_radius_mm))
                     for _, pose, _offset, rim_radius_mm in sites]
        scan_candidate = keep if scan_provenance is None else (keep & scan_provenance)
        orphan = orphan_flap_mask(cut, site_poses, candidate=scan_candidate)
        keep = keep & ~orphan

        F = np.asarray(cut.faces)
        Vc = np.asarray(cut.vertices, float)
        out = trimesh.Trimesh(Vc.copy(), F[keep].copy(), process=False)
        out.remove_unreferenced_vertices()
        if len(out.faces) == 0:
            raise ValueError("the floored hole cut left nothing to ship")

        # THE FLOOR LIDS (client live, 2026-08-16: "still see residues or
        # left over" — the white patch INSIDE the recess). Where the scan
        # dove BELOW the gingival floor (a pocket the scanner saw through
        # the cap's own openings — measured on 276794487's own run as a
        # 395-vertex boundary loop AT the floor plane), the floor plane cut
        # nothing and the disc is left holed. Every floor-height boundary
        # loop inside the hole's own footprint is fan-lidded flat — the
        # floor itself is the fourth ruling's own client-ruled fabrication
        # at gum level, and lidding its holes is the same ruling, noted.
        for index, (pose, floor_a, r_ref) in enumerate(site_geoms, 1):
            origin = pose[:3, 3]
            R = pose[:3, :3]
            axis = R @ np.array([0.0, 0.0, 1.0])
            lids, lid_count = _lid_planar_holes(out, origin, axis, floor_a,
                                                r_ref)
            if lid_count:
                out = trimesh.util.concatenate([out] + lids)
                out.merge_vertices()
                notes.append(
                    f"site {index}: {lid_count} gap"
                    f"{'' if lid_count == 1 else 's'} in the gingival floor "
                    f"{'was' if lid_count == 1 else 'were'} lidded — the "
                    f"scan there dove below the floor through the cap's own "
                    f"openings")

        # THE COLLAR BRIDGE, here too (client live, 2026-08-16, the second
        # screenshot's moat crescents — this artifact never received the
        # wiring ``_csg_carve`` got; the reconciliation the floored-holes
        # ledger entry flagged). Tracked provenance names each site's own
        # tool faces; the untracked fallback path stays bridge-less — its
        # note already discloses the degraded build.
        if tracked_keep is not None:
            out_boundary_loops = _boundary_loops_of(out)
            kept_source = np.asarray(tracked.source)[keep]
            out_F = np.asarray(cut.faces)[keep]
            bridges: list = []
            for index, ((pose, _floor_a, _r_ref), (_t, _p, _o, site_rim_r)) \
                    in enumerate(zip(site_geoms, sites), 1):
                site_tool = out_F[kept_source == (tracked.base_groups
                                                  + (index - 1))]
                if len(site_tool) == 0:
                    continue
                bridge, note = _bridge_recess_collar(
                    out_boundary_loops, Vc, site_tool, pose,
                    float(site_rim_r))
                if note is not None:
                    notes.append(f"site {index}: {note}")
                if bridge is not None:
                    bridges.append(bridge)
            if bridges:
                n_base_faces = len(out.faces)
                out = trimesh.util.concatenate([out] + bridges)
                out.merge_vertices()
                out = _shed_nonmanifold_strip_faces(out, n_base_faces)

        out, cull_notes = cull_floating_fragments(
            out, [(np.asarray(pose, float), float(rim_r))
                  for _t, pose, _o, rim_r in sites])
        notes.extend(cull_notes)
        return out, notes
    except Exception as exc:  # noqa: BLE001 — honest absence
        return None, [f"the open arch with floored holes could not be built "
                      f"({exc}) — the package ships without it"]
