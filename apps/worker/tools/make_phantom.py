"""PRINTED PHANTOM generator — the ground-truth-by-construction validation plate.

Ubiquitous language (matches ``docs/engagement/phantom-protocol.md``):
  * DESIGN FRAME — the coordinate system this file works in: origin at the plate's
    XY centroid, +z up, z=0 at the flat print face (the bottom).
  * SITE — one healing-cap placement: a real library template (``CapLibrary``,
    canonical frame: +z = axis, rim down) fused into the plate at a known pose.
  * SUBMERGENCE — how much of the cap's own flank a raised "gum" collar covers:
    exposed (collar stops at the rim, 0% covered), half (covers to mid-flank),
    deep (covers to 1mm below the cap's own top edge).
  * FIDUCIALS — 3 corner posts of distinct height+diameter, plus one chamfered
    (cut) corner, that let the evaluator recover the design frame from an
    arbitrary-orientation scan with no other information.

Geometry is built ENTIRELY from analytic SDF primitives (box, cylinder, half-space,
plane-wedge) plus the real cap CAD meshes (voxelized via the local ``_cap_sdf`` — the
``case_prep.adapters.mesh_sdf.mesh_to_sdf`` occupancy machinery with a
pitch-INDEPENDENT hole seal; see its docstring), unioned on one shared grid and
extracted once via marching cubes (``case_prep.domain.sdf.extract_surface``) — the
same SDF-CSG engine the production pipeline uses for boolean ops on messy scan
geometry (``src/case_prep/domain/sdf.py``, ``src/case_prep/adapters/mesh_sdf.py``,
``src/case_prep/adapters/booleans.py``), reused here (not modified) via its public
primitives plus a couple of small analytic SDFs (box, half-space, plane-wedge)
written locally because the box primitive does not exist in the read-only
``domain/sdf.py`` module.

DETERMINISM: every parameter below is a fixed literal (no RNG anywhere in this
file) — the plate design is the same every time by construction, which is a
strictly stronger guarantee than a seeded-RNG determinism, and gives byte-for-byte
identical vertices across runs trivially. No wall-clock touches any output.

Run as a CLI:
    cd apps/worker
    PYTHONWARNINGS=ignore .venv/bin/python tools/make_phantom.py \\
        --out-dir reports/phantom --voxel-mm 0.15 --n-sites 6

Or import ``generate_phantom`` directly (what tests do, and what
``evaluate_phantom.py`` imports geometry constants from).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import trimesh

from scipy import ndimage

from case_prep.adapters.cap_library import CapLibrary
from case_prep.adapters.mesh_sdf import resample_sdf
from case_prep.domain.cap_catalog import CapSpec
from case_prep.domain.geometry import RigidTransform
from case_prep.domain.sdf import SdfGrid, extract_surface, op_intersection, op_union, sdf_cylinder

WORKER_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIB_ROOT = WORKER_ROOT / "data" / "real" / "library" / "caps"
DEFAULT_OUT_DIR = WORKER_ROOT / "reports" / "phantom"

# ---------------------------------------------------------------------------------
# PLATE GEOMETRY (design frame: origin at plate XY centroid, z=0 = flat print face)
# ---------------------------------------------------------------------------------
PLATE_LEN_MM = 70.0   # X extent (length)
PLATE_WID_MM = 45.0   # Y extent (width)
PLATE_BASE_H_MM = 10.0  # flat slab height before the ridge bump

# The occlusal "ridge" a shallow bump running the plate's full length (X), modeled as
# a large-radius cylinder whose crest pokes RIDGE_AMP above the flat slab and tapers
# to zero at |y| = RIDGE_HALF_WIDTH — comparable curvature to a real arch ridge cross
# section, and trivially watertight (union of two exact analytic SDFs).
RIDGE_AMP_MM = 4.0
RIDGE_HALF_WIDTH_MM = 12.0
# Closed form for R such that the cylinder (radius R, centred RIDGE_AMP below the
# slab top at y=0) is exactly RIDGE_AMP proud at y=0 and exactly flush (0 proud) at
# y = +/- RIDGE_HALF_WIDTH: R - sqrt(R^2 - w^2) = amp  =>  R = (w^2 + amp^2) / (2*amp).
RIDGE_R_MM = (RIDGE_HALF_WIDTH_MM ** 2 + RIDGE_AMP_MM ** 2) / (2.0 * RIDGE_AMP_MM)
RIDGE_CENTER_Z_MM = PLATE_BASE_H_MM - RIDGE_R_MM + RIDGE_AMP_MM
RIDGE_AXIS = (1.0, 0.0, 0.0)  # runs along plate length

# 3 corner posts (DIFFERENT height+diameter each — the registration signature) plus
# one chamfered (cut) corner. Inset from the true footprint corners so the post
# cylinders sit fully within slab material, clear of the central ridge band.
FIDUCIAL_POSTS: List[Dict] = [
    {"corner": "A", "xy_mm": (27.0, 15.0), "diameter_mm": 3.0, "height_mm": 5.0},
    {"corner": "B", "xy_mm": (-27.0, 15.0), "diameter_mm": 4.0, "height_mm": 8.0},
    {"corner": "C", "xy_mm": (-27.0, -15.0), "diameter_mm": 5.0, "height_mm": 3.0},
]
# The 4th (true) plate corner is chamfered instead of getting a post: a 45-degree,
# 10mm-leg cut through the full plate thickness. `p0_xy_mm` is a point ON the cut
# line; `normal_xy` points OUTWARD (toward the corner being removed) so
# dot(xy - p0, normal) > 0 selects the wedge to carve away.
FIDUCIAL_CHAMFER: Dict = {
    "corner": "D",
    "plate_corner_xy_mm": (35.0, -22.5),
    "p0_xy_mm": (25.0, -22.5),
    "p1_xy_mm": (35.0, -12.5),  # the two endpoints of the cut line (unambiguous for sampling)
    "normal_xy": (0.7071067811865476, -0.7071067811865476),
    "leg_mm": 10.0,
}

# Embed the collar's bottom this far below the cap's own rim (along its axis) so it
# always fuses solidly into the ridge/slab regardless of a site's small tilt.
_COLLAR_EMBED_MM = 4.0
_COLLAR_MARGIN_MM = 1.8  # collar outer radius = cap's native rim radius + this
# Seat the cap's rim THIS far below the ridge/slab surface (along its axis) — a
# flush, knife-edge touching plane between the cap solid and the ridge/collar solid
# is not robust at print/scan voxel resolution: measured on the mini-plate (0.5mm
# voxel), a zero-overlap junction let marching-cubes reconstruct the cap's own
# UPPER portion as a topologically separate island, silently dropped by the
# largest-component debris cleanup (build_plate_solid) — i.e. the cap's crown was
# missing from the printable solid entirely. A small guaranteed volumetric overlap
# fixes the connection at its root, and is invisible from outside (it only buries
# material that was always going to be embedded near the base).
_RIM_EMBED_MM = 0.6

# ---------------------------------------------------------------------------------
# THE 6 DESIGNED SITES — two rows of three. Fixed literals (see module docstring):
# no RNG is needed for a deterministic phantom. `--n-sites` takes a prefix of this
# table for the fast mini-plate used in tests.
#
# `clock_deg` is the DESIGNED CLOCK ANGLE: the cap template is rotated by it about
# its own canonical axis BEFORE placement (see compute_site_pose), making rotation a
# ground-truth-by-construction quantity alongside position/tilt — the physical
# arbiter for the codes-vs-recess clocking-instrument conflict (auto_flow winner
# pass, 2026-07-20). The angles are deliberately spread and avoid 90-degree
# multiples (a near-4-fold top face could alias those); the one 0-degree site (s6)
# is the canonical-rotation reference.
# ---------------------------------------------------------------------------------
SITES: List[Dict] = [
    dict(site_id="s1", tooth=1, model="zimmer-4.5", variant="6020",
        y_mm=8.0, x_mm=-18.0, tilt_deg=0.0, tilt_theta_deg=0.0, clock_deg=117.0,
        submergence="exposed"),
    dict(site_id="s2", tooth=2, model="zimmer-4.5", variant="7030",
        y_mm=8.0, x_mm=0.0, tilt_deg=8.0, tilt_theta_deg=60.0, clock_deg=45.0,
        submergence="half"),
    dict(site_id="s3", tooth=3, model="neodent-gm", variant="6020",
        y_mm=8.0, x_mm=18.0, tilt_deg=0.0, tilt_theta_deg=0.0, clock_deg=190.0,
        submergence="deep"),
    dict(site_id="s4", tooth=4, model="neodent-gm", variant="6030",
        y_mm=-8.0, x_mm=-18.0, tilt_deg=8.0, tilt_theta_deg=150.0, clock_deg=260.0,
        submergence="exposed"),
    dict(site_id="s5", tooth=5, model="zimmer-4.5", variant="7020",
        y_mm=-8.0, x_mm=0.0, tilt_deg=4.0, tilt_theta_deg=210.0, clock_deg=331.0,
        submergence="half"),
    dict(site_id="s6", tooth=6, model="neodent-gm", variant="5030",
        y_mm=-8.0, x_mm=18.0, tilt_deg=0.0, tilt_theta_deg=0.0, clock_deg=0.0,
        submergence="deep"),
]
SUBMERGENCE_LEVELS = ("exposed", "half", "deep")


def submergence_fraction(level: str, height_mm: float) -> float:
    """Fraction of a cap's local rim->top height the collar rises to, by submergence
    level. 'deep' targets 1mm short of the cap's own top edge — the clinical limit
    (any less exposed and an operator could no longer identify/click the cap)."""
    if level == "exposed":
        return 0.0
    if level == "half":
        return 0.5
    if level == "deep":
        return max(0.0, (height_mm - 1.0) / height_mm)
    raise ValueError(f"unknown submergence level {level!r}; expected one of {SUBMERGENCE_LEVELS}")


# ---------------------------------------------------------------------------------
# Analytic SDF primitives not in the (read-only) domain/sdf.py primitive set.
# Same "outside + inside" exact-SDF style as domain.sdf.sdf_cylinder.
# ---------------------------------------------------------------------------------
def sdf_box(coords: np.ndarray, center, half_extents) -> np.ndarray:
    rel = coords - np.asarray(center, float)
    q = np.abs(rel) - np.asarray(half_extents, float)
    outside = np.linalg.norm(np.maximum(q, 0.0), axis=-1)
    inside = np.minimum(np.max(q, axis=-1), 0.0)
    return outside + inside


def sdf_half_space_above(coords: np.ndarray, z_level: float) -> np.ndarray:
    """Negative (inside) where z >= z_level, positive (outside) below it."""
    return z_level - coords[..., 2]


def sdf_plane_wedge(coords_xy: np.ndarray, p0_xy, normal_xy) -> np.ndarray:
    """Signed distance (full-height, no z dependency) to the chamfer cut plane:
    positive on the side being carved away."""
    p0 = np.asarray(p0_xy, float)
    n = np.asarray(normal_xy, float)
    return (coords_xy[..., 0] - p0[0]) * n[0] + (coords_xy[..., 1] - p0[1]) * n[1]


_CAP_SEAL_MM = 1.0  # pitch-INDEPENDENT closing distance for cap voxelization (below)


def _cap_sdf(posed: trimesh.Trimesh, pitch: float) -> "SdfGrid":
    """Occupancy SDF of a posed cap with a PITCH-INDEPENDENT hole seal.

    The library cap CADs are holey (592 open boundary edges on the 6020, spread over
    the full z-range incl. the ~1.4mm bore mouth). ``mesh_to_sdf``'s flood-fill seal
    is a fixed 2-VOXEL closing: at the 0.5mm test pitch that is a 1.0mm reach and the
    holes seal, but at print pitch the same 2 voxels reach only 0.3mm — the exterior
    flood LEAKS INTO the cap through the bore mouth, the crown reads as a one-voxel
    shell, and the +0.5*pitch offset plus Gaussian smoothing then erases it from the
    extracted solid entirely (measured: the zimmer 6020's code band carried 116
    vertices at 0.2mm vs 474 for the collar-buried copy of the same CAD — the
    exposed crown was simply NOT THERE, on the printable plate). This helper is
    mesh_to_sdf with one change: closing iterations = ceil(_CAP_SEAL_MM / pitch), so
    the sealed distance is the SAME physical ~1mm at every pitch — identical to
    mesh_to_sdf at the validated 0.5mm test pitch (2 iterations) by construction.
    Coded-relief dips are open concavities, not through-holes: the closing's erosion
    restores them (verified by the instrument-at-truth probe at 0.15/0.2mm)."""
    iterations = max(2, int(np.ceil(_CAP_SEAL_MM / pitch)))
    vox = posed.voxelized(pitch)
    pad = iterations + 1  # the dilation must never touch the grid border
    surface = np.pad(np.asarray(vox.matrix, dtype=bool), pad, constant_values=False)
    origin = np.asarray(vox.transform)[:3, 3] - pad * pitch

    closed_surface = ndimage.binary_closing(surface, iterations=iterations)
    empty = ~closed_surface
    labels, _ = ndimage.label(empty)
    border = np.concatenate([
        labels[0, :, :].ravel(), labels[-1, :, :].ravel(),
        labels[:, 0, :].ravel(), labels[:, -1, :].ravel(),
        labels[:, :, 0].ravel(), labels[:, :, -1].ravel(),
    ])
    exterior_labels = set(int(x) for x in np.unique(border) if x != 0)
    exterior = np.isin(labels, list(exterior_labels)) if exterior_labels else np.zeros_like(empty)
    filled = ~exterior

    signed = (ndimage.distance_transform_edt(~filled)
              - ndimage.distance_transform_edt(filled)) * pitch
    signed = signed + 0.5 * pitch
    signed = ndimage.gaussian_filter(signed, sigma=1.0)

    nx, ny, nz = surface.shape
    ax = origin[0] + np.arange(nx) * pitch
    ay = origin[1] + np.arange(ny) * pitch
    az = origin[2] + np.arange(nz) * pitch
    gx, gy, gz = np.meshgrid(ax, ay, az, indexing="ij")
    coords = np.stack([gx, gy, gz], axis=-1)
    return SdfGrid(coords=coords, pitch=pitch, values=signed)


def ridge_top_z(y_mm: float) -> float:
    """Design-frame z of the plate's top surface at a given y (0 = flat slab)."""
    y = float(y_mm)
    if abs(y) > RIDGE_HALF_WIDTH_MM:
        return PLATE_BASE_H_MM
    return RIDGE_CENTER_Z_MM + float(np.sqrt(max(RIDGE_R_MM ** 2 - y ** 2, 0.0)))


