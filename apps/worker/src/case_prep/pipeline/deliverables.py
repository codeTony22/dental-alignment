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

from typing import Iterable, Optional, Sequence, Tuple

import numpy as np
import trimesh

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
    """The arch plus each part transformed by its pose — one composite deliverable mesh."""
    placed = []
    for part, pose in posed_parts:
        p = part.copy()
        p.apply_transform(np.asarray(pose, float))
        placed.append(p)
    return trimesh.util.concatenate([arch.copy()] + placed)


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
    out = arch
    notes: list = []
    liners = []
    V = np.asarray(arch.vertices, float)
    for index, (template, pose, offset_mm, rim_radius_mm) in enumerate(sites, 1):
        pose = np.asarray(pose, float)
        try:
            posed = _envelope_solid(template, offset_mm)
            posed.apply_transform(pose)
            # THE CULL SWEEPS WIDER THAN THE SEAT (client 2026-08-09): the
            # scanned cap deviates from the template, and everything it does
            # beyond the relief envelope survived as torn flaps around the
            # socket. The cull uses its own clearance; the liner stays exact.
            cull = _envelope_solid(template, offset_mm + _CULL_MARGIN_MM)
            cull.apply_transform(pose)
            collar = _collar_z_local(V, pose, rim_radius_mm)
            # THE ANY-VERTEX CULL: a face goes if any of its three corners is
            # inside the cull envelope. All-corners-outside-with-centroid-inside
            # needs a triangle wider than the socket — scan facets are ~0.3mm
            # against a ~5mm envelope, so the vertex test alone decides. The
            # kept boundary then has no vertex reaching in: no needle tips.
            verts_now = np.asarray(out.vertices, float)
            lo, hi = cull.bounds
            near_v = np.all((verts_now >= lo - 1e-6) & (verts_now <= hi + 1e-6),
                            axis=1)
            v_inside = np.zeros(len(verts_now), bool)
            if near_v.any():
                v_inside[near_v] = cull.contains(verts_now[near_v])
            face_gone = v_inside[out.faces].any(axis=1)
            kept = trimesh.Trimesh(verts_now.copy(),
                                   out.faces[~face_gone], process=False)
            kept.remove_unreferenced_vertices()
            # the liner: the envelope's surface below the gum line (plus a small
            # tuck so the wall reaches behind the cut edge), measured along the
            # POSE AXIS about the pose origin. The gum line is a FITTED PLANE
            # (client 2026-08-09): one median collar left the wall standing in a
            # proud crescent out of the low side of a tilted arch — each face is
            # clipped against the plane's height at its OWN position. Wound to
            # face the VOID: walls inward, floor discs upward — the flip is
            # skipped for faces already pointing up the axis (the top disc, when
            # a submerged cap leaves it below the gum).
            origin = pose[:3, 3]
            R = pose[:3, :3]
            axis = R @ np.array([0.0, 0.0, 1.0])
            a0, bx, cy = _collar_plane(V, pose, rim_radius_mm)
            zs_p, prof_p = _envelope_profile(template, offset_mm)
            # THE FLOOR STOPS JUST BELOW THE GUM (client 2026-08-09): the higher
            # of the cap's offset base and (collar − visible depth). A tall cap's
            # full tunnel hung out of the thin scan shell as a cylinder.
            # THE PLATFORM FLOOR, CORRECTED (client 2026-08-09, third pass:
            # "still too deep — just the gingival offset platform, the top of
            # the library"): top_floor puts the floor at the CAP'S TOP + the
            # relief — the envelope's own top disc — clamped just below the
            # gum so a proud cap still leaves its footprint dish rather than
            # no socket at all. visible_depth_mm=None keeps the full-depth
            # read; the default stays the shallow visible dish.
            if top_floor:
                floor_axial = max(min(float(zs_p[-1]), a0 - 0.05),
                                  float(zs_p[0]))
            elif visible_depth_mm is None:
                floor_axial = float(zs_p[0])
            else:
                floor_axial = max(float(zs_p[0]),
                                  a0 - float(visible_depth_mm))
            fc = np.asarray(posed.triangles_center, float) - origin
            face_axial = fc @ axis
            fx = fc @ (R @ np.array([1.0, 0.0, 0.0]))
            fy = fc @ (R @ np.array([0.0, 1.0, 0.0]))
            # judged by the face's HIGHEST vertex, not its centroid: the bottom
            # ring is pulled down by the offset, so its quads span several ring
            # rows — a centroid that passed the clip left its top vertex 0.36mm
            # proud of the gum (measured on the tilted-sheet pin)
            v_axial = (np.asarray(posed.vertices, float) - origin) @ axis
            face_top = v_axial[posed.faces].max(axis=1)
            # the wall band: fully below the gum tuck, with any part above the
            # floor (a face straddling the floor hides under the floor fan).
            # The honest emptiness test is the FLOOR's, not the wall's: a gum
            # line at the cap's base leaves a legitimate floor-and-collar
            # socket with no wall rows at all.
            if floor_axial > a0 + 0.15:
                raise ValueError("imprint sits wholly above the gum line")
            below = ((face_top <= a0 + bx * fx + cy * fy + 0.15)
                     & (face_top >= floor_axial + 0.01))
            site_liners = []
            if below.any():
                kept_faces = posed.faces[below].copy()
                outward = np.asarray(posed.face_normals, float)[below] @ axis
                flip = outward <= 0.9
                kept_faces[flip] = kept_faces[flip][:, ::-1]
                liner = trimesh.Trimesh(np.asarray(posed.vertices).copy(),
                                        kept_faces, process=False)
                liner.remove_unreferenced_vertices()
                site_liners.append(liner)
            # the floor itself: one flat fan at the visible depth, radius from
            # the envelope's own profile there — the lathe's bottom disc is
            # below the axial filter, so this is the ONE floor either way
            r_floor = float(np.interp(floor_axial, zs_p, prof_p))
            f_seg = 64
            f_theta = np.linspace(0.0, 2.0 * np.pi, f_seg, endpoint=False)
            xl0 = R @ np.array([1.0, 0.0, 0.0])
            yl0 = R @ np.array([0.0, 1.0, 0.0])
            ring = (origin[None, :] + axis[None, :] * floor_axial
                    + np.outer(np.cos(f_theta) * r_floor, xl0)
                    + np.outer(np.sin(f_theta) * r_floor, yl0))
            f_verts = np.vstack([origin + axis * floor_axial, ring])
            f_faces = [[0, 1 + j, 1 + (j + 1) % f_seg] for j in range(f_seg)]
            site_liners.append(trimesh.Trimesh(f_verts,
                                               np.asarray(f_faces, int),
                                               process=False))
            # THE COLLAR ANNULUS (client 2026-08-09: "we cannot leave the empty
            # space there"): the any-vertex cull opens the scan up to one
            # triangle-edge WIDER than the wall, leaving an annular moat between
            # the wall's mouth and the cut edge. Bridge it — inner ring on the
            # wall's own mouth, outer ring 1.4mm out riding the fitted gum
            # plane, faces up. The same bridging the cylinder socket always had
            # (_hole_bore's collar); this one follows the tilt.
            xl = R @ np.array([1.0, 0.0, 0.0])
            yl = R @ np.array([0.0, 1.0, 0.0])
            seg = 64
            theta = np.linspace(0.0, 2.0 * np.pi, seg, endpoint=False)
            dirs = (np.outer(np.cos(theta), xl) + np.outer(np.sin(theta), yl))
            # the mouth's radius depends on its height and vice versa (a tilted
            # plane over a lathe) — two fixed-point passes settle it
            mouth_h = np.full(seg, a0 + 0.15)
            for _ in range(2):
                r_mouth = np.interp(mouth_h, zs_p, prof_p)
                mx = r_mouth * np.cos(theta)
                my = r_mouth * np.sin(theta)
                mouth_h = a0 + bx * mx + cy * my + 0.15
            # the collar reaches past the cut edge, which now sits a cull margin
            # farther out than the wall
            r_outer = r_mouth + 1.4 + _CULL_MARGIN_MM
            ox = r_outer * np.cos(theta)
            oy = r_outer * np.sin(theta)
            outer_h = a0 + bx * ox + cy * oy
            inner_pts = (origin[None, :] + dirs * r_mouth[:, None]
                         + np.outer(mouth_h, axis))
            outer_pts = (origin[None, :] + dirs * r_outer[:, None]
                         + np.outer(outer_h, axis))
            collar_faces = []
            for j in range(seg):
                k = (j + 1) % seg
                collar_faces.append([j, seg + j, seg + k])
                collar_faces.append([j, seg + k, k])
            collar = trimesh.Trimesh(np.vstack([inner_pts, outer_pts]),
                                     np.asarray(collar_faces, int),
                                     process=False)
            # the site lands ATOMICALLY: nothing joins the output until every
            # piece of it exists — a late exception must reach the fallback with
            # no half-liner already in the list
            site_liners.append(collar)
            out = kept
            liners.extend(site_liners)
        except Exception as exc:  # noqa: BLE001 — the fallback IS the containment
            notes.append(f"site {index}: the cap imprint could not be built "
                         f"({exc}) — the cylinder socket was used instead")
            collar = _collar_z_local(V, pose, rim_radius_mm)
            span_up = 8.0
            shifted = pose.copy()
            shifted[:3, 3] = (pose[:3, 3] + (pose[:3, :3] @ np.array([0., 0., 1.]))
                              * (collar + (span_up - _HOLE_DEPTH_MM) / 2.0))
            out = remove_cap_region(out, shifted, radius_mm=rim_radius_mm,
                                    half_height_mm=(_HOLE_DEPTH_MM + span_up) / 2.0)
            liners.append(_hole_bore(pose, rim_radius_mm + _REGION_MARGIN_MM,
                                     collar, _HOLE_DEPTH_MM))
    return trimesh.util.concatenate([out] + liners), notes
