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

from typing import Iterable, Sequence, Tuple

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
