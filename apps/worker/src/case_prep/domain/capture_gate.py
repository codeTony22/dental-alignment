"""The CAPTURE GATE — scan-quality intake checks, per site (master plan §1 SCAN row,
§8 item 11 / slice 30).

The industry's coded-cap gold standards refuse inadequate scans AT INTAKE, while the
patient is still in the chair, with a concrete recapture instruction:

- ZimVie BellaTek coded healing caps (lab manual ZVINST0213 / tech guide ZVINST0206): "Verify that
  a clear scan has captured all the ... markings, all the soft-tissue contours and the
  entire circumference of the healing abutment"; the collar must sit 1-2 mm above the
  soft tissue (1 mm MINIMUM) around the whole circumference or the case is rejected.
- Dentsply Sirona Atlantis (Scan Upload guide 32670865): a formal RESCAN REQUESTED
  order state — "The scans you provided are not suitable for abutment design and will
  be deleted" — for missing/corrupted feature surface.
  (Both cited in docs/research/doctor-inputs-research.md, capture-factor rows 2-3.)

Our pipeline had NO such gate: t7 (doctor-zimmer-4.5) shipped with ~46% of its
seat-band arc EMPTY scan and the fleet's worst collar exposure — a scan no algorithm
can rescue, discovered at the END of the pipeline instead of intake
(docs/research/marks-as-locators-plan.md §1c "scan holes: workflow, not software").

Three checks per site, each value/bound/verdict + one concrete recapture message:
  (a) RIM ARC COVERAGE   — occupancy of the seat-band annulus arc (the |d-rim_r|<0.5
      band auto_flow._rim_seat seats in, the arc-bin idea generalised to 24 bearings);
  (b) CODE-BAND VISIBILITY — occupancy of the coded-cutout annulus, the same
      (theta, r) grid geometry clock_signature reads rotation from;
  (c) COLLAR EXPOSURE    — rim height above the surrounding tissue (robust proxy:
      rim_z minus the median tissue z in a surrounding annulus).
Overall verdict = the worst check. Pure domain geometry: numpy only, deterministic,
no IO, no RNG draws.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

import numpy as np

# The coded-band geometry is clock_signature's OWN convention — imported, not copied,
# so the gate can never drift from what the rotation reader actually needs.
from case_prep.domain.clock_signature import R_HI, R_LO, Z_HI, Z_LO

VERDICT_PASS = "pass"
VERDICT_MARGINAL = "marginal"
VERDICT_RESCAN = "rescan"
_SEVERITY = {VERDICT_PASS: 0, VERDICT_MARGINAL: 1, VERDICT_RESCAN: 2}

# --- (a) RIM ARC COVERAGE ------------------------------------------------------------
# Band construction = auto_flow._rim_seat's seat band (|xy-dist - rim_r| < 0.5) with
# the same inlier-refined plane fit (3 fit-and-prune rounds at 0.6mm — wall/pocket
# points do not lie in the rim plane), then a tight in-plane slab. Occupancy over 24
# bearings, a bearing counting only when it holds a real surface sample (not 1-2 stray
# wall points crossing the annulus).
RIM_BAND_HALF_MM = 0.5     # the seat band _rim_seat itself fits (auto_flow.py)
RIM_PREFILTER_Z_MM = 1.5   # drop far wall/tissue before the plane fit
RIM_SLAB_HALF_MM = 0.25    # in-plane slab; at 0.5 stray wall points faked bearings
RIM_N_BINS = 24
RIM_BIN_MIN_PTS = 10       # IOS-class density (fleet: 0.1-0.2mm spacing). CALIBRATION
#                            RECEIPT (2026-07-24 fleet sweep, curated marks): with this
#                            construction t7 reads 0.542 occupied — exactly the recorded
#                            "46% of the seat-band arc empty" failure exemplar (master
#                            plan §1); the healthy fleet reads 0.583-1.0.
# The standard requires the ENTIRE circumference (ZVINST0206): pass allows at most 2 of 24
# bearings missing; below the rescan line sits the measured unrescuable pair (t7 0.542,
# t4 0.542) with the worst healthy site (t13, ring 25%-visible by physics, a genuinely
# borderline capture) one bearing above at 0.583.
RIM_PASS_MIN = 0.92
RIM_RESCAN_BELOW = 0.55

# --- (b) CODE-BAND VISIBILITY ---------------------------------------------------------
# Annulus [R_LO, R_HI]*rim_r, z in [rim_z+Z_LO, rim_z+Z_HI] — clock_signature's coded
# band. Grid 60x4 (vs the reader's 120x8): occupancy at the reader's own resolution is
# mesh-density-sensitive (measured: healthy zimmer sites read 0.27-0.33 on coarser
# meshes purely from cell size), so the gate judges visibility on an equal-geometry
# coarser grid where the healthy fleet reads 0.66-0.98.
CODE_N_THETA = 60
CODE_N_R = 4
# The standard: "code markings clearly visible" or the scan is rejected. The rotation reader
# refuses below occupancy 0.30 on its canonical-frame grid (clock_signature.EV_MIN_OCC);
# this raw-frame coarser grid reads systematically higher, so the rescan floor carries
# 1.5x headroom (0.45). Fleet receipt: healthy 0.66-0.98; a half-carved code band
# measures ~0.5 (synthetic); pass at 0.70 keeps the whole healthy fleet pass/marginal.
CODE_PASS_MIN = 0.70
CODE_RESCAN_BELOW = 0.45

# --- (c) COLLAR EXPOSURE --------------------------------------------------------------
# Proxy: rim_z minus the median tissue z in the annulus [rim_r+1.0, rim_r+3.0] (tissue
# within +-4mm of rim height — neighbouring crowns tower above and are excluded).
EXPO_TISSUE_R_MM = (1.0, 3.0)
EXPO_TISSUE_Z_WINDOW_MM = 4.0
EXPO_MIN_TISSUE_PTS = 30
# The lab manual's hard rule: collar 1-2mm above the soft tissue, 1mm MINIMUM (ZVINST0213) —
# the pass line. Rescan floor 0.35mm: fleet-calibrated between the worst healthy site
# (t13 reads 0.64 — degraded but workable, the physics memo's tissue-biased site) and
# the measured unrescuable pair (t4 0.18, t7 -0.29 — collar at/below tissue level,
# exactly the class the standard refuses outright).
EXPO_PASS_MIN_MM = 1.0
EXPO_RESCAN_BELOW_MM = 0.35

# rim_z estimation: the cap's top/rim is the HIGHEST strong level slab over the cap's
# own footprint (recess core excluded). Sloped walls/tissue spread across z and cannot
# concentrate 60% of the strongest slab's mass in one 0.6mm window (verified on all 10
# fleet sites: rim_z landed on the cap top everywhere, incl. t7 where a naive band
# percentile read the neighbouring wall 3mm too high).
_SLAB_MM = 0.6
_SLAB_STEP_MM = 0.2
_SLAB_KEEP_FRAC = 0.6


@dataclass(frozen=True)
class CaptureCheck:
    """One cited capture check: the measured value against its bounds. ``value`` may be
    None when the input is too starved to measure — never silently a pass."""

    name: str
    value: Optional[float]
    bound_pass: float          # value >= bound_pass          -> pass
    bound_rescan: float        # value <  bound_rescan        -> rescan (else marginal)
    verdict: str
    message: str

    def to_dict(self) -> dict:
        return {"name": self.name,
                "value": None if self.value is None else round(float(self.value), 3),
                "bound_pass": self.bound_pass, "bound_rescan": self.bound_rescan,
                "verdict": self.verdict, "message": self.message}


@dataclass(frozen=True)
class CaptureAssessment:
    """The per-site intake assessment. Overall verdict = the WORST check (the industry
    pattern: any one deficiency is grounds to recapture while the patient is in the
    chair; Atlantis' RESCAN REQUESTED names single causes)."""

    verdict: str
    rim_arc: CaptureCheck
    code_band: CaptureCheck
    collar: CaptureCheck
    rim_z: Optional[float] = None    # local-frame rim height the checks were read at

    @property
    def checks(self) -> Tuple[CaptureCheck, CaptureCheck, CaptureCheck]:
        return (self.rim_arc, self.code_band, self.collar)

    def to_dict(self) -> dict:
        return {"verdict": self.verdict,
                "rim_z_mm": None if self.rim_z is None else round(float(self.rim_z), 3),
                "checks": [c.to_dict() for c in self.checks]}


def _verdict(value: Optional[float], bound_pass: float, bound_rescan: float) -> str:
    if value is None:
        return VERDICT_MARGINAL  # unmeasurable is flagged, never silently passed
    if value >= bound_pass:
        return VERDICT_PASS
    if value < bound_rescan:
        return VERDICT_RESCAN
    return VERDICT_MARGINAL


def _top_slab_z(L: np.ndarray, seed_xy: np.ndarray, rim_r: float) -> Optional[float]:
    xy = L[:, :2] - seed_xy
    r = np.linalg.norm(xy, axis=1)
    z = L[(r > 0.9) & (r < rim_r + RIM_BAND_HALF_MM), 2]
    if len(z) < 40:
        return None
    zg = np.arange(z.min(), z.max() + _SLAB_STEP_MM, _SLAB_STEP_MM)
    counts = np.array([((z >= z0) & (z < z0 + _SLAB_MM)).sum() for z0 in zg])
    top = np.where(counts >= _SLAB_KEEP_FRAC * counts.max())[0][-1]
    zsel = z[(z >= zg[top]) & (z < zg[top] + _SLAB_MM)]
    return float(np.median(zsel))


def _longest_missing_run(occupied: np.ndarray) -> Tuple[int, float]:
    """(run length, centroid bin) of the longest CIRCULAR run of missing bins.
    The caller converts the centroid bin to an angle in its own bin convention."""
    n = len(occupied)
    missing = ~occupied
    if missing.all():
        return n, 0.0
    # unroll twice for circularity; runs longer than n are clipped by the all-check
    best_len, best_start = 0, 0
    run, start = 0, 0
    for i in range(2 * n):
        if missing[i % n]:
            if run == 0:
                start = i
            run += 1
            if run > best_len and run <= n:
                best_len, best_start = run, start
        else:
            run = 0
    centre_bin = (best_start + (best_len - 1) / 2.0) % n
    return best_len, float(centre_bin)


def _direction_label(angle: float, outward_xy: Optional[np.ndarray]) -> str:
    """Name the side a missing arc faces: buccal/lingual via the arch's outward
    direction when it is decisive, else the occlusal-view clock bearing."""
    d = np.array([np.cos(angle), np.sin(angle)])
    if outward_xy is not None:
        o = np.asarray(outward_xy, float)
        nrm = np.linalg.norm(o)
        if nrm > 1e-9:
            dot = float(d @ (o / nrm))
            if dot >= 0.5:
                return "cheek-facing (buccal) side"
            if dot <= -0.5:
                return "tongue-facing (lingual) side"
    hour = int(np.round(((90.0 - np.degrees(angle)) % 360.0) / 30.0)) % 12 or 12
    return f"{hour} o'clock side (occlusal view)"


def _rim_arc_check(L: np.ndarray, seed_xy: np.ndarray, rim_r: float, rim_z: float,
                   outward_xy: Optional[np.ndarray]) -> CaptureCheck:
    xy = L[:, :2] - seed_xy
    r = np.linalg.norm(xy, axis=1)
    band = L[(np.abs(r - rim_r) < RIM_BAND_HALF_MM)
             & (np.abs(L[:, 2] - rim_z) < RIM_PREFILTER_Z_MM)]
    n = np.array([0.0, 0.0, 1.0])
    c0 = np.array([seed_xy[0], seed_xy[1], rim_z])
    if len(band) >= 40:
        # the _rim_seat inlier-refined plane fit: wall points do not lie in the rim's
        # plane, a genuinely tilted rim's own points survive because they define it
        c0 = band.mean(axis=0)
        for _ in range(3):
            _, _, vt = np.linalg.svd(band - c0, full_matrices=False)
            n = vt[2] / np.linalg.norm(vt[2])
            keep = np.abs((band - c0) @ n) < 0.6
            if keep.all() or keep.sum() < 40:
                break
            band = band[keep]
            c0 = band.mean(axis=0)
        if n[2] < 0:
            n = -n
        if n[2] < np.cos(np.radians(45.0)):  # implausible rim plane — junk fit
            n, c0 = np.array([0.0, 0.0, 1.0]), np.array([seed_xy[0], seed_xy[1], rim_z])
    band = band[np.abs((band - c0) @ n) < RIM_SLAB_HALF_MM]
    th = np.arctan2(band[:, 1] - seed_xy[1], band[:, 0] - seed_xy[0])
    bins = ((th + np.pi) // (2 * np.pi / RIM_N_BINS)).astype(int) % RIM_N_BINS
    counts = np.bincount(bins, minlength=RIM_N_BINS)
    occupied = counts >= RIM_BIN_MIN_PTS
    value = float(occupied.mean())
    verdict = _verdict(value, RIM_PASS_MIN, RIM_RESCAN_BELOW)
    if verdict == VERDICT_PASS:
        msg = (f"Entire rim circumference captured "
               f"({int(occupied.sum())}/{RIM_N_BINS} bearings).")
    else:
        run, centre_bin = _longest_missing_run(occupied)
        # rim bin 0 starts at -pi (arctan2 + pi flooring above)
        angle = -np.pi + (centre_bin + 0.5) * 2 * np.pi / RIM_N_BINS
        side = _direction_label(angle, outward_xy)
        msg = (f"Rescan the rim on the {side} — "
               f"{round(100 * (1 - value))}% of the ring is missing "
               f"(largest gap ≈{run * 360 // RIM_N_BINS}°). Coded-cap workflows "
               f"require the entire cap circumference in the scan.")
    return CaptureCheck("rim_arc", value, RIM_PASS_MIN, RIM_RESCAN_BELOW, verdict, msg)


def _code_band_check(L: np.ndarray, seed_xy: np.ndarray, rim_r: float, rim_z: float,
                     outward_xy: Optional[np.ndarray]) -> CaptureCheck:
    xy = L[:, :2] - seed_xy
    r = np.linalg.norm(xy, axis=1)
    sel = ((r > R_LO * rim_r) & (r < R_HI * rim_r)
           & (L[:, 2] > rim_z + Z_LO) & (L[:, 2] < rim_z + Z_HI))
    th = np.degrees(np.arctan2(xy[sel, 1], xy[sel, 0])) % 360.0
    tb = np.minimum((th / (360.0 / CODE_N_THETA)).astype(int), CODE_N_THETA - 1)
    rb = np.minimum(((r[sel] - R_LO * rim_r) / ((R_HI - R_LO) * rim_r)
                     * CODE_N_R).astype(int), CODE_N_R - 1)
    grid = np.zeros((CODE_N_THETA, CODE_N_R), bool)
    grid[tb, rb] = True
    value = float(grid.mean())
    verdict = _verdict(value, CODE_PASS_MIN, CODE_RESCAN_BELOW)
    if verdict == VERDICT_PASS:
        msg = f"Coded band {round(100 * value)}% captured — codes readable."
    else:
        msg = (f"Rescan the cap's top face — only {round(100 * value)}% of the coded "
               f"band is captured; the code markings must be clearly visible to read "
               f"the cap's rotation (the standard rejects scans without them).")
        occupied_cols = grid.any(axis=1)  # _longest_missing_run takes OCCUPIED flags
        run, centre_bin = _longest_missing_run(occupied_cols)
        if run >= 4:  # a contiguous >=24 deg blind sector is directional information
            # code column 0 starts at 0 deg from +x CCW (the % 360 binning above);
            # wrap the centroid back into [-pi, pi) for the direction label
            deg = ((centre_bin + 0.5) * (360.0 / CODE_N_THETA) + 180.0) % 360.0 - 180.0
            msg += (f" Worst sector faces the "
                    f"{_direction_label(np.radians(deg), outward_xy)}.")
    return CaptureCheck("code_band", value, CODE_PASS_MIN, CODE_RESCAN_BELOW,
                        verdict, msg)


def _collar_check(L: np.ndarray, seed_xy: np.ndarray, rim_r: float,
                  rim_z: float) -> CaptureCheck:
    xy = L[:, :2] - seed_xy
    r = np.linalg.norm(xy, axis=1)
    tissue = L[(r > rim_r + EXPO_TISSUE_R_MM[0]) & (r < rim_r + EXPO_TISSUE_R_MM[1])]
    tissue = tissue[np.abs(tissue[:, 2] - rim_z) < EXPO_TISSUE_Z_WINDOW_MM]
    if len(tissue) < EXPO_MIN_TISSUE_PTS:
        # The standard requires ALL soft-tissue contours captured — absent tissue is itself
        # a capture defect; flagged marginal (unmeasurable), never silently passed
        return CaptureCheck(
            "collar_exposure", None, EXPO_PASS_MIN_MM, EXPO_RESCAN_BELOW_MM,
            VERDICT_MARGINAL,
            "Surrounding soft-tissue contours are not in the scan — collar exposure "
            "unmeasurable. Rescan the tissue collar around the cap (the standard "
            "requires all soft-tissue contours).")
    value = float(rim_z - np.median(tissue[:, 2]))
    verdict = _verdict(value, EXPO_PASS_MIN_MM, EXPO_RESCAN_BELOW_MM)
    if verdict == VERDICT_PASS:
        msg = f"Collar {value:.2f}mm supragingival (≥1mm collar rule met)."
    elif verdict == VERDICT_MARGINAL:
        msg = (f"Collar is only {value:.2f}mm above the surrounding tissue — below "
               f"the 1mm supragingival minimum the coded-cap workflow requires "
               f"(the standard asks 1-2mm). Consider tissue retraction and rescan.")
    else:
        msg = (f"Collar reads {value:.2f}mm above the surrounding tissue — effectively "
               f"submerged. The standard hard-requires ≥1mm supragingival around the whole "
               f"circumference; retract tissue or swap to a taller healing cap, then "
               f"rescan while the patient is in the chair.")
    return CaptureCheck("collar_exposure", value, EXPO_PASS_MIN_MM,
                        EXPO_RESCAN_BELOW_MM, verdict, msg)


def assess_capture(scan_points_local: np.ndarray, site_centre_xy: Sequence[float],
                   rim_r_hint: float,
                   arch_outward_xy: Optional[Sequence[float]] = None
                   ) -> CaptureAssessment:
    """Assess one site's capture quality in the crowns-up LOCAL frame.

    ``site_centre_xy``/``rim_r_hint``: a locator-quality centre and the site's rim
    radius (the human centre+rim pair, a border-circle fit, or the detector's measured
    rim). The pair is used AS GIVEN — the gate never re-centres or self-corrects it
    (the centre+rim pair is one measurement owned at its source; see the re-click
    pair-integrity record).

    ``arch_outward_xy``: optional unit-ish xy direction from the arch centre toward
    the cheek at this site, for buccal/lingual naming in messages. Default: derived
    from the scan's own xy centroid (the palate/arch interior lies inward of the tooth
    row on every jaw scan — a cheap, honest proxy). Pass None-safe custom values when
    the caller has a better arch frame.
    """
    L = np.asarray(scan_points_local, float)
    seed_xy = np.asarray(site_centre_xy, float)
    rim_r = float(rim_r_hint)
    if arch_outward_xy is None:
        arch_outward_xy = seed_xy - L[:, :2].mean(axis=0)
    outward = np.asarray(arch_outward_xy, float)

    rim_z = _top_slab_z(L, seed_xy, rim_r)
    if rim_z is None:
        msg = ("Too little scan surface at the marked site to measure capture "
               "quality — rescan the cap area.")
        starved = [
            CaptureCheck("rim_arc", 0.0, RIM_PASS_MIN, RIM_RESCAN_BELOW,
                         VERDICT_RESCAN, msg),
            CaptureCheck("code_band", 0.0, CODE_PASS_MIN, CODE_RESCAN_BELOW,
                         VERDICT_RESCAN, msg),
            CaptureCheck("collar_exposure", None, EXPO_PASS_MIN_MM,
                         EXPO_RESCAN_BELOW_MM, VERDICT_MARGINAL, msg),
        ]
        return CaptureAssessment(VERDICT_RESCAN, *starved, rim_z=None)

    rim = _rim_arc_check(L, seed_xy, rim_r, rim_z, outward)
    code = _code_band_check(L, seed_xy, rim_r, rim_z, outward)
    collar = _collar_check(L, seed_xy, rim_r, rim_z)
    overall = max((c.verdict for c in (rim, code, collar)),
                  key=lambda v: _SEVERITY[v])
    return CaptureAssessment(overall, rim, code, collar, rim_z=rim_z)
