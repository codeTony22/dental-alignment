"""Build a SEMI-REAL case: a real intraoral arch (e.g. Teeth3DS) as the base, with
scan bodies placed on its occlusal surface at known poses. This stresses the full
pipeline on REAL mesh topology (dense, non-watertight, real defects) while retaining
exact ground truth — the strongest validation available without real implant-scan data.

Honest framing: the bodies are placed on the occlusal surface for a *geometry* demo;
this is not an anatomically-real implant case (no public dataset has scan bodies in place).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import trimesh

from case_prep.adapters.ingest import canonicalize_library, normalize_orientation
from case_prep.adapters.synthetic import _PLATFORM_DEPTH, _SCAN_BODY_TYPE, make_scan_body_mesh
from case_prep.domain.clocking import clocking_angle_deg
from case_prep.domain.geometry import Axis, RigidTransform
from case_prep.domain.ground_truth import GroundTruth, ImplantTruth
from case_prep.domain.poses import Retention
from case_prep.manifest import CaseManifest, SiteSpec

_TOOTH_POOL = [19, 20, 21, 29, 30, 31]


def build_real_implant_case(scan_path, scanbody_path, out_dir, tooth: int = 8,
                            retention: Retention = Retention.CEMENT,
                            scan_body_type: str = "certain3i_4_1") -> GroundTruth:
    """Wire a REAL case (doctor's input scan + the scan body segmented out) into the
    pipeline's case format. The segmented body is canonicalized into a local-frame library
    and its real placement becomes ground truth. NOTE: with no manufacturer scan-body->platform
    transform, this recovers the scan-BODY pose, not the implant platform; and the segmented
    body is the captured (not clean-CAD) reference — so this measures convergence, not yet
    clinical accuracy. Drop in the clean library CAD + platform transform to get the real number."""
    out = Path(out_dir)
    (out / "library" / scan_body_type).mkdir(parents=True, exist_ok=True)

    scan = trimesh.load(scan_path, force="mesh")
    sb = trimesh.load(scanbody_path, force="mesh")
    lib_local, placement = canonicalize_library(sb)

    scan.export(out / "scan.stl")
    lib_local.export(out / "library" / scan_body_type / "mesh.stl")
    (out / "library" / scan_body_type / "transform.json").write_text(
        json.dumps({"scan_body_to_platform": np.eye(4).tolist()}))  # identity until the real spec lands
    (out / "case.json").write_text(CaseManifest(
        case_ref=f"real-{Path(scan_path).stem[:24]}", scan_file="scan.stl",
        implant_sites=[SiteSpec(tooth=tooth, scan_body_type=scan_body_type, retention=retention)],
    ).model_dump_json(indent=2))

    axis = Axis.from_vector(placement.rotation @ np.array([0.0, 0.0, 1.0]))
    gt = GroundTruth(poses=[ImplantTruth(
        tooth=tooth, scan_body_type=scan_body_type, retention=retention,
        position=[float(x) for x in placement.translation],
        axis=[float(x) for x in axis.direction], clocking_degrees=None)])
    (out / "ground_truth.json").write_text(gt.model_dump_json(indent=2))
    return gt


def _occlusal_sites(arch: trimesh.Trimesh, n: int, rng) -> np.ndarray:
    """Pick n well-spread points on the occlusal ridge (the high-z band of the arch)."""
    v = np.asarray(arch.vertices, float)
    band = v[v[:, 2] > v[:, 2].max() - 4.0]
    centre = band[:, :2].mean(axis=0)
    ang = np.arctan2(band[:, 1] - centre[1], band[:, 0] - centre[0])
    sites = []
    for lo, hi in zip(np.linspace(ang.min(), ang.max(), n + 1)[:-1],
                      np.linspace(ang.min(), ang.max(), n + 1)[1:]):
        sel = band[(ang >= lo) & (ang < hi)]
        if len(sel):
            sites.append(sel[sel[:, 2].argmax()])  # highest point in the angular bin
    return np.array(sites[:n])


def build_embedded_case(real_arch_path, library_cad_path, out_dir, n_implants: int = 1,
                        retention: Retention = Retention.CEMENT, seed: int = 0,
                        noise_mm: float = 0.04, occlusion: float = 0.30,
                        scan_body_type: str = "certain3i_4_1",
                        canonicalize=canonicalize_library) -> GroundTruth:
    """Embed the CLEAN library CAD into a REAL arch at known poses, DEGRADED (sensor noise +
    occlusion), and use that same clean CAD as the registration reference. This is the honest
    real-geometry end-to-end test short of a patient arch scanned with this exact abutment: it
    exercises localization among real teeth (step 2) and registration of the clean reference
    (step 3-4) on real dental structure, with exact ground truth.

    Degradation is essential and deliberate: registering the clean CAD against a clean copy of
    itself would be CAD-vs-CAD (trivially perfect, proving nothing). The placed body is noised and
    partially occluded so the recovered accuracy reflects a real intraoral capture."""
    out = Path(out_dir)
    (out / "library" / scan_body_type).mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    arch, _ = normalize_orientation(trimesh.load(real_arch_path, force="mesh"))
    # scan BODIES use the tallest-PCA frame (default); squat revolute parts (healing caps)
    # must pass canonicalize_revolute — tallest-PCA would embed them lying on their side
    # and record a diameter as the ground-truth axis
    lib_local, _ = canonicalize(trimesh.load(library_cad_path, force="mesh"))
    sites = _occlusal_sites(arch, n_implants, rng)
    teeth = sorted(rng.choice(_TOOTH_POOL, size=len(sites), replace=False).tolist())

    parts = [arch]
    truths, declared = [], []
    for tooth, site in zip(teeth, sites):
        tilt_deg = float(rng.uniform(0, 8))
        tilt_axis = np.array([rng.uniform(-1, 1), rng.uniform(-1, 1), 0.0]) + [1e-6, 0, 0]
        clocking = float(rng.uniform(0, 360))
        T = (RigidTransform.from_translation(site)
             .compose(RigidTransform.from_axis_angle(tilt_axis, tilt_deg))
             .compose(RigidTransform.from_axis_angle([0, 0, 1], clocking)))
        body = lib_local.copy()
        body.apply_transform(T.matrix)
        _degrade_body(body, rng, noise_mm, occlusion)  # simulate a real intraoral capture
        parts.append(body)

        position = T.apply([0.0, 0.0, 0.0])  # platform == canonical centroid (sb->platform = identity)
        axis = Axis.from_vector(T.rotation @ np.array([0.0, 0.0, 1.0]))
        truths.append(ImplantTruth(
            tooth=tooth, scan_body_type=scan_body_type, retention=retention,
            position=[float(x) for x in position], axis=[float(x) for x in axis.direction],
            clocking_degrees=clocking_angle_deg(T.rotation) if retention is Retention.SCREW else None,
        ))
        declared.append(SiteSpec(tooth=tooth, scan_body_type=scan_body_type, retention=retention))

    scan = trimesh.util.concatenate(parts)
    scan.export(out / "scan.stl")
    lib_local.export(out / "library" / scan_body_type / "mesh.stl")  # the CLEAN reference (not degraded)
    (out / "library" / scan_body_type / "transform.json").write_text(
        json.dumps({"scan_body_to_platform": np.eye(4).tolist()}))  # identity until the real spec lands
    (out / "case.json").write_text(CaseManifest(
        case_ref=f"embedded-{Path(library_cad_path).stem[:20]}", scan_file="scan.stl",
        implant_sites=declared).model_dump_json(indent=2))
    gt = GroundTruth(poses=truths)
    (out / "ground_truth.json").write_text(gt.model_dump_json(indent=2))
    return gt


def _degrade_body(mesh: trimesh.Trimesh, rng, noise_mm: float, occlusion: float) -> None:
    """In-place: drop a fraction of faces (occlusion) then jitter vertices (sensor noise)."""
    if occlusion > 0 and len(mesh.faces) > 10:
        keep = rng.random(len(mesh.faces)) > occlusion
        if keep.any():
            mesh.update_faces(keep)
            mesh.remove_unreferenced_vertices()
    if noise_mm > 0:
        mesh.vertices = np.asarray(mesh.vertices, float) + rng.normal(0, noise_mm, (len(mesh.vertices), 3))


def build_semireal_case(real_arch_path, out_dir, n_implants: int = 3,
                        retention: Retention = Retention.CEMENT, seed: int = 0) -> GroundTruth:
    out = Path(out_dir)
    (out / "library" / _SCAN_BODY_TYPE).mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    arch, _ = normalize_orientation(trimesh.load(real_arch_path, force="mesh"))
    sites = _occlusal_sites(arch, n_implants, rng)
    teeth = sorted(rng.choice(_TOOTH_POOL, size=len(sites), replace=False).tolist())

    clean_sb = make_scan_body_mesh()
    parts = [arch]
    truths, declared = [], []
    for tooth, site in zip(teeth, sites):
        tilt_deg = float(rng.uniform(0, 6))
        tilt_axis = np.array([rng.uniform(-1, 1), rng.uniform(-1, 1), 0.0]) + [1e-6, 0, 0]
        clocking = float(rng.uniform(0, 360))
        T = (RigidTransform.from_translation(site)
             .compose(RigidTransform.from_axis_angle(tilt_axis, tilt_deg))
             .compose(RigidTransform.from_axis_angle([0, 0, 1], clocking)))
        body = clean_sb.copy()
        body.apply_transform(T.matrix)
        parts.append(body)

        platform = T.apply([0.0, 0.0, -_PLATFORM_DEPTH])
        axis = Axis.from_vector(T.rotation @ np.array([0.0, 0.0, 1.0]))
        truths.append(ImplantTruth(
            tooth=tooth, scan_body_type=_SCAN_BODY_TYPE, retention=retention,
            position=[float(x) for x in platform], axis=[float(x) for x in axis.direction],
            clocking_degrees=clocking_angle_deg(T.rotation) if retention is Retention.SCREW else None,
        ))
        declared.append(SiteSpec(tooth=tooth, scan_body_type=_SCAN_BODY_TYPE, retention=retention))

    scan = trimesh.util.concatenate(parts)
    scan.export(out / "scan.stl")
    clean_sb.export(out / "library" / _SCAN_BODY_TYPE / "mesh.stl")
    (out / "library" / _SCAN_BODY_TYPE / "transform.json").write_text(json.dumps(
        {"scan_body_to_platform": RigidTransform.from_translation([0, 0, -_PLATFORM_DEPTH]).matrix.tolist()}))
    (out / "case.json").write_text(CaseManifest(
        case_ref=f"semireal-{Path(real_arch_path).stem}", scan_file="scan.stl",
        implant_sites=declared).model_dump_json(indent=2))
    gt = GroundTruth(poses=truths)
    (out / "ground_truth.json").write_text(gt.model_dump_json(indent=2))
    return gt