def load_cap_libraries(lib_root: "Path | str" = DEFAULT_LIB_ROOT) -> Dict[str, CapLibrary]:
    root = Path(lib_root)
    models = sorted({s["model"] for s in SITES})
    return {m: CapLibrary.load(root / m) for m in models}


def _radius_at_local_z(template: trimesh.Trimesh, z: float, band_mm: float = 0.4) -> float:
    """Radial extent of the template's OWN surface at local height ``z`` (a thin
    z-band, widening until enough vertices are caught) — used to aim the operator's
    border clicks at the ACTUAL visible cap boundary for a given submergence level
    (a taller/shorter collar exposes a different, not-necessarily-rim-diameter, band
    of the cap), rather than assuming every submergence shows the same radius."""
    v = np.asarray(template.vertices, float)
    band = band_mm
    for _ in range(6):
        sel = v[np.abs(v[:, 2] - z) < band]
        if len(sel) >= 12:
            return float(np.percentile(np.linalg.norm(sel[:, :2], axis=1), 90))
        band *= 1.8
    # degenerate fallback: nearest few vertices by |z-target|
    idx = np.argsort(np.abs(v[:, 2] - z))[:12]
    return float(np.percentile(np.linalg.norm(v[idx, :2], axis=1), 90))


def _visible_ring_points_local(template: trimesh.Trimesh, z_local: float, n: int = 4,
                               z_band: float = 0.3) -> np.ndarray:
    """``n`` REAL mesh points near local height ``z_local``, one per angular sector,
    each the sector's OWN widest point (not a uniform-radius circle). These caps are
    NOT rotationally symmetric at a given height (a coded flat/cutout feature can
    leave one side's silhouette 1-2mm narrower than the opposite side — measured on
    zimmer-4.5-6020 at its flare: 1.5-2.4mm on one side vs 3.1mm on the other) — a
    border-click gesture that assumes a perfect circle aims THROUGH empty space on
    the narrow sides, and a raycast-style snap then jumps to whatever real geometry
    is nearest, which is often a different height entirely. Real mesh points are
    used directly as the click AIM so the synthesized gesture — like a real one —
    always aims at material that is actually there."""
    v = np.asarray(template.vertices, float)
    pts = []
    for k in range(n):
        target = k * 360.0 / n
        band = z_band
        found = None
        for _ in range(6):
            sel = v[np.abs(v[:, 2] - z_local) < band]
            if len(sel):
                ang = np.degrees(np.arctan2(sel[:, 1], sel[:, 0])) % 360.0
                d = np.abs(((ang - target + 180.0) % 360.0) - 180.0)
                sector = sel[d < (180.0 / n)]
                if len(sector) >= 3:
                    r = np.linalg.norm(sector[:, :2], axis=1)
                    found = sector[np.argmax(r)]
                    break
            band *= 1.6
        if found is None:
            ang_all = np.degrees(np.arctan2(v[:, 1], v[:, 0])) % 360.0
            d_all = np.abs(((ang_all - target + 180.0) % 360.0) - 180.0)
            dz = np.abs(v[:, 2] - z_local)
            score = d_all / 45.0 + dz / max(z_band, 0.1)
            found = v[np.argmin(score)]
        pts.append(found)
    return np.array(pts)


