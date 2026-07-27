"""Messy-mesh generator: injects the defect classes real intraoral scans exhibit, so
the SDF booleans and ingest can be stress-tested against realistic pathology without
patient data. Deterministic (seeded). This is the adversarial counterpart to the clean
synthetic generator — clean geometry never triggers the boolean-robustness failure mode.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import trimesh


@dataclass
class DefectSpec:
    seed: int = 0
    hole_fraction: float = 0.0       # fraction of faces dropped -> non-watertight holes
    noise_mm: float = 0.0            # gaussian vertex jitter stddev
    spurious_fragments: int = 0      # disconnected floating blobs (scan artefacts)


def inject_defects(mesh: trimesh.Trimesh, spec: DefectSpec) -> trimesh.Trimesh:
    rng = np.random.default_rng(spec.seed)
    out = mesh.copy()

    if spec.hole_fraction > 0:
        keep = rng.random(len(out.faces)) > spec.hole_fraction
        out.update_faces(keep)
        out.remove_unreferenced_vertices()

    if spec.noise_mm > 0:
        out.vertices = out.vertices + rng.normal(0, spec.noise_mm, out.vertices.shape)

    parts = [out]
    for _ in range(spec.spurious_fragments):
        blob = trimesh.creation.icosphere(subdivisions=1, radius=float(rng.uniform(0.4, 1.0)))
        extent = float(np.linalg.norm(mesh.extents))
        blob.apply_translation(rng.uniform(-0.6, 0.6, 3) * extent)
        parts.append(blob)
    return trimesh.util.concatenate(parts) if len(parts) > 1 else out
