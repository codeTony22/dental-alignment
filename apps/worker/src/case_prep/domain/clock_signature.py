"""Coded-cutout clock signature — the ROTATIONAL instrument the client's eye uses.

Client report 2026-07-20: "still not properly aligned and rotated to match the healing
cap and bore channels." Root cause (measured, docs/research + scratchpad synthesis): a
lab tech judges rotation by the CODED CUTOUTS on the cap's top face; the pipeline's
recess-void azimuth is systematically unreliable (a partially-visible recess dip biases
its centroid sideways — measured: the void clock rotated AWAY from the coded features
on 5 of 7 sites where it fired), and the mean-distance face sweep is angularly flat.

This module implements the extractor that WON the two-pose consistency validation
(2026-07-20, design "e8": for the same scan at two poses with an exactly-known applied
rotation, the extracted angles must differ by that rotation — e8 passed 6/7 rotated
sites to <=10 deg, the one failure being a half-occluded ring its own evidence gate
flags; simpler 1-D azimuthal profiles passed at most 3/7 and MUST NOT be substituted).

Design (all deterministic):
- The scan crop, in the CANONICAL template frame of a candidate pose, is unwrapped into
  a (theta, r) DEPTH image: 120 x 8 cells over r in [0.42, 0.80]*rmax, z in
  [ztop-1.2, ztop+0.25]; cell value = clip(ztop - p90(z), 0, 0.9). The p90/max-z
  channel reads the coded dips (0.4-0.7mm deep at r [0.46-0.72]*rmax); a p10/depth
  channel reads the AXISYMMETRIC screw recess instead and carries no angular signal —
  that inversion is why the earlier 1-D depth profile failed validation.
- The template's own signature keeps only INFORMATIVE radial rows (azimuthal span
  > 0.15mm, deep at < 80% of azimuths — drops the axisymmetric recess rows; this
  filtering is what makes the low-relief 4020 class work).
- Azimuths are measured about the SCAN's own cap-rim centre (converged trimmed Kasa on
  the rim ring, z ztop+/-0.35, r [0.80, 1.15]*rmax, 0.15mm trim), estimated ONCE as a
  physical point and mapped through candidate poses. Do NOT re-estimate per candidate
  (breaks two-pose consistency, measured) and do NOT use the scan's p97 radius ring
  (that is the gingival emergence ring at ~1.5*rmax, not the cap rim — measured).
- Masked per-shift Pearson correlation of the row-zero-meaned images over 120 circular
  shifts, parabolic sub-bin refinement; prominence = peak minus the best rival local
  maximum >= 30 deg away.

Convention: the returned ``shift_deg`` is the CCW rotation about the part's canonical
axis to ADD to the pose so the coded cutouts align with the scan (the "m" convention of
the validation round: m = -delta where scan(theta) ~ template(theta - delta))."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
import trimesh

N_THETA = 120                      # 3-degree bins
N_R = 8
R_LO, R_HI = 0.42, 0.80           # radial band of the coded features, *rmax
Z_LO, Z_HI = -1.2, 0.25           # z window about ztop
CLIP_MM = 0.9
ROW_SPAN_MIN_MM = 0.15            # informative-row gate
ROW_DEEP_FRAC_MAX = 0.8           # axisymmetric-recess row rejection

# evidence gates, calibrated on the validation fleet (weak sites cap6020 ship
# prom 0.03 / t7 prom 0.02 refuse; strong sites read prom 0.3-1.9)
EV_MIN_CORR = 0.45
EV_MIN_PROM = 0.10
EV_MIN_OCC = 0.30


def wrap_deg(a: float) -> float:
    return float((a + 180.0) % 360.0 - 180.0)


@dataclass
class TemplateSignature:
    ztop: float
    rmax: float
    image: np.ndarray            # (N_THETA, n_informative_rows), row-zero-meaned
    rows: np.ndarray             # indices of the informative radial rows
    relief_span_mm: float        # max cell relief across informative rows

    @property
    def has_coded_relief(self) -> bool:
        return self.image.shape[1] > 0 and self.relief_span_mm > 0.2


@dataclass
class NotchReading:
    shift_deg: Optional[float]   # rotation to ADD to the pose (None = no signal)
    corr: float
    prominence: float
    occupancy: float
    n_points: int
    peaks: List[Tuple[float, float]] = field(default_factory=list)  # (shift, corr)

    @property
    def has_evidence(self) -> bool:
        return (self.shift_deg is not None and self.corr >= EV_MIN_CORR
                and self.prominence >= EV_MIN_PROM
                and self.occupancy >= EV_MIN_OCC)


def _kasa(xy: np.ndarray) -> np.ndarray:
    A = np.c_[2.0 * xy, np.ones(len(xy))]
    sol, *_ = np.linalg.lstsq(A, (xy ** 2).sum(axis=1), rcond=None)
    return sol[:2]


def _depth_grid(pts: np.ndarray, ztop: float, rmax: float,
                centre_xy: np.ndarray, min_pts: int) -> Tuple[np.ndarray, float]:
    """(theta, r) image of clip(ztop - p90(z), 0, CLIP_MM); NaN where under-occupied."""
    xy = pts[:, :2] - centre_xy
    r = np.linalg.norm(xy, axis=1)
    sel = ((r > R_LO * rmax) & (r < R_HI * rmax)
           & (pts[:, 2] > ztop + Z_LO) & (pts[:, 2] < ztop + Z_HI))
    th = np.degrees(np.arctan2(xy[sel, 1], xy[sel, 0])) % 360.0
    rr, z = r[sel], pts[sel, 2]
    tb = np.minimum((th / (360.0 / N_THETA)).astype(int), N_THETA - 1)
    rb = np.minimum(((rr - R_LO * rmax) / ((R_HI - R_LO) * rmax)
                     * N_R).astype(int), N_R - 1)
    img = np.full((N_THETA, N_R), np.nan)
    flat = tb * N_R + rb
    order = np.argsort(flat)
    flat_s, z_s = flat[order], z[order]
    starts = np.searchsorted(flat_s, np.arange(N_THETA * N_R))
    ends = np.searchsorted(flat_s, np.arange(N_THETA * N_R) + 1)
    for cell in range(N_THETA * N_R):
        a, b = starts[cell], ends[cell]
        if b - a >= min_pts:
            img[cell // N_R, cell % N_R] = np.clip(
                ztop - np.percentile(z_s[a:b], 90), 0.0, CLIP_MM)
    occ = float(np.mean(~np.isnan(img)))
    return img, occ


def _row_zero_mean(img: np.ndarray) -> np.ndarray:
    out = img.copy()
    for j in range(img.shape[1]):
        col = out[:, j]
        m = ~np.isnan(col)
        if m.sum() >= 8:
            col[m] = col[m] - col[m].mean()
        else:
            col[:] = np.nan
        out[:, j] = col
    return out


_SIG_CACHE: dict = {}


def template_signature(template: trimesh.Trimesh) -> TemplateSignature:
    """Precompute (cached by mesh identity) the template's coded-relief signature.
    The seeded surface sampling SAVES AND RESTORES the global RNG state — this may be
    called mid run_auto_case, whose downstream stages depend on the pinned stream
    (measured hazard, review 2026-07-20)."""
    key = id(template)
    if key in _SIG_CACHE:
        return _SIG_CACHE[key]
    state = np.random.get_state()
    try:
        np.random.seed(0)
        samp, _ = trimesh.sample.sample_surface(template, 120_000)
    finally:
        np.random.set_state(state)
    samp = np.asarray(samp, float)
    tv = np.asarray(template.vertices, float)
    ztop = float(tv[:, 2].max())
    top = tv[tv[:, 2] > ztop - 1.0]
    rmax = float(np.percentile(np.linalg.norm(top[:, :2], axis=1), 97))
    ring = tv[np.linalg.norm(tv[:, :2], axis=1) > rmax - 0.4]
    centre = _kasa(ring[:, :2]) if len(ring) >= 20 else np.zeros(2)
    img, _ = _depth_grid(samp, ztop, rmax, centre, min_pts=2)
    spans = np.nanmax(img, axis=0) - np.nanmin(img, axis=0)
    rows = np.where(np.nan_to_num(spans) > ROW_SPAN_MIN_MM)[0]
    good = [j for j in rows
            if float(np.nanmean(img[:, j] > 0.15)) < ROW_DEEP_FRAC_MAX]
    rows = np.array(good if good else rows.tolist(), int)
    sig = TemplateSignature(
        ztop=ztop, rmax=rmax,
        image=_row_zero_mean(img[:, rows]) if len(rows) else np.empty((N_THETA, 0)),
        rows=rows,
        relief_span_mm=float(np.nan_to_num(spans[rows]).max()) if len(rows) else 0.0)
    _SIG_CACHE[key] = sig
    return sig


def scan_rim_centre(pts_canon: np.ndarray, ztop: float, rmax: float) -> np.ndarray:
    """Converged trimmed Kasa on the SCAN's own cap-rim ring, canonical frame.
    Estimated once per site; callers map the resulting physical point through
    candidate poses (never re-estimate per candidate)."""
    c = np.zeros(2)
    band_pts = pts_canon[(pts_canon[:, 2] > ztop - 1.2)
                         & (pts_canon[:, 2] < ztop + 0.8)]
    if len(band_pts) >= 30:
        r = np.linalg.norm(band_pts[:, :2], axis=1)
        keep = r < 1.6 * rmax
        if keep.sum() >= 30:
            rp = np.percentile(r[keep], 97)
            band = band_pts[keep][np.abs(r[keep] - rp) < 0.4]
            if len(band) >= 20:
                c = _kasa(band[:, :2])
    band0 = pts_canon[(pts_canon[:, 2] > ztop - 0.35)
                      & (pts_canon[:, 2] < ztop + 0.35)]
    for _ in range(12):
        if len(band0) < 20:
            break
        r = np.linalg.norm(band0[:, :2] - c, axis=1)
        band = band0[(r > 0.80 * rmax) & (r < 1.15 * rmax)]
        if len(band) < 20:
            break
        cn = _kasa(band[:, :2])
        rr = np.linalg.norm(band[:, :2] - cn, axis=1)
        keep = band[np.abs(rr - np.median(rr)) < 0.15]
        if len(keep) >= 20:
            cn = _kasa(keep[:, :2])
        done = np.linalg.norm(cn - c) < 0.01
        c = cn
        if done:
            break
    return c


def _masked_shift_corr(scan_img: np.ndarray, tmpl_img: np.ndarray):
    n = scan_img.shape[0]
    corr = np.full(n, np.nan)
    for k in range(n):
        t = np.roll(tmpl_img, k, axis=0)
        m = ~np.isnan(scan_img) & ~np.isnan(t)
        if m.sum() < 40:
            continue
        a, b = scan_img[m], t[m]
        sa, sb = a.std(), b.std()
        if sa < 1e-9 or sb < 1e-9:
            continue
        corr[k] = float(np.mean((a - a.mean()) * (b - b.mean())) / (sa * sb))
    if np.isnan(corr).all():
        return None, 0.0, 0.0, None
    corr_f = np.where(np.isnan(corr), -1.0, corr)
    k0 = int(np.argmax(corr_f))
    peak = float(corr_f[k0])
    ym, yp = corr_f[(k0 - 1) % n], corr_f[(k0 + 1) % n]
    denom = ym - 2 * corr_f[k0] + yp
    off = 0.5 * (ym - yp) / denom if abs(denom) > 1e-12 else 0.0
    off = float(np.clip(off, -0.5, 0.5))
    delta = wrap_deg((k0 + off) * (360.0 / n))
    # rival local maxima >= 30 deg away (circular)
    sep_bins = int(round(30.0 / (360.0 / n)))
    rivals = []
    for i in range(n):
        if min(abs(i - k0), n - abs(i - k0)) < sep_bins:
            continue
        if corr_f[i] >= corr_f[(i - 1) % n] and corr_f[i] >= corr_f[(i + 1) % n]:
            rivals.append((wrap_deg(-(i * 360.0 / n)), float(corr_f[i])))
    second = max((c for _, c in rivals), default=float(corr_f.min()))
    rivals.sort(key=lambda t: -t[1])
    return delta, peak, peak - second, rivals[:3]


def notch_reading(scan_pts_canon: np.ndarray, sig: TemplateSignature,
                  centre_xy: np.ndarray) -> NotchReading:
    """Read the coded-cutout misalignment of a scan crop (canonical template frame of
    the pose under evaluation) against a template signature, azimuths about
    ``centre_xy`` (the once-estimated scan rim centre mapped into this frame)."""
    if not sig.has_coded_relief:
        return NotchReading(None, 0.0, 0.0, 0.0, 0)
    img, occ = _depth_grid(scan_pts_canon, sig.ztop, sig.rmax, centre_xy, min_pts=1)
    n_pts = int(np.sum(~np.isnan(img)))
    simg = _row_zero_mean(img[:, sig.rows])
    delta, peak, prom, rivals = _masked_shift_corr(simg, sig.image)
    if delta is None:
        return NotchReading(None, 0.0, 0.0, occ, n_pts)
    return NotchReading(wrap_deg(-delta), peak, prom, occ, n_pts,
                        peaks=rivals or [])