def _flare_peak_local_z(template: trimesh.Trimesh, n_bins: int = 60) -> Tuple[float, float]:
    """The height of the cap's own natural WIDEST visible point ('these caps FLARE at
    the emergence' — auto_flow._rim_seat). This is the correct border-click target for
    a fully EXPOSED cap (nothing covers it, a real operator clicks the widest visible
    ring — exactly what the production rim seat's pinned-depth search resolves to: it
    walks DOWN from the top and stops at the first/highest bin at least as wide as the
    click, so a click below the true flare peak is systematically mis-resolved UP to
    it). Returns (local_z, radius_mm) of the peak."""
    v = np.asarray(template.vertices, float)
    z_rim, z_top = float(v[:, 2].min()), float(v[:, 2].max())
    best_z, best_r = z_rim, 0.0
    for z in np.linspace(z_rim, z_top, n_bins):
        r = _radius_at_local_z(template, float(z), band_mm=0.25)
        if r > best_r:
            best_z, best_r = float(z), r
    return best_z, best_r


def compute_site_pose(site: Dict, template: trimesh.Trimesh, rim_radius_mm: float) -> Dict:
    """The DESIGN pose + derived geometry for one site: local canonical template frame
    -> design/world frame (SAME convention ``run_auto_case`` produces — the template
    is already canonicalized by ``CapLibrary.load``: +z axis, rim at local min-z)."""
    v = np.asarray(template.vertices, float)
    z_rim, z_top = float(v[:, 2].min()), float(v[:, 2].max())
    height_mm = z_top - z_rim

    tilt_axis = [np.cos(np.radians(site["tilt_theta_deg"])),
                np.sin(np.radians(site["tilt_theta_deg"])), 0.0]
    tilt = RigidTransform.from_axis_angle(tilt_axis, site["tilt_deg"])
    clock = RigidTransform.from_axis_angle([0.0, 0.0, 1.0], site["clock_deg"])
    R = tilt.rotation @ clock.rotation  # clock about the local axis first, then tilt
    axis_world = R @ np.array([0.0, 0.0, 1.0])

    # embed the rim slightly below the nominal ridge surface — see _RIM_EMBED_MM
    target_rim = np.array([site["x_mm"], site["y_mm"],
                           ridge_top_z(site["y_mm"]) - _RIM_EMBED_MM])
    t = target_rim - R @ np.array([0.0, 0.0, z_rim])
    pose = np.eye(4)
    pose[:3, :3] = R
    pose[:3, 3] = t

    rim_world = R @ np.array([0.0, 0.0, z_rim]) + t
    top_world = R @ np.array([0.0, 0.0, z_top]) + t

    frac = submergence_fraction(site["submergence"], height_mm)
    collar_top_local_z = z_rim + frac * (z_top - z_rim)
    collar_top_world = rim_world + frac * (top_world - rim_world)
    collar_bottom_world = rim_world - _COLLAR_EMBED_MM * axis_world

    # The collar must stay SNUG against the cap's own (roughly rim->flare monotonic
    # non-decreasing) radius profile at the height it actually covers, not the
    # template's overall NATIVE diameter (measured near the wider flare, well above
    # the rim for most variants) — a constant collar radius that oversizes the
    # bottom band buries the true rim edge under a wider, misleading boundary that a
    # click aimed at the true rim (or an ICP correspondence) would wrongly land on,
    # biasing the recovered seat depth (measured during protocol validation: an
    # oversized collar at an 'exposed' site read a ~2.5mm systematic depth bias).
    visible_radius_mm = _radius_at_local_z(template, collar_top_local_z)
    collar_radius_mm = visible_radius_mm + _COLLAR_MARGIN_MM

    # The OPERATOR'S CLICK TARGET is a separate concern from the collar's own
    # geometry. For a covered site (half/deep) the doctor can only see the tissue
    # line itself — its own true local radius, exactly what the collar above uses.
    # For an EXPOSED cap nothing covers it, so a real operator clicks the cap's own
    # widest visible ring (the flare) wherever it naturally occurs — which is also
    # the ONLY click height a fully-exposed cap's local radius could be, that the
    # production pinned-seat's "walk down from the top, stop at the first bin at
    # least this wide" convention resolves correctly (measured: clicking the true
    # bottom RIM of an exposed cap, whose own radius is smaller than the flare
    # above it, gets walked UP to the flare and mis-seats by the height difference,
    # ~2.5-3.3mm on these variants — a real characteristic of that production
    # convention, not a phantom-design defect, and the reason the ~50um-tolerance
    # phantom is worth building: it is EXACTLY the kind of gap truth-known geometry
    # exposes).
    if site["submergence"] == "exposed":
        click_z, click_r = _flare_peak_local_z(template)
    else:
        click_z, click_r = collar_top_local_z, visible_radius_mm
    click_world = R @ np.array([0.0, 0.0, click_z]) + t
    ring_local = _visible_ring_points_local(template, click_z, n=4)
    ring_world = ring_local @ R.T + t

    return dict(
        pose=pose, height_mm=height_mm, z_rim_local=z_rim, z_top_local=z_top,
        rim_world=rim_world, top_world=top_world, axis_world=axis_world,
        collar_top_world=collar_top_world, collar_bottom_world=collar_bottom_world,
        collar_radius_mm=collar_radius_mm, collar_top_local_z=collar_top_local_z,
        visible_rim_center_world=click_world, visible_rim_radius_mm=click_r,
        rim_ring_world=ring_world,
    )


