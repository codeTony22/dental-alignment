"""PRINTED PHANTOM evaluator — closes the loop opened by ``make_phantom.py``.

Given a SCANNED phantom (arbitrary frame, printed from ``phantom-plate.stl``) and its
``phantom-ground-truth.json``, this:

  1. REGISTERS the scan into the design frame using the fiducials — 3 corner posts of
     distinct height+diameter matched by signature (coarse), refined by trimmed ICP
     against a design-frame reference cloud reconstructed purely from the truth JSON
     (never the pristine STL, which a real evaluator would not have either).
  2. Obtains operator marks per site — from ``--marks`` if given, else SYNTHESIZES the
     same gesture an operator would make (a centre click at the designed cap top + 4
     border clicks around the designed visible-rim circle, snapped to the actual scan
     surface, jittered by the measured 0.3mm click FLE).
  3. Runs the REAL pipeline (``run_auto_case``) with each site's TRUE variant declared
     (the shipping path), and compares the shipped pose to the designed truth.
  4. Builds the CONFIDENCE-VALIDATION table: per-site grade vs true pose error, plus
     the fleet verdict (rank correlation, max true error per grade). Since the truth
     also fixes each cap's DESIGNED CLOCK ANGLE (make_phantom ``clock_deg``), every
     row additionally reports the residual clock error measured by BOTH rotation
     instruments — the coded-feature reading and the recess-void bore azimuth
     (``clock_readings``) — making the phantom the physical arbiter of the
     codes-vs-recess conflict.

Open3D is never used (segfaults on this host — see ``case_prep.domain.icp``); all
registration math is pure numpy/scipy, matching the rest of the pipeline.

CLI:
    cd apps/worker
    PYTHONWARNINGS=ignore .venv/bin/python tools/evaluate_phantom.py \\
        --scan <scanned-phantom.stl> --truth reports/phantom/phantom-ground-truth.json \\
        [--marks <marks.json>] [--out-dir reports/phantom]
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_phantom as mp  # noqa: E402  (local sibling module, path bootstrap above)

from case_prep.adapters.cap_library import CapLibrary  # noqa: E402
from case_prep.domain.cap_catalog import CapSpec  # noqa: E402
from case_prep.domain.clock_signature import (notch_reading, scan_rim_centre,  # noqa: E402
                                              template_signature, wrap_deg)
from case_prep.domain.geometry import Axis  # noqa: E402
from case_prep.domain.icp import trimmed_icp  # noqa: E402
from case_prep.pipeline.auto_flow import (ConfirmedSite, run_auto_case,  # noqa: E402
                                          _ring_centre_3d, _screw_recess_centre,
                                          _template_bore_centre)

WORKER_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = WORKER_ROOT / "reports" / "phantom"
DEFAULT_LIB_ROOT = WORKER_ROOT / "data" / "real" / "library" / "caps"
DEFAULT_CONSTRUCTION_ROOT = WORKER_ROOT / "data" / "real" / "library" / "construction"
_VENDOR_BY_MODEL = {"zimmer-4.5": "atlantis", "neodent-gm": "dess"}

# Registration sanity bar (see docstring of `register_scan`): a genuine phantom's
# BEST candidate frame scores well under 2 on real (noisy, occluded) data; a
# non-phantom scan (wrong object, or the right frame simply not present) scores in
# the hundreds because no fiducial signature is found at all. See
# reports/phantom/ generation notes / phantom-protocol.md for the measurement.
_COARSE_SCORE_ABORT = 15.0
_ICP_FITNESS_ABORT = 0.20
_ICP_RMSE_ABORT_MM = 1.5
_MIN_SCAN_POINTS = 200

_CLICK_FLE_SIGMA_MM = 0.3  # measured operator centre/border click noise (docs/research/fle-calibration.md)


class RegistrationError(RuntimeError):
    """The scan could not be registered to the phantom design frame — either it is
    not this phantom, or the fiducials are too degraded/occluded to trust. Raised
    instead of ever emitting a fabricated validation."""


@dataclass(frozen=True)
class RegistrationResult:
    transform: np.ndarray  # 4x4, scan (world) frame -> design frame
    frame_label: str
    coarse_score: float
    icp_fitness: float
    icp_rmse_mm: float
    post_matches: Dict[str, Dict] = field(default_factory=dict)


# ---------------------------------------------------------------------------------
# Step 1: registration
# ---------------------------------------------------------------------------------
def _candidate_frames(pts: np.ndarray) -> Tuple[List[np.ndarray], np.ndarray]:
    """PCA-derived candidate design frames (columns = length, width, up).

    A REAL scanned phantom (lab/desktop scanner, like a stone model) is captured
    from one side — the face resting on the scanner stage is never seen — so the
    scan is a single-sided OPEN shell, not the closed printable solid. That also
    means there is no 'flat bottom band' to detect: PCA's third axis is oriented by
    the mean-normal test alone (mirrors ``cap_detection.crown_up_axis`` — outward
    normals predominantly face the scanner, i.e. away from the material). Two
    ambiguities survive an imperfect/borderline normal signal: the up sign AND the
    in-plane 180-degree rotation about it — rather than trust a marginal normal
    projection, this returns ALL 4 combinations and lets the fiducial-signature
    match (which is unambiguous) pick the winner."""
    c = pts.mean(axis=0)
    centred = pts - c
    _, _, vt = np.linalg.svd(centred, full_matrices=False)
    up0 = vt[2]
    length0 = vt[0] - (vt[0] @ up0) * up0
    norm_len = np.linalg.norm(length0)
    length0 = length0 / norm_len if norm_len > 1e-9 else np.array([1.0, 0.0, 0.0])

    frames = []
    for up_sign in (1.0, -1.0):
        up = up_sign * up0
        for len_sign in (1.0, -1.0):
            length = len_sign * length0
            width = np.cross(up, length)
            frames.append(np.c_[length, width, up])
    return frames, c


def _kabsch(p: np.ndarray, q: np.ndarray) -> np.ndarray:
    """Best rigid 4x4 mapping p -> q (Umeyama without scale); local reimplementation
    (not importing icp.py's private ``_kabsch``) — the standard SVD/Kabsch algorithm."""
    cp, cq = p.mean(axis=0), q.mean(axis=0)
    h = (p - cp).T @ (q - cq)
    u, _, vt = np.linalg.svd(h)
    d = np.sign(np.linalg.det(vt.T @ u.T)) or 1.0
    r = vt.T @ np.diag([1.0, 1.0, d]) @ u.T
    t = cq - r @ cp
    m = np.eye(4)
    m[:3, :3] = r
    m[:3, 3] = t
    return m


def _score_and_match_frame(pts: np.ndarray, frame: np.ndarray, c: np.ndarray,
                           truth: Dict) -> Tuple[float, Dict[str, Dict]]:
    """Fiducial-signature score for one candidate frame: sum of squared
    (height,diameter) errors at each of the 3 post corners (by FIXED design label —
    no permutation search needed, a wrong frame simply shows the WRONG post's, or no,
    signature there) plus a penalty if the chamfer corner unexpectedly has material.

    Heights are measured RELATIVE to each post's own local surroundings (no absolute
    design z=0 needed — a real scan may never include the bottom face at all, see
    ``_candidate_frames``): a TIGHT disc around the post gives its tip, a THIN
    ANNULUS just outside it gives the surrounding plate-top surface — both stay
    within the posts' own margin from the plate edge/ridge (never touch a side
    wall), which a single wide search disc could otherwise pick up."""
    local = (pts - c) @ frame
    score = 0.0
    matches: Dict[str, Dict] = {}
    for post in truth["fiducials"]["posts"]:
        nominal = np.array(post["xy_mm"])
        r = post["diameter_mm"] / 2.0
        d = np.linalg.norm(local[:, :2] - nominal, axis=1)
        peak_region = local[d < r + 1.0]
        background = local[(d >= r + 1.5) & (d < r + 4.0)]
        if len(peak_region) < 5 or len(background) < 5:
            score += 100.0
            continue
        background_z = float(np.median(background[:, 2]))
        peak_z = float(np.percentile(peak_region[:, 2], 98))
        obs_h = peak_z - background_z
        top_band = peak_region[peak_region[:, 2] > peak_z - 1.0]
        if len(top_band) < 3:
            score += 100.0
            continue
        cluster_xy = top_band[:, :2].mean(axis=0)
        obs_d = float(2 * np.percentile(np.linalg.norm(top_band[:, :2] - cluster_xy, axis=1), 90))
        score += (obs_h - post["height_mm"]) ** 2 + (obs_d - post["diameter_mm"]) ** 2
        cluster_local = np.array([cluster_xy[0], cluster_xy[1], top_band[:, 2].max()])
        matches[post["corner"]] = {
            "world": cluster_local @ frame.T + c,
            "design_expected": np.array([nominal[0], nominal[1],
                                         truth["plate"]["base_height_mm"] + post["height_mm"]]),
        }
    # the chamfer corner is CUT AWAY: a tight radius right at the true (uncut) plate
    # corner should find almost nothing there, regardless of any local z datum
    chamfer = truth["fiducials"]["chamfer"]
    near_c = local[np.linalg.norm(local[:, :2] - np.array(chamfer["plate_corner_xy_mm"]), axis=1) < 3.0]
    score += 30.0 if len(near_c) > 8 else 0.0
    return score, matches


def register_scan(scan: trimesh.Trimesh, truth: Dict) -> RegistrationResult:
    """Register ``scan`` (arbitrary frame) into the phantom's DESIGN frame.

    Coarse: PCA gives the plate's axes up to a 4-way ambiguity (up sign x in-plane
    180-degree rotation — see ``_candidate_frames``); each candidate is scored by
    fiducial height+diameter signature match at the 3 labeled post corners (measured
    RELATIVE to each post's own local surroundings, so no absolute datum/bottom face
    is needed), and the winner's 3 matched post positions give a coarse rigid
    transform (Kabsch). Refine: trimmed ICP (domain.icp — Open3D SEGFAULTS on this
    host, never used) against a reference cloud reconstructed from the truth JSON
    alone (plate top/bottom/posts/chamfer + each site's cap template sampled at its
    designed pose) — never the pristine STL, which a real evaluator would not have.

    Raises RegistrationError with a clear message (never a bare exception, never a
    silently-wrong transform) when the fiducial signature is not found or the
    refined fit is not trustworthy — e.g. this is not the phantom.
    """
    pts = np.asarray(scan.vertices, float)
    if len(pts) < _MIN_SCAN_POINTS:
        raise RegistrationError(
            f"scan has only {len(pts)} vertices (< {_MIN_SCAN_POINTS}) — too sparse to "
            f"be a phantom scan; aborting rather than guessing a registration")

    frames, c = _candidate_frames(pts)
    scored = [(*_score_and_match_frame(pts, f, c, truth), f, name)
             for f, name in zip(frames, ("A", "B", "C", "D"))]
    scored.sort(key=lambda t: t[0])
    best_score, best_matches, best_frame, best_name = scored[0]

    if best_score > _COARSE_SCORE_ABORT or len(best_matches) < 3:
        raise RegistrationError(
            f"phantom fiducial signature not found (best candidate frame score "
            f"{best_score:.1f}, threshold {_COARSE_SCORE_ABORT}; "
            f"{len(best_matches)}/3 posts matched) — this does not look like the "
            f"printed phantom (wrong object, or fiducials too occluded/damaged); "
            f"aborting rather than producing a fake validation")

    measured = np.array([best_matches[p["corner"]]["world"] for p in truth["fiducials"]["posts"]])
    expected = np.array([best_matches[p["corner"]]["design_expected"]
                         for p in truth["fiducials"]["posts"]])
    m0 = _kabsch(measured, expected)

    target = mp.build_reference_cloud(truth, lib_root=DEFAULT_LIB_ROOT)
    rng = np.random.default_rng(0)
    src_idx = (rng.choice(len(pts), size=15000, replace=False)
              if len(pts) > 15000 else np.arange(len(pts)))
    icp = trimmed_icp(pts[src_idx], target, m0, max_corr_dist=1.5, trim_fraction=0.85)

    if icp.fitness < _ICP_FITNESS_ABORT or icp.inlier_rmse > _ICP_RMSE_ABORT_MM:
        raise RegistrationError(
            f"registration refinement did not converge to a trustworthy fit "
            f"(ICP fitness {icp.fitness:.2f} < {_ICP_FITNESS_ABORT}, or rmse "
            f"{icp.inlier_rmse:.2f}mm > {_ICP_RMSE_ABORT_MM}mm) — aborting rather "
            f"than producing a fake validation")

    return RegistrationResult(
        transform=icp.transform.matrix, frame_label=best_name, coarse_score=float(best_score),
        icp_fitness=float(icp.fitness), icp_rmse_mm=float(icp.inlier_rmse),
        post_matches={k: {"world": v["world"].tolist()} for k, v in best_matches.items()},
    )


# ---------------------------------------------------------------------------------
# Step 2: operator marks (given, or synthesized from truth)
# ---------------------------------------------------------------------------------
def _raycast_snap(vertices: np.ndarray, aim: np.ndarray, axis: np.ndarray,
                  t0: np.ndarray, t1: np.ndarray, lateral_radii=(1.0, 2.0, 4.0, 8.0)
                  ) -> np.ndarray:
    """Simulate an operator's click: a raycast down the viewing direction (here, the
    cap's own axis — a reasonable proxy for 'looking at the site') lands on the
    TOP-MOST real surface point near the aim's lateral (XY-in-the-click-plane)
    position — NOT simply the nearest point in 3D, which can jump to a nearer but
    unrelated lower feature (measured: the naive nearest-surface snap landed on the
    plate/collar 1-2mm below an aim at the cap's own flare). Mirrors the click
    simulation already established in tests/test_auto_flow.py
    (``test_multipoint_rim_gesture_seats_within_bounds``)."""
    rel = vertices - aim
    lateral = np.c_[rel @ t0, rel @ t1]
    d = np.linalg.norm(lateral, axis=1)
    for r in lateral_radii:
        near = np.where(d < r)[0]
        if len(near):
            axial = rel[near] @ axis
            return vertices[near[np.argmax(axial)]]
    return aim  # nothing nearby at all — fall back to the raw aim (marks stay a locator)


def synthesize_marks(truth: Dict, registered_scan: trimesh.Trimesh, sigma_mm: float = _CLICK_FLE_SIGMA_MM
                     ) -> Dict[str, Dict]:
    """The gesture an operator would make: a centre click at the designed cap top +
    4 border clicks around the designed VISIBLE-rim circle (the tissue/collar line —
    what a real operator actually sees, not necessarily the cap's own physical rim),
    each jittered in-plane by the measured click FLE and snapped to the actual
    (registered) scan surface via a raycast-style snap — the same path a real
    gesture takes. Deterministic: one RNG stream seeded from a fixed constant,
    consumed in truth['sites'] order."""
    verts = np.asarray(registered_scan.vertices, float)
    rng = np.random.default_rng(20260715)
    marks: Dict[str, Dict] = {}
    for site in truth["sites"]:
        axis = np.array(site["axis_world"], float)
        axis = axis / np.linalg.norm(axis)
        t0 = np.cross(axis, [0.0, 0.0, 1.0])
        if np.linalg.norm(t0) < 1e-6:
            t0 = np.array([1.0, 0.0, 0.0])
        t0 = t0 / np.linalg.norm(t0)
        t1 = np.cross(axis, t0)

        centre_aim = np.array(site["top_world"], float) + t0 * rng.normal(0, sigma_mm) \
            + t1 * rng.normal(0, sigma_mm)
        centre_snap = _raycast_snap(verts, centre_aim, axis, t0, t1)

        # Aim at the 4 REAL mesh points make_phantom.py identified near the visible
        # boundary (one per angular sector) rather than an idealized circle — these
        # caps are not rotationally symmetric at a given height (a coded flat/cutout
        # feature can leave one side's silhouette 1-2mm narrower than the opposite
        # side), so a uniform-radius aim can miss the actual surface on the narrow
        # side and the raycast snap then jumps to unrelated (often much lower)
        # geometry. See make_phantom._visible_ring_points_local.
        border = []
        for ring_pt in site["rim_ring_world"]:
            aim = np.array(ring_pt, float) + t0 * rng.normal(0, sigma_mm) + t1 * rng.normal(0, sigma_mm)
            border.append(_raycast_snap(verts, aim, axis, t0, t1))

        marks[site["site_id"]] = {
            "tooth": site["tooth"],
            "center": [float(x) for x in centre_snap],
            "rim_points": [[float(x) for x in p] for p in border],
        }
    return marks


def load_marks(path: "Path | str", registration: RegistrationResult) -> Dict[str, Dict]:
    """Operator marks from a file, in the SCAN's own (pre-registration) world
    coordinates (matches ``--scan``) — transformed into the design frame the
    registered scan (and the pipeline call) operate in."""
    raw = json.loads(Path(path).read_text())
    m = registration.transform
    out: Dict[str, Dict] = {}
    for site_id, entry in raw.items():
        centre = (np.array(entry["center"], float) @ m[:3, :3].T) + m[:3, 3]
        rim_points = [(np.array(p, float) @ m[:3, :3].T) + m[:3, 3] for p in entry.get("rim_points", [])]
        out[site_id] = {
            "tooth": entry["tooth"],
            "center": [float(x) for x in centre],
            "rim_points": [[float(x) for x in p] for p in rim_points],
        }
    return out


# ---------------------------------------------------------------------------------
# Step 3: run the real pipeline, declared-variant shipping path
# ---------------------------------------------------------------------------------
def run_pipeline(truth: Dict, registered_scan: trimesh.Trimesh, marks: Dict[str, Dict],
                 work_dir: "Path | str", lib_root: "Path | str" = DEFAULT_LIB_ROOT,
                 construction_root: "Path | str" = DEFAULT_CONSTRUCTION_ROOT
                 ) -> Dict[str, Dict]:
    """One ``run_auto_case`` call per model (a shared CapLibrary can't safely serve
    two vendors with colliding variant codes, e.g. both catalogs have a '6020'), each
    declaring the site's TRUE variant — the shipping path. Returns tooth -> combined
    row (the summary row + the written implant.json's pose_matrix/position/axis)."""
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    by_model: Dict[str, List[Dict]] = {}
    for site in truth["sites"]:
        by_model.setdefault(site["model"], []).append(site)

    rows: Dict[str, Dict] = {}
    for model, sites in by_model.items():
        lib = CapLibrary.load(Path(lib_root) / model)
        vendor = _VENDOR_BY_MODEL.get(model, model)
        construction_mesh = trimesh.load(
            Path(construction_root) / vendor / f"{model}-scanbody.stl", force="mesh")
        confirmed = []
        for site in sites:
            m = marks[site["site_id"]]
            confirmed.append(ConfirmedSite(
                tooth=site["tooth"], center=tuple(m["center"]),
                declared_variant=site["variant"],
                center_mark=m["center"], rim_points=m["rim_points"]))
        summary = run_auto_case(
            case_id=f"phantom-{model}", scan=registered_scan, library=lib,
            construction_mesh=construction_mesh, vendor=vendor, confirmed=confirmed,
            jaw_label="phantom", out_dir=work / model, generate_product=False,
            compute_confidence=True)
        for row in summary["sites"]:
            tooth = row["tooth"]
            implant_json_path = work / model / f"phantom-{model}-{tooth}-implant.json"
            if implant_json_path.exists():
                row = {**row, "implant_record": json.loads(implant_json_path.read_text())}
            rows[str(tooth)] = row
    return rows


# ---------------------------------------------------------------------------------
# Step 4: truth comparison + the confidence-validation table
# ---------------------------------------------------------------------------------
def true_pose_error(shipped: Dict, truth_site: Dict) -> Optional[Dict]:
    """centre error (mm, split in-plane vs along-axis/depth), axis error (deg), and
    identified-vs-declared variant agreement, for one site. None when the pipeline
    could not seat this site at all (row carries 'error')."""
    record = shipped.get("implant_record")
    if "error" in shipped or record is None:
        return None
    shipped_pos = np.array(record["position"], float)
    shipped_axis = np.array(record["axis"], float)
    truth_pose = np.array(truth_site["pose"], float)
    truth_pos = truth_pose[:3, 3]
    truth_axis = truth_pose[:3, :3] @ np.array([0.0, 0.0, 1.0])

    err_vec = shipped_pos - truth_pos
    depth_mm = float(err_vec @ truth_axis)
    inplane_mm = float(np.linalg.norm(err_vec - depth_mm * truth_axis))
    centre_mm = float(np.linalg.norm(err_vec))
    axis_deg = Axis.from_vector(shipped_axis).angle_to(Axis.from_vector(truth_axis))

    variant_ok = (record.get("implant_model") == truth_site["model"]
                 and record.get("variant_code") == truth_site["variant"])
    return dict(centre_mm=centre_mm, inplane_mm=inplane_mm, depth_mm=depth_mm,
               axis_deg=float(axis_deg), variant_correct=bool(variant_ok))


def clock_readings(scan_pts: np.ndarray, template: trimesh.Trimesh,
                   shipped: Dict, truth_site: Dict) -> Optional[Dict]:
    """The CLOCK ERROR of one shipped pose, measured TWO independent ways against the
    designed clock angle — the physical arbiter for the codes-vs-recess instrument
    conflict (auto_flow winner pass, 2026-07-20: the two instruments disagreed on 5
    of 7 fleet sites and on a rigid part they cannot both be right).

    The designed truth pose already contains ``clock_deg`` (make_phantom rotates the
    template about its own canonical axis before placement), so the shipped pose's
    TRUE residual clock error is the twist of truth_pose^-1 @ shipped_pose about the
    canonical +z axis. Each instrument independently estimates that same residual
    from the scan at the shipped pose:

    (a) CODES — ``notch_reading`` at the shipped pose (azimuths about the scan's own
        once-estimated rim centre, the production convention): the reading grows
        WITH an applied rotation (two-pose identity, validated design e8), so the
        reading itself IS the estimate. clock_err_codes_deg = |reading - twist|.
    (b) RECESS — the scanned screw-void centre (``_screw_recess_centre``, canonical
        frame of the shipped pose) vs where the CAD bore's off-axis arm points: the
        azimuth of (void - rim centre) lags the azimuth of (bore - ring centre) by
        exactly the twist, so their difference is the estimate — the same bore-arm
        geometry ``_recess_clocking``'s sweep nulls, read out directly (no adoption
        gates: this is a measurement, not a pose change).

    Returns None when the site has no shipped pose. ``clock_err_*_deg`` are None
    when that instrument produced no reading at all; ``codes_evidence`` reports the
    production evidence gate (corr/prominence/occupancy) so weak reads are honest."""
    record = shipped.get("implant_record")
    if "error" in shipped or record is None:
        return None
    pose = np.asarray(record["pose_matrix"], float)
    truth_pose = np.asarray(truth_site["pose"], float)
    rel = truth_pose[:3, :3].T @ pose[:3, :3]
    twist_deg = float(np.degrees(np.arctan2(rel[1, 0], rel[0, 0])))

    # both instruments read in the CANONICAL frame of the shipped pose (z = the
    # shipped axis), on the same 8mm crop the production clock pass uses
    crop = scan_pts[np.linalg.norm(scan_pts[:, :2] - pose[:2, 3], axis=1) < 8.0]
    canon = (crop - pose[:3, 3]) @ pose[:3, :3]

    sig = template_signature(template)
    c0 = scan_rim_centre(canon, sig.ztop, sig.rmax)
    read = notch_reading(canon, sig, c0)
    codes_err = (abs(wrap_deg(read.shift_deg - twist_deg))
                 if read.shift_deg is not None else None)

    recess_err = None
    recess_estimate = None
    bore = _template_bore_centre(template)
    ring3 = _ring_centre_3d(template)
    if bore is not None and ring3 is not None:
        arm = (bore - ring3)[:2]
        lever = float(np.linalg.norm(arm))
        if lever >= 0.15:  # same no-information refusal as _recess_clocking
            v = np.asarray(template.vertices, float)
            top = v[v[:, 2] > v[:, 2].max() - 1.0]
            rmax = float(np.percentile(np.linalg.norm(top[:, :2], axis=1), 95))
            void_c = _screw_recess_centre(canon, c0, rmax, expected_radius=lever)
            if void_c is not None:
                recess_estimate = float(wrap_deg(
                    np.degrees(np.arctan2(arm[1], arm[0])
                               - np.arctan2(void_c[1] - c0[1], void_c[0] - c0[0]))))
                recess_err = abs(wrap_deg(recess_estimate - twist_deg))

    evidence = {(True, True): "codes+recess", (True, False): "codes",
                (False, True): "recess", (False, False): "none"}[
        (bool(read.has_evidence), recess_err is not None)]
    return dict(
        designed_clock_deg=float(truth_site["clock_deg"]),
        pose_twist_err_deg=twist_deg,
        clock_err_codes_deg=codes_err,
        clock_err_recess_deg=recess_err,
        codes_reading_deg=(float(read.shift_deg) if read.shift_deg is not None else None),
        recess_reading_deg=recess_estimate,
        codes_evidence=bool(read.has_evidence),
        notch_corr=float(read.corr), notch_prominence=float(read.prominence),
        notch_occupancy=float(read.occupancy),
        evidence=evidence,
    )


_GRADE_RANK = {"low": 0, "medium": 1, "high": 2}


def build_confidence_table(rows: List[Dict]) -> Tuple[str, Dict]:
    """Markdown table (per-site grade vs true error) + the fleet verdict: does grade
    ORDER correlate with true error (Spearman, when scipy + >=3 distinct-grade sites
    are available), the max true error observed within each grade, and one honest
    conclusion line."""
    lines = ["| site | model-variant | submergence | grade | pos spread p90 (mm) | "
            "axis spread p90 (deg) | true centre err (mm) | true in-plane (mm) | "
            "true depth (mm) | true axis err (deg) | variant ok | "
            "clock_err_codes_deg | clock_err_recess_deg | evidence |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    max_err_by_grade: Dict[str, float] = {}
    max_axis_by_grade: Dict[str, float] = {}
    grade_ranks: List[int] = []
    centre_errs: List[float] = []

    for r in rows:
        grade = (r["confidence"] or {}).get("grade") if r.get("confidence") else None
        err = r.get("true_error")
        centre = f"{err['centre_mm']:.3f}" if err else "n/a"
        inplane = f"{err['inplane_mm']:.3f}" if err else "n/a"
        depth = f"{err['depth_mm']:+.3f}" if err else "n/a"
        axis_e = f"{err['axis_deg']:.2f}" if err else "n/a"
        vok = ("yes" if err["variant_correct"] else "NO") if err else "n/a"
        pos_spread = r["confidence"]["pose_pos_spread_mm"] if r.get("confidence") else None
        axis_spread = r["confidence"]["pose_axis_spread_deg"] if r.get("confidence") else None
        clock = r.get("clock")
        ck_codes = (f"{clock['clock_err_codes_deg']:.1f}"
                    if clock and clock["clock_err_codes_deg"] is not None else "n/a")
        ck_recess = (f"{clock['clock_err_recess_deg']:.1f}"
                     if clock and clock["clock_err_recess_deg"] is not None else "n/a")
        ck_ev = clock["evidence"] if clock else "n/a"
        lines.append(f"| {r['site_id']} | {r['label']} | {r['submergence']} | "
                     f"{grade or 'n/a'} | {pos_spread if pos_spread is not None else 'n/a'} | "
                     f"{axis_spread if axis_spread is not None else 'n/a'} | {centre} | "
                     f"{inplane} | {depth} | {axis_e} | {vok} | "
                     f"{ck_codes} | {ck_recess} | {ck_ev} |")
        if grade and err:
            max_err_by_grade[grade] = max(max_err_by_grade.get(grade, 0.0), err["centre_mm"])
            max_axis_by_grade[grade] = max(max_axis_by_grade.get(grade, 0.0), err["axis_deg"])
            grade_ranks.append(_GRADE_RANK[grade])
            centre_errs.append(err["centre_mm"])

    spearman = None
    if len(set(grade_ranks)) >= 2 and len(grade_ranks) >= 3:
        try:
            from scipy.stats import spearmanr
            rho, pval = spearmanr(grade_ranks, centre_errs)
            spearman = {"rho": float(rho), "p_value": float(pval)}
        except ImportError:
            spearman = None

    verdict_lines = []
    for g in ("high", "medium", "low"):
        if g in max_err_by_grade:
            verdict_lines.append(
                f"- on this phantom, **{g}** bounded true error at "
                f"{max_err_by_grade[g]:.2f}mm centre / {max_axis_by_grade[g]:.1f}deg axis "
                f"(n={grade_ranks.count(_GRADE_RANK[g])})")
    if spearman is not None:
        direction = ("grade correctly tracks error (higher grade -> lower error)"
                    if spearman["rho"] < 0 else
                    "grade does NOT track error in the expected direction")
        verdict_lines.append(
            f"- Spearman rank correlation (grade vs true centre error): "
            f"rho={spearman['rho']:.2f}, p={spearman['p_value']:.3f} -> {direction}")
    else:
        verdict_lines.append(
            "- Spearman correlation not computed (fewer than 3 sites with both a "
            "grade and a true error, or all one grade) — see the per-site rows above")

    table_md = "\n".join(lines)
    verdict_md = "\n".join(verdict_lines) if verdict_lines else "- no graded sites to verdict"
    return table_md + "\n\n" + verdict_md, {
        "max_true_centre_err_mm_by_grade": max_err_by_grade,
        "max_true_axis_err_deg_by_grade": max_axis_by_grade,
        "spearman": spearman,
        "n_graded_sites": len(grade_ranks),
    }


# ---------------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------------
def evaluate_phantom(scan_path: "Path | str", truth_path: "Path | str",
                     marks_path: Optional["Path | str"] = None,
                     out_dir: "Path | str" = DEFAULT_OUT_DIR,
                     work_dir: Optional["Path | str"] = None,
                     lib_root: "Path | str" = DEFAULT_LIB_ROOT,
                     construction_root: "Path | str" = DEFAULT_CONSTRUCTION_ROOT
                     ) -> Dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    work = Path(work_dir) if work_dir is not None else out / "pipeline-work"

    truth = json.loads(Path(truth_path).read_text())
    scan = trimesh.load(scan_path, force="mesh")

    registration = register_scan(scan, truth)
    registered_scan = scan.copy()
    registered_scan.apply_transform(registration.transform)

    marks = (load_marks(marks_path, registration) if marks_path is not None
            else synthesize_marks(truth, registered_scan))

    pipeline_rows = run_pipeline(truth, registered_scan, marks, work_dir=work,
                                 lib_root=lib_root, construction_root=construction_root)

    libs = mp.load_cap_libraries(lib_root)
    reg_pts = np.asarray(registered_scan.vertices, float)
    site_results: List[Dict] = []
    for site in truth["sites"]:
        row = pipeline_rows.get(str(site["tooth"]), {"error": "no pipeline row for this tooth"})
        err = true_pose_error(row, site) if "error" not in row else None
        clock = None
        if "error" not in row:
            template = libs[site["model"]].template(CapSpec(site["model"], site["variant"]))
            clock = clock_readings(reg_pts, template, row, site)
        site_results.append({
            "site_id": site["site_id"], "tooth": site["tooth"],
            "label": f"{site['model']}-{site['variant']}", "submergence": site["submergence"],
            "confidence": row.get("confidence"), "pipeline_row": row, "true_error": err,
            "clock": clock,
        })

    table_md, verdict = build_confidence_table(site_results)

    report = {
        "registration": {
            "frame_label": registration.frame_label,
            "coarse_score": registration.coarse_score,
            "icp_fitness": registration.icp_fitness,
            "icp_residual_mm": registration.icp_rmse_mm,
        },
        "sites": site_results,
        "confidence_validation": verdict,
    }
    (out / "phantom-evaluation.json").write_text(json.dumps(report, indent=2, default=str))

    md = [
        "# Phantom evaluation",
        "",
        "## Registration",
        f"- winning candidate frame: `{registration.frame_label}`",
        f"- coarse fiducial-signature score: {registration.coarse_score:.2f} "
        f"(abort threshold {_COARSE_SCORE_ABORT})",
        f"- ICP fitness: {registration.icp_fitness:.2f}",
        f"- ICP residual (inlier RMSE): {registration.icp_rmse_mm:.3f}mm",
        "",
        "## Confidence-validation table",
        "",
        table_md,
        "",
    ]
    (out / "phantom-evaluation.md").write_text("\n".join(md))

    return report


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scan", required=True)
    p.add_argument("--truth", required=True)
    p.add_argument("--marks", default=None)
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--work-dir", default=None)
    args = p.parse_args()

    try:
        report = evaluate_phantom(args.scan, args.truth, marks_path=args.marks,
                                  out_dir=args.out_dir, work_dir=args.work_dir)
    except RegistrationError as exc:
        print(f"ABORTED: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"registration: frame={report['registration']['frame_label']} "
         f"fitness={report['registration']['icp_fitness']:.2f} "
         f"residual={report['registration']['icp_residual_mm']:.3f}mm")
    print(f"wrote {args.out_dir}/phantom-evaluation.md and .json")


if __name__ == "__main__":
    main()
