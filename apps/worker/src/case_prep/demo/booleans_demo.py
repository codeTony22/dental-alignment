"""Boolean-operations demo: bores a screw-access channel into a restoration via SDF-CSG,
proves it stays robust on a deliberately messy (non-watertight) mesh, and writes both an
SDF cross-section render and real STL files you can open in any 3D viewer.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import trimesh

from case_prep.adapters.booleans import screw_channel
from case_prep.adapters.mesh_sdf import mesh_to_sdf, sdf_to_mesh
from case_prep.adapters.messy import DefectSpec, inject_defects
from case_prep.adapters.render import render_csg_slices
from case_prep.domain.sdf import op_difference, sdf_cylinder


@dataclass
class BooleanCase:
    name: str
    input_watertight: bool
    output_watertight: bool
    input_volume: float
    output_volume: float
    input_stl: Path
    output_stl: Path


def _restoration() -> trimesh.Trimesh:
    # a crown-abutment stand-in: a solid cylinder the screw channel passes through.
    # Subdivided to small triangles like a real scan, so injected holes are small and
    # bridgeable (a coarse mesh's giant triangles would leave holes too big to close).
    m = trimesh.creation.cylinder(radius=4.0, height=11.0, sections=64)
    for _ in range(2):
        m = m.subdivide()
    return m


def run_booleans_demo(out_dir, pitch: float = 0.25) -> tuple:
    out = Path(out_dir)
    (out / "stl").mkdir(parents=True, exist_ok=True)

    cases: List[BooleanCase] = []
    render_path: Optional[Path] = None

    for name, mesh in (
        ("clean restoration", _restoration()),
        ("messy restoration (holes + noise)",
         inject_defects(_restoration(), DefectSpec(seed=5, hole_fraction=0.12, noise_mm=0.05))),
    ):
        bored = screw_channel(mesh, position=[0, 0, 0], axis=[0, 0, 1], radius=1.2, length=15.0, pitch=pitch)
        in_stl = out / "stl" / f"{name.split()[0]}_input.stl"
        out_stl = out / "stl" / f"{name.split()[0]}_bored.stl"
        mesh.export(in_stl)
        bored.export(out_stl)
        cases.append(BooleanCase(
            name=name,
            input_watertight=bool(mesh.is_watertight), output_watertight=bool(bored.is_watertight),
            input_volume=float(mesh.volume), output_volume=float(bored.volume),
            input_stl=in_stl, output_stl=out_stl,
        ))

        if render_path is None:  # render the clean case's field slice
            grid = mesh_to_sdf(mesh, pitch)
            after = op_difference(grid.values, sdf_cylinder(grid, [0, 0, 0], [0, 0, 1], 1.2, 7.5))
            render_path = render_csg_slices(
                grid, grid.values, after,
                "Screw-access channel via SDF-CSG (signed-distance slice)",
                out / "csg-slice.png",
            )

    return cases, render_path
