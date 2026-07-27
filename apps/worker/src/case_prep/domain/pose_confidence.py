"""Per-site alignment confidence (Spec A, 2026-07-15). Pure domain logic — no IO, no
framework. Turns a set of bootstrap re-seats (the same site aligned under perturbed marks)
plus the site's existing quality signals into a graded confidence the gate can act on.

Distinct from ``domain.confidence`` (the Phase-2A retention/ICP gate): this measures how
STABLE the alignment is to plausible operator click error — "would a slightly different,
equally-plausible click give the same seat?" A tight bootstrap spread = yes = trustworthy.
It is a READ-OUT: it never changes the shipped pose or the identified variant.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import numpy as np
from scipy.spatial.transform import Rotation


@dataclass(frozen=True)
class PoseSpread:
    """p90 deviation of a bootstrap pose ensemble from its reference seat."""
    pos_p90_mm: float
    axis_p90_deg: float
    clock_p90_deg: float


def pose_spread(poses: List[np.ndarray], reference: np.ndarray) -> PoseSpread:
    """Spread of a set of 4x4 poses about ``reference``, split into the three physically
    distinct ways a cap seat can wobble: TILT of the axis (out-of-cone error), CLOCKING
    about the axis (coded-face rotation), and POSITION. Reported as p90 so one unlucky
    perturbation does not dominate. Axis-tilt and clocking are separated because a revolute
    part tolerates clocking wobble very differently from axis wobble."""
    ref = np.asarray(reference, float)
    ref_R = ref[:3, :3]
    ref_axis = ref_R @ np.array([0.0, 0.0, 1.0])
    pos: List[float] = []
    tilt: List[float] = []
    clock: List[float] = []
    for m in poses:
        m = np.asarray(m, float)
        pos.append(float(np.linalg.norm(m[:3, 3] - ref[:3, 3])))
        axis = m[:3, :3] @ np.array([0.0, 0.0, 1.0])
        cos = float(np.clip(axis @ ref_axis, -1.0, 1.0))
        tilt.append(float(np.degrees(np.arccos(cos))))
        # relative rotation in the reference frame: its z-component is clocking (rotation
        # ABOUT the axis), its xy-components are tilt — the rotvec cleanly separates them
        rel = Rotation.from_matrix(ref_R.T @ m[:3, :3]).as_rotvec()
        clock.append(float(np.degrees(abs(rel[2]))))

    def p90(vals: List[float]) -> float:
        return float(np.percentile(vals, 90)) if vals else 0.0

    return PoseSpread(p90(pos), p90(tilt), p90(clock))


def fitzpatrick_tre(marks_xy: np.ndarray, target_xy: np.ndarray,
                    fle_mm: float) -> Optional[float]:
    """Fitzpatrick's expected target registration error (mm) at ``target_xy`` from N
    fiducials with per-fiducial localization error ``fle_mm``, in the occlusal plane:

        TRE^2 = (FLE^2 / N) * (1 + (1/3) * sum_k d_k^2 / f_k^2)

    over the two principal axes k of the fiducial configuration, where d_k is the target's
    distance from principal axis k and f_k the RMS fiducial distance from it. This is a
    PRIOR — it predicts pose error from the mark GEOMETRY alone, before any seat. Returns
    None for a configuration that cannot support it (< 3 marks, or collinear marks whose
    perpendicular spread is zero). Note it is spread-independent exactly at the fiducial
    centroid (d_k=0), which is correct physics: there, only mark COUNT lowers TRE."""
    P = np.asarray(marks_xy, float)
    if len(P) < 3:
        return None
    c = P.mean(axis=0)
    centred = P - c
    _, _, vt = np.linalg.svd(centred, full_matrices=False)  # principal axes (2D)
    tgt = np.asarray(target_xy, float) - c
    total = 0.0
    for k in range(2):
        e_k = vt[k]                            # principal axis k (line through centroid)
        e_perp = np.array([-e_k[1], e_k[0]])   # perpendicular: distance-to-line direction
        f_k = float(np.sqrt(np.mean((centred @ e_perp) ** 2)))
        if f_k < 1e-6:
            return None                        # collinear about this axis — no spread
        d_k = float(abs(tgt @ e_perp))
        total += (d_k * d_k) / (f_k * f_k)
    tre_sq = (fle_mm * fle_mm / len(P)) * (1.0 + total / 3.0)
    return float(np.sqrt(max(tre_sq, 0.0)))


# Grade thresholds, calibrated to DISCRIMINATE the measured fleet distribution (2026-07-15):
# good single-pair gestures re-seat with p90 spread ~0.7-1.3mm / 7-18deg, sloppy gestures
# ~1.6-2.5mm / 16-48deg. A bootstrap p90 runs ~2x the actual pose error (real errors ~0.48mm
# centre / 4-5deg axis), so "high" (<=0.6mm / <=8deg) implies ~<=0.3mm/4deg actual — and in
# practice is reached by tight BORDER-CLICK gestures, not single pairs; a good pair lands
# "medium", which is the honest signal ("add border clicks for high confidence").
#
# INPUT (roadmap #2) now truth-calibrated: an operator repeat-click FLE study over the
# `reports/live-demo/run-history.jsonl` history (10 independent 4-point border gestures across
# 4 real sites, 27-40 clicks depending on channel; see docs/research/fle-calibration.md) measured
# the occlusal-plane (xy) click scatter directly, three independent ways — repeat-position
# matching (core, slip excluded: p50/p68/p90 = 0.32/0.46/0.61mm, n=27), within-gesture
# leave-one-out circle fit (p50/p68/p90 = 0.23/0.41/0.77mm, n=40), and leave-one-out plane fit
# (p50/p68/p90 = 0.31/0.50/0.91mm, n=40). All three invert to a per-axis Gaussian sigma of
# ~0.27-0.32mm — CONFIRMING the bootstrap's sigma_mm=0.3 default (auto_flow.py); no change made.
# Because that default is now grounded rather than anecdotal, and the p90 spread ranges above
# were themselves measured downstream of it, these threshold constants stay as they are. What
# remains open is roadmap #7: an independent-ground-truth pass/fail line — these grades
# discriminate the fleet distribution correctly but are not yet validated against a truth-known
# seat error. Any single HARD signal off drops straight to "low".
_POS_HIGH_MM = 0.60
_POS_LOW_MM = 1.50
_AXIS_HIGH_DEG = 8.0
_AXIS_LOW_DEG = 22.0
_RIM_HIGH_MM = 0.80
_RIM_LOW_MM = 1.20
_TOP_LOW_MM = 1.50           # matches the guard/guidance ride-off bar
_BORDER_DISAGREE_MM = 0.60   # matches the guidance border-click bar


def confidence_grade(spread: PoseSpread, rim_agreement_mm: Optional[float],
                     top_face_p90_mm: Optional[float], candidates_too_close: bool,
                     border_disagree_mm: Optional[float],
                     tre_mm: Optional[float]) -> str:
    """'high' | 'medium' | 'low'. High = the seat is stable under click noise AND every
    quality signal is tight AND the variant is unambiguous. A single HARD failure (unstable
    pose, high seat residual, riding top face) is 'low'; softer misses are 'medium'. tre_mm
    is carried for reporting; the grade rests on the empirical bootstrap spread + the
    measured seat signals, not the prior."""
    if (spread.pos_p90_mm > _POS_LOW_MM
            or spread.axis_p90_deg > _AXIS_LOW_DEG
            or (rim_agreement_mm is not None and rim_agreement_mm > _RIM_LOW_MM)
            or (top_face_p90_mm is not None and top_face_p90_mm > _TOP_LOW_MM)):
        return "low"

    tight = (spread.pos_p90_mm <= _POS_HIGH_MM
             and spread.axis_p90_deg <= _AXIS_HIGH_DEG
             and (rim_agreement_mm is None or rim_agreement_mm <= _RIM_HIGH_MM)
             and not candidates_too_close
             and (border_disagree_mm is None or border_disagree_mm <= _BORDER_DISAGREE_MM))
    return "high" if tight else "medium"
