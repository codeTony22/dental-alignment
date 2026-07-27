"""Signed-distance-field CSG core — the robust boolean technique for the messy,
non-watertight meshes real intraoral scans produce (design 6.5).

Operands are combined as distance fields on a voxel grid (union=min, intersection=max,
difference=max(a,-b)); the surface is re-extracted with marching cubes. This is
intrinsically tolerant of holes/degeneracies because it never relies on consistent
mesh connectivity. Pure numpy + skimage — no trimesh, no IO (the mesh<->grid bridge
lives in adapters/mesh_sdf.py).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np


@dataclass(frozen=True)
class SdfGrid:
    """A regular voxel grid. ``coords`` is the (nx,ny,nz,3) world position of each cell;
    ``values`` (optional) is the (nx,ny,nz) signed distance, negative inside."""

    coords: np.ndarray
    pitch: float
    values: np.ndarray = None  # type: ignore[assignment]

    @property
    def shape(self) -> Tuple[int, int, int]:
        return self.coords.shape[:3]

    @property
    def origin(self) -> np.ndarray:
        return self.coords[0, 0, 0]

    @classmethod
    def from_bounds(cls, bounds: np.ndarray, pitch: float, pad: int = 3) -> "SdfGrid":
        bounds = np.asarray(bounds, dtype=float)
        lo = bounds[0] - pad * pitch
        hi = bounds[1] + pad * pitch
        axes = [np.arange(lo[i], hi[i] + pitch, pitch) for i in range(3)]
        gx, gy, gz = np.meshgrid(*axes, indexing="ij")
        coords = np.stack([gx, gy, gz], axis=-1)
        return cls(coords=coords, pitch=pitch)

    def with_values(self, values: np.ndarray) -> "SdfGrid":
        return SdfGrid(coords=self.coords, pitch=self.pitch, values=np.asarray(values, float))


def sdf_sphere(grid: SdfGrid, center, radius: float) -> np.ndarray:
    return np.linalg.norm(grid.coords - np.asarray(center, float), axis=-1) - radius


def sdf_cylinder(grid: SdfGrid, point, axis, radius: float, half_length: float) -> np.ndarray:
    """Finite cylinder centred at ``point``, along unit ``axis``. Exact SDF — used as the
    screw-access channel solid to subtract along the recovered implant axis."""
    a = np.asarray(axis, float)
    a = a / np.linalg.norm(a)
    rel = grid.coords - np.asarray(point, float)
    along = rel @ a  # signed distance along the axis
    radial_vec = rel - along[..., None] * a
    radial = np.linalg.norm(radial_vec, axis=-1)
    # 2D distance in (radial, axial) space to the cylinder's rectangle cross-section
    d_radial = radial - radius
    d_axial = np.abs(along) - half_length
    outside = np.sqrt(np.maximum(d_radial, 0) ** 2 + np.maximum(d_axial, 0) ** 2)
    inside = np.minimum(np.maximum(d_radial, d_axial), 0.0)
    return outside + inside


def op_union(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.minimum(a, b)


def op_intersection(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.maximum(a, b)


def op_difference(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """a minus b — keep a, carve out b."""
    return np.maximum(a, -b)


def op_smooth_union(a: np.ndarray, b: np.ndarray, k: float) -> np.ndarray:
    """Polynomial smooth-min (Inigo Quilez) — organic blends that tolerate imperfect
    scan geometry where hard mesh booleans crack (design 6.6)."""
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1 - h) + a * h - k * h * (1.0 - h)


def extract_surface(grid: SdfGrid) -> Tuple[np.ndarray, np.ndarray]:
    """Marching cubes at the zero level set -> (vertices in world coords, faces)."""
    from skimage import measure

    if grid.values is None:
        raise ValueError("grid has no values to extract a surface from")
    # Lewiner method (skimage default) is topologically correct; allow_degenerate=False
    # drops sliver triangles at sharp features (e.g. a screw-channel rim) that would
    # otherwise read as non-manifold.
    verts, faces, _normals, _vals = measure.marching_cubes(
        grid.values, level=0.0, allow_degenerate=False
    )
    # marching_cubes returns vertices in index space; map to world via origin + pitch
    world = grid.origin + verts * grid.pitch
    return world, faces
