"""Adversarial synthetic case generator (ground-truth-by-construction).

Places known scan-body meshes at known 6-DoF poses on a gingiva arch and writes a
complete case directory plus held-out ground truth. Degradations (vertex noise,
partial capture) are tunable so 'the pipeline recovers the pose' is a real result,
not a tautology. No Open3D here — pure numpy/trimesh, so it is fully testable.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np
import trimesh

from case_prep.domain.clocking import clocking_angle_deg
from case_prep.domain.confidence import CaseMode
from case_prep.domain.geometry import Axis, RigidTransform
from case_prep.domain.ground_truth import GroundTruth, ImplantTruth
from case_prep.domain.poses import Retention
from case_prep.manifest import CaseManifest, SiteSpec

# Scan-body geometry constants (mm). A near-cylinder with one flat = the
# anti-rotation feature that makes clocking *possible* but symmetry-ambiguity *hard*.
_SB_RADIUS = 2.0
_SB_HEIGHT = 8.0
_SB_FLAT_X = 0.4  # flat plane at x = FLAT_X (< radius) cuts a distinct D-profile (anti-rotation)
_PLATFORM_DEPTH = 1.5  # platform sits this far below the scan-body base, along -axis

# Universal-numbering posterior teeth we draw sites from.
_TOOTH_POOL = [2, 3, 14, 15, 18, 19, 30, 31]
_SCAN_BODY_TYPE = "synthetic_sb"


def make_scan_body_mesh(
    radius: float = _SB_RADIUS, height: float = _SB_HEIGHT, flat_x: float = _SB_FLAT_X
) -> trimesh.Trimesh:
    """A scan body in local frame: base center at origin, axis = +z, with one flat
    face on the +x side (the anti-rotation feature)."""
    mesh = trimesh.creation.cylinder(radius=radius, height=height, sections=64)
    mesh.apply_translation([0.0, 0.0, height / 2.0])  # base at z=0
    # subdivide so the shaft has vertices along its height (a bare cylinder has only
    # top/bottom rings, which would defeat height-based localization)
    for _ in range(2):
        mesh = mesh.subdivide()
    v = mesh.vertices.copy()
    v[v[:, 0] > flat_x, 0] = flat_x  # project the +x arc onto a flat plane
    mesh.vertices = v
    return mesh


def make_gingiva_arch(rng: np.random.Generator) -> trimesh.Trimesh:
    """A coarse curved soft-tissue strip the scan bodies stand proud of, so
    height-above-surface detection is exercised honestly."""
    thetas = np.linspace(-1.0, 1.0, 40)
    arch_r = 25.0
    centers = np.c_[arch_r * np.sin(thetas), arch_r * np.cos(thetas) - arch_r, np.zeros_like(thetas)]
    boxes = []
    for c in centers:
        b = trimesh.creation.box(extents=[4.0, 4.0, 1.5])
        b.apply_translation(c + [0, 0, -0.75])
        boxes.append(b)
    return trimesh.util.concatenate(boxes)


def _placement_transform(center_xy: np.ndarray, tilt_deg: float, clocking_deg: float,
                         tilt_axis: np.ndarray) -> RigidTransform:
    """World transform for a scan body: clock about its own axis, tilt slightly,
    translate to its arch position (base center at z=0)."""
    clock = RigidTransform.from_axis_angle([0, 0, 1], clocking_deg)
    tilt = RigidTransform.from_axis_angle(tilt_axis, tilt_deg)
    translate = RigidTransform.from_translation([center_xy[0], center_xy[1], 0.0])
    return translate.compose(tilt).compose(clock)


@dataclass
class SyntheticParams:
    seed: int = 0
    n_implants: int = 2
    retention: Retention = Retention.CEMENT
    noise_mm: float = 0.0  # gaussian vertex jitter stddev
    partial_fraction: float = 0.0  # fraction of scan-body faces dropped (occlusion)
    max_tilt_deg: float = 6.0


def generate_case(out_dir, params: SyntheticParams) -> GroundTruth:
    out = Path(out_dir)
    (out / "library" / _SCAN_BODY_TYPE).mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(params.seed)

    teeth = sorted(rng.choice(_TOOTH_POOL, size=params.n_implants, replace=False).tolist())
    thetas = np.linspace(-0.8, 0.8, params.n_implants)
    arch_r = 25.0

    clean_sb = make_scan_body_mesh()
    scan_parts: List[trimesh.Trimesh] = [make_gingiva_arch(rng)]
    truths: List[ImplantTruth] = []
    sites: List[SiteSpec] = []

    for tooth, theta in zip(teeth, thetas):
        center_xy = np.array([arch_r * np.sin(theta), arch_r * np.cos(theta) - arch_r])
        tilt_deg = float(rng.uniform(0, params.max_tilt_deg))
        tilt_axis = np.array([rng.uniform(-1, 1), rng.uniform(-1, 1), 0.0]) + [1e-6, 0, 0]
        clocking_deg = float(rng.uniform(0, 360))

        T = _placement_transform(center_xy, tilt_deg, clocking_deg, tilt_axis)

        placed = clean_sb.copy()
        placed.apply_transform(T.matrix)
        scan_parts.append(placed)

        # platform = a point PLATFORM_DEPTH below the base along the body axis
        platform_local = np.array([0.0, 0.0, -_PLATFORM_DEPTH])
        platform_world = T.apply(platform_local)
        axis_world = Axis.from_vector(T.rotation @ np.array([0.0, 0.0, 1.0]))

        retention = params.retention
        truths.append(
            ImplantTruth(
                tooth=tooth,
                scan_body_type=_SCAN_BODY_TYPE,
                retention=retention,
                position=[float(x) for x in platform_world],
                axis=[float(x) for x in axis_world.direction],
                # store clocking on the same rotation-derived basis the engine recovers,
                # so ground-truth vs recovered is an apples-to-apples comparison
                clocking_degrees=(
                    clocking_angle_deg(T.rotation) if retention is Retention.SCREW else None
                ),
            )
        )
        sites.append(SiteSpec(tooth=tooth, scan_body_type=_SCAN_BODY_TYPE, retention=retention))

    scan = trimesh.util.concatenate(scan_parts)
    scan = _degrade(scan, rng, params)

    # Write the case contract.
    scan.export(out / "scan.stl")
    clean_sb.export(out / "library" / _SCAN_BODY_TYPE / "mesh.stl")
    sb_to_platform = RigidTransform.from_translation([0.0, 0.0, -_PLATFORM_DEPTH])
    (out / "library" / _SCAN_BODY_TYPE / "transform.json").write_text(
        json.dumps({"scan_body_to_platform": sb_to_platform.matrix.tolist()}, indent=2)
    )
    # VALIDATED: synthetic is the data class the gate thresholds were calibrated on — the one
    # class where a PASS may auto-approve (every other writer inherits the advisory default).
    manifest = CaseManifest(case_ref=f"synthetic-{params.seed}", scan_file="scan.stl",
                            implant_sites=sites, mode=CaseMode.VALIDATED)
    (out / "case.json").write_text(manifest.model_dump_json(indent=2))

    gt = GroundTruth(poses=truths)
    (out / "ground_truth.json").write_text(gt.model_dump_json(indent=2))
    return gt


def _degrade(mesh: trimesh.Trimesh, rng: np.random.Generator, params: SyntheticParams):
    if params.partial_fraction > 0:
        keep = rng.random(len(mesh.faces)) > params.partial_fraction
        mesh.update_faces(keep)
        mesh.remove_unreferenced_vertices()
    if params.noise_mm > 0:
        mesh.vertices = mesh.vertices + rng.normal(0, params.noise_mm, mesh.vertices.shape)
    return mesh
