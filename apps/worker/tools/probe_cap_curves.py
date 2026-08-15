#!/usr/bin/env python
"""Healing-cap curve measurement probe — density, STL colour, dihedral closure.

WHY: the curve-alignment design (`docs/engagement/healing-cap-curve-alignment-design.md`)
cites three fleet measurements that originally lived only in a specialist's terminal
scrollback. This tool is the receipt: anyone can re-run it against `data/real/scans/`
and get the same tables.

Three instruments, all deterministic:

1. **STL colour** — binary-STL per-facet attribute bytes, plus trimesh vertex/face
   colour cardinality. Uniform default grey counts as *no colour* (that is what a
   doctor's RealGUIDE STL actually carries).
2. **Local triangle density** — faces whose centroid is within 3 mm of the curated
   centre vs the 6–12 mm tissue annulus, as triangles per mm². Absolute values are
   exporter-specific; the *ratio* is the prior. A ratio < 1 is an inversion (the
   cap is coarser than its neighbourhood) and is the reason density is a prior,
   never a gate.
3. **Dihedral rim closure** — of 24 bearings (15°) about the curated centre, how
   many contain a crease edge (face-adjacency angle > 20° / > 30°) within ±0.8 mm
   of the doctor's marked rim radius. Partial arcs are the expected case.

CLI is a thin wrapper — every analysis function is importable and covered by
`tests/test_probe_cap_curves.py`.

    .venv/bin/python tools/probe_cap_curves.py
    .venv/bin/python tools/probe_cap_curves.py --scans /path/to/scans
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np
import trimesh

WORKER_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCANS = WORKER_ROOT / "data" / "real" / "scans"

CAP_BALL_MM = 3.0
TISSUE_ANNULUS_MM = (6.0, 12.0)
N_BEARINGS = 24
RADIAL_TOL_MM = 0.8
CREASE_DEG_LO = 20.0
CREASE_DEG_HI = 30.0


# --------------------------------------------------------------------------------------
# Readings
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class ColourReading:
    path: str
    header: str
    n_faces: int
    attr_nonzero: int
    distinct_vertex_colors: int
    distinct_face_colors: int


@dataclass(frozen=True)
class DensityReading:
    cap_tri_per_mm2: float
    tissue_tri_per_mm2: float
    ratio: float
    cap_median_edge_mm: float
    tissue_median_edge_mm: float
    case_id: str = ""
    tooth: int = 0


@dataclass(frozen=True)
class ClosureReading:
    bearings_hit_20deg: int
    bearings_hit_30deg: int
    n_bearings: int = N_BEARINGS
    case_id: str = ""
    tooth: int = 0


@dataclass(frozen=True)
class FleetSite:
    case_id: str
    tooth: int
    stl_path: Path
    center: Tuple[float, float, float]
    rim_r_mm: float


@dataclass(frozen=True)
class FleetReport:
    colour: Tuple[ColourReading, ...]
    density: Tuple[DensityReading, ...]
    closure: Tuple[ClosureReading, ...]


# --------------------------------------------------------------------------------------
# Colour
# --------------------------------------------------------------------------------------

def _distinct_colors(arr) -> int:
    """Unique rows in a colour array. A missing or uniform (default-grey) channel is 0."""
    if arr is None:
        return 0
    a = np.asarray(arr)
    if a.size == 0:
        return 0
    rows = a.reshape(len(a), -1)
    uniq = np.unique(rows, axis=0)
    return 0 if len(uniq) <= 1 else int(len(uniq))


def read_stl_colour(path: Path) -> ColourReading:
    """Read the STL colour channels without trusting trimesh's default grey as signal."""
    data = path.read_bytes()
    if len(data) < 84:
        raise ValueError(f"{path} is too small to be a binary STL")
    header = data[:80].split(b"\0", 1)[0].decode("latin-1", errors="replace").strip()
    n_faces = int(struct.unpack_from("<I", data, 80)[0])
    expected = 84 + n_faces * 50
    if len(data) == expected:
        attr_nonzero = 0
        off = 84
        for _ in range(n_faces):
            if struct.unpack_from("<H", data, off + 48)[0]:
                attr_nonzero += 1
            off += 50
    else:
        # ASCII, or a non-standard payload — there is no attribute channel to count.
        attr_nonzero = 0
        n_faces = 0

    mesh = trimesh.load(path, force="mesh", process=False)
    visual = getattr(mesh, "visual", None)
    vcol = getattr(visual, "vertex_colors", None) if visual is not None else None
    fcol = getattr(visual, "face_colors", None) if visual is not None else None
    return ColourReading(
        path=str(path),
        header=header,
        n_faces=int(len(mesh.faces)) if n_faces == 0 else n_faces,
        attr_nonzero=int(attr_nonzero),
        distinct_vertex_colors=_distinct_colors(vcol),
        distinct_face_colors=_distinct_colors(fcol),
    )