def build_plate_solid(n_sites: int, voxel_mm: float,
                      lib_root: "Path | str" = DEFAULT_LIB_ROOT
                      ) -> Tuple[trimesh.Trimesh, List[Dict]]:
    """Build the fused phantom plate solid + per-site design records. Union order:
    analytic base slab+ridge -> analytic posts -> analytic chamfer cut -> per-site
    (analytic collar + voxelized cap template), each on ONE shared grid, extracted
    once. Cap screw bores close under the SDF closing/occupancy machinery — expected
    and harmless (the scan can never see a bore either)."""
    if not (1 <= n_sites <= len(SITES)):
        raise ValueError(f"n_sites must be in [1, {len(SITES)}], got {n_sites}")
    sites = SITES[:n_sites]
    libs = load_cap_libraries(lib_root)

    pad_xy = 4.0
    pad_z = 1.5
    top_z = PLATE_BASE_H_MM + RIDGE_AMP_MM + 12.0  # headroom for the tallest post + cap
    bounds = np.array([
        [-PLATE_LEN_MM / 2 - pad_xy, -PLATE_WID_MM / 2 - pad_xy, -pad_z],
        [PLATE_LEN_MM / 2 + pad_xy, PLATE_WID_MM / 2 + pad_xy, top_z],
    ])
    grid = SdfGrid.from_bounds(bounds, pitch=voxel_mm, pad=2)

    acc = sdf_box(grid.coords, [0.0, 0.0, PLATE_BASE_H_MM / 2.0],
                 [PLATE_LEN_MM / 2.0, PLATE_WID_MM / 2.0, PLATE_BASE_H_MM / 2.0])
    ridge = sdf_cylinder(grid, [0.0, 0.0, RIDGE_CENTER_Z_MM], RIDGE_AXIS,
                         RIDGE_R_MM, PLATE_LEN_MM / 2.0)
    ridge_capped = op_intersection(ridge, sdf_half_space_above(grid.coords, PLATE_BASE_H_MM))
    acc = op_union(acc, ridge_capped)

    for p in FIDUCIAL_POSTS:
        post = sdf_cylinder(grid, [p["xy_mm"][0], p["xy_mm"][1],
                                   PLATE_BASE_H_MM + p["height_mm"] / 2.0],
                            [0.0, 0.0, 1.0], p["diameter_mm"] / 2.0, p["height_mm"] / 2.0)
        acc = op_union(acc, post)

    wedge = sdf_plane_wedge(grid.coords, FIDUCIAL_CHAMFER["p0_xy_mm"], FIDUCIAL_CHAMFER["normal_xy"])
    acc = np.maximum(acc, wedge)  # carve the chamfer wedge away from EVERYTHING built so far

    records: List[Dict] = []
    for site in sites:
        lib = libs[site["model"]]
        spec = CapSpec(site["model"], site["variant"])
        template = lib.template(spec)
        rim_radius_mm = lib.variant_dimensions()[site["variant"]][0] / 2.0

        geo = compute_site_pose(site, template, rim_radius_mm)
        collar_half_len = float(np.linalg.norm(
            geo["collar_top_world"] - geo["collar_bottom_world"]) / 2.0)
        collar_mid = (geo["collar_top_world"] + geo["collar_bottom_world"]) / 2.0
        collar = sdf_cylinder(grid, collar_mid, geo["axis_world"],
                              geo["collar_radius_mm"], collar_half_len)
        acc = op_union(acc, collar)

        posed = template.copy()
        posed.apply_transform(geo["pose"])
        # NOT mesh_to_sdf: its fixed 2-voxel hole seal is pitch-dependent and lets
        # the flood-fill hollow out the cap crown at print pitch — see _cap_sdf
        cap_grid = _cap_sdf(posed, voxel_mm)
        cap_res = resample_sdf(cap_grid, grid.coords)
        acc = op_union(acc, cap_res)

        records.append(dict(site=site, rim_radius_mm=rim_radius_mm, **geo))

    verts, faces = extract_surface(grid.with_values(acc))
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    mesh.fix_normals()

    # Marching-cubes on this shared grid does not always weld every part into ONE
    # connected component. Two distinct causes were measured during validation:
    # (a) genuine sub-voxel debris — a handful of micro-shells (single-digit to a
    #     few dozen vertices), spawned by trilinear-resampling a cap's sharp
    #     screw-bore rim / coded-cutout edges onto the coarser shared grid; and
    # (b) a REAL cap fragment: the library CAD's own coded cutout (an
    #     anti-rotation slot cutting deep into the part) can leave a near-knife-edge
    #     wall at typical print/scan voxel pitch that marching cubes resolves as
    #     topologically separate from the rest of the cap — measured on
    #     zimmer-4.5-6020 at 0.5mm AND at the fine 0.15mm print pitch alike (a
    #     property of the CAD, not the voxel size). Silently keeping only the
    #     largest component (an earlier version of this tool did) DISCARDS that
    #     fragment — the cap's own crown was missing from the printable solid,
    #     which also broke every downstream measurement of it.
    #
    # The fix: keep every individually-watertight component (dropping only true
    # zero-volume slivers) as a multi-shell mesh. This is a normal, printable SLA
    # artifact — the fragments spatially overlap/touch the main body (measured: the
    # 'disconnected' fragment's z-range overlapps the main body's by >0mm, i.e. they
    # are not floating apart) and fuse during resin exposure even where the DIGITAL
    # mesh's marching-cubes topology drew the line between them. ``is_watertight``
    # is still checked and required on the assembled result: multiple watertight
    # shells concatenated (no vertex welding across components) remain watertight
    # by trimesh's own definition (a manifold check per edge, not a connectivity
    # requirement) — verified empirically and by the generator test.
    parts = [p for p in mesh.split(only_watertight=True) if p.volume > 1e-6]
    if not parts:
        raise RuntimeError("phantom solid failed to extract any watertight component")
    combined = trimesh.util.concatenate(parts) if len(parts) > 1 else parts[0]
    if not combined.is_watertight:
        raise RuntimeError("phantom plate is not watertight after debris cleanup")
    return combined, records


