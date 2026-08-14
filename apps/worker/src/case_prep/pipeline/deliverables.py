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
                          posed_parts: Sequence[Tuple[trimesh.Trimesh, np.ndarray]]
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
    geometry degrades silently, the manifest never does."""
    from scipy.spatial import cKDTree

    try:
        solid = solidified_shell_cached(arch)
        part_solids: List[trimesh.Trimesh] = []
        fallback_parts: List[Tuple[trimesh.Trimesh, np.ndarray]] = []
        notes: List[str] = []
        for index, (part, pose) in enumerate(posed_parts, 1):
            try:
                part_solids.append(exact_cap_punch(part, 0.0, np.asarray(pose, float)))
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
        F = np.asarray(fused.faces)
        V = np.asarray(fused.vertices, float)
        out = trimesh.Trimesh(V.copy(), F[keep].copy(), process=False)
        out.remove_unreferenced_vertices()
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
        if top_floor:
            depth = max(float(offset_mm), _PLATFORM_COUNTERSINK_MIN_MM)
        elif visible_depth_mm is not None:
            depth = float(visible_depth_mm)
        else:
            depth = None
        floor_a = (float(zs_p[0]) if depth is None
                   else max(h_low - depth, float(zs_p[0])))
        if depth is not None:
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
                ray_origins=probes,
                ray_directions=[-axis] * len(probes))
            if len(hits):
                base_a = float(((hits - origin) @ axis).min())
                floor_a = max(floor_a, base_a + 0.3)
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
        inside = np.zeros(len(C), bool)
        for origin, axis, xl, yl, zs_p, prof_p, floor_a, h_low in regions:
            rel = C - origin
            a = rel @ axis
            r = np.hypot(rel @ xl, rel @ yl)
            rmax = np.interp(np.clip(a, float(zs_p[0]), float(zs_p[-1])),
                             zs_p, prof_p)
            inside |= ((r < rmax + 0.05) & (a > floor_a - 0.05)
                      & (a < h_low + 3.0))
        # THE OPEN ARCH COMES BACK (§10-AS.16, client 2026-08-10: "why did we
        # build a dental model — we need to work with the open arch"): the
        # solidify base and skirt exist ONLY so the boolean has a solid to
        # cut. The artifact is the SCAN. A face survives if it lies on a cut
        # surface (the recess) or on the original shell itself; the
        # fabricated closure — base plate, skirt, anything the scan never
        # contained — is stripped by the 0.35mm distance fallback.
        keep = strip_fabricated(cut, arch, inside)
    F = np.asarray(cut.faces)
    Vc = np.asarray(cut.vertices, float)
    out = trimesh.Trimesh(Vc.copy(), F[keep & ~inside].copy(), process=False)
    out.remove_unreferenced_vertices()
    socket: Optional[trimesh.Trimesh] = None
    if bool(inside.any()):
        socket = trimesh.Trimesh(Vc.copy(), F[inside].copy(), process=False)
        socket.remove_unreferenced_vertices()
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
    out = trimesh.Trimesh(V.copy(), faces[~face_moved].copy(), process=False)
    out.remove_unreferenced_vertices()
    socket: Optional[trimesh.Trimesh] = None
    if bool(face_moved.any()):
        socket = trimesh.Trimesh(V.copy(), faces[face_moved].copy(),
                                 process=False)
        socket.remove_unreferenced_vertices()
    return out, socket, notes


def closed_model_with_recesses(scan: trimesh.Trimesh,
                               sites: Sequence[Tuple[trimesh.Trimesh,
                                                     np.ndarray, float,
                                                     float]]
                               ) -> Tuple[Optional[trimesh.Trimesh], list]:
    """ARTIFACT 6 RETURNS (client 2026-08-11: "we lose the artifact 6 we had
    before"), rebuilt thin on the csg machinery: the solidified lab model —
    base kept, this is its whole point — with every site's EXACT cap + offset
    cut out by one manifold difference. §10-AS.19's retirement is reversed by
    the client's own ask; §10-AS.16's open-arch doctrine still governs every
    OTHER artifact. FAIL-OPEN as a whole: additive artifact, so any refusal
    returns (None, [why]) and the package ships without it."""
    try:
        solid = solidified_shell_cached(scan)
        tools = []
        notes: list = []
        for index, (template, pose, offset_mm, rim_radius_mm) in enumerate(
                sites, 1):
            pose = np.asarray(pose, float)
            try:
                tools.append(exact_cap_punch(template, float(offset_mm), pose))
            except Exception as exc:  # noqa: BLE001 — the envelope stands in
                zs_p, prof_p = _envelope_profile(template, float(offset_mm))
                tools.append(punch_solid(zs_p, prof_p, float(zs_p[0]), pose))
                notes.append(f"site {index}: the exact cap could not be cut "
                             f"in the closed model ({exc}) — its envelope "
                             f"was used instead")
        model = default_kernel().difference(solid, tools)
        if not model.is_watertight:
            raise ValueError("the boolean result is not watertight")
        return model, notes
    except Exception as exc:  # noqa: BLE001 — honest absence
        return None, [f"the closed model could not be built ({exc}) — "
                      f"the package ships without it"]