# --------------------------------------------------------------------------------------
# Density
# --------------------------------------------------------------------------------------

def _triangle_areas(verts: np.ndarray, faces: np.ndarray) -> np.ndarray:
    tris = verts[faces]
    return 0.5 * np.linalg.norm(
        np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]), axis=1)


def _median_edge_mm(verts: np.ndarray, faces: np.ndarray) -> float:
    if len(faces) == 0:
        return 0.0
    tris = verts[faces]
    edges = np.concatenate([
        np.linalg.norm(tris[:, 1] - tris[:, 0], axis=1),
        np.linalg.norm(tris[:, 2] - tris[:, 1], axis=1),
        np.linalg.norm(tris[:, 0] - tris[:, 2], axis=1),
    ])
    return float(np.median(edges))


def _region_density(n_faces: int, area_mm2: float) -> float:
    if area_mm2 <= 0.0 or n_faces == 0:
        return 0.0
    return float(n_faces) / float(area_mm2)


def local_density(verts: np.ndarray, faces: np.ndarray, center: np.ndarray,
                  cap_ball_mm: float = CAP_BALL_MM,
                  tissue_annulus_mm: Tuple[float, float] = TISSUE_ANNULUS_MM,
                  ) -> DensityReading:
    """Cap-local vs tissue-annulus tessellation, in triangles per mm²."""
    verts = np.asarray(verts, dtype=float)
    faces = np.asarray(faces, dtype=int)
    center = np.asarray(center, dtype=float).reshape(3)
    centroids = verts[faces].mean(axis=1)
    dist = np.linalg.norm(centroids - center, axis=1)
    areas = _triangle_areas(verts, faces)
    cap = dist <= cap_ball_mm
    lo, hi = tissue_annulus_mm
    tissue = (dist >= lo) & (dist <= hi)
    cap_n, tissue_n = int(cap.sum()), int(tissue.sum())
    cap_area, tissue_area = float(areas[cap].sum()), float(areas[tissue].sum())
    cap_d = _region_density(cap_n, cap_area)
    tissue_d = _region_density(tissue_n, tissue_area)
    ratio = (cap_d / tissue_d) if tissue_d > 0.0 else 0.0
    return DensityReading(
        cap_tri_per_mm2=cap_d,
        tissue_tri_per_mm2=tissue_d,
        ratio=ratio,
        cap_median_edge_mm=_median_edge_mm(verts, faces[cap]),
        tissue_median_edge_mm=_median_edge_mm(verts, faces[tissue]),
    )


# --------------------------------------------------------------------------------------
# Dihedral closure
# --------------------------------------------------------------------------------------