def build_reference_cloud(truth: Dict, lib_root: "Path | str" = DEFAULT_LIB_ROOT,
                          top_spacing_mm: float = 1.2, n_cap_samples: int = 1500
                          ) -> np.ndarray:
    """Reconstruct a design-frame point cloud PURELY from ``truth`` (the ground-truth
    dict/JSON) plus the real cap library — no dependency on the printed/pristine STL,
    which the evaluator never has. Used as the trimmed-ICP registration target: plate
    top surface (box + ridge) and bottom plane, the 3 fiducial posts, the chamfer cut
    face, and each site's cap template sampled at its DESIGNED pose."""
    plate = truth["plate"]
    length_mm, width_mm = plate["footprint_mm"]
    base_h = plate["base_height_mm"]
    ridge = plate["ridge"]

    def ridge_z(y: np.ndarray) -> np.ndarray:
        y = np.asarray(y, float)
        z = np.full_like(y, base_h)
        inside = np.abs(y) <= ridge["half_width_mm"]
        z[inside] = ridge["center_z_mm"] + np.sqrt(
            np.maximum(ridge["radius_mm"] ** 2 - y[inside] ** 2, 0.0))
        return z

    xs = np.arange(-length_mm / 2, length_mm / 2 + 1e-6, top_spacing_mm)
    ys = np.arange(-width_mm / 2, width_mm / 2 + 1e-6, top_spacing_mm)
    gx, gy = np.meshgrid(xs, ys, indexing="ij")
    top = np.stack([gx, gy, ridge_z(gy.ravel()).reshape(gx.shape)], axis=-1).reshape(-1, 3)
    bottom = np.stack([gx, gy, np.zeros_like(gx)], axis=-1).reshape(-1, 3)

    fid = truth["fiducials"]
    for p in fid["posts"]:
        keep_r = p["diameter_mm"] / 2.0 + 0.5
        top = top[np.linalg.norm(top[:, :2] - np.array(p["xy_mm"]), axis=1) > keep_r]
        bottom = bottom[np.linalg.norm(bottom[:, :2] - np.array(p["xy_mm"]), axis=1) > keep_r]

    ch = fid["chamfer"]
    n = np.array(ch["normal_xy"])
    p0 = np.array(ch["p0_xy_mm"])

    def outside_wedge(P: np.ndarray) -> np.ndarray:
        return ((P[:, 0] - p0[0]) * n[0] + (P[:, 1] - p0[1]) * n[1]) <= 0.0

    top = top[outside_wedge(top)]
    bottom = bottom[outside_wedge(bottom)]

    clouds = [top, bottom]
    for p in fid["posts"]:
        r, h = p["diameter_mm"] / 2.0, p["height_mm"]
        theta = np.linspace(0.0, 2 * np.pi, 24, endpoint=False)
        zs = np.linspace(base_h, base_h + h, 6)
        side = np.array([[p["xy_mm"][0] + r * np.cos(t), p["xy_mm"][1] + r * np.sin(t), z]
                         for z in zs for t in theta])
        rhos = np.linspace(0.0, r, 4)
        top_disk = np.array([[p["xy_mm"][0] + rho * np.cos(t), p["xy_mm"][1] + rho * np.sin(t),
                              base_h + h] for rho in rhos for t in theta])
        clouds.append(side)
        clouds.append(top_disk)

    p1 = np.array(ch["p1_xy_mm"])
    cut = np.array([[*(p0 + (p1 - p0) * tt), z]
                    for tt in np.linspace(0.0, 1.0, 12) for z in np.linspace(0.0, base_h, 8)])
    clouds.append(cut)

    libs = load_cap_libraries(lib_root)
    # trimesh.sample.sample_surface draws from numpy's GLOBAL RNG: pin the seed for a
    # deterministic reference cloud, restoring the ambient state afterwards (the
    # save/seed/restore pattern of domain.clock_signature.template_signature).
    state = np.random.get_state()
    try:
        np.random.seed(0)
        for s in truth["sites"]:
            template = libs[s["model"]].template(CapSpec(s["model"], s["variant"]))
            sampled, _ = trimesh.sample.sample_surface(template, n_cap_samples)
            pose = np.asarray(s["pose"], float)
            clouds.append(np.asarray(sampled, float) @ pose[:3, :3].T + pose[:3, 3])
    finally:
        np.random.set_state(state)

    return np.concatenate(clouds, axis=0)


