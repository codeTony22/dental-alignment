"""The background probe + bridge gate census (plan 2026-08-16, goal-3 S0).

``background_fraction`` — does an artifact show BACKGROUND (the viewer's
"white") through itself inside a site's neighbourhood disc? The formalized
version of the ad-hoc painter probes that diagnosed the ghost, the floor
breach and the moat on the real fleet. Implementation is a pure-numpy
COVERAGE rasterization (no matplotlib, no anti-aliasing, no sampling):
project every nearby face along the view, mark the pixels its triangle
covers, and count disc pixels no face covered. Deterministic to the float
by construction. Views: occlusal plus four oblique tilts — a moat can hide
from straight above and show at a tilt (the client's own screenshots are
obliques).

``bridge_gate_census`` — replay ``_bridge_recess_collar``'s outer-candidate
gates per boundary loop, importing the bridge's OWN constants (one source
of truth), and report per-gate verdicts. A silent bridge is then a table,
not a mystery.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np
import trimesh

from case_prep.pipeline.deliverables import (_BRIDGE_ROUNDNESS_MM,
                                             _BRIDGE_SEARCH_MM,
                                             _BRIDGE_Z_BAND_MM,
                                             _loop_overlap_fraction)

#: pixel pitch of the coverage raster (mm) — fine enough that a 0.3mm moat
#: sliver is several pixels wide, coarse enough to stay fast
_PIXEL_MM = 0.05
#: the oblique tilt the client's own screenshots roughly use
_OBLIQUE_DEG = 35.0
#: the acceptance disc reaches this far past the catalog rim — the moat's
#: own scale (measured banks sit within ~1mm of the mouth), NOT the
#: bridge's generous radial search
_DISC_MARGIN_MM = 3.0


def _site_frame(pose: np.ndarray):
    pose = np.asarray(pose, float)
    origin = pose[:3, 3]
    R = pose[:3, :3]
    axis = R @ np.array([0.0, 0.0, 1.0])
    u = R @ np.array([1.0, 0.0, 0.0])
    v = R @ np.array([0.0, 1.0, 0.0])
    return origin, axis, u, v


def _views(axis: np.ndarray, u: np.ndarray, v: np.ndarray
           ) -> List[np.ndarray]:
    """Occlusal + four obliques, each a unit view direction."""
    c, s = np.cos(np.radians(_OBLIQUE_DEG)), np.sin(np.radians(_OBLIQUE_DEG))
    views = [axis]
    for t in (u, -u, v, -v):
        w = axis * c + t * s
        views.append(w / np.linalg.norm(w))
    return views


def _coverage_background(mesh: trimesh.Trimesh, origin: np.ndarray,
                         view: np.ndarray, disc_r: float) -> float:
    """Fraction of disc pixels not covered by any face, along ``view``."""
    h = (np.array([1.0, 0.0, 0.0]) if abs(view[0]) < 0.9
         else np.array([0.0, 1.0, 0.0]))
    a = np.cross(view, h)
    a /= np.linalg.norm(a)
    b = np.cross(view, a)

    V = np.asarray(mesh.vertices, float) - origin
    P = np.column_stack([V @ a, V @ b])
    F = np.asarray(mesh.faces, np.int64)
    tri = P[F]                                          # (n, 3, 2)

    # only faces whose projected bbox touches the disc participate
    lo = tri.min(axis=1)
    hi = tri.max(axis=1)
    near = ((lo[:, 0] <= disc_r) & (hi[:, 0] >= -disc_r)
            & (lo[:, 1] <= disc_r) & (hi[:, 1] >= -disc_r))
    tri = tri[near]

    n_pix = int(np.ceil(2 * disc_r / _PIXEL_MM))
    xs = (np.arange(n_pix) + 0.5) * _PIXEL_MM - disc_r
    covered = np.zeros((n_pix, n_pix), dtype=bool)

    for t in tri:
        x0 = max(0, int((t[:, 0].min() + disc_r) / _PIXEL_MM))
        x1 = min(n_pix, int((t[:, 0].max() + disc_r) / _PIXEL_MM) + 1)
        y0 = max(0, int((t[:, 1].min() + disc_r) / _PIXEL_MM))
        y1 = min(n_pix, int((t[:, 1].max() + disc_r) / _PIXEL_MM) + 1)
        if x0 >= x1 or y0 >= y1:
            continue
        gx, gy = np.meshgrid(xs[x0:x1], xs[y0:y1], indexing="ij")
        # barycentric point-in-triangle, inclusive of edges
        d = ((t[1, 1] - t[2, 1]) * (t[0, 0] - t[2, 0])
             + (t[2, 0] - t[1, 0]) * (t[0, 1] - t[2, 1]))
        if abs(d) < 1e-12:
            continue
        w0 = ((t[1, 1] - t[2, 1]) * (gx - t[2, 0])
              + (t[2, 0] - t[1, 0]) * (gy - t[2, 1])) / d
        w1 = ((t[2, 1] - t[0, 1]) * (gx - t[2, 0])
              + (t[0, 0] - t[2, 0]) * (gy - t[2, 1])) / d
        w2 = 1.0 - w0 - w1
        inside = (w0 >= -1e-9) & (w1 >= -1e-9) & (w2 >= -1e-9)
        covered[x0:x1, y0:y1] |= inside

    gx, gy = np.meshgrid(xs, xs, indexing="ij")
    in_disc = np.hypot(gx, gy) <= disc_r
    n_disc = int(in_disc.sum())
    if n_disc == 0:
        return 0.0
    background = in_disc & ~covered
    return float(background.sum()) / float(n_disc)


def background_fraction(mesh: trimesh.Trimesh, pose: np.ndarray,
                        rim_r: float,
                        disc_r: Optional[float] = None) -> float:
    """The WORST background fraction across the occlusal + oblique views,
    inside the site disc (default radius ``rim_r + _DISC_MARGIN_MM`` — the
    moat's own scale; measured banks sit within ~1mm of the mouth)."""
    origin, axis, u, v = _site_frame(pose)
    r = float(disc_r) if disc_r is not None else float(rim_r) + _DISC_MARGIN_MM
    worst = 0.0
    for view in _views(axis, u, v):
        worst = max(worst,
                    _coverage_background(mesh, origin, view, r))
    return worst


def bridge_gate_census(out_loops: Sequence[np.ndarray],
                       mouth: np.ndarray,
                       pose: np.ndarray) -> List[Dict[str, object]]:
    """Per candidate loop: n / r̄±σ / ā / a-span and the bridge's own outer
    gates as booleans — ``radius_window`` (every point beyond the mouth's
    own max radius, within the search), ``z_band``, ``roundness``, and
    ``mouth_duplicate`` (exact-point overlap). Constants imported from the
    bridge itself — one source of truth."""
    origin, axis, u, v = _site_frame(pose)

    def _ra(pts: np.ndarray):
        rel = np.asarray(pts, float) - origin
        aa = rel @ axis
        rr = np.hypot(rel @ u, rel @ v)
        return rr, aa

    mouth_r, mouth_a = _ra(mouth)
    mouth_r_max = float(mouth_r.max())
    mouth_a_mid = float(mouth_a.mean())

    rows: List[Dict[str, object]] = []
    for lp in out_loops:
        r, a = _ra(lp)
        rows.append({
            "n": int(len(lp)),
            "r_mean": float(r.mean()),
            "r_std": float(r.std()),
            "a_mean": float(a.mean()),
            "a_span": float(a.max() - a.min()),
            "mouth_duplicate": bool(
                _loop_overlap_fraction(np.asarray(lp, float),
                                       np.asarray(mouth, float)) > 0.9),
            "radius_window": bool(
                np.all(r > mouth_r_max - 1e-6)
                and np.all(r < mouth_r_max + _BRIDGE_SEARCH_MM)),
            "z_band": bool(np.all(np.abs(a - mouth_a_mid)
                                  < _BRIDGE_Z_BAND_MM)),
            "roundness": bool(float(r.std()) <= _BRIDGE_ROUNDNESS_MM),
        })
    return rows
