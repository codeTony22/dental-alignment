"""Dental boolean operations via SDF-CSG (design 6.5). The second operand is an
analytic primitive (cylinder / offset), so only the restoration mesh is voxelized —
fast, and robust to the non-watertight scan geometry that cracks naive mesh booleans.
"""
from __future__ import annotations

import numpy as np
import trimesh

from case_prep.adapters.mesh_sdf import mesh_to_sdf, resample_sdf, sdf_to_mesh
from case_prep.domain.sdf import (
    SdfGrid,
    op_difference,
    op_intersection,
    op_smooth_union,
    op_union,
    sdf_cylinder,
)

_OPS = {"union": op_union, "intersection": op_intersection, "difference": op_difference}


def mesh_boolean(mesh_a, mesh_b, op: str, pitch: float = 0.3, pad: int = 3):
    """Boolean of TWO meshes via SDF-CSG on a shared grid. ``op`` is 'union',
    'intersection', or 'difference' (a minus b). Robust to non-watertight inputs."""
    if op not in _OPS:
        raise ValueError(f"unknown op {op!r}; expected one of {sorted(_OPS)}")
    ga = mesh_to_sdf(mesh_a, pitch)
    gb = mesh_to_sdf(mesh_b, pitch)
    bounds = np.array([
        np.minimum(mesh_a.bounds[0], mesh_b.bounds[0]),
        np.maximum(mesh_a.bounds[1], mesh_b.bounds[1]),
    ])
    grid = SdfGrid.from_bounds(bounds, pitch, pad)
    va = resample_sdf(ga, grid.coords)
    vb = resample_sdf(gb, grid.coords)
    return sdf_to_mesh(grid.with_values(_OPS[op](va, vb)))


def screw_channel(mesh, position, axis, radius: float, length: float, pitch: float = 0.2):
    """Bore the screw-access channel: subtract a cylinder along the implant axis."""
    grid = mesh_to_sdf(mesh, pitch)
    channel = sdf_cylinder(grid, position, axis, radius, length / 2.0)
    return sdf_to_mesh(grid.with_values(op_difference(grid.values, channel)))


def add_abutment_post(mesh, position, axis, radius: float, length: float,
                      pitch: float = 0.2, smooth: float = 0.0):
    """Union an abutment post (analytic cylinder) onto the restoration. ``smooth`` > 0
    uses a smooth-min blend for an organic fillet that tolerates imperfect geometry."""
    grid = mesh_to_sdf(mesh, pitch, pad=int(length / pitch) + 4)
    post = sdf_cylinder(grid, position, axis, radius, length / 2.0)
    combined = op_smooth_union(grid.values, post, smooth) if smooth > 0 else op_union(grid.values, post)
    return sdf_to_mesh(grid.with_values(combined))


def offset_surface(mesh, distance: float, pitch: float = 0.2):
    """Offset the surface outward (+) or inward (-) by ``distance`` — the basis of the
    cement-gap construction (offset then difference)."""
    grid = mesh_to_sdf(mesh, pitch, pad=int(abs(distance) / pitch) + 4)
    return sdf_to_mesh(grid.with_values(grid.values - distance))