def _fit_plane(points: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    origin = points.mean(axis=0)
    _, _, vt = np.linalg.svd(points - origin, full_matrices=False)
    normal = vt[-1]
    nlen = float(np.linalg.norm(normal))
    if nlen < 1e-12:
        normal = np.array([0.0, 0.0, 1.0])
    else:
        normal = normal / nlen
    return origin, normal


def _tangent_basis(normal: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    t0 = np.cross(normal, np.array([0.0, 0.0, 1.0]))
    if np.linalg.norm(t0) < 1e-6:
        t0 = np.cross(normal, np.array([1.0, 0.0, 0.0]))
    t0 = t0 / np.linalg.norm(t0)
    t1 = np.cross(normal, t0)
    t1 = t1 / np.linalg.norm(t1)
    return t0, t1


def _project_xy(points: np.ndarray, origin: np.ndarray, normal: np.ndarray) -> np.ndarray:
    if len(points) == 0:
        return np.zeros((0, 2))
    finite = np.isfinite(points).all(axis=1)
    points = points[finite]
    if len(points) == 0:
        return np.zeros((0, 2))
    t0, t1 = _tangent_basis(normal)
    if not (np.isfinite(t0).all() and np.isfinite(t1).all()):
        return np.zeros((0, 2))
    d = points - origin
    xy = np.column_stack([d @ t0, d @ t1])
    return xy[np.isfinite(xy).all(axis=1)]


def _bearing_hits(xy: np.ndarray, rim_r_mm: float, radial_tol_mm: float,
                  n_bearings: int) -> int:
    if len(xy) == 0:
        return 0
    r = np.linalg.norm(xy, axis=1)
    in_band = np.abs(r - rim_r_mm) <= radial_tol_mm
    if not in_band.any():
        return 0
    theta = np.arctan2(xy[in_band, 1], xy[in_band, 0])
    bins = np.floor((theta + np.pi) / (2.0 * np.pi) * n_bearings).astype(int) % n_bearings
    return int(np.unique(bins).size)


def _welded_mesh(verts: np.ndarray, faces: np.ndarray) -> trimesh.Trimesh:
    """Binary STL does not share vertices; weld so face adjacency exists."""
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    mesh.merge_vertices()
    return mesh


def _crease_mids_from_mesh(mesh: trimesh.Trimesh, min_angle_rad: float) -> np.ndarray:
    if mesh.face_adjacency is None or len(mesh.face_adjacency) == 0:
        return np.zeros((0, 3))
    angles = np.asarray(mesh.face_adjacency_angles, dtype=float)
    edges = np.asarray(mesh.face_adjacency_edges, dtype=int)
    keep = angles > min_angle_rad
    if not keep.any():
        return np.zeros((0, 3))
    pair = np.asarray(mesh.vertices, dtype=float)[edges[keep]]
    return pair.mean(axis=1)


def dihedral_closure(verts: np.ndarray, faces: np.ndarray, center: np.ndarray,
                     rim_r_mm: float,
                     n_bearings: int = N_BEARINGS,
                     radial_tol_mm: float = RADIAL_TOL_MM,
                     ) -> ClosureReading:
    """How many of `n_bearings` around `center` see a crease at the marked rim."""
    verts = np.asarray(verts, dtype=float)
    faces = np.asarray(faces, dtype=int)
    center = np.asarray(center, dtype=float).reshape(3)
    # Plane from the rim-band vertices so the unwrap is in the cap's own frame,
    # not the scan's world XY (arches arrive at arbitrary orientation).
    dist = np.linalg.norm(verts - center, axis=1)
    band = verts[np.abs(dist - rim_r_mm) <= max(radial_tol_mm, 1.5)]
    if len(band) < 8:
        band = verts[dist <= rim_r_mm + 2.0]
    if len(band) < 3:
        return ClosureReading(0, 0, n_bearings)
    _origin, normal = _fit_plane(band)

    def _in_rim_shell(mids: np.ndarray) -> np.ndarray:
        if len(mids) == 0:
            return mids
        d = np.linalg.norm(mids - center, axis=1)
        return mids[np.abs(d - rim_r_mm) <= radial_tol_mm]

    welded = _welded_mesh(verts, faces)
    mids_20 = _in_rim_shell(_crease_mids_from_mesh(welded, np.deg2rad(CREASE_DEG_LO)))
    mids_30 = _in_rim_shell(_crease_mids_from_mesh(welded, np.deg2rad(CREASE_DEG_HI)))
    # Unwrap about the curated centre, not the rim-band centroid — gum at the
    # same 3D radius would pull that centroid off the cap.
    xy20 = _project_xy(mids_20, center, normal) if len(mids_20) else np.zeros((0, 2))
    xy30 = _project_xy(mids_30, center, normal) if len(mids_30) else np.zeros((0, 2))
    return ClosureReading(
        bearings_hit_20deg=_bearing_hits(xy20, rim_r_mm, radial_tol_mm, n_bearings),
        bearings_hit_30deg=_bearing_hits(xy30, rim_r_mm, radial_tol_mm, n_bearings),
        n_bearings=n_bearings,
    )


# --------------------------------------------------------------------------------------
# Fleet walk
# --------------------------------------------------------------------------------------

def discover_fleet(scans_dir: Path) -> List[FleetSite]:
    """One row per suggested site under `doctor-*/{sites.json, *.stl}`."""
    rows: List[FleetSite] = []
    for case_dir in sorted(p for p in scans_dir.glob("doctor-*") if p.is_dir()):
        sites_path = case_dir / "sites.json"
        if not sites_path.is_file():
            continue
        stls = sorted(case_dir.glob("*.stl"))
        jaw = [p for p in stls if "jaw" in p.name.lower()]
        stl = (jaw or stls)[0] if (jaw or stls) else None
        if stl is None:
            continue
        payload = json.loads(sites_path.read_text())
        case_id = case_dir.name[len("doctor-"):]
        for site in payload.get("suggested_sites") or []:
            center_list = site.get("center_mark") or site.get("center")
            rim_list = site.get("rim_mark")
            if not center_list or not rim_list:
                continue
            center = tuple(float(x) for x in center_list)
            rim = np.asarray(rim_list, dtype=float)
            rim_r = float(np.linalg.norm(rim - np.asarray(center, dtype=float)))
            rows.append(FleetSite(
                case_id=case_id,
                tooth=int(site["tooth"]),
                stl_path=stl,
                center=center,  # type: ignore[arg-type]
                rim_r_mm=rim_r,
            ))
    return rows


def probe_fleet(scans_dir: Path) -> FleetReport:
    sites = discover_fleet(scans_dir)
    colour: List[ColourReading] = []
    density: List[DensityReading] = []
    closure: List[ClosureReading] = []
    seen_stl: dict = {}
    meshes: dict = {}
    for site in sites:
        key = str(site.stl_path)
        if key not in seen_stl:
            seen_stl[key] = read_stl_colour(site.stl_path)
            colour.append(seen_stl[key])
            meshes[key] = trimesh.load(site.stl_path, force="mesh", process=False)
        mesh = meshes[key]
        verts = np.asarray(mesh.vertices, dtype=float)
        faces = np.asarray(mesh.faces, dtype=int)
        center = np.asarray(site.center, dtype=float)
        density.append(replace(
            local_density(verts, faces, center),
            case_id=site.case_id, tooth=site.tooth))
        closure.append(replace(
            dihedral_closure(verts, faces, center, site.rim_r_mm),
            case_id=site.case_id, tooth=site.tooth))
    return FleetReport(tuple(colour), tuple(density), tuple(closure))


def render_markdown(report: FleetReport) -> str:
    lines = [
        "# Healing-cap curve probe",
        "",
        "Re-run: `cd apps/worker && .venv/bin/python tools/probe_cap_curves.py`.",
        f"Instruments: cap ball {CAP_BALL_MM:.0f} mm · tissue annulus "
        f"{TISSUE_ANNULUS_MM[0]:.0f}–{TISSUE_ANNULUS_MM[1]:.0f} mm · "
        f"{N_BEARINGS} bearings · radial tol {RADIAL_TOL_MM} mm · "
        f"crease {CREASE_DEG_LO:.0f}° / {CREASE_DEG_HI:.0f}°.",
        "",
        "## Colour (binary STL attribute bytes + trimesh visuals)",
        "",
        "| file | header | faces | attr_nonzero | vertex colours | face colours |",
        "|---|---|---|---|---|---|",
    ]
    for row in report.colour:
        name = Path(row.path).parent.name + "/" + Path(row.path).name
        lines.append(
            f"| `{name}` | {row.header or '(empty)'} | {row.n_faces} | "
            f"{row.attr_nonzero} | {row.distinct_vertex_colors} | "
            f"{row.distinct_face_colors} |")
    lines += [
        "",
        "## Local triangle density (cap vs tissue annulus)",
        "",
        "| site | cap tri/mm² | tissue tri/mm² | ratio | cap edge mm | tissue edge mm |",
        "|---|---|---|---|---|---|",
    ]
    for row in report.density:
        lines.append(
            f"| {row.case_id} t{row.tooth} | {row.cap_tri_per_mm2:.1f} | "
            f"{row.tissue_tri_per_mm2:.1f} | {row.ratio:.2f}× | "
            f"{row.cap_median_edge_mm:.3f} | {row.tissue_median_edge_mm:.3f} |")
    lines += [
        "",
        "## Dihedral rim closure (of 24 bearings)",
        "",
        "| site | >20° ±0.8 mm | >30° ±0.8 mm |",
        "|---|---|---|",
    ]
    for row in report.closure:
        lines.append(
            f"| {row.case_id} t{row.tooth} | "
            f"{row.bearings_hit_20deg}/{row.n_bearings} | "
            f"{row.bearings_hit_30deg}/{row.n_bearings} |")
    if report.closure:
        hits20 = sorted(r.bearings_hit_20deg for r in report.closure)
        hits30 = sorted(r.bearings_hit_30deg for r in report.closure)
        mid = len(hits20) // 2
        lines += [
            "",
            f"Median closure at 20°: {hits20[mid]}/24. "
            f"Median at 30°: {hits30[mid]}/24. "
            "A curve extractor must be designed for partial arcs.",
        ]
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure density, STL colour, and dihedral closure on doctor scans.")
    parser.add_argument("--scans", type=Path, default=DEFAULT_SCANS,
                        help="Path to data/real/scans (doctor-*/ folders).")
    args = parser.parse_args(argv)
    if not args.scans.is_dir():
        print(f"no scans directory at {args.scans}", file=sys.stderr)
        return 2
    print(render_markdown(probe_fleet(args.scans)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
