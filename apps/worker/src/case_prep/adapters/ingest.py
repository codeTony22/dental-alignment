"""Real-file ingest: normalize a raw scan into the occlusal-up, centred frame the
pipeline assumes, and gate implausible scale. Synthetic cases are already z-up; real
intraoral STLs arrive in arbitrary orientation, so this is the bridge for real data.
"""
from __future__ import annotations

from pathlib import Path
from typing import Tuple

import numpy as np
import trimesh

from case_prep.domain.geometry import RigidTransform

ARCH_SPAN_LO_MM = 40.0
ARCH_SPAN_HI_MM = 80.0


def _principal_frame(points: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Return (centroid, eigenvectors) with eigenvectors sorted by DESCENDING variance."""
    centroid = points.mean(axis=0)
    cov = np.cov((points - centroid).T)
    vals, vecs = np.linalg.eigh(cov)
    order = np.argsort(vals)[::-1]  # largest spread first
    return centroid, vecs[:, order]


def normalize_orientation(mesh: trimesh.Trimesh) -> Tuple[trimesh.Trimesh, RigidTransform]:
    """Rotate so the thin (occlusal) axis -> +z with scan bodies pointing +z, centre at
    origin. Returns the normalized mesh and the rigid transform applied."""
    pts = np.asarray(mesh.vertices, float)
    centroid, axes = _principal_frame(pts)
    # axes[:,0],[:,1] = the two wide arch directions; axes[:,2] = thinnest = occlusal
    up = axes[:, 2]
    # orient up toward the protrusions (scan bodies): the side with the longer tail
    proj = (pts - centroid) @ up
    if proj.max() < -proj.min():
        up = -up
    x = axes[:, 0]
    y = np.cross(up, x)
    x = np.cross(y, up)  # re-orthogonalize
    rot = np.vstack([x / np.linalg.norm(x), y / np.linalg.norm(y), up / np.linalg.norm(up)])

    transform = RigidTransform.from_rotation(rot).compose(RigidTransform.from_translation(-centroid))
    out = mesh.copy()
    out.apply_transform(transform.matrix)
    return out, transform


def arch_span_mm(mesh: trimesh.Trimesh) -> float:
    """The larger horizontal extent — a proxy for arch width used by the scale gate."""
    ex = mesh.extents
    return float(sorted(ex)[-1])


def scale_ok(mesh: trimesh.Trimesh, lo: float = ARCH_SPAN_LO_MM, hi: float = ARCH_SPAN_HI_MM) -> bool:
    return lo <= arch_span_mm(mesh) <= hi


def canonicalize_library(mesh: trimesh.Trimesh) -> Tuple[trimesh.Trimesh, RigidTransform]:
    """Centre a library scan-body mesh at the origin with its principal axes aligned, and
    return (local mesh, local->world placement). Registration assumes the library is in this
    canonical frame; real library/CAD/segmented meshes arrive in arbitrary world frames, so
    they must be canonicalized first (a real Certain scan body in world coords
    otherwise sends ICP ~its-offset off-target)."""
    v = np.asarray(mesh.vertices, float)
    centroid = v.mean(axis=0)
    centred = v - centroid
    _, _, vt = np.linalg.svd(centred, full_matrices=False)
    # IDEMPOTENCE: canonicalization is a projection — an already-canonical mesh (centred at the
    # origin, principal axes on the coordinate axes, largest spread on z) must return UNCHANGED.
    # SVD eigenvector signs are arbitrary, so re-deriving the frame for such a mesh can flip
    # axes and rotate the part (measured: an 11 mm vertex shift on the real vendor CAD),
    # silently breaking any caller that canonicalizes defensively (e.g. the cap library).
    # Recognising the fixed point keeps the (validated) frame convention untouched for every
    # first-time canonicalization.
    if (np.linalg.norm(centroid) < 1e-5
            and abs(vt[0][2]) > 1 - 1e-6    # largest-spread axis already on ±z
            and abs(vt[1][1]) > 1 - 1e-6    # mid on ±y
            and abs(vt[2][0]) > 1 - 1e-6):  # smallest on ±x
        return mesh.copy(), RigidTransform(np.eye(4))
    # Put the LARGEST-spread principal axis on local +z, to match the engine's convention
    # (it seeds the body axis = tallest spread). Mismatching this starts ICP ~90 deg off.
    r = vt[[2, 1, 0]]  # rows: smallest->x, mid->y, largest->z
    if np.linalg.det(r) < 0:
        r[0] = -r[0]  # keep a right-handed frame
    local = mesh.copy()
    local.vertices = (v - centroid) @ r.T  # local = r @ (v - centroid)
    placement = np.eye(4)
    placement[:3, :3] = r.T  # world = r.T @ local + centroid
    placement[:3, 3] = centroid
    return local, RigidTransform(placement)


def canonicalize_revolute(mesh: trimesh.Trimesh,
                          max_samples: int = 4000) -> Tuple[trimesh.Trimesh, RigidTransform]:
    """Canonicalize a ROTATIONAL part (healing cap): local +z = the rotational-SYMMETRY
    axis, open rim (the gingival side) facing DOWN. Returns (local mesh, local->world).

    Healing caps are squat — wider than tall — so ``canonicalize_library``'s tallest-PCA-axis
    convention puts a DIAMETER on +z, and every consumer of pose-z (the implant record's
    axis, cap-region removal, construction seating) inherits a sideways frame.

    AXIS SELECTION (client audit, 2026-07-15): manufacturer cap CADs are saved
    AXIS-ALIGNED (measured on the full catalog: revolution error about file-z 0.05-0.09,
    near-perfect) — and the previous PCA-candidate search TILTED every template off that
    axis (4.1 to 88.1 deg; the 6030s loaded fully SIDEWAYS), because the caps' large
    coded cutouts skew the covariance so much that NO principal axis is the symmetry
    axis. The saved file axis therefore joins the candidate set and WINS TIES: candidates
    = [file-z, the three principal axes], scored by trimmed multi-angle self-similarity
    (the revolute majority of the surface must map onto itself at EVERY rotation angle —
    a single 90-degree test near-tied on the cut parts), on deterministic area-uniform
    surface samples (vertex sampling over-weights the densely-tessellated cutout).
    File-z is preferred within a 10% score margin — a genuinely rotated file loses
    decisively and falls back to the search (see the spun-part test), while a
    convention-following file can never be un-aligned by candidate noise again."""
    from scipy.spatial import cKDTree

    v = np.asarray(mesh.vertices, float)
    centroid = v.mean(axis=0)
    centred = v - centroid
    _, _, vt = np.linalg.svd(centred, full_matrices=False)

    # deterministic area-uniform surface samples (local RNG: never disturbs the global
    # seed the pipeline pins for reproducibility)
    rng = np.random.default_rng(0)
    tri = np.asarray(mesh.triangles, float) - centroid
    areas = np.asarray(mesh.area_faces, float)
    if len(tri) and areas.sum() > 0:
        idx = rng.choice(len(tri), size=min(max_samples, 4000), p=areas / areas.sum())
        u = rng.random((len(idx), 1))
        w = rng.random((len(idx), 1))
        flip_uv = (u + w) > 1.0
        u[flip_uv] = 1.0 - u[flip_uv]
        w[flip_uv] = 1.0 - w[flip_uv]
        t = tri[idx]
        sub = t[:, 0] + u * (t[:, 1] - t[:, 0]) + w * (t[:, 2] - t[:, 0])
    else:  # degenerate surface — fall back to vertex subsampling
        sub = centred[:: max(1, len(centred) // max_samples)]
    # SCORING anchor = the area-sample mass centre, NOT the vertex centroid: dense
    # tessellation at the coded cutout drags the vertex centroid laterally OFF the
    # true axis line, and rotating about a parallel-but-displaced axis penalizes
    # every point (measured on 4020: file-z error 0.19 anchored at the vertex
    # centroid vs 0.05 at the mass centre — enough to flip the selection). The
    # canonical FRAME still centres at the vertex centroid as always (downstream
    # silhouette/dim conventions are calibrated on it); only the scoring moves.
    sub = sub - sub.mean(axis=0)
    sub_tree = cKDTree(sub)

    def revolution_error(candidate: np.ndarray) -> float:
        # trimmed (60%) mean self-distance under six rotation angles about `candidate`
        total = 0.0
        for ang_deg in (30.0, 60.0, 90.0, 120.0, 150.0, 180.0):
            r = trimesh.transformations.rotation_matrix(
                np.radians(ang_deg), candidate)[:3, :3]
            d = np.sort(sub_tree.query(sub @ r.T)[0])
            total += float(d[: int(len(d) * 0.6)].mean())
        return total / 6.0

    file_z = np.array([0.0, 0.0, 1.0])
    candidates = [file_z, vt[0], vt[1], vt[2]]
    errs = [revolution_error(a) for a in candidates]
    # the saved axis wins ties (10% margin): the convention carries information the
    # geometry of a heavily-cut part cannot recover on its own
    if errs[0] <= min(errs[1:]) * 1.10:
        axis = file_z
    else:
        axis = candidates[1 + int(np.argmin(errs[1:]))]

    def rim_mean_z(local_mesh: trimesh.Trimesh) -> float:
        outline = local_mesh.outline()
        if outline is None or not len(outline.entities):
            return -1.0  # watertight part: no rim evidence, keep the current sign
        pts = np.concatenate([np.asarray(d, float) for d in outline.discrete])
        return float(pts[:, 2].mean())

    # IDEMPOTENCE (same lesson as canonicalize_library): an already-canonical mesh must
    # return UNCHANGED — SVD signs are arbitrary and would spin/flip it on re-entry.
    # An accepted file-z axis lands here too (|axis[2]| = 1 exactly) once centred.
    if np.linalg.norm(centroid) < 1e-5 and abs(axis[2]) > 1 - 1e-6:
        if rim_mean_z(mesh) <= 0.0:
            return mesh.copy(), RigidTransform(np.eye(4))
        r = trimesh.transformations.rotation_matrix(np.pi, [1.0, 0.0, 0.0])[:3, :3]
    elif abs(axis[2]) > 1 - 1e-6:
        # the SAVED axis won: respect the whole saved frame — identity rotation (the
        # file's own x/y stay the in-plane directions), flip 180 about x only if the
        # open rim reads up. Deriving in-plane axes from PCA here would spin the part
        # by covariance noise on every reload for no benefit.
        r = np.eye(3)
        if rim_mean_z(trimesh.Trimesh(centred, mesh.faces.copy(),
                                      process=False)) > 0.0:
            r = trimesh.transformations.rotation_matrix(np.pi, [1.0, 0.0, 0.0])[:3, :3]
    else:
        # in-plane directions are a free parameter for a revolute part — take the two
        # remaining principal axes, orthogonalized against the symmetry axis
        rest = [a for a in vt if abs(float(a @ axis)) < 1 - 1e-9]
        x = rest[0] - (rest[0] @ axis) * axis
        x /= np.linalg.norm(x)
        r = np.vstack([x, np.cross(axis, x), axis])  # rows -> x, y, z(symmetry)
        if np.linalg.det(r) < 0:
            r[0] = -r[0]
        local_try = trimesh.Trimesh(centred @ r.T, mesh.faces.copy(), process=False)
        if rim_mean_z(local_try) > 0.0:  # rim up -> flip 180 about x
            r = trimesh.transformations.rotation_matrix(np.pi, [1.0, 0.0, 0.0])[:3, :3] @ r

    local = mesh.copy()
    local.vertices = centred @ r.T
    placement = np.eye(4)
    placement[:3, :3] = r.T
    placement[:3, 3] = centroid
    return local, RigidTransform(placement)


def load_raw_scan(path, normalize: bool = True) -> trimesh.Trimesh:
    """Load a real STL/PLY scan (no case.json) and optionally normalize its frame."""
    mesh = trimesh.load(Path(path), force="mesh")
    if normalize:
        mesh, _ = normalize_orientation(mesh)
    return mesh
