"""Filesystem case loader. Reads the same case-directory contract whether the case
was produced by the synthetic generator or dropped in from a real client export.
Does NOT load ground_truth.json — that is held out from the pipeline by design.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import numpy as np
import trimesh

from case_prep.domain.geometry import RigidTransform
from case_prep.manifest import CaseManifest


@dataclass
class LibraryPart:
    mesh: trimesh.Trimesh
    scan_body_to_platform: RigidTransform
    # False when the transform is the identity placeholder ("until the real spec lands"):
    # the derived pose is then the SCAN BODY's pose, not the implant platform's — downstream
    # consumers must see that honestly (pose_origin in rows / implant.json).
    platform_transform_known: bool = True


@dataclass
class LoadedCase:
    case_dir: Path
    manifest: CaseManifest
    scan: trimesh.Trimesh
    library: Dict[str, LibraryPart]


def load_case(case_dir) -> LoadedCase:
    case_dir = Path(case_dir)
    manifest = CaseManifest.model_validate_json((case_dir / "case.json").read_text())
    scan = trimesh.load(case_dir / manifest.scan_file, force="mesh")

    library: Dict[str, LibraryPart] = {}
    for sb_type in {s.scan_body_type for s in manifest.implant_sites}:
        part_dir = case_dir / "library" / sb_type
        mesh = trimesh.load(part_dir / "mesh.stl", force="mesh")
        transform = json.loads((part_dir / "transform.json").read_text())
        m = np.asarray(transform["scan_body_to_platform"], dtype=float)
        library[sb_type] = LibraryPart(
            mesh=mesh, scan_body_to_platform=RigidTransform(m),
            platform_transform_known=not np.allclose(m, np.eye(4)))
    return LoadedCase(case_dir=case_dir, manifest=manifest, scan=scan, library=library)