def _preview_png(mesh: trimesh.Trimesh, records: List[Dict], path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    v = np.asarray(mesh.vertices, float)
    step = max(1, len(v) // 20000)
    vs = v[::step]

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    views = [("Top (XY)", 0, 1), ("Front (XZ)", 0, 2), ("Side (YZ)", 1, 2)]
    for ax, (title, i, j) in zip(axes, views):
        ax.scatter(vs[:, i], vs[:, j], s=0.3, c="#888888", alpha=0.5)
        for r in records:
            c = r["rim_world"]
            ax.scatter([c[i]], [c[j]], s=30, c="crimson")
            ax.annotate(r["site"]["site_id"], (c[i], c[j]), fontsize=7)
        for p in FIDUCIAL_POSTS:
            xyz = (p["xy_mm"][0], p["xy_mm"][1], PLATE_BASE_H_MM + p["height_mm"])
            ax.scatter([xyz[i]], [xyz[j]], s=25, c="royalblue", marker="^")
        ax.set_title(title)
        ax.set_aspect("equal")
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def generate_phantom(out_dir: "Path | str" = DEFAULT_OUT_DIR, voxel_mm: float = 0.15,
                     n_sites: int = 6, lib_root: "Path | str" = DEFAULT_LIB_ROOT
                     ) -> Dict:
    """Build the phantom plate + write ``phantom-plate.stl``,
    ``phantom-ground-truth.json`` and a preview PNG under ``out_dir``. Returns the
    ground-truth dict (also what gets written to JSON)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    mesh, records = build_plate_solid(n_sites=n_sites, voxel_mm=voxel_mm, lib_root=lib_root)

    stl_path = out / "phantom-plate.stl"
    mesh.export(stl_path)

    truth = {
        "design_frame": {
            "description": "origin at the plate's XY centroid; +z up; z=0 is the "
                            "flat print face (bottom).",
            "up_axis": [0.0, 0.0, 1.0],
        },
        "plate": {
            "footprint_mm": [PLATE_LEN_MM, PLATE_WID_MM],
            "base_height_mm": PLATE_BASE_H_MM,
            "ridge": {
                "amplitude_mm": RIDGE_AMP_MM, "half_width_mm": RIDGE_HALF_WIDTH_MM,
                "radius_mm": RIDGE_R_MM, "center_z_mm": RIDGE_CENTER_Z_MM,
                "axis": list(RIDGE_AXIS),
            },
        },
        "fiducials": {
            "posts": FIDUCIAL_POSTS,
            "chamfer": FIDUCIAL_CHAMFER,
        },
        "sites": [
            {
                "site_id": r["site"]["site_id"],
                "tooth": r["site"]["tooth"],
                "model": r["site"]["model"],
                "variant": r["site"]["variant"],
                "label": f"{r['site']['model']}-{r['site']['variant']}",
                "submergence": r["site"]["submergence"],
                "tilt_deg": r["site"]["tilt_deg"],
                # the designed clock angle (rotation about the cap's own canonical
                # axis, applied before tilt — see compute_site_pose): rotation truth
                "clock_deg": r["site"]["clock_deg"],
                "pose": r["pose"].tolist(),
                "height_mm": r["height_mm"],
                "rim_world": r["rim_world"].tolist(),
                "top_world": r["top_world"].tolist(),
                "axis_world": r["axis_world"].tolist(),
                "rim_radius_mm": r["rim_radius_mm"],
                "collar_radius_mm": r["collar_radius_mm"],
                "collar_top_world": r["collar_top_world"].tolist(),
                "visible_rim_center_world": r["visible_rim_center_world"].tolist(),
                "visible_rim_radius_mm": r["visible_rim_radius_mm"],
                # 4 REAL mesh points near the visible-rim height, one per angular
                # sector — the border-click aim targets (see _visible_ring_points_local:
                # these caps are not rotationally symmetric at a given height, so a
                # uniform-radius circle can aim through empty space on one side).
                "rim_ring_world": r["rim_ring_world"].tolist(),
            }
            for r in records
        ],
        "generation": {
            "tool": "make_phantom.py", "voxel_mm": voxel_mm, "n_sites": n_sites,
            "lib_root": str(lib_root),
        },
    }
    (out / "phantom-ground-truth.json").write_text(json.dumps(truth, indent=2))

    try:
        _preview_png(mesh, records, out / "phantom-preview.png")
    except ImportError:
        pass  # matplotlib is a dev-optional dependency; the STL/JSON are still valid

    return truth


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--voxel-mm", type=float, default=0.15,
                   help="SDF grid pitch, mm. ~0.12-0.15 for print quality; use a "
                        "coarser value (e.g. 0.4-0.5) for fast test runs.")
    p.add_argument("--n-sites", type=int, default=6, help="1-6; a prefix of the "
                   "designed site table (fewer sites = a fast mini-plate).")
    p.add_argument("--lib-root", default=str(DEFAULT_LIB_ROOT))
    args = p.parse_args()

    truth = generate_phantom(out_dir=args.out_dir, voxel_mm=args.voxel_mm,
                             n_sites=args.n_sites, lib_root=args.lib_root)
    print(f"wrote {args.n_sites} sites to {args.out_dir} "
         f"(voxel {args.voxel_mm}mm): "
         f"{[s['label'] for s in truth['sites']]}")


if __name__ == "__main__":
    main()
