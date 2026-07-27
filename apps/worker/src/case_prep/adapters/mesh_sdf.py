"""Mesh <-> SDF bridge (uses trimesh + scipy). Kept out of the domain so the SDF math
stays dependency-light.

mesh_to_sdf is deliberately ROBUST to non-watertight input: it voxelizes the surface,
closes sub-voxel gaps by a 1-voxel dilation, then flood-fills the exterior from the grid
border. Anything the exterior can't reach is interior. A hole the flood-fill can't leak
through is bridged — which is why this tolerates the holey, degenerate meshes that crack
naive mesh booleans.
"""
from __future__ import annotations

import numpy as np
import trimesh
from scipy import ndimage

from case_prep.domain.sdf import SdfGrid, extract_surface


def mesh_to_sdf(mesh: trimesh.Trimesh, pitch: float, pad: int = 3) -> SdfGrid:
    vox = mesh.voxelized(pitch)
    surface = np.pad(np.asarray(vox.matrix, dtype=bool), pad, constant_values=False)
    origin = np.asarray(vox.transform)[:3, 3] - pad * pitch

    # Close holes in the surface SHELL (dilate+erode) so the flood-fill can't leak
    # through them — without thickening the solid. Distances are still measured to the
    # ORIGINAL surface, so there is no net inflation: robust AND accurate.
    closed_surface = ndimage.binary_closing(surface, iterations=2)
    empty = ~closed_surface
    labels, _ = ndimage.label(empty)
    border = np.concatenate([
        labels[0, :, :].ravel(), labels[-1, :, :].ravel(),
        labels[:, 0, :].ravel(), labels[:, -1, :].ravel(),
        labels[:, :, 0].ravel(), labels[:, :, -1].ravel(),
    ])
    exterior_labels = set(int(x) for x in np.unique(border) if x != 0)
    exterior = np.isin(labels, list(exterior_labels)) if exterior_labels else np.zeros_like(empty)
    filled = ~exterior  # solid occupancy: interior + surface (incl. bridged holes)

    # SDF from occupancy: distance-out minus distance-in. The zero crossing sits cleanly
    # BETWEEN filled and empty cells (not on cell centres), so marching cubes is watertight.
    # Boundary voxels straddle the true surface, biasing the solid ~half a voxel large;
    # add 0.5*pitch to pull the zero level back to the true surface.
    signed = (ndimage.distance_transform_edt(~filled) - ndimage.distance_transform_edt(filled)) * pitch
    signed = signed + 0.5 * pitch
    # The EDT field is quantised to voxel steps; iso-surfaces at non-zero levels (offsets,
    # channel walls) would cut through coincident cells and produce degenerate marching
    # cubes. A sub-voxel Gaussian smooths the staircase so any iso-level extracts cleanly.
    signed = ndimage.gaussian_filter(signed, sigma=1.0)

    nx, ny, nz = surface.shape
    ax = origin[0] + np.arange(nx) * pitch
    ay = origin[1] + np.arange(ny) * pitch
    az = origin[2] + np.arange(nz) * pitch
    gx, gy, gz = np.meshgrid(ax, ay, az, indexing="ij")
    coords = np.stack([gx, gy, gz], axis=-1)
    return SdfGrid(coords=coords, pitch=pitch, values=signed)


def resample_sdf(source: SdfGrid, target_coords: np.ndarray, outside: float = 1e3) -> np.ndarray:
    """Trilinearly resample a source SDF onto arbitrary target world coords. Cells outside
    the source grid read as ``outside`` (a large positive = exterior), so two meshes with
    different extents can be combined on one common grid."""
    idx = (target_coords - source.origin) / source.pitch  # (...,3) float indices
    coords_idx = np.moveaxis(idx, -1, 0)  # (3, ...)
    return ndimage.map_coordinates(
        source.values, coords_idx, order=1, mode="constant", cval=outside
    )


def sdf_to_mesh(grid: SdfGrid) -> trimesh.Trimesh:
    verts, faces = extract_surface(grid)
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    mesh.fix_normals()
    return mesh
